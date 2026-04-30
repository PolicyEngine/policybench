"""Tests for chunked no-tools evaluation orchestration."""

from pathlib import Path

import pandas as pd

from policybench.chunked_eval import (
    chunk_is_complete,
    chunk_scenario_ranges,
    merge_model_outputs,
    run_chunk,
    run_chunk_with_retries,
    run_chunked_eval,
)


def test_chunk_is_complete_requires_expected_rows_and_clean_predictions(tmp_path):
    path = tmp_path / "chunk.csv"
    pd.DataFrame(
        {
            "model": ["m", "m"],
            "scenario_id": ["s1", "s1"],
            "variable": ["income_tax", "income_tax_applied_credits"],
            "prediction": [1.0, 2.0],
            "explanation": ["Wages drive tax.", "Income is too high."],
            "error": [None, None],
        }
    ).to_csv(path, index=False)

    assert chunk_is_complete(path, scenario_program_counts=[2])
    assert not chunk_is_complete(path, scenario_program_counts=[3])


def test_chunk_is_complete_rejects_error_rows(tmp_path):
    path = tmp_path / "chunk.csv"
    pd.DataFrame(
        {
            "model": ["m", "m"],
            "scenario_id": ["s1", "s1"],
            "variable": ["income_tax", "income_tax_applied_credits"],
            "prediction": [1.0, None],
            "explanation": ["Wages drive tax.", "Income is too high."],
            "error": [None, "RateLimitError: insufficient_quota"],
        }
    ).to_csv(path, index=False)

    assert not chunk_is_complete(path, scenario_program_counts=[2])


def test_chunk_is_complete_requires_explanations_by_default(tmp_path):
    path = tmp_path / "chunk.csv"
    pd.DataFrame(
        {
            "model": ["m", "m"],
            "scenario_id": ["s1", "s1"],
            "variable": ["income_tax", "income_tax_applied_credits"],
            "prediction": [1.0, 2.0],
            "explanation": ["Wages drive tax.", ""],
            "error": [None, None],
        }
    ).to_csv(path, index=False)

    assert not chunk_is_complete(path, scenario_program_counts=[2])
    assert chunk_is_complete(
        path,
        scenario_program_counts=[2],
        require_explanations=False,
    )


def test_chunk_is_complete_rejects_missing_prediction_column(tmp_path):
    path = tmp_path / "chunk.csv"
    pd.DataFrame(
        {
            "model": ["m"],
            "scenario_id": ["s1"],
            "variable": ["income_tax"],
            "explanation": ["Wages drive tax."],
            "error": [None],
        }
    ).to_csv(path, index=False)

    assert not chunk_is_complete(path, scenario_program_counts=[1])


def test_chunk_scenario_ranges_builds_stable_paths(tmp_path):
    chunks = chunk_scenario_ranges(
        scenario_count=25,
        chunk_size=10,
        chunk_dir=tmp_path / "chunks",
    )

    assert [(chunk.start, chunk.end, chunk.path.name) for chunk in chunks] == [
        (0, 10, "s0000_0010.csv"),
        (10, 20, "s0010_0020.csv"),
        (20, 25, "s0020_0025.csv"),
    ]


def test_run_chunk_invokes_package_cli(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, check):
        calls.append((cmd, check))

    monkeypatch.setattr("policybench.chunked_eval.subprocess.run", fake_run)

    run_chunk(
        country="us",
        model="gpt-5.5",
        program_set="v2_headline",
        scenario_manifest=tmp_path / "scenarios.csv",
        scenario_count=100,
        output=tmp_path / "chunk.csv",
        start=20,
        end=30,
        include_explanations=True,
        single_output=False,
    )

    cmd, check = calls[0]
    assert check is True
    assert cmd[1:4] == ["-m", "policybench.cli", "eval-no-tools"]
    assert "--scenario-start" in cmd
    assert cmd[cmd.index("--scenario-start") + 1] == "20"
    assert "--scenario-end" in cmd
    assert cmd[cmd.index("--scenario-end") + 1] == "30"
    assert "--model" in cmd
    assert cmd[cmd.index("--model") + 1] == "gpt-5.5"
    assert "--no-explanations" not in cmd


def test_run_chunk_adds_ablation_flags(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, check):
        calls.append((cmd, check))

    monkeypatch.setattr("policybench.chunked_eval.subprocess.run", fake_run)

    run_chunk(
        country="us",
        model="gpt-5.5",
        program_set="v2_headline",
        scenario_manifest=tmp_path / "scenarios.csv",
        scenario_count=100,
        output=tmp_path / "chunk.csv",
        start=0,
        end=1,
        include_explanations=False,
        single_output=True,
    )

    cmd, _ = calls[0]
    assert "--no-explanations" in cmd
    assert "--single-output" in cmd


