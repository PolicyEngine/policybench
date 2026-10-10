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
RUNNER = ROOT / "scripts/run_audit_claude.sh"
sys.path.insert(0, str(ROOT / "scripts"))

from freeze_snapshot import (  # noqa: E402
    audit_judge_provenance,
    verdict_provenance,
    verify_adjudications_keep_judge_verdicts,
)

from policybench.audit import (  # noqa: E402
    AUDIT_OUTPUT_SCHEMA,
    template_version_problems,
)
from policybench.judge_template import template_header  # noqa: E402

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


# Fake claude: reports a lane login, keeps a real-shaped session transcript
# where Claude Code does (the prompt it read as the one user text message,
# thinking and text turns at the requested effort, one StructuredOutput call
# and its result) and prints the CLI JSON envelope with the verdict. It reads
# its canned output from fake.json beside it: the runner gives claude calls an
# allowlisted environment. fake.json may also give the call another answer
# than the envelope's verdict, an environment snapshot and further events.
FAKE_CLAUDE = """
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
if args[:1] == ["--version"]:
    print("9.9.9 (fake)")
    sys.exit(0)
if args[:1] == ["auth"]:
    print(json.dumps(
        {"loggedIn": True, "authMethod": "oauth_token", "apiProvider": "firstParty"}
    ))
    sys.exit(0)
fake = json.loads(Path(__file__).with_name("fake.json").read_text())
prompt = sys.stdin.buffer.read().decode("utf-8")
effort = args[args.index("--effort") + 1]
envelope = json.loads(Path(fake["envelope"]).read_text())
verdict = envelope["structured_output"]
turns = [
    {"type": "thinking", "thinking": "", "signature": "sig"},
    {"type": "text", "text": json.dumps(verdict)},
    {"type": "tool_use", "id": "toolu_1", "name": "StructuredOutput",
     "input": fake.get("answer", verdict)},
]
events = [{"type": "user", "message": {"role": "user", "content": prompt}}]
if "snapshot" in fake:
    events.append({"type": "attachment", "attachment": {
        "type": "environment", "snapshot": fake["snapshot"]}})
events += [
    {"type": "assistant", "effort": effort,
     "message": {"role": "assistant", "content": [part]}}
    for part in turns
]
events.append({"type": "user", "message": {"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "toolu_1",
     "content": "Structured output provided successfully"}]}})
events += fake.get("events", [])
project = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "p"
project.mkdir(parents=True, exist_ok=True)
(project / (envelope["session_id"] + ".jsonl")).write_text(
    "".join(json.dumps(event) + "\\n" for event in events)
)
print(json.dumps(envelope))
"""


def _claude_audit(tmp_path: Path, **fake) -> tuple[Path, Path, dict]:
    """One case to judge, fake claude and codex CLIs and a lane config dir;
    ``fake`` adds to the fake claude's fake.json. Returns the audit directory,
    the case directory and the runners' environment."""
    audit_dir = tmp_path / "audit"
    cases = audit_dir / "cases"
    case_dir = cases / "us__scenario_001__snap"
    case_dir.mkdir(parents=True)
    (audit_dir / "schema.json").write_text(json.dumps(AUDIT_OUTPUT_SCHEMA))
    (audit_dir / "cases.jsonl").write_text(
        json.dumps(
            {
                "case_id": case_dir.name,
                "wrong_models": [m["model"] for m in VERDICT["models"]],
                "parse_failure_only": False,
            }
        )
        + "\n"
    )
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
    (bin_dir / "fake.json").write_text(
        json.dumps({"envelope": str(envelope_path), **fake})
    )
    (bin_dir / "claude").write_text(f"#!{sys.executable}\n{FAKE_CLAUDE}")
    (bin_dir / "claude").chmod(0o755)
    lane_config = tmp_path / "lane-config"
    lane_config.mkdir()
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
        "CLAUDE_CONFIG_DIR": str(lane_config),
        "AUDIT_ACCOUNT": "claude:lane@example.org",
    }
    return audit_dir, case_dir, env


