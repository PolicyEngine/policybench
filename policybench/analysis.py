"""Metrics and analysis for PolicyBench results."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from policybench.config import BINARY_PROGRAMS, RATE_PROGRAMS
from policybench.prompts import make_no_tools_batch_prompt
from policybench.scenarios import scenario_from_dict


def mean_absolute_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute mean absolute error."""
    return float(np.mean(np.abs(y_true - y_pred)))


def mean_absolute_percentage_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute MAPE, excluding zero ground truth values."""
    mask = y_true != 0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])))


def accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute accuracy for binary predictions."""
    # Round predictions to 0 or 1
    y_pred_binary = np.round(y_pred).astype(int)
    y_true_binary = np.round(y_true).astype(int)
    return float(np.mean(y_true_binary == y_pred_binary))


def exact_amount_match(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    absolute_tolerance: float = 1.0,
) -> float:
    """Fraction of amount predictions within an absolute tolerance."""
    return float(np.mean(np.abs(y_true - y_pred) <= absolute_tolerance))


def within_tolerance(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    tolerance: float = 0.10,
) -> float:
    """Fraction of predictions within tolerance of ground truth.

    For values where ground truth is 0, checks if prediction is also 0.
    """
    mask_nonzero = y_true != 0
    mask_zero = ~mask_nonzero

    correct = np.zeros(len(y_true), dtype=bool)

    # For nonzero ground truth: within relative tolerance
    if mask_nonzero.any():
        rel_error = np.abs(
            (y_true[mask_nonzero] - y_pred[mask_nonzero]) / y_true[mask_nonzero]
        )
        correct[mask_nonzero] = rel_error <= tolerance

    # For zero ground truth: prediction must be within absolute tolerance
    if mask_zero.any():
        correct[mask_zero] = np.abs(y_pred[mask_zero]) <= 1.0  # $1 tolerance

    return float(np.mean(correct))


def summarize_runs_by_model(
    ground_truth: pd.DataFrame,
    repeated_predictions: pd.DataFrame | None,
) -> pd.DataFrame:
    """Summarize each repeated run separately at the model level."""
    if (
        repeated_predictions is None
        or repeated_predictions.empty
        or "run_id" not in repeated_predictions.columns
    ):
        return pd.DataFrame()

    rows = []
    for run_id, run_predictions in repeated_predictions.groupby("run_id"):
        metrics = compute_metrics(ground_truth, run_predictions)
        summary = summary_by_model(metrics)
        if summary.empty:
            continue
        summary = summary.copy()
        summary.insert(0, "run_id", run_id)
        rows.append(summary)

    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def _std_or_nan(series: pd.Series) -> float:
    values = series.dropna()
    if len(values) <= 1:
        return float("nan")
    return float(values.std(ddof=1))


def run_stability_by_model(run_model_summary: pd.DataFrame) -> pd.DataFrame:
    """Aggregate repeated-run stability metrics by model."""
    if run_model_summary.empty:
        return pd.DataFrame()

    return (
        run_model_summary.groupby("model")
        .agg(
            run_count=("run_id", "nunique"),
            score_run_mean=("mean_score", "mean"),
            score_run_std=("mean_score", _std_or_nan),
            score_run_min=("mean_score", "min"),
            score_run_max=("mean_score", "max"),
            within10pct_run_mean=("mean_within_10pct", "mean"),
            within10pct_run_std=("mean_within_10pct", _std_or_nan),
            within10pct_run_min=("mean_within_10pct", "min"),
            within10pct_run_max=("mean_within_10pct", "max"),
            mae_run_mean=("mean_mae", "mean"),
            mae_run_std=("mean_mae", _std_or_nan),
            coverage_run_mean=("mean_coverage", "mean"),
            coverage_run_std=("mean_coverage", _std_or_nan),
            accuracy_run_mean=("mean_accuracy", "mean"),
            accuracy_run_std=("mean_accuracy", _std_or_nan),
        )
        .reset_index()
    )


