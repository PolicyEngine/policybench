"""The one-model effort override, POLICYBENCH_REASONING_EFFORT_OVERRIDE.

The board sends no reasoning control. A sensitivity run sets the variable to
``<Claude litellm id>=<effort>`` to send that one model Anthropic's effort
parameter, ``output_config.effort``. These are unit tests and send nothing:
the litellm checks replace litellm's HTTP ``post`` with a stub that records
the request body and headers and either raises or returns a canned response
from this file, and the harness checks replace the harness's ``completion``.
The tests that reach litellm's request builder run under both states of
litellm's model map for the two Claude ids (``loaded_map``), since the effort
beta header depends on which map the process loaded.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import litellm
import pandas as pd
import pytest
from litellm.llms.anthropic.common_utils import AnthropicModelInfo
from litellm.llms.custom_httpx import http_handler

import policybench.eval_no_tools as eval_no_tools
from policybench import analysis, full_run_export
from policybench import supervisor as supervisor_module
from policybench.cache import enable_cache
from policybench.config import MODELS
from policybench.eval_no_tools import (
    REASONING_EFFORT_OVERRIDE_ENV,
    REASONING_EFFORT_OVERRIDES,
    ReasoningEffortOverride,
    SensitivityKnobError,
    _apply_thinking_configuration,
    _build_resume_metadata,
    _chat_completion_request_kwargs,
    _request_explanations_once,
    _responses_request_kwargs,
    _thinking_configuration,
    _treatment_metadata,
    _uses_responses_api,
    resolve_reasoning_effort_override,
    run_single_no_tools,
)
from policybench.scenarios import Person, Scenario, scenario_to_dict
from policybench.supervisor import Supervisor

ROOT = Path(__file__).resolve().parents[1]
OPUS = "claude-opus-5-5"
FABLE = "claude-fable-5-2"
GPT = next(model for model in MODELS.values() if _uses_responses_api(model))
GEMINI = next(model for model in MODELS.values() if model.startswith("gemini/"))
# Every key through which litellm or the API could take a reasoning control.
REASONING_KEYS = {"output_config", "reasoning", "reasoning_effort", "thinking"}
EFFORT_BETA = "effort-2025-11-24"
# The model-map flag litellm reads to leave the effort beta header out.
SUPPORTS_ADAPTIVE = "supports_adaptive_thinking"


def _new_process(monkeypatch) -> None:
    """Forget what this process resolved, as a fresh worker would start."""
    monkeypatch.setattr(eval_no_tools, "_PROCESS_REASONING_EFFORT_OVERRIDE", [])


@pytest.fixture(autouse=True)
def no_override(monkeypatch):
    monkeypatch.delenv(REASONING_EFFORT_OVERRIDE_ENV, raising=False)
    monkeypatch.delenv("LITELLM_DROP_PARAMS", raising=False)
    monkeypatch.setattr(litellm, "drop_params", False)
    monkeypatch.setattr(litellm, "cache", None)
    _new_process(monkeypatch)


def _set_override(monkeypatch, value: str) -> None:
    """Start a fresh process with the variable set to ``value``."""
    _new_process(monkeypatch)
    monkeypatch.setenv(REASONING_EFFORT_OVERRIDE_ENV, value)


def _unset_override(monkeypatch) -> None:
    _new_process(monkeypatch)
    monkeypatch.delenv(REASONING_EFFORT_OVERRIDE_ENV, raising=False)


@pytest.fixture
def scenario() -> Scenario:
    return Scenario(
        id="mini",
        state="CA",
        filing_status="single",
        adults=[Person(name="adult1", age=35, employment_income=50_000.0)],
        year=2026,
    )


def _kwargs(scenario: Scenario, model_id: str, *, repair: bool = False) -> dict:
    if _uses_responses_api(model_id):
        _, kwargs = _responses_request_kwargs(
            scenario, ["snap", "ssi"], model_id, repair=repair
        )
    else:
        _, kwargs = _chat_completion_request_kwargs(
            scenario, ["snap", "ssi"], model_id, repair=repair
        )
    return kwargs


def _sent(kwargs: dict, monkeypatch) -> tuple[dict, dict]:
    """The JSON body and headers litellm would POST to Anthropic."""
    captured: dict = {}

    def stub_post(self, url, data=None, json=None, headers=None, **_):  # noqa: A002
        captured["url"] = url
        captured["body"] = json if json is not None else __import__("json").loads(data)
        captured["headers"] = dict(headers or {})
        raise RuntimeError("stub: the request is recorded, never sent")

    monkeypatch.setattr(http_handler.HTTPHandler, "post", stub_post)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-value-not-a-key")
    request = {key: value for key, value in kwargs.items() if key != "caching"}
    with pytest.raises(Exception):
        litellm.completion(**request, api_base="http://127.0.0.1:9", num_retries=0)
    assert captured["url"] == "http://127.0.0.1:9/v1/messages"
    headers = {
        key.lower(): value
        for key, value in captured["headers"].items()
        if key.lower() not in {"x-api-key", "authorization"}
    }
    return captured["body"], headers


def _bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True).encode()


def _adaptive(model_id: str) -> bool:
    """litellm's own reading of its loaded model map: it adds the effort beta
    header only for a model the map does not mark as adaptive-thinking."""
    return AnthropicModelInfo._is_adaptive_thinking_model(model_id, "anthropic")


@contextlib.contextmanager
def _model_map(model_ids: tuple[str, ...], *, adaptive: bool):
    """Mark each id's litellm.model_cost entry (and its ``anthropic/`` entry,
    where the loaded map has one) as adaptive-thinking or not, then restore.

    The effort runs loaded litellm's bundled map (LITELLM_LOCAL_MODEL_COST_MAP
    =True), which does not mark these ids, so litellm added the effort beta
    header. The remote map litellm loads otherwise (CI sets no LITELLM
    variable) may mark them, and then litellm adds none. ``adaptive=False`` is
    the runs' state, set explicitly so that no other entry or fallback rule of
    whichever map this process loaded decides it."""
    keys = [
        key
        for model_id in model_ids
        for key in (model_id, f"anthropic/{model_id}")
        if key in litellm.model_cost
    ]
    saved = {key: litellm.model_cost[key] for key in keys}
    try:
        for key in keys:
            litellm.model_cost[key] = {**saved[key], SUPPORTS_ADAPTIVE: adaptive}
        litellm.utils._invalidate_model_cost_lowercase_map()
        states = {model_id: _adaptive(model_id) for model_id in model_ids}
        assert states == dict.fromkeys(model_ids, adaptive), states
        yield
    finally:
        litellm.model_cost.update(saved)
        litellm.utils._invalidate_model_cost_lowercase_map()


@pytest.fixture(params=["bundled_map", "adaptive_map"])
def loaded_map(request):
    """Run the test as if this process had loaded litellm's bundled map (the
    two Claude ids not marked adaptive, as in the effort runs) or a map that
    marks them adaptive (as the remote map may, in CI): the tests that reach
    litellm's request builder must hold under either."""
    with _model_map((OPUS, FABLE), adaptive=request.param == "adaptive_map"):
        yield request.param


