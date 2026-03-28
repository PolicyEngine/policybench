"""Prompt templates for PolicyBench evaluations."""

from policybench.scenarios import (
    PERSON_BOOLEAN_INPUT_FIELDS,
    PERSON_NUMERIC_INPUT_FIELDS,
    Person,
    Scenario,
)

# Variable descriptions for natural language prompts
VARIABLE_DESCRIPTIONS = {
    "income_tax": "total federal income tax liability",
    "income_tax_before_refundable_credits": (
        "federal income tax before refundable credits"
    ),
    "eitc": "Earned Income Tax Credit amount",
    "ctc": "Child Tax Credit amount",
    "income_tax_refundable_credits": "total refundable tax credits",
    "snap": "annual SNAP (food stamps) benefit amount",
    "ssi": "annual Supplemental Security Income (SSI) amount",
    "free_school_meals": (
        "whether the household qualifies for free school meals "
        "(1 if eligible, 0 if not)"
    ),
    "is_medicaid_eligible": (
        "whether the household is eligible for Medicaid (1 if eligible, 0 if not)"
    ),
    "household_state_income_tax": "state income tax liability",
}

PERSON_INCOME_LABELS = {
    "self_employment_income": "self-employment income",
    "unemployment_compensation": "unemployment compensation",
    "taxable_interest_income": "taxable interest income",
    "qualified_dividend_income": "qualified dividend income",
    "short_term_capital_gains": "short-term capital gains",
    "long_term_capital_gains": "long-term capital gains",
    "taxable_ira_distributions": "taxable IRA distributions",
    "taxable_private_pension_income": "taxable private pension income",
    "social_security_retirement": "Social Security retirement income",
    "social_security_disability": "Social Security disability income",
    "disability_benefits": "disability benefits",
    "veterans_benefits": "veterans benefits",
}

PERSON_FLAG_LABELS = {
    "is_disabled": "is disabled",
    "is_blind": "is blind",
    "is_full_time_college_student": "is a full-time college student",
}


def _join_phrases(parts: list[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def describe_person(person: Person) -> str:
    """Create a natural language description of a person."""
    role = person.name.replace("adult", "Adult ").replace("child", "Child ")
    details = [f"{role} is {person.age} years old"]

    if person.name.startswith("adult"):
        details.append(
            f"has ${person.employment_income:,.0f} in annual employment income"
        )

    income_parts = []
    for field in PERSON_NUMERIC_INPUT_FIELDS:
        if field == "weekly_hours_worked":
            value = float(person.inputs.get(field, 0.0))
            if value > 0:
                details.append(f"works about {value:,.0f} hours per week")
            continue

        value = float(person.inputs.get(field, 0.0))
        if abs(value) > 1e-6:
            label = PERSON_INCOME_LABELS[field]
            income_parts.append(f"${value:,.0f} in {label}")

    if income_parts:
        details.append(f"receives {_join_phrases(income_parts)}")

    flag_parts = [
        PERSON_FLAG_LABELS[field]
        for field in PERSON_BOOLEAN_INPUT_FIELDS
        if person.inputs.get(field)
    ]
    if flag_parts:
        details.append(_join_phrases(flag_parts))

    return " and ".join(details) + "."


def describe_household(scenario: Scenario) -> str:
    """Create a natural language description of a household."""
    parts = []

    # Filing status
    status_map = {
        "single": "a single filer",
        "joint": "a married couple filing jointly",
        "head_of_household": "a head of household filer",
    }
    parts.append(f"Consider {status_map[scenario.filing_status]}")
    parts.append(f"living in {scenario.state}")
    parts.append(f"for tax year {scenario.year}.")

    # Adults
    for adult in scenario.adults:
        parts.append(describe_person(adult))

    # Children
    if scenario.children:
        for child in scenario.children:
            parts.append(describe_person(child))
    else:
        parts.append("They have no children.")

    return " ".join(parts)


def make_no_tools_prompt(
    scenario: Scenario,
    variable: str,
    answer_contract: str = "tool",
) -> str:
    """Create a prompt for the AI-alone condition."""
    description = describe_household(scenario)
    var_desc = VARIABLE_DESCRIPTIONS.get(variable, variable)

    if answer_contract == "json":
        answer_instructions = (
            'Return a JSON object exactly like {"answer": 1234.5}. '
            "Put only the numeric value in the answer field, with no dollar signs, "
            "commas, or other text in that field. "
            "Do not rely on plain text outside the JSON object for the final answer. "
        )
    else:
        answer_instructions = (
            "Use the `submit_answer` function exactly once to return "
            "the final numeric answer. "
            "Put only the numeric value in the `answer` field, with "
            "no dollar signs, commas, or other text in that field. "
            "Do not rely on plain text for the final answer. "
        )

    return (
        f"{description}\n\n"
        f"What is the {var_desc} for this household? "
        f"{answer_instructions}"
        f"If the answer is a dollar amount, give the annual amount. "
        f"If the answer is a rate, give a decimal (e.g. 0.25 for 25%)."
    )
