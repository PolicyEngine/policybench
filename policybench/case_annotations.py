"""Generate grouped case-level audit notes for wrong predictions."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Sequence

import pandas as pd

from policybench.analysis import score_single_prediction
from policybench.annotation_taxonomy import infer_failure_category
from policybench.full_run_export import load_annotations, load_predictions
from policybench.spec import metric_type_for_output

THEME_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "missing parsed outputs",
        ("missing", "no parsed", "not parsed", "parse", "extraction", "repair"),
    ),
    (
        "taxable-income or deduction assumptions",
        ("deduction", "taxable", "allowance", "itemiz"),
    ),
    (
        "credit or phaseout treatment",
        ("credit", "eitc", "ctc", "refundable", "phaseout"),
    ),
    (
        "thresholds, brackets, or rates",
        ("threshold", "bracket", "rate", "fpl", "poverty", "taper"),
    ),
    (
        "categorical eligibility",
        ("eligible", "eligibility", "categorical"),
    ),
    (
        "asset or resource treatment",
        ("asset", "resource", "savings", "capital"),
    ),
    (
        "health coverage and premium assumptions",
        ("premium", "marketplace", "esi", "employer-sponsored", "coverage", "slcsp"),
    ),
    (
        "age or disability treatment",
        ("age", "disabled", "disability", "medicare", "pip"),
    ),
    (
        "annualization or period assumptions",
        ("annual", "weekly", "monthly"),
    ),
    (
        "payroll or employment tax base",
        ("payroll", "fica", "ni", "national insurance", "social security"),
    ),
    (
        "state or local policy rules",
        ("state", "local", "county", "nyc", "texas", "california"),
    ),
)


def _reference_path(country_dir: Path) -> Path:
    reference_path = country_dir / "reference_outputs.csv"
    if reference_path.exists():
        return reference_path
    legacy_reference_path = country_dir / "ground_truth.csv"
    if legacy_reference_path.exists():
        return legacy_reference_path
    raise FileNotFoundError(f"Missing {reference_path}.")


def _expected_prediction_rows(
    reference: pd.DataFrame,
    predictions: pd.DataFrame,
) -> pd.DataFrame:
    """Return one row per model-scenario-variable combination."""
    models = pd.DataFrame({"model": sorted(predictions["model"].dropna().unique())})
    expected = reference.assign(_join_key=1).merge(
        models.assign(_join_key=1),
        on="_join_key",
    )
    expected = expected.drop(columns="_join_key")

    prediction_columns = ["model", "scenario_id", "variable", "prediction"]
    optional_columns = [
        column for column in ["explanation", "error"] if column in predictions.columns
    ]
    prediction_details = predictions[prediction_columns + optional_columns].rename(
        columns={"error": "prediction_error"}
    )
    merged = expected.merge(
        prediction_details,
        on=["model", "scenario_id", "variable"],
        how="left",
    )
    if "explanation" not in merged.columns:
        merged["explanation"] = pd.NA
    if "prediction_error" not in merged.columns:
        merged["prediction_error"] = pd.NA
    return merged


def wrong_prediction_rows(country_dir: Path) -> pd.DataFrame:
    """Return all wrong prediction rows with row-level audit annotations."""
    reference = pd.read_csv(_reference_path(country_dir))
    predictions = load_predictions(country_dir)
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
    wrong = merged.loc[merged["score"] < 1].copy()
    annotations = load_annotations(country_dir)
    if not annotations.empty:
        wrong = wrong.merge(
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
    if "annotation" not in wrong.columns:
        wrong["annotation"] = pd.NA
    for column in ["failure_source", "failure_subtype"]:
        if column not in wrong.columns:
            wrong[column] = pd.NA
    missing_categories = (
        wrong["annotation"].astype("string").fillna("").str.strip() != ""
    ) & (
        (wrong["failure_source"].astype("string").fillna("").str.strip() == "")
        | (wrong["failure_subtype"].astype("string").fillna("").str.strip() == "")
    )
    if missing_categories.any():
        inferred = wrong.loc[missing_categories, "annotation"].map(
            infer_failure_category
        )
        wrong.loc[missing_categories, "failure_source"] = [
            category.failure_source for category in inferred
        ]
        wrong.loc[missing_categories, "failure_subtype"] = [
            category.failure_subtype for category in inferred
        ]
    return wrong


def _format_value(value: float, country: str, variable: str) -> str:
    if pd.isna(value):
        return "missing"
    if metric_type_for_output(variable) == "binary":
        return "Yes" if round(float(value)) == 1 else "No"
    if country == "us":
        return f"${float(value):,.2f}"
    return f"GBP {float(value):,.2f}"


def _direction_for_row(row: pd.Series) -> str:
    prediction = row["prediction"]
    if pd.isna(prediction):
        return "missing"
    if prediction > row["value"]:
        return "over"
    if prediction < row["value"]:
        return "under"
    return "outside tolerance"


def _direction_summary(group: pd.DataFrame) -> str:
    counts = Counter(_direction_for_row(row) for _, row in group.iterrows())
    order = ["over", "under", "missing", "outside tolerance"]
    parts = [f"{counts[label]} {label}" for label in order if counts[label]]
    return ", ".join(parts)


def _prediction_range(group: pd.DataFrame, country: str, variable: str) -> str:
    parsed = pd.to_numeric(group["prediction"], errors="coerce").dropna()
    if parsed.empty:
        return "no wrong row had a parsed numeric value"
    min_value = parsed.min()
    max_value = parsed.max()
    if min_value == max_value:
        return f"parsed wrong values were {_format_value(min_value, country, variable)}"
    return (
        "parsed wrong values ranged from "
        f"{_format_value(min_value, country, variable)} to "
        f"{_format_value(max_value, country, variable)}"
    )


def _top_themes(group: pd.DataFrame) -> str:
    texts = []
    if "annotation" in group.columns:
        texts.extend(group["annotation"].dropna().astype(str).str.lower().tolist())
    if not any(text.strip() for text in texts):
        for column in ["explanation", "prediction_error"]:
            if column in group.columns:
                texts.extend(
                    group[column].dropna().astype(str).str.lower().tolist(),
                )
    combined_text = "\n".join(texts)
    if not combined_text.strip():
        return "no common explanation pattern identified"

    counts: Counter[str] = Counter()
    for theme, keywords in THEME_KEYWORDS:
        counts[theme] = sum(combined_text.count(keyword) for keyword in keywords)

    themes = [theme for theme, count in counts.most_common(3) if count > 0]
    if not themes:
        return "no common explanation pattern identified"
    return "; ".join(themes)


def _case_annotation(
    group: pd.DataFrame,
    country: str,
    total_model_count: int,
) -> str:
    variable = str(group["variable"].iloc[0])
    truth = float(group["value"].iloc[0])
    wrong_count = len(group)
    missing_count = int(
        pd.to_numeric(group["prediction"], errors="coerce").isna().sum()
    )
    missing_label = "row" if missing_count == 1 else "rows"
    note = (
        f"Grouped audit: {wrong_count}/{total_model_count} models did not receive "
        f"full credit for this {variable} case. Wrong responses were "
        f"{_direction_summary(group)} "
        f"relative to the reference {_format_value(truth, country, variable)}; "
        f"{_prediction_range(group, country, variable)}. Common patterns: "
        f"{_top_themes(group)}."
    )
    if missing_count:
        note += f" {missing_count} wrong {missing_label} had no parsed value."
    return note


def _joined_unique_values(group: pd.DataFrame, column: str) -> str:
    values = sorted(
        {str(value).strip() for value in group[column].dropna() if str(value).strip()}
    )
    return ";".join(values)


def build_case_annotations(country_dir: Path) -> pd.DataFrame:
    """Build one grouped audit note per wrong scenario-output case."""
    country = country_dir.name
    wrong = wrong_prediction_rows(country_dir)
    predictions = load_predictions(country_dir)
    total_model_count = int(predictions["model"].dropna().nunique())
    rows = []
    for (scenario_id, variable), group in wrong.groupby(
        ["scenario_id", "variable"],
        sort=True,
    ):
        rows.append(
            {
                "country": country,
                "scenario_id": scenario_id,
                "variable": variable,
                "wrong_model_count": int(len(group)),
                "total_model_count": total_model_count,
                "case_failure_sources": _joined_unique_values(
                    group,
                    "failure_source",
                ),
                "case_failure_subtypes": _joined_unique_values(
                    group,
                    "failure_subtype",
                ),
                "case_annotation": _case_annotation(
                    group,
                    country,
                    total_model_count,
                ),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "country",
            "scenario_id",
            "variable",
            "wrong_model_count",
            "total_model_count",
            "case_failure_sources",
            "case_failure_subtypes",
            "case_annotation",
        ],
    )


def write_case_annotations(
    run_dir: str | Path,
    countries: Sequence[str] | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """Write case-note CSVs for a full run."""
    run_path = Path(run_dir)
    annotation_dir = Path(output_dir) if output_dir else run_path / "annotations"
    annotation_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for country in countries or ["us", "uk"]:
        case_annotations = build_case_annotations(run_path / country)
        output_path = annotation_dir / f"{country}_case_notes.csv"
        case_annotations.to_csv(output_path, index=False)
        written[country] = output_path
        print(f"Wrote {output_path} ({len(case_annotations)} rows)")
    return written


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
        help="Country code to annotate. Repeat to annotate multiple countries.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for generated case-note CSVs.",
    )
    args = parser.parse_args()

    write_case_annotations(
        run_dir=args.run_dir,
        countries=args.countries,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
