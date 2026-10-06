"""Offline contract tests; the frozen CSV is input evidence, never recomputed."""

import csv
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from policybench import prompt_contract_v2 as v2
from policybench.prompt_contract_v2 import (
    CONTRACT_VERSION,
    ContractInputError,
    FactProvenance,
    contract_identity,
    render_household_contract,
)
from policybench.scenarios import Person, Scenario

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = (
    ROOT
    / "paper/snapshot/20260501/runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace/scenarios.csv"
)
SNAPSHOT_SHA256 = "71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a"
GOLDEN = Path(__file__).parent / "fixtures/prompt_contract_v2/scenario_074.txt"


@pytest.fixture(scope="module")
def frozen_scenarios():
    """Read checked-in inputs without the engine or coercing their JSON types."""
    assert hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest() == SNAPSHOT_SHA256
    result = {}
    for row in csv.DictReader(SNAPSHOT.open()):
        data = json.loads(row["scenario_json"])
        for group in ("adults", "children"):
            data[group] = [Person(**person) for person in data[group]]
        result[data["id"]] = Scenario(**data)
    return result


def render(scenario, **kwargs):
    return render_household_contract(
        scenario, policyengine_us_version="2.15.17", **kwargs
    )


def test_real_ssdi_fixture_preserves_income_and_exposes_absent_duration(
    frozen_scenarios,
):
    result = render(frozen_scenarios["scenario_074"])
    assert (
        "Social Security disability income [social_security_disability]: $33,640.0"
        in result.text
    )
    assert (
        "SSDI benefit months as of January 1 "
        "[months_receiving_social_security_disability]: "
        "unknown (not supplied; provenance: unknown)"
    ) in result.text
    assert (
        "person.head.months_receiving_social_security_disability"
        in result.unknown_facts
    )
    assert "0 months" not in result.text


def test_real_general_disability_is_not_an_ssi_or_tax_disability_claim(
    frozen_scenarios,
):
    result = render(frozen_scenarios["scenario_008"])
    assert (
        "General disability indicator (survey characteristic) [is_disabled]: yes"
        in result.text
    )
    assert (
        "[meets_ssi_disability_criteria]: unknown (not supplied; provenance: unknown)"
        in result.text
    )
    assert "[is_permanently_and_totally_disabled]: unknown" in result.text
    assert "[is_incapable_of_self_care]: unknown" in result.text
    assert "- is disabled" not in result.text


@pytest.mark.parametrize("months", [0, 1, 23, 24, 120, 2**53 + 1])
def test_integer_status_is_exact_not_currency_or_boolean(
    simple_single_scenario, months
):
    simple_single_scenario.adults[0].inputs[
        "months_receiving_social_security_disability"
    ] = months
    result = render(simple_single_scenario)
    assert (
        f"[months_receiving_social_security_disability]: {months:,} months"
        in result.text
    )
    assert f"${months:,} months" not in result.text


@pytest.mark.parametrize(
    "value", [True, False, 24.0, 24.5, "24", -1, float("nan"), [], {}]
)
def test_integer_status_rejects_incompatible_types(simple_single_scenario, value):
    simple_single_scenario.adults[0].inputs[
        "months_receiving_social_security_disability"
    ] = value
    with pytest.raises(
        ContractInputError, match="months_receiving_social_security_disability"
    ):
        render(simple_single_scenario)


@pytest.mark.parametrize("value", [0, 1, "false", "true", 0.0, [], {}])
def test_boolean_disability_does_not_coerce_truthiness(simple_single_scenario, value):
    simple_single_scenario.adults[0].inputs["meets_ssi_disability_criteria"] = value
    with pytest.raises(ContractInputError, match="meets_ssi_disability_criteria"):
        render(simple_single_scenario)


def test_explicit_false_with_unknown_provenance_is_not_observed(simple_single_scenario):
    simple_single_scenario.adults[0].inputs["meets_ssi_disability_criteria"] = False
    result = render(simple_single_scenario)
    assert (
        "[meets_ssi_disability_criteria]: no (supplied value; "
        "provenance: unknown; not an observed fact)" in result.text
    )
    assert "person.adult1.meets_ssi_disability_criteria" in result.unknown_facts


