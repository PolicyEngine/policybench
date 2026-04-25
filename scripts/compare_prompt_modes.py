"""Compare multi-output and single-output benchmark runs.

This script assumes both prediction files were generated from the same
ground-truth/scenario manifest and differ only in prompt mode.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from policybench.analysis import analyze_no_tools


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ground-truth", required=True)
    parser.add_argument("--multi-predictions", required=True)
    parser.add_argument("--single-predictions", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def _read_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def _write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _merge_with_delta(
    multi: pd.DataFrame,
    single: pd.DataFrame,
    keys: list[str],
    value_columns: list[str],
) -> pd.DataFrame:
    columns = keys + value_columns
    merged = multi[columns].merge(
        single[columns],
        on=keys,
        suffixes=("_multi", "_single"),
        how="outer",
    )
    for column in value_columns:
        merged[f"{column}_delta_single_minus_multi"] = (
            merged[f"{column}_single"] - merged[f"{column}_multi"]
        )
    return merged


def _model_comparison(
    multi_analysis: dict[str, pd.DataFrame],
    single_analysis: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    return _merge_with_delta(
        multi_analysis["model_summary"],
        single_analysis["model_summary"],
        keys=["model"],
        value_columns=[
            "mean_score",
            "mean_exact",
            "mean_within_1pct",
            "mean_within_5pct",
            "mean_within_10pct",
            "mean_accuracy",
            "mean_coverage",
            "total_n",
            "parsed_n",
        ],
    ).sort_values("mean_score_delta_single_minus_multi", ascending=False)


def _impact_comparison(
    multi_analysis: dict[str, pd.DataFrame],
    single_analysis: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    multi = multi_analysis.get("impact_summary", pd.DataFrame())
    single = single_analysis.get("impact_summary", pd.DataFrame())
    if multi.empty or single.empty:
        return pd.DataFrame()
    return _merge_with_delta(
        multi,
        single,
        keys=["model"],
        value_columns=[
            "mean_impact_score",
            "mean_household_score",
            "mean_household_coverage",
            "households",
            "total_variables",
            "parsed_variables",
        ],
    ).sort_values("mean_impact_score_delta_single_minus_multi", ascending=False)


def _variable_comparison(
    multi_analysis: dict[str, pd.DataFrame],
    single_analysis: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    return _merge_with_delta(
        multi_analysis["variable_summary"],
        single_analysis["variable_summary"],
        keys=["variable"],
        value_columns=[
            "mean_score",
            "mean_exact",
            "mean_within_1pct",
            "mean_within_5pct",
            "mean_within_10pct",
            "mean_accuracy",
            "mean_coverage",
            "total_n",
            "parsed_n",
        ],
    ).sort_values("mean_score_delta_single_minus_multi", ascending=False)


def _usage_comparison(
    multi_analysis: dict[str, pd.DataFrame],
    single_analysis: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    multi = multi_analysis.get("usage_summary", pd.DataFrame())
    single = single_analysis.get("usage_summary", pd.DataFrame())
    if multi.empty or single.empty:
        return pd.DataFrame()
    return _merge_with_delta(
        multi,
        single,
        keys=["model"],
        value_columns=[
            "total_rows",
            "parsed_rows",
            "error_rows",
            "total_cost_usd",
            "total_elapsed_seconds",
            "total_tokens",
            "reasoning_tokens",
        ],
    ).sort_values("total_cost_usd_delta_single_minus_multi", ascending=False)


def _format_cell(value) -> str:
    if pd.isna(value):
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    if frame.empty:
        return ""
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    rows = [
        "| "
        + " | ".join(_format_cell(row[column]) for column in columns)
        + " |"
        for _, row in frame[columns].iterrows()
    ]
    return "\n".join([header, separator, *rows])


def _render_report(
    model_comparison: pd.DataFrame,
    impact_comparison: pd.DataFrame,
    usage_comparison: pd.DataFrame,
) -> str:
    lines = [
        "# Prompt Mode Comparison",
        "",
        "Delta columns are `single_output - multi_output`.",
        "",
    ]
    if not model_comparison.empty:
        lines.extend(
            [
                "## Model Score Deltas",
                "",
                _markdown_table(
                    model_comparison,
                    [
                        "model",
                        "mean_score_multi",
                        "mean_score_single",
                        "mean_score_delta_single_minus_multi",
                        "mean_coverage_multi",
                        "mean_coverage_single",
                    ],
                ),
                "",
            ]
        )
    if not impact_comparison.empty:
        lines.extend(
            [
                "## Impact Score Deltas",
                "",
                _markdown_table(
                    impact_comparison,
                    [
                        "model",
                        "mean_impact_score_multi",
                        "mean_impact_score_single",
                        "mean_impact_score_delta_single_minus_multi",
                    ],
                ),
                "",
            ]
        )
    if not usage_comparison.empty:
        lines.extend(
            [
                "## Usage Deltas",
                "",
                _markdown_table(
                    usage_comparison,
                    [
                        "model",
                        "total_cost_usd_multi",
                        "total_cost_usd_single",
                        "total_cost_usd_delta_single_minus_multi",
                        "total_elapsed_seconds_multi",
                        "total_elapsed_seconds_single",
                    ],
                ),
                "",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ground_truth = _read_csv(args.ground_truth)
    multi_predictions = _read_csv(args.multi_predictions)
    single_predictions = _read_csv(args.single_predictions)

    multi_analysis = analyze_no_tools(ground_truth, multi_predictions)
    single_analysis = analyze_no_tools(ground_truth, single_predictions)

    model_comparison = _model_comparison(multi_analysis, single_analysis)
    impact_comparison = _impact_comparison(multi_analysis, single_analysis)
    variable_comparison = _variable_comparison(multi_analysis, single_analysis)
    usage_comparison = _usage_comparison(multi_analysis, single_analysis)

    _write_frame(model_comparison, output_dir / "model_comparison.csv")
    _write_frame(impact_comparison, output_dir / "impact_comparison.csv")
    _write_frame(variable_comparison, output_dir / "variable_comparison.csv")
    _write_frame(usage_comparison, output_dir / "usage_comparison.csv")
    (output_dir / "report.md").write_text(
        _render_report(model_comparison, impact_comparison, usage_comparison),
        encoding="utf-8",
    )

    print(f"Wrote prompt-mode comparison to {output_dir}")


if __name__ == "__main__":
    main()
