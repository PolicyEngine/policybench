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
commit. The Seal release workflow seals every release that has landed since
sealing began and marks the release main serves Latest; ``policybench
seal-release`` plans and makes the same moves by hand.

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
# The merge of PR #208, which holds release dashboard-data-20261010: the last
# board before the Seal release workflow. The workflow seals releases main first
# names after it; tags of earlier releases are re-pointed by hand.
SEALING_STARTS_AFTER = "5a8164a001efb27fa55f47fe7ea26666a0de31f8"


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
    the pointer is left out. A shallow clone is refused: its history may
    start after a release's first commit, and a later one would pass for it."""
    if _git(root, "rev-parse", "--is-shallow-repository").strip() != "false":
        raise ReleaseTagError(
            "this clone is shallow, so a release's first commit may be missing; "
            "run git fetch --unshallow"
        )
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


def live_pointer(
    ref: str = DEFAULT_REF, *, root: str = ".", path: str = POINTER_PATH
) -> tuple[str, str]:
    """The tag and sha256 the pointer at ``ref`` names."""
    pointer = _pointer_at(root, _git(root, "rev-parse", ref).strip(), path)
    if pointer is None:
        raise ReleaseTagError(f"{ref} has no {path}")
    return pointer["tag"], pointer["sha256"]


def is_ancestor(commit: str, of: str, *, root: str = ".") -> bool:
    """Whether ``commit`` is ``of`` or an ancestor of it."""
    result = subprocess.run(
        ["git", "-C", root, "merge-base", "--is-ancestor", commit, of],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        detail = result.stderr.strip() or result.stdout.strip()
        raise ReleaseTagError(f"git merge-base failed: {detail}")
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


def plan_one(
    tag: str, *, repo: str = DEFAULT_REPO, ref: str = DEFAULT_REF, root: str = "."
) -> TagPlan:
    history = pointer_history(ref, root=root)
    return plan_tag(
        tag, remote_tag_commit(repo, tag), fetch_release(repo, tag), history
    )


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


def plan_landed(
    after: str = SEALING_STARTS_AFTER,
    *,
    repo: str = DEFAULT_REPO,
    ref: str = DEFAULT_REF,
    root: str = ".",
) -> list[TagPlan]:
    """A plan for every release that landed on ``ref`` after ``after``.

    A tag counts when main first names it after ``after``. A tag that main
    named at or before ``after`` belongs to an earlier release, whatever asset
    it holds now, and is left out: those tags are re-pointed by hand. A plan
    with no board stays in, so the caller can report it.
    """
    history = pointer_history(ref, root=root)
    if not is_ancestor(after, ref, root=root):
        raise ReleaseTagError(
            f"{after[:12]} is not {ref} or an ancestor of it, so the releases "
            "that landed after it are unknown"
        )
    landed = set(_git(root, "rev-list", f"{after}..{ref}").split())
    earlier = {e.tag for e in history if e.commit not in landed}
    tags = dict.fromkeys(e.tag for e in history if e.commit in landed)
    return [
        plan_tag(tag, remote_tag_commit(repo, tag), fetch_release(repo, tag), history)
        for tag in tags
        if tag not in earlier
    ]


def _require_digest(repo: str, plan: TagPlan, when: str) -> None:
    release = fetch_release(repo, plan.tag)
    now = release.sha256 if release else None
    if now != plan.sha256:
        moved = f"; {plan.tag} now names {plan.board[:12]}" if when == "after" else ""
        raise ReleaseTagError(
            f"{plan.tag}'s {ASSET_NAME} changed {when} the move "
            f"(planned {plan.sha256[:12]}, now {(now or 'none')[:12]}){moved}. "
            "Plan again."
        )


def checked_move(plan: TagPlan, *, repo: str = DEFAULT_REPO) -> None:
    """Move ``plan``'s tag to its board commit. The release's asset digest is
    read again just before and just after the move: if the asset changed, the
    board may have too, so the move is refused or reported."""
    if plan.action != "move":
        raise ReleaseTagError(f"{plan.tag} has nothing to move ({plan.action})")
    _require_digest(repo, plan, "before")
    move_tag(repo, plan.tag, plan.board)
    _require_digest(repo, plan, "after")


def apply_plans(
    plans: list[TagPlan], *, repo: str = DEFAULT_REPO
) -> tuple[list[str], dict[str, str]]:
    """Move every tag whose plan is ``move``. A failed move does not stop the
    others. Return the tags moved and, for each tag that failed, why."""
    moved, failed = [], {}
    for plan in plans:
        if plan.action != "move":
            continue
        try:
            checked_move(plan, repo=repo)
        except ReleaseTagError as exc:
            failed[plan.tag] = str(exc)
        else:
            moved.append(plan.tag)
    return moved, failed


def promote_live(
    *, repo: str = DEFAULT_REPO, ref: str = DEFAULT_REF, root: str = "."
) -> str:
    """Mark Latest the release the pointer at ``ref`` names, once its asset is
    checked to be the pointer's bytes; return its tag."""
    tag, sha256 = live_pointer(ref, root=root)
    release = fetch_release(repo, tag)
    if release is None or release.sha256 != sha256:
        held = release.sha256[:12] if release and release.sha256 else "none"
        raise ReleaseTagError(
            f"the pointer at {ref} names {tag} with sha256 {sha256[:12]}, but the "
            f"release holds {held}; not marking it Latest"
        )
    make_latest(repo, release)
    return tag


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
    which.add_argument(
        "--landed-after",
        nargs="?",
        const=SEALING_STARTS_AFTER,
        metavar="COMMIT",
        help="Seal every release that --ref first names after COMMIT "
        f"(default {SEALING_STARTS_AFTER[:12]}, the last board before sealing "
        "began)",
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
        help="With --apply, also mark Latest the release the pointer at --ref names",
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
    if args.latest and not args.apply:
        raise SystemExit("--latest needs --apply")
    root = "."
    where = {"repo": args.repo, "ref": args.ref, "root": root}
    try:
        if args.all:
            plans = plan_all(**where)
        elif args.landed_after:
            plans = plan_landed(args.landed_after, **where)
        else:
            tag = live_pointer(args.ref, root=root)[0] if args.live else args.tag
            plans = [plan_one(tag, **where)]
            if plans[0].action == "leave":
                raise ReleaseTagError(f"cannot seal {tag}: {plans[0].reason}")
    except ReleaseTagError as exc:
        raise SystemExit(str(exc)) from exc
    moved, failed = apply_plans(plans, repo=args.repo) if args.apply else ([], {})
    problems = [f"cannot move {tag}: {why}" for tag, why in failed.items()]
    if args.landed_after:
        problems += [
            f"cannot seal {p.tag}: {p.reason}" for p in plans if p.action == "leave"
        ]
    latest = None
    if args.latest:
        try:
            live = live_pointer(args.ref, root=root)[0]
            if live in failed:
                problems.append(f"left Latest alone: {live}'s tag did not move")
            else:
                latest = promote_live(**where)
        except ReleaseTagError as exc:
            problems.append(str(exc))
    if args.json:
        print(json.dumps([_plan_record(plan) for plan in plans], indent=2))
    else:
        for plan in plans:
            print(_plan_line(plan, root))
        count = len(moved) if args.apply else sum(p.action == "move" for p in plans)
        verb = "Moved" if args.apply else "Would move"
        print(f"{verb} {count} tag{'' if count == 1 else 's'}")
        if latest:
            print(f"Marked {latest} Latest")
    if problems:
        raise SystemExit("\n".join(problems))


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
