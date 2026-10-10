"""policybench.fix_module_closure: the local files a fix module loads, and the
modules whose closure cannot be established (the 2026-10-09 delta review's
finding 3)."""

import json
import re
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from policybench.fix_module_closure import (
    ClosureError,
    dependency_closure,
    direct_dependencies,
)

REPO = Path(__file__).resolve().parents[1]
FIXES = REPO / "reference_audit/2026-09-22/fixes"
# The loader the regex-based discovery recognized, before this module.
LITERAL = re.compile(r"with_name\(\s*['\"]([^'\"]+)['\"]\s*\)")


def read(files: dict[str, str]):
    return lambda name: files[name].encode()


def test_literal_siblings_are_found_transitively_in_source_order():
    files = {
        "a_v2.py": (
            "from pathlib import Path\n"
            "y = Path(__file__).with_name('a.py')\n"
            'z = Path(__file__).with_name( "c.json" )\n'
        ),
        "a.py": 'b = Path(__file__).with_name("b.py")\n',
        "b.py": 'a = Path(__file__).with_name("a.py")\n',
        "c.json": "{}",
    }
    assert dependency_closure("a_v2.py", read(files)) == ["a.py", "c.json", "b.py"]
    assert dependency_closure("c.json", read(files)) == []


@pytest.mark.parametrize(
    "source, problem",
    [
        # The delta review's case: c13v3_upstream_plus_r30.py's loader.
        (
            "_HERE = Path(__file__).resolve().parent\n"
            "def load(name):\n"
            "    return spec_from_file_location(name, _HERE / f'{name}.py')\n",
            "uses __file__ other than",
        ),
        ("p = os.path.dirname(__file__)\n", "uses __file__ other than"),
        ("p = Path(__file__).with_name(NAME)\n", "uses __file__ other than"),
        ("p = Path(__file__).with_name('a' + '.py')\n", "uses __file__ other than"),
        ("p = Path(__file__).with_name('../a.py')\n", "uses __file__ other than"),
        ("p = Path(__file__).with_name('sub/a.py')\n", "uses __file__ other than"),
        ("p = Path(__file__).parent / 'a.py'\n", "uses __file__ other than"),
        ("t = json.load(open('tables.json'))\n", "names the file 'tables.json'"),
        ("HERE = Path('reference_audit/x.py')\n", "names the file"),
        ("import sys\nsys.path.insert(0, 'x')\n", "uses sys.path"),
        ("import importlib\nm = importlib.import_module('a')\n", "uses .import_module"),
        ("from importlib import import_module\n", "imports ['import_module']"),
        ("m = __import__('a')\n", "calls __import__"),
        ("exec(open(p).read())\n", "calls exec"),
        ("x = eval(s)\n", "calls eval"),
        ("c = compile(s, 'f', 'exec')\n", "calls compile"),
        ("import runpy\n", "runpy"),
        ("from . import sibling\n", "relatively"),
        ("os.chdir(d)\n", "uses .chdir"),
        # The pre-T review's forms: a pattern over a literally named sibling's
        # directory, a name built from pieces, the module's own location
        # reached another way, and this repository's own package.
        (
            "d = Path(__file__).with_name('x.py').parent.glob('r0*_v2.py')\n",
            "uses .glob",
        ),
        ("fs = sorted(HERE.rglob('*'))\n", "uses .rglob"),
        ("fs = list(d.iterdir())\n", "uses .iterdir"),
        ("fs = os.listdir(d)\n", "uses .listdir"),
        ("fs = os.walk(d)\n", "uses .walk"),
        ("o = __spec__.origin\n", "uses __spec__"),
        ("l = __loader__\n", "uses __loader__"),
        ("import sys\nf = sys.modules[__name__].__file__\n", "uses .__file__"),
        ("import inspect\n", "inspect"),
        ("g = globals()\n", "calls globals"),
        ("v = vars()\n", "calls vars"),
        ("from policybench.scenarios import load\n", "policybench"),
        ("import policybench.scenarios\n", "policybench"),
        ("def f(:\n", "does not parse"),
    ],
)
def test_other_ways_of_reaching_local_files_are_refused(source, problem):
    with pytest.raises(ClosureError, match=re.escape(problem)):
        direct_dependencies(source, "m.py")


def test_a_refused_sibling_refuses_the_module_that_loads_it():
    files = {
        "top.py": 'Path(__file__).with_name("mid.py")\n',
        "mid.py": "_HERE = Path(__file__).resolve().parent\n",
    }
    with pytest.raises(ClosureError, match="mid.py"):
        dependency_closure("top.py", read(files))


@pytest.mark.parametrize(
    "source",
    [
        '"""Loads x.py from its directory."""\nimport re\nP = re.compile("a")\n',
        "def f():\n    '''Reads tables.json.'''\n    return 1\n",
        "from pathlib import Path\n"
        "from importlib.util import spec_from_file_location\n",
        "label = 'state_income_tax'\n",
    ],
)
def test_ordinary_code_and_docstrings_are_not_refused(source):
    assert direct_dependencies(source, "m.py") == []


NAMES = st.from_regex(r"[a-z][a-z0-9_]{0,12}\.(py|json)", fullmatch=True)


@given(st.lists(NAMES, max_size=8), st.sampled_from(["'", '"']))
def test_literal_loads_give_exactly_their_names_in_order(names, quote):
    """Property: a module of literal with_name loads depends on exactly those
    files, each once, in source order."""
    source = "".join(
        f"x{i} = Path(__file__).with_name({quote}{name}{quote})\n"
        for i, name in enumerate(names)
    )
    assert direct_dependencies(source, "m.py") == list(dict.fromkeys(names))


def _regex_closure(name: str) -> list[str]:
    found, queue = [], [name]
    while queue:
        for dep in LITERAL.findall((FIXES / queue.pop(0)).read_text()):
            if dep != name and dep not in found:
                found.append(dep)
                queue.append(dep)
    return found


def test_on_the_committed_fixes_it_agrees_with_literal_discovery_or_refuses():
    """Differential, on every committed audited fix module: where the closure
    is established it is the one literal with_name discovery found; the
    modules it refuses are exactly the wrappers that build sibling paths at
    run time (``_HERE / f"{name}.py"``), which literal discovery missed, and
    the ones that import this repository's own package. No module the
    engine upgrade's evidence applies is refused."""
    refused = set()
    for path in sorted(FIXES.glob("*.py")):
        try:
            closure = dependency_closure(path.name, lambda n: (FIXES / n).read_bytes())
        except ClosureError:
            refused.add(path.name)
            continue
        assert closure == _regex_closure(path.name), path.name
    wrappers = {
        path.name for path in FIXES.glob("*.py") if 'f"{name}.py"' in path.read_text()
    }
    in_repo = {
        path.name
        for path in FIXES.glob("*.py")
        if re.search(r"^\s*(from|import) policybench\b", path.read_text(), re.M)
    }
    assert refused == wrappers | in_repo
    evidence = json.loads(
        (
            FIXES.parents[1] / "2026-10-09-engine-upgrade/evidence/pe2.37.2.json"
        ).read_text()
    )
    applied = {m for item in evidence["items"] for m in item["modules"]}
    assert applied and applied.isdisjoint(refused), applied & refused
    assert "c13v3_upstream_plus_r30.py" in refused
    assert {
        "r01_ira_compensation_v2.py",
        "r02_ira_219g_v2.py",
        "r03_estate_income__qbi_false_v2.py",
    }.isdisjoint(refused)
