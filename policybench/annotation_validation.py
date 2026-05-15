"""Validate prediction-level audit annotation coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from policybench.analysis import score_single_prediction
from policybench.annotation_taxonomy import (
    validate_failure_source,
    validate_failure_subtype,
)
from policybench.full_run_export import (
    load_annotations,
    load_case_annotations,
    load_predictions,
)

FINAL_FAILURE_SOURCES = {"llm_error"}


def _expected_prediction_rows(
    reference: pd.DataFrame,
    predictions: pd.DataFrame,
) -> pd.DataFrame:
    """Return one row per model-scenario-variable target."""
    models = pd.DataFrame({"model": sorted(predictions["model"].dropna().unique())})
    expected = reference.assign(_join_key=1).merge(
        models.assign(_join_key=1),
        on="_join_key",
    )
    expected = expected.drop(columns="_join_key")
    return expected.merge(
        predictions[["model", "scenario_id", "variable", "prediction"]],
        on=["model", "scenario_id", "variable"],
        how="left",
    )


def wrong_prediction_rows_from_frames(
    reference: pd.DataFrame,
    predictions: pd.DataFrame,
) -> pd.DataFrame:
    """Return all model-target rows whose benchmark score is below full credit."""
    merged = _expected_prediction_rows(reference, predictions)
    merged["score"] = [
        score_single_prediction(variable, truth, prediction)
        for variable, truth, prediction in zip(
            merged["variable"],
            merged["value"],
            merged["prediction"],
            strict=True,
        )
    ]
    return merged.loc[
        merged["score"] < 1,
        ["model", "scenario_id", "variable", "value", "prediction", "score"],
    ].copy()


def wrong_prediction_rows(country_dir: Path) -> pd.DataFrame:
    """Return all prediction rows whose benchmark score is below full credit."""
    reference_path = country_dir / "reference_outputs.csv"
    if not reference_path.exists():
        reference_path = country_dir / "ground_truth.csv"
    reference = pd.read_csv(reference_path)
    predictions = load_predictions(country_dir)
    return wrong_prediction_rows_from_frames(reference, predictions)


def _missing_row_annotation_mask(frame: pd.DataFrame) -> pd.Series:
    return (
        (frame["annotation"].astype("string").fillna("").str.strip() == "")
        | (frame["failure_source"].astype("string").fillna("").str.strip() == "")
        | (frame["failure_subtype"].astype("string").fillna("").str.strip() == "")
    )


def missing_annotation_rows(
    wrong: pd.DataFrame,
    annotations: pd.DataFrame,
) -> pd.DataFrame:
    """Return wrong rows missing a row-level annotation or category."""
    annotated = wrong.merge(
        annotations[
            [
                "model",
                "scenario_id",
                "variable",
                "annotation",
                "failure_source",
                "failure_subtype",
            ]
        ],
        on=["model", "scenario_id", "variable"],
        how="left",
    )
    return annotated.loc[_missing_row_annotation_mask(annotated)].copy()


def unresolved_annotation_rows(
    wrong: pd.DataFrame,
    annotations: pd.DataFrame,
) -> pd.DataFrame:
    """Return annotated wrong rows not classified as final model/contract errors."""
    annotated = wrong.merge(
        annotations[
            [
                "model",
                "scenario_id",
                "variable",
                "annotation",
                "failure_source",
                "failure_subtype",
            ]
        ],
        on=["model", "scenario_id", "variable"],
        how="left",
    )
    complete = annotated.loc[~_missing_row_annotation_mask(annotated)].copy()
    return complete.loc[~complete["failure_source"].isin(FINAL_FAILURE_SOURCES)].copy()


def validate_annotation_coverage(country_dir: Path) -> pd.DataFrame:
    """Return wrong prediction rows missing an annotation."""
    wrong = wrong_prediction_rows(country_dir)
    annotations = load_annotations(country_dir)
    return missing_annotation_rows(wrong, annotations)


def validate_final_failure_sources(country_dir: Path) -> pd.DataFrame:
    """Return wrong rows whose annotation is not final enough for scoring claims."""
    wrong = wrong_prediction_rows(country_dir)
    annotations = load_annotations(country_dir)
    return unresolved_annotation_rows(wrong, annotations)


def validate_case_annotation_coverage(country_dir: Path) -> pd.DataFrame:
    """Return wrong scenario-output groups missing a case annotation."""
    wrong_cases = (
        wrong_prediction_rows(country_dir)[["scenario_id", "variable"]]
        .drop_duplicates()
        .copy()
    )
    case_annotations = load_case_annotations(country_dir)
    annotated = wrong_cases.merge(
        case_annotations[
            [
                "scenario_id",
                "variable",
                "case_annotation",
                "case_failure_sources",
                "case_failure_subtypes",
            ]
        ],
        on=["scenario_id", "variable"],
        how="left",
    )
    missing_annotation = (
        (annotated["case_annotation"].astype("string").fillna("").str.strip() == "")
        | (
            annotated["case_failure_sources"].astype("string").fillna("").str.strip()
            == ""
        )
        | (
            annotated["case_failure_subtypes"].astype("string").fillna("").str.strip()
            == ""
        )
    )
    return annotated.loc[missing_annotation].copy()


def _read_row_annotations(annotation_dir: Path, country: str) -> pd.DataFrame:
    files = sorted(annotation_dir.glob(f"{country}_*_annotations.csv"))
    if not files:
        raise FileNotFoundError(
            f"No row annotation files found for {country} in {annotation_dir}."
        )
    annotations = pd.concat((pd.read_csv(path) for path in files), ignore_index=True)
    annotations["failure_source"] = annotations["failure_source"].map(
        validate_failure_source
    )
    annotations["failure_subtype"] = annotations["failure_subtype"].map(
        validate_failure_subtype
    )
    return annotations


def _read_case_annotations(annotation_dir: Path, country: str) -> pd.DataFrame:
    path = annotation_dir / f"{country}_case_notes.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}.")
    return pd.read_csv(path)


def _snapshot_country_dir(snapshot_dir: Path, country: str) -> Path:
    manifest = json.loads((snapshot_dir / "manifest.json").read_text())
    run_label = manifest["source_run_labels"][country]
    run_dir = snapshot_dir / "runs" / run_label
    if not run_dir.exists():
        raise FileNotFoundError(f"Missing snapshot run directory: {run_dir}")
    return run_dir


def validate_snapshot_audit(
    *,
    snapshot_dir: Path,
    annotations_dir: Path,
    country: str,
) -> dict[str, pd.DataFrame]:
    """Validate row and case annotations against a frozen snapshot country."""
    country_dir = _snapshot_country_dir(snapshot_dir, country)
    reference = pd.read_csv(country_dir / "reference_outputs.csv")
    predictions = pd.read_csv(country_dir / "predictions.csv.gz")
    wrong = wrong_prediction_rows_from_frames(reference, predictions)
    annotations = _read_row_annotations(annotations_dir, country)
    case_annotations = _read_case_annotations(annotations_dir, country)

    wrong_cases = wrong[["scenario_id", "variable"]].drop_duplicates().copy()
    annotated_cases = wrong_cases.merge(
        case_annotations[
            [
                "scenario_id",
                "variable",
                "case_annotation",
                "case_failure_sources",
                "case_failure_subtypes",
            ]
        ],
        on=["scenario_id", "variable"],
        how="left",
    )
    missing_case_annotation = (
        (
            annotated_cases["case_annotation"].astype("string").fillna("").str.strip()
            == ""
        )
        | (
            annotated_cases["case_failure_sources"]
            .astype("string")
            .fillna("")
            .str.strip()
            == ""
        )
        | (
            annotated_cases["case_failure_subtypes"]
            .astype("string")
            .fillna("")
            .str.strip()
            == ""
        )
    )
    return {
        "wrong": wrong,
        "missing_rows": missing_annotation_rows(wrong, annotations),
        "unresolved_rows": unresolved_annotation_rows(wrong, annotations),
        "missing_cases": annotated_cases.loc[missing_case_annotation].copy(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        default=None,
        help="Full-run directory containing country subdirectories.",
    )
    parser.add_argument(
        "--snapshot-dir",
        default=None,
        help="Frozen snapshot directory containing manifest.json and runs/.",
    )
    parser.add_argument(
        "--annotations-dir",
        default=None,
        help="Explicit annotation directory for --snapshot-dir validation.",
    )
    parser.add_argument(
        "--country",
        action="append",
        default=None,
        help="Country code to validate. Repeat to validate multiple countries.",
    )
    args = parser.parse_args()

    countries = args.country or ["us", "uk"]
    missing_frames = []
    missing_case_frames = []
    unresolved_frames = []
    for country in countries:
        if args.snapshot_dir:
            if args.annotations_dir is None:
                raise SystemExit("--snapshot-dir requires --annotations-dir.")
            result = validate_snapshot_audit(
                snapshot_dir=Path(args.snapshot_dir),
                annotations_dir=Path(args.annotations_dir),
                country=country,
            )
            missing = result["missing_rows"]
            unresolved = result["unresolved_rows"]
            missing_cases = result["missing_cases"]
            print(f"{country}: {len(result['wrong'])} wrong prediction rows audited")
        else:
            if args.run_dir is None:
                raise SystemExit("Pass either --run-dir or --snapshot-dir.")
            country_dir = Path(args.run_dir) / country
            missing = validate_annotation_coverage(country_dir)
            unresolved = validate_final_failure_sources(country_dir)
            missing_cases = validate_case_annotation_coverage(country_dir)

        missing["country"] = country
        missing_frames.append(missing)
        unresolved["country"] = country
        unresolved_frames.append(unresolved)
        missing_cases["country"] = country
        missing_case_frames.append(missing_cases)
        print(f"{country}: {len(missing)} wrong prediction rows missing annotation")
        print(f"{country}: {len(unresolved)} wrong prediction rows unresolved")
        print(
            f"{country}: {len(missing_cases)} wrong scenario-output cases "
            "missing case annotation"
        )

    all_missing = pd.concat(missing_frames, ignore_index=True)
    all_unresolved = pd.concat(unresolved_frames, ignore_index=True)
    all_missing_cases = pd.concat(missing_case_frames, ignore_index=True)
    if not all_missing.empty or not all_unresolved.empty or not all_missing_cases.empty:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
