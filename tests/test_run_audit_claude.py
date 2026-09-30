"""scripts/run_audit_claude.sh isolates each judge and bills only the lane.

A fake claude CLI records the command line, working directory and environment
of every call, writes the session transcript where Claude Code keeps it and
answers with a canned verdict. The runner gives every claude call an
allowlisted environment, so the fake reads its settings from a file beside it.
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
LANE = {"loggedIn": True, "authMethod": "oauth_token", "apiProvider": "firstParty"}
DESKTOP = {
    "loggedIn": True,
    "authMethod": "claude.ai",
    "apiProvider": "firstParty",
    "email": "desktop@example.org",
}
# What a judge's environment may hold (macOS adds __CF_* to any process).
ALLOWED_ENV = {
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CODE_EFFORT_LEVEL",
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_CODE_SAFE_MODE",
    "CLAUDE_CODE_DISABLE_CLAUDE_MDS",
}
FAKE_CLAUDE = """#!{python}
import hashlib, json, os, sys
from pathlib import Path

fake = json.loads(Path(__file__).with_name("fake.json").read_text())
log = Path(fake["log"])
args = sys.argv[1:]
config = os.environ.get("CLAUDE_CONFIG_DIR")
if args[:1] == ["--version"]:
    print("9.9.9 (Claude Code)")
    sys.exit(0)
if args[:2] == ["auth", "status"]:
    number = len(list(log.glob("auth-*.json")))
    (log / f"auth-{{number}}.json").write_text(json.dumps(
        {{"env": sorted(os.environ), "config_dir": config}}))
    print(json.dumps(fake["auth"] if config else fake["desktop_auth"]))
    sys.exit(0)
prompt = sys.stdin.read()
number = len(list(log.glob("call-*.json")))
session = f"session-{{number}}"
(log / f"call-{{number}}.json").write_text(json.dumps({{
    "argv": args,
    "cwd": os.getcwd(),
    "cwd_entries": sorted(os.listdir(".")),
    "env": sorted(os.environ),
    "config_dir": config,
    "oauth_token": os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"),
    "effort": os.environ.get("CLAUDE_CODE_EFFORT_LEVEL"),
    "safe_mode": os.environ.get("CLAUDE_CODE_SAFE_MODE"),
    "no_claude_mds": os.environ.get("CLAUDE_CODE_DISABLE_CLAUDE_MDS"),
    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
}}))
verdict = json.loads(Path(fake["verdict"]).read_text())
environment = {{"workingDirectory": os.getcwd(), "isGitRepo": fake["git_repo"]}}
events = [
    {{"type": "user", "message": {{"role": "user", "content": prompt}}}},
    {{"type": "attachment", "attachment": {{"type": "environment",
                                           "snapshot": environment}}}},
]
events += [{{"type": "attachment", "attachment": {{"type": kind}}}}
           for kind in fake["attachments"]]
for name in fake["tools"] + ["StructuredOutput"]:
    part = {{"type": fake["part_type"] if name != "StructuredOutput" else "tool_use",
             "name": name, "input": {{}}}}
    events.append({{"type": "assistant", "message": {{"content": [part]}}}})
lines = "".join(json.dumps(e) + "\\n" for e in events)
if fake["bad_line"]:
    lines += "{{not json\\n"
