"""Provider-free tests of the no-tools stage's files, retries and shared spend."""

from __future__ import annotations

import ast
import fcntl
import functools
import io
import json
import math
import operator
import os
import signal
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import confirmatory_no_tools as nt  # noqa: E402


@pytest.fixture
def setup(tmp_path, monkeypatch):
    # These state-machine fixtures inject a minimal board and fake records.
    # Real treatment pins and prompts are covered in the saved-record suite.
    monkeypatch.setattr(nt, "validate_treatment", lambda *args: None, raising=False)
    draw = ["h2", "h1"]
    baseline = tmp_path / "baseline-exclusions.json"
    baseline.write_text('{"exclusions": []}\n')
    return {
        "design": {
            "board": "synthetic.csv",
            "engine": "policyengine-us 2.60.4",
            "draw_order": draw,
            "spent_before": nt.NO_TOOLS_CAP,
            "baseline_exclusions": {
                "path": str(baseline),
                "sha256": nt.sha256_file(baseline),
            },
            "no_tools": {
                "runs": str(tmp_path / "no-tools"),
                "folder": "none",
                "stage": "confirmatory",
            },
        },
        "board": {
            "scenarios": {sid: SimpleNamespace(id=sid) for sid in draw},
            "variables": {sid: ["snap"] for sid in draw},
        },
    }


def record(sid, profile, status="complete", error=None, cost=0.1):
    return {
        "scenario_id": sid,
        "model": profile.name,
        "arm": profile.arm,
        "status": status,
        "error": error,
        "turns": [] if status == "harness_error" else [{"model": profile.model_id}],
        "predictions": {"snap": 1},
        "totals": {"cost_usd": cost},
    }


class Provider:
    def __init__(self, planted=None):
        self.planted, self.calls = planted or {}, []
        self.lock = threading.Lock()

    def __call__(
        self, scenario, variables, tool_call, completion_fn, spend, *, profile
    ):
        key = profile.name, scenario.id
        with self.lock:
            n = 1 + sum(call[:2] == key for call in self.calls)
            self.calls.append((*key, n))
        spec = self.planted.get((*key, n), {})
        cost = spec.get("cost", 0.1)
        spend.add(cost)
        if spec.get("raise"):
            raise RuntimeError("synthetic harness failure")
        return record(
            scenario.id,
            profile,
            cost=cost,
            status=spec.get("status", "complete"),
            error=spec.get("error"),
        )


def stage(setup, provider=None, models=None, **kwargs):
    return nt.Stage(
        setup["design"],
        models=models,
        board=setup["board"],
        run_household=provider or Provider(),
        completion_for=lambda profile: None,
        out=io.StringIO(),
        **kwargs,
    )


def final(plan, model=nt.CHEAP[0], sid="h2"):
    return plan.households(model) / f"{sid}.json"


def load(path):
    return json.loads(path.read_text())


def plant(setup, status, error, n=1, **extra):
    return {(nt.CHEAP[0], "h2", n): {"status": status, "error": error, **extra}}


def test_every_household_ok_in_draw_order_and_each_model_has_its_thread(setup):
    provider, threads = Provider(), {}

    def fake(*args, **kwargs):
        threads.setdefault(kwargs["profile"].name, threading.current_thread().name)
        return provider(*args, **kwargs)

    plan = stage(setup, fake)
    assert plan.execute() == 0
    assert all(plan.states[m] == "complete" for m in nt.CHEAP)
    assert len(set(threads.values())) == len(nt.CHEAP)
    for model in nt.CHEAP:
        assert [call[1] for call in provider.calls if call[0] == model] == ["h2", "h1"]
        for sid in setup["design"]["draw_order"]:
            assert load(final(plan, model, sid))["attempts"] == []
    assert plan.spend.spent_usd == pytest.approx(0.6)


def test_provider_rerun_links_the_unchanged_archived_bytes(setup):
    provider = Provider(plant(setup, "provider_error", "APIConnectionError: synthetic"))
    plan = stage(setup, provider, models=[nt.CHEAP[0]])
    written = {}
    original = nt.write_json

    def capture(path, payload, *args, **kwargs):
        result = original(path, payload, *args, **kwargs)
        written.setdefault(path.name, path.read_bytes())
        return result

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(nt, "write_json", capture)
        assert plan.execute() == 0
    path = final(plan)
    archive = path.parent / "attempts/h2-1.json"
    assert archive.read_bytes() == written["h2.json"]
    assert load(path)["attempts"] == [
        {
            "n": 1,
            "file": "attempts/h2-1.json",
            "sha256": nt.sha256_file(archive),
            "status": "provider_error",
            "class": "provider",
            "reason": "APIConnectionError",
        }
    ]
    assert stage(setup, models=[nt.CHEAP[0]]).spend.spent_usd == pytest.approx(0.3)


def test_third_provider_failure_stands_and_has_only_two_archives(setup):
    planted = {
        **plant(setup, "provider_error", "APIConnectionError", 1),
        **plant(setup, "provider_error", "APIConnectionError", 2),
        **plant(setup, "provider_error", "APIConnectionError", 3),
    }
    provider = Provider(planted)
    plan = stage(setup, provider, models=[nt.CHEAP[0]])
    assert plan.execute() == 0
    assert [n for m, sid, n in provider.calls if sid == "h2"] == [1, 2, 3]
    assert len(load(final(plan))["attempts"]) == nt.MAX_RERUNS
    assert load(final(plan))["status"] == "provider_error"


def test_operator_pause_stops_its_model_and_reinvocation_resumes(setup):
    provider = Provider(
        plant(setup, "provider_error", "AuthenticationError: synthetic")
    )
    first = stage(setup, provider)
    assert first.execute() == 1
    assert first.states[nt.CHEAP[0]] == "operator-paused"
    assert not final(first, sid="h1").exists()
    assert first.states[nt.CHEAP[1]] == "complete"
    before = final(first).read_bytes()
    resumed = stage(setup, models=[nt.CHEAP[0]])
    assert resumed.execute() == 0
    assert (final(resumed).parent / "attempts/h2-1.json").read_bytes() == before
    assert load(final(resumed))["attempts"][0]["class"] == "operator"


def test_harness_stop_prevents_later_households_and_persists(setup):
    provider = Provider(plant(setup, "provider_error", "BadRequestError: synthetic"))

    # A request error is a harness class only before a completed turn.
    def early_failure(*args, **kwargs):
        result = provider(*args, **kwargs)
        if result["status"] == "provider_error":
            result["turns"] = []
        return result

    plan = stage(setup, early_failure, models=[nt.CHEAP[0]])
    assert plan.execute() == 1
    assert plan.states[nt.CHEAP[0]] == "harness-stopped"
    assert not final(plan, sid="h1").exists()
    resumed_provider = Provider()
    resumed = stage(setup, resumed_provider, models=[nt.CHEAP[0]])
    assert resumed.execute() == 1
    assert resumed_provider.calls == []


def paused(setup):
    plan = stage(
        setup,
        Provider(plant(setup, "provider_error", "AuthenticationError")),
        models=[nt.CHEAP[0]],
    )
    assert plan.execute() == 1
    return plan


def test_crash_after_archive_resumes_at_the_next_attempt_number(setup, monkeypatch):
    first = paused(setup)
    original = nt.os.replace

    def interrupted(source, target):
        original(source, target)
        if Path(target).parent.name == "attempts":
            raise RuntimeError("synthetic crash after archive")

    monkeypatch.setattr(nt.os, "replace", interrupted)
    with pytest.raises(RuntimeError, match="synthetic crash"):
        first.archive(nt.CHEAP[0], "h2")
    monkeypatch.setattr(nt.os, "replace", original)
    assert not final(first).exists()
    resumed = stage(setup, models=[nt.CHEAP[0]])
    assert resumed.execute() == 0
    assert load(final(resumed))["attempts"][0]["n"] == 1
    assert " h2 2 ok stands " in resumed.out.getvalue()


def test_spend_in_archives_and_optional_models_carries_across_invocations(setup):
    first = paused(setup)
    first.archive(nt.CHEAP[0], "h2")
    optional = stage(setup, models=["gpt-6-sol"])
    assert optional.execute() == 0
    resumed = stage(setup, models=[nt.CHEAP[0]])
    assert resumed.spend.spent_usd == pytest.approx(0.3)
    assert resumed.execute() == 0
    assert resumed.spend.spent_usd == pytest.approx(0.5)


def test_reaching_the_cap_prevents_every_new_attempt_across_invocations(
    setup, monkeypatch
):
    monkeypatch.setattr(nt, "NO_TOOLS_CAP", 0.1)
    plan = stage(setup, models=[nt.CHEAP[0]])
    assert plan.execute() == 1
    assert len(list(plan.households(nt.CHEAP[0]).glob("*.json"))) == 1
    provider = Provider()
    resumed = stage(setup, provider, models=[nt.CHEAP[1]])
    assert resumed.execute() == 1
    assert provider.calls == []
    assert resumed.spend.spent_usd == pytest.approx(0.1)


def test_budget_stop_is_shared_by_all_models(setup):
    provider = Provider(plant(setup, "budget_stop", None))
    plan = stage(setup, provider, models=[nt.CHEAP[0]])
    assert plan.execute() == 1
    assert plan.stopped.is_set()
    resumed = stage(setup, Provider(), models=[nt.CHEAP[1]])
    assert resumed.execute() == 1
    assert resumed.states[nt.CHEAP[1]] == "budget-stopped"


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda r: r.update(prior_attempts=[]), "prior_attempts"),
        (lambda r: r.pop("attempts"), "attempts list"),
    ],
)
def test_refuse_a_final_not_written_by_this_script(setup, mutation, match):
    first = paused(setup)
    path = final(first)
    payload = load(path)
    mutation(payload)
    path.write_text(json.dumps(payload))
    with pytest.raises(nt.StateError, match=match):
        stage(setup)


def test_refuse_an_attempt_number_gap_and_name_its_files(setup):
    first = paused(setup)
    first.archive(nt.CHEAP[0], "h2")
    archive = final(first).parent / "attempts/h2-1.json"
    archive.rename(archive.with_name("h2-2.json"))
    with pytest.raises(nt.StateError, match="attempt-number gap.*h2-2.json"):
        stage(setup)


@pytest.mark.parametrize(
    "field,value", [("sha256", "wrong"), ("n", 2), ("reason", "edited")]
)
def test_refuse_a_final_with_corrupted_attempt_links(setup, field, value):
    paused(setup)
    resumed = stage(setup, models=[nt.CHEAP[0]])
    assert resumed.execute() == 0
    path = final(resumed)
    payload = load(path)
    payload["attempts"][0][field] = value
    path.write_text(json.dumps(payload))
    match = "attempt link n" if field == "n" else "attempts disagree"
    with pytest.raises(nt.StateError, match=match):
        stage(setup)


def test_an_attempt_that_raises_keeps_its_spend(setup):
    provider = Provider(plant(setup, "complete", None, **{"raise": True, "cost": 0.27}))
    plan = stage(setup, provider, models=[nt.CHEAP[0]])
    assert plan.execute() == 0
    archive = final(plan).parent / "attempts/h2-1.json"
    assert load(archive)["status"] == "harness_error"
    assert load(archive)["totals"]["cost_usd"] == 0.27
    assert plan.spend.spent_usd == pytest.approx(0.47)
    assert stage(setup, models=[nt.CHEAP[0]]).spend.spent_usd == pytest.approx(0.47)


def test_dry_run_lists_done_households_and_next_owed_attempt_without_providers(setup):
    first = paused(setup)
    first.archive(nt.CHEAP[0], "h2")
    provider = Provider()
    plan = stage(setup, provider, models=[nt.CHEAP[0]])
    assert plan.dry_run() == 1
    text = plan.out.getvalue()
    assert "done []" in text and "h2:2" in text and "h1:1" in text
    assert "$0.100000" in text
    assert provider.calls == []


