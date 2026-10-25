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

import pytest
from packaging.requirements import InvalidRequirement, Requirement

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


# What pip's requirements-file reader (pip/_internal/req/req_file.py) does to
# each line before parsing it: a line ending in a backslash continues on the
# next, unless it is a comment; a # at a line's start or after whitespace
# starts a comment; and a token starting with - begins the line's options.
_COMMENT = re.compile(r"(^|\s+)#.*$")
_ARCHIVE = (".whl", ".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tar.xz", ".tar")


def _logical_lines(text: str) -> list[str]:
    lines, pending = [], []
    for line in text.splitlines():
        if line.endswith("\\") and not _COMMENT.match(line):
            pending.append(line.strip("\\"))
            continue
        lines.append("".join([*pending, " " + line if _COMMENT.match(line) else line]))
        pending = []
    if pending:
        lines.append("".join(pending))
    return [stripped for line in lines if (stripped := _COMMENT.sub("", line).strip())]


def _requirement_names(path: Path) -> set[str]:
    """Names of the packages a requirements file asks pip to install.

    It follows -r includes, relative to the including file as pip resolves
    them, and skips -c constraints and other options, which install nothing.
    A requirement it can't name without fetching it (a bare URL or path, or an
    -e editable install) fails the test rather than being guessed at.
    """
    names = set()
    for line in _logical_lines(path.read_text()):
        include = re.match(r"(?:-r|--requirement)(?:\s+|=)?(\S+)$", line)
        if include:
            names |= _requirement_names(path.parent / include.group(1))
            continue
        if line.startswith("-"):
            assert not line.startswith(("-e", "--editable")), f"unnamed: {line}"
            continue
        arguments = []
        for token in line.split(" "):
            if token.startswith("-"):
                break
            arguments.append(token)
        requirement = Requirement(" ".join(arguments))
        assert not requirement.name.endswith(_ARCHIVE), f"a path, unnamed: {line}"
        names.add(_name(requirement.name))
    return names


def test_requirement_names_read_requirements_files_as_pip_does(tmp_path):
    (tmp_path / "base.txt").write_text("Included_Pkg\n-c constraints.txt\n")
    (tmp_path / "requirements.txt").write_text(
        "# top\n"
        "  # indented\n"
        "\n"
        "--index-url https://example.com/simple\n"
        "foo>=1  # why\n"
        "Bar_Baz[extra] ; python_version >= '3.12'\n"
        "named @ https://example.com/named-1.0.tar.gz#sha256=00\n"
        "hashed==1.0 --hash=sha256:00\n"
        "continued \\\n"
        "    >=2\n"
        "-r base.txt\n"
    )
    assert _requirement_names(tmp_path / "requirements.txt") == {
        "foo",
        "bar-baz",
        "named",
        "hashed",
        "continued",
        "included-pkg",
    }


@pytest.mark.parametrize(
    "line",
    [
        "https://example.com/pkg-1.0-py3-none-any.whl",
        "./vendor/pkg-1.0.tar.gz",
        "pkg-1.0-py3-none-any.whl",
        "-e ./local",
        "git+https://example.com/pkg.git",
    ],
)
def test_requirement_names_refuse_requirements_they_cant_name(tmp_path, line):
    (tmp_path / "requirements.txt").write_text(line + "\n")
    with pytest.raises((AssertionError, InvalidRequirement)):
        _requirement_names(tmp_path / "requirements.txt")


def test_docs_site_requirements_declare_jupyter_book():
    assert "jupyter-book" in _requirement_names(ROOT / "docs" / "requirements.txt")
