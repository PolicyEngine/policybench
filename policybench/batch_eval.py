"""Batch-API evaluation: identical requests to the sync path at ~50% cost.

Anthropic, OpenAI, and Gemini expose async batch endpoints at half their
synchronous prices. This module submits the same request bodies the sync
harness builds (``eval_no_tools``), polls until the provider finishes, and
writes the same chunk CSVs the chunked runner produces — so resume, retries,
merging, scoring, the runstore, and the dashboard export all work unchanged.

Semantics that differ from sync mode, by design:

- ``elapsed_seconds`` / ``request_started_at`` / ``request_completed_at`` are
  empty on batch rows: a batch round-trip includes provider queue time, which
  is not model latency. Models evaluated in batch mode show no latency on the
  leaderboard rather than a misleading one. Batch turnaround is recorded in
  the run's ``batches/`` state files.
- Cost columns are reconstructed from token usage at standard synchronous
  rates (litellm's price map plus ``PRICE_OVERRIDES_PER_1M``), matching the
  leaderboard's comparison basis. Actual spend is ~half of the reported
  figure; the state file records that the run used the batch endpoint.

xAI and DeepSeek have no batch APIs; use the sync chunked runner for them.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, Iterator, Protocol

import pandas as pd

from policybench.eval_no_tools import (
    MAX_REPAIR_ROUNDS,
    _chat_completion_request_kwargs,
    _chunk_variables,
    _enforce_explanation_value_contract,
    _reconstruct_token_cost,
    _required_explanation_chunk_size,
    _responses_request_kwargs,
    _serialize_response_payload,
    _uses_responses_api,
    extract_explanations,
    extract_predictions,
)
from policybench.scenarios import Scenario
from policybench.spec import expand_programs_for_scenario

BATCH_STATE_DIRNAME = "batches"
DEFAULT_POLL_SECONDS = 30
DEFAULT_MAX_WAIT_SECONDS = 4 * 60 * 60


@dataclass
class BatchUnit:
    """One provider request: a scenario and the variable chunk it asks for."""

    scenario_id: str
    variables: list[str]
    chunk_index: int
    repair: bool = False

    @property
    def custom_id(self) -> str:
        # Anthropic custom_ids allow [a-zA-Z0-9_-], max 64 chars. Variable
        # names are too long to embed, so the state manifest carries the
        # decode table and the id stays structural.
        prefix = "r" if self.repair else "u"
        return f"{self.scenario_id}__{prefix}{self.chunk_index:03d}"


@dataclass
class NormalizedResult:
    """Provider-agnostic view of one batch result entry."""

    custom_id: str
    content: str | None = None
    tool_calls: list | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_prompt_tokens: int | None = None
    cache_write_prompt_tokens: int | None = None
    provider_response_id: str | None = None
    provider_resolved_model: str | None = None
    error: str | None = None


def _tool_call_shim(name: str, arguments: str):
    """Minimal object with the attributes the sync extractors read."""
    return SimpleNamespace(
        function=SimpleNamespace(name=name, arguments=arguments),
        id=None,
        type="function",
    )


class BatchProviderAdapter(Protocol):
    """One provider's batch endpoint behind a uniform surface."""

    provider: str

    def supports(self, model_id: str) -> bool: ...

    def build_request_body(
        self, scenario: Scenario, unit: BatchUnit, model_id: str
    ) -> dict: ...

    def submit(self, requests: list[tuple[str, dict]], model_id: str) -> str: ...

    def status(self, batch_id: str) -> str:
        """Return "in_progress", "ended", or "failed"."""
        ...

    def results(self, batch_id: str) -> Iterator[NormalizedResult]: ...


class AnthropicBatchAdapter:
    """Anthropic Message Batches (JSON request array, results as JSONL).

    Request bodies are built from the sync path's OpenAI-format kwargs and
    translated to Messages-API params, so a batch-run model sees the same
    prompt, the same forced tool call, and the same token ceiling as a
    sync-run one.
    """

    provider = "anthropic"

    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def supports(self, model_id: str) -> bool:
        return model_id.startswith("claude-")

    def build_request_body(
        self, scenario: Scenario, unit: BatchUnit, model_id: str
    ) -> dict:
        _, kwargs = _chat_completion_request_kwargs(
            scenario=scenario,
            variables=unit.variables,
            model_id=model_id,
            repair=unit.repair,
            include_explanations=True,
        )
        return _openai_kwargs_to_anthropic_params(kwargs)

    def submit(self, requests: list[tuple[str, dict]], model_id: str) -> str:
        batch = self.client.messages.batches.create(
            requests=[
                {"custom_id": custom_id, "params": params}
                for custom_id, params in requests
            ]
        )
        return batch.id

    def status(self, batch_id: str) -> str:
        batch = self.client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            return "ended"
        if batch.processing_status in ("canceling", "canceled"):
            return "failed"
        return "in_progress"

    def results(self, batch_id: str) -> Iterator[NormalizedResult]:
        for entry in self.client.messages.batches.results(batch_id):
            yield _normalize_anthropic_entry(entry)


