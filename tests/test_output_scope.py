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


class Node:
    pass


def tree(aggregate, refundable=None, ca_refundable=None):
    """A parameter tree holding the three scoped lists."""
    root = Node()
    leaves = {
        output_scope.STATE_AGGREGATE_PARAMETER: Leaf(aggregate),
        output_scope.STATE_REFUNDABLE_PARAMETER: Leaf(
            refundable or ["ny_refundable_credits", "ca_refundable_credits"]
        ),
        output_scope.CA_REFUNDABLE_PARAMETER: Leaf(ca_refundable or ["ca_eitc"]),
    }
    for path, leaf in leaves.items():
        node = root
        parts = path.split(".")
        for part in parts[:-1]:
            if not hasattr(node, part):
                setattr(node, part, Node())
            node = getattr(node, part)
        setattr(node, parts[-1], leaf)
    return root, leaves


def test_remove_local_components_clears_every_list_and_updates_only_when_needed():
    params, leaves = tree(
        STATE_ENTRIES + ["nyc_income_tax_before_refundable_credits"],
        ["ny_refundable_credits", "nyc_refundable_credits", "ca_refundable_credits"],
        ["ca_eitc", "ca_sf_wftc"],
    )
    assert output_scope.listed_local_components(params) == [
        "nyc_income_tax_before_refundable_credits"
    ]
    assert output_scope.all_listed_local_components(params) == [
        "nyc_income_tax_before_refundable_credits",
        "nyc_refundable_credits",
        "ca_sf_wftc",
    ]
    output_scope.remove_local_components(params)
    aggregate = leaves[output_scope.STATE_AGGREGATE_PARAMETER]
    assert aggregate.value == STATE_ENTRIES
    assert aggregate.updates == [output_scope.SCOPE_PERIOD]
    assert leaves[output_scope.STATE_REFUNDABLE_PARAMETER].value == [
        "ny_refundable_credits",
        "ca_refundable_credits",
    ]
    assert leaves[output_scope.CA_REFUNDABLE_PARAMETER].value == ["ca_eitc"]
    assert output_scope.all_listed_local_components(params) == []
    output_scope.remove_local_components(params)
    assert aggregate.updates == [output_scope.SCOPE_PERIOD]


def test_remove_local_components_refuses_to_drop_a_state_entry():
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


@pytest.mark.parametrize("path", list(output_scope.SCOPED_LISTS))
def test_installed_engine_lists_no_local_entry_the_adapter_misses(path):
    """Guards every policyengine-us upgrade: a new local entry in a state list must
    be named here, and every state entry the adapter keeps must still be listed."""
    entries = output_scope.installed_parameter_list(path)
    spec = output_scope.SCOPED_LISTS[path]
    for name in spec["keeps"]:
        assert name in entries
    local = output_scope.local_components(entries)
    assert local == [e for e in entries if e in spec["local"]], local
    assert set(spec["local"]) <= set(local)
    assert not output_scope.local_components(output_scope.scoped_components(entries))


def test_no_other_state_list_carries_a_local_entry():
    """Every list feeding the two state outputs is scoped: the state income tax and
    state refundable credit lists, and each state's refundable list they add."""
    import importlib.util
    from pathlib import Path

    import yaml

    spec = importlib.util.find_spec("policyengine_us")
    root = Path(next(iter(spec.submodule_search_locations))) / "parameters"
    scoped = {path.replace(".", "/") + ".yaml" for path in output_scope.SCOPED_LISTS}
    hits = {}
    for path in root.glob("gov/states/**/*.yaml"):
        relative = str(path.relative_to(root))
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        if not isinstance(data, dict) or not isinstance(data.get("values"), dict):
            continue
        latest = data["values"][sorted(data["values"])[-1]]
        if not isinstance(latest, list):
            continue
        local = output_scope.local_components(str(x) for x in latest)
        # Refundable-credit lists feed state_refundable_credits; nonrefundable
        # aggregates (state_non_refundable_credits) feed no benchmark output.
        feeds_output = (
            "refundable" in relative and "non_refundable" not in relative
        ) or "income_tax_before_refundable" in relative
        if local and feeds_output:
            hits["gov/" + relative.split("gov/", 1)[-1]] = local
    unscoped = {k: v for k, v in hits.items() if k not in scoped}
    assert not unscoped, unscoped
