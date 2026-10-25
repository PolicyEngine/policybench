"""LiteLLM disk cache setup for PolicyBench."""

import ctypes
import ctypes.util
import errno
import functools
import os
import stat
import struct
import sys
from collections.abc import Callable

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

# Directories are opened one at a time relative to their already-checked
# parent, never following a symlink. A directory the user may search but not
# list (an ancestor at mode 0o711, say) is opened for search only.
_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_SEARCH_FLAGS = getattr(os, "O_PATH", 0) or getattr(os, "O_SEARCH", 0)
# O_NONBLOCK keeps a FIFO swapped in after the type check from blocking open.
_FILE_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
    | getattr(os, "O_CLOEXEC", 0)
)

# BSD and macOS give an entry the group of the directory it is made in; Linux
# and System V give it the process's group unless the directory is setgid.
_BSD_GROUPS = sys.platform == "darwin" or "bsd" in sys.platform


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
        "otherwise fix the ownership, permissions, ACLs or umask, or set "
        "POLICYBENCH_CACHE_DIR to a directory only you can write."
    )


def _changed(path: str) -> CacheDirError:
    return CacheDirError(
        f"Can't use {path} as the LiteLLM disk cache: it changed while it was "
        "being checked. Run again."
    )


def user_private_gid(uid: int) -> int | None:
    """The user's primary group if it is theirs alone, else None.

    Debian, Ubuntu and Fedora give each user a primary group of their own
    name with no other members (a user-private group), so the group-writable
    files that umask 002 makes there are writable by the user alone. Other
    groups, macOS's staff among them, are shared.
    """
    import grp
    import pwd

    try:
        user = pwd.getpwuid(uid)
        group = grp.getgrgid(user.pw_gid)
    except KeyError:
        return None
    if group.gr_name != user.pw_name or set(group.gr_mem) - {user.pw_name}:
        return None
    if any(
        other.pw_gid == user.pw_gid and other.pw_uid != uid for other in pwd.getpwall()
    ):
        return None
    return user.pw_gid


def _no_private_groups(uid: int) -> int | None:
    return None


def _group(gid: int) -> str:
    try:
        import grp

        return f"group {grp.getgrgid(gid).gr_name} (gid {gid})"
    except (ImportError, KeyError):
        return f"gid {gid}"


def cache_problem(
    st: os.stat_result,
    uid: int,
    private_gid: Callable[[int], int | None] = _no_private_groups,
) -> str | None:
    """Why another account could write the cache directory or an entry in it.

    ``private_gid`` maps a uid to its user-private group (see
    ``user_private_gid``), the one group allowed to write.
    """
    if st.st_uid != uid:
        return f"is owned by uid {st.st_uid}, not the current user (uid {uid})"
    mode = stat.S_IMODE(st.st_mode)
    if st.st_mode & stat.S_IWOTH:
        return f"is world-writable (mode {mode:#o})"
    if st.st_mode & stat.S_IWGRP and st.st_gid != private_gid(uid):
        return f"is writable by {_group(st.st_gid)} (mode {mode:#o})"
    return None


def parent_problem(
    st: os.stat_result,
    uid: int,
    private_gid: Callable[[int], int | None] = _no_private_groups,
) -> str | None:
    """Why another account could swap the cache directory out of this parent.

    diskcache reopens cache.db by path for each new thread and process, so an
    account that can rename entries in a parent could replace the directory
    after it was checked. The sticky bit (as on /tmp) limits renaming an entry
    to its owner. Without it, a parent must be the user's own or root's, and
    writable by its owner alone or by the owner's private group.
    """
    if st.st_uid not in (uid, 0):
        return f"is owned by uid {st.st_uid}, not the current user (uid {uid})"
    if st.st_mode & stat.S_ISVTX:
        return None
    mode = stat.S_IMODE(st.st_mode)
    if st.st_mode & stat.S_IWOTH:
        return f"is world-writable without the sticky bit (mode {mode:#o})"
    if st.st_mode & stat.S_IWGRP and st.st_gid != private_gid(st.st_uid):
        return (
            f"is writable by {_group(st.st_gid)} without the sticky bit "
            f"(mode {mode:#o})"
        )
    return None


# ACLs. An allow entry for another account matters when it lets them change
# an entry's data, add or remove a directory's entries, delete the entry
# itself, or change its permissions or owner. Deny entries only take access
# away, and the user and root can already do anything.

# macOS (acl_to_text format, which names directory rights by their file
# equivalents: "write" for add_file, "append" for add_subdirectory).
_DARWIN_ACL_TYPE_EXTENDED = 0x00000100
_DARWIN_HARMLESS_RIGHTS = frozenset(
    {
        "read",
        "execute",
        "readattr",
        "writeattr",
        "readextattr",
        "writeextattr",
        "readsecurity",
        "synchronize",
    }
)


