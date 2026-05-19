"""Export full-run analysis and frontend payloads."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from policybench.analysis import (
    analyze_no_tools,
    build_dashboard_payload,
    build_scenario_prompt_map,
    export_analysis,
)
from policybench.annotation_taxonomy import (
    validate_failure_source,
    validate_failure_subtype,
)
from policybench.spec import get_output_ids, output_group_id


def _canonical_output_ids(country: str) -> set[str]:
    return set(get_output_ids(country, "headline"))


def _filter_to_canonical_outputs(frame: pd.DataFrame, country: str) -> pd.DataFrame:
    """Drop source-run rows outside the canonical headline output scope."""
    if frame.empty or "variable" not in frame.columns:
        return frame
    canonical = _canonical_output_ids(country)
    return frame[frame["variable"].map(output_group_id).isin(canonical)].reset_index(
        drop=True
    )


def load_predictions(country_dir: Path) -> pd.DataFrame:
    """Load a country run's predictions, preferring per-model CSVs when present."""
    by_model_dir = country_dir / "by_model"
    files = sorted(by_model_dir.glob("*.csv")) if by_model_dir.exists() else []
    predictions_path = country_dir / "predictions.csv"
    compressed_predictions_path = country_dir / "predictions.csv.gz"
    if files:
        predictions = pd.concat(
            (pd.read_csv(path) for path in files), ignore_index=True
        )
        predictions.to_csv(predictions_path, index=False)
        return predictions
    if predictions_path.exists():
        return pd.read_csv(predictions_path)
    if compressed_predictions_path.exists():
        return pd.read_csv(compressed_predictions_path)
    raise FileNotFoundError(
        f"Expected at least one CSV in {by_model_dir}, {predictions_path}, "
        f"or {compressed_predictions_path}."
    )


