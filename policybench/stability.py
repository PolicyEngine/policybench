"""Repeated-run answer-stability metrics (stability spec layer 1).

Implements docs/stability_spec.md: row-level flip metrics with
scenario-cluster bootstrap CIs, the run-vs-sampling variance decomposition
with its chi-square decision rule, and the cache-contamination guard that
makes repeat runs meaningful (see "Cache discipline" in the spec).
"""

from __future__ import annotations

import json
import math
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from policybench.analysis import (
    BINARY_PROGRAMS,
    binary_flag,
    household_headline_scores,
    row_hit_scores,
)
from policybench.spec import metric_type_for_output

STABILITY_SPEC_VERSION = "2026-08-18-v1"

# Headline mutual-exact tolerance for amount rows, matching the
# prediction-vs-reference exact tolerance in analysis.row_hit_scores.
AMOUNT_EXACT_TOLERANCE = 1.0

DEFAULT_BOOTSTRAP_DRAWS = 1000
DEFAULT_BOOTSTRAP_SEED = 20260818

_BOOTSTRAPPED_METRICS = (
    "unanimous_parse_rate",
    "coverage_flip_rate",
    "invalid_binary_rate",
    "answer_flip_rate",
    "unanimous_exact_answer_rate",
    "verdict_flip_rate_parsed",
    "verdict_flip_rate_all",
    "consistently_wrong_divergent_rate",
)


class CacheContaminationError(RuntimeError):
    """Raised when repeat runs contain cache-served responses."""


def _is_binary_variable(variable: str) -> bool:
    return metric_type_for_output(variable) == "binary" or variable in BINARY_PROGRAMS


def is_parsed_prediction(variable: str, prediction) -> bool:
    """Per-type parse: amounts need a numeric; binary rows need a valid flag."""
    if prediction is None:
        return False
    try:
        if pd.isna(prediction):
            return False
    except (TypeError, ValueError):
        return False
    if _is_binary_variable(variable):
        return binary_flag(prediction) is not None
    try:
        float(prediction)
    except (TypeError, ValueError):
        return False
    return True


def mutually_exact(variable: str, a, b) -> bool:
    """Headline exact tolerance applied between two predictions."""
    if not is_parsed_prediction(variable, a) or not is_parsed_prediction(variable, b):
        return False
    if _is_binary_variable(variable):
        return binary_flag(a) == binary_flag(b)
    return abs(float(a) - float(b)) <= AMOUNT_EXACT_TOLERANCE


def _regularized_lower_gamma(a: float, x: float) -> float:
    """Regularized lower incomplete gamma P(a, x) (series / continued fraction)."""
    if x < 0 or a <= 0:
        raise ValueError("Require x >= 0 and a > 0")
    if x == 0:
        return 0.0
    log_gamma_a = math.lgamma(a)
    if x < a + 1.0:
        # Series representation.
        term = 1.0 / a
        total = term
        n = a
        for _ in range(500):
            n += 1.0
            term *= x / n
            total += term
            if abs(term) < abs(total) * 1e-14:
                break
        return total * math.exp(-x + a * math.log(x) - log_gamma_a)
    # Continued fraction for Q(a, x) = 1 - P(a, x) (Lentz's method).
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    q = math.exp(-x + a * math.log(x) - log_gamma_a) * h
    return 1.0 - q


def chi2_ppf(p: float, df: int) -> float:
    """Chi-square quantile via bisection on the regularized gamma CDF.

    Self-contained because scipy is not a project dependency; accurate to
    ~1e-8 on the small df used for run-count confidence intervals.
    """
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    if df < 1:
        raise ValueError("df must be >= 1")
    a = df / 2.0

    def cdf(x: float) -> float:
        return _regularized_lower_gamma(a, x / 2.0)

    low, high = 0.0, float(df)
    while cdf(high) < p:
        high *= 2.0
        if high > 1e8:
            raise RuntimeError("chi2_ppf failed to bracket the quantile")
    for _ in range(200):
        mid = 0.5 * (low + high)
        if cdf(mid) < p:
            low = mid
        else:
            high = mid
        if high - low < 1e-10 * max(1.0, high):
            break
    return 0.5 * (low + high)


