"""Ground truth calculations using PolicyEngine-US."""

import os
from typing import Any

import pandas as pd

from policybench.config import DEFAULT_COUNTRY, PROGRAMS, TAX_YEAR, get_programs
from policybench.scenarios import Scenario, get_uk_dataset_path

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
    """Calculate a single variable for a scenario."""
    if scenario.country == "uk":
        return calculate_ground_truth([scenario], programs=[variable], year=year)[
            "value"
        ].iloc[0]

    household = scenario.to_pe_household()
    from policyengine_us import Simulation

    sim = Simulation(situation=household)
    return _extract_scalar_value(sim.calculate(variable, year), variable)


def _calculate_ground_truth_us(
    scenarios: list[Scenario],
    programs: list[str],
    year: int,
) -> pd.DataFrame:
    from policyengine_us import Simulation

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


def _calculate_ground_truth_uk(
    scenarios: list[Scenario],
    programs: list[str],
    year: int,
) -> pd.DataFrame:
    from policyengine_uk import Microsimulation as UKMicrosimulation
    from policyengine_uk.data import UKSingleYearDataset

    os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
    dataset = UKSingleYearDataset(file_path=str(get_uk_dataset_path()))
    sim = UKMicrosimulation(dataset=dataset)
    period = str(year)

    person_household_ids = pd.Series(
        sim.calculate("person_household_id", period, map_to="person", unweighted=True)
    ).astype(int)
    person_benunit_ids = pd.Series(
        sim.calculate("person_benunit_id", period, map_to="person", unweighted=True)
    ).astype(int)
    benunit_households = (
        pd.DataFrame(
            {
                "benunit_id": person_benunit_ids.to_numpy(),
                "household_id": person_household_ids.to_numpy(),
            }
        )
        .drop_duplicates(subset=["benunit_id"])
        .set_index("benunit_id")["household_id"]
    )
    household_ids = pd.Series(
        sim.calculate("household_id", period, map_to="household", unweighted=True)
    ).astype(int)

    rows = []
    scenario_household_ids = {
        scenario.id: int(scenario.metadata["household_id"]) for scenario in scenarios
    }
    for variable in programs:
        entity_key = sim.tax_benefit_system.variables[variable].entity.key
        values = _aggregate_uk_variable_to_households(
            sim=sim,
            variable=variable,
            period=period,
            entity_key=entity_key,
            person_household_ids=person_household_ids,
            benunit_households=benunit_households,
            household_ids=household_ids,
        )
        for scenario in scenarios:
            rows.append(
                {
                    "scenario_id": scenario.id,
                    "variable": variable,
                    "value": float(values.loc[scenario_household_ids[scenario.id]]),
                }
            )
    return pd.DataFrame(rows)


def _aggregate_uk_variable_to_households(
    sim: Any,
    variable: str,
    period: str,
    entity_key: str,
    person_household_ids: pd.Series,
    benunit_households: pd.Series,
    household_ids: pd.Series,
) -> pd.Series:
    """Aggregate a UK variable from its native entity to household level."""
    if entity_key == "person":
        values = pd.Series(
            sim.calculate(variable, period, map_to="person", unweighted=True)
        )
        return values.groupby(person_household_ids).sum()

    if entity_key == "benunit":
        benunit_ids = pd.Series(
            sim.calculate("benunit_id", period, map_to="benunit", unweighted=True)
        ).astype(int)
        values = pd.DataFrame(
            {
                "value": sim.calculate(
                    variable, period, map_to="benunit", unweighted=True
                ),
                "household_id": benunit_households.reindex(benunit_ids).to_numpy(),
            }
        )
        return values.groupby("household_id")["value"].sum()

    if entity_key == "household":
        values = pd.Series(
            sim.calculate(variable, period, map_to="household", unweighted=True),
            index=household_ids,
        )
        return values.groupby(level=0).sum()

    raise ValueError(
        f"Unsupported UK entity '{entity_key}' for benchmark variable '{variable}'."
    )


def calculate_ground_truth(
    scenarios: list[Scenario],
    programs: list[str] | None = None,
    year: int = TAX_YEAR,
) -> pd.DataFrame:
    """Calculate ground truth for all scenarios × programs.

    Returns a DataFrame with columns: scenario_id, variable, value
    """
    if not scenarios:
        return pd.DataFrame(columns=["scenario_id", "variable", "value"])

    country = scenarios[0].country or DEFAULT_COUNTRY
    if any(scenario.country != country for scenario in scenarios):
        raise ValueError(
            "All scenarios in one ground-truth batch must share a country."
        )

    if programs is None:
        programs = get_programs(country) if country != DEFAULT_COUNTRY else PROGRAMS

    if country == "us":
        return _calculate_ground_truth_us(scenarios, programs, year)
    if country == "uk":
        return _calculate_ground_truth_uk(scenarios, programs, year)
    raise ValueError(f"Unsupported country '{country}'")
