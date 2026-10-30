"""Hash-bound inputs and report-compatible variables stay provider-free."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_confirmatory_no_tools import Provider, nt, record, stage
from tests.test_confirmatory_no_tools import setup as _setup_fixture
from tests.test_confirmatory_no_tools_records import (
    OPTIONAL_EVIDENCE,
    assert_boundary,
    full_record,
    save_records,
)
from tests.test_confirmatory_no_tools_records import (
    saved_records as _saved_records_fixture,
)
from tests.test_confirmatory_no_tools_records import (
    treatment_templates as _treatment_templates_fixture,
)
from tests.test_confirmatory_run import N_DRAW, World, complete_preflight_design, cr

setup = _setup_fixture
saved_records = _saved_records_fixture
treatment_templates = _treatment_templates_fixture


def replace_text_read(monkeypatch, path, replacement):
    """Simulate replacement after the first byte read, without changing disk.
    Count both byte readers: Path.read_bytes, and the descriptor-guarded
    read_regular that saved records go through (when the runner has it, so the
    same cases run against an older runner)."""
    original_bytes, original_text = Path.read_bytes, Path.read_text
    original_regular = getattr(nt, "read_regular", None)
    reads = []

    def read_bytes(source):
        data = original_bytes(source)
        if source == path:
            reads.append(("bytes", data))
        return data

    def read_regular(source):
        data = original_regular(source)
        if Path(source) == path:
            reads.append(("bytes", data))
        return data

    if original_regular is not None:
        monkeypatch.setattr(nt, "read_regular", read_regular)

    def read_text(source, *args, **kwargs):
        if source == path:
            reads.append(("text", replacement))
            return replacement
        return original_text(source, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(Path, "read_text", read_text)
    return reads


@pytest.mark.parametrize("data", [b"not JSON", b"\xff"], ids=["json", "utf8"])
def test_baseline_replacement_cannot_supply_unhashed_decoded_bytes(
    setup, monkeypatch, data
):
    path = Path(setup["design"]["baseline_exclusions"]["path"])
    path.write_bytes(data)
    setup["design"]["baseline_exclusions"]["sha256"] = nt.sha256_file(path)
    reads = replace_text_read(monkeypatch, path, '{"exclusions": []}')
    provider = Provider()
    with pytest.raises(nt.StateError) as caught:
        with nt.Stage(
            setup["design"],
            board=setup["board"],
            run_household=provider,
            completion_for=lambda profile: None,
            out=io.StringIO(),
        ):
            pytest.fail("the declared baseline bytes must be decoded")
    assert str(path) in str(caught.value)
    assert reads == [("bytes", data)]
    assert provider.calls == []


def test_baseline_hash_and_decoder_share_one_valid_buffer(setup, monkeypatch):
    path = Path(setup["design"]["baseline_exclusions"]["path"])
    data = path.read_bytes()
    reads = replace_text_read(monkeypatch, path, "not JSON")
    provider = Provider()
    with nt.Stage(
        setup["design"],
        board=setup["board"],
        run_household=provider,
        completion_for=lambda profile: None,
        out=io.StringIO(),
    ) as plan:
        assert plan.spend.spent_usd == 0
    assert reads == [("bytes", data)]
    assert provider.calls == []


def saved_history(setup, archive_cost=0.3, final_cost=0.1):
    """Save one rerun-eligible archive and the final that links it."""
    root = Path(setup["design"]["no_tools"]["runs"])
    folder = root / nt.CHEAP[0] / "none/confirmatory/households"
    profile = SimpleNamespace(name=nt.CHEAP[0], arm="none", model_id="synthetic")
    archive = folder / "attempts/h2-1.json"
    archive.parent.mkdir(parents=True)
    prior = record(
        "h2",
        profile,
        status="provider_error",
        error="APIConnectionError",
        cost=archive_cost,
    )
    prior["attempts"] = []
    archive.write_text(json.dumps(prior))
    saved = record("h2", profile, cost=final_cost)
    saved["attempts"] = [
        {
            "n": 1,
            "file": "attempts/h2-1.json",
            "sha256": nt.sha256_file(archive),
            "status": "provider_error",
            "class": "provider",
            "reason": "APIConnectionError",
        }
    ]
    (folder / "h2.json").write_text(json.dumps(saved))
    return {"archive": archive, "final": folder / "h2.json"}, prior, saved


@pytest.mark.parametrize("which", ["archive", "final"])
def test_saved_record_hash_and_decoder_share_one_buffer(setup, monkeypatch, which):
    paths, prior, saved = saved_history(setup)
    path = paths[which]
    data = path.read_bytes()
    # Hashed before the reads are counted, so the count is the runner's alone.
    archive_sha256 = nt.sha256_file(paths["archive"])
    final_sha256 = nt.sha256_file(paths["final"])
    # A second read would see a cheaper record than the hashed bytes hold.
    replaced = dict(prior if which == "archive" else saved, totals={"cost_usd": 0.2})
    reads = replace_text_read(monkeypatch, path, json.dumps(replaced))
    provider = Provider()
    with stage(setup, provider, models=[nt.CHEAP[0]]) as plan:
        assert plan.spend.spent_usd == pytest.approx(0.4)
        state = plan.histories[nt.CHEAP[0]]["h2"]
        assert state["entries"][0]["sha256"] == archive_sha256
        assert state["final_sha256"] == final_sha256
    assert reads == [("bytes", data)]
    assert provider.calls == []


def test_archive_links_the_digest_its_final_was_read_from(setup):
    paths, _, saved = saved_history(setup)
    saved["status"], saved["error"] = "provider_error", "APIConnectionError"
    paths["final"].write_text(json.dumps(saved))
    data = paths["final"].read_bytes()
    provider = Provider()
    with stage(setup, provider, models=[nt.CHEAP[0]]) as plan:
        assert plan.archive(nt.CHEAP[0], "h2")
        link = plan.histories[nt.CHEAP[0]]["h2"]["entries"][-1]
    assert link["n"] == 2 and link["file"] == "attempts/h2-2.json"
    assert link["sha256"] == hashlib.sha256(data).hexdigest()
    assert (paths["archive"].parent / "h2-2.json").read_bytes() == data
    assert provider.calls == []


def test_archive_refuses_a_final_changed_after_it_was_read(setup):
    paths, _, saved = saved_history(setup)
    saved["status"], saved["error"] = "provider_error", "APIConnectionError"
    paths["final"].write_text(json.dumps(saved))
    provider = Provider()
    with stage(setup, provider, models=[nt.CHEAP[0]]) as plan:
        changed = dict(saved, totals={"cost_usd": 0.2})
        paths["final"].write_text(json.dumps(changed))
        with pytest.raises(nt.StateError, match=re.escape(str(paths["final"]))):
            plan.archive(nt.CHEAP[0], "h2")
        assert len(plan.histories[nt.CHEAP[0]]["h2"]["entries"]) == 1
    assert json.loads(paths["final"].read_text()) == changed
    assert not (paths["archive"].parent / "h2-2.json").exists()
    assert provider.calls == []


def test_archive_moves_back_a_final_changed_before_its_rename(setup, monkeypatch):
    paths, _, saved = saved_history(setup)
    saved["status"], saved["error"] = "provider_error", "APIConnectionError"
    paths["final"].write_text(json.dumps(saved))
    changed = dict(saved, totals={"cost_usd": 0.2})
    original = nt.os.replace

    def change_then_rename(source, target):
        # The write lands after the digest check and before the rename.
        if Path(source) == paths["final"]:
            Path(source).write_text(json.dumps(changed))
        original(source, target)

    provider = Provider()
    with stage(setup, provider, models=[nt.CHEAP[0]]) as plan:
        monkeypatch.setattr(nt.os, "replace", change_then_rename)
        with pytest.raises(
            nt.StateError,
            match=re.escape(f"{paths['final']}: final changed during its archive move"),
        ):
            plan.archive(nt.CHEAP[0], "h2")
        state = plan.histories[nt.CHEAP[0]]["h2"]
        assert len(state["entries"]) == 1 and state["final"] == saved
    assert json.loads(paths["final"].read_text()) == changed
    assert sorted(p.name for p in paths["archive"].parent.iterdir()) == ["h2-1.json"]
    assert provider.calls == []


def test_archive_refuses_a_final_changed_after_the_runner_wrote_it(setup, monkeypatch):
    provider = Provider(
        {
            (nt.CHEAP[0], "h2", 1): {
                "status": "provider_error",
                "error": "APIConnectionError",
            }
        }
    )
    original = nt.write_json

    def write_then_change(path, payload, *args, **kwargs):
        digest = original(path, payload, *args, **kwargs)
        if nt.CHEAP[0] in Path(path).parts:
            path.write_bytes(path.read_bytes() + b" ")
        return digest

    monkeypatch.setattr(nt, "write_json", write_then_change)
    plan = stage(setup, provider)
    assert plan.execute() == 1
    assert plan.states[nt.CHEAP[0]] == "error"
    # The other models continue through both households.
    assert all(plan.states[model] == "complete" for model in nt.CHEAP[1:])
    assert all(
        plan.standing(model, sid) for model in nt.CHEAP[1:] for sid in ("h2", "h1")
    )
    assert [call for call in provider.calls if call[0] == nt.CHEAP[0]] == [
        (nt.CHEAP[0], "h2", 1)
    ]
    folder = plan.households(nt.CHEAP[0])
    assert json.loads((folder / "h2.json").read_text())["status"] == "provider_error"
    assert not (folder / "attempts").exists()


def pool_design(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "HOUSEHOLDS", N_DRAW)
    monkeypatch.setattr(cr, "host_power", lambda: (True, True))
    world = World(tmp_path, monkeypatch, models=(cr.CHEAP[0],))
    return world, complete_preflight_design(world, tmp_path)


@pytest.mark.parametrize("data", [b"not JSON", b"\xff"], ids=["json", "utf8"])
def test_preflight_pool_replacement_cannot_supply_unhashed_decoded_bytes(
    tmp_path, monkeypatch, data
):
    world, design = pool_design(tmp_path, monkeypatch)
    path = Path(design["eligible_pool"]["path"])
    replacement = path.read_text()
    path.write_bytes(data)
    design["eligible_pool"]["sha256"] = cr.sha256_file(path)
    reads = replace_text_read(monkeypatch, path, replacement)
    problems = cr.preflight(design, (cr.CHEAP[0],))
    assert any(str(path) in problem for problem in problems), problems
    assert reads == [("bytes", data)]
    assert world.provider.count == {}


def test_preflight_pool_hash_and_decoder_share_one_valid_buffer(tmp_path, monkeypatch):
    world, design = pool_design(tmp_path, monkeypatch)
    path = Path(design["eligible_pool"]["path"])
    data = path.read_bytes()
    reads = replace_text_read(monkeypatch, path, "[]")
    problems = cr.preflight(design, (cr.CHEAP[0],))
    assert not any("the draw, recomputed" in problem for problem in problems), problems
    assert not any(str(path) in problem for problem in problems), problems
    assert reads == [("bytes", data)]
    assert world.provider.count == {}


def no_tools_households(design, model):
    spec = design["no_tools"]
    return Path(spec["runs"]) / model / spec["folder"] / spec["stage"] / "households"


def saved_spend(world, design):
    """Save $0.20 in a cheap model's final, $0.10 in the archive it replaced and
    $0.05 in an optional model's final. Return their sum."""
    model, sid = cr.CHEAP[0], design["draw_order"][0]
    folder = no_tools_households(design, model)
    final = json.loads((folder / f"{sid}.json").read_text())
    failed = {
        key: value for key, value in final.items() if key not in OPTIONAL_EVIDENCE
    }
    failed.update(
        status="provider_error",
        error="APIConnectionError",
        predictions={variable: None for variable in final["variables"]},
        turns=[],
        totals={"cost_usd": 0.1},
    )
    archive = folder / "attempts" / f"{sid}-1.json"
    digest = cr.write_json(archive, failed)
    final.update(
        attempts=[nt.entry(archive, failed, 1, digest)], totals={"cost_usd": 0.2}
    )
    cr.write_json(folder / f"{sid}.json", final)
    optional = full_record(world.board, "gpt-6-sol", design["engine"], sid)
    optional["totals"] = {"cost_usd": 0.05}
    cr.write_json(no_tools_households(design, "gpt-6-sol") / f"{sid}.json", optional)
    return 0.35


