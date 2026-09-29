"""Tests for counterfactual consistency (stability spec layer 3)."""

from unittest.mock import patch

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from policybench.counterfactual import (
    CF_ID_SUFFIX,
    ZERO_DELTA_BASELINE_MODEL,
    binomial_ci_exact,
    build_counterfactual_manifest,
    build_counterfactual_twin,
    compute_truth_deltas,
    delta_metrics_by_model,
    matched_delta_frame,
    noise_floor_frame,
    reportable_groups,
)
from policybench.scenarios import load_scenarios_from_manifest


class TestTwinBuilder:
    def test_twin_perturbs_head_and_rewrites_id(self, simple_single_scenario):
        twin = build_counterfactual_twin(simple_single_scenario)
        assert twin.id == f"{simple_single_scenario.id}{CF_ID_SUFFIX}"
        assert twin.adults[0].employment_income == pytest.approx(51_000.0)
        # Base is untouched.
        assert simple_single_scenario.adults[0].employment_income == pytest.approx(
            50_000.0
        )
        cf = twin.metadata["counterfactual"]
        assert cf["base_scenario_id"] == simple_single_scenario.id
        assert cf["perturbed_field"] == "employment_income"
        assert cf["perturbation_amount"] == 1000.0
        assert cf["first_dollar"] is False

    def test_first_dollar_flag_for_zero_wage_head(self, simple_single_scenario):
        simple_single_scenario.adults[0].employment_income = 0.0
        twin = build_counterfactual_twin(simple_single_scenario)
        assert twin.metadata["counterfactual"]["first_dollar"] is True

    def test_manifest_round_trips_through_loader(self, tmp_path, sample_scenarios):
        twins, manifest = build_counterfactual_manifest(sample_scenarios)
        assert list(manifest["base_scenario_id"]) == [s.id for s in sample_scenarios]
        assert set(manifest["perturbed_field"]) == {"employment_income"}
        assert set(manifest["perturbation_amount"]) == {1000.0}
        # total_income reflects the perturbation, not the base value.
        base_incomes = [s.total_income for s in sample_scenarios]
        assert list(manifest["total_income"]) == pytest.approx(
            [income + 1000.0 for income in base_incomes]
        )
        path = tmp_path / "cf_scenarios.csv"
        manifest.to_csv(path, index=False)
        loaded = load_scenarios_from_manifest(path)
        assert [s.id for s in loaded] == [t.id for t in twins]


class TestTruthDeltas:
    def test_merges_arms_and_rounds_to_cents(self, sample_scenarios):
        twins, _ = build_counterfactual_manifest(sample_scenarios)
        base_ids = [s.id for s in sample_scenarios]

        def fake_ground_truth(scenarios, programs=None, year=None):
            rows = []
            for scenario in scenarios:
                perturbed = scenario.id.endswith(CF_ID_SUFFIX)
                rows.append(
                    {
                        "scenario_id": scenario.id,
                        "variable": "snap",
                        "value": 100.0 + (10.001 if perturbed else 0.0),
                    }
                )
                rows.append(
                    {
                        "scenario_id": scenario.id,
                        "variable": "person_wic_eligible",
                        "value": 1.0,
                    }
                )
            return pd.DataFrame(rows)

        with patch(
            "policybench.counterfactual.calculate_ground_truth",
            side_effect=fake_ground_truth,
        ):
            deltas = compute_truth_deltas(sample_scenarios, twins, ["snap"], 2026)

        assert set(deltas["scenario_id"]) == set(base_ids)
        snap = deltas[deltas["variable"] == "snap"].iloc[0]
        assert snap["true_delta"] == pytest.approx(10.0)  # rounded to cents
        assert not snap["is_binary"]
        wic = deltas[deltas["variable"] == "person_wic_eligible"].iloc[0]
        assert wic["true_delta"] == pytest.approx(0.0)
        assert wic["is_binary"]
        assert "first_dollar" in deltas.columns


