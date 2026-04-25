"""Reference-output calculations using PolicyEngine."""

import os
from typing import Any

import pandas as pd

from policybench.config import DEFAULT_COUNTRY, TAX_YEAR, get_programs
from policybench.scenarios import Scenario, get_uk_dataset_path
from policybench.spec import find_output_spec

# These benchmark variables are household-level boolean labels derived from
# PolicyEngine outputs that are naturally person-level or dollar-valued.
DERIVED_HOUSEHOLD_BOOLEAN_VARIABLES = {
    "free_school_meals",
    "household_free_school_meal_eligible",
    "household_reduced_price_school_meal_eligible",
    "is_medicaid_eligible",
    "household_medicaid_eligible",
    "household_chip_eligible",
    "household_medicare_eligible",
    "any_medicaid_eligible",
    "any_chip_eligible",
    "any_medicare_eligible",
    "free_school_meals_eligible",
    "reduced_price_school_meals_eligible",
}


def _pe_variable_for_output(variable: str, country: str) -> str:
    output = find_output_spec(variable, country=country)
    return output.pe_variable if output is not None else variable


def _aggregation_for_output(variable: str, country: str) -> str:
    output = find_output_spec(variable, country=country)
    if output is not None:
        return output.aggregation
    if variable in DERIVED_HOUSEHOLD_BOOLEAN_VARIABLES:
        return "any_positive"
    return "sum"


def _impact_weight_variable_for_output(variable: str, country: str) -> str | None:
    output = find_output_spec(variable, country=country)
    return output.impact_weight_variable if output is not None else None


def _impact_weight_aggregation_for_output(variable: str, country: str) -> str:
    output = find_output_spec(variable, country=country)
    if output is None or output.impact_weight_aggregation is None:
        return _aggregation_for_output(variable, country)
    return output.impact_weight_aggregation


def _extract_scalar_value(
    result,
    variable: str,
    country: str = DEFAULT_COUNTRY,
) -> float:
    """Convert a PolicyEngine result array into the benchmark scalar."""
    value = float(result.sum())
    if _aggregation_for_output(variable, country) == "any_positive":
        return float(value > 0)
    return value


def _extract_scalar_with_aggregation(result, aggregation: str) -> float:
    value = float(result.sum())
    if aggregation == "any_positive":
        return float(value > 0)
    return value


def _extract_impact_weight(
    value_result,
    weight_result,
    variable: str,
    country: str = DEFAULT_COUNTRY,
) -> float:
    """Convert an auxiliary PolicyEngine result into an impact-score weight."""
    output = find_output_spec(variable, country=country)
    if output is not None and output.metric_type == "binary":
        try:
            if len(value_result) == len(weight_result):
                weight_result = weight_result * (value_result > 0)
        except TypeError:
            pass

    weight = _extract_scalar_with_aggregation(
        weight_result,
        _impact_weight_aggregation_for_output(variable, country),
    )
    return abs(weight)


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
    pe_variable = _pe_variable_for_output(variable, scenario.country)
    return _extract_scalar_value(
        sim.calculate(pe_variable, year),
        variable,
        scenario.country,
    )


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
            pe_variable = _pe_variable_for_output(variable, "us")
            value_result = sim.calculate(pe_variable, year)
            value = _extract_scalar_value(value_result, variable, "us")
            impact_weight = None
            impact_weight_variable = _impact_weight_variable_for_output(variable, "us")
            if impact_weight_variable is not None:
                impact_weight = _extract_impact_weight(
                    value_result,
                    sim.calculate(impact_weight_variable, year),
                    variable,
                    "us",
                )
            rows.append(
                {
                    "scenario_id": scenario.id,
                    "variable": variable,
                    "value": value,
                    "impact_weight": impact_weight,
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
        pe_variable = _pe_variable_for_output(variable, "uk")
        entity_key = sim.tax_benefit_system.variables[pe_variable].entity.key
        values = _aggregate_uk_variable_to_households(
            sim=sim,
            variable=pe_variable,
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
                    "impact_weight": None,
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
        return pd.DataFrame(
            columns=["scenario_id", "variable", "value", "impact_weight"]
        )

    country = scenarios[0].country or DEFAULT_COUNTRY
    if any(scenario.country != country for scenario in scenarios):
        raise ValueError(
            "All scenarios in one ground-truth batch must share a country."
        )

    if programs is None:
        programs = get_programs(country)

    if country == "us":
        return _calculate_ground_truth_us(scenarios, programs, year)
    if country == "uk":
        return _calculate_ground_truth_uk(scenarios, programs, year)
    raise ValueError(f"Unsupported country '{country}'")
