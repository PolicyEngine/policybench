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

import codecs
import os
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


# The line forms _requirement_names reads. pip (req_file.py and
# req/constructors.py) and uv, which builds the docs site, read each of them
# the same way; any other line fails the test rather than being guessed at.
# Elsewhere they differ: on continuation lines, -r spellings, archive-like
# versions, encoding declarations, include cycles and includes through a
# symlinked directory, and uv 0.11 rejects a trailing comma that pip and
# later uv accept. A false marker makes both quietly install nothing. So a
# guess could hide jupyter-book from one or both.
#   - blank lines and comments: a # at a line's start or after whitespace,
#     except a PEP 263 encoding line among a file's first two, which pip
#     applies to the whole file;
#   - includes: -r FILE, --requirement FILE or --requirement=FILE, resolved
#     relative to the including file, with no cycle and no .. after a
#     symlinked directory;
#   - requirements: a name, optional extras and version specifiers with no
#     trailing comma; no URL, path, marker, archive name or per-requirement
#     option.
# Every file is UTF-8 with no byte-order mark.
_COMMENT = re.compile(r"(^|\s+)#.*$")
_INCLUDE = re.compile(
    r"(?:-r\s+|--requirement(?:\s+|=))([A-Za-z0-9._/][A-Za-z0-9._/-]*)"
)
# pip decodes a file by its byte-order mark, or else by a PEP 263 line among
# its first two that starts with # (_decode_req_file in req_file.py). The
# UTF-16 and UTF-32 marks aren't valid UTF-8, so only UTF-8's needs a check.
_PEP263 = re.compile(rb"coding[:=]\s*([-\w.]+)")
# pip's archive extensions (pip/_internal/utils/filetypes.py), which it
# compares case-insensitively, after stripping extras, to decide that a line
# names a file rather than a project.
_ARCHIVE = (".zip", ".whl", ".tar.bz2", ".tbz", ".tar.gz", ".tgz", ".tar")
_ARCHIVE += (".tar.xz", ".txz", ".tlz", ".tar.lz", ".tar.lzma")


def _requirement_names(path: Path, _including: tuple[str, ...] = ()) -> set[str]:
    """Names of the packages a requirements file asks pip and uv to install,
    following its includes. A line outside the forms above fails the test."""
    real = os.path.realpath(path)
    assert real not in _including, f"an include cycle: {path}"
    data = path.read_bytes()
    assert not data.startswith(codecs.BOM_UTF8), f"a byte-order mark: {path.name}"
    for first in data.split(b"\n")[:2]:
        assert not (first[:1] == b"#" and _PEP263.search(first)), (
            f"an encoding declaration: {path.name}: {first!r}"
        )
    try:
        # Decoded from bytes, so a lone carriage return isn't a line break.
        text = data.decode()
    except UnicodeDecodeError:
        raise AssertionError(f"not UTF-8: {path.name}") from None
    names = set()
    for number, raw in enumerate(text.split("\n"), 1):
        raw = raw.removesuffix("\r")
        where = f"{path.name}:{number}: {raw!r}"
        assert all(c in " \t" for c in raw if c.isspace()), (
            f"whitespace other than spaces and tabs: {where}"
        )
        assert not raw.endswith("\\"), f"a continuation line: {where}"
        line = _COMMENT.sub("", raw).strip()
        if not line:
            continue
        include = _INCLUDE.fullmatch(line)
        if include:
            target = path.parent / include.group(1)
            # pip collapses .. before opening the file (os.path.abspath),
            # while opening it follows a symlink before applying the ..
            lexical = os.path.realpath(os.path.normpath(target))
            assert os.path.realpath(target) == lexical, (
                f"an include whose .. crosses a symlink: {where}"
            )
            names |= _requirement_names(target, (*_including, real))
            continue
        assert not line.startswith("-"), f"an option: {where}"
        assert not re.search(r"\s-", line), f"a per-requirement option: {where}"
        assert not re.search(r"[@:/\\]", line), f"a URL or path: {where}"
        assert ";" not in line, f"a marker: {where}"
        assert "===" not in line, f"arbitrary equality: {where}"
        assert not re.search(r",\s*\)?$", line), f"a trailing comma: {where}"
        stem = re.sub(r"\s*\[[^\]]+\]$", "", line).lower()
        assert not stem.endswith(_ARCHIVE), f"an archive name: {where}"
        requirement = Requirement(line)
        assert requirement.url is None and requirement.marker is None, where
        names.add(_name(requirement.name))
    return names


