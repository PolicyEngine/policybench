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
  the message a pool started with those features would send.
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
- **Failures.** Each attempt's class follows the pre-registration's table, in
  the precedence the report's ``classify`` uses, from its record and the host
  evidence for its start and end; its action follows from its class and its
  attempt number. An operator failure pauses the model's lanes until
  ``resume``. A harness failure stops them, and so does one inconclusive
  error that ends runs in more than five of the model's households. A
  replaced attempt is saved, before its rerun, as
  ``households/attempts/<household>-<n>.json``.
- **The host log.** Every 30 seconds: the time, the load average and the
  kernel's memory-pressure level. At the end, the guard's and the power log's
  lines from a day before the booking to its end. An attempt's class waits
  for its host evidence to be complete: a sample more than 60 seconds after
  the pass's last end, or no sample for more than 90 seconds.

The records' format is the confirmatory report's (its module docstring). The
report recomputes every class, action, order and admission decision from the
records, with its own copy of these rules; the study's differential test runs
this runner on fakes and checks that its records pass the report.

The runner runs the treatment harness's code. It refuses to start unless its
``tool_pilot_argon.py``, ``policybench`` package and fix module are the
treatment commit's (6b00a6f0), its tree is clean at the design's run commit,
the machine is on AC power with the lid open, and the runs folder holds no
records: a run is never resumed. An interrupt (SIGINT or SIGTERM) stops every
model's lanes with a stop event and lets the conversations under way end; a
second interrupt exits at once.
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
EXCERPT_LEAD = 86_400.0  # host logs are kept from a day before the booking
WAIT_SECONDS = 1.0  # how often a waiting lane looks again

