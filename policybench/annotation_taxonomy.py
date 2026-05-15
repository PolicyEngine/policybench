"""Structured taxonomy for developer audit annotations."""

from __future__ import annotations

from dataclasses import dataclass

FAILURE_SOURCE_VALUES = (
    "llm_error",
    "prompt_ambiguity",
    "reference_model_issue_fixed",
    "reference_data_issue_fixed",
    "parse_contract_failure",
    "needs_review",
)

FAILURE_SUBTYPE_VALUES = (
    "missing_output",
    "taxable_income_or_deductions",
    "credit_phaseout",
    "thresholds_rates",
    "categorical_eligibility",
    "asset_resource",
    "health_coverage",
    "age_disability",
    "period_annualization",
    "payroll_tax_base",
    "state_local_rule",
    "household_unit_or_filing_status",
    "other",
)


@dataclass(frozen=True)
class FailureCategory:
    """One structured classification for a wrong prediction row."""

    failure_source: str
    failure_subtype: str


def validate_failure_source(value: object) -> str:
    """Return a normalized failure-source value or raise on invalid input."""
    normalized = str(value).strip()
    if normalized not in FAILURE_SOURCE_VALUES:
        allowed = ", ".join(FAILURE_SOURCE_VALUES)
        raise ValueError(f"Invalid failure_source '{normalized}'. Allowed: {allowed}")
    return normalized


def validate_failure_subtype(value: object) -> str:
    """Return a normalized failure-subtype value or raise on invalid input."""
    normalized = str(value).strip()
    if normalized not in FAILURE_SUBTYPE_VALUES:
        allowed = ", ".join(FAILURE_SUBTYPE_VALUES)
        raise ValueError(f"Invalid failure_subtype '{normalized}'. Allowed: {allowed}")
    return normalized


def infer_failure_category(annotation: object) -> FailureCategory:
    """Infer a structured category from the existing annotation prose.

    The inference is deterministic and intentionally conservative: parser or
    extraction failures get their own source, explicit upstream/prompt notes are
    separated, and otherwise the discrepancy is treated as a model error.
    """
    text = str(annotation or "").lower()

    is_missing_output = any(
        phrase in text
        for phrase in (
            "no parsed",
            "missing parsed",
            "missing output",
            "missing prediction",
            "prediction parser reported missing",
            "output extraction failure",
            "model omitted",
        )
    ) or ("missing" in text and "prediction" in text)

    if is_missing_output:
        source = "parse_contract_failure"
    elif any(phrase in text for phrase in ("prompt ambiguity", "ambiguous prompt")):
        source = "prompt_ambiguity"
    elif "reference data issue fixed" in text or "upstream data issue fixed" in text:
        source = "reference_data_issue_fixed"
    elif "reference model issue fixed" in text or "upstream model issue fixed" in text:
        source = "reference_model_issue_fixed"
    elif "needs review" in text:
        source = "needs_review"
    else:
        source = "llm_error"

    subtype = _infer_failure_subtype(text)
    return FailureCategory(source, subtype)


def _infer_failure_subtype(text: str) -> str:
    if any(
        phrase in text
        for phrase in (
            "no parsed",
            "missing parsed",
            "missing output",
            "missing prediction",
            "prediction parser reported missing",
            "output extraction failure",
            "model omitted",
        )
    ) or ("missing" in text and "prediction" in text):
        return "missing_output"
    if any(
        phrase in text
        for phrase in (
            "deduction",
            "deductible",
            "taxable",
            "itemiz",
            "allowance",
        )
    ):
        return "taxable_income_or_deductions"
    if any(
        phrase in text
        for phrase in (
            "credit",
            "eitc",
            "ctc",
            "refundable",
            "phaseout",
        )
    ):
        return "credit_phaseout"
    if any(
        phrase in text
        for phrase in (
            "threshold",
            "bracket",
            "rate",
            "fpl",
            "poverty",
            "taper",
        )
    ):
        return "thresholds_rates"
    if "eligible" in text or "eligibility" in text or "categorical" in text:
        return "categorical_eligibility"
    if any(phrase in text for phrase in ("asset", "resource", "savings", "capital")):
        return "asset_resource"
    if any(
        phrase in text
        for phrase in (
            "premium",
            "marketplace",
            "esi",
            "employer-sponsored",
            "coverage",
            "slcsp",
        )
    ):
        return "health_coverage"
    if any(
        phrase in text
        for phrase in (
            "age",
            "disabled",
            "disability",
            "medicare",
            "pip",
        )
    ):
        return "age_disability"
    if any(
        phrase in text
        for phrase in (
            "annual",
            "annualisation",
            "annualization",
            "weekly",
            "monthly",
        )
    ):
        return "period_annualization"
    if any(
        phrase in text
        for phrase in (
            "payroll",
            "fica",
            "national insurance",
            "social security",
            "self-employment tax",
        )
    ):
        return "payroll_tax_base"
    if any(
        phrase in text
        for phrase in (
            "state",
            "local",
            "county",
            "nyc",
            "texas",
            "california",
        )
    ):
        return "state_local_rule"
    if "filing status" in text or "dependent" in text or "head of household" in text:
        return "household_unit_or_filing_status"
    return "other"
