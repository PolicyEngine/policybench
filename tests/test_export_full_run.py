import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from policybench.case_annotations import wrong_prediction_rows
from policybench.full_run_export import (
    ReferenceProvenanceError,
    load_annotations,
    load_case_annotations,
    load_predictions,
    merge_annotations,
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


def test_merge_annotations_preserves_unannotated_budget_exhaustion() -> None:
    predictions = pd.DataFrame(
        [
            {
                "model": "model_a",
                "scenario_id": "s001",
                "variable": "income_tax",
                "failure_source": "budget_exhausted_at_ceiling",
            },
            {
                "model": "model_b",
                "scenario_id": "s001",
                "variable": "income_tax",
                "failure_source": None,
            },
        ]
    )
    annotations = pd.DataFrame(
        [
            {
                "model": "model_b",
                "scenario_id": "s001",
                "variable": "income_tax",
                "annotation": "Used the wrong bracket.",
                "failure_source": "llm_error",
                "failure_subtype": "thresholds_rates",
            }
        ]
    )

    merged = merge_annotations(predictions, annotations)

    assert merged.loc[merged["model"] == "model_a", "failure_source"].iloc[0] == (
        "budget_exhausted_at_ceiling"
    )


def test_merge_annotations_cannot_overwrite_recorded_budget_exhaustion() -> None:
    predictions = pd.DataFrame(
        [
            {
                "model": "model_a",
                "scenario_id": "s001",
                "variable": "income_tax",
                "failure_source": "budget_exhausted_at_ceiling",
            }
        ]
    )
    annotations = pd.DataFrame(
        [
            {
                "model": "model_a",
                "scenario_id": "s001",
                "variable": "income_tax",
                "annotation": "Stale parse annotation.",
                "failure_source": "parse_contract_failure",
                "failure_subtype": "missing_output",
            }
        ]
    )

    merged = merge_annotations(predictions, annotations)

    assert merged["failure_source"].tolist() == ["budget_exhausted_at_ceiling"]


def test_merge_annotations_cannot_invent_budget_exhaustion() -> None:
    predictions = pd.DataFrame(
        [
            {
                "model": "model_a",
                "scenario_id": "s001",
                "variable": "income_tax",
                "prediction": 100.0,
            },
            {
                "model": "model_b",
                "scenario_id": "s001",
                "variable": "income_tax",
                "prediction": None,
            },
        ]
    )
    annotations = pd.DataFrame(
        [
            {
                "model": model,
                "scenario_id": "s001",
                "variable": "income_tax",
                "annotation": "Incorrect reserved source.",
                "failure_source": "budget_exhausted_at_ceiling",
                "failure_subtype": "missing_output",
            }
            for model in ("model_a", "model_b")
        ]
    )

    merged = merge_annotations(predictions, annotations)

    assert merged["failure_source"].tolist() == [
        "llm_error",
        "parse_contract_failure",
    ]


def test_wrong_prediction_rows_keeps_recorded_budget_source_over_annotation(
    tmp_path: Path,
) -> None:
    country_dir = tmp_path / "full_run" / "us"
    country_dir.mkdir(parents=True)
    pd.DataFrame(
        [{"scenario_id": "s001", "variable": "income_tax", "value": 100.0}]
    ).to_csv(country_dir / "reference_outputs.csv", index=False)
    pd.DataFrame(
        [
            {
                "model": "model_a",
                "scenario_id": "s001",
                "variable": "income_tax",
                "prediction": None,
                "failure_source": "budget_exhausted_at_ceiling",
            }
        ]
    ).to_csv(country_dir / "predictions.csv", index=False)
    annotations_dir = country_dir.parent / "annotations"
    annotations_dir.mkdir()
    pd.DataFrame(
        [
            {
                "model": "model_a",
                "scenario_id": "s001",
                "variable": "income_tax",
                "annotation": "Stale parse annotation.",
                "failure_source": "parse_contract_failure",
                "failure_subtype": "missing_output",
            }
        ]
    ).to_csv(annotations_dir / "us_tax_annotations.csv", index=False)

    wrong = wrong_prediction_rows(country_dir)

    assert wrong["failure_source"].tolist() == ["budget_exhausted_at_ceiling"]


def test_wrong_prediction_rows_cannot_invent_budget_source(tmp_path: Path) -> None:
    country_dir = tmp_path / "full_run" / "us"
    country_dir.mkdir(parents=True)
    pd.DataFrame(
        [{"scenario_id": "s001", "variable": "income_tax", "value": 100.0}]
    ).to_csv(country_dir / "reference_outputs.csv", index=False)
    pd.DataFrame(
        [
            {
                "model": "model_a",
                "scenario_id": "s001",
                "variable": "income_tax",
                "prediction": 200.0,
            },
            {
                "model": "model_b",
                "scenario_id": "s001",
                "variable": "income_tax",
                "prediction": None,
            },
        ]
    ).to_csv(country_dir / "predictions.csv", index=False)
    annotations_dir = country_dir.parent / "annotations"
    annotations_dir.mkdir()
    pd.DataFrame(
        [
            {
                "model": model,
                "scenario_id": "s001",
                "variable": "income_tax",
                "annotation": "Incorrect reserved source.",
                "failure_source": "budget_exhausted_at_ceiling",
                "failure_subtype": "missing_output",
            }
            for model in ("model_a", "model_b")
        ]
    ).to_csv(annotations_dir / "us_tax_annotations.csv", index=False)

    wrong = wrong_prediction_rows(country_dir).sort_values("model")

    assert wrong["failure_source"].tolist() == [
        "llm_error",
        "parse_contract_failure",
    ]


def test_available_countries_detects_only_populated_dirs(tmp_path):
    from policybench.full_run_export import _available_countries

    (tmp_path / "us").mkdir()
    (tmp_path / "us" / "reference_outputs.csv").write_text("scenario_id\n")
    (tmp_path / "uk").mkdir()  # empty -> not a runnable country dir

    assert _available_countries(tmp_path) == ["us"]


def test_export_full_run_errors_clearly_when_no_country_dirs(tmp_path):
    import pytest

    from policybench.full_run_export import export_full_run

    with pytest.raises(FileNotFoundError, match="No country subdirectory"):
        export_full_run(tmp_path, skip_app_data=True)


def test_reference_policyengine_bundles_come_from_the_sidecar(tmp_path):
    """The payload's PolicyEngine provenance describes the references being
    scored, which the reference generator records beside them; the exporting
    machine's installed runtime is not evidence about them."""
    from policybench.full_run_export import reference_policyengine_bundles

    ground_truth = tmp_path / "reference_outputs.csv"
    ground_truth.write_text("scenario_id,variable,value\n")
    with pytest.raises(
        ReferenceProvenanceError,
        match="Reference provenance sidecar is missing",
    ):
        reference_policyengine_bundles(ground_truth, "us")

    sidecar = tmp_path / "reference_outputs.csv.meta.json"
    bundle = {
        "model_package": "policyengine-us",
        "model_version": "1.755.4",
        "data_package": "populace-data",
        "data_version": "0.1.0",
        "default_dataset": "populace_us_2024",
        "default_dataset_uri": (
            "hf://policyengine/populace-us/populace_us_2024.h5@build-id"
        ),
        "bundle_id": "us-4.16.1",
    }
    sidecar.write_text(
        json.dumps({"country": "us", "policyengine_bundles": {"us": bundle}})
    )
    assert reference_policyengine_bundles(ground_truth, "us") == {"us": bundle}
    with pytest.raises(
        ReferenceProvenanceError,
        match="country 'us', expected 'uk'",
    ):
        reference_policyengine_bundles(ground_truth, "uk")


def test_reference_policyengine_bundles_rejects_an_empty_bundle(tmp_path):
    from policybench.full_run_export import reference_policyengine_bundles

    ground_truth = tmp_path / "reference_outputs.csv"
    ground_truth.write_text("scenario_id,variable,value\n")
    sidecar = tmp_path / "reference_outputs.csv.meta.json"
    sidecar.write_text(
        json.dumps({"country": "us", "policyengine_bundles": {"us": {}}})
    )

    with pytest.raises(ReferenceProvenanceError) as exc_info:
        reference_policyengine_bundles(ground_truth, "us")

    message = str(exc_info.value)
    for field in (
        "model_package",
        "model_version",
        "data_package",
        "data_version",
        "default_dataset",
        "default_dataset_uri",
    ):
        assert field in message


def test_reference_policyengine_bundles_rejects_missing_model_version(tmp_path):
    from policybench.full_run_export import reference_policyengine_bundles

    ground_truth = tmp_path / "reference_outputs.csv"
    ground_truth.write_text("scenario_id,variable,value\n")
    sidecar = tmp_path / "reference_outputs.csv.meta.json"
    sidecar.write_text(
        json.dumps(
            {
                "country": "us",
                "policyengine_bundles": {
                    "us": {
                        "model_package": "policyengine-us",
                        "data_package": "populace-data",
                        "data_version": "0.1.0",
                        "default_dataset": "populace_us_2024",
                        "default_dataset_uri": "hf://example/dataset@revision",
                    }
                },
            }
        )
    )

    with pytest.raises(ReferenceProvenanceError, match="model_version"):
        reference_policyengine_bundles(ground_truth, "us")


def test_reference_policyengine_bundles_rejects_missing_dataset_identity(tmp_path):
    from policybench.full_run_export import reference_policyengine_bundles

    ground_truth = tmp_path / "reference_outputs.csv"
    ground_truth.write_text("scenario_id,variable,value\n")
    sidecar = tmp_path / "reference_outputs.csv.meta.json"
    sidecar.write_text(
        json.dumps(
            {
                "country": "us",
                "policyengine_bundles": {
                    "us": {
                        "model_package": "policyengine-us",
                        "model_version": "1.755.4",
                    }
                },
            }
        )
    )

    with pytest.raises(ReferenceProvenanceError) as exc_info:
        reference_policyengine_bundles(ground_truth, "us")

    message = str(exc_info.value)
    for field in (
        "data_package",
        "data_version",
        "default_dataset",
        "default_dataset_uri",
    ):
        assert field in message


def test_export_full_run_cli_fails_closed_without_reference_sidecar(
    tmp_path, monkeypatch
):
    from policybench.cli import main

    run_dir = tmp_path / "run"
    country_dir = run_dir / "us"
    country_dir.mkdir(parents=True)
    (country_dir / "reference_outputs.csv").write_text(
        "scenario_id,variable,value\ns001,income_tax,100\n"
    )
    (country_dir / "scenarios.csv").write_text("scenario_id,country\ns001,us\n")
    app_payload = tmp_path / "data.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "policybench",
            "export-full-run",
            "--run-dir",
            str(run_dir),
            "--app-data-output",
            str(app_payload),
        ],
    )

    with pytest.raises(SystemExit, match="Reference provenance sidecar is missing"):
        main()

    assert not (country_dir / "data.json").exists()
    assert not (run_dir / "data.json").exists()
    assert not app_payload.exists()
