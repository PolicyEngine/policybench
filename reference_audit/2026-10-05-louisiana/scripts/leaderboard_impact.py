"""Score the frozen run under each option for the two Louisiana state income tax outputs.

Reads the pass's inputs from git, never from the working tree: the frozen run
(payload, predictions, references, scenarios, exclusions) as PASS_COMMIT (release
dashboard-data-20260930, #187) holds it, and the sweep's candidate values as
AUDIT_COMMIT (#202, which merged this audit) holds them. Later releases rewrite the
working tree's run: dashboard-data-20261006 (#202) excluded eight more outputs, and
scoring that run would silently regenerate different evidence (1,920 scored outputs
instead of the pass's 1,928). Each input in INPUTS is staged under
``<scratch>/pass_inputs`` and must match its pinned sha256, or the script stops before
scoring anything. The scoring code is the checkout's; the ``keep`` check below stops
the script if that code no longer scores the pinned run as the pinned payload records.

Copies the staged run (predictions, references, scenarios, exclusions) to scratch
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

Its standard output is ``verification/leaderboard_impact.log``. The checkout needs
PASS_COMMIT and AUDIT_COMMIT in its history (a shallow clone needs
``git fetch --unshallow``). ``--out-dir`` writes the verification files elsewhere;
tests/test_reference_audit_pins.py regenerates them that way and requires the
committed ones, and the log, byte for byte.
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
AUDIT_PATH = "reference_audit/2026-10-05-louisiana"
SWEEP_PATH = f"{AUDIT_PATH}/verification/sweep_la_standard_deduction.csv"
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
    SWEEP_PATH: (
        AUDIT_COMMIT,
        "406bceb71581dfe676722740bd588896e2b72ef1baa74b4975d80b1ca851a8e0",
    ),
}
OUTPUTS = (
    ("scenario_051", "state_income_tax_before_refundable_credits"),
    ("scenario_077", "state_income_tax_before_refundable_credits"),
)
REGENERATE = ("ldr_published", "ldr_official", "hold_2025")
OPTIONS = ("keep",) + REGENERATE + ("exclude",)
TOLERANCE = 1.0
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


def candidate_values(path: Path) -> dict[str, dict[tuple[str, str], float]]:
    """Each candidate's two reference values, from the sweep CSV at ``path``."""
    sweep = pd.read_csv(path).set_index(["scenario_id", "variable"])
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


def stage(source: Path, target: Path, option: str, values: dict) -> Path:
    """Copy the staged run at ``source`` to ``target`` and apply ``option``."""
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in RUN_FILES:
        shutil.copy2(source / name, target / name)
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


def exact_models(values: dict, option: str, source: Path) -> dict[str, list[str]]:
    """Models within the $1 tolerance of each output's reference under an option."""
    published = json.loads(gzip.decompress((source / "data.json.gz").read_bytes()))
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
    values = candidate_values(inputs / SWEEP_PATH)

    payloads = {}
    for option in OPTIONS:
        payloads[option] = analyze(stage(source, scratch / option, option, values))
        if option == "keep":
            check_reproduces_published(payloads["keep"], source)

    out_dir.mkdir(parents=True, exist_ok=True)
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
            "exact_models": exact_models(values, option, source),
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
    pd.concat(frames).to_csv(out_dir / "leaderboard_impact_models.csv", index=False)
    (out_dir / "leaderboard_impact.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
