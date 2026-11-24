"""A freshly built request replays from the LiteLLM disk cache.

The supervisor re-sends a household whose worker failed, and the new worker
builds every request again. The harness counts on LiteLLM's disk cache to
answer the requests it has already paid for, which works only when the key
LiteLLM looks up for a freshly built request is the key it stored the first
answer under.

For a ``gemini/`` request that carries a tool it was not. When a call with no
pinned key misses the cache and goes on to store its response, LiteLLM computes
the key twice from the keyword arguments it is given, once to look an answer up
before the call and once to store the answer after it, and in between it
rewrites the board's tool schemas in place (it
drops ``additionalProperties: false``, and the integer ``enum`` of the 0/1
outputs). The harness now hands LiteLLM a copy of the request and pins the key
of the request as built (``_litellm_call_kwargs``).

These are unit tests. The replay tests run LiteLLM's own request path
(parameter mapping, the provider's request transformation, the cache lookup
and store) and replace only the wire: ``httpx.Client.send`` answers from this
file. The tests of the wrapper alone use a synthetic request function. A
socket connection made during any test fails it.

Importing LiteLLM is outside those fixtures: it attempts to fetch its model
cost map unless ``LITELLM_LOCAL_MODEL_COST_MAP=True``. When this module is the
first to import LiteLLM (the file run by itself), it sets that for the import.
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import os
import socket
import sys
from concurrent.futures import ThreadPoolExecutor

if "litellm" not in sys.modules:
    # Only for this import; later modules see the environment as it was. With
    # hot reload set, LiteLLM lets a .env file override the first line.
    _SAVED = {
        name: os.environ.get(name)
        for name in ("LITELLM_LOCAL_MODEL_COST_MAP", "LITELLM_DEV_ENV_HOT_RELOAD")
    }
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    os.environ.pop("LITELLM_DEV_ENV_HOT_RELOAD", None)
    try:
        import litellm
    finally:
        for _name, _value in _SAVED.items():
            if _value is None:
                os.environ.pop(_name, None)
            else:
                os.environ[_name] = _value

import httpx  # noqa: E402
import litellm  # noqa: E402
import pytest  # noqa: E402
from hypothesis import HealthCheck, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

import policybench.eval_no_tools as eval_no_tools  # noqa: E402
from policybench.cache import enable_cache  # noqa: E402
from policybench.completion_budget import (  # noqa: E402
    completion_budget_from_kwargs,
    next_completion_budget,
)
from policybench.eval_no_tools import (  # noqa: E402
    ANSWER_FUNCTION_NAME,
    REASONING_EFFORT_OVERRIDE_ENV,
    _answer_contract_for_model,
    _chat_completion_request_kwargs,
    _completion_budget_ceiling,
    _request_explanations_once,
    _request_predictions_once,
    _response_cache_hit,
    _responses_request_kwargs,
    _run_request_with_wall_timeout,
    _uses_responses_api,
)
from policybench.model_cards import MODEL_CARDS  # noqa: E402
from policybench.scenarios import Person, Scenario  # noqa: E402

SCENARIO = Scenario(
    id="mini",
    state="CA",
    filing_status="single",
    adults=[Person(name="adult1", age=35, employment_income=50_000.0)],
    year=2026,
)
# The binary output gives the answer tool an integer ``enum``, one of the two
# schema fields LiteLLM strips for Gemini.
VARIABLES = ["snap", "ssi", "free_school_meals_eligible"]
ANSWERS = {variable: 1.0 for variable in VARIABLES}
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
# Settings that would send a request somewhere else or shape it differently:
# a base URL from the environment, LiteLLM's switches, and the keys and base
# URL a process can set on the litellm module, which win over the environment.
ROUTING_VARIABLES = (
    "ANTHROPIC_API_BASE",
    "ANTHROPIC_BASE_URL",
    "DEEPSEEK_API_BASE",
    "GEMINI_API_BASE",
    "LITELLM_ANTHROPIC_DISABLE_URL_SUFFIX",
    "LITELLM_MODIFY_PARAMS",
    "OPENAI_API_BASE",
    "OPENAI_BASE_URL",
    "OPENAI_ORGANIZATION",
    "OPENROUTER_API_BASE",
    "XAI_API_BASE",
)
CALLBACK_LISTS = (
    "input_callback",
    "success_callback",
    "failure_callback",
    "_async_success_callback",
    "_async_failure_callback",
)
LITELLM_ROUTING_GLOBALS = (
    "anthropic_key",
    "api_base",
    "api_key",
    "headers",
    "openai_key",
    "openrouter_key",
    "organization",
    "xai_key",
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


BOARD_IDS = sorted(card.litellm_id for card in MODEL_CARDS.values())
GROUPS: dict[str, list[str]] = {}
for _model_id in BOARD_IDS:
    GROUPS.setdefault(_group(_model_id), []).append(_model_id)
# One model per provider path and answer contract on the board. A card for a
# new provider or contract joins both lists without an edit here.
REPRESENTATIVES = [ids[0] for _, ids in sorted(GROUPS.items())]
GEMINI_TOOL_ID = GROUPS["gemini / tool"][0]


def _doubled_budget(model_id: str) -> tuple[int, int] | None:
    """A card's starting budget and the next rung, if it has one."""
    if _uses_responses_api(model_id):
        _, request = _responses_request_kwargs(SCENARIO, VARIABLES, model_id)
    else:
        _, request = _chat_completion_request_kwargs(SCENARIO, VARIABLES, model_id)
    base = completion_budget_from_kwargs(request)
    doubled = next_completion_budget(base, _completion_budget_ceiling(model_id))
    return None if doubled is None else (base, doubled)


