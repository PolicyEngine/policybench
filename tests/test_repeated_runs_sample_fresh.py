"""Each repeat of a repeated run asks the models again.

``policybench eval-no-tools-repeated`` turns the LiteLLM disk cache on, and
every repeat builds the same requests. LiteLLM keys the cache on the request,
so repeats 2..N used to get repeat 1's responses back from the cache for
every request whose stored answer a rebuilt request finds, and the run
reported no run-to-run variation. Each repeat now runs under its own cache
namespace (``_OwnCacheNamespace``).

Most tests run the harness's repeated path through LiteLLM's real request
path and replace only the wire: ``httpx.Client.send`` answers from this file
with a value that names the call. All but the no-cache control use the
harness's real disk cache (``enable_cache`` in a temporary directory). The
autouse fixture blocks sockets while each test runs and gives every request
one attempt (``MAX_ATTEMPTS``). It cannot reach LiteLLM's model-cost map,
which LiteLLM loads when it is first imported, before any fixture; set
``LITELLM_LOCAL_MODEL_COST_MAP=True`` to keep that load off the network.
Fixtures count requests per repeat and, where a test asks for them, record
the cache keys each repeat looks up and stores.

Six test functions send no request: the namespace's spelling, the guard
against unrecorded files (each case), the response counter, the overlap
guard, and the two that check the namespace comes back (they replace the
runner; the property test replaces the cache object too).
"""

from __future__ import annotations

import json
import os
import socket
from types import SimpleNamespace

import httpx
import litellm
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import policybench.eval_no_tools as eval_no_tools
from policybench.cache import enable_cache
from policybench.config import MODELS
from policybench.eval_no_tools import (
    EXPLANATION_FUNCTION_NAME,
    REASONING_EFFORT_OVERRIDE_ENV,
    REPEATED_RUN_MARKER,
    _answer_contract_for_model,
    _OwnCacheNamespace,
    _repeat_cache_namespace,
    _response_sources,
    _uses_responses_api,
    run_repeated_no_tools_eval,
)
from policybench.model_cards import MODEL_CARDS, explanation_chunk_size_for
from policybench.scenarios import Person, Scenario

SCENARIO = Scenario(
    id="repeat_household",
    state="CA",
    filing_status="single",
    adults=[Person(name="adult1", age=35, employment_income=18_000.0)],
    year=2026,
)
VARIABLES = ["snap", "ssi"]
OPUS = "claude-opus-5-5"

PROVIDER_KEY_VARIABLES = (
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "XAI_API_KEY",
)
SENSITIVITY_VARIABLES = (
    REASONING_EFFORT_OVERRIDE_ENV,
    "LITELLM_DROP_PARAMS",
    "POLICYBENCH_CHUNK_OVERRIDE",
    "POLICYBENCH_CONTRACT_OVERRIDE",
    "POLICYBENCH_TOOL_CHOICE",
)


def _group(model_id: str) -> str:
    """The provider path and answer contract a model's requests take."""
    if _uses_responses_api(model_id):
        provider = "openai responses"
    elif model_id.startswith("claude-"):
        provider = "anthropic"
    else:
        provider = model_id.split("/", 1)[0]
    return f"{provider} / {_answer_contract_for_model(model_id, env={})}"


def _name_of(model_id: str) -> str:
    names = {card.litellm_id: name for name, card in MODEL_CARDS.items()}
    names.update({litellm_id: name for name, litellm_id in MODELS.items()})
    return names[model_id]


GROUPS: dict[str, list[str]] = {}
for _model_id in sorted(card.litellm_id for card in MODEL_CARDS.values()):
    GROUPS.setdefault(_group(_model_id), []).append(_model_id)
# One card per provider path and answer contract; a new one joins without an
# edit here.
REPRESENTATIVES = [ids[0] for _, ids in sorted(GROUPS.items())]
assert REPRESENTATIVES, "no model card to run the repeat tests on"
# The follow-up-path tests read the requested outputs from the request's
# Anthropic tool schema, and need a card that asks for every output at once.
ANTHROPIC_TOOL = next(
    model_id
    for model_id in GROUPS["anthropic / tool"]
    if explanation_chunk_size_for(model_id) is None
)


def _answer(call: int) -> dict:
    value = 1000 + call
    return {
        "outputs": {
            variable: {"value": value, "explanation": f"Call {call}. value = {value}"}
            for variable in VARIABLES
        }
    }


def _tool_name(body: dict) -> str | None:
    for tool in body.get("tools") or []:
        declarations = tool.get("functionDeclarations") or tool.get(
            "function_declarations"
        )
        if declarations:
            return declarations[0]["name"]
        if "function" in tool:
            return tool["function"]["name"]
        if "name" in tool:
            return tool["name"]
    return None


