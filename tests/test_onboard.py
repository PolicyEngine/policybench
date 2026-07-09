"""Gauntlet decision-tree tests with mocked provider responses."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from policybench.onboard import format_report, run_gauntlet
from policybench.scenarios import Person, Scenario

FULL_VARS = [f"var_{i}" for i in range(16)]


@pytest.fixture(scope="module")
def scenario():
    # Synthetic scenario: generate_scenarios() loads the certified populace
    # frame, which is far too heavy for CI runners.
    return Scenario(
        id="scenario_000",
        state="CA",
        filing_status="SINGLE",
        adults=[Person(name="adult_1", age=35, employment_income=30_000.0)],
    )


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


def fake_responses_response(variables, tokens=200):
    import json

    arguments = json.dumps(
        {"outputs": {v: {"value": 1, "explanation": "x"} for v in variables}}
    )
    return SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="submit_outputs",
                arguments=arguments,
            )
        ],
        output_text=None,
        status="completed",
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=tokens,
            total_tokens=100 + tokens,
            cost=0.002,
        ),
    )


def fake_responses_json_response(variables, tokens=200):
    import json

    content = json.dumps(
        {"outputs": {v: {"value": 1, "explanation": "x"} for v in variables}}
    )
    return SimpleNamespace(
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="output_text", text=content)],
            )
        ],
        output_text=content,
        status="completed",
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=tokens,
            total_tokens=100 + tokens,
            cost=0.002,
        ),
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
    assert report.card.expected_cost_per_scenario_usd == pytest.approx(0.002)


def test_small_probe_uses_supplied_country_variables(scenario):
    uk_scenario = Scenario(
        id=scenario.id,
        state="",
        filing_status=None,
        adults=scenario.adults,
        country="uk",
        source_dataset="enhanced_frs_2023_24",
    )
    uk_variables = [
        "income_tax",
        "national_insurance",
        "capital_gains_tax",
        "child_benefit",
        "universal_credit",
    ]
    requested = []

    def respond(messages, **kwargs):
        variables = list(
            kwargs["tools"][0]["function"]["parameters"]["properties"]["outputs"][
                "properties"
            ]
        )
        requested.append(variables)
        return fake_response(variables=variables)

    with patch("policybench.onboard.completion", side_effect=respond):
        report = run_gauntlet("openrouter/example/uk-clean", uk_scenario, uk_variables)

    assert report.card is not None
    assert requested[0] == uk_variables[:3]
    assert requested[1] == uk_variables


def test_gpt_model_probe_uses_responses_api_like_production(scenario):
    calls = []

    def respond(**kwargs):
        calls.append(kwargs)
        tool = kwargs["tools"][0]
        variables = list(tool["parameters"]["properties"]["outputs"]["properties"])
        return fake_responses_response(variables)

    with (
        patch("policybench.onboard.responses", side_effect=respond),
        patch(
            "policybench.onboard.completion",
            side_effect=AssertionError("GPT probes must not use Chat Completions"),
        ),
    ):
        report = run_gauntlet("gpt-5.6-sol", scenario, FULL_VARS)

    assert report.card.answer_contract == "tool"
    assert report.card.explanation_chunk_size is None
    assert len(calls) == 2
    assert all(call["model"] == "gpt-5.6-sol" for call in calls)
    assert all("input" in call and "messages" not in call for call in calls)
    assert all(call["max_output_tokens"] == 16_384 for call in calls)
    assert all(call["timeout"] == 300 for call in calls)


def test_gpt_responses_tool_rejection_falls_back_to_json(scenario):
    def respond(**kwargs):
        if kwargs.get("tools"):
            raise RuntimeError("tool_choice incompatible with this model")
        requested = [variable for variable in FULL_VARS if variable in kwargs["input"]]
        return fake_responses_json_response(requested)

    with (
        patch("policybench.onboard.responses", side_effect=respond),
        patch(
            "policybench.onboard.completion",
            side_effect=AssertionError("GPT probes must not use Chat Completions"),
        ),
    ):
        report = run_gauntlet("gpt-5.6-sol", scenario, FULL_VARS)

    assert [probe.name for probe in report.probes] == [
        "tool-3var",
        "json-3var",
        "json-full",
    ]
    assert report.card.answer_contract == "json"
    assert report.card.explanation_chunk_size is None


def test_tool_rejection_falls_to_json(scenario):
    def respond(messages, **kwargs):
        if kwargs.get("tools"):
            raise RuntimeError(
                "BadRequestError: tool_choice incompatible with thinking"
            )
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
    assert report.card.expected_cost_per_scenario_usd == pytest.approx(0.012)


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


@pytest.mark.parametrize(
    "message",
    [
        "NotFoundError: model gpt-5.6-sol does not exist or you do not have access",
        "PermissionDeniedError: permission denied for this organization",
        "RateLimitError: insufficient_quota; exceeded your current quota",
    ],
)
def test_rollout_access_errors_abort_without_shaping_card(scenario, message):
    with patch("policybench.onboard.responses", side_effect=RuntimeError(message)):
        report = run_gauntlet("gpt-5.6-sol", scenario, FULL_VARS)

    assert len(report.probes) == 1
    assert report.card is None
    assert "environment error" in report.aborted


def test_missing_meta_key_aborts_before_provider_call(monkeypatch, scenario):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-reused")

    report = run_gauntlet(
        "openai/muse-spark-1.1",
        scenario,
        FULL_VARS,
    )

    assert len(report.probes) == 1
    assert report.card is None
    assert "MODEL_API_KEY" in report.probes[0].error
    assert "environment error" in report.aborted


def test_transient_provider_error_aborts_without_falling_back_contract(scenario):
    with patch(
        "policybench.onboard.completion",
        side_effect=RuntimeError("RateLimitError: 429 Too Many Requests"),
    ):
        report = run_gauntlet("openrouter/example/rate-limited", scenario, FULL_VARS)

    assert len(report.probes) == 1
    assert report.card is None
    assert "environment error" in report.aborted
