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

Invariants, for every Anthropic response:

- when the response carries a thinking count, ``reasoning_tokens`` holds that
  count exactly if it is a whole number in ``[0, completion_tokens]``, and
  holds nothing otherwise; the harness never clamps a count;
- so ``reasoning_tokens`` never exceeds ``completion_tokens``, per response and
  per row (a row sums its request group and splits the sum over its outputs);
- the count changes no other usage column: prompt, completion and total
  tokens and every cost column stay as they were, since ``output_tokens``
  already includes thinking;
- when the response carries no count, each path records what it recorded
  before: litellm's own count on the sync path (which litellm caps at the
  completion) and nothing on the batch path;
- a LiteLLM cache replay keeps the count;
- the sync path and the batch path record the same token counts for the same
  response.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import litellm
import pytest
from anthropic._decoders.jsonl import JSONLDecoder
from anthropic.types.messages import MessageBatchIndividualResponse
from hypothesis import given, settings
from hypothesis import strategies as st
from litellm.caching.caching import Cache
from litellm.llms.anthropic.chat.transformation import AnthropicConfig
from litellm.llms.custom_httpx.http_handler import HTTPHandler
from litellm.types.utils import ModelResponse

from policybench.batch_eval import _normalize_anthropic_entry
from policybench.eval_no_tools import (
    ANTHROPIC_THINKING_CAPTURE_INSTALLED,
    ANTHROPIC_THINKING_TOKENS_FIELD,
    _aggregate_request_results,
    _bounded_reasoning_tokens,
    _capture_anthropic_thinking_tokens,
    _extract_usage_metadata,
    _install_anthropic_thinking_token_capture,
    _response_cache_hit,
    run_single_no_tools,
)
from policybench.scenarios import Person, Scenario

FIXTURE = Path(__file__).parent / "fixtures" / "anthropic_haiku55_probe_responses.json"
PROBES = json.loads(FIXTURE.read_text())["probes"]
# A request with no thinking parameter: a thinking block with empty text, and
# 119 of the response's 123 output tokens counted as thinking.
THINKING = PROBES["thinking_default"]["response"]
# A forced tool call: no thinking block, and a thinking count of 0.
FORCED_TOOL = PROBES["forced_tool"]["response"]
MODEL_ID = "claude-haiku-5-5"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
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


def _without_thinking_field(body: dict) -> dict:
    """The same response as an API that sends no output_tokens_details."""
    stripped = copy.deepcopy(body)
    stripped["usage"].pop("output_tokens_details", None)
    return stripped


def _with_thinking_count(body: dict, thinking) -> dict:
    changed = copy.deepcopy(body)
    changed["usage"]["output_tokens_details"] = {"thinking_tokens": thinking}
    return changed


def _http_response(body: dict) -> httpx.Response:
    return httpx.Response(
        200, json=copy.deepcopy(body), request=httpx.Request("POST", ANTHROPIC_URL)
    )


def _litellm_response(body: dict, model: str = MODEL_ID, **kwargs):
    """Answer ``litellm.completion`` with a raw Anthropic response, offline.

    Returns the response and how many HTTP posts litellm made (0 on a cache
    replay).
    """
    client = HTTPHandler()
    with patch.object(client, "post", return_value=_http_response(body)) as post:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": "x"}],
            api_key="test-key",
            client=client,
            max_tokens=2048,
            **kwargs,
        )
    return response, post.call_count


def _transformed(body: dict) -> ModelResponse:
    """litellm's Anthropic response transform alone (fast, for property tests)."""
    return AnthropicConfig().transform_response(
        model=MODEL_ID,
        raw_response=_http_response(body),
        model_response=ModelResponse(id=body["id"]),
        logging_obj=MagicMock(),
        request_data={},
        messages=[],
        optional_params={},
        litellm_params={},
        encoding=None,
    )


def _usage(response) -> dict:
    return _extract_usage_metadata(response, MODEL_ID, [], "")


