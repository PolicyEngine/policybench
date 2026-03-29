"""Household scenario generation for PolicyBench."""

from dataclasses import dataclass, field
from functools import lru_cache
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

ALLOWED_INPUT_ENTITIES = {"person", "tax_unit", "spm_unit", "household"}

EXCLUDED_INPUT_VARIABLES = {
    "age",
    "business_is_qualified",
    "business_is_sstb",
    "co_ccap_is_in_entry_process",
    "county_fips",
    "family_id",
    "filing_status",
    "has_itin",
    "household_count",
    "household_id",
    "household_weight",
    "id_receives_aged_or_disabled_credit",
    "is_computer_scientist",
    "is_executive_administrative_professional",
    "is_farmer_fisher",
    "is_female",
    "is_hispanic",
    "is_household_head",
    "is_related_to_head_or_spouse",
    "is_tafdc_related_to_head_or_spouse",
    "is_tax_unit_head",
    "is_tax_unit_spouse",
    "la_receives_blind_exemption",
    "person_count",
    "person_family_id",
    "person_household_id",
    "person_id",
    "person_marital_unit_id",
    "person_spm_unit_id",
    "person_tax_unit_id",
    "previous_year_income_available",
    "spm_unit_id",
    "spm_unit_capped_work_childcare_expenses",
    "spm_unit_spm_threshold",
    "state_code",
    "state_fips",
    "tax_unit_count",
    "tax_unit_id",
    "wy_power_shelter_qualified",
}

EXCLUDED_INPUT_PREFIXES = (
    "takes_up_",
    "would_",
)

EXCLUDED_INPUT_SUFFIXES = (
    "_count",
    "_fips",
    "_id",
    "_reported",
    "_would_be_qualified",
)

INPUT_NAME_ALIASES = {
    "employment_income_before_lsr": "employment_income",
    "self_employment_income_before_lsr": "self_employment_income",
    "weekly_hours_worked_before_lsr": "weekly_hours_worked",
    "long_term_capital_gains_before_response": "long_term_capital_gains",
}

DEFAULT_TAKEUP_INPUTS = {
    "person": {
        "takes_up_medicaid_if_eligible": True,
        "takes_up_ssi_if_eligible": True,
    },
    "tax_unit": {
        "takes_up_aca_if_eligible": True,
        "takes_up_dc_ptc": True,
        "takes_up_eitc": True,
        "would_file_if_eligible_for_refundable_credit": True,
        "would_file_taxes_voluntarily": True,
    },
    "spm_unit": {
        "takes_up_snap_if_eligible": True,
    },
    "household": {},
}

MONETARY_INCOME_FIELDS = {
    "alimony_income",
    "child_support_received",
    "disability_benefits",
    "employment_income",
    "estate_income",
    "farm_income",
    "farm_operations_income",
    "farm_rent_income",
    "miscellaneous_income",
    "non_qualified_dividend_income",
    "partnership_s_corp_income",
    "partnership_se_income",
    "qualified_dividend_income",
    "rental_income",
    "salt_refund_income",
    "self_employment_income",
    "short_term_capital_gains",
    "social_security_dependents",
    "social_security_disability",
    "social_security_retirement",
    "social_security_survivors",
    "ssi_reported",
    "tax_exempt_interest_income",
    "taxable_401k_distributions",
    "taxable_403b_distributions",
    "taxable_interest_income",
    "taxable_ira_distributions",
    "taxable_private_pension_income",
    "taxable_sep_distributions",
    "tip_income",
    "unemployment_compensation",
    "veterans_benefits",
    "workers_compensation",
    "long_term_capital_gains",
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
    "is_tax_unit_head": False,
    "is_tax_unit_spouse": False,
}


@dataclass(frozen=True)
class InputVariableSpec:
    """Promptable raw input metadata."""

    output_name: str
    source_name: str
    entity: str
    value_type: str


def _is_promptable_input_variable(name: str, variable) -> bool:
    if variable.entity.key not in ALLOWED_INPUT_ENTITIES:
        return False
    if name in EXCLUDED_INPUT_VARIABLES:
        return False
    if name.startswith(EXCLUDED_INPUT_PREFIXES):
        return False
    if name.endswith(EXCLUDED_INPUT_SUFFIXES):
        return False

    value_type = getattr(variable.value_type, "__name__", str(variable.value_type))
    return value_type in {"float", "bool"}


@lru_cache(maxsize=1)
def get_promptable_input_specs() -> tuple[InputVariableSpec, ...]:
    """Discover promptable raw inputs from the default PE-US variable registry."""
    sim = Microsimulation()
    specs: dict[str, InputVariableSpec] = {}

    for source_name, variable in sim.tax_benefit_system.variables.items():
        if not variable.is_input_variable():
            continue
        if not _is_promptable_input_variable(source_name, variable):
            continue

        output_name = INPUT_NAME_ALIASES.get(source_name, source_name)
        value_type = getattr(variable.value_type, "__name__", str(variable.value_type))
        specs[output_name] = InputVariableSpec(
            output_name=output_name,
            source_name=source_name,
            entity=variable.entity.key,
            value_type=value_type,
        )

    return tuple(
        sorted(
            specs.values(),
            key=lambda spec: (spec.entity, spec.output_name),
        )
    )


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
            float(value)
            for field, value in self.inputs.items()
            if field in MONETARY_INCOME_FIELDS
        )