def _canned_answer(path: str, body: dict, call: int) -> dict:
    """A provider-shaped answer whose values name the call that made it."""
    tool = _tool_name(body)
    arguments = _answer(call)
    text = json.dumps(arguments)
    if ":generateContent" in path:
        part = (
            {"functionCall": {"name": tool, "args": arguments}}
            if tool
            else {"text": text}
        )
        return {
            "candidates": [
                {
                    "content": {"role": "model", "parts": [part]},
                    "finishReason": "STOP",
                    "index": 0,
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 5,
                "totalTokenCount": 15,
            },
            "modelVersion": "stub",
            "responseId": f"stub-{call}",
        }
    if path.endswith("/messages"):
        content = (
            [
                {
                    "type": "tool_use",
                    "id": f"toolu_{call}",
                    "name": tool,
                    "input": arguments,
                }
            ]
            if tool
            else [{"type": "text", "text": text}]
        )
        return {
            "id": f"stub-{call}",
            "type": "message",
            "role": "assistant",
            "model": body.get("model", "stub"),
            "content": content,
            "stop_reason": "tool_use" if tool else "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
    if path.endswith("/responses"):
        return {
            "id": f"stub-{call}",
            "object": "response",
            "created_at": 1_795_000_000,
            "status": "completed",
            "model": body.get("model", "stub"),
            "output": [
                {
                    "type": "function_call",
                    "id": f"fc_{call}",
                    "call_id": f"call_{call}",
                    "name": tool,
                    "arguments": text,
                    "status": "completed",
                }
            ],
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "error": None,
            "incomplete_details": None,
            "instructions": None,
            "metadata": {},
            "temperature": 1.0,
            "top_p": 1.0,
            "truncation": "disabled",
            "text": {"format": {"type": "text"}},
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        }
    if path.endswith("/chat/completions"):
        message = (
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call_{call}",
                        "type": "function",
                        "function": {"name": tool, "arguments": text},
                    }
                ],
            }
            if tool
            else {"role": "assistant", "content": text}
        )
        return {
            "id": f"stub-{call}",
            "object": "chat.completion",
            "created": 1_795_000_000,
            "model": body.get("model", "stub"),
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": "tool_calls" if tool else "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
    raise AssertionError(f"the stub has no answer for the path {path}")


def _anthropic_message(call: int, body: dict, content: list, stop_reason: str):
    return {
        "id": f"stub-{call}",
        "type": "message",
        "role": "assistant",
        "model": body.get("model", "stub"),
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


class _FollowUpAnswers:
    """Anthropic tool answers that send each household down one follow-up path.

    - ``repair``: a request for several outputs gets the first one only, so
      the harness asks again for the rest (a repair round).
    - ``chunk``: plain answers; the test sets a chunk size of one output.
    - ``escalation``: a request at the first completion budget it sees stops
      on the length limit with nothing in it, so the harness asks again with
      a larger budget.
    - ``explanation``: values with blank explanations; with no repair round
      left, the harness asks for the explanations alone.

    Each household's answer depends only on the request, not on the order
    requests arrive in, so a repeat that asks again takes the same path.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.first_budget: int | None = None
        self.values: dict[str, float] = {}

    def __call__(self, url_path: str, body: dict, call: int) -> dict:
        assert url_path.endswith("/messages"), url_path
        (tool,) = body["tools"]
        schema = tool["input_schema"]["properties"]
        value = 1000 + call
        if tool["name"] == EXPLANATION_FUNCTION_NAME:
            explanations = {
                variable: f"Call {call}. value = {self.values[variable]:g}"
                for variable in schema
            }
            return _anthropic_message(
                call,
                body,
                [
                    {
                        "type": "tool_use",
                        "id": f"toolu_{call}",
                        "name": tool["name"],
                        "input": explanations,
                    }
                ],
                "tool_use",
            )
        asked = list(schema["outputs"]["properties"])
        if self.path == "escalation":
            if self.first_budget is None:
                self.first_budget = body["max_tokens"]
            if body["max_tokens"] == self.first_budget:
                return _anthropic_message(call, body, [], "max_tokens")
        if self.path == "repair":
            asked = asked[:1]
        self.values.update(dict.fromkeys(asked, value))
        explanation = (
            "" if self.path == "explanation" else f"Call {call}. value = {value}"
        )
        outputs = {
            variable: {"value": value, "explanation": explanation} for variable in asked
        }
        return _anthropic_message(
            call,
            body,
            [
                {
                    "type": "tool_use",
                    "id": f"toolu_{call}",
                    "name": tool["name"],
                    "input": {"outputs": outputs},
                }
            ],
            "tool_use",
        )


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No key, no socket, no sensitivity knob, one attempt per request."""

    def refuse(*_args, **_kwargs):
        raise AssertionError("a test tried to open a socket")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    for name in PROVIDER_KEY_VARIABLES:
        monkeypatch.setenv(name, "test-value-not-a-key")
    for name in SENSITIVITY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(eval_no_tools, "_PROCESS_REASONING_EFFORT_OVERRIDE", [])
    monkeypatch.setattr(eval_no_tools, "MAX_ATTEMPTS", 1)
    monkeypatch.setattr(litellm, "drop_params", False)
    # Turning the cache on registers LiteLLM callbacks, and LiteLLM moves
    # callbacks between its lists; give every list back.
    for name, value in list(vars(litellm).items()):
        if "callback" in name and isinstance(value, list):
            monkeypatch.setattr(litellm, name, list(value))
    # LiteLLM remembers which callbacks it has set up in this module global.
    monkeypatch.setattr(
        litellm.utils, "callback_list", list(litellm.utils.callback_list or [])
    )
    monkeypatch.setattr(litellm, "cache", None)


@pytest.fixture(autouse=True)
def safe_umask():
    """The cache guard refuses a umask that lets others write the cache."""
    previous = os.umask(0o022)
    yield
    os.umask(previous)


class _Wire(list):
    """The requests LiteLLM put on the wire.

    ``answer(path, body, call)`` builds each response: a provider-shaped body,
    or a ``(status, body)`` pair for an error.
    """

    answer = staticmethod(_canned_answer)


@pytest.fixture
def wire(monkeypatch) -> _Wire:
    """The requests LiteLLM put on the wire, each answered from this file."""
    sent = _Wire()

    def send(self, request, **_kwargs):
        body = json.loads(request.content)
        sent.append({"path": request.url.path, "body": body})
        answer = sent.answer(request.url.path, body, len(sent))
        status, payload = answer if isinstance(answer, tuple) else (200, answer)
        return httpx.Response(status, json=payload, request=request)

    def no_async_send(self, request, **_kwargs):
        raise AssertionError("the harness sends no asynchronous request")

    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setattr(httpx.AsyncClient, "send", no_async_send)
    return sent


@pytest.fixture
def disk_cache(tmp_path):
    """The harness's disk cache, on in a temporary directory."""
    enable_cache(str(tmp_path / "cache"))
    return litellm.cache


@pytest.fixture
def sent_per_repeat(monkeypatch, wire) -> dict[str, int]:
    """How many requests each repeat put on the wire, by run id."""
    counts: dict[str, int] = {}
    runners = {
        name: getattr(eval_no_tools, name)
        for name in ("run_no_tools_eval", "run_no_tools_single_output_eval")
    }

    def counting(runner):
        def run(*args, **kwargs):
            before = len(wire)
            try:
                return runner(*args, **kwargs)
            finally:
                run_id = kwargs.get("run_id")
                counts[run_id] = counts.get(run_id, 0) + len(wire) - before

        return run

    for name, runner in runners.items():
        monkeypatch.setattr(eval_no_tools, name, counting(runner))
    return counts


@pytest.fixture
def keys_per_repeat(monkeypatch, disk_cache) -> dict[str | None, list[tuple[str, str]]]:
    """The keys LiteLLM looked up and stored in the disk cache, by run id."""
    keys: dict[str | None, list[tuple[str, str]]] = {}
    running: list[str | None] = [None]
    get, put = disk_cache.cache.get_cache, disk_cache.cache.set_cache

    def get_cache(key, **kwargs):
        keys.setdefault(running[-1], []).append(("lookup", key))
        return get(key, **kwargs)

    def set_cache(key, value, **kwargs):
        keys.setdefault(running[-1], []).append(("store", key))
        return put(key, value, **kwargs)

    monkeypatch.setattr(disk_cache.cache, "get_cache", get_cache)
    monkeypatch.setattr(disk_cache.cache, "set_cache", set_cache)

    def tracking(runner):
        def run(*args, **kwargs):
            running.append(kwargs.get("run_id"))
            try:
                return runner(*args, **kwargs)
            finally:
                running.pop()

        return run

    for name in ("run_no_tools_eval", "run_no_tools_single_output_eval"):
        monkeypatch.setattr(eval_no_tools, name, tracking(getattr(eval_no_tools, name)))
    return keys


def _run(model_id: str, output_dir, repeats: int = 2, **kwargs) -> pd.DataFrame:
    return run_repeated_no_tools_eval(
        [SCENARIO],
        repeats=repeats,
        output_dir=str(output_dir),
        models={_name_of(model_id): model_id},
        programs=VARIABLES,
        **kwargs,
    )


def _calls(frame: pd.DataFrame, run_id: str) -> pd.DataFrame:
    return frame[frame["run_id"] == run_id].drop_duplicates("call_id")


def _raw(frame: pd.DataFrame, run_id: str) -> list[str]:
    return frame[frame["run_id"] == run_id]["raw_response"].tolist()


def _assert_answered(frame: pd.DataFrame) -> None:
    """The stub's answers parsed, so no repair round ran."""
    assert frame["error"].isna().all(), frame["error"].dropna().iloc[0]
    assert frame["prediction"].notna().all()


@pytest.mark.parametrize("model_id", REPRESENTATIVES)
def test_repeat_2_asks_again_when_repeat_1_is_cached(
    model_id, disk_cache, sent_per_repeat, keys_per_repeat, tmp_path
):
    base = disk_cache.namespace

    frame = _run(model_id, tmp_path / "runs")

    _assert_answered(frame)
    sent = sent_per_repeat
    assert sent["run_000"] > 0
    assert sent["run_001"] == sent["run_000"], (
        "repeat 2 got repeat 1's responses from the disk cache"
    )
    second = _calls(frame, "run_001")
    assert second["cache_hit_calls"].sum() == 0
    assert second["live_calls"].sum() == sent["run_001"]
    assert _raw(frame, "run_001") != _raw(frame, "run_000")
    # Every key a repeat looks up or stores sits under its own namespace,
    # whether or not the cache can find the answer again later.
    assert set(keys_per_repeat) == {"run_000", "run_001"}
    for run_id, used in keys_per_repeat.items():
        assert {kind for kind, _ in used} == {"lookup", "store"}
        prefix = f"{_repeat_cache_namespace(base, run_id)}:"
        assert all(key.startswith(prefix) for _, key in used), run_id


def test_the_repeat_namespace_is_spelled_out():
    """A rerun finds a repeat's answers only while this spelling holds."""
    assert (
        _repeat_cache_namespace("policybench:x", "run_000")
        == "policybench:x:repeat=run_000"
    )
    assert _repeat_cache_namespace(None, "run_007") == "repeat=run_007"
    assert _repeat_cache_namespace("", "run_007") == "repeat=run_007"


def test_a_single_output_repeat_asks_again(
    disk_cache, sent_per_repeat, keys_per_repeat, tmp_path
):
    base = disk_cache.namespace

    frame = _run(OPUS, tmp_path / "runs", single_output=True)

    _assert_answered(frame)
    # One request per output, so the single-output runner ran, not the batch
    # runner (one request for the household).
    assert sent_per_repeat == {"run_000": len(VARIABLES), "run_001": len(VARIABLES)}
    assert _calls(frame, "run_001")["cache_hit_calls"].sum() == 0
    assert set(_raw(frame, "run_001")).isdisjoint(_raw(frame, "run_000"))
    # Both repeats used the disk cache, each under its own namespace.
    assert set(keys_per_repeat) == {"run_000", "run_001"}
    for run_id, used in keys_per_repeat.items():
        assert {kind for kind, _ in used} == {"lookup", "store"}
        prefix = f"{_repeat_cache_namespace(base, run_id)}:"
        assert all(key.startswith(prefix) for _, key in used), run_id


def _request_shape(body: dict) -> tuple[str, tuple[str, ...], int]:
    """An Anthropic tool request's tool, the outputs it asks for, and its
    completion budget."""
    (tool,) = body["tools"]
    schema = tool["input_schema"]["properties"]
    if tool["name"] == EXPLANATION_FUNCTION_NAME:
        return "explanation", tuple(schema), body["max_tokens"]
    return "answer", tuple(schema["outputs"]["properties"]), body["max_tokens"]


@pytest.mark.parametrize("path", ["repair", "chunk", "escalation", "explanation"])
def test_a_follow_up_request_asks_again_under_its_repeats_namespace(
    path, monkeypatch, disk_cache, wire, sent_per_repeat, keys_per_repeat, tmp_path
):
    """A repair round, explanation chunks, a larger completion budget and
    the explanation-only request each go out again in repeat 2, under its
    namespace."""
    if path == "chunk":
        monkeypatch.setattr(
            eval_no_tools, "_required_explanation_chunk_size", lambda *_a, **_k: 1
        )
    if path == "explanation":
        monkeypatch.setattr(eval_no_tools, "MAX_REPAIR_ROUNDS", 0)
    wire.answer = _FollowUpAnswers(path)
    base = disk_cache.namespace

    frame = _run(ANTHROPIC_TOOL, tmp_path / "runs")

    _assert_answered(frame)
    assert frame["explanation"].fillna("").str.strip().ne("").all()
    # Two requests a repeat: the household's first and the follow-up the
    # path names. A plain answer would take one.
    assert sent_per_repeat == {"run_000": 2, "run_001": 2}
    shapes = [_request_shape(request["body"]) for request in wire]
    first, follow_up = {
        "repair": (("answer", ("snap", "ssi")), ("answer", ("ssi",))),
        "chunk": (("answer", ("snap",)), ("answer", ("ssi",))),
        "escalation": (("answer", ("snap", "ssi")), ("answer", ("snap", "ssi"))),
        "explanation": (("answer", ("snap", "ssi")), ("explanation", ("snap", "ssi"))),
    }[path]
    assert [shape[:2] for shape in shapes] == [first, follow_up] * 2
    budgets = [shape[2] for shape in shapes]
    if path == "escalation":
        assert budgets[1] > budgets[0] and budgets[2:] == budgets[:2]
    second = _calls(frame, "run_001")
    assert second["live_calls"].sum() == 2
    assert second["cache_hit_calls"].sum() == 0
    assert set(_raw(frame, "run_001")).isdisjoint(_raw(frame, "run_000"))
    for run_id, used in keys_per_repeat.items():
        assert sum(kind == "lookup" for kind, _ in used) == 2, run_id
        prefix = f"{_repeat_cache_namespace(base, run_id)}:"
        assert all(key.startswith(prefix) for _, key in used), run_id


def _a_rebuilt_request_replays(
    model_id: str, output_dir, wire: list, monkeypatch
) -> tuple[bool, bool]:
    """Whether a plain run's rebuilt requests find their stored answers, and
    whether the harness handed LiteLLM a cache key for every request.

    Two ``eval-no-tools`` runs of the same household on the cache, outside any
    repeat. LiteLLM rewrites a ``gemini/`` tool request's schema between its
    cache lookup and its store, so unless the harness pins each request's
    cache key, that group's rebuilt request never finds its answer, repeat or
    not.
    """
    keyed: list[bool] = []

    def spying(request_fn):
        def request(*args, **kwargs):
            keyed.append("cache_key" in kwargs)
            return request_fn(*args, **kwargs)

        return request

    for name in ("completion", "responses"):
        monkeypatch.setattr(eval_no_tools, name, spying(getattr(eval_no_tools, name)))

    def plain(name: str) -> int:
        before = len(wire)
        eval_no_tools.run_no_tools_eval(
            [SCENARIO],
            models={_name_of(model_id): model_id},
            programs=VARIABLES,
            output_path=str(output_dir / f"{name}.csv"),
        )
        return len(wire) - before

    first, second = plain("plain_1"), plain("plain_2")
    assert first > 0 and second in (0, first)
    assert keyed
    return second == 0, all(keyed)


@pytest.mark.parametrize("model_id", REPRESENTATIVES)
def test_a_rerun_replays_each_repeats_own_responses(
    model_id, disk_cache, sent_per_repeat, wire, tmp_path, capsys, monkeypatch
):
    """A rerun's repeats replay exactly when a plain rebuilt request does, and
    then each replays its own answers. The namespace scopes the cache; it
    does not decide whether the cache can find an answer."""
    replays, keys_pinned = _a_rebuilt_request_replays(
        model_id, tmp_path, wire, monkeypatch
    )
    # Only a gemini/ tool request may fail to replay, and only while the
    # harness leaves the cache key to LiteLLM.
    assert replays or (_group(model_id) == "gemini / tool" and not keys_pinned)
    first = _run(model_id, tmp_path / "first")
    _assert_answered(first)
    one_repeat = sent_per_repeat["run_000"]
    assert sent_per_repeat["run_001"] == one_repeat > 0, (
        "a repeat replayed the plain run's answers, or another repeat's"
    )
    sent_before = len(wire)
    sent_per_repeat.clear()
    capsys.readouterr()

    # As a new process would: a new cache object on the same directory. And a
    # new output directory, so no CSV resume answers for the cache; one more
    # repeat than before.
    enable_cache(str(tmp_path / "cache"))
    assert litellm.cache is not disk_cache
    again = _run(model_id, tmp_path / "again", repeats=3)

    rerun = 0 if replays else one_repeat
    assert sent_per_repeat == {
        "run_000": rerun,
        "run_001": rerun,
        "run_002": one_repeat,
    }
    assert len(wire) - sent_before == 2 * rerun + one_repeat
    assert set(_raw(again, "run_002")).isdisjoint(
        _raw(again, "run_000") + _raw(again, "run_001")
    )
    assert set(_raw(again, "run_001")).isdisjoint(_raw(again, "run_000"))
    out = capsys.readouterr().out
    assert f"run_002: provider responses {one_repeat}, cache replays 0\n" in out
    if replays:
        for run_id in ("run_000", "run_001"):
            assert _raw(again, run_id) == _raw(first, run_id)
            replayed = _calls(again, run_id)
            assert replayed["live_calls"].sum() == 0
            assert replayed["cache_hit_calls"].sum() == one_repeat
        assert f"run_001: provider responses 0, cache replays {one_repeat}\n" in out


@pytest.mark.parametrize("model_id", REPRESENTATIVES)
def test_no_repeat_ever_returns_another_repeats_responses(
    model_id, disk_cache, wire, tmp_path
):
    """Across a run and a rerun on the same cache, an answer only ever comes
    back under the run id that first got it."""
    first = _run(model_id, tmp_path / "first")
    again = _run(model_id, tmp_path / "again", repeats=3)

    answers = {
        (label, run_id): set(_raw(frame, run_id))
        for label, frame in (("first", first), ("again", again))
        for run_id in sorted(set(frame["run_id"]))
    }
    assert len(answers) == 5
    assert all("value" in text for raw in answers.values() for text in raw)
    for (label, run_id), raw in answers.items():
        for (other_label, other_id), other in answers.items():
            if other_id != run_id:
                shared = raw & other
                assert not shared, (
                    f"{label} {run_id} returned {len(shared)} of "
                    f"{other_label} {other_id}'s responses"
                )


def test_the_cli_command_asks_again_on_repeat_2(monkeypatch, sent_per_repeat, tmp_path):
    """The command as the CLI runs it: the cache on, then two repeats."""
    from policybench.cli import main

    model_id = OPUS
    assert MODELS[_name_of(model_id)] == model_id
    monkeypatch.setattr("policybench.cache.CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(
        "policybench.cli._load_eval_scenarios", lambda _args: [SCENARIO]
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "policybench",
            "eval-no-tools-repeated",
            "--num-scenarios",
            "1",
            "--repeats",
            "2",
            "--model",
            _name_of(model_id),
            "--program",
            "snap",
            "--program",
            "ssi",
            "--output-dir",
            str(tmp_path / "runs"),
        ],
    )

    main()

    assert litellm.cache is not None, "the command no longer turns the cache on"
    assert (tmp_path / "cache" / "cache.db").exists()
    assert sent_per_repeat["run_000"] > 0
    assert sent_per_repeat["run_001"] == sent_per_repeat["run_000"]
    first = pd.read_csv(tmp_path / "runs" / "run_000.csv")
    second = pd.read_csv(tmp_path / "runs" / "run_001.csv")
    assert second["cache_hit_calls"].sum() == 0
    assert second["raw_response"].tolist() != first["raw_response"].tolist()
    assert (tmp_path / "runs" / REPEATED_RUN_MARKER).exists()


def test_a_rerun_into_the_same_directory_resumes_and_says_so(
    disk_cache, sent_per_repeat, tmp_path, capsys
):
    first = _run(OPUS, tmp_path / "runs")
    one_repeat = sent_per_repeat["run_000"]
    out = capsys.readouterr().out
    assert f"run_000: provider responses {one_repeat}, cache replays 0\n" in out
    assert "resumed" not in out
    sent_per_repeat.clear()

    again = _run(OPUS, tmp_path / "runs")

    assert sent_per_repeat == {"run_000": 0, "run_001": 0}
    for run_id in ("run_000", "run_001"):
        assert _raw(again, run_id) == _raw(first, run_id)
    out = capsys.readouterr().out
    assert (
        f"run_001: provider responses {one_repeat}, cache replays 0; of these, "
        f"kept from run_001.csv: provider responses {one_repeat}, cache replays 0\n"
    ) in out
    record = json.loads((tmp_path / "runs" / REPEATED_RUN_MARKER).read_text())
    assert record == {"repeats_with_own_cache_namespace": ["run_000", "run_001"]}


@pytest.mark.parametrize("left_by", ["fatal error", "infrastructure error"])
def test_a_resume_that_keeps_no_row_does_not_say_it_kept_any(
    left_by, disk_cache, wire, sent_per_repeat, tmp_path, capsys
):
    """The repeat's file exists, but the runner keeps none of its rows, so the
    line names no kept rows."""
    runs = tmp_path / "runs"
    if left_by == "fatal error":
        # A rejected key stops the model with no row; the command then writes
        # a CSV holding a header only. Nothing was cached.
        wire.answer = lambda *_args: (
            401,
            {
                "type": "error",
                "error": {"type": "authentication_error", "message": "bad key"},
            },
        )
        _run(ANTHROPIC_TOOL, runs, repeats=1)
        assert (runs / "run_000.csv").read_text().strip() == "run_id"
        expected = ({"run_000": 1}, "provider responses 1, cache replays 0")
    else:
        # Rows whose error the loader counts as infrastructure, as an
        # interrupted or older run can leave. The answer is in the cache.
        _run(ANTHROPIC_TOOL, runs, repeats=1)
        rows = pd.read_csv(runs / "run_000.csv")
        rows["error"] = "litellm.Timeout: request timed out"
        rows.to_csv(runs / "run_000.csv", index=False)
        expected = ({"run_000": 0}, "provider responses 0, cache replays 1")
    assert sent_per_repeat["run_000"] > 0
    sent_per_repeat.clear()
    capsys.readouterr()
    wire.answer = staticmethod(_canned_answer)

    again = _run(ANTHROPIC_TOOL, runs, repeats=1)

    _assert_answered(again)
    sent, counts = expected
    assert sent_per_repeat == sent
    out = capsys.readouterr().out
    assert f"run_000: {counts}\n" in out
    assert "kept from" not in out


def test_a_repeat_file_the_marker_does_not_record_is_refused(
    disk_cache, wire, sent_per_repeat, tmp_path
):
    """The marker does not vouch for a directory, only for the repeats it
    lists: here a run without per-repeat namespaces, as an earlier version of
    the command ran, adds a repeat file beside a recorded one."""
    runs = tmp_path / "runs"
    _run(OPUS, runs, repeats=1)
    eval_no_tools.run_no_tools_eval(
        [SCENARIO],
        models={_name_of(OPUS): OPUS},
        programs=VARIABLES,
        output_path=str(runs / "run_001.csv"),
        run_id="run_001",
    )
    sent = len(wire)
    record = (runs / REPEATED_RUN_MARKER).read_text()

    with pytest.raises(ValueError, match=r"run_001\.csv.*Use a new output directory"):
        _run(OPUS, runs, repeats=3)

    assert len(wire) == sent
    assert (runs / REPEATED_RUN_MARKER).read_text() == record
    assert not (runs / "run_002.csv").exists()


@pytest.mark.parametrize(
    "marker",
    [
        None,
        '{"repeats_with_own_cache_namespace": ["run_000"]}',
        '{"each_repeat_has_its_own_cache_namespace": true}',
        '{"repeats_with_own_cache_namespace": "run_000"}',
        "not json",
    ],
)
def test_repeat_files_without_a_record_are_refused_before_any_request(
    marker, monkeypatch, tmp_path
):
    """A file the marker does not list, here one past the repeats asked for,
    or a marker that cannot be read: the command sends nothing."""
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "run_000.csv").write_text("model,scenario_id,variable,prediction\n")
    (runs / "run_005.csv").write_text("model,scenario_id,variable,prediction\n")
    if marker is not None:
        (runs / REPEATED_RUN_MARKER).write_text(marker)
    called = []
    monkeypatch.setattr(
        eval_no_tools, "run_no_tools_eval", lambda *a, **k: called.append(k)
    )

    with pytest.raises(ValueError, match="Use a new output directory"):
        _run(OPUS, runs)

    assert not called
    if marker is None:
        assert not (runs / REPEATED_RUN_MARKER).exists()
    else:
        assert (runs / REPEATED_RUN_MARKER).read_text() == marker


