"""Install commands in the docs must name a source that exists.

PolicyBench is not published on PyPI: on 2026-10-06 both
https://pypi.org/pypi/policybench/json and https://pypi.org/simple/policybench/
returned 404. A command that installs the ``policybench`` distribution from a
package index by name (``pip install policybench``, ``uvx policybench``) fails
today, and would install whatever a third party later uploads under the name.
The README installs from GitHub and the development docs from a clone; these
tests hold every surface a reader follows to that. If PolicyBench is ever
published to PyPI, delete this module with the README's "not published" line.
"""

import html
import re
import shlex
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["name"]
REPO_URL = "https://github.com/PolicyEngine/policybench"

# Where readers and agents look for install instructions. Dated records
# (docs/adds0928/, docs/gpt61sol/, reference_audit/) are left out: they quote
# what happened rather than tell anyone what to run.
SURFACES = (
    "*.md",
    "docs/*.md",
    "docs/requirements.txt",
    "paper/README.md",
    "paper/index.qmd",
    "app/public/paper/web/index.html",
    "sensitivity/*.md",
    "app/src/**/*.ts",
    "app/src/**/*.tsx",
    "app/src/notes/*.json",
    ".github/workflows/*.yml",
)

# Each installer and what its positional arguments are.
#   requirements: every positional argument is a requirement (pip install).
#   tool: the first positional names the tool's package, unless --from or
#     --spec names it, and later tokens are the tool's own arguments (uvx).
#   command: positionals are a command to run; only --with adds a package.
# `pip install` also matches inside `uv pip install` and `python -m pip install`.
INSTALLERS = (
    (re.compile(r"(?<![\w-])pip3?\s+install\b"), "requirements"),
    (re.compile(r"\bpipx\s+install\b"), "requirements"),
    (re.compile(r"\buv\s+(?:add|tool\s+install)\b"), "requirements"),
    (re.compile(r"\b(?:conda|mamba|micromamba)\s+install\b"), "requirements"),
    (re.compile(r"\b(?:poetry|pdm)\s+add\b"), "requirements"),
    (re.compile(r"\buvx\b|\buv\s+tool\s+run\b|\bpipx\s+run\b"), "tool"),
    (re.compile(r"\buv\s+run\b"), "command"),
)
# Options whose value is a requirement, and options whose value is anything
# else (a path, an index, a Python version, a channel) and is skipped.
REQUIREMENT_OPTIONS = {"--with", "--from", "--spec"}
VALUE_OPTIONS = {
    "-c",
    "-e",
    "-f",
    "-i",
    "-p",
    "-r",
    "-t",
    "--channel",
    "--constraint",
    "--editable",
    "--extra",
    "--extra-index-url",
    "--find-links",
    "--group",
    "--index",
    "--index-url",
    "--prefix",
    "--python",
    "--requirement",
    "--root",
    "--target",
    "--with-editable",
    "--with-requirements",
}
# What ends a command on its line: shell operators, an inline-code backtick,
# or the markup that follows a command embedded in a link, tag or string.
COMMAND_END = re.compile(r"[`;|&<>)]")
SENTENCE_END = ",.;:!?"


def _normalize(name: str) -> str:
    """PEP 503 name normalization."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _index_name(token: str) -> str | None:
    """The distribution ``token`` fetches from an index by name, if any.

    Paths, archives, URLs and PEP 508 direct references (``name @ url``) are
    not fetched from an index by name, so they return None.
    """
    if not token or token[0] in "-./~$" or "/" in token or "\\" in token:
        return None
    if token.startswith(("git+", "file:")) or "://" in token:
        return None
    if token.endswith((".whl", ".tar.gz", ".zip")):
        return None
    match = re.match(r"([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)(.*)$", token)
    if match is None:
        return None
    name, rest = match.groups()
    if re.match(r"(\[[^\]]*\])?\s*@\s*(git\+|file:|\w+://)", rest):
        return None
    return _normalize(name)


def _tokens(segment: str) -> list[str]:
    try:
        tokens = shlex.split(segment)
    except ValueError:  # an unbalanced quote, e.g. a command inside a JSON string
        tokens = segment.split()
    return [token.strip("'\"") for token in tokens]


def _scan(tokens: list[str], role: str) -> list[str]:
    """Distributions the installer's arguments fetch from an index by name."""
    names = []
    named_by_option = False
    i = 0
    while i < len(tokens):
        raw = tokens[i]
        token = raw if raw.startswith(".") else raw.rstrip(SENTENCE_END)
        # Prose after an inline command: "pip install uv, then clone the repo".
        ends_sentence = token != raw
        if token.startswith("-"):
            flag, has_value, value = token.partition("=")
            if flag in REQUIREMENT_OPTIONS:
                if not has_value and i + 1 < len(tokens):
                    i += 1
                    value = tokens[i]
                named_by_option = True
                names += [n for n in map(_index_name, value.split(",")) if n]
            elif flag in VALUE_OPTIONS and not has_value:
                i += 1
        elif role == "command" or (role == "tool" and named_by_option):
            break
        elif i + 1 < len(tokens) and tokens[i + 1].startswith("@"):
            # A PEP 508 direct reference split by spaces: "name @ url".
            i += 2 if tokens[i + 1] == "@" else 1
        else:
            name = _index_name(token)
            if name:
                names.append(name)
            if role == "tool":
                break
        if ends_sentence:
            break
        i += 1
    return names


