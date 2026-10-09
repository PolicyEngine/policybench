"""Recompute every PolicyBench reference without the engine's assumed Medicare enrollment.

policyengine-us 2.15.17 counts a Medicare Part B premium in medical expenses for every
person it treats as enrolled in Medicare. ``medical_expense_health_insurance_premiums``
uses ``health_insurance_premiums`` when that input is set; otherwise it adds
``health_insurance_premiums_without_medicare_part_b`` and ``medicare_part_b_premium *
medicare_enrolled``. ``medicare_enrolled`` adds ``takes_up_medicare_if_eligible``, whose
default is True, for everyone ``is_medicare_eligible`` (age 65, or 24 months of Social
Security disability benefits). ``medicare_part_b_premium`` is the gross premium (the
$202.90 monthly base for 2026 plus an income-related amount on MAGI from two years
earlier) less Medicare Savings Program coverage. No PolicyBench household sets any of
these inputs, and no prompt states Medicare enrollment or a Part B premium.

The reference system is the one that built the published references: policyengine-us
2.15.17 plus ``latest_final`` (reference_audit/2026-09-28/fixes), on households built by
``Scenario.to_pe_household``. The script first recomputes every output and impact weight
and checks them against the published reference CSV. It then reruns every household
under each reading:

``no_part_b``
    Each person's ``medicare_part_b_premium`` is 0: no Part B premium is paid, the
    prompt's "treat any unlisted numeric input as 0". Enrollment itself is unchanged.
``not_enrolled``
    Each person's ``takes_up_medicare_if_eligible`` is False, so nobody is enrolled:
    the prompt's "do not infer ... health coverage". This removes every channel that
    reads enrollment, not only the Part B premium.
``not_enrolled_direct``
    Each person's ``medicare_enrolled`` is False. A differential check on
    ``not_enrolled`` through the other input; the two must agree on every output.
``irmaa_from_2026_income``
    The income-related Part B amount read on the household's 2026 MAGI (AGI plus
    tax-exempt interest) instead of the unset 2024 MAGI, which the engine computes as 0.
    A sensitivity check on the premium's size, not a reading the prompt supports.

For every household with a Medicare-eligible person it also records each person's
Medicare variables and a propagation trace: every engine variable, at every 2026
period the simulation computed, whose value differs between the reference and the
``no_part_b`` or ``not_enrolled`` simulation. The trace lists the consumers that fire,
which the static list of formulas that read the premium cannot show.

Households with an output that moves are also run on a grid of the Part B readings and
the four readings of the state income tax in the federal SALT deduction that
reference_audit/2026-10-05 (PolicyEngine/policybench#191) proposes: the engine's
withholding estimate, the state liability (iterated to a fixed point), none paid, and
none paid without the engine's local sales tax estimate.

Run from a policybench checkout with the policyengine-us 2.15.17 venv:

  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=<checkout> \\
    <triage>/.venv-pe21517/bin/python \\
      reference_audit/2026-10-05-medicare-part-b/scripts/sweep_part_b.py \\
      --out-dir reference_audit/2026-10-05-medicare-part-b/verification
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

import numpy as np
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
TRACE_TOLERANCE = 1e-6
# sweep.py's rename for the 1.755.4 harness; sweep_latest.py kept it on 2.15.17.
RENAME = {"partnership_se_income": "partnership_self_employment_net_earnings"}
MAX_ITERATIONS = 25
CONVERGED = 0.005
FEDERAL = "federal_income_tax_before_refundable_credits"
STATE = "state_income_tax_before_refundable_credits"

READINGS = {
    "no_part_b": {"people": {"medicare_part_b_premium": 0.0}},
    "not_enrolled": {"people": {"takes_up_medicare_if_eligible": False}},
    "not_enrolled_direct": {"people": {"medicare_enrolled": False}},
    "irmaa_from_2026_income": {},  # tax-unit input set per household below
}
TRACED_READINGS = ("no_part_b", "not_enrolled")
PART_B_GRID = ("modeled", "no_part_b", "not_enrolled")
SALT_GRID = ("estimate", "liability", "zero", "zero_no_local_sales")

PERSON_DIAGNOSTICS = (
    "age",
    "is_medicare_eligible",
    "takes_up_medicare_if_eligible",
    "medicare_enrolled",
    "base_part_b_premium",
    "gross_medicare_part_b_premium",
    "msp_part_b_premium_coverage",
    "medicare_part_b_premium",
    "health_insurance_premiums",
    "health_insurance_premiums_without_medicare_part_b",
    "medical_expense_health_insurance_premiums",
    "other_medical_expenses",
    "base_part_a_premium",
    "medicare_part_a_premium",
    "income_adjusted_part_d_premium_surcharge",
    "medicare_cost",
    "is_usda_elderly",
    "is_usda_disabled",
    "social_security_disability",
    "months_receiving_social_security_disability",
)
TAX_UNIT_DIAGNOSTICS = (
    "medicare_irmaa_magi_two_years_prior",
    "adjusted_gross_income",
    "tax_exempt_interest_income",
    "itemized_medical_expenses",
    "medical_expense_deduction",
    "tax_unit_itemizes",
    "standard_deduction",
    "itemized_taxable_income_deductions",
    "salt_deduction",
    "state_withheld_income_tax",
    "local_sales_tax",
)
SPM_UNIT_DIAGNOSTICS = (
    "snap",
    "snap_excess_medical_expense_deduction",
    "snap_net_income",
    "snap_gross_income",
)

_SYSTEM = None


def _assemble_fixes() -> Path:
    """latest_final and its parts, plus the sales tax table the IRS module reads."""
    target = Path(tempfile.mkdtemp(prefix="part_b_fixes_"))
    for path in (AUDIT_0928 / "fixes").glob("*.py"):
        shutil.copy2(path, target / path.name)
    shutil.copy2(AUDIT_0922 / "fixes/r19_irs_sales_tax_2025.json", target)
    return target


def _system():
    global _SYSTEM
    if _SYSTEM is None:
        from policyengine_us import CountryTaxBenefitSystem

        path = _assemble_fixes() / "latest_final.py"
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


def _simulate(situation, *, people=None, tax_unit=None):
    from policyengine_us import Simulation

    situation = copy.deepcopy(situation)
    for person in situation["people"].values():
        for name, value in (people or {}).items():
            person[name] = {PERIOD: value}
    tu = situation["tax_units"]["tax_unit"]
    for name, value in (tax_unit or {}).items():
        tu[name] = {PERIOD: value}
    return Simulation(tax_benefit_system=_system(), situation=situation)


def _total(sim, variable: str) -> float:
    return float(np.asarray(sim.calculate(variable, YEAR)).sum())


def _outputs(sim, scenario, variables) -> tuple[dict, dict]:
    """Every output and, where the output has one, its impact weight."""
    from policybench.ground_truth import (
        _extract_person_impact_weight,
        _extract_person_value,
        _impact_weight_variable_for_output,
        _pe_variable_for_output,
    )

    values, weights = {}, {}
    for variable in variables:
        result = sim.calculate(_pe_variable_for_output(variable, "us"), YEAR)
        values[variable] = float(_extract_person_value(result, scenario, variable))
        weight_variable = _impact_weight_variable_for_output(variable, "us")
        if weight_variable is not None:
            weights[variable] = float(
                _extract_person_impact_weight(
                    result, sim.calculate(weight_variable, YEAR), scenario, variable
                )
            )
    return values, weights


def _person_diagnostics(sim, names) -> dict:
    out = {}
    for variable in PERSON_DIAGNOSTICS:
        values = np.asarray(sim.calculate(variable, YEAR))
        out[variable] = {
            name: (
                bool(v)
                if values.dtype == bool
                else (float(v) if np.issubdtype(values.dtype, np.number) else str(v))
            )
            for name, v in zip(names, values)
        }
    return out


def _unit_diagnostics(sim) -> dict:
    out = {variable: _total(sim, variable) for variable in TAX_UNIT_DIAGNOSTICS}
    for variable in SPM_UNIT_DIAGNOSTICS:
        # Monthly SNAP variables sum to the year when asked for a year.
        out[variable] = _total(sim, variable)
    return out


def _cached(sim) -> dict:
    """Every value the simulation computed or was given for a 2026 period."""
    values = {}
    for name in sim.tax_benefit_system.variables:
        holder = sim.get_holder(name)
        for period in holder.get_known_periods():
            if period.start.year != YEAR:
                continue
            array = holder.get_array(period)
            if array is not None:
                values[(name, str(period))] = np.asarray(array)
    return values


def _trace(base: dict, other: dict) -> list[dict]:
    """Variables whose 2026 values differ between two simulations."""
    rows = {}
    for key in sorted(set(base) | set(other)):
        name, period = key
        if key not in base or key not in other:
            row = rows.setdefault(name, {"variable": name, "max_abs_diff": 0.0})
            row.setdefault("computed_in_one_only", []).append(period)
            continue
        a, b = base[key], other[key]
        if a.shape != b.shape:
            continue
        if np.issubdtype(a.dtype, np.number) and np.issubdtype(b.dtype, np.number):
            diff = np.abs(a.astype(float) - b.astype(float))
            if diff.size and diff.max() > TRACE_TOLERANCE:
                row = rows.setdefault(name, {"variable": name, "max_abs_diff": 0.0})
                row["max_abs_diff"] = max(row["max_abs_diff"], float(diff.max()))
                row.setdefault("periods", []).append(period)
        elif not np.array_equal(a.astype(str), b.astype(str)):
            row = rows.setdefault(name, {"variable": name, "max_abs_diff": 0.0})
            row["categorical"] = True
            row.setdefault("periods", []).append(period)
    return [rows[name] for name in sorted(rows)]


def _salt_liability(sim) -> float:
    """The SALT audit's liability reading: state plus Maryland county, less NYC."""
    state = _total(sim, STATE)
    md_county = _total(sim, "md_local_income_tax_before_refundable_credits")
    nyc = _total(sim, "nyc_income_tax_before_refundable_credits")
    return max(0.0, state + md_county - nyc)


