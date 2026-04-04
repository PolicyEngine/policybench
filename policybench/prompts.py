"""Prompt templates for PolicyBench evaluations."""

from policybench.scenarios import (
    Person,
    Scenario,
)

# Variable descriptions for natural language prompts
US_VARIABLE_DESCRIPTIONS = {
    "adjusted_gross_income": (
        "federal adjusted gross income (AGI), after above-the-line deductions "
        "but before standard or itemized deductions and exemptions"
    ),
    "income_tax": (
        "net federal income tax liability after refundable credits "
        "(this can be negative if refundable credits exceed pre-credit tax liability)"
    ),
    "income_tax_before_refundable_credits": (
        "federal income tax before refundable credits are applied "
        "(do not subtract refundable credits)"
    ),
    "eitc": "Earned Income Tax Credit amount",
    "ctc": "Child Tax Credit amount",
    "income_tax_refundable_credits": (
        "total refundable federal tax credits only "
        "(not pre-credit tax liability and not non-refundable credits)"
    ),
    "snap": "annual SNAP (food stamps) benefit amount",
    "ssi": "annual Supplemental Security Income (SSI) amount",
    "free_school_meals": (
        "whether the household qualifies for free school meals "
        "(1 if yes, 0 if no; reduced-price meals do not count as 1)"
    ),
    "is_medicaid_eligible": (
        "whether anyone in the household is eligible for Medicaid "
        "(1 if yes, 0 if no)"
    ),
    "state_agi": "state adjusted gross income (state AGI)",
    "state_income_tax_before_refundable_credits": (
        "state income tax before refundable credits are applied "
        "(do not subtract state refundable credits)"
    ),
    "state_refundable_credits": "total refundable state tax credits only",
    "household_state_income_tax": "state income tax liability",
}

UK_VARIABLE_DESCRIPTIONS = {
    "income_tax": "annual UK Income Tax liability",
    "national_insurance": "annual UK National Insurance contributions",
    "child_benefit": "annual Child Benefit amount",
    "universal_credit": "annual Universal Credit amount",
    "pension_credit": "annual Pension Credit amount",
    "housing_benefit": "annual Housing Benefit amount",
    "pip": "annual Personal Independence Payment (PIP) amount",
    "carers_allowance": "annual Carer's Allowance amount",
    "attendance_allowance": "annual Attendance Allowance amount",
    "council_tax": "annual Council Tax liability",
}

INPUT_LABEL_OVERRIDES = {
    "adjusted_gross_income": "adjusted gross income",
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
    "employment_income": "employment income",
    "estate_income": "estate income",
    "excess_withheld_payroll_tax": "excess withheld payroll tax",
    "farm_income": "farm income",
    "farm_operations_income": "farm operations income",
    "farm_rent_income": "farm rent income",
    "general_business_credit": "general business credit",
    "has_esi": "has employer-sponsored insurance",
    "has_marketplace_health_coverage": "has Marketplace health coverage",
    "has_never_worked": "has never worked",
    "health_insurance_premiums_without_medicare_part_b": (
        "health insurance premiums excluding Medicare Part B"
    ),
    "health_savings_account_ald": "health savings account deduction",
    "home_mortgage_interest": "home mortgage interest",
    "hours_worked_last_week": "hours worked last week",
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
    "tip_income": "tip income",
    "traditional_401k_contributions": "traditional 401(k) contributions",
    "traditional_ira_contributions": "traditional IRA contributions",
    "unadjusted_basis_qualified_property": (
        "unadjusted basis of qualified property"
    ),
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
    "petrol_spending": "petrol spending",
    "pip": "Personal Independence Payment",
    "pip_dl_category": "PIP daily living award",
    "pip_m_category": "PIP mobility award",
    "private_pension_contributions": "private pension contributions",
    "private_pension_income": "private pension income",
    "property_income": "property income",
    "recreation_consumption": "recreation spending",
    "region": "region",
    "rent": "rent",
    "restaurants_and_hotels_consumption": "restaurants and hotels spending",
    "savings": "savings",
    "savings_interest_income": "savings interest income",
    "state_pension_reported": "state pension income",
    "tenure_type": "tenure",
    "transport_consumption": "transport spending",
}


NON_MONETARY_NUMERIC_FIELDS = {
    "weekly_hours_worked",
    "hours_worked_last_week",
    "hours_worked",
    "num_vehicles",
}


def _currency_symbol(country: str) -> str:
    return "£" if country == "uk" else "$"


def get_variable_description(variable: str, country: str = "us") -> str:
    """Return the prompt description for a benchmark output."""
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


def _format_input_line(field: str, value, country: str = "us") -> str:
    label = _humanize_input_label(field)
    if isinstance(value, bool):
        return f"- {label}"
    if isinstance(value, str):
        return f"- {label}: {value.replace('_', ' ').title()}"
    if field in NON_MONETARY_NUMERIC_FIELDS:
        return f"- {label}: {float(value):,.0f}"
    return f"- {label}: {_currency_symbol(country)}{float(value):,.0f}"


def _person_heading(person: Person) -> str:
    if person.name.startswith("adult"):
        return person.name.replace("adult", "Adult ")
    if person.name.startswith("child"):
        return person.name.replace("child", "Child ")
    return person.name.replace("_", " ").title()


def describe_person(person: Person, country: str = "us") -> str:
    """Create a structured description of a person."""
    lines = [
        f"{_person_heading(person)}:",
        f"- age: {person.age}",
    ]

    if person.name.startswith("adult") or abs(person.employment_income) > 1e-6:
        lines.append(
            f"- employment income: {_currency_symbol(country)}{person.employment_income:,.0f}"
        )

    for field, value in sorted(person.inputs.items()):
        lines.append(_format_input_line(field, value, country=country))

    return "\n".join(lines)