def test_response_sources_counts_each_request_group_once():
    batch = [
        # Model "a" and household "b:c", and model "a:b" and household "c",
        # share the call id "run_000:a:b:c"; they are two request groups.
        {
            "model": "a",
            "scenario_id": "b:c",
            "variable": "snap",
            "live_calls": 2,
            "cache_hit_calls": 0,
        },
        {
            "model": "a",
            "scenario_id": "b:c",
            "variable": "ssi",
            "live_calls": 2,
            "cache_hit_calls": 0,
        },
        {
            "model": "a:b",
            "scenario_id": "c",
            "variable": "snap",
            "live_calls": 1,
            "cache_hit_calls": 0,
        },
        {
            "model": "a:b",
            "scenario_id": "d",
            "variable": "snap",
            "live_calls": 0,
            "cache_hit_calls": 1,
        },
        {
            "model": "a:b",
            "scenario_id": "e",
            "variable": "snap",
            "live_calls": 1,
            "cache_hit_calls": None,
        },
        {
            "model": "a:b",
            "scenario_id": "f",
            "variable": "snap",
            "live_calls": None,
            "cache_hit_calls": None,
        },
    ]
    frame = pd.DataFrame(batch)
    for row in batch:
        row["call_id"] = ":".join(["run_000", row["model"], row["scenario_id"]])
    assert _response_sources(pd.DataFrame(batch)) == (3, 1, 2)
    assert _response_sources(frame) == (3, 1, 2)
    # One output a request in the single-output runner.
    assert _response_sources(frame, single_output=True) == (5, 1, 2)
    no_counts = pd.DataFrame([{"model": "a", "scenario_id": "b", "variable": "snap"}])
    assert _response_sources(no_counts) == (0, 0, 1)
    assert _response_sources(pd.DataFrame()) == (0, 0, 0)


