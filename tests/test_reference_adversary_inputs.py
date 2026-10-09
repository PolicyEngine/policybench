"""The reference adversary's scripts read only the pass's pinned inputs.

``reference_audit/2026-10-05-reference-adversary/scripts/pass_inputs.py`` pins
every input the pass read, by commit and sha256: the frozen run as release
dashboard-data-20260930 (8b4c0ca1) committed it, the output definitions and the
reference system's convention modules as that commit held them, #194's law
table, and the pass's own records as #200 merged them. Later commits rewrote
the working tree's copies (#202 the run's payload and exclusion record, #204
one convention module). These tests check that

* the pins are what the pass read: each commit holds those bytes, the
  committed evidence records the same hashes, and the README's Inputs table
  lists each pin with the scripts that stage it;
* any other bytes are refused, and each script refuses before it computes or
  writes anything;
* no script opens the working tree's copy of a pinned input (an audit hook
  fails any such open);
* each script regenerates its committed outputs byte for byte. The engine-side
  regenerations need policyengine-us 2.15.17 and take minutes, so they are
  marked slow and CI deselects them; build_proposals.py's regeneration is fast.

CI checks out full history, so git holds every pinned input.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from functools import cache
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "reference_audit/2026-10-05-reference-adversary"
SCRIPTS = AUDIT / "scripts"
VERIFICATION = AUDIT / "verification"
PROBES = sorted((VERIFICATION / "probes").glob("*.json"))
sys.path.insert(0, str(SCRIPTS))
import pass_inputs as pins  # noqa: E402

from tests import working_tree_fence as fence  # noqa: E402

# Release dashboard-data-20261006 (#202): the run's payload and exclusion record
# as it rewrote them.
RELEASE_20261006_COMMIT = "9ce4ade8382962a9134860c23f56d92509b5e57f"
RELEASE_20261006_SHA256 = {
    "data.json.gz": "b1da3eae058c1a511f5579bc8235c822cf6862e33caf4840004bd0cf0f34c41d",
    "reference_exclusions.json": (
        "92741dfd047298eacb79a0dadeb7e4965e3c6f986beab0341b12ff8f5b023815"
    ),
}
# latest_alt_snap_mortgage_residence.py as #204 rewrote it (held at 4db91b5f).
MODULE_204 = "reference_audit/2026-09-28/fixes/latest_alt_snap_mortgage_residence.py"
MODULE_204_SHA256 = "5e701f8fa1b31bfeed882a0bc5160faa4ee1d2b5a67974f9d9dc60e6f6638053"
# Every pin: (commit, path, sha256).
PINNED = (
    [
        (pins.PASS_COMMIT, f"{pins.RUN_PATH}/{name}", sha)
        for name, sha in pins.RUN_SHA256.items()
    ]
    + [(pins.PASS_COMMIT, path, sha) for path, sha in pins.FIXES_SHA256.items()]
    + [
        (pins.PASS_COMMIT, pins.SPECS_PATH, pins.SPECS_SHA256),
        (pins.LAW_COMMIT, pins.LAW_PATH, pins.LAW_SHA256),
        (pins.RECORDS_COMMIT, pins.PROPOSALS_PATH, pins.PROPOSALS_SHA256),
        (pins.RECORDS_COMMIT, pins.CONFORMANCE_PATH, pins.CONFORMANCE_SHA256),
    ]
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"reference_adversary_{name}", SCRIPTS / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


conformance = _load("definition_conformance")
sources = _load("publication_sources")
probe = _load("engine_probe")
proposals = _load("build_proposals")
impact = _load("leaderboard_impact")
SCRIPT_MODULES = {
    "definition_conformance": conformance,
    "publication_sources": sources,
    "engine_probe": probe,
    "build_proposals": proposals,
}


# ---------------------------------------------------------------------------
# A fence on the working tree's copy of every pinned input
# ---------------------------------------------------------------------------

# The working tree's copies; policybench may read its own benchmark_specs.json.
FENCE = {
    "forbidden": [
        str(ROOT / path)
        for path in (
            pins.RUN_PATH,
            *pins.FIXES_SHA256,
            pins.SPECS_PATH,
            pins.LAW_PATH,
            pins.PROPOSALS_PATH,
            pins.CONFORMANCE_PATH,
        )
    ],
    "exempt": {str(ROOT / pins.SPECS_PATH): str(ROOT / "policybench")},
    "root": str(ROOT),
}


@contextmanager
def fenced():
    """Inside, opening the working tree's copy of any pinned input raises."""
    fence.arm(**FENCE)
    try:
        yield
    finally:
        fence.disarm()


