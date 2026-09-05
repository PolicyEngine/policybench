"""AI-alone evaluation using LiteLLM (no tools provided)."""

import hashlib
import json
import logging
import os
import re
import signal
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from uuid import uuid4

import litellm
import pandas as pd
from litellm import completion, responses

from policybench.completion_budget import (
    MAX_ESCALATED_COMPLETION_TOKENS,
    completion_budget_from_kwargs,
    next_completion_budget,
    with_completion_budget,
)
from policybench.config import (
    GPT_RESPONSES_MODELS,
    MODELS,
    PRICE_OVERRIDES_PER_1M,
    PROGRAMS,
)
from policybench.model_cards import (
    PROMPT_CONTRACT_VERSION,
    answer_contract_for,
    card_for,
    completion_budget_ceiling_for,
    explanation_chunk_size_for,
)
from policybench.policyengine_runtime import policyengine_bundles_for_countries
from policybench.prompts import (
    get_variable_description,
    make_explanation_repair_prompt,
    make_no_tools_batch_prompt,
    make_no_tools_batch_repair_prompt,
)
from policybench.scenarios import Scenario, scenario_to_dict
from policybench.spec import expand_programs_for_scenario, metric_type_for_output
from policybench.spend_ledger import (
    count_budget_escalations,
    read_spend_ledger,
    spend_ledger_path,
    upsert_spend_ledger,
)

logger = logging.getLogger(__name__)

# Canonical columns emitted by both no-tools result writers. ``run_id`` is
# added only by repeated runs. Keep the worker-schema parity test in sync.
NO_TOOLS_RESULT_COLUMNS = (
    "call_id",
    "model",
    "scenario_id",
    "variable",
    "prediction",
    "explanation",
    "failure_source",
    "raw_response",
    "error",
    "elapsed_seconds",
    "request_started_at",
    "request_completed_at",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "reasoning_tokens",
    "cached_prompt_tokens",
    "cache_write_prompt_tokens",
    "provider_reported_cost_usd",
    "reconstructed_cost_usd",
    "total_cost_usd",
    "cost_is_estimated",
    "estimated_cost_usd",
    "provider_response_id",
    "provider_system_fingerprint",
    "provider_resolved_model",
)

# litellm resolves an unprefixed model's provider (and prices it) through its
# model-cost map, whose remote refresh can time out mid-run and whose bundled
# backup lags brand-new models. Register the Claude Fable line locally so
# provider routing and cost reconstruction never depend on the remote fetch.
# Prices come from the canonical per-million overrides so registration and
# PolicyBench's reconstruction cannot drift apart.
_LOCAL_CLAUDE_FABLE_MODELS = ("claude-fable-5", "claude-fable-5.1")
for _display_id in _LOCAL_CLAUDE_FABLE_MODELS:
    _model_id = MODELS[_display_id]
    if _model_id in litellm.model_cost:
        continue
    _prices = PRICE_OVERRIDES_PER_1M[_display_id]
    litellm.register_model(
        {
            _model_id: {
                "max_tokens": 128000,
                "max_input_tokens": 1000000,
                "max_output_tokens": 128000,
                "input_cost_per_token": _prices["input"] / 1_000_000,
                "output_cost_per_token": _prices["output"] / 1_000_000,
                "cache_read_input_token_cost": _prices["cache_read"] / 1_000_000,
                "cache_creation_input_token_cost": (_prices["cache_write"] / 1_000_000),
                "litellm_provider": "anthropic",
                "mode": "chat",
                "supports_function_calling": True,
                "supports_tool_choice": True,
                "supports_reasoning": True,
                "supports_vision": True,
                "supports_prompt_caching": True,
            }
        }
    )

# LiteLLM's bundled model map predates the GPT-5.6 release. Without a
# local entry it cannot infer that the unprefixed public API ids belong to
# OpenAI, so requests fail before reaching the provider. Keep these entries
# minimal and grounded in OpenAI's published model/pricing pages; a future
# LiteLLM map entry takes precedence automatically.
for _model_id in GPT_RESPONSES_MODELS.values():
    if _model_id in litellm.model_cost:
        continue
    _prices = PRICE_OVERRIDES_PER_1M[_model_id]
    _input_cost = _prices["input"] / 1_000_000
    _output_cost = _prices["output"] / 1_000_000
    litellm.register_model(
        {
            _model_id: {
                "max_tokens": 128000,
                "max_input_tokens": 1050000,
                "max_output_tokens": 128000,
                "input_cost_per_token": _input_cost,
                "output_cost_per_token": _output_cost,
                "cache_read_input_token_cost": _input_cost * 0.1,
                "cache_creation_input_token_cost": _input_cost * 1.25,
                "input_cost_per_token_above_272k_tokens": _input_cost * 2,
                "cache_read_input_token_cost_above_272k_tokens": (_input_cost * 0.2),
                "output_cost_per_token_above_272k_tokens": _output_cost * 1.5,
                "litellm_provider": "openai",
                "mode": "chat",
                "supported_endpoints": [
                    "/v1/chat/completions",
                    "/v1/batch",
                    "/v1/responses",
                ],
                "supports_function_calling": True,
                "supports_parallel_function_calling": True,
                "supports_prompt_caching": True,
                "supports_reasoning": True,
                "supports_response_schema": True,
                "supports_tool_choice": True,
                "supports_vision": True,
            }
        }
    )


def _env_int(name: str, default: int, env: dict | None = None) -> int:
    source = os.environ if env is None else env
    value = source.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


MAX_ATTEMPTS = _env_int("POLICYBENCH_MAX_ATTEMPTS", 2)
RETRY_BASE_DELAY = _env_int("POLICYBENCH_RETRY_BASE_DELAY", 2)
REQUEST_TIMEOUT_SECONDS = _env_int("POLICYBENCH_REQUEST_TIMEOUT_SECONDS", 20)
GEMINI_PRO_REQUEST_TIMEOUT_SECONDS = _env_int(
    "POLICYBENCH_GEMINI_PRO_REQUEST_TIMEOUT_SECONDS", 60
)
XAI_REQUEST_TIMEOUT_SECONDS = _env_int("POLICYBENCH_XAI_REQUEST_TIMEOUT_SECONDS", 420)
# Gemini emits ~5-6k tokens for a full large-household answer (its higher token
# cap); that generation exceeds the 20s default, so all Gemini models get a
# longer request timeout, not just the pro model.
GEMINI_REQUEST_TIMEOUT_SECONDS = _env_int(
    "POLICYBENCH_GEMINI_REQUEST_TIMEOUT_SECONDS", 120
)
# Claude opus/sonnet run adaptive thinking, which can exceed 20s on hard
# scenarios; the default would time out mid-think and never complete the chunk.
CLAUDE_REQUEST_TIMEOUT_SECONDS = _env_int(
    "POLICYBENCH_CLAUDE_REQUEST_TIMEOUT_SECONDS", 120
)
# Claude models whose requests run thinking without us asking: the Fable line
# cannot disable it, and Sonnet 5 defaults to adaptive thinking when the
# request omits the thinking param (ours do — models run at their API
# defaults). Hard single outputs can think for minutes, so they get a longer
# timeout than the rest of the Claude family.
THINKING_DEFAULT_CLAUDE_MODELS = (
    "claude-fable-5",
    "claude-fable-5-1",
    "claude-sonnet-5",
    "claude-opus-5",
)
THINKING_CLAUDE_REQUEST_TIMEOUT_SECONDS = _env_int(
    "POLICYBENCH_THINKING_CLAUDE_REQUEST_TIMEOUT_SECONDS", 300
)
REQUEST_WALL_TIMEOUT_GRACE_SECONDS = 30
REQUEST_WALL_TIMEOUT_MULTIPLIER = 1.5
CHECKPOINT_EVERY_ROWS = 25
DEFAULT_MAX_REPAIR_ROUNDS = 2


def _max_repair_rounds(env: dict | None = None) -> int:
    return _env_int(
        "POLICYBENCH_MAX_REPAIR_ROUNDS",
        DEFAULT_MAX_REPAIR_ROUNDS,
        env,
    )


MAX_REPAIR_ROUNDS = _max_repair_rounds()
RESUME_METADATA_VERSION = 7
DEFAULT_MAX_COMPLETION_TOKENS = 64
EXTENDED_MAX_COMPLETION_TOKENS = 256
EXPLANATION_MAX_COMPLETION_TOKENS = 4096
GEMINI_JSON_MAX_COMPLETION_TOKENS = 16384
GEMINI_PRO_JSON_MAX_COMPLETION_TOKENS = 16384
MAX_COMPLETION_TOKENS_CAP = 4096
# Large households request ~56 per-person outputs; with required explanations a
# verbose model (Gemini) needs ~5-6k completion tokens. The 4096 cap truncated
# Gemini mid-output, silently dropping the tail of the per-person keys, so it
# gets a higher ceiling. Terser models finish well under 4096 and are untouched.
GEMINI_MAX_COMPLETION_TOKENS_CAP = 16384
# Thinking-by-default Claude models bill thinking against the same completion
# budget as the tool-call answer, so the shared 4096 cap could truncate
# mid-answer after a long think. Extra headroom costs nothing when unused.
THINKING_CLAUDE_MAX_COMPLETION_TOKENS_CAP = 16384
# Per-model reasoning-effort overrides sent as `reasoning={"effort": ...}`.
# Models absent from this mapping receive NO reasoning-control parameters:
# whatever an unconfigured API call does is what the benchmark measures.
# EMPTY since 2026-07-03: gpt-5.5 ran with effort "low" from the May 2026
# launch through the v1.x runs (recorded in the manuscript's snapshot
# config); the pin was removed so every model runs unconfigured.
REASONING_EFFORT_OVERRIDES: dict[str, str] = {}
# Per-model serving treatments (answer contract, chunking, timeouts,
# thinking-class budgets) live in policybench/model_cards.py; family-prefix
# heuristics below are the fallback for models without a card.
ANSWER_TOKENS_PER_VARIABLE = 48
EXPLANATION_TOKENS_PER_VARIABLE = 96
ANSWER_COMPLETION_BUFFER_TOKENS = 96
ANSWER_FUNCTION_NAME = "submit_outputs"
EXPLANATION_FUNCTION_NAME = "submit_explanations"


class RequestWallTimeoutError(TimeoutError):
    """Raised when a provider request exceeds PolicyBench's local wall timeout."""


class SensitivityKnobError(ValueError):
    """Raised when a serving sensitivity knob is unsupported by a transport."""


NON_RETRYABLE_ERRORS = (
    RequestWallTimeoutError,
    SensitivityKnobError,
    litellm.AuthenticationError,
    litellm.BadRequestError,
    litellm.ContextWindowExceededError,
    litellm.InvalidRequestError,
    litellm.PermissionDeniedError,
    litellm.UnsupportedParamsError,
    litellm.UnprocessableEntityError,
)
MODEL_FATAL_ERRORS = (
    litellm.AuthenticationError,
    litellm.BadRequestError,
    litellm.ContextWindowExceededError,
    litellm.InvalidRequestError,
    litellm.NotFoundError,
    litellm.PermissionDeniedError,
    litellm.UnsupportedParamsError,
    litellm.UnprocessableEntityError,
)
RETRYABLE_PROVIDER_ERRORS = (
    RequestWallTimeoutError,
    litellm.APIConnectionError,
    litellm.APIError,
    litellm.APIResponseValidationError,
    litellm.BadGatewayError,
    litellm.InternalServerError,
    litellm.RateLimitError,
    litellm.ServiceUnavailableError,
    litellm.Timeout,
)
PROVIDER_ERROR_TEXT_MARKERS = (
    "APIConnectionError",
    "APIError",
    "APIResponseValidationError",
    "BadGatewayError",
    "Connection timed out",
    "InternalServerError",
    "RateLimitError",
    "RequestWallTimeoutError",
    "ServiceUnavailableError",
    "Timeout",
    "temporarily unavailable",
)
FATAL_ERROR_TEXT_MARKERS = (
    "AuthenticationError",
    "BadRequestError",
    "ContextWindowExceededError",
    "InvalidRequestError",
    "NotFoundError",
    "PermissionDeniedError",
    "UnsupportedParamsError",
    "UnprocessableEntityError",
)
STANDALONE_NUMBER_RE = re.compile(r"^\$?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$")
EXPLANATION_VALUE_RE = re.compile(
    r"\bvalue\s*=\s*(\$?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*\.?\s*$",
    re.IGNORECASE,
)


def _format_error(error: Exception) -> str:
    return f"{type(error).__name__}: {str(error).replace(chr(10), ' ')[:500]}"


def _is_insufficient_quota_error(error: Exception) -> bool:
    return "insufficient_quota" in str(error)


def _is_fatal_error_text(error: str | None) -> bool:
    return bool(error and "insufficient_quota" in error)


def _should_retry(error: Exception) -> bool:
    if _is_insufficient_quota_error(error):
        return False
    return not isinstance(error, NON_RETRYABLE_ERRORS)


def _is_model_fatal_error(error: Exception) -> bool:
    return isinstance(error, MODEL_FATAL_ERRORS) or _is_insufficient_quota_error(error)


def is_retryable_provider_error_text(error: str | None) -> bool:
    """Return whether an error string reflects provider transport instability."""
    if not error:
        return False
    if _is_insufficient_quota_error(Exception(error)):
        return False
    error_lower = error.lower()
    return any(marker.lower() in error_lower for marker in PROVIDER_ERROR_TEXT_MARKERS)


def is_infrastructure_error_text(error: str | None) -> bool:
    """Return whether a stored row error should not count as a model miss."""
    if not error:
        return False
    if _is_fatal_error_text(error):
        return True
    error_lower = error.lower()
    if any(marker.lower() in error_lower for marker in FATAL_ERROR_TEXT_MARKERS):
        return True
    return is_retryable_provider_error_text(error)


def _is_retryable_provider_error(error: Exception) -> bool:
    if _is_model_fatal_error(error):
        return False
    return isinstance(
        error,
        RETRYABLE_PROVIDER_ERRORS,
    ) or is_retryable_provider_error_text(_format_error(error))


def _get_usage_value(obj, key: str):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


@dataclass(frozen=True)
class ReconstructedCost:
    """A token-cost reconstruction and whether it came from LiteLLM's map."""

    usd: float | None
    is_estimated: bool | None


