"""Household scenario generation for PolicyBench."""

from dataclasses import dataclass, field
import json
from typing import Any

import numpy as np
import pandas as pd
from policyengine_us import Microsimulation

from policybench.config import NUM_SCENARIOS, SEED, TAX_YEAR

SUPPORTED_FILING_STATUSES = {
    "SINGLE": "single",
    "JOINT": "joint",
    "HEAD_OF_HOUSEHOLD": "head_of_household",
}

PE_FILING_STATUSES = {
    "single": "SINGLE",
    "joint": "JOINT",
    "head_of_household": "HEAD_OF_HOUSEHOLD",
}

PERSON_NUMERIC_INPUT_FIELDS = (
    "self_employment_income",
    "weekly_hours_worked",
    "unemployment_compensation",
    "taxable_interest_income",
    "qualified_dividend_income",
    "short_term_capital_gains",
    "long_term_capital_gains",
    "taxable_ira_distributions",
    "taxable_private_pension_income",
    "social_security_retirement",
    "social_security_disability",
    "disability_benefits",
    "veterans_benefits",
)

PERSON_BOOLEAN_INPUT_FIELDS = (
    "is_disabled",
    "is_blind",
    "is_full_time_college_student",
)

PERSON_INPUT_VARIABLES = {
    "employment_income": "employment_income_before_lsr",
    "self_employment_income": "self_employment_income_before_lsr",
    "weekly_hours_worked": "weekly_hours_worked_before_lsr",
    "unemployment_compensation": "unemployment_compensation",
    "taxable_interest_income": "taxable_interest_income",
    "qualified_dividend_income": "qualified_dividend_income",
    "short_term_capital_gains": "short_term_capital_gains",
    "long_term_capital_gains": "long_term_capital_gains_before_response",
    "taxable_ira_distributions": "taxable_ira_distributions",
    "taxable_private_pension_income": "taxable_private_pension_income",
    "social_security_retirement": "social_security_retirement",
    "social_security_disability": "social_security_disability",
    "disability_benefits": "disability_benefits",
    "veterans_benefits": "veterans_benefits",
    "is_disabled": "is_disabled",
    "is_blind": "is_blind",
    "is_full_time_college_student": "is_full_time_college_student",
}

BASE_CPS_COLUMNS = {
    "person_id": "person_id",
    "household_id": "household_id",
    "tax_unit_id": "tax_unit_id",
    "spm_unit_id": "spm_unit_id",
    "family_id": "family_id",
    "household_weight": "household_weight",
    "state_code": "state_code",
    "filing_status": "filing_status",
    "age": "age",
    "is_tax_unit_head": "is_tax_unit_head",
    "is_tax_unit_spouse": "is_tax_unit_spouse",
}

REQUIRED_CPS_COLUMNS = {
    "person_id",
    "household_id",
    "tax_unit_id",
    "spm_unit_id",
    "family_id",
    "household_weight",
    "state_code",
    "filing_status",
    "age",
}

OPTIONAL_CPS_DEFAULTS = {
    "employment_income": 0.0,
    "self_employment_income": 0.0,
    "weekly_hours_worked": 0.0,
    "unemployment_compensation": 0.0,
    "taxable_interest_income": 0.0,
    "qualified_dividend_income": 0.0,
    "short_term_capital_gains": 0.0,
    "long_term_capital_gains": 0.0,
    "taxable_ira_distributions": 0.0,
    "taxable_private_pension_income": 0.0,
    "social_security_retirement": 0.0,
    "social_security_disability": 0.0,
    "disability_benefits": 0.0,
    "veterans_benefits": 0.0,
    "is_disabled": False,
    "is_blind": False,
    "is_full_time_college_student": False,
    "is_tax_unit_head": False,
    "is_tax_unit_spouse": False,
}


@dataclass
class Person:
    """A person in a benchmark household."""

    name: str
    age: int
    employment_income: float
    inputs: dict[str, Any] = field(default_factory=dict)

    @property
    def total_income(self) -> float:
        return self.employment_income + sum(
            float(self.inputs.get(field, 0.0)) for field in PERSON_NUMERIC_INPUT_FIELDS
        )


