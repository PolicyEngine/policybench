"""Batch-mode eval: request parity, result normalization, repair, resume."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from policybench.batch_eval import (
    AnthropicBatchAdapter,
    BatchRunState,
    BatchUnit,
    NormalizedResult,
    OpenAIBatchAdapter,
    _normalize_anthropic_entry,
    _normalize_openai_entry,
    _openai_kwargs_to_anthropic_params,
    adapter_for_model,
    build_units,
    parse_unit_result,
    rows_from_unit,
    run_batch_eval,
)
from policybench.eval_no_tools import _chat_completion_request_kwargs
from policybench.scenarios import Person, Scenario
from policybench.spec import expand_programs_for_scenario
from policybench.spend_ledger import read_spend_ledger, spend_ledger_path


@pytest.fixture
def scenario():
    return Scenario(
        id="scenario_000",
        state="CA",
        filing_status="single",
        adults=[Person(name="adult1", age=35, employment_income=50_000.0)],
        year=2026,
    )


@pytest.fixture
def second_scenario():
    return Scenario(
        id="scenario_001",
        state="TX",
        filing_status="single",
        adults=[Person(name="adult1", age=40, employment_income=30_000.0)],
        year=2026,
    )


def test_anthropic_request_translation_matches_sync_shape(scenario):
    """The batch body must carry the same prompt, forced tool, and token
    ceiling the sync path sends, in Messages-API form."""
    _, kwargs = _chat_completion_request_kwargs(
        scenario=scenario,
        variables=["eitc"],
        model_id="claude-sonnet-5",
        repair=False,
        include_explanations=True,
    )
    params = _openai_kwargs_to_anthropic_params(kwargs)

    assert params["model"] == "claude-sonnet-5"
    assert params["max_tokens"] == 16384
    assert [message["role"] for message in params["messages"]] == ["user"]
    assert params["messages"][0]["content"] == kwargs["messages"][0]["content"]
    (tool,) = params["tools"]
    assert tool["name"] == "submit_outputs"
    outputs_schema = tool["input_schema"]["properties"]["outputs"]
    assert outputs_schema["properties"]["eitc"]["required"] == [
        "value",
        "explanation",
    ]
    assert params["tool_choice"] == {"type": "tool", "name": "submit_outputs"}


def test_anthropic_translation_rejects_unknown_parameters():
    """A new sync request feature must be translated deliberately, not
    silently dropped from batch requests."""
    with pytest.raises(ValueError, match="response_format"):
        _openai_kwargs_to_anthropic_params(
            {
                "model": "claude-sonnet-5",
                "messages": [{"role": "user", "content": "hi"}],
                "max_completion_tokens": 100,
                "response_format": {"type": "json_object"},
            }
        )


def test_adapter_routing():
    assert isinstance(adapter_for_model("claude-fable-5"), AnthropicBatchAdapter)
    assert adapter_for_model("gpt-5.5").provider == "openai"
    for model_id in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
        assert adapter_for_model(model_id).provider == "openai"
    assert adapter_for_model("gemini/gemini-3.5-flash").provider == "gemini"
    assert adapter_for_model("xai/grok-4.3") is None
    assert adapter_for_model("deepseek/deepseek-v4-pro") is None


def test_anthropic_batch_preflight_rejects_json_contract():
    with pytest.raises(
        ValueError,
        match=(
            "batch adapter supports the forced tool contract only; "
            "run claude-fable-5-1 through the supervisor"
        ),
    ):
        adapter_for_model("claude-fable-5-1")


def test_batch_cli_reports_json_contract_error_before_dispatch(
    monkeypatch, scenario, tmp_path
):
    from policybench.cli import main

    monkeypatch.setattr(
        "policybench.scenarios.load_scenarios_from_manifest", lambda _path: [scenario]
    )
    monkeypatch.setattr(
        "policybench.batch_eval.run_batch_eval",
        lambda **_kwargs: pytest.fail("unsupported model dispatched batch work"),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "policybench",
            "eval-no-tools-batch",
            "--model",
            "claude-fable-5.1",
            "--scenario-manifest",
            str(tmp_path / "scenarios.csv"),
            "--output-dir",
            str(tmp_path / "batch"),
            "--country",
            "us",
        ],
    )

    with pytest.raises(SystemExit, match="forced tool contract only.*supervisor"):
        main()


@pytest.mark.parametrize("explicit_adapter", [False, True])
def test_anthropic_json_contract_is_rejected_before_batch_work(
    tmp_path, scenario, explicit_adapter
):
    client = MagicMock()
    run_dir = tmp_path / "batch"

    with pytest.raises(ValueError, match="forced tool contract only"):
        run_batch_eval(
            scenarios=[scenario],
            programs=["eitc"],
            model_name="claude-fable-5.1",
            model_id="claude-fable-5-1",
            run_dir=run_dir,
            adapter=AnthropicBatchAdapter(client=client) if explicit_adapter else None,
        )

    client.messages.batches.create.assert_not_called()
    assert not run_dir.exists()


@pytest.mark.parametrize(
    "knob,value",
    [("POLICYBENCH_CONTRACT_OVERRIDE", "json"), ("POLICYBENCH_TOOL_CHOICE", "auto")],
)
def test_anthropic_batch_preflight_uses_effective_contract(monkeypatch, knob, value):
    monkeypatch.setenv(knob, value)

    with pytest.raises(ValueError, match="forced tool contract only"):
        adapter_for_model("claude-fable-5")


def test_openai_batch_body_rejects_connection_secrets(monkeypatch, scenario):
    monkeypatch.setattr(
        "policybench.batch_eval._responses_request_kwargs",
        lambda **_: (
            [],
            {
                "model": "gpt-5.6-sol",
                "api_key": "must-not-enter-body",
            },
        ),
    )
    adapter = OpenAIBatchAdapter(client=MagicMock())
    unit = BatchUnit(scenario.id, ["eitc"], 0)

    with pytest.raises(ValueError, match="must never enter a batch body"):
        adapter.build_request_body(scenario, unit, "gpt-5.6-sol")


def test_run_batch_rejects_explicit_adapter_model_mismatch(tmp_path, scenario):
    adapter = OpenAIBatchAdapter(client=MagicMock())

    with pytest.raises(ValueError, match="does not support"):
        run_batch_eval(
            scenarios=[scenario],
            programs=["eitc"],
            model_name="grok-4.3",
            model_id="xai/grok-4.3",
            run_dir=tmp_path,
            adapter=adapter,
        )


def test_gpt_56_batch_body_uses_public_responses_id(scenario):
    adapter = adapter_for_model("gpt-5.6-sol")
    unit = BatchUnit(scenario.id, ["eitc"], 0)

    body = adapter.build_request_body(scenario, unit, "gpt-5.6-sol")

    assert body["model"] == "gpt-5.6-sol"
    assert body["max_output_tokens"] == 16_384
    assert body["tool_choice"] == {"type": "function", "name": "submit_outputs"}
    assert "timeout" not in body


def test_build_units_mirrors_sync_chunking(scenario):
    programs = ["eitc", "snap", "medicaid_eligible"]
    units = build_units([scenario], programs, "claude-sonnet-5")
    expanded = expand_programs_for_scenario(programs, scenario)
    # Claude explanation runs chunk one output per request.
    assert [unit.variables for unit in units] == [[v] for v in expanded]
    assert all(len(unit.custom_id) <= 64 for unit in units)
    assert all(c.isalnum() or c in "_-" for unit in units for c in unit.custom_id)
    # Completed keys are skipped.
    done = {(scenario.id, expanded[0])}
    remaining = build_units([scenario], programs, "claude-sonnet-5", done)
    assert len(remaining) == len(units) - 1


def test_normalize_anthropic_entry_success_and_error():
    entry = SimpleNamespace(
        custom_id="scenario_000__u000",
        result=SimpleNamespace(
            type="succeeded",
            message=SimpleNamespace(
                id="msg_01",
                model="claude-sonnet-5",
                content=[
                    SimpleNamespace(type="text", text="working"),
                    SimpleNamespace(
                        type="tool_use",
                        name="submit_outputs",
                        input={
                            "outputs": {"eitc": {"value": 4022.0, "explanation": "ok"}}
                        },
                    ),
                ],
                usage=SimpleNamespace(
                    input_tokens=100,
                    output_tokens=50,
                    cache_read_input_tokens=20,
                    cache_creation_input_tokens=10,
                ),
            ),
        ),
    )
    normalized = _normalize_anthropic_entry(entry)
    assert normalized.prompt_tokens == 130
    assert normalized.cached_prompt_tokens == 20
    assert normalized.cache_write_prompt_tokens == 10
    assert normalized.tool_calls[0].function.name == "submit_outputs"
    assert json.loads(normalized.tool_calls[0].function.arguments) == {
        "outputs": {"eitc": {"value": 4022.0, "explanation": "ok"}}
    }

    errored = SimpleNamespace(
        custom_id="scenario_000__u001",
        result=SimpleNamespace(
            type="errored", error=SimpleNamespace(type="rate_limit", message="slow")
        ),
    )
    assert "rate_limit" in _normalize_anthropic_entry(errored).error or (
        "slow" in _normalize_anthropic_entry(errored).error
    )


def test_normalize_openai_entry_responses_shape():
    entry = {
        "custom_id": "scenario_000__u000",
        "response": {
            "status_code": 200,
            "body": {
                "id": "resp_01",
                "model": "gpt-5.5",
                "output": [
                    {
                        "type": "function_call",
                        "name": "submit_outputs",
                        "arguments": json.dumps(
                            {"eitc": {"value": 1.0, "explanation": "x"}}
                        ),
                    }
                ],
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "input_tokens_details": {
                        "cached_tokens": 4,
                        "cache_write_tokens": 3,
                    },
                    "output_tokens_details": {"reasoning_tokens": 2},
                },
            },
        },
    }
    normalized = _normalize_openai_entry(entry)
    assert normalized.reasoning_tokens == 2
    assert normalized.cached_prompt_tokens == 4
    assert normalized.cache_write_prompt_tokens == 3
    assert normalized.tool_calls[0].function.name == "submit_outputs"


def test_parse_unit_result_roundtrip(scenario):
    unit = BatchUnit(scenario_id=scenario.id, variables=["eitc"], chunk_index=0)
    result = NormalizedResult(
        custom_id=unit.custom_id,
        tool_calls=[
            SimpleNamespace(
                function=SimpleNamespace(
                    name="submit_outputs",
                    arguments=json.dumps(
                        {
                            "outputs": {
                                "eitc": {
                                    "value": 4022.0,
                                    "explanation": "34% of earned. value = 4022",
                                }
                            }
                        }
                    ),
                )
            )
        ],
    )
    predictions, explanations, raw, error = parse_unit_result(unit, result)
    assert error is None
    assert predictions == {"eitc": 4022.0}
    assert explanations["eitc"] == "34% of earned. value = 4022"
    assert "submit_outputs" in raw


def test_rows_apportion_usage_and_omit_latency():
    unit = BatchUnit(
        scenario_id="scenario_000",
        variables=["eitc", "snap", "ssi"],
        chunk_index=0,
    )
    result = NormalizedResult(
        custom_id=unit.custom_id, prompt_tokens=300, completion_tokens=30
    )
    rows = rows_from_unit(
        model_name="gpt-5.5",
        model_id="gpt-5.5",
        unit=unit,
        predictions={"eitc": 1.0, "snap": 2.0, "ssi": 3.0},
        explanations={"eitc": "a", "snap": "b", "ssi": "c"},
        raw_response="{}",
        error=None,
        result=result,
    )
    assert len(rows) == 3
    assert all(row["prompt_tokens"] == 100 for row in rows)
    assert all(row["elapsed_seconds"] is None for row in rows)
    assert all(row["request_started_at"] is None for row in rows)
    # Cost reconstructed at standard sync rates for leaderboard parity.
    assert rows[0]["reconstructed_cost_usd"] is not None
    assert rows[0]["total_cost_usd"] == rows[0]["reconstructed_cost_usd"]
    assert rows[0]["cost_is_estimated"] is True


def test_anthropic_batch_cost_uses_policybench_price_override():
    unit = BatchUnit("scenario_000", ["eitc"], 0)
    result = NormalizedResult(
        custom_id=unit.custom_id,
        prompt_tokens=130,
        completion_tokens=50,
        cached_prompt_tokens=20,
        cache_write_prompt_tokens=10,
    )
    rows = rows_from_unit(
        model_name="claude-sonnet-5",
        model_id="claude-sonnet-5",
        unit=unit,
        predictions={"eitc": 1.0},
        explanations={"eitc": "x"},
        raw_response="{}",
        error=None,
        result=result,
    )
    expected = 130 * 3e-6 + 50 * 15e-6

    assert rows[0]["reconstructed_cost_usd"] == pytest.approx(expected)
    assert rows[0]["cost_is_estimated"] is False
    assert rows[0]["cache_write_prompt_tokens"] == 10


@pytest.mark.parametrize(
    ("prompt_tokens", "completion_tokens", "cached", "cache_write", "expected"),
    [
        (100_000, 0, 0, 100_000, 0.625),
        (300_000, 10_000, 0, 300_000, 4.2),
        (100_000, 0, 100_000, 0, 0.05),
    ],
)
def test_gpt_56_batch_cost_uses_cache_and_long_context_rates(
    prompt_tokens, completion_tokens, cached, cache_write, expected
):
    unit = BatchUnit("scenario_000", ["eitc"], 0)
    result = NormalizedResult(
        custom_id=unit.custom_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_prompt_tokens=cached,
        cache_write_prompt_tokens=cache_write,
    )
    rows = rows_from_unit(
        model_name="gpt-5.6-sol",
        model_id="gpt-5.6-sol",
        unit=unit,
        predictions={"eitc": 1.0},
        explanations={"eitc": "x"},
        raw_response="{}",
        error=None,
        result=result,
    )

    assert rows[0]["reconstructed_cost_usd"] == pytest.approx(expected)
    assert rows[0]["cache_write_prompt_tokens"] == cache_write


class FakeAdapter:
    """Scripted adapter: first round breaks one unit, repair round fixes it."""

    provider = "fake"

    def __init__(self):
        self.submissions: list[list[tuple[str, dict]]] = []
        self.status_calls = 0

    def supports(self, model_id: str) -> bool:
        return True

    def build_request_body(self, scenario, unit, model_id):
        return {"scenario": scenario.id, "variables": unit.variables}

    def submit(self, requests, model_id):
        self.submissions.append(requests)
        return f"batch_{len(self.submissions)}"

    def status(self, batch_id):
        self.status_calls += 1
        return "ended"

    def results(self, batch_id):
        round_index = int(batch_id.split("_")[1]) - 1
        for custom_id, body in self.submissions[round_index]:
            variables = body["variables"]
            good = {
                "outputs": {
                    variable: {
                        "value": 1000.0,
                        "explanation": f"repaired {variable}. value = 1000",
                    }
                    for variable in variables
                }
            }
            if round_index == 0 and custom_id.endswith("u001"):
                # Missing explanation -> violates the contract -> repair target.
                yield NormalizedResult(
                    custom_id=custom_id,
                    tool_calls=[
                        SimpleNamespace(
                            function=SimpleNamespace(
                                name="submit_outputs",
                                arguments=json.dumps(
                                    {
                                        "outputs": {
                                            variable: {
                                                "value": 7.0,
                                                "explanation": "",
                                            }
                                            for variable in variables
                                        }
                                    }
                                ),
                            )
                        )
                    ],
                    prompt_tokens=10,
                    completion_tokens=5,
                )
                continue
            yield NormalizedResult(
                custom_id=custom_id,
                tool_calls=[
                    SimpleNamespace(
                        function=SimpleNamespace(
                            name="submit_outputs", arguments=json.dumps(good)
                        )
                    )
                ],
                prompt_tokens=10,
                completion_tokens=5,
            )


def test_run_batch_eval_end_to_end_with_repair(tmp_path, scenario, second_scenario):
    adapter = FakeAdapter()
    frame = run_batch_eval(
        scenarios=[scenario, second_scenario],
        programs=["eitc", "snap"],
        model_name="claude-sonnet-5",
        model_id="claude-sonnet-5",
        run_dir=tmp_path,
        adapter=adapter,
        poll_seconds=0,
        sleep=lambda _s: None,
        log=lambda *_a, **_k: None,
    )

    expanded = expand_programs_for_scenario(["eitc", "snap"], scenario)
    assert len(frame) == 2 * len(expanded)
    # Every row satisfies the answer contract after the repair round.
    assert frame["prediction"].notna().all()
    assert frame["explanation"].astype(str).str.strip().ne("").all()
    # The broken unit was re-requested in a second, smaller submission.
    assert len(adapter.submissions) == 2
    assert len(adapter.submissions[1]) == 2  # one broken unit per scenario
    # Chunk-of-one repair carries the repaired explanation.
    repaired = frame[frame["explanation"].astype(str).str.startswith("repaired")]
    assert len(repaired) == len(frame)  # round 2 rows only replace broken ones
    # State files persisted for both rounds.
    assert (tmp_path / "batches" / "claude-sonnet-5.round0.json").exists()
    assert (tmp_path / "batches" / "claude-sonnet-5.round1.json").exists()
    ledger_path = tmp_path / "batches" / "claude-sonnet-5.spend.jsonl"
    ledger = read_spend_ledger(ledger_path)
    assert len(ledger) == len(adapter.submissions[0]) + len(adapter.submissions[1])
    assert len({record["call_key"] for record in ledger}) == len(ledger)
    assert {record["phase"] for record in ledger} == {"initial", "repair"}
    assert any(record["status"] == "parse_error" for record in ledger)
    repaired_calls = [record for record in ledger if record["phase"] == "repair"]
    assert repaired_calls
    assert all(record["status"] == "ok" for record in repaired_calls)
    assert all(record["total_cost_usd"] is not None for record in ledger)
    assert all("provider_reported_cost_usd" in record for record in ledger)
    assert all("provider_resolved_model" in record for record in ledger)
    assert frame["total_cost_usd"].sum() == pytest.approx(
        sum(record["total_cost_usd"] for record in ledger)
    )
    assert (tmp_path / "by_model" / "claude-sonnet-5.csv").exists()
    model_output = tmp_path / "by_model" / "claude-sonnet-5.csv"
    written = pd.read_csv(model_output)
    assert read_spend_ledger(spend_ledger_path(model_output)) == ledger
    assert set(written.columns) >= {
        "call_id",
        "model",
        "scenario_id",
        "variable",
        "prediction",
        "explanation",
        "raw_response",
        "error",
        "elapsed_seconds",
        "request_started_at",
        "request_completed_at",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "reasoning_tokens",
        "cached_prompt_tokens",
        "cache_write_prompt_tokens",
        "provider_reported_cost_usd",
        "reconstructed_cost_usd",
        "total_cost_usd",
        "cost_is_estimated",
        "estimated_cost_usd",
        "provider_response_id",
        "provider_system_fingerprint",
        "provider_resolved_model",
    }


class ResumeAdapter(FakeAdapter):
    """Round 0 already submitted by a prior process; results retrievable."""

    def __init__(self, prior_requests):
        super().__init__()
        self.submissions = [prior_requests]

    def submit(self, requests, model_id):
        self.submissions.append(requests)
        return f"batch_{len(self.submissions)}"


def test_run_batch_eval_resumes_existing_round_without_resubmitting(tmp_path, scenario):
    programs = ["eitc"]
    units = build_units([scenario], programs, "claude-sonnet-5")
    prior_requests = [(unit.custom_id, {"variables": unit.variables}) for unit in units]
    state = BatchRunState(
        model="claude-sonnet-5",
        model_id="claude-sonnet-5",
        round_index=0,
        batch_id="batch_1",
        provider="fake",
        submitted_at=0.0,
        units={
            unit.custom_id: {
                "scenario_id": unit.scenario_id,
                "variables": unit.variables,
                "chunk_index": unit.chunk_index,
                "repair": False,
            }
            for unit in units
        },
    )
    state.save(tmp_path)

    adapter = ResumeAdapter(prior_requests)
    frame = run_batch_eval(
        scenarios=[scenario],
        programs=programs,
        model_name="claude-sonnet-5",
        model_id="claude-sonnet-5",
        run_dir=tmp_path,
        adapter=adapter,
        poll_seconds=0,
        sleep=lambda _s: None,
        log=lambda *_a, **_k: None,
    )
    # The pre-existing round was polled and collected, not resubmitted:
    # submissions grew only if a repair round was needed (it wasn't).
    assert len(adapter.submissions) == 1
    assert frame["prediction"].notna().all()

    ledger_path = tmp_path / "batches" / "claude-sonnet-5.spend.jsonl"
    first_ledger = read_spend_ledger(ledger_path)
    assert len(first_ledger) == len(prior_requests)

    # Re-polling the same completed provider batch upserts by batch/custom id
    # instead of charging the same physical calls twice.
    second_adapter = ResumeAdapter(prior_requests)
    run_batch_eval(
        scenarios=[scenario],
        programs=programs,
        model_name="claude-sonnet-5",
        model_id="claude-sonnet-5",
        run_dir=tmp_path,
        adapter=second_adapter,
        poll_seconds=0,
        sleep=lambda _s: None,
        log=lambda *_a, **_k: None,
    )
    second_ledger = read_spend_ledger(ledger_path)
    assert len(second_ledger) == len(first_ledger)
    assert {record["call_key"] for record in second_ledger} == {
        record["call_key"] for record in first_ledger
    }


def test_batch_resume_rejects_changed_model_id(tmp_path, scenario):
    units = build_units([scenario], ["eitc"], "claude-sonnet-5")
    prior_requests = [(unit.custom_id, {"variables": unit.variables}) for unit in units]
    state = BatchRunState(
        model="claude-sonnet-5",
        model_id="different-provider/model",
        round_index=0,
        batch_id="batch_1",
        provider="fake",
        submitted_at=0.0,
        units={
            unit.custom_id: {
                "scenario_id": unit.scenario_id,
                "variables": unit.variables,
                "chunk_index": unit.chunk_index,
                "repair": False,
            }
            for unit in units
        },
    )
    state.save(tmp_path)

    with pytest.raises(ValueError, match="model_id"):
        run_batch_eval(
            scenarios=[scenario],
            programs=["eitc"],
            model_name="claude-sonnet-5",
            model_id="claude-sonnet-5",
            run_dir=tmp_path,
            adapter=ResumeAdapter(prior_requests),
            poll_seconds=0,
            sleep=lambda _s: None,
            log=lambda *_a, **_k: None,
        )


def test_batch_spend_ledger_records_provider_errors_and_missing_results(
    tmp_path, scenario, monkeypatch
):
    class ErrorAndMissingAdapter(FakeAdapter):
        def results(self, batch_id):
            custom_id, _body = self.submissions[0][0]
            yield NormalizedResult(custom_id=custom_id, error="batch_errored: denied")

    monkeypatch.setattr("policybench.batch_eval.MAX_REPAIR_ROUNDS", 0)
    adapter = ErrorAndMissingAdapter()
    run_batch_eval(
        scenarios=[scenario],
        programs=["eitc", "snap"],
        model_name="claude-sonnet-5",
        model_id="claude-sonnet-5",
        run_dir=tmp_path,
        adapter=adapter,
        poll_seconds=0,
        sleep=lambda _s: None,
        log=lambda *_a, **_k: None,
    )

    ledger = read_spend_ledger(tmp_path / "batches" / "claude-sonnet-5.spend.jsonl")
    assert len(ledger) == 2
    assert {record["status"] for record in ledger} == {
        "provider_error",
        "missing",
    }
    for record in ledger:
        assert record["prompt_tokens"] is None
        assert record["completion_tokens"] is None
        assert record["total_cost_usd"] is None
        assert record["provider_response_id"] is None
        assert record["provider_resolved_model"] is None


def test_terminal_batch_failure_records_submitted_calls(tmp_path, scenario):
    class FailedBatchAdapter(FakeAdapter):
        def status(self, batch_id):
            return "failed"

    adapter = FailedBatchAdapter()
    with pytest.raises(RuntimeError, match="ended as failed"):
        run_batch_eval(
            scenarios=[scenario],
            programs=["eitc"],
            model_name="claude-sonnet-5",
            model_id="claude-sonnet-5",
            run_dir=tmp_path,
            adapter=adapter,
            poll_seconds=0,
            sleep=lambda _s: None,
            log=lambda *_a, **_k: None,
        )

    ledger = read_spend_ledger(tmp_path / "batches" / "claude-sonnet-5.spend.jsonl")
    assert len(ledger) == len(adapter.submissions[0])
    assert {record["status"] for record in ledger} == {"provider_error"}
    assert all(record["total_cost_usd"] is None for record in ledger)


def test_batch_result_iteration_failure_preserves_all_submitted_calls(
    tmp_path, scenario
):
    class InterruptedResultsAdapter(FakeAdapter):
        def results(self, batch_id):
            results = super().results(batch_id)
            yield next(results)
            raise RuntimeError("result stream interrupted")

    adapter = InterruptedResultsAdapter()
    with pytest.raises(RuntimeError, match="result stream interrupted"):
        run_batch_eval(
            scenarios=[scenario],
            programs=["eitc", "snap"],
            model_name="claude-sonnet-5",
            model_id="claude-sonnet-5",
            run_dir=tmp_path,
            adapter=adapter,
            poll_seconds=0,
            sleep=lambda _s: None,
            log=lambda *_a, **_k: None,
        )

    ledger = read_spend_ledger(tmp_path / "batches" / "claude-sonnet-5.spend.jsonl")
    assert len(ledger) == len(adapter.submissions[0])
    assert ledger[0]["status"] == "ok"
    assert {record["status"] for record in ledger[1:]} == {"pending"}
