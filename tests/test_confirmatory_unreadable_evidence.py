"""File and folder failures must remain named refusals before providers."""

import contextlib
import errno
import io
import json
import os
import re
import threading
import time
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
    assert str(target) in "\n".join(cr.preflight(design, (cr.CHEAP[0],)))
    assert not w.provider.count


@contextlib.contextmanager
def fifo_released_after(path, seconds=5.0):
    """Bound a reader that blocks on the FIFO: after `seconds`, open and close a
    writer every 50 ms, so each blocked open sees end of file instead of hanging."""
    done = threading.Event()

    def release():
        if done.wait(seconds):
            return
        while not done.is_set():
            with contextlib.suppress(OSError):  # ENXIO while no reader waits
                os.close(os.open(path, os.O_WRONLY | os.O_NONBLOCK))
            done.wait(0.05)

    thread = threading.Thread(target=release, daemon=True)
    thread.start()
    try:
        yield
    finally:
        done.set()
        thread.join()


@pytest.mark.parametrize("kind", ["fifo", "device"])
@pytest.mark.parametrize("which", ["final", "archive"])
@pytest.mark.parametrize("boundary", ["startup", "preflight"])
def test_saved_record_that_is_not_a_regular_file_refuses_at_once(
    setup, boundary, which, kind
):
    spec = setup["design"]["no_tools"]
    folder = (
        Path(spec["runs"]) / nt.CHEAP[0] / spec["folder"] / spec["stage"] / "households"
    )
    target = folder / ("h2.json" if which == "final" else "attempts/h2-1.json")
    target.parent.mkdir(parents=True)
    if kind == "fifo":
        os.mkfifo(target)
    else:
        target.symlink_to("/dev/null")
    provider = Provider()
    start = time.monotonic()
    with fifo_released_after(target) if kind == "fifo" else contextlib.nullcontext():
        if boundary == "startup":
            with pytest.raises(nt.StateError) as caught:
                with stage(setup, provider):
                    pytest.fail("a special file must refuse before execution")
            message = str(caught.value)
        else:
            message = "\n".join(nt.stage_problems(setup["design"]))
    found = "FIFO" if kind == "fifo" else "character device"
    assert str(target) in message
    assert f"expected a regular file, found {found}" in message
    assert time.monotonic() - start < 5, "no read may block on the special file"
    assert provider.calls == []


def prepared_final(plan, model=nt.CHEAP[0], sid="h2"):
    """Save a rerun-eligible final and its history, with no attempts folder."""
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
    source = folder / f"{sid}.json"
    source.write_text(json.dumps(payload))
    plan.histories[model][sid] = {
        "final": payload,
        "entries": [],
        "final_sha256": nt.sha256_file(source),
    }
    return folder, source, payload


def test_archive_refuses_an_existing_target_and_keeps_both_files(setup):
    provider = Provider()
    with stage(setup, provider) as plan:
        folder, source, payload = prepared_final(plan)
        target = folder / "attempts" / "h2-1.json"
        target.parent.mkdir()
        target.write_text('{"synthetic": "an earlier archive"}')
        with pytest.raises(
            nt.StateError, match=re.escape(f"{target}: would overwrite")
        ):
            plan.archive(nt.CHEAP[0], "h2")
        assert source.read_text() == json.dumps(payload)
        assert target.read_text() == '{"synthetic": "an earlier archive"}'
        assert sorted(p.name for p in target.parent.iterdir()) == ["h2-1.json"]
        assert plan.histories[nt.CHEAP[0]]["h2"]["entries"] == []
    assert provider.calls == []


def test_archive_digest_refusal_leaves_no_attempts_folder(setup):
    provider = Provider()
    with stage(setup, provider) as plan:
        folder, source, payload = prepared_final(plan)
        source.write_text(json.dumps(dict(payload, totals={"cost_usd": 0.2})))
        with pytest.raises(nt.StateError, match=re.escape(f"{source}: final changed")):
            plan.archive(nt.CHEAP[0], "h2")
        assert json.loads(source.read_text())["totals"] == {"cost_usd": 0.2}
        assert not (folder / "attempts").exists()
        assert plan.histories[nt.CHEAP[0]]["h2"]["entries"] == []
    assert provider.calls == []