def _send_doubled(model_id: str) -> dict:
    rung = _doubled_budget(model_id)
    if rung is None:
        pytest.skip(f"{model_id} starts at its completion-budget ceiling")
    return _request_predictions_once(
        SCENARIO,
        VARIABLES,
        model_id,
        completion_budget_tokens=rung[1],
        escalated_from_budget_tokens=rung[0],
    )


# Every request the harness sends for a household. Each call builds its
# request again, as a re-sent worker does.
REQUESTS = {
    "answers with explanations": lambda model_id: _request_predictions_once(
        SCENARIO, VARIABLES, model_id
    ),
    "answers only": lambda model_id: _request_predictions_once(
        SCENARIO, VARIABLES, model_id, include_explanations=False
    ),
    "repair": lambda model_id: _request_predictions_once(
        SCENARIO, VARIABLES[:2], model_id, repair=True
    ),
    "doubled budget": _send_doubled,
    "explanations only": lambda model_id: _request_explanations_once(
        SCENARIO, VARIABLES, ANSWERS, model_id
    ),
}
FIRST_REQUEST = "answers with explanations"
OTHER_REQUESTS = [kind for kind in REQUESTS if kind != FIRST_REQUEST]
EVERY_REQUEST = list(itertools.product(REPRESENTATIVES, REQUESTS))


def _has_tool(body: dict) -> str | None:
    """The name of the tool a provider request declares, in any wire format."""
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
    """A provider-shaped answer that names the call it answers.

    The call number reaches the harness's ``raw_response``, so a replayed
    answer is told apart from a second answer to the same request.
    """
    tool = _has_tool(body)
    arguments = {"stub_call": call}
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
    for name in (*SENSITIVITY_VARIABLES, *ROUTING_VARIABLES):
        monkeypatch.delenv(name, raising=False)
    for name in LITELLM_ROUTING_GLOBALS:
        monkeypatch.setattr(litellm, name, None)
    monkeypatch.setattr(eval_no_tools, "_PROCESS_REASONING_EFFORT_OVERRIDE", [])
    monkeypatch.setattr(eval_no_tools, "MAX_ATTEMPTS", 1)
    monkeypatch.setattr(litellm, "drop_params", False)
    monkeypatch.setattr(litellm, "modify_params", False)
    # Each test starts with no LiteLLM callbacks, whatever an earlier test on
    # this worker left. Turning the cache on registers some, and the first
    # call after that records them in litellm.utils; all are put back after.
    for name in CALLBACK_LISTS:
        monkeypatch.setattr(litellm, name, [])
    monkeypatch.setattr(litellm.utils, "callback_list", [])
    monkeypatch.setattr(litellm, "cache", None)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class Wire(list):
    """The requests LiteLLM put on the wire, each answered from this file.

    A header or a query string can carry a key, so an entry keeps their
    digests, not their values: a failed comparison then prints no value.
    """

    def __init__(self) -> None:
        super().__init__()
        self._sent_text: list[str] = []

    def record(self, request, body: dict) -> None:
        headers = dict(request.headers)
        self._sent_text.append(json.dumps([str(request.url), headers, body]))
        self.append(
            {
                "path": request.url.path,
                "query": _digest(request.url.query.decode()),
                "headers": {name: _digest(value) for name, value in headers.items()},
                "body": body,
            }
        )

    def carries(self, text: str) -> bool:
        """Whether any URL, header or body sent so far contains ``text``."""
        return any(text in sent for sent in self._sent_text)


