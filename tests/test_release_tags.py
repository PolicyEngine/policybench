"""Tests for finding each release's board commit and sealing its tag there."""

import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from policybench import release_tags as rt
from policybench.release_tags import PointerCommit, Release

ROOT = Path(__file__).resolve().parents[1]
REPO = rt.DEFAULT_REPO
SHAS = {"a": "a" * 64, "b": "b" * 64, "c": "c" * 64}
T1, T2, T3 = (
    "dashboard-data-20270101",
    "dashboard-data-20270102",
    "dashboard-data-20270103",
)
GIT = ["-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false"]
GIT += ["-c", "user.name=t", "-c", "user.email=t@t"]


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *GIT, *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class Scratch:
    """A scratch repository whose main branch commits pointers."""

    def __init__(self, root: Path, *, root_release: tuple | None = None):
        self.root = root
        root.mkdir(parents=True)
        git(root, "init", "-q", "-b", "main")
        self.edits = 0
        if root_release:
            self.release(*root_release)
        else:
            self.other()

    def commit(self, message: str) -> str:
        git(self.root, "add", "-A")
        git(self.root, "commit", "--allow-empty", "-qm", message)
        return git(self.root, "rev-parse", "HEAD")

    def release(self, tag: str, sha256: str) -> str:
        pointer = self.root / rt.POINTER_PATH
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(
            json.dumps({"version": 1, "tag": tag, "sha256": sha256}, indent=2)
        )
        return self.commit(f"point at {tag}")

    def other(self) -> str:
        self.edits += 1
        (self.root / "notes.txt").write_text(str(self.edits))
        return self.commit("an unrelated change")

    def delete(self) -> str:
        (self.root / rt.POINTER_PATH).unlink()
        return self.commit("drop the pointer")

    def newline(self) -> str:
        """Add or drop the pointer's trailing newline, and nothing else."""
        pointer = self.root / rt.POINTER_PATH
        text = pointer.read_text()
        pointer.write_text(text[:-1] if text.endswith("\n") else text + "\n")
        return self.commit("touch the pointer's last line")

    def reformat(self) -> str:
        """Rewrite the pointer's bytes without changing its tag or sha256."""
        pointer = self.root / rt.POINTER_PATH
        record = json.loads(pointer.read_text())
        indent = 2 if pointer.read_text().startswith('{\n    "') else 4
        pointer.write_text(json.dumps(record, indent=indent, sort_keys=True))
        return self.commit("reformat the pointer")

    def merge(self, steps) -> str:
        """Apply ``steps`` on a side branch, then merge it with a merge commit."""
        git(self.root, "checkout", "-q", "-b", "side")
        for step in steps:
            self.apply(step)
        git(self.root, "checkout", "-q", "main")
        git(self.root, "merge", "-q", "--no-ff", "-m", "merge side", "side")
        git(self.root, "branch", "-q", "-D", "side")
        return git(self.root, "rev-parse", "HEAD")

    def apply(self, step) -> None:
        kind = step[0]
        if kind == "release":
            self.release(step[1], SHAS[step[2]])
        elif kind == "other":
            self.other()
        elif kind == "delete":
            if (self.root / rt.POINTER_PATH).exists():
                self.delete()
        elif kind == "reformat":
            if (self.root / rt.POINTER_PATH).exists():
                self.reformat()
        elif kind == "newline":
            if (self.root / rt.POINTER_PATH).exists():
                self.newline()
        else:
            self.merge(step[1])


@pytest.fixture
def scratch(tmp_path):
    return Scratch(tmp_path / "repo")


