"""Tests for versioned LiteLLM cache setup and the cache-directory guard."""

import glob
import os
import stat
from unittest.mock import patch

import litellm
import pytest
from hypothesis import given
from hypothesis import strategies as st

from policybench.cache import (
    CacheDirError,
    UnsafeCacheDirError,
    cache_problem,
    enable_cache,
    parent_problem,
    secure_cache_dir,
)
from policybench.model_cards import PROMPT_CONTRACT_VERSION

posix_only = pytest.mark.skipif(
    not hasattr(os, "getuid"), reason="needs POSIX owners and permission bits"
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


def fake_owner(monkeypatch, path, uid: int) -> None:
    """Make os.stat and os.lstat report ``path`` as owned by ``uid``."""
    target = os.path.realpath(path)
    for name in ("stat", "lstat"):
        real = getattr(os, name)

        def fake(p, *args, _real=real, **kwargs):
            result = _real(p, *args, **kwargs)
            if isinstance(p, (str, os.PathLike)) and os.fspath(p) == target:
                fields = list(result[:10])
                fields[4] = uid  # st_uid
                return os.stat_result(fields)
            return result

        monkeypatch.setattr(os, name, fake)


@pytest.fixture
def umask():
    """Set the process umask for a test and restore it afterwards."""
    previous = os.umask(0o022)
    os.umask(previous)
    yield os.umask
    os.umask(previous)


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


@posix_only
def test_value_files_made_under_umask_000_are_refused_next_run(
    monkeypatch, tmp_path, umask
):
    """diskcache makes its files under the process umask.

    Under umask 000 its value subdirectories come out world-writable. The guard
    can't stop that mid-run, but refuses the cache at the next start.
    """
    monkeypatch.setattr(litellm, "cache", None)
    umask(0o000)
    cache_dir = tmp_path / "cache"
    enable_cache(str(cache_dir))
    litellm.cache.cache.set_cache("key", {"response": "x" * 40_000})

    with pytest.raises(UnsafeCacheDirError, match="is world-writable"):
        secure_cache_dir(str(cache_dir))


@posix_only
@pytest.mark.parametrize("process_umask", [0o000, 0o002, 0o022, 0o077])
def test_missing_directory_and_parents_are_created_owner_only(
    tmp_path, umask, process_umask
):
    umask(process_umask)
    cache_dir = tmp_path / "new" / "nested" / "cache"

    resolved = secure_cache_dir(str(cache_dir))

    assert resolved == os.path.realpath(cache_dir)
    for created in (tmp_path / "new", tmp_path / "new" / "nested", cache_dir):
        assert mode_of(created) == 0o700


@posix_only
def test_existing_0o755_cache_is_accepted_and_left_alone(tmp_path):
    cache_dir = make_cache(tmp_path, dir_mode=0o755)

    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)
    assert mode_of(cache_dir) == 0o755


@posix_only
@pytest.mark.parametrize("dir_mode", [0o770, 0o775, 0o2775])
def test_group_writable_cache_and_entries_are_accepted(tmp_path, dir_mode):
    """Ubuntu's umask 002 with user-private groups makes these by default."""
    cache_dir = make_cache(tmp_path, dir_mode=dir_mode)
    for name in CACHE_FILES:
        (cache_dir / name).chmod(0o664)
    for name in CACHE_SUBDIRS:
        (cache_dir / name).chmod(0o775)

    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)


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

    with pytest.raises(UnsafeCacheDirError, match=f"it is owned by uid {owner},"):
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
def test_entry_deleted_by_a_concurrent_run_is_skipped(monkeypatch, tmp_path):
    """diskcache culls value files past its size limit while others run."""
    cache_dir = make_cache(tmp_path)
    culled = os.path.realpath(cache_dir / CACHE_FILES[-1])
    real_lstat = os.lstat

    def lstat(p, *args, **kwargs):
        if isinstance(p, str) and p == culled:
            raise FileNotFoundError(2, "No such file or directory", p)
        return real_lstat(p, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", lstat)

    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)


