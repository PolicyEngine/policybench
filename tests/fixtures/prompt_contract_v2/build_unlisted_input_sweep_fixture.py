"""Rebuild unlisted_input_sweep_20261005.json from the recorded sweep runs.

The fixture vendors the moves that PR #196's unlisted-input sweep recorded on the
frozen run, plus the four payroll moves from PR #194's scope sweep, so the v2
required-facts report runs without the engine. The run directory lives on the
build machine (``results/local`` is not committed); pass it explicitly:

    python tests/fixtures/prompt_contract_v2/build_unlisted_input_sweep_fixture.py \
        --run-dir results/local/unlisted_input_sweep_20261005/final_run \
        --payroll-sweep <checkout of #194>/reference_audit/2026-10-05-payroll/\
verification/sweep_payroll_scope.csv

Re-record after #196 merges: the 2026-10-05 run predates its head (44850656),
which adds Part B's ``not_enrolled`` reading.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "unlisted_input_sweep_20261005.json"
MOVE_FIELDS = (
    "scenario_id",
    "state",
    "variable",
    "estimate",
    "reading",
    "kind",
    "variant",
    "status",
)
# #194's optional employer pass-through has no engine input, so #196 does not
# register it yet ("Once d972 is ruled, register #194's ... as an estimate").
PAYROLL_ESTIMATE = {
    "id": "state_paid_leave_employee_share",
    "entity": "person",
    "engine_inputs": [],
    "readings": [{"id": "mandatory_scope", "kind": "alternative"}],
    "found_in": "reference_audit 2026-10-05-payroll (PR #194, d972)",
    "why_unlisted": (
        "No prompt states whether the employer deducts the employee share of a "
        "state paid-leave or disability premium that the law lets it deduct but "
        "does not require; the engine counts the largest permitted share."
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _amount(text: str) -> float:
    # Preserve the recorded engine values: rounding can hide a >$1 movement.
    return float(text)


def build(run_dir: Path, payroll_sweep: Path) -> dict:
    summary = json.loads((run_dir / "summary.json").read_text())
    run = summary["run"]
    parts = {}
    with (run_dir / "readings.csv").open() as handle:
        for row in csv.DictReader(handle):
            if row["estimate"] == "all_literal_readings" and row["detail"]:
                detail = json.loads(row["detail"])
                parts[row["scenario_id"]] = sorted(
                    part.split("/")[0] for part in detail.get("parts", [])
                )
    moves = []
    with (run_dir / "moves.csv").open() as handle:
        for row in csv.DictReader(handle):
            move = {field: row[field] for field in MOVE_FIELDS}
            move["reference"] = _amount(row["reference"])
            move["baseline"] = _amount(row["baseline"])
            move["value"] = _amount(row["value"])
            move["override"] = row["override"]
            if row["estimate"] == "all_literal_readings":
                move["parts"] = parts[row["scenario_id"]]
            moves.append(move)
    with payroll_sweep.open() as handle:
        for row in csv.DictReader(handle):
            if row["moved_over_tolerance"] != "True":
                continue
            moves.append(
                {
                    "scenario_id": row["scenario_id"],
                    "state": row["state"],
                    "variable": row["variable"],
                    "estimate": PAYROLL_ESTIMATE["id"],
                    "reading": "mandatory_scope",
                    "kind": "alternative",
                    "variant": "",
                    "status": "excluded_same_input"
                    if row["excluded"] == "True"
                    else "scored",
                    "reference": _amount(row["reference"]),
                    "baseline": _amount(row["final"]),
                    "override": "employer.state_paid_leave_employee_share=False",
                    "value": _amount(row["scoped"]),
                }
            )
    moves.sort(
        key=lambda m: (
            m["scenario_id"],
            m["variable"],
            m["estimate"],
            m["reading"],
            m["variant"],
        )
    )
    estimates = [
        {
            "id": estimate["id"],
            "entity": estimate["entity"],
            "engine_inputs": estimate["engine_inputs"],
            "readings": [
                {"id": reading["id"], "kind": reading["kind"]}
                for reading in estimate["readings"]
            ],
            "found_in": estimate["found_in"],
            "why_unlisted": estimate["why_unlisted"],
        }
        for estimate in summary["estimates"]
    ]
    estimates.append(PAYROLL_ESTIMATE)
    baselines = {}
    with (run_dir / "baseline.csv").open() as handle:
        for row in csv.DictReader(handle):
            baselines.setdefault(row["scenario_id"], {})[row["variable"]] = _amount(
                row["baseline"]
            )
    return {
        "schema_version": 1,
        "description": (
            "Reference moves recorded by the unlisted-input sweeps of 2026-10-05 on "
            "the frozen US run: every output whose reference moves by more than "
            "$1 (or flips) when an engine estimate of an unlisted input takes the "
            "prompt's literal reading or a documented alternative. Read by "
            "tests/test_prompt_contract_v2_required_facts.py; rebuilt by "
            "build_unlisted_input_sweep_fixture.py."
        ),
        "sources": {
            "comparison_logic": {
                "pull_request": 196,
                "commit": "4485065643fd7ace5a46cfeff740c1b9f3170ad2",
                "unlisted_input_sweep_py_sha256": (
                    "7847d76347476e8d8ced79cb009d8b434eeb6607d01fd507dbd543a5c2a2892b"
                ),
                "output_scope_py_sha256": (
                    "8442a244bd5463b07ae2b02d16f0178ee1ad533b4e203500e51c6b8d1bcd9b10"
                ),
            },
            "unlisted_input_sweep": {
                "pull_request": 196,
                "branch": "unlisted-input-sweep",
                "run_dir": "results/local/unlisted_input_sweep_20261005/final_run "
                "(build machine; not committed)",
                "moves_csv_sha256": _sha256(run_dir / "moves.csv"),
                "baseline_csv_sha256": _sha256(run_dir / "baseline.csv"),
                "readings_csv_sha256": _sha256(run_dir / "readings.csv"),
                "summary_json_sha256": _sha256(run_dir / "summary.json"),
                "generated_at_utc": run["generated_at_utc"],
                "policyengine_us": run["policyengine_us"],
                "policyengine_core": run["policyengine_core"],
                "fix": run["fix"],
                "output_scope_adapter": run["output_scope_adapter"],
                "scenarios": run["scenarios"],
                "scenarios_sha256": run["scenarios_sha256"],
                "reference_sha256": run["reference_sha256"],
                "exclusions_sha256": run["exclusions_sha256"],
                "tolerance": run["tolerance"],
                "outputs": summary["outputs"],
                "scored_outputs": summary["scored_outputs"],
                "simulations": summary["simulations"],
                "note": "Recorded before #196's head 44850656, which adds Part B's "
                "not_enrolled reading; re-record after #196 merges.",
            },
            "payroll_scope_sweep": {
                "pull_request": 194,
                "branch": "payroll-state-components-20261005",
                "file": "reference_audit/2026-10-05-payroll/verification/"
                "sweep_payroll_scope.csv",
                "sha256": _sha256(payroll_sweep),
                "reading": "payroll_mandatory_scope leaves the optional employer "
                "pass-through shares out of employee state payroll tax",
            },
        },
        "estimates": estimates,
        "baselines": baselines,
        "moves": moves,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--payroll-sweep", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    fixture = build(args.run_dir, args.payroll_sweep)
    args.out.write_text(json.dumps(fixture, indent=1, sort_keys=False) + "\n")
    print(f"wrote {args.out}: {len(fixture['moves'])} moves")


if __name__ == "__main__":
    main()
