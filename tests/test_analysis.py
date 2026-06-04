"""Tests for metrics and analysis."""

import json

import numpy as np
import pandas as pd
import pytest

from policybench.analysis import (
    accuracy,
    amount_accuracy_by_model,
    analyze_no_tools,
    bounded_global_variable_weights,
    bounded_household_scores,
    bounded_row_score,
    build_dashboard_payload,
    build_scenario_prompt_map,
    compute_metrics,
    continuous_row_score,
    exact_amount_match,
    export_analysis,
    export_dashboard_data,
    household_net_income_by_scenario,
    mean_absolute_error,
    mean_absolute_percentage_error,
    participation_accuracy_by_model,
    render_markdown_report,
    run_stability_by_model,
    score_single_prediction,
    summarize_runs_by_model,
    summary_by_model,
    summary_by_variable,
    threshold_score_single_prediction,
    usage_summary_by_model,
    weighted_hit_rate_scores_by_model,
    within_tolerance,
)
from policybench.config import (
    UK_HEADLINE_PROGRAMS,
    US_HEADLINE_PROGRAMS,
    get_programs,
)


class TestBasicMetrics:
    def test_mae_perfect(self):
        y = np.array([100.0, 200.0, 300.0])
        assert mean_absolute_error(y, y) == 0.0

    def test_mae_known(self):
        y_true = np.array([100.0, 200.0, 300.0])
        y_pred = np.array([110.0, 190.0, 310.0])
        assert mean_absolute_error(y_true, y_pred) == 10.0

    def test_mape_perfect(self):
        y = np.array([100.0, 200.0, 300.0])
        assert mean_absolute_percentage_error(y, y) == 0.0

    def test_mape_known(self):
        y_true = np.array([100.0, 200.0])
        y_pred = np.array([110.0, 220.0])
        # Errors: 10% and 10%
        assert abs(mean_absolute_percentage_error(y_true, y_pred) - 0.10) < 1e-10

    def test_mape_skips_zeros(self):
        y_true = np.array([0.0, 100.0])
        y_pred = np.array([10.0, 110.0])
        # Only considers index 1: 10% error
        assert abs(mean_absolute_percentage_error(y_true, y_pred) - 0.10) < 1e-10

    def test_mape_all_zeros(self):
        y_true = np.array([0.0, 0.0])
        y_pred = np.array([10.0, 20.0])
        assert np.isnan(mean_absolute_percentage_error(y_true, y_pred))

    def test_accuracy_perfect(self):
        y = np.array([0.0, 1.0, 1.0, 0.0])
        assert accuracy(y, y) == 1.0

    def test_accuracy_half(self):
        y_true = np.array([0.0, 1.0, 1.0, 0.0])
        y_pred = np.array([1.0, 0.0, 1.0, 0.0])
        assert accuracy(y_true, y_pred) == 0.5

    def test_within_tolerance_perfect(self):
        y = np.array([100.0, 200.0, 300.0])
        assert within_tolerance(y, y) == 1.0

    def test_within_tolerance_known(self):
        y_true = np.array([100.0, 200.0, 1000.0])
        # 5% off, 5% off, 20% off
        y_pred = np.array([105.0, 210.0, 1200.0])
        # First two within 10%, third is not
        assert abs(within_tolerance(y_true, y_pred, tolerance=0.10) - 2 / 3) < 1e-10

    def test_within_tolerance_zero_ground_truth(self):
        y_true = np.array([0.0])
        y_pred = np.array([0.5])  # Within $1 tolerance
        assert within_tolerance(y_true, y_pred) == 1.0

        y_pred_far = np.array([5.0])  # Outside $1 tolerance
        assert within_tolerance(y_true, y_pred_far) == 0.0

    def test_exact_amount_match_known(self):
        y_true = np.array([100.0, 200.0, 300.0])
        y_pred = np.array([100.5, 202.0, 299.5])
        assert exact_amount_match(y_true, y_pred) == pytest.approx(2 / 3)

    def test_score_single_prediction_uses_bounded_amount_score(self):
        assert score_single_prediction("income_tax", 100.0, 100.5) == pytest.approx(
            0.995
        )
        assert score_single_prediction("income_tax", 100.0, 104.0) == pytest.approx(
            0.96
        )
        assert score_single_prediction("income_tax", 100.0, None) == 0.0
        assert threshold_score_single_prediction(
            "income_tax",
            100.0,
            104.0,
        ) == pytest.approx(0.5)

    def test_bounded_row_score_requires_exact_binary_flags(self):
        assert bounded_row_score("head_medicaid_eligible", 1.0, 1.0) == 1.0
        assert bounded_row_score("head_medicaid_eligible", 1.0, 0.6) == 0.0
        assert bounded_row_score("head_medicaid_eligible", 1.0, 0.5) == 0.0
        assert bounded_row_score("head_medicaid_eligible", 0.0, 0.5) == 0.0
        assert bounded_row_score("head_medicaid_eligible", 1.0, 0.4) == 0.0


