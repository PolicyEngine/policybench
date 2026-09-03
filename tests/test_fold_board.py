import json
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
    (scoring / "reference_outputs.csv.meta.json").write_text(
        json.dumps({"policyengine_bundles": {"us": {"model_version": "1.755.4"}}})
    )
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


def test_fold_preserves_new_addition_columns(board, tmp_path):
    base_path, scoring = board
    add = tmp_path / "new.csv"
    frame = predictions("model-c", 3)
    frame["cache_write_prompt_tokens"] = 12.5
    frame.to_csv(add, index=False)

    fold_board(base_path, [add], scoring, tmp_path / "out", export=False)

    combined = pd.read_csv(tmp_path / "out" / "us" / "predictions.csv")
    assert "cache_write_prompt_tokens" in combined
    assert (
        combined.loc[combined["model"] == "model-c", "cache_write_prompt_tokens"]
        .eq(12.5)
        .all()
    )
    assert (
        combined.loc[
            combined["model"].isin(["model-a", "model-b"]),
            "cache_write_prompt_tokens",
        ]
        .isna()
        .all()
    )


def test_excludes_short_run(board, tmp_path):
    base_path, scoring = board
    add = tmp_path / "short.csv"
    predictions("model-c", 2).to_csv(add, index=False)
    result = fold_board(base_path, [add], scoring, tmp_path / "out", export=False)
    assert result["folded"] == []
    assert "4 rows (need 6)" in result["excluded"]["model-c"]
    assert result["models"] == 2


def test_rejects_duplicate_rows(board, tmp_path):
    base_path, scoring = board
    dupes = predictions("model-c", 3)
    dupes = pd.concat([dupes, dupes.iloc[:1]], ignore_index=True)
    dupes_path = tmp_path / "dupes.csv"
    dupes.to_csv(dupes_path, index=False)

    with pytest.raises(FoldError, match="duplicate scenario/variable"):
        fold_board(base_path, [dupes_path], scoring, tmp_path / "out", export=False)


def test_rejects_existing_model(board, tmp_path):
    base_path, scoring = board
    existing = tmp_path / "existing.csv"
    predictions("model-a", 3).to_csv(existing, index=False)

    with pytest.raises(FoldError, match="already on the base board"):
        fold_board(base_path, [existing], scoring, tmp_path / "out", export=False)


def test_rejects_duplicate_model_additions(board, tmp_path):
    base_path, scoring = board
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    predictions("model-c", 3).to_csv(first, index=False)
    predictions("model-c", 3).to_csv(second, index=False)

    with pytest.raises(FoldError, match="duplicate model addition"):
        fold_board(
            base_path,
            [first, second],
            scoring,
            tmp_path / "out",
            export=False,
        )


def test_unbalanced_base_raises(board, tmp_path):
    base_path, scoring = board
    frame = pd.read_csv(base_path)
    extra = frame.iloc[:1].copy()
    extra["variable"] = "var_extra"
    frame = pd.concat([frame, extra], ignore_index=True)
    frame.to_csv(base_path, index=False)
    with pytest.raises(FoldError, match="unequal per-model row counts"):
        fold_board(base_path, [], scoring, tmp_path / "out", export=False)


def test_fold_copies_the_reference_sidecar(board, tmp_path):
    """The exporter reads reference_outputs.csv.meta.json for the payload's
    PolicyEngine provenance, so a folded board must carry it."""
    base_path, scoring = board
    add = tmp_path / "new.csv"
    predictions("model-c", 3).to_csv(add, index=False)
    fold_board(base_path, [add], scoring, tmp_path / "out", export=False)
    copied = tmp_path / "out" / "us" / "reference_outputs.csv.meta.json"
    assert copied.exists()
    assert json.loads(copied.read_text())["policyengine_bundles"]["us"] == {
        "model_version": "1.755.4"
    }


def test_export_refuses_a_scoring_source_without_the_sidecar(board, tmp_path):
    """Without the sidecar the export would fall back to the exporting
    machine's installed policyengine-us as the reference provenance."""
    base_path, scoring = board
    (scoring / "reference_outputs.csv.meta.json").unlink()
    add = tmp_path / "new.csv"
    predictions("model-c", 3).to_csv(add, index=False)
    with pytest.raises(ValueError, match="reference_outputs.csv.meta.json"):
        fold_board(base_path, [add], scoring, tmp_path / "out", export=True)


def test_reused_output_removes_stale_reference_sidecar_before_export(board, tmp_path):
    base_path, scoring = board
    (scoring / "reference_outputs.csv.meta.json").unlink()
    out_dir = tmp_path / "out"
    stale_sidecar = out_dir / "us" / "reference_outputs.csv.meta.json"
    stale_sidecar.parent.mkdir(parents=True)
    stale_sidecar.write_text(
        json.dumps({"policyengine_bundles": {"us": {"model_version": "stale"}}})
    )

    with pytest.raises(ValueError, match="Reference provenance sidecar is missing"):
        fold_board(base_path, [], scoring, out_dir, export=True)

    assert not stale_sidecar.exists()


def test_reused_output_replaces_reference_sidecar_from_source(board, tmp_path):
    base_path, scoring = board
    out_dir = tmp_path / "out"
    destination = out_dir / "us" / "reference_outputs.csv.meta.json"
    destination.parent.mkdir(parents=True)
    destination.write_text(
        json.dumps({"policyengine_bundles": {"us": {"model_version": "stale"}}})
    )
    source = scoring / "reference_outputs.csv.meta.json"
    source.write_text(
        json.dumps({"policyengine_bundles": {"us": {"model_version": "fresh"}}})
    )

    fold_board(base_path, [], scoring, out_dir, export=False)

    assert destination.read_bytes() == source.read_bytes()
