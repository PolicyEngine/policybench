from pathlib import Path

import pandas as pd

from policybench.full_run_export import (
    load_annotations,
    load_case_annotations,
    load_predictions,
    merge_case_annotations,
)


def _write_predictions(path: Path, model: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "model": model,
                "scenario_id": "s001",
                "variable": "income_tax",
                "prediction": 1,
            }
        ]
    ).to_csv(path, index=False)


def test_load_predictions_prefers_by_model_outputs(tmp_path: Path) -> None:
    country_dir = tmp_path / "us"
    _write_predictions(country_dir / "predictions.csv", "last_model_only")
    _write_predictions(country_dir / "by_model" / "model_a.csv", "model_a")
    _write_predictions(country_dir / "by_model" / "model_b.csv", "model_b")

    predictions = load_predictions(country_dir)

    assert sorted(predictions["model"]) == ["model_a", "model_b"]
    written = pd.read_csv(country_dir / "predictions.csv")
    assert sorted(written["model"]) == ["model_a", "model_b"]


def test_load_predictions_falls_back_to_root_predictions(tmp_path: Path) -> None:
    country_dir = tmp_path / "us"
    _write_predictions(country_dir / "predictions.csv", "combined")

    predictions = load_predictions(country_dir)

    assert predictions["model"].tolist() == ["combined"]


def test_load_predictions_reads_compressed_snapshot_predictions(
    tmp_path: Path,
) -> None:
    country_dir = tmp_path / "us"
    _write_predictions(country_dir / "predictions.csv.gz", "compressed")

    predictions = load_predictions(country_dir)

    assert predictions["model"].tolist() == ["compressed"]


def test_load_annotations_reads_run_annotations(tmp_path: Path) -> None:
    annotations_dir = tmp_path / "full_run" / "annotations"
    annotations_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "country": "us",
                "model": "model_a",
                "scenario_id": "s001",
                "variable": "income_tax",
                "annotation": "Wrong tax bracket.",
                "failure_source": "llm_error",
                "failure_subtype": "thresholds_rates",
            }
        ]
    ).to_csv(annotations_dir / "us_tax_annotations.csv", index=False)

    annotations = load_annotations(tmp_path / "full_run" / "us")

    assert annotations.to_dict(orient="records") == [
        {
            "model": "model_a",
            "scenario_id": "s001",
            "variable": "income_tax",
            "annotation": "Wrong tax bracket.",
            "failure_source": "llm_error",
            "failure_subtype": "thresholds_rates",
        }
    ]


def test_load_annotations_rejects_duplicate_prediction_keys(tmp_path: Path) -> None:
    annotations_dir = tmp_path / "full_run" / "annotations"
    annotations_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "model": "model_a",
                "scenario_id": "s001",
                "variable": "income_tax",
                "annotation": "First.",
                "failure_source": "llm_error",
                "failure_subtype": "thresholds_rates",
            },
            {
                "model": "model_a",
                "scenario_id": "s001",
                "variable": "income_tax",
                "annotation": "Duplicate.",
                "failure_source": "llm_error",
                "failure_subtype": "thresholds_rates",
            },
        ]
    ).to_csv(annotations_dir / "us_tax_annotations.csv", index=False)

    try:
        load_annotations(tmp_path / "full_run" / "us")
    except ValueError as error:
        assert "Duplicate annotations" in str(error)
    else:
        raise AssertionError("Expected duplicate annotations to fail")


def test_load_annotations_rejects_missing_failure_category(tmp_path: Path) -> None:
    annotations_dir = tmp_path / "full_run" / "annotations"
    annotations_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "model": "model_a",
                "scenario_id": "s001",
                "variable": "income_tax",
                "annotation": "Wrong tax bracket.",
            },
        ]
    ).to_csv(annotations_dir / "us_tax_annotations.csv", index=False)

    try:
        load_annotations(tmp_path / "full_run" / "us")
    except ValueError as error:
        assert "failure_source" in str(error)
        assert "failure_subtype" in str(error)
    else:
        raise AssertionError("Expected missing failure category to fail")


def test_load_case_annotations_reads_run_case_notes(tmp_path: Path) -> None:
    annotations_dir = tmp_path / "full_run" / "annotations"
    annotations_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "country": "us",
                "scenario_id": "s001",
                "variable": "income_tax",
                "case_annotation": "Two models used the wrong bracket.",
                "case_failure_sources": "llm_error",
                "case_failure_subtypes": "thresholds_rates",
            }
        ]
    ).to_csv(annotations_dir / "us_case_notes.csv", index=False)

    case_annotations = load_case_annotations(tmp_path / "full_run" / "us")

    assert case_annotations.to_dict(orient="records") == [
        {
            "scenario_id": "s001",
            "variable": "income_tax",
            "case_annotation": "Two models used the wrong bracket.",
            "case_failure_sources": "llm_error",
            "case_failure_subtypes": "thresholds_rates",
        }
    ]


def test_load_case_annotations_rejects_duplicate_case_keys(tmp_path: Path) -> None:
    annotations_dir = tmp_path / "full_run" / "annotations"
    annotations_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "scenario_id": "s001",
                "variable": "income_tax",
                "case_annotation": "First.",
                "case_failure_sources": "llm_error",
                "case_failure_subtypes": "thresholds_rates",
            },
            {
                "scenario_id": "s001",
                "variable": "income_tax",
                "case_annotation": "Duplicate.",
                "case_failure_sources": "llm_error",
                "case_failure_subtypes": "thresholds_rates",
            },
        ]
    ).to_csv(annotations_dir / "us_case_notes.csv", index=False)

    try:
        load_case_annotations(tmp_path / "full_run" / "us")
    except ValueError as error:
        assert "Duplicate case annotations" in str(error)
    else:
        raise AssertionError("Expected duplicate case annotations to fail")


def test_merge_case_annotations_attaches_notes_to_prediction_rows() -> None:
    predictions = pd.DataFrame(
        [
            {
                "model": "model_a",
                "scenario_id": "s001",
                "variable": "income_tax",
                "prediction": 100,
            }
        ]
    )
    case_annotations = pd.DataFrame(
        [
            {
                "scenario_id": "s001",
                "variable": "income_tax",
                "case_annotation": "Shared case note.",
                "case_failure_sources": "llm_error",
                "case_failure_subtypes": "thresholds_rates",
            }
        ]
    )

    merged = merge_case_annotations(predictions, case_annotations)

    assert merged["case_annotation"].tolist() == ["Shared case note."]
    assert merged["case_failure_sources"].tolist() == ["llm_error"]
    assert merged["case_failure_subtypes"].tolist() == ["thresholds_rates"]