def test_each_attempt_uses_none_profile_and_refuses_a_tool_call(setup):
    def fake(scenario, variables, tool_call, completion, spend, *, profile):
        assert profile.arm == "none" and profile.prompt_version == nt.PROMPT_VERSION
        assert variables == ["snap"]
        with pytest.raises(RuntimeError, match="cannot call a tool"):
            tool_call({})
        return record(scenario.id, profile, cost=0)

    assert stage(setup, fake, models=[nt.CHEAP[0]]).execute() == 0


def test_registered_cap_matches_the_report_when_available():
    """The local report is separate from this public repository's dependency tree."""
    configured = os.environ.get("CONFIRMATORY_REPORT")
    candidates = (
        [Path(configured)]
        if configured
        else [Path(__file__).resolve().parents[2] / "report" / "confirmatory_report.py"]
    )
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        pytest.skip("set CONFIRMATORY_REPORT to compare the separate report checkout")
    tree = ast.parse(path.read_text())
    cap = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "NO_TOOLS_CAP"
            for target in node.targets
        )
    )
    assert nt.NO_TOOLS_CAP == cap == 5.0


def test_main_supports_multiple_model_options_and_dry_run(setup, tmp_path, capsys):
    write_board_fixture(setup, tmp_path / "board")
    path = tmp_path / "design.json"
    path.write_text(json.dumps(setup["design"]))
    assert (
        nt.main(
            [
                "run",
                str(path),
                "--model",
                nt.CHEAP[0],
                nt.CHEAP[1],
                "--model",
                nt.CHEAP[2],
                "--dry-run",
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    assert all(model in output for model in nt.CHEAP)


def test_in_flight_models_observe_the_shared_cap_before_their_next_turn(
    setup, monkeypatch
):
    monkeypatch.setattr(nt, "NO_TOOLS_CAP", 0.1)
    ready, charged = threading.Barrier(3), threading.Barrier(3)
    calls = []

    def fake(scenario, variables, tool_call, completion, spend, *, profile):
        calls.append((profile.name, scenario.id))
        ready.wait(timeout=30)
        cost = 0.1 if profile.name == nt.CHEAP[0] else 0.0
        spend.add(cost)
        charged.wait(timeout=30)
        assert spend.exhausted()
        return record(scenario.id, profile, cost=cost)

    plan = stage(setup, fake)
    assert plan.execute() == 1
    assert len(calls) == 3 and all(sid == "h2" for _, sid in calls)
    assert plan.spend.spent_usd == pytest.approx(0.1)


@pytest.mark.parametrize(
    "status,error,expected",
    [
        ("budget_stop", None, "stopped"),
        ("provider_error", "BadRequestError: synthetic", "stop"),
    ],
)
def test_dry_run_marks_harness_and_budget_finals_as_blocked(
    setup, status, error, expected
):
    plan = stage(setup, models=[nt.CHEAP[0]])
    profile = nt.pilot.model_profile(
        nt.CHEAP[0], arm="none", prompt_version=nt.PROMPT_VERSION
    )
    payload = record("h2", profile, status=status, error=error, cost=0)
    payload["turns"] = []
    payload["attempts"] = []
    nt.write_json(final(plan), payload)
    if hasattr(plan, "close"):
        plan.close()
    resumed = stage(setup, models=[nt.CHEAP[0]])
    assert resumed.dry_run() == 1
    assert f"h2:blocked {expected} at attempt 1" in resumed.out.getvalue()


def test_sigint_finishes_saves_and_stops_before_the_next_household(setup, tmp_path):
    run_no_tools_probe(
        setup,
        tmp_path,
        "finish_admitted_attempt",
        r"""
        calls = []
        saved_handlers = {
            sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)
        }


        def interrupted(
            scenario, variables, tool_call, completion, spend, *, profile
        ):
            calls.append(scenario.id)
            spend.add(0.17)
            if scenario.id == "h2":
                os.kill(os.getpid(), signal.SIGINT)
                assert plan.interrupted.wait(30), (
                    "SIGINT must set the interruption event"
                )
            return record(scenario.id, profile, cost=0.17)


        plan = stage(setup, interrupted, models=[nt.CHEAP[0]])
        result = plan.execute()
        assert result != 0, "SIGINT must give a coordinated nonzero exit"
        assert calls == ["h2"]
        assert load(final(plan))["totals"]["cost_usd"] == 0.17
        assert plan.states[nt.CHEAP[0]] == "interrupted"
        assert not plan.stopped.is_set(), (
            "interrupts must preserve the budget event"
        )
        assert not final(plan, sid="h1").exists()
        assert all(
            signal.getsignal(sig) == handler
            for sig, handler in saved_handlers.items()
        )
        assert "finish and save" in plan.out.getvalue()
        """,
    )


def test_stage_lock_refuses_a_second_invocation_and_releases_after_dry_run(setup):
    first = stage(setup, models=[nt.CHEAP[0]])
    with pytest.raises(nt.StateError, match="another no-tools invocation"):
        stage(setup, models=[nt.CHEAP[1]])
    assert first.dry_run() == 1
    second = stage(setup, models=[nt.CHEAP[1]])
    assert second.dry_run() == 1


@pytest.mark.parametrize("fault", ["missing", "hash"])
def test_baseline_exclusions_must_exist_and_hash_before_startup(setup, fault):
    spec = setup["design"]["baseline_exclusions"]
    if fault == "missing":
        Path(spec["path"]).unlink()
    else:
        spec["sha256"] = "0" * 64
    with pytest.raises(nt.StateError, match="baseline exclusions"):
        stage(setup)


def test_archive_identity_and_rerun_eligibility_are_checked_directly(setup):
    first = paused(setup)
    first.archive(nt.CHEAP[0], "h2")
    path = final(first).parent / "attempts/h2-1.json"
    payload = load(path)
    payload["scenario_id"] = "h1"
    path.write_text(json.dumps(payload))
    with pytest.raises(nt.StateError, match="household differs from archive name h2"):
        stage(setup)
    payload.update(scenario_id="h2", status="complete", error=None)
    path.write_text(json.dumps(payload))
    with pytest.raises(nt.StateError, match="archived attempt was ineligible"):
        stage(setup)


def test_two_provider_failures_then_harness_failure_has_no_standing_final(setup):
    provider = Provider(
        {
            **plant(setup, "provider_error", "APIConnectionError", 1),
            **plant(setup, "provider_error", "APIConnectionError", 2),
            **plant(setup, "provider_error", "BadRequestError", 3),
        }
    )

    def failure(*args, **kwargs):
        result = provider(*args, **kwargs)
        if result["error"] == "BadRequestError":
            result["turns"] = []
        return result

    plan = stage(setup, failure, models=[nt.CHEAP[0]])
    assert plan.execute() == 1
    assert plan.states[nt.CHEAP[0]] == "harness-stopped"
    assert [n for _, _, n in provider.calls] == [1, 2, 3]
    assert len(load(final(plan))["attempts"]) == 2
    assert not plan.standing(nt.CHEAP[0], "h2")
    assert not final(plan, sid="h1").exists()


@pytest.mark.parametrize(
    "status,error,expected",
    [
        ("provider_error", "BadRequestError", "stop"),
        ("budget_stop", None, "stopped"),
    ],
)
def test_stage_problems_requires_every_cheap_model_final_to_stand(
    setup, status, error, expected, monkeypatch
):
    plan = stage(setup)
    assert plan.execute() == 0
    path = final(plan, model=nt.CHEAP[-1], sid="h1")
    payload = load(path)
    payload.update(status=status, error=error, turns=[])
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(
        nt.pilot, "load_board", lambda _: pytest.fail("helper loads board")
    )
    problems = nt.stage_problems(setup["design"])
    assert any(nt.CHEAP[-1] in p and "h1" in p and expected in p for p in problems)


def test_stage_problems_reports_missing_finals_and_invalid_optional_history(setup):
    plan = stage(setup)
    assert plan.execute() == 0
    assert nt.stage_problems(setup["design"]) == []
    final(plan, sid="h1").unlink()
    optional = plan.households("gpt-6-sol") / "attempts/h2-2.json"
    optional.parent.mkdir(parents=True)
    optional.write_text("{}")
    problems = nt.stage_problems(setup["design"])
    assert any(nt.CHEAP[0] in p and "h1" in p and "missing" in p for p in problems)
    assert any("attempt-number gap" in p and "gpt-6-sol" in p for p in problems)


def test_real_harness_checks_other_models_spend_before_the_next_turn(
    setup, monkeypatch
):
    from policybench import eval_no_tools

    monkeypatch.setattr(nt, "NO_TOOLS_CAP", 0.1)
    for scenario in setup["board"]["scenarios"].values():
        scenario.country = "us"

    def prompt(scenario, variables, profile):
        return "Synthetic household", {
            "_board_prompt_sha256": "synthetic",
            "_sent_board_prompt_sha256": "synthetic",
            "_budget_ceiling": 100,
            "_answer_tool": nt.pilot.answer_tool_for(
                profile, variables, scenario.country
            ),
            "max_tokens": 100,
        }

    monkeypatch.setattr(nt.pilot, "build_initial_request", prompt)
    monkeypatch.setattr(
        eval_no_tools,
        "_extract_usage_metadata",
        lambda response, *args: {"total_cost_usd": response.synthetic_cost},
    )
    entered = threading.Barrier(2)
    requests = []
    models = [nt.CHEAP[0], nt.CHEAP[2]]
    first_id = nt.pilot.model_profile(models[0], arm="none").model_id

    def completion(**kwargs):
        requests.append(kwargs["model"])
        entered.wait(timeout=30)
        if kwargs["model"] != first_id:
            assert plan.stopped.wait(timeout=30), "other model must cross shared cap"
        message = SimpleNamespace(
            role="assistant", content="", tool_calls=None, function_call=None
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            synthetic_cost=0.11 if kwargs["model"] == first_id else 0.0,
            id="synthetic-response",
        )

    plan = nt.Stage(
        setup["design"],
        models=models,
        board=setup["board"],
        run_household=nt.pilot.run_household,
        completion_for=lambda profile: completion,
        out=io.StringIO(),
    )
    assert plan.execute() == 1
    assert len(requests) == 2
    for model in models:
        payload = load(final(plan, model=model))
        assert payload["status"] == "budget_stop", payload.get("error")
        assert len(payload["turns"]) == 1
        assert not final(plan, model=model, sid="h1").exists()
    assert plan.spend.spent_usd == pytest.approx(0.11)


def track_interrupt_return(monkeypatch):
    """Observe the actual installed first-signal handler returning."""
    returned = threading.Event()
    register = signal.signal

    def install(signum, handler):
        if callable(handler) and handler.__name__ == "interrupt":

            def tracked(sig, frame):
                handler(sig, frame)
                returned.set()

            return register(signum, tracked)
        return register(signum, handler)

    monkeypatch.setattr(signal, "signal", install)
    return returned


@pytest.mark.parametrize("boundary", ["archive", "attempt"])
def test_signal_between_check_and_action_refuses_new_admission(
    setup, tmp_path, boundary
):
    """R1: the watcher interrupts before the proposed action reaches admission."""
    run_no_tools_probe(
        setup,
        tmp_path,
        f"refuse_{boundary}_admission",
        f"        boundary = {boundary!r}\n"
        + r"""
        if boundary == "archive":
            paused(setup)
        provider = Provider()
        plan = stage(setup, provider, models=[nt.CHEAP[0]])
        returned = track_interrupt_return(monkeypatch)


        def signal_and_wait():
            os.kill(os.getpid(), signal.SIGINT)
            assert returned.wait(30), "the signal handler must finish"
            assert plan.interrupted.wait(30), (
                "the watcher must set the interrupt before admission"
            )


        if boundary == "archive":
            original = plan.archive

            def archive(*args):
                signal_and_wait()
                return original(*args)

            monkeypatch.setattr(plan, "archive", archive)
        else:
            original = nt.AttemptSpend

            def attempt_spend(*args):
                signal_and_wait()
                return original(*args)

            monkeypatch.setattr(nt, "AttemptSpend", attempt_spend)
        assert plan.execute() == 1
        assert returned.is_set()
        assert provider.calls == [], (
            "R1: no provider attempt begins after interruption"
        )
        archives = plan.households(nt.CHEAP[0]) / "attempts"
        assert not list(archives.glob("*.json")), (
            "R1: no archive moves after interruption"
        )
        """,
    )


def test_failed_second_thread_start_keeps_invocation_lock_until_worker_finishes(
    setup, tmp_path
):
    """R2: exceptional shutdown waits for every worker before closing its lock."""
    run_no_tools_probe(
        setup,
        tmp_path,
        "failed_second_start",
        r"""
        import fcntl

        entered, release, failed_start, closed = (
            threading.Event() for _ in range(4)
        )
        original_start = threading.Thread.start
        original_close = nt.Stage.close
        observed = {}


        def provider(scenario, variables, tool_call, completion, spend, *, profile):
            entered.set()
            assert release.wait(timeout=30)
            return record(scenario.id, profile)


        plan = stage(setup, provider)
        monkeypatch.setattr(nt, "START_GRACE_SECONDS", 0.05, raising=False)


        def start(thread):
            if thread.name == f"no-tools-{nt.CHEAP[1]}":
                assert entered.wait(timeout=30)
                failed_start.set()
                raise RuntimeError("synthetic second thread start failure")
            return original_start(thread)


        def close(current):
            original_close(current)
            if current is plan:
                closed.set()


        def observe():
            assert failed_start.wait(timeout=30)
            observed["closed_while_live"] = closed.wait(timeout=0.2)
            lock = (plan.root / ".confirmatory-no-tools.lock").open("a")
            try:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    observed["held"] = True
                else:
                    observed["held"] = False
            finally:
                lock.close()
                release.set()


        watcher = threading.Thread(target=observe)
        watcher.start()
        monkeypatch.setattr(threading.Thread, "start", start)
        monkeypatch.setattr(nt.Stage, "close", close)
        try:
            with pytest.raises(RuntimeError, match="second thread start"):
                plan.execute()
        finally:
            release.set()
            watcher.join(timeout=30)
        assert not watcher.is_alive(), "R2: independent lock probe finishes"
        assert observed["held"], "R2: a live worker must retain the invocation lock"
        assert not observed["closed_while_live"], (
            "R2: cleanup joins before unlocking"
        )
        assert plan.interrupted.is_set(), (
            "R2: exceptional shutdown refuses further work"
        )
        assert plan._lock_file is None
        assert load(final(plan))["status"] == "complete", (
            "R2: admitted worker saves before cleanup returns"
        )
        """,
    )


def test_second_signal_exits_while_output_lock_is_held(setup, tmp_path):
    """R4: forced termination is independent of the worker-shared output lock."""
    import textwrap

    probe = tmp_path / "forced_exit.py"
    probe.write_text(
        textwrap.dedent("""\
        import io
        import json
        import os
        import signal
        import sys
        import threading
        import time
        from types import SimpleNamespace
        import confirmatory_no_tools as nt

        design = json.loads(sys.argv[1])
        draw = design['draw_order']
        board = {
            'scenarios': {sid: SimpleNamespace(id=sid) for sid in draw},
            'variables': {sid: ['snap'] for sid in draw},
        }
        held = threading.Event()
        plan = nt.Stage(design, models=[nt.CHEAP[0]], board=board,
                        completion_for=lambda profile: None, out=io.StringIO())

        def worker(model):
            with plan._say_lock:
                held.set()
                time.sleep(30)

        plan.run_model = worker

        def signals():
            assert held.wait(10)
            os.write(1, b'ready\\n')
            os.kill(os.getpid(), signal.SIGINT)
            assert plan.interrupted.wait(30)
            os.kill(os.getpid(), signal.SIGTERM)

        threading.Thread(target=signals, daemon=True).start()
        plan.execute()
        raise AssertionError('forced exit returned')
        """)
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(nt.__file__).parent), env.get("PYTHONPATH", "")]
    )
    result = run_no_tools_fork_probe(
        probe,
        [json.dumps(setup["design"])],
        env=env,
        ready_marker=b"ready\n",
    )
    stdout, stderr = result.stdout, result.stderr
    assert b"ready\n" in stdout, (stdout, stderr)
    assert result.returncode == 128 + signal.SIGTERM, (stdout, stderr)
    assert b"every unsaved attempt then under way is lost, with its spend" in stderr
    assert b"saved finals, archives and the spend they record survive" in stderr


@pytest.mark.parametrize("category", ["optional", "outside-draw"])
def test_stage_problems_classifies_every_saved_final(setup, category):
    """R3: optional and off-draw finals use the initialization classifier."""
    plan = stage(setup)
    assert plan.execute() == 0
    model = "gpt-6-sol" if category == "optional" else nt.CHEAP[0]
    sid = "h2" if category == "optional" else "outside-draw"
    profile = nt.pilot.model_profile(
        model, arm="none", prompt_version=nt.PROMPT_VERSION
    )
    payload = record(sid, profile)
    payload.update(attempts=[], turns=[None])
    path = plan.households(model) / f"{sid}.json"
    nt.write_json(path, payload)
    match = "outside the draw" if category == "outside-draw" else "get"
    with pytest.raises(nt.StateError, match=match):
        stage(setup)
    problems = nt.stage_problems(setup["design"])
    assert any(model in problem and match in problem for problem in problems), (
        "R3: every final refused by initialization must fail stage preflight",
        problems,
    )


@pytest.mark.parametrize(
    "payload", ["[]", "{invalid json", '{"exclusions": [{"scenario_id": "h2"}]}']
)
def test_baseline_schema_is_usable_before_any_provider_call(setup, payload):
    """R5: correctly hashed malformed inventories refuse without provider calls."""
    spec = setup["design"]["baseline_exclusions"]
    path = Path(spec["path"])
    path.write_text(payload)
    spec["sha256"] = nt.sha256_file(path)
    provider = Provider()
    try:
        with pytest.raises(nt.StateError, match="baseline exclusion"):
            plan = stage(setup, provider)
            plan.close()
    finally:
        assert provider.calls == [], "R5: schema checks precede provider calls"


@pytest.mark.parametrize("reader", ["final", "archive", "baseline", "design"])
@pytest.mark.parametrize("fault", ["nested", "non-object", "invalid-utf8"])
def test_undecodable_stage_file_refuses_with_path(setup, tmp_path, reader, fault):
    """Every file reader names its refusal; deep decoding stays in a child."""
    run_no_tools_probe(
        setup,
        tmp_path,
        f"decode_{reader}_{fault}",
        f"        reader, fault = {reader!r}, {fault!r}\n"
        + r"""
        from contextlib import redirect_stdout
        from pathlib import Path

        if fault == "nested":
            sys.setrecursionlimit(1000)
            depth = sys.getrecursionlimit() * 20
            payload = (
                b'{"attempts": [], "exclusions": [], "nested": '
                + b"[" * depth + b"0" + b"]" * depth + b"}"
            )
        elif fault == "non-object":
            payload = b"[]"
        else:
            payload = (
                b'{"scenario_id": "h2", "status": "provider_error", '
                b'"error": "APIConnectionError", "attempts": [], '
                b'"exclusions": [], "note": "\xff"}'
            )

        provider = Provider()
        root = Path(setup["design"]["no_tools"]["runs"])
        if reader in ("final", "archive"):
            path = root / nt.CHEAP[0] / "none/confirmatory/households"
            path /= "h2.json" if reader == "final" else "attempts/h2-1.json"
        elif reader == "baseline":
            path = Path(setup["design"]["baseline_exclusions"]["path"])
        else:
            path = root.parent / "design.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

        if reader == "design":
            refusals = []

            class CapturedStateError(nt.StateError):
                def __init__(self, *args):
                    super().__init__(*args)
                    refusals.append(self)

            def unexpected_stage(*args, **kwargs):
                pytest.fail("an undecodable design must refuse before Stage")

            monkeypatch.setattr(nt, "StateError", CapturedStateError)
            monkeypatch.setattr(nt, "Stage", unexpected_stage)
            output = io.StringIO()
            with redirect_stdout(output):
                assert nt.main(["run", str(path), "--dry-run"]) == 1
            assert "The no-tools stage cannot start:" in output.getvalue()
            assert str(path) in output.getvalue()
            assert len(refusals) == 1
            caught = SimpleNamespace(value=refusals[0])
        else:
            if reader == "baseline":
                setup["design"]["baseline_exclusions"]["sha256"] = (
                    nt.sha256_file(path)
                )
            with pytest.raises(nt.StateError) as caught:
                with stage(setup, provider):
                    pytest.fail("an undecodable file must refuse before execution")
            assert str(path) in str(caught.value)
            if reader in ("final", "archive"):
                problems = nt.stage_problems(setup["design"])
                assert any(str(path) in problem for problem in problems), problems
        if fault == "nested":
            assert isinstance(caught.value.__cause__, RecursionError)
            trace = caught.value.__cause__.__traceback__
            frames = []
            while trace is not None:
                frames.append(trace.tb_frame.f_code.co_filename)
                trace = trace.tb_next
            assert any(name.endswith("json/decoder.py") for name in frames), frames
        elif fault == "invalid-utf8":
            assert isinstance(caught.value.__cause__, UnicodeDecodeError)
        assert provider.calls == []
        """,
    )


def write_board_fixture(setup, directory):
    """Write a small board consumed by the unmodified harness readers."""
    import csv

    directory.mkdir()
    engine = nt.pilot._versions()["policyengine-us"]
    setup["design"]["engine"] = f"policyengine-us {engine}"
    setup["design"]["board"] = str(directory)
    meta = {
        "programs": ["snap"],
        "revisions": [
            {"kind": "engine_upgrade", "engine_version": f"policyengine-us {engine}"}
        ],
    }
    (directory / "reference_outputs.csv.meta.json").write_text(json.dumps(meta))
    (directory / "reference_exclusions.json").write_text('{"exclusions": []}')
    with (directory / "reference_outputs.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["scenario_id", "variable", "value"])
        writer.writerows((sid, "snap", 1) for sid in setup["design"]["draw_order"])
    with (directory / "scenarios.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["scenario_json"])
        writer.writerows(
            [json.dumps({"id": sid, "state": "CA", "adults": []})]
            for sid in setup["design"]["draw_order"]
        )


@pytest.mark.parametrize(
    "reader,fault",
    [
        (reader, fault)
        for reader in ("metadata", "exclusions", "scenarios")
        for fault in ("nested", "non-object", "invalid-utf8")
    ]
    + [("reference", "invalid-utf8")],
)
def test_undecodable_board_file_refuses_with_path(setup, tmp_path, reader, fault):
    run_no_tools_probe(
        setup,
        tmp_path,
        f"board_{reader}_{fault}",
        f"        reader, fault = {reader!r}, {fault!r}\n"
        + r"""
        import csv
        from pathlib import Path

        directory = Path(setup["design"]["no_tools"]["runs"]).parent / "board"
        write_board_fixture(setup, directory)
        names = {
            "metadata": "reference_outputs.csv.meta.json",
            "exclusions": "reference_exclusions.json",
            "scenarios": "scenarios.csv",
            "reference": "reference_outputs.csv",
        }
        path = directory / names[reader]
        if fault == "nested":
            sys.setrecursionlimit(1000)
            depth = sys.getrecursionlimit() * 20
            payload = b'{"nested":' + b"[" * depth + b"0" + b"]" * depth + b"}"
        elif fault == "non-object":
            payload = b"[]"
        else:
            payload = b'{"note":"\xff"}'
        if reader == "scenarios":
            # Quote the JSON as a CSV field, retaining the corrupt UTF-8 byte.
            text = io.StringIO(newline="")
            writer = csv.writer(text)
            writer.writerow(["scenario_json"])
            writer.writerow([payload.decode("latin1")])
            payload = text.getvalue().encode("latin1")
        elif reader == "reference":
            payload = b"scenario_id,variable,value\nh2,\xff,1\n"
        path.write_bytes(payload)
        provider = Provider()
        with pytest.raises(nt.StateError) as caught:
            with nt.Stage(
                setup["design"], board=None, run_household=provider,
                completion_for=lambda profile: None, out=io.StringIO(),
            ):
                pytest.fail("an unusable board must refuse before execution")
        assert str(path) in str(caught.value)
        if fault == "nested":
            assert isinstance(caught.value.__cause__, RecursionError)
            trace = caught.value.__cause__.__traceback__
            frames = []
            while trace is not None:
                frames.append(trace.tb_frame.f_code.co_filename)
                trace = trace.tb_next
            assert any(name.endswith("json/decoder.py") for name in frames), frames
        elif fault == "invalid-utf8":
            assert isinstance(caught.value.__cause__, UnicodeDecodeError)
        assert provider.calls == []
        """,
    )


@pytest.mark.parametrize("with_exclusions", [True, False])
def test_valid_board_loads_through_harness(setup, tmp_path, with_exclusions):
    directory = tmp_path / "board"
    write_board_fixture(setup, directory)
    if not with_exclusions:
        (directory / "reference_exclusions.json").unlink()
    expected = nt.pilot.load_board(directory)
    provider = Provider()
    with nt.Stage(
        setup["design"],
        board=None,
        run_household=provider,
        completion_for=lambda profile: None,
        out=io.StringIO(),
    ) as plan:
        assert plan.board.keys() == expected.keys()
        for key in ("reference", "scored", "excluded", "scenarios_frame"):
            assert plan.board[key].equals(expected[key])
        for key in ("meta", "scenarios", "variables"):
            assert plan.board[key] == expected[key]
        assert plan.spend.spent_usd == 0
        assert plan.histories == {model: {} for model in nt.CHEAP}
        assert provider.calls == []


@pytest.mark.parametrize("with_filename", [True, False])
def test_delegated_board_oserror_refuses_with_path(
    setup, tmp_path, monkeypatch, with_filename
):
    directory = tmp_path / "board"
    write_board_fixture(setup, directory)
    reference = directory / "reference_outputs.csv"
    error = (
        OSError(5, "synthetic reread failure", str(reference))
        if with_filename
        else OSError("synthetic reread failure")
    )
    read_csv = nt.pilot.pd.read_csv
    rereads = []

    def fail_reference_reread(source, *args, **kwargs):
        # Prechecks pass an opened stream; the unchanged harness passes a path.
        if isinstance(source, Path) and source == reference:
            rereads.append(source)
            raise error
        return read_csv(source, *args, **kwargs)

    monkeypatch.setattr(nt.pilot.pd, "read_csv", fail_reference_reread)
    provider = Provider()
    try:
        with pytest.raises(nt.StateError) as caught:
            with nt.Stage(
                setup["design"],
                board=None,
                run_household=provider,
                completion_for=lambda profile: None,
                out=io.StringIO(),
            ):
                pytest.fail("a failed board reread must refuse before execution")
        assert rereads == [reference]
        assert caught.value.__cause__ is error
        assert str(reference if with_filename else directory) in str(caught.value)
    finally:
        assert provider.calls == []


@pytest.mark.parametrize("reader", ["metadata", "scenarios"])
def test_board_changed_to_nested_json_after_check_refuses_with_path(
    setup, tmp_path, reader
):
    run_no_tools_probe(
        setup,
        tmp_path,
        f"board_changed_{reader}",
        f"        reader = {reader!r}\n"
        + r"""
        import csv
        from pathlib import Path

        sys.setrecursionlimit(1000)
        depth = sys.getrecursionlimit() * 20
        payload = '{"nested":' + "[" * depth + "0" + "]" * depth + "}"
        directory = Path(setup["design"]["no_tools"]["runs"]).parent / "board"
        write_board_fixture(setup, directory)
        filename = (
            "reference_outputs.csv.meta.json" if reader == "metadata"
            else "scenarios.csv"
        )
        path = directory / filename
        load_board = nt.pilot.load_board
        delegates = []

        def change_then_load(source):
            delegates.append(source)
            if reader == "metadata":
                path.write_text(payload)
            else:
                with path.open("w", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(["scenario_json"])
                    writer.writerow([payload])
            return load_board(source)

        monkeypatch.setattr(nt.pilot, "load_board", change_then_load)
        provider = Provider()
        try:
            with pytest.raises(nt.StateError) as caught:
                with nt.Stage(
                    setup["design"], board=None, run_household=provider,
                    completion_for=lambda profile: None, out=io.StringIO(),
                ):
                    pytest.fail("a changed board must refuse before execution")
            assert delegates == [directory], "all prechecks must finish first"
            assert str(path) in str(caught.value)
            assert "changed after" in str(caught.value)
            assert isinstance(caught.value.__cause__, RecursionError)
            trace = caught.value.__cause__.__traceback__
            frames = []
            while trace is not None:
                frames.append(trace.tb_frame.f_code.co_filename)
                trace = trace.tb_next
            assert any(name.endswith("json/decoder.py") for name in frames), frames
        finally:
            assert provider.calls == []
        """,
    )


def test_board_exclusions_exists_failure_refuses_with_path(
    setup, tmp_path, monkeypatch
):
    directory = tmp_path / "board"
    write_board_fixture(setup, directory)
    exclusions = directory / "reference_exclusions.json"
    error = PermissionError(13, "synthetic unreadable board parent", str(exclusions))
    stat = Path.stat
    checks = []

    def fail_exclusions_stat(path, *args, **kwargs):
        if path == exclusions:
            checks.append(path)
            raise error
        return stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fail_exclusions_stat)
    provider = Provider()
    try:
        with pytest.raises(nt.StateError) as caught:
            with nt.Stage(
                setup["design"],
                board=None,
                run_household=provider,
                completion_for=lambda profile: None,
                out=io.StringIO(),
            ):
                pytest.fail("an unreadable exclusions path must refuse")
        assert checks == [exclusions]
        assert caught.value.__cause__ is error
        assert str(exclusions) in str(caught.value)
    finally:
        assert provider.calls == []


@pytest.mark.parametrize(
    "error_type",
    [
        ValueError,
        TypeError,
        AttributeError,
        KeyError,
        RecursionError,
        OverflowError,
        SystemExit,
    ],
)
def test_unchanged_board_delegate_failure_names_folder(
    setup, tmp_path, monkeypatch, error_type
):
    directory = tmp_path / "board"
    write_board_fixture(setup, directory)
    error = error_type("synthetic delegated failure")
    delegates = []

    def fail_load(source):
        delegates.append(source)
        raise error

    monkeypatch.setattr(nt.pilot, "load_board", fail_load)
    provider = Provider()
    try:
        with pytest.raises(nt.StateError) as caught:
            with nt.Stage(
                setup["design"],
                board=None,
                run_household=provider,
                completion_for=lambda profile: None,
                out=io.StringIO(),
            ):
                pytest.fail("a failed board delegate must refuse before execution")
        assert delegates == [directory]
        assert caught.value.__cause__ is error
        assert str(directory) in str(caught.value)
        assert "changed after" not in str(caught.value)
    finally:
        assert provider.calls == []


def test_board_delegate_failure_names_each_changed_file(setup, tmp_path, monkeypatch):
    directory = tmp_path / "board"
    write_board_fixture(setup, directory)
    paths = [
        directory / name
        for name in ("reference_outputs.csv.meta.json", "scenarios.csv")
    ]
    error = ValueError("synthetic delegated failure")
    delegates = []

    def change_then_fail(source):
        delegates.append(source)
        for path in paths:
            path.write_bytes(path.read_bytes() + b"\n")
        raise error

    monkeypatch.setattr(nt.pilot, "load_board", change_then_fail)
    provider = Provider()
    try:
        with pytest.raises(nt.StateError) as caught:
            with nt.Stage(
                setup["design"],
                board=None,
                run_household=provider,
                completion_for=lambda profile: None,
                out=io.StringIO(),
            ):
                pytest.fail("a changed board must refuse before execution")
        assert delegates == [directory]
        assert caught.value.__cause__ is error
        assert all(str(path) in str(caught.value) for path in paths)
        assert "changed after" in str(caught.value)
    finally:
        assert provider.calls == []


@pytest.mark.parametrize("reader", ["final", "archive"])
@pytest.mark.parametrize("boundary", ["startup", "preflight"])
def test_oversized_record_cost_refuses_with_path(setup, reader, boundary):
    root = Path(setup["design"]["no_tools"]["runs"])
    path = root / nt.CHEAP[0] / "none/confirmatory/households"
    path /= "h2.json" if reader == "final" else "attempts/h2-1.json"
    payload = record(
        "h2",
        SimpleNamespace(name=nt.CHEAP[0], arm="none", model_id="synthetic"),
        status="provider_error",
        error="APIConnectionError",
        cost=10**400,
    )
    payload["attempts"] = []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    provider = Provider()
    if boundary == "startup":
        with pytest.raises(nt.StateError) as caught:
            with stage(setup, provider):
                pytest.fail("an oversized cost must refuse before execution")
        assert str(path) in str(caught.value)
        assert isinstance(caught.value.__cause__, OverflowError)
    else:
        problems = nt.stage_problems(setup["design"])
        assert any(str(path) in problem for problem in problems), problems
    assert provider.calls == []


@pytest.mark.parametrize("reader", ["final", "archive"])
@pytest.mark.parametrize("boundary", ["startup", "preflight"])
@pytest.mark.parametrize(
    "fault",
    [
        "missing-totals",
        "null-totals",
        "false-totals",
        "empty-list-totals",
        "empty-string-totals",
        "true-totals",
        "number-totals",
        "list-totals",
        "missing-cost",
        "null",
        "true",
        "false",
        "numeric-string",
        "empty-string",
        "invalid-string",
        "empty-list",
        "list",
        "empty-object",
        "object",
        "nan",
        "infinity",
        "negative-infinity",
        "negative",
        "overflow",
    ],
)
def test_strict_saved_cost_refuses_with_path(setup, reader, boundary, fault):
    root = Path(setup["design"]["no_tools"]["runs"])
    path = root / nt.CHEAP[0] / "none/confirmatory/households"
    path /= "h2.json" if reader == "final" else "attempts/h2-1.json"
    payload = record(
        "h2",
        SimpleNamespace(name=nt.CHEAP[0], arm="none", model_id="synthetic"),
        status="provider_error",
        error="APIConnectionError",
    )
    payload["attempts"] = []
    totals = {
        "null-totals": None,
        "false-totals": False,
        "empty-list-totals": [],
        "empty-string-totals": "",
        "true-totals": True,
        "number-totals": 1,
        "list-totals": [1],
    }
    costs = {
        "null": None,
        "true": True,
        "false": False,
        "numeric-string": "0.25",
        "empty-string": "",
        "invalid-string": "invalid",
        "empty-list": [],
        "list": [0.25],
        "empty-object": {},
        "object": {"value": 0.25},
        "nan": float("nan"),
        "infinity": float("inf"),
        "negative-infinity": float("-inf"),
        "negative": -0.25,
        "overflow": 10**400,
    }
    if fault == "missing-totals":
        del payload["totals"]
    elif fault in totals:
        payload["totals"] = totals[fault]
    elif fault == "missing-cost":
        payload["totals"] = {}
    else:
        payload["totals"]["cost_usd"] = costs[fault]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    provider = Provider()
    try:
        if boundary == "startup":
            with pytest.raises(nt.StateError) as caught:
                with stage(setup, provider):
                    pytest.fail("an invalid saved cost must refuse before execution")
            assert str(path) in str(caught.value)
        else:
            problems = nt.stage_problems(setup["design"])
            assert any(str(path) in problem for problem in problems), problems
    finally:
        assert provider.calls == []


@pytest.mark.parametrize("cost", [0, 0.0, -0.0, 0.25, 2])
def test_valid_saved_numeric_cost_preserves_spend(setup, cost):
    root = Path(setup["design"]["no_tools"]["runs"])
    folder = root / nt.CHEAP[0] / "none/confirmatory/households"
    folder.mkdir(parents=True)
    profile = SimpleNamespace(name=nt.CHEAP[0], arm="none", model_id="synthetic")
    archive = folder / "attempts/h2-1.json"
    archive.parent.mkdir()
    prior = record(
        "h2", profile, status="provider_error", error="APIConnectionError", cost=cost
    )
    prior["attempts"] = []
    archive.write_text(json.dumps(prior))
    saved = record("h2", profile, cost=cost)
    saved["attempts"] = [nt.entry(archive, prior, 1, nt.sha256_file(archive))]
    (folder / "h2.json").write_text(json.dumps(saved))
    provider = Provider()
    with stage(setup, provider) as plan:
        assert plan.spend.spent_usd == 2 * float(cost)
    assert not any(
        str(folder) in problem for problem in nt.stage_problems(setup["design"])
    )
    assert provider.calls == []


def require_a_stop_at_the_cap(setup, saved):
    """Save these (model, household, cost) finals, and require that startup's sum
    reaches the cap, no owed attempt starts, and another open takes the lock."""
    root = Path(setup["design"]["no_tools"]["runs"])
    for model, sid, cost in saved:
        folder = root / model / "none/confirmatory/households"
        folder.mkdir(parents=True, exist_ok=True)
        profile = SimpleNamespace(name=model, arm="none", model_id="synthetic")
        payload = dict(record(sid, profile, cost=cost), attempts=[])
        (folder / f"{sid}.json").write_text(json.dumps(payload))
    provider = Provider()
    plan = stage(setup, provider)
    assert plan.spend.spent_usd == nt.NO_TOOLS_CAP
    assert plan.stopped.is_set()
    assert plan.execute() == 1
    assert provider.calls == []
    with (root / ".confirmatory-no-tools.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            pytest.fail(f"the invocation lock stayed held: {error}")


def test_startup_spend_takes_the_exact_sum_at_the_stage_cap(setup):
    """A running total of these costs stays under the cap and their exact sum
    reaches it."""
    costs = [math.nextafter(nt.NO_TOOLS_CAP, 0.0), 2**-52, 2**-52, 2**-52]
    assert functools.reduce(operator.add, costs) < nt.NO_TOOLS_CAP
    places = [
        (nt.CHEAP[0], "h2"),
        (nt.CHEAP[0], "h1"),
        (nt.CHEAP[1], "h2"),
        (nt.CHEAP[2], "h2"),
    ]
    require_a_stop_at_the_cap(setup, [(*p, c) for p, c in zip(places, costs)])


def test_startup_spend_sums_every_model_at_once_at_the_stage_cap(setup):
    """Rounding each model's costs first falls one float under the cap, and the
    exact sum of all three reaches it."""
    first = [3 * 2**-53, math.nextafter(nt.NO_TOOLS_CAP, 0.0)]
    second = [2**-52]
    subtotals = [nt.exact_spend(first), nt.exact_spend(second)]
    assert nt.exact_spend(subtotals) < nt.NO_TOOLS_CAP
    require_a_stop_at_the_cap(
        setup,
        [
            (nt.CHEAP[0], "h1", first[0]),
            (nt.CHEAP[0], "h2", first[1]),
            (nt.CHEAP[1], "h2", second[0]),
        ],
    )


def run_no_tools_probe(setup, tmp_path, name, body):
    """Bound a signal or worker-shutdown regression to its own process."""
    import textwrap

    prelude = r"""
    import io
    import json
    import os
    import runpy
    import signal
    import sys
    import threading
    from types import SimpleNamespace
    import pytest

    helpers = runpy.run_path(sys.argv[2])
    for helper in (
        "nt",
        "record",
        "Provider",
        "stage",
        "final",
        "load",
        "paused",
        "track_interrupt_return",
        "write_board_fixture",
    ):
        globals()[helper] = helpers[helper]
    design = json.loads(sys.argv[1])
    setup = {
        "design": design,
        "board": {
            "scenarios": {
                sid: SimpleNamespace(id=sid) for sid in design["draw_order"]
            },
            "variables": {sid: ["snap"] for sid in design["draw_order"]},
        },
    }
    monkeypatch = pytest.MonkeyPatch()
    """
    probe = tmp_path / f"{name}.py"
    probe.write_text(textwrap.dedent(prelude) + "\n" + textwrap.dedent(body))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(nt.__file__).parent), env.get("PYTHONPATH", "")]
    )
    result = run_no_tools_fork_probe(
        probe,
        [json.dumps(setup["design"]), str(Path(__file__))],
        env=env,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)