def _truth_deltas():
    rows = []
    # 12 scenarios x payroll_tax with a nonzero delta -> reportable group.
    for i in range(12):
        rows.append(
            {
                "scenario_id": f"s{i}",
                "variable": "payroll_tax",
                "base_value": 1000.0,
                "true_delta": 76.5,
                "is_binary": False,
                "output_group": "payroll_tax",
                "first_dollar": False,
            }
        )
    # snap: 2 nonzero (one negative), below the n>=10 group floor.
    rows.append(
        {
            "scenario_id": "s0",
            "variable": "snap",
            "base_value": 300.0,
            "true_delta": -237.6,
            "is_binary": False,
            "output_group": "snap",
            "first_dollar": False,
        }
    )
    rows.append(
        {
            "scenario_id": "s1",
            "variable": "snap",
            "base_value": 0.0,
            "true_delta": 0.0,
            "is_binary": False,
            "output_group": "snap",
            "first_dollar": False,
        }
    )
    # One large-response row (>= $200) beyond payroll's 76.5s.
    rows.append(
        {
            "scenario_id": "s2",
            "variable": "tanf",
            "base_value": 750.0,
            "true_delta": -750.0,
            "is_binary": False,
            "output_group": "tanf",
            "first_dollar": False,
        }
    )
    # Binary row with no reference flip.
    rows.append(
        {
            "scenario_id": "s0",
            "variable": "person_wic_eligible",
            "base_value": 1.0,
            "true_delta": 0.0,
            "is_binary": True,
            "output_group": "person_wic_eligible",
            "first_dollar": False,
        }
    )
    return pd.DataFrame(rows)


def _predictions(model="m", run_id=None, perturbed=False):
    truth = _truth_deltas()
    rows = []
    for row in truth.itertuples():
        base = 900.0 if row.variable == "payroll_tax" else float(row.base_value)
        if row.variable == "person_wic_eligible":
            prediction = 1.0
        elif perturbed:
            # The model moves exactly with truth on payroll, misses tanf/snap.
            prediction = base + (76.5 if row.variable == "payroll_tax" else 0.0)
        else:
            prediction = base
        entry = {
            "model": model,
            "scenario_id": row.scenario_id,
            "variable": row.variable,
            "prediction": prediction,
        }
        if run_id is not None:
            entry["run_id"] = run_id
        rows.append(entry)
    return pd.DataFrame(rows)


def _large_response_matched(detected_by_scenario, repeats=1, n_variables=1):
    """Use one perturbed arm and repeated bases on known qualifying rows."""
    truth_rows = []
    base_rows = []
    perturbed_rows = []
    for i, detected in enumerate(detected_by_scenario):
        for variable in ("snap", "tanf")[:n_variables]:
            scenario_id = f"s{i}"
            truth_rows.append(
                {
                    "scenario_id": scenario_id,
                    "variable": variable,
                    "true_delta": 250.0,
                    "is_binary": False,
                    "output_group": variable,
                    "first_dollar": False,
                }
            )
            for run in range(repeats):
                base_rows.append(
                    {
                        "model": "m",
                        "scenario_id": scenario_id,
                        "variable": variable,
                        "run_id": f"run_{run:03d}",
                        "prediction": 0.0,
                    }
                )
            perturbed_rows.append(
                {
                    "model": "m",
                    "scenario_id": f"{scenario_id}{CF_ID_SUFFIX}",
                    "variable": variable,
                    "prediction": 250.0 if detected else 0.0,
                }
            )
    return matched_delta_frame(
        pd.DataFrame(base_rows),
        pd.DataFrame(perturbed_rows),
        pd.DataFrame(truth_rows),
    )


class TestMatchedDeltaFrame:
    def test_matches_rows_and_computes_pred_delta(self):
        matched = matched_delta_frame(
            _predictions(), _predictions(perturbed=True), _truth_deltas()
        )
        payroll = matched[matched["variable"] == "payroll_tax"]
        assert payroll["pred_delta"].tolist() == pytest.approx([76.5] * len(payroll))
        assert payroll["both_parsed"].all()
        tanf = matched[matched["variable"] == "tanf"].iloc[0]
        assert tanf["pred_delta"] == pytest.approx(0.0)

    def test_multiple_base_runs_produce_one_match_per_run(self):
        base = pd.concat(
            [
                _predictions(run_id="run_000"),
                _predictions(run_id="run_001"),
            ],
            ignore_index=True,
        )
        matched = matched_delta_frame(
            base, _predictions(perturbed=True), _truth_deltas()
        )
        assert set(matched["base_run_id"]) == {"run_000", "run_001"}
        assert len(matched) == 2 * len(_truth_deltas())


