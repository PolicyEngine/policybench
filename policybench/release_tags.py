"""Find the commit that holds each release's board, and seal the tag there.

A release ``dashboard-data-YYYYMMDD[a-z]`` is a GitHub release whose asset
``dashboard-data.json`` the committed pointer ``app/src/data.artifact.json``
names. The release has to exist before its PR merges, because CI's app job and
Vercel download the asset the PR's pointer names. GitHub therefore creates the
tag before the release PR's merge commit exists, on main as it stood then,
which holds the previous release's board.

A release's board commit is the first commit on main's first-parent line whose
pointer names the release's tag and the sha256 of the asset the release holds
now. For a release PR that is its squash commit. Sealing moves the tag to that
commit. The Seal release workflow seals each release when its PR merges, and
``policybench seal-release`` plans and makes the same move by hand.

The module uses only the standard library, so the workflow runs it as
``python -m policybench.release_tags`` without installing the package.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass

DEFAULT_REPO = "PolicyEngine/policybench"
DEFAULT_REF = "origin/main"
POINTER_PATH = "app/src/data.artifact.json"
ASSET_NAME = "dashboard-data.json"
TAG_PATTERN = re.compile(r"dashboard-data-\d{8}[a-z]?")


class ReleaseTagError(RuntimeError):
    pass


@dataclass(frozen=True)
class PointerCommit:
    """A commit that changed the pointer, and the pointer it committed."""

    commit: str
    tag: str
    sha256: str


@dataclass(frozen=True)
class Release:
    """A GitHub release and the sha256 GitHub records for its dashboard asset."""

    id: int
    sha256: str | None


@dataclass(frozen=True)
class TagPlan:
    """Where a release's tag points, and where its board is.

    ``action`` is ``sealed`` when the tag names the board commit, ``move`` when
    it names another commit, and ``leave`` when there is no board commit to
    move it to (``reason`` says why).
    """

    tag: str
    current: str | None
    board: str | None
    sha256: str | None
    reason: str | None = None

    @property
    def action(self) -> str:
        if self.board is None or self.current is None:
            return "leave"
        return "sealed" if self.current == self.board else "move"


# --- git ---------------------------------------------------------------------


def _git(root: str, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", root, *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip()
        raise ReleaseTagError(f"git {' '.join(args[:2])} failed: {detail}") from exc
    return result.stdout


def _pointer_at(root: str, commit: str, path: str) -> dict | None:
    """The pointer committed at ``commit``, or None when the commit has none."""
    try:
        text = _git(root, "show", f"{commit}:{path}")
    except ReleaseTagError:
        return None
    try:
        pointer = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReleaseTagError(
            f"{path} at {commit[:12]} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(pointer.get("tag"), str) or not isinstance(
        pointer.get("sha256"), str
    ):
        raise ReleaseTagError(f"{path} at {commit[:12]} names no tag and sha256")
    return pointer


def pointer_history(
    ref: str = DEFAULT_REF, *, root: str = ".", path: str = POINTER_PATH
) -> list[PointerCommit]:
    """Each commit on ``ref``'s first-parent line that changed the pointer,
    oldest first, with the tag and sha256 it committed. A commit that deleted
    the pointer is left out."""
    commits = _git(
        root, "log", "--first-parent", "--reverse", "--format=%H", ref, "--", path
    ).split()
    history = []
    for commit in commits:
        pointer = _pointer_at(root, commit, path)
        if pointer is not None:
            history.append(PointerCommit(commit, pointer["tag"], pointer["sha256"]))
    return history


def board_commit(history: list[PointerCommit], tag: str, sha256: str) -> str | None:
    """The first commit in ``history`` whose pointer names ``tag`` and
    ``sha256``, or None when none does."""
    for entry in history:
        if entry.tag == tag and entry.sha256 == sha256:
            return entry.commit
    return None


def live_tag(
    ref: str = DEFAULT_REF, *, root: str = ".", path: str = POINTER_PATH
) -> str:
    """The tag the pointer at ``ref`` names."""
    pointer = _pointer_at(root, _git(root, "rev-parse", ref).strip(), path)
    if pointer is None:
        raise ReleaseTagError(f"{ref} has no {path}")
    return pointer["tag"]


def is_ancestor(commit: str, of: str, *, root: str = ".") -> bool:
    """Whether ``commit`` is ``of`` or an ancestor of it."""
    result = subprocess.run(
        ["git", "-C", root, "merge-base", "--is-ancestor", commit, of],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise ReleaseTagError(
            f"git merge-base failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.returncode == 0


def commit_subject(commit: str, *, root: str = ".") -> str:
    return _git(root, "log", "-1", "--format=%s", commit).strip()


# --- GitHub ------------------------------------------------------------------


class _NotFound(Exception):
    pass


def _gh_api(*args: str) -> object:
    try:
        result = subprocess.run(
            ["gh", "api", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ReleaseTagError("GitHub CLI (gh) not found") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip()
        if "HTTP 404" in detail:
            raise _NotFound(detail) from exc
        raise ReleaseTagError(f"gh api {args[-1]} failed: {detail}") from exc
    return json.loads(result.stdout) if result.stdout.strip() else None


def _ref_commit(ref: dict, tag: str) -> str:
    target = ref["object"]
    if target["type"] != "commit":
        raise ReleaseTagError(
            f"{tag} is an annotated tag; only lightweight tags are sealed"
        )
    return target["sha"]


def remote_tag_commit(repo: str, tag: str) -> str | None:
    """The commit GitHub's tag names, or None when the tag does not exist."""
    try:
        ref = _gh_api(f"repos/{repo}/git/ref/tags/{tag}")
    except _NotFound:
        return None
    return _ref_commit(ref, tag)