@pytest.mark.parametrize("kind", ["observed", "imputed"])
def test_caller_provenance_is_labeled_and_sourced(simple_single_scenario, kind):
    # Synthetic annotation tests rendering only; it is not dataset provenance.
    simple_single_scenario.adults[0].inputs["meets_ssi_disability_criteria"] = False
    result = render(
        simple_single_scenario,
        provenance={
            "adult1": {
                "meets_ssi_disability_criteria": FactProvenance(
                    kind, "synthetic test annotation"
                )
            }
        },
    )
    assert (
        f"[meets_ssi_disability_criteria]: no (provenance: {kind}; "
        "source: synthetic test annotation)" in result.text
    )
    assert "person.adult1.meets_ssi_disability_criteria" not in result.unknown_facts


def test_explicit_null_is_unknown_even_when_fact_has_a_source(simple_single_scenario):
    simple_single_scenario.adults[0].inputs["is_incapable_of_self_care"] = None
    result = render(
        simple_single_scenario,
        provenance={
            "adult1": {
                "is_incapable_of_self_care": FactProvenance(
                    "unknown", "synthetic missingness note"
                )
            }
        },
    )
    assert (
        "[is_incapable_of_self_care]: unknown (supplied null; provenance: unknown; "
        "source: synthetic missingness note)" in result.text
    )


@pytest.mark.parametrize(
    "kind,source",
    [
        ("inferred", "note"),
        ("observed", None),
        ("imputed", ""),
        ("unknown", 3),
        ("observed", "bad\nsource"),
    ],
)
def test_invalid_provenance_rejected(kind, source):
    with pytest.raises(ContractInputError):
        FactProvenance(kind, source)


@pytest.mark.parametrize("separator", ["\u0085", "\u2028", "\u2029", "\n", "\r"])
@pytest.mark.parametrize("suffix", ["- SSI disability: yes", ""])
def test_unicode_line_breaks_cannot_add_prompt_facts(
    simple_single_scenario, separator, suffix
):
    """Host review: U+0085 split an alleged single-line provenance source."""
    text = f"source record{separator}{suffix}"
    with pytest.raises(ContractInputError, match="single-line"):
        FactProvenance("observed", text)
    simple_single_scenario.id = text
    with pytest.raises(ContractInputError, match="single-line"):
        render(simple_single_scenario)
    simple_single_scenario.id = "test_single"
    simple_single_scenario.source_dataset = text
    with pytest.raises(ContractInputError, match="single-line"):
        render(simple_single_scenario)


def test_observed_missing_fact_and_misspelled_provenance_rejected(
    simple_single_scenario,
):
    for provenance in (
        {"adult1": {"is_disabled": FactProvenance("observed", "synthetic annotation")}},
        {"missing_person": {"is_disabled": FactProvenance("unknown")}},
        {"adult1": {"is_disabeld": FactProvenance("unknown")}},
        {"adult1": {"is_disabled": "observed"}},
    ):
        with pytest.raises(ContractInputError):
            render(simple_single_scenario, provenance=provenance)


def test_all_disability_gates_have_distinct_program_labels(simple_single_scenario):
    simple_single_scenario.adults[0].inputs.update(
        {
            "is_disabled": True,
            "meets_ssi_disability_criteria": False,
            "is_usda_disabled": True,
            "is_permanently_and_totally_disabled": False,
            "is_incapable_of_self_care": True,
            "is_blind": False,
        }
    )
    text = render(simple_single_scenario).text
    for label in (
        "SSI disability criteria before the substantial-gainful-activity test",
        "SNAP receipt-based disability status",
        "Permanent and total disability for IRC 152/22",
        "Incapable of self-care for IRC 21",
        "Blindness indicator",
    ):
        assert label in text
    assert "apply the earnings test separately" in text
    assert "does not establish SSI disability" in text


