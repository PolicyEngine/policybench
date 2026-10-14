"""Tests for analysis.model_cost_latency (leaderboard cost + latency)."""

import numpy as np
import pandas as pd
import pytest

from policybench.analysis import model_cost_latency


def _row(model, scenario, cost, elapsed, prompt=100, completion=50):
    return {
        "model": model,
        "scenario_id": scenario,
        "variable": "v",
        "prediction": 1.0,
        "total_cost_usd": cost,
        "elapsed_seconds": elapsed,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


def test_cost_total_per_household_and_median_latency():
    preds = pd.DataFrame(
        [
            _row("a", "s1", 0.10, 10.0),
            _row("a", "s2", 0.30, 30.0),
            _row("a", "s3", 0.20, 80.0),
        ]
    )
    out = model_cost_latency(preds)
    assert out["a"]["costUsd"] == pytest.approx(0.60)
    # per household = total / 3 distinct scenarios
    assert out["a"]["costPerHousehold"] == pytest.approx(0.20)
    # median of [10, 30, 80] = 30 (robust to the 80s outlier)
    assert out["a"]["latencySeconds"] == pytest.approx(30.0)
    assert out["a"]["totalTokens"] == 450


def test_latency_sums_calls_within_a_household_then_takes_median():
    # Two calls for s1 (a chunked / retried household), one for s2.
    preds = pd.DataFrame(
        [
            _row("a", "s1", 0.05, 12.0),
            _row("a", "s1", 0.05, 8.0),
            _row("a", "s2", 0.10, 4.0),
        ]
    )
    out = model_cost_latency(preds)
    # s1 = 12 + 8 = 20s, s2 = 4s -> median([20, 4]) = 12
    assert out["a"]["latencySeconds"] == pytest.approx(12.0)


def test_price_override_fills_missing_cost():
    preds = pd.DataFrame(
        [
            _row(
                "grok-build-0.1",
                "s1",
                np.nan,
                5.0,
                prompt=1_000_000,
                completion=2_000_000,
            ),
        ]
    )
    overrides = {"grok-build-0.1": {"input": 1.0, "output": 2.0}}
    out = model_cost_latency(preds, overrides)
    # 1M * $1/1M + 2M * $2/1M = $1 + $4 = $5
    assert out["grok-build-0.1"]["costUsd"] == pytest.approx(5.0)


def test_missing_cost_without_override_is_omitted_not_zero():
    preds = pd.DataFrame([_row("a", "s1", np.nan, 5.0)])
    out = model_cost_latency(preds)
    assert "costUsd" not in out["a"]
    # latency still recorded
    assert out["a"]["latencySeconds"] == pytest.approx(5.0)


def test_all_null_latency_is_omitted_not_zero():
    preds = pd.DataFrame(
        [
            _row("a", "s1", 0.10, np.nan),
            _row("a", "s2", 0.20, np.nan),
        ]
    )
    out = model_cost_latency(preds)
    assert "latencySeconds" not in out["a"]


def test_empty_predictions_returns_empty():
    assert model_cost_latency(pd.DataFrame()) == {}


# ----- invariants of household latency (docs/latency_replay_audit.md) -------

from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from policybench.analysis import (  # noqa: E402
    REPLAYED_HOUSEHOLD_SECONDS,
    household_latency_seconds,
)

# A household's calls: each call's latency and how many rows it answered.
CALLS = st.lists(
    st.tuples(
        st.floats(min_value=0.0, max_value=2_000.0, allow_nan=False),
        st.integers(min_value=1, max_value=8),
    ),
    min_size=1,
    max_size=6,
)
HOUSEHOLDS = st.lists(CALLS, min_size=1, max_size=15)


def _split_rows(households):
    """Rows the way the harness writes them: each call's latency divided
    equally among the rows it answered."""
    rows = []
    for index, calls in enumerate(households):
        for seconds, n_rows in calls:
            rows += [_row("m", f"s{index:03d}", 0.01, seconds / n_rows)] * n_rows
    return pd.DataFrame(rows)


@given(HOUSEHOLDS)
@settings(max_examples=200, deadline=None)
def test_household_latency_is_the_sum_of_its_calls(households):
    """Splitting a call's latency across its rows and summing the rows gives
    back the household's total request time."""
    latency = household_latency_seconds(_split_rows(households))
    for index, calls in enumerate(households):
        expected = sum(seconds for seconds, _ in calls)
        assert latency[("m", f"s{index:03d}")] == pytest.approx(expected, abs=1e-9)


@given(HOUSEHOLDS)
@settings(max_examples=200, deadline=None)
def test_published_latency_is_the_median_household(households):
    preds = _split_rows(households)
    expected = float(np.median([sum(s for s, _ in calls) for calls in households]))
    out = model_cost_latency(preds)
    assert out["m"]["latencySeconds"] == pytest.approx(expected, abs=1e-6)
    # Cost is additive the same way: the run total is every row's cost.
    assert out["m"]["costUsd"] == pytest.approx(0.01 * len(preds))


@given(
    st.lists(
        st.floats(min_value=0.0, max_value=2_000.0, allow_nan=False),
        min_size=1,
        max_size=20,
    ),
    st.data(),
)
@settings(max_examples=200, deadline=None)
def test_a_replay_can_only_lower_the_median(seconds, data):
    """Replacing a household's time with a cache lookup's (smaller) time
    never raises the published median, so replays bias it down, never up."""
    index = data.draw(st.integers(min_value=0, max_value=len(seconds) - 1))
    lookup = data.draw(st.floats(min_value=0.0, max_value=seconds[index]))
    before = model_cost_latency(
        pd.DataFrame([_row("m", f"s{i}", 0.01, t) for i, t in enumerate(seconds)])
    )["m"]["latencySeconds"]
    replayed = list(seconds)
    replayed[index] = lookup
    after = model_cost_latency(
        pd.DataFrame([_row("m", f"s{i}", 0.01, t) for i, t in enumerate(replayed)])
    )["m"]["latencySeconds"]
    assert after <= before + 1e-9


@given(
    st.integers(min_value=0, max_value=12),
    st.integers(min_value=0, max_value=12),
)
def test_a_median_under_a_second_means_most_households_replayed(n_fast, n_slow):
    """With replays under the line and calls above it, the median is under the
    line when more than half the households replayed and at or above it when
    fewer than half did. At exactly half it can fall either side (the tie test
    below), so the paper's dash rule is a majority-replay rule only off ties."""
    if n_fast + n_slow == 0:
        return
    seconds = [0.02] * n_fast + [30.0] * n_slow
    median = model_cost_latency(
        pd.DataFrame([_row("m", f"s{i}", 0.01, t) for i, t in enumerate(seconds)])
    )["m"]["latencySeconds"]
    if 2 * n_fast > n_fast + n_slow:
        assert median < REPLAYED_HOUSEHOLD_SECONDS
    if 2 * n_fast < n_fast + n_slow:
        assert median >= REPLAYED_HOUSEHOLD_SECONDS


@given(
    st.integers(min_value=1, max_value=12),
    st.floats(min_value=0.0, max_value=0.12),
    st.floats(min_value=1.0, max_value=3.0),
)
def test_at_exactly_half_replays_the_median_is_the_middle_pairs_mean(n, replay, call):
    """Half replays and half calls: the median is the mean of the slowest
    replay and the fastest call, which is under a second only when the calls
    are fast enough (50 replays at 0.02 s and 50 calls at 1.75 s give 0.885 s)."""
    seconds = [replay] * n + [call] * n
    median = model_cost_latency(
        pd.DataFrame([_row("m", f"s{i}", 0.01, t) for i, t in enumerate(seconds)])
    )["m"]["latencySeconds"]
    assert median == pytest.approx((replay + call) / 2)
    assert (median < REPLAYED_HOUSEHOLD_SECONDS) == (
        replay + call < 2 * REPLAYED_HOUSEHOLD_SECONDS
    )


@given(
    st.lists(st.floats(min_value=1.0, max_value=500.0), min_size=1, max_size=10),
    st.integers(min_value=1, max_value=10),
)
def test_untimed_households_are_left_out_not_counted_as_zero(seconds, n_untimed):
    timed = [_row("m", f"t{i}", 0.01, t) for i, t in enumerate(seconds)]
    untimed = [_row("m", f"u{i}", 0.01, np.nan) for i in range(n_untimed)]
    out = model_cost_latency(pd.DataFrame(timed + untimed))
    assert out["m"]["latencySeconds"] == pytest.approx(float(np.median(seconds)))
    latency = household_latency_seconds(pd.DataFrame(untimed))
    assert latency.isna().all()


def test_household_latency_of_nothing_is_empty():
    assert household_latency_seconds(pd.DataFrame()).empty
    assert household_latency_seconds(pd.DataFrame([{"model": "m"}])).empty
