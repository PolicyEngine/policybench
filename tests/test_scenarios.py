"""Tests for scenario generation."""

import json

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import policybench.scenarios as scenarios_module
from policybench.scenarios import (
    SUPPORTED_FILING_STATUSES,
    Person,
    Scenario,
    _eligible_uk_households,
    _is_geographic_defined_for,
    generate_scenarios,
    get_promptable_input_specs,
    load_excluded_household_ids,
    load_scenarios_from_manifest,
    scenario_manifest,
    scenarios_from_cps_frame,
    scenarios_from_uk_frames,
)


def test_uk_dataset_candidates_avoid_developer_transfer_worktree():
    candidate_paths = [str(path) for path in scenarios_module.UK_DATASET_CANDIDATES]

    assert all(
        "policyengine-uk-data-transfer-pr" not in path for path in candidate_paths
    )
    assert any(path.endswith("data/enhanced_cps_2025.h5") for path in candidate_paths)


@pytest.fixture
def sample_person_frame():
    return pd.DataFrame(
        [
            {
                "person_id": 1,
                "household_id": 101,
                "tax_unit_id": 201,
                "spm_unit_id": 301,
                "family_id": 401,
                "marital_unit_id": 501,
                "household_weight": 2.0,
                "state_code": "CA",
                "filing_status": "HEAD_OF_HOUSEHOLD",
                "age": 35,
                "employment_income": 30_000.0,
                "real_estate_taxes": 4_000.0,
                "home_mortgage_interest": 9_000.0,
                "health_savings_account_ald": 800.0,
                "spm_unit_pre_subsidy_childcare_expenses": 2_400.0,
                "auto_loan_interest": 300.0,
                "auto_loan_balance": 5_000.0,
                "is_tax_unit_head": True,
            },
            {
                "person_id": 2,
                "household_id": 101,
                "tax_unit_id": 201,
                "spm_unit_id": 301,
                "family_id": 401,
                "marital_unit_id": 501,
                "household_weight": 2.0,
                "state_code": "CA",
                "filing_status": "HEAD_OF_HOUSEHOLD",
                "age": 8,
                "employment_income": 0.0,
            },
            {
                "person_id": 3,
                "household_id": 102,
                "tax_unit_id": 202,
                "spm_unit_id": 302,
                "family_id": 402,
                "marital_unit_id": 502,
                "household_weight": 3.0,
                "state_code": "TX",
                "filing_status": "JOINT",
                "age": 40,
                "employment_income": 70_000.0,
                "is_tax_unit_head": True,
            },
            {
                "person_id": 4,
                "household_id": 102,
                "tax_unit_id": 202,
                "spm_unit_id": 302,
                "family_id": 402,
                "marital_unit_id": 502,
                "household_weight": 3.0,
                "state_code": "TX",
                "filing_status": "JOINT",
                "age": 38,
                "employment_income": 30_000.0,
                "self_employment_income": 5_000.0,
                "is_tax_unit_spouse": True,
            },
            {
                "person_id": 5,
                "household_id": 102,
                "tax_unit_id": 202,
                "spm_unit_id": 302,
                "family_id": 402,
                "marital_unit_id": 502,
                "household_weight": 3.0,
                "state_code": "TX",
                "filing_status": "JOINT",
                "age": 10,
                "employment_income": 0.0,
            },
            {
                "person_id": 6,
                "household_id": 102,
                "tax_unit_id": 202,
                "spm_unit_id": 302,
                "family_id": 402,
                "marital_unit_id": 502,
                "household_weight": 3.0,
                "state_code": "TX",
                "filing_status": "JOINT",
                "age": 5,
                "employment_income": 0.0,
            },
            {
                "person_id": 7,
                "household_id": 103,
                "tax_unit_id": 203,
                "spm_unit_id": 303,
                "family_id": 403,
                "marital_unit_id": 503,
                "household_weight": 1.0,
                "state_code": "NY",
                "filing_status": "SINGLE",
                "age": 67,
                "employment_income": 0.0,
                "social_security_retirement": 22_000.0,
                "is_tax_unit_head": True,
            },
            {
                "person_id": 8,
                "household_id": 103,
                "tax_unit_id": 203,
                "spm_unit_id": 303,
                "family_id": 403,
                "marital_unit_id": 504,
                "household_weight": 1.0,
                "state_code": "NY",
                "filing_status": "SINGLE",
                "age": 19,
                "employment_income": 0.0,
                "is_full_time_college_student": True,
            },
            {
                "person_id": 9,
                "household_id": 104,
                "tax_unit_id": 204,
                "spm_unit_id": 304,
                "family_id": 404,
                "marital_unit_id": 505,
                "household_weight": 4.0,
                "state_code": "FL",
                "filing_status": "SINGLE",
                "age": 50,
                "employment_income": 45_000.0,
                "is_tax_unit_head": True,
            },
            {
                "person_id": 10,
                "household_id": 104,
                "tax_unit_id": 205,
                "spm_unit_id": 304,
                "family_id": 404,
                "marital_unit_id": 505,
                "household_weight": 4.0,
                "state_code": "FL",
                "filing_status": "SINGLE",
                "age": 22,
                "employment_income": 12_000.0,
            },
            {
                "person_id": 11,
                "household_id": 105,
                "tax_unit_id": 206,
                "spm_unit_id": 306,
                "family_id": 406,
                "marital_unit_id": 506,
                "household_weight": 5.0,
                "state_code": "CO",
                "filing_status": "SINGLE",
                "age": 52,
                "employment_income": 0.0,
                "disability_benefits": 18_000.0,
                "is_disabled": True,
                "is_tax_unit_head": True,
            },
            {
                "person_id": 12,
                "household_id": 106,
                "tax_unit_id": 207,
                "spm_unit_id": 307,
                "family_id": 407,
                "marital_unit_id": 507,
                "household_weight": 6.0,
                "state_code": "AZ",
                "filing_status": "HEAD_OF_HOUSEHOLD",
                "age": 45,
                "employment_income": 38_000.0,
                "is_tax_unit_head": True,
            },
            {
                "person_id": 13,
                "household_id": 106,
                "tax_unit_id": 207,
                "spm_unit_id": 307,
                "family_id": 407,
                "marital_unit_id": 507,
                "household_weight": 6.0,
                "state_code": "AZ",
                "filing_status": "HEAD_OF_HOUSEHOLD",
                "age": 16,
                "employment_income": 0.0,
            },
            {
                "person_id": 14,
                "household_id": 106,
                "tax_unit_id": 207,
                "spm_unit_id": 307,
                "family_id": 407,
                "marital_unit_id": 507,
                "household_weight": 6.0,
                "state_code": "AZ",
                "filing_status": "HEAD_OF_HOUSEHOLD",
                "age": 14,
                "employment_income": 0.0,
            },
            {
                "person_id": 15,
                "household_id": 106,
                "tax_unit_id": 207,
                "spm_unit_id": 307,
                "family_id": 407,
                "marital_unit_id": 507,
                "household_weight": 6.0,
                "state_code": "AZ",
                "filing_status": "HEAD_OF_HOUSEHOLD",
                "age": 12,
                "employment_income": 0.0,
            },
            {
                "person_id": 16,
                "household_id": 106,
                "tax_unit_id": 207,
                "spm_unit_id": 307,
                "family_id": 407,
                "marital_unit_id": 507,
                "household_weight": 6.0,
                "state_code": "AZ",
                "filing_status": "HEAD_OF_HOUSEHOLD",
                "age": 10,
                "employment_income": 0.0,
            },
            {
                "person_id": 17,
                "household_id": 106,
                "tax_unit_id": 207,
                "spm_unit_id": 307,
                "family_id": 407,
                "marital_unit_id": 507,
                "household_weight": 6.0,
                "state_code": "AZ",
                "filing_status": "HEAD_OF_HOUSEHOLD",
                "age": 8,
                "employment_income": 0.0,
            },
            {
                "person_id": 18,
                "household_id": 106,
                "tax_unit_id": 207,
                "spm_unit_id": 307,
                "family_id": 407,
                "marital_unit_id": 507,
                "household_weight": 6.0,
                "state_code": "AZ",
                "filing_status": "HEAD_OF_HOUSEHOLD",
                "age": 6,
                "employment_income": 0.0,
            },
        ]
    )