def test_preamble_freezes_takeup_history_and_federal_ssi_boundary(
    simple_single_scenario,
):
    text = render(simple_single_scenario).text
    assert (
        "eligible TANF/MOE noncash benefits used for SNAP categorical eligibility"
        in text
    )
    assert "does not create substantive eligibility or historical entitlement" in text
    assert (
        "Social Security, SSDI, and veterans payments and histories "
        "are supplied inputs only" in text
    )
    assert "federal SSI only" in text
    assert "Medicare eligibility is evaluated on January 1" in text
    assert "Unknown facts and unknown provenance are never observed negatives" in text
    assert "unlisted integer inputs" in text


def test_employer_premiums_are_employer_paid_with_exact_precision(
    simple_single_scenario,
):
    simple_single_scenario.adults[0].inputs["employer_sponsored_insurance_premiums"] = (
        8389.275390625
    )
    text = render(simple_single_scenario).text
    assert (
        "Employer-paid insurance premiums (not included in stated wages) "
        "[employer_sponsored_insurance_premiums]: $8,389.275390625" in text
    )


def test_weekly_hours_absent_null_supplied_and_conflicting(simple_single_scenario):
    person = simple_single_scenario.adults[0]
    assert (
        "Weekly hours: 0 hours/week (contract assumption; "
        "no weekly-hours input supplied)" in render(simple_single_scenario).text
    )
    person.inputs["hours_worked_last_week"] = 37.5
    assert (
        "[hours_worked_last_week]: 37.5 hours/week"
        in render(simple_single_scenario).text
    )
    person.inputs["weekly_hours_worked"] = 40
    with pytest.raises(ContractInputError, match="conflicting weekly-hours"):
        render(simple_single_scenario)
    person.inputs["weekly_hours_worked"] = 37.5
    assert (
        "[weekly_hours_worked]: 37.5 hours/week" in render(simple_single_scenario).text
    )
    person.inputs = {"hours_worked_last_week": None}
    text = render(simple_single_scenario).text
    assert "[hours_worked_last_week]: unknown" in text
    assert "Weekly hours: 0" not in text


@pytest.mark.parametrize("value", [True, "40", -1, 169, float("inf"), float("nan")])
def test_invalid_hours_rejected(simple_single_scenario, value):
    simple_single_scenario.adults[0].inputs["weekly_hours_worked"] = value
    with pytest.raises(ContractInputError, match="weekly_hours_worked"):
        render(simple_single_scenario)


def test_unknown_fields_are_retained_without_guessed_meaning_or_units(
    simple_single_scenario,
):
    simple_single_scenario.adults[0].inputs.update(
        {"new_status": 24, "new_enum": "NONE", "new_null": None}
    )
    result = render(simple_single_scenario)
    assert (
        "[new_status]: 24 (unsupported input; meaning and units not interpreted)"
        in result.text
    )
    assert (
        '[new_enum]: "NONE" (unsupported input; meaning and units not interpreted)'
        in result.text
    )
    assert "person.adult1.new_status" in result.unsupported_inputs
    assert "person.adult1.new_null" in result.unknown_facts


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), {"2026": True}, [24], object()]
)
def test_unsupported_non_scalar_or_nonfinite_values_fail_closed(
    simple_single_scenario, value
):
    simple_single_scenario.adults[0].inputs["new_status"] = value
    with pytest.raises(ContractInputError, match="new_status"):
        render(simple_single_scenario)


def test_wrong_entity_and_conflicting_takeup_rejected(simple_single_scenario):
    simple_single_scenario.tax_unit_inputs["meets_ssi_disability_criteria"] = True
    with pytest.raises(ContractInputError, match="person input"):
        render(simple_single_scenario)
    simple_single_scenario.tax_unit_inputs = {}
    simple_single_scenario.adults[0].inputs["takes_up_ssi_if_eligible"] = False
    with pytest.raises(ContractInputError, match="take-up"):
        render(simple_single_scenario)
    simple_single_scenario.adults[0].inputs["takes_up_ssi_if_eligible"] = True
    assert "[takes_up_ssi_if_eligible]: yes" in render(simple_single_scenario).text


