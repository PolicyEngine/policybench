"""Tests for versioned LiteLLM cache setup and the cache-directory guard."""

import errno
import glob
import os
import stat
import struct
import subprocess
import sys
import threading
from itertools import chain, combinations
from unittest.mock import patch

import diskcache
import litellm
import pytest
from hypothesis import given
from hypothesis import strategies as st

from policybench import cache as cache_module
from policybench.cache import (
    CacheDirError,
    UnsafeCacheDirError,
    cache_problem,
    darwin_acl_problem,
    enable_cache,
    linux_acl_problem,
    mountinfo_filesystem_type,
    nfs4_acl_entries,
    nfs4_acl_problem,
    parent_problem,
    posix_acl_entries,
    process_umask,
    secure_cache_dir,
    umask_problem,
)
from policybench.model_cards import PROMPT_CONTRACT_VERSION

posix_only = pytest.mark.skipif(
    not hasattr(os, "getuid"), reason="needs POSIX owners and permission bits"
)
darwin_only = pytest.mark.skipif(sys.platform != "darwin", reason="macOS ACLs")
linux_only = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux POSIX ACLs"
)
not_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads anything"
)

# What diskcache and SQLite keep in a cache directory: the index, its WAL,
# shared-memory and rollback-journal files, and the two levels of hex
# subdirectories holding .val files for values of 32 KB or more.
CACHE_FILES = (
    "cache.db",
    "cache.db-wal",
    "cache.db-shm",
    "cache.db-journal",
    "ab/cd/0123456789abcdef0123456789ab.val",
)
CACHE_SUBDIRS = ("ab", "ab/cd")
VALUE_FILE = CACHE_FILES[-1]


def mode_of(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def other_uid() -> int:
    return os.getuid() + 1


def make_cache(tmp_path, dir_mode=0o700):
    """A cache directory holding every kind of entry diskcache makes."""
    cache_dir = tmp_path / "cache"
    (cache_dir / "ab" / "cd").mkdir(parents=True)
    for name in CACHE_FILES:
        (cache_dir / name).write_bytes(b"")
        (cache_dir / name).chmod(0o644)
    for name in CACHE_SUBDIRS:
        (cache_dir / name).chmod(0o755)
    cache_dir.chmod(dir_mode)
    return cache_dir


def _with_uid(result: os.stat_result, uid: int) -> os.stat_result:
    fields = list(result[:10])
    fields[4] = uid  # st_uid
    return os.stat_result(fields)


def fake_owner(monkeypatch, path, uid: int) -> None:
    """Make every stat of ``path``'s inode report it as owned by ``uid``.

    Keyed by inode rather than path, so it holds for descriptors and for the
    directory after a rename.
    """
    target = os.lstat(path)
    inode = (target.st_dev, target.st_ino)
    for name in ("stat", "lstat", "fstat"):
        real = getattr(os, name)

        def fake(*args, _real=real, **kwargs):
            result = _real(*args, **kwargs)
            if (result.st_dev, result.st_ino) == inode:
                return _with_uid(result, uid)
            return result

        monkeypatch.setattr(os, name, fake)


def pretend_root(monkeypatch) -> None:
    """Run as if the current user were root and owned what they own."""
    me = os.getuid()
    for name in ("stat", "lstat", "fstat"):
        real = getattr(os, name)

        def fake(*args, _real=real, **kwargs):
            result = _real(*args, **kwargs)
            return _with_uid(result, 0) if result.st_uid == me else result

        monkeypatch.setattr(os, name, fake)
    monkeypatch.setattr(os, "getuid", lambda: 0)


def private_group(monkeypatch, gid: int | None) -> None:
    """Make ``gid`` the current user's private group (None: they have none)."""
    me = os.getuid()
    monkeypatch.setattr(
        cache_module, "user_private_gid", lambda uid: gid if uid == me else None
    )


def new_entry_group(directory) -> int:
    """The group a new entry in ``directory`` gets, found by making one."""
    probe = directory / ".group-probe"
    probe.write_bytes(b"")
    try:
        return os.stat(probe).st_gid
    finally:
        probe.unlink()


@pytest.fixture(autouse=True)
def safe_umask():
    """Run every test under umask 022 unless it sets its own."""
    previous = os.umask(0o022)
    yield
    os.umask(previous)


@pytest.fixture
def umask():
    """Set the process umask for a test (safe_umask restores it)."""
    return os.umask


def test_enable_cache_namespaces_entries_by_bumped_contract_version(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(litellm, "cache", None)
    fake_cache = object()
    cache_dir = tmp_path / "policybench-cache"

    with patch("policybench.cache.Cache", return_value=fake_cache) as cache_class:
        enable_cache(str(cache_dir))

    assert PROMPT_CONTRACT_VERSION == "2026-08-09-v2-scoring-contract"
    cache_class.assert_called_once_with(
        type="disk",
        disk_cache_dir=os.path.realpath(cache_dir),
        namespace=f"policybench:{PROMPT_CONTRACT_VERSION}",
    )
    assert litellm.cache is fake_cache


def test_enable_cache_round_trips_through_real_disk_cache(monkeypatch, tmp_path):
    """The guard accepts what LiteLLM's real diskcache backend creates.

    The response is past diskcache's 32 KB inline limit, so it lands in a .val
    file under two hex subdirectories, which the second check walks.
    """
    monkeypatch.setattr(litellm, "cache", None)
    cache_dir = tmp_path / "cache"
    response = {"response": "x" * 40_000}

    enable_cache(str(cache_dir))
    litellm.cache.cache.set_cache("key", response)

    assert litellm.cache.cache.get_cache("key") == response
    assert (cache_dir / "cache.db").exists()
    assert len(glob.glob(str(cache_dir / "*" / "*" / "*.val"))) == 1
    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)


# The umask. diskcache adds value directories and files after the guard has
# run, so the guard refuses a umask under which another account could write
# them.


@posix_only
def test_diskcache_makes_value_files_under_the_process_umask(tmp_path, umask):
    """Why the umask matters: under umask 000 a value file is world-writable."""
    umask(0o000)
    with diskcache.Cache(str(tmp_path / "cache")) as cache:
        cache.set("key", {"response": "x" * 40_000})

    (value_file,) = glob.glob(str(tmp_path / "cache" / "*" / "*" / "*.val"))
    assert mode_of(value_file) == 0o666
    assert mode_of(os.path.dirname(value_file)) == 0o777


@posix_only
def test_existing_cache_is_refused_under_umask_000_before_diskcache_opens_it(
    monkeypatch, tmp_path, umask
):
    """Every existing entry is safe, but the next .val file would not be."""
    monkeypatch.setattr(litellm, "cache", None)
    cache_dir = make_cache(tmp_path, dir_mode=0o755)
    umask(0o000)

    with patch("policybench.cache.Cache") as cache_class:
        with pytest.raises(
            UnsafeCacheDirError,
            match="the files diskcache adds to it would be writable by every "
            "account under your umask 000",
        ):
            enable_cache(str(cache_dir))

    cache_class.assert_not_called()
    assert litellm.cache is None


@posix_only
@pytest.mark.parametrize(
    ("process_umask", "group_is_private", "refusal"),
    [
        (0o000, True, "every account under your umask 000"),
        (0o000, False, "every account under your umask 000"),
        (0o002, False, r"gid \d+\)? under your umask 002"),
        (0o002, True, None),
        (0o020, False, "every account under your umask 020"),
        (0o022, False, None),
        (0o077, False, None),
    ],
)
def test_umask_is_refused_when_new_cache_files_would_be_writable_by_others(
    monkeypatch, tmp_path, umask, process_umask, group_is_private, refusal
):
    cache_dir = make_cache(tmp_path)
    private_group(monkeypatch, new_entry_group(cache_dir) if group_is_private else None)
    umask(process_umask)

    if refusal is None:
        assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)
    else:
        with pytest.raises(UnsafeCacheDirError, match=refusal):
            secure_cache_dir(str(cache_dir))


@posix_only
def test_value_subdirectory_giving_new_files_a_shared_group_is_refused(
    monkeypatch, tmp_path, umask
):
    """Under umask 002, every directory's new entries must get a private group."""
    cache_dir = make_cache(tmp_path)
    mine = new_entry_group(cache_dir)
    private_group(monkeypatch, mine)
    umask(0o002)
    real_fstat = os.fstat
    subdir = os.lstat(cache_dir / "ab" / "cd")

    def fstat(fd):
        result = real_fstat(fd)
        if (result.st_dev, result.st_ino) == (subdir.st_dev, subdir.st_ino):
            # A setgid subdirectory of a shared group, as `cp -a` from a
            # shared project directory could leave.
            fields = list(result[:10])
            fields[0] |= stat.S_ISGID
            fields[5] = mine + 1  # st_gid
            return os.stat_result(fields)
        return result

    monkeypatch.setattr(os, "fstat", fstat)

    with pytest.raises(UnsafeCacheDirError) as refused:
        secure_cache_dir(str(cache_dir))

    message = str(refused.value)
    assert "the files diskcache adds to its ab/cd would be writable by " in message
    assert f"gid {mine + 1}" in message
    assert "under your umask 002" in message