def _batch_entry(body: dict) -> MessageBatchIndividualResponse:
    """A succeeded Message Batches entry, decoded as the SDK decodes results.

    ``client.messages.batches.results`` yields each JSONL line through this
    decoder, which builds the SDK's types without validating them, so a null
    or malformed count reaches ``_normalize_anthropic_entry`` as sent.
    """
    line = json.dumps(
        {
            "custom_id": "scenario_000__u000",
            "result": {"type": "succeeded", "message": body},
        }
    ).encode()
    (entry,) = JSONLDecoder(
        raw_iterator=iter([line + b"\n"]),
        line_type=MessageBatchIndividualResponse,
        http_response=httpx.Response(200),
    )
    return entry


# The mechanism


def test_litellm_alone_drops_anthropics_thinking_count():
    """Unwrapped, litellm's usage reports 0 reasoning and drops the field.

    If this fails, litellm changed how it reports Anthropic reasoning, and the
    capture in eval_no_tools may no longer be needed.
    """
    litellm_calculate_usage = AnthropicConfig.calculate_usage.__wrapped__
    usage = litellm_calculate_usage(
        AnthropicConfig(),
        usage_object=copy.deepcopy(THINKING["usage"]),
        reasoning_content="",
        completion_response=copy.deepcopy(THINKING),
    )

    assert THINKING["content"][0] == {
        "type": "thinking",
        "thinking": "",
        "signature": "SIGNATURE-PLACEHOLDER",
    }
    assert THINKING["usage"]["output_tokens_details"] == {"thinking_tokens": 119}
    assert usage.completion_tokens == 123
    assert usage.completion_tokens_details.reasoning_tokens == 0
    dumped = usage.model_dump()
    assert "output_tokens_details" not in dumped
    assert ANTHROPIC_THINKING_TOKENS_FIELD not in dumped


def test_the_capture_wraps_litellm_once():
    assert ANTHROPIC_THINKING_CAPTURE_INSTALLED is True
    assert AnthropicConfig.calculate_usage._policybench_thinking_capture is True
    assert _install_anthropic_thinking_token_capture() is True
    # Installing again does not wrap the wrapper.
    assert not hasattr(
        AnthropicConfig.calculate_usage.__wrapped__, "_policybench_thinking_capture"
    )


def test_capture_never_breaks_a_response():
    """A usage object that refuses the attribute still comes back, uncounted."""

    class FrozenUsage:
        def __setattr__(self, name, value):
            raise TypeError("frozen")

    frozen = FrozenUsage()

    assert (
        _capture_anthropic_thinking_tokens(frozen, copy.deepcopy(THINKING["usage"]))
        is frozen
    )
    assert not hasattr(frozen, ANTHROPIC_THINKING_TOKENS_FIELD)


# The sync path, through litellm.completion


def test_recorded_response_records_anthropics_thinking_count():
    response, posts = _litellm_response(THINKING)
    usage = _usage(response)

    assert posts == 1
    assert usage["reasoning_tokens"] == 119
    assert usage["completion_tokens"] == 123
    assert usage["prompt_tokens"] == 54


def test_without_the_field_reasoning_is_litellms_count_and_nothing_else_moves():
    with_field = _usage(_litellm_response(THINKING)[0])
    without_field = _usage(_litellm_response(_without_thinking_field(THINKING))[0])

    # litellm's count of the empty thinking text.
    assert without_field["reasoning_tokens"] == 0
    assert with_field["reasoning_tokens"] == 119
    for key in OTHER_USAGE_KEYS:
        assert with_field[key] == without_field[key], key


def test_forced_tool_response_records_a_zero_count():
    usage = _usage(_litellm_response(FORCED_TOOL)[0])

    assert FORCED_TOOL["usage"]["output_tokens_details"] == {"thinking_tokens": 0}
    assert usage["reasoning_tokens"] == 0
    assert usage["completion_tokens"] == 33


@pytest.mark.parametrize("thinking", [124, -1, True, "119", 119.5])
def test_sync_records_an_impossible_thinking_count_as_unknown(thinking):
    """Thinking is part of output, so the harness never clamps a count
    outside [0, 123].

    JSON has no NaN or infinity, so these are the shapes a response can carry;
    ``_bounded_reasoning_tokens`` has its own property test over every float.
    """
    usage = _usage(_litellm_response(_with_thinking_count(THINKING, thinking))[0])

    assert usage["reasoning_tokens"] is None
    assert usage["completion_tokens"] == 123


