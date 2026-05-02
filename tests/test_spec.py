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

US_HEADLINE = [
    "federal_income_tax_before_refundable_credits",
    "federal_refundable_credits",
    "payroll_tax",
    "self_employment_tax",
    "state_income_tax_before_refundable_credits",
    "state_refundable_credits",
    "local_income_tax",
    "snap",
    "ssi",
    "tanf",
    "premium_tax_credit",
    "person_wic_eligible",
    "person_medicaid_eligible",
    "person_chip_eligible",
    "person_medicare_eligible",
    "person_head_start_eligible",
    "person_early_head_start_eligible",
    "free_school_meals_eligible",
    "reduced_price_school_meals_eligible",
]


def test_headline_uses_net_income_components_and_coverage_bools():
    outputs = get_output_specs("us", "headline")
    by_id = {output.id: output for output in outputs}

    assert [output.id for output in outputs] == US_HEADLINE
    assert {output.metric_type for output in outputs} == {"amount", "binary"}
    assert "income_tax" not in [output.id for output in outputs]
    assert "adjusted_gross_income" not in [output.id for output in outputs]
    assert "household_state_income_tax" not in [output.id for output in outputs]
    assert by_id["state_income_tax_before_refundable_credits"].net_income_sign == -1
    assert by_id["state_refundable_credits"].net_income_sign == 1
    federal_before = by_id["federal_income_tax_before_refundable_credits"]
    federal_refundable = by_id["federal_refundable_credits"]
    premium_tax_credit = by_id["premium_tax_credit"]
    assert federal_before.pe_variable == "income_tax_before_refundable_credits"
    assert federal_before.net_income_sign == -1
    assert federal_refundable.pe_variable == "income_tax_refundable_credits"
    assert federal_refundable.net_income_sign == 1
    assert "after nonrefundable credits" in federal_before.prompt
    assert "before refundable credits" in federal_before.prompt
    assert "nonrefundable portion of CTC" in federal_before.prompt
    assert "nonrefundable credits actually used" in federal_before.prompt
    assert "refundable federal income tax credits" in federal_refundable.prompt
    assert "EITC" in federal_refundable.prompt
    assert "refundable CTC" in federal_refundable.prompt
    assert "exclude the ACA Premium Tax Credit" in federal_refundable.prompt
    assert premium_tax_credit.pe_variable == "premium_tax_credit"
    assert premium_tax_credit.role == "health"
    assert premium_tax_credit.net_income_sign == 1
    assert "Marketplace health insurance" in premium_tax_credit.prompt
    assert "what the household knows about the plan they selected" in (
        premium_tax_credit.prompt
    )
    assert "benchmark premium" in premium_tax_credit.prompt
    assert "selected plan costs about the same as the local benchmark Silver plan" in (
        premium_tax_credit.prompt
    )
    assert impact_weight_variable_for_output("person_wic_eligible") == "wic"
    assert impact_weight_variable_for_output("head_wic_eligible") == "wic"
    assert impact_weight_variable_for_output("person_medicaid_eligible") == "medicaid"
    assert impact_weight_variable_for_output("head_medicaid_eligible") == "medicaid"
    assert (
        impact_weight_variable_for_output("child1_head_start_eligible") == "head_start"
    )
    assert (
        impact_weight_variable_for_output("child1_early_head_start_eligible")
        == "early_head_start"
    )
    assert (
        impact_weight_variable_for_output("free_school_meals_eligible")
        == "free_school_meals"
    )


def test_head_start_eligibility_expands_only_for_children():
    scenario = Scenario(
        id="mini",
        state="CA",
        filing_status="head_of_household",
        adults=[Person(name="head", age=35, employment_income=50_000)],
        children=[Person(name="child1", age=4, employment_income=0)],
        year=2026,
    )

    assert expand_programs_for_scenario(
        ["person_head_start_eligible", "person_early_head_start_eligible"],
        scenario,
    ) == [
        "child1_head_start_eligible",
        "child1_early_head_start_eligible",
    ]


def test_program_set_parser_supports_current_sets():
    assert parse_program_set(None) == ("policybench", "headline")
    assert parse_program_set("policybench") == ("policybench", "headline")
    assert parse_program_set("headline") == ("policybench", "headline")
    assert get_programs("us") == US_HEADLINE
    assert get_programs("uk", "headline") == [
        "income_tax",
        "national_insurance",
        "capital_gains_tax",
        "child_benefit",
        "universal_credit",
        "pension_credit",
        "pip",
    ]
    with pytest.raises(ValueError, match="Unknown program set"):
        parse_program_set("legacy_extra")


def test_metric_and_impact_metadata_are_spec_driven():
    assert metric_type_for_output("head_medicaid_eligible") == "binary"
    assert (
        net_income_sign_for_output("federal_income_tax_before_refundable_credits") == -1
    )
    assert net_income_sign_for_output("federal_refundable_credits") == 1
    assert net_income_sign_for_output("premium_tax_credit") == 1
    assert net_income_sign_for_output("snap") == 1


def test_find_output_spec_prefers_default_spec_for_overlapping_outputs():
    output = find_output_spec("child_benefit", country="uk")

    assert output is not None
    assert "gross Child Benefit" in output.prompt
    assert "before the High Income Child Benefit Charge" in output.prompt
    assert "do not apply an income test" in output.prompt
    assert "do not subtract HICBC" in output.prompt
    assert "even when HICBC would recover it through tax" in output.prompt
    assert "do not require stated benefit receipt" in output.prompt


def test_unknown_spec_errors_are_clear():
    with pytest.raises(ValueError, match="Unknown benchmark spec"):
        get_benchmark_spec("missing")

    with pytest.raises(ValueError, match="Unknown program set"):
        parse_program_set("v9_headline")

    assert find_output_spec("not_a_real_output") is None