@posix_only
def test_cache_used_under_a_private_group_umask_stays_acceptable(
    monkeypatch, tmp_path, umask
):
    """Ubuntu's umask 002 with user-private groups: group-writable, but only
    by the user."""
    monkeypatch.setattr(litellm, "cache", None)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(mode=0o700)
    private_group(monkeypatch, new_entry_group(cache_dir))
    umask(0o002)

    enable_cache(str(cache_dir))
    litellm.cache.cache.set_cache("key", {"response": "x" * 40_000})

    (value_file,) = glob.glob(str(cache_dir / "*" / "*" / "*.val"))
    assert mode_of(value_file) == 0o664
    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)


@posix_only
@pytest.mark.parametrize("process_umask", [0o000, 0o002, 0o022, 0o077])
def test_missing_directory_and_parents_are_created_owner_only(
    monkeypatch, tmp_path, umask, process_umask
):
    private_group(monkeypatch, new_entry_group(tmp_path))
    umask(process_umask)
    cache_dir = tmp_path / "new" / "nested" / "cache"

    if process_umask & 0o002:
        assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)
    else:
        with pytest.raises(UnsafeCacheDirError, match="under your umask 000"):
            secure_cache_dir(str(cache_dir))

    for created in (tmp_path / "new", tmp_path / "new" / "nested", cache_dir):
        assert mode_of(created) == 0o700


# Ownership and mode bits of the cache and everything in it.


@posix_only
def test_existing_0o755_cache_is_accepted_and_left_alone(tmp_path):
    cache_dir = make_cache(tmp_path, dir_mode=0o755)

    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)
    assert mode_of(cache_dir) == 0o755


def _group_writable_cache(tmp_path, dir_mode):
    cache_dir = make_cache(tmp_path, dir_mode=dir_mode)
    for name in CACHE_FILES:
        (cache_dir / name).chmod(0o664)
    for name in CACHE_SUBDIRS:
        (cache_dir / name).chmod(0o775)
    return cache_dir


@posix_only
@pytest.mark.parametrize("dir_mode", [0o770, 0o775, 0o2775])
def test_group_writable_cache_and_entries_are_accepted_for_a_private_group(
    monkeypatch, tmp_path, dir_mode
):
    """What Ubuntu's umask 002 with user-private groups makes by default."""
    cache_dir = _group_writable_cache(tmp_path, dir_mode)
    private_group(monkeypatch, os.stat(cache_dir).st_gid)

    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)


@posix_only
@pytest.mark.parametrize("dir_mode", [0o770, 0o775, 0o2775])
def test_group_writable_cache_is_refused_for_a_shared_group(
    monkeypatch, tmp_path, dir_mode
):
    """macOS's staff, say: every other local account is in it."""
    cache_dir = _group_writable_cache(tmp_path, dir_mode)
    private_group(monkeypatch, None)

    with pytest.raises(UnsafeCacheDirError) as refused:
        secure_cache_dir(str(cache_dir))

    message = str(refused.value)
    assert "it is writable by " in message
    assert f"gid {os.stat(cache_dir).st_gid}" in message
    # Not dir_mode: chmod drops setgid for a group the user isn't in.
    assert f"(mode {mode_of(cache_dir):#o})" in message


@posix_only
def test_directory_owned_by_another_user_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(litellm, "cache", None)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(mode=0o700)
    fake_owner(monkeypatch, cache_dir, other_uid())

    with patch("policybench.cache.Cache") as cache_class:
        with pytest.raises(UnsafeCacheDirError) as refused:
            enable_cache(str(cache_dir))

    message = str(refused.value)
    assert f"Refusing to use {os.path.realpath(cache_dir)} " in message
    assert f"it is owned by uid {other_uid()}" in message
    assert "GHSA-w8v5-vhqr-4h9v" in message
    assert "delete it (it is only a cache)" in message
    cache_class.assert_not_called()
    assert litellm.cache is None


@posix_only
def test_foreign_directory_is_refused_when_only_getuid_differs(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(mode=0o700)
    owner = os.stat(cache_dir).st_uid
    monkeypatch.setattr(os, "getuid", lambda: owner + 1)

    # Checked from the root down, the first of the user's directories on the
    # way is refused.
    with pytest.raises(
        UnsafeCacheDirError,
        match=rf"is owned by uid {owner}, not the current user \(uid {owner + 1}\)",
    ):
        secure_cache_dir(str(cache_dir))


@posix_only
@pytest.mark.parametrize("name", CACHE_FILES + CACHE_SUBDIRS)
def test_entry_owned_by_another_user_is_refused(monkeypatch, tmp_path, name):
    cache_dir = make_cache(tmp_path)
    fake_owner(monkeypatch, cache_dir / name, other_uid())

    with pytest.raises(UnsafeCacheDirError, match=f"its {name} is owned by uid"):
        secure_cache_dir(str(cache_dir))


@posix_only
@pytest.mark.parametrize("dir_mode", [0o777, 0o703, 0o1777])
def test_world_writable_directory_is_refused(tmp_path, dir_mode):
    """Even with the sticky bit, others could plant cache.db or value files."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_dir.chmod(dir_mode)

    with pytest.raises(
        UnsafeCacheDirError, match=rf"it is world-writable \(mode {dir_mode:#o}\)"
    ):
        secure_cache_dir(str(cache_dir))


@posix_only
@pytest.mark.parametrize("name", CACHE_FILES)
def test_world_writable_file_in_the_cache_is_refused(tmp_path, name):
    cache_dir = make_cache(tmp_path)
    (cache_dir / name).chmod(0o666)

    with pytest.raises(UnsafeCacheDirError, match=f"its {name} is world-writable"):
        secure_cache_dir(str(cache_dir))


@posix_only
@pytest.mark.parametrize("name", CACHE_SUBDIRS)
def test_leftover_world_writable_value_subdirectory_is_refused(tmp_path, name):
    """Fixing the top directory's mode doesn't fix what is under it."""
    cache_dir = make_cache(tmp_path, dir_mode=0o755)
    (cache_dir / name).chmod(0o777)

    with pytest.raises(UnsafeCacheDirError, match=f"its {name} is world-writable"):
        secure_cache_dir(str(cache_dir))


@posix_only
def test_symlink_inside_the_cache_is_refused(tmp_path):
    """diskcache never makes one, and SQLite would follow it."""
    cache_dir = make_cache(tmp_path)
    elsewhere = tmp_path / "elsewhere.db"
    elsewhere.write_bytes(b"")
    (cache_dir / "cache.db").unlink()
    (cache_dir / "cache.db").symlink_to(elsewhere)

    with pytest.raises(UnsafeCacheDirError, match="its cache.db is a symlink"):
        secure_cache_dir(str(cache_dir))


@posix_only
def test_fifo_inside_the_cache_is_refused_without_opening_it(tmp_path):
    """Opening a FIFO for reading would wait for a writer."""
    cache_dir = make_cache(tmp_path)
    os.mkfifo(cache_dir / "ab" / "pipe")

    with pytest.raises(
        UnsafeCacheDirError, match="its ab/pipe is not a file or a directory"
    ):
        secure_cache_dir(str(cache_dir))


@posix_only
@pytest.mark.parametrize("name", [VALUE_FILE, "ab/cd"])
@pytest.mark.parametrize("call", ["stat", "open"])
def test_entry_deleted_by_a_concurrent_run_is_skipped(
    monkeypatch, tmp_path, name, call
):
    """diskcache culls value files past its size limit while others run."""
    cache_dir = make_cache(tmp_path)
    doomed = cache_dir / name
    target = os.path.basename(name)
    real = getattr(os, call)

    def delete_first(path, *args, dir_fd=None, **kwargs):
        if dir_fd is not None and path == target and os.path.lexists(doomed):
            if os.path.isdir(doomed):
                for child in os.listdir(doomed):
                    os.unlink(doomed / child)
                os.rmdir(doomed)
            else:
                os.unlink(doomed)
        return real(path, *args, dir_fd=dir_fd, **kwargs)

    monkeypatch.setattr(os, call, delete_first)

    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)
    assert not os.path.lexists(doomed)


@posix_only
def test_file_replaced_by_a_directory_while_checked_is_refused(monkeypatch, tmp_path):
    """The opened entry is judged, and must be what the listing said.

    Otherwise a directory swapped in for cache.db between its stat and its
    open would be judged as a file, and its contents never walked.
    """
    cache_dir = make_cache(tmp_path)
    db = cache_dir / "cache.db"
    real_open = os.open

    def swap_then_open(path, *args, dir_fd=None, **kwargs):
        if dir_fd is not None and path == "cache.db" and not os.path.isdir(db):
            os.unlink(db)
            os.mkdir(db, 0o700)
            (db / "planted.val").write_bytes(b"")
            os.chmod(db / "planted.val", 0o666)
        return real_open(path, *args, dir_fd=dir_fd, **kwargs)

    monkeypatch.setattr(os, "open", swap_then_open)

    with pytest.raises(CacheDirError, match="it changed while it was being checked"):
        secure_cache_dir(str(cache_dir))


@posix_only
@not_root
def test_unreadable_subdirectory_is_a_clean_error(tmp_path):
    cache_dir = make_cache(tmp_path)
    (cache_dir / "ab").chmod(0o000)
    try:
        with pytest.raises(CacheDirError, match="Can't check .*ab in the LiteLLM"):
            secure_cache_dir(str(cache_dir))
    finally:
        (cache_dir / "ab").chmod(0o755)


@posix_only
@not_root
def test_listable_but_unsearchable_cache_is_a_clean_error(tmp_path):
    """Read without search permission lists names but can't stat them."""
    cache_dir = make_cache(tmp_path)
    cache_dir.chmod(0o400)
    try:
        with pytest.raises(
            CacheDirError,
            match="Can't check .*cache/ab in the LiteLLM disk cache: Permission",
        ):
            secure_cache_dir(str(cache_dir))
    finally:
        cache_dir.chmod(0o700)


# Parents. Anyone who can rename an entry in a parent could swap the cache
# out after the check, so each parent is checked, from the root down.


@posix_only
def test_new_directory_inside_a_foreign_parent_is_refused(monkeypatch, tmp_path):
    """The shared-/tmp case: another account pre-created a parent of the path.

    The new cache directory itself is ours, but the parent's owner could rename
    it and put their own in its place after the check.
    """
    shared = tmp_path / "shared"
    shared.mkdir()
    fake_owner(monkeypatch, shared, other_uid())

    with pytest.raises(
        UnsafeCacheDirError,
        match=f"its parent directory {os.path.realpath(shared)} is owned by uid",
    ):
        secure_cache_dir(str(shared / "cache"))


@posix_only
@pytest.mark.parametrize("as_root", [False, True])
def test_root_owned_parent_is_accepted_unless_a_shared_group_can_write(
    monkeypatch, tmp_path, as_root
):
    """A root-owned directory's group is a shared one (wheel, or a team's),
    whose members could swap the cache out unless the sticky bit stops them,
    and that holds when the cache is root's too (review r2's 02775 case)."""
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o755)
    if as_root:
        pretend_root(monkeypatch)
    else:
        fake_owner(monkeypatch, shared, 0)
    monkeypatch.setattr(cache_module, "user_private_gid", lambda uid: None)
    cache_dir = shared / "cache"

    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)

    for mode in (0o775, 0o2775):
        shared.chmod(mode)
        with pytest.raises(
            UnsafeCacheDirError,
            match=rf"its parent directory .*shared is writable by .* without the "
            rf"sticky bit \(mode {mode_of(shared):#o}\)",
        ):
            secure_cache_dir(str(cache_dir))
    shared.chmod(0o1775)
    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)


