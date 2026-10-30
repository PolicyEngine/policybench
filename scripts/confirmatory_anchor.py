"""Push the confirmatory run's anchors outside the run.

Usage:
    python scripts/confirmatory_anchor.py --repo DIR ANCHORS

The runner calls this every 15 minutes and at its end (with up to three final
tries), with a snapshot of its `anchors.jsonl`: each line holds every log's
line count and chain head at a time. The snapshot is a copy, not a record.
This copies it to `anchors.jsonl` in DIR, a clone checked out on a branch
of its own, commits it and pushes the branch to its remote. The remote's record
of each push is the anchor's time from outside the run: a log edited after an
anchor was pushed no longer matches that anchor's head.

An exclusive non-blocking lock in the clone's `.git` directory covers every
read, copy, commit and push. Every Git command inherits its descriptor, so a
surviving command keeps the clone busy even if this helper alone is killed.
Ordinary local hooks and remote helpers inherit it too. The per-command
`core.fsmonitor=false` disables normal index-triggered fsmonitor startup.
A configured hook can still run `git fsmonitor--daemon start`, whose child
closes inherited descriptors; this falls under the configured-command limit:
configured commands must retain the descriptor without unlocking it in any
background clone writer. This advisory lock does not cover independent
writers or replacement of the lock file. The lock is local: processes on an
external remote server never hold it. The remote's safety rests on the byte-prefix
check and ordinary non-force pushes.

A credential-cache daemon or any other descriptor holder can keep the clone
busy up to the holder's lifetime (the credential cache defaults to 900
seconds), indefinitely if it never exits or closes the descriptor. Every
later try, including all three final tries, then fails as busy and is reported
as a failed push. A busy clone fails without changing its records. Under the
lock, the clone's current file must be a byte prefix of the snapshot (equality
is allowed): a delayed older command cannot replace newer evidence. This
checks bytes, not JSON or line boundaries; the runner supplies complete,
synced lines. Git's own index.lock is left alone; a git failure is a failed
push. Never force-push.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import subprocess
import sys
from pathlib import Path


def git(repo: Path, lock_fd: int, *args: str) -> str:
    """Run Git with the clone lock inherited, retaining failures for the caller."""
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        pass_fds=(lock_fd,),
    ).stdout


def main(argv=None) -> int:
    """Push a whole snapshot only while exclusively extending the clone's file."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", type=Path, required=True, help="the anchors clone")
    parser.add_argument(
        "anchors", type=Path, help="a snapshot of the run's anchors.jsonl"
    )
    args = parser.parse_args(argv)
    repo = args.repo.expanduser()
    target = repo / "anchors.jsonl"
    with (repo / ".git" / "confirmatory-anchor.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(
                "anchor clone busy: another helper or Git process holds its lock",
                file=sys.stderr,
            )
            return 1
        snapshot = args.anchors.read_bytes()
        current = target.read_bytes() if target.exists() else b""
        if not snapshot.startswith(current):
            print(
                "refusing anchor snapshot: the clone's anchors.jsonl is not a byte "
                "prefix of the snapshot",
                file=sys.stderr,
            )
            return 1
        if snapshot != current or not target.exists():
            target.write_bytes(snapshot)
        lines = snapshot.decode().splitlines()
        git(repo, lock.fileno(), "add", "anchors.jsonl")
        if git(repo, lock.fileno(), "status", "--porcelain", "--", "anchors.jsonl"):
            head = hashlib.sha256(lines[-1].encode()).hexdigest() if lines else "none"
            git(
                repo,
                lock.fileno(),
                "commit",
                "-q",
                "-m",
                f"anchor {len(lines)}: {head}",
            )
        git(repo, lock.fileno(), "push", "-q", "origin", "HEAD")
        print(f"pushed {len(lines)} anchors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
