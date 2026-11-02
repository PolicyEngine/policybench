"""Trace PolicyBench scenario_039 (VA) and scenario_025 (OH) on a policyengine-us checkout.

Builds each situation the way policybench.scenarios.Scenario.to_pe_household does
(person inputs as listed, the hours alias, the take-up defaults, head/spouse marital
unit) and prints the full computation tree of the benchmark output.

Usage: python trace_cells.py <scenarios.csv> [out_dir]
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np
from policyengine_us import Simulation
import policyengine_us

csv.field_size_limit(10**9)
YEAR = 2026
ALIASES = {"hours_worked_last_week": "weekly_hours_worked_before_lsr"}
TAKEUP = {
    "person": {"takes_up_medicaid_if_eligible": True, "takes_up_ssi_if_eligible": True},
    "tax_unit": {
        "takes_up_aca_if_eligible": True,
        "takes_up_dc_ptc": True,
        "takes_up_eitc": True,
        "would_file_if_eligible_for_refundable_credit": True,
        "would_file_taxes_voluntarily": True,
    },
    "spm_unit": {"takes_up_snap_if_eligible": True},
    "household": {},
}
DROPPED_TAX_UNIT = {"first_home_mortgage_interest", "second_home_mortgage_interest"}


def y(v):
    return {str(YEAR): v}


def situation(sc):
    people, names = {}, []
    for p in sc["adults"] + sc.get("children", []):
        d = {"age": y(p["age"]), "employment_income": y(p["employment_income"])}
        for k, v in p["inputs"].items():
            d[k] = y(v)
        for s, t in ALIASES.items():
            if s in p["inputs"] and t not in p["inputs"]:
                d[t] = y(p["inputs"][s])
        for k, v in TAKEUP["person"].items():
            d.setdefault(k, y(v))
        people[p["name"]] = d
        names.append(p["name"])
    tu = {"members": names}
    for k, v in sc["tax_unit_inputs"].items():
        if k not in DROPPED_TAX_UNIT:
            tu[k] = y(v)
    for k, v in TAKEUP["tax_unit"].items():
        tu.setdefault(k, y(v))
    spm = {"members": names, **{k: y(v) for k, v in sc["spm_unit_inputs"].items()}}
    for k, v in TAKEUP["spm_unit"].items():
        spm.setdefault(k, y(v))
    hh = {"members": names, "state_code": y(sc["state"])}
    for k, v in sc["household_inputs"].items():
        hh[k] = y(v)
    heads = [a["name"] for a in sc["adults"] if a["inputs"].get("is_tax_unit_head")]
    spouses = [a["name"] for a in sc["adults"] if a["inputs"].get("is_tax_unit_spouse")]
    groups = []
    couple = (heads[0], spouses[0]) if len(heads) == 1 and len(spouses) == 1 else None
    if couple:
        groups.append(list(couple))
    for n in names:
        if not couple or n not in couple:
            groups.append([n])
    return {
        "people": people,
        "marital_units": {f"marital_unit_{i}": {"members": g} for i, g in enumerate(groups, 1)},
        "tax_units": {"tax_unit": tu},
        "spm_units": {"spm_unit": spm},
        "families": {"family": {"members": names}},
        "households": {"household": hh},
    }


def fmt(a):
    a = np.asarray(a)
    if a.dtype.kind in "fiu":
        return ", ".join(f"{float(x):,.2f}" for x in a.ravel())
    return ", ".join(str(x) for x in a.ravel())


def print_tree(sim, out, max_depth=40, show_zero=False):
    seen = set()

    def walk(node, depth):
        v = np.asarray(node.value)
        zero = v.dtype.kind in "fiub" and not np.any(v)
        key = (node.name, str(node.period))
        if zero and not show_zero and depth > 1:
            return
        mark = "" if key not in seen else "  (shown above)"
        out.write(f"{'  ' * depth}{node.name}<{node.period}> = {fmt(v)}{mark}\n")
        if key in seen or depth >= max_depth:
            return
        seen.add(key)
        for c in node.children:
            walk(c, depth + 1)

    for root in sim.tracer.trees:
        walk(root, 0)


CELLS = {
    "scenario_039": ("income_tax_before_refundable_credits", [
        "filing_status", "surviving_spouse_eligible", "tax_unit_child_dependents", "head_of_household_eligible",
        "irs_gross_income", "self_employment_income", "estate_income", "taxable_pension_income",
        "taxable_ira_distributions", "social_security", "tax_unit_combined_income_for_social_security_taxability",
        "tax_unit_taxable_social_security", "above_the_line_deductions", "loss_ald", "adjusted_gross_income",
        "standard_deduction", "basic_standard_deduction", "additional_standard_deduction", "additional_senior_deduction",
        "itemized_taxable_income_deductions", "tax_unit_itemizes", "qualified_business_income", "qualified_business_income_deduction",
        "taxable_income_deductions", "taxable_income", "income_tax_main_rates", "capital_gains_tax", "regular_tax_before_credits",
        "alternative_minimum_tax", "net_investment_income_tax", "income_tax_before_credits",
        "income_tax_capped_non_refundable_credits", "elderly_disabled_credit", "savers_credit",
        "income_tax_before_refundable_credits", "self_employment_tax", "va_income_tax_before_refundable_credits",
    ]),
    "scenario_025": ("state_income_tax_before_refundable_credits", [
        "filing_status", "adjusted_gross_income", "adjusted_gross_income_person", "oh_additions", "oh_deductions", "oh_agi", "oh_agi_person",
        "has_esi", "is_medicare_eligible", "oh_employer_subsidized_health_plan_eligible",
        "medical_expense_health_insurance_premiums", "self_employed_health_insurance_ald_person", "oh_medical_care_insurance_premiums",
        "oh_uninsured_unreimbursed_medical_care_expenses", "oh_insured_unreimbursed_medical_care_expense_amount",
        "oh_insured_unreimbursed_medical_care_expenses", "oh_insured_unreimbursed_medical_care_expenses_person",
        "oh_unreimbursed_medical_care_expense_deduction", "oh_unreimbursed_medical_care_expense_deduction_person",
        "oh_modified_agi", "oh_personal_exemptions", "oh_taxable_income", "oh_taxable_business_income", "oh_taxable_nonbusiness_income",
        "oh_income_tax_before_non_refundable_credits", "oh_non_refundable_credits", "oh_retirement_credit",
        "oh_pension_based_retirement_income_credit", "oh_lump_sum_distribution_credit", "oh_senior_citizen_credit",
        "oh_joint_filing_credit", "oh_joint_filing_credit_eligible", "oh_joint_filing_credit_qualifying_income",
        "oh_exemption_credit", "oh_non_public_school_credits", "oh_cdcc", "oh_income_tax_before_refundable_credits",
        "oh_refundable_credits", "oh_income_tax", "state_income_tax_before_refundable_credits",
    ]),
}


def main():
    scen_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)
    scen = {}
    with open(scen_path) as f:
        for row in csv.DictReader(f):
            if row["scenario_id"] in CELLS:
                scen[row["scenario_id"]] = json.loads(row["scenario_json"])
    from importlib.metadata import version
    print("policyengine-us", version("policyengine-us"), "at", Path(policyengine_us.__file__).parent)
    print("policyengine-core", version("policyengine-core"))
    for sid, (target, names) in CELLS.items():
        sit = situation(scen[sid])
        (out_dir / f"{sid}_situation.json").write_text(json.dumps(sit, indent=1))
        sim = Simulation(situation=sit)
        sim.trace = True
        val = sim.calculate(target, YEAR)
        print(f"\n===== {sid} {target} = {fmt(val)}")
        with open(out_dir / f"{sid}_trace.txt", "w") as out:
            print_tree(sim, out)
        with open(out_dir / f"{sid}_trace_full.txt", "w") as out:
            print_tree(sim, out, show_zero=True)
        flat = Simulation(situation=sit)
        tbs = flat.tax_benefit_system
        for n in names:
            if n not in tbs.variables:
                print(f"  {n:62s} (not a variable on this version)")
                continue
            try:
                val_n = flat.calculate(n, YEAR)
                if tbs.variables[n].value_type.__name__ == "Enum":
                    val_n = np.array([str(x) for x in val_n.decode_to_str()])
                print(f"  {n:62s} {fmt(val_n)}")
            except Exception as e:  # report, don't hide
                print(f"  {n:62s} ERROR {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