@posix_only
def test_own_group_writable_parent_is_accepted_for_a_private_group(
    monkeypatch, tmp_path
):
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o775)
    private_group(monkeypatch, os.stat(shared).st_gid)

    assert secure_cache_dir(str(shared / "cache")) == os.path.realpath(shared / "cache")

    private_group(monkeypatch, None)
    with pytest.raises(
        UnsafeCacheDirError, match="is writable by .* without the sticky bit"
    ):
        secure_cache_dir(str(shared / "cache"))


@posix_only
def test_world_writable_parent_needs_the_sticky_bit(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)

    with pytest.raises(
        UnsafeCacheDirError, match="is world-writable without the sticky bit"
    ):
        secure_cache_dir(str(shared / "cache"))

    # Like /tmp: only an entry's owner can rename it, so this is safe.
    shared.chmod(0o1777)
    assert secure_cache_dir(str(shared / "cache")) == os.path.realpath(shared / "cache")


@posix_only
@not_root
def test_parent_the_user_can_search_but_not_list_is_checked(tmp_path):
    """Opened for search only (O_SEARCH, or O_PATH on Linux), the way a home
    directory at 0o711 is passed through."""
    parent = tmp_path / "search-only"
    parent.mkdir()
    cache_dir = parent / "cache"
    parent.chmod(0o311)
    try:
        with pytest.raises(PermissionError):
            os.listdir(parent)
        assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)
        assert mode_of(cache_dir) == 0o700
    finally:
        parent.chmod(0o755)


def _interleave(build, action, guard):
    """Run ``guard`` on a fresh tree once for each file-system call it makes,
    doing ``action`` just before that call.

    Returns what each run returned or raised, in call order, and what a run
    without the action did. ``build`` makes the tree under a MonkeyPatch that
    is undone after the run.
    """
    outcomes = []
    while True:
        point = len(outcomes)
        with pytest.MonkeyPatch.context() as monkeypatch:
            tree = build(monkeypatch, point)
            state = {"calls": 0, "acted": False}
            for name in ("open", "stat", "lstat", "fstat", "scandir"):
                real = getattr(os, name)

                def counted(*args, _real=real, **kwargs):
                    if state["calls"] == point and not state["acted"]:
                        state["acted"] = True
                        action(tree)
                    state["calls"] += 1
                    return _real(*args, **kwargs)

                monkeypatch.setattr(os, name, counted)
            try:
                outcome = guard(tree)
            except CacheDirError as error:
                outcome = error
        if not state["acted"]:
            return outcomes, outcome
        outcomes.append(outcome)


@posix_only
def test_a_parent_swapped_mid_check_is_never_accepted(tmp_path):
    """Review r2's swap, done before each of the guard's calls in turn.

    Bob owns the world-writable ``shared``. In it are Alice's cache and her
    ``staging`` directory, which holds Bob's world-writable ``cache``. Bob
    renames ``shared`` away and puts ``staging`` in its place (his to do, as
    the owner of ``shared`` and of its entry in a sticky directory), so the
    path leads through a safe parent to his cache. Checking parents by path
    after reading the cache accepted that; opening each directory through its
    checked parent sees one tree or the other, and both are refused.
    """

    def build(monkeypatch, point):
        root = tmp_path / f"case-{point}"
        root.mkdir()
        root.chmod(0o1777)
        shared = root / "shared"
        (shared / "cache").mkdir(parents=True)
        (shared / "cache").chmod(0o700)
        (shared / "staging" / "cache").mkdir(parents=True)
        (shared / "staging").chmod(0o755)
        (shared / "staging" / "cache").chmod(0o777)
        shared.chmod(0o777)
        fake_owner(monkeypatch, shared, other_uid())
        fake_owner(monkeypatch, shared / "staging" / "cache", other_uid())
        return root

    def swap(root):
        os.rename(root / "shared", root / "shared-old")
        os.rename(root / "shared-old" / "staging", root / "shared")

    outcomes, unswapped = _interleave(
        build, swap, lambda root: secure_cache_dir(str(root / "shared" / "cache"))
    )

    assert len(outcomes) > 10
    accepted = [
        point
        for point, outcome in enumerate(outcomes)
        if not isinstance(outcome, UnsafeCacheDirError)
    ]
    assert accepted == []
    assert isinstance(unswapped, UnsafeCacheDirError)


@posix_only
def test_a_cache_replaced_after_its_check_is_never_accepted(tmp_path):
    """The user's own concurrent change, which only the final comparison of
    the path with the checked directory catches once the checks are done."""

    def build(monkeypatch, point):
        root = tmp_path / f"case-{point}"
        make_cache(root)
        return root

    def replace(root):
        os.rename(root / "cache", root / "cache-old")
        os.mkdir(root / "cache")
        os.chmod(root / "cache", 0o777)

    outcomes, unreplaced = _interleave(
        build, replace, lambda root: secure_cache_dir(str(root / "cache"))
    )

    assert len(outcomes) > 10
    accepted = [
        point
        for point, outcome in enumerate(outcomes)
        if not isinstance(outcome, CacheDirError)
    ]
    assert accepted == []
    assert unreplaced == os.path.realpath(tmp_path / f"case-{len(outcomes)}" / "cache")


@posix_only
def test_symlink_is_resolved_and_the_target_is_checked(monkeypatch, tmp_path):
    monkeypatch.setattr(litellm, "cache", None)
    target = tmp_path / "real-cache"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target)

    with patch("policybench.cache.Cache") as cache_class:
        enable_cache(str(link))

    # The resolved path goes to diskcache, so re-pointing the link later
    # cannot redirect the cache.
    assert cache_class.call_args.kwargs["disk_cache_dir"] == os.path.realpath(target)

    fake_owner(monkeypatch, target, other_uid())
    with pytest.raises(UnsafeCacheDirError, match="it is owned by uid"):
        secure_cache_dir(str(link))


@posix_only
def test_home_and_variables_are_expanded_like_diskcache(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("POLICYBENCH_TEST_CACHE_ROOT", str(tmp_path / "root"))

    assert secure_cache_dir("~/cache") == os.path.realpath(tmp_path / "cache")
    assert secure_cache_dir("$POLICYBENCH_TEST_CACHE_ROOT/cache") == (
        os.path.realpath(tmp_path / "root" / "cache")
    )


def test_path_diskcache_would_expand_again_is_refused_before_creating_it(
    monkeypatch, tmp_path
):
    """diskcache runs expandvars on the path it gets; it must not move it."""
    monkeypatch.setenv("POLICYBENCH_TEST_OUTER", "$POLICYBENCH_TEST_INNER")
    monkeypatch.setenv("POLICYBENCH_TEST_INNER", "elsewhere")

    with pytest.raises(CacheDirError, match=r"would expand the \$ in it") as refused:
        secure_cache_dir(str(tmp_path / "$POLICYBENCH_TEST_OUTER"))

    assert not isinstance(refused.value, UnsafeCacheDirError)
    assert str(tmp_path / "elsewhere") in str(refused.value)
    assert os.listdir(tmp_path) == []


def test_file_in_place_of_the_directory_is_a_plain_error(tmp_path):
    cache_file = tmp_path / "cache"
    cache_file.write_text("not a directory")

    with pytest.raises(CacheDirError, match="it is not a directory") as refused:
        secure_cache_dir(str(cache_file))

    assert not isinstance(refused.value, UnsafeCacheDirError)
    assert "GHSA" not in str(refused.value)


@posix_only
@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root writes anywhere"
)
def test_parent_that_cannot_be_written_is_a_clean_error(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        with pytest.raises(
            CacheDirError, match="Can't create the LiteLLM disk cache directory"
        ):
            secure_cache_dir(str(locked / "cache"))
    finally:
        locked.chmod(0o700)


def test_empty_cache_directory_is_rejected(monkeypatch):
    monkeypatch.setattr("policybench.cache.CACHE_DIR", "")

    with pytest.raises(CacheDirError, match="empty string"):
        enable_cache()


@posix_only
def test_ownership_and_mode_checks_are_skipped_without_getuid(monkeypatch, tmp_path):
    """Windows: no POSIX owners, and os.stat reports writable dirs as 0o777."""
    cache_dir = make_cache(tmp_path, dir_mode=0o777)
    (cache_dir / "cache.db").chmod(0o666)
    monkeypatch.delattr(os, "getuid")

    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)


