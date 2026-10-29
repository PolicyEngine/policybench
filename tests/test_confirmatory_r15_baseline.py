"""Hash-bound inputs and report-compatible variables stay provider-free."""

from __future__ import annotations

import importlib.util
import io
import os
import sys
from pathlib import Path

import pytest

from tests.test_confirmatory_no_tools import Provider, nt
from tests.test_confirmatory_no_tools import setup as _setup_fixture
from tests.test_confirmatory_no_tools_records import (
    assert_boundary,
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
    """Simulate replacement after the first byte read, without changing disk."""
    original_bytes, original_text = Path.read_bytes, Path.read_text
    reads = []

    def read_bytes(source):
        data = original_bytes(source)
        if source == path:
            reads.append(("bytes", data))
        return data

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


@pytest.fixture(scope="module")
def report_module():
    configured = os.environ.get("CONFIRMATORY_REPORT")
    if not configured:
        pytest.skip(
            "set CONFIRMATORY_REPORT for the separate report's acceptance control"
        )
    path = Path(configured)
    name = "confirmatory_report_r15_variables_control"
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
