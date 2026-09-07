"""Opt-in US household prompt contract 2.0.0; no evaluator or v1 integration.

This module renders supplied facts, not policy results. It uses no model registry,
simulation, network, or v1 prompt helpers. Unknown inputs remain visible and block
any claim that the result is a complete evaluation contract. See
``docs/prompt_contract_v2.md`` for the deliberately limited supported surface.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from policybench.scenarios import Scenario

CONTRACT_VERSION = "2.0.0"

TASK_PREFACE = (
    "Estimate requested outputs under the declared PolicyEngine-US version and "
    "the calculation conventions below. All listed people live together in the "
    "stated household group. Unless dated explicitly, facts apply throughout "
    "the tax-benefit year without changes in status or income volatility; wage "
    "amounts are annual totals including overtime, and hourly rates are "
    "straight-time rates. Unlisted numeric inputs, including unlisted integer "
    "inputs, are zero and unlisted boolean inputs are false, except for the "
    "explicitly listed unknown facts and the filing and take-up assumptions. "
    "Unknown facts and unknown provenance are never observed negatives. A "
    "supplied value with unknown provenance remains a supplied value, not an "
    "observation; an unknown value must not be replaced with zero or false. "
    "A general disability indicator is a survey characteristic and does not "
    "establish SSI disability, tax-specific disability, SSDI entitlement, or "
    "Medicare eligibility. SSI disability uses the separately stated criteria "
    "before the substantial-gainful-activity test; apply the earnings test "
    "separately. SNAP receipt-based disability, tax-specific disability, and "
    "self-care conditions are separate facts. Medicare eligibility is evaluated "
    "on January 1; SSDI benefit months are measured as of that date. "
    "Assume filing and full take-up of eligible requested benefits, plus "
    "eligible TANF/MOE noncash benefits used for SNAP categorical eligibility, "
    "and apply those computed benefits in downstream calculations. This "
    "exception permits computed receipt; it does not create substantive "
    "eligibility or historical entitlement. Social Security, SSDI, and veterans "
    "payments and histories are supplied inputs only. Infer no other income, "
    "expenses, assets, receipt, rent, or coverage. The SSI output includes "
    "federal SSI only; state supplements require a separate requested output. "
    "If neither weekly-hours input is supplied, this contract assumes 0 "
    "hours/week, not an observed zero. Do not derive hours from annual wages or "
    "an hourly rate. Supplied null hours remain unknown. These conventions are "
    "declared assumptions, not verified engine behavior."
)

# Explicit labels and types, independent of the mutable engine input registry.
# The source names are always printed; no field is silently filtered or aliased.
_DISABILITY_LABELS = {
    "is_disabled": "General disability indicator (survey characteristic)",
    "is_blind": "Blindness indicator (not a program-specific disability finding)",
    "meets_ssi_disability_criteria": (
        "SSI disability criteria before the substantial-gainful-activity test"
    ),
    "is_usda_disabled": "SNAP receipt-based disability status",
    "is_permanently_and_totally_disabled": (
        "Permanent and total disability for IRC 152/22"
    ),
    "is_incapable_of_self_care": "Incapable of self-care for IRC 21",
}
_HOURS_LABELS = {
    "hours_worked_last_week": "Usual weekly hours worked",
    "weekly_hours_worked": "Weekly hours worked",
}
_PERSON_MONEY_LABELS = {
    "employment_income": "Gross wages and salaries",
    "employer_sponsored_insurance_premiums": (
        "Employer-paid insurance premiums (not included in stated wages)"
    ),
    "social_security_disability": "Social Security disability income",
    "social_security_retirement": "Social Security retirement income",
    "social_security_dependents": "Social Security dependent benefits",
    "social_security_survivors": "Social Security survivor benefits",
    "veterans_benefits": "Veterans benefits",
    "ssi_reported": "Reported SSI income (supplied receipt, not computed SSI)",
    "disability_benefits": "Disability benefits (unspecified program)",
    "self_employment_income": "Self-employment income",
    "bank_account_assets": "Bank account assets",
    "stock_assets": "Stock assets",
    "pre_subsidy_rent": "Pre-subsidy rent",
    "real_estate_taxes": "Real estate taxes",
    "home_mortgage_interest": "Home mortgage interest",
    "tip_income": "Tip income included in gross wages and salaries above",
}
_PERSON_BOOL_LABELS = {
    "is_tax_unit_head": "Tax unit head",
    "is_tax_unit_spouse": "Tax unit spouse",
    "is_unmarried_partner_of_household_head": "Unmarried partner of household head",
    "has_esi": "Has employer-sponsored insurance",
}
_DURATION = "months_receiving_social_security_disability"
_PROVENANCE_FIELDS = frozenset(_DISABILITY_LABELS) | {
    _DURATION,
    "social_security_disability",
}
_PERSON_FIELDS = (
    _PROVENANCE_FIELDS
    | _HOURS_LABELS.keys()
    | _PERSON_MONEY_LABELS.keys()
    | _PERSON_BOOL_LABELS.keys()
    | {"age", "hourly_wage"}
)
# The existing Scenario defaults are evidence for these explicit true-only
# inputs; accepting false here would contradict this contract's fixed preamble.
_TAKEUP_ENTITIES = {
    "takes_up_medicaid_if_eligible": "person",
    "takes_up_ssi_if_eligible": "person",
    "takes_up_aca_if_eligible": "tax_unit",
    "takes_up_dc_ptc": "tax_unit",
    "takes_up_eitc": "tax_unit",
    "would_file_if_eligible_for_refundable_credit": "tax_unit",
    "would_file_taxes_voluntarily": "tax_unit",
    "takes_up_snap_if_eligible": "spm_unit",
}
_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN "
    "MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA "
    "WV WI WY".split()
)
_FILING_STATUSES = {
    "single": "Single",
    "joint": "Joint",
    "head_of_household": "Head of household",
}


class ContractInputError(ValueError):
    """An input cannot be represented faithfully under this contract."""


def _text(value: object, path: str) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or value.splitlines() != [value]
    ):
        raise ContractInputError(f"{path}: expected non-empty single-line text")
    return value


def _mapping(value: object, path: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise ContractInputError(f"{path}: expected a mapping")
    for key in value:
        if type(key) is not str or re.fullmatch(r"[a-z][a-z0-9_]*", key) is None:
            raise ContractInputError(f"{path}: invalid input or person name {key!r}")
    return value


def _number(value: object, path: str, *, integer: bool = False) -> int | float:
    valid_types = (int,) if integer else (int, float)
    if type(value) not in valid_types or (
        type(value) is float and not math.isfinite(value)
    ):
        expected = "integer" if integer else "finite number"
        raise ContractInputError(f"{path}: expected {expected}, without coercion")
    return value


def _numeric_text(value: int | float) -> str:
    # repr preserves float precision, including sub-dollar and fractional hours.
    # Add grouping only to the whole part; never round or convert ints to floats.
    raw = str(value)
    if "e" in raw.lower():
        return raw
    whole, dot, fraction = raw.partition(".")
    grouped = "-0" if whole == "-0" else f"{int(whole):,}"
    return f"{grouped}{dot}{fraction}"


def _scalar_json(value: object, path: str) -> str:
    if value is not None and type(value) not in (bool, int, float, str):
        raise ContractInputError(f"{path}: unsupported non-scalar input")
    if type(value) is float and not math.isfinite(value):
        raise ContractInputError(f"{path}: unsupported non-finite input")
    return json.dumps(value, ensure_ascii=True, allow_nan=False)


@dataclass(frozen=True)
class FactProvenance:
    """Caller-supplied provenance, not independently verified by this renderer.

    Observed and imputed claims require a non-empty source. Unknown may also
    name a source documenting missingness. A source is a label, not fetched.
    """

    kind: str
    source: str | None = None

    def __post_init__(self) -> None:
        if type(self.kind) is not str or self.kind not in (
            "observed",
            "imputed",
            "unknown",
        ):
            raise ContractInputError(
                "provenance kind must be observed, imputed, or unknown"
            )
        if self.source is not None:
            _text(self.source, "provenance source")
        if self.kind != "unknown" and self.source is None:
            raise ContractInputError(f"{self.kind} provenance requires a source")


@dataclass(frozen=True)
class RenderedHouseholdContract:
    """Review artifact, with unresolved fact and unsupported-input paths.

    Even empty diagnostic tuples do not certify board readiness. This slice
    defines neither output/answer schemas nor engine-compatible unit mappings.
    """

    text: str
    contract_id: str
    unknown_facts: tuple[str, ...]
    unsupported_inputs: tuple[str, ...]


def contract_identity() -> str:
    """Version plus SHA-256 of this module's exact source bytes (source installs)."""
    digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return f"policybench-us-household-prompt/{CONTRACT_VERSION}:sha256:{digest}"


