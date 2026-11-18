"""Write policybench_calculator/core.py from scripts/tool_pilot_argon.py.

    python scripts/sync_calculator_core.py          rewrite core.py
    python scripts/sync_calculator_core.py --check  exit 1 if core.py is stale

The tool pilot's harness holds the calculator (the tool a model is given) in
one script with the code that calls models. ``policybench_calculator.core`` is
the calculator alone, for anything else that offers it (the MCP server). The
v2 confirmatory runner pins the harness to its treatment commit
(``scripts/confirmatory_run.py``, ``TREATMENT_PATHS``), so the harness cannot
import the package yet; until it can, this script keeps the package's copy
exact.

The copy is the dependency closure of ``ENTRY_POINTS`` among the harness's
module-level statements, in the harness's order: each statement's source
lines byte for byte, with the comment block directly above it. The closure
comes from Python's own symbol tables, so a name counts only where a scope
reads it as a global, and a local variable that shares a module-level name
pulls nothing in.

Run it after any change to the harness that the closure reaches (the
calculator itself, or the v2-pilot wording the labels feature reads);
``tests/test_calculator_core.py`` fails until core.py is current.
"""

from __future__ import annotations

import ast
import builtins
import symtable
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts/tool_pilot_argon.py"
CORE = ROOT / "policybench_calculator/core.py"

# What a server or a harness needs to offer the calculator; everything else in
# core.py is there because one of these reads it.
ENTRY_POINTS = (
    "TOOL_NAME",
    "TOOL_TIMEOUT_SECONDS",
    "TOOL_FEATURES",
    "arm_features",
    "calculate_tool_schema",
    "set_stated_engine",
    "stating_engine",
    "engine_text",
    "build_registry",
    "normalize_request",
    "execute_request",
    "build_tool_system",
    "board_engine",
    "_require_engine",
    "tool_call_frame",
    "frame_features",
    "worker_request",
    "_worker_main",
    "ToolPool",
)
# Names every module has.
MODULE_NAMES = frozenset({"__file__", "__name__"})

HEADER = '''"""The household calculator the PolicyBench tool pilot gives a model.

Written by ``scripts/sync_calculator_core.py``; do not edit it by hand.

This module is a verbatim copy of the calculator inside
``scripts/tool_pilot_argon.py``: the tool's schema and descriptions for each
feature set, the validator (names, labels, placement, overrides, the flat
household), the engine call, the explanations, the board's pinned engine and
convention reform, and the worker pool that runs each call in its own process
under a timeout. Nothing here calls a model.

Why a copy. The v2 confirmatory runner refuses to start unless
``scripts/tool_pilot_argon.py`` and the ``policybench`` package are its
treatment commit's (``scripts/confirmatory_run.py``, ``TREATMENT_PATHS``), so
the harness cannot import this module until that run is over. Until then both
hold the same code. ``tests/test_calculator_core.py`` fails if this file is
not the sync script's output for the harness as it stands, if any definition
here differs from the harness's (compared by AST), or if the two build
different tool schemas or read a call differently. To change the calculator,
change the harness and run the sync script; once the treatment pin is lifted,
the harness imports this module and its own copy goes.

Everything below the imports is the harness's text, in the harness's order.
"""
'''

IMPORTS = """from __future__ import annotations

import contextlib
import copy
import difflib
import functools
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import multiprocessing as mp
import os
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
"""

DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def statement_names(node: ast.stmt) -> list[str]:
    """The module-level names a definition or an assignment binds."""
    if isinstance(node, DEFINITIONS):
        return [node.name]
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        return []
    return [n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)]


def imported_names(tree: ast.Module) -> set[str]:
    return {
        (alias.asname or alias.name).split(".")[0]
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }


def _loads(node: ast.AST) -> set[str]:
    return {
        n.id
        for n in ast.walk(node)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }


def _global_reads(table: symtable.SymbolTable) -> set[str]:
    """Every name a scope, or a scope nested in it, reads as a global."""
    names = {
        symbol.get_name()
        for symbol in table.get_symbols()
        if symbol.is_global() and symbol.is_referenced()
    }
    for child in table.get_children():
        names |= _global_reads(child)
    return names


