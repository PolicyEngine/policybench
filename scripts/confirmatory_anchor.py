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
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", type=Path, required=True, help="the anchors clone")
    parser.add_argument("anchors", type=Path, help="a snapshot of the run's anchors.jsonl")
    args = parser.parse_args(argv)
    repo = args.repo.expanduser()
    target = repo / "anchors.jsonl"
    shutil.copyfile(args.anchors, target)
    lines = target.read_text().splitlines()
    git(repo, "add", "anchors.jsonl")
    if git(repo, "status", "--porcelain", "--", "anchors.jsonl"):
        head = hashlib.sha256(lines[-1].encode()).hexdigest() if lines else "none"
        git(repo, "commit", "-q", "-m", f"anchor {len(lines)}: {head}")
    git(repo, "push", "-q", "origin", "HEAD")
    print(f"pushed {len(lines)} anchors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
