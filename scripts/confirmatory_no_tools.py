#!/usr/bin/env python3
"""Run the confirmatory no-tools stage with complete, recoverable attempts.

Every model runs in its own thread, in draw order, under a shared $5 ceiling.
A replaced final is moved byte for byte into ``households/attempts`` before
its rerun; the final links every archive by number, hash, status and reason.
Re-invocation resumes solely from those files and is an operator's approval
to rerun a paused account failure. Native harness resume is never used.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import threading
from pathlib import Path

# confirmatory_run pins the harness and policybench to this checkout.
from confirmatory_run import (
    CHEAP,
    MAX_RERUNS,
    PROMPT_VERSION,
    action,
    attempt_cost,
    classify,
    default_completion,
    pilot,
    sha256_file,
    write_json,
)

NO_TOOLS_CAP = 5.0


class StateError(ValueError):
    """The files cannot describe an intact no-tools attempt history."""


def component(value: str) -> str:
    """A record/model name must name one ordinary path component."""
    if (
        not isinstance(value, str)
        or value in ("", ".", "..")
        or Path(value).name != value
    ):
        raise StateError(f"invalid path component {value!r}")
    return value


def read_record(path: Path) -> dict:
    try:
        record = json.loads(path.read_text())
        if not isinstance(record, dict):
            raise ValueError("record is not a JSON object")
        if "prior_attempts" in record:
            raise ValueError("native prior_attempts cannot preserve full attempts")
        if not isinstance(record.get("attempts"), list):
            raise ValueError("record lacks an attempts list")
        cost = attempt_cost(record)
        if not math.isfinite(cost) or cost < 0:
            raise ValueError("attempt cost must be finite and nonnegative")
        return record
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise StateError(f"{path}: {error}") from error


def entry(path: Path, record: dict, n: int) -> dict:
    cls, reason = classify(record, 0.0, 0.0, None)
    return {
        "n": n,
        "file": f"attempts/{path.name}",
        "sha256": sha256_file(path),
        "status": record.get("status"),
        "class": cls,
        "reason": reason,
    }


def history(folder: Path) -> tuple[dict[str, dict], float]:
    """Validate a model's histories, including an interrupted archive, and sum spend."""
    archives: dict[str, list[tuple[int, Path]]] = {}
    for path in sorted((folder / "attempts").glob("*.json")):
        match = re.fullmatch(r"(.+)-([1-9][0-9]*)\.json", path.name)
        if not match:
            raise StateError(f"{path}: invalid attempt number")
        archives.setdefault(match[1], []).append((int(match[2]), path))
    finals = {path.stem: path for path in sorted(folder.glob("*.json"))}
    states, spent = {}, 0.0
    for sid in sorted(set(finals) | set(archives)):
        paths = sorted(archives.get(sid, []))
        numbers = [n for n, _ in paths]
        if numbers != list(range(1, len(paths) + 1)):
            raise StateError(
                f"{folder}: attempt-number gap for {sid}: "
                + ", ".join(path.name for _, path in paths)
            )
        if len(paths) > MAX_RERUNS:
            raise StateError(f"{folder}: {sid} exceeds {MAX_RERUNS} reruns")
        entries = []
        for n, path in paths:
            record = read_record(path)
            if record.get("scenario_id") != sid:
                raise StateError(f"{path}: household differs from archive name {sid}")
            if record["attempts"] != entries:
                raise StateError(f"{path}: attempts disagree with earlier archives")
            cls, _ = classify(record, 0.0, 0.0, None)
            if action(cls, n) not in ("rerun", "pause-rerun"):
                raise StateError(f"{path}: archived attempt was ineligible for rerun")
            entries.append(entry(path, record, n))
            spent += attempt_cost(record)
        final = None
        if sid in finals:
            path = finals[sid]
            final = read_record(path)
            if final.get("scenario_id") != sid:
                raise StateError(f"{path}: household differs from final name {sid}")
            if final["attempts"] != entries:
                raise StateError(f"{path}: attempts disagree with archived files")
            spent += attempt_cost(final)
        states[sid] = {"entries": entries, "final": final}
    return states, spent


