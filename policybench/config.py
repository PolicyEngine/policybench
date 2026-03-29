"""Configuration constants for PolicyBench."""

# Tax year for all evaluations
TAX_YEAR = 2025

# Random seed for reproducible scenario generation
SEED = 42

# Models to benchmark (latest provider-published versions as of 2026-03-25)
MODELS = {
    "claude-opus-4.6": "claude-opus-4-6",
    "claude-sonnet-4.6": "claude-sonnet-4-6",
    "claude-haiku-4.5": "claude-haiku-4-5-20251001",
    "gpt-5.4": "gpt-5.4",
    "gpt-5.4-mini": "gpt-5.4-mini",
    "gpt-5.4-nano": "gpt-5.4-nano",
    "gemini-3.1-pro-preview": "gemini/gemini-3.1-pro-preview",
    "gemini-3-flash-preview": "gemini/gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview": "gemini/gemini-3.1-flash-lite-preview",
}

# PolicyEngine-US variables to evaluate
PROGRAMS = [
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

# Binary (eligibility) variables — evaluated with accuracy, not MAE
BINARY_PROGRAMS = ["is_medicaid_eligible", "free_school_meals"]

# Rate variables — evaluated with absolute error, not percentage
RATE_PROGRAMS = []

# Number of scenarios to generate
NUM_SCENARIOS = 100
