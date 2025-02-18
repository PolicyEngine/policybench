# tests/test_households.py
import pytest
from policybench.households import generate_random_household, generate_scenarios


def test_generate_random_household():
    sc = generate_random_household(n_adults=2, n_children=3, year=2025, state="NY")
    assert "people" in sc
    assert "households" in sc
    hh_key = list(sc["households"].keys())[0]
    assert sc["households"][hh_key]["state_name"]["2025"] == "NY"
    # More checks here


def test_generate_scenarios():
    scenarios = generate_scenarios(num_scenarios=3, year=2025)
    assert len(scenarios) == 3
    for sc in scenarios:
        assert "people" in sc
        # etc.
