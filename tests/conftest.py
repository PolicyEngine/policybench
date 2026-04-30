"""Shared fixtures for PolicyBench tests."""

import pytest

from policybench.scenarios import Person, Scenario


@pytest.fixture
def simple_single_scenario():
    """Single filer, no kids, $50k income in CA."""
    return Scenario(
        id="test_single",
        state="CA",
        filing_status="single",
        adults=[Person(name="adult1", age=35, employment_income=50_000.0)],
        children=[],
        year=2026,
    )


@pytest.fixture
def family_scenario():
    """Joint filers, 2 kids, $100k combined income in TX."""
    return Scenario(
        id="test_family",
        state="TX",
        filing_status="joint",
        adults=[
            Person(name="adult1", age=40, employment_income=70_000.0),
            Person(name="adult2", age=38, employment_income=30_000.0),
        ],
        children=[
            Person(name="child1", age=10, employment_income=0.0),
            Person(name="child2", age=5, employment_income=0.0),
        ],
        year=2026,
    )


@pytest.fixture
def low_income_scenario():
    """Single parent, 2 kids, $15k income in NY (EITC/SNAP eligible)."""
    return Scenario(
        id="test_low_income",
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
def sample_scenarios(simple_single_scenario, family_scenario, low_income_scenario):
    """A small set of test scenarios."""
    return [simple_single_scenario, family_scenario, low_income_scenario]
