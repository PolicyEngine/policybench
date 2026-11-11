"""Anthropic's thinking-token count reaches ``reasoning_tokens``.

Anthropic reports how many of a response's output tokens went to thinking in
``usage.output_tokens_details.thinking_tokens``; ``output_tokens`` stays the
inclusive total Anthropic bills (the anthropic SDK's docstrings in
``types/usage.py`` and ``types/output_tokens_details.py``). litellm 1.95.0
builds an Anthropic response's usage in ``AnthropicConfig.calculate_usage``,
which never reads that field: it counts reasoning by tokenizing the thinking
text the response returns. The recorded Claude Haiku 5.5 response in
``tests/fixtures`` returns its thinking block with empty text, so litellm
reports 0 reasoning tokens where Anthropic reports 119. PolicyBench copies the
provider's count onto litellm's usage
(``eval_no_tools._install_anthropic_thinking_token_capture``) and records it;
the batch path reads it from the SDK's usage.

The two recorded responses come from ``tests/fixtures``. Every other response
here is MOCK DATA: a recorded response whose usage numbers, thinking text,
model id or answer the test swaps or Hypothesis draws.

Invariants, for every Anthropic response of the shape PolicyBench requests
(litellm sums ``usage.iterations`` when a response has them; the SDK's
``Usage`` type has no such field, and no test here draws one):

1. Exact or empty. When the response carries a thinking count,
   ``reasoning_tokens`` holds that count if it is a whole number in
   ``[0, output_tokens]`` and holds nothing otherwise. The harness never
   clamps a count.
2. Bound. ``reasoning_tokens`` never exceeds the response's output tokens. A
   row sums the counts its request group's responses reported and splits the
   sum over its outputs, so a row's count never exceeds its completion tokens.
3. Cost. The count changes no other usage column: prompt, completion and
   total tokens and every cost column equal what litellm gives without the
   capture.
4. Fallback. When the response carries no count, each path records what it
   recorded before: litellm's own count on the sync path, nothing on the
   batch path.
5. Replay. A LiteLLM cache replay records what the live call recorded. An
   entry cached before the capture existed replays litellm's own count.
6. Agreement. For a response whose output and thinking counts are JSON
   integers, the sync path and the batch path record the same reasoning
   count. The batch path reads both counts as the SDK's types hold them, so
   a count sent as a string, a boolean or a fraction can differ there.

No test calls a model. ``httpx.MockTransport`` answers litellm's and the
SDK's requests, so their own request and response code runs. Both clients
get the API's base URL by argument, so an ``ANTHROPIC_BASE_URL`` in the
environment moves no URL a test asserts.
"""

from __future__ import annotations

import copy
import json
import logging
import math
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import httpx
import litellm
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from litellm.llms.custom_httpx.http_handler import HTTPHandler

from policybench.batch_eval import (
    AnthropicBatchAdapter,
    BatchUnit,
    NormalizedResult,
    _batch_spend_record,
    rows_from_unit,
)
from policybench.cache import enable_cache
from policybench.config import MODELS
from policybench.eval_no_tools import (
    ANTHROPIC_THINKING_CAPTURE_INSTALLED,
    _aggregate_request_results,
    _bounded_thinking_tokens,
    _capture_anthropic_thinking_tokens,
    _extract_usage_metadata,
    _install_anthropic_thinking_token_capture,
    _recorded_anthropic_thinking_tokens,
    _response_cache_hit,
    _spend_ledger_record,
    _with_thinking_capture,
    run_no_tools_eval,
    run_single_no_tools,
)
from policybench.scenarios import Person, Scenario

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "anthropic_haiku55_probe_responses.json"
PROBES = json.loads(FIXTURE.read_text())["probes"]
# A request with no thinking parameter. The response holds a thinking block
# with empty text, and Anthropic counts 119 of its 123 output tokens as
# thinking.
THINKING = PROBES["no_thinking_parameter"]["response"]
# A forced tool call. The response holds no thinking block and a thinking
# count of 0.
FORCED_TOOL = PROBES["forced_tool"]["response"]
HAIKU = "claude-haiku-5-5"
# A Claude row on the JSON answer contract, for the MOCK board rows.
SONNET = "claude-sonnet-5-5"
SONNET_NAME = "claude-sonnet-5.5"
API_BASE = "https://api.anthropic.com"
MESSAGES_URL = f"{API_BASE}/v1/messages"
MOCK_THINKING_TEXT = "The 2026 standard deduction for a single filer applies."
MOCK_BOARD_OUTPUTS = {
    "income_tax": {
        "value": 3500,
        "explanation": "Wage income drives tax. value = 3500",
    }
}
# What the SDK's MessageBatch type needs of a finished batch.
MOCK_BATCH = {
    "id": "msgbatch_test",
    "type": "message_batch",
    "processing_status": "ended",
    "request_counts": {
        "processing": 0,
        "succeeded": 1,
        "errored": 0,
        "canceled": 0,
        "expired": 0,
    },
    "created_at": "2026-11-10T00:00:00Z",
    "expires_at": "2026-11-11T00:00:00Z",
    "ended_at": "2026-11-10T00:01:00Z",
    "archived_at": None,
    "cancel_initiated_at": None,
    "results_url": (
        "https://api.anthropic.com/v1/messages/batches/msgbatch_test/results"
    ),
}
# Every usage column other than reasoning_tokens; none may move with the count.
OTHER_USAGE_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cached_prompt_tokens",
    "cache_write_prompt_tokens",
    "provider_reported_cost_usd",
    "reconstructed_cost_usd",
    "total_cost_usd",
    "cost_is_estimated",
    "estimated_cost_usd",
)


