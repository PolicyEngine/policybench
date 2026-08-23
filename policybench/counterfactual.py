"""Counterfactual consistency (stability spec layer 3).

Builds +$1,000 head-earnings twins of the frozen scenarios, computes
PolicyEngine true deltas for both arms with one engine version, and compares
each model's implied delta to the truth. Metric semantics follow
docs/stability_spec.md, which was rebuilt around the measured truth-delta
distribution (zero binary flips, 247/1,000 nonzero amount rows on the
frozen manifest): the nonzero-true stratum is primary, binary flips report
counts rather than rates, and "large response" replaces cliff language.
"""

from __future__ import annotations

import copy
from itertools import combinations

import numpy as np
import pandas as pd

from policybench.analysis import BINARY_PROGRAMS, binary_flag
from policybench.ground_truth import calculate_ground_truth
from policybench.scenarios import Scenario, scenario_manifest
from policybench.spec import metric_type_for_output, output_group_id
from policybench.stability import is_parsed_prediction

CF_ID_SUFFIX = "__cf1k"
CF_DEFAULT_AMOUNT = 1000.0
CF_PERTURBED_FIELD = "employment_income"

DELTA_EXACT_TOLERANCE = 1.0
# Sign dead zone: |delta| <= $1 counts as "no change".
SIGN_DEAD_ZONE = 1.0
LARGE_RESPONSE_TRUE_CUT = 200.0
LARGE_RESPONSE_PREDICTED_CUT = 100.0
LARGE_RESPONSE_MIN_ROWS = 20

ZERO_DELTA_BASELINE_MODEL = "__zero_delta_baseline__"


def _is_binary_variable(variable: str) -> bool:
    return metric_type_for_output(variable) == "binary" or variable in BINARY_PROGRAMS


def build_counterfactual_twin(
    scenario: Scenario, amount: float = CF_DEFAULT_AMOUNT
) -> Scenario:
    """Return the scenario's perturbed twin (head wages += amount).

    Twins are built at the Scenario level so the embedded id, recomputed
    total_income, and scenario_json stay mutually consistent; the manifest
    loader hard-fails on id mismatches, so the frozen CSV is never edited.
    """
    twin = copy.deepcopy(scenario)
    head = twin.adults[0]
    first_dollar = float(head.employment_income) == 0.0
    head.employment_income = float(head.employment_income) + float(amount)
    twin.id = f"{scenario.id}{CF_ID_SUFFIX}"
    twin.metadata = dict(twin.metadata)
    twin.metadata["counterfactual"] = {
        "base_scenario_id": scenario.id,
        "perturbed_field": CF_PERTURBED_FIELD,
        "person": head.name,
        "perturbation_amount": float(amount),
        "first_dollar": first_dollar,
    }
    return twin


def build_counterfactual_manifest(
    scenarios: list[Scenario], amount: float = CF_DEFAULT_AMOUNT
) -> tuple[list[Scenario], pd.DataFrame]:
    """Build twins and their manifest (extra columns are loader-ignored)."""
    twins = [build_counterfactual_twin(scenario, amount) for scenario in scenarios]
    manifest = scenario_manifest(twins)
    manifest["base_scenario_id"] = [
        twin.metadata["counterfactual"]["base_scenario_id"] for twin in twins
    ]
    manifest["perturbed_field"] = CF_PERTURBED_FIELD
    manifest["perturbation_amount"] = float(amount)
    manifest["first_dollar"] = [
        twin.metadata["counterfactual"]["first_dollar"] for twin in twins
    ]
    return twins, manifest