@pytest.mark.parametrize(("thinking", "expected"), [(119.0, 119), (123, 123), (0, 0)])
def test_sync_keeps_whole_counts_up_to_output(thinking, expected):
    usage = _usage(_litellm_response(_with_thinking_count(THINKING, thinking))[0])

    assert usage["reasoning_tokens"] == expected


def test_sync_treats_a_null_thinking_count_as_absent():
    usage = _usage(_litellm_response(_with_thinking_count(THINKING, None))[0])

    assert usage["reasoning_tokens"] == 0


def test_thinking_count_survives_a_litellm_cache_replay(monkeypatch):
    for name in ("input_callback", "success_callback", "_async_success_callback"):
        monkeypatch.setattr(litellm, name, list(getattr(litellm, name)))
    monkeypatch.setattr(litellm, "cache", Cache(type="local"))

    live, live_posts = _litellm_response(THINKING, caching=True)
    replay, replay_posts = _litellm_response(THINKING, caching=True)

    assert (live_posts, replay_posts) == (1, 0)
    assert not _response_cache_hit(live)
    assert _response_cache_hit(replay)
    assert _usage(live)["reasoning_tokens"] == 119
    assert _usage(replay)["reasoning_tokens"] == 119


@patch("policybench.eval_no_tools.completion")
def test_board_row_records_the_thinking_count(mock_completion):
    """A JSON-contract Claude row: the recorded usage and empty thinking block,
    with the board's JSON answer as the response text."""
    body = copy.deepcopy(THINKING)
    body["model"] = "claude-sonnet-5-5"
    body["content"][1]["text"] = json.dumps(
        {
            "outputs": {
                "income_tax": {
                    "value": 3500,
                    "explanation": "Wage income drives tax. value = 3500",
                }
            }
        }
    )
    mock_completion.return_value, _ = _litellm_response(body, model="claude-sonnet-5-5")
    scenario = Scenario(
        id="mini",
        state="CA",
        filing_status="single",
        adults=[Person(name="adult1", age=35, employment_income=50_000.0)],
        year=2026,
    )

    result = run_single_no_tools(scenario, "income_tax", "claude-sonnet-5-5")

    assert mock_completion.call_args.kwargs["response_format"] == {
        "type": "json_object"
    }
    assert result["prediction"] == 3500.0
    assert result["error"] is None
    assert result["reasoning_tokens"] == 119
    assert result["completion_tokens"] == 123
    assert result["spend_ledger"][0]["reasoning_tokens"] == 119


# The batch path, through the anthropic SDK's Message


def test_batch_entry_records_anthropics_thinking_count():
    normalized = _normalize_anthropic_entry(_batch_entry(THINKING))

    assert normalized.reasoning_tokens == 119
    assert normalized.completion_tokens == 123
    assert normalized.prompt_tokens == 54


def test_batch_entry_without_the_field_leaves_reasoning_empty():
    with_field = _normalize_anthropic_entry(_batch_entry(THINKING))
    without_field = _normalize_anthropic_entry(
        _batch_entry(_without_thinking_field(THINKING))
    )

    assert without_field.reasoning_tokens is None
    assert {**vars(with_field), "reasoning_tokens": None} == vars(without_field)


def test_batch_entry_with_an_impossible_count_records_unknown():
    normalized = _normalize_anthropic_entry(
        _batch_entry(_with_thinking_count(THINKING, 124))
    )

    assert normalized.reasoning_tokens is None
    assert normalized.completion_tokens == 123


# Properties

ABSENT = "absent"


@st.composite
def anthropic_responses(draw):
    """A recorded-shape Anthropic response with drawn usage and thinking."""
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
    thinking_block = draw(st.booleans())
    if thinking_block:
        body["content"][0]["thinking"] = draw(st.text(max_size=40))
    else:
        del body["content"][0]
    return body, thinking


