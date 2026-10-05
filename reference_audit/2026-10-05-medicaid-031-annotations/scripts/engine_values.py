"""Recompute how the reference system decides scenario_031's head Medicaid eligibility.

The reference system is the one that built the published references: policyengine-us
2.15.17 plus ``latest_final`` (reference_audit/2026-09-28/fixes), on the household
``Scenario.to_pe_household`` builds. The script records the 2026 parameters and the
intermediate variables of the optional senior-or-disabled pathway, under the engine's
modeled Medicare Part B premium and under two readings without it:

``no_part_b``
    The head's ``medicare_part_b_premium`` is 0.
``not_enrolled``
    The head's ``takes_up_medicare_if_eligible`` is False, so the head is not enrolled.

It asserts what the rewritten annotations say: countable income is SSI unearned income
less 12 months of California's $230 disregard, which replaces SSI's $20 general income
exclusion; it is the same under every reading; it is at or below 138% of the 2026
poverty guideline; gross income and income less only the $20 exclusion are above that
limit; countable resources are below California's asset limit; and the reference equals
the published value.

Run from a policybench checkout with the policyengine-us 2.15.17 venv:

  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=<checkout> \\
    <triage>/.venv-pe21517/bin/python \\
      reference_audit/2026-10-05-medicaid-031-annotations/scripts/engine_values.py
"""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parents[1]
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
AUDIT_0928 = ROOT / "reference_audit/2026-09-28"
AUDIT_0922 = ROOT / "reference_audit/2026-09-22"
SCENARIO = "scenario_031"
OUTPUT = "head_medicaid_eligible"
YEAR = 2026
PERIOD = str(YEAR)
STATE = "CA"
CENT = 0.005

READINGS = {
    "modeled": {},
    "no_part_b": {"medicare_part_b_premium": 0.0},
    "not_enrolled": {"takes_up_medicare_if_eligible": False},
}

PERSON_VARIABLES = (
    "age",
    "is_ssi_aged",
    "is_ssi_disabled",
    "is_blind",
    "is_ssi_aged_blind_disabled",
    "is_ssi_recipient_for_medicaid",
    "is_medicare_eligible",
    "medicare_enrolled",
    "medicare_part_b_premium",
    "social_security",
    "pension_income",
    "taxable_ira_distributions",
    "alimony_expense",
    "ssi_unearned_income",
    "ssi_marital_unearned_income",
    "ssi_marital_earned_income",
    "ssi_in_kind_support_and_maintenance",
    "medicaid_optional_senior_or_disabled_unearned_income_deemed_from_ineligible_parent",
    "medicaid_optional_senior_or_disabled_income_deemed_from_ineligible_spouse",
    "ssi_couple_computation_applies",
    "medicaid_optional_senior_or_disabled_countable_income",
    "medicaid_optional_senior_or_disabled_income_limit",
    "is_optional_senior_or_disabled_income_eligible",
    "ssi_countable_resources",
    "is_optional_senior_or_disabled_asset_eligible",
    "is_optional_senior_or_disabled_for_medicaid",
    "is_adult_for_medicaid_nfc",
    "is_adult_for_medicaid",
    "immigration_status",
    "is_medicaid_immigration_status_eligible",
    "medicaid_category",
    "is_medicaid_eligible",
)


