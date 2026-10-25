"""Tests for analysis.model_cost_latency (leaderboard cost + latency).

Cost invariants, for every input (the property test executes them):
- costUsd and costPerHousehold are both present or both absent;
- a model has a cost exactly when one of its rows recorded total_cost_usd, or
  it has a price override and one of its rows recorded both prompt and
  completion token counts; a row missing either count is not priced, so no
  cost rests on a count nobody recorded, and a model with no usage at all
  gets no cost rather than $0;
- a recorded cost is the sum of the recorded row costs and the override is
  not consulted; a filled cost is the override's prices applied to the token
  sums of the rows that recorded both counts;
- costPerHousehold is costUsd over the distinct households in the input.
The frozen-snapshot tests check the published figures: every model's usage
fields but Claude Fable 5's reproduce from the frozen predictions, and Fable
5's, which those rows do not record, are not computed at all.
"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from policybench.analysis import model_cost_latency
from policybench.config import PRICE_OVERRIDES_PER_1M
from policybench.snapshot_payload import read_run_payload

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "paper/snapshot/20260501"


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


def test_price_override_without_recorded_tokens_gives_no_cost():
    """Claude Fable 5's frozen board rows record no cost, tokens or latency. Its
    price override has nothing to price, so it gets no cost, not $0."""
    preds = pd.DataFrame(
        [
            _row("claude-fable-5", s, np.nan, np.nan, prompt=np.nan, completion=np.nan)
            for s in ("s1", "s2")
        ]
    )
    overrides = {"claude-fable-5": PRICE_OVERRIDES_PER_1M["claude-fable-5"]}
    assert model_cost_latency(preds, overrides) == {}


def test_price_override_without_recorded_tokens_keeps_the_rest():
    preds = pd.DataFrame(
        [_row("m", "s1", np.nan, 5.0, prompt=np.nan, completion=np.nan)]
    )
    out = model_cost_latency(preds, {"m": {"input": 1.0, "output": 2.0}})
    assert out == {"m": {"latencySeconds": 5.0}}


@pytest.mark.parametrize(
    "prompt, completion", [(np.nan, 2_000_000), (1_000_000, np.nan)]
)
def test_price_override_needs_both_token_counts(prompt, completion):
    """Pricing one side would report part of the spend as all of it."""
    preds = pd.DataFrame(
        [_row("m", "s1", np.nan, 5.0, prompt=prompt, completion=completion)]
    )
    out = model_cost_latency(preds, {"m": {"input": 1.0, "output": 2.0}})
    assert "costUsd" not in out["m"]
    assert "costPerHousehold" not in out["m"]


def test_price_override_needs_both_counts_on_one_row():
    """Counts split across rows price no row: each row is missing one side."""
    preds = pd.DataFrame(
        [
            _row("m", "s1", np.nan, 5.0, prompt=1_000_000, completion=np.nan),
            _row("m", "s2", np.nan, 5.0, prompt=np.nan, completion=1_000_000),
        ]
    )
    out = model_cost_latency(preds, {"m": {"input": 1.0, "output": 2.0}})
    assert "costUsd" not in out["m"]


def test_price_override_prices_only_rows_with_both_counts():
    """A row missing a count adds nothing; it is not priced at $0 for it."""
    preds = pd.DataFrame(
        [
            _row("m", "s1", np.nan, 5.0, prompt=1_000_000, completion=2_000_000),
            _row("m", "s2", np.nan, 5.0, prompt=3_000_000, completion=np.nan),
            _row("m", "s3", np.nan, 5.0, prompt=np.nan, completion=np.nan),
        ]
    )
    out = model_cost_latency(preds, {"m": {"input": 1.0, "output": 2.0}})
    # s1 only: 1M * $1/1M + 2M * $2/1M
    assert out["m"]["costUsd"] == pytest.approx(5.0)
    assert out["m"]["costPerHousehold"] == pytest.approx(5.0 / 3)


def test_recorded_zero_cost_and_recorded_zero_tokens_stay_zero():
    """A $0 the rows record (a free model, or zero tokens) is a real $0."""
    preds = pd.DataFrame(
        [
            _row("free", "s1", 0.0, 5.0),
            _row("zero-tokens", "s1", np.nan, 5.0, prompt=0, completion=0),
        ]
    )
    out = model_cost_latency(preds, {"zero-tokens": {"input": 1.0, "output": 2.0}})
    assert out["free"]["costUsd"] == 0.0
    assert out["zero-tokens"]["costUsd"] == 0.0


MODEL_NAMES = ("a", "b", "c")
SCENARIOS = ("s1", "s2", "s3", "s4")

missing = st.just(float("nan"))
usage_row = st.fixed_dictionaries(
    {
        "model": st.sampled_from(MODEL_NAMES),
        "scenario_id": st.sampled_from(SCENARIOS),
        "total_cost_usd": st.one_of(
            missing,
            st.just(0.0),
            st.floats(min_value=0, max_value=50, allow_subnormal=False),
        ),
        "prompt_tokens": st.one_of(missing, st.integers(0, 5_000_000).map(float)),
        "completion_tokens": st.one_of(missing, st.integers(0, 5_000_000).map(float)),
        "elapsed_seconds": st.one_of(missing, st.floats(min_value=0, max_value=600)),
    }
)
price = st.fixed_dictionaries(
    {
        "input": st.floats(min_value=0, max_value=100, allow_subnormal=False),
        "output": st.floats(min_value=0, max_value=100, allow_subnormal=False),
    }
)


def _reference_cost(rows: list[dict], override: dict | None) -> float | None:
    """The cost the invariants define, from the rows in plain Python."""
    recorded = [
        r["total_cost_usd"] for r in rows if not math.isnan(r["total_cost_usd"])
    ]
    if recorded:
        return math.fsum(recorded)
    priced = [
        r
        for r in rows
        if not math.isnan(r["prompt_tokens"]) and not math.isnan(r["completion_tokens"])
    ]
    if override is None or not priced:
        return None
    return (
        math.fsum(r["prompt_tokens"] for r in priced) * override["input"] / 1e6
        + math.fsum(r["completion_tokens"] for r in priced) * override["output"] / 1e6
    )


@settings(max_examples=300, deadline=None)
@given(
    drawn=st.lists(usage_row, min_size=1, max_size=12),
    overrides=st.dictionaries(st.sampled_from(MODEL_NAMES), price, max_size=3),
    uncosted=st.sets(st.sampled_from(MODEL_NAMES)),
    untokened=st.sets(st.sampled_from(MODEL_NAMES)),
)
def test_cost_is_present_exactly_when_recorded_usage_supports_it(
    drawn, overrides, uncosted, untokened
):
    # Whole models with no recorded cost, or (like Fable 5) no token counts,
    # so the fill and the no-usage cases are drawn often.
    nan = float("nan")
    rows = [
        {
            **row,
            **({"total_cost_usd": nan} if row["model"] in uncosted else {}),
            **(
                {"prompt_tokens": nan, "completion_tokens": nan}
                if row["model"] in untokened
                else {}
            ),
        }
        for row in drawn
    ]
    frame = pd.DataFrame(rows)
    frame["variable"] = "v"
    frame["prediction"] = 1.0
    frame["total_tokens"] = frame["prompt_tokens"] + frame["completion_tokens"]
    out = model_cost_latency(frame, overrides)
    households = frame["scenario_id"].nunique()
    for model in sorted(set(frame["model"])):
        entry = out.get(model, {})
        expected = _reference_cost(
            [r for r in rows if r["model"] == model], overrides.get(model)
        )
        assert ("costUsd" in entry) == ("costPerHousehold" in entry)
        if expected is None:
            assert "costUsd" not in entry
            continue
        assert entry["costUsd"] == pytest.approx(expected, rel=1e-12, abs=1e-12)
        assert entry["costPerHousehold"] == pytest.approx(
            entry["costUsd"] / households, rel=1e-12, abs=1e-12
        )


# --- The frozen snapshot: published figures --------------------------------

USAGE_FIELDS = ("costUsd", "costPerHousehold", "latencySeconds", "totalTokens")


@pytest.fixture(scope="module")
def frozen():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    run = SNAPSHOT_DIR / "runs" / manifest["source_run_labels"]["us"]
    predictions = pd.read_csv(
        run / "predictions.csv.gz",
        usecols=[
            "model",
            "scenario_id",
            "variable",
            "prediction",
            "error",
            "total_cost_usd",
            "elapsed_seconds",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        ],
        low_memory=False,
    )
    published = {row["model"]: row for row in read_run_payload(run)["modelStats"]}
    return model_cost_latency(predictions, PRICE_OVERRIDES_PER_1M), published


def test_frozen_usage_reproduces_every_published_model_but_fable_5(frozen):
    """The published cost, latency and tokens of every model but Fable 5 are
    model_cost_latency's on the frozen predictions, to the bit and with the
    same fields present."""
    computed, published = frozen
    assert len(published) > 1
    for model, row in published.items():
        if model == "claude-fable-5":
            continue
        assert {k: row[k] for k in USAGE_FIELDS if k in row} == computed[model], model


def test_frozen_fable_5_usage_is_carried_not_computed(frozen):
    """Fable 5's rows record no usage, so nothing is computed for it (no $0
    cost); the published figures are the four the release drivers carry."""
    computed, published = frozen
    assert "claude-fable-5" not in computed
    fable = published["claude-fable-5"]
    assert all(fable[k] > 0 for k in USAGE_FIELDS)


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
