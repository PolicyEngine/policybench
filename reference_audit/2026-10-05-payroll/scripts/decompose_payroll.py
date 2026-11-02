"""Split every PolicyBench payroll_tax reference into its federal and state parts.

The payroll_tax output is ``spm_unit_payroll_tax``, which sums ``employee_payroll_tax``
over the SPM unit's tax units. In policyengine-us 2.15.17 that adds employee Social
Security tax, employee Medicare tax, Additional Medicare Tax and
``employee_state_payroll_tax`` (variables/gov/irs/tax/payroll/employee_payroll_tax.py).
The state part adds one ``<st>_employee_state_payroll_tax`` aggregate per state, each of
which adds that state's program contributions
(variables/gov/states/tax/payroll/employee_state_payroll_tax.py).

The script rebuilds every household with ``Scenario.to_pe_household`` on the system that
built the published references (policyengine-us 2.15.17 plus ``latest_final``), checks
that ``spm_unit_payroll_tax`` reproduces every published payroll_tax reference, and
records each household's federal and per-program state contributions.

  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=<checkout> \\
    <triage>/.venv-pe21517/bin/python \\
    reference_audit/2026-10-05-payroll/scripts/decompose_payroll.py \\
      --out-dir reference_audit/2026-10-05-payroll/verification
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import version
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
AUDIT_0928 = ROOT / "reference_audit/2026-09-28"
AUDIT_0922 = ROOT / "reference_audit/2026-09-22"
YEAR = 2026
OUTPUT = "payroll_tax"
# sweep.py's rename for the 1.755.4 harness; sweep_latest.py kept it on 2.15.17.
RENAME = {"partnership_se_income": "partnership_self_employment_net_earnings"}
FEDERAL = (
    "employee_social_security_tax",
    "employee_medicare_tax",
    "additional_medicare_tax",
)
# Leaf programs under each <st>_employee_state_payroll_tax in policyengine-us 2.15.17.
STATE_PROGRAMS = {
    "CA": ("ca_employee_state_disability_insurance_contribution",),
    "CO": ("co_employee_famli_contribution",),
    "CT": ("ct_employee_paid_leave_contribution",),
    "DE": ("de_employee_paid_leave_contribution",),
    "MA": ("ma_employee_paid_leave_contribution",),
    "ME": ("me_employee_paid_leave_contribution",),
    "MN": ("mn_employee_paid_leave_contribution",),
    "NJ": (
        "nj_employee_temporary_disability_insurance_contribution",
        "nj_employee_family_leave_insurance_contribution",
    ),
    "NY": (
        "ny_employee_paid_family_leave_contribution",
        "ny_employee_disability_benefits_contribution",
    ),
    "OR": (
        "or_employee_paid_leave_contribution",
        "or_employee_statewide_transit_tax",
    ),
    "PA": ("pa_employee_unemployment_compensation_contribution",),
    "RI": ("ri_employee_temporary_disability_insurance_contribution",),
    "VT": ("vt_employee_child_care_contribution",),
    "WA": (
        "wa_employee_paid_leave_contribution",
        "wa_employee_long_term_care_contribution",
    ),
}
LEAVES = tuple(v for programs in STATE_PROGRAMS.values() for v in programs)

_SYSTEM = None


def _assemble_fixes() -> Path:
    """latest_final and its parts, plus the sales tax table the IRS module reads."""
    target = Path(tempfile.mkdtemp(prefix="payroll_fixes_"))
    for path in (AUDIT_0928 / "fixes").glob("*.py"):
        shutil.copy2(path, target / path.name)
    shutil.copy2(AUDIT_0922 / "fixes/r19_irs_sales_tax_2025.json", target)
    return target


def _system():
    global _SYSTEM
    if _SYSTEM is None:
        from policyengine_us import CountryTaxBenefitSystem

        fix_dir = _assemble_fixes()
        path = fix_dir / "latest_final.py"
        spec = importlib.util.spec_from_file_location("latest_final", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["latest_final"] = module
        spec.loader.exec_module(module)
        _SYSTEM = CountryTaxBenefitSystem(reform=module.reform)
    return _SYSTEM


def build_situation(scenario) -> dict:
    situation = scenario.to_pe_household()
    for person in situation["people"].values():
        for old, new in RENAME.items():
            if old in person:
                person[new] = person.pop(old)
    return situation


def decompose(scenario_json: str) -> dict:
    from policyengine_us import Simulation

    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output
    from policybench.scenarios import scenario_from_dict

    scenario = scenario_from_dict(json.loads(scenario_json))
    sim = Simulation(tax_benefit_system=_system(), situation=build_situation(scenario))
    pe_variable = _pe_variable_for_output(OUTPUT, "us")
    total = float(
        _extract_person_value(sim.calculate(pe_variable, YEAR), scenario, OUTPUT)
    )
    parts = {name: float(sim.calculate(name, YEAR).sum()) for name in FEDERAL}
    parts["employee_state_payroll_tax"] = float(
        sim.calculate("employee_state_payroll_tax", YEAR).sum()
    )
    leaves = {name: float(sim.calculate(name, YEAR).sum()) for name in LEAVES}
    people = []
    for person_id, person in build_situation(scenario)["people"].items():
        people.append(person_id)
    wages = [float(x) for x in sim.calculate("employment_income", YEAR)]
    return {
        "scenario_id": scenario.id,
        "state": scenario.state,
        "payroll_tax": total,
        "parts": parts,
        "state_leaves": {k: v for k, v in leaves.items() if v != 0.0},
        "employment_income": wages,
        "people": people,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reference = pd.read_csv(RUN / "reference_outputs.csv")
    payroll = reference[reference["variable"] == OUTPUT].set_index("scenario_id")
    exclusions = json.loads((RUN / "reference_exclusions.json").read_text())[
        "exclusions"
    ]
    excluded = {e["scenario_id"]: e for e in exclusions if e["variable"] == OUTPUT}
    scenarios = pd.read_csv(RUN / "scenarios.csv")
    scenarios = scenarios[scenarios["scenario_id"].isin(payroll.index)]

    engine = version("policyengine-us")
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(decompose, scenarios["scenario_json"].tolist()))
    results.sort(key=lambda r: r["scenario_id"])

    rows = []
    for r in results:
        sid = r["scenario_id"]
        ref = float(payroll.loc[sid, "value"])
        federal = sum(r["parts"][name] for name in FEDERAL)
        state = r["parts"]["employee_state_payroll_tax"]
        rows.append(
            {
                "scenario_id": sid,
                "state": r["state"],
                "reference": ref,
                "recomputed": r["payroll_tax"],
                "matches_reference": abs(r["payroll_tax"] - ref) <= 1e-3,
                **{name: r["parts"][name] for name in FEDERAL},
                "federal_total": federal,
                "employee_state_payroll_tax": state,
                "parts_add_up": abs(federal + state - r["payroll_tax"]) <= 1e-3,
                "state_programs": ";".join(
                    f"{k}={v:.2f}" for k, v in sorted(r["state_leaves"].items())
                ),
                "leaves_add_up": abs(sum(r["state_leaves"].values()) - state) <= 1e-3,
                "excluded": sid in excluded,
                "excluded_reason": excluded[sid]["reason_code"]
                if sid in excluded
                else "",
                "household_wages": sum(r["employment_income"]),
            }
        )
    table = pd.DataFrame(rows)
    table.to_csv(out_dir / "payroll_decomposition.csv", index=False)
    (out_dir / "payroll_decomposition.json").write_text(
        json.dumps({"policyengine_us": engine, "households": results}, indent=1) + "\n"
    )
    print(f"policyengine-us {engine}; {len(table)} payroll outputs")
    print(f"reproduce published reference: {int(table['matches_reference'].sum())}")
    print(f"federal + state = total: {int(table['parts_add_up'].sum())}")
    print(f"leaves add to state part: {int(table['leaves_add_up'].sum())}")
    with_state = table[table["employee_state_payroll_tax"].abs() > 0]
    print(f"outputs with a state component: {len(with_state)}")
    with pd.option_context("display.width", 250, "display.max_rows", 200):
        print(
            with_state[
                [
                    "scenario_id",
                    "state",
                    "reference",
                    "federal_total",
                    "employee_state_payroll_tax",
                    "state_programs",
                    "excluded",
                ]
            ].to_string(index=False)
        )
        bad = table[~table["matches_reference"]]
        if not bad.empty:
            print("MISMATCH", bad[["scenario_id", "reference", "recomputed"]])


if __name__ == "__main__":
    main()
