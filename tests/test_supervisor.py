"""Supervisor unit tests — no live subprocesses or API calls.

Workers are stubbed with instantly-exiting processes; scenario CSVs are
synthesized by the stub so the queue, resume, budget-governor, adaptive-
concurrency, and combine behaviors are exercised on real files.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from policybench.config import MODELS
from policybench.spend_ledger import spend_ledger_path, upsert_spend_ledger
from policybench.supervisor import (
    ADAPTIVE_WINDOW,
    BUDGET_STOP_FRACTION,
    DEFAULT_MAX_WORKERS,
    TREATMENT_FINGERPRINT_VERSION,
    ScenarioResult,
    Supervisor,
)

N_SCENARIOS = 6


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    path = tmp_path / "scenarios.csv"
    pd.DataFrame(
        {"scenario_id": [f"scenario_{i:03d}" for i in range(N_SCENARIOS)]}
    ).to_csv(path, index=False)
    return path


def make_supervisor(manifest: Path, tmp_path: Path, **kwargs) -> Supervisor:
    return Supervisor(
        model="test-model",
        manifest=manifest,
        run_dir=tmp_path / "run",
        **kwargs,
    )


def stub_worker(
    supervisor: Supervisor,
    monkeypatch,
    cost_per_scenario: float = 0.1,
    fail_indices: set[int] | None = None,
    timeout_indices: set[int] | None = None,
    budget_escalation_counts: dict[int, int] | None = None,
):
    """Replace _spawn with a no-op process and synthesize the scenario CSV."""
    fail_indices = fail_indices or set()
    timeout_indices = timeout_indices or set()
    budget_escalation_counts = budget_escalation_counts or {}

    def fake_spawn(index: int):
        if index not in fail_indices:
            out = supervisor.scenario_csv(index)
            out.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                {
                    "scenario_id": [supervisor.scenario_ids[index]] * 2,
                    "prediction": [1.0, 2.0],
                    "total_cost_usd": [cost_per_scenario / 2] * 2,
                }
            ).to_csv(out, index=False)
            escalation_count = budget_escalation_counts.get(index, 0)
            if escalation_count:
                upsert_spend_ledger(
                    spend_ledger_path(out),
                    [
                        {
                            "call_key": f"sync:{index}:{escalation_index}",
                            "escalated_from_budget_tokens": 256 * 2**escalation_index,
                            "completion_budget_tokens": 512 * 2**escalation_index,
                        }
                        for escalation_index in range(escalation_count)
                    ],
                )
        if index in timeout_indices:
            log = supervisor.scenario_csv(index).with_suffix(".log")
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text("litellm.Timeout: Connection timed out")
        return subprocess.Popen(["true"])

    monkeypatch.setattr(supervisor, "_spawn", fake_spawn)


def test_happy_path_completes_all_and_combines(manifest, tmp_path, monkeypatch):
    supervisor = make_supervisor(manifest, tmp_path)
    stub_worker(supervisor, monkeypatch)
    state = supervisor.run(poll_seconds=0.01)
    assert len(state.completed) == N_SCENARIOS
    assert state.stopped_reason is None
    combined = pd.read_csv(supervisor.run_dir / "predictions.csv")
    assert combined.scenario_id.nunique() == N_SCENARIOS
    heartbeat = json.loads((supervisor.run_dir / "run_state.json").read_text())
    assert heartbeat["completed"] == N_SCENARIOS
    assert heartbeat["treatment_fingerprint"] == {
        "fingerprint_version": TREATMENT_FINGERPRINT_VERSION,
        "model_id": "test-model",
        "answer_contract": "tool",
        "tool_choice_mode": "forced",
        "chunk_size": None,
        "prompt_contract_version": "2026-08-09-v2-scoring-contract",
        "completion_budget_ceiling": 128000,
    }


def test_fingerprint_records_the_contract_override(manifest, tmp_path):
    """A sensitivity run that declares the tool on a JSON-contract model must
    fingerprint the contract it actually sent, so a resume under the default
    contract is refused rather than spliced in."""
    supervisor = make_supervisor(
        manifest,
        tmp_path,
        env={
            "POLICYBENCH_CONTRACT_OVERRIDE": "json",
            "POLICYBENCH_TOOL_CHOICE": "auto",
        },
    )
    assert supervisor.treatment_fingerprint["answer_contract"] == "json"
    assert supervisor.treatment_fingerprint["tool_choice_mode"] is None


def test_budget_escalation_counts_land_in_run_state(
    manifest,
    tmp_path,
    monkeypatch,
):
    supervisor = make_supervisor(manifest, tmp_path)
    stub_worker(
        supervisor,
        monkeypatch,
        budget_escalation_counts={0: 2, 3: 1},
    )

    state = supervisor.run(poll_seconds=0.01)

    assert state.budget_escalation_count == 3
    heartbeat = json.loads((supervisor.run_dir / "run_state.json").read_text())
    assert heartbeat["budget_escalation_count"] == 3

    resumed = make_supervisor(manifest, tmp_path)
    resumed_state = resumed.run(poll_seconds=0)
    assert resumed_state.budget_escalation_count == 3


def test_resume_skips_completed_scenarios(manifest, tmp_path, monkeypatch):
    initial = make_supervisor(manifest, tmp_path)
    stub_worker(initial, monkeypatch)
    for index in (0, 1):
        initial._spawn(index).wait()
    initial.write_heartbeat()

    supervisor = make_supervisor(manifest, tmp_path)
    stub_worker(supervisor, monkeypatch)
    spawned: list[int] = []
    original = supervisor._spawn

    def tracking_spawn(index: int):
        spawned.append(index)
        return original(index)

    monkeypatch.setattr(supervisor, "_spawn", tracking_spawn)
    state = supervisor.run(poll_seconds=0.01)
    assert 0 not in spawned and 1 not in spawned
    assert sorted(spawned) == [2, 3, 4, 5]
    assert len(state.completed) == N_SCENARIOS


def test_resume_rejects_changed_model_id(manifest, tmp_path, monkeypatch):
    monkeypatch.setitem(MODELS, "test-model", "provider/model-a")
    initial = make_supervisor(manifest, tmp_path)
    initial.write_heartbeat()

    monkeypatch.setitem(MODELS, "test-model", "provider/model-b")
    resumed = make_supervisor(manifest, tmp_path)
    monkeypatch.setattr(
        resumed,
        "_spawn",
        lambda _index: pytest.fail("mismatched resume dispatched a worker"),
    )

    with pytest.raises(ValueError, match="model_id"):
        resumed.run(poll_seconds=0.01)


def test_resume_rejects_unversioned_treatment_fingerprint(
    manifest, tmp_path, monkeypatch
):
    initial = make_supervisor(manifest, tmp_path)
    initial.write_heartbeat()
    state_path = initial.run_dir / "run_state.json"
    state = json.loads(state_path.read_text())
    del state["treatment_fingerprint"]["fingerprint_version"]
    state_path.write_text(json.dumps(state))

    resumed = make_supervisor(manifest, tmp_path)
    monkeypatch.setattr(
        resumed,
        "_spawn",
        lambda _index: pytest.fail("unversioned resume dispatched a worker"),
    )

    with pytest.raises(ValueError, match="fingerprint_version"):
        resumed.run(poll_seconds=0.01)


def test_resume_rejects_changed_tool_choice(manifest, tmp_path, monkeypatch):
    initial = make_supervisor(
        manifest,
        tmp_path,
        env={"POLICYBENCH_TOOL_CHOICE": "forced"},
    )
    initial.write_heartbeat()

    resumed = make_supervisor(
        manifest,
        tmp_path,
        env={"POLICYBENCH_TOOL_CHOICE": "auto"},
    )
    monkeypatch.setattr(
        resumed,
        "_spawn",
        lambda _index: pytest.fail("mismatched resume dispatched a worker"),
    )

    with pytest.raises(ValueError, match="tool_choice_mode"):
        resumed.run(poll_seconds=0.01)


def test_resume_rejects_scenario_outputs_without_run_state(
    manifest,
    tmp_path,
    monkeypatch,
):
    supervisor = make_supervisor(manifest, tmp_path)
    stub_worker(supervisor, monkeypatch)
    supervisor._spawn(0).wait()

    resumed = make_supervisor(manifest, tmp_path)
    monkeypatch.setattr(
        resumed,
        "_spawn",
        lambda _index: pytest.fail("unvalidated resume dispatched a worker"),
    )

    with pytest.raises(ValueError, match="run_state.json"):
        resumed.run(poll_seconds=0.01)


def test_resume_rejects_orphan_spend_ledger_without_run_state(
    manifest, tmp_path, monkeypatch
):
    supervisor = make_supervisor(manifest, tmp_path)
    ledger_path = spend_ledger_path(supervisor.scenario_csv(0))
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text(
        json.dumps(
            {
                "call_key": "sync:stale",
                "status": "ok",
                "total_cost_usd": 1.0,
            }
        )
        + "\n"
    )
    monkeypatch.setattr(
        supervisor,
        "_spawn",
        lambda _index: pytest.fail("orphan ledger dispatched a worker"),
    )

    with pytest.raises(ValueError, match="run_state.json"):
        supervisor.run(poll_seconds=0.01)


def test_failed_scenarios_retry_up_to_max_rounds(manifest, tmp_path, monkeypatch):
    supervisor = make_supervisor(manifest, tmp_path, max_rounds=3)
    stub_worker(supervisor, monkeypatch, fail_indices={4})
    state = supervisor.run(poll_seconds=0.01)
    assert len(state.completed) == N_SCENARIOS - 1
    assert "scenario_004" in state.failed
    assert state.failed["scenario_004"] == 3
    assert "incomplete" in state.stopped_reason


def test_budget_governor_stops_dispatching(manifest, tmp_path, monkeypatch):
    supervisor = make_supervisor(manifest, tmp_path, budget_usd=0.3, max_workers=1)
    stub_worker(supervisor, monkeypatch, cost_per_scenario=0.1)
    state = supervisor.run(poll_seconds=0.01)
    assert state.stopped_reason and state.stopped_reason.startswith("budget")
    assert len(state.completed) < N_SCENARIOS
    assert state.spent_usd >= 0.3 * BUDGET_STOP_FRACTION


def test_projection_warning_from_card_estimate(manifest, tmp_path, monkeypatch):
    supervisor = make_supervisor(manifest, tmp_path, budget_usd=100.0)
    monkeypatch.setattr(
        "policybench.supervisor.card_for",
        lambda _mid: type("Card", (), {"expected_cost_per_scenario_usd": 50.0})(),
    )
    assert supervisor.budget_allows_dispatch()
    assert "projected $300.00 exceeds budget $100.00" in supervisor.projection_warning


def test_adaptive_backoff_and_recovery(manifest, tmp_path):
    supervisor = make_supervisor(manifest, tmp_path, max_workers=6)
    supervisor.state.workers = 4
    for _ in range(ADAPTIVE_WINDOW):
        supervisor._record(ScenarioResult("s", 0, ok=False, timed_out=True))
    assert supervisor.state.workers < 4
    supervisor._recent.clear()
    supervisor.state.workers = 4
    for _ in range(ADAPTIVE_WINDOW):
        supervisor._record(ScenarioResult("s", 0, ok=True))
    assert supervisor.state.workers == 5


def test_default_worker_cap(manifest, tmp_path):
    supervisor = make_supervisor(manifest, tmp_path, max_workers=12)
    assert supervisor.state.workers == DEFAULT_MAX_WORKERS
    assert supervisor.max_workers == 12


def test_spend_prefers_credits_delta_over_disk(manifest, tmp_path, monkeypatch):
    usage = {"value": 100.0}
    monkeypatch.setattr(Supervisor, "_credits_usage", lambda self: usage["value"])
    supervisor = make_supervisor(manifest, tmp_path)
    assert supervisor._credits_baseline == 100.0
    # Replayed scenarios put stale cost on disk; the meter must ignore it.
    stub = tmp_path / "run" / "scenarios"
    stub.mkdir(parents=True)
    pd.DataFrame(
        {"scenario_id": ["scenario_000"], "prediction": [1.0], "total_cost_usd": [9.9]}
    ).to_csv(stub / "scenario_000.csv", index=False)
    usage["value"] = 100.5
    assert supervisor._spent() == pytest.approx(0.5)


def test_openrouter_resume_keeps_prior_spend_offset(manifest, tmp_path, monkeypatch):
    usage = {"value": 100.0}
    monkeypatch.setitem(MODELS, "test-model", "openrouter/example/model")
    monkeypatch.setattr(Supervisor, "_credits_usage", lambda self: usage["value"])
    initial = make_supervisor(manifest, tmp_path, max_rounds=0)
    initial.state.spent_usd = 1.25
    initial.write_heartbeat()

    usage["value"] = 101.0
    resumed = make_supervisor(manifest, tmp_path, max_rounds=0)
    state = resumed.run(poll_seconds=0)
    assert state.spent_usd == pytest.approx(1.25)

    usage["value"] = 101.5
    resumed._credits_checked_at = float("-inf")
    assert resumed._spent() == pytest.approx(1.75)


def test_spend_falls_back_to_disk_without_credits(manifest, tmp_path, monkeypatch):
    monkeypatch.setattr(Supervisor, "_credits_usage", lambda self: None)
    supervisor = make_supervisor(manifest, tmp_path)
    stub = tmp_path / "run" / "scenarios"
    stub.mkdir(parents=True)
    pd.DataFrame(
        {"scenario_id": ["scenario_000"], "prediction": [1.0], "total_cost_usd": [0.7]}
    ).to_csv(stub / "scenario_000.csv", index=False)
    assert supervisor._spent() == pytest.approx(0.7)


def test_spend_prefers_scenario_ledger_over_matching_csv(
    manifest, tmp_path, monkeypatch
):
    monkeypatch.setattr(Supervisor, "_credits_usage", lambda self: None)
    supervisor = make_supervisor(manifest, tmp_path)
    scenario_path = supervisor.scenario_csv(0)
    scenario_path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "scenario_id": ["scenario_000"],
            "prediction": [1.0],
            "total_cost_usd": [9.9],
        }
    ).to_csv(scenario_path, index=False)
    spend_ledger_path(scenario_path).write_text(
        "\nnot-json\n"
        + json.dumps(
            {
                "call_key": "sync:initial",
                "status": "parse_error",
                "total_cost_usd": 0.2,
            }
        )
        + "\n"
        + json.dumps(
            {
                "call_key": "sync:repair",
                "status": "ok",
                "total_cost_usd": 0.3,
            }
        )
        + "\n"
    )

    assert supervisor._spent() == pytest.approx(0.5)


def test_spend_falls_back_to_csv_when_ledger_has_no_valid_records(
    manifest, tmp_path, monkeypatch
):
    monkeypatch.setattr(Supervisor, "_credits_usage", lambda self: None)
    supervisor = make_supervisor(manifest, tmp_path)
    scenario_path = supervisor.scenario_csv(0)
    scenario_path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "scenario_id": ["scenario_000"],
            "prediction": [1.0],
            "total_cost_usd": [0.7],
        }
    ).to_csv(scenario_path, index=False)
    spend_ledger_path(scenario_path).write_text("interrupted-json")

    assert supervisor._spent() == pytest.approx(0.7)


def test_spend_falls_back_to_csv_when_ledger_has_only_null_costs(
    manifest, tmp_path, monkeypatch
):
    monkeypatch.setattr(Supervisor, "_credits_usage", lambda self: None)
    supervisor = make_supervisor(manifest, tmp_path)
    scenario_path = supervisor.scenario_csv(0)
    scenario_path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "scenario_id": ["scenario_000"],
            "prediction": [1.0],
            "total_cost_usd": [0.7],
        }
    ).to_csv(scenario_path, index=False)
    spend_ledger_path(scenario_path).write_text(
        json.dumps(
            {
                "call_key": "sync:pending",
                "status": "pending",
                "total_cost_usd": None,
            }
        )
        + "\n"
    )

    assert supervisor._spent() == pytest.approx(0.7)


def test_spend_includes_orphan_failed_scenario_ledger(manifest, tmp_path, monkeypatch):
    monkeypatch.setattr(Supervisor, "_credits_usage", lambda self: None)
    supervisor = make_supervisor(manifest, tmp_path)
    scenario_path = supervisor.scenario_csv(4)
    scenario_path.parent.mkdir(parents=True)
    spend_ledger_path(scenario_path).write_text(
        json.dumps(
            {
                "call_key": "sync:provider-error",
                "status": "provider_error",
                "total_cost_usd": 0.4,
            }
        )
        + "\n"
    )

    assert scenario_path.exists() is False
    assert supervisor._spent() == pytest.approx(0.4)


def test_non_openrouter_model_ignores_openrouter_account_meter(
    manifest, tmp_path, monkeypatch
):
    called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("OpenRouter meter should not be queried")

    monkeypatch.setattr("urllib.request.urlopen", fail_if_called)
    supervisor = Supervisor(
        model="gpt-5.6-sol",
        manifest=manifest,
        run_dir=tmp_path / "run",
        env={"OPENROUTER_API_KEY": "present-but-unrelated"},
    )

    assert supervisor._credits_baseline is None
    assert called is False


def test_supervisor_rejects_sensitivity_knobs_for_responses_models(
    manifest, tmp_path, monkeypatch
):
    """gpt-5 models run on the Responses transport, whose builders send the
    forced tool only; a knobbed run must fail before any request is sent
    rather than be fingerprinted as auto."""
    monkeypatch.setitem(MODELS, "test-model", "gpt-5.6-sol")
    make_supervisor(manifest, tmp_path)
    with pytest.raises(ValueError, match="Responses API"):
        make_supervisor(manifest, tmp_path, env={"POLICYBENCH_TOOL_CHOICE": "auto"})
    with pytest.raises(ValueError, match="POLICYBENCH_CONTRACT_OVERRIDE"):
        make_supervisor(
            manifest, tmp_path, env={"POLICYBENCH_CONTRACT_OVERRIDE": "json"}
        )


def test_run_cli_maps_sensitivity_knob_error_to_system_exit(
    manifest, tmp_path, monkeypatch
):
    from policybench.cli import main

    run_dir = tmp_path / "run"
    monkeypatch.setenv("POLICYBENCH_TOOL_CHOICE", "auto")
    monkeypatch.setattr(
        "sys.argv",
        [
            "policybench",
            "run",
            "--model",
            "gpt-5.6-sol",
            "--scenario-manifest",
            str(manifest),
            "--run-dir",
            str(run_dir),
        ],
    )

    with pytest.raises(SystemExit, match="Responses API"):
        main()

    assert not run_dir.exists()
