"""Tests for the unlisted-input sweep (policybench/unlisted_input_sweep.py).

Every test here runs on a small fake engine: FakeSimulation computes a handful of
tax and benefit variables from the situation dict with toy formulas shaped like the
engine's (the SALT deduction takes the larger of income and sales tax, a state's
tax reads the federal SALT deduction, county sets Maryland's local rate). The
real-engine checks are marked slow.
"""

from __future__ import annotations

import copy
import json
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from policybench import unlisted_input_sweep as sweep
from policybench.scenarios import (
    Person,
    Scenario,
    is_excluded_prompt_input_name,
    scenario_manifest,
    scenario_to_dict,
)

YEAR = "2026"
INCOME_TAX_STATES = {"MD", "CA"}
NO_LOCAL_SALES_TAX_STATES = {"CT"}
MD_RATES = {
    "ALLEGANY_COUNTY_MD": 0.0303,
    "BALTIMORE_CITY_MD": 0.032,
    "WORCESTER_COUNTY_MD": 0.0225,
}
PROGRAMS = [
    "federal_income_tax_before_refundable_credits",
    "state_income_tax_before_refundable_credits",
    "snap",
    "ssi",
    "person_medicare_eligible",
]


class FakeCounty(Enum):
    UNKNOWN = "UNKNOWN"
    WORCESTER_COUNTY_MD = "Worcester County, MD"
    ALLEGANY_COUNTY_MD = "Allegany County, MD"
    BALTIMORE_CITY_MD = "Baltimore city, MD"
    ALPINE_COUNTY_CA = "Alpine County, CA"
    ALAMEDA_COUNTY_CA = "Alameda County, CA"
    ALBANY_COUNTY_NY = "Albany County, NY"
    KINGS_COUNTY_NY = "Kings County, NY"
    NASSAU_COUNTY_NY = "Nassau County, NY"


FIRST_COUNTY = {
    "MD": "ALLEGANY_COUNTY_MD",
    "CA": "ALAMEDA_COUNTY_CA",
    "NY": "ALBANY_COUNTY_NY",
}
NYC_COUNTIES = {"KINGS_COUNTY_NY"}


class EnumResult(list):
    def decode_to_str(self):
        return np.array(self, dtype=object)


class Node(SimpleNamespace):
    """A parameter tree node: attributes for children, a value when called."""

    def __init__(self, value=None, **children):
        super().__init__(**children)
        self._value = value
        self.updates = []

    def __call__(self, instant):
        return self._value

    def update(self, period, value):
        self.updates.append((period, value))
        self._value = value


def fake_parameters(
    aggregate,
    refundable=("ny_refundable_credits", "ca_refundable_credits"),
    ca_refundable=("ca_eitc",),
):
    return Node(
        gov=Node(
            irs=Node(
                deductions=Node(
                    itemized=Node(
                        interest=Node(
                            mortgage=Node(pre_tcja_origination_year=Node(2017))
                        )
                    )
                )
            ),
            states=Node(
                household=Node(
                    state_income_tax_before_refundable_credits=Node(list(aggregate)),
                    state_refundable_credits=Node(list(refundable)),
                ),
                ca=Node(
                    tax=Node(
                        income=Node(credits=Node(refundable=Node(list(ca_refundable))))
                    )
                ),
            ),
        )
    )


class FakeSystem:
    def __init__(self, aggregate=("md_income_tax_before_refundable_credits",)):
        self.aggregate = list(aggregate)
        self.parameters = fake_parameters(aggregate)
        names = [n[3:] for n in dir(FakeSimulation) if n.startswith("_v_")]
        self.variables = {name: SimpleNamespace() for name in names}
        self.variables["county"] = SimpleNamespace(possible_values=FakeCounty)
        self.variables["partnership_self_employment_net_earnings"] = SimpleNamespace()