def test_repeats_cannot_overlap_in_one_process(disk_cache):
    base = disk_cache.namespace
    with _OwnCacheNamespace("run_000"):
        with pytest.raises(RuntimeError, match="another repeat is running"):
            with _OwnCacheNamespace("run_001"):
                pass
        assert disk_cache.namespace == _repeat_cache_namespace(base, "run_000")
    assert disk_cache.namespace == base
    with _OwnCacheNamespace("run_001"):
        assert disk_cache.namespace == _repeat_cache_namespace(base, "run_001")
    assert disk_cache.namespace == base


def test_without_a_cache_every_repeat_asks(sent_per_repeat, tmp_path):
    assert litellm.cache is None

    _run(OPUS, tmp_path / "runs")

    assert sent_per_repeat["run_000"] > 0
    assert sent_per_repeat["run_001"] == sent_per_repeat["run_000"]


def test_an_effort_override_keeps_the_repeat_namespace(
    disk_cache, sent_per_repeat, keys_per_repeat, tmp_path, monkeypatch
):
    """The override's own request namespace outranks the cache's, so it has
    to carry the repeat: for the lookup, the store, and a rerun's replay."""
    monkeypatch.setenv(REASONING_EFFORT_OVERRIDE_ENV, f"{OPUS}=high")
    base = disk_cache.namespace

    first = _run(OPUS, tmp_path / "runs")

    one_repeat = sent_per_repeat["run_000"]
    assert sent_per_repeat["run_001"] == one_repeat > 0
    assert set(keys_per_repeat) == {"run_000", "run_001"}
    for run_id, used in keys_per_repeat.items():
        assert {kind for kind, _ in used} == {"lookup", "store"}
        prefix = f"{_repeat_cache_namespace(base, run_id)}:{OPUS}:effort=high:"
        assert all(key.startswith(prefix) for _, key in used), run_id
    sent_per_repeat.clear()

    enable_cache(str(tmp_path / "cache"))
    again = _run(OPUS, tmp_path / "again")

    assert sent_per_repeat == {"run_000": 0, "run_001": 0}
    for run_id in ("run_000", "run_001"):
        assert _raw(again, run_id) == _raw(first, run_id)