def compute_truth_deltas(
    base_scenarios: list[Scenario],
    twin_scenarios: list[Scenario],
    programs: list[str],
    year: int,
) -> pd.DataFrame:
    """PolicyEngine true deltas, both arms computed with the installed engine.

    Deltas are rounded to cents before any threshold comparison so knife-edge
    rows cannot enter or leave a cut on sub-cent engine jitter.
    """
    base_truth = calculate_ground_truth(base_scenarios, programs=programs, year=year)
    twin_truth = calculate_ground_truth(twin_scenarios, programs=programs, year=year)
    first_dollar = {
        twin.metadata["counterfactual"]["base_scenario_id"]: twin.metadata[
            "counterfactual"
        ]["first_dollar"]
        for twin in twin_scenarios
    }
    twin_truth = twin_truth.copy()
    twin_truth["base_scenario_id"] = twin_truth["scenario_id"].str.replace(
        CF_ID_SUFFIX, "", regex=False
    )
    merged = base_truth.merge(
        twin_truth[["base_scenario_id", "variable", "value"]],
        left_on=["scenario_id", "variable"],
        right_on=["base_scenario_id", "variable"],
        suffixes=("_base", "_perturbed"),
    )
    out = pd.DataFrame(
        {
            "scenario_id": merged["scenario_id"],
            "variable": merged["variable"],
            "base_value": merged["value_base"],
            "perturbed_value": merged["value_perturbed"],
            "true_delta": ((merged["value_perturbed"] - merged["value_base"]).round(2)),
            "is_binary": merged["variable"].map(_is_binary_variable),
            "output_group": merged["variable"].map(output_group_id),
            "first_dollar": merged["scenario_id"].map(first_dollar).fillna(False),
        }
    )
    return out


def matched_delta_frame(
    base_predictions: pd.DataFrame,
    perturbed_predictions: pd.DataFrame,
    truth_deltas: pd.DataFrame,
) -> pd.DataFrame:
    """One row per (model, base run, scenario, variable) with pred/true deltas.

    When the base arm carries a run_id column (layer-1 repeats), every base
    run is matched, giving a pred-delta distribution instead of one arbitrary
    pairing.
    """
    base = base_predictions.copy()
    if "run_id" not in base.columns:
        base["run_id"] = "base"
    pert = perturbed_predictions.copy()
    pert["base_scenario_id"] = pert["scenario_id"].str.replace(
        CF_ID_SUFFIX, "", regex=False
    )
    pert_lookup = {
        (row.model, row.base_scenario_id, row.variable): row.prediction
        for row in pert.itertuples()
    }
    truth_lookup = truth_deltas.set_index(["scenario_id", "variable"])

    rows = []
    for row in base.itertuples():
        key = (row.scenario_id, row.variable)
        if key not in truth_lookup.index:
            continue
        truth = truth_lookup.loc[key]
        pred_base = row.prediction
        pred_pert = pert_lookup.get((row.model, row.scenario_id, row.variable))
        parsed_base = is_parsed_prediction(row.variable, pred_base)
        parsed_pert = is_parsed_prediction(row.variable, pred_pert)
        both = parsed_base and parsed_pert
        is_binary = bool(truth["is_binary"])
        if both and not is_binary:
            pred_delta = float(pred_pert) - float(pred_base)
        elif both and is_binary:
            pred_delta = float(binary_flag(pred_pert) - binary_flag(pred_base))
        else:
            pred_delta = float("nan")
        rows.append(
            {
                "model": row.model,
                "base_run_id": row.run_id,
                "scenario_id": row.scenario_id,
                "variable": row.variable,
                "is_binary": is_binary,
                "output_group": truth["output_group"],
                "first_dollar": bool(truth["first_dollar"]),
                "both_parsed": both,
                "pred_delta": pred_delta,
                "true_delta": float(truth["true_delta"]),
            }
        )
    return pd.DataFrame(rows)


def _sign(value: float, dead_zone: float = SIGN_DEAD_ZONE) -> int:
    if abs(value) <= dead_zone:
        return 0
    return 1 if value > 0 else -1


def _delta_within_band(pred_delta: float, true_delta: float) -> bool:
    """Band = max($1, 10% |true|): a strict superset of delta-exact.

    Deliberately diverges from the level metrics' zero-floor semantics —
    counterfactual deltas concentrate under $77, where a bare relative band
    would be stricter than exact.
    """
    band = max(DELTA_EXACT_TOLERANCE, 0.10 * abs(true_delta))
    return abs(pred_delta - true_delta) <= band


def reportable_groups(truth_deltas: pd.DataFrame, min_rows: int = 10) -> list[str]:
    """Amount output groups with >= min_rows nonzero-true rows (pre-registered)."""
    amount = truth_deltas[~truth_deltas["is_binary"]]
    nonzero = amount[amount["true_delta"].abs() > DELTA_EXACT_TOLERANCE]
    counts = nonzero.groupby("output_group").size()
    return sorted(counts[counts >= min_rows].index)