class FakeSimulation:
    """Toy formulas over a PolicyBench situation; an input overrides its formula."""

    instances = 0
    state_salt_share = -0.05
    salt_cap = 10_000.0

    def __init__(self, tax_benefit_system, situation):
        type(self).instances += 1
        self.system = tax_benefit_system
        self.situation = situation
        self.people = list(situation["people"].values())
        self.tax_unit = next(iter(situation["tax_units"].values()))
        self.household = next(iter(situation["households"].values()))
        self.cache = {}

    def calculate(self, variable, period):
        assert str(period) == YEAR
        if variable not in self.cache:
            self.cache[variable] = getattr(self, f"_v_{variable}")()
        return self.cache[variable]

    # helpers
    def _person(self, name, default):
        return np.array(
            [float(p.get(name, {YEAR: default})[YEAR]) for p in self.people]
        )

    def _unit(self, node, name, formula):
        if name in node:
            return np.array([float(node[name][YEAR])])
        return np.array([float(formula())])

    def _sum(self, name):
        return float(self.calculate(name, YEAR).sum())

    @property
    def state(self):
        return self.household["state_code"][YEAR]

    # person variables
    def _v_age(self):
        return self._person("age", 0)

    def _v_employment_income(self):
        return self._person("employment_income", 0)

    def _v_social_security_disability(self):
        return self._person("social_security_disability", 0)

    def _v_is_disabled(self):
        return self._person("is_disabled", False).astype(bool)

    def _v_weekly_hours_worked_before_lsr(self):
        return self._person("weekly_hours_worked_before_lsr", 0)

    def _v_months_receiving_social_security_disability(self):
        return self._person("months_receiving_social_security_disability", 0)

    def _v_meets_ssi_disability_criteria(self):
        return self._person("meets_ssi_disability_criteria", False).astype(bool)

    def _v_medicare_part_b_premium(self):
        modeled = np.where(self.calculate("age", YEAR) >= 65, 2_000.0, 0.0)
        return np.array(
            [
                float(p["medicare_part_b_premium"][YEAR])
                if "medicare_part_b_premium" in p
                else modeled[i]
                for i, p in enumerate(self.people)
            ]
        )

    def _v_is_medicare_eligible(self):
        age = self.calculate("age", YEAR)
        months = self.calculate("months_receiving_social_security_disability", YEAR)
        return (age >= 65) | (months >= 24)

    # household
    def _v_county(self):
        if "county" in self.household:
            return EnumResult([self.household["county"][YEAR]])
        return EnumResult([FIRST_COUNTY.get(self.state, "UNKNOWN")])

    # tax unit
    def _v_adjusted_gross_income(self):
        return np.array(
            [self._sum("employment_income") + self._sum("social_security_disability")]
        )

    def _v_state_withheld_income_tax(self):
        agi = self._sum("adjusted_gross_income")
        rate = 0.05 if self.state in INCOME_TAX_STATES else 0.0
        return self._unit(
            self.tax_unit, "state_withheld_income_tax", lambda: rate * agi
        )

    def _v_state_sales_tax(self):
        return np.array([800.0])

    def _v_local_sales_tax(self):
        share = 0.0 if self.state in NO_LOCAL_SALES_TAX_STATES else 0.2
        return self._unit(
            self.tax_unit,
            "local_sales_tax",
            lambda: share * self._sum("state_sales_tax"),
        )

    def _v_local_income_tax(self):
        # NYC residents owe a toy 3% city tax.
        rate = 0.03 if self._sum("in_nyc") else 0.0
        return np.array([rate * self._sum("adjusted_gross_income")])

    def _v_salt_deduction(self):
        income = self._sum("state_withheld_income_tax") + self._sum("local_income_tax")
        sales = self._sum("state_sales_tax") + self._sum("local_sales_tax")
        real_estate = float(self.tax_unit.get("real_estate_taxes", {YEAR: 0})[YEAR])
        return np.array([min(self.salt_cap, max(income, sales) + real_estate)])

    def _v_first_home_mortgage_balance(self):
        return self._unit(self.tax_unit, "first_home_mortgage_balance", lambda: 0)

    def _v_second_home_mortgage_balance(self):
        return self._unit(self.tax_unit, "second_home_mortgage_balance", lambda: 0)

    def _v_first_home_mortgage_origination_year(self):
        return self._unit(
            self.tax_unit, "first_home_mortgage_origination_year", lambda: 0
        )

    def _v_second_home_mortgage_origination_year(self):
        return self._unit(
            self.tax_unit, "second_home_mortgage_origination_year", lambda: 0
        )

    def _v_deductible_mortgage_interest_tax_unit(self):
        interest = float(
            self.tax_unit.get("first_home_mortgage_interest", {YEAR: 0})[YEAR]
        )
        balance = self._sum("first_home_mortgage_balance")
        year = self._sum("first_home_mortgage_origination_year")
        cap = 1_000_000.0 if 0 < year <= 2017 else 750_000.0
        share = min(1.0, cap / balance) if balance > 0 else 1.0
        return np.array([interest * share])

    def _v_non_deductible_mortgage_interest_tax_unit(self):
        interest = float(
            self.tax_unit.get("first_home_mortgage_interest", {YEAR: 0})[YEAR]
        )
        return np.array([interest - self._sum("deductible_mortgage_interest_tax_unit")])

    def _v_income_tax_before_refundable_credits(self):
        # The federal output's engine variable.
        agi = self._sum("adjusted_gross_income")
        medical = max(0.0, self._sum("medicare_part_b_premium") - 0.075 * agi)
        itemized = (
            self._sum("salt_deduction")
            + medical
            + self._sum("deductible_mortgage_interest_tax_unit")
        )
        return np.array([0.2 * max(0.0, agi - max(15_000.0, itemized))])

    def _v_in_nyc(self):
        county = self.calculate("county", YEAR).decode_to_str()[0]
        return np.array([county in NYC_COUNTIES])

    def _v_home_mortgage_interest_tax_unit(self):
        return np.array(
            [float(self.tax_unit.get("first_home_mortgage_interest", {YEAR: 0})[YEAR])]
        )

    def _v_md_local_income_tax_before_refundable_credits(self):
        if self.state != "MD":
            return np.array([0.0])
        county = self.calculate("county", YEAR).decode_to_str()[0]
        return np.array([MD_RATES[county] * self._sum("adjusted_gross_income")])

    def _v_nyc_income_tax_before_refundable_credits(self):
        return np.array([0.0])

    def _v_state_income_tax_before_refundable_credits(self):
        if self.state not in INCOME_TAX_STATES:
            return np.array([0.0])
        amount = 0.04 * self._sum("adjusted_gross_income")
        amount += self.state_salt_share * self._sum("salt_deduction")
        if "md_local_income_tax_before_refundable_credits" in self.system.aggregate:
            amount += self._sum("md_local_income_tax_before_refundable_credits")
        return np.array([max(0.0, amount)])

    def _v_state_refundable_credits(self):
        return self._unit(self.tax_unit, "state_refundable_credits", lambda: 0)

    # benefits
    def _v_snap(self):
        hours = self.calculate("weekly_hours_worked_before_lsr", YEAR)
        ages = self.calculate("age", YEAR)
        adults = ages >= 18
        if (ages < 18).any() or (hours[adults] >= 20).all():
            return np.array([1_200.0])
        return np.array([0.0])

    def _v_ssi(self):
        return self.calculate("meets_ssi_disability_criteria", YEAR) * 5_000.0


class DivergingSimulation(FakeSimulation):
    """A state tax that rises twice as fast as an uncapped SALT deduction."""

    state_salt_share = 2.0
    salt_cap = float("inf")


@pytest.fixture(autouse=True)
def _reset_counter():
    FakeSimulation.instances = 0
    yield


def make_engine(simulation_class=FakeSimulation, **kwargs):
    return sweep.Engine(
        system=FakeSystem(),
        simulation_class=simulation_class,
        **kwargs,
    )


def make_scenario(
    sid="scenario_test",
    state="MD",
    income=120_000.0,
    *,
    head_inputs=None,
    spouse=None,
    children=(),
    tax_unit_inputs=None,
):
    adults = [
        Person("head", 45, income, dict(head_inputs or {"is_tax_unit_head": True}))
    ]
    if spouse is not None:
        adults.append(spouse)
    return Scenario(
        id=sid,
        state=state,
        filing_status="single" if spouse is None else "joint",
        adults=adults,
        children=list(children),
        tax_unit_inputs=dict(tax_unit_inputs or {}),
        year=2026,
    )


def make_job(scenario, estimate_ids=None, programs=PROGRAMS, combined=True):
    from policybench.spec import expand_programs_for_scenario

    ids = tuple(estimate_ids or sweep.ESTIMATES_BY_ID)
    return sweep.HouseholdJob(
        scenario_json=json.dumps(scenario_to_dict(scenario)),
        variables=tuple(expand_programs_for_scenario(programs, scenario)),
        estimate_ids=ids,
        combined=combined,
    )


def readings_of(result, estimate, reading=None):
    return [
        r
        for r in result["readings"]
        if r["estimate"] == estimate and (reading is None or r["reading"] == reading)
    ]


# ---------------------------------------------------------------------------
# Override
# ---------------------------------------------------------------------------


def base_situation():
    return make_scenario().to_pe_household()


def test_override_sets_values_for_the_period_without_mutating_the_input():
    situation = base_situation()
    before = copy.deepcopy(situation)
    override = sweep.Override(
        people={"head": {"medicare_part_b_premium": 0.0}},
        tax_unit={"state_withheld_income_tax": 12.5},
        household={"county": "BALTIMORE_CITY_MD"},
    )
    out = override.apply(situation, YEAR)
    assert situation == before
    assert out["people"]["head"]["medicare_part_b_premium"] == {YEAR: 0.0}
    assert out["tax_units"]["tax_unit"]["state_withheld_income_tax"] == {YEAR: 12.5}
    assert out["households"]["household"]["county"] == {YEAR: "BALTIMORE_CITY_MD"}


def test_override_rejects_an_unknown_person():
    with pytest.raises(KeyError):
        sweep.Override(people={"ghost": {"x": 1}}).apply(base_situation(), YEAR)


def test_override_merge_rejects_conflicts_and_keeps_both_sides():
    a = sweep.Override(tax_unit={"local_sales_tax": 0.0})
    b = sweep.Override(tax_unit={"state_withheld_income_tax": 0.0})
    merged = a.merged(b)
    assert merged.tax_unit == {"local_sales_tax": 0.0, "state_withheld_income_tax": 0.0}
    with pytest.raises(ValueError):
        a.merged(sweep.Override(tax_unit={"local_sales_tax": 1.0}))
    with pytest.raises(ValueError):
        sweep.Override(people={"head": {"x": 1}}).merged(
            sweep.Override(people={"head": {"x": 2}})
        )


