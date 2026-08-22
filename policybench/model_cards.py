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
scorable instead (the gauntlet enforces this). The chunked treatments that
predate the rule keep their shipped behavior — the cards below for
gpt-5.5, claude-fable-5, claude-sonnet-5, kimi-k2.6, glm-5.2, and
qwen3.7-max, plus the claude- family heuristic (1 output per request) that
covers the older Claude roster; an earlier comparison found chunking made
little scoring difference. The paper documents the asymmetry.
"""

from __future__ import annotations

from dataclasses import dataclass

from policybench.completion_budget import MAX_ESCALATED_COMPLETION_TOKENS

PROMPT_CONTRACT_VERSION = "2026-08-09-v2-scoring-contract"
CLAUDE_EXPLANATION_CHUNK_SIZE = 1

# The Claude roster that shipped under the pre-canonical-prompt regime keeps
# its 1-output-per-request treatment; chunking is closed to new models, so
# Claude models added after July 2026 answer the whole-scenario request.
GRANDFATHERED_CHUNKED_CLAUDE_MODELS = frozenset(
    {
        "claude-fable-5",
        "claude-sonnet-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    }
)


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
    # Overrides the thinking-class starting budget for models whose reasoning
    # tail overflows 16,384. Headroom is free — only generated tokens bill.
    completion_token_cap: int | None = None
    # Hard provider output limit, when it is lower than PolicyBench's 128k
    # escalation ceiling. This is distinct from ``completion_token_cap``,
    # which selects the model's starting budget rather than limiting retries.
    provider_max_completion_tokens: int | None = None
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
    "claude-sonnet-4-6": ModelCard(
        litellm_id="claude-sonnet-4-6",
        provider_max_completion_tokens=64_000,
        notes="Provider output ceiling recorded by the serving metadata.",
    ),
    "claude-haiku-4-5-20251001": ModelCard(
        litellm_id="claude-haiku-4-5-20251001",
        provider_max_completion_tokens=64_000,
        notes="Provider output ceiling recorded by the serving metadata.",
    ),
    "gemini/gemini-3.1-pro-preview": ModelCard(
        litellm_id="gemini/gemini-3.1-pro-preview",
        provider_max_completion_tokens=65_536,
        notes="Provider output ceiling recorded by the serving metadata.",
    ),
    "gemini/gemini-3.1-flash-lite-preview": ModelCard(
        litellm_id="gemini/gemini-3.1-flash-lite-preview",
        provider_max_completion_tokens=65_536,
        notes="Provider output ceiling recorded by the serving metadata.",
    ),
    "gemini/gemini-3.5-flash": ModelCard(
        litellm_id="gemini/gemini-3.5-flash",
        provider_max_completion_tokens=65_535,
        notes="Provider output ceiling recorded by the serving metadata.",
    ),
    "gemini/gemini-3-flash-preview": ModelCard(
        litellm_id="gemini/gemini-3-flash-preview",
        provider_max_completion_tokens=65_535,
        notes="Provider output ceiling recorded by the serving metadata.",
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
    "xai/grok-4.6": ModelCard(
        litellm_id="xai/grok-4.6",
        answer_contract="tool",
        request_timeout_seconds=600,
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.07,
        notes=(
            "Provisional card mirroring grok-4.5 ahead of the 2026-08-20 "
            "gauntlet; flagship successor released 2026-08-12 at $2/$6 "
            "per 1M (litellm map)."
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
    "gemini/gemini-3.6-flash": ModelCard(
        litellm_id="gemini/gemini-3.6-flash",
        answer_contract="tool",
        thinking_budget=True,
        provider_max_completion_tokens=65_536,
        expected_cost_per_scenario_usd=0.07,
        notes=(
            "Onboarded 2026-07-21: forced tool contract passed 3/3 and "
            "16/16 whole-scenario (8,567 completion tokens), unlike the "
            "older Gemini roster, which runs the JSON contract by family "
            "heuristic. Cost estimated from the full-scenario probe at "
            "launch pricing ($1.50/$7.50 per 1M)."
        ),
    ),
    "gemini/gemini-3.7-flash": ModelCard(
        litellm_id="gemini/gemini-3.7-flash",
        answer_contract="tool",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.012,
        notes=(
            "Onboarded 2026-08-17: forced tool contract passed 3/3 and "
            "16/16 whole-scenario (2,709 completion tokens). Introductory "
            "pricing $0.75/$3.75 per 1M through 2026-12-31; doubles "
            "2027-01-01."
        ),
    ),
    "openrouter/stealth/ox-alpha": ModelCard(
        litellm_id="openrouter/stealth/ox-alpha",
        answer_contract="tool",
        request_timeout_seconds=600,
        thinking_budget=True,
        provider_max_completion_tokens=131_072,
        expected_cost_per_scenario_usd=0.0,
        notes=(
            "Cloaked OpenRouter preview, free window from 2026-08-21; "
            "identity unconfirmed. Provisional card for the preview run — "
            "publishes beside the board, never in it. Contract set by the "
            "2026-08-20 gauntlet."
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
    "openrouter/qwen/qwen3.8-max": ModelCard(
        litellm_id="openrouter/qwen/qwen3.8-max",
        answer_contract="json",
        request_timeout_seconds=2400,
        thinking_budget=True,
        completion_token_cap=98_304,
        expected_cost_per_scenario_usd=0.219,
        notes=(
            "Onboarded 2026-08-05: the heaviest reasoner on the roster. "
            "Alibaba rejects forced tool_choice (same "
            "invalid_parameter_error as qwen3.7-max), so it runs the "
            "JSON contract — whole-scenario, per the canonical-prompt "
            "rule. Reasoning is per-call and enormous: a 3-variable "
            "probe used 40,423 completion tokens (871s) and the full "
            "16-variable probe 36,083 (738s), both finish=stop; at the "
            "K3 cap of 49,152 one probe died at finish=length with "
            "nothing parseable, so the cap is 98,304 and the timeout "
            "2400s (~50 tok/s observed; unused headroom is free). "
            "$2/$6 per 1M on OpenRouter/QwenCloud."
        ),
    ),
    "openrouter/thinkingmachines/inkling": ModelCard(
        litellm_id="openrouter/thinkingmachines/inkling",
        answer_contract="tool",
        request_timeout_seconds=1200,
        thinking_budget=True,
        completion_token_cap=49_152,
        expected_cost_per_scenario_usd=0.088,
        notes=(
            "Onboarded 2026-08-03: forced tool contract passed 3/3 and "
            "the whole-scenario 16-variable probe 16/16 once given "
            "reasoning headroom (the default 64-token/variable budget "
            "died at finish=length — reasoning bills as completion). The "
            "full probe used 21,161 completion tokens, over the shared "
            "16,384 ceiling, so the cap stays at 49,152 and the timeout "
            "at 1200s (~80 tok/s observed; unused headroom is free). "
            "$1/$4.05 per 1M on OpenRouter."
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


def completion_budget_ceiling_for(model_id: str) -> int:
    """Return the documented hard provider cap or PolicyBench's 128k default."""
    card = card_for(model_id)
    provider_max = card.provider_max_completion_tokens if card is not None else None
    if provider_max is None:
        return MAX_ESCALATED_COMPLETION_TOKENS
    if provider_max <= 0:
        raise ValueError("provider_max_completion_tokens must be positive")
    return min(MAX_ESCALATED_COMPLETION_TOKENS, provider_max)


def answer_contract_for(model_id: str) -> str:
    """Return the effective structured-answer contract for a model."""
    card = card_for(model_id)
    if card is not None and card.answer_contract is not None:
        return card.answer_contract
    if model_id.startswith("deepseek/") or model_id.startswith("gemini/"):
        return "json"
    return "tool"


def explanation_chunk_size_for(
    model_id: str,
    *,
    chunk_override: str | None = None,
) -> int | None:
    """Return the effective explanation-output chunk size for a model."""
    if chunk_override == "none":
        return None
    card = card_for(model_id)
    if card is not None and card.explanation_chunk_size is not None:
        return card.explanation_chunk_size
    if model_id in GRANDFATHERED_CHUNKED_CLAUDE_MODELS:
        return CLAUDE_EXPLANATION_CHUNK_SIZE
    return None
