"""The car-loan interest audit's committed tables follow from the frozen snapshot
(reference_audit/2026-11-11-car-loan-interest)."""

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pytest

from policybench.analysis import (
    _country_from_scenarios,
    row_hit_scores,
    weighted_hit_rate_scores_by_model,
)
from policybench.full_run_export import _filter_to_canonical_outputs
from policybench.paper_results import moves_beyond_tolerance
from policybench.reference_exclusions import (
    exclusions_path_for,
    load_reference_exclusions,
    split_reference,
)
from policybench.snapshot_payload import read_run_payload

ROOT = Path(__file__).resolve().parents[1]
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace"
)
AUDIT = ROOT / "reference_audit/2026-11-11-car-loan-interest/verification"
KEY = ["scenario_id", "variable"]


@lru_cache(maxsize=1)
def _snapshot():
    """The frozen references, split as the export splits them, and the
    frozen predictions, filtered to the canonical outputs."""
    reference_path = RUN / "reference_outputs.csv"
    scenarios = pd.read_csv(RUN / "scenarios.csv")
    country = str(scenarios["country"].dropna().iloc[0]).lower()
    exclusions = load_reference_exclusions(exclusions_path_for(reference_path))
    reference = _filter_to_canonical_outputs(pd.read_csv(reference_path), country, None)
    predictions = _filter_to_canonical_outputs(
        pd.read_csv(
            RUN / "predictions.csv.gz",
            usecols=["model", "scenario_id", "variable", "prediction"],
            low_memory=False,
        ),
        country,
        None,
    )
    scored, _ = split_reference(reference, exclusions)
    market_income = dict(
        zip(
            scenarios["scenario_id"].astype(str),
            pd.to_numeric(scenarios["total_income"], errors="coerce").fillna(0.0),
        )
    )
    return scored, exclusions, predictions, market_income, scenarios


def _shares(ground_truth) -> pd.Series:
    _, _, predictions, market_income, scenarios = _snapshot()
    table = weighted_hit_rate_scores_by_model(
        ground_truth,
        predictions,
        market_income,
        country=_country_from_scenarios(scenarios),
    )
    return table.set_index("model")["weighted_exact"] * 100


def _ranks(shares: pd.Series) -> pd.Series:
    return shares.rank(ascending=False, method="min").astype(int)


def _boards() -> pd.DataFrame:
    return pd.read_csv(AUDIT / "scoreboards.csv").set_index("model")


def _moved() -> pd.DataFrame:
    return pd.read_csv(AUDIT / "moved_cells.csv")


def test_scoreboard_a_is_the_frozen_board():
    boards = _boards()
    frozen = pd.Series(
        {
            row["model"]: row["exact"]
            for row in read_run_payload(RUN)["modelStats"]
            if row["condition"] == "no_tools"
        }
    )
    assert sorted(boards.index) == sorted(frozen.index)
    for model, exact in frozen.items():
        assert boards.loc[model, "share_a"] == pytest.approx(exact, abs=1e-9), model
    assert (boards["rank_a"] == _ranks(frozen).reindex(boards.index)).all()


def test_moved_cells_are_the_engine_runs_moves_on_the_frozen_references():
    moved = _moved()
    computed = pd.read_csv(AUDIT / "computed.csv")
    moves = computed[
        [
            moves_beyond_tolerance(v, b, a)
            for v, b, a in zip(computed["variable"], computed["base"], computed["alt"])
        ]
    ]
    assert list(zip(moved["scenario_id"], moved["variable"])) == sorted(
        zip(moves["scenario_id"], moves["variable"])
    )
    joined = moved.merge(moves, on=KEY).merge(
        pd.read_csv(RUN / "reference_outputs.csv"), on=KEY
    )
    assert len(joined) == len(moved)
    assert (joined["engine_baseline"] == joined["base"]).all()
    assert (joined["alternative"] == joined["alt"]).all()
    assert (joined["reference"] == joined["value"]).all()
    assert joined["change"].tolist() == pytest.approx(
        (joined["alternative"] - joined["engine_baseline"]).tolist(), abs=1e-9
    )
    excluded = {(e["scenario_id"], e["variable"]) for e in _snapshot()[1]}
    assert joined["scored"].tolist() == [
        k not in excluded for k in zip(joined["scenario_id"], joined["variable"])
    ]
    # Every scored reference that moves is the engine's baseline to the cent.
    scored = joined[joined["scored"]]
    assert ((scored["reference"] - scored["engine_baseline"]).abs() < 0.005).all()


