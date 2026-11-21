"""scripts/effort_sensitivity.py run_stats and --check-board on figures the
rows cannot establish.

model_cost_latency leaves out a cost it cannot establish, and the model when
it has neither a cost nor a latency; run_stats then reports null for those
fields, as the dashboard reports a cost as not recorded, rather than failing.
It reports null the same way for a call count some row does not record (rows
written before the column existed), and for output tokens and the request
time window when no row records them, where it used to raise or report zero;
with no first request, the lockfile pin is null too. A household whose
request failed records no usage and no request times, and does not null the
run's figures.
The dashboard leaves such a key out of a frozen modelStats row (the committed
snapshot's gpt-5.5 row has no latencySeconds), so --check-board reads the
frozen figures without assuming the keys: a figure only one side records fails
the check, and a figure neither side records passes it.
"""

import copy
import dataclasses
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from policybench.analysis import model_cost_latency
from policybench.config import PRICE_OVERRIDES_PER_1M

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def script():
    # The script defines dataclasses, which look their module up in
    # sys.modules while it loads.
    name = "effort_sensitivity_under_test"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / "effort_sensitivity.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(name, None)


@pytest.fixture(scope="module")
def run_stats(script):
    return script.run_stats


def _rows(model, *, cost, elapsed, live=1):
    return pd.DataFrame(
        [
            {
                "model": model,
                "scenario_id": scenario,
                "variable": "v",
                "prediction": 1.0,
                "total_cost_usd": cost,
                "elapsed_seconds": elapsed,
                "prompt_tokens": 1_000.0,
                "completion_tokens": 200.0,
                "total_tokens": 1_200.0,
                "cached_prompt_tokens": 400.0,
                "cache_write_prompt_tokens": 0.0,
                "live_calls": live,
                "cache_hit_calls": 0,
                "request_started_at": 1_763_600_000.0,
                "request_completed_at": 1_763_600_010.0,
            }
            for scenario in ("s1", "s2")
        ]
    )


def test_recorded_cost_and_latency_are_reported(run_stats):
    rows = _rows("claude-fable-5.2", cost=0.01, elapsed=4.0)
    stats = run_stats(rows, "claude-fable-5.2")
    expected = model_cost_latency(rows, PRICE_OVERRIDES_PER_1M)["claude-fable-5.2"]
    assert stats["cost_usd"] == expected["costUsd"] == pytest.approx(0.02)
    assert stats["cost_per_household_usd"] == expected["costPerHousehold"]
    assert stats["median_household_seconds"] == expected["latencySeconds"]


def test_unestablished_cost_is_null(run_stats):
    """Fable 5.2 rows with no recorded cost whose households each sum two
    responses: the cache-rate fill cannot price them, so the cost is null and
    the latency is still reported."""
    rows = _rows("claude-fable-5.2", cost=np.nan, elapsed=4.0, live=2)
    stats = run_stats(rows, "claude-fable-5.2")
    assert stats["cost_usd"] is None
    assert stats["cost_per_household_usd"] is None
    assert stats["median_household_seconds"] == pytest.approx(4.0)


def test_model_with_no_cost_or_latency_is_all_null(run_stats):
    """With no cost, no latency and no total tokens, model_cost_latency leaves
    the model out altogether."""
    rows = _rows("claude-fable-5.2", cost=np.nan, elapsed=np.nan, live=2).drop(
        columns=["total_tokens"]
    )
    assert "claude-fable-5.2" not in model_cost_latency(rows, PRICE_OVERRIDES_PER_1M)
    stats = run_stats(rows, "claude-fable-5.2")
    assert stats["cost_usd"] is None
    assert stats["cost_per_household_usd"] is None
    assert stats["median_household_seconds"] is None


def test_board_check_counts_a_figure_one_side_lacks_as_a_mismatch(script):
    """--check-board compares each recomputed figure with the frozen one; a
    figure only one side records fails the check instead of raising, and a
    figure neither side records passes."""
    assert script._close(1.0, 1.0 + 1e-12)
    assert not script._close(1.0, 1.0 + 1e-6)
    assert not script._close(None, 31.69)
    assert not script._close(31.69, None)
    assert script._close(None, None)


