"""The October 5 audits' scripts read the inputs their passes read, pinned in git.

Seven scripts in reference_audit/2026-10-05, 2026-10-05-louisiana,
2026-10-05-medicare-part-b and 2026-10-05-payroll read the frozen run as
PASS_COMMIT (release dashboard-data-20260930, #187) committed it, and their audits'
own inputs as #202 merged them. Each input is checked against its sha256:

- the four ``scripts/leaderboard_impact.py``, which score the run;
- the SALT and Part B audits' ``scripts/propose_exclusions.py`` and the payroll
  audit's ``scripts/model_answers.py``, which read it directly.

None reads the working tree's run, which later releases rewrite. On the run #202
left, three impact scripts and Part B's proposals stop on exclusions #202 installed.
The Louisiana impact script, the SALT proposals and the payroll answers rewrite
their committed files without an error. CI checks out full history, so git holds
every pinned input.
"""

from __future__ import annotations

import ast
import difflib
import gzip
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from functools import cache
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
# The pins tests/test_consensus.py and tests/test_reference_adversary.py hold.
PASS_COMMIT = "8b4c0ca146bb6f66deba6ce24009d49d70d92df2"
FROZEN_SHA256 = "1e029aaa87d1dfbd2ceee88419599a919dd7c9d4aba78a308ec48d008d54ae18"
# Release dashboard-data-20261006 (#202) merged the four audits, installed their
# eight records and rewrote the run's payload and exclusions.
AUDIT_COMMIT = "9ce4ade8382962a9134860c23f56d92509b5e57f"
RELEASE_20261006_SHA256 = (
    "b1da3eae058c1a511f5579bc8235c822cf6862e33caf4840004bd0cf0f34c41d"
)
RUN_PATH = (
    "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
RUN_FILES = {
    "data.json.gz",
    "predictions.csv.gz",
    "reference_outputs.csv",
    "reference_outputs.csv.meta.json",
    "reference_exclusions.json",
    "scenarios.csv",
    "scenarios.csv.meta.json",
}
# The run files #202 rewrote.
REWRITTEN = {f"{RUN_PATH}/data.json.gz", f"{RUN_PATH}/reference_exclusions.json"}
# #191's head; its reference_audit/2026-10-05/proposed_exclusions.json holds the
# records the Part B and payroll passes read.
PR191_HEAD = "8af912a062dd7ae1373de4c043ae2727d3406930"
SALT_RECORDS = "reference_audit/2026-10-05/proposed_exclusions.json"
EXCLUDE = frozenset({"reference_exclusions.json"})
REGENERATE = frozenset({"reference_outputs.csv", "reference_outputs.csv.meta.json"})
SALT = "reference_audit/2026-10-05"
LOUISIANA = "reference_audit/2026-10-05-louisiana"
PART_B = "reference_audit/2026-10-05-medicare-part-b"
PAYROLL = "reference_audit/2026-10-05-payroll"


def _run(*names: str) -> set[str]:
    return {f"{RUN_PATH}/{name}" for name in names}


# The scoring scripts: the flags their evidence was written with, every input,
# each scratch copy's changed run files, and the summary fields that come from
# the inputs rather than from scoring.
IMPACT = {
    SALT: SimpleNamespace(
        flags=[],
        inputs=_run(*RUN_FILES) | {SALT_RECORDS},
        copies={"base": frozenset(), "proposed": EXCLUDE},
        from_inputs=lambda summary: summary["proposed_exclusions"],
    ),
    LOUISIANA: SimpleNamespace(
        flags=[],
        inputs=_run(*RUN_FILES)
        | {f"{LOUISIANA}/verification/sweep_la_standard_deduction.csv"},
        copies={
            "keep": frozenset(),
            "ldr_published": REGENERATE,
            "ldr_official": REGENERATE,
            "hold_2025": REGENERATE,
            "exclude": EXCLUDE,
        },
        from_inputs=lambda summary: (
            summary["outputs"],
            summary["reference_values"],
            {k: v["exact_models"] for k, v in summary["options"].items()},
        ),
    ),
    PART_B: SimpleNamespace(
        flags=["--weights-check"],
        inputs=_run(*RUN_FILES, "analysis/impact_summary_by_model.csv")
        | {
            f"{PART_B}/proposed_exclusions.json",
            f"{PART_B}/verification/sweep_part_b.csv",
            f"{PART_B}/verification/inputs/pr191_proposed_exclusions.json",
        },
        copies={
            "published": frozenset(),
            "part_b": EXCLUDE,
            "salt": EXCLUDE,
            "salt_and_part_b": EXCLUDE,
            "weights_2_15_17": REGENERATE,
        },
        from_inputs=lambda summary: (
            [(case["case"], case["exclusions_added"]) for case in summary["cases"]],
            summary["impact_weights_check"]["impact_weights_replaced"],
        ),
    ),
    PAYROLL: SimpleNamespace(
        flags=["--with-salt"],
        inputs=_run(*RUN_FILES)
        | {
            f"{PAYROLL}/proposed_exclusions.json",
            f"{PAYROLL}/proposed_regenerations.json",
            SALT_RECORDS,
        },
        copies={
            "published": frozenset(),
            "salt": EXCLUDE,
            "exclude": EXCLUDE,
            "regenerate": REGENERATE,
            "exclude+salt": EXCLUDE,
            "regenerate+salt": EXCLUDE | REGENERATE,
        },
        from_inputs=lambda summary: (
            summary["salt_commit"],
            {
                name: (case["changed_outputs"], case["measured_against"])
                for name, case in summary.items()
                if isinstance(case, dict)
            },
        ),
    ),
}
# The scripts that read the run directly: every input, and every file they write
# (relative to --out-dir) with the committed file it must reproduce.
DIRECT = {
    f"{SALT}/scripts/propose_exclusions.py": SimpleNamespace(
        inputs=_run("reference_exclusions.json", "reference_outputs.csv")
        | {
            f"{SALT}/verification/sweep_salt_withholding.csv",
            f"{SALT}/verification/sweep_salt_withholding_households.json",
            f"{SALT}/verification/variants.json",
        },
        outputs={"proposed_exclusions.json": SALT_RECORDS},
    ),
    f"{PART_B}/scripts/propose_exclusions.py": SimpleNamespace(
        inputs=_run("predictions.csv.gz", "reference_exclusions.json")
        | {
            "app/src/modelMeta.ts",
            f"{PART_B}/verification/sweep_part_b_summary.json",
            f"{PART_B}/verification/sweep_part_b_households.json",
            f"{PART_B}/verification/inputs/pr191_proposed_exclusions.json",
        },
        outputs={
            "proposed_exclusions.json": f"{PART_B}/proposed_exclusions.json",
            "verification/model_answers.csv": (
                f"{PART_B}/verification/model_answers.csv"
            ),
        },
    ),
    f"{PAYROLL}/scripts/model_answers.py": SimpleNamespace(
        inputs=_run("data.json.gz")
        | {
            f"{PAYROLL}/verification/payroll_decomposition.csv",
            f"{PAYROLL}/program_classification.json",
        },
        outputs={
            "model_answers.csv": f"{PAYROLL}/verification/model_answers.csv",
            "model_answers_summary.json": (
                f"{PAYROLL}/verification/model_answers_summary.json"
            ),
        },
    ),
}


def _load(script: str):
    name = "pins_" + re.sub(r"\W", "_", script)
    spec = importlib.util.spec_from_file_location(name, ROOT / script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _impact_script(audit: str) -> str:
    return f"{audit}/scripts/leaderboard_impact.py"


MODULES = {
    **{_impact_script(audit): _load(_impact_script(audit)) for audit in IMPACT},
    **{script: _load(script) for script in DIRECT},
}
SPECS = {**{_impact_script(audit): spec for audit, spec in IMPACT.items()}, **DIRECT}


def _committed(audit: str) -> list[str]:
    """The evidence an impact script writes (the Louisiana log is its stdout)."""
    return sorted(
        path.name
        for path in (ROOT / audit / "verification").glob("leaderboard_impact*")
        if path.suffix != ".log"
    )


def _argv(monkeypatch, script: str, out: Path, *extra: str) -> None:
    argv = [str(ROOT / script), "--out-dir", str(out), *extra]
    monkeypatch.setattr(sys, "argv", argv)


def _impact_argv(monkeypatch, audit: str, scratch: Path, out: Path) -> None:
    flags = ["--scratch", str(scratch), *IMPACT[audit].flags]
    _argv(monkeypatch, _impact_script(audit), out, *flags)


def _tampered_checkout(path: Path, module) -> Path:
    """A checkout sharing this repository's objects whose working tree holds junk.

    Every file the script reads is junk in the working tree, and every other
    file is absent, so a script that read the working tree instead of git would
    fail or write something else.
    """
    subprocess.run(
        ["git", "clone", "--quiet", "--shared", "--no-checkout", str(ROOT), str(path)],
        check=True,
    )
    for name in module.INPUTS:
        junk = path / name
        junk.parent.mkdir(parents=True, exist_ok=True)
        junk.write_bytes(b"not the pass's input\n")
    return path


@cache
def _pinned_bytes(commit: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{path}"],
        capture_output=True,
        check=True,
    ).stdout


def _fetch(module, commit: str, path: str, pinned: str, target: Path) -> None:
    """Read one pinned input with the script's own git reader."""
    if hasattr(module, "git_input"):
        module.git_input(commit, path, pinned, target)
    else:
        content = module.git_bytes(commit, path, pinned)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


@pytest.mark.parametrize("script", SPECS)
def test_the_pins_cover_every_file_the_script_reads(script):
    module = MODULES[script]
    assert set(module.INPUTS) == SPECS[script].inputs
    for path, (commit, pinned) in module.INPUTS.items():
        on_run = path.startswith(RUN_PATH) or path == "app/src/modelMeta.ts"
        assert commit == (PASS_COMMIT if on_run else AUDIT_COMMIT), path
        assert hashlib.sha256(_pinned_bytes(commit, path)).hexdigest() == pinned, path


@pytest.mark.parametrize("audit", IMPACT)
def test_pass_inputs_stage_exactly_the_pinned_bytes(audit, tmp_path):
    impact = MODULES[_impact_script(audit)]
    assert set(impact.RUN_FILES) == RUN_FILES - {"data.json.gz"}
    inputs = impact.pass_inputs(tmp_path / "pass_inputs")
    staged = sorted(
        path.relative_to(inputs).as_posix()
        for path in inputs.rglob("*")
        if path.is_file()
    )
    assert staged == sorted(impact.INPUTS)
    for path, (_, pinned) in impact.INPUTS.items():
        assert impact.sha256(inputs / path) == pinned, path
    # The README's frozen run: 46 models, 1,928 scored outputs each.
    payload = json.loads(
        gzip.decompress((inputs / RUN_PATH / "data.json.gz").read_bytes())
    )
    assert len(payload["modelStats"]) == 46
    assert {row["n"] for row in payload["modelStats"]} == {1928}

    (inputs / "stray").write_text("left over\n")
    impact.pass_inputs(inputs)
    assert not (inputs / "stray").exists()


def test_the_pins_agree_across_the_scripts_and_with_the_adversary():
    """Every script pins a shared input to the same commit and bytes, and the
    payload is the one the reference adversary's scripts pin."""
    pins: dict[str, set] = {}
    for module in MODULES.values():
        for path, pin in module.INPUTS.items():
            pins.setdefault(path, set()).add(pin)
    assert {path: len(found) for path, found in pins.items() if len(found) > 1} == {}
    assert pins[f"{RUN_PATH}/data.json.gz"] == {(PASS_COMMIT, FROZEN_SHA256)}

    scripts = ROOT / "reference_audit/2026-10-05-reference-adversary/scripts"
    for name in ("definition_conformance.py", "publication_sources.py"):
        tree = ast.parse((scripts / name).read_text())
        found = [
            node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and [target.id for target in node.targets] == ["PAYLOAD_SHA256"]
        ]
        assert found == [FROZEN_SHA256], name


def test_the_salt_records_are_one_file_pinned_four_ways():
    """The SALT audit's proposals, Part B's copy of #191's records (read by two
    scripts) and the records the payroll script reads are the same bytes."""
    salt = MODULES[_impact_script(SALT)].INPUTS[SALT_RECORDS]
    copy = f"{PART_B}/verification/inputs/pr191_proposed_exclusions.json"
    assert MODULES[_impact_script(PART_B)].INPUTS[copy] == salt
    assert MODULES[f"{PART_B}/scripts/propose_exclusions.py"].INPUTS[copy] == salt
    assert MODULES[_impact_script(PAYROLL)].INPUTS[SALT_RECORDS] == salt
    assert MODULES[_impact_script(PAYROLL)].SALT_COMMIT == PR191_HEAD
    for script in (_impact_script(PART_B), f"{PART_B}/scripts/propose_exclusions.py"):
        assert MODULES[script].SALT_SHA256 == salt[1]


def test_the_salt_pin_is_191s_head():
    """#191 was closed unmerged, so its head is only on its branch."""
    shown = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{PR191_HEAD}:{SALT_RECORDS}"],
        capture_output=True,
    )
    if shown.returncode:
        pytest.skip(f"{PR191_HEAD[:12]} is not in this clone")
    pinned = MODULES[_impact_script(PAYROLL)].SALT_SHA256
    assert hashlib.sha256(shown.stdout).hexdigest() == pinned


@pytest.mark.parametrize("commit", [PASS_COMMIT, AUDIT_COMMIT])
def test_every_pinned_commit_is_on_main(commit):
    """No pin depends on a branch that may be deleted."""
    pinned = {pin[0] for module in MODULES.values() for pin in module.INPUTS.values()}
    assert pinned == {PASS_COMMIT, AUDIT_COMMIT}
    ancestor = subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"]
    )
    assert ancestor.returncode == 0, commit


