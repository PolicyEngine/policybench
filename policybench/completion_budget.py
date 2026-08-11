"""Helpers for provider-specific completion-budget request fields."""

from __future__ import annotations

# Length-terminated requests may double beyond their normal serving budget.
# A model card can lower this default when its provider has a documented cap.
MAX_ESCALATED_COMPLETION_TOKENS = 128_000

COMPLETION_BUDGET_KEYS = (
    "max_completion_tokens",
    "max_output_tokens",
    "max_tokens",
)


def completion_budget_from_kwargs(request_kwargs: dict) -> int | None:
    """Return the active completion budget from a provider request."""
    for key in COMPLETION_BUDGET_KEYS:
        value = request_kwargs.get(key)
        if value is not None:
            return int(value)
    return None


def with_completion_budget(request_kwargs: dict, budget: int) -> dict:
    """Copy a request and replace its provider-specific completion budget."""
    updated = dict(request_kwargs)
    for key in COMPLETION_BUDGET_KEYS:
        if key in updated:
            updated[key] = int(budget)
            return updated
    raise ValueError("Request has no recognized completion-budget field")


def next_completion_budget(current: int, ceiling: int) -> int | None:
    """Return the next doubled budget, capped at ``ceiling``."""
    if current >= ceiling:
        return None
    return min(current * 2, ceiling)
