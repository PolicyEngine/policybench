"""The October 5 audits' leaderboard impact comes from the passes' pinned inputs.

``scripts/leaderboard_impact.py`` in reference_audit/2026-10-05,
2026-10-05-louisiana, 2026-10-05-medicare-part-b and 2026-10-05-payroll each read
the frozen run as PASS_COMMIT (release dashboard-data-20260930, #187) committed it,
and their audits' own inputs as #202 merged them, each checked against its sha256.
They never read the working tree's run, which later releases rewrite: on the run
#202 left, three of them stop on duplicate exclusions and the Louisiana one rewrites
its evidence. CI checks out full history, so git holds every pinned input.
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
# #191's head; its reference_audit/2026-10-05/proposed_exclusions.json is the
# records the Part B and payroll passes scored.
PR191_HEAD = "8af912a062dd7ae1373de4c043ae2727d3406930"
EXCLUDE = frozenset({"reference_exclusions.json"})
REGENERATE = frozenset({"reference_outputs.csv", "reference_outputs.csv.meta.json"})


def _load(audit: str):
    path = ROOT / "reference_audit" / audit / "scripts/leaderboard_impact.py"
    name = "impact_" + audit.replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# For each audit: the flags its evidence was written with, the audit inputs it
# reads besides the run, each scratch copy's changed run files, and the summary
# fields that come from the inputs rather than from scoring.
AUDITS = {
    "2026-10-05": SimpleNamespace(
        flags=[],
        audit_inputs={"reference_audit/2026-10-05/proposed_exclusions.json"},
        extra_run_inputs=set(),
        copies={"base": frozenset(), "proposed": EXCLUDE},
        from_inputs=lambda summary: summary["proposed_exclusions"],
    ),
    "2026-10-05-louisiana": SimpleNamespace(
        flags=[],
        audit_inputs={
            "reference_audit/2026-10-05-louisiana/verification/"
            "sweep_la_standard_deduction.csv"
        },
        extra_run_inputs=set(),
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
    "2026-10-05-medicare-part-b": SimpleNamespace(
        flags=["--weights-check"],
        audit_inputs={
            "reference_audit/2026-10-05-medicare-part-b/proposed_exclusions.json",
            "reference_audit/2026-10-05-medicare-part-b/verification/sweep_part_b.csv",
            "reference_audit/2026-10-05-medicare-part-b/verification/inputs/"
            "pr191_proposed_exclusions.json",
        },
        extra_run_inputs={"analysis/impact_summary_by_model.csv"},
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
    "2026-10-05-payroll": SimpleNamespace(
        flags=["--with-salt"],
        audit_inputs={
            "reference_audit/2026-10-05-payroll/proposed_exclusions.json",
            "reference_audit/2026-10-05-payroll/proposed_regenerations.json",
            "reference_audit/2026-10-05/proposed_exclusions.json",
        },
        extra_run_inputs=set(),
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
MODULES = {audit: _load(audit) for audit in AUDITS}


def _verification(audit: str) -> Path:
    return ROOT / "reference_audit" / audit / "verification"


def _committed(audit: str) -> list[str]:
    """The evidence files the script writes (the Louisiana log is its stdout)."""
    return sorted(
        path.name
        for path in _verification(audit).glob("leaderboard_impact*")
        if path.suffix != ".log"
    )


def _argv(monkeypatch, audit: str, scratch: Path, out: Path) -> None:
    script = ROOT / "reference_audit" / audit / "scripts/leaderboard_impact.py"
    argv = [str(script), "--scratch", str(scratch), "--out-dir", str(out)]
    monkeypatch.setattr(sys, "argv", argv + AUDITS[audit].flags)


def _tampered_checkout(path: Path, impact) -> Path:
    """A checkout sharing this repository's objects whose working tree holds junk.

    Every file the script used to read from the working tree is junk, and every
    other file is absent, so a script that read any of them instead of git would
    fail or regenerate different evidence.
    """
    subprocess.run(
        ["git", "clone", "--quiet", "--shared", "--no-checkout", str(ROOT), str(path)],
        check=True,
    )
    for name in impact.INPUTS:
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


@pytest.mark.parametrize("audit", AUDITS)
def test_the_pins_cover_every_file_the_script_reads(audit, tmp_path):
    impact, spec = MODULES[audit], AUDITS[audit]
    run_inputs = RUN_FILES | spec.extra_run_inputs
    assert (
        set(impact.INPUTS)
        == {f"{RUN_PATH}/{name}" for name in run_inputs} | spec.audit_inputs
    )
    assert set(impact.RUN_FILES) == RUN_FILES - {"data.json.gz"}
    for path, (commit, _) in impact.INPUTS.items():
        expected = PASS_COMMIT if path.startswith(RUN_PATH) else AUDIT_COMMIT
        assert commit == expected, path

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


def test_the_run_pins_agree_across_the_audits_and_the_adversary():
    """Every script pins the same run bytes, and the payload the adversary pins."""
    run_pins = [
        {path: pin for path, pin in impact.INPUTS.items() if path.startswith(RUN_PATH)}
        for impact in MODULES.values()
    ]
    shared = set.intersection(*(set(pins) for pins in run_pins))
    assert shared == {f"{RUN_PATH}/{name}" for name in RUN_FILES}
    for path in shared:
        assert len({pins[path] for pins in run_pins}) == 1, path
    assert run_pins[0][f"{RUN_PATH}/data.json.gz"] == (PASS_COMMIT, FROZEN_SHA256)

    scripts = ROOT / "reference_audit/2026-10-05-reference-adversary/scripts"
    for name in ("definition_conformance.py", "publication_sources.py"):
        tree = ast.parse((scripts / name).read_text())
        pins = [
            node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and [target.id for target in node.targets] == ["PAYLOAD_SHA256"]
        ]
        assert pins == [FROZEN_SHA256], name


def test_the_salt_records_are_one_file_pinned_three_ways():
    """The SALT audit's proposals, Part B's copy of #191's records and the records
    the payroll script reads are the same bytes."""
    salt = MODULES["2026-10-05"].INPUTS[
        "reference_audit/2026-10-05/proposed_exclusions.json"
    ]
    part_b = MODULES["2026-10-05-medicare-part-b"]
    payroll = MODULES["2026-10-05-payroll"]
    assert part_b.INPUTS[part_b.SALT_COPY_PATH] == salt
    assert payroll.INPUTS[payroll.SALT_RECORDS] == salt
    assert part_b.SALT_SHA256 == payroll.SALT_SHA256 == salt[1]
    assert payroll.SALT_COMMIT == PR191_HEAD


def test_the_salt_pin_is_191s_head():
    """#191 was closed unmerged, so its head is only on its branch."""
    path = "reference_audit/2026-10-05/proposed_exclusions.json"
    shown = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{PR191_HEAD}:{path}"],
        capture_output=True,
    )
    if shown.returncode:
        pytest.skip(f"{PR191_HEAD[:12]} is not in this clone")
    digest = MODULES["2026-10-05-payroll"].SALT_SHA256
    assert hashlib.sha256(shown.stdout).hexdigest() == digest


