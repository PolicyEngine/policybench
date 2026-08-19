"""Tests for repeated-run answer-stability metrics (stability spec layer 1)."""

import json
import math

import pandas as pd
import pytest

from policybench.stability import (
    CacheContaminationError,
    assert_cache_free,
    chi2_ppf,
    cross_run_response_id_duplicates,
    is_parsed_prediction,
    load_runs_dirs,
    mutually_exact,
    row_stability_by_model,
    run_pair_frame,
    run_std_ci,
    scan_runs_for_cache_hits,
    stability_variance_decomposition,
)


class TestChiSquare:
    def test_known_quantiles_df2_closed_form(self):
        # df=2 has the closed form ppf(p) = -2 ln(1 - p).
        assert chi2_ppf(0.95, 2) == pytest.approx(5.99146, abs=1e-4)
        assert chi2_ppf(0.05, 2) == pytest.approx(0.10259, abs=1e-4)

    def test_known_quantiles_other_df(self):
        assert chi2_ppf(0.95, 4) == pytest.approx(9.48773, abs=1e-3)
        assert chi2_ppf(0.05, 4) == pytest.approx(0.71072, abs=1e-3)
        assert chi2_ppf(0.95, 1) == pytest.approx(3.84146, abs=1e-3)

    def test_run_std_ci_multipliers_match_spec(self):
        # Spec: K=3 -> std CI multipliers [0.578, 4.415] at 90% two-sided.
        low, high = run_std_ci(1.0, k=3, level=0.90)
        assert low == pytest.approx(0.578, abs=2e-3)
        assert high == pytest.approx(4.415, abs=2e-3)
        low5, high5 = run_std_ci(1.0, k=5, level=0.90)
        assert low5 == pytest.approx(0.649, abs=2e-3)
        assert high5 == pytest.approx(2.372, abs=2e-3)

    def test_run_std_ci_scales_with_std(self):
        low1, high1 = run_std_ci(1.0, k=3)
        low2, high2 = run_std_ci(2.0, k=3)
        assert low2 == pytest.approx(2 * low1)
        assert high2 == pytest.approx(2 * high1)

    def test_run_std_ci_nan_below_two_runs(self):
        low, high = run_std_ci(float("nan"), k=1)
        assert math.isnan(low) and math.isnan(high)


class TestParseAndMutualExact:
    def test_amount_parse(self):
        assert is_parsed_prediction("snap", 100.0)
        assert is_parsed_prediction("snap", 0.0)
        assert not is_parsed_prediction("snap", None)
        assert not is_parsed_prediction("snap", float("nan"))

    def test_binary_parse_requires_valid_flag(self):
        assert is_parsed_prediction("person_wic_eligible", 1.0)
        assert is_parsed_prediction("person_wic_eligible", 0)
        # Numeric but not 0/1: coverage-parse would say parsed; flag-parse says no.
        assert not is_parsed_prediction("person_wic_eligible", 0.5)
        assert not is_parsed_prediction("person_wic_eligible", None)

    def test_mutual_exact_amounts_dollar_tolerance(self):
        assert mutually_exact("snap", 100.0, 100.9)
        assert not mutually_exact("snap", 100.0, 101.5)
        assert not mutually_exact("snap", None, 100.0)

    def test_mutual_exact_binary_flags(self):
        assert mutually_exact("person_wic_eligible", 1.0, 1)
        assert not mutually_exact("person_wic_eligible", 1.0, 0.0)
        # Identical invalid flags are neither flips nor exact.
        assert not mutually_exact("person_wic_eligible", 0.5, 0.5)


def _ground_truth():
    return pd.DataFrame(
        {
            "scenario_id": ["s1", "s1", "s2", "s2"],
            "variable": ["snap", "person_wic_eligible", "snap", "person_wic_eligible"],
            "value": [100.0, 1.0, 0.0, 0.0],
        }
    )


