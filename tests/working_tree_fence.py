"""An audit hook that fails any open of the working tree's copy of a pinned input.

tests/test_reference_adversary_inputs.py arms it in-process around the
reference adversary's scripts, and in every process of a script it runs as a
subprocess, worker processes included: ``sitecustomize(directory)`` writes a
``sitecustomize.py`` that loads this file and calls ``install_from_env()``, so
putting ``directory`` first on PYTHONPATH and the fence's JSON in ``ENV`` arms
each interpreter as it starts.

``exempt`` maps a forbidden file to the one directory whose code may open it:
policybench reads its own ``benchmark_specs.json`` (package data, which the
scripts treat as code), while a script that opened that file itself would trip
the fence.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ENV = "REFERENCE_ADVERSARY_FENCE"
_STATE: dict = {"forbidden": (), "exempt": {}, "root": ""}
_INSTALLED = False


def _innermost_repository_frame() -> str:
    """The file of the innermost calling frame that is repository code."""
    root = _STATE["root"] + os.sep
    frame = sys._getframe(2)
    while frame is not None:
        name = os.path.abspath(frame.f_code.co_filename)
        if name.startswith(root) and f"{os.sep}.venv{os.sep}" not in name:
            return name
        frame = frame.f_back
    return ""


def _hook(event: str, args: tuple) -> None:
    if event != "open" or not _STATE["forbidden"]:
        return
    target = args[0]
    if not isinstance(target, (str, bytes, os.PathLike)):
        return
    path = os.path.abspath(os.fsdecode(target))
    if not any(
        path == forbidden or path.startswith(forbidden + os.sep)
        for forbidden in _STATE["forbidden"]
    ):
        return
    owner = _STATE["exempt"].get(path)
    if owner and _innermost_repository_frame().startswith(owner + os.sep):
        return
    raise PermissionError(f"opened the working tree's {path}")


def arm(forbidden, exempt: dict[str, str], root: str) -> None:
    global _INSTALLED
    if not _INSTALLED:
        sys.addaudithook(_hook)
        _INSTALLED = True
    _STATE.update(
        forbidden=tuple(os.path.abspath(path) for path in forbidden),
        exempt={os.path.abspath(k): os.path.abspath(v) for k, v in exempt.items()},
        root=os.path.abspath(root),
    )


def disarm() -> None:
    _STATE["forbidden"] = ()


def install_from_env() -> None:
    fence = os.environ.get(ENV)
    if fence:
        arm(**json.loads(fence))


def sitecustomize(directory: Path) -> Path:
    """Write a sitecustomize.py into ``directory`` that arms the fence from ENV."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "sitecustomize.py").write_text(
        "import importlib.util\n"
        'spec = importlib.util.spec_from_file_location("working_tree_fence", '
        f"{str(Path(__file__).resolve())!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "module.install_from_env()\n"
    )
    return directory