def _system():
    from policyengine_us import CountryTaxBenefitSystem

    target = Path(tempfile.mkdtemp(prefix="medicaid_031_fixes_"))
    for path in (AUDIT_0928 / "fixes").glob("*.py"):
        shutil.copy2(path, target / path.name)
    shutil.copy2(AUDIT_0922 / "fixes/r19_irs_sales_tax_2025.json", target)
    spec = importlib.util.spec_from_file_location(
        "latest_final", target / "latest_final.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["latest_final"] = module
    spec.loader.exec_module(module)
    return CountryTaxBenefitSystem(reform=module.reform)


def _scalar(value):
    array = np.asarray(value)
    if array.dtype.kind in "OUS":
        return str(array[0])
    if array.dtype == bool:
        return bool(array[0])
    return float(array[0])


def main() -> None:
    from policyengine_us import Simulation

    from policybench.scenarios import scenario_from_dict

    scenarios = pd.read_csv(RUN / "scenarios.csv")
    row = scenarios[scenarios["scenario_id"] == SCENARIO].iloc[0]
    scenario = scenario_from_dict(json.loads(row["scenario_json"]))
    situation = scenario.to_pe_household()
    assert list(situation["people"]) == ["head"], situation["people"].keys()

    system = _system()
    p = system.parameters(f"{PERIOD}-01-01")
    sod = p.gov.hhs.medicaid.eligibility.categories.senior_or_disabled
    parameters = {
        "senior_or_disabled.income.disregard.individual[CA] (monthly)": float(
            sod.income.disregard.individual[STATE]
        ),
        "senior_or_disabled.income.limit.individual[CA] (share of FPG)": float(
            sod.income.limit.individual[STATE]
        ),
        "senior_or_disabled.assets.limit.individual[CA]": float(
            sod.assets.limit.individual[STATE]
        ),
        "ssa.ssi.income.exclusions.general (monthly)": float(
            p.gov.ssa.ssi.income.exclusions.general
        ),
        "ssa.ssi.eligibility.aged_threshold": float(
            p.gov.ssa.ssi.eligibility.aged_threshold
        ),
        "ssa.ssi.eligibility.resources.limit.individual": float(
            p.gov.ssa.ssi.eligibility.resources.limit.individual
        ),
        "ssa.ssi.income.sources.unearned": list(p.gov.ssa.ssi.income.sources.unearned),
        "ssa.ssi.eligibility.resources.countable": list(
            p.gov.ssa.ssi.eligibility.resources.countable
        ),
        "hhs.fpg.first_person[CONTIGUOUS_US] 2026": float(
            p.gov.hhs.fpg.first_person["CONTIGUOUS_US"]
        ),
        "hhs.fpg.first_person[CONTIGUOUS_US] 2025": float(
            system.parameters("2025-01-01").gov.hhs.fpg.first_person["CONTIGUOUS_US"]
        ),
    }

    readings = {}
    for name, inputs in READINGS.items():
        case = copy.deepcopy(situation)
        for variable, value in inputs.items():
            case["people"]["head"][variable] = {PERIOD: value}
        sim = Simulation(tax_benefit_system=system, situation=case)
        values = {}
        for variable in PERSON_VARIABLES:
            result = sim.calculate(variable, YEAR)
            if hasattr(result, "decode_to_str"):
                values[variable] = str(result.decode_to_str()[0])
            else:
                values[variable] = _scalar(result)
        readings[name] = values

    modeled = readings["modeled"]
    disregard = parameters["senior_or_disabled.income.disregard.individual[CA] (monthly)"]
    general = parameters["ssa.ssi.income.exclusions.general (monthly)"]
    share = parameters["senior_or_disabled.income.limit.individual[CA] (share of FPG)"]
    fpg = parameters["hhs.fpg.first_person[CONTIGUOUS_US] 2026"]
    asset_limit = parameters["senior_or_disabled.assets.limit.individual[CA]"]
    gross = modeled["ssi_marital_unearned_income"]
    countable = modeled["medicaid_optional_senior_or_disabled_countable_income"]
    limit = modeled["medicaid_optional_senior_or_disabled_income_limit"]

    # The reference is the published one.
    reference = pd.read_csv(RUN / "reference_outputs.csv")
    published = reference[
        (reference["scenario_id"] == SCENARIO) & (reference["variable"] == OUTPUT)
    ]
    assert len(published) == 1, published
    published_value = float(published.iloc[0]["value"])
    assert published_value == 1.0, published_value
    assert modeled["is_medicaid_eligible"] is True

    # Unearned income is Social Security, the pension and the IRA distribution.
    parts = (
        modeled["social_security"]
        + modeled["pension_income"]
        + modeled["taxable_ira_distributions"]
    )
    assert abs(gross - parts) < CENT, (gross, parts)
    assert modeled["ssi_marital_earned_income"] == 0.0
    for variable in (
        "ssi_in_kind_support_and_maintenance",
        "medicaid_optional_senior_or_disabled_unearned_income_deemed_from_ineligible_parent",
        "medicaid_optional_senior_or_disabled_income_deemed_from_ineligible_spouse",
    ):
        assert modeled[variable] == 0.0, variable
    assert modeled["ssi_couple_computation_applies"] is False

    # The CA disregard replaces the $20 general exclusion; it is not added to it.
    assert disregard == 230.0 and general == 20.0
    assert abs(countable - (gross - 12 * disregard)) < CENT, (countable, gross)
    assert abs(limit - share * fpg) < CENT, (limit, share, fpg)
    assert share == 1.38 and fpg == 15_960.0
    assert countable <= limit
    assert gross > limit
    assert gross - 12 * general > limit

    # Assets and category.
    assert modeled["ssi_countable_resources"] == 4_200.0
    assert asset_limit == 130_000.0
    assert modeled["ssi_countable_resources"] < asset_limit
    assert modeled["is_ssi_aged"] is True and modeled["is_ssi_disabled"] is False
    assert modeled["is_ssi_recipient_for_medicaid"] is False
    assert modeled["is_adult_for_medicaid_nfc"] is False
    assert modeled["medicaid_category"] == "SENIOR_OR_DISABLED"
    # No status is listed, so the default applies.
    assert modeled["immigration_status"] == "CITIZEN"
    assert modeled["is_medicaid_immigration_status_eligible"] is True

    # The modeled Part B premium does not enter the test.
    assert modeled["medicare_enrolled"] is True
    assert abs(modeled["medicare_part_b_premium"] - 2_434.80) < CENT
    for name in ("no_part_b", "not_enrolled"):
        other = readings[name]
        assert other["medicare_part_b_premium"] == 0.0, name
        for variable in (
            "medicaid_optional_senior_or_disabled_countable_income",
            "medicaid_optional_senior_or_disabled_income_limit",
            "is_optional_senior_or_disabled_income_eligible",
            "is_medicaid_eligible",
            "medicaid_category",
        ):
            assert other[variable] == modeled[variable], (name, variable)

    summary = {
        "gross_unearned_income": round(gross, 2),
        "disregard_annual": 12 * disregard,
        "countable_income": round(countable, 2),
        "income_limit": round(limit, 2),
        "margin_under_limit": round(limit - countable, 2),
        "gross_over_limit": round(gross - limit, 2),
        "gross_less_ssi_general_exclusion_only": round(gross - 12 * general, 2),
        "gross_share_of_2026_fpg": round(gross / fpg, 4),
        "limit_at_2025_fpg": round(
            share * parameters["hhs.fpg.first_person[CONTIGUOUS_US] 2025"], 2
        ),
        "monthly": {
            "gross": round(gross / 12, 2),
            "countable": round(countable / 12, 2),
            "limit": round(limit / 12, 2),
        },
    }
    payload = {
        "note": (
            "scenario_031 head_medicaid_eligible on the reference system "
            "(policyengine-us 2.15.17 + reference_audit/2026-09-28/fixes/latest_final.py). "
            "Written by scripts/engine_values.py, which asserts every relation the "
            "rewritten annotations state."
        ),
        "policyengine_us": version("policyengine-us"),
        "published_reference": published_value,
        "parameters": parameters,
        "summary": summary,
        "readings": readings,
    }
    out = HERE / "verification/engine_values.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, sort_keys=False) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
