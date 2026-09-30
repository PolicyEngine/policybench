"""scripts/run_audit_claude.sh isolates each judge and bills only the lane.

A fake claude CLI records the command line, working directory and environment
of every judge call, writes the session transcript where Claude Code keeps it
and answers with a canned verdict.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from policybench.audit import AUDIT_OUTPUT_SCHEMA

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_audit_claude.sh"
CASES = ("us__scenario_000__snap", "us__scenario_001__ssi")
VERDICT = {
    "reference_suspect": False,
    "reference_bug_hypothesis": "",
    "case_failure_source": "llm_error",
    "case_failure_subtype": "thresholds_rates",
    "rationale": "The model applied last year's threshold.",
    "models": [
        {
            "model": "gpt-6.1-sol",
            "failure_source": "llm_error",
            "failure_subtype": "thresholds_rates",
            "diagnosis": "It used the 2025 threshold.",
        }
    ],
}
FAKE_CLAUDE = """#!{python}
import hashlib, json, os, sys
from pathlib import Path

args = sys.argv[1:]
if args[:1] == ["--version"]:
    print("9.9.9 (Claude Code)")
    sys.exit(0)
if args[:2] == ["auth", "status"]:
    print(os.environ.get("FAKE_AUTH", json.dumps(
        {{"loggedIn": True, "authMethod": "oauth_token"}})))
    sys.exit(0)
prompt = sys.stdin.read()
log = Path(os.environ["FAKE_CLAUDE_LOG"])
number = len(list(log.glob("call-*.json")))
session = f"session-{{number}}"
config = os.environ.get("CLAUDE_CONFIG_DIR")
(log / f"call-{{number}}.json").write_text(json.dumps({{
    "argv": args,
    "cwd": os.getcwd(),
    "cwd_entries": sorted(os.listdir(".")),
    "config_dir": config,
    "api_key": "ANTHROPIC_API_KEY" in os.environ,
    "auth_token": "ANTHROPIC_AUTH_TOKEN" in os.environ,
    "oauth_token": os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"),
    "safe_mode": os.environ.get("CLAUDE_CODE_SAFE_MODE"),
    "no_claude_mds": os.environ.get("CLAUDE_CODE_DISABLE_CLAUDE_MDS"),
    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
}}))
verdict = json.loads(Path(os.environ["FAKE_VERDICT"]).read_text())
events = [{{"type": "user", "message": {{"role": "user", "content": prompt}}}}]
for name in json.loads(os.environ.get("FAKE_TOOLS", "[]")) + ["StructuredOutput"]:
    part = {{"type": "tool_use", "name": name, "input": {{}}}}
    events.append({{"type": "assistant", "message": {{"content": [part]}}}})
if os.environ.get("FAKE_NO_TRANSCRIPT") != "1":
    transcript = Path(config) / "projects" / "-tmp-pb-judge" / f"{{session}}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text("".join(json.dumps(e) + "\\n" for e in events))
