"""End-to-end tests for the stability suite commands (all external calls mocked)."""

import json
from unittest.mock import patch

import pandas as pd
import pytest

from policybench.reasoning_stability import text_key
from policybench.stability import CacheContaminationError
from policybench.stability_report import (
    read_runs_metadata,
    run_counterfactual_manifest,
    run_counterfactual_report,
    run_reasoning_stability,
    run_stability_report,
    serving_config_diff,
    stability_cost_plan,
)

VARIABLES = ["snap", "payroll_tax", "person_wic_eligible"]
SCENARIOS = ["scenario_000", "scenario_001"]


def _reference(tmp_path):
    rows = []
    for sid, values in zip(
        SCENARIOS, [[100.0, 500.0, 1.0], [0.0, 700.0, 0.0]], strict=True
    ):
        for var, value in zip(VARIABLES, values, strict=True):
            rows.append({"scenario_id": sid, "variable": var, "value": value})
    path = tmp_path / "reference_outputs.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _manifest(tmp_path):
    path = tmp_path / "scenarios.csv"
    pd.DataFrame(
        {
            "scenario_id": SCENARIOS,
            "country": ["us", "us"],
            "total_income": [30000.0, 45000.0],
        }
    ).to_csv(path, index=False)
    return path


def _run_frame(model, run_id, jitter=0.0, explanation_suffix=""):
    rows = []
    for sid, values in zip(
        SCENARIOS, [[100.0, 500.0, 1.0], [0.0, 700.0, 0.0]], strict=True
    ):
        for var, value in zip(VARIABLES, values, strict=True):
            pred = value + (jitter if var == "snap" else 0.0)
            rows.append(
                {
                    "run_id": run_id,
                    "model": model,
                    "scenario_id": sid,
                    "variable": var,
                    "prediction": pred,
                    "explanation": f"{var} derived for {sid}{explanation_suffix}",
                    "provider_response_id": f"{model}-{run_id}-{sid}",
                }
            )
    return pd.DataFrame(rows)


def _write_runs(path, model, k=2, cache_hit=False, with_metadata=True, jitter=0.0):
    path.mkdir(parents=True, exist_ok=True)
    for i in range(k):
        run_id = f"run_{i:03d}"
        frame = _run_frame(
            model,
            run_id,
            jitter=jitter * i,
            explanation_suffix=f" (run {i})" if jitter else "",
        )
        frame.to_csv(path / f"{run_id}.csv", index=False)
        ledger = path / f"{run_id}.csv.spend.jsonl"
        ledger.write_text(json.dumps({"cache_hit": cache_hit and i > 0}) + "\n")
    if with_metadata:
        (path / "runs_metadata.json").write_text(
            json.dumps(
                {
                    "scenario_hash": "abc",
                    "programs": VARIABLES,
                    "repeats": k,
                    "response_contract": {
                        "tool_choice_condition": "forced",
                        "chunk_override": None,
                    },
                    "cache_enabled": False,
                }
            )
        )
    return path