def remote_release_tags(repo: str) -> dict[str, str]:
    """Every ``dashboard-data-*`` tag on GitHub and the commit it names."""
    refs = _gh_api("--paginate", f"repos/{repo}/git/matching-refs/tags/dashboard-data-")
    tags = {}
    for ref in refs or []:
        tag = ref["ref"].removeprefix("refs/tags/")
        if TAG_PATTERN.fullmatch(tag):
            tags[tag] = _ref_commit(ref, tag)
    return tags


def fetch_release(repo: str, tag: str, asset: str = ASSET_NAME) -> Release | None:
    """The release for ``tag``, or None when there is none. Its ``sha256`` is
    None when the release has no ``asset`` or GitHub records no digest for it."""
    try:
        release = _gh_api(f"repos/{repo}/releases/tags/{tag}")
    except _NotFound:
        return None
    sha256 = None
    for item in release.get("assets", []):
        digest = item.get("digest") or ""
        if item.get("name") == asset and digest.startswith("sha256:"):
            sha256 = digest.removeprefix("sha256:")
    return Release(id=release["id"], sha256=sha256)


def move_tag(repo: str, tag: str, commit: str) -> None:
    """Point GitHub's ``tag`` at ``commit`` and check that it does."""
    _gh_api(
        "-X",
        "PATCH",
        f"repos/{repo}/git/refs/tags/{tag}",
        "-f",
        f"sha={commit}",
        "-F",
        "force=true",
    )
    now = remote_tag_commit(repo, tag)
    if now != commit:
        raise ReleaseTagError(f"{tag} names {now} after the move, not {commit}")


def make_latest(repo: str, release: Release) -> None:
    _gh_api(
        "-X", "PATCH", f"repos/{repo}/releases/{release.id}", "-f", "make_latest=true"
    )


# --- plans -------------------------------------------------------------------


def plan_tag(
    tag: str,
    current: str | None,
    release: Release | None,
    history: list[PointerCommit],
) -> TagPlan:
    """Where ``tag`` should point, given its release and the pointer history."""
    if release is None:
        return TagPlan(tag, current, None, None, "no GitHub release has this tag")
    if release.sha256 is None:
        return TagPlan(
            tag,
            current,
            None,
            None,
            f"GitHub records no sha256 for the release's {ASSET_NAME}",
        )
    board = board_commit(history, tag, release.sha256)
    reason = None
    if board is None:
        reason = "no commit on main names this tag with the release's asset"
    elif current is None:
        reason = "the tag does not exist"
    return TagPlan(tag, current, board, release.sha256, reason)


@dataclass(frozen=True)
class Sealed:
    """What ``seal`` found and did. ``skipped`` says why it did nothing."""

    plan: TagPlan
    moved: bool
    skipped: str | None = None


def seal(
    tag: str,
    *,
    repo: str = DEFAULT_REPO,
    ref: str = DEFAULT_REF,
    root: str = ".",
    apply: bool = False,
    latest: bool = False,
    new_since: str | None = None,
) -> Sealed:
    """Plan, and with ``apply`` make, the move of ``tag`` to its board commit.

    Refuses when the release has no verifiable asset or no commit on ``ref``
    names it. With ``new_since``, does nothing unless the board commit is
    neither ``new_since`` nor an ancestor of it: the workflow passes the commit
    main named before the push, so it seals only a release that push landed.
    """
    release = fetch_release(repo, tag)
    current = remote_tag_commit(repo, tag)
    plan = plan_tag(tag, current, release, pointer_history(ref, root=root))
    if plan.action == "leave":
        raise ReleaseTagError(f"cannot seal {tag}: {plan.reason}")
    if new_since is not None and is_ancestor(plan.board, new_since, root=root):
        return Sealed(
            plan,
            moved=False,
            skipped=f"its board commit was on main at {new_since[:12]}, "
            "so this push landed no new release",
        )
    moved = False
    if apply:
        if plan.action == "move":
            move_tag(repo, tag, plan.board)
            moved = True
        if latest:
            make_latest(repo, release)
    return Sealed(plan, moved)