def _openai_kwargs_to_anthropic_params(kwargs: dict) -> dict:
    """Translate the sync path's litellm kwargs into Messages-API params.

    Only the shapes the no-tools harness produces are handled: a single user
    message, one forced function tool, and a completion-token ceiling. A new
    request feature must be added here and covered by the parity test before
    batch runs may use it.
    """
    params: dict = {
        "model": kwargs["model"],
        "max_tokens": kwargs["max_completion_tokens"],
        "messages": [
            {"role": message["role"], "content": message["content"]}
            for message in kwargs["messages"]
        ],
    }
    tools = kwargs.get("tools") or []
    if tools:
        params["tools"] = [
            {
                "name": tool["function"]["name"],
                "description": tool["function"].get("description", ""),
                "input_schema": tool["function"]["parameters"],
            }
            for tool in tools
        ]
    tool_choice = kwargs.get("tool_choice")
    if isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
        params["tool_choice"] = {
            "type": "tool",
            "name": tool_choice["function"]["name"],
        }
    unsupported = set(kwargs) - {
        "model",
        "messages",
        "max_completion_tokens",
        "tools",
        "tool_choice",
        "caching",
        "timeout",
    }
    if unsupported:
        raise ValueError(
            "Sync request uses parameters the batch translation does not "
            f"cover yet: {sorted(unsupported)}. Extend "
            "_openai_kwargs_to_anthropic_params and its parity test."
        )
    return params


def _normalize_anthropic_entry(entry) -> NormalizedResult:
    result = entry.result
    if result.type != "succeeded":
        error = getattr(result, "error", None)
        detail = getattr(error, "message", None) or getattr(error, "type", None)
        return NormalizedResult(
            custom_id=entry.custom_id,
            error=f"batch_{result.type}: {detail or 'no detail'}",
        )
    message = result.message
    text_parts: list[str] = []
    tool_calls: list = []
    for block in message.content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text_parts.append(block.text)
        elif block_type == "tool_use":
            tool_calls.append(_tool_call_shim(block.name, json.dumps(block.input)))
    usage = message.usage
    uncached_input_tokens = getattr(usage, "input_tokens", None)
    cached_input_tokens = getattr(usage, "cache_read_input_tokens", None)
    cache_write_tokens = getattr(usage, "cache_creation_input_tokens", None)
    prompt_tokens = None
    if uncached_input_tokens is not None:
        # Anthropic reports uncached input separately from cache reads/writes;
        # normalize to the inclusive prompt-token convention used elsewhere.
        prompt_tokens = (
            uncached_input_tokens
            + (cached_input_tokens or 0)
            + (cache_write_tokens or 0)
        )
    return NormalizedResult(
        custom_id=entry.custom_id,
        content="\n".join(text_parts) or None,
        tool_calls=tool_calls or None,
        prompt_tokens=prompt_tokens,
        completion_tokens=getattr(usage, "output_tokens", None),
        cached_prompt_tokens=cached_input_tokens,
        cache_write_prompt_tokens=cache_write_tokens,
        provider_response_id=getattr(message, "id", None),
        provider_resolved_model=getattr(message, "model", None),
    )


