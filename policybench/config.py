"""Configuration constants for PolicyBench."""

from policybench.spec import (
    DEFAULT_PROGRAM_SET,
    available_spec_ids,
    binary_output_ids,
    get_output_ids,
)

# Tax year for all evaluations
TAX_YEAR = 2026

# Random seed for reproducible scenario generation
SEED = 42

# Default benchmark country
DEFAULT_COUNTRY = "us"

# Canonical default benchmark models. This list should track the published
# no-tools leaderboard rather than every model ever probed in the repo.
#
# Most identifiers below are provider aliases (e.g. ``claude-opus-4.7`` or
# ``gpt-5.5``), not dated revisions. Provider responses can be routed to
# different underlying weights over time. Runs after 2026-05-01 capture
# ``provider_response_id``, ``provider_system_fingerprint``, and
# ``provider_resolved_model`` in ``predictions.csv.gz``; older snapshots
# only have the alias and the raw response payload.
MODELS = {
    "claude-fable-5": "claude-fable-5",
    "claude-opus-4.7": "claude-opus-4-7",
    "claude-sonnet-4.6": "claude-sonnet-4-6",
    "claude-haiku-4.5": "claude-haiku-4-5-20251001",
    "grok-4.3": "xai/grok-4.3",
    "grok-4.20": "xai/grok-4.20-reasoning",
    "grok-4.1-fast": "xai/grok-4-1-fast-non-reasoning",
    "gpt-5.5": "gpt-5.5",
    "gpt-5.4-mini": "gpt-5.4-mini",
    "gpt-5.4-nano": "gpt-5.4-nano",
    "gemini-3.1-pro-preview": "gemini/gemini-3.1-pro-preview",
    "gemini-3.5-flash": "gemini/gemini-3.5-flash",
    "gemini-3-flash-preview": "gemini/gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview": "gemini/gemini-3.1-flash-lite-preview",
    "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
    "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
}

# Current output set. The benchmark contains signed household net-income
# components plus coverage booleans with explicit impact weights.
US_HEADLINE_PROGRAMS = get_output_ids("us", "headline")
UK_HEADLINE_PROGRAMS = get_output_ids("uk", "headline")

COUNTRY_PROGRAMS = {
    "us": US_HEADLINE_PROGRAMS,
    "uk": UK_HEADLINE_PROGRAMS,
}

# Default benchmark outputs for new runs.
PROGRAMS = US_HEADLINE_PROGRAMS

# Binary (eligibility) variables -- evaluated with accuracy, not MAE
BINARY_PROGRAMS = binary_output_ids()

# Number of scenarios to generate
NUM_SCENARIOS = 100


def get_programs(country: str, program_set: str = DEFAULT_PROGRAM_SET) -> list[str]:
    """Return the configured benchmark outputs for a country and program set."""
    try:
        return get_output_ids(country, program_set)
    except ValueError as exc:
        valid_countries = ", ".join(sorted(COUNTRY_PROGRAMS))
        valid_sets = sorted({DEFAULT_PROGRAM_SET, *available_spec_ids()})
        raise ValueError(
            "Unsupported country/program_set "
            f"('{country}', '{program_set}'). Valid countries: "
            f"{valid_countries}. Valid program sets: "
            f"{', '.join(sorted(set(valid_sets)))}."
        ) from exc