def _run_cleanup_regression(setup, tmp_path, case):
    """Run every exceptional-cleanup signal probe behind a process deadline."""
    import textwrap

    probe = tmp_path / "cleanup_regression.py"
    probe.write_text(
        textwrap.dedent(r"""
        import io
        import json
        import os
        import signal
        import subprocess
        import sys
        import threading
        import time
        from types import SimpleNamespace
        import confirmatory_no_tools as nt

        nt.pilot.model_profile(
            nt.CHEAP[0], arm="none", prompt_version=nt.PROMPT_VERSION
        )
        print("cleanup-regression-ready", flush=True)
        design, case = json.loads(sys.argv[1]), sys.argv[2]
        board = {
            "scenarios": {
                sid: SimpleNamespace(id=sid) for sid in design["draw_order"]
            },
            "variables": {sid: ["snap"] for sid in design["draw_order"]},
        }
        model = nt.CHEAP[0]
        entered, release, saved, worker_returned = (
            threading.Event() for _ in range(4)
        )
        cleanup_entered, closed = threading.Event(), threading.Event()
        handler_returned = threading.Event()
        order, observed, calls = [], {}, []
        original_handlers = {
            sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)
        }
        original_start = threading.Thread.start
        original_signal = signal.signal
        original_close = nt.Stage.close
        original_write = nt.write_json
        main_ident = threading.get_ident()
        nt.START_GRACE_SECONDS = 0.05


        def provider(scenario, variables, tool_call, completion, spend, *, profile):
            calls.append((profile.name, scenario.id))
            entered.set()
            assert release.wait(20), "cleanup rule: release the admitted worker"
            spend.add(0.1)
            return {
                "scenario_id": scenario.id,
                "model": profile.name,
                "arm": profile.arm,
                "status": "complete",
                "error": None,
                "turns": [{"model": profile.model_id}],
                "predictions": {"snap": 1},
                "totals": {"cost_usd": 0.1},
            }


        models = list(nt.CHEAP[:2]) if case == "condition-signal" else [model]
        plan = nt.Stage(
            design,
            models=models,
            board=board,
            run_household=provider,
            completion_for=lambda profile: None,
            out=io.StringIO(),
        )
        original_model = plan.run_model


        def run_model(name):
            try:
                return original_model(name)
            finally:
                worker_returned.set()


        plan.run_model = run_model


        def write(path, payload, *args, **kwargs):
            result = original_write(path, payload, *args, **kwargs)
            if path == plan.households(model) / "h2.json":
                order.append("saved")
                saved.set()
            return result


        nt.write_json = write


        def close(current):
            if current is plan and current._lock_file is not None:
                order.append("close")
                closed.set()
            return original_close(current)


        nt.Stage.close = close


        def register(sig, handler):
            if sig in original_handlers and handler == original_handlers[sig]:
                order.append("restore:" + signal.Signals(sig).name)
            elif sig in original_handlers and callable(handler):
                original = handler

                def tracked(signum, frame):
                    original(signum, frame)
                    handler_returned.set()

                handler = tracked
            return original_signal(sig, handler)


        signal.signal = register


        def lock_held():
            # A separate process opens the lock independently of the worker.
            probe = (
                "import fcntl,sys; f=open(sys.argv[1],'a'); "
                "\ntry: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)"
                "\nexcept BlockingIOError: print('held')"
                "\nelse: print('released')"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    probe,
                    str(plan.root / ".confirmatory-no-tools.lock"),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            return result.stdout.strip() == "held"


        if case == "condition-signal":

            class InterruptInsideSet(threading.Event):
                def set(self):
                    if threading.get_ident() == main_ident and not hasattr(
                        self, "injected"
                    ):
                        self.injected = True
                        with self._cond:
                            cleanup_entered.set()
                            os.kill(os.getpid(), signal.SIGINT)
                            assert handler_returned.wait(10), (
                                "cleanup rule: handler returns inside Event.set"
                            )
                            self._flag = True
                            self._cond.notify_all()
                        return
                    super().set()

            plan.interrupted = InterruptInsideSet()

            def start(thread):
                if thread.name == "no-tools-" + nt.CHEAP[1]:
                    assert entered.wait(10)
                    raise RuntimeError("synthetic second start failure")
                return original_start(thread)

            def observe():
                assert cleanup_entered.wait(10)
                assert handler_returned.wait(10)
                observed["held"] = lock_held()
                observed["closed_while_live"] = closed.is_set()
                release.set()

            actor = threading.Thread(target=observe, daemon=True)
            actor.start()
            threading.Thread.start = start
            try:
                plan.execute()
            except RuntimeError as error:
                assert str(error) == "synthetic second start failure"
                observed["propagated"] = True
                propagated_error = error
            else:
                raise AssertionError(
                    "cleanup rule: original start exception propagates"
                )
            actor.join(10)
            assert handler_returned.is_set(), (
                "cleanup rule: SIGINT handler returns inside Event.set"
            )
            assert observed.get("held"), (
                "cleanup rule: invocation lock survives Event.set signal"
            )
            assert not observed.get("closed_while_live"), (
                "cleanup rule: admitted worker saves before close"
            )
            assert plan.interrupted.is_set()

        elif case in ("join-once", "join-twice"):
            raised = []
            original_set = plan.interrupted.set

            def interrupt_cleanup():
                cleanup_entered.set()
                return original_set()

            plan.interrupted.set = interrupt_cleanup

            def injected(sig, frame):
                raised.append(len(raised) + 1)
                raise KeyboardInterrupt(
                    "synthetic wait interruption " + str(len(raised))
                )

            signal.signal(signal.SIGUSR1, injected)

            def main_in_worker_wait():
                frame = sys._current_frames().get(main_ident)
                while frame is not None:
                    if frame.f_code.co_name == "_wait_for_tstate_lock":
                        return True
                    if frame.f_code.co_name == "wait":
                        event = frame.f_locals.get("self")
                        if event in getattr(plan, "_worker_done", {}).values():
                            return True
                    frame = frame.f_back
                return False

            def await_wait(cleanup=False):
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if closed.is_set():
                        return False
                    if (
                        not cleanup or cleanup_entered.is_set()
                    ) and main_in_worker_wait():
                        return True
                    time.sleep(0.001)
                return False

            def observe():
                assert entered.wait(10)
                assert await_wait(), (
                    "cleanup rule: main thread reaches a worker wait"
                )
                os.kill(os.getpid(), signal.SIGUSR1)
                if case == "join-twice":
                    if await_wait(cleanup=True):
                        os.kill(os.getpid(), signal.SIGUSR1)
                # The original implementation closes early after poisoning Thread's
                # tstate lock. Give it that opportunity while the provider is held.
                observed["closed_while_live"] = closed.wait(0.1)
                observed["held"] = lock_held()
                release.set()

            actor = threading.Thread(target=observe, daemon=True)
            actor.start()
            try:
                plan.execute()
            except KeyboardInterrupt as error:
                observed["exception"] = str(error)
                order.append("propagated")
            else:
                raise AssertionError("cleanup rule: wait exception must propagate")
            finally:
                release.set()
            actor.join(15)
            assert worker_returned.wait(10), (
                "cleanup rule: worker finishes after injected wait exception"
            )
            assert observed.get("exception") == "synthetic wait interruption 1", (
                "cleanup rule: preserve original exception"
            )
            expected = 2 if case == "join-twice" else 1
            assert len(raised) == expected, (
                "cleanup rule: repeat interruption exercises cleanup wait"
            )
            assert not observed.get("closed_while_live"), (
                "cleanup rule: close waits for worker done"
            )
            assert observed.get("held"), (
                "cleanup rule: invocation lock stays held through worker done"
            )

        elif case in ("start-after", "start-before"):

            def start(thread):
                if thread.name == "no-tools-" + model:
                    if case == "start-after":
                        original_start(thread)
                        assert entered.wait(10)
                    raise RuntimeError("synthetic start interruption")
                return original_start(thread)

            def observe():
                assert entered.wait(10)
                observed["closed_while_live"] = closed.wait(0.1)
                observed["held"] = lock_held()
                release.set()

            actor = None
            if case == "start-after":
                actor = threading.Thread(target=observe, daemon=True)
                actor.start()
            threading.Thread.start = start
            began = time.monotonic()
            try:
                plan.execute()
            except RuntimeError as error:
                observed["exception"] = str(error)
                order.append("propagated")
            else:
                raise AssertionError(
                    "cleanup rule: failed start exception must propagate"
                )
            if actor is not None:
                actor.join(15)
                assert not observed.get("closed_while_live"), (
                    "cleanup rule: partially started worker saves before close"
                )
                assert observed.get("held"), (
                    "cleanup rule: partially started worker retains invocation lock"
                )
            else:
                elapsed = time.monotonic() - began
                assert elapsed >= nt.START_GRACE_SECONDS * 0.9, (
                    "cleanup rule: unstarted worker receives start grace"
                )
                assert not calls and not entered.is_set(), (
                    "cleanup rule: failed native start touches no worker files"
                )
                assert not list(
                    plan.root.glob("*/none/confirmatory/households/*.json")
                )
            assert observed.get("exception") == "synthetic start interruption"

        else:
            raise AssertionError(case)

        if case != "start-before":
            assert saved.is_set(), "cleanup rule: admitted worker saves its final"
            assert order.index("saved") < order.index("close"), (
                "cleanup rule: save precedes close"
            )
            for sig in (signal.SIGINT, signal.SIGTERM):
                assert order.index("saved") < order.index(
                    "restore:" + signal.Signals(sig).name
                ), "cleanup rule: save precedes handler restoration"
        assert plan._lock_file is None, (
            "cleanup rule: invocation lock eventually closes"
        )
        assert all(
            signal.getsignal(sig) == old for sig, old in original_handlers.items()
        ), "cleanup rule: handlers eventually restore"
        print(json.dumps({"case": case, "order": order, "observed": observed}))
        if case == "condition-signal":
            raise propagated_error
        """)
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(nt.__file__).parent), env.get("PYTHONPATH", "")]
    )
    result = run_no_tools_fork_probe(
        probe,
        [json.dumps(setup["design"]), case],
        env=env,
        ready_marker=b"cleanup-regression-ready\n",
        text=True,
    )
    assert "cleanup-regression-ready\n" in result.stdout, (
        "cleanup rule: subprocess reaches readiness",
        result.stdout,
        result.stderr,
    )
    assert result.returncode == (1 if case == "condition-signal" else 0), (
        result.stdout,
        result.stderr,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_signal_inside_cleanup_event_condition_keeps_worker_protected(setup, tmp_path):
    """R10.1: a real signal inside Event.set cannot reenter its condition lock."""
    result = _run_cleanup_regression(setup, tmp_path, "condition-signal")
    assert result["observed"]["propagated"]


@pytest.mark.parametrize("case", ["join-once", "join-twice"])
def test_wait_exceptions_preserve_worker_completion_and_original_exception(
    setup, tmp_path, case
):
    """R10.2: real SIGUSR1 exceptions cannot release protection before done."""
    _run_cleanup_regression(setup, tmp_path, case)


@pytest.mark.parametrize("case", ["start-after", "start-before"])
def test_raised_start_tracks_native_worker_or_waits_start_grace(setup, tmp_path, case):
    """R10.2: a raised start has a completion event and bounded began grace."""
    _run_cleanup_regression(setup, tmp_path, case)


def admission_probe(setup, tmp_path, boundary, force):
    """Exercise real signals behind a paused admission in a bounded subprocess."""
    import textwrap

    if boundary == "archive":
        paused(setup)
    probe = tmp_path / "admission_probe.py"
    probe.write_text(
        textwrap.dedent(r"""
        import io
        import json
        import os
        import signal
        import sys
        import threading
        import time
        import traceback
        from pathlib import Path
        from types import SimpleNamespace
        import confirmatory_no_tools as nt

        design = json.loads(sys.argv[1])
        boundary, force = sys.argv[2], sys.argv[3] == "force"
        board = {
            "scenarios": {
                sid: SimpleNamespace(id=sid) for sid in design["draw_order"]
            },
            "variables": {sid: ["snap"] for sid in design["draw_order"]},
        }
        entered, release, returned, watcher_ready, committed = (
            threading.Event() for _ in range(5)
        )
        errors, calls, order = [], [], []
        plan = None


        class AdmissionLock:
            def __init__(self):
                self.lock = threading.Lock()

            def __enter__(self):
                if threading.current_thread().name == "no-tools-signal-watcher":
                    watcher_ready.set()
                self.lock.acquire()
                return self

            def __exit__(self, *exc):
                self.lock.release()

            def locked(self):
                return self.lock.locked()


        class InterruptEvent(threading.Event):
            def set(self):
                order.append("interrupt")
                super().set()
                watcher_ready.set()


        def provider(scenario, variables, tool_call, completion, spend, *, profile):
            calls.append(scenario.id)
            assert plan.interrupted.wait(20), "R3: watcher eventually interrupts"
            spend.add(0.1)
            return {
                "scenario_id": scenario.id,
                "model": profile.name,
                "arm": profile.arm,
                "status": "complete",
                "error": None,
                "turns": [{"model": profile.model_id}],
                "predictions": {"snap": 1},
                "totals": {"cost_usd": 0.1},
            }


        def completion(profile):
            if boundary == "archive":
                assert plan.interrupted.wait(20), (
                    "R3: archive finishes before another attempt"
                )
            return None


        plan = nt.Stage(
            design,
            models=[nt.CHEAP[0]],
            board=board,
            run_household=provider,
            completion_for=completion,
            out=io.StringIO(),
        )
        plan.interrupted = InterruptEvent()
        plan._admission_lock = AdmissionLock()
        original_say = plan.say


        def say(text):
            if text.startswith("Interrupted:"):
                assert plan.interrupted.is_set(), "R3: message follows interruption"
                assert committed.is_set(), (
                    "R3: admitted commit precedes interruption message"
                )
                order.append("message")
            original_say(text)


        plan.say = say
        original_signal = signal.signal


        def install(signum, handler):
            if callable(handler) and handler.__name__ == "interrupt":

                def tracked(sig, frame):
                    handler(sig, frame)
                    returned.set()

                return original_signal(signum, tracked)
            return original_signal(signum, handler)


        signal.signal = install


        def pause_commit():
            entered.set()
            os.write(1, b"ready\n")
            assert release.wait(20), "R3: paused admitted commit is released"


        if boundary == "archive":
            original_replace = nt.os.replace

            def replace(source, target):
                if Path(target).parent.name == "attempts":
                    pause_commit()
                    original_replace(source, target)
                    order.append("commit")
                    committed.set()
                    return
                return original_replace(source, target)

            nt.os.replace = replace
        else:

            class Admitted(dict):
                def __setitem__(self, key, value):
                    pause_commit()
                    super().__setitem__(key, value)
                    order.append("commit")
                    committed.set()

            plan._admitted_attempts = Admitted()


        def control():
            try:
                assert entered.wait(20), "R3: worker reaches the admission commit"
                held_at_commit = plan._admission_lock.locked()
                os.kill(os.getpid(), signal.SIGINT)
                assert returned.wait(5), (
                    "R3: first handler returns while worker holds admission lock"
                )
                assert held_at_commit, (
                    "R3: worker holds the admission lock at its commit"
                )
                assert watcher_ready.wait(5), (
                    "R3: watcher reaches the admission boundary"
                )
                assert not plan.interrupted.is_set(), (
                    "R3: interrupt cannot precede admitted commit"
                )
                assert not committed.is_set(), (
                    "R3: commit remains paused during first handler"
                )
                if force:
                    os.write(1, b"handler-returned-watcher-waiting\n")
                    os.kill(os.getpid(), signal.SIGINT)
                    # The handler runs on the main thread. Sleep (releasing
                    # the GIL) so it can exit the process before this thread
                    # reports that it did not; 20 s stays inside the probe's
                    # 30 s execution deadline.
                    time.sleep(20)
                    raise AssertionError("R3: forced exit returned")
            except BaseException:
                errors.append(traceback.format_exc())
                if force:
                    os.write(2, errors[-1].encode())
                    os._exit(99)
            finally:
                if not force:
                    release.set()


        controller = threading.Thread(target=control, daemon=True)
        controller.start()
        result = plan.execute()
        controller.join(20)
        assert not errors, "\n".join(errors)
        assert not controller.is_alive(), "R3: controller finishes"
        assert result == 1, "R3: signalled run exits nonzero"
        assert (
            order.index("commit")
            < order.index("interrupt")
            < order.index("message")
        ), order
        assert plan.interrupted.is_set(), (
            "R3: watcher sets interrupt after admitted commit"
        )
        households = plan.households(nt.CHEAP[0])
        assert not (households / "h1.json").exists(), (
            "R3: no later household is admitted"
        )
        if boundary == "archive":
            assert calls == [], (
                "R3: no attempt admitted after the watcher interrupts"
            )
            assert (households / "attempts/h2-1.json").exists(), (
                "R3: admitted archive is saved"
            )
            assert not (households / "h2.json").exists(), (
                "R3: refused next attempt has no final"
            )
            assert plan._admitted_attempts == {}, (
                "R3: no subsequent attempt is admitted"
            )
        else:
            assert calls == ["h2"], "R3: exactly the admitted attempt runs"
            saved = json.loads((households / "h2.json").read_text())
            assert saved["status"] == "complete", (
                "R3: admitted attempt saves its final"
            )
            assert saved["totals"]["cost_usd"] == 0.1, (
                "R3: admitted attempt saves spend"
            )
            assert len(plan._admitted_attempts) == 1, "R3: nothing else is admitted"
        print(json.dumps({"order": order, "calls": calls}))
        """)
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(nt.__file__).parent), env.get("PYTHONPATH", "")]
    )
    result = run_no_tools_fork_probe(
        probe,
        [json.dumps(setup["design"]), boundary, "force" if force else "finish"],
        env=env,
        ready_marker=b"ready\n",
    )
    assert b"ready\n" in result.stdout, (result.stdout, result.stderr)
    return result.returncode, result.stdout, result.stderr