def _fenced_env(directory: Path) -> dict[str, str]:
    """A subprocess environment whose every interpreter, workers included, is fenced."""
    return dict(
        os.environ,
        PYTHONPATH=f"{fence.sitecustomize(directory)}{os.pathsep}{ROOT}",
        PYTHONDONTWRITEBYTECODE="1",
        OPENBLAS_NUM_THREADS="1",
        **{fence.ENV: json.dumps(FENCE)},
    )


def test_the_fence_catches_a_working_tree_read():
    """The hook is not vacuous: each way the scripts read files trips it."""
    run = ROOT / pins.RUN_PATH
    with fenced():
        with pytest.raises(PermissionError, match="working tree"):
            pd.read_csv(run / "scenarios.csv")
        with pytest.raises(PermissionError, match="working tree"):
            gzip.open(run / "data.json.gz").read()
        with pytest.raises(PermissionError, match="working tree"):
            (ROOT / MODULE_204).read_text()
        with pytest.raises(PermissionError, match="working tree"):
            (ROOT / pins.CONFORMANCE_PATH).read_bytes()
        # Only policybench's own code may read its output definitions.
        with pytest.raises(PermissionError, match="working tree"):
            (ROOT / pins.SPECS_PATH).read_bytes()
        from policybench import spec

        spec._raw_spec_data.cache_clear()
        assert spec._raw_spec_data()
        # git show reads the object store, not the working tree.
        assert pins.git_bytes(
            pins.PASS_COMMIT, MODULE_204, pins.FIXES_SHA256[MODULE_204]
        )
    assert (run / "scenarios.csv").read_bytes()


FENCE_PROBE = """
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def read(path):
    return len(Path(path).read_bytes())


if __name__ == "__main__":
    with ProcessPoolExecutor(1) as pool:
        print(pool.submit(read, sys.argv[1]).result())
"""


@pytest.mark.parametrize("where", ["main", "worker"])
def test_the_fence_reaches_every_process_of_a_subprocess(where, tmp_path):
    """Armed through sitecustomize, it fails a read in the main process and in a
    spawned worker alike; unarmed, the same read succeeds."""
    script = tmp_path / "read.py"
    if where == "main":
        script.write_text("import sys\nprint(len(open(sys.argv[1], 'rb').read()))\n")
    else:
        script.write_text(FENCE_PROBE)
    target = str(ROOT / pins.RUN_PATH / "scenarios.csv")
    env = _fenced_env(tmp_path / "fence")
    fenced_run = subprocess.run(
        [sys.executable, str(script), target], env=env, capture_output=True, text=True
    )
    assert fenced_run.returncode != 0
    assert "opened the working tree's" in fenced_run.stderr
    env.pop(fence.ENV)
    plain = subprocess.run(
        [sys.executable, str(script), target], env=env, capture_output=True, text=True
    )
    assert plain.returncode == 0, plain.stderr
    assert int(plain.stdout) > 0


# ---------------------------------------------------------------------------
# The pins are what the pass read
# ---------------------------------------------------------------------------


def test_every_pin_is_what_its_commit_holds():
    for commit, path, pinned in PINNED:
        data = pins.git_bytes(commit, path, pinned)
        assert hashlib.sha256(data).hexdigest() == pinned, path
    # The README's frozen run: 46 models, 1,928 scored cells.
    payload = json.loads(
        gzip.decompress(
            pins.git_bytes(
                pins.PASS_COMMIT,
                f"{pins.RUN_PATH}/data.json.gz",
                pins.RUN_SHA256["data.json.gz"],
            )
        )
    )
    assert len(payload["modelStats"]) == 46
    assert {row["n"] for row in payload["modelStats"]} == {1928}


