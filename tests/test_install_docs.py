"""Install commands in the docs must name a source that exists.

PolicyBench is not published on PyPI: on 2026-10-06 both
https://pypi.org/pypi/policybench/json and https://pypi.org/simple/policybench/
returned 404. A command that installs the ``policybench`` distribution from a
package index by name (``pip install policybench``, ``uvx policybench``) fails
today, and would install whatever a third party later uploads under the name.
The README installs it from GitHub and the development docs from a clone; these
tests hold every surface a reader follows to that. A doc that quotes the index
command, even to warn against it, fails too: readers copy commands. If
PolicyBench is ever published to PyPI, delete this module with the README's
"not published" line.
"""

import html
import json
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
#   requirements: each positional is a requirement (pip install).
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
# Options whose value is a requirement; --from and --spec also name the tool.
REQUIREMENT_OPTIONS = {"--with", "-w", "--from", "--spec"}
TOOL_OPTIONS = {"--from", "--spec"}
# Options whose value is anything else (a path, an index, a Python version, a
# channel, a format control), which is skipped.
VALUE_OPTIONS = {
    "-C",
    "-P",
    "-c",
    "-e",
    "-f",
    "-i",
    "-n",
    "-p",
    "-r",
    "-t",
    "--channel",
    "--config-settings",
    "--constraint",
    "--default-index",
    "--directory",
    "--editable",
    "--env-file",
    "--exclude-newer",
    "--extra",
    "--extra-index-url",
    "--find-links",
    "--group",
    "--index",
    "--index-strategy",
    "--index-url",
    "--name",
    "--no-binary",
    "--only-binary",
    "--optional",
    "--pip-args",
    "--platform",
    "--prefix",
    "--project",
    "--python",
    "--python-platform",
    "--python-version",
    "--requirement",
    "--root",
    "--target",
    "--upgrade-package",
    "--with-editable",
    "--with-requirements",
}
# Flags that keep the installer off every index, as in an offline install
# from a directory of built wheels.
OFFLINE_FLAGS = {"--no-index", "--offline"}
SHELL_OPERATORS = {";", "&", "&&", "|", "||", "<", ">", ">>", "(", ")"}
FENCE = re.compile(r"^(```|~~~)[^\n]*\n(.*?)^\1", re.DOTALL | re.MULTILINE)
INLINE_CODE = re.compile(r"`([^`]+)`")
HTML_CODE = re.compile(r"<(code|pre)\b[^>]*>(.*?)</\1>", re.DOTALL)
TAG = re.compile(r"<[^>]+>")


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
    match = re.match(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", token)
    return _normalize(match.group()) if match else None


def _tokens(arguments: str) -> list[str]:
    """Shell tokens, with quotes, ``#`` comments and operators handled."""
    for text in (arguments, re.sub(r"[\"']", "", arguments)):
        lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        try:
            return list(lexer)
        except ValueError:  # an unbalanced quote: retry without quotes
            continue
    return []


def _scan(tokens: list[str], role: str, every_positional: bool) -> list[str]:
    """Distributions an installer's arguments fetch from an index by name.

    In code every positional of a ``requirements`` installer counts. In prose
    only the one right after the installer and its options does, so "uv tool
    install puts policybench on your PATH" names no requirement.
    """
    names = []
    named_tool = False
    i = 0
    while i < len(tokens) and tokens[i] not in SHELL_OPERATORS:
        token = tokens[i].strip("\u201c\u201d\u2018\u2019")  # curly quotes in prose
        if token in OFFLINE_FLAGS:
            return []
        if token.startswith("-"):
            flag, has_value, value = token.partition("=")
            if flag in REQUIREMENT_OPTIONS:
                if not has_value and i + 1 < len(tokens):
                    i += 1
                    value = tokens[i]
                names += [n for n in map(_index_name, value.split(",")) if n]
                named_tool = named_tool or flag in TOOL_OPTIONS
            elif flag in VALUE_OPTIONS and not has_value:
                i += 1
        elif role == "command" or (role == "tool" and named_tool):
            break
        else:
            name = _index_name(token.rstrip(".,;:!?)}\"'"))
            if name:
                names.append(name)
            if role == "tool" or not every_positional:
                break
        i += 1
    return names


def _installs(snippet: str, every_positional: bool) -> list[str]:
    names = []
    for pattern, role in INSTALLERS:
        for match in pattern.finditer(snippet):
            tokens = _tokens(snippet[match.end() :])
            names += _scan(tokens, role, every_positional)
    return names


def _code_and_prose(text: str, markup: bool) -> tuple[list[str], str]:
    """Split text into code snippets and the prose around them.

    Code is fenced blocks and, in markup, ``<pre>`` elements (one command per
    line), plus inline code spans and ``<code>`` elements, joined across a
    soft wrap.
    Prose is everything else with line breaks collapsed, so a wrapped sentence
    reads as one line.
    """
    code = []
    if markup:
        for tag, inner in HTML_CODE.findall(text):
            inner = html.unescape(TAG.sub("", inner))
            code += inner.splitlines() if tag == "pre" else [" ".join(inner.split())]
        text = html.unescape(TAG.sub(" ", text))
    for _, block in FENCE.findall(text.replace("\\\n", " ")):
        code += block.splitlines()
    text = FENCE.sub("\n", text)
    code += [" ".join(span.split()) for span in INLINE_CODE.findall(text)]
    return code, " ".join(INLINE_CODE.sub(r"\1", text).split())


def index_installs(text: str, markup: bool = False) -> list[str]:
    """Every distribution an install command in ``text`` fetches by name."""
    code, prose = _code_and_prose(text, markup)
    names = [n for snippet in code for n in _installs(snippet, True)]
    return names + _installs(prose, False)


def _json_strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return [s for item in value for s in _json_strings(item)]
    return []


def surface_installs(path: Path) -> list[str]:
    """Every distribution ``path`` fetches from an index by name."""
    text = path.read_text(encoding="utf-8")
    if path.name.endswith("requirements.txt"):
        # Each line of a requirements file is itself a requirement.
        lines = (line.split("#", 1)[0].strip() for line in text.splitlines())
        return [n for n in map(_index_name, lines) if n]
    if path.suffix == ".json":
        # Decode escapes so a quoted command in a note reads as written.
        strings = _json_strings(json.loads(text))
        return [n for s in strings for n in index_installs(s)]
    if path.suffix in {".yml", ".yaml", ".sh"}:
        return [n for line in text.splitlines() for n in _installs(line, True)]
    return index_installs(text, markup=path.suffix in {".html", ".ts", ".tsx"})


@pytest.mark.parametrize(
    "text",
    [
        "pip install policybench",
        "$ pip3 install -U policybench",
        "python -m pip install 'policybench[dev]>=2'",
        "py -3.12 -m pip install policybench",
        "uv pip install --system PolicyBench==2.0.0",
        "uv tool install --python 3.12 policybench",
        "uv add policybench",
        "pipx install policybench",
        "conda install -c conda-forge policybench",
        "!pip install policybench",
        "`pip install numpy policybench`",
        '`pip install "policyengine-us>=2" policybench`',
        "`pip install --no-binary :all: policybench`",
        "Run pip install policybench to get started.",
        "Install it with `pip install\npolicybench` and run it.",
        "Install it with `pip\ninstall policybench`.",
        "uvx policybench --help",
        "uvx policybench@latest --help",
        "uv tool run policybench --help",
        "pipx run policybench",
        "`uvx --with rich policybench --help`",
        "`uvx -w policybench python`",
        "`uv run --with numpy,policybench python`",
        "`uvx --from policybench policybench --help`",
        "uv add --optional dev policybench",
        "uvx --exclude-newer 2026-10-01 policybench --help",
        "Install it with pip install \u201cpolicybench\u201d.",
        "PolicyBench is not on PyPI, so `pip install policybench` fails.",
        "```bash\npip install \\\n  policybench\n```",
    ],
)
def test_detector_flags_index_installs_of_policybench(text):
    assert DISTRIBUTION in index_installs(text)


@pytest.mark.parametrize(
    "text",
    [
        f"pip install git+{REPO_URL}",
        f"pip install git+{REPO_URL}.git@main",
        f"pip install git+{REPO_URL}#egg=policybench",
        f"uv tool install --python 3.12 git+{REPO_URL}  # puts policybench on PATH",
        f"uvx --from git+{REPO_URL} policybench --help",
        f"pip install 'policybench @ git+{REPO_URL}'",
        f"pip install policybench@git+{REPO_URL}",
        'pip install -e ".[dev]"   # editable install of policybench',
        "pip install -e policybench",
        "pip install ./policybench",
        "pip install dist/policybench-2.0.0-py3-none-any.whl",
        "pip install policybench-tools",
        "pip install uv, then clone policybench.",
        "uv tool install puts policybench on your PATH.",
        "A plain pip install of policybench fails because it is not on PyPI.",
        "uvx and uv tool install both fetch policybench from GitHub.",
        "`pip install --no-index --find-links dist policybench`",
        "conda install -n policybench uv",
        "uv sync --locked --extra dev",
        "uv run policybench onboard",
        "uv run python -m policybench.cli reference-outputs",
        "policybench --help",
    ],
)
def test_detector_passes_installs_from_source(text):
    assert DISTRIBUTION not in index_installs(text)


@pytest.mark.parametrize(
    ("name", "content", "flagged"),
    [
        ("requirements.txt", "policybench>=2\n", True),
        ("requirements.txt", "jupyter-book\nPolicyBench  # the benchmark\n", True),
        ("requirements.txt", f"git+{REPO_URL}\n-e .\n# policybench\n", False),
        ("note.json", json.dumps({"body": 'Run "pip install policybench".'}), True),
        ("note.json", json.dumps({"body": "```bash\nuvx policybench\n```"}), True),
        ("note.json", json.dumps({"body": f"pip install git+{REPO_URL}"}), False),
        (
            "Page.tsx",
            "<code>\n  uv tool install --python 3.12\n  policybench\n</code>",
            True,
        ),
        (
            "Page.tsx",
            "<p>\n  Install with pip install\n  policybench today.\n</p>",
            True,
        ),
        ("page.html", '<span class="ex">pip</span> install policybench', True),
        ("page.html", "<pre>pip install uv\npolicybench --help</pre>", False),
        ("ci.yml", "      - run: pip install policybench\n", True),
        ("ci.yml", "      - run: pip install uv\n", False),
    ],
)
def test_detector_reads_each_surface_format(tmp_path, name, content, flagged):
    path = tmp_path / name
    path.write_text(content)
    assert (DISTRIBUTION in surface_installs(path)) is flagged


@pytest.mark.parametrize("pattern", SURFACES)
def test_no_surface_installs_policybench_from_an_index(pattern):
    paths = sorted(ROOT.glob(pattern))
    assert paths, f"{pattern} matches no file; update SURFACES"
    for path in paths:
        assert DISTRIBUTION not in surface_installs(path), (
            f"{path.relative_to(ROOT)} installs {DISTRIBUTION} from a package "
            f"index by name, or quotes a command that does, but it is not "
            f"published there; install from git+{REPO_URL} or a clone instead"
        )


def _github_source(token: str) -> bool:
    source = re.sub(r"^[\w.-]+(\[[^\]]*\])?\s*@\s*", "", token)
    return re.match(rf"git\+{re.escape(REPO_URL)}(\.git)?([@#/]|$)", source) is not None


def test_readme_installs_policybench_from_github():
    """The quick start installs PolicyBench itself from this repository (its
    dependencies still come from PyPI) and shows ``policybench --help``."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    quick_start = readme.split("## Quick start", 1)[1].split("\n## ", 1)[0]
    code, _ = _code_and_prose(quick_start, markup=False)
    sources = [
        token
        for snippet in code
        for pattern, _ in INSTALLERS[:3]
        for match in pattern.finditer(snippet)
        for token in _tokens(snippet[match.end() :])
    ]
    assert any(map(_github_source, sources)), code
    assert "policybench --help" in code
