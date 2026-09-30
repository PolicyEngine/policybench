#!/usr/bin/env bash
# Bulk failure-audit classifier, run through the Claude Code CLI so the work
# bills to a Claude subscription lane rather than a metered API key. Mirrors
# scripts/run_audit_codex.sh: same audit directory layout, same schema, same
# resumable verdict.json contract, so the two runners are interchangeable.
#
#   policybench audit-prepare --country-dir <dir> --audit-dir <audit>
#   scripts/run_audit_claude.sh <audit>          # this script
#   policybench audit-collect  --country-dir <dir> --audit-dir <audit>
#
# Each judge is independent of everything but its prompt:
#   - it runs from a fresh empty directory outside any git repository, with
#     every built-in tool removed (--tools "") and the file, search, web and
#     shell tools also denied by name, no MCP servers, no skills, no CLAUDE.md
#     files and no user settings (safe mode);
#   - its session transcript is copied beside the verdict as
#     claude.transcript.jsonl, and a verdict whose transcript shows any tool
#     call other than the structured-output answer is rejected.
#
# Credentials: the lane's own, never the desktop login. CLAUDE_CONFIG_DIR must
# name the lane's config directory, and it may not be the desktop login's
# ($HOME/.claude). A home lane sets it to its home. For a keychain-token lane,
# point it at an empty directory kept for the lane and pass the lane's token as
# CLAUDE_CODE_OAUTH_TOKEN; with an empty config directory a missing token logs
# nothing in, so nothing can fall back to the desktop login. The runner refuses
# to start unless `claude auth status` reports a login there, and unsets
# ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN so no call bills an API key.
# AUDIT_ACCOUNT may name the lane's account (the CLI reports no email for a
# token login); it is recorded as declared.
#
# Concurrency and model are tunable via env (AUDIT_PARALLEL, AUDIT_MODEL;
# default model opus). AUDIT_ONLY, a space-separated list of case directory
# names, limits the run to those cases. Portable to bash 3.2.
#
# Judge provenance: beside each verdict.json the runner writes
# verdict.meta.json with the judge model requested, the model the CLI reports,
# the CLI version, the session id, the UTC timestamp, the sha256 of the verdict
# and of the prompt the judge read, the login the CLI reports, the declared
# account and the isolation the judge ran under.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AUDIT_DIR="${1:?usage: run_audit_claude.sh <audit_dir>}"
SCHEMA="$AUDIT_DIR/schema.json"
PARALLEL="${AUDIT_PARALLEL:-4}"
MODEL="${AUDIT_MODEL:-opus}"
ONLY="${AUDIT_ONLY:-}"
# The tools each judge is denied by name, on top of --tools "" removing every
# built-in tool: file reading and editing, search, web and shell.
DISALLOWED="Bash,BashOutput,KillShell,Read,Write,Edit,MultiEdit,NotebookEdit,Glob,Grep,LS,WebFetch,WebSearch,Agent,Task"
# Verdict validation needs jsonschema: prefer the project virtual environment's
# interpreter (uv sync installs it), then an explicit AUDIT_PYTHON, then python3.
if [ -n "${AUDIT_PYTHON:-}" ]; then
  PYTHON="$AUDIT_PYTHON"
