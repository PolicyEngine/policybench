"""Tests for policybench/output_scope.py: local taxes stay out of the state output."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from policybench import output_scope

STATE_ENTRIES = [
    "ca_income_tax_before_refundable_credits",
    "md_income_tax_before_refundable_credits",
    "ny_income_tax_before_refundable_credits",
    "mt_income_tax_before_refundable_credits_unit",
    "nc_income_tax",
]


def test_known_local_taxes_are_recognized():
    for name in output_scope.LOCAL_INCOME_TAX_COMPONENTS:
        assert output_scope.is_local_component(name)
    for name in STATE_ENTRIES:
        assert not output_scope.is_local_component(name)
    assert output_scope.is_local_component("pa_philadelphia_wage_tax")
    assert output_scope.is_local_component("in_local_income_tax_before_credits")


@settings(max_examples=200, deadline=None)
@given(
    st.lists(
        st.sampled_from(STATE_ENTRIES + list(output_scope.LOCAL_INCOME_TAX_COMPONENTS)),
        max_size=12,
    )
)
def test_scoping_keeps_every_state_entry_in_order_and_no_local_one(entries):
    kept = output_scope.scoped_components(entries)
    assert kept == [e for e in entries if e in STATE_ENTRIES]
    assert not output_scope.local_components(kept)
    assert output_scope.scoped_components(kept) == kept
    assert sorted(kept + output_scope.local_components(entries)) == sorted(entries)


class Leaf:
    def __init__(self, value):
        self.value = list(value)
        self.updates = []

    def __call__(self, instant):
        return list(self.value)

    def update(self, period, value):
        self.updates.append(period)
        self.value = list(value)


def tree(entries):
    leaf = Leaf(entries)
    node = type("N", (), {})()
    node.gov = type("N", (), {})()
    node.gov.states = type("N", (), {})()
    node.gov.states.household = type("N", (), {})()
    node.gov.states.household.state_income_tax_before_refundable_credits = leaf
    return node, leaf


def test_remove_local_components_updates_only_when_needed():
    params, leaf = tree(STATE_ENTRIES + ["nyc_income_tax_before_refundable_credits"])
    assert output_scope.listed_local_components(params) == [
        "nyc_income_tax_before_refundable_credits"
    ]
    output_scope.remove_local_components(params)
    assert leaf.value == STATE_ENTRIES
    assert leaf.updates == ["year:2015-01-01:20"]
    output_scope.remove_local_components(params)
    assert leaf.updates == ["year:2015-01-01:20"]


def test_remove_local_components_refuses_to_drop_a_state_tax():
    params, _ = tree(["ca_income_tax_before_refundable_credits"])
    with pytest.raises(AssertionError):
        output_scope.remove_local_components(params)


class Sim:
    def __init__(self, values):
        self.values = values

    def calculate(self, name, period):
        return np.array([self.values[name]])


def test_scope_violations_lists_each_nonzero_local_tax():
    sim = Sim(
        {
            "nyc_income_tax_before_refundable_credits": 1_234.5,
            "md_local_income_tax_before_refundable_credits": 0.0,
        }
    )
    assert output_scope.scope_violations(
        sim, output_scope.LOCAL_INCOME_TAX_COMPONENTS, 2026
    ) == {"nyc_income_tax_before_refundable_credits": 1_234.5}


def test_reform_is_a_policyengine_reform_built_on_first_use():
    from policyengine_core.reforms import Reform

    assert issubclass(output_scope.reform, Reform)
    assert output_scope.reform is output_scope.reform
    with pytest.raises(AttributeError):
        output_scope.no_such_attribute  # noqa: B018


def test_installed_engine_lists_no_local_tax_the_adapter_misses():
    """Guards every policyengine-us upgrade: a new local entry in the state
    aggregate must be named here and removed by the adapter."""
    entries = output_scope.installed_state_aggregate()
    assert "md_income_tax_before_refundable_credits" in entries
    assert "ny_income_tax_before_refundable_credits" in entries
    local = output_scope.local_components(entries)
    assert set(local) <= set(output_scope.LOCAL_INCOME_TAX_COMPONENTS), local
    assert "nyc_income_tax_before_refundable_credits" in local
    assert not output_scope.local_components(output_scope.scoped_components(entries))