def test_requirement_names_read_the_forms_pip_and_uv_agree_on(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "base.txt").write_text("Included_Pkg\n")
    (tmp_path / "sub" / "more.txt").write_text("-r ../deep.txt\n")
    (tmp_path / "deep.txt").write_text("deep\n")
    (tmp_path / "other.txt").write_text("other\r\n")
    (tmp_path / "requirements.txt").write_text(
        "# top\n"
        "  # indented\n"
        "\n"
        "foo>=1  # why\n"
        "Bar_Baz[extra]\n"
        "spaced >= 1.0, < 3\n"
        "\tTabbed==1.0\t# a tab before the comment\n"
        "-r base.txt\n"
        "--requirement sub/more.txt\n"
        "--requirement=other.txt\n"
    )
    assert _requirement_names(tmp_path / "requirements.txt") == {
        "foo",
        "bar-baz",
        "spaced",
        "tabbed",
        "included-pkg",
        "deep",
        "other",
    }


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("jupyter-book>=2.0 \\\n    --hash=sha256:00\n", "a continuation line"),
        ("jupyter-book \\\n>=2.0\n", "a continuation line"),
        # pip joins the next line onto a comment that doesn't start the line.
        ("foo  # see below \\\njupyter-book\n", "a continuation line"),
        ("jupyter-book\x0c>=2.0\n", "whitespace other than"),
        ("jupyter-book>=2.0\xa0# note\n", "whitespace other than"),
        ("jupyter-book>=2.0\rfoo\n", "whitespace other than"),
        # pip decodes the file as UTF-7, so "+AFw" is a backslash that joins the
        # jupyter-book line into the comment before it.
        ("# coding: utf-7\nfoo  # x+AFw\njupyter-book\n", "an encoding declaration"),
        (
            "# Docs site; no coding=needed\njupyter-book>=2.0\n",
            "an encoding declaration",
        ),
        ("\n# coding: utf-16\njupyter-book\n", "an encoding declaration"),
        ("\ufeffjupyter-book\n", "a byte-order mark"),
        (b"jupyter-book  # caf\xe9\n", "not UTF-8"),
        ("jupyter-book\n".encode("utf-16"), "not UTF-8"),
        ("jupyter-book\n".encode("utf-32"), "not UTF-8"),
        ("-r requirements.txt\n", "an include cycle"),
        ("-r=base.txt\n", "an option"),  # pip opens "=base.txt"; uv, base.txt
        ("-rbase.txt\n", "an option"),
        ("--requirementbase.txt\n", "an option"),
        ("--requirements=base.txt\n", "an option"),
        ("--requirem base.txt\n", "an option"),
        ('-r "base.txt"\n', "an option"),
        ("-r base.txt --pre\n", "an option"),
        ("-r base.txt -r other.txt\n", "an option"),
        ("-r ${DIR}/base.txt\n", "an option"),
        ("-r https://example.com/base.txt\n", "an option"),
        ("-c base.txt\n", "an option"),
        ("-e ./local\n", "an option"),
        ("--editable=./local\n", "an option"),
        ("--edit ./local\n", "an option"),
        ("--pre -e ./local\n", "an option"),
        ("--index-url https://example.com/simple\n", "an option"),
        ("https://example.com/pkg-1.0-py3-none-any.whl\n", "a URL or path"),
        ("git+https://example.com/pkg.git\n", "a URL or path"),
        ("./vendor/pkg-1.0.tar.gz\n", "a URL or path"),
        ("named @ https://example.com/named-1.0.tar.gz\n", "a URL or path"),
        (
            "jupyter-book @ https://h.example/p;v=1/jupyter_book-2.1.7-py3-none-any.whl\n",
            "a URL",
        ),
        ('jupyter-book>=2.0 ; python_version < "3"\n', "a marker"),
        ("jupyter-book>=2.0; extra == 'docs'\n", "a marker"),
        ("jupyter-book===2.0\n", "arbitrary equality"),
        ("jupyter-book===2.0.zip\n", "arbitrary equality"),
        ("jupyter-book>=2.0,\n", "a trailing comma"),
        ("jupyter-book (>=1, <3 , )  # x\n", "a trailing comma"),
        ("jupyter-book>=2.0 --hash=sha256:00\n", "a per-requirement option"),
        ("pkg-1.0-py3-none-any.whl\n", "an archive name"),
        ("PKG-1.0-py3-none-any.WHL\n", "an archive name"),
        ("jupyter-book.txz\n", "an archive name"),
        ("jupyter-book==2.0+local.zip\n", "an archive name"),
        ("jupyter-book.zip[docs]\n", "an archive name"),
        ("jupyter-book.zip [docs]\n", "an archive name"),
        # A naive comment rule would read this as "foo".
        ("foo#bar\n", None),
        ("${PKG}>=2.0\n", None),
    ],
)
def test_requirement_names_refuse_every_other_form(tmp_path, text, reason):
    (tmp_path / "base.txt").write_text("jupyter-book>=2.0\n")
    data = text if isinstance(text, bytes) else text.encode()
    (tmp_path / "requirements.txt").write_bytes(data)
    if reason is None:
        with pytest.raises(InvalidRequirement):
            _requirement_names(tmp_path / "requirements.txt")
    else:
        with pytest.raises(AssertionError, match=re.escape(reason)):
            _requirement_names(tmp_path / "requirements.txt")


def test_requirement_names_refuse_an_include_whose_dotdot_crosses_a_symlink(
    tmp_path,
):
    """pip opens -r sub/../base.txt as docs/base.txt; the OS follows sub first."""
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "more.txt").write_text("more\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "sub").symlink_to(tmp_path / "elsewhere")
    (tmp_path / "docs" / "base.txt").write_text("foo\n")
    (tmp_path / "base.txt").write_text("jupyter-book\n")
    requirements = tmp_path / "docs" / "requirements.txt"
    requirements.write_text("-r sub/more.txt\n")
    assert _requirement_names(requirements) == {"more"}
    requirements.write_text("-r sub/../base.txt\n")
    with pytest.raises(AssertionError, match="an include whose .. crosses a symlink"):
        _requirement_names(requirements)


def test_docs_site_requirements_declare_jupyter_book():
    assert "jupyter-book" in _requirement_names(ROOT / "docs" / "requirements.txt")
