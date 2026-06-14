"""Population-derived output weights for PolicyBench scoring.

The benchmark evaluates a fixed sample of households, but the output weights
should reflect policy importance in the full source populations. This module
loads a committed weight artifact and contains the generator used to rebuild it
from the full US Enhanced CPS and UK enhanced FRS microsimulation datasets.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from policybench.config import TAX_YEAR
from policybench.spec import get_output_specs

WEIGHT_ARTIFACT = Path(__file__).with_name("population_weights.json")
UK_FULL_EFRS_DATASET = (
    "hf://policyengine/policyengine-uk-data-private/enhanced_frs_2023_24.h5"
)


def normalize_weights(weights: pd.Series) -> pd.Series:
    """Normalize nonnegative weights to sum to one."""
    weights = pd.to_numeric(weights, errors="coerce").fillna(0.0).astype(float)
    weights = weights.clip(lower=0.0)
    total = float(weights.sum())
    if total <= 0:
        return weights
    return weights / total


def load_population_weight_payload(
    path: str | Path = WEIGHT_ARTIFACT,
) -> dict[str, Any]:
    """Load the committed population-weight artifact."""
    artifact_path = Path(path)
    if not artifact_path.exists():
        return {"countries": {}}
    return json.loads(artifact_path.read_text(encoding="utf-8"))


def population_weight_series(
    country: str,
    kind: str = "household",
    *,
    path: str | Path = WEIGHT_ARTIFACT,
) -> pd.Series:
    """Return population-derived weights for one country and weighting kind."""
    payload = load_population_weight_payload(path)
    country_payload = payload.get("countries", {}).get(country, {})
    weights = country_payload.get("weights", {}).get(kind, {})
    return normalize_weights(pd.Series(weights, dtype=float))


def matching_population_weight_series(
    country: str | None,
    kind: str,
    output_groups: list[str],
) -> pd.Series | None:
    """Return population weights if they fully cover the requested output groups.

    Tests and ad hoc analyses often use toy variable names that are not part of
    the canonical benchmark. In that case callers should fall back to weights
    computed from the supplied DataFrame.
    """
    if not country:
        return None
    weights = population_weight_series(country, kind)
    if weights.empty:
        return None
    unique_groups = list(dict.fromkeys(output_groups))
    if not set(unique_groups).issubset(set(weights.index)):
        return None
    return normalize_weights(weights.reindex(unique_groups).fillna(0.0))


def _weighted_mean_by_household(
    contributions: pd.DataFrame,
    household_net_income: pd.Series,
    household_weight: pd.Series,
) -> pd.Series:
    abs_total = contributions.sum(axis=1)
    denom = pd.concat([household_net_income.abs(), abs_total], axis=1).max(axis=1)
    shares = contributions.div(denom.where(denom > 0), axis=0).fillna(0.0)
    total_weight = float(household_weight.sum())
    if total_weight <= 0:
        return pd.Series(0.0, index=contributions.columns, dtype=float)
    return shares.mul(household_weight, axis=0).sum(axis=0) / total_weight


def _weights_from_contributions(
    *,
    country: str,
    contributions: pd.DataFrame,
    household_net_income: pd.Series,
    household_weight: pd.Series,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    valid = (
        household_weight.replace([np.inf, -np.inf], np.nan).notna()
        & household_net_income.replace([np.inf, -np.inf], np.nan).notna()
        & (household_weight > 0)
    )
    contributions = contributions.loc[valid].fillna(0.0).abs()
    household_net_income = household_net_income.loc[valid].astype(float)
    household_weight = household_weight.loc[valid].astype(float)

    household_raw = _weighted_mean_by_household(
        contributions,
        household_net_income,
        household_weight,
    )
    aggregate_raw = contributions.mul(household_weight, axis=0).sum(axis=0)
    equal_raw = pd.Series(1.0, index=contributions.columns, dtype=float)

    return {
        "country": country,
        "metadata": {
            **metadata,
            "positive_weight_households": int(len(contributions)),
            "total_household_weight": float(household_weight.sum()),
        },
        "weights": {
            "household": normalize_weights(household_raw).to_dict(),
            "aggregate": normalize_weights(aggregate_raw).to_dict(),
            "equal": normalize_weights(equal_raw).to_dict(),
        },
        "raw": {
            "household": household_raw.to_dict(),
            "aggregate": aggregate_raw.to_dict(),
        },
    }


def _series_by_household(
    values: np.ndarray,
    household_ids: pd.Series,
) -> pd.Series:
    return (
        pd.Series(np.asarray(values, dtype=float), index=household_ids)
        .groupby(level=0)
        .sum()
    )


def _us_population_contributions(year: int) -> dict[str, Any]:
    from policybench.policyengine_runtime import make_us_microsimulation

    sim = make_us_microsimulation()
    bundle = sim.policyengine_bundle
    outputs = get_output_specs("us", "headline")
    household_ids = pd.Series(
        sim.calculate("household_id", year, map_to="household", use_weights=False)
    ).astype(int)
    household_weight = _series_by_household(
        sim.calculate("household_weight", year, map_to="household", use_weights=False),
        household_ids,
    )
    household_net_income = _series_by_household(
        sim.calculate(
            "household_net_income",
            year,
            map_to="household",
            use_weights=False,
        ),
        household_ids,
    )
    person_household_ids = pd.Series(
        sim.calculate("person_household_id", year, map_to="person", use_weights=False)
    ).astype(int)

    contributions = pd.DataFrame(index=household_weight.index)
    for output in outputs:
        if output.impact_weight_variable is not None and output.aggregation == "person":
            values = np.asarray(
                sim.calculate(
                    output.pe_variable,
                    year,
                    map_to="person",
                    use_weights=False,
                ),
                dtype=float,
            )
            impact_values = np.asarray(
                sim.calculate(
                    output.impact_weight_variable,
                    year,
                    map_to="person",
                    use_weights=False,
                ),
                dtype=float,
            )
            contribution = (values > 0) * np.abs(impact_values)
            series = pd.Series(contribution).groupby(person_household_ids).sum()
        else:
            values = np.asarray(
                sim.calculate(
                    output.pe_variable,
                    year,
                    map_to="household",
                    use_weights=False,
                ),
                dtype=float,
            )
            if output.aggregation == "any_positive":
                impact_variable = output.impact_weight_variable or output.pe_variable
                impact_values = np.asarray(
                    sim.calculate(
                        impact_variable,
                        year,
                        map_to="household",
                        use_weights=False,
                    ),
                    dtype=float,
                )
                values = (values > 0) * np.abs(impact_values)
            series = _series_by_household(values, household_ids)
        contributions[output.id] = series.reindex(contributions.index).fillna(0.0)

    return _weights_from_contributions(
        country="us",
        contributions=contributions,
        household_net_income=household_net_income,
        household_weight=household_weight,
        metadata={
            "source_dataset": "full PolicyEngine US Enhanced CPS",
            "source_dataset_uri": bundle["default_dataset_uri"],
            "policyengine_version": bundle["policyengine_version"],
            "policyengine_bundle_id": bundle["bundle_id"],
            "policyengine_model_version": bundle["model_version"],
            "policyengine_data_version": bundle["data_version"],
            "certified_data_build_id": bundle["certified_data_build_id"],
            "certified_data_artifact_sha256": bundle["certified_data_artifact_sha256"],
            "source_household_rows": int(len(household_ids)),
            "tax_year": year,
        },
    )


def _aggregate_uk_to_households(
    sim: Any,
    variable: str,
    period: str,
    entity_key: str,
    household_ids: pd.Series,
    person_household_ids: pd.Series,
    benunit_households: pd.Series,
) -> pd.Series:
    if entity_key == "person":
        values = pd.Series(
            sim.calculate(variable, period, map_to="person", unweighted=True),
            dtype=float,
        )
        return values.groupby(person_household_ids).sum()
    if entity_key == "benunit":
        benunit_ids = pd.Series(
            sim.calculate("benunit_id", period, map_to="benunit", unweighted=True)
        ).astype(int)
        values = pd.Series(
            sim.calculate(variable, period, map_to="benunit", unweighted=True),
            dtype=float,
        )
        return (
            pd.DataFrame(
                {
                    "value": values.to_numpy(),
                    "household_id": benunit_households.reindex(benunit_ids).to_numpy(),
                }
            )
            .groupby("household_id")["value"]
            .sum()
        )
    if entity_key == "household":
        values = pd.Series(
            sim.calculate(variable, period, map_to="household", unweighted=True),
            index=household_ids,
            dtype=float,
        )
        return values.groupby(level=0).sum()
    raise ValueError(f"Unsupported UK entity '{entity_key}' for '{variable}'.")


def _uk_population_contributions(year: int) -> dict[str, Any]:
    from policyengine_uk import Microsimulation

    sim = Microsimulation(dataset=UK_FULL_EFRS_DATASET)
    period = str(year)
    outputs = get_output_specs("uk", "headline")
    household_ids = pd.Series(
        sim.calculate("household_id", period, map_to="household", unweighted=True)
    ).astype(int)
    household_weight = (
        pd.Series(
            sim.calculate(
                "household_weight", period, map_to="household", unweighted=True
            ),
            index=household_ids,
            dtype=float,
        )
        .groupby(level=0)
        .sum()
    )
    household_net_income = (
        pd.Series(
            sim.calculate(
                "household_net_income",
                period,
                map_to="household",
                unweighted=True,
            ),
            index=household_ids,
            dtype=float,
        )
        .groupby(level=0)
        .sum()
    )
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

    contributions = pd.DataFrame(index=household_weight.index)
    for output in outputs:
        entity_key = sim.tax_benefit_system.variables[output.pe_variable].entity.key
        series = _aggregate_uk_to_households(
            sim=sim,
            variable=output.pe_variable,
            period=period,
            entity_key=entity_key,
            household_ids=household_ids,
            person_household_ids=person_household_ids,
            benunit_households=benunit_households,
        )
        contributions[output.id] = series.reindex(contributions.index).fillna(0.0)

    return _weights_from_contributions(
        country="uk",
        contributions=contributions,
        household_net_income=household_net_income,
        household_weight=household_weight,
        metadata={
            "source_dataset": "full PolicyEngine UK enhanced FRS",
            "source_dataset_uri": UK_FULL_EFRS_DATASET,
            "source_household_rows": int(len(household_ids)),
            "tax_year": year,
        },
    )


def generate_population_weight_payload(
    countries: list[str] | None = None,
    *,
    year: int = TAX_YEAR,
) -> dict[str, Any]:
    """Generate the full population-weight payload."""
    selected = countries or ["us", "uk"]
    generators = {
        "us": _us_population_contributions,
        "uk": _uk_population_contributions,
    }
    payload = {
        "metadata": {
            "metadata_version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "tax_year": year,
            "method": (
                "Weighted mean of each output's absolute household net-income "
                "contribution share using full source microsimulation datasets."
            ),
        },
        "countries": {},
    }
    for country in selected:
        if country not in generators:
            raise ValueError(f"Unsupported country '{country}'.")
        payload["countries"][country] = generators[country](year)
    return payload


def write_population_weight_payload(
    path: str | Path = WEIGHT_ARTIFACT,
    countries: list[str] | None = None,
    *,
    year: int = TAX_YEAR,
) -> Path:
    """Regenerate and write the population-weight artifact."""
    output_path = Path(path)
    payload = generate_population_weight_payload(countries=countries, year=year)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_path
