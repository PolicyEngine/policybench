"""Judge provenance follows the verdict it describes, across both runners."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from freeze_snapshot import audit_judge_provenance, verdict_provenance  # noqa: E402

from policybench.audit import AUDIT_OUTPUT_SCHEMA  # noqa: E402

VERDICT = {
    "reference_suspect": False,
    "reference_bug_hypothesis": "",
    "case_failure_source": "llm_error",
    "case_failure_subtype": "thresholds_rates",
    "rationale": "Both models used last year's threshold.",
    "models": [
        {
            "model": "m1",
            "failure_source": "llm_error",
            "failure_subtype": "thresholds_rates",
            "diagnosis": "Applied the 2025 threshold instead of the 2026 one.",
        }
    ],
}


def _case(cases: Path, name: str, verdict: dict) -> Path:
    case_dir = cases / name
    case_dir.mkdir(parents=True)
    (case_dir / "verdict.json").write_text(
        json.dumps(verdict, indent=2, sort_keys=True)
    )
    return case_dir


def _sidecar(case_dir: Path, *, model: str, runner: str, bound: bool) -> None:
    meta = {
        "judge_runner": runner,
        "judge_model_requested": model,
        "judge_model_reported": ["claude-opus-5"] if model == "opus" else [model],
        "judged_at_utc": "2026-09-05T02:40:00+00:00",
    }
    if bound:
        meta["verdict_sha256"] = hashlib.sha256(
            (case_dir / "verdict.json").read_bytes()
        ).hexdigest()
    (case_dir / "verdict.meta.json").write_text(json.dumps(meta))


def _codex_log(case_dir: Path, model: str) -> None:
    (case_dir / "codex.log").write_text(
        f"OpenAI Codex v0.144.0\n--------\nmodel: {model}\n"
    )


def test_sidecar_counts_only_when_bound_to_the_current_verdict(tmp_path: Path):
    cases = tmp_path / "cases"
    fresh = _case(cases, "fresh_claude", VERDICT)
    _sidecar(fresh, model="opus", runner="scripts/run_audit_claude.sh", bound=True)
    _codex_log(fresh, "gpt-5.6-sol")  # an older Codex attempt; the sidecar wins

    stale = _case(
        cases, "stale_claude_then_codex", {**VERDICT, "case_rationale": "new"}
    )
    _sidecar(stale, model="opus", runner="scripts/run_audit_claude.sh", bound=False)
    (stale / "verdict.meta.json").write_text(
        json.dumps(
            {
                "judge_runner": "scripts/run_audit_claude.sh",
                "judge_model_requested": "opus",
                "judge_model_reported": ["claude-opus-5"],
                "judged_at_utc": "2026-09-05T02:40:00+00:00",
                "verdict_sha256": "0" * 64,
            }
        )
    )
    _codex_log(stale, "gpt-5.6-sol")

    legacy = _case(cases, "legacy_sidecar_no_hash", VERDICT)
    _sidecar(legacy, model="opus", runner="scripts/run_audit_claude.sh", bound=False)

    codex = _case(cases, "codex_sidecar", VERDICT)
    _sidecar(codex, model="default", runner="scripts/run_audit_codex.sh", bound=True)
    (codex / "verdict.meta.json").write_text(
        json.dumps(
            {
                "judge_runner": "scripts/run_audit_codex.sh",
                "judge_model_requested": "default",
                "judge_model_reported": ["gpt-5.6-sol"],
                "judged_at_utc": "2026-09-05T03:00:00+00:00",
                "verdict_sha256": hashlib.sha256(
                    (codex / "verdict.json").read_bytes()
                ).hexdigest(),
            }
        )
    )

    assert verdict_provenance(fresh) is not None
    assert verdict_provenance(stale) is None
    assert verdict_provenance(legacy) is None

    tally = audit_judge_provenance(cases)
    assert tally["cases_judged"] == 4
    by_judge = {judge: entry["cases"] for judge, entry in tally["by_judge"].items()}
    # fresh -> Opus via bound sidecar; stale -> unknown (a sidecar that does
    # not match the verdict is not provenance, and its presence rules out the
    # codex.log fallback); legacy -> unknown (no hash); codex -> Sol.
    assert by_judge == {"claude-opus-5": 1, "gpt-5.6-sol": 1, "unknown": 2}


def _fake_cli(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


@pytest.mark.skipif(sys.platform == "win32", reason="bash runners")
def test_rejudging_through_the_other_runner_replaces_provenance(tmp_path: Path):
    """Claude judges a case; the case is re-prepared (verdict gone, stale
    sidecar left behind as before the fix); Codex re-judges it. The published
    provenance must be Codex's, both in the sidecar and in the tally."""
    audit_dir = tmp_path / "audit"
    cases = audit_dir / "cases"
    case_dir = cases / "us__scenario_001__snap"
    case_dir.mkdir(parents=True)
    (audit_dir / "schema.json").write_text(json.dumps(AUDIT_OUTPUT_SCHEMA))
    (case_dir / "prompt.md").write_text("Classify this miss.\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Fake CLIs read their canned output from files, so the verdict text (which
    # contains an apostrophe) never passes through shell quoting.
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(
        json.dumps(
            {
                "structured_output": VERDICT,
                "modelUsage": {"claude-opus-5": {}},
                "session_id": "s",
            }
        )
    )
    verdict_path = tmp_path / "canned_verdict.json"
    verdict_path.write_text(json.dumps(VERDICT))
    # Fake claude: prints the CLI JSON envelope with the structured verdict.
    _fake_cli(
        bin_dir / "claude",
        'if [ "$1" = --version ]; then echo "9.9.9 (fake)"; exit 0; fi\n'
        f'cat >/dev/null; cat "{envelope_path}"\n',
    )
    # Fake codex: writes the -o file and logs its model header to stdout.
    _fake_cli(
        bin_dir / "codex",
        'out=""; while [ $# -gt 0 ]; do'
        ' if [ "$1" = -o ]; then out="$2"; shift; fi; shift; done\n'
        "cat >/dev/null\n"
        'echo "OpenAI Codex v0.144.0"; echo "--------"; echo "model: gpt-5.6-sol"\n'
        f'cat "{verdict_path}" > "$out"\n',
    )
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "AUDIT_PYTHON": sys.executable,
        "AUDIT_PARALLEL": "1",
    }

    claude = subprocess.run(
        ["bash", str(ROOT / "scripts/run_audit_claude.sh"), str(audit_dir)],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )
    assert claude.returncode == 0, claude.stderr + claude.stdout
    meta = json.loads((case_dir / "verdict.meta.json").read_text())
    assert meta["judge_runner"] == "scripts/run_audit_claude.sh"
    assert (
        meta["verdict_sha256"]
        == hashlib.sha256((case_dir / "verdict.json").read_bytes()).hexdigest()
    )
    assert {
        j: e["cases"] for j, e in audit_judge_provenance(cases)["by_judge"].items()
    } == {"claude-opus-5": 1}

    # Re-prepared case: the verdict is gone but (as before the fix) the sidecar
    # was left behind. Codex re-judges.
    (case_dir / "verdict.json").unlink()
    codex = subprocess.run(
        ["bash", str(ROOT / "scripts/run_audit_codex.sh"), str(audit_dir)],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )
    assert codex.returncode == 0, codex.stderr + codex.stdout
    meta = json.loads((case_dir / "verdict.meta.json").read_text())
    assert meta["judge_runner"] == "scripts/run_audit_codex.sh"
    assert meta["judge_model_reported"] == ["gpt-5.6-sol"]
    assert (
        meta["verdict_sha256"]
        == hashlib.sha256((case_dir / "verdict.json").read_bytes()).hexdigest()
    )
    assert {
        j: e["cases"] for j, e in audit_judge_provenance(cases)["by_judge"].items()
    } == {"gpt-5.6-sol": 1}