def test_the_board_constant_stays_empty():
    assert REASONING_EFFORT_OVERRIDES == {}


@pytest.mark.usefixtures("loaded_map")
def test_default_sends_no_reasoning_control(scenario, monkeypatch):
    for model_id in (OPUS, FABLE):
        kwargs = _kwargs(scenario, model_id)
        assert not REASONING_KEYS & set(kwargs), model_id
        assert "cache" not in kwargs
        assert not REASONING_KEYS & set(_kwargs(scenario, model_id, repair=True))
        assert _thinking_configuration(model_id) == {"mode": "provider_default"}
        body, headers = _sent(kwargs, monkeypatch)
        assert not REASONING_KEYS & set(body), model_id
        assert set(body) == {"model", "messages", "max_tokens"}, model_id
        assert EFFORT_BETA not in headers.get("anthropic-beta", ""), model_id


@pytest.mark.usefixtures("loaded_map")
@pytest.mark.parametrize(
    ("named", "effort", "other"),
    [(OPUS, "high", FABLE), (FABLE, "medium", OPUS)],
)
def test_override_sends_exactly_the_value_for_exactly_the_named_model(
    scenario, monkeypatch, named, effort, other
):
    with _model_map((named,), adaptive=False):
        _check_override_request(scenario, monkeypatch, named, effort, other)