def test_the_committed_evidence_records_the_pins():
    """Differential: the hashes the pass's own outputs recorded equal the pins."""
    run = json.loads((VERIFICATION / "definition_conformance.json").read_text())["run"]
    assert run["payload"] == f"{pins.RUN_PATH}/data.json.gz"
    assert run["payload_sha256"] == pins.RUN_SHA256["data.json.gz"]
    assert run["reference_outputs_sha256"] == pins.RUN_SHA256["reference_outputs.csv"]
    assert run["scenarios_sha256"] == pins.RUN_SHA256["scenarios.csv"]
    assert run["benchmark_specs_sha256"] == pins.SPECS_SHA256
    assert run["fixes_sha256"] == pins.FIXES_SHA256
    assert run["law_classification"]["sha256"] == pins.LAW_SHA256
    assert run["law_classification"]["source"] == conformance.LAW_SOURCE

    meta = json.loads((VERIFICATION / "publication_sources.json").read_text())["meta"]
    assert meta["payload"] == f"{pins.RUN_PATH}/data.json.gz"
    assert meta["payload_sha256"] == pins.RUN_SHA256["data.json.gz"]
    assert meta["reference_outputs"] == f"{pins.RUN_PATH}/reference_outputs.csv"

    flags = json.loads((AUDIT / "consensus_flags.json").read_text())
    assert flags["source"] == f"{pins.RUN_PATH}/data.json.gz"
    assert flags["source_sha256"] == pins.RUN_SHA256["data.json.gz"]


def test_later_commits_hold_other_bytes_than_the_pins():
    """Why the pins exist: #202 rewrote the run's payload and exclusion record and
    #204 a convention module, so reading those commits' copies is refused."""
    for name, sha in RELEASE_20261006_SHA256.items():
        with pytest.raises(SystemExit, match=f"has sha256 {sha}, not the pinned"):
            pins.git_bytes(
                RELEASE_20261006_COMMIT,
                f"{pins.RUN_PATH}/{name}",
                pins.RUN_SHA256[name],
            )
    with pytest.raises(SystemExit, match=f"has sha256 {MODULE_204_SHA256}, not"):
        pins.git_bytes(pins.RECORDS_COMMIT, MODULE_204, pins.FIXES_SHA256[MODULE_204])


def _staged(script: str, tmp_path: Path) -> set[tuple[str, str]]:
    """Every (commit, path) a script stages, recorded as git_input is called."""
    seen: set[tuple[str, str]] = set()
    original = pins.git_input

    def record(commit, path, pinned, target):
        seen.add((commit, path))
        return original(commit, path, pinned, target)

    with mock.patch.object(pins, "git_input", record):
        if script == "leaderboard_impact":
            impact.stage_inputs(tmp_path / script)
        else:
            SCRIPT_MODULES[script].stage_inputs(tmp_path / script)
        if script in ("definition_conformance", "publication_sources"):
            SCRIPT_MODULES[script]._assemble_fixes()
        if script == "engine_probe":
            # The probe builds its reference system with definition_conformance's
            # builder, which stages the convention modules.
            conformance._assemble_fixes()
    return seen


def _readme_inputs() -> dict[str, tuple[str, str, set[str]]]:
    """README Inputs rows: path -> (commit, sha256, readers)."""
    rows = {}
    pattern = re.compile(
        r"^\s*\| `(?P<path>[^`]+)`[^|]* \| `(?P<commit>[0-9a-f]{8})` \| "
        r"`(?P<sha>[0-9a-f]{64})` \|(?: (?P<readers>[^|]*) \|)?$"
    )
    for line in (AUDIT / "README.md").read_text().splitlines():
        match = pattern.match(line)
        if match is None:
            continue
        path = match["path"].replace("<run>", pins.RUN_PATH)
        readers = set(re.findall(r"`([^`]+)`", match["readers"] or ""))
        assert path not in rows, f"README lists {path} twice"
        rows[path] = (match["commit"], match["sha"], readers)
    return rows