@pytest.fixture
def sample_uk_frames():
    person_df = pd.DataFrame(
        [
            {
                "person_id": 1,
                "person_household_id": 1001,
                "person_benunit_id": 2001,
                "age": 42,
                "gender": "FEMALE",
                "marital_status": "MARRIED",
                "employment_income": 42_000.0,
                "self_employment_income": 0.0,
                "savings_interest_income": 120.0,
                "dividend_income": 50.0,
                "private_pension_income": 0.0,
                "state_pension": 0.0,
                "state_pension_reported": 0.0,
                "capital_gains_before_response": 0.0,
                "property_income": 0.0,
                "miscellaneous_income": 0.0,
                "employment_expenses": 150.0,
                "private_pension_contributions": 600.0,
                "gift_aid": 75.0,
                "blind_persons_allowance": 0.0,
                "is_disabled_for_benefits": False,
                "pip_dl_category": "NONE",
                "pip_m_category": "NONE",
                "hours_worked": 37.5,
                "is_disabled": False,
                "is_student": False,
            },
            {
                "person_id": 2,
                "person_household_id": 1001,
                "person_benunit_id": 2001,
                "age": 12,
                "gender": "MALE",
                "marital_status": "SINGLE",
                "employment_income": 0.0,
                "self_employment_income": 0.0,
                "savings_interest_income": 0.0,
                "dividend_income": 0.0,
                "private_pension_income": 0.0,
                "state_pension": 0.0,
                "state_pension_reported": 0.0,
                "capital_gains_before_response": 0.0,
                "property_income": 0.0,
                "miscellaneous_income": 0.0,
                "employment_expenses": 0.0,
                "private_pension_contributions": 0.0,
                "gift_aid": 0.0,
                "blind_persons_allowance": 0.0,
                "is_disabled_for_benefits": False,
                "pip_dl_category": "NONE",
                "pip_m_category": "NONE",
                "hours_worked": 0.0,
                "is_disabled": False,
                "is_student": True,
            },
            {
                "person_id": 3,
                "person_household_id": 1002,
                "person_benunit_id": 2002,
                "age": 72,
                "gender": "MALE",
                "marital_status": "SINGLE",
                "employment_income": 0.0,
                "self_employment_income": 0.0,
                "savings_interest_income": 40.0,
                "dividend_income": 0.0,
                "private_pension_income": 8_500.0,
                "state_pension": 12_000.0,
                "state_pension_reported": 11_000.0,
                "capital_gains_before_response": 0.0,
                "property_income": 0.0,
                "miscellaneous_income": 0.0,
                "employment_expenses": 0.0,
                "private_pension_contributions": 0.0,
                "gift_aid": 0.0,
                "blind_persons_allowance": 0.0,
                "is_disabled_for_benefits": True,
                "pip_dl_category": "STANDARD",
                "pip_dl_reported": 5_740.80,
                "pip_m_category": "NONE",
                "pip_m_reported": 0.0,
                "hours_worked": 0.0,
                "is_disabled": True,
                "is_student": False,
            },
        ]
    )
    household_df = pd.DataFrame(
        [
            {
                "household_id": 1001,
                "household_weight": 2.5,
                "region": "LONDON",
                "tenure_type": "RENT_PRIVATELY",
                "council_tax": 1_800.0,
                "rent": 14_400.0,
                "mortgage_interest_repayment": 0.0,
                "mortgage_capital_repayment": 0.0,
                "savings": 2_500.0,
                "household_wealth": 22_000.0,
                "num_vehicles": 1.0,
                "council_tax_band": "C",
            },
            {
                "household_id": 1002,
                "household_weight": 1.5,
                "region": "WALES",
                "tenure_type": "OWNED_OUTRIGHT",
                "council_tax": 1_200.0,
                "rent": 0.0,
                "mortgage_interest_repayment": 0.0,
                "mortgage_capital_repayment": 0.0,
                "savings": 6_000.0,
                "household_wealth": 95_000.0,
                "num_vehicles": 0.0,
                "council_tax_band": "B",
            },
        ]
    )
    return person_df, household_df


def test_generate_scenarios_count(sample_person_frame):
    """Generates the requested number of scenarios."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=3, seed=42)
    assert len(scenarios) == 3


def test_generate_scenarios_deterministic(sample_person_frame):
    """Same seed produces identical scenarios."""
    s1 = scenarios_from_cps_frame(sample_person_frame, n=3, seed=123)
    s2 = scenarios_from_cps_frame(sample_person_frame, n=3, seed=123)
    for a, b in zip(s1, s2):
        assert a.id == b.id
        assert a.state == b.state
        assert a.filing_status == b.filing_status
        assert a.total_income == b.total_income
        assert a.num_children == b.num_children


def test_generate_scenarios_different_seeds(sample_person_frame):
    """Different seeds produce different samples."""
    s1 = scenarios_from_cps_frame(sample_person_frame, n=2, seed=1)
    s2 = scenarios_from_cps_frame(sample_person_frame, n=2, seed=2)
    different = sum(
        1
        for a, b in zip(s1, s2)
        if a.state != b.state or a.total_income != b.total_income
    )
    assert different > 0


def test_scenario_structure(sample_person_frame):
    """Each scenario has required fields."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=3, seed=0)
    for scenario in scenarios:
        assert scenario.id.startswith("scenario_")
        assert len(scenario.state) == 2
        assert scenario.filing_status in SUPPORTED_FILING_STATUSES.values()
        assert len(scenario.adults) >= 1
        assert scenario.num_children >= 0
        assert scenario.year == 2026
        assert scenario.source_dataset == "populace_us_2024"


def test_invalid_households_are_filtered(sample_person_frame):
    """Ambiguous or multi-tax-unit households should not be benchmark scenarios."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=4, seed=0)
    household_ids = {scenario.metadata["household_id"] for scenario in scenarios}
    assert 104 not in household_ids


def test_large_households_are_allowed_when_structure_is_clean(sample_person_frame):
    """Large households with one tax/SPM/family/marital unit should remain eligible."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=4, seed=0)
    scenario_106 = next(
        scenario for scenario in scenarios if scenario.metadata["household_id"] == 106
    )
    assert len(scenario_106.adults) == 1
    assert scenario_106.num_children == 6


def test_adult_dependents_are_allowed_when_structure_is_clean(sample_person_frame):
    """Single-tax-unit households can include adult dependents."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=5, seed=0)
    scenario_103 = next(
        scenario for scenario in scenarios if scenario.metadata["household_id"] == 103
    )

    assert [person.name for person in scenario_103.adults] == ["head", "dependent1"]
    assert scenario_103.adults[0].inputs["is_tax_unit_head"] is True
    assert scenario_103.adults[0].inputs["is_tax_unit_spouse"] is False
    assert scenario_103.adults[1].inputs["is_tax_unit_head"] is False
    assert scenario_103.adults[1].inputs["is_tax_unit_spouse"] is False


def test_richer_cps_inputs_are_preserved(sample_person_frame):
    """Raw nonzero inputs across entities should be carried into the scenario."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=4, seed=0)
    joint = next(s for s in scenarios if s.filing_status == "joint")
    assert joint.adults[1].inputs["self_employment_income"] == 5_000.0

    disabled_single = next(s for s in scenarios if s.state == "CO")
    assert disabled_single.adults[0].inputs["is_disabled"] is True
    assert disabled_single.adults[0].inputs["disability_benefits"] == 18_000.0

    hoh = next(s for s in scenarios if s.state == "CA")
    assert hoh.adults[0].inputs["real_estate_taxes"] == 4_000.0
    assert hoh.adults[0].inputs["home_mortgage_interest"] == 9_000.0
    assert hoh.tax_unit_inputs["health_savings_account_ald"] == 800.0
    assert hoh.spm_unit_inputs["spm_unit_pre_subsidy_childcare_expenses"] == 2_400.0
    assert hoh.household_inputs["auto_loan_interest"] == 300.0
    assert hoh.household_inputs["auto_loan_balance"] == 5_000.0


