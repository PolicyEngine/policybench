"""Each repeat of a repeated run asks the models again.

``policybench eval-no-tools-repeated`` turns the LiteLLM disk cache on, and
every repeat builds the same requests. LiteLLM keys the cache on the request,
so repeats 2..N used to get repeat 1's responses back from the cache and the
run reported no run-to-run variation. Each repeat now runs under its own
cache namespace (``_OwnCacheNamespace``).

These tests run the harness's repeated path through LiteLLM's real request
path and the harness's real disk cache (``enable_cache`` in a temporary
directory). Only the wire is replaced: ``httpx.Client.send`` answers from this
file with a value that names the call, and a socket connection fails the test.
"""

from __future__ import annotations

import json
import socket
from types import SimpleNamespace

import httpx
import litellm
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import policybench.eval_no_tools as eval_no_tools
from policybench.cache import enable_cache
from policybench.config import MODELS
from policybench.eval_no_tools import (
    REASONING_EFFORT_OVERRIDE_ENV,
    _answer_contract_for_model,
    _repeat_cache_namespace,
    _uses_responses_api,
    run_repeated_no_tools_eval,
)
from policybench.model_cards import MODEL_CARDS
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
# LiteLLM rewrites a gemini/ tool request's schema between its cache lookup
# and its store, so a rebuilt gemini/ tool request never finds its stored
# answer, repeat or not, until the harness pins the cache key. The tests that
# need a replay leave that group out; the others cover it.
REPLAYING = [
    model_id for model_id in REPRESENTATIVES if _group(model_id) != "gemini / tool"
]


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
    # Turning the cache on registers LiteLLM callbacks; give them back too.
    for name in ("input_callback", "success_callback", "_async_success_callback"):
        monkeypatch.setattr(litellm, name, list(getattr(litellm, name)))
    monkeypatch.setattr(litellm, "cache", None)


@pytest.fixture
def wire(monkeypatch) -> list[dict]:
    """The requests LiteLLM put on the wire, each answered from this file."""
    sent: list[dict] = []

    def send(self, request, **_kwargs):
        body = json.loads(request.content)
        sent.append({"path": request.url.path, "body": body})
        return httpx.Response(
            200,
            json=_canned_answer(request.url.path, body, len(sent)),
            request=request,
        )

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
                counts[kwargs["run_id"]] = (
                    counts.get(kwargs["run_id"], 0) + len(wire) - before
                )

        return run

    for name, runner in runners.items():
        monkeypatch.setattr(eval_no_tools, name, counting(runner))
    return counts


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


@pytest.mark.parametrize("model_id", REPRESENTATIVES)
def test_repeat_2_asks_again_when_repeat_1_is_cached(
    model_id, disk_cache, sent_per_repeat, tmp_path
):
    frame = _run(model_id, tmp_path / "runs")

    sent = sent_per_repeat
    assert sent["run_000"] > 0
    assert sent["run_001"] == sent["run_000"], (
        "repeat 2 got repeat 1's responses from the disk cache"
    )
    second = _calls(frame, "run_001")
    assert second["cache_hit_calls"].sum() == 0
    assert second["live_calls"].sum() == sent["run_001"]
    assert _raw(frame, "run_001") != _raw(frame, "run_000")


def test_a_single_output_repeat_asks_again(disk_cache, sent_per_repeat, tmp_path):
    model_id = REPLAYING[0]

    _run(model_id, tmp_path / "runs", single_output=True)

    assert sent_per_repeat["run_000"] > 0
    assert sent_per_repeat["run_001"] == sent_per_repeat["run_000"]