def test_override_key_is_canonical_across_number_types():
    assert (
        sweep.Override(tax_unit={"x": 0}).key()
        == sweep.Override(tax_unit={"x": 0.0}).key()
    )
    assert sweep.Override().is_empty()
    assert sweep.Override(tax_unit={"x": 1.0}).describe() == "tax_unit.x=1.00"


values = st.one_of(
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False), st.booleans()
)
variable_names = st.sampled_from(["a", "b", "c", "d"])
group_values = st.dictionaries(variable_names, values, max_size=3)


@settings(max_examples=60, deadline=None)
@given(tax_unit=group_values, household=group_values, head=group_values)
def test_override_apply_is_pure_and_idempotent(tax_unit, household, head):
    situation = base_situation()
    before = copy.deepcopy(situation)
    override = sweep.Override(
        people={"head": head} if head else {}, tax_unit=tax_unit, household=household
    )
    once = override.apply(situation, YEAR)
    assert situation == before
    assert override.apply(once, YEAR) == once


@settings(max_examples=60, deadline=None)
@given(a=group_values, b=group_values)
def test_override_merge_is_commutative_when_it_succeeds(a, b):
    left = sweep.Override(tax_unit=a)
    right = sweep.Override(tax_unit=b)
    try:
        ab = left.merged(right)
    except ValueError:
        with pytest.raises(ValueError):
            right.merged(left)
        return
    assert ab.key() == right.merged(left).key()


# ---------------------------------------------------------------------------
# Moves
# ---------------------------------------------------------------------------


def test_amount_moves_only_past_the_dollar_tolerance():
    assert not sweep.output_moved(100.0, 101.0, binary=False)
    assert sweep.output_moved(100.0, 101.01, binary=False)
    assert sweep.output_moved(100.0, 98.99, binary=False)


def test_flag_moves_only_when_it_flips():
    assert sweep.output_moved(0.0, 1.0, binary=True)
    assert not sweep.output_moved(1.0, 1.0, binary=True)
    assert not sweep.output_moved(1.0, 0.9, binary=True)


amounts = st.floats(min_value=-1e7, max_value=1e7, allow_nan=False)


@settings(max_examples=200, deadline=None)
@given(a=amounts, b=amounts, binary=st.booleans())
def test_moves_are_symmetric_and_never_reflexive(a, b, binary):
    assert sweep.output_moved(a, b, binary=binary) == sweep.output_moved(
        b, a, binary=binary
    )
    assert not sweep.output_moved(a, a, binary=binary)
    if not binary:
        assert sweep.output_moved(a, b, binary=False) == (abs(a - b) > 1.0)


def test_binary_outputs_follow_the_spec_metric_type():
    assert sweep.is_binary_output("head_medicare_eligible")
    assert sweep.is_binary_output("free_school_meals_eligible")
    assert not sweep.is_binary_output("snap")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REQUIRED = {
    "state_withheld_income_tax",
    "local_sales_tax",
    "medicare_part_b_premium",
    "county",
    "weekly_hours_worked_before_lsr",
    "mortgage_origination_year",
}


def test_registry_holds_the_audited_estimates_with_unique_readings():
    ids = [e.id for e in sweep.ESTIMATES]
    assert len(ids) == len(set(ids))
    assert REQUIRED <= set(ids)
    assert sweep.COMBINED_ESTIMATE not in ids
    for estimate in sweep.ESTIMATES:
        assert estimate.readings, estimate.id
        reading_ids = [r.id for r in estimate.readings]
        assert len(reading_ids) == len(set(reading_ids))
        for reading in estimate.readings:
            assert reading.kind in {sweep.LITERAL, sweep.ALTERNATIVE}
            assert reading.description
        for text in (
            estimate.engine_behavior,
            estimate.why_unlisted,
            estimate.found_in,
        ):
            assert text.strip()
        assert estimate.entity in {"person", "tax_unit", "spm_unit", "household"}


def test_state_withholding_has_the_literal_and_both_paid_readings():
    estimate = sweep.ESTIMATES_BY_ID["state_withheld_income_tax"]
    kinds = {r.id: r.kind for r in estimate.readings}
    assert kinds == {
        "zero": sweep.LITERAL,
        "liability": sweep.ALTERNATIVE,
        "net": sweep.ALTERNATIVE,
    }


def test_no_frozen_household_states_a_registered_input():
    run = Path(__file__).resolve().parents[1] / sweep.DEFAULT_RUN_DIR
    scenarios = pd.read_csv(run / "scenarios.csv")
    registered = {
        name for estimate in sweep.ESTIMATES for name in estimate.engine_inputs
    }
    for raw in scenarios["scenario_json"]:
        data = json.loads(raw)
        stated = set(data["tax_unit_inputs"]) | set(data["household_inputs"])
        stated |= set(data["spm_unit_inputs"])
        for person in data["adults"] + data["children"]:
            stated |= set(person["inputs"])
        assert not stated & registered, (data["id"], stated & registered)


def test_registered_person_inputs_never_reach_a_prompt():
    for name in (
        "weekly_hours_worked_before_lsr",
        "takes_up_medicare_if_eligible",
        "county_fips",
    ):
        assert is_excluded_prompt_input_name(name)


def test_select_estimates_rejects_unknown_ids():
    assert sweep.select_estimates(None) == sweep.ESTIMATES
    assert [e.id for e in sweep.select_estimates(["county"])] == ["county"]
    with pytest.raises(SystemExit):
        sweep.select_estimates(["no_such_estimate"])


# ---------------------------------------------------------------------------
# One household on the fake engine
# ---------------------------------------------------------------------------


def test_household_baseline_and_withholding_readings_move_federal_tax():
    scenario = make_scenario(
        tax_unit_inputs={
            "real_estate_taxes": 4_000.0,
            "first_home_mortgage_interest": 20_000.0,
        }
    )
    result = sweep.sweep_household(
        make_job(scenario, ["state_withheld_income_tax"]), make_engine()
    )
    base = result["baseline"]["federal_income_tax_before_refundable_credits"]
    zero = readings_of(result, "state_withheld_income_tax", "zero")[0]
    assert not zero["noop"]
    assert zero["override"] == {"tax_unit": {"state_withheld_income_tax": 0.0}}
    # Itemized deductions: SALT of min(10,000, 6,000 + 4,000) plus 20,000 of
    # interest. Without withholding, SALT takes 960 of sales tax plus 4,000.
    assert base == pytest.approx(0.2 * (120_000 - 30_000))
    assert zero["outputs"]["federal_income_tax_before_refundable_credits"] == (
        pytest.approx(base + 0.2 * (10_000 - 4_960))
    )