class OpenAIBatchAdapter:
    """OpenAI Batch API over the responses endpoint the gpt-5.x path uses.

    OpenAI batches take a JSONL file where each line carries a custom_id and
    a raw request body for the target endpoint. The harness's gpt-5.x models
    go through ``litellm.responses``, so bodies are built by the same
    ``_responses_request_kwargs`` used sync.
    """

    provider = "openai"
    endpoint = "/v1/responses"

    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import openai

            self._client = openai.OpenAI()
        return self._client

    def supports(self, model_id: str) -> bool:
        return _uses_responses_api(model_id)

    def build_request_body(
        self, scenario: Scenario, unit: BatchUnit, model_id: str
    ) -> dict:
        _, kwargs = _responses_request_kwargs(
            scenario=scenario,
            variables=unit.variables,
            model_id=model_id,
            repair=unit.repair,
            include_explanations=True,
        )
        kwargs.pop("timeout", None)
        connection_keys = {
            "api_base",
            "api_key",
            "base_url",
            "custom_llm_provider",
        }
        leaked = connection_keys & kwargs.keys()
        if leaked:
            raise ValueError(
                "Provider connection settings must never enter a batch body: "
                f"{', '.join(sorted(leaked))}"
            )
        return kwargs

    def submit(self, requests: list[tuple[str, dict]], model_id: str) -> str:
        lines = "\n".join(
            json.dumps(
                {
                    "custom_id": custom_id,
                    "method": "POST",
                    "url": self.endpoint,
                    "body": body,
                }
            )
            for custom_id, body in requests
        )
        batch_file = self.client.files.create(
            file=("policybench_batch.jsonl", lines.encode("utf-8")),
            purpose="batch",
        )
        batch = self.client.batches.create(
            input_file_id=batch_file.id,
            endpoint=self.endpoint,
            completion_window="24h",
        )
        return batch.id

    def status(self, batch_id: str) -> str:
        batch = self.client.batches.retrieve(batch_id)
        if batch.status == "completed":
            return "ended"
        if batch.status in ("failed", "expired", "cancelled", "cancelling"):
            return "failed"
        return "in_progress"

    def results(self, batch_id: str) -> Iterator[NormalizedResult]:
        batch = self.client.batches.retrieve(batch_id)
        raw = self.client.files.content(batch.output_file_id).text
        for line in raw.splitlines():
            if line.strip():
                yield _normalize_openai_entry(json.loads(line))


def _normalize_openai_entry(entry: dict) -> NormalizedResult:
    custom_id = entry.get("custom_id", "")
    response = entry.get("response") or {}
    if entry.get("error") or response.get("status_code", 200) >= 400:
        detail = entry.get("error") or response.get("body")
        return NormalizedResult(
            custom_id=custom_id, error=f"batch_errored: {json.dumps(detail)[:200]}"
        )
    body = response.get("body") or {}
    text_parts: list[str] = []
    tool_calls: list = []
    for item in body.get("output", []):
        item_type = item.get("type")
        if item_type == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    text_parts.append(part.get("text", ""))
        elif item_type == "function_call":
            tool_calls.append(
                _tool_call_shim(item.get("name", ""), item.get("arguments", "{}"))
            )
    usage = body.get("usage") or {}
    output_details = usage.get("output_tokens_details") or {}
    input_details = usage.get("input_tokens_details") or {}
    return NormalizedResult(
        custom_id=custom_id,
        content="\n".join(text_parts) or None,
        tool_calls=tool_calls or None,
        prompt_tokens=usage.get("input_tokens"),
        completion_tokens=usage.get("output_tokens"),
        reasoning_tokens=output_details.get("reasoning_tokens"),
        cached_prompt_tokens=input_details.get("cached_tokens"),
        cache_write_prompt_tokens=input_details.get("cache_write_tokens")
        or input_details.get("cache_creation_tokens"),
        provider_response_id=body.get("id"),
        provider_resolved_model=body.get("model"),
    )