@st.composite
def _edits(draw) -> tuple[str, str, str, int, int]:
    """One script, one of its pinned inputs and one change to the input's bytes."""
    script = draw(st.sampled_from(sorted(MODULES)))
    path = draw(st.sampled_from(sorted(MODULES[script].INPUTS)))
    kind = draw(st.sampled_from(["flip", "truncate", "append"]))
    commit = MODULES[script].INPUTS[path][0]
    position = draw(st.integers(0, len(_pinned_bytes(commit, path)) - 1))
    return script, path, kind, position, draw(st.integers(1, 255))


def _shown(stdout: bytes) -> SimpleNamespace:
    return SimpleNamespace(
        run=lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=stdout, stderr=b""
        )
    )


@settings(max_examples=80, deadline=None)
@given(_edits())
def test_any_changed_byte_in_a_pinned_input_is_refused(edit):
    """Invariant: a script's git reader returns or writes only the pinned bytes."""
    script, path, kind, position, byte = edit
    module = MODULES[script]
    commit, pinned = module.INPUTS[path]
    original = _pinned_bytes(commit, path)
    if kind == "flip":
        changed = bytearray(original)
        changed[position] ^= byte
        tampered = bytes(changed)
    elif kind == "truncate":
        tampered = original[:position]
    else:
        tampered = original + bytes([byte])
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "staged" / Path(path).name
        with mock.patch.object(module, "subprocess", _shown(tampered)):
            with pytest.raises(SystemExit, match="not the pinned"):
                _fetch(module, commit, path, pinned, target)
        assert not target.exists()
        # The unchanged bytes pass the same check.
        with mock.patch.object(module, "subprocess", _shown(original)):
            _fetch(module, commit, path, pinned, target)
        assert target.read_bytes() == original