def _label(name: str) -> str:
    if name in _DISABILITY_LABELS:
        return _DISABILITY_LABELS[name]
    if name == _DURATION:
        return "SSDI benefit months as of January 1"
    if name in _HOURS_LABELS:
        return _HOURS_LABELS[name]
    if name in _PERSON_MONEY_LABELS:
        return _PERSON_MONEY_LABELS[name]
    if name in _PERSON_BOOL_LABELS:
        return _PERSON_BOOL_LABELS[name]
    if name == "hourly_wage":
        return "Straight-time hourly wage"
    if name == "age":
        return "Age"
    if name in _TAKEUP_ENTITIES:
        return "Filing/take-up convention"
    return "Raw input"


def _value_text(name: str, value: object, path: str) -> str:
    if name in _DISABILITY_LABELS or name in _PERSON_BOOL_LABELS:
        if type(value) is not bool:
            raise ContractInputError(f"{path}: expected boolean, without coercion")
        return "yes" if value else "no"
    if name in _TAKEUP_ENTITIES:
        if value is not True:
            raise ContractInputError(
                f"{path}: contradicts fixed filing/take-up convention"
            )
        return "yes"
    if name == _DURATION or name == "age":
        number = _number(value, path, integer=True)
        if number < 0:
            raise ContractInputError(f"{path}: must be nonnegative")
        unit = "months" if name == _DURATION else "years"
        return f"{_numeric_text(number)} {unit}"
    if name in _HOURS_LABELS:
        number = _number(value, path)
        if not 0 <= number <= 168:
            raise ContractInputError(f"{path}: hours must be between 0 and 168")
        return f"{_numeric_text(number)} hours/week"
    if name in _PERSON_MONEY_LABELS or name == "hourly_wage":
        number = _number(value, path)
        if (
            name in ("employer_sponsored_insurance_premiums", "hourly_wage")
            and number < 0
        ):
            raise ContractInputError(f"{path}: must be nonnegative")
        suffix = "/hour" if name == "hourly_wage" else ""
        return f"${_numeric_text(number)}{suffix}"
    return _scalar_json(value, path)


