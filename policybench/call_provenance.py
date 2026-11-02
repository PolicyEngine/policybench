"""Where each household's responses came from: provider calls or cache replays.

Prediction rows record ``live_calls``, ``cache_hit_calls`` and
``live_elapsed_seconds`` (``eval_no_tools.NO_TOOLS_CALL_PROVENANCE_COLUMNS``;
docs/runbook.md, "Call provenance"). This module reads them back per
household. It sits outside ``analysis.py`` because nothing published reads it:
``model_cost_latency`` still counts a replay's lookup time as a call (#228).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from policybench.eval_no_tools import NO_TOOLS_CALL_PROVENANCE_COLUMNS

HOUSEHOLD_CALL_STATUSES = (
    "live",
    "partial_replay",
    "full_replay",
    "no_response",
    "unknown",
)


def household_call_provenance(predictions: pd.DataFrame) -> pd.DataFrame:
    """Where each household's responses came from, by (model, scenario_id).

    ``status`` is ``live`` when the provider answered every response behind the
    household's rows, ``full_replay`` when the LiteLLM disk cache replayed
    every one, ``partial_replay`` for a mix, and ``no_response`` when no
    response reached any row. It is ``unknown`` when any row lacks the
    call-provenance columns, as every row written before they existed does.
    The test is per row, so it holds whether a household's rows share one
    request group (household runs) or each have their own (single-output runs,
    row repairs, batch chunks).

    ``live_elapsed_seconds`` sums the rows' live time, as the rows'
    ``elapsed_seconds`` sum to the household's latency: zero for a full
    replay, NaN when unknown or untimed (batch rows carry no time).
    """
    keys = ["model", "scenario_id"]
    if predictions.empty or not set(keys) <= set(predictions.columns):
        return pd.DataFrame(
            {
                "status": pd.Series(dtype=object),
                "live_elapsed_seconds": pd.Series(dtype=float),
            },
            index=pd.MultiIndex.from_tuples([], names=keys),
        )
    frame = predictions[keys].copy()
    for column in NO_TOOLS_CALL_PROVENANCE_COLUMNS:
        frame[column] = (
            pd.to_numeric(predictions[column], errors="coerce")
            if column in predictions.columns
            else np.nan
        )
    frame["known"] = frame["live_calls"].notna() & frame["cache_hit_calls"].notna()
    frame["any_live"] = frame["live_calls"].fillna(0) > 0
    frame["any_hit"] = frame["cache_hit_calls"].fillna(0) > 0
    grouped = frame.groupby(keys)
    flags = grouped.agg(
        known=("known", "all"),
        any_live=("any_live", "any"),
        any_hit=("any_hit", "any"),
    )
    status = np.select(
        [
            ~flags["known"],
            flags["any_live"] & flags["any_hit"],
            flags["any_hit"],
            flags["any_live"],
        ],
        ["unknown", "partial_replay", "full_replay", "live"],
        default="no_response",
    )
    live_elapsed = grouped["live_elapsed_seconds"].sum(min_count=1)
    return pd.DataFrame(
        {
            "status": pd.Series(status, index=flags.index, dtype=object),
            "live_elapsed_seconds": live_elapsed.where(flags["known"]),
        },
        index=flags.index,
    )