def darwin_acl_problem(text: str, uid: int, *, inherited_too: bool) -> str | None:
    """Why an entry of this macOS ACL lets another account write.

    An only_inherit entry applies not to the directory itself but to entries
    made in it later, so it counts only with ``inherited_too`` (the cache and
    its subdirectories, where diskcache adds entries). A right this function
    doesn't know counts as a write.
    """
    for line in text.splitlines():
        if not line or line.startswith("!#acl"):
            continue
        fields = line.split(":")
        if len(fields) < 6:
            return f"has an ACL entry PolicyBench can't read ({line!r})"
        tag, name, qualifier = fields[0], fields[2] or fields[1], fields[-3]
        flags, rights = fields[-2].split(","), fields[-1].split(",")
        if flags[0] == "deny" or ("only_inherit" in flags and not inherited_too):
            continue
        if tag == "user" and qualifier in (str(uid), "0"):
            continue
        writes = [right for right in rights if right not in _DARWIN_HARMLESS_RIGHTS]
        if writes:
            held = "inherited by new entries " if "only_inherit" in flags else ""
            return f"has an ACL entry {held}letting {tag} {name} {','.join(writes)}"
    return None


@functools.cache
def _darwin_libc():
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    libc.acl_get_fd_np.restype = ctypes.c_void_p
    libc.acl_get_fd_np.argtypes = [ctypes.c_int, ctypes.c_int]
    libc.acl_to_text.restype = ctypes.c_void_p
    libc.acl_to_text.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ssize_t)]
    libc.acl_free.restype = ctypes.c_int
    libc.acl_free.argtypes = [ctypes.c_void_p]
    return libc


def _darwin_acl_text(fd: int) -> str | None:
    libc = _darwin_libc()
    acl = libc.acl_get_fd_np(fd, _DARWIN_ACL_TYPE_EXTENDED)
    if not acl:
        error = ctypes.get_errno()
        if error == errno.ENOENT:  # no ACL
            return None
        raise OSError(error, os.strerror(error))
    try:
        length = ctypes.c_ssize_t()
        text = libc.acl_to_text(acl, ctypes.byref(length))
        if not text:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        try:
            return ctypes.string_at(text, length.value).decode()
        finally:
            libc.acl_free(text)
    finally:
        libc.acl_free(acl)


# Linux POSIX ACLs, stored as system.posix_acl_* extended attributes: a
# little-endian version (2), then (tag, permissions, id) entries.
_ACL_USER_OBJ, _ACL_USER, _ACL_GROUP_OBJ, _ACL_GROUP, _ACL_MASK, _ACL_OTHER = (
    0x01,
    0x02,
    0x04,
    0x08,
    0x10,
    0x20,
)
_ACL_WRITE = 0x02
# The mask limits what named entries and the owning group get.
_MASKED_TAGS = (_ACL_USER, _ACL_GROUP_OBJ, _ACL_GROUP)


def posix_acl_entries(blob: bytes) -> list[tuple[int, int, int]]:
    """The (tag, permissions, id) entries of a Linux POSIX ACL attribute."""
    if len(blob) < 4 or (len(blob) - 4) % 8 or struct.unpack_from("<I", blob)[0] != 2:
        raise ValueError("not a version-2 POSIX ACL")
    return [struct.unpack_from("<HHI", blob, at) for at in range(4, len(blob), 8)]


def linux_acl_problem(
    access: bytes | None,
    default: bytes | None,
    st: os.stat_result,
    uid: int,
    private_gid: Callable[[int], int | None] = _no_private_groups,
    new_entry_gid: int | None = None,
) -> str | None:
    """Why this entry's POSIX ACLs let another account write it or new entries.

    The access ACL's owner, owning-group (as the mask) and other rights are the
    mode bits, which cache_problem and parent_problem judge, so only its named
    entries are judged here; the mask limits them. The default ACL of a
    directory becomes the access ACL of entries made in it, in place of the
    umask, so all of its entries count, the owning group's as the group
    ``new_entry_gid`` that new entries get.
    """
    try:
        acls = [
            (kind, posix_acl_entries(blob))
            for kind, blob in (("ACL", access), ("default ACL", default))
            if blob
        ]
    except ValueError:
        return "has an ACL PolicyBench can't read"
    owners_group = private_gid(st.st_uid)
    for kind, entries in acls:
        mask = next((perm for tag, perm, _ in entries if tag == _ACL_MASK), 0o7)
        for tag, perm, qualifier in entries:
            masked = perm & mask if tag in _MASKED_TAGS else perm
            if not masked & _ACL_WRITE:
                continue
            if tag == _ACL_USER and qualifier not in (uid, 0, st.st_uid):
                return f"has an {kind} entry letting uid {qualifier} write"
            if tag == _ACL_GROUP and qualifier != owners_group:
                return f"has an {kind} entry letting {_group(qualifier)} write"
            if kind == "default ACL":
                if tag == _ACL_OTHER:
                    return "has a default ACL letting every account write new entries"
                if tag == _ACL_GROUP_OBJ and new_entry_gid != private_gid(uid):
                    return (
                        "has a default ACL letting "
                        f"{_group(new_entry_gid)} write new entries"
                    )
    return None


