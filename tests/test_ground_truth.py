"""Tests for ground truth calculations."""

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
        year=2025,
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
        year=2025,
    )


@pytest.fixture
def single_parent_single():
    return Scenario(
        id="gt_single_parent_single",
        state="CA",
        filing_status="single",
        adults=[Person(name="adult1", age=30, employment_income=50_000.0)],
        children=[Person(name="child1", age=8, employment_income=0.0)],
        year=2025,
    )


@pytest.fixture
def single_parent_hoh():
    return Scenario(
        id="gt_single_parent_hoh",
        state="CA",
        filing_status="head_of_household",
        adults=[Person(name="adult1", age=30, employment_income=50_000.0)],
        children=[Person(name="child1", age=8, employment_income=0.0)],
        year=2025,
    )


@pytest.mark.slow
class TestGroundTruth:
    """Tests that require PolicyEngine-US (slow)."""

    def test_adjusted_gross_income_matches_simple_wages(self, single_50k):
        """A simple $50k wage earner should have AGI equal to wages."""
        agi = calculate_single(single_50k, "adjusted_gross_income")
        assert agi == pytest.approx(50_000.0, abs=1e-6)

    def test_eitc_zero_for_50k_single(self, single_50k):
        """A $50k single filer with no kids should get $0 EITC."""
        eitc = calculate_single(single_50k, "eitc")
        assert eitc == 0

    def test_eitc_positive_for_low_income_family(self, family_low_income):
        """A $15k HoH with 2 kids should receive EITC."""
        eitc = calculate_single(family_low_income, "eitc")
        assert eitc > 0
        # 2025 EITC for 2 kids at $15k should be substantial
        assert eitc > 2_000

    def test_snap_positive_for_low_income(self, family_low_income):
        """A $15k family with kids should receive SNAP benefits."""
        snap = calculate_single(family_low_income, "snap")
        assert snap > 0

    def test_filing_status_affects_ground_truth(
        self,
        single_parent_single,
        single_parent_hoh,
    ):
        """Single and HoH versions of the same household should not collapse."""
        single_tax = calculate_single(
            single_parent_single,
            "income_tax_before_refundable_credits",
        )
        hoh_tax = calculate_single(
            single_parent_hoh,
            "income_tax_before_refundable_credits",
        )
        assert single_tax != hoh_tax

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
            programs=["adjusted_gross_income", "eitc"],
        )
        assert isinstance(df, pd.DataFrame)
        assert set(df.columns) == {"scenario_id", "variable", "value"}
        assert len(df) == 2  # 1 scenario × 2 programs
        assert df["scenario_id"].iloc[0] == "gt_single_50k"

    def test_ground_truth_multiple_scenarios(self, single_50k, family_low_income):
        """Ground truth works with multiple scenarios."""
        df = calculate_ground_truth(
            [single_50k, family_low_income],
            programs=["adjusted_gross_income"],
        )
        assert len(df) == 2
        assert set(df["scenario_id"]) == {"gt_single_50k", "gt_family_low"}


class TestGroundTruthScalarExtraction:
    def test_free_school_meals_amount_becomes_household_boolean(self):
        assert (
            ground_truth._extract_scalar_value(
                np.array([1116.0]),
                "free_school_meals",
            )
            == 1.0
        )

    def test_medicaid_person_level_counts_become_household_boolean(self):
        assert (
            ground_truth._extract_scalar_value(
                np.array([1.0, 0.0, 1.0]),
                "is_medicaid_eligible",
            )
            == 1.0
        )

    def test_household_boolean_variables_keep_zero_as_zero(self):
        assert (
            ground_truth._extract_scalar_value(
                np.array([0.0, 0.0]),
                "is_medicaid_eligible",
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