class GeminiBatchAdapter:
    """Gemini developer-API inline batches via google-genai.

    The harness's ``gemini/`` models use the developer API, whose batch mode
    accepts inline requests (no GCS staging). Marked experimental until the
    first paid gemini batch run validates it end to end (#85).
    """

    provider = "gemini"

    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client()
        return self._client

    def supports(self, model_id: str) -> bool:
        return model_id.startswith("gemini/")

    def build_request_body(
        self, scenario: Scenario, unit: BatchUnit, model_id: str
    ) -> dict:
        _, kwargs = _chat_completion_request_kwargs(
            scenario=scenario,
            variables=unit.variables,
            model_id=model_id,
            repair=unit.repair,
            include_explanations=True,
        )
        prompt = kwargs["messages"][0]["content"]
        return {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "config": {
                "max_output_tokens": kwargs["max_completion_tokens"],
                "response_mime_type": "application/json",
            },
        }

    def submit(self, requests: list[tuple[str, dict]], model_id: str) -> str:
        model = model_id.split("/", 1)[1]
        job = self.client.batches.create(
            model=model,
            src=[
                {**body, "metadata": {"custom_id": custom_id}}
                for custom_id, body in requests
            ],
        )
        return job.name

    def status(self, batch_id: str) -> str:
        job = self.client.batches.get(name=batch_id)
        state = str(getattr(job, "state", ""))
        if "SUCCEEDED" in state:
            return "ended"
        if any(word in state for word in ("FAILED", "CANCELLED", "EXPIRED")):
            return "failed"
        return "in_progress"

    def results(self, batch_id: str) -> Iterator[NormalizedResult]:
        job = self.client.batches.get(name=batch_id)
        for inline in job.dest.inlined_responses:
            metadata = getattr(inline, "metadata", None) or {}
            custom_id = metadata.get("custom_id", "")
            if getattr(inline, "error", None):
                yield NormalizedResult(
                    custom_id=custom_id,
                    error=f"batch_errored: {inline.error}",
                )
                continue
            response = inline.response
            text = getattr(response, "text", None)
            usage = getattr(response, "usage_metadata", None)
            yield NormalizedResult(
                custom_id=custom_id,
                content=text,
                prompt_tokens=getattr(usage, "prompt_token_count", None),
                completion_tokens=getattr(usage, "candidates_token_count", None),
                reasoning_tokens=getattr(usage, "thoughts_token_count", None),
                provider_resolved_model=getattr(response, "model_version", None),
            )


ADAPTERS: tuple[type, ...] = (
    AnthropicBatchAdapter,
    OpenAIBatchAdapter,
    GeminiBatchAdapter,
)


def adapter_for_model(model_id: str, adapters: Iterable | None = None):
    """Return the adapter that owns ``model_id``, or None (sync-only model)."""
    candidates = list(adapters) if adapters is not None else [a() for a in ADAPTERS]
    for adapter in candidates:
        if adapter.supports(model_id):
            return adapter
    return None


@dataclass
class BatchRunState:
    """Persisted per-round record so interrupted runs re-poll, not resubmit."""

    model: str
    round_index: int
    batch_id: str
    provider: str
    submitted_at: float
    units: dict[str, dict] = field(default_factory=dict)
    completed_at: float | None = None

    def path(self, run_dir: Path) -> Path:
        return (
            run_dir / BATCH_STATE_DIRNAME / f"{self.model}.round{self.round_index}.json"
        )

    def save(self, run_dir: Path) -> None:
        path = self.path(run_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.__dict__, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, run_dir: Path, model: str, round_index: int):
        path = run_dir / BATCH_STATE_DIRNAME / f"{model}.round{round_index}.json"
        if not path.exists():
            return None
        return cls(**json.loads(path.read_text(encoding="utf-8")))


def build_units(
    scenarios: list[Scenario],
    programs: list[str],
    model_id: str,
    completed_keys: set[tuple[str, str]] | None = None,
) -> list[BatchUnit]:
    """Expand scenarios into per-request units, mirroring sync chunking."""
    completed = completed_keys or set()
    chunk_size = _required_explanation_chunk_size(model_id, True)
    units: list[BatchUnit] = []
    for scenario in scenarios:
        expanded = expand_programs_for_scenario(programs, scenario)
        chunks = _chunk_variables(expanded, chunk_size) if chunk_size else [expanded]
        for index, chunk in enumerate(chunks):
            if all((scenario.id, variable) in completed for variable in chunk):
                continue
            units.append(
                BatchUnit(scenario_id=scenario.id, variables=chunk, chunk_index=index)
            )
    return units


def parse_unit_result(
    unit: BatchUnit, result: NormalizedResult
) -> tuple[dict, dict, str | None, str | None]:
    """Run the sync extractors over a normalized result.

    Returns (predictions, explanations, raw_response, error).
    """
    if result.error:
        empty = {variable: None for variable in unit.variables}
        return empty, dict(empty), None, result.error
    raw_response = _serialize_response_payload(
        content=result.content,
        tool_calls=result.tool_calls,
        function_call=None,
    )
    predictions = extract_predictions(
        content=result.content,
        variables=unit.variables,
        tool_calls=result.tool_calls,
        function_call=None,
    )
    explanations = extract_explanations(
        content=result.content,
        variables=unit.variables,
        tool_calls=result.tool_calls,
        function_call=None,
    )
    predictions, explanations = _enforce_explanation_value_contract(
        predictions, explanations, unit.variables
    )
    return predictions, explanations, raw_response, None