def _xattr(target: int | str, name: str) -> bytes | None:
    try:
        return os.getxattr(target, name)
    except OSError as error:
        if error.errno in (errno.ENODATA, errno.ENOTSUP, errno.EOPNOTSUPP):
            return None  # no such ACL, or a filesystem without ACLs
        raise


def _new_entry_gid(st: os.stat_result) -> int:
    """The group of an entry made in this directory."""
    if _BSD_GROUPS or st.st_mode & stat.S_ISGID:
        return st.st_gid
    return os.getegid()


def _acl_problem(
    fd: int,
    readable: bool,
    st: os.stat_result,
    uid: int,
    private_gid: Callable[[int], int | None],
    *,
    inherited_too: bool,
) -> str | None:
    """Why an ACL on this entry lets another account write it or, with
    ``inherited_too``, entries made in it later. Checked on macOS and Linux."""
    if sys.platform == "darwin":
        text = _darwin_acl_text(fd)
        if text is None:
            return None
        return darwin_acl_problem(text, uid, inherited_too=inherited_too)
    if sys.platform.startswith("linux"):
        # A search-only (O_PATH) descriptor can't read attributes itself.
        target = fd if readable else f"/proc/self/fd/{fd}"
        access = _xattr(target, "system.posix_acl_access")
        default = None
        if inherited_too and stat.S_ISDIR(st.st_mode):
            default = _xattr(target, "system.posix_acl_default")
        return linux_acl_problem(
            access, default, st, uid, private_gid, _new_entry_gid(st)
        )
    return None


def process_umask() -> int:
    """The process umask, read without changing it where Linux allows."""
    try:
        with open("/proc/self/status") as status:
            for line in status:
                if line.startswith("Umask:"):
                    return int(line.split()[1], 8)
    except OSError:
        pass
    # Elsewhere reading it means setting it; the strictest value in between
    # keeps a file another thread makes meanwhile private.
    umask = os.umask(0o077)
    os.umask(umask)
    return umask


def umask_problem(
    umask: int,
    st: os.stat_result,
    uid: int,
    private_gid: Callable[[int], int | None] = _no_private_groups,
) -> str | None:
    """What the files diskcache adds to this directory would be writable by.

    diskcache adds value directories and files (modes 0o777 and 0o666 less
    the umask) after the guard has run, so the umask must not let other
    accounts write them. SQLite's files never get more than cache.db's 0o644.
    """
    if not umask & stat.S_IWOTH:
        return f"every account under your umask {umask:03o}"
    gid = _new_entry_gid(st)
    if not umask & stat.S_IWGRP and gid != private_gid(uid):
        return f"{_group(gid)} under your umask {umask:03o}"
    return None


def _open_directory(
    name: str, dir_fd: int | None, display: str, *, search_ok: bool
) -> tuple[int, bool]:
    """Open a directory without following a symlink; return (fd, readable)."""
    try:
        try:
            return os.open(name, _DIRECTORY_FLAGS, dir_fd=dir_fd), True
        except PermissionError:
            if not (search_ok and _SEARCH_FLAGS):
                raise
            flags = _SEARCH_FLAGS | (_DIRECTORY_FLAGS & ~os.O_RDONLY)
            return os.open(name, flags, dir_fd=dir_fd), False
    except OSError as error:
        raise CacheDirError(
            f"Can't check {display} for the LiteLLM disk cache: {error.strerror}."
        ) from error