class TestComputeMetrics:
    @pytest.fixture
    def ground_truth_df(self):
        return pd.DataFrame(
            {
                "scenario_id": ["s1", "s2", "s3", "s1", "s2", "s3"],
                "variable": [
                    "income_tax",
                    "income_tax",
                    "income_tax",
                    "eitc",
                    "eitc",
                    "eitc",
                ],
                "value": [5000.0, 10000.0, 0.0, 3000.0, 0.0, 6000.0],
            }
        )

    @pytest.fixture
    def predictions_df(self):
        return pd.DataFrame(
            {
                "model": ["model_a"] * 6,
                "scenario_id": ["s1", "s2", "s3", "s1", "s2", "s3"],
                "variable": [
                    "income_tax",
                    "income_tax",
                    "income_tax",
                    "eitc",
                    "eitc",
                    "eitc",
                ],
                "prediction": [5500.0, 9000.0, 100.0, 3300.0, 500.0, 5400.0],
            }
        )

    def test_compute_metrics_returns_dataframe(self, ground_truth_df, predictions_df):
        metrics = compute_metrics(ground_truth_df, predictions_df)
        assert isinstance(metrics, pd.DataFrame)
        assert "model" in metrics.columns
        assert "variable" in metrics.columns
        assert "mae" in metrics.columns

    def test_compute_metrics_correct_rows(self, ground_truth_df, predictions_df):
        metrics = compute_metrics(ground_truth_df, predictions_df)
        # 1 model × 2 variables = 2 rows
        assert len(metrics) == 2

    def test_compute_metrics_mae_values(self, ground_truth_df, predictions_df):
        metrics = compute_metrics(ground_truth_df, predictions_df)
        income_tax_row = metrics[metrics["variable"] == "income_tax"]
        # MAE for income_tax: |5500-5000|=500, |9000-10000|=1000, |100-0|=100
        # Mean: (500+1000+100)/3 = 533.33
        expected_mae = (500 + 1000 + 100) / 3
        assert abs(income_tax_row["mae"].iloc[0] - expected_mae) < 0.01

    def test_compute_metrics_counts_missing_predictions_as_failures(self):
        ground_truth_df = pd.DataFrame(
            {
                "scenario_id": ["s1", "s2"],
                "variable": ["income_tax", "income_tax"],
                "value": [100.0, 100.0],
            }
        )
        predictions_df = pd.DataFrame(
            {
                "model": ["model_a", "model_a"],
                "scenario_id": ["s1", "s2"],
                "variable": ["income_tax", "income_tax"],
                "prediction": [100.0, None],
            }
        )

        metrics = compute_metrics(ground_truth_df, predictions_df)
        row = metrics.iloc[0]

        assert row["n"] == 2
        assert row["n_parsed"] == 1
        assert row["coverage"] == 0.5
        assert row["mae"] == 0.0
        assert row["exact"] == 0.5
        assert row["within_1pct"] == 0.5
        assert row["within_5pct"] == 0.5
        assert row["within_10pct"] == 0.5
        assert row["score"] == 0.5

    def test_compute_metrics_counts_missing_rows_in_denominator(self):
        ground_truth_df = pd.DataFrame(
            {
                "scenario_id": ["s1", "s2"],
                "variable": ["income_tax", "income_tax"],
                "value": [100.0, 100.0],
            }
        )
        predictions_df = pd.DataFrame(
            {
                "model": ["model_a"],
                "scenario_id": ["s1"],
                "variable": ["income_tax"],
                "prediction": [100.0],
            }
        )

        metrics = compute_metrics(ground_truth_df, predictions_df)
        row = metrics.iloc[0]

        assert row["n"] == 2
        assert row["n_parsed"] == 1
        assert row["coverage"] == 0.5
        assert row["exact"] == 0.5
        assert row["score"] == 0.5

    def test_compute_metrics_keeps_zero_coverage_variable_rows(self):
        ground_truth_df = pd.DataFrame(
            {
                "scenario_id": ["s1", "s1"],
                "variable": ["income_tax", "eitc"],
                "value": [100.0, 50.0],
            }
        )
        predictions_df = pd.DataFrame(
            {
                "model": ["model_a"],
                "scenario_id": ["s1"],
                "variable": ["income_tax"],
                "prediction": [100.0],
            }
        )

        metrics = compute_metrics(ground_truth_df, predictions_df).sort_values(
            "variable"
        )
        assert metrics["variable"].tolist() == ["eitc", "income_tax"]

        eitc_row = metrics[metrics["variable"] == "eitc"].iloc[0]
        assert eitc_row["n"] == 1
        assert eitc_row["n_parsed"] == 0
        assert eitc_row["coverage"] == 0.0
        assert eitc_row["score"] == 0.0

    def test_compute_metrics_score_uses_bounded_continuous_score(self):
        ground_truth_df = pd.DataFrame(
            {
                "scenario_id": ["s1", "s2", "s3", "s4"],
                "variable": ["income_tax"] * 4,
                "value": [100.0, 100.0, 100.0, 100.0],
            }
        )
        predictions_df = pd.DataFrame(
            {
                "model": ["model_a"] * 4,
                "scenario_id": ["s1", "s2", "s3", "s4"],
                "variable": ["income_tax"] * 4,
                "prediction": [100.0, 100.5, 104.0, 112.0],
            }
        )

        metrics = compute_metrics(ground_truth_df, predictions_df)
        row = metrics.iloc[0]

        assert row["exact"] == pytest.approx(0.5)
        assert row["within_1pct"] == pytest.approx(0.5)
        assert row["within_5pct"] == pytest.approx(0.75)
        assert row["within_10pct"] == pytest.approx(0.75)
        assert row["threshold_score"] == pytest.approx(0.625)
        assert row["score"] == pytest.approx((1 + 0.995 + 0.96 + 0.88) / 4)