@posix_only
@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root reads anything"
)
def test_unreadable_subdirectory_is_a_clean_error(tmp_path):
    cache_dir = make_cache(tmp_path)
    (cache_dir / "ab").chmod(0o000)
    try:
        with pytest.raises(CacheDirError, match="Can't check .*ab in the LiteLLM"):
            secure_cache_dir(str(cache_dir))
    finally:
        (cache_dir / "ab").chmod(0o755)


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
def test_root_owned_parent_is_accepted_unless_its_group_can_write(
    monkeypatch, tmp_path
):
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o755)
    fake_owner(monkeypatch, shared, 0)
    cache_dir = shared / "cache"

    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)

    if os.getuid() != 0:
        # A root-owned directory's group is a shared one, so its members could
        # swap the cache out, unless the sticky bit stops them.
        shared.chmod(0o775)
        with pytest.raises(
            UnsafeCacheDirError,
            match="is owned by root and group-writable without the sticky bit",
        ):
            secure_cache_dir(str(cache_dir))
        shared.chmod(0o1775)
        assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)


@posix_only
def test_own_group_writable_parent_is_accepted(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o775)

    assert secure_cache_dir(str(shared / "cache")) == os.path.realpath(shared / "cache")


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


# The rules themselves, over every permission bit pattern (setuid, setgid and
# sticky included) and owner, with the current uid both a regular user and
# root. The cache directory and everything in it must be the user's own and
# not world-writable. A parent must be the user's or root's; with the sticky
# bit anything else goes, and without it a parent may not be world-writable,
# nor group-writable when it is root's rather than the user's.
ME, OTHER, ROOT = 1000, 1001, 0
ALL_MODES = range(0o10000)


def stat_with(mode: int, uid: int) -> os.stat_result:
    return os.stat_result((stat.S_IFDIR | mode, 0, 0, 0, uid, 0, 0, 0, 0, 0))


@pytest.mark.parametrize("me", [ME, ROOT])
@pytest.mark.parametrize("owner", [ME, OTHER, ROOT])
def test_cache_rule_over_every_mode(me, owner):
    for mode in ALL_MODES:
        accepted = cache_problem(stat_with(mode, owner), me) is None
        assert accepted == (owner == me and not mode & 0o002), oct(mode)


@pytest.mark.parametrize("me", [ME, ROOT])
@pytest.mark.parametrize("owner", [ME, OTHER, ROOT])
def test_parent_rule_over_every_mode(me, owner):
    for mode in ALL_MODES:
        accepted = parent_problem(stat_with(mode, owner), me) is None
        sticky = bool(mode & stat.S_ISVTX)
        writable_by_others = mode & 0o002 or (owner != me and mode & 0o020)
        expected = owner in (me, ROOT) and (sticky or not writable_by_others)
        assert accepted == expected, oct(mode)


uids = st.integers(min_value=0, max_value=2**32 - 1)
modes = st.integers(min_value=0, max_value=0o7777)


@given(me=uids, owner=uids, mode=modes)
def test_group_write_never_matters_on_the_users_own_directories(me, owner, mode):
    with_group, without_group = mode | 0o020, mode & ~0o020
    assert (cache_problem(stat_with(with_group, owner), me) is None) == (
        cache_problem(stat_with(without_group, owner), me) is None
    )
    if owner == me:
        assert (parent_problem(stat_with(with_group, owner), me) is None) == (
            parent_problem(stat_with(without_group, owner), me) is None
        )


@given(me=uids, owner=uids, mode=modes)
def test_the_cache_rule_is_at_least_as_strict_as_the_parent_rule(me, owner, mode):
    if cache_problem(stat_with(mode, owner), me) is None:
        assert parent_problem(stat_with(mode, owner), me) is None