@dataclass
class Scenario:
    """A household scenario for benchmarking."""

    id: str
    state: str
    filing_status: str
    adults: list[Person]
    children: list[Person] = field(default_factory=list)
    tax_unit_inputs: dict[str, Any] = field(default_factory=dict)
    spm_unit_inputs: dict[str, Any] = field(default_factory=dict)
    household_inputs: dict[str, Any] = field(default_factory=dict)
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
            for field, value in DEFAULT_TAKEUP_INPUTS["person"].items():
                person_data.setdefault(field, self._yearize(value))
            people[person.name] = person_data
            adult_names.append(person.name)

        for person in self.children:
            person_data = {
                "age": self._yearize(person.age),
                "employment_income": self._yearize(person.employment_income),
            }
            for field, value in person.inputs.items():
                person_data[field] = self._yearize(value)
            for field, value in DEFAULT_TAKEUP_INPUTS["person"].items():
                person_data.setdefault(field, self._yearize(value))
            people[person.name] = person_data
            child_names.append(person.name)

        all_names = adult_names + child_names

        tax_unit_data = {
            "members": all_names,
            "filing_status": self._yearize(PE_FILING_STATUSES[self.filing_status]),
        }
        for field, value in self.tax_unit_inputs.items():
            tax_unit_data[field] = self._yearize(value)
        for field, value in DEFAULT_TAKEUP_INPUTS["tax_unit"].items():
            tax_unit_data.setdefault(field, self._yearize(value))

        spm_unit_data = {"members": all_names}
        for field, value in self.spm_unit_inputs.items():
            spm_unit_data[field] = self._yearize(value)
        for field, value in DEFAULT_TAKEUP_INPUTS["spm_unit"].items():
            spm_unit_data.setdefault(field, self._yearize(value))

        household_data = {
            "members": all_names,
            "state_code": self._yearize(self.state),
        }
        for field, value in self.household_inputs.items():
            household_data[field] = self._yearize(value)
        for field, value in DEFAULT_TAKEUP_INPUTS["household"].items():
            household_data.setdefault(field, self._yearize(value))

        return {
            "people": people,
            "tax_units": {"tax_unit": tax_unit_data},
            "spm_units": {"spm_unit": spm_unit_data},
            "families": {"family": {"members": all_names}},
            "households": {"household": household_data},
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
        "tax_unit_inputs": scenario.tax_unit_inputs,
        "spm_unit_inputs": scenario.spm_unit_inputs,
        "household_inputs": scenario.household_inputs,
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
        tax_unit_inputs=dict(data.get("tax_unit_inputs", {})),
        spm_unit_inputs=dict(data.get("spm_unit_inputs", {})),
        household_inputs=dict(data.get("household_inputs", {})),
        year=int(data.get("year", TAX_YEAR)),
        source_dataset=str(data.get("source_dataset", "enhanced_cps")),
        metadata=dict(data.get("metadata", {})),
    )


def load_enhanced_cps_person_frame() -> tuple[pd.DataFrame, int]:
    """Load a person-level frame from the default Enhanced CPS microsimulation."""
    sim = Microsimulation()
    dataset_year = sim.default_input_period
    input_specs = get_promptable_input_specs()

    values = {}
    for output_name, variable_name in BASE_CPS_COLUMNS.items():
        values[output_name] = np.asarray(
            sim.calculate(
                variable_name,
                dataset_year,
                map_to="person",
                use_weights=False,
            )
        )

    for spec in input_specs:
        values[spec.output_name] = np.asarray(
            sim.calculate(
                spec.source_name,
                dataset_year,
                map_to="person",
                use_weights=False,
            )
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

    input_specs = get_promptable_input_specs()

    missing_defaults = {
        column: default
        for column, default in OPTIONAL_CPS_DEFAULTS.items()
        if column not in df.columns
    }
    missing_defaults.update(
        {
            spec.output_name: False if spec.value_type == "bool" else 0.0
            for spec in input_specs
            if spec.output_name not in df.columns
        }
    )
    if missing_defaults:
        defaults_df = pd.DataFrame(missing_defaults, index=df.index)
        df = pd.concat([df, defaults_df], axis=1).copy()

    numeric_columns = {
        "age",
        "household_weight",
        "employment_income",
        *(
            spec.output_name
            for spec in input_specs
            if spec.value_type == "float"
        ),
    }
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)

    boolean_columns = {
        "is_tax_unit_head",
        "is_tax_unit_spouse",
        *(
            spec.output_name
            for spec in input_specs
            if spec.value_type == "bool"
        ),
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
            tax_units=("tax_unit_id", "nunique"),
            spm_units=("spm_unit_id", "nunique"),
            families=("family_id", "nunique"),
            adults=("is_adult", "sum"),
            filing_status=("filing_status", "first"),
        )
        .reset_index()
    )

    summary = summary[
        (summary["tax_units"] == 1)
        & (summary["spm_units"] == 1)
        & (summary["families"] == 1)
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


def _extract_entity_inputs(
    row: pd.Series,
    entity: str,
) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    for spec in get_promptable_input_specs():
        if spec.entity != entity or spec.output_name == "employment_income":
            continue

        if spec.value_type == "bool":
            if bool(row[spec.output_name]):
                inputs[spec.output_name] = True
            continue

        value = float(row[spec.output_name])
        if abs(value) > 1e-6:
            inputs[spec.output_name] = value

    return inputs


def _build_person(row: pd.Series, label: str) -> Person:
    return Person(
        name=label,
        age=int(round(float(row["age"]))),
        employment_income=float(row["employment_income"]),
        inputs=_extract_entity_inputs(row, "person"),
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
                tax_unit_inputs=_extract_entity_inputs(household.iloc[0], "tax_unit"),
                spm_unit_inputs=_extract_entity_inputs(household.iloc[0], "spm_unit"),
                household_inputs=_extract_entity_inputs(household.iloc[0], "household"),
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