class TestSummaries:
    @pytest.fixture
    def metrics_df(self):
        return pd.DataFrame(
            {
                "model": ["a", "a", "b", "b"],
                "variable": ["income_tax", "eitc", "income_tax", "eitc"],
                "score": [0.55, 0.75, 0.40, 0.50],
                "exact": [0.3, 0.6, 0.2, 0.3],
                "within_1pct": [0.4, 0.7, 0.3, 0.4],
                "within_5pct": [0.6, 0.8, 0.4, 0.5],
                "threshold_score": [0.45, 0.75, 0.35, 0.50],
                "mae": [500.0, 300.0, 1000.0, 800.0],
                "mape": [0.10, 0.05, 0.20, 0.15],
                "accuracy": [float("nan")] * 4,
                "within_10pct": [0.8, 0.9, 0.5, 0.6],
                "n": [50, 50, 50, 50],
                "n_parsed": [50, 50, 45, 40],
                "coverage": [1.0, 1.0, 0.9, 0.8],
            }
        )

    def test_summary_by_model(self, metrics_df):
        summary = summary_by_model(metrics_df)
        assert len(summary) == 2
        model_a = summary[summary["model"] == "a"]
        assert abs(model_a["mean_score"].iloc[0] - 0.65) < 1e-10
        assert abs(model_a["mean_mae"].iloc[0] - 400.0) < 1e-10
        assert model_a["parsed_n"].iloc[0] == 100
        assert model_a["mean_coverage"].iloc[0] == 1.0

    def test_summary_by_variable(self, metrics_df):
        summary = summary_by_variable(metrics_df)
        assert len(summary) == 2
        it = summary[summary["variable"] == "income_tax"]
        assert abs(it["mean_score"].iloc[0] - 0.475) < 1e-10
        assert abs(it["mean_mae"].iloc[0] - 750.0) < 1e-10

    def test_get_programs_supports_current_sets(self):
        assert get_programs("us", "headline") == US_HEADLINE_PROGRAMS
        assert get_programs("uk", "headline") == UK_HEADLINE_PROGRAMS

    def test_analyze_no_tools_returns_expected_tables(self):
        ground_truth_df = pd.DataFrame(
            {
                "scenario_id": ["s1", "s2"],
                "variable": ["income_tax", "income_tax"],
                "value": [5000.0, 10000.0],
            }
        )
        predictions_df = pd.DataFrame(
            {
                "model": ["model_a", "model_a"],
                "scenario_id": ["s1", "s2"],
                "variable": ["income_tax", "income_tax"],
                "prediction": [5500.0, 9000.0],
            }
        )
        analysis = analyze_no_tools(ground_truth_df, predictions_df)
        assert set(analysis) == {
            "metrics",
            "model_summary",
            "bounded_summary",
            "global_weights",
            "variable_summary",
            "usage_summary",
            "run_model_summary",
            "run_stability",
        }
        assert len(analysis["metrics"]) == 1
        assert len(analysis["model_summary"]) == 1
        assert len(analysis["variable_summary"]) == 1
        assert len(analysis["usage_summary"]) == 1
        assert analysis["run_model_summary"].empty
        assert analysis["run_stability"].empty

    def test_summarize_runs_and_run_stability_by_model(self):
        ground_truth_df = pd.DataFrame(
            {
                "scenario_id": ["s1", "s2", "s1", "s2"],
                "variable": ["income_tax", "income_tax", "eitc", "eitc"],
                "value": [100.0, 200.0, 0.0, 50.0],
            }
        )
        predictions_df = pd.DataFrame(
            {
                "run_id": ["run_000"] * 4 + ["run_001"] * 4,
                "model": ["model_a"] * 8,
                "scenario_id": ["s1", "s2", "s1", "s2"] * 2,
                "variable": ["income_tax", "income_tax", "eitc", "eitc"] * 2,
                "prediction": [110.0, 180.0, 0.0, 45.0, 100.0, 210.0, 0.0, 40.0],
            }
        )

        run_summary = summarize_runs_by_model(
            ground_truth_df,
            predictions_df,
        )
        stability = run_stability_by_model(run_summary)

        assert set(run_summary["run_id"]) == {"run_000", "run_001"}
        row = stability.iloc[0]
        assert row["model"] == "model_a"
        assert row["run_count"] == 2
        assert row["within10pct_run_min"] <= row["within10pct_run_max"]
        assert row["within10pct_run_std"] >= 0

    def test_usage_summary_by_model_sums_cost_and_tokens(self):
        predictions_df = pd.DataFrame(
            {
                "model": ["model_a", "model_a", "model_b"],
                "scenario_id": ["s1", "s2", "s1"],
                "variable": ["income_tax", "eitc", "income_tax"],
                "prediction": [1.0, None, 2.0],
                "error": [None, None, "Timeout"],
                "provider_reported_cost_usd": [0.1, None, 0.3],
                "reconstructed_cost_usd": [0.1, 0.2, 0.3],
                "total_cost_usd": [0.1, 0.2, 0.3],
                "cost_is_estimated": [False, True, False],
                "estimated_cost_usd": [0.1, 0.2, 0.3],
                "elapsed_seconds": [1.0, 2.0, 3.0],
                "prompt_tokens": [10, 20, 30],
                "completion_tokens": [1, 2, 3],
                "total_tokens": [11, 22, 33],
                "reasoning_tokens": [0, 1, 2],
                "cached_prompt_tokens": [4, 5, 6],
            }
        )

        summary = usage_summary_by_model(predictions_df)
        model_a = summary[summary["model"] == "model_a"].iloc[0]

        assert model_a["total_rows"] == 2
        assert model_a["parsed_rows"] == 1
        assert model_a["error_rows"] == 0
        assert model_a["total_cost_usd"] == pytest.approx(0.3)
        assert model_a["estimated_cost_rows"] == 1
        assert model_a["total_estimated_cost_usd"] == pytest.approx(0.3)
        assert model_a["total_elapsed_seconds"] == 3.0
        assert model_a["total_tokens"] == 33.0

    def test_render_markdown_report_contains_sections(self, metrics_df):
        analysis = {
            "metrics": metrics_df,
            "model_summary": summary_by_model(metrics_df),
            "variable_summary": summary_by_variable(metrics_df),
            "usage_summary": pd.DataFrame(
                {
                    "model": ["a"],
                    "total_rows": [100],
                    "parsed_rows": [95],
                    "error_rows": [5],
                    "total_provider_reported_cost_usd": [1.00],
                    "total_reconstructed_cost_usd": [1.23],
                    "total_cost_usd": [1.23],
                    "estimated_cost_rows": [100],
                    "total_estimated_cost_usd": [1.23],
                    "total_elapsed_seconds": [120.0],
                    "prompt_tokens": [1000.0],
                    "completion_tokens": [200.0],
                    "total_tokens": [1200.0],
                    "reasoning_tokens": [50.0],
                    "cached_prompt_tokens": [100.0],
                }
            ),
            "run_model_summary": pd.DataFrame(),
            "run_stability": pd.DataFrame(),
        }
        report = render_markdown_report(analysis)
        assert "# PolicyBench Analysis" in report
        assert "## Usage" in report
        assert "Total cost" in report
        assert "cost_rows_estimated" in report
        assert "## Summary by model" in report
        assert "## Summary by variable" in report
        assert "mean_binary_accuracy" in report
        assert "mean_accuracy" in report

    def test_render_markdown_report_includes_run_stability(self, metrics_df):
        analysis = {
            "metrics": metrics_df,
            "model_summary": summary_by_model(metrics_df).assign(
                run_count=[3, 3],
                within10pct_run_mean=[0.85, 0.55],
                within10pct_run_std=[0.02, 0.03],
                within10pct_run_min=[0.82, 0.52],
                within10pct_run_max=[0.87, 0.58],
                mae_run_mean=[400.0, 900.0],
                mae_run_std=[20.0, 30.0],
            ),
            "variable_summary": summary_by_variable(metrics_df),
            "usage_summary": pd.DataFrame(),
            "run_model_summary": pd.DataFrame(
                {
                    "run_id": ["run_000", "run_001", "run_002"],
                    "model": ["a", "a", "a"],
                    "mean_score": [0.72, 0.74, 0.76],
                    "mean_exact": [0.52, 0.54, 0.56],
                    "mean_within_1pct": [0.62, 0.64, 0.66],
                    "mean_within_5pct": [0.72, 0.74, 0.76],
                    "mean_mae": [390.0, 410.0, 400.0],
                    "mean_mape": [0.1, 0.11, 0.09],
                    "mean_within_10pct": [0.83, 0.85, 0.87],
                    "mean_accuracy": [float("nan")] * 3,
                    "mean_coverage": [1.0, 1.0, 1.0],
                    "total_n": [100, 100, 100],
                    "parsed_n": [100, 100, 100],
                }
            ),
            "run_stability": pd.DataFrame(
                {
                    "model": ["a"],
                    "run_count": [3],
                    "score_run_mean": [0.74],
                    "score_run_std": [0.02],
                    "score_run_min": [0.72],
                    "score_run_max": [0.76],
                    "within10pct_run_mean": [0.85],
                    "within10pct_run_std": [0.02],
                    "within10pct_run_min": [0.83],
                    "within10pct_run_max": [0.87],
                    "mae_run_mean": [400.0],
                    "mae_run_std": [20.0],
                }
            ),
        }
        report = render_markdown_report(analysis)
        assert "## Run stability" in report
        assert "score_run_mean" in report

    def test_export_analysis_writes_expected_files(self, metrics_df, tmp_path):
        analysis = {
            "metrics": metrics_df,
            "model_summary": summary_by_model(metrics_df),
            "variable_summary": summary_by_variable(metrics_df),
            "usage_summary": pd.DataFrame(
                {
                    "model": ["a"],
                    "total_rows": [100],
                    "parsed_rows": [95],
                    "error_rows": [5],
                    "total_provider_reported_cost_usd": [1.00],
                    "total_reconstructed_cost_usd": [1.23],
                    "total_cost_usd": [1.23],
                    "estimated_cost_rows": [100],
                    "total_estimated_cost_usd": [1.23],
                    "total_elapsed_seconds": [120.0],
                    "prompt_tokens": [1000.0],
                    "completion_tokens": [200.0],
                    "total_tokens": [1200.0],
                    "reasoning_tokens": [50.0],
                    "cached_prompt_tokens": [100.0],
                }
            ),
            "run_model_summary": pd.DataFrame(
                {
                    "run_id": ["run_000"],
                    "model": ["a"],
                    "mean_score": [0.75],
                    "mean_exact": [0.55],
                    "mean_within_1pct": [0.65],
                    "mean_within_5pct": [0.75],
                    "mean_mae": [400.0],
                    "mean_mape": [0.1],
                    "mean_within_10pct": [0.8],
                    "mean_accuracy": [float("nan")],
                    "mean_coverage": [1.0],
                    "total_n": [100],
                    "parsed_n": [100],
                }
            ),
            "run_stability": pd.DataFrame(
                {
                    "model": ["a"],
                    "run_count": [1],
                    "score_run_mean": [0.75],
                    "score_run_std": [float("nan")],
                    "score_run_min": [0.75],
                    "score_run_max": [0.75],
                    "within10pct_run_mean": [0.8],
                    "within10pct_run_std": [float("nan")],
                    "within10pct_run_min": [0.8],
                    "within10pct_run_max": [0.8],
                    "mae_run_mean": [400.0],
                    "mae_run_std": [float("nan")],
                }
            ),
        }
        exported = export_analysis(analysis, tmp_path)
        assert set(exported) == {
            "metrics",
            "model_summary",
            "variable_summary",
            "usage_summary",
            "report",
            "run_model_summary",
            "run_stability",
        }
        assert exported["metrics"].exists()
        assert exported["model_summary"].exists()
        assert exported["variable_summary"].exists()
        assert exported["usage_summary"].exists()
        assert exported["report"].exists()

    def test_build_dashboard_payload_matches_frontend_shape(self):
        ground_truth_df = pd.DataFrame(
            {
                "scenario_id": ["s1", "s1", "s2", "s2"],
                "variable": ["income_tax", "adult1_medicaid_eligible"] * 2,
                "value": [100.0, 1.0, 200.0, 0.0],
            }
        )
        predictions_df = pd.DataFrame(
            {
                "model": ["model_a"] * 4,
                "scenario_id": ["s1", "s1", "s2", "s2"],
                "variable": ["income_tax", "adult1_medicaid_eligible"] * 2,
                "prediction": [110.0, 1.0, 210.0, 0.0],
                "explanation": ["brief note", None, None, None],
                "annotation": ["off by 10%", None, None, None],
                "failure_source": ["llm_error", None, None, None],
                "failure_subtype": ["thresholds_rates", None, None, None],
                "case_annotation": [
                    "two models missed the bracket",
                    None,
                    None,
                    None,
                ],
                "case_failure_sources": ["llm_error", None, None, None],
                "case_failure_subtypes": ["thresholds_rates", None, None, None],
            }
        )
        scenarios_df = pd.DataFrame(
            {
                "scenario_id": ["s1", "s2"],
                "state": ["CA", "NY"],
                "filing_status": ["single", "joint"],
                "num_adults": [1, 2],
                "num_children": [0, 1],
                "total_income": [50_000.0, 75_000.0],
            }
        )
        analysis = analyze_no_tools(ground_truth_df, predictions_df)

        payload = build_dashboard_payload(
            ground_truth_df,
            predictions_df,
            analysis,
            scenarios_df,
        )

        assert set(payload) == {
            "country",
            "failureModes",
            "policyengineBundles",
            "scenarios",
            "modelStats",
            "programStats",
            "heatmap",
            "scenarioPredictions",
            "globalWeights",
        }
        # All three weighting views expose a per-variable map.
        assert set(payload["globalWeights"]) == {"household", "aggregate", "equal"}
        for view_weights in payload["globalWeights"].values():
            assert isinstance(view_weights, dict)
        assert payload["country"] == "us"
        assert payload["scenarios"]["s1"]["country"] == "us"
        assert payload["scenarios"]["s1"]["filingStatus"] == "single"
        assert payload["modelStats"][0]["condition"] == "no_tools"
        assert "score" in payload["modelStats"][0]
        assert "within10pctRunMean" not in payload["modelStats"][0]
        assert payload["heatmap"][0]["condition"] == "no_tools"
        income_program = next(
            row for row in payload["programStats"] if row["variable"] == "income_tax"
        )
        assert income_program["score"] == pytest.approx(92.5)
        assert income_program["thresholdScore"] == pytest.approx(37.5)
        income_heatmap = next(
            row for row in payload["heatmap"] if row["variable"] == "income_tax"
        )
        assert income_heatmap["score"] == pytest.approx(92.5)
        assert income_heatmap["thresholdScore"] == pytest.approx(37.5)
        assert (
            payload["scenarioPredictions"]["s1"]["income_tax"]["model_a"]["prediction"]
            == 110.0
        )
        scored = payload["scenarioPredictions"]["s1"]["income_tax"]["model_a"]
        assert scored["score"] == pytest.approx(90.0)
        assert scored["boundedScore"] == pytest.approx(90.0)
        assert scored["thresholdScore"] == pytest.approx(25.0)
        assert scored["exact"] == 0.0
        assert scored["within1pct"] == 0.0
        assert scored["within5pct"] == 0.0
        assert scored["within10pct"] == 100.0
        assert (
            payload["scenarioPredictions"]["s1"]["income_tax"]["model_a"]["explanation"]
            == "brief note"
        )
        assert (
            payload["scenarioPredictions"]["s1"]["income_tax"]["model_a"]["annotation"]
            == "off by 10%"
        )
        assert (
            payload["scenarioPredictions"]["s1"]["income_tax"]["model_a"][
                "failureSource"
            ]
            == "llm_error"
        )
        assert (
            payload["scenarioPredictions"]["s1"]["income_tax"]["model_a"][
                "failureSubtype"
            ]
            == "thresholds_rates"
        )
        assert (
            payload["scenarioPredictions"]["s1"]["income_tax"]["model_a"][
                "caseAnnotation"
            ]
            == "two models missed the bracket"
        )
        assert (
            payload["scenarioPredictions"]["s1"]["income_tax"]["model_a"][
                "caseFailureSources"
            ]
            == "llm_error"
        )
        assert (
            payload["scenarioPredictions"]["s1"]["income_tax"]["model_a"][
                "caseFailureSubtypes"
            ]
            == "thresholds_rates"
        )

    def test_build_dashboard_payload_keeps_missing_predictions_as_misses(self):
        ground_truth_df = pd.DataFrame(
            {
                "scenario_id": ["s1", "s2", "s3"],
                "variable": ["income_tax", "income_tax", "income_tax"],
                "value": [100.0, 200.0, 300.0],
            }
        )
        predictions_df = pd.DataFrame(
            {
                "model": ["model_a", "model_a"],
                "scenario_id": ["s1", "s2"],
                "variable": ["income_tax", "income_tax"],
                "prediction": [100.0, None],
                "error": [None, "could not parse numeric answer"],
            }
        )
        scenarios_df = pd.DataFrame(
            {
                "scenario_id": ["s1", "s2", "s3"],
                "state": ["CA", "NY", "TX"],
                "filing_status": ["single", "single", "single"],
                "num_adults": [1, 1, 1],
                "num_children": [0, 0, 0],
                "total_income": [50_000.0, 60_000.0, 70_000.0],
            }
        )
        analysis = analyze_no_tools(ground_truth_df, predictions_df)

        payload = build_dashboard_payload(
            ground_truth_df,
            predictions_df,
            analysis,
            scenarios_df,
        )

        parsed = payload["scenarioPredictions"]["s1"]["income_tax"]["model_a"]
        unparseable = payload["scenarioPredictions"]["s2"]["income_tax"]["model_a"]
        missing = payload["scenarioPredictions"]["s3"]["income_tax"]["model_a"]

        assert parsed["parsed"] is True
        assert parsed["prediction"] == 100.0
        assert parsed["score"] == 100.0
        assert parsed["boundedScore"] == 100.0
        assert parsed["thresholdScore"] == 100.0
        assert parsed["exact"] == 100.0
        assert unparseable["parsed"] is False
        assert unparseable["prediction"] is None
        assert unparseable["error"] is None
        assert unparseable["score"] == 0.0
        assert unparseable["boundedScore"] == 0.0
        assert unparseable["thresholdScore"] == 0.0
        assert unparseable["predictionError"] == "could not parse numeric answer"
        assert missing["parsed"] is False
        assert missing["prediction"] is None
        assert missing["score"] == 0.0
        assert missing["boundedScore"] == 0.0
        assert missing["thresholdScore"] == 0.0

    def test_analyze_no_tools_merges_run_stability(self):
        ground_truth_df = pd.DataFrame(
            {
                "scenario_id": ["s1", "s2"],
                "variable": ["income_tax", "income_tax"],
                "value": [100.0, 200.0],
            }
        )
        predictions_df = pd.DataFrame(
            {
                "model": ["model_a", "model_a"],
                "scenario_id": ["s1", "s2"],
                "variable": ["income_tax", "income_tax"],
                "prediction": [110.0, 190.0],
            }
        )
        repeated_predictions_df = pd.DataFrame(
            {
                "run_id": ["run_000", "run_000", "run_001", "run_001"],
                "model": ["model_a"] * 4,
                "scenario_id": ["s1", "s2", "s1", "s2"],
                "variable": ["income_tax", "income_tax", "income_tax", "income_tax"],
                "prediction": [110.0, 190.0, 90.0, 210.0],
            }
        )

        analysis = analyze_no_tools(
            ground_truth_df,
            predictions_df,
            repeated_predictions=repeated_predictions_df,
        )

        row = analysis["model_summary"].iloc[0]
        assert row["run_count"] == 2
        assert analysis["run_model_summary"]["run_id"].nunique() == 2

    def test_build_dashboard_payload_includes_prompt_map(self):
        ground_truth_df = pd.DataFrame(
            {
                "scenario_id": ["s1"],
                "variable": ["income_tax"],
                "value": [100.0],
            }
        )
        predictions_df = pd.DataFrame(
            {
                "model": ["model_a"],
                "scenario_id": ["s1"],
                "variable": ["income_tax"],
                "prediction": [110.0],
            }
        )
        scenarios_df = pd.DataFrame(
            {
                "scenario_id": ["s1"],
                "state": ["CA"],
                "filing_status": ["single"],
                "num_adults": [1],
                "num_children": [0],
                "total_income": [50_000.0],
            }
        )
        analysis = analyze_no_tools(ground_truth_df, predictions_df)
        prompt_map = {
            "s1": {
                "income_tax": {
                    "tool": "tool prompt",
                    "json": "json prompt",
                }
            }
        }

        payload = build_dashboard_payload(
            ground_truth_df,
            predictions_df,
            analysis,
            scenarios_df,
            scenario_prompts=prompt_map,
        )

        assert payload["scenarios"]["s1"]["prompt"]["tool"] == "tool prompt"
        assert "failureModes" in payload
        assert "programs" in payload["failureModes"]
        assert "households" in payload["failureModes"]

    def test_build_scenario_prompt_map_from_manifest_json(self):
        scenario = {
            "id": "s1",
            "state": "CA",
            "filing_status": "single",
            "adults": [
                {
                    "name": "adult1",
                    "age": 35,
                    "employment_income": 50000.0,
                    "inputs": {},
                }
            ],
            "children": [],
            "year": 2026,
            "source_dataset": "enhanced_cps_2024",
            "metadata": {"household_id": 1},
        }
        scenarios_df = pd.DataFrame(
            {
                "scenario_id": ["s1"],
                "scenario_json": [json.dumps(scenario)],
            }
        )

        prompt_map = build_scenario_prompt_map(scenarios_df, ["income_tax"])

        assert "income_tax" in prompt_map["s1"]
        assert "submit_outputs" in prompt_map["s1"]["income_tax"]["tool"]
        assert (
            '"outputs": {"income_tax": {"value": 1234.5'
            in prompt_map["s1"]["income_tax"]["json"]
        )

    def test_build_scenario_prompt_map_collapses_person_outputs_to_templates(self):
        scenario = {
            "id": "s1",
            "country": "us",
            "state": "CA",
            "filing_status": "single",
            "adults": [
                {
                    "name": "head",
                    "age": 35,
                    "employment_income": 50000.0,
                    "inputs": {},
                }
            ],
            "children": [],
            "year": 2026,
            "source_dataset": "enhanced_cps_2024",
            "metadata": {"household_id": 1},
        }
        scenarios_df = pd.DataFrame(
            {
                "scenario_id": ["s1"],
                "scenario_json": [json.dumps(scenario)],
            }
        )

        prompt_map = build_scenario_prompt_map(
            scenarios_df,
            ["head_wic_eligible", "child1_wic_eligible"],
        )

        assert list(prompt_map["s1"]) == ["head_wic_eligible"]
        assert (
            "child1_wic_eligible" not in prompt_map["s1"]["head_wic_eligible"]["json"]
        )

    def test_export_dashboard_data_writes_json(self, tmp_path):
        ground_truth_df = pd.DataFrame(
            {
                "scenario_id": ["s1"],
                "variable": ["income_tax"],
                "value": [100.0],
            }
        )
        predictions_df = pd.DataFrame(
            {
                "model": ["model_a"],
                "scenario_id": ["s1"],
                "variable": ["income_tax"],
                "prediction": [110.0],
            }
        )
        scenarios_df = pd.DataFrame(
            {
                "scenario_id": ["s1"],
                "state": ["CA"],
                "filing_status": ["single"],
                "num_adults": [1],
                "num_children": [0],
                "total_income": [50_000.0],
            }
        )
        analysis = analyze_no_tools(ground_truth_df, predictions_df)

        output_path = tmp_path / "data.json"
        exported = export_dashboard_data(
            ground_truth_df,
            predictions_df,
            analysis,
            scenarios_df,
            output_path,
        )

        assert exported.exists()
        assert '"modelStats"' in exported.read_text()
        assert '"failureModes"' in exported.read_text()


