"""Tests for analysis.model_cost_latency (leaderboard cost + latency).

Cost invariants, for every input (the property test executes them):
- costUsd and costPerHousehold are both present or both absent;
- a recorded cost is the sum of the recorded row costs and the override is
  not consulted;
- otherwise a model has a cost exactly when it has a price override that is
  not a Responses-API GPT model and one of its rows recorded both prompt and
  completion token counts, and, for an override with a cache rate, every such
  row records one provider response (live_calls and cache_hit_calls are 1
  and 0, or 0 and 1), a cached count and, if the override lists a cache-write
  rate, a cache-write count; a row missing either token count is not priced,
  so no cost rests on a count nobody recorded, and a model with no usage at
  all gets no cost rather than $0;
- a filled cost is never negative for non-negative counts and rates;
- a filled cost is the override's input and output rates applied to the
  token sums of the rows that recorded both counts, with each row's cached
  and cache-write tokens, bounded by its prompt count, at the override's
  cache rates where it has them;
- a Responses-API GPT model's cost is never filled: its long-context rate
  turns on one request's prompt length, which no row records;
- costPerHousehold is costUsd over the distinct households in the input.
The reconstruction tests check that a filled cache-rate cost is what
eval_no_tools._reconstruct_token_cost records for the one response the rows
share, and that rows summing two responses, or with an unrecorded count, get
no cost. The frozen-snapshot tests check the published figures: every model's
usage fields but Claude Fable 5's reproduce from the frozen predictions,
including the two models whose cost the override fills (Gemini 3.6 Flash and
Grok Build 0.1), and Fable 5's, which those rows do not record, are not
computed at all.
"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from policybench.analysis import RESPONSE_COUNT_COLUMNS, model_cost_latency
from policybench.config import GPT_RESPONSES_MODELS, MODELS, PRICE_OVERRIDES_PER_1M
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


def _usage_row(
    model, scenario, prompt, completion, cached, cache_write, live=1, cache_hits=0
):
    """A row with no recorded cost; by default its usage is one live
    response's."""
    return {
        **_row(model, scenario, np.nan, 5.0, prompt=prompt, completion=completion),
        "cached_prompt_tokens": cached,
        "cache_write_prompt_tokens": cache_write,
        "live_calls": live,
        "cache_hit_calls": cache_hits,
    }


@pytest.mark.parametrize("prompt", [100_000, 300_000])
def test_gpt_responses_override_fills_no_cost(prompt):
    """GPT-6.1 Sol charges a request above 272k prompt tokens 2x input and
    cache and 1.5x output on every token. A row holds an equal share of its
    request group's usage, so the row does not show whether a request crossed
    272k, and pricing the rows at the base rates could understate the cost."""
    model = "gpt-6.1-sol"
    preds = pd.DataFrame(
        [_usage_row(model, "s1", prompt, 20_000, 50_000, 0)],
    )
    out = model_cost_latency(preds, PRICE_OVERRIDES_PER_1M)
    assert "costUsd" not in out[model]
    assert "costPerHousehold" not in out[model]
    assert out[model]["latencySeconds"] == pytest.approx(5.0)


def test_gpt_household_sum_does_not_bound_a_request_on_a_partial_frame():
    """One GPT-6.1 Sol request of 300,000 prompt tokens, above the 272k line,
    split among a household's four rows. A frame holding three of them sums
    to 225,000, which looks like a base-rate request. The rows do not show
    whether a household is complete, so a household's sum is not used to
    place its requests under 272k, and the model gets no cost."""
    model = "gpt-6.1-sol"
    household = [_usage_row(model, "s1", 300_000 / 4, 5_000, 0, 0) for _ in range(4)]
    partial = pd.DataFrame(household[:3])
    assert partial["prompt_tokens"].sum() < 272_000 < 300_000
    for frame in (partial, pd.DataFrame(household)):
        out = model_cost_latency(frame, PRICE_OVERRIDES_PER_1M)
        assert "costUsd" not in out[model]