def test_promptable_inputs_are_pure_leaf_variables():
    """Prompts should not expose conditional or formula-defined PE variables."""
    from policybench.policyengine_runtime import make_us_microsimulation

    sim = make_us_microsimulation()
    specs = get_promptable_input_specs()
    source_names = {spec.source_name for spec in specs}

    assert "medicare_enrolled" not in source_names
    assert "net_worth" not in source_names
    assert "employer_quarterly_payroll_expense_override" not in source_names
    assert "employer_state_unemployment_tax_rate_override" not in source_names
    assert "has_medicaid_health_coverage_at_interview" not in source_names
    assert "has_never_worked" not in source_names
    assert "hourly_wage" in source_names
    assert "hours_worked_last_week" in source_names
    assert "is_paid_hourly" in source_names
    assert "is_union_member_or_covered" not in source_names
    assert "is_wic_at_nutritional_risk" not in source_names
    assert "selected_marketplace_plan_benchmark_ratio" in source_names
    assert "va_ccsp_is_full_day" not in source_names
    assert "weekly_hours_worked" not in source_names
    assert "weekly_hours_worked_before_lsr" not in source_names
    assert all("_last_year" not in source_name for source_name in source_names)
    assert "was_calworks_recipient" in source_names
    for spec in specs:
        variable = sim.tax_benefit_system.variables[spec.source_name]
        assert getattr(variable, "formula", None) is None
        assert not getattr(variable, "formulas", None)
        defined_for = getattr(variable, "defined_for", None)
        assert defined_for is None or _is_geographic_defined_for(defined_for)
        assert not getattr(variable, "adds", None)
        assert not getattr(variable, "subtracts", None)


def test_conditional_inputs_are_not_preserved():
    """Conditional leaf inputs should not appear in scenario facts."""
    scenario = scenarios_from_cps_frame(
        pd.DataFrame(
            [
                {
                    "person_id": 1,
                    "household_id": 1,
                    "tax_unit_id": 1,
                    "spm_unit_id": 1,
                    "family_id": 1,
                    "marital_unit_id": 1,
                    "household_weight": 1.0,
                    "state_code": "PA",
                    "filing_status": "SINGLE",
                    "age": 64,
                    "employment_income": 50_000.0,
                    "medicare_enrolled": True,
                    "has_medicaid_health_coverage_at_interview": True,
                    "is_tax_unit_head": True,
                }
            ]
        ),
        n=1,
        seed=0,
    )[0]

    assert "medicare_enrolled" not in scenario.adults[0].inputs
    assert "has_medicaid_health_coverage_at_interview" not in scenario.adults[0].inputs


def test_missing_bool_inputs_are_not_preserved():
    """Missing boolean source values should not become true prompt facts."""
    scenario = scenarios_from_cps_frame(
        pd.DataFrame(
            [
                {
                    "person_id": 1,
                    "household_id": 1,
                    "tax_unit_id": 1,
                    "spm_unit_id": 1,
                    "family_id": 1,
                    "marital_unit_id": 1,
                    "household_weight": 1.0,
                    "state_code": "PA",
                    "filing_status": "SINGLE",
                    "age": 35,
                    "employment_income": 50_000.0,
                    "has_esi": pd.NA,
                    "is_tax_unit_head": True,
                }
            ]
        ),
        n=1,
        seed=0,
    )[0]

    assert "has_esi" not in scenario.adults[0].inputs


def test_aggregate_net_worth_input_is_not_preserved():
    """Aggregate net worth should not be mixed with partial balance-sheet facts."""
    scenario = scenarios_from_cps_frame(
        pd.DataFrame(
            [
                {
                    "person_id": 1,
                    "household_id": 1,
                    "tax_unit_id": 1,
                    "spm_unit_id": 1,
                    "family_id": 1,
                    "marital_unit_id": 1,
                    "household_weight": 1.0,
                    "state_code": "PA",
                    "filing_status": "SINGLE",
                    "age": 35,
                    "employment_income": 50_000.0,
                    "bank_account_assets": 500.0,
                    "employer_quarterly_payroll_expense_override": -1.0,
                    "employer_state_unemployment_tax_rate_override": -1.0,
                    "employment_income_last_year": 48_000.0,
                    "hourly_wage": 25.0,
                    "hours_worked_last_week": 40.0,
                    "is_paid_hourly": True,
                    "is_wic_at_nutritional_risk": True,
                    "net_worth": 250_000.0,
                    "selected_marketplace_plan_benchmark_ratio": 1.25,
                    "self_employment_income_last_year": 2_000.0,
                    "va_ccsp_is_full_day": True,
                    "weekly_hours_worked": 40.0,
                    "is_tax_unit_head": True,
                }
            ]
        ),
        n=1,
        seed=0,
    )[0]

    assert scenario.adults[0].inputs["bank_account_assets"] == 500.0
    assert (
        "employer_quarterly_payroll_expense_override" not in scenario.adults[0].inputs
    )
    assert (
        "employer_state_unemployment_tax_rate_override" not in scenario.adults[0].inputs
    )
    assert scenario.adults[0].inputs["hourly_wage"] == 25.0
    assert scenario.adults[0].inputs["hours_worked_last_week"] == 40.0
    assert scenario.adults[0].inputs["is_paid_hourly"] is True
    assert "is_wic_at_nutritional_risk" not in scenario.adults[0].inputs
    assert "weekly_hours_worked" not in scenario.adults[0].inputs
    assert scenario.tax_unit_inputs["selected_marketplace_plan_benchmark_ratio"] == 1.25
    assert "employment_income_last_year" not in scenario.adults[0].inputs
    assert "self_employment_income_last_year" not in scenario.adults[0].inputs
    assert "va_ccsp_is_full_day" not in scenario.adults[0].inputs
    assert "net_worth" not in scenario.household_inputs


def test_overtime_premium_input_is_sent_to_policyengine():
    scenario = scenarios_from_cps_frame(
        pd.DataFrame(
            [
                {
                    "person_id": 1,
                    "household_id": 1,
                    "tax_unit_id": 1,
                    "spm_unit_id": 1,
                    "family_id": 1,
                    "marital_unit_id": 1,
                    "household_weight": 1.0,
                    "state_code": "PA",
                    "filing_status": "SINGLE",
                    "age": 35,
                    "employment_income": 50_000.0,
                    "fsla_overtime_premium": 3_000.0,
                    "tip_income": 5_000.0,
                    "is_tax_unit_head": True,
                }
            ]
        ),
        n=1,
        seed=0,
    )[0]

    assert scenario.adults[0].inputs["tip_income"] == 5_000.0
    assert scenario.total_income == 50_000.0

    pe_household = scenario.to_pe_household()
    head = pe_household["people"]["head"]
    assert "tip_income" in head
    # fsla_overtime_premium became a model input (no formula) in
    # policyengine-us 1.722+, so the scenario must pass the sampled value
    # through — dropping it would silently change no-tax-on-overtime math.
    assert head["fsla_overtime_premium"] == {"2026": 3_000.0}


def test_formula_county_fields_are_not_prompted_or_sent_to_policyengine():
    scenario = scenarios_from_cps_frame(
        pd.DataFrame(
            [
                {
                    "person_id": 1,
                    "household_id": 1,
                    "tax_unit_id": 1,
                    "spm_unit_id": 1,
                    "family_id": 1,
                    "marital_unit_id": 1,
                    "household_weight": 1.0,
                    "state_code": "CA",
                    "state_fips": 6,
                    "county_fips": 37,
                    "county_str": "LOS_ANGELES_COUNTY_CA",
                    "filing_status": "SINGLE",
                    "age": 35,
                    "employment_income": 50_000.0,
                    "is_tax_unit_head": True,
                }
            ]
        ),
        n=1,
        seed=0,
    )[0]

    pe_household = scenario.to_pe_household()
    household = pe_household["households"]["household"]
    assert "county_fips" not in household
    assert "county_str" not in household


def test_geographic_leaf_inputs_are_preserved():
    """State-gated leaf inputs should remain available as scenario facts."""
    scenario = scenarios_from_cps_frame(
        pd.DataFrame(
            [
                {
                    "person_id": 1,
                    "household_id": 1,
                    "tax_unit_id": 1,
                    "spm_unit_id": 1,
                    "family_id": 1,
                    "marital_unit_id": 1,
                    "household_weight": 1.0,
                    "state_code": "CA",
                    "filing_status": "SINGLE",
                    "age": 35,
                    "employment_income": 50_000.0,
                    "was_calworks_recipient": True,
                    "is_tax_unit_head": True,
                }
            ]
        ),
        n=1,
        seed=0,
    )[0]

    assert scenario.spm_unit_inputs["was_calworks_recipient"] is True