def test_liability_reading_reaches_a_fixed_point_with_county_tax_added():
    scenario = make_scenario()
    engine = make_engine()
    result = sweep.sweep_household(
        make_job(scenario, ["state_withheld_income_tax"]), engine
    )
    reading = readings_of(result, "state_withheld_income_tax", "liability")[0]
    assert reading["converged"]
    last = reading["trace"][-1]
    assert abs(last["implied"] - last["withheld"]) < sweep.FIXED_POINT_TOLERANCE
    paid = reading["detail"]["paid"]
    # Re-simulating at the reported amount reproduces it: state tax at that SALT
    # deduction plus Allegany's county tax.
    situation = sweep.Override(tax_unit={"state_withheld_income_tax": paid}).apply(
        scenario.to_pe_household(), YEAR
    )
    sim = FakeSimulation(engine.system, situation)
    state = sim._sum("state_income_tax_before_refundable_credits")
    county = 0.0303 * 120_000
    assert state + county == pytest.approx(paid, abs=0.01)
    assert reading["detail"]["engine_value"] == pytest.approx(0.05 * 120_000)


def test_net_reading_subtracts_state_refundable_credits():
    scenario = make_scenario(tax_unit_inputs={"state_refundable_credits": 300.0})
    result = sweep.sweep_household(
        make_job(scenario, ["state_withheld_income_tax"]), make_engine()
    )
    liability = readings_of(result, "state_withheld_income_tax", "liability")[0]
    net = readings_of(result, "state_withheld_income_tax", "net")[0]
    assert net["converged"]
    paid = net["detail"]["paid"]
    assert paid < liability["detail"]["paid"]
    situation = sweep.Override(tax_unit={"state_withheld_income_tax": paid}).apply(
        scenario.to_pe_household(), YEAR
    )
    sim = FakeSimulation(FakeSystem(), situation)
    state = sim._sum("state_income_tax_before_refundable_credits")
    assert state + 0.0303 * 120_000 - 300.0 == pytest.approx(paid, abs=0.01)


def test_a_diverging_fixed_point_is_reported_not_hidden():
    scenario = make_scenario(income=60_000.0)
    result = sweep.sweep_household(
        make_job(scenario, ["state_withheld_income_tax"]),
        make_engine(DivergingSimulation),
    )
    reading = readings_of(result, "state_withheld_income_tax", "liability")[0]
    assert not reading["converged"]
    assert reading["iterations"] == sweep.MAX_FIXED_POINT_ITERATIONS


def test_readings_that_change_nothing_are_not_simulated():
    # Texas has no income tax: the withholding estimate is already 0, and so is
    # the liability, so all three withholding readings are no-ops.
    scenario = make_scenario(state="TX")
    result = sweep.sweep_household(
        make_job(scenario, ["state_withheld_income_tax"], combined=False),
        make_engine(),
    )
    withholding = readings_of(result, "state_withheld_income_tax")
    assert {r["reading"] for r in withholding} == {"zero", "liability", "net"}
    assert all(r["noop"] and r["outputs"] is None for r in withholding)
    assert result["simulations"] == 1


def test_local_sales_tax_reading_is_a_noop_where_the_engine_already_has_none():
    ct = sweep.sweep_household(
        make_job(make_scenario(state="CT"), ["local_sales_tax"]), make_engine()
    )
    md = sweep.sweep_household(
        make_job(make_scenario(state="MD"), ["local_sales_tax"]), make_engine()
    )
    assert readings_of(ct, "local_sales_tax")[0]["noop"]
    assert not readings_of(md, "local_sales_tax")[0]["noop"]


def test_part_b_reading_zeroes_only_people_with_a_modeled_premium():
    spouse = Person("spouse", 70, 0.0, {"is_tax_unit_spouse": True})
    scenario = make_scenario(spouse=spouse, income=30_000.0)
    result = sweep.sweep_household(
        make_job(scenario, ["medicare_part_b_premium"]), make_engine()
    )
    reading = readings_of(result, "medicare_part_b_premium")[0]
    assert reading["override"] == {
        "people": {"spouse": {"medicare_part_b_premium": 0.0}}
    }
    young = sweep.sweep_household(
        make_job(make_scenario(), ["medicare_part_b_premium"]), make_engine()
    )
    assert readings_of(young, "medicare_part_b_premium") == []


def test_forty_hours_applies_only_to_people_without_stated_hours():
    spouse = Person(
        "spouse",
        40,
        10_000.0,
        {"is_tax_unit_spouse": True, "hours_worked_last_week": 35},
    )
    scenario = make_scenario(spouse=spouse, income=0.0)
    result = sweep.sweep_household(
        make_job(scenario, ["weekly_hours_worked_before_lsr"]), make_engine()
    )
    reading = readings_of(result, "weekly_hours_worked_before_lsr")[0]
    assert reading["override"] == {
        "people": {"head": {"weekly_hours_worked_before_lsr": 40.0}}
    }
    assert result["baseline"]["snap"] == 0.0
    assert reading["outputs"]["snap"] == 1_200.0


def test_pre_tcja_reading_runs_only_where_the_cap_binds():
    capped = make_scenario(
        tax_unit_inputs={
            "first_home_mortgage_balance": 900_000.0,
            "first_home_mortgage_interest": 45_000.0,
        }
    )
    under = make_scenario(
        tax_unit_inputs={
            "first_home_mortgage_balance": 300_000.0,
            "first_home_mortgage_interest": 15_000.0,
        }
    )
    result = sweep.sweep_household(
        make_job(capped, ["mortgage_origination_year"]), make_engine()
    )
    reading = readings_of(result, "mortgage_origination_year")[0]
    assert reading["override"] == {
        "tax_unit": {"first_home_mortgage_origination_year": 2017.0}
    }
    assert reading["detail"]["capped_interest"] == pytest.approx(
        45_000 * (1 - 750_000 / 900_000)
    )
    negative = make_scenario(
        tax_unit_inputs={
            "first_home_mortgage_balance": 900_000.0,
            "first_home_mortgage_interest": -9_000.0,
        }
    )
    # Negative interest: nothing is non-deductible, yet the share is below 1,
    # so the pre-TCJA cap still changes the deduction and must be simulated.
    moved = sweep.sweep_household(
        make_job(negative, ["mortgage_origination_year"]), make_engine()
    )
    assert len(readings_of(moved, "mortgage_origination_year")) == 1
    base = result["baseline"]["federal_income_tax_before_refundable_credits"]
    assert reading["outputs"]["federal_income_tax_before_refundable_credits"] < base
    none = sweep.sweep_household(
        make_job(under, ["mortgage_origination_year"]), make_engine()
    )
    assert readings_of(none, "mortgage_origination_year") == []


def test_county_reading_tries_every_other_county_of_the_state():
    engine = make_engine()
    assert engine.counties("MD") == [
        "ALLEGANY_COUNTY_MD",
        "BALTIMORE_CITY_MD",
        "WORCESTER_COUNTY_MD",
    ]
    scenario = make_scenario(tax_unit_inputs={"real_estate_taxes": 0.0})
    result = sweep.sweep_household(make_job(scenario, ["county"]), engine)
    readings = readings_of(result, "county")
    assert [r["variant"] for r in readings] == engine.counties("MD")
    by_county = {r["variant"]: r for r in readings}
    assert by_county["ALLEGANY_COUNTY_MD"]["noop"]
    assert not by_county["WORCESTER_COUNTY_MD"]["noop"]


def test_county_states_limits_the_county_reading():
    engine = make_engine(county_states=frozenset({"CA"}))
    result = sweep.sweep_household(make_job(make_scenario(), ["county"]), engine)
    assert readings_of(result, "county") == []


