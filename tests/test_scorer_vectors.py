"""Tests for the cross-language scorer parity vector generator.

These guard the fixture consumed by ``app/tests/canonicalScore.test.ts``:
deterministic output, a stable schema, expected scores that match the published
Python canonical scorer on the unfiltered case, correct filter semantics, and
zero-weight slices that produce missing scores rather than zero scores. All fast
and pure — no network, no provider calls.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from policybench.analysis import (
    bounded_household_scores,
    household_headline_scores,
)
from policybench.scorer_vectors import (
    DEFAULT_FIXTURE_PATH,
    FIXTURE_VERSION,
    SCORE_FIELDS,
    build_vectors,
    canonical_filtered_scores,
    serialize_vectors,
    write_scorer_vectors,
)
from policybench.spec import output_group_id

_REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def fixture_payload() -> dict:
    return build_vectors()


def test_build_vectors_is_deterministic():
    first = serialize_vectors(build_vectors())
    second = serialize_vectors(build_vectors())
    assert first == second


def test_build_vectors_seed_changes_output():
    default = serialize_vectors(build_vectors())
    other = serialize_vectors(build_vectors(seed=999))
    assert default != other


def test_fixture_top_level_schema(fixture_payload):
    assert fixture_payload["version"] == FIXTURE_VERSION
    assert fixture_payload["tolerance"] == 1e-9
    assert isinstance(fixture_payload["seed"], int)
    assert isinstance(fixture_payload["description"], str)
    assert fixture_payload["description"]
    assert len(fixture_payload["vectors"]) >= 24


def test_every_required_vector_category_present(fixture_payload):
    names = {vector["name"] for vector in fixture_payload["vectors"]}
    required_prefixes = [
        "unfiltered_full",
        "single_program",
        "positives_only",
        "zeros_only",
        "all_zero_reference",
        "models_missing_rows",
        "weights_groups_mismatch",
        "zero_weight_single_program",
    ]
    for prefix in required_prefixes:
        matching = [name for name in names if name.startswith(prefix)]
        assert len(matching) == len(SCORE_FIELDS), (
            f"expected one vector per field for {prefix!r}, found {matching}"
        )


def test_vector_schema_is_complete(fixture_payload):
    required_keys = {
        "name",
        "description",
        "country",
        "weightsView",
        "programFilter",
        "referenceFilter",
        "field",
        "scenarioPredictions",
        "globalWeights",
        "expectedScores",
    }
    for vector in fixture_payload["vectors"]:
        assert required_keys <= set(vector), vector["name"]
        assert vector["country"] == "us"
        assert vector["field"] in SCORE_FIELDS
        assert vector["referenceFilter"] in {"all", "positives", "zeros"}
        assert vector["weightsView"] in {"household", "aggregate", "equal"}
        assert set(vector["globalWeights"]) == {"household", "aggregate", "equal"}
        # scenarioPredictions is dense: every variable cell holds the same set of
        # models, and each record has prediction + groundTruth keys.
        for variable_map in vector["scenarioPredictions"].values():
            for model_map in variable_map.values():
                for record in model_map.values():
                    assert "prediction" in record
                    assert "groundTruth" in record


def test_expected_scores_rounded_to_ten_decimals(fixture_payload):
    for vector in fixture_payload["vectors"]:
        for score in vector["expectedScores"].values():
            assert score == round(score, 10)
        for view_weights in vector["globalWeights"].values():
            for weight in view_weights.values():
                assert weight == round(weight, 10)


def test_serialized_fixture_is_within_size_budget(fixture_payload):
    serialized = serialize_vectors(fixture_payload)
    assert len(serialized.encode("utf-8")) < 200 * 1024


def test_committed_fixture_matches_generator():
    """The committed fixture must equal a fresh generation (no manual drift)."""
    committed = (_REPO_ROOT / DEFAULT_FIXTURE_PATH).read_text(encoding="utf-8")
    regenerated = serialize_vectors(build_vectors()) + "\n"
    assert committed == regenerated, (
        "Committed scorer_vectors.json is stale; "
        "run `policybench export-scorer-vectors`."
    )


def test_write_scorer_vectors_round_trip(tmp_path):
    output = write_scorer_vectors(str(tmp_path / "vectors.json"))
    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["version"] == FIXTURE_VERSION
    assert len(payload["vectors"]) >= 24


def _frames_from_vector(vector: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reconstruct ground-truth and prediction frames from a fixture vector."""
    gt_rows = []
    pred_rows = []
    for scenario_id, variable_map in vector["scenarioPredictions"].items():
        for variable, model_map in variable_map.items():
            records = list(model_map.values())
            gt_rows.append(
                {
                    "scenario_id": scenario_id,
                    "variable": variable,
                    "value": records[0]["groundTruth"],
                }
            )
            for model, record in model_map.items():
                pred_rows.append(
                    {
                        "model": model,
                        "scenario_id": scenario_id,
                        "variable": variable,
                        "prediction": record["prediction"],
                    }
                )
    return pd.DataFrame(gt_rows), pd.DataFrame(pred_rows)


