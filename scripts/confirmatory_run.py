"""The confirmatory calculator-interface run.

Usage:
    python scripts/confirmatory_run.py run DESIGN [--workers N] [--dry-run]
    python scripts/confirmatory_run.py resume DESIGN MODEL [--note TEXT]

Runs the frozen pre-registration's "Run procedure" and writes its "Run
records", which the confirmatory report checks before it scores anything.
DESIGN is the JSON file written at the freeze, the file the report reads.

- **Lanes.** Each model has two lanes. Households alternate between them in
  draw order, the first drawn to lane 1. A lane runs one household's arms one
  after another, in the order drawn for that household and model (the stream
  ``order/<model>``), then its reruns in passes (second attempts before
  third, each pass in the household's order), and only then decides its next
  household. The six models run at once.
- **One engine pool per model**, started once, with no features of its own.
  Each call carries its arm's features in a call frame (``tool_call_frame``),
  the message a pool started with those features would send. ``setup-start``
  and ``setup-end`` events bracket startup and pool restarts, so setup time
  can be distinguished from an idle lane.
- **Admission.** A lane admits its next household when the spend of the
  model's finished households (every attempt, replaced ones included) plus
  the reserve for each household under way, this one included, is at most
  the model's cap plus $1e-9. A household is finished when its last attempt
  has ended. After one refusal every later decision is a refusal. A decision
  waits while an operator pause holds, and while any of the model's
  households has ended a pass whose reruns are undecided, so that whether it
  has finished is known.
- **Spend.** No conversation is stopped for spend, except at the hard
  ceiling: the overall cap plus $25, over the spend before the calculator
  stage and every model's spend since. At the crossing, no attempt starts,
  the conversations under way end ``budget_stop`` at their next turn, and
  every model's run log gets a ``ceiling`` event at the crossing's time.
  The decision to admit a household and the crossing share one lock, so no
  household is decided after the crossing.
- **The attempt deadline.** A conversation still running an hour after it
  started is abandoned: its attempt gets a harness-error record
  (``AttemptDeadline``) holding the spend so far, the model's lanes stop,
  and the conversation ends ``budget_stop`` at its next turn. Its spend after
  the deadline still counts toward the ceiling, and goes to the run log as
  ``late-cost`` events.
- **Failures.** Each attempt's class follows the pre-registration's table, in
  the precedence the report's ``classify`` uses, from its record and the host
  evidence for its start and end; its action follows from its class and its
  attempt number. An operator failure pauses the model's lanes until
  ``resume``, which is accepted only if written after the pause began. A
  harness failure stops them, and so does one inconclusive error that ends
  runs in more than five of the model's households. A replaced attempt is
  saved, before its rerun, as ``households/attempts/<household>-<n>.json``.
- **Stops.** Every ``stop`` event names its cause: ``harness``,
  ``inconclusive``, ``deadline``, ``pool`` (the engine pool could not be
  started again), ``runner-error`` (an exception in the runner itself, which
  stops every model's lanes after writing what had ended), ``interrupt`` or
  ``sampler``. The ceiling's events are ``ceiling`` events of cause
  ``ceiling``.
- **The host log.** Every 30 seconds: the time, the monotonic clock, the
  load average and the kernel's memory-pressure level (None when it could not
  be read, which is no sample). At the end, the guard's and the power log's
  lines from a day before the run's start to its end. A read of those logs is
  tried five times; one that still fails during the run is a runner error,
  and at the end leaves ``host-error.txt`` in place of the excerpts. An
  attempt's class waits for its host evidence to
  be complete: a good sample more than 60 seconds after the pass's last end,
  or no good sample for more than 90 seconds. A sampler whose samples have
  failed for five minutes, or whose thread has ended, stops every model.
- **Chains and anchors.** Every line of the run logs, the admission logs and
  the host log carries ``prev``, the sha256 of the line before it. The first
  line's is a seed: for a model's logs, the sha256 of the frozen hash, the
  model and the file's name; for the host log, of its name. Every 15
  minutes, and at the end, ``anchors.jsonl`` gets a line with every log's
  line count and head and every manifest's sha256, itself chained, and the
  design's ``anchor_command`` is run on a synced, atomic copy in the
  background. Each ``anchors.<head>.push-snapshot.jsonl`` is a copy, not a
  record, and is never replaced by a later push's snapshot. Each push's
  result goes to ``anchor-pushes.jsonl``. ``confirmatory_anchor.py`` is that
  command: under an exclusive, non-blocking clone lock, it accepts only a
  snapshot extending the clone's anchors, commits it and pushes it, so the
  remote holds each anchor's time from outside the run. Retiring a worker
  does not ensure its command has ended. If an old helper still holds the
  lock, later pushes fail as busy; a final segment left local is a deviation.
  Final pushes get up to three tries per set of heads, waiting a minute
  after each failed try ends before starting the next.

The records' format is the confirmatory report's (its module docstring). The
report recomputes every class, action, order and admission decision from the
records, with its own copy of these rules; the study's differential test runs
this runner on fakes and checks that its records pass the report.

The runner runs the treatment harness's code. It refuses to start unless its
``tool_pilot_argon.py``, ``policybench`` package and fix module are the
treatment commit's (6b00a6f0), its tree is clean at the design's run commit,
the machine is on AC power with the lid open, and the runs folder holds no
records: a run is never resumed. ``--workers`` must equal the design's
engine workers per model. An interrupt (SIGINT or SIGTERM) only notes the
signal; the main loop then stops every model's lanes with cause
``interrupt`` and lets the conversations under way end. A second interrupt
exits at once until cleanup ignores signals before its final check. Signals
during any re-anchoring after that check are ignored, including a second
interrupt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import numpy as np

# The harness and policybench come from this checkout, whatever else is on the
# path: the preflight refuses any other.
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

import tool_pilot_argon as pilot  # noqa: E402

TREATMENT_COMMIT = "6b00a6f0c4997e73b9968b412b57646957cad631"
# The treatment's code, which must be the treatment commit's.
TREATMENT_PATHS = (
    "scripts/tool_pilot_argon.py",
    "policybench",
    "reference_audit/2026-09-28/fixes",
)
PROMPT_VERSION = "v2-pilot"
CHEAP = ("claude-haiku-5.5", "gpt-6-luna", "gemini-3.5-flash-lite")
FRONTIER = ("gpt-6-sol", "claude-opus-5.5", "gemini-4-argon")
ARMS = (
    "pe",
    "pe3",
    "pe3-b",
    "loo-labels",
    "loo-names",
    "loo-flat",
    "loo-labels-flat",
)
FRONTIER_ARMS = ("pe", "pe3")
# The features each label drops from pe3; None for the tool v1 arm.
DROPPED = {
    "pe": None,
    "pe3": (),
    "pe3-b": (),
    "loo-labels": ("labels",),
    "loo-names": ("names",),
    "loo-flat": ("flat",),
    "loo-labels-flat": ("labels", "flat"),
}
HOUSEHOLDS = 120
MAX_RERUNS = 2
INCONCLUSIVE_STOP = 5  # households of a model one inconclusive error may end
PRESSURE_WINDOW = 60.0  # seconds
HOST_LOG_GAP = 90.0  # seconds
SAMPLE_SECONDS = 30.0
CEILING_MARGIN = 25.0  # dollars above the overall cap
ADMISSION_SLACK = 1e-9  # dollars
EXCERPT_LEAD = 86_400.0  # host logs are kept from a day before the run's start
WAIT_SECONDS = 1.0  # how often a waiting lane looks again
ATTEMPT_DEADLINE = 3600.0  # seconds; the longest development attempt took 714
SAMPLER_SILENCE = 300.0  # seconds without a host-log sample that stop the run
READ_TRIES = 5  # reads of the guard's and the power log before a runner error
READ_WAIT = 10.0  # seconds between them
ANCHOR_SECONDS = 900.0  # how often the logs' chain heads are anchored
ANCHOR_RETRY = 60.0  # seconds to the next anchor after a failed push
ANCHOR_PUSH_TIMEOUT = 300.0  # seconds; then the command's process group is killed
KILL_GRACE = 10.0  # seconds to drain pipes after killing the process group
FINAL_PUSH_TRIES = 3  # includes the first final push
LATE_JOIN = 60.0  # seconds the run's end waits, in all, for abandoned attempts
# What a stop event names as its cause.
STOP_CAUSES = frozenset(
    {
        "harness",
        "inconclusive",
        "pool",
        "deadline",
        "runner-error",
        "interrupt",
        "sampler",
    }
)

# The pre-registration's error classes (its "Failures" table): the names of
# litellm's exception classes under the harness's retryable classes (transport)
# and under its model-fatal ones (request and account). A record keeps only
# the raised class's name.
TRANSPORT = frozenset(
    {
        "APIConnectionError",
        "APIError",
        "APIResponseValidationError",
        "BadGatewayError",
        "InternalServerError",
        "JSONSchemaValidationError",
        "MidStreamFallbackError",
        "RateLimitError",
        "ServiceUnavailableError",
        "Timeout",
        "RequestWallTimeoutError",
    }
)
REQUEST = frozenset(
    {
        "BadRequestError",
        "ContentPolicyViolationError",
        "ContextWindowExceededError",
        "ImageFetchError",
        "InvalidRequestError",
        "LiteLLMUnknownProvider",
        "RejectedRequestError",
        "UnprocessableEntityError",
        "UnsupportedParamsError",
    }
)
ACCOUNT = frozenset({"AuthenticationError", "PermissionDeniedError", "NotFoundError"})
# A timeout on the escalated request, the one asking for the escalation
# ceiling after a truncated turn, is the model's long generation timing out.
TIMEOUTS = frozenset({"Timeout", "RequestWallTimeoutError"})
HOST_ENGINE = frozenset({"MemoryError", "OSError"})
RERUN = frozenset({"provider", "host", "none", "operator"})
FINISHED = frozenset({"complete", "incomplete", "turn_limit"})
# Classes decided without the host evidence: they come before host trouble.
EARLY = frozenset({"operator", "harness", "ceiling", "none"})

REQUIRED = (
    "preregistration",
    "frozen_sha256",
    "runs",
    "stage",
    "board",
    "engine",
    "eligible_pool",
    "draw_order",
    "arms",
    "frontier_arms",
    "treatment_harness",
    "run_commit",
    "caps",
    "reserves",
    "overall_cap",
    "spent_before",
    "workers",
    "anchor_command",
)


# ---------------------------------------------------------------- streams


def master_seed(frozen_sha256: str) -> int:
    if not re.fullmatch(r"[0-9a-f]{64}", frozen_sha256 or ""):
        raise ValueError(f"not a sha256: {frozen_sha256!r}")
    return int(frozen_sha256[:16], 16)


def stream(master: int, name: str) -> np.random.Generator:
    key = int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big")
    return np.random.default_rng(np.random.SeedSequence(master, spawn_key=(key,)))


def draw(master: int, pool_ids: list[str], n: int | None = None) -> list[str]:
    ids = np.array(sorted(pool_ids))
    size = HOUSEHOLDS if n is None else n
    return [
        str(s) for s in stream(master, "draw").choice(ids, size=size, replace=False)
    ]


def orders(
    master: int, model: str, draw_order: list[str], arms: tuple[str, ...]
) -> dict[str, list[str]]:
    """Each drawn household's arm order for a model, drawn for every household
    in draw order, so no order depends on which households run."""
    generator = stream(master, f"order/{model}")
    return {
        sid: [str(a) for a in generator.permutation(list(arms))] for sid in draw_order
    }


# ---------------------------------------------------------------- arms


def arm_string(label: str) -> str:
    """The harness's arm string for a design label (`TOOL_FEATURES` order)."""
    dropped = DROPPED[label]
    if dropped is None:
        return "pe"
    if not dropped:
        return "pe3"
    return "pe:" + "+".join(f for f in pilot.TOOL_FEATURES if f not in dropped)