@posix_only
@pytest.mark.parametrize(
    ("cache_dir_mode", "message"),
    [
        (0o777, "Refusing to use .* world-writable"),
        (None, "empty string"),
    ],
)
def test_cli_exits_with_the_error_before_any_model_call(
    monkeypatch, tmp_path, cache_dir_mode, message
):
    from policybench.cli import main

    if cache_dir_mode is None:
        monkeypatch.setattr("policybench.cache.CACHE_DIR", "")
    else:
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cache_dir.chmod(cache_dir_mode)
        monkeypatch.setattr("policybench.cache.CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(
        "sys.argv",
        [
            "policybench",
            "eval-no-tools",
            "--num-scenarios",
            "1",
            "--model",
            "gpt-5.6-sol",
            "--program",
            "snap",
            "--output",
            str(tmp_path / "predictions.csv"),
        ],
    )

    with patch("policybench.cli._load_eval_scenarios") as load_scenarios:
        with pytest.raises(SystemExit, match=message):
            main()

    load_scenarios.assert_not_called()


# ACLs, which grant access the mode bits don't show (`ls -l` marks them +).


def chmod_acl(path, entry: str) -> None:
    subprocess.run(["/bin/chmod", "+a", entry, str(path)], check=True)


@darwin_only
@pytest.mark.parametrize(
    ("name", "entry", "granted"),
    [
        ("cache.db", "user:nobody allow write", "user nobody write"),
        (VALUE_FILE, "user:nobody allow append", "user nobody append"),
        (VALUE_FILE, "group:everyone allow writesecurity", "group everyone"),
        ("ab/cd", "user:nobody allow add_file", "user nobody write"),
        ("ab", "group:everyone allow delete_child", "group everyone delete_child"),
    ],
)
def test_macos_acl_write_grant_in_the_cache_is_refused(tmp_path, name, entry, granted):
    """Review r2's case: the mode stays 0o644 while the ACL lets nobody write."""
    cache_dir = make_cache(tmp_path)
    chmod_acl(cache_dir / name, entry)

    with pytest.raises(
        UnsafeCacheDirError, match=f"its {name} has an ACL entry letting {granted}"
    ):
        secure_cache_dir(str(cache_dir))


@darwin_only
def test_macos_deny_and_own_acl_entries_are_accepted(tmp_path):
    """Like the deny-delete entry macOS puts on every home directory."""
    import pwd

    cache_dir = make_cache(tmp_path)
    user = pwd.getpwuid(os.getuid()).pw_name
    try:
        for target in (cache_dir, cache_dir / "ab", cache_dir / "cache.db"):
            chmod_acl(target, "group:everyone deny delete")
            chmod_acl(target, f"user:{user} allow write,delete,writesecurity")
            chmod_acl(target, "user:nobody allow read,readattr,readsecurity")

        assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)
    finally:
        # The deny entries would stop pytest removing the directory.
        subprocess.run(["/bin/chmod", "-R", "-N", str(cache_dir)], check=True)


@darwin_only
def test_macos_acl_inherited_by_new_cache_entries_is_refused(tmp_path):
    cache_dir = make_cache(tmp_path)
    chmod_acl(cache_dir / "ab", "user:nobody allow write,file_inherit,only_inherit")

    with pytest.raises(
        UnsafeCacheDirError,
        match="its ab has an ACL entry inherited by new entries letting user "
        "nobody write",
    ):
        secure_cache_dir(str(cache_dir))


@darwin_only
def test_macos_parent_acls(tmp_path):
    """An inheritable grant on a parent spares the parent and existing caches,
    but reaches a cache made under it; a grant on the parent itself doesn't."""
    parent = tmp_path / "parent"
    existing = make_cache(parent)
    chmod_acl(
        parent,
        "user:nobody allow add_file,add_subdirectory,file_inherit,"
        "directory_inherit,only_inherit",
    )

    assert secure_cache_dir(str(existing)) == os.path.realpath(existing)
    with pytest.raises(
        UnsafeCacheDirError,
        match=r"its parent directory .*parent/new has an ACL entry letting user "
        "nobody write,append",
    ):
        secure_cache_dir(str(parent / "new" / "cache"))

    chmod_acl(parent, "user:nobody allow delete_child")
    with pytest.raises(
        UnsafeCacheDirError,
        match=r"its parent directory .*parent has an ACL entry letting user "
        "nobody delete_child",
    ):
        secure_cache_dir(str(existing))


@darwin_only
@not_root
def test_macos_acl_on_a_search_only_parent_is_read(tmp_path):
    parent = tmp_path / "search-only"
    parent.mkdir()
    chmod_acl(parent, "user:nobody allow add_file")
    parent.chmod(0o311)
    try:
        with pytest.raises(
            UnsafeCacheDirError, match="has an ACL entry letting user nobody write"
        ):
            secure_cache_dir(str(parent / "cache"))
    finally:
        parent.chmod(0o755)


ACL_UNDEFINED_ID = 0xFFFFFFFF
USER_OBJ, USER, GROUP_OBJ, GROUP, MASK, OTHER = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20


def acl_blob(entries) -> bytes:
    return struct.pack("<I", 2) + b"".join(
        struct.pack("<HHI", tag, perm, qualifier) for tag, perm, qualifier in entries
    )


def set_linux_acl(path, kind: str, entries) -> None:
    try:
        os.setxattr(path, f"system.posix_acl_{kind}", acl_blob(entries))
    except OSError as error:
        # GitHub's Ubuntu runners take ACLs, and CI's -q output wouldn't show
        # a skip, so only skip elsewhere.
        if os.environ.get("GITHUB_ACTIONS"):
            raise
        pytest.skip(f"this filesystem won't take a POSIX ACL: {error}")


def acl_granting(uid: int, perm: int, mask: int, owner: int = 0o6):
    """An access ACL letting ``uid`` ``perm``, limited by ``mask``."""
    return [
        (USER_OBJ, owner, ACL_UNDEFINED_ID),
        (USER, perm, uid),
        (GROUP_OBJ, 0o4, ACL_UNDEFINED_ID),
        (MASK, mask, ACL_UNDEFINED_ID),
        (OTHER, 0o4, ACL_UNDEFINED_ID),
    ]


@linux_only
def test_linux_acl_write_grant_in_the_cache_is_refused(monkeypatch, tmp_path):
    """The mask shows as the group bits, so with a private group the mode
    check passes the file; the ACL check catches the named entry."""
    cache_dir = make_cache(tmp_path)
    private_group(monkeypatch, os.stat(cache_dir / VALUE_FILE).st_gid)
    set_linux_acl(cache_dir / VALUE_FILE, "access", acl_granting(other_uid(), 6, 6))

    with pytest.raises(
        UnsafeCacheDirError,
        match=f"its {VALUE_FILE} has an ACL entry letting uid {other_uid()} write",
    ):
        secure_cache_dir(str(cache_dir))

    set_linux_acl(cache_dir / VALUE_FILE, "access", acl_granting(other_uid(), 6, 4))
    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)


@linux_only
def test_linux_default_acl_on_the_cache_is_refused(tmp_path):
    cache_dir = make_cache(tmp_path)
    set_linux_acl(
        cache_dir / "ab",
        "default",
        [
            (USER_OBJ, 0o7, ACL_UNDEFINED_ID),
            (GROUP_OBJ, 0o5, ACL_UNDEFINED_ID),
            (OTHER, 0o7, ACL_UNDEFINED_ID),
        ],
    )

    with pytest.raises(
        UnsafeCacheDirError,
        match="its ab has a default ACL letting every account write new entries",
    ):
        secure_cache_dir(str(cache_dir))


@linux_only
@not_root
def test_linux_acl_on_a_search_only_parent_is_read(monkeypatch, tmp_path):
    """Read through /proc/self/fd, since an O_PATH descriptor can't be."""
    parent = tmp_path / "search-only"
    parent.mkdir()
    private_group(monkeypatch, os.stat(parent).st_gid)
    set_linux_acl(parent, "access", acl_granting(other_uid(), 7, 7, owner=0o7))
    parent.chmod(0o331)  # the mask is the group bits, and keeps write
    try:
        with pytest.raises(
            UnsafeCacheDirError,
            match=f"has an ACL entry letting uid {other_uid()} write",
        ):
            secure_cache_dir(str(parent / "cache"))
    finally:
        parent.chmod(0o755)