def test_cache_rates_price_cached_and_cache_write_tokens():
    """Claude Fable 5.2's override lists $8 input, $0.20 cache reads, $10
    cache writes and $40 output per 1M tokens. The filled cost prices the
    rows' cached and cache-write tokens at those rates, not at the input
    rate."""
    model = "claude-fable-5.2"
    rates = PRICE_OVERRIDES_PER_1M[model]
    assert rates == {
        "input": 8.0,
        "output": 40.0,
        "cache_read": 0.2,
        "cache_write": 10.0,
    }
    preds = pd.DataFrame(
        [_usage_row(model, "s1", 1_000_000, 10_000, 600_000, 100_000)],
    )
    out = model_cost_latency(preds, PRICE_OVERRIDES_PER_1M)
    # 300k uncached at $8, 600k cached at $0.20, 100k written at $10, and
    # 10k output at $40 per 1M: $2.40 + $0.12 + $1.00 + $0.40.
    assert out[model]["costUsd"] == pytest.approx(3.92)


def test_cache_read_override_prices_cache_writes_at_input():
    """Grok 4.7's override lists a cache-read rate and no cache-write rate,
    so cache-write tokens take the input rate, as the reconstruction prices
    them, and a frame with no cache-write column still has a cost."""
    model = "grok-4.7"
    preds = pd.DataFrame(
        [_usage_row(model, "s1", 1_000_000, 100_000, 400_000, 200_000)],
    )
    # $2 on 600k (uncached and written), $0.50 on 400k cached, $6 on 100k.
    expected = (600_000 * 2.0 + 400_000 * 0.5 + 100_000 * 6.0) / 1e6
    out = model_cost_latency(preds, PRICE_OVERRIDES_PER_1M)
    assert out[model]["costUsd"] == pytest.approx(expected)
    no_writes = preds.drop(columns=["cache_write_prompt_tokens"])
    out = model_cost_latency(no_writes, PRICE_OVERRIDES_PER_1M)
    assert out[model]["costUsd"] == pytest.approx(expected)


@pytest.mark.parametrize(
    "model, dropped",
    [
        ("claude-fable-5.2", "cached_prompt_tokens"),
        ("claude-fable-5.2", "cache_write_prompt_tokens"),
        ("grok-4.7", "cached_prompt_tokens"),
    ],
)
def test_cache_rate_without_its_column_fills_no_cost(model, dropped):
    """A frame with no column for a usage the override prices apart records
    none of that usage, so the cache distinction cannot be recovered."""
    preds = pd.DataFrame(
        [_usage_row(model, "s1", 1_000_000, 10_000, 600_000, 100_000)],
    ).drop(columns=[dropped])
    out = model_cost_latency(preds, PRICE_OVERRIDES_PER_1M)
    assert "costUsd" not in out[model]


def test_input_output_override_needs_no_cache_columns():
    """An override with only input and output rates prices every prompt token
    at the input rate, so the cache columns do not matter."""
    preds = pd.DataFrame(
        [_row("m", "s1", np.nan, 5.0, prompt=1_000_000, completion=2_000_000)]
    )
    out = model_cost_latency(preds, {"m": {"input": 1.0, "output": 2.0}})
    assert out["m"]["costUsd"] == pytest.approx(5.0)
    preds["cached_prompt_tokens"] = 500_000.0
    out = model_cost_latency(preds, {"m": {"input": 1.0, "output": 2.0}})
    assert out["m"]["costUsd"] == pytest.approx(5.0)


@pytest.mark.parametrize(
    "model, emptied",
    [
        ("claude-fable-5.2", "cached_prompt_tokens"),
        ("claude-fable-5.2", "cache_write_prompt_tokens"),
        ("grok-4.7", "cached_prompt_tokens"),
    ],
)
def test_empty_cache_count_fills_no_cost(model, emptied):
    """An empty count may be one the provider did not report or a column
    another model's rows brought into the frame, so the cache distinction
    cannot be recovered and the model gets no cost."""
    preds = pd.DataFrame(
        [
            _usage_row(model, "s1", 1_000_000, 10_000, 600_000, 100_000),
            _usage_row(model, "s2", 1_000_000, 10_000, 600_000, 100_000),
        ]
    )
    preds.loc[1, emptied] = np.nan
    out = model_cost_latency(preds, PRICE_OVERRIDES_PER_1M)
    assert "costUsd" not in out[model]


