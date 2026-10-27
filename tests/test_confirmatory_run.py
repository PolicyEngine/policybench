"""The confirmatory runner (scripts/confirmatory_run.py).

The runs here are fakes: a fake provider whose conversations a test plants,
a fake engine pool and a host log sampled every 20 ms, on a fake board. Each
run is checked by `run_problems`, which recomputes, from the files the runner
wrote and nothing else, every rule the run procedure states: the records and
their hashes, each attempt's class and action, the lanes and the schedule,
admission, pauses, stops and the ceiling. The study's differential test runs
the runner and checks its records with the confirmatory report itself.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import confirmatory_run as cr  # noqa: E402
import tool_pilot_argon as pilot  # noqa: E402

from policybench.scenarios import Person, Scenario  # noqa: E402

VARIABLES = ["snap", "federal_income_tax_before_refundable_credits"]
POOL = [f"h{i:02d}" for i in range(12)]
N_DRAW = 6
COST = 0.01
TZ = "America/New_York"
PREREG = "A frozen pre-registration for a test.\n"
ENGINE = "2.60.4"
# The harness times requests with the raw wall clock, which steps back by
# about 0.1 ms on this host, even within a thread; the report allows a second, as
# here, which also covers a small correction of the clock.
CLOCK_SLACK = 1.0
# The anchor command in a test: a copy of the anchors to the test's folder.
ANCHOR_SCRIPT = Path(__file__).resolve().parent / "fake_anchor.py"
# How far apart anchors and their triggers' stops may be in a test, on a
# loaded host.
ANCHOR_SLACK = 30.0
TRIGGER_BOUND = 5.0


# ---------------------------------------------------------------- streams


def test_the_master_seed_is_the_first_sixteen_hex_digits():
    sha = hashlib.sha256(b"x").hexdigest()
    assert cr.master_seed(sha) == int(sha[:16], 16)
    with pytest.raises(ValueError):
        cr.master_seed("not a sha")


def test_a_stream_is_keyed_by_its_name_alone():
    a = cr.stream(7, "order/m").integers(0, 1 << 30, 5)
    b = cr.stream(7, "order/m").integers(0, 1 << 30, 5)
    c = cr.stream(7, "order/n").integers(0, 1 << 30, 5)
    assert list(a) == list(b) and list(a) != list(c)
    key = int.from_bytes(hashlib.sha256(b"draw").digest()[:8], "big")
    want = np.random.default_rng(np.random.SeedSequence(7, spawn_key=(key,)))
    assert list(cr.stream(7, "draw").integers(0, 100, 8)) == list(
        want.integers(0, 100, 8)
    )


@settings(deadline=None)
@given(st.integers(0, (1 << 64) - 1), st.integers(1, 12))
def test_the_draw_is_seeded_and_without_replacement(master, n):
    got = cr.draw(master, list(reversed(POOL)), n=n)
    assert got == cr.draw(master, POOL, n=n)  # the pool is sorted first
    assert len(set(got)) == n and set(got) <= set(POOL)


def test_orders_are_permutations_drawn_for_every_household_in_draw_order():
    got = cr.orders(9, "m", POOL, cr.ARMS)
    assert list(got) == POOL
    assert all(sorted(o) == sorted(cr.ARMS) for o in got.values())
    generator = cr.stream(9, "order/m")
    assert got[POOL[0]] == [str(a) for a in generator.permutation(list(cr.ARMS))]
    # The first households' orders do not depend on the later ones.
    assert cr.orders(9, "m", POOL[:3], cr.ARMS) == {s: got[s] for s in POOL[:3]}


# ---------------------------------------------------------------- arms


def test_arm_strings_follow_the_harness_feature_order():
    assert cr.arm_string("pe") == "pe"
    assert cr.arm_string("pe3") == cr.arm_string("pe3-b") == "pe3"
    for label, dropped in cr.DROPPED.items():
        if dropped:
            kept = [f for f in pilot.TOOL_FEATURES if f not in dropped]
            assert cr.arm_string(label) == "pe:" + "+".join(kept)


@pytest.mark.parametrize("model", cr.CHEAP + cr.FRONTIER)
def test_each_arm_has_its_registered_features(model):
    for label in cr.ARMS if model in cr.CHEAP else cr.FRONTIER_ARMS:
        profile = cr.arm_profile(model, label)
        dropped = cr.DROPPED[label]
        want = set() if dropped is None else set(pilot.TOOL_FEATURES) - set(dropped)
        assert profile.uses_calculator and set(profile.tool_features) == want
        assert profile.prompt_version == cr.PROMPT_VERSION


def test_an_arm_whose_features_are_not_registered_is_refused(monkeypatch):
    # The harness builds an arm's features from its arm string: a string that
    # does not give the label's registered features is refused.
    monkeypatch.setattr(cr, "arm_string", lambda label: "pe:names+labels")
    with pytest.raises(ValueError, match="features"):
        cr.arm_profile("gpt-6-luna", "loo-flat")


def litellm_names(groups) -> set[str]:
    """The names of litellm's exception classes under any of `groups`."""
    import inspect

    import litellm

    found = set()
    for module in (litellm, litellm.exceptions):
        for obj in vars(module).values():
            if inspect.isclass(obj) and issubclass(obj, BaseException):
                if issubclass(obj, groups):
                    found.add(obj.__name__)
    return found


def test_the_error_classes_are_policybench_s():
    """A record keeps the raised class's name, and the harness groups classes
    by inheritance: so each list holds every litellm class under the
    harness's group."""
    from policybench import eval_no_tools as e

    fatal = litellm_names(e.MODEL_FATAL_ERRORS)
    retryable = litellm_names(e.RETRYABLE_PROVIDER_ERRORS) - fatal
    assert cr.REQUEST | cr.ACCOUNT == fatal
    assert cr.TRANSPORT - {"RequestWallTimeoutError"} == retryable
    assert "RequestWallTimeoutError" in {
        c.__name__ for c in e.RETRYABLE_PROVIDER_ERRORS
    }
    assert {"ContentPolicyViolationError", "RejectedRequestError"} <= cr.REQUEST
    assert not cr.REQUEST & cr.ACCOUNT
    assert not cr.TRANSPORT & (cr.REQUEST | cr.ACCOUNT)
    assert cr.TIMEOUTS <= cr.TRANSPORT


# ---------------------------------------------------------------- classes


def record(status="complete", error=None, turns=1, calls=(), truncated=False):
    """`truncated`: the record's last turn is a truncated one, its escalated
    request then failing (with `turns` - 1 completed turns before it)."""
    turn = {"calls": [{"result": r} for r in calls]}
    out = [dict(turn) for _ in range(turns)]
    if truncated:
        out = out[: max(turns - 1, 0)] + [{"truncated_and_retried": True}]
    return {"status": status, "error": error, "turns": out}


class AlwaysTrouble:
    def trouble(self, start, end):
        return "memory pressure"


CASES = [
    (record(), "ok"),
    (record("incomplete"), "ok"),
    (record("turn_limit"), "ok"),
    (record("provider_error", "RateLimitError: slow down"), "provider"),
    (record("provider_error", "BadRequestError: too long"), "model"),
    (record("provider_error", "BadRequestError: bad", turns=0), "harness"),
    (record("provider_error", "BadRequestError: x", truncated=True), "harness"),
    (record("provider_error", "BadRequestError: x", 2, truncated=True), "model"),
    (record("provider_error", "ContentPolicyViolationError: x", turns=0), "harness"),
    (record("provider_error", "ContentPolicyViolationError: x"), "model"),
    (record("provider_error", "RejectedRequestError: x", turns=0), "harness"),
    # The escalated request's timeout is the model's long generation.
    (record("provider_error", "Timeout: 300 s", truncated=True), "model"),
    (record("provider_error", "Timeout: 300 s", 3, truncated=True), "model"),
    (record("provider_error", "Timeout: 300 s"), "provider"),
    # A truncated return is a return: no longer `none`.
    (record("provider_error", "RateLimitError: x", truncated=True), "provider"),
    (
        record("provider_error", "ProviderEmpty: no choices", truncated=True),
        "inconclusive",
    ),
    (record("provider_error", "ProviderEmpty: no choices", turns=0), "none"),
    (record("provider_error", "JSONSchemaValidationError: x"), "provider"),
    (record("provider_error", "AuthenticationError: key", turns=0), "operator"),
    (record("provider_error", "RateLimitError: insufficient_quota"), "operator"),
    (record("provider_error", "ProviderEmpty: no choices"), "inconclusive"),
    (record("provider_error", "RateLimitError: x", turns=0), "none"),
    (
        record("harness_error", "RuntimeError: every tool worker was lost", turns=0),
        "none",
    ),
    (record("harness_error", "the tool pool had no worker"), "inconclusive"),
    (record("budget_stop"), "ceiling"),
    (record("budget_stop", turns=0), "ceiling"),
    (record(calls=[{"error": "timeout", "message": "slow"}]), "inconclusive"),
    (
        record(calls=[{"error": "engine", "message": "tool worker failed: EOF"}]),
        "inconclusive",
    ),
    (record(calls=[{"error": "engine", "message": "MemoryError: x"}]), "inconclusive"),
    (record(calls=[{"error": "engine", "message": "ValueError: no person"}]), "model"),
    (record(calls=[{"results": {"snap": {"error": "OSError: disk"}}}]), "inconclusive"),
    (record(calls=[{"results": {"snap": {"error": "KeyError: x"}}}]), "model"),
    # The explain feature's trace of a variable, which catches its own errors.
    (
        record(calls=[{"explanations": {"snap": {"error": "MemoryError: x"}}}]),
        "inconclusive",
    ),
    (
        record(calls=[{"explanations": {"snap": {"error": "OSError: disk"}}}]),
        "inconclusive",
    ),
    (record(calls=[{"explanations": {"snap": {"error": "KeyError: x"}}}]), "model"),
    (record(calls=[{"explanations": {"snap": {"value": 1.0}}}]), "ok"),
    (record("running"), "inconclusive"),
]


@pytest.mark.parametrize("rec, want", CASES)
def test_each_failure_takes_its_class(rec, want):
    assert cr.classify(rec, 0.0, 1.0, None)[0] == want


@pytest.mark.parametrize("rec, want", CASES)
def test_host_trouble_outranks_every_class_but_the_early_four(rec, want):
    got = cr.classify(rec, 0.0, 1.0, AlwaysTrouble())[0]
    assert got == (want if want in cr.EARLY else "host")


@pytest.mark.parametrize("rec, want", CASES)
def test_an_early_class_needs_no_host_evidence(rec, want):
    early = cr.classify(rec, 0.0, 1.0, None)[0]
    assert (early in cr.EARLY) == (want in cr.EARLY)


def test_actions_follow_the_class_and_the_attempt():
    for cls in ("ok", "model", "provider", "host", "none", "operator", "harness"):
        for n in (1, 2, 3):
            got = cr.action(cls, n)
            if cls == "harness":
                assert got == "stop"
            elif cls in ("provider", "host", "none") and n <= 2:
                assert got == "rerun"
            elif cls == "operator" and n <= 2:
                assert got == "pause-rerun"
            else:
                assert got == "stands"
    assert cr.action("ceiling", 1) == "stopped"
    assert cr.action("inconclusive", 1) == "stands"


# ---------------------------------------------------------------- host evidence


def guard_line(t: float, what: str) -> str:
    stamp = datetime.fromtimestamp(t, ZoneInfo(TZ)).strftime("%Y-%m-%d %H:%M:%S")
    return f"{stamp} [poll] lid closed on battery: {what} pids: 1 2"


def power_line(t: float, kind: str) -> str:
    stamp = datetime.fromtimestamp(t, ZoneInfo(TZ)).strftime("%Y-%m-%d %H:%M:%S %z")
    return f"{stamp} {kind:<20}\t{kind} due to a test"


def test_guard_pauses_and_power_sleeps_are_spans():
    t = 1_800_000_000.0
    guard = "\n".join(
        [
            guard_line(t, "paused"),
            guard_line(t + 10, "resumed"),
            "junk",
            guard_line(t + 20, "paused"),
        ]
    )
    assert cr.guard_spans(guard, TZ, end=t + 99) == [
        (t, t + 10, "guard pause"),
        (t + 20, t + 99, "guard pause"),
    ]
    power = "\n".join(
        [
            power_line(t, "Sleep"),
            power_line(t + 5, "DarkWake"),
            power_line(t + 7, "Sleep"),
        ]
    )
    assert cr.power_spans(power, end=t + 50) == [
        (t, t + 5, "sleep"),
        (t + 7, t + 50, "sleep"),
    ]


def test_an_excerpt_keeps_the_lines_stamped_in_its_window():
    t = 1_800_000_000.0
    text = "\n".join(guard_line(t + k, "paused") for k in (-5, 0, 5, 10)) + "\nx"
    zone = ZoneInfo(TZ)
    kept = cr.excerpt(text, lambda x: cr.guard_times(x, zone), t, t + 5)
    assert kept.splitlines() == [guard_line(t, "paused"), guard_line(t + 5, "paused")]


class Readers:
    """The host log's inputs, which a test can change while it runs."""

    def __init__(self):
        self.pressure = 1
        self.pressing = 0  # attempts under way that raise the pressure
        self.stall = 0.0
        self.guard: list[str] = []
        self.power: list[str] = []
        self.lock = threading.Lock()

    def read_pressure(self):
        with self.lock:
            stall, self.stall = self.stall, 0.0
        if stall:
            time.sleep(stall)
        return 2 if self.pressing else self.pressure

    def host(self, folder):
        return cr.HostLog(
            folder,
            timezone=TZ,
            interval=0.02,
            read_load=lambda: (1.0, 2.0, 3.0),
            read_pressure=self.read_pressure,
            read_guard=lambda: "\n".join(self.guard),
            read_power=lambda: "\n".join(self.power),
        )