def test_the_readme_lists_each_pin_and_the_scripts_that_stage_it(tmp_path):
    rows = _readme_inputs()
    staged = {
        script: _staged(script, tmp_path)
        for script in [*SCRIPT_MODULES, "leaderboard_impact"]
    }
    readers: dict[tuple[str, str], set[str]] = {}
    for script, inputs in staged.items():
        for key in inputs:
            readers.setdefault(key, set()).add(f"{script}.py")
    fixes = set(pins.FIXES_SHA256)
    for commit, path, pinned in PINNED:
        assert path in rows, f"README's Inputs table omits {path}"
        row_commit, row_sha, row_readers = rows.pop(path)
        assert commit.startswith(row_commit), path
        assert row_sha == pinned, path
        expected = readers.get((commit, path), set())
        assert expected, f"no script stages {path}"
        if path in fixes:
            # The convention modules' table names their readers once, above it.
            assert row_readers == set(), path
            continue
        scripts = {reader for reader in row_readers if reader.endswith(".py")}
        assert scripts == expected, path
    # Rows left over are the CLI's inputs, which no script here reads.
    for path, (commit, sha, row_readers) in rows.items():
        assert not any(reader.endswith(".py") for reader in row_readers), path
        assert (
            hashlib.sha256(
                subprocess.run(
                    ["git", "-C", str(ROOT), "show", f"{commit}:{path}"],
                    capture_output=True,
                    check=True,
                ).stdout
            ).hexdigest()
            == sha
        ), path
    fix_readers = {
        script
        for script, inputs in staged.items()
        if inputs & {(pins.PASS_COMMIT, path) for path in fixes}
    }
    assert fix_readers == {
        "definition_conformance",
        "publication_sources",
        "engine_probe",
    }
    text = (AUDIT / "README.md").read_text()
    assert (
        "read by `definition_conformance.py`, `publication_sources.py` and "
        "`engine_probe.py`" in text
    )


def test_no_script_holds_its_own_pin_or_names_the_run():
    """pass_inputs.py is the only place a pin or the run's path is written."""
    hexdigest = re.compile(r"\b[0-9a-f]{64}\b")
    for path in sorted(SCRIPTS.glob("*.py")):
        if path.name == "pass_inputs.py":
            continue
        text = path.read_text()
        assert not hexdigest.search(text), path.name
        assert "paper/snapshot" not in text, path.name


# ---------------------------------------------------------------------------
# Any other bytes are refused
# ---------------------------------------------------------------------------


@cache
def _pinned_bytes(index: int) -> bytes:
    commit, path, pinned = PINNED[index]
    return pins.git_bytes(commit, path, pinned)


@st.composite
def _edits(draw) -> tuple[int, str, int, int]:
    """One pinned input and one change to its bytes: flip, cut or extend."""
    index = draw(st.integers(0, len(PINNED) - 1))
    kind = draw(st.sampled_from(["flip", "truncate", "append"]))
    position = draw(st.integers(0, len(_pinned_bytes(index)) - 1))
    return index, kind, position, draw(st.integers(1, 255))


def _shown(data: bytes) -> SimpleNamespace:
    return SimpleNamespace(
        run=lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=data, stderr=b""
        )
    )


@settings(max_examples=60, deadline=None)
@given(_edits())
def test_any_changed_byte_in_any_pinned_input_is_refused_unwritten(edit):
    """Invariant: git_input writes a file only if its bytes are the pinned bytes."""
    index, kind, position, byte = edit
    commit, path, pinned = PINNED[index]
    original = _pinned_bytes(index)
    if kind == "flip":
        changed = bytearray(original)
        changed[position] ^= byte
        tampered = bytes(changed)
    elif kind == "truncate":
        tampered = original[:position]
    else:
        tampered = original + bytes([byte])
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / Path(path).name
        with mock.patch.object(pins, "subprocess", _shown(tampered)):
            with pytest.raises(SystemExit, match=f"not the pinned {pinned}"):
                pins.git_input(commit, path, pinned, target)
        assert not target.exists()
        # The unchanged bytes pass the same check.
        with mock.patch.object(pins, "subprocess", _shown(original)):
            pins.git_input(commit, path, pinned, target)
        assert target.read_bytes() == original