@pytest.mark.parametrize("commit", sorted({PASS_COMMIT, AUDIT_COMMIT}))
def test_every_pinned_commit_is_on_main(commit):
    """No pin depends on a branch that may be deleted."""
    pinned = {pin[0] for impact in MODULES.values() for pin in impact.INPUTS.values()}
    assert pinned == {PASS_COMMIT, AUDIT_COMMIT}
    ancestor = subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"]
    )
    assert ancestor.returncode == 0, commit


@st.composite
def _edits(draw) -> tuple[str, str, str, int, int]:
    """One audit, one of its pinned inputs and one change to the input's bytes."""
    audit = draw(st.sampled_from(sorted(AUDITS)))
    path = draw(st.sampled_from(sorted(MODULES[audit].INPUTS)))
    kind = draw(st.sampled_from(["flip", "truncate", "append"]))
    commit = MODULES[audit].INPUTS[path][0]
    position = draw(st.integers(0, len(_pinned_bytes(commit, path)) - 1))
    return audit, path, kind, position, draw(st.integers(1, 255))


def _shown(stdout: bytes) -> SimpleNamespace:
    return SimpleNamespace(
        run=lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=stdout, stderr=b""
        )
    )


@settings(max_examples=60, deadline=None)
@given(_edits())
def test_any_changed_byte_in_a_pinned_input_is_refused_unwritten(edit):
    """Invariant: git_input writes a file only if its bytes are the pinned bytes."""
    audit, path, kind, position, byte = edit
    impact = MODULES[audit]
    commit, pinned = impact.INPUTS[path]
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
        with mock.patch.object(impact, "subprocess", _shown(tampered)):
            with pytest.raises(SystemExit, match="not the pinned"):
                impact.git_input(commit, path, pinned, target)
        assert not target.exists()
        # The unchanged bytes pass the same check.
        with mock.patch.object(impact, "subprocess", _shown(original)):
            impact.git_input(commit, path, pinned, target)
        assert target.read_bytes() == original


def _refusals(audit: str) -> list[tuple[str, tuple[str, str], str]]:
    impact, spec = MODULES[audit], AUDITS[audit]
    audit_input = sorted(spec.audit_inputs)[0]
    pinned = impact.INPUTS[audit_input][1]
    return [
        # #202's payload, which the working tree holds today.
        (
            f"{RUN_PATH}/data.json.gz",
            (AUDIT_COMMIT, FROZEN_SHA256),
            f"data.json.gz has sha256 {RELEASE_20261006_SHA256}, "
            f"not the pinned {FROZEN_SHA256}",
        ),
        # The audit's input before the audit existed.
        (audit_input, (PASS_COMMIT, pinned), "cannot read"),
        (audit_input, (AUDIT_COMMIT, "0" * 64), f"not the pinned {'0' * 64}"),
        (f"{RUN_PATH}/scenarios.csv", ("0" * 40, FROZEN_SHA256), "cannot read"),
    ]