def _touch(path: Path, when: float) -> None:
    os.utime(path, (when, when))


def test_log_fallback_needs_a_contemporaneous_log_and_no_sidecar(tmp_path: Path):
    """A hash-less sidecar beside an older codex.log (a legacy Codex-to-Claude
    re-judge) is unknown, not Codex; a sidecar-less verdict is Codex only when
    its log was written alongside it."""
    cases = tmp_path / "cases"
    now = 1_800_000_000.0

    claude_legacy = _case(cases, "legacy_claude_after_codex", VERDICT)
    _sidecar(
        claude_legacy, model="opus", runner="scripts/run_audit_claude.sh", bound=False
    )
    _codex_log(claude_legacy, "gpt-5.6-sol")
    _touch(claude_legacy / "codex.log", now - 86_400)
    _touch(claude_legacy / "verdict.json", now)

    codex_fresh = _case(cases, "codex_no_sidecar_fresh_log", VERDICT)
    _codex_log(codex_fresh, "gpt-5.6-sol")
    _touch(codex_fresh / "codex.log", now - 30)
    _touch(codex_fresh / "verdict.json", now)

    codex_old = _case(cases, "codex_no_sidecar_stale_log", VERDICT)
    _codex_log(codex_old, "gpt-5.6-sol")
    _touch(codex_old / "codex.log", now - 86_400)
    _touch(codex_old / "verdict.json", now)

    tally = audit_judge_provenance(cases)
    by_judge = {judge: entry["cases"] for judge, entry in tally["by_judge"].items()}
    assert by_judge == {"gpt-5.6-sol": 1, "unknown": 2}


