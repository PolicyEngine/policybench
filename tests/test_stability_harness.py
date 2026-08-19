"""Harness-side changes backing the stability spec: condition fingerprints,
repeat-set metadata, and cache-free repeated runs."""

import json
from unittest.mock import patch

import pandas as pd

from policybench.eval_no_tools import (
    _response_contract_metadata,
    run_repeated_no_tools_eval,
)
from policybench.scenarios import scenario_manifest


class TestConditionFingerprint:
    def test_default_condition_is_forced_no_override(self, monkeypatch):
        monkeypatch.delenv("POLICYBENCH_TOOL_CHOICE", raising=False)
        monkeypatch.delenv("POLICYBENCH_CHUNK_OVERRIDE", raising=False)
        contract = _response_contract_metadata()
        assert contract["tool_choice_condition"] == "forced"
        assert contract["chunk_override"] is None

    def test_env_conditions_enter_the_fingerprint(self, monkeypatch):
        monkeypatch.setenv("POLICYBENCH_TOOL_CHOICE", "auto")
        monkeypatch.setenv("POLICYBENCH_CHUNK_OVERRIDE", "none")
        contract = _response_contract_metadata()
        assert contract["tool_choice_condition"] == "auto"
        assert contract["chunk_override"] == "none"


class TestRunsMetadata:
    def test_repeated_eval_writes_runs_metadata(
        self, tmp_path, sample_scenarios, monkeypatch
    ):
        monkeypatch.delenv("POLICYBENCH_TOOL_CHOICE", raising=False)

        def fake_run(scenarios, models=None, programs=None, output_path=None, run_id=None, include_explanations=True):
            frame = pd.DataFrame(
                {
                    "run_id": [run_id],
                    "model": ["m"],
                    "scenario_id": [scenarios[0].id],
                    "variable": ["snap"],
                    "prediction": [1.0],
                }
            )
            frame.to_csv(output_path, index=False)
            return frame

        with patch("policybench.eval_no_tools.run_no_tools_eval", side_effect=fake_run):
            run_repeated_no_tools_eval(
                sample_scenarios,
                repeats=2,
                output_dir=str(tmp_path),
                models={"m": "m"},
                programs=["snap"],
            )

        metadata = json.loads((tmp_path / "runs_metadata.json").read_text())
        assert metadata["repeats"] == 2
        assert metadata["models"] == {"m": "m"}
        assert metadata["programs"] == ["snap"]
        assert metadata["cache_enabled"] is False
        assert metadata["response_contract"]["tool_choice_condition"] == "forced"
        assert metadata["scenario_count"] == len(sample_scenarios)

    def test_mixed_model_groups_in_one_directory_rejected(
        self, tmp_path, sample_scenarios, monkeypatch
    ):
        monkeypatch.delenv("POLICYBENCH_TOOL_CHOICE", raising=False)

        def fake_run(scenarios, models=None, programs=None, output_path=None, run_id=None, include_explanations=True):
            frame = pd.DataFrame(
                {
                    "run_id": [run_id],
                    "model": [next(iter(models))],
                    "scenario_id": [scenarios[0].id],
                    "variable": ["snap"],
                    "prediction": [1.0],
                }
            )
            frame.to_csv(output_path, index=False)
            return frame

        with patch("policybench.eval_no_tools.run_no_tools_eval", side_effect=fake_run):
            run_repeated_no_tools_eval(
                sample_scenarios,
                repeats=1,
                output_dir=str(tmp_path),
                models={"m1": "m1"},
                programs=["snap"],
            )
            try:
                run_repeated_no_tools_eval(
                    sample_scenarios,
                    repeats=1,
                    output_dir=str(tmp_path),
                    models={"m2": "m2"},
                    programs=["snap"],
                )
            except ValueError as exc:
                assert "models" in str(exc)
            else:
                raise AssertionError("expected ValueError for mixed model groups")


class TestRepeatedRunsCacheFree:
    def _manifest(self, tmp_path, sample_scenarios):
        path = tmp_path / "scenarios.csv"
        scenario_manifest(sample_scenarios).to_csv(path, index=False)
        return path

    def test_repeated_command_does_not_enable_cache(self, tmp_path, sample_scenarios):
        from policybench import cli

        manifest = self._manifest(tmp_path, sample_scenarios)
        argv = [
            "policybench",
            "eval-no-tools-repeated",
            "--scenario-manifest",
            str(manifest),
            "--num-scenarios",
            str(len(sample_scenarios)),
            "--output-dir",
            str(tmp_path / "runs"),
            "--repeats",
            "1",
        ]
        with (
            patch("policybench.cache.enable_cache") as enable_cache,
            patch(
                "policybench.eval_no_tools.run_repeated_no_tools_eval",
                return_value=pd.DataFrame(),
            ) as run,
            patch("sys.argv", argv),
        ):
            cli.main()
        enable_cache.assert_not_called()
        run.assert_called_once()

    def test_single_eval_still_enables_cache(self, tmp_path, sample_scenarios):
        from policybench import cli

        manifest = self._manifest(tmp_path, sample_scenarios)
        argv = [
            "policybench",
            "eval-no-tools",
            "--scenario-manifest",
            str(manifest),
            "--num-scenarios",
            str(len(sample_scenarios)),
            "--output",
            str(tmp_path / "predictions.csv"),
        ]
        with (
            patch("policybench.cache.enable_cache") as enable_cache,
            patch(
                "policybench.eval_no_tools.run_no_tools_eval",
                return_value=pd.DataFrame(),
            ),
            patch("sys.argv", argv),
        ):
            cli.main()
        enable_cache.assert_called_once()
