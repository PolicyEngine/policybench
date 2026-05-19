"""Tests for full-population scoring weights."""

import pandas as pd
import pytest

from policybench.population_weights import (
    _weights_from_contributions,
    load_population_weight_payload,
    population_weight_series,
)
from policybench.spec import get_output_ids


def test_population_weight_artifact_covers_headline_output_groups():
    payload = load_population_weight_payload()
    assert set(payload["countries"]) == {"us", "uk"}

    for country in ["us", "uk"]:
        expected = set(get_output_ids(country, "headline"))
        country_payload = payload["countries"][country]
        for kind in ["household", "aggregate", "equal"]:
            weights = country_payload["weights"][kind]
            assert set(weights) == expected
            assert sum(weights.values()) == pytest.approx(1.0)


def test_population_weight_artifact_has_expected_nonzero_weights():
    us = population_weight_series("us", "household")
    uk = population_weight_series("uk", "household")

    assert us["federal_income_tax_before_refundable_credits"] > 0
    assert us["payroll_tax"] > 0
    assert us["person_medicaid_eligible"] > 0
    assert us["snap"] > 0
    assert uk["income_tax"] > 0
    assert uk["universal_credit"] > 0
    assert uk["pip"] > 0

    # The current full ECPS source has no local-income-tax-positive households.
    # Keeping this at zero is intentional until the scenario source can
    # represent local tax jurisdictions.
    assert us["local_income_tax"] == 0


def test_weights_from_contributions_uses_household_weights_and_aggregate_sums():
    contributions = pd.DataFrame(
        {
            "tax": [10.0, 0.0],
            "benefit": [0.0, 10.0],
        },
        index=["h1", "h2"],
    )
    household_net_income = pd.Series({"h1": 100.0, "h2": 10.0})
    household_weight = pd.Series({"h1": 1.0, "h2": 9.0})

    result = _weights_from_contributions(
        country="test",
        contributions=contributions,
        household_net_income=household_net_income,
        household_weight=household_weight,
        metadata={"source_dataset": "unit test"},
    )

    assert result["weights"]["aggregate"]["tax"] == pytest.approx(0.1)
    assert result["weights"]["aggregate"]["benefit"] == pytest.approx(0.9)
    assert result["weights"]["household"]["tax"] == pytest.approx(0.01 / 0.91)
    assert result["weights"]["household"]["benefit"] == pytest.approx(0.9 / 0.91)
    assert result["metadata"]["positive_weight_households"] == 2
    assert result["metadata"]["total_household_weight"] == pytest.approx(10.0)
