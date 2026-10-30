"""The anchor command: each call commits the run's anchors and pushes them."""

import fcntl
import hashlib
import io
import json
import math
import os
import select
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


def anchor_command(repo: Path, anchors: Path):
    """Run the real helper and retain its failure message and exit status."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), str(anchors)],
        capture_output=True,
        text=True,
    )


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
    """An equal snapshot succeeds without changing the file or remote history."""
    remote, repo = clone
    anchors = tmp_path / "anchors.jsonl"
    anchors.write_text('{"time": 1.0}\n')
    for _ in range(2):
        assert confirmatory_anchor.main(["--repo", str(repo), str(anchors)]) == 0
    assert len(remote_log(remote)) == 1
    assert remote_file(remote) == anchors.read_text()


def test_an_older_snapshot_cannot_replace_a_newer_remote_file(clone, tmp_path):
    """A delayed helper cannot commit or push a prefix after the newer snapshot."""
    remote, repo = clone
    older, newer = tmp_path / "older.jsonl", tmp_path / "newer.jsonl"
    older.write_bytes(b'{"time": 1.0}\n')
    newer.write_bytes(older.read_bytes() + b'{"time": 2.0}\n')
    assert anchor_command(repo, newer).returncode == 0
    history, index = remote_log(remote), (repo / ".git" / "index").read_bytes()
    out = anchor_command(repo, older)
    assert out.returncode != 0 and "not a byte prefix" in out.stderr
    assert (repo / "anchors.jsonl").read_bytes() == newer.read_bytes()
    assert (repo / ".git" / "index").read_bytes() == index
    assert remote_file(remote).encode() == newer.read_bytes()
    assert remote_log(remote) == history


def test_a_busy_clone_is_refused_without_changing_its_records(clone, tmp_path):
    """A held flock prevents target, index, commit and remote writes."""
    remote, repo = clone
    anchors = tmp_path / "anchors.jsonl"
    first = b'{"time": 1.0}\n'
    anchors.write_bytes(first)
    assert anchor_command(repo, anchors).returncode == 0
    history, index = remote_log(remote), (repo / ".git" / "index").read_bytes()
    anchors.write_bytes(first + b'{"time": 2.0}\n')
    with (repo / ".git" / "confirmatory-anchor.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        out = anchor_command(repo, anchors)
    assert out.returncode != 0 and "busy" in out.stderr
    assert (repo / "anchors.jsonl").read_bytes() == first
    assert (repo / ".git" / "index").read_bytes() == index
    assert remote_file(remote).encode() == first
    assert remote_log(remote) == history


@pytest.mark.parametrize("hook_name", ["pre-commit", "pre-push", "pre-receive"])
def test_killing_only_the_helper_keeps_its_git_writer_locked(
    clone, tmp_path, hook_name
):
    """A Git child already using the clone retains the lock after helper death."""
    remote, repo = clone
    anchors = tmp_path / "anchors.jsonl"
    first = b'{"time": 1.0}\n'
    older = first + b'{"time": 2.0}\n'
    snapshots = [older + b'{"time": 3.0}\n', older + b'{"time": 3.0}\n{"time": 4.0}\n']
    anchors.write_bytes(first)
    assert anchor_command(repo, anchors).returncode == 0
    ready, release = tmp_path / "ready", tmp_path / "release"
    for path in (ready, release):
        os.mkfifo(path)
    hook_lock = tmp_path / "hook-lock.json"
    hooks = remote / "hooks" if hook_name == "pre-receive" else repo / ".git" / "hooks"
    hook = hooks / hook_name
    hook.write_text(
        f"#!{sys.executable}\n"
        "import json, os\n"
        "from pathlib import Path\n"
        "if os.environ.get('ANCHOR_TEST_BLOCK') == '1':\n"
        f"    lock = Path({str(repo / '.git' / 'confirmatory-anchor.lock')!r}).stat()\n"
        "    inherited = []\n"
        "    for fd in range(3, 256):\n"
        "        try:\n"
        "            info = os.fstat(fd)\n"
        "        except OSError:\n"
        "            continue\n"
        "        if (info.st_dev, info.st_ino) == (lock.st_dev, lock.st_ino):\n"
        "            inherited.append(os.get_inheritable(fd))\n"
        f"    Path({str(hook_lock)!r}).write_text(json.dumps(inherited))\n"
        f"    with open({str(ready)!r}, 'wb', buffering=0) as pipe:\n"
        "        pipe.write(b'1')\n"
        f"    with open({str(release)!r}, 'rb', buffering=0) as pipe:\n"
        "        pipe.read(1)\n"
    )
    hook.chmod(0o755)

    def records():
        """Read the clone's file, index, HEAD and the remote without writing."""
        objects = [
            subprocess.run(
                ["git", "-C", str(repo), "show", obj], check=True, capture_output=True
            ).stdout
            for obj in (":anchors.jsonl", "HEAD:anchors.jsonl")
        ]
        return (
            (repo / "anchors.jsonl").read_bytes(),
            (repo / ".git" / "index").read_bytes(),
            *objects,
            remote_file(remote).encode(),
            remote_log(remote),
        )

    ready_fd, release_fd = (os.open(path, os.O_RDWR) for path in (ready, release))
    child = None
    try:
        anchors.write_bytes(older)
        child = subprocess.Popen(
            [sys.executable, str(SCRIPT), "--repo", str(repo), str(anchors)],
            env={**os.environ, "ANCHOR_TEST_BLOCK": "1"},
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert select.select([ready_fd], [], [], 15.0)[0], "Git did not reach its hook"
        assert os.read(ready_fd, 1) == b"1"
        before = records()
        assert before[0] == before[2] == older
        child.kill()
        assert child.wait(timeout=15.0) == -signal.SIGKILL
        for snapshot in snapshots:
            anchors.write_bytes(snapshot)
            out = anchor_command(repo, anchors)
            assert out.returncode == 1 and "busy" in out.stderr, (
                "a surviving Git writer lost the helper's clone lock: " + out.stderr
            )
            assert records() == before
        assert json.loads(hook_lock.read_text()) == [True]
        os.write(release_fd, b"1")
        child.communicate(timeout=15.0)
        # Pipe closure need not mean every inherited lock holder has ended.
        with (repo / ".git" / "confirmatory-anchor.lock").open("a") as lock:
            deadline = time.monotonic() + 15.0
            while True:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    assert time.monotonic() < deadline, "a Git child did not finish"
                    threading.Event().wait(0.01)
        after = records()
        assert after[0] == after[2] == after[3] == older
        assert after[4] in (first, older)
        for snapshot in snapshots:
            anchors.write_bytes(snapshot)
            out = anchor_command(repo, anchors)
            assert out.returncode == 0, out.stderr
            state = records()
            assert state[0] == state[2] == state[3] == state[4] == snapshot
        history = subprocess.run(
            ["git", "-C", str(remote), "rev-list", "--reverse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        previous = b""
        for commit in history:
            content = subprocess.run(
                ["git", "-C", str(remote), "show", f"{commit}:anchors.jsonl"],
                check=True,
                capture_output=True,
            ).stdout
            assert content.startswith(previous)
            previous = content
        assert previous == snapshots[-1]
    finally:
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.communicate(timeout=15.0)
        for fd in (ready_fd, release_fd):
            os.close(fd)


@pytest.mark.parametrize("command", ["add", "status"])
def test_killing_only_the_helper_during_add_or_status_keeps_the_clone_locked(
    clone, tmp_path, command
):
    """A clean filter pins each real Git command across helper-only death."""
    remote, repo = clone
    anchors = tmp_path / "anchors.jsonl"
    first = b'{"time": 1.0}\n'
    older = first + b'{"time": 2.0}\n'
    snapshots = [older + b'{"time": 3.0}\n', older + b'{"time": 3.0}\n{"time": 4.0}\n']
    anchors.write_bytes(first)
    assert anchor_command(repo, anchors).returncode == 0
    ready, release = tmp_path / "ready", tmp_path / "release"
    for path in (ready, release):
        os.mkfifo(path)
    invocation = tmp_path / "filter-invocation"
    filter_lock = tmp_path / "filter-lock.json"
    clean = tmp_path / "clean-filter"
    block_at = 1 if command == "add" else 2
    clean.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "content = sys.stdin.buffer.read()\n"
        "if os.environ.get('ANCHOR_TEST_BLOCK') == '1':\n"
        f"    invocation = Path({str(invocation)!r})\n"
        "    count = int(invocation.read_text()) + 1 if invocation.exists() else 1\n"
        "    invocation.write_text(str(count))\n"
        f"    if count == {block_at}:\n"
        f"        lock = Path({str(repo / '.git' / 'confirmatory-anchor.lock')!r})"
        ".stat()\n"
        "        inherited = []\n"
        "        for fd in range(3, 256):\n"
        "            try:\n"
        "                info = os.fstat(fd)\n"
        "            except OSError:\n"
        "                continue\n"
        "            if (info.st_dev, info.st_ino) == (lock.st_dev, lock.st_ino):\n"
        "                inherited.append(os.get_inheritable(fd))\n"
        f"        Path({str(filter_lock)!r}).write_text(json.dumps(inherited))\n"
        f"        with open({str(ready)!r}, 'wb', buffering=0) as pipe:\n"
        "            pipe.write(b'1')\n"
        f"        with open({str(release)!r}, 'rb', buffering=0) as pipe:\n"
        "            pipe.read(1)\n"
        f"    elif count == 1 and {command == 'status'!r}:\n"
        f"        target = Path({str(repo / 'anchors.jsonl')!r})\n"
        "        info = target.stat()\n"
        "        os.utime(target, ns=(info.st_atime_ns, "
        "info.st_mtime_ns - 2000000000))\n"
        "sys.stdout.buffer.write(content)\n"
    )
    clean.chmod(0o755)
    (repo / ".git" / "info" / "attributes").write_text("anchors.jsonl filter=anchor\n")
    for name, value in (("clean", str(clean)), ("required", "true")):
        subprocess.run(
            ["git", "-C", str(repo), "config", f"filter.anchor.{name}", value],
            check=True,
        )

    def records():
        """Read file, raw index, staged and committed bytes and remote history."""
        objects = [
            subprocess.run(
                ["git", "-C", str(repo), "show", obj], check=True, capture_output=True
            ).stdout
            for obj in (":anchors.jsonl", "HEAD:anchors.jsonl")
        ]
        return (
            (repo / "anchors.jsonl").read_bytes(),
            (repo / ".git" / "index").read_bytes(),
            *objects,
            remote_file(remote).encode(),
            remote_log(remote),
        )

    ready_fd, release_fd = (os.open(path, os.O_RDWR) for path in (ready, release))
    child = None
    try:
        anchors.write_bytes(older)
        child = subprocess.Popen(
            [sys.executable, str(SCRIPT), "--repo", str(repo), str(anchors)],
            env={**os.environ, "ANCHOR_TEST_BLOCK": "1"},
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert select.select([ready_fd], [], [], 15.0)[0], (
            f"Git {command} did not reach its clean filter"
        )
        assert os.read(ready_fd, 1) == b"1"
        # The first conversion runs in add; changing its stat forces status's second.
        assert invocation.read_text() == str(block_at)
        before = records()
        assert before[0] == older
        assert before[2] == (first if command == "add" else older)
        assert before[3] == before[4] == first
        child.kill()
        assert child.wait(timeout=15.0) == -signal.SIGKILL
        for snapshot in snapshots:
            anchors.write_bytes(snapshot)
            out = anchor_command(repo, anchors)
            assert out.returncode == 1 and "busy" in out.stderr, (
                f"a surviving Git {command} lost the helper's clone lock: " + out.stderr
            )
            assert records() == before
        assert json.loads(filter_lock.read_text()) == [True]
        os.write(release_fd, b"1")
        child.communicate(timeout=15.0)
        with (repo / ".git" / "confirmatory-anchor.lock").open("a") as lock:
            deadline = time.monotonic() + 15.0
            while True:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    assert time.monotonic() < deadline, f"Git {command} did not finish"
                    threading.Event().wait(0.01)
        after = records()
        assert after[0] == after[2] == older
        assert after[3] == after[4] == first
        for snapshot in snapshots:
            anchors.write_bytes(snapshot)
            out = anchor_command(repo, anchors)
            assert out.returncode == 0, out.stderr
            state = records()
            assert state[0] == state[2] == state[3] == state[4] == snapshot
        history = subprocess.run(
            ["git", "-C", str(remote), "rev-list", "--reverse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        previous = b""
        for commit in history:
            content = subprocess.run(
                ["git", "-C", str(remote), "show", f"{commit}:anchors.jsonl"],
                check=True,
                capture_output=True,
            ).stdout
            assert content.startswith(previous)
            previous = content
        assert previous == snapshots[-1]
    finally:
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.communicate(timeout=15.0)
        for fd in (ready_fd, release_fd):
            os.close(fd)


def test_a_detached_hook_descendant_keeps_the_clone_locked(clone, tmp_path):
    """A double-forked holder outlives its hook and helper until explicitly released."""
    remote, repo = clone
    anchors = tmp_path / "anchors.jsonl"
    first = b'{"time": 1.0}\n'
    older = first + b'{"time": 2.0}\n'
    snapshots = [older + b'{"time": 3.0}\n', older + b'{"time": 3.0}\n{"time": 4.0}\n']
    anchors.write_bytes(first)
    assert anchor_command(repo, anchors).returncode == 0
    ready, release = tmp_path / "ready", tmp_path / "release"
    for path in (ready, release):
        os.mkfifo(path)
    holder = tmp_path / "detached-holder.json"
    hook = repo / ".git" / "hooks" / "pre-push"
    hook.write_text(
        f"#!{sys.executable}\n"
        "import json, os\n"
        "from pathlib import Path\n"
        "if os.environ.get('ANCHOR_TEST_DETACH') == '1':\n"
        f"    ready = os.open({str(ready)!r}, os.O_WRONLY)\n"
        f"    release = os.open({str(release)!r}, os.O_RDONLY)\n"
        "    hook_pid = os.getpid()\n"
        "    child = os.fork()\n"
        "    if child:\n"
        "        os.waitpid(child, 0)\n"
        "        raise SystemExit(0)\n"
        "    os.setsid()\n"
        "    if os.fork():\n"
        "        os._exit(0)\n"
        "    with open(os.devnull, 'r+b', buffering=0) as null:\n"
        "        for fd in range(3):\n"
        "            os.dup2(null.fileno(), fd)\n"
        f"    lock = Path({str(repo / '.git' / 'confirmatory-anchor.lock')!r}).stat()\n"
        "    inherited = []\n"
        "    for fd in range(3, 256):\n"
        "        try:\n"
        "            info = os.fstat(fd)\n"
        "        except OSError:\n"
        "            continue\n"
        "        if (info.st_dev, info.st_ino) == (lock.st_dev, lock.st_ino):\n"
        "            inherited.append(os.get_inheritable(fd))\n"
        "    state = dict(pid=os.getpid(), sid=os.getsid(0), pgid=os.getpgrp(),\n"
        "                 hook_pid=hook_pid, inherited=inherited)\n"
        f"    Path({str(holder)!r}).write_text(json.dumps(state))\n"
        "    os.write(ready, b'1')\n"
        "    os.read(release, 1)\n"
        "    os._exit(0)\n"
    )
    hook.chmod(0o755)

    def records():
        """Read the clone's file, index, HEAD and remote without writing."""
        objects = [
            subprocess.run(
                ["git", "-C", str(repo), "show", obj], check=True, capture_output=True
            ).stdout
            for obj in (":anchors.jsonl", "HEAD:anchors.jsonl")
        ]
        return (
            (repo / "anchors.jsonl").read_bytes(),
            (repo / ".git" / "index").read_bytes(),
            *objects,
            remote_file(remote).encode(),
            remote_log(remote),
        )

    ready_fd, release_fd = (os.open(path, os.O_RDWR) for path in (ready, release))
    child = None
    descendant = None
    try:
        anchors.write_bytes(older)
        child = subprocess.Popen(
            [sys.executable, str(SCRIPT), "--repo", str(repo), str(anchors)],
            env={**os.environ, "ANCHOR_TEST_DETACH": "1"},
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert select.select([ready_fd], [], [], 15.0)[0], (
            "hook did not detach its holder"
        )
        assert os.read(ready_fd, 1) == b"1"
        state = json.loads(holder.read_text())
        descendant = state["pid"]
        stdout, stderr = child.communicate(timeout=15.0)
        assert child.returncode == 0, stderr.decode()
        assert stdout == b"pushed 2 anchors\n"
        assert state["sid"] != child.pid and state["pgid"] != child.pid
        assert descendant != state["sid"]
        os.kill(descendant, 0)
        with pytest.raises(ProcessLookupError):
            os.kill(state["hook_pid"], 0)
        before = records()
        assert before[0] == before[2] == before[3] == before[4] == older
        for snapshot in snapshots:
            anchors.write_bytes(snapshot)
            out = anchor_command(repo, anchors)
            assert out.returncode == 1 and "busy" in out.stderr, (
                "a detached hook descendant lost the helper's clone lock: " + out.stderr
            )
            assert records() == before
        assert state["inherited"] == [True]
        os.write(release_fd, b"1")
        with (repo / ".git" / "confirmatory-anchor.lock").open("a") as lock:
            deadline = time.monotonic() + 15.0
            while True:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    assert time.monotonic() < deadline, (
                        "the detached holder did not exit"
                    )
                    threading.Event().wait(0.01)
        descendant = None
        for snapshot in snapshots:
            anchors.write_bytes(snapshot)
            out = anchor_command(repo, anchors)
            assert out.returncode == 0, out.stderr
            state = records()
            assert state[0] == state[2] == state[3] == state[4] == snapshot
    finally:
        os.write(release_fd, b"1")
        if descendant is not None:
            try:
                os.kill(descendant, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.communicate(timeout=15.0)
        for fd in (ready_fd, release_fd):
            os.close(fd)


def test_a_changed_middle_line_is_refused_without_writing(clone, tmp_path):
    """A longer snapshot still fails when it rewrites an existing line."""
    remote, repo = clone
    anchors = tmp_path / "anchors.jsonl"
    first = b'{"time": 1.0}\n{"time": 2.0}\n{"time": 3.0}\n'
    anchors.write_bytes(first)
    assert anchor_command(repo, anchors).returncode == 0
    history, index = remote_log(remote), (repo / ".git" / "index").read_bytes()
    anchors.write_bytes(first.replace(b"2.0", b"9.0") + b'{"time": 4.0}\n')
    out = anchor_command(repo, anchors)
    assert out.returncode != 0 and "not a byte prefix" in out.stderr
    assert (repo / "anchors.jsonl").read_bytes() == first
    assert (repo / ".git" / "index").read_bytes() == index
    assert remote_file(remote).encode() == first
    assert remote_log(remote) == history


def test_a_stale_git_index_lock_is_left_alone(clone, tmp_path):
    """A failed git command never removes another command's index lock."""
    remote, repo = clone
    anchors = tmp_path / "anchors.jsonl"
    first = b'{"time": 1.0}\n'
    anchors.write_bytes(first)
    assert anchor_command(repo, anchors).returncode == 0
    history = remote_log(remote)
    index_lock = repo / ".git" / "index.lock"
    index_lock.write_bytes(b"stale lock kept for its owner\n")
    anchors.write_bytes(first + b'{"time": 2.0}\n')
    out = anchor_command(repo, anchors)
    assert out.returncode != 0 and "CalledProcessError" in out.stderr
    assert index_lock.read_bytes() == b"stale lock kept for its owner\n"
    assert remote_file(remote).encode() == first
    assert remote_log(remote) == history


def test_normal_index_fsmonitor_startup_is_disabled(clone, tmp_path):
    """The per-command override suppresses a configured index-triggered monitor."""
    remote, repo = clone
    anchors = tmp_path / "anchors.jsonl"
    anchors.write_bytes(b'{"time": 1.0}\n')
    assert anchor_command(repo, anchors).returncode == 0
    invoked, monitor = tmp_path / "monitor-invoked", tmp_path / "fsmonitor"
    monitor.write_text(
        f"#!{sys.executable}\n"
        "from pathlib import Path\n"
        f"Path({str(invoked)!r}).touch()\n"
    )
    monitor.chmod(0o755)
    subprocess.run(
        ["git", "-C", str(repo), "config", "core.fsmonitor", str(monitor)], check=True
    )
    anchors.write_bytes(anchors.read_bytes() + b'{"time": 2.0}\n')
    out = anchor_command(repo, anchors)
    assert out.returncode == 0, out.stderr
    assert not invoked.exists()
    assert remote_file(remote).encode() == anchors.read_bytes()


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
    assert (
        "pipes" in rows[0]["output"] and "held open after the kill" in rows[0]["output"]
    )


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
        assert "command may still be running" in rows[0]["output"]
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
    assert all(
        copy.endswith(b"\n") and live.startswith(copy) for copy in copies.values()
    )


def test_a_retired_command_cannot_shrink_the_remote_after_the_final_push(
    clone, tmp_path, monkeypatch
):
    """A live old command released after finish cannot replace newer evidence."""
    remote, repo = clone
    folder = tmp_path / "run"
    folder.mkdir()
    delayed = tmp_path / "delayed-helper.py"
    delayed.write_text(
        "import os, sys\n"
        "ready, release = map(int, sys.argv[1:3])\n"
        "os.write(ready, b'1')\n"
        "os.close(ready)\n"
        "os.read(release, 1)\n"
        "os.close(release)\n"
        "os.execv(sys.executable, [sys.executable, *sys.argv[3:]])\n"
    )
    ready_read, ready_write = os.pipe()
    release_read, release_write = os.pipe()
    real_popen, children, waits = subprocess.Popen, [], []
    run = bare_finish_run(folder, [sys.executable, str(SCRIPT), "--repo", str(repo)])

    def popen(command, **kwargs):
        """Delay only the first real helper, before it can acquire the clone lock."""
        if len(command) > 1 and command[1] == str(SCRIPT):
            if not children:
                command = [
                    sys.executable,
                    str(delayed),
                    str(ready_write),
                    str(release_read),
                    *command[1:],
                ]
                kwargs["pass_fds"] = (ready_write, release_read)
            child = real_popen(command, **kwargs)
            children.append(child)
            return child
        return real_popen(command, **kwargs)

    def short_join(timeout=None):
        """Exercise retirement without waiting for the production join bound."""
        waits.append(timeout)
        return join(timeout=0.02)

    monkeypatch.setattr(cr.subprocess, "Popen", popen)
    monkeypatch.setattr(cr.signal, "signal", lambda *args: None)
    monkeypatch.setattr(cr, "ANCHOR_PUSH_TIMEOUT", 30.0)
    worker = join = None
    try:
        run.anchor()
        worker, join = run._push, run._push.join
        assert select.select([ready_read], [], [], 15.0)[0], (
            "the old command did not start"
        )
        assert os.read(ready_read, 1) == b"1"
        monkeypatch.setattr(worker, "join", short_join)
        run.finish()
        assert children[0].poll() is None
        newer = (folder / "anchors.jsonl").read_bytes()
        assert len(newer.splitlines()) == 2
        assert remote_file(remote).encode() == newer
        history = remote_log(remote)
        path = folder / "anchor-pushes.jsonl"
        before = path.read_bytes()
        rows = [json.loads(line) for line in before.splitlines()]
        assert waits == [pytest.approx(cr.ANCHOR_PUSH_TIMEOUT + cr.KILL_GRACE + 30)]
        assert [row["outcome"] for row in rows] == ["error", "success"]
        assert rows[0]["returncode"] is None
        assert "command may still be running" in rows[0]["output"]
    finally:
        try:
            os.write(release_write, b"1")
        except BrokenPipeError:
            pass
        if join is not None:
            join(timeout=45.0)
        for child in children:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        for fd in (ready_read, ready_write, release_read, release_write):
            os.close(fd)
    assert not worker.is_alive() and len(children) == 2
    assert children[0].returncode == 1
    assert path.read_bytes() == before
    assert remote_file(remote).encode() == newer
    assert remote_log(remote) == history
