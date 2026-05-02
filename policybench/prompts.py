"""Prompt templates for PolicyBench evaluations."""

from policybench.scenarios import (
    Person,
    Scenario,
    is_excluded_prompt_input_name,
)
from policybench.spec import find_output_spec, parse_person_output

TASK_PREFACE = (
    "Estimate the requested tax and benefit outputs using only the household "
    "facts below. All listed people live together and are in one household "
    "group for tax and benefit calculations. All listed facts describe the "
    "full tax-benefit year. Treat demographic, work, student, disability, housing, "
    "health coverage, and household-composition facts as constant throughout "
    "the tax-benefit year, with no within-year income volatility or status changes. "
    "Wage and salary amounts are annual totals, including any overtime pay; "
    "hourly wage is a straight-time rate when listed. "
    "Treat any unlisted numeric input as 0 and any other unlisted household "
    "fact, boolean, or status input as false. Assume tax filing and program "
    "take-up when required. Do not infer unlisted income, expenses, assets, "
    "benefit receipt, rent, or health coverage.\n\n"
)

EXPLANATION_CONSISTENCY_INSTRUCTION = (
    "Each explanation must support the numeric value submitted for the same "
    "variable in `answers`. If an explanation mentions a final amount, that "
    "amount must match the corresponding `answers` value. Do not write that "
    "you will use one value while submitting a different value. "
)

# Variable descriptions for natural language prompts
US_VARIABLE_DESCRIPTIONS = {
    "snap": "annual SNAP (food stamps) benefit amount",
    "ssi": "annual Supplemental Security Income (SSI) amount",
}

UK_VARIABLE_DESCRIPTIONS = {
    "income_tax": (
        "household total annual UK Income Tax liability, excluding Capital Gains Tax"
    ),
    "national_insurance": (
        "household total annual UK National Insurance contributions, excluding "
        "employer National Insurance"
    ),
    "capital_gains_tax": (
        "household total annual UK Capital Gains Tax, computed separately from "
        "Income Tax"
    ),
    "child_benefit": (
        "household total annual gross Child Benefit amount before the High Income "
        "Child Benefit Charge, including qualifying young people; do not apply "
        "an income test or tax-charge reduction to this output; do not subtract "
        "HICBC here because it is included in Income Tax, so report gross Child "
        "Benefit even when HICBC would recover it through tax"
    ),
    "universal_credit": "household total annual Universal Credit amount",
    "pension_credit": "household total annual Pension Credit amount",
    "housing_benefit": "annual Housing Benefit amount",
    "pip": "household total annual Personal Independence Payment (PIP) amount",
    "carers_allowance": "annual Carer's Allowance amount",
    "attendance_allowance": "annual Attendance Allowance amount",
    "council_tax": "annual Council Tax liability",
}