def binomial_ci_exact(successes: int, trials: int, level: float = 0.95):
    """Clopper–Pearson interval via bisection on exact binomial tails."""
    if trials <= 0:
        return float("nan"), float("nan")
    alpha = 1.0 - level

    def tail_ge(p: float) -> float:
        # P(X >= successes | p)
        q = 1.0 - p
        total = 0.0
        prob = q**trials
        # iterate pmf via recurrence
        for k in range(0, trials + 1):
            if k >= successes:
                total += prob
            prob = prob * (trials - k) / (k + 1) * (p / q) if q > 0 else 0.0
        return total

    def tail_le(p: float) -> float:
        q = 1.0 - p
        total = 0.0
        prob = q**trials
        for k in range(0, trials + 1):
            if k <= successes:
                total += prob
            prob = prob * (trials - k) / (k + 1) * (p / q) if q > 0 else 0.0
        return total

    if successes == 0:
        low = 0.0
    else:
        lo, hi = 0.0, 1.0
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            if tail_ge(mid) < alpha / 2:
                lo = mid
            else:
                hi = mid
        low = 0.5 * (lo + hi)
    if successes == trials:
        high = 1.0
    else:
        lo, hi = 0.0, 1.0
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            if tail_le(mid) > alpha / 2:
                lo = mid
            else:
                hi = mid
        high = 0.5 * (lo + hi)
    return low, high


def _with_zero_baseline(matched: pd.DataFrame) -> pd.DataFrame:
    """Append the zero-delta baseline as a pseudo-model on the same rows."""
    one_run = matched.drop_duplicates(subset=["scenario_id", "variable"]).copy()
    baseline = one_run.assign(
        model=ZERO_DELTA_BASELINE_MODEL,
        base_run_id="baseline",
        both_parsed=True,
        pred_delta=0.0,
    )
    return pd.concat([matched, baseline], ignore_index=True)


