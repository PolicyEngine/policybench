"""The anchor command: each call commits the run's anchors and pushes them."""

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
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import confirmatory_anchor  # noqa: E402
import confirmatory_run as cr  # noqa: E402

SCRIPT = Path(confirmatory_anchor.__file__)


@pytest.fixture
def clone(tmp_path, monkeypatch):
    """A clone of an empty bare remote, with git's own settings only."""
    empty = tmp_path / "gitconfig"
    empty.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "anchor test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "anchor@example.invalid")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    repo = tmp_path / "anchors"
    subprocess.run(["git", "clone", "-q", str(remote), str(repo)], check=True)
    return remote, repo


def remote_log(remote: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(remote), "log", "--format=%s", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.splitlines()


def remote_file(remote: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(remote), "show", "HEAD:anchors.jsonl"],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout


@pytest.mark.parametrize("name", ["anchors.jsonl", "anchors.push-snapshot.jsonl"])
def test_each_anchor_is_committed_and_pushed(clone, tmp_path, name):
    """A snapshot's local name never changes the remote record's name."""
    remote, repo = clone
    anchors = tmp_path / name
    lines = ['{"time": 1.0, "prev": "a"}', '{"time": 2.0, "prev": "b"}']
    shas = [hashlib.sha256(line.encode()).hexdigest() for line in lines]
    anchors.write_text(lines[0] + "\n")
    assert confirmatory_anchor.main(["--repo", str(repo), str(anchors)]) == 0
    anchors.write_text("\n".join(lines) + "\n")
    assert confirmatory_anchor.main(["--repo", str(repo), str(anchors)]) == 0
    assert remote_log(remote) == [f"anchor 2: {shas[1]}", f"anchor 1: {shas[0]}"]
    assert remote_file(remote) == anchors.read_text()
    assert sorted(path.name for path in repo.iterdir() if path.name != ".git") == [
        "anchors.jsonl"
    ]


def test_an_unchanged_file_makes_no_commit(clone, tmp_path):
    remote, repo = clone
    anchors = tmp_path / "anchors.jsonl"
    anchors.write_text('{"time": 1.0}\n')
    for _ in range(2):
        assert confirmatory_anchor.main(["--repo", str(repo), str(anchors)]) == 0
    assert len(remote_log(remote)) == 1


def test_a_failed_push_exits_nonzero(clone, tmp_path):
    """The runner records the command's return code; a push that fails must
    not look like one that landed."""
    remote, repo = clone
    anchors = tmp_path / "anchors.jsonl"
    anchors.write_text('{"time": 1.0}\n')
    subprocess.run(
        ["git", "-C", str(repo), "remote", "set-url", "origin", str(tmp_path / "gone")],
        check=True,
    )
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), str(anchors)],
        capture_output=True,
        text=True,
    )
    assert out.returncode != 0


def bare_run(folder, command):
    """Just the anchor writer, without the board, engines or providers."""
    run = object.__new__(cr.Run)
    run.design = {"runs": str(folder), "anchor_command": command}
    run.out, run._say_lock = io.StringIO(), threading.Lock()
    run.lanes, run.host = {}, None
    run._anchor_head = cr.chain_seed("a" * 64, "", "anchors.jsonl")
    run._anchored = run._next_anchor = -math.inf
    run._pushing, run._push = threading.Lock(), None
    run._push_error = None
    return run


def bare_finish_run(folder, command):
    """An anchor writer with an empty, already closed run to finish."""

    class Ledger:
        def close(self, pending):
            return []

    run = bare_run(folder, command)
    run.ceiling, run._failed = Ledger(), threading.Event()
    run.signalled, run._interrupted = None, False
    run.watch = lambda anchor=True: None
    return run