def _render_inputs(
    inputs: Mapping,
    entity: str,
    prefix: str,
    provenance: Mapping,
    unknown: set[str],
    unsupported: set[str],
) -> list[str]:
    names = set(inputs)
    if entity == "person":
        names.update(_PROVENANCE_FIELDS)
    lines = []
    for name in sorted(names):
        path = f"{prefix}.{name}"
        if name in _PERSON_FIELDS and entity != "person":
            raise ContractInputError(f"{path}: {name} is a person input")
        if name in _TAKEUP_ENTITIES and entity != _TAKEUP_ENTITIES[name]:
            raise ContractInputError(
                f"{path}: incorrect entity for filing/take-up input"
            )
        supplied = name in inputs
        value = inputs.get(name)
        supported = name in _PERSON_FIELDS or name in _TAKEUP_ENTITIES
        fact_provenance = provenance.get(name, FactProvenance("unknown"))
        if not supported:
            unsupported.add(path)
        if value is None:
            if name in _TAKEUP_ENTITIES:
                raise ContractInputError(
                    f"{path}: unknown filing/take-up contradicts convention"
                )
            if fact_provenance.kind != "unknown":
                raise ContractInputError(
                    f"{path}: {fact_provenance.kind} provenance without a value"
                )
            unknown.add(path)
            rendered = "unknown"
            notes = [
                "supplied null" if supplied else "not supplied",
                "provenance: unknown",
            ]
        else:
            rendered = _value_text(name, value, path)
            notes = []
            if name in _PROVENANCE_FIELDS:
                if fact_provenance.kind == "unknown":
                    unknown.add(path)
                    notes.extend(
                        [
                            "supplied value",
                            "provenance: unknown",
                            "not an observed fact",
                        ]
                    )
                else:
                    notes.append(f"provenance: {fact_provenance.kind}")
        if fact_provenance.source is not None:
            notes.append(f"source: {fact_provenance.source}")
        if not supported:
            notes.extend(["unsupported input", "meaning and units not interpreted"])
        suffix = f" ({'; '.join(notes)})" if notes else ""
        lines.append(f"- {_label(name)} [{name}]: {rendered}{suffix}")
    return lines