@pytest.mark.parametrize("boundary", ["archive", "attempt"])
def test_signal_waits_for_an_admission_commit_without_blocking_handler(
    setup, tmp_path, boundary
):
    """R3: watcher interruption waits for commits admitted under the worker lock."""
    code, stdout, stderr = admission_probe(setup, tmp_path, boundary, force=False)
    assert code == 0, (stdout, stderr)


@pytest.mark.parametrize("boundary", ["archive", "attempt"])
def test_second_signal_forces_exit_while_watcher_waits_for_admission(
    setup, tmp_path, boundary
):
    """R3: the forced path remains available while the watcher waits for admission."""
    code, stdout, stderr = admission_probe(setup, tmp_path, boundary, force=True)
    assert code == 128 + signal.SIGINT, (stdout, stderr)
    assert b"handler-returned-watcher-waiting\n" in stdout
    assert (
        b"Forced interruption: every unsaved attempt then under way is lost, "
        b"with its spend; saved finals, archives and the spend they record survive."
    ) in stderr


def test_signal_after_all_workers_complete_still_exits_one(setup, tmp_path):
    """R4: a signal before handler restoration makes even a complete run fail."""
    import textwrap

    probe = tmp_path / "signal_after_workers.py"
    probe.write_text(
        textwrap.dedent(r"""
        import io
        import json
        import os
        import signal
        import sys
        from types import SimpleNamespace
        import confirmatory_no_tools as nt

        design = json.loads(sys.argv[1])
        board = {
            "scenarios": {
                sid: SimpleNamespace(id=sid) for sid in design["draw_order"]
            },
            "variables": {sid: ["snap"] for sid in design["draw_order"]},
        }
        plan = nt.Stage(
            design,
            models=[nt.CHEAP[0]],
            board=board,
            completion_for=lambda profile: None,
            out=io.StringIO(),
        )


        def complete(model):
            plan.states[model] = "complete"


        plan.run_model = complete
        original_signal = signal.signal
        previous = signal.getsignal(signal.SIGINT)
        sent = False


        def restore(sig, handler):
            global sent
            if not sent and sig == signal.SIGINT and handler == previous:
                sent = True
                os.kill(os.getpid(), signal.SIGINT)
            return original_signal(sig, handler)


        signal.signal = restore
        assert plan.execute() == 1, (
            "R4: signal arrival before restoration requires exit 1"
        )
        assert all(state == "complete" for state in plan.states.values())
        assert sent, "R4: signal arrives after every worker completed"
        """)
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(nt.__file__).parent), env.get("PYTHONPATH", "")]
    )
    result = run_no_tools_fork_probe(
        probe,
        [json.dumps(setup["design"])],
        env=env,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)