def test_the_mock_board_model_is_a_json_contract_claude_row():
    assert MODELS[SONNET_NAME] == SONNET


# MOCK response builders


def _without_count(body: dict) -> dict:
    """MOCK: the same response from an API that sends no output_tokens_details."""
    stripped = copy.deepcopy(body)
    stripped["usage"].pop("output_tokens_details", None)
    return stripped


def _with_count(body: dict, thinking) -> dict:
    """MOCK: the same response with another thinking count."""
    changed = copy.deepcopy(body)
    changed["usage"]["output_tokens_details"] = {"thinking_tokens": thinking}
    return changed


def _with_raw_count(body: dict, raw: str) -> str:
    """MOCK: the response as JSON text whose thinking count is the token ``raw``.

    Python's JSON parser, which httpx and the SDK use, accepts ``NaN`` and
    ``Infinity``; a dict handed to an encoder could not carry them.
    """
    marker = "@@THINKING-COUNT@@"
    return json.dumps(_with_count(body, marker)).replace(f'"{marker}"', raw)


def _with_thinking_text(body: dict, text: str = MOCK_THINKING_TEXT) -> dict:
    """MOCK: the same response with text in its thinking block."""
    changed = copy.deepcopy(body)
    assert changed["content"][0]["type"] == "thinking"
    changed["content"][0]["thinking"] = text
    return changed


def _as_content(body) -> bytes:
    """Return a response body as bytes; ``body`` is a dict or JSON text."""
    return body.encode() if isinstance(body, str) else json.dumps(body).encode()


# The sync path's plumbing: litellm over a mocked transport


def _litellm_response(body, model: str = HAIKU, prompt: str = "x", **kwargs):
    """Answer ``litellm.completion`` with a raw Anthropic response.

    Returns the response and the requests litellm sent (none on a cache
    replay).
    """
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            content=_as_content(body),
            headers={"content-type": "application/json"},
        )

    client = HTTPHandler(client=httpx.Client(transport=httpx.MockTransport(handler)))
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        api_key="test-key",
        api_base=API_BASE,
        client=client,
        max_tokens=2048,
        **kwargs,
    )
    return response, requests


def _transformed(body) -> litellm.ModelResponse:
    """Run litellm's Anthropic response transform alone, for the properties."""
    raw = httpx.Response(
        200, content=_as_content(body), request=httpx.Request("POST", MESSAGES_URL)
    )
    return litellm.AnthropicConfig().transform_response(
        model=HAIKU,
        raw_response=raw,
        model_response=litellm.ModelResponse(),
        logging_obj=MagicMock(),
        request_data={},
        messages=[],
        optional_params={},
        litellm_params={},
        encoding=None,
    )


@contextmanager
def _litellm_before_the_capture():
    """Swap in litellm's own ``calculate_usage``, as before this change.

    With it the usage carries no provider count, so ``_extract_usage_metadata``
    takes the path it took before.
    """
    unwrapped = litellm.AnthropicConfig.calculate_usage.__wrapped__
    with patch.object(litellm.AnthropicConfig, "calculate_usage", unwrapped):
        yield


def _usage(response, model: str = HAIKU) -> dict:
    return _extract_usage_metadata(response, model, [], "")


def _without_response_id(usage: dict) -> dict:
    """Drop the response id: litellm gives each live response an id of its
    own, so two live calls never share one."""
    return {key: value for key, value in usage.items() if key != "provider_response_id"}


@pytest.fixture
def litellm_cache_state(monkeypatch):
    """Let a test set ``litellm.cache``; restore it and litellm's callbacks."""
    for name in ("input_callback", "success_callback", "_async_success_callback"):
        monkeypatch.setattr(litellm, name, list(getattr(litellm, name)))
    monkeypatch.setattr(litellm, "cache", None)
    return monkeypatch


