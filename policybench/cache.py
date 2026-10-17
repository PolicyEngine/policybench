"""LiteLLM disk cache setup for PolicyBench."""

import os
import stat

import litellm
from litellm.caching.caching import Cache

from policybench.model_cards import PROMPT_CONTRACT_VERSION

# Resolved relative to the process CWD unless POLICYBENCH_CACHE_DIR is set.
# Chunked/resumed runs shell out to subprocesses that inherit the parent CWD, so
# set the env var (to an absolute path) when launching commands from different
# directories — otherwise a run started elsewhere silently gets a fresh cache.
CACHE_DIR = os.environ.get("POLICYBENCH_CACHE_DIR", ".policybench_cache")

# LiteLLM's disk cache is diskcache, which unpickles any entry its sqlite index
# (cache.db) marks as pickled, inline or from a .val file under the cache
# directory, and no diskcache release fixes that (GHSA-w8v5-vhqr-4h9v). So
# whoever can write anything in the cache can run code in the process that
# reads it, and enable_cache only accepts a cache no other account can write.


class CacheDirError(RuntimeError):
    """The LiteLLM disk cache directory can't be used."""


class UnsafeCacheDirError(CacheDirError):
    """Another account could write the LiteLLM disk cache."""


def _unsafe(path: str, reason: str) -> UnsafeCacheDirError:
    return UnsafeCacheDirError(
        f"Refusing to use {path} as the LiteLLM disk cache: {reason}. LiteLLM's "
        "disk cache (diskcache) unpickles cache entries, so an account that can "
        "write the cache can run code as you (GHSA-w8v5-vhqr-4h9v). If another "
        "account could have written to it, delete it (it is only a cache); "
        "otherwise fix the ownership or permissions, or set "
        "POLICYBENCH_CACHE_DIR to a directory only you can write."
    )


def cache_problem(st: os.stat_result, uid: int) -> str | None:
    """Why another account could write the cache directory or an entry in it.

    Group write is allowed: with the user-private groups of a default Ubuntu
    install (umask 002), every directory a user makes is group-writable.
    """
    if st.st_uid != uid:
        return f"is owned by uid {st.st_uid}, not the current user (uid {uid})"
    if st.st_mode & stat.S_IWOTH:
        return f"is world-writable (mode {stat.S_IMODE(st.st_mode):#o})"
    return None


def parent_problem(st: os.stat_result, uid: int) -> str | None:
    """Why another account could swap the cache directory out of this parent.

    diskcache reopens cache.db by path for each new thread and process, so an
    account that can rename entries in a parent could replace the directory
    after it was checked. The sticky bit (as on /tmp) limits renaming an entry
    to its owner. Without it, a parent must be the user's own, or root's and
    writable by root alone: a root-owned directory's group is a shared one,
    unlike the user-private group that makes the user's own directories
    group-writable.
    """
    if st.st_uid not in (uid, 0):
        return f"is owned by uid {st.st_uid}, not the current user (uid {uid})"
    if st.st_mode & stat.S_ISVTX:
        return None
    mode = stat.S_IMODE(st.st_mode)
    if st.st_mode & stat.S_IWOTH:
        return f"is world-writable without the sticky bit (mode {mode:#o})"
    if st.st_uid != uid and st.st_mode & stat.S_IWGRP:
        return (
            "is owned by root and group-writable without the sticky bit "
            f"(mode {mode:#o})"
        )
    return None