@pytest.mark.parametrize("during_grace", [True, False])
def test_native_worker_without_ident_obeys_start_grace_and_entry_interrupt(
    setup, tmp_path, during_grace
):
    """R10.2: native startup can precede ident and must never outlive file safety."""
    import textwrap

    probe = tmp_path / "native_start_regression.py"
    probe.write_text(
        textwrap.dedent(r"""
        import io
        import json
        import os
        import signal
        import subprocess
        import sys
        import threading
        import time
        from types import SimpleNamespace
        import confirmatory_no_tools as nt

        nt.pilot.model_profile(
            nt.CHEAP[0], arm="none", prompt_version=nt.PROMPT_VERSION
        )
        print("native-start-regression-ready", flush=True)
        design = json.loads(sys.argv[1])
        during_grace = sys.argv[2] == "True"
        model = nt.CHEAP[0]
        board = {
            "scenarios": {
                sid: SimpleNamespace(id=sid) for sid in design["draw_order"]
            },
            "variables": {sid: ["snap"] for sid in design["draw_order"]},
        }
        native_entered, bootstrap_release = threading.Event(), threading.Event()
        cleanup_entered, closed, native_finished = (
            threading.Event() for _ in range(3)
        )
        done_held, release_done = threading.Event(), threading.Event()
        original_bootstrap = threading.Thread._bootstrap_inner
        original_run = threading.Thread.run
        original_close = nt.Stage.close
        main_ident = threading.get_ident()
        worker, calls, order, observed = [], [], [], {}
        nt.START_GRACE_SECONDS = 10 if during_grace else 0.05


        def provider(scenario, variables, tool_call, completion, spend, *, profile):
            calls.append(scenario.id)
            return {
                "scenario_id": scenario.id,
                "model": profile.name,
                "arm": profile.arm,
                "status": "complete",
                "error": None,
                "turns": [{"model": profile.model_id}],
                "predictions": {"snap": 1},
                "totals": {"cost_usd": 0.0},
            }


        plan = nt.Stage(
            design,
            models=[model],
            board=board,
            run_household=provider,
            completion_for=lambda profile: None,
            out=io.StringIO(),
        )
        original_set = plan.interrupted.set


        def interrupt_cleanup():
            result = original_set()
            cleanup_entered.set()
            return result


        plan.interrupted.set = interrupt_cleanup


        def bootstrap(thread):
            if thread.name == "no-tools-" + model:
                worker.append(thread)
                native_entered.set()
                assert bootstrap_release.wait(20), (
                    "start grace rule: release native startup"
                )
            return original_bootstrap(thread)


        def run(thread):
            try:
                return original_run(thread)
            finally:
                if thread.name == "no-tools-" + model:
                    order.append("native-finished")
                    native_finished.set()


        def close(current):
            if current is plan and current._lock_file is not None:
                order.append("close")
                closed.set()
            return original_close(current)


        threading.Thread._bootstrap_inner = bootstrap
        threading.Thread.run = run
        nt.Stage.close = close


        def injected(sig, frame):
            raise KeyboardInterrupt("synthetic startup wait interruption")


        signal.signal(signal.SIGUSR1, injected)


        def main_in_start_wait():
            frame = sys._current_frames().get(main_ident)
            while frame is not None:
                if (
                    frame.f_code.co_name == "wait"
                    and frame.f_locals.get("self") is worker[0]._started
                ):
                    return True
                frame = frame.f_back
            return False


        def lock_held():
            probe = (
                "import fcntl,sys; f=open(sys.argv[1],'a'); "
                "\ntry: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)"
                "\nexcept BlockingIOError: print('held')"
                "\nelse: print('released')"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    probe,
                    str(plan.root / ".confirmatory-no-tools.lock"),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            return result.stdout.strip() == "held"


        def observe():
            assert native_entered.wait(10)
            assert worker[0].ident is None, (
                "start grace rule: native worker has no ident"
            )
            deadline = time.monotonic() + 10
            while not main_in_start_wait():
                assert time.monotonic() < deadline, (
                    "start grace rule: main reaches _started.wait"
                )
                time.sleep(0.001)
            os.kill(os.getpid(), signal.SIGUSR1)
            assert cleanup_entered.wait(10)
            if during_grace:
                # Let the native target begin immediately within grace, then
                # hold its completion independently of process-startup load.
                done = getattr(plan, "_worker_done", {}).get(model)
                if done is not None:
                    original_done_set = done.set

                    def set_done():
                        done_held.set()
                        assert release_done.wait(20), (
                            "start grace rule: release begun worker completion"
                        )
                        return original_done_set()

                    done.set = set_done
                bootstrap_release.set()
                if done is not None:
                    assert done_held.wait(10), (
                        "start grace rule: late target reaches completion"
                    )
                try:
                    observed["held_at_cleanup"] = lock_held()
                finally:
                    release_done.set()
            else:
                assert closed.wait(10), (
                    "start grace rule: close after bounded grace"
                )
                bootstrap_release.set()


        actor = threading.Thread(target=observe, daemon=True)
        actor.start()
        try:
            plan.execute()
        except KeyboardInterrupt as error:
            assert str(error) == "synthetic startup wait interruption"
        else:
            raise AssertionError("start grace rule: original exception propagates")
        finally:
            if closed.is_set() and not during_grace:
                bootstrap_release.set()
        actor.join(15)
        assert native_finished.wait(10), (
            "start grace rule: native worker eventually completes"
        )
        assert not calls, (
            "start grace rule: interrupted late worker makes no provider call"
        )
        assert not list(plan.root.glob("*/none/confirmatory/households/*.json")), (
            "start grace rule: interrupted late worker writes no files"
        )
        if during_grace:
            assert observed.get("held_at_cleanup"), (
                "start grace rule: invocation lock stays held during grace"
            )
            assert order.index("native-finished") < order.index("close"), (
                "start grace rule: worker begun during grace completes before close"
            )
        else:
            assert order.index("close") < order.index("native-finished"), (
                "start grace rule: worker beyond grace exits safely after close"
            )
        assert plan._lock_file is None
        print(json.dumps({"during_grace": during_grace, "order": order}))
        """)
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(nt.__file__).parent), env.get("PYTHONPATH", "")]
    )
    result = run_no_tools_fork_probe(
        probe,
        [json.dumps(setup["design"]), str(during_grace)],
        env=env,
        ready_marker=b"native-start-regression-ready\n",
    )
    assert b"native-start-regression-ready\n" in result.stdout, (
        "start grace rule: subprocess reaches readiness",
        result.stdout,
        result.stderr,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)


