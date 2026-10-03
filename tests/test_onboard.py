"""Gauntlet decision-tree tests with mocked provider responses."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from policybench import eval_no_tools as harness
from policybench.completion_budget import completion_budget_from_kwargs
from policybench.model_cards import MODEL_CARDS, ModelCard, card_for
from policybench.onboard import (
    PROBE_TIMEOUT_SECONDS,
    format_report,
    provisional_probe_card,
    run_gauntlet,
)
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


def test_ceiling_burn_on_full_probe_is_not_scorable(scenario):
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
    assert report.card is None
    assert "canonical whole-scenario prompt" in report.unscorable_reason
    assert "NOT SCORABLE" in format_report(report)


def test_no_viable_contract_yields_no_card(scenario):
    def respond(messages, **kwargs):
        raise RuntimeError("nope")

    with patch("policybench.onboard.completion", side_effect=respond):
        report = run_gauntlet("openrouter/example/dead", scenario, FULL_VARS)
    assert report.card is None
    assert "NOT SCORABLE" in format_report(report)


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


def test_transient_provider_error_aborts_without_falling_back_contract(scenario):
    with patch(
        "policybench.onboard.completion",
        side_effect=RuntimeError("RateLimitError: 429 Too Many Requests"),
    ):
        report = run_gauntlet("openrouter/example/rate-limited", scenario, FULL_VARS)

    assert len(report.probes) == 1
    assert report.card is None
    assert "environment error" in report.aborted


# --- The probe card -------------------------------------------------------
#
# The probes build their requests through the harness, which reads the
# model's card. A model with no card yet is probed under the provisional
# thinking-class card the gauntlet derives, served by card_for only while
# the probes run.

CARDLESS_GPT6 = "gpt-6.9-onboard-test"
# gpt-6.1-sol's 3-variable probe once it had a card (model_cards.py notes).
GPT61_SOL_PROBE_TOKENS = 735


def _tool_variables(kwargs):
    """The outputs a forced-tool probe asked for, on either transport."""
    tool = kwargs["tools"][0]
    parameters = tool.get("parameters") or tool["function"]["parameters"]
    return list(parameters["properties"]["outputs"]["properties"])


def _answer_every_probe(calls, seen_cards=None):
    """A provider that answers every forced-tool probe on either transport."""

    def respond(**kwargs):
        calls.append(kwargs)
        if seen_cards is not None:
            seen_cards.append(card_for(kwargs["model"]))
        variables = _tool_variables(kwargs)
        if "input" in kwargs:
            return fake_responses_response(variables)
        return fake_response(variables=variables)

    return respond


@contextmanager
def _provider(respond):
    with (
        patch("policybench.onboard.responses", side_effect=respond),
        patch("policybench.onboard.completion", side_effect=respond),
    ):
        yield


def fake_responses_incomplete(budget):
    """A reasoning model that spends the whole budget thinking: no answer."""
    return SimpleNamespace(
        output=[SimpleNamespace(type="reasoning", summary=[])],
        output_text=None,
        status="incomplete",
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=budget,
            total_tokens=100 + budget,
            cost=0.001,
        ),
    )


def test_cardless_reasoning_model_is_probed_under_the_thinking_budget(scenario):
    """gpt-6.1-sol, 2026-09-29: probed before its card existed, both
    3-variable probes stopped incomplete at the 384-token non-thinking budget
    and the gauntlet reported the model NOT SCORABLE."""
    assert card_for(CARDLESS_GPT6) is None
    # No family prefix covers gpt-6, so card-less it gets the default budget:
    # 96 + 96 per variable.
    assert harness._completion_controls(
        CARDLESS_GPT6, include_explanations=True, variables=FULL_VARS[:3]
    ) == {"max_completion_tokens": 384}

    calls, seen_cards = [], []

    def respond(**kwargs):
        calls.append(kwargs)
        seen_cards.append(card_for(CARDLESS_GPT6))
        budget = kwargs["max_output_tokens"]
        if budget < GPT61_SOL_PROBE_TOKENS:
            return fake_responses_incomplete(budget)
        return fake_responses_response(
            _tool_variables(kwargs), tokens=GPT61_SOL_PROBE_TOKENS
        )

    with (
        patch("policybench.onboard.responses", side_effect=respond),
        patch(
            "policybench.onboard.completion",
            side_effect=AssertionError("GPT probes must not use Chat Completions"),
        ),
    ):
        report = run_gauntlet(CARDLESS_GPT6, scenario, FULL_VARS)

    assert [call["max_output_tokens"] for call in calls] == [16_384, 16_384]
    assert [call["timeout"] for call in calls] == [300, 300]
    assert [probe.name for probe in report.probes] == ["tool-3var", "tool-full"]
    assert all(probe.ok for probe in report.probes)
    assert report.card is not None
    assert report.card.answer_contract == "tool"
    assert report.card.thinking_budget is True

    provisional = ModelCard(litellm_id=CARDLESS_GPT6, thinking_budget=True)
    assert seen_cards == [provisional, provisional]
    assert report.probe_card == provisional
    assert report.probe_card_provisional is True
    assert [(p.completion_budget, p.timeout_seconds) for p in report.probes] == [
        (16_384, 300),
        (16_384, 300),
    ]
    assert card_for(CARDLESS_GPT6) is None


@pytest.mark.parametrize(
    ("model_id", "budget_key"),
    [
        # Card-less, these got 384 tokens for 3 variables (default), 4,096
        # (claude- family) and 4,096 as max_tokens at 420s (xai/ family).
        ("openrouter/example/reasoner", "max_completion_tokens"),
        ("claude-onboard-test", "max_completion_tokens"),
        ("xai/grok-onboard-test", "max_tokens"),
    ],
)
def test_cardless_chat_probes_carry_the_thinking_class_budget(
    scenario, model_id, budget_key
):
    assert card_for(model_id) is None
    calls = []
    with _provider(_answer_every_probe(calls)):
        report = run_gauntlet(model_id, scenario, FULL_VARS)

    assert all("input" not in call for call in calls)
    assert [call[budget_key] for call in calls] == [16_384, 16_384]
    assert [call["timeout"] for call in calls] == [300, 300]
    assert report.probe_card == provisional_probe_card(model_id)
    assert report.probe_card_provisional is True
    assert card_for(model_id) is None


@pytest.mark.parametrize(
    ("model_id", "budgets", "timeout"),
    [
        # No thinking budget on the card: the claude- family budget, and the
        # 240s probe floor over the family's 120s.
        ("claude-sonnet-4-6", [4_096, 4_096], PROBE_TIMEOUT_SECONDS),
        # The card's own completion_token_cap and timeout.
        ("openrouter/moonshotai/kimi-k3", [49_152, 49_152], 1_200),
        ("xai/grok-4.7", [16_384, 16_384], 1_800),
    ],
)
def test_carded_model_keeps_probing_under_its_own_card(
    scenario, model_id, budgets, timeout
):
    card = MODEL_CARDS[model_id]
    calls = []
    with _provider(_answer_every_probe(calls)):
        report = run_gauntlet(model_id, scenario, FULL_VARS)

    assert [completion_budget_from_kwargs(call) for call in calls] == budgets
    assert [call["timeout"] for call in calls] == [timeout, timeout]
    assert report.probe_card is card
    assert report.probe_card_provisional is False
    assert MODEL_CARDS[model_id] is card


@pytest.mark.parametrize("model_id", sorted(MODEL_CARDS))
def test_every_carded_model_probes_exactly_as_the_harness_sends(scenario, model_id):
    """For a model with a card, the provisional card never takes effect: each
    probe's budget and timeout are the harness's own for that card."""
    calls = []
    with _provider(_answer_every_probe(calls)):
        report = run_gauntlet(model_id, scenario, FULL_VARS)

    expected = [
        (
            completion_budget_from_kwargs(
                harness._completion_controls(
                    model_id, include_explanations=True, variables=variables
                )
            ),
            max(PROBE_TIMEOUT_SECONDS, harness._request_timeout_seconds(model_id)),
        )
        for variables in (FULL_VARS[:3], FULL_VARS)
    ]
    assert [
        (completion_budget_from_kwargs(call), call["timeout"]) for call in calls
    ] == expected
    assert report.probe_card is MODEL_CARDS[model_id]
    assert report.probe_card_provisional is False


class _MalformedResponse:
    """A provider response whose every field read fails outside the probe's
    request guard, so the error escapes run_gauntlet."""

    def __getattr__(self, name):
        raise ValueError(f"malformed provider response: no {name}")


def _scripted_provider(model_id, outcomes, seen_cards):
    script = iter(outcomes)

    def respond(**kwargs):
        seen_cards.append(card_for(model_id))
        outcome = next(script)
        variables = _tool_variables(kwargs) if kwargs.get("tools") else FULL_VARS
        responses_api = "input" in kwargs
        if outcome == "refuse":
            raise RuntimeError("BadRequestError: tool_choice is not supported")
        if outcome == "credits":
            raise RuntimeError("This request requires more credits")
        if outcome == "interrupt":
            raise KeyboardInterrupt
        if outcome == "malformed":
            return _MalformedResponse()
        if outcome == "burn":
            budget = completion_budget_from_kwargs(kwargs)
            if responses_api:
                return fake_responses_incomplete(budget)
            return fake_response(tokens=budget, finish="length", empty=True)
        if responses_api:
            if kwargs.get("tools"):
                return fake_responses_response(variables)
            return fake_responses_json_response(variables)
        return fake_response(variables=variables, tool_call=bool(kwargs.get("tools")))

    return respond


GAUNTLET_OUTCOMES = ("answer", "burn", "refuse", "credits", "malformed", "interrupt")
OUTCOME_MODEL_IDS = (
    CARDLESS_GPT6,
    "openrouter/example/reasoner",
    "xai/grok-onboard-test",
    "gpt-6.1-sol",
    "claude-sonnet-4-6",
    "openrouter/moonshotai/kimi-k3",
)


@pytest.mark.parametrize("model_id", OUTCOME_MODEL_IDS)
@pytest.mark.parametrize(
    ("first_probe", "escapes"),
    [
        ("refuse", None),
        ("credits", None),
        ("malformed", ValueError),
        ("interrupt", KeyboardInterrupt),
    ],
)
def test_model_cards_unchanged_when_a_probe_raises(
    scenario, model_id, first_probe, escapes
):
    before = dict(MODEL_CARDS)
    own_card = card_for(model_id)
    seen_cards = []
    respond = _scripted_provider(model_id, [first_probe, "refuse"], seen_cards)

    with _provider(respond):
        if escapes is None:
            report = run_gauntlet(model_id, scenario, FULL_VARS)
            assert report.card is None
        else:
            with pytest.raises(escapes):
                run_gauntlet(model_id, scenario, FULL_VARS)

    # The probe ran under the card in effect, and that card is gone again.
    assert seen_cards[0] == (own_card or provisional_probe_card(model_id))
    assert MODEL_CARDS.keys() == before.keys()
    assert all(MODEL_CARDS[key] is card for key, card in before.items())
    assert card_for(model_id) is own_card


@settings(max_examples=150, deadline=None)
@given(
    model_id=st.sampled_from(OUTCOME_MODEL_IDS),
    outcomes=st.lists(st.sampled_from(GAUNTLET_OUTCOMES), min_size=3, max_size=3),
)
def test_model_cards_unchanged_after_any_gauntlet_outcome(scenario, model_id, outcomes):
    """Invariant: whatever the probes return or raise, run_gauntlet leaves
    MODEL_CARDS exactly as it found it, and every probe ran under the card
    in effect (the model's own, else the provisional one)."""
    before = dict(MODEL_CARDS)
    own_card = card_for(model_id)
    seen_cards = []
    with _provider(_scripted_provider(model_id, outcomes, seen_cards)):
        try:
            run_gauntlet(model_id, scenario, FULL_VARS)
        except (ValueError, KeyboardInterrupt):
            pass

    assert seen_cards
    assert set(seen_cards) == {own_card or provisional_probe_card(model_id)}
    assert MODEL_CARDS.keys() == before.keys()
    assert all(MODEL_CARDS[key] is card for key, card in before.items())
    assert card_for(model_id) is own_card


CARDLESS_PREFIXES = (
    "gpt-6.",
    "gpt-5.",
    "claude-",
    "xai/",
    "gemini/",
    "deepseek/",
    "openrouter/example/",
    "",
)


@settings(max_examples=80, deadline=None)
@given(
    prefix=st.sampled_from(CARDLESS_PREFIXES),
    suffix=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-.", max_size=8),
    variable_count=st.integers(min_value=3, max_value=24),
)
def test_automatic_probe_card_matches_a_hand_written_provisional_card(
    scenario, prefix, suffix, variable_count
):
    """Differential: probing a card-less model sends exactly the requests the
    old workaround did (a hand-written thinking-budget card registered before
    onboarding), and derives the same card."""
    model_id = f"{prefix}onboard-{suffix}"
    assert card_for(model_id) is None
    variables = [f"var_{i}" for i in range(variable_count)]

    automatic_calls = []
    with _provider(_answer_every_probe(automatic_calls)):
        automatic = run_gauntlet(model_id, scenario, variables)
    assert card_for(model_id) is None

    hand_written_calls = []
    hand_written_card = ModelCard(litellm_id=model_id, thinking_budget=True)
    with (
        patch.dict(MODEL_CARDS, {model_id: hand_written_card}),
        _provider(_answer_every_probe(hand_written_calls)),
    ):
        hand_written = run_gauntlet(model_id, scenario, variables)

    assert automatic_calls == hand_written_calls
    assert automatic.card == hand_written.card
    assert automatic.probe_card == hand_written.probe_card == hand_written_card
    assert automatic.probe_card_provisional is True
    assert hand_written.probe_card_provisional is False
    # The derived card is the probe card plus the probe findings.
    assert (
        replace(
            automatic.card,
            answer_contract=None,
            request_timeout_seconds=None,
            expected_cost_per_scenario_usd=None,
            notes="",
        )
        == automatic.probe_card
    )


def test_report_records_the_provisional_probe_card(scenario):
    calls = []
    with _provider(_answer_every_probe(calls)):
        report = run_gauntlet(CARDLESS_GPT6, scenario, FULL_VARS)
    text = format_report(report)

    assert (
        "Probe card: provisional (thinking_budget=True). The model has no card" in text
    )
    assert "s of 300s, tokens=200 of 16384, finish=" in text
    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["probe_card"] == vars(provisional_probe_card(CARDLESS_GPT6))
    assert payload["probe_card_provisional"] is True
    assert [probe["completion_budget"] for probe in payload["probes"]] == [
        16_384,
        16_384,
    ]
    assert [probe["timeout_seconds"] for probe in payload["probes"]] == [300, 300]


def test_report_records_the_existing_probe_card(scenario):
    calls = []
    with _provider(_answer_every_probe(calls)):
        report = run_gauntlet("claude-sonnet-4-6", scenario, FULL_VARS)
    text = format_report(report)

    assert (
        "Probe card: the model's card in policybench/model_cards.py "
        "(provider_max_completion_tokens=64000)." in text
    )
    assert "tokens=200 of 4096" in text
    payload = report.to_dict()
    assert payload["probe_card"] == vars(MODEL_CARDS["claude-sonnet-4-6"])
    assert payload["probe_card_provisional"] is False


@pytest.mark.parametrize(
    ("first_probe", "verdict"),
    [
        ("answer", "Suggested ModelCard"),
        ("credits", "ABORTED"),
        ("burn", "NOT SCORABLE"),
    ],
)
def test_every_verdict_names_the_probe_card(scenario, first_probe, verdict):
    seen_cards = []
    outcomes = [first_probe, first_probe, first_probe]
    with _provider(_scripted_provider(CARDLESS_GPT6, outcomes, seen_cards)):
        report = run_gauntlet(CARDLESS_GPT6, scenario, FULL_VARS)
    text = format_report(report)

    assert verdict in text
    assert "Probe card: provisional (thinking_budget=True)" in text


def test_probe_that_fails_before_sending_records_no_budget(scenario):
    with patch(
        "policybench.onboard._probe_request",
        side_effect=RuntimeError("could not build the request"),
    ):
        report = run_gauntlet("openrouter/example/broken", scenario, FULL_VARS)

    assert report.probes[0].completion_budget is None
    assert report.probes[0].timeout_seconds is None
    assert "s of ?, tokens=None of ?," in format_report(report)
    assert card_for("openrouter/example/broken") is None


def test_failed_request_records_the_budget_and_timeout_it_was_sent_with(scenario):
    """A probe whose request raises (a refusal, a timeout) still records the
    budget and timeout it ran under, so a timed-out probe can be diagnosed."""
    with patch(
        "policybench.onboard.completion",
        side_effect=RuntimeError("BadRequestError: tool_choice is not supported"),
    ):
        report = run_gauntlet("openrouter/example/refuser", scenario, FULL_VARS)

    assert [probe.name for probe in report.probes] == ["tool-3var", "json-3var"]
    assert all(probe.error for probe in report.probes)
    assert [(p.completion_budget, p.timeout_seconds) for p in report.probes] == [
        (16_384, 300),
        (16_384, 300),
    ]
    assert "s of 300s, tokens=None of 16384, finish=None)" in format_report(report)


def test_derived_card_follows_the_provisional_probe_card(scenario):
    """The suggested card is the provisional card plus the probe findings, so
    any field the probes ran under carries into the suggestion."""
    model_id = "openrouter/example/long-reasoner"
    capped = ModelCard(
        litellm_id=model_id, thinking_budget=True, completion_token_cap=49_152
    )
    calls = []
    with (
        patch("policybench.onboard.provisional_probe_card", return_value=capped),
        _provider(_answer_every_probe(calls)),
    ):
        report = run_gauntlet(model_id, scenario, FULL_VARS)

    assert [call["max_completion_tokens"] for call in calls] == [49_152, 49_152]
    assert report.probe_card is capped
    assert report.card.completion_token_cap == 49_152
    assert report.card.thinking_budget is True
    assert card_for(model_id) is None