def raw_blob(root: Path, commit: str) -> str:
    """The pointer's exact bytes at ``commit``; raises when it has none."""
    return subprocess.run(
        ["git", "-C", str(root), "show", f"{commit}:{rt.POINTER_PATH}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def first_parent_blobs(root: Path, ref: str = "main") -> list[tuple[str, str]]:
    """Every first-parent commit, oldest first, with its pointer's bytes or
    None: the slow reference the path-limited history must agree with."""
    commits = git(root, "rev-list", "--first-parent", "--reverse", ref).split()
    out = []
    for commit in commits:
        try:
            out.append((commit, raw_blob(root, commit)))
        except subprocess.CalledProcessError:
            out.append((commit, None))
    return out


def expected_history(root: Path) -> list[tuple[str, tuple[str, str]]]:
    """Each first-parent commit whose pointer bytes differ from its first
    parent's and exist, with the tag and sha256 it names."""
    expected, previous = [], None
    for commit, blob in first_parent_blobs(root):
        if blob is not None and blob != previous:
            pointer = json.loads(blob)
            expected.append((commit, (pointer["tag"], pointer["sha256"])))
        previous = blob
    return expected


# --- the board commit --------------------------------------------------------


def test_the_board_is_the_first_main_commit_naming_the_tag_and_asset(scratch):
    first = scratch.release(T1, SHAS["a"])
    scratch.other()
    second = scratch.release(T2, SHAS["b"])
    scratch.other()
    history = rt.pointer_history("main", root=str(scratch.root))
    assert [entry.commit for entry in history] == [first, second]
    assert rt.board_commit(history, T1, SHAS["a"]) == first
    assert rt.board_commit(history, T2, SHAS["b"]) == second
    # The tag alone is not enough: the asset must be the bytes main named.
    assert rt.board_commit(history, T1, SHAS["b"]) is None
    assert rt.board_commit(history, T3, SHAS["a"]) is None


def test_a_replaced_asset_moves_the_board_to_the_commit_naming_the_new_bytes(
    scratch,
):
    # Release 20260705's shape: the asset was replaced under the same tag.
    original = scratch.release(T1, SHAS["a"])
    replaced = scratch.release(T1, SHAS["b"])
    history = rt.pointer_history("main", root=str(scratch.root))
    assert rt.board_commit(history, T1, SHAS["b"]) == replaced
    assert rt.board_commit(history, T1, SHAS["a"]) == original


def test_pointing_back_at_an_older_release_keeps_its_first_board(scratch):
    first = scratch.release(T1, SHAS["a"])
    scratch.release(T2, SHAS["b"])
    scratch.release(T1, SHAS["a"])
    history = rt.pointer_history("main", root=str(scratch.root))
    assert rt.board_commit(history, T1, SHAS["a"]) == first


def test_a_side_branch_commit_is_never_a_board_only_the_merge_is(scratch):
    git(scratch.root, "checkout", "-q", "-b", "side")
    on_side = scratch.release(T1, SHAS["a"])
    git(scratch.root, "checkout", "-q", "main")
    git(scratch.root, "merge", "-q", "--no-ff", "-m", "merge side", "side")
    merge = git(scratch.root, "rev-parse", "HEAD")
    history = rt.pointer_history("main", root=str(scratch.root))
    assert rt.board_commit(history, T1, SHAS["a"]) == merge != on_side


def test_a_deleted_pointer_is_left_out_of_the_history(scratch):
    first = scratch.release(T1, SHAS["a"])
    scratch.delete()
    again = scratch.release(T2, SHAS["b"])
    history = rt.pointer_history("main", root=str(scratch.root))
    assert [entry.commit for entry in history] == [first, again]


def test_an_unreadable_pointer_is_refused(scratch):
    pointer = scratch.root / rt.POINTER_PATH
    pointer.parent.mkdir(parents=True)
    pointer.write_text("{not json")
    scratch.commit("break the pointer")
    with pytest.raises(rt.ReleaseTagError, match="is not valid JSON"):
        rt.pointer_history("main", root=str(scratch.root))


def test_a_pointer_without_a_tag_and_sha256_is_refused(scratch):
    pointer = scratch.root / rt.POINTER_PATH
    pointer.parent.mkdir(parents=True)
    pointer.write_text(json.dumps({"tag": T1}))
    scratch.commit("half a pointer")
    with pytest.raises(rt.ReleaseTagError, match="names no tag and sha256"):
        rt.pointer_history("main", root=str(scratch.root))


def test_the_live_pointer_is_the_one_at_the_ref(scratch):
    scratch.release(T1, SHAS["a"])
    scratch.release(T2, SHAS["b"])
    assert rt.live_pointer("main", root=str(scratch.root)) == (T2, SHAS["b"])
    assert rt.live_pointer("main~1", root=str(scratch.root)) == (T1, SHAS["a"])


STEP = st.one_of(
    st.tuples(st.just("release"), st.sampled_from([T1, T2, T3]), st.sampled_from("ab")),
    st.tuples(st.just("other")),
    st.tuples(st.just("delete")),
    st.tuples(st.just("reformat")),
    st.tuples(st.just("newline")),
)
STEPS = st.lists(
    st.one_of(
        STEP,
        st.tuples(st.just("merge"), st.lists(STEP, min_size=1, max_size=3)),
    ),
    max_size=7,
)
ROOT_RELEASE = st.one_of(
    st.none(), st.tuples(st.sampled_from([T1, T2]), st.sampled_from(["a" * 64]))
)


@settings(max_examples=25, deadline=None)
@given(STEPS, ROOT_RELEASE)
def test_the_fast_history_is_every_first_parent_pointer_change(steps, root_release):
    """Differential: the path-limited log lists exactly the first-parent
    commits whose pointer bytes differ from their first parent's, root commit,
    merges, rollbacks, reformats and re-additions included, and so finds the
    same board for every (tag, sha256) as reading every commit."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Scratch(Path(tmp) / "repo", root_release=root_release)
        for step in steps:
            repo.apply(step)
        history = rt.pointer_history("main", root=str(repo.root))
        expected = expected_history(repo.root)
        assert [(e.commit, (e.tag, e.sha256)) for e in history] == expected
        for tag in (T1, T2, T3):
            for sha in SHAS.values():
                first = next((c for c, named in expected if named == (tag, sha)), None)
                assert rt.board_commit(history, tag, sha) == first


# --- plans -------------------------------------------------------------------

HISTORIES = st.lists(
    st.tuples(st.sampled_from([T1, T2, T3]), st.sampled_from(sorted(SHAS.values()))),
    max_size=8,
).map(
    lambda pairs: [
        PointerCommit(f"{i:040x}", tag, sha) for i, (tag, sha) in enumerate(pairs)
    ]
)
RELEASES = st.one_of(
    st.none(),
    st.builds(Release, id=st.just(1), sha256=st.none()),
    st.builds(Release, id=st.just(1), sha256=st.sampled_from(sorted(SHAS.values()))),
)


@settings(max_examples=300, deadline=None)
@given(
    HISTORIES,
    st.sampled_from([T1, T2, T3]),
    RELEASES,
    st.one_of(st.none(), st.integers(0, 9).map(lambda i: f"{i:040x}")),
)
def test_a_plan_moves_a_tag_only_to_its_board_and_sealing_twice_is_a_no_op(
    history, tag, release, current
):
    plan = rt.plan_tag(tag, current, release, history)
    if release is None or release.sha256 is None:
        assert plan.board is None and plan.action == "leave" and plan.reason
        return
    board = rt.board_commit(history, tag, release.sha256)
    assert plan.board == board
    if board is not None:
        first = next(e for e in history if e.commit == board)
        assert (first.tag, first.sha256) == (tag, release.sha256)
        earlier = history[: history.index(first)]
        assert (tag, release.sha256) not in {(e.tag, e.sha256) for e in earlier}
    if board is None or current is None:
        assert plan.action == "leave" and plan.reason
    elif current == board:
        assert plan.action == "sealed" and plan.reason is None
    else:
        assert plan.action == "move"
        # After the move, the same plan finds nothing left to do.
        again = rt.plan_tag(tag, board, release, history)
        assert again.action == "sealed"


# --- GitHub, faked -----------------------------------------------------------


class FakeGitHub:
    """Stands in for ``gh api``: tags, releases, and every call made."""

    def __init__(self):
        self.tags = {}
        self.releases = {}
        self.drift = None  # a commit a moved tag lands on instead of the asked one
        self.after_move = None  # called after each tag move
        self.deny = set()  # tags whose move GitHub refuses
        self.calls = []
        self.latest = []

    def release(self, tag, sha256, *, release_id=7, asset=rt.ASSET_NAME):
        assets = [{"name": "predictions.csv.gz", "digest": "sha256:" + "f" * 64}]
        assets.append({"name": asset, "digest": sha256 and f"sha256:{sha256}"})
        self.releases[tag] = {"id": release_id, "tag_name": tag, "assets": assets}

    @property
    def writes(self):
        return [call for call in self.calls if call[0] == "-X"]

    def __call__(self, *args):
        self.calls.append(args)
        if args[0] == "-X":
            path = args[2]
            fields = dict(a.split("=", 1) for a in args[3:] if "=" in a)
            if "/git/refs/tags/" in path:
                tag = path.rsplit("/git/refs/tags/", 1)[1]
                assert fields == {"sha": fields["sha"], "force": "true"}
                if tag in self.deny:
                    raise rt.ReleaseTagError(f"gh api {path} failed: HTTP 403")
                self.tags[tag] = self.drift or fields["sha"]
                if self.after_move:
                    self.after_move()
                return {"ref": f"refs/tags/{tag}"}
            assert fields == {"make_latest": "true"}
            self.latest.append(int(path.rsplit("/", 1)[1]))
            return {}
        if args[0] == "--paginate":
            return [
                {"ref": f"refs/tags/{t}", "object": {"sha": c, "type": "commit"}}
                for t, c in self.tags.items()
            ]
        path = args[0]
        if "/git/ref/tags/" in path:
            tag = path.rsplit("/git/ref/tags/", 1)[1]
            if tag not in self.tags:
                raise rt._NotFound(tag)
            return {"object": {"sha": self.tags[tag], "type": "commit"}}
        tag = path.rsplit("/releases/tags/", 1)[1]
        if tag not in self.releases:
            raise rt._NotFound(tag)
        return self.releases[tag]


@pytest.fixture
def github(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(rt, "_gh_api", fake)
    return fake


@pytest.fixture
def landed(scratch, github):
    """Main before the release PR, its merge, and a release whose tag GitHub
    put on main as it stood before the merge."""
    before = scratch.release(T1, SHAS["a"])
    merge = scratch.release(T2, SHAS["b"])
    github.tags[T2] = before
    github.release(T2, SHAS["b"])
    return before, merge


def where(scratch):
    return {"root": str(scratch.root), "ref": "main"}


def test_a_move_puts_the_tag_on_the_merge_commit_and_checks_it(scratch, github, landed):
    before, merge = landed
    plan = rt.plan_one(T2, **where(scratch))
    assert (plan.action, plan.current, plan.board) == ("move", before, merge)
    assert rt.apply_plans([plan]) == ([T2], {})
    assert github.tags[T2] == merge
    assert github.writes == [
        (
            "-X",
            "PATCH",
            f"repos/{REPO}/git/refs/tags/{T2}",
            "-f",
            f"sha={merge}",
            "-F",
            "force=true",
        )
    ]
    # The asset digest was read for the plan, before the move and after it.
    reads = [c for c in github.calls if c[0] == f"repos/{REPO}/releases/tags/{T2}"]
    assert len(reads) == 3
    assert github.latest == []


def test_a_sealed_tag_is_not_moved_again(scratch, github, landed):
    _, merge = landed
    github.tags[T2] = merge
    plan = rt.plan_one(T2, **where(scratch))
    assert plan.action == "sealed"
    assert rt.apply_plans([plan]) == ([], {}) and github.writes == []


def test_a_move_github_does_not_show_is_refused(scratch, github, landed):
    github.drift = "e" * 40
    with pytest.raises(rt.ReleaseTagError, match="after the move"):
        rt.checked_move(rt.plan_one(T2, **where(scratch)))


def test_an_asset_replaced_after_planning_is_refused_before_the_move(
    scratch, github, landed
):
    # Release 20260705's shape, mid-run: the plan was made for the old bytes.
    plan = rt.plan_one(T2, **where(scratch))
    github.release(T2, SHAS["c"])
    with pytest.raises(rt.ReleaseTagError, match="changed before the move"):
        rt.checked_move(plan)
    assert github.writes == []


def test_an_asset_replaced_during_the_move_is_reported(scratch, github, landed):
    _, merge = landed
    github.after_move = lambda: github.release(T2, SHAS["c"])
    with pytest.raises(
        rt.ReleaseTagError, match=f"changed after the move.*{merge[:12]}"
    ):
        rt.checked_move(rt.plan_one(T2, **where(scratch)))


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        (lambda gh: gh.releases.pop(T2), "no GitHub release has this tag"),
        (lambda gh: gh.release(T2, None), "GitHub records no sha256"),
        (lambda gh: gh.release(T2, SHAS["c"]), "no commit on main names this tag"),
        (lambda gh: gh.release(T2, SHAS["b"], asset="other.json"), "no sha256"),
        (lambda gh: gh.tags.pop(T2), "the tag does not exist"),
    ],
)
def test_sealing_one_tag_refuses_a_release_it_cannot_verify(
    scratch, github, landed, monkeypatch, setup, message
):
    setup(github)
    monkeypatch.chdir(scratch.root)
    with pytest.raises(SystemExit, match=message):
        rt.main(["seal-release", "--tag", T2, "--ref", "main", "--apply"])
    assert github.writes == []


def test_an_annotated_tag_is_refused(github, monkeypatch):
    github.tags[T2] = "d" * 40

    def annotated(*args):
        result = github(*args)
        if "/git/ref/tags/" in args[0]:
            result["object"]["type"] = "tag"
        return result

    monkeypatch.setattr(rt, "_gh_api", annotated)
    with pytest.raises(rt.ReleaseTagError, match="annotated tag"):
        rt.remote_tag_commit(REPO, T2)


# --- the releases that landed (what the workflow runs) -------------------------


def test_every_release_landed_since_sealing_began_is_sealed_in_one_run(scratch, github):
    # GitHub cancels a pending run when a newer one queues, so one run must
    # seal every release that has landed, not just the newest.
    start = git(scratch.root, "rev-parse", "HEAD")
    first = scratch.release(T1, SHAS["a"])
    scratch.other()
    second = scratch.release(T2, SHAS["b"])
    github.tags = {T1: start, T2: first}
    github.release(T1, SHAS["a"], release_id=1)
    github.release(T2, SHAS["b"], release_id=2)
    plans = rt.plan_landed(start, **where(scratch))
    assert [(p.tag, p.action, p.board) for p in plans] == [
        (T1, "move", first),
        (T2, "move", second),
    ]
    assert rt.apply_plans(plans) == ([T1, T2], {})
    assert rt.plan_landed(start, **where(scratch))[0].action == "sealed"


def test_an_older_release_main_points_back_at_is_left_alone(scratch, github):
    old_board = scratch.release(T1, SHAS["a"])
    start = scratch.release(T2, SHAS["b"])
    scratch.release(T1, SHAS["a"])  # main points back at T1 after sealing began
    github.tags = {T1: "1" * 40, T2: old_board}
    github.release(T1, SHAS["a"], release_id=1)
    github.release(T2, SHAS["b"], release_id=2)
    assert rt.plan_landed(start, **where(scratch)) == []
    assert rt.apply_plans(rt.plan_landed(start, **where(scratch))) == ([], {})
    assert github.writes == [] and github.tags[T1] == "1" * 40


def test_an_earlier_release_stays_out_even_after_its_asset_is_replaced(scratch, github):
    # Replace release T1's asset and land a pointer naming the new bytes after
    # sealing began: T1 was named before, so its tag stays a manual re-point.
    old_board = scratch.release(T1, SHAS["a"])
    start = scratch.other()
    scratch.release(T1, SHAS["c"])
    github.tags = {T1: old_board}
    github.release(T1, SHAS["c"], release_id=1)
    assert rt.plan_landed(start, **where(scratch)) == []


def test_a_start_that_is_not_an_ancestor_of_the_ref_is_refused(scratch, github):
    scratch.release(T1, SHAS["a"])
    git(scratch.root, "checkout", "-q", "-b", "elsewhere", "HEAD~1")
    elsewhere = scratch.other()
    git(scratch.root, "checkout", "-q", "main")
    with pytest.raises(rt.ReleaseTagError, match="not main or an ancestor"):
        rt.plan_landed(elsewhere, **where(scratch))
    assert github.calls == []


def test_a_shallow_clone_is_refused(scratch, tmp_path):
    scratch.release(T1, SHAS["a"])
    scratch.other()
    scratch.release(T2, SHAS["b"])
    shallow = tmp_path / "shallow"
    url = f"file://{scratch.root}"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", url, str(shallow)], check=True
    )
    with pytest.raises(rt.ReleaseTagError, match="shallow"):
        rt.pointer_history("HEAD", root=str(shallow))


def test_a_refused_move_does_not_stop_the_others_or_latest(
    scratch, github, monkeypatch, capsys
):
    start = git(scratch.root, "rev-parse", "HEAD")
    first = scratch.release(T1, SHAS["a"])
    second = scratch.release(T2, SHAS["b"])
    github.tags = {T1: start, T2: first}
    github.release(T1, SHAS["a"], release_id=1)
    github.release(T2, SHAS["b"], release_id=2)
    github.deny = {T1}
    monkeypatch.chdir(scratch.root)
    argv = ["seal-release", "--landed-after", start, "--ref", "main", "--apply"]
    with pytest.raises(SystemExit, match=f"cannot move {T1}: .*HTTP 403"):
        rt.main([*argv, "--latest"])
    assert github.tags == {T1: start, T2: second}
    assert github.latest == [2]
    assert "Moved 1 tag\nMarked " + T2 + " Latest" in capsys.readouterr().out


def test_latest_is_left_alone_when_the_live_releases_own_move_fails(
    scratch, github, monkeypatch
):
    start = git(scratch.root, "rev-parse", "HEAD")
    first = scratch.release(T1, SHAS["a"])
    scratch.release(T2, SHAS["b"])
    github.tags = {T1: start, T2: first}
    github.release(T1, SHAS["a"], release_id=1)
    github.release(T2, SHAS["b"], release_id=2)
    github.deny = {T2}
    monkeypatch.chdir(scratch.root)
    argv = ["seal-release", "--landed-after", start, "--ref", "main", "--apply"]
    with pytest.raises(SystemExit, match=f"left Latest alone: {T2}"):
        rt.main([*argv, "--latest"])
    assert github.tags[T1] == first and github.latest == []


def test_a_landed_release_that_cannot_be_sealed_fails_the_run_after_the_others(
    scratch, github, monkeypatch, capsys
):
    start = git(scratch.root, "rev-parse", "HEAD")
    first = scratch.release(T1, SHAS["a"])
    scratch.release(T2, SHAS["b"])
    github.tags = {T1: start, T2: first}
    github.release(T1, SHAS["a"], release_id=1)
    github.release(T2, SHAS["c"], release_id=2)  # bytes no pointer names
    monkeypatch.chdir(scratch.root)
    argv = ["seal-release", "--landed-after", start, "--ref", "main", "--apply"]
    with pytest.raises(SystemExit, match=f"cannot seal {T2}"):
        rt.main(argv)
    assert github.tags[T1] == first and github.tags[T2] == first
    assert "Moved 1 tag" in capsys.readouterr().out


def test_latest_follows_the_release_main_serves_not_the_run(
    scratch, github, monkeypatch, capsys
):
    # A re-run of an older push still marks the release main serves now.
    start = git(scratch.root, "rev-parse", "HEAD")
    first = scratch.release(T1, SHAS["a"])
    second = scratch.release(T2, SHAS["b"])
    github.tags = {T1: first, T2: second}
    github.release(T1, SHAS["a"], release_id=1)
    github.release(T2, SHAS["b"], release_id=2)
    monkeypatch.chdir(scratch.root)
    argv = ["seal-release", "--landed-after", start, "--ref", "main", "--apply"]
    rt.main([*argv, "--latest"])
    assert github.latest == [2]
    assert "Moved 0 tags\nMarked " + T2 + " Latest" in capsys.readouterr().out


def test_latest_is_refused_when_the_release_does_not_hold_the_pointers_bytes(
    scratch, github, landed
):
    github.release(T2, SHAS["c"])
    with pytest.raises(rt.ReleaseTagError, match="not marking it Latest"):
        rt.promote_live(**where(scratch))
    assert github.latest == []


def test_sealing_starts_after_the_last_board_cut_before_the_workflow():
    """The workflow never moves the tags of the releases in the runbook
    table: each of their board commits is this commit or an ancestor of it."""
    history = rt.pointer_history("HEAD", root=str(ROOT))
    live = [e for e in history if e.tag == "dashboard-data-20261010"]
    assert [e.commit for e in live][0] == rt.SEALING_STARTS_AFTER
    rows = RUNBOOK_ROW.findall((ROOT / "docs/runbook.md").read_text(encoding="utf-8"))
    for _, commit, _ in rows:
        full = git(ROOT, "rev-parse", commit)
        git(ROOT, "merge-base", "--is-ancestor", full, rt.SEALING_STARTS_AFTER)


def test_plan_all_covers_every_release_tag_and_apply_moves_only_the_moves(
    scratch, github
):
    first = scratch.release(T1, SHAS["a"])
    second = scratch.release(T2, SHAS["b"])
    github.tags = {T1: first, T2: first, T3: second, "v1.0": first}
    github.release(T1, SHAS["a"], release_id=1)
    github.release(T2, SHAS["b"], release_id=2)
    github.release(T3, SHAS["c"], release_id=3)  # never reached main
    plans = rt.plan_all(**where(scratch))
    assert [(p.tag, p.action) for p in plans] == [
        (T1, "sealed"),
        (T2, "move"),
        (T3, "leave"),
    ]
    assert rt.apply_plans(plans) == ([T2], {})
    assert github.tags == {T1: first, T2: second, T3: second, "v1.0": first}
    assert [p.action for p in rt.plan_all(**where(scratch))] == [
        "sealed",
        "sealed",
        "leave",
    ]


def test_gh_api_tells_a_404_from_other_failures(monkeypatch):
    def failing(stderr):
        def run(args, **kwargs):
            raise subprocess.CalledProcessError(1, args, stderr=stderr)

        return run

    monkeypatch.setattr(rt.subprocess, "run", failing("gh: Not Found (HTTP 404)"))
    assert rt.remote_tag_commit(REPO, T1) is None
    assert rt.fetch_release(REPO, T1) is None
    monkeypatch.setattr(rt.subprocess, "run", failing("HTTP 403: forbidden"))
    with pytest.raises(rt.ReleaseTagError, match="HTTP 403"):
        rt.remote_tag_commit(REPO, T1)

    def missing(args, **kwargs):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(rt.subprocess, "run", missing)
    with pytest.raises(rt.ReleaseTagError, match="gh\\) not found"):
        rt.fetch_release(REPO, T1)


# --- the command line --------------------------------------------------------


def test_the_cli_plans_without_writing_and_reports_the_count(
    scratch, github, landed, monkeypatch, capsys
):
    monkeypatch.chdir(scratch.root)
    rt.main(["seal-release", "--all", "--ref", "main"])
    out = capsys.readouterr().out
    assert T2 in out and "move" in out and "Would move 1 tag\n" in out
    rt.main(["seal-release", "--live", "--ref", "main", "--json"])
    record = json.loads(capsys.readouterr().out)
    assert record[0]["tag"] == T2 and record[0]["action"] == "move"
    assert github.writes == []
    with pytest.raises(SystemExit, match="--latest needs --apply"):
        rt.main(["seal-release", "--all", "--ref", "main", "--latest"])
    assert github.writes == []


def test_the_cli_live_seal_moves_and_marks_latest(
    scratch, github, landed, monkeypatch, capsys
):
    _, merge = landed
    monkeypatch.chdir(scratch.root)
    rt.main(["seal-release", "--live", "--ref", "main", "--apply", "--latest"])
    assert "Moved 1 tag\nMarked " + T2 + " Latest" in capsys.readouterr().out
    assert github.tags[T2] == merge and github.latest == [7]


def test_release_commit_prints_the_board(scratch, github, landed, monkeypatch, capsys):
    _, merge = landed
    monkeypatch.chdir(scratch.root)
    rt.main(["release-commit", T2, "--ref", "main"])
    assert capsys.readouterr().out == f"{merge}\n"
    rt.main(["release-commit", T1, "--ref", "main", "--sha256", SHAS["a"]])
    assert capsys.readouterr().out.strip() == git(scratch.root, "rev-parse", "main~1")
    with pytest.raises(SystemExit, match="no commit on main names it"):
        rt.main(["release-commit", T1, "--ref", "main", "--sha256", SHAS["c"]])


@pytest.mark.parametrize(
    "argv",
    [
        ["seal-release"],
        ["seal-release", "--tag", T1, "--all"],
        ["seal-release", "--landed-after", "--live"],
    ],
)
def test_seal_release_needs_exactly_one_target(argv):
    with pytest.raises(SystemExit) as raised:
        rt.main(argv)
    assert raised.value.code == 2


def test_landed_after_defaults_to_where_sealing_began():
    parser = rt.argparse.ArgumentParser()
    rt.configure_seal_parser(parser)
    assert parser.parse_args(["--landed-after"]).landed_after == (
        rt.SEALING_STARTS_AFTER
    )
    assert parser.parse_args(["--landed-after", "abc"]).landed_after == "abc"


def test_the_policybench_cli_exposes_both_commands(
    scratch, github, landed, monkeypatch, capsys
):
    from policybench import cli

    _, merge = landed
    monkeypatch.chdir(scratch.root)
    argv = ["policybench", "release-commit", T2, "--ref", "main"]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    assert capsys.readouterr().out == f"{merge}\n"
    argv = ["policybench", "seal-release", "--all", "--ref", "main"]
    monkeypatch.setattr(sys, "argv", argv)
    cli.main()
    assert "Would move 1 tag" in capsys.readouterr().out


# --- the workflow and the record ---------------------------------------------


def test_the_module_imports_only_the_standard_library():
    """The Seal release workflow runs it without installing the package."""
    tree = ast.parse(Path(rt.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported - {"__future__"} <= set(sys.stdlib_module_names)


def test_the_workflow_seals_the_landed_releases_against_main_as_it_is_now():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/seal-release.yml").read_text(encoding="utf-8")
    )
    trigger = workflow.get("on", workflow.get(True))
    assert trigger == {"push": {"branches": ["main"], "paths": [rt.POINTER_PATH]}}
    assert workflow["permissions"] == {"contents": "write"}
    assert workflow["concurrency"]["cancel-in-progress"] is False
    (job,) = workflow["jobs"].values()
    steps = job["steps"]
    checkout = next(
        s for s in steps if s.get("uses", "").startswith("actions/checkout")
    )
    assert checkout["with"]["fetch-depth"] == 0
    runs = [s for s in steps if "run" in s]
    fetch, seal_step = runs
    assert fetch["run"].split()[-1] == "+refs/heads/main:refs/remotes/origin/main"
    command = seal_step["run"].split()
    assert command[:4] == ["python", "-m", "policybench.release_tags", "seal-release"]
    # --landed-after takes its default, the commit where sealing began.
    assert command[command.index("--landed-after") + 1].startswith("--")
    assert command[command.index("--ref") + 1] == "origin/main"
    assert "--apply" in command and "--latest" in command
    # Nothing comes from the push event, which a re-run replays.
    assert "github.event" not in json.dumps(job) and "GITHUB_SHA" not in json.dumps(job)
    assert seal_step["env"] == {"GH_TOKEN": "${{ github.token }}"}
    # The module needs only the standard library, so the job installs nothing.
    assert not any(
        "uv " in s.get("run", "") or "pip" in s.get("run", "") for s in steps
    )


# The runbook's table of releases cut before sealing, checked against git.
RUNBOOK_ROW = re.compile(
    r"^\| `(dashboard-data-\d{8}[a-z]?)` \| `([0-9a-f]{12})` \| `([0-9a-f]{12})` \|",
    re.M,
)
LAST_UNSEALED = "dashboard-data-20261010"
NEVER_ON_MAIN = {
    "dashboard-data-20260709",
    "dashboard-data-20260901",
    "dashboard-data-20260901b",
    "dashboard-data-20260905",
    "dashboard-data-20260905b",
}
NO_RELEASE = {"dashboard-data-20260705b"}


def test_the_runbook_names_each_older_releases_board_commit():
    rows = RUNBOOK_ROW.findall((ROOT / "docs/runbook.md").read_text(encoding="utf-8"))
    assert len(rows) == 29
    history = rt.pointer_history("HEAD", root=str(ROOT))
    for tag, commit, sha_prefix in rows:
        shas = {
            e.sha256
            for e in history
            if e.tag == tag and e.sha256.startswith(sha_prefix)
        }
        assert len(shas) == 1, tag
        board = rt.board_commit(history, tag, shas.pop())
        assert board is not None and board.startswith(commit), tag
    on_main = {e.tag for e in history if e.tag <= LAST_UNSEALED}
    assert on_main == {tag for tag, _, _ in rows} | NO_RELEASE
    assert not NEVER_ON_MAIN & {e.tag for e in history}
    runbook = (ROOT / "docs/runbook.md").read_text(encoding="utf-8")
    for tag in NEVER_ON_MAIN | NO_RELEASE:
        assert tag.removeprefix("dashboard-data") in runbook
