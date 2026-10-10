"""Score the frozen run with and without the proposed exclusions, through the analyze CLI.

Reads the pass's inputs from git, never from the working tree: the frozen run
(payload, predictions, references, scenarios, exclusions) as PASS_COMMIT (release
dashboard-data-20260930, #187) holds it, and proposed_exclusions.json as AUDIT_COMMIT
(#202, which merged this audit) holds it. Later releases rewrite the working tree's
run: dashboard-data-20261006 (#202) installed all three of these records, so a copy
of today's run with them appended carries duplicate exclusions, which the analyze CLI
refuses. Each input in INPUTS is staged under ``<scratch>/pass_inputs`` and must
match its pinned sha256, or the script stops before scoring anything. The scoring
code is the checkout's; the check below stops the script if that code no longer
scores the pinned run as the pinned payload records.

Copies the staged run (predictions, references, scenarios, exclusions) to two scratch
directories and never writes the snapshot. In one copy the exclusion record is
unchanged; in the other the proposed records (proposed_exclusions.json) are appended.
Each copy is scored with ``python -m policybench.cli analyze``, the command the freeze
runs, and the dashboard payloads are compared.

The unchanged copy must reproduce the published payload's scoring: every modelStats
field except the cost and latency fields the freeze overlays, and programStats,
heatmap, globalWeights and failureModes exactly. The script stops if it does not.

  PYTHONPATH=<checkout> <policybench venv>/bin/python \\
    reference_audit/2026-10-05/scripts/leaderboard_impact.py --scratch <dir>

The checkout needs PASS_COMMIT and AUDIT_COMMIT in its history (a shallow clone needs
``git fetch --unshallow``). ``--out-dir`` writes the verification files elsewhere;
tests/test_reference_audit_pins.py regenerates them that way and requires the
committed ones byte for byte.
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
OUT_DIR = HERE / "verification"
# The pass's inputs, pinned by commit and sha256.
PASS_COMMIT = "8b4c0ca146bb6f66deba6ce24009d49d70d92df2"
AUDIT_COMMIT = "9ce4ade8382962a9134860c23f56d92509b5e57f"
RUN_PATH = (
    "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
AUDIT_PATH = "reference_audit/2026-10-05"
PROPOSED_PATH = f"{AUDIT_PATH}/proposed_exclusions.json"
# Every file the script reads from the repository: path -> (commit, sha256).
# pass_inputs() stages each at the same path under its target.
INPUTS = {
    f"{RUN_PATH}/data.json.gz": (
        PASS_COMMIT,
        "1e029aaa87d1dfbd2ceee88419599a919dd7c9d4aba78a308ec48d008d54ae18",
    ),
    f"{RUN_PATH}/predictions.csv.gz": (
        PASS_COMMIT,
        "ca2c4c48c7fd3e680c9c61a7380ecfcb60ce95f913c5c363762e023949d8ad12",
    ),
    f"{RUN_PATH}/reference_outputs.csv": (
        PASS_COMMIT,
        "e8bbba8fd3e90f78e7c0e83df06227bc1c94563e92f7405fe12be853a30b2466",
    ),
    f"{RUN_PATH}/reference_outputs.csv.meta.json": (
        PASS_COMMIT,
        "816fef53c452d8520a321bc12bc29b28da1e7956a06818e5ec13d7fc7b371a4b",
    ),
    f"{RUN_PATH}/reference_exclusions.json": (
        PASS_COMMIT,
        "bf4e6a249aeee01d0b71f5834ef7a35c4bab2266d2c59d0e81b12a0da44281c2",
    ),
    f"{RUN_PATH}/scenarios.csv": (
        PASS_COMMIT,
        "71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a",
    ),
    f"{RUN_PATH}/scenarios.csv.meta.json": (
        PASS_COMMIT,
        "03a66e90b86e9bd0cc77f27520784bd581777762f749675dc716e24c1b8eaebb",
    ),
    PROPOSED_PATH: (
        AUDIT_COMMIT,
        "3c330177762c46fa5c52b02f9f943e9d5a65e15855280b64e9b462ab27413272",
    ),
}
# Copied into each copy and scored; data.json.gz is only compared against.
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


def git_input(commit: str, path: str, pinned: str, target: Path) -> Path:
    """Write ``path`` as ``commit`` holds it to ``target``, refusing any other bytes."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{path}"],
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit(
            f"cannot read {path} at {commit[:12]}; fetch full history "
            f"(git fetch --unshallow): {result.stderr.decode().strip()}"
        )
    digest = hashlib.sha256(result.stdout).hexdigest()
    if digest != pinned:
        raise SystemExit(
            f"{commit[:12]}:{path} has sha256 {digest}, not the pinned {pinned}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(result.stdout)
    return target


def pass_inputs(target: Path) -> Path:
    """Stage every input in INPUTS at its repository path under ``target``."""
    if target.exists():
        shutil.rmtree(target)
    for path, (commit, pinned) in INPUTS.items():
        git_input(commit, path, pinned, target / path)
    return target


def stage(source: Path, target: Path, extra: list[dict] | None) -> Path:
    """Copy the staged run at ``source`` to ``target`` and append ``extra``."""
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in RUN_FILES:
        shutil.copy2(source / name, target / name)
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


def check_reproduces_published(base: dict, source: Path) -> None:
    """Stop unless ``base`` scores as the staged ``source/data.json.gz`` does."""
    published = json.loads(gzip.decompress((source / "data.json.gz").read_bytes()))
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
    parser.add_argument(
        "--out-dir",
        default=str(OUT_DIR),
        help="where to write the verification files (default: %(default)s)",
    )
    args = parser.parse_args()
    scratch = Path(args.scratch).resolve()
    out_dir = Path(args.out_dir)
    # stage() and pass_inputs() delete and rewrite scratch/<name>, so scratch and
    # the repository must not overlap: neither may lie inside the other.
    root = ROOT.resolve()
    if scratch.is_relative_to(root) or root.is_relative_to(scratch):
        parser.error(f"--scratch must not overlap the repository ({ROOT})")
    inputs = pass_inputs(scratch / "pass_inputs")
    source = inputs / RUN_PATH
    proposals = json.loads((inputs / PROPOSED_PATH).read_text())["exclusions"]

    base = analyze(stage(source, scratch / "base", None))
    check_reproduces_published(base, source)
    proposed = analyze(stage(source, scratch / "proposed", proposals))

    models = compare(base, proposed)
    zero = {
        "published": always_zero(scratch / "base"),
        "proposed": always_zero(scratch / "proposed"),
    }
    leader = models.sort_values("exact_rank_proposed").index[0]
    programs = program_rows(base, proposed)
    out_dir.mkdir(parents=True, exist_ok=True)
    models.to_csv(out_dir / "leaderboard_impact_models.csv")
    programs.to_csv(out_dir / "leaderboard_impact_programs.csv")
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
    (out_dir / "leaderboard_impact.json").write_text(
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
