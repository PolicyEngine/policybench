"""Tests for chunked no-tools evaluation orchestration."""

import itertools
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pandas as pd
import pytest

from policybench.chunked_eval import (
    PolicyEngineProvenanceHandoff,
    chunk_is_complete,
    chunk_scenario_ranges,
    merge_chunks,
    merge_model_outputs,
    run_chunk,
    run_chunk_with_retries,
    run_chunked_eval,
    run_model_chunks,
)
from policybench.config import DEFAULT_PROGRAM_SET, get_programs
from policybench.policyengine_runtime import (
    POLICYENGINE_PROVENANCE_ENV,
    POLICYENGINE_PROVENANCE_FILENAME,
)
from policybench.scenarios import Person, Scenario, scenario_to_dict
from policybench.spec import expand_programs_for_scenario
from policybench.spend_ledger import (
    read_spend_ledger,
    spend_ledger_path,
    upsert_spend_ledger,
)
from tests.policyengine_probe import probe_environment, probe_records

# MOCK bundles: the unit tests below never import PolicyEngine, so the fake
# writer records these placeholders. The end-to-end tests at the bottom run
# the real writer in a fresh interpreter.
MOCK_BUNDLES = {
    "us": {"bundle_id": "MOCK-us", "country_id": "us"},
    "uk": {"bundle_id": "MOCK-uk", "country_id": "uk"},
}