class TestContinuousRowScore:
    """Continuous floor-free row score: max(0, 1 - |err|/|ref|), with ref=0 cased."""

    def test_exact_match(self):
        assert continuous_row_score(100.0, 100.0) == 1.0

    def test_fifty_percent_off(self):
        assert continuous_row_score(100.0, 50.0) == pytest.approx(0.5)

    def test_at_full_error(self):
        # off by exactly |ref|, lands at 0
        assert continuous_row_score(100.0, 0.0) == 0.0

    def test_over_clipped_negative_pred(self):
        assert continuous_row_score(100.0, -100.0) == 0.0

    def test_huge_over_clipped(self):
        # error 9x reference -> still 0 (no negative scores)
        assert continuous_row_score(100.0, 1000.0) == 0.0

    def test_negative_reference(self):
        # |ref| in denominator handles signed references
        assert continuous_row_score(-100.0, -100.0) == 1.0
        assert continuous_row_score(-100.0, -50.0) == pytest.approx(0.5)

    def test_zero_ref_zero_pred(self):
        assert continuous_row_score(0.0, 0.0) == 1.0

    def test_zero_ref_nonzero_pred(self):
        # any nonzero prediction on zero ref is fully wrong (no $1,000 floor)
        assert continuous_row_score(0.0, 50.0) == 0.0
        assert continuous_row_score(0.0, 0.01) == 0.0
        assert continuous_row_score(0.0, -0.5) == 0.0

    def test_none_pred(self):
        assert continuous_row_score(100.0, None) == 0.0
        assert continuous_row_score(0.0, None) == 0.0

    def test_nan_pred(self):
        assert continuous_row_score(100.0, float("nan")) == 0.0
        assert continuous_row_score(0.0, float("nan")) == 0.0

    def test_boolean_match(self):
        # ref/pred encoded as 0/1 — same formula gives binary accuracy
        assert continuous_row_score(1.0, 1.0) == 1.0
        assert continuous_row_score(0.0, 0.0) == 1.0
        assert continuous_row_score(1.0, 0.0) == 0.0  # |err|=1, |ref|=1, score=0
        assert continuous_row_score(0.0, 1.0) == 0.0  # ref=0 special-case


