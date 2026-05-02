"""Tests for scenario generation."""

import json

import pandas as pd
import pytest

import policybench.scenarios as scenarios_module
from policybench.scenarios import (
    SUPPORTED_FILING_STATUSES,
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
        assert scenario.source_dataset == "enhanced_cps"


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


def test_formula_overtime_premium_is_not_prompted_or_sent_to_policyengine():
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
    assert "fsla_overtime_premium" not in head


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
    """Top-level US generation should delegate to the Enhanced CPS loader."""

    def fake_loader():
        return sample_person_frame, 2024

    monkeypatch.setattr(
        "policybench.scenarios.load_enhanced_cps_person_frame", fake_loader
    )
    scenarios = generate_scenarios(n=3, seed=0)

    assert len(scenarios) == 3
    assert all(scenario.metadata["dataset_year"] == 2024 for scenario in scenarios)
    assert all(scenario.source_dataset == "enhanced_cps_2024" for scenario in scenarios)


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
