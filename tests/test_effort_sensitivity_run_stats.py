"""scripts/effort_sensitivity.py run_stats on rows whose cost is not recorded.

model_cost_latency leaves out a cost it cannot establish, and the model when
it has neither a cost nor a latency; run_stats then reports null for those
fields, as the dashboard reports a cost as not recorded, rather than failing,
and --check-board counts a null figure as a mismatch.
"""

import importlib.util
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


def test_board_check_counts_an_unestablished_figure_as_a_mismatch(script):
    """--check-board compares each recomputed figure with the frozen one; a
    figure run_stats reports as null fails the check instead of raising."""
    assert script._close(1.0, 1.0 + 1e-12)
    assert not script._close(1.0, 1.0 + 1e-6)
    assert not script._close(None, 31.69)
    assert not script._close(31.69, None)