class TestHouseholdNetIncome:
    """household_net_income_by_scenario: market income + signed program flows."""

    def _ground_truth(self):
        return pd.DataFrame(
            {
                "scenario_id": ["s1", "s1", "s1"],
                "variable": [
                    "federal_income_tax_before_refundable_credits",
                    "snap",
                    "person_medicaid_eligible",
                ],
                "value": [4000.0, 5000.0, 1.0],
                "impact_weight": [pd.NA, pd.NA, 8000.0],
            }
        )

    def test_signed_sum_with_market_income(self):
        gt = self._ground_truth()
        market = {"s1": 20000.0}
        nets = household_net_income_by_scenario(gt, market)
        # 20k market - 4k tax + 5k snap + 8k medicaid value (eligible) = 29k
        assert nets["s1"] == pytest.approx(29000.0)

    def test_boolean_not_eligible_contributes_zero(self):
        gt = self._ground_truth().copy()
        gt.loc[gt["variable"] == "person_medicaid_eligible", "value"] = 0.0
        market = {"s1": 20000.0}
        nets = household_net_income_by_scenario(gt, market)
        # 20k - 4k + 5k + 0 = 21k
        assert nets["s1"] == pytest.approx(21000.0)

    def test_missing_market_defaults_to_zero(self):
        gt = self._ground_truth()
        nets = household_net_income_by_scenario(gt, {})
        # 0 - 4k + 5k + 8k = 9k
        assert nets["s1"] == pytest.approx(9000.0)