def delta_metrics_by_model(
    matched: pd.DataFrame,
    large_response_min_rows: int = LARGE_RESPONSE_MIN_ROWS,
    group_min_rows: int = 10,
) -> dict[str, pd.DataFrame]:
    """Delta metrics per docs/stability_spec.md layer 3.

    Returns ``summary`` (per model), ``per_group`` (pre-registered groups
    only), ``binary_counts`` (counts, never rates: the +$1k reference
    produces zero flips), ``large_response`` (with suppression flag and
    exact binomial CI), and ``large_response_rows`` (the auditable
    qualifying-row list).
    """
    if matched.empty:
        return {
            "summary": pd.DataFrame(),
            "per_group": pd.DataFrame(),
            "binary_counts": pd.DataFrame(),
            "large_response": pd.DataFrame(),
            "large_response_rows": pd.DataFrame(),
        }
    matched = _with_zero_baseline(matched)
    amount = matched[~matched["is_binary"] & matched["both_parsed"]].copy()
    amount["nonzero_true"] = amount["true_delta"].abs() > DELTA_EXACT_TOLERANCE
    amount["exact"] = (
        amount["pred_delta"] - amount["true_delta"]
    ).abs() <= DELTA_EXACT_TOLERANCE
    amount["within_band"] = [
        _delta_within_band(p, t)
        for p, t in zip(amount["pred_delta"], amount["true_delta"], strict=True)
    ]
    amount["true_sign"] = amount["true_delta"].map(_sign)
    amount["pred_sign"] = amount["pred_delta"].map(_sign)
    amount["sign_match"] = amount["true_sign"] == amount["pred_sign"]
    amount["abs_error"] = (amount["pred_delta"] - amount["true_delta"]).abs()

    summary_rows = []
    per_group_rows = []
    binary_rows = []
    large_rows = []

    truth_rows = matched.drop_duplicates(subset=["scenario_id", "variable"])
    qualifying = truth_rows[
        ~truth_rows["is_binary"]
        & (truth_rows["true_delta"].abs() >= LARGE_RESPONSE_TRUE_CUT)
    ][["scenario_id", "variable", "output_group", "true_delta"]].reset_index(drop=True)

    groups = reportable_groups(
        truth_rows.rename(columns={"output_group": "output_group"}),
        min_rows=group_min_rows,
    )

    for model, group in matched.groupby("model"):
        model_amount = amount[amount["model"] == model]
        nonzero = model_amount[model_amount["nonzero_true"]]
        pos = nonzero[nonzero["true_sign"] > 0]
        neg = nonzero[nonzero["true_sign"] < 0]
        summary_rows.append(
            {
                "model": model,
                "n_matched_rows": int(len(group)),
                "delta_coverage": float(group["both_parsed"].mean()),
                "n_nonzero_true": int(len(nonzero)),
                "delta_exact_rate_nonzero": (
                    float(nonzero["exact"].mean()) if len(nonzero) else float("nan")
                ),
                "delta_within_10pct_rate_nonzero": (
                    float(nonzero["within_band"].mean())
                    if len(nonzero)
                    else float("nan")
                ),
                "delta_mae_nonzero": (
                    float(nonzero["abs_error"].mean()) if len(nonzero) else float("nan")
                ),
                "sign_recall_positive": (
                    float(pos["sign_match"].mean()) if len(pos) else float("nan")
                ),
                "sign_recall_negative": (
                    float(neg["sign_match"].mean()) if len(neg) else float("nan")
                ),
                "delta_exact_rate_amount_pooled": (
                    float(model_amount["exact"].mean())
                    if len(model_amount)
                    else float("nan")
                ),
                "delta_mae_amount_pooled": (
                    float(model_amount["abs_error"].mean())
                    if len(model_amount)
                    else float("nan")
                ),
            }
        )

        for output_group in groups:
            in_group = nonzero[nonzero["output_group"] == output_group]
            if in_group.empty:
                continue
            per_group_rows.append(
                {
                    "model": model,
                    "output_group": output_group,
                    "n_nonzero_true": int(len(in_group)),
                    "delta_exact_rate": float(in_group["exact"].mean()),
                    "delta_within_10pct_rate": float(in_group["within_band"].mean()),
                    "delta_mae": float(in_group["abs_error"].mean()),
                    "sign_agreement": float(in_group["sign_match"].mean()),
                }
            )

        model_binary = group[group["is_binary"] & group["both_parsed"]]
        reference_flips = int(
            (
                model_binary.drop_duplicates(subset=["scenario_id", "variable"])[
                    "true_delta"
                ].abs()
                > 0
            ).sum()
        )
        model_flips = int((model_binary["pred_delta"].abs() > 0).sum())
        binary_rows.append(
            {
                "model": model,
                "n_binary_rows": int(len(model_binary)),
                "n_reference_flips": reference_flips,
                "n_model_flips": model_flips,
            }
        )

        model_large = model_amount.merge(
            qualifying[["scenario_id", "variable"]],
            on=["scenario_id", "variable"],
        )
        detected = model_large[
            (model_large["pred_sign"] == model_large["true_sign"])
            & (model_large["pred_delta"].abs() >= LARGE_RESPONSE_PREDICTED_CUT)
        ]
        n_qualifying = int(len(model_large))
        ci_low, ci_high = binomial_ci_exact(len(detected), n_qualifying)
        large_rows.append(
            {
                "model": model,
                "true_cut_usd": LARGE_RESPONSE_TRUE_CUT,
                "predicted_cut_usd": LARGE_RESPONSE_PREDICTED_CUT,
                "n_qualifying_rows": n_qualifying,
                "n_detected": int(len(detected)),
                "detection_rate": (
                    len(detected) / n_qualifying if n_qualifying else float("nan")
                ),
                "detection_rate_ci_low": ci_low,
                "detection_rate_ci_high": ci_high,
                "suppressed": n_qualifying < large_response_min_rows,
            }
        )

    return {
        "summary": pd.DataFrame(summary_rows),
        "per_group": pd.DataFrame(per_group_rows),
        "binary_counts": pd.DataFrame(binary_rows),
        "large_response": pd.DataFrame(large_rows),
        "large_response_rows": qualifying,
    }


