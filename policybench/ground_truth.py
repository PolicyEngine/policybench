"""Ground truth calculations using PolicyEngine-US."""

import pandas as pd
from policyengine_us import Simulation

from policybench.config import PROGRAMS, TAX_YEAR
from policybench.scenarios import Scenario

HOUSEHOLD_BOOLEAN_VARIABLES = {
    "free_school_meals",
    "is_medicaid_eligible",
}


def _extract_scalar_value(result, variable: str) -> float:
    """Convert a PolicyEngine result array into the benchmark scalar."""
    value = float(result.sum())
    if variable in HOUSEHOLD_BOOLEAN_VARIABLES:
        return float(value > 0)
    return value


def calculate_single(
    scenario: Scenario,
    variable: str,
    year: int = TAX_YEAR,
) -> float:
    """Calculate a single variable for a scenario using PE-US."""
    household = scenario.to_pe_household()
    sim = Simulation(situation=household)
    return _extract_scalar_value(sim.calculate(variable, year), variable)


def calculate_ground_truth(
    scenarios: list[Scenario],
    programs: list[str] | None = None,
    year: int = TAX_YEAR,
) -> pd.DataFrame:
    """Calculate ground truth for all scenarios × programs.

    Returns a DataFrame with columns: scenario_id, variable, value
    """
    if programs is None:
        programs = PROGRAMS

    rows = []
    for scenario in scenarios:
        sim = Simulation(situation=scenario.to_pe_household())
        for variable in programs:
            value = _extract_scalar_value(sim.calculate(variable, year), variable)
            rows.append(
                {
                    "scenario_id": scenario.id,
                    "variable": variable,
                    "value": value,
                }
            )

    return pd.DataFrame(rows)
