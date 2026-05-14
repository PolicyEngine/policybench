"""Validate prediction-level audit annotation coverage."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from policybench.analysis import score_single_prediction
from policybench.full_run_export import load_annotations, load_predictions


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
        annotations[["model", "scenario_id", "variable", "annotation"]],
        on=["model", "scenario_id", "variable"],
        how="left",
    )
    missing_annotation = (
        annotated["annotation"].astype("string").fillna("").str.strip() == ""
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
    for country in countries:
        country_dir = run_dir / country
        missing = validate_annotation_coverage(country_dir)
        missing["country"] = country
        missing_frames.append(missing)
        print(f"{country}: {len(missing)} wrong prediction rows missing annotation")

    all_missing = pd.concat(missing_frames, ignore_index=True)
    if not all_missing.empty:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
