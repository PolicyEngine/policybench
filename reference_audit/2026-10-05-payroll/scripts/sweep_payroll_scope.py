"""Recompute every PolicyBench reference with and without the payroll output-scope adapter.

The reference system is the one that built the published references: policyengine-us
2.15.17 plus ``latest_final`` (the nine pre-freeze-law conventions and the Maryland
output-scope adapter), on households built by ``Scenario.to_pe_household``. The script
recomputes every output under it and checks the result against the published reference
CSV. It then recomputes every output under ``latest_final`` plus
``fixes/payroll_mandatory_scope.py``, which drops the employee shares an employer may but
need not deduct from ``employee_state_payroll_tax``, and lists every output that moves.

Any output other than payroll_tax that reads employee payroll tax (for example through
``spm_unit_paycheck_withholdings`` or ``household_tax_before_refundable_credits``) would
move too, so the sweep covers all 1,984 outputs, not only payroll_tax.

  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=<checkout> \\
    <triage>/.venv-pe21517/bin/python \\
    reference_audit/2026-10-05-payroll/scripts/sweep_payroll_scope.py \\
      --out-dir reference_audit/2026-10-05-payroll/verification
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import version
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
AUDIT_0928 = ROOT / "reference_audit/2026-09-28"
AUDIT_0922 = ROOT / "reference_audit/2026-09-22"
ADAPTER = HERE / "fixes/payroll_mandatory_scope.py"
YEAR = 2026
BINARY_SUFFIXES = ("_eligible",)
TOLERANCE = 1.0
# sweep.py's rename for the 1.755.4 harness; sweep_latest.py kept it on 2.15.17.
RENAME = {"partnership_se_income": "partnership_self_employment_net_earnings"}

_SYSTEMS: dict[str, object] = {}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _fix_dir() -> Path:
    """latest_final and its parts, plus the sales tax table the IRS module reads."""
    target = Path(tempfile.mkdtemp(prefix="payroll_scope_fixes_"))
    for path in (AUDIT_0928 / "fixes").glob("*.py"):
        shutil.copy2(path, target / path.name)
    shutil.copy2(AUDIT_0922 / "fixes/r19_irs_sales_tax_2025.json", target)
    return target


def _system(name: str):
    if name not in _SYSTEMS:
        from policyengine_core.reforms import Reform
        from policyengine_us import CountryTaxBenefitSystem

        final = _load(_fix_dir() / "latest_final.py", "latest_final").reform
        if name == "final":
            _SYSTEMS[name] = CountryTaxBenefitSystem(reform=final)
        else:
            adapter = _load(ADAPTER, "payroll_mandatory_scope").reform

            class combined(Reform):
                def apply(self):
                    final.apply(self)
                    adapter.apply(self)

            _SYSTEMS[name] = CountryTaxBenefitSystem(reform=combined)
    return _SYSTEMS[name]


def build_situation(scenario) -> dict:
    situation = scenario.to_pe_household()
    for person in situation["people"].values():
        for old, new in RENAME.items():
            if old in person:
                person[new] = person.pop(old)
    return situation


def _outputs(sim, scenario, variables) -> dict[str, float]:
    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output

    values = {}
    for variable in variables:
        pe_variable = _pe_variable_for_output(variable, "us")
        values[variable] = float(
            _extract_person_value(sim.calculate(pe_variable, YEAR), scenario, variable)
        )
    return values


def sweep_scenario(args: tuple[str, list[str]]) -> dict:
    from policyengine_us import Simulation

    from policybench.scenarios import scenario_from_dict

    scenario_json, variables = args
    scenario = scenario_from_dict(json.loads(scenario_json))
    situation = build_situation(scenario)
    result = {"scenario_id": scenario.id, "state": scenario.state}
    for name in ("final", "scoped"):
        sim = Simulation(tax_benefit_system=_system(name), situation=situation)
        result[name] = _outputs(sim, scenario, variables)
        result[f"{name}_state_payroll"] = float(
            sim.calculate("employee_state_payroll_tax", YEAR).sum()
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    from policybench.scenarios import scenario_from_dict
    from policybench.spec import expand_programs_for_scenario

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = json.loads((RUN / "reference_outputs.csv.meta.json").read_text())
    reference = pd.read_csv(RUN / "reference_outputs.csv")
    indexed = reference.set_index(["scenario_id", "variable"])["value"]
    exclusions = json.loads((RUN / "reference_exclusions.json").read_text())[
        "exclusions"
    ]
    excluded = {(e["scenario_id"], e["variable"]): e for e in exclusions}
    scenarios = pd.read_csv(RUN / "scenarios.csv")

    jobs = []
    for _, row in scenarios.iterrows():
        scenario = scenario_from_dict(json.loads(row["scenario_json"]))
        variables = [
            v
            for v in expand_programs_for_scenario(meta["programs"], scenario)
            if (scenario.id, v) in indexed.index
        ]
        jobs.append((row["scenario_json"], variables))

    engine = version("policyengine-us")
    print(f"policyengine-us {engine}; {len(jobs)} households", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(sweep_scenario, jobs))
    results.sort(key=lambda r: r["scenario_id"])

    rows = []
    for result in results:
        sid = result["scenario_id"]
        for variable, base in result["final"].items():
            key = (sid, variable)
            ref = float(indexed[key])
            scoped = result["scoped"][variable]
            entry = excluded.get(key)
            binary = variable.endswith(BINARY_SUFFIXES)
            rows.append(
                {
                    "scenario_id": sid,
                    "state": result["state"],
                    "variable": variable,
                    "reference": ref,
                    "final": base,
                    "final_matches_reference": (
                        round(base) == round(ref) if binary else abs(base - ref) <= 1e-3
                    ),
                    "scoped": scoped,
                    "delta": scoped - base,
                    "moved_any": scoped != base,
                    "moved_over_tolerance": (
                        round(scoped) != round(base)
                        if binary
                        else abs(scoped - base) > TOLERANCE
                    ),
                    "excluded": entry is not None,
                    "excluded_reason": entry["reason_code"] if entry else "",
                }
            )
    table = pd.DataFrame(rows)
    table.to_csv(out_dir / "sweep_payroll_scope.csv", index=False)
    households = {
        r["scenario_id"]: {
            "state": r["state"],
            "employee_state_payroll_tax_final": r["final_state_payroll"],
            "employee_state_payroll_tax_scoped": r["scoped_state_payroll"],
        }
        for r in results
    }
    (out_dir / "sweep_payroll_scope_households.json").write_text(
        json.dumps(
            {
                "policyengine_us": engine,
                "adapter_sha256": hashlib.sha256(ADAPTER.read_bytes()).hexdigest(),
                "households": households,
            },
            indent=1,
            sort_keys=True,
        )
        + "\n"
    )

    scored = table[~table["excluded"]]
    mismatched = table[~table["final_matches_reference"]]
    # Excluded outputs decided before the 2.15.17 upgrade keep their decided values; the
    # sidecar's engine_upgrade revision lists each one's 2.15.17 value.
    rechecked = {
        (item["scenario_id"], item["variable"]): item["value_on_2_15_17"]
        for revision in meta["revisions"]
        for item in revision.get("excluded_outputs_rechecked", [])
    }
    unexplained = [
        (row.scenario_id, row.variable)
        for row in mismatched.itertuples()
        if not row.excluded
        or abs(rechecked.get((row.scenario_id, row.variable), float("nan")) - row.final)
        > 1e-3
    ]
    print(
        f"baseline: {len(table)} outputs, {len(scored)} scored; "
        f"{int((~mismatched['excluded']).sum())} scored outputs differ from the "
        f"published reference; {int(mismatched['excluded'].sum())} excluded outputs "
        f"keep their decided values ({len(rechecked)} rechecked in the sidecar); "
        f"unexplained differences: {unexplained}"
    )
    if unexplained:
        raise SystemExit("the baseline does not reproduce the published references")
    moved = table[table["moved_any"]]
    print(
        f"\nadapter: {len(moved)} outputs move at all, "
        f"{int(table['moved_over_tolerance'].sum())} by more than ${TOLERANCE:.0f} "
        f"({int((table['moved_over_tolerance'] & ~table['excluded']).sum())} scored)"
    )
    with pd.option_context("display.width", 220, "display.max_rows", 500):
        print(
            moved[
                [
                    "scenario_id",
                    "state",
                    "variable",
                    "reference",
                    "final",
                    "scoped",
                    "delta",
                    "excluded",
                ]
            ].to_string(index=False)
        )


if __name__ == "__main__":
    main()