INPUT_LABEL_OVERRIDES = {
    "agi": "AGI",
    "alimony_expense": "alimony expense",
    "alimony_income": "alimony income",
    "amt_foreign_tax_credit": "AMT foreign tax credit",
    "auto_loan_balance": "auto loan balance",
    "auto_loan_interest": "auto loan interest",
    "bank_account_assets": "bank account assets",
    "bond_assets": "bond assets",
    "casualty_loss": "casualty loss",
    "charitable_cash_donations": "charitable cash donations",
    "charitable_non_cash_donations": "charitable non-cash donations",
    "child_support_expense": "child support expense",
    "child_support_received": "child support received",
    "deductible_mortgage_interest": "deductible mortgage interest",
    "disability_benefits": "disability benefits",
    "domestic_production_ald": "domestic production deduction",
    "early_withdrawal_penalty": "early withdrawal penalty",
    "educator_expense": "educator expense",
    "employment_income": "wages and salaries, including tips and commissions",
    "employee_pension_contributions_reported": "employee pension contributions",
    "estate_income": "estate income",
    "excess_withheld_payroll_tax": "excess withheld payroll tax",
    "farm_income": "farm income",
    "farm_operations_income": "farm operations income",
    "farm_rent_income": "farm rent income",
    "general_business_credit": "general business credit",
    "has_esi": "has employer-sponsored insurance",
    "has_marketplace_health_coverage": "has Marketplace health coverage",
    "health_insurance_premiums_without_medicare_part_b": (
        "health insurance premiums excluding Medicare Part B"
    ),
    "health_savings_account_ald": "health savings account deduction",
    "home_mortgage_interest": "home mortgage interest",
    "hours_worked_last_week": "usual weekly hours worked",
    "is_blind": "is blind",
    "is_disabled": "is disabled",
    "is_full_time_college_student": "is a full-time college student",
    "is_military": "is in the military",
    "is_separated": "is separated",
    "is_surviving_spouse": "is a surviving spouse",
    "long_term_capital_gains": "long-term capital gains",
    "medicare_enrolled": "is enrolled in Medicare",
    "medicare_part_b_premiums": "Medicare Part B premiums",
    "miscellaneous_income": "miscellaneous income",
    "net_worth": "net worth",
    "non_qualified_dividend_income": "non-qualified dividend income",
    "other_credits": "other credits",
    "other_medical_expenses": "other medical expenses",
    "over_the_counter_health_expenses": "over-the-counter health expenses",
    "partnership_s_corp_income": "partnership or S-corp income",
    "partnership_se_income": "self-employment partnership income",
    "pre_subsidy_rent": "pre-subsidy rent",
    "prior_year_minimum_tax_credit": "prior-year minimum tax credit",
    "qualified_dividend_income": "qualified dividend income",
    "qualified_tuition_expenses": "qualified tuition expenses",
    "real_estate_taxes": "real estate taxes",
    "rental_income": "rental income",
    "roth_401k_contributions": "Roth 401(k) contributions",
    "roth_ira_contributions": "Roth IRA contributions",
    "salt_refund_income": "state and local tax refund income",
    "self_employed_pension_contributions": "self-employed pension contributions",
    "self_employment_income": "self-employment income",
    "short_term_capital_gains": "short-term capital gains",
    "social_security_dependents": "Social Security dependent benefits",
    "social_security_disability": "Social Security disability income",
    "social_security_retirement": "Social Security retirement income",
    "social_security_survivors": "Social Security survivor benefits",
    "spm_unit_pre_subsidy_childcare_expenses": "pre-subsidy childcare expenses",
    "ssi_reported": "reported SSI income",
    "stock_assets": "stock assets",
    "student_loan_interest": "student loan interest",
    "tax_exempt_interest_income": "tax-exempt interest income",
    "taxable_401k_distributions": "taxable 401(k) distributions",
    "taxable_403b_distributions": "taxable 403(b) distributions",
    "unemployment_compensation": "unemployment compensation",
    "taxable_interest_income": "taxable interest income",
    "taxable_ira_distributions": "taxable IRA distributions",
    "taxable_private_pension_income": "taxable private pension income",
    "taxable_sep_distributions": "taxable SEP distributions",
    "tip_income": "tip income included in wages and salaries",
    "traditional_401k_contributions": "traditional 401(k) contributions",
    "traditional_ira_contributions": "traditional IRA contributions",
    "unadjusted_basis_qualified_property": ("unadjusted basis of qualified property"),
    "unrecaptured_section_1250_gain": "unrecaptured section 1250 gain",
    "unreimbursed_business_employee_expenses": (
        "unreimbursed employee business expenses"
    ),
    "veterans_benefits": "veterans benefits",
    "weekly_hours_worked": "hours worked per week",
    "workers_compensation": "workers' compensation",
    "capital_gains_before_response": "capital gains",
    "communication_consumption": "communication spending",
    "council_tax": "Council Tax",
    "council_tax_band": "Council Tax band",
    "corporate_wealth": "corporate financial wealth",
    "dividend_income": "dividend income",
    "education_consumption": "education spending",
    "food_and_non_alcoholic_beverages_consumption": (
        "food and non-alcoholic beverages spending"
    ),
    "full_rate_vat_expenditure_rate": "full-rate VAT expenditure share",
    "gender": "gender",
    "gift_aid": "Gift Aid donations",
    "health_consumption": "health spending",
    "household_furnishings_consumption": "household furnishings spending",
    "household_wealth": "household wealth",
    "housing_water_and_electricity_consumption": (
        "housing, water, and electricity spending"
    ),
    "is_disabled_for_benefits": "is disabled for benefits",
    "is_student": "is a student",
    "marital_status": "marital status",
    "miscellaneous_consumption": "miscellaneous spending",
    "mortgage_capital_repayment": "mortgage capital repayment",
    "mortgage_interest_repayment": "mortgage interest repayment",
    "national_insurance": "National Insurance",
    "num_vehicles": "number of vehicles",
    "other_residential_property_value": "other residential property value",
    "petrol_spending": "petrol spending",
    "pip": "Personal Independence Payment",
    "pip_dl_category": "PIP daily living component award",
    "pip_dl_reported": "reported PIP daily living amount",
    "pip_m_category": "PIP mobility component award",
    "pip_m_reported": "reported PIP mobility amount",
    "private_pension_contributions": "private pension contributions",
    "private_pension_income": "private pension income",
    "property_income": "property income",
    "recreation_consumption": "recreation spending",
    "region": "region",
    "rent": "rent",
    "restaurants_and_hotels_consumption": "restaurants and hotels spending",
    "savings": "savings",
    "savings_interest_income": "savings interest income",
    "state_pension": "State Pension income",
    "state_pension_reported": "reported State Pension income",
    "tenure_type": "tenure",
    "transport_consumption": "transport spending",
    "selected_marketplace_plan_benchmark_ratio": ("selected Marketplace plan premium"),
    "weeks_unemployed": "weeks unemployed",
}


