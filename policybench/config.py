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
    "claude-opus-4.8": "claude-opus-4-8",
    "claude-opus-4.7": "claude-opus-4-7",
    "claude-sonnet-5": "claude-sonnet-5",
    "claude-sonnet-4.6": "claude-sonnet-4-6",
    "claude-haiku-4.5": "claude-haiku-4-5-20251001",
    "grok-4.3": "xai/grok-4.3",
    "grok-build-0.1": "xai/grok-build-0.1",
    "gpt-5.5": "gpt-5.5",
    "gpt-5.4-mini": "gpt-5.4-mini",
    "gpt-5.4-nano": "gpt-5.4-nano",
    "gemini-3.1-pro-preview": "gemini/gemini-3.1-pro-preview",
    "gemini-3.5-flash": "gemini/gemini-3.5-flash",
    "gemini-3-flash-preview": "gemini/gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview": "gemini/gemini-3.1-flash-lite-preview",
    "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
    "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
    "kimi-k2.6": "openrouter/moonshotai/kimi-k2.6",
    "glm-5.2": "openrouter/z-ai/glm-5.2",
    "minimax-m3": "openrouter/minimax/minimax-m3",
    "qwen-3.7-max": "openrouter/qwen/qwen3.7-max",
}

# Per-1M-token USD prices for models litellm's cost map does not yet cover
# (typically brand-new provider preview models). Used only as a fallback when a
# run's reconstructed per-call cost is missing, so the leaderboard can still
# show a cost. Keyed by the display id used in predictions.csv.gz.
PRICE_OVERRIDES_PER_1M: dict[str, dict[str, float]] = {
    # grok-build-0.1: $1 / $2 per 1M input/output tokens (https://x.ai/api).
    "grok-build-0.1": {"input": 1.0, "output": 2.0},
    # claude-fable-5: $10 / $50 per 1M input/output tokens
    # (https://platform.claude.com/docs/en/about-claude/models/overview).
    "claude-fable-5": {"input": 10.0, "output": 50.0},
    # claude-sonnet-5: $3 / $15 per 1M standard rate (same source). litellm's
    # map carries the same figures; this fallback keeps the leaderboard priced
    # if reconstruction is unavailable. Introductory billing ($2 / $10 through
    # 2026-08-31) is intentionally not used — costs compare at standard rates.
    "claude-sonnet-5": {"input": 3.0, "output": 15.0},
    # Open-weight additions, per-1M USD from the OpenRouter live model list
    # (https://openrouter.ai/api/v1/models, retrieved 2026-07-05). DeepSeek
    # runs on its native API at the same list prices.
    "deepseek-v4-pro": {"input": 0.435, "output": 0.87},
    "deepseek-v4-flash": {"input": 0.09, "output": 0.18},
    "kimi-k2.6": {"input": 0.66, "output": 3.41},
    "glm-5.2": {"input": 0.574, "output": 1.804},
    "minimax-m3": {"input": 0.3, "output": 1.2},
    "qwen-3.7-max": {"input": 1.25, "output": 3.75},
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