def run_std_ci(std: float, k: int, level: float = 0.90) -> tuple[float, float]:
    """Chi-square CI for a std estimated from ``k`` runs (df = k - 1).

    The upper bound at two-sided ``level`` 0.90 equals the one-sided 95%
    upper bound the spec's decision rule uses.
    """
    if k < 2 or std is None or (isinstance(std, float) and math.isnan(std)):
        return float("nan"), float("nan")
    df = k - 1
    alpha = 1.0 - level
    low = std * math.sqrt(df / chi2_ppf(1.0 - alpha / 2.0, df))
    high = std * math.sqrt(df / chi2_ppf(alpha / 2.0, df))
    return low, high


def _prediction_lookup(repeated_predictions: pd.DataFrame) -> pd.DataFrame:
    required = {"run_id", "model", "scenario_id", "variable", "prediction"}
    missing = required - set(repeated_predictions.columns)
    if missing:
        raise ValueError(f"repeated predictions missing columns: {sorted(missing)}")
    return repeated_predictions


def run_pair_frame(
    repeated_predictions: pd.DataFrame,
    ground_truth: pd.DataFrame,
) -> pd.DataFrame:
    """One row per (model, scenario, variable, run pair) with stability flags.

    Every expected row (from the reference frame) appears for every model and
    run pair; predictions a run never produced count as unparsed, mirroring
    the headline's missing-scores-zero semantics.
    """
    if repeated_predictions.empty or ground_truth.empty:
        return pd.DataFrame(
            columns=[
                "model",
                "scenario_id",
                "variable",
                "run_a",
                "run_b",
                "is_binary",
                "parsed_a",
                "parsed_b",
                "both_parsed",
                "mutually_exact",
                "exact_a",
                "exact_b",
            ]
        )
    preds = _prediction_lookup(repeated_predictions)
    run_ids = sorted(preds["run_id"].dropna().unique())
    models = sorted(preds["model"].dropna().unique())
    by_key: dict[tuple, object] = {
        (row.model, row.run_id, row.scenario_id, row.variable): row.prediction
        for row in preds.itertuples()
    }
    exact_cache: dict[tuple, float] = {}

    def exact_correct(model, run_id, scenario_id, variable, value) -> bool:
        key = (model, run_id, scenario_id, variable)
        if key not in exact_cache:
            prediction = by_key.get(key)
            exact_cache[key] = row_hit_scores(variable, value, prediction)["exact"]
        return bool(exact_cache[key])

    rows = []
    for gt_row in ground_truth.itertuples():
        variable = gt_row.variable
        is_binary = _is_binary_variable(variable)
        for model in models:
            for run_a, run_b in combinations(run_ids, 2):
                pred_a = by_key.get((model, run_a, gt_row.scenario_id, variable))
                pred_b = by_key.get((model, run_b, gt_row.scenario_id, variable))
                parsed_a = is_parsed_prediction(variable, pred_a)
                parsed_b = is_parsed_prediction(variable, pred_b)
                rows.append(
                    {
                        "model": model,
                        "scenario_id": gt_row.scenario_id,
                        "variable": variable,
                        "run_a": run_a,
                        "run_b": run_b,
                        "is_binary": is_binary,
                        "parsed_a": parsed_a,
                        "parsed_b": parsed_b,
                        "both_parsed": parsed_a and parsed_b,
                        "mutually_exact": mutually_exact(variable, pred_a, pred_b),
                        "exact_a": exact_correct(
                            model, run_a, gt_row.scenario_id, variable, gt_row.value
                        ),
                        "exact_b": exact_correct(
                            model, run_b, gt_row.scenario_id, variable, gt_row.value
                        ),
                    }
                )
    return pd.DataFrame(rows)


