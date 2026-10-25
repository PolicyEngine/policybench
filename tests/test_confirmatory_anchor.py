"""The anchor command: each call commits the run's anchors and pushes them."""

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import confirmatory_anchor  # noqa: E402

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
