"""Household scenario generation for PolicyBench."""

import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from policybench.config import DEFAULT_COUNTRY, NUM_SCENARIOS, SEED, TAX_YEAR

SUPPORTED_FILING_STATUSES = {
    "SINGLE": "single",
    "JOINT": "joint",
    "HEAD_OF_HOUSEHOLD": "head_of_household",
}

ALLOWED_INPUT_ENTITIES = {"person", "tax_unit", "spm_unit", "household"}

US_STATE_CODES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "DC",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
}

GEOGRAPHIC_DEFINED_FOR_PREFIXES = ("in_",)

EXCLUDED_INPUT_VARIABLES = {
    "age",
    "business_is_qualified",
    "business_is_sstb",
    "co_ccap_is_in_entry_process",
    "county_fips",
    "family_id",
    "filing_status",
    "employer_quarterly_payroll_expense_override",
    "employer_state_unemployment_tax_rate_override",
    "has_itin",
    "has_marketplace_health_coverage",
    "has_marketplace_health_coverage_at_interview",
    "has_medicaid_health_coverage_at_interview",
    "has_never_worked",
    "has_non_marketplace_direct_purchase_health_coverage_at_interview",
    "has_tricare_health_coverage_at_interview",
    "has_va_health_coverage_at_interview",
    "household_count",
    "household_id",
    "household_weight",
    "id_receives_aged_or_disabled_credit",
    "four_year_college_student",
    "is_computer_scientist",
    "is_executive_administrative_professional",
    "is_farmer_fisher",
    "is_female",
    "is_eligible_for_american_opportunity_credit",
    "is_full_time_college_student",
    "is_part_time_college_student",
    "is_hispanic",
    "is_household_head",
    "is_tafdc_related_to_head_or_spouse",
    "is_union_member_or_covered",
    "is_wic_at_nutritional_risk",
    "is_tax_unit_head",
    "is_tax_unit_spouse",
    "la_receives_blind_exemption",
    "medicare_enrolled",
    "net_worth",
    "person_count",
    "person_family_id",
    "person_household_id",
    "person_id",
    "person_marital_unit_id",
    "person_spm_unit_id",
    "person_tax_unit_id",
    "previous_year_income_available",
    "qualified_tuition_expenses",
    "spm_unit_id",
    "spm_unit_capped_work_childcare_expenses",
    "spm_unit_spm_threshold",
    "state_code",
    "state_fips",
    "tax_unit_count",
    "tax_unit_id",
    "technical_institution_student",
    "tuition_and_fees",
    "va_ccsp_is_full_day",
    "weekly_hours_worked",
    "weekly_hours_worked_before_lsr",
    "wy_power_shelter_qualified",
}

# Prompt-visible inputs PolicyEngine reads under another name. The prompt shows
# hours_worked_last_week as "usual weekly hours worked"; the SNAP work rules read
# weekly_hours_worked_before_lsr, which the prompt never shows. policyengine-us
# defaulted that input to 40 until #9261 (2026-08-12) made it 0, so a stated 40
# hours stopped reaching the SNAP work tests. The stated value is copied to the
# engine name; a person with no stated hours keeps the engine default, which is
# also the prompt's rule for unlisted numbers (0).
PE_INPUT_ALIASES = {"hours_worked_last_week": "weekly_hours_worked_before_lsr"}

# Manifest inputs policyengine-us has renamed. The manifests keep the name the
# prompts were rendered from; the situation passes the value under the engine's
# name. policyengine-us 1.728.0 renamed partnership_se_income. Every reference
# build since then has applied the rename outside this builder: v1.1 in a
# patched manifest, later builds in the RENAME map of
# reference_audit/*/scripts/sweep.py.
PE_INPUT_RENAMES = {
    "partnership_se_income": "partnership_self_employment_net_earnings",
}

