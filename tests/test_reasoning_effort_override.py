"""The one-model effort override, POLICYBENCH_REASONING_EFFORT_OVERRIDE.

The board sends no reasoning control. A sensitivity run sets the variable to
``<Claude litellm id>=<effort>`` to send that one model Anthropic's effort
parameter, ``output_config.effort``. These are unit tests: the litellm checks
replace litellm's HTTP ``post`` with a stub that records the request body and
raises, so no request leaves the process.
"""

from __future__ import annotations

import json
from pathlib import Path

import litellm
import pandas as pd
import pytest
from litellm.llms.custom_httpx import http_handler

from policybench.eval_no_tools import (
    REASONING_EFFORT_OVERRIDE_ENV,
    REASONING_EFFORT_OVERRIDES,
    SensitivityKnobError,
    _build_resume_metadata,
    _chat_completion_request_kwargs,
    _thinking_configuration,
    _treatment_metadata,
)
from policybench.scenarios import Person, Scenario, scenario_to_dict
from policybench.supervisor import Supervisor

OPUS = "claude-opus-5-5"
FABLE = "claude-fable-5-2"
# Every key through which litellm or the API could take a reasoning control.
REASONING_KEYS = {"output_config", "reasoning", "reasoning_effort", "thinking"}


@pytest.fixture(autouse=True)
def no_override(monkeypatch):
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
    _, kwargs = _chat_completion_request_kwargs(
        scenario, ["snap", "ssi"], model_id, repair=repair
    )
    return kwargs


def _sent_body(kwargs: dict, monkeypatch) -> dict:
    """The JSON body litellm would POST to Anthropic for these kwargs."""
    captured: dict = {}

    def stub_post(self, url, data=None, json=None, headers=None, **_):  # noqa: A002
        captured["url"] = url
        captured["body"] = json if json is not None else __import__("json").loads(data)
        raise RuntimeError("stub: the request is recorded, never sent")

    monkeypatch.setattr(http_handler.HTTPHandler, "post", stub_post)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-value-not-a-key")
    request = {key: value for key, value in kwargs.items() if key != "caching"}
    with pytest.raises(Exception):
        litellm.completion(**request, api_base="http://127.0.0.1:9", num_retries=0)
    assert captured["url"] == "http://127.0.0.1:9/v1/messages"
    return captured["body"]


def test_the_board_constant_stays_empty():
    assert REASONING_EFFORT_OVERRIDES == {}


def test_default_sends_no_reasoning_control(scenario, monkeypatch):
    for model_id in (OPUS, FABLE):
        kwargs = _kwargs(scenario, model_id)
        assert not REASONING_KEYS & set(kwargs), model_id
        assert not REASONING_KEYS & set(_kwargs(scenario, model_id, repair=True))
        assert _thinking_configuration(model_id) == {"mode": "provider_default"}
        body = _sent_body(kwargs, monkeypatch)
        assert not REASONING_KEYS & set(body), model_id
        assert set(body) == {"model", "messages", "max_tokens"}, model_id


@pytest.mark.parametrize(
    ("named", "effort", "other"),
    [(OPUS, "high", FABLE), (FABLE, "medium", OPUS)],
)
def test_override_sends_exactly_the_value_for_exactly_the_named_model(
    scenario, monkeypatch, named, effort, other
):
    board = {model_id: _kwargs(scenario, model_id) for model_id in (named, other)}
    board_repair = _kwargs(scenario, named, repair=True)
    board_body = {
        model_id: _sent_body(kwargs, monkeypatch) for model_id, kwargs in board.items()
    }

    monkeypatch.setenv(REASONING_EFFORT_OVERRIDE_ENV, f"{named}={effort}")
    sensitivity = _kwargs(scenario, named)
    assert sensitivity == {**board[named], "output_config": {"effort": effort}}
    assert _kwargs(scenario, named, repair=True) == {
        **board_repair,
        "output_config": {"effort": effort},
    }
    assert _kwargs(scenario, other) == board[other]

    body = _sent_body(sensitivity, monkeypatch)
    assert body == {**board_body[named], "output_config": {"effort": effort}}
    assert _sent_body(_kwargs(scenario, other), monkeypatch) == board_body[other]


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
    monkeypatch.setenv(REASONING_EFFORT_OVERRIDE_ENV, f"{FABLE}=medium")
    sensitivity = metadata()
    assert sensitivity["treatment"]["claude-fable-5.2"]["thinking"] == {
        "reasoning_effort": "medium"
    }
    assert {k: v for k, v in sensitivity.items() if k != "treatment"} == {
        k: v for k, v in board.items() if k != "treatment"
    }


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


@pytest.mark.parametrize(
    "value",
    [
        OPUS,  # no effort
        f"{OPUS}=",  # empty effort
        f"{OPUS}=extreme",  # not an Anthropic level
        f"{OPUS}=High",  # levels are lower case
        "claude-opus-5.5=high",  # a config key, not the litellm id
        "claude-opus-9-9=high",  # not a configured model
        "gpt-6.1-sol=high",  # not a Claude model
        "=high",
    ],
)
def test_a_malformed_override_fails_instead_of_sending_the_board_request(
    scenario, monkeypatch, value
):
    monkeypatch.setenv(REASONING_EFFORT_OVERRIDE_ENV, value)
    with pytest.raises(SensitivityKnobError):
        _kwargs(scenario, OPUS)
    with pytest.raises(SensitivityKnobError):
        _thinking_configuration(FABLE)