def test_children_and_adults_split_by_age(sample_person_frame):
    """Adults and children should be split at age 18."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=4, seed=0)
    for scenario in scenarios:
        for adult in scenario.adults:
            assert adult.age >= 18
        for child in scenario.children:
            assert child.age < 18


def test_pe_household_format(simple_single_scenario):
    """PE household JSON has required structure and lets PE infer filing status."""
    household = simple_single_scenario.to_pe_household()

    assert "people" in household
    assert "tax_units" in household
    assert "spm_units" in household
    assert "families" in household
    assert "households" in household

    assert "adult1" in household["people"]
    person = household["people"]["adult1"]
    assert "age" in person
    assert "employment_income" in person

    tax_unit = household["tax_units"]["tax_unit"]
    assert "filing_status" not in tax_unit
    assert tax_unit["takes_up_eitc"]["2026"] is True
    assert tax_unit["would_file_if_eligible_for_refundable_credit"]["2026"] is True
    assert tax_unit["would_file_taxes_voluntarily"]["2026"] is True

    housing = household["households"]["household"]
    assert "state_code" in housing
    assert (
        household["people"]["adult1"]["takes_up_medicaid_if_eligible"]["2026"] is True
    )
    assert household["people"]["adult1"]["takes_up_ssi_if_eligible"]["2026"] is True


def test_pe_household_includes_cross_entity_inputs():
    """Scenario-level tax-unit, SPM, and household inputs should be emitted."""
    scenario = scenarios_from_cps_frame(
        pd.DataFrame(
            [
                {
                    "person_id": 1,
                    "household_id": 1,
                    "tax_unit_id": 1,
                    "spm_unit_id": 1,
                    "family_id": 1,
                    "marital_unit_id": 1,
                    "household_weight": 1.0,
                    "state_code": "CA",
                    "filing_status": "SINGLE",
                    "age": 40,
                    "employment_income": 50_000.0,
                    "real_estate_taxes": 4_200.0,
                    "health_savings_account_ald": 900.0,
                    "spm_unit_pre_subsidy_childcare_expenses": 1_200.0,
                    "auto_loan_interest": 250.0,
                    "is_tax_unit_head": True,
                }
            ]
        ),
        n=1,
        seed=0,
    )[0]

    household = scenario.to_pe_household()
    assert household["people"]["head"]["real_estate_taxes"]["2026"] == 4_200.0
    assert (
        household["tax_units"]["tax_unit"]["health_savings_account_ald"]["2026"]
        == 900.0
    )
    assert (
        household["spm_units"]["spm_unit"]["spm_unit_pre_subsidy_childcare_expenses"][
            "2026"
        ]
        == 1_200.0
    )
    assert (
        household["spm_units"]["spm_unit"]["takes_up_snap_if_eligible"]["2026"] is True
    )
    assert household["households"]["household"]["auto_loan_interest"]["2026"] == 250.0


def test_total_income_ignores_deductions_and_hours(sample_person_frame):
    """Display income should not add deductions or weekly hours as income."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=4, seed=0)
    hoh = next(s for s in scenarios if s.state == "CA")
    assert hoh.total_income == 30_000.0


def test_pe_household_with_children(family_scenario):
    """PE household includes children in all groups."""
    household = family_scenario.to_pe_household()

    all_members = household["tax_units"]["tax_unit"]["members"]
    assert "adult1" in all_members
    assert "adult2" in all_members
    assert "child1" in all_members
    assert "child2" in all_members
    assert "filing_status" not in household["tax_units"]["tax_unit"]
    assert len(household["people"]) == 4


def test_generate_scenarios_uses_loader(monkeypatch, sample_person_frame):
    """Top-level US generation should delegate to the certified dataset loader."""

    def fake_loader():
        return sample_person_frame, 2024, "populace_us_2024"

    monkeypatch.setattr(
        "policybench.scenarios.load_certified_us_person_frame", fake_loader
    )
    scenarios = generate_scenarios(n=3, seed=0)

    assert len(scenarios) == 3
    assert all(scenario.metadata["dataset_year"] == 2024 for scenario in scenarios)
    assert all(scenario.source_dataset == "populace_us_2024" for scenario in scenarios)


def test_generate_uk_scenarios_uses_loader(monkeypatch, sample_uk_frames):
    person_df, household_df = sample_uk_frames

    def fake_loader():
        return person_df, household_df, 2025

    monkeypatch.setattr("policybench.scenarios.load_uk_transfer_frames", fake_loader)
    scenarios = generate_scenarios(n=2, seed=0, country="uk")

    assert len(scenarios) == 2
    assert all(scenario.country == "uk" for scenario in scenarios)
    assert all(scenario.filing_status is None for scenario in scenarios)
    assert all(scenario.metadata["dataset_year"] == 2025 for scenario in scenarios)
    assert all(
        scenario.source_dataset == "uk_calibrated_transfer_2025"
        for scenario in scenarios
    )


def test_scenarios_from_cps_frame_can_exclude_households(sample_person_frame):
    """Sampling can exclude already-used benchmark households."""
    scenarios = scenarios_from_cps_frame(
        sample_person_frame,
        n=2,
        seed=0,
        excluded_household_ids={102},
    )

    assert len(scenarios) == 2
    household_ids = {scenario.metadata["household_id"] for scenario in scenarios}
    assert 102 not in household_ids
    assert len(household_ids) == 2


def test_load_excluded_household_ids_from_manifest_json(tmp_path):
    """Manifest helper should recover household ids from serialized scenarios."""
    manifest_path = tmp_path / "scenarios.csv"
    pd.DataFrame(
        [
            {
                "scenario_id": "scenario_000",
                "scenario_json": json.dumps({"metadata": {"household_id": 101}}),
            },
            {
                "scenario_id": "scenario_001",
                "scenario_json": json.dumps({"metadata": {"household_id": 205}}),
            },
        ]
    ).to_csv(manifest_path, index=False)

    assert load_excluded_household_ids(manifest_path) == {101, 205}


def test_scenario_manifest_exports_summary_fields(sample_person_frame):
    """Scenario manifest should expose the dashboard summary fields."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=2, seed=0)
    manifest = scenario_manifest(scenarios)

    assert set(manifest.columns) == {
        "scenario_id",
        "country",
        "state",
        "filing_status",
        "num_adults",
        "num_children",
        "total_income",
        "source_dataset",
        "scenario_json",
    }
    assert len(manifest) == 2
    assert manifest["scenario_id"].str.startswith("scenario_").all()


def test_load_scenarios_from_manifest_round_trips(sample_person_frame, tmp_path):
    """Serialized manifests should reconstruct the exact scenarios."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=2, seed=0)
    manifest_path = tmp_path / "scenarios.csv"
    scenario_manifest(scenarios).to_csv(manifest_path, index=False)

    loaded = load_scenarios_from_manifest(manifest_path)

    assert [scenario.id for scenario in loaded] == [
        scenario.id for scenario in scenarios
    ]
    assert [scenario.state for scenario in loaded] == [
        scenario.state for scenario in scenarios
    ]
    assert [scenario.filing_status for scenario in loaded] == [
        scenario.filing_status for scenario in scenarios
    ]
    assert [scenario.total_income for scenario in loaded] == [
        scenario.total_income for scenario in scenarios
    ]


def test_scenarios_from_uk_frames_include_region_and_household_inputs(sample_uk_frames):
    person_df, household_df = sample_uk_frames
    scenarios = scenarios_from_uk_frames(person_df, household_df, n=2, seed=0)

    assert len(scenarios) == 2
    london = next(s for s in scenarios if s.state == "LONDON")
    assert london.country == "uk"
    assert london.filing_status is None
    assert london.household_inputs["rent"] == 14_400.0
    assert london.household_inputs["tenure_type"] == "RENT_PRIVATELY"
    assert "council_tax_band" not in london.household_inputs
    assert "council_tax" not in london.household_inputs
    assert "benunit_id" not in london.household_inputs
    assert london.children[0].inputs["is_student"] is True
    pensioner = next(s for s in scenarios if s.state == "WALES")
    assert pensioner.adults[0].inputs["state_pension"] == 12_000.0
    assert "state_pension_reported" not in pensioner.adults[0].inputs
    assert pensioner.adults[0].inputs["pip_dl_category"] == "STANDARD"
    assert "pip_dl_reported" not in pensioner.adults[0].inputs
    assert "pip_m_reported" not in pensioner.adults[0].inputs