NON_MONETARY_NUMERIC_FIELDS = {
    "weekly_hours_worked",
    "hours_worked_last_week",
    "hours_worked",
    "num_vehicles",
    "weeks_unemployed",
}

RATE_OR_RATIO_FIELD_SUFFIXES = (
    "_rate",
    "_ratio",
)


def _currency_symbol(country: str) -> str:
    return "£" if country == "uk" else "$"


def _person_label_from_name(person_name: str, country: str = "us") -> str:
    if country == "us":
        if person_name in {"head", "adult1"}:
            return "Head"
        if person_name in {"spouse", "adult2"}:
            return "Spouse"
        if person_name.startswith("dependent"):
            return person_name.replace("dependent", "Dependent ")
    if person_name.startswith("adult"):
        return person_name.replace("adult", "Adult ")
    if person_name.startswith("qyp"):
        return person_name.replace("qyp", "Qualifying young person ")
    if person_name.startswith("child"):
        return person_name.replace("child", "Child ")
    return person_name.replace("_", " ").title()


def get_variable_description(variable: str, country: str = "us") -> str:
    """Return the prompt description for a benchmark output."""
    parsed_person_output = parse_person_output(variable)
    if parsed_person_output is not None:
        person_name, _, template = parsed_person_output
        return str(template["prompt"]).format(
            person_label=_person_label_from_name(person_name, country=country)
        )
    output = find_output_spec(variable, country=country)
    if output is not None:
        return output.prompt
    if country == "uk":
        return UK_VARIABLE_DESCRIPTIONS.get(variable, variable)
    return US_VARIABLE_DESCRIPTIONS.get(variable, variable)


def _variable_request_line(variable: str) -> str:
    description = get_variable_description(variable)
    return f"- {variable}: {description}"


def _humanize_input_label(field: str) -> str:
    if field in INPUT_LABEL_OVERRIDES:
        return INPUT_LABEL_OVERRIDES[field]
    return field.replace("_", " ")


def _format_marketplace_plan_ratio(value: float) -> str:
    percentage = value * 100
    if abs(percentage - 100) <= 0.5:
        return (
            "- selected Marketplace plan: a benchmark Silver plan, or a plan "
            "with about the same pre-subsidy premium"
        )
    if percentage < 100:
        return (
            "- selected Marketplace plan: a lower-premium plan costing about "
            f"{percentage:,.0f}% as much as the local benchmark Silver plan "
            "before subsidies"
        )
    return (
        "- selected Marketplace plan: a higher-premium plan costing about "
        f"{percentage:,.0f}% as much as the local benchmark Silver plan "
        "before subsidies"
    )