def compute_metrics(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
) -> pd.DataFrame:
    """Compute metrics by model and variable.

    Args:
        ground_truth: DataFrame with columns [scenario_id, variable, value]
        predictions: DataFrame with columns [model, scenario_id, variable, prediction]

    Returns:
        DataFrame with bounded hit-rate scores plus diagnostic error metrics
    """
    merged = predictions.merge(
        ground_truth,
        on=["scenario_id", "variable"],
        how="inner",
    )

    rows = []
    for (model, variable), group in merged.groupby(["model", "variable"]):
        scored = group.dropna(subset=["prediction"])
        total_n = len(group)
        parsed_n = len(scored)
        coverage = parsed_n / total_n if total_n else float("nan")

        row = {
            "model": model,
            "variable": variable,
            "n": total_n,
            "n_parsed": parsed_n,
            "coverage": coverage,
        }

        if parsed_n == 0:
            row["mae"] = float("nan")
            row["mape"] = float("nan")
            if variable in BINARY_PROGRAMS:
                row["accuracy"] = 0.0
            else:
                row["accuracy"] = float("nan")
            row["exact"] = 0.0
            row["within_1pct"] = 0.0
            row["within_5pct"] = 0.0
            row["within_10pct"] = 0.0
            row["score"] = 0.0
            rows.append(row)
            continue

        y_true = scored["value"].values
        y_pred = scored["prediction"].values

        if variable in BINARY_PROGRAMS:
            accuracy_score = accuracy(y_true, y_pred) * coverage
            row["mae"] = mean_absolute_error(y_true, y_pred)
            row["mape"] = float("nan")
            row["accuracy"] = accuracy_score
            row["exact"] = accuracy_score
            row["within_1pct"] = accuracy_score
            row["within_5pct"] = accuracy_score
            row["within_10pct"] = accuracy_score
            row["score"] = accuracy_score
        elif variable in RATE_PROGRAMS:
            exact = (
                exact_amount_match(y_true, y_pred, absolute_tolerance=1e-4) * coverage
            )
            within_1pct = within_tolerance(y_true, y_pred, tolerance=0.01) * coverage
            within_5pct = within_tolerance(y_true, y_pred, tolerance=0.05) * coverage
            within_10pct = within_tolerance(y_true, y_pred, tolerance=0.10) * coverage
            row["mae"] = mean_absolute_error(y_true, y_pred)
            row["mape"] = float("nan")
            row["accuracy"] = float("nan")
            row["exact"] = exact
            row["within_1pct"] = within_1pct
            row["within_5pct"] = within_5pct
            row["within_10pct"] = within_10pct
            row["score"] = float(
                np.mean([exact, within_1pct, within_5pct, within_10pct])
            )
        else:
            exact = (
                exact_amount_match(y_true, y_pred, absolute_tolerance=1.0) * coverage
            )
            within_1pct = within_tolerance(y_true, y_pred, tolerance=0.01) * coverage
            within_5pct = within_tolerance(y_true, y_pred, tolerance=0.05) * coverage
            within_10pct = within_tolerance(y_true, y_pred, tolerance=0.10) * coverage
            row["mae"] = mean_absolute_error(y_true, y_pred)
            row["mape"] = mean_absolute_percentage_error(y_true, y_pred)
            row["accuracy"] = float("nan")
            row["exact"] = exact
            row["within_1pct"] = within_1pct
            row["within_5pct"] = within_5pct
            row["within_10pct"] = within_10pct
            row["score"] = float(
                np.mean([exact, within_1pct, within_5pct, within_10pct])
            )

        rows.append(row)

    return pd.DataFrame(rows)


def summary_by_model(metrics: pd.DataFrame) -> pd.DataFrame:
    """Aggregate metrics by model across all variables."""
    return (
        metrics.groupby("model")
        .agg(
            mean_score=("score", "mean"),
            mean_exact=("exact", "mean"),
            mean_within_1pct=("within_1pct", "mean"),
            mean_within_5pct=("within_5pct", "mean"),
            mean_mae=("mae", "mean"),
            mean_mape=("mape", "mean"),
            mean_within_10pct=("within_10pct", "mean"),
            mean_accuracy=("accuracy", "mean"),
            mean_coverage=("coverage", "mean"),
            total_n=("n", "sum"),
            parsed_n=("n_parsed", "sum"),
        )
        .reset_index()
    )


def summary_by_variable(metrics: pd.DataFrame) -> pd.DataFrame:
    """Aggregate metrics by variable across all models."""
    return (
        metrics.groupby("variable")
        .agg(
            mean_score=("score", "mean"),
            mean_exact=("exact", "mean"),
            mean_within_1pct=("within_1pct", "mean"),
            mean_within_5pct=("within_5pct", "mean"),
            mean_mae=("mae", "mean"),
            mean_mape=("mape", "mean"),
            mean_within_10pct=("within_10pct", "mean"),
            mean_accuracy=("accuracy", "mean"),
            mean_coverage=("coverage", "mean"),
            total_n=("n", "sum"),
            parsed_n=("n_parsed", "sum"),
        )
        .reset_index()
    )


def _sum_or_nan(series: pd.Series) -> float:
    values = series.dropna()
    if values.empty:
        return float("nan")
    return float(values.sum())


