"""Score the frozen run with and without the proposed exclusions, through the analyze CLI.

Copies the frozen run (predictions, references, scenarios, exclusions) to two scratch
directories and never writes the snapshot. In one copy the exclusion record is
unchanged; in the other the proposed records (proposed_exclusions.json) are appended.
Each copy is scored with ``python -m policybench.cli analyze``, the command the freeze
runs, and the dashboard payloads are compared.

The unchanged copy must reproduce the published payload's scoring: every modelStats
field except the cost and latency fields the freeze overlays, and programStats,
heatmap, globalWeights and failureModes exactly. The script stops if it does not.

  PYTHONPATH=<checkout> <policybench venv>/bin/python \\
    reference_audit/2026-10-05/scripts/leaderboard_impact.py --scratch <dir>
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
PROPOSED = HERE / "proposed_exclusions.json"
OUT_DIR = HERE / "verification"
RUN_FILES = (
    "predictions.csv.gz",
    "reference_outputs.csv",
    "reference_outputs.csv.meta.json",
    "reference_exclusions.json",
    "scenarios.csv",
    "scenarios.csv.meta.json",
)
# The freeze overlays these from the published payload; the analyze CLI does not.
OVERLAID = {"costUsd", "costPerHousehold", "totalTokens", "latencySeconds"}
METRICS = (
    "exact",
    "within1pct",
    "within5pct",
    "within10pct",
    "score",
    "outputGroupScore",
)
EXACT_PAYLOAD_KEYS = ("programStats", "heatmap", "globalWeights", "failureModes")
RANKED = ("exact", "within1pct", "score")


def always_zero(run_dir: Path) -> dict[str, float]:
    """The always-zero baseline, as paper_results._always_zero_weighted_rates scores it."""
    import numpy as np

    from policybench.analysis import weighted_hit_rate_scores_by_model
    from policybench.reference_exclusions import scored_reference_for
    from policybench.spec import get_output_ids, output_group_id

    truth, _ = scored_reference_for(run_dir / "reference_outputs.csv")
    headline = set(get_output_ids("us", "headline"))
    truth = truth[truth["variable"].map(output_group_id).isin(headline)]
    truth = truth.reset_index(drop=True)
    truth["scenario_id"] = truth["scenario_id"].astype(str)
    scenarios = pd.read_csv(run_dir / "scenarios.csv")
    market = dict(
        zip(
            scenarios["scenario_id"].astype(str),
            pd.to_numeric(scenarios["total_income"], errors="coerce").fillna(0.0),
        )
    )
    predictions = truth[["scenario_id", "variable"]].copy()
    predictions["model"] = "Always zero"
    predictions["prediction"] = np.zeros(len(truth))
    scored = weighted_hit_rate_scores_by_model(truth, predictions, market, country="us")
    return {
        "exact": float(scored["weighted_exact"].mean()) * 100,
        "within1pct": float(scored["weighted_within_1pct"].mean()) * 100,
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(target: Path, extra: list[dict] | None) -> Path:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in RUN_FILES:
        shutil.copy2(RUN / name, target / name)
    if extra:
        record = json.loads((target / "reference_exclusions.json").read_text())
        record["exclusions"].extend(extra)
        (target / "reference_exclusions.json").write_text(
            json.dumps(record, indent=2) + "\n"
        )
    return target


def analyze(run_dir: Path) -> dict:
    out = run_dir / "analysis"
    dashboard = run_dir / "dashboard.json"
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "policybench.cli",
            "analyze",
            "-g",
            str(run_dir / "reference_outputs.csv"),
            "-p",
            str(run_dir / "predictions.csv.gz"),
            "-s",
            str(run_dir / "scenarios.csv"),
            "-o",
            str(out),
            "--app-data-output",
            str(dashboard),
            "--reference-digest",
            sha256(run_dir / "reference_outputs.csv"),
        ],
        cwd=ROOT,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    payload = json.loads(dashboard.read_text())
    return payload["countries"]["us"]


def check_reproduces_published(base: dict) -> None:
    published = json.loads(gzip.decompress((RUN / "data.json.gz").read_bytes()))
    for key in EXACT_PAYLOAD_KEYS:
        if published[key] != base[key]:
            raise SystemExit(f"unchanged copy does not reproduce published {key}")
    a = {m["model"]: m for m in published["modelStats"]}
    b = {m["model"]: m for m in base["modelStats"]}
    if set(a) != set(b):
        raise SystemExit("model sets differ")
    for model, row in a.items():
        for field, value in row.items():
            if field not in OVERLAID and value != b[model].get(field):
                raise SystemExit(f"{model}.{field}: {value} != {b[model].get(field)}")


def ranks(frame: pd.DataFrame, metric: str) -> pd.Series:
    return frame[metric].rank(ascending=False, method="min").astype(int)


def compare(base: dict, proposed: dict) -> pd.DataFrame:
    a = pd.DataFrame(base["modelStats"]).set_index("model")
    b = pd.DataFrame(proposed["modelStats"]).set_index("model")
    rows = pd.DataFrame(index=a.index)
    for metric in METRICS:
        rows[f"{metric}_published"] = a[metric]
        rows[f"{metric}_proposed"] = b[metric]
        rows[f"{metric}_delta"] = b[metric] - a[metric]
    for metric in RANKED:
        rows[f"{metric}_rank_published"] = ranks(a, metric)
        rows[f"{metric}_rank_proposed"] = ranks(b, metric)
        rows[f"{metric}_rank_change"] = (
            rows[f"{metric}_rank_published"] - rows[f"{metric}_rank_proposed"]
        )
    rows["n_published"] = a["n"]
    rows["n_proposed"] = b["n"]
    return rows.sort_values("exact_rank_published")


def program_rows(base: dict, proposed: dict) -> pd.DataFrame:
    a = pd.DataFrame(base["programStats"]).set_index("variable")
    b = pd.DataFrame(proposed["programStats"]).set_index("variable")
    rows = pd.DataFrame(index=a.index)
    for metric in ("exact", "score", "n"):
        rows[f"{metric}_published"] = a[metric]
        rows[f"{metric}_proposed"] = b[metric]
        rows[f"{metric}_delta"] = b[metric] - a[metric]
    return rows[(rows.filter(like="_delta").abs() > 1e-9).any(axis=1)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", required=True)
    args = parser.parse_args()
    scratch = Path(args.scratch)
    proposals = json.loads(PROPOSED.read_text())["exclusions"]

    base = analyze(stage(scratch / "base", None))
    check_reproduces_published(base)
    proposed = analyze(stage(scratch / "proposed", proposals))

    models = compare(base, proposed)
    zero = {
        "published": always_zero(scratch / "base"),
        "proposed": always_zero(scratch / "proposed"),
    }
    leader = models.sort_values("exact_rank_proposed").index[0]
    programs = program_rows(base, proposed)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    models.to_csv(OUT_DIR / "leaderboard_impact_models.csv")
    programs.to_csv(OUT_DIR / "leaderboard_impact_programs.csv")
    summary = {
        "proposed_exclusions": [
            f"{p['scenario_id']}/{p['variable']}" for p in proposals
        ],
        "published_reproduced": True,
        "scored_outputs": {
            "published": int(base["modelStats"][0]["n"]),
            "proposed": int(proposed["modelStats"][0]["n"]),
        },
        "exact_delta_pp": {
            "min": float(models["exact_delta"].min()),
            "max": float(models["exact_delta"].max()),
            "mean": float(models["exact_delta"].mean()),
        },
        "score_delta": {
            "min": float(models["score_delta"].min()),
            "max": float(models["score_delta"].max()),
        },
        **{
            f"{metric}_rank_changes": {
                model: {
                    "published": int(row[f"{metric}_rank_published"]),
                    "proposed": int(row[f"{metric}_rank_proposed"]),
                }
                for model, row in models.iterrows()
                if row[f"{metric}_rank_change"] != 0
            }
            for metric in RANKED
        },
        "always_zero_baseline": zero,
        "leader_margin_over_always_zero_exact": {
            "model": leader,
            "published": float(
                models.loc[leader, "exact_published"] - zero["published"]["exact"]
            ),
            "proposed": float(
                models.loc[leader, "exact_proposed"] - zero["proposed"]["exact"]
            ),
        },
        "top5_exact_published": models.sort_values("exact_rank_published")
        .head(5)
        .index.tolist(),
        "top5_exact_proposed": models.sort_values("exact_rank_proposed")
        .head(5)
        .index.tolist(),
    }
    (OUT_DIR / "leaderboard_impact.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    with pd.option_context("display.width", 250, "display.max_rows", 100):
        print(
            models[
                [
                    "exact_published",
                    "exact_proposed",
                    "exact_delta",
                    "exact_rank_published",
                    "exact_rank_proposed",
                    "score_published",
                    "score_proposed",
                    "score_delta",
                    "score_rank_published",
                    "score_rank_proposed",
                ]
            ].round(4)
        )
        print(programs.round(4))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