def load_annotations(country_dir: Path) -> pd.DataFrame:
    """Load optional prediction annotations for a country run."""
    country = country_dir.name
    annotations_dir = country_dir.parent / "annotations"
    committed_annotations_dir = Path("annotations") / country_dir.parent.name
    files = sorted(annotations_dir.glob(f"{country}_*_annotations.csv"))
    if not files:
        files = sorted(committed_annotations_dir.glob(f"{country}_*_annotations.csv"))
    annotation_columns = [
        "model",
        "scenario_id",
        "variable",
        "annotation",
        "failure_source",
        "failure_subtype",
    ]
    if not files:
        return pd.DataFrame(columns=annotation_columns)

    annotations = pd.concat((pd.read_csv(path) for path in files), ignore_index=True)
    required = set(annotation_columns)
    missing = required - set(annotations.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Annotation files missing columns: {missing_text}")

    annotations = annotations[annotation_columns].copy()
    annotations = annotations[
        annotations["annotation"].astype("string").fillna("").str.strip() != ""
    ]
    annotations["failure_source"] = annotations["failure_source"].map(
        validate_failure_source
    )
    annotations["failure_subtype"] = annotations["failure_subtype"].map(
        validate_failure_subtype
    )
    duplicate_keys = annotations.duplicated(
        ["model", "scenario_id", "variable"],
        keep=False,
    )
    if duplicate_keys.any():
        duplicates = annotations.loc[
            duplicate_keys, ["model", "scenario_id", "variable"]
        ].drop_duplicates()
        raise ValueError(
            "Duplicate annotations for prediction rows: "
            f"{duplicates.to_dict(orient='records')[:5]}"
        )
    return annotations


def load_case_annotations(country_dir: Path) -> pd.DataFrame:
    """Load optional grouped annotations for country scenario-output cases."""
    country = country_dir.name
    annotations_dir = country_dir.parent / "annotations"
    committed_annotations_dir = Path("annotations") / country_dir.parent.name
    files = sorted(annotations_dir.glob(f"{country}_case_notes.csv"))
    if not files:
        files = sorted(committed_annotations_dir.glob(f"{country}_case_notes.csv"))
    case_annotation_columns = [
        "scenario_id",
        "variable",
        "case_annotation",
        "case_failure_sources",
        "case_failure_subtypes",
    ]
    if not files:
        return pd.DataFrame(columns=case_annotation_columns)

    case_annotations = pd.concat(
        (pd.read_csv(path) for path in files),
        ignore_index=True,
    )
    required = set(case_annotation_columns)
    missing = required - set(case_annotations.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Case annotation files missing columns: {missing_text}")

    case_annotations = case_annotations[case_annotation_columns].copy()
    case_annotations = case_annotations[
        case_annotations["case_annotation"].astype("string").fillna("").str.strip()
        != ""
    ]
    duplicate_keys = case_annotations.duplicated(
        ["scenario_id", "variable"],
        keep=False,
    )
    if duplicate_keys.any():
        duplicates = case_annotations.loc[
            duplicate_keys, ["scenario_id", "variable"]
        ].drop_duplicates()
        raise ValueError(
            "Duplicate case annotations for scenario-output rows: "
            f"{duplicates.to_dict(orient='records')[:5]}"
        )
    return case_annotations


def load_case_reference_explanations(country_dir: Path) -> pd.DataFrame:
    """Load optional written 'reference computation' narratives for each case.

    These are agent-generated narratives describing how PolicyEngine derived
    the truth value for each ``(scenario_id, variable)`` case. The same text
    applies to every model on that case — it's about the reference, not the
    prediction.
    """
    country = country_dir.name
    annotations_dir = country_dir.parent / "annotations"
    committed_annotations_dir = Path("annotations") / country_dir.parent.name
    filename = f"{country}_case_reference_explanations.csv"
    files = sorted(annotations_dir.glob(filename))
    if not files:
        files = sorted(committed_annotations_dir.glob(filename))
    columns = ["scenario_id", "variable", "reference_explanation"]
    if not files:
        return pd.DataFrame(columns=columns)

    raw = pd.concat([pd.read_csv(path) for path in files], ignore_index=True)
    if "explanation" not in raw.columns:
        return pd.DataFrame(columns=columns)
    explanations = raw[["scenario_id", "variable", "explanation"]].rename(
        columns={"explanation": "reference_explanation"}
    )
    explanations = explanations[
        explanations["reference_explanation"].astype("string").fillna("").str.strip()
        != ""
    ]
    return explanations.drop_duplicates(["scenario_id", "variable"], keep="first")


def merge_case_reference_explanations(
    predictions: pd.DataFrame,
    explanations: pd.DataFrame,
) -> pd.DataFrame:
    """Attach the per-case reference-computation narrative to prediction rows."""
    if explanations.empty:
        return predictions
    if "reference_explanation" in predictions.columns:
        predictions = predictions.drop(columns=["reference_explanation"])
    return predictions.merge(explanations, on=["scenario_id", "variable"], how="left")


def merge_annotations(
    predictions: pd.DataFrame,
    annotations: pd.DataFrame,
) -> pd.DataFrame:
    """Attach optional audit annotations to prediction rows."""
    if annotations.empty:
        return predictions
    existing_columns = [
        column
        for column in ["annotation", "failure_source", "failure_subtype"]
        if column in predictions.columns
    ]
    if existing_columns:
        predictions = predictions.drop(columns=existing_columns)
    return predictions.merge(
        annotations,
        on=["model", "scenario_id", "variable"],
        how="left",
    )


def merge_case_annotations(
    predictions: pd.DataFrame,
    case_annotations: pd.DataFrame,
) -> pd.DataFrame:
    """Attach optional grouped audit annotations to prediction rows."""
    if case_annotations.empty:
        return predictions
    existing_columns = [
        column
        for column in [
            "case_annotation",
            "case_failure_sources",
            "case_failure_subtypes",
        ]
        if column in predictions.columns
    ]
    if existing_columns:
        predictions = predictions.drop(columns=existing_columns)
    return predictions.merge(
        case_annotations,
        on=["scenario_id", "variable"],
        how="left",
    )


def export_country(country_dir: Path) -> dict:
    """Write analysis artifacts and dashboard payload for one country run."""
    ground_truth_path = country_dir / "reference_outputs.csv"
    legacy_ground_truth_path = country_dir / "ground_truth.csv"
    scenarios_path = country_dir / "scenarios.csv"
    if not ground_truth_path.exists():
        if legacy_ground_truth_path.exists():
            ground_truth_path = legacy_ground_truth_path
        else:
            raise FileNotFoundError(f"Missing {ground_truth_path}.")
    if not scenarios_path.exists():
        raise FileNotFoundError(f"Missing {scenarios_path}.")

    ground_truth = pd.read_csv(ground_truth_path)
    predictions = load_predictions(country_dir)
    predictions = merge_annotations(predictions, load_annotations(country_dir))
    predictions = merge_case_annotations(
        predictions,
        load_case_annotations(country_dir),
    )
    predictions = merge_case_reference_explanations(
        predictions,
        load_case_reference_explanations(country_dir),
    )
    scenarios = pd.read_csv(scenarios_path)
    country = (
        str(scenarios["country"].dropna().iloc[0]).lower()
        if "country" in scenarios.columns and not scenarios["country"].dropna().empty
        else country_dir.name.lower().split("_", 1)[0]
    )
    ground_truth = _filter_to_canonical_outputs(ground_truth, country)
    predictions = _filter_to_canonical_outputs(predictions, country)

    analysis = analyze_no_tools(ground_truth, predictions, scenarios=scenarios)
    export_analysis(analysis, country_dir / "analysis")

    scenario_prompts = build_scenario_prompt_map(
        scenarios,
        ground_truth["variable"].drop_duplicates().tolist(),
    )
    payload = build_dashboard_payload(
        ground_truth,
        predictions,
        analysis,
        scenarios,
        scenario_prompts=scenario_prompts,
    )
    (country_dir / "data.json").write_text(json.dumps(payload), encoding="utf-8")
    return payload


def export_full_run(
    run_dir: str | Path,
    countries: Sequence[str] | None = None,
    app_data_output: str | Path = "app/src/data.json",
    skip_app_data: bool = False,
) -> dict:
    """Export per-country and combined frontend artifacts from a full run."""
    run_path = Path(run_dir)
    selected_countries = list(countries or ["us", "uk"])

    country_payloads = {
        country: export_country(run_path / country) for country in selected_countries
    }
    combined_payload = {"countries": country_payloads}

    run_payload_path = run_path / "data.json"
    run_payload_path.write_text(json.dumps(combined_payload), encoding="utf-8")
    print(f"Wrote {run_payload_path}")

    if not skip_app_data:
        app_data_path = Path(app_data_output)
        app_data_path.parent.mkdir(parents=True, exist_ok=True)
        app_data_path.write_text(json.dumps(combined_payload), encoding="utf-8")
        print(f"Wrote {app_data_path}")

    return combined_payload


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
        dest="countries",
        default=None,
        help="Country code to export. Repeat to export multiple countries.",
    )
    parser.add_argument(
        "--app-data-output",
        default="app/src/data.json",
        help="Path for the combined frontend payload.",
    )
    parser.add_argument(
        "--skip-app-data",
        action="store_true",
        help="Only write the combined payload under the run directory.",
    )
    args = parser.parse_args()

    export_full_run(
        run_dir=args.run_dir,
        countries=args.countries,
        app_data_output=args.app_data_output,
        skip_app_data=args.skip_app_data,
    )


if __name__ == "__main__":
    main()