def _refusals(script: str) -> list[tuple[str, tuple[str, str], str]]:
    module = MODULES[script]
    rewritten = sorted(REWRITTEN & set(module.INPUTS))[0]
    pinned = module.INPUTS[rewritten][1]
    current = hashlib.sha256(_pinned_bytes(AUDIT_COMMIT, rewritten)).hexdigest()
    own = sorted(path for path in module.INPUTS if path.startswith("reference_audit"))
    return [
        # The file as #202 rewrote it, which the working tree holds today.
        (
            rewritten,
            (AUDIT_COMMIT, pinned),
            f"has sha256 {current}, not the pinned {pinned}",
        ),
        # The audit's own input before the audit existed.
        (own[0], (PASS_COMMIT, module.INPUTS[own[0]][1]), "cannot read"),
        (own[0], (AUDIT_COMMIT, "0" * 64), f"not the pinned {'0' * 64}"),
        (rewritten, ("0" * 40, pinned), "cannot read"),
    ]


@pytest.mark.parametrize(
    ("audit", "path", "pin", "message"),
    [
        (audit, *refusal)
        for audit in IMPACT
        for refusal in _refusals(_impact_script(audit))
    ],
)
def test_pass_inputs_refuse_anything_but_the_pinned_bytes(
    tmp_path, monkeypatch, audit, path, pin, message
):
    impact = MODULES[_impact_script(audit)]
    monkeypatch.setitem(impact.INPUTS, path, pin)
    with pytest.raises(SystemExit, match=re.escape(message)):
        impact.pass_inputs(tmp_path / "pass_inputs")