def statement_reads(node: ast.stmt, module_table: symtable.SymbolTable) -> set[str]:
    """The module-level names a statement reads."""
    if isinstance(node, DEFINITIONS):
        tables = [
            child
            for child in module_table.get_children()
            if child.get_name() == node.name and child.get_lineno() == node.lineno
        ]
        if len(tables) != 1:
            raise SystemExit(f"no single symbol table for {node.name}")
        reads = _global_reads(tables[0])
        # Decorators, bases and argument defaults are read in module scope.
        outside = list(node.decorator_list)
        if isinstance(node, ast.ClassDef):
            outside += [*node.bases, *(k.value for k in node.keywords)]
        else:
            outside += [*node.args.defaults, *(d for d in node.args.kw_defaults if d)]
        for expression in outside:
            reads |= _loads(expression)
        return reads
    # An assignment: the names it loads, less a comprehension's or a lambda's
    # own variables.
    own = {
        n.id
        for inner in ast.walk(node)
        if isinstance(inner, ast.comprehension)
        for n in ast.walk(inner.target)
        if isinstance(n, ast.Name)
    }
    own |= {
        argument.arg
        for inner in ast.walk(node)
        if isinstance(inner, ast.Lambda)
        for argument in ast.walk(inner.args)
        if isinstance(argument, ast.arg)
    }
    return _loads(node) - own


def closure(source: str) -> list[ast.stmt]:
    """The harness statements the entry points need, in the harness's order."""
    tree = ast.parse(source)
    module_table = symtable.symtable(source, HARNESS.name, "exec")
    imported = imported_names(tree)
    by_name: dict[str, ast.stmt] = {}
    for node in tree.body:
        for name in statement_names(node):
            if name in by_name:
                raise SystemExit(f"{name} is defined twice at module level")
            by_name[name] = node
    missing = [name for name in ENTRY_POINTS if name not in by_name]
    if missing:
        raise SystemExit(f"entry points not in the harness: {missing}")
    wanted: set[int] = set()
    seen: set[str] = set()
    unresolved: set[str] = set()
    stack = list(ENTRY_POINTS)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        node = by_name[name]
        wanted.add(id(node))
        for read in statement_reads(node, module_table):
            if read in by_name:
                stack.append(read)
            elif (
                read not in imported
                and not hasattr(builtins, read)
                and read not in MODULE_NAMES
            ):
                unresolved.add(read)
    if unresolved:
        raise SystemExit(f"names the closure reads but nothing defines: {unresolved}")
    return [node for node in tree.body if id(node) in wanted]


def _span(lines: list[str], node: ast.stmt) -> tuple[int, int]:
    """A statement's 1-based lines, from its first decorator, extended up over
    the comment lines directly above it."""
    start = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))])
    while start > 1 and lines[start - 2].lstrip().startswith("#"):
        start -= 1
    return start, node.end_lineno


def render(source: str) -> str:
    """core.py's text for a harness source."""
    lines = source.splitlines()
    parts = [HEADER, "\n", IMPORTS]
    previous_end, previous_was_definition = None, False
    for node in closure(source):
        start, end = _span(lines, node)
        definition = isinstance(node, DEFINITIONS)
        if previous_end is None:
            gap = "\n"
        else:
            between = lines[previous_end : start - 1]
            if all(not text.strip() for text in between):
                # Neighbours in the harness keep the harness's spacing.
                gap = "\n" * len(between)
            else:
                gap = "\n\n" if definition or previous_was_definition else "\n"
        parts.append(gap + "\n".join(lines[start - 1 : end]) + "\n")
        previous_end, previous_was_definition = end, definition
    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    text = render(HARNESS.read_text())
    if "--check" in argv:
        if not CORE.exists() or CORE.read_text() != text:
            print(
                f"{CORE.relative_to(ROOT)} is not the calculator in "
                f"{HARNESS.relative_to(ROOT)}; run scripts/sync_calculator_core.py"
            )
            return 1
        return 0
    CORE.write_text(text)
    print(f"wrote {CORE.relative_to(ROOT)}: {len(text.splitlines())} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
