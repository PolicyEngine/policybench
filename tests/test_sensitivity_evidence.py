"""The Fable 5.1 thinking sensitivity claims are pinned to committed evidence.

``sensitivity/data/`` holds the run's predictions and per-variable rates with a
summary JSON; the doc's headline numbers must match the summary, the committed
files must match the summary's hashes, and the exact-match score must
recompute from the committed predictions against the frozen references and
weights.
"""

import gzip
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

from policybench.scorer_vectors import canonical_filtered_scores
from policybench.snapshot_payload import read_run_payload
from policybench.spec import output_group_id

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "sensitivity" / "data"
SUMMARY = json.loads((DATA / "claude-fable-5-1-thinking.json").read_text())
DOC = ROOT / "sensitivity" / "claude-thinking-2026-08.md"
SNAPSHOT_DIR = ROOT / "paper" / "snapshot" / "20260501"
RUN_DIR = SNAPSHOT_DIR / "runs" / "us_full_run_20260612_policyengine_4_16_1_populace"

SENSITIVITY_ROWS = {
    "Claude Fable 5": "claude-fable-5",
    "Claude Opus 5": "claude-opus-5",
    "Claude Sonnet 5": "claude-sonnet-5",
    "Claude Fable 5.1": "claude-fable-5.1",
}


def _would_rank(exact: float, rows: list[dict]) -> int:
    """Match app/src/lib/wouldRank.ts: 1 + rows with strictly higher exact."""
    return 1 + sum(
        (row["exact"] if row.get("exact") is not None else 0) > exact for row in rows
    )


def test_committed_assets_match_the_summary_pins():
    for name, pin in SUMMARY["assets"].items():
        path = DATA / name
        assert path.exists(), name
        assert path.stat().st_size == pin["bytes"], name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == pin["sha256"], name


def test_doc_table_row_matches_the_summary():
    text = DOC.read_text()
    board = SUMMARY["board"]["exact"]
    sens = SUMMARY["sensitivity"]["exact"]
    delta = SUMMARY["delta_exact"]
    pattern = (
        r"^\| Claude Fable 5\.1 \| ([\d.]+) \(#\d+\) \| "
        r"\*\*([\d.]+)\*\* \| \+([\d.]+) \|"
    )
    row = re.search(pattern, text, re.M)
    assert row, "Fable 5.1 sensitivity row missing from the doc"
    assert float(row.group(1)) == round(board, 1)
    assert float(row.group(2)) == round(sens, 1)
    assert float(row.group(3)) == round(delta, 1)
    assert (
        f"{SUMMARY['sensitivity']['n_parsed']:,}/{SUMMARY['sensitivity']['n']:,}"
        in text
    )


def test_doc_table_ranks_match_the_frozen_39_model_board():
    text = DOC.read_text()
    assert "on the 39-model board (2026-09-05)" in text
    rows = read_run_payload(RUN_DIR)["modelStats"]
    assert len(rows) == 39
    board_by_model = {row["model"]: row for row in rows}

    for label, model in SENSITIVITY_ROWS.items():
        pattern = (
            rf"^\| {re.escape(label)} \| [\d.]+ \(#(\d+)\) \| "
            rf"\*\*([\d.]+)\*\* \| [^|]+ \| \**#(\d+)\** \|"
        )
        match = re.search(pattern, text, re.M)
        assert match, f"{label} sensitivity row missing from the doc"
        board_rank, sensitivity_exact, would_rank = match.groups()
        assert int(board_rank) == _would_rank(board_by_model[model]["exact"], rows)
        assert int(would_rank) == _would_rank(float(sensitivity_exact), rows)

    assert SUMMARY["sensitivity"]["would_rank"] == _would_rank(
        SUMMARY["sensitivity"]["exact"], rows
    )


def test_exact_score_recomputes_from_committed_predictions():
    with gzip.open(
        DATA / "sensitivity-claude-fable-5-1-thinking-predictions.csv.gz"
    ) as fileobj:
        predictions = pd.read_csv(
            fileobj, usecols=["model", "scenario_id", "variable", "prediction"]
        )
    assert set(predictions["model"]) == {SUMMARY["sensitivity_model_id"]}
    assert len(predictions) == SUMMARY["sensitivity"]["n"]
    ground_truth = pd.read_csv(RUN_DIR / "reference_outputs.csv")
    payload = read_run_payload(RUN_DIR)
    weights_by_group: dict[str, float] = {}
    for variable, weight in payload["globalWeights"]["household"].items():
        group = output_group_id(variable)
        weights_by_group[group] = weights_by_group.get(group, 0.0) + weight
    scores, _ = canonical_filtered_scores(
        ground_truth,
        predictions,
        weights_by_group,
        set(weights_by_group),
        "all",
        "exact",
    )
    assert round(scores[SUMMARY["sensitivity_model_id"]], 1) == round(
        SUMMARY["sensitivity"]["exact"], 1
    )


def test_board_row_in_summary_matches_the_frozen_snapshot():
    payload = read_run_payload(RUN_DIR)
    row = next(m for m in payload["modelStats"] if m["model"] == SUMMARY["model"])
    assert round(row["exact"], 3) == SUMMARY["board"]["exact"]
    assert round(row["within1pct"], 3) == SUMMARY["board"]["within1pct"]