def render_household_contract(
    scenario: Scenario,
    *,
    policyengine_us_version: str,
    provenance: Mapping[str, Mapping[str, FactProvenance]] | None = None,
) -> RenderedHouseholdContract:
    """Render an existing US Scenario without modifying it or computing outcomes.

    Provenance keys are exact person names and supported disability/history
    input names. Missing provenance stays unknown; no source is inferred from
    ``source_dataset`` or ``metadata``. Unsupported scalar inputs are printed
    verbatim as JSON with an explicit marker. Invalid supported inputs raise.
    """
    if (
        type(policyengine_us_version) is not str
        or re.fullmatch(r"\d+\.\d+\.\d+", policyengine_us_version) is None
    ):
        raise ContractInputError(
            "policyengine_us_version: expected an exact x.y.z version"
        )
    if scenario.country != "us":
        raise ContractInputError("country: this contract supports US scenarios only")
    if type(scenario.state) is not str or scenario.state not in _STATES:
        raise ContractInputError("state: unsupported US state code")
    year = _number(scenario.year, "year", integer=True)
    if not 1 <= year <= 9999:
        raise ContractInputError("year: expected a calendar year from 1 to 9999")
    if (
        type(scenario.filing_status) is not str
        or scenario.filing_status not in _FILING_STATUSES
    ):
        raise ContractInputError("filing_status: unsupported or unknown filing status")
    _text(scenario.id, "scenario id")
    _text(scenario.source_dataset, "source dataset")
    if type(scenario.adults) is not list or not scenario.adults:
        raise ContractInputError("adults: expected a non-empty list")
    if type(scenario.children) is not list:
        raise ContractInputError("children: expected a list")
    people = scenario.adults + scenario.children
    person_names = []
    for person in people:
        name = _text(person.name, "person name")
        _mapping({name: None}, "person name")
        if name in person_names:
            raise ContractInputError(f"duplicate person name: {name}")
        person_names.append(name)
    provenance = {} if provenance is None else _mapping(provenance, "provenance")
    for person_name, facts in provenance.items():
        if person_name not in person_names:
            raise ContractInputError(f"provenance: unknown person {person_name}")
        for name, fact in _mapping(facts, f"provenance.{person_name}").items():
            if name not in _PROVENANCE_FIELDS or not isinstance(fact, FactProvenance):
                raise ContractInputError(
                    f"provenance.{person_name}.{name}: unsupported fact or provenance"
                )
    identity = contract_identity()
    lines = [
        f"Household prompt contract: {identity}",
        "Status: opt-in, unactivated household-fact slice; "
        "not a complete evaluation contract.",
        f"Declared calculation version: policyengine-us {policyengine_us_version} "
        "(caller-supplied; not verified).",
        "",
        TASK_PREFACE,
        "",
        "Household:",
        f"- scenario: {scenario.id}",
        f"- state: {scenario.state}",
        f"- tax year: {year}",
        f"- Medicare/SSDI duration reference date: {year:04d}-01-01",
        f"- supplied filing status: {_FILING_STATUSES[scenario.filing_status]}",
        f"- source dataset label (not fact provenance): {scenario.source_dataset}",
        "- marital-unit mapping: not defined by this slice; "
        "do not infer couples from person names",
        "- provenance annotations are caller-supplied, not independently verified",
    ]
    unknown: set[str] = set()
    unsupported: set[str] = set()
    for person in people:
        prefix = f"person.{person.name}"
        inputs = dict(_mapping(person.inputs, prefix))
        for duplicate in ("age", "employment_income"):
            if duplicate in inputs:
                raise ContractInputError(
                    f"{prefix}.{duplicate}: duplicates a dedicated Person field"
                )
        # Dedicated fields are required, unlike nullable optional inputs.
        _value_text("age", person.age, f"{prefix}.age")
        _value_text(
            "employment_income", person.employment_income, f"{prefix}.employment_income"
        )
        inputs.update(age=person.age, employment_income=person.employment_income)
        hours = [inputs[name] for name in _HOURS_LABELS if name in inputs]
        if len(hours) == 2 and hours[0] != hours[1]:
            raise ContractInputError(f"{prefix}: conflicting weekly-hours inputs")
        lines.extend(["", f"Person {person.name}:"])
        lines.extend(
            _render_inputs(
                inputs,
                "person",
                prefix,
                provenance.get(person.name, {}),
                unknown,
                unsupported,
            )
        )
        if not hours:
            lines.append(
                "- Weekly hours: 0 hours/week (contract assumption; "
                "no weekly-hours input supplied)"
            )
    for entity in ("tax_unit", "spm_unit", "household"):
        inputs = _mapping(getattr(scenario, f"{entity}_inputs"), entity)
        if inputs:
            lines.extend(["", f"{entity} inputs:"])
            lines.extend(
                _render_inputs(inputs, entity, entity, {}, unknown, unsupported)
            )
    lines.extend(
        [
            "",
            "Contract limitations:",
            "- Unsupported inputs remain visible and uninterpreted; "
            "resolve them before evaluation.",
            "- Resolve unknown values/provenance and unit mappings, then "
            "validate engine assumptions before scoring.",
            "- No output request, answer schema, reference certification, "
            "or board activation is supplied here.",
        ]
    )
    return RenderedHouseholdContract(
        text="\n".join(lines),
        contract_id=identity,
        unknown_facts=tuple(sorted(unknown)),
        unsupported_inputs=tuple(sorted(unsupported)),
    )