DARWIN_ACLS = {
    # What acl_to_text gives for macOS's home-directory entry and for entries
    # set with chmod +a.
    "group:ABCDEFAB-CDEF-ABCD-EFAB-CDEF0000000C:everyone:12:deny:delete": None,
    "user:FFFFEEEE-DDDD-CCCC-BBBB-AAAAFFFFFFFE:nobody:-2:allow:write,append": (
        "has an ACL entry letting user nobody write,append"
    ),
    "group:ABCDEFAB-CDEF-ABCD-EFAB-CDEF00000014:staff:20:"
    "allow,file_inherit,only_inherit:execute": None,
    "user:FFFFEEEE-DDDD-CCCC-BBBB-AAAAFFFFFFFE:nobody:-2:"
    "allow,inherited,file_inherit,directory_inherit:write,delete_child": (
        "has an ACL entry letting user nobody write,delete_child"
    ),
    "user:4CD5CFEB-EF5F-4F47-B0F3-0E0040999E3D:alice:1000:allow:write": None,
    "user:FFFFEEEE-DDDD-CCCC-BBBB-AAAAFFFFFFF0:root:0:allow:chown": None,
    # An unknown right counts as a write; an entry whose holder macOS can't
    # name is someone else's.
    "user:AAAAAAAA-0000-0000-0000-000000000000:::allow:read,frobnicate": (
        "has an ACL entry letting user AAAAAAAA-0000-0000-0000-000000000000 frobnicate"
    ),
    "user:nobody:allow:write": "has an ACL entry PolicyBench can't read",
}


@pytest.mark.parametrize(("line", "expected"), DARWIN_ACLS.items())
def test_darwin_acl_text(line, expected):
    problem = darwin_acl_problem(f"!#acl 1\n{line}\n", 1000, inherited_too=False)
    if expected is None:
        assert problem is None
    else:
        assert problem.startswith(expected)


def test_darwin_only_inherit_entries_count_for_new_entries_only():
    text = "!#acl 1\nuser:U:nobody:-2:allow,file_inherit,only_inherit:write\n"
    assert darwin_acl_problem(text, 1000, inherited_too=False) is None
    assert darwin_acl_problem(text, 1000, inherited_too=True) == (
        "has an ACL entry inherited by new entries letting user nobody write"
    )


WRITE_RIGHTS = ("write", "append", "delete", "delete_child", "writesecurity", "chown")
HARMLESS_RIGHTS = ("read", "execute", "readattr", "writeattr", "readsecurity")
INHERIT_FLAGS = (
    "file_inherit",
    "directory_inherit",
    "limit_inherit",
    "only_inherit",
    "inherited",
)
ME_ON_A_MAC = 501

darwin_entries = st.tuples(
    st.sampled_from(["user", "group"]),
    st.sampled_from([ME_ON_A_MAC, 0, -2, 20]),
    st.sampled_from(["allow", "deny"]),
    st.lists(st.sampled_from(INHERIT_FLAGS), unique=True, max_size=3),
    st.lists(st.sampled_from(WRITE_RIGHTS + HARMLESS_RIGHTS), unique=True, min_size=1),
)


def darwin_text(entries) -> str:
    lines = [
        f"{tag}:UUID-{qualifier}:name{qualifier}:{qualifier}:"
        f"{','.join([kind, *flags])}:{','.join(rights)}\n"
        for tag, qualifier, kind, flags, rights in entries
    ]
    return "!#acl 1\n" + "".join(lines)


def darwin_writer(entry, inherited_too: bool) -> bool:
    tag, qualifier, kind, flags, rights = entry
    return (
        kind == "allow"
        and (inherited_too or "only_inherit" not in flags)
        and not (tag == "user" and qualifier in (ME_ON_A_MAC, 0))
        and any(right in WRITE_RIGHTS for right in rights)
    )


@given(entries=st.lists(darwin_entries, max_size=6), inherited_too=st.booleans())
def test_darwin_acl_problem_is_any_entry_letting_another_account_write(
    entries, inherited_too
):
    problem = darwin_acl_problem(
        darwin_text(entries), ME_ON_A_MAC, inherited_too=inherited_too
    )
    assert (problem is not None) == any(
        darwin_writer(entry, inherited_too) for entry in entries
    )


@given(entries=st.lists(darwin_entries, max_size=6))
def test_darwin_new_entries_rule_is_at_least_as_strict(entries):
    text = darwin_text(entries)
    if darwin_acl_problem(text, ME_ON_A_MAC, inherited_too=True) is None:
        assert darwin_acl_problem(text, ME_ON_A_MAC, inherited_too=False) is None


# The mode rules themselves, over every permission bit pattern (setuid,
# setgid and sticky included), owner and private group, with the current uid
# both a regular user and root. The cache directory and everything in it must
# be the user's own, not world-writable, and group-writable only by the
# user's private group. A parent must be the user's or root's; with the
# sticky bit anything else goes, and without it a parent may not be
# world-writable, nor writable by a group other than its owner's private one.
ME, OTHER_USER, ROOT = 1000, 1001, 0
GID, OTHER_GID = 1000, 1001
ALL_MODES = range(0o10000)
PRIVATE_GROUPS = {
    "none": lambda uid: None,
    "mine": lambda uid: GID if uid == ME else None,
    "root's": lambda uid: GID if uid == ROOT else None,
}


def stat_with(mode: int, uid: int, gid: int = GID) -> os.stat_result:
    return os.stat_result((stat.S_IFDIR | mode, 0, 0, 0, uid, gid, 0, 0, 0, 0))


@pytest.mark.parametrize("private", PRIVATE_GROUPS)
@pytest.mark.parametrize("me", [ME, ROOT])
@pytest.mark.parametrize("owner", [ME, OTHER_USER, ROOT])
def test_cache_rule_over_every_mode(me, owner, private):
    private_gid = PRIVATE_GROUPS[private]
    for mode in ALL_MODES:
        accepted = cache_problem(stat_with(mode, owner), me, private_gid) is None
        group_ok = not mode & 0o020 or private_gid(me) == GID
        assert accepted == (owner == me and not mode & 0o002 and group_ok), oct(mode)


@pytest.mark.parametrize("private", PRIVATE_GROUPS)
@pytest.mark.parametrize("me", [ME, ROOT])
@pytest.mark.parametrize("owner", [ME, OTHER_USER, ROOT])
def test_parent_rule_over_every_mode(me, owner, private):
    private_gid = PRIVATE_GROUPS[private]
    for mode in ALL_MODES:
        accepted = parent_problem(stat_with(mode, owner), me, private_gid) is None
        sticky = bool(mode & stat.S_ISVTX)
        shared_group_writes = mode & 0o020 and private_gid(owner) != GID
        writable_by_others = mode & 0o002 or shared_group_writes
        expected = owner in (me, ROOT) and (sticky or not writable_by_others)
        assert accepted == expected, oct(mode)


def group_semantics(monkeypatch, semantics: str) -> int:
    """Judge new entries' groups as on BSD, or as on Linux with the process's
    group GID; the directory mode to use (setgid for "setgid")."""
    monkeypatch.setattr(cache_module, "_BSD_GROUPS", semantics == "bsd")
    monkeypatch.setattr(os, "getegid", lambda: GID)
    return 0o2755 if semantics == "setgid" else 0o755


@pytest.mark.parametrize("semantics", ["bsd", "setgid", "linux"])
@pytest.mark.parametrize("private", [True, False])
def test_umask_rule_over_every_umask(monkeypatch, private, semantics):
    mode = group_semantics(monkeypatch, semantics)
    private_gid = PRIVATE_GROUPS["mine" if private else "none"]
    for directory_gid in (GID, OTHER_GID):
        directory = stat_with(mode, ME, directory_gid)
        # BSD and setgid: the directory's group. Linux: the process's, or the
        # directory's under grpid.
        possible = {directory_gid} | ({GID} if semantics == "linux" else set())
        groups_private = all(private_gid(ME) == gid for gid in possible)
        for umask in range(0o1000):
            accepted = umask_problem(umask, directory, ME, private_gid) is None
            expected = bool(umask & 0o002 and (umask & 0o020 or groups_private))
            assert accepted == expected, (oct(umask), directory_gid)


@posix_only
def test_new_entries_get_one_of_the_groups_the_umask_rule_allows_for(tmp_path):
    groups = cache_module._new_entry_gids(os.stat(tmp_path))
    assert new_entry_group(tmp_path) in groups


@pytest.mark.parametrize("semantics", ["bsd", "setgid", "linux"])
def test_new_entry_groups(monkeypatch, semantics):
    mode = group_semantics(monkeypatch, semantics)
    groups = cache_module._new_entry_gids(stat_with(mode, ME, OTHER_GID))
    assert groups == ({OTHER_GID, GID} if semantics == "linux" else {OTHER_GID})


@posix_only
def test_a_shared_group_cache_is_refused_under_umask_002_where_grpid_could_apply(
    monkeypatch, tmp_path, umask
):
    """Review r3's case: a private process group, umask 002 and an existing
    0o755 cache of a shared group, not setgid. On a filesystem mounted with
    grpid, diskcache's new entries would get the shared group."""
    cache_dir = make_cache(tmp_path, dir_mode=0o755)
    shared = os.stat(cache_dir).st_gid
    monkeypatch.setattr(cache_module, "_BSD_GROUPS", False)
    monkeypatch.setattr(os, "getegid", lambda: shared + 1)
    private_group(monkeypatch, shared + 1)
    umask(0o002)

    with pytest.raises(UnsafeCacheDirError) as refused:
        secure_cache_dir(str(cache_dir))

    message = str(refused.value)
    assert cache_module._group(shared) in message
    assert "under your umask 002 if the filesystem gives new entries" in message

    private_group(monkeypatch, shared)
    monkeypatch.setattr(os, "getegid", lambda: shared)
    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)