def _price_override_for(
    model_name: str, model_id: str
) -> tuple[str, dict[str, float]] | None:
    """Resolve a canonical price by display name, provider id, or roster alias."""
    for candidate in (model_name, model_id):
        override = PRICE_OVERRIDES_PER_1M.get(candidate)
        if override is not None:
            return candidate, override
    for display_name, configured_id in MODELS.items():
        if configured_id == model_id:
            override = PRICE_OVERRIDES_PER_1M.get(display_name)
            if override is not None:
                return display_name, override
    return None


def _reconstruct_token_cost(
    *,
    model_name: str,
    model_id: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    cached_prompt_tokens: int | None = None,
    cache_write_prompt_tokens: int | None = None,
) -> ReconstructedCost:
    """Reconstruct standard synchronous token cost from provider usage.

    PolicyBench's explicit prices are authoritative. LiteLLM's mutable model
    map is used only when no override exists, and that fallback is marked as
    estimated. GPT-5.6 overrides include their documented cache and
    long-context pricing. Other overrides can declare cache-read and
    cache-write rates; overrides without them apply their standard rate to
    the inclusive prompt-token count.
    """
    if prompt_tokens is None or completion_tokens is None:
        return ReconstructedCost(None, None)
    cached = max(0, min(int(cached_prompt_tokens or 0), int(prompt_tokens)))
    cache_write = max(
        0,
        min(int(cache_write_prompt_tokens or 0), int(prompt_tokens) - cached),
    )

    resolved_override = _price_override_for(model_name, model_id)
    if resolved_override is not None:
        override_name, rates = resolved_override
        input_rate = rates["input"] / 1_000_000
        output_rate = rates["output"] / 1_000_000
        if override_name in GPT_RESPONSES_MODELS:
            if prompt_tokens > 272_000:
                input_rate *= 2
                output_rate *= 1.5
            uncached = int(prompt_tokens) - cached - cache_write
            cost = (
                uncached * input_rate
                + cached * input_rate * 0.1
                + cache_write * input_rate * 1.25
                + int(completion_tokens) * output_rate
            )
        elif "cache_read" in rates or "cache_write" in rates:
            uncached = int(prompt_tokens) - cached - cache_write
            cache_read_rate = rates.get("cache_read", rates["input"]) / 1_000_000
            cache_write_rate = rates.get("cache_write", rates["input"]) / 1_000_000
            cost = (
                uncached * input_rate
                + cached * cache_read_rate
                + cache_write * cache_write_rate
                + int(completion_tokens) * output_rate
            )
        else:
            cost = (
                int(prompt_tokens) * input_rate + int(completion_tokens) * output_rate
            )
        return ReconstructedCost(float(cost), False)

    try:
        input_cost, output_cost = litellm.cost_per_token(
            model=model_id,
            prompt_tokens=int(prompt_tokens),
            completion_tokens=int(completion_tokens),
            cache_read_input_tokens=cached,
            cache_creation_input_tokens=cache_write,
        )
        return ReconstructedCost(float(input_cost + output_cost), True)
    except Exception:
        return ReconstructedCost(None, None)


def _extract_provider_fingerprint(response) -> dict:
    """Capture the provider response id, system fingerprint, and resolved model.

    These fields make it possible to audit which underlying model build a
    provider routed an alias to (e.g. ``claude-opus-4-7`` resolving to a
    dated weights revision). Providers that do not report a particular field
    return ``None`` for that field.
    """
    return {
        "provider_response_id": _get_usage_value(response, "id"),
        "provider_system_fingerprint": _get_usage_value(response, "system_fingerprint"),
        "provider_resolved_model": _get_usage_value(response, "model"),
    }


def _response_cache_hit(response) -> bool:
    hidden = (
        response.get("_hidden_params")
        if isinstance(response, dict)
        else getattr(response, "_hidden_params", None)
    )
    return isinstance(hidden, dict) and hidden.get("cache_hit") is True


def _extract_usage_metadata(
    response, model_id: str, messages: list[dict], content: str
) -> dict:
    usage = getattr(response, "usage", None)
    prompt_tokens_details = _get_usage_value(usage, "prompt_tokens_details")
    if prompt_tokens_details is None:
        prompt_tokens_details = _get_usage_value(usage, "input_tokens_details")
    completion_tokens_details = _get_usage_value(usage, "completion_tokens_details")
    if completion_tokens_details is None:
        completion_tokens_details = _get_usage_value(usage, "output_tokens_details")
    reasoning_tokens = _get_usage_value(usage, "reasoning_tokens")
    if reasoning_tokens is None:
        reasoning_tokens = _get_usage_value(
            completion_tokens_details, "reasoning_tokens"
        )

    prompt_tokens = _get_usage_value(usage, "prompt_tokens") or _get_usage_value(
        usage, "input_tokens"
    )
    completion_tokens = _get_usage_value(
        usage, "completion_tokens"
    ) or _get_usage_value(usage, "output_tokens")
    cached_prompt_tokens = _get_usage_value(prompt_tokens_details, "cached_tokens")
    cache_write_prompt_tokens = _get_usage_value(
        prompt_tokens_details, "cache_write_tokens"
    )
    if cache_write_prompt_tokens is None:
        cache_write_prompt_tokens = _get_usage_value(
            prompt_tokens_details, "cache_creation_tokens"
        )

    provider_reported_cost_usd = _get_usage_value(usage, "cost")
    override = _price_override_for(model_id, model_id)
    reconstructed = _reconstruct_token_cost(
        model_name=model_id,
        model_id=model_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_prompt_tokens=cached_prompt_tokens,
        cache_write_prompt_tokens=cache_write_prompt_tokens,
    )
    reconstructed_cost_usd = reconstructed.usd

    if override is not None and reconstructed_cost_usd is not None:
        total_cost_usd = reconstructed_cost_usd
        cost_is_estimated = False
    elif reconstructed_cost_usd is not None:
        total_cost_usd = reconstructed_cost_usd
        cost_is_estimated = reconstructed.is_estimated
    else:
        total_cost_usd = provider_reported_cost_usd
        cost_is_estimated = False if provider_reported_cost_usd is not None else None

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": _get_usage_value(usage, "total_tokens"),
        "reasoning_tokens": reasoning_tokens,
        "cached_prompt_tokens": cached_prompt_tokens,
        "cache_write_prompt_tokens": cache_write_prompt_tokens,
        "provider_reported_cost_usd": provider_reported_cost_usd,
        "reconstructed_cost_usd": reconstructed_cost_usd,
        "total_cost_usd": total_cost_usd,
        "cost_is_estimated": cost_is_estimated,
        "estimated_cost_usd": total_cost_usd,
        **_extract_provider_fingerprint(response),
    }


_SPEND_LEDGER_USAGE_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "reasoning_tokens",
    "cached_prompt_tokens",
    "cache_write_prompt_tokens",
    "provider_reported_cost_usd",
    "reconstructed_cost_usd",
    "total_cost_usd",
    "cost_is_estimated",
    "estimated_cost_usd",
    "provider_response_id",
    "provider_system_fingerprint",
    "provider_resolved_model",
)


def _spend_ledger_record(
    *,
    call_key: str,
    phase: str,
    attempt: int,
    status: str,
    scenario: Scenario,
    variables: list[str],
    model_id: str,
    request_started_at: float | None,
    request_completed_at: float | None,
    elapsed_seconds: float | None,
    usage: dict | None = None,
    error: str | None = None,
    cache_hit: bool = False,
    completion_budget_tokens: int | None = None,
    escalated_from_budget_tokens: int | None = None,
) -> dict:
    """Build one audit row for a physical synchronous provider request."""
    usage = usage or {}
    usage_fields = {field: usage.get(field) for field in _SPEND_LEDGER_USAGE_FIELDS}
    cached_response_cost_usd = None
    if cache_hit:
        cached_response_cost_usd = usage_fields["total_cost_usd"]
        for field in (
            "provider_reported_cost_usd",
            "reconstructed_cost_usd",
            "total_cost_usd",
            "estimated_cost_usd",
        ):
            usage_fields[field] = 0.0
        usage_fields["cost_is_estimated"] = False
    return {
        "call_key": call_key,
        "mode": "sync",
        "phase": phase,
        "attempt": attempt,
        "status": status,
        "model_id": model_id,
        "scenario_id": scenario.id,
        "variables": list(variables),
        "request_started_at": request_started_at,
        "request_completed_at": request_completed_at,
        "elapsed_seconds": elapsed_seconds,
        "error": error,
        "cache_hit": cache_hit,
        "cached_response_cost_usd": cached_response_cost_usd,
        "completion_budget_tokens": completion_budget_tokens,
        "escalated_from_budget_tokens": escalated_from_budget_tokens,
        **usage_fields,
    }


def _spend_records(source) -> list[dict]:
    records = (
        source.get("spend_ledger", [])
        if isinstance(source, dict)
        else getattr(source, "spend_ledger", [])
    )
    return [dict(record) for record in records]


def _attach_spend_records(error: Exception, records: list[dict]) -> None:
    error.spend_ledger = [*records, *_spend_records(error)]


def _emit_spend_records(
    spend_callback: Callable[[list[dict]], None] | None,
    records: list[dict],
) -> None:
    """Persist records without letting storage errors masquerade as call errors."""
    if spend_callback is None:
        return
    try:
        spend_callback(records)
    except Exception as error:
        _attach_spend_records(error, records)
        error._policybench_spend_persistence_failure = True
        raise


def _parse_standalone_number(text: str) -> float | None:
    cleaned = text.strip()
    if not cleaned or not STANDALONE_NUMBER_RE.fullmatch(cleaned):
        return None
    return float(cleaned.replace(",", "").replace("$", ""))


def _required_explanation_chunk_size(
    model_id: str,
    include_explanations: bool,
    env: dict | None = None,
) -> int | None:
    if not include_explanations:
        return None
    # Sensitivity-run escape hatch, sibling of POLICYBENCH_TOOL_CHOICE:
    # POLICYBENCH_CHUNK_OVERRIDE=none runs grandfathered chunked models on
    # the canonical whole-scenario request so their sensitivity runs are
    # shaped like the rest of the roster. Never set for leaderboard runs.
    source = os.environ if env is None else env
    return explanation_chunk_size_for(
        model_id,
        chunk_override=source.get("POLICYBENCH_CHUNK_OVERRIDE"),
    )


def _chunk_variables(variables: list[str], chunk_size: int) -> list[list[str]]:
    return [variables[i : i + chunk_size] for i in range(0, len(variables), chunk_size)]


def _sum_optional_field(results: list[dict], field: str) -> float | int | None:
    values = [result.get(field) for result in results if result.get(field) is not None]
    if not values:
        return None
    return sum(values)


def _completion_token_budget(
    base_tokens: int,
    variables: list[str] | None,
    include_explanations: bool,
    cap: int = MAX_COMPLETION_TOKENS_CAP,
) -> int:
    variable_count = len(variables or [])
    per_variable = (
        EXPLANATION_TOKENS_PER_VARIABLE
        if include_explanations
        else ANSWER_TOKENS_PER_VARIABLE
    )
    dynamic_tokens = ANSWER_COMPLETION_BUFFER_TOKENS + per_variable * variable_count
    return min(max(base_tokens, dynamic_tokens), cap)


def _uncapped_completion_controls(
    model_id: str,
    include_explanations: bool = True,
    variables: list[str] | None = None,
) -> dict:
    if model_id.startswith("gemini/"):
        if model_id == "gemini/gemini-3.1-pro-preview":
            base_tokens = GEMINI_PRO_JSON_MAX_COMPLETION_TOKENS
        else:
            base_tokens = GEMINI_JSON_MAX_COMPLETION_TOKENS
        return {
            "max_completion_tokens": _completion_token_budget(
                base_tokens,
                variables,
                include_explanations,
                cap=GEMINI_MAX_COMPLETION_TOKENS_CAP,
            )
        }
    card = card_for(model_id)
    # A thinking-budget card outranks the legacy xai/ family branch:
    # grok-4.5 reasons by default (14k tokens on the 16-variable probe),
    # while grok-4.3 has no card and keeps the flat family budget.
    if model_id.startswith("xai/") and not (card is not None and card.thinking_budget):
        if include_explanations:
            base_tokens = EXPLANATION_MAX_COMPLETION_TOKENS
        else:
            base_tokens = EXTENDED_MAX_COMPLETION_TOKENS
        return {
            "max_tokens": _completion_token_budget(
                base_tokens, variables, include_explanations
            )
        }
    if card is not None and card.thinking_budget:
        # Reasoning-by-default models bill reasoning against the same
        # completion budget as the answer, and the reasoning spend does not
        # depend on whether explanations were requested — an answers-only
        # request (--no-explanations, repairs) needs the same headroom the
        # explanation path got in #101, or default-effort reasoning exhausts
        # the small dynamic budget before any output. Unused headroom is
        # free.
        cap = (
            card.completion_token_cap
            if card.completion_token_cap is not None
            else THINKING_CLAUDE_MAX_COMPLETION_TOKENS_CAP
        )
        budget = _completion_token_budget(
            cap,
            variables,
            include_explanations,
            cap=cap,
        )
        # xAI rejects max_completion_tokens outright (litellm
        # UnsupportedParamsError); it takes the same budget as max_tokens.
        if model_id.startswith("xai/"):
            return {"max_tokens": budget}
        return {"max_completion_tokens": budget}
    if model_id.startswith("gpt-5"):
        if include_explanations:
            base_tokens = EXPLANATION_MAX_COMPLETION_TOKENS
        else:
            base_tokens = EXTENDED_MAX_COMPLETION_TOKENS
        return {
            "max_completion_tokens": _completion_token_budget(
                base_tokens, variables, include_explanations
            )
        }
    if model_id in THINKING_DEFAULT_CLAUDE_MODELS:
        if include_explanations:
            base_tokens = THINKING_CLAUDE_MAX_COMPLETION_TOKENS_CAP
        else:
            base_tokens = EXTENDED_MAX_COMPLETION_TOKENS
        return {
            "max_completion_tokens": _completion_token_budget(
                base_tokens,
                variables,
                include_explanations,
                cap=THINKING_CLAUDE_MAX_COMPLETION_TOKENS_CAP,
            )
        }
    if model_id.startswith("claude-"):
        if include_explanations:
            base_tokens = EXPLANATION_MAX_COMPLETION_TOKENS
        else:
            base_tokens = EXTENDED_MAX_COMPLETION_TOKENS
        return {
            "max_completion_tokens": _completion_token_budget(
                base_tokens, variables, include_explanations
            )
        }
    return {
        "max_completion_tokens": _completion_token_budget(
            DEFAULT_MAX_COMPLETION_TOKENS, variables, include_explanations
        )
    }


