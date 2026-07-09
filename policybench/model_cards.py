"""Declarative per-model serving treatments.

A ModelCard captures everything the harness must know about how one model's
serving stack behaves: which answer contract it can honor, whether whole-
scenario requests converge or need chunking, how long its slowest calls run,
and whether reasoning-by-default token appetite needs the thinking-class
completion budget. None of this is model *configuration* — every model still
runs unconfigured at its provider-default reasoning effort. Cards only
encode serving-stack facts discovered during onboarding (see
``policybench onboard``).

Cards OVERRIDE the family-prefix heuristics in ``eval_no_tools``; models
without a card (or with a field left ``None``) keep the heuristic treatment.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCard:
    litellm_id: str
    # "tool" | "json" | None (None → family heuristic)
    answer_contract: str | None = None
    # Variables per request when explanations are on; None → no chunking
    # unless the family heuristic chunks (Claude=1, gpt-5.5=3).
    explanation_chunk_size: int | None = None
    request_timeout_seconds: int | None = None
    # True → 16,384-token completion budget on both explanation arms
    # (reasoning bills against the same budget as the answer).
    thinking_budget: bool | None = None
    # Measured during onboarding; informs the run supervisor's projection
    # before live per-scenario costs exist.
    expected_cost_per_scenario_usd: float | None = None
    notes: str = ""


MODEL_CARDS: dict[str, ModelCard] = {
    "gpt-5.6-sol": ModelCard(
        litellm_id="gpt-5.6-sol",
        thinking_budget=True,
        notes=(
            "New reasoning model. Serving treatment must be "
            "rechecked with `policybench onboard` after API access is granted."
        ),
    ),
    "gpt-5.6-terra": ModelCard(
        litellm_id="gpt-5.6-terra",
        thinking_budget=True,
        notes=(
            "New reasoning model. Serving treatment must be "
            "rechecked with `policybench onboard` after API access is granted."
        ),
    ),
    "gpt-5.6-luna": ModelCard(
        litellm_id="gpt-5.6-luna",
        thinking_budget=True,
        notes=(
            "New reasoning model. Serving treatment must be "
            "rechecked with `policybench onboard` after API access is granted."
        ),
    ),
    "gpt-5.5": ModelCard(
        litellm_id="gpt-5.5",
        explanation_chunk_size=3,
        request_timeout_seconds=60,
        thinking_budget=True,
        notes=(
            "Reasons at default (medium) effort; pre-#101 per-chunk budgets "
            "truncated it at exactly the ceiling."
        ),
    ),
    "deepseek/deepseek-v4-pro": ModelCard(
        litellm_id="deepseek/deepseek-v4-pro",
        answer_contract="json",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.011,
        notes="Direct DeepSeek API; no cost field in responses.",
    ),
    "deepseek/deepseek-v4-flash": ModelCard(
        litellm_id="deepseek/deepseek-v4-flash",
        answer_contract="json",
        thinking_budget=True,
    ),
    "openrouter/moonshotai/kimi-k2.6": ModelCard(
        litellm_id="openrouter/moonshotai/kimi-k2.6",
        answer_contract="json",
        explanation_chunk_size=3,
        request_timeout_seconds=600,
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.396,
        notes=(
            "Moonshot returns 400 for forced tool_choice with thinking "
            "enabled; OpenRouter silently reroutes to hosts that reason to "
            "the token ceiling. Whole-scenario JSON overflows into truncated "
            "documents; converges at 3 variables/call."
        ),
    ),
    "openrouter/z-ai/glm-5.2": ModelCard(
        litellm_id="openrouter/z-ai/glm-5.2",
        answer_contract="json",
        explanation_chunk_size=3,
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.09,
        notes=(
            "Reasons to the full ceiling on whole-scenario requests in both "
            "contracts; converges at 3 variables/call."
        ),
    ),
    "openrouter/minimax/minimax-m3": ModelCard(
        litellm_id="openrouter/minimax/minimax-m3",
        answer_contract="tool",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.02,
        notes="Handles forced tool calls cleanly (12s / 926-token probe).",
    ),
    "openrouter/qwen/qwen3.7-max": ModelCard(
        litellm_id="openrouter/qwen/qwen3.7-max",
        answer_contract="json",
        explanation_chunk_size=3,
        request_timeout_seconds=600,
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.129,
        notes=(
            "Alibaba returns 400 for tool_choice=required in thinking mode. "
            "Largest households need >300s even at 3-variable chunks: six "
            "grind rounds at 300s plateaued at 64/100; one 600s round "
            "reached 93."
        ),
    ),
}


def card_for(model_id: str) -> ModelCard | None:
    return MODEL_CARDS.get(model_id)