for copy in range(fake["transcripts"]):
    project = Path(config) / "projects" / f"-tmp-pb-judge-{{copy}}"
    transcript = project / f"{{session}}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(lines)
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
        "CLAUDE_CODE_EFFORT_LEVEL": "xhigh",
        # None of these may reach a claude call.
        "ANTHROPIC_API_KEY": "must-not-reach-a-judge",
        "ANTHROPIC_AUTH_TOKEN": "must-not-reach-a-judge",
        "ANTHROPIC_BASE_URL": "https://example.invalid",
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "CLAUDE_SECURESTORAGE_CONFIG_DIR": "",
    }
    defaults = {
        "log": str(calls),
        "verdict": str(verdict),
        "auth": LANE,
        "desktop_auth": DESKTOP,
        "tools": [],
        "part_type": "tool_use",
        "attachments": [],
        "git_repo": False,
        "bad_line": False,
        "transcripts": 1,
    }

    def run(env_changes=None, **fake):
        (bin_dir / "fake.json").write_text(json.dumps({**defaults, **fake}))
        environment = {**env, **(env_changes or {})}
        environment = {k: v for k, v in environment.items() if v is not None}
        result = subprocess.run(
            ["bash", str(RUNNER), str(audit)],
            capture_output=True,
            text=True,
            env=environment,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
        )
        logged = [json.loads(p.read_text()) for p in sorted(calls.glob("call-*.json"))]
        return result, logged

    run.calls = calls
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
        # The lane's credentials only.
        assert Path(call["config_dir"]) == config.resolve()
        assert call["oauth_token"] == "lane-token"
        assert call["effort"] == "xhigh"
    assert calls[0]["cwd"] != calls[1]["cwd"]
    prompts = {
        sha((audit / "cases" / name / "prompt.md").read_bytes()) for name in CASES
    }
    assert {call["prompt_sha256"] for call in calls} == prompts


def test_only_an_allowlisted_environment_reaches_any_claude_call(lane):
    """No API key, base URL, provider switch or keychain override (an empty
    CLAUDE_SECURESTORAGE_CONFIG_DIR selects the desktop login's keychain entry)
    reaches the login check or a judge."""
    _, _, _, run = lane
    result, calls = run()
    assert result.returncode == 0, result.stderr
    checks = [json.loads(p.read_text()) for p in sorted(run.calls.glob("auth-*.json"))]
    assert calls and checks
    for seen in [*calls, *checks]:
        extra = {k for k in seen["env"] if not k.startswith("__CF")} - ALLOWED_ENV
        assert extra == set(), extra


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
        assert meta["judge_effort"] == "xhigh"
        assert meta["judge_isolation"]["transcript_tool_calls"] == 0
        transcript = (case / "claude.transcript.jsonl").read_text()
        assert f"Classify {name}." in transcript


def test_a_home_lanes_own_account_is_recorded(lane):
    audit, _, _, run = lane
    home_login = {**DESKTOP, "email": "lane@x.org"}
    result, _ = run(
        {"CLAUDE_CODE_OAUTH_TOKEN": None, "AUDIT_ACCOUNT": None}, auth=home_login
    )
    assert result.returncode == 0, result.stderr
    meta = json.loads((audit / "cases" / CASES[0] / "verdict.meta.json").read_text())
    assert meta["judge_auth"]["account"] == "lane@x.org"


@pytest.mark.parametrize(
    "env_changes, fake, message",
    [
        ({"CLAUDE_CONFIG_DIR": None}, {}, "CLAUDE_CONFIG_DIR is not set"),
        ({"CLAUDE_CONFIG_DIR": "DESKTOP"}, {}, "desktop login"),
        ({"CLAUDE_CONFIG_DIR": "DESKTOP_LINK"}, {}, "desktop login"),
        ({"CLAUDE_CONFIG_DIR": "MISSING"}, {}, "is not a directory"),
        ({}, {"auth": {"loggedIn": False}}, "no login"),
        ({}, {"auth": {**LANE, "apiProvider": "bedrock"}}, "not a first-party"),
        ({}, {"auth": {**LANE, "authMethod": "api_key_helper"}}, "not a subscription"),
        ({}, {"auth": {**LANE, "authMethod": "api_key"}}, "not a subscription"),
        ({}, {"auth": DESKTOP}, "a lane token is set but"),
        ({"AUDIT_ACCOUNT": None}, {}, "set AUDIT_ACCOUNT"),
        (
            {"CLAUDE_CODE_OAUTH_TOKEN": None},
            {"auth": DESKTOP},
            "the desktop login's account",
        ),
        ({"AUDIT_PARALLEL": "0"}, {}, "positive integer"),
        ({"AUDIT_PARALLEL": "four"}, {}, "positive integer"),
    ],
)
def test_the_runner_refuses_anything_but_the_lanes_own_login(
    lane, env_changes, fake, message
):
    audit, _, _, run = lane
    home = audit.parent / "home"
    places = {
        "DESKTOP": str(home / ".claude"),
        "DESKTOP_LINK": str(audit.parent / "link-to-desktop"),
        "MISSING": str(audit.parent / "no-such-dir"),
    }
    (audit.parent / "link-to-desktop").symlink_to(home / ".claude")
    changes = {k: places.get(v, v) for k, v in env_changes.items()}
    result, calls = run(changes, **fake)
    assert result.returncode == 1
    assert message in result.stderr
    assert calls == []
    assert not list(audit.rglob("verdict.json"))