uids = st.integers(min_value=0, max_value=2**32 - 1)
gids = st.sampled_from([GID, OTHER_GID])
modes = st.integers(min_value=0, max_value=0o7777)


@given(me=uids, owner=uids, gid=gids, mode=modes)
def test_group_write_never_matters_for_the_owners_private_group(me, owner, gid, mode):
    def private_gid(uid):
        return gid

    with_group, without_group = mode | 0o020, mode & ~0o020
    for rule in (cache_problem, parent_problem):
        assert (rule(stat_with(with_group, owner, gid), me, private_gid) is None) == (
            rule(stat_with(without_group, owner, gid), me, private_gid) is None
        )


@given(me=uids, owner=uids, mode=modes)
def test_group_write_by_a_shared_group_always_matters(me, owner, mode):
    shared = stat_with(mode | 0o020, owner)
    assert cache_problem(shared, me) is not None
    if not mode & stat.S_ISVTX:
        assert parent_problem(shared, me) is not None


@given(me=uids, owner=uids, mode=modes, private=st.sampled_from(list(PRIVATE_GROUPS)))
def test_the_cache_rule_is_at_least_as_strict_as_the_parent_rule(
    me, owner, mode, private
):
    private_gid = PRIVATE_GROUPS[private]
    if cache_problem(stat_with(mode, owner), me, private_gid) is None:
        assert parent_problem(stat_with(mode, owner), me, private_gid) is None


# Linux POSIX ACLs. The oracle runs acl(5)'s access check algorithm for each
# account that might try to write, rather than restating the guard's rule.
# GID is the private group of ME, so no one else is in it; anyone may be in
# OTHER_GID or 3000.
ATTACKERS = (OTHER_USER, 2000, 4242)
SHARED_GROUPS = (OTHER_GID, 3000)
acl_perms = st.integers(min_value=0, max_value=7)


@st.composite
def posix_acls(draw):
    """A valid ACL: one owner, owning-group and other entry, distinct named
    entries, and a mask whenever there is a named entry (acl(5))."""
    users = draw(st.lists(st.sampled_from([ME, *ATTACKERS[:2], ROOT]), unique=True))
    groups = draw(st.lists(st.sampled_from([GID, *SHARED_GROUPS]), unique=True))
    entries = [(USER_OBJ, draw(acl_perms), ACL_UNDEFINED_ID)]
    entries += [(USER, draw(acl_perms), qualifier) for qualifier in users]
    entries.append((GROUP_OBJ, draw(acl_perms), ACL_UNDEFINED_ID))
    entries += [(GROUP, draw(acl_perms), qualifier) for qualifier in groups]
    if users or groups or draw(st.booleans()):
        entries.append((MASK, draw(acl_perms), ACL_UNDEFINED_ID))
    entries.append((OTHER, draw(acl_perms), ACL_UNDEFINED_ID))
    return entries


def acl5_grants_write(entries, owner: int, group: int, euid: int, groups) -> bool:
    """acl(5)'s access check algorithm, for write, for an unprivileged process."""

    def only(tag):
        (perm,) = [perm for t, perm, _ in entries if t == tag]
        return perm

    mask = next((perm for tag, perm, _ in entries if tag == MASK), 0o7)
    if euid == owner:
        return bool(only(USER_OBJ) & 0o2)
    for tag, perm, qualifier in entries:
        if tag == USER and qualifier == euid:
            return bool(perm & mask & 0o2)
    matching = [
        perm
        for tag, perm, qualifier in entries
        if (tag == GROUP_OBJ and group in groups)
        or (tag == GROUP and qualifier in groups)
    ]
    if matching:
        return any(perm & mask & 0o2 for perm in matching)
    return bool(only(OTHER) & 0o2)


def subsets(items):
    return chain.from_iterable(combinations(items, n) for n in range(len(items) + 1))


def another_account_can_write(entries, owner: int, group: int) -> bool:
    shared = [g for g in (group, *SHARED_GROUPS) if g != GID]
    return any(
        acl5_grants_write(entries, owner, group, attacker, set(groups))
        for attacker in ATTACKERS
        if attacker != owner
        for groups in subsets(shared)
    )


def mode_of_acl(entries) -> int:
    """The mode bits an entry with this access ACL shows (acl(5))."""
    perm = {tag: perm for tag, perm, _ in entries}
    group_class = perm.get(MASK, perm[GROUP_OBJ])
    return perm[USER_OBJ] << 6 | group_class << 3 | perm[OTHER]


def private_to_me(uid: int) -> int | None:
    return GID if uid == ME else None


@given(entries=posix_acls(), group=st.sampled_from([GID, OTHER_GID]))
def test_an_access_acl_is_refused_when_acl5_lets_another_account_write(entries, group):
    """Sound against acl(5); stricter only where the mode bits show group write
    by a shared group that the owning-group entry itself lacks."""
    entry = stat_with(mode_of_acl(entries), ME, group)
    refused = (
        cache_problem(entry, ME, private_to_me)
        or linux_acl_problem(acl_blob(entries), None, entry, ME, private_to_me)
    ) is not None
    writable = another_account_can_write(entries, ME, group)
    shows_shared_group_write = mode_of_acl(entries) & 0o020 and group != GID
    assert refused == (writable or bool(shows_shared_group_write))


@given(
    entries=posix_acls(),
    new_gids=st.sampled_from([{GID}, {OTHER_GID}, {GID, OTHER_GID}]),
)
def test_a_default_acl_is_refused_exactly_when_new_entries_would_be_writable(
    entries, new_gids
):
    """A directory's default ACL becomes its new entries' access ACL (owned by
    ME, of one of new_gids); diskcache's modes keep every write bit."""
    directory = stat_with(0o755, ME)
    refused = linux_acl_problem(
        None, acl_blob(entries), directory, ME, private_to_me, new_gids
    )
    writable = any(another_account_can_write(entries, ME, gid) for gid in new_gids)
    assert (refused is not None) == writable


@given(entries=posix_acls())
def test_posix_acl_round_trips(entries):
    assert posix_acl_entries(acl_blob(entries)) == entries


@pytest.mark.parametrize(
    "blob", [b"\x02\x00\x00", struct.pack("<I", 3), acl_blob([]) + b"\x00"]
)
def test_unreadable_posix_acl_is_a_problem(blob):
    assert linux_acl_problem(blob, None, stat_with(0o644, ME), ME) == (
        "has an ACL PolicyBench can't read"
    )


@given(entries=posix_acls(), new_gids=st.sampled_from([{GID}, {GID, OTHER_GID}]))
def test_linux_default_acl_rule_is_at_least_as_strict(entries, new_gids):
    blob = acl_blob(entries)
    directory = stat_with(0o755, ME)
    if linux_acl_problem(None, blob, directory, ME, private_to_me, new_gids) is None:
        assert linux_acl_problem(blob, None, directory, ME, private_to_me) is None


# NFSv4 ACLs (RFC 7531), as Linux's NFS client shows them in system.nfs4_acl.
ALLOW, DENY, AUDIT, ALARM = 0, 1, 2, 3
FILE_INHERIT, DIRECTORY_INHERIT, NO_PROPAGATE, INHERIT_ONLY = 0x1, 0x2, 0x4, 0x8
IDENTIFIER_GROUP = 0x40
READ_DATA, WRITE_DATA, APPEND_DATA, READ_NAMED_ATTRS = 0x1, 0x2, 0x4, 0x8
WRITE_NAMED_ATTRS, EXECUTE, DELETE_CHILD, READ_ATTRIBUTES = 0x10, 0x20, 0x40, 0x80
WRITE_ATTRIBUTES, WRITE_RETENTION, DELETE = 0x100, 0x200, 0x10000
READ_ACL, WRITE_ACL, WRITE_OWNER, SYNCHRONIZE = 0x20000, 0x40000, 0x80000, 0x100000
NFS4_HARMLESS = (
    READ_DATA,
    READ_NAMED_ATTRS,
    EXECUTE,
    READ_ATTRIBUTES,
    WRITE_ATTRIBUTES,
    READ_ACL,
    SYNCHRONIZE,
)
NFS4_WRITES = (
    WRITE_DATA,
    APPEND_DATA,
    WRITE_NAMED_ATTRS,
    DELETE_CHILD,
    WRITE_RETENTION,
    DELETE,
    WRITE_ACL,
    WRITE_OWNER,
)
NFS4_READ = READ_DATA | EXECUTE | READ_ATTRIBUTES | READ_ACL | SYNCHRONIZE


def nfs4_blob(entries) -> bytes:
    blob = struct.pack(">I", len(entries))
    for kind, flags, rights, holder in entries:
        name = holder.encode()
        blob += struct.pack(">IIII", kind, flags, rights, len(name))
        blob += name + b"\x00" * (-len(name) % 4)
    return blob


