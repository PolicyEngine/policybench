from pathlib import Path

import pandas as pd
import pytest

from policybench.fold_board import FoldError, fold_board


def predictions(model: str, n_scenarios: int, rows_per_scenario: int = 2):
    records = []
    for i in range(n_scenarios):
        for j in range(rows_per_scenario):
            records.append(
                {
                    "model": model,
                    "scenario_id": f"scenario_{i:03d}",
                    "variable": f"var_{j}",
                    "prediction": 1.0,
                }
            )
    return pd.DataFrame(records)


@pytest.fixture
def board(tmp_path: Path):
    base = pd.concat(
        [predictions("model-a", 3), predictions("model-b", 3)], ignore_index=True
    )
    base_path = tmp_path / "base.csv"
    base.to_csv(base_path, index=False)
    scoring = tmp_path / "scoring"
    scoring.mkdir()
    (scoring / "reference_outputs.csv").write_text("scenario_id\n")
    (scoring / "scenarios.csv").write_text("scenario_id\n")
    return base_path, scoring


def test_folds_complete_model(board, tmp_path):
    base_path, scoring = board
    add = tmp_path / "new.csv"
    predictions("model-c", 3).to_csv(add, index=False)
    result = fold_board(base_path, [add], scoring, tmp_path / "out", export=False)
    assert result["folded"] == ["model-c"]
    assert result["models"] == 3
    combined = pd.read_csv(tmp_path / "out" / "us" / "predictions.csv")
    assert combined.model.nunique() == 3
    assert (tmp_path / "out" / "by_model" / "model-c.csv").exists()
    assert (tmp_path / "out" / "us" / "reference_outputs.csv").exists()


def test_excludes_short_run(board, tmp_path):
    base_path, scoring = board
    add = tmp_path / "short.csv"
    predictions("model-c", 2).to_csv(add, index=False)
    result = fold_board(base_path, [add], scoring, tmp_path / "out", export=False)
    assert result["folded"] == []
    assert "4 rows (need 6)" in result["excluded"]["model-c"]
    assert result["models"] == 2


def test_excludes_duplicates_and_existing_model(board, tmp_path):
    base_path, scoring = board
    dupes = predictions("model-c", 3)
    dupes = pd.concat([dupes, dupes.iloc[:1]], ignore_index=True)
    dupes_path = tmp_path / "dupes.csv"
    dupes.to_csv(dupes_path, index=False)
    existing = tmp_path / "existing.csv"
    predictions("model-a", 3).to_csv(existing, index=False)
    result = fold_board(
        base_path, [dupes_path, existing], scoring, tmp_path / "out", export=False
    )
    assert result["folded"] == []
    assert "duplicate" in result["excluded"]["model-c"]
    assert "already on the base board" in result["excluded"]["model-a"]


def test_unbalanced_base_raises(board, tmp_path):
    base_path, scoring = board
    frame = pd.read_csv(base_path)
    frame = pd.concat([frame, frame.iloc[:1]], ignore_index=True)
    frame.to_csv(base_path, index=False)
    with pytest.raises(FoldError, match="unequal per-model row counts"):
        fold_board(base_path, [], scoring, tmp_path / "out", export=False)
