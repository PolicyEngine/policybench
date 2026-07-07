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

from policybench.supervisor import (
    ADAPTIVE_WINDOW,
    BUDGET_STOP_FRACTION,
    DEFAULT_MAX_WORKERS,
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
):
    """Replace _spawn with a no-op process and synthesize the scenario CSV."""
    fail_indices = fail_indices or set()
    timeout_indices = timeout_indices or set()

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


def test_resume_skips_completed_scenarios(manifest, tmp_path, monkeypatch):
    supervisor = make_supervisor(manifest, tmp_path)
    stub_worker(supervisor, monkeypatch)
    for index in (0, 1):
        supervisor._spawn(index).wait()
    spawned: list[int] = []
    original = supervisor._spawn

    def tracking_spawn(index: int):
        spawned.append(index)
        return original(index)

    monkeypatch.setattr(supervisor, "_spawn", tracking_spawn)
    supervisor.run(poll_seconds=0.01)
    assert 0 not in spawned and 1 not in spawned
    assert sorted(spawned) == [2, 3, 4, 5]


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


def test_spend_falls_back_to_disk_without_credits(manifest, tmp_path, monkeypatch):
    monkeypatch.setattr(Supervisor, "_credits_usage", lambda self: None)
    supervisor = make_supervisor(manifest, tmp_path)
    stub = tmp_path / "run" / "scenarios"
    stub.mkdir(parents=True)
    pd.DataFrame(
        {"scenario_id": ["scenario_000"], "prediction": [1.0], "total_cost_usd": [0.7]}
    ).to_csv(stub / "scenario_000.csv", index=False)
    assert supervisor._spent() == pytest.approx(0.7)