def _grid_cell(situation, scenario, variables, part_b: str, salt: str) -> dict:
    people = {
        "modeled": {},
        "no_part_b": READINGS["no_part_b"]["people"],
        "not_enrolled": READINGS["not_enrolled"]["people"],
    }[part_b]
    tax_unit = {}
    trace = []
    if salt in ("zero", "zero_no_local_sales"):
        tax_unit["state_withheld_income_tax"] = 0.0
    if salt == "zero_no_local_sales":
        tax_unit["local_sales_tax"] = 0.0
    sim = _simulate(situation, people=people, tax_unit=tax_unit)
    if salt == "liability":
        withheld = _salt_liability(sim)
        for _ in range(MAX_ITERATIONS):
            tax_unit["state_withheld_income_tax"] = withheld
            sim = _simulate(situation, people=people, tax_unit=tax_unit)
            implied = _salt_liability(sim)
            trace.append({"withheld": withheld, "implied": implied})
            if abs(implied - withheld) < CONVERGED:
                break
            withheld = implied
        else:
            raise RuntimeError(f"{scenario.id} {part_b}: liability did not converge")
    values, _ = _outputs(sim, scenario, variables)
    return {
        "outputs": values,
        "itemizes": _total(sim, "tax_unit_itemizes"),
        "salt_deduction": _total(sim, "salt_deduction"),
        "medical_expense_deduction": _total(sim, "medical_expense_deduction"),
        "state_withheld_income_tax": _total(sim, "state_withheld_income_tax"),
        "fixed_point_trace": trace,
    }


