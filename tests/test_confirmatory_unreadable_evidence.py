"""File and folder failures must remain named refusals before providers."""

import errno
import io
import json
import os
import re
from pathlib import Path

import pytest

from tests.test_confirmatory_no_tools import (
    Provider,
    nt,
    stage,
    write_board_fixture,
)
from tests.test_confirmatory_no_tools import (
    setup as _setup_fixture,
)
from tests.test_confirmatory_run import (
    complete_preflight_design,
    cr,
)
from tests.test_confirmatory_run import (
    fast as _fast_fixture,
)
from tests.test_confirmatory_run import (
    world as _world_fixture,
)

setup = _setup_fixture
world = _world_fixture
fast = _fast_fixture


def deny_listing(monkeypatch, target):
    for name in ("scandir", "listdir"):
        original = getattr(os, name)

        def denied(path, *args, _original=original, **kwargs):
            if not isinstance(path, int) and Path(path) == target:
                raise PermissionError("synthetic denied listing")
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(os, name, denied)


def deny_stat(monkeypatch, target):
    original = os.stat

    def denied(path, *args, **kwargs):
        if not isinstance(path, int) and Path(path) == target:
            # Path predicates suppress ELOOP on the pinned Python 3.12.
            raise OSError(errno.ELOOP, "synthetic inaccessible metadata")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", denied)


@pytest.mark.parametrize("which", ["finals", "attempts"])
@pytest.mark.parametrize("boundary", ["startup", "preflight"])
def test_unlistable_optional_history_refuses(
    setup, world, tmp_path, monkeypatch, which, boundary
):
    provider = Provider()
    if boundary == "startup":
        design = setup["design"]
    else:
        w = world(models=(cr.CHEAP[0],))
        design = complete_preflight_design(w, tmp_path)
        monkeypatch.setattr(cr, "host_power", lambda: (True, True))
    spec = design["no_tools"]
    folder = (
        Path(spec["runs"]) / "gpt-6-sol" / spec["folder"] / spec["stage"] / "households"
    )
    target = folder if which == "finals" else folder / "attempts"
    target.mkdir(parents=True)
    deny_listing(monkeypatch, target)
    if boundary == "startup":
        with pytest.raises(nt.StateError, match=str(target)):
            with stage(setup, provider):
                pass
    else:
        assert str(target) in "\n".join(cr.preflight(design, (cr.CHEAP[0],)))
        assert not w.provider.count
    assert provider.calls == []


@pytest.mark.parametrize("which", ["root-list", "root-stat", "model-stat"])
@pytest.mark.parametrize("boundary", ["startup", "preflight"])
def test_model_inventory_failure_refuses(
    setup, world, tmp_path, monkeypatch, which, boundary
):
    provider = Provider()
    if boundary == "startup":
        design = setup["design"]
    else:
        w = world(models=(cr.CHEAP[0],))
        design = complete_preflight_design(w, tmp_path)
        monkeypatch.setattr(cr, "host_power", lambda: (True, True))
    root = Path(design["no_tools"]["runs"])
    (root / "gpt-6-sol").mkdir(parents=True, exist_ok=True)
    target = root / "gpt-6-sol" if which == "model-stat" else root
    (deny_listing if which == "root-list" else deny_stat)(monkeypatch, target)
    if boundary == "startup":
        with state_for_loading(setup) as plan:
            with pytest.raises(nt.StateError, match=str(target)):
                plan._load_state(setup["board"])
    else:
        assert str(target) in "\n".join(cr.preflight(design, (cr.CHEAP[0],)))
        assert not w.provider.count
    assert provider.calls == []


