"""The local files an audited fix module loads.

A fix module in ``reference_audit/2026-09-22/fixes`` can load a sibling file,
which then runs (or is read) with it, so a pin on the module must also pin
everything it loads. The one supported loader is
``Path(__file__).with_name("<file>")`` with a literal file name. A module that
reaches local files another way has a closure these gates cannot establish,
so it is refused rather than pinned short. The other ways are:

- another use of ``__file__`` (``Path(__file__).resolve().parent / f"{name}.py"``);
- a file name given outside that call (``open("x.json")``, ``_HERE / "x.py"``);
- ``sys.path``, ``runpy``, ``importlib.import_module``, ``__import__``, a
  file loader class, ``os.chdir``, or the ``exec``/``eval``/``compile``
  builtins;
- listing a directory (``glob``, ``rglob``, ``iterdir``, ``listdir``,
  ``scandir``, ``walk``), which turns a pattern into files no literal names;
- reaching the module's own location another way (``__spec__``,
  ``__loader__``, an attribute ``.__file__`` such as
  ``sys.modules[__name__].__file__``, ``inspect``, ``globals()``, ``vars()``);
- importing this repository's own package (``policybench``), whose code no
  fix-module pin covers.

The builder (``reference_audit/2026-10-09-engine-upgrade/scripts/
build_references_upgrade.py``) and the release driver
(``scripts/finish_haiku55.py``) both derive a target's pinned siblings here,
from the committed bytes.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable

# A literal sibling file name: no directory part.
SIBLING = re.compile(r"^[A-Za-z0-9_.\-]+\.[A-Za-z0-9]+$")
# A string constant that names a local file.
FILE_NAME = re.compile(
    r"^[\w.\-/]*\.(py|pyc|json|csv|tsv|ya?ml|toml|txt|pkl|pickle|parquet|h5|npz|npy)$",
    re.IGNORECASE,
)
# Builtins that run or load code a static read cannot follow.
BANNED_BUILTINS = frozenset(
    {"__import__", "exec", "eval", "compile", "globals", "vars"}
)
# Names, as a bare name or an attribute, that load code or move the paths
# local files resolve against.
BANNED_NAMES = frozenset(
    {
        "import_module",
        "run_path",
        "run_module",
        "runpy",
        "SourceFileLoader",
        "SourcelessFileLoader",
        "ExtensionFileLoader",
        "chdir",
        "getfile",
        "getsourcefile",
        "glob",
        "rglob",
        "iterdir",
        "listdir",
        "scandir",
        "walk",
        "__spec__",
        "__loader__",
    }
)
# Modules whose import reaches code or files a fix-module pin does not cover:
# runpy runs other files, inspect finds them, and policybench is this
# repository's own package.
BANNED_IMPORTS = frozenset({"runpy", "inspect", "policybench"})


class ClosureError(ValueError):
    """A fix module whose local dependency closure cannot be established."""


def _docstrings(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(id(body[0].value))
    return found


def _is_path_call(node: ast.AST) -> bool:
    func = node.func if isinstance(node, ast.Call) else None
    return (isinstance(func, ast.Name) and func.id == "Path") or (
        isinstance(func, ast.Attribute) and func.attr == "Path"
    )


def direct_dependencies(text: str, name: str = "<module>") -> list[str]:
    """The sibling files one fix module's source loads, in source order.
    Raises ClosureError when the module reaches local files any other way."""
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        raise ClosureError(f"{name} does not parse: {error}") from None
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    docstrings = _docstrings(tree)
    literals: set[int] = set()
    found: list[tuple[int, int, str]] = []
    problems: list[str] = []

    def at(node) -> str:
        return f"{name}:{getattr(node, 'lineno', '?')}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "__file__":
            call = parents.get(id(node))
            attr = parents.get(id(call)) if call is not None else None
            outer = parents.get(id(attr)) if attr is not None else None
            if not (
                _is_path_call(call)
                and call.args == [node]
                and not call.keywords
                and isinstance(attr, ast.Attribute)
                and attr.value is call
                and attr.attr == "with_name"
                and isinstance(outer, ast.Call)
                and outer.func is attr
                and len(outer.args) == 1
                and not outer.keywords
                and isinstance(outer.args[0], ast.Constant)
                and isinstance(outer.args[0].value, str)
                and SIBLING.match(outer.args[0].value)
                and ".." not in outer.args[0].value
            ):
                problems.append(
                    f"{at(node)} uses __file__ other than as "
                    'Path(__file__).with_name("<file>")'
                )
                continue
            literal = outer.args[0]
            literals.add(id(literal))
            found.append((literal.lineno, literal.col_offset, literal.value))
        elif isinstance(node, ast.Name) and node.id in BANNED_BUILTINS:
            problems.append(f"{at(node)} calls {node.id}")
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            problems.append(f"{at(node)} uses {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in BANNED_NAMES:
            problems.append(f"{at(node)} uses .{node.attr}")
        elif isinstance(node, ast.Attribute) and node.attr == "__file__":
            problems.append(f"{at(node)} uses .__file__ of another object")
        elif (
            isinstance(node, ast.Attribute)
            and node.attr == "path"
            and isinstance(node.value, ast.Name)
            and node.value.id == "sys"
        ):
            problems.append(f"{at(node)} uses sys.path")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            imported = {alias.name for alias in node.names}
            if any(m.split(".")[0] in BANNED_IMPORTS for m in modules) or (
                isinstance(node, ast.ImportFrom) and node.level
            ):
                problems.append(
                    f"{at(node)} imports {modules} relatively or from "
                    f"{sorted(BANNED_IMPORTS)}"
                )
            elif isinstance(node, ast.ImportFrom) and (
                banned := imported & (BANNED_NAMES | BANNED_BUILTINS)
            ):
                problems.append(f"{at(node)} imports {sorted(banned)}")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in literals
            and id(node) not in docstrings
            and FILE_NAME.match(node.value.strip())
        ):
            problems.append(
                f"{at(node)} names the file {node.value!r} outside "
                'Path(__file__).with_name("<file>")'
            )
    if problems:
        raise ClosureError(
            f"the local files {name} loads cannot be established: {'; '.join(problems)}"
        )
    ordered: list[str] = []
    for _, _, literal in sorted(found):
        if literal not in ordered:
            ordered.append(literal)
    return ordered


def dependency_closure(name: str, read: Callable[[str], bytes]) -> list[str]:
    """Every sibling file the named fix module loads, transitively, in
    discovery order, without the module itself; ``read(file)`` gives a file's
    bytes (as committed). A loaded Python file is followed in turn; any other
    file (a JSON table) is a leaf. Raises ClosureError for a module whose
    closure cannot be established."""
    found: list[str] = []
    queue = [name] if name.endswith(".py") else []
    while queue:
        current = queue.pop(0)
        for dep in direct_dependencies(read(current).decode(), current):
            if dep != name and dep not in found:
                found.append(dep)
                if dep.endswith(".py"):
                    queue.append(dep)
    return found
