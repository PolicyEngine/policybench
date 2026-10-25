"""The paper render environment stays free of Jupyter Book's server stack.

The ``docs`` extra is the environment ``paper/render_paper.py`` and the Paper
workflow render the manuscript in. Quarto's Jupyter engine runs the notebook
through nbclient and nbformat on the ipykernel ``python3`` kernel; it never
imports jupyter-book, or the jupyter-server and nbconvert stack behind it.
jupyter-book builds only the docs/ site, from docs/requirements.txt, so it stays
out of uv.lock: Dependabot scans every locked package, whichever extra pulls it
in, and that stack brought bleach, mistune and soupsieve alerts with it.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER_KERNEL = {"ipykernel", "nbclient", "nbformat"}
DOCS_SITE_STACK = {"jupyter-book", "jupyter-server", "nbconvert"}


def _name(requirement: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
    assert match, requirement
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def _extras() -> dict[str, set[str]]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    return {
        extra: {_name(requirement) for requirement in requirements}
        for extra, requirements in project["optional-dependencies"].items()
    }


def test_docs_extra_holds_the_render_kernel():
    assert RENDER_KERNEL <= _extras()["docs"]


def test_no_extra_declares_the_docs_site_stack():
    for extra, names in _extras().items():
        assert not names & DOCS_SITE_STACK, extra


def test_docs_site_stack_is_not_locked():
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    locked = {package["name"] for package in lock["package"]}
    assert not locked & DOCS_SITE_STACK


def _requirement_names(text: str) -> set[str]:
    """Package names in a requirements file, read the way pip reads it: a #
    at a line's start or after whitespace starts a comment, and a line
    starting with - is an option."""
    lines = (re.sub(r"(^|\s)#.*$", "", line).strip() for line in text.splitlines())
    return {_name(line) for line in lines if line and not line.startswith("-")}


def test_requirement_names_skip_comments_and_options():
    text = "# top\n  # indented\n\n--index-url https://x\nfoo>=1  # why\nBar_Baz\n"
    assert _requirement_names(text) == {"foo", "bar-baz"}


def test_docs_site_requirements_declare_jupyter_book():
    text = (ROOT / "docs" / "requirements.txt").read_text()
    assert "jupyter-book" in _requirement_names(text)