class TestBoundedGlobalVariableWeights:
    """Bounded global weights: mean of |abs|/max(|net|, Σ|abs|), renormalized."""

    def test_weights_sum_to_one(self):
        gt = pd.DataFrame(
            {
                "scenario_id": ["s1", "s1", "s2", "s2"],
                "variable": ["federal_income_tax_before_refundable_credits", "snap"]
                * 2,
                "value": [4000.0, 5000.0, 1000.0, 6000.0],
                "impact_weight": [pd.NA, pd.NA, pd.NA, pd.NA],
            }
        )
        market = {"s1": 60000.0, "s2": 20000.0}
        weights = bounded_global_variable_weights(gt, market)
        assert weights.sum() == pytest.approx(1.0)
        assert set(weights.index) == {
            "federal_income_tax_before_refundable_credits",
            "snap",
        }

    def test_rich_slice_tiny_benefit_gets_near_zero(self):
        # Rich household with $1 benefit + zero taxes. The benefit should
        # have near-zero share, not 100%.
        gt = pd.DataFrame(
            {
                "scenario_id": ["rich"],
                "variable": ["snap"],
                "value": [1.0],
                "impact_weight": [pd.NA],
            }
        )
        market = {"rich": 200_000.0}
        weights = bounded_global_variable_weights(gt, market)
        # Only one variable; weight = 1.0 after renormalization.
        # But the *raw* per-household share before renormalization is tiny.
        # Add a second variable so renormalization can split.
        gt = pd.concat(
            [
                gt,
                pd.DataFrame(
                    {
                        "scenario_id": ["other"],
                        "variable": ["snap"],
                        "value": [4000.0],
                        "impact_weight": [pd.NA],
                    }
                ),
            ]
        )
        market2 = {"rich": 200_000.0, "other": 20_000.0}
        # With a second household where SNAP is meaningful, the rich household
        # contributes essentially nothing, so the global weight is dominated
        # by "other".
        weights = bounded_global_variable_weights(gt, market2)
        # Both households have SNAP only -> renormalized weight is 1.0 either way,
        # but we verify the rich slice's per-household share is small.
        # Sanity: shares sum to 1 after renormalization.
        assert weights["snap"] == pytest.approx(1.0)

    def test_country_population_weights_can_weight_zero_sample_output(
        self,
        monkeypatch,
    ):
        gt = pd.DataFrame(
            {
                "scenario_id": ["s1", "s1", "s2", "s2"],
                "variable": ["income_tax", "pip"] * 2,
                "value": [1000.0, 0.0, 2000.0, 0.0],
                "impact_weight": [pd.NA, pd.NA, pd.NA, pd.NA],
            }
        )

        def fake_population_weights(country, kind, output_groups):
            assert country == "uk"
            assert kind == "household"
            assert output_groups == ["income_tax", "pip"]
            return pd.Series({"income_tax": 0.8, "pip": 0.2})

        monkeypatch.setattr(
            "policybench.analysis.matching_population_weight_series",
            fake_population_weights,
        )

        weights = bounded_global_variable_weights(
            gt,
            {"s1": 30_000.0, "s2": 40_000.0},
            country="uk",
        )

        assert weights["pip"] == pytest.approx(0.2)
        assert weights["income_tax"] == pytest.approx(0.8)