@pytest.mark.parametrize(
    "margin, refused",
    [
        (1.0, False),
        (0.0, False),
        (-nt.MONEY_TOLERANCE / 2, False),
        (-nt.MONEY_TOLERANCE * 2, True),
        (-0.05, True),
        (-0.35, True),
    ],
    ids=[
        "above",
        "equal",
        "inside-tolerance",
        "past-tolerance",
        "lacks-optional",
        "zero",
    ],
)
def test_preflight_compares_spent_before_with_all_saved_spend(
    tmp_path, monkeypatch, margin, refused
):
    world, design = pool_design(tmp_path, monkeypatch)
    spent = saved_spend(world, design)
    design["spent_before"] = spent + margin
    problems = cr.preflight(design, (cr.CHEAP[0],))
    assert [problem for problem in problems if problem.startswith("no-tools")] == (
        [
            f"no-tools spend: spent_before ${spent + margin:.4f} is less than "
            f"the saved records' ${spent:.4f}"
        ]
        if refused
        else []
    )
    assert world.provider.count == {}


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), None, "unknown", -1e-7, 10**400],
    ids=["nan", "infinite", "null", "text", "negative", "overflow"],
)
def test_preflight_refuses_an_unusable_spent_before(tmp_path, monkeypatch, value):
    world, design = pool_design(tmp_path, monkeypatch)
    design["spent_before"] = value
    problems = cr.preflight(design, (cr.CHEAP[0],))
    assert any("finite, nonnegative" in problem for problem in problems), problems
    assert world.provider.count == {}


