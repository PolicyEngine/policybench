"""Opt-in US household prompt contract 2.1.0; no evaluator or v1 integration.

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

CONTRACT_VERSION = "2.1.0"

# Explicit exceptions to the generic unlisted-zero rule. These names are also
# used by the report-only sensitivity check; rendering an unknown is not coverage.
STATED_CONVENTION_INPUTS = frozenset(
    {
        "state_withheld_income_tax",
        "takes_up_medicare_if_eligible",
        "medicare_part_b_premium",
        "medical_expense_health_insurance_premiums",
        "health_insurance_premiums_without_medicare_part_b",
        "state_paid_leave_employee_share",
        "hours_worked_last_week",
        "weekly_hours_worked",
    }
)

TASK_PREFACE = (
    "Estimate requested outputs under the declared PolicyEngine-US version and "
    "the calculation conventions below. All listed people live together in the "
    "stated household group. Unless dated explicitly, facts apply throughout "
    "the tax-benefit year without changes in status or income volatility; wage "
    "amounts are annual totals including overtime, and hourly rates are "
    "straight-time rates. Unlisted numeric inputs, including unlisted integer "
    "inputs, are zero and unlisted boolean inputs are false, except for the "
    "explicitly listed unknown facts and the named calculation conventions. "
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
    "Assume filing and full take-up of eligible requested benefits (Medicare "
    "enrollment can be explicitly overridden), plus "
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
    "declared assumptions, not verified engine behavior. "
    "Every input read by a scored reference whose change by a plausible amount "
    "moves that reference by more than $1 must be covered by a stated fact or "
    "an explicit convention. A generic zero default does not cover a computed "
    "engine estimate. Legacy sweep findings report gaps; they do not certify "
    "readiness. Do not subtract employer-paid or employee after-tax premiums "
    "from FICA wages. Employee pre-tax health premiums reduce income-tax and "
    "FICA wages under the declared model."
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
    "pre_tax_health_insurance_premiums": "Employee pre-tax health insurance premiums",
    "health_insurance_premiums_without_medicare_part_b": (
        "Employee after-tax health insurance premiums excluding Part B"
    ),
    "health_insurance_premiums": (
        "Employee after-tax health insurance premiums including Part B"
    ),
    "other_health_insurance_premiums": (
        "Employee after-tax other health insurance premiums"
    ),
    "medicare_part_b_premium": "Employee after-tax annual Part B premium, net of MSP",
    "medical_expense_health_insurance_premiums": (
        "Employee after-tax medical-expense health insurance premium total"
    ),
    "financial_assistance": "Cash financial assistance from the named outside source",
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
    "takes_up_medicare_if_eligible": "Part B enrollment if Medicare-eligible",
    "is_surviving_spouse": "Surviving spouse indicator (see deciding facts below)",
    "dependent_child_lives_in_home": "Dependent child lives in the home",
    "state_paid_leave_employee_share_withheld": "Employer withholds employee share",
}
_PERSON_TEXT_LABELS = {
    "financial_assistance_source": "Source of cash financial assistance"
}
_TAX_UNIT_MONEY_LABELS = {
    "state_withheld_income_tax": (
        "Annual state income tax paid during the year for SALT"
    ),
}
_OPTIONAL_PAYROLL_PROGRAMS = {
    "MN": "MN Paid Leave",
    "CO": "CO FAMLI",
    "MA": "MA PFML",
    "NY": "NY PFL/DBL",
    "DE": "DE Paid Leave",
    "ME": "ME PFML",
    "VT": "VT child-care contribution",
    "WA": "WA PFML",
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
    | _PERSON_TEXT_LABELS.keys()
    | {"age", "hourly_wage", "spouse_death_year"}
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
    """Hash source bytes plus canonical v2 definitions, excluding mutable v1 text."""
    source = Path(__file__).read_bytes()
    definitions = json.dumps(v2_output_definitions(), sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(source + b"\n" + definitions).hexdigest()
    return f"policybench-us-household-prompt/{CONTRACT_VERSION}:sha256:{digest}"


def v2_output_definitions() -> dict[str, str]:
    """Read explicitly gated proposed wording without changing the v1 spec loader."""
    data = json.loads(Path(__file__).with_name("benchmark_specs.json").read_text())
    outputs = data["specs"]["policybench"]["countries"]["us"]
    return {
        item["id"]: item["v2_prompt"]
        for item in outputs
        if item.get("v2_prompt_contract") == CONTRACT_VERSION
    }


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
    if name in _PERSON_TEXT_LABELS:
        return _PERSON_TEXT_LABELS[name]
    if name in _TAX_UNIT_MONEY_LABELS:
        return _TAX_UNIT_MONEY_LABELS[name]
    if name == "spouse_death_year":
        return "Spouse death year"
    if name == "hourly_wage":
        return "Straight-time hourly wage"
    if name == "age":
        return "Age"
    if name in _TAKEUP_ENTITIES:
        return "Filing/take-up convention"
    return "Raw input"


def _value_text(name: str, value: object, path: str) -> str:
    if name in _PERSON_TEXT_LABELS:
        return _text(value, path)
    if name == "spouse_death_year":
        year = _number(value, path, integer=True)
        if not 1 <= year <= 9999:
            raise ContractInputError(f"{path}: expected a calendar year")
        return str(year)
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
    if (
        name in _PERSON_MONEY_LABELS
        or name in _TAX_UNIT_MONEY_LABELS
        or name == "hourly_wage"
    ):
        number = _number(value, path)
        if (
            "premiums" in name or name in ("medicare_part_b_premium", "hourly_wage")
        ) and number < 0:
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
        if name in _TAX_UNIT_MONEY_LABELS and entity != "tax_unit":
            raise ContractInputError(f"{path}: {name} is a tax_unit input")
        if name in _TAKEUP_ENTITIES and entity != _TAKEUP_ENTITIES[name]:
            raise ContractInputError(
                f"{path}: incorrect entity for filing/take-up input"
            )
        supplied = name in inputs
        value = inputs.get(name)
        supported = (
            name in _PERSON_FIELDS
            or name in _TAKEUP_ENTITIES
            or name in _TAX_UNIT_MONEY_LABELS
        )
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
        if "takes_up_medicare_if_eligible" not in inputs:
            lines.append(
                "- Part B enrollment [takes_up_medicare_if_eligible]: yes if eligible "
                "(declared convention; includes Part B, not evidence of enrollment)"
            )
        if "medicare_part_b_premium" not in inputs:
            lines.append(
                "- Employee after-tax annual Part B premium [medicare_part_b_premium]: "
                "declared-model standard premium plus IRMAA, net of Medicare Savings "
                "Program support; paid only while enrolled (declared convention). "
                "Unlisted two-year-prior IRMAA MAGI is $0."
            )
            if year == 2026 and policyengine_us_version == "2.15.17":
                lines.append(
                    "- 2026 Part B standard premium: $202.90/month, $2,434.80/year "
                    "before IRMAA and Medicare Savings Program support "
                    "(declared policyengine-us 2.15.17 convention)."
                )
        if "medical_expense_health_insurance_premiums" not in inputs:
            lines.append(
                "- Employee after-tax medical premium total "
                "[medical_expense_health_insurance_premiums]: "
                "nonzero health_insurance_premiums overrides the component sum; "
                "otherwise health_insurance_premiums_without_medicare_part_b "
                "(zero if absent) plus medicare_part_b_premium while enrolled. "
                "A supplied zero total in health_insurance_premiums still uses "
                "the component sum (declared convention; do not double-count)."
            )
        program = _OPTIONAL_PAYROLL_PROGRAMS.get(scenario.state)
        if program:
            choice = inputs.get("state_paid_leave_employee_share_withheld", True)
            if choice is None:
                description = "employer's withholding choice is unknown"
            elif choice:
                description = "employer withholds the full employee share"
            else:
                description = (
                    "employer pays the employee share; no employee withholding"
                )
            lines.append(
                f"- {program}: {description} "
                "(declared convention when not supplied; use the declared model's "
                "employee-share parameters; NY DBL uses 52 weeks/year)."
            )
        if inputs.get("is_surviving_spouse") is True:
            if "spouse_death_year" not in inputs:
                lines.append(
                    f"- Spouse death year [spouse_death_year]: {year - 1} "
                    "(declared convention; synthetic date, not an observed fact)."
                )
            elif (
                inputs["spouse_death_year"] is not None
                and inputs["spouse_death_year"] > year
            ):
                raise ContractInputError(
                    f"{prefix}.spouse_death_year: future death year"
                )
            if "dependent_child_lives_in_home" not in inputs:
                child_lives = "yes" if scenario.children else "no"
                lines.append(
                    "- Dependent child lives in the home "
                    f"[dependent_child_lives_in_home]: {child_lives} "
                    "(declared convention: listed children are dependent children "
                    "living in the home). Apply the dated filing-status rules; "
                    "the surviving spouse label alone does not establish "
                    "qualifying surviving spouse status."
                )
        if (
            "financial_assistance" in inputs
            and "financial_assistance_source" not in inputs
        ):
            lines.append(
                "- Source of financial assistance [financial_assistance_source]: "
                "cash gifts from friends or relatives outside the household "
                "(declared convention; count as SNAP unearned cash income)."
            )
    for entity in ("tax_unit", "spm_unit", "household"):
        inputs = _mapping(getattr(scenario, f"{entity}_inputs"), entity)
        if inputs:
            lines.extend(["", f"{entity} inputs:"])
            lines.extend(
                _render_inputs(inputs, entity, entity, {}, unknown, unsupported)
            )
        if entity == "tax_unit" and "state_withheld_income_tax" not in inputs:
            lines.extend(
                [
                    "",
                    "Tax-unit SALT payment convention:",
                    "- Annual state income tax paid during the year "
                    "[state_withheld_income_tax]: the declared model's per-state AGI "
                    "withholding estimate, treated as paid; not the final state income "
                    "tax liability (declared convention for each supplied tax unit). "
                    "A supplied tax-unit value overrides this estimate. SALT chooses "
                    "the larger of state_withheld_income_tax + local_income_tax and "
                    "state_sales_tax + local_sales_tax, then adds real estate tax "
                    "and applies the deduction cap. Montana's separate "
                    "mt_withheld_income_tax reader still requires its own stated input "
                    "or convention before scoring.",
                ]
            )
    lines.extend(["", "Proposed v2 output definitions (not an output request):"])
    for name, definition in sorted(v2_output_definitions().items()):
        lines.append(f"- [{name}]: {definition}")
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