@pytest.mark.parametrize(
    ("attribute", "value", "message"),
    [
        (
            "PASS_COMMIT",
            pins.RECORDS_COMMIT,
            f"latest_alt_snap_mortgage_residence.py has sha256 {MODULE_204_SHA256}, "
            f"not the pinned {pins.FIXES_SHA256[MODULE_204]}",
        ),
        ("PASS_COMMIT", "0" * 40, "cannot read"),
    ],
)
@pytest.mark.parametrize("script", ["definition_conformance", "publication_sources"])
def test_the_reference_system_refuses_other_convention_modules(
    script, attribute, value, message, monkeypatch
):
    """#204's rewrite of a convention module (on 4db91b5f) is refused."""
    monkeypatch.setattr(pins, attribute, value)
    with pytest.raises(SystemExit, match=re.escape(message)):
        SCRIPT_MODULES[script]._assemble_fixes()


def _never(name: str):
    def called(*args, **kwargs):
        raise AssertionError(f"{name} ran after an input was refused")

    return called


def _argv(script: str, out: Path) -> list[str]:
    if script == "engine_probe":
        return [script, "scenario_043", "--out", str(out / "probe.json")]
    if script == "build_proposals":
        return [script, "--out", str(out / "proposed_changes.json")]
    return [script, "--out-dir", str(out)]


# The first input each script stages that #202 rewrote.
FIRST_REWRITTEN = {
    "definition_conformance": "data.json.gz",
    "publication_sources": "data.json.gz",
    "engine_probe": "reference_exclusions.json",
    "build_proposals": "reference_exclusions.json",
}


@pytest.mark.parametrize("script", sorted(SCRIPT_MODULES))
def test_a_mismatched_input_stops_the_script_before_it_computes_or_writes(
    script, tmp_path, monkeypatch
):
    """Pointed at #202's run, each script refuses before any engine work or write."""
    module = SCRIPT_MODULES[script]
    monkeypatch.setattr(pins, "PASS_COMMIT", RELEASE_20261006_COMMIT)
    for name in ("_system", "_assemble_fixes", "install_build_hooks", "_conformance"):
        if hasattr(module, name):
            monkeypatch.setattr(module, name, _never(name))
    monkeypatch.setattr(module, "build", _never("build"), raising=False)
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", _argv(script, out))
    name = FIRST_REWRITTEN[script]
    with pytest.raises(
        SystemExit,
        match=re.escape(
            f"{name} has sha256 {RELEASE_20261006_SHA256[name]}, "
            f"not the pinned {pins.RUN_SHA256[name]}"
        ),
    ):
        module.main()
    assert not out.exists()


@pytest.mark.parametrize(
    ("attribute", "value", "message"),
    [
        ("CONFORMANCE_SHA256", "0" * 64, f"not the pinned {'0' * 64}"),
        ("RECORDS_COMMIT", pins.PASS_COMMIT, "cannot read"),
    ],
)
def test_build_proposals_refuses_another_conformance_scan(
    attribute, value, message, tmp_path, monkeypatch
):
    monkeypatch.setattr(pins, attribute, value)
    monkeypatch.setattr(proposals, "build", _never("build"))
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", _argv("build_proposals", out))
    with pytest.raises(SystemExit, match=re.escape(message)):
        proposals.main()
    assert not out.exists()


def test_definition_conformance_refuses_another_law_table(tmp_path, monkeypatch):
    monkeypatch.setattr(pins, "LAW_SHA256", "0" * 64)
    with pytest.raises(SystemExit, match=f"not the pinned {'0' * 64}"):
        conformance.stage_inputs(tmp_path / "inputs")


def test_build_proposals_never_writes_the_committed_records(monkeypatch, capsys):
    committed = (AUDIT / "proposed_changes.json").read_bytes()
    monkeypatch.setattr(proposals, "build", _never("build"))
    for target in (
        AUDIT / "proposed_changes.json",
        SCRIPTS / ".." / "proposed_changes.json",
    ):
        monkeypatch.setattr(sys, "argv", ["build_proposals", "--out", str(target)])
        with pytest.raises(SystemExit):
            proposals.main()
        assert "is pinned at sha256" in capsys.readouterr().err
    monkeypatch.setattr(sys, "argv", ["build_proposals"])
    with pytest.raises(SystemExit):
        proposals.main()
    assert (AUDIT / "proposed_changes.json").read_bytes() == committed
    assert hashlib.sha256(committed).hexdigest() == pins.PROPOSALS_SHA256