@pytest.fixture
def wire(monkeypatch) -> Wire:
    sent = Wire()

    def send(self, request, **_kwargs):
        body = json.loads(request.content)
        sent.record(request, body)
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


class CacheKeys:
    """The keys LiteLLM looked up and stored in one disk cache."""

    def __init__(self, disk_cache) -> None:
        self.looked_up: list[str] = []
        self.stored: list[str] = []
        get, put = disk_cache.get_cache, disk_cache.set_cache

        def get_cache(key, **kwargs):
            self.looked_up.append(key)
            return get(key, **kwargs)

        def set_cache(key, value, **kwargs):
            self.stored.append(key)
            return put(key, value, **kwargs)

        disk_cache.get_cache, disk_cache.set_cache = get_cache, set_cache


@pytest.fixture
def cache_keys(tmp_path, offline) -> CacheKeys:
    """Turn the harness's disk cache on in a temporary directory."""
    enable_cache(str(tmp_path / "cache"))
    return CacheKeys(litellm.cache.cache)


class _Built(BaseException):
    """Stops a harness request function once it has built its request."""


def _as_built(monkeypatch, kind: str, model_id: str) -> tuple:
    """The LiteLLM function and the request the harness builds, unsent."""
    built: dict = {}

    def stop(request_fn, request_kwargs):
        built.update(request_fn=request_fn, request=request_kwargs)
        raise _Built

    with monkeypatch.context() as patch:
        patch.setattr(eval_no_tools, "_run_request_with_wall_timeout", stop)
        with pytest.raises(_Built):
            REQUESTS[kind](model_id)
    return built["request_fn"], built["request"]


def _cache_hit(result: dict) -> bool:
    return result["spend_ledger"][-1]["cache_hit"]


def _assert_replays(kind: str, model_id: str, wire: list, keys: CacheKeys) -> None:
    first = REQUESTS[kind](model_id)
    assert len(wire) == 1
    if _uses_responses_api(model_id):
        # LiteLLM would hand a Responses call it bridges through completion
        # the same pinned key as the inner call.
        assert wire[0]["path"].endswith("/responses")
    assert not _cache_hit(first)
    assert (first["live_calls"], first["cache_hit_calls"]) == (1, 0)
    assert keys.stored == keys.looked_up, "stored under a key no request looks up"

    second = REQUESTS[kind](model_id)  # built again, as a re-sent worker does
    assert len(wire) == 1, "the freshly built request was sent, and paid for, again"
    assert _cache_hit(second)
    assert (second["live_calls"], second["cache_hit_calls"]) == (0, 1)
    assert second["raw_response"] == first["raw_response"]
    assert "stub_call" in first["raw_response"]
    assert keys.looked_up == keys.stored * 2


@pytest.mark.parametrize("model_id", BOARD_IDS)
def test_a_freshly_built_request_replays_for_every_card(model_id, wire, cache_keys):
    _assert_replays(FIRST_REQUEST, model_id, wire, cache_keys)


@pytest.mark.parametrize("kind", OTHER_REQUESTS)
@pytest.mark.parametrize("model_id", REPRESENTATIVES)
def test_every_request_the_harness_sends_replays(model_id, kind, wire, cache_keys):
    _assert_replays(kind, model_id, wire, cache_keys)


