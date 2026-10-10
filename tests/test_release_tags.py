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

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True)
        git(root, "init", "-q", "-b", "main")
        self.edits = 0
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
        else:
            self.merge(step[1])


@pytest.fixture
def scratch(tmp_path):
    return Scratch(tmp_path / "repo")


def first_parent_pointers(root: Path, ref: str = "main") -> list[tuple[str, tuple]]:
    """Every first-parent commit, oldest first, with the (tag, sha256) its
    tree holds, or None: the slow reference the fast history must agree with."""
    commits = git(root, "rev-list", "--first-parent", "--reverse", ref).split()
    out = []
    for commit in commits:
        try:
            pointer = json.loads(git(root, "show", f"{commit}:{rt.POINTER_PATH}"))
            out.append((commit, (pointer["tag"], pointer["sha256"])))
        except subprocess.CalledProcessError:
            out.append((commit, None))
    return out


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


def test_the_live_tag_is_the_one_the_pointer_at_the_ref_names(scratch):
    scratch.release(T1, SHAS["a"])
    scratch.release(T2, SHAS["b"])
    assert rt.live_tag("main", root=str(scratch.root)) == T2
    assert rt.live_tag("main~1", root=str(scratch.root)) == T1


STEP = st.one_of(
    st.tuples(st.just("release"), st.sampled_from([T1, T2, T3]), st.sampled_from("ab")),
    st.tuples(st.just("other")),
    st.tuples(st.just("delete")),
)
STEPS = st.lists(
    st.one_of(
        STEP,
        st.tuples(st.just("merge"), st.lists(STEP, min_size=1, max_size=3)),
    ),
    max_size=7,
)