def wait_for_samples(log: Path, enough, seconds: float = 5.0) -> None:
    """Wait until the host log's complete samples satisfy `enough`. A loaded
    host can stretch the 0.02 s sampler past any fixed sleep."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        text = log.read_text() if log.exists() else ""
        if enough([json.loads(x) for x in text.split("\n")[:-1]]):
            return
        time.sleep(0.01)


@pytest.fixture
def fast(monkeypatch):
    """Short evidence windows, with room for the shared host's scheduler.
    Intentional gaps scale with this bound; ordinary stalls must not turn
    an untouched fake run into a host-failure test."""
    monkeypatch.setattr(cr, "PRESSURE_WINDOW", 0.06)
    monkeypatch.setattr(cr, "HOST_LOG_GAP", 5.0)
    monkeypatch.setattr(cr, "WAIT_SECONDS", 0.005)
    monkeypatch.setattr(cr, "HOUSEHOLDS", N_DRAW)
    monkeypatch.setattr(cr, "SAMPLER_SILENCE", 1.0)
    monkeypatch.setattr(cr, "READ_WAIT", 0.01)
    monkeypatch.setattr(cr, "ANCHOR_SECONDS", 0.3)
    handlers = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    yield
    for signum, handler in handlers.items():
        signal.signal(signum, handler)


def test_the_host_log_samples_and_closes(tmp_path, fast):
    readers = Readers()
    host = readers.host(tmp_path)
    wait_for_samples(tmp_path / "host-log.jsonl", lambda samples: len(samples) >= 4)
    host.close()
    meta = json.loads((tmp_path / "host.json").read_text())
    samples = [
        json.loads(x) for x in (tmp_path / "host-log.jsonl").read_text().splitlines()
    ]
    assert meta["timezone"] == TZ and meta["start"] <= samples[0]["time"]
    assert samples[-1]["time"] <= meta["end"]
    assert len(samples) >= 4
    assert samples[0]["load1"] == 1.0 and samples[0]["pressure"] == 1
    times = [s["time"] for s in samples]
    assert times == sorted(times)


def test_pressure_near_an_attempt_is_host_trouble_once_settled(tmp_path, fast):
    readers = Readers()
    host = readers.host(tmp_path)
    start = time.time()
    readers.pressure = 2
    wait_for_samples(
        tmp_path / "host-log.jsonl",
        lambda samples: any(x["pressure"] == 2 for x in samples),
    )
    readers.pressure = 1
    end = time.time()
    host.wait_settled(end)
    assert host.settled(end)
    host.refresh(after=end)
    assert host.trouble(start, end) == "memory pressure"
    assert host.trouble(end + 1, end + 2) is None
    host.close()


def test_a_stalled_host_log_is_a_gap(tmp_path, fast):
    readers = Readers()
    host = readers.host(tmp_path)
    time.sleep(0.03)
    start = time.time()
    stall = cr.HOST_LOG_GAP + 0.3
    readers.stall = stall
    time.sleep(stall + 0.05)
    end = time.time()
    host.wait_settled(end)
    host.refresh(after=end)
    assert host.trouble(start, end) == "host log gap"
    host.close()


def test_guard_pauses_and_sleeps_reach_an_attempt_after_a_refresh(tmp_path, fast):
    readers = Readers()
    host = readers.host(tmp_path)
    start = time.time()
    readers.guard += [guard_line(start, "paused"), guard_line(start + 1, "resumed")]
    end = time.time()
    host.wait_settled(end)
    assert host.trouble(start, end) is None  # not read yet
    host.refresh(after=end)
    assert host.trouble(start, end) == "guard pause"
    readers.guard.clear()
    readers.power += [power_line(start, "Sleep"), power_line(start + 1, "Wake")]
    host.refresh(after=time.time())
    assert host.trouble(start, end) == "sleep"
    host.close()
    assert "Sleep" in (tmp_path / "pmset.log").read_text()


def test_a_failed_pressure_reading_is_no_sample(tmp_path, fast):
    """A sample with no pressure reading is written, but it is no sample: a
    failing reading under pressure would hide the evidence the rule reads,
    so the silence it leaves is a gap."""
    readers = Readers()
    host = readers.host(tmp_path)
    time.sleep(0.03)
    start = time.time()
    readers.pressure = None
    time.sleep(cr.HOST_LOG_GAP + 0.2)
    readers.pressure = 1
    end = time.time()
    host.wait_settled(end)
    host.refresh(after=end)
    assert host.trouble(start, end) == "host log gap"
    host.close()
    samples = [
        json.loads(x) for x in (tmp_path / "host-log.jsonl").read_text().splitlines()
    ]
    assert any(x["pressure"] is None for x in samples)
    folder_host = host_from_files(tmp_path)
    assert folder_host.trouble(start, end) == "host log gap"  # the report's reading


def test_the_host_log_is_a_hash_chain_with_a_monotonic_time(tmp_path, fast):
    readers = Readers()
    host = readers.host(tmp_path)
    time.sleep(0.1)
    host.close()
    path = tmp_path / "host-log.jsonl"
    assert chain_problems(path, cr.HOST_SEED) == []
    lines = path.read_text().splitlines()
    assert host.heads() == {"lines": len(lines), "sha256": cr.line_sha(lines[-1])}
    ticks = [json.loads(x)["monotonic"] for x in lines]
    assert ticks == sorted(ticks)


def test_a_failed_log_read_is_tried_again(tmp_path, fast):
    calls = []

    def power():
        calls.append(1)
        if len(calls) <= 2:
            raise subprocess.CalledProcessError(1, ["pmset"])
        return ""

    host = cr.HostLog(
        tmp_path,
        timezone=TZ,
        interval=0.02,
        read_load=lambda: (1.0, 2.0, 3.0),
        read_pressure=lambda: 1,
        read_guard=lambda: "",
        read_power=power,
    )
    host.refresh(after=time.time())
    assert len(calls) == 3  # two failures, then a read
    host.close()
    assert (tmp_path / "pmset.log").exists()


def test_logs_that_cannot_be_read_are_a_runner_error(tmp_path, fast):
    def power():
        raise subprocess.TimeoutExpired(["pmset"], 120)

    host = cr.HostLog(
        tmp_path,
        timezone=TZ,
        interval=0.02,
        read_load=lambda: (1.0, 2.0, 3.0),
        read_pressure=lambda: 1,
        read_guard=lambda: "",
        read_power=power,
    )
    with pytest.raises(cr.HostEvidenceError):
        host.refresh(after=time.time())
    host.close()
    assert "TimeoutExpired" in (tmp_path / "host-error.txt").read_text()
    assert not (tmp_path / "pmset.log").exists()


def test_a_sampler_whose_samples_fail_is_dead_after_its_silence(tmp_path, fast):
    readers = Readers()
    host = readers.host(tmp_path)
    assert host.dead() is None
    readers.pressure = None
    host.sample()
    time.sleep(cr.SAMPLER_SILENCE + 0.2)
    assert "samples failing since" in host.dead()
    readers.pressure = 1
    host.sample()
    assert host.dead() is None  # a good sample: alive again
    host.close()


# ---------------------------------------------------------------- the ceiling


def test_the_clock_never_goes_back(monkeypatch):
    monkeypatch.setattr(cr, "_clock_last", cr._clock_last)  # restored after
    base = time.time() + 1000.0
    readings = iter([base, base - 1e-4, base + 2e-4, base - 5.0, base + 3e-4])
    monkeypatch.setattr(time, "time", lambda: next(readings))
    assert [cr.clock() for _ in range(5)] == [
        base,
        base,
        base + 2e-4,
        base + 2e-4,
        base + 3e-4,
    ]


def test_a_backward_wall_clock_does_not_delay_a_due_anchor(monkeypatch):
    """Once the ordered clock reaches the due time, a wall-clock step cannot
    make the anchor not due again."""
    run = cr.Run.__new__(cr.Run)
    run._pushing = threading.Lock()
    run._push_error = None
    base = time.time() + 1000.0
    run._next_anchor = base
    monkeypatch.setattr(cr, "_clock_last", base - 1.0)
    readings = iter([base - 1.0, base + 1.0, base - 5.0])
    monkeypatch.setattr(time, "time", lambda: next(readings))
    assert [run.anchor_due() for _ in range(3)] == [False, True, True]


def test_the_anchor_interval_and_retry_wait_are_registered_durations():
    """paper/preregistration-draft.md:218: anchors every 15 minutes, and retries
    a minute after the failed push ends."""
    assert cr.ANCHOR_SECONDS == 900.0
    assert cr.ANCHOR_RETRY == 60.0


def test_a_wall_clock_that_steps_back_keeps_the_run_procedure(world, monkeypatch):
    """Every reading of the wall clock up to 0.2 ms early (steps back of up to
    0.1 ms seen on this host): the run's times still order its attempts,
    stops and decisions."""
    import random

    jitter, real = random.Random(7), time.time
    monkeypatch.setattr(time, "time", lambda: real() - jitter.uniform(0.0, 2e-4))
    w = world().execute()
    assert run_problems(w) == []
    for model in w.models:
        assert len(w.attempts(model)) == N_DRAW * len(labels_of(model))


def test_the_ceiling_crosses_at_its_amount_and_stays_crossed():
    ceiling = cr.Ceiling(1.0, 0.25)
    ceiling.add(0.5)
    assert not ceiling.exhausted() and ceiling.crossed_at is None
    ceiling.add(0.25)
    assert ceiling.exhausted() and ceiling.crossed_at is not None
    first = ceiling.crossed_at
    ceiling.add(None)
    assert ceiling.crossed_at == first and ceiling.spent_usd == pytest.approx(1.0)


def test_the_ceiling_ignores_a_reserve():
    # No conversation stops for a model's spend: only the ceiling stops one.
    assert not cr.Ceiling(1.0, 0.0).exhausted(reserve_usd=5.0)


# ---------------------------------------------------------------- fake runs


def scenario(sid: str) -> Scenario:
    i = POOL.index(sid)
    return Scenario(
        id=sid,
        state="CO",
        filing_status="single",
        adults=[Person(name="head", age=30 + i, employment_income=10_000.0 * (i + 1))],
        children=[],
    )


class FakePool:
    """An engine pool that answers every call and keeps what it was sent."""

    def __init__(self, lanes, fail: bool = False):
        if fail:
            raise RuntimeError("tool worker failed to start: a test")
        self.messages: list = []
        self.lost = 0
        self.closed = False

    def call(self, message):
        self.messages.append(message)
        return {"results": {"snap": {"values": {"spm": 1.0}}}}, 0.0

    def counters(self):
        return {"timeouts": 0, "crashes": 0, "lost": self.lost}

    def close(self):
        self.closed = True


class FakeProvider:
    """Conversations a test plants. specs[(model, label, household, n)] holds a
    record's `status` and `error`, `turns` (default 1), `cost` per turn,
    `sleep` per turn, `calls` (tool arguments, one call each, per turn),
    `pressure` (high pressure during the attempt), `stall` (a host-log stall,
    seconds), `guard` (a guard pause over the attempt), `resume_after`
    (seconds after which the operator resumes), `raise` (the conversation
    raises before its first turn), `raise_after` (it raises after its turns)
    and `check` (a function of the lanes, called first)."""

    def __init__(self, world, specs=None):
        self.world, self.specs = world, specs or {}
        self.count: dict = {}
        self.lock = threading.Lock()

    def __call__(self, lanes, sid, label, tool_call, spend):
        model = lanes.model
        with self.lock:
            n = self.count[(model, label, sid)] = (
                self.count.get((model, label, sid), 0) + 1
            )
        spec = self.specs.get((model, label, sid, n), {})
        readers = self.world.readers
        if spec.get("check"):
            spec["check"](lanes)
        if spec.get("raise"):
            raise RuntimeError("a test raised")
        if spec.get("pressure"):
            with readers.lock:
                readers.pressing += 1
            lanes.run.host.sample()  # the planted pressure is actually observed
        if spec.get("stall"):
            readers.stall = spec["stall"]
        start = time.time()
        rec = {
            "scenario_id": sid,
            "model": model,
            "arm": cr.arm_string(label),
            "variables": list(VARIABLES),
            "status": "running",
            "turns": [],
            "predictions": {v: 0.0 for v in VARIABLES},
        }
        for i in range(spec.get("turns", 1)):
            if spend.exhausted():
                rec["status"] = "budget_stop"
                break
            started = time.time()
            time.sleep(spec.get("sleep", 0.0))
            completed = time.time()
            cost = spec.get("cost", COST)
            spend.add(cost)
            turn = {
                "index": i,
                "request_started_at": started,
                "request_completed_at": completed,
                "total_cost_usd": cost,
                "calls": [],
            }
            for arguments in spec.get("calls", []):
                result, latency = tool_call(arguments)
                turn["calls"].append({"arguments": arguments, "result": result})
            rec["turns"].append(turn)
        if spec.get("raise_after"):
            raise RuntimeError("a test raised after spending")
        if rec["status"] == "running":
            rec["status"] = spec.get("status", "complete")
        if spec.get("error"):
            rec["error"] = spec["error"]
        if spec.get("guard"):
            readers.guard += [
                guard_line(math.floor(start) - 1, "paused"),
                guard_line(math.ceil(time.time()) + 1, "resumed"),
            ]
        if spec.get("stall"):
            time.sleep(spec["stall"] + 0.02)
        if spec.get("pressure"):
            with readers.lock:
                readers.pressing -= 1
        rec["totals"] = {"cost_usd": sum(t["total_cost_usd"] for t in rec["turns"])}
        if spec.get("resume_after") is not None:
            folder = lanes.folder

            def resume():
                with lanes.cond:
                    if (
                        not lanes.cond.wait_for(
                            lambda: lanes.paused or lanes.halted(), timeout=30
                        )
                        or not lanes.paused
                    ):
                        return
                time.sleep(spec["resume_after"])
                cr.write_json(
                    folder / "RESUME.json",
                    {"time": cr.clock(), "note": "fixed in a test"},
                )

            threading.Thread(target=resume, daemon=True).start()
        return rec


class World:
    """A fake board, design and run."""

    def __init__(
        self,
        tmp: Path,
        monkeypatch,
        specs=None,
        caps=None,
        reserve=7 * 3 * COST,
        overall_cap=100.0,
        spent_before=1.0,
        no_output=(),
        models=None,
        pool=FakePool,
    ):
        self.tmp = tmp
        prereg = tmp / "prereg.md"
        prereg.write_text(PREREG)
        frozen = cr.sha256_file(prereg)
        master = cr.master_seed(frozen)
        self.draw_order = cr.draw(master, POOL, n=N_DRAW)
        board_path = tmp / "board"
        board_path.mkdir()
        (board_path / "reference_outputs.csv").write_text(
            "scenario_id,variable,value\n"
        )
        self.no_output = set(no_output)
        scored = [
            (sid, v) for sid in POOL if sid not in self.no_output for v in VARIABLES
        ]
        self.board = {
            "scenarios": {sid: scenario(sid) for sid in POOL},
            "variables": {sid: list(VARIABLES) for sid in POOL},
            "scored": pd.DataFrame(scored, columns=["scenario_id", "variable"]),
        }
        monkeypatch.setattr(pilot, "load_board", lambda path: self.board)
        monkeypatch.setattr(pilot, "board_engine", lambda path=None: ENGINE)
        monkeypatch.setitem(
            pilot._STATED_ENGINE, "version", pilot._STATED_ENGINE["version"]
        )
        self.models = tuple(models or cr.CHEAP + cr.FRONTIER)
        budget_models = tuple(dict.fromkeys(cr.CHEAP + cr.FRONTIER + self.models))
        self.design = {
            "preregistration": str(prereg),
            "frozen_sha256": frozen,
            "runs": str(tmp / "runs"),
            "stage": "confirm",
            "board": str(board_path),
            "engine": f"policyengine-us {ENGINE}",
            "draw_order": self.draw_order,
            "arms": {a: a for a in cr.ARMS},
            "frontier_arms": {a: f"f-{a}" for a in cr.FRONTIER_ARMS},
            "caps": {m: (caps or {}).get(m, 10.0) for m in budget_models},
            "reserves": {m: reserve for m in budget_models},
            "overall_cap": overall_cap,
            "spent_before": spent_before,
            "workers": 2,
            "anchor_command": [sys.executable, str(ANCHOR_SCRIPT), str(tmp)],
        }
        self.readers = Readers()
        self.provider = FakeProvider(self, specs)
        self.run = cr.Run(
            self.design,
            models=self.models,
            converse=self.provider,
            pool_factory=pool,
            completion_for=lambda profile: None,
            host_factory=self.readers.host,
            out=io.StringIO(),
        )

    def execute(self):
        self.run.execute()
        return self

    # What the runner wrote.

    def runs(self) -> Path:
        return Path(self.design["runs"])

    def lines(self, model, name="run-log.jsonl") -> list[dict]:
        path = self.runs() / model / name
        if not path.exists():
            return []
        return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]

    def attempts(self, model) -> list[dict]:
        return [x for x in self.lines(model) if "event" not in x]

    def events(self, model, kind=None) -> list[dict]:
        return [
            x
            for x in self.lines(model)
            if x.get("event") and kind in (None, x["event"])
        ]

    def folder(self, model, label) -> Path:
        arms = (
            self.design["arms"] if model in cr.CHEAP else self.design["frontier_arms"]
        )
        return self.runs() / model / arms[label] / "confirm" / "households"


def labels_of(model):
    return cr.ARMS if model in cr.CHEAP else cr.FRONTIER_ARMS


def host_from_files(folder: Path):
    """The host evidence as the report builds it, from the archived files."""
    meta = json.loads((folder / "host.json").read_text())
    start, end = float(meta["start"]), float(meta["end"])
    samples = [
        json.loads(x) for x in (folder / "host-log.jsonl").read_text().splitlines() if x
    ]
    spans = cr.guard_spans(
        (folder / "clamshell-guard.log").read_text(), meta["timezone"], end
    )
    spans += cr.power_spans((folder / "pmset.log").read_text(), end)
    # A sample with no pressure reading is no sample.
    good = [s for s in samples if s.get("pressure") is not None]
    times = sorted(float(s["time"]) for s in good)
    for a, b in zip([start] + times, times + [end]):
        if b - a > cr.HOST_LOG_GAP:
            spans.append((a, b, "host log gap"))
    pressure = [float(s["time"]) for s in good if int(s["pressure"]) > 1]

    class Host:
        def trouble(self, s, e):
            for a, b, what in spans:
                if a <= e and b >= s:
                    return what
            for t in pressure:
                if s - cr.PRESSURE_WINDOW <= t <= e + cr.PRESSURE_WINDOW:
                    return "memory pressure"
            return None

    return Host()


def chain_problems(path: Path, seed: str) -> list[str]:
    """Whether each line's `prev` is the line before's sha256 (the first's,
    `seed`)."""
    head = seed
    for i, text in enumerate(path.read_text().splitlines() if path.exists() else []):
        if json.loads(text).get("prev") != head:
            return [f"{path.name} line {i + 1}: its prev is not the line before's hash"]
        head = cr.line_sha(text)
    return []


def chain_heads(path: Path, seed: str) -> list[str]:
    """The chain's head after each count of lines, from none."""
    heads = [seed]
    for text in path.read_text().splitlines() if path.exists() else []:
        heads.append(cr.line_sha(text))
    return heads