def test_canonical_filtered_recomputes_expected_scores(fixture_payload):
    """Replaying the canonical scorer on the payload reproduces expectedScores."""
    for vector in fixture_payload["vectors"]:
        gt, pred = _frames_from_vector(vector)
        weights = vector["globalWeights"][vector["weightsView"]]
        scores, _ = canonical_filtered_scores(
            gt,
            pred,
            weights,
            set(vector["programFilter"]),
            vector["referenceFilter"],
            vector["field"],
        )
        expected = vector["expectedScores"]
        assert set(scores) == set(expected), vector["name"]
        for model, value in expected.items():
            assert scores[model] == pytest.approx(value, abs=1e-9), vector["name"]


def test_canonical_equals_published_with_shared_weights():
    """With identical weights, canonical_filtered_scores == published headline.

    Pins the core equivalence directly on a hand-built case: the low-level
    filter-then-score path the fixture uses reproduces ``household_headline_scores``
    and ``bounded_household_scores`` byte-for-byte on the unfiltered, all-groups
    case when both are fed the same population weights.
    """
    gt = pd.DataFrame(
        [
            {"scenario_id": "s0", "variable": "snap", "value": 1200.0},
            {"scenario_id": "s0", "variable": "eitc", "value": 3000.0},
            {"scenario_id": "s0", "variable": "head_medicaid_eligible", "value": 1.0},
            {"scenario_id": "s1", "variable": "snap", "value": 0.0},
            {"scenario_id": "s1", "variable": "eitc", "value": 500.0},
            {"scenario_id": "s1", "variable": "head_medicaid_eligible", "value": 0.0},
        ]
    )
    pred = pd.DataFrame(
        [
            {
                "model": "m1",
                "scenario_id": "s0",
                "variable": "snap",
                "prediction": 1200.0,
            },
            {
                "model": "m1",
                "scenario_id": "s0",
                "variable": "eitc",
                "prediction": 2900.0,
            },
            {
                "model": "m1",
                "scenario_id": "s0",
                "variable": "head_medicaid_eligible",
                "prediction": 1.0,
            },
            {"model": "m1", "scenario_id": "s1", "variable": "snap", "prediction": 0.0},
            {
                "model": "m1",
                "scenario_id": "s1",
                "variable": "eitc",
                "prediction": 500.0,
            },
            {
                "model": "m1",
                "scenario_id": "s1",
                "variable": "head_medicaid_eligible",
                "prediction": 0.0,
            },
            {"model": "m2", "scenario_id": "s0", "variable": "snap", "prediction": 0.0},
            {
                "model": "m2",
                "scenario_id": "s0",
                "variable": "eitc",
                "prediction": 3000.0,
            },
            {
                "model": "m2",
                "scenario_id": "s0",
                "variable": "head_medicaid_eligible",
                "prediction": 0.0,
            },
            {
                "model": "m2",
                "scenario_id": "s1",
                "variable": "snap",
                "prediction": 100.0,
            },
            {
                "model": "m2",
                "scenario_id": "s1",
                "variable": "eitc",
                "prediction": None,
            },
            {
                "model": "m2",
                "scenario_id": "s1",
                "variable": "head_medicaid_eligible",
                "prediction": 1.0,
            },
        ]
    )
    # Derive the benchmark weights the published scorer would use, and feed the
    # SAME weights to the canonical filter path.
    from policybench.analysis import bounded_global_variable_weights

    weights = bounded_global_variable_weights(gt, {}, country=None)
    weights_by_group = {str(k): float(v) for k, v in weights.items()}
    active = set(weights_by_group)

    for field, metric in [("within1pct", "within_1pct"), ("exact", "exact")]:
        published = (
            household_headline_scores(gt, pred, {}, country=None, metric=metric)
            .groupby("model")["score"]
            .mean()
            .mul(100.0)
            .to_dict()
        )
        canonical, _ = canonical_filtered_scores(
            gt, pred, weights_by_group, active, "all", field
        )
        assert canonical == pytest.approx(published, abs=1e-9)

    published_continuous = (
        bounded_household_scores(gt, pred, {}, country=None)
        .groupby("model")["score"]
        .mean()
        .mul(100.0)
        .to_dict()
    )
    canonical_continuous, _ = canonical_filtered_scores(
        gt, pred, weights_by_group, active, "all", "continuous"
    )
    assert canonical_continuous == pytest.approx(published_continuous, abs=1e-9)


