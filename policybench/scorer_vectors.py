"""Deterministic cross-language parity vectors for the canonical leaderboard scorer.

The leaderboard's per-model score is computed twice: once in Python
(:mod:`policybench.analysis`) for the published headline / paper, and once in
TypeScript (``app/src/lib/canonicalScore.ts``) for the interactive app. Those two
implementations must agree exactly — scorer drift between them would silently
change the published rankings.

This module generates a fixed battery of synthetic ``scenarioPredictions``
payloads plus their expected per-model scores, computed by the **Python**
canonical scorer. ``app/tests/canonicalScore.test.ts`` replays the payloads
through the TypeScript scorer and asserts it reproduces the expected scores,
turning the equivalence into a CI-enforced invariant.

The generator is fully deterministic (seeded ``numpy`` RNG, no wall-clock or
filesystem inputs), so regenerating the fixture is reproducible and reviewable.

Expected-value semantics
------------------------
The expected scores are produced by :func:`canonical_filtered_scores`, which
implements exactly the path the app relies on: take the **exported** output-group
weights (computed once over the full population), subset the ground-truth rows by
the program filter and reference filter, split each surviving group's weight
across its concrete rows inside a household, renormalize within the household,
score each row, and average households with equal weight. On the unfiltered,
all-positive-weight case this reproduces :func:`policybench.analysis.
household_headline_scores` / :func:`policybench.analysis.bounded_household_scores`
byte-for-byte (verified in ``tests/test_scorer_vectors.py``).

Known Python/TypeScript divergence
----------------------------------
There is exactly one case where the two scorers disagree, and it is pinned and
flagged here rather than hidden. When the entire kept active set of a household
carries **zero** output-group weight (so the within-household renormalization
denominator is 0), the Python scorer still counts that household in the
equal-household mean (with score 0), while the TypeScript scorer skips it
(``if (denominator <= 0) continue``). This is reachable in production only via an
output group whose population weight is exactly 0 (e.g. ``local_income_tax`` in
the US payload). Vectors that exercise this carry ``"tsDivergence": true`` and
record both the Python expectation and the value the current TypeScript scorer
produces; the TypeScript test asserts the documented (divergent) behavior so the
gap stays visible.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from policybench.analysis import (
    bounded_row_score,
    row_hit_scores,
)
from policybench.spec import output_group_id

# Schema version for the emitted fixture. Bump when the vector shape changes so a
# stale fixture is an obvious mismatch in review.
FIXTURE_VERSION = 1

# Default committed location of the fixture the TypeScript parity test loads.
DEFAULT_FIXTURE_PATH = "app/tests/fixtures/scorer_vectors.json"

# Deterministic seed for the committed fixture. Changing this regenerates every
# vector, so keep it stable unless intentionally refreshing the fixture.
DEFAULT_SEED = 20260610

# Field names exposed to the app's scoring toggle.
SCORE_FIELDS = ("exact", "within1pct", "continuous")

# Map an app score field to the Python row-hit metric key.
_FIELD_TO_HIT_METRIC = {"exact": "exact", "within1pct": "within_1pct"}

# Amount outputs whose Python spec metric type is "amount" and whose TypeScript
# classification (``isBinaryVariable``) is also amount, for the US country.
_AMOUNT_VARIABLES = (
    "snap",
    "eitc",
    "income_tax",
    "ctc",
    "ssi",
    "social_security",
    "tanf",
)

# Concrete person-eligibility outputs. Both scorers classify these as binary and
# map them to the same output group (``person_<program>_eligible``).
_BINARY_VARIABLES = (
    "head_medicaid_eligible",
    "spouse_medicaid_eligible",
    "child1_medicaid_eligible",
    "head_chip_eligible",
    "child1_wic_eligible",
    "child2_wic_eligible",
    "adult1_medicare_eligible",
    "child1_head_start_eligible",
    "child2_head_start_eligible",
    "child1_early_head_start_eligible",
)

_MODELS = ("model_alpha", "model_beta", "model_gamma")

_REFERENCE_FILTERS = ("all", "positives", "zeros")


def _round10(value: float) -> float:
    """Round to 10 decimals, normalizing -0.0 to 0.0 for stable JSON."""
    rounded = round(float(value), 10)
    return 0.0 if rounded == 0.0 else rounded


def canonical_filtered_scores(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
    weights_by_group: dict[str, float],
    active_groups: set[str],
    reference_filter: str,
    field: str,
) -> tuple[dict[str, float], dict[str, bool]]:
    """Canonical per-model score (0–100) under a program + reference filter.

    Implements the exact path the app uses: exported output-group weights
    (already computed over the full population), filter rows, split group weights
    across concrete rows per household, renormalize within each household, score
    each row, and average households with equal weight.

    Returns ``(scores, household_zero_weight)`` where ``scores`` maps model →
    score and ``household_zero_weight`` maps scenario_id → whether that household
    contributed only zero-weight kept rows (denominator 0). The latter is what
    drives the documented TypeScript divergence.
    """
    if field not in SCORE_FIELDS:
        raise ValueError(f"Unknown score field {field!r}. Valid: {SCORE_FIELDS}.")

    gt = ground_truth.copy()
    gt["output_group"] = gt["variable"].map(output_group_id)
    keep = gt["output_group"].isin(active_groups)
    if reference_filter == "positives":
        keep &= gt["value"] != 0
    elif reference_filter == "zeros":
        keep &= gt["value"] == 0
    elif reference_filter != "all":
        raise ValueError(
            f"Unknown reference filter {reference_filter!r}. "
            f"Valid: {_REFERENCE_FILTERS}."
        )
    gt = gt[keep].copy()

    models = sorted(predictions["model"].dropna().unique())
    if gt.empty or not models:
        return {}, {}

    weights_series = pd.Series(weights_by_group, dtype=float)

    # Split each group's weight across its concrete rows inside a household, then
    # renormalize within the household. This mirrors
    # ``analysis._row_weights_for_ground_truth`` but is inlined so the fixture
    # generator does not depend on a private helper's signature.
    rows = gt[["scenario_id", "variable", "output_group"]].drop_duplicates().copy()
    rows["group_weight"] = rows["output_group"].map(weights_series).fillna(0.0)
    counts = rows.groupby(["scenario_id", "output_group"])["variable"].transform(
        "count"
    )
    rows["raw_weight"] = np.where(counts > 0, rows["group_weight"] / counts, 0.0)
    scenario_sums = rows.groupby("scenario_id")["raw_weight"].transform("sum")
    rows["weight"] = np.where(
        scenario_sums > 0, rows["raw_weight"] / scenario_sums, 0.0
    )

    household_zero_weight = {
        str(scenario_id): bool(total <= 0)
        for scenario_id, total in rows.groupby("scenario_id")["raw_weight"]
        .sum()
        .items()
    }

    row_weight = rows.set_index(["scenario_id", "variable"])["weight"]

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
    if field == "continuous":
        merged["row_score"] = [
            bounded_row_score(variable, truth, prediction)
            for variable, truth, prediction in zip(
                merged["variable"], merged["value"], merged["prediction"], strict=True
            )
        ]
    else:
        metric = _FIELD_TO_HIT_METRIC[field]
        merged["row_score"] = [
            row_hit_scores(variable, truth, prediction)[metric]
            for variable, truth, prediction in zip(
                merged["variable"], merged["value"], merged["prediction"], strict=True
            )
        ]
    merged["weight"] = [
        float(row_weight.get((scenario_id, variable), 0.0))
        for scenario_id, variable in zip(
            merged["scenario_id"], merged["variable"], strict=True
        )
    ]
    merged["weighted"] = merged["row_score"] * merged["weight"]

    household = merged.groupby(["model", "scenario_id"])["weighted"].sum().reset_index()
    # Python averages over every kept household with equal weight (including the
    # zero-weight households, which contribute score 0). The TypeScript scorer
    # instead skips zero-denominator households entirely — that difference is the
    # documented divergence, captured separately via ``household_zero_weight``.
    scores = {
        str(model): float(group["weighted"].mean()) * 100.0
        for model, group in household.groupby("model")
    }
    return scores, household_zero_weight


def typescript_filtered_scores(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
    weights_by_group: dict[str, float],
    active_groups: set[str],
    reference_filter: str,
    field: str,
) -> dict[str, float]:
    """Model → score under the *TypeScript* household-skipping convention.

    Identical to :func:`canonical_filtered_scores` except households whose entire
    kept active set carries zero output-group weight are dropped from the
    equal-household mean (and a model present in no surviving household is
    omitted). Used only to record the expected value for vectors that exercise
    the documented divergence.
    """
    gt = ground_truth.copy()
    gt["output_group"] = gt["variable"].map(output_group_id)
    keep = gt["output_group"].isin(active_groups)
    if reference_filter == "positives":
        keep &= gt["value"] != 0
    elif reference_filter == "zeros":
        keep &= gt["value"] == 0
    gt = gt[keep].copy()
    models = sorted(predictions["model"].dropna().unique())
    if gt.empty or not models:
        return {}

    weights_series = pd.Series(weights_by_group, dtype=float)
    rows = gt[["scenario_id", "variable", "output_group"]].drop_duplicates().copy()
    rows["group_weight"] = rows["output_group"].map(weights_series).fillna(0.0)
    counts = rows.groupby(["scenario_id", "output_group"])["variable"].transform(
        "count"
    )
    rows["raw_weight"] = np.where(counts > 0, rows["group_weight"] / counts, 0.0)
    denom = rows.groupby("scenario_id")["raw_weight"].transform("sum")
    rows["weight"] = np.where(denom > 0, rows["raw_weight"] / denom, 0.0)
    kept_scenarios = {
        str(scenario_id)
        for scenario_id, total in rows.groupby("scenario_id")["raw_weight"]
        .sum()
        .items()
        if total > 0
    }
    row_weight = rows.set_index(["scenario_id", "variable"])["weight"]

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
    merged = merged[merged["scenario_id"].astype(str).isin(kept_scenarios)]
    if merged.empty:
        return {}
    if field == "continuous":
        merged["row_score"] = [
            bounded_row_score(variable, truth, prediction)
            for variable, truth, prediction in zip(
                merged["variable"], merged["value"], merged["prediction"], strict=True
            )
        ]
    else:
        metric = _FIELD_TO_HIT_METRIC[field]
        merged["row_score"] = [
            row_hit_scores(variable, truth, prediction)[metric]
            for variable, truth, prediction in zip(
                merged["variable"], merged["value"], merged["prediction"], strict=True
            )
        ]
    merged["weight"] = [
        float(row_weight.get((scenario_id, variable), 0.0))
        for scenario_id, variable in zip(
            merged["scenario_id"], merged["variable"], strict=True
        )
    ]
    merged["weighted"] = merged["row_score"] * merged["weight"]
    household = merged.groupby(["model", "scenario_id"])["weighted"].sum().reset_index()
    return {
        str(model): float(group["weighted"].mean()) * 100.0
        for model, group in household.groupby("model")
    }


def _scenario_predictions_payload(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    """Build the dense ``scenarioPredictions`` payload the app consumes.

    Dense means every (scenario, variable, model) cell exists; a model that did
    not predict a variable still gets a cell with ``prediction: null``. This
    matches ``analysis.export_dashboard_data``: it iterates a
    ``ground_truth × models`` grid, so the app never sees a truly missing cell.
    """
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
    payload: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for _, row in merged.sort_values(["scenario_id", "variable", "model"]).iterrows():
        scenario = payload.setdefault(str(row["scenario_id"]), {})
        variable = scenario.setdefault(str(row["variable"]), {})
        prediction = row["prediction"]
        variable[str(row["model"])] = {
            "prediction": (
                None
                if prediction is None or pd.isna(prediction)
                else _round10(prediction)
            ),
            "groundTruth": _round10(row["value"]),
        }
    return payload


def _weights_payload(weights_by_group: dict[str, float]) -> dict[str, float]:
    return {group: _round10(weight) for group, weight in weights_by_group.items()}


def _round_frame_values(
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
    weights_by_group: dict[str, float],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    """Round all scorer inputs to the fixture's 10-decimal serialization grid.

    The expected scores MUST be computed from exactly the values that land in the
    serialized payload — rounded ground-truth, rounded predictions, and rounded
    weights — otherwise the TypeScript scorer (which only sees the rounded
    values) and Python (which would otherwise see full precision) could differ by
    more than the 1e-9 comparison tolerance, since a 1e-10 weight rounding scales
    by ~100 in a percentage score. Rounding inputs first makes the only residual
    difference float summation order, which is far below 1e-9.
    """
    gt = ground_truth.copy()
    gt["value"] = gt["value"].map(_round10)
    pred = predictions.copy()
    pred["prediction"] = pred["prediction"].map(
        lambda value: None if value is None or pd.isna(value) else _round10(value)
    )
    weights = {group: _round10(weight) for group, weight in weights_by_group.items()}
    return gt, pred, weights


def _vector(
    *,
    name: str,
    description: str,
    ground_truth: pd.DataFrame,
    predictions: pd.DataFrame,
    weights_by_group: dict[str, float],
    active_groups: set[str],
    reference_filter: str,
    field: str,
    weights_view: str = "household",
    ts_divergence: bool = False,
) -> dict[str, Any]:
    """Assemble one parity vector with Python-computed expected scores.

    Inputs are rounded to the serialization grid before scoring so the expected
    values match what the TypeScript scorer computes from the written payload.
    """
    ground_truth, predictions, weights_by_group = _round_frame_values(
        ground_truth, predictions, weights_by_group
    )
    expected, household_zero_weight = canonical_filtered_scores(
        ground_truth,
        predictions,
        weights_by_group,
        active_groups,
        reference_filter,
        field,
    )
    scenario_predictions = _scenario_predictions_payload(ground_truth, predictions)
    # Expose all three views with the same weights so the TypeScript side, which
    # reads ``globalWeights[view]``, can pick the requested one. Only the chosen
    # view's numbers matter for the assertion.
    global_weights = {
        view: _weights_payload(weights_by_group)
        for view in ("household", "aggregate", "equal")
    }
    vector: dict[str, Any] = {
        "name": name,
        "description": description,
        "country": "us",
        "weightsView": weights_view,
        "programFilter": sorted(active_groups),
        "referenceFilter": reference_filter,
        "field": field,
        "scenarioPredictions": scenario_predictions,
        "globalWeights": global_weights,
        "expectedScores": {model: _round10(score) for model, score in expected.items()},
        "tsDivergence": ts_divergence,
    }
    if ts_divergence:
        ts_scores = typescript_filtered_scores(
            ground_truth,
            predictions,
            weights_by_group,
            active_groups,
            reference_filter,
            field,
        )
        vector["divergenceReason"] = (
            "A household's entire kept active set carries zero output-group "
            "weight, so the within-household renormalization denominator is 0. "
            "Python counts the household in the equal-household mean (score 0); "
            "the TypeScript scorer skips it (denominator <= 0 guard). Reachable "
            "in production via a zero-population-weight output group such as "
            "local_income_tax (US)."
        )
        vector["zeroWeightScenarios"] = sorted(
            scenario_id for scenario_id, zero in household_zero_weight.items() if zero
        )
        vector["typescriptScores"] = {
            model: _round10(score) for model, score in ts_scores.items()
        }
    return vector


# --------------------------------------------------------------------------- #
# Synthetic case construction.
# --------------------------------------------------------------------------- #


def _positive_weights_for(
    variables: list[str], rng: np.random.Generator
) -> dict[str, float]:
    """Strictly-positive, normalized output-group weights for the given outputs.

    Positivity guarantees TypeScript/Python parity (the divergence only occurs at
    zero weight). Weights are normalized to sum to 1 like the exported payloads.
    """
    groups = list(dict.fromkeys(output_group_id(v) for v in variables))
    raw = {group: float(rng.uniform(0.2, 1.0)) for group in groups}
    total = sum(raw.values())
    return {group: weight / total for group, weight in raw.items()}


def _random_amount_truth(rng: np.random.Generator, *, allow_zero: bool = True) -> float:
    if allow_zero and rng.random() < 0.35:
        return 0.0
    return float(rng.integers(1, 30_001))


def _random_amount_prediction(rng: np.random.Generator, truth: float) -> float | None:
    roll = rng.random()
    if roll < 0.15:
        return None
    if truth == 0.0:
        return 0.0 if rng.random() < 0.5 else float(rng.integers(1, 6))
    shape = rng.random()
    if shape < 0.30:
        return truth  # exact
    if shape < 0.55:
        return float(round(truth * (1 + rng.uniform(-0.008, 0.008)), 2))  # within 1%
    if shape < 0.78:
        return float(round(truth * (1 + rng.uniform(-0.09, 0.09)), 2))  # within 10%
    return float(rng.integers(0, 40_001))  # far


def _random_binary_prediction(rng: np.random.Generator) -> float | None:
    roll = rng.random()
    if roll < 0.12:
        return None
    if roll < 0.20:
        return float(round(rng.random(), 2))  # contract-violating non-0/1 answer
    return float(rng.integers(0, 2))


def _build_case(
    rng: np.random.Generator,
    *,
    n_scenarios: int,
    variables: list[str],
    force_all_zero_amounts: bool = False,
    sparse_rows: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate ground-truth and prediction frames for one synthetic case."""
    gt_rows: list[dict[str, Any]] = []
    pred_rows: list[dict[str, Any]] = []
    for index in range(n_scenarios):
        scenario_id = f"s{index}"
        if sparse_rows:
            present = [v for v in variables if rng.random() < 0.85]
            if not present:
                present = [variables[0]]
        else:
            present = list(variables)
        for variable in present:
            is_binary = variable in _BINARY_VARIABLES
            if is_binary:
                truth = float(rng.integers(0, 2))
            elif force_all_zero_amounts:
                truth = 0.0
            else:
                truth = _random_amount_truth(rng)
            gt_rows.append(
                {"scenario_id": scenario_id, "variable": variable, "value": truth}
            )
            for model in _MODELS:
                prediction = (
                    _random_binary_prediction(rng)
                    if is_binary
                    else _random_amount_prediction(rng, truth)
                )
                pred_rows.append(
                    {
                        "model": model,
                        "scenario_id": scenario_id,
                        "variable": variable,
                        "prediction": (
                            None if prediction is None else float(prediction)
                        ),
                    }
                )
    return pd.DataFrame(gt_rows), pd.DataFrame(pred_rows)


