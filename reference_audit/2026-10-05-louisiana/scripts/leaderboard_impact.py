"""Score the frozen run under each option for the two Louisiana state income tax outputs.

Copies the frozen run (predictions, references, scenarios, exclusions) to scratch
directories and never writes the snapshot. Each option is one copy:

``keep``
    Unchanged. It must reproduce the published payload's scoring: every modelStats field
    except the cost and latency fields the freeze overlays, and programStats, heatmap,
    globalWeights and failureModes exactly. The script stops if it does not.
``ldr_published``, ``ldr_official`` and ``hold_2025``
    The two references replaced by their values under that candidate deduction, read from
    ``verification/sweep_la_standard_deduction.csv`` (policyengine-us 2.15.17 with
    ``latest_final`` and the candidate).
``exclude``
    The two outputs appended to the exclusion record, so no model is scored on them.

Each copy is scored with ``python -m policybench.cli analyze``, the command the freeze
runs, and every option is compared with ``keep``.

  PYTHONPATH=<checkout> <policybench venv>/bin/python \\
    reference_audit/2026-10-05-louisiana/scripts/leaderboard_impact.py --scratch <dir>
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
SWEEP = HERE / "verification/sweep_la_standard_deduction.csv"
OUT_DIR = HERE / "verification"
OUTPUTS = (
    ("scenario_051", "state_income_tax_before_refundable_credits"),
    ("scenario_077", "state_income_tax_before_refundable_credits"),
)
REGENERATE = ("ldr_published", "ldr_official", "hold_2025")
OPTIONS = ("keep",) + REGENERATE + ("exclude",)
TOLERANCE = 1.0
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_values() -> dict[str, dict[tuple[str, str], float]]:
    sweep = pd.read_csv(SWEEP).set_index(["scenario_id", "variable"])
    values = {}
    for candidate in ("engine",) + REGENERATE:
        values[candidate] = {key: float(sweep.loc[key, candidate]) for key in OUTPUTS}
    return values


def exclusion_entries(values: dict) -> list[dict]:
    """Draft records, only to score the exclude option; the reason code is a stand-in."""
    entries = []
    for key in OUTPUTS:
        entries.append(
            {
                "scenario_id": key[0],
                "variable": key[1],
                "reason_code": "reference_law_published_after_freeze",
                "root_cause": "c_la_standard_deduction_2026",
                "published": "draft: scoring stand-in, not a record",
                "law": "La. R.S. 47:294(B)",
                "alternative_reading": "draft: scoring stand-in, not a record",
                "frozen_value": values["engine"][key],
                "alternative_value": values["hold_2025"][key],
                "engine_version": "policyengine-us 2.15.17",
                "decided_on": "draft",
                "decided_by": "draft",
            }
        )
    return entries


def stage(target: Path, option: str, values: dict) -> Path:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in RUN_FILES:
        shutil.copy2(RUN / name, target / name)
    if option in REGENERATE:
        # Rewrite only the two rows' value field, so every other byte stays as frozen,
        # and record the new digest in the copy's sidecar, as a regeneration would.
        path = target / "reference_outputs.csv"
        lines = path.read_text().splitlines(keepends=True)
        for (sid, variable), value in values[option].items():
            prefix = f"{sid},{variable},"
            hits = [i for i, line in enumerate(lines) if line.startswith(prefix)]
            if len(hits) != 1:
                raise SystemExit(f"{sid}/{variable}: {len(hits)} reference rows")
            _, _, _, weight = lines[hits[0]].rstrip("\n").split(",")
            lines[hits[0]] = f"{prefix}{value!r},{weight}\n"
        path.write_text("".join(lines))
        sidecar = target / "reference_outputs.csv.meta.json"
        meta = json.loads(sidecar.read_text())
        meta["reference_csv_sha256"] = sha256(path)
        sidecar.write_text(json.dumps(meta, indent=2) + "\n")
    if option == "exclude":
        path = target / "reference_exclusions.json"
        record = json.loads(path.read_text())
        record["exclusions"].extend(exclusion_entries(values))
        path.write_text(json.dumps(record, indent=2) + "\n")
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


def compare(base: dict, option: dict) -> pd.DataFrame:
    a = pd.DataFrame(base["modelStats"]).set_index("model")
    b = pd.DataFrame(option["modelStats"]).set_index("model")
    rows = pd.DataFrame(index=a.index)
    for metric in METRICS:
        rows[f"{metric}_published"] = a[metric]
        rows[f"{metric}_option"] = b[metric]
        rows[f"{metric}_delta"] = b[metric] - a[metric]
    for metric in ("exact", "score"):
        rows[f"{metric}_rank_published"] = ranks(a, metric)
        rows[f"{metric}_rank_option"] = ranks(b, metric)
        rows[f"{metric}_rank_change"] = (
            rows[f"{metric}_rank_published"] - rows[f"{metric}_rank_option"]
        )
    rows["n_published"] = a["n"]
    rows["n_option"] = b["n"]
    return rows.sort_values("exact_rank_published")


def exact_models(values: dict, option: str) -> dict[str, list[str]]:
    """Models within the $1 tolerance of each output's reference under an option."""
    published = json.loads(gzip.decompress((RUN / "data.json.gz").read_bytes()))
    predictions = published["scenarioPredictions"]
    result = {}
    for sid, variable in OUTPUTS:
        if option == "exclude":
            result[f"{sid}/{variable}"] = []
            continue
        reference = values["engine" if option == "keep" else option][(sid, variable)]
        rows = predictions[sid][variable]
        result[f"{sid}/{variable}"] = sorted(
            model
            for model, row in rows.items()
            if row.get("prediction") is not None
            and abs(float(row["prediction"]) - reference) <= TOLERANCE
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", required=True)
    args = parser.parse_args()
    scratch = Path(args.scratch)
    values = candidate_values()

    payloads = {}
    for option in OPTIONS:
        payloads[option] = analyze(stage(scratch / option, option, values))
        if option == "keep":
            check_reproduces_published(payloads["keep"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "outputs": [f"{sid}/{variable}" for sid, variable in OUTPUTS],
        "reference_values": {
            option: (
                None
                if option == "exclude"
                else {
                    f"{sid}/{variable}": values["engine" if option == "keep" else option][
                        (sid, variable)
                    ]
                    for sid, variable in OUTPUTS
                }
            )
            for option in OPTIONS
        },
        "published_reproduced": True,
        "options": {},
    }
    frames = []
    for option in OPTIONS:
        models = compare(payloads["keep"], payloads[option])
        frame = models.copy()
        frame.insert(0, "option", option)
        frames.append(frame.reset_index())
        summary["options"][option] = {
            "scored_outputs": int(payloads[option]["modelStats"][0]["n"]),
            "exact_models": exact_models(values, option),
            "exact_delta_pp": {
                "min": float(models["exact_delta"].min()),
                "max": float(models["exact_delta"].max()),
            },
            "score_delta": {
                "min": float(models["score_delta"].min()),
                "max": float(models["score_delta"].max()),
            },
            "exact_rank_changes": {
                model: {
                    "published": int(row["exact_rank_published"]),
                    "option": int(row["exact_rank_option"]),
                }
                for model, row in models.iterrows()
                if row["exact_rank_change"] != 0
            },
            "score_rank_changes": {
                model: {
                    "published": int(row["score_rank_published"]),
                    "option": int(row["score_rank_option"]),
                }
                for model, row in models.iterrows()
                if row["score_rank_change"] != 0
            },
            "top5_exact": models.sort_values("exact_rank_option").head(5).index.tolist(),
            "top5_score": models.sort_values("score_rank_option").head(5).index.tolist(),
        }
    pd.concat(frames).to_csv(OUT_DIR / "leaderboard_impact_models.csv", index=False)
    (OUT_DIR / "leaderboard_impact.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