def usage_summary_by_model(predictions: pd.DataFrame) -> pd.DataFrame:
    """Aggregate cost, runtime, and token usage by model."""
    if predictions.empty or "model" not in predictions.columns:
        return pd.DataFrame()

    usage = predictions.copy()
    for column in (
        "error",
        "provider_reported_cost_usd",
        "reconstructed_cost_usd",
        "total_cost_usd",
        "cost_is_estimated",
        "estimated_cost_usd",
        "elapsed_seconds",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "reasoning_tokens",
        "cached_prompt_tokens",
    ):
        if column not in usage.columns and column == "error":
            usage[column] = None
        elif column not in usage.columns and column == "cost_is_estimated":
            usage[column] = False
        elif column not in usage.columns:
            usage[column] = float("nan")

    return (
        usage.groupby("model")
        .agg(
            total_rows=("variable", "size"),
            parsed_rows=("prediction", lambda s: int(s.notna().sum())),
            error_rows=("error", lambda s: int(s.notna().sum())),
            total_provider_reported_cost_usd=(
                "provider_reported_cost_usd",
                _sum_or_nan,
            ),
            total_reconstructed_cost_usd=("reconstructed_cost_usd", _sum_or_nan),
            total_cost_usd=("total_cost_usd", _sum_or_nan),
            estimated_cost_rows=(
                "cost_is_estimated",
                lambda s: int(s.fillna(False).sum()),
            ),
            total_estimated_cost_usd=("estimated_cost_usd", _sum_or_nan),
            total_elapsed_seconds=("elapsed_seconds", _sum_or_nan),
            prompt_tokens=("prompt_tokens", _sum_or_nan),
            completion_tokens=("completion_tokens", _sum_or_nan),
            total_tokens=("total_tokens", _sum_or_nan),
            reasoning_tokens=("reasoning_tokens", _sum_or_nan),
            cached_prompt_tokens=("cached_prompt_tokens", _sum_or_nan),
        )
        .reset_index()
    )


