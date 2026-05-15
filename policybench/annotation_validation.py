"""Validate prediction-level audit annotation coverage."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from policybench.analysis import score_single_prediction
from policybench.full_run_export import (
    load_annotations,
    load_case_annotations,
    load_predictions,
)


def wrong_prediction_rows(country_dir: Path) -> pd.DataFrame:
    """Return all prediction rows whose benchmark score is below full credit."""
    reference_path = country_dir / "reference_outputs.csv"
    if not reference_path.exists():
        reference_path = country_dir / "ground_truth.csv"
    reference = pd.read_csv(reference_path)
    predictions = load_predictions(country_dir)
    merged = reference.merge(
        predictions,
        on=["scenario_id", "variable"],
        how="left",
    )
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


def validate_annotation_coverage(country_dir: Path) -> pd.DataFrame:
    """Return wrong prediction rows missing an annotation."""
    wrong = wrong_prediction_rows(country_dir)
    annotations = load_annotations(country_dir)
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
    missing_annotation = (
        (annotated["annotation"].astype("string").fillna("").str.strip() == "")
        | (annotated["failure_source"].astype("string").fillna("").str.strip() == "")
        | (annotated["failure_subtype"].astype("string").fillna("").str.strip() == "")
    )
    return annotated.loc[missing_annotation].copy()


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Full-run directory containing country subdirectories.",
    )
    parser.add_argument(
        "--country",
        action="append",
        default=None,
        help="Country code to validate. Repeat to validate multiple countries.",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    countries = args.country or ["us", "uk"]
    missing_frames = []
    missing_case_frames = []
    for country in countries:
        country_dir = run_dir / country
        missing = validate_annotation_coverage(country_dir)
        missing["country"] = country
        missing_frames.append(missing)
        print(f"{country}: {len(missing)} wrong prediction rows missing annotation")
        missing_cases = validate_case_annotation_coverage(country_dir)
        missing_cases["country"] = country
        missing_case_frames.append(missing_cases)
        print(
            f"{country}: {len(missing_cases)} wrong scenario-output cases "
            "missing case annotation"
        )

    all_missing = pd.concat(missing_frames, ignore_index=True)
    all_missing_cases = pd.concat(missing_case_frames, ignore_index=True)
    if not all_missing.empty or not all_missing_cases.empty:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