def _contents_problem(path: str, uid: int) -> str | None:
    """Why another account could have written an entry inside the cache.

    Covers cache.db and the files SQLite keeps beside it, and the hex
    subdirectories and .val files diskcache stores large values in. diskcache
    never makes symlinks, so a symlink is refused rather than followed.
    """

    def fail(error: OSError) -> None:
        # A concurrent run sharing the cache can delete a value file or its
        # directory mid-walk (diskcache culls past its size limit).
        if not isinstance(error, FileNotFoundError):
            raise CacheDirError(
                f"Can't check {error.filename} in the LiteLLM disk cache: "
                f"{error.strerror}."
            ) from error

    for root, dirnames, filenames in os.walk(path, onerror=fail):
        for name in sorted(dirnames + filenames):
            entry = os.path.join(root, name)
            try:
                st = os.lstat(entry)
            except FileNotFoundError:
                continue
            relative = os.path.relpath(entry, path)
            if stat.S_ISLNK(st.st_mode):
                return f"its {relative} is a symlink"
            problem = cache_problem(st, uid)
            if problem:
                return f"its {relative} {problem}"
    return None


def _make_private_dirs(path: str) -> None:
    """Create ``path`` and any missing parents with mode 0o700."""
    missing = []
    while not os.path.isdir(path):
        missing.append(path)
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    for directory in reversed(missing):
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            # A concurrent run sharing the cache created it first; the checks
            # in secure_cache_dir judge it like any other existing directory.
            pass
        except OSError as error:
            raise CacheDirError(
                f"Can't create the LiteLLM disk cache directory {directory}: "
                f"{error.strerror}."
            ) from error


def _check_no_reexpansion(path: str) -> None:
    # diskcache.Cache runs expandvars on the directory it is given; the path
    # handed to it must come through unchanged.
    expanded = os.path.expandvars(path)
    if expanded != path:
        raise CacheDirError(
            f"Can't use {path} as the LiteLLM disk cache: diskcache would expand "
            f"the $ in it and open {expanded} instead."
        )


def secure_cache_dir(cache_dir: str) -> str:
    """Resolve, create and vet the cache directory; return the path to open.

    Raises UnsafeCacheDirError when another account could write the directory
    or anything in it, or could swap the directory out of a parent, and
    CacheDirError when the path can't be used at all.
    """
    if not cache_dir:
        raise CacheDirError(
            "The LiteLLM disk cache directory is an empty string; unset "
            "POLICYBENCH_CACHE_DIR or set it to a path."
        )
    # diskcache.Cache expands ~ and $VARS in the directory it is given, so
    # expand the same way before resolving.
    path = os.path.realpath(os.path.expandvars(os.path.expanduser(cache_dir)))
    _check_no_reexpansion(path)
    _make_private_dirs(path)
    # Resolve again: a symlink could have taken the name before mkdir did.
    path = os.path.realpath(path)
    _check_no_reexpansion(path)
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode):
        raise CacheDirError(
            f"Can't use {path} as the LiteLLM disk cache: it is not a directory."
        )

    getuid = getattr(os, "getuid", None)
    if getuid is None:
        # Windows has no POSIX owners, and os.stat reports every writable
        # directory there as mode 0o777, so neither check means anything.
        return path
    uid = getuid()

    problem = cache_problem(st, uid)
    if problem:
        raise _unsafe(path, f"it {problem}")
    parent = os.path.dirname(path)
    while True:
        problem = parent_problem(os.lstat(parent), uid)
        if problem:
            raise _unsafe(path, f"its parent directory {parent} {problem}")
        grandparent = os.path.dirname(parent)
        if grandparent == parent:
            break
        parent = grandparent
    problem = _contents_problem(path, uid)
    if problem:
        raise _unsafe(path, problem)
    return path


def enable_cache(cache_dir: str | None = None):
    """Enable LiteLLM disk caching for reproducible, cost-efficient runs.

    The cache directory defaults to ``cache_dir`` if given, else
    ``$POLICYBENCH_CACHE_DIR``, else ``.policybench_cache`` in the current
    working directory. A missing directory is created with mode 0o700; one
    another account could write is refused (see ``secure_cache_dir``).
    """
    litellm.cache = Cache(
        type="disk",
        disk_cache_dir=secure_cache_dir(cache_dir or CACHE_DIR),
        namespace=f"policybench:{PROMPT_CONTRACT_VERSION}",
    )