def _repeated_predictions():
    """Two runs, one model, engineered per-row behaviors.

    s1/snap: 100 vs 250 -> parsed both, flip, verdict flips (exact vs wrong).
    s1/wic: 1 vs 1 -> stable and exact-correct both runs.
    s2/snap: 0 vs missing -> coverage flip; verdict flips under all-rows.
    s2/wic: 0.5 vs 0.5 -> invalid binary in both runs (never parsed).
    """
    rows = []
    for run_id, snap1, wic1, snap2, wic2 in [
        ("run_000", 100.0, 1.0, 0.0, 0.5),
        ("run_001", 250.0, 1.0, None, 0.5),
    ]:
        rows += [
            {"run_id": run_id, "model": "m", "scenario_id": "s1", "variable": "snap", "prediction": snap1},
            {"run_id": run_id, "model": "m", "scenario_id": "s1", "variable": "person_wic_eligible", "prediction": wic1},
            {"run_id": run_id, "model": "m", "scenario_id": "s2", "variable": "snap", "prediction": snap2},
            {"run_id": run_id, "model": "m", "scenario_id": "s2", "variable": "person_wic_eligible", "prediction": wic2},
        ]
    return pd.DataFrame(rows)


class TestRunPairFrame:
    def test_pair_flags(self):
        pairs = run_pair_frame(_repeated_predictions(), _ground_truth())
        assert set(pairs["run_a"]) == {"run_000"}
        assert set(pairs["run_b"]) == {"run_001"}
        by_row = pairs.set_index(["scenario_id", "variable"])

        snap1 = by_row.loc[("s1", "snap")]
        assert bool(snap1["both_parsed"]) and not bool(snap1["mutually_exact"])
        assert bool(snap1["exact_a"]) and not bool(snap1["exact_b"])

        wic1 = by_row.loc[("s1", "person_wic_eligible")]
        assert bool(wic1["mutually_exact"]) and bool(wic1["exact_a"]) and bool(wic1["exact_b"])

        snap2 = by_row.loc[("s2", "snap")]
        assert not bool(snap2["both_parsed"])
        assert bool(snap2["exact_a"]) and not bool(snap2["exact_b"])

        wic2 = by_row.loc[("s2", "person_wic_eligible")]
        assert not bool(wic2["both_parsed"])

    def test_three_runs_make_three_pairs_per_row(self):
        preds = _repeated_predictions()
        third = preds[preds["run_id"] == "run_000"].assign(run_id="run_002")
        pairs = run_pair_frame(pd.concat([preds, third]), _ground_truth())
        assert len(pairs) == 4 * 3  # C(3,2) pairs x 4 rows