def vanish(monkeypatch, target):
    """A listing returned target, but its metadata read finds it gone."""
    original = os.stat

    def gone(path, *args, **kwargs):
        if not isinstance(path, int) and Path(path) == target:
            raise FileNotFoundError(errno.ENOENT, "synthetic vanished entry", str(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", gone)


def plant_listed_entry(monkeypatch, target, fault, tmp_path):
    if fault == "dangling":
        # A model folder symlinked to an unmounted volume.
        target.symlink_to(tmp_path / "unmounted-volume")
    else:
        target.mkdir()
        vanish(monkeypatch, target)


@pytest.mark.parametrize("fault", ["dangling", "vanished"])
@pytest.mark.parametrize("boundary", ["startup", "preflight"])
def test_listed_model_entry_without_metadata_refuses(
    setup, world, tmp_path, monkeypatch, fault, boundary
):
    provider = Provider()
    if boundary == "startup":
        design = setup["design"]
    else:
        w = world(models=(cr.CHEAP[0],))
        design = complete_preflight_design(w, tmp_path)
        monkeypatch.setattr(cr, "host_power", lambda: (True, True))
    root = Path(design["no_tools"]["runs"])
    root.mkdir(parents=True, exist_ok=True)
    target = root / "ghost-model"
    plant_listed_entry(monkeypatch, target, fault, tmp_path)
    if boundary == "startup":
        with pytest.raises(nt.StateError, match=re.escape(str(target))):
            with stage(setup, provider):
                pass
    else:
        problems = cr.preflight(design, (cr.CHEAP[0],))
        assert any(
            problem.startswith(f"no-tools stage: {target}:") for problem in problems
        ), problems
        assert not w.provider.count
    assert provider.calls == []


@pytest.mark.parametrize("fault", ["dangling", "vanished"])
@pytest.mark.parametrize("level", ["arm", "stage"])
def test_preflight_listed_calculator_entry_without_metadata_refuses(
    world, tmp_path, monkeypatch, fault, level
):
    w = world(models=(cr.CHEAP[0],))
    design = complete_preflight_design(w, tmp_path)
    monkeypatch.setattr(cr, "host_power", lambda: (True, True))
    folder = Path(design["runs"]) / cr.CHEAP[0]
    parent = folder if level == "arm" else folder / "pe"
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / "ghost"
    plant_listed_entry(monkeypatch, target, fault, tmp_path)
    problems = cr.preflight(design, (cr.CHEAP[0],))
    assert any(problem.startswith(f"{target}:") for problem in problems), problems
    assert not w.provider.count


@pytest.mark.parametrize("fault", ["file", "stat"])
@pytest.mark.parametrize("which", ["finals", "attempts"])
@pytest.mark.parametrize("boundary", ["startup", "preflight"])
def test_broken_optional_history_folder_refuses(
    setup, world, tmp_path, monkeypatch, fault, which, boundary
):
    provider = Provider()
    if boundary == "startup":
        design = setup["design"]
    else:
        w = world(models=(cr.CHEAP[0],))
        design = complete_preflight_design(w, tmp_path)
        monkeypatch.setattr(cr, "host_power", lambda: (True, True))
    spec = design["no_tools"]
    folder = (
        Path(spec["runs"]) / "gpt-6-sol" / spec["folder"] / spec["stage"] / "households"
    )
    target = folder if which == "finals" else folder / "attempts"
    target.parent.mkdir(parents=True, exist_ok=True)
    if fault == "file":
        target.write_text("{}")
    else:
        target.mkdir()
        deny_stat(monkeypatch, target)
    if boundary == "startup":
        with pytest.raises(nt.StateError, match=re.escape(str(target))):
            with stage(setup, provider):
                pass
    else:
        assert str(target) in "\n".join(cr.preflight(design, (cr.CHEAP[0],)))
        assert not w.provider.count
    assert provider.calls == []


def state_for_loading(setup):
    # Isolate _load_state from the constructor's mkdir and lock operations.
    import threading

    plan = object.__new__(nt.Stage)
    plan.design = setup["design"]
    plan.draw_order = setup["design"]["draw_order"]
    plan.root = Path(setup["design"]["no_tools"]["runs"])
    plan.folder, plan.stage = "none", "confirmatory"
    plan.models = nt.CHEAP
    plan.stopped = threading.Event()
    plan._lock_file = None
    return plan


@pytest.mark.parametrize("which", ["folder-list", "folder-stat", "log-stat"])
def test_calculator_summary_inventory_failure_refuses(world, monkeypatch, which):
    w = world(models=(cr.CHEAP[0],))
    lanes = w.run.lanes[cr.CHEAP[0]]
    target = (
        next(iter(lanes.households_dir.values()))
        if which != "log-stat"
        else lanes.folder / "run-log.jsonl"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if which == "folder-list":
        target.mkdir(exist_ok=True)
    (deny_listing if which == "folder-list" else deny_stat)(monkeypatch, target)
    with pytest.raises(nt.StateError, match=str(target)):
        lanes.summary()
    assert not w.provider.count


@pytest.mark.parametrize(
    "which", ["model", "arm", "stage", "households", "run-log", "host-log"]
)
def test_calculator_preflight_inventory_failure_refuses(
    world, tmp_path, monkeypatch, which
):
    w = world(models=(cr.CHEAP[0],))
    design = complete_preflight_design(w, tmp_path)
    monkeypatch.setattr(cr, "host_power", lambda: (True, True))
    folder = Path(design["runs"]) / cr.CHEAP[0]
    targets = {
        "model": folder,
        "arm": folder / "pe3",
        "stage": folder / "pe3/confirm",
        "households": folder / "pe3/confirm/households",
        "run-log": folder / "run-log.jsonl",
        "host-log": Path(design["runs"]) / "host/host-log.jsonl",
    }
    target = targets[which]
    if which.endswith("log"):
        target.parent.mkdir(parents=True, exist_ok=True)
        deny_stat(monkeypatch, target)
    else:
        target.mkdir(parents=True, exist_ok=True)
        deny_listing(monkeypatch, target)
    assert str(target) in "\n".join(cr.preflight(design, (cr.CHEAP[0],)))
    assert not w.provider.count


@pytest.mark.parametrize("which", ["model", "arm", "stage", "households"])
def test_calculator_preflight_directory_stat_failure_refuses(
    world, tmp_path, monkeypatch, which
):
    w = world(models=(cr.CHEAP[0],))
    design = complete_preflight_design(w, tmp_path)
    monkeypatch.setattr(cr, "host_power", lambda: (True, True))
    folder = Path(design["runs"]) / cr.CHEAP[0]
    target = (
        folder
        / {
            "model": "",
            "arm": "pe3",
            "stage": "pe3/confirm",
            "households": "pe3/confirm/households",
        }[which]
    )
    target.mkdir(parents=True, exist_ok=True)
    deny_stat(monkeypatch, target)
    assert str(target) in "\n".join(cr.preflight(design, (cr.CHEAP[0],)))
    assert not w.provider.count


def test_preflight_unreadable_preregistration_refuses(world, tmp_path, monkeypatch):
    w = world(models=(cr.CHEAP[0],))
    design = complete_preflight_design(w, tmp_path)
    target = Path(design["preregistration"])
    original = Path.read_bytes

    def denied(path):
        if path == target:
            raise PermissionError("synthetic denied read")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", denied)
    monkeypatch.setattr(cr, "host_power", lambda: (True, True))
    assert str(target) in "\n".join(cr.preflight(design, (cr.CHEAP[0],)))
    assert not w.provider.count


def test_archive_target_stat_failure_refuses(setup, monkeypatch):
    provider = Provider()
    with stage(setup, provider) as plan:
        model, sid = nt.CHEAP[0], "h2"
        folder = plan.households(model)
        folder.mkdir(parents=True)
        payload = {
            "scenario_id": sid,
            "status": "provider_error",
            "error": "APIConnectionError",
            "turns": [],
            "attempts": [],
            "totals": {"cost_usd": 0.1},
        }
        (folder / f"{sid}.json").write_text(json.dumps(payload))
        plan.histories[model][sid] = {
            "final": payload,
            "entries": [],
            "final_sha256": nt.sha256_file(folder / f"{sid}.json"),
        }
        target = folder / "attempts" / f"{sid}-1.json"
        deny_stat(monkeypatch, target)
        with pytest.raises(nt.StateError, match=str(target)):
            plan.archive(model, sid)
        assert (folder / f"{sid}.json").read_text() == json.dumps(payload)
    assert provider.calls == []


def test_board_exclusions_stat_failure_refuses(setup, tmp_path, monkeypatch):
    write_board_fixture(setup, tmp_path / "board")
    target = Path(setup["design"]["board"]) / "reference_exclusions.json"
    deny_stat(monkeypatch, target)
    provider = Provider()
    with pytest.raises(nt.StateError, match=str(target)):
        with nt.Stage(setup["design"], run_household=provider, out=io.StringIO()):
            pass
    assert provider.calls == []