def rows_from_unit(
    *,
    model_name: str,
    model_id: str,
    unit: BatchUnit,
    predictions: dict,
    explanations: dict,
    raw_response: str | None,
    error: str | None,
    result: NormalizedResult | None,
    run_id: str | None = None,
) -> list[dict]:
    """Emit CSV rows in the sync schema, usage apportioned across the chunk."""
    size = len(unit.variables)
    prompt_tokens = result.prompt_tokens if result else None
    completion_tokens = result.completion_tokens if result else None
    reconstructed = _reconstruct_token_cost(
        model_name=model_name,
        model_id=model_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_prompt_tokens=(result.cached_prompt_tokens if result else None),
        cache_write_prompt_tokens=(
            result.cache_write_prompt_tokens if result else None
        ),
    )
    total_tokens = (
        prompt_tokens + completion_tokens
        if prompt_tokens is not None and completion_tokens is not None
        else None
    )

    def split(value):
        return value / size if value is not None else None

    call_id = ":".join(
        part for part in [run_id, model_name, unit.scenario_id] if part is not None
    )
    rows = []
    for variable in unit.variables:
        rows.append(
            {
                **({"run_id": run_id} if run_id is not None else {}),
                "call_id": call_id,
                "model": model_name,
                "scenario_id": unit.scenario_id,
                "variable": variable,
                "prediction": predictions.get(variable),
                "explanation": explanations.get(variable),
                "raw_response": raw_response,
                "error": error,
                # Batch round-trips include provider queue time, which is not
                # model latency; leave the latency fields empty rather than
                # publish a misleading number.
                "elapsed_seconds": None,
                "request_started_at": None,
                "request_completed_at": None,
                "prompt_tokens": split(prompt_tokens),
                "completion_tokens": split(completion_tokens),
                "total_tokens": split(total_tokens),
                "reasoning_tokens": split(result.reasoning_tokens if result else None),
                "cached_prompt_tokens": split(
                    result.cached_prompt_tokens if result else None
                ),
                "cache_write_prompt_tokens": split(
                    result.cache_write_prompt_tokens if result else None
                ),
                "provider_reported_cost_usd": None,
                "reconstructed_cost_usd": split(reconstructed),
                "total_cost_usd": split(reconstructed),
                "cost_is_estimated": False if reconstructed is not None else None,
                "estimated_cost_usd": split(reconstructed),
                "provider_response_id": result.provider_response_id if result else None,
                "provider_system_fingerprint": None,
                "provider_resolved_model": (
                    result.provider_resolved_model if result else None
                ),
            }
        )
    return rows