class TestRowStability:
    def test_metrics_on_engineered_runs(self):
        table = row_stability_by_model(
            _repeated_predictions(), _ground_truth(), n_boot=50, seed=1
        )
        row = table.set_index("model").loc["m"]
        assert row["k"] == 2
        assert row["n_rows"] == 4
        assert row["n_scenarios"] == 2
        # Parsed in all runs: s1/snap and s1/wic -> 2/4.
        assert row["unanimous_parse_rate"] == pytest.approx(0.5)
        # s2/snap parsed once, missing once.
        assert row["coverage_flip_rate"] == pytest.approx(0.25)
        # s2/wic invalid in at least one run, over 2 binary rows.
        assert row["invalid_binary_rate"] == pytest.approx(0.5)
        # Both-parsed pairs: s1/snap (flip), s1/wic (stable) -> 1/2.
        assert row["answer_flip_rate"] == pytest.approx(0.5)
        assert row["unanimous_exact_answer_rate"] == pytest.approx(0.25)
        # Verdict flips among both-parsed pairs: s1/snap only -> 1/2.
        assert row["verdict_flip_rate_parsed"] == pytest.approx(0.5)
        # All pairs: s1/snap flip + s2/snap (exact vs missing) -> 2/4.
        assert row["verdict_flip_rate_all"] == pytest.approx(0.5)

    def test_consistently_wrong_divergent_amount_rows_only(self):
        gt = pd.DataFrame(
            {
                "scenario_id": ["s1", "s1"],
                "variable": ["snap", "person_wic_eligible"],
                "value": [500.0, 1.0],
            }
        )
        preds = pd.DataFrame(
            {
                "run_id": ["run_000"] * 2 + ["run_001"] * 2,
                "model": ["m"] * 4,
                "scenario_id": ["s1"] * 4,
                "variable": ["snap", "person_wic_eligible"] * 2,
                # snap: wrong both runs with different wrong answers.
                # wic: wrong both runs (same wrong flag, the only one possible).
                "prediction": [100.0, 0.0, 200.0, 0.0],
            }
        )
        table = row_stability_by_model(preds, gt, n_boot=10, seed=1)
        out = table.set_index("model").loc["m"]
        # Binary row excluded by construction; 1/1 amount rows divergent.
        assert out["consistently_wrong_divergent_rate"] == pytest.approx(1.0)
        assert out["n_consistently_wrong_amount_rows"] == 1

    def test_bootstrap_ci_columns_present_and_ordered(self):
        table = row_stability_by_model(
            _repeated_predictions(), _ground_truth(), n_boot=50, seed=7
        )
        row = table.iloc[0]
        for metric in ["answer_flip_rate", "verdict_flip_rate_parsed"]:
            assert row[f"{metric}_ci_low"] <= row[metric] <= row[f"{metric}_ci_high"]

    def test_bootstrap_deterministic_under_seed(self):
        a = row_stability_by_model(_repeated_predictions(), _ground_truth(), n_boot=30, seed=3)
        b = row_stability_by_model(_repeated_predictions(), _ground_truth(), n_boot=30, seed=3)
        pd.testing.assert_frame_equal(a, b)

    def test_empty_inputs(self):
        assert row_stability_by_model(pd.DataFrame(), _ground_truth()).empty
        assert row_stability_by_model(_repeated_predictions(), pd.DataFrame()).empty


class TestVarianceDecomposition:
    def _inputs(self):
        gt = pd.DataFrame(
            {
                "scenario_id": ["s1", "s2", "s3", "s4"],
                "variable": ["snap"] * 4,
                "value": [100.0, 200.0, 300.0, 400.0],
            }
        )
        rows = []
        # Model with run-to-run movement: run_000 all exact, run_001 half exact,
        # run_002 all exact.
        for run_id, preds in [
            ("run_000", [100.0, 200.0, 300.0, 400.0]),
            ("run_001", [100.0, 200.0, 999.0, 999.0]),
            ("run_002", [100.0, 200.0, 300.0, 400.0]),
        ]:
            for sid, p in zip(["s1", "s2", "s3", "s4"], preds, strict=True):
                rows.append(
                    {"run_id": run_id, "model": "m", "scenario_id": sid, "variable": "snap", "prediction": p}
                )
        return gt, pd.DataFrame(rows), {"s1": 0.0, "s2": 0.0, "s3": 0.0, "s4": 0.0}

    def test_per_model_columns_and_decision_rule(self):
        gt, preds, market = self._inputs()
        per_model, pooled = stability_variance_decomposition(gt, preds, market)
        row = per_model.set_index("model").loc["m"]
        assert row["k"] == 3
        # Run scores: 1.0, 0.5, 1.0 -> std = 0.288675.
        assert row["run_score_mean"] == pytest.approx(5 / 6, abs=1e-6)
        assert row["run_score_std"] == pytest.approx(0.288675, abs=1e-5)
        assert row["run_score_std_ci_low"] < row["run_score_std"] < row["run_score_std_ci_high"]
        assert row["sampling_se"] > 0
        assert row["run_to_sampling_ratio"] == pytest.approx(
            row["run_score_std"] / row["sampling_se"]
        )
        # Decision rule uses the CI upper bound, not the point ratio.
        expected = bool(row["run_score_std_ci_high"] < row["sampling_se"])
        assert bool(row["sampling_dominates"]) == expected
        # K=3 detectable floor from the spec.
        assert row["detectable_ratio_floor"] == pytest.approx(1 / 4.415, abs=1e-3)

    def test_pooled_roster_estimate(self):
        gt, preds, market = self._inputs()
        second = preds.assign(model="m2")
        both = pd.concat([preds, second], ignore_index=True)
        per_model, pooled = stability_variance_decomposition(gt, both, market)
        assert len(per_model) == 2
        assert pooled["n_models"] == 2
        assert pooled["pooled_df"] == 2 * 2
        assert pooled["pooled_run_score_std"] == pytest.approx(0.288675, abs=1e-5)
        homogeneity = pooled["homogeneity"]
        assert set(homogeneity) == {"m", "m2"}
        assert sum(homogeneity.values()) == pytest.approx(1.0)

    def test_requires_run_id(self):
        gt, preds, market = self._inputs()
        per_model, pooled = stability_variance_decomposition(
            gt, preds.drop(columns=["run_id"]), market
        )
        assert per_model.empty