@pytest.mark.parametrize(
    "fault, needle",
    [
        ("valid", None),
        ("undeclared", "baseline_exclusions"),
        ("missing", "No such file"),
        ("changed", "do not hash as declared"),
        ("malformed", "Expecting"),
        ("schema", "must contain an exclusions list"),
        ("repeated", "repeat a cell"),
    ],
)
def test_preflight_applies_startup_s_baseline_check(
    tmp_path, monkeypatch, fault, needle
):
    world, design = pool_design(tmp_path, monkeypatch)
    spec = design["baseline_exclusions"]
    path = Path(spec["path"])
    cell = {"scenario_id": "h", "variable": "snap"}
    if fault == "undeclared":
        del design["baseline_exclusions"]
    elif fault == "missing":
        path.unlink()
    elif fault == "changed":
        path.write_text('{"exclusions": [], "changed": true}')
    elif fault != "valid":
        path.write_text(
            {
                "malformed": "{",
                "schema": "{}",
                "repeated": json.dumps({"exclusions": [cell, cell]}),
            }[fault]
        )
        spec["sha256"] = nt.sha256_file(path)
    found = [
        problem
        for problem in cr.preflight(design, (cr.CHEAP[0],))
        if "baseline" in problem
    ]
    if needle is None:
        assert found == []
    else:
        assert len(found) == 1 and needle in found[0], found
        assert fault == "undeclared" or str(path) in found[0]
    assert world.provider.count == {}


@pytest.fixture(scope="module")
def report_module():
    configured = os.environ.get("CONFIRMATORY_REPORT")
    if not configured:
        pytest.skip(
            "set CONFIRMATORY_REPORT for the separate report's acceptance control"
        )
    path = Path(configured)
    name = "confirmatory_report_variables_control"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    with pytest.MonkeyPatch.context() as patch:
        patch.syspath_prepend(str(path.parent))
        patch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        yield module


@pytest.mark.parametrize("reader", ["final", "archive"])
def test_variables_object_is_accepted_by_runner_and_report(
    saved_records, report_module, monkeypatch, reader
):
    saved = saved_records
    payload = saved.finals[nt.CHEAP[0]] if reader == "final" else saved.archives[0]
    payload["variables"] = {"snap": {"synthetic_metadata": True}}
    save_records(saved)
    assert_boundary(saved, "startup", None)
    assert_boundary(saved, "preflight", None)
    saved.design["treatment_harness"] = "synthetic-harness"
    monkeypatch.setattr(report_module, "harness_module", lambda path: nt.pilot)
    problems = []
    costs = report_module.no_tools_costs(saved.design, problems)
    assert problems == []
    assert costs["registered_usd"] + costs["other_usd"] == pytest.approx(0.5)