def analyze_no_tools(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
    repeated_predictions: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Build the standard no-tools analysis tables."""
    metrics = compute_metrics(ground_truth, predictions)
    model_summary = summary_by_model(metrics)
    run_model_summary = summarize_runs_by_model(ground_truth, repeated_predictions)
    run_stability = run_stability_by_model(run_model_summary)
    if not run_stability.empty:
        model_summary = model_summary.merge(run_stability, on="model", how="left")
    model_summary = model_summary.sort_values(
        "mean_score",
        ascending=False,
    )
    variable_summary = summary_by_variable(metrics).sort_values("variable")
    usage_summary = usage_summary_by_model(predictions).sort_values("model")
    return {
        "metrics": metrics,
        "model_summary": model_summary,
        "variable_summary": variable_summary,
        "usage_summary": usage_summary,
        "run_model_summary": run_model_summary,
        "run_stability": run_stability,
    }


def _format_metric(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value:.3f}"


def _format_seconds(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value / 60:.1f} min"


def render_markdown_report(analysis: dict[str, pd.DataFrame]) -> str:
    """Render a compact markdown report from analysis tables."""
    model_summary = analysis["model_summary"]
    variable_summary = analysis["variable_summary"]
    usage_summary = analysis.get("usage_summary", pd.DataFrame())
    run_stability = analysis.get("run_stability", pd.DataFrame())

    lines = [
        "# PolicyBench Analysis",
        "",
        "This report is generated by `policybench analyze` "
        "from no-tools benchmark results.",
        "",
    ]

    if not model_summary.empty:
        top_model = model_summary.iloc[0]
        lines.extend(
            [
                "## Headline",
                "",
                (
                    f"Top model: `{top_model['model']}` with "
                    f"`mean_score={_format_metric(top_model['mean_score'])}` "
                    f"`mean_exact={_format_metric(top_model['mean_exact'])}` "
                    f"and `mean_mae={_format_metric(top_model['mean_mae'])}`."
                ),
                "",
            ]
        )
        if (
            "run_count" in top_model.index
            and not pd.isna(top_model.get("run_count"))
            and top_model.get("run_count", 0) > 1
            and "score_run_mean" in top_model.index
        ):
            lines.extend(
                [
                    (
                        f"Across `{int(top_model['run_count'])}` "
                        "repeated runs on the fixed "
                        "scenario set, this model averaged "
                        f"`{_format_metric(top_model['score_run_mean'])}` "
                        "headline score"
                        + (
                            " with run-to-run std "
                            f"`{_format_metric(top_model['score_run_std'])}`."
                            if not pd.isna(top_model.get("score_run_std"))
                            else "."
                        )
                    ),
                    "",
                ]
            )

    if not usage_summary.empty:
        total_cost = _sum_or_nan(usage_summary["total_cost_usd"])
        total_runtime = _sum_or_nan(usage_summary["total_elapsed_seconds"])
        lines.extend(
            [
                "## Usage",
                "",
                (
                    f"Total cost: `{_format_metric(total_cost)}` USD. "
                    f"Estimated total runtime: `{_format_seconds(total_runtime)}`."
                ),
                "",
                "| model | total_cost_usd | cost_rows_estimated "
                "| total_elapsed | total_tokens "
                "| reasoning_tokens | parsed_rows | total_rows |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for _, row in usage_summary.iterrows():
            lines.append(
                "| "
                f"{row['model']} | "
                f"{_format_metric(row['total_cost_usd'])} | "
                f"{int(row['estimated_cost_rows'])} | "
                f"{_format_seconds(row['total_elapsed_seconds'])} | "
                f"{_format_metric(row['total_tokens'])} | "
                f"{_format_metric(row['reasoning_tokens'])} | "
                f"{int(row['parsed_rows'])} | "
                f"{int(row['total_rows'])} |"
            )
        lines.append("")

    if not run_stability.empty:
        lines.extend(
            [
                "## Run stability",
                "",
                "Repeated runs on the same fixed household set, summarized by model.",
                "",
                "| model | run_count | score_run_mean "
                "| score_run_std | score_run_min "
                "| score_run_max | mae_run_mean "
                "| mae_run_std |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for _, row in run_stability.sort_values(
            "score_run_mean",
            ascending=False,
        ).iterrows():
            lines.append(
                "| "
                f"{row['model']} | "
                f"{int(row['run_count'])} | "
                f"{_format_metric(row['score_run_mean'])} | "
                f"{_format_metric(row['score_run_std'])} | "
                f"{_format_metric(row['score_run_min'])} | "
                f"{_format_metric(row['score_run_max'])} | "
                f"{_format_metric(row['mae_run_mean'])} | "
                f"{_format_metric(row['mae_run_std'])} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Summary by model",
            "",
            "| model | mean_score | mean_exact "
            "| mean_within_1pct | mean_within_5pct "
            "| mean_within_10pct | mean_mae | total_n |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in model_summary.iterrows():
        lines.append(
            "| "
            f"{row['model']} | "
            f"{_format_metric(row['mean_score'])} | "
            f"{_format_metric(row['mean_exact'])} | "
            f"{_format_metric(row['mean_within_1pct'])} | "
            f"{_format_metric(row['mean_within_5pct'])} | "
            f"{_format_metric(row['mean_within_10pct'])} | "
            f"{_format_metric(row['mean_mae'])} | "
            f"{int(row['total_n'])} |"
        )

    lines.extend(
        [
            "",
            "## Summary by variable",
            "",
            "| variable | mean_score | mean_exact "
            "| mean_within_1pct | mean_within_5pct "
            "| mean_within_10pct | mean_mae | total_n |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in variable_summary.iterrows():
        lines.append(
            "| "
            f"{row['variable']} | "
            f"{_format_metric(row['mean_score'])} | "
            f"{_format_metric(row['mean_exact'])} | "
            f"{_format_metric(row['mean_within_1pct'])} | "
            f"{_format_metric(row['mean_within_5pct'])} | "
            f"{_format_metric(row['mean_within_10pct'])} | "
            f"{_format_metric(row['mean_mae'])} | "
            f"{int(row['total_n'])} |"
        )

    lines.append("")
    return "\n".join(lines)


def _clean_json_number(value):
    if pd.isna(value):
        return None
    return float(value)


def _clean_json_text(value):
    if pd.isna(value):
        return None
    return str(value)


def _scenario_feature_frame(scenarios: pd.DataFrame) -> pd.DataFrame:
    """Build scenario-level feature slices for failure-mode analysis."""

    def _numeric_value(value):
        if isinstance(value, bool):
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if np.isnan(numeric):
            return None
        return numeric

    rows = []
    for _, row in scenarios.iterrows():
        scenario_id = row["scenario_id"]
        country = row.get("country", "us")
        state = row.get("state")
        filing_status = row.get("filing_status")
        num_children = int(row.get("num_children", 0))
        total_income = float(row.get("total_income", 0.0))
        feature_row = {
            "scenario_id": scenario_id,
            "state": state,
            "filing_status": filing_status,
            "num_children": num_children,
            "has_children": int(num_children > 0),
            "total_income": total_income,
            "low_income": int(total_income <= 30_000),
            "high_income": int(total_income >= 100_000),
            "no_income_tax_state": int(
                country == "us"
                and state in {"AK", "FL", "NV", "SD", "TN", "TX", "WA", "WY", "NH"}
            ),
            "elderly_adult": 0,
            "any_disabled": 0,
            "has_retirement_income": 0,
            "has_capital_income": 0,
            "wage_only": 1,
        }

        scenario_json = row.get("scenario_json")
        if isinstance(scenario_json, str) and scenario_json:
            scenario = json.loads(scenario_json)
            adults = scenario.get("adults", [])
            children = scenario.get("children", [])
            people = adults + children

            adult_ages = [int(person.get("age", 0)) for person in adults]
            retirement_income = 0.0
            capital_income = 0.0
            non_wage_income = 0.0
            any_disabled = False

            for person in people:
                inputs = person.get("inputs", {})
                any_disabled = any_disabled or bool(
                    inputs.get("is_disabled") or inputs.get("is_disabled_for_benefits")
                )
                retirement_income += sum(
                    _numeric_value(inputs.get(key)) or 0.0
                    for key in (
                        "social_security_retirement",
                        "taxable_ira_distributions",
                        "taxable_private_pension_income",
                        "state_pension_reported",
                        "private_pension_income",
                    )
                )
                capital_income += sum(
                    _numeric_value(inputs.get(key)) or 0.0
                    for key in (
                        "taxable_interest_income",
                        "qualified_dividend_income",
                        "short_term_capital_gains",
                        "long_term_capital_gains",
                        "savings_interest_income",
                        "dividend_income",
                        "capital_gains_before_response",
                        "property_income",
                    )
                )
                for key, value in inputs.items():
                    if key in {
                        "weekly_hours_worked",
                        "hours_worked",
                        "is_disabled",
                        "is_disabled_for_benefits",
                        "is_blind",
                        "is_full_time_college_student",
                        "is_student",
                        "gender",
                        "marital_status",
                        "pip_dl_category",
                        "pip_m_category",
                    }:
                        continue
                    numeric_value = _numeric_value(value)
                    if numeric_value is not None:
                        non_wage_income += numeric_value

            feature_row.update(
                {
                    "elderly_adult": int(any(age >= 65 for age in adult_ages)),
                    "any_disabled": int(any_disabled),
                    "has_retirement_income": int(abs(retirement_income) > 1e-6),
                    "has_capital_income": int(abs(capital_income) > 1e-6),
                    "wage_only": int(abs(non_wage_income) <= 1e-6),
                }
            )

        rows.append(feature_row)

    return pd.DataFrame(rows)


def _row_is_correct(row: pd.Series) -> bool:
    if row["variable"] in BINARY_PROGRAMS:
        return bool(round(row["prediction"]) == round(row["value"]))
    if row["value"] == 0:
        return bool(abs(row["prediction"]) <= 1.0)
    return bool(abs(row["prediction"] - row["value"]) / abs(row["value"]) <= 0.10)


def build_failure_modes_payload(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
    scenarios: pd.DataFrame,
) -> dict[str, list[dict] | dict]:
    """Build structured failure-mode slices for the frontend."""
    features = _scenario_feature_frame(scenarios)
    merged = predictions.merge(
        ground_truth,
        on=["scenario_id", "variable"],
        how="inner",
    ).dropna(subset=["prediction"])
    merged = merged.merge(features, on="scenario_id", how="left")
    merged["correct"] = merged.apply(_row_is_correct, axis=1)
    merged["positive_truth"] = merged["value"] > 0
    merged["zero_truth"] = merged["value"] == 0
    merged["underpredict_positive"] = np.where(
        (~merged["variable"].isin(BINARY_PROGRAMS)) & merged["positive_truth"],
        merged["prediction"] < merged["value"],
        np.nan,
    )
    merged["nonzero_prediction_on_zero"] = np.where(
        (~merged["variable"].isin(BINARY_PROGRAMS)) & merged["zero_truth"],
        merged["prediction"].abs() > 1.0,
        np.nan,
    )

    program_slices = []
    for variable, group in merged.groupby("variable"):
        item: dict[str, float | int | str | bool | None] = {
            "variable": variable,
            "isBinary": variable in BINARY_PROGRAMS,
            "overallCorrectPct": float(group["correct"].mean() * 100),
            "withChildrenPct": float(
                group.loc[group["has_children"] == 1, "correct"].mean() * 100
            )
            if (group["has_children"] == 1).any()
            else None,
            "withoutChildrenPct": float(
                group.loc[group["has_children"] == 0, "correct"].mean() * 100
            )
            if (group["has_children"] == 0).any()
            else None,
            "lowIncomePct": float(
                group.loc[group["low_income"] == 1, "correct"].mean() * 100
            )
            if (group["low_income"] == 1).any()
            else None,
            "highIncomePct": float(
                group.loc[group["high_income"] == 1, "correct"].mean() * 100
            )
            if (group["high_income"] == 1).any()
            else None,
        }
        if variable in BINARY_PROGRAMS:
            positive = group[group["value"] > 0]
            negative = group[group["value"] == 0]
            item["positiveCasePct"] = (
                float(positive["correct"].mean() * 100) if not positive.empty else None
            )
            item["zeroCasePct"] = (
                float(negative["correct"].mean() * 100) if not negative.empty else None
            )
        else:
            positive = group[group["positive_truth"]]
            zero = group[group["zero_truth"]]
            item["positiveCasePct"] = (
                float(positive["correct"].mean() * 100) if not positive.empty else None
            )
            item["zeroCasePct"] = (
                float((~zero["nonzero_prediction_on_zero"].astype(bool)).mean() * 100)
                if not zero.empty
                else None
            )
            item["underpredictSharePositivePct"] = (
                float(positive["underpredict_positive"].mean() * 100)
                if not positive.empty
                else None
            )
        program_slices.append(item)

    segment_defs = [
        ("Households with children", merged["has_children"] == 1),
        ("Low-income households", merged["low_income"] == 1),
        ("Disabled households", merged["any_disabled"] == 1),
        ("Retirement-income households", merged["has_retirement_income"] == 1),
        ("Wage-only households", merged["wage_only"] == 1),
        ("No-income-tax states", merged["no_income_tax_state"] == 1),
        ("High-income households", merged["high_income"] == 1),
    ]
    household_segments = []
    for label, mask in segment_defs:
        segment = merged.loc[mask]
        if segment.empty:
            continue
        household_segments.append(
            {
                "label": label,
                "correctPct": float(segment["correct"].mean() * 100),
                "n": int(len(segment)),
            }
        )

    program_slices = sorted(program_slices, key=lambda item: item["overallCorrectPct"])
    household_segments = sorted(household_segments, key=lambda item: item["correctPct"])

    return {
        "programs": program_slices,
        "households": household_segments,
    }


def build_dashboard_payload(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
    analysis: dict[str, pd.DataFrame],
    scenarios: pd.DataFrame,
    scenario_prompts: dict[str, dict[str, dict[str, str]]] | None = None,
) -> dict:
    """Build the dashboard payload consumed by the app frontend."""
    merged = predictions.merge(
        ground_truth,
        on=["scenario_id", "variable"],
        how="inner",
    )
    merged = merged.dropna(subset=["prediction"]).copy()
    merged["error"] = merged["prediction"] - merged["value"]

    metrics = analysis["metrics"].copy()

    scenario_rows = scenarios.sort_values("scenario_id").to_dict("records")
    payload_country = (
        str(scenarios["country"].dropna().iloc[0]).lower()
        if "country" in scenarios.columns and not scenarios["country"].dropna().empty
        else "us"
    )
    scenario_payload = {}
    for row in scenario_rows:
        item = {
            "country": str(row.get("country", payload_country)).lower(),
            "state": row["state"],
            "filingStatus": _clean_json_text(row.get("filing_status")),
            "numAdults": int(row["num_adults"]),
            "numChildren": int(row["num_children"]),
            "totalIncome": float(row["total_income"]),
        }
        if scenario_prompts and row["scenario_id"] in scenario_prompts:
            first_prompt = next(
                iter(scenario_prompts[row["scenario_id"]].values()), None
            )
            if first_prompt is not None:
                item["prompt"] = first_prompt
        scenario_payload[row["scenario_id"]] = item

    model_stats = []
    for _, row in (
        analysis["model_summary"].sort_values("mean_score", ascending=False).iterrows()
    ):
        item = {
            "model": row["model"],
            "condition": "no_tools",
            "score": _clean_json_number(
                row["mean_score"] * 100
                if not pd.isna(row["mean_score"])
                else row["mean_score"]
            ),
            "exact": _clean_json_number(
                row["mean_exact"] * 100
                if not pd.isna(row["mean_exact"])
                else row["mean_exact"]
            ),
            "within1pct": _clean_json_number(
                row["mean_within_1pct"] * 100
                if not pd.isna(row["mean_within_1pct"])
                else row["mean_within_1pct"]
            ),
            "within5pct": _clean_json_number(
                row["mean_within_5pct"] * 100
                if not pd.isna(row["mean_within_5pct"])
                else row["mean_within_5pct"]
            ),
            "mae": float(row["mean_mae"]),
            "mape": _clean_json_number(
                row["mean_mape"] * 100
                if not pd.isna(row["mean_mape"])
                else row["mean_mape"]
            ),
            "within10pct": _clean_json_number(
                row["mean_within_10pct"] * 100
                if not pd.isna(row["mean_within_10pct"])
                else row["mean_within_10pct"]
            ),
            "n": int(row["total_n"]),
            "nParsed": int(row["parsed_n"]),
            "coverage": _clean_json_number(
                row["mean_coverage"] * 100
                if not pd.isna(row["mean_coverage"])
                else row["mean_coverage"]
            ),
            "runCount": int(row["run_count"])
            if "run_count" in row.index and not pd.isna(row["run_count"])
            else None,
            "scoreRunMean": _clean_json_number(
                row["score_run_mean"] * 100
                if "score_run_mean" in row.index and not pd.isna(row["score_run_mean"])
                else float("nan")
            ),
            "scoreRunStd": _clean_json_number(
                row["score_run_std"] * 100
                if "score_run_std" in row.index and not pd.isna(row["score_run_std"])
                else float("nan")
            ),
            "scoreRunMin": _clean_json_number(
                row["score_run_min"] * 100
                if "score_run_min" in row.index and not pd.isna(row["score_run_min"])
                else float("nan")
            ),
            "scoreRunMax": _clean_json_number(
                row["score_run_max"] * 100
                if "score_run_max" in row.index and not pd.isna(row["score_run_max"])
                else float("nan")
            ),
            "within10pctRunMean": _clean_json_number(
                row["within10pct_run_mean"] * 100
                if "within10pct_run_mean" in row.index
                and not pd.isna(row["within10pct_run_mean"])
                else float("nan")
            ),
            "within10pctRunStd": _clean_json_number(
                row["within10pct_run_std"] * 100
                if "within10pct_run_std" in row.index
                and not pd.isna(row["within10pct_run_std"])
                else float("nan")
            ),
            "within10pctRunMin": _clean_json_number(
                row["within10pct_run_min"] * 100
                if "within10pct_run_min" in row.index
                and not pd.isna(row["within10pct_run_min"])
                else float("nan")
            ),
            "within10pctRunMax": _clean_json_number(
                row["within10pct_run_max"] * 100
                if "within10pct_run_max" in row.index
                and not pd.isna(row["within10pct_run_max"])
                else float("nan")
            ),
            "maeRunMean": _clean_json_number(
                row["mae_run_mean"]
                if "mae_run_mean" in row.index and not pd.isna(row["mae_run_mean"])
                else float("nan")
            ),
            "maeRunStd": _clean_json_number(
                row["mae_run_std"]
                if "mae_run_std" in row.index and not pd.isna(row["mae_run_std"])
                else float("nan")
            ),
        }
        if not pd.isna(row["mean_accuracy"]):
            item["accuracy"] = float(row["mean_accuracy"] * 100)
        model_stats.append({k: v for k, v in item.items() if v is not None})

    program_rows = []
    for variable, group in metrics.groupby("variable"):
        item = {
            "variable": variable,
            "score": float(group["score"].mean() * 100),
            "exact": float(group["exact"].mean() * 100),
            "within1pct": float(group["within_1pct"].mean() * 100),
            "within5pct": float(group["within_5pct"].mean() * 100),
            "mae": float(group["mae"].mean()),
            "n": int(group["n"].sum()),
            "nParsed": int(group["n_parsed"].sum()),
        }
        mean_mape = group["mape"].mean()
        mean_accuracy = group["accuracy"].mean()
        mean_within = group["within_10pct"].mean()
        mean_coverage = group["coverage"].mean()
        if not pd.isna(mean_mape):
            item["mape"] = float(mean_mape * 100)
        if not pd.isna(mean_accuracy):
            item["accuracy"] = float(mean_accuracy * 100)
        if not pd.isna(mean_within):
            item["within10pct"] = float(mean_within * 100)
        if not pd.isna(mean_coverage):
            item["coverage"] = float(mean_coverage * 100)
        program_rows.append(item)
    program_stats = sorted(program_rows, key=lambda row: row["variable"])

    heatmap = []
    for _, row in metrics.sort_values(["variable", "model"]).iterrows():
        item = {
            "model": row["model"],
            "variable": row["variable"],
            "condition": "no_tools",
            "score": float(row["score"] * 100),
            "exact": float(row["exact"] * 100),
            "within1pct": float(row["within_1pct"] * 100),
            "within5pct": float(row["within_5pct"] * 100),
            "mae": float(row["mae"]),
            "n": int(row["n"]),
            "nParsed": int(row["n_parsed"]),
            "coverage": float(row["coverage"] * 100),
        }
        if not pd.isna(row["accuracy"]):
            item["accuracy"] = float(row["accuracy"] * 100)
        if not pd.isna(row["within_10pct"]):
            item["within10pct"] = float(row["within_10pct"] * 100)
        heatmap.append(item)

    scenario_predictions: dict[str, dict[str, dict[str, dict[str, float | str]]]] = {}
    for _, row in merged.sort_values(["scenario_id", "variable", "model"]).iterrows():
        scenario_data = scenario_predictions.setdefault(row["scenario_id"], {})
        variable_data = scenario_data.setdefault(row["variable"], {})
        prediction_item: dict[str, float | str] = {
            "prediction": float(row["prediction"]),
            "groundTruth": float(row["value"]),
            "error": float(row["error"]),
        }
        explanation = row.get("explanation")
        if isinstance(explanation, str) and explanation.strip():
            prediction_item["explanation"] = explanation.strip()
        variable_data[row["model"]] = prediction_item

    return {
        "country": payload_country,
        "scenarios": scenario_payload,
        "modelStats": model_stats,
        "programStats": program_stats,
        "heatmap": heatmap,
        "scenarioPredictions": scenario_predictions,
        "failureModes": build_failure_modes_payload(
            ground_truth,
            predictions,
            scenarios,
        ),
    }


COUNTRY_LABELS = {
    "us": "United States",
    "uk": "United Kingdom",
}


def build_global_dashboard_payload(country_payloads: dict[str, dict]) -> dict:
    """Build a shared global leaderboard from multiple country payloads."""
    no_tools_models_by_country: dict[str, dict[str, dict]] = {}
    for country, payload in country_payloads.items():
        no_tools_models_by_country[country] = {
            row["model"]: row
            for row in payload.get("modelStats", [])
            if row.get("condition") == "no_tools"
        }

    common_models: set[str] = set()
    for country_models in no_tools_models_by_country.values():
        if not common_models:
            common_models = set(country_models)
        else:
            common_models &= set(country_models)

    def _mean(values: list[float | int | None]) -> float | None:
        filtered = [float(value) for value in values if value is not None]
        if not filtered:
            return None
        return float(np.mean(filtered))

    model_stats = []
    for model in sorted(common_models):
        rows = {
            country: country_models[model]
            for country, country_models in no_tools_models_by_country.items()
        }
        item = {
            "model": model,
            "condition": "no_tools",
            "score": _mean([row.get("score") for row in rows.values()]),
            "exact": _mean([row.get("exact") for row in rows.values()]),
            "within1pct": _mean([row.get("within1pct") for row in rows.values()]),
            "within5pct": _mean([row.get("within5pct") for row in rows.values()]),
            "within10pct": _mean([row.get("within10pct") for row in rows.values()]),
            "coverage": _mean([row.get("coverage") for row in rows.values()]),
            "n": int(sum(int(row.get("n", 0)) for row in rows.values())),
            "nParsed": int(sum(int(row.get("nParsed", 0)) for row in rows.values())),
            "countryScores": {
                country: float(row["score"])
                for country, row in rows.items()
                if row.get("score") is not None
            },
        }
        accuracy = _mean([row.get("accuracy") for row in rows.values()])
        if accuracy is not None:
            item["accuracy"] = accuracy
        model_stats.append(item)

    model_stats.sort(key=lambda row: row["score"], reverse=True)

    country_summaries = []
    for country, payload in country_payloads.items():
        country_summaries.append(
            {
                "key": country,
                "label": COUNTRY_LABELS.get(country, country.upper()),
                "households": len(payload.get("scenarios", {})),
                "models": len(no_tools_models_by_country[country]),
                "programs": len(payload.get("programStats", [])),
            }
        )

    return {
        "modelStats": model_stats,
        "countrySummaries": country_summaries,
        "sharedModelCount": len(common_models),
    }


def export_dashboard_data(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
    analysis: dict[str, pd.DataFrame],
    scenarios: pd.DataFrame,
    output_path: str | Path,
    scenario_prompts: dict[str, dict[str, dict[str, str]]] | None = None,
) -> Path:
    """Write the frontend dashboard payload to disk."""
    dashboard_path = Path(output_path)
    dashboard_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_dashboard_payload(
        ground_truth,
        predictions,
        analysis,
        scenarios,
        scenario_prompts=scenario_prompts,
    )
    dashboard_path.write_text(json.dumps(payload), encoding="utf-8")
    return dashboard_path


def build_scenario_prompt_map(
    scenarios: pd.DataFrame,
    variables: list[str],
) -> dict[str, dict[str, dict[str, str]]]:
    """Build exact prompts for each scenario/variable/answer contract."""
    if "scenario_json" not in scenarios.columns:
        return {}

    prompt_map: dict[str, dict[str, dict[str, str]]] = {}
    for _, row in scenarios.dropna(subset=["scenario_json"]).iterrows():
        scenario = scenario_from_dict(json.loads(row["scenario_json"]))
        tool_prompt = make_no_tools_batch_prompt(
            scenario,
            variables,
            answer_contract="tool",
        )
        json_prompt = make_no_tools_batch_prompt(
            scenario,
            variables,
            answer_contract="json",
        )
        prompt_map[row["scenario_id"]] = {
            variable: {
                "tool": tool_prompt,
                "json": json_prompt,
            }
            for variable in variables
        }
    return prompt_map


def export_analysis(
    analysis: dict[str, pd.DataFrame],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write production analysis artifacts to disk."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    metrics_path = output_path / "metrics.csv"
    model_summary_path = output_path / "summary_by_model.csv"
    variable_summary_path = output_path / "summary_by_variable.csv"
    usage_summary_path = output_path / "usage_summary.csv"
    report_path = output_path / "report.md"

    analysis["metrics"].to_csv(metrics_path, index=False)
    analysis["model_summary"].to_csv(model_summary_path, index=False)
    analysis["variable_summary"].to_csv(variable_summary_path, index=False)
    analysis["usage_summary"].to_csv(usage_summary_path, index=False)
    report_path.write_text(render_markdown_report(analysis), encoding="utf-8")

    exported = {
        "metrics": metrics_path,
        "model_summary": model_summary_path,
        "variable_summary": variable_summary_path,
        "usage_summary": usage_summary_path,
        "report": report_path,
    }
    run_model_summary = analysis.get("run_model_summary", pd.DataFrame())
    if not run_model_summary.empty:
        run_model_summary_path = output_path / "run_model_summary.csv"
        run_model_summary.to_csv(run_model_summary_path, index=False)
        exported["run_model_summary"] = run_model_summary_path

    run_stability = analysis.get("run_stability", pd.DataFrame())
    if not run_stability.empty:
        run_stability_path = output_path / "run_stability_by_model.csv"
        run_stability.to_csv(run_stability_path, index=False)
        exported["run_stability"] = run_stability_path

    return exported
