"""Provider-free tests of the no-tools stage's files, retries and shared spend."""

from __future__ import annotations

import ast
import io
import json
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import confirmatory_no_tools as nt  # noqa: E402


@pytest.fixture
def setup(tmp_path):
    draw = ["h2", "h1"]
    return {
        "design": {
            "board": "synthetic.csv",
            "engine": "policyengine-us 2.60.4",
            "draw_order": draw,
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
    with pytest.raises(nt.StateError, match="attempts disagree"):
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


def test_main_supports_multiple_model_options_and_dry_run(
    setup, tmp_path, monkeypatch, capsys
):
    path = tmp_path / "design.json"
    path.write_text(json.dumps(setup["design"]))
    monkeypatch.setattr(nt.pilot, "board_engine", lambda path: "2.60.4")
    monkeypatch.setattr(nt.pilot, "_require_engine", lambda path: None)
    monkeypatch.setattr(nt.pilot, "load_board", lambda path: setup["board"])
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


def test_dry_run_marks_harness_and_budget_finals_as_blocked(setup):
    plan = stage(setup, models=[nt.CHEAP[0]])
    profile = nt.pilot.model_profile(
        nt.CHEAP[0], arm="none", prompt_version=nt.PROMPT_VERSION
    )
    payload = record("h2", profile, status="budget_stop", cost=0)
    payload["attempts"] = []
    nt.write_json(final(plan), payload)
    resumed = stage(setup, models=[nt.CHEAP[0]])
    assert resumed.dry_run() == 1
    assert "h2:blocked stopped at attempt 1" in resumed.out.getvalue()