def _completion_budget_ceiling(model_id: str) -> int:
    """Return the largest completion budget PolicyBench may request."""
    return completion_budget_ceiling_for(model_id)


def _completion_controls(
    model_id: str,
    include_explanations: bool = True,
    variables: list[str] | None = None,
) -> dict:
    """Return initial controls capped by a documented provider maximum."""
    controls = _uncapped_completion_controls(
        model_id,
        include_explanations=include_explanations,
        variables=variables,
    )
    budget = completion_budget_from_kwargs(controls)
    ceiling = _completion_budget_ceiling(model_id)
    if budget is not None and budget > ceiling:
        return with_completion_budget(controls, ceiling)
    return controls


def _initial_completion_budget_tokens(
    model_id: str,
    variables: list[str] | None,
    include_explanations: bool = True,
) -> int | None:
    """Return the budget sent on an initial request for concrete outputs.

    ``variables`` must already reflect single-output mode or the first chunk,
    if either applies. This deliberately records the first API request rather
    than claiming to summarize later repair or escalation requests.
    """
    if variables is None:
        return None
    return completion_budget_from_kwargs(
        _completion_controls(
            model_id,
            include_explanations=include_explanations,
            variables=variables,
        )
    )


def _request_timeout_seconds(model_id: str, env: dict | None = None) -> int:
    def configured(name: str, current: int, default: int) -> int:
        if env is None:
            return current
        value = env.get(name)
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    card = card_for(model_id)
    if card is not None and card.request_timeout_seconds is not None:
        return card.request_timeout_seconds
    if card is not None and card.thinking_budget:
        return configured(
            "POLICYBENCH_THINKING_CLAUDE_REQUEST_TIMEOUT_SECONDS",
            THINKING_CLAUDE_REQUEST_TIMEOUT_SECONDS,
            300,
        )
    if model_id.startswith("gemini/"):
        return configured(
            "POLICYBENCH_GEMINI_REQUEST_TIMEOUT_SECONDS",
            GEMINI_REQUEST_TIMEOUT_SECONDS,
            120,
        )
    if model_id == "gpt-5.5":
        return configured(
            "POLICYBENCH_GEMINI_PRO_REQUEST_TIMEOUT_SECONDS",
            GEMINI_PRO_REQUEST_TIMEOUT_SECONDS,
            60,
        )
    if model_id.startswith("xai/"):
        return configured(
            "POLICYBENCH_XAI_REQUEST_TIMEOUT_SECONDS",
            XAI_REQUEST_TIMEOUT_SECONDS,
            420,
        )
    if model_id in THINKING_DEFAULT_CLAUDE_MODELS:
        return configured(
            "POLICYBENCH_THINKING_CLAUDE_REQUEST_TIMEOUT_SECONDS",
            THINKING_CLAUDE_REQUEST_TIMEOUT_SECONDS,
            300,
        )
    if model_id.startswith("claude-"):
        return configured(
            "POLICYBENCH_CLAUDE_REQUEST_TIMEOUT_SECONDS",
            CLAUDE_REQUEST_TIMEOUT_SECONDS,
            120,
        )
    return configured(
        "POLICYBENCH_REQUEST_TIMEOUT_SECONDS",
        REQUEST_TIMEOUT_SECONDS,
        20,
    )


def _request_wall_timeout_seconds(request_kwargs: dict) -> float:
    """Return a local hard timeout slightly above the provider timeout."""
    provider_timeout = request_kwargs.get("timeout") or REQUEST_TIMEOUT_SECONDS
    provider_timeout = float(provider_timeout)
    return max(
        provider_timeout + REQUEST_WALL_TIMEOUT_GRACE_SECONDS,
        provider_timeout * REQUEST_WALL_TIMEOUT_MULTIPLIER,
    )


def _run_request_with_wall_timeout(request_fn, request_kwargs: dict):
    """Run one LiteLLM request with a process-local wall-clock timeout.

    Some provider clients can outlive the configured request timeout. The CLI
    runs requests on the main thread, so SIGALRM gives the runner a last-resort
    escape hatch while preserving normal behavior in non-main-thread contexts.
    """
    if (
        threading.current_thread() is not threading.main_thread()
        or not hasattr(signal, "SIGALRM")
        or not hasattr(signal, "setitimer")
    ):
        return request_fn(**request_kwargs)

    wall_timeout_seconds = _request_wall_timeout_seconds(request_kwargs)
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)

    def _raise_timeout(_signum, _frame):
        raise RequestWallTimeoutError(
            f"Provider request exceeded {wall_timeout_seconds}s wall-clock timeout"
        )

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, wall_timeout_seconds)
    try:
        return request_fn(**request_kwargs)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)


def _answer_contract_for_model(model_id: str, env: dict | None = None) -> str:
    # Sensitivity-run escape hatch, sibling of POLICYBENCH_TOOL_CHOICE and
    # POLICYBENCH_CHUNK_OVERRIDE: POLICYBENCH_CONTRACT_OVERRIDE=tool runs a
    # JSON-contract model with the answer tool declared, so a tool_choice=auto
    # sensitivity run has a tool for the model to choose. Never set for
    # leaderboard runs.
    source = os.environ if env is None else env
    return answer_contract_for(
        model_id,
        contract_override=source.get("POLICYBENCH_CONTRACT_OVERRIDE"),
    )


def _tool_choice_for(function_name: str) -> str | dict:
    """Return the tool_choice every chat-path builder sends for its tool.

    The canonical board forces the tool. POLICYBENCH_TOOL_CHOICE=auto is the
    sensitivity-run escape hatch that lets the model decide when to call it:
    Anthropic models skip thinking when the tool is forced (verified on
    claude-opus-5: forced tool or forced tool + explicit adaptive produce no
    thinking blocks; tool_choice auto produces them), so the board runs those
    Claudes without thinking while reasoning-by-default providers reason
    regardless. Never set this for leaderboard runs; scores under auto are
    not comparable to the board. The answer and explanation-repair builders
    both call this so a sensitivity run never mixes modes mid-scenario.
    """
    if os.environ.get("POLICYBENCH_TOOL_CHOICE") == "auto":
        return "auto"
    return {"type": "function", "function": {"name": function_name}}


def _uses_responses_api(model_id: str) -> bool:
    return model_id.startswith("gpt-5") or model_id.startswith("gpt-6")


def _thinking_configuration(model_id: str) -> dict | None:
    """Describe the reasoning control used by the request builders.

    A provider-default entry means the harness sends no reasoning-control
    parameter for a model known to reason by default. ``None`` means the
    harness applies no thinking treatment for that model. Keeping explicit
    reasoning overrides behind this helper makes request construction and
    persisted treatment metadata share one source of truth.
    """
    if model_id in REASONING_EFFORT_OVERRIDES:
        return {"reasoning_effort": REASONING_EFFORT_OVERRIDES[model_id]}
    card = card_for(model_id)
    if (card is not None and card.thinking_budget) or (
        model_id in THINKING_DEFAULT_CLAUDE_MODELS
    ):
        return {"mode": "provider_default"}
    return None


def _first_request_variables(
    model_id: str,
    variables: list[str],
    include_explanations: bool,
    *,
    single_output: bool = False,
    chunk_override: str | None = None,
) -> list[str]:
    """Select the outputs included in a model's first API request."""
    if single_output:
        return variables[:1]
    chunk_size = (
        explanation_chunk_size_for(model_id, chunk_override=chunk_override)
        if include_explanations
        else None
    )
    if chunk_size is not None:
        return variables[:chunk_size]
    return variables


def _apply_thinking_configuration(request_kwargs: dict, model_id: str) -> None:
    """Apply the explicit part of ``_thinking_configuration`` in place."""
    thinking = _thinking_configuration(model_id)
    if thinking is not None and "reasoning_effort" in thinking:
        request_kwargs["reasoning"] = {"effort": thinking["reasoning_effort"]}


def _chat_completion_request_kwargs(
    scenario: Scenario,
    variables: list[str],
    model_id: str,
    repair: bool = False,
    include_explanations: bool = True,
) -> tuple[list[dict], dict]:
    answer_contract = _answer_contract_for_model(model_id)
    prompt_builder = (
        make_no_tools_batch_repair_prompt if repair else make_no_tools_batch_prompt
    )
    prompt = prompt_builder(
        scenario,
        variables,
        answer_contract=answer_contract,
        include_explanations=include_explanations,
    )
    messages = [{"role": "user", "content": prompt}]
    request_kwargs = {
        "model": model_id,
        "messages": messages,
        "caching": True,
        "timeout": _request_timeout_seconds(model_id),
        **_completion_controls(
            model_id,
            include_explanations=include_explanations,
            variables=variables,
        ),
    }
    if answer_contract == "tool":
        tool = _build_answer_tool(
            variables,
            country=scenario.country,
            include_explanations=include_explanations,
        )
        request_kwargs.update(
            {"tools": [tool], "tool_choice": _tool_choice_for(ANSWER_FUNCTION_NAME)}
        )
    else:
        request_kwargs["response_format"] = {"type": "json_object"}
    _apply_thinking_configuration(request_kwargs, model_id)
    return messages, request_kwargs


def _responses_request_kwargs(
    scenario: Scenario,
    variables: list[str],
    model_id: str,
    repair: bool = False,
    include_explanations: bool = True,
) -> tuple[list[dict], dict]:
    _reject_sensitivity_knobs_for_responses(model_id)
    answer_contract = _answer_contract_for_model(model_id)
    prompt_builder = (
        make_no_tools_batch_repair_prompt if repair else make_no_tools_batch_prompt
    )
    prompt = prompt_builder(
        scenario,
        variables,
        answer_contract=answer_contract,
        include_explanations=include_explanations,
    )
    request_kwargs = {
        "model": model_id,
        "input": prompt,
        "timeout": _request_timeout_seconds(model_id),
        "max_output_tokens": _completion_controls(
            model_id,
            include_explanations=include_explanations,
            variables=variables,
        )["max_completion_tokens"],
    }
    if answer_contract == "tool":
        request_kwargs.update(
            {
                "tools": [
                    _responses_tool_schema(
                        variables,
                        country=scenario.country,
                        include_explanations=include_explanations,
                    )
                ],
                "tool_choice": {
                    "type": "function",
                    "name": ANSWER_FUNCTION_NAME,
                },
            }
        )
    _apply_thinking_configuration(request_kwargs, model_id)
    return [{"role": "user", "content": prompt}], request_kwargs


def _build_answer_tool(
    variables: list[str],
    country: str = "us",
    include_explanations: bool = True,
) -> dict:
    def value_schema(variable: str) -> dict:
        schema = {
            "type": "number",
            "description": get_variable_description(variable, country=country),
        }
        if metric_type_for_output(variable) == "binary":
            schema.update(
                {
                    "type": "integer",
                    "enum": [0, 1],
                    "description": (
                        get_variable_description(variable, country=country)
                        + " Use 1 for yes/eligible and 0 for no/not eligible."
                    ),
                }
            )
        return schema

    if include_explanations:
        outputs_schema = {
            "type": "object",
            "properties": {
                variable: {
                    "type": "object",
                    "properties": {
                        "value": value_schema(variable),
                        "explanation": {
                            "type": "string",
                            "description": (
                                "Brief explanation supporting this exact value"
                            ),
                        },
                    },
                    "required": ["value", "explanation"],
                    "additionalProperties": False,
                }
                for variable in variables
            },
            "required": list(variables),
            "additionalProperties": False,
        }
    else:
        outputs_schema = {
            "type": "object",
            "properties": {variable: value_schema(variable) for variable in variables},
            "required": list(variables),
            "additionalProperties": False,
        }
    parameters = outputs_schema
    if include_explanations:
        parameters = {
            "type": "object",
            "properties": {
                "outputs": outputs_schema,
            },
            "required": ["outputs"],
            "additionalProperties": False,
        }
    return {
        "type": "function",
        "function": {
            "name": ANSWER_FUNCTION_NAME,
            "description": (
                "Submit all requested benchmark outputs. "
                "Every requested key is required, including keys whose value is 0."
            ),
            "parameters": parameters,
        },
    }


def _build_explanation_tool(
    variables: list[str],
    country: str = "us",
) -> dict:
    parameters = {
        "type": "object",
        "properties": {
            variable: {
                "type": "string",
                "description": (
                    f"Brief explanation for the estimated {variable} value: "
                    f"{get_variable_description(variable, country=country)}"
                ),
            }
            for variable in variables
        },
        "required": list(variables),
        "additionalProperties": False,
    }
    return {
        "type": "function",
        "function": {
            "name": EXPLANATION_FUNCTION_NAME,
            "description": (
                "Submit explanations for already-returned numeric benchmark answers."
            ),
            "parameters": parameters,
        },
    }


def _responses_explanation_tool_schema(
    variables: list[str],
    country: str = "us",
) -> dict:
    function_schema = _build_explanation_tool(variables, country=country)["function"]
    return {
        "type": "function",
        "name": function_schema["name"],
        "description": function_schema["description"],
        "parameters": function_schema["parameters"],
    }


def _responses_tool_schema(
    variables: list[str],
    country: str = "us",
    include_explanations: bool = True,
) -> dict:
    function_schema = _build_answer_tool(
        variables,
        country=country,
        include_explanations=include_explanations,
    )["function"]
    return {
        "type": "function",
        "name": function_schema["name"],
        "description": function_schema["description"],
        "parameters": function_schema["parameters"],
    }


def _normalize_variables(variables: str | Iterable[str]) -> list[str]:
    if isinstance(variables, str):
        return [variables]
    return list(variables)