class TestStabilityReport:
    def test_writes_tables_and_metadata(self, tmp_path):
        runs_a = _write_runs(tmp_path / "runs" / "a", "gpt-5.6-sol", jitter=5.0)
        runs_b = _write_runs(tmp_path / "runs" / "b", "claude-opus-5")
        out = tmp_path / "stability"
        result = run_stability_report(
            runs_dirs=[runs_a, runs_b],
            reference_outputs=_reference(tmp_path),
            scenario_manifest=_manifest(tmp_path),
            output_dir=out,
            n_boot=20,
            seed=1,
            serving_config=None,
        )
        assert (out / "row_stability_by_model.csv").exists()
        assert (out / "variance_decomposition_by_model.csv").exists()
        assert (out / "run_stability_by_model.csv").exists()
        metadata = json.loads((out / "stability_metadata.json").read_text())
        assert metadata["stability_spec_version"] == "2026-08-18-v1"
        assert metadata["cache_guard"]["cache_hits"] == 0
        assert (
            metadata["runs_metadata"]["condition"]["tool_choice_condition"] == "forced"
        )
        assert metadata["cross_run_response_id_duplicates"] == 0
        assert set(metadata["models"]) == {"gpt-5.6-sol", "claude-opus-5"}
        row_table = result["tables"]["row_stability_by_model"].set_index("model")
        # The jittered model flips its snap answers; the other is unanimous.
        assert row_table.loc["gpt-5.6-sol", "answer_flip_rate"] > 0
        assert row_table.loc["claude-opus-5", "answer_flip_rate"] == 0
        assert (
            "pooled_run_to_sampling_ratio" in metadata["pooled_variance_decomposition"]
        )

    def test_cache_contamination_hard_fails(self, tmp_path):
        runs = _write_runs(tmp_path / "runs", "gpt-5.6-sol", cache_hit=True)
        with pytest.raises(CacheContaminationError):
            run_stability_report(
                runs_dirs=[runs],
                reference_outputs=_reference(tmp_path),
                scenario_manifest=_manifest(tmp_path),
                output_dir=tmp_path / "out",
                n_boot=5,
                serving_config=None,
            )

    def test_mismatched_condition_refuses_to_pool(self, tmp_path):
        runs_a = _write_runs(tmp_path / "a", "m1")
        runs_b = _write_runs(tmp_path / "b", "m2")
        meta = json.loads((runs_b / "runs_metadata.json").read_text())
        meta["response_contract"]["tool_choice_condition"] = "auto"
        (runs_b / "runs_metadata.json").write_text(json.dumps(meta))
        with pytest.raises(ValueError, match="fingerprint"):
            read_runs_metadata([runs_a, runs_b])

    def test_missing_sidecars_are_reported_not_fatal(self, tmp_path):
        runs = _write_runs(tmp_path / "a", "m1", with_metadata=False)
        meta = read_runs_metadata([runs])
        assert meta["sidecars_missing"] == [str(runs)]
        assert meta["condition"] is None


class TestServingConfigDiff:
    def test_diffs_against_registry(self, tmp_path):
        registry = tmp_path / "serving.json"
        registry.write_text(
            json.dumps(
                {
                    "models": {
                        "gpt-5.6-sol": {
                            "answer_contract": "tool",
                            "request_shape": "whole scenario",
                            "tool_choice": "forced",
                        }
                    }
                }
            )
        )
        diff = serving_config_diff(
            ["gpt-5.6-sol", "claude-fable-5"],
            {"tool_choice_condition": "auto", "chunk_override": None},
            registry,
        )
        assert diff["gpt-5.6-sol"]["in_snapshot_registry"] is True
        assert diff["gpt-5.6-sol"]["diffs"]["tool_choice"] == {
            "effective": "auto",
            "snapshot": "forced",
        }
        assert diff["claude-fable-5"]["in_snapshot_registry"] is False
        assert (
            diff["claude-fable-5"]["effective"]["request_shape"] == "1 output/request"
        )