def _row_level_frame(
    repeated_predictions: pd.DataFrame,
    ground_truth: pd.DataFrame,
) -> pd.DataFrame:
    """One row per (model, scenario, variable) with K-way flags."""
    preds = _prediction_lookup(repeated_predictions)
    run_ids = sorted(preds["run_id"].dropna().unique())
    models = sorted(preds["model"].dropna().unique())
    by_key = {
        (row.model, row.run_id, row.scenario_id, row.variable): row.prediction
        for row in preds.itertuples()
    }
    rows = []
    for gt_row in ground_truth.itertuples():
        variable = gt_row.variable
        is_binary = _is_binary_variable(variable)
        for model in models:
            predictions = [
                by_key.get((model, run_id, gt_row.scenario_id, variable))
                for run_id in run_ids
            ]
            parsed = [is_parsed_prediction(variable, p) for p in predictions]
            numeric_non_flag = False
            if is_binary:
                for p in predictions:
                    if p is None:
                        continue
                    try:
                        if pd.isna(p):
                            continue
                        float(p)
                    except (TypeError, ValueError):
                        continue
                    if binary_flag(p) is None:
                        numeric_non_flag = True
            all_pairwise_exact = all(
                mutually_exact(variable, a, b)
                for a, b in combinations(predictions, 2)
            )
            exact_flags = [
                bool(row_hit_scores(variable, gt_row.value, p)["exact"])
                for p in predictions
            ]
            rows.append(
                {
                    "model": model,
                    "scenario_id": gt_row.scenario_id,
                    "variable": variable,
                    "is_binary": is_binary,
                    "all_parsed": all(parsed),
                    "any_parsed": any(parsed),
                    "invalid_binary": numeric_non_flag,
                    "unanimous_exact_answer": all(parsed) and all_pairwise_exact,
                    "all_wrong": all(parsed) and not any(exact_flags),
                    "wrong_divergent": (
                        all(parsed) and not any(exact_flags) and not all_pairwise_exact
                    ),
                }
            )
    return pd.DataFrame(rows)