def _never(name: str):
    def call(*args, **kwargs):
        raise AssertionError(f"{name} ran after the inputs were refused")

    return call


@pytest.mark.parametrize(
    ("audit", "path"),
    [(audit, path) for audit in IMPACT for path in IMPACT[audit].inputs],
)
def test_any_refused_input_stops_the_impact_script_before_it_scores(
    tmp_path, monkeypatch, audit, path
):
    impact = MODULES[_impact_script(audit)]
    commit, _ = impact.INPUTS[path]
    monkeypatch.setitem(impact.INPUTS, path, (commit, "0" * 64))
    for name in ("analyze", "always_zero", "stage"):
        if hasattr(impact, name):
            monkeypatch.setattr(impact, name, _never(name))
    out = tmp_path / "out"
    _impact_argv(monkeypatch, audit, tmp_path / "scratch", out)
    with pytest.raises(SystemExit, match=f"{re.escape(path)} has sha256 .* not the"):
        impact.main()
    assert not out.exists()


@pytest.mark.parametrize(
    ("script", "path"),
    [(script, path) for script in DIRECT for path in DIRECT[script].inputs],
)
def test_any_refused_input_stops_the_direct_script_before_it_writes(
    tmp_path, monkeypatch, script, path
):
    module = MODULES[script]
    commit, _ = module.INPUTS[path]
    monkeypatch.setitem(module.INPUTS, path, (commit, "0" * 64))
    out = tmp_path / "out"
    _argv(monkeypatch, script, out)
    with pytest.raises(SystemExit, match=f"{re.escape(path)} has sha256 .* not the"):
        module.main()
    assert not out.exists()