# Settings that would change a request these tests assert: litellm's switch
# for the ``/v1/messages`` suffix and the harness's sensitivity-run overrides.
REQUEST_SHAPING_VARIABLES = (
    "LITELLM_ANTHROPIC_DISABLE_URL_SUFFIX",
    "POLICYBENCH_CONTRACT_OVERRIDE",
    "POLICYBENCH_TOOL_CHOICE",
    "POLICYBENCH_CHUNK_OVERRIDE",
)


@pytest.fixture(autouse=True, scope="module")
def default_request_settings():
    """Run this module's tests without the request-shaping variables."""
    with pytest.MonkeyPatch.context() as patcher:
        for name in REQUEST_SHAPING_VARIABLES:
            patcher.delenv(name, raising=False)
        yield


# The batch path's plumbing: the SDK over a mocked transport


class _MockBatches:
    """An Anthropic client whose Message Batches endpoints a test fills.

    ``results`` reads entries as the harness does:
    ``AnthropicBatchAdapter.results`` calls the SDK's
    ``client.messages.batches.results``, which fetches the batch and then its
    JSONL results.
    """

    def __init__(self) -> None:
        self.lines = b""
        self.paths: list[str] = []
        self.client = anthropic.Anthropic(
            api_key="test-key",
            base_url=API_BASE,
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(self._answer)),
        )

    def _answer(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if request.url.path.endswith("/results"):
            return httpx.Response(200, content=self.lines)
        return httpx.Response(200, json=MOCK_BATCH)

    def results(self, *bodies) -> list[NormalizedResult]:
        self.paths.clear()
        self.lines = b"".join(
            b'{"custom_id": "scenario_000__u000", "result": '
            b'{"type": "succeeded", "message": ' + _as_content(body) + b"}}\n"
            for body in bodies
        )
        return list(AnthropicBatchAdapter(client=self.client).results("msgbatch_test"))


BATCHES = _MockBatches()


# MOCK board rows


@pytest.fixture
def mini_scenario():
    return Scenario(
        id="mini",
        state="CA",
        filing_status="single",
        adults=[Person(name="adult1", age=35, employment_income=50_000.0)],
        year=2026,
    )


def _mock_board_response(
    outputs: dict,
    *,
    input_tokens: int = 54,
    output_tokens: int = 123,
    thinking: int = 119,
):
    """MOCK DATA: the recorded response as a JSON-contract board answer.

    The model id, the answer text and the usage numbers replace the
    recording's; litellm parses the result as it parses a live response.
    """
    body = copy.deepcopy(THINKING)
    body["model"] = SONNET
    body["content"][1]["text"] = json.dumps({"outputs": outputs})
    body["usage"]["input_tokens"] = input_tokens
    body["usage"]["output_tokens"] = output_tokens
    body["usage"]["output_tokens_details"] = {"thinking_tokens": thinking}
    return _litellm_response(body, model=SONNET)[0]


# The mechanism


def test_litellm_alone_drops_anthropics_thinking_count():
    """Without the capture, litellm reports 0 reasoning and carries the
    provider's count nowhere on its response.

    If this fails, litellm changed how it reports Anthropic reasoning, and
    eval_no_tools may no longer need the capture.
    """
    assert THINKING["content"][0] == {
        "type": "thinking",
        "thinking": "",
        "signature": "SIGNATURE-PLACEHOLDER",
    }
    assert THINKING["usage"]["output_tokens_details"] == {"thinking_tokens": 119}

    with _litellm_before_the_capture():
        response, _ = _litellm_response(THINKING)

    assert response.usage.completion_tokens == 123
    assert response.usage.completion_tokens_details.reasoning_tokens == 0
    assert "output_tokens_details" not in response.usage.model_dump()
    assert "thinking_tokens" not in response.model_dump_json()
    assert "thinking_tokens" not in json.dumps(response._hidden_params, default=str)


def test_the_capture_wraps_litellm_once():
    wrapped = litellm.AnthropicConfig.calculate_usage

    assert ANTHROPIC_THINKING_CAPTURE_INSTALLED is True
    assert wrapped._policybench_thinking_capture is True
    assert _install_anthropic_thinking_token_capture() is True
    # A second install leaves the one wrapper where it stood.
    assert litellm.AnthropicConfig.calculate_usage is wrapped
    assert not hasattr(wrapped.__wrapped__, "_policybench_thinking_capture")


def test_the_wrapper_reads_the_raw_usage_by_keyword_or_position():
    raw_usage = copy.deepcopy(THINKING["usage"])
    config = litellm.AnthropicConfig()

    by_keyword = config.calculate_usage(usage_object=raw_usage, reasoning_content="")
    by_position = config.calculate_usage(raw_usage, "")

    assert _recorded_anthropic_thinking_tokens(by_keyword) == 119
    assert _recorded_anthropic_thinking_tokens(by_position) == 119


def test_the_wrapper_survives_a_renamed_litellm_parameter():
    """MOCK: a later litellm that calls the builder with another keyword. The
    wrapper returns litellm's result as it is and raises nothing."""
    built = litellm.Usage(prompt_tokens=54, completion_tokens=123, total_tokens=177)

    def renamed(self, usage, reasoning_content=None):
        return built

    wrapped = _with_thinking_capture(renamed)
    result = wrapped(object(), usage=copy.deepcopy(THINKING["usage"]))

    assert result is built
    assert _recorded_anthropic_thinking_tokens(built) is None


def test_the_capture_never_breaks_a_response(caplog):
    """A usage object that refuses the attribute still comes back, uncounted,
    and so does litellm's usage when the raw usage has an odd shape."""

    class FrozenUsage:
        def __setattr__(self, name, value):
            raise TypeError("frozen")

    frozen = FrozenUsage()
    with caplog.at_level(logging.WARNING, logger="policybench.eval_no_tools"):
        returned = _capture_anthropic_thinking_tokens(
            frozen, copy.deepcopy(THINKING["usage"])
        )

    assert returned is frozen
    assert "Could not record Anthropic's thinking-token count" in caplog.text
    odd_shapes = (None, "usage", ["usage"], 7, {"output_tokens_details": ["x"]})
    for raw_usage in odd_shapes:
        usage = litellm.Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        assert _capture_anthropic_thinking_tokens(usage, raw_usage) is usage
        assert _recorded_anthropic_thinking_tokens(usage) is None


def test_a_test_doubles_invented_attribute_is_no_provider_count():
    """A ``MagicMock`` usage invents every attribute a caller asks for; only
    a JSON value under the capture's name counts as a provider count."""
    usage = MagicMock()
    usage.prompt_tokens = 5
    usage.completion_tokens = 9
    usage.reasoning_tokens = 7
    response = SimpleNamespace(usage=usage, id="mock", model=HAIKU)

    assert _recorded_anthropic_thinking_tokens(usage) is None
    assert _usage(response)["reasoning_tokens"] == 7


def test_the_bound_reads_output_tokens_when_the_usage_has_no_completion_count():
    """MOCK usage, not litellm's: it carries a provider count and names its
    completion count ``output_tokens``. litellm's own usage always carries
    ``completion_tokens``."""
    usage = SimpleNamespace(
        input_tokens=54, output_tokens=123, anthropic_thinking_tokens=119
    )
    response = SimpleNamespace(usage=usage, id="mock", model=HAIKU)

    assert _usage(response)["reasoning_tokens"] == 119
    assert _usage(response)["completion_tokens"] == 123


# The sync path, through litellm.completion


def test_recorded_response_records_anthropics_thinking_count():
    response, requests = _litellm_response(THINKING)
    usage = _usage(response)

    assert [(r.method, str(r.url)) for r in requests] == [("POST", MESSAGES_URL)]
    assert usage["reasoning_tokens"] == 119
    assert usage["completion_tokens"] == 123
    assert usage["prompt_tokens"] == 54


def test_the_count_moves_no_other_usage_column():
    """Differential against litellm without the capture: reasoning moves from
    0 to 119 and every other column stays."""
    after = _usage(_litellm_response(THINKING)[0])
    with _litellm_before_the_capture():
        before = _usage(_litellm_response(THINKING)[0])

    assert (before["reasoning_tokens"], after["reasoning_tokens"]) == (0, 119)
    assert before["total_cost_usd"] > 0
    assert _without_response_id({**after, "reasoning_tokens": 0}) == (
        _without_response_id(before)
    )


def test_without_the_field_sync_records_litellms_count_of_the_thinking_text():
    """MOCK: no provider count and text in the thinking block. litellm counts
    the text, and the harness records that count, as it did before."""
    body = _with_thinking_text(_without_count(THINKING))
    with _litellm_before_the_capture():
        before = _usage(_litellm_response(body)[0])
    after = _usage(_litellm_response(body)[0])

    assert before["reasoning_tokens"] > 0
    assert _without_response_id(after) == _without_response_id(before)


def test_without_the_field_or_thinking_text_sync_records_zero(caplog):
    with caplog.at_level(logging.WARNING, logger="policybench.eval_no_tools"):
        usage = _usage(_litellm_response(_without_count(THINKING))[0])

    assert usage["reasoning_tokens"] == 0
    assert usage["completion_tokens"] == 123
    assert "Recording reasoning_tokens as unknown" not in caplog.text


def test_the_provider_count_replaces_litellms_count_of_the_thinking_text():
    """MOCK: text in the thinking block and a provider count. litellm's count
    of the text differs from Anthropic's 119, and the harness records 119."""
    body = _with_thinking_text(THINKING)
    with _litellm_before_the_capture():
        litellm_count = _usage(_litellm_response(body)[0])["reasoning_tokens"]

    assert litellm_count not in (0, 119)
    assert _usage(_litellm_response(body)[0])["reasoning_tokens"] == 119


def test_forced_tool_response_records_a_zero_count():
    usage = _usage(_litellm_response(FORCED_TOOL)[0])

    assert FORCED_TOOL["usage"]["output_tokens_details"] == {"thinking_tokens": 0}
    assert usage["reasoning_tokens"] == 0
    assert usage["completion_tokens"] == 33


@pytest.mark.parametrize(
    "raw",
    ["124", "-1", "true", '"119"', "119.5", "[119]", '{"count": 119}']
    + ["NaN", "Infinity", "-Infinity", "1e400"],
)
def test_sync_records_an_impossible_thinking_count_as_unknown(raw, caplog):
    """MOCK counts. Thinking is part of output, so the harness never clamps a
    count outside [0, 123], and it accepts whole numbers only."""
    with caplog.at_level(logging.WARNING, logger="policybench.eval_no_tools"):
        usage = _usage(_litellm_response(_with_raw_count(THINKING, raw))[0])

    assert usage["reasoning_tokens"] is None
    assert usage["completion_tokens"] == 123
    assert "Recording reasoning_tokens as unknown" in caplog.text


@pytest.mark.parametrize(("raw", "expected"), [("119.0", 119), ("123", 123), ("0", 0)])
def test_sync_keeps_whole_counts_up_to_output(raw, expected):
    usage = _usage(_litellm_response(_with_raw_count(THINKING, raw))[0])

    assert usage["reasoning_tokens"] == expected
    assert type(usage["reasoning_tokens"]) is int


def test_sync_treats_a_null_thinking_count_as_absent():
    usage = _usage(_litellm_response(_with_raw_count(THINKING, "null"))[0])

    assert usage["reasoning_tokens"] == 0


@pytest.mark.parametrize(("thinking", "expected"), [(0, 0), (1, None)])
def test_a_response_with_no_output_tokens_keeps_an_empty_completion(thinking, expected):
    """MOCK: zero output tokens. The row's completion count stays empty, as
    before this change, and the bound is the zero the response reported."""
    body = _with_count(THINKING, thinking)
    body["usage"]["output_tokens"] = 0
    after = _usage(_litellm_response(body)[0])
    with _litellm_before_the_capture():
        before = _usage(_litellm_response(body)[0])

    assert (before["completion_tokens"], before["reasoning_tokens"]) == (None, 0)
    assert after["reasoning_tokens"] == expected
    assert _without_response_id({**after, "reasoning_tokens": 0}) == (
        _without_response_id(before)
    )


@pytest.mark.parametrize(
    "raw",
    ["119", "0", "124", "-1", '"119"', "true", "119.5", "[119]", "null"]
    + ["NaN", "Infinity"],
)
def test_a_cache_replay_records_what_the_live_call_recorded(raw, litellm_cache_state):
    """MOCK counts, through litellm's in-memory cache."""
    litellm_cache_state.setattr(litellm, "cache", litellm.Cache(type="local"))
    body = _with_raw_count(THINKING, raw)

    live, live_requests = _litellm_response(body, caching=True)
    replay, replay_requests = _litellm_response(body, caching=True)

    assert (len(live_requests), len(replay_requests)) == (1, 0)
    assert not _response_cache_hit(live)
    assert _response_cache_hit(replay)
    assert _usage(replay) == _usage(live)


def test_the_harness_disk_cache_keeps_the_count_for_the_next_process(
    tmp_path, litellm_cache_state
):
    """``enable_cache`` sets up the cache the harness runs with. A new
    ``Cache`` on the same directory and namespace stands in for the next
    process."""
    enable_cache(str(tmp_path / "cache"))
    cache_dir = os.path.realpath(tmp_path / "cache")
    namespace = litellm.cache.namespace

    live, live_requests = _litellm_response(THINKING, caching=True)
    litellm_cache_state.setattr(
        litellm,
        "cache",
        litellm.Cache(type="disk", disk_cache_dir=cache_dir, namespace=namespace),
    )
    replay, replay_requests = _litellm_response(THINKING, caching=True)

    assert namespace.startswith("policybench:")
    assert (len(live_requests), len(replay_requests)) == (1, 0)
    assert _response_cache_hit(replay)
    assert _usage(live)["reasoning_tokens"] == 119
    assert _usage(replay) == _usage(live)


def test_an_entry_cached_before_the_capture_replays_litellms_count(
    litellm_cache_state,
):
    """The request's cache key is the same with and without the capture, so
    the replay hits the older entry, which holds no provider count."""
    litellm_cache_state.setattr(litellm, "cache", litellm.Cache(type="local"))
    with _litellm_before_the_capture():
        written, written_requests = _litellm_response(THINKING, caching=True)

    replay, replay_requests = _litellm_response(THINKING, caching=True)

    assert (len(written_requests), len(replay_requests)) == (1, 0)
    assert _response_cache_hit(replay)
    assert _usage(replay) == _usage(written)
    assert _usage(replay)["reasoning_tokens"] == 0


def test_a_replays_spend_record_keeps_the_count_and_charges_nothing(
    mini_scenario, litellm_cache_state
):
    """The spend ledger's record of a cache replay holds the response's
    token counts and a zero cost."""
    litellm_cache_state.setattr(litellm, "cache", litellm.Cache(type="local"))
    live, _ = _litellm_response(THINKING, caching=True)
    replay, _ = _litellm_response(THINKING, caching=True)

    record = _spend_ledger_record(
        call_key="sync:mock",
        phase="initial",
        attempt=1,
        status="ok",
        scenario=mini_scenario,
        variables=["income_tax"],
        model_id=HAIKU,
        request_started_at=None,
        request_completed_at=None,
        elapsed_seconds=None,
        usage=_usage(replay),
        cache_hit=_response_cache_hit(replay),
    )

    assert record["cache_hit"] is True
    assert record["reasoning_tokens"] == 119
    assert record["completion_tokens"] == 123
    assert record["total_cost_usd"] == 0.0
    assert record["cached_response_cost_usd"] == _usage(live)["total_cost_usd"] > 0


# MOCK board rows through the row writers


@patch("policybench.eval_no_tools.completion")
def test_board_row_records_the_thinking_count(mock_completion, mini_scenario):
    """MOCK: a JSON-contract Claude row whose response carries the recorded
    usage."""
    mock_completion.return_value = _mock_board_response(MOCK_BOARD_OUTPUTS)

    result = run_single_no_tools(mini_scenario, "income_tax", SONNET)

    assert mock_completion.call_args.kwargs["response_format"] == {
        "type": "json_object"
    }
    assert result["prediction"] == 3500.0
    assert result["error"] is None
    assert result["reasoning_tokens"] == 119
    assert result["completion_tokens"] == 123
    assert result["spend_ledger"][0]["reasoning_tokens"] == 119


@patch("policybench.eval_no_tools.completion")
def test_a_repair_round_adds_its_own_count_to_the_row(mock_completion, mini_scenario):
    """MOCK: the first answer lacks its explanation, so the harness asks
    again; the row sums both responses' counts."""
    mock_completion.side_effect = [
        _mock_board_response({"income_tax": {"value": 3500}}),
        _mock_board_response(
            MOCK_BOARD_OUTPUTS, input_tokens=60, output_tokens=80, thinking=70
        ),
    ]

    result = run_single_no_tools(mini_scenario, "income_tax", SONNET)

    assert mock_completion.call_count == 2
    assert result["error"] is None
    assert result["reasoning_tokens"] == 119 + 70
    assert result["completion_tokens"] == 123 + 80
    assert [r["reasoning_tokens"] for r in result["spend_ledger"]] == [119, 70]


@patch("policybench.eval_no_tools._required_explanation_chunk_size", return_value=1)
@patch("policybench.eval_no_tools.completion")
def test_a_chunked_request_sums_each_chunks_count(
    mock_completion, _chunk_size, mini_scenario
):
    """MOCK: one output per request; the row sums the two responses' counts."""
    mock_completion.side_effect = [
        _mock_board_response(MOCK_BOARD_OUTPUTS),
        _mock_board_response(
            {
                "federal_refundable_credits": {
                    "value": 0,
                    "explanation": "No credit applies. value = 0",
                }
            },
            input_tokens=60,
            output_tokens=80,
            thinking=70,
        ),
    ]

    result = run_single_no_tools(
        mini_scenario, ["income_tax", "federal_refundable_credits"], SONNET
    )

    assert mock_completion.call_count == 2
    assert result["reasoning_tokens"] == 119 + 70
    assert result["completion_tokens"] == 123 + 80


def test_sync_rows_split_the_count_over_the_requests_outputs(mini_scenario):
    """MOCK: one request answers two outputs, and each CSV row takes half of
    its usage."""
    mock_result = {
        "predictions": {"income_tax": 3500.0, "federal_refundable_credits": 0.0},
        "explanations": {
            "income_tax": "Wage income drives tax. value = 3500",
            "federal_refundable_credits": "No credit applies. value = 0",
        },
        "raw_response": "{}",
        "error": None,
        "elapsed_seconds": 1.0,
        "prompt_tokens": 54,
        "completion_tokens": 123,
        "total_tokens": 177,
        "reasoning_tokens": 119,
        "cached_prompt_tokens": 0,
        "cache_write_prompt_tokens": 0,
        "provider_reported_cost_usd": None,
        "reconstructed_cost_usd": 0.001,
        "total_cost_usd": 0.001,
        "cost_is_estimated": False,
        "estimated_cost_usd": 0.001,
    }
    with patch(
        "policybench.eval_no_tools.run_single_no_tools", return_value=mock_result
    ):
        rows = run_no_tools_eval(
            [mini_scenario],
            models={SONNET_NAME: SONNET},
            programs=["income_tax", "federal_refundable_credits"],
        )

    assert list(rows["reasoning_tokens"]) == [59.5, 59.5]
    assert list(rows["completion_tokens"]) == [61.5, 61.5]


# The batch path, through the SDK's client.messages.batches.results


def test_batch_entry_records_anthropics_thinking_count():
    (entry,) = BATCHES.results(THINKING)

    assert BATCHES.paths == [
        "/v1/messages/batches/msgbatch_test",
        "/v1/messages/batches/msgbatch_test/results",
    ]
    assert entry.reasoning_tokens == 119
    assert entry.completion_tokens == 123
    assert entry.prompt_tokens == 54


def test_batch_entry_without_the_field_leaves_reasoning_empty(caplog):
    with caplog.at_level(logging.WARNING, logger="policybench.eval_no_tools"):
        with_field, without_field = BATCHES.results(THINKING, _without_count(THINKING))

    assert without_field.reasoning_tokens is None
    assert {**vars(with_field), "reasoning_tokens": None} == vars(without_field)
    assert "Recording reasoning_tokens as unknown" not in caplog.text


def test_batch_forced_tool_entry_records_a_zero_count():
    (entry,) = BATCHES.results(FORCED_TOOL)

    assert entry.reasoning_tokens == 0
    assert entry.completion_tokens == 33
    assert [call.function.name for call in entry.tool_calls] == ["answer"]


@pytest.mark.parametrize("raw", ["124", "-1", "119.5", "NaN", "Infinity"])
def test_batch_records_an_impossible_thinking_count_as_unknown(raw, caplog):
    with caplog.at_level(logging.WARNING, logger="policybench.eval_no_tools"):
        (entry,) = BATCHES.results(_with_raw_count(THINKING, raw))

    assert entry.reasoning_tokens is None
    assert entry.completion_tokens == 123
    assert "Recording reasoning_tokens as unknown" in caplog.text


def test_batch_rows_split_the_count_and_the_spend_record_keeps_it():
    """MOCK: the recorded response as a two-output batch request."""
    (entry,) = BATCHES.results(THINKING)
    unit = BatchUnit(
        scenario_id="mini",
        variables=["income_tax", "federal_refundable_credits"],
        chunk_index=0,
    )
    predictions = {"income_tax": 3500.0, "federal_refundable_credits": 0.0}
    explanations = {
        "income_tax": "Wage income drives tax. value = 3500",
        "federal_refundable_credits": "No credit applies. value = 0",
    }

    rows = rows_from_unit(
        model_name=SONNET_NAME,
        model_id=SONNET,
        unit=unit,
        predictions=predictions,
        explanations=explanations,
        raw_response=None,
        error=None,
        result=entry,
    )
    spend = _batch_spend_record(
        state=SimpleNamespace(
            batch_id="msgbatch_test", provider="anthropic", round_index=0
        ),
        unit=unit,
        model_name=SONNET_NAME,
        model_id=SONNET,
        result=entry,
        predictions=predictions,
        explanations=explanations,
        error=None,
    )

    assert [row["reasoning_tokens"] for row in rows] == [59.5, 59.5]
    assert [row["completion_tokens"] for row in rows] == [61.5, 61.5]
    assert spend["reasoning_tokens"] == 119


# Properties, over MOCK responses

ABSENT = "absent"


@st.composite
def mock_anthropic_responses(draw):
    """MOCK DATA: the recorded response with drawn usage, thinking count and
    thinking text. Returns the body and the count (``ABSENT`` for none)."""
    output_tokens = draw(st.integers(min_value=0, max_value=131_072))
    thinking = draw(
        st.one_of(
            st.just(ABSENT),
            st.none(),
            st.integers(min_value=0, max_value=output_tokens),
            st.integers(min_value=-5, max_value=output_tokens + 5),
            st.integers(min_value=-(2**40), max_value=2**40),
        )
    )
    body = copy.deepcopy(THINKING)
    body["usage"]["input_tokens"] = draw(st.integers(min_value=0, max_value=10**6))
    body["usage"]["output_tokens"] = output_tokens
    body["usage"]["cache_read_input_tokens"] = draw(
        st.integers(min_value=0, max_value=10**5)
    )
    body["usage"]["cache_creation_input_tokens"] = draw(
        st.integers(min_value=0, max_value=10**5)
    )
    if thinking == ABSENT:
        del body["usage"]["output_tokens_details"]
    else:
        body["usage"]["output_tokens_details"] = {"thinking_tokens": thinking}
    if draw(st.booleans()):
        body["content"][0]["thinking"] = draw(st.text(max_size=40))
    else:
        del body["content"][0]
    return body, thinking


@settings(max_examples=150, deadline=None)
@given(case=mock_anthropic_responses())
def test_sync_records_the_count_exactly_or_not_at_all(case):
    """Invariants 1 to 4 on the sync path, against litellm without the
    capture as the record of what the harness did before."""
    body, thinking = case
    output_tokens = body["usage"]["output_tokens"]
    after = _usage(_transformed(body))
    with _litellm_before_the_capture():
        before = _usage(_transformed(body))
    reasoning = after["reasoning_tokens"]

    if thinking == ABSENT or thinking is None:
        assert reasoning == before["reasoning_tokens"]
    elif 0 <= thinking <= output_tokens:
        assert reasoning == thinking
    else:
        assert reasoning is None
    assert reasoning is None or (
        type(reasoning) is int and 0 <= reasoning <= output_tokens
    )
    for key in OTHER_USAGE_KEYS:
        assert after[key] == before[key], key


@settings(max_examples=150, deadline=None)
@given(case=mock_anthropic_responses())
def test_batch_records_the_count_exactly_or_not_at_all(case):
    """Invariants 1 to 4 on the batch path."""
    body, thinking = case
    output_tokens = body["usage"]["output_tokens"]
    entry, baseline = BATCHES.results(body, _without_count(body))
    reasoning = entry.reasoning_tokens

    if thinking == ABSENT or thinking is None:
        assert reasoning is None
    elif 0 <= thinking <= output_tokens:
        assert reasoning == thinking
    else:
        assert reasoning is None
    assert reasoning is None or (
        type(reasoning) is int and 0 <= reasoning <= output_tokens
    )
    assert entry.completion_tokens == output_tokens
    assert baseline.reasoning_tokens is None
    assert {**vars(entry), "reasoning_tokens": None} == vars(baseline)


@settings(max_examples=150, deadline=None)
@given(case=mock_anthropic_responses())
def test_sync_and_batch_paths_record_the_same_counts(case):
    """Invariant 6. Differential: one response through litellm and through
    the SDK."""
    body, thinking = case
    sync = _usage(_transformed(body))
    (batch,) = BATCHES.results(body)

    # The sync path records a zero prompt or completion count as empty
    # (``0 or None`` in _extract_usage_metadata, as before this change).
    assert sync["prompt_tokens"] == (batch.prompt_tokens or None)
    assert sync["completion_tokens"] == (batch.completion_tokens or None)
    assert sync["cached_prompt_tokens"] == batch.cached_prompt_tokens
    assert sync["cache_write_prompt_tokens"] == batch.cache_write_prompt_tokens
    if thinking != ABSENT and thinking is not None:
        assert sync["reasoning_tokens"] == batch.reasoning_tokens


def _is_whole_count(value) -> bool:
    """The test's own reading of "a whole, non-negative, finite number"."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value == math.floor(value)
        and value >= 0
    )


@given(
    thinking=st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(2**40), max_value=2**40),
        st.floats(allow_nan=True, allow_infinity=True),
        st.text(max_size=5),
    ),
    output_tokens=st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(2**40), max_value=2**40),
        st.floats(allow_nan=True, allow_infinity=True),
    ),
)
def test_the_bound_returns_the_count_itself_or_nothing(thinking, output_tokens):
    bounded = _bounded_thinking_tokens(thinking, output_tokens)

    if (
        _is_whole_count(thinking)
        and _is_whole_count(output_tokens)
        and thinking <= output_tokens
    ):
        assert type(bounded) is int
        assert bounded == thinking
    else:
        assert bounded is None


@given(
    requests=st.lists(
        st.integers(min_value=0, max_value=10**6).flatmap(
            lambda completion: st.tuples(
                st.just(completion),
                st.one_of(st.none(), st.integers(min_value=0, max_value=completion)),
            )
        ),
        min_size=1,
        max_size=6,
    )
)
def test_a_request_group_sums_the_counts_its_responses_reported(requests):
    """MOCK usage. A row's request group (chunks, repair rounds) sums every
    response's count; a response without one adds nothing. Each drawn count
    stays within its own response's completion, so the exact sum also keeps
    the group's count within its completion (invariant 2)."""
    aggregate = _aggregate_request_results(
        [
            {"completion_tokens": completion, "reasoning_tokens": reasoning}
            for completion, reasoning in requests
        ]
    )
    known = [reasoning for _, reasoning in requests if reasoning is not None]

    assert aggregate["completion_tokens"] == sum(c for c, _ in requests)
    assert aggregate["reasoning_tokens"] == (sum(known) if known else None)