# ---------------------------------------------------------------------------
# The working tree is never read
# ---------------------------------------------------------------------------


def test_build_proposals_regenerates_the_committed_records_from_git(
    tmp_path, monkeypatch
):
    """The whole script, with every working-tree input fenced off, writes the
    committed proposed_changes.json byte for byte."""
    out = tmp_path / "proposed_changes.json"
    monkeypatch.setattr(sys, "argv", ["build_proposals", "--out", str(out)])
    with fenced():
        proposals.main()
    assert out.read_bytes() == (AUDIT / "proposed_changes.json").read_bytes()
    assert pins.sha256(out) == pins.PROPOSALS_SHA256


def test_definition_conformance_reads_only_staged_inputs(tmp_path):
    with fenced():
        staged = conformance.stage_inputs(tmp_path / "inputs")
        laws, meta = conformance.law_classifications(
            staged / "program_classification.json"
        )
    assert sorted(path.name for path in (staged / "run").iterdir()) == sorted(
        conformance.RUN_FILES
    )
    for name in conformance.RUN_FILES:
        assert pins.sha256(staged / "run" / name) == pins.RUN_SHA256[name]
    assert pins.sha256(staged / "benchmark_specs.json") == pins.SPECS_SHA256
    recorded = json.loads((VERIFICATION / "definition_conformance.json").read_text())
    assert meta == recorded["run"]["law_classification"]
    assert laws


def test_the_reference_system_is_built_from_staged_modules():
    expected = {Path(path).name: sha for path, sha in pins.FIXES_SHA256.items()}
    for module in (conformance, sources):
        with fenced():
            fix_dir = module._assemble_fixes()
        assert {path.name: pins.sha256(path) for path in fix_dir.iterdir()} == expected
    # definition_conformance records the hashes of the directory it built from.
    assert conformance._assemble_fixes() == conformance._FIX_DIR


def test_publication_sources_reads_only_staged_inputs(tmp_path):
    with fenced():
        run = sources.stage_inputs(tmp_path / "run")
        scored, sha = sources._scored_cells_from_payload(run / "data.json.gz")
    assert sorted(path.name for path in run.iterdir()) == sorted(sources.RUN_FILES)
    assert sha == pins.RUN_SHA256["data.json.gz"]
    assert len(scored) == sources.SCORED_CELLS
    reference = pd.read_csv(run / "reference_outputs.csv")
    exclusions = json.loads((run / "reference_exclusions.json").read_text())
    excluded = {(e["scenario_id"], e["variable"]) for e in exclusions["exclusions"]}
    keys = set(zip(reference["scenario_id"], reference["variable"]))
    assert scored == keys - excluded


def test_engine_probe_scores_the_pass_cells_not_202s(tmp_path, monkeypatch):
    """The probe's reproduction set comes from the pass's exclusion record.

    #202 later excluded scenario_043's payroll_tax; read from the working tree,
    the probe would drop it. The engine is stubbed to return the published
    references, so this runs without policyengine-us.
    """
    reference = pd.read_csv(
        io.BytesIO(
            pins.git_bytes(
                pins.PASS_COMMIT,
                f"{pins.RUN_PATH}/reference_outputs.csv",
                pins.RUN_SHA256["reference_outputs.csv"],
            )
        )
    )
    published = {
        row.variable: float(row.value)
        for row in reference[reference["scenario_id"] == "scenario_043"].itertuples()
    }
    engine = SimpleNamespace(
        build_situation=conformance.build_situation,
        _system=lambda: SimpleNamespace(variables={}),
        _simulation=lambda situation: None,
        _outputs=lambda sim, scenario, scored: {v: published[v] for v in scored},
        REPRODUCE_TOLERANCE=conformance.REPRODUCE_TOLERANCE,
    )
    monkeypatch.setattr(probe, "_conformance", lambda: engine)
    out = tmp_path / "probe.json"
    monkeypatch.setattr(
        sys, "argv", ["engine_probe", "scenario_043", "--out", str(out)]
    )
    with fenced():
        probe.main()
    committed = json.loads(
        (VERIFICATION / "probes/co_sales_tax_refund_scenario_043.json").read_text()
    )
    written = json.loads(out.read_text())
    assert "payroll_tax" in written["reproduction"]
    assert {
        variable: row["published"] for variable, row in written["reproduction"].items()
    } == {
        variable: row["published"]
        for variable, row in committed["reproduction"].items()
    }
    assert written["people"] == committed["people"]
    assert written["state"] == committed["state"] == "CO"