_NO_TOOLS_FORK_WARMED = False


def run_no_tools_fork_probe(
    probe,
    args=(),
    *,
    env=None,
    timeout=30,
    ready_marker=None,
    ready_timeout=120,
    text=False,
):
    """Run actual probe code in a forked subprocess with bounded cleanup.

    The parent warms the provider-free profile imports once. A fresh child
    executes the probe with its own signals, stdout, stderr and process exit.
    Readiness has a separate deadline; the execution deadline begins when the
    child reaches its actual readiness marker, or after subprocess setup.
    """
    import multiprocessing
    import runpy
    import subprocess
    import time
    import traceback

    global _NO_TOOLS_FORK_WARMED
    if not _NO_TOOLS_FORK_WARMED:
        nt.pilot.model_profile(
            nt.CHEAP[0], arm="none", prompt_version=nt.PROMPT_VERSION
        )
        _NO_TOOLS_FORK_WARMED = True
    probe = Path(probe).resolve()
    stdout_path = probe.with_suffix(".stdout")
    stderr_path = probe.with_suffix(".stderr")
    command = [sys.executable, str(probe), *map(str, args)]
    context = multiprocessing.get_context("fork")
    startup_ready = context.Event()

    # Flush existing parent streams before fork so the child cannot duplicate
    # any buffered pytest output when its streams are replaced.
    sys.stdout.flush()
    sys.stderr.flush()
    with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:

        def child():
            code = 0
            try:
                os.dup2(stdout_file.fileno(), 1)
                os.dup2(stderr_file.fileno(), 2)
                sys.stdout = os.fdopen(os.dup(1), "w", buffering=1)
                sys.stderr = os.fdopen(os.dup(2), "w", buffering=1)
                if env is not None:
                    os.environ.clear()
                    os.environ.update(env)
                sys.argv = command[1:]
                signal.signal(signal.SIGINT, signal.default_int_handler)
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
                startup_ready.set()
                runpy.run_path(str(probe), run_name="__main__")
            except SystemExit as error:
                if error.code is None:
                    code = 0
                elif isinstance(error.code, int):
                    code = error.code
                else:
                    print(error.code, file=sys.stderr)
                    code = 1
            except BaseException:
                traceback.print_exc()
                code = 1
            finally:
                sys.stdout.flush()
                sys.stderr.flush()
            os._exit(code)

        process = context.Process(target=child, name=f"no-tools-probe-{probe.stem}")
        process.start()
        initial_deadline = time.monotonic() + ready_timeout

        def output():
            stdout = stdout_path.read_bytes()
            stderr = stderr_path.read_bytes()
            if text:
                return stdout.decode(errors="replace"), stderr.decode(errors="replace")
            return stdout, stderr

        def expired(limit):
            process.kill()
            process.join(timeout=30)
            stdout, stderr = output()
            raise subprocess.TimeoutExpired(
                command, limit, output=stdout, stderr=stderr
            )

        try:
            while not startup_ready.is_set() and process.is_alive():
                remaining = initial_deadline - time.monotonic()
                if remaining <= 0:
                    expired(ready_timeout)
                startup_ready.wait(timeout=min(remaining, 0.1))
            if ready_marker is not None:
                marker = (
                    ready_marker.encode()
                    if isinstance(ready_marker, str)
                    else ready_marker
                )
                while marker not in stdout_path.read_bytes() and process.is_alive():
                    if time.monotonic() >= initial_deadline:
                        expired(ready_timeout)
                    time.sleep(0.01)
            process.join(timeout=timeout)
            if process.is_alive():
                expired(timeout)
            stdout, stderr = output()
            return subprocess.CompletedProcess(
                command, process.exitcode, stdout, stderr
            )
        finally:
            if process.is_alive():
                process.kill()
                process.join(timeout=30)
            process.close()


