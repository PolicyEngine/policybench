"""Recompute every PolicyBench reference with the state income tax in SALT read three ways.

policyengine-us 2.15.17 fills the state income tax part of the federal SALT deduction
(26 U.S.C. 164(a)(3)) with ``state_withheld_income_tax``, which adds per-state
``*_withheld_income_tax`` estimates (parameters/gov/states/household/
state_withheld_income_tax.yaml). Each estimate is a formula of the person's federal AGI
(for Massachusetts, 5% of AGI above the $4,400 single exemption), not the household's
state liability, and no PolicyBench prompt states state income tax withheld or paid.

The reference system is the one that built the published references: policyengine-us
2.15.17 plus ``latest_final`` (the nine pre-freeze-law conventions and the Maryland
output-scope adapter), on households built by ``Scenario.to_pe_household``. The script
first recomputes every output under it and checks the result against the published
reference CSV. It then reruns every household under three readings of "state income
tax paid in 2026", each fed in as ``state_withheld_income_tax`` (the tax-unit input that
SALT and the state formulas that read SALT or withholding consume):

``liability``
    The household pays its 2026 state income tax liability during 2026: the engine's
    own state income tax before refundable credits. Maryland county tax is added
    (2.15.17 sends it to SALT only through the withholding proxy; the published
    output excludes it) and NYC tax is removed (it reaches SALT through
    ``local_income_tax``). Because a state's tax can depend on federal tax or on the
    federal SALT deduction, the input is iterated to a fixed point; the trace records
    how many passes each household needed.
``net``
    As ``liability``, net of state refundable credits and floored at zero.
``zero``
    The prompt's "treat any unlisted numeric input as 0": no state income tax was
    withheld or paid in 2026, so SALT takes the larger of local income tax and the
    engine's general sales tax (164(b)(5)).

Run from a policybench checkout with the policyengine-us 2.15.17 venv:

  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=<checkout> \\
    <triage>/.venv-pe21517/bin/python reference_audit/2026-10-05/scripts/sweep_salt_withholding.py \\
      --out-dir reference_audit/2026-10-05/verification
"""

from __future__ import annotations

import argparse
import copy
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
PERIOD = str(YEAR)
BINARY_SUFFIXES = ("_eligible",)
TOLERANCE = 1.0
# sweep.py's rename for the 1.755.4 harness; sweep_latest.py kept it on 2.15.17.
RENAME = {"partnership_se_income": "partnership_self_employment_net_earnings"}
MAX_ITERATIONS = 25
CONVERGED = 0.005
READINGS = ("liability", "net", "zero")
DIAGNOSTICS = (
    "adjusted_gross_income",
    "tax_unit_taxable_social_security",
    "tax_unit_itemizes",
    "standard_deduction",
    "itemized_taxable_income_deductions",
    "real_estate_taxes",
    "state_withheld_income_tax",
    "local_income_tax",
    "state_sales_tax",
    "local_sales_tax",
    "state_and_local_sales_or_income_tax",
    "salt",
    "salt_cap",
    "salt_deduction",
    "state_income_tax_before_refundable_credits",
    "md_local_income_tax_before_refundable_credits",
    "nyc_income_tax_before_refundable_credits",
    "state_refundable_credits",
    "employee_state_payroll_tax",
    "income_tax_before_refundable_credits",
)

_SYSTEM = None
_FIX_DIR = None


def _assemble_fixes() -> Path:
    """latest_final and its parts, plus the sales tax table the IRS module reads."""
    target = Path(tempfile.mkdtemp(prefix="salt_withholding_fixes_"))
    for path in (AUDIT_0928 / "fixes").glob("*.py"):
        shutil.copy2(path, target / path.name)
    shutil.copy2(AUDIT_0922 / "fixes/r19_irs_sales_tax_2025.json", target)
    return target


