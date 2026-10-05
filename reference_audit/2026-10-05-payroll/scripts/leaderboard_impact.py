"""Score the frozen run as published, with the proposed exclusions, and with regenerated references.

Copies the frozen run (predictions, references, scenarios, exclusions) to scratch
directories and never writes the snapshot. Three copies are scored with
``python -m policybench.cli analyze``, the command the freeze runs:

``published``
    Unchanged. It must reproduce the published payload's scoring: every modelStats field
    except the cost and latency fields the freeze overlays, and programStats, heatmap,
    globalWeights and failureModes exactly. The script stops if it does not.
``exclude``
    The records in ``proposed_exclusions.json`` appended to the exclusion record.
``regenerate``
    The references in ``proposed_regenerations.json`` written into the reference CSV
    (and the copy's sidecar digest updated to match, as a release's sidecar would be).

Sensitivity: the open state income tax withholding proposal (PolicyEngine/policybench#191,
decision d963) excludes three federal outputs and may land in the same release. With
``--with-salt`` the script also scores that proposal alone (``salt``) and each option on
top of it (``exclude+salt``, ``regenerate+salt``), reading its records from the pinned
commit ``SALT_COMMIT``; the ``*+salt`` deltas are measured against ``salt``.

  PYTHONPATH=<checkout> <policybench venv>/bin/python \\
    reference_audit/2026-10-05-payroll/scripts/leaderboard_impact.py --scratch <dir> \\
    [--with-salt]
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
EXCLUSIONS = HERE / "proposed_exclusions.json"
REGENERATIONS = HERE / "proposed_regenerations.json"
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
VARIANTS = ("exclude", "regenerate")
OUTPUT = "payroll_tax"
SALT_COMMIT = "8af912a062dd7ae1373de4c043ae2727d3406930"
SALT_RECORDS = "reference_audit/2026-10-05/proposed_exclusions.json"


def salt_exclusions() -> list[dict]:
    """The #191 proposal's records, read from its pinned commit."""
    shown = subprocess.run(
        ["git", "show", f"{SALT_COMMIT}:{SALT_RECORDS}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(shown.stdout)["exclusions"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def stage(target: Path, variant: str | None) -> Path:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in RUN_FILES:
        shutil.copy2(RUN / name, target / name)
    parts = set((variant or "").split("+")) - {""}
    extra = []
    if "exclude" in parts:
        extra += json.loads(EXCLUSIONS.read_text())["exclusions"]
    if "salt" in parts:
        extra += salt_exclusions()
    if extra:
        record = json.loads((target / "reference_exclusions.json").read_text())
        record["exclusions"].extend(extra)
        (target / "reference_exclusions.json").write_text(
            json.dumps(record, indent=2) + "\n"
        )
    if "regenerate" in parts:
        changes = json.loads(REGENERATIONS.read_text())["regenerated"]
        reference = pd.read_csv(target / "reference_outputs.csv", dtype={"value": str})
        index = reference.set_index(["scenario_id", "variable"]).index
        for change in changes:
            key = (change["scenario_id"], change["variable"])
            row = index.get_loc(key)
            if abs(float(reference.at[row, "value"]) - change["frozen_value"]) > 1e-9:
                raise SystemExit(f"{key}: frozen value differs from the reference CSV")
            reference.at[row, "value"] = repr(float(change["regenerated_value"]))
        reference.to_csv(target / "reference_outputs.csv", index=False)
        before = (RUN / "reference_outputs.csv").read_text().splitlines()
        after = (target / "reference_outputs.csv").read_text().splitlines()
        changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        if len(before) != len(after) or len(changed) != len(changes):
            raise SystemExit(
                f"regenerated CSV changes {len(changed)} lines, expected {len(changes)}"
            )
        meta_path = target / "reference_outputs.csv.meta.json"
        meta = json.loads(meta_path.read_text())
        meta["reference_csv_sha256"] = sha256(target / "reference_outputs.csv")
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")
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


def payroll_exact_counts(payload: dict) -> pd.Series:
    """Each model's count of exact payroll_tax rows among scored outputs."""
    counts: dict[str, int] = {}
    for outputs in payload["scenarioPredictions"].values():
        cells = outputs.get(OUTPUT, {})
        for model, cell in cells.items():
            if cell.get("scored"):
                counts[model] = counts.get(model, 0) + int(cell["exact"] == 100.0)
    return pd.Series(counts)


def compare(base: dict, other: dict) -> pd.DataFrame:
    a = pd.DataFrame(base["modelStats"]).set_index("model")
    b = pd.DataFrame(other["modelStats"]).set_index("model")
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
    rows["payroll_exact_published"] = payroll_exact_counts(base)
    rows["payroll_exact_proposed"] = payroll_exact_counts(other)
    rows["payroll_exact_delta"] = (
        rows["payroll_exact_proposed"] - rows["payroll_exact_published"]
    )
    return rows.sort_values("exact_rank_published")


def program_rows(base: dict, other: dict) -> pd.DataFrame:
    a = pd.DataFrame(base["programStats"]).set_index("variable")
    b = pd.DataFrame(other["programStats"]).set_index("variable")
    rows = pd.DataFrame(index=a.index)
    for metric in ("exact", "score", "n"):
        rows[f"{metric}_published"] = a[metric]
        rows[f"{metric}_proposed"] = b[metric]
        rows[f"{metric}_delta"] = b[metric] - a[metric]
    return rows[(rows.filter(like="_delta").abs() > 1e-9).any(axis=1)]


def summarize(
    models: pd.DataFrame,
    programs: pd.DataFrame,
    base: dict,
    other: dict,
    zero: dict,
    changed: list[str],
) -> dict:
    leader = models.sort_values("exact_rank_proposed").index[0]
    return {
        "changed_outputs": changed,
        "scored_outputs": {
            "published": int(base["modelStats"][0]["n"]),
            "proposed": int(other["modelStats"][0]["n"]),
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
        "payroll_exact_delta_by_model": {
            model: int(delta)
            for model, delta in models["payroll_exact_delta"].items()
            if delta != 0
        },
        "payroll_program": programs.loc[[OUTPUT]].to_dict(orient="index")
        if OUTPUT in programs.index
        else {},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--with-salt", action="store_true")
    args = parser.parse_args()
    scratch = Path(args.scratch)

    base_dir = stage(scratch / "published", None)
    base = analyze(base_dir)
    check_reproduces_published(base)
    zero_published = always_zero(base_dir)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {"published_reproduced": True}
    plan = [(variant, base, zero_published) for variant in VARIANTS]
    if args.with_salt:
        salt_dir = stage(scratch / "salt", "salt")
        salt = analyze(salt_dir)
        salt_zero = always_zero(salt_dir)
        plan.insert(0, ("salt", base, zero_published))
        plan += [(f"{variant}+salt", salt, salt_zero) for variant in VARIANTS]
        summary["salt_commit"] = SALT_COMMIT
    for variant, reference_payload, reference_zero in plan:
        run_dir = stage(scratch / variant, variant)
        other = analyze(run_dir)
        models = compare(reference_payload, other)
        programs = program_rows(reference_payload, other)
        zero = {"published": reference_zero, "proposed": always_zero(run_dir)}
        records = []
        if "exclude" in variant:
            records += json.loads(EXCLUSIONS.read_text())["exclusions"]
        if "regenerate" in variant:
            records += json.loads(REGENERATIONS.read_text())["regenerated"]
        if variant == "salt":
            records += salt_exclusions()
        changed = [f"{r['scenario_id']}/{r['variable']}" for r in records]
        models.to_csv(
            OUT_DIR / f"leaderboard_impact_{variant.replace('+', '_plus_')}_models.csv"
        )
        programs.to_csv(
            OUT_DIR
            / f"leaderboard_impact_{variant.replace('+', '_plus_')}_programs.csv"
        )
        summary[variant] = summarize(
            models, programs, reference_payload, other, zero, changed
        )
        summary[variant]["measured_against"] = (
            "salt" if variant.endswith("+salt") else "published"
        )
        with pd.option_context("display.width", 250, "display.max_rows", 100):
            print(f"\n=== {variant} ===")
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
                        "score_rank_published",
                        "score_rank_proposed",
                        "payroll_exact_published",
                        "payroll_exact_proposed",
                    ]
                ].round(4)
            )
            print(programs.round(4))
    (OUT_DIR / "leaderboard_impact.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