def test_signal_handlers_restore_before_either_watcher_descriptor_closes(
    setup, tmp_path
):
    """R11: every handler that can write is removed before either pipe end closes."""
    run_no_tools_probe(
        setup,
        tmp_path,
        "watcher_descriptor_order",
        r"""
        plan = stage(setup, models=[nt.CHEAP[0]])
        previous = {
            sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)
        }
        original_pipe, original_close = os.pipe, os.close
        original_signal = signal.signal
        watcher_pipe, events = [], []


        def pipe():
            descriptors = original_pipe()
            assert not watcher_pipe, "R11: execute creates one watcher pipe"
            watcher_pipe.extend(descriptors)
            return descriptors


        def register(sig, handler):
            old = original_signal(sig, handler)
            if sig in previous and handler == previous[sig]:
                events.append(("restore", sig))
            return old


        def close(fd):
            original_close(fd)
            if fd in watcher_pipe:
                events.append(("close", fd))


        monkeypatch.setattr(os, "pipe", pipe)
        monkeypatch.setattr(os, "close", close)
        monkeypatch.setattr(signal, "signal", register)
        assert plan.execute() == 0
        restored, closed = set(), []
        for kind, value in events:
            if kind == "restore":
                restored.add(value)
            else:
                assert restored == set(previous), (
                    "R11: both handlers restore before either pipe descriptor "
                    f"closes: {events}"
                )
                closed.append(value)
        assert len(watcher_pipe) == 2
        assert closed == watcher_pipe, "R11: both watcher descriptors close"
        assert all(
            signal.getsignal(sig) == handler for sig, handler in previous.items()
        ), "R11: both prior handlers remain installed"
        """,
    )