FABLE = "claude-fable-5.2"
OPUS = "claude-opus-5.5"


@pytest.fixture(scope="module")
def frozen(script):
    return script.scoring_inputs(), script.load_board_predictions()


def _without(inputs, model, key):
    payload = copy.deepcopy(inputs.payload)
    (row,) = [row for row in payload["modelStats"] if row["model"] == model]
    del row[key]
    return dataclasses.replace(inputs, payload=payload)


def _passes(script, report):
    return all(
        script._close(mine, frozen)
        for checks in report.values()
        for mine, frozen in checks.values()
    )


def test_committed_snapshot_passes_the_board_check(script, frozen):
    inputs, board = frozen
    assert _passes(script, script.check_board(inputs, board))


@pytest.mark.parametrize(
    ("model", "key", "field"),
    [
        (FABLE, "costUsd", "cost_usd"),
        (OPUS, "latencySeconds", "median_household_seconds"),
    ],
)
def test_a_figure_only_the_recomputation_has_fails_the_board_check(
    script, frozen, model, key, field
):
    """A frozen row without the key reports the figure as missing."""
    inputs, board = frozen
    report = script.check_board(_without(inputs, model, key), board)
    mine, frozen_value = report[model][field]
    assert mine is not None
    assert frozen_value is None
    assert not _passes(script, report)


@pytest.mark.parametrize(
    ("key", "field"),
    [("exact", "exact"), ("within1pct", "within1pct"), ("nParsed", "n_parsed")],
)
def test_a_score_the_frozen_row_lacks_fails_the_board_check(script, frozen, key, field):
    """The dashboard also leaves out a score it could not compute; the check
    reports it as missing and fails, for the exact comparison as well."""
    inputs, board = frozen
    report = script.check_board(_without(inputs, FABLE, key), board)
    mine, frozen_value = report[FABLE][field]
    assert mine is not None
    assert frozen_value is None
    assert mine != frozen_value
    assert not _passes(script, report)


def test_a_cost_neither_side_records_passes_the_board_check(script, frozen):
    """Fable 5.2 rows with no recorded cost whose rows each sum two responses
    get no cost from the cache-rate fill; a frozen row without costUsd agrees,
    and a frozen row with one does not."""
    inputs, board = frozen
    cleared = board.copy()
    fable = cleared["model"] == FABLE
    cleared.loc[fable, "total_cost_usd"] = np.nan
    cleared.loc[fable, "live_calls"] = 2
    cleared.loc[fable, "cache_hit_calls"] = 0
    agree = script.check_board(_without(inputs, FABLE, "costUsd"), cleared)
    assert agree[FABLE]["cost_usd"] == (None, None)
    assert _passes(script, agree)
    differ = script.check_board(inputs, cleared)
    assert differ[FABLE]["cost_usd"][0] is None
    assert differ[FABLE]["cost_usd"][1] is not None
    assert not _passes(script, differ)


UNTIMED = {"request_started_at": np.nan, "request_completed_at": np.nan}
PROVENANCE = [
    "live_calls",
    "cache_hit_calls",
    "request_started_at",
    "request_completed_at",
]


def test_untimed_rows_report_no_latency_and_no_time_window(run_stats):
    """Rows that record no elapsed time and no request timestamps: the cost is
    still reported; the latency and the first and last times are null. This
    raised ValueError (NaT) from the time window."""
    rows = _rows("claude-fable-5.2", cost=0.01, elapsed=np.nan).assign(**UNTIMED)
    stats = run_stats(rows, "claude-fable-5.2")
    assert stats["cost_usd"] == pytest.approx(0.02)
    assert stats["median_household_seconds"] is None
    assert stats["first_request_utc"] is None
    assert stats["last_response_utc"] is None


def test_rows_without_timestamps_keep_their_latency(run_stats):
    """Elapsed time recorded, request timestamps not (the frozen board's
    older rows): the latency is reported and the time window is null."""
    rows = _rows("claude-fable-5.2", cost=0.01, elapsed=4.0).assign(**UNTIMED)
    stats = run_stats(rows, "claude-fable-5.2")
    assert stats["median_household_seconds"] == pytest.approx(4.0)
    assert stats["first_request_utc"] is None
    assert stats["last_response_utc"] is None