def noise_floor_frame(
    repeated_base_predictions: pd.DataFrame,
    truth_deltas: pd.DataFrame,
) -> pd.DataFrame:
    """Base-vs-base null deltas from layer-1 repeats (true delta ≡ 0).

    Produces the same shape as matched_delta_frame so every signal statistic
    can be recomputed on its exact row subset with a zero true delta — the
    row-matched noise floor the spec requires.
    """
    preds = repeated_base_predictions
    if "run_id" not in preds.columns:
        raise ValueError("noise floor needs repeated base runs with run_id")
    run_ids = sorted(preds["run_id"].dropna().unique())
    if len(run_ids) < 2:
        raise ValueError("noise floor needs at least two base runs")
    lookup = {
        (row.model, row.run_id, row.scenario_id, row.variable): row.prediction
        for row in preds.itertuples()
    }
    truth_lookup = truth_deltas.set_index(["scenario_id", "variable"])
    models = sorted(preds["model"].dropna().unique())
    rows = []
    for (scenario_id, variable), truth in truth_lookup.iterrows():
        is_binary = bool(truth["is_binary"])
        for model in models:
            for run_a, run_b in combinations(run_ids, 2):
                pred_a = lookup.get((model, run_a, scenario_id, variable))
                pred_b = lookup.get((model, run_b, scenario_id, variable))
                parsed = is_parsed_prediction(
                    variable, pred_a
                ) and is_parsed_prediction(variable, pred_b)
                if parsed and not is_binary:
                    delta = float(pred_b) - float(pred_a)
                elif parsed and is_binary:
                    delta = float(binary_flag(pred_b) - binary_flag(pred_a))
                else:
                    delta = float("nan")
                rows.append(
                    {
                        "model": model,
                        "base_run_id": f"{run_a}|{run_b}",
                        "scenario_id": scenario_id,
                        "variable": variable,
                        "is_binary": is_binary,
                        "output_group": truth["output_group"],
                        "first_dollar": bool(truth["first_dollar"]),
                        "both_parsed": parsed,
                        "pred_delta": delta,
                        "true_delta": 0.0,
                    }
                )
    return pd.DataFrame(rows)


def signal_vs_noise_test(
    matched: pd.DataFrame,
    floor: pd.DataFrame,
    n_boot: int = 1000,
    seed: int = 20260818,
) -> pd.DataFrame:
    """Scenario-cluster bootstrap of (signal − floor) median |delta|.

    Signal: median |pred_delta| on nonzero-true amount rows of the matched
    frame. Floor: median |pred_delta| on the same rows of the base-vs-base
    frame. "Indistinguishable from repeat noise" iff the 95% interval of
    the difference covers 0.
    """
    rows = []
    rng = np.random.default_rng(seed)
    key_cols = ["scenario_id", "variable"]
    signal_rows = matched[
        ~matched["is_binary"]
        & matched["both_parsed"]
        & (matched["true_delta"].abs() > DELTA_EXACT_TOLERANCE)
        & (matched["model"] != ZERO_DELTA_BASELINE_MODEL)
    ]
    for model, signal in signal_rows.groupby("model"):
        keys = signal[key_cols].drop_duplicates()
        floor_rows = floor.merge(keys, on=key_cols)
        floor_rows = floor_rows[
            (floor_rows["model"] == model) & floor_rows["both_parsed"]
        ]
        if signal.empty or floor_rows.empty:
            continue
        scenarios = sorted(signal["scenario_id"].unique())
        signal_by_scenario = {
            sid: group["pred_delta"].abs().to_numpy()
            for sid, group in signal.groupby("scenario_id")
        }
        floor_by_scenario = {
            sid: group["pred_delta"].abs().to_numpy()
            for sid, group in floor_rows.groupby("scenario_id")
        }
        point_signal = float(np.median(signal["pred_delta"].abs()))
        point_floor = float(np.median(floor_rows["pred_delta"].abs()))
        diffs = []
        n = len(scenarios)
        for _ in range(max(0, n_boot)):
            draw = rng.integers(0, n, size=n)
            sig_values = np.concatenate(
                [signal_by_scenario[scenarios[i]] for i in draw]
            )
            floor_values = np.concatenate(
                [floor_by_scenario.get(scenarios[i], np.array([])) for i in draw]
            )
            if not len(floor_values):
                continue
            diffs.append(float(np.median(sig_values) - np.median(floor_values)))
        if diffs:
            ci_low, ci_high = np.percentile(diffs, [2.5, 97.5])
        else:
            ci_low = ci_high = float("nan")
        rows.append(
            {
                "model": model,
                "signal_median_abs_delta": point_signal,
                "noise_floor_median_abs_delta": point_floor,
                "difference": point_signal - point_floor,
                "difference_ci_low": float(ci_low),
                "difference_ci_high": float(ci_high),
                "distinguishable_from_noise": bool(ci_low > 0 or ci_high < 0),
            }
        )
    return pd.DataFrame(rows)