def test_scenarios_from_uk_frames_keeps_adult_qualifying_young_people_as_dependents(
    sample_uk_frames,
):
    person_df, household_df = sample_uk_frames
    qyp_people = person_df.iloc[[0, 1]].copy()
    qyp_people["person_id"] = [20, 21]
    qyp_people["person_household_id"] = 1003
    qyp_people["person_benunit_id"] = 3001
    qyp_people["age"] = [45, 18]
    qyp_people["is_child_or_QYP"] = [False, True]
    qyp_household = household_df.iloc[[0]].copy()
    qyp_household["household_id"] = 1003
    qyp_household["household_weight"] = 1_000.0

    person_df = pd.concat([person_df, qyp_people], ignore_index=True)
    household_df = pd.concat([household_df, qyp_household], ignore_index=True)
    eligible = _eligible_uk_households(person_df, household_df)
    scenarios = scenarios_from_uk_frames(
        person_df,
        household_df,
        n=3,
        seed=0,
    )

    assert set(eligible["household_id"]) == {1001, 1002, 1003}
    qyp_scenario = next(s for s in scenarios if s.metadata["household_id"] == 1003)
    assert [person.name for person in qyp_scenario.adults] == ["adult1"]
    assert [person.name for person in qyp_scenario.children] == ["qyp1"]


def test_scenarios_from_uk_frames_filter_to_one_benefit_unit(sample_uk_frames):
    person_df, household_df = sample_uk_frames
    extra_people = person_df.iloc[[0, 0]].copy()
    extra_people["person_id"] = [10, 11]
    extra_people["person_household_id"] = 1003
    extra_people["person_benunit_id"] = [3001, 3002]
    extra_people["age"] = [40, 38]
    extra_household = household_df.iloc[[0]].copy()
    extra_household["household_id"] = 1003
    extra_household["household_weight"] = 1_000.0

    scenarios = scenarios_from_uk_frames(
        pd.concat([person_df, extra_people], ignore_index=True),
        pd.concat([household_df, extra_household], ignore_index=True),
        n=2,
        seed=0,
    )

    household_ids = {scenario.metadata["household_id"] for scenario in scenarios}
    assert household_ids == {1001, 1002}


def test_scenarios_from_uk_frames_use_employment_income_leaf(sample_uk_frames):
    person_df, household_df = sample_uk_frames
    person_df = person_df.rename(
        columns={"employment_income": "employment_income_before_lsr"}
    )

    scenarios = scenarios_from_uk_frames(person_df, household_df, n=2, seed=0)

    london = next(s for s in scenarios if s.state == "LONDON")
    assert london.adults[0].employment_income == 42_000.0
    assert "employment_income_before_lsr" not in london.adults[0].inputs


def test_sample_household_ids_requires_enough_positive_weight():
    from policybench.scenarios import _sample_household_ids

    # Three eligible households but only one has positive sampling weight;
    # requesting two must raise a clear error, not numpy's cryptic
    # "Fewer non-zero entries in p than size".
    eligible = pd.DataFrame(
        {"household_id": [1, 2, 3], "household_weight": [5.0, 0.0, 0.0]}
    )
    with pytest.raises(ValueError, match="positive sampling weight"):
        _sample_household_ids(eligible, n=2, seed=0)


def _couple_scenario(
    head_name: str,
    spouse_name: str,
    *,
    flags: bool = True,
    filing_status: str | None = "joint",
    state: str = "TX",
    age: int = 67,
    extra_adults: tuple[str, ...] = (),
    children: tuple[str, ...] = (),
) -> Scenario:
    def adult(name: str, role: str | None) -> Person:
        inputs: dict[str, object] = {}
        if flags:
            inputs["is_tax_unit_head"] = role == "head"
            inputs["is_tax_unit_spouse"] = role == "spouse"
        return Person(name=name, age=age, employment_income=0.0, inputs=inputs)

    return Scenario(
        id="couple",
        state=state,
        filing_status=filing_status,
        adults=[
            adult(head_name, "head"),
            adult(spouse_name, "spouse"),
            *[adult(name, None) for name in extra_adults],
        ],
        children=[Person(name=name, age=8, employment_income=0.0) for name in children],
    )


def _unit_members(scenario: Scenario) -> set[frozenset[str]]:
    return {frozenset(unit["members"]) for unit in scenario.marital_units().values()}


def test_marital_units_follow_relationship_inputs_not_person_names():
    """Renaming people must not change the household the engine sees."""
    canonical = _couple_scenario("head", "spouse", extra_adults=("dependent1",))
    renamed = _couple_scenario("adult1", "adult2", extra_adults=("adult3",))

    assert _unit_members(canonical) == {
        frozenset({"head", "spouse"}),
        frozenset({"dependent1"}),
    }
    assert _unit_members(renamed) == {
        frozenset({"adult1", "adult2"}),
        frozenset({"adult3"}),
    }
    # Flags win over names: the person called "spouse" is the flagged head.
    swapped = _couple_scenario("spouse", "head")
    assert swapped.marital_couple() == ("spouse", "head")


def test_marital_units_cover_every_person_exactly_once():
    scenario = _couple_scenario(
        "adult1", "adult2", extra_adults=("adult3",), children=("kid1", "kid2")
    )
    members = [
        name for unit in scenario.marital_units().values() for name in unit["members"]
    ]
    assert sorted(members) == ["adult1", "adult2", "adult3", "kid1", "kid2"]
    assert scenario.to_pe_household()["marital_units"] == scenario.marital_units()


def test_marital_units_fall_back_for_manifests_without_relationship_inputs():
    # Legacy manifests name the couple head/spouse.
    assert _couple_scenario("head", "spouse", flags=False).marital_couple() == (
        "head",
        "spouse",
    )
    # A joint return with exactly two adults is a married couple.
    assert _couple_scenario("adult1", "adult2", flags=False).marital_couple() == (
        "adult1",
        "adult2",
    )
    # Two unflagged adults who do not file jointly are not assumed married.
    single = _couple_scenario("adult1", "adult2", flags=False, filing_status="single")
    assert single.marital_couple() is None
    assert _unit_members(single) == {frozenset({"adult1"}), frozenset({"adult2"})}
    # Flags present but no spouse flagged: no couple, whatever the names say.
    no_spouse = _couple_scenario("head", "spouse")
    no_spouse.adults[1].inputs["is_tax_unit_spouse"] = False
    assert no_spouse.marital_couple() is None


@pytest.mark.slow
def test_reference_calculation_is_invariant_to_person_identifiers():
    """A joint-filing couple, both 67 with no income, gets the same SSI whether
    the people are called head/spouse or adult1/adult2 (PolicyEngine-US)."""
    from policybench.ground_truth import calculate_single

    canonical = calculate_single(_couple_scenario("head", "spouse"), "ssi")
    renamed = calculate_single(_couple_scenario("adult1", "adult2"), "ssi")
    assert renamed == pytest.approx(canonical)
    # Splitting the couple into two single-person marital units would pay two
    # individual SSI awards; the couple rate is lower than twice the individual.
    single_units = _couple_scenario("adult1", "adult2")
    for adult in single_units.adults:
        adult.inputs["is_tax_unit_head"] = False
        adult.inputs["is_tax_unit_spouse"] = False
    single_units.filing_status = "single"
    assert calculate_single(single_units, "ssi") > canonical


def test_marital_unit_keys_cannot_collide_with_person_names():
    """A dependent named "couple" (or anything else) must not displace the
    couple's unit: keys are positional, and every person stays mapped."""
    scenario = _couple_scenario("head", "spouse", children=("couple",))
    units = scenario.marital_units()
    assert list(units) == ["marital_unit_1", "marital_unit_2"]
    assert units["marital_unit_1"]["members"] == ["head", "spouse"]
    assert units["marital_unit_2"]["members"] == ["couple"]
    for name in ("marital_unit_1", "marital_unit_2", "1", "spouse2"):
        renamed = _couple_scenario("head", "spouse", children=(name,))
        members = sorted(
            member
            for unit in renamed.marital_units().values()
            for member in unit["members"]
        )
        assert members == sorted(["head", "spouse", name])


