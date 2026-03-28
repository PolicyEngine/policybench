"""Tests for scenario generation."""

import pandas as pd
import pytest

from policybench.scenarios import (
    SUPPORTED_FILING_STATUSES,
    generate_scenarios,
    scenario_manifest,
    scenarios_from_cps_frame,
)


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
                "household_weight": 2.0,
                "state_code": "CA",
                "filing_status": "HEAD_OF_HOUSEHOLD",
                "age": 35,
                "employment_income": 30_000.0,
                "is_tax_unit_head": True,
            },
            {
                "person_id": 2,
                "household_id": 101,
                "tax_unit_id": 201,
                "spm_unit_id": 301,
                "family_id": 401,
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
                "household_weight": 5.0,
                "state_code": "CO",
                "filing_status": "SINGLE",
                "age": 52,
                "employment_income": 0.0,
                "disability_benefits": 18_000.0,
                "is_disabled": True,
                "is_tax_unit_head": True,
            },
        ]
    )


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
        assert scenario.year == 2025
        assert scenario.source_dataset == "enhanced_cps"


def test_invalid_households_are_filtered(sample_person_frame):
    """Ambiguous or multi-tax-unit households should not be benchmark scenarios."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=3, seed=0)
    household_ids = {scenario.metadata["household_id"] for scenario in scenarios}
    assert 104 not in household_ids
    assert 103 not in household_ids


def test_joint_filers_have_exactly_two_adults(sample_person_frame):
    """Joint filers should map to exactly two adults in promptable scenarios."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=3, seed=0)
    for scenario in scenarios:
        if scenario.filing_status == "joint":
            assert len(scenario.adults) == 2


def test_single_and_hoh_filers_have_exactly_one_adult(sample_person_frame):
    """Single and HoH scenarios should exclude extra unlabeled adults."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=3, seed=0)
    for scenario in scenarios:
        if scenario.filing_status in {"single", "head_of_household"}:
            assert len(scenario.adults) == 1


def test_richer_cps_inputs_are_preserved(sample_person_frame):
    """Selected non-wage CPS inputs should be carried into the scenario."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=3, seed=0)
    joint = next(s for s in scenarios if s.filing_status == "joint")
    assert joint.adults[1].inputs["self_employment_income"] == 5_000.0

    disabled_single = next(s for s in scenarios if s.state == "CO")
    assert disabled_single.adults[0].inputs["is_disabled"] is True
    assert disabled_single.adults[0].inputs["disability_benefits"] == 18_000.0


def test_children_and_adults_split_by_age(sample_person_frame):
    """Adults and children should be split at age 18."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=3, seed=0)
    for scenario in scenarios:
        for adult in scenario.adults:
            assert adult.age >= 18
        for child in scenario.children:
            assert child.age < 18


def test_pe_household_format(simple_single_scenario):
    """PE household JSON has required structure, including filing status."""
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
    assert tax_unit["filing_status"]["2025"] == "SINGLE"

    housing = household["households"]["household"]
    assert "state_code" in housing


def test_pe_household_with_children(family_scenario):
    """PE household includes children in all groups."""
    household = family_scenario.to_pe_household()

    all_members = household["tax_units"]["tax_unit"]["members"]
    assert "adult1" in all_members
    assert "adult2" in all_members
    assert "child1" in all_members
    assert "child2" in all_members
    assert household["tax_units"]["tax_unit"]["filing_status"]["2025"] == "JOINT"
    assert len(household["people"]) == 4


def test_generate_scenarios_uses_loader(monkeypatch, sample_person_frame):
    """Top-level generation should delegate to the Enhanced CPS loader."""

    def fake_loader():
        return sample_person_frame, 2024

    monkeypatch.setattr("policybench.scenarios.load_enhanced_cps_person_frame", fake_loader)
    scenarios = generate_scenarios(n=3, seed=0)

    assert len(scenarios) == 3
    assert all(scenario.metadata["dataset_year"] == 2024 for scenario in scenarios)
    assert all(scenario.source_dataset == "enhanced_cps_2024" for scenario in scenarios)


def test_scenario_manifest_exports_summary_fields(sample_person_frame):
    """Scenario manifest should expose the dashboard summary fields."""
    scenarios = scenarios_from_cps_frame(sample_person_frame, n=2, seed=0)
    manifest = scenario_manifest(scenarios)

    assert set(manifest.columns) == {
        "scenario_id",
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