def anchor_problems(world: World) -> list[str]:
    """The anchors: a chain of their own; each holds every log's head at its
    count; the last holds every log whole; the last was pushed."""
    problems: list[str] = []
    runs, frozen = world.runs(), world.design["frozen_sha256"]
    path = runs / "anchors.jsonl"
    problems += chain_problems(path, cr.chain_seed(frozen, "", "anchors.jsonl"))
    anchors = [json.loads(x) for x in path.read_text().splitlines()]
    heads = {
        (model, name): chain_heads(
            runs / model / name, cr.chain_seed(frozen, model, name)
        )
        for model in world.models
        for name in ("run-log.jsonl", "admission-log.jsonl")
    }
    host = chain_heads(runs / "host" / "host-log.jsonl", cr.HOST_SEED)
    for i, anchor in enumerate(anchors):
        for (model, name), chain in heads.items():
            got = anchor["models"][model][name]
            if got["lines"] >= len(chain) or chain[got["lines"]] != got["sha256"]:
                problems.append(f"anchor {i}: {model}/{name} is not the log's head")
        got = anchor["host-log.jsonl"]
        if got["lines"] >= len(host) or host[got["lines"]] != got["sha256"]:
            problems.append(f"anchor {i}: the host log is not the log's head")
    last = anchors[-1]
    for (model, name), chain in heads.items():
        if last["models"][model][name]["lines"] != len(chain) - 1:
            problems.append(f"the last anchor leaves out lines of {model}/{name}")
    if last["host-log.jsonl"]["lines"] != len(host) - 1:
        problems.append("the last anchor leaves out host-log lines")
    for a, b in zip(anchors, anchors[1:]):
        if b["time"] - a["time"] > cr.ANCHOR_SECONDS + ANCHOR_SLACK:
            problems.append(f"anchors {a['time']!r} and {b['time']!r} too far apart")
    pushes = [
        json.loads(x) for x in (runs / "anchor-pushes.jsonl").read_text().splitlines()
    ]
    final = cr.line_sha(path.read_text().splitlines()[-1])
    if not any(x["anchor"] == final and x["returncode"] == 0 for x in pushes):
        problems.append("the last anchor was not pushed")
    copy = world.tmp / "anchored.jsonl"
    if not copy.exists() or copy.read_text() != path.read_text():
        problems.append("the anchor command's copy is not the anchors")
    return problems


def run_problems(world: World) -> list[str]:
    """Every rule of the run procedure, recomputed from the runner's files."""
    problems: list[str] = []
    host = host_from_files(world.runs() / "host")
    frozen = world.design["frozen_sha256"]
    problems += chain_problems(world.runs() / "host" / "host-log.jsonl", cr.HOST_SEED)
    problems += anchor_problems(world)
    late_total = 0.0
    position = {sid: i for i, sid in enumerate(world.draw_order)}
    master = cr.master_seed(world.design["frozen_sha256"])
    all_attempts = []
    ceiling_events = {}
    for model in world.models:
        labels = labels_of(model)
        drawn = cr.orders(master, model, world.draw_order, labels)
        lines = world.attempts(model)
        events = world.events(model)
        for name in ("run-log.jsonl", "admission-log.jsonl"):
            problems += chain_problems(
                world.runs() / model / name, cr.chain_seed(frozen, model, name)
            )
        for e in events:
            if e["event"] == "stop" and e.get("cause") not in cr.STOP_CAUSES:
                problems.append(f"{model}: a stop with no cause ({e})")
            if e["event"] == "ceiling" and e.get("cause") != "ceiling":
                problems.append(f"{model}: a ceiling event with another cause")
        late_total += sum(e["cost_usd"] for e in events if e["event"] == "late-cost")
        causes = {e.get("cause") for e in events if e["event"] == "stop"}
        stops = [e["time"] for e in events if e["event"] in ("stop", "ceiling")]
        stopped_at = min(stops) if stops else math.inf
        ceiling_events[model] = [e["time"] for e in events if e["event"] == "ceiling"]
        cost: dict[str, float] = {}
        span: dict[str, list[float]] = {}
        by_run: dict = {}
        cut_short: set[str] = set()  # an arm or a rerun the stop kept from running
        for x in lines:
            by_run.setdefault((x["household"], x["arm"]), []).append(x)
        # Records and hashes.
        for label in labels:
            folder = world.folder(model, label)
            finals = sorted(folder.glob("*.json")) if folder.is_dir() else []
            for path in finals:
                if (path.stem, label) not in by_run:
                    problems.append(
                        f"{model}/{label}/{path.stem}: a record with no line"
                    )
        for (sid, label), xs in sorted(by_run.items()):
            at = f"{model}/{label}/{sid}"
            xs.sort(key=lambda x: x["attempt"])
            if [x["attempt"] for x in xs] != list(range(1, len(xs) + 1)):
                problems.append(f"{at}: attempts {[x['attempt'] for x in xs]}")
                continue
            final_path = world.folder(model, label) / f"{sid}.json"
            final = json.loads(final_path.read_text())
            entries = final.get("attempts") or []
            if len(entries) != len(xs) - 1:
                problems.append(f"{at}: {len(entries)} entries for {len(xs)} attempts")
                continue
            for k, x in enumerate(xs, start=1):
                if k < len(xs):
                    entry = entries[k - 1]
                    path = world.folder(model, label) / entry["file"]
                    rec = json.loads(path.read_text())
                    if entry["n"] != k or entry["sha256"] != cr.sha256_file(path):
                        problems.append(f"{at}#{k}: its entry does not hash its file")
                    if entry["class"] != x["class"] or entry["status"] != rec["status"]:
                        problems.append(f"{at}#{k}: its entry is not its line's")
                    if x["sha256"] != entry["sha256"]:
                        problems.append(f"{at}#{k}: its line's hash is not its file's")
                else:
                    rec = final
                    if x["sha256"] != cr.sha256_file(final_path):
                        problems.append(
                            f"{at}#{k}: its line's hash is not its record's"
                        )
                cls, _ = cr.classify(rec, x["start"], x["end"], host)
                if x["class"] == "unsettled" and "runner-error" in causes:
                    cls = "unsettled"  # classed when the runner failed: it stands
                rule = cr.action(cls, k)
                if x["class"] != cls or x["action"] != rule:
                    problems.append(
                        f"{at}#{k}: logged {x['class']}/{x['action']}, "
                        f"recomputed {cls}/{rule}"
                    )
                if x["status"] != rec["status"] or x["lane"] != 1 + position[sid] % 2:
                    problems.append(f"{at}#{k}: status or lane")
                if k < len(xs) and rule not in ("rerun", "pause-rerun"):
                    problems.append(f"{at}#{k}: rerun after {cls}")
                if k == len(xs) and rule in ("rerun", "pause-rerun"):
                    cut_short.add(sid)
                    if not stops:
                        problems.append(
                            f"{at}#{k}: a rerun due and never run, with no stop"
                        )
                times = [
                    t[key]
                    for t in rec.get("turns") or []
                    for key in ("request_started_at", "request_completed_at")
                ]
                if times and (
                    min(times) < x["start"] - CLOCK_SLACK
                    or max(times) > x["end"] + CLOCK_SLACK
                ):
                    problems.append(
                        f"{at}#{k}: requests {min(times)!r}-{max(times)!r} outside "
                        f"its start and end {x['start']!r}-{x['end']!r}"
                    )
                if x["start"] > stopped_at:
                    problems.append(f"{at}#{k}: started after a stop")
                cost[sid] = cost.get(sid, 0.0) + cr.attempt_cost(rec)
                s, e = span.get(sid, [math.inf, -math.inf])
                span[sid] = [min(s, x["start"]), max(e, x["end"])]
                all_attempts.append((model, sid, label, k, x, rec))
        # The schedule.
        for lane in (1, 2):
            mine = sorted(
                (x for x in lines if x["lane"] == lane), key=lambda x: x["start"]
            )
            for a, b in zip(mine, mine[1:]):
                if b["start"] < a["end"]:
                    problems.append(f"{model} lane {lane}: attempts overlap")
            blocks: list = []
            for x in mine:
                if blocks and blocks[-1][0] == x["household"]:
                    blocks[-1][1].append(x)
                else:
                    blocks.append((x["household"], [x]))
            sids = [s for s, _ in blocks]
            if len(set(sids)) != len(sids) or sids != sorted(sids, key=position.get):
                problems.append(
                    f"{model} lane {lane}: households split or out of order"
                )
            for i, (sid, block) in enumerate(blocks):
                got = [(x["attempt"], x["arm"]) for x in block]
                firsts = [a for n, a in got if n == 1]
                want = [(1, a) for a in firsts]
                for n in range(2, cr.MAX_RERUNS + 2):
                    again = {x["arm"] for x in block if x["attempt"] == n}
                    want += [(n, a) for a in drawn[sid] if a in again]
                cut = firsts != drawn[sid]
                if cut:
                    cut_short.add(sid)
                if got != want or firsts != drawn[sid][: len(firsts)]:
                    problems.append(f"{model}/{sid}: ran {got}, drawn {drawn[sid]}")
                if cut and not (stops and i == len(blocks) - 1):
                    problems.append(f"{model}/{sid}: cut short without a stop")
        # Admission.
        decisions = sorted(
            world.lines(model, "admission-log.jsonl"), key=lambda x: x["time"]
        )
        cap = world.design["caps"][model]
        reserve = world.design["reserves"][model]
        admitted: dict[str, float] = {}
        refused = False
        # A household a stop cut short is under way until the stop.
        ended = {
            h: max(e, stopped_at) if h in cut_short else e for h, (_, e) in span.items()
        }
        for x in decisions:
            sid, t = x["household"], x["time"]
            if sid in world.no_output:
                problems.append(
                    f"{model}/{sid}: a household with no scored output decided"
                )
            finished = [h for h in admitted if h in ended and ended[h] <= t]
            spend = sum(cost[h] for h in finished)
            under = sum(1 for h in admitted if h not in finished) + 1
            ok = not refused and spend + under * reserve <= cap + cr.ADMISSION_SLACK
            if x["decision"] != ("admit" if ok else "refuse"):
                problems.append(f"{model}/{sid}: logged {x['decision']}, rule {ok}")
            if abs(x["finished_spend"] - spend) > 1e-9 or x["under_way"] != under:
                problems.append(
                    f"{model}/{sid}: spend {x['finished_spend']} vs {spend}"
                )
            if x["lane"] != 1 + position[sid] % 2:
                problems.append(f"{model}/{sid}: decided on the other lane")
            if x["decision"] == "admit":
                admitted[sid] = t
            else:
                refused = True
        for sid, (s, _) in span.items():
            if sid not in admitted or s < admitted[sid]:
                problems.append(f"{model}/{sid}: ran without, or before, its admission")
        for lane in (1, 2):
            expect = [
                s
                for s in world.draw_order
                if 1 + position[s] % 2 == lane and s not in world.no_output
            ]
            decided = [x["household"] for x in decisions if x["lane"] == lane]
            if decided != expect[: len(decided)]:
                problems.append(f"{model} lane {lane}: decisions skip a household")
            if len(decided) < len(expect) and not (refused or stops):
                problems.append(f"{model} lane {lane}: stopped deciding early")
            if not stops and set(
                a for a in admitted if 1 + position[a] % 2 == lane
            ) - set(span):
                problems.append(f"{model} lane {lane}: admitted and never run")
        # Pauses.
        resumes = sorted(e["time"] for e in events if e["event"] == "resume")
        for x in lines:
            if x["class"] != "operator":
                continue
            pauses = [
                e for e in events if e["event"] == "pause" and e["time"] >= x["end"] - 1
            ]
            if not pauses:
                problems.append(
                    f"{model}/{x['household']}: an operator failure, no pause"
                )
                continue
            until = next((t for t in resumes if t >= pauses[0]["time"]), math.inf)
            if any(x["end"] < y["start"] < until for y in lines):
                problems.append(f"{model}: an attempt started during a pause")
    # The ceiling, over every model.
    total = world.design["spent_before"] + sum(
        cr.attempt_cost(r) for *_, r in all_attempts
    )
    ceiling = world.design["overall_cap"] + cr.CEILING_MARGIN
    if total >= ceiling and not all(ceiling_events.values()):
        problems.append(f"spend {total} reached the ceiling and a model has no event")
    for times in ceiling_events.values():
        for t in times:
            if any(x["start"] > t for *_, x, _ in all_attempts):
                problems.append("an attempt started after the ceiling")
    # Conservation: the ceiling counted exactly the records' spend, and the
    # spend of abandoned attempts after their deadline.
    if abs(world.run.ceiling.spent_usd - total - late_total) > 1e-9:
        problems.append(
            f"the ceiling counted {world.run.ceiling.spent_usd}, records {total} "
            f"and late spend {late_total}"
        )
    problems += trigger_problems(world, all_attempts)
    return problems