def _format_input_line(field: str, value, country: str = "us") -> str:
    label = _humanize_input_label(field)
    if isinstance(value, bool):
        if value:
            return f"- {label}"
        return f"- {label}: no"
    if isinstance(value, str):
        return f"- {label}: {value.replace('_', ' ').title()}"
    if field == "selected_marketplace_plan_benchmark_ratio":
        return _format_marketplace_plan_ratio(float(value))
    if field in NON_MONETARY_NUMERIC_FIELDS:
        return f"- {label}: {float(value):,.0f}"
    if field.endswith(RATE_OR_RATIO_FIELD_SUFFIXES):
        return f"- {label}: {float(value):,.4g}"
    return f"- {label}: {_currency_symbol(country)}{float(value):,.0f}"


def _person_heading(person: Person, country: str = "us") -> str:
    return _person_label_from_name(person.name, country=country)


def describe_person(person: Person, country: str = "us") -> str:
    """Create a structured description of a person."""
    lines = [
        f"{_person_heading(person, country=country)}:",
        f"- age: {person.age}",
    ]

    if person.name.startswith("adult") or abs(person.employment_income) > 1e-6:
        employment_label = _humanize_input_label("employment_income")
        lines.append(
            f"- {employment_label}: "
            f"{_currency_symbol(country)}"
            f"{person.employment_income:,.0f}"
        )

    for field, value in sorted(person.inputs.items()):
        if is_excluded_prompt_input_name(field):
            continue
        lines.append(_format_input_line(field, value, country=country))

    return "\n".join(lines)


def _describe_entity_inputs(
    title: str, inputs: dict[str, object], country: str = "us"
) -> str:
    if not inputs:
        return ""
    lines = [f"{title}:"]
    for field, value in sorted(inputs.items()):
        if is_excluded_prompt_input_name(field):
            continue
        lines.append(_format_input_line(field, value, country=country))
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def describe_household(scenario: Scenario) -> str:
    """Create a structured description of a household."""
    period_label = (
        f"UK fiscal year: {scenario.year}-{str(scenario.year + 1)[-2:]}"
        if scenario.country == "uk"
        else f"tax year: {scenario.year}"
    )
    lines = [
        "Household:",
        f"- {'region' if scenario.country == 'uk' else 'state'}: {scenario.state}",
        f"- {period_label}",
        "",
    ]

    if scenario.country == "uk":
        benunit_ids = scenario.metadata.get("benunit_ids") or []
        benunit_count = len(benunit_ids) if benunit_ids else 1
        lines.insert(-1, f"- benefit units in household: {benunit_count}")
        if benunit_count == 1:
            lines.extend(
                [
                    "Household structure:",
                    "- all listed people live together in one UK benefit unit",
                    "- if two adults are listed, Adult 1 and Adult 2 are a couple",
                    (
                        "- children and qualifying young people are dependents, "
                        "not partners"
                    ),
                    "- requested outputs are household totals",
                    "",
                ]
            )
    for adult in scenario.adults:
        lines.extend([describe_person(adult, country=scenario.country), ""])

    if scenario.children:
        for child in scenario.children:
            lines.extend([describe_person(child, country=scenario.country), ""])

    household_title = (
        "Household assets and housing"
        if scenario.country == "uk"
        else "Household inputs"
    )
    for title, inputs in (
        ("Tax unit", scenario.tax_unit_inputs),
        ("Benefit inputs", scenario.spm_unit_inputs),
        (household_title, scenario.household_inputs),
    ):
        block = _describe_entity_inputs(title, inputs, country=scenario.country)
        if block:
            lines.extend([block, ""])

    return "\n".join(line for line in lines).strip()


def make_no_tools_prompt(
    scenario: Scenario,
    variable: str,
    answer_contract: str = "tool",
) -> str:
    """Create a prompt for the AI-alone condition."""
    description = describe_household(scenario)
    var_desc = get_variable_description(variable, country=scenario.country)

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
        f"{TASK_PREFACE}"
        f"{description}\n\n"
        f"What is the {var_desc} for this household? "
        f"{answer_instructions}"
        f"If the answer is a currency amount, give the annual amount. "
        f"If the answer is a rate, give a decimal (e.g. 0.25 for 25%)."
    )


