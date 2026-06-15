"""Tests for full-population scoring weights."""

from types import SimpleNamespace

import pandas as pd
import pytest

from policybench.population_weights import (
    _clear_formula_owned_output_inputs,
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

    assert us["local_income_tax"] > 0


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


def test_clear_formula_owned_output_inputs_deletes_only_active_formula_outputs():
    class FakeVariable:
        def __init__(self, has_formula: bool):
            self.has_formula = has_formula

        def get_formula(self, period: str):
            return (lambda *_: None) if self.has_formula else None

    class FakeHolder:
        def __init__(self, known_periods):
            self._known_periods = list(known_periods)
            self.deleted = False

        def get_known_periods(self):
            return list(self._known_periods)

        def delete_arrays(self):
            self.deleted = True
            self._known_periods = []

    holders = {
        "formula_output": FakeHolder(["2026"]),
        "input_output": FakeHolder(["2026"]),
        "uncached_formula_output": FakeHolder([]),
    }
    sim = SimpleNamespace(
        tax_benefit_system=SimpleNamespace(
            variables={
                "formula_output": FakeVariable(True),
                "input_output": FakeVariable(False),
                "uncached_formula_output": FakeVariable(True),
            }
        ),
        get_holder=lambda name: holders[name],
    )
    outputs = [
        SimpleNamespace(pe_variable="formula_output"),
        SimpleNamespace(pe_variable="input_output"),
        SimpleNamespace(pe_variable="uncached_formula_output"),
    ]

    cleared = _clear_formula_owned_output_inputs(sim, outputs, 2026)

    assert cleared == ["formula_output"]
    assert holders["formula_output"].deleted
    assert not holders["input_output"].deleted
    assert not holders["uncached_formula_output"].deleted


def test_population_weight_artifact_covers_current_headline_spec():
    """Drift sentinel for the committed population-weight artifact.

    The headline ranking pulls variable weights from this artifact. If a spec
    rename (e.g. from a model/microdata bump) left an output group uncovered,
    ``bounded_global_variable_weights`` would silently fall back to benchmark-row
    weights instead of the population weights. This guards the id and tax-year
    contract — both stable across data refreshes — and deliberately does not pin
    the weight values or household counts, which the microdata refresh changes.
    """
    from policybench.config import TAX_YEAR
    from policybench.population_weights import matching_population_weight_series
    from policybench.spec import output_group_id

    payload = load_population_weight_payload()
    for country in ("us", "uk"):
        country_payload = payload["countries"][country]
        assert country_payload["metadata"]["tax_year"] == TAX_YEAR, (
            f"{country} population weights target tax year "
            f"{country_payload['metadata']['tax_year']}, not TAX_YEAR={TAX_YEAR}."
        )
        groups = list(
            dict.fromkeys(
                output_group_id(o) for o in get_output_ids(country, "headline")
            )
        )
        for kind in ("household", "equal", "aggregate"):
            assert (
                matching_population_weight_series(country, kind, groups) is not None
            ), (
                f"{country}/{kind} population weights do not cover the current "
                "headline output groups; regenerate population_weights.json."
            )
