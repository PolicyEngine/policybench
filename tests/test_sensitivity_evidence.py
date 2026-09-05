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

from policybench.reference_exclusions import scored_reference_for
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
    # Score against the same reference the board scores: excluded outputs out.
    ground_truth, _ = scored_reference_for(RUN_DIR / "reference_outputs.csv")
    payload = read_run_payload(RUN_DIR)
    weights_by_group: dict[str, float] = {}
    for variable, weight in payload["globalWeights"]["household"].items():
        group = output_group_id(variable)
        weights_by_group[group] = weights_by_group.get(group, 0.0) + weight
    # The summary's three scores are the app's exact, within-1% and bounded
    # ("continuous") fields on the scored reference.
    for field, key in (
        ("exact", "exact"),
        ("within1pct", "within1pct"),
        ("continuous", "score"),
    ):
        scores, _ = canonical_filtered_scores(
            ground_truth,
            predictions,
            weights_by_group,
            set(weights_by_group),
            "all",
            field,
        )
        assert round(scores[SUMMARY["sensitivity_model_id"]], 3) == round(
            SUMMARY["sensitivity"][key], 3
        ), field


def test_board_row_in_summary_matches_the_frozen_snapshot():
    payload = read_run_payload(RUN_DIR)
    row = next(m for m in payload["modelStats"] if m["model"] == SUMMARY["model"])
    assert round(row["exact"], 3) == SUMMARY["board"]["exact"]
    assert round(row["within1pct"], 3) == SUMMARY["board"]["within1pct"]
    assert round(row["score"], 3) == SUMMARY["board"]["score"]


AUGUST = json.loads((DATA / "claude-thinking-2026-08.json").read_text())


def _scored_inputs():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from sensitivity_by_variable import scored_inputs

    return scored_inputs(RUN_DIR)


def _by_variable_rates(predictions, reference, scenarios):
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from sensitivity_by_variable import by_variable_rates

    return by_variable_rates(predictions, reference, scenarios)


def _all_runs() -> list[tuple[str, str, dict]]:
    """(board model, asset stem, summary block) for the four thinking runs."""
    runs = [
        (
            SUMMARY["model"],
            "sensitivity-claude-fable-5-1-thinking",
            {"assets": SUMMARY["assets"], **SUMMARY},
        )
    ]
    for block in AUGUST["runs"].values():
        stem = next(
            name for name in block["assets"] if name.endswith("-predictions.csv.gz")
        ).removesuffix("-predictions.csv.gz")
        runs.append((block["model"], stem, block))
    return runs


def test_august_assets_match_their_pins():
    for block in AUGUST["runs"].values():
        for name, pin in block["assets"].items():
            path = DATA / name
            assert path.exists(), name
            assert path.stat().st_size == pin["bytes"], name
            assert hashlib.sha256(path.read_bytes()).hexdigest() == pin["sha256"], name


def test_august_scores_recompute_from_committed_predictions():
    reference, _ = _scored_inputs()
    payload = read_run_payload(RUN_DIR)
    weights_by_group: dict[str, float] = {}
    for variable, weight in payload["globalWeights"]["household"].items():
        group = output_group_id(variable)
        weights_by_group[group] = weights_by_group.get(group, 0.0) + weight
    board_by_model = {row["model"]: row for row in payload["modelStats"]}
    for model_id, block in AUGUST["runs"].items():
        stem = next(
            name for name in block["assets"] if name.endswith("-predictions.csv.gz")
        )
        with gzip.open(DATA / stem) as fileobj:
            predictions = pd.read_csv(
                fileobj, usecols=["model", "scenario_id", "variable", "prediction"]
            )
        assert set(predictions["model"]) == {model_id}
        for field, key in (
            ("exact", "exact"),
            ("within1pct", "within1pct"),
            ("continuous", "score"),
        ):
            scores, _ = canonical_filtered_scores(
                reference,
                predictions,
                weights_by_group,
                set(weights_by_group),
                "all",
                field,
            )
            assert round(scores[model_id], 3) == round(block["sensitivity"][key], 3), (
                model_id,
                field,
            )
        board = board_by_model[block["model"]]
        assert round(board["exact"], 3) == block["board"]["exact"]
        assert block["sensitivity"]["would_rank"] == _would_rank(
            block["sensitivity"]["exact"], payload["modelStats"]
        )


def test_by_variable_assets_recompute_on_the_scored_reference():
    """Every committed per-program asset equals the exporter's heatmap rows for
    the run against the scored reference (excluded outputs out of ``n``)."""
    reference, scenarios = _scored_inputs()
    for _, stem, _block in _all_runs():
        with gzip.open(DATA / f"{stem}-predictions.csv.gz") as fileobj:
            predictions = pd.read_csv(
                fileobj, usecols=["model", "scenario_id", "variable", "prediction"]
            )
        expected = _by_variable_rates(predictions, reference, scenarios)
        committed = pd.read_csv(DATA / f"{stem}-by-variable.csv.gz")
        pd.testing.assert_frame_equal(
            committed, expected, check_exact=False, atol=1e-9, check_dtype=False
        )
        assert committed.loc[committed["variable"] == "snap", "n"].item() == 97
        assert (
            committed.loc[
                committed["variable"] == "person_medicare_eligible", "n"
            ].item()
            == 172
        )


def _doc_program_table(text: str, header: str) -> dict[str, tuple[float, float, float]]:
    start = text.index(header)
    rows = {}
    for line in text[start:].split("\n")[2:]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows[cells[0]] = (float(cells[1]), float(cells[2]), float(cells[3]))
    return rows


def test_doc_program_tables_match_the_frozen_heatmap_and_assets():
    text = DOC.read_text()
    payload = read_run_payload(RUN_DIR)
    for board_model, header, stem in (
        (
            "claude-fable-5",
            "| program | board | auto | delta |",
            "sensitivity-claude-fable-5-thinking",
        ),
        (
            "claude-fable-5.1",
            "| program | board (JSON) | auto (tool declared) | delta |",
            "sensitivity-claude-fable-5-1-thinking",
        ),
    ):
        table = _doc_program_table(text, header)
        board = {
            row["variable"]: row["exact"]
            for row in payload["heatmap"]
            if row["model"] == board_model
        }
        asset = pd.read_csv(DATA / f"{stem}-by-variable.csv.gz").set_index("variable")
        assert set(table) == set(board) == set(asset.index)
        for variable, (board_rate, auto_rate, delta) in table.items():
            assert board_rate == round(board[variable], 1), (board_model, variable)
            assert auto_rate == round(float(asset.loc[variable, "exact"]), 1), (
                board_model,
                variable,
            )
            assert delta == round(auto_rate - board_rate, 1), (board_model, variable)
