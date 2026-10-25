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

import hashlib
import io
import json
import math
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


def test_the_error_classes_are_policybench_s():
    from policybench import eval_no_tools as e

    assert cr.TRANSPORT == {c.__name__ for c in e.RETRYABLE_PROVIDER_ERRORS}
    assert cr.REQUEST | cr.ACCOUNT == {c.__name__ for c in e.MODEL_FATAL_ERRORS}
    assert not cr.REQUEST & cr.ACCOUNT
    assert not cr.TRANSPORT & (cr.REQUEST | cr.ACCOUNT)


# ---------------------------------------------------------------- classes


def record(status="complete", error=None, turns=1, calls=(), truncated=False):
    turn = {"calls": [{"result": r} for r in calls]}
    out = [dict(turn) for _ in range(turns)]
    if truncated:
        out = [{"truncated_and_retried": True}]
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
    kept = cr.excerpt(text, lambda x: cr.guard_time(x, zone), t, t + 5)
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


@pytest.fixture
def fast(monkeypatch):
    """Windows scaled down a thousandfold, so a fake run takes a second; the
    host-log gap less, so a sampler a busy host stalls past 90 ms (seen at a
    load of 12) is not a gap."""
    monkeypatch.setattr(cr, "PRESSURE_WINDOW", 0.06)
    monkeypatch.setattr(cr, "HOST_LOG_GAP", 0.5)
    monkeypatch.setattr(cr, "WAIT_SECONDS", 0.005)
    monkeypatch.setattr(cr, "HOUSEHOLDS", N_DRAW)


def test_the_host_log_samples_and_closes(tmp_path, fast):
    readers = Readers()
    host = readers.host(tmp_path)
    time.sleep(0.1)
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
    time.sleep(0.05)
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
    readers.stall = 0.8
    time.sleep(0.85)
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
    (seconds after which the operator resumes) and `raise` (the conversation
    raises)."""

    def __init__(self, world, specs=None):
        self.world, self.specs = world, specs or {}
        self.count: dict = {}
        self.lock = threading.Lock()

    def __call__(self, lanes, sid, label, tool_call):
        model = lanes.model
        with self.lock:
            n = self.count[(model, label, sid)] = (
                self.count.get((model, label, sid), 0) + 1
            )
        spec = self.specs.get((model, label, sid, n), {})
        readers = self.world.readers
        if spec.get("raise"):
            raise RuntimeError("a test raised")
        if spec.get("pressure"):
            with readers.lock:
                readers.pressing += 1
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
        spend = lanes.run.ceiling
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
                cr.write_json(folder / "RESUME.json", {"note": "fixed in a test"})

            threading.Timer(spec["resume_after"], resume).start()
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
            "caps": {m: (caps or {}).get(m, 10.0) for m in cr.CHEAP + cr.FRONTIER},
            "reserves": {m: reserve for m in cr.CHEAP + cr.FRONTIER},
            "overall_cap": overall_cap,
            "spent_before": spent_before,
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
    times = sorted(float(s["time"]) for s in samples)
    for a, b in zip([start] + times, times + [end]):
        if b - a > cr.HOST_LOG_GAP:
            spans.append((a, b, "host log gap"))
    pressure = [float(s["time"]) for s in samples if int(s.get("pressure") or 0) > 1]

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


def run_problems(world: World) -> list[str]:
    """Every rule of the run procedure, recomputed from the runner's files."""
    problems: list[str] = []
    host = host_from_files(world.runs() / "host")
    position = {sid: i for i, sid in enumerate(world.draw_order)}
    master = cr.master_seed(world.design["frozen_sha256"])
    all_attempts = []
    ceiling_events = {}
    for model in world.models:
        labels = labels_of(model)
        drawn = cr.orders(master, model, world.draw_order, labels)
        lines = world.attempts(model)
        events = world.events(model)
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
    # Conservation: the ceiling counted exactly the records' spend.
    if abs(world.run.ceiling.spent_usd - total) > 1e-9:
        problems.append(
            f"the ceiling counted {world.run.ceiling.spent_usd}, records {total}"
        )
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
        (model, "pe", stalled, 1): {"stall": 0.8},
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


def test_a_guard_pause_over_an_attempt_reruns_it(world):
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
    assert [x["event"] for x in w.lines("gpt-6-sol")] == ["ceiling"]
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
    assert run_problems(w) == []


