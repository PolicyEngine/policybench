"""Tests for ground truth calculations."""

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


def test_calculate_ground_truth_uk_aggregates_native_entities(monkeypatch):
    class FakeVariable:
        def __init__(self, entity_key: str):
            self.entity = SimpleNamespace(key=entity_key)

    class FakeSimulation:
        def __init__(self, dataset):
            self.tax_benefit_system = SimpleNamespace(
                variables={
                    "income_tax": FakeVariable("person"),
                    "child_benefit": FakeVariable("benunit"),
                    "housing_costs": FakeVariable("household"),
                }
            )

        def calculate(self, variable, year, map_to, unweighted=True):
            lookup = {
                ("person_household_id", "person"): np.array([101, 101, 202]),
                ("person_benunit_id", "person"): np.array([101, 101, 202]),
                ("benunit_id", "benunit"): np.array([101, 202]),
                ("household_id", "household"): np.array([101, 202]),
                ("income_tax", "person"): np.array([100.0, 25.0, 80.0]),
                ("child_benefit", "benunit"): np.array([40.0, 10.0]),
                ("housing_costs", "household"): np.array([700.0, 300.0]),
            }
            return lookup[(variable, map_to)]

    monkeypatch.setattr(
        ground_truth,
        "make_uk_transfer_microsimulation",
        lambda dataset_path: FakeSimulation(dataset_path),
    )
    monkeypatch.setattr(
        ground_truth,
        "get_uk_dataset_path",
        lambda: "/tmp/fake_enhanced_cps_uk.h5",
    )

    scenarios = [
        Scenario(
            id="uk_1",
            country="uk",
            state="WEST_MIDLANDS",
            filing_status=None,
            adults=[Person(name="adult1", age=40, employment_income=0.0)],
            metadata={"household_id": 101},
        ),
        Scenario(
            id="uk_2",
            country="uk",
            state="LONDON",
            filing_status=None,
            adults=[Person(name="adult1", age=35, employment_income=0.0)],
            metadata={"household_id": 202},
        ),
    ]

    result = calculate_ground_truth(
        scenarios,
        programs=["income_tax", "child_benefit", "housing_costs"],
        year=2026,
    ).sort_values(["scenario_id", "variable"])

    expected = pd.DataFrame(
        [
            {"scenario_id": "uk_1", "variable": "child_benefit", "value": 40.0},
            {"scenario_id": "uk_1", "variable": "housing_costs", "value": 700.0},
            {"scenario_id": "uk_1", "variable": "income_tax", "value": 125.0},
            {"scenario_id": "uk_2", "variable": "child_benefit", "value": 10.0},
            {"scenario_id": "uk_2", "variable": "housing_costs", "value": 300.0},
            {"scenario_id": "uk_2", "variable": "income_tax", "value": 80.0},
        ]
    ).sort_values(["scenario_id", "variable"])

    pd.testing.assert_frame_equal(
        result.drop(columns="impact_weight").reset_index(drop=True),
        expected.reset_index(drop=True),
    )