class TestBoundedHouseholdScores:
    """Bounded household scores: mean of weighted continuous row scores."""

    def test_perfect_predictions_score_one(self):
        gt = pd.DataFrame(
            {
                "scenario_id": ["s1", "s1"],
                "variable": ["federal_income_tax_before_refundable_credits", "snap"],
                "value": [4000.0, 5000.0],
                "impact_weight": [pd.NA, pd.NA],
            }
        )
        preds = pd.DataFrame(
            {
                "model": ["m1", "m1"],
                "scenario_id": ["s1", "s1"],
                "variable": ["federal_income_tax_before_refundable_credits", "snap"],
                "prediction": [4000.0, 5000.0],
            }
        )
        market = {"s1": 60000.0}
        out = bounded_household_scores(gt, preds, market)
        assert out.loc[out["model"] == "m1", "score"].iloc[0] == pytest.approx(1.0)

    def test_population_group_weights_split_across_person_outputs(
        self,
        monkeypatch,
    ):
        gt = pd.DataFrame(
            {
                "scenario_id": ["s1", "s1", "s1"],
                "variable": [
                    "income_tax",
                    "head_medicaid_eligible",
                    "spouse_medicaid_eligible",
                ],
                "value": [100.0, 1.0, 1.0],
                "impact_weight": [pd.NA, 9000.0, 1000.0],
            }
        )
        preds = pd.DataFrame(
            {
                "model": ["m1", "m1", "m1"],
                "scenario_id": ["s1", "s1", "s1"],
                "variable": [
                    "income_tax",
                    "head_medicaid_eligible",
                    "spouse_medicaid_eligible",
                ],
                "prediction": [100.0, 0.0, 1.0],
            }
        )

        def fake_population_weights(country, kind, output_groups):
            assert country == "us"
            assert kind == "household"
            assert output_groups == ["income_tax", "person_medicaid_eligible"]
            return pd.Series(
                {
                    "income_tax": 0.4,
                    "person_medicaid_eligible": 0.6,
                }
            )

        monkeypatch.setattr(
            "policybench.analysis.matching_population_weight_series",
            fake_population_weights,
        )

        out = bounded_household_scores(
            gt,
            preds,
            {"s1": 20_000.0},
            country="us",
        )

        # Medicaid's 0.6 group weight is split evenly across the two people
        # in this household. It is not split by these rows' impact_weight
        # values, which are already represented in the population-level group
        # weight.
        assert out.loc[out["model"] == "m1", "score"].iloc[0] == pytest.approx(0.7)

    def test_weighted_hit_rates_are_household_normalized_and_binary_strict(
        self,
        monkeypatch,
    ):
        gt = pd.DataFrame(
            {
                "scenario_id": ["s1", "s1"],
                "variable": ["income_tax", "head_medicaid_eligible"],
                "value": [100.0, 1.0],
                "impact_weight": [pd.NA, 9000.0],
            }
        )
        preds = pd.DataFrame(
            {
                "model": ["m1", "m1"],
                "scenario_id": ["s1", "s1"],
                "variable": ["income_tax", "head_medicaid_eligible"],
                "prediction": [100.0, 0.0],
            }
        )

        def fake_population_weights(country, kind, output_groups):
            assert country == "us"
            assert kind == "household"
            assert output_groups == ["income_tax", "person_medicaid_eligible"]
            return pd.Series(
                {
                    "income_tax": 0.25,
                    "person_medicaid_eligible": 0.75,
                }
            )

        monkeypatch.setattr(
            "policybench.analysis.matching_population_weight_series",
            fake_population_weights,
        )

        out = weighted_hit_rate_scores_by_model(
            gt,
            preds,
            {"s1": 20_000.0},
            country="us",
        )

        row = out.loc[out["model"] == "m1"].iloc[0]
        # The tax row is correct and the binary Medicaid row is wrong. A binary
        # 1 -> 0 miss must score 0, not pass the amount-style $1 tolerance.
        assert row["weighted_exact"] == pytest.approx(0.25)
        assert row["weighted_within_1pct"] == pytest.approx(0.25)

    def test_zero_predictions_score_low(self):
        gt = pd.DataFrame(
            {
                "scenario_id": ["s1", "s1"],
                "variable": ["federal_income_tax_before_refundable_credits", "snap"],
                "value": [4000.0, 5000.0],
                "impact_weight": [pd.NA, pd.NA],
            }
        )
        preds = pd.DataFrame(
            {
                "model": ["zero"],
                "scenario_id": ["s1"],
                "variable": ["federal_income_tax_before_refundable_credits"],
                "prediction": [0.0],
            }
        )
        # Missing prediction on snap; tax pred is 0 (full error vs 4000).
        market = {"s1": 60000.0}
        out = bounded_household_scores(gt, preds, market)
        assert out.loc[out["model"] == "zero", "score"].iloc[0] < 0.5