@pytest.mark.parametrize(
    ("script", "path", "pin", "message"),
    [(script, *refusal) for script in DIRECT for refusal in _refusals(script)],
)
def test_a_refused_input_stops_the_direct_script_before_it_writes(
    tmp_path, monkeypatch, script, path, pin, message
):
    module = MODULES[script]
    monkeypatch.setitem(module.INPUTS, path, pin)
    out = tmp_path / "out"
    _argv(monkeypatch, script, out)
    with pytest.raises(SystemExit, match=re.escape(message)):
        module.main()
    assert not out.exists()


@pytest.mark.parametrize("audit", IMPACT)
def test_scratch_inside_the_repository_is_refused(tmp_path, monkeypatch, audit):
    impact = MODULES[_impact_script(audit)]
    monkeypatch.setattr(impact, "pass_inputs", _never("pass_inputs"))
    _impact_argv(monkeypatch, audit, ROOT / "results/scratch", tmp_path / "out")
    with pytest.raises(SystemExit) as stopped:
        impact.main()
    assert stopped.value.code == 2
    assert not (ROOT / "results/scratch").exists()


@pytest.mark.parametrize("audit", IMPACT)
def test_the_impact_script_scores_only_the_staged_inputs(tmp_path, monkeypatch, audit):
    """Run from a checkout whose working tree is junk, every copy still starts from
    the pinned bytes, the inputs give the committed records, and the full set of
    evidence files is written."""
    impact, spec = MODULES[_impact_script(audit)], IMPACT[audit]
    monkeypatch.setattr(impact, "ROOT", _tampered_checkout(tmp_path / "co", impact))
    scored: dict[str, dict[str, str]] = {}
    published: dict = {}

    def analyze(run_dir: Path) -> dict:
        scored[run_dir.name] = {
            name: impact.sha256(run_dir / name) for name in impact.RUN_FILES
        }
        if not published:
            payload = run_dir.parent / "pass_inputs" / RUN_PATH / "data.json.gz"
            published.update(json.loads(gzip.decompress(payload.read_bytes())))
        return published

    monkeypatch.setattr(impact, "analyze", analyze)
    if hasattr(impact, "always_zero"):
        monkeypatch.setattr(
            impact, "always_zero", lambda run_dir: {"exact": 0.0, "within1pct": 0.0}
        )
    if hasattr(impact, "legacy_impact_summary"):
        # The freeze's summary, scored by scripts/freeze_snapshot.py from the
        # checkout; here the pinned frozen file stands in for it.
        frozen = tmp_path / "scratch/pass_inputs" / impact.FROZEN_IMPACT_PATH
        monkeypatch.setattr(
            impact, "legacy_impact_summary", lambda run_dir: pd.read_csv(frozen)
        )
    out = tmp_path / "out"
    _impact_argv(monkeypatch, audit, tmp_path / "scratch", out)
    impact.main()

    pinned = {name: impact.INPUTS[f"{RUN_PATH}/{name}"][1] for name in impact.RUN_FILES}
    assert set(scored) == set(spec.copies)
    for copy, digests in scored.items():
        changed = {name for name in pinned if digests[name] != pinned[name]}
        assert changed == spec.copies[copy], copy
    assert sorted(path.name for path in out.iterdir()) == _committed(audit)
    summary = json.loads((out / "leaderboard_impact.json").read_text())
    committed = json.loads(
        (ROOT / audit / "verification/leaderboard_impact.json").read_text()
    )
    assert summary["published_reproduced"] is True
    assert spec.from_inputs(summary) == spec.from_inputs(committed)