def test_failed_pushes_retry_and_keep_every_outcome(tmp_path, monkeypatch):
    """A failed remote never looks anchored; retry follows the failure's end,
    then a successful push restores the ordinary cadence."""
    now, calls = [1000.0], []
    monkeypatch.setattr(cr.time, "time", lambda: now[0])
    monkeypatch.setattr(cr, "clock", lambda: now[0])
    monkeypatch.setattr(cr, "ANCHOR_SECONDS", 900.0)
    monkeypatch.setattr(cr, "ANCHOR_RETRY", 60.0)
    monkeypatch.setattr(cr, "ANCHOR_PUSH_TIMEOUT", 123.0)

    class Push:
        def __init__(self, command, **kwargs):
            calls.append((command, kwargs))
            self.returncode = 1 if len(calls) < 4 else 0

        def communicate(self, timeout):
            assert timeout == cr.ANCHOR_PUSH_TIMEOUT
            now[0] += 7.0
            return "", "remote unavailable" if self.returncode else "pushed"

    monkeypatch.setattr(cr.subprocess, "Popen", Push)
    run = bare_run(tmp_path, ["push-anchors"])
    assert run.anchor_due()
    for i in range(4):
        started = now[0]
        run.anchor(wait=True)
        assert not run.anchor_due()
        expected = now[0] + cr.ANCHOR_RETRY if i < 3 else started + cr.ANCHOR_SECONDS
        assert run._next_anchor == expected
        now[0] = expected
        assert run.anchor_due()
    anchors = [
        json.loads(x) for x in (tmp_path / "anchors.jsonl").read_text().splitlines()
    ]
    pushes = [
        json.loads(x)
        for x in (tmp_path / "anchor-pushes.jsonl").read_text().splitlines()
    ]
    assert [x["outcome"] for x in pushes] == ["failed"] * 3 + ["success"]
    assert [x["returncode"] for x in pushes] == [1, 1, 1, 0]
    assert [x["anchor_time"] for x in pushes] == [x["time"] for x in anchors]
    assert all(x["started"] == x["anchor_time"] < x["ended"] for x in pushes)
    assert all(x[1]["start_new_session"] for x in calls)
    assert len({x["anchor"] for x in pushes}) == 4


def test_an_anchor_command_that_cannot_start_is_recorded(tmp_path):
    run = bare_run(tmp_path, [str(tmp_path / "missing-command")])
    run.anchor(wait=True)
    push = json.loads((tmp_path / "anchor-pushes.jsonl").read_text())
    assert push["outcome"] == "error" and push["returncode"] is None
    assert "FileNotFoundError" in push["output"]
    assert run._next_anchor == push["ended"] + cr.ANCHOR_RETRY


@pytest.mark.parametrize("wait", [False, True])
def test_push_log_io_failure_reaches_the_supervisor(tmp_path, monkeypatch, wait):
    """A successful remote push whose outcome could not be synced is still a
    runner error, both in supervision and in the final blocking anchor."""
    calls, fsync = [], os.fsync

    class Push:
        returncode = 0

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, timeout):
            return "pushed", ""

    def fail_push_sync(fd):
        calls.append(fd)
        if (tmp_path / "anchor-pushes.jsonl").exists():
            # The anchor and its copy synced; only the outcome's sync fails.
            raise OSError("push-log fsync failed")
        return fsync(fd)

    monkeypatch.setattr(cr.subprocess, "Popen", Push)
    monkeypatch.setattr(cr.os, "fsync", fail_push_sync)
    run = bare_run(tmp_path, ["push-anchors"])
    if wait:
        with pytest.raises(OSError, match="anchor push outcome could not be recorded"):
            run.anchor(wait=True)
    else:
        run.anchor()
        run._push.join()
    with pytest.raises(OSError, match="push-log fsync failed"):
        run.anchor_due()
    assert not run._push.is_alive()
    assert len(calls) == 3


def test_a_running_push_reads_a_snapshot_while_the_final_anchor_is_appended(
    tmp_path, monkeypatch
):
    """A push released after the final append still sees its own whole prefix."""
    reading, release, joining = threading.Event(), threading.Event(), threading.Event()
    calls, copies, errors = [], [], []

    class Push:
        returncode = 0

        def __init__(self, command, **kwargs):
            self.source = Path(command[-1])
            calls.append(self.source)
            self.first = len(calls) == 1

        def communicate(self, timeout):
            if self.first:
                reading.set()
                assert release.wait(15.0), "the first push was never released"
            copies.append(self.source.read_bytes())
            return "pushed", ""

    monkeypatch.setattr(cr.subprocess, "Popen", Push)
    run = bare_run(tmp_path, ["push-anchors"])
    run.anchor()
    assert reading.wait(15.0), "the first push did not start"
    first, join = run._push, run._push.join

    def joining_push(timeout=None):
        joining.set()
        return join(timeout=timeout)

    def final_anchor():
        try:
            run.anchor(wait=True)
        except BaseException as error:
            errors.append(error)

    monkeypatch.setattr(first, "join", joining_push)
    final = threading.Thread(target=final_anchor, daemon=True)
    final.start()
    try:
        assert joining.wait(15.0), "the final anchor did not join the blocked push"
        live = (tmp_path / "anchors.jsonl").read_bytes()
        assert len(live.splitlines()) == 2
        assert calls[0] != tmp_path / "anchors.jsonl"
        assert calls[0].name.endswith("push-snapshot.jsonl")
        assert len(calls[0].read_bytes().splitlines()) == 1
    finally:
        release.set()
        final.join(timeout=15.0)
    assert not final.is_alive() and not errors
    live = (tmp_path / "anchors.jsonl").read_bytes()
    assert len(copies) == 2 and copies[-1] == live
    assert all(copy.endswith(b"\n") and live.startswith(copy) for copy in copies)
    assert len(set(calls)) == 2