# The pre-registration's error classes (its "Failures" table).
TRANSPORT = frozenset(
    {
        "APIConnectionError",
        "APIError",
        "APIResponseValidationError",
        "BadGatewayError",
        "InternalServerError",
        "RateLimitError",
        "ServiceUnavailableError",
        "Timeout",
        "RequestWallTimeoutError",
    }
)
REQUEST = frozenset(
    {
        "BadRequestError",
        "ContextWindowExceededError",
        "InvalidRequestError",
        "UnprocessableEntityError",
        "UnsupportedParamsError",
    }
)
ACCOUNT = frozenset({"AuthenticationError", "PermissionDeniedError", "NotFoundError"})
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
    calls."""
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
            for value in (result.get("results") or {}).values():
                if isinstance(value, dict) and value.get("error"):
                    name = str(value["error"]).split(":", 1)[0]
                    (host if name in HOST_ENGINE else model).append(name)
    return host, model


def classify(record: dict, start: float, end: float, host) -> tuple[str, str]:
    """(class, detail) of one attempt. In order of precedence: operator (an
    account class or insufficient_quota); harness (a request class with no
    model request yet returned); ceiling (budget_stop); none (no model request
    returned); host (host trouble during the attempt); provider (a transport
    class); model (a request class); inconclusive (any other provider error,
    any harness error, a tool timeout, a worker failure, MemoryError or
    OSError); otherwise ok, or model when the engine raised on a household the
    model built. `host` is None to decide only the classes before host."""
    status, error = record.get("status"), str(record.get("error") or "")
    name = error_class(record)
    reached = bool(completed_turns(record))
    if status == "provider_error" and (
        name in ACCOUNT or "insufficient_quota" in error
    ):
        return "operator", name
    if status == "provider_error" and name in REQUEST and not reached:
        return "harness", name
    if status == "budget_stop":
        return "ceiling", status
    if not reached:
        return "none", f"{status}: {name}" if name else str(status)
    trouble = host.trouble(start, end) if host is not None else None
    if trouble:
        return "host", trouble
    if status == "provider_error":
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


# ---------------------------------------------------------------- host evidence


GUARD_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \[[^\]]*\] (.*)$")
POWER_LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d{4}) ([^\t]*?)\s*\t")
GUARD_LOG = Path.home() / "Library/Logs/clamshell-guard.log"


def guard_time(line: str, zone: ZoneInfo) -> float | None:
    match = GUARD_LINE.match(line)
    if not match:
        return None
    stamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    return stamp.replace(tzinfo=zone).timestamp()


def power_time(line: str) -> float | None:
    match = POWER_LINE.match(line)
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S %z").timestamp()


def guard_spans(text: str, timezone: str, end: float) -> list:
    """Pauses: from a 'paused pids:' line to the next 'resumed pids:' line (or
    `end`)."""
    zone, spans, opened = ZoneInfo(timezone), [], None
    for line in text.splitlines():
        t = guard_time(line, zone)
        if t is None:
            continue
        what = GUARD_LINE.match(line).group(2)
        if "paused pids:" in what and opened is None:
            opened = t
        elif "resumed pids:" in what and opened is not None:
            spans.append((opened, t, "guard pause"))
            opened = None
    if opened is not None:
        spans.append((opened, end, "guard pause"))
    return spans


def power_spans(text: str, end: float) -> list:
    """Sleeps: from a Sleep line to the next Wake or DarkWake line (or `end`)."""
    spans, opened = [], None
    for line in text.splitlines():
        t = power_time(line)
        if t is None:
            continue
        kind = POWER_LINE.match(line).group(2).strip()
        if kind == "Sleep" and opened is None:
            opened = t
        elif kind in ("Wake", "DarkWake") and opened is not None:
            spans.append((opened, t, "sleep"))
            opened = None
    if opened is not None:
        spans.append((opened, end, "sleep"))
    return spans


def excerpt(text: str, when: Callable[[str], float | None], since: float, until: float):
    """The lines of a log stamped within [since, until]."""
    keep = []
    for line in text.splitlines():
        t = when(line)
        if t is not None and since <= t <= until:
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
    try:
        return GUARD_LOG.read_text(errors="replace")
    except OSError:
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


class HostLog:
    """The host log, written every `interval` seconds, and the host evidence an
    attempt's class reads: the guard's pauses, the power log's sleeps, the
    host log's gaps and its memory-pressure samples."""

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
        self.start = time.time()
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
        load1, load5, load15 = self._read_load()
        pressure = self._read_pressure()
        with self._cond:
            t = time.time()
            line = {
                "time": t,
                "load1": load1,
                "load5": load5,
                "load15": load15,
                "pressure": pressure,
            }
            with (self.folder / "host-log.jsonl").open("a") as handle:
                handle.write(json.dumps(line) + "\n")
            self._samples.append((t, pressure))
            self._cond.notify_all()

    def _loop(self) -> None:
        k = 1
        while not self._stop.wait(
            max(0.0, self.start + k * self.interval - time.time())
        ):
            self.sample()
            # After a stall, the next sample is the next tick, with no burst.
            k = max(k + 1, math.ceil((time.time() - self.start) / self.interval))

    def settled(self, end: float) -> bool:
        """Whether every sample that could bear on an attempt ending at `end` is
        in: one later than the pressure window, or a silence longer than a
        gap (which is itself host trouble when it covers the attempt)."""
        with self._cond:
            latest = self._samples[-1][0]
            return latest > end + PRESSURE_WINDOW or time.time() - latest > HOST_LOG_GAP

    def wait_settled(self, end: float) -> None:
        with self._cond:
            while not self.settled(end):
                self._cond.wait(timeout=min(self.interval, 5.0))

    def refresh(self, after: float) -> None:
        """Read the guard's and the power log again unless read since `after`."""
        with self._refresh_lock:
            if self._read_at > after:
                return
            now = time.time()
            since = self.start - EXCERPT_LEAD
            zone = ZoneInfo(self.timezone)
            guard = excerpt(
                self._read_guard(), lambda x: guard_time(x, zone), since, now
            )
            power = excerpt(self._read_power(), power_time, since, now)
            spans = guard_spans(guard, self.timezone, now) + power_spans(power, now)
            with self._cond:
                self._spans, self._read_at = spans, now

    def _evidence(self) -> tuple[list, list[float]]:
        """(spans, the times of samples above 1), as the report builds them
        from the archived logs, with a silence so far as an open gap."""
        with self._cond:
            spans = list(self._spans)
            times = [t for t, _ in self._samples]
            pressure = [t for t, p in self._samples if int(p or 0) > 1]
        for a, b in zip([self.start] + times, times):
            if b - a > HOST_LOG_GAP:
                spans.append((a, b, "host log gap"))
        now = time.time() if self.end is None else self.end
        if now - times[-1] > HOST_LOG_GAP:
            spans.append((times[-1], now, "host log gap"))
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
        """A last sample, the booking's end, and the guard's and power log's
        lines for the booking."""
        self._stop.set()
        self._thread.join(timeout=self.interval + 10)
        self.sample()
        with self._cond:
            self.end = time.time()
        self._write_meta()
        since, zone = self.start - EXCERPT_LEAD, ZoneInfo(self.timezone)
        guard = excerpt(
            self._read_guard(), lambda x: guard_time(x, zone), since, self.end
        )
        (self.folder / "clamshell-guard.log").write_text(guard)
        power = excerpt(self._read_power(), power_time, since, self.end)
        (self.folder / "pmset.log").write_text(power)