@pytest.mark.parametrize("script", DIRECT)
def test_the_direct_script_reproduces_its_files_from_a_junk_checkout(
    tmp_path, monkeypatch, script
):
    """Run for real from a checkout whose working tree is junk: every file the
    script writes is the committed one, byte for byte."""
    module = MODULES[script]
    monkeypatch.setattr(module, "ROOT", _tampered_checkout(tmp_path / "co", module))
    out = tmp_path / "out"
    _argv(monkeypatch, script, out)
    module.main()
    written = sorted(
        path.relative_to(out).as_posix() for path in out.rglob("*") if path.is_file()
    )
    assert written == sorted(DIRECT[script].outputs)
    for name, committed in DIRECT[script].outputs.items():
        assert (out / name).read_bytes() == (ROOT / committed).read_bytes(), name


@pytest.mark.slow
@pytest.mark.parametrize("audit", IMPACT)
def test_regeneration_reproduces_the_committed_evidence(tmp_path, audit):
    """Score every copy for real and require the committed files byte for byte.

    Runs from this checkout, whose run a later release has rewritten, so the
    evidence can only match if the script reads the pinned inputs. One to two
    minutes of ``policybench analyze`` runs per audit, so CI deselects it. Run it
    with
      OPENBLAS_NUM_THREADS=1 uv run pytest -m slow \\
        tests/test_reference_audit_pins.py
    """
    out = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, str(ROOT / _impact_script(audit))]
        + ["--scratch", str(tmp_path / "scratch"), "--out-dir", str(out)]
        + IMPACT[audit].flags,
        cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=str(ROOT)),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-4000:]
    committed = _committed(audit)
    assert sorted(path.name for path in out.iterdir()) == committed
    if audit == LOUISIANA:
        (out / "leaderboard_impact.log").write_text(result.stdout)
        committed.append("leaderboard_impact.log")
    verification = ROOT / audit / "verification"
    differing = [
        name
        for name in committed
        if (out / name).read_bytes() != (verification / name).read_bytes()
    ]
    if differing:
        first = differing[0]
        diff = difflib.unified_diff(
            (verification / first).read_text().splitlines(),
            (out / first).read_text().splitlines(),
            f"committed/{first}",
            f"regenerated/{first}",
            lineterm="",
        )
        pytest.fail(
            f"{len(differing)} files differ: {differing}\n" + "\n".join(list(diff)[:60])
        )