@pytest.fixture(autouse=True)
def provenance_writer(monkeypatch):
    """Replace the fresh-interpreter provenance writer with one that writes
    MOCK bundles, and record each call."""
    calls = []

    def fake_writer(python, path, countries, env, **kwargs):
        path = Path(path)
        calls.append(
            {
                "python": python,
                "path": path,
                "countries": list(countries),
                "env": dict(env),
                "existing": path.read_text() if path.exists() else None,
            }
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        bundles = {country: MOCK_BUNDLES[country] for country in countries}
        path.write_text(json.dumps({"policyengine_bundles": bundles}))
        return True

    monkeypatch.setattr(
        "policybench.chunked_eval.run_policyengine_provenance_writer", fake_writer
    )
    return calls


def _probe_scenarios(count: int) -> list[Scenario]:
    return [
        Scenario(
            id=f"probe_{index}",
            state="CA",
            filing_status="single",
            adults=[Person(name="adult", age=35, employment_income=50_000)],
        )
        for index in range(count)
    ]


def _write_manifest(path: Path, scenarios: list[Scenario]) -> Path:
    pd.DataFrame(
        {
            "scenario_id": [scenario.id for scenario in scenarios],
            "scenario_json": [
                json.dumps(scenario_to_dict(scenario)) for scenario in scenarios
            ],
        }
    ).to_csv(path, index=False)
    return path


def _complete_chunk_writer(scenarios: list[Scenario], calls: list):
    """A run_chunk stand-in that records its call and writes a complete chunk."""
    programs = get_programs("us", DEFAULT_PROGRAM_SET)
    lock = threading.Lock()

    def fake_run_chunk(**kwargs):
        with lock:
            calls.append(kwargs)
        rows = []
        for scenario in scenarios[kwargs["start"] : kwargs["end"]]:
            variables = expand_programs_for_scenario(programs, scenario)
            raw_response = json.dumps(
                {
                    "outputs": {
                        variable: {"value": 1, "explanation": "It is 1."}
                        for variable in variables
                    }
                }
            )
            rows.extend(
                {
                    "model": kwargs["model"],
                    "scenario_id": scenario.id,
                    "variable": variable,
                    "prediction": 1.0,
                    "explanation": "It is 1.",
                    "raw_response": raw_response,
                    "error": None,
                }
                for variable in variables
            )
        kwargs["output"].parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(kwargs["output"], index=False)

    return fake_run_chunk


def test_chunk_is_complete_requires_expected_rows(tmp_path):
    path = tmp_path / "chunk.csv"
    pd.DataFrame(
        {
            "model": ["m", "m"],
            "scenario_id": ["s1", "s1"],
            "variable": ["income_tax", "federal_refundable_credits"],
            "prediction": [1.0, 2.0],
            "explanation": ["Wages drive tax.", "Income is too high."],
            "error": [None, None],
        }
    ).to_csv(path, index=False)

    assert chunk_is_complete(path, scenario_program_counts=[2])
    assert not chunk_is_complete(path, scenario_program_counts=[3])


def test_chunk_is_complete_keeps_model_contract_errors_as_benchmark_outcomes(
    tmp_path,
):
    path = tmp_path / "chunk.csv"
    pd.DataFrame(
        {
            "model": ["m", "m"],
            "scenario_id": ["s1", "s1"],
            "variable": ["income_tax", "federal_refundable_credits"],
            "prediction": [1.0, None],
            "explanation": ["Wages drive tax.", "Income is too high."],
            "error": [None, "Missing predictions after repair: foo"],
        }
    ).to_csv(path, index=False)

    assert chunk_is_complete(path, scenario_program_counts=[2])


def test_chunk_is_complete_rejects_provider_errors(tmp_path):
    path = tmp_path / "chunk.csv"
    pd.DataFrame(
        {
            "model": ["m", "m"],
            "scenario_id": ["s1", "s1"],
            "variable": ["income_tax", "federal_refundable_credits"],
            "prediction": [1.0, None],
            "explanation": ["Wages drive tax.", ""],
            "error": [None, "RequestWallTimeoutError: Provider request timed out"],
        }
    ).to_csv(path, index=False)

    assert not chunk_is_complete(path, scenario_program_counts=[2])


def test_chunk_is_complete_keeps_missing_explanations_as_benchmark_outcomes(
    tmp_path,
):
    path = tmp_path / "chunk.csv"
    pd.DataFrame(
        {
            "model": ["m", "m"],
            "scenario_id": ["s1", "s1"],
            "variable": ["income_tax", "federal_refundable_credits"],
            "prediction": [1.0, 2.0],
            "explanation": ["Wages drive tax.", ""],
            "error": [None, None],
        }
    ).to_csv(path, index=False)

    assert chunk_is_complete(path, scenario_program_counts=[2])
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

    def fake_run(cmd, check, env):
        calls.append((cmd, check, env))

    monkeypatch.setattr("policybench.chunked_eval.subprocess.run", fake_run)

    run_chunk(
        country="us",
        model="gpt-5.5",
        program_set="headline",
        scenario_manifest=tmp_path / "scenarios.csv",
        scenario_count=100,
        output=tmp_path / "chunk.csv",
        start=20,
        end=30,
        include_explanations=True,
        single_output=False,
    )

    cmd, check, env = calls[0]
    assert check is True
    # Without a worker environment the chunk inherits this process's.
    assert env is None
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

    def fake_run(cmd, check, env):
        calls.append((cmd, check))

    monkeypatch.setattr("policybench.chunked_eval.subprocess.run", fake_run)

    run_chunk(
        country="us",
        model="gpt-5.5",
        program_set="headline",
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


def test_run_chunk_with_retries_keeps_row_level_failures(monkeypatch, tmp_path):
    output = tmp_path / "chunk.csv"
    calls = []

    def fake_run_chunk(**kwargs):
        calls.append(kwargs)
        pd.DataFrame(
            {
                "model": ["gpt-5.5"],
                "scenario_id": ["s1"],
                "variable": ["income_tax"],
                "prediction": [None],
                "explanation": [""],
                "error": ["Missing prediction"],
            }
        ).to_csv(output, index=False)

    monkeypatch.setattr("policybench.chunked_eval.run_chunk", fake_run_chunk)

    run_chunk_with_retries(
        country="us",
        model="gpt-5.5",
        program_set="headline",
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

    assert len(calls) == 1
    assert chunk_is_complete(output, scenario_program_counts=[1])


def test_run_chunk_with_retries_retries_provider_failures(monkeypatch, tmp_path):
    output = tmp_path / "chunk.csv"
    calls = []

    def fake_run_chunk(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            pd.DataFrame(
                {
                    "model": ["gpt-5.5"],
                    "scenario_id": ["s1"],
                    "variable": ["income_tax"],
                    "prediction": [None],
                    "explanation": [""],
                    "error": ["RateLimitError: provider overloaded"],
                }
            ).to_csv(output, index=False)
            return
        pd.DataFrame(
            {
                "model": ["gpt-5.5"],
                "scenario_id": ["s1"],
                "variable": ["income_tax"],
                "prediction": [123.0],
                "explanation": ["Wage income drives tax. value = 123"],
                "error": [None],
            }
        ).to_csv(output, index=False)

    monkeypatch.setattr("policybench.chunked_eval.run_chunk", fake_run_chunk)

    run_chunk_with_retries(
        country="us",
        model="gpt-5.5",
        program_set="headline",
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


def test_chunk_and_model_merges_preserve_call_ledgers(tmp_path):
    chunks = [tmp_path / "chunk0.csv", tmp_path / "chunk1.csv"]
    for index, path in enumerate(chunks):
        pd.DataFrame(
            {
                "model": ["m"],
                "scenario_id": [f"s{index}"],
                "variable": ["income_tax"],
                "prediction": [float(index)],
            }
        ).to_csv(path, index=False)
        upsert_spend_ledger(
            spend_ledger_path(path),
            [
                {
                    "call_key": f"sync:{index}",
                    "phase": "repair" if index else "initial",
                    "status": "ok",
                    "total_cost_usd": 0.1,
                }
            ],
        )

    model_output = tmp_path / "by_model" / "m.csv"
    merge_chunks(model="m", chunk_paths=chunks, output_path=model_output)
    model_ledger = read_spend_ledger(spend_ledger_path(model_output))
    assert {record["call_key"] for record in model_ledger} == {"sync:0", "sync:1"}

    upsert_spend_ledger(
        spend_ledger_path(model_output),
        [
            {
                "call_key": "sync:stale",
                "phase": "initial",
                "status": "ok",
                "total_cost_usd": 99.0,
            }
        ],
    )
    merge_chunks(model="m", chunk_paths=chunks, output_path=model_output)
    model_ledger = read_spend_ledger(spend_ledger_path(model_output))
    assert {record["call_key"] for record in model_ledger} == {"sync:0", "sync:1"}

    combined_output = tmp_path / "predictions.csv"
    merge_model_outputs(
        model_output_paths=[model_output],
        output_path=combined_output,
    )
    combined_ledger = read_spend_ledger(spend_ledger_path(combined_output))
    assert combined_ledger == model_ledger


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
        models=["gpt-5.5", "grok-4.3"],
        program_set="headline",
        chunk_size=10,
        parallel=2,
        model_parallel=1,
        chunk_attempts=1,
        include_explanations=True,
        single_output=False,
    )

    assert [call["model"] for call in calls] == ["gpt-5.5", "grok-4.3"]
    assert output == tmp_path / "predictions" / "predictions.csv"
    assert pd.read_csv(output)["model"].tolist() == ["gpt-5.5", "grok-4.3"]


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
        models=["gpt-5.5", "grok-4.3"],
        program_set="headline",
        chunk_size=10,
        parallel=2,
        model_parallel=2,
        chunk_attempts=3,
        include_explanations=True,
        single_output=False,
    )

    assert sorted(call["model"] for call in calls) == [
        "gpt-5.5",
        "grok-4.3",
    ]
    assert {call["chunk_attempts"] for call in calls} == {3}
    assert output == tmp_path / "predictions" / "predictions.csv"


def test_run_model_chunks_rejects_parallel_claude(tmp_path):
    with pytest.raises(ValueError, match="must run with --parallel 1"):
        run_model_chunks(
            scenario_manifest=tmp_path / "missing.csv",
            output_dir=tmp_path / "predictions",
            country="us",
            model="claude-opus-4.7",
            program_set="headline",
            chunk_size=10,
            parallel=2,
            chunk_attempts=1,
            include_explanations=True,
            single_output=False,
        )


def test_run_chunked_eval_rejects_model_parallel_claude(tmp_path):
    with pytest.raises(ValueError, match="--model-parallel 1"):
        run_chunked_eval(
            scenario_manifest=tmp_path / "missing.csv",
            output_dir=tmp_path / "predictions",
            country="us",
            models=["gpt-5.5", "claude-opus-4.7"],
            program_set="headline",
            chunk_size=10,
            parallel=1,
            model_parallel=2,
            chunk_attempts=1,
            include_explanations=True,
            single_output=False,
        )


# -- PolicyEngine provenance computed once per invocation ---------------------


def test_run_chunk_passes_the_worker_environment(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        "policybench.chunked_eval.subprocess.run",
        lambda cmd, check, env: calls.append(env),
    )

    run_chunk(
        country="us",
        model="gpt-5.5",
        program_set="headline",
        scenario_manifest=tmp_path / "scenarios.csv",
        scenario_count=1,
        output=tmp_path / "chunk.csv",
        start=0,
        end=1,
        include_explanations=True,
        single_output=False,
        env={"A": "1"},
    )

    assert calls == [{"A": "1"}]


def test_handoff_writes_once_and_points_every_worker_at_its_file(
    provenance_writer, tmp_path
):
    handoff = PolicyEngineProvenanceHandoff(tmp_path / "out")
    envs = []
    lock = threading.Lock()

    def take():
        env = handoff.worker_env({"us"})
        with lock:
            envs.append(env)

    threads = [threading.Thread(target=take) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    path = (tmp_path / "out" / POLICYENGINE_PROVENANCE_FILENAME).resolve()
    assert len(provenance_writer) == 1
    (call,) = provenance_writer
    assert call["python"] == sys.executable
    assert call["path"] == path
    assert call["countries"] == ["us"]
    assert POLICYENGINE_PROVENANCE_ENV not in call["env"]
    assert len(envs) == 8
    assert {env[POLICYENGINE_PROVENANCE_ENV] for env in envs} == {str(path)}
    assert handoff.bundles == {"us": MOCK_BUNDLES["us"]}


def test_handoff_replaces_an_inherited_provenance_file(
    provenance_writer, tmp_path, monkeypatch
):
    monkeypatch.setenv(POLICYENGINE_PROVENANCE_ENV, str(tmp_path / "elsewhere.json"))
    monkeypatch.setenv("POLICYBENCH_TEST_MARKER", "kept")
    handoff = PolicyEngineProvenanceHandoff(tmp_path)

    env = handoff.worker_env(["US"])

    assert env[POLICYENGINE_PROVENANCE_ENV] == str(handoff.path)
    assert env["POLICYBENCH_TEST_MARKER"] == "kept"
    assert provenance_writer[0]["countries"] == ["us"]


@pytest.mark.parametrize(
    "writer_outcome",
    ["fails", "leaves no file", "leaves another country", "leaves bad json"],
)
def test_handoff_leaves_workers_to_compute_when_the_write_fails(
    tmp_path, monkeypatch, writer_outcome
):
    calls = []

    def failing_writer(python, path, countries, env, **kwargs):
        calls.append(countries)
        path = Path(path)
        if writer_outcome == "leaves another country":
            path.write_text(json.dumps({"policyengine_bundles": {"uk": {}}}))
        elif writer_outcome == "leaves bad json":
            path.write_text("{not json")
        return writer_outcome != "fails"

    monkeypatch.setattr(
        "policybench.chunked_eval.run_policyengine_provenance_writer", failing_writer
    )
    monkeypatch.setenv(POLICYENGINE_PROVENANCE_ENV, str(tmp_path / "inherited.json"))
    handoff = PolicyEngineProvenanceHandoff(tmp_path)

    first = handoff.worker_env({"us"})
    second = handoff.worker_env({"us"})

    assert POLICYENGINE_PROVENANCE_ENV not in first
    assert POLICYENGINE_PROVENANCE_ENV not in second
    assert calls == [["us"]], "a failed handoff is not retried per chunk"
    assert handoff.bundles is None


def test_handoff_skips_mixed_country_chunks(provenance_writer, tmp_path):
    handoff = PolicyEngineProvenanceHandoff(tmp_path)

    env = handoff.worker_env({"us", "uk"})

    assert provenance_writer == []
    assert POLICYENGINE_PROVENANCE_ENV not in env


def test_handoff_gives_the_file_only_to_its_own_countries(provenance_writer, tmp_path):
    handoff = PolicyEngineProvenanceHandoff(tmp_path)

    us_env = handoff.worker_env({"us"})
    uk_env = handoff.worker_env({"uk"})

    assert len(provenance_writer) == 1
    assert us_env[POLICYENGINE_PROVENANCE_ENV] == str(handoff.path)
    assert POLICYENGINE_PROVENANCE_ENV not in uk_env


def test_handoff_does_not_delete_a_concurrent_invocations_file(
    provenance_writer, tmp_path
):
    """Several invocations can share one output dir, so an earlier file stays
    in place until the writer atomically replaces it."""
    path = tmp_path / POLICYENGINE_PROVENANCE_FILENAME
    path.write_text("written by another invocation")

    PolicyEngineProvenanceHandoff(tmp_path).worker_env({"us"})

    assert provenance_writer[0]["existing"] == "written by another invocation"


@pytest.mark.parametrize("parallel", [1, 3])
def test_run_model_chunks_hands_every_chunk_the_provenance_file(
    provenance_writer, tmp_path, monkeypatch, parallel
):
    scenarios = _probe_scenarios(5)
    manifest = _write_manifest(tmp_path / "scenarios.csv", scenarios)
    calls = []
    monkeypatch.setattr(
        "policybench.chunked_eval.run_chunk", _complete_chunk_writer(scenarios, calls)
    )

    output = run_model_chunks(
        scenario_manifest=manifest,
        output_dir=tmp_path / "out",
        country="us",
        model="gpt-5.5",
        chunk_size=2,
        parallel=parallel,
    )

    path = str((tmp_path / "out" / POLICYENGINE_PROVENANCE_FILENAME).resolve())
    assert output.exists()
    assert len(provenance_writer) == 1
    assert sorted(call["start"] for call in calls) == [0, 2, 4]
    assert {call["env"][POLICYENGINE_PROVENANCE_ENV] for call in calls} == {path}


def test_run_model_chunks_skips_provenance_when_no_chunk_is_pending(
    provenance_writer, tmp_path, monkeypatch
):
    """A pass that only merges finished chunks never imports PolicyEngine."""
    scenarios = _probe_scenarios(3)
    manifest = _write_manifest(tmp_path / "scenarios.csv", scenarios)
    calls = []
    fake_run_chunk = _complete_chunk_writer(scenarios, calls)
    monkeypatch.setattr("policybench.chunked_eval.run_chunk", fake_run_chunk)
    kwargs = {
        "scenario_manifest": manifest,
        "output_dir": tmp_path / "out",
        "country": "us",
        "model": "gpt-5.5",
        "chunk_size": 2,
    }
    run_model_chunks(**kwargs)
    provenance_writer.clear()
    calls.clear()

    output = run_model_chunks(**kwargs)

    assert output.exists()
    assert calls == []
    assert provenance_writer == []


@pytest.mark.parametrize("model_parallel", [1, 2])
def test_run_chunked_eval_writes_provenance_once_for_all_models(
    provenance_writer, tmp_path, monkeypatch, model_parallel
):
    scenarios = _probe_scenarios(3)
    manifest = _write_manifest(tmp_path / "scenarios.csv", scenarios)
    calls = []
    monkeypatch.setattr(
        "policybench.chunked_eval.run_chunk", _complete_chunk_writer(scenarios, calls)
    )

    output = run_chunked_eval(
        scenario_manifest=manifest,
        output_dir=tmp_path / "out",
        country="us",
        models=["gpt-5.5", "grok-4.3"],
        chunk_size=1,
        parallel=2,
        model_parallel=model_parallel,
    )

    path = (tmp_path / "out" / POLICYENGINE_PROVENANCE_FILENAME).resolve()
    assert sorted(pd.read_csv(output)["model"].unique()) == ["gpt-5.5", "grok-4.3"]
    assert [call["path"] for call in provenance_writer] == [path]
    assert len(calls) == 6
    assert {call["env"][POLICYENGINE_PROVENANCE_ENV] for call in calls} == {str(path)}


# Every request sequence of length 1-3 over these country sets, for every
# writer outcome, with and without an inherited file: the handoff's
# invariants are checked exhaustively rather than sampled.
HANDOFF_REQUESTS = [("us",), ("uk",), ("us", "uk"), ("US",)]
HANDOFF_SEQUENCES = [
    sequence
    for length in (1, 2, 3)
    for sequence in itertools.product(HANDOFF_REQUESTS, repeat=length)
]


@pytest.mark.parametrize("inherited", [False, True])
@pytest.mark.parametrize("outcome", ["written", "writer fails", "unreadable"])
def test_handoff_invariants_hold_for_every_request_sequence(
    tmp_path, monkeypatch, outcome, inherited
):
    """For any sequence of requests: the writer runs at most once, and only
    for a single-country first request; a worker gets the file exactly when
    it was written and read back for that worker's own countries; and the
    worker environment is otherwise this process's, minus any inherited
    provenance file."""
    calls = []

    def writer(python, path, countries, env, **kwargs):
        calls.append(list(countries))
        if outcome == "written":
            bundles = {country: MOCK_BUNDLES[country] for country in countries}
            Path(path).write_text(json.dumps({"policyengine_bundles": bundles}))
        elif outcome == "unreadable":
            Path(path).write_text("{not json")
        return outcome != "writer fails"

    monkeypatch.setattr(
        "policybench.chunked_eval.run_policyengine_provenance_writer", writer
    )
    if inherited:
        monkeypatch.setenv(POLICYENGINE_PROVENANCE_ENV, str(tmp_path / "old.json"))
    else:
        monkeypatch.delenv(POLICYENGINE_PROVENANCE_ENV, raising=False)
    base = {
        key: value
        for key, value in os.environ.items()
        if key != POLICYENGINE_PROVENANCE_ENV
    }

    for index, sequence in enumerate(HANDOFF_SEQUENCES):
        calls.clear()
        handoff = PolicyEngineProvenanceHandoff(tmp_path / f"out{index}")
        handoff.path.parent.mkdir()
        first = sorted({country.lower() for country in sequence[0]})
        envs = [handoff.worker_env(set(request)) for request in sequence]

        assert calls == ([first] if len(first) == 1 else []), sequence
        written = len(first) == 1 and outcome == "written"
        for request, env in zip(sequence, envs):
            wanted = sorted({country.lower() for country in request})
            handed = written and wanted == first
            assert env.get(POLICYENGINE_PROVENANCE_ENV) == (
                str(handoff.path) if handed else None
            ), (sequence, request)
            assert {
                key: value
                for key, value in env.items()
                if key != POLICYENGINE_PROVENANCE_ENV
            } == base


def test_output_dir_scanners_ignore_the_provenance_file(tmp_path, monkeypatch):
    """Exporters, reparsing and the run store read the same thing from a
    chunked output dir with and without policyengine_provenance.json, and
    leave the file alone."""
    from policybench.full_run_export import load_predictions
    from policybench.reparse_predictions import reparse_country_run
    from policybench.runstore import RunStore, import_run_dir

    scenarios = _probe_scenarios(2)
    manifest = _write_manifest(tmp_path / "scenarios.csv", scenarios)
    calls = []
    monkeypatch.setattr(
        "policybench.chunked_eval.run_chunk", _complete_chunk_writer(scenarios, calls)
    )
    with_file = tmp_path / "with_file"
    run_chunked_eval(
        scenario_manifest=manifest,
        output_dir=with_file,
        country="us",
        models=["gpt-5.5", "grok-4.3"],
        chunk_size=1,
    )
    provenance = with_file / POLICYENGINE_PROVENANCE_FILENAME
    provenance_bytes = provenance.read_bytes()
    without_file = tmp_path / "without_file"
    shutil.copytree(with_file, without_file)
    (without_file / POLICYENGINE_PROVENANCE_FILENAME).unlink()

    results = {}
    for directory in (with_file, without_file):
        predictions = load_predictions(directory)
        reparsed = reparse_country_run(directory)
        run_id, db_path = import_run_dir(
            directory, db_path=tmp_path / f"{directory.name}.db", run_id="probe"
        )
        with RunStore(db_path) as store:
            counts = store.status_counts(run_id)
        results[directory.name] = (
            predictions,
            {str(Path(path).relative_to(directory)): n for path, n in reparsed.items()},
            counts,
        )

    pd.testing.assert_frame_equal(results["with_file"][0], results["without_file"][0])
    assert results["with_file"][1:] == results["without_file"][1:]
    assert provenance.read_bytes() == provenance_bytes


# -- end to end: real chunk workers, real provenance writer, fake LLM ---------

PROBE_MODELS = ["claude-sonnet-4.6", "claude-haiku-4.5"]


def _run_probed(cmd: list[str], env: dict, cwd: Path) -> None:
    run = subprocess.run(
        cmd, env=env, cwd=cwd, capture_output=True, text=True, timeout=900
    )
    assert run.returncode == 0, run.stdout + run.stderr


def _assert_policyengine_stayed_in_the_writer(records, *, orchestrator, workers):
    orchestrators = [r for r in records if orchestrator in r["argv"]]
    writers = [r for r in records if r["argv"][0] == "-c"]
    chunk_workers = [r for r in records if "eval-no-tools" in r["argv"]]
    assert len(orchestrators) == 1 and orchestrators[0]["at_exit"] == []
    # One writer for the whole invocation, and it did load PolicyEngine,
    # which also shows the probe detects it.
    assert len(writers) == 1 and "policyengine_us" in writers[0]["at_exit"]
    assert len(chunk_workers) == workers
    for worker in chunk_workers:
        assert worker["requests"], "the worker never reached its LLM request"
        assert all(loaded == [] for loaded in worker["requests"])
        assert worker["at_exit"] == []


def test_chunked_run_keeps_policyengine_out_of_chunk_workers(tmp_path, monkeypatch):
    """End to end through `eval-no-tools-chunked`: two models, two one-scenario
    chunks each. Only the one-shot writer imports PolicyEngine, and every
    chunk sidecar is byte-identical to the one a chunk worker computing its
    own provenance, as all did before the handoff, writes."""
    scenarios = _probe_scenarios(2)
    manifest = _write_manifest(tmp_path / "scenarios.csv", scenarios)
    probed_env, probe_dir = probe_environment(tmp_path)

    # The pre-handoff chunk worker: run_chunk's exact command for the first
    # chunk, started with no provenance file so it computes the bundles.
    baseline_output = tmp_path / "baseline" / "s0000_0001.csv"
    commands = []
    with monkeypatch.context() as patch:
        patch.setattr(
            "policybench.chunked_eval.subprocess.run",
            lambda cmd, **kwargs: commands.append(cmd),
        )
        run_chunk(
            country="us",
            model=PROBE_MODELS[0],
            program_set=DEFAULT_PROGRAM_SET,
            scenario_manifest=manifest,
            scenario_count=len(scenarios),
            output=baseline_output,
            start=0,
            end=1,
            include_explanations=True,
            single_output=False,
        )
    (baseline_command,) = commands
    baseline_log = tmp_path / "baseline.log"
    with baseline_log.open("w") as log:
        baseline = subprocess.Popen(
            baseline_command,
            env=probed_env,
            cwd=tmp_path,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        output_dir = tmp_path / "chunked"
        model_flags = [flag for model in PROBE_MODELS for flag in ("--model", model)]
        _run_probed(
            [
                sys.executable,
                "-m",
                "policybench.cli",
                "eval-no-tools-chunked",
                "--scenario-manifest",
                str(manifest),
                "--output-dir",
                str(output_dir),
                "--country",
                "us",
                *model_flags,
                "--chunk-size",
                "1",
            ],
            probed_env,
            tmp_path,
        )
        assert baseline.wait(timeout=900) == 0, baseline_log.read_text()

    records = probe_records(probe_dir)
    (baseline_record,) = [r for r in records if str(baseline_output) in r["argv"]]
    # Positive control: a worker that computes provenance loads PolicyEngine
    # before its first request, and the probe sees it.
    assert "policyengine_us" in baseline_record["requests"][0]
    _assert_policyengine_stayed_in_the_writer(
        [r for r in records if r is not baseline_record],
        orchestrator="eval-no-tools-chunked",
        workers=4,
    )

    before = Path(f"{baseline_output}.meta.json").read_bytes()
    handed = (
        output_dir / "chunks" / PROBE_MODELS[0] / "s0000_0001.csv.meta.json"
    ).read_bytes()
    assert handed == before
    provenance = json.loads((output_dir / POLICYENGINE_PROVENANCE_FILENAME).read_text())
    expected_bundles = json.loads(before)["policyengine_bundles"]
    assert provenance["policyengine_bundles"] == expected_bundles
    sidecars = sorted((output_dir / "chunks").glob("*/*.meta.json"))
    assert len(sidecars) == 4
    for sidecar in sidecars:
        bundles = json.loads(sidecar.read_text())["policyengine_bundles"]
        assert bundles == expected_bundles
    predictions = pd.read_csv(output_dir / "predictions.csv")
    assert sorted(predictions["model"].unique()) == sorted(PROBE_MODELS)
    assert predictions["prediction"].notna().all()


def test_retry_round_keeps_policyengine_out_of_chunk_workers(tmp_path):
    """End to end through `retry-failed-responses`: two models share one
    provenance file at the round's root."""
    scenarios = _probe_scenarios(2)
    manifest = _write_manifest(tmp_path / "scenarios.csv", scenarios)
    programs = get_programs("us", DEFAULT_PROGRAM_SET)
    source = tmp_path / "predictions.csv"
    pd.DataFrame(
        [
            {
                "model": model,
                "scenario_id": scenario.id,
                "variable": variable,
                "prediction": None,
                "explanation": "",
                "error": "Missing predictions after repair",
            }
            for model in PROBE_MODELS
            for scenario in scenarios
            for variable in expand_programs_for_scenario(programs, scenario)
        ]
    ).to_csv(source, index=False)
    probed_env, probe_dir = probe_environment(tmp_path)
    retry_dir = tmp_path / "retry"

    _run_probed(
        [
            sys.executable,
            "-m",
            "policybench.cli",
            "retry-failed-responses",
            "--country",
            "us",
            "--source-predictions",
            str(source),
            "--scenario-manifest",
            str(manifest),
            "--output-dir",
            str(retry_dir),
            "--chunk-size",
            "1",
        ],
        probed_env,
        tmp_path,
    )

    _assert_policyengine_stayed_in_the_writer(
        probe_records(probe_dir),
        orchestrator="retry-failed-responses",
        workers=4,
    )
    provenance = json.loads((retry_dir / POLICYENGINE_PROVENANCE_FILENAME).read_text())
    sidecars = sorted((retry_dir / "model_runs").glob("*/chunks/*/*.meta.json"))
    assert len(sidecars) == 4
    for sidecar in sidecars:
        bundles = json.loads(sidecar.read_text())["policyengine_bundles"]
        assert bundles == provenance["policyengine_bundles"]
    assert not list(
        (retry_dir / "model_runs").glob(f"*/{POLICYENGINE_PROVENANCE_FILENAME}")
    )
    accepted = pd.read_csv(retry_dir / "accepted_retry_units.csv")
    assert len(accepted) == 4