def _load_reform(fix_dir: Path):
    path = fix_dir / "latest_final.py"
    spec = importlib.util.spec_from_file_location("latest_final", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["latest_final"] = module
    spec.loader.exec_module(module)
    return module.reform


def _system():
    global _SYSTEM, _FIX_DIR
    if _SYSTEM is None:
        from policyengine_us import CountryTaxBenefitSystem

        _FIX_DIR = _assemble_fixes()
        _SYSTEM = CountryTaxBenefitSystem(reform=_load_reform(_FIX_DIR))
    return _SYSTEM


def build_situation(scenario) -> dict:
    situation = scenario.to_pe_household()
    for person in situation["people"].values():
        for old, new in RENAME.items():
            if old in person:
                person[new] = person.pop(old)
    return situation


def _tax_unit_value(sim, variable: str) -> float:
    try:
        return float(sim.calculate(variable, YEAR).sum())
    except Exception:  # noqa: BLE001 - diagnostics only; a missing variable is None
        return float("nan")


def _salt_income_tax(sim, reading: str) -> float:
    """The state (and Maryland county) income tax a reading says was paid in 2026."""
    if reading == "zero":
        return 0.0
    state = _tax_unit_value(sim, "state_income_tax_before_refundable_credits")
    md_county = _tax_unit_value(sim, "md_local_income_tax_before_refundable_credits")
    nyc = _tax_unit_value(sim, "nyc_income_tax_before_refundable_credits")
    amount = state + md_county - nyc
    if reading == "net":
        amount -= _tax_unit_value(sim, "state_refundable_credits")
    return max(0.0, amount)


def _outputs(sim, scenario, variables) -> dict[str, float]:
    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output

    values = {}
    for variable in variables:
        pe_variable = _pe_variable_for_output(variable, "us")
        values[variable] = float(
            _extract_person_value(sim.calculate(pe_variable, YEAR), scenario, variable)
        )
    return values


def _diagnostics(sim) -> dict[str, float]:
    return {name: _tax_unit_value(sim, name) for name in DIAGNOSTICS}


def _simulate(situation: dict, withheld: float | None):
    from policyengine_us import Simulation

    situation = copy.deepcopy(situation)
    if withheld is not None:
        situation["tax_units"]["tax_unit"]["state_withheld_income_tax"] = {
            PERIOD: withheld
        }
    return Simulation(tax_benefit_system=_system(), situation=situation)


def sweep_scenario(args: tuple[str, list[str]]) -> dict:
    """Baseline and the three readings for one household."""
    from policybench.scenarios import scenario_from_dict

    scenario_json, variables = args
    scenario = scenario_from_dict(json.loads(scenario_json))
    situation = build_situation(scenario)

    base = _simulate(situation, None)
    result = {
        "scenario_id": scenario.id,
        "state": scenario.state,
        "baseline": _outputs(base, scenario, variables),
        "baseline_diagnostics": _diagnostics(base),
        "readings": {},
    }
    for reading in READINGS:
        trace = []
        if reading == "zero":
            withheld = 0.0
            sim = _simulate(situation, withheld)
            trace.append({"withheld": withheld, "implied": 0.0})
            converged = True
        else:
            withheld = _salt_income_tax(base, reading)
            converged = False
            for _ in range(MAX_ITERATIONS):
                sim = _simulate(situation, withheld)
                implied = _salt_income_tax(sim, reading)
                trace.append({"withheld": withheld, "implied": implied})
                if abs(implied - withheld) < CONVERGED:
                    converged = True
                    break
                withheld = implied
        result["readings"][reading] = {
            "withheld": withheld,
            "converged": converged,
            "iterations": len(trace),
            "trace": trace,
            "outputs": _outputs(sim, scenario, variables),
            "diagnostics": _diagnostics(sim),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--scenarios", nargs="*")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    from policybench.scenarios import scenario_from_dict
    from policybench.spec import expand_programs_for_scenario

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = json.loads((RUN / "reference_outputs.csv.meta.json").read_text())
    programs = meta["programs"]
    reference = pd.read_csv(RUN / "reference_outputs.csv")
    indexed = reference.set_index(["scenario_id", "variable"])["value"]
    exclusions = json.loads((RUN / "reference_exclusions.json").read_text())[
        "exclusions"
    ]
    excluded = {(e["scenario_id"], e["variable"]): e for e in exclusions}
    scenarios = pd.read_csv(RUN / "scenarios.csv")
    if args.scenarios:
        scenarios = scenarios[scenarios["scenario_id"].isin(args.scenarios)]

    jobs = []
    for _, row in scenarios.iterrows():
        scenario = scenario_from_dict(json.loads(row["scenario_json"]))
        variables = [
            v
            for v in expand_programs_for_scenario(programs, scenario)
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
        for variable, base in result["baseline"].items():
            key = (sid, variable)
            ref = float(indexed[key])
            entry = excluded.get(key)
            binary = variable.endswith(BINARY_SUFFIXES)
            row = {
                "scenario_id": sid,
                "state": result["state"],
                "variable": variable,
                "reference": ref,
                "baseline": base,
                "baseline_matches_reference": (
                    round(base) == round(ref) if binary else abs(base - ref) <= 1e-3
                ),
                "excluded": entry is not None,
                "excluded_reason": entry["reason_code"] if entry else "",
            }
            for reading in READINGS:
                value = result["readings"][reading]["outputs"][variable]
                delta = value - base
                row[reading] = value
                row[f"{reading}_delta"] = delta
                row[f"{reading}_moved"] = (
                    round(value) != round(base) if binary else abs(delta) > TOLERANCE
                )
            rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(out_dir / "sweep_salt_withholding.csv", index=False)

    households = []
    for result in results:
        item = {
            "scenario_id": result["scenario_id"],
            "state": result["state"],
            "baseline": result["baseline_diagnostics"],
        }
        for reading in READINGS:
            r = result["readings"][reading]
            item[reading] = {
                "withheld": r["withheld"],
                "converged": r["converged"],
                "iterations": r["iterations"],
                "trace": r["trace"],
                "diagnostics": r["diagnostics"],
            }
        households.append(item)
    (out_dir / "sweep_salt_withholding_households.json").write_text(
        json.dumps(
            {"policyengine_us": engine, "households": households},
            indent=1,
            sort_keys=True,
        )
        + "\n"
    )

    scored = table[~table["excluded"]]
    mismatched = table[~table["baseline_matches_reference"] & ~table["excluded"]]
    print(
        f"baseline: {len(table)} outputs, {len(scored)} scored, "
        f"{len(mismatched)} scored outputs differ from the published reference"
    )
    if not mismatched.empty:
        print(mismatched[["scenario_id", "variable", "reference", "baseline"]])
    unconverged = [
        (h["scenario_id"], reading)
        for h in households
        for reading in READINGS
        if not h[reading]["converged"]
    ]
    print(f"unconverged: {unconverged}")
    with pd.option_context("display.width", 220, "display.max_rows", 500):
        for reading in READINGS:
            moved = table[table[f"{reading}_moved"]]
            print(
                f"\n{reading}: {len(moved)} outputs move "
                f"({int((~moved['excluded']).sum())} scored)"
            )
            print(
                moved[
                    [
                        "scenario_id",
                        "state",
                        "variable",
                        "baseline",
                        reading,
                        f"{reading}_delta",
                        "excluded",
                    ]
                ].to_string(index=False)
            )


if __name__ == "__main__":
    main()