@pytest.mark.slow
def test_reference_calculation_is_invariant_to_a_child_named_couple():
    from policybench.ground_truth import calculate_single

    baseline = calculate_single(
        _couple_scenario("head", "spouse", children=("dependent1",)), "ssi"
    )
    renamed = calculate_single(
        _couple_scenario("head", "spouse", children=("couple",)), "ssi"
    )
    assert renamed == pytest.approx(baseline)


def _hours_scenario(hours):
    row = {
        "person_id": 1,
        "household_id": 1,
        "tax_unit_id": 1,
        "spm_unit_id": 1,
        "family_id": 1,
        "marital_unit_id": 1,
        "household_weight": 1.0,
        "state_code": "VA",
        "filing_status": "SINGLE",
        "age": 31,
        "employment_income": 520.0,
        "is_tax_unit_head": True,
    }
    if hours is not None:
        row["hours_worked_last_week"] = hours
    return scenarios_from_cps_frame(pd.DataFrame([row]), n=1, seed=0)[0]


@pytest.mark.parametrize("hours", [12.0, 40.0, 60.0])
def test_stated_usual_hours_reach_the_snap_work_tests(hours):
    """The prompt's "usual weekly hours worked" is what SNAP's work rules read."""
    scenario = _hours_scenario(hours)
    head = scenario.to_pe_household()["people"]["head"]
    assert head["hours_worked_last_week"] == {"2026": hours}
    assert head["weekly_hours_worked_before_lsr"] == {"2026": hours}
    # The engine name stays out of the prompt; only the stated input is shown.
    assert scenarios_module.is_excluded_prompt_input_name(
        "weekly_hours_worked_before_lsr"
    )
    assert not scenarios_module.is_excluded_prompt_input_name("hours_worked_last_week")


@pytest.mark.parametrize("hours", [None, 0.0])
def test_unstated_or_zero_hours_keep_the_engine_default(hours):
    # Zero-valued inputs are not carried, so the engine default (0) applies,
    # which is also the prompt's rule for unlisted numbers.
    head = _hours_scenario(hours).to_pe_household()["people"]["head"]
    assert "hours_worked_last_week" not in head
    assert "weekly_hours_worked_before_lsr" not in head


class _FakeUKVariable:
    def __init__(self, entity_key: str):
        self.entity = type("Entity", (), {"key": entity_key})()


class _FakeUKTransferSimulation:
    """Stored values are the 2025 survey year; 2026 values are uprated."""

    STORED = {
        "person_id": ("person", [1.0, 2.0]),
        "person_household_id": ("person", [10.0, 10.0]),
        "person_benunit_id": ("person", [20.0, 20.0]),
        "age": ("person", [40.0, 17.0]),
        "gender": ("person", ["FEMALE", "MALE"]),
        "employment_income_before_lsr": ("person", [30_000.0, 0.0]),
        "benunit_id": ("benunit", [20.0]),
        "household_id": ("household", [10.0]),
        "household_weight": ("household", [1.0]),
        "region": ("household", ["NORTH_WEST"]),
        "rent": ("household", [6_000.0]),
    }
    UPRATED = {"employment_income_before_lsr": 1.034, "rent": 1.02}
    COMPUTED = {
        "state_pension": [0.0, 0.0],
        "current_education": ["NOT_IN_EDUCATION", "POST_SECONDARY"],
        "date_of_birth": [19860601, 20090401],
    }

    def __init__(self, extra_stored=None, drop_computed=()):
        stored = dict(self.STORED, **(extra_stored or {}))
        self.stored = stored
        variables = {
            name: _FakeUKVariable(entity) for name, (entity, _) in stored.items()
        }
        for name in self.COMPUTED:
            if name not in drop_computed:
                variables[name] = _FakeUKVariable("person")
        for name in extra_stored or {}:
            if name.startswith("unknown_"):
                variables.pop(name)
        self.tax_benefit_system = type("TBS", (), {"variables": variables})()
        self.periods = set()

    def calculate(self, variable, period, map_to=None, unweighted=True):
        self.periods.add(period)
        if variable in self.COMPUTED:
            return np.asarray(self.COMPUTED[variable])
        values = np.asarray(self.stored[variable][1])
        if period == "2026" and variable in self.UPRATED:
            return values * self.UPRATED[variable]
        return values


def _patch_uk_transfer(monkeypatch, sim):
    import policybench.policyengine_runtime as runtime

    class FakeDataset:
        time_period = 2025

        def __init__(self, file_path):
            self.file_path = file_path

        def load(self):
            return {
                name: np.asarray(values) for name, (_, values) in sim.stored.items()
            }

    monkeypatch.setattr(scenarios_module, "get_uk_dataset_path", lambda: "fake.h5")
    monkeypatch.setattr(
        runtime, "get_uk_single_year_dataset_class", lambda: FakeDataset
    )
    monkeypatch.setattr(runtime, "make_uk_transfer_microsimulation", lambda path: sim)


def test_load_uk_transfer_frames_prompts_reference_period_values(monkeypatch):
    sim = _FakeUKTransferSimulation()
    _patch_uk_transfer(monkeypatch, sim)

    person_df, household_df, dataset_year = scenarios_module.load_uk_transfer_frames()

    assert dataset_year == 2025
    assert sim.periods == {"2026"}
    # The prompt must show the uprated 2026-27 amounts the reference uses,
    # not the stored 2025 survey values.
    assert person_df["employment_income_before_lsr"].tolist() == pytest.approx(
        [31_020.0, 0.0]
    )
    assert household_df["rent"].tolist() == pytest.approx([6_120.0])
    assert person_df["current_education"].tolist() == [
        "NOT_IN_EDUCATION",
        "POST_SECONDARY",
    ]
    assert person_df["date_of_birth"].tolist() == [19860601, 20090401]


def test_load_uk_transfer_frames_rejects_variables_the_engine_dropped(monkeypatch):
    sim = _FakeUKTransferSimulation(
        extra_stored={"unknown_pip_dl_reported": ("person", [0.0, 0.0])}
    )
    _patch_uk_transfer(monkeypatch, sim)

    with pytest.raises(ValueError, match="does not define"):
        scenarios_module.load_uk_transfer_frames()


def test_load_uk_transfer_frames_rejects_renamed_computed_inputs(monkeypatch):
    sim = _FakeUKTransferSimulation(drop_computed=("current_education",))
    _patch_uk_transfer(monkeypatch, sim)

    with pytest.raises(ValueError, match="no longer defines 'current_education'"):
        scenarios_module.load_uk_transfer_frames()


def test_load_uk_transfer_frames_rejects_benefit_unit_inputs(monkeypatch):
    sim = _FakeUKTransferSimulation(extra_stored={"benunit_rent": ("benunit", [100.0])})
    _patch_uk_transfer(monkeypatch, sim)

    with pytest.raises(ValueError, match="benefit-unit inputs"):
        scenarios_module.load_uk_transfer_frames()


def test_uk_current_education_is_prompted_only_for_ages_16_to_19():
    def person_row(age):
        return pd.Series(
            {
                "person_id": 1,
                "person_household_id": 1,
                "person_benunit_id": 1,
                "age": age,
                "employment_income_before_lsr": 0.0,
                "current_education": "POST_SECONDARY",
            }
        )

    prompted = {
        age: "current_education"
        in scenarios_module._extract_uk_person_inputs(person_row(age))
        for age in (15, 16, 19, 20)
    }
    assert prompted == {15: False, 16: True, 19: True, 20: False}


UK_PROMPTED_PERSON_INPUTS = {
    "savings_interest_income": st.integers(min_value=1, max_value=10**6),
    "dividend_income": st.integers(min_value=1, max_value=10**6),
    "property_income": st.integers(min_value=-(10**5), max_value=10**6).filter(bool),
    "pip_dl_category": st.sampled_from(["STANDARD", "ENHANCED"]),
    "is_disabled_for_benefits": st.just(True),
    "gender": st.sampled_from(["MALE", "FEMALE"]),
    # Age 40 on 6 October 2026.
    "date_of_birth": st.sampled_from([19860101, 19860601, 19851231]),
}