class TestCacheGuard:
    def _write_ledger(self, tmp_path, records):
        runs = tmp_path / "runs"
        runs.mkdir()
        (runs / "run_000.csv").write_text("model,scenario_id\n")
        ledger = runs / "run_000.csv.spend.jsonl"
        ledger.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        return runs

    def test_clean_ledger_passes(self, tmp_path):
        runs = self._write_ledger(tmp_path, [{"cache_hit": False}, {"cache_hit": False}])
        report = scan_runs_for_cache_hits([runs])
        assert report["cache_hits"] == 0
        assert report["records"] == 2
        assert_cache_free([runs])

    def test_cache_hit_raises(self, tmp_path):
        runs = self._write_ledger(tmp_path, [{"cache_hit": False}, {"cache_hit": True}])
        assert scan_runs_for_cache_hits([runs])["cache_hits"] == 1
        with pytest.raises(CacheContaminationError):
            assert_cache_free([runs])

    def test_missing_ledgers_reported(self, tmp_path):
        runs = tmp_path / "runs"
        runs.mkdir()
        (runs / "run_000.csv").write_text("model\n")
        report = scan_runs_for_cache_hits([runs])
        assert report["ledgers"] == 0
        # No ledger is not proof of no cache: surfaced, not silently passed.
        assert report["runs_without_ledger"] == 1

    def test_cross_run_response_id_duplicates(self):
        preds = pd.DataFrame(
            {
                "run_id": ["run_000", "run_001", "run_000", "run_001"],
                "model": ["m"] * 4,
                "scenario_id": ["s1", "s1", "s2", "s2"],
                "variable": ["snap"] * 4,
                "prediction": [1.0] * 4,
                "provider_response_id": ["r1", "r1", "r2", "r3"],
            }
        )
        assert cross_run_response_id_duplicates(preds) == 1
        assert cross_run_response_id_duplicates(preds.drop(columns=["provider_response_id"])) is None


class TestLoadRunsDirs:
    def _write_runs(self, path, model, run_ids):
        path.mkdir(parents=True)
        for run_id in run_ids:
            pd.DataFrame(
                {
                    "run_id": [run_id],
                    "model": [model],
                    "scenario_id": ["s1"],
                    "variable": ["snap"],
                    "prediction": [1.0],
                }
            ).to_csv(path / f"{run_id}.csv", index=False)

    def test_loads_and_concats_disjoint_models(self, tmp_path):
        self._write_runs(tmp_path / "a", "m1", ["run_000", "run_001"])
        self._write_runs(tmp_path / "b", "m2", ["run_000", "run_001"])
        frame = load_runs_dirs([tmp_path / "a", tmp_path / "b"])
        assert set(frame["model"]) == {"m1", "m2"}
        assert len(frame) == 4

    def test_rejects_overlapping_models(self, tmp_path):
        self._write_runs(tmp_path / "a", "m1", ["run_000"])
        self._write_runs(tmp_path / "b", "m1", ["run_000"])
        with pytest.raises(ValueError, match="model"):
            load_runs_dirs([tmp_path / "a", tmp_path / "b"])

    def test_rejects_mismatched_run_id_sets(self, tmp_path):
        self._write_runs(tmp_path / "a", "m1", ["run_000", "run_001"])
        self._write_runs(tmp_path / "b", "m2", ["run_000"])
        with pytest.raises(ValueError, match="run_id"):
            load_runs_dirs([tmp_path / "a", tmp_path / "b"])