def test_county_readings_that_put_a_household_in_a_locality_are_labeled():
    engine = make_engine()
    assert "in_nyc" in engine.locality_flags
    scenario = make_scenario(state="NY", income=80_000.0)
    job = make_job(scenario, ["county"], programs=PROGRAMS + ["local_income_tax"])
    result = sweep.sweep_household(job, engine)
    assert result["baseline_localities"] == []
    by_county = {r["variant"]: r for r in readings_of(result, "county")}
    assert by_county["KINGS_COUNTY_NY"]["localities"] == ["in_nyc"]
    assert by_county["NASSAU_COUNTY_NY"]["localities"] == []
    assert by_county["KINGS_COUNTY_NY"]["outputs"]["local_income_tax"] == 2_400.0
    reference = pd.Series(
        {(scenario.id, v): value for v, value in result["baseline"].items()}
    )
    report = sweep.evaluate([result], reference, {})
    moves = report.moves.set_index(["variable", "variant"])
    assert moves.loc[("local_income_tax", "KINGS_COUNTY_NY"), "status"] == (
        "prompt_rules_out"
    )
    assert moves.loc[("local_income_tax", "KINGS_COUNTY_NY"), "localities"] == "in_nyc"
    assert report.summary["counts"]["scored"] == 0
    assert report.summary["counts"]["prompt_rules_out"] == 1
    assert report.summary["moved_outputs"][0]["localities"] == ["in_nyc"]
    summary = report.summary
    assert sweep.exit_code(summary, strict=True, allow_baseline_mismatch=False) == 0


def test_locality_flags_are_discovered_from_the_installed_engine():
    flags = sweep.discover_locality_flags()
    assert {"in_nyc", "in_san_francisco", "in_denver"} <= set(flags)
    assert all(flag.startswith("in_") for flag in flags)
    # Indiana's state variables share the in_ prefix; none is a locality flag.
    assert "in_income_tax" not in flags


def test_ssdi_and_ssi_alternatives_target_the_right_people():
    head = {
        "is_tax_unit_head": True,
        "social_security_disability": 12_000.0,
        "is_disabled": True,
    }
    scenario = make_scenario(head_inputs=head, income=0.0)
    result = sweep.sweep_household(
        make_job(
            scenario,
            [
                "months_receiving_social_security_disability",
                "meets_ssi_disability_criteria",
            ],
        ),
        make_engine(),
    )
    months = readings_of(result, "months_receiving_social_security_disability")[0]
    assert months["outputs"]["head_medicare_eligible"] == 1.0
    assert result["baseline"]["head_medicare_eligible"] == 0.0
    ssi = readings_of(result, "meets_ssi_disability_criteria")[0]
    assert ssi["outputs"]["ssi"] == 5_000.0


def test_combined_reading_applies_every_literal_reading_at_once():
    spouse = Person("spouse", 70, 0.0, {"is_tax_unit_spouse": True})
    scenario = make_scenario(spouse=spouse, income=90_000.0)
    result = sweep.sweep_household(make_job(scenario), make_engine())
    combined = readings_of(result, sweep.COMBINED_ESTIMATE)[0]
    assert combined["detail"]["parts"] == [
        "state_withheld_income_tax/zero",
        "local_sales_tax/zero",
        "medicare_part_b_premium/zero",
    ]
    assert combined["override"]["tax_unit"] == {
        "local_sales_tax": 0.0,
        "state_withheld_income_tax": 0.0,
    }
    assert combined["override"]["people"] == {
        "spouse": {"medicare_part_b_premium": 0.0}
    }


def test_combined_reading_is_skipped_when_one_literal_reading_or_none_applies():
    # Texas: no withholding estimate and no Medicare-age person, so only the local
    # sales tax reading changes anything and the combined reading would repeat it.
    result = sweep.sweep_household(make_job(make_scenario(state="TX")), make_engine())
    assert readings_of(result, sweep.COMBINED_ESTIMATE) == []


def test_identical_overrides_are_simulated_once():
    # Without refundable credits the net reading's fixed point is the liability's.
    scenario = make_scenario()
    result = sweep.sweep_household(
        make_job(scenario, ["state_withheld_income_tax"], combined=False),
        make_engine(),
    )
    liability = readings_of(result, "state_withheld_income_tax", "liability")[0]
    net = readings_of(result, "state_withheld_income_tax", "net")[0]
    assert liability["override"] == net["override"]
    # baseline + zero + the liability iterations; net reuses every one of them.
    assert result["simulations"] == 2 + liability["iterations"]
    assert FakeSimulation.instances == result["simulations"]


def test_reference_situation_renames_and_patches_as_the_builder_did():
    head = {"is_tax_unit_head": True, "partnership_se_income": 5_000.0}
    scenario = make_scenario(head_inputs=head)
    engine = make_engine()

    def patch(situation, scenario):
        situation["tax_units"]["tax_unit"]["patched"] = {YEAR: 1}
        return situation

    situation = sweep.build_reference_situation(scenario, engine, patch)
    head_inputs = situation["people"]["head"]
    assert "partnership_se_income" not in head_inputs
    assert head_inputs["partnership_self_employment_net_earnings"] == {YEAR: 5_000.0}
    assert situation["tax_units"]["tax_unit"]["patched"] == {YEAR: 1}

    engine.system.variables["partnership_se_income"] = SimpleNamespace()
    kept = sweep.build_reference_situation(scenario, engine)
    assert "partnership_se_income" in kept["people"]["head"]


def test_household_reports_local_taxes_for_the_scope_check():
    engine = make_engine(
        removed_local_components=("md_local_income_tax_before_refundable_credits",)
    )
    result = sweep.sweep_household(make_job(make_scenario(), ["county"]), engine)
    assert result["local_taxes"] == {
        "md_local_income_tax_before_refundable_credits": pytest.approx(0.0303 * 120_000)
    }
    assert result["removed_local_components"] == [
        "md_local_income_tax_before_refundable_credits"
    ]


# ---------------------------------------------------------------------------
# SALT paid: two system configurations, one amount
# ---------------------------------------------------------------------------


class StubSimulation:
    def __init__(self, values):
        self.values = values

    def calculate(self, variable, period):
        return np.array([self.values.get(variable, 0.0)])


SALT_CONTEXTS = (
    sweep.HouseholdContext(make_scenario(), {}, [], make_engine()),
    sweep.HouseholdContext(
        make_scenario(),
        {},
        [],
        make_engine(
            aggregate_local_components=(
                "md_local_income_tax_before_refundable_credits",
                "nyc_income_tax_before_refundable_credits",
            ),
            remaining_local_components=(
                "md_local_income_tax_before_refundable_credits",
                "nyc_income_tax_before_refundable_credits",
                "nyc_refundable_credits",
            ),
        ),
    ),
)