def _check_override_request(scenario, monkeypatch, named, effort, other):
    """The request with the named model in the runs' map state (not marked
    adaptive), then the same request with the model marked adaptive."""
    untargeted = (other, GPT, GEMINI)
    board = {model_id: _kwargs(scenario, model_id) for model_id in (named, *untargeted)}
    board_repair = _kwargs(scenario, named, repair=True)
    board_sent = {
        model_id: _sent(board[model_id], monkeypatch) for model_id in (named, other)
    }

    _set_override(monkeypatch, f"{named}={effort}")
    sensitivity = _kwargs(scenario, named)
    namespace = f"policybench:2026-08-09-v2-scoring-contract:{named}:effort={effort}"
    added = {"output_config": {"effort": effort}, "cache": {"namespace": namespace}}
    assert sensitivity == {**board[named], **added}
    assert _kwargs(scenario, named, repair=True) == {**board_repair, **added}
    # Requests for models the variable does not name are the board's.
    for model_id in untargeted:
        assert _bytes(_kwargs(scenario, model_id)) == _bytes(board[model_id]), model_id

    body, headers = _sent(sensitivity, monkeypatch)
    board_body, board_headers = board_sent[named]
    assert body == {**board_body, "output_config": {"effort": effort}}
    assert EFFORT_BETA in headers["anthropic-beta"]
    assert {k: v for k, v in headers.items() if k != "anthropic-beta"} == board_headers
    other_body, other_headers = _sent(_kwargs(scenario, other), monkeypatch)
    assert _bytes(other_body) == _bytes(board_sent[other][0])
    assert other_headers == board_sent[other][1]
    # A map that marks the named model adaptive changes the header only: the
    # same body, and the board's headers with no effort beta header.
    with _model_map((named,), adaptive=True):
        adaptive_body, adaptive_headers = _sent(sensitivity, monkeypatch)
    assert adaptive_body == body
    assert EFFORT_BETA not in adaptive_headers.get("anthropic-beta", "")
    assert adaptive_headers == board_headers


def _explanation_response() -> SimpleNamespace:
    message = SimpleNamespace(
        content=json.dumps({"snap": "From the supplied answer. value = 0"}),
        tool_calls=None,
        function_call=None,
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="stop")],
        usage=litellm.Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def test_the_explanation_repair_request_carries_the_same_effort(scenario, monkeypatch):
    sent: list[dict] = []

    def fake_completion(**kwargs):
        sent.append(kwargs)
        return _explanation_response()

    monkeypatch.setattr(eval_no_tools, "completion", fake_completion)
    for model_id in (OPUS, FABLE):
        _request_explanations_once(scenario, ["snap"], {"snap": 0.0}, model_id)
    board_opus, board_fable = sent[-2:]
    assert not REASONING_KEYS & set(board_opus)

    _set_override(monkeypatch, f"{OPUS}=high")
    for model_id in (OPUS, FABLE):
        _request_explanations_once(scenario, ["snap"], {"snap": 0.0}, model_id)
    opus, fable = sent[-2:]
    assert opus == {
        **board_opus,
        "output_config": {"effort": "high"},
        "cache": {
            "namespace": "policybench:2026-08-09-v2-scoring-contract:"
            f"{OPUS}:effort=high"
        },
    }
    assert _bytes(fable) == _bytes(board_fable)


def test_an_existing_output_config_keeps_its_other_members(monkeypatch):
    _set_override(monkeypatch, f"{OPUS}=high")
    request = {"model": OPUS, "output_config": {"format": {"type": "json_schema"}}}
    _apply_thinking_configuration(request, OPUS)
    assert request["output_config"] == {
        "format": {"type": "json_schema"},
        "effort": "high",
    }
    conflicting = {"model": OPUS, "output_config": {"effort": "low"}}
    with pytest.raises(SensitivityKnobError, match="already sets"):
        _apply_thinking_configuration(conflicting, OPUS)
    assert conflicting["output_config"] == {"effort": "low"}