class TestDeltaMetrics:
    def test_headline_metrics_and_baseline(self):
        matched = matched_delta_frame(
            _predictions(), _predictions(perturbed=True), _truth_deltas()
        )
        result = delta_metrics_by_model(matched)
        summary = result["summary"].set_index("model")
        row = summary.loc["m"]
        # Nonzero universe: 12 payroll + 1 snap + 1 tanf = 14 rows.
        assert row["n_nonzero_true"] == 14
        # Model nails payroll (12), misses snap and tanf -> 12/14.
        assert row["delta_exact_rate_nonzero"] == pytest.approx(12 / 14)
        # within band = max($1, 10%|true|): identical hits here.
        assert row["delta_within_10pct_rate_nonzero"] == pytest.approx(12 / 14)
        # Positive direction: 12 payroll all correct; negative: snap+tanf missed.
        assert row["sign_recall_positive"] == pytest.approx(1.0)
        assert row["sign_recall_negative"] == pytest.approx(0.0)
        baseline = summary.loc["__zero_delta_baseline__"]
        assert baseline["delta_exact_rate_nonzero"] == pytest.approx(0.0)
        # Pooled secondary includes the zero-delta snap row: 1 exact / 15 amount.
        assert baseline["delta_exact_rate_amount_pooled"] == pytest.approx(1 / 15)

    def test_small_delta_band_floor_makes_within_superset_of_exact(self):
        truth = pd.DataFrame(
            [
                {
                    "scenario_id": "s0",
                    "variable": "state_refundable_credits",
                    "base_value": 100.0,
                    "true_delta": 3.83,
                    "is_binary": False,
                    "output_group": "state_refundable_credits",
                    "first_dollar": False,
                }
            ]
        )
        base = pd.DataFrame(
            [
                {
                    "model": "m",
                    "scenario_id": "s0",
                    "variable": "state_refundable_credits",
                    "prediction": 100.0,
                }
            ]
        )
        pert = base.assign(prediction=104.0)  # pred_delta = 4.0, error $0.17
        matched = matched_delta_frame(base, pert, truth)
        summary = delta_metrics_by_model(matched)["summary"].set_index("model").loc["m"]
        assert summary["delta_exact_rate_nonzero"] == pytest.approx(1.0)
        # A bare 10% band would be $0.38 -- the $1 floor keeps this a superset.
        assert summary["delta_within_10pct_rate_nonzero"] == pytest.approx(1.0)

    def test_binary_counts_not_rates(self):
        matched = matched_delta_frame(
            _predictions(), _predictions(perturbed=True), _truth_deltas()
        )
        result = delta_metrics_by_model(matched)
        binary = result["binary_counts"].set_index("model").loc["m"]
        assert binary["n_reference_flips"] == 0
        assert binary["n_model_flips"] == 0
        assert "flip_recall" not in result["binary_counts"].columns

    def test_large_response_suppressed_below_min_rows(self):
        matched = matched_delta_frame(
            _predictions(), _predictions(perturbed=True), _truth_deltas()
        )
        result = delta_metrics_by_model(matched, large_response_min_rows=20)
        large = result["large_response"]
        # tanf -750 and snap -237.6 qualify at >= $200 -> suppressed but counted.
        assert large.iloc[0]["n_qualifying_rows"] == 2
        assert bool(large.iloc[0]["suppressed"]) is True
        rows = result["large_response_rows"]
        assert set(rows["variable"]) == {"tanf", "snap"}

    def test_repeated_comparisons_do_not_clear_unique_row_threshold(self):
        matched = _large_response_matched([True, False] * 5, repeats=3)
        result = delta_metrics_by_model(matched)
        large = result["large_response"].set_index("model").loc["m"]
        assert len(result["large_response_rows"]) == 10
        assert large["n_qualifying_rows"] == 10
        assert large["n_qualifying_scenarios"] == 10
        assert large["n_comparisons"] == 30
        assert large["n_detected"] == 15
        assert large["detection_rate"] == pytest.approx(0.5)
        assert bool(large["suppressed"]) is True

    def test_large_response_interval_clusters_variables_and_repeats(self):
        matched = _large_response_matched([True, False], repeats=3, n_variables=2)
        large = (
            delta_metrics_by_model(matched, n_boot=1000, seed=7)["large_response"]
            .set_index("model")
            .loc["m"]
        )
        # All observations within each household move together. Resampling the
        # two households therefore gives rates 0, 1/2, or 1, irrespective of K.
        assert large["n_qualifying_rows"] == 4
        assert large["n_qualifying_scenarios"] == 2
        assert large["n_comparisons"] == 12
        assert large["detection_rate_ci_low"] == pytest.approx(0.0)
        assert large["detection_rate_ci_high"] == pytest.approx(1.0)
        assert large["detection_rate_ci_method"] == "scenario_cluster_bootstrap"

    def test_large_response_interval_weights_unequal_household_sizes(self):
        matched = _large_response_matched([False, True], repeats=2, n_variables=2)
        # One failed comparison in s0; two successes and one failure in s1.
        # The repeated snap comparisons remain in the same household draw.
        matched = matched[
            ((matched["variable"] == "snap") & (matched["base_run_id"] == "run_000"))
            | (
                (matched["scenario_id"] == "s1")
                & (
                    (matched["variable"] == "snap")
                    | (matched["base_run_id"] == "run_000")
                )
            )
        ].copy()
        matched.loc[matched["variable"] == "tanf", "pred_delta"] = 0.0
        large = (
            delta_metrics_by_model(matched, n_boot=1000, seed=7)["large_response"]
            .set_index("model")
            .loc["m"]
        )
        assert large["n_qualifying_rows"] == 3
        assert large["n_qualifying_scenarios"] == 2
        assert large["n_comparisons"] == 4
        assert large["n_detected"] == 2
        # Pool the comparisons: 2/4, rather than the household mean (0+2/3)/2.
        assert large["detection_rate"] == pytest.approx(0.5)
        # The four equally likely household draws are (s0,s0), (s0,s1),
        # (s1,s0), (s1,s1), with rates 0, 1/2, 1/2, 2/3 respectively.
        assert large["detection_rate_ci_low"] == pytest.approx(0.0)
        assert large["detection_rate_ci_high"] == pytest.approx(2 / 3)
        # Seed 7's first four draws are (s1,s1) three times, then (s1,s0).
        # Their pooled rates are 2/3, 2/3, 2/3, 1/2; the interpolated 2.5th
        # percentile is 0.5 + 0.075 * (2/3 - 0.5) = 0.5125. Averaging
        # household rates within each draw would incorrectly give 0.35833.
        four_draws = (
            delta_metrics_by_model(matched, n_boot=4, seed=7)["large_response"]
            .set_index("model")
            .loc["m"]
        )
        assert four_draws["detection_rate_ci_low"] == pytest.approx(0.5125)
        assert four_draws["detection_rate_ci_high"] == pytest.approx(2 / 3)

    @pytest.mark.parametrize("detected", [False, True])
    def test_single_scenario_cannot_estimate_cluster_uncertainty(self, detected):
        matched = _large_response_matched([detected], repeats=3, n_variables=2)
        large = (
            delta_metrics_by_model(matched)["large_response"]
            .set_index("model")
            .loc["m"]
        )
        assert large["n_qualifying_rows"] == 2
        assert pd.isna(large["detection_rate_ci_low"])
        assert pd.isna(large["detection_rate_ci_high"])

    def test_unparsed_repeats_do_not_supply_qualifying_support(self):
        matched = _large_response_matched([True, False] * 10, repeats=3)
        missing = matched["scenario_id"] == "s0"
        matched.loc[missing, "both_parsed"] = False
        matched.loc[missing, "pred_delta"] = float("nan")
        large = (
            delta_metrics_by_model(matched)["large_response"]
            .set_index("model")
            .loc["m"]
        )
        assert large["n_qualifying_rows"] == 19
        assert large["n_comparisons"] == 57
        assert bool(large["suppressed"]) is True

    @settings(max_examples=30, deadline=None)
    @given(
        detected=st.lists(st.booleans(), min_size=2, max_size=25),
        repeats=st.integers(min_value=2, max_value=5),
        n_variables=st.integers(min_value=1, max_value=2),
    )
    def test_uniform_repetition_preserves_support_rate_and_uncertainty(
        self, detected, repeats, n_variables
    ):
        """Replicating observations must not create new independent evidence."""
        once = _large_response_matched(detected, n_variables=n_variables)
        repeated = _large_response_matched(
            detected, repeats=repeats, n_variables=n_variables
        ).iloc[::-1]
        first = (
            delta_metrics_by_model(once, n_boot=100, seed=13)["large_response"]
            .set_index("model")
            .loc["m"]
        )
        second = (
            delta_metrics_by_model(repeated, n_boot=100, seed=13)["large_response"]
            .set_index("model")
            .loc["m"]
        )
        n_rows = len(detected) * n_variables
        assert first["n_qualifying_rows"] == second["n_qualifying_rows"] == n_rows
        assert (
            first["n_qualifying_scenarios"]
            == second["n_qualifying_scenarios"]
            == len(detected)
        )
        assert bool(first["suppressed"]) == bool(second["suppressed"]) == (n_rows < 20)
        assert second["n_comparisons"] == first["n_comparisons"] * repeats
        assert second["n_detected"] == first["n_detected"] * repeats
        for field in (
            "detection_rate",
            "detection_rate_ci_low",
            "detection_rate_ci_high",
        ):
            assert second[field] == pytest.approx(first[field])
            assert 0.0 <= second[field] <= 1.0

    def test_reportable_groups_from_truth(self):
        groups = reportable_groups(_truth_deltas(), min_rows=10)
        assert groups == ["payroll_tax"]
        per_group = delta_metrics_by_model(
            matched_delta_frame(
                _predictions(), _predictions(perturbed=True), _truth_deltas()
            )
        )["per_group"]
        assert set(per_group["output_group"]) == {"payroll_tax"}


