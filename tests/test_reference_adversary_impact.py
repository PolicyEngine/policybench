"""The reference adversary's leaderboard impact comes from the pass's pinned inputs.

``reference_audit/2026-10-05-reference-adversary/scripts/leaderboard_impact.py``
reads the frozen run as PASS_COMMIT (release dashboard-data-20260930, #187)
committed it and the proposals as #200 merged them, each checked against its
sha256. It never reads the working tree's run, which later releases rewrite
(#202 did). CI checks out full history, so git holds every pinned input.
"""

from __future__ import annotations

import difflib
import gzip
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "reference_audit/2026-10-05-reference-adversary"
SCRIPT = AUDIT / "scripts/leaderboard_impact.py"
VERIFICATION = AUDIT / "verification"
# The pins tests/test_consensus.py and tests/test_reference_adversary.py hold.
PASS_COMMIT = "8b4c0ca146bb6f66deba6ce24009d49d70d92df2"
FROZEN_SHA256 = "1e029aaa87d1dfbd2ceee88419599a919dd7c9d4aba78a308ec48d008d54ae18"
# Release dashboard-data-20261006 (#202) rewrote the run's payload and exclusions.
RELEASE_20261006_COMMIT = "9ce4ade8382962a9134860c23f56d92509b5e57f"
RELEASE_20261006_SHA256 = (
    "b1da3eae058c1a511f5579bc8235c822cf6862e33caf4840004bd0cf0f34c41d"
)
COMMITTED = sorted(path.name for path in VERIFICATION.glob("leaderboard_impact*"))


def _load_script():
    spec = importlib.util.spec_from_file_location("adversary_impact", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


impact = _load_script()


def _tampered_checkout(path: Path) -> Path:
    """A checkout sharing this repository's objects whose working tree holds junk.

    Its run directory and proposals are not the pass's inputs, so a script that
    read them instead of git would fail or regenerate different evidence.
    """
    subprocess.run(
        ["git", "clone", "--quiet", "--shared", "--no-checkout", str(ROOT), str(path)],
        check=True,
    )
    for name in impact.RUN_SHA256:
        junk = path / impact.RUN_PATH / name
        junk.parent.mkdir(parents=True, exist_ok=True)
        junk.write_bytes(b"not the pass's input\n")
    proposals = path / impact.PROPOSALS_PATH
    proposals.parent.mkdir(parents=True, exist_ok=True)
    proposals.write_text('{"root_causes": {}}\n')
    return path


def _argv(monkeypatch, tmp_path: Path) -> Path:
    out = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--scratch",
            str(tmp_path / "scratch"),
            "--out-dir",
            str(out),
        ],
    )
    return out


def test_the_pins_cover_every_file_the_script_reads(tmp_path):
    assert impact.PASS_COMMIT == PASS_COMMIT
    assert impact.RUN_SHA256["data.json.gz"] == FROZEN_SHA256
    assert set(impact.RUN_SHA256) == {*impact.RUN_FILES, "data.json.gz"}

    inputs = impact.pass_inputs(tmp_path / "pass_inputs")
    staged = sorted(
        path.relative_to(inputs).as_posix()
        for path in inputs.rglob("*")
        if path.is_file()
    )
    assert staged == sorted(
        [f"run/{name}" for name in impact.RUN_SHA256] + [impact.PROPOSALS_NAME]
    )
    for name, pinned in impact.RUN_SHA256.items():
        assert impact.sha256(inputs / "run" / name) == pinned
    assert impact.sha256(inputs / impact.PROPOSALS_NAME) == impact.PROPOSALS_SHA256
    # The README's frozen run: 46 models, 1,928 scored cells.
    payload = json.loads(gzip.decompress((inputs / "run/data.json.gz").read_bytes()))
    assert len(payload["modelStats"]) == 46
    assert {row["n"] for row in payload["modelStats"]} == {1928}

    (inputs / "stray").write_text("left over\n")
    impact.pass_inputs(inputs)
    assert not (inputs / "stray").exists()