def test_run_chunk_with_retries_retries_incomplete_output(monkeypatch, tmp_path):
    output = tmp_path / "chunk.csv"
    calls = []

    def fake_run_chunk(**kwargs):
        calls.append(kwargs)
        explanation = "" if len(calls) == 1 else "Wages drive tax."
        pd.DataFrame(
            {
                "model": ["gpt-5.5"],
                "scenario_id": ["s1"],
                "variable": ["income_tax"],
                "prediction": [1.0],
                "explanation": [explanation],
                "error": [None],
            }
        ).to_csv(output, index=False)

    monkeypatch.setattr("policybench.chunked_eval.run_chunk", fake_run_chunk)

    run_chunk_with_retries(
        country="us",
        model="gpt-5.5",
        program_set="v2_headline",
        scenario_manifest=tmp_path / "scenarios.csv",
        scenario_count=1,
        output=output,
        start=0,
        end=1,
        include_explanations=True,
        single_output=False,
        scenario_program_counts=[1],
        attempts=2,
    )

    assert len(calls) == 2
    assert chunk_is_complete(output, scenario_program_counts=[1])


def test_merge_model_outputs_writes_combined_predictions(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    pd.DataFrame(
        {
            "model": ["m1"],
            "scenario_id": ["s1"],
            "variable": ["income_tax"],
            "prediction": [1.0],
        }
    ).to_csv(first, index=False)
    pd.DataFrame(
        {
            "model": ["m2"],
            "scenario_id": ["s1"],
            "variable": ["income_tax"],
            "prediction": [2.0],
        }
    ).to_csv(second, index=False)

    output = merge_model_outputs(
        model_output_paths=[first, second],
        output_path=tmp_path / "predictions.csv",
    )

    combined = pd.read_csv(output)
    assert combined["model"].tolist() == ["m1", "m2"]
    assert combined["prediction"].tolist() == [1.0, 2.0]


def test_run_chunked_eval_runs_requested_models_and_merges(monkeypatch, tmp_path):
    calls = []

    def fake_run_model_chunks(**kwargs):
        calls.append(kwargs)
        output = Path(kwargs["output_dir"]) / "by_model" / (kwargs["model"] + ".csv")
        output.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            {
                "model": [kwargs["model"]],
                "scenario_id": ["s1"],
                "variable": ["income_tax"],
                "prediction": [1.0],
            }
        ).to_csv(output, index=False)
        return output

    monkeypatch.setattr(
        "policybench.chunked_eval.run_model_chunks",
        fake_run_model_chunks,
    )

    output = run_chunked_eval(
        scenario_manifest=tmp_path / "scenarios.csv",
        output_dir=tmp_path / "predictions",
        country="us",
        models=["gpt-5.5", "claude-opus-4.7"],
        program_set="v2_headline",
        chunk_size=10,
        parallel=2,
        model_parallel=1,
        chunk_attempts=1,
        include_explanations=True,
        single_output=False,
    )

    assert [call["model"] for call in calls] == ["gpt-5.5", "claude-opus-4.7"]
    assert output == tmp_path / "predictions" / "predictions.csv"
    assert pd.read_csv(output)["model"].tolist() == ["gpt-5.5", "claude-opus-4.7"]


def test_run_chunked_eval_can_parallelize_models(monkeypatch, tmp_path):
    calls = []

    def fake_run_model_chunks(**kwargs):
        calls.append(kwargs)
        output = Path(kwargs["output_dir"]) / "by_model" / (kwargs["model"] + ".csv")
        output.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            {
                "model": [kwargs["model"]],
                "scenario_id": ["s1"],
                "variable": ["income_tax"],
                "prediction": [1.0],
            }
        ).to_csv(output, index=False)
        return output

    monkeypatch.setattr(
        "policybench.chunked_eval.run_model_chunks",
        fake_run_model_chunks,
    )

    output = run_chunked_eval(
        scenario_manifest=tmp_path / "scenarios.csv",
        output_dir=tmp_path / "predictions",
        country="us",
        models=["gpt-5.5", "claude-opus-4.7"],
        program_set="v2_headline",
        chunk_size=10,
        parallel=2,
        model_parallel=2,
        chunk_attempts=3,
        include_explanations=True,
        single_output=False,
    )

    assert sorted(call["model"] for call in calls) == [
        "claude-opus-4.7",
        "gpt-5.5",
    ]
    assert {call["chunk_attempts"] for call in calls} == {3}
    assert output == tmp_path / "predictions" / "predictions.csv"