# What a server derives from a 0o755 directory's mode: the owner may do
# anything, the group and everyone else read and search.
NFS4_FROM_0755 = [
    (
        ALLOW,
        0,
        NFS4_READ | WRITE_DATA | APPEND_DATA | DELETE_CHILD | WRITE_ACL,
        "OWNER@",
    ),
    (DENY, 0, WRITE_DATA | APPEND_DATA | DELETE_CHILD, "GROUP@"),
    (ALLOW, 0, NFS4_READ, "GROUP@"),
    (DENY, 0, WRITE_DATA | APPEND_DATA | DELETE_CHILD | WRITE_ACL, "EVERYONE@"),
    (ALLOW, 0, NFS4_READ, "EVERYONE@"),
]
NFS4_ACLS = [
    (NFS4_FROM_0755, False, None),
    (NFS4_FROM_0755, True, None),
    (
        [(ALLOW, 0, WRITE_DATA, "EVERYONE@")],
        False,
        "has an NFSv4 ACL entry letting EVERYONE@ write",
    ),
    (
        [(ALLOW, 0, APPEND_DATA, "bob@example.com")],
        False,
        "has an NFSv4 ACL entry letting bob@example.com write",
    ),
    # Review r4: a holder is the server's name, which this process's uids
    # needn't match, so even the user's own uid may be another account.
    (
        [(ALLOW, 0, WRITE_DATA, str(ME))],
        False,
        f"has an NFSv4 ACL entry letting {ME} write",
    ),
    ([(ALLOW, 0, WRITE_DATA, "0")], False, "has an NFSv4 ACL entry letting 0 write"),
    ([(ALLOW, 0, NFS4_READ, str(ME))], False, None),
    (
        [(ALLOW, IDENTIFIER_GROUP, WRITE_DATA, str(ME))],
        False,
        f"has an NFSv4 ACL entry letting {ME} write",
    ),
    ([(DENY, 0, WRITE_DATA, "EVERYONE@")], False, None),
    (
        [(AUDIT, 0, WRITE_DATA, "EVERYONE@"), (ALARM, 0, DELETE, "EVERYONE@")],
        True,
        None,
    ),
    ([(ALLOW, 0, WRITE_ATTRIBUTES | NFS4_READ, "EVERYONE@")], True, None),
    (
        [(ALLOW, 0, WRITE_RETENTION, "EVERYONE@")],
        False,
        "has an NFSv4 ACL entry letting EVERYONE@ write",
    ),
    ([(ALLOW, FILE_INHERIT | INHERIT_ONLY, WRITE_DATA, "EVERYONE@")], False, None),
    (
        [(ALLOW, FILE_INHERIT | INHERIT_ONLY, WRITE_DATA, "EVERYONE@")],
        True,
        "has an NFSv4 ACL entry inherited by new entries letting EVERYONE@ write",
    ),
    ([(ALLOW, INHERIT_ONLY, WRITE_DATA, "EVERYONE@")], True, None),
    ([(ALLOW, 0, WRITE_DATA, "OWNER@")], True, None),
    ([(ALLOW, DIRECTORY_INHERIT, WRITE_DATA, "GROUP@")], True, None),
]


@pytest.mark.parametrize(("entries", "inherited_too", "expected"), NFS4_ACLS)
def test_nfs4_acl(entries, inherited_too, expected):
    directory = stat_with(0o755, ME)  # of GID, the private group
    problem = nfs4_acl_problem(
        nfs4_blob(entries),
        directory,
        ME,
        private_to_me,
        {GID},
        inherited_too=inherited_too,
    )
    assert problem == expected


def test_nfs4_group_entries_need_private_groups():
    write = nfs4_blob([(ALLOW, FILE_INHERIT, WRITE_DATA, "GROUP@")])
    shared = stat_with(0o755, ME, OTHER_GID)
    problem = nfs4_acl_problem(
        write, shared, ME, private_to_me, {OTHER_GID}, inherited_too=False
    )
    other = cache_module._group(OTHER_GID)
    assert problem == f"has an NFSv4 ACL entry letting {other} write"
    # The directory's group is private, but new entries may get a shared one.
    problem = nfs4_acl_problem(
        write,
        stat_with(0o755, ME),
        ME,
        private_to_me,
        {GID, OTHER_GID},
        inherited_too=True,
    )
    assert problem == (
        f"has an NFSv4 ACL entry inherited by new entries letting {other} write"
    )


@pytest.mark.parametrize(
    "blob",
    [
        b"",
        struct.pack(">I", 1),
        struct.pack(">IIIII", 1, ALLOW, 0, WRITE_DATA, 9) + b"EVERYONE",
        struct.pack(">IIIII", 1, ALLOW, 0, WRITE_DATA, 2) + b"\xff\xfe\x00\x00",
        # Review r4's nit: a name short of its padding, and bytes after the
        # last entry.
        struct.pack(">IIIII", 1, ALLOW, 0, 1, 1) + b"x",
        struct.pack(">IIIII", 1, ALLOW, 0, 1, 1) + b"x\x00",
        struct.pack(">IIIII", 1, ALLOW, 0, 1, 1) + b"x\x00\x00\x00" + b"\x00" * 4,
        struct.pack(">I", 0) + b"\x00",
    ],
)
def test_unreadable_nfs4_acl_is_a_problem(blob):
    assert nfs4_acl_problem(blob, stat_with(0o755, ME), ME, inherited_too=False) == (
        "has an NFSv4 ACL PolicyBench can't read"
    )


NFS4_HOLDERS = (
    "OWNER@",
    "GROUP@",
    "EVERYONE@",
    "INTERACTIVE@",
    "bob@example.com",
    "2000",
    str(ME),
    "0",
)
nfs4_entries = st.lists(
    st.tuples(
        st.sampled_from([ALLOW, DENY, AUDIT, ALARM]),
        st.sets(
            st.sampled_from(
                [
                    FILE_INHERIT,
                    DIRECTORY_INHERIT,
                    NO_PROPAGATE,
                    INHERIT_ONLY,
                    IDENTIFIER_GROUP,
                ]
            )
        ).map(sum),
        st.sets(st.sampled_from(NFS4_HARMLESS + NFS4_WRITES)).map(sum),
        st.sampled_from(NFS4_HOLDERS),
    ),
    max_size=6,
)


@given(entries=nfs4_entries)
def test_nfs4_acl_round_trips(entries):
    assert nfs4_acl_entries(nfs4_blob(entries)) == entries


@given(entries=nfs4_entries, data=st.data())
def test_nfs4_acl_must_be_read_to_its_end(entries, data):
    """Any cut short of the whole attribute, and any bytes added after it,
    make it unreadable."""
    blob = nfs4_blob(entries)
    cut = data.draw(st.integers(0, len(blob) - 1))
    extra = data.draw(st.binary(min_size=1, max_size=8))
    for broken in (blob[:cut], blob + extra):
        with pytest.raises(ValueError):
            nfs4_acl_entries(broken)


def nfs4_grants_write(entries, group: int, attacker: str, groups) -> bool:
    """RFC 5661's evaluation (section 6.2.1) of an ACL for an account that is
    neither the owner nor root: for each right, the first allow or deny entry
    that names the account and holds the right decides it."""

    def names_attacker(flags, holder):
        if holder == "GROUP@":
            return group in groups
        if holder in ("EVERYONE@", "INTERACTIVE@"):
            return True
        if holder.endswith("@"):
            return False  # OWNER@
        return holder in groups if flags & IDENTIFIER_GROUP else holder == attacker

    for right in NFS4_WRITES:
        for kind, flags, rights, holder in entries:
            if kind in (ALLOW, DENY) and not flags & INHERIT_ONLY and rights & right:
                if names_attacker(flags, holder):
                    if kind == ALLOW:
                        return True
                    break
    return False


def nfs4_writer(entries, group: int) -> bool:
    # NFSv4 names are the server's, which the guard can't map to this
    # process's ids, so any named account or group, even one named by the
    # user's or root's id, may be or hold another account (review r4).
    shared = [g for g in (group,) if g != GID] + [
        "bob@example.com",
        "2000",
        str(ME),
        "0",
    ]
    return any(
        nfs4_grants_write(entries, group, attacker, set(groups))
        for attacker in ("bob@example.com", "2000", "4242", str(ME), "0")
        for groups in subsets(shared)
    )


@given(entries=nfs4_entries, group=st.sampled_from([GID, OTHER_GID]))
def test_nfs4_acl_is_refused_exactly_when_its_allow_entries_let_someone_write(
    entries, group
):
    """Ignoring deny entries errs toward refusing: refused exactly when the
    RFC's evaluation, with the deny entries taken out, lets another account
    write; so always when it does with them in."""
    entry = stat_with(0o755, ME, group)
    refused = (
        nfs4_acl_problem(
            nfs4_blob(entries), entry, ME, private_to_me, inherited_too=False
        )
        is not None
    )
    allows = [e for e in entries if e[0] != DENY]
    assert refused == nfs4_writer(allows, group)
    if nfs4_writer(entries, group):
        assert refused


@given(entries=nfs4_entries, new_gids=st.sampled_from([{GID}, {GID, OTHER_GID}]))
def test_nfs4_new_entries_rule_is_at_least_as_strict(entries, new_gids):
    blob = nfs4_blob(entries)
    directory = stat_with(0o755, ME)
    if (
        nfs4_acl_problem(
            blob, directory, ME, private_to_me, new_gids, inherited_too=True
        )
        is None
    ):
        assert (
            nfs4_acl_problem(blob, directory, ME, private_to_me, inherited_too=False)
            is None
        )


def fake_linux_xattrs(monkeypatch, attributes: dict[str, bytes]) -> None:
    """Make the guard's Linux attribute reads see ``attributes``."""

    def listxattr(target):
        return [name for name in attributes if not name.startswith("hidden:")]

    def xattr(target, name):
        return attributes.get(name, attributes.get(f"hidden:{name}"))

    monkeypatch.setattr(os, "listxattr", listxattr, raising=False)
    monkeypatch.setattr(cache_module, "_xattr", xattr)


