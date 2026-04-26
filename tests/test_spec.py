"""Tests for benchmark output specifications."""

import pytest

from policybench.config import get_programs
from policybench.scenarios import Person, Scenario
from policybench.spec import (
    expand_programs_for_scenario,
    find_output_spec,
    get_benchmark_spec,
    get_output_specs,
    impact_weight_variable_for_output,
    metric_type_for_output,
    net_income_sign_for_output,
    parse_program_set,
)

US_V2_HEADLINE = [
    "income_tax",
    "payroll_tax",
    "self_employment_tax",
    "household_state_income_tax",
    "local_income_tax",
    "snap",
    "ssi",
    "tanf",
    "wic",
    "person_medicaid_eligible",
    "person_chip_eligible",
    "person_medicare_eligible",
    "person_head_start_eligible",
    "person_early_head_start_eligible",
    "free_school_meals_eligible",
    "reduced_price_school_meals_eligible",
]


def test_v2_headline_uses_net_income_components_and_coverage_bools():
    outputs = get_output_specs("us", "v2_headline")

    assert [output.id for output in outputs] == US_V2_HEADLINE
    assert {output.metric_type for output in outputs} == {"amount", "binary"}
    assert "adjusted_gross_income" not in [output.id for output in outputs]
    assert impact_weight_variable_for_output("person_medicaid_eligible") == "medicaid"
    assert impact_weight_variable_for_output("adult1_medicaid_eligible") == "medicaid"
    assert (
        impact_weight_variable_for_output("child1_head_start_eligible")
        == "head_start"
    )
    assert (
        impact_weight_variable_for_output("child1_early_head_start_eligible")
        == "early_head_start"
    )
    assert (
        impact_weight_variable_for_output("free_school_meals_eligible")
        == "free_school_meals"
    )


def test_v2_supplementary_keeps_derived_eligibility_labels_explicit():
    outputs = get_output_specs("us", "v2_supplementary")
    by_id = {output.id: output for output in outputs}

    school_meals = by_id["household_free_school_meal_eligible"]
    social_security_tax = by_id["person_employee_social_security_tax"]
    additional_medicare_tax = by_id["household_additional_medicare_tax"]

    assert school_meals.pe_variable == "free_school_meals"
    assert school_meals.metric_type == "binary"
    assert school_meals.aggregation == "any_positive"
    assert "benchmark household" in school_meals.prompt
    assert social_security_tax.pe_variable == "employee_social_security_tax"
    assert social_security_tax.aggregation == "person"
    assert social_security_tax.metric_type == "amount"
    assert additional_medicare_tax.pe_variable == "additional_medicare_tax"
    assert additional_medicare_tax.aggregation == "sum"


def test_person_payroll_diagnostics_expand_per_household_member():
    scenario = Scenario(
        id="mini",
        state="CA",
        filing_status="head_of_household",
        adults=[Person(name="adult1", age=35, employment_income=50_000)],
        children=[Person(name="child1", age=8, employment_income=0)],
        year=2025,
    )

    assert expand_programs_for_scenario(
        ["person_employee_social_security_tax", "household_additional_medicare_tax"],
        scenario,
    ) == [
        "adult1_employee_social_security_tax",
        "child1_employee_social_security_tax",
        "household_additional_medicare_tax",
    ]


def test_head_start_eligibility_expands_only_for_children():
    scenario = Scenario(
        id="mini",
        state="CA",
        filing_status="head_of_household",
        adults=[Person(name="adult1", age=35, employment_income=50_000)],
        children=[Person(name="child1", age=4, employment_income=0)],
        year=2025,
    )

    assert expand_programs_for_scenario(
        ["person_head_start_eligible", "person_early_head_start_eligible"],
        scenario,
    ) == [
        "child1_head_start_eligible",
        "child1_early_head_start_eligible",
    ]


def test_program_set_parser_supports_legacy_and_rebuilt_sets():
    assert parse_program_set(None) == ("v2", "headline")
    assert parse_program_set("v1") == ("v1", "headline")
    assert parse_program_set("v2_headline") == ("v2", "headline")
    assert parse_program_set("v2_supplementary") == ("v2", "supplementary")
    assert get_programs("us") == US_V2_HEADLINE
    assert get_programs("uk", "v2_headline") == [
        "income_tax",
        "national_insurance",
        "child_benefit",
        "universal_credit",
        "pension_credit",
        "pip",
    ]


def test_metric_and_impact_metadata_are_spec_driven():
    assert metric_type_for_output("household_medicaid_eligible") == "binary"
    assert net_income_sign_for_output("income_tax") == -1
    assert net_income_sign_for_output("snap") == 1
    assert net_income_sign_for_output("adjusted_gross_income") == 0


def test_unknown_spec_errors_are_clear():
    with pytest.raises(ValueError, match="Unknown benchmark spec"):
        get_benchmark_spec("missing")

    with pytest.raises(ValueError, match="Unknown program set"):
        parse_program_set("v9_headline")

    assert find_output_spec("not_a_real_output") is None