def _scenario_aggregates(
    pair_frame: pd.DataFrame,
    row_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Numerator/denominator sums per (model, scenario) for every metric."""
    pair = pair_frame.assign(
        flip_num=lambda df: df["both_parsed"] & ~df["mutually_exact"],
        flip_den=lambda df: df["both_parsed"],
        verdict_parsed_num=lambda df: df["both_parsed"]
        & (df["exact_a"] != df["exact_b"]),
        verdict_parsed_den=lambda df: df["both_parsed"],
        verdict_all_num=lambda df: df["exact_a"] != df["exact_b"],
        verdict_all_den=1,
    )
    pair_agg = (
        pair.groupby(["model", "scenario_id"])[
            [
                "flip_num",
                "flip_den",
                "verdict_parsed_num",
                "verdict_parsed_den",
                "verdict_all_num",
                "verdict_all_den",
            ]
        ]
        .sum()
        .reset_index()
    )
    row = row_frame.assign(
        unanimous_parse_num=lambda df: df["all_parsed"],
        rows_den=1,
        coverage_flip_num=lambda df: df["any_parsed"] & ~df["all_parsed"],
        invalid_binary_num=lambda df: df["is_binary"] & df["invalid_binary"],
        binary_den=lambda df: df["is_binary"],
        unanimous_exact_num=lambda df: df["unanimous_exact_answer"],
        wrong_divergent_num=lambda df: ~df["is_binary"] & df["wrong_divergent"],
        wrong_den=lambda df: ~df["is_binary"] & df["all_wrong"],
    )
    row_agg = (
        row.groupby(["model", "scenario_id"])[
            [
                "unanimous_parse_num",
                "rows_den",
                "coverage_flip_num",
                "invalid_binary_num",
                "binary_den",
                "unanimous_exact_num",
                "wrong_divergent_num",
                "wrong_den",
            ]
        ]
        .sum()
        .reset_index()
    )
    return pair_agg.merge(row_agg, on=["model", "scenario_id"], how="outer").fillna(0)


_METRIC_FRACTIONS = {
    "unanimous_parse_rate": ("unanimous_parse_num", "rows_den"),
    "coverage_flip_rate": ("coverage_flip_num", "rows_den"),
    "invalid_binary_rate": ("invalid_binary_num", "binary_den"),
    "answer_flip_rate": ("flip_num", "flip_den"),
    "unanimous_exact_answer_rate": ("unanimous_exact_num", "rows_den"),
    "verdict_flip_rate_parsed": ("verdict_parsed_num", "verdict_parsed_den"),
    "verdict_flip_rate_all": ("verdict_all_num", "verdict_all_den"),
    "consistently_wrong_divergent_rate": ("wrong_divergent_num", "wrong_den"),
}


def _rates_from_aggregates(aggregates: pd.DataFrame) -> pd.DataFrame:
    sums = aggregates.groupby("model").sum(numeric_only=True)
    out = pd.DataFrame(index=sums.index)
    for metric, (num, den) in _METRIC_FRACTIONS.items():
        denominator = sums[den]
        out[metric] = np.where(denominator > 0, sums[num] / denominator, np.nan)
    return out


def row_stability_by_model(
    repeated_predictions: pd.DataFrame,
    ground_truth: pd.DataFrame,
    n_boot: int = DEFAULT_BOOTSTRAP_DRAWS,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> pd.DataFrame:
    """Row-level stability metrics per model with scenario-cluster bootstrap CIs.

    All rows of a scenario come from a handful of completions per run, so the
    scenario (household), not the row or pair, is the independent unit; CIs
    resample scenarios with replacement, paired across models.
    """
    if (
        repeated_predictions is None
        or repeated_predictions.empty
        or ground_truth.empty
        or "run_id" not in getattr(repeated_predictions, "columns", [])
    ):
        return pd.DataFrame()
    pair_frame = run_pair_frame(repeated_predictions, ground_truth)
    row_frame = _row_level_frame(repeated_predictions, ground_truth)
    if pair_frame.empty or row_frame.empty:
        return pd.DataFrame()
    aggregates = _scenario_aggregates(pair_frame, row_frame)
    point = _rates_from_aggregates(aggregates)

    scenario_ids = sorted(aggregates["scenario_id"].unique())
    rng = np.random.default_rng(seed)
    wide = {
        column: aggregates.pivot_table(
            index="scenario_id", columns="model", values=column, aggfunc="sum"
        )
        .reindex(scenario_ids)
        .fillna(0.0)
        for column in set(
            column for pair in _METRIC_FRACTIONS.values() for column in pair
        )
    }
    models = point.index.tolist()
    boot_values: dict[str, list[np.ndarray]] = {m: [] for m in _METRIC_FRACTIONS}
    n_scenarios = len(scenario_ids)
    for _ in range(max(0, n_boot)):
        draw = rng.integers(0, n_scenarios, size=n_scenarios)
        for metric, (num, den) in _METRIC_FRACTIONS.items():
            num_sum = wide[num].values[draw].sum(axis=0)
            den_sum = wide[den].values[draw].sum(axis=0)
            with np.errstate(invalid="ignore", divide="ignore"):
                boot_values[metric].append(np.where(den_sum > 0, num_sum / den_sum, np.nan))

    run_ids = sorted(repeated_predictions["run_id"].dropna().unique())
    result_rows = []
    for model_index, model in enumerate(models):
        model_pairs = pair_frame[pair_frame["model"] == model]
        row = {
            "model": model,
            "k": len(run_ids),
            "n_rows": int((row_frame["model"] == model).sum()),
            "n_scenarios": n_scenarios,
            "n_run_pairs_parsed": int(model_pairs["both_parsed"].sum()),
            "n_consistently_wrong_amount_rows": int(
                (
                    (row_frame["model"] == model)
                    & ~row_frame["is_binary"]
                    & row_frame["all_wrong"]
                ).sum()
            ),
        }
        for metric in _METRIC_FRACTIONS:
            row[metric] = float(point.loc[model, metric])
            draws = np.array([b[model_index] for b in boot_values[metric]])
            draws = draws[~np.isnan(draws)]
            if len(draws):
                row[f"{metric}_ci_low"] = float(np.percentile(draws, 2.5))
                row[f"{metric}_ci_high"] = float(np.percentile(draws, 97.5))
            else:
                row[f"{metric}_ci_low"] = float("nan")
                row[f"{metric}_ci_high"] = float("nan")
        result_rows.append(row)
    return pd.DataFrame(result_rows)


def stability_variance_decomposition(
    ground_truth: pd.DataFrame,
    repeated_predictions: pd.DataFrame,
    market_income_by_scenario: dict[str, float] | pd.Series,
    country: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Across-run std of the headline score vs household-sampling SE.

    Returns ``(per_model, pooled)``. The decision rule is CI-based: the
    manuscript's sampling-dominance claim is confirmed for a model iff the
    one-sided 95% upper bound on its run std sits below its sampling SE.
    ``pooled`` aggregates squared run deviations across models (M·(K−1) df)
    for a roster-level ratio with usable power at small K, plus each model's
    share of the pooled sum of squares as a homogeneity check.
    """
    empty = pd.DataFrame(), {}
    if (
        repeated_predictions is None
        or repeated_predictions.empty
        or "run_id" not in getattr(repeated_predictions, "columns", [])
        or ground_truth.empty
    ):
        return empty

    run_ids = sorted(repeated_predictions["run_id"].dropna().unique())
    per_run_scores: list[pd.DataFrame] = []
    for run_id in run_ids:
        run_preds = repeated_predictions[repeated_predictions["run_id"] == run_id]
        household = household_headline_scores(
            ground_truth,
            run_preds,
            market_income_by_scenario,
            country=country,
            metric="exact",
        )
        if household.empty:
            continue
        household = household.assign(run_id=run_id)
        per_run_scores.append(household)
    if not per_run_scores:
        return empty
    household_scores = pd.concat(per_run_scores, ignore_index=True)

    run_level = (
        household_scores.groupby(["model", "run_id"])["score"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .rename(columns={"mean": "run_score", "std": "household_std", "count": "n_households"})
    )
    run_level["run_sampling_se"] = run_level["household_std"] / np.sqrt(
        run_level["n_households"]
    )

    rows = []
    pooled_ss = 0.0
    pooled_df = 0
    ss_by_model: dict[str, float] = {}
    sampling_ses = []
    for model, group in run_level.groupby("model"):
        k = len(group)
        run_scores = group["run_score"].to_numpy()
        std = float(np.std(run_scores, ddof=1)) if k > 1 else float("nan")
        ci_low, ci_high = run_std_ci(std, k)
        sampling_se = float(group["run_sampling_se"].mean())
        ratio = std / sampling_se if sampling_se > 0 else float("nan")
        ratio_ci_high = ci_high / sampling_se if sampling_se > 0 else float("nan")
        detectable_floor = (
            math.sqrt((k - 1) / chi2_ppf(0.05, k - 1)) ** -1 if k > 1 else float("nan")
        )
        if k > 1:
            ss = float(((run_scores - run_scores.mean()) ** 2).sum())
            pooled_ss += ss
            pooled_df += k - 1
            ss_by_model[model] = ss
            sampling_ses.append(sampling_se)
        rows.append(
            {
                "model": model,
                "k": k,
                "n_households": int(group["n_households"].iloc[0]),
                "run_score_mean": float(np.mean(run_scores)),
                "run_score_std": std,
                "run_score_std_ci_low": ci_low,
                "run_score_std_ci_high": ci_high,
                "sampling_se": sampling_se,
                "run_to_sampling_ratio": ratio,
                "ratio_ci_high": ratio_ci_high,
                "sampling_dominates": bool(ci_high < sampling_se)
                if not math.isnan(ci_high)
                else False,
                "detectable_ratio_floor": detectable_floor,
            }
        )
    per_model = pd.DataFrame(rows)

    pooled: dict = {}
    if pooled_df > 0:
        pooled_std = math.sqrt(pooled_ss / pooled_df)
        mean_sampling_se = float(np.mean(sampling_ses)) if sampling_ses else float("nan")
        pooled_ci_low = pooled_std * math.sqrt(pooled_df / chi2_ppf(0.95, pooled_df))
        pooled_ci_high = pooled_std * math.sqrt(pooled_df / chi2_ppf(0.05, pooled_df))
        total_ss = pooled_ss if pooled_ss > 0 else float("nan")
        pooled = {
            "n_models": len(ss_by_model),
            "pooled_df": pooled_df,
            "pooled_run_score_std": pooled_std,
            "pooled_run_score_std_ci_low": pooled_ci_low,
            "pooled_run_score_std_ci_high": pooled_ci_high,
            "mean_sampling_se": mean_sampling_se,
            "pooled_run_to_sampling_ratio": (
                pooled_std / mean_sampling_se if mean_sampling_se else float("nan")
            ),
            "pooled_sampling_dominates": bool(pooled_ci_high < mean_sampling_se),
            "homogeneity": {
                model: (ss / total_ss if total_ss else float("nan"))
                for model, ss in sorted(ss_by_model.items())
            },
        }
    return per_model, pooled


def scan_runs_for_cache_hits(runs_dirs: list[str | Path]) -> dict:
    """Scan run directories' spend ledgers for cache-served responses."""
    ledgers = 0
    records = 0
    cache_hits = 0
    runs_without_ledger = 0
    for runs_dir in runs_dirs:
        runs_path = Path(runs_dir)
        for run_csv in sorted(runs_path.glob("run_*.csv")):
            ledger_path = run_csv.with_name(run_csv.name + ".spend.jsonl")
            if not ledger_path.exists():
                runs_without_ledger += 1
                continue
            ledgers += 1
            for line in ledger_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                records += 1
                if record.get("cache_hit"):
                    cache_hits += 1
    return {
        "ledgers": ledgers,
        "records": records,
        "cache_hits": cache_hits,
        "runs_without_ledger": runs_without_ledger,
    }


def assert_cache_free(runs_dirs: list[str | Path]) -> dict:
    """Hard-fail when any repeat run served a response from the disk cache."""
    report = scan_runs_for_cache_hits(runs_dirs)
    if report["cache_hits"]:
        raise CacheContaminationError(
            f"{report['cache_hits']} cache-served responses found across "
            f"{report['ledgers']} spend ledgers. Repeat-run stability metrics "
            "would measure the cache, not the model; rerun the repeats "
            "cache-free (eval-no-tools-repeated no longer enables the disk "
            "cache) before reporting."
        )
    return report


def cross_run_response_id_duplicates(repeated_predictions: pd.DataFrame) -> int | None:
    """Count response ids reused across different runs (residual replay check)."""
    if "provider_response_id" not in repeated_predictions.columns:
        return None
    frame = repeated_predictions.dropna(subset=["provider_response_id"])
    if frame.empty:
        return 0
    per_id = frame.groupby(["model", "provider_response_id"])["run_id"].nunique()
    return int((per_id > 1).sum())


def load_runs_dirs(runs_dirs: list[str | Path]) -> pd.DataFrame:
    """Load and concatenate per-provider-group runs directories.

    Model sets must be disjoint across directories (each model's repeats live
    in exactly one directory) and every directory must contain the same
    run_id set, so K is pinned across the pooled repeat set.
    """
    from policybench.eval_no_tools import load_repeated_predictions

    frames = []
    seen_models: dict[str, Path] = {}
    run_id_sets: dict[Path, frozenset] = {}
    for runs_dir in runs_dirs:
        runs_path = Path(runs_dir)
        frame = load_repeated_predictions(str(runs_path))
        for model in frame["model"].dropna().unique():
            if model in seen_models:
                raise ValueError(
                    f"model {model!r} appears in both {seen_models[model]} and "
                    f"{runs_path}; per-provider-group runs directories must be "
                    "model-disjoint"
                )
            seen_models[str(model)] = runs_path
        run_id_sets[runs_path] = frozenset(frame["run_id"].dropna().unique())
        frames.append(frame)
    distinct = set(run_id_sets.values())
    if len(distinct) > 1:
        detail = {str(path): sorted(ids) for path, ids in run_id_sets.items()}
        raise ValueError(
            f"runs directories disagree on run_id sets (K must be pinned): {detail}"
        )
    return pd.concat(frames, ignore_index=True)