def make_no_tools_batch_prompt(
    scenario: Scenario,
    variables: list[str],
    answer_contract: str = "tool",
    include_explanations: bool = True,
) -> str:
    """Create a prompt that requests all benchmark outputs in one response."""
    description = describe_household(scenario)
    requested_variables = "\n".join(
        f"- {variable}: {get_variable_description(variable, country=scenario.country)}"
        for variable in variables
    )

    if answer_contract == "json":
        requested_keys = ", ".join(f'"{variable}": 1234.5' for variable in variables)
        if include_explanations:
            example = (
                f'{{"answers": {{{requested_keys}}}, '
                f'"explanations": {{"{variables[0]}": "short note"}}}}'
            )
            answer_instructions = (
                "Return a single JSON object with an "
                "`answers` object and a required "
                "`explanations` object. "
                "Use the exact variable names as keys "
                "inside `answers`, for example "
                f"{example}. "
                "Include every requested key exactly once "
                "in `answers`, even if the value is 0. "
                "Include every requested key exactly "
                "once in `explanations`. "
                "Each explanation must be non-empty, "
                "specific to that variable, and concise. "
                f"{EXPLANATION_CONSISTENCY_INSTRUCTION}"
                "Put only numeric values in `answers`, "
                "with no dollar signs, commas, or "
                "explanatory text in the values. "
                "Do not rely on plain text outside "
                "the JSON object for the final answers. "
            )
        else:
            answer_instructions = (
                "Return a single JSON object containing "
                "every requested quantity. "
                "Use the exact variable names as keys, "
                f"for example {{{requested_keys}}}. "
                "Include every requested key exactly "
                "once, even if the value is 0. "
                "Put only numeric values in the JSON "
                "object, with no dollar signs, "
                "commas, or explanatory text in "
                "the values. "
                "Do not rely on plain text outside "
                "the JSON object for the final "
                "answers. "
            )
    else:
        if include_explanations:
            answer_instructions = (
                "Use the `submit_answers` function "
                "exactly once. "
                "Return an `answers` object with every "
                "requested quantity and a required "
                "`explanations` object with concise notes "
                "keyed by the same variable names. "
                "Include every requested key exactly "
                "once in `explanations`, and do not "
                "leave any explanation blank. "
                f"{EXPLANATION_CONSISTENCY_INSTRUCTION}"
                "Use the exact variable names as keys "
                "inside `answers` and put only numeric "
                "values there. "
                "Include every requested key exactly "
                "once in `answers`, even if the "
                "value is 0. "
                "Do not rely on plain text for the final answers. "
            )
        else:
            answer_instructions = (
                "Use the `submit_answers` function exactly once to return every "
                "requested quantity. "
                "Use the exact variable names as keys and put only numeric values "
                "in the arguments. "
                "Include every requested key exactly once, even if the value is 0. "
                "Do not rely on plain text for the final answers. "
            )

    return (
        f"{TASK_PREFACE}"
        f"{description}\n\n"
        "Provide the following policy quantities for this household:\n"
        f"{requested_variables}\n\n"
        f"{answer_instructions}"
        "If an answer is a currency amount, give the annual amount. "
        "If an answer is a rate, give a decimal (e.g. 0.25 for 25%)."
    )