def trigger_problems(world: World, all_attempts) -> list[str]:
    """Each stop rule's trigger has its stop, and each stop of those causes
    its trigger: a harness failure and an abandoned attempt stop the model at
    their end, before any other attempt starts; one inconclusive error ending
    runs in a sixth household stops it once that household's pass is classed."""
    problems: list[str] = []
    for model in world.models:
        events = world.events(model)
        mine = [(sid, k, x, rec) for m, sid, _, k, x, rec in all_attempts if m == model]
        triggers: list[tuple[str, float]] = []
        joined: dict[str, dict[str, float]] = {}  # key -> household -> pass end
        for sid, k, x, rec in mine:
            if x["class"] == "harness":
                triggers.append(("harness", x["end"]))
            if str(rec.get("error") or "").startswith("AttemptDeadline"):
                triggers.append(("deadline", x["end"]))
            status = rec.get("status")
            if x["class"] == "inconclusive" and status in (
                "provider_error",
                "harness_error",
            ):
                key = f"{status}: {cr.error_class(rec) or rec.get('error')}"
                end = max(y["end"] for s, n, y, _ in mine if s == sid and n == k)
                households = joined.setdefault(key, {})
                households[sid] = min(households.get(sid, math.inf), end)
        for households in joined.values():
            ends = sorted(households.values())
            if len(ends) > cr.INCONCLUSIVE_STOP:
                triggers.append(("inconclusive", ends[cr.INCONCLUSIVE_STOP]))
        stops = [e for e in events if e["event"] == "stop"]
        for cause, t in triggers:
            if not any(
                e.get("cause") == cause and t <= e["time"] <= t + TRIGGER_BOUND
                for e in stops
            ):
                problems.append(f"{model}: a {cause} trigger at {t!r} with no stop")
            if cause != "inconclusive" and any(x["start"] > t for _, _, x, _ in mine):
                problems.append(f"{model}: an attempt started after a {cause} stop")
        for e in stops:
            if e.get("cause") in ("harness", "deadline", "inconclusive") and not any(
                cause == e["cause"] and t <= e["time"] <= t + TRIGGER_BOUND
                for cause, t in triggers
            ):
                problems.append(f"{model}: a {e['cause']} stop with no trigger")
    return problems


@pytest.fixture
def world(tmp_path, monkeypatch, fast):
    """A fake run to plant failures in, then execute."""

    def make(**kwargs):
        return World(tmp_path, monkeypatch, **kwargs)

    return make


def test_an_untouched_run_runs_every_household_and_arm(world):
    w = world().execute()
    assert run_problems(w) == []
    for model in w.models:
        labels = labels_of(model)
        attempts = w.attempts(model)
        assert len(attempts) == N_DRAW * len(labels)
        assert {x["class"] for x in attempts} == {"ok"}
        assert all(
            x["decision"] == "admit" for x in w.lines(model, "admission-log.jsonl")
        )
        manifests = list((w.runs() / model).glob("manifest-*.json"))
        assert len(manifests) == 1
        m = json.loads(manifests[0].read_text())
        assert m["arms"] == {
            label: {
                "arm": cr.arm_string(label),
                "features": sorted(cr.arm_profile(model, label).tool_features),
            }
            for label in labels
        }
        assert m["treatment_commit"] == cr.TREATMENT_COMMIT
        assert m["cap_usd"] == 10.0 and m["reserve_usd"] == pytest.approx(0.21)
        assert m["board_engine"] == f"policyengine-us {ENGINE}"
        assert not (w.runs() / model / "in-flight").exists() or not any(
            (w.runs() / model / "in-flight").iterdir()
        )
    host = json.loads((w.runs() / "host" / "host.json").read_text())
    assert host["timezone"] == TZ and host["end"] > host["start"]


def test_households_alternate_lanes_in_draw_order(world):
    w = world(models=("gpt-6-luna",)).execute()
    lanes = {x["household"]: x["lane"] for x in w.attempts("gpt-6-luna")}
    assert [lanes[s] for s in w.draw_order] == [1, 2] * (N_DRAW // 2)


def test_each_household_runs_its_arms_in_its_drawn_order(world):
    w = world(models=("claude-haiku-5.5",)).execute()
    master = cr.master_seed(w.design["frozen_sha256"])
    drawn = cr.orders(master, "claude-haiku-5.5", w.draw_order, cr.ARMS)
    for sid in w.draw_order:
        mine = sorted(
            (x for x in w.attempts("claude-haiku-5.5") if x["household"] == sid),
            key=lambda x: x["start"],
        )
        assert [x["arm"] for x in mine] == drawn[sid]


def test_each_call_carries_its_arm_s_features(world):
    calls = {"situation": "{}", "variables": ["snap"]}
    model = "gpt-6-luna"
    w = world(models=(model,))
    sid = w.draw_order[0]
    w.provider.specs = {(model, label, sid, 1): {"calls": [calls]} for label in cr.ARMS}
    w.execute()
    messages = w.run.lanes[model].pool.messages
    assert len(messages) == len(cr.ARMS)
    raw = [m for m in messages if not isinstance(m, tuple)]
    framed = [m for m in messages if isinstance(m, tuple)]
    assert raw == [calls]  # the tool v1 arm: as a featureless pool sends it
    want = {
        tuple(sorted(cr.arm_profile(model, label).tool_features))
        for label in cr.ARMS
        if label != "pe"
    }
    assert {m[1] for m in framed} == want
    assert all(m[0] == pilot.CALL_FRAME and m[2] == calls for m in framed)
    # The worker reads each frame's features as the arm's.
    for m in framed:
        assert pilot.frame_features(m[1]) == frozenset(m[1])
    assert run_problems(w) == []


def test_households_with_no_scored_output_are_never_decided(world):
    model = "gemini-4-argon"
    master = cr.master_seed(hashlib.sha256(PREREG.encode()).hexdigest())
    skipped = cr.draw(master, POOL, n=N_DRAW)[1]
    w = world(models=(model,), no_output=(skipped,)).execute()
    assert skipped not in {
        x["household"] for x in w.lines(model, "admission-log.jsonl")
    }
    assert skipped not in {x["household"] for x in w.attempts(model)}
    assert run_problems(w) == []


def test_a_provider_error_is_rerun_after_the_household_s_first_pass(world):
    model = "claude-haiku-5.5"
    w = world(models=(model,))
    sid = w.draw_order[0]
    master = cr.master_seed(w.design["frozen_sha256"])
    first = cr.orders(master, model, w.draw_order, cr.ARMS)[sid][0]
    error = {"status": "provider_error", "error": "RateLimitError: slow down"}
    w.provider.specs = {(model, first, sid, 1): error, (model, first, sid, 2): error}
    w.execute()
    mine = sorted(
        (x for x in w.attempts(model) if x["household"] == sid),
        key=lambda x: x["start"],
    )
    assert [(x["attempt"], x["arm"]) for x in mine][-2:] == [(2, first), (3, first)]
    assert [x["class"] for x in mine if x["arm"] == first] == ["provider"] * 2 + ["ok"]
    final = json.loads((w.folder(model, first) / f"{sid}.json").read_text())
    assert [e["n"] for e in final["attempts"]] == [1, 2]
    assert final["attempts"][0]["reason"] == "RateLimitError"
    assert (w.folder(model, first) / "attempts" / f"{sid}-1.json").exists()
    assert run_problems(w) == []


def test_a_third_attempt_stands_whatever_its_class(world):
    model = "gpt-6-sol"
    w = world(models=(model,))
    sid = w.draw_order[1]
    error = {"status": "provider_error", "error": "APIConnectionError: reset"}
    w.provider.specs = {(model, "pe3", sid, n): error for n in (1, 2, 3)}
    w.execute()
    mine = [x for x in w.attempts(model) if x["household"] == sid and x["arm"] == "pe3"]
    assert sorted((x["attempt"], x["action"]) for x in mine) == [
        (1, "rerun"),
        (2, "rerun"),
        (3, "stands"),
    ]
    assert run_problems(w) == []


def test_host_trouble_during_an_attempt_reruns_it(world):
    model = "gemini-3.5-flash-lite"
    w = world(models=(model,))
    pressured, stalled = w.draw_order[0], w.draw_order[2]  # both lane 1
    w.provider.specs = {
        (model, "loo-flat", pressured, 1): {"pressure": True, "sleep": 0.05},
        (model, "pe", stalled, 1): {"stall": cr.HOST_LOG_GAP + 0.3},
    }
    w.execute()

    def first(sid, label):
        line = next(
            x
            for x in w.attempts(model)
            if (x["household"], x["arm"], x["attempt"]) == (sid, label, 1)
        )
        final = json.loads((w.folder(model, label) / f"{sid}.json").read_text())
        return line, final["attempts"][0]

    line, entry = first(pressured, "loo-flat")
    assert line["class"] == entry["class"] == "host" and line["action"] == "rerun"
    assert "memory pressure 2 at" in entry["reason"]
    line, entry = first(stalled, "pe")
    assert line["class"] == "host" and "host log gap" in entry["reason"]
    assert run_problems(w) == []


def test_a_guard_pause_over_an_attempt_reruns_it(world, monkeypatch):
    # Guard lines have whole seconds and the fake brackets by another
    # second: keep the lookahead longer than its possible two-second backdate.
    monkeypatch.setattr(cr, "PRESSURE_WINDOW", 2.1)
    model = "gpt-6-sol"
    w = world(models=(model,))
    sid = w.draw_order[0]
    w.provider.specs = {(model, "pe3", sid, 1): {"guard": True}}
    w.execute()
    line = next(
        x
        for x in w.attempts(model)
        if (x["household"], x["arm"], x["attempt"]) == (sid, "pe3", 1)
    )
    assert line["class"] == "host"
    final = json.loads((w.folder(model, "pe3") / f"{sid}.json").read_text())
    assert final["attempts"][0]["reason"].startswith("guard pause: guard pause ")
    archived = (w.runs() / "host" / "clamshell-guard.log").read_text()
    assert "paused pids" in archived
    assert run_problems(w) == []


def test_an_operator_failure_pauses_the_model_until_resumed(world):
    model = "gpt-6-luna"
    w = world(models=(model, "claude-haiku-5.5"))
    sid = w.draw_order[0]
    w.provider.specs = {
        (model, "pe3", sid, 1): {
            "status": "provider_error",
            "error": "AuthenticationError: bad key",
            "turns": 0,
            "resume_after": 0.4,
        }
    }
    w.execute()
    pauses, resumes = w.events(model, "pause"), w.events(model, "resume")
    assert len(pauses) == 1 and len(resumes) == 1
    assert resumes[0]["reason"] == "fixed in a test"
    started = [x["start"] for x in w.attempts(model)]
    assert not [t for t in started if pauses[0]["time"] < t < resumes[0]["time"]]
    assert resumes[0]["time"] - pauses[0]["time"] >= 0.35
    rerun = [
        x for x in w.attempts(model) if x["household"] == sid and x["arm"] == "pe3"
    ]
    assert [x["action"] for x in sorted(rerun, key=lambda x: x["attempt"])] == [
        "pause-rerun",
        "stands",
    ]
    assert not w.events("claude-haiku-5.5", "pause")  # another model runs on
    assert list((w.runs() / model).glob("resume-*.json"))
    assert run_problems(w) == []


def test_a_request_class_on_the_first_request_stops_the_model(world):
    model = "claude-opus-5.5"
    w = world(models=(model, "gpt-6-sol"))
    sid = w.draw_order[2]
    w.provider.specs = {
        (model, "pe", sid, 1): {
            "status": "provider_error",
            "error": "BadRequestError: bad tools",
            "turns": 0,
        }
    }
    w.execute()
    stops = w.events(model, "stop")
    assert len(stops) == 1 and "first request" in stops[0]["reason"]
    assert stops[0]["cause"] == "harness"
    assert not [x for x in w.attempts(model) if x["start"] > stops[0]["time"]]
    assert len(w.attempts("gpt-6-sol")) == N_DRAW * 2  # the other model finishes
    assert run_problems(w) == []


def test_one_inconclusive_error_in_six_households_stops_the_model(world):
    model = "gpt-6-luna"
    w = world(models=(model,))
    error = {"status": "provider_error", "error": "ProviderEmpty: no choices"}
    w.provider.specs = {(model, "pe", sid, 1): error for sid in w.draw_order}
    w.execute()
    stops = w.events(model, "stop")
    assert len(stops) == 1
    assert (
        stops[0]["reason"] == "provider_error: ProviderEmpty ended runs in 6 households"
    )
    assert stops[0]["cause"] == "inconclusive"
    assert run_problems(w) == []


def test_five_households_with_one_inconclusive_error_do_not_stop(world):
    model = "gpt-6-luna"
    w = world(models=(model,))
    error = {"status": "provider_error", "error": "ProviderEmpty: no choices"}
    w.provider.specs = {(model, "pe", sid, 1): error for sid in w.draw_order[:5]}
    w.execute()
    assert not w.events(model, "stop")
    assert len(w.attempts(model)) == N_DRAW * len(cr.ARMS)
    assert run_problems(w) == []


def test_a_refusal_ends_both_lanes_decisions(world):
    model = "claude-haiku-5.5"
    # Each household costs 7 arms x $0.01; the reserve is $0.21 per household.
    w = world(models=(model,), caps={model: 0.5}).execute()
    decisions = w.lines(model, "admission-log.jsonl")
    refused = [x for x in decisions if x["decision"] == "refuse"]
    after = decisions[decisions.index(refused[0]) :]
    assert refused and all(x["decision"] == "refuse" for x in after)
    admitted = {x["household"] for x in decisions if x["decision"] == "admit"}
    assert {x["household"] for x in w.attempts(model)} == admitted
    assert run_problems(w) == []


def test_spend_never_stops_a_conversation_below_the_ceiling(world):
    model = "gemini-4-argon"
    w = world(models=(model,), caps={model: 0.05}, reserve=0.01)
    sid = w.draw_order[0]
    w.provider.specs = {(model, "pe", sid, 1): {"turns": 4, "cost": 0.5}}
    w.execute()
    # $2 on one arm, far past the cap: it ran to the end; later households
    # were refused.
    ran = [x for x in w.attempts(model) if x["household"] == sid and x["arm"] == "pe"]
    assert ran[0]["status"] == "complete"
    assert any(x["decision"] == "refuse" for x in w.lines(model, "admission-log.jsonl"))
    assert run_problems(w) == []


def test_the_hard_ceiling_stops_every_model(world):
    w = world(
        models=("claude-haiku-5.5", "gpt-6-sol", "gemini-4-argon"),
        overall_cap=0.0,
        spent_before=24.0,
    )
    sid = w.draw_order[1]
    # One long conversation crosses $25 while the others run.
    w.provider.specs = {
        ("gpt-6-sol", "pe3", sid, 1): {"turns": 3, "cost": 0.5, "sleep": 0.02}
    }
    w.execute()
    events = {m: w.events(m, "ceiling") for m in w.models}
    assert all(len(e) == 1 for e in events.values())
    crossed = events["gpt-6-sol"][0]["time"]
    assert {e[0]["time"] for e in events.values()} == {crossed}
    assert w.run.ceiling.spent_usd >= 25.0
    for m in w.models:
        assert not [x for x in w.attempts(m) if x["start"] > crossed]
    assert run_problems(w) == []


def test_a_model_that_decides_nothing_still_has_both_logs(world):
    """haiku's first attempt crosses the ceiling before gpt-6-sol's lanes,
    held back, decide: gpt-6-sol's run log holds only the ceiling event and
    its admission log is empty."""
    w = world(
        models=("claude-haiku-5.5", "gpt-6-sol"), overall_cap=0.0, spent_before=24.5
    )
    sid = w.draw_order[0]
    first = w.run.lanes["claude-haiku-5.5"].orders[sid][0]
    w.provider.specs = {("claude-haiku-5.5", first, sid, 1): {"cost": 1.0}}
    held = w.run.lanes["gpt-6-sol"]
    admit = held.admit

    def late(sid, lane):
        time.sleep(0.3)
        return admit(sid, lane)

    held.admit = late
    w.execute()
    admission = w.runs() / "gpt-6-sol" / "admission-log.jsonl"
    assert admission.exists() and admission.read_text() == ""
    assert [
        x["event"]
        for x in w.lines("gpt-6-sol")
        if x["event"] not in ("setup-start", "setup-end")
    ] == ["ceiling"]
    assert run_problems(w) == []


def test_a_conversation_under_way_at_the_ceiling_ends_budget_stop(world):
    model = "gpt-6-luna"
    w = world(models=(model,), overall_cap=0.0, spent_before=24.9)
    sid = w.draw_order[0]
    master = cr.master_seed(w.design["frozen_sha256"])
    first = cr.orders(master, model, w.draw_order, cr.ARMS)[sid][0]
    w.provider.specs = {(model, first, sid, 1): {"turns": 5, "cost": 0.06}}
    w.execute()
    line = next(
        x for x in w.attempts(model) if x["household"] == sid and x["arm"] == first
    )
    assert line["status"] == "budget_stop" and line["class"] == "ceiling"
    assert line["action"] == "stopped"
    assert run_problems(w) == []


def test_an_attempt_that_raises_is_saved_as_a_harness_error_record(world):
    model = "claude-opus-5.5"
    w = world(models=(model,))
    sid = w.draw_order[3]
    w.provider.specs = {(model, "pe3", sid, 1): {"raise": True}}
    w.execute()
    replaced = json.loads(
        (w.folder(model, "pe3") / "attempts" / f"{sid}-1.json").read_text()
    )
    assert replaced["status"] == "harness_error" and replaced["turns"] == []
    assert replaced["error"] == "RuntimeError: a test raised"
    assert replaced["tool_features"] == sorted(
        cr.arm_profile(model, "pe3").tool_features
    )
    line = next(
        x
        for x in w.attempts(model)
        if x["household"] == sid and x["attempt"] == 1 and x["arm"] == "pe3"
    )
    assert line["class"] == "none" and line["action"] == "rerun"
    assert run_problems(w) == []


def test_a_pool_that_lost_every_worker_is_started_again(world):
    model = "gpt-6-sol"
    starts = []

    class Losing(FakePool):
        def __init__(self, lanes):
            super().__init__(lanes)
            starts.append(self)

        def call(self, message):
            self.lost = 2  # every worker gone after this call
            return super().call(message)

    w = world(models=(model,), pool=Losing)
    sid = w.draw_order[0]
    w.provider.specs = {(model, "pe", sid, 1): {"calls": [{"situation": "{}"}]}}
    w.execute()
    assert len(starts) == 2 and starts[0].closed
    setup = [e for e in w.events(model) if e.get("phase") == "restart"]
    assert [e["event"] for e in setup] == ["setup-start", "setup-end"]
    assert setup[0]["start"] == setup[0]["time"] == setup[1]["start"]
    assert setup[1]["time"] >= setup[0]["time"]
    assert setup[1]["outcome"] == "ready"
    assert run_problems(w) == []


def test_a_pool_that_cannot_start_again_stops_the_model(world, monkeypatch):
    model = "gpt-6-sol"
    made = []

    def pool(lanes):
        made.append(1)
        return FakePool(lanes, fail=len(made) > 1)

    w = world(models=(model,), pool=pool)
    sid = w.draw_order[0]
    w.provider.specs = {(model, "pe", sid, 1): {"calls": [{"situation": "{}"}]}}
    original = FakePool.call

    def losing(self, message):
        self.lost = 2
        return original(self, message)

    monkeypatch.setattr(FakePool, "call", losing)
    w.execute()
    stops = w.events(model, "stop")
    assert stops and "engine pool" in stops[0]["reason"]
    assert stops[0]["cause"] == "pool"
    setup = [e for e in w.events(model) if e.get("phase") == "restart"]
    assert [e["event"] for e in setup] == ["setup-start", "setup-end"]
    assert setup[1]["outcome"] == "failed"
    assert run_problems(w) == []


def test_a_household_a_stop_cuts_short_is_under_way_until_the_stop(world):
    """Lane 1's first household loses the pool in its first arm, and the
    restart waits while lane 2 finishes its household and
    decides its next: the household lane 1 cut short has ended its last
    attempt, but it is still under way, so its spend is not counted."""
    model = "gpt-6-sol"
    made = []
    other_second, restarting, decided_after = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )

    class Losing(FakePool):
        def call(self, message):
            assert other_second.wait(30)
            self.lost = 2
            return super().call(message)

    def pool(lanes):
        made.append(1)
        if len(made) > 1:
            restarting.set()
            assert decided_after.wait(30)
            raise RuntimeError("tool worker failed to start: a test")
        return Losing(lanes)

    w = world(models=(model,), pool=pool)
    cut, other, after = w.draw_order[0], w.draw_order[1], w.draw_order[3]
    lanes = w.run.lanes[model]
    orders, admit = lanes.orders, lanes.admit

    def in_second(lanes):
        other_second.set()
        assert restarting.wait(30)

    def admitted(sid, lane):
        ok = admit(sid, lane)
        if sid == after and ok:
            decided_after.set()
            # Keep this admitted household from racing the failed restart
            # for the pool lock before lane 1 records its stop.
            with lanes.cond:
                assert lanes.cond.wait_for(lambda: lanes.stopped, timeout=30)
        return ok

    lanes.admit = admitted
    w.provider.specs = {
        (model, orders[cut][0], cut, 1): {"calls": [{"situation": "{}"}]},
        (model, orders[other][1], other, 1): {"check": in_second},
    }
    w.execute()
    stop = w.events(model, "stop")[0]["time"]
    decided = {x["household"]: x for x in w.lines(model, "admission-log.jsonl")}
    assert decided[after]["time"] < stop  # decided while the cut household waited
    assert decided[after]["finished_spend"] == pytest.approx(2 * COST)  # `other` only
    assert decided[after]["under_way"] == 2  # `cut` and `after`
    assert [x["arm"] for x in w.attempts(model) if x["household"] == cut] == [
        orders[cut][0]
    ]
    setup = [e for e in w.events(model) if e.get("phase") == "restart"]
    assert [e["event"] for e in setup] == ["setup-start", "setup-end"]
    assert setup[0]["start"] == setup[0]["time"] == setup[1]["start"]
    assert setup[1]["time"] >= decided[after]["time"]
    assert setup[1]["outcome"] == "failed"
    assert run_problems(w) == []


