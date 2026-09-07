"""Offline contract tests; the frozen CSV is input evidence, never recomputed."""

import csv
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

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
        scenario, policyengine_us_version="1.755.4", **kwargs
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
    assert CONTRACT_VERSION == "2.0.0"
    assert original.contract_id.startswith(
        "policybench-us-household-prompt/2.0.0:sha256:"
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
