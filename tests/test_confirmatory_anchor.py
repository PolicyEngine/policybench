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


def test_each_anchor_is_committed_and_pushed(clone, tmp_path):
    remote, repo = clone
    anchors = tmp_path / "anchors.jsonl"
    lines = ['{"time": 1.0, "prev": "a"}', '{"time": 2.0, "prev": "b"}']
    shas = [hashlib.sha256(line.encode()).hexdigest() for line in lines]
    anchors.write_text(lines[0] + "\n")
    assert confirmatory_anchor.main(["--repo", str(repo), str(anchors)]) == 0
    anchors.write_text("\n".join(lines) + "\n")
    assert confirmatory_anchor.main(["--repo", str(repo), str(anchors)]) == 0
    assert remote_log(remote) == [f"anchor 2: {shas[1]}", f"anchor 1: {shas[0]}"]
    assert remote_file(remote) == anchors.read_text()


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
        if len(calls) == 2:  # The anchor itself was synced; its push outcome was not.
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
    assert len(calls) == 2


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