@dataclass
class Scenario:
    """A household scenario for benchmarking."""

    id: str
    state: str
    filing_status: str
    adults: list[Person]
    children: list[Person] = field(default_factory=list)
    year: int = TAX_YEAR
    source_dataset: str = "enhanced_cps"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def all_people(self) -> list[Person]:
        return self.adults + self.children

    @property
    def total_income(self) -> float:
        return sum(person.total_income for person in self.all_people)

    @property
    def num_children(self) -> int:
        return len(self.children)

    def _yearize(self, value: Any) -> dict[str, Any]:
        return {str(self.year): value}

    def to_pe_household(self) -> dict:
        """Convert to PolicyEngine-US household JSON format."""
        people = {}
        adult_names = []
        child_names = []

        for person in self.adults:
            person_data = {
                "age": self._yearize(person.age),
                "employment_income": self._yearize(person.employment_income),
            }
            for field, value in person.inputs.items():
                person_data[field] = self._yearize(value)
            people[person.name] = person_data
            adult_names.append(person.name)

        for person in self.children:
            person_data = {
                "age": self._yearize(person.age),
                "employment_income": self._yearize(person.employment_income),
            }
            for field, value in person.inputs.items():
                person_data[field] = self._yearize(value)
            people[person.name] = person_data
            child_names.append(person.name)

        all_names = adult_names + child_names

        return {
            "people": people,
            "tax_units": {
                "tax_unit": {
                    "members": all_names,
                    "filing_status": self._yearize(
                        PE_FILING_STATUSES[self.filing_status]
                    ),
                }
            },
            "spm_units": {"spm_unit": {"members": all_names}},
            "families": {"family": {"members": all_names}},
            "households": {
                "household": {
                    "members": all_names,
                    "state_code": self._yearize(self.state),
                }
            },
        }


def person_to_dict(person: Person) -> dict[str, Any]:
    """Serialize a Person to a JSON-safe dict."""
    return {
        "name": person.name,
        "age": int(person.age),
        "employment_income": float(person.employment_income),
        "inputs": person.inputs,
    }


def person_from_dict(data: dict[str, Any]) -> Person:
    """Reconstruct a Person from a serialized dict."""
    return Person(
        name=str(data["name"]),
        age=int(data["age"]),
        employment_income=float(data["employment_income"]),
        inputs=dict(data.get("inputs", {})),
    )


def scenario_to_dict(scenario: Scenario) -> dict[str, Any]:
    """Serialize a Scenario to a JSON-safe dict."""
    return {
        "id": scenario.id,
        "state": scenario.state,
        "filing_status": scenario.filing_status,
        "adults": [person_to_dict(person) for person in scenario.adults],
        "children": [person_to_dict(person) for person in scenario.children],
        "year": int(scenario.year),
        "source_dataset": scenario.source_dataset,
        "metadata": scenario.metadata,
    }


def scenario_from_dict(data: dict[str, Any]) -> Scenario:
    """Reconstruct a Scenario from a serialized dict."""
    return Scenario(
        id=str(data["id"]),
        state=str(data["state"]),
        filing_status=str(data["filing_status"]),
        adults=[person_from_dict(person) for person in data.get("adults", [])],
        children=[person_from_dict(person) for person in data.get("children", [])],
        year=int(data.get("year", TAX_YEAR)),
        source_dataset=str(data.get("source_dataset", "enhanced_cps")),
        metadata=dict(data.get("metadata", {})),
    )


def load_enhanced_cps_person_frame() -> tuple[pd.DataFrame, int]:
    """Load a person-level frame from the default Enhanced CPS microsimulation."""
    sim = Microsimulation()
    dataset_year = sim.default_input_period

    values = {}
    for output_name, variable_name in {
        **BASE_CPS_COLUMNS,
        **PERSON_INPUT_VARIABLES,
    }.items():
        values[output_name] = sim.calculate(
            variable_name,
            dataset_year,
            map_to="person",
            use_weights=False,
        )

    return pd.DataFrame(values), dataset_year


def scenario_manifest(scenarios: list[Scenario]) -> pd.DataFrame:
    """Build a compact scenario manifest for downstream exports."""
    rows = []
    for scenario in scenarios:
        rows.append(
            {
                "scenario_id": scenario.id,
                "state": scenario.state,
                "filing_status": scenario.filing_status,
                "num_adults": len(scenario.adults),
                "num_children": scenario.num_children,
                "total_income": scenario.total_income,
                "source_dataset": scenario.source_dataset,
                "scenario_json": json.dumps(
                    scenario_to_dict(scenario),
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            }
        )
    return pd.DataFrame(rows)


def _prepare_cps_frame(person_df: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_CPS_COLUMNS - set(person_df.columns)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"Missing required CPS columns: {missing_list}")

    df = person_df.copy()

    for column, default in OPTIONAL_CPS_DEFAULTS.items():
        if column not in df.columns:
            df[column] = default

    numeric_columns = {
        "age",
        "household_weight",
        "employment_income",
        *PERSON_NUMERIC_INPUT_FIELDS,
    }
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)

    boolean_columns = {
        "is_tax_unit_head",
        "is_tax_unit_spouse",
        *PERSON_BOOLEAN_INPUT_FIELDS,
    }
    for column in boolean_columns:
        df[column] = df[column].fillna(False).astype(bool)

    for column in ("person_id", "household_id", "tax_unit_id", "spm_unit_id", "family_id"):
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.dropna(
        subset=["person_id", "household_id", "tax_unit_id", "spm_unit_id", "family_id"]
    ).copy()
    for column in ("person_id", "household_id", "tax_unit_id", "spm_unit_id", "family_id"):
        df[column] = df[column].astype(int)

    df["state_code"] = df["state_code"].astype(str)
    df["filing_status"] = df["filing_status"].astype(str)
    df["is_adult"] = df["age"] >= 18
    return df