def _open_checked_cache_dir(
    path: str, uid: int, private_gid: Callable[[int], int | None]
) -> int:
    """Open the cache directory, checking its ancestors from the root down.

    Each directory is opened relative to its parent's descriptor only after
    that parent has passed, so every check is of a directory reached through
    ones no other account can change, and the path diskcache later opens by
    name leads to the same directories.
    """
    names = [name for name in path.split(os.sep) if name]
    current = os.sep
    fd, readable = _open_directory(current, None, current, search_ok=bool(names))
    try:
        for index, name in enumerate(names):
            st = os.fstat(fd)
            problem = parent_problem(st, uid, private_gid) or _acl_problem(
                fd, readable, st, uid, private_gid, inherited_too=False
            )
            if problem:
                raise _unsafe(path, f"its parent directory {current} {problem}")
            current = os.path.join(current, name)
            # The cache directory itself must be listable.
            child, readable = _open_directory(
                name, fd, current, search_ok=index < len(names) - 1
            )
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _contents_problem(
    cache_fd: int,
    path: str,
    uid: int,
    private_gid: Callable[[int], int | None],
    umask: int,
) -> str | None:
    """Why another account could write an entry inside the cache, or one
    diskcache adds to a directory in it.

    Covers cache.db and the files SQLite keeps beside it, and the hex
    subdirectories and .val files diskcache stores large values in. diskcache
    makes nothing else, so a symlink (which SQLite would follow) or any other
    kind of entry is refused rather than opened.
    """
    pending = [("", os.dup(cache_fd))]
    entry = ""
    try:
        while pending:
            directory, dir_fd = pending.pop()
            entry = directory
            try:
                with os.scandir(dir_fd) as listing:
                    names = sorted(item.name for item in listing)
                for name in names:
                    entry = os.path.join(directory, name)
                    try:
                        st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
                        if stat.S_ISLNK(st.st_mode):
                            return f"its {entry} is a symlink"
                        is_dir = stat.S_ISDIR(st.st_mode)
                        if not (is_dir or stat.S_ISREG(st.st_mode)):
                            return f"its {entry} is not a file or a directory"
                        flags = _DIRECTORY_FLAGS if is_dir else _FILE_FLAGS
                        fd = os.open(name, flags, dir_fd=dir_fd)
                    except FileNotFoundError:
                        # A concurrent run sharing the cache can delete a value
                        # file or its directory (diskcache culls past its size
                        # limit).
                        continue
                    try:
                        # Judge what was opened.
                        opened = os.fstat(fd)
                        if stat.S_IFMT(opened.st_mode) != stat.S_IFMT(st.st_mode):
                            raise _changed(path)
                        problem = cache_problem(
                            opened, uid, private_gid
                        ) or _acl_problem(
                            fd, True, opened, uid, private_gid, inherited_too=is_dir
                        )
                        if problem:
                            return f"its {entry} {problem}"
                        if is_dir:
                            writers = umask_problem(umask, opened, uid, private_gid)
                            if writers:
                                return (
                                    f"the files diskcache adds to its {entry} "
                                    f"would be writable by {writers}"
                                )
                            pending.append((entry, fd))
                            fd = None
                    finally:
                        if fd is not None:
                            os.close(fd)
            finally:
                os.close(dir_fd)
    except CacheDirError:
        raise
    except OSError as error:
        raise CacheDirError(
            f"Can't check {os.path.join(path, entry)} in the LiteLLM disk cache: "
            f"{error.strerror}."
        ) from error
    finally:
        for _, dir_fd in pending:
            os.close(dir_fd)
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
    or anything in it (by ownership, mode bits or ACL), could swap the
    directory out of a parent, or could write the files diskcache adds under
    the process umask; and CacheDirError when the path can't be used at all.
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
    if not stat.S_ISDIR(os.lstat(path).st_mode):
        raise CacheDirError(
            f"Can't use {path} as the LiteLLM disk cache: it is not a directory."
        )

    getuid = getattr(os, "getuid", None)
    if getuid is None:
        # Windows has no POSIX owners, and os.stat reports every writable
        # directory there as mode 0o777, so neither check means anything.
        return path
    uid = getuid()
    private_gid = functools.cache(user_private_gid)
    umask = process_umask()

    try:
        fd = _open_checked_cache_dir(path, uid, private_gid)
        try:
            st = os.fstat(fd)
            problem = cache_problem(st, uid, private_gid) or _acl_problem(
                fd, True, st, uid, private_gid, inherited_too=True
            )
            if problem:
                raise _unsafe(path, f"it {problem}")
            writers = umask_problem(umask, st, uid, private_gid)
            if writers:
                raise _unsafe(
                    path,
                    f"the files diskcache adds to it would be writable by {writers}",
                )
            problem = _contents_problem(fd, path, uid, private_gid, umask)
            if problem:
                raise _unsafe(path, problem)
            # The checked directories can't be changed by another account, so
            # this only catches the user's own concurrent change.
            if not os.path.samestat(st, os.stat(path)):
                raise _changed(path)
        finally:
            os.close(fd)
    except OSError as error:
        raise CacheDirError(
            f"Can't check {path} for the LiteLLM disk cache: {error.strerror}."
        ) from error
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