@pytest.mark.parametrize("tool", ["Read", "Grep", "Bash", "WebFetch"])
def test_a_verdict_from_a_judge_that_called_a_tool_is_rejected(lane, tool):
    audit, _, _, run = lane
    result, calls = run(tools=[tool])
    assert len(calls) == 2
    assert "[FAIL]" in result.stdout and "[ok]" not in result.stdout
    assert not list(audit.rglob("verdict.json"))
    assert not list(audit.rglob("verdict.meta.json"))
    log = (audit / "cases" / CASES[0] / "claude.log").read_text()
    assert f"the judge called tools: ['{tool}']" in log


@pytest.mark.parametrize(
    "fake, message",
    [
        ({"tools": ["web_search"], "part_type": "server_tool_use"}, "called tools"),
        ({"tools": ["read"], "part_type": "mcp_tool_use"}, "called tools"),
        ({"attachments": ["file"]}, "unexpected attachments: ['file']"),
        ({"attachments": ["nested_memory"]}, "unexpected attachments"),
        ({"git_repo": True}, "inside a git repository"),
        ({"bad_line": True}, "is not JSON"),
        ({"transcripts": 0}, "no single transcript"),
        ({"transcripts": 2}, "no single transcript"),
    ],
)
def test_a_transcript_showing_more_than_the_prompt_is_rejected(lane, fake, message):
    audit, _, _, run = lane
    result, _ = run(**fake)
    assert "[ok]" not in result.stdout
    assert not list(audit.rglob("verdict.json"))
    assert message in (audit / "cases" / CASES[0] / "claude.log").read_text()


def test_a_scratch_directory_inside_a_git_repository_is_refused(lane, tmp_path):
    audit, _, _, run = lane
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    result, calls = run({"TMPDIR": str(repo)})
    assert calls == []
    assert "inside a git repository" in result.stdout
    assert not list(audit.rglob("verdict.json"))


def test_audit_only_limits_the_run_to_the_named_cases(lane):
    audit, _, _, run = lane
    result, calls = run({"AUDIT_ONLY": f"{CASES[1]} us__scenario_*__nope"})
    assert result.returncode == 0, result.stderr
    assert len(calls) == 1
    assert not (audit / "cases" / CASES[0] / "verdict.json").exists()
    assert (audit / "cases" / CASES[1] / "verdict.json").exists()
    assert "AUDIT_ONLY names no case: us__scenario_*__nope" in result.stderr


def test_a_valid_verdict_is_never_judged_again(lane):
    audit, _, _, run = lane
    run()
    before = {p: p.read_bytes() for p in audit.rglob("verdict*.json")}
    result, calls = run()
    assert result.returncode == 0
    assert len(calls) == 2  # the first run's calls only
    assert {p: p.read_bytes() for p in audit.rglob("verdict*.json")} == before


def test_an_invalid_verdict_is_judged_again_and_its_stale_evidence_replaced(lane):
    audit, _, _, run = lane
    case = audit / "cases" / CASES[0]
    (case / "verdict.json").write_text('{"models": []}')
    (case / "verdict.meta.json").write_text('{"stale": true}')
    (case / "claude.transcript.jsonl").write_text("stale transcript\n")
    result, calls = run({"AUDIT_ONLY": CASES[0]})
    assert result.returncode == 0, result.stderr
    assert len(calls) == 1
    meta = json.loads((case / "verdict.meta.json").read_text())
    assert meta["verdict_sha256"] == sha((case / "verdict.json").read_bytes())
    assert "stale transcript" not in (case / "claude.transcript.jsonl").read_text()
