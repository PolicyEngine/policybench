"""Gauntlet decision-tree tests with mocked provider responses."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from policybench.onboard import format_report, run_gauntlet
from policybench.scenarios import generate_scenarios

FULL_VARS = [f"var_{i}" for i in range(16)]


@pytest.fixture(scope="module")
def scenario():
    return generate_scenarios(n=1, seed=0)[0]


def fake_response(
    variables=None, tokens=200, finish="stop", tool_call=True, empty=False
):
    if empty:
        message = SimpleNamespace(content=None, tool_calls=None, function_call=None)
    elif tool_call:
        import json

        arguments = json.dumps(
            {"outputs": {v: {"value": 1, "explanation": "x"} for v in variables}}
        )
        call = SimpleNamespace(
            function=SimpleNamespace(name="submit_outputs", arguments=arguments)
        )
        message = SimpleNamespace(content=None, tool_calls=[call], function_call=None)
    else:
        import json

        content = json.dumps(
            {"outputs": {v: {"value": 1, "explanation": "x"} for v in variables}}
        )
        message = SimpleNamespace(content=content, tool_calls=None, function_call=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish)],
        usage=SimpleNamespace(completion_tokens=tokens, cost=0.002),
    )


def test_clean_tool_model_gets_tool_contract(scenario):
    def respond(messages, **kwargs):
        tools = kwargs.get("tools")
        variables = (
            list(
                tools[0]["function"]["parameters"]["properties"]["outputs"][
                    "properties"
                ]
            )
            if tools
            else FULL_VARS
        )
        return fake_response(variables=variables, tool_call=bool(tools))

    with patch("policybench.onboard.completion", side_effect=respond):
        report = run_gauntlet("openrouter/example/clean", scenario, FULL_VARS)
    assert report.card.answer_contract == "tool"
    assert report.card.explanation_chunk_size is None
    assert report.card.request_timeout_seconds is None


def test_tool_rejection_falls_to_json(scenario):
    def respond(messages, **kwargs):
        if kwargs.get("tools"):
            raise RuntimeError("tool_choice incompatible with thinking")
        return fake_response(variables=_requested(messages), tool_call=False)

    def _requested(messages):
        text = messages[0]["content"]
        return [v for v in (FULL_VARS + ["payroll_tax", "snap", "ssi"]) if v in text]

    with patch("policybench.onboard.completion", side_effect=respond):
        report = run_gauntlet("openrouter/example/no-tools", scenario, FULL_VARS)
    assert report.card.answer_contract == "json"
    names = [p.name for p in report.probes]
    assert names == ["tool-3var", "json-3var", "json-full"]


def test_ceiling_burn_on_full_probe_triggers_chunking(scenario):
    calls = {"n": 0}

    def respond(messages, **kwargs):
        calls["n"] += 1
        text = messages[0]["content"]
        requested = [
            v for v in (FULL_VARS + ["payroll_tax", "snap", "ssi"]) if v in text
        ]
        if len(requested) > 3:
            return fake_response(tokens=16_384, finish="length", empty=True)
        return fake_response(variables=requested, tool_call=bool(kwargs.get("tools")))

    with patch("policybench.onboard.completion", side_effect=respond):
        report = run_gauntlet("openrouter/example/burner", scenario, FULL_VARS)
    assert report.card.explanation_chunk_size == 3
    assert report.card.expected_cost_per_scenario_usd is not None


def test_no_viable_contract_yields_no_card(scenario):
    def respond(messages, **kwargs):
        raise RuntimeError("nope")

    with patch("policybench.onboard.completion", side_effect=respond):
        report = run_gauntlet("openrouter/example/dead", scenario, FULL_VARS)
    assert report.card is None
    assert "cannot run the benchmark" in format_report(report)


def test_slow_probes_earn_extended_timeout(scenario):
    clock = {"t": 0.0}

    def fake_time():
        clock["t"] += 200.0
        return clock["t"]

    def respond(messages, **kwargs):
        tools = kwargs.get("tools")
        variables = (
            list(
                tools[0]["function"]["parameters"]["properties"]["outputs"][
                    "properties"
                ]
            )
            if tools
            else FULL_VARS
        )
        return fake_response(variables=variables, tool_call=bool(tools))

    with (
        patch("policybench.onboard.completion", side_effect=respond),
        patch("policybench.onboard.time.time", side_effect=fake_time),
    ):
        report = run_gauntlet("openrouter/example/slow", scenario, FULL_VARS)
    assert report.card.request_timeout_seconds == 600


def test_credit_errors_abort_without_card(scenario):
    def respond(messages, **kwargs):
        if kwargs.get("tools"):
            variables = list(
                kwargs["tools"][0]["function"]["parameters"]["properties"]["outputs"][
                    "properties"
                ]
            )
            if len(variables) > 3:
                raise RuntimeError(
                    "This request requires more credits, or fewer max_tokens."
                )
            return fake_response(variables=variables, tool_call=True)
        return fake_response(variables=FULL_VARS, tool_call=False)

    with patch("policybench.onboard.completion", side_effect=respond):
        report = run_gauntlet("openrouter/example/broke", scenario, FULL_VARS)
    assert report.card is None
    assert "environment error" in report.aborted
    assert "no card derived" in format_report(report)
