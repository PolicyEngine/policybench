"""The manuscript's row-level views score the same outputs as the board."""

import json
from pathlib import Path

from policybench.manuscript_views import (
    country_scores_from_rows,
    flatten_scored_predictions,
)
from policybench.reference_exclusions import exclusion_keys, load_reference_exclusions
from policybench.snapshot_payload import read_run_payload

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "paper" / "snapshot" / "20260501"


def _payload(excluded: bool) -> dict:
    def record(prediction: float, truth: float, scored: bool = True) -> dict:
        row = {"prediction": prediction, "groundTruth": truth}
        if not scored:
            row["scored"] = False
        return row

    return {
        "scenarioPredictions": {
            "scenario_001": {
                # Model a matches the frozen (excluded) reference; b does not.
                "ssi": {
                    "a": record(0.0, 0.0, scored=not excluded),
                    "b": record(11928.0, 0.0, scored=not excluded),
                },
                "snap": {"a": record(1200.0, 1200.0), "b": record(1200.0, 1200.0)},
            },
            "scenario_002": {
                "ssi": {"a": record(500.0, 500.0), "b": record(500.0, 500.0)},
            },
        }
    }


def test_excluded_rows_are_left_out_and_neither_help_nor_hurt():
    rows = flatten_scored_predictions("us", _payload(excluded=True))
    assert len(rows) == 4
    assert not (
        (rows["scenario_id"] == "scenario_001") & (rows["variable"] == "ssi")
    ).any()
    scores = country_scores_from_rows(rows).set_index("model")["score"]
    assert scores["a"] == scores["b"] == 100.0

    # Without the flag the same output is scored, and the miss counts against b.
    plain = flatten_scored_predictions("us", _payload(excluded=False))
    assert len(plain) == 6
    plain_scores = country_scores_from_rows(plain).set_index("model")["score"]
    assert plain_scores["a"] == 100.0 and plain_scores["b"] < 100.0


def test_frozen_payload_flattens_to_the_scored_universe():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    for country, run_label in manifest["source_run_labels"].items():
        run_dir = ROOT / manifest["source_run_artifacts"][run_label]["path"]
        payload = read_run_payload(run_dir)
        excluded = exclusion_keys(
            load_reference_exclusions(run_dir / "reference_exclusions.json")
        )
        rows = flatten_scored_predictions(country, payload)
        n_models = sum(1 for m in payload["modelStats"] if m["condition"] == "no_tools")
        scored_per_model = {m["n"] for m in payload["modelStats"]}
        assert scored_per_model == {len(rows) // n_models}
        assert len(rows) == n_models * next(iter(scored_per_model))
        keys = set(zip(rows["scenario_id"], rows["variable"]))
        assert not (keys & excluded)