@pytest.mark.parametrize(("model_id", "kind"), EVERY_REQUEST)
def test_a_call_leaves_the_callers_request_as_built(
    model_id, kind, wire, cache_keys, monkeypatch
):
    request_fn, request = _as_built(monkeypatch, kind, model_id)
    as_built = copy.deepcopy(request)

    _run_request_with_wall_timeout(request_fn, request)

    assert len(wire) == 1
    assert request == as_built


@pytest.mark.parametrize(("model_id", "kind"), EVERY_REQUEST)
def test_a_retry_of_the_same_request_replays(
    model_id, kind, wire, cache_keys, monkeypatch
):
    """The attempt loop retries with the request object it already sent."""
    request_fn, request = _as_built(monkeypatch, kind, model_id)

    _run_request_with_wall_timeout(request_fn, request)
    retried = _run_request_with_wall_timeout(request_fn, request)

    assert len(wire) == 1
    assert _response_cache_hit(retried)


@pytest.mark.parametrize(("model_id", "kind"), EVERY_REQUEST)
def test_the_pinned_key_is_the_key_litellm_looks_up_by_itself(
    model_id, kind, wire, cache_keys, monkeypatch
):
    """The pin changes no lookup key, so stored answers keep replaying.

    A plain LiteLLM call stands in for an answer stored before the pin. The
    harness finds it exactly when LiteLLM stored it under the key it looked up,
    which holds for every request LiteLLM does not rewrite between the two.
    """
    request_fn, request = _as_built(monkeypatch, kind, model_id)

    request_fn(**copy.deepcopy(request))
    (plain_lookup,), (plain_stored,) = cache_keys.looked_up, cache_keys.stored
    response = _run_request_with_wall_timeout(request_fn, request)

    assert cache_keys.looked_up == [plain_lookup, plain_lookup]
    assert _response_cache_hit(response) == (plain_stored == plain_lookup)
    assert set(cache_keys.stored) == {plain_stored, plain_lookup}


@pytest.mark.parametrize(("model_id", "kind"), EVERY_REQUEST)
def test_the_pin_never_reaches_the_provider(
    model_id, kind, wire, tmp_path, monkeypatch
):
    """The path, query, headers and body are the ones LiteLLM sends alone."""
    request_fn, request = _as_built(monkeypatch, kind, model_id)

    request_fn(**copy.deepcopy(request))  # no cache: LiteLLM alone
    enable_cache(str(tmp_path / "cache"))
    key = litellm.cache.get_cache_key(**copy.deepcopy(request))
    _run_request_with_wall_timeout(request_fn, request)

    plain, pinned = wire
    assert pinned == plain
    assert wire.carries(request["model"].rsplit("/", 1)[-1])
    for pin in ("cache_key", key, key.rsplit(":", 1)[-1]):
        assert not wire.carries(pin)


def test_an_effort_override_keeps_its_own_namespace(wire, cache_keys, monkeypatch):
    """The pinned key carries the namespace of a request's ``cache`` control."""
    monkeypatch.setenv(REASONING_EFFORT_OVERRIDE_ENV, f"{OPUS}=high")
    namespace = f"{litellm.cache.namespace}:{OPUS}:effort=high"
    _assert_replays(FIRST_REQUEST, OPUS, wire, cache_keys)
    assert all(key.startswith(f"{namespace}:") for key in cache_keys.stored)

    monkeypatch.delenv(REASONING_EFFORT_OVERRIDE_ENV)
    monkeypatch.setattr(eval_no_tools, "_PROCESS_REASONING_EFFORT_OVERRIDE", [])
    board = REQUESTS[FIRST_REQUEST](OPUS)

    assert len(wire) == 2, "the board request replayed the override's answer"
    assert not _cache_hit(board)


def _rewriting_request_fn(received: list[dict]):
    """A request function that rewrites its arguments in place, as LiteLLM can."""

    def request_fn(**kwargs):
        received.append(copy.deepcopy(kwargs))
        for tool in kwargs.get("tools", []):
            tool["function"]["parameters"].pop("additionalProperties", None)
        kwargs["messages"].append({"role": "assistant", "content": "added"})
        return "answer"

    return request_fn


