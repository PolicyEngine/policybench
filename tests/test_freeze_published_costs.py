"""The freeze needs a published cost for every board model.

analysis.model_cost_latency leaves costUsd out of a model's dashboard row when
no row of the model records a cost and the rows' usage cannot establish one
from its price override: a cache-rate model whose rows sum several responses
or lack a count, and a Responses-API GPT model. The freeze's report sums
every board model's cost, so freeze_snapshot.require_published_costs names
the models without one and stops, where the lookup used to raise
KeyError('costUsd').
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from policybench.analysis import model_cost_latency
from policybench.config import PRICE_OVERRIDES_PER_1M
from policybench.snapshot_payload import read_run_payload

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import freeze_snapshot as freezer  # noqa: E402


def _payload(*rows: dict) -> dict:
    return {"modelStats": list(rows)}


def _stat(model: str, condition: str = "no_tools", **fields) -> dict:
    return {"model": model, "condition": condition, **fields}


def test_a_board_model_without_a_cost_is_named():
    payload = _payload(
        _stat("costed", costUsd=1.0),
        _stat("no-key"),
        _stat("null", costUsd=None),
        _stat("nan", costUsd=math.nan),
        _stat("infinite", costUsd=math.inf),
        _stat("negative", costUsd=-1.0),
        _stat("true", costUsd=True),
        _stat("text", costUsd="1.0"),
        _stat("tools-arm", condition="with_tools"),
    )
    with pytest.raises(SystemExit) as refused:
        freezer.require_published_costs(payload)
    message = str(refused.value)
    # A cost the payload lacks and one it carries but cannot publish are
    # reported separately: the second is not a model no row costed.
    assert "no costUsd for no-key, null:" in message
    assert "zero or more, for infinite, nan, negative, text, true:" in message
    assert "tools-arm" not in message
    assert "costed" not in message


def test_a_recorded_negative_cost_is_not_reported_as_unrecorded():
    """Rows that record a cost of -1.0 give a dashboard row a costUsd of
    -1.0. The freeze refuses it as a cost it cannot publish, without saying
    that no row records one."""
    rows = _costless_rows("gemini-3.6-flash", live=1).assign(total_cost_usd=-0.5)
    entry = model_cost_latency(rows, PRICE_OVERRIDES_PER_1M)["gemini-3.6-flash"]
    assert entry["costUsd"] == -1.0
    with pytest.raises(SystemExit) as refused:
        freezer.require_published_costs(_payload(_stat("gemini-3.6-flash", **entry)))
    message = str(refused.value)
    assert "zero or more, for gemini-3.6-flash:" in message
    assert "no costUsd for" not in message


def test_a_zero_cost_is_a_cost_and_the_payload_order_is_kept():
    payload = _payload(
        _stat("zero-charge", costUsd=0),
        _stat("costed", costUsd=1.5),
        _stat("tools-arm", condition="with_tools", costUsd=9.0),
    )
    costs = freezer.require_published_costs(payload)
    assert costs == {"zero-charge": 0, "costed": 1.5}
    assert list(costs) == ["zero-charge", "costed"]


def test_the_committed_snapshot_has_a_cost_for_every_board_model():
    """The check changes nothing for the frozen board: the costs the report
    sums are the ones the payload carries, in its order."""
    payload = read_run_payload(freezer.RUN_DEST)
    board = [row for row in payload["modelStats"] if row["condition"] == "no_tools"]
    assert board
    costs = freezer.require_published_costs(payload)
    assert list(costs.items()) == [(row["model"], row["costUsd"]) for row in board]


def _costless_rows(model: str, live: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "model": model,
                "scenario_id": scenario,
                "variable": "v",
                "prediction": 1.0,
                "total_cost_usd": np.nan,
                "elapsed_seconds": 4.0,
                "prompt_tokens": 1_000.0,
                "completion_tokens": 200.0,
                "total_tokens": 1_200.0,
                "cached_prompt_tokens": 400.0,
                "cache_write_prompt_tokens": 0.0,
                "live_calls": live,
                "cache_hit_calls": 0,
            }
            for scenario in ("s1", "s2")
        ]
    )


@pytest.fixture
def staged_freeze(tmp_path, monkeypatch):
    """regenerate_analysis with the analyze CLI and its CSVs stubbed, reading
    its payload from a staged run directory. Returns a function that stages a
    payload and regenerates the analysis."""
    staged = tmp_path / "run"
    staged.mkdir()
    (staged / "reference_outputs.csv").write_text("scenario_id,variable,value\n")
    monkeypatch.setattr(freezer, "RUN_DEST", staged)
    monkeypatch.setattr(freezer.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        freezer.pd,
        "read_csv",
        lambda path, *args, **kwargs: pd.DataFrame(
            {
                "model": [],
                "bounded_score": [],
                "amount_accuracy": [],
                "participation_accuracy": [],
            }
        ),
    )
    monkeypatch.setattr(
        freezer,
        "render_markdown_report",
        lambda tables, *, published_model_costs: json.dumps(published_model_costs),
    )
    monkeypatch.setattr(
        freezer, "scored_reference_for", lambda path: (pd.DataFrame(), None)
    )
    monkeypatch.setattr(
        freezer,
        "household_impact_summary_by_model",
        lambda references, predictions: pd.DataFrame({"model": []}),
    )

    def regenerate(payload: dict) -> Path:
        (staged / "data.json").write_text(json.dumps(payload))
        freezer.regenerate_analysis(staged / "analysis")
        return staged / "analysis" / "report.md"

    return regenerate


def test_rows_the_fill_cannot_price_stop_the_report_by_name(staged_freeze):
    """Fable 5.2 rows with no recorded cost whose households each sum two
    responses: the cache-rate fill gives no cost, the dashboard row has no
    costUsd, and the freeze's report names the model instead of raising
    KeyError. The same rows with one response each are priced and reported."""
    model = "claude-fable-5.2"

    def stat(live: int) -> dict:
        entry = model_cost_latency(_costless_rows(model, live), PRICE_OVERRIDES_PER_1M)
        return _stat(model, **entry.get(model, {}))

    unpriced = stat(live=2)
    assert "costUsd" not in unpriced
    with pytest.raises(SystemExit, match=rf"no costUsd for {model}:"):
        staged_freeze(_payload(unpriced))

    priced = stat(live=1)
    report = staged_freeze(_payload(priced))
    assert json.loads(report.read_text()) == {model: priced["costUsd"]}
    assert priced["costUsd"] > 0