def sweep_scenario(job) -> dict:
    from policybench.scenarios import scenario_from_dict

    scenario_json, variables = job
    scenario = scenario_from_dict(json.loads(scenario_json))
    situation = build_situation(scenario)
    names = list(situation["people"])

    base = _simulate(situation)
    base_values, base_weights = _outputs(base, scenario, variables)
    eligible = bool(np.asarray(base.calculate("is_medicare_eligible", YEAR)).any())
    result = {
        "scenario_id": scenario.id,
        "state": scenario.state,
        "people": names,
        "medicare_eligible": eligible,
        "baseline": base_values,
        "baseline_weights": base_weights,
        "baseline_person": _person_diagnostics(base, names),
        "baseline_units": _unit_diagnostics(base),
        "readings": {},
    }
    base_cache = _cached(base) if eligible else None
    magi_2026 = _total(base, "adjusted_gross_income") + _total(
        base, "tax_exempt_interest_income"
    )
    for reading, spec in READINGS.items():
        tax_unit = (
            {"medicare_irmaa_magi_two_years_prior": magi_2026}
            if reading == "irmaa_from_2026_income"
            else {}
        )
        sim = _simulate(situation, people=spec.get("people"), tax_unit=tax_unit)
        values, weights = _outputs(sim, scenario, variables)
        entry = {"outputs": values, "weights": weights}
        if eligible:
            entry["person"] = _person_diagnostics(sim, names)
            entry["units"] = _unit_diagnostics(sim)
            if reading in TRACED_READINGS:
                entry["trace"] = _trace(base_cache, _cached(sim))
        result["readings"][reading] = entry

    moved = any(
        _moved(variable, base_values[variable], r["outputs"][variable])
        for r in result["readings"].values()
        for variable in variables
    )
    if moved:
        result["grid"] = {
            f"{part_b}|{salt}": _grid_cell(situation, scenario, variables, part_b, salt)
            for part_b in PART_B_GRID
            for salt in SALT_GRID
        }
    return result