class TestCounterfactualManifestCommand:
    def test_writes_manifest_deltas_and_drift(self, tmp_path, sample_scenarios):
        from policybench.scenarios import scenario_manifest

        base_manifest = tmp_path / "base.csv"
        scenario_manifest(sample_scenarios).to_csv(base_manifest, index=False)
        frozen = tmp_path / "frozen.csv"
        pd.DataFrame(
            {
                "scenario_id": [s.id for s in sample_scenarios],
                "variable": ["snap"] * 3,
                "value": [100.0, 100.0, 160.0],
            }
        ).to_csv(frozen, index=False)

        def fake_deltas(base, twins, programs, year):
            return pd.DataFrame(
                {
                    "scenario_id": [s.id for s in base],
                    "variable": ["snap"] * 3,
                    "base_value": [100.0, 100.0, 100.0],
                    "perturbed_value": [100.0, 50.0, 100.0],
                    "true_delta": [0.0, -50.0, 0.0],
                    "is_binary": [False] * 3,
                    "output_group": ["snap"] * 3,
                    "first_dollar": [False] * 3,
                }
            )

        with patch(
            "policybench.stability_report.compute_truth_deltas", side_effect=fake_deltas
        ):
            metadata = run_counterfactual_manifest(
                scenario_manifest=base_manifest,
                output_dir=tmp_path / "cf",
                programs=["snap"],
                year=2026,
                frozen_reference_outputs=frozen,
            )
        assert (tmp_path / "cf" / "cf_scenarios.csv").exists()
        assert (tmp_path / "cf" / "truth_deltas.csv").exists()
        summary = metadata["truth_delta_summary"]
        assert summary["n_nonzero_amount_rows"] == 1
        assert summary["n_negative"] == 1
        assert summary["n_binary_flips"] == 0
        drift = metadata["base_vs_frozen_reference_drift"]
        assert drift["n_compared"] == 3
        assert drift["n_within_1usd"] == 2
        assert drift["max_abs_drift"] == pytest.approx(60.0)

    def test_skip_reference_outputs(self, tmp_path, sample_scenarios):
        from policybench.scenarios import scenario_manifest

        base_manifest = tmp_path / "base.csv"
        scenario_manifest(sample_scenarios).to_csv(base_manifest, index=False)
        metadata = run_counterfactual_manifest(
            scenario_manifest=base_manifest,
            output_dir=tmp_path / "cf",
            programs=["snap"],
            year=2026,
            compute_references=False,
        )
        assert "truth_deltas" not in metadata
        assert metadata["perturbation"]["n_scenarios"] == 3


class TestCounterfactualReportCommand:
    def _truth(self, tmp_path):
        rows = []
        for sid in SCENARIOS:
            rows.append(
                {
                    "scenario_id": sid,
                    "variable": "payroll_tax",
                    "base_value": 500.0,
                    "true_delta": 76.5,
                    "is_binary": False,
                    "output_group": "payroll_tax",
                    "first_dollar": False,
                }
            )
            rows.append(
                {
                    "scenario_id": sid,
                    "variable": "person_wic_eligible",
                    "base_value": 1.0,
                    "true_delta": 0.0,
                    "is_binary": True,
                    "output_group": "person_wic_eligible",
                    "first_dollar": False,
                }
            )
        path = tmp_path / "truth_deltas.csv"
        pd.DataFrame(rows).to_csv(path, index=False)
        return path

    def test_with_repeats_as_base_arm(self, tmp_path):
        runs = _write_runs(tmp_path / "runs", "m", k=2)
        perturbed = _run_frame("m", "run_000").drop(columns=["run_id"])
        perturbed["scenario_id"] = perturbed["scenario_id"] + "__cf1k"
        perturbed.loc[perturbed["variable"] == "payroll_tax", "prediction"] += 76.5
        perturbed_path = tmp_path / "perturbed.csv"
        perturbed.to_csv(perturbed_path, index=False)
        out = tmp_path / "cf_report"
        result = run_counterfactual_report(
            perturbed_predictions=perturbed_path,
            truth_deltas=self._truth(tmp_path),
            output_dir=out,
            base_runs_dirs=[runs],
            n_boot=20,
        )
        tables = result["tables"]
        summary = tables["delta_summary"].set_index("model")
        assert summary.loc["m", "delta_exact_rate_nonzero"] == pytest.approx(1.0)
        assert "noise_floor_summary" in tables
        assert "signal_vs_noise" in tables
        assert (out / "delta_summary.csv").exists()
        metadata = json.loads((out / "stability_metadata.json").read_text())
        assert metadata["cache_guard"]["cache_hits"] == 0

    def test_single_base_file(self, tmp_path):
        base = _run_frame("m", "run_000").drop(columns=["run_id"])
        base_path = tmp_path / "base.csv"
        base.to_csv(base_path, index=False)
        perturbed = base.copy()
        perturbed["scenario_id"] = perturbed["scenario_id"] + "__cf1k"
        perturbed_path = tmp_path / "perturbed.csv"
        perturbed.to_csv(perturbed_path, index=False)
        result = run_counterfactual_report(
            perturbed_predictions=perturbed_path,
            truth_deltas=self._truth(tmp_path),
            output_dir=tmp_path / "out",
            base_predictions=base_path,
            n_boot=5,
        )
        assert "noise_floor_summary" not in result["tables"]
        summary = result["tables"]["delta_summary"].set_index("model")
        # No movement on payroll -> misses both nonzero rows.
        assert summary.loc["m", "delta_exact_rate_nonzero"] == pytest.approx(0.0)


