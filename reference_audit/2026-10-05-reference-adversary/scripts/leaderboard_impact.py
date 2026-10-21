"""Score the frozen run as published and under each alternative in proposed_changes.json.

Reads the pass's inputs from git, never from the working tree: the frozen run
(payload, predictions, references, scenarios, exclusions) as commit PASS_COMMIT
(release dashboard-data-20260930, #187) holds it, and proposed_changes.json as
PROPOSALS_COMMIT (#200) holds it. Later releases rewrite the working tree's run
(dashboard-data-20261006, #202, rewrote its payload and exclusions), and scoring
those would regenerate different evidence into this pass's verification files.
Each file is staged under ``<scratch>/pass_inputs`` and must match its pinned
sha256, or the script stops before scoring anything. The scoring code is the
checkout's; ``published`` below stops the script if that code no longer scores
the pinned run as the pinned payload records.

Copies the staged run to scratch directories and never writes the snapshot. Each
copy is scored with ``python -m policybench.cli analyze``, the command the freeze
runs (the method of PolicyEngine/policybench#191 and #194):

``published``
    Unchanged. It must reproduce the published payload's scoring: every modelStats field
    except the cost and latency fields the freeze overlays, and programStats, heatmap,
    globalWeights and failureModes exactly. The script stops if it does not.
``exclude:<cause>``
    That root cause's exclusion records appended to the exclusion record.
``regenerate:<cause>``
    That root cause's regenerated references written into the reference CSV (and the
    copy's sidecar digest updated to match, as a release's sidecar would be).
``recommended``
    Every CONFIRMED root cause regenerated and every AMBIGUOUS one excluded.
``exclude_all``
    Every root cause excluded.

Every variant is measured against ``published``.

  PYTHONPATH=<checkout> <policybench venv>/bin/python \\
    reference_audit/2026-10-05-reference-adversary/scripts/leaderboard_impact.py \\
    --scratch <dir>

The checkout needs PASS_COMMIT and PROPOSALS_COMMIT in its history (a shallow
clone needs ``git fetch --unshallow``). ``--out-dir`` writes the verification
files elsewhere; tests/test_reference_adversary_impact.py regenerates them that
way and requires the committed ones byte for byte.
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
RUN_PATH = (
    "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
RUN_SHA256 = {
    "data.json.gz": "1e029aaa87d1dfbd2ceee88419599a919dd7c9d4aba78a308ec48d008d54ae18",
    "predictions.csv.gz": (
        "ca2c4c48c7fd3e680c9c61a7380ecfcb60ce95f913c5c363762e023949d8ad12"
    ),
    "reference_outputs.csv": (
        "e8bbba8fd3e90f78e7c0e83df06227bc1c94563e92f7405fe12be853a30b2466"
    ),
    "reference_outputs.csv.meta.json": (
        "816fef53c452d8520a321bc12bc29b28da1e7956a06818e5ec13d7fc7b371a4b"
    ),
    "reference_exclusions.json": (
        "bf4e6a249aeee01d0b71f5834ef7a35c4bab2266d2c59d0e81b12a0da44281c2"
    ),
    "scenarios.csv": "71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a",
    "scenarios.csv.meta.json": (
        "03a66e90b86e9bd0cc77f27520784bd581777762f749675dc716e24c1b8eaebb"
    ),
}
PROPOSALS_COMMIT = "4db91b5f10581947f60a07f899e0ec2867b0405e"
PROPOSALS_PATH = "reference_audit/2026-10-05-reference-adversary/proposed_changes.json"
PROPOSALS_SHA256 = "3a6e5920a2d02e94e1df52c95c1def2739f3eb21b1fb67fc74a7d68219a749bf"
PROPOSALS_NAME = Path(PROPOSALS_PATH).name
# Copied into each variant and scored; data.json.gz is only compared against.
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
    """Stage the pass's run bundle under ``target/run`` and its proposals beside it."""
    if target.exists():
        shutil.rmtree(target)
    for name, pinned in RUN_SHA256.items():
        git_input(PASS_COMMIT, f"{RUN_PATH}/{name}", pinned, target / "run" / name)
    git_input(
        PROPOSALS_COMMIT, PROPOSALS_PATH, PROPOSALS_SHA256, target / PROPOSALS_NAME
    )
    return target


def proposals(path: Path) -> dict:
    return json.loads(path.read_text())["root_causes"]


def variants(path: Path) -> dict[str, dict[str, list[dict]]]:
    """Each variant's exclusion and regeneration records, from ``path``'s proposals."""
    causes = proposals(path)
    plan: dict[str, dict[str, list[dict]]] = {}
    for cause, spec in causes.items():
        plan[f"exclude:{cause}"] = {"exclude": spec["exclusions"], "regenerate": []}
        if spec["regenerations"]:
            plan[f"regenerate:{cause}"] = {
                "exclude": [],
                "regenerate": spec["regenerations"],
            }
    plan["recommended"] = {
        "exclude": [
            record
            for spec in causes.values()
            if spec["verdict"] != "CONFIRMED"
            for record in spec["exclusions"]
        ],
        "regenerate": [
            record
            for spec in causes.values()
            if spec["verdict"] == "CONFIRMED"
            for record in spec["regenerations"]
        ],
    }
    plan["exclude_all"] = {
        "exclude": [r for spec in causes.values() for r in spec["exclusions"]],
        "regenerate": [],
    }
    return plan


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


