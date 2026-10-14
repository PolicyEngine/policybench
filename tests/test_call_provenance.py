"""Per-row call provenance: live calls, cache replays and live time.

Every row writer fills ``live_calls``, ``cache_hit_calls`` and
``live_elapsed_seconds`` (``eval_no_tools.NO_TOOLS_CALL_PROVENANCE_COLUMNS``).
The invariants these tests execute, for every row a writer emits:

1. ``live_calls`` and ``cache_hit_calls`` are non-negative integers that count
   every response behind the row's time, live or replayed.
2. ``0 <= live_elapsed_seconds <= elapsed_seconds``, and the two are empty
   together.
3. A row whose responses were all cache hits has zero live calls and exactly
   zero live time.
4. A row with no cache hits has live time exactly equal to its elapsed time.
5. The counts and live time agree with the spend ledger's answered records,
   an independent record of the same calls (differential).
6. Batch rows never record a cache hit and carry no live time.
7. The columns round-trip through the run store and CSV byte for byte; a CSV
   written before they existed round-trips without them and classifies as
   unknown.
8. Adding the columns changes no published number.
"""

import json
import math
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import litellm
import pandas as pd
import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

import policybench.eval_no_tools as eval_no_tools
import policybench.row_repair as row_repair
from policybench.analysis import model_cost_latency, usage_summary_by_model
from policybench.batch_eval import BatchUnit, NormalizedResult, rows_from_unit
from policybench.call_provenance import (
    HOUSEHOLD_CALL_STATUSES,
    household_call_provenance,
)
from policybench.config import COUNTRY_PROGRAMS
from policybench.eval_no_tools import (
    NO_TOOLS_CALL_PROVENANCE_COLUMNS,
    NO_TOOLS_RESULT_COLUMNS,
    _aggregate_call_provenance,
    _aggregate_request_results,
    _build_resume_metadata,
    _request_call_provenance,
    _write_resume_metadata,
    run_no_tools_eval,
    run_no_tools_single_output_eval,
)
from policybench.retry_eval import merge_retry_predictions
from policybench.row_repair import (
    _append_rows,
    merge_row_repair_predictions,
    repair_prediction_row,
)
from policybench.runstore import (
    _RESPONSE_COLUMNS,
    RunStore,
    export_predictions_csv,
    import_run_csv,
)
from policybench.scenarios import Person, Scenario
from policybench.spend_ledger import read_spend_ledger, spend_ledger_path

PROVENANCE = list(NO_TOOLS_CALL_PROVENANCE_COLUMNS)
US_VARIABLES = COUNTRY_PROGRAMS["us"]
FROZEN_US_PREDICTIONS = (
    Path(__file__).resolve().parents[1]
    / "paper/snapshot/20260501/runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace/predictions.csv.gz"
)


def _scenario(scenario_id: str, income: float = 50_000.0) -> Scenario:
    return Scenario(
        id=scenario_id,
        state="CA",
        filing_status="single",
        adults=[Person(name="adult1", age=35, employment_income=income)],
        year=2026,
    )


def test_the_provenance_columns_close_the_row_schema_and_are_response_level():
    assert NO_TOOLS_RESULT_COLUMNS[-3:] == NO_TOOLS_CALL_PROVENANCE_COLUMNS
    assert set(NO_TOOLS_CALL_PROVENANCE_COLUMNS) <= set(_RESPONSE_COLUMNS)


def test_one_request_is_a_live_call_or_a_replay():
    assert _request_call_provenance(12.5, False) == {
        "live_calls": 1,
        "cache_hit_calls": 0,
        "live_elapsed_seconds": 12.5,
    }
    assert _request_call_provenance(0.02, True) == {
        "live_calls": 0,
        "cache_hit_calls": 1,
        "live_elapsed_seconds": 0.0,
    }


def test_no_responses_means_zero_calls_and_no_live_time():
    assert _aggregate_call_provenance([]) == {
        "live_calls": 0,
        "cache_hit_calls": 0,
        "live_elapsed_seconds": None,
    }
    aggregated = _aggregate_request_results([])
    assert aggregated["elapsed_seconds"] is None
    assert aggregated["live_elapsed_seconds"] is None