def _json_response(content: str | None, *, finish_reason: str, completion_tokens):
    message = SimpleNamespace(content=content, tool_calls=None, function_call=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        usage=litellm.Usage(
            prompt_tokens=12,
            completion_tokens=completion_tokens,
            total_tokens=12 + completion_tokens,
        ),
    )


def test_retries_and_doubled_budgets_send_the_resolved_effort(scenario, monkeypatch):
    """A retry after a provider error and a request at a doubled budget each
    carry the value the run resolved and recorded."""
    monkeypatch.setattr(eval_no_tools, "RETRY_BASE_DELAY", 0)
    monkeypatch.setattr(eval_no_tools, "MAX_REPAIR_ROUNDS", 0)
    _set_override(monkeypatch, f"{OPUS}=high")
    sent: list[dict] = []

    def fake_completion(**kwargs):
        sent.append(dict(kwargs))
        if len(sent) == 1:
            raise RuntimeError("transient provider error")
        budget = kwargs["max_completion_tokens"]
        if len(sent) == 2:
            return _json_response(
                None, finish_reason="length", completion_tokens=budget
            )
        return _json_response(
            '{"outputs": {"snap": {"value": 0}}}',
            finish_reason="stop",
            completion_tokens=40,
        )

    monkeypatch.setattr(eval_no_tools, "completion", fake_completion)
    result = run_single_no_tools(
        scenario, ["snap"], OPUS, include_explanations=False, _allow_chunking=False
    )
    assert result["predictions"] == {"snap": 0.0}
    assert result["budget_escalation_count"] == 1
    assert len(sent) == 3
    for kwargs in sent:
        assert kwargs["output_config"] == {"effort": "high"}
        assert kwargs["cache"]["namespace"].endswith(f"{OPUS}:effort=high")
    first, retry, doubled = (kwargs["max_completion_tokens"] for kwargs in sent)
    assert retry == first
    assert doubled == 2 * first
    metadata = _treatment_metadata({"opus": OPUS}, False)
    assert metadata["opus"]["thinking"] == {"reasoning_effort": "high"}


def test_a_changed_environment_stops_the_run_instead_of_sending_a_second_value(
    scenario, monkeypatch
):
    monkeypatch.setattr(eval_no_tools, "MAX_REPAIR_ROUNDS", 0)
    _set_override(monkeypatch, f"{OPUS}=high")
    recorded = _treatment_metadata({"opus": OPUS}, False)["opus"]["thinking"]
    assert recorded == {"reasoning_effort": "high"}
    sent: list[dict] = []

    def fake_completion(**kwargs):
        sent.append(dict(kwargs))
        monkeypatch.setenv(REASONING_EFFORT_OVERRIDE_ENV, f"{OPUS}=low")
        return _json_response(
            None,
            finish_reason="length",
            completion_tokens=kwargs["max_completion_tokens"],
        )

    monkeypatch.setattr(eval_no_tools, "completion", fake_completion)
    with pytest.raises(SensitivityKnobError, match="changed"):
        run_single_no_tools(
            scenario, ["snap"], OPUS, include_explanations=False, _allow_chunking=False
        )
    assert [kwargs["output_config"] for kwargs in sent] == [{"effort": "high"}]


def test_treatment_records_the_effort_sent():
    models = {"opus": OPUS, "fable": FABLE}
    board = _treatment_metadata(models, True, env={})
    assert (
        board["opus"]["thinking"]
        == board["fable"]["thinking"]
        == {"mode": "provider_default"}
    )
    sensitivity = _treatment_metadata(
        models, True, env={REASONING_EFFORT_OVERRIDE_ENV: f"{OPUS}=high"}
    )
    assert sensitivity["opus"]["thinking"] == {"reasoning_effort": "high"}
    assert sensitivity["fable"] == board["fable"]
    assert {k: v for k, v in sensitivity["opus"].items() if k != "thinking"} == {
        k: v for k, v in board["opus"].items() if k != "thinking"
    }