# Manifest inputs the situation leaves out, by entity. policyengine-us #9605
# deletes the tax-unit first_home_mortgage_interest and
# second_home_mortgage_interest inputs. Every household that lists them also
# lists the same interest as the person-level home_mortgage_interest (on the
# two that list a second home, the person value is the sum of both loans).
# From 1.782.1, home_mortgage_interest_tax_unit falls back to the person-level
# input when the tax-unit inputs are absent (from 1.804.1, #9276, it prefers
# it), so leaving them out moves no reference on those engines. 1.620.0 through
# 1.782.0 take the interest only from the tax-unit inputs (on 1.755.4 five
# outputs move without them), so references built on those engines reproduce
# from a commit before this change. The prompts still list the inputs. The
# per-loan balances and origination years stay, since the acquisition-debt cap
# reads them.
PE_DROPPED_INPUTS = {
    "tax_unit": frozenset(
        {"first_home_mortgage_interest", "second_home_mortgage_interest"}
    ),
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

PROMPTABLE_REPORTED_INPUTS = {
    "employee_pension_contributions_reported",
}

INPUT_NAME_ALIASES = {
    "employment_income_before_lsr": "employment_income",
    "self_employment_income_before_lsr": "self_employment_income",
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
    "unemployment_compensation",
    "veterans_benefits",
    "workers_compensation",
    "long_term_capital_gains",
}

BASE_PERSON_COLUMNS = {
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

UK_PERSON_ID_COLUMNS = {
    "person_id",
    "person_household_id",
    "person_benunit_id",
}

UK_HOUSEHOLD_ID_COLUMNS = {
    "household_id",
    "household_weight",
}

UK_EXCLUDED_PERSON_INPUTS = {
    *UK_PERSON_ID_COLUMNS,
    "person_id",
    "is_child_or_QYP",
}

UK_EXCLUDED_HOUSEHOLD_INPUTS = {
    *UK_HOUSEHOLD_ID_COLUMNS,
    "alcohol_and_tobacco_consumption",
    "clothing_and_footwear_consumption",
    "communication_consumption",
    "council_tax",
    "council_tax_band",
    "diesel_spending",
    "education_consumption",
    "food_and_non_alcoholic_beverages_consumption",
    "full_rate_vat_expenditure_rate",
    "health_consumption",
    "household_furnishings_consumption",
    "housing_water_and_electricity_consumption",
    "main_residence_value",
    "miscellaneous_consumption",
    "num_vehicles",
    "petrol_spending",
    "recreation_consumption",
    "region",
    "restaurants_and_hotels_consumption",
    "transport_consumption",
}

# Person facts PE-UK derives rather than stores. ``state_pension`` is derived
# from the stored reported amount; ``current_education`` is imputed from age
# when the data carries no enrolment (16-17 non-advanced, 18-19 higher
# education), and decides qualifying-young-person status for Child Benefit and
# Universal Credit, so the prompt has to state it. ``date_of_birth`` places
# each person within their year of age (a seeded draw in microdata), which
# decides State Pension age and the Pension Credit savings credit cutoff.
UK_COMPUTED_PERSON_INPUTS = (
    "state_pension",
    "current_education",
    "date_of_birth",
)

# Ages at which enrolment changes a qualifying-young-person or student rule.
# Below 16 every person is a child; from 20 no one is a qualifying young person.
UK_EDUCATION_PROMPT_AGES = range(16, 20)

# A fixed Broad Rental Market Area within each region, for private renters.
# PE-UK reads the Local Housing Allowance from the BRMA alone and defaults
# every household to Maidstone, whatever its region; the transfer data records
# none. The prompt states the area it uses.
UK_REGION_BRMA = {
    "NORTH_EAST": "TYNESIDE",
    "NORTH_WEST": "CENTRAL_GREATER_MANCHESTER",
    "YORKSHIRE": "LEEDS",
    "EAST_MIDLANDS": "NOTTINGHAM",
    "WEST_MIDLANDS": "BIRMINGHAM",
    "EAST_OF_ENGLAND": "CAMBRIDGE",
    "LONDON": "INNER_NORTH_LONDON",
    "SOUTH_EAST": "MAIDSTONE",
    "SOUTH_WEST": "BRISTOL",
    "WALES": "CARDIFF",
    "SCOTLAND": "GREATER_GLASGOW",
    "NORTHERN_IRELAND": "BELFAST",
}
UK_PRIVATE_RENT_TENURE = "RENT_PRIVATELY"

# The age a prompted person in non-advanced education began it, where the
# scenario gives none. PE-UK's default (1000) would fail every
# qualifying-young-person entry condition. The prompt states the age.
UK_EDUCATION_ENTRY_AGE = 16
UK_EDUCATION_ENTRY_FIELD = "age_started_or_accepted_current_education_or_training"

UK_NON_PROMPTABLE_SENTINELS = {
    "",
    "NONE",
}

UK_EMPLOYMENT_INCOME_COLUMNS = (
    "employment_income",
    "employment_income_before_lsr",
)

UK_TRANSFER_DATASET_FILENAME = "enhanced_cps_2025.h5"
# Commit 6b1f80e (policyengine-uk-data#419, 2026-05-24) rebuilt the artifact
# with PIP component categories. The earlier pin (9514dfb, 2026-04-26) stored
# reported PIP amounts, which policyengine-uk stopped reading when
# policyengine-uk#1656 moved that mapping into the data package.
UK_TRANSFER_DATASET_SHA256 = (
    "c663daea31b6fb8300f5c4758ccdcd7a227835ad7de90655294392fb95543eec"
)
UK_TRANSFER_DATASET_PINNED_COMMIT = "6b1f80e0fdcd7ec149f347b4e0b2ae0081f0ff1b"
UK_TRANSFER_DATASET_PINNED_URL = (
    "https://raw.githubusercontent.com/PolicyEngine/policyengine-uk-data/"
    f"{UK_TRANSFER_DATASET_PINNED_COMMIT}/policyengine_uk_data/storage/"
    f"{UK_TRANSFER_DATASET_FILENAME}"
)
UK_TRANSFER_DATASET_PUBLIC_REPO = "https://github.com/PolicyEngine/policyengine-uk-data"
UK_TRANSFER_DATASET_LOCAL_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "data" / UK_TRANSFER_DATASET_FILENAME,
    Path(__file__).resolve().parents[2]
    / "policyengine-uk-data"
    / "policyengine_uk_data"
    / "storage"
    / UK_TRANSFER_DATASET_FILENAME,
)
UK_DATASET_CANDIDATES = UK_TRANSFER_DATASET_LOCAL_CANDIDATES


@dataclass(frozen=True)
class InputVariableSpec:
    """Promptable raw input metadata."""

    output_name: str
    source_name: str
    entity: str
    value_type: str
    default_value: Any = None


def _is_promptable_input_variable(name: str, variable) -> bool:
    if variable.entity.key not in ALLOWED_INPUT_ENTITIES:
        return False
    if is_excluded_prompt_input_name(name):
        return False

    if getattr(variable, "formula", None) is not None:
        return False
    if getattr(variable, "formulas", None):
        return False
    defined_for = getattr(variable, "defined_for", None)
    if defined_for is not None and not _is_geographic_defined_for(defined_for):
        return False
    if getattr(variable, "adds", None):
        return False
    if getattr(variable, "subtracts", None):
        return False

    value_type = getattr(variable.value_type, "__name__", str(variable.value_type))
    return value_type in {"float", "bool"}


def is_prior_year_input_name(name: str) -> bool:
    return name.startswith("last_year_") or "_last_year" in name


def is_excluded_prompt_input_name(name: str) -> bool:
    excluded_by_suffix = name.endswith(EXCLUDED_INPUT_SUFFIXES) and (
        name not in PROMPTABLE_REPORTED_INPUTS
    )
    return (
        name in EXCLUDED_INPUT_VARIABLES
        or is_prior_year_input_name(name)
        or name.startswith(EXCLUDED_INPUT_PREFIXES)
        or excluded_by_suffix
    )


def _is_geographic_defined_for(defined_for: Any) -> bool:
    value = str(defined_for)
    return value in US_STATE_CODES or value.startswith(GEOGRAPHIC_DEFINED_FOR_PREFIXES)


@lru_cache(maxsize=1)
def get_promptable_input_specs() -> tuple[InputVariableSpec, ...]:
    """Discover promptable raw inputs from the default PE-US variable registry."""
    from policybench.policyengine_runtime import make_us_microsimulation

    sim = make_us_microsimulation()
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
            default_value=getattr(variable, "default_value", None),
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
    filing_status: str | None
    adults: list[Person]
    children: list[Person] = field(default_factory=list)
    tax_unit_inputs: dict[str, Any] = field(default_factory=dict)
    spm_unit_inputs: dict[str, Any] = field(default_factory=dict)
    household_inputs: dict[str, Any] = field(default_factory=dict)
    year: int = TAX_YEAR
    country: str = DEFAULT_COUNTRY
    source_dataset: str = "populace_us_2024"
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

    def _pe_inputs(self, entity: str, inputs: dict[str, Any]) -> dict[str, Any]:
        """An entity's manifest inputs, yearized, under the engine's names."""
        dropped = PE_DROPPED_INPUTS.get(entity, frozenset())
        data: dict[str, Any] = {}
        for key, value in inputs.items():
            if key in dropped:
                continue
            name = PE_INPUT_RENAMES.get(key, key)
            if name in data:
                raise ValueError(
                    f"Scenario {self.id} sets {name} twice on one {entity}: "
                    f"directly and through the input it renames."
                )
            data[name] = self._yearize(value)
        return data

    def to_pe_household(self) -> dict:
        """Convert to PolicyEngine-US household JSON format."""
        if self.country != "us":
            raise ValueError("to_pe_household is only supported for US scenarios.")
        people = {}
        adult_names = []
        child_names = []

        for person in self.adults:
            person_data = {
                "age": self._yearize(person.age),
                "employment_income": self._yearize(person.employment_income),
            }
            person_data.update(self._pe_inputs("person", person.inputs))
            for source, target in PE_INPUT_ALIASES.items():
                if source in person.inputs and target not in person.inputs:
                    person_data[target] = self._yearize(person.inputs[source])
            for key, value in DEFAULT_TAKEUP_INPUTS["person"].items():
                person_data.setdefault(key, self._yearize(value))
            people[person.name] = person_data
            adult_names.append(person.name)

        for person in self.children:
            person_data = {
                "age": self._yearize(person.age),
                "employment_income": self._yearize(person.employment_income),
            }
            person_data.update(self._pe_inputs("person", person.inputs))
            for source, target in PE_INPUT_ALIASES.items():
                if source in person.inputs and target not in person.inputs:
                    person_data[target] = self._yearize(person.inputs[source])
            for key, value in DEFAULT_TAKEUP_INPUTS["person"].items():
                person_data.setdefault(key, self._yearize(value))
            people[person.name] = person_data
            child_names.append(person.name)

        all_names = adult_names + child_names

        tax_unit_data = {
            "members": all_names,
        }
        tax_unit_data.update(self._pe_inputs("tax_unit", self.tax_unit_inputs))
        for key, value in DEFAULT_TAKEUP_INPUTS["tax_unit"].items():
            tax_unit_data.setdefault(key, self._yearize(value))

        spm_unit_data = {"members": all_names}
        spm_unit_data.update(self._pe_inputs("spm_unit", self.spm_unit_inputs))
        for key, value in DEFAULT_TAKEUP_INPUTS["spm_unit"].items():
            spm_unit_data.setdefault(key, self._yearize(value))

        household_data = {
            "members": all_names,
            "state_code": self._yearize(self.state),
        }
        household_data.update(self._pe_inputs("household", self.household_inputs))
        for key, value in DEFAULT_TAKEUP_INPUTS["household"].items():
            household_data.setdefault(key, self._yearize(value))

        return {
            "people": people,
            "marital_units": self.marital_units(),
            "tax_units": {"tax_unit": tax_unit_data},
            "spm_units": {"spm_unit": spm_unit_data},
            "families": {"family": {"members": all_names}},
            "households": {"household": household_data},
        }

    def to_pe_uk_situation(self, prefix: str = "") -> dict:
        """Convert to a PolicyEngine-UK situation holding only prompted facts.

        Each listed person, the region and the household inputs go in
        unchanged; nothing else from the source record does, so the reference
        is a function of the prompt. The benchmark keeps households with one
        benefit unit, so every person joins that unit. The prompt states the
        relationships, so they go in explicitly rather than through PE-UK's
        presumptions: the listed adults are the claimant and partner, every
        child is neither, and a couple is not married (the prompt states no
        marriage, and unlisted statuses are false). ``prefix`` namespaces
        entity keys when several scenarios share one simulation.

        Raises ``ValueError`` for inputs the prompt cannot show: tax-unit or
        benefit inputs, or person fields the renderer filters out.
        """
        if self.country != "uk":
            raise ValueError("to_pe_uk_situation is only supported for UK scenarios.")
        self = canonical_uk_scenario(self)
        hidden_household = sorted(
            k for k in self.household_inputs if is_excluded_prompt_input_name(k)
        )
        if hidden_household:
            raise ValueError(
                f"{self.id}: household inputs the prompt does not show: "
                f"{hidden_household}"
            )
        if self.tax_unit_inputs or self.spm_unit_inputs:
            raise ValueError(
                f"{self.id}: UK scenarios cannot carry tax-unit or benefit inputs."
            )
        people = {}
        for person in self.all_people:
            hidden = sorted(
                k for k in person.inputs if is_excluded_prompt_input_name(k)
            )
            if hidden:
                raise ValueError(
                    f"{self.id} {person.name}: inputs the prompt does not show: "
                    f"{hidden}"
                )
            person_data = {
                "age": self._yearize(person.age),
                # The stored wage leaf; employment_income adds the (zero)
                # labour-supply response to it, as in the microsimulation.
                "employment_income_before_lsr": self._yearize(person.employment_income),
                "is_claimant_or_partner": self._yearize(
                    person.name.startswith("adult")
                ),
            }
            for key, value in person.inputs.items():
                if key == "date_of_birth":
                    value = int(value)
                person_data[key] = self._yearize(value)
            people[f"{prefix}{person.name}"] = person_data
        members = list(people)
        household_data = {
            "members": members,
            "region": self._yearize(self.state),
        }
        for key, value in self.household_inputs.items():
            household_data[key] = self._yearize(value)
        return {
            "people": people,
            "benunits": {
                f"{prefix}benunit": {
                    "members": members,
                    "is_married": self._yearize(False),
                }
            },
            "households": {f"{prefix}household": household_data},
        }

    def marital_couple(self) -> tuple[str, str] | None:
        """The names of the tax unit's head and spouse, if the household has both.

        The couple comes from the relationship inputs each adult carries
        (``is_tax_unit_head`` / ``is_tax_unit_spouse``), never from person
        identifiers, so renaming people leaves the household unchanged. Two
        fallbacks cover manifests that predate those inputs: adults literally
        named ``head`` and ``spouse``, and otherwise a joint filing status with
        exactly two adults (a joint return is filed by a married couple).
        """
        heads = [a.name for a in self.adults if bool(a.inputs.get("is_tax_unit_head"))]
        spouses = [
            a.name for a in self.adults if bool(a.inputs.get("is_tax_unit_spouse"))
        ]
        if heads or spouses:
            if len(heads) == 1 and len(spouses) == 1 and heads[0] != spouses[0]:
                return heads[0], spouses[0]
            return None
        names = [a.name for a in self.adults]
        if "head" in names and "spouse" in names:
            return "head", "spouse"
        if len(self.adults) == 2 and str(self.filing_status or "").lower() == "joint":
            return names[0], names[1]
        return None

    def marital_units(self) -> dict:
        """Head and spouse form the only couple; everyone else is alone.

        Without an explicit marital-unit map policyengine-core places every
        household member in one marital unit, which the engine reads as one
        couple: SSI then deems the whole household's income to any eligible
        adult as if the others were a spouse. The frozen references are
        unaffected (verified against policyengine-us 1.755.4: no output moves),
        because no benchmark household has a non-spouse adult the engine finds
        SSI-eligible under the facts as listed.

        Unit identifiers are positional (``marital_unit_1``, ``marital_unit_2``,
        ...), never derived from person names, so no person identifier can
        collide with another unit's key and drop members from the map.
        """
        couple = self.marital_couple()
        groups: list[list[str]] = []
        if couple is not None:
            groups.append(list(couple))
        for person in self.all_people:
            if couple is not None and person.name in couple:
                continue
            groups.append([person.name])
        return {
            f"marital_unit_{index}": {"members": members}
            for index, members in enumerate(groups, start=1)
        }


# Fields the prompt shows as a fraction rather than a whole number. The
# renderer formats by the same suffixes.
RATE_OR_RATIO_FIELD_SUFFIXES = ("_rate", "_ratio")
UK_GAINFUL_SELF_EMPLOYMENT_FIELD = "uc_is_in_gainful_self_employment"


def _canonical_uk_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Each numeric input as the prompt shows it: amounts to the whole unit,
    rates to four significant figures. An explicit zero is a stated fact and
    is kept."""
    canonical: dict[str, Any] = {}
    for key, value in inputs.items():
        if isinstance(value, (bool, np.bool_, str)) or value is None:
            canonical[key] = value
        elif key.endswith(RATE_OR_RATIO_FIELD_SUFFIXES):
            canonical[key] = round_uk_prompt_rate(value)
        else:
            canonical[key] = round_uk_prompt_number(value)
    return canonical


def canonical_uk_person(person: Person) -> Person:
    """A UK person holding exactly the facts the prompt states about them.

    Besides whole-number amounts, three statuses PE-UK would otherwise fill in
    itself are made explicit, each following the prompt's rule that an
    unlisted status is false:

    - someone aged 16 to 19 with no education status is not in education
      (PE-UK imputes enrolment from age);
    - someone in non-advanced education with no entry age began it at
      ``UK_EDUCATION_ENTRY_AGE``;
    - someone with self-employment income and no gainful self-employment
      determination has none (PE-UK presumes one, applying the Universal
      Credit minimum income floor).
    """
    inputs = _canonical_uk_inputs(person.inputs)
    if int(person.age) in UK_EDUCATION_PROMPT_AGES:
        inputs.setdefault("current_education", "NOT_IN_EDUCATION")
    if inputs.get("current_education") == "POST_SECONDARY":
        inputs.setdefault(UK_EDUCATION_ENTRY_FIELD, float(UK_EDUCATION_ENTRY_AGE))
    if inputs.get("self_employment_income"):
        inputs.setdefault(UK_GAINFUL_SELF_EMPLOYMENT_FIELD, False)
    return Person(
        name=person.name,
        age=person.age,
        employment_income=round_uk_prompt_number(person.employment_income),
        inputs=inputs,
    )


def canonical_uk_scenario(scenario: "Scenario") -> "Scenario":
    """A UK scenario holding exactly the facts its prompt states.

    The prompt renderer and the reference builder both start from this, so a
    scenario loaded from a manifest gives the same facts to each as one built
    from the transfer data:

    - every amount is the whole number the prompt shows;
    - each person is canonical (:func:`canonical_uk_person`);
    - a private renter without a Broad Rental Market Area gets the fixed one
      for the region (``UK_REGION_BRMA``).

    Idempotent. Scenarios of other countries are returned unchanged.
    """
    if scenario.country != "uk":
        return scenario

    household_inputs = _canonical_uk_inputs(scenario.household_inputs)
    if (
        household_inputs.get("tenure_type") == UK_PRIVATE_RENT_TENURE
        and "brma" not in household_inputs
    ):
        if scenario.state not in UK_REGION_BRMA:
            raise ValueError(
                f"{scenario.id}: no Broad Rental Market Area is set for region "
                f"{scenario.state!r}."
            )
        household_inputs["brma"] = UK_REGION_BRMA[scenario.state]
    return Scenario(
        id=scenario.id,
        state=scenario.state,
        filing_status=scenario.filing_status,
        adults=[canonical_uk_person(adult) for adult in scenario.adults],
        children=[canonical_uk_person(child) for child in scenario.children],
        tax_unit_inputs=scenario.tax_unit_inputs,
        spm_unit_inputs=scenario.spm_unit_inputs,
        household_inputs=household_inputs,
        year=scenario.year,
        country=scenario.country,
        source_dataset=scenario.source_dataset,
        metadata=scenario.metadata,
    )


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
        "country": scenario.country,
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
        country=str(data.get("country", DEFAULT_COUNTRY)),
        state=str(data["state"]),
        filing_status=(
            None if data.get("filing_status") is None else str(data["filing_status"])
        ),
        adults=[person_from_dict(person) for person in data.get("adults", [])],
        children=[person_from_dict(person) for person in data.get("children", [])],
        tax_unit_inputs=dict(data.get("tax_unit_inputs", {})),
        spm_unit_inputs=dict(data.get("spm_unit_inputs", {})),
        household_inputs=dict(data.get("household_inputs", {})),
        year=int(data.get("year", TAX_YEAR)),
        source_dataset=str(data.get("source_dataset", "populace_us_2024")),
        metadata=dict(data.get("metadata", {})),
    )


def load_certified_us_person_frame() -> tuple[pd.DataFrame, int, str]:
    """Load a person-level frame from the certified US microsimulation dataset.

    Returns ``(person_df, dataset_year, dataset_label)``. The label is read
    from the live simulation's PolicyEngine bundle (``default_dataset``), so it
    reflects the dataset the run actually materialized -- the certified
    populace build (``populace_us_2024``) -- rather than a hardcoded name.
    """
    from policybench.policyengine_runtime import make_us_microsimulation

    sim = make_us_microsimulation()
    dataset_year = sim.default_input_period
    dataset_label = str(sim.policyengine_bundle["default_dataset"])
    input_specs = get_promptable_input_specs()

    values = {}
    for output_name, variable_name in BASE_PERSON_COLUMNS.items():
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

    return pd.DataFrame(values), dataset_year, dataset_label


def _hash_file(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _verify_uk_transfer_artifact(path: Path) -> Path:
    """Confirm the artifact's sha256 matches the pinned snapshot value."""
    actual = _hash_file(path)
    if actual != UK_TRANSFER_DATASET_SHA256:
        raise ValueError(
            f"UK transfer dataset at {path} has sha256 {actual}, expected "
            f"{UK_TRANSFER_DATASET_SHA256}. Update the artifact or the pinned "
            "expected hash."
        )
    return path


UK_TRANSFER_DOWNLOAD_TIMEOUT_SECONDS = 60


def _download_uk_transfer_artifact(destination: Path) -> Path:
    """Download the snapshot's UK transfer artifact from the pinned commit.

    Streams the download to a per-process temp file alongside the destination,
    sha256-verifies the temp file, and only atomically ``replace()``s the
    destination on success. The per-process temp suffix avoids collisions
    when two policybench processes share a cache directory. Raises
    ``RuntimeError`` on network errors or HTTP failures and ``ValueError``
    (via verification) on hash mismatch.
    """
    import tempfile

    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        UK_TRANSFER_DATASET_PINNED_URL,
        headers={"User-Agent": "policybench"},
    )
    fd, tmp_name = tempfile.mkstemp(
        prefix=destination.name + ".",
        suffix=".part",
        dir=str(destination.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            try:
                with urllib.request.urlopen(
                    request, timeout=UK_TRANSFER_DOWNLOAD_TIMEOUT_SECONDS
                ) as response:
                    if getattr(response, "status", 200) >= 400:
                        raise RuntimeError(
                            f"Download of {UK_TRANSFER_DATASET_PINNED_URL} "
                            f"returned HTTP {response.status}."
                        )
                    for chunk in iter(lambda: response.read(1024 * 1024), b""):
                        if not chunk:
                            break
                        handle.write(chunk)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise RuntimeError(
                    "Failed to download UK transfer dataset from "
                    f"{UK_TRANSFER_DATASET_PINNED_URL}: {exc}. Set "
                    "POLICYBENCH_UK_DATASET_PATH to a local copy or "
                    "POLICYBENCH_UK_DATASET_DOWNLOAD=0 to disable the "
                    "download step."
                ) from exc
        _verify_uk_transfer_artifact(tmp_path)
        tmp_path.replace(destination)
        return destination
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def get_uk_dataset_path() -> Path:
    """Locate the UK calibrated transfer dataset published in policyengine-uk-data.

    Resolution order: ``POLICYBENCH_UK_DATASET_PATH`` env var, then the
    sibling ``policyengine-uk-data`` checkout or a local ``data/`` copy, then
    a pinned-commit download from the public ``policyengine-uk-data`` GitHub
    repo. The returned path is sha256-verified against the snapshot value.
    Set ``POLICYBENCH_UK_DATASET_DOWNLOAD=0`` to disable the download step.
    Set ``POLICYBENCH_UK_DATASET_CACHE`` to override the download cache root
    (default ``~/.cache/policybench``).

    If ``POLICYBENCH_UK_DATASET_PATH`` is set to a path that does not exist or
    does not match the pinned sha256, this raises ``FileNotFoundError`` or
    ``ValueError`` rather than silently falling through to the download path.
    """
    configured = os.environ.get("POLICYBENCH_UK_DATASET_PATH")
    if configured:
        path = Path(configured).expanduser()
        if not path.exists():
            raise FileNotFoundError(
                f"POLICYBENCH_UK_DATASET_PATH={configured} does not exist. "
                "Unset the variable or point it at a local copy of "
                f"{UK_TRANSFER_DATASET_FILENAME} (sha256 "
                f"{UK_TRANSFER_DATASET_SHA256})."
            )
        return _verify_uk_transfer_artifact(path)

    for candidate in UK_DATASET_CANDIDATES:
        if candidate.exists():
            try:
                return _verify_uk_transfer_artifact(candidate)
            except ValueError:
                continue

    if os.environ.get("POLICYBENCH_UK_DATASET_DOWNLOAD", "1") != "0":
        cache_root = Path(
            os.environ.get(
                "POLICYBENCH_UK_DATASET_CACHE",
                Path.home() / ".cache" / "policybench",
            )
        ).expanduser()
        cached = cache_root / UK_TRANSFER_DATASET_FILENAME
        if cached.exists():
            try:
                return _verify_uk_transfer_artifact(cached)
            except ValueError:
                cached.unlink(missing_ok=True)
        return _download_uk_transfer_artifact(cached)

    searched = "\n".join(f"- {candidate}" for candidate in UK_DATASET_CANDIDATES)
    raise FileNotFoundError(
        "Could not find the UK calibrated transfer dataset. Either set "
        "POLICYBENCH_UK_DATASET_PATH to a local copy of "
        f"{UK_TRANSFER_DATASET_FILENAME} (sha256 "
        f"{UK_TRANSFER_DATASET_SHA256}), enable downloads, or place the "
        "artifact in one of:\n"
        f"{searched}\n"
        f"The artifact is published at {UK_TRANSFER_DATASET_PINNED_URL}."
    )


UK_REFERENCE_PERIOD_INPUT_ENTITIES = ("person", "household")


def _uk_dataset_inputs_by_entity(
    values: dict[str, Any], tax_benefit_system: Any
) -> dict[str, list[str]]:
    """Group the artifact's stored variables by PE-UK entity.

    Every stored variable must be one the installed policyengine-uk defines.
    A variable the engine no longer reads (as ``pip_dl_reported`` became
    after policyengine-uk#1656) would otherwise drop out of the reference
    silently while the stale value still reached the prompt.
    """
    unknown = sorted(key for key in values if key not in tax_benefit_system.variables)
    if unknown:
        raise ValueError(
            "The UK transfer artifact stores variables the installed "
            f"policyengine-uk does not define: {unknown}. Re-pin a transfer "
            "artifact built for this model version."
        )
    grouped: dict[str, list[str]] = {}
    for key in values:
        entity = tax_benefit_system.variables[key].entity.key
        grouped.setdefault(entity, []).append(key)
    return grouped


def load_uk_transfer_frames(
    period: int = TAX_YEAR,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Load person and household frames from the local UK transfer artifact.

    The artifact stores one survey year (2025). PE-UK uprates stored incomes,
    rents and savings when a later year is calculated, so each stored variable
    is read back from the simulation at the reference ``period``. The prompt
    then shows the same amounts the reference calculation uses, rather than
    the stored base-year amounts.
    """
    from policybench.policyengine_runtime import (
        get_uk_single_year_dataset_class,
        make_uk_transfer_microsimulation,
    )

    os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")
    dataset_path = get_uk_dataset_path()
    UKSingleYearDataset = get_uk_single_year_dataset_class()
    dataset = UKSingleYearDataset(file_path=str(dataset_path))
    values = dataset.load()

    sim = make_uk_transfer_microsimulation(dataset_path)
    period = str(period)
    inputs_by_entity = _uk_dataset_inputs_by_entity(values, sim.tax_benefit_system)

    unsupported = sorted(
        variable
        for entity, variables in inputs_by_entity.items()
        if entity not in UK_REFERENCE_PERIOD_INPUT_ENTITIES
        for variable in variables
        if not variable.endswith("_id")
    )
    if unsupported:
        raise ValueError(
            "The UK transfer artifact stores benefit-unit inputs the prompt "
            f"cannot show yet: {unsupported}."
        )

    frames: dict[str, dict[str, np.ndarray]] = {}
    for entity in UK_REFERENCE_PERIOD_INPUT_ENTITIES:
        frames[entity] = {
            variable: np.asarray(
                sim.calculate(variable, period, map_to=entity, unweighted=True)
            )
            for variable in inputs_by_entity.get(entity, [])
        }

    person_df = pd.DataFrame(frames["person"])
    household_df = pd.DataFrame(frames["household"])

    person_df["person_id"] = pd.to_numeric(
        person_df["person_id"], errors="coerce"
    ).astype(int)
    person_df["person_household_id"] = pd.to_numeric(
        person_df["person_household_id"], errors="coerce"
    ).astype(int)
    person_df["person_benunit_id"] = pd.to_numeric(
        person_df["person_benunit_id"], errors="coerce"
    ).astype(int)
    person_df["age"] = (
        pd.to_numeric(person_df["age"], errors="coerce").fillna(0).astype(int)
    )

    for variable in UK_COMPUTED_PERSON_INPUTS:
        if variable not in sim.tax_benefit_system.variables:
            raise ValueError(
                f"policyengine-uk no longer defines '{variable}', which the UK "
                "transfer path prompts. Update UK_COMPUTED_PERSON_INPUTS."
            )
        calculated = np.asarray(
            sim.calculate(
                variable,
                period,
                map_to="person",
                unweighted=True,
            )
        )
        if len(calculated) != len(person_df):
            raise ValueError(
                f"Calculated UK person variable '{variable}' returned "
                f"{len(calculated)} values for {len(person_df)} people."
            )
        person_df[variable] = calculated

    household_df["household_id"] = pd.to_numeric(
        household_df["household_id"], errors="coerce"
    ).astype(int)
    household_df["household_weight"] = pd.to_numeric(
        household_df["household_weight"], errors="coerce"
    ).fillna(0.0)

    return person_df, household_df, int(dataset.time_period)


# Backward-compatible alias for older local scripts.
load_uk_enhanced_cps_frames = load_uk_transfer_frames


def scenario_manifest(scenarios: list[Scenario]) -> pd.DataFrame:
    """Build a compact scenario manifest for downstream exports."""
    rows = []
    for scenario in scenarios:
        rows.append(
            {
                "scenario_id": scenario.id,
                "country": scenario.country,
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


def load_scenarios_from_manifest(path: str | Path) -> list[Scenario]:
    """Reconstruct scenarios from a serialized scenario manifest."""
    manifest = pd.read_csv(path)
    if "scenario_json" not in manifest.columns:
        raise ValueError(
            "Scenario manifest must include a scenario_json column. "
            "Regenerate it with `policybench reference-outputs`."
        )

    scenarios = []
    for _, row in manifest.iterrows():
        scenario_json = row["scenario_json"]
        if pd.isna(scenario_json):
            raise ValueError("Scenario manifest contains an empty scenario_json value.")
        scenario = scenario_from_dict(json.loads(str(scenario_json)))
        scenario_id = str(row.get("scenario_id", scenario.id))
        if scenario.id != scenario_id:
            raise ValueError(
                f"Scenario manifest row id mismatch: expected {scenario_id}, "
                f"found {scenario.id} in scenario_json."
            )
        scenarios.append(scenario)
    return scenarios


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
            spec.output_name: (
                spec.default_value
                if spec.default_value is not None
                else (False if spec.value_type == "bool" else 0.0)
            )
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
        *(spec.output_name for spec in input_specs if spec.value_type == "float"),
    }
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)

    boolean_columns = {
        "is_tax_unit_head",
        "is_tax_unit_spouse",
        *(spec.output_name for spec in input_specs if spec.value_type == "bool"),
    }
    for column in boolean_columns:
        df[column] = df[column].fillna(False).astype(bool)

    for column in (
        "person_id",
        "household_id",
        "tax_unit_id",
        "spm_unit_id",
        "family_id",
    ):
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.dropna(
        subset=["person_id", "household_id", "tax_unit_id", "spm_unit_id", "family_id"]
    ).copy()
    for column in (
        "person_id",
        "household_id",
        "tax_unit_id",
        "spm_unit_id",
        "family_id",
    ):
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
        & (summary["adults"] >= 1)
        & (summary["filing_status"].isin(SUPPORTED_FILING_STATUSES))
    ]
    return summary


def _sample_household_ids(
    eligible_households: pd.DataFrame,
    n: int,
    seed: int,
) -> list[int]:
    if len(eligible_households) < n:
        raise ValueError(
            f"Requested {n} scenarios, but only {len(eligible_households)} eligible "
            "source households were available."
        )

    rng = np.random.default_rng(seed)
    household_ids = eligible_households["household_id"].to_numpy()
    weights = eligible_households["household_weight"].to_numpy(dtype=float)
    weights = np.where(weights > 0, weights, 0.0)
    probabilities = None
    if weights.sum() > 0:
        positive = int((weights > 0).sum())
        if positive < n:
            raise ValueError(
                f"Requested {n} scenarios, but only {positive} source households "
                "have positive sampling weight (weighted sampling without "
                "replacement needs at least n positive-weight households)."
            )
        probabilities = weights / weights.sum()

    sampled = rng.choice(
        household_ids,
        size=n,
        replace=False,
        p=probabilities,
    )
    return [int(household_id) for household_id in sampled]


def load_excluded_household_ids(manifest_path: str | Path) -> set[int]:
    """Extract sampled household ids from a scenario manifest CSV."""
    manifest = pd.read_csv(manifest_path)
    if "household_id" in manifest.columns:
        return {
            int(household_id)
            for household_id in pd.to_numeric(
                manifest["household_id"], errors="coerce"
            ).dropna()
        }

    if "scenario_json" not in manifest.columns:
        raise ValueError(
            "Scenario manifest must include either a "
            "household_id or scenario_json column."
        )

    household_ids: set[int] = set()
    for scenario_json in manifest["scenario_json"].dropna():
        scenario = json.loads(str(scenario_json))
        household_id = scenario.get("metadata", {}).get("household_id")
        if household_id is not None:
            household_ids.add(int(household_id))
    return household_ids


def _extract_entity_inputs(
    row: pd.Series,
    entity: str,
) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    for spec in get_promptable_input_specs():
        if spec.entity != entity or spec.output_name == "employment_income":
            continue

        if pd.isna(row[spec.output_name]):
            continue

        if spec.value_type == "bool":
            value = bool(row[spec.output_name])
            default = (
                bool(spec.default_value) if spec.default_value is not None else False
            )
            if value != default:
                inputs[spec.output_name] = value
            continue

        value = float(row[spec.output_name])
        if (
            spec.default_value is not None
            and abs(value - float(spec.default_value)) <= 1e-6
        ):
            continue
        if abs(value) > 1e-6:
            inputs[spec.output_name] = value

    return inputs


def _build_person_with_tax_unit_role(row: pd.Series, label: str) -> Person:
    person = _build_person(row, label)
    person.inputs["is_tax_unit_head"] = bool(row["is_tax_unit_head"])
    person.inputs["is_tax_unit_spouse"] = bool(row["is_tax_unit_spouse"])
    return person


def _person_role_label(
    row: pd.Series,
    *,
    dependent_count: int,
    child_count: int,
) -> str:
    if bool(row["is_tax_unit_head"]):
        return "head"
    if bool(row["is_tax_unit_spouse"]):
        return "spouse"
    if bool(row["is_adult"]):
        return f"dependent{dependent_count}"
    return f"child{child_count}"


def _build_people_from_household(
    household: pd.DataFrame,
) -> tuple[list[Person], list[Person]]:
    adults: list[Person] = []
    children: list[Person] = []
    dependent_count = 0
    child_count = 0

    for _, row in household.iterrows():
        if bool(row["is_tax_unit_head"]) or bool(row["is_tax_unit_spouse"]):
            label = _person_role_label(
                row,
                dependent_count=dependent_count,
                child_count=child_count,
            )
        elif bool(row["is_adult"]):
            dependent_count += 1
            label = _person_role_label(
                row,
                dependent_count=dependent_count,
                child_count=child_count,
            )
        else:
            child_count += 1
            label = _person_role_label(
                row,
                dependent_count=dependent_count,
                child_count=child_count,
            )

        person = _build_person_with_tax_unit_role(row, label)
        if bool(row["is_adult"]):
            adults.append(person)
        else:
            children.append(person)

    return adults, children


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
    dataset_label: str | None = None,
    excluded_household_ids: set[int] | None = None,
) -> list[Scenario]:
    """Sample benchmark scenarios from a person-level US source frame.

    ``dataset_label`` is the certified dataset name reported by the runtime
    (e.g. ``populace_us_2024``); when provided it is recorded verbatim as each
    scenario's ``source_dataset``. When omitted, a neutral populace default is
    used so generated scenarios are never mislabeled.
    """
    df = _prepare_cps_frame(person_df)
    eligible_households = _eligible_households(df)
    if excluded_household_ids:
        eligible_households = eligible_households[
            ~eligible_households["household_id"].isin(excluded_household_ids)
        ].copy()
    sampled_household_ids = _sample_household_ids(eligible_households, n=n, seed=seed)

    scenarios = []
    for i, household_id in enumerate(sampled_household_ids):
        household = df[df["household_id"] == household_id].copy()
        household = household.sort_values(
            by=["is_tax_unit_head", "is_tax_unit_spouse", "age", "person_id"],
            ascending=[False, False, False, True],
        )

        adults, children = _build_people_from_household(household)

        filing_status = SUPPORTED_FILING_STATUSES[household["filing_status"].iloc[0]]
        metadata = {
            "household_id": int(household_id),
            "tax_unit_id": int(household["tax_unit_id"].iloc[0]),
        }
        if dataset_year is not None:
            metadata["dataset_year"] = int(dataset_year)

        source_dataset = dataset_label or "populace_us_2024"
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


def round_uk_prompt_number(value: float) -> float:
    """A UK numeric input as the prompt shows it: to the whole unit.

    The prompt formats every UK amount, hour count and date with no decimals
    (Python's round-half-even, as the formatter rounds), so storing the
    rounded value makes the reference use exactly the stated fact.
    """
    return float(round(float(value)))


def round_uk_prompt_rate(value: float) -> float:
    """A UK rate or ratio as the prompt shows it: to four significant figures.

    The prompt formats rates with ``.4g``, so the stored value is the one that
    format prints and the reference uses exactly the stated rate.
    """
    return float(f"{float(value):.4g}")


def _uk_promptable_value(value: Any) -> Any | None:
    if pd.isna(value):
        return None
    if isinstance(value, (np.bool_, bool)):
        return True if bool(value) else None
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned in UK_NON_PROMPTABLE_SENTINELS:
            return None
        return cleaned
    try:
        numeric = round_uk_prompt_number(value)
    except (TypeError, ValueError):
        return value
    if numeric == 0:
        return None
    return numeric


def _extract_uk_person_inputs(row: pd.Series) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    for col, value in row.items():
        if (
            col in UK_EXCLUDED_PERSON_INPUTS
            or col.endswith("_id")
            or is_excluded_prompt_input_name(col)
            or col
            in {
                "age",
                *UK_EMPLOYMENT_INCOME_COLUMNS,
                "marital_status",
            }
        ):
            continue
        if col == "current_education" and int(row["age"]) not in (
            UK_EDUCATION_PROMPT_AGES
        ):
            continue
        promptable = _uk_promptable_value(value)
        if promptable is not None:
            inputs[col] = promptable
    return inputs


def _extract_uk_household_inputs(row: pd.Series) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    for col, value in row.items():
        if col in UK_EXCLUDED_HOUSEHOLD_INPUTS or col.endswith("_id"):
            continue
        promptable = _uk_promptable_value(value)
        if promptable is not None:
            inputs[col] = promptable
    return inputs


def _build_uk_person(row: pd.Series, label: str) -> Person:
    employment_income = 0.0
    for column in UK_EMPLOYMENT_INCOME_COLUMNS:
        if column not in row:
            continue
        value = pd.to_numeric(row[column], errors="coerce")
        if not pd.isna(value):
            employment_income = round_uk_prompt_number(value)
            break
    return Person(
        name=label,
        age=int(row["age"]),
        employment_income=employment_income,
        inputs=_extract_uk_person_inputs(row),
    )


def _eligible_uk_households(
    person_df: pd.DataFrame,
    household_df: pd.DataFrame,
) -> pd.DataFrame:
    """Return UK households with promptable one-benefit-unit structure."""
    people = person_df.copy()
    people["person_household_id"] = pd.to_numeric(
        people["person_household_id"], errors="coerce"
    )
    people["person_benunit_id"] = pd.to_numeric(
        people["person_benunit_id"], errors="coerce"
    )
    people["age"] = pd.to_numeric(people["age"], errors="coerce")
    people = people.dropna(
        subset=["person_household_id", "person_benunit_id", "age"]
    ).copy()
    people["is_adult"] = people["age"] >= 18
    people["is_child_or_qyp"] = (
        people["is_child_or_QYP"].fillna(False).astype(bool)
        if "is_child_or_QYP" in people.columns
        else ~people["is_adult"]
    )
    people["is_prompt_adult"] = people["is_adult"] & ~people["is_child_or_qyp"]

    summary = (
        people.groupby("person_household_id")
        .agg(
            benefit_units=("person_benunit_id", "nunique"),
            adults=("is_prompt_adult", "sum"),
        )
        .reset_index()
        .rename(columns={"person_household_id": "household_id"})
    )
    eligible_ids = set(
        summary.loc[
            (summary["benefit_units"] == 1)
            & (summary["adults"] >= 1)
            & (summary["adults"] <= 2),
            "household_id",
        ].astype(int)
    )
    return household_df[household_df["household_id"].isin(eligible_ids)].copy()


def scenarios_from_uk_frames(
    person_df: pd.DataFrame,
    household_df: pd.DataFrame,
    n: int = NUM_SCENARIOS,
    seed: int = SEED,
    year: int = TAX_YEAR,
    dataset_year: int | None = None,
    excluded_household_ids: set[int] | None = None,
) -> list[Scenario]:
    """Sample benchmark scenarios from the local UK transfer dataset."""
    eligible_households = _eligible_uk_households(person_df, household_df)
    if excluded_household_ids:
        eligible_households = eligible_households[
            ~eligible_households["household_id"].isin(excluded_household_ids)
        ].copy()

    sampled_household_ids = _sample_household_ids(eligible_households, n=n, seed=seed)
    household_lookup = household_df.set_index("household_id")

    scenarios = []
    for index, household_id in enumerate(sampled_household_ids):
        household_row = household_lookup.loc[int(household_id)]
        household_people = person_df[
            person_df["person_household_id"] == int(household_id)
        ].copy()
        household_people = household_people.sort_values(
            by=["age", "person_id"],
            ascending=[False, True],
        )

        adults = []
        children = []
        adult_count = 0
        child_count = 0
        qyp_count = 0
        for _, row in household_people.iterrows():
            is_child_or_qyp = bool(row.get("is_child_or_QYP", False))
            if int(row["age"]) >= 18 and not is_child_or_qyp:
                adult_count += 1
                adults.append(_build_uk_person(row, f"adult{adult_count}"))
            elif int(row["age"]) >= 16 and is_child_or_qyp:
                qyp_count += 1
                children.append(_build_uk_person(row, f"qyp{qyp_count}"))
            else:
                child_count += 1
                children.append(_build_uk_person(row, f"child{child_count}"))

        metadata = {"household_id": int(household_id)}
        benunit_ids = sorted(
            {
                int(benunit_id)
                for benunit_id in household_people["person_benunit_id"]
                .dropna()
                .astype(int)
            }
        )
        if benunit_ids:
            metadata["benunit_ids"] = benunit_ids
        if dataset_year is not None:
            metadata["dataset_year"] = int(dataset_year)

        scenarios.append(
            Scenario(
                id=f"scenario_{index:03d}",
                country="uk",
                state=str(household_row["region"]),
                filing_status=None,
                adults=adults,
                children=children,
                household_inputs=_extract_uk_household_inputs(household_row),
                year=year,
                source_dataset=(
                    f"uk_calibrated_transfer_{int(dataset_year)}"
                    if dataset_year is not None
                    else "uk_calibrated_transfer"
                ),
                metadata=metadata,
            )
        )

    return [canonical_uk_scenario(scenario) for scenario in scenarios]


def generate_scenarios(
    n: int = NUM_SCENARIOS,
    seed: int = SEED,
    excluded_household_ids: set[int] | None = None,
    country: str = DEFAULT_COUNTRY,
) -> list[Scenario]:
    """Generate benchmark scenarios for a country."""
    if country == "us":
        person_df, dataset_year, dataset_label = load_certified_us_person_frame()
        return scenarios_from_cps_frame(
            person_df,
            n=n,
            seed=seed,
            year=TAX_YEAR,
            dataset_year=dataset_year,
            dataset_label=dataset_label,
            excluded_household_ids=excluded_household_ids,
        )
    if country == "uk":
        person_df, household_df, dataset_year = load_uk_transfer_frames()
        return scenarios_from_uk_frames(
            person_df,
            household_df,
            n=n,
            seed=seed,
            year=TAX_YEAR,
            dataset_year=dataset_year,
            excluded_household_ids=excluded_household_ids,
        )
    raise ValueError(f"Unsupported country '{country}'")


def split_scenarios(
    scenarios: list[Scenario],
    private_fraction: float,
    seed: int,
) -> tuple[list[Scenario], list[Scenario]]:
    """Deterministically partition scenarios into (public, private) splits.

    The private split is a uniformly sampled subset whose membership depends
    only on ``seed`` and the scenario ids, so re-running reference-output
    generation with the same inputs reproduces the same partition. Both
    splits preserve the input ordering.
    """
    if not 0.0 <= private_fraction < 1.0:
        raise ValueError(f"private_fraction must be in [0, 1), got {private_fraction}")
    if private_fraction == 0.0:
        return list(scenarios), []

    private_count = round(len(scenarios) * private_fraction)
    if private_count == 0:
        return list(scenarios), []

    # Rank by a seeded hash of each scenario id rather than random.sample so
    # membership is a pure function of (id, seed), independent of list order.
    def membership_rank(scenario: Scenario) -> str:
        digest = hashlib.sha256(f"{seed}:{scenario.id}".encode("utf-8"))
        return digest.hexdigest()

    ranked = sorted(scenarios, key=membership_rank)
    private_ids = {scenario.id for scenario in ranked[:private_count]}
    public = [s for s in scenarios if s.id not in private_ids]
    private = [s for s in scenarios if s.id in private_ids]
    return public, private