@settings(max_examples=200, deadline=None)
@given(
    state=st.floats(min_value=0, max_value=1e5),
    md=st.floats(min_value=0, max_value=1e4),
    nyc=st.floats(min_value=0, max_value=1e4),
    refundable=st.floats(min_value=0, max_value=1e4),
    nyc_credits=st.floats(min_value=0, max_value=1e3),
    net=st.booleans(),
)
def test_salt_paid_is_the_same_with_or_without_the_scope_adapter(
    state, md, nyc, refundable, nyc_credits, net
):
    """With the adapter the state lists are state-only; without it they carry the
    local taxes and NYC's credits. Either way the amount paid is state tax plus
    Maryland county tax, less state refundable credits for the net reading."""
    common = {
        "md_local_income_tax_before_refundable_credits": md,
        "nyc_income_tax_before_refundable_credits": nyc,
        "nyc_refundable_credits": nyc_credits,
    }
    adapted, raw = SALT_CONTEXTS
    with_adapter = sweep.salt_income_tax_paid(
        adapted,
        StubSimulation(
            {
                **common,
                "state_income_tax_before_refundable_credits": state,
                "state_refundable_credits": refundable,
            }
        ),
        net=net,
    )
    without = sweep.salt_income_tax_paid(
        raw,
        StubSimulation(
            {
                **common,
                "state_income_tax_before_refundable_credits": state + md + nyc,
                "state_refundable_credits": refundable + nyc_credits,
            }
        ),
        net=net,
    )
    expected = max(0.0, state + md - (refundable if net else 0.0))
    assert with_adapter == pytest.approx(expected, abs=1e-6)
    assert without == pytest.approx(expected, abs=1e-6)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def result_for(sid, baseline, readings, local_taxes=None):
    return {
        "scenario_id": sid,
        "state": "MD",
        "baseline": baseline,
        "local_taxes": local_taxes or {},
        "readings": readings,
        "simulations": 1 + len(readings),
        "aggregate_local_components": [],
        "removed_local_components": [],
        "remaining_local_components": [],
        "baseline_localities": [],
    }


def reading(
    estimate,
    name,
    outputs,
    kind=sweep.LITERAL,
    variant="",
    converged=True,
    localities=(),
):
    return {
        "estimate": estimate,
        "reading": name,
        "kind": kind,
        "variant": variant,
        "override": {},
        "override_text": "",
        "noop": outputs is None,
        "converged": converged,
        "iterations": 1,
        "trace": [],
        "detail": {},
        "localities": list(localities),
        "outputs": outputs,
    }


FED = "federal_income_tax_before_refundable_credits"
STATE = "state_income_tax_before_refundable_credits"


def frame(results):
    rows = {}
    for r in results:
        for variable, value in r["baseline"].items():
            rows[(r["scenario_id"], variable)] = value
    return pd.Series(rows)


def test_evaluate_marks_scored_excluded_and_acknowledged_moves():
    results = [
        result_for(
            "s1",
            {FED: 1_000.0, STATE: 500.0, "head_medicare_eligible": 0.0},
            [
                reading(
                    "state_withheld_income_tax",
                    "zero",
                    {FED: 1_400.0, STATE: 500.5, "head_medicare_eligible": 0.0},
                ),
                reading(
                    "months_receiving_social_security_disability",
                    "twenty_four_months",
                    {FED: 1_000.0, STATE: 500.0, "head_medicare_eligible": 1.0},
                    kind=sweep.ALTERNATIVE,
                ),
            ],
        ),
        result_for(
            "s2",
            {FED: 2_000.0},
            [reading("local_sales_tax", "zero", {FED: 2_002.0})],
        ),
        result_for(
            "s3",
            {FED: 3_000.0},
            [reading("county", "each_county", {FED: 3_050.0}, variant="X_MD")],
        ),
        result_for(
            "s4",
            {FED: 4_000.0},
            [
                reading(
                    "county",
                    "each_county",
                    {FED: 4_100.0},
                    variant="KINGS_COUNTY_NY",
                    localities=["in_nyc"],
                )
            ],
        ),
    ]
    exclusions = {
        ("s1", "head_medicare_eligible"): {
            "reason_code": "reference_depends_on_unlisted_input",
            "unlisted_input": "months_receiving_social_security_disability",
        },
        ("s2", FED): {"reason_code": "reference_engine_defect"},
    }
    acknowledgements = {("s3", FED, "county", "*"): {"status": "pending d999"}}
    report = sweep.evaluate(results, frame(results), exclusions, acknowledgements)
    moves = report.moves.set_index(["scenario_id", "variable"])
    assert moves.loc[("s1", FED), "status"] == "scored"
    assert moves.loc[("s1", FED), "delta"] == pytest.approx(400.0)
    assert ("s1", STATE) not in moves.index  # 50 cents is within tolerance
    assert moves.loc[("s1", "head_medicare_eligible"), "status"] == (
        "excluded_same_input"
    )
    assert moves.loc[("s2", FED), "status"] == "excluded_other_reason"
    assert moves.loc[("s3", FED), "status"] == "acknowledged"
    assert moves.loc[("s3", FED), "acknowledged_status"] == "pending d999"
    assert moves.loc[("s4", FED), "status"] == "prompt_rules_out"
    assert report.summary["counts"] == {
        "scored": 1,
        "acknowledged": 1,
        "prompt_rules_out": 1,
        "excluded_same_input": 1,
        "excluded_other_reason": 1,
    }
    assert (
        sweep.exit_code(report.summary, strict=False, allow_baseline_mismatch=False)
        == 0
    )
    assert (
        sweep.exit_code(report.summary, strict=True, allow_baseline_mismatch=False) == 2
    )


def test_evaluate_flags_baseline_mismatches_on_scored_outputs_only():
    results = [result_for("s1", {FED: 1_000.0, STATE: 10.0}, [])]
    reference = pd.Series({("s1", FED): 1_000.5, ("s1", STATE): 99.0})
    exclusions = {("s1", STATE): {"reason_code": "reference_engine_defect"}}
    report = sweep.evaluate(results, reference, exclusions)
    assert report.summary["baseline_scored_mismatches"] == [
        {
            "scenario_id": "s1",
            "variable": FED,
            "reference": 1_000.5,
            "baseline": 1_000.0,
        }
    ]
    assert report.summary["baseline_excluded_mismatches"] == 1
    summary = report.summary
    assert sweep.exit_code(summary, strict=False, allow_baseline_mismatch=False) == 1
    assert sweep.exit_code(summary, strict=False, allow_baseline_mismatch=True) == 0


def test_scope_violations_and_unconverged_fixed_points_fail_the_run():
    results = [
        result_for(
            "s1",
            {FED: 1.0},
            [
                reading(
                    "state_withheld_income_tax",
                    "liability",
                    {FED: 1.0},
                    converged=False,
                )
            ],
            local_taxes={"nyc_income_tax_before_refundable_credits": 250.0},
        )
    ]
    summary = sweep.evaluate(results, frame(results), {}).summary
    assert summary["scope_violations"][0]["scenario_id"] == "s1"
    assert summary["unconverged"] == [
        {
            "scenario_id": "s1",
            "estimate": "state_withheld_income_tax",
            "reading": "liability",
        }
    ]
    assert sweep.exit_code(summary, strict=False, allow_baseline_mismatch=True) == 1


def test_exclusion_names_inputs_matches_the_record_text():
    record = {"unlisted_input": "weekly_hours_worked_before_lsr and whether ..."}
    assert sweep.exclusion_names_inputs(record, ["weekly_hours_worked_before_lsr"])
    assert not sweep.exclusion_names_inputs(record, ["county"])
    assert not sweep.exclusion_names_inputs(None, ["county"])