@settings(max_examples=60, deadline=None)
@given(
    adult_inputs=st.fixed_dictionaries(
        {},
        optional={name: strat for name, strat in UK_PROMPTED_PERSON_INPUTS.items()},
    ),
    household_inputs=st.fixed_dictionaries(
        {},
        optional={
            "rent": st.integers(min_value=1, max_value=10**5),
            "savings": st.integers(min_value=1, max_value=10**6),
            "tenure_type": st.sampled_from(["RENT_PRIVATELY", "OWNED_OUTRIGHT"]),
        },
    ),
    num_children=st.integers(min_value=0, max_value=3),
    wage=st.integers(min_value=0, max_value=10**6),
)
def test_uk_situation_holds_exactly_the_prompted_facts(
    adult_inputs, household_inputs, num_children, wage
):
    from policybench.prompts import describe_household, describe_person

    scenario = Scenario(
        id="uk",
        country="uk",
        state="SCOTLAND",
        filing_status=None,
        adults=[
            Person(name="adult1", age=40, employment_income=wage, inputs=adult_inputs)
        ],
        children=[
            Person(
                name=f"child{i + 1}",
                age=17,
                employment_income=0.0,
                inputs={"current_education": "POST_SECONDARY"},
            )
            for i in range(num_children)
        ],
        household_inputs=household_inputs,
        year=2026,
    )

    situation = scenario.to_pe_uk_situation(prefix="s__")
    prompt = describe_household(scenario)

    people = situation["people"]
    assert set(people) == {f"s__{p.name}" for p in scenario.all_people}
    adult = people["s__adult1"]
    structural = {"age", "employment_income_before_lsr", "is_claimant_or_partner"}
    assert set(adult) == structural | set(adult_inputs)
    assert adult["is_claimant_or_partner"] == {"2026": True}
    assert adult["employment_income_before_lsr"] == {"2026": wage}
    adult_lines = describe_person(scenario.adults[0], country="uk")
    for key, value in adult_inputs.items():
        assert adult[key] == {"2026": value}
        # Every input the situation holds is one the prompt states.
        if key == "is_disabled_for_benefits":
            assert "limited capability for work" in adult_lines
        else:
            label = key.replace("_", " ") if key != "pip_dl_category" else "PIP"
            assert label.split()[0].lower() in adult_lines.lower()
    for i in range(num_children):
        child = people[f"s__child{i + 1}"]
        assert child["is_claimant_or_partner"] == {"2026": False}
        assert child[scenarios_module.UK_EDUCATION_ENTRY_FIELD] == {
            "2026": scenarios_module.UK_EDUCATION_ENTRY_AGE
        }
        assert "age when the current education or training began: 16" in prompt
    (benunit,) = situation["benunits"].values()
    (household,) = situation["households"].values()
    assert benunit["members"] == household["members"] == list(people)
    assert benunit["is_married"] == {"2026": False}
    expected_household = {"members", "region", *household_inputs}
    if household_inputs.get("tenure_type") == "RENT_PRIVATELY":
        expected_household.add("brma")
        assert "Broad Rental Market Area" in prompt
    assert set(household) == expected_household
    assert household["region"] == {"2026": "SCOTLAND"}


def test_uk_situation_rejects_inputs_the_prompt_cannot_show():
    base = dict(
        id="uk",
        country="uk",
        state="WALES",
        filing_status=None,
        year=2026,
    )
    hidden = Scenario(
        **base,
        adults=[
            Person(
                name="adult1",
                age=70,
                employment_income=0.0,
                inputs={"state_pension_reported": 9_000.0},
            )
        ],
    )
    with pytest.raises(ValueError, match="inputs the prompt does not show"):
        hidden.to_pe_uk_situation()
    tax_unit = Scenario(
        **base,
        adults=[Person(name="adult1", age=40, employment_income=0.0)],
        tax_unit_inputs={"anything": 1},
    )
    with pytest.raises(ValueError, match="tax-unit or benefit inputs"):
        tax_unit.to_pe_uk_situation()


def _uk_renter(**overrides) -> Scenario:
    fields = dict(
        id="uk",
        country="uk",
        state="SCOTLAND",
        filing_status=None,
        adults=[Person(name="adult1", age=40, employment_income=15_095.1591796875)],
        household_inputs={"tenure_type": "RENT_PRIVATELY", "rent": 7_200.4},
        year=2026,
    )
    fields.update(overrides)
    return Scenario(**fields)


def test_uk_private_renters_get_their_region_brma_in_prompt_and_reference():
    from policybench.prompts import describe_household

    scenario = _uk_renter()
    (household,) = scenario.to_pe_uk_situation()["households"].values()
    assert household["brma"] == {"2026": "GREATER_GLASGOW"}
    assert (
        "Broad Rental Market Area (for the Local Housing Allowance): Greater Glasgow"
        in describe_household(scenario)
    )

    stated = _uk_renter(
        household_inputs={"tenure_type": "RENT_PRIVATELY", "brma": "LOTHIAN"}
    )
    (household,) = stated.to_pe_uk_situation()["households"].values()
    assert household["brma"] == {"2026": "LOTHIAN"}

    owner = _uk_renter(household_inputs={"tenure_type": "OWNED_OUTRIGHT"})
    (household,) = owner.to_pe_uk_situation()["households"].values()
    assert "brma" not in household
    assert "Broad Rental Market Area" not in describe_household(owner)

    with pytest.raises(ValueError, match="no Broad Rental Market Area"):
        _uk_renter(state="ATLANTIS").to_pe_uk_situation()


def test_a_loaded_uk_manifest_gives_prompt_and_reference_the_same_facts(tmp_path):
    from policybench.prompts import describe_household

    # A manifest written before the conventions: unrounded amounts, no BRMA.
    manifest = tmp_path / "scenarios.csv"
    scenario_manifest([_uk_renter()]).to_csv(manifest, index=False)
    (loaded,) = load_scenarios_from_manifest(manifest)
    assert loaded.adults[0].employment_income == 15_095.1591796875

    situation = loaded.to_pe_uk_situation()
    (person,) = situation["people"].values()
    (household,) = situation["households"].values()
    prompt = describe_household(loaded)
    assert person["employment_income_before_lsr"] == {"2026": 15_095.0}
    assert "gross wages and salaries: £15,095" in prompt
    assert household["rent"] == {"2026": 7_200.0}
    assert "rent: £7,200" in prompt
    assert household["brma"] == {"2026": "GREATER_GLASGOW"}
    assert "Greater Glasgow" in prompt


@pytest.mark.parametrize("entry_age", [18, 19])
def test_an_explicit_uk_education_entry_age_is_kept_and_stated(entry_age):
    from policybench.prompts import describe_household

    scenario = _uk_renter(
        children=[
            Person(
                name="child1",
                age=19,
                employment_income=0.0,
                inputs={
                    "current_education": "POST_SECONDARY",
                    scenarios_module.UK_EDUCATION_ENTRY_FIELD: entry_age,
                },
            )
        ]
    )
    child = scenario.to_pe_uk_situation()["people"]["child1"]
    assert child[scenarios_module.UK_EDUCATION_ENTRY_FIELD] == {"2026": entry_age}
    assert (
        f"age when the current education or training began: {entry_age}"
        in describe_household(scenario)
    )


def test_uk_situation_rejects_household_inputs_the_prompt_cannot_show():
    hidden = _uk_renter(
        household_inputs={
            "tenure_type": "OWNED_OUTRIGHT",
            "bus_fare_spending_reported": 300.0,
        }
    )
    assert scenarios_module.is_excluded_prompt_input_name("bus_fare_spending_reported")
    with pytest.raises(ValueError, match="household inputs the prompt does not show"):
        hidden.to_pe_uk_situation()


uk_numbers = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False)


@settings(max_examples=100, deadline=None)
@given(
    wage=uk_numbers,
    savings=uk_numbers,
    rent=uk_numbers,
    tenure=st.sampled_from(["RENT_PRIVATELY", "OWNED_OUTRIGHT"]),
    child_in_education=st.booleans(),
)
def test_canonical_uk_scenario_is_idempotent(
    wage, savings, rent, tenure, child_in_education
):
    scenario = _uk_renter(
        adults=[
            Person(
                name="adult1",
                age=40,
                employment_income=wage,
                inputs={"savings_interest_income": savings, "gender": "FEMALE"},
            )
        ],
        children=[
            Person(
                name="child1",
                age=17,
                employment_income=0.0,
                inputs={"current_education": "POST_SECONDARY"}
                if child_in_education
                else {},
            )
        ],
        household_inputs={"tenure_type": tenure, "rent": rent},
    )
    once = scenarios_module.canonical_uk_scenario(scenario)
    twice = scenarios_module.canonical_uk_scenario(once)
    assert scenarios_module.scenario_to_dict(once) == scenarios_module.scenario_to_dict(
        twice
    )
    # The original is untouched.
    assert scenario.adults[0].employment_income == wage


