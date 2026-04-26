"""Tests for the full-run chunk orchestration helpers."""

import pandas as pd

from scripts.run_full_model_chunks import chunk_is_complete


def test_chunk_is_complete_requires_expected_rows_and_clean_predictions(tmp_path):
    path = tmp_path / "chunk.csv"
    pd.DataFrame(
        {
            "model": ["m", "m"],
            "scenario_id": ["s1", "s1"],
            "variable": ["income_tax", "eitc"],
            "prediction": [1.0, 2.0],
            "error": [None, None],
        }
    ).to_csv(path, index=False)

    assert chunk_is_complete(path, scenario_program_counts=[2])
    assert not chunk_is_complete(path, scenario_program_counts=[3])


def test_chunk_is_complete_rejects_error_rows(tmp_path):
    path = tmp_path / "chunk.csv"
    pd.DataFrame(
        {
            "model": ["m", "m"],
            "scenario_id": ["s1", "s1"],
            "variable": ["income_tax", "eitc"],
            "prediction": [1.0, None],
            "error": [None, "RateLimitError: insufficient_quota"],
        }
    ).to_csv(path, index=False)

    assert not chunk_is_complete(path, scenario_program_counts=[2])