# ---------------------------------------------------------------------------
# Byte-for-byte regeneration (slow: the reference system, policyengine-us 2.15.17)
# ---------------------------------------------------------------------------


def _run(script: str, tmp_path: Path, *args: str) -> None:
    """Run a script with the fence armed in every one of its processes."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / f"{script}.py"), *args],
        cwd=ROOT,
        env=_fenced_env(tmp_path / "fence"),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-4000:]


def _identical_but(regenerated: Path, committed: Path, volatile: set[str]) -> dict:
    """Require the files byte for byte, except the one line carrying each key in
    ``volatile``; return the regenerated value of each of those keys."""
    new = regenerated.read_bytes().splitlines(keepends=True)
    old = committed.read_bytes().splitlines(keepends=True)
    assert len(new) == len(old), regenerated.name
    line = re.compile(rb'^\s*"(?P<key>[a-z_0-9]+)": (?P<value>.*?),?\n$')
    values = {}
    for key in volatile:
        lines = [
            i
            for i, text in enumerate(old)
            if re.match(rb'^\s*"' + key.encode() + rb'": ', text)
        ]
        assert len(lines) == 1, (committed.name, key)
        values[key] = json.loads(line.match(new[lines[0]])["value"])
    differing = [i for i, (a, b) in enumerate(zip(new, old)) if a != b]
    unexpected = [
        (i + 1, old[i][:120], new[i][:120])
        for i in differing
        if (match := line.match(old[i])) is None
        or match["key"].decode() not in volatile
    ]
    assert not unexpected, (regenerated.name, unexpected[:5])
    return values


@pytest.mark.slow
def test_definition_conformance_regenerates_byte_for_byte(tmp_path):
    """Only the wall time and this script's own sha256 differ from the record.

    About two to four minutes. Run with
      OPENBLAS_NUM_THREADS=1 uv run pytest -m slow \\
        tests/test_reference_adversary_inputs.py
    """
    _run("definition_conformance", tmp_path, "--out-dir", str(tmp_path))
    assert (tmp_path / "definition_conformance.md").read_bytes() == (
        VERIFICATION / "definition_conformance.md"
    ).read_bytes()
    values = _identical_but(
        tmp_path / "definition_conformance.json",
        VERIFICATION / "definition_conformance.json",
        {"seconds", "script_sha256"},
    )
    assert values["script_sha256"] == pins.sha256(SCRIPTS / "definition_conformance.py")


@pytest.mark.slow
def test_publication_sources_regenerates_byte_for_byte(tmp_path):
    """Only the wall time differs from the record. About four to ten minutes."""
    _run("publication_sources", tmp_path, "--out-dir", str(tmp_path))
    assert (tmp_path / "publication_sources.md").read_bytes() == (
        VERIFICATION / "publication_sources.md"
    ).read_bytes()
    _identical_but(
        tmp_path / "publication_sources.json",
        VERIFICATION / "publication_sources.json",
        {"seconds"},
    )


def _probe_args(path: Path) -> list[str]:
    """The arguments a committed probe records about itself."""
    record = json.loads(path.read_text())
    args = [record["scenario_id"], "--period", record["period"]]
    args += ["--variables", *record["variables"]]
    args += ["--parameters", *record["parameters"]]
    for assignment in record.get("counterfactual", {}).get("set", []):
        args += ["--set", assignment]
    return args


@pytest.mark.slow
@pytest.mark.parametrize("path", PROBES, ids=[path.stem for path in PROBES])
def test_every_probe_regenerates_byte_for_byte(path, tmp_path):
    """About a minute each."""
    assert len(PROBES) == 8
    out = tmp_path / path.name
    _run("engine_probe", tmp_path, *_probe_args(path), "--out", str(out))
    assert out.read_bytes() == path.read_bytes()