class TestReasoningStabilityCommand:
    def test_deterministic_only_path(self, tmp_path):
        runs = _write_runs(tmp_path / "runs", "m", k=2, jitter=0.0)
        out = tmp_path / "reasoning"
        result = run_reasoning_stability(
            runs_dirs=[runs],
            reference_outputs=_reference(tmp_path),
            output_dir=out,
            reference_explanations=None,
            gold_set=None,
            deterministic_only=True,
            min_stable_exact_pairs=1,
        )
        summary = result["tables"]["reasoning_stability_by_model"].set_index("model")
        # Identical explanations across runs: every stable pair short-circuits.
        assert summary.loc["m", "short_circuit_share_stable"] == pytest.approx(1.0)
        assert summary.loc[
            "m", "right_answer_unstable_reasoning_rate"
        ] == pytest.approx(0.0)
        metadata = json.loads((out / "stability_metadata.json").read_text())
        assert metadata["judge"]["deterministic_only"] is True
        assert metadata["validation"] == {}

    def test_judged_path_with_mocked_extraction(self, tmp_path):
        runs = _write_runs(tmp_path / "runs", "m", k=2, jitter=0.0)
        # Make explanations differ across runs so the judge is needed.
        for i in range(2):
            path = runs / f"run_{i:03d}.csv"
            frame = pd.read_csv(path)
            frame["explanation"] = frame["explanation"] + f" (run {i})"
            frame.to_csv(path, index=False)
        ref_expl = tmp_path / "reference_explanations.csv"
        pd.DataFrame(
            {
                "scenario_id": SCENARIOS * 3,
                "variable": [v for v in VARIABLES for _ in SCENARIOS],
                "explanation": [
                    f"reference {v} {s}" for v in VARIABLES for s in SCENARIOS
                ],
            }
        ).to_csv(ref_expl, index=False)
        gold = tmp_path / "gold.csv"
        pd.DataFrame(
            {
                "variable": ["snap", "payroll_tax"],
                "explanation": ["gold snap text", "gold payroll text"],
                "labels": ["categorical_eligibility", "payroll_tax_base"],
            }
        ).to_csv(gold, index=False)

        def fake_extraction(
            items, judge_model, cache_path, concurrency=8, grade_pass=0
        ):
            out = {}
            for item in items:
                item_key = text_key(item["variable"], item["text"])
                key = f"{judge_model}|{item_key}|{grade_pass}"
                if item["variable"] == "payroll_tax":
                    labels = ["payroll_tax_base"]
                elif item["variable"] == "snap":
                    # Primary judge disagrees with itself across runs on snap.
                    labels = (
                        ["categorical_eligibility"]
                        if "run 0" in item["text"]
                        else ["thresholds_rates"]
                    )
                    if "gold" in item["text"]:
                        labels = ["categorical_eligibility"]
                else:
                    labels = ["age_disability"]
                out[key] = {
                    "key": key,
                    "text_key": text_key(item["variable"], item["text"]),
                    "variable": item["variable"],
                    "judge_model": judge_model,
                    "prompt_version": "test",
                    "grade_pass": grade_pass,
                    "labels": labels,
                    "error": "",
                }
            return out

        def gold_eval(accuracy, ci_low):
            return {
                "judge_model": "judge",
                "n_gold": 100,
                "n_graded": 100,
                "exact_set_accuracy": accuracy,
                "exact_set_accuracy_ci_low": ci_low,
                "exact_set_accuracy_ci_high": 1.0,
                "krippendorff_alpha_jaccard": 1.0,
                "per_label": pd.DataFrame({"label": ["other"], "agreement": [1.0]}),
            }

        def run(gold_result, output_dir):
            # evaluate_against_gold keys by judge_cache_key; the fake extraction
            # keys differ, so the gold evaluation is stubbed at the gate level.
            with (
                patch(
                    "policybench.stability_report.run_label_extraction",
                    side_effect=fake_extraction,
                ),
                patch(
                    "policybench.stability_report.evaluate_against_gold",
                    return_value=gold_result,
                ),
            ):
                return run_reasoning_stability(
                    runs_dirs=[runs],
                    reference_outputs=_reference(tmp_path),
                    output_dir=output_dir,
                    reference_explanations=ref_expl,
                    gold_set=gold,
                    judge_model="judge",
                    cross_judge_model="cross",
                    validation_modulus=1,
                    min_stable_exact_pairs=1,
                )

        result = run(gold_eval(0.95, 0.89), tmp_path / "reasoning")
        summary = result["tables"]["reasoning_stability_by_model"].set_index("model")
        # snap pairs disagree (2 scenarios), payroll agree (2), wic agree (2).
        assert summary.loc[
            "m", "right_answer_unstable_reasoning_rate"
        ] == pytest.approx(2 / 6)
        validation = result["validation"]
        assert validation["gold_gate"]["status"] == "pass"
        assert validation["cross_judge"]["n"] > 0
        assert validation["cross_judge_gate"]["status"] in {"pass", "pass_marginal"}
        assert "determinism_floor" in validation
        assert validation["judge_below_reliability_bar"] is False
        assert "reference_alignment_by_model" in result["tables"]
        assert "dominant_label_set_share_by_model" in result["tables"]
        assert (
            tmp_path / "reasoning" / "validation_cross_judge_per_label.csv"
        ).exists()

        # A gold gate whose CI lower bound sits under the floor fails CI-aware,
        # and the headline is withheld (exported as NaN) while companions stay.
        failed = run(gold_eval(0.85, 0.60), tmp_path / "reasoning_failed")
        failed_summary = failed["tables"]["reasoning_stability_by_model"].set_index(
            "model"
        )
        assert failed["validation"]["gold_gate"]["status"] == "fail"
        assert failed["validation"]["judge_below_reliability_bar"] is True
        assert pd.isna(failed_summary.loc["m", "right_answer_unstable_reasoning_rate"])
        assert failed_summary.loc[
            "m", "joint_unstable_reasoning_rate_all_pairs"
        ] == pytest.approx(2 / 6)


