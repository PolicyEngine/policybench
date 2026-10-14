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
# (cache.db, in the cache directory) marks as pickled, and no diskcache release
# fixes that (GHSA-w8v5-vhqr-4h9v). So whoever can write the cache directory can
# run code in the process that reads it, and enable_cache only accepts a
# directory no other account can write. SQLite reads the -wal and -shm files
# beside cache.db, so they are held to the same rule.
CACHE_DB_FILES = ("cache.db", "cache.db-wal", "cache.db-shm")


class UnsafeCacheDirError(RuntimeError):
    """The cache directory is one another account could write."""


def _refuse(path: str, reason: str) -> UnsafeCacheDirError:
    return UnsafeCacheDirError(
        f"Refusing to use {path} as the LiteLLM disk cache: {reason}. LiteLLM's "
        "disk cache (diskcache) unpickles cache entries, so an account that can "
        "write the cache can run code as you (GHSA-w8v5-vhqr-4h9v). Fix the "
        "ownership or permissions, or set POLICYBENCH_CACHE_DIR to a directory "
        "only you can write."
    )


def cache_problem(st: os.stat_result, uid: int) -> str | None:
    """Why another account could write the cache directory or a database file.

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
    after it was checked. Root-owned parents are trusted, and world-writable
    ones with the sticky bit (like /tmp) only let an entry's owner rename it.
    """
    if st.st_uid not in (uid, 0):
        return f"is owned by uid {st.st_uid}, not the current user (uid {uid})"
    if st.st_mode & stat.S_IWOTH and not st.st_mode & stat.S_ISVTX:
        return (
            "is world-writable without the sticky bit "
            f"(mode {stat.S_IMODE(st.st_mode):#o})"
        )
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


def secure_cache_dir(cache_dir: str) -> str:
    """Resolve, create and vet the cache directory; return the path to open.

    Raises UnsafeCacheDirError when another account could write the directory
    or its database files, or could swap the directory out of a parent.
    """
    if not cache_dir:
        raise ValueError(
            "The LiteLLM disk cache directory is an empty string; unset "
            "POLICYBENCH_CACHE_DIR or set it to a path."
        )
    # diskcache.Cache expands ~ and $VARS in the directory it is given, so
    # expand the same way before resolving.
    path = os.path.realpath(os.path.expandvars(os.path.expanduser(cache_dir)))
    _make_private_dirs(path)
    # Resolve again: a symlink could have taken the name before mkdir did.
    path = os.path.realpath(path)
    if os.path.expandvars(path) != path:
        raise _refuse(path, "diskcache would expand the $ in it to another path")
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode):
        raise _refuse(path, "it is not a directory")

    getuid = getattr(os, "getuid", None)
    if getuid is None:
        # Windows has no POSIX owners, and os.stat reports every writable
        # directory there as mode 0o777, so neither check means anything.
        return path
    uid = getuid()

    problem = cache_problem(st, uid)
    if problem:
        raise _refuse(path, f"it {problem}")
    for name in CACHE_DB_FILES:
        try:
            db_st = os.stat(os.path.join(path, name))
        except FileNotFoundError:
            continue
        problem = cache_problem(db_st, uid)
        if problem:
            raise _refuse(path, f"its {name} {problem}")
    parent = os.path.dirname(path)
    while True:
        problem = parent_problem(os.lstat(parent), uid)
        if problem:
            raise _refuse(path, f"its parent directory {parent} {problem}")
        grandparent = os.path.dirname(parent)
        if grandparent == parent:
            return path
        parent = grandparent


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