def test_resume_metadata_records_the_effort_sent(scenario, monkeypatch):
    def metadata() -> dict:
        return _build_resume_metadata(
            task="eval_no_tools_batch",
            scenarios=[scenario],
            models={"claude-fable-5.2": FABLE},
            programs=["snap"],
            run_id=None,
            include_explanations=True,
        )

    board = metadata()
    assert board["treatment"]["claude-fable-5.2"]["thinking"] == {
        "mode": "provider_default"
    }
    _set_override(monkeypatch, f"{FABLE}=medium")
    sensitivity = metadata()
    assert sensitivity["treatment"]["claude-fable-5.2"]["thinking"] == {
        "reasoning_effort": "medium"
    }
    assert {k: v for k, v in sensitivity.items() if k != "treatment"} == {
        k: v for k, v in board.items() if k != "treatment"
    }
    # The same process's requests carry the value its record holds.
    assert _kwargs(scenario, FABLE)["output_config"] == {"effort": "medium"}


def _manifest(tmp_path: Path) -> Path:
    path = tmp_path / "scenarios.csv"
    scenarios = [
        Scenario(
            id=f"scenario_{i:03d}",
            state="CA",
            filing_status="single",
            adults=[Person(name="adult", age=35, employment_income=50_000)],
        )
        for i in range(2)
    ]
    pd.DataFrame(
        {
            "scenario_id": [s.id for s in scenarios],
            "scenario_json": [json.dumps(scenario_to_dict(s)) for s in scenarios],
        }
    ).to_csv(path, index=False)
    return path


def test_run_fingerprint_records_the_effort_sent(tmp_path):
    manifest = _manifest(tmp_path)
    board = Supervisor(
        model="claude-opus-5.5", manifest=manifest, run_dir=tmp_path / "board"
    ).treatment_fingerprint
    assert board["thinking"] == {"mode": "provider_default"}
    sensitivity = Supervisor(
        model="claude-opus-5.5",
        manifest=manifest,
        run_dir=tmp_path / "sensitivity",
        env={REASONING_EFFORT_OVERRIDE_ENV: f"{OPUS}=high"},
    ).treatment_fingerprint
    assert sensitivity == {**board, "thinking": {"reasoning_effort": "high"}}
    other = Supervisor(
        model="claude-fable-5.2",
        manifest=manifest,
        run_dir=tmp_path / "other",
        env={REASONING_EFFORT_OVERRIDE_ENV: f"{OPUS}=high"},
    ).treatment_fingerprint
    assert other["thinking"] == {"mode": "provider_default"}


def _spawned_env(supervisor: Supervisor, monkeypatch) -> dict:
    spawned: list[dict] = []

    def fake_popen(cmd, **kwargs):
        spawned.append(dict(kwargs["env"]))
        return SimpleNamespace(args=cmd)

    monkeypatch.setattr(supervisor_module.subprocess, "Popen", fake_popen)
    supervisor._spawn(0)
    (env,) = spawned
    return env