def test_acknowledgements_require_the_key_fields(tmp_path):
    path = tmp_path / "ack.json"
    path.write_text(json.dumps({"acknowledged": [{"scenario_id": "s1"}]}))
    with pytest.raises(SystemExit):
        sweep.load_acknowledgements(path)
    path.write_text(
        json.dumps(
            {
                "acknowledged": [
                    {
                        "scenario_id": "s1",
                        "variable": FED,
                        "estimate": "county",
                        "status": "pending",
                    }
                ]
            }
        )
    )
    assert ("s1", FED, "county", "*") in sweep.load_acknowledgements(path)
    assert sweep.load_acknowledgements(None) == {}


def test_scope_lists_must_agree_across_workers():
    a = result_for("s1", {}, [])
    b = dict(a, removed_local_components=["nyc_income_tax_before_refundable_credits"])
    assert sweep.scope_lists([a, a]) == {key: [] for key in sweep.SCOPE_KEYS}
    assert sweep.scope_lists([b])["removed_local_components"] == [
        "nyc_income_tax_before_refundable_credits"
    ]
    with pytest.raises(RuntimeError):
        sweep.scope_lists([a, b])


@settings(max_examples=100, deadline=None)
@given(
    deltas=st.lists(
        st.floats(min_value=-50, max_value=50, allow_nan=False), min_size=1, max_size=6
    ),
    excluded=st.lists(st.booleans(), min_size=6, max_size=6),
)
def test_every_move_row_is_a_real_move_with_a_consistent_status(deltas, excluded):
    variables = [f"v{i}" for i in range(len(deltas))]
    baseline = {v: 100.0 for v in variables}
    outputs = {v: 100.0 + d for v, d in zip(variables, deltas)}
    results = [
        result_for("s1", baseline, [reading("local_sales_tax", "zero", outputs)])
    ]
    exclusions = {
        ("s1", v): {"reason_code": "reference_engine_defect"}
        for v, flag in zip(variables, excluded)
        if flag
    }
    report = sweep.evaluate(results, frame(results), exclusions)
    moved = {v for v, d in zip(variables, deltas) if abs(d) > 1.0}
    assert set(report.moves["variable"]) == moved
    for _, row in report.moves.iterrows():
        assert row["scored"] == (("s1", row["variable"]) not in exclusions)
        assert (row["status"] == "scored") == row["scored"]
        assert abs(row["delta"]) > 1.0


# ---------------------------------------------------------------------------
# Jobs, workers and the fix module
# ---------------------------------------------------------------------------


def test_build_jobs_puts_the_most_counties_first(monkeypatch):
    monkeypatch.setattr(
        sweep, "_county_count", lambda state: {"MD": 24, "CA": 58}.get(state, 0)
    )
    scenarios = scenario_manifest(
        [make_scenario("a", "TX"), make_scenario("b", "MD"), make_scenario("c", "CA")]
    )
    reference = pd.Series({(sid, FED): 0.0 for sid in ("a", "b", "c")})
    jobs = sweep.build_jobs(
        scenarios, reference, [FED, STATE], sweep.ESTIMATES, county_states=None
    )
    ids = [json.loads(j.scenario_json)["id"] for j in jobs]
    assert ids == ["c", "b", "a"]
    assert all(j.variables == (FED,) for j in jobs)
    md_only = sweep.build_jobs(
        scenarios, reference, [FED], sweep.ESTIMATES, county_states=frozenset({"MD"})
    )
    assert [json.loads(j.scenario_json)["id"] for j in md_only] == ["b", "a", "c"]


def test_run_jobs_builds_one_system_per_worker(monkeypatch):
    calls = {}

    class Done:
        def __init__(self, value):
            self.value = value

        def result(self):
            return self.value

    class FakePool:
        def __init__(self, max_workers, mp_context, initializer, initargs):
            calls.update(
                workers=max_workers,
                method=mp_context.get_start_method(),
                initializer=initializer,
                initargs=initargs,
                submitted=[],
            )

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def submit(self, fn, job):
            calls["submitted"].append((fn, job))
            return Done(
                {"scenario_id": job, "state": "MD", "simulations": 1, "seconds": 0}
            )

    monkeypatch.setattr(sweep, "ProcessPoolExecutor", FakePool)
    monkeypatch.setattr(sweep, "as_completed", lambda futures: reversed(futures))
    seen = []
    config = sweep.EngineConfig(fix_path=None)
    out = sweep.run_jobs(
        ["j1", "j2"], config, workers=3, progress=lambda d, t, r: seen.append((d, t))
    )
    assert [r["scenario_id"] for r in out] == ["j2", "j1"]
    assert seen == [(1, 2), (2, 2)]
    assert calls["workers"] == 3
    assert calls["method"] == "spawn"
    assert calls["initializer"] is sweep._init_worker
    assert calls["initargs"] == (config,)
    assert [fn for fn, _ in calls["submitted"]] == [sweep._run_job] * 2


def test_run_jobs_in_process_uses_the_same_worker_setup(monkeypatch):
    built = []

    def fake_build(config):
        built.append(config)
        return make_engine(), None

    monkeypatch.setattr(sweep, "build_engine", fake_build)
    job = make_job(make_scenario(), ["local_sales_tax"])
    out = sweep.run_jobs([job], sweep.EngineConfig(fix_path=None), workers=1)
    assert len(built) == 1
    assert out[0]["scenario_id"] == "scenario_test"


def test_fix_dir_and_module_load_with_their_support_files(tmp_path):
    fixes = tmp_path / "fixes"
    fixes.mkdir()
    (fixes / "part.py").write_text("VALUE = 7\n")
    (fixes / "notes.txt").write_text("not copied\n")
    (fixes / "main_fix.py").write_text(
        "import importlib.util, json\n"
        "from pathlib import Path\n"
        "spec = importlib.util.spec_from_file_location("
        "'part', Path(__file__).with_name('part.py'))\n"
        "part = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(part)\n"
        "TABLE = json.loads(Path(__file__).with_name('table.json').read_text())\n"
        "reform = None\n"
        "def patch(situation, scenario):\n"
        "    return situation\n"
    )
    support = tmp_path / "elsewhere" / "table.json"
    support.parent.mkdir()
    support.write_text(json.dumps({"rate": 0.2}))
    path = sweep.assemble_fix_dir(fixes / "main_fix.py", [support], tmp_path / "out")
    assert sorted(p.name for p in path.parent.iterdir()) == [
        "main_fix.py",
        "part.py",
        "table.json",
    ]
    module = sweep.load_fix_module(path)
    assert module.part.VALUE == 7
    assert module.TABLE == {"rate": 0.2}
    assert module.reform is None and callable(module.patch)


