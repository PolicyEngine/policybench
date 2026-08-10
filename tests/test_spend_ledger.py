"""Tests for the durable provider-call spend ledger."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from policybench.eval_no_tools import run_no_tools_eval, run_single_no_tools
from policybench.scenarios import Person, Scenario
from policybench.spend_ledger import (
    read_spend_ledger,
    spend_ledger_path,
    upsert_spend_ledger,
)


@pytest.fixture
def scenario():
    return Scenario(
        id="mini",
        state="CA",
        filing_status="single",
        adults=[Person(name="adult1", age=35, employment_income=50_000.0)],
        year=2026,
    )


def _record(call_key, phase, status, cost):
    return {
        "call_key": call_key,
        "mode": "sync",
        "phase": phase,
        "status": status,
        "total_cost_usd": cost,
    }


def test_spend_ledger_path_is_a_sidecar():
    assert spend_ledger_path("run/scenario.csv").name == "scenario.csv.spend.jsonl"


def test_upsert_spend_ledger_deduplicates_stable_call_keys(tmp_path):
    path = tmp_path / "calls.spend.jsonl"
    upsert_spend_ledger(
        path,
        [
            {
                "call_key": "batch:one:u000",
                "status": "parse_error",
                "total_cost_usd": 0.1,
            },
            {
                "call_key": "batch:two:r000",
                "status": "ok",
                "total_cost_usd": 0.2,
            },
        ],
    )
    upsert_spend_ledger(
        path,
        [
            {
                "call_key": "batch:one:u000",
                "status": "parse_error",
                "total_cost_usd": 0.1,
            }
        ],
    )

    records = read_spend_ledger(path)
    assert [record["call_key"] for record in records] == [
        "batch:one:u000",
        "batch:two:r000",
    ]
    assert sum(record["total_cost_usd"] for record in records) == pytest.approx(0.3)


def test_spend_ledger_missing_repoll_cannot_erase_priced_result(tmp_path):
    path = tmp_path / "batch.spend.jsonl"
    upsert_spend_ledger(
        path,
        [
            {
                "call_key": "batch:one:u000",
                "status": "ok",
                "total_cost_usd": 0.4,
                "prompt_tokens": 100,
            }
        ],
    )
    upsert_spend_ledger(
        path,
        [
            {
                "call_key": "batch:one:u000",
                "status": "missing",
                "total_cost_usd": None,
                "prompt_tokens": None,
            }
        ],
    )

    assert read_spend_ledger(path) == [
        {
            "call_key": "batch:one:u000",
            "status": "ok",
            "total_cost_usd": 0.4,
            "prompt_tokens": 100,
        }
    ]


def test_spend_ledger_preserves_nullable_failed_call_fields(tmp_path):
    path = tmp_path / "failed.spend.jsonl"
    upsert_spend_ledger(
        path,
        [
            {
                "call_key": "sync:failed",
                "status": "provider_error",
                "elapsed_seconds": None,
                "total_cost_usd": None,
            }
        ],
    )

    raw = json.loads(path.read_text().strip())
    assert raw["elapsed_seconds"] is None
    assert raw["total_cost_usd"] is None
    assert read_spend_ledger(path) == [raw]


@patch("policybench.eval_no_tools.responses")
def test_cached_response_is_a_zero_spend_ledger_record(mock_responses, scenario):
    mock_responses.return_value = SimpleNamespace(
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call",
                name="submit_outputs",
                arguments='{"outputs":{"income_tax":{"value":123}}}',
            )
        ],
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=2,
            total_tokens=12,
            cost=0.01,
        ),
        _hidden_params={"cache_hit": True},
    )

    result = run_single_no_tools(
        scenario,
        "income_tax",
        "gpt-5.4",
        include_explanations=False,
    )

    assert result["total_cost_usd"] == pytest.approx(0.000055)
    assert result["cost_is_estimated"] is True
    assert len(result["spend_ledger"]) == 1
    assert result["spend_ledger"][0]["cache_hit"] is True
    assert result["spend_ledger"][0]["cached_response_cost_usd"] == pytest.approx(
        0.000055
    )
    assert result["spend_ledger"][0]["total_cost_usd"] == 0.0


@patch("policybench.eval_no_tools.responses")
def test_spend_persistence_failure_does_not_retry_paid_call(mock_responses, scenario):
    mock_responses.return_value = SimpleNamespace(
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call",
                name="submit_outputs",
                arguments='{"outputs":{"income_tax":{"value":123}}}',
            )
        ],
        usage=SimpleNamespace(input_tokens=10, output_tokens=2, total_tokens=12),
    )
    persist = Mock(side_effect=OSError("ledger unavailable"))

    with pytest.raises(OSError) as exc_info:
        run_single_no_tools(
            scenario,
            "income_tax",
            "gpt-5.4",
            include_explanations=False,
            _spend_callback=persist,
        )

    assert mock_responses.call_count == 1
    assert persist.call_count == 1
    assert exc_info.value.spend_ledger[0]["status"] == "ok"


@patch("policybench.eval_no_tools._request_predictions_once")
def test_run_single_ledger_keeps_initial_and_repair_calls(mock_request, scenario):
    mock_request.side_effect = [
        {
            "predictions": {"income_tax": None},
            "explanations": {},
            "raw_response": "broken",
            "spend_ledger": [_record("sync:initial", "initial", "parse_error", 0.1)],
        },
        {
            "predictions": {"income_tax": 123.0},
            "explanations": {},
            "raw_response": "fixed",
            "spend_ledger": [_record("sync:repair", "repair", "ok", 0.2)],
        },
    ]

    result = run_single_no_tools(
        scenario,
        "income_tax",
        "gpt-5.4",
        include_explanations=False,
    )

    assert [record["phase"] for record in result["spend_ledger"]] == [
        "initial",
        "repair",
    ]
    assert sum(
        record["total_cost_usd"] for record in result["spend_ledger"]
    ) == pytest.approx(0.3)


@patch("policybench.eval_no_tools.run_single_no_tools")
def test_eval_persists_successful_and_repair_call_ledger(
    mock_run_single, scenario, tmp_path
):
    output_path = tmp_path / "scenario.csv"
    mock_run_single.return_value = {
        "predictions": {"income_tax": 123.0},
        "explanations": {},
        "raw_response": "fixed",
        "error": None,
        "spend_ledger": [
            _record("sync:initial", "initial", "parse_error", 0.1),
            _record("sync:repair", "repair", "ok", 0.2),
        ],
    }

    run_no_tools_eval(
        [scenario],
        models={"test-model": "gpt-5.4"},
        programs=["income_tax"],
        output_path=str(output_path),
        include_explanations=False,
    )

    records = read_spend_ledger(spend_ledger_path(output_path))
    assert [record["phase"] for record in records] == ["initial", "repair"]
    assert {record["model"] for record in records} == {"test-model"}
    assert {record["scenario_id"] for record in records} == {"mini"}


@patch("policybench.eval_no_tools.run_single_no_tools")
def test_eval_persists_failed_provider_call_ledger(mock_run_single, scenario, tmp_path):
    output_path = tmp_path / "scenario.csv"
    error = RuntimeError("provider rejected request")
    error.spend_ledger = [_record("sync:failed", "initial", "provider_error", None)]
    mock_run_single.side_effect = error

    run_no_tools_eval(
        [scenario],
        models={"test-model": "gpt-5.4"},
        programs=["income_tax"],
        output_path=str(output_path),
        include_explanations=False,
    )

    records = read_spend_ledger(spend_ledger_path(output_path))
    assert len(records) == 1
    assert records[0]["status"] == "provider_error"
    assert records[0]["total_cost_usd"] is None


@patch("policybench.eval_no_tools.run_single_no_tools")
def test_eval_flushes_each_call_before_scenario_completion(
    mock_run_single, scenario, tmp_path
):
    output_path = tmp_path / "scenario.csv"

    def interrupt_after_call(*_args, _spend_callback=None, **_kwargs):
        assert _spend_callback is not None
        _spend_callback([_record("sync:initial", "initial", "ok", 0.1)])
        raise KeyboardInterrupt

    mock_run_single.side_effect = interrupt_after_call

    with pytest.raises(KeyboardInterrupt):
        run_no_tools_eval(
            [scenario],
            models={"test-model": "gpt-5.4"},
            programs=["income_tax"],
            output_path=str(output_path),
            include_explanations=False,
        )

    records = read_spend_ledger(spend_ledger_path(output_path))
    assert [record["call_key"] for record in records] == ["sync:initial"]


@patch("policybench.eval_no_tools.run_single_no_tools")
def test_eval_refuses_orphan_ledger_without_resume_metadata(
    mock_run_single, scenario, tmp_path
):
    output_path = tmp_path / "scenario.csv"
    upsert_spend_ledger(
        spend_ledger_path(output_path),
        [_record("sync:stale", "initial", "ok", 1.0)],
    )

    with pytest.raises(ValueError, match="resume metadata"):
        run_no_tools_eval(
            [scenario],
            models={"test-model": "gpt-5.4"},
            programs=["income_tax"],
            output_path=str(output_path),
            include_explanations=False,
        )

    mock_run_single.assert_not_called()