def test_the_fingerprint_and_every_worker_carry_one_resolved_value(
    tmp_path, monkeypatch
):
    """The supervisor's own process environment and the environment it gives
    its workers can differ; the fingerprint records the workers' value, and a
    later change to the supervisor's process environment changes neither."""
    manifest = _manifest(tmp_path)
    monkeypatch.setenv(REASONING_EFFORT_OVERRIDE_ENV, f"{OPUS}=low")
    supervisor = Supervisor(
        model="claude-opus-5.5",
        manifest=manifest,
        run_dir=tmp_path / "run",
        env={REASONING_EFFORT_OVERRIDE_ENV: f"{OPUS}=high"},
    )
    assert supervisor.reasoning_effort_override == ReasoningEffortOverride(OPUS, "high")
    assert supervisor.treatment_fingerprint["thinking"] == {"reasoning_effort": "high"}
    assert _spawned_env(supervisor, monkeypatch)[REASONING_EFFORT_OVERRIDE_ENV] == (
        f"{OPUS}=high"
    )
    monkeypatch.setenv(REASONING_EFFORT_OVERRIDE_ENV, f"{OPUS}=medium")
    assert _spawned_env(supervisor, monkeypatch)[REASONING_EFFORT_OVERRIDE_ENV] == (
        f"{OPUS}=high"
    )
    assert supervisor._treatment_fingerprint()["thinking"] == {
        "reasoning_effort": "high"
    }

    # With no supervisor setting, the process environment's value is the one
    # resolved, recorded and handed to the workers.
    inherited = Supervisor(
        model="claude-opus-5.5", manifest=manifest, run_dir=tmp_path / "inherited"
    )
    assert inherited.treatment_fingerprint["thinking"] == {"reasoning_effort": "medium"}
    assert _spawned_env(inherited, monkeypatch)[REASONING_EFFORT_OVERRIDE_ENV] == (
        f"{OPUS}=medium"
    )
    # An explicitly empty supervisor setting is refused, not read as unset.
    with pytest.raises(SensitivityKnobError):
        Supervisor(
            model="claude-opus-5.5",
            manifest=manifest,
            run_dir=tmp_path / "empty",
            env={REASONING_EFFORT_OVERRIDE_ENV: ""},
        )


def test_drop_params_with_the_override_fails_loudly(scenario, tmp_path, monkeypatch):
    # LITELLM_DROP_PARAMS turns drop_params on for any non-empty value.
    for value in ("True", "False", "0"):
        env = {
            REASONING_EFFORT_OVERRIDE_ENV: f"{OPUS}=high",
            "LITELLM_DROP_PARAMS": value,
        }
        with pytest.raises(SensitivityKnobError, match="LITELLM_DROP_PARAMS"):
            resolve_reasoning_effort_override(env)
        with pytest.raises(SensitivityKnobError, match="LITELLM_DROP_PARAMS"):
            Supervisor(
                model="claude-opus-5.5",
                manifest=_manifest(tmp_path),
                run_dir=tmp_path / f"drop-{value}",
                env=env,
            )
    # drop_params on in the client: the board requests need no effort field.
    monkeypatch.setattr(litellm, "drop_params", True)
    board = {model_id: _kwargs(scenario, model_id) for model_id in (OPUS, FABLE)}
    assert not REASONING_KEYS & set(board[OPUS])
    _set_override(monkeypatch, f"{OPUS}=high")
    with pytest.raises(SensitivityKnobError, match="drop_params"):
        _kwargs(scenario, OPUS)
    assert _bytes(_kwargs(scenario, FABLE)) == _bytes(board[FABLE])