@pytest.mark.parametrize(
    ("audit", "path", "pin", "message"),
    [(audit, *refusal) for audit in AUDITS for refusal in _refusals(audit)],
)
def test_pass_inputs_refuse_anything_but_the_pinned_bytes(
    tmp_path, monkeypatch, audit, path, pin, message
):
    impact = MODULES[audit]
    monkeypatch.setitem(impact.INPUTS, path, pin)
    with pytest.raises(SystemExit, match=re.escape(message)):
        impact.pass_inputs(tmp_path / "pass_inputs")


def _never(name: str):
    def call(*args, **kwargs):
        raise AssertionError(f"{name} ran after the inputs were refused")

    return call


@pytest.mark.parametrize("audit", AUDITS)
def test_a_refused_input_stops_the_script_before_it_scores(
    tmp_path, monkeypatch, audit
):
    impact = MODULES[audit]
    path = f"{RUN_PATH}/data.json.gz"
    monkeypatch.setitem(impact.INPUTS, path, (AUDIT_COMMIT, FROZEN_SHA256))
    for name in ("analyze", "always_zero", "stage"):
        if hasattr(impact, name):
            monkeypatch.setattr(impact, name, _never(name))
    out = tmp_path / "out"
    _argv(monkeypatch, audit, tmp_path / "scratch", out)
    with pytest.raises(SystemExit, match=f"not the pinned {FROZEN_SHA256}"):
        impact.main()
    assert not out.exists()


@pytest.mark.parametrize("audit", AUDITS)
def test_scratch_inside_the_repository_is_refused(tmp_path, monkeypatch, audit):
    impact = MODULES[audit]
    monkeypatch.setattr(impact, "pass_inputs", _never("pass_inputs"))
    _argv(monkeypatch, audit, ROOT / "results/scratch", tmp_path / "out")
    with pytest.raises(SystemExit) as stopped:
        impact.main()
    assert stopped.value.code == 2
    assert not (ROOT / "results/scratch").exists()


@pytest.mark.parametrize("audit", AUDITS)
def test_the_script_scores_only_the_staged_inputs(tmp_path, monkeypatch, audit):
    """Run from a checkout whose working tree is junk, every copy still starts from
    the pinned bytes, the inputs give the committed records, and the full set of
    evidence files is written."""
    impact, spec = MODULES[audit], AUDITS[audit]
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
    _argv(monkeypatch, audit, tmp_path / "scratch", out)
    impact.main()

    pinned = {name: impact.INPUTS[f"{RUN_PATH}/{name}"][1] for name in impact.RUN_FILES}
    assert set(scored) == set(spec.copies)
    for copy, digests in scored.items():
        changed = {name for name in pinned if digests[name] != pinned[name]}
        assert changed == spec.copies[copy], copy
    assert sorted(path.name for path in out.iterdir()) == _committed(audit)
    summary = json.loads((out / "leaderboard_impact.json").read_text())
    committed = json.loads(
        (_verification(audit) / "leaderboard_impact.json").read_text()
    )
    assert summary["published_reproduced"] is True
    assert spec.from_inputs(summary) == spec.from_inputs(committed)


@pytest.mark.slow
@pytest.mark.parametrize("audit", AUDITS)
def test_regeneration_reproduces_the_committed_evidence(tmp_path, audit):
    """Score every copy for real and require the committed files byte for byte.

    Runs from this checkout, whose run a later release has rewritten, so the
    evidence can only match if the script reads the pinned inputs. One to two
    minutes of ``policybench analyze`` runs per audit, so CI deselects it. Run it
    with
      OPENBLAS_NUM_THREADS=1 uv run pytest -m slow \\
        tests/test_reference_audit_impact.py
    """
    out = tmp_path / "out"
    script = ROOT / "reference_audit" / audit / "scripts/leaderboard_impact.py"
    result = subprocess.run(
        [sys.executable, str(script), "--scratch", str(tmp_path / "scratch")]
        + ["--out-dir", str(out), *AUDITS[audit].flags],
        cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=str(ROOT)),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-4000:]
    committed = _committed(audit)
    assert sorted(path.name for path in out.iterdir()) == committed
    if audit == "2026-10-05-louisiana":
        (out / "leaderboard_impact.log").write_text(result.stdout)
        committed.append("leaderboard_impact.log")
    differing = [
        name
        for name in committed
        if (out / name).read_bytes() != (_verification(audit) / name).read_bytes()
    ]
    if differing:
        first = differing[0]
        diff = difflib.unified_diff(
            (_verification(audit) / first).read_text().splitlines(),
            (out / first).read_text().splitlines(),
            f"committed/{first}",
            f"regenerated/{first}",
            lineterm="",
        )
        pytest.fail(
            f"{len(differing)} files differ: {differing}\n" + "\n".join(list(diff)[:60])
        )