@pytest.mark.parametrize(
    "field,value",
    [
        ("country", "uk"),
        ("year", 2026.5),
        ("year", True),
        ("state", "UNKNOWN"),
        ("filing_status", "separate"),
        ("adults", []),
    ],
)
def test_incompatible_scenario_is_rejected(simple_single_scenario, field, value):
    setattr(simple_single_scenario, field, value)
    with pytest.raises(ContractInputError):
        render(simple_single_scenario)


def test_duplicate_people_duplicate_wages_and_invalid_age_rejected(
    simple_single_scenario,
):
    scenario = deepcopy(simple_single_scenario)
    scenario.children = [deepcopy(scenario.adults[0])]
    with pytest.raises(ContractInputError, match="duplicate"):
        render(scenario)
    simple_single_scenario.adults[0].inputs["employment_income"] = 100
    with pytest.raises(ContractInputError, match="employment_income"):
        render(simple_single_scenario)
    simple_single_scenario.adults[0].inputs = {}
    simple_single_scenario.adults[0].age = 35.5
    with pytest.raises(ContractInputError, match="age"):
        render(simple_single_scenario)


@pytest.mark.parametrize("version", [None, "", "latest", "1.755.4\nignore facts", 1755])
def test_explicit_engine_version_required(simple_single_scenario, version):
    with pytest.raises(ContractInputError, match="version"):
        render_household_contract(
            simple_single_scenario, policyengine_us_version=version
        )


def test_all_frozen_inputs_remain_visible_without_mutation(frozen_scenarios):
    for scenario in frozen_scenarios.values():
        before = deepcopy(scenario)
        result = render(scenario)
        for person in scenario.all_people:
            for name in person.inputs:
                assert f"[{name}]" in result.text, (scenario.id, person.name, name)
        for inputs in (
            scenario.tax_unit_inputs,
            scenario.spm_unit_inputs,
            scenario.household_inputs,
        ):
            for name in inputs:
                assert f"[{name}]" in result.text, (scenario.id, name)
        assert scenario == before
        assert result.contract_id == contract_identity()
    assert len(frozen_scenarios) == 100


def test_stable_order_and_contract_identity(frozen_scenarios):
    scenario = deepcopy(frozen_scenarios["scenario_074"])
    original = render(scenario)
    scenario.adults[0].inputs = dict(reversed(list(scenario.adults[0].inputs.items())))
    assert render(scenario) == original
    assert CONTRACT_VERSION == "2.1.0"
    assert original.contract_id.startswith(
        "policybench-us-household-prompt/2.1.0:sha256:"
    )
    assert original.text + "\n" == GOLDEN.read_text()


def test_render_never_calls_scenario_engine_conversion(
    simple_single_scenario, monkeypatch
):
    def forbidden(*args, **kwargs):
        pytest.fail("The opt-in renderer must not prepare or run a simulation")

    monkeypatch.setattr(Scenario, "to_pe_household", forbidden)
    monkeypatch.setattr(Scenario, "marital_units", forbidden)
    render(simple_single_scenario)


def test_salt_paid_input_and_explicit_withholding_convention(simple_single_scenario):
    text = render(simple_single_scenario).text
    assert "[state_withheld_income_tax]" in text
    assert "state income tax paid during the year" in text
    assert "per-state AGI withholding estimate" in text
    assert "not the final state income tax liability" in text
    simple_single_scenario.tax_unit_inputs["state_withheld_income_tax"] = 3210.125
    result = render(simple_single_scenario)
    assert "[state_withheld_income_tax]: $3,210.125" in result.text
    assert "tax_unit.state_withheld_income_tax" not in result.unsupported_inputs
    assert simple_single_scenario.tax_unit_inputs == {
        "state_withheld_income_tax": 3210.125
    }


def test_salt_known_field_on_wrong_entity_fails(simple_single_scenario):
    simple_single_scenario.adults[0].inputs["state_withheld_income_tax"] = 123
    with pytest.raises(ContractInputError, match="tax_unit input"):
        render(simple_single_scenario)