def test_a_result_without_provenance_makes_the_aggregate_unknown():
    results = [
        {"elapsed_seconds": 2.0, **_request_call_provenance(2.0, False)},
        {"elapsed_seconds": 1.0},
    ]

    aggregated = _aggregate_request_results(results)

    assert aggregated["elapsed_seconds"] == 3.0
    assert {column: aggregated[column] for column in PROVENANCE} == dict.fromkeys(
        PROVENANCE
    )


@given(
    st.lists(
        st.tuples(
            st.floats(min_value=0, max_value=1e5, allow_nan=False),
            st.booleans(),
        ),
        max_size=12,
    )
)
def test_aggregated_provenance_counts_every_response_and_bounds_live_time(pairs):
    results = [
        {"elapsed_seconds": elapsed, **_request_call_provenance(elapsed, hit)}
        for elapsed, hit in pairs
    ]

    aggregated = _aggregate_request_results(results)

    hits = sum(hit for _, hit in pairs)
    assert aggregated["cache_hit_calls"] == hits
    assert aggregated["live_calls"] == len(pairs) - hits
    if not pairs:
        assert aggregated["live_elapsed_seconds"] is None
        return
    live = aggregated["live_elapsed_seconds"]
    assert 0 <= live <= aggregated["elapsed_seconds"]
    if hits == len(pairs):
        assert live == 0
    if hits == 0:
        assert live == aggregated["elapsed_seconds"]
    assert live == pytest.approx(sum(e for e, hit in pairs if not hit))


# -- end to end through the real request path ---------------------------------

RESPONSE_MODES = (
    # Weighted toward complete answers so most households finish; the other
    # modes drive repair rounds, budget escalation and explanation repairs.
    "answer",
    "answer",
    "answer",
    "values_only",
    "empty",
    "truncated",
)


def _answer_arguments(with_explanations: bool) -> str:
    outputs = {}
    for index, variable in enumerate(US_VARIABLES, start=1):
        entry = {"value": float(index)}
        if with_explanations:
            entry["explanation"] = f"Explanation for {variable}. value = {index}"
        outputs[variable] = entry
    return json.dumps({"outputs": outputs})


def _mock_response(mode: str, cache_hit: bool):
    tool_calls = []
    if mode in ("answer", "values_only"):
        tool_calls = [
            SimpleNamespace(
                function=SimpleNamespace(
                    name="submit_outputs",
                    arguments=_answer_arguments(mode == "answer"),
                )
            )
        ]
    message = SimpleNamespace(content=None, tool_calls=tool_calls, function_call=None)
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=message,
                finish_reason="length" if mode == "truncated" else "stop",
            )
        ],
        usage=litellm.Usage(prompt_tokens=12, completion_tokens=3, total_tokens=15),
        # litellm's caching handler sets this on every disk-cache replay
        # (litellm/caching/caching_handler.py); a provider response lacks it.
        _hidden_params={"cache_hit": cache_hit},
    )


