"""Metrics and analysis for PolicyBench results."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from policybench.config import BINARY_PROGRAMS, RATE_PROGRAMS
from policybench.prompts import make_no_tools_prompt
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
        DataFrame with columns [model, variable, mae, mape, accuracy_10pct, n]
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
                row["within_10pct"] = float("nan")
            else:
                row["accuracy"] = float("nan")
                row["within_10pct"] = 0.0
            rows.append(row)
            continue

        y_true = scored["value"].values
        y_pred = scored["prediction"].values

        if variable in BINARY_PROGRAMS:
            row["mae"] = mean_absolute_error(y_true, y_pred)
            row["mape"] = float("nan")
            row["accuracy"] = accuracy(y_true, y_pred) * coverage
            row["within_10pct"] = float("nan")
        elif variable in RATE_PROGRAMS:
            row["mae"] = mean_absolute_error(y_true, y_pred)
            row["mape"] = float("nan")
            row["accuracy"] = float("nan")
            row["within_10pct"] = within_tolerance(y_true, y_pred, tolerance=0.10) * coverage
        else:
            row["mae"] = mean_absolute_error(y_true, y_pred)
            row["mape"] = mean_absolute_percentage_error(y_true, y_pred)
            row["accuracy"] = float("nan")
            row["within_10pct"] = within_tolerance(y_true, y_pred, tolerance=0.10) * coverage

        rows.append(row)

    return pd.DataFrame(rows)


def summary_by_model(metrics: pd.DataFrame) -> pd.DataFrame:
    """Aggregate metrics by model across all variables."""
    return (
        metrics.groupby("model")
        .agg(
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
        elif column not in usage.columns:
            usage[column] = float("nan")

    return (
        usage.groupby("model")
        .agg(
            total_rows=("variable", "size"),
            parsed_rows=("prediction", lambda s: int(s.notna().sum())),
            error_rows=("error", lambda s: int(s.notna().sum())),
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
        "mean_within_10pct",
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
        "This report is generated by `policybench analyze` from no-tools benchmark results.",
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
                    f"`mean_within_10pct={_format_metric(top_model['mean_within_10pct'])}` "
                    f"and `mean_mae={_format_metric(top_model['mean_mae'])}`."
                ),
                "",
            ]
        )
        if (
            "run_count" in top_model.index
            and not pd.isna(top_model.get("run_count"))
            and top_model.get("run_count", 0) > 1
        ):
            lines.extend(
                [
                    (
                        f"Across `{int(top_model['run_count'])}` repeated runs on the fixed "
                        "scenario set, this model averaged "
                        f"`{_format_metric(top_model['within10pct_run_mean'])}` "
                        "within-10% accuracy"
                        + (
                            f" with run-to-run std `{_format_metric(top_model['within10pct_run_std'])}`."
                            if not pd.isna(top_model.get("within10pct_run_std"))
                            else "."
                        )
                    ),
                    "",
                ]
            )

    if not usage_summary.empty:
        total_cost = _sum_or_nan(usage_summary["total_estimated_cost_usd"])
        total_runtime = _sum_or_nan(usage_summary["total_elapsed_seconds"])
        lines.extend(
            [
                "## Usage",
                "",
                (
                    f"Estimated total cost: `{_format_metric(total_cost)}` USD. "
                    f"Estimated total runtime: `{_format_seconds(total_runtime)}`."
                ),
                "",
                "| model | total_estimated_cost_usd | total_elapsed | total_tokens | reasoning_tokens | parsed_rows | total_rows |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for _, row in usage_summary.iterrows():
            lines.append(
                "| "
                f"{row['model']} | "
                f"{_format_metric(row['total_estimated_cost_usd'])} | "
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
                "| model | run_count | within10_run_mean | within10_run_std | within10_run_min | within10_run_max | mae_run_mean | mae_run_std |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for _, row in run_stability.sort_values(
            "within10pct_run_mean",
            ascending=False,
        ).iterrows():
            lines.append(
                "| "
                f"{row['model']} | "
                f"{int(row['run_count'])} | "
                f"{_format_metric(row['within10pct_run_mean'])} | "
                f"{_format_metric(row['within10pct_run_std'])} | "
                f"{_format_metric(row['within10pct_run_min'])} | "
                f"{_format_metric(row['within10pct_run_max'])} | "
                f"{_format_metric(row['mae_run_mean'])} | "
                f"{_format_metric(row['mae_run_std'])} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Summary by model",
            "",
            "| model | mean_mae | mean_mape | mean_within_10pct | total_n |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in model_summary.iterrows():
        lines.append(
            "| "
            f"{row['model']} | "
            f"{_format_metric(row['mean_mae'])} | "
            f"{_format_metric(row['mean_mape'])} | "
            f"{_format_metric(row['mean_within_10pct'])} | "
            f"{int(row['total_n'])} |"
        )

    lines.extend(
        [
            "",
            "## Summary by variable",
            "",
            "| variable | mean_mae | mean_mape | mean_within_10pct | total_n |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in variable_summary.iterrows():
        lines.append(
            "| "
            f"{row['variable']} | "
            f"{_format_metric(row['mean_mae'])} | "
            f"{_format_metric(row['mean_mape'])} | "
            f"{_format_metric(row['mean_within_10pct'])} | "
            f"{int(row['total_n'])} |"
        )

    lines.append("")
    return "\n".join(lines)


def _clean_json_number(value):
    if pd.isna(value):
        return None
    return float(value)


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
    scenario_payload = {
        row["scenario_id"]: {
            "state": row["state"],
            "filingStatus": row["filing_status"],
            "numAdults": int(row["num_adults"]),
            "numChildren": int(row["num_children"]),
            "totalIncome": float(row["total_income"]),
            **(
                {"promptByVariable": scenario_prompts[row["scenario_id"]]}
                if scenario_prompts and row["scenario_id"] in scenario_prompts
                else {}
            ),
        }
        for row in scenario_rows
    }

    model_stats = []
    for _, row in analysis["model_summary"].sort_values(
        "mean_within_10pct", ascending=False
    ).iterrows():
        item = {
            "model": row["model"],
            "condition": "no_tools",
            "mae": float(row["mean_mae"]),
            "mape": _clean_json_number(
                row["mean_mape"] * 100 if not pd.isna(row["mean_mape"]) else row["mean_mape"]
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

    scatter = []
    for _, row in merged.sort_values(["model", "scenario_id", "variable"]).iterrows():
        scatter.append(
            {
                "model": row["model"],
                "condition": "no_tools",
                "scenario": row["scenario_id"],
                "variable": row["variable"],
                "prediction": float(row["prediction"]),
                "groundTruth": float(row["value"]),
                "error": float(row["error"]),
            }
        )

    return {
        "scenarios": scenario_payload,
        "modelStats": model_stats,
        "programStats": program_stats,
        "heatmap": heatmap,
        "scatter": scatter,
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
        prompt_map[row["scenario_id"]] = {
            variable: {
                "tool": make_no_tools_prompt(
                    scenario,
                    variable,
                    answer_contract="tool",
                ),
                "json": make_no_tools_prompt(
                    scenario,
                    variable,
                    answer_contract="json",
                ),
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
