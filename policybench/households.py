import random
import math
from typing import Dict, Any, List


def generate_random_household(
    n_adults=2, n_children=2, year=2025, state="CA"
) -> Dict[str, Any]:
    """
    Returns a PolicyEngine scenario dict, with random incomes for the specified
    number of adults/children, set in the given 'state' for 'year'.
    You can expand logic to vary ages, etc.
    """
    scenario = {
        "people": {},
        "families": {},
        "marital_units": {},
        "tax_units": {},
        "spm_units": {},
        "households": {},
    }

    # Create people
    people_keys = []
    for i in range(n_adults):
        pid = f"adult{i+1}"
        scenario["people"][pid] = {
            "age": {str(year): random.randint(25, 60)},
            "employment_income": {str(year): random.randint(0, 50000)},
        }
        people_keys.append(pid)

    for j in range(n_children):
        pid = f"child{j+1}"
        scenario["people"][pid] = {
            "age": {str(year): random.randint(1, 17)},
            "employment_income": {str(year): 0},
        }
        people_keys.append(pid)

    # One family, household, etc. (Simplistic: everyone in same family)
    scenario["families"] = {"fam1": {"members": people_keys}}
    scenario["marital_units"] = {
        "mar1": {"members": people_keys},
    }
    scenario["tax_units"] = {"tax1": {"members": people_keys}}
    scenario["spm_units"] = {"spm1": {"members": people_keys}}
    scenario["households"] = {
        "hh1": {"members": people_keys, "state_name": {str(year): state}}
    }
    return scenario


def generate_scenarios(num_scenarios=2, year=2025, state="CA") -> List[Dict[str, Any]]:
    """
    Returns a list of randomly generated scenario dicts.
    Tweak logic to produce more variety (different states, child counts, etc.).
    """
    scenarios = []
    for _ in range(num_scenarios):
        n_adults = random.choice([1, 2])  # random 1 or 2 adults
        n_children = random.choice([0, 1, 2, 3])  # random up to 3 kids
        st = random.choice(["CA", "NY", "TX", "FL", "MA"])  # random among 5 states
        sc = generate_random_household(n_adults, n_children, year, st)
        scenarios.append(sc)
    return scenarios