def test_an_interrupt_stops_every_model_and_lets_attempts_end(world):
    w = world(models=("gpt-6-luna", "gpt-6-sol"))
    sid = w.draw_order[0]
    first = w.run.lanes["gpt-6-luna"].orders[sid][0]

    def interrupt_inside(lanes):
        # The signal arrives during the household's first attempt, which
        # finishes only once the main loop has stopped the lanes, so no
        # timing on a loaded host lets the household's later arms start first.
        w.run.interrupt(2, None)
        until = time.time() + 30
        while not lanes.stopped and time.time() < until:
            time.sleep(0.01)

    w.provider.specs = {("gpt-6-luna", first, sid, 1): {"check": interrupt_inside}}
    w.execute()
    for m in w.models:
        stops = w.events(m, "stop")
        assert len(stops) == 1 and stops[0]["reason"] == "operator stop (signal 2)"
        assert stops[0]["cause"] == "interrupt"
        assert not [x for x in w.attempts(m) if x["start"] > stops[0]["time"]]
    luna = [x for x in w.attempts("gpt-6-luna") if x["household"] == sid]
    assert luna and len(luna) < len(cr.ARMS)  # cut by the stop
    assert run_problems(w) == []


def test_a_failed_explain_trace_is_inconclusive(world):
    """The explain feature's trace catches its own errors and returns them
    under `explanations`: a MemoryError there is the host's, not a miss."""

    class Explaining(FakePool):
        def call(self, message):
            self.messages.append(message)
            return {
                "results": {"snap": {"values": {"spm": 1.0}}},
                "explanations": {"snap": {"error": "MemoryError: a test"}},
            }, 0.0

    model = "gpt-6-luna"
    w = world(models=(model,), pool=Explaining)
    sid = w.draw_order[0]
    w.provider.specs = {(model, "pe3", sid, 1): {"calls": [{"situation": "{}"}]}}
    w.execute()
    line = next(
        x for x in w.attempts(model) if x["household"] == sid and x["arm"] == "pe3"
    )
    assert line["class"] == "inconclusive" and line["action"] == "stands"
    assert run_problems(w) == []


def test_no_household_is_decided_after_the_crossing(world):
    """The crossing lands between the lanes' halt check and the decision: the
    decision's time is taken under the ceiling's lock, after a second look."""
    w = world(models=("gpt-6-luna",))
    lanes = w.run.lanes["gpt-6-luna"]
    halted = lanes.halted

    def crossing():
        result = halted()
        if not result:
            w.run.ceiling.add(1e6)  # another lane's spend, just after the check
        return result

    lanes.halted = crossing
    decided = lanes.admit(w.draw_order[0], 1)
    lines = w.lines("gpt-6-luna", "admission-log.jsonl")
    assert decided is False and lines == []


@pytest.mark.parametrize(
    "when", ["before the run", "before the run, misdated", "during the pause"]
)
def test_a_resume_written_before_the_pause_is_ignored(world, when, monkeypatch):
    """A resume left from before a pause would end that pause unseen: it is
    set aside, and the pause holds until a resume written during it. One
    found while no pause holds is set aside at once, whatever time it
    states; one found during the pause but stamped before it is set aside
    too."""
    model = "gpt-6-luna"
    w = world(models=(model,))
    sid = w.draw_order[0]
    folder = w.runs() / model
    folder.mkdir(parents=True)
    stale = {"time": time.time(), "note": "stale"}
    if when.startswith("before the run"):
        if when.endswith("misdated"):
            stale["time"] += 3600.0  # a writer whose clock runs ahead
        cr.write_json(folder / "RESUME.json", stale)

    lanes, watch = w.run.lanes[model], w.run.watch
    planted, fresh = False, False

    def supervised(*args, **kwargs):
        nonlocal planted, fresh
        with lanes.cond:
            if when == "during the pause" and lanes.paused and not planted:
                cr.write_json(folder / "RESUME.json", stale)
                planted = True
        watch(*args, **kwargs)
        with lanes.cond:
            if (
                lanes.paused
                and list(folder.glob("resume-ignored-*.json"))
                and not fresh
            ):
                # The stale note has been read and archived before its
                # replacement exists; the next watch sees only the fresh one.
                cr.write_json(
                    folder / "RESUME.json",
                    {"time": cr.clock(), "note": "fixed in a test"},
                )
                fresh = True

    monkeypatch.setattr(w.run, "watch", supervised)

    w.provider.specs = {
        (model, "pe3", sid, 1): {
            "status": "provider_error",
            "error": "AuthenticationError: bad key",
            "turns": 0,
        }
    }
    w.execute()
    pauses, resumes = w.events(model, "pause"), w.events(model, "resume")
    assert len(pauses) == 1 and len(resumes) == 1
    assert resumes[0]["reason"] == "fixed in a test"
    assert resumes[0]["time"] >= pauses[0]["time"]
    ignored = list(folder.glob("resume-ignored-*.json"))
    assert len(ignored) == 1 and json.loads(ignored[0].read_text()) == stale
    assert run_problems(w) == []


def test_the_signal_handler_only_notes_the_signal(world, monkeypatch):
    """The handler runs on the main thread between any two of its bytecodes,
    perhaps holding a lock it would need: it takes none. A second signal
    exits at once."""
    w = world(models=("gpt-6-luna",))
    lanes = w.run.lanes["gpt-6-luna"]
    exits = []
    monkeypatch.setattr(os, "_exit", lambda code: exits.append(code))
    with w.run._say_lock, lanes.cond, lanes._log_lock:
        w.run.interrupt(2, None)  # would deadlock if it took any of these
    assert w.run.signalled == 2 and not lanes.stopped
    assert w.lines("gpt-6-luna") == []
    w.run.interrupt(15, None)
    assert exits == [130]


def test_an_attempt_that_raises_after_spending_keeps_its_cost(world):
    model = "claude-haiku-5.5"
    w = world(models=(model,))
    sid = w.draw_order[0]
    first = w.run.lanes[model].orders[sid][0]
    w.provider.specs = {
        (model, first, sid, 1): {"turns": 2, "cost": 0.03, "raise_after": True}
    }
    w.execute()
    replaced = json.loads(
        (w.folder(model, first) / "attempts" / f"{sid}-1.json").read_text()
    )
    assert replaced["status"] == "harness_error" and replaced["turns"] == []
    assert replaced["totals"]["cost_usd"] == pytest.approx(0.06)
    assert run_problems(w) == []  # the ceiling counted it, and so do the records


def test_an_attempt_past_its_deadline_is_abandoned_and_stops_the_model(
    world, monkeypatch
):
    """The conversation runs on in its own thread; at the deadline its record
    is a harness error with the spend so far, the model stops, and the
    conversation ends `budget_stop` at its next turn. Its spend after the
    deadline is a late-cost event."""
    monkeypatch.setattr(cr, "ATTEMPT_DEADLINE", 0.3)
    model = "gpt-6-luna"
    w = world(models=(model, "claude-haiku-5.5"))
    sid = w.draw_order[0]
    first = w.run.lanes[model].orders[sid][0]
    w.provider.specs = {
        (model, first, sid, 1): {"turns": 4, "cost": 0.01, "sleep": 0.2},
        **{
            ("claude-haiku-5.5", label, s, 1): {"sleep": 0.05}
            for label in cr.ARMS
            for s in w.draw_order[:2]
        },
    }
    w.execute()
    line = next(
        x for x in w.attempts(model) if x["household"] == sid and x["arm"] == first
    )
    final = json.loads((w.folder(model, first) / f"{sid}.json").read_text())
    assert final["error"].startswith("AttemptDeadline: past the attempt deadline")
    assert final["totals"]["cost_usd"] == pytest.approx(0.01)  # turn 1 only
    assert line["class"] == "none"  # its rerun is cut short by the stop
    stops = w.events(model, "stop")
    assert len(stops) == 1 and stops[0]["cause"] == "deadline"
    late = w.events(model, "late-cost")
    assert len(late) == 1 and late[0]["cost_usd"] == pytest.approx(0.01)
    assert not [x for x in w.attempts(model) if x["start"] > line["end"]]
    assert len(w.attempts("claude-haiku-5.5")) == N_DRAW * len(cr.ARMS)
    assert run_problems(w) == []


def test_a_sampler_whose_samples_fail_stops_every_model(world):
    models = ("gpt-6-luna", "gpt-6-sol")
    w = world(models=models)
    w.provider.specs = {
        (m, label, sid, 1): {"sleep": 0.1}
        for m in models
        for label in labels_of(m)
        for sid in w.draw_order
    }
    threading.Timer(0.3, lambda: setattr(w.readers, "pressure", None)).start()
    w.execute()
    for m in models:
        stops = w.events(m, "stop")
        assert len(stops) == 1 and stops[0]["cause"] == "sampler"
        assert "samples failing since" in stops[0]["reason"]
    assert run_problems(w) == []