def test_rows_written_before_the_provenance_columns_report_null_counts(run_stats):
    """Rows from a run that wrote no call counts or request times: those
    figures are null, the rest is reported, and the result writes as JSON.
    This raised KeyError('live_calls')."""
    rows = _rows("claude-fable-5.2", cost=0.01, elapsed=4.0).drop(columns=PROVENANCE)
    stats = run_stats(rows, "claude-fable-5.2")
    for field in (
        "answered_calls",
        "households_with_a_second_answered_call",
        "cache_hit_calls",
        "first_request_utc",
        "last_response_utc",
    ):
        assert stats[field] is None, field
    assert stats["cost_usd"] == pytest.approx(0.02)
    assert stats["median_household_seconds"] == pytest.approx(4.0)
    assert stats["households"] == 2
    assert stats["output_tokens"] == 400
    assert json.loads(json.dumps(stats)) == stats


def test_unrecorded_cache_hits_are_null_not_zero(run_stats):
    rows = _rows("claude-fable-5.2", cost=0.01, elapsed=4.0).assign(
        cache_hit_calls=np.nan
    )
    stats = run_stats(rows, "claude-fable-5.2")
    assert stats["answered_calls"] == 2
    assert stats["cache_hit_calls"] is None


def test_unrecorded_output_tokens_are_null_not_zero(run_stats):
    rows = _rows("claude-fable-5.2", cost=0.01, elapsed=4.0)
    unrecorded = rows.assign(completion_tokens=np.nan)
    assert run_stats(unrecorded, "claude-fable-5.2")["output_tokens"] is None
    absent = rows.drop(columns=["completion_tokens"])
    assert run_stats(absent, "claude-fable-5.2")["output_tokens"] is None


def test_a_failed_household_keeps_the_runs_tokens_and_time_window(run_stats):
    """The runner writes a failed household's rows with no prediction, usage
    or request times and with call counts of zero. The run's output tokens,
    request window and counts still come from the households that answered."""
    rows = _rows("claude-fable-5.2", cost=0.01, elapsed=4.0)
    failed = rows["scenario_id"] == "s2"
    unrecorded = [
        "prediction",
        "total_cost_usd",
        "elapsed_seconds",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cached_prompt_tokens",
        "cache_write_prompt_tokens",
        *UNTIMED,
    ]
    rows.loc[failed, unrecorded] = np.nan
    rows.loc[failed, "live_calls"] = 0
    stats = run_stats(rows, "claude-fable-5.2")
    assert stats["households"] == 2
    assert stats["parse_failures"] == 1
    assert stats["output_tokens"] == 200
    assert stats["answered_calls"] == 1
    assert stats["cache_hit_calls"] == 0
    assert stats["first_request_utc"] == "2025-11-20T00:53:20Z"
    assert stats["last_response_utc"] == "2025-11-20T00:53:30Z"
    assert stats["cost_usd"] == pytest.approx(0.01)


def test_lockfile_pin_is_null_without_a_first_request(script):
    """git log reads --before=None as now; with no first request the pin is
    not established, so it is null rather than today's lockfile."""
    assert script.lockfile_litellm(None) == {"lockfile_commit": None, "litellm": None}


def test_board_rows_reproduce_the_committed_run_figures(script, frozen):
    """The published summary's board figures, from the frozen board rows:
    Opus 5.5's rows predate the call counts (null), Fable 5.2's record them."""
    _, board = frozen
    committed = json.loads(
        (ROOT / "sensitivity" / "data" / "claude-effort-2026-11.json").read_text()
    )["runs"]
    boards = {run["model"]: run["board"] for run in committed.values()}
    assert set(boards) == {FABLE, OPUS}
    for model, published in boards.items():
        stats = script.run_stats(board, model)
        assert stats == {field: published[field] for field in stats}, model
    assert boards[OPUS]["answered_calls"] is None
    assert boards[FABLE]["answered_calls"] == 106