elif [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python3"
fi
CLAUDE_BIN="${AUDIT_CLAUDE_BIN:-claude}"
{ command -v "$PYTHON" >/dev/null 2>&1 || [ -x "$PYTHON" ]; } || {
  echo "no python interpreter for verdict validation; set AUDIT_PYTHON" >&2
  exit 1
}
"$PYTHON" -c "import jsonschema" >/dev/null 2>&1 || {
  echo "$PYTHON lacks jsonschema, which verdict validation requires; run inside" >&2
  echo "the project environment (uv sync) or set AUDIT_PYTHON to an interpreter" >&2
  echo "that has it. Refusing to start: verdicts could not be validated." >&2
  exit 1
}
command -v "$CLAUDE_BIN" >/dev/null 2>&1 || {
  echo "claude CLI not found; set AUDIT_CLAUDE_BIN" >&2
  exit 1
}

[ -f "$SCHEMA" ] || { echo "missing $SCHEMA — run audit-prepare first" >&2; exit 1; }
# Absolute paths: each judge runs from its own empty directory.
AUDIT_DIR="$(cd "$AUDIT_DIR" && pwd)"
SCHEMA="$AUDIT_DIR/schema.json"
CASES_DIR="$AUDIT_DIR/cases"
SCHEMA_JSON=$(cat "$SCHEMA")

# The lane's own credentials, never the desktop login's.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN
[ -n "${CLAUDE_CONFIG_DIR:-}" ] || {
  echo "CLAUDE_CONFIG_DIR is not set: the judges would bill the desktop login." >&2
  echo "Set it to this lane's config directory (see the header). Refusing to start." >&2
  exit 1
}
[ -d "$CLAUDE_CONFIG_DIR" ] || {
  echo "CLAUDE_CONFIG_DIR ($CLAUDE_CONFIG_DIR) is not a directory; refusing to start" >&2
  exit 1
}
CONFIG_DIR="$(cd "$CLAUDE_CONFIG_DIR" && pwd -P)"
DESKTOP_DIR="$HOME/.claude"
[ -d "$DESKTOP_DIR" ] && DESKTOP_DIR="$(cd "$DESKTOP_DIR" && pwd -P)"
[ "$CONFIG_DIR" != "$DESKTOP_DIR" ] || {
  echo "CLAUDE_CONFIG_DIR is the desktop login's ($DESKTOP_DIR); refusing to start" >&2
  exit 1
}
export CLAUDE_CONFIG_DIR="$CONFIG_DIR"
AUTH_JSON=$("$CLAUDE_BIN" auth status </dev/null 2>/dev/null)
AUTH=$("$PYTHON" -c '
import json, sys
try:
    status = json.loads(sys.argv[1])
except ValueError:
    sys.exit(1)
if status.get("loggedIn") is not True:
    sys.exit(1)
print(json.dumps({
    "method": status.get("authMethod"),
    "account": status.get("email"),
    "org": status.get("orgId"),
}, sort_keys=True))
' "$AUTH_JSON") || {
  echo "claude auth status reports no login in $CONFIG_DIR; refusing to start" >&2
  exit 1
}
CLI_VERSION=$("$CLAUDE_BIN" --version </dev/null 2>/dev/null | head -n 1)

# A verdict is "done" only if it is parseable JSON carrying the required keys.
verdict_ok() {
  # A verdict counts only if it satisfies the audit schema in full (every
  # required key, enum values, no extra properties); a partial object from a
  # fallback parse must not be published or mark the case complete.
  [ -s "$1" ] || return 1
  "$PYTHON" "$SCRIPT_DIR/validate_verdict.py" "$SCHEMA" "$1" >/dev/null 2>&1
}

# Pull the structured verdict out of the CLI's JSON envelope. Claude Code
# returns `structured_output` when --json-schema is set; fall back to parsing
# the `result` text as JSON. Copy the session transcript beside the verdict
# and reject a verdict whose judge called any tool but the structured answer.
# Also emit the provenance sidecar.
extract_verdict() {
  case_dir="$1"; out_tmp="$2"; meta_tmp="$3"
  "$PYTHON" - "$case_dir" "$out_tmp" "$meta_tmp" "$MODEL" "$CLI_VERSION" \
    "$CONFIG_DIR" "$AUTH" "${AUDIT_ACCOUNT:-}" "$DISALLOWED" <<'PY'
import datetime, glob, hashlib, json, shutil, sys
from pathlib import Path

(case_dir, out_path, meta_path, requested_model, cli_version, config_dir, auth,
 declared, disallowed) = sys.argv[1:10]
case = Path(case_dir)
try:
    envelope = json.load(open(case / "claude.json"))
except Exception:
    sys.exit(1)
verdict = envelope.get("structured_output")
if verdict is None:
    text = envelope.get("result")
    if not isinstance(text, str):
        sys.exit(1)
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        verdict = json.loads(text)
    except Exception:
        sys.exit(1)
if not isinstance(verdict, dict):
    sys.exit(1)
session = envelope.get("session_id")
found = glob.glob(f"{glob.escape(config_dir)}/projects/*/{session}.jsonl")
if not session or len(found) != 1:
    print(f"no single transcript for session {session} in {config_dir}", file=sys.stderr)
    sys.exit(3)
shutil.copyfile(found[0], case / "claude.transcript.jsonl")
calls = []
for line in open(found[0]):
    try:
        event = json.loads(line)
    except ValueError:
        continue
    content = (event.get("message") or {}).get("content")
    if event.get("type") == "assistant" and isinstance(content, list):
        calls += [
            part.get("name")
            for part in content
            if part.get("type") == "tool_use" and part.get("name") != "StructuredOutput"
        ]
if calls:
    print(f"the judge called tools: {calls}", file=sys.stderr)
    sys.exit(2)
verdict_bytes = json.dumps(verdict, indent=2, sort_keys=True).encode("utf-8")
open(out_path, "wb").write(verdict_bytes)
meta = {
    "judge_runner": "scripts/run_audit_claude.sh",
    # Binds the sidecar to this verdict: a sidecar whose hash does not match
    # the case's verdict.json is stale and carries no provenance.
    "verdict_sha256": hashlib.sha256(verdict_bytes).hexdigest(),
    # The exact bytes the judge read on stdin.
    "prompt_sha256": hashlib.sha256((case / "prompt.md").read_bytes()).hexdigest(),
    "judge_model_requested": requested_model,
    "judge_model_reported": sorted((envelope.get("modelUsage") or {}).keys()),
    "judge_cli_version": cli_version,
    "judge_auth": json.loads(auth),
    "judge_account_declared": declared or None,
    "judge_isolation": {
        "cwd": "a fresh empty directory outside any git repository",
        "tools": "none (--tools '')",
        "disallowed_tools": disallowed.split(","),
        "transcript_tool_calls": 0,
    },
    "session_id": session,
    "judged_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "cost_usd": envelope.get("total_cost_usd"),
    "duration_ms": envelope.get("duration_ms"),
}
json.dump(meta, open(meta_path, "w"), indent=2, sort_keys=True)
PY
}

classify_one() {
  case_dir="$1"
  prompt="$case_dir/prompt.md"
  out="$case_dir/verdict.json"
  tmp="$case_dir/verdict.json.tmp"
  meta_tmp="$case_dir/verdict.meta.json.tmp"
  envelope="$case_dir/claude.json"
  [ -f "$prompt" ] || return 0
  verdict_ok "$out" && return 0
  # No valid verdict: any sidecar left behind describes a verdict that no
  # longer exists (re-prepared case) and must not outlive it.
  rm -f "$tmp" "$meta_tmp" "$envelope" "$case_dir/verdict.meta.json" \
    "$case_dir/claude.transcript.jsonl"
  work=$(mktemp -d "${TMPDIR:-/tmp}/pb-judge.XXXXXX") || {
    echo "[FAIL] $(basename "$case_dir") (no scratch directory)"
    return 0
  }
  if git -C "$work" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    rmdir "$work"
    echo "[FAIL] $(basename "$case_dir") (scratch directory is inside a git repository)"
    return 0
  fi
  # Self-contained prompt on stdin, no tools, no project instructions; the
  # schema enforces the JSON shape. Publish atomically only once it validates.
  ( cd "$work" && CLAUDE_CODE_SAFE_MODE=1 CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 \
    "$CLAUDE_BIN" -p \
      --model "$MODEL" \
      --output-format json \
      --json-schema "$SCHEMA_JSON" \
      --tools "" \
      --disallowedTools "$DISALLOWED" \
      --strict-mcp-config \
      --disable-slash-commands \
      < "$prompt" > "$envelope" 2> "$case_dir/claude.log" )
  rmdir "$work" 2>/dev/null || echo "[warn] $(basename "$case_dir"): the judge left files in $work"
  if extract_verdict "$case_dir" "$tmp" "$meta_tmp" 2>> "$case_dir/claude.log" \
    && verdict_ok "$tmp"; then
    mv -f "$tmp" "$out"
    mv -f "$meta_tmp" "$case_dir/verdict.meta.json"
    echo "[ok] $(basename "$case_dir")"
  else
    rm -f "$tmp" "$meta_tmp"
    echo "[FAIL] $(basename "$case_dir") (see claude.log / claude.json)"
  fi
}

selected() {
  [ -z "$ONLY" ] && return 0
  for name in $ONLY; do
    [ "$name" = "$1" ] && return 0
  done
  return 1
}

total=$(ls -d "$CASES_DIR"/*/ 2>/dev/null | wc -l | tr -d ' ')
echo "audit: $total cases | parallel=$PARALLEL model=$MODEL runner=claude ($CLI_VERSION)"
echo "login: $AUTH in $CONFIG_DIR${AUDIT_ACCOUNT:+ (declared: $AUDIT_ACCOUNT)}"

i=0
pids=""
for case_dir in "$CASES_DIR"/*/; do
  case_dir="${case_dir%/}"
  selected "$(basename "$case_dir")" || continue
  classify_one "$case_dir" &
  pids="$pids $!"
  i=$((i + 1))
  if [ $((i % PARALLEL)) -eq 0 ]; then
    wait $pids 2>/dev/null
    pids=""
  fi
done
[ -n "$pids" ] && wait $pids 2>/dev/null

done_count=0
for case_dir in "$CASES_DIR"/*/; do
  verdict_ok "${case_dir%/}/verdict.json" && done_count=$((done_count + 1))
done
echo "audit complete: $done_count/$total verdicts present"