class TestCostPlan:
    def test_prices_from_logged_usage_with_override_fallback(self):
        predictions = pd.DataFrame(
            {
                "model": ["gpt-5.4-mini"] * 4 + ["kimi-k3"] * 4,
                "scenario_id": ["s1", "s1", "s2", "s2"] * 2,
                "variable": ["snap", "ssi"] * 4,
                "prediction": [1.0] * 8,
                "prompt_tokens": [100] * 8,
                "completion_tokens": [50] * 8,
                "total_tokens": [150] * 8,
                "total_cost_usd": [0.01] * 4 + [0.0] * 4,
            }
        )
        plan = stability_cost_plan(predictions, repeats=3, cf_arms=1).set_index("model")
        assert plan.loc["gpt-5.4-mini", "cost_basis"] == "logged"
        assert plan.loc["gpt-5.4-mini", "cost_per_run_usd"] == pytest.approx(0.04)
        assert plan.loc["gpt-5.4-mini", "model_spend_usd"] == pytest.approx(0.16)
        assert plan.loc["kimi-k3", "cost_basis"] == "override_prices"
        # 400 prompt tokens at $3/M + 200 completion at $15/M.
        assert plan.loc["kimi-k3", "cost_per_run_usd"] == pytest.approx(0.0012 + 0.003)
        assert plan.loc["gpt-5.4-mini", "judge_calls"] == round(4 * 3 * 1.1)
        assert "__total__" in plan.index
