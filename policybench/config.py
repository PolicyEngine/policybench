"""Configuration constants for PolicyBench."""

# Tax year for all evaluations
TAX_YEAR = 2025

# Random seed for reproducible scenario generation
SEED = 42

# Default benchmark country
DEFAULT_COUNTRY = "us"

# Canonical default benchmark models. This list should track the published
# no-tools leaderboard rather than every model ever probed in the repo.
MODELS = {
    "claude-opus-4.6": "claude-opus-4-6",
    "claude-sonnet-4.6": "claude-sonnet-4-6",
    "claude-haiku-4.5": "claude-haiku-4-5-20251001",
    "grok-4.20": "xai/grok-4.20-reasoning",
    "grok-4.1-fast": "xai/grok-4-1-fast-non-reasoning",
    "gpt-5.4": "gpt-5.4",
    "gpt-5.4-mini": "gpt-5.4-mini",
    "gpt-5.4-nano": "gpt-5.4-nano",
    "gemini-3.1-pro-preview": "gemini/gemini-3.1-pro-preview",
    "gemini-3-flash-preview": "gemini/gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview": "gemini/gemini-3.1-flash-lite-preview",
}

# PolicyEngine-US variables to evaluate
US_PROGRAMS = [
    # Federal tax
    "adjusted_gross_income",
    "income_tax_before_refundable_credits",
    # Credits
    "eitc",
    "ctc",
    "income_tax_refundable_credits",
    # Benefits
    "snap",
    "ssi",
    "free_school_meals",
    "is_medicaid_eligible",
    # State tax
    "state_agi",
    "state_income_tax_before_refundable_credits",
    "state_refundable_credits",
    "household_state_income_tax",
]

# PolicyEngine-UK variables to evaluate
UK_PROGRAMS = [
    "income_tax",
    "national_insurance",
    "child_benefit",
    "universal_credit",
    "pension_credit",
    "pip",
]

# Proposed v2 headline sets. These drop intermediate tax-base quantities from
# the main ranking and focus on disjoint household-budget components.
US_HEADLINE_PROGRAMS_V2 = [
    "employee_payroll_tax",
    "self_employment_tax",
    "income_tax_before_refundable_credits",
    "household_state_income_tax",
    "eitc",
    "ctc",
    "snap",
    "ssi",
]

UK_HEADLINE_PROGRAMS_V2 = [
    "income_tax",
    "national_insurance",
    "council_tax_less_benefit",
    "child_benefit",
    "universal_credit",
    "pension_credit",
    "pip",
]

# Supplementary outputs that remain useful diagnostically but do not fit the
# proposed headline cash-component benchmark.
US_SUPPLEMENTARY_PROGRAMS_V2 = [
    "free_school_meals",
    "is_medicaid_eligible",
]

UK_SUPPLEMENTARY_PROGRAMS_V2: list[str] = []

COUNTRY_PROGRAMS = {
    "us": US_PROGRAMS,
    "uk": UK_PROGRAMS,
}

PROGRAM_SETS = {
    "v1": COUNTRY_PROGRAMS,
    "v2_headline": {
        "us": US_HEADLINE_PROGRAMS_V2,
        "uk": UK_HEADLINE_PROGRAMS_V2,
    },
    "v2_supplementary": {
        "us": US_SUPPLEMENTARY_PROGRAMS_V2,
        "uk": UK_SUPPLEMENTARY_PROGRAMS_V2,
    },
}

# Backward-compatible default
PROGRAMS = US_PROGRAMS

# Binary (eligibility) variables — evaluated with accuracy, not MAE
BINARY_PROGRAMS = ["is_medicaid_eligible", "free_school_meals"]

# Rate variables — evaluated with absolute error, not percentage
RATE_PROGRAMS = []

# Proposed impact-score floor. Each household gets equal overall weight, while
# programs within a household receive a blend of equal weighting and weighting
# by absolute contribution to household net income.
HOUSEHOLD_IMPACT_SCORE_FLOOR = 0.3

# Number of scenarios to generate
NUM_SCENARIOS = 100


def get_programs(country: str, program_set: str = "v1") -> list[str]:
    """Return the configured benchmark outputs for a country and program set."""
    try:
        return PROGRAM_SETS[program_set][country]
    except KeyError as exc:
        valid_countries = ", ".join(sorted(COUNTRY_PROGRAMS))
        valid_sets = ", ".join(sorted(PROGRAM_SETS))
        raise ValueError(
            "Unsupported country/program_set "
            f"('{country}', '{program_set}'). Valid countries: "
            f"{valid_countries}. Valid program sets: {valid_sets}."
        ) from exc
