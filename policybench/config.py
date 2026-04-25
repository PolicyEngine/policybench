"""Configuration constants for PolicyBench."""

from policybench.spec import (
    DEFAULT_PROGRAM_SET,
    binary_output_ids,
    get_output_ids,
    rate_output_ids,
)

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

# Legacy public benchmark outputs. These are loaded from
# `benchmark_specs.json`; keep the names for backward compatibility with tests,
# scripts, and existing result artifacts.
US_PROGRAMS = get_output_ids("us", "v1")
UK_PROGRAMS = get_output_ids("uk", "v1")

# Rebuilt v2 output sets. The headline set contains signed household
# net-income components plus coverage booleans with explicit impact weights;
# intermediate bases remain supplementary diagnostics.
US_HEADLINE_PROGRAMS_V2 = get_output_ids("us", "v2_headline")
UK_HEADLINE_PROGRAMS_V2 = get_output_ids("uk", "v2_headline")
US_SUPPLEMENTARY_PROGRAMS_V2 = get_output_ids("us", "v2_supplementary")
UK_SUPPLEMENTARY_PROGRAMS_V2 = []

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

# Default rebuilt benchmark outputs for new runs.
PROGRAMS = US_HEADLINE_PROGRAMS_V2

# Binary (eligibility) variables -- evaluated with accuracy, not MAE
BINARY_PROGRAMS = binary_output_ids()

# Rate variables -- evaluated with absolute error, not percentage
RATE_PROGRAMS = rate_output_ids()

# Proposed impact-score floor. Each household gets equal overall weight, while
# programs within a household receive a blend of equal weighting and weighting
# by absolute contribution to household net income.
HOUSEHOLD_IMPACT_SCORE_FLOOR = 0.3

# Number of scenarios to generate
NUM_SCENARIOS = 100


def get_programs(country: str, program_set: str = DEFAULT_PROGRAM_SET) -> list[str]:
    """Return the configured benchmark outputs for a country and program set."""
    try:
        return get_output_ids(country, program_set)
    except ValueError as exc:
        valid_countries = ", ".join(sorted(COUNTRY_PROGRAMS))
        valid_sets = ", ".join(sorted(PROGRAM_SETS))
        raise ValueError(
            "Unsupported country/program_set "
            f"('{country}', '{program_set}'). Valid countries: "
            f"{valid_countries}. Valid program sets: {valid_sets}."
        ) from exc