class TestNoiseFloor:
    def test_base_pairs_have_zero_true_delta(self):
        base = pd.concat(
            [_predictions(run_id="run_000"), _predictions(run_id="run_001")],
            ignore_index=True,
        )
        floor = noise_floor_frame(base, _truth_deltas())
        assert (floor["true_delta"] == 0).all()
        assert set(floor["variable"]) == set(_truth_deltas()["variable"])
        # Identical repeats -> zero null deltas.
        assert floor["pred_delta"].abs().max() == pytest.approx(0.0)


class TestSignalVsNoise:
    def test_real_signal_with_silent_noise_floor_is_distinguishable(self):
        from policybench.counterfactual import signal_vs_noise_test

        base = pd.concat(
            [_predictions(run_id="run_000"), _predictions(run_id="run_001")],
            ignore_index=True,
        )
        matched = matched_delta_frame(
            _predictions(run_id="run_000"),
            _predictions(perturbed=True),
            _truth_deltas(),
        )
        floor = noise_floor_frame(base, _truth_deltas())
        result = signal_vs_noise_test(matched, floor, n_boot=100, seed=5)
        row = result.set_index("model").loc["m"]
        # Model moves $76.50 on payroll; identical repeats -> zero noise.
        assert row["signal_median_abs_delta"] == pytest.approx(76.5)
        assert row["noise_floor_median_abs_delta"] == pytest.approx(0.0)
        assert bool(row["distinguishable_from_noise"]) is True
        assert ZERO_DELTA_BASELINE_MODEL not in set(result["model"])


class TestBinomialCI:
    def test_exact_ci_known_values(self):
        low, high = binomial_ci_exact(0, 20)
        assert low == pytest.approx(0.0)
        assert high == pytest.approx(0.1684, abs=2e-3)
        low, high = binomial_ci_exact(10, 20)
        assert low == pytest.approx(0.272, abs=2e-3)
        assert high == pytest.approx(0.728, abs=2e-3)

    def test_degenerate_n_zero(self):
        low, high = binomial_ci_exact(0, 0)
        assert pd.isna(low) and pd.isna(high)
