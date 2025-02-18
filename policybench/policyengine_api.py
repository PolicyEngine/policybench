# my_llm_benchmark/policyengine_api.py
import numpy as np
from typing import Dict, Any
from policyengine_us import Simulation


def compute_ground_truth(
    program: str, scenario: Dict[str, Any], year: int = 2025
) -> float:
    """
    Given a program name (e.g. 'eitc', 'snap', 'household_net_income'),
    a year, and a household scenario (dict), compute the ground truth with PolicyEngine.

    Returns a float. If there's only one household in scenario, we take index 0.
    """
    sim = Simulation(situation=scenario)
    result = sim.calculate(program, year, map_to="household")
    return float(result[0])