@pytest.mark.parametrize(
    ("attribute", "value", "message"),
    [
        (
            "PASS_COMMIT",
            RELEASE_20261006_COMMIT,
            f"data.json.gz has sha256 {RELEASE_20261006_SHA256}, "
            f"not the pinned {FROZEN_SHA256}",
        ),
        ("PROPOSALS_SHA256", "0" * 64, f"not the pinned {'0' * 64}"),
        ("PASS_COMMIT", "0" * 40, "cannot read"),
    ],
)
def test_pass_inputs_refuse_anything_but_the_pinned_bytes(
    tmp_path, monkeypatch, attribute, value, message
):
    monkeypatch.setattr(impact, attribute, value)
    with pytest.raises(SystemExit, match=re.escape(message)):
        impact.pass_inputs(tmp_path / "pass_inputs")


def test_a_refused_input_stops_the_script_before_it_scores(tmp_path, monkeypatch):
    def analyze(run_dir):
        raise AssertionError(f"scored {run_dir} after its inputs were refused")

    monkeypatch.setattr(impact, "PASS_COMMIT", RELEASE_20261006_COMMIT)
    monkeypatch.setattr(impact, "analyze", analyze)
    out = _argv(monkeypatch, tmp_path)
    with pytest.raises(SystemExit, match=f"not the pinned {FROZEN_SHA256}"):
        impact.main()
    assert not out.exists()


def test_the_script_scores_only_the_staged_inputs(tmp_path, monkeypatch):
    """Run from a checkout whose working-tree run is junk, every variant still
    starts from the pinned bytes and the full set of evidence files is written."""
    monkeypatch.setattr(impact, "ROOT", _tampered_checkout(tmp_path / "checkout"))
    scored: dict[str, dict[str, str]] = {}
    published: dict = {}

    def analyze(run_dir: Path) -> dict:
        scored[run_dir.name] = {
            name: impact.sha256(run_dir / name) for name in impact.RUN_FILES
        }
        if not published:
            payload = run_dir.parent / "pass_inputs/run/data.json.gz"
            published.update(json.loads(gzip.decompress(payload.read_bytes())))
        return published

    monkeypatch.setattr(impact, "analyze", analyze)
    monkeypatch.setattr(
        impact, "always_zero", lambda run_dir: {"exact": 0.0, "within1pct": 0.0}
    )
    out = _argv(monkeypatch, tmp_path)
    impact.main()

    pinned = {name: impact.RUN_SHA256[name] for name in impact.RUN_FILES}
    assert scored.pop("published") == pinned
    exclusions = {"reference_exclusions.json"}
    regenerations = {"reference_outputs.csv", "reference_outputs.csv.meta.json"}
    expected = {
        "recommended": exclusions | regenerations,
        "exclude_all": exclusions,
    }
    assert set(scored) >= set(expected)
    for variant, digests in scored.items():
        changed = {name for name in pinned if digests[name] != pinned[name]}
        if variant.startswith("exclude__"):
            assert changed == exclusions, variant
        elif variant.startswith("regenerate__"):
            assert changed == regenerations, variant
        else:
            assert changed == expected[variant], variant
    assert sorted(path.name for path in out.iterdir()) == COMMITTED
    summary = json.loads((out / "leaderboard_impact.json").read_text())
    assert summary["published_reproduced"] is True
    assert summary["proposals"] == "proposed_changes.json"


@pytest.mark.slow
def test_regeneration_reproduces_the_committed_evidence(tmp_path):
    """Score every variant for real and require the committed files byte for byte.

    About five minutes of ``policybench analyze`` runs, so CI deselects it. Run it
    with
      OPENBLAS_NUM_THREADS=1 uv run pytest -m slow \\
        tests/test_reference_adversary_impact.py
    """
    assert len(COMMITTED) == 23
    out = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--scratch",
            str(tmp_path / "scratch"),
            "--out-dir",
            str(out),
        ],
        cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=str(ROOT)),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-4000:]
    assert sorted(path.name for path in out.iterdir()) == COMMITTED
    differing = [
        name
        for name in COMMITTED
        if (out / name).read_bytes() != (VERIFICATION / name).read_bytes()
    ]
    if differing:
        first = differing[0]
        diff = difflib.unified_diff(
            (VERIFICATION / first).read_text().splitlines(),
            (out / first).read_text().splitlines(),
            f"committed/{first}",
            f"regenerated/{first}",
            lineterm="",
        )
        pytest.fail(
            f"{len(differing)} files differ: {differing}\n" + "\n".join(list(diff)[:60])
        )