def _describe_entity_inputs(title: str, inputs: dict[str, object], country: str = "us") -> str:
    if not inputs:
        return ""
    lines = [f"{title}:"]
    for field, value in sorted(inputs.items()):
        lines.append(_format_input_line(field, value, country=country))
    return "\n".join(lines)


def describe_household(scenario: Scenario) -> str:
    """Create a structured description of a household."""
    lines = [
        "Household:",
        f"- {'region' if scenario.country == 'uk' else 'state'}: {scenario.state}",
        f"- tax year: {scenario.year}",
        "",
    ]

    if scenario.filing_status:
        lines.insert(2, f"- filing status: {scenario.filing_status}")

    for adult in scenario.adults:
        lines.extend([describe_person(adult, country=scenario.country), ""])

    if scenario.children:
        for child in scenario.children:
            lines.extend([describe_person(child, country=scenario.country), ""])
    else:
        lines.extend(["Children:", "- none", ""])

    for title, inputs in (
        ("Tax unit", scenario.tax_unit_inputs),
        ("SPM unit", scenario.spm_unit_inputs),
        ("Household inputs", scenario.household_inputs),
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
    include_explanations: bool = False,
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
            answer_instructions = (
                "Return a single JSON object with an `answers` object and a required "
                "`explanations` object. "
                f'Use the exact variable names as keys inside `answers`, for example {{"answers": {{{requested_keys}}}, "explanations": {{"{variables[0]}": "short note"}}}}. '
                "Include every requested key exactly once in `answers`, even if the value is 0. "
                "Include every requested key exactly once in `explanations`. "
                "Keep each explanation to one short sentence of at most 12 words. "
                "Each explanation must be non-empty and specific to that variable. "
                "Put only numeric values in `answers`, with no dollar signs, commas, or explanatory text in the values. "
                "Do not rely on plain text outside the JSON object for the final answers. "
            )
        else:
            answer_instructions = (
                "Return a single JSON object containing every requested quantity. "
                f'Use the exact variable names as keys, for example {{{requested_keys}}}. '
                "Include every requested key exactly once, even if the value is 0. "
                "Put only numeric values in the JSON object, with no dollar signs, "
                "commas, or explanatory text in the values. "
                "Do not rely on plain text outside the JSON object for the final answers. "
            )
    else:
        if include_explanations:
            answer_instructions = (
                "Use the `submit_answers` function exactly once. "
                "Return an `answers` object with every requested quantity and a required "
                "`explanations` object with brief notes keyed by the same variable names. "
                "Keep each explanation to one short sentence of at most 12 words. "
                "Include every requested key exactly once in `explanations`, and do not leave any explanation blank. "
                "Use the exact variable names as keys inside `answers` and put only numeric values there. "
                "Include every requested key exactly once in `answers`, even if the value is 0. "
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
    include_explanations: bool = False,
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
            answer_instructions = (
                "A prior response omitted required answers and/or explanations. Return a single JSON object "
                "with an `answers` object containing the listed quantities below "
                "and a required `explanations` object keyed by those same variables. "
                f'Use the exact variable names as keys inside `answers`, for example {{"answers": {{{requested_keys}}}}}. '
                "Include every listed key exactly once in `answers`, even if the value is 0. "
                "Include every listed key exactly once in `explanations`. "
                "Keep each explanation to one short sentence of at most 12 words. "
                "Each explanation must be non-empty and specific to that variable. "
                "Do not include any keys that are not listed below. "
                "Put only numeric values in `answers`, with no dollar signs, commas, or explanatory text in the values. "
                "Do not rely on plain text outside the JSON object for the final answers. "
            )
        else:
            answer_instructions = (
                "A prior response omitted required keys. Return a single JSON object "
                "containing only the missing quantities listed below. "
                f'Use the exact variable names as keys, for example {{{requested_keys}}}. '
                "Include every listed key exactly once, even if the value is 0. "
                "Do not include any keys that are not listed below. "
                "Put only numeric values in the JSON object, with no dollar signs, "
                "commas, or explanatory text in the values. "
                "Do not rely on plain text outside the JSON object for the final answers. "
            )
    else:
        if include_explanations:
            answer_instructions = (
                "A prior response omitted required answers and/or explanations. Use the `submit_answers` "
                "function exactly once to return an `answers` object containing the listed quantities below, "
                "and a required `explanations` object keyed by those same variables. "
                "Keep each explanation to one short sentence of at most 12 words. "
                "Include every listed key exactly once in `explanations`, and do not leave any explanation blank. "
                "Use the exact variable names as keys inside `answers` and put only numeric values there. "
                "Include every listed key exactly once in `answers`, even if the value is 0. "
                "Do not include any keys that are not listed below. "
                "Do not rely on plain text for the final answers. "
            )
        else:
            answer_instructions = (
                "A prior response omitted required keys. Use the `submit_answers` "
                "function exactly once to return only the missing quantities listed below. "
                "Use the exact variable names as keys and put only numeric values in "
                "the arguments. "
                "Include every listed key exactly once, even if the value is 0. "
                "Do not include any keys that are not listed below. "
                "Do not rely on plain text for the final answers. "
            )

    return (
        f"{description}\n\n"
        "Provide only the following listed policy quantities for this household:\n"
        f"{requested_variables}\n\n"
        f"{answer_instructions}"
        "If an answer is a currency amount, give the annual amount. "
        "If an answer is a rate, give a decimal (e.g. 0.25 for 25%)."
    )