# ---------------------------------------------------------------- spend


class Ceiling(pilot.Spend):
    """The hard ceiling over every model's spend: once the total reaches it,
    `exhausted` is true for good, which ends each conversation under way at
    its next turn and lets no attempt start."""

    def __init__(self, ceiling_usd: float, spent_before: float):
        super().__init__(ceiling_usd, spent_before)
        self.crossed_at: float | None = None

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    def add(self, usd: float | None) -> None:
        with self._lock:
            self.spent_usd += float(usd or 0.0)
            if self.crossed_at is None and self.spent_usd >= self.budget_usd:
                self.crossed_at = time.time()

    def exhausted(self, reserve_usd: float = 0.0) -> bool:
        with self._lock:
            return self.crossed_at is not None


# ---------------------------------------------------------------- files


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def write_json(path: Path, payload, indent: int | None = 1) -> str:
    """Write a file whole (to a temporary name, then renamed); its sha256."""
    data = json.dumps(payload, indent=indent, default=str).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return sha256_bytes(data)


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


def converse_with_harness(lanes: "Lanes", sid: str, label: str, tool_call) -> dict:
    """One attempt: the treatment harness's conversation for the arm, under the
    hard ceiling."""
    board = lanes.run.board
    return pilot.run_household(
        board["scenarios"][sid],
        board["variables"][sid],
        tool_call,
        lanes.completion,
        lanes.run.ceiling,
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
        self.stopped = False
        self.inconclusive: dict[str, list[str]] = {}
        self.pool = None
        self._pool_lock = threading.Lock()
        self.completion = None

    # The records.

    def households(self, lane: int) -> list[str]:
        return [
            sid
            for i, sid in enumerate(self.run.draw_order)
            if i % 2 == lane - 1 and sid not in self.run.no_output
        ]

    def write_line(self, line: dict, name: str = "run-log.jsonl") -> None:
        with self._log_lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            with (self.folder / name).open("a") as handle:
                handle.write(json.dumps(line) + "\n")
                handle.flush()
                os.fsync(handle.fileno())

    def event(self, kind: str, reason: str, at: float | None = None) -> None:
        self.write_line(
            {"event": kind, "time": time.time() if at is None else at, "reason": reason}
        )
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

    # Stops and pauses.

    def halted(self) -> bool:
        return self.stopped or self.run.ceiling.exhausted()

    def stop(self, reason: str, kind: str = "stop", at: float | None = None) -> None:
        """Stop the lanes. Every rule that stops them writes its own event."""
        with self.cond:
            self.stopped = True
            self.event(kind, reason, at)
            self.cond.notify_all()

    def resume(self, note: str) -> None:
        with self.cond:
            if self.paused:
                self.paused = False
                self.event("resume", note)
                self.cond.notify_all()

    # One household.

    def admit(self, sid: str, lane: int) -> bool:
        with self.cond:
            while not self.halted() and (
                self.paused or "settling" in self.state.values()
            ):
                self.cond.wait(timeout=WAIT_SECONDS)
            if self.halted():
                return False
            now = time.time()
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
                if self.stopped or self.run.ceiling.crossed_at is not None:
                    return None
                return time.time()

    def end_attempt(
        self, sid: str, label: str, n: int, start: float, record: dict, last: bool
    ) -> Attempt:
        """The attempt's end. A class decided without the host evidence acts at
        once: an operator failure pauses the lanes, a harness failure stops
        them, before any other attempt can start."""
        with self.cond:
            end = time.time()
            self.spent[sid] += attempt_cost(record)
            attempt = Attempt(label, n, start, end, record)
            cls, detail = classify(record, start, end, None)
            if cls in EARLY:
                attempt.cls, attempt.detail = cls, detail
            if cls == "operator":
                self.paused = True
                self.event("pause", f"{label}/{sid} attempt {n}: {detail}")
            if cls == "harness":
                self.stopped = True
                self.event(
                    "stop",
                    f"{label}/{sid}: a request class on the first request ({detail})",
                )
            if last:
                self.state[sid] = "settling"
            self.cond.notify_all()
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
            a.cls, a.detail = cls, detail
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
            self.stop(stop)

    def converse(self, sid: str, label: str) -> dict:
        profile = self.profiles[label]
        board = self.run.board
        features = frozenset(profile.tool_features)

        def tool_call(arguments):
            message = (
                pilot.tool_call_frame(features, arguments) if features else arguments
            )
            return self.pool.call(message)

        try:
            return self.run.converse(self, sid, label, tool_call)
        except Exception as error:  # an attempt that left no record of its own
            return pilot.harness_error_record(
                sid, board["variables"][sid], profile, error
            )

    def ensure_pool(self) -> bool:
        """The model's pool, started again if it has lost every worker; False
        if it cannot be."""
        with self._pool_lock:
            if (
                self.pool is not None
                and self.pool.counters()["lost"] < self.run.workers
            ):
                return True
            old = self.pool
            try:
                self.pool = self.run.pool_factory(self)
            except RuntimeError as error:
                self.run.say(f"{self.model}: the engine pool did not start: {error}")
                return False
            if old is not None:
                self.run.say(
                    f"{self.model}: the engine pool lost every worker; started again"
                )
                old.close()
            return True

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

    def run_household(self, sid: str, lane: int) -> None:
        order = self.orders[sid]
        attempts: dict[str, list[Attempt]] = {label: [] for label in order}
        entries: dict[str, list[dict]] = {label: [] for label in order}
        in_flight = self.folder / "in-flight" / sid
        todo = [(1, label) for label in order]
        while todo:
            done: list[Attempt] = []
            for i, (n, label) in enumerate(todo):
                if not self.ensure_pool():
                    self.stop("the engine pool could not be started again")
                    break
                start = self.start_attempt()
                if start is None:
                    break
                if n > 1:
                    self.replace(sid, lane, attempts[label][-1], entries[label])
                record = self.converse(sid, label)
                a = self.end_attempt(
                    sid, label, n, start, record, last=i == len(todo) - 1
                )
                write_json(in_flight / f"{label}-{n}.json", record)
                attempts[label].append(a)
                done.append(a)
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
        for label, mine in attempts.items():
            if mine:
                final = mine[-1]
                sha = write_json(
                    self.households_dir[label] / f"{sid}.json",
                    {**final.record, "attempts": entries[label]},
                )
                self.attempt_line(sid, lane, final, sha)
        with self.cond:
            self.state[sid] = "finished"
            self.cond.notify_all()
        shutil.rmtree(in_flight, ignore_errors=True)

    def lane(self, lane: int) -> None:
        try:
            for sid in self.households(lane):
                if not self.admit(sid, lane):
                    return
                self.run_household(sid, lane)
        except Exception as error:  # a runner defect: this model stops, the rest run on
            self.run.say(traceback.format_exc())
            self.stop(f"runner error on lane {lane}: {type(error).__name__}: {error}")

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
        workers: int = 2,
        models: tuple[str, ...] | None = None,
        converse: Callable = converse_with_harness,
        pool_factory: Callable = default_pool,
        completion_for: Callable = default_completion,
        host_factory: Callable | None = None,
        out=sys.stdout,
    ):
        self.design, self.workers, self.out = design, workers, out
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

    def say(self, text: str) -> None:
        with self._say_lock:
            print(text, file=self.out, flush=True)

    def stop_all(self, reason: str) -> None:
        for lanes in self.lanes.values():
            lanes.stop(reason)

    def watch(self) -> None:
        """The ceiling's events, and resumes after operator pauses."""
        crossed = self.ceiling.crossed_at
        if crossed is not None and not self._ceiling_written:
            self._ceiling_written = True
            reason = (
                f"total spend ${self.ceiling.spent_usd:.2f} reached the hard ceiling "
                f"${self.ceiling.budget_usd:.2f}"
            )
            for lanes in self.lanes.values():
                lanes.stop(reason, kind="ceiling", at=crossed)
        for lanes in self.lanes.values():
            path = lanes.folder / "RESUME.json"
            if lanes.paused and path.exists():
                note = json.loads(path.read_text()).get("note") or "resumed"
                path.rename(lanes.folder / f"resume-{time.time():.0f}.json")
                lanes.resume(note)

    def execute(self) -> None:
        runs = Path(self.design["runs"])
        self.host = self.host_factory(runs / "host")
        try:
            starting = {}
            for model, lanes in self.lanes.items():
                lanes.completion = self.completion_for(lanes.profiles["pe3"])
                stamp = time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())
                write_json(
                    lanes.folder / f"manifest-{stamp}.json", lanes.manifest(), indent=2
                )
                # A model whose lanes never decide still has both logs.
                for name in ("run-log.jsonl", "admission-log.jsonl"):
                    (lanes.folder / name).touch()
                starting[model] = threading.Thread(
                    target=lanes.ensure_pool, daemon=True
                )
                starting[model].start()
            for thread in starting.values():
                thread.join()
            threads = [
                threading.Thread(
                    target=lanes.lane, args=(lane,), name=f"{model}-{lane}", daemon=True
                )
                for model, lanes in self.lanes.items()
                for lane in (1, 2)
            ]
            for thread in threads:
                thread.start()
            while any(t.is_alive() for t in threads):
                self.watch()
                for t in threads:
                    t.join(timeout=0.5 / len(threads))
            self.watch()
        finally:
            for model, lanes in self.lanes.items():
                stamp = time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())
                write_json(
                    lanes.folder / f"run-summary-{stamp}.json",
                    lanes.summary(),
                    indent=2,
                )
                if lanes.pool is not None:
                    lanes.pool.close()
            self.host.close()

    def interrupt(self, signum, frame) -> None:
        self.interrupts += 1
        if self.interrupts > 1:
            raise KeyboardInterrupt
        self.say(
            f"signal {signum}: stopping every model's lanes; "
            "the conversations under way end"
        )
        self.stop_all(f"operator stop (signal {signum})")


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
    run.add_argument("--workers", type=int, default=2, help="engine workers per model")
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
    models = CHEAP + FRONTIER
    problems = preflight(design, models)
    pilot._require_engine(Path(design["board"]))
    if problems:
        print("The run cannot start:\n" + "\n".join(f"- {p}" for p in problems))
        return 1
    plan = Run(design, workers=args.workers)
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