def test_push_times_use_the_ordered_clock_after_a_wall_clock_step_back(
    tmp_path, monkeypatch
):
    """The anchor, its cadence and its push never precede that anchor's time."""
    base = time.time() + 1000.0
    readings = iter([base, base - 0.0001])
    monkeypatch.setattr(cr, "_clock_last", 0.0)
    monkeypatch.setattr(cr.time, "time", lambda: next(readings, base - 0.0001))

    class Push:
        returncode = 0

        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, timeout):
            return "pushed", ""

    monkeypatch.setattr(cr.subprocess, "Popen", Push)
    run = bare_run(tmp_path, ["push-anchors"])
    run.anchor(wait=True)
    anchor = json.loads((tmp_path / "anchors.jsonl").read_text())
    push = json.loads((tmp_path / "anchor-pushes.jsonl").read_text())
    assert anchor["time"] <= run._anchored <= push["started"] <= push["ended"]
    assert push["anchor_time"] == anchor["time"]


def test_a_push_timeout_kills_its_children_and_grandchildren(tmp_path, monkeypatch):
    """All descendants inherit the captured pipe: reaping the command cannot
    finish until they close it. The timeout starts after both have launched."""
    script = tmp_path / "push.py"
    script.write_text(
        "import os, subprocess, sys, threading\n"
        "from pathlib import Path\n"
        "folder, level = Path(sys.argv[1]), int(sys.argv[2])\n"
        "(folder / f'pid-{level}').write_text(str(os.getpid()))\n"
        "if level < 2:\n"
        "    child = subprocess.Popen(\n"
        "        [sys.executable, __file__, str(folder), str(level + 1)])\n"
        "threading.Event().wait()\n"
    )
    run = bare_run(tmp_path, [sys.executable, str(script), str(tmp_path), "0"])
    real_popen, real_killpg = subprocess.Popen, os.killpg
    children, kills, errors = [], [], []
    done = threading.Event()

    def popen(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        communicate = child.communicate

        def ready_communicate(timeout=None):
            if timeout is not None:
                deadline = time.monotonic() + 30.0
                ready = tmp_path / "pid-2"
                while not ready.exists() or not ready.read_text().strip():
                    assert time.monotonic() < deadline, "the descendants did not start"
                    done.wait(0.01)
            return communicate(timeout=timeout)

        child.communicate = ready_communicate
        return child

    def killpg(pid, signum):
        kills.append((pid, signum))
        return real_killpg(pid, signum)

    def push():
        try:
            run.anchor(wait=True)
        except BaseException as error:
            errors.append(error)
        finally:
            done.set()

    with monkeypatch.context() as patch:
        patch.setattr(cr.subprocess, "Popen", popen)
        patch.setattr(cr.os, "killpg", killpg)
        patch.setattr(cr, "ANCHOR_PUSH_TIMEOUT", 0.05)
        thread = threading.Thread(target=push, daemon=True)
        thread.start()
        finished = done.wait(45.0)
        if not finished:
            for child in children:
                try:
                    real_killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            thread.join(timeout=5.0)
    assert finished, "the timed-out command left descendants holding its pipes"
    assert not errors
    assert len(children) == 1 and kills == [(children[0].pid, signal.SIGKILL)]
    push = json.loads((tmp_path / "anchor-pushes.jsonl").read_text())
    assert push["outcome"] == "timeout" and push["returncode"] == -signal.SIGKILL
    assert push["started"] <= push["ended"]
    for level in (1, 2):
        assert int((tmp_path / f"pid-{level}").read_text()) > 0


def test_finish_abandons_pipes_held_by_a_descendant_outside_the_push_group(
    tmp_path, monkeypatch
):
    """An escaped grandchild cannot hold finish open after the kill's grace."""
    script = tmp_path / "escaped-push.py"
    script.write_text(
        "import os, subprocess, sys, threading\n"
        "from pathlib import Path\n"
        "folder = Path(sys.argv[1])\n"
        "if len(sys.argv) > 2 and sys.argv[2] == 'escaped':\n"
        "    (folder / 'escaped-pid').write_text(str(os.getpid()))\n"
        "else:\n"
        "    subprocess.Popen(\n"
        "        [sys.executable, __file__, str(folder), 'escaped'],\n"
        "        start_new_session=True)\n"
        "threading.Event().wait()\n"
    )
    run = bare_finish_run(tmp_path, [sys.executable, str(script), str(tmp_path)])
    real_popen = subprocess.Popen
    ready, done = threading.Event(), threading.Event()
    children, errors = [], []

    def popen(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        communicate = child.communicate

        def ready_communicate(timeout=None):
            if not ready.is_set():
                deadline = time.monotonic() + 15.0
                pid = tmp_path / "escaped-pid"
                while not pid.exists() or not pid.read_text().strip():
                    assert time.monotonic() < deadline, "the grandchild did not start"
                    done.wait(0.01)
                ready.set()
            return communicate(timeout=timeout)

        child.communicate = ready_communicate
        return child

    def finish():
        try:
            run.finish()
        except BaseException as error:
            errors.append(error)
        finally:
            done.set()

    monkeypatch.setattr(cr.subprocess, "Popen", popen)
    monkeypatch.setattr(cr.signal, "signal", lambda *args: None)
    monkeypatch.setattr(cr, "ANCHOR_PUSH_TIMEOUT", 0.05)
    monkeypatch.setattr(cr, "KILL_GRACE", 0.05)
    monkeypatch.setattr(cr, "FINAL_PUSH_TRIES", 1)
    thread = threading.Thread(target=finish, daemon=True)
    thread.start()
    try:
        assert ready.wait(15.0), "the push never launched its grandchild"
        started = time.monotonic()
        finished = done.wait(10.0)
        elapsed = time.monotonic() - started
    finally:
        pid = tmp_path / "escaped-pid"
        if pid.exists() and pid.read_text().strip():
            try:
                os.kill(int(pid.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
        for child in children:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        thread.join(timeout=15.0)
    assert finished and elapsed < 10.0, "finish waited for the escaped child's pipe"
    assert not errors and not thread.is_alive()
    rows = [
        json.loads(line)
        for line in (tmp_path / "anchor-pushes.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 1 and rows[0]["outcome"] == "timeout"
    assert "pipes" in rows[0]["output"] and "held open after the kill" in rows[0]["output"]


def test_finish_records_a_stuck_push_once_even_if_its_thread_later_ends(
    tmp_path, monkeypatch
):
    """A bounded join retires the worker's right to append a second outcome."""
    started, release = threading.Event(), threading.Event()
    calls, waits, copies = [], [], {}

    class Push:
        returncode = 0

        def __init__(self, command, **kwargs):
            calls.append(command)
            self.first = len(calls) == 1
            self.source = Path(command[-1])
            self.returncode = 1 if self.first else 0

        def communicate(self, timeout):
            if self.first:
                started.set()
                assert release.wait(15.0), "the abandoned worker was never released"
            copies[self.source] = self.source.read_bytes()
            return "pushed", ""

    monkeypatch.setattr(cr.subprocess, "Popen", Push)
    monkeypatch.setattr(cr.signal, "signal", lambda *args: None)
    monkeypatch.setattr(cr, "ANCHOR_PUSH_TIMEOUT", 0.05)
    monkeypatch.setattr(cr, "KILL_GRACE", 0.05)
    run = bare_finish_run(tmp_path, ["push-anchors"])
    run.anchor()
    assert started.wait(15.0), "the periodic push did not start"
    worker, join = run._push, run._push.join

    def short_join(timeout=None):
        waits.append(timeout)
        return join(timeout=0.02)

    monkeypatch.setattr(worker, "join", short_join)
    try:
        began = time.monotonic()
        run.finish()
        assert time.monotonic() - began < 10.0
        path = tmp_path / "anchor-pushes.jsonl"
        before = path.read_bytes()
        rows = [json.loads(line) for line in before.splitlines()]
        assert waits == [pytest.approx(cr.ANCHOR_PUSH_TIMEOUT + cr.KILL_GRACE + 30)]
        assert len(rows) == 2
        assert rows[0]["outcome"] == "error" and rows[0]["returncode"] is None
        assert "push thread did not end" in rows[0]["output"]
        assert rows[1]["outcome"] == "success"
        next_anchor = run._next_anchor
    finally:
        release.set()
        join(timeout=15.0)
    assert not worker.is_alive()
    assert path.read_bytes() == before
    assert len({row["anchor"] for row in rows}) == len(rows)
    assert run._last_push_outcome == "success" and run._next_anchor == next_anchor
    live = (tmp_path / "anchors.jsonl").read_bytes()
    assert len(copies[Path(calls[0][-1])].splitlines()) == 1
    assert len(copies[Path(calls[1][-1])].splitlines()) == 2
    assert all(copy.endswith(b"\n") and live.startswith(copy) for copy in copies.values())