def failing_settle(lanes, sid, times):
    """Lanes.settle, failing its first `times` calls for household `sid`."""
    original, calls = lanes.settle, []

    def settle(at, done):
        if at == sid and len(calls) < times:
            calls.append(at)
            raise RuntimeError("a test's runner defect")
        return original(at, done)

    lanes.settle = settle
    return calls


@pytest.mark.parametrize("times", [1, 2])
def test_a_runner_error_stops_every_model_and_writes_what_ended(world, times):
    """A runner error in a household's pass: every model stops, and that
    household's ended attempts are classed, or `unsettled` if classing fails
    again, and written with their lines before the lane ends."""
    models = ("gpt-6-luna", "gpt-6-sol")
    w = world(models=models)
    sid = w.draw_order[2]
    failing_settle(w.run.lanes["gpt-6-luna"], sid, times)
    w.execute()
    for m in models:
        stops = w.events(m, "stop")
        assert len(stops) == 1 and stops[0]["cause"] == "runner-error"
    mine = [x for x in w.attempts("gpt-6-luna") if x["household"] == sid]
    assert len(mine) == len(cr.ARMS)  # the pass ended before the error
    assert {x["class"] for x in mine} == ({"ok"} if times == 1 else {"unsettled"})
    for label in cr.ARMS:
        assert (w.folder("gpt-6-luna", label) / f"{sid}.json").exists()
    assert run_problems(w) == []


