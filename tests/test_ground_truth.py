"""Tests for reference-output calculations."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import policybench.ground_truth as ground_truth
from policybench.ground_truth import calculate_ground_truth, calculate_single
from policybench.scenarios import Person, Scenario


@pytest.fixture
def single_50k():
    return Scenario(
        id="gt_single_50k",
        state="CA",
        filing_status="single",
        adults=[Person(name="adult1", age=35, employment_income=50_000.0)],
        year=2026,
    )


@pytest.fixture
def family_low_income():
    return Scenario(
        id="gt_family_low",
        state="NY",
        filing_status="head_of_household",
        adults=[Person(name="adult1", age=30, employment_income=15_000.0)],
        children=[
            Person(name="child1", age=8, employment_income=0.0),
            Person(name="child2", age=3, employment_income=0.0),
        ],
        year=2026,
    )


@pytest.fixture
def single_parent_single():
    return Scenario(
        id="gt_single_parent_single",
        state="CA",
        filing_status="single",
        adults=[Person(name="adult1", age=30, employment_income=50_000.0)],
        children=[Person(name="child1", age=8, employment_income=0.0)],
        year=2026,
    )


@pytest.fixture
def single_parent_hoh():
    return Scenario(
        id="gt_single_parent_hoh",
        state="CA",
        filing_status="head_of_household",
        adults=[Person(name="adult1", age=30, employment_income=50_000.0)],
        children=[Person(name="child1", age=8, employment_income=0.0)],
        year=2026,
    )


@pytest.mark.slow
class TestGroundTruth:
    """Tests that require PolicyEngine-US (slow)."""

    def test_payroll_tax_positive_for_simple_wages(self, single_50k):
        """A simple wage earner should owe employee-side payroll tax."""
        payroll_tax = calculate_single(single_50k, "payroll_tax")
        assert payroll_tax > 0

    def test_eitc_zero_for_50k_single(self, single_50k):
        """A $50k single filer with no kids should get $0 EITC."""
        eitc = calculate_single(single_50k, "eitc")
        assert eitc == 0

    def test_eitc_positive_for_low_income_family(self, family_low_income):
        """A $15k HoH with 2 kids should receive EITC."""
        eitc = calculate_single(family_low_income, "eitc")
        assert eitc > 0
        # 2026 EITC for 2 kids at $15k should be substantial
        assert eitc > 2_000

    def test_income_tax_reconciles_from_compact_tax_components(
        self,
        single_parent_hoh,
    ):
        """Federal income tax should reconcile from two tax-front pieces."""
        tax_before_refundable = calculate_single(
            single_parent_hoh,
            "federal_income_tax_before_refundable_credits",
        )
        refundable_credits = calculate_single(
            single_parent_hoh,
            "federal_refundable_credits",
        )
        income_tax = calculate_single(single_parent_hoh, "income_tax")

        assert refundable_credits == pytest.approx(tax_before_refundable - income_tax)
        assert income_tax == pytest.approx(tax_before_refundable - refundable_credits)
        assert refundable_credits >= 0

    def test_snap_positive_for_low_income(self, family_low_income):
        """A $15k family with kids should receive SNAP benefits."""
        snap = calculate_single(family_low_income, "snap")
        assert snap > 0

    def test_household_structure_drives_filing_status_ground_truth(
        self,
        single_50k,
        single_parent_hoh,
    ):
        """PE should infer HoH from a single adult with a child."""
        single_tax = calculate_single(
            single_50k,
            "federal_income_tax_before_refundable_credits",
        )
        hoh_tax = calculate_single(
            single_parent_hoh,
            "federal_income_tax_before_refundable_credits",
        )
        assert hoh_tax < single_tax

    def test_household_net_income_reasonable(self, single_50k):
        """Net income should be close to market income minus taxes."""
        net = calculate_single(single_50k, "household_net_income")
        market = calculate_single(single_50k, "household_market_income")
        # Net should be less than market (after taxes)
        assert net < market
        assert net > 0

    def test_calculate_ground_truth_dataframe(self, single_50k):
        """calculate_ground_truth returns proper DataFrame structure."""
        df = calculate_ground_truth(
            [single_50k],
            programs=[
                "payroll_tax",
                "federal_refundable_credits",
                "premium_tax_credit",
            ],
        )
        assert isinstance(df, pd.DataFrame)
        assert set(df.columns) == {
            "scenario_id",
            "variable",
            "value",
            "impact_weight",
        }
        assert len(df) == 3  # 1 scenario × 3 programs
        assert df["scenario_id"].iloc[0] == "gt_single_50k"

    def test_ground_truth_multiple_scenarios(self, single_50k, family_low_income):
        """Ground truth works with multiple scenarios."""
        df = calculate_ground_truth(
            [single_50k, family_low_income],
            programs=["payroll_tax"],
        )
        assert len(df) == 2
        assert set(df["scenario_id"]) == {"gt_single_50k", "gt_family_low"}

    def test_us_vectorized_ground_truth_matches_scalar_reference(
        self,
        single_50k,
        family_low_income,
    ):
        """US reference outputs are vectorized without changing semantics."""
        scenarios = [single_50k, family_low_income]
        programs = [
            "federal_income_tax_before_refundable_credits",
            "self_employment_tax",
            "snap",
            "person_medicaid_eligible",
            "person_wic_eligible",
            "free_school_meals_eligible",
        ]

        vectorized = calculate_ground_truth(scenarios, programs=programs)
        scalar = ground_truth._calculate_ground_truth_us_scalar(
            scenarios,
            programs,
            year=2026,
        )
        sort_columns = ["scenario_id", "variable"]

        pd.testing.assert_frame_equal(
            vectorized.sort_values(sort_columns).reset_index(drop=True),
            scalar.sort_values(sort_columns).reset_index(drop=True),
            check_exact=False,
            rtol=1e-9,
            atol=1e-9,
        )


class TestGroundTruthScalarExtraction:
    def test_free_school_meals_amount_becomes_household_boolean(self):
        assert (
            ground_truth._extract_scalar_value(
                np.array([1116.0]),
                "free_school_meals_eligible",
            )
            == 1.0
        )

    def test_person_level_eligibility_extracts_person_value(self):
        scenario = Scenario(
            id="mini",
            state="CA",
            filing_status="head_of_household",
            adults=[
                Person(name="adult1", age=30, employment_income=0.0),
                Person(name="adult2", age=30, employment_income=0.0),
            ],
            children=[Person(name="child1", age=3, employment_income=0.0)],
            year=2026,
        )

        assert (
            ground_truth._extract_person_value(
                np.array([1.0, 0.0, 1.0]),
                scenario,
                "child1_medicaid_eligible",
            )
            == 1.0
        )

    def test_household_boolean_ids_map_to_policyengine_outputs(self):
        assert (
            ground_truth._extract_scalar_value(
                np.array([250.0]),
                "free_school_meals_eligible",
            )
            == 1.0
        )
        assert (
            ground_truth._pe_variable_for_output(
                "free_school_meals_eligible",
                "us",
            )
            == "free_school_meals"
        )

    def test_person_impact_weight_uses_selected_person(self):
        scenario = Scenario(
            id="mini",
            state="CA",
            filing_status="head_of_household",
            adults=[
                Person(name="adult1", age=30, employment_income=0.0),
                Person(name="adult2", age=30, employment_income=0.0),
            ],
            children=[Person(name="child1", age=3, employment_income=0.0)],
            year=2026,
        )

        assert (
            ground_truth._extract_person_impact_weight(
                np.array([1.0, 0.0, 1.0]),
                np.array([100.0, 500.0, 25.0]),
                scenario,
                "child1_medicaid_eligible",
            )
            == 25.0
        )

    def test_household_boolean_variables_keep_zero_as_zero(self):
        assert (
            ground_truth._extract_scalar_value(
                np.array([0.0, 0.0]),
                "free_school_meals_eligible",
            )
            == 0.0
        )

    def test_non_boolean_variables_still_sum(self):
        assert (
            ground_truth._extract_scalar_value(
                np.array([2000.0, 250.0]),
                "snap",
            )
            == 2250.0
        )


def _uk_scenario(scenario_id: str, *, rent: float, child_age: int | None = None):
    children = (
        [Person(name="child1", age=child_age, employment_income=0.0)]
        if child_age is not None
        else []
    )
    return Scenario(
        id=scenario_id,
        country="uk",
        state="WEST_MIDLANDS",
        filing_status=None,
        adults=[
            Person(
                name="adult1",
                age=40,
                employment_income=18_000.0,
                inputs={"gender": "FEMALE", "date_of_birth": 19860601.0},
            )
        ],
        children=children,
        household_inputs={"rent": rent, "tenure_type": "RENT_PRIVATELY"},
        metadata={"household_id": 1},
    )


class _FakeUKSimulation:
    """Records each situation and returns per-entity values derived from it."""

    situations: list = []

    def __init__(self, situation):
        type(self).situations.append(situation)
        self.situation = situation
        self.tax_benefit_system = SimpleNamespace(
            variables={
                "income_tax": SimpleNamespace(entity=SimpleNamespace(key="person")),
                "child_benefit": SimpleNamespace(entity=SimpleNamespace(key="benunit")),
                "housing_costs": SimpleNamespace(
                    entity=SimpleNamespace(key="household")
                ),
            }
        )

    def calculate(self, variable, period):
        assert period == "2026"
        people = self.situation["people"].values()
        household = next(iter(self.situation["households"].values()))
        if variable == "income_tax":
            return np.array(
                [
                    person["employment_income_before_lsr"]["2026"] * 0.1
                    for person in people
                ]
            )
        if variable == "child_benefit":
            children = sum(1 for person in people if person["age"]["2026"] < 16)
            return np.array([children * 100.0])
        if variable == "housing_costs":
            return np.array([household["rent"]["2026"]])
        raise KeyError(variable)


def test_calculate_ground_truth_uk_runs_each_scenario_on_its_prompted_facts(
    monkeypatch,
):
    _FakeUKSimulation.situations = []
    monkeypatch.setattr(
        ground_truth,
        "get_uk_situation_simulation_class",
        lambda: _FakeUKSimulation,
    )
    scenarios = [
        _uk_scenario("uk_1", rent=7_000.0, child_age=4),
        _uk_scenario("uk_2", rent=3_000.0),
    ]

    result = calculate_ground_truth(
        scenarios,
        programs=["income_tax", "child_benefit", "housing_costs"],
        year=2026,
    ).sort_values(["scenario_id", "variable"])

    expected = pd.DataFrame(
        [
            {"scenario_id": "uk_1", "variable": "child_benefit", "value": 100.0},
            {"scenario_id": "uk_1", "variable": "housing_costs", "value": 7_000.0},
            {"scenario_id": "uk_1", "variable": "income_tax", "value": 1_800.0},
            {"scenario_id": "uk_2", "variable": "child_benefit", "value": 0.0},
            {"scenario_id": "uk_2", "variable": "housing_costs", "value": 3_000.0},
            {"scenario_id": "uk_2", "variable": "income_tax", "value": 1_800.0},
        ]
    )
    pd.testing.assert_frame_equal(
        result.drop(columns="impact_weight").reset_index(drop=True),
        expected.reset_index(drop=True),
    )
    # One simulation per scenario, so no household shares a simulation (and
    # PE-UK's per-benefit-unit seeded draws) with another.
    assert len(_FakeUKSimulation.situations) == 2
    assert all(
        len(situation["households"]) == 1 and len(situation["benunits"]) == 1
        for situation in _FakeUKSimulation.situations
    )


def test_calculate_ground_truth_uk_does_not_depend_on_batch_composition(monkeypatch):
    monkeypatch.setattr(
        ground_truth,
        "get_uk_situation_simulation_class",
        lambda: _FakeUKSimulation,
    )
    programs = ["income_tax", "child_benefit", "housing_costs"]
    first = _uk_scenario("uk_1", rent=7_000.0, child_age=4)
    second = _uk_scenario("uk_2", rent=3_000.0)

    together = calculate_ground_truth([second, first], programs=programs, year=2026)
    alone = calculate_ground_truth([first], programs=programs, year=2026)

    pd.testing.assert_frame_equal(
        together[together["scenario_id"] == "uk_1"].reset_index(drop=True),
        alone.reset_index(drop=True),
    )


def test_calculate_ground_truth_uk_rejects_unsupported_entities(monkeypatch):
    class UnsupportedEntitySimulation(_FakeUKSimulation):
        def __init__(self, situation):
            super().__init__(situation)
            self.tax_benefit_system.variables["income_tax"] = SimpleNamespace(
                entity=SimpleNamespace(key="state")
            )

    monkeypatch.setattr(
        ground_truth,
        "get_uk_situation_simulation_class",
        lambda: UnsupportedEntitySimulation,
    )

    with pytest.raises(ValueError, match="Unsupported UK entity"):
        calculate_ground_truth(
            [_uk_scenario("uk_1", rent=1.0)], programs=["income_tax"], year=2026
        )