print(json.dumps({{
    "structured_output": verdict,
    "modelUsage": {{"claude-opus-5-5": {{}}}},
    "session_id": session,
    "total_cost_usd": 0.5,
    "duration_ms": 1000,
}}))
"""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def lane(tmp_path):
    """An audit with two unjudged cases, a fake CLI and a lane config dir."""
    audit = tmp_path / "audit"
    for name in CASES:
        (audit / "cases" / name).mkdir(parents=True)
        (audit / "cases" / name / "prompt.md").write_text(f"Classify {name}.\n")
    (audit / "schema.json").write_text(json.dumps(AUDIT_OUTPUT_SCHEMA))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    claude = bin_dir / "claude"
    claude.write_text(FAKE_CLAUDE.format(python=sys.executable))
    claude.chmod(0o755)
    verdict = tmp_path / "verdict.json"
    verdict.write_text(json.dumps(VERDICT))
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    config = tmp_path / "lane-config"
    config.mkdir()
    calls = tmp_path / "calls"
    calls.mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(home),
        "TMPDIR": str(scratch),
        "AUDIT_PYTHON": sys.executable,
        "AUDIT_PARALLEL": "1",
        "AUDIT_MODEL": "claude-opus-5-5",
        "AUDIT_ACCOUNT": "claude:lane@example.org",
        "CLAUDE_CONFIG_DIR": str(config),
        "CLAUDE_CODE_OAUTH_TOKEN": "lane-token",
        "ANTHROPIC_API_KEY": "must-not-reach-a-judge",
        "ANTHROPIC_AUTH_TOKEN": "must-not-reach-a-judge",
        "FAKE_CLAUDE_LOG": str(calls),
        "FAKE_VERDICT": str(verdict),
    }

    def run(**changes):
        environment = {**env, **changes}
        environment = {k: v for k, v in environment.items() if v is not None}
        result = subprocess.run(
            ["bash", str(RUNNER), str(audit)],
            capture_output=True,
            text=True,
            env=environment,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
        )
        logged = [
            json.loads(path.read_text()) for path in sorted(calls.glob("call-*.json"))
        ]
        return result, logged

    return audit, config, scratch, run


def _flag(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


def test_each_judge_runs_isolated_on_the_lanes_login(lane):
    audit, config, scratch, run = lane
    result, calls = run()
    assert result.returncode == 0, result.stderr + result.stdout
    assert len(calls) == 2
    schema = (audit / "schema.json").read_text()
    for call in calls:
        argv = call["argv"]
        assert argv[0] == "-p"
        assert _flag(argv, "--model") == "claude-opus-5-5"
        assert _flag(argv, "--output-format") == "json"
        assert _flag(argv, "--json-schema") == schema
        # Every built-in tool removed, and the dangerous ones denied by name.
        assert _flag(argv, "--tools") == ""
        denied = set(_flag(argv, "--disallowedTools").split(","))
        tools = {"Read", "Grep", "Glob", "Bash", "WebFetch", "WebSearch", "Edit"}
        assert tools | {"Write", "NotebookEdit", "Agent"} <= denied
        assert "--strict-mcp-config" in argv and "--disable-slash-commands" in argv
        assert call["safe_mode"] == "1" and call["no_claude_mds"] == "1"
        # A fresh empty directory, outside the repository and the audit.
        cwd = Path(call["cwd"]).resolve()
        assert call["cwd_entries"] == []
        assert cwd.parent == scratch.resolve()
        for tree in (ROOT, audit):
            assert tree.resolve() not in (cwd, *cwd.parents)
        assert not cwd.exists()
        # The lane's credentials only; no API key reaches a judge.
        assert Path(call["config_dir"]) == config.resolve()
        assert call["oauth_token"] == "lane-token"
        assert not call["api_key"] and not call["auth_token"]
    assert calls[0]["cwd"] != calls[1]["cwd"]
    prompts = {
        sha((audit / "cases" / name / "prompt.md").read_bytes()) for name in CASES
    }
    assert {call["prompt_sha256"] for call in calls} == prompts


def test_the_sidecar_binds_the_prompt_and_records_the_login(lane):
    audit, _, _, run = lane
    result, _ = run()
    assert result.returncode == 0, result.stderr + result.stdout
    for name in CASES:
        case = audit / "cases" / name
        meta = json.loads((case / "verdict.meta.json").read_text())
        assert meta["prompt_sha256"] == sha((case / "prompt.md").read_bytes())
        assert meta["verdict_sha256"] == sha((case / "verdict.json").read_bytes())
        assert meta["judge_model_reported"] == ["claude-opus-5-5"]
        assert meta["judge_auth"] == {
            "method": "oauth_token",
            "account": None,
            "org": None,
        }
        assert meta["judge_account_declared"] == "claude:lane@example.org"
        assert meta["judge_isolation"]["transcript_tool_calls"] == 0
        transcript = (case / "claude.transcript.jsonl").read_text()
        assert f"Classify {name}." in transcript


def test_a_reported_email_is_recorded(lane):
    audit, _, _, run = lane
    status = {"loggedIn": True, "authMethod": "claude.ai", "email": "lane@x.org"}
    result, _ = run(FAKE_AUTH=json.dumps(status))
    assert result.returncode == 0, result.stderr
    meta = json.loads((audit / "cases" / CASES[0] / "verdict.meta.json").read_text())
    assert meta["judge_auth"]["account"] == "lane@x.org"


@pytest.mark.parametrize(
    "setting, message",
    [
        ("unset", "CLAUDE_CONFIG_DIR is not set"),
        ("desktop", "desktop login"),
        ("missing", "is not a directory"),
        ("logged_out", "no login"),
    ],
)
def test_the_runner_refuses_anything_but_the_lanes_own_login(lane, setting, message):
    audit, _, _, run = lane
    changes = {}
    if setting == "unset":
        changes["CLAUDE_CONFIG_DIR"] = None
    elif setting == "desktop":
        changes["CLAUDE_CONFIG_DIR"] = str(audit.parent / "home/.claude")
    elif setting == "missing":
        changes["CLAUDE_CONFIG_DIR"] = str(audit.parent / "no-such-dir")
    else:
        changes["FAKE_AUTH"] = json.dumps({"loggedIn": False, "authMethod": "none"})
    result, calls = run(**changes)
    assert result.returncode == 1
    assert message in result.stderr
    assert calls == []
    assert not list(audit.rglob("verdict.json"))


@pytest.mark.parametrize("tool", ["Read", "Grep", "Bash", "WebFetch"])
def test_a_verdict_from_a_judge_that_called_a_tool_is_rejected(lane, tool):
    audit, _, _, run = lane
    result, calls = run(FAKE_TOOLS=json.dumps([tool]))
    assert len(calls) == 2
    assert "[FAIL]" in result.stdout and "[ok]" not in result.stdout
    assert not list(audit.rglob("verdict.json"))
    assert not list(audit.rglob("verdict.meta.json"))
    log = (audit / "cases" / CASES[0] / "claude.log").read_text()
    assert f"the judge called tools: ['{tool}']" in log


def test_a_verdict_without_its_transcript_is_rejected(lane):
    audit, _, _, run = lane
    result, _ = run(FAKE_NO_TRANSCRIPT="1")
    assert "[ok]" not in result.stdout
    assert not list(audit.rglob("verdict.json"))


def test_a_scratch_directory_inside_a_git_repository_is_refused(lane, tmp_path):
    audit, _, _, run = lane
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    result, calls = run(TMPDIR=str(repo))
    assert calls == []
    assert "inside a git repository" in result.stdout
    assert not list(audit.rglob("verdict.json"))


def test_audit_only_limits_the_run_to_the_named_cases(lane):
    audit, _, _, run = lane
    result, calls = run(AUDIT_ONLY=CASES[1])
    assert result.returncode == 0, result.stderr
    assert len(calls) == 1
    assert not (audit / "cases" / CASES[0] / "verdict.json").exists()
    assert (audit / "cases" / CASES[1] / "verdict.json").exists()


def test_a_valid_verdict_is_never_judged_again(lane):
    audit, _, _, run = lane
    run()
    before = {p: p.read_bytes() for p in audit.rglob("verdict*.json")}
    result, calls = run()
    assert result.returncode == 0
    assert len(calls) == 2  # the first run's calls only
    assert {p: p.read_bytes() for p in audit.rglob("verdict*.json")} == before