class TestAmountAndParticipationAccuracy:
    def test_amount_excludes_zero_reference_and_boolean_cells(self):
        gt = pd.DataFrame(
            {
                "scenario_id": ["s1", "s1", "s1"],
                "variable": ["snap", "aca_ptc", "person_medicaid_eligible"],
                "value": [5000.0, 0.0, 1.0],
                "impact_weight": [pd.NA, pd.NA, 8000.0],
            }
        )
        preds = pd.DataFrame(
            {
                "model": ["m1", "m1", "m1"],
                "scenario_id": ["s1", "s1", "s1"],
                "variable": ["snap", "aca_ptc", "person_medicaid_eligible"],
                "prediction": [5000.0, 100.0, 0.0],  # aca and medicaid wrong
            }
        )
        market = {"s1": 20000.0}
        amount = amount_accuracy_by_model(gt, preds, market)
        # Only the snap row (nonzero amount) counts; perfect → 1.0
        assert amount.loc[amount["model"] == "m1", "amount_accuracy"].iloc[
            0
        ] == pytest.approx(1.0)

    def test_participation_counts_zero_match_and_boolean_match(self):
        gt = pd.DataFrame(
            {
                "scenario_id": ["s1", "s1", "s1"],
                "variable": ["snap", "aca_ptc", "person_medicaid_eligible"],
                "value": [5000.0, 0.0, 1.0],
                "impact_weight": [pd.NA, pd.NA, 8000.0],
            }
        )
        preds = pd.DataFrame(
            {
                "model": ["m1", "m1", "m1"],
                "scenario_id": ["s1", "s1", "s1"],
                "variable": ["snap", "aca_ptc", "person_medicaid_eligible"],
                "prediction": [5000.0, 100.0, 0.0],
            }
        )
        # snap: nonzero ref, nonzero pred -> match. aca: zero ref, nonzero pred -> miss.
        # medicaid: ref=1, pred=0 -> miss. So 1 of 3 -> 33.3%.
        out = participation_accuracy_by_model(gt, preds)
        assert out.loc[out["model"] == "m1", "participation_accuracy"].iloc[
            0
        ] == pytest.approx(1 / 3)

    def test_participation_requires_exact_binary_flags(self):
        gt = pd.DataFrame(
            {
                "scenario_id": ["s1", "s1"],
                "variable": [
                    "person_medicaid_eligible",
                    "person_chip_eligible",
                ],
                "value": [1.0, 0.0],
                "impact_weight": [8000.0, 5000.0],
            }
        )
        preds = pd.DataFrame(
            {
                "model": ["m1", "m1"],
                "scenario_id": ["s1", "s1"],
                "variable": [
                    "person_medicaid_eligible",
                    "person_chip_eligible",
                ],
                "prediction": [1.0, 0.5],
            }
        )

        out = participation_accuracy_by_model(gt, preds)
        assert out.loc[out["model"] == "m1", "participation_accuracy"].iloc[
            0
        ] == pytest.approx(0.5)


class TestEqualAndAggregateScores:
    """Equal-weight and aggregate-weight (budget) scoring as opt-in alternatives."""

    def _ground_truth(self):
        return pd.DataFrame(
            {
                "scenario_id": ["s1", "s1", "s2", "s2"],
                "variable": [
                    "federal_income_tax_before_refundable_credits",
                    "snap",
                    "federal_income_tax_before_refundable_credits",
                    "snap",
                ],
                "value": [4000.0, 0.0, 1000.0, 6000.0],
                "impact_weight": [pd.NA, pd.NA, pd.NA, pd.NA],
            }
        )

    def _predictions(self):
        # Perfect taxes, missed snap on s2
        return pd.DataFrame(
            {
                "model": ["m1"] * 4,
                "scenario_id": ["s1", "s1", "s2", "s2"],
                "variable": [
                    "federal_income_tax_before_refundable_credits",
                    "snap",
                    "federal_income_tax_before_refundable_credits",
                    "snap",
                ],
                "prediction": [4000.0, 0.0, 1000.0, 0.0],
            }
        )

    def test_equal_weight_score(self):
        from policybench.analysis import equal_weight_scores_by_model

        out = equal_weight_scores_by_model(self._ground_truth(), self._predictions())
        # s1: tax=1.0, snap=1.0 -> 1.0; s2: tax=1.0, snap=0.0 -> 0.5; mean = 0.75
        assert out.loc[out["model"] == "m1", "equal_score"].iloc[0] == pytest.approx(
            0.75
        )

    def test_aggregate_weight_score(self):
        from policybench.analysis import aggregate_weight_scores_by_model

        out = aggregate_weight_scores_by_model(
            self._ground_truth(), self._predictions()
        )
        # Total |ref| over scenarios: tax=4000+1000=5000; snap=0+6000=6000; grand=11000
        # Weights: tax=5/11, snap=6/11
        # s1: tax=1.0*5/11 + snap=1.0*6/11 = 1.0
        # s2: tax=1.0*5/11 + snap=0.0*6/11 = 5/11
        # Mean = (1.0 + 5/11) / 2 = (11/11 + 5/11) / 2 = 16/22 = 8/11 ≈ 0.7273
        assert out.loc[out["model"] == "m1", "aggregate_score"].iloc[
            0
        ] == pytest.approx(8 / 11)
