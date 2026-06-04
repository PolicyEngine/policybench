"""Reference-output calculations using PolicyEngine."""

import os
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from policybench.config import DEFAULT_COUNTRY, TAX_YEAR, get_programs
from policybench.policyengine_runtime import (
    get_us_situation_simulation_class,
    make_uk_transfer_microsimulation,
)
from policybench.scenarios import Scenario, get_uk_dataset_path
from policybench.spec import (
    expand_programs_for_scenario,
    find_output_spec,
    parse_person_output,
)


@dataclass(frozen=True)
class _USScenarioEntityIndex:
    person_indices: dict[str, int]
    marital_unit_indices: tuple[int, ...]
    tax_unit_indices: tuple[int, ...]
    spm_unit_indices: tuple[int, ...]
    family_indices: tuple[int, ...]
    household_indices: tuple[int, ...]


def _pe_variable_for_output(variable: str, country: str) -> str:
    parsed_person_output = parse_person_output(variable)
    if parsed_person_output is not None:
        return parsed_person_output[2]["pe_variable"]
    output = find_output_spec(variable, country=country)
    return output.pe_variable if output is not None else variable


def _aggregation_for_output(variable: str, country: str) -> str:
    if parse_person_output(variable) is not None:
        return "person"
    output = find_output_spec(variable, country=country)
    if output is not None:
        return output.aggregation
    return "sum"


def _impact_weight_variable_for_output(variable: str, country: str) -> str | None:
    parsed_person_output = parse_person_output(variable)
    if parsed_person_output is not None:
        return parsed_person_output[2].get("impact_weight_variable")
    output = find_output_spec(variable, country=country)
    return output.impact_weight_variable if output is not None else None


def _impact_weight_aggregation_for_output(variable: str, country: str) -> str:
    output = find_output_spec(variable, country=country)
    if output is None:
        return "sum"
    if output.impact_weight_aggregation is None:
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


def _person_index_for_output(scenario: Scenario, variable: str) -> int | None:
    parsed_person_output = parse_person_output(variable)
    if parsed_person_output is None:
        return None
    person_name = parsed_person_output[0]
    for index, person in enumerate(scenario.all_people):
        if person.name == person_name:
            return index
    raise ValueError(
        f"Output '{variable}' refers to {person_name}, but that person is not "
        f"present in scenario '{scenario.id}'."
    )


def _extract_person_value(result, scenario: Scenario, variable: str) -> float:
    person_index = _person_index_for_output(scenario, variable)
    if person_index is None:
        return _extract_scalar_value(result, variable, scenario.country)
    if len(result) <= person_index:
        raise ValueError(
            f"PolicyEngine returned {len(result)} values for '{variable}', "
            f"but scenario '{scenario.id}' needs person index {person_index}."
        )
    return float(result[person_index])


def _extract_scalar_with_aggregation(result, aggregation: str) -> float:
    value = float(result.sum())
    if aggregation == "any_positive":
        return float(value > 0)
    return value


def _us_entity_indices(
    index: _USScenarioEntityIndex,
    entity_key: str,
) -> tuple[int, ...]:
    if entity_key == "person":
        return tuple(index.person_indices.values())
    if entity_key == "marital_unit":
        return index.marital_unit_indices
    if entity_key == "tax_unit":
        return index.tax_unit_indices
    if entity_key == "spm_unit":
        return index.spm_unit_indices
    if entity_key == "family":
        return index.family_indices
    if entity_key == "household":
        return index.household_indices
    raise ValueError(f"Unsupported US entity '{entity_key}'.")


def _us_entity_indices_for_output(
    scenario: Scenario,
    variable: str,
    entity_key: str,
    index: _USScenarioEntityIndex,
) -> tuple[int, ...]:
    parsed_person_output = parse_person_output(variable)
    if parsed_person_output is not None and entity_key == "person":
        person_name = parsed_person_output[0]
        if person_name not in index.person_indices:
            raise ValueError(
                f"Output '{variable}' refers to {person_name}, but that person "
                f"is not present in scenario '{scenario.id}'."
            )
        return (index.person_indices[person_name],)
    return _us_entity_indices(index, entity_key)


def _extract_impact_weight(
    value_result,
    weight_result,
    variable: str,
    country: str = DEFAULT_COUNTRY,
) -> float:
    """Convert an auxiliary PolicyEngine result into an impact-score weight."""
    output = find_output_spec(variable, country=country)
    if (
        output is not None and output.metric_type == "binary"
    ) or _aggregation_for_output(variable, country) == "any_positive":
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


