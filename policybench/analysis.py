"""Metrics and analysis for PolicyBench results."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from policybench.config import (
    BINARY_PROGRAMS,
    HOUSEHOLD_IMPACT_SCORE_FLOOR,
)
from policybench.policyengine_runtime import policyengine_bundles_for_countries
from policybench.prompts import make_no_tools_batch_prompt
from policybench.scenarios import scenario_from_dict
from policybench.spec import (
    expand_programs_for_scenario,
    metric_type_for_output,
    net_income_sign_for_output,
    output_group_id,
)


def mean_absolute_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute mean absolute error."""
    return float(np.mean(np.abs(y_true - y_pred)))


def mean_absolute_percentage_error(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute MAPE, excluding zero reference values."""
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
    """Fraction of predictions within tolerance of reference values.

    For values where the reference value is 0, checks if prediction is also 0.
    """
    mask_nonzero = y_true != 0
    mask_zero = ~mask_nonzero

    correct = np.zeros(len(y_true), dtype=bool)

    # For nonzero reference values: within relative tolerance
    if mask_nonzero.any():
        rel_error = np.abs(
            (y_true[mask_nonzero] - y_pred[mask_nonzero]) / y_true[mask_nonzero]
        )
        correct[mask_nonzero] = rel_error <= tolerance

    # For zero reference values: prediction must be within absolute tolerance
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


def continuous_row_score(y_true: float, y_pred: float | None) -> float:
    """Continuous, floor-free row score in [0, 1].

    For a nonzero reference: ``max(0, 1 - |pred - ref| / |ref|)``.
    For a zero reference: 1 if the prediction is exactly 0, else 0
    (any nonzero prediction is fully wrong).

    With this formulation booleans encoded as 0/1 fall out naturally:
    a wrong eligibility call has |err| = 1 = |ref|, so the score is 0;
    a right call has |err| = 0, score 1.
    """
    if y_pred is None:
        return 0.0
    try:
        if pd.isna(y_pred):
            return 0.0
    except (TypeError, ValueError):
        return 0.0
    ref = float(y_true)
    pred = float(y_pred)
    if ref == 0.0:
        return 1.0 if pred == 0.0 else 0.0
    return max(0.0, 1.0 - abs(pred - ref) / abs(ref))


def _signed_contributions(ground_truth: pd.DataFrame) -> pd.DataFrame:
    """Compute the signed and absolute contribution of each cell to net income.

    Adds three columns to a copy of the input:

    - ``net_income_sign``: +1 for benefits / refundable credits, -1 for taxes.
    - ``signed_contribution``: the signed dollar effect on net income.
      Amount cells: ``value * net_income_sign``.
      Binary cells with a paired ``impact_weight`` value:
      ``value * impact_weight * net_income_sign``
      (the paired value is added when the LLM predicts "eligible", $0
      otherwise — for the reference, ``value`` is 1 if truly eligible).
    - ``abs_contribution``: ``|signed_contribution|``. Used as ``|ref|``
      in the bounded weighting denominator.
    """
    df = ground_truth.copy()
    df["net_income_sign"] = df["variable"].map(net_income_sign_for_output)
    if "impact_weight" in df.columns:
        explicit = pd.to_numeric(df["impact_weight"], errors="coerce")
    else:
        explicit = pd.Series(pd.NA, index=df.index, dtype="Float64")
    explicit_filled = explicit.fillna(1.0)
    # For amount cells the multiplier is 1 (so signed = value*sign);
    # for binary cells the multiplier is the paired dollar value (so signed
    # = boolean * paired_value * sign, i.e. paired value when eligible).
    df["signed_contribution"] = df["value"] * explicit_filled * df["net_income_sign"]
    df["abs_contribution"] = df["signed_contribution"].abs()
    return df


def household_net_income_by_scenario(
    ground_truth: pd.DataFrame,
    market_income_by_scenario: dict[str, float] | pd.Series,
) -> pd.Series:
    """Net income per scenario: market income + signed program contributions.

    Booleans contribute their paired per-capita value when eligible.
    """
    df = _signed_contributions(ground_truth)
    signed_total = df.groupby("scenario_id")["signed_contribution"].sum()
    market = pd.Series(market_income_by_scenario)
    market = pd.to_numeric(market, errors="coerce").fillna(0.0)
    market = market.reindex(signed_total.index, fill_value=0.0)
    return market + signed_total


def bounded_global_variable_weights(
    ground_truth: pd.DataFrame,
    market_income_by_scenario: dict[str, float] | pd.Series,
) -> pd.Series:
    """Bounded global variable weights.

    Per household: ``share_ij = |ref_ij| / max(|net_income_i|, Σ_k |ref_ik|)``.
    Global weight for variable j = mean of per-household shares across
    households, then renormalized so weights sum to 1.

    The ``max(...)`` denominator caps per-household shares at 1 (in the
    cancellation case where taxes and benefits sum to more than net income)
    and dwarfs tiny programs in high-earning households (so a $1 benefit
    to a $200k household gets share ≈ 5e-6, not 100%).
    """
    df = _signed_contributions(ground_truth)
    abs_total = df.groupby("scenario_id")["abs_contribution"].sum()
    net_income = household_net_income_by_scenario(
        ground_truth, market_income_by_scenario
    )
    denom = pd.concat([net_income.abs(), abs_total], axis=1).max(axis=1)
    denom = denom.reindex(df["scenario_id"].values).values
    shares = np.where(
        denom > 0,
        df["abs_contribution"].values / np.where(denom > 0, denom, 1.0),
        0.0,
    )
    df["share"] = shares
    # Average each variable's share across ALL scenarios in the benchmark, not
    # just scenarios where the variable appears — otherwise a variable that
    # applies only to households with a 6th child gets inflated weight because
    # the denominator collapses to the handful of households that have one.
    total_scenarios = df["scenario_id"].nunique()
    raw = df.groupby("variable")["share"].sum() / max(total_scenarios, 1)
    total = float(raw.sum())
    if total <= 0:
        return raw
    return raw / total


def bounded_household_scores(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
    market_income_by_scenario: dict[str, float] | pd.Series,
) -> pd.DataFrame:
    """Score each model using bounded global variable weights × continuous row score.

    Returns one row per (model, scenario_id) with the household score,
    plus the model-level mean.
    """
    if ground_truth.empty or predictions.empty:
        return pd.DataFrame(columns=["model", "scenario_id", "score"])
    weights = bounded_global_variable_weights(ground_truth, market_income_by_scenario)
    models = sorted(predictions["model"].dropna().unique())
    grid = (
        ground_truth.assign(_k=1)
        .merge(pd.DataFrame({"model": models, "_k": 1}), on="_k")
        .drop(columns="_k")
    )
    merged = grid.merge(
        predictions[["model", "scenario_id", "variable", "prediction"]],
        on=["model", "scenario_id", "variable"],
        how="left",
    )
    merged["row_score"] = [
        continuous_row_score(t, p)
        for t, p in zip(merged["value"], merged["prediction"])
    ]
    merged["weight"] = merged["variable"].map(weights).fillna(0.0)
    merged["weighted"] = merged["row_score"] * merged["weight"]
    return (
        merged.groupby(["model", "scenario_id"])["weighted"]
        .sum()
        .rename("score")
        .reset_index()
    )


def amount_accuracy_by_model(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
    market_income_by_scenario: dict[str, float] | pd.Series,
) -> pd.DataFrame:
    """Amount accuracy: weighted continuous row score over dollar cells where ref ≠ 0.

    Conditional on amount-type variables with nonzero references — booleans
    and zero-ref dollar cells are excluded because amount accuracy is about
    "did you get the magnitude roughly right", not "did you predict the
    eligibility / zero call". Per-household weights are the global variable
    weights from :func:`bounded_global_variable_weights`, renormalized within
    each household across the eligible cells. Households are averaged with
    equal weight.
    """
    if ground_truth.empty or predictions.empty:
        return pd.DataFrame(columns=["model", "amount_accuracy"])
    weights = bounded_global_variable_weights(ground_truth, market_income_by_scenario)
    gt = ground_truth.copy()
    gt["metric_type"] = gt["variable"].map(metric_type_for_output)
    if "impact_weight" in gt.columns:
        explicit = pd.to_numeric(gt["impact_weight"], errors="coerce")
    else:
        explicit = pd.Series(pd.NA, index=gt.index, dtype="Float64")
    is_amount = (
        (gt["metric_type"] != "binary")
        & (~gt["variable"].isin(BINARY_PROGRAMS))
        & explicit.isna()
    )
    amount_rows = gt[is_amount & (gt["value"].abs() > 0)]
    models = sorted(predictions["model"].dropna().unique())
    grid = (
        amount_rows.assign(_k=1)
        .merge(pd.DataFrame({"model": models, "_k": 1}), on="_k")
        .drop(columns="_k")
    )
    merged = grid.merge(
        predictions[["model", "scenario_id", "variable", "prediction"]],
        on=["model", "scenario_id", "variable"],
        how="left",
    )
    merged["row_score"] = [
        continuous_row_score(t, p)
        for t, p in zip(merged["value"], merged["prediction"])
    ]
    merged["weight"] = merged["variable"].map(weights).fillna(0.0)
    merged["weighted_score"] = merged["row_score"] * merged["weight"]
    household_agg = merged.groupby(["model", "scenario_id"]).agg(
        num=("weighted_score", "sum"),
        den=("weight", "sum"),
    )
    household_agg["amount_accuracy"] = np.where(
        household_agg["den"] > 0,
        household_agg["num"]
        / household_agg["den"].where(household_agg["den"] > 0, 1.0),
        1.0,
    )
    return (
        household_agg.reset_index()
        .groupby("model")["amount_accuracy"]
        .mean()
        .reset_index()
    )


def _weighted_household_scores(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
    weights: pd.Series,
    per_household_normalize: bool = True,
) -> pd.DataFrame:
    """Helper: row_score * weight summed per household and averaged per model.

    When ``per_household_normalize`` is True (default for the equal and
    aggregate views), weights are renormalized within each scenario so that
    a household's weights sum to 1 over the variables it actually has — this
    keeps the score in [0, 1] regardless of how many of the benchmark's
    variables apply to that scenario. The headline ``bounded_household_scores``
    intentionally uses ``per_household_normalize=False`` so per-household
    shares stay anchored to the bounded denominator and can sum to less than 1.
    """
    if ground_truth.empty or predictions.empty:
        return pd.DataFrame(columns=["model", "score"])
    models = sorted(predictions["model"].dropna().unique())
    grid = (
        ground_truth.assign(_k=1)
        .merge(pd.DataFrame({"model": models, "_k": 1}), on="_k")
        .drop(columns="_k")
    )
    merged = grid.merge(
        predictions[["model", "scenario_id", "variable", "prediction"]],
        on=["model", "scenario_id", "variable"],
        how="left",
    )
    merged["row_score"] = [
        continuous_row_score(t, p)
        for t, p in zip(merged["value"], merged["prediction"])
    ]
    merged["weight"] = merged["variable"].map(weights).fillna(0.0)
    if per_household_normalize:
        sums = merged.groupby(["model", "scenario_id"])["weight"].transform("sum")
        merged["weight"] = np.where(sums > 0, merged["weight"] / sums, 0.0)
    merged["weighted"] = merged["row_score"] * merged["weight"]
    household = (
        merged.groupby(["model", "scenario_id"])["weighted"]
        .sum()
        .rename("score")
        .reset_index()
    )
    return household.groupby("model")["score"].mean().reset_index()


def equal_weight_scores_by_model(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
) -> pd.DataFrame:
    """Equal-output-weight scores: each variable gets weight 1/K, then per-row
    scores are averaged within a household and households are averaged with
    equal weight.
    """
    if ground_truth.empty or predictions.empty:
        return pd.DataFrame(columns=["model", "equal_score"])
    variables = ground_truth["variable"].drop_duplicates().tolist()
    if not variables:
        return pd.DataFrame(columns=["model", "equal_score"])
    weights = pd.Series(1.0 / len(variables), index=variables)
    out = _weighted_household_scores(ground_truth, predictions, weights)
    return out.rename(columns={"score": "equal_score"})


def aggregate_global_variable_weights(ground_truth: pd.DataFrame) -> pd.Series:
    """Budget-weighted (aggregate-impact) per-variable weights.

    Each variable's weight is its share of total absolute reference dollars
    across the benchmark. Booleans contribute their paired ``impact_weight``
    value when eligible.
    """
    if ground_truth.empty:
        return pd.Series(dtype=float)
    gt = ground_truth.copy()
    if "impact_weight" in gt.columns:
        explicit = pd.to_numeric(gt["impact_weight"], errors="coerce").abs()
        gt["abs_value"] = explicit.fillna(gt["value"].abs())
    else:
        gt["abs_value"] = gt["value"].abs()
    totals = gt.groupby("variable")["abs_value"].sum()
    grand = float(totals.sum())
    if grand <= 0:
        return pd.Series(0.0, index=totals.index)
    return totals / grand


def equal_global_variable_weights(ground_truth: pd.DataFrame) -> pd.Series:
    """Equal per-variable weights: ``1 / K`` across the benchmark's unique outputs."""
    if ground_truth.empty:
        return pd.Series(dtype=float)
    variables = ground_truth["variable"].drop_duplicates().tolist()
    if not variables:
        return pd.Series(dtype=float)
    return pd.Series(1.0 / len(variables), index=variables)


def aggregate_weight_scores_by_model(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
) -> pd.DataFrame:
    """Budget-weighted (aggregate-impact) scores: each variable's weight is its
    share of total absolute reference dollars across the benchmark. Booleans
    contribute their paired ``impact_weight`` value when eligible.
    """
    if ground_truth.empty or predictions.empty:
        return pd.DataFrame(columns=["model", "aggregate_score"])
    weights = aggregate_global_variable_weights(ground_truth)
    if weights.empty:
        return pd.DataFrame(columns=["model", "aggregate_score"])
    out = _weighted_household_scores(ground_truth, predictions, weights)
    return out.rename(columns={"score": "aggregate_score"})


def participation_accuracy_by_model(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
) -> pd.DataFrame:
    """Participation accuracy: cell-level binary check.

    For amount cells: a match means ``(pred == 0)`` iff ``(ref == 0)``.
    For boolean cells: a match means ``pred == ref`` exactly (encoded 0/1).
    Reported as a fraction of all cells (across all scenarios and variables).
    """
    if ground_truth.empty or predictions.empty:
        return pd.DataFrame(columns=["model", "participation_accuracy"])
    gt = ground_truth.copy()
    gt["metric_type"] = gt["variable"].map(metric_type_for_output)
    if "impact_weight" in gt.columns:
        explicit = pd.to_numeric(gt["impact_weight"], errors="coerce")
    else:
        explicit = pd.Series(pd.NA, index=gt.index, dtype="Float64")
    gt["is_binary"] = (
        (gt["metric_type"] == "binary")
        | gt["variable"].isin(BINARY_PROGRAMS)
        | explicit.notna()
    )
    models = sorted(predictions["model"].dropna().unique())
    grid = (
        gt.assign(_k=1)
        .merge(pd.DataFrame({"model": models, "_k": 1}), on="_k")
        .drop(columns="_k")
    )
    merged = grid.merge(
        predictions[["model", "scenario_id", "variable", "prediction"]],
        on=["model", "scenario_id", "variable"],
        how="left",
    )

    def _match(row):
        ref = row["value"]
        pred = row["prediction"]
        if pred is None or pd.isna(pred):
            return False
        if row["is_binary"]:
            return float(pred) == float(ref)
        return (float(ref) == 0.0) == (float(pred) == 0.0)

    merged["match"] = merged.apply(_match, axis=1)
    return (
        merged.groupby("model")["match"]
        .mean()
        .rename("participation_accuracy")
        .reset_index()
    )


def score_single_prediction(
    variable: str,
    y_true: float,
    y_pred: float | None,
) -> float:
    """Score one prediction on the same 0-1 bounded scale used in aggregates."""
    if y_pred is None or pd.isna(y_pred):
        return 0.0

    y_true_arr = np.array([y_true], dtype=float)
    y_pred_arr = np.array([y_pred], dtype=float)

    metric_type = metric_type_for_output(variable)
    if metric_type == "binary" or variable in BINARY_PROGRAMS:
        return accuracy(y_true_arr, y_pred_arr)

    exact = exact_amount_match(
        y_true_arr,
        y_pred_arr,
        absolute_tolerance=1.0,
    )
    within_1pct = within_tolerance(y_true_arr, y_pred_arr, tolerance=0.01)
    within_5pct = within_tolerance(y_true_arr, y_pred_arr, tolerance=0.05)
    within_10pct = within_tolerance(y_true_arr, y_pred_arr, tolerance=0.10)
    return float(np.mean([exact, within_1pct, within_5pct, within_10pct]))


def household_equal_impact_scores(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
    floor_share: float = HOUSEHOLD_IMPACT_SCORE_FLOOR,
) -> pd.DataFrame:
    """Score models by equal household weight and within-household dollar impact.

    Each household contributes equally to the final metric. Within a household,
    each requested output row gets a blended weight:

    - `floor_share / K` equal-weight floor
    - `(1 - floor_share)` times its absolute reference-value share

    This keeps small or zero-value components from disappearing while still
    giving more weight to larger resource components within a household.
    """
    if floor_share < 0 or floor_share > 1:
        raise ValueError("floor_share must be between 0 and 1.")

    if ground_truth.empty or predictions.empty or "model" not in predictions.columns:
        return pd.DataFrame(
            columns=[
                "model",
                "scenario_id",
                "impact_score",
                "equal_weight_score",
                "coverage",
                "parsed_variables",
                "total_variables",
                "floor_share",
            ]
        )

    models = pd.DataFrame({"model": sorted(predictions["model"].dropna().unique())})
    if models.empty:
        return pd.DataFrame(
            columns=[
                "model",
                "scenario_id",
                "impact_score",
                "equal_weight_score",
                "coverage",
                "parsed_variables",
                "total_variables",
                "floor_share",
            ]
        )

    expected = ground_truth.assign(_join_key=1).merge(
        models.assign(_join_key=1),
        on="_join_key",
    )
    expected = expected.drop(columns="_join_key")

    merged = expected.merge(
        predictions[["model", "scenario_id", "variable", "prediction"]],
        on=["model", "scenario_id", "variable"],
        how="left",
    )

    base_weights = ground_truth.copy()
    base_weights["net_income_sign"] = base_weights["variable"].map(
        net_income_sign_for_output
    )
    default_abs_value = (base_weights["value"] * base_weights["net_income_sign"]).abs()
    if "impact_weight" in base_weights.columns:
        explicit_weight = pd.to_numeric(
            base_weights["impact_weight"],
            errors="coerce",
        ).abs()
        base_weights["abs_value"] = explicit_weight.fillna(default_abs_value)
    else:
        base_weights["abs_value"] = default_abs_value
    base_weights["total_variables"] = base_weights.groupby("scenario_id")[
        "variable"
    ].transform("size")
    base_weights["abs_total"] = base_weights.groupby("scenario_id")[
        "abs_value"
    ].transform("sum")
    base_weights["weight"] = np.where(
        base_weights["abs_total"] > 0,
        floor_share / base_weights["total_variables"]
        + (1 - floor_share) * base_weights["abs_value"] / base_weights["abs_total"],
        1 / base_weights["total_variables"],
    )

    merged = merged.merge(
        base_weights[["scenario_id", "variable", "weight", "total_variables"]],
        on=["scenario_id", "variable"],
        how="left",
    )

    merged["row_score"] = [
        score_single_prediction(variable, y_true, y_pred)
        for variable, y_true, y_pred in zip(
            merged["variable"],
            merged["value"],
            merged["prediction"],
        )
    ]
    merged["weighted_row_score"] = merged["row_score"] * merged["weight"]

    household_scores = (
        merged.groupby(["model", "scenario_id"])
        .agg(
            impact_score=("weighted_row_score", "sum"),
            equal_weight_score=("row_score", "mean"),
            parsed_variables=("prediction", lambda s: int(s.notna().sum())),
            total_variables=("total_variables", "first"),
        )
        .reset_index()
    )
    household_scores["coverage"] = (
        household_scores["parsed_variables"] / household_scores["total_variables"]
    )
    household_scores["floor_share"] = floor_share
    return household_scores


def household_impact_summary_by_model(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
    floor_share: float = HOUSEHOLD_IMPACT_SCORE_FLOOR,
) -> pd.DataFrame:
    """Aggregate household-equal impact scores by model."""
    household_scores = household_equal_impact_scores(
        ground_truth,
        predictions,
        floor_share=floor_share,
    )
    if household_scores.empty:
        return pd.DataFrame(
            columns=[
                "model",
                "mean_impact_score",
                "mean_household_score",
                "mean_household_coverage",
                "households",
                "total_variables",
                "parsed_variables",
                "floor_share",
            ]
        )

    return (
        household_scores.groupby("model")
        .agg(
            mean_impact_score=("impact_score", "mean"),
            mean_household_score=("equal_weight_score", "mean"),
            mean_household_coverage=("coverage", "mean"),
            households=("scenario_id", "nunique"),
            total_variables=("total_variables", "sum"),
            parsed_variables=("parsed_variables", "sum"),
            floor_share=("floor_share", "first"),
        )
        .reset_index()
        .sort_values("mean_impact_score", ascending=False)
    )


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


def _expected_prediction_grid(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
) -> pd.DataFrame:
    """Build the full expected model × scenario × variable grid."""
    if (
        ground_truth.empty
        or predictions.empty
        or "model" not in predictions.columns
        or predictions["model"].dropna().empty
    ):
        return pd.DataFrame(columns=["model", "scenario_id", "variable", "value"])

    models = pd.DataFrame({"model": sorted(predictions["model"].dropna().unique())})
    expected = ground_truth.assign(_join_key=1).merge(
        models.assign(_join_key=1),
        on="_join_key",
    )
    return expected.drop(columns="_join_key")


def _prediction_detail_rows(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
) -> pd.DataFrame:
    """Build one row per expected prediction, preserving missing rows as misses."""
    expected = _expected_prediction_grid(ground_truth, predictions)
    if expected.empty:
        return pd.DataFrame(
            columns=[
                "model",
                "scenario_id",
                "variable",
                "value",
                "prediction",
                "explanation",
                "prediction_error",
                "parsed",
                "error",
                "score",
                "annotation",
                "failure_source",
                "failure_subtype",
                "case_annotation",
                "case_failure_sources",
                "case_failure_subtypes",
                "reference_explanation",
            ]
        )

    prediction_columns = ["model", "scenario_id", "variable", "prediction"]
    optional_columns = [
        column
        for column in [
            "explanation",
            "error",
            "annotation",
            "failure_source",
            "failure_subtype",
            "case_annotation",
            "case_failure_sources",
            "case_failure_subtypes",
            "reference_explanation",
        ]
        if column in predictions.columns
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
    if "annotation" not in merged.columns:
        merged["annotation"] = pd.NA
    if "failure_source" not in merged.columns:
        merged["failure_source"] = pd.NA
    if "failure_subtype" not in merged.columns:
        merged["failure_subtype"] = pd.NA
    if "case_annotation" not in merged.columns:
        merged["case_annotation"] = pd.NA
    if "case_failure_sources" not in merged.columns:
        merged["case_failure_sources"] = pd.NA
    if "case_failure_subtypes" not in merged.columns:
        merged["case_failure_subtypes"] = pd.NA
    if "reference_explanation" not in merged.columns:
        merged["reference_explanation"] = pd.NA

    merged["parsed"] = merged["prediction"].notna()
    merged["error"] = np.where(
        merged["parsed"],
        merged["prediction"] - merged["value"],
        np.nan,
    )
    merged["score"] = [
        score_single_prediction(variable, y_true, y_pred)
        for variable, y_true, y_pred in zip(
            merged["variable"],
            merged["value"],
            merged["prediction"],
            strict=True,
        )
    ]
    return merged


def compute_metrics(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
) -> pd.DataFrame:
    """Compute metrics by model and variable.

    Args:
        ground_truth: DataFrame with columns [scenario_id, variable, value]
        predictions: DataFrame with columns [model, scenario_id, variable, prediction]

    Returns:
        DataFrame with bounded hit-rate scores plus secondary error metrics
    """
    merged = _expected_prediction_grid(ground_truth, predictions).merge(
        predictions[["model", "scenario_id", "variable", "prediction"]],
        on=["model", "scenario_id", "variable"],
        how="left",
    )
    if merged.empty:
        return pd.DataFrame()
    merged["output_group"] = merged["variable"].map(output_group_id)

    rows = []
    for (model, variable), group in merged.groupby(["model", "output_group"]):
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
            if (
                metric_type_for_output(variable) == "binary"
                or variable in BINARY_PROGRAMS
            ):
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

        metric_type = metric_type_for_output(variable)
        if metric_type == "binary" or variable in BINARY_PROGRAMS:
            accuracy_score = accuracy(y_true, y_pred) * coverage
            row["mae"] = mean_absolute_error(y_true, y_pred)
            row["mape"] = float("nan")
            row["accuracy"] = accuracy_score
            row["exact"] = accuracy_score
            row["within_1pct"] = accuracy_score
            row["within_5pct"] = accuracy_score
            row["within_10pct"] = accuracy_score
            row["score"] = accuracy_score
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
    scenarios: pd.DataFrame | None = None,
    repeated_predictions: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Build the standard no-tools analysis tables.

    Args:
        ground_truth: reference outputs (scenario_id, variable, value, impact_weight).
        predictions: model predictions (model, scenario_id, variable, prediction, ...).
        scenarios: scenario metadata. If provided, supplies ``total_income`` per
            scenario for the bounded-global-variable-weights metric. Without it,
            market income defaults to $0 (which collapses the bounded
            formulation to the simple shares-sum-to-1 version).
        repeated_predictions: optional batch of repeat runs for stability metrics.
    """
    metrics = compute_metrics(ground_truth, predictions)
    model_summary = summary_by_model(metrics)
    impact_summary = household_impact_summary_by_model(ground_truth, predictions)
    run_model_summary = summarize_runs_by_model(ground_truth, repeated_predictions)
    run_stability = run_stability_by_model(run_model_summary)
    if not run_stability.empty:
        model_summary = model_summary.merge(run_stability, on="model", how="left")

    market_income: dict[str, float] = {}
    if (
        scenarios is not None
        and not scenarios.empty
        and "total_income" in scenarios.columns
    ):
        market_income = dict(
            zip(
                scenarios["scenario_id"].astype(str),
                pd.to_numeric(scenarios["total_income"], errors="coerce").fillna(0.0),
            )
        )

    bounded_scores = bounded_household_scores(ground_truth, predictions, market_income)
    if not bounded_scores.empty:
        bounded_summary = (
            bounded_scores.groupby("model")["score"]
            .mean()
            .rename("bounded_score")
            .reset_index()
        )
        amount_acc = amount_accuracy_by_model(ground_truth, predictions, market_income)
        participation_acc = participation_accuracy_by_model(ground_truth, predictions)
        equal_scores = equal_weight_scores_by_model(ground_truth, predictions)
        aggregate_scores = aggregate_weight_scores_by_model(ground_truth, predictions)
        bounded_summary = (
            bounded_summary.merge(amount_acc, on="model", how="left")
            .merge(participation_acc, on="model", how="left")
            .merge(equal_scores, on="model", how="left")
            .merge(aggregate_scores, on="model", how="left")
        )
        global_weights = (
            bounded_global_variable_weights(ground_truth, market_income)
            .rename("global_weight")
            .reset_index()
        )
        model_summary = model_summary.merge(bounded_summary, on="model", how="left")
    else:
        bounded_summary = pd.DataFrame(
            columns=[
                "model",
                "bounded_score",
                "amount_accuracy",
                "participation_accuracy",
                "equal_score",
                "aggregate_score",
            ]
        )
        global_weights = pd.DataFrame(columns=["variable", "global_weight"])

    sort_column = (
        "bounded_score" if "bounded_score" in model_summary.columns else "mean_score"
    )
    model_summary = model_summary.sort_values(sort_column, ascending=False)
    variable_summary = summary_by_variable(metrics).sort_values("variable")
    usage_summary = usage_summary_by_model(predictions).sort_values("model")
    return {
        "metrics": metrics,
        "model_summary": model_summary,
        "impact_summary": impact_summary,
        "bounded_summary": bounded_summary,
        "global_weights": global_weights,
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
    impact_summary = analysis.get("impact_summary", pd.DataFrame())
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
        primary_summary = impact_summary if not impact_summary.empty else model_summary
        top_model = primary_summary.iloc[0]
        if not impact_summary.empty:
            headline = (
                f"Top model: `{top_model['model']}` with "
                f"`mean_impact_score="
                f"{_format_metric(top_model['mean_impact_score'])}` "
                "(household-equal impact score)."
            )
        else:
            headline = (
                f"Top model: `{top_model['model']}` with "
                f"`mean_score={_format_metric(top_model['mean_score'])}` "
                f"`mean_exact={_format_metric(top_model['mean_exact'])}` "
                f"and `mean_mae={_format_metric(top_model['mean_mae'])}`."
            )
        lines.extend(
            [
                "## Headline",
                "",
                headline,
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
            "## Summary by model (equal-output-group score)",
            "",
            "| model | mean_score | mean_exact "
            "| mean_within_1pct | mean_within_5pct "
            "| mean_within_10pct | mean_binary_accuracy | mean_mae | total_n |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
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
            f"{_format_metric(row['mean_accuracy'])} | "
            f"{_format_metric(row['mean_mae'])} | "
            f"{int(row['total_n'])} |"
        )

    lines.extend(
        [
            "",
        ]
    )

    bounded_summary = analysis.get("bounded_summary")
    if isinstance(bounded_summary, pd.DataFrame) and not bounded_summary.empty:
        lines.extend(
            [
                "## Bounded global variable weights (headline)",
                "",
                "Households receive equal weight. The score is a weighted "
                "average of continuous row scores; each variable's weight is "
                "the mean across households of "
                "`|ref_ij| / max(|household_net_income_i|, sum_k |ref_ik|)`, "
                "renormalized so weights sum to 1.",
                "",
                "| model | bounded_score | amount_accuracy | participation_accuracy |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for _, row in bounded_summary.iterrows():
            lines.append(
                "| "
                f"{row['model']} | "
                f"{_format_metric(row['bounded_score'])} | "
                f"{_format_metric(row.get('amount_accuracy'))} | "
                f"{_format_metric(row.get('participation_accuracy'))} |"
            )

        lines.extend(["", ""])

    if not impact_summary.empty:
        lines.extend(
            [
                "## Household-equal impact score (30% floor — legacy)",
                "",
                "Retained for comparison with prior reports. Each requested "
                "output row gets a blend of equal weighting and weighting by "
                "absolute reference impact.",
                "",
                "| model | mean_impact_score | mean_household_score "
                "| mean_household_coverage | households |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for _, row in impact_summary.iterrows():
            lines.append(
                "| "
                f"{row['model']} | "
                f"{_format_metric(row['mean_impact_score'])} | "
                f"{_format_metric(row['mean_household_score'])} | "
                f"{_format_metric(row['mean_household_coverage'])} | "
                f"{int(row['households'])} |"
            )

        lines.extend(
            [
                "",
            ]
        )

    lines.extend(
        [
            "## Summary by variable",
            "",
            "Amount variables use the tolerance columns. "
            "Binary coverage flags use `mean_accuracy` as the headline metric.",
            "",
            "| variable | metric_type | mean_score | mean_exact "
            "| mean_within_1pct | mean_within_5pct "
            "| mean_within_10pct | mean_accuracy | mean_mae | total_n |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in variable_summary.iterrows():
        row_metric_type = metric_type_for_output(row["variable"])
        metric_type = (
            "binary_accuracy"
            if row_metric_type == "binary" or row["variable"] in BINARY_PROGRAMS
            else "amount_tolerance"
        )
        lines.append(
            "| "
            f"{row['variable']} | "
            f"{metric_type} | "
            f"{_format_metric(row['mean_score'])} | "
            f"{_format_metric(row['mean_exact'])} | "
            f"{_format_metric(row['mean_within_1pct'])} | "
            f"{_format_metric(row['mean_within_5pct'])} | "
            f"{_format_metric(row['mean_within_10pct'])} | "
            f"{_format_metric(row['mean_accuracy'])} | "
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
    if (
        metric_type_for_output(row["variable"]) == "binary"
        or row["variable"] in BINARY_PROGRAMS
    ):
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
    merged["output_group"] = merged["variable"].map(output_group_id)
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
    for variable, group in merged.groupby("output_group"):
        is_binary = (
            metric_type_for_output(variable) == "binary" or variable in BINARY_PROGRAMS
        )
        item: dict[str, float | int | str | bool | None] = {
            "variable": variable,
            "isBinary": is_binary,
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
        if is_binary:
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
    merged = _prediction_detail_rows(ground_truth, predictions)

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

    impact_summary = analysis.get("impact_summary")
    impact_by_model: dict[str, float] = {}
    if isinstance(impact_summary, pd.DataFrame) and not impact_summary.empty:
        for _, impact_row in impact_summary.iterrows():
            model_name = impact_row.get("model")
            score = impact_row.get("mean_impact_score")
            if model_name is None or pd.isna(score):
                continue
            impact_by_model[str(model_name)] = float(score) * 100

    bounded_summary = analysis.get("bounded_summary")
    bounded_by_model: dict[str, dict[str, float]] = {}
    if isinstance(bounded_summary, pd.DataFrame) and not bounded_summary.empty:
        for _, bounded_row in bounded_summary.iterrows():
            model_name = bounded_row.get("model")
            if model_name is None:
                continue
            entry = {}
            for column, key in (
                ("bounded_score", "bounded"),
                ("amount_accuracy", "amount"),
                ("participation_accuracy", "participation"),
                ("equal_score", "equal"),
                ("aggregate_score", "aggregate"),
            ):
                value = bounded_row.get(column)
                if value is not None and not pd.isna(value):
                    entry[key] = float(value) * 100
            bounded_by_model[str(model_name)] = entry

    model_stats = []
    for _, row in analysis["model_summary"].iterrows():
        output_group_score = _clean_json_number(
            row["mean_score"] * 100
            if not pd.isna(row["mean_score"])
            else row["mean_score"]
        )
        impact_score = impact_by_model.get(str(row["model"]))
        bounded_entry = bounded_by_model.get(str(row["model"]), {})
        bounded_score = bounded_entry.get("bounded")
        # Bounded global variable weights is the new headline. Fall back to the
        # old 30%-floor impact score for backwards compatibility on legacy
        # datasets, and finally to the equal-weight output-group score.
        primary_score = (
            _clean_json_number(bounded_score)
            if bounded_score is not None
            else _clean_json_number(impact_score)
            if impact_score is not None
            else output_group_score
        )
        item = {
            "model": row["model"],
            "condition": "no_tools",
            "score": primary_score,
            "outputGroupScore": output_group_score,
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
        if impact_score is not None:
            item["impactScore"] = impact_score
        if bounded_score is not None:
            item["boundedScore"] = bounded_score
        if "amount" in bounded_entry:
            item["amountAccuracy"] = bounded_entry["amount"]
        if "participation" in bounded_entry:
            item["participationAccuracy"] = bounded_entry["participation"]
        if "equal" in bounded_entry:
            item["equalScore"] = bounded_entry["equal"]
        if "aggregate" in bounded_entry:
            item["aggregateScore"] = bounded_entry["aggregate"]
        model_stats.append({k: v for k, v in item.items() if v is not None})
    model_stats.sort(key=lambda row: row["score"], reverse=True)

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

    scenario_predictions: dict[str, dict[str, dict[str, dict]]] = {}
    for _, row in merged.sort_values(["scenario_id", "variable", "model"]).iterrows():
        scenario_data = scenario_predictions.setdefault(row["scenario_id"], {})
        variable_data = scenario_data.setdefault(row["variable"], {})
        prediction_item: dict[str, float | str | bool | None] = {
            "prediction": _clean_json_number(row["prediction"]),
            "groundTruth": _clean_json_number(row["value"]),
            "error": _clean_json_number(row["error"]),
            "parsed": bool(row["parsed"]),
            "score": _clean_json_number(row["score"] * 100),
        }
        explanation = row.get("explanation")
        if isinstance(explanation, str) and explanation.strip():
            prediction_item["explanation"] = explanation.strip()
        annotation = row.get("annotation")
        if isinstance(annotation, str) and annotation.strip():
            prediction_item["annotation"] = annotation.strip()
        failure_source = row.get("failure_source")
        if isinstance(failure_source, str) and failure_source.strip():
            prediction_item["failureSource"] = failure_source.strip()
        failure_subtype = row.get("failure_subtype")
        if isinstance(failure_subtype, str) and failure_subtype.strip():
            prediction_item["failureSubtype"] = failure_subtype.strip()
        case_annotation = row.get("case_annotation")
        if (
            isinstance(case_annotation, str)
            and case_annotation.strip()
            and row["score"] < 1
        ):
            prediction_item["caseAnnotation"] = case_annotation.strip()
        case_failure_sources = row.get("case_failure_sources")
        if (
            isinstance(case_failure_sources, str)
            and case_failure_sources.strip()
            and row["score"] < 1
        ):
            prediction_item["caseFailureSources"] = case_failure_sources.strip()
        case_failure_subtypes = row.get("case_failure_subtypes")
        if (
            isinstance(case_failure_subtypes, str)
            and case_failure_subtypes.strip()
            and row["score"] < 1
        ):
            prediction_item["caseFailureSubtypes"] = case_failure_subtypes.strip()
        prediction_error = _clean_json_text(row.get("prediction_error"))
        if prediction_error:
            prediction_item["predictionError"] = prediction_error
        reference_explanation = row.get("reference_explanation")
        if isinstance(reference_explanation, str) and reference_explanation.strip():
            prediction_item["referenceExplanation"] = reference_explanation.strip()
        variable_data[row["model"]] = prediction_item

    # Per-variable weights under each of the three weightings, exposed so the
    # leaderboard can render a transparency table without recomputing on the
    # client. ``household`` is the bounded global variable weights (mean of
    # |ref| / max(|net|, Σ|ref|) across households, renormalized to sum to 1).
    # ``aggregate`` is each variable's share of total absolute reference
    # dollars across the benchmark (booleans use their paired ``impact_weight``
    # value). ``equal`` is ``1 / K`` for every variable.
    market_income_map: dict[str, float] = {}
    if "total_income" in scenarios.columns:
        market_income_map = dict(
            zip(
                scenarios["scenario_id"].astype(str),
                pd.to_numeric(scenarios["total_income"], errors="coerce").fillna(0.0),
            )
        )

    def _weights_dict(weights: pd.Series) -> dict[str, float]:
        return {str(name): float(value) for name, value in weights.items()}

    weights_payload = {
        "household": _weights_dict(
            bounded_global_variable_weights(ground_truth, market_income_map)
        ),
        "aggregate": _weights_dict(aggregate_global_variable_weights(ground_truth)),
        "equal": _weights_dict(equal_global_variable_weights(ground_truth)),
    }

    return {
        "country": payload_country,
        "policyengineBundles": policyengine_bundles_for_countries({payload_country}),
        "scenarios": scenario_payload,
        "modelStats": model_stats,
        "programStats": program_stats,
        "heatmap": heatmap,
        "scenarioPredictions": scenario_predictions,
        "globalWeights": weights_payload,
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
        primary_values = [row.get("score") for row in rows.values()]
        output_group_values = [
            row.get("outputGroupScore", row.get("score")) for row in rows.values()
        ]
        item = {
            "model": model,
            "condition": "no_tools",
            "score": _mean(primary_values),
            "outputGroupScore": _mean(output_group_values),
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
            "outputGroupCountryScores": {
                country: float(row["outputGroupScore"])
                for country, row in rows.items()
                if row.get("outputGroupScore") is not None
            },
        }
        accuracy = _mean([row.get("accuracy") for row in rows.values()])
        if accuracy is not None:
            item["accuracy"] = accuracy
        impact_values = [row.get("impactScore") for row in rows.values()]
        if all(value is not None for value in impact_values) and impact_values:
            item["impactScore"] = _mean(impact_values)
            item["impactCountryScores"] = {
                country: float(row["impactScore"])
                for country, row in rows.items()
                if row.get("impactScore") is not None
            }
        # Bounded score is the headline (mirrored in "score"); add the
        # alternative weightings so the leaderboard can switch views.
        for source_key, dest_key, country_key in (
            ("boundedScore", "boundedScore", "boundedCountryScores"),
            ("equalScore", "equalScore", "equalCountryScores"),
            ("aggregateScore", "aggregateScore", "aggregateCountryScores"),
            ("amountAccuracy", "amountAccuracy", "amountCountryScores"),
            (
                "participationAccuracy",
                "participationAccuracy",
                "participationCountryScores",
            ),
        ):
            values = [row.get(source_key) for row in rows.values()]
            if all(value is not None for value in values) and values:
                item[dest_key] = _mean(values)
                item[country_key] = {
                    country: float(row[source_key])
                    for country, row in rows.items()
                    if row.get(source_key) is not None
                }
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
        "policyengineBundles": {
            country: payload.get("policyengineBundles", {}).get(country)
            for country, payload in country_payloads.items()
            if payload.get("policyengineBundles", {}).get(country) is not None
        },
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

    variable_groups = list(
        dict.fromkeys(output_group_id(variable) for variable in variables)
    )
    prompt_map: dict[str, dict[str, dict[str, str]]] = {}
    for _, row in scenarios.dropna(subset=["scenario_json"]).iterrows():
        scenario = scenario_from_dict(json.loads(row["scenario_json"]))
        scenario_variables = expand_programs_for_scenario(variable_groups, scenario)
        tool_prompt = make_no_tools_batch_prompt(
            scenario,
            scenario_variables,
            answer_contract="tool",
        )
        json_prompt = make_no_tools_batch_prompt(
            scenario,
            scenario_variables,
            answer_contract="json",
        )
        prompt_map[row["scenario_id"]] = {
            variable: {
                "tool": tool_prompt,
                "json": json_prompt,
            }
            for variable in scenario_variables
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
    impact_summary_path = output_path / "impact_summary_by_model.csv"
    variable_summary_path = output_path / "summary_by_variable.csv"
    usage_summary_path = output_path / "usage_summary.csv"
    report_path = output_path / "report.md"

    analysis["metrics"].to_csv(metrics_path, index=False)
    analysis["model_summary"].to_csv(model_summary_path, index=False)
    analysis.get("impact_summary", pd.DataFrame()).to_csv(
        impact_summary_path,
        index=False,
    )
    analysis["variable_summary"].to_csv(variable_summary_path, index=False)
    analysis["usage_summary"].to_csv(usage_summary_path, index=False)
    report_path.write_text(render_markdown_report(analysis), encoding="utf-8")

    exported = {
        "metrics": metrics_path,
        "model_summary": model_summary_path,
        "impact_summary": impact_summary_path,
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