def arm_profile(model: str, label: str) -> pilot.ModelProfile:
    """The treatment harness's profile for a model and design label; refused
    unless its calculator features are the ones the label registers."""
    profile = pilot.model_profile(
        model, arm=arm_string(label), prompt_version=PROMPT_VERSION
    )
    dropped = DROPPED[label]
    want = set() if dropped is None else set(pilot.TOOL_FEATURES) - set(dropped)
    if not profile.uses_calculator or set(profile.tool_features) != want:
        raise ValueError(
            f"{model}/{label}: the harness gives features "
            f"{sorted(profile.tool_features)}, not {sorted(want)}"
        )
    return profile


# ---------------------------------------------------------------- classes


def error_class(record: dict) -> str:
    return str(record.get("error") or "").split(":", 1)[0].strip()


def completed_turns(record: dict) -> list:
    return [t for t in record.get("turns") or [] if not t.get("truncated_and_retried")]


def call_failures(record: dict) -> tuple[list[str], list[str]]:
    """(the inconclusive tool failures, the model's engine exceptions) in its
    calls: a call's own error, and the errors in its results and in its
    explanations (the explain feature's trace of a variable)."""
    host, model = [], []
    for turn in record.get("turns") or []:
        for call in turn.get("calls") or []:
            result = call.get("result")
            if not isinstance(result, dict):
                continue
            error, message = result.get("error"), str(result.get("message") or "")
            name = message.split(":", 1)[0]
            if error == "timeout":
                host.append("tool timeout")
            elif error == "engine" and message.startswith("tool worker failed:"):
                host.append("tool worker failure")
            elif error == "engine":
                (host if name in HOST_ENGINE else model).append(name)
            for group in ("results", "explanations"):
                values = result.get(group)
                for value in values.values() if isinstance(values, dict) else ():
                    if isinstance(value, dict) and value.get("error"):
                        name = str(value["error"]).split(":", 1)[0]
                        (host if name in HOST_ENGINE else model).append(name)
    return host, model


def escalation_timed_out(record: dict) -> bool:
    """Whether the attempt ended on a timeout of its escalated request: the
    harness records a truncated turn, then asks again at the escalation
    ceiling, and an error there leaves the truncated turn last."""
    turns = record.get("turns") or []
    return (
        record.get("status") == "provider_error"
        and error_class(record) in TIMEOUTS
        and bool(turns)
        and bool(turns[-1].get("truncated_and_retried"))
    )


def classify(record: dict, start: float, end: float, host) -> tuple[str, str]:
    """(class, detail) of one attempt. In order of precedence: operator (an
    account class or insufficient_quota); harness (a request class with no
    completed model turn yet); ceiling (budget_stop); none (no turn recorded:
    no model request returned, truncated or not); host (host trouble during
    the attempt); model (a timeout of the escalated request); provider (a
    transport class); model (a request class); inconclusive (any other
    provider error, any harness error, a tool timeout, a worker failure,
    MemoryError or OSError); otherwise ok, or model when the engine raised on
    a household the model built. `host` is None to decide only the classes
    before host."""
    status, error = record.get("status"), str(record.get("error") or "")
    name = error_class(record)
    returned = bool(record.get("turns"))
    completed = bool(completed_turns(record))
    if status == "provider_error" and (
        name in ACCOUNT or "insufficient_quota" in error
    ):
        return "operator", name
    if status == "provider_error" and name in REQUEST and not completed:
        return "harness", name
    if status == "budget_stop":
        return "ceiling", status
    if not returned:
        return "none", f"{status}: {name}" if name else str(status)
    trouble = host.trouble(start, end) if host is not None else None
    if trouble:
        return "host", trouble
    if status == "provider_error":
        if escalation_timed_out(record):
            return "model", f"{name} on the escalated request"
        if name in TRANSPORT:
            return "provider", name
        if name in REQUEST:
            return "model", name
        return "inconclusive", name or "provider_error"
    if status == "harness_error":
        return "inconclusive", error or "harness_error"
    tool, engine = call_failures(record)
    if tool:
        return "inconclusive", tool[0]
    if status not in FINISHED:
        return "inconclusive", f"status {status}"
    return ("model", engine[0]) if engine else ("ok", str(status))


def action(cls: str, attempt: int) -> str:
    if cls == "harness":
        return "stop"
    if cls == "ceiling":
        return "stopped"
    if cls in RERUN and attempt <= MAX_RERUNS:
        return "pause-rerun" if cls == "operator" else "rerun"
    return "stands"


def attempt_cost(record: dict) -> float:
    return float((record.get("totals") or {}).get("cost_usd") or 0.0)


_clock_lock = threading.Lock()
_clock_last = 0.0


def clock() -> float:
    """`time.time()`, never earlier than a time it gave before. The wall clock
    can step back by about 0.1 ms, even within a thread, and the run records order
    attempts, stops, admission decisions and the ceiling's crossing by the
    times this gives; each is taken under the lock that orders it."""
    global _clock_last
    with _clock_lock:
        _clock_last = max(time.time(), _clock_last)
        return _clock_last


# ---------------------------------------------------------------- host evidence


GUARD_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \[[^\]]*\] (.*)$")
POWER_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d{4}) ([^\t]*?)\s*\t")
GUARD_LOG = Path.home() / "Library/Logs/clamshell-guard.log"


def guard_times(line: str, zone: ZoneInfo) -> tuple[float, float] | None:
    """The earliest and latest instants a guard line's local time can be. They
    differ only within an hour that a change of offset repeats or skips: on
    2026-11-01, New York's 01:00-02:00 comes twice, and the guard's lines
    carry no offset."""
    match = GUARD_LINE.match(line)
    if not match:
        return None
    stamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    both = [stamp.replace(tzinfo=zone, fold=fold).timestamp() for fold in (0, 1)]
    return min(both), max(both)


def power_times(line: str) -> tuple[float, float] | None:
    """A power-log line's instant, twice (its time carries its offset)."""
    match = POWER_LINE.match(line)
    if not match:
        return None
    t = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S %z").timestamp()
    return t, t


def guard_spans(text: str, timezone: str, end: float) -> list:
    """Pauses: from a 'paused pids:' line to the next 'resumed pids:' line (or
    `end`), each from the earliest reading of its pause to the latest of its
    resume."""
    zone, spans, opened = ZoneInfo(timezone), [], None
    for line in text.splitlines():
        times = guard_times(line, zone)
        if times is None:
            continue
        what = GUARD_LINE.match(line).group(2)
        if "paused pids:" in what and opened is None:
            opened = times[0]
        elif "resumed pids:" in what and opened is not None:
            spans.append((opened, times[1], "guard pause"))
            opened = None
    if opened is not None:
        spans.append((opened, end, "guard pause"))
    return spans


def power_spans(text: str, end: float) -> list:
    """Sleeps: from a Sleep line to the next Wake or DarkWake line (or `end`)."""
    spans, opened = [], None
    for line in text.splitlines():
        times = power_times(line)
        if times is None:
            continue
        t = times[0]
        kind = POWER_LINE.match(line).group(2).strip()
        if kind == "Sleep" and opened is None:
            opened = t
        elif kind in ("Wake", "DarkWake") and opened is not None:
            spans.append((opened, t, "sleep"))
            opened = None
    if opened is not None:
        spans.append((opened, end, "sleep"))
    return spans


def excerpt(
    text: str,
    when: Callable[[str], tuple[float, float] | None],
    since: float,
    until: float,
):
    """The lines of a log that one reading of its time puts within [since,
    until]."""
    keep = []
    for line in text.splitlines():
        times = when(line)
        if times is not None and times[0] <= until and times[1] >= since:
            keep.append(line + "\n")
    return "".join(keep)