def test_archive_refuses_a_final_replaced_by_a_fifo_at_once(setup):
    provider = Provider()
    with stage(setup, provider) as plan:
        folder, source, _ = prepared_final(plan)
        source.unlink()
        os.mkfifo(source)
        start = time.monotonic()
        with fifo_released_after(source):
            with pytest.raises(
                nt.StateError, match="expected a regular file, found FIFO"
            ):
                plan.archive(nt.CHEAP[0], "h2")
        assert time.monotonic() - start < 5, "no digest read may block on a FIFO"
        assert not (folder / "attempts").exists()
    assert provider.calls == []


def test_archive_refuses_a_target_replaced_by_a_fifo_after_its_rename(
    setup, monkeypatch
):
    provider = Provider()
    with stage(setup, provider) as plan:
        folder, source, _ = prepared_final(plan)
        target = folder / "attempts" / "h2-1.json"
        original = nt.os.replace

        def rename_then_replace(old, new):
            original(old, new)
            Path(new).unlink()
            os.mkfifo(new)

        monkeypatch.setattr(nt.os, "replace", rename_then_replace)
        start = time.monotonic()
        with fifo_released_after(target):
            with pytest.raises(
                nt.StateError, match="expected a regular file, found FIFO"
            ):
                plan.archive(nt.CHEAP[0], "h2")
        assert time.monotonic() - start < 5, "the second hash may not block on a FIFO"
        assert not source.exists()
        assert plan.histories[nt.CHEAP[0]]["h2"]["entries"] == []
    assert provider.calls == []


@pytest.mark.parametrize("fault", ["second-read", "move-back"])
def test_a_failed_archive_stops_one_model_and_startup_recovers_it(setup, fault):
    """The second hash or the move back fails: that model errors, the others
    finish, the invocation releases its lock, and the archive stays with no
    final and no link. Startup then rebuilds the link from the bytes present,
    changed or not, which is the limit the draft states."""
    model = nt.CHEAP[0]
    provider = Provider(
        {(model, "h2", 1): {"status": "provider_error", "error": "APIConnectionError"}}
    )
    plan = stage(setup, provider)
    folder = plan.households(model)
    source, target = folder / "h2.json", folder / "attempts" / "h2-1.json"
    with pytest.MonkeyPatch.context() as patch:
        if fault == "second-read":
            read = nt.read_regular

            def unreadable(path):
                if Path(path) == target:
                    raise PermissionError(errno.EACCES, "synthetic denied", str(path))
                return read(path)

            patch.setattr(nt, "read_regular", unreadable)
        else:
            replace = os.replace

            def failed_move_back(old, new):
                if Path(old) == source:
                    Path(old).write_bytes(Path(old).read_bytes() + b" ")
                elif Path(old) == target:
                    raise OSError(errno.EIO, "synthetic failed move", str(old))
                replace(old, new)

            patch.setattr(os, "replace", failed_move_back)
        assert plan.execute() == 1
    assert plan.states[model] == "error"
    assert str(target) in plan.out.getvalue()
    assert all(plan.states[other] == "complete" for other in nt.CHEAP[1:])
    assert all(
        plan.standing(other, sid) for other in nt.CHEAP[1:] for sid in ("h2", "h1")
    )
    assert [call for call in provider.calls if call[0] == model] == [(model, "h2", 1)]
    assert target.exists() and not source.exists()
    digest = nt.sha256_file(target)
    again = Provider()
    resumed = stage(setup, again, models=[model])  # raises if the lock survived
    assert resumed.histories[model]["h2"]["entries"][0]["sha256"] == digest
    assert resumed.execute() == 0
    assert again.calls == [(model, "h2", 1), (model, "h1", 1)]
    assert json.loads(source.read_text())["attempts"][0]["sha256"] == digest
    assert nt.stage_problems(setup["design"]) == []


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
        assert not (folder / "attempts").exists()
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