def _assert_row_invariants(rows: pd.DataFrame) -> None:
    for column in ("live_calls", "cache_hit_calls"):
        assert rows[column].notna().all()
        assert (rows[column] >= 0).all()
        assert (rows[column] == rows[column].round()).all()
    live = rows["live_elapsed_seconds"]
    elapsed = rows["elapsed_seconds"]
    assert (live.isna() == elapsed.isna()).all()
    timed = elapsed.notna()
    assert (live[timed] >= 0).all()
    assert (live[timed] <= elapsed[timed]).all()
    all_hits = (rows["live_calls"] == 0) & (rows["cache_hit_calls"] > 0)
    assert (live[all_hits & timed] == 0).all()
    no_hits = rows["cache_hit_calls"] == 0
    assert (live[no_hits & timed] == elapsed[no_hits & timed]).all()


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(
    data=st.data(),
    writer=st.sampled_from(["household", "single_output"]),
    model_id=st.sampled_from(["claude-sonnet-4-6", "claude-opus-4-6"]),
    output_count=st.integers(min_value=1, max_value=3),
    household_count=st.integers(min_value=1, max_value=2),
)
def test_rows_record_each_responses_provenance_and_agree_with_the_ledger(
    data, writer, model_id, output_count, household_count
):
    """Drive run_no_tools_eval / run_no_tools_single_output_eval through the
    real request path. Each mocked response's cache flag, duration and shape
    (a full answer, values only, nothing, or a length cut) is drawn per call,
    so households mix replays with live calls across chunks (Claude Sonnet
    4.6 answers one output per request), repair rounds, budget escalations
    and explanation repairs."""
    programs = US_VARIABLES[:output_count]
    scenarios = [
        _scenario(f"scenario_{index:03d}", 40_000.0 + index)
        for index in range(household_count)
    ]
    clock = [1_000.0]
    current = {"group": None}
    calls: list[tuple[tuple, bool, float]] = []
    real_run_single = eval_no_tools.run_single_no_tools

    def tracking_run_single(scenario, variable, *args, **kwargs):
        key = (scenario.id,) if writer == "household" else (scenario.id, variable)
        current["group"] = key
        return real_run_single(scenario, variable, *args, **kwargs)

    def fake_completion(**_kwargs):
        mode = data.draw(st.sampled_from(RESPONSE_MODES), label="mode")
        cache_hit = data.draw(st.booleans(), label="cache_hit")
        seconds = data.draw(
            st.floats(min_value=0, max_value=900, allow_nan=False),
            label="seconds",
        )
        clock[0] += seconds
        calls.append((current["group"], cache_hit, seconds))
        return _mock_response(mode, cache_hit)

    fake_time = SimpleNamespace(
        perf_counter=lambda: clock[0],
        time=time.time,
        sleep=lambda _seconds: None,
    )
    runner = (
        run_no_tools_eval
        if writer == "household"
        else (run_no_tools_single_output_eval)
    )
    with (
        tempfile.TemporaryDirectory() as tmp,
        patch.object(eval_no_tools, "completion", side_effect=fake_completion),
        patch.object(eval_no_tools, "time", fake_time),
        patch.object(eval_no_tools, "run_single_no_tools", tracking_run_single),
    ):
        output_path = Path(tmp) / "run" / "predictions.csv"
        output_path.parent.mkdir()
        frame = runner(
            scenarios,
            models={"Model": model_id},
            programs=programs,
            output_path=str(output_path),
        )
        ledger = read_spend_ledger(spend_ledger_path(output_path))

        assert list(frame.columns) == list(NO_TOOLS_RESULT_COLUMNS)
        _assert_row_invariants(frame)

        group_columns = (
            ["scenario_id"]
            if writer == "household"
            else [
                "scenario_id",
                "variable",
            ]
        )
        for key, rows in frame.groupby(group_columns):
            group_calls = [call for call in calls if call[0] == tuple(key)]
            hits = sum(hit for _, hit, _ in group_calls)
            # One request group per household (or per output): every row
            # repeats its counts.
            assert rows["live_calls"].nunique() == 1
            assert rows["cache_hit_calls"].nunique() == 1
            assert int(rows["cache_hit_calls"].iloc[0]) == hits
            assert int(rows["live_calls"].iloc[0]) == len(group_calls) - hits
            live_seconds = sum(seconds for _, hit, seconds in group_calls if not hit)
            assert rows["live_elapsed_seconds"].sum() == pytest.approx(
                live_seconds, rel=1e-9, abs=1e-6
            )

            # Differential: the spend ledger records the same calls
            # independently, one record per physical request.
            records = [
                record
                for record in ledger
                if record["scenario_id"] == key[0]
                and (writer == "household" or record["variables"] == [key[1]])
                and record["status"] in ("ok", "parse_error")
            ]
            assert len(records) == len(group_calls)
            assert sum(record["cache_hit"] for record in records) == hits
            assert sum(
                record["elapsed_seconds"]
                for record in records
                if not record["cache_hit"]
            ) == pytest.approx(rows["live_elapsed_seconds"].sum(), rel=1e-9, abs=1e-6)
            assert sum(record["elapsed_seconds"] for record in records) == (
                pytest.approx(rows["elapsed_seconds"].sum(), rel=1e-9, abs=1e-6)
            )

        # The analysis classifier reads the same facts back from the rows.
        status = household_call_provenance(frame)["status"]
        for scenario in scenarios:
            household_calls = [call for call in calls if call[0][0] == scenario.id]
            hits = sum(hit for _, hit, _ in household_calls)
            expected = (
                "full_replay"
                if hits == len(household_calls)
                else "live"
                if hits == 0
                else "partial_replay"
            )
            assert status[("Model", scenario.id)] == expected
            event(f"household {expected}")
            event(f"household calls {min(len(household_calls), 6)}+")

        # The CSV carries the same values, and the run store returns it byte
        # for byte with the counts queryable from usage_json.
        written = pd.read_csv(output_path, float_precision="round_trip")
        pd.testing.assert_frame_equal(
            written[PROVENANCE].astype(float),
            frame[PROVENANCE].astype(float),
            check_exact=True,
        )
        db_path = Path(tmp) / "run.db"
        run_id = import_run_csv(db_path, output_path)
        exported = export_predictions_csv(db_path, run_id, Path(tmp) / "out.csv")
        assert exported.read_bytes() == output_path.read_bytes()
        with RunStore(db_path) as store:
            stored = store.connection.execute(
                "SELECT scenario_id, usage_json FROM responses WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        for row in stored:
            usage = json.loads(row["usage_json"])
            expected_rows = frame[frame["scenario_id"] == row["scenario_id"]]
            assert usage["cache_hit_calls"] in set(expected_rows["cache_hit_calls"])
            assert usage["live_calls"] in set(expected_rows["live_calls"])


def test_a_household_that_raised_records_no_responses(monkeypatch, tmp_path):
    def raising_run_single(*_args, **_kwargs):
        raise ValueError("malformed provider payload")

    monkeypatch.setattr(eval_no_tools, "run_single_no_tools", raising_run_single)

    frame = run_no_tools_eval(
        [_scenario("scenario_000")],
        models={"Model": "claude-opus-4-6"},
        programs=US_VARIABLES[:2],
        output_path=str(tmp_path / "predictions.csv"),
    )

    assert set(frame["live_calls"]) == {0}
    assert set(frame["cache_hit_calls"]) == {0}
    assert frame["live_elapsed_seconds"].isna().all()
    assert frame["elapsed_seconds"].isna().all()
    assert set(household_call_provenance(frame)["status"]) == {"no_response"}


def test_resumed_output_keeps_older_rows_empty(monkeypatch, tmp_path):
    """Rows written before the columns existed stay empty when a run resumes
    and later households fill them."""
    scenarios = [_scenario("scenario_000"), _scenario("scenario_001", 60_000.0)]
    models = {"Model": "claude-opus-4-6"}
    programs = US_VARIABLES[:2]
    output_path = tmp_path / "predictions.csv"
    _write_resume_metadata(
        str(output_path),
        _build_resume_metadata(
            task="eval_no_tools_batch",
            scenarios=scenarios,
            models=models,
            programs=programs,
            run_id=None,
            include_explanations=True,
        ),
    )
    older_columns = [c for c in NO_TOOLS_RESULT_COLUMNS if c not in PROVENANCE]
    older = pd.DataFrame(
        [
            {
                **dict.fromkeys(older_columns),
                "call_id": "Model:scenario_000",
                "model": "Model",
                "scenario_id": "scenario_000",
                "variable": variable,
                "prediction": 1.0,
                "explanation": "Explanation. value = 1",
                "raw_response": "{}",
                "elapsed_seconds": 0.01,
            }
            for variable in programs
        ],
        columns=older_columns,
    )
    older.to_csv(output_path, index=False)

    def live_run_single(_scenario, variables, *_args, **_kwargs):
        return {
            "predictions": dict.fromkeys(variables, 2.0),
            "explanations": dict.fromkeys(variables, "Explanation. value = 2"),
            "raw_response": "{}",
            "error": None,
            "elapsed_seconds": 8.0,
            **_request_call_provenance(8.0, False),
        }

    monkeypatch.setattr(eval_no_tools, "run_single_no_tools", live_run_single)
    run_no_tools_eval(
        scenarios,
        models=models,
        programs=programs,
        output_path=str(output_path),
    )

    written = pd.read_csv(output_path)
    assert list(written.columns) == list(NO_TOOLS_RESULT_COLUMNS)
    resumed = written[written["scenario_id"] == "scenario_000"]
    fresh = written[written["scenario_id"] == "scenario_001"]
    assert resumed[PROVENANCE].isna().all().all()
    assert set(fresh["live_calls"]) == {1}
    assert set(fresh["cache_hit_calls"]) == {0}
    assert fresh["live_elapsed_seconds"].tolist() == [4.0, 4.0]
    status = household_call_provenance(written)["status"]
    assert status[("Model", "scenario_000")] == "unknown"
    assert status[("Model", "scenario_001")] == "live"


# -- batch, row repair and retry writers --------------------------------------


@given(
    output_count=st.integers(min_value=1, max_value=6),
    answered=st.booleans(),
    prompt_tokens=st.integers(min_value=0, max_value=100_000),
)
def test_batch_rows_are_live_untimed_and_never_cache_hits(
    output_count, answered, prompt_tokens
):
    unit = BatchUnit(
        scenario_id="scenario_000",
        variables=US_VARIABLES[:output_count],
        chunk_index=0,
    )
    result = (
        NormalizedResult(
            custom_id=unit.custom_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=10,
        )
        if answered
        else None
    )

    rows = rows_from_unit(
        model_name="Model",
        model_id="claude-sonnet-4-6",
        unit=unit,
        predictions={},
        explanations={},
        raw_response=None,
        error=None if answered else "batch_missing: no result entry returned",
        result=result,
    )

    assert len(rows) == output_count
    for row in rows:
        assert row["cache_hit_calls"] == 0
        assert row["live_calls"] == int(answered)
        assert row["live_elapsed_seconds"] is None
        assert row["elapsed_seconds"] is None
    frame = pd.DataFrame(rows)
    expected = "live" if answered else "no_response"
    assert set(household_call_provenance(frame)["status"]) == {expected}


def test_row_repair_carries_the_repair_requests_provenance(monkeypatch):
    calls = iter(
        [
            {
                "predictions": {"payroll_tax": None},
                "explanations": {"payroll_tax": None},
                "raw_response": None,
                "error": "Missing predictions after repair: payroll_tax",
                "elapsed_seconds": 0.02,
                **_request_call_provenance(0.02, True),
            },
            ValueError("provider returned malformed JSON"),
            {
                "predictions": {"payroll_tax": 7.0},
                "explanations": {"payroll_tax": "Payroll. value = 7"},
                "raw_response": "{}",
                "error": None,
                "elapsed_seconds": 5.5,
                **_request_call_provenance(5.5, False),
            },
        ]
    )

    def scripted_run_single(*_args, **_kwargs):
        outcome = next(calls)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(row_repair, "run_single_no_tools", scripted_run_single)
    monkeypatch.setitem(row_repair.MODELS, "Model", "claude-opus-4-6")

    final, attempts = repair_prediction_row(
        country="us",
        scenario=_scenario("scenario_000"),
        model="Model",
        variable="payroll_tax",
        attempts_per_row=3,
    )

    assert [
        (row["live_calls"], row["cache_hit_calls"], row["live_elapsed_seconds"])
        for row in attempts
    ] == [(0, 1, 0.0), (0, 0, None), (1, 0, 5.5)]
    assert final["live_elapsed_seconds"] == 5.5


def test_append_rows_widens_an_older_header_and_keeps_its_cells(tmp_path):
    path = tmp_path / "row_repair_attempts.csv"
    path.write_text(
        "model,scenario_id,variable,prediction,explanation\n"
        'm,s1,tax,1.10,"Tax, federal. value = 1.10"\n'
    )

    _append_rows(
        path,
        [
            {
                "variable": "benefit",
                "model": "m",
                "scenario_id": "s2",
                "prediction": 2.0,
                "explanation": "Benefit. value = 2",
                "live_calls": 1,
                "cache_hit_calls": 0,
                "live_elapsed_seconds": 3.5,
            }
        ],
    )
    _append_rows(
        path,
        [{"model": "m", "scenario_id": "s3", "variable": "tax", "prediction": 4.0}],
    )

    lines = path.read_text().splitlines()
    assert lines[0] == (
        "model,scenario_id,variable,prediction,explanation,"
        "live_calls,cache_hit_calls,live_elapsed_seconds"
    )
    assert lines[1] == 'm,s1,tax,1.10,"Tax, federal. value = 1.10",,,'
    frame = pd.read_csv(path)
    assert frame["scenario_id"].tolist() == ["s1", "s2", "s3"]
    assert frame.loc[1, "variable"] == "benefit"
    assert frame.loc[1, "live_elapsed_seconds"] == 3.5
    assert math.isnan(frame.loc[2, "live_calls"])


def test_append_rows_replaces_a_headerless_empty_file(tmp_path):
    path = tmp_path / "row_repair_attempts.csv"
    pd.DataFrame().to_csv(path, index=False)

    _append_rows(path, [{"model": "m", "live_calls": 1}])

    assert pd.read_csv(path).to_dict("records") == [{"model": "m", "live_calls": 1}]


def test_row_repair_merge_fills_only_the_repaired_row(tmp_path):
    source_path = tmp_path / "source.csv"
    repair_path = tmp_path / "repair.csv"
    pd.DataFrame(
        {
            "model": ["model_a", "model_a"],
            "scenario_id": ["s1", "s1"],
            "variable": ["tax", "benefit"],
            "prediction": [1.0, None],
            "explanation": ["Tax. value = 1", None],
            "raw_response": [None, None],
            "error": [None, "Missing prediction after repair: benefit"],
        }
    ).to_csv(source_path, index=False)
    pd.DataFrame(
        {
            "country": ["us"],
            "attempt": [1],
            "model": ["model_a"],
            "scenario_id": ["s1"],
            "variable": ["benefit"],
            "prediction": [22.0],
            "explanation": ["Repair benefit. value = 22"],
            "raw_response": ["raw"],
            "error": [None],
            "elapsed_seconds": [6.0],
            "live_calls": [1],
            "cache_hit_calls": [0],
            "live_elapsed_seconds": [6.0],
        }
    ).to_csv(repair_path, index=False)

    outputs = merge_row_repair_predictions(
        source_predictions=source_path,
        repair_predictions=repair_path,
        output_dir=tmp_path / "merged",
    )

    merged = pd.read_csv(outputs["merged_predictions"]).set_index("variable")
    assert merged.loc["benefit", "live_calls"] == 1
    assert merged.loc["benefit", "live_elapsed_seconds"] == 6.0
    assert merged.loc["tax", PROVENANCE].isna().all()
    assert set(household_call_provenance(merged.reset_index())["status"]) == {"unknown"}


def test_retry_merge_carries_the_retry_rows_provenance(tmp_path):
    source_path = tmp_path / "source.csv"
    retry_path = tmp_path / "retry.csv"
    target_path = tmp_path / "target.csv"
    pd.DataFrame(
        {
            "model": ["model_a", "model_a", "model_b"],
            "scenario_id": ["s1", "s1", "s1"],
            "variable": ["tax", "benefit", "tax"],
            "prediction": [1.0, None, 2.0],
            "explanation": ["Tax. value = 1", "", "Tax. value = 2"],
            "error": [None, "Missing predictions after repair: benefit", None],
        }
    ).to_csv(source_path, index=False)
    pd.DataFrame(
        {
            "model": ["model_a", "model_a"],
            "scenario_id": ["s1", "s1"],
            "variable": ["tax", "benefit"],
            "prediction": [10.0, 20.0],
            "explanation": ["Retry tax. value = 10", "Retry benefit. value = 20"],
            "error": [None, None],
            "elapsed_seconds": [0.01, 0.01],
            "live_calls": [0, 0],
            "cache_hit_calls": [1, 1],
            "live_elapsed_seconds": [0.0, 0.0],
        }
    ).to_csv(retry_path, index=False)
    pd.DataFrame({"model": ["model_a"], "scenario_id": ["s1"]}).to_csv(
        target_path, index=False
    )

    outputs = merge_retry_predictions(
        source_predictions=source_path,
        retry_predictions=retry_path,
        target_units=target_path,
        output_dir=tmp_path / "merged",
    )

    merged = pd.read_csv(outputs["merged_predictions"])
    retried = merged[merged["model"] == "model_a"]
    kept = merged[merged["model"] == "model_b"]
    assert set(retried["cache_hit_calls"]) == {1}
    assert set(retried["live_elapsed_seconds"]) == {0.0}
    assert kept[PROVENANCE].isna().all().all()
    status = household_call_provenance(merged)["status"]
    assert status[("model_a", "s1")] == "full_replay"
    assert status[("model_b", "s1")] == "unknown"


# -- run store ----------------------------------------------------------------

optional_count = st.one_of(st.none(), st.integers(min_value=0, max_value=40))
optional_seconds = st.one_of(
    st.none(), st.floats(min_value=0, max_value=1e4, allow_nan=False)
)


@settings(max_examples=50, deadline=None)
@given(
    st.lists(
        st.tuples(optional_count, optional_count, optional_seconds, optional_seconds),
        min_size=1,
        max_size=6,
    )
)
def test_run_store_round_trips_provenance_byte_for_byte(households):
    frame = pd.DataFrame(
        [
            {
                "call_id": f"Model:scenario_{index:03d}",
                "model": "Model",
                "scenario_id": f"scenario_{index:03d}",
                "variable": variable,
                "prediction": 1.0,
                "explanation": "Explanation. value = 1",
                "raw_response": "{}",
                "error": None,
                "elapsed_seconds": elapsed,
                "live_calls": live_calls,
                "cache_hit_calls": cache_hit_calls,
                "live_elapsed_seconds": live_elapsed,
            }
            for index, (live_calls, cache_hit_calls, live_elapsed, elapsed) in (
                enumerate(households)
            )
            for variable in ("payroll_tax", "self_employment_tax")
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "run" / "predictions.csv"
        csv_path.parent.mkdir()
        frame.to_csv(csv_path, index=False)
        db_path = Path(tmp) / "run.db"

        run_id = import_run_csv(db_path, csv_path)
        exported = export_predictions_csv(db_path, run_id, Path(tmp) / "out.csv")

        assert exported.read_bytes() == csv_path.read_bytes()
        with RunStore(db_path) as store:
            usage = {
                row["scenario_id"]: json.loads(row["usage_json"])
                for row in store.connection.execute(
                    "SELECT scenario_id, usage_json FROM responses"
                ).fetchall()
            }
        for index, (live_calls, cache_hit_calls, _, _) in enumerate(households):
            stored = usage[f"scenario_{index:03d}"]
            assert stored.get("live_calls") == live_calls
            assert stored.get("cache_hit_calls") == cache_hit_calls


def test_run_store_round_trips_a_csv_that_predates_the_columns(tmp_path):
    frame = pd.DataFrame(
        {
            "call_id": ["Model:scenario_000"] * 2,
            "model": ["Model"] * 2,
            "scenario_id": ["scenario_000"] * 2,
            "variable": ["payroll_tax", "self_employment_tax"],
            "prediction": [1.0, 2.0],
            "explanation": ["A. value = 1", "B. value = 2"],
            "elapsed_seconds": [0.015, 0.015],
        }
    )
    csv_path = tmp_path / "run" / "predictions.csv"
    csv_path.parent.mkdir()
    frame.to_csv(csv_path, index=False)

    run_id = import_run_csv(tmp_path / "run.db", csv_path)
    exported = export_predictions_csv(tmp_path / "run.db", run_id, tmp_path / "o.csv")

    assert exported.read_bytes() == csv_path.read_bytes()
    assert not set(PROVENANCE) & set(pd.read_csv(exported).columns)


# -- analysis -------------------------------------------------------------------


def _brute_force_status(rows: list[dict]) -> str:
    if any(row["live_calls"] is None or row["cache_hit_calls"] is None for row in rows):
        return "unknown"
    any_live = any(row["live_calls"] > 0 for row in rows)
    any_hit = any(row["cache_hit_calls"] > 0 for row in rows)
    if any_live and any_hit:
        return "partial_replay"
    if any_hit:
        return "full_replay"
    if any_live:
        return "live"
    return "no_response"


provenance_rows = st.lists(
    st.fixed_dictionaries(
        {
            "variable": st.sampled_from(US_VARIABLES[:4]),
            "elapsed_seconds": optional_seconds,
            "live_calls": optional_count,
            "cache_hit_calls": optional_count,
            "live_elapsed_seconds": optional_seconds,
            "prompt_tokens": st.integers(min_value=0, max_value=5_000),
            "completion_tokens": st.integers(min_value=0, max_value=5_000),
            "total_cost_usd": st.floats(min_value=0, max_value=5, allow_nan=False),
        }
    ),
    min_size=1,
    max_size=5,
)


@settings(max_examples=150, deadline=None)
@given(
    st.dictionaries(
        st.tuples(st.sampled_from(["m1", "m2"]), st.sampled_from(["s1", "s2", "s3"])),
        provenance_rows,
        min_size=1,
    )
)
def test_household_classification_and_published_numbers(households):
    records = [
        {"model": model, "scenario_id": scenario_id, "prediction": 1.0, **row}
        for (model, scenario_id), rows in households.items()
        for row in rows
    ]
    frame = pd.DataFrame(records)

    provenance = household_call_provenance(frame)

    assert set(provenance.index) == set(households)
    assert set(provenance["status"]) <= set(HOUSEHOLD_CALL_STATUSES)
    for key, rows in households.items():
        assert provenance.loc[key, "status"] == _brute_force_status(rows)
        live = provenance.loc[key, "live_elapsed_seconds"]
        values = [row["live_elapsed_seconds"] for row in rows]
        if provenance.loc[key, "status"] == "unknown" or all(
            value is None for value in values
        ):
            assert math.isnan(live)
        else:
            assert live == pytest.approx(sum(v for v in values if v is not None))

    # Adding the provenance columns changes nothing published.
    without = frame.drop(columns=PROVENANCE)
    assert model_cost_latency(frame) == model_cost_latency(without)
    pd.testing.assert_frame_equal(
        usage_summary_by_model(frame), usage_summary_by_model(without)
    )


def test_frames_without_the_columns_classify_as_unknown():
    frame = pd.DataFrame(
        {
            "model": ["m", "m"],
            "scenario_id": ["s1", "s2"],
            "variable": ["tax", "tax"],
            "elapsed_seconds": [0.02, 30.0],
        }
    )

    provenance = household_call_provenance(frame)

    assert provenance["status"].tolist() == ["unknown", "unknown"]
    assert provenance["live_elapsed_seconds"].isna().all()
    assert household_call_provenance(pd.DataFrame()).empty


@pytest.mark.skipif(
    not FROZEN_US_PREDICTIONS.exists(), reason="frozen snapshot not checked out"
)
def test_the_frozen_us_run_predates_the_columns():
    """The frozen board predates the fields, so every household is unknown:
    its replays are identified only by the audit's evidence (#228)."""
    header = pd.read_csv(FROZEN_US_PREDICTIONS, nrows=0)
    assert not set(PROVENANCE) & set(header.columns)

    sample = pd.read_csv(
        FROZEN_US_PREDICTIONS,
        nrows=500,
        usecols=["model", "scenario_id", "variable", "elapsed_seconds"],
    )
    assert set(household_call_provenance(sample)["status"]) == {"unknown"}
