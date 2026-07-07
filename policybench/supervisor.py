"""Run supervisor: a per-scenario work queue with a budget governor.

Replaces the fixed-range worker pattern that made the 2026-07 open-weight
runs painful: a slow scenario can no longer hold a 25-scenario range
hostage, crashed workers cost one scenario's progress instead of a range,
spend is projected from live per-scenario costs and the run stops cleanly
at a budget threshold instead of dying in a 402 storm, and a heartbeat
state file makes progress externally visible while worker stdout sits in
block buffers.

Each work item is ONE scenario, executed in its own subprocess through the
existing sync CLI path — reusing the disk cache, repair rounds, and the
SIGALRM wall timeout (which only functions on a process's main thread).
Results land as one CSV per scenario under ``<run_dir>/scenarios/`` and are
combined into ``<run_dir>/predictions.csv`` at the end; rerunning the same
command skips completed scenarios and replays partially-complete ones from
the response cache.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from policybench.config import MODELS
from policybench.model_cards import card_for

HEARTBEAT_FILENAME = "run_state.json"
SCENARIO_DIR = "scenarios"
DEFAULT_MAX_WORKERS = 4
MIN_WORKERS = 1
# Above this timeout share in the sliding window, concurrency steps down.
TIMEOUT_RATE_BACKOFF_THRESHOLD = 0.3
ADAPTIVE_WINDOW = 8
# Dispatching stops once projected spend for in-flight + queued work would
# cross this share of the budget.
BUDGET_STOP_FRACTION = 0.9


@dataclass
class ScenarioResult:
    scenario_id: str
    index: int
    ok: bool
    cost_usd: float = 0.0
    rows: int = 0
    missing_predictions: int = 0
    timed_out: bool = False
    seconds: float = 0.0


@dataclass
class RunState:
    model: str
    total: int
    completed: list[str] = field(default_factory=list)
    failed: dict[str, int] = field(default_factory=dict)
    spent_usd: float = 0.0
    budget_usd: float | None = None
    workers: int = DEFAULT_MAX_WORKERS
    stopped_reason: str | None = None
    started_at: float = 0.0
    updated_at: float = 0.0

    def projected_total_usd(self) -> float | None:
        if not self.completed:
            return None
        per = self.spent_usd / len(self.completed)
        return per * self.total


class Supervisor:
    def __init__(
        self,
        model: str,
        manifest: Path,
        run_dir: Path,
        budget_usd: float | None = None,
        max_workers: int = DEFAULT_MAX_WORKERS,
        max_rounds: int = 4,
        python: str | None = None,
        env: dict | None = None,
    ):
        self.model = model
        self.litellm_id = MODELS.get(model, model)
        self.manifest = Path(manifest)
        self.run_dir = Path(run_dir)
        self.budget_usd = budget_usd
        self.max_workers = max_workers
        self.max_rounds = max_rounds
        self.python = python or sys.executable
        self.env = {**os.environ, **(env or {})}
        self.scenario_ids = self._load_scenario_ids()
        self.state = RunState(
            model=model,
            total=len(self.scenario_ids),
            budget_usd=budget_usd,
            workers=min(max_workers, DEFAULT_MAX_WORKERS),
        )
        self._recent: list[ScenarioResult] = []
        self.projection_warning: str | None = None
        self._credits_baseline = self._credits_usage()
        self._credits_checked_at = float("-inf")
        self._credits_spent = 0.0

    # -- setup -------------------------------------------------------------

    def _load_scenario_ids(self) -> list[str]:
        frame = pd.read_csv(self.manifest)
        return list(frame["scenario_id"])

    def scenario_csv(self, index: int) -> Path:
        return self.run_dir / SCENARIO_DIR / f"scenario_{index:03d}.csv"

    def _scenario_complete(self, index: int) -> bool:
        path = self.scenario_csv(index)
        if not path.exists():
            return False
        try:
            frame = pd.read_csv(path)
        except Exception:
            return False
        return len(frame) > 0 and set(frame["scenario_id"]) == {
            self.scenario_ids[index]
        }

    def pending_indices(self) -> list[int]:
        return [
            i for i in range(len(self.scenario_ids)) if not self._scenario_complete(i)
        ]

    # -- budget ------------------------------------------------------------

    # Cache-replayed responses carry their ORIGINAL recorded cost, so the
    # disk sum double-counts money spent in earlier runs (observed on the
    # supervisor's first production outing: $7.74 "spent" in a minute of
    # free replays). When an OpenRouter key is present, the /credits delta
    # from run start is the authoritative meter; the disk sum is the
    # fallback for providers without a balance endpoint.
    CREDITS_POLL_SECONDS = 20.0

    def _credits_usage(self) -> float | None:
        key = self.env.get("OPENROUTER_API_KEY")
        if not key:
            return None
        request = urllib.request.Request(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.load(response)["data"]
            return float(data["total_usage"])
        except Exception:
            return None

    def _spent(self) -> float:
        now = time.monotonic()
        if (
            self._credits_baseline is not None
            and now - self._credits_checked_at >= self.CREDITS_POLL_SECONDS
        ):
            usage = self._credits_usage()
            self._credits_checked_at = now
            if usage is not None:
                self._credits_spent = max(0.0, usage - self._credits_baseline)
        if self._credits_baseline is not None:
            return self._credits_spent
        return self._spent_from_disk()

    def _spent_from_disk(self) -> float:
        total = 0.0
        scen_dir = self.run_dir / SCENARIO_DIR
        if not scen_dir.exists():
            return 0.0
        for path in scen_dir.glob("scenario_*.csv"):
            try:
                frame = pd.read_csv(path)
            except Exception:
                continue
            col = frame.get("total_cost_usd")
            if col is not None:
                total += float(col.fillna(0).sum())
        return total

    def budget_allows_dispatch(self) -> bool:
        if self.budget_usd is None:
            return True
        if self.state.spent_usd >= self.budget_usd * BUDGET_STOP_FRACTION:
            self.state.stopped_reason = (
                f"budget: spent ${self.state.spent_usd:.2f} of "
                f"${self.budget_usd:.2f} (stop at "
                f"{BUDGET_STOP_FRACTION:.0%})"
            )
            return False
        projected = self.state.projected_total_usd()
        card = card_for(self.litellm_id)
        if projected is None and card and card.expected_cost_per_scenario_usd:
            projected = card.expected_cost_per_scenario_usd * self.state.total
        if projected is not None and projected > self.budget_usd:
            # Keep dispatching — partial coverage still monetizes via the
            # response cache — but surface the projection immediately.
            self.projection_warning = (
                f"projected ${projected:.2f} exceeds budget ${self.budget_usd:.2f}"
            )
        return True

    # -- adaptive concurrency ----------------------------------------------

    def _record(self, result: ScenarioResult) -> None:
        self._recent.append(result)
        window = self._recent[-ADAPTIVE_WINDOW:]
        timeout_rate = sum(1 for r in window if r.timed_out) / len(window)
        if timeout_rate > TIMEOUT_RATE_BACKOFF_THRESHOLD:
            self.state.workers = max(MIN_WORKERS, self.state.workers - 1)
        elif (
            len(window) == ADAPTIVE_WINDOW
            and timeout_rate == 0
            and self.state.workers < self.max_workers
        ):
            self.state.workers += 1

    # -- heartbeat ----------------------------------------------------------

    def write_heartbeat(self) -> None:
        self.state.updated_at = time.time()
        payload = {
            "model": self.state.model,
            "total": self.state.total,
            "completed": len(self.state.completed),
            "failed_counts": self.state.failed,
            "spent_usd": round(self.state.spent_usd, 4),
            "budget_usd": self.state.budget_usd,
            "projected_total_usd": self.state.projected_total_usd(),
            "workers": self.state.workers,
            "stopped_reason": self.state.stopped_reason,
            "projection_warning": self.projection_warning,
            "started_at": self.state.started_at,
            "updated_at": self.state.updated_at,
        }
        self.run_dir.mkdir(parents=True, exist_ok=True)
        path = self.run_dir / HEARTBEAT_FILENAME
        path.write_text(json.dumps(payload, indent=2))

    # -- workers -------------------------------------------------------------

    def _spawn(self, index: int) -> subprocess.Popen:
        out = self.scenario_csv(index)
        out.parent.mkdir(parents=True, exist_ok=True)
        log = out.with_suffix(".log")
        cmd = [
            self.python,
            "-m",
            "policybench.cli",
            "eval-no-tools",
            "--model",
            self.model,
            "--scenario-manifest",
            str(self.manifest),
            "-n",
            str(len(self.scenario_ids)),
            "--scenario-start",
            str(index),
            "--scenario-end",
            str(index + 1),
            "-o",
            str(out),
        ]
        return subprocess.Popen(
            cmd,
            stdout=open(log, "w"),
            stderr=subprocess.STDOUT,
            env=self.env,
        )

    def _collect(self, index: int, started: float) -> ScenarioResult:
        scenario_id = self.scenario_ids[index]
        path = self.scenario_csv(index)
        if not path.exists():
            return ScenarioResult(
                scenario_id, index, ok=False, seconds=time.time() - started
            )
        try:
            frame = pd.read_csv(path)
        except Exception:
            return ScenarioResult(
                scenario_id, index, ok=False, seconds=time.time() - started
            )
        cost = float(
            frame.get("total_cost_usd", pd.Series(dtype=float)).fillna(0).sum()
        )
        missing = int(frame["prediction"].isna().sum()) if "prediction" in frame else 0
        log = path.with_suffix(".log")
        timed_out = False
        if log.exists():
            text = log.read_text(errors="ignore")
            timed_out = "Timeout" in text or "timed out" in text
        return ScenarioResult(
            scenario_id,
            index,
            ok=len(frame) > 0,
            cost_usd=cost,
            rows=len(frame),
            missing_predictions=missing,
            timed_out=timed_out,
            seconds=time.time() - started,
        )

    # -- main loop -----------------------------------------------------------

    def run(self, poll_seconds: float = 2.0) -> RunState:
        self.state.started_at = time.time()
        queue: list[int] = []
        rounds: dict[int, int] = {}
        for round_no in range(self.max_rounds):
            pending = self.pending_indices()
            if not pending:
                break
            queue = list(pending)
            in_flight: dict[int, tuple[subprocess.Popen, float]] = {}
            while queue or in_flight:
                while (
                    queue
                    and len(in_flight) < self.state.workers
                    and self.budget_allows_dispatch()
                ):
                    index = queue.pop(0)
                    rounds[index] = rounds.get(index, 0) + 1
                    in_flight[index] = (self._spawn(index), time.time())
                if not in_flight:
                    break  # budget stop with nothing running
                time.sleep(poll_seconds)
                for index in list(in_flight):
                    proc, started = in_flight[index]
                    if proc.poll() is None:
                        continue
                    del in_flight[index]
                    result = self._collect(index, started)
                    self._record(result)
                    if result.ok:
                        self.state.completed.append(result.scenario_id)
                    else:
                        self.state.failed[result.scenario_id] = rounds[index]
                    self.state.spent_usd = self._spent()
                    self.write_heartbeat()
            if self.state.stopped_reason:
                break
        self.state.spent_usd = self._spent()
        remaining = self.pending_indices()
        if remaining and not self.state.stopped_reason:
            self.state.stopped_reason = (
                f"{len(remaining)} scenarios incomplete after {self.max_rounds} rounds"
            )
        self.write_heartbeat()
        self.combine()
        return self.state

    # -- output ---------------------------------------------------------------

    def combine(self) -> Path | None:
        scen_dir = self.run_dir / SCENARIO_DIR
        parts = sorted(scen_dir.glob("scenario_*.csv")) if scen_dir.exists() else []
        if not parts:
            return None
        frames = []
        for path in parts:
            try:
                frames.append(pd.read_csv(path))
            except Exception:
                continue
        if not frames:
            return None
        combined = pd.concat(frames, ignore_index=True)
        out = self.run_dir / "predictions.csv"
        combined.to_csv(out, index=False)
        return out