def test_the_request_function_gets_a_copy_and_one_key_for_every_attempt(cache_keys):
    _, request = _chat_completion_request_kwargs(SCENARIO, VARIABLES, GEMINI_TOOL_ID)
    as_built = copy.deepcopy(request)
    received: list[dict] = []
    request_fn = _rewriting_request_fn(received)

    assert _run_request_with_wall_timeout(request_fn, request) == "answer"
    assert _run_request_with_wall_timeout(request_fn, request) == "answer"

    assert request == as_built
    key = litellm.cache.get_cache_key(**copy.deepcopy(as_built))
    assert received == [{**as_built, "cache_key": key}] * 2


def test_a_worker_thread_gets_the_copy_and_the_key_too(cache_keys):
    """``repair-failed-rows`` sends requests from worker threads, which take
    the wrapper's other return: the wall-clock alarm needs the main thread."""
    _, request = _chat_completion_request_kwargs(SCENARIO, VARIABLES, GEMINI_TOOL_ID)
    as_built = copy.deepcopy(request)
    received: list[dict] = []
    request_fn = _rewriting_request_fn(received)

    with ThreadPoolExecutor(max_workers=1) as pool:
        answer = pool.submit(_run_request_with_wall_timeout, request_fn, request)
        assert answer.result() == "answer"

    assert request == as_built
    key = litellm.cache.get_cache_key(**copy.deepcopy(as_built))
    assert received == [{**as_built, "cache_key": key}]


def test_without_a_cache_the_request_function_gets_an_equal_copy():
    assert litellm.cache is None
    _, request = _chat_completion_request_kwargs(SCENARIO, VARIABLES, GEMINI_TOOL_ID)
    as_built = copy.deepcopy(request)
    received: list[dict] = []

    _run_request_with_wall_timeout(_rewriting_request_fn(received), request)

    assert received == [as_built]
    assert request == as_built


def test_a_key_the_caller_set_is_kept(cache_keys):
    _, request = _chat_completion_request_kwargs(SCENARIO, VARIABLES, GEMINI_TOOL_ID)
    request["cache_key"] = "the-callers-own-key"
    received: list[dict] = []

    _run_request_with_wall_timeout(_rewriting_request_fn(received), request)

    assert received[0]["cache_key"] == "the-callers-own-key"


_LEAVES = st.sampled_from(
    [
        {"type": "number"},
        {"type": "integer", "enum": [0, 1]},
        {"type": "string"},
        {"type": "string", "enum": ["a", "b"]},
        {"type": "boolean"},
        {"type": "array", "items": {"type": "number"}},
    ]
)


def _objects(children):
    return st.dictionaries(
        st.sampled_from(["a", "b", "c", "d"]), children, min_size=1, max_size=3
    ).flatmap(
        lambda properties: st.fixed_dictionaries(
            {
                "type": st.just("object"),
                "properties": st.just(properties),
                "required": st.just(sorted(properties)),
            },
            optional={"additionalProperties": st.booleans()},
        )
    )


# Each example gets its own copy: the leaves above are shared objects, and a
# call that rewrote one would change every later example.
TOOL_SCHEMAS = _objects(st.recursive(_LEAVES, _objects, max_leaves=6)).map(
    copy.deepcopy
)


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(schema=TOOL_SCHEMAS)
def test_any_tool_schema_is_stored_under_the_key_it_is_looked_up_by(
    schema, wire, cache_keys
):
    """Whatever LiteLLM rewrites in a Gemini tool's schema, the keys agree."""
    request = {
        "model": GEMINI_TOOL_ID,
        # Each example asks something new, so none replays an earlier example.
        "messages": [{"role": "user", "content": f"example {len(wire)}"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": ANSWER_FUNCTION_NAME,
                    "description": "Submit the outputs.",
                    "parameters": schema,
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": ANSWER_FUNCTION_NAME}},
    }
    as_built = copy.deepcopy(request)
    sent = len(wire)

    _run_request_with_wall_timeout(litellm.completion, request)
    replayed = _run_request_with_wall_timeout(
        litellm.completion, copy.deepcopy(as_built)
    )

    assert request == as_built
    assert len(wire) == sent + 1
    assert _response_cache_hit(replayed)
    assert cache_keys.stored[-1] == cache_keys.looked_up[-1]
