"""Tests for versioned LiteLLM cache setup and the cache-directory guard."""

import os
import stat
from unittest.mock import patch

import litellm
import pytest
from hypothesis import given
from hypothesis import strategies as st

from policybench.cache import (
    CACHE_DB_FILES,
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


def mode_of(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def other_uid() -> int:
    return os.getuid() + 1


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
    """The guard accepts what LiteLLM's real diskcache backend creates."""
    monkeypatch.setattr(litellm, "cache", None)
    cache_dir = tmp_path / "cache"

    enable_cache(str(cache_dir))
    litellm.cache.cache.set_cache("key", {"answer": 1})

    assert litellm.cache.cache.get_cache("key") == {"answer": 1}
    assert (cache_dir / "cache.db").exists()
    # A second run over the now-populated cache is accepted too.
    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)


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
def test_existing_0o755_directory_is_accepted_and_left_alone(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_dir.chmod(0o755)

    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)
    assert mode_of(cache_dir) == 0o755


@posix_only
@pytest.mark.parametrize("dir_mode", [0o770, 0o775, 0o2775])
def test_group_writable_directory_and_database_are_accepted(tmp_path, dir_mode):
    """Ubuntu's umask 002 with user-private groups makes these by default."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    for name in CACHE_DB_FILES:
        (cache_dir / name).write_bytes(b"")
        (cache_dir / name).chmod(0o664)
    cache_dir.chmod(dir_mode)

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
@pytest.mark.parametrize("name", CACHE_DB_FILES)
def test_database_file_owned_by_another_user_is_refused(monkeypatch, tmp_path, name):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(mode=0o700)
    (cache_dir / name).write_bytes(b"")
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
@pytest.mark.parametrize("name", CACHE_DB_FILES)
def test_world_writable_database_file_is_refused(tmp_path, name):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(mode=0o700)
    (cache_dir / name).write_bytes(b"")
    (cache_dir / name).chmod(0o666)

    with pytest.raises(UnsafeCacheDirError, match=f"its {name} is world-writable"):
        secure_cache_dir(str(cache_dir))


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
def test_root_owned_parent_is_accepted(monkeypatch, tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    fake_owner(monkeypatch, shared, 0)

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


def test_path_diskcache_would_expand_again_is_refused(monkeypatch, tmp_path):
    """diskcache runs expandvars on the path it gets; it must not move it."""
    monkeypatch.setenv("POLICYBENCH_TEST_OUTER", "$POLICYBENCH_TEST_INNER")
    monkeypatch.setenv("POLICYBENCH_TEST_INNER", "elsewhere")

    with pytest.raises(UnsafeCacheDirError, match=r"would expand the \$ in it"):
        secure_cache_dir(str(tmp_path / "$POLICYBENCH_TEST_OUTER"))


def test_file_in_place_of_the_directory_is_refused(tmp_path):
    cache_file = tmp_path / "cache"
    cache_file.write_text("not a directory")

    with pytest.raises(UnsafeCacheDirError, match="it is not a directory"):
        secure_cache_dir(str(cache_file))


def test_empty_cache_directory_is_rejected(monkeypatch):
    monkeypatch.setattr("policybench.cache.CACHE_DIR", "")

    with pytest.raises(ValueError, match="empty string"):
        enable_cache()


@posix_only
def test_ownership_and_mode_checks_are_skipped_without_getuid(monkeypatch, tmp_path):
    """Windows: no POSIX owners, and os.stat reports writable dirs as 0o777."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_dir.chmod(0o777)
    monkeypatch.delattr(os, "getuid")

    assert secure_cache_dir(str(cache_dir)) == os.path.realpath(cache_dir)


@posix_only
def test_cli_exits_with_the_refusal_before_any_model_call(monkeypatch, tmp_path):
    from policybench.cli import main

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_dir.chmod(0o777)
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
        with pytest.raises(SystemExit, match="Refusing to use .* world-writable"):
            main()

    load_scenarios.assert_not_called()


# The policy itself, over every permission bit pattern (setuid, setgid and
# sticky included) and owner: the cache directory and its database files must
# be the user's own and not world-writable; a parent must be the user's or
# root's, and world-writable only with the sticky bit. Group write never
# matters.
ME, OTHER, ROOT = 1000, 1001, 0
ALL_MODES = range(0o10000)


def stat_with(mode: int, uid: int) -> os.stat_result:
    return os.stat_result((stat.S_IFDIR | mode, 0, 0, 0, uid, 0, 0, 0, 0, 0))


@pytest.mark.parametrize("me", [ME, ROOT])
@pytest.mark.parametrize("owner", [ME, OTHER, ROOT])
def test_cache_policy_over_every_mode(me, owner):
    for mode in ALL_MODES:
        accepted = cache_problem(stat_with(mode, owner), me) is None
        assert accepted == (owner == me and not mode & 0o002), oct(mode)


@pytest.mark.parametrize("me", [ME, ROOT])
@pytest.mark.parametrize("owner", [ME, OTHER, ROOT])
def test_parent_policy_over_every_mode(me, owner):
    for mode in ALL_MODES:
        accepted = parent_problem(stat_with(mode, owner), me) is None
        expected = owner in (me, ROOT) and (
            not mode & 0o002 or bool(mode & stat.S_ISVTX)
        )
        assert accepted == expected, oct(mode)


uids = st.integers(min_value=0, max_value=2**32 - 1)
modes = st.integers(min_value=0, max_value=0o7777)


@given(me=uids, owner=uids, mode=modes)
def test_group_write_never_changes_either_verdict(me, owner, mode):
    for check in (cache_problem, parent_problem):
        with_group = check(stat_with(mode | 0o020, owner), me) is None
        without_group = check(stat_with(mode & ~0o020, owner), me) is None
        assert with_group == without_group


@given(me=uids, owner=uids, mode=modes)
def test_an_acceptable_cache_dir_is_an_acceptable_parent(me, owner, mode):
    """The cache rule is strictly stricter than the parent rule."""
    if cache_problem(stat_with(mode, owner), me) is None:
        assert parent_problem(stat_with(mode, owner), me) is None