def plan_all(
    *, repo: str = DEFAULT_REPO, ref: str = DEFAULT_REF, root: str = "."
) -> list[TagPlan]:
    """A plan for every ``dashboard-data-*`` tag on GitHub, oldest first."""
    history = pointer_history(ref, root=root)
    tags = remote_release_tags(repo)
    return [
        plan_tag(tag, tags[tag], fetch_release(repo, tag), history)
        for tag in sorted(tags)
    ]


def apply_plans(plans: list[TagPlan], *, repo: str = DEFAULT_REPO) -> list[str]:
    """Move every tag whose plan is ``move``; return the tags moved."""
    moved = []
    for plan in plans:
        if plan.action == "move":
            move_tag(repo, plan.tag, plan.board)
            moved.append(plan.tag)
    return moved


# --- command line ------------------------------------------------------------

RELEASE_COMMIT_HELP = "Print the commit that holds a release's board"
SEAL_HELP = (
    "Plan, and with --apply make, the move of release tags to the commits "
    "that hold their boards"
)


def configure_release_commit_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("tag", help="Release tag, e.g. dashboard-data-20261010")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument(
        "--ref", default=DEFAULT_REF, help="Branch whose history holds the board"
    )
    parser.add_argument(
        "--sha256",
        help="The release asset's sha256; read from GitHub when omitted",
    )


def configure_seal_parser(parser: argparse.ArgumentParser) -> None:
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--tag", help="Seal this release tag")
    which.add_argument(
        "--live", action="store_true", help="Seal the tag the pointer at --ref names"
    )
    which.add_argument(
        "--all", action="store_true", help="Plan every dashboard-data-* tag"
    )
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument(
        "--ref", default=DEFAULT_REF, help="Branch whose history holds the board"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Move the tags; without it, only print the plan",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Also mark the sealed release Latest (with --tag or --live)",
    )
    parser.add_argument(
        "--new-since",
        metavar="COMMIT",
        help="Seal only a release whose board commit is not COMMIT or an "
        "ancestor of it (with --live)",
    )
    parser.add_argument("--json", action="store_true", help="Print the plan as JSON")


def _plan_line(plan: TagPlan, root: str) -> str:
    current = plan.current[:12] if plan.current else "-"
    board = plan.board[:12] if plan.board else "-"
    line = f"{plan.tag:26} {plan.action:6} tag {current:12} board {board:12}"
    if plan.board:
        line += f"  {commit_subject(plan.board, root=root)}"
    if plan.reason:
        line += f"  ({plan.reason})"
    return line


def _plan_record(plan: TagPlan) -> dict:
    return {**asdict(plan), "action": plan.action}


def run_release_commit(args: argparse.Namespace) -> None:
    sha256 = args.sha256
    if sha256 is None:
        release = fetch_release(args.repo, args.tag)
        if release is None or release.sha256 is None:
            raise SystemExit(
                f"{args.tag}: GitHub has no release asset sha256; pass --sha256"
            )
        sha256 = release.sha256
    commit = board_commit(pointer_history(args.ref), args.tag, sha256)
    if commit is None:
        raise SystemExit(
            f"{args.tag}: no commit on {args.ref} names it with sha256 {sha256[:12]}"
        )
    print(commit)


def run_seal(args: argparse.Namespace) -> None:
    root = "."
    skipped = None
    try:
        if args.all:
            if args.latest or args.new_since:
                raise SystemExit("--latest and --new-since need --tag or --live")
            plans = plan_all(repo=args.repo, ref=args.ref, root=root)
            moved = apply_plans(plans, repo=args.repo) if args.apply else []
        else:
            if args.new_since and not args.live:
                raise SystemExit("--new-since needs --live")
            tag = live_tag(args.ref, root=root) if args.live else args.tag
            result = seal(
                tag,
                repo=args.repo,
                ref=args.ref,
                root=root,
                apply=args.apply,
                latest=args.latest,
                new_since=args.new_since,
            )
            plans = [result.plan]
            moved = [tag] if result.moved else []
            skipped = result.skipped
    except ReleaseTagError as exc:
        raise SystemExit(str(exc)) from exc
    if args.json:
        print(json.dumps([_plan_record(plan) for plan in plans], indent=2))
        return
    for plan in plans:
        print(_plan_line(plan, root))
    if skipped:
        print(f"Left {plans[0].tag} alone: {skipped}")
        return
    count = len(moved) if args.apply else sum(p.action == "move" for p in plans)
    verb = "Moved" if args.apply else "Would move"
    print(f"{verb} {count} tag{'' if count == 1 else 's'}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m policybench.release_tags")
    commands = parser.add_subparsers(dest="command", required=True)
    configure_release_commit_parser(
        commands.add_parser("release-commit", help=RELEASE_COMMIT_HELP)
    )
    configure_seal_parser(commands.add_parser("seal-release", help=SEAL_HELP))
    args = parser.parse_args(argv)
    if args.command == "release-commit":
        run_release_commit(args)
    else:
        run_seal(args)


if __name__ == "__main__":
    main(sys.argv[1:])
