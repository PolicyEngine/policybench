"""Configuration constants for PolicyBench."""

# Tax year for all evaluations
TAX_YEAR = 2025

# Random seed for reproducible scenario generation
SEED = 42

# Default benchmark country
DEFAULT_COUNTRY = "us"

# Models to benchmark (latest provider-published versions as of 2026-03-30)
MODELS = {
    "claude-opus-4.6": "claude-opus-4-6",
    "claude-sonnet-4.6": "claude-sonnet-4-6",
    "claude-haiku-4.5": "claude-haiku-4-5-20251001",
    "grok-4.20": "xai/grok-4.20-reasoning",
    "grok-4.1-fast": "xai/grok-4-1-fast-non-reasoning",
    "gpt-5.4": "gpt-5.4",
    "gpt-5.4-pro": "gpt-5.4-pro",
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

COUNTRY_PROGRAMS = {
    "us": US_PROGRAMS,
    "uk": UK_PROGRAMS,
}

# Backward-compatible default
PROGRAMS = US_PROGRAMS

# Binary (eligibility) variables — evaluated with accuracy, not MAE
BINARY_PROGRAMS = ["is_medicaid_eligible", "free_school_meals"]

# Rate variables — evaluated with absolute error, not percentage
RATE_PROGRAMS = []

# Number of scenarios to generate
NUM_SCENARIOS = 100


def get_programs(country: str) -> list[str]:
    """Return the configured benchmark outputs for a country."""
    try:
        return COUNTRY_PROGRAMS[country]
    except KeyError as exc:
        valid = ", ".join(sorted(COUNTRY_PROGRAMS))
        raise ValueError(f"Unsupported country '{country}'. Valid choices: {valid}") from exc
