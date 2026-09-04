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

import hashlib
import json
import math
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from policybench.config import MODELS, PROGRAMS
from policybench.model_cards import (
    PROMPT_CONTRACT_VERSION,
    answer_contract_for,
    card_for,
    completion_budget_ceiling_for,
    explanation_chunk_size_for,
)
from policybench.spend_ledger import (
    SPEND_LEDGER_SUFFIX,
    count_budget_escalations,
    read_spend_ledger,
)

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
TREATMENT_FINGERPRINT_VERSION = 3


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
    budget_escalation_count: int = 0

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
        from policybench.eval_no_tools import _reject_sensitivity_knobs_for_responses

        _reject_sensitivity_knobs_for_responses(
            self.litellm_id, env={**os.environ, **(env or {})}
        )
        self.manifest = Path(manifest)
        self.run_dir = Path(run_dir)
        self.budget_usd = budget_usd
        self.max_workers = max_workers
        self.max_rounds = max_rounds
        self.python = python or sys.executable
        self.env = {**os.environ, **(env or {})}
        self.scenarios = self._load_scenarios()
        self.scenario_ids = [scenario.id for scenario in self.scenarios]
        self.initial_request_variables = self._load_initial_request_variables()
        self.treatment_fingerprint = self._treatment_fingerprint()
        self.workload = self._workload()
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
        self._credits_spent_offset = 0.0

    # -- setup -------------------------------------------------------------

    def _load_scenarios(self):
        from policybench.scenarios import load_scenarios_from_manifest

        scenarios = load_scenarios_from_manifest(self.manifest)
        if not scenarios:
            raise ValueError("Scenario manifest must contain at least one scenario.")
        return scenarios

    def _load_initial_request_variables(self) -> list[str]:
        """Expand the first manifest row exactly as the worker CLI will."""
        from policybench.spec import expand_programs_for_scenario

        return expand_programs_for_scenario(PROGRAMS, self.scenarios[0])

    @staticmethod
    def _joined_sha256(values: list[str]) -> str:
        return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()

    def _workload(self) -> dict:
        return {
            "manifest_sha256": hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
            "scenario_ids_sha256": self._joined_sha256(self.scenario_ids),
            "output_set_sha256": self._joined_sha256(sorted(PROGRAMS)),
            "prompt_contract_version": PROMPT_CONTRACT_VERSION,
        }

    def scenario_csv(self, index: int) -> Path:
        return self.run_dir / SCENARIO_DIR / f"scenario_{index:03d}.csv"

    def _expected_outputs_for_scenario(self, index: int) -> list[str]:
        from policybench.spec import expand_programs_for_scenario

        return expand_programs_for_scenario(PROGRAMS, self.scenarios[index])

    def _scenario_complete(self, index: int) -> bool:
        from policybench.eval_no_tools import NO_TOOLS_RESULT_COLUMNS

        path = self.scenario_csv(index)
        if not path.exists():
            return False

        metadata_path = Path(f"{path}.meta.json")
        if not metadata_path.exists():
            self._raise_stale_scenario_output(
                path,
                f"missing required {metadata_path.name}",
                extra_path=metadata_path,
            )

        try:
            frame = pd.read_csv(path)
        except Exception as error:
            self._raise_stale_scenario_output(path, f"could not read CSV: {error}")

        missing_columns = sorted(set(NO_TOOLS_RESULT_COLUMNS) - set(frame.columns))
        if missing_columns:
            self._raise_stale_scenario_output(
                path,
                f"missing columns {missing_columns}",
            )

        expected_scenario_id = self.scenario_ids[index]
        actual_scenario_ids = frame["scenario_id"].tolist()
        if not actual_scenario_ids or any(
            scenario_id != expected_scenario_id for scenario_id in actual_scenario_ids
        ):
            self._raise_stale_scenario_output(
                path,
                f"scenario_id rows do not exactly equal {expected_scenario_id!r}",
            )

        actual_models = frame["model"].tolist()
        if not actual_models or any(model != self.model for model in actual_models):
            self._raise_stale_scenario_output(
                path,
                f"model rows do not exactly equal {self.model!r}",
                extra_path=metadata_path,
            )

        expected_outputs = self._expected_outputs_for_scenario(index)
        actual_outputs = frame["variable"].tolist()
        if len(actual_outputs) != len(expected_outputs) or set(actual_outputs) != set(
            expected_outputs
        ):
            missing = sorted(set(expected_outputs) - set(actual_outputs))
            unexpected = sorted(set(actual_outputs) - set(expected_outputs))
            self._raise_stale_scenario_output(
                path,
                "output rows differ from the current workload "
                f"(missing={missing}, unexpected={unexpected})",
            )

        try:
            metadata = json.loads(metadata_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            self._raise_stale_scenario_output(
                path,
                f"could not read {metadata_path.name}: {error}",
                extra_path=metadata_path,
            )
        if not isinstance(metadata, dict):
            self._raise_stale_scenario_output(
                path,
                f"{metadata_path.name} must contain a JSON object",
                extra_path=metadata_path,
            )

        expected_metadata = self._expected_scenario_metadata(index)
        for field_name, expected in expected_metadata.items():
            stored = metadata.get(field_name)
            if stored != expected:
                self._raise_stale_scenario_output(
                    path,
                    f"{metadata_path.name} field {field_name!r} differs "
                    f"(stored={stored!r}, requested={expected!r})",
                    extra_path=metadata_path,
                )
        return True

    def _expected_scenario_metadata(self, index: int) -> dict:
        from policybench.eval_no_tools import _build_resume_metadata

        # Match the eval-no-tools CLI defaults used by _spawn, including
        # its sliced scenario list and the environment of the subprocess.
        return _build_resume_metadata(
            task="eval_no_tools_batch",
            scenarios=[self.scenarios[index]],
            models={self.model: self.litellm_id},
            programs=PROGRAMS,
            run_id=None,
            include_explanations=True,
            env=self.env,
        )

    def _raise_stale_scenario_output(
        self,
        path: Path,
        reason: str,
        *,
        extra_path: Path | None = None,
    ) -> None:
        offending = [path]
        if extra_path is not None:
            offending.append(extra_path)
        raise ValueError(
            "Cannot resume: stale scenario output files "
            f"{', '.join(str(item) for item in offending)}: {reason}. "
            "Use a fresh run directory."
        )

    def pending_indices(self) -> list[int]:
        return [
            i for i in range(len(self.scenario_ids)) if not self._scenario_complete(i)
        ]

    def _treatment_fingerprint(self) -> dict:
        from policybench.eval_no_tools import (
            _first_request_variables,
            _initial_completion_budget_tokens,
            _max_repair_rounds,
            _request_timeout_seconds,
            _thinking_configuration,
        )

        answer_contract = answer_contract_for(
            self.litellm_id,
            contract_override=self.env.get("POLICYBENCH_CONTRACT_OVERRIDE"),
        )
        first_request_variables = _first_request_variables(
            self.litellm_id,
            self.initial_request_variables,
            include_explanations=True,
            chunk_override=self.env.get("POLICYBENCH_CHUNK_OVERRIDE"),
        )
        return {
            "fingerprint_version": TREATMENT_FINGERPRINT_VERSION,
            "model_id": self.litellm_id,
            "answer_contract": answer_contract,
            "tool_choice_mode": (
                None
                if answer_contract != "tool"
                else (
                    "auto"
                    if self.env.get("POLICYBENCH_TOOL_CHOICE") == "auto"
                    else "forced"
                )
            ),
            "chunk_size": explanation_chunk_size_for(
                self.litellm_id,
                chunk_override=self.env.get("POLICYBENCH_CHUNK_OVERRIDE"),
            ),
            "prompt_contract_version": PROMPT_CONTRACT_VERSION,
            "completion_budget_ceiling": completion_budget_ceiling_for(self.litellm_id),
            "initial_completion_budget_tokens": _initial_completion_budget_tokens(
                self.litellm_id,
                first_request_variables,
            ),
            "thinking": _thinking_configuration(self.litellm_id),
            "request_timeout_seconds": _request_timeout_seconds(
                self.litellm_id,
                env=self.env,
            ),
            "max_repair_rounds": _max_repair_rounds(self.env),
        }

    def _validate_resume(self) -> dict | None:
        state_path = self.run_dir / HEARTBEAT_FILENAME
        scenario_dir = self.run_dir / SCENARIO_DIR
        scenario_artifacts = {
            path
            for pattern in ("scenario_*.csv", f"*{SPEND_LEDGER_SUFFIX}", "*.meta.json")
            for path in scenario_dir.glob(pattern)
        }
        if not state_path.exists():
            if scenario_artifacts:
                raise ValueError(
                    f"Cannot resume run at {self.run_dir}: existing scenario outputs "
                    f"are missing {HEARTBEAT_FILENAME}. Use a fresh run directory."
                )
            return None

        try:
            existing = json.loads(state_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(
                f"Cannot resume run at {self.run_dir}: could not read "
                f"{HEARTBEAT_FILENAME}: {error}"
            ) from error
        if not isinstance(existing, dict):
            raise ValueError(
                f"Cannot resume run at {self.run_dir}: {HEARTBEAT_FILENAME} "
                "must contain a JSON object."
            )
        if existing.get("model") != self.model:
            raise ValueError(
                "Cannot resume: run state field 'model' differs "
                f"(stored={existing.get('model')!r}, requested={self.model!r})."
            )

        stored_workload = existing.get("workload")
        if not isinstance(stored_workload, dict):
            raise ValueError(
                "Cannot resume: run state field 'workload' is missing. "
                "Use a fresh run directory."
            )
        missing_workload_fields = sorted(set(self.workload) - set(stored_workload))
        if missing_workload_fields:
            raise ValueError(
                "Cannot resume: stored workload is missing fields: "
                f"{', '.join(missing_workload_fields)}. Use a fresh run directory."
            )
        for field_name, requested in self.workload.items():
            stored = stored_workload.get(field_name)
            if stored != requested:
                raise ValueError(
                    "Cannot resume: workload field "
                    f"'{field_name}' differs "
                    f"(stored={stored!r}, requested={requested!r}). "
                    "Use a fresh run directory."
                )

        expected_artifacts = {
            Path(f"{self.scenario_csv(index)}{suffix}")
            for index in range(len(self.scenario_ids))
            for suffix in ("", SPEND_LEDGER_SUFFIX, ".meta.json")
        }
        unexpected_artifacts = sorted(scenario_artifacts - expected_artifacts)
        if unexpected_artifacts:
            raise ValueError(
                "Cannot resume: stale scenario output files "
                f"{', '.join(str(path) for path in unexpected_artifacts)} are outside "
                "the current workload. Use a fresh run directory."
            )

        stored_fingerprint = existing.get("treatment_fingerprint")
        if not isinstance(stored_fingerprint, dict):
            raise ValueError(
                "Cannot resume: run state field 'treatment_fingerprint' is missing. "
                "Use a fresh run directory."
            )
        missing_fields = sorted(
            set(self.treatment_fingerprint) - set(stored_fingerprint)
        )
        if missing_fields:
            raise ValueError(
                "Cannot resume: stored treatment fingerprint is missing fields "
                f"required by fingerprint v{TREATMENT_FINGERPRINT_VERSION}: "
                f"{', '.join(missing_fields)}. Use a fresh run directory."
            )
        for field_name, requested in self.treatment_fingerprint.items():
            stored = stored_fingerprint.get(field_name)
            if stored != requested:
                raise ValueError(
                    "Cannot resume: treatment fingerprint field "
                    f"'{field_name}' differs "
                    f"(stored={stored!r}, requested={requested!r}). "
                    "Use a fresh run directory."
                )
        return existing

    # -- budget ------------------------------------------------------------

    # Cache-replayed responses carry their ORIGINAL recorded cost, so the
    # disk sum double-counts money spent in earlier runs (observed on the
    # supervisor's first production outing: $7.74 "spent" in a minute of
    # free replays). When an OpenRouter key is present, the /credits delta
    # from run start is the authoritative meter; the disk sum is the
    # fallback for providers without a balance endpoint. Never use the
    # OpenRouter account meter for a model served by another provider merely
    # because that credential also happens to be present in the environment.
    CREDITS_POLL_SECONDS = 20.0

    def _credits_usage(self) -> float | None:
        if not self.litellm_id.startswith("openrouter/"):
            return None
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
            return self._credits_spent_offset + self._credits_spent
        return self._spent_from_disk()

    def _spent_from_disk(self) -> float:
        total = 0.0
        scen_dir = self.run_dir / SCENARIO_DIR
        if not scen_dir.exists():
            return 0.0

        ledger_backed_csvs: set[Path] = set()
        expected_csvs = [
            self.scenario_csv(index) for index in range(len(self.scenario_ids))
        ]
        for csv_path in expected_csvs:
            path = Path(f"{csv_path}{SPEND_LEDGER_SUFFIX}")
            records = read_spend_ledger(path)
            if not records:
                continue
            ledger_total = 0.0
            has_ledger_cost = False
            for record in records:
                cost = record.get("total_cost_usd")
                if cost is None:
                    continue
                try:
                    parsed_cost = float(cost)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(parsed_cost):
                    continue
                ledger_total += parsed_cost
                has_ledger_cost = True
            if has_ledger_cost:
                ledger_backed_csvs.add(csv_path)
                total += ledger_total

        for path in expected_csvs:
            if path in ledger_backed_csvs:
                continue
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

    def _budget_escalation_count_from_disk(self) -> int:
        scenario_dir = self.run_dir / SCENARIO_DIR
        if not scenario_dir.exists():
            return 0
        return sum(
            count_budget_escalations(
                read_spend_ledger(f"{self.scenario_csv(index)}{SPEND_LEDGER_SUFFIX}")
            )
            for index in range(len(self.scenario_ids))
        )

    def write_heartbeat(self) -> None:
        self.state.updated_at = time.time()
        self.state.budget_escalation_count = self._budget_escalation_count_from_disk()
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
            "budget_escalation_count": self.state.budget_escalation_count,
            "workload": self.workload,
            "treatment_fingerprint": self.treatment_fingerprint,
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
        existing_state = self._validate_resume()
        if self._credits_baseline is not None and existing_state is not None:
            prior_spend = existing_state.get("spent_usd")
            if isinstance(prior_spend, (int, float)) and prior_spend > 0:
                self._credits_spent_offset = float(prior_spend)
        existing_started_at = (
            existing_state.get("started_at") if existing_state is not None else None
        )
        self.state.started_at = (
            float(existing_started_at)
            if isinstance(existing_started_at, (int, float)) and existing_started_at > 0
            else time.time()
        )
        self.state.completed = [
            scenario_id
            for index, scenario_id in enumerate(self.scenario_ids)
            if self._scenario_complete(index)
        ]
        self.state.spent_usd = self._spent()
        self.write_heartbeat()
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
        if not scen_dir.exists():
            return None
        frames = []
        for index in range(len(self.scenario_ids)):
            if self._scenario_complete(index):
                frames.append(pd.read_csv(self.scenario_csv(index)))
        if not frames:
            return None
        combined = pd.concat(frames, ignore_index=True)
        out = self.run_dir / "predictions.csv"
        combined.to_csv(out, index=False)
        return out