def _extract_person_impact_weight(
    value_result,
    weight_result,
    scenario: Scenario,
    variable: str,
) -> float:
    person_index = _person_index_for_output(scenario, variable)
    if person_index is None:
        return _extract_impact_weight(
            value_result,
            weight_result,
            variable,
            scenario.country,
        )
    if len(value_result) <= person_index or len(weight_result) <= person_index:
        raise ValueError(
            f"PolicyEngine returned too few values for '{variable}' in "
            f"scenario '{scenario.id}'."
        )
    if float(value_result[person_index]) <= 0:
        return 0.0
    return abs(float(weight_result[person_index]))


def _copy_us_entity_data(
    entity_data: dict[str, Any],
    person_name_map: dict[str, str],
) -> dict[str, Any]:
    copied = dict(entity_data)
    if "members" in copied:
        copied["members"] = [person_name_map[member] for member in copied["members"]]
    return copied


def _build_us_vectorized_situation(
    scenarios: list[Scenario],
) -> tuple[dict[str, dict[str, Any]], dict[str, _USScenarioEntityIndex]]:
    """Build one PE-US situation containing all benchmark scenarios."""
    entity_id_variables = {
        "marital_units": "marital_unit_id",
        "tax_units": "tax_unit_id",
        "spm_units": "spm_unit_id",
        "families": "family_id",
        "households": "household_id",
    }
    person_entity_id_variables = {
        "marital_units": "person_marital_unit_id",
        "tax_units": "person_tax_unit_id",
        "spm_units": "person_spm_unit_id",
        "families": "person_family_id",
        "households": "person_household_id",
    }
    combined = {
        "people": {},
        "marital_units": {},
        "tax_units": {},
        "spm_units": {},
        "families": {},
        "households": {},
    }
    scenario_indexes: dict[str, _USScenarioEntityIndex] = {}

    for scenario_position, scenario in enumerate(scenarios):
        if scenario.id in scenario_indexes:
            raise ValueError(f"Duplicate scenario id '{scenario.id}'.")
        situation = scenario.to_pe_household()
        situation.setdefault(
            "marital_units",
            {"marital_unit": {"members": list(situation["people"])}},
        )
        prefix = f"scenario{scenario_position}"
        person_name_map: dict[str, str] = {}
        person_indices: dict[str, int] = {}
        period = str(scenario.year)
        person_entity_ids = {person_name: {} for person_name in situation["people"]}
        source_entity_ids: dict[str, dict[str, int]] = {}

        for entity_group in (
            "marital_units",
            "tax_units",
            "spm_units",
            "families",
            "households",
        ):
            source_entity_ids[entity_group] = {}
            person_id_variable = person_entity_id_variables[entity_group]
            for entity_name, entity_data in situation[entity_group].items():
                entity_id = len(combined[entity_group]) + len(
                    source_entity_ids[entity_group]
                )
                source_entity_ids[entity_group][entity_name] = entity_id
                for member in entity_data["members"]:
                    person_entity_ids[member][person_id_variable] = entity_id

        for person_name, person_data in situation["people"].items():
            prefixed_name = f"{prefix}_{person_name}"
            person_name_map[person_name] = prefixed_name
            person_indices[person_name] = len(combined["people"])
            copied_person_data = dict(person_data)
            for variable, entity_id in person_entity_ids[person_name].items():
                copied_person_data[variable] = {period: entity_id}
            combined["people"][prefixed_name] = copied_person_data

        entity_indices: dict[str, tuple[int, ...]] = {}
        for entity_group in (
            "marital_units",
            "tax_units",
            "spm_units",
            "families",
            "households",
        ):
            indices = []
            for entity_name, entity_data in situation[entity_group].items():
                prefixed_name = f"{prefix}_{entity_name}"
                entity_id = source_entity_ids[entity_group][entity_name]
                indices.append(entity_id)
                copied_entity_data = _copy_us_entity_data(
                    entity_data,
                    person_name_map,
                )
                copied_entity_data[entity_id_variables[entity_group]] = {
                    period: entity_id
                }
                combined[entity_group][prefixed_name] = copied_entity_data
            entity_indices[entity_group] = tuple(indices)

        scenario_indexes[scenario.id] = _USScenarioEntityIndex(
            person_indices=person_indices,
            marital_unit_indices=entity_indices["marital_units"],
            tax_unit_indices=entity_indices["tax_units"],
            spm_unit_indices=entity_indices["spm_units"],
            family_indices=entity_indices["families"],
            household_indices=entity_indices["households"],
        )

    return combined, scenario_indexes


def _extract_us_vectorized_value(
    value_result: np.ndarray,
    *,
    scenario: Scenario,
    variable: str,
    entity_key: str,
    index: _USScenarioEntityIndex,
) -> float:
    indices = _us_entity_indices_for_output(scenario, variable, entity_key, index)
    return _extract_scalar_with_aggregation(
        value_result[list(indices)],
        _aggregation_for_output(variable, "us"),
    )