def build_vectors(seed: int = 20260610) -> dict[str, Any]:
    """Build the full deterministic fixture payload.

    The vector set covers: unfiltered full-program vectors, single-program
    vectors, positives-only and zeros-only vectors, all-zero-reference vectors,
    vectors with models missing rows (null predictions in a dense payload), and
    vectors whose weights omit some present groups — plus the flagged
    zero-weight divergence vectors.
    """
    rng = np.random.default_rng(seed)
    vectors: list[dict[str, Any]] = []

    mixed = list(_AMOUNT_VARIABLES[:4]) + list(_BINARY_VARIABLES[:4])

    # 1. Unfiltered, full program set, all three fields.
    for field in SCORE_FIELDS:
        gt, pred = _build_case(
            rng, n_scenarios=int(rng.integers(4, 8)), variables=mixed
        )
        weights = _positive_weights_for(mixed, rng)
        groups = set(weights)
        vectors.append(
            _vector(
                name=f"unfiltered_full_{field}",
                description=(
                    "Full program set, all reference cases — the canonical "
                    "headline path with no filtering."
                ),
                ground_truth=gt,
                predictions=pred,
                weights_by_group=weights,
                active_groups=groups,
                reference_filter="all",
                field=field,
            )
        )

    # 2. Single-program vectors (one active output group).
    for field in SCORE_FIELDS:
        variables = list(_AMOUNT_VARIABLES[:3]) + list(_BINARY_VARIABLES[:3])
        gt, pred = _build_case(
            rng, n_scenarios=int(rng.integers(4, 8)), variables=variables
        )
        weights = _positive_weights_for(variables, rng)
        groups = sorted(weights)
        single = {groups[int(rng.integers(0, len(groups)))]}
        vectors.append(
            _vector(
                name=f"single_program_{field}",
                description="One active output group; weights renormalize to it.",
                ground_truth=gt,
                predictions=pred,
                weights_by_group=weights,
                active_groups=single,
                reference_filter="all",
                field=field,
            )
        )

    # 3. Positives-only and zeros-only vectors.
    for reference_filter in ("positives", "zeros"):
        for field in SCORE_FIELDS:
            gt, pred = _build_case(
                rng, n_scenarios=int(rng.integers(5, 8)), variables=mixed
            )
            weights = _positive_weights_for(mixed, rng)
            vectors.append(
                _vector(
                    name=f"{reference_filter}_only_{field}",
                    description=(
                        f"Reference filter = {reference_filter}; rows are subset "
                        "before the canonical scorer runs."
                    ),
                    ground_truth=gt,
                    predictions=pred,
                    weights_by_group=weights,
                    active_groups=set(weights),
                    reference_filter=reference_filter,
                    field=field,
                )
            )

    # 4. All-zero-reference amount vectors (every amount truth is 0).
    for field in SCORE_FIELDS:
        amount_only = list(_AMOUNT_VARIABLES[:4])
        gt, pred = _build_case(
            rng,
            n_scenarios=int(rng.integers(4, 7)),
            variables=amount_only,
            force_all_zero_amounts=True,
        )
        weights = _positive_weights_for(amount_only, rng)
        vectors.append(
            _vector(
                name=f"all_zero_reference_{field}",
                description=(
                    "Every amount reference is 0; exercises the zero-reference "
                    "row-score branch (exact-zero credit)."
                ),
                ground_truth=gt,
                predictions=pred,
                weights_by_group=weights,
                active_groups=set(weights),
                reference_filter="all",
                field=field,
            )
        )

    # 5. Models-missing-rows vectors. Sparse generation + dense payload means
    #    each missing (model, row) becomes a null-prediction cell.
    for field in SCORE_FIELDS:
        variables = list(_AMOUNT_VARIABLES[:3]) + list(_BINARY_VARIABLES[:5])
        # Force heavy sparsity so models genuinely miss rows.
        gt_rows: list[dict[str, Any]] = []
        pred_rows: list[dict[str, Any]] = []
        n_scenarios = int(rng.integers(5, 8))
        for index in range(n_scenarios):
            scenario_id = f"s{index}"
            present = [v for v in variables if rng.random() < 0.8] or [variables[0]]
            for variable in present:
                is_binary = variable in _BINARY_VARIABLES
                truth = (
                    float(rng.integers(0, 2))
                    if is_binary
                    else _random_amount_truth(rng)
                )
                gt_rows.append(
                    {"scenario_id": scenario_id, "variable": variable, "value": truth}
                )
                for model in _MODELS:
                    # 30% chance a given model omits this row entirely.
                    if rng.random() < 0.30:
                        continue
                    prediction = (
                        _random_binary_prediction(rng)
                        if is_binary
                        else _random_amount_prediction(rng, truth)
                    )
                    pred_rows.append(
                        {
                            "model": model,
                            "scenario_id": scenario_id,
                            "variable": variable,
                            "prediction": (
                                None if prediction is None else float(prediction)
                            ),
                        }
                    )
        gt = pd.DataFrame(gt_rows)
        pred = pd.DataFrame(pred_rows)
        weights = _positive_weights_for(variables, rng)
        vectors.append(
            _vector(
                name=f"models_missing_rows_{field}",
                description=(
                    "Some (model, row) cells are absent from predictions; the "
                    "dense payload represents them as null-prediction cells that "
                    "score 0 but still carry weight."
                ),
                ground_truth=gt,
                predictions=pred,
                weights_by_group=weights,
                active_groups=set(weights),
                reference_filter="all",
                field=field,
            )
        )

    # 6. Weights whose groups do not all appear in the data (and vice versa):
    #    weight map includes extra groups never present, and one present group is
    #    omitted from the weights (so its rows get weight 0 but the household
    #    still has positively-weighted rows).
    for field in SCORE_FIELDS:
        variables = list(_AMOUNT_VARIABLES[:4]) + list(_BINARY_VARIABLES[:3])
        gt, pred = _build_case(
            rng,
            n_scenarios=int(rng.integers(4, 7)),
            variables=variables,
            sparse_rows=False,
        )
        present_groups = list(dict.fromkeys(output_group_id(v) for v in variables))
        weights = _positive_weights_for(variables, rng)
        # Drop one present group from the weights entirely.
        dropped = present_groups[-1]
        weights.pop(dropped, None)
        # Add phantom groups that never appear in the data.
        weights["tanf"] = 0.05
        weights["social_security"] = 0.03
        total = sum(weights.values())
        weights = {group: weight / total for group, weight in weights.items()}
        # Active set is every present group (including the unweighted one).
        active = set(present_groups)
        vectors.append(
            _vector(
                name=f"weights_groups_mismatch_{field}",
                description=(
                    "globalWeights omits one present group and includes phantom "
                    "groups absent from the data; the present unweighted group's "
                    "rows get weight 0 while the rest of the household stays "
                    "positively weighted."
                ),
                ground_truth=gt,
                predictions=pred,
                weights_by_group=weights,
                active_groups=active,
                reference_filter="all",
                field=field,
            )
        )

    # 7. Flagged zero-weight divergence vectors. A single output group with
    #    weight exactly 0 is the sole active program, so every household's kept
    #    active set has denominator 0. Python scores 0 for all models; the
    #    TypeScript scorer omits them.
    zero_weight_variable = "income_tax"
    for field in SCORE_FIELDS:
        variables = [zero_weight_variable] + list(_BINARY_VARIABLES[:2])
        gt, pred = _build_case(
            rng,
            n_scenarios=int(rng.integers(3, 6)),
            variables=variables,
            sparse_rows=False,
        )
        weights = _positive_weights_for(variables, rng)
        # Force the income_tax group's weight to exactly 0, renormalize the rest.
        weights[output_group_id(zero_weight_variable)] = 0.0
        remaining = sum(weights.values())
        if remaining > 0:
            weights = {group: weight / remaining for group, weight in weights.items()}
            weights[output_group_id(zero_weight_variable)] = 0.0
        vectors.append(
            _vector(
                name=f"zero_weight_single_program_{field}",
                description=(
                    "Active program is a single zero-population-weight output "
                    "group, so every household's renormalization denominator is "
                    "0. Pins the documented Python/TypeScript divergence."
                ),
                ground_truth=gt,
                predictions=pred,
                weights_by_group=weights,
                active_groups={output_group_id(zero_weight_variable)},
                reference_filter="all",
                field=field,
                ts_divergence=True,
            )
        )

    return {
        "version": FIXTURE_VERSION,
        "seed": seed,
        "tolerance": 1e-9,
        "description": (
            "Cross-language parity vectors for the canonical leaderboard scorer. "
            "Expected scores are computed by the Python canonical scorer "
            "(policybench.analysis) and replayed through the TypeScript scorer "
            "(app/src/lib/canonicalScore.ts) in app/tests/canonicalScore.test.ts."
        ),
        "vectors": vectors,
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        result = float(value)
        return result if math.isfinite(result) else None
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def serialize_vectors(payload: dict[str, Any]) -> str:
    """Serialize a fixture payload to compact, deterministic JSON.

    Compact (no indentation) keeps the committed fixture comfortably under the
    size budget; the file is generated, never hand-edited, so the canonical
    review surface is this module and the tests, not the raw floats. Keys are
    sorted so regeneration is byte-stable.
    """
    return json.dumps(
        payload,
        default=_json_default,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    )


def write_scorer_vectors(
    output_path: str = DEFAULT_FIXTURE_PATH,
    *,
    seed: int = DEFAULT_SEED,
) -> Path:
    """Generate the fixture and write it to ``output_path``.

    Returns the path written. Creates parent directories as needed.
    """
    payload = build_vectors(seed=seed)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_vectors(payload) + "\n", encoding="utf-8")
    return path
