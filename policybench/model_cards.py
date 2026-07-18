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

Scores are only comparable when every model answers the same canonical
whole-scenario prompt, so ``explanation_chunk_size`` is closed to new
models: a model that cannot answer the canonical prompt is listed as not
scorable instead (the gauntlet enforces this). The chunked cards below —
gpt-5.5, claude-fable-5, claude-sonnet-5, kimi-k2.6, glm-5.2, and
qwen3.7-max — predate the rule and keep their shipped treatments; an
earlier comparison found chunking made little scoring difference.
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
    # Overrides the thinking-budget completion ceiling for models whose
    # reasoning tail overflows 16,384. Headroom is free — only tokens
    # actually generated bill.
    completion_token_cap: int | None = None
    # Measured during onboarding; informs the run supervisor's projection
    # before live per-scenario costs exist.
    expected_cost_per_scenario_usd: float | None = None
    notes: str = ""


MODEL_CARDS: dict[str, ModelCard] = {
    "gpt-5.6-sol": ModelCard(
        litellm_id="gpt-5.6-sol",
        answer_contract="tool",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.09,
        notes=(
            "Onboarded 2026-07-09: forced tool contract and whole-scenario "
            "requests passed. The 100-scenario sync run cost $8.95; OpenAI "
            "Batch did not yet support the model id."
        ),
    ),
    "gpt-5.6-terra": ModelCard(
        litellm_id="gpt-5.6-terra",
        answer_contract="tool",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.039,
        notes=(
            "Onboarded 2026-07-09: forced tool contract and whole-scenario "
            "requests passed. The 100-scenario sync run cost $3.89; OpenAI "
            "Batch did not yet support the model id."
        ),
    ),
    "gpt-5.6-luna": ModelCard(
        litellm_id="gpt-5.6-luna",
        answer_contract="tool",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.019,
        notes=(
            "Onboarded 2026-07-09: forced tool contract and whole-scenario "
            "requests passed. The 100-scenario sync run cost $1.87; OpenAI "
            "Batch did not yet support the model id."
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
    "xai/grok-4.5": ModelCard(
        litellm_id="xai/grok-4.5",
        answer_contract="tool",
        request_timeout_seconds=420,
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.091,
        notes=(
            "Onboarded 2026-07-10: forced tool contract passed 3/3 and "
            "16/16; the full-scenario probe used 14,225 tokens, so it gets "
            "the thinking-class budget. Timeout matches grok-4.3's 420s for "
            "tail scenarios."
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
    "openrouter/moonshotai/kimi-k3": ModelCard(
        litellm_id="openrouter/moonshotai/kimi-k3",
        answer_contract="json",
        request_timeout_seconds=1200,
        thinking_budget=True,
        completion_token_cap=49_152,
        expected_cost_per_scenario_usd=0.3,
        notes=(
            "Moonshot rejects forced tool_choice with thinking enabled "
            "(same as kimi-k2.6), so it runs the JSON contract — but "
            "whole-scenario, not chunked: reasoning spend is per-call, "
            "not per-variable (a full 16-var probe finished at 12.4k "
            "completion tokens while a 3-var probe hit 31k), so chunking "
            "at 3 would multiply cost ~7x for nothing. The reasoning "
            "tail overflows the shared 16,384 ceiling (one probe burned "
            "all 16,384 in 430s with no answer), so the cap is 49,152 "
            "and the timeout 1200s — enough to generate to the cap at "
            "the observed ~35-40 tok/s; unused headroom is free. Single "
            "OpenRouter endpoint (Moonshot AI, native int4), $3/$15 per "
            "1M tokens."
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