class Spend:
    """The stage's recorded spend, shared by every model and every invocation."""

    def __init__(self, spent: float, stopped: threading.Event):
        self.spent_usd, self.budget_usd = spent, NO_TOOLS_CAP
        self.lock, self.stopped = threading.Lock(), stopped
        if spent >= self.budget_usd:
            stopped.set()

    def exhausted(self, reserve_usd: float = 0.0) -> bool:
        with self.lock:
            return (
                self.stopped.is_set() or self.spent_usd + reserve_usd >= self.budget_usd
            )


class AttemptSpend:
    """Count a request in both the stage and its own exception fallback record."""

    def __init__(self, stage: Spend):
        self.stage, self.spent_usd = stage, 0.0

    def add(self, usd: float | None) -> None:
        cost = float(usd or 0.0)
        with self.stage.lock:
            self.spent_usd += cost
            self.stage.spent_usd += cost
            if self.stage.spent_usd >= self.stage.budget_usd:
                self.stage.stopped.set()

    def exhausted(self, reserve_usd: float = 0.0) -> bool:
        return self.stage.exhausted(reserve_usd)


class Stage:
    """One stage, with injectable providers/board for a provider-free rehearsal."""

    def __init__(
        self,
        design: dict,
        models=None,
        run_household=None,
        completion_for=default_completion,
        board=None,
        out=None,
    ):
        self.design = design
        self.models = tuple(dict.fromkeys(models if models is not None else CHEAP))
        if not self.models:
            raise StateError("at least one model is required")
        for model in self.models:
            component(model)
        self.draw_order = [component(sid) for sid in design["draw_order"]]
        if len(self.draw_order) != len(set(self.draw_order)):
            raise StateError("draw_order repeats a household")
        spec = design["no_tools"]
        self.root = Path(spec["runs"])
        self.folder, self.stage = component(spec["folder"]), component(spec["stage"])
        self.out = sys.stdout if out is None else out
        self._say_lock = threading.Lock()
        self.stopped = threading.Event()
        self.completion_for = completion_for
        self.run_household = (
            run_household if run_household is not None else pilot.run_household
        )
        pilot.set_stated_engine(design["engine"].split()[-1])
        if board is None:
            board_path = Path(design["board"])
            if f"policyengine-us {pilot.board_engine(board_path)}" != design["engine"]:
                raise StateError("the board's engine differs from the design")
            pilot._require_engine(board_path)
            board = pilot.load_board(board_path)
        self.board = board
        missing = set(self.draw_order) - set(board["scenarios"])
        missing |= set(self.draw_order) - set(board["variables"])
        if missing:
            raise StateError(
                f"drawn households missing from the board: {sorted(missing)}"
            )
        self.histories = {}
        spent = 0.0
        folders = (
            {p.name for p in self.root.iterdir() if p.is_dir()}
            if self.root.is_dir()
            else set()
        )
        for model in sorted(folders | set(self.models)):
            states, cost = history(self.households(model))
            self.histories[model] = states
            spent += cost
            # A saved ceiling failure is a stage-wide stop on every invocation.
            if any(
                state["final"] is not None
                and action(
                    classify(state["final"], 0.0, 0.0, None)[0],
                    len(state["entries"]) + 1,
                )
                == "stopped"
                for state in states.values()
            ):
                self.stopped.set()
        self.spend = Spend(spent, self.stopped)
        self.states = {model: "pending" for model in self.models}

    def households(self, model: str) -> Path:
        return self.root / model / self.folder / self.stage / "households"

    def say(self, text: str) -> None:
        with self._say_lock:
            print(text, file=self.out, flush=True)

    def standing(self, model: str, sid: str) -> bool:
        state = self.histories[model].get(sid)
        return bool(
            state
            and state["final"] is not None
            and action(
                classify(state["final"], 0.0, 0.0, None)[0], len(state["entries"]) + 1
            )
            == "stands"
        )

    def dry_run(self) -> int:
        for model in self.models:
            done = [sid for sid in self.draw_order if self.standing(model, sid)]
            owed = []
            for sid in self.draw_order:
                if sid in done:
                    continue
                state = self.histories[model].get(sid, {"entries": [], "final": None})
                n = len(state["entries"]) + 1
                if state["final"] is not None:
                    outcome = action(classify(state["final"], 0.0, 0.0, None)[0], n)
                    if outcome in ("stop", "stopped"):
                        owed.append(f"{sid}:blocked {outcome} at attempt {n}")
                        continue
                    n += 1
                owed.append(f"{sid}:{n}")
            self.say(f"{model}: done {done}; owed (household:next attempt) {owed}")
        self.say(f"stage spend ${self.spend.spent_usd:.6f} of ${NO_TOOLS_CAP:.2f}")
        return (
            0
            if all(
                self.standing(model, sid)
                for model in self.models
                for sid in self.draw_order
            )
            else 1
        )

    def archive(self, model: str, sid: str) -> None:
        """Move an eligible final unchanged, then extend its reconstructed links."""
        state = self.histories[model][sid]
        record, entries = state["final"], state["entries"]
        n = len(entries) + 1
        cls, _ = classify(record, 0.0, 0.0, None)
        if action(cls, n) not in ("rerun", "pause-rerun"):
            raise StateError(f"{model}/{sid}: attempt {n} is ineligible for rerun")
        folder = self.households(model)
        target = folder / "attempts" / f"{sid}-{n}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise StateError(f"{target}: would overwrite an archived attempt")
        os.replace(folder / f"{sid}.json", target)
        entries.append(entry(target, record, n))
        state["final"] = None

    def run_model(self, model: str) -> None:
        try:
            profile = pilot.model_profile(
                model, arm="none", prompt_version=PROMPT_VERSION
            )
            if profile.uses_calculator or profile.uses_web:
                raise StateError(f"{model}: the none profile offers a tool")
            completion = None
            completion_loaded = False
            for sid in self.draw_order:
                state = self.histories[model].setdefault(
                    sid, {"entries": [], "final": None}
                )
                while True:
                    if state["final"] is not None:
                        cls, _ = classify(state["final"], 0.0, 0.0, None)
                        outcome = action(cls, len(state["entries"]) + 1)
                        if outcome == "stands":
                            break
                        if outcome == "stop":
                            self.states[model] = "harness-stopped"
                            return
                        if outcome == "stopped":
                            self.stopped.set()
                    if self.spend.exhausted():
                        self.states[model] = "budget-stopped"
                        return
                    if state["final"] is not None:
                        self.archive(model, sid)
                    if not completion_loaded:
                        completion = self.completion_for(profile)
                        completion_loaded = True
                    if self.spend.exhausted():
                        self.states[model] = "budget-stopped"
                        return
                    spend = AttemptSpend(self.spend)

                    def no_tool(arguments):
                        raise RuntimeError("the no-tools arm cannot call a tool")

                    try:
                        record = self.run_household(
                            self.board["scenarios"][sid],
                            self.board["variables"][sid],
                            no_tool,
                            completion,
                            spend,
                            profile=profile,
                        )
                    except Exception as error:
                        record = pilot.harness_error_record(
                            sid, self.board["variables"][sid], profile, error
                        )
                        record["totals"]["cost_usd"] = spend.spent_usd
                    record["attempts"] = list(state["entries"])
                    write_json(self.households(model) / f"{sid}.json", record)
                    state["final"] = record
                    n = len(state["entries"]) + 1
                    cls, _ = classify(record, 0.0, 0.0, None)
                    outcome = action(cls, n)
                    self.say(
                        f"{model} {sid} {n} {cls} {outcome} ${attempt_cost(record):.6f}"
                    )
                    if outcome == "pause-rerun":
                        self.states[model] = "operator-paused"
                        return
                    if outcome == "stop":
                        self.states[model] = "harness-stopped"
                        return
                    if outcome == "stopped":
                        self.stopped.set()
                        self.states[model] = "budget-stopped"
                        return
                    if outcome == "stands":
                        break
            self.states[model] = "complete"
        except Exception as error:
            self.states[model] = "error"
            self.say(f"{model}: {type(error).__name__}: {error}")

    def execute(self) -> int:
        threads = [
            threading.Thread(
                target=self.run_model, args=(model,), name=f"no-tools-{model}"
            )
            for model in self.models
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for model in self.models:
            self.say(f"{model}: {self.states[model]}")
        self.say(f"stage spend ${self.spend.spent_usd:.6f} of ${NO_TOOLS_CAP:.2f}")
        return (
            0 if all(self.states[model] == "complete" for model in self.models) else 1
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("design", type=Path)
    run.add_argument("--model", action="extend", nargs="+")
    run.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        stage = Stage(json.loads(args.design.read_text()), models=args.model)
        return stage.dry_run() if args.dry_run else stage.execute()
    except (StateError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"The no-tools stage cannot start: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