def test_each_attempt_is_on_disk_before_the_next_starts(world, monkeypatch):
    """An ended attempt is written, synced, before its household's next
    attempt starts; a replaced one is saved, with its line, before its rerun
    starts."""
    model = "claude-haiku-5.5"
    w = world(models=(model,))
    sid = w.draw_order[0]
    order = w.run.lanes[model].orders[sid]
    import fcntl

    if not hasattr(fcntl, "F_GETPATH"):
        pytest.skip("no F_GETPATH: the paths synced cannot be told")
    synced: list[str] = []
    real = os.fsync

    def fsync(fd):
        path = fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024))
        synced.append(path.rstrip(b"\0").decode())
        return real(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    seen = {}

    def before_second(lanes):
        seen["in-flight"] = (
            lanes.folder / "in-flight" / sid / f"{order[0]}-1.json"
        ).exists()

    def before_rerun(lanes):
        seen["replaced"] = (
            w.folder(model, order[1]) / "attempts" / f"{sid}-1.json"
        ).exists()
        seen["line"] = any(
            x["household"] == sid and x["arm"] == order[1] and x["attempt"] == 1
            for x in w.attempts(model)
        )

    error = {"status": "provider_error", "error": "RateLimitError: slow"}
    w.provider.specs = {
        (model, order[1], sid, 1): {**error, "check": before_second},
        (model, order[1], sid, 2): {"check": before_rerun},
    }
    w.execute()
    assert seen == {"in-flight": True, "replaced": True, "line": True}
    # Each whole-file write is synced before its rename.
    assert any(f"/in-flight/{sid}/.{order[0]}-1.json.tmp" in p for p in synced)
    assert any(f"/attempts/.{sid}-1.json.tmp" in p for p in synced)
    assert run_problems(w) == []


def test_the_worker_count_is_the_design_s(tmp_path, capsys):
    design = tmp_path / "design.json"
    design.write_text(json.dumps({"runs": str(tmp_path / "runs"), "workers": 2}))
    assert cr.main(["run", str(design), "--workers", "3"]) == 1
    assert "the design runs 2 engine workers" in capsys.readouterr().out


def test_the_checker_catches_a_runner_that_ignores_a_harness_failure(
    world, monkeypatch
):
    """trigger_problems is not vacuous: a runner whose harness failure does
    not stop the model fails it."""
    model = "claude-opus-5.5"
    w = world(models=(model,))
    sid = w.draw_order[0]
    w.provider.specs = {
        (model, "pe", sid, 1): {
            "status": "provider_error",
            "error": "BadRequestError: bad tools",
            "turns": 0,
        }
    }
    lanes = w.run.lanes[model]
    real = lanes.event

    def no_stop(kind, reason, at=None, cause=None, **extra):
        if cause == "harness":
            lanes.stopped = False  # the fault: the stop is not kept
            return
        real(kind, reason, at, cause, **extra)

    lanes.event = no_stop
    w.execute()
    problems = run_problems(w)
    assert any("a harness trigger" in p and "with no stop" in p for p in problems)
    assert any("an attempt started after a harness stop" in p for p in problems)


def test_the_checker_catches_an_edited_log_line(world):
    w = world(models=("gpt-6-sol",)).execute()
    path = w.runs() / "gpt-6-sol" / "admission-log.jsonl"
    lines = path.read_text().splitlines()
    edited = json.loads(lines[1])
    edited["finished_spend"] += 1.0
    path.write_text("\n".join([lines[0], json.dumps(edited)] + lines[2:]) + "\n")
    problems = run_problems(w)
    assert any("its prev is not the line before's hash" in p for p in problems)
    # An interior edit need not change a later anchor's head: its successor
    # still has its old bytes. A tail edit separately exercises the anchor.
    edited = json.loads(lines[-1])
    edited["finished_spend"] += 1.0
    path.write_text("\n".join(lines[:-1] + [json.dumps(edited)]) + "\n")
    problems = run_problems(w)
    assert any("is not the log's head" in p for p in problems)


KINDS = {
    "ok": {},
    "provider": {"status": "provider_error", "error": "RateLimitError: slow"},
    "none": {"status": "harness_error", "error": "RuntimeError: lost", "turns": 0},
    "model": {"status": "provider_error", "error": "BadRequestError: long"},
    "inconclusive": {"status": "provider_error", "error": "ProviderEmpty: none"},
    "pressure": {"pressure": True, "sleep": 0.04},
    "incomplete": {"status": "incomplete"},
    "harness": {"status": "provider_error", "error": "BadRequestError: x", "turns": 0},
    "costly": {"turns": 3, "cost": 0.2},
}


@settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(
    planted=st.lists(
        st.tuples(
            st.sampled_from(("claude-haiku-5.5", "gpt-6-sol")),
            st.sampled_from(cr.FRONTIER_ARMS),
            st.integers(0, N_DRAW - 1),
            st.integers(1, 3),
            st.sampled_from(sorted(KINDS)),
        ),
        max_size=10,
    ),
    cap=st.sampled_from([0.3, 0.6, 10.0]),
    spent_before=st.sampled_from([0.0, 24.0]),
)
def test_every_run_keeps_the_run_procedure(
    tmp_path_factory, fast, planted, cap, spent_before
):
    """Whatever fails, and wherever spend lands, the records follow every rule."""
    tmp = tmp_path_factory.mktemp("run")
    mp = pytest.MonkeyPatch()
    try:
        models = ("claude-haiku-5.5", "gpt-6-sol")
        w = World(
            tmp,
            mp,
            models=models,
            caps={m: cap for m in models},
            overall_cap=0.0,
            spent_before=spent_before,
        )
        w.provider.specs = {
            (model, label, w.draw_order[i], n): KINDS[kind]
            for model, label, i, n, kind in planted
        }
        w.execute()
        assert run_problems(w) == []
    finally:
        mp.undo()


def test_the_checker_catches_a_planted_fault(world):
    """run_problems is not vacuous: an edited log line fails it."""
    w = world(models=("gpt-6-sol",)).execute()
    path = w.runs() / "gpt-6-sol" / "run-log.jsonl"
    lines = path.read_text().splitlines()
    at = next(i for i, line in enumerate(lines) if "event" not in json.loads(line))
    first = json.loads(lines[at])
    first["class"] = "provider"
    lines[at] = json.dumps(first)
    path.write_text("\n".join(lines) + "\n")
    assert any("recomputed" in p for p in run_problems(w))


# ---------------------------------------------------------------- before a run


def test_the_preflight_names_a_missing_field():
    assert cr.preflight({}, cr.CHEAP) == [f"the design has no {', '.join(cr.REQUIRED)}"]


def complete_preflight_design(w, tmp_path):
    """Each calculator preflight starts after synthetic standing no-tools finals."""
    pool = tmp_path / "pool.json"
    pool.write_text(json.dumps([{"id": s} for s in POOL]))
    design = dict(
        w.design,
        eligible_pool={"path": str(pool), "sha256": cr.sha256_file(pool)},
        treatment_harness=str(cr.ROOT),
        run_commit="0" * 40,
        no_tools={
            "runs": str(tmp_path / "no-tools"),
            "folder": "none",
            "stage": "confirm",
        },
    )
    for model in cr.CHEAP:
        for sid in design["draw_order"]:
            cr.write_json(
                Path(design["no_tools"]["runs"])
                / model
                / "none/confirm/households"
                / f"{sid}.json",
                {
                    "scenario_id": sid,
                    "status": "complete",
                    "turns": [{}],
                    "totals": {"cost_usd": 0.0},
                    "attempts": [],
                },
            )
    return design


def test_the_preflight_refuses_a_changed_draw_and_a_dirty_runner(
    world, tmp_path, monkeypatch
):
    w = world(models=("gpt-6-luna",))
    design = complete_preflight_design(w, tmp_path)
    design["draw_order"] = list(reversed(w.draw_order))
    monkeypatch.setattr(cr, "host_power", lambda: (True, False))
    problems = cr.preflight(design, ("gpt-6-luna",))
    text = "\n".join(problems)
    assert "the draw, recomputed" in text
    assert "not the run commit, clean" in text
    assert "lid open False" in text
    design["draw_order"] = w.draw_order
    assert "the draw" not in "\n".join(cr.preflight(design, ("gpt-6-luna",)))
    assert not any(
        p.startswith("no-tools") for p in cr.preflight(design, ("gpt-6-luna",))
    )


def test_the_preflight_refuses_a_runs_folder_with_records(world, tmp_path):
    w = world(models=("gpt-6-luna",)).execute()
    design = complete_preflight_design(w, tmp_path)
    text = "\n".join(cr.preflight(design, ("gpt-6-luna",)))
    assert "already holds records" in text and "already holds a host log" in text


@pytest.mark.parametrize(
    "fault,expected",
    [
        ("missing", "missing"),
        ("harness", "stop"),
        ("ceiling", "stopped"),
        ("history", "attempts list"),
    ],
)
def test_preflight_refuses_an_unfinished_no_tools_stage(
    world, tmp_path, fault, expected
):
    w = world(models=(cr.CHEAP[0],))
    design = complete_preflight_design(w, tmp_path)
    model, sid = cr.CHEAP[-1], w.draw_order[-1]
    path = (
        Path(design["no_tools"]["runs"])
        / model
        / "none/confirm/households"
        / f"{sid}.json"
    )
    payload = json.loads(path.read_text())
    if fault == "missing":
        path.unlink()
    else:
        if fault == "history":
            payload.pop("attempts")
        else:
            payload.update(
                status="budget_stop" if fault == "ceiling" else "provider_error",
                error="BadRequestError" if fault == "harness" else None,
                turns=[],
            )
        path.write_text(json.dumps(payload))
    text = "\n".join(cr.preflight(design, (cr.CHEAP[0],)))
    assert "no-tools" in text and model in text and sid in text and expected in text


@pytest.mark.parametrize("relationship", ["equal", "inside", "contains"])
def test_preflight_refuses_overlapping_no_tools_and_calculator_roots(
    world, tmp_path, relationship
):
    w = world(models=(cr.CHEAP[0],))
    design = complete_preflight_design(w, tmp_path)
    calculator = Path(design["runs"])
    design["no_tools"]["runs"] = str(
        {
            "equal": calculator,
            "inside": calculator / "no-tools",
            "contains": calculator.parent,
        }[relationship]
    )
    assert any("roots overlap" in p for p in cr.preflight(design, (cr.CHEAP[0],)))


def test_resume_writes_the_operator_s_note(tmp_path):
    design = tmp_path / "design.json"
    design.write_text(json.dumps({"runs": str(tmp_path / "runs")}))
    assert cr.main(["resume", str(design), "gpt-6-luna", "--note", "key rotated"]) == 0
    note = json.loads((tmp_path / "runs" / "gpt-6-luna" / "RESUME.json").read_text())
    assert note["note"] == "key rotated"


# ---------------------------------------------------------------- the harness


def chat_response(calls):
    from types import SimpleNamespace

    message = SimpleNamespace(
        role="assistant", content=None, tool_calls=calls, function_call=None
    )
    usage = SimpleNamespace(
        prompt_tokens=1000,
        completion_tokens=200,
        total_tokens=1200,
        reasoning_tokens=0,
        prompt_tokens_details=SimpleNamespace(cached_tokens=0),
        completion_tokens_details=None,
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls")],
        usage=usage,
        model="claude-haiku-5-5",
    )


def chat_call(name, arguments, call_id):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def stateless_model(**kwargs):
    """A tool-contract model: one calculation, then its answers. It reads the
    conversation so far, so the two lanes can share it."""
    if not any(m.get("role") == "tool" for m in kwargs["messages"]):
        arguments = {"situation": json.dumps({"people": {}}), "variables": ["snap"]}
        return chat_response([chat_call(pilot.TOOL_NAME, arguments, "c1")])
    outputs = {v: {"value": 0, "explanation": "value = 0"} for v in VARIABLES}
    return chat_response([chat_call("submit_outputs", {"outputs": outputs}, "s1")])


def stateless_responses_model(**kwargs):
    """A Responses tool-contract model: calculate, then submit the answers."""
    from types import SimpleNamespace

    if "previous_response_id" not in kwargs:
        name, call_id = pilot.TOOL_NAME, "c1"
        arguments = {"situation": json.dumps({"people": {}}), "variables": ["snap"]}
    else:
        name, call_id = "submit_outputs", "s1"
        arguments = {
            "outputs": {v: {"value": 0, "explanation": "value = 0"} for v in VARIABLES}
        }
    return SimpleNamespace(
        id=f"resp_{call_id}",
        output=[
            SimpleNamespace(
                type="function_call",
                id=f"fc_{call_id}",
                call_id=call_id,
                name=name,
                arguments=json.dumps(arguments),
                status="completed",
            )
        ],
        output_text=None,
        status="completed",
        incomplete_details=None,
        usage=SimpleNamespace(
            input_tokens=1000,
            output_tokens=200,
            total_tokens=1200,
            input_tokens_details=SimpleNamespace(cached_tokens=0),
            output_tokens_details=SimpleNamespace(reasoning_tokens=0),
        ),
        model=kwargs["model"],
    )


def stateless_json_model(**kwargs):
    """A Gemini JSON-contract model: calculate, then answer in JSON text."""
    if not any(m.get("role") == "tool" for m in kwargs["messages"]):
        response = stateless_model(**kwargs)
        response.model = kwargs["model"]
        return response
    response = chat_response([])
    response.model = kwargs["model"]
    response.choices[0].finish_reason = "stop"
    response.choices[0].message.content = json.dumps(
        {v: {"value": 0, "explanation": "value = 0"} for v in VARIABLES}
    )
    return response


@pytest.mark.parametrize(
    "model, completion",
    [
        ("claude-haiku-5.5", stateless_model),
        ("gpt-6-luna", stateless_responses_model),
        ("gemini-3.1-pro-preview", stateless_json_model),
    ],
)
def test_the_harness_conversation_runs_under_the_runner(world, model, completion):
    """Each API and answer contract completes real harness conversations in
    both runner lanes, with the registered feature frame for every arm.

    The confirmatory roster's Geminis use tools. The older board profile
    covers the harness's Gemini JSON path in a fake design, without changing
    the production roster or any model's answer contract."""
    w = world(models=(model,))
    w.run.converse = cr.converse_with_harness
    w.run.completion_for = lambda profile: completion
    w.execute()
    labels = labels_of(model)
    attempts = w.attempts(model)
    assert len(attempts) == N_DRAW * len(labels)
    assert {x["status"] for x in attempts} == {"complete"}
    messages = w.run.lanes[model].pool.messages
    assert len(messages) == N_DRAW * len(labels)  # one calculation per attempt
    frames = [m for m in messages if isinstance(m, tuple)]
    assert len(frames) == N_DRAW * (len(labels) - 1)  # every arm but pe
    sid = w.draw_order[0]
    label = "loo-names" if "loo-names" in labels else "pe3"
    rec = json.loads((w.folder(model, label) / f"{sid}.json").read_text())
    profile = cr.arm_profile(model, label)
    assert rec["arm"] == cr.arm_string(label) and rec["attempts"] == []
    assert rec["tool_features"] == sorted(profile.tool_features)
    assert rec["predictions"] == {v: 0.0 for v in VARIABLES}
    assert run_problems(w) == []


@pytest.mark.parametrize(
    "model, completion, api, contract, label",
    [
        (model, completion, api, contract, label)
        for model, completion, api, contract in [
            ("gpt-6-luna", stateless_responses_model, "responses", "tool"),
            ("gemini-3.1-pro-preview", stateless_json_model, "chat", "json"),
        ]
        for label in labels_of(model)
    ],
)
def test_the_runner_sends_the_treatment_conversation(
    world, label, model, completion, api, contract
):
    """Compare every provider request and calculation against the unchanged
    treatment harness at 6b00a6f0, including the tool-result continuation.

    Gemini 3.1's board profile exercises JSON; both confirmatory Geminis use
    the tool contract. No contract or model card is replaced for this test."""
    w = world(models=(model,))
    lanes, sid = w.run.lanes[model], w.draw_order[0]
    requests, calculations = [], []

    def provider(**kwargs):
        """Keep each request before the conversation can extend its messages."""
        requests.append(copy.deepcopy(kwargs))
        return completion(**kwargs)

    def tool(arguments):
        """Keep exactly what the conversation sends to the calculator."""
        calculations.append(arguments)
        return {"results": {"snap": {"values": {"spm": 1.0}}}}, 0.0

    lanes.completion = provider
    record = cr.converse_with_harness(
        lanes, sid, label, tool, cr.AttemptSpend(w.run.ceiling)
    )
    sent, called = requests[:], calculations[:]
    requests.clear()
    calculations.clear()
    profile = pilot.model_profile(
        model, arm=cr.arm_string(label), prompt_version="v2-pilot"
    )
    treatment = pilot.run_household(
        w.board["scenarios"][sid],
        w.board["variables"][sid],
        tool,
        provider,
        pilot.Spend(100.0),
        profile=profile,
    )
    assert record["api"] == treatment["api"] == api
    assert record["contract"] == treatment["contract"] == contract
    assert record["status"] == treatment["status"] == "complete"
    assert record["predictions"] == treatment["predictions"] == {
        v: 0.0 for v in VARIABLES
    }
    assert len(sent) == len(requests) == 2
    assert sent == requests and called == calculations and len(called) == 1
    assert record["messages"] == treatment["messages"]
    first, second = sent
    if api == "responses":
        assert "messages" not in first and "previous_response_id" not in first
        assert first["tool_choice"] == "required"
        assert [t["name"] for t in first["tools"]] == [
            pilot.TOOL_NAME,
            "submit_outputs",
        ]
        assert "max_output_tokens" in first
        assert second["previous_response_id"] == "resp_c1"
        assert second["input"] == [
            {
                "type": "function_call_output",
                "call_id": "c1",
                "output": json.dumps({"results": {"snap": {"values": {"spm": 1.0}}}}),
            }
        ]
    else:
        assert "input" not in first and first["tool_choice"] == "auto"
        assert [t["function"]["name"] for t in first["tools"]] == [pilot.TOOL_NAME]
        assert second["messages"][-1]["role"] == "tool"
        assert second["messages"][-1]["tool_call_id"] == "c1"


def test_the_ceiling_ends_a_harness_conversation_at_its_next_turn(world):
    model = "claude-haiku-5.5"
    w = world(models=(model,), overall_cap=0.0, spent_before=25.0 - 1e-9)
    w.run.converse = cr.converse_with_harness
    w.run.completion_for = lambda profile: stateless_model
    w.execute()
    # The first turns cross the ceiling; each conversation under way ends
    # budget_stop before its next request, and no attempt starts after.
    attempts = w.attempts(model)
    assert attempts and {x["status"] for x in attempts} == {"budget_stop"}
    assert len(attempts) <= 2  # one per lane at most
    assert len(w.events(model, "ceiling")) == 1
    assert run_problems(w) == []


def test_a_reader_that_keeps_raising_starts_the_sampler_silence(
    tmp_path, fast, monkeypatch
):
    readers = Readers()
    host = readers.host(tmp_path)
    host._stop.set()
    host._thread.join()
    now, reads = [time.time()], []

    def pressure():
        reads.append(now[0])
        raise RuntimeError("pressure reader failed")

    class Ticks:
        def wait(self, timeout):
            now[0] += cr.SAMPLER_SILENCE + 1.0
            return len(reads) == 3

    # Run the real sampling loop across three failures with a controlled
    # clock; no scheduling or sleep decides whether its silence has elapsed.
    with monkeypatch.context() as patch:
        patch.setattr(cr.time, "time", lambda: now[0])
        patch.setattr(host, "_stop", Ticks())
        patch.setattr(host, "_read_pressure", pressure)
        patch.setattr(host._thread, "is_alive", lambda: True)
        host._loop()
        assert len(reads) == 3
        assert host.failing_since == reads[0]
        assert "samples failing since" in host.dead()
        assert "RuntimeError: pressure reader failed" in host.dead()
        patch.setattr(host, "_read_pressure", lambda: 1)
        host.sample()
        assert host.failing_since is None and host.failure is None
        assert host.dead() is None
    host.close()


def test_a_second_lane_s_authentication_failure_invalidates_a_resume(
    world, monkeypatch
):
    model = "gpt-6-luna"
    w = world(models=(model,))
    lanes = w.run.lanes[model]
    first, second = w.draw_order[:2]
    lanes.spent.update({first: 0.0, second: 0.0})
    now = [time.time()]

    def tick():
        now[0] += 1.0
        return now[0]

    monkeypatch.setattr(cr, "clock", tick)
    auth = record("provider_error", "AuthenticationError: bad key", turns=0)
    lanes.end_attempt(first, "pe3", 1, now[0], auth, False)
    note = {"time": lanes.paused_at, "note": "first key fixed"}
    cr.write_json(lanes.folder / "RESUME.json", note)
    resume = lanes.resume

    def second_failure(*args, **kwargs):
        # The other lane finishes after watch reads the note and immediately
        # before resume validates it. The second pause requires its own note.
        lanes.end_attempt(second, "pe3", 1, now[0], auth, False)
        return resume(*args, **kwargs)

    monkeypatch.setattr(lanes, "resume", second_failure)
    w.run.watch(anchor=False)
    assert lanes.paused and lanes.paused_at > note["time"]
    assert len(w.events(model, "pause")) == 2
    assert w.events(model, "resume") == []
    assert list(lanes.folder.glob("resume-ignored-*.json"))
    monkeypatch.setattr(lanes, "resume", resume)
    cr.write_json(
        lanes.folder / "RESUME.json",
        {"time": lanes.paused_at, "note": "both keys fixed"},
    )
    w.run.watch(anchor=False)
    assert not lanes.paused
    assert [event["reason"] for event in w.events(model, "resume")] == [
        "both keys fixed"
    ]


def test_an_interrupt_during_setup_starts_no_pool_or_lane(world, monkeypatch):
    started = []
    w = world(
        models=("gpt-6-luna", "gpt-6-sol"),
        pool=lambda lanes: started.append((lanes.model, "pool")),
    )

    def completion(profile):
        if w.run.signalled is None:
            w.run.interrupt(2, None)

    w.run.completion_for = completion
    for model, lanes in w.run.lanes.items():
        monkeypatch.setattr(
            lanes, "lane", lambda lane, m=model: started.append((m, lane))
        )
    w.execute()
    assert started == [] and w.provider.count == {}
    for model in w.models:
        assert [e["cause"] for e in w.events(model, "stop")] == ["interrupt"]
        setup = [e for e in w.events(model) if e.get("phase") == "startup"]
        assert [e["event"] for e in setup] == ["setup-start", "setup-end"]
        assert setup[0]["start"] == setup[0]["time"] == setup[1]["start"]
        stop = w.events(model, "stop")[0]["time"]
        assert setup[0]["time"] <= stop <= setup[1]["time"]
        assert setup[1]["outcome"] == "stopped"
    assert run_problems(w) == []


def test_a_slow_pool_start_is_polled_and_anchored_before_it_finishes(
    world, monkeypatch
):
    model = "gpt-6-sol"
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    polls, anchors = [], []

    def pool(lanes):
        entered.set()
        # Readiness depends on supervision, never on which sleep wins.
        assert release.wait(10), "startup was not supervised"
        finished.set()
        return FakePool(lanes)

    w = world(models=(model,), pool=pool)
    watch, anchor = w.run.watch, w.run.anchor

    def supervised(*args, **kwargs):
        watch(*args, **kwargs)
        if entered.is_set() and not finished.is_set():
            polls.append(cr.clock())
            if len(polls) == 3:
                release.set()

    def anchored(*args, **kwargs):
        if entered.is_set() and not finished.is_set():
            anchors.append(cr.clock())
        return anchor(*args, **kwargs)

    monkeypatch.setattr(w.run, "watch", supervised)
    monkeypatch.setattr(w.run, "anchor", anchored)
    w.execute()
    assert len(polls) >= 3 and anchors
    setup = [e for e in w.events(model) if e.get("phase") == "startup"]
    assert setup[0]["time"] <= min(polls + anchors)
    assert max(polls + anchors) <= setup[1]["time"]
    assert setup[1]["outcome"] == "ready"
    assert all(a["start"] >= setup[1]["time"] for a in w.attempts(model))
    assert run_problems(w) == []


def test_an_interrupt_during_pool_start_is_recorded_before_readiness(
    world, monkeypatch
):
    model = "gpt-6-sol"
    stopped = threading.Event()
    started = []

    def pool(lanes):
        w.run.interrupt(2, None)
        assert stopped.wait(10), "the setup interrupt was not processed"
        return FakePool(lanes)

    w = world(models=(model,), pool=pool)
    watch = w.run.watch

    def supervised(*args, **kwargs):
        watch(*args, **kwargs)
        if w.run.lanes[model].stopped:
            stopped.set()

    monkeypatch.setattr(w.run, "watch", supervised)
    monkeypatch.setattr(w.run.lanes[model], "lane", started.append)
    w.execute()
    assert stopped.is_set() and started == []
    assert [e["cause"] for e in w.events(model, "stop")] == ["interrupt"]
    assert w.events(model, "setup-end")[0]["outcome"] == "stopped"
    assert w.run.lanes[model].pool.closed
    assert run_problems(w) == []


def test_an_interrupt_between_lane_launches_prevents_the_next_lane(world, monkeypatch):
    model = "gpt-6-sol"
    w = world(models=(model,))
    signalled = threading.Event()
    started = []
    start = threading.Thread.start

    def lane(number):
        started.append(number)
        w.run.interrupt(2, None)
        signalled.set()

    def start_and_signal(thread):
        start(thread)
        if thread.name == f"{model}-1":
            assert signalled.wait(10)

    monkeypatch.setattr(w.run.lanes[model], "lane", lane)
    monkeypatch.setattr(threading.Thread, "start", start_and_signal)
    w.execute()
    assert started == [1]
    assert [e["cause"] for e in w.events(model, "stop")] == ["interrupt"]
    assert run_problems(w) == []


def test_stop_all_notifies_every_model_before_a_failed_event_write(world, monkeypatch):
    w = world(models=("gpt-6-luna", "gpt-6-sol"))
    notified = []
    for model, lanes in w.run.lanes.items():
        notify = lanes.cond.notify_all

        def observed(model=model, notify=notify):
            notified.append(model)
            notify()

        monkeypatch.setattr(lanes.cond, "notify_all", observed)
    first = w.run.lanes[w.models[0]]

    def broken(line, name="run-log.jsonl"):
        assert all(lanes.stopped for lanes in w.run.lanes.values())
        raise OSError("the first model's event log is unavailable")

    monkeypatch.setattr(first, "write_line", broken)
    w.run.stop_all("disk failure", "runner-error")
    assert notified == list(w.models)
    assert all(lanes.stopped for lanes in w.run.lanes.values())
    assert w.events(w.models[1], "stop")[0]["cause"] == "runner-error"


@pytest.mark.parametrize(
    "kind,error", [("pause", "AuthenticationError"), ("stop", "BadRequestError")]
)
def test_end_attempt_retains_the_record_before_a_failed_event_write(
    world, monkeypatch, kind, error
):
    model = "gpt-6-luna"
    w = world(models=(model, "gpt-6-sol"))
    sid = w.draw_order[0]
    lanes = w.run.lanes[model]
    label = lanes.orders[sid][0]
    w.provider.specs = {
        (model, label, sid, 1): {
            "status": "provider_error",
            "error": f"{error}: a test",
            "turns": 0 if kind == "stop" else 1,
        }
    }
    write = lanes.write_line
    failed = []

    def broken(line, name="run-log.jsonl"):
        if line.get("event") == kind and not failed:
            failed.append(line)
            raise OSError("end_attempt's event write failed")
        write(line, name)

    monkeypatch.setattr(lanes, "write_line", broken)
    w.execute()
    assert len(failed) == 1
    record = json.loads((w.folder(model, label) / f"{sid}.json").read_text())
    assert record["error"] == f"{error}: a test"
    assert record["totals"]["cost_usd"] == pytest.approx(0 if kind == "stop" else COST)
    lines = w.lines(model)
    saved = next(
        i
        for i, x in enumerate(lines)
        if x.get("household") == sid and x.get("arm") == label
    )
    stopped = next(i for i, x in enumerate(lines) if x.get("cause") == "runner-error")
    assert saved < stopped
    assert all(lanes.stopped for lanes in w.run.lanes.values())
    assert (
        lanes.folder / "in-flight" / sid
    ).exists() is False  # event failed before disk write


def test_a_final_record_write_failure_still_recovers_the_other_arms(world, monkeypatch):
    model = "gpt-6-luna"
    w = world(models=(model,))
    sid = w.draw_order[0]
    w.run.no_output.update(w.draw_order[1:])
    first = w.run.lanes[model].orders[sid][0]
    target = w.folder(model, first) / f"{sid}.json"
    write = cr.write_json

    def broken(path, payload, indent=1):
        if Path(path) == target:
            raise OSError("one final record cannot be written")
        return write(path, payload, indent)

    monkeypatch.setattr(cr, "write_json", broken)
    w.execute()
    assert len(w.attempts(model)) == len(cr.ARMS) - 1
    assert all(
        (w.folder(model, a) / f"{sid}.json").exists() for a in cr.ARMS if a != first
    )
    assert (w.run.lanes[model].folder / "in-flight" / sid / f"{first}-1.json").exists()
    assert w.lines(model)[-1]["cause"] == "runner-error"


def blocked_cleanup_request(w, monkeypatch):
    """One real request, released by the test after the abandoned join."""
    monkeypatch.setattr(cr, "ATTEMPT_DEADLINE", 0.02)
    monkeypatch.setattr(cr, "LATE_JOIN", 0.0)
    monkeypatch.setattr(cr, "CEILING_MARGIN", 0.0)
    w.design.update(overall_cap=0.10, spent_before=0.0)
    w.run.no_output.update(w.draw_order[1:])
    w.run.ceiling = cr.Ceiling(0.10, 0.0)
    release, returned = threading.Event(), threading.Event()

    def converse(lanes, sid, label, tool_call, spend):
        assert release.wait(30)
        spend.add(0.20)
        returned.set()
        return {"status": "budget_stop", "turns": [], "totals": {"cost_usd": 0.20}}

    w.run.converse = converse
    return release, returned


def test_cleanup_counts_a_request_returning_during_host_close(world, monkeypatch):
    model = "gpt-6-luna"
    w = world(models=(model,))
    release, returned = blocked_cleanup_request(w, monkeypatch)
    host_factory = w.run.host_factory

    def host(folder):
        evidence = host_factory(folder)
        close = evidence.close

        def finish():
            release.set()
            assert returned.wait(10)
            for lanes in w.run.lanes.values():
                for item in list(lanes.abandoned):
                    item["thread"].join(timeout=10)
                    assert not item["thread"].is_alive()
            close()

        evidence.close = finish
        return evidence

    w.run.host_factory = host
    try:
        w.execute()
    finally:
        release.set()
    assert returned.is_set()
    assert w.run.ceiling.spent_usd == pytest.approx(0.20)
    assert w.run.ceiling.closed
    assert [e["cost_usd"] for e in w.events(model, "late-cost")] == [
        pytest.approx(0.20)
    ]
    assert len(w.events(model, "ceiling")) == 1
    assert w.events(model, "late-unresolved") == []
    assert anchor_problems(w) == []
    assert run_problems(w) == []


@pytest.mark.parametrize("returns_at_close", [False, True])
def test_cleanup_records_an_unresolved_request_before_closing_the_ledger(
    world, monkeypatch, returns_at_close
):
    model = "gpt-6-luna"
    w = world(models=(model,))
    release, returned = blocked_cleanup_request(w, monkeypatch)
    if returns_at_close:
        close = w.run.ceiling.close

        def finish(pending=None):
            unresolved = close(pending)
            release.set()
            assert returned.wait(10)
            return unresolved

        monkeypatch.setattr(w.run.ceiling, "close", finish)
    try:
        w.execute()
        unresolved = w.events(model, "late-unresolved")
        assert len(unresolved) == 1
        assert unresolved[0]["outcome"] == "unresolved-at-ledger-close"
        assert unresolved[0]["counted_usd"] == 0.0
        assert w.events(model, "stop")[-1]["cause"] == "runner-error"
        assert w.run.ceiling.closed
        assert anchor_problems(w) == []
        before = (w.runs() / model / "run-log.jsonl").read_bytes()
    finally:
        release.set()
        assert returned.wait(10)
    assert w.run.ceiling.spent_usd == 0.0
    assert w.run.ceiling.unrecorded_usd == pytest.approx(0.20)
    assert (w.runs() / model / "run-log.jsonl").read_bytes() == before


@pytest.mark.parametrize("during", ["host-close", "final-push"])
def test_a_first_interrupt_during_cleanup_is_recorded_and_anchored(
    world, monkeypatch, during
):
    model = "gpt-6-sol"
    w = world(models=(model,))
    w.run.no_output.update(w.draw_order)
    if during == "host-close":
        host_factory = w.run.host_factory

        def host(folder):
            evidence = host_factory(folder)
            close = evidence.close

            def finish():
                w.run.interrupt(2, None)
                close()

            evidence.close = finish
            return evidence

        w.run.host_factory = host
    else:
        anchor = w.run.anchor
        signalled = []

        def push(wait=False):
            anchor(wait=wait)
            if wait and not signalled:
                signalled.append(True)
                w.run.interrupt(2, None)

        monkeypatch.setattr(w.run, "anchor", push)
    w.execute()
    assert [e["cause"] for e in w.events(model, "stop")] == ["interrupt"]
    assert w.run._interrupted
    assert anchor_problems(w) == []


def test_a_replacement_log_failure_keeps_a_valid_final_history(world, monkeypatch):
    model = "gpt-6-luna"
    w = world(models=(model,))
    sid = w.draw_order[0]
    w.run.no_output.update(w.draw_order[1:])
    lanes = w.run.lanes[model]
    label = lanes.orders[sid][0]
    w.provider.specs = {
        (model, label, sid, 1): {
            "status": "provider_error",
            "error": "RateLimitError: a test",
        }
    }
    write, failed = lanes.write_line, []

    def broken(line, name="run-log.jsonl"):
        if line.get("arm") == label and line.get("attempt") == 1 and not failed:
            failed.append(line)
            raise OSError("the replaced attempt's log write failed")
        write(line, name)

    monkeypatch.setattr(lanes, "write_line", broken)
    w.execute()
    rec = json.loads((w.folder(model, label) / f"{sid}.json").read_text())
    assert rec["attempts"] == []
    assert w.provider.count[(model, label, sid)] == 1
    logged = [x for x in w.attempts(model) if x["arm"] == label]
    assert len(logged) == 1
    assert all(
        logged[0][key] == value for key, value in failed[0].items() if key != "sha256"
    )
    assert logged[0]["sha256"] == cr.sha256_file(w.folder(model, label) / f"{sid}.json")
    assert run_problems(w) == []


def test_a_supervision_error_drains_active_lanes_before_final_anchor(
    world, monkeypatch
):
    model = "gpt-6-sol"
    w = world(models=(model,))
    w.run.no_output.update(w.draw_order[1:])
    started, returned = threading.Event(), threading.Event()
    converse, watch = w.run.converse, w.run.watch
    failed = []

    def request(*args):
        started.set()
        assert w.run._failed.wait(10)
        rec = converse(*args)
        returned.set()
        return rec

    def broken_watch(anchor=True):
        if started.is_set() and not failed:
            failed.append(True)
            raise OSError("supervision failed while a request was active")
        watch(anchor=anchor)

    w.run.converse = request
    monkeypatch.setattr(w.run, "watch", broken_watch)
    with pytest.raises(OSError, match="supervision failed"):
        w.execute()
    assert returned.is_set()
    assert len(w.attempts(model)) == 1
    assert w.lines(model)[-1]["cause"] == "runner-error"
    assert w.run.ceiling.spent_usd == pytest.approx(1.0 + COST)
    assert anchor_problems(w) == []
    assert run_problems(w) == []


def final_push_world(world, monkeypatch, fail_all=False, models=("gpt-6-luna",)):
    """A run with no periodic pushes, whose first final push fails."""
    w = world(models=models)
    w.run.no_output.update(w.draw_order)
    monkeypatch.setattr(w.run, "anchor_due", lambda: False)
    monkeypatch.setattr(cr, "ANCHOR_RETRY", 0.013)
    script = w.tmp / "retrying-anchor.py"
    script.write_text(
        "import shutil, sys\n"
        "from pathlib import Path\n"
        "folder = Path(sys.argv[1])\n"
        "counter = folder / 'push-count'\n"
        "n = int(counter.read_text()) + 1 if counter.exists() else 1\n"
        "counter.write_text(str(n))\n"
        "shutil.copyfile(sys.argv[3], folder / f'pushed-{n}.jsonl')\n"
        "raise SystemExit(1 if n == 1 or sys.argv[2] == '1' else 0)\n"
    )
    w.design["anchor_command"] = [
        sys.executable,
        str(script),
        str(w.tmp),
        str(int(fail_all)),
    ]
    return w


@pytest.mark.parametrize("fail_all", [False, True], ids=["then-success", "all-fail"])
def test_the_final_push_is_retried_until_success_or_three_tries(
    world, monkeypatch, fail_all
):
    """Final retries stop at the first success, or after three failures."""
    w = final_push_world(world, monkeypatch, fail_all=fail_all)
    w.execute()
    anchors = [
        json.loads(x) for x in (w.runs() / "anchors.jsonl").read_text().splitlines()
    ]
    pushes = [
        json.loads(x)
        for x in (w.runs() / "anchor-pushes.jsonl").read_text().splitlines()
    ]
    expected = 3 if fail_all else 2
    assert cr.FINAL_PUSH_TRIES == 3
    assert len(pushes) == len(anchors) == expected
    assert [row["outcome"] for row in pushes] == (
        ["failed"] * 3 if fail_all else ["failed", "success"]
    )
    final = (w.runs() / "anchors.jsonl").read_bytes()
    assert (w.tmp / f"pushed-{expected}.jsonl").read_bytes() == final
    assert pushes[-1]["anchor"] == cr.line_sha(final.decode().splitlines()[-1])
    assert pushes[-1]["anchor_time"] == anchors[-1]["time"]
    assert all(a["models"] == anchors[0]["models"] for a in anchors)
    assert all(a["host-log.jsonl"] == anchors[0]["host-log.jsonl"] for a in anchors)
    assert all(a["time"] < b["time"] for a, b in zip(anchors, anchors[1:]))


def test_each_final_push_retry_waits_from_the_previous_try_s_end(world, monkeypatch):
    """Each final retry starts at least ANCHOR_RETRY after the prior try ends,
    even when the failed command itself takes time."""
    from types import SimpleNamespace

    w = world(models=("gpt-6-luna",))
    now = [1000.0]
    durations = iter([7.0, 11.0, 5.0])
    monkeypatch.setattr(cr, "clock", lambda: now[0])

    def sleep(seconds):
        """Advance the controlled clock by the requested wait."""
        now[0] += seconds

    def failed_command(*args, **kwargs):
        """A failed anchor command with a controlled, nonzero duration."""

        def communicate(timeout):
            """Finish the command after its planted duration."""
            now[0] += next(durations)
            return "", "controlled push failure"

        return SimpleNamespace(returncode=1, communicate=communicate)

    monkeypatch.setattr(time, "sleep", sleep)
    monkeypatch.setattr(subprocess, "Popen", failed_command)
    w.run.finish()
    pushes = [
        json.loads(x)
        for x in (w.runs() / "anchor-pushes.jsonl").read_text().splitlines()
    ]
    assert len(pushes) == cr.FINAL_PUSH_TRIES == 3
    assert [p["outcome"] for p in pushes] == ["failed"] * 3
    assert [p["ended"] - p["started"] for p in pushes] == [7.0, 11.0, 5.0]
    assert all(
        b["started"] >= a["ended"] + cr.ANCHOR_RETRY
        for a, b in zip(pushes, pushes[1:])
    )


def test_a_first_signal_during_final_push_retries_is_logged_and_anchored(
    world, monkeypatch
):
    """A first signal during the retry wait is covered by the last push."""
    w = final_push_world(world, monkeypatch, models=("gpt-6-luna", "gpt-6-sol"))
    sleep, delivered = time.sleep, []

    def during_retry(seconds):
        if seconds == cr.ANCHOR_RETRY and not delivered:
            delivered.append(True)
            w.run.interrupt(signal.SIGTERM, None)
        sleep(seconds)

    monkeypatch.setattr(time, "sleep", during_retry)
    w.execute()
    assert delivered and w.run._interrupted
    anchors = [
        json.loads(x) for x in (w.runs() / "anchors.jsonl").read_text().splitlines()
    ]
    pushes = [
        json.loads(x)
        for x in (w.runs() / "anchor-pushes.jsonl").read_text().splitlines()
    ]
    assert [row["outcome"] for row in pushes] == ["failed", "success", "success"]
    for model in w.models:
        assert [row["cause"] for row in w.events(model, "stop")] == ["interrupt"]
        assert anchors[-1]["models"][model]["run-log.jsonl"] == (
            w.run.lanes[model].heads()["run-log.jsonl"]
        )
        assert anchors[-2]["models"][model]["run-log.jsonl"]["lines"] == (
            len(w.lines(model)) - 1
        )
    assert (w.tmp / "pushed-3.jsonl").read_bytes() == (
        w.runs() / "anchors.jsonl"
    ).read_bytes()


def test_a_second_signal_during_final_push_retries_exits_at_once(world, monkeypatch):
    """The retry wait leaves the second signal's immediate exit intact."""
    w = final_push_world(world, monkeypatch)
    sleep, delivered = time.sleep, []

    def exit_now(code):
        raise SystemExit(code)

    def during_retry(seconds):
        if seconds == cr.ANCHOR_RETRY and not delivered:
            delivered.append(True)
            w.run.interrupt(signal.SIGINT, None)
            w.run.interrupt(signal.SIGTERM, None)
        sleep(seconds)

    monkeypatch.setattr(os, "_exit", exit_now)
    monkeypatch.setattr(time, "sleep", during_retry)
    with pytest.raises(SystemExit) as stopped:
        w.execute()
    assert stopped.value.code == 130 and delivered
    assert len((w.runs() / "anchor-pushes.jsonl").read_text().splitlines()) == 1
    assert all(not w.events(model, "stop") for model in w.models)


def test_a_signal_at_the_final_ignore_hook_is_logged_and_anchored(world, monkeypatch):
    """A signal between the last ordinary check and SIG_IGN is not lost."""
    w = world(models=("gpt-6-luna", "gpt-6-sol"))
    w.run.no_output.update(w.draw_order)
    monkeypatch.setattr(w.run, "anchor_due", lambda: False)
    ignore = w.run._ignore_signals
    ignored, delivered = [], []
    monkeypatch.setattr(
        signal, "signal", lambda signum, handler: ignored.append((signum, handler))
    )

    def at_end():
        if not delivered:
            delivered.append(True)
            w.run.interrupt(signal.SIGTERM, None)
        ignore()

    monkeypatch.setattr(w.run, "_ignore_signals", at_end)
    w.execute()
    assert delivered and w.run._interrupted
    assert (signal.SIGINT, signal.SIG_IGN) in ignored
    assert (signal.SIGTERM, signal.SIG_IGN) in ignored
    for model in w.models:
        stops = w.events(model, "stop")
        assert len(stops) == 1 and stops[0]["cause"] == "interrupt"
        assert stops[0]["reason"] == f"operator stop (signal {signal.SIGTERM})"
    assert anchor_problems(w) == []


def test_a_final_push_log_failure_is_stopped_and_locally_anchored(world, monkeypatch):
    model = "gpt-6-sol"
    w = world(models=(model,))
    w.run.no_output.update(w.draw_order)
    push = w.run._push_anchor

    def broken(head, anchor_time):
        if w.run.host.end is not None:
            with w.run._pushing:
                w.run._push_error = OSError("the final push outcome cannot be written")
        else:
            push(head, anchor_time)

    monkeypatch.setattr(w.run, "_push_anchor", broken)
    with pytest.raises(OSError, match="push outcome could not be recorded"):
        w.execute()
    assert w.events(model, "stop")[-1]["cause"] == "runner-error"
    last = json.loads((w.runs() / "anchors.jsonl").read_text().splitlines()[-1])
    assert last["models"][model]["run-log.jsonl"]["lines"] == len(w.lines(model))
    assert last["host-log.jsonl"] == w.run.host.heads()