def test_medicare_convention_and_explicit_enrollment_and_premium(
    simple_single_scenario,
):
    person = simple_single_scenario.adults[0]
    person.age = 69
    text = render(simple_single_scenario).text
    assert "[takes_up_medicare_if_eligible]: yes if eligible" in text
    assert "[medicare_part_b_premium]" in text
    assert "IRMAA" in text and "Medicare Savings Program" in text
    assert "[medical_expense_health_insurance_premiums]" in text
    person.inputs.update(takes_up_medicare_if_eligible=False, medicare_part_b_premium=0)
    result = render(simple_single_scenario)
    assert "[takes_up_medicare_if_eligible]: no" in result.text
    assert "[medicare_part_b_premium]: $0" in result.text
    assert not any("medicare_part_b" in path for path in result.unsupported_inputs)


@pytest.mark.parametrize(
    "state,program",
    [
        ("MN", "MN Paid Leave"),
        ("CO", "CO FAMLI"),
        ("MA", "MA PFML"),
        ("NY", "NY PFL/DBL"),
        ("DE", "DE Paid Leave"),
        ("ME", "ME PFML"),
        ("VT", "VT child-care contribution"),
        ("WA", "WA PFML"),
    ],
)
def test_optional_employee_share_is_a_stated_employer_choice(
    simple_single_scenario, state, program
):
    simple_single_scenario.state = state
    text = render(simple_single_scenario).text
    assert program in text
    assert "employer withholds the full employee share" in text
    simple_single_scenario.adults[0].inputs[
        "state_paid_leave_employee_share_withheld"
    ] = False
    text = render(simple_single_scenario).text
    assert "employer pays the employee share" in text


def test_premium_payer_labels_and_medical_total_override(simple_single_scenario):
    simple_single_scenario.adults[0].inputs.update(
        employer_sponsored_insurance_premiums=8000,
        pre_tax_health_insurance_premiums=1200,
        health_insurance_premiums_without_medicare_part_b=600,
        health_insurance_premiums=3034.8,
    )
    text = render(simple_single_scenario).text
    assert (
        "Employee pre-tax health insurance premiums "
        "[pre_tax_health_insurance_premiums]: $1,200" in text
    )
    assert "Employee after-tax health insurance premiums excluding Part B" in text
    assert "Employee after-tax health insurance premiums including Part B" in text
    assert (
        "Do not subtract employer-paid or employee after-tax premiums from FICA wages"
        in text
    )
    assert "nonzero health_insurance_premiums overrides the component sum" in text


def test_loaded_surviving_spouse_and_cash_source(frozen_scenarios):
    text = render(frozen_scenarios["scenario_000"]).text
    assert "Spouse death year [spouse_death_year]: 2025" in text
    assert (
        "Dependent child lives in the home [dependent_child_lives_in_home]: no" in text
    )
    assert "declared convention" in text
    text = render(frozen_scenarios["scenario_030"]).text
    assert "cash gifts from friends or relatives outside the household" in text
    assert "[financial_assistance]" in text


def test_loaded_facts_allow_supplied_details_without_inference(simple_single_scenario):
    simple_single_scenario.adults[0].inputs.update(
        is_surviving_spouse=True,
        spouse_death_year=2024,
        dependent_child_lives_in_home=True,
        financial_assistance=1500,
        financial_assistance_source="cash gift from a sister outside the household",
    )
    text = render(simple_single_scenario).text
    assert "[spouse_death_year]: 2024" in text
    assert "[dependent_child_lives_in_home]: yes" in text
    assert "cash gift from a sister outside the household" in text


def test_v2_output_wording_is_gated_and_has_common_income_tax_scope():
    raw = json.loads((ROOT / "policybench/benchmark_specs.json").read_text())
    definitions = v2.v2_output_definitions()
    scope = "Do not add a dependent's separate income tax return"
    ids = {
        "federal_income_tax_before_refundable_credits",
        "federal_refundable_credits",
        "state_income_tax_before_refundable_credits",
        "state_refundable_credits",
        "local_income_tax",
    }
    for entry in raw["specs"]["policybench"]["countries"]["us"]:
        if entry["id"] in ids:
            assert scope in definitions[entry["id"]]
            assert scope not in entry["prompt"]
        if entry["id"] == "payroll_tax":
            assert (
                "employee shares the employer chooses to withhold"
                in definitions[entry["id"]]
            )
            assert (
                "employee shares the employer chooses to withhold"
                not in entry["prompt"]
            )