def _eligible_households(person_df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        person_df.groupby("household_id")
        .agg(
            household_weight=("household_weight", "first"),
            state_nunique=("state_code", "nunique"),
            filing_nunique=("filing_status", "nunique"),
            tax_units=("tax_unit_id", "nunique"),
            spm_units=("spm_unit_id", "nunique"),
            families=("family_id", "nunique"),
            household_size=("person_id", "size"),
            adults=("is_adult", "sum"),
            filing_status=("filing_status", "first"),
        )
        .reset_index()
    )

    summary = summary[
        (summary["state_nunique"] == 1)
        & (summary["filing_nunique"] == 1)
        & (summary["tax_units"] == 1)
        & (summary["spm_units"] == 1)
        & (summary["families"] == 1)
        & (summary["household_size"].between(1, 6))
        & (summary["filing_status"].isin(SUPPORTED_FILING_STATUSES))
    ]

    exact_adult_counts = (
        ((summary["filing_status"] == "JOINT") & (summary["adults"] == 2))
        | (
            summary["filing_status"].isin(["SINGLE", "HEAD_OF_HOUSEHOLD"])
            & (summary["adults"] == 1)
        )
    )
    summary = summary[exact_adult_counts]
    return summary


def _sample_household_ids(
    eligible_households: pd.DataFrame,
    n: int,
    seed: int,
) -> list[int]:
    if len(eligible_households) < n:
        raise ValueError(
            f"Requested {n} scenarios, but only {len(eligible_households)} eligible "
            "Enhanced CPS households were available."
        )

    rng = np.random.default_rng(seed)
    household_ids = eligible_households["household_id"].to_numpy()
    weights = eligible_households["household_weight"].to_numpy(dtype=float)
    weights = np.where(weights > 0, weights, 0.0)
    probabilities = None
    if weights.sum() > 0:
        probabilities = weights / weights.sum()

    sampled = rng.choice(
        household_ids,
        size=n,
        replace=False,
        p=probabilities,
    )
    return [int(household_id) for household_id in sampled]


def _extract_person_inputs(row: pd.Series) -> dict[str, Any]:
    inputs: dict[str, Any] = {}

    for field in PERSON_NUMERIC_INPUT_FIELDS:
        value = float(row[field])
        if abs(value) > 1e-6:
            inputs[field] = value

    for field in PERSON_BOOLEAN_INPUT_FIELDS:
        if bool(row[field]):
            inputs[field] = True

    return inputs


def _build_person(row: pd.Series, label: str) -> Person:
    return Person(
        name=label,
        age=int(round(float(row["age"]))),
        employment_income=float(row["employment_income"]),
        inputs=_extract_person_inputs(row),
    )


def scenarios_from_cps_frame(
    person_df: pd.DataFrame,
    n: int = NUM_SCENARIOS,
    seed: int = SEED,
    year: int = TAX_YEAR,
    dataset_year: int | None = None,
) -> list[Scenario]:
    """Sample benchmark scenarios from a person-level Enhanced CPS frame."""
    df = _prepare_cps_frame(person_df)
    eligible_households = _eligible_households(df)
    sampled_household_ids = _sample_household_ids(eligible_households, n=n, seed=seed)

    scenarios = []
    for i, household_id in enumerate(sampled_household_ids):
        household = df[df["household_id"] == household_id].copy()
        household = household.sort_values(
            by=["is_tax_unit_head", "is_tax_unit_spouse", "age", "person_id"],
            ascending=[False, False, False, True],
        )

        adults = []
        children = []
        adult_count = 0
        child_count = 0

        for _, row in household.iterrows():
            if row["is_adult"]:
                adult_count += 1
                adults.append(_build_person(row, f"adult{adult_count}"))
            else:
                child_count += 1
                children.append(_build_person(row, f"child{child_count}"))

        filing_status = SUPPORTED_FILING_STATUSES[household["filing_status"].iloc[0]]
        metadata = {
            "household_id": int(household_id),
            "tax_unit_id": int(household["tax_unit_id"].iloc[0]),
        }
        if dataset_year is not None:
            metadata["dataset_year"] = int(dataset_year)

        source_dataset = (
            f"enhanced_cps_{int(dataset_year)}"
            if dataset_year is not None
            else "enhanced_cps"
        )

        scenarios.append(
            Scenario(
                id=f"scenario_{i:03d}",
                state=household["state_code"].iloc[0],
                filing_status=filing_status,
                adults=adults,
                children=children,
                year=year,
                source_dataset=source_dataset,
                metadata=metadata,
            )
        )

    return scenarios


def generate_scenarios(n: int = NUM_SCENARIOS, seed: int = SEED) -> list[Scenario]:
    """Generate benchmark scenarios from sampled Enhanced CPS households."""
    person_df, dataset_year = load_enhanced_cps_person_frame()
    return scenarios_from_cps_frame(
        person_df,
        n=n,
        seed=seed,
        year=TAX_YEAR,
        dataset_year=dataset_year,
    )