@pytest.mark.parametrize("model_id", REPLAYING)
def test_a_rerun_replays_each_repeats_own_responses(
    model_id, disk_cache, sent_per_repeat, wire, tmp_path, capsys
):
    first = _run(model_id, tmp_path / "first")
    one_repeat = sent_per_repeat["run_000"]
    sent_before = len(wire)
    sent_per_repeat.clear()
    capsys.readouterr()

    # A new output directory, so no CSV resume answers for the cache; one
    # more repeat than before.
    again = _run(model_id, tmp_path / "again", repeats=3)

    assert sent_per_repeat == {"run_000": 0, "run_001": 0, "run_002": one_repeat}
    assert len(wire) - sent_before == one_repeat
    for run_id in ("run_000", "run_001"):
        assert _raw(again, run_id) == _raw(first, run_id)
        replayed = _calls(again, run_id)
        assert replayed["live_calls"].sum() == 0
        assert replayed["cache_hit_calls"].sum() == one_repeat
    assert _raw(again, "run_001") != _raw(again, "run_000")
    assert _raw(again, "run_002") not in (
        _raw(again, "run_000"),
        _raw(again, "run_001"),
    )
    out = capsys.readouterr().out
    assert (
        f"run_001: 0 responses from the provider, {one_repeat} replayed from "
        "the disk cache"
    ) in out
    assert f"run_002: {one_repeat} responses from the provider, 0 replayed" in out


@pytest.mark.parametrize("model_id", REPRESENTATIVES)
def test_no_repeat_ever_returns_another_repeats_responses(
    model_id, disk_cache, wire, tmp_path
):
    """Across a run and a rerun on the same cache, an answer only ever comes
    back under the run id that first got it."""
    first = _run(model_id, tmp_path / "first")
    again = _run(model_id, tmp_path / "again", repeats=3)

    answers = {
        (label, run_id): _raw(frame, run_id)
        for label, frame in (("first", first), ("again", again))
        for run_id in sorted(set(frame["run_id"]))
    }
    assert len(answers) == 5
    assert all("value" in text for raw in answers.values() for text in raw)
    for (label, run_id), raw in answers.items():
        for (other_label, other_id), other in answers.items():
            if other_id != run_id:
                assert raw != other, (
                    f"{label} {run_id} returned {other_label} {other_id}'s responses"
                )


def test_the_cli_command_asks_again_on_repeat_2(monkeypatch, sent_per_repeat, tmp_path):
    """The command as the CLI runs it: the cache on, then two repeats."""
    from policybench.cli import main

    model_id = REPLAYING[0]
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
    second = pd.read_csv(tmp_path / "runs" / "run_001.csv")
    assert second["cache_hit_calls"].sum() == 0


def test_without_a_cache_every_repeat_asks(sent_per_repeat, tmp_path):
    assert litellm.cache is None

    _run(REPLAYING[0], tmp_path / "runs")

    assert sent_per_repeat["run_000"] > 0
    assert sent_per_repeat["run_001"] == sent_per_repeat["run_000"]


def test_an_effort_override_keeps_the_repeat_namespace(
    disk_cache, sent_per_repeat, tmp_path, monkeypatch
):
    """The override's own request namespace outranks the cache's, so it has
    to carry the repeat."""
    monkeypatch.setenv(REASONING_EFFORT_OVERRIDE_ENV, f"{OPUS}=high")
    stored: list[str] = []
    put = disk_cache.cache.set_cache

    def set_cache(key, value, **kwargs):
        stored.append(key)
        return put(key, value, **kwargs)

    monkeypatch.setattr(disk_cache.cache, "set_cache", set_cache)
    base = disk_cache.namespace

    _run(OPUS, tmp_path / "runs")

    assert sent_per_repeat["run_001"] == sent_per_repeat["run_000"] > 0
    for run_id in ("run_000", "run_001"):
        prefix = f"{_repeat_cache_namespace(base, run_id)}:{OPUS}:effort=high:"
        assert any(key.startswith(prefix) for key in stored), run_id


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
        _run(REPLAYING[0], tmp_path / "runs")

    assert seen == [_repeat_cache_namespace(base, "run_000")]
    assert litellm.cache.namespace == base


@settings(
    max_examples=60,
    deadline=None,
    # The autouse offline fixture holds for every example.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
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
                    "call_id": run_id,
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