@settings(max_examples=25, deadline=None)
@given(STEPS)
def test_the_fast_history_agrees_with_reading_every_first_parent_commit(steps):
    """Differential: the path-limited log finds the same board for every
    (tag, sha256) as reading the pointer at every first-parent commit."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Scratch(Path(tmp) / "repo")
        for step in steps:
            repo.apply(step)
        history = rt.pointer_history("main", root=str(repo.root))
        slow = first_parent_pointers(repo.root)
        for tag in (T1, T2, T3):
            for sha in SHAS.values():
                expected = next(
                    (commit for commit, named in slow if named == (tag, sha)), None
                )
                assert rt.board_commit(history, tag, sha) == expected
        # Each listed commit changed the pointer from its first parent's.
        named = dict(slow)
        order = [commit for commit, _ in slow]
        for entry in history:
            index = order.index(entry.commit)
            before = named[order[index - 1]] if index else None
            assert named[entry.commit] == (entry.tag, entry.sha256) != before


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

    def __init__(self, tags=None, releases=None, drift=None):
        self.tags = dict(tags or {})
        self.releases = dict(releases or {})
        self.drift = drift  # a commit the tag lands on instead of the asked one
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
                self.tags[tag] = self.drift or fields["sha"]
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


def test_seal_moves_the_tag_to_the_merge_commit_and_checks_it(scratch, github, landed):
    before, merge = landed
    result = rt.seal(T2, root=str(scratch.root), ref="main", apply=True)
    assert result.moved and result.skipped is None
    assert (result.plan.current, result.plan.board) == (before, merge)
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
    assert github.latest == []


def test_without_apply_seal_only_plans(scratch, github, landed):
    before, merge = landed
    result = rt.seal(T2, root=str(scratch.root), ref="main", latest=True)
    assert result.plan.action == "move" and not result.moved
    assert github.writes == [] and github.tags[T2] == before


def test_a_sealed_tag_is_not_moved_again_but_can_be_marked_latest(
    scratch, github, landed
):
    _, merge = landed
    github.tags[T2] = merge
    result = rt.seal(T2, root=str(scratch.root), ref="main", apply=True, latest=True)
    assert result.plan.action == "sealed" and not result.moved
    assert [call[2] for call in github.writes] == [f"repos/{REPO}/releases/7"]
    assert github.latest == [7]


def test_a_move_github_does_not_show_is_refused(scratch, github, landed):
    github.drift = "e" * 40
    with pytest.raises(rt.ReleaseTagError, match="after the move"):
        rt.seal(T2, root=str(scratch.root), ref="main", apply=True)


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
def test_seal_refuses_a_release_it_cannot_verify_and_writes_nothing(
    scratch, github, landed, setup, message
):
    setup(github)
    with pytest.raises(rt.ReleaseTagError, match=message):
        rt.seal(T2, root=str(scratch.root), ref="main", apply=True, latest=True)
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


def test_new_since_seals_only_a_release_the_push_landed(scratch, github, landed):
    before, merge = landed
    # The push from `before` to `merge` landed release T2: seal it.
    result = rt.seal(T2, root=str(scratch.root), ref="main", new_since=before)
    assert result.skipped is None and result.plan.action == "move"
    # A later push that leaves the pointer on T2 (or points back at it) did
    # not land it, so nothing is done.
    scratch.other()
    result = rt.seal(
        T2, root=str(scratch.root), ref="main", apply=True, latest=True, new_since=merge
    )
    assert result.skipped and not result.moved
    assert github.writes == [] and github.tags[T2] == before


def test_plan_all_covers_every_release_tag_and_apply_moves_only_the_moves(
    scratch, github
):
    first = scratch.release(T1, SHAS["a"])
    second = scratch.release(T2, SHAS["b"])
    github.tags = {T1: first, T2: first, T3: second, "v1.0": first}
    github.release(T1, SHAS["a"], release_id=1)
    github.release(T2, SHAS["b"], release_id=2)
    github.release(T3, SHAS["c"], release_id=3)  # never reached main
    plans = rt.plan_all(root=str(scratch.root), ref="main")
    assert [(p.tag, p.action) for p in plans] == [
        (T1, "sealed"),
        (T2, "move"),
        (T3, "leave"),
    ]
    assert rt.apply_plans(plans) == [T2]
    assert github.tags == {T1: first, T2: second, T3: second, "v1.0": first}
    assert [p.action for p in rt.plan_all(root=str(scratch.root), ref="main")] == [
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
    assert f"{T2}" in out and "move" in out and "Would move 1 tag\n" in out
    assert github.writes == []
    rt.main(["seal-release", "--live", "--ref", "main", "--json"])
    record = json.loads(capsys.readouterr().out)
    assert record[0]["tag"] == T2 and record[0]["action"] == "move"


def test_the_cli_live_seal_the_workflow_runs(
    scratch, github, landed, monkeypatch, capsys
):
    before, merge = landed
    monkeypatch.chdir(scratch.root)
    argv = ["seal-release", "--live", "--ref", merge, "--new-since", before]
    rt.main([*argv, "--apply", "--latest"])
    assert "Moved 1 tag\n" in capsys.readouterr().out
    assert github.tags[T2] == merge and github.latest == [7]
    # The workflow running again on the same push does nothing new.
    rt.main(["seal-release", "--live", "--ref", merge, "--new-since", merge, "--apply"])
    assert "Left" in capsys.readouterr().out
    assert len(github.writes) == 2


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
    ],
)
def test_seal_release_needs_exactly_one_target(argv):
    with pytest.raises(SystemExit) as raised:
        rt.main(argv)
    assert raised.value.code == 2


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--all", "--latest"], "need --tag or --live"),
        (["--all", "--new-since", "abc"], "need --tag or --live"),
        (["--tag", T1, "--new-since", "abc"], "--new-since needs --live"),
    ],
)
def test_flags_that_only_fit_one_live_seal_are_refused(argv, message, github):
    with pytest.raises(SystemExit, match=message):
        rt.main(["seal-release", *argv])
    assert github.calls == []


def test_the_policybench_cli_exposes_both_commands(
    scratch, github, landed, monkeypatch, capsys
):
    from policybench import cli

    _, merge = landed
    monkeypatch.chdir(scratch.root)
    monkeypatch.setattr(
        sys, "argv", ["policybench", "release-commit", T2, "--ref", "main"]
    )
    cli.main()
    assert capsys.readouterr().out == f"{merge}\n"
    monkeypatch.setattr(
        sys, "argv", ["policybench", "seal-release", "--all", "--ref", "main"]
    )
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


def test_the_workflow_seals_only_the_release_a_push_to_main_landed():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/seal-release.yml").read_text(encoding="utf-8")
    )
    trigger = workflow.get("on", workflow.get(True))
    assert trigger == {"push": {"branches": ["main"], "paths": [rt.POINTER_PATH]}}
    assert workflow["permissions"] == {"contents": "write"}
    (job,) = workflow["jobs"].values()
    checkout = next(
        s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout")
    )
    assert checkout["with"]["fetch-depth"] == 0
    (seal_step,) = [s for s in job["steps"] if "run" in s]
    command = seal_step["run"].split()
    assert command[:4] == ["python", "-m", "policybench.release_tags", "seal-release"]
    for flag in ("--live", "--apply", "--latest"):
        assert flag in command
    assert command[command.index("--ref") + 1] == '"$GITHUB_SHA"'
    assert command[command.index("--new-since") + 1] == '"$BEFORE"'
    assert seal_step["env"]["BEFORE"] == "${{ github.event.before }}"
    assert seal_step["env"]["GH_TOKEN"] == "${{ github.token }}"
    # The installed package is not needed, so the job does not sync it.
    assert not any("uv sync" in s.get("run", "") for s in job["steps"])


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
