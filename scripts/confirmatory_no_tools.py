#!/usr/bin/env python3
"""Run the confirmatory no-tools stage with complete, recoverable attempts.

Every model runs in its own thread, in draw order, under a shared $5 ceiling.
A replaced final is moved byte for byte into ``households/attempts`` before
its rerun; the final links every archive by number, hash, status and reason.
Re-invocation resumes solely from those files and is an operator's approval
to rerun a paused account failure. Native harness resume is never used.
An archive move or attempt is admitted when its interruption check and commit
under the admission lock precede the watcher setting the interrupt under that
same lock. After that interrupt is set, no archive move or attempt is admitted.
The lock covers only the check and rename or admission state change; admitted
attempts finish and save outside it. The first SIGINT or SIGTERM records its
number and wakes the watcher through a nonblocking pipe. The handler takes no
lock and raises nothing beyond allocation failure. While running, the watcher
sets the interrupt, releases admission, and then announces that attempts already
admitted will finish and save. A first signal recorded after watcher shutdown
still forces exit 1 without setting the interrupt or printing that announcement.
The guarded cleanup path sets the interrupt and waits for script-owned worker
completion before restoring handlers or releasing the invocation lock.
Guarded waits retry exceptions raised within them and preserve the original
exception. Another handler raising in an unguarded instruction, before a guarded
call, in cleanup bookkeeping or in finally, can replace it and skip waits.
An exception caught in a model thread instead marks that model error without
setting the interrupt. A second signal immediately uses a nonblocking stderr
write and exits, losing every unsaved attempt then under way with its spend;
saved finals, archives and their recorded spend survive. Any signal before
handler restoration requires exit 1 on graceful completion, even if every
worker completed.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import re
import signal
import sys
import threading
import time
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
START_GRACE_SECONDS = 10


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
            try:
                classify(final, 0.0, 0.0, None)
            except (TypeError, ValueError, AttributeError, KeyError) as error:
                raise StateError(
                    f"{path}: cannot classify saved final: {error}"
                ) from error
            spent += attempt_cost(final)
        states[sid] = {"entries": entries, "final": final}
    return states, spent


def stage_problems(design: dict) -> list[str]:
    """Read stage histories and standing finals without a board or provider."""
    problems = []
    try:
        spec = design["no_tools"]
        root = Path(spec["runs"])
        folder, stage = component(spec["folder"]), component(spec["stage"])
        draw_order = [component(sid) for sid in design["draw_order"]]
        models = set(CHEAP)
        if root.is_dir():
            models.update(path.name for path in root.iterdir() if path.is_dir())
    except (OSError, KeyError, TypeError, ValueError) as error:
        return [f"no-tools stage: {error}"]
    for model in sorted(models):
        try:
            states, _ = history(root / model / folder / stage / "households")
            if model not in CHEAP:
                continue
            for sid in draw_order:
                state = states.get(sid)
                if state is None or state["final"] is None:
                    problems.append(f"no-tools {model}/{sid}: missing standing final")
                    continue
                outcome = action(
                    classify(state["final"], 0.0, 0.0, None)[0],
                    len(state["entries"]) + 1,
                )
                if outcome != "stands":
                    problems.append(
                        f"no-tools {model}/{sid}: final action is {outcome}"
                    )
        except (OSError, TypeError, ValueError, AttributeError, KeyError) as error:
            problems.append(f"no-tools {model}: {error}")
    return problems


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
        self._say_lock = threading.RLock()
        self.stopped = threading.Event()
        self.interrupted = threading.Event()
        self._admission_lock = threading.Lock()
        self._admitted_attempts = {}
        self._threads = []
        self.completion_for = completion_for
        self.run_household = (
            run_household if run_household is not None else pilot.run_household
        )
        self._lock_file = None
        try:
            baseline = design["baseline_exclusions"]
            if not isinstance(baseline, dict) or not isinstance(
                baseline.get("path"), str
            ):
                raise StateError("baseline exclusions need path and sha256")
            baseline_path = Path(baseline["path"])
            if sha256_file(baseline_path) != baseline.get("sha256"):
                raise StateError("baseline exclusions do not hash as declared")
            payload = json.loads(baseline_path.read_text())
            exclusions = (
                payload.get("exclusions") if isinstance(payload, dict) else None
            )
            if not isinstance(exclusions, list):
                raise StateError("baseline exclusions must contain an exclusions list")
            cells = []
            for exclusion in exclusions:
                if not isinstance(exclusion, dict) or any(
                    not isinstance(exclusion.get(key), str) or not exclusion[key]
                    for key in ("scenario_id", "variable")
                ):
                    raise StateError(
                        "baseline exclusion needs household and output strings"
                    )
                cells.append((exclusion["scenario_id"], exclusion["variable"]))
            if len(cells) != len(set(cells)):
                raise StateError("baseline exclusions repeat a cell")
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise StateError(f"baseline exclusions: {error}") from error
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock_file = (self.root / ".confirmatory-no-tools.lock").open("a")
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self.close()
            raise StateError(
                f"another no-tools invocation holds the lock in {self.root}"
            ) from error
        try:
            self._load_state(board)
        except BaseException:
            self.close()
            raise

    def _load_state(self, board) -> None:
        design = self.design
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

    def close(self) -> None:
        """Release the invocation lock, including after initialization failure."""
        lock = getattr(self, "_lock_file", None)
        if lock is not None:
            lock.close()
            self._lock_file = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        self.close()

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
        try:
            return self._dry_run()
        finally:
            self.close()

    def _dry_run(self) -> int:
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

    def archive(self, model: str, sid: str) -> bool:
        """Atomically admit a prepared archive move, then extend its links."""
        state = self.histories[model][sid]
        record, entries = state["final"], state["entries"]
        n = len(entries) + 1
        cls, _ = classify(record, 0.0, 0.0, None)
        if action(cls, n) not in ("rerun", "pause-rerun"):
            raise StateError(f"{model}/{sid}: attempt {n} is ineligible for rerun")
        folder = self.households(model)
        source = folder / f"{sid}.json"
        target = folder / "attempts" / f"{sid}-{n}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise StateError(f"{target}: would overwrite an archived attempt")
        link = entry(source, record, n)
        link["file"] = f"attempts/{target.name}"
        with self._admission_lock:
            if self.interrupted.is_set():
                return False
            os.replace(source, target)
            state["final"] = None
        entries.append(link)
        return True

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
                if self.interrupted.is_set():
                    self.states[model] = "interrupted"
                    return
                state = self.histories[model].setdefault(
                    sid, {"entries": [], "final": None}
                )
                while True:
                    if self.interrupted.is_set():
                        self.states[model] = "interrupted"
                        return
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
                        if self.interrupted.is_set():
                            self.states[model] = "interrupted"
                            return
                        if not self.archive(model, sid):
                            self.states[model] = "interrupted"
                            return
                    if not completion_loaded:
                        completion = self.completion_for(profile)
                        completion_loaded = True
                    if self.spend.exhausted():
                        self.states[model] = "budget-stopped"
                        return
                    spend = AttemptSpend(self.spend)
                    with self._admission_lock:
                        if self.interrupted.is_set():
                            self.states[model] = "interrupted"
                            return
                        self._admitted_attempts[model, sid] = len(state["entries"]) + 1

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
                    if self.interrupted.is_set():
                        self.states[model] = "interrupted"
                        return
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
        previous = {}
        signals = []
        closing = False
        watcher = None
        watcher_done = threading.Event()
        watcher_began = threading.Event()
        watcher_started = False
        failure = None
        read_fd = write_fd = None
        self._started_workers = []
        self._starting_worker = None
        self._worker_began = {}
        self._worker_done = {}

        def wake_watcher():
            try:
                os.write(write_fd, b"!")
            except OSError:
                pass

        def interrupt(signum, frame):
            signals.append(signum)
            if len(signals) >= 2:
                try:
                    os.set_blocking(2, False)
                    os.write(
                        2,
                        b"Forced interruption: every unsaved attempt then under way "
                        b"is lost, with its spend; saved finals, archives and the "
                        b"spend they record survive.\n",
                    )
                except OSError:
                    pass
                os._exit(128 + signum)
            wake_watcher()

        def stop_admission():
            while True:
                try:
                    with self._admission_lock:
                        self.interrupted.set()
                    return
                except BaseException:
                    continue

        def watch_signals():
            watcher_began.set()
            notified = False
            try:
                if closing:
                    return
                while True:
                    os.read(read_fd, 1)
                    if closing:
                        return
                    if signals and not notified:
                        with self._admission_lock:
                            self.interrupted.set()
                        notified = True
                        self.say(
                            "Interrupted: attempts already admitted "
                            "will finish and save."
                        )
            finally:
                watcher_done.set()

        try:
            read_fd, write_fd = os.pipe()
            os.set_blocking(write_fd, False)
            if threading.current_thread() is threading.main_thread():
                for sig in (signal.SIGINT, signal.SIGTERM):
                    previous[sig] = signal.signal(sig, interrupt)
            watcher = threading.Thread(
                target=watch_signals, name="no-tools-signal-watcher"
            )
            watcher.start()
            watcher_started = True
            result = self._execute()
        except BaseException as error:
            failure = error
            # SIGINT/SIGTERM handlers raise nothing beyond allocation failure.
            # Guarded waits retry exceptions raised within them, including those
            # from another handler (for example SIGUSR1 raising KeyboardInterrupt).
            # Another handler raising in an unguarded instruction, before a
            # guarded call, in cleanup bookkeeping or in finally, can replace
            # the original exception and skip waits.
            stop_admission()
            self._wait_for_workers()
            raise
        finally:
            closing = True
            if write_fd is not None:
                wake_watcher()
            shutdown_error = None
            if watcher is not None:
                # start() can raise after native startup, even before ident is set.
                # A watcher beginning after grace sees closing before reading a pipe.
                deadline = time.monotonic() + START_GRACE_SECONDS
                while not watcher_started and not watcher_began.is_set():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        watcher_began.wait(remaining)
                    except BaseException as error:
                        if shutdown_error is None:
                            shutdown_error = error
                if watcher_started or watcher_began.is_set():
                    while True:
                        try:
                            watcher_done.wait()
                            watcher.join()
                            break
                        except BaseException as error:
                            if shutdown_error is None:
                                shutdown_error = error
            if failure is None and shutdown_error is not None:
                stop_admission()
            # Restore the handlers first: until then a signal still writes to
            # write_fd, whose number a closed pipe could hand to another file.
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            for fd in (read_fd, write_fd):
                if fd is not None:
                    os.close(fd)
            self.close()
            if failure is None and shutdown_error is not None:
                raise shutdown_error
        return 1 if signals else result

    def _wait_for_workers(self) -> None:
        """Retry exceptions raised within guarded worker-completion waits.

        The installed SIGINT and SIGTERM handlers raise nothing beyond allocation
        failure. Guarded waits retry exceptions from elsewhere, such as a test-only
        SIGUSR1 handler raising KeyboardInterrupt, preserving the original exception.
        Another handler raising in unguarded instructions before a guarded call,
        in cleanup bookkeeping or in finally can replace it and skip waits.
        """
        workers = list(self._started_workers)
        starting = self._starting_worker
        if starting is not None and starting not in workers:
            model = self.models[self._threads.index(starting)]
            deadline = time.monotonic() + START_GRACE_SECONDS
            while not self._worker_began[model].is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    self._worker_began[model].wait(remaining)
                except BaseException:
                    continue
            if self._worker_began[model].is_set():
                workers.append(starting)
        for thread in workers:
            model = self.models[self._threads.index(thread)]
            while True:
                try:
                    self._worker_done[model].wait()
                    thread.join()
                    break
                except BaseException:
                    continue

    def _run_worker(self, model: str) -> None:
        self._worker_began[model].set()
        try:
            if self.interrupted.is_set():
                self.states[model] = "interrupted"
                return
            self.run_model(model)
        finally:
            self._worker_done[model].set()

    def _execute(self) -> int:
        self._worker_began = {model: threading.Event() for model in self.models}
        self._worker_done = {model: threading.Event() for model in self.models}
        self._threads = [
            threading.Thread(
                target=self._run_worker, args=(model,), name=f"no-tools-{model}"
            )
            for model in self.models
        ]
        for thread in self._threads:
            self._starting_worker = thread
            thread.start()
            self._started_workers.append(thread)
            self._starting_worker = None
        for model, thread in zip(self.models, self._threads):
            self._worker_done[model].wait()
            thread.join()
        for model in self.models:
            self.say(f"{model}: {self.states[model]}")
        self.say(f"stage spend ${self.spend.spent_usd:.6f} of ${NO_TOOLS_CAP:.2f}")
        return (
            0
            if not self.interrupted.is_set()
            and all(self.states[model] == "complete" for model in self.models)
            else 1
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
        with Stage(json.loads(args.design.read_text()), models=args.model) as stage:
            return stage.dry_run() if args.dry_run else stage.execute()
    except (StateError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"The no-tools stage cannot start: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