def run_batch_eval(
    *,
    scenarios: list[Scenario],
    programs: list[str],
    model_name: str,
    model_id: str,
    run_dir: Path,
    adapter=None,
    poll_seconds: int = DEFAULT_POLL_SECONDS,
    max_wait_seconds: int = DEFAULT_MAX_WAIT_SECONDS,
    sleep=time.sleep,
    clock=time.time,
    log=print,
) -> pd.DataFrame:
    """Submit, poll, collect, and repair one model's run via its batch API.

    Writes ``<run_dir>/by_model/<model>.csv`` in the sync schema and returns
    the frame. Rounds beyond the first re-request only units whose response
    violated the answer contract, mirroring the sync repair loop.
    """
    adapter = adapter or adapter_for_model(model_id)
    if adapter is None:
        raise ValueError(
            f"{model_id} has no batch adapter — use the sync chunked runner."
        )
    if not adapter.supports(model_id):
        raise ValueError(
            f"{adapter.provider} batch adapter does not support {model_id}"
        )

    scenario_by_id = {scenario.id: scenario for scenario in scenarios}
    rows_by_key: dict[tuple[str, str], dict] = {}
    units = build_units(scenarios, programs, model_id)

    for round_index in range(1 + MAX_REPAIR_ROUNDS):
        if not units:
            break
        state = BatchRunState.load(run_dir, model_name, round_index)
        if state is None:
            repair = round_index > 0
            for unit in units:
                unit.repair = repair
            requests = [
                (
                    unit.custom_id,
                    adapter.build_request_body(
                        scenario_by_id[unit.scenario_id], unit, model_id
                    ),
                )
                for unit in units
            ]
            log(
                f"[{model_name}] round {round_index}: submitting "
                f"{len(requests)} requests via {adapter.provider} batch"
            )
            batch_id = adapter.submit(requests, model_id)
            state = BatchRunState(
                model=model_name,
                round_index=round_index,
                batch_id=batch_id,
                provider=adapter.provider,
                submitted_at=clock(),
                units={
                    unit.custom_id: {
                        "scenario_id": unit.scenario_id,
                        "variables": unit.variables,
                        "chunk_index": unit.chunk_index,
                        "repair": unit.repair,
                    }
                    for unit in units
                },
            )
            state.save(run_dir)
        else:
            log(f"[{model_name}] round {round_index}: resuming batch {state.batch_id}")

        deadline = clock() + max_wait_seconds
        while True:
            status = adapter.status(state.batch_id)
            if status == "ended":
                break
            if status == "failed":
                raise RuntimeError(
                    f"Batch {state.batch_id} for {model_name} ended as failed"
                )
            if clock() > deadline:
                raise TimeoutError(
                    f"Batch {state.batch_id} for {model_name} still running "
                    f"after {max_wait_seconds}s; rerun to resume polling"
                )
            sleep(poll_seconds)

        unit_index = {
            custom_id: BatchUnit(
                scenario_id=meta["scenario_id"],
                variables=list(meta["variables"]),
                chunk_index=meta["chunk_index"],
                repair=meta.get("repair", False),
            )
            for custom_id, meta in state.units.items()
        }
        seen: set[str] = set()
        for result in adapter.results(state.batch_id):
            unit = unit_index.get(result.custom_id)
            if unit is None:
                continue
            seen.add(result.custom_id)
            predictions, explanations, raw_response, error = parse_unit_result(
                unit, result
            )
            for row in rows_from_unit(
                model_name=model_name,
                model_id=model_id,
                unit=unit,
                predictions=predictions,
                explanations=explanations,
                raw_response=raw_response,
                error=error,
                result=result if not result.error else None,
            ):
                key = (row["scenario_id"], row["variable"])
                existing = rows_by_key.get(key)
                # Later rounds only override rows the earlier round left
                # broken, mirroring sync repair-merge semantics.
                if (
                    existing is None
                    or existing.get("prediction") is None
                    or not str(existing.get("explanation") or "").strip()
                ):
                    rows_by_key[key] = row
        for custom_id, unit in unit_index.items():
            if custom_id in seen:
                continue
            for row in rows_from_unit(
                model_name=model_name,
                model_id=model_id,
                unit=unit,
                predictions={variable: None for variable in unit.variables},
                explanations={variable: None for variable in unit.variables},
                raw_response=None,
                error="batch_missing: no result entry returned",
                result=None,
            ):
                rows_by_key.setdefault((row["scenario_id"], row["variable"]), row)

        state.completed_at = clock()
        state.save(run_dir)
        log(
            f"[{model_name}] round {round_index}: collected "
            f"{len(seen)}/{len(unit_index)} results in "
            f"{state.completed_at - state.submitted_at:.0f}s"
        )

        units = _repair_targets(scenario_by_id, programs, model_id, rows_by_key)
        if units:
            log(
                f"[{model_name}] round {round_index}: {len(units)} units "
                "violate the answer contract; scheduling repair round"
            )

    frame = pd.DataFrame(list(rows_by_key.values()))
    by_model = run_dir / "by_model"
    by_model.mkdir(parents=True, exist_ok=True)
    output = by_model / f"{model_name}.csv"
    frame.to_csv(output, index=False)
    log(f"[{model_name}] wrote {output} ({len(frame):,} rows)")
    return frame


def _repair_targets(
    scenario_by_id: dict,
    programs: list[str],
    model_id: str,
    rows_by_key: dict[tuple[str, str], dict],
) -> list[BatchUnit]:
    """Units whose rows are missing a parsed value or a nonempty explanation."""
    broken: dict[str, list[str]] = {}
    for (scenario_id, variable), row in rows_by_key.items():
        if (
            row.get("prediction") is None
            or not str(row.get("explanation") or "").strip()
        ):
            broken.setdefault(scenario_id, []).append(variable)
    chunk_size = _required_explanation_chunk_size(model_id, True)
    units: list[BatchUnit] = []
    for scenario_id, variables in sorted(broken.items()):
        ordered = [
            variable
            for variable in expand_programs_for_scenario(
                programs, scenario_by_id[scenario_id]
            )
            if variable in set(variables)
        ]
        chunks = _chunk_variables(ordered, chunk_size) if chunk_size else [ordered]
        for index, chunk in enumerate(chunks):
            units.append(
                BatchUnit(
                    scenario_id=scenario_id,
                    variables=chunk,
                    chunk_index=index,
                    repair=True,
                )
            )
    return units