def test_scoreboards_b_and_c_follow_from_the_moved_cells():
    # Each board takes about 1.4 s to score on the release's host, so this
    # recomputes both for every model.
    scored = _snapshot()[0]
    moved = _moved()
    moved = moved[moved["scored"]]
    alternative = {
        (s, v): a
        for s, v, a in zip(
            moved["scenario_id"], moved["variable"], moved["alternative"]
        )
    }
    keys = list(zip(scored["scenario_id"], scored["variable"]))
    assert set(alternative) <= set(keys)
    board_b = scored.loc[[k not in alternative for k in keys]].reset_index(drop=True)
    board_c = scored.assign(
        value=[alternative.get(k, x) for k, x in zip(keys, scored["value"])]
    )
    boards = _boards()
    for name, ground_truth in (("b", board_b), ("c", board_c)):
        shares = _shares(ground_truth)
        assert sorted(shares.index) == sorted(boards.index)
        assert boards[f"share_{name}"].tolist() == pytest.approx(
            shares.reindex(boards.index).tolist(), abs=1e-9
        ), name
        assert (boards[f"rank_{name}"] == _ranks(shares).reindex(boards.index)).all()


def test_model_matches_follow_from_the_frozen_predictions():
    predictions = _snapshot()[2].set_index(["model", "scenario_id", "variable"])
    moved = _moved()
    moved = moved[moved["scored"]]
    matches = pd.read_csv(AUDIT / "model_matches.csv").set_index("model")
    for model, row in matches.iterrows():
        counts = {"reference": 0, "alternative": 0, "ref_only": 0, "alt_only": 0}
        for cell in moved.itertuples():
            pred = predictions["prediction"].get(
                (model, cell.scenario_id, cell.variable)
            )
            pred = None if pred is None or pd.isna(pred) else float(pred)
            ref = row_hit_scores(cell.variable, cell.reference, pred)["exact"]
            alt = row_hit_scores(cell.variable, cell.alternative, pred)["exact"]
            counts["reference"] += bool(ref)
            counts["alternative"] += bool(alt)
            counts["ref_only"] += bool(ref and not alt)
            counts["alt_only"] += bool(alt and not ref)
        assert (
            row["matches_reference"],
            row["matches_alternative"],
            row["reference_only"],
            row["alternative_only"],
        ) == tuple(counts.values()), model


def test_headline_facts_agree_with_the_tables():
    facts = json.loads((AUDIT / "headline.json").read_text())
    moved = _moved()
    households = pd.read_csv(AUDIT / "households.csv")
    scored, exclusions, *_ = _snapshot()
    assert facts["cells_moved"] == len(moved)
    assert facts["scored_cells_moved"] == int(moved["scored"].sum())
    assert facts["excluded_cells_moved"] == int((~moved["scored"]).sum())
    assert facts["scored_outputs_per_model"] == len(scored)
    assert facts["excluded_outputs"] == len(exclusions)
    assert facts["households_stating_auto_loan_interest_above_zero"] == int(
        (households["stated_auto_loan_interest"] > 0).sum()
    )
    boards = _boards()
    assert sorted(facts["models"]) == sorted(boards.index)
    for model, by_board in facts["models"].items():
        for name in ("a", "b", "c"):
            assert by_board[name] == {
                "share": round(float(boards.loc[model, f"share_{name}"]), 3),
                "rank": int(boards.loc[model, f"rank_{name}"]),
            }, (model, name)


def test_headline_counts():
    # The counts the audit's README and the release note state, as the
    # committed moved_cells.csv, scoreboards.csv and headline.json give them:
    # 15 outputs move beyond the tolerance, 11 scored and 4 the release
    # already excludes, on a board of 52 models.
    facts = json.loads((AUDIT / "headline.json").read_text())
    moved = _moved()
    assert facts["cells_moved"] == len(moved) == 15
    assert facts["scored_cells_moved"] == int(moved["scored"].sum()) == 11
    assert facts["excluded_cells_moved"] == int((~moved["scored"]).sum()) == 4
    assert len(facts["models"]) == len(_boards()) == 52