def _canned_post(calls: list[dict]):
    def stub_post(self, url, data=None, json=None, headers=None, **_):  # noqa: A002
        body = json if json is not None else __import__("json").loads(data)
        assert url.startswith("http://127.0.0.1:9"), url
        calls.append(body)
        payload = {
            "id": f"msg_stub_{len(calls)}",
            "type": "message",
            "role": "assistant",
            "model": body["model"],
            "content": [{"type": "text", "text": f"ANSWER-{len(calls)}"}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        return httpx.Response(
            200,
            json=payload,
            headers={"content-type": "application/json"},
            request=httpx.Request("POST", url),
        )

    return stub_post


def _call(kwargs: dict, calls: list[dict]) -> tuple[str, bool, int]:
    before = len(calls)
    response = litellm.completion(
        **kwargs, api_base="http://127.0.0.1:9", num_retries=0
    )
    hit = bool((getattr(response, "_hidden_params", {}) or {}).get("cache_hit"))
    return response.choices[0].message.content, hit, len(calls) - before


@pytest.mark.usefixtures("loaded_map")
@pytest.mark.parametrize("first", ["board", "override"])
def test_the_disk_cache_never_replays_across_the_two_conditions(
    scenario, tmp_path, monkeypatch, first
):
    """litellm's cache key leaves output_config out; the effort's own
    namespace keeps an override run from replaying a board answer and a board
    run from replaying an override answer, while each still replays its own."""
    calls: list[dict] = []
    monkeypatch.setattr(http_handler.HTTPHandler, "post", _canned_post(calls))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-value-not-a-key")
    enable_cache(str(tmp_path / "cache"))

    def build(condition: str) -> dict:
        if condition == "board":
            _unset_override(monkeypatch)
        else:
            _set_override(monkeypatch, f"{OPUS}=high")
        return _kwargs(scenario, OPUS)

    second = "override" if first == "board" else "board"
    text_1, hit_1, http_1 = _call(build(first), calls)
    assert (hit_1, http_1) == (False, 1)
    text_2, hit_2, http_2 = _call(build(second), calls)
    assert (hit_2, http_2) == (False, 1), "replayed the other condition's answer"
    assert text_2 != text_1
    # Each condition replays only its own answer.
    assert _call(build(first), calls) == (text_1, True, 0)
    assert _call(build(second), calls) == (text_2, True, 0)
    assert ("output_config" in calls[0]) == (first == "override")
    assert ("output_config" in calls[1]) == (second == "override")


@pytest.mark.parametrize(
    "value",
    [
        "",  # explicitly empty
        OPUS,  # no effort
        f"{OPUS}=",  # empty effort
        f"{OPUS}=extreme",  # not an Anthropic level
        f"{OPUS}=High",  # levels are lower case
        f"{OPUS}=xhigh",  # litellm 1.95.0 refuses it for this id
        f"{OPUS}=max",  # litellm 1.95.0 refuses it for this id
        f" {OPUS}=high",
        f"{OPUS}=high ",
        "claude-opus-5.5=high",  # a config key, not the litellm id
        "claude-opus-9-9=high",  # not a configured model
        "gpt-6.1-sol=high",  # not a Claude model
        "=high",
    ],
)
def test_a_malformed_override_fails_instead_of_sending_the_board_request(
    scenario, tmp_path, monkeypatch, value
):
    _set_override(monkeypatch, value)
    with pytest.raises(SensitivityKnobError, match=REASONING_EFFORT_OVERRIDE_ENV):
        _kwargs(scenario, OPUS)
    # A malformed value stops any model's run, not only the one it names.
    with pytest.raises(SensitivityKnobError):
        _thinking_configuration(FABLE)
    with pytest.raises(SensitivityKnobError):
        _kwargs(scenario, GEMINI)
    with pytest.raises(SensitivityKnobError):
        Supervisor(
            model="claude-fable-5.2",
            manifest=_manifest(tmp_path),
            run_dir=tmp_path / "run",
        )


def test_an_explicit_environment_ignores_the_process_value(monkeypatch):
    _set_override(monkeypatch, f"{OPUS}=high")
    assert _thinking_configuration(OPUS, env={}) == {"mode": "provider_default"}
    assert _thinking_configuration(OPUS) == {"reasoning_effort": "high"}


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(
        f"{name}_for_effort_guard", ROOT / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("value", [f"{OPUS}=high", ""])
def test_the_freeze_and_the_board_exports_refuse_while_the_variable_is_set(
    tmp_path, monkeypatch, value
):
    assert analysis.REASONING_EFFORT_OVERRIDE_ENV == REASONING_EFFORT_OVERRIDE_ENV
    freezer = _load_script("freeze_snapshot")
    # Were a guard missing, nothing here could reach the repository: the
    # freeze's inputs and outputs point into tmp_path (main stops at its
    # missing source run), and every step that writes only records its call.
    for constant in ("SOURCE_RUN", "RUN_DEST", "SNAPSHOT_DIR", "ANNOTATIONS_DEST"):
        monkeypatch.setattr(freezer, constant, tmp_path / f"absent-{constant}")
    touched: list[str] = []
    for step in (
        "model_response_window",
        "remove_stale_artifacts",
        "freeze_run",
        "freeze_committed_artifacts",
        "freeze_annotations",
        "build_manifest",
        "write_app_paper_snapshot",
    ):
        monkeypatch.setattr(
            freezer, step, lambda *a, _step=step, **k: touched.append(_step)
        )
    monkeypatch.setenv(REASONING_EFFORT_OVERRIDE_ENV, value)

    with pytest.raises(SystemExit, match=REASONING_EFFORT_OVERRIDE_ENV):
        freezer.main()
    serving = tmp_path / "model_serving_config.json"
    with pytest.raises(SystemExit, match=REASONING_EFFORT_OVERRIDE_ENV):
        freezer.freeze_serving_configuration(serving)
    # The release freezers reach the serving config and the board rows only
    # through freezer.main, after the treatment check they all share.
    state_path = tmp_path / "run_state.json"
    with pytest.raises(SystemExit, match=REASONING_EFFORT_OVERRIDE_ENV):
        freezer._validate_treatment_fingerprint(
            {}, {}, model="claude-opus-5.5", run_state_path=state_path
        )
    # freeze_adds0928 sets OPENBLAS_NUM_THREADS and puts the checkout on
    # sys.path when loaded; both are restored after the test.
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "1")
    monkeypatch.setattr(sys, "path", list(sys.path))
    adds0928 = _load_script("freeze_adds0928")
    # A set value stops at the check's refusal; the empty value stops earlier,
    # where the expected treatment is built, as a malformed override.
    with pytest.raises(
        (SystemExit, SensitivityKnobError), match=REASONING_EFFORT_OVERRIDE_ENV
    ):
        adds0928.validate_treatment(
            freezer,
            {"model": "claude-opus-5.5", "treatment_fingerprint": {}},
            state_path,
            ROOT / "paper/snapshot/20260501/us_scenarios.csv",
        )
    dashboard = tmp_path / "out" / "data.json"
    with pytest.raises(SystemExit, match=REASONING_EFFORT_OVERRIDE_ENV):
        analysis.export_dashboard_data(
            pd.DataFrame(),
            pd.DataFrame(),
            {},
            pd.DataFrame(),
            dashboard,
            policyengine_bundles={},
        )
    with pytest.raises(SystemExit, match=REASONING_EFFORT_OVERRIDE_ENV):
        full_run_export.export_country(tmp_path)
    with pytest.raises(SystemExit, match=REASONING_EFFORT_OVERRIDE_ENV):
        full_run_export.export_full_run(
            tmp_path, app_data_output=tmp_path / "app-data.json", skip_app_data=True
        )
    assert touched == []
    assert not serving.exists()
    assert not dashboard.parent.exists()

    monkeypatch.delenv(REASONING_EFFORT_OVERRIDE_ENV)
    analysis.refuse_reasoning_effort_override("A step")  # unset: no refusal


def test_every_release_freezer_runs_the_treatment_check_before_it_writes():
    """The guard sits in the check, so each freezer's main must reach it first.

    Each scripts/freeze_<release>.py main calls validate_treatment (from
    freeze_adds0928) before freezer.main, which writes the serving config and
    the board rows, and before any write_json, shutil or os.replace call of
    its own.
    """
    import ast

    writes = {"write_json", "copyfile", "copy2", "copytree", "replace", "mkdir"}
    freezers = sorted(
        path
        for path in (ROOT / "scripts").glob("freeze_*.py")
        if path.name != "freeze_snapshot.py"
    )
    assert len(freezers) == 7
    for path in freezers:
        tree = ast.parse(path.read_text())
        (main,) = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        ]
        calls = [node for node in ast.walk(main) if isinstance(node, ast.Call)]

        def lines(names, calls=calls):
            return [
                call.lineno
                for call in calls
                if getattr(call.func, "id", getattr(call.func, "attr", None)) in names
            ]

        checks = lines({"validate_treatment"})
        freeze_main = [
            call.lineno
            for call in calls
            if isinstance(call.func, ast.Attribute)
            and call.func.attr == "main"
            and getattr(call.func.value, "id", None) == "freezer"
        ]
        assert checks and freeze_main, path.name
        assert min(checks) < min(freeze_main), path.name
        assert all(min(checks) < line for line in lines(writes)), path.name