def test_a_household_a_stop_cuts_short_is_under_way_until_the_stop(world):
    """Lane 1's first household loses the pool in its first arm, and the
    restart fails 0.6 s later. In between, lane 2 finishes its household and
    decides its next: the household lane 1 cut short has ended its last
    attempt, but it is still under way, so its spend is not counted."""
    model = "gpt-6-sol"
    made = []

    class Losing(FakePool):
        def call(self, message):
            self.lost = 2
            return super().call(message)

    def pool(lanes):
        made.append(1)
        if len(made) > 1:
            time.sleep(0.6)
            raise RuntimeError("tool worker failed to start: a test")
        return Losing(lanes)

    w = world(models=(model,), pool=pool)
    cut, other, after = w.draw_order[0], w.draw_order[1], w.draw_order[3]
    orders = w.run.lanes[model].orders
    w.provider.specs = {
        (model, orders[cut][0], cut, 1): {"sleep": 0.1, "calls": [{"situation": "{}"}]},
        (model, orders[other][0], other, 1): {"sleep": 0.02},
        (model, orders[other][1], other, 1): {"sleep": 0.3},
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
    assert run_problems(w) == []


def test_an_interrupt_stops_every_model_and_lets_attempts_end(world):
    w = world(models=("gpt-6-luna", "gpt-6-sol"))
    sid = w.draw_order[0]
    w.provider.specs = {("gpt-6-luna", lbl, sid, 1): {"sleep": 0.1} for lbl in cr.ARMS}
    threading.Timer(0.15, lambda: w.run.interrupt(2, None)).start()
    w.execute()
    for m in w.models:
        stops = w.events(m, "stop")
        assert len(stops) == 1 and stops[0]["reason"] == "operator stop (signal 2)"
        assert not [x for x in w.attempts(m) if x["start"] > stops[0]["time"]]
    luna = [x for x in w.attempts("gpt-6-luna") if x["household"] == sid]
    assert luna and len(luna) < len(cr.ARMS)  # cut by the stop
    assert run_problems(w) == []


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
    first = json.loads(lines[0])
    first["class"] = "provider"
    path.write_text("\n".join([json.dumps(first)] + lines[1:]) + "\n")
    assert any("recomputed" in p for p in run_problems(w))


# ---------------------------------------------------------------- before a run


def test_the_preflight_names_a_missing_field():
    assert cr.preflight({}, cr.CHEAP) == [f"the design has no {', '.join(cr.REQUIRED)}"]


def test_the_preflight_refuses_a_changed_draw_and_a_dirty_runner(
    world, tmp_path, monkeypatch
):
    w = world(models=("gpt-6-luna",))
    pool = tmp_path / "pool.json"
    pool.write_text(json.dumps([{"id": s} for s in POOL]))
    design = dict(
        w.design,
        eligible_pool={"path": str(pool), "sha256": cr.sha256_file(pool)},
        treatment_harness=str(cr.ROOT),
        run_commit="0" * 40,
        draw_order=list(reversed(w.draw_order)),
    )
    monkeypatch.setattr(cr, "host_power", lambda: (True, False))
    problems = cr.preflight(design, ("gpt-6-luna",))
    text = "\n".join(problems)
    assert "the draw, recomputed" in text
    assert "not the run commit, clean" in text
    assert "lid open False" in text
    design["draw_order"] = w.draw_order
    assert "the draw" not in "\n".join(cr.preflight(design, ("gpt-6-luna",)))


def test_the_preflight_refuses_a_runs_folder_with_records(world, tmp_path):
    w = world(models=("gpt-6-luna",)).execute()
    pool = tmp_path / "pool.json"
    pool.write_text(json.dumps([{"id": s} for s in POOL]))
    design = dict(
        w.design,
        eligible_pool={"path": str(pool), "sha256": cr.sha256_file(pool)},
        treatment_harness=str(cr.ROOT),
        run_commit="0" * 40,
    )
    text = "\n".join(cr.preflight(design, ("gpt-6-luna",)))
    assert "already holds records" in text and "already holds a host log" in text


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


def test_the_harness_conversation_runs_under_the_runner(world):
    model = "claude-haiku-5.5"
    w = world(models=(model,))
    w.run.converse = cr.converse_with_harness
    w.run.completion_for = lambda profile: stateless_model
    w.execute()
    attempts = w.attempts(model)
    assert len(attempts) == N_DRAW * len(cr.ARMS)
    assert {x["status"] for x in attempts} == {"complete"}
    messages = w.run.lanes[model].pool.messages
    assert len(messages) == N_DRAW * len(cr.ARMS)  # one calculation per attempt
    frames = [m for m in messages if isinstance(m, tuple)]
    assert len(frames) == N_DRAW * (len(cr.ARMS) - 1)  # every arm but pe
    sid = w.draw_order[0]
    rec = json.loads((w.folder(model, "loo-names") / f"{sid}.json").read_text())
    profile = cr.arm_profile(model, "loo-names")
    assert rec["arm"] == cr.arm_string("loo-names") and rec["attempts"] == []
    assert rec["tool_features"] == sorted(profile.tool_features)
    assert rec["predictions"] == {v: 0.0 for v in VARIABLES}
    assert run_problems(w) == []


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