def test_empty_cache_write_count_is_irrelevant_without_a_cache_write_rate():
    """Grok 4.7 lists no cache-write rate, so cache-write tokens price at the
    input rate like uncached ones and an empty cache-write count changes
    nothing."""
    model = "grok-4.7"
    preds = pd.DataFrame(
        [_usage_row(model, "s1", 1_000_000, 100_000, 400_000, np.nan)],
    )
    expected = (600_000 * 2.0 + 400_000 * 0.5 + 100_000 * 6.0) / 1e6
    out = model_cost_latency(preds, PRICE_OVERRIDES_PER_1M)
    assert out[model]["costUsd"] == pytest.approx(expected)


def test_concatenated_frames_fill_no_cost_from_padded_cache_columns():
    """full_run_export and fold_board concatenate per-model frames, and
    pandas pads a column one frame lacks with NaN. A cache-rate model whose
    own rows have no cache columns gets no cost in the combined frame, as it
    does alone."""
    model = "claude-fable-5.2"
    older = pd.DataFrame(
        [_row(model, s, np.nan, 5.0, prompt=1_000, completion=200) for s in "ab"]
    )
    newer = pd.DataFrame(
        [
            {
                **_usage_row("claude-opus-5.5", s, 1_000, 200, 400, 0),
                "total_cost_usd": 0.01,
            }
            for s in "ab"
        ]
    )
    combined = pd.concat([older, newer], ignore_index=True)
    assert combined.loc[combined["model"] == model, "cached_prompt_tokens"].isna().all()
    assert "costUsd" not in model_cost_latency(older, PRICE_OVERRIDES_PER_1M)[model]
    assert "costUsd" not in model_cost_latency(combined, PRICE_OVERRIDES_PER_1M)[model]


def _two_response_rows(model, first, second, rows):
    """One synchronous household answered by two responses: the runner sums
    their counts (_aggregate_request_results), splits the sums equally among
    the household's rows and repeats the response count on each."""
    summed = [a + b for a, b in zip(first, second)]
    return [
        _usage_row(model, "s1", *(count / rows for count in summed), live=2)
        for _ in range(rows)
    ]


def test_rows_summing_two_responses_fill_no_cost():
    """Two Fable 5.2 responses of 100,000 prompt and 1,000 completion tokens,
    with 150,000 and 0 cache reads reported: the reconstruction bounds the
    first response's reads by its prompt and prices the two at $0.90, but
    bounding the household's sums would give $0.51. Rows that sum responses
    do not show each response's counts, so the model gets no cost."""
    reconstruct = _reconstruction()
    model = "claude-fable-5.2"
    first, second = (100_000, 1_000, 150_000, 0), (100_000, 1_000, 0, 0)
    per_response = sum(
        reconstruct(
            model_name=model,
            model_id=MODELS[model],
            prompt_tokens=p,
            completion_tokens=c,
            cached_prompt_tokens=r,
            cache_write_prompt_tokens=w,
        ).usd
        for p, c, r, w in (first, second)
    )
    assert per_response == pytest.approx(0.90)
    preds = pd.DataFrame(_two_response_rows(model, first, second, rows=4))
    out = model_cost_latency(preds, PRICE_OVERRIDES_PER_1M)
    assert "costUsd" not in out[model]