@pytest.mark.skipif(sys.platform == "win32", reason="bash runners")
def test_rejudging_through_the_other_runner_replaces_provenance(tmp_path: Path):
    """Claude judges a case; the case is re-prepared (verdict gone, stale
    sidecar left behind as before the fix); Codex re-judges it. The published
    provenance must be Codex's, both in the sidecar and in the tally."""
    audit_dir, case_dir, env = _claude_audit(tmp_path)
    cases = audit_dir / "cases"

    claude = subprocess.run(
        ["bash", str(RUNNER), str(audit_dir)],
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
    assert (
        meta["prompt_sha256"]
        == hashlib.sha256((case_dir / "prompt.md").read_bytes()).hexdigest()
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
    # The fixture's prompt is no judge template's.
    assert meta["judge_template_version"] is None
    # The bytes Codex judged, from its private copy of prompt.md.
    assert (
        meta["prompt_sha256"]
        == hashlib.sha256((case_dir / "prompt.md").read_bytes()).hexdigest()
    )
    assert (
        meta["verdict_sha256"]
        == hashlib.sha256((case_dir / "verdict.json").read_bytes()).hexdigest()
    )
    assert {
        j: e["cases"] for j, e in audit_judge_provenance(cases)["by_judge"].items()
    } == {"gpt-5.6-sol": 1}


@pytest.mark.skipif(sys.platform == "win32", reason="bash runners")
@pytest.mark.parametrize(
    "fake, problem",
    [
        # The judge's one accepted answer is not the envelope's verdict.
        (
            {"answer": {**VERDICT, "rationale": "Another answer."}},
            "the verdict is not the judge's answer",
        ),
        # An event of a type the stage's isolated transcripts never carry.
        ({"events": [{"type": "progress", "data": {}}]}, "an event of type 'progress'"),
        # An e-mail address in an attachment other than the session context.
        (
            {
                "events": [
                    {
                        "type": "attachment",
                        "attachment": {
                            "type": "prompt_snapshot",
                            "systemPrompt": ["The user's email is max@example.org."],
                        },
                    }
                ]
            },
            "an e-mail address at line 6.attachment.systemPrompt[0]",
        ),
        # A key naming an account, nested in the environment snapshot.
        (
            {"snapshot": {"isGitRepo": False, "identity": {"accountUuid": "8f0c"}}},
            "key line 2.attachment.snapshot.identity.accountUuid",
        ),
    ],
)
def test_no_verdict_or_provenance_is_recorded_from_a_transcript_the_runner_rejects(
    tmp_path: Path, fake, problem
):
    """The runner writes a verdict and its sidecar only from a transcript whose
    one accepted answer is the verdict, whose events are all of the listed
    types and which carries no account data. Otherwise the case keeps no
    verdict and no provenance, and the tally counts no judge."""
    audit_dir, case_dir, env = _claude_audit(tmp_path, **fake)
    claude = subprocess.run(
        ["bash", str(RUNNER), str(audit_dir)],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )
    assert "[ok]" not in claude.stdout
    assert not (case_dir / "verdict.json").exists()
    assert not (case_dir / "verdict.meta.json").exists()
    assert audit_judge_provenance(audit_dir / "cases")["by_judge"] == {}
    assert problem in (case_dir / "claude.log").read_text()


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


def _adjudication(judge_source: str, judge_subtype: str) -> dict:
    return {
        "country": "us",
        "scenario_id": "scenario_001",
        "variable": "snap",
        "judge_failure_source": judge_source,
        "judge_failure_subtype": judge_subtype,
        "adjudicated_failure_source": "reference_engine_defect",
        "adjudicated_failure_subtype": "benefit_formula",
    }


def test_adjudication_keeps_the_judges_verdict_verbatim(tmp_path: Path):
    cases = tmp_path / "cases"
    _case(cases, "us__scenario_001__snap", VERDICT)
    verify_adjudications_keep_judge_verdicts(
        [_adjudication("llm_error", "thresholds_rates")], cases
    )
    # The adjudicated class recorded as the judge's is refused.
    with pytest.raises(SystemExit, match="judge said"):
        verify_adjudications_keep_judge_verdicts(
            [_adjudication("reference_engine_defect", "thresholds_rates")], cases
        )
    with pytest.raises(SystemExit, match="judge said"):
        verify_adjudications_keep_judge_verdicts(
            [_adjudication("llm_error", "benefit_formula")], cases
        )
    # So is an entry whose case has no verdict to keep.
    missing = dict(_adjudication("llm_error", "thresholds_rates"), variable="wic")
    with pytest.raises(SystemExit, match="no verdict"):
        verify_adjudications_keep_judge_verdicts([missing], cases)


def test_adjudication_flag_matches_the_verdict_or_names_its_run(tmp_path: Path):
    cases = tmp_path / "cases"
    _case(cases, "us__scenario_001__snap", VERDICT)  # the verdict does not flag
    entry = _adjudication("llm_error", "thresholds_rates")
    # A flag the current verdict does not raise must name the run that raised it.
    with pytest.raises(SystemExit, match="no earlier run is named"):
        verify_adjudications_keep_judge_verdicts(
            [dict(entry, judge_reference_suspect=True)], cases
        )
    verify_adjudications_keep_judge_verdicts(
        [
            dict(
                entry,
                judge_reference_suspect=True,
                judge_reference_suspect_source="an earlier judge run",
            )
        ],
        cases,
    )
    # A verdict that flags the reference must be recorded as flagged.
    flagged = dict(VERDICT, reference_suspect=True)
    _case(cases, "us__scenario_002__snap", flagged)
    with pytest.raises(SystemExit, match="judge_reference_suspect=False"):
        verify_adjudications_keep_judge_verdicts(
            [dict(entry, scenario_id="scenario_002", judge_reference_suspect=False)],
            cases,
        )


@pytest.mark.skipif(sys.platform == "win32", reason="bash runners")
def test_both_runners_record_the_judge_template_version(tmp_path: Path):
    """Each runner's sidecar records the template version of the prompt its
    verdict was judged on, so prepare_audit can render the case on it again."""
    audit_dir, case_dir, env = _claude_audit(tmp_path)
    for runner, version in (("run_audit_claude.sh", 2), ("run_audit_codex.sh", 1)):
        (case_dir / "verdict.json").unlink(missing_ok=True)
        (case_dir / "prompt.md").write_text(
            template_header(version) + "\nCOUNTRY: US\nClassify this miss.\n"
        )
        result = subprocess.run(
            ["bash", str(ROOT / "scripts" / runner), str(audit_dir)],
            capture_output=True,
            text=True,
            env=env,
            cwd=tmp_path,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        meta = json.loads((case_dir / "verdict.meta.json").read_text())
        assert meta["judge_runner"] == f"scripts/{runner}"
        assert meta["judge_template_version"] == version
        assert template_version_problems(audit_dir) == []


@pytest.mark.skipif(sys.platform == "win32", reason="bash runners")
def test_codex_publishes_no_verdict_for_a_prompt_rewritten_while_it_judged(
    tmp_path: Path,
):
    """Codex judges a v1 prompt; audit-prepare rewrites prompt.md to v2 while
    it runs. The verdict describes bytes prompt.md no longer holds, so the
    runner publishes neither it nor a sidecar, and leaves no copy behind."""
    audit_dir, case_dir, env = _claude_audit(tmp_path)
    v1 = template_header(1) + "\nCOUNTRY: US\nClassify this miss.\n"
    v2 = template_header(2) + "\nCOUNTRY: US\nClassify this miss.\n"
    (case_dir / "prompt.md").write_text(v1)
    rewrite = tmp_path / "v2.md"
    rewrite.write_text(v2)
    verdict = tmp_path / "canned_verdict.json"
    copies = tmp_path / "copies"
    copies.mkdir()
    _fake_cli(
        tmp_path / "bin" / "codex",
        'out=""; while [ $# -gt 0 ]; do'
        ' if [ "$1" = -o ]; then out="$2"; shift; fi; shift; done\n'
        "cat >/dev/null\n"
        'echo "model: gpt-5.6-sol"\n'
        f'cp "{rewrite}" "{case_dir / "prompt.md"}"\n'
        f'cat "{verdict}" > "$out"\n',
    )
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/run_audit_codex.sh"), str(audit_dir)],
        capture_output=True,
        text=True,
        env={**env, "TMPDIR": str(copies)},
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"[FAIL] {case_dir.name}" in result.stdout
    assert not (case_dir / "verdict.json").exists()
    assert not (case_dir / "verdict.meta.json").exists()
    assert list(copies.iterdir()) == []
    assert (case_dir / "prompt.md").read_text() == v2