def linux_verdict(
    monkeypatch, attributes, *, inherited_too=True, filesystem="ext4", mode=None
):
    monkeypatch.setattr(cache_module, "_BSD_GROUPS", False)
    monkeypatch.setattr(os, "getegid", lambda: GID)
    monkeypatch.setattr(cache_module, "_filesystem_type", lambda dev: filesystem)
    fake_linux_xattrs(monkeypatch, attributes)
    entry = stat_with(0o755, ME)
    if mode is not None:
        entry = os.stat_result((mode, *entry[1:]))
    return cache_module._linux_acl_problem(
        "entry", entry, ME, private_to_me, inherited_too=inherited_too
    )


def test_linux_reads_nfs4_acls_then_posix_acls(monkeypatch):
    everyone = nfs4_blob([(ALLOW, 0, WRITE_DATA, "EVERYONE@")])
    assert linux_verdict(monkeypatch, {"system.nfs4_acl": everyone}) == (
        "has an NFSv4 ACL entry letting EVERYONE@ write"
    )
    safe = nfs4_blob(NFS4_FROM_0755)
    posix = acl_blob(acl_granting(OTHER_USER, 6, 6))
    assert (
        linux_verdict(
            monkeypatch,
            {
                "system.nfs4_acl": safe,
                "system.posix_acl_access": posix,
                "security.selinux": b"x",
            },
        )
        == f"has an ACL entry letting uid {OTHER_USER} write"
    )
    assert linux_verdict(monkeypatch, {"system.nfs4_acl": safe}) is None


@pytest.mark.parametrize("name", ["system.nfs4_dacl", "hidden:system.nfs4_dacl"])
def test_linux_reads_an_nfs4_dacl(monkeypatch, name):
    """An NFSv4.1 server may offer the DACL alone: a flag word, then the
    entries."""
    flag = struct.pack(">I", 1)  # ACL4_AUTO_INHERIT
    everyone = nfs4_blob([(ALLOW, 0, WRITE_DATA, "EVERYONE@")])
    assert linux_verdict(monkeypatch, {name: flag + everyone}) == (
        "has an NFSv4 ACL entry letting EVERYONE@ write"
    )
    assert linux_verdict(monkeypatch, {name: flag + nfs4_blob(NFS4_FROM_0755)}) is None
    assert linux_verdict(monkeypatch, {name: flag}) == (
        "has an NFSv4 ACL PolicyBench can't read"
    )
    # The ACL attribute, when there is one, doesn't excuse the DACL.
    safe = nfs4_blob(NFS4_FROM_0755)
    assert linux_verdict(
        monkeypatch, {"system.nfs4_acl": safe, name: flag + everyone}
    ) == ("has an NFSv4 ACL entry letting EVERYONE@ write")


@pytest.mark.parametrize(
    "name",
    [
        "system.richacl",
        "security.NTACL",
        "system.cifs_ntsd",
        "hidden:system.nfs4_acl_xdr",
        "hidden:security.nfs4acl_xdr",
        "hidden:system.cifs_acl",
        "hidden:system.smb3_acl",
        # Review r4 finding 1: the kernel's AFS client lists none of these.
        # A listed one, from a client that lists them, is refused too.
        "afs.yfs.acl_inherited",
        "afs.acl",
        "hidden:afs.acl",
        "hidden:afs.yfs.acl",
        "hidden:afs.yfs.vol_acl",
    ],
)
def test_linux_refuses_acls_it_cant_judge(monkeypatch, name):
    """Listed or not, an ACL attribute the guard doesn't read is refused,
    including on parents."""
    shown = name.removeprefix("hidden:")
    for inherited_too in (True, False):
        assert linux_verdict(monkeypatch, {name: b""}, inherited_too=inherited_too) == (
            f"has an ACL PolicyBench can't check ({shown})"
        )


def test_linux_refuses_directories_on_afs(monkeypatch):
    """Review r4 finding 1: AFS grants writes by its directories' ACLs, which
    OpenAFS doesn't show as attributes, so any directory on AFS is refused,
    with or without them."""
    for attributes in ({}, {"hidden:afs.acl": b""}):
        for inherited_too in (True, False):
            assert linux_verdict(
                monkeypatch, attributes, inherited_too=inherited_too, filesystem="afs"
            ) == ("is on an afs filesystem, whose ACLs PolicyBench can't check")
    # A file shares its directory's filesystem, which is judged with it.
    regular = stat.S_IFREG | 0o644
    assert linux_verdict(monkeypatch, {}, filesystem="afs", mode=regular) is None
    assert linux_verdict(monkeypatch, {}, filesystem=None) is None


def dev(major, minor):
    return os.makedev(major, minor)


MOUNTINFO = """\
22 1 253:2 / / rw,relatime shared:1 - ext4 /dev/mapper/root rw
36 35 98:0 /mnt1 /mnt2 rw,noatime master:1 - ext3 /dev/root rw,errors=continue
41 22 0:52 / /afs rw,relatime shared:30 - afs AFS rw
42 41 0:53 / /afs/example.com/user\\040name rw,relatime - afs %example.com:user rw
43 22 0:54 / /run/doc rw,nosuid shared:31 propagate_from:2 - fuse.portal portal rw
44 22 0:55 / /broken rw shared:32
"""


@pytest.mark.parametrize(
    ("major", "minor", "expected"),
    [
        (253, 2, "ext4"),
        (98, 0, "ext3"),  # proc_pid_mountinfo(5)'s example
        (0, 52, "afs"),  # OpenAFS's single /afs mount
        (0, 53, "afs"),  # a volume the kernel's client mounts
        (0, 54, "fuse.portal"),  # two optional fields
        (0, 55, None),  # no separator
        (8, 1, None),  # not mounted
    ],
)
def test_mountinfo_gives_each_devices_filesystem_type(major, minor, expected):
    assert mountinfo_filesystem_type(MOUNTINFO, dev(major, minor)) == expected


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="reads /proc/self/mountinfo"
)
def test_filesystem_type_agrees_with_findmnt(tmp_path):
    """The type read from /proc for tmp_path's device is the one util-linux's
    findmnt gives for the mount holding it."""
    try:
        found = subprocess.run(
            ["findmnt", "--noheadings", "--output", "FSTYPE", "--target", tmp_path],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("findmnt is unavailable")
    assert cache_module._filesystem_type(os.stat(tmp_path).st_dev) == found[0]


def test_linux_without_attribute_support_has_no_acl_problem(monkeypatch):
    def listxattr(target):
        raise OSError(errno.ENOTSUP, os.strerror(errno.ENOTSUP))

    assert linux_verdict(monkeypatch, {}) is None
    monkeypatch.setattr(os, "listxattr", listxattr, raising=False)
    assert (
        cache_module._linux_acl_problem(
            "entry", stat_with(0o755, ME), ME, private_to_me, inherited_too=True
        )
        is None
    )


class WatchedLock:
    """A lock that records when a thread has to wait for it."""

    def __init__(self):
        self.lock = threading.Lock()
        self.waited = threading.Event()

    def __enter__(self):
        if not self.lock.acquire(blocking=False):
            self.waited.set()
            self.lock.acquire()
        return self

    def __exit__(self, *exc):
        self.lock.release()


def run_umask_readers(monkeypatch, proc_reads):
    """Run two process_umask calls, the first paused holding its 0o077
    stand-in until the second has finished or is waiting for the lock.

    The process umask is faked, starting at 0o000. ``proc_reads`` gives what
    each /proc read returns in turn, None for a failed read or ``"umask"`` for
    the umask at that moment.
    """
    current = {"umask": 0o000}
    stand_in_set, release = threading.Event(), threading.Event()
    reads = iter(proc_reads)

    def proc_umask():
        value = next(reads)
        return current["umask"] if value == "umask" else value

    def fake_umask(mask):
        previous, current["umask"] = current["umask"], mask
        if mask == 0o077 and not stand_in_set.is_set():
            stand_in_set.set()
            release.wait(10)
        return previous

    lock = WatchedLock()
    monkeypatch.setattr(cache_module, "_UMASK_LOCK", lock)
    monkeypatch.setattr(cache_module, "_proc_umask", proc_umask)
    monkeypatch.setattr(os, "umask", fake_umask)
    results = {}
    first = threading.Thread(target=lambda: results.update(first=process_umask()))
    second = threading.Thread(target=lambda: results.update(second=process_umask()))
    first.start()
    assert stand_in_set.wait(10)
    second.start()
    # Without the lock the second read finishes; with it, it waits.
    while second.is_alive() and not lock.waited.wait(0.01):
        pass
    release.set()
    first.join(10)
    second.join(10)
    assert current["umask"] == 0o000
    return results


def test_concurrent_umask_reads_see_the_real_umask(monkeypatch):
    """Review r3: where reading the umask means setting it, a second reader
    between the first's two calls would read the first's stand-in, 0o077,
    and restore it."""
    results = run_umask_readers(monkeypatch, [None, None])
    assert results == {"first": 0o000, "second": 0o000}


def test_a_proc_read_waits_for_another_guards_stand_in(monkeypatch):
    """Review r4 finding 3: the first guard's /proc read fails, so it sets the
    stand-in; the second's /proc read succeeds, and must not see it."""
    results = run_umask_readers(monkeypatch, [None, "umask"])
    assert results == {"first": 0o000, "second": 0o000}