def test_required_facts_rule_is_explicit(simple_single_scenario):
    text = render(simple_single_scenario).text
    assert "Every input read by a scored reference" in text
    assert "more than $1" in text
    assert "stated fact or an explicit convention" in text
    assert "Legacy sweep findings report gaps; they do not certify readiness" in text


def test_common_scope_does_not_add_local_tax_to_other_outputs():
    definitions = v2.v2_output_definitions()
    for name, definition in definitions.items():
        if name != "local_income_tax":
            assert "explicitly applicable local wage" not in definition.lower()


def test_all_frozen_insurance_premiums_have_payer_labels(frozen_scenarios):
    for scenario in frozen_scenarios.values():
        rendered = render(scenario)
        for person in scenario.all_people:
            for name in person.inputs:
                if "insurance_premiums" in name:
                    assert (
                        f"person.{person.name}.{name}"
                        not in rendered.unsupported_inputs
                    )
                    line = next(
                        line
                        for line in rendered.text.splitlines()
                        if f"[{name}]" in line
                    )
                    assert any(
                        payer in line
                        for payer in (
                            "Employer-paid",
                            "Employee pre-tax",
                            "Employee after-tax",
                        )
                    )


def test_v1_spec_bytes_and_resume_fingerprint_are_preserved():
    from policybench.eval_no_tools import _package_file_sha256

    assert _package_file_sha256("benchmark_specs.json") == (
        "ce233f8cbb0549b33469b5929fc6df3cd5d064c727529afafe26ff2da7970cc5"
    )


def test_sales_tax_estimates_have_named_conventions(simple_single_scenario):
    text = render(simple_single_scenario).text
    assert "[state_sales_tax]" in text and "2025 IRS optional sales-tax table" in text
    assert "[local_sales_tax]" in text and "20% of state_sales_tax" in text


def test_pre_response_hours_are_explicit_and_accept_an_override(simple_single_scenario):
    text = render(simple_single_scenario).text
    assert "[weekly_hours_worked_before_lsr]: 0 hours/week" in text
    simple_single_scenario.adults[0].inputs["weekly_hours_worked_before_lsr"] = 30
    text = render(simple_single_scenario).text
    assert "[weekly_hours_worked_before_lsr]: 30 hours/week" in text
    assert "[weekly_hours_worked_before_lsr]: 0" not in text


def test_all_three_hours_inputs_must_agree(simple_single_scenario):
    simple_single_scenario.adults[0].inputs.update(
        hours_worked_last_week=30,
        weekly_hours_worked=30,
        weekly_hours_worked_before_lsr=20,
    )
    with pytest.raises(ContractInputError, match="conflicting weekly-hours"):
        render(simple_single_scenario)


def test_joint_survivor_convention_does_not_kill_the_listed_spouse(frozen_scenarios):
    text = render(frozen_scenarios["scenario_111"]).text
    assert "prior deceased spouse" in text
    assert "current listed spouse is living" in text


@pytest.mark.parametrize("name", ["financial_assistance", "state_withheld_income_tax"])
def test_negative_paid_amounts_rejected(simple_single_scenario, name):
    inputs = (
        simple_single_scenario.tax_unit_inputs
        if name == "state_withheld_income_tax"
        else simple_single_scenario.adults[0].inputs
    )
    inputs[name] = -1
    with pytest.raises(ContractInputError, match="nonnegative"):
        render(simple_single_scenario)


def test_payroll_choice_in_state_without_optional_program_is_rejected(
    simple_single_scenario,
):
    simple_single_scenario.adults[0].inputs[
        "state_paid_leave_employee_share_withheld"
    ] = True
    with pytest.raises(ContractInputError, match="no optional employee-share program"):
        render(simple_single_scenario)


def test_future_death_year_is_rejected_without_survivor_indicator(
    simple_single_scenario,
):
    simple_single_scenario.adults[0].inputs["spouse_death_year"] = 2027
    with pytest.raises(ContractInputError, match="future death year"):
        render(simple_single_scenario)