@pytest.mark.parametrize(
    "live, cache_hits",
    [
        (2, 0),
        (1, 1),
        (0, 2),
        (0, 0),
        (np.nan, 0),
        (1, np.nan),
        # Counts no runner writes, though they sum to one.
        (-1, 2),
        (2, -1),
        (0.5, 0.5),
        (1.5, -0.5),
    ],
)
def test_cache_rates_need_rows_recording_one_response(live, cache_hits):
    """A cache-rate fill needs every priced row to record one response, live
    or replayed: counts of (1, 0) or (0, 1). A row recording none, several,
    no count, or counts that only sum to one gets no cost. (One replayed
    response is priced: test_one_replayed_response_is_priced.)"""
    model = "claude-fable-5.2"
    preds = pd.DataFrame(
        [
            _usage_row(model, "s1", 1_000, 200, 400, 100),
            _usage_row(model, "s2", 1_000, 200, 400, 100, live, cache_hits),
        ]
    )
    out = model_cost_latency(preds, PRICE_OVERRIDES_PER_1M)
    assert "costUsd" not in out[model]


def test_cache_rates_need_the_response_count_columns():
    model = "claude-fable-5.2"
    preds = pd.DataFrame([_usage_row(model, "s1", 1_000, 200, 400, 100)])
    for column in RESPONSE_COUNT_COLUMNS:
        out = model_cost_latency(preds.drop(columns=[column]), PRICE_OVERRIDES_PER_1M)
        assert "costUsd" not in out[model]


def test_one_replayed_response_is_priced():
    """A response the disk cache replays records its usage like a live one."""
    model = "claude-fable-5.2"
    preds = pd.DataFrame(
        [_usage_row(model, "s1", 1_000_000, 10_000, 600_000, 100_000, 0, 1)]
    )
    out = model_cost_latency(preds, PRICE_OVERRIDES_PER_1M)
    assert out[model]["costUsd"] == pytest.approx(3.92)


def test_response_counts_read_back_as_floats_are_priced():
    """A count column with an empty cell elsewhere, or one read back from a
    CSV beside such a column, holds 1.0 and 0.0: still one response."""
    model = "claude-fable-5.2"
    preds = pd.DataFrame(
        [
            _usage_row(model, "s1", 1_000_000, 10_000, 600_000, 100_000, 1.0, 0.0),
            _usage_row(model, "s2", 1_000_000, 10_000, 600_000, 100_000, 0.0, 1.0),
        ]
    )
    assert preds["live_calls"].dtype == float
    out = model_cost_latency(preds, PRICE_OVERRIDES_PER_1M)
    assert out[model]["costUsd"] == pytest.approx(2 * 3.92)


@pytest.mark.parametrize("shares", range(2, 13))
@pytest.mark.parametrize("prompt", [1, 7, 10, 1_000_003])
def test_a_fully_cached_prompt_never_prices_below_zero(shares, prompt):
    """A fully cached response split among rows whose shares are not exact
    in floating point, at a zero cache-read rate: every token is cached, so
    the cost is exactly zero. Subtracting the summed cache counts from the
    summed prompt count gave -8.9e-22 for seven tokens over six rows."""
    rates = {"input": 1.0, "output": 1.0, "cache_read": 0.0}
    share = prompt / shares
    preds = pd.DataFrame(
        [_usage_row("m", "s1", share, 0, share, 0) for _ in range(shares)]
    )
    out = model_cost_latency(preds, {"m": rates})
    assert out["m"]["costUsd"] == 0.0


def test_response_count_columns_are_the_runner_provenance_counts():
    from policybench.eval_no_tools import NO_TOOLS_CALL_PROVENANCE_COLUMNS

    assert set(RESPONSE_COUNT_COLUMNS) == set(NO_TOOLS_CALL_PROVENANCE_COLUMNS) - {
        "live_elapsed_seconds"
    }


def test_input_output_override_ignores_response_counts():
    """An input-and-output override prices the rows' sums, which are linear
    in the responses they add up, so rows recording several responses, or no
    count, still price."""
    preds = pd.DataFrame(
        [
            _usage_row("m", "s1", 1_000_000, 2_000_000, np.nan, np.nan, live=3),
            _usage_row("m", "s2", 1_000_000, 2_000_000, np.nan, np.nan, live=np.nan),
        ]
    )
    out = model_cost_latency(preds, {"m": {"input": 1.0, "output": 2.0}})
    assert out["m"]["costUsd"] == pytest.approx(10.0)