def stage(source: Path, target: Path, records: dict[str, list[dict]] | None) -> Path:
    """Copy the staged run at ``source`` to ``target`` and apply ``records``."""
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in RUN_FILES:
        shutil.copy2(source / name, target / name)
    if not records:
        return target
    if records["exclude"]:
        record = json.loads((target / "reference_exclusions.json").read_text())
        record["exclusions"].extend(records["exclude"])
        (target / "reference_exclusions.json").write_text(
            json.dumps(record, indent=2) + "\n"
        )
    changes = records["regenerate"]
    if changes:
        reference = pd.read_csv(target / "reference_outputs.csv", dtype={"value": str})
        index = reference.set_index(["scenario_id", "variable"]).index
        for change in changes:
            key = (change["scenario_id"], change["variable"])
            row = index.get_loc(key)
            if abs(float(reference.at[row, "value"]) - change["frozen_value"]) > 1e-9:
                raise SystemExit(f"{key}: frozen value differs from the reference CSV")
            reference.at[row, "value"] = repr(float(change["regenerated_value"]))
        reference.to_csv(target / "reference_outputs.csv", index=False)
        before = (source / "reference_outputs.csv").read_text().splitlines()
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


def cell_exact(payload: dict, cells: list[tuple[str, str]]) -> dict[str, dict]:
    """Per changed cell: whether it is scored and how many models are exact on it."""
    out = {}
    for scenario_id, variable in cells:
        models = payload["scenarioPredictions"][scenario_id][variable]
        scored = {cell["scored"] for cell in models.values()}
        out[f"{scenario_id}/{variable}"] = {
            "scored": scored == {True},
            "reference": next(iter(models.values()))["groundTruth"],
            "exact_models": sum(int(cell["exact"] == 100.0) for cell in models.values()),
        }
    return out


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
    base: dict,
    other: dict,
    zero: dict,
    cells: list[tuple[str, str]],
) -> dict:
    leader = models.sort_values("exact_rank_proposed").index[0]
    return {
        "changed_outputs": [f"{s}/{v}" for s, v in cells],
        "cells_published": cell_exact(base, cells),
        "cells_proposed": cell_exact(other, cells),
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
        "leader": {
            "model": leader,
            "exact_published": float(models.loc[leader, "exact_published"]),
            "exact_proposed": float(models.loc[leader, "exact_proposed"]),
        },
        "top5_exact_published": models.sort_values("exact_rank_published")
        .head(5)
        .index.tolist(),
        "top5_exact_proposed": models.sort_values("exact_rank_proposed")
        .head(5)
        .index.tolist(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", required=True)
    parser.add_argument(
        "--only", nargs="*", help="score only these variants (default: all)"
    )
    parser.add_argument(
        "--out-dir",
        default=str(OUT_DIR),
        help="where to write the verification files (default: %(default)s)",
    )
    args = parser.parse_args()
    scratch = Path(args.scratch).resolve()
    out_dir = Path(args.out_dir)
    # stage() and pass_inputs() delete and rewrite scratch/<name>; never inside
    # the repository.
    if scratch == ROOT.resolve() or scratch.is_relative_to(ROOT.resolve()):
        parser.error(f"--scratch must be outside the repository ({ROOT})")
    inputs = pass_inputs(scratch / "pass_inputs")
    source = inputs / "run"
    plan = variants(inputs / PROPOSALS_NAME)
    unknown = sorted(set(args.only or ()) - set(plan))
    if unknown:
        parser.error(f"unknown variant(s) {unknown}; choose from {sorted(plan)}")

    base_dir = stage(source, scratch / "published", None)
    base = analyze(base_dir)
    check_reproduces_published(base, source)
    zero_published = always_zero(base_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {"published_reproduced": True, "proposals": PROPOSALS_NAME}
    if args.only:
        plan = {name: plan[name] for name in args.only}
    for name, records in plan.items():
        run_dir = stage(source, scratch / name.replace(":", "__"), records)
        other = analyze(run_dir)
        models = compare(base, other)
        programs = program_rows(base, other)
        zero = {"published": zero_published, "proposed": always_zero(run_dir)}
        cells = sorted(
            {
                (r["scenario_id"], r["variable"])
                for r in records["exclude"] + records["regenerate"]
            }
        )
        slug = name.replace(":", "_")
        models.to_csv(out_dir / f"leaderboard_impact_{slug}_models.csv")
        programs.to_csv(out_dir / f"leaderboard_impact_{slug}_programs.csv")
        summary[name] = summarize(models, base, other, zero, cells)
        summary[name]["programs"] = programs.round(6).to_dict(orient="index")
        with pd.option_context("display.width", 250, "display.max_rows", 100):
            print(f"\n=== {name} ===")
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
                    ]
                ].round(4)
            )
            print(programs.round(4))
    (out_dir / "leaderboard_impact.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "proposals"}, indent=2)[:4000])


if __name__ == "__main__":
    main()