def make_no_tools_batch_repair_prompt(
    scenario: Scenario,
    variables: list[str],
    answer_contract: str = "tool",
    include_explanations: bool = True,
) -> str:
    """Create a repair prompt for only the missing benchmark outputs."""
    description = describe_household(scenario)
    requested_variables = "\n".join(
        f"- {variable}: {get_variable_description(variable, country=scenario.country)}"
        for variable in variables
    )

    if answer_contract == "json":
        requested_keys = ", ".join(f'"{variable}": 1234.5' for variable in variables)
        if include_explanations:
            example = (
                f'{{"answers": {{{requested_keys}}}, '
                f'"explanations": {{"{variables[0]}": "short note"}}}}'
            )
            answer_instructions = (
                "A prior response omitted required "
                "answers and/or explanations. "
                "Return a single JSON object "
                "with an `answers` object containing "
                "the listed quantities below "
                "and a required `explanations` object "
                "keyed by those same variables. "
                "Use the exact variable names as keys "
                "inside `answers`, for example "
                f"{example}. "
                "Include every listed key exactly once "
                "in `answers`, even if the value is 0. "
                "Include every listed key exactly "
                "once in `explanations`. "
                "Each explanation must be non-empty, "
                "specific to that variable, and concise. "
                f"{EXPLANATION_CONSISTENCY_INSTRUCTION}"
                "Do not include any keys that are "
                "not listed below. "
                "Put only numeric values in `answers`, "
                "with no dollar signs, commas, or "
                "explanatory text in the values. "
                "Do not rely on plain text outside "
                "the JSON object for the final "
                "answers. "
            )
        else:
            answer_instructions = (
                "A prior response omitted required "
                "keys. Return a single JSON object "
                "containing only the missing quantities "
                "listed below. "
                "Use the exact variable names as keys, "
                f"for example {{{requested_keys}}}. "
                "Include every listed key exactly once, even if the value is 0. "
                "Do not include any keys that are not listed below. "
                "Put only numeric values in the JSON "
                "object, with no dollar signs, "
                "commas, or explanatory text in "
                "the values. "
                "Do not rely on plain text outside "
                "the JSON object for the final "
                "answers. "
            )
    else:
        if include_explanations:
            answer_instructions = (
                "A prior response omitted required "
                "answers and/or explanations. "
                "Use the `submit_answers` function "
                "exactly once to return an `answers` "
                "object containing the listed "
                "quantities below, and a required "
                "`explanations` object keyed by those "
                "same variables. "
                "Include every listed key exactly once "
                "in `explanations`, and do not leave "
                "any explanation blank. "
                f"{EXPLANATION_CONSISTENCY_INSTRUCTION}"
                "Use the exact variable names as keys "
                "inside `answers` and put only numeric "
                "values there. "
                "Include every listed key exactly once "
                "in `answers`, even if the value "
                "is 0. "
                "Do not include any keys that are not listed below. "
                "Do not rely on plain text for the final answers. "
            )
        else:
            answer_instructions = (
                "A prior response omitted required "
                "keys. Use the `submit_answers` "
                "function exactly once to return only "
                "the missing quantities listed below. "
                "Use the exact variable names as keys and put only numeric values in "
                "the arguments. "
                "Include every listed key exactly once, even if the value is 0. "
                "Do not include any keys that are not listed below. "
                "Do not rely on plain text for the final answers. "
            )

    return (
        f"{TASK_PREFACE}"
        f"{description}\n\n"
        "Provide only the following listed policy quantities for this household:\n"
        f"{requested_variables}\n\n"
        f"{answer_instructions}"
        "If an answer is a currency amount, give the annual amount. "
        "If an answer is a rate, give a decimal (e.g. 0.25 for 25%)."
    )


def make_explanation_repair_prompt(
    scenario: Scenario,
    variables: list[str],
    answers: dict[str, float],
) -> str:
    """Create a prompt for missing explanations only."""
    description = describe_household(scenario)
    requested_variables = "\n".join(
        f"- {variable}: {get_variable_description(variable, country=scenario.country)}"
        for variable in variables
    )
    returned_answers = "\n".join(
        f"- {variable}: {answers[variable]}" for variable in variables
    )

    return (
        f"{TASK_PREFACE}"
        f"{description}\n\n"
        "A prior response returned numeric answers but omitted explanations for "
        "the following policy quantities:\n"
        f"{requested_variables}\n\n"
        "Use these already-returned numeric answers as context; do not recalculate "
        "or return numeric answers in this repair response:\n"
        f"{returned_answers}\n\n"
        "Use the `submit_explanations` function exactly once. Return only a "
        "single object keyed by the listed variable names. Include every listed "
        "key exactly once, and make every explanation non-empty, specific to "
        "that variable, and concise. Each explanation must support the "
        "already-returned numeric answer for the same variable; do not mention "
        "a different final amount."
    )