def memory_pressure() -> int | None:
    """`sysctl kern.memorystatus_vm_pressure_level`: 1 when normal on this host."""
    try:
        out = subprocess.run(
            ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return int(out.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def read_guard_log() -> str:
    """The guard's log; empty when there is none (the guard never paused
    anything). Any other error is raised, for the reader to try again."""
    try:
        return GUARD_LOG.read_text(errors="replace")
    except FileNotFoundError:
        return ""


def read_power_log() -> str:
    out = subprocess.run(
        ["pmset", "-g", "log"], capture_output=True, text=True, timeout=120, check=True
    )
    return out.stdout


def local_timezone() -> str:
    """The IANA name of the host's zone, which the guard log's times are in."""
    target = os.path.realpath("/etc/localtime")
    if "zoneinfo/" not in target:
        raise SystemExit(f"cannot tell the host's time zone from {target}")
    return target.split("zoneinfo/", 1)[1]


# The `prev` of the host log's first line.
HOST_SEED = hashlib.sha256(b"host-log.jsonl").hexdigest()


class HostEvidenceError(RuntimeError):
    """The guard's or the power log could not be read: a runner error."""


class HostLog:
    """The host log, written every `interval` seconds, and the host evidence an
    attempt's class reads: the guard's pauses, the power log's sleeps, the
    host log's gaps and its memory-pressure samples. A sample whose pressure
    could not be read is no sample: the silence around it is a gap."""

    def __init__(
        self,
        folder: Path,
        timezone: str | None = None,
        interval: float = SAMPLE_SECONDS,
        read_load: Callable[[], tuple] = os.getloadavg,
        read_pressure: Callable[[], int | None] = memory_pressure,
        read_guard: Callable[[], str] = read_guard_log,
        read_power: Callable[[], str] = read_power_log,
    ):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.timezone = timezone or local_timezone()
        ZoneInfo(self.timezone)  # refused here, not at the first pause
        self.interval = interval
        self._read_load, self._read_pressure = read_load, read_pressure
        self._read_guard, self._read_power = read_guard, read_power
        self._cond = threading.Condition()
        self._samples: list[tuple[float, int | None]] = []
        self._spans: list = []  # guard pauses and sleeps at the last refresh
        self._read_at = -math.inf
        self._refresh_lock = threading.Lock()
        self._stop = threading.Event()
        self.failure: str | None = None  # the sampler's last error
        self.failing_since: float | None = None  # failed samples since then
        self._head, self._lines = HOST_SEED, 0  # the log's hash chain
        self.start = time.time()
        self.written = self.start  # the last sample written
        self.end: float | None = None
        self._write_meta()
        self.sample()
        self._thread = threading.Thread(target=self._loop, name="host-log", daemon=True)
        self._thread.start()

    def _write_meta(self) -> None:
        meta = {"timezone": self.timezone, "start": self.start}
        if self.end is not None:
            meta["end"] = self.end
        write_json(self.folder / "host.json", meta)

    def sample(self) -> None:
        """One sample. A load or pressure the host would not give is written
        as null; a sample that cannot be written is the sampler's failure,
        and the silence it leaves is a gap."""
        try:
            load1, load5, load15 = self._read_load()
        except OSError:
            load1 = load5 = load15 = None
        pressure = self._read_pressure()
        with self._cond:
            t = time.time()
            line = {
                "time": t,
                "monotonic": time.monotonic(),
                "load1": load1,
                "load5": load5,
                "load15": load15,
                "pressure": pressure,
            }
            text = json.dumps({**line, "prev": self._head})
            try:
                with (self.folder / "host-log.jsonl").open("a") as handle:
                    handle.write(text + "\n")
            except OSError as error:
                self.failure = f"{type(error).__name__}: {error}"
                self.failing_since = self.failing_since or t
                return
            self._head, self._lines = line_sha(text), self._lines + 1
            self.written = t
            if pressure is None:
                self.failure = "no memory-pressure reading"
                self.failing_since = self.failing_since or t
            else:
                self.failure = None
                self.failing_since = None
            self._samples.append((t, pressure))
            self._cond.notify_all()

    def heads(self) -> dict:
        """The host log's line count and last line's sha256, for an anchor."""
        with self._cond:
            return {"lines": self._lines, "sha256": self._head}

    def dead(self) -> str | None:
        """Why the sampler is taken for dead: no good sample for
        SAMPLER_SILENCE seconds while its samples fail, or its thread gone.
        A host that slept or was paused is not this: its sampler failed
        nothing."""
        if self.end is None and not self._thread.is_alive():
            return "the sampler's thread ended"
        since = self.failing_since
        if since is not None and time.time() - since > SAMPLER_SILENCE:
            return f"samples failing since {since:.1f} ({self.failure})"
        return None

    def _loop(self) -> None:
        k = 1
        while not self._stop.wait(
            max(0.0, self.start + k * self.interval - time.time())
        ):
            try:
                self.sample()
            except Exception as error:  # the sampler runs on; watch() sees the silence
                self.failure = f"{type(error).__name__}: {error}"
                self.failing_since = self.failing_since or time.time()
            # After a stall, the next sample is the next tick, with no burst.
            k = max(k + 1, math.ceil((time.time() - self.start) / self.interval))

    def _good(self) -> list[float]:
        """The times of the samples with a pressure reading."""
        return [t for t, p in self._samples if p is not None]

    def settled(self, end: float) -> bool:
        """Whether every sample that could bear on an attempt ending at `end` is
        in: one later than the pressure window, or a silence longer than a
        gap (which is itself host trouble when it covers the attempt)."""
        with self._cond:
            good = self._good()
            latest = good[-1] if good else self.start
            return latest > end + PRESSURE_WINDOW or time.time() - latest > HOST_LOG_GAP

    def wait_settled(self, end: float) -> None:
        with self._cond:
            while not self.settled(end):
                self._cond.wait(timeout=min(self.interval, 5.0))

    def _read_logs(self) -> tuple[str, str]:
        """The guard's and the power log, read up to READ_TRIES times."""
        for attempt in range(READ_TRIES):
            try:
                return self._read_guard(), self._read_power()
            except (OSError, subprocess.SubprocessError) as error:
                failure = f"{type(error).__name__}: {error}"
                if attempt < READ_TRIES - 1:
                    time.sleep(READ_WAIT)
        raise HostEvidenceError(f"the guard's or the power log: {failure}")

    def refresh(self, after: float) -> None:
        """Read the guard's and the power log again unless read since `after`.
        A failed read keeps the last spans and tries again; HostEvidenceError
        after READ_TRIES."""
        with self._refresh_lock:
            if self._read_at > after:
                return
            now = time.time()
            since = self.start - EXCERPT_LEAD
            zone = ZoneInfo(self.timezone)
            guard_text, power_text = self._read_logs()
            guard = excerpt(guard_text, lambda x: guard_times(x, zone), since, now)
            power = excerpt(power_text, power_times, since, now)
            spans = guard_spans(guard, self.timezone, now) + power_spans(power, now)
            with self._cond:
                self._spans, self._read_at = spans, now

    def _evidence(self) -> tuple[list, list[float]]:
        """(spans, the times of samples above 1), as the report builds them
        from the archived logs, with a silence so far as an open gap."""
        with self._cond:
            spans = list(self._spans)
            times = self._good()
            pressure = [t for t, p in self._samples if p is not None and int(p) > 1]
        for a, b in zip([self.start] + times, times):
            if b - a > HOST_LOG_GAP:
                spans.append((a, b, "host log gap"))
        now = time.time() if self.end is None else self.end
        last = times[-1] if times else self.start
        if now - last > HOST_LOG_GAP:
            spans.append((last, now, "host log gap"))
        return spans, pressure

    def trouble(self, start: float, end: float) -> str | None:
        spans, pressure = self._evidence()
        for a, b, what in spans:
            if a <= end and b >= start:
                return what
        for t in pressure:
            if start - PRESSURE_WINDOW <= t <= end + PRESSURE_WINDOW:
                return "memory pressure"
        return None

    def describe(self, start: float, end: float) -> str:
        """The host evidence behind an attempt's host class, for its rerun's
        reason."""
        spans, _ = self._evidence()
        parts = [
            f"{what} {a:.1f}-{b:.1f}" for a, b, what in spans if a <= end and b >= start
        ]
        with self._cond:
            parts += [
                f"memory pressure {p} at {t:.1f}"
                for t, p in self._samples
                if int(p or 0) > 1
                and start - PRESSURE_WINDOW <= t <= end + PRESSURE_WINDOW
            ]
        return "; ".join(parts)

    def close(self) -> None:
        """A last sample, the run's end, and the guard's and power log's lines
        from a day before the run's start to its end. If the logs cannot be
        read, `host-error.txt` says why and the excerpts are not written: the
        report then has no host evidence to check against."""
        self._stop.set()
        self._thread.join(timeout=self.interval + 10)
        try:
            self.sample()
        except Exception as error:
            self.failure = f"{type(error).__name__}: {error}"
        with self._cond:
            self.end = time.time()
        self._write_meta()
        since, zone = self.start - EXCERPT_LEAD, ZoneInfo(self.timezone)
        try:
            guard_text, power_text = self._read_logs()
        except HostEvidenceError as error:
            (self.folder / "host-error.txt").write_text(f"{error}\n")
            return
        guard = excerpt(guard_text, lambda x: guard_times(x, zone), since, self.end)
        (self.folder / "clamshell-guard.log").write_text(guard)
        power = excerpt(power_text, power_times, since, self.end)
        (self.folder / "pmset.log").write_text(power)


# ---------------------------------------------------------------- spend


class Ceiling(pilot.Spend):
    """The hard ceiling over every model's spend: once the total reaches it,
    `exhausted` is true for good, which ends each conversation under way at
    its next turn and lets no attempt start."""

    def __init__(self, ceiling_usd: float, spent_before: float):
        super().__init__(ceiling_usd, spent_before)
        self.crossed_at: float | None = None
        self.closed = False  # the records are final: spend is no longer counted
        self.unrecorded_usd = 0.0  # spend after that, in no record

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    def charge(self, usd: float) -> bool:
        """Count `usd`, with the lock held; False, and the spend unrecorded,
        once the ledger has closed."""
        if self.closed:
            self.unrecorded_usd += usd
            return False
        self.spent_usd += usd
        if self.crossed_at is None and self.spent_usd >= self.budget_usd:
            self.crossed_at = clock()
        return True

    def add(self, usd: float | None) -> None:
        with self._lock:
            self.charge(float(usd or 0.0))

    def close(self, pending: list[dict] | None = None) -> list[dict]:
        """Close the ledger at the run's end: what the ceiling has counted is
        then what the records hold. Snapshot unresolved requests under the
        same lock: one finishing afterward cannot disappear from recovery."""
        with self._lock:
            self.closed = True
            return [item for item in pending or [] if item["thread"].is_alive()]

    def exhausted(self, reserve_usd: float = 0.0) -> bool:
        with self._lock:
            return self.crossed_at is not None


class AttemptSpend:
    """The hard ceiling as one attempt's conversation sees it. Every cost goes
    to the ceiling, and the attempt keeps its own total, so an attempt that
    raises still records what it spent. Once the attempt is abandoned at its
    deadline, the conversation ends `budget_stop` at its next turn, and what
    it spends after is kept apart as late spend. The attempt's totals and the
    ceiling's change under the ceiling's lock, so they always agree; once
    the ledger has closed, neither counts more."""

    def __init__(self, ceiling: Ceiling):
        self.ceiling = ceiling
        self.spent_usd = 0.0
        self.late_usd = 0.0
        self.abandoned = False

    def add(self, usd: float | None) -> None:
        usd = float(usd or 0.0)
        with self.ceiling.lock:
            if not self.ceiling.charge(usd):
                return
            if self.abandoned:
                self.late_usd += usd
            else:
                self.spent_usd += usd

    def exhausted(self, reserve_usd: float = 0.0) -> bool:
        return self.abandoned or self.ceiling.exhausted()

    def abandon(self) -> float:
        """Abandon the attempt; what it had spent."""
        with self.ceiling.lock:
            self.abandoned = True
            return self.spent_usd


# ---------------------------------------------------------------- files


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def write_json(path: Path, payload, indent: int | None = 1) -> str:
    """Write a file whole (to a temporary name, synced, then renamed); its
    sha256."""
    data = json.dumps(payload, indent=indent, default=str).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return sha256_bytes(data)


def chain_seed(frozen_sha256: str, model: str, name: str) -> str:
    """The `prev` of a log's first line: the log's place in the design."""
    return sha256_bytes(f"{frozen_sha256}/{model}/{name}".encode())


def line_sha(text: str) -> str:
    """A log line's hash, the next line's `prev`: its JSON, no newline."""
    return sha256_bytes(text.encode())


# ---------------------------------------------------------------- one model


@dataclass
class Attempt:
    label: str
    n: int
    start: float
    end: float
    record: dict
    cls: str = ""
    detail: str = ""
    reason: str = ""
    settled: bool = False  # classed with its pass's host evidence
    logged: bool = False  # its run-log line written


class AttemptDeadline(RuntimeError):
    """An attempt ran past ATTEMPT_DEADLINE and was abandoned."""


def converse_with_harness(
    lanes: "Lanes", sid: str, label: str, tool_call, spend: AttemptSpend
) -> dict:
    """One attempt: the treatment harness's conversation for the arm, under the
    hard ceiling."""
    board = lanes.run.board
    return pilot.run_household(
        board["scenarios"][sid],
        board["variables"][sid],
        tool_call,
        lanes.completion,
        spend,
        profile=lanes.profiles[label],
    )


class Lanes:
    """One model's two lanes: its admission, its attempts and its records."""

    def __init__(self, run: "Run", model: str, labels: tuple[str, ...], folders: dict):
        self.run, self.model, self.labels = run, model, labels
        design = run.design
        self.folder = Path(design["runs"]) / model
        self.households_dir = {
            label: self.folder / folders[label] / design["stage"] / "households"
            for label in labels
        }
        self.profiles = {label: arm_profile(model, label) for label in labels}
        self.cap = float(design["caps"][model])
        self.reserve = float(design["reserves"][model])
        self.orders = orders(run.master, model, run.draw_order, labels)
        self.cond = threading.Condition()
        self._log_lock = threading.Lock()
        self.state: dict[str, str] = {}  # household -> running, settling, finished
        self.spent: dict[str, float] = {}  # household -> its attempts' cost so far
        self.refused = False
        self.paused = False
        self.paused_at: float | None = None
        self.stopped = False
        self.inconclusive: dict[str, list[str]] = {}
        self.pool = None
        self._pool_lock = threading.Lock()
        self.completion = None
        self.manifest_sha256: str | None = None
        # Each log is a hash chain: a line's `prev` is the line before's sha256.
        self._heads = {
            name: chain_seed(design["frozen_sha256"], model, name)
            for name in ("run-log.jsonl", "admission-log.jsonl")
        }
        self._counts = {name: 0 for name in self._heads}
        # Attempts abandoned at their deadline, whose spend after it is logged.
        self.abandoned: list[dict] = []

    # The records.

    def households(self, lane: int) -> list[str]:
        return [
            sid
            for i, sid in enumerate(self.run.draw_order)
            if i % 2 == lane - 1 and sid not in self.run.no_output
        ]

    def write_line(self, line: dict, name: str = "run-log.jsonl") -> None:
        with self._log_lock:
            text = json.dumps({**line, "prev": self._heads[name]})
            self.folder.mkdir(parents=True, exist_ok=True)
            with (self.folder / name).open("a") as handle:
                handle.write(text + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._heads[name] = line_sha(text)
            self._counts[name] += 1

    def heads(self) -> dict:
        """Each log's line count and last line's sha256, for an anchor."""
        with self._log_lock:
            return {
                name: {"lines": self._counts[name], "sha256": self._heads[name]}
                for name in self._heads
            }

    def event(
        self, kind: str, reason: str, at: float | None = None, cause=None, **extra
    ) -> None:
        line = {"event": kind, "time": clock() if at is None else at, "reason": reason}
        if cause is not None:
            line["cause"] = cause
        self.write_line({**line, **extra})
        self.run.say(f"{self.model}: {kind} ({reason})")

    def attempt_line(self, sid: str, lane: int, a: Attempt, sha: str) -> None:
        self.write_line(
            {
                "household": sid,
                "arm": a.label,
                "lane": lane,
                "attempt": a.n,
                "start": a.start,
                "end": a.end,
                "status": a.record.get("status"),
                "class": a.cls,
                "action": action(a.cls, a.n),
                "sha256": sha,
            }
        )
        a.logged = True

    # Stops and pauses.

    def halted(self) -> bool:
        return self.stopped or self.run._failed.is_set() or self.run.ceiling.exhausted()

    def stop(
        self, reason: str, cause: str, kind: str = "stop", at: float | None = None
    ) -> None:
        """Stop the lanes. Every rule that stops them writes its own event,
        naming its cause."""
        if (kind, cause) != ("ceiling", "ceiling") and cause not in STOP_CAUSES:
            raise ValueError(f"no stop has the cause {cause!r}")
        with self.cond:
            self.stopped = True
            self.cond.notify_all()
            self.event(kind, reason, at, cause=cause)

    def resume(self, note: str, noted_at: float) -> bool:
        """A note may end only a pause it was written during; another lane's
        later operator failure cannot be cleared by the older note."""
        with self.cond:
            if not (self.paused and noted_at >= self.paused_at):
                return False
            self.paused = False
            self.cond.notify_all()
            self.event("resume", note)
            return True

    # One household.

    def admit(self, sid: str, lane: int) -> bool:
        with self.cond:
            while not self.halted() and (
                self.paused or "settling" in self.state.values()
            ):
                self.cond.wait(timeout=WAIT_SECONDS)
            # Taken under the ceiling's lock, so no decision follows the crossing.
            with self.run.ceiling.lock:
                if (
                    self.stopped
                    or self.run._failed.is_set()
                    or self.run.ceiling.crossed_at is not None
                ):
                    return False
                now = clock()
            finished = [h for h, s in self.state.items() if s == "finished"]
            spend = sum(self.spent[h] for h in finished)
            under_way = len(self.state) - len(finished) + 1
            ok = (
                not self.refused
                and spend + under_way * self.reserve <= self.cap + ADMISSION_SLACK
            )
            self.write_line(
                {
                    "household": sid,
                    "lane": lane,
                    "time": now,
                    "decision": "admit" if ok else "refuse",
                    "finished_spend": spend,
                    "under_way": under_way,
                    "reserve": self.reserve,
                    "cap": self.cap,
                },
                "admission-log.jsonl",
            )
            if ok:
                self.state[sid], self.spent[sid] = "running", 0.0
            else:
                self.refused = True
            self.cond.notify_all()
            return ok

    def start_attempt(self) -> float | None:
        """The attempt's start, or None when the lanes have stopped. Waits out a
        pause. The start is taken under the ceiling's lock, so no attempt
        starts after the crossing."""
        with self.cond:
            while self.paused and not self.halted():
                self.cond.wait(timeout=WAIT_SECONDS)
            with self.run.ceiling.lock:
                if (
                    self.stopped
                    or self.run._failed.is_set()
                    or self.run.ceiling.crossed_at is not None
                ):
                    return None
                return clock()

    def end_attempt(
        self,
        sid: str,
        label: str,
        n: int,
        start: float,
        record: dict,
        last: bool,
        deadline: bool = False,
        retained: list[Attempt] | None = None,
    ) -> Attempt:
        """The attempt's end. A class decided without the host evidence acts at
        once: an operator failure pauses the lanes, a harness failure stops
        them, before any other attempt can start; so does an attempt
        abandoned at its deadline."""
        with self.cond:
            end = clock()
            self.spent[sid] += attempt_cost(record)
            attempt = Attempt(label, n, start, end, record)
            if retained is not None:
                retained.append(attempt)  # recovery owns it before any event I/O
            cls, detail = classify(record, start, end, None)
            if cls in EARLY:
                attempt.cls, attempt.detail = cls, detail
            if cls == "operator":
                self.paused, self.paused_at = True, clock()
            if cls == "harness" or deadline:
                self.stopped = True
            if last:
                self.state[sid] = "settling"
            self.cond.notify_all()
            if cls == "operator":
                self.event(
                    "pause", f"{label}/{sid} attempt {n}: {detail}", at=self.paused_at
                )
            if cls == "harness":
                self.event(
                    "stop",
                    f"{label}/{sid}: a request class on the first request ({detail})",
                    cause="harness",
                )
            if deadline:
                self.event(
                    "stop",
                    f"{label}/{sid} attempt {n} ran past the attempt deadline "
                    f"of {ATTEMPT_DEADLINE:.0f} s",
                    cause="deadline",
                )
        return attempt

    def settle(self, sid: str, done: list[Attempt]) -> None:
        """Each attempt's class once the host evidence for the pass is in."""
        last = max(a.end for a in done)
        host = self.run.host
        host.wait_settled(last)
        host.refresh(after=last)
        stop = None
        for a in done:
            cls, detail = classify(a.record, a.start, a.end, host)
            if a.cls and a.cls != cls:
                raise RuntimeError(f"{a.label}/{sid}: class {a.cls} became {cls}")
            a.cls, a.detail, a.settled = cls, detail, True
            a.reason = (
                f"{detail}: {host.describe(a.start, a.end)}"
                if cls == "host"
                else detail
            )
            status = a.record.get("status")
            if cls == "inconclusive" and status in ("provider_error", "harness_error"):
                key = f"{status}: {error_class(a.record) or a.record.get('error')}"
                with self.cond:
                    seen = self.inconclusive.setdefault(key, [])
                    if sid not in seen:
                        seen.append(sid)
                    if len(seen) > INCONCLUSIVE_STOP and stop is None:
                        stop = f"{key} ended runs in {len(seen)} households"
        if stop:
            self.stop(stop, cause="inconclusive")

    def converse(self, sid: str, label: str, n: int) -> tuple[dict, bool]:
        """(the attempt's record, whether it was abandoned). The conversation
        runs in a thread of its own. One that raises leaves a harness-error
        record with the spend it counted; one still running at
        ATTEMPT_DEADLINE is abandoned with a harness-error record holding
        the spend so far, ends `budget_stop` at its next turn, and writes
        nothing."""
        profile = self.profiles[label]
        variables = self.run.board["variables"][sid]
        features = frozenset(profile.tool_features)
        spend = AttemptSpend(self.run.ceiling)

        def tool_call(arguments):
            message = (
                pilot.tool_call_frame(features, arguments) if features else arguments
            )
            return self.pool.call(message)

        box: dict = {}

        def work():
            try:
                box["record"] = self.run.converse(self, sid, label, tool_call, spend)
            except Exception as error:  # an attempt that left no record of its own
                box["error"] = error

        thread = threading.Thread(
            target=work, name=f"{self.model}-{sid}-{label}-{n}", daemon=True
        )
        thread.start()
        thread.join(timeout=ATTEMPT_DEADLINE)
        if thread.is_alive():
            spent = spend.abandon()
            with self.cond:
                self.abandoned.append(
                    {
                        "household": sid,
                        "arm": label,
                        "attempt": n,
                        "spend": spend,
                        "thread": thread,
                        "logged": 0.0,
                    }
                )
            error = AttemptDeadline(
                f"past the attempt deadline of {ATTEMPT_DEADLINE:.0f} s"
            )
            record = pilot.harness_error_record(sid, variables, profile, error)
            record["totals"]["cost_usd"] = spent
            return record, True
        if "error" in box:
            record = pilot.harness_error_record(sid, variables, profile, box["error"])
            record["totals"]["cost_usd"] = spend.spent_usd
            return record, False
        return box["record"], False

    def log_late(self, final: bool = False) -> None:
        """A `late-cost` event for each abandoned attempt that has ended (or,
        at the end of the run, for each one still running) with spend after
        its deadline not yet logged."""
        with self.cond:
            pending = list(self.abandoned)
        for item in pending:
            ended = not item["thread"].is_alive()
            late = item["spend"].late_usd
            if (ended or final) and late > item["logged"]:
                self.event(
                    "late-cost",
                    f"{item['arm']}/{item['household']} attempt {item['attempt']}: "
                    "spend after its deadline",
                    household=item["household"],
                    arm=item["arm"],
                    attempt=item["attempt"],
                    cost_usd=late - item["logged"],
                )
                item["logged"] = late
            if ended:
                with self.cond:
                    self.abandoned.remove(item)

    def ensure_pool(self, startup: bool = False) -> bool:
        """The model's pool, started again if it has lost every worker; False
        if it cannot be."""
        with self._pool_lock:
            if self.halted():
                return False
            if (
                self.pool is not None
                and self.pool.counters()["lost"] < self.run.workers
            ):
                return True
            old = self.pool
            start, outcome = clock(), "failed"
            if not startup:
                self.event(
                    "setup-start",
                    "engine pool restart",
                    at=start,
                    phase="restart",
                    start=start,
                )
            try:
                try:
                    self.pool = self.run.pool_factory(self)
                except RuntimeError as error:
                    self.run.say(
                        f"{self.model}: the engine pool did not start: {error}"
                    )
                    return False
                if old is not None:
                    self.run.say(
                        f"{self.model}: the engine pool lost every worker; "
                        "started again"
                    )
                    old.close()
                outcome = "stopped" if self.halted() else "ready"
                return outcome == "ready"
            finally:
                if not startup:
                    self.event(
                        "setup-end",
                        "engine pool restart",
                        phase="restart",
                        start=start,
                        outcome=outcome,
                    )

    def replace(self, sid: str, lane: int, previous: Attempt, entries: list) -> None:
        """Save the attempt a rerun replaces, before the rerun."""
        folder = self.households_dir[previous.label] / "attempts"
        name = f"{sid}-{previous.n}.json"
        sha = write_json(folder / name, previous.record)
        entries.append(
            {
                "n": previous.n,
                "file": f"attempts/{name}",
                "sha256": sha,
                "status": previous.record.get("status"),
                "class": previous.cls,
                "reason": previous.reason,
            }
        )
        self.attempt_line(sid, lane, previous, sha)

    def passes(
        self, sid: str, lane: int, attempts: dict, entries: dict, in_flight: Path
    ) -> None:
        """The household's arms in its drawn order, then its reruns in passes,
        each pass classed once its host evidence is in."""
        todo = [(1, label) for label in self.orders[sid]]
        while todo:
            done: list[Attempt] = []
            for i, (n, label) in enumerate(todo):
                if not self.ensure_pool():
                    if not self.halted():
                        self.stop("the engine pool could not be started again", "pool")
                    break
                start = self.start_attempt()
                if start is None:
                    break
                if n > 1:
                    self.replace(sid, lane, attempts[label][-1], entries[label])
                record, abandoned = self.converse(sid, label, n)
                a = self.end_attempt(
                    sid,
                    label,
                    n,
                    start,
                    record,
                    i == len(todo) - 1,
                    abandoned,
                    retained=attempts[label],
                )
                done.append(a)
                write_json(in_flight / f"{label}-{n}.json", record)
                self.run.say(
                    f"{self.model} lane {lane} {sid} {label} #{n}: "
                    f"{record.get('status')} ${attempt_cost(record):.4f} "
                    f"(total ${self.run.ceiling.spent_usd:.2f})"
                )
            if not done:
                break
            self.settle(sid, done)
            cut = len(done) < len(todo)
            todo = (
                []
                if cut or self.halted()
                else [
                    (a.n + 1, a.label)
                    for a in done
                    if a.n <= MAX_RERUNS and a.cls in RERUN
                ]
            )
            with self.cond:
                self.state[sid] = "running" if todo else "finished"
                self.cond.notify_all()

    def run_household(self, sid: str, lane: int) -> bool:
        """One household; False when the runner failed part way. Then every
        model stops, and the attempts that ended are classed (as `unsettled`
        when their host evidence cannot be read) and written before the lane
        ends."""
        attempts: dict[str, list[Attempt]] = {label: [] for label in self.orders[sid]}
        entries: dict[str, list[dict]] = {label: [] for label in self.orders[sid]}
        in_flight = self.folder / "in-flight" / sid
        failure = None
        try:
            self.passes(sid, lane, attempts, entries, in_flight)
        except Exception as error:
            self.run._failed.set()  # block starts while records are recovered
            failure = (
                f"runner error on {self.model} lane {lane} ({sid}): "
                f"{type(error).__name__}: {error}"
            )
            self.run.say(traceback.format_exc())
            pending = [a for mine in attempts.values() for a in mine if not a.settled]
            if pending:
                try:
                    self.settle(sid, pending)
                except Exception as again:
                    self.run.say(traceback.format_exc())
                    for a in pending:
                        a.cls, a.settled = "unsettled", True
                        a.detail = a.reason = (
                            f"unsettled: {type(again).__name__}: {again}"
                        )
        for label, mine in attempts.items():
            if mine and not mine[-1].logged:
                final = mine[-1]
                try:
                    sha = write_json(
                        self.households_dir[label] / f"{sid}.json",
                        {
                            **final.record,
                            "attempts": [
                                entry
                                for entry in entries[label]
                                if entry["n"] < final.n
                            ],
                        },
                    )
                    self.attempt_line(sid, lane, final, sha)
                except Exception as error:  # the other arms still get written
                    self.run._failed.set()
                    failure = failure or (
                        f"runner error writing {self.model} lane {lane} ({sid}): "
                        f"{type(error).__name__}: {error}"
                    )
                    self.run.say(traceback.format_exc())
        if failure is not None:
            self.run.stop_all(failure, cause="runner-error")
        with self.cond:
            self.state[sid] = "finished"
            self.cond.notify_all()
        if failure is None:
            shutil.rmtree(in_flight, ignore_errors=True)
        return failure is None

    def lane(self, lane: int) -> None:
        try:
            for sid in self.households(lane):
                if not self.admit(sid, lane) or not self.run_household(sid, lane):
                    return
        except Exception as error:  # a runner defect: every model stops
            self.run.say(traceback.format_exc())
            self.run.stop_all(
                f"runner error on {self.model} lane {lane}: "
                f"{type(error).__name__}: {error}",
                cause="runner-error",
            )

    def manifest(self) -> dict:
        board, design = self.run.board, self.run.design
        pe3 = arm_profile(self.model, "pe3")
        first = sorted(board["scenarios"])[0]

        def timeout(profile):
            built = pilot.build_initial_request(
                board["scenarios"][first], board["variables"][first], profile
            )
            return built[1].get("timeout")

        board_path = Path(design["board"])
        return {
            "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "git_head": pilot._git("rev-parse", "HEAD"),
            "git_dirty": bool(pilot._git("status", "--porcelain")),
            "script_sha256": sha256_file(Path(__file__)),
            "harness_sha256": sha256_file(Path(pilot.__file__)),
            "treatment_commit": TREATMENT_COMMIT,
            "versions": pilot._versions(),
            "fix_module": str(pilot.FIX_MODULE.relative_to(pilot.ROOT)),
            "fix_module_sha256": sha256_file(pilot.FIX_MODULE),
            "board": str(board_path),
            "board_engine": f"policyengine-us {pilot.board_engine(board_path)}",
            "board_reference_sha256": sha256_file(board_path / "reference_outputs.csv"),
            "model": self.model,
            "model_id": pe3.model_id,
            "api": pe3.api,
            "answer_contract": pe3.contract,
            "prompt_version": PROMPT_VERSION,
            "prompt_wording_sha256": pilot.prompt_wording_sha256(pe3),
            "request_timeout_seconds": timeout(pe3),
            "turn_cap": pilot.TOOL_TURN_CAP,
            "max_calculations_per_turn": pilot.MAX_CALCULATIONS_PER_TURN,
            "tool_timeout_seconds": pilot.TOOL_TIMEOUT_SECONDS,
            "arms": {
                label: {
                    "arm": arm_string(label),
                    "features": sorted(self.profiles[label].tool_features),
                }
                for label in self.labels
            },
            "arm_settings": {
                label: {
                    "tool_notice_sha256": hashlib.sha256(
                        profile.notice.encode()
                    ).hexdigest(),
                    **pilot.profile_treatment(profile),
                    "tool_version": profile.tool_version,
                    "request_timeout_seconds": timeout(profile),
                }
                for label, profile in self.profiles.items()
            },
            "folders": {
                label: str(path) for label, path in self.households_dir.items()
            },
            "cap_usd": self.cap,
            "reserve_usd": self.reserve,
            "overall_cap_usd": float(design["overall_cap"]),
            "ceiling_usd": self.run.ceiling.budget_usd,
            "spent_before_usd": float(design["spent_before"]),
            "lanes": {lane: self.households(lane) for lane in (1, 2)},
            "no_scored_output": sorted(self.run.no_output),
            "workers": self.run.workers,
            "attempt_deadline_seconds": ATTEMPT_DEADLINE,
            "anchor_seconds": ANCHOR_SECONDS,
            "anchor_command": list(design["anchor_command"]),
        }

    def summary(self) -> dict:
        records = []
        for label, folder in self.households_dir.items():
            for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
                records.append(json.loads(path.read_text()))
        lines = []
        path = self.folder / "run-log.jsonl"
        if path.exists():
            lines = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
        attempts = [x for x in lines if "event" not in x]
        count: dict[str, int] = {}
        for x in attempts:
            count[x["class"]] = count.get(x["class"], 0) + 1
        return {
            "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model": self.model,
            "households_finished": sorted(
                h for h, s in self.state.items() if s == "finished"
            ),
            "refused": self.refused,
            "stopped": self.stopped,
            "spent_usd": sum(self.spent.values()),
            "final_records": len(records),
            "attempts": len(attempts),
            "classes": dict(sorted(count.items())),
            "events": [x for x in lines if "event" in x],
            "tool_pool": self.pool.counters() if self.pool is not None else None,
            "abandoned_running": len(self.abandoned),
        }


# ---------------------------------------------------------------- the run


def default_pool(lanes: Lanes):
    return pilot.ToolPool(
        size=lanes.run.workers,
        board=Path(lanes.run.design["board"]),
        tool_features=frozenset(),
    )


def default_completion(profile: pilot.ModelProfile):
    from litellm import completion, responses

    return responses if profile.api == "responses" else completion


class Run:
    """The six models' lanes, the host log and the hard ceiling."""

    def __init__(
        self,
        design: dict,
        workers: int | None = None,
        models: tuple[str, ...] | None = None,
        converse: Callable = converse_with_harness,
        pool_factory: Callable = default_pool,
        completion_for: Callable = default_completion,
        host_factory: Callable | None = None,
        out=sys.stdout,
    ):
        self.design, self.out = design, out
        self.workers = int(design["workers"]) if workers is None else workers
        self.converse, self.pool_factory = converse, pool_factory
        self.completion_for = completion_for
        self.host_factory = host_factory or (lambda folder: HostLog(folder))
        self._say_lock = threading.Lock()
        self.master = master_seed(design["frozen_sha256"])
        self.draw_order = list(design["draw_order"])
        board_path = Path(design["board"])
        pilot.set_stated_engine(pilot.board_engine(board_path))
        self.board = pilot.load_board(board_path)
        scored = {str(s) for s in self.board["scored"]["scenario_id"]}
        self.no_output = {sid for sid in self.draw_order if sid not in scored}
        self.ceiling = Ceiling(
            float(design["overall_cap"]) + CEILING_MARGIN, float(design["spent_before"])
        )
        self.models = tuple(models or CHEAP + FRONTIER)
        self.lanes = {
            model: Lanes(
                self,
                model,
                ARMS if model in CHEAP else FRONTIER_ARMS,
                design["arms"] if model in CHEAP else design["frontier_arms"],
            )
            for model in self.models
        }
        self.host: HostLog | None = None
        self._ceiling_written = False
        self.interrupts = 0
        self.signalled: int | None = None  # set by the signal handler alone
        self._interrupted = False
        self._sampler_stopped = False
        self._failed = threading.Event()  # recovery blocks starts before stop I/O
        self._anchor_head = chain_seed(design["frozen_sha256"], "", "anchors.jsonl")
        self._anchored = -math.inf
        self._pushing = threading.Lock()
        self._next_anchor = -math.inf
        self._push: threading.Thread | None = None
        self._push_error: OSError | None = None
        self._push_pending: dict | None = None
        self._last_push_outcome: str | None = None

    def say(self, text: str) -> None:
        with self._say_lock:
            print(text, file=self.out, flush=True)

    def stop_all(
        self, reason: str, cause: str, kind: str = "stop", at: float | None = None
    ) -> None:
        # Set every state before the first fallible write; notify even if a
        # disk error prevents a model's event from being recorded.
        for lanes in self.lanes.values():
            with lanes.cond:
                lanes.stopped = True
                lanes.cond.notify_all()
        for lanes in self.lanes.values():
            try:
                lanes.event(kind, reason, at, cause=cause)
            except Exception:
                self.say(traceback.format_exc())

    # Anchors: the logs' chain heads, written and pushed outside the run.

    def _check_push_error(self) -> None:
        with self._pushing:
            error = self._push_error
        if error is not None:
            raise OSError(
                f"anchor push outcome could not be recorded: {error}"
            ) from error

    def anchor_due(self) -> bool:
        self._check_push_error()
        with self._pushing:
            return clock() >= self._next_anchor

    def anchor(self, wait: bool = False, push: bool = True) -> None:
        """Every log's chain head to `anchors.jsonl`, itself a chain, then the
        design's anchor command on a synced snapshot, in the background (one
        current worker at a time; an anchor whose push would wait is written
        but not pushed until the next). A snapshot is a copy, not a record,
        and its path is unique even if a push thread has to be abandoned.
        Each push's result goes to `anchor-pushes.jsonl`."""
        runs = Path(self.design["runs"])
        line = {
            "time": clock(),
            "models": {
                model: {**lanes.heads(), "manifest": lanes.manifest_sha256}
                for model, lanes in self.lanes.items()
            },
            "host-log.jsonl": self.host.heads() if self.host is not None else None,
            "prev": self._anchor_head,
        }
        text = json.dumps(line)
        with (runs / "anchors.jsonl").open("a") as handle:
            handle.write(text + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._anchor_head, self._anchored = line_sha(text), clock()
        with self._pushing:
            self._next_anchor = self._anchored + ANCHOR_SECONDS
        if not push:
            return  # a push-log failure still leaves the final local heads
        if self._push is not None and self._push.is_alive():
            if not wait:
                return
            self._join_push()
        snapshot = runs / f"anchors.{self._anchor_head}.push-snapshot.jsonl"
        tmp = snapshot.with_suffix(".tmp")
        with tmp.open("wb") as handle:
            handle.write((runs / "anchors.jsonl").read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, snapshot)
        with self._pushing:
            self._push_pending = {
                "anchor": self._anchor_head,
                "anchor_time": line["time"],
                "started": clock(),
            }
            self._last_push_outcome = None
        self._push = threading.Thread(
            target=self._push_anchor,
            args=(self._anchor_head, line["time"]),
            daemon=True,
        )
        self._push.start()
        if wait:
            self._join_push()

    def _join_push(self) -> None:
        """Bound the thread join and retire its outcome if it cannot end.
        Its command may survive; the helper's lock and prefix check protect
        the clone. Waiting for _pushing still assumes a responsive filesystem."""
        self._push.join(timeout=ANCHOR_PUSH_TIMEOUT + KILL_GRACE + 30)
        if self._push.is_alive():
            with self._pushing:
                pending = self._push_pending
            if pending is not None:
                self._record_push(
                    {
                        **pending,
                        "ended": clock(),
                        "outcome": "error",
                        "returncode": None,
                        "output": "the anchor push thread did not end after its time limit; "
                        "its command may still be running",
                    }
                )
        self._check_push_error()

    def _record_push(self, line: dict) -> None:
        """Claim one outcome under the push lock; a late worker cannot repeat it.
        The lock covers writing and fsync, so a wedged filesystem can delay
        supervision and retirement beyond the thread join's bound."""
        with self._pushing:
            pending = self._push_pending
            if pending is None or pending["anchor"] != line["anchor"]:
                return
            self._push_pending = None
            self._last_push_outcome = line["outcome"]
            if line["outcome"] != "success":
                self._next_anchor = min(
                    self._next_anchor, line["ended"] + ANCHOR_RETRY
                )
            try:
                path = Path(self.design["runs"]) / "anchor-pushes.jsonl"
                with path.open("a") as handle:
                    handle.write(json.dumps(line) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError as error:
                # A daemon's exception must reach the supervisor or final join.
                self._push_error = self._push_error or error
                return
        if line["outcome"] != "success":
            self.say(
                f"the anchor push failed ({line['outcome']}, "
                f"{line['returncode']}): {line['output']}"
            )

    def _push_anchor(self, head: str, anchor_time: float) -> None:
        """Push one immutable snapshot and record its bounded command's outcome."""
        runs = Path(self.design["runs"])
        command = [str(x) for x in self.design["anchor_command"]]
        command.append(str(runs / f"anchors.{head}.push-snapshot.jsonl"))
        with self._pushing:
            pending = self._push_pending
            if pending is None or pending["anchor"] != head:
                return
            started = pending["started"] = clock()
        try:
            child = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                stdout, stderr = child.communicate(timeout=ANCHOR_PUSH_TIMEOUT)
                outcome = "success" if child.returncode == 0 else "failed"
            except subprocess.TimeoutExpired:
                # The command is a session leader: git and ssh share its group.
                # Killing just the command leaves its push running after timeout.
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    stdout, stderr = child.communicate(timeout=KILL_GRACE)
                except subprocess.TimeoutExpired as error:
                    for pipe in (child.stdout, child.stderr):
                        if pipe is not None:
                            pipe.close()
                    stdout, stderr = error.output or b"", error.stderr or b""
                    if isinstance(stdout, bytes):
                        stdout = stdout.decode(errors="replace")
                    if isinstance(stderr, bytes):
                        stderr = stderr.decode(errors="replace")
                    stderr += "\npipes were held open after the kill"
                outcome = "timeout"
            code, text = child.returncode, (stdout + stderr)[-2000:]
        except (OSError, subprocess.SubprocessError) as error:
            code, outcome, text = None, "error", f"{type(error).__name__}: {error}"
        ended = clock()
        line = {
            "anchor": head,
            "anchor_time": anchor_time,
            "started": started,
            "ended": ended,
            "outcome": outcome,
            "returncode": code,
            "output": text,
        }
        self._record_push(line)

    # The main loop's work.

    def watch(self, anchor: bool = True) -> None:
        """The ceiling's events, an interrupt, a dead sampler, resumes after
        operator pauses, late spend and the anchors."""
        crossed = self.ceiling.crossed_at
        if crossed is not None and not self._ceiling_written:
            self._ceiling_written = True
            reason = (
                f"total spend ${self.ceiling.spent_usd:.2f} reached the hard ceiling "
                f"${self.ceiling.budget_usd:.2f}"
            )
            self.stop_all(reason, "ceiling", kind="ceiling", at=crossed)
        if self.signalled is not None and not self._interrupted:
            self._interrupted = True
            self.say(
                f"signal {self.signalled}: stopping every model's lanes; "
                "the conversations under way finish"
            )
            self.stop_all(f"operator stop (signal {self.signalled})", "interrupt")
        dead = self.host.dead() if self.host is not None else None
        if dead and not self._sampler_stopped:
            self._sampler_stopped = True
            self.stop_all(f"the host log stopped: {dead}", "sampler")
        for lanes in self.lanes.values():
            path = lanes.folder / "RESUME.json"
            if not path.exists():
                continue
            try:
                note = json.loads(path.read_text())
            except (OSError, ValueError):
                continue  # still being written
            stamp = f"{time.time():.3f}"
            if lanes.resume(
                note.get("note") or "resumed", float(note.get("time") or 0.0)
            ):
                path.rename(lanes.folder / f"resume-{stamp}.json")
            else:
                # Written before the pause it would end, or with no pause.
                path.rename(lanes.folder / f"resume-ignored-{stamp}.json")
                self.say(f"{lanes.model}: a resume written before any pause, ignored")
        for lanes in self.lanes.values():
            lanes.log_late()
        if anchor and self.anchor_due():
            self.anchor()

    def execute(self) -> None:
        runs = Path(self.design["runs"])
        starting, threads = {}, []
        setup_open = set()
        try:
            self.host = self.host_factory(runs / "host")
            ready, failures = {}, {}
            startup = clock()
            for lanes in self.lanes.values():
                lanes.event(
                    "setup-start",
                    "run startup",
                    at=startup,
                    phase="startup",
                    start=startup,
                )
                setup_open.add(lanes.model)
            for model, lanes in self.lanes.items():
                self.watch(anchor=False)
                lanes.completion = self.completion_for(lanes.profiles["pe3"])
                stamp = time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())
                lanes.manifest_sha256 = write_json(
                    lanes.folder / f"manifest-{stamp}.json", lanes.manifest(), indent=2
                )
                # A model whose lanes never decide still has both logs.
                for name in ("run-log.jsonl", "admission-log.jsonl"):
                    (lanes.folder / name).touch()

            def start_pool(model, lanes):
                try:
                    ready[model] = lanes.ensure_pool(startup=True)
                except Exception as error:
                    failures[model] = error
                    self._failed.set()

            for model, lanes in self.lanes.items():
                self.watch()
                if lanes.halted():
                    continue
                starting[model] = threading.Thread(
                    target=start_pool, args=(model, lanes), daemon=True
                )
                starting[model].start()
            while any(t.is_alive() for t in starting.values()):
                self.watch()
                for thread in starting.values():
                    thread.join(timeout=0.5 / len(starting))
            self.watch()
            for model, lanes in self.lanes.items():
                outcome = (
                    "failed"
                    if model in failures
                    else "stopped"
                    if lanes.halted()
                    else "ready"
                    if ready.get(model)
                    else "failed"
                )
                lanes.event(
                    "setup-end",
                    "run startup",
                    phase="startup",
                    start=startup,
                    outcome=outcome,
                )
                setup_open.discard(model)
                if outcome == "failed" and model not in failures:
                    lanes.stop("the engine pool could not be started", "pool")
            if failures:
                raise next(iter(failures.values()))
            threads = []
            for model, lanes in self.lanes.items():
                for lane in (1, 2):
                    self.watch()
                    with lanes.cond:
                        if lanes.halted() or self.signalled is not None:
                            continue
                        thread = threading.Thread(
                            target=lanes.lane,
                            args=(lane,),
                            name=f"{model}-{lane}",
                            daemon=True,
                        )
                        thread.start()
                        threads.append(thread)
            while any(t.is_alive() for t in threads):
                self.watch()
                for t in threads:
                    t.join(timeout=0.5 / len(threads))
            self.watch()
        except Exception as error:
            self._failed.set()
            # Supervisors finish their bounded attempts and recovery before
            # the ledger, host and final anchor can close underneath them.
            for lanes in self.lanes.values():
                with lanes.cond:
                    lanes.cond.notify_all()
            for thread in [*starting.values(), *threads]:
                while thread.is_alive():
                    thread.join(timeout=WAIT_SECONDS)
                    try:
                        self.watch(anchor=False)
                    except Exception:
                        self.say(traceback.format_exc())
            for model in setup_open:
                try:
                    self.lanes[model].event(
                        "setup-end",
                        "run startup",
                        phase="startup",
                        start=startup,
                        outcome="failed",
                    )
                except Exception:
                    self.say(traceback.format_exc())
            self.stop_all(
                f"runner error: {type(error).__name__}: {error}", "runner-error"
            )
            raise
        finally:
            self.finish()

    def finish(self) -> None:
        """One join deadline, then close pools and host before closing the
        ledger. Its final late costs, crossings and signals precede the last
        anchor. An unresolved request makes future spend unknowable: record
        it explicitly, with a runner-error stop, rather than claim it settled.
        Retry the final push up to three times per set of heads, waiting
        ANCHOR_RETRY after each failed try ends. Then ignore signals and check
        once more for a first signal needing coverage. Signals during the
        resulting re-anchoring are ignored, including a second interrupt."""
        errors = []

        def attempt(work):
            try:
                work()
                return True
            except Exception as error:
                errors.append(error)
                self._failed.set()
                self.say(traceback.format_exc())
                self.stop_all(
                    f"runner error during cleanup: {type(error).__name__}: {error}",
                    "runner-error",
                )
                return False

        until = time.monotonic() + LATE_JOIN
        for lanes in self.lanes.values():
            for item in list(lanes.abandoned):
                while item["thread"].is_alive() and time.monotonic() < until:
                    item["thread"].join(
                        timeout=min(WAIT_SECONDS, max(0.0, until - time.monotonic()))
                    )
                    attempt(lambda: self.watch(anchor=False))
        for lanes in self.lanes.values():
            if lanes.pool is not None:
                attempt(lanes.pool.close)
        if self.host is not None:
            attempt(self.host.close)
        pending = []
        for lanes in self.lanes.values():
            with lanes.cond:
                pending.extend({**item, "lanes": lanes} for item in lanes.abandoned)
        unresolved = self.ceiling.close(pending)
        for lanes in self.lanes.values():
            attempt(lambda: lanes.log_late(final=True))
        for item in unresolved:
            attempt(
                lambda: item["lanes"].event(
                    "late-unresolved",
                    "request unresolved when the ledger closed; "
                    "future spend is unrecorded",
                    household=item["household"],
                    arm=item["arm"],
                    attempt=item["attempt"],
                    outcome="unresolved-at-ledger-close",
                    counted_usd=item["spend"].spent_usd + item["spend"].late_usd,
                )
            )
        if unresolved:
            self._failed.set()
            self.stop_all(
                f"{len(unresolved)} abandoned requests unresolved at ledger close; "
                "future spend is unrecorded",
                "runner-error",
            )
        # A first signal can also arrive while the final push is running.
        while True:
            attempt(lambda: self.watch(anchor=False))
            for lanes in self.lanes.values():
                stamp = time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())
                attempt(
                    lambda: write_json(
                        lanes.folder / f"run-summary-{stamp}.json",
                        lanes.summary(),
                        indent=2,
                    )
                )
            for push_try in range(FINAL_PUSH_TRIES):
                if push_try:
                    time.sleep(ANCHOR_RETRY)
                if not attempt(lambda: self.anchor(wait=True)):
                    attempt(lambda: self.watch(anchor=False))
                    # The error handler appended stops after that snapshot. Keep
                    # them covered locally even if pushing cannot be recorded.
                    try:
                        self.anchor(push=False)
                    except Exception as error:
                        errors.append(error)
                        self.say(traceback.format_exc())
                    break
                if self._last_push_outcome == "success":
                    break
            if self.signalled is not None and not self._interrupted:
                continue
            self._ignore_signals()
            if self.signalled is not None and not self._interrupted:
                continue
            break
        if errors:
            raise errors[0]

    def _ignore_signals(self) -> None:
        """Close signal delivery before the last check; the process is ending."""
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)

    def interrupt(self, signum, frame) -> None:
        """The signal handler. It only notes the signal; the main loop stops
        every model's lanes. A second signal exits at once while this handler
        is installed; cleanup ignores signals before its final check."""
        self.interrupts += 1
        if self.interrupts > 1:
            os._exit(130)
        self.signalled = signum


# ---------------------------------------------------------------- before a run


def host_power() -> tuple[bool, bool]:
    """(on AC power, lid open)."""
    batt = subprocess.run(
        ["pmset", "-g", "batt"], capture_output=True, text=True
    ).stdout
    lid = subprocess.run(
        ["ioreg", "-r", "-k", "AppleClamshellState", "-d", "1"],
        capture_output=True,
        text=True,
    ).stdout
    return "'AC Power'" in batt, '"AppleClamshellState" = No' in lid


def preflight(design: dict, models: tuple[str, ...]) -> list[str]:
    """What stops the run from starting."""
    missing = [k for k in REQUIRED if k not in design]
    if missing:
        return [f"the design has no {', '.join(missing)}"]
    problems = []
    command = design["anchor_command"]
    if (
        not isinstance(command, list)
        or not command
        or shutil.which(str(command[0])) is None
    ):
        problems.append(f"the anchor command {command!r} is not a command here")
    if design.get("stated_engine_overrides"):
        problems.append("the confirmatory run states the board's engine: no overrides")
    if sha256_file(Path(design["preregistration"])) != design["frozen_sha256"]:
        problems.append("the frozen copy does not hash to frozen_sha256")
    pool = design["eligible_pool"]
    if sha256_file(Path(pool["path"])) != pool["sha256"]:
        problems.append("the eligible pool does not hash as frozen")
    else:
        ids = [e["id"] for e in json.loads(Path(pool["path"]).read_text())]
        if draw(master_seed(design["frozen_sha256"]), ids) != list(
            design["draw_order"]
        ):
            problems.append(
                "the draw, recomputed from the stream 'draw', is not the design's"
            )
    head, dirty = pilot._git("rev-parse", "HEAD"), pilot._git("status", "--porcelain")
    if head != design["run_commit"] or dirty:
        problems.append(
            f"the runner is at {head[:12]} (dirty {bool(dirty)}), "
            "not the run commit, clean"
        )
    changed = subprocess.run(
        [
            "git",
            "-C",
            str(pilot.ROOT),
            "diff",
            "--quiet",
            TREATMENT_COMMIT,
            "HEAD",
            "--",
            *TREATMENT_PATHS,
        ]
    ).returncode
    if changed:
        problems.append(f"the treatment's code differs from {TREATMENT_COMMIT[:12]}'s")
    import policybench

    places = [Path(p).resolve() for p in policybench.__path__]
    if pilot.ROOT != ROOT or not all(p.is_relative_to(ROOT) for p in places):
        problems.append(
            f"the harness ({pilot.__file__}) or policybench ({places}) is not "
            "this checkout's"
        )
    harness = design["treatment_harness"]
    harness_head = subprocess.run(
        ["git", "-C", harness, "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    if harness_head != TREATMENT_COMMIT:
        problems.append(
            f"the treatment harness is at {harness_head[:12]}, "
            f"not {TREATMENT_COMMIT[:12]}"
        )
    board = Path(design["board"])
    engine = pilot.board_engine(board)
    if f"policyengine-us {engine}" != design["engine"]:
        problems.append(
            f"the board's engine {engine} is not the design's {design['engine']}"
        )
    installed = pilot._versions()["policyengine-us"]
    if installed != engine:
        problems.append(f"policyengine-us {installed} is installed, not {engine}")
    if set(design["arms"]) != set(ARMS) or set(design["frontier_arms"]) != set(
        FRONTIER_ARMS
    ):
        problems.append("the design's arms are not the registered ones")
    for name in ("arms", "frontier_arms"):
        if len(set(design[name].values())) != len(design[name]):
            problems.append(f"two {name} share a folder")
    for model in models:
        if model not in design["caps"] or model not in design["reserves"]:
            problems.append(f"{model}: no cap or reserve")
        for label in ARMS if model in CHEAP else FRONTIER_ARMS:
            try:
                arm_profile(model, label)
            except (ValueError, SystemExit) as error:
                problems.append(str(error))
        key = pilot.provider_key(pilot.model_profile(model).model_id)
        if not os.environ.get(key):
            problems.append(f"{model}: {key} is not set")
        folder = Path(design["runs"]) / model
        if (folder / "run-log.jsonl").exists() or any(
            folder.glob("*/*/households/*.json")
        ):
            problems.append(f"{folder} already holds records; a run is never resumed")
    if (Path(design["runs"]) / "host" / "host-log.jsonl").exists():
        problems.append("the runs folder already holds a host log")
    ac, lid = host_power()
    if not (ac and lid):
        problems.append(
            f"the host is not on AC power with the lid open (AC {ac}, lid open {lid})"
        )
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the confirmatory stage")
    run.add_argument("design", type=Path)
    run.add_argument(
        "--workers", type=int, help="engine workers per model: the design's alone"
    )
    run.add_argument("--dry-run", action="store_true", help="check and print the plan")
    resume = sub.add_parser("resume", help="end an operator pause")
    resume.add_argument("design", type=Path)
    resume.add_argument("model")
    resume.add_argument("--note", default="the account was fixed")
    args = parser.parse_args(argv)
    design = json.loads(args.design.read_text())
    if args.command == "resume":
        folder = Path(design["runs"]) / args.model
        write_json(folder / "RESUME.json", {"time": time.time(), "note": args.note})
        print(f"{args.model}: resume requested; the runner resumes within a second")
        return 0
    if args.workers is not None and args.workers != design.get("workers"):
        print(
            f"The run cannot start: --workers {args.workers}, and the design "
            f"runs {design.get('workers')} engine workers per model."
        )
        return 1
    models = CHEAP + FRONTIER
    problems = preflight(design, models)
    pilot._require_engine(Path(design["board"]))
    if problems:
        print("The run cannot start:\n" + "\n".join(f"- {p}" for p in problems))
        return 1
    plan = Run(design)
    if args.dry_run:
        for model, lanes in plan.lanes.items():
            sizes = [len(lanes.households(lane)) for lane in (1, 2)]
            print(
                f"{model}: arms {', '.join(lanes.labels)}; lanes {sizes[0]} and "
                f"{sizes[1]} households; cap ${lanes.cap:.2f}, "
                f"reserve ${lanes.reserve:.2f}"
            )
        print(
            f"no scored output: {sorted(plan.no_output)}; hard ceiling "
            f"${plan.ceiling.budget_usd:.2f} "
            f"(${plan.ceiling.spent_usd:.2f} spent before)"
        )
        return 0
    signal.signal(signal.SIGINT, plan.interrupt)
    signal.signal(signal.SIGTERM, plan.interrupt)
    plan.execute()
    return 0


if __name__ == "__main__":
    sys.exit(main())