def test_cache_write_rate_needs_the_cached_count():
    """The cached count bounds the cache-write count, so an override with a
    cache-write rate and no cache-read rate still needs it: 300k cached and
    900k written on a 1M prompt leaves 700k to price at the write rate."""
    rates = {"input": 1.0, "output": 2.0, "cache_write": 3.0}
    row = _usage_row("m", "s1", 1_000_000, 0, 300_000, 900_000)
    out = model_cost_latency(pd.DataFrame([row]), {"m": rates})
    # 300k cached at the input rate, 700k written at the write rate.
    assert out["m"]["costUsd"] == pytest.approx((300_000 * 1.0 + 700_000 * 3.0) / 1e6)
    row["cached_prompt_tokens"] = np.nan
    out = model_cost_latency(pd.DataFrame([row]), {"m": rates})
    assert "costUsd" not in out["m"]


@pytest.fixture
def pandas_2_groupby(monkeypatch):
    """DataFrame.groupby with pandas 2's default: a categorical key gets a
    group for every category (observed=False). uv.lock pins pandas 3, whose
    default is observed=True, and pyproject allows pandas>=2.0."""
    groupby = pd.DataFrame.groupby

    def observed_false_by_default(self, *args, **kwargs):
        kwargs.setdefault("observed", False)
        return groupby(self, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "groupby", observed_false_by_default)


@pytest.mark.parametrize("groupby_default", ["pandas 3", "pandas 2"])
@pytest.mark.parametrize("model", ["gemini-3.6-flash", "claude-fable-5.2"])
def test_categorical_model_column_prices_the_model_itself(
    request, groupby_default, model
):
    """With the model column categorical and the filled model after another
    category, the fill prices the model's own rows, under either pandas
    default, not the first category's empty group."""
    if groupby_default == "pandas 2":
        request.getfixturevalue("pandas_2_groupby")
    rates = PRICE_OVERRIDES_PER_1M[model]
    filled = [_usage_row(model, s, 1_000, 200, 400, 100) for s in ("s1", "s2")]
    recorded = [
        {**_usage_row("claude-opus-5", s, 1_000, 200, 400, 100), "total_cost_usd": 0.01}
        for s in ("s1", "s2")
    ]
    preds = pd.DataFrame(recorded + filled)
    preds["model"] = pd.Categorical(
        preds["model"], categories=["claude-opus-5", model, "unused"]
    )
    if "cache_read" in rates:
        expected = (
            2 * 500 * rates["input"]
            + 2 * 400 * rates["cache_read"]
            + 2 * 100 * rates["cache_write"]
            + 2 * 200 * rates["output"]
        ) / 1e6
    else:
        expected = (2 * 1_000 * rates["input"] + 2 * 200 * rates["output"]) / 1e6
    out = model_cost_latency(preds, PRICE_OVERRIDES_PER_1M)
    assert out[model]["costUsd"] == pytest.approx(expected, rel=1e-12)
    assert out["claude-opus-5"]["costUsd"] == pytest.approx(0.02)


def _reconstruction():
    """eval_no_tools imports litellm, so the parity tests import it lazily."""
    from policybench.eval_no_tools import _reconstruct_token_cost

    return _reconstruct_token_cost


USAGES = [
    (1_000, 500, None, None),
    (120_000, 30_000, 70_000, None),
    (150_000, 8_000, 40_000, 25_000),
    (300_000, 12_000, 100_000, 50_000),
    (80_000, 4_000, 90_000, 5_000),  # a cached count above the prompt count
]