def _extract_us_vectorized_impact_weight(
    value_result: np.ndarray,
    weight_result: np.ndarray,
    *,
    scenario: Scenario,
    variable: str,
    value_entity_key: str,
    weight_entity_key: str,
    index: _USScenarioEntityIndex,
) -> float:
    parsed_person_output = parse_person_output(variable)
    if parsed_person_output is not None:
        person_name = parsed_person_output[0]
        person_index = index.person_indices[person_name]
        if float(value_result[person_index]) <= 0:
            return 0.0
        return abs(float(weight_result[person_index]))

    value_indices = _us_entity_indices_for_output(
        scenario,
        variable,
        value_entity_key,
        index,
    )
    weight_indices = _us_entity_indices_for_output(
        scenario,
        variable,
        weight_entity_key,
        index,
    )
    return _extract_impact_weight(
        value_result[list(value_indices)],
        weight_result[list(weight_indices)],
        variable,
        "us",
    )


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
    Simulation = get_us_situation_simulation_class()
    sim = Simulation(situation=household)
    pe_variable = _pe_variable_for_output(variable, scenario.country)
    return _extract_person_value(
        sim.calculate(pe_variable, year),
        scenario,
        variable,
    )


def _calculate_ground_truth_us_scalar(
    scenarios: list[Scenario],
    programs: list[str],
    year: int,
) -> pd.DataFrame:
    Simulation = get_us_situation_simulation_class()
    rows = []
    for scenario in scenarios:
        sim = Simulation(situation=scenario.to_pe_household())
        for variable in expand_programs_for_scenario(programs, scenario):
            pe_variable = _pe_variable_for_output(variable, "us")
            value_result = sim.calculate(pe_variable, year)
            value = _extract_person_value(value_result, scenario, variable)
            impact_weight = None
            impact_weight_variable = _impact_weight_variable_for_output(variable, "us")
            if impact_weight_variable is not None:
                impact_weight = _extract_person_impact_weight(
                    value_result,
                    sim.calculate(impact_weight_variable, year),
                    scenario,
                    variable,
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


def _calculate_ground_truth_us(
    scenarios: list[Scenario],
    programs: list[str],
    year: int,
) -> pd.DataFrame:
    Simulation = get_us_situation_simulation_class()
    situation, scenario_indexes = _build_us_vectorized_situation(scenarios)
    sim = Simulation(situation=situation)

    variable_cache: dict[str, tuple[np.ndarray, str]] = {}

    def calculate_variable(variable: str) -> tuple[np.ndarray, str]:
        if variable not in variable_cache:
            entity_key = sim.tax_benefit_system.variables[variable].entity.key
            variable_cache[variable] = (
                np.asarray(sim.calculate(variable, year)),
                entity_key,
            )
        return variable_cache[variable]

    rows = []
    for scenario in scenarios:
        index = scenario_indexes[scenario.id]
        for variable in expand_programs_for_scenario(programs, scenario):
            pe_variable = _pe_variable_for_output(variable, "us")
            value_result, value_entity_key = calculate_variable(pe_variable)
            value = _extract_us_vectorized_value(
                value_result,
                scenario=scenario,
                variable=variable,
                entity_key=value_entity_key,
                index=index,
            )
            impact_weight = None
            impact_weight_variable = _impact_weight_variable_for_output(variable, "us")
            if impact_weight_variable is not None:
                weight_result, weight_entity_key = calculate_variable(
                    impact_weight_variable,
                )
                impact_weight = _extract_us_vectorized_impact_weight(
                    value_result,
                    weight_result,
                    scenario=scenario,
                    variable=variable,
                    value_entity_key=value_entity_key,
                    weight_entity_key=weight_entity_key,
                    index=index,
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
    os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
    sim = make_uk_transfer_microsimulation(get_uk_dataset_path())
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
    variables = sorted(
        {
            variable
            for scenario in scenarios
            for variable in expand_programs_for_scenario(programs, scenario)
        }
    )
    for variable in variables:
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
    """Calculate PolicyEngine reference outputs for all scenarios × programs.

    Returns a DataFrame with columns: scenario_id, variable, value
    """
    if not scenarios:
        return pd.DataFrame(
            columns=["scenario_id", "variable", "value", "impact_weight"]
        )

    country = scenarios[0].country or DEFAULT_COUNTRY
    if any(scenario.country != country for scenario in scenarios):
        raise ValueError(
            "All scenarios in one reference-output batch must share a country."
        )

    if programs is None:
        programs = get_programs(country)

    if country == "us":
        return _calculate_ground_truth_us(scenarios, programs, year)
    if country == "uk":
        return _calculate_ground_truth_uk(scenarios, programs, year)
    raise ValueError(f"Unsupported country '{country}'")