def _moved(variable: str, base: float, value: float) -> bool:
    if variable.endswith(BINARY_SUFFIXES):
        return round(value) != round(base)
    return abs(value - base) > TOLERANCE


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--scenarios", nargs="*")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    from policybench.scenarios import scenario_from_dict
    from policybench.spec import expand_programs_for_scenario

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = json.loads((RUN / "reference_outputs.csv.meta.json").read_text())
    reference = pd.read_csv(RUN / "reference_outputs.csv")
    indexed = reference.set_index(["scenario_id", "variable"])
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
            for v in expand_programs_for_scenario(meta["programs"], scenario)
            if (scenario.id, v) in indexed.index
        ]
        jobs.append((row["scenario_json"], variables))

    engine = version("policyengine-us")
    print(f"policyengine-us {engine}; {len(jobs)} households", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = sorted(pool.map(sweep_scenario, jobs), key=lambda r: r["scenario_id"])

    rows = []
    for result in results:
        sid = result["scenario_id"]
        for variable, base in result["baseline"].items():
            ref = float(indexed.loc[(sid, variable), "value"])
            ref_weight = indexed.loc[(sid, variable), "impact_weight"]
            entry = excluded.get((sid, variable))
            binary = variable.endswith(BINARY_SUFFIXES)
            row = {
                "scenario_id": sid,
                "state": result["state"],
                "variable": variable,
                "medicare_household": result["medicare_eligible"],
                "reference": ref,
                "baseline": base,
                "baseline_matches_reference": (
                    round(base) == round(ref) if binary else abs(base - ref) <= 1e-3
                ),
                "reference_impact_weight": (
                    float(ref_weight) if pd.notna(ref_weight) else None
                ),
                "baseline_impact_weight": result["baseline_weights"].get(variable),
                "excluded": entry is not None,
                "excluded_reason": entry["reason_code"] if entry else "",
            }
            for reading in READINGS:
                r = result["readings"][reading]
                value = r["outputs"][variable]
                row[reading] = value
                row[f"{reading}_delta"] = value - base
                row[f"{reading}_moved"] = _moved(variable, base, value)
                row[f"{reading}_impact_weight"] = r["weights"].get(variable)
            rows.append(row)
    table = pd.DataFrame(rows)
    table.to_csv(out_dir / "sweep_part_b.csv", index=False)

    weight_mismatch = table[
        table["reference_impact_weight"].notna()
        & (
            (table["reference_impact_weight"] - table["baseline_impact_weight"]).abs()
            > 1e-3
        )
    ]
    mismatched = table[~table["baseline_matches_reference"]]
    scored_mismatched = mismatched[~mismatched["excluded"]]
    medicare_households = [r["scenario_id"] for r in results if r["medicare_eligible"]]
    part_b_households = [
        r["scenario_id"]
        for r in results
        if sum(r["baseline_person"]["medicare_part_b_premium"].values()) > 0
    ]
    msp_people = [
        (r["scenario_id"], name)
        for r in results
        for name, v in r["baseline_person"]["msp_part_b_premium_coverage"].items()
        if v > 0
    ]
    eligible_people = [
        (r["scenario_id"], name)
        for r in results
        for name, v in r["baseline_person"]["is_medicare_eligible"].items()
        if v
    ]
    enrollment_matches_eligibility = all(
        r["baseline_person"]["medicare_enrolled"][name]
        == r["baseline_person"]["is_medicare_eligible"][name]
        for r in results
        for name in r["people"]
    )
    snap_or_eligibility = table[
        table["medicare_household"]
        & (
            (table["variable"] == "snap")
            | table["variable"].str.endswith(BINARY_SUFFIXES)
        )
    ]
    differential = table[
        (table["not_enrolled"] - table["not_enrolled_direct"]).abs() > 1e-6
    ]

    def moved_rows(reading):
        moved = table[table[f"{reading}_moved"]]
        return [
            {
                "scenario_id": r.scenario_id,
                "state": r.state,
                "variable": r.variable,
                "reference": r.baseline,
                "value": getattr(r, reading),
                "delta": getattr(r, f"{reading}_delta"),
                "excluded": bool(r.excluded),
            }
            for r in moved.itertuples()
        ]

    def weight_moves(reading):
        col = f"{reading}_impact_weight"
        sub = table[table["baseline_impact_weight"].notna()]
        sub = sub[(sub[col] - sub["baseline_impact_weight"]).abs() > 1e-3]
        return [
            {
                "scenario_id": r.scenario_id,
                "variable": r.variable,
                "baseline_impact_weight": r.baseline_impact_weight,
                "impact_weight": getattr(r, col),
                "excluded": bool(r.excluded),
            }
            for r in sub.itertuples()
        ]

    summary = {
        "policyengine_us": engine,
        "households": len(results),
        "outputs": len(table),
        "scored_outputs": int((~table["excluded"]).sum()),
        "scored_reference_mismatches": scored_mismatched[
            ["scenario_id", "variable", "reference", "baseline"]
        ].to_dict("records"),
        "excluded_outputs_differing_from_frozen_value": int(
            mismatched["excluded"].sum()
        ),
        "impact_weight_mismatches": weight_mismatch[
            [
                "scenario_id",
                "variable",
                "reference_impact_weight",
                "baseline_impact_weight",
            ]
        ].to_dict("records"),
        "medicare_eligible_people": len(eligible_people),
        "medicare_households": medicare_households,
        "part_b_households": part_b_households,
        "msp_part_b_coverage_people": msp_people,
        "enrollment_equals_eligibility_in_reference": enrollment_matches_eligibility,
        "not_enrolled_vs_direct_differences": differential[
            ["scenario_id", "variable", "not_enrolled", "not_enrolled_direct"]
        ].to_dict("records"),
        "moved": {reading: moved_rows(reading) for reading in READINGS},
        "impact_weight_moves": {reading: weight_moves(reading) for reading in READINGS},
        "snap_and_eligibility_outputs_in_medicare_households": snap_or_eligibility[
            ["scenario_id", "state", "variable", "excluded", "baseline"]
            + [reading for reading in READINGS]
        ].to_dict("records"),
    }
    (out_dir / "sweep_part_b_summary.json").write_text(
        json.dumps(summary, indent=1) + "\n"
    )
    (out_dir / "sweep_part_b_households.json").write_text(
        json.dumps({"policyengine_us": engine, "households": results}, indent=1) + "\n"
    )

    print(
        f"baseline: {len(table)} outputs, {summary['scored_outputs']} scored; "
        f"{len(scored_mismatched)} scored outputs differ from the published reference; "
        f"{len(weight_mismatch)} impact weights differ"
    )
    print(
        f"Medicare-eligible: {len(eligible_people)} people in "
        f"{len(medicare_households)} households; Part B premium in "
        f"{len(part_b_households)} households; MSP Part B coverage for "
        f"{len(msp_people)} people; enrollment equals eligibility: "
        f"{enrollment_matches_eligibility}"
    )
    print(f"not_enrolled vs not_enrolled_direct differences: {len(differential)}")
    with pd.option_context("display.width", 220, "display.max_rows", 500):
        for reading in READINGS:
            moved = summary["moved"][reading]
            scored = sum(not m["excluded"] for m in moved)
            print(f"\n{reading}: {len(moved)} outputs move ({scored} scored)")
            for m in moved:
                print(
                    f"  {m['scenario_id']} {m['state']} {m['variable']}: "
                    f"{m['reference']:,.2f} -> {m['value']:,.2f} "
                    f"({m['delta']:+,.2f}){' [excluded]' if m['excluded'] else ''}"
                )
            weights = summary["impact_weight_moves"][reading]
            print(f"  impact weights moved: {len(weights)}")
        print("\nSNAP and eligibility outputs in Medicare households (any change):")
        changed = snap_or_eligibility[
            np.column_stack(
                [
                    (
                        snap_or_eligibility[reading] - snap_or_eligibility["baseline"]
                    ).abs()
                    > 1e-6
                    for reading in READINGS
                ]
            ).any(axis=1)
        ]
        print(changed.to_string(index=False) if len(changed) else "  none")
    for result in results:
        if "grid" in result:
            print(f"\n{result['scenario_id']} grid (federal, state, itemizes):")
            for key, cell in result["grid"].items():
                o = cell["outputs"]
                print(
                    f"  {key:32s} {o.get(FEDERAL, float('nan')):>12,.2f} "
                    f"{o.get(STATE, float('nan')):>10,.2f} {cell['itemizes']:.0f}"
                )


if __name__ == "__main__":
    main()