@pytest.mark.parametrize("model", sorted(PRICE_OVERRIDES_PER_1M))
@pytest.mark.parametrize("prompt, completion, cached, cache_write", USAGES)
def test_filled_cost_matches_request_reconstruction(
    model, prompt, completion, cached, cache_write
):
    """A household answered by one response has its usage on one row here, so
    the filled cost is what eval_no_tools._reconstruct_token_cost records for
    that response, for every override, where the row records each count the
    override's cache rates need; a GPT Responses model's is not filled."""
    reconstruct = _reconstruction()
    recorded = reconstruct(
        model_name=model,
        model_id=MODELS.get(model, model),
        prompt_tokens=prompt,
        completion_tokens=completion,
        cached_prompt_tokens=cached,
        cache_write_prompt_tokens=cache_write,
    )
    assert recorded.usd is not None and recorded.is_estimated is False
    preds = pd.DataFrame(
        [
            _usage_row(
                model,
                "s1",
                prompt,
                completion,
                np.nan if cached is None else cached,
                np.nan if cache_write is None else cache_write,
            )
        ]
    )
    out = model_cost_latency(preds, PRICE_OVERRIDES_PER_1M)[model]
    rates = PRICE_OVERRIDES_PER_1M[model]
    unrecorded = ("cache_read" in rates or "cache_write" in rates) and (
        cached is None or ("cache_write" in rates and cache_write is None)
    )
    if model in GPT_RESPONSES_MODELS or unrecorded:
        assert "costUsd" not in out
    else:
        assert out["costUsd"] == pytest.approx(recorded.usd, rel=1e-12)


def test_filled_cost_splits_like_the_request():
    """Rows that share one response's usage equally price to the response's
    cost: dividing a response's counts among rows commutes with bounding them
    by its prompt count."""
    reconstruct = _reconstruction()
    model = "claude-fable-5.2"
    request = reconstruct(
        model_name=model,
        model_id=MODELS[model],
        prompt_tokens=210_000,
        completion_tokens=21_000,
        cached_prompt_tokens=140_000,
        cache_write_prompt_tokens=35_000,
    )
    preds = pd.DataFrame(
        [_usage_row(model, "s1", 210_000 / 7, 3_000, 20_000, 5_000) for _ in range(7)]
    )
    out = model_cost_latency(preds, PRICE_OVERRIDES_PER_1M)
    assert out[model]["costUsd"] == pytest.approx(request.usd, rel=1e-12)


MODEL_NAMES = ("a", "b", "c", "gpt-6.1-sol")
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
        "cached_prompt_tokens": st.one_of(
            missing, st.integers(0, 6_000_000).map(float)
        ),
        "cache_write_prompt_tokens": st.one_of(
            missing, st.integers(0, 6_000_000).map(float)
        ),
        "elapsed_seconds": st.one_of(missing, st.floats(min_value=0, max_value=600)),
        # -1, 2 and 0.5 let a draw pair counts that only sum to one.
        "live_calls": st.one_of(missing, st.sampled_from([0.0, 1.0, 2.0, -1.0, 0.5])),
        "cache_hit_calls": st.one_of(missing, st.sampled_from([0.0, 1.0, 2.0, 0.5])),
    }
)
rate = st.floats(min_value=0, max_value=100, allow_subnormal=False)
price = st.fixed_dictionaries(
    {"input": rate, "output": rate},
    optional={"cache_read": rate, "cache_write": rate},
)


def _reference_cost(
    model: str, rows: list[dict], override: dict | None
) -> float | None:
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
    if override is None or not priced or model in GPT_RESPONSES_MODELS:
        return None
    prompt = math.fsum(r["prompt_tokens"] for r in priced)
    completion = math.fsum(r["completion_tokens"] for r in priced)
    if "cache_read" not in override and "cache_write" not in override:
        return prompt * override["input"] / 1e6 + completion * override["output"] / 1e6
    counts = ["cached_prompt_tokens", "live_calls", "cache_hit_calls"]
    if "cache_write" in override:
        counts.append("cache_write_prompt_tokens")
    if any(math.isnan(r[c]) for r in priced for c in counts) or any(
        (r["live_calls"], r["cache_hit_calls"]) not in {(1.0, 0.0), (0.0, 1.0)}
        for r in priced
    ):
        return None

    def written_count(row):
        if "cache_write" not in override:
            return 0.0
        return max(row["cache_write_prompt_tokens"], 0.0)

    cached = [
        min(max(r["cached_prompt_tokens"], 0.0), r["prompt_tokens"]) for r in priced
    ]
    written = [
        min(written_count(r), r["prompt_tokens"] - c) for r, c in zip(priced, cached)
    ]
    uncached = math.fsum(
        r["prompt_tokens"] - c - w for r, c, w in zip(priced, cached, written)
    )
    return (
        uncached * override["input"]
        + math.fsum(cached) * override.get("cache_read", override["input"])
        + math.fsum(written) * override.get("cache_write", override["input"])
        + completion * override["output"]
    ) / 1e6


