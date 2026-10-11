"""Tests for the stratified UK audit sample (policybench.uk_audit)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from policybench import uk_audit
from policybench.config import get_programs
from policybench.prompts import describe_household
from policybench.scenarios import Person, Scenario, scenario_from_dict, scenario_to_dict

REGIONS = (
    "NORTH_EAST",
    "NORTH_WEST",
    "YORKSHIRE",
    "EAST_MIDLANDS",
    "WEST_MIDLANDS",
    "EAST_OF_ENGLAND",
    "LONDON",
    "SOUTH_EAST",
    "SOUTH_WEST",
    "WALES",
    "SCOTLAND",
    "NORTHERN_IRELAND",
)


def _frames(n_households: int = 3000, seed: int = 0):
    """Synthetic transfer frames with every structure the strata select."""
    rng = np.random.default_rng(seed)
    people, households = [], []
    person_id = 0
    for household_id in range(n_households):
        kind = household_id % 6
        region = REGIONS[int(rng.integers(len(REGIONS)))]
        if kind == 0:  # pensioner couple
            ages = [int(rng.integers(67, 90)), int(rng.integers(67, 90))]
        elif kind == 1:  # family
            ages = [int(rng.integers(25, 50)), int(rng.integers(25, 50)), 3, 9]
        elif kind == 2:  # single parent
            ages = [int(rng.integers(20, 45)), int(rng.integers(0, 15))]
        elif kind == 3:  # working-age couple
            ages = [int(rng.integers(25, 64)), int(rng.integers(25, 64))]
        elif kind == 4:  # single adult
            ages = [int(rng.integers(20, 64))]
        else:  # single pensioner
            ages = [int(rng.integers(67, 95))]
        low = rng.random() < 0.4
        for position, age in enumerate(ages):
            adult = age >= 18
            earnings = 0.0
            if adult and age < 67:
                earnings = float(
                    rng.uniform(0, 12_000) if low else rng.uniform(20_000, 130_000)
                )
            self_employment = 0.0
            if adult and age < 67 and rng.random() < 0.08:
                self_employment = float(rng.uniform(-8_000, -100))
            people.append(
                {
                    "person_id": person_id,
                    "person_household_id": household_id,
                    "person_benunit_id": household_id,
                    "age": age,
                    "employment_income_before_lsr": earnings,
                    "self_employment_income": self_employment,
                    "private_pension_income": float(rng.uniform(0, 4_000))
                    if age >= 67
                    else 0.0,
                    "property_income": 0.0,
                    "savings_interest_income": 0.0,
                    "dividend_income": 0.0,
                    "miscellaneous_income": 0.0,
                    "gift_aid": 100.0 if position == 0 else 0.0,
                    "date_of_birth": (2026 - age) * 10000 + 701,
                    "pip_dl_category": "NONE",
                }
            )
            person_id += 1
        households.append(
            {
                "household_id": household_id,
                "household_weight": float(rng.uniform(1, 100)),
                "region": region,
                "tenure_type": "RENT_PRIVATELY"
                if rng.random() < 0.4
                else "OWNED_OUTRIGHT",
                "rent": float(rng.uniform(5_000, 15_000)),
                "savings": float(
                    rng.uniform(0, 10_000) if low else rng.uniform(20_000, 200_000)
                ),
                "council_tax_band": str(rng.choice(list("ABCDEFGHI"))),
            }
        )
    return pd.DataFrame(people), pd.DataFrame(households)


@pytest.fixture(scope="module")
def sample():
    person_df, household_df = _frames()
    return uk_audit.stratified_uk_audit_scenarios(
        person_df, household_df, dataset_year=2025
    )


def _stratum(scenarios, name):
    return [s for s in scenarios if s.metadata["stratum"] == name]


def test_strata_counts_and_distinct_households(sample):
    expected = {s.name: s.count for s in uk_audit.UK_AUDIT_STRATA}
    assert dict(uk_audit.stratum_counts(sample)) == expected
    assert len(sample) == sum(expected.values()) == 200
    ids = [s.metadata["household_id"] for s in sample]
    assert len(ids) == len(set(ids))
    assert [s.id for s in sample] == [f"scenario_{i:03d}" for i in range(len(sample))]


def test_sample_is_deterministic():
    person_df, household_df = _frames()
    first = uk_audit.stratified_uk_audit_scenarios(person_df, household_df)
    second = uk_audit.stratified_uk_audit_scenarios(person_df, household_df)
    assert [scenario_to_dict(s) for s in first] == [scenario_to_dict(s) for s in second]


def test_a_later_stratum_does_not_change_earlier_draws():
    person_df, household_df = _frames()
    strata = uk_audit.UK_AUDIT_STRATA
    full = uk_audit.stratified_uk_audit_scenarios(
        person_df, household_df, strata=strata
    )
    shorter = uk_audit.stratified_uk_audit_scenarios(
        person_df, household_df, strata=strata[:-1]
    )
    assert [scenario_to_dict(s) for s in shorter] == [
        scenario_to_dict(s) for s in full[: len(shorter)]
    ]


def test_every_household_is_in_great_britain_with_a_council(sample):
    for scenario in sample:
        assert scenario.state != "NORTHERN_IRELAND"
        council = scenario.household_inputs["local_authority"]
        regional = {c.local_authority: c for c in uk_audit.COUNCILS[scenario.state]}
        assert council in regional
        band = scenario.household_inputs["council_tax_band"]
        charge = regional[council].band_d * uk_audit.band_ratio(scenario.state, band)
        if len(scenario.adults) == 1:
            charge *= 1 - uk_audit.SINGLE_PERSON_DISCOUNT
        assert scenario.household_inputs["council_tax"] == round(charge)
        if band == "I":
            assert scenario.state == "WALES"


def test_private_renters_are_placed_in_their_councils_rental_area(sample):
    for scenario in sample:
        inputs = scenario.household_inputs
        if inputs.get("tenure_type") == "RENT_PRIVATELY":
            regional = {c.local_authority: c for c in uk_audit.COUNCILS[scenario.state]}
            assert inputs["brma"] == regional[inputs["local_authority"]].brma


def test_everyone_67_or_over_has_a_state_pension_outside_control(sample):
    for scenario in sample:
        for adult in scenario.adults:
            stated = adult.inputs.get("state_pension_reported")
            if scenario.metadata["stratum"] == "control":
                assert stated is None
            elif adult.age >= uk_audit.PENSIONER_MIN_AGE:
                assert stated and stated > 0
            else:
                assert stated is None


def test_pension_strata(sample):
    for name in ("pension_age", "pension_age_low_income"):
        for scenario in _stratum(sample, name):
            assert all(a.age >= uk_audit.PENSIONER_MIN_AGE for a in scenario.adults)
            assert not scenario.children
    tenures = {
        s.household_inputs.get("tenure_type")
        for s in _stratum(sample, "pension_age")
        + _stratum(sample, "pension_age_low_income")
    }
    assert tenures & set(uk_audit.SOCIAL_TENURES)


def test_carers_stratum(sample):
    carers = _stratum(sample, "carers")
    assert carers
    for scenario in carers:
        assert len(scenario.adults) == 2
        assert scenario.state not in ("SCOTLAND", "NORTHERN_IRELAND")
        hours = [a.inputs.get("care_hours") for a in scenario.adults]
        assert sum(h is not None for h in hours) == 1
        assert {h for h in hours if h is not None} <= set(uk_audit.CARE_HOURS)


def test_childcare_costs_only_for_children_eleven_or_under(sample):
    for scenario in sample:
        for child in scenario.children:
            cost = child.inputs.get("childcare_expenses")
            if scenario.metadata["stratum"] == "childcare" and child.age <= 11:
                assert cost and cost > 0
                assert (
                    child.inputs["tax_free_childcare_uses_qualifying_provider"] is True
                )
            else:
                assert cost is None


def test_gift_aid_only_in_control(sample):
    for scenario in sample:
        has_gift_aid = any(p.inputs.get("gift_aid") for p in scenario.all_people)
        if has_gift_aid:
            assert scenario.metadata["stratum"] == "control"


def test_low_income_strata(sample):
    for name in (
        "scotland_low_income_families",
        "pension_age_low_income",
        "private_renters_low_income",
    ):
        for scenario in _stratum(sample, name):
            capital = sum(
                scenario.household_inputs.get(column, 0)
                for column in uk_audit.CAPITAL_COLUMNS
            )
            assert capital < uk_audit.LOW_CAPITAL


def test_scenarios_round_trip_through_the_manifest(sample):
    for scenario in sample:
        assert scenario_from_dict(scenario_to_dict(scenario)) == scenario


@settings(max_examples=300, deadline=None)
@given(
    dob=st.integers(min_value=19200101, max_value=19600405),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
def test_state_pension_is_within_the_scheme_bounds(dob, seed):
    """Every drawn State Pension lies between 60% of its scheme's flat rate
    and the flat rate plus the largest top-up, on the scheme the date of
    birth puts the person on."""
    person = Person(
        name="adult1", age=70, employment_income=0, inputs={"date_of_birth": dob}
    )
    annual = uk_audit.draw_state_pension(person, np.random.default_rng(seed))
    weekly = annual / uk_audit.WEEKS_PER_YEAR
    if dob >= uk_audit.NEW_STATE_PENSION_FIRST_BIRTH_DATE:
        low, high = (
            0.60 * uk_audit.NEW_STATE_PENSION_WEEKLY,
            uk_audit.NEW_STATE_PENSION_WEEKLY + 60,
        )
    else:
        low, high = (
            0.60 * uk_audit.BASIC_STATE_PENSION_WEEKLY,
            uk_audit.BASIC_STATE_PENSION_WEEKLY + 120,
        )
    assert low - 0.01 <= weekly <= high + 0.01


@given(region=st.sampled_from(["SCOTLAND", "WALES", "LONDON"]))
def test_band_ratios_increase_with_band(region):
    table = (
        uk_audit.SCOTLAND_BAND_RATIOS
        if region == "SCOTLAND"
        else uk_audit.WALES_BAND_RATIOS
        if region == "WALES"
        else uk_audit.ENGLAND_BAND_RATIOS
    )
    ratios = [uk_audit.band_ratio(region, band) for band in sorted(table)]
    assert ratios == sorted(ratios)
    assert uk_audit.band_ratio(region, "D") == 1


def test_valid_band_maps_band_i_outside_wales():
    assert uk_audit.valid_band("WALES", "I") == "I"
    assert uk_audit.valid_band("LONDON", "I") == "H"
    assert uk_audit.valid_band("SCOTLAND", "I") == "H"


def test_council_table_is_sourced_and_covers_every_gb_region():
    for region in REGIONS:
        if region == "NORTHERN_IRELAND":
            continue
        assert uk_audit.COUNCILS[region]
    for councils in uk_audit.COUNCILS.values():
        for council in councils:
            assert council.band_d > 0
            assert council.band_d_source
    simulated = {
        c.local_authority for cs in uk_audit.COUNCILS.values() for c in cs
    } & set(uk_audit.SIMULATED_WORKING_AGE_CTR_COUNCILS)
    assert simulated == set(uk_audit.SIMULATED_WORKING_AGE_CTR_COUNCILS)


def test_council_table_names_exist_in_policyengine_uk():
    locations = pytest.importorskip(
        "policyengine_uk.variables.household.demographic.locations"
    )
    for region, councils in uk_audit.COUNCILS.items():
        for council in councils:
            assert council.local_authority in locations.LocalAuthority.__members__
            assert council.brma in locations.BRMAName.__members__


def test_uk_audit_outputs():
    programs = get_programs("uk", "uk_audit")
    assert programs[:7] == get_programs("uk")
    assert programs[7:] == [
        "high_income_child_benefit_charge",
        "carers_allowance",
        "attendance_allowance",
        "housing_benefit",
        "council_tax_reduction",
        "tax_free_childcare",
        "scottish_child_payment",
    ]


def test_uk_audit_outputs_map_to_policyengine_uk_variables():
    pytest.importorskip("policyengine_uk")
    from policyengine_uk import CountryTaxBenefitSystem

    from policybench.ground_truth import _pe_variable_for_output

    variables = CountryTaxBenefitSystem().variables
    for program in get_programs("uk", "uk_audit"):
        assert _pe_variable_for_output(program, "uk") in variables


def test_prompt_states_the_new_facts():
    scenario = Scenario(
        id="scenario_000",
        state="WALES",
        filing_status=None,
        adults=[
            Person(
                name="adult1",
                age=78,
                employment_income=0,
                inputs={
                    "state_pension_reported": 12_548.0,
                    "aa_category": "LOWER",
                    "date_of_birth": 19480601,
                },
            ),
            Person(
                name="adult2", age=60, employment_income=0, inputs={"care_hours": 40.0}
            ),
        ],
        household_inputs={
            "tenure_type": "RENT_FROM_HA",
            "rent": 6_000.0,
            "local_authority": "CARDIFF",
            "council_tax_band": "C",
            "council_tax": 1_786.0,
        },
        country="uk",
    )
    text = describe_household(scenario)
    assert "State Pension (amount for 2026-27): £12,548" in text
    assert "Attendance Allowance award: lower rate" in text
    assert "hours a week spent caring for the other adult in the household: 40" in text
    assert "£40" not in text
    assert "tenure: renting from a housing association" in text
    assert "council (local authority): Cardiff" in text
    assert "after the single person discount" in text
    situation = scenario.to_pe_uk_situation()
    assert situation["people"]["adult1"]["state_pension_reported"] == {"2026": 12_548.0}