def test_composed_reform_runs_the_fix_then_removes_local_taxes():
    applied = []

    class FixReform:
        @staticmethod
        def apply(system):
            applied.append("fix")

    class FakeReformSystem:
        def __init__(self):
            self.parameters = fake_parameters(
                [
                    "md_income_tax_before_refundable_credits",
                    "ny_income_tax_before_refundable_credits",
                    "nyc_income_tax_before_refundable_credits",
                ]
            )

        def modify_parameters(self, fn):
            self.parameters = fn(self.parameters)

    composed, seen = sweep.compose_reform(FixReform, adapter=True)
    system = FakeReformSystem()
    composed.apply(system)
    # A second pass sees the scoped lists; the record keeps what the fix left.
    composed.apply(system)
    assert applied == ["fix", "fix"]
    assert seen["listed"] == ["nyc_income_tax_before_refundable_credits"]
    aggregate = system.parameters.gov.states.household
    assert aggregate.state_income_tax_before_refundable_credits("2026-01-01") == [
        "md_income_tax_before_refundable_credits",
        "ny_income_tax_before_refundable_credits",
    ]

    unadapted, seen = sweep.compose_reform(None, adapter=False)
    system = FakeReformSystem()
    unadapted.apply(system)
    assert seen["listed"] == ["nyc_income_tax_before_refundable_credits"]
    assert "nyc_income_tax_before_refundable_credits" in (
        system.parameters.gov.states.household.state_income_tax_before_refundable_credits(
            "2026-01-01"
        )
    )


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def write_run(tmp_path, scenarios, engine, exclusions=()):
    run = tmp_path / "run"
    run.mkdir()
    scenario_manifest(scenarios).to_csv(run / "scenarios.csv", index=False)
    rows = []
    for scenario in scenarios:
        job = make_job(scenario, [], combined=False)
        result = sweep.sweep_household(job, engine)
        for variable, value in result["baseline"].items():
            rows.append(
                {"scenario_id": scenario.id, "variable": variable, "value": value}
            )
    pd.DataFrame(rows).to_csv(run / "reference_outputs.csv", index=False)
    (run / "reference_outputs.csv.meta.json").write_text(
        json.dumps({"programs": PROGRAMS})
    )
    (run / "reference_exclusions.json").write_text(
        json.dumps({"exclusions": list(exclusions)})
    )
    return run


def test_command_writes_every_artifact_and_gates_on_scored_moves(
    tmp_path, monkeypatch, capsys
):
    from policybench.cli import main

    engine = make_engine()
    scenarios = [
        make_scenario(
            "scenario_a", "MD", tax_unit_inputs={"real_estate_taxes": 4_000.0}
        ),
        make_scenario("scenario_b", "TX", income=40_000.0),
    ]
    run = write_run(tmp_path, scenarios, engine)
    monkeypatch.setattr(sweep, "build_engine", lambda config: (engine, None))
    monkeypatch.setattr(sweep, "_county_count", lambda state: 3)
    out = tmp_path / "out"
    argv = [
        "policybench",
        "unlisted-input-sweep",
        "--run-dir",
        str(run),
        "--out-dir",
        str(out),
        "--workers",
        "1",
    ]
    monkeypatch.setattr("sys.argv", argv)
    main()
    for name in (
        "moves.csv",
        "readings.csv",
        "baseline.csv",
        "values.csv.gz",
        "summary.json",
        "households.json",
        "report.md",
    ):
        assert (out / name).exists(), name
    summary = json.loads((out / "summary.json").read_text())
    assert summary["baseline_scored_mismatches"] == []
    assert summary["counts"]["scored"] >= 1
    assert summary["run"]["fix_id"] == "baseline"
    assert {e["id"] for e in summary["estimates"]} == set(sweep.ESTIMATES_BY_ID)
    moves = pd.read_csv(out / "moves.csv")
    # Texas has no withholding estimate; both households have no stated hours.
    assert set(
        moves[moves["estimate"] == "state_withheld_income_tax"]["scenario_id"]
    ) == {"scenario_a"}
    assert set(
        moves[moves["estimate"] == "weekly_hours_worked_before_lsr"]["variable"]
    ) == {"snap"}
    assert "Scored outputs that move" in capsys.readouterr().out

    monkeypatch.setattr("sys.argv", argv + ["--strict"])
    with pytest.raises(SystemExit) as raised:
        main()
    assert raised.value.code == 2

    acknowledged = tmp_path / "ack.json"
    acknowledged.write_text(
        json.dumps(
            {
                "acknowledged": [
                    {
                        "scenario_id": row.scenario_id,
                        "variable": row.variable,
                        "estimate": row.estimate,
                        "status": "pending",
                    }
                    for row in moves.itertuples()
                ]
            }
        )
    )
    monkeypatch.setattr(
        "sys.argv", argv + ["--strict", "--acknowledged", str(acknowledged)]
    )
    main()


def test_command_rejects_a_run_without_its_reference(tmp_path, monkeypatch):
    from policybench.cli import main

    monkeypatch.setattr(
        "sys.argv",
        [
            "policybench",
            "unlisted-input-sweep",
            "--run-dir",
            str(tmp_path),
            "--out-dir",
            str(tmp_path / "out"),
        ],
    )
    with pytest.raises(SystemExit, match="Missing"):
        main()


# ---------------------------------------------------------------------------
# Real engine (slow)
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "reference_audit/2026-09-28/fixes/latest_final.py"
SALES_TABLE = ROOT / "reference_audit/2026-09-22/fixes/r19_irs_sales_tax_2025.json"


@pytest.fixture(scope="module")
def real_engine(tmp_path_factory):
    fix = sweep.assemble_fix_dir(FIX, [SALES_TABLE], tmp_path_factory.mktemp("fix"))
    return sweep.build_engine(
        sweep.EngineConfig(fix_path=str(fix), county_states=("MD",))
    )


@pytest.mark.slow
def test_real_engine_reproduces_the_recorded_unlisted_input_exclusions(real_engine):
    """On the published reference system the sweep reproduces every scored
    reference of these households and finds the recorded weekly-hours and SSDI
    exclusions as excluded for the same input."""
    engine, patch = real_engine
    assert engine.removed_local_components == (
        "nyc_income_tax_before_refundable_credits",
        "nyc_refundable_credits",
        "ca_sf_wftc",
    )
    assert engine.aggregate_local_components == ()
    assert engine.remaining_local_components == ()
    assert {"in_nyc", "in_san_francisco"} <= set(engine.locality_flags)
    run = ROOT / sweep.DEFAULT_RUN_DIR
    scenarios = pd.read_csv(run / "scenarios.csv")
    scenarios = scenarios[
        scenarios["scenario_id"].isin(["scenario_007", "scenario_056", "scenario_068"])
    ]
    reference = pd.read_csv(run / "reference_outputs.csv").set_index(
        ["scenario_id", "variable"]
    )["value"]
    meta = json.loads((run / "reference_outputs.csv.meta.json").read_text())
    exclusions = {
        (e["scenario_id"], e["variable"]): e
        for e in json.loads((run / "reference_exclusions.json").read_text())[
            "exclusions"
        ]
    }
    jobs = sweep.build_jobs(
        scenarios, reference, meta["programs"], sweep.ESTIMATES, frozenset({"MD"})
    )
    results = [sweep.sweep_household(job, engine, patch) for job in jobs]
    report = sweep.evaluate(results, reference, exclusions)
    assert report.summary["baseline_scored_mismatches"] == []
    assert report.summary["scope_violations"] == []
    moved = {
        (o["scenario_id"], o["variable"]): o["status"]
        for o in report.summary["moved_outputs"]
    }
    assert moved[("scenario_007", "head_medicare_eligible")] == "excluded_same_input"
    assert moved[("scenario_056", "snap")] == "excluded_same_input"
    county = [r for r in results if r["scenario_id"] == "scenario_068"][0]
    assert len(readings_of(county, "county")) == 24