@settings(max_examples=150, deadline=None)
@given(case=anthropic_responses())
def test_sync_reasoning_stays_within_completion_and_never_moves_cost(case):
    body, thinking = case
    output_tokens = body["usage"]["output_tokens"]
    usage = _usage(_transformed(body))
    baseline = _usage(_transformed(_without_thinking_field(body)))
    reasoning = usage["reasoning_tokens"]
    # _extract_usage_metadata records a response's zero output tokens as an
    # empty completion count (``0 or None``), as it did before this change.
    completion = usage["completion_tokens"]
    assert completion == (output_tokens or None)

    assert reasoning is None or (
        type(reasoning) is int and 0 <= reasoning <= (completion or 0)
    )
    if thinking == ABSENT or thinking is None:
        # No provider count: litellm's own, which it caps at the completion.
        assert reasoning == baseline["reasoning_tokens"]
    elif completion is not None and 0 <= thinking <= completion:
        assert reasoning == thinking
    else:
        assert reasoning is None
    for key in OTHER_USAGE_KEYS:
        assert usage[key] == baseline[key], key


@settings(max_examples=150, deadline=None)
@given(case=anthropic_responses())
def test_batch_reasoning_stays_within_completion(case):
    body, thinking = case
    output_tokens = body["usage"]["output_tokens"]
    normalized = _normalize_anthropic_entry(_batch_entry(body))
    baseline = _normalize_anthropic_entry(_batch_entry(_without_thinking_field(body)))
    reasoning = normalized.reasoning_tokens
    assert normalized.completion_tokens == output_tokens

    assert reasoning is None or (
        type(reasoning) is int and 0 <= reasoning <= normalized.completion_tokens
    )
    if thinking == ABSENT or thinking is None:
        assert reasoning is None
    elif 0 <= thinking <= output_tokens:
        assert reasoning == thinking
    else:
        assert reasoning is None
    assert baseline.reasoning_tokens is None
    assert {**vars(normalized), "reasoning_tokens": None} == vars(baseline)


@settings(max_examples=150, deadline=None)
@given(case=anthropic_responses())
def test_sync_and_batch_paths_record_the_same_counts(case):
    """Differential: one response through litellm and through the SDK."""
    body, thinking = case
    sync = _usage(_transformed(body))
    batch = _normalize_anthropic_entry(_batch_entry(body))

    # The sync path records a zero prompt or completion count as empty
    # (``0 or None`` in _extract_usage_metadata, as before this change).
    assert sync["prompt_tokens"] == (batch.prompt_tokens or None)
    assert sync["completion_tokens"] == (batch.completion_tokens or None)
    assert sync["cached_prompt_tokens"] == batch.cached_prompt_tokens
    assert sync["cache_write_prompt_tokens"] == batch.cache_write_prompt_tokens
    if thinking != ABSENT and thinking is not None and batch.completion_tokens:
        assert sync["reasoning_tokens"] == batch.reasoning_tokens


@given(
    reasoning=st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(2**40), max_value=2**40),
        st.floats(allow_nan=True, allow_infinity=True),
        st.text(max_size=5),
    ),
    completion=st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(2**40), max_value=2**40),
        st.floats(allow_nan=True, allow_infinity=True),
    ),
)
def test_bounded_reasoning_is_none_or_within_completion(reasoning, completion):
    bounded = _bounded_reasoning_tokens(reasoning, completion)

    assert bounded is None or (
        type(bounded) is int
        and not isinstance(completion, bool)
        and 0 <= bounded <= completion
    )


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
    ),
    outputs=st.integers(min_value=1, max_value=40),
)
def test_aggregated_rows_keep_reasoning_within_completion(requests, outputs):
    """A row sums its request group (repairs included) and splits it evenly
    over the group's outputs; neither step lets reasoning pass completion."""
    aggregate = _aggregate_request_results(
        [
            {"completion_tokens": completion, "reasoning_tokens": reasoning}
            for completion, reasoning in requests
        ]
    )
    reasoning = aggregate["reasoning_tokens"]
    completion = aggregate["completion_tokens"]

    if reasoning is not None:
        assert 0 <= reasoning <= completion
        assert reasoning / outputs <= completion / outputs