def test_reference_filter_subsets_rows_before_scoring():
    """The reference filter subsets rows first, then the canonical scorer runs."""
    gt = pd.DataFrame(
        [
            {"scenario_id": "s0", "variable": "snap", "value": 1000.0},
            {"scenario_id": "s0", "variable": "eitc", "value": 0.0},
        ]
    )
    pred = pd.DataFrame(
        [
            {
                "model": "m1",
                "scenario_id": "s0",
                "variable": "snap",
                "prediction": 1000.0,
            },
            {
                "model": "m1",
                "scenario_id": "s0",
                "variable": "eitc",
                "prediction": 5000.0,
            },
        ]
    )
    weights = {"snap": 0.5, "eitc": 0.5}
    active = {"snap", "eitc"}

    # Positives-only keeps just snap (value 1000): m1 is exactly right -> 100.
    positives, _ = canonical_filtered_scores(
        gt, pred, weights, active, "positives", "within1pct"
    )
    assert positives == pytest.approx({"m1": 100.0})

    # Zeros-only keeps just eitc (value 0): m1 predicted 5000 -> wrong -> 0.
    zeros, _ = canonical_filtered_scores(
        gt, pred, weights, active, "zeros", "within1pct"
    )
    assert zeros == pytest.approx({"m1": 0.0})


def test_zero_weight_vectors_are_plain_empty_score_vectors(fixture_payload):
    """Zero-weight vectors are ordinary parity vectors with no scoreable models."""
    zero_weight = [
        vector
        for vector in fixture_payload["vectors"]
        if vector["name"].startswith("zero_weight_single_program")
    ]
    assert len(zero_weight) == len(SCORE_FIELDS)
    for vector in zero_weight:
        assert vector["expectedScores"] == {}
        assert "tsDivergence" not in vector
        assert "typescriptScores" not in vector
        assert "zeroWeightScenarios" not in vector
        assert "divergenceReason" not in vector


def test_active_group_is_actually_zero_weight_for_empty_score_vectors(
    fixture_payload,
):
    """The zero-weight vectors really have a zero-weight active group."""
    for vector in fixture_payload["vectors"]:
        if not vector["name"].startswith("zero_weight_single_program"):
            continue
        weights = vector["globalWeights"][vector["weightsView"]]
        active_weight = sum(
            weights.get(output_group_id(group), 0.0)
            for group in vector["programFilter"]
        )
        assert active_weight == 0.0, vector["name"]