def test_signal_after_watcher_descriptor_reuse_cannot_write_to_replacement(
    setup, tmp_path
):
    """R11: a real signal after close cannot write into a reused descriptor."""
    run_no_tools_probe(
        setup,
        tmp_path,
        "watcher_descriptor_reuse",
        r"""
        plan = stage(setup, models=[nt.CHEAP[0]])
        original_pipe, original_close = os.pipe, os.close
        original_signal = signal.signal
        previous_interrupts = []


        def previous_interrupt(sig, frame):
            previous_interrupts.append(sig)


        original_signal(signal.SIGINT, previous_interrupt)
        watcher_pipe, replacement = [], []
        sent = False


        def pipe():
            descriptors = original_pipe()
            assert not watcher_pipe, "R11: execute creates one watcher pipe"
            watcher_pipe.extend(descriptors)
            return descriptors


        def close(fd):
            global sent
            original_close(fd)
            if fd == watcher_pipe[1] and not replacement:
                read_fd, write_fd = original_pipe()
                # Preserve the read end if it acquired the descriptor that must
                # become the replacement write end.
                if read_fd == fd:
                    copied_read_fd = os.dup(read_fd)
                    original_close(read_fd)
                    read_fd = copied_read_fd
                if write_fd != fd:
                    os.dup2(write_fd, fd)
                    original_close(write_fd)
                    write_fd = fd
                replacement.extend((read_fd, write_fd))
                os.set_blocking(read_fd, False)
                sent = True
                # This executes on the main thread immediately after the old
                # write descriptor closes and its number is safely reused.
                os.kill(os.getpid(), signal.SIGINT)


        monkeypatch.setattr(os, "pipe", pipe)
        monkeypatch.setattr(os, "close", close)
        try:
            result = plan.execute()
            assert sent and len(replacement) == 2
            try:
                received = os.read(replacement[0], 1)
            except BlockingIOError:
                received = b""
            assert received == b"", (
                "R11: a restored handler cannot write into the replacement "
                f"descriptor; received {received!r}"
            )
            assert result == 0
            assert previous_interrupts == [signal.SIGINT], (
                "R11: the real signal reaches the restored prior handler"
            )
        finally:
            for fd in replacement:
                original_close(fd)
        """,
    )


@pytest.mark.parametrize("case", ["before-native", "after-native", "after-grace"])
def test_watcher_start_failure_restores_resources_and_late_entry_is_safe(
    setup, tmp_path, case
):
    """R11: failed watcher startup preserves cleanup and the late-entry guard."""
    run_no_tools_probe(
        setup,
        tmp_path,
        "watcher_start_" + case,
        "        case = "
        + repr(case)
        + r"""
        import errno
        import time

        provider = Provider()
        plan = stage(setup, provider, models=[nt.CHEAP[0]])
        original_handlers = {
            sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)
        }
        original_start = threading.Thread.start
        original_run = threading.Thread.run
        original_pipe = os.pipe
        original_read = os.read
        original_fd_close = os.close
        original_close = plan.close
        native_entered, reading, release_late, target_finished = (
            threading.Event() for _ in range(4)
        )
        watchers, pipe_fds, closed_fds, reads, target_errors, order = (
            [] for _ in range(6)
        )
        start_error = RuntimeError("synthetic watcher start " + case)
        nt.START_GRACE_SECONDS = 0.05


        def pipe():
            descriptors = original_pipe()
            assert not pipe_fds, "watcher lifecycle: execute creates one pipe"
            pipe_fds.extend(descriptors)
            return descriptors


        def read(fd, count):
            if fd in pipe_fds:
                assert fd not in closed_fds, (
                    "watcher lifecycle: a late watcher cannot read a closed pipe"
                )
                reads.append(fd)
                reading.set()
            return original_read(fd, count)


        def fd_close(fd):
            result = original_fd_close(fd)
            if fd in pipe_fds:
                closed_fds.append(fd)
                order.append("descriptor-closed")
            return result


        def close():
            result = original_close()
            order.append("stage-closed")
            return result


        def run(thread):
            if thread.name != "no-tools-signal-watcher":
                return original_run(thread)
            native_entered.set()
            try:
                if case == "after-grace":
                    assert release_late.wait(20), (
                        "watcher lifecycle: release the delayed native target"
                    )
                    assert set(closed_fds) == set(pipe_fds), (
                        "watcher lifecycle: delayed target begins after pipe close"
                    )
                    order.append("late-target-entered")
                return original_run(thread)
            except BaseException as error:
                target_errors.append(error)
                raise
            finally:
                target_finished.set()


        def start(thread):
            if thread.name != "no-tools-signal-watcher":
                return original_start(thread)
            watchers.append(thread)
            if case != "before-native":
                original_start(thread)
                assert native_entered.wait(10), (
                    "watcher lifecycle: the native thread starts before failure"
                )
                if case == "after-native":
                    assert reading.wait(10), (
                        "watcher lifecycle: the begun watcher reaches its pipe read"
                    )
            raise start_error


        monkeypatch.setattr(os, "pipe", pipe)
        monkeypatch.setattr(os, "read", read)
        monkeypatch.setattr(os, "close", fd_close)
        monkeypatch.setattr(threading.Thread, "run", run)
        monkeypatch.setattr(threading.Thread, "start", start)
        monkeypatch.setattr(plan, "close", close)
        started_at = time.monotonic()
        try:
            plan.execute()
        except RuntimeError as error:
            assert error is start_error, (
                "watcher lifecycle: propagate the original start exception"
            )
        else:
            raise AssertionError("watcher lifecycle: startup failure must propagate")
        elapsed = time.monotonic() - started_at

        assert len(watchers) == 1 and len(pipe_fds) == 2
        assert sorted(closed_fds) == sorted(pipe_fds), (
            "watcher lifecycle: close both descriptors exactly once"
        )
        assert order.count("stage-closed") == 1
        assert all(
            signal.getsignal(sig) == handler
            for sig, handler in original_handlers.items()
        ), "watcher lifecycle: restore both installed handlers"
        for fd in pipe_fds:
            try:
                os.fstat(fd)
            except OSError as error:
                assert error.errno == errno.EBADF
            else:
                raise AssertionError("watcher lifecycle: descriptor remains open")
        assert plan.interrupted.is_set(), (
            "watcher lifecycle: failed startup stops admission"
        )
        assert provider.calls == [] and plan._started_workers == [], (
            "watcher lifecycle: no worker is admitted after startup failure"
        )
        assert plan._lock_file is None, (
            "watcher lifecycle: release the stage invocation lock"
        )
        if case == "before-native":
            assert elapsed >= nt.START_GRACE_SECONDS * 0.9, (
                "watcher lifecycle: allow bounded grace for a possible native start"
            )
            assert not native_entered.is_set()
            assert not target_finished.is_set()
            assert not reads
        elif case == "after-native":
            assert reads == [pipe_fds[0]]
            assert target_finished.is_set(), (
                "watcher lifecycle: join the watcher before cleanup returns"
            )
        else:
            assert elapsed >= nt.START_GRACE_SECONDS * 0.9, (
                "watcher lifecycle: delayed target outlasts the bounded start grace"
            )
            assert not target_finished.is_set()
            release_late.set()
            watchers[0].join(timeout=10)
            assert target_finished.is_set()
            assert not reads, (
                "watcher lifecycle: late entry checks closing before reading"
            )
            assert order.index("stage-closed") < order.index("late-target-entered")
        assert not target_errors, target_errors
        assert not watchers[0].is_alive(), (
            "watcher lifecycle: no watcher remains after probe cleanup"
        )
        assert not any(
            thread.name == "no-tools-signal-watcher"
            for thread in threading.enumerate()
        )
        monkeypatch.undo()
        """,
    )


def test_first_sigint_after_watcher_shutdown_preserves_completed_finals(
    setup, tmp_path
):
    """R11.2: late recording forces exit 1 without watcher interruption or output."""
    import textwrap

    probe = tmp_path / "late_first_sigint.py"
    probe.write_text(
        textwrap.dedent(r"""
        import json
        import os
        import runpy
        import signal
        import sys
        import threading
        from types import SimpleNamespace

        helpers = runpy.run_path(sys.argv[2])
        nt, stage, final, load = (
            helpers[name] for name in ("nt", "stage", "final", "load")
        )
        design = json.loads(sys.argv[1])
        setup = {
            "design": design,
            "board": {
                "scenarios": {
                    sid: SimpleNamespace(id=sid) for sid in design["draw_order"]
                },
                "variables": {sid: ["snap"] for sid in design["draw_order"]},
            },
        }
        plan = stage(setup)
        previous = {
            sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)
        }
        original_signal = signal.signal
        original_start = threading.Thread.start
        watcher = []
        restoring, recorded = threading.Event(), threading.Event()
        handler_returned = threading.Event()
        errors = []


        def start(thread):
            if thread.name == "no-tools-signal-watcher":
                watcher.append(thread)
            return original_start(thread)


        def register(sig, handler):
            if sig in previous and handler == previous[sig]:
                if sig == signal.SIGINT:
                    assert len(watcher) == 1 and not watcher[0].is_alive(), (
                        "late signal: watcher has finished before restoration"
                    )
                    restoring.set()
                    assert recorded.wait(20), "late signal: controller finishes"
            elif sig in previous:
                original_handler = handler

                def tracked(signum, frame):
                    original_handler(signum, frame)
                    handler_returned.set()

                handler = tracked
            return original_signal(sig, handler)


        def send():
            try:
                assert restoring.wait(20), "late signal: restoration pauses"
                os.kill(os.getpid(), signal.SIGINT)
                assert handler_returned.wait(20), "late signal: handler returns"
            except BaseException as error:
                errors.append(error)
            finally:
                recorded.set()


        actor = threading.Thread(target=send, daemon=True)
        actor.start()
        threading.Thread.start = start
        signal.signal = register
        result = plan.execute()
        actor.join(20)
        assert not actor.is_alive() and not errors, errors
        assert result == 1, "late signal: recorded SIGINT requires exit 1"
        assert not plan.interrupted.is_set(), (
            "late signal: a finished watcher cannot set interruption"
        )
        assert all(state == "complete" for state in plan.states.values())
        for model in plan.models:
            for sid in design["draw_order"]:
                assert load(final(plan, model, sid))["status"] == "complete", (
                    "late signal: every worker's final is saved"
                )
        assert "Interrupted" not in plan.out.getvalue(), (
            "late signal: a finished watcher prints no announcement"
        )
        assert all(signal.getsignal(sig) == old for sig, old in previous.items())
        assert not watcher[0].is_alive() and plan._lock_file is None
        print("late-first-signal-verified", flush=True)
        sys.exit(result)
        """)
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(nt.__file__).parent), env.get("PYTHONPATH", "")]
    )
    result = run_no_tools_fork_probe(
        probe,
        [json.dumps(setup["design"]), str(Path(__file__))],
        env=env,
    )
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert b"late-first-signal-verified\n" in result.stdout, (
        result.stdout,
        result.stderr,
    )