def test_the_cache_namespace_comes_back_when_a_repeat_fails(
    disk_cache, monkeypatch, tmp_path
):
    base = disk_cache.namespace
    seen: list[str] = []

    def failing(*_args, run_id, **_kwargs):
        seen.append(litellm.cache.namespace)
        raise RuntimeError("provider down")

    monkeypatch.setattr(eval_no_tools, "run_no_tools_eval", failing)

    with pytest.raises(RuntimeError, match="provider down"):
        _run(OPUS, tmp_path / "runs")

    assert seen == [_repeat_cache_namespace(base, "run_000")]
    assert litellm.cache.namespace == base


@settings(max_examples=60, deadline=None)
@given(
    base=st.one_of(st.none(), st.text(min_size=1, max_size=40)),
    repeats=st.integers(min_value=1, max_value=6),
    fail_at=st.one_of(st.none(), st.integers(min_value=0, max_value=5)),
)
def test_repeats_get_distinct_namespaces_and_the_base_comes_back(
    base, repeats, fail_at, tmp_path_factory
):
    """For any base namespace, repeat count and failing repeat: each repeat
    that runs sees its own namespace, built on the base, and the cache's
    namespace is the base again afterwards."""
    output_dir = tmp_path_factory.mktemp("runs")
    cache = SimpleNamespace(namespace=base)
    seen: dict[str, str] = {}

    def runner(*_args, run_id, **_kwargs):
        seen[run_id] = litellm.cache.namespace
        if fail_at is not None and int(run_id.split("_")[1]) == fail_at:
            raise RuntimeError("provider down")
        return pd.DataFrame(
            [
                {
                    "run_id": run_id,
                    "model": "a",
                    "scenario_id": SCENARIO.id,
                    "variable": "snap",
                    "live_calls": 1,
                    "cache_hit_calls": 0,
                }
            ]
        )

    saved = (litellm.cache, eval_no_tools.run_no_tools_eval)
    litellm.cache, eval_no_tools.run_no_tools_eval = cache, runner
    try:
        try:
            run_repeated_no_tools_eval(
                [SCENARIO], repeats=repeats, output_dir=str(output_dir)
            )
        except RuntimeError:
            assert fail_at is not None and fail_at < repeats
        else:
            assert fail_at is None or fail_at >= repeats
        assert cache.namespace == base
    finally:
        litellm.cache, eval_no_tools.run_no_tools_eval = saved

    ran = min(repeats, repeats if fail_at is None else fail_at + 1)
    assert list(seen) == [f"run_{index:03d}" for index in range(ran)]
    assert len(set(seen.values())) == ran
    for run_id, namespace in seen.items():
        assert namespace == _repeat_cache_namespace(base, run_id)
        assert namespace.endswith(f"repeat={run_id}")
        if base:
            assert namespace.startswith(f"{base}:")