@pytest.mark.slow
def test_pe_uk_reads_a_prompted_couple_as_an_unmarried_couple():
    """The prompt says two adults are a couple, not married. PE-UK would
    otherwise presume a 37/18 pair to be a parent and child, and presume any
    couple married (scenario_056 and the Marriage Allowance cells)."""
    from policyengine_uk import Simulation

    scenario = Scenario(
        id="uk",
        country="uk",
        state="WALES",
        filing_status=None,
        adults=[
            Person(name="adult1", age=37, employment_income=30_000.0),
            Person(name="adult2", age=18, employment_income=0.0),
        ],
        household_inputs={"tenure_type": "OWNED_OUTRIGHT"},
        year=2026,
    )
    sim = Simulation(situation=scenario.to_pe_uk_situation())
    assert bool(sim.calculate("is_couple", 2026)[0])
    assert not bool(sim.calculate("is_married", 2026)[0])
    assert float(sim.calculate("marriage_allowance", 2026).sum()) == 0


def test_uk_situation_rejects_us_scenarios():
    scenario = Scenario(
        id="us",
        state="CA",
        filing_status="single",
        adults=[Person(name="adult1", age=40, employment_income=1.0)],
    )
    with pytest.raises(ValueError, match="only supported for UK"):
        scenario.to_pe_uk_situation()


@settings(max_examples=500, deadline=None)
@given(
    value=st.floats(
        min_value=-1e7, max_value=1e7, allow_nan=False, allow_infinity=False
    )
)
def test_uk_rounding_keeps_the_displayed_number(value):
    from policybench.prompts import _format_input_line

    rounded = scenarios_module.round_uk_prompt_number(value)
    assert rounded == int(rounded)
    if rounded == 0:
        # Extraction leaves an amount shown as £0 (or £-0) unlisted, which the
        # prompt reads as 0.
        assert scenarios_module._uk_promptable_value(value) is None
        return
    # The prompt shows the rounded value exactly as it showed the raw one, so
    # the reference uses the number the models read.
    assert _format_input_line("savings", value, country="uk") == _format_input_line(
        "savings", rounded, country="uk"
    )


def test_uk_promptable_values_are_whole_and_drop_amounts_shown_as_zero():
    assert scenarios_module._uk_promptable_value(15_095.16) == 15_095.0
    assert scenarios_module._uk_promptable_value(-107_891.4) == -107_891.0
    assert scenarios_module._uk_promptable_value(0.4) is None
    assert scenarios_module._uk_promptable_value(0.6) == 1.0


def test_canonical_uk_person_keeps_explicit_zeros_and_rates():
    from policybench.prompts import describe_person

    person = Person(
        name="adult1",
        age=66,
        employment_income=0.0,
        inputs={
            "months_since_last_birthday": 0,
            "full_rate_vat_expenditure_rate": 0.25,
            "savings_interest_income": 0.4,
        },
    )
    canonical = scenarios_module.canonical_uk_person(person)
    # An explicit zero is a stated fact: dropping it would let PE-UK use its
    # own default (six months), moving the date of birth.
    assert canonical.inputs["months_since_last_birthday"] == 0.0
    assert canonical.inputs["full_rate_vat_expenditure_rate"] == 0.25
    assert canonical.inputs["savings_interest_income"] == 0.0
    lines = describe_person(person, country="uk")
    assert "- months since last birthday: 0" in lines
    assert "- savings interest income: £0" in lines


def test_canonical_uk_rate_is_the_rate_the_prompt_shows():
    from policybench.prompts import describe_household

    scenario = _uk_renter(
        household_inputs={
            "tenure_type": "OWNED_OUTRIGHT",
            "full_rate_vat_expenditure_rate": 0.123456789,
        }
    )
    canonical = scenarios_module.canonical_uk_scenario(scenario)
    assert canonical.household_inputs["full_rate_vat_expenditure_rate"] == 0.1235
    assert "full-rate VAT expenditure share: 0.1235" in describe_household(scenario)
    situation = scenario.to_pe_uk_situation()
    (household,) = situation["households"].values()
    assert household["full_rate_vat_expenditure_rate"] == {"2026": 0.1235}


@settings(max_examples=300, deadline=None)
@given(
    rate=st.one_of(
        st.floats(min_value=-10, max_value=10, allow_nan=False, allow_infinity=False),
        # Around the thousands separator and .4g's switch to exponent form.
        st.floats(
            min_value=-200_000,
            max_value=200_000,
            allow_nan=False,
            allow_infinity=False,
        ),
        st.sampled_from(
            [999.95, 1_000.0, 1_234.5, -1_234.5, 9_999.4, 9_999.6, 12_345.0]
        ),
    )
)
def test_uk_prompt_rate_round_trips_through_its_display(rate):
    stored = scenarios_module.round_uk_prompt_rate(rate)
    # The prompt's format prints the stored value exactly, and storing is
    # idempotent, so the reference and the prompt hold the same rate.
    assert float(f"{stored:,.4g}".replace(",", "")) == stored
    assert f"{stored:,.4g}" == f"{rate:,.4g}"
    assert scenarios_module.round_uk_prompt_rate(stored) == stored


def test_canonical_uk_person_states_statuses_pe_uk_would_impute():
    from policybench.prompts import describe_person

    teenager = Person(name="child1", age=17, employment_income=0.0)
    canonical = scenarios_module.canonical_uk_person(teenager)
    # PE-UK imputes non-advanced education at 17; the prompt's rule is that an
    # unlisted status is false.
    assert canonical.inputs["current_education"] == "NOT_IN_EDUCATION"
    assert scenarios_module.UK_EDUCATION_ENTRY_FIELD not in canonical.inputs
    assert "- current education: not in education or training" in describe_person(
        teenager, country="uk"
    )
    assert (
        "current_education"
        not in scenarios_module.canonical_uk_person(
            Person(name="child1", age=12, employment_income=0.0)
        ).inputs
    )

    trader = Person(
        name="adult1",
        age=40,
        employment_income=0.0,
        inputs={"self_employment_income": 3_900.0},
    )
    canonical = scenarios_module.canonical_uk_person(trader)
    assert canonical.inputs[scenarios_module.UK_GAINFUL_SELF_EMPLOYMENT_FIELD] is False
    assert (
        "- determined to be in gainful self-employment for Universal Credit: no"
        in describe_person(trader, country="uk")
    )
    stated = scenarios_module.canonical_uk_person(
        Person(
            name="adult1",
            age=40,
            employment_income=0.0,
            inputs={
                "self_employment_income": 3_900.0,
                scenarios_module.UK_GAINFUL_SELF_EMPLOYMENT_FIELD: True,
            },
        )
    )
    assert stated.inputs[scenarios_module.UK_GAINFUL_SELF_EMPLOYMENT_FIELD] is True


def test_describe_person_and_describe_household_agree_for_uk():
    from policybench.prompts import describe_household, describe_person

    scenario = _uk_renter(
        adults=[
            Person(
                name="adult1",
                age=40,
                employment_income=15_095.16,
                inputs={"self_employment_income": 3_900.4},
            )
        ],
        children=[Person(name="child1", age=17, employment_income=0.0)],
    )
    household = describe_household(scenario)
    for person in scenario.all_people:
        assert describe_person(person, country="uk") in household


@pytest.mark.slow
def test_pe_uk_applies_no_minimum_income_floor_without_a_determination():
    from policyengine_uk import Simulation

    scenario = _uk_renter(
        adults=[
            Person(
                name="adult1",
                age=40,
                employment_income=0.0,
                inputs={"self_employment_income": 3_900.0},
            )
        ],
        household_inputs={"tenure_type": "OWNED_OUTRIGHT"},
    )
    sim = Simulation(situation=scenario.to_pe_uk_situation())
    assert not bool(sim.calculate("uc_mif_applies", 2026).any())
    assert float(sim.calculate("universal_credit", 2026).sum()) > 0