def _sum_optional_numbers(values: Iterable[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return sum(present)


def _min_optional_numbers(values: Iterable[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return min(present)


def _max_optional_numbers(values: Iterable[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return max(present)


def _first_non_null(values: Iterable):
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _combine_raw_responses(raw_responses: list[str | None]) -> str | None:
    present = [raw_response for raw_response in raw_responses if raw_response]
    if not present:
        return None
    if len(present) == 1:
        return present[0]
    return json.dumps({"responses": present})


def _missing_variables(predictions: dict[str, float | None]) -> list[str]:
    return [variable for variable, value in predictions.items() if value is None]


def _merge_predictions(
    base: dict[str, float | None],
    incoming: dict[str, float | None],
) -> dict[str, float | None]:
    merged = dict(base)
    for variable, value in incoming.items():
        if value is not None:
            merged[variable] = value
    return merged


def _combined_cost_is_estimated(results: list[dict]) -> bool | None:
    flags = [
        result.get("cost_is_estimated")
        for result in results
        if result.get("total_cost_usd") is not None
    ]
    if any(flag is True for flag in flags):
        return True
    if any(flag is False for flag in flags):
        return False
    return None


def _aggregate_request_results(results: list[dict]) -> dict:
    if not results:
        return {
            "raw_response": None,
            "elapsed_seconds": None,
            "request_started_at": None,
            "request_completed_at": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "reasoning_tokens": None,
            "cached_prompt_tokens": None,
            "cache_write_prompt_tokens": None,
            "provider_reported_cost_usd": None,
            "reconstructed_cost_usd": None,
            "total_cost_usd": None,
            "cost_is_estimated": None,
            "estimated_cost_usd": None,
            "provider_response_id": None,
            "provider_system_fingerprint": None,
            "provider_resolved_model": None,
        }

    return {
        "raw_response": _combine_raw_responses(
            [result.get("raw_response") for result in results]
        ),
        "elapsed_seconds": _sum_optional_numbers(
            result.get("elapsed_seconds") for result in results
        ),
        "request_started_at": _min_optional_numbers(
            result.get("request_started_at") for result in results
        ),
        "request_completed_at": _max_optional_numbers(
            result.get("request_completed_at") for result in results
        ),
        "prompt_tokens": _sum_optional_numbers(
            result.get("prompt_tokens") for result in results
        ),
        "completion_tokens": _sum_optional_numbers(
            result.get("completion_tokens") for result in results
        ),
        "total_tokens": _sum_optional_numbers(
            result.get("total_tokens") for result in results
        ),
        "reasoning_tokens": _sum_optional_numbers(
            result.get("reasoning_tokens") for result in results
        ),
        "cached_prompt_tokens": _sum_optional_numbers(
            result.get("cached_prompt_tokens") for result in results
        ),
        "cache_write_prompt_tokens": _sum_optional_numbers(
            result.get("cache_write_prompt_tokens") for result in results
        ),
        "provider_reported_cost_usd": _sum_optional_numbers(
            result.get("provider_reported_cost_usd") for result in results
        ),
        "reconstructed_cost_usd": _sum_optional_numbers(
            result.get("reconstructed_cost_usd") for result in results
        ),
        "total_cost_usd": _sum_optional_numbers(
            result.get("total_cost_usd") for result in results
        ),
        "cost_is_estimated": _combined_cost_is_estimated(results),
        "estimated_cost_usd": _sum_optional_numbers(
            result.get("estimated_cost_usd") for result in results
        ),
        "provider_response_id": _first_non_null(
            result.get("provider_response_id") for result in results
        ),
        "provider_system_fingerprint": _first_non_null(
            result.get("provider_system_fingerprint") for result in results
        ),
        "provider_resolved_model": _first_non_null(
            result.get("provider_resolved_model") for result in results
        ),
    }


def _empty_failed_result(
    variables: list[str],
    error: Exception,
) -> dict:
    spend_records = _spend_records(error)
    return {
        "predictions": {variable: None for variable in variables},
        "explanations": {variable: None for variable in variables},
        "prediction": None,
        "error": _format_error(error),
        "repair_disagreements": [],
        "failure_sources": {},
        "budget_escalation_count": count_budget_escalations(spend_records),
        "spend_ledger": spend_records,
        **_aggregate_request_results([]),
    }


def extract_number(text: str) -> float | None:
    """Extract a numeric value from a standalone numeric payload."""
    if not text:
        return None

    full_match = _parse_standalone_number(text)
    if full_match is not None:
        return full_match

    return None


def _coerce_prediction_value(value) -> float | None:
    if isinstance(value, dict):
        return _coerce_prediction_value(value.get("value"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        return extract_number(value)
    return None


def _parse_json_object_string(value):
    if not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
    except Exception:
        stripped = value.strip()
        if not stripped.startswith(("{", "[")):
            return value
        try:
            parsed, end = json.JSONDecoder().raw_decode(stripped)
        except Exception:
            return value
        trailing = stripped[end:].strip()
        if trailing and set(trailing) - {'"', "'"}:
            return value
        return parsed
    return parsed


def _json_text_candidates(value: str) -> list[str]:
    """Return JSON-like text variants for provider-escaped partial payloads."""
    candidates = [value]
    if '\\"' in value:
        unescaped = (
            value.replace('\\"', '"').replace("\\\\n", "\n").replace("\\\\t", "\t")
        )
        if unescaped not in candidates:
            candidates.append(unescaped)
    return candidates


def _balanced_json_object_at(text: str, start: int) -> str | None:
    """Return the complete JSON object starting at start, or None if truncated."""
    if start < 0 or start >= len(text) or text[start] != "{":
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _extract_complete_variable_objects_from_text(
    text: str,
    variables: list[str],
) -> dict[str, dict]:
    """Extract complete keyed JSON objects from otherwise invalid JSON text."""
    extracted: dict[str, dict] = {}
    for candidate in _json_text_candidates(text):
        for variable in variables:
            if variable in extracted:
                continue
            pattern = re.compile(rf'"{re.escape(variable)}"\s*:\s*{{')
            match = pattern.search(candidate)
            if not match:
                continue
            object_start = match.end() - 1
            object_text = _balanced_json_object_at(candidate, object_start)
            if object_text is None:
                continue
            try:
                parsed = json.loads(object_text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                extracted[variable] = parsed
    return extracted


def _find_variable_entries(payload, variables: list[str]) -> dict[str, dict]:
    """Find requested variable answer objects in nested provider payloads."""
    found: dict[str, dict] = {}

    def visit(value) -> None:
        if len(found) == len(variables):
            return
        if isinstance(value, str):
            parsed = _parse_json_object_string(value)
            if parsed is not value:
                visit(parsed)
            for variable, entry in _extract_complete_variable_objects_from_text(
                value,
                variables,
            ).items():
                found.setdefault(variable, entry)
            return
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        for variable in variables:
            entry = value.get(variable)
            if isinstance(entry, dict):
                found.setdefault(variable, entry)
            elif entry is not None:
                found.setdefault(variable, {"value": entry})
        if "outputs" in value:
            visit(value.get("outputs"))
        for item in value.values():
            visit(item)

    visit(_extract_outputs_payload(payload))
    return found


def _extract_outputs_payload(payload):
    """Return the nested outputs object from a provider payload, if present."""
    if isinstance(payload, str):
        payload = _parse_json_object_string(payload)

    if not isinstance(payload, dict):
        return payload

    outputs = payload.get("outputs")
    if outputs is None:
        return payload

    outputs = _parse_json_object_string(outputs)
    if isinstance(outputs, dict):
        return outputs
    return payload


def _extract_terminal_explanation_value(explanation: str) -> float | None:
    match = EXPLANATION_VALUE_RE.search(explanation.strip())
    if not match:
        return None
    return float(match.group(1).replace("$", "").replace(",", ""))


def _numeric_values_match(left: float, right: float) -> bool:
    return abs(left - right) <= 1e-6 * max(1.0, abs(left), abs(right))


def _merge_repair_cells(
    base: dict,
    repair: dict,
    *,
    field: str,
    disagreements: list[dict],
) -> dict:
    """Fill invalid cells from a repair response without changing valid cells."""
    merged = dict(base)
    for variable, repair_value in repair.items():
        if repair_value is None:
            continue
        original_value = merged.get(variable)
        if original_value is None:
            merged[variable] = repair_value
            continue

        if field == "prediction":
            disagrees = not _numeric_values_match(
                float(original_value), float(repair_value)
            )
        else:
            disagrees = original_value != repair_value
        if not disagrees:
            continue

        diagnostic = {
            "variable": variable,
            "field": field,
            "original": original_value,
            "repair": repair_value,
        }
        disagreements.append(diagnostic)
        logger.warning(
            "Ignoring repair disagreement for %s %s: original=%r repair=%r",
            variable,
            field,
            original_value,
            repair_value,
        )
    return merged


def _enforce_explanation_value_contract(
    predictions: dict[str, float | None],
    explanations: dict[str, str | None],
    variables: list[str],
) -> tuple[dict[str, float | None], dict[str, str | None]]:
    """Use the terminal explanation value only when structured output is unusable.

    The response contract requires every explanation to end with a ``value = X``
    line. A valid structured/tool value is canonical. The explanation trailer only
    rescues a missing or unparseable structured value; disagreements are logged and
    leave the structured value unchanged. A structured value whose explanation has
    no usable trailer drops the explanation rather than the value.
    """
    checked_predictions = dict(predictions)
    checked_explanations = dict(explanations)
    for variable in variables:
        explanation = checked_explanations.get(variable)
        if not isinstance(explanation, str) or not explanation.strip():
            continue
        explanation_value = _extract_terminal_explanation_value(explanation)
        if explanation_value is None:
            checked_explanations[variable] = None
            continue
        prediction = checked_predictions.get(variable)
        if prediction is None:
            checked_predictions[variable] = explanation_value
        elif not _numeric_values_match(prediction, explanation_value):
            logger.warning(
                "Structured value disagrees with explanation trailer for %s: "
                "structured=%r explanation=%r; keeping structured value",
                variable,
                prediction,
                explanation_value,
            )
    return checked_predictions, checked_explanations


def _extract_predictions_from_payload(
    payload,
    variables: list[str],
) -> dict[str, float | None]:
    predictions = {variable: None for variable in variables}
    entries = _find_variable_entries(payload, variables)
    for variable, entry in entries.items():
        predictions[variable] = _coerce_prediction_value(entry)

    return predictions


def _extract_explanations_from_payload(
    payload,
    variables: list[str],
) -> dict[str, str | None]:
    explanations = {variable: None for variable in variables}
    entries = _find_variable_entries(payload, variables)
    for variable, entry in entries.items():
        explanation = entry.get("explanation")
        if isinstance(explanation, str):
            cleaned = explanation.strip()
            explanations[variable] = cleaned or None
    return explanations


def _missing_explanations(
    explanations: dict[str, str | None],
    variables: list[str],
) -> list[str]:
    return [
        variable
        for variable in variables
        if not isinstance(explanations.get(variable), str)
        or not explanations.get(variable, "").strip()
    ]


def _get_tool_call_function(tool_call):
    if tool_call is None:
        return None
    if isinstance(tool_call, dict):
        return tool_call.get("function")
    return getattr(tool_call, "function", None)


def _get_function_name(function_call) -> str | None:
    if function_call is None:
        return None
    if isinstance(function_call, dict):
        return function_call.get("name")
    return getattr(function_call, "name", None)


def _get_function_arguments(function_call):
    if function_call is None:
        return None
    if isinstance(function_call, dict):
        return function_call.get("arguments")
    return getattr(function_call, "arguments", None)


def _serialize_function_call(function_call) -> dict | None:
    name = _get_function_name(function_call)
    arguments = _get_function_arguments(function_call)
    if not isinstance(name, str):
        name = None
    if isinstance(arguments, (dict, list)):
        pass
    elif not isinstance(arguments, str):
        arguments = None

    if name is None and arguments is None:
        return None
    if function_call is None:
        return None
    return {
        "name": name,
        "arguments": arguments,
    }


def _serialize_response_payload(
    content, tool_calls=None, function_call=None
) -> str | None:
    payload = {}
    if content is not None:
        payload["content"] = content

    serialized_tool_calls = []
    for tool_call in tool_calls or []:
        function = _get_tool_call_function(tool_call)
        serialized_tool_calls.append(
            {
                "name": _get_function_name(function),
                "arguments": _get_function_arguments(function),
            }
        )
    if serialized_tool_calls:
        payload["tool_calls"] = serialized_tool_calls

    serialized_function_call = _serialize_function_call(function_call)
    if serialized_function_call is not None:
        payload["function_call"] = serialized_function_call

    if not payload:
        return None
    if set(payload) == {"content"} and isinstance(content, str):
        return content
    return json.dumps(payload)


def _get_response_item_attr(item, key: str):
    if item is None:
        return None
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _responses_content_and_tool_calls(response) -> tuple[str | None, list[dict]]:
    output = getattr(response, "output", None) or []
    content_segments = []
    tool_calls = []
    for item in output:
        item_type = _get_response_item_attr(item, "type")
        if item_type == "function_call":
            tool_calls.append(
                {
                    "function": {
                        "name": _get_response_item_attr(item, "name"),
                        "arguments": _get_response_item_attr(item, "arguments"),
                    }
                }
            )
            continue
        if item_type != "message":
            continue
        for part in _get_response_item_attr(item, "content") or []:
            if _get_response_item_attr(part, "type") != "output_text":
                continue
            text = _get_response_item_attr(part, "text")
            if text:
                content_segments.append(text)

    content = getattr(response, "output_text", None)
    if not content and content_segments:
        content = "\n".join(content_segments)
    return content, tool_calls


def _response_finish_reason(
    response,
    *,
    responses_api: bool,
    completion_budget_tokens: int | None = None,
) -> str | None:
    """Normalize provider completion-limit signals to ``length``."""
    if not responses_api:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return None
        reason = _get_response_item_attr(choices[0], "finish_reason")
        return str(reason) if isinstance(reason, str) else None

    reason = _get_response_item_attr(response, "finish_reason")
    if reason == "length":
        return "length"
    status = _get_response_item_attr(response, "status")
    details = _get_response_item_attr(response, "incomplete_details")
    incomplete_reason = _get_response_item_attr(details, "reason")
    if status == "incomplete" and incomplete_reason in {
        "max_output_tokens",
        "max_tokens",
        "length",
    }:
        return "length"
    if (
        status == "incomplete"
        and incomplete_reason is None
        and completion_budget_tokens is not None
    ):
        usage = _get_response_item_attr(response, "usage")
        output_tokens = _get_usage_value(usage, "completion_tokens")
        if output_tokens is None:
            output_tokens = _get_usage_value(usage, "output_tokens")
        if (
            isinstance(output_tokens, (int, float))
            and not isinstance(output_tokens, bool)
            and output_tokens >= completion_budget_tokens
        ):
            # LiteLLM's chat-to-Responses adapter currently drops the
            # underlying chat ``finish_reason``. A bare incomplete response
            # that consumed the requested output budget is the remaining
            # observable completion-cap signal; lower-token incomplete
            # responses (for example filters/refusals) are not escalated.
            return "length"
    if status == "length":
        return "length"
    if status == "completed":
        return "stop"
    if isinstance(reason, str):
        return reason
    return str(status) if isinstance(status, str) else None


def extract_predictions(
    content: str | None,
    variables: list[str],
    tool_calls=None,
    function_call=None,
) -> dict[str, float | None]:
    """Extract a mapping of variable -> prediction from tool output or valid JSON."""
    for tool_call in tool_calls or []:
        function = _get_tool_call_function(tool_call)
        if _get_function_name(function) != ANSWER_FUNCTION_NAME:
            continue
        arguments = _get_function_arguments(function)
        predictions = _extract_predictions_from_payload(arguments, variables)
        if any(value is not None for value in predictions.values()):
            return predictions

    if _get_function_name(function_call) == ANSWER_FUNCTION_NAME:
        arguments = _get_function_arguments(function_call)
        predictions = _extract_predictions_from_payload(arguments, variables)
        if any(value is not None for value in predictions.values()):
            return predictions

    return _extract_predictions_from_payload(content, variables)


def extract_explanations(
    content: str | None,
    variables: list[str],
    tool_calls=None,
    function_call=None,
) -> dict[str, str | None]:
    """Extract optional per-variable explanations from structured output."""
    for tool_call in tool_calls or []:
        function = _get_tool_call_function(tool_call)
        if _get_function_name(function) != ANSWER_FUNCTION_NAME:
            continue
        arguments = _get_function_arguments(function)
        explanations = _extract_explanations_from_payload(arguments, variables)
        if any(value is not None for value in explanations.values()):
            return explanations

    if _get_function_name(function_call) == ANSWER_FUNCTION_NAME:
        arguments = _get_function_arguments(function_call)
        explanations = _extract_explanations_from_payload(arguments, variables)
        if any(value is not None for value in explanations.values()):
            return explanations

    return _extract_explanations_from_payload(content, variables)


def _extract_explanation_repair_payload(payload, variables: list[str]) -> dict:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return {variable: None for variable in variables}
    if not isinstance(payload, dict):
        return {variable: None for variable in variables}
    return {
        variable: (
            value.strip()
            if isinstance((value := payload.get(variable)), str) and value.strip()
            else None
        )
        for variable in variables
    }


def _extract_repaired_explanations(
    content: str | None,
    variables: list[str],
    tool_calls=None,
    function_call=None,
) -> dict:
    for tool_call in tool_calls or []:
        function = _get_tool_call_function(tool_call)
        if _get_function_name(function) != EXPLANATION_FUNCTION_NAME:
            continue
        explanations = _extract_explanation_repair_payload(
            _get_function_arguments(function), variables
        )
        if any(value is not None for value in explanations.values()):
            return explanations

    if _get_function_name(function_call) == EXPLANATION_FUNCTION_NAME:
        explanations = _extract_explanation_repair_payload(
            _get_function_arguments(function_call), variables
        )
        if any(value is not None for value in explanations.values()):
            return explanations

    return _extract_explanation_repair_payload(content, variables)


def _request_explanations_once(
    scenario: Scenario,
    variables: list[str],
    answers: dict[str, float],
    model_id: str,
    spend_callback: Callable[[list[dict]], None] | None = None,
    *,
    completion_budget_tokens: int | None = None,
    escalated_from_budget_tokens: int | None = None,
) -> dict:
    answer_contract = _answer_contract_for_model(model_id)
    prompt = make_explanation_repair_prompt(
        scenario,
        variables,
        answers,
        answer_contract=answer_contract,
    )
    if _uses_responses_api(model_id):
        _reject_sensitivity_knobs_for_responses(model_id)
        messages = [{"role": "user", "content": prompt}]
        request_kwargs = {
            "model": model_id,
            "input": prompt,
            "timeout": _request_timeout_seconds(model_id),
            "max_output_tokens": _completion_controls(
                model_id,
                include_explanations=True,
                variables=variables,
            )["max_completion_tokens"],
            "tools": [
                _responses_explanation_tool_schema(
                    variables,
                    country=scenario.country,
                )
            ],
            "tool_choice": {
                "type": "function",
                "name": EXPLANATION_FUNCTION_NAME,
            },
        }
        _apply_thinking_configuration(request_kwargs, model_id)
        request_fn = responses
    else:
        messages = [{"role": "user", "content": prompt}]
        request_kwargs = {
            "model": model_id,
            "messages": messages,
            "caching": True,
            "timeout": _request_timeout_seconds(model_id),
            **_completion_controls(
                model_id,
                include_explanations=True,
                variables=variables,
            ),
        }
        if answer_contract == "tool":
            request_kwargs.update(
                {
                    "tools": [
                        _build_explanation_tool(
                            variables,
                            country=scenario.country,
                        )
                    ],
                    "tool_choice": _tool_choice_for(EXPLANATION_FUNCTION_NAME),
                }
            )
        else:
            request_kwargs["response_format"] = {"type": "json_object"}
        _apply_thinking_configuration(request_kwargs, model_id)
        request_fn = completion

    if completion_budget_tokens is not None:
        request_kwargs = with_completion_budget(
            request_kwargs,
            completion_budget_tokens,
        )
    request_completion_budget = completion_budget_from_kwargs(request_kwargs)
    call_key = f"sync:{uuid4().hex}"
    request_started_at = time.time()
    started_at = time.perf_counter()
    usage: dict = {}
    try:
        response = _run_request_with_wall_timeout(request_fn, request_kwargs)
        elapsed_seconds = time.perf_counter() - started_at
        request_completed_at = time.time()
        if _uses_responses_api(model_id):
            content, tool_calls = _responses_content_and_tool_calls(response)
            function_call = None
        else:
            message = response.choices[0].message
            content = getattr(message, "content", None)
            tool_calls = getattr(message, "tool_calls", None)
            function_call = getattr(message, "function_call", None)
        finish_reason = _response_finish_reason(
            response,
            responses_api=_uses_responses_api(model_id),
            completion_budget_tokens=request_completion_budget,
        )
        raw_response = _serialize_response_payload(
            content=content,
            tool_calls=tool_calls,
            function_call=function_call,
        )
        explanations = _extract_repaired_explanations(
            content,
            variables,
            tool_calls=tool_calls,
            function_call=function_call,
        )
        for variable in variables:
            explanation = explanations.get(variable)
            if not isinstance(explanation, str) or not explanation.strip():
                explanations[variable] = None
                continue
            explanation_value = _extract_terminal_explanation_value(explanation)
            answer = answers.get(variable)
            if explanation_value is None or answer is None:
                explanations[variable] = None
                continue
            if not _numeric_values_match(explanation_value, float(answer)):
                explanations[variable] = None
        usage = _extract_usage_metadata(response, model_id, messages, content or "")
        spend_record = _spend_ledger_record(
            call_key=call_key,
            phase="explanation_repair",
            attempt=1,
            status=(
                "parse_error"
                if any(explanations.get(variable) is None for variable in variables)
                else "ok"
            ),
            scenario=scenario,
            variables=variables,
            model_id=model_id,
            request_started_at=request_started_at,
            request_completed_at=request_completed_at,
            elapsed_seconds=elapsed_seconds,
            usage=usage,
            cache_hit=_response_cache_hit(response),
            completion_budget_tokens=request_completion_budget,
            escalated_from_budget_tokens=escalated_from_budget_tokens,
        )
        _emit_spend_records(spend_callback, [spend_record])
        return {
            "explanations": explanations,
            "raw_response": raw_response,
            "elapsed_seconds": elapsed_seconds,
            "request_started_at": request_started_at,
            "request_completed_at": request_completed_at,
            "finish_reason": finish_reason,
            "completion_budget": request_completion_budget,
            **usage,
            "spend_ledger": [spend_record],
        }
    except SensitivityKnobError:
        raise
    except Exception as error:
        if getattr(error, "_policybench_spend_persistence_failure", False):
            raise
        request_completed_at = time.time()
        spend_record = _spend_ledger_record(
            call_key=call_key,
            phase="explanation_repair",
            attempt=1,
            status="provider_error",
            scenario=scenario,
            variables=variables,
            model_id=model_id,
            request_started_at=request_started_at,
            request_completed_at=request_completed_at,
            elapsed_seconds=time.perf_counter() - started_at,
            usage=usage,
            error=_format_error(error),
            completion_budget_tokens=request_completion_budget,
            escalated_from_budget_tokens=escalated_from_budget_tokens,
        )
        _emit_spend_records(spend_callback, [spend_record])
        _attach_spend_records(error, [spend_record])
        raise


def _request_explanations_with_budget_escalation(
    scenario: Scenario,
    variables: list[str],
    answers: dict[str, float],
    model_id: str,
    *,
    base_explanations: dict[str, str | None],
    repair_disagreements: list[dict],
    spend_callback: Callable[[list[dict]], None] | None,
) -> dict:
    """Repair explanations, escalating length-truncated missing cells."""
    explanations = dict(base_explanations)
    request_results: list[dict] = []
    exhausted_variables: set[str] = set()
    escalation_count = 0
    request_variables = list(variables)
    budget_override: int | None = None
    escalated_from: int | None = None

    while True:
        try:
            result = _request_explanations_once(
                scenario,
                request_variables,
                {variable: answers[variable] for variable in request_variables},
                model_id,
                spend_callback=spend_callback,
                completion_budget_tokens=budget_override,
                escalated_from_budget_tokens=escalated_from,
            )
        except SensitivityKnobError:
            raise
        except Exception as error:
            prior_spend = [
                record
                for prior_result in request_results
                for record in _spend_records(prior_result)
            ]
            if prior_spend:
                _attach_spend_records(error, prior_spend)
            error._policybench_partial_explanation_round = {
                "explanations": explanations,
                "request_results": request_results,
                "exhausted_variables": exhausted_variables,
                "budget_escalation_count": escalation_count,
            }
            raise

        request_results.append(result)
        explanations = _merge_repair_cells(
            explanations,
            result.get("explanations", {}),
            field="explanation",
            disagreements=repair_disagreements,
        )
        remaining = [
            variable
            for variable in request_variables
            if not str(explanations.get(variable) or "").strip()
        ]
        if result.get("finish_reason") != "length" or not remaining:
            break

        current_budget = result.get("completion_budget")
        if current_budget is None:
            break
        next_budget = next_completion_budget(
            int(current_budget),
            _completion_budget_ceiling(model_id),
        )
        if next_budget is None:
            exhausted_variables.update(remaining)
            break

        logger.warning(
            "Escalating completion budget: model=%s scenario=%s "
            "from_budget=%s to_budget=%s",
            model_id,
            scenario.id,
            current_budget,
            next_budget,
        )
        escalation_count += 1
        if any(
            str(result["explanations"].get(variable) or "").strip()
            for variable in request_variables
        ):
            request_variables = remaining
        budget_override = next_budget
        escalated_from = int(current_budget)

    return {
        "explanations": explanations,
        "request_results": request_results,
        "exhausted_variables": exhausted_variables,
        "budget_escalation_count": escalation_count,
    }


def _request_predictions_once(
    scenario: Scenario,
    variables: list[str],
    model_id: str,
    *,
    repair: bool = False,
    include_explanations: bool = True,
    spend_callback: Callable[[list[dict]], None] | None = None,
    completion_budget_tokens: int | None = None,
    escalated_from_budget_tokens: int | None = None,
) -> dict:
    if _uses_responses_api(model_id):
        messages, request_kwargs = _responses_request_kwargs(
            scenario=scenario,
            variables=variables,
            model_id=model_id,
            repair=repair,
            include_explanations=include_explanations,
        )
        request_fn = responses
    else:
        messages, request_kwargs = _chat_completion_request_kwargs(
            scenario=scenario,
            variables=variables,
            model_id=model_id,
            repair=repair,
            include_explanations=include_explanations,
        )
        request_fn = completion

    if completion_budget_tokens is not None:
        request_kwargs = with_completion_budget(
            request_kwargs,
            completion_budget_tokens,
        )
    request_completion_budget = completion_budget_from_kwargs(request_kwargs)
    spend_records = []
    phase = "repair" if repair else "initial"
    for attempt in range(MAX_ATTEMPTS):
        call_key = f"sync:{uuid4().hex}"
        request_started_at = time.time()
        started_at = time.perf_counter()
        usage: dict = {}
        try:
            response = _run_request_with_wall_timeout(request_fn, request_kwargs)
            elapsed_seconds = time.perf_counter() - started_at
            request_completed_at = time.time()
            if _uses_responses_api(model_id):
                content, tool_calls = _responses_content_and_tool_calls(response)
                function_call = None
            else:
                message = response.choices[0].message
                content = getattr(message, "content", None)
                tool_calls = getattr(message, "tool_calls", None)
                function_call = getattr(message, "function_call", None)
            finish_reason = _response_finish_reason(
                response,
                responses_api=_uses_responses_api(model_id),
                completion_budget_tokens=request_completion_budget,
            )
            raw_response = _serialize_response_payload(
                content=content,
                tool_calls=tool_calls,
                function_call=function_call,
            )
            predictions = extract_predictions(
                content=content,
                variables=variables,
                tool_calls=tool_calls,
                function_call=function_call,
            )
            explanations = extract_explanations(
                content=content,
                variables=variables,
                tool_calls=tool_calls,
                function_call=function_call,
            )
            predictions, explanations = _enforce_explanation_value_contract(
                predictions,
                explanations,
                variables,
            )
            usage = _extract_usage_metadata(
                response,
                model_id,
                messages,
                raw_response or content,
            )
            has_parse_error = any(
                predictions.get(variable) is None for variable in variables
            ) or (
                include_explanations
                and any(
                    not str(explanations.get(variable) or "").strip()
                    for variable in variables
                )
            )
            spend_records.append(
                _spend_ledger_record(
                    call_key=call_key,
                    phase=phase,
                    attempt=attempt + 1,
                    status="parse_error" if has_parse_error else "ok",
                    scenario=scenario,
                    variables=variables,
                    model_id=model_id,
                    request_started_at=request_started_at,
                    request_completed_at=request_completed_at,
                    elapsed_seconds=elapsed_seconds,
                    usage=usage,
                    cache_hit=_response_cache_hit(response),
                    completion_budget_tokens=request_completion_budget,
                    escalated_from_budget_tokens=(
                        escalated_from_budget_tokens if attempt == 0 else None
                    ),
                )
            )
            _emit_spend_records(spend_callback, [spend_records[-1]])
            return {
                "predictions": predictions,
                "explanations": explanations,
                "raw_response": raw_response,
                "elapsed_seconds": elapsed_seconds,
                "request_started_at": request_started_at,
                "request_completed_at": request_completed_at,
                "finish_reason": finish_reason,
                "completion_budget": request_completion_budget,
                "budget_escalation_count": int(
                    escalated_from_budget_tokens is not None
                ),
                **usage,
                "spend_ledger": spend_records,
            }
        except SensitivityKnobError:
            raise
        except Exception as e:
            if getattr(e, "_policybench_spend_persistence_failure", False):
                raise
            request_completed_at = time.time()
            elapsed_seconds = time.perf_counter() - started_at
            spend_records.append(
                _spend_ledger_record(
                    call_key=call_key,
                    phase=phase,
                    attempt=attempt + 1,
                    status="provider_error",
                    scenario=scenario,
                    variables=variables,
                    model_id=model_id,
                    request_started_at=request_started_at,
                    request_completed_at=request_completed_at,
                    elapsed_seconds=elapsed_seconds,
                    usage=usage,
                    error=_format_error(e),
                    completion_budget_tokens=request_completion_budget,
                    escalated_from_budget_tokens=(
                        escalated_from_budget_tokens if attempt == 0 else None
                    ),
                )
            )
            _emit_spend_records(spend_callback, [spend_records[-1]])
            if attempt == MAX_ATTEMPTS - 1 or not _should_retry(e):
                _attach_spend_records(e, spend_records)
                raise
            delay = RETRY_BASE_DELAY * (2**attempt)
            print(f"  Retry {attempt + 1}: {e!r:.60s}... {delay}s")
            time.sleep(delay)

    raise RuntimeError("Request loop exited unexpectedly")


def _request_predictions_with_budget_escalation(
    scenario: Scenario,
    variables: list[str],
    model_id: str,
    *,
    repair: bool,
    include_explanations: bool,
    base_predictions: dict[str, float | None],
    base_explanations: dict[str, str | None],
    repair_disagreements: list[dict],
    spend_callback: Callable[[list[dict]], None] | None,
) -> dict:
    """Run one logical request, escalating only length-truncated misses."""
    predictions = dict(base_predictions)
    explanations = dict(base_explanations)
    request_results: list[dict] = []
    exhausted_variables: set[str] = set()
    escalation_count = 0
    request_variables = list(variables)
    request_is_repair = repair
    budget_override: int | None = None
    escalated_from: int | None = None

    while True:
        try:
            result = _request_predictions_once(
                scenario,
                request_variables,
                model_id,
                repair=request_is_repair,
                include_explanations=include_explanations,
                spend_callback=spend_callback,
                completion_budget_tokens=budget_override,
                escalated_from_budget_tokens=escalated_from,
            )
        except SensitivityKnobError:
            raise
        except Exception as error:
            prior_spend = [
                record
                for prior_result in request_results
                for record in _spend_records(prior_result)
            ]
            if prior_spend:
                _attach_spend_records(error, prior_spend)
            error._policybench_partial_budget_round = {
                "predictions": predictions,
                "explanations": explanations,
                "request_results": request_results,
                "exhausted_variables": exhausted_variables,
                "budget_escalation_count": escalation_count,
            }
            raise

        request_results.append(result)
        predictions = _merge_repair_cells(
            predictions,
            result["predictions"],
            field="prediction",
            disagreements=repair_disagreements,
        )
        explanations = _merge_repair_cells(
            explanations,
            result.get("explanations", {}),
            field="explanation",
            disagreements=repair_disagreements,
        )

        remaining = [
            variable
            for variable in request_variables
            if predictions.get(variable) is None
            or (
                include_explanations
                and not str(explanations.get(variable) or "").strip()
            )
        ]
        if result.get("finish_reason") != "length" or not remaining:
            break

        current_budget = result.get("completion_budget")
        if current_budget is None:
            break
        next_budget = next_completion_budget(
            int(current_budget),
            _completion_budget_ceiling(model_id),
        )
        if next_budget is None:
            exhausted_variables.update(remaining)
            break

        logger.warning(
            "Escalating completion budget: model=%s scenario=%s "
            "from_budget=%s to_budget=%s",
            model_id,
            scenario.id,
            current_budget,
            next_budget,
        )
        escalation_count += 1
        yielded_valid_cell = any(
            result["predictions"].get(variable) is not None
            or (
                include_explanations
                and bool(str(result["explanations"].get(variable) or "").strip())
            )
            for variable in request_variables
        )
        if yielded_valid_cell:
            request_variables = remaining
            request_is_repair = True
        budget_override = next_budget
        escalated_from = int(current_budget)

    return {
        "predictions": predictions,
        "explanations": explanations,
        "request_results": request_results,
        "exhausted_variables": exhausted_variables,
        "budget_escalation_count": escalation_count,
    }


def run_single_no_tools(
    scenario: Scenario,
    variable: str | Iterable[str],
    model_id: str,
    include_explanations: bool = True,
    _allow_chunking: bool = True,
    _spend_callback: Callable[[list[dict]], None] | None = None,
) -> dict:
    """Run a single scenario for one or more variables without tools."""
    variables = _normalize_variables(variable)
    chunk_size = _required_explanation_chunk_size(model_id, include_explanations)
    if _allow_chunking and chunk_size and len(variables) > chunk_size:
        chunk_results = []
        predictions = {}
        explanations = {}
        errors = []
        for chunk in _chunk_variables(variables, chunk_size):
            try:
                chunk_result = run_single_no_tools(
                    scenario,
                    chunk,
                    model_id,
                    include_explanations=include_explanations,
                    _allow_chunking=False,
                    _spend_callback=_spend_callback,
                )
            except SensitivityKnobError:
                raise
            except Exception as error:
                if _is_model_fatal_error(error):
                    _attach_spend_records(
                        error,
                        [
                            record
                            for result in chunk_results
                            for record in _spend_records(result)
                        ],
                    )
                    raise
                chunk_result = _empty_failed_result(chunk, error)
            chunk_results.append(chunk_result)
            predictions.update(chunk_result["predictions"])
            explanations.update(
                {
                    variable: value
                    for variable, value in chunk_result.get("explanations", {}).items()
                    if value is not None
                }
            )
            if chunk_result.get("error"):
                errors.append(chunk_result["error"])

        raw_response = json.dumps(
            {
                "chunked_responses": [
                    {
                        "variables": chunk,
                        "raw_response": result.get("raw_response"),
                    }
                    for chunk, result in zip(
                        _chunk_variables(variables, chunk_size),
                        chunk_results,
                        strict=True,
                    )
                ]
            }
        )
        return {
            "predictions": predictions,
            "explanations": explanations,
            "prediction": predictions[variables[0]] if len(variables) == 1 else None,
            "error": "; ".join(errors) if errors else None,
            "raw_response": raw_response,
            "elapsed_seconds": _sum_optional_field(chunk_results, "elapsed_seconds"),
            "request_started_at": _min_optional_numbers(
                result.get("request_started_at") for result in chunk_results
            ),
            "request_completed_at": _max_optional_numbers(
                result.get("request_completed_at") for result in chunk_results
            ),
            "prompt_tokens": _sum_optional_field(chunk_results, "prompt_tokens"),
            "completion_tokens": _sum_optional_field(
                chunk_results, "completion_tokens"
            ),
            "total_tokens": _sum_optional_field(chunk_results, "total_tokens"),
            "reasoning_tokens": _sum_optional_field(chunk_results, "reasoning_tokens"),
            "cached_prompt_tokens": _sum_optional_field(
                chunk_results, "cached_prompt_tokens"
            ),
            "cache_write_prompt_tokens": _sum_optional_field(
                chunk_results, "cache_write_prompt_tokens"
            ),
            "provider_reported_cost_usd": _sum_optional_field(
                chunk_results, "provider_reported_cost_usd"
            ),
            "reconstructed_cost_usd": _sum_optional_field(
                chunk_results, "reconstructed_cost_usd"
            ),
            "total_cost_usd": _sum_optional_field(chunk_results, "total_cost_usd"),
            "cost_is_estimated": _combined_cost_is_estimated(chunk_results),
            "estimated_cost_usd": _sum_optional_field(
                chunk_results, "estimated_cost_usd"
            ),
            "provider_response_id": _first_non_null(
                result.get("provider_response_id") for result in chunk_results
            ),
            "provider_system_fingerprint": _first_non_null(
                result.get("provider_system_fingerprint") for result in chunk_results
            ),
            "provider_resolved_model": _first_non_null(
                result.get("provider_resolved_model") for result in chunk_results
            ),
            "repair_disagreements": [
                disagreement
                for result in chunk_results
                for disagreement in result.get("repair_disagreements", [])
            ],
            "failure_sources": {
                variable: source
                for result in chunk_results
                for variable, source in result.get("failure_sources", {}).items()
            },
            "budget_escalation_count": sum(
                int(result.get("budget_escalation_count", 0))
                for result in chunk_results
            ),
            "spend_ledger": [
                record for result in chunk_results for record in _spend_records(result)
            ],
        }

    request_results: list[dict] = []
    spend_records: list[dict] = []
    predictions = {variable: None for variable in variables}
    explanations = {variable: None for variable in variables}
    repair_errors = []
    repair_disagreements: list[dict] = []
    exhausted_variables: set[str] = set()
    budget_escalation_count = 0
    request_failed = False

    try:
        initial_round = _request_predictions_with_budget_escalation(
            scenario,
            variables,
            model_id,
            repair=False,
            include_explanations=include_explanations,
            base_predictions=predictions,
            base_explanations=explanations,
            repair_disagreements=repair_disagreements,
            spend_callback=_spend_callback,
        )
    except SensitivityKnobError:
        raise
    except Exception as error:
        partial_round = getattr(error, "_policybench_partial_budget_round", None)
        has_valid_partial = partial_round and any(
            value is not None for value in partial_round["predictions"].values()
        )
        if not has_valid_partial:
            raise
        initial_round = partial_round
        spend_records.extend(_spend_records(error))
        repair_errors.append(_format_error(error))
        request_failed = True
    request_results.extend(initial_round["request_results"])
    if not request_failed:
        spend_records.extend(
            record
            for result in initial_round["request_results"]
            for record in _spend_records(result)
        )
    predictions = initial_round["predictions"]
    explanations = initial_round["explanations"]
    exhausted_variables.update(initial_round["exhausted_variables"])
    budget_escalation_count += initial_round["budget_escalation_count"]

    missing = _missing_variables(predictions)
    missing_explanations = (
        _missing_explanations(explanations, variables) if include_explanations else []
    )
    for _ in range(0 if request_failed else MAX_REPAIR_ROUNDS):
        repair_targets = sorted(
            (set(missing) | set(missing_explanations)) - exhausted_variables
        )
        if not repair_targets:
            break
        try:
            repair_round = _request_predictions_with_budget_escalation(
                scenario,
                repair_targets,
                model_id,
                repair=True,
                include_explanations=include_explanations,
                base_predictions=predictions,
                base_explanations=explanations,
                repair_disagreements=repair_disagreements,
                spend_callback=_spend_callback,
            )
        except SensitivityKnobError:
            raise
        except Exception as error:
            spend_records.extend(_spend_records(error))
            request_failed = True
            partial_round = getattr(
                error,
                "_policybench_partial_budget_round",
                None,
            )
            if partial_round:
                request_results.extend(partial_round["request_results"])
                predictions = partial_round["predictions"]
                explanations = partial_round["explanations"]
                exhausted_variables.update(partial_round["exhausted_variables"])
                budget_escalation_count += partial_round["budget_escalation_count"]
                missing = _missing_variables(predictions)
                missing_explanations = (
                    _missing_explanations(explanations, variables)
                    if include_explanations
                    else []
                )
            repair_errors.append(_format_error(error))
            break
        request_results.extend(repair_round["request_results"])
        spend_records.extend(
            record
            for result in repair_round["request_results"]
            for record in _spend_records(result)
        )
        predictions = repair_round["predictions"]
        explanations = repair_round["explanations"]
        exhausted_variables.update(repair_round["exhausted_variables"])
        budget_escalation_count += repair_round["budget_escalation_count"]
        missing = _missing_variables(predictions)
        missing_explanations = (
            _missing_explanations(explanations, variables)
            if include_explanations
            else []
        )

    if (
        include_explanations
        and not request_failed
        and not missing
        and missing_explanations
    ):
        explanation_answers = {
            variable: predictions[variable]
            for variable in missing_explanations
            if predictions.get(variable) is not None
            and variable not in exhausted_variables
        }
        if explanation_answers:
            try:
                explanation_round = _request_explanations_with_budget_escalation(
                    scenario,
                    list(explanation_answers),
                    explanation_answers,
                    model_id,
                    base_explanations=explanations,
                    repair_disagreements=repair_disagreements,
                    spend_callback=_spend_callback,
                )
                request_results.extend(explanation_round["request_results"])
                spend_records.extend(
                    record
                    for result in explanation_round["request_results"]
                    for record in _spend_records(result)
                )
                explanations = explanation_round["explanations"]
                exhausted_variables.update(explanation_round["exhausted_variables"])
                budget_escalation_count += explanation_round["budget_escalation_count"]
                missing_explanations = _missing_explanations(explanations, variables)
            except SensitivityKnobError:
                raise
            except Exception as error:
                spend_records.extend(_spend_records(error))
                partial_round = getattr(
                    error,
                    "_policybench_partial_explanation_round",
                    None,
                )
                if partial_round:
                    request_results.extend(partial_round["request_results"])
                    explanations = partial_round["explanations"]
                    exhausted_variables.update(partial_round["exhausted_variables"])
                    budget_escalation_count += partial_round["budget_escalation_count"]
                    missing_explanations = _missing_explanations(
                        explanations,
                        variables,
                    )
                repair_errors.append(_format_error(error))

    exhausted_missing = sorted(set(missing) & exhausted_variables)
    ordinary_missing = sorted(set(missing) - exhausted_variables)
    if exhausted_missing:
        repair_errors.append(
            "budget_exhausted_at_ceiling: " + ", ".join(exhausted_missing)
        )
    if ordinary_missing:
        repair_errors.append(
            "Missing predictions after repair: " + ", ".join(ordinary_missing)
        )
    ordinary_missing_explanations = sorted(
        set(missing_explanations) - exhausted_variables
    )
    exhausted_missing_explanations = sorted(
        (set(missing_explanations) & exhausted_variables) - set(missing)
    )
    if include_explanations and exhausted_missing_explanations:
        repair_errors.append(
            "budget_exhausted_at_ceiling (explanation): "
            + ", ".join(exhausted_missing_explanations)
        )
    if include_explanations and ordinary_missing_explanations:
        repair_errors.append(
            "Missing explanations after repair: "
            + ", ".join(ordinary_missing_explanations)
        )

    aggregated = _aggregate_request_results(request_results)
    return {
        "predictions": predictions,
        "explanations": explanations,
        "prediction": predictions[variables[0]] if len(variables) == 1 else None,
        "error": "; ".join(repair_errors) if repair_errors else None,
        "repair_disagreements": repair_disagreements,
        "failure_sources": {
            variable: "budget_exhausted_at_ceiling" for variable in exhausted_missing
        },
        "budget_escalation_count": budget_escalation_count,
        "spend_ledger": spend_records,
        **aggregated,
    }


def _load_existing_rows(
    output_path: str | None,
    scenarios: list[Scenario],
    programs: list[str],
    include_explanations: bool = True,
) -> tuple[list[dict], set[tuple[str, str]]]:
    if not output_path:
        return [], set()

    path = Path(output_path)
    existing = _read_existing_output(path)
    if existing is None:
        return [], set()

    if existing.empty:
        return [], set()

    group_columns = ["model", "scenario_id"]
    completed_keys: set[tuple[str, str]] = set()
    keep_mask = pd.Series(False, index=existing.index)
    expected_programs = {
        scenario.id: set(expand_programs_for_scenario(programs, scenario))
        for scenario in scenarios
    }

    for key, group in existing.groupby(group_columns):
        has_all_programs = set(group["variable"]) >= expected_programs.get(
            key[1],
            set(programs),
        )
        has_infrastructure_error = (
            "error" in group.columns
            and group["error"]
            .fillna("")
            .astype(str)
            .map(is_infrastructure_error_text)
            .any()
        )
        has_explanation_column = not include_explanations or (
            "explanation" in group.columns
        )
        if has_all_programs and has_explanation_column and not has_infrastructure_error:
            completed_keys.add((key[0], key[1]))
            keep_mask.loc[group.index] = True

    retained = existing.loc[keep_mask].copy()
    rows = retained.to_dict("records")
    return rows, completed_keys


def _output_metadata_path(output_path: str | None) -> Path | None:
    if not output_path:
        return None
    return Path(f"{output_path}.meta.json")


def _read_existing_output(path: Path) -> pd.DataFrame | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return None


def _package_file_sha256(filename: str) -> str:
    return hashlib.sha256(Path(__file__).with_name(filename).read_bytes()).hexdigest()


def _response_contract_metadata() -> dict:
    return {
        "prompt_contract_version": PROMPT_CONTRACT_VERSION,
        "answer_function_name": ANSWER_FUNCTION_NAME,
        "explanation_function_name": EXPLANATION_FUNCTION_NAME,
        "response_shape": "outputs.{variable}.{value,explanation}",
        "explanation_value_contract": "terminal explanation value equals numeric value",
        "prompt_template_sha256": _package_file_sha256("prompts.py"),
        "benchmark_spec_sha256": _package_file_sha256("benchmark_specs.json"),
    }


def _serialize_scenario(scenario: Scenario) -> str:
    return json.dumps(
        scenario_to_dict(scenario),
        separators=(",", ":"),
        sort_keys=True,
    )


def _scenario_hash(scenarios: list[Scenario]) -> str:
    scenario_signature = json.dumps(
        [
            {
                "scenario_id": scenario.id,
                "scenario_json": _serialize_scenario(scenario),
            }
            for scenario in scenarios
        ],
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(scenario_signature.encode("utf-8")).hexdigest()


def _build_resume_metadata(
    *,
    task: str,
    scenarios: list[Scenario],
    models: dict[str, str],
    programs: list[str],
    run_id: str | None,
    include_explanations: bool,
    env: dict | None = None,
) -> dict:
    countries = {(scenario.country or "us").lower() for scenario in scenarios}
    return {
        "metadata_version": RESUME_METADATA_VERSION,
        "task": task,
        "run_id": run_id,
        "include_explanations": include_explanations,
        "scenario_count": len(scenarios),
        "scenario_hash": _scenario_hash(scenarios),
        "programs": sorted(programs),
        "models": {name: models[name] for name in sorted(models)},
        "treatment": _treatment_metadata(
            models,
            include_explanations,
            first_scenario_variables=(
                expand_programs_for_scenario(programs, scenarios[0])
                if scenarios
                else None
            ),
            single_output=task == "eval_no_tools_single_output",
            env=env,
        ),
        "policyengine_bundles": policyengine_bundles_for_countries(countries),
        "response_contract": _response_contract_metadata(),
        "completion_budget_escalation": {
            "strategy": "double_on_length_with_missing_payload",
            "default_ceiling": MAX_ESCALATED_COMPLETION_TOKENS,
            "model_ceilings": {
                name: _completion_budget_ceiling(models[name])
                for name in sorted(models)
            },
        },
    }


def _treatment_metadata(
    models: dict[str, str],
    include_explanations: bool,
    *,
    first_scenario_variables: list[str] | None = None,
    single_output: bool = False,
    env: dict | None = None,
) -> dict:
    """Effective per-model serving treatment recorded beside a resumable output.

    A resumed file must not mix rows from different answer contracts,
    tool_choice modes, or chunk sizes: the sensitivity knobs
    (POLICYBENCH_TOOL_CHOICE, POLICYBENCH_CONTRACT_OVERRIDE,
    POLICYBENCH_CHUNK_OVERRIDE) change the request without changing the model
    id, so the resume check compares this block too.
    """
    source = os.environ if env is None else env
    max_repair_rounds = MAX_REPAIR_ROUNDS if env is None else _max_repair_rounds(source)
    treatment = {}
    for name, model_id in sorted(models.items()):
        answer_contract = _answer_contract_for_model(model_id, env=env)
        treatment[name] = {
            "answer_contract": answer_contract,
            "tool_choice_mode": (
                None
                if answer_contract != "tool"
                else (
                    "auto"
                    if source.get("POLICYBENCH_TOOL_CHOICE") == "auto"
                    else "forced"
                )
            ),
            "explanation_chunk_size": _required_explanation_chunk_size(
                model_id,
                include_explanations,
                env=env,
            ),
            "contract_override": source.get("POLICYBENCH_CONTRACT_OVERRIDE"),
            "max_repair_rounds": max_repair_rounds,
            "initial_completion_budget_tokens": _initial_completion_budget_tokens(
                model_id,
                (
                    _first_request_variables(
                        model_id,
                        first_scenario_variables,
                        include_explanations,
                        single_output=single_output,
                        chunk_override=source.get("POLICYBENCH_CHUNK_OVERRIDE"),
                    )
                    if first_scenario_variables is not None
                    else None
                ),
                include_explanations=include_explanations,
            ),
            "thinking": _thinking_configuration(model_id),
            "request_timeout_seconds": _request_timeout_seconds(model_id, env=env),
        }
    return treatment


def _reject_sensitivity_knobs_for_responses(
    model_id: str, env: dict | None = None
) -> None:
    """Refuse the sensitivity knobs on the Responses API transport.

    The Responses builders (initial answer and explanation repair) send the
    forced answer tool only; POLICYBENCH_TOOL_CHOICE=auto and
    POLICYBENCH_CONTRACT_OVERRIDE are implemented for the chat transport alone.
    Failing fast keeps a run from being fingerprinted as auto/JSON while every
    request it sent was forced-tool (policybench#139 tracks the Responses
    equivalents).
    """
    source = os.environ if env is None else env
    knobs = sorted(
        key
        for key in ("POLICYBENCH_TOOL_CHOICE", "POLICYBENCH_CONTRACT_OVERRIDE")
        if source.get(key)
    )
    if knobs and _uses_responses_api(model_id):
        raise SensitivityKnobError(
            f"{model_id} runs on the Responses API transport, which sends the "
            f"forced answer tool only; {', '.join(knobs)} are not implemented "
            "for it (policybench#139). Unset them or choose a chat-transport model."
        )


def _write_resume_metadata(output_path: str | None, metadata: dict) -> None:
    metadata_path = _output_metadata_path(output_path)
    if metadata_path is None:
        return
    runtime_metadata = dict(metadata)
    runtime_metadata["budget_escalation_count"] = count_budget_escalations(
        read_spend_ledger(spend_ledger_path(output_path))
    )
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(runtime_metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _validate_resume_metadata(output_path: str | None, expected: dict) -> None:
    if not output_path:
        return

    path = Path(output_path)
    metadata_path = _output_metadata_path(output_path)
    if metadata_path is None:
        return

    ledger_path = spend_ledger_path(path)
    has_output = path.exists() and path.stat().st_size > 0
    has_ledger = ledger_path.exists() and ledger_path.stat().st_size > 0
    if not has_output and not has_ledger:
        return
    if not metadata_path.exists():
        raise ValueError(
            f"Existing output or spend ledger at {path} is missing its resume "
            "metadata sidecar "
            f"at {metadata_path}. Delete the stale output or use a fresh path."
        )

    existing = json.loads(metadata_path.read_text(encoding="utf-8"))
    mismatches = []
    for key in (
        "metadata_version",
        "task",
        "run_id",
        "include_explanations",
        "scenario_count",
        "scenario_hash",
        "programs",
        "models",
        "treatment",
        "policyengine_bundles",
        "response_contract",
        "completion_budget_escalation",
    ):
        if existing.get(key) != expected.get(key):
            mismatches.append(key)

    if mismatches:
        mismatch_list = ", ".join(mismatches)
        raise ValueError(
            f"Existing output at {path} does not match the requested benchmark "
            f"settings ({mismatch_list}). Use a fresh output path instead of "
            "resuming this file."
        )


def _save_checkpoint(
    output_path: str | None,
    rows: list[dict],
    metadata: dict,
) -> None:
    if not output_path:
        return
    path = Path(output_path)
    if not rows:
        if path.exists():
            path.unlink()
        _write_resume_metadata(output_path, metadata)
        return
    pd.DataFrame(rows).to_csv(path, index=False)
    _write_resume_metadata(output_path, metadata)


def _persist_spend_records(
    output_path: str | None,
    source,
    *,
    model_name: str,
    model_id: str,
    scenario_id: str,
    run_id: str | None,
) -> None:
    if not output_path:
        return
    records = _spend_records(source)
    if not records:
        return
    for record in records:
        record.setdefault("model", model_name)
        record.setdefault("model_id", model_id)
        record.setdefault("scenario_id", scenario_id)
        if run_id is not None:
            record.setdefault("run_id", run_id)
    upsert_spend_ledger(spend_ledger_path(output_path), records)


def _make_spend_callback(
    output_path: str | None,
    *,
    model_name: str,
    model_id: str,
    scenario_id: str,
    run_id: str | None,
) -> Callable[[list[dict]], None] | None:
    if not output_path:
        return None

    def persist(records: list[dict]) -> None:
        _persist_spend_records(
            output_path,
            {"spend_ledger": records},
            model_name=model_name,
            model_id=model_id,
            scenario_id=scenario_id,
            run_id=run_id,
        )

    return persist


def _load_existing_single_output_rows(
    output_path: str | None,
    include_explanations: bool = True,
) -> tuple[list[dict], set[tuple[str, str, str]]]:
    if not output_path:
        return [], set()

    existing = _read_existing_output(Path(output_path))
    if existing is None:
        return [], set()
    required_columns = {"model", "scenario_id", "variable", "prediction"}
    if not required_columns.issubset(existing.columns):
        return [], set()

    infrastructure_error_mask = (
        existing["error"].fillna("").astype(str).map(is_infrastructure_error_text)
        if "error" in existing.columns
        else pd.Series(False, index=existing.index)
    )
    if include_explanations and "explanation" not in existing.columns:
        return [], set()

    keep_mask = ~infrastructure_error_mask
    retained = existing.loc[keep_mask].copy()
    completed_keys = {
        (str(row.model), str(row.scenario_id), str(row.variable))
        for row in retained.itertuples()
    }
    return retained.to_dict("records"), completed_keys


def run_no_tools_eval(
    scenarios: list[Scenario],
    models: dict[str, str] | None = None,
    programs: list[str] | None = None,
    output_path: str | None = None,
    run_id: str | None = None,
    include_explanations: bool = True,
) -> pd.DataFrame:
    """Run the AI-alone evaluation across all models.

    If output_path is provided, saves incrementally every
    ``CHECKPOINT_EVERY_ROWS`` rows.

    Returns DataFrame with columns:
        model, scenario_id, variable, prediction, explanation, failure_source,
        raw_response, error, elapsed_seconds, prompt_tokens, completion_tokens,
        total_tokens, reasoning_tokens, cached_prompt_tokens,
        cache_write_prompt_tokens, estimated_cost_usd
    """
    if models is None:
        models = MODELS
    if programs is None:
        programs = PROGRAMS

    for model_id in models.values():
        _reject_sensitivity_knobs_for_responses(model_id)

    resume_metadata = _build_resume_metadata(
        task="eval_no_tools_batch",
        scenarios=scenarios,
        models=models,
        programs=programs,
        run_id=run_id,
        include_explanations=include_explanations,
    )
    _validate_resume_metadata(output_path, resume_metadata)
    _write_resume_metadata(output_path, resume_metadata)
    all_rows, completed = _load_existing_rows(
        output_path,
        scenarios,
        programs,
        include_explanations=include_explanations,
    )
    total = len(models) * len(scenarios)
    done = len(completed)

    for model_name, model_id in models.items():
        model_fatal = False
        for scenario in scenarios:
            key = (model_name, scenario.id)
            if key in completed:
                continue
            scenario_programs = expand_programs_for_scenario(programs, scenario)
            try:
                result = run_single_no_tools(
                    scenario,
                    scenario_programs,
                    model_id,
                    include_explanations=include_explanations,
                    _spend_callback=_make_spend_callback(
                        output_path,
                        model_name=model_name,
                        model_id=model_id,
                        scenario_id=scenario.id,
                        run_id=run_id,
                    ),
                )
                _persist_spend_records(
                    output_path,
                    result,
                    model_name=model_name,
                    model_id=model_id,
                    scenario_id=scenario.id,
                    run_id=run_id,
                )
                error = result.get("error")
                if _is_fatal_error_text(error):
                    model_fatal = True
                    print(
                        f"  Stopping {model_name} due to fatal error; "
                        "unattempted rows will be retried on resume."
                    )
                    if output_path:
                        _save_checkpoint(output_path, all_rows, resume_metadata)
                    break
                if is_retryable_provider_error_text(error):
                    if output_path:
                        _save_checkpoint(output_path, all_rows, resume_metadata)
                    raise RuntimeError(error)
            except SensitivityKnobError:
                raise
            except Exception as e:
                _persist_spend_records(
                    output_path,
                    e,
                    model_name=model_name,
                    model_id=model_id,
                    scenario_id=scenario.id,
                    run_id=run_id,
                )
                error = _format_error(e)
                print(f"  ERROR [{model_name}] {scenario.id}: {error}")
                if _is_model_fatal_error(e):
                    model_fatal = True
                    print(
                        f"  Stopping {model_name} due to fatal error; "
                        "unattempted rows will be retried on resume."
                    )
                    if output_path:
                        _save_checkpoint(output_path, all_rows, resume_metadata)
                    break
                if _is_retryable_provider_error(e):
                    if output_path:
                        _save_checkpoint(output_path, all_rows, resume_metadata)
                    raise
                result = {
                    "predictions": {variable: None for variable in scenario_programs},
                    "explanations": {variable: None for variable in scenario_programs},
                    "raw_response": None,
                    "error": error,
                    "elapsed_seconds": None,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                    "reasoning_tokens": None,
                    "cached_prompt_tokens": None,
                    "cache_write_prompt_tokens": None,
                    "provider_reported_cost_usd": None,
                    "reconstructed_cost_usd": None,
                    "total_cost_usd": None,
                    "cost_is_estimated": None,
                    "estimated_cost_usd": None,
                    "failure_sources": {},
                    "budget_escalation_count": 0,
                }

            batch_size = len(scenario_programs)
            call_id = ":".join(
                [part for part in [run_id, model_name, scenario.id] if part is not None]
            )
            elapsed_seconds = result.get("elapsed_seconds")
            prompt_tokens = result.get("prompt_tokens")
            completion_tokens = result.get("completion_tokens")
            total_tokens = result.get("total_tokens")
            reasoning_tokens = result.get("reasoning_tokens")
            cached_prompt_tokens = result.get("cached_prompt_tokens")
            cache_write_prompt_tokens = result.get("cache_write_prompt_tokens")
            provider_reported_cost_usd = result.get("provider_reported_cost_usd")
            reconstructed_cost_usd = result.get("reconstructed_cost_usd")
            total_cost_usd = result.get("total_cost_usd")
            cost_is_estimated = result.get("cost_is_estimated")
            estimated_cost_usd = result.get("estimated_cost_usd")
            for variable in scenario_programs:
                prediction = result["predictions"].get(variable)
                explanation = result.get("explanations", {}).get(variable)
                all_rows.append(
                    {
                        **({"run_id": run_id} if run_id is not None else {}),
                        "call_id": call_id,
                        "model": model_name,
                        "scenario_id": scenario.id,
                        "variable": variable,
                        "prediction": prediction,
                        "explanation": explanation,
                        "failure_source": result.get("failure_sources", {}).get(
                            variable
                        ),
                        "raw_response": result["raw_response"],
                        "error": error,
                        "elapsed_seconds": (
                            elapsed_seconds / batch_size
                            if elapsed_seconds is not None
                            else None
                        ),
                        # Absolute epoch bounds of the response's provider
                        # call(s); shared verbatim by every row in the batch so
                        # wall-clock spans can be derived downstream (#80).
                        "request_started_at": result.get("request_started_at"),
                        "request_completed_at": result.get("request_completed_at"),
                        "prompt_tokens": (
                            prompt_tokens / batch_size
                            if prompt_tokens is not None
                            else None
                        ),
                        "completion_tokens": (
                            completion_tokens / batch_size
                            if completion_tokens is not None
                            else None
                        ),
                        "total_tokens": (
                            total_tokens / batch_size
                            if total_tokens is not None
                            else None
                        ),
                        "reasoning_tokens": (
                            reasoning_tokens / batch_size
                            if reasoning_tokens is not None
                            else None
                        ),
                        "cached_prompt_tokens": (
                            cached_prompt_tokens / batch_size
                            if cached_prompt_tokens is not None
                            else None
                        ),
                        "cache_write_prompt_tokens": (
                            cache_write_prompt_tokens / batch_size
                            if cache_write_prompt_tokens is not None
                            else None
                        ),
                        "provider_reported_cost_usd": (
                            provider_reported_cost_usd / batch_size
                            if provider_reported_cost_usd is not None
                            else None
                        ),
                        "reconstructed_cost_usd": (
                            reconstructed_cost_usd / batch_size
                            if reconstructed_cost_usd is not None
                            else None
                        ),
                        "total_cost_usd": (
                            total_cost_usd / batch_size
                            if total_cost_usd is not None
                            else None
                        ),
                        "cost_is_estimated": cost_is_estimated,
                        "estimated_cost_usd": (
                            estimated_cost_usd / batch_size
                            if estimated_cost_usd is not None
                            else None
                        ),
                        "provider_response_id": result.get("provider_response_id"),
                        "provider_system_fingerprint": result.get(
                            "provider_system_fingerprint"
                        ),
                        "provider_resolved_model": result.get(
                            "provider_resolved_model"
                        ),
                    }
                )

            completed.add(key)
            done += 1
            if done % CHECKPOINT_EVERY_ROWS == 0:
                print(f"  Progress: {done}/{total} ({done * 100 // total}%)")
                if output_path:
                    _save_checkpoint(output_path, all_rows, resume_metadata)
            if model_fatal:
                break

    df = pd.DataFrame(all_rows)
    if output_path:
        _save_checkpoint(output_path, all_rows, resume_metadata)
    return df


def run_no_tools_single_output_eval(
    scenarios: list[Scenario],
    models: dict[str, str] | None = None,
    programs: list[str] | None = None,
    output_path: str | None = None,
    run_id: str | None = None,
    include_explanations: bool = True,
) -> pd.DataFrame:
    """Run AI-alone evaluation one output at a time."""
    if models is None:
        models = MODELS
    if programs is None:
        programs = PROGRAMS

    for model_id in models.values():
        _reject_sensitivity_knobs_for_responses(model_id)

    resume_metadata = _build_resume_metadata(
        task="eval_no_tools_single_output",
        scenarios=scenarios,
        models=models,
        programs=programs,
        run_id=run_id,
        include_explanations=include_explanations,
    )
    _validate_resume_metadata(output_path, resume_metadata)
    _write_resume_metadata(output_path, resume_metadata)
    all_rows, completed = _load_existing_single_output_rows(
        output_path,
        include_explanations=include_explanations,
    )
    scenario_programs_by_id = {
        scenario.id: expand_programs_for_scenario(programs, scenario)
        for scenario in scenarios
    }
    total = len(models) * sum(
        len(scenario_programs) for scenario_programs in scenario_programs_by_id.values()
    )
    done = len(completed)

    for model_name, model_id in models.items():
        model_fatal = False
        for scenario in scenarios:
            for variable in scenario_programs_by_id[scenario.id]:
                key = (model_name, scenario.id, variable)
                if key in completed:
                    continue
                try:
                    result = run_single_no_tools(
                        scenario,
                        variable,
                        model_id,
                        include_explanations=include_explanations,
                        _spend_callback=_make_spend_callback(
                            output_path,
                            model_name=model_name,
                            model_id=model_id,
                            scenario_id=scenario.id,
                            run_id=run_id,
                        ),
                    )
                    _persist_spend_records(
                        output_path,
                        result,
                        model_name=model_name,
                        model_id=model_id,
                        scenario_id=scenario.id,
                        run_id=run_id,
                    )
                    error = result.get("error")
                    if _is_fatal_error_text(error):
                        model_fatal = True
                        print(
                            f"  Stopping {model_name} due to fatal error; "
                            "unattempted rows will be retried on resume."
                        )
                        if output_path:
                            _save_checkpoint(output_path, all_rows, resume_metadata)
                        break
                    if is_retryable_provider_error_text(error):
                        if output_path:
                            _save_checkpoint(output_path, all_rows, resume_metadata)
                        raise RuntimeError(error)
                except SensitivityKnobError:
                    raise
                except Exception as e:
                    _persist_spend_records(
                        output_path,
                        e,
                        model_name=model_name,
                        model_id=model_id,
                        scenario_id=scenario.id,
                        run_id=run_id,
                    )
                    error = _format_error(e)
                    print(f"  ERROR [{model_name}] {scenario.id} {variable}: {error}")
                    if _is_model_fatal_error(e):
                        model_fatal = True
                        print(
                            f"  Stopping {model_name} due to fatal error; "
                            "unattempted rows will be retried on resume."
                        )
                        if output_path:
                            _save_checkpoint(output_path, all_rows, resume_metadata)
                        break
                    if _is_retryable_provider_error(e):
                        if output_path:
                            _save_checkpoint(output_path, all_rows, resume_metadata)
                        raise
                    result = {
                        "predictions": {variable: None},
                        "explanations": {variable: None},
                        "raw_response": None,
                        "error": error,
                        "elapsed_seconds": None,
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "total_tokens": None,
                        "reasoning_tokens": None,
                        "cached_prompt_tokens": None,
                        "cache_write_prompt_tokens": None,
                        "provider_reported_cost_usd": None,
                        "reconstructed_cost_usd": None,
                        "total_cost_usd": None,
                        "cost_is_estimated": None,
                        "estimated_cost_usd": None,
                        "provider_response_id": None,
                        "provider_system_fingerprint": None,
                        "provider_resolved_model": None,
                        "failure_sources": {},
                        "budget_escalation_count": 0,
                    }

                call_id = ":".join(
                    [
                        part
                        for part in [run_id, model_name, scenario.id, variable]
                        if part is not None
                    ]
                )
                all_rows.append(
                    {
                        **({"run_id": run_id} if run_id is not None else {}),
                        "call_id": call_id,
                        "model": model_name,
                        "scenario_id": scenario.id,
                        "variable": variable,
                        "prediction": result["predictions"].get(variable),
                        "explanation": result.get("explanations", {}).get(variable),
                        "failure_source": result.get("failure_sources", {}).get(
                            variable
                        ),
                        "raw_response": result["raw_response"],
                        "error": error,
                        "elapsed_seconds": result.get("elapsed_seconds"),
                        "request_started_at": result.get("request_started_at"),
                        "request_completed_at": result.get("request_completed_at"),
                        "prompt_tokens": result.get("prompt_tokens"),
                        "completion_tokens": result.get("completion_tokens"),
                        "total_tokens": result.get("total_tokens"),
                        "reasoning_tokens": result.get("reasoning_tokens"),
                        "cached_prompt_tokens": result.get("cached_prompt_tokens"),
                        "cache_write_prompt_tokens": result.get(
                            "cache_write_prompt_tokens"
                        ),
                        "provider_reported_cost_usd": result.get(
                            "provider_reported_cost_usd"
                        ),
                        "reconstructed_cost_usd": result.get("reconstructed_cost_usd"),
                        "total_cost_usd": result.get("total_cost_usd"),
                        "cost_is_estimated": result.get("cost_is_estimated"),
                        "estimated_cost_usd": result.get("estimated_cost_usd"),
                        "provider_response_id": result.get("provider_response_id"),
                        "provider_system_fingerprint": result.get(
                            "provider_system_fingerprint"
                        ),
                        "provider_resolved_model": result.get(
                            "provider_resolved_model"
                        ),
                    }
                )

                completed.add(key)
                done += 1
                if done % CHECKPOINT_EVERY_ROWS == 0:
                    print(f"  Progress: {done}/{total} ({done * 100 // total}%)")
                    if output_path:
                        _save_checkpoint(output_path, all_rows, resume_metadata)

            if model_fatal:
                break
        if model_fatal:
            continue

    df = pd.DataFrame(all_rows)
    if output_path:
        _save_checkpoint(output_path, all_rows, resume_metadata)
    return df


def run_repeated_no_tools_eval(
    scenarios: list[Scenario],
    repeats: int,
    output_dir: str,
    models: dict[str, str] | None = None,
    programs: list[str] | None = None,
    include_explanations: bool = True,
    single_output: bool = False,
) -> pd.DataFrame:
    """Run repeated AI-alone evaluations, saving one artifact per run."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    frames = []
    for run_index in range(repeats):
        run_id = f"run_{run_index:03d}"
        run_output_path = output_path / f"{run_id}.csv"
        print(f"=== Starting {run_id} ===")
        runner = run_no_tools_single_output_eval if single_output else run_no_tools_eval
        frame = runner(
            scenarios,
            models=models,
            programs=programs,
            output_path=str(run_output_path),
            run_id=run_id,
            include_explanations=include_explanations,
        )
        if "run_id" not in frame.columns:
            frame = frame.copy()
            frame["run_id"] = run_id
            frame.to_csv(run_output_path, index=False)
        frames.append(frame)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_repeated_predictions(runs_dir: str) -> pd.DataFrame:
    """Load per-run prediction CSVs from a directory into one DataFrame."""
    runs_path = Path(runs_dir)
    files = sorted(runs_path.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No run CSVs found in {runs_path}")

    frames = []
    for path in files:
        frame = pd.read_csv(path)
        if "run_id" not in frame.columns:
            frame = frame.copy()
            frame["run_id"] = path.stem
        frames.append(frame)

    return pd.concat(frames, ignore_index=True)
