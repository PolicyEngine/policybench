"""Declarative per-model serving treatments.

A ModelCard captures everything the harness must know about how one model's
serving stack behaves: which answer contract it can honor, whether whole-
scenario requests converge or need chunking, how long its slowest calls run,
and whether reasoning-by-default token appetite needs the thinking-class
completion budget. None of this is model *configuration* — every model still
runs unconfigured at its provider-default reasoning effort. Cards only
encode serving-stack facts discovered during onboarding (see
``policybench onboard``); a card written before its model's onboarding says
so in its notes.

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

from collections.abc import Iterator
from contextlib import contextmanager
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
    # The model's starting budget, for models whose reasoning tail overflows
    # 16,384: it overrides the thinking-class starting budget on a
    # thinking_budget card and, on a gemini/ card, the Gemini family's
    # 16,384-token starting budget. Requests are still clamped to the
    # escalation ceiling. Headroom is free — only generated tokens bill.
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
    "gpt-6-astra": ModelCard(
        litellm_id="gpt-6-astra",
        answer_contract="tool",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.25,
        notes=(
            "Onboarded 2026-09-04, the day the API opened (announced "
            "2026-09-03 as a limited preview): forced tool contract passed "
            "3/3 (978 completion tokens) and 16/16 whole-scenario (1,171 "
            "tokens) on the Responses API with provider-default reasoning "
            "(effort medium), like GPT-5.6 Sol."
        ),
    ),
    "gpt-6-sol": ModelCard(
        litellm_id="gpt-6-sol",
        answer_contract="tool",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.016,
        notes=(
            "Onboarded 2026-09-22, the day OpenAI announced it: forced tool "
            "contract passed 3/3 (1,761 completion tokens) and 16/16 "
            "whole-scenario (1,141 tokens) on the Responses API with "
            "provider-default reasoning (effort medium), like GPT-6 Astra."
        ),
    ),
    "gpt-6.1-sol": ModelCard(
        litellm_id="gpt-6.1-sol",
        answer_contract="tool",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.021,
        notes=(
            "Onboarded 2026-09-29, the day OpenAI announced it: forced tool "
            "contract passed 3/3 (735 completion tokens) and 16/16 "
            "whole-scenario (1,626 tokens) on the Responses API with "
            "provider-default reasoning (effort medium, per the model page), "
            "like GPT-6 Sol. Probed before its card existed, it got the "
            "384-token non-thinking budget and stopped incomplete."
        ),
    ),
    "gpt-6.1-terra": ModelCard(
        litellm_id="gpt-6.1-terra",
        answer_contract="tool",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.01,
        notes=(
            "Onboarded 2026-10-26, the day OpenAI announced it: forced tool "
            "contract passed 3/3 (881 completion tokens) and 16/16 "
            "whole-scenario (1,414 tokens) on the Responses API with "
            "provider-default reasoning (effort medium, per the model page), "
            "like GPT-6.1 Sol. Probed before its card existed, it got the "
            "384-token non-thinking budget and stopped incomplete. A "
            "two-household smoke parsed all 36 outputs for $0.02, with "
            "reasoning tokens on every request."
        ),
    ),
    # GPT-6.2 Astra. Written 2026-11-17, the day OpenAI released the model,
    # from OpenAI's documentation read that day, and onboarded 2026-11-19: the
    # gauntlet and a two-household smoke ran under this card's request fields
    # (onboarding changed only this comment, the notes and the expected cost).
    # Field by field:
    # - answer_contract "tool": the board's forced answer tool on the
    #   Responses API, which OpenAI's API changelog says tool calling on the
    #   model requires (developers.openai.com/api/docs/changelog). The
    #   gauntlet's tool probes passed, 3/3 (459 completion tokens, 13s) and
    #   16/16 whole-scenario (870 tokens, 17s), each response with status
    #   completed, and the smoke parsed all 36 outputs (16 and 20).
    # - explanation_chunk_size None: 16/16 on the canonical whole-scenario
    #   request (chunking is closed to new models anyway).
    # - thinking_budget True: OpenAI's reasoning guide lists the model as a
    #   reasoning model, its model page says the API rejects reasoning effort
    #   "none" and states no default effort, and reasoning tokens are billed
    #   as output tokens (developers.openai.com/api/docs/guides/reasoning).
    #   The harness sends no reasoning parameter. Under the forced tool the
    #   model reasoned on both smoke requests: 212 of 848 completion tokens
    #   on the first household and 78 of 902 on the second (the gauntlet
    #   report records no reasoning count). The gauntlet used 3% and 5% of
    #   the 16,384-token starting budget and the smoke at most 902 tokens
    #   (6%), with no budget escalation.
    # - request_timeout_seconds None: the thinking class's 300s. The probes
    #   took 13s and 17s and the smoke's households 16s and 15s, far under
    #   the 150s past which the gauntlet suggests a longer timeout.
    # - provider_max_completion_tokens None: the model page lists a maximum
    #   output of 128,000 tokens, the harness's escalation ceiling.
    # - expected_cost_per_scenario_usd 0.057: the cost `policybench onboard`
    #   suggested from the whole-scenario probe, rounded to three places, at
    #   OpenAI's list rates ($8/$40 per 1M, cache writes at $10). The
    #   gauntlet report gives the probe's 870 completion tokens but no prompt
    #   or cache counts. The probe sends the manifest's first scenario, the
    #   request the smoke sent as its first household (2,236 prompt tokens),
    #   and that household read 2,104 tokens from the cache. With 2,236
    #   prompt tokens, 2,104 cache writes and zero cache reads, the probe
    #   would cost $0.056896. The record does not fix those counts: a
    #   three-output probe on the same scenario ran first, the smoke's read
    #   does not show which request wrote the cache, and other write counts
    #   round to the same 0.057 (2,200, for one). With no cache write and no
    #   cache read the probe would round to 0.053. The smoke's two households
    #   cost $0.036 and $0.063: 2,104 of the first's 2,236 prompt tokens were
    #   cache reads, at $0.40 per 1M, and 2,578 of the second's 2,710 were
    #   cache writes, at $10.
    # Both smoke responses name the model as gpt-6.2-astra, the requested
    # name, with no dated snapshot (the Responses API's model field, which the
    # harness records as provider_resolved_model).
    "gpt-6.2-astra": ModelCard(
        litellm_id="gpt-6.2-astra",
        answer_contract="tool",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.057,
        notes=(
            "Onboarded 2026-11-19; OpenAI released the model on 2026-11-17. "
            "Forced tool contract passed 3/3 (459 completion tokens) and 16/16 "
            "whole-scenario (870 tokens) on the Responses API, which OpenAI "
            "says tool calling on this model requires; onboarding estimated "
            "about $0.057 per scenario at OpenAI's list rates. OpenAI lists "
            "it as a reasoning model whose API rejects "
            "reasoning effort none; the model page states no default effort, "
            "and the harness sends no reasoning parameter. A two-household "
            "smoke parsed all 36 outputs for $0.10, with no budget escalation "
            "and reasoning tokens on both requests (212 and 78). Both smoke "
            "responses name the model as gpt-6.2-astra, the requested name, "
            "with no dated snapshot."
        ),
    ),
    # GPT-6.2 Sol. Like the Astra card above, written 2026-11-17 from
    # OpenAI's documentation and onboarded 2026-11-19 under this card's
    # request fields. Field by field:
    # - answer_contract "tool": the board's forced answer tool on the
    #   Responses API, which OpenAI's API changelog says tool calling on the
    #   model requires (developers.openai.com/api/docs/changelog). The
    #   gauntlet's tool probes passed, 3/3 (1,145 completion tokens, 25s) and
    #   16/16 whole-scenario (1,339 tokens, 32s), each response with status
    #   completed, and the smoke parsed all 36 outputs (16 and 20).
    # - explanation_chunk_size None: 16/16 on the canonical whole-scenario
    #   request (chunking is closed to new models anyway).
    # - thinking_budget True: as on the Astra card, OpenAI lists the model as
    #   a reasoning model whose API rejects reasoning effort "none", states
    #   no default effort, and bills reasoning tokens as output tokens
    #   (developers.openai.com/api/docs/guides/reasoning). The harness sends
    #   no reasoning parameter. Under the forced tool the model reasoned on
    #   both smoke requests, more than Astra did: 1,344 of 2,013 completion
    #   tokens on the first household and 547 of 1,377 on the second (the
    #   gauntlet report records no reasoning count). The gauntlet used 7% and
    #   8% of the 16,384-token starting budget and the smoke at most 2,013
    #   tokens (12%), with no budget escalation.
    # - request_timeout_seconds None: the thinking class's 300s. The probes
    #   took 25s and 32s and the smoke's households 43s and 28s, under the
    #   150s past which the gauntlet suggests a longer timeout. A first
    #   gauntlet run the same day stopped on its 3-variable probe with a
    #   litellm.Timeout and no response, after 150s on the gauntlet's clock
    #   (litellm's error cites the 300s timeout); the gauntlet classed it as
    #   an environment error, not a serving fact, and derived no card. The
    #   rerun is the one recorded here.
    # - provider_max_completion_tokens None: the model page lists a maximum
    #   output of 128,000 tokens, the harness's escalation ceiling.
    # - expected_cost_per_scenario_usd 0.019: the cost `policybench onboard`
    #   suggested from the whole-scenario probe, rounded to three places, at
    #   OpenAI's list rates ($2/$10 per 1M, cache writes at $2.50). As on the
    #   Astra card, the gauntlet report gives the probe's 1,339 completion
    #   tokens but no prompt or cache counts, and the smoke's first
    #   household, the same 2,236-token request, read 2,104 tokens from the
    #   cache. With 2,236 prompt tokens, 2,104 cache writes and zero cache
    #   reads, the probe would cost $0.018914. The record does not fix those
    #   counts: a three-output probe on the same scenario ran first, the
    #   smoke's read does not show which request wrote the cache, and other
    #   write counts round to the same 0.019 (2,200, for one). With no cache
    #   write and no cache read the probe would round to 0.018. The smoke's
    #   two households cost $0.021 and $0.020, with the same cache reads
    #   (2,104 tokens) and writes (2,578) as Astra's.
    # Both smoke responses name the model as gpt-6.2-sol, the requested name,
    # with no dated snapshot (provider_resolved_model).
    "gpt-6.2-sol": ModelCard(
        litellm_id="gpt-6.2-sol",
        answer_contract="tool",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.019,
        notes=(
            "Onboarded 2026-11-19; OpenAI released the model on 2026-11-17. "
            "Forced tool contract passed 3/3 (1,145 completion tokens) and "
            "16/16 whole-scenario (1,339 tokens) on the Responses API, which "
            "OpenAI says tool calling on this model requires; onboarding "
            "estimated about $0.019 per scenario at OpenAI's list rates. "
            "OpenAI lists it as a reasoning model whose API rejects "
            "reasoning effort none; the model page states no default effort, "
            "and the harness sends no reasoning parameter. A two-household "
            "smoke parsed all 36 outputs for $0.04, with no budget escalation "
            "and reasoning tokens on both requests (1,344 and 547). Both smoke "
            "responses name the model as gpt-6.2-sol, the requested name, with "
            "no dated snapshot."
        ),
    ),
    "gpt-6-luna": ModelCard(
        litellm_id="gpt-6-luna",
        answer_contract="tool",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.002,
        notes=(
            "Onboarded 2026-09-22, the day OpenAI announced it: forced tool "
            "contract passed 3/3 (2,048 completion tokens) and 16/16 "
            "whole-scenario (2,768 tokens) on the Responses API with "
            "provider-default reasoning (effort medium), like GPT-6 Astra."
        ),
    ),
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
    "claude-fable-5-1": ModelCard(
        litellm_id="claude-fable-5-1",
        answer_contract="json",
        request_timeout_seconds=600,
        thinking_budget=True,
        provider_max_completion_tokens=128_000,
        expected_cost_per_scenario_usd=0.27,
        notes=(
            "Onboarded 2026-09-01 (release day). The API rejects forced "
            "tool use on this model with a 400 (tool_choice type tool/any "
            "'not supported for this model'): adaptive thinking is always "
            "on and a forced call would skip it, per the model docs. So it "
            "runs the JSON contract like Kimi K3 and Qwen 3.8 Max, "
            "whole-scenario: 3/3 and 16/16 parsed in the gauntlet (4,028 "
            "and 4,799 completion tokens, 46s and 56s). Unlike Fable 5's "
            "forced-tool board row, this row reasons. The JSON contract "
            "has no batch translation, so it runs on the sync path. Cost "
            "estimated from the full-scenario probe at $10/$50 per 1M; the "
            "100-scenario run cost $25.70 (median 49s per household, "
            "1,984/1,984 parsed, no budget escalations)."
        ),
    ),
    "claude-fable-5-2": ModelCard(
        litellm_id="claude-fable-5-2",
        answer_contract="json",
        request_timeout_seconds=600,
        thinking_budget=True,
        provider_max_completion_tokens=128_000,
        expected_cost_per_scenario_usd=0.143,
        notes=(
            "Onboarded 2026-11-09, release day (the Models API lists the id "
            "with created_at 2026-11-09). The API rejects forced tool use on "
            "this model with a 400 (tool_choice type tool/any 'not supported "
            "for this model'), as on Fable 5.1, and adaptive thinking is "
            "always on, per the model docs, so the row reasons at the "
            "provider default and runs the JSON contract whole-scenario on "
            "the sync path. The API's default effort is high, as on Fable "
            "5.1 and Sonnet 5.5, where Opus 5.5's and Haiku 5.5's is medium "
            "(platform.claude.com effort docs, read 2026-11-09). With no "
            "thinking parameter, the board's prompt for the first household, "
            "sent directly through Anthropic's SDK, drew a thinking block "
            "(1,789 of 2,881 output tokens), though a one-question probe "
            "drew none. Gauntlet: 3/3 and 16/16 parsed (1,563 and 3,219 "
            "completion tokens, 16s and 30s); the gauntlet's cost estimate "
            "is $0.143 per scenario at $8/$40 per 1M. The timeout is 600s, "
            "as on the other Claude JSON-contract rows (Fable 5.1, Opus 5.5, "
            "Sonnet 5.5); the gauntlet's slowest probe took 30s, under its "
            "own 150s trigger, so it suggested the 300s class default."
        ),
    ),
    "claude-opus-5-5": ModelCard(
        litellm_id="claude-opus-5-5",
        answer_contract="json",
        request_timeout_seconds=600,
        thinking_budget=True,
        provider_max_completion_tokens=128_000,
        expected_cost_per_scenario_usd=0.057,
        notes=(
            "Onboarded 2026-09-22 (the Models API lists the id with "
            "created_at 2026-09-21). The API rejects forced tool use on this "
            "model with a 400 (tool_choice type tool/any 'not supported for "
            "this model'), as on Fable 5.1, and a request with no thinking "
            "parameter returns a thinking block (87 thinking tokens on a "
            "one-question probe), so the row reasons at the provider "
            "default and runs the JSON contract whole-scenario on the sync "
            "path (the batch adapter supports the forced tool contract "
            "only). Gauntlet: 3/3 and 16/16 parsed (1,664 and 2,489 "
            "completion tokens, 15s and 21s); the gauntlet's cost estimate "
            "is $0.057 per scenario at $4/$20 per 1M with $0.20 cache reads."
        ),
    ),
    # Every field below comes from the 2026-09-28 onboarding record in
    # results/local/adds202609/sonnet55/ (sonnet55_onboard.json, the
    # thinking-default probe, and the Models API entry):
    # - answer_contract "json": forced tool use returns a 400, so the
    #   forced-tool board request cannot be sent; the JSON contract passed.
    # - explanation_chunk_size None: 16/16 on the canonical whole-scenario
    #   request (chunking is closed to new models anyway).
    # - thinking_budget True: a request with no thinking parameter returns a
    #   thinking block, so the row reasons at the API default (adaptive
    #   thinking, effort high) and thinking bills against the answer budget.
    # - request_timeout_seconds 600: the value the other JSON-contract
    #   thinking rows (Fable 5.1, Opus 5.5) carry; the slowest probe took 17s,
    #   under the gauntlet's own 150s trigger for a longer timeout.
    # - provider_max_completion_tokens 128_000: the Models API max_tokens.
    # - expected_cost_per_scenario_usd 0.027: the gauntlet's full-scenario
    #   probe at $2/$10 per 1M.
    "claude-sonnet-5-5": ModelCard(
        litellm_id="claude-sonnet-5-5",
        answer_contract="json",
        request_timeout_seconds=600,
        thinking_budget=True,
        provider_max_completion_tokens=128_000,
        expected_cost_per_scenario_usd=0.027,
        notes=(
            "Onboarded 2026-09-28, release day (the Models API lists the id "
            "with created_at 2026-09-28). The API rejects forced tool use on "
            "this model with a 400 (tool_choice type tool/any 'not supported "
            "for this model'), as on Opus 5.5 and Fable 5.1, and a request "
            "with no thinking parameter returns a thinking block (108 of 115 "
            "output tokens on a one-question probe), so the row reasons at "
            "the provider default (adaptive thinking, effort high) and runs "
            "the JSON contract whole-scenario on the sync path (the batch "
            "adapter supports the forced tool contract only). Gauntlet: 3/3 "
            "and 16/16 parsed (1,523 and 2,389 completion tokens, 11s and "
            "17s); the gauntlet's cost estimate is $0.027 per scenario at "
            "$2/$10 per 1M with $0.20 cache reads."
        ),
    ),
    # Every field below comes from the 2026-10-08 onboarding record in
    # results/local/haiku55/ (haiku55_onboard.md, the thinking-default and
    # forced-tool probes, and the Models API entry):
    # - answer_contract "tool": unlike Sonnet 5.5 and Opus 5.5, the API
    #   accepts forced tool use on this model, so the row takes the board's
    #   forced answer tool. Anthropic models skip thinking under a forced
    #   tool (eval_no_tools._tool_choice_for), and the forced-tool probe
    #   returned no thinking block, so the row answers without extended
    #   thinking, as Claude Opus 5's does.
    # - explanation_chunk_size None: 16/16 on the canonical whole-scenario
    #   request (chunking is closed to new models anyway).
    # - thinking_budget True: a request with no thinking parameter returns a
    #   thinking block, so the row is in the thinking-default class (16,384
    #   tokens, the class's 300s timeout).
    # - request_timeout_seconds None: the class default; the slowest probe
    #   took 4s, under the gauntlet's own 150s trigger for a longer timeout.
    # - provider_max_completion_tokens 128_000: the Models API max_tokens.
    # - expected_cost_per_scenario_usd 0.001: the gauntlet's full-scenario
    #   probe at $0.10/$0.50 per 1M.
    "claude-haiku-5-5": ModelCard(
        litellm_id="claude-haiku-5-5",
        answer_contract="tool",
        thinking_budget=True,
        provider_max_completion_tokens=128_000,
        expected_cost_per_scenario_usd=0.001,
        notes=(
            "Onboarded 2026-10-08, the day after release (the Models API "
            "lists the id with created_at 2026-10-07). A request with no "
            "thinking parameter returns a thinking block (119 of 123 output "
            "tokens on a one-question probe), but unlike Sonnet 5.5 and Opus "
            "5.5 the API accepts forced tool use on this model, and the "
            "forced-tool probe returned no thinking block. The row therefore "
            "takes the board's forced answer tool, under which it answers "
            "without extended thinking, as Claude Opus 5's row does. "
            "Gauntlet: 3/3 and 16/16 parsed on the tool contract (355 and "
            "1,004 completion tokens, 2s and 4s); the gauntlet's cost "
            "estimate is $0.001 per scenario at $0.10/$0.50 per 1M with "
            "$0.01 cache reads."
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
    "xai/grok-4.6": ModelCard(
        litellm_id="xai/grok-4.6",
        answer_contract="tool",
        request_timeout_seconds=600,
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.07,
        notes=(
            "Onboarded 2026-08-20: forced tool contract passed 3/3 and "
            "16/16 whole-scenario. Heavy reasoner — the 3-variable probe "
            "spent 26,260 tokens over 391s, so the timeout is 600s and the "
            "thinking-class budget applies. Released 2026-08-12 at $2/$6 "
            "per 1M (litellm map). The 100-scenario run cost $8.70."
        ),
    ),
    "xai/grok-4.7": ModelCard(
        litellm_id="xai/grok-4.7",
        answer_contract="tool",
        request_timeout_seconds=1800,
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.2,
        notes=(
            "Onboarded 2026-09-28: forced tool contract passed 3/3 (247s, "
            "19,125 tokens) and 16/16 whole-scenario (472s, 32,960 tokens). "
            "A first attempt with a 600s timeout passed 3/3 in 454s (39,192 "
            "tokens) and then timed out on the whole-scenario probe, so "
            "latency sits near 600s and the timeout is 1800s. Heavier than "
            "Grok 4.6 (26,260 tokens on the 3-variable probe); at $2/$6 per "
            "1M the gauntlet estimates $0.20 per scenario."
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
    "deepseek/deepseek-flash": ModelCard(
        litellm_id="deepseek/deepseek-flash",
        answer_contract="json",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.017,
        notes=(
            "Onboarded 2026-09-28 as DeepSeek V4.1 Flash (the deepseek-flash "
            "name). The forced tool contract is rejected in thinking mode "
            "('Thinking mode does not support this tool_choice'), as for the "
            "V4 rows; the JSON contract passed 3/3 (80s, 19,313 tokens) and "
            "16/16 whole-scenario (56s, 13,789 tokens). Thinking stays at "
            "the provider default (on). Priced at the peak list rate."
        ),
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
    "gemini/gemini-3.8-flash": ModelCard(
        litellm_id="gemini/gemini-3.8-flash",
        answer_contract="tool",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.015,
        notes=(
            "Onboarded 2026-09-03 (released 2026-09-02): forced tool contract "
            "passed 3/3 and 16/16 whole-scenario (3,409 completion tokens). "
            "Introductory pricing $0.75/$3.75 per 1M through 2026-12-31."
        ),
    ),
    "gemini/gemini-3.5-flash-lite": ModelCard(
        litellm_id="gemini/gemini-3.5-flash-lite",
        answer_contract="tool",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.004,
        notes=(
            "Onboarded 2026-09-03: forced tool contract passed 3/3 and 16/16 "
            "whole-scenario (622 completion tokens)."
        ),
    ),
    # Every field below comes from the 2026-10-13 onboarding record in
    # ~/reviews/policybench-gemini-4-argon/{probes,onboard,smoke,board-run}
    # (the reasoning probes, the output-limit probe, the gauntlet report, the
    # two-scenario smoke, and the forced and tool_choice auto 100-household
    # runs' comparison):
    # - answer_contract "tool": the Gemini API accepts a forced function call
    #   on this model (litellm sends mode ANY with allowed_function_names),
    #   and the gauntlet passed on it, so the row takes the board's forced
    #   answer tool, as Gemini 3.6, 3.7 and 3.8 Flash do.
    # - explanation_chunk_size None: 16/16 on the canonical whole-scenario
    #   request (chunking is closed to new models anyway).
    # - thinking_budget True: the model reasons by default (Google's guide
    #   gives a default thinking_level of medium), so it is in the
    #   thinking-default class and takes that class's 300s timeout. The
    #   16,384-token starting budget is the Gemini family's.
    # - request_timeout_seconds None: the class default; the slowest of 87
    #   harness-path probe calls took 41s, and the slowest board household
    #   took 53s in the first board run and 47s in the second.
    # - provider_max_completion_tokens 32_768. Google's pages disagree: the
    #   Gemini 4 Argon guide for generateContent says "One non-streaming
    #   request returns up to 32,768 tokens" (64K per stream), and the
    #   Models API's outputTokenLimit is 32,768 (models-get-gemini-4-argon
    #   .json in the onboarding record, read 2026-10-13); the model page
    #   lists 65,536 as "default synchronous". litellm makes one
    #   non-streaming REST request, so the card follows the guide; 32,768 is
    #   the safe value either way.
    # - expected_cost_per_scenario_usd 0.032: the gauntlet's full-scenario
    #   probe at $2/$10 per 1M.
    "gemini/gemini-4-argon": ModelCard(
        litellm_id="gemini/gemini-4-argon",
        answer_contract="tool",
        thinking_budget=True,
        provider_max_completion_tokens=32_768,
        expected_cost_per_scenario_usd=0.032,
        notes=(
            "Onboarded 2026-10-13, the day Google opened the model to the "
            "public (the Gemini API changelog lists gemini-4-argon as "
            "generally available that day; the 2026-09-30 launch was limited "
            "to Fairwind Program cyber partners). The Gemini API accepts a "
            "forced function call on this model, so the row takes the "
            "board's forced answer tool: the gauntlet, run with no card, "
            "passed 3/3 (442 completion tokens, 5s) and 16/16 whole-scenario "
            "(2,619 tokens, 24s) on the tool contract, about $0.032 per "
            "scenario at $2/$10 per 1M. The harness sends no thinkingConfig, "
            "and Google's guide gives a default thinking_level of medium. "
            "The model decides call by call whether to think. A forced tool "
            "does not switch its reasoning off, and no statistically "
            "significant reduction in how often it reasons was detected. Over "
            "the 100 board households a first forced-tool board run returned "
            "reasoning tokens on 80 and a tool_choice auto run on 82 (Fisher "
            "exact p = 0.86; 70 households reasoned in both runs, 10 only "
            "when forced, 12 only under auto, 8 in neither), so the row has no "
            "tool_choice auto sensitivity run; the second board run, below, "
            "reasoned on 85. Earlier probes agree: on the "
            "board's own request for 13 households (29 calls a shape) the "
            "forced tool returned reasoning tokens on 20 calls, auto on 25 and "
            "the JSON contract on 22 (forced against auto, p = 0.21), and all "
            "87 calls parsed every output; on a one-question probe (10 calls a "
            "shape) it returned thought tokens on 6 forced calls, 7 auto, 5 "
            "with mode ANY and no named function, and none with no tools or "
            "with a JSON response type. The first board run answered all 100 "
            "households in one request each, 1,984/1,984 parsed, with no "
            "budget escalation, for $2.77 (a median of 20s and about 2,030 "
            "completion tokens per household, at most 6,374 against the "
            "16,384-token starting budget). It ran with a 65,536-token "
            "escalation ceiling, the model page's figure, but Google's "
            "generateContent guide and the Models API give 32,768 for one "
            "non-streaming request, which is what the harness sends, so the "
            "board row is a second run on this card: all 100 households in one "
            "request each, 1,984/1,984 parsed, no budget escalation, $2.79, "
            "reasoning tokens on 85 households (a median of 22s and about "
            "1,990 completion tokens per household, at most 47s and 4,872). "
            "Requests asking for up to 131,072 tokens returned 200, which "
            "shows only that the parameter is accepted."
        ),
    ),
    # Gemini 4 Carbon. Every field below comes from the 2026-11-14 onboarding
    # record in ~/reviews/policybench-gemini-4-carbon/{probes,onboard,smoke}
    # (a raw generateContent probe, a one-question reasoning probe of 10 calls
    # a shape, the gauntlet report, run with no card from a checkout of
    # origin/main, and a 2-household smoke run on this card; the gauntlet's
    # exact token counts are in onboard/carbon/usage-rows.jsonl) and from
    # Google's pages:
    # - answer_contract "json". The gauntlet's 3-variable probe sent the
    #   board's forced answer tool (litellm sends mode ANY with
    #   allowed_function_names), and the API accepted the forced call, but the
    #   model reasoned until the 16,384-token budget ran out: 16,384
    #   completion tokens, 16,381 of them reasoning, finish=length, 0 of 3
    #   outputs parsed, 203s. The gauntlet sends each probe once, with no
    #   budget escalation, so the tool request ran at half the
    #   max_output_tokens Google's Gemini 4 Carbon guide recommends: "at
    #   least 32,768, since Gemini 4 Carbon can spend more of the limit on
    #   thinking" (aistudio.google.com/docs/whats-new-gemini-4-carbon, read
    #   2026-11-13). The gauntlet then passed on the JSON contract, 3/3
    #   (9,964 completion tokens, 105s) and 16/16 whole-scenario (7,257
    #   tokens, 79s), and suggested "json". The onboarding procedure, written
    #   before the runs, makes the card JSON when the tool probe fails, and the
    #   tool contract was not re-tested: re-running the gauntlet until the tool
    #   probe passes would choose the contract on a retry. So the request
    #   declares no tool and asks for a JSON object, as the older Gemini rows'
    #   requests do by the family default.
    # - explanation_chunk_size None: 16/16 on the canonical whole-scenario
    #   request (chunking is closed to new models anyway).
    # - thinking_budget True: the model reasons by default. Google's thinking
    #   guide lists its default as "On (medium)", with levels low, medium and
    #   high (aistudio.google.com/docs/generate-content/thinking, read
    #   2026-11-13), and all 51 raw generateContent responses in the record
    #   carry thought tokens. The 16,384-token starting budget is not the
    #   card's: the harness gives every gemini/ id 16,384
    #   (GEMINI_JSON_MAX_COMPLETION_TOKENS). The gauntlet used all of it on the
    #   forced-tool probe, 61% on the 3-variable JSON probe and 44% on the
    #   whole-scenario JSON probe (22% of the 32,768-token ceiling).
    # - request_timeout_seconds 900. Google's Gemini 4 Carbon guide says hard
    #   prompts "can take several minutes" and recommends HTTP client
    #   timeouts of "at least 15 minutes"
    #   (aistudio.google.com/docs/whats-new-gemini-4-carbon, read 2026-11-13).
    #   The gauntlet's probes ran at about 80 to 95 completion tokens a
    #   second, so a first request at the 16,384-token budget takes about 170
    #   to 205s and a retry at the 32,768-token ceiling about 345 to 410s,
    #   past the thinking class's 300s. The one-question probe ran slower on
    #   15 of its 50 calls, down to 53 tokens a second, where a request at
    #   the ceiling would take about 620s. Google's generateContent
    #   long-decode guide says the server closes a non-streaming connection
    #   after 10 minutes and recommends a 20-minute client read timeout, and
    #   its option table gives 20 minutes per request for a non-streaming
    #   loop (aistudio.google.com/docs/long-decode?generate-content=true,
    #   read 2026-11-14). If the server closes at 10 minutes, no request on
    #   this row runs past 600s, so a request at the ceiling would not finish
    #   at that slowest rate, and the timeout's last 300s never apply. If
    #   the table's 20 minutes applies instead, 900s still exceeds the about
    #   345 to 410s the gauntlet's rates predict for a request at the
    #   ceiling, and the 620s the slowest probe rate predicts. The harness
    #   can double the request budget once, from 16,384 to the ceiling
    #   below. If a length-truncated response at that ceiling leaves outputs
    #   missing, the harness records those outputs as
    #   budget_exhausted_at_ceiling. The ceiling bounds each response, so a
    #   household's requests can total more than 32,768 completion tokens:
    #   the harness keeps the values a truncated response returned and asks
    #   again for the outputs still missing.
    # - provider_max_completion_tokens 32_768: the Models API's
    #   outputTokenLimit for the model, whose entry lists generateContent
    #   among its supported methods (models.get on
    #   generativelanguage.googleapis.com/v1beta/models/gemini-4-carbon, read
    #   2026-11-13). Google's generateContent long-decode guide gives the same
    #   cap for the request the harness sends, one direct non-streaming REST
    #   generateContent call: such calls on gemini-4-carbon "Default to 32K
    #   (32,768) output tokens", and a larger max_output_tokens without a
    #   continuation_token returns a 400 error
    #   (aistudio.google.com/docs/long-decode?generate-content=true, read
    #   2026-11-14). The model page lists 65,536 as "default synchronous",
    #   which that guide gives for streaming and SDK calls.
    # - expected_cost_per_scenario_usd 0.075: the gauntlet's whole-scenario
    #   probe, 1,271 prompt and 7,257 completion tokens, $0.075112 at $2/$10
    #   per 1M, Google's rate through 2026-11-30. The smoke's two households
    #   cost $0.100 and $0.081 with no escalation.
    "gemini/gemini-4-carbon": ModelCard(
        litellm_id="gemini/gemini-4-carbon",
        answer_contract="json",
        request_timeout_seconds=900,
        thinking_budget=True,
        provider_max_completion_tokens=32_768,
        expected_cost_per_scenario_usd=0.075,
        notes=(
            "Onboarded 2026-11-14. Google opened the model to the public on "
            "2026-11-10 (the Gemini API changelog lists gemini-4-carbon as "
            "generally available that day; an earlier release went to "
            "cybersecurity defenders through its Fairwind Program). The row "
            "answers on the JSON contract. The gauntlet, run with no card, "
            "sent the board's forced answer tool first, and the Gemini API "
            "accepted the forced call, but on the 3-variable probe the model "
            "reasoned until the 16,384-token budget ran out (16,381 reasoning "
            "tokens, 0 of 3 outputs parsed, 203s). The gauntlet sends each "
            "probe once, with no budget escalation, so the tool request ran "
            "at 16,384 tokens, half the minimum that Google's Gemini 4 Carbon "
            "guide recommends for this model. The gauntlet then passed "
            "on the JSON contract, 3/3 (9,964 completion tokens, 105s) and "
            "16/16 whole-scenario (7,257 tokens, 79s), about $0.075 per "
            "scenario at $2/$10 per 1M; the tool contract was not re-tested. "
            "Gemini 4 Argon's rule, a tool_choice auto sensitivity run only "
            "if forcing the tool suppresses reasoning, applies only to a row "
            "that answers through the forced tool, so this row has no such "
            "run. The harness sends no thinkingConfig, and Google's thinking "
            "guide lists the model's default as On (medium). Unlike Argon, "
            "the model reasoned on every call of a one-question "
            "generateContent probe (10 calls a shape): thought tokens on all "
            "50 calls, under a forced function call, tool_choice auto, mode "
            "ANY with no named function, a JSON response type and no tools "
            "(Argon on the same probe: 6 forced, 7 auto, 5 with mode ANY and "
            "no named function, and none with a JSON response type or no "
            "tools). On that one-question request, unlike the gauntlet's, "
            "the forced calls returned a function call 10 times out of 10, "
            "with a median of about 2,515 thought tokens against about 2,988 "
            "under auto. "
            "generateContent reports the count as "
            "usageMetadata.thoughtsTokenCount (on all 51 raw responses), "
            "litellm 1.95.0 maps it to reasoning_tokens and counts it inside "
            "completion_tokens, and the harness records it as each row's "
            "reasoning_tokens (16,381, 9,318 and 6,056 on the three gauntlet "
            "calls). Every response names the model as gemini-4-carbon, the "
            "requested name, with no dated snapshot (modelVersion on the 51 "
            "raw responses). The Models API gives an outputTokenLimit of "
            "32,768, and Google's generateContent long-decode guide gives the "
            "same 32,768 tokens for one direct non-streaming REST call, which "
            "is what the harness sends; the model page lists 65,536 as the "
            "default synchronous output, which the guide gives for streaming "
            "and SDK calls. The card sets a 900s timeout: Google's Gemini 4 Carbon "
            "guide recommends client timeouts of at least 15 minutes, and a "
            "retry at the 32,768-token ceiling takes about 345 to 410s at the "
            "gauntlet's 80 to 95 completion tokens a second. Google's "
            "generateContent long-decode guide says the server closes a "
            "non-streaming call after 10 minutes, which would end a request "
            "at 600s. The same guide recommends a 20-minute client read "
            "timeout, and its option table gives 20 minutes per request. The "
            "harness can double the request budget once, from 16,384 to "
            "32,768 tokens. If a length-truncated response at that ceiling "
            "leaves outputs missing, the harness records those outputs as "
            "budget_exhausted_at_ceiling. Google lists $2/$10 per 1M through "
            "2026-11-30 and $4/$20 from 2026-12-01."
        ),
    ),
    # Gemini 4 Hydrogen. Every field below comes from the 2026-11-14
    # onboarding record in
    # ~/reviews/policybench-gemini-4-carbon/{probes,onboard,smoke}
    # (a raw generateContent probe, a one-question reasoning probe of 10 calls
    # a shape, the gauntlet report, run with no card from a checkout of
    # origin/main, a harness-path probe of the board's own request, 16
    # calls a shape, run from an export of this card's branch before its
    # rebase onto main, with the same request code, and a 2-household smoke
    # run on this card) and from Google's pages:
    # - answer_contract "tool": the Gemini API accepts a forced function call
    #   on this model (litellm sends mode ANY with allowed_function_names),
    #   and the gauntlet passed on it, 3/3 (10,956 completion tokens, 48s) and
    #   16/16 whole-scenario (11,947 tokens, 51s), finish=tool_calls, so the
    #   row takes the board's forced answer tool, as every Gemini card from
    #   Gemini 3.6 Flash on does except Gemini 4 Carbon's.
    # - explanation_chunk_size None: 16/16 on the canonical whole-scenario
    #   request (chunking is closed to new models anyway).
    # - thinking_budget True: the model reasons by default. Google's thinking
    #   guide lists its default as "On (high)", with levels low, medium, high
    #   and xhigh (aistudio.google.com/docs/generate-content/thinking, read
    #   2026-11-13), and all 51 raw generateContent responses in the record
    #   carry thought tokens. The harness sends no thinkingConfig, so this
    #   model's default is high where Carbon's and Argon's is medium. The
    #   16,384-token starting budget is not the card's: the harness gives every
    #   gemini/ id 16,384 (GEMINI_JSON_MAX_COMPLETION_TOKENS). The gauntlet
    #   used 67% of it on the 3-variable probe and 73% on the whole-scenario
    #   probe (18% of the 65,536-token ceiling).
    # - request_timeout_seconds 600. At the gauntlet's 228 to 234 completion
    #   tokens a second, a request at the 65,536-token ceiling (the second
    #   budget escalation) takes about 280 to 290s, and at the slowest rates
    #   in the record (about 215 to 220 a second, in the one-question probe,
    #   the harness-path probe and the smoke) about 300s, the thinking
    #   class's timeout. Google's generateContent long-decode guide says the
    #   server closes a non-streaming connection after 10 minutes and
    #   recommends a 20-minute client read timeout, and its option table
    #   gives 20 minutes per request
    #   (aistudio.google.com/docs/long-decode?generate-content=true, read
    #   2026-11-14). If the server closes at 10 minutes, a client timeout
    #   above 600s could not help this request. If the table's 20 minutes
    #   applies instead, 600s still exceeds the about 300s the record's
    #   slowest rates predict for a request at the ceiling.
    # - provider_max_completion_tokens 65_536: the Models API's
    #   outputTokenLimit for the model, whose entry lists generateContent
    #   among its supported methods (models.get on
    #   generativelanguage.googleapis.com/v1beta/models/gemini-4-hydrogen, read
    #   2026-11-13). Google's generateContent long-decode guide gives the same
    #   cap for every call on this model: "all gemini-4-hydrogen calls"
    #   default to 64K (65,536) output tokens, streaming and non-streaming
    #   (aistudio.google.com/docs/long-decode?generate-content=true, read
    #   2026-11-14).
    # - expected_cost_per_scenario_usd 0.094: the gauntlet's whole-scenario
    #   probe, 2,762 prompt and 11,947 completion tokens, $0.0937455 at
    #   $1.50/$7.50 per 1M. The gauntlet report gives the cost to three places
    #   and no prompt count; the 2,762 is the prompt count Google returned for
    #   the harness-path probe's forced call on scenario 0, the same request
    #   (the same messages, answer tool and 16,384-token budget). The rest of
    #   the record runs higher: the smoke's two households cost $0.117 and
    #   $0.109 with no escalation, and 6 of the harness-path probe's 16
    #   forced calls ran out of the starting budget, where the board doubles
    #   the budget and asks again.
    "gemini/gemini-4-hydrogen": ModelCard(
        litellm_id="gemini/gemini-4-hydrogen",
        answer_contract="tool",
        request_timeout_seconds=600,
        thinking_budget=True,
        provider_max_completion_tokens=65_536,
        expected_cost_per_scenario_usd=0.094,
        notes=(
            "Onboarded 2026-11-14. The Gemini API changelog lists "
            "gemini-4-hydrogen as generally available on 2026-11-12, on the "
            "free and the paid tier. The Gemini API accepts a forced function "
            "call on this model, so the row takes the board's forced answer "
            "tool: the gauntlet, run with no card, passed 3/3 (10,956 "
            "completion tokens, 48s) and 16/16 whole-scenario (11,947 tokens, "
            "51s) on the tool contract, about $0.094 per scenario at "
            "$1.50/$7.50 per 1M. The harness sends no thinkingConfig, and "
            "Google's thinking guide lists the model's default as On (high), "
            "where Gemini 4 Carbon's and Argon's is medium. Unlike Argon, the "
            "model reasoned on every call of a one-question generateContent "
            "probe (10 calls a shape): thought tokens on all 50 calls, under "
            "a forced function call, tool_choice auto, mode ANY with no named "
            "function, a JSON response type and no tools, with a median of "
            "5,273 thought tokens forced against about 5,496 under auto, and the "
            "forced calls returned a function call 10 times out of 10. "
            "On the board's own request for the frozen manifest's first 16 "
            "scenarios (16 calls a shape, under a rule fixed before the first "
            "call), the forced tool returned reasoning tokens on 16 of 16 "
            "calls, tool_choice auto on 16 of 16 and the JSON contract on 16 "
            "of 16 (forced against auto, two-sided Fisher exact p = 1.0), so "
            "forcing the tool did not lower how often the model reasoned, and "
            "the row has no tool_choice auto sensitivity run (Gemini 4 Argon's "
            "rule adds one only if forcing the tool suppresses reasoning). "
            "That probe sent each request once, with no budget escalation: 6 "
            "forced, 6 auto and 2 JSON calls ran out of the 16,384-token "
            "budget (finish=length, 14,869 to 16,381 reasoning tokens each), "
            "the forced and auto calls on the same six scenarios, so 184 of "
            "334 outputs parsed under each tool mode and 262 under JSON; on "
            "such a call "
            "the board doubles the budget, up to the 65,536-token ceiling, "
            "and asks again. "
            "generateContent reports the thought-token count as "
            "usageMetadata.thoughtsTokenCount (on all 51 raw responses), and "
            "litellm 1.95.0 maps it to reasoning_tokens and counts it inside "
            "completion_tokens (checked on the saved responses), which the "
            "harness records as each row's reasoning_tokens. Every response "
            "names the model as gemini-4-hydrogen, the requested name, with "
            "no dated snapshot (modelVersion on the 51 raw responses). The "
            "Models API gives an outputTokenLimit of 65,536, and Google's "
            "generateContent long-decode guide gives the same 65,536 tokens "
            "for every call on this model, streaming or not. The gauntlet "
            "used 67% and 73% of the 16,384-token starting budget. The "
            "card sets a 600s timeout: a request at the 65,536-token ceiling takes "
            "about 280 to 290s at the gauntlet's 228 to 234 completion tokens "
            "a second, close to the thinking class's 300s. Google's "
            "generateContent long-decode guide says the server closes a "
            "non-streaming call after 10 minutes. The same guide recommends "
            "a 20-minute client read timeout, and its option table gives 20 "
            "minutes per request. Google lists $1.50/$7.50 per 1M."
        ),
    ),
    # Gemini 4 Neon. This card was written from Google's documentation, read
    # 2026-11-19, the day after Google released the model, and from the Gemini
    # 4 Hydrogen card above, whose default thinking level, high, it shares.
    # The same day the onboarding gauntlet ran under this card, then with the
    # thinking class's 300s timeout; two raw generateContent calls with no
    # tools asked the model one plain tax question; and a two-household smoke
    # ran on the board's request, then with the Gemini family's 16,384-token
    # starting budget. After the smoke the card's starting budget moved to the
    # 65,536-token ceiling (completion_token_cap below); a smoke at that
    # starting budget is to come. Field by field:
    # - answer_contract "tool": Hydrogen's contract, the board's forced answer
    #   tool, which litellm sends as mode ANY with allowed_function_names.
    #   Google's model page lists function calling as supported
    #   (aistudio.google.com/docs/models/gemini-4-neon), and the API
    #   reference's FunctionCallingConfig describes mode ANY for every model,
    #   naming no exception (aistudio.google.com/api-reference/caching). The
    #   gauntlet settled nothing between the contracts. The API accepted the
    #   forced call, but on the 3-variable tool probe the model reasoned until
    #   the 16,384-token budget ran out: 16,384 completion tokens, 16,381 of
    #   them reasoning, finish=length, 0 of 3 outputs parsed, 127s. The
    #   3-variable JSON probe ended the same way: 16,384 and 16,381,
    #   finish=length, 0 of 3, 129s. The gauntlet sends each probe once at
    #   that budget, with no budget escalation, so it found neither contract
    #   answering, reported the model "not scorable" at that budget, did not
    #   reach its whole-scenario probe and derived no card. Gemini 4 Carbon's
    #   card took JSON because its JSON probes passed after its tool probe ran
    #   out of budget; here both ran out, so the card kept the tool contract.
    #   The smoke settled it: on the board's request, which doubles the budget
    #   on a length finish, both households answered every output through the
    #   forced tool once the budget allowed, 16 of 16 and 20 of 20, values
    #   and explanations, so the contract stays.
    # - explanation_chunk_size None: the canonical whole-scenario request
    #   (chunking is closed to new models).
    # - thinking_budget True: the model reasons by default. Google's thinking
    #   guide lists its default as "On (high)", with levels low, medium, high
    #   and xhigh, and lists "minimal" as not supported on Gemini 4 models
    #   (aistudio.google.com/docs/thinking); no page read says thinking can be
    #   turned off. The harness sends no thinkingConfig. Google's pricing
    #   page bills thinking tokens as output
    #   ("Output price (including thinking tokens)",
    #   aistudio.google.com/docs/pricing). The model reasoned on every call in
    #   the record. The harness recorded 16,381 reasoning tokens on each
    #   gauntlet probe, inside 16,384 completion tokens (the other 3 text),
    #   so litellm 1.95.0 counts reasoning inside completion_tokens and the
    #   output rate prices it. The two raw calls, one direct REST
    #   generateContent request each with no tools, asked for a single filer's
    #   federal income tax before refundable credits, and generateContent
    #   reported usageMetadata.thoughtsTokenCount on both: 7,575 thought
    #   tokens and 355 answer tokens (candidatesTokenCount) with no
    #   thinkingConfig (the default, high), and 1,370 and 350 with
    #   thinkingLevel low. These are facts about the model; the board sends
    #   no thinkingConfig, so low is not a treatment it uses. The smoke's four
    #   requests reported reasoning tokens too, from 13,431 to 32,765 each.
    # - completion_token_cap 65_536: the starting budget, at the escalation
    #   ceiling, set after the smoke. The smoke ran at the Gemini family's
    #   16,384-token starting budget (GEMINI_JSON_MAX_COMPLETION_TOKENS),
    #   which the board's request doubles on a length finish to 32,768 and
    #   then 65,536. The 20-output household answered on its first request:
    #   14,984 completion tokens, 13,431 of them reasoning, 110s. The
    #   16-output household's first request used the whole 16,384-token
    #   budget (16,381 reasoning tokens, 128s) and its second the whole 32,768
    #   (32,765 reasoning tokens, 247s), both finish=length with no outputs;
    #   its third, at 65,536, answered with 24,444 completion tokens (23,115
    #   reasoning) in 187s. A request that runs out is billed in full and its
    #   output discarded: 49,152 of the smoke's 88,580 completion tokens, an
    #   estimated $0.75 of the smoke's $1.36 at Google's list rates (the
    #   households $1.12 and $0.23). Starting at the ceiling leaves no lower
    #   rung to bill and discard. A request at the ceiling that ends at length
    #   with outputs missing has no rung left: the harness records those
    #   outputs as budget_exhausted_at_ceiling and asks for them no more. The
    #   record does not show whether the model reasons longer when given a
    #   larger first budget; the smoke at this starting budget will show it
    #   for the same two households.
    # - request_timeout_seconds 600, set from the measured output rate as on
    #   Hydrogen's card. The gauntlet's probes ran at about 129 and 127
    #   completion tokens a second (16,384 tokens in 127s and 129s), the raw
    #   call at the default level at about 138 (7,930 thought and answer
    #   tokens in 57s), and the smoke's four requests at 128 to 136, the
    #   32,768-token one at 132, so the record shows no slowdown with length
    #   up to 32,768 tokens. Every request now asks for the 65,536-token
    #   ceiling. At 127 to 138 tokens a second one that used all of it would
    #   take about 475 to 516s, past the thinking class's 300s. No request in
    #   the record used the whole ceiling (the smoke's request at 65,536
    #   stopped at 24,444 tokens), so that is a constant-rate prediction.
    #   Google's generateContent long-decode guide, read
    #   2026-11-14 for the Carbon and Hydrogen cards above and not re-read for
    #   this one, says the server closes a non-streaming connection after 10
    #   minutes and recommends a 20-minute client read timeout, and its option
    #   table gives 20 minutes per request
    #   (aistudio.google.com/docs/long-decode?generate-content=true).
    #   If the server closes at 10 minutes, a client timeout above 600s could
    #   not help this request, which litellm sends as one non-streaming
    #   request, with no long-decode continuation. If the table's 20 minutes
    #   applies instead, 600s still exceeds the about 475 to 516s that those
    #   rates predict for a request at the ceiling. This departs from
    #   Hydrogen's test, under which 600s exceeds what the slowest rates in
    #   its record predict: the slowest rate here, the raw call at level low
    #   (1,720 thought and answer tokens in 16s, about 105 a second), predicts
    #   about 624s at the ceiling. The card sets that call aside: it is short,
    #   so the call's fixed time weighs more in its average, and it ran at a
    #   thinking level the board does not send. No page read for Neon gives a
    #   model-specific client timeout, as Google's Gemini 4 Carbon guide does
    #   for Carbon (hence Carbon's 900s). The margin is smaller than
    #   Hydrogen's: a request at the ceiling outlasts 600s at any rate below
    #   about 109 completion tokens a second.
    # - provider_max_completion_tokens 65_536: the Models API's
    #   outputTokenLimit for the model, whose entry lists generateContent
    #   among its supported methods (models.get on
    #   generativelanguage.googleapis.com/v1beta/models/gemini-4-neon, read
    #   2026-11-19). litellm makes one non-streaming generateContent request.
    #   Google's model page gives the same 65,536 as the model's "default
    #   synchronous" maximum output, and up to 1,048,576 with long decode. The
    #   raw call at the default level asked for maxOutputTokens 65,536 on one
    #   non-streaming generateContent request and returned 200 (it stopped at
    #   7,930 thought and answer tokens), which shows only that the value is
    #   accepted.
    # - expected_cost_per_scenario_usd is not set: the gauntlet did not reach
    #   its whole-scenario probe and derived no cost, and the smoke ran at the
    #   16,384-token starting budget, which this card no longer sends. It
    #   stays unset until the smoke at the new starting budget.
    # Both raw responses name the model as gemini-4-neon, the requested name,
    # with no dated snapshot (modelVersion). The gauntlet's rows carry the
    # same name, but litellm sets it from the request on this path, so they
    # cannot show a re-route.
    "gemini/gemini-4-neon": ModelCard(
        litellm_id="gemini/gemini-4-neon",
        answer_contract="tool",
        request_timeout_seconds=600,
        thinking_budget=True,
        completion_token_cap=65_536,
        provider_max_completion_tokens=65_536,
        notes=(
            "Written 2026-11-19 from Google's documentation, read that day, "
            "the day after Google released the model. The Gemini API "
            "changelog lists gemini-4-neon as generally available on "
            "2026-11-18, on the paid tier; Google's pricing page lists no "
            "free tier for it. The card takes Gemini 4 Hydrogen's contract, "
            "the board's forced answer tool on the whole-scenario request; "
            "Google's model page lists function calling as supported. The "
            "harness sends no thinkingConfig, and Google's thinking guide "
            "lists the model's default as On (high), with levels low, medium, "
            "high and xhigh, as for Hydrogen. The same day the onboarding "
            "gauntlet ran under this card, then with a 300s timeout and the "
            "Gemini family's 16,384-token starting budget. The "
            "Gemini API accepted the forced call, but on the 3-variable tool "
            "probe the model reasoned until the 16,384-token budget ran out "
            "(16,381 reasoning tokens, finish=length, 0 of 3 outputs parsed, "
            "127s), and the 3-variable JSON probe ended the same way (16,381 "
            "reasoning tokens, 0 of 3, 129s). The gauntlet sends each probe "
            "once at that budget, with no budget escalation, so it found "
            "neither contract answering, reported the model not scorable at "
            "that budget and derived no card. Both contracts failed the same "
            "way, so the row kept the tool contract. Two raw generateContent "
            "calls with one plain tax question and no tools returned thought "
            "tokens (usageMetadata.thoughtsTokenCount): 7,575 thought tokens "
            "and 355 answer tokens with no thinkingConfig, and 1,370 and 350 "
            "at thinking level low, which the board does not send. "
            "Both name the model as gemini-4-neon, the requested name, with "
            "no dated snapshot. A two-household smoke then ran on the board's "
            "request at the 16,384-token starting budget, which the request "
            "doubles on a length finish to 32,768 and then 65,536. Both "
            "households answered every output through the forced tool, 16 of "
            "16 and 20 of 20, so the tool contract stays. The 20-output "
            "household answered on its first request (14,984 completion "
            "tokens, 13,431 of them reasoning, 110s). The 16-output "
            "household's first request used the whole 16,384-token budget and "
            "its second the whole 32,768, both with no answer (16,381 and "
            "32,765 reasoning tokens, 128s and 247s); its third, at 65,536, "
            "answered with 24,444 completion tokens (23,115 reasoning) in "
            "187s. A request that runs out is billed in full and its output "
            "discarded: 49,152 of the smoke's 88,580 completion tokens, an "
            "estimated $0.75 of the smoke's $1.36 at Google's list rates. So "
            "the card starts at the 65,536-token ceiling (completion_token_cap), "
            "with no lower rung to bill and discard; when a request at the "
            "ceiling ends at length with outputs missing, the harness records "
            "them as budget_exhausted_at_ceiling. A smoke at that starting "
            "budget is to come, and the card sets no expected cost per "
            "scenario until then. The Models API gives the model an "
            "outputTokenLimit of 65,536 and lists generateContent, the method "
            "the harness calls with one non-streaming request, among its "
            "supported methods; the model page gives the same 65,536 as the "
            "default synchronous output. The gauntlet's probes, the raw call "
            "at the default level and the smoke's requests ran at about 127 "
            "to 138 completion tokens a second, the smoke's 32,768-token "
            "request at 132, so a request that used the whole 65,536-token "
            "ceiling would take about 475 to 516s at those rates (a request "
            "slower than about 109 tokens a second outlasts 600s); no request "
            "in the record used the whole ceiling. The card sets a 600s "
            "timeout, as Hydrogen's does. The raw call at level low, a short "
            "one, averaged about 105 a second, which predicts about 624s at "
            "the ceiling; Hydrogen's 600s exceeds what the slowest rates in "
            "its record predict, but this card sets that call aside, since "
            "its fixed time weighs more and the board does not send its "
            "thinking level. Google's generateContent long-decode guide (read "
            "2026-11-14 for the Carbon and Hydrogen cards, not re-read for "
            "Neon) says the server closes a non-streaming call after 10 "
            "minutes. The same guide recommends a 20-minute client read "
            "timeout, and its option table gives 20 minutes per request. "
            "Google lists $3/$15 per 1M."
        ),
    ),
    "openrouter/z-ai/glm-5.3": ModelCard(
        litellm_id="openrouter/z-ai/glm-5.3",
        answer_contract="tool",
        request_timeout_seconds=2400,
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.25,
        notes=(
            "Onboarded 2026-09-03 (released 2026-08-18): forced tool contract "
            "passed 3/3 and 16/16 whole-scenario (3,008 completion tokens) "
            "under a thinking-budget probe; its predecessor glm-5.2 ran JSON "
            "in 3-output chunks. The board run reasons far past the probe "
            "(median 6,000 completion tokens per household, several past "
            "100,000) and one household timed out four times at the 300-second "
            "default, so the timeout was raised to 2,400 seconds after 99 of "
            "100 households had completed; the run's spend ledger records "
            "every attempt."
        ),
    ),
    "openrouter/deepseek/deepseek-v4-pro-0813": ModelCard(
        litellm_id="openrouter/deepseek/deepseek-v4-pro-0813",
        answer_contract="tool",
        request_timeout_seconds=2400,
        thinking_budget=True,
        completion_token_cap=98_304,
        expected_cost_per_scenario_usd=0.15,
        notes=(
            "Onboarded 2026-09-04: the 2026-08-12 snapshot of DeepSeek V4 "
            "Pro, addressed by its dated OpenRouter id because the direct "
            "API alias moved under the board's existing row. Forced tool "
            "contract passed 3/3 (63,913 completion tokens, 898s) and 16/16 "
            "whole-scenario (23,920 tokens) under a 98,304-token cap; at "
            "the 16,384 default it reasoned to the ceiling without answering."
        ),
    ),
    "openrouter/deepseek/deepseek-v4-flash-0731": ModelCard(
        litellm_id="openrouter/deepseek/deepseek-v4-flash-0731",
        answer_contract="tool",
        request_timeout_seconds=2400,
        thinking_budget=True,
        completion_token_cap=98_304,
        expected_cost_per_scenario_usd=0.005,
        notes=(
            "Onboarded 2026-09-03: the 2026-07-31 snapshot of DeepSeek V4 "
            "Flash, addressed by its dated OpenRouter id. Forced tool "
            "contract passed 3/3 and 16/16 whole-scenario (7,127 completion "
            "tokens) under a 98,304-token cap; at the 16,384 default it "
            "reasoned to the ceiling without answering."
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
            "Cloaked OpenRouter preview listed 2026-08-20 (free window); "
            "Z.ai identified it as GLM-5.3-Flash on 2026-08-26, after its "
            "run. Board row labeled as a preview: public and callable under "
            "the identical request, dated by its listing. "
            "Tool contract passed the 2026-08-20 gauntlet 3/3 and 16/16 "
            "after the thinking-class budget."
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
    "openrouter/meta/muse-wonder": ModelCard(
        litellm_id="openrouter/meta/muse-wonder",
        answer_contract="json",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.059,
        notes=(
            "Onboarded 2026-10-13, the day after Meta released it. OpenRouter "
            "lists one endpoint, Meta's own (meta/muse-wonder-20261012), so "
            "OpenRouter passes requests to Meta's API. That API accepts "
            "tool_choice 'auto' only: a forced (named-function) or 'required' "
            'tool choice returns a 400 (\'only "auto" is supported for '
            "tool_choice'), so the row runs the JSON contract whole-scenario, "
            "as Opus 5.5 and Sonnet 5.5 do. A request with no reasoning "
            "parameter reasons at the provider default: on a one-question "
            "probe, 1,913 and 3,089 of 1,991 and 3,181 completion tokens with "
            "no tools, and 2,189 and 2,635 of 2,352 and 2,815 with tool_choice "
            "auto; it returns a short reasoning summary and an encrypted "
            "trace. No reasoning-suppression sensitivity run is needed: the "
            "row already reasons on the JSON contract, as Opus 5.5's and "
            "Sonnet 5.5's do. Gauntlet: without the reasoning budget the "
            "3-variable JSON probe stopped at the token limit (384 tokens); "
            "with it, 3/3 and 16/16 parsed on the JSON contract (2,402 and "
            "2,736 completion tokens, 15s and 18s). The gauntlet's cost "
            "estimate is $0.059 per scenario at $4/$20 per 1M with $0.20 "
            "cache reads."
        ),
    ),
    "openrouter/meta/muse-spark-1.3": ModelCard(
        litellm_id="openrouter/meta/muse-spark-1.3",
        answer_contract="json",
        thinking_budget=True,
        expected_cost_per_scenario_usd=0.02,
        notes=(
            "Onboarded 2026-10-13; Meta released it on 2026-09-02. OpenRouter "
            "lists one endpoint, Meta's own (meta/muse-spark-1.3-20260902), so "
            "OpenRouter passes requests to Meta's API. As for Muse Wonder, "
            "that API accepts tool_choice 'auto' only, and Meta rejects forced "
            "tool choices: a named-function or 'required' tool choice returned "
            'a 400 on each of three tries (\'only "auto" is supported for '
            "tool_choice'), so the row runs the JSON contract whole-scenario. "
            "A request with no reasoning parameter reasons at the provider "
            "default: on a one-question probe, 4,311, 7,684 and 8,174 of "
            "4,690, 8,073 and 8,586 completion tokens with no tools, and "
            "4,844, 5,481 and 6,022 of 5,055, 5,667 and 6,266 with "
            "tool_choice auto. No reasoning-suppression sensitivity run is "
            "needed: the row already reasons on the JSON contract. Gauntlet: "
            "without the reasoning budget the 3-variable JSON probe stopped at "
            "the token limit (384 tokens); with it, 3/3 and 16/16 parsed on "
            "the JSON contract (8,163 and 4,258 completion tokens, 106s and "
            "58s), about $0.020 per scenario at $1.25/$4.25 per 1M with $0.15 "
            "cache reads. A four-household smoke on the run path (16, 20, 28 "
            "and 32 outputs) parsed 96/96 in one request each. The board run "
            "answered all 100 households in one request each (four replayed "
            "from the smoke, below), the largest "
            "(scenario_008, 56 outputs) included: 1,984/1,984 parsed, no "
            "budget escalation, at most 96s and 9,871 completion tokens per "
            "household, so the row keeps the thinking class's 300s timeout "
            "and 16,384-token starting budget. Its four smoke households "
            "replay the smoke's responses from the harness cache (identical "
            "requests), as the smoke households of earlier rows do."
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


@contextmanager
def provisional_card(card: ModelCard) -> Iterator[ModelCard]:
    """Serve ``card`` from ``card_for`` inside the block if its model has none.

    Yields the card in effect for ``card.litellm_id``: the model's own card
    when it has one (``card`` is then unused), otherwise ``card``, which is
    removed on exit, even when the block raises, so ``MODEL_CARDS`` is left
    as it was. The onboarding gauntlet probes a new model this way under the
    card it would derive. Not thread-safe: other threads calling
    ``card_for`` for the same id see ``card`` while the block runs.
    """
    existing = card_for(card.litellm_id)
    if existing is not None:
        yield existing
        return
    MODEL_CARDS[card.litellm_id] = card
    try:
        yield card
    finally:
        MODEL_CARDS.pop(card.litellm_id, None)


def completion_budget_ceiling_for(model_id: str) -> int:
    """Return the documented hard provider cap or PolicyBench's 128k default."""
    card = card_for(model_id)
    provider_max = card.provider_max_completion_tokens if card is not None else None
    if provider_max is None:
        return MAX_ESCALATED_COMPLETION_TOKENS
    if provider_max <= 0:
        raise ValueError("provider_max_completion_tokens must be positive")
    return min(MAX_ESCALATED_COMPLETION_TOKENS, provider_max)


def answer_contract_for(
    model_id: str,
    *,
    contract_override: str | None = None,
) -> str:
    """Return the effective structured-answer contract for a model.

    ``contract_override`` is the sensitivity-run escape hatch (env
    ``POLICYBENCH_CONTRACT_OVERRIDE``): a JSON-contract model can be run with
    the answer tool declared so ``POLICYBENCH_TOOL_CHOICE=auto`` has a tool
    to leave to the model. Never set for leaderboard runs.
    """
    if contract_override is not None:
        if contract_override not in ("tool", "json"):
            raise ValueError(
                "POLICYBENCH_CONTRACT_OVERRIDE must be 'tool' or 'json', "
                f"got {contract_override!r}"
            )
        return contract_override
    card = card_for(model_id)
    if card is not None and card.answer_contract is not None:
        return card.answer_contract
    # Family heuristic, not a capability fact: the older Gemini and DeepSeek
    # rows answer as JSON objects whether or not their provider accepts a
    # forced tool call. The disclosures name this alongside the providers
    # that reject forced tools.
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