def index_installs(text: str) -> list[str]:
    """Every distribution an install command in ``text`` fetches by name."""
    names = []
    for line in text.replace("\\\n", " ").splitlines():
        for pattern, role in INSTALLERS:
            for match in pattern.finditer(line):
                segment = COMMAND_END.split(line[match.end() :], maxsplit=1)[0]
                names += _scan(_tokens(segment), role)
    return names


def surface_installs(path: Path) -> list[str]:
    """Every distribution ``path`` fetches from an index by name."""
    text = path.read_text(encoding="utf-8")
    if path.name.endswith("requirements.txt"):
        # Each line of a requirements file is itself a requirement.
        lines = (line.split("#", 1)[0].strip() for line in text.splitlines())
        return [n for n in map(_index_name, lines) if n]
    if path.suffix == ".html":
        # Highlighted code splits a command across spans; read it as shown.
        text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return index_installs(text)


@pytest.mark.parametrize(
    "command",
    [
        "pip install policybench",
        "pip3 install -U policybench",
        "python -m pip install 'policybench[dev]>=2'",
        "uv pip install PolicyBench==2.0.0",
        "uv tool install --python 3.12 policybench",
        "uv add policybench",
        "pipx install policybench",
        "conda install -c conda-forge policybench",
        "pip install numpy policybench",
        "pip install policybench.",
        "uvx policybench --help",
        "uvx policybench@latest --help",
        "uv tool run policybench --help",
        "pipx run policybench",
        "uvx --with policybench python",
        "uv run --with numpy,policybench python",
        "uvx --from policybench policybench --help",
        "Run `pip install policybench` first.",
        '"body": "Run pip install policybench to start",',
        "pip install \\\n  policybench",
    ],
)
def test_detector_flags_index_installs_of_policybench(command):
    assert DISTRIBUTION in index_installs(command)


@pytest.mark.parametrize(
    "command",
    [
        f"pip install git+{REPO_URL}",
        f"pip install git+{REPO_URL}.git@main",
        f"uv tool install --python 3.12 git+{REPO_URL}",
        f"uvx --from git+{REPO_URL} policybench --help",
        f"pip install 'policybench @ git+{REPO_URL}'",
        f"pip install policybench@git+{REPO_URL}",
        'pip install -e ".[dev]"',
        "pip install -e policybench",
        "pip install ./policybench",
        "pip install dist/policybench-2.0.0-py3-none-any.whl",
        "pip install policybench-tools",
        "pip install uv",
        "Run pip install uv, then clone policybench.",
        "uv sync --locked --extra dev",
        "uv run policybench onboard",
        "uv run python -m policybench.cli reference-outputs",
        "policybench --help",
    ],
)
def test_detector_passes_installs_from_source(command):
    assert DISTRIBUTION not in index_installs(command)


@pytest.mark.parametrize(
    ("lines", "flagged"),
    [
        ("policybench>=2\n", True),
        ("jupyter-book>=2.0\nPolicyBench  # the benchmark\n", True),
        (f"git+{REPO_URL}\n-e .\n# policybench\n", False),
    ],
)
def test_detector_reads_requirements_files(tmp_path, lines, flagged):
    path = tmp_path / "requirements.txt"
    path.write_text(lines)
    assert (DISTRIBUTION in surface_installs(path)) is flagged


@pytest.mark.parametrize("pattern", SURFACES)
def test_no_surface_installs_policybench_from_an_index(pattern):
    paths = sorted(ROOT.glob(pattern))
    assert paths, f"{pattern} matches no file; update SURFACES"
    for path in paths:
        assert DISTRIBUTION not in surface_installs(path), (
            f"{path.relative_to(ROOT)} installs {DISTRIBUTION} from a package "
            f"index by name, but it is not published there; install from "
            f"git+{REPO_URL} or a clone instead"
        )


def test_readme_installs_policybench_from_github():
    """The quick start installs the package from this repository, so a reader
    can run ``policybench --help`` without a package index."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quick_start = readme.split("## Quick start", 1)[1].split("\n## ", 1)[0]
    installs_from_github = re.search(
        r"(?:pip3?\s+install|uv\s+tool\s+install|uv\s+add|pipx\s+install|--from)"
        rf"\s+(?:\S+\s+)*?git\+{re.escape(REPO_URL)}(?:\.git)?(?:@\S+)?(?=\s|$)",
        quick_start,
    )
    assert installs_from_github, quick_start
    assert "policybench --help" in quick_start