def test_backfill_binds_only_with_ownership_evidence(tmp_path: Path):
    from backfill_verdict_provenance import backfill

    cases = tmp_path / "cases"
    now = 1_800_000_000.0
    judged_at = "2027-01-15T00:00:00+00:00"
    import datetime

    judged_ts = datetime.datetime.fromisoformat(judged_at).timestamp()

    def legacy_claude(name: str, *, log_offset: float | None) -> Path:
        case_dir = _case(cases, name, VERDICT)
        (case_dir / "verdict.meta.json").write_text(
            json.dumps(
                {
                    "judge_runner": "scripts/run_audit_claude.sh",
                    "judge_model_requested": "opus",
                    "judge_model_reported": ["claude-opus-5"],
                    "judged_at_utc": judged_at,
                }
            )
        )
        _touch(case_dir / "verdict.json", judged_ts + 5)
        if log_offset is not None:
            _codex_log(case_dir, "gpt-5.6-sol")
            _touch(case_dir / "codex.log", judged_ts + log_offset)
        return case_dir

    bound = legacy_claude("claude_then_nothing", log_offset=None)
    bound_older_log = legacy_claude("codex_then_claude", log_offset=-3_600)
    # Codex re-judged two minutes after the Claude sidecar was written: the
    # sidecar does not own the current verdict, however close the times are.
    contested = legacy_claude("claude_then_codex", log_offset=120)
    _touch(contested / "verdict.json", judged_ts + 125)

    codex_only = _case(cases, "codex_only", VERDICT)
    _codex_log(codex_only, "gpt-5.6-sol")
    _touch(codex_only / "codex.log", now - 86_400)
    _touch(codex_only / "verdict.json", now)

    counts = backfill(cases, tolerance=600.0, dry_run=False)
    assert counts == {
        "bound": 2,
        "codex_sidecar_written": 1,
        "left_alone": 1,
        "already": 0,
    }
    for case_dir in (bound, bound_older_log):
        assert verdict_provenance(case_dir)["judge_model_requested"] == "opus"
    assert "verdict_sha256" not in json.loads(
        (contested / "verdict.meta.json").read_text()
    )
    assert verdict_provenance(codex_only)["judge_model_reported"] == ["gpt-5.6-sol"]

    tally = audit_judge_provenance(cases)
    by_judge = {judge: entry["cases"] for judge, entry in tally["by_judge"].items()}
    assert by_judge == {"claude-opus-5": 2, "gpt-5.6-sol": 1, "unknown": 1}
    # Idempotent: a second pass changes nothing.
    assert backfill(cases, tolerance=600.0, dry_run=False)["already"] == 3