@settings(max_examples=300, deadline=None)
@given(
    drawn=st.lists(usage_row, min_size=1, max_size=12),
    overrides=st.dictionaries(st.sampled_from(MODEL_NAMES), price, max_size=3),
    uncosted=st.sets(st.sampled_from(MODEL_NAMES)),
    untokened=st.sets(st.sampled_from(MODEL_NAMES)),
    single=st.sets(st.sampled_from(MODEL_NAMES)),
)
def test_cost_is_present_exactly_when_recorded_usage_supports_it(
    drawn, overrides, uncosted, untokened, single
):
    # Whole models with no recorded cost, or (like Fable 5) no token counts,
    # so the fill and the no-usage cases are drawn often; and whole models
    # whose rows each record one response and every cache count, so the
    # cache-rate fill is drawn often too.
    nan = float("nan")

    def recorded(value):
        return 0.0 if math.isnan(value) else value

    rows = [
        {
            **row,
            **({"total_cost_usd": nan} if row["model"] in uncosted else {}),
            **(
                {"prompt_tokens": nan, "completion_tokens": nan}
                if row["model"] in untokened
                else {}
            ),
            **(
                {
                    "live_calls": 1.0,
                    "cache_hit_calls": 0.0,
                    "cached_prompt_tokens": recorded(row["cached_prompt_tokens"]),
                    "cache_write_prompt_tokens": recorded(
                        row["cache_write_prompt_tokens"]
                    ),
                }
                if row["model"] in single
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
            model, [r for r in rows if r["model"] == model], overrides.get(model)
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


def _frozen_run() -> Path:
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    return SNAPSHOT_DIR / "runs" / manifest["source_run_labels"]["us"]


@pytest.fixture(scope="module")
def frozen_predictions():
    return pd.read_csv(
        _frozen_run() / "predictions.csv.gz",
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
            "cached_prompt_tokens",
            "cache_write_prompt_tokens",
        ],
        low_memory=False,
    )


@pytest.fixture(scope="module")
def frozen(frozen_predictions):
    run = _frozen_run()
    published = {row["model"]: row for row in read_run_payload(run)["modelStats"]}
    return model_cost_latency(frozen_predictions, PRICE_OVERRIDES_PER_1M), published


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


# The published board's models whose cost the override fills, and the costs
# the board publishes for them (paper/snapshot/20260501, 2026-11-20).
FROZEN_FILLED_COSTS = {
    "gemini-3.6-flash": 5.4831164999999995,
    "grok-build-0.1": 4.487201,
}


def test_frozen_filled_costs_are_the_published_ones(frozen, frozen_predictions):
    """Exactly two published models record no cost on any row and take the
    override's: their overrides list only input and output rates, so the
    fill prices every prompt token at the input rate, as it did when the
    board was published, and the figures do not move by a bit."""
    computed, published = frozen
    filled = sorted(
        model
        for model, rows in frozen_predictions.groupby("model")
        if rows["total_cost_usd"].isna().all()
        and model in PRICE_OVERRIDES_PER_1M
        and rows[["prompt_tokens", "completion_tokens"]].notna().all(axis=1).any()
    )
    assert filled == sorted(FROZEN_FILLED_COSTS)
    for model, cost in FROZEN_FILLED_COSTS.items():
        assert set(PRICE_OVERRIDES_PER_1M[model]) == {"input", "output"}
        assert model not in GPT_RESPONSES_MODELS
        assert published[model]["costUsd"] == cost
        assert computed[model]["costUsd"] == cost


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
