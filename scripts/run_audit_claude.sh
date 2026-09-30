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
#     shell tools also denied by name, no MCP servers and no skills, in safe
#     mode (no CLAUDE.md files, plugins, user hooks, output styles or
#     auto-memory; admin-managed settings still apply), without the config
#     directory's user settings (--setting-sources project,local: the empty
#     directory has neither), and at one explicit effort level;
#   - its session transcript is copied beside the verdict as
#     claude.transcript.jsonl. A verdict is rejected if the transcript shows
#     any tool call but the structured answer, a context attachment of a kind
#     not listed below, a session context that is not empty (an account
#     e-mail or git status), a working directory inside a git repository, an
#     assistant turn at any effort but the requested one, or an advisor model.
#
# Credentials: the lane's own subscription login, never the desktop login and
# never an API key. CLAUDE_CONFIG_DIR must name the lane's config directory,
# which may not be the desktop login's (~/.claude, compared by file identity).
# A home lane sets it to its home. A keychain-token lane points it at an empty
# directory kept for the lane and passes the lane's token as
# CLAUDE_CODE_OAUTH_TOKEN; with an empty config directory a missing token logs
# nothing in, so nothing can fall back to the desktop login. Every claude call
# runs with an allowlisted environment (PATH, HOME, user, locale, temp dir,
# the config dir, the token and the effort level), so no API key, provider
# switch, base URL or keychain override reaches it. Before judging, the runner
# requires `claude auth status`, run the same way, to report a first-party
# login by the lane's token (when one is set) or by a claude.ai home login
# that is not the desktop's account. A token login reports no account, so
# AUDIT_ACCOUNT must then name it; it is recorded as declared.
#
# The desktop login, by explicit opt-in only (Max, 2026-09-30): with
# JUDGE_ALLOW_DESKTOP_LOGIN=1 the judges run on the desktop login instead.
# The CLI finds that login only under its default config directory, so the
# judges then run with CLAUDE_CONFIG_DIR unset (it may name the desktop's
# ~/.claude, by file identity, and nothing else). No lane token and no
# AUDIT_ACCOUNT may be set, `claude auth status` must report the desktop
# account's own claude.ai login in that directory, and every sidecar records
# the opt-in as the declared account. Everything else stays as above: the
# empty directory, no tools, the allowlisted environment and no API key.
# JUDGE_ALLOW_DESKTOP_LOGIN takes 1 or nothing; any other value is refused.
#
# A judge the API refuses is logged with the CLI's error. When the refusal
# says the login cannot judge now (HTTP 401, 403 or 429: a revoked login, an
# organization that bars Claude Code, a usage limit), the runner starts no
# further judge, lets the running ones finish and exits 1; the run resumes
# where it stopped once the login can judge again.
#
# Concurrency, model and effort are tunable via env (AUDIT_PARALLEL, a
# positive integer; AUDIT_MODEL, default opus; AUDIT_EFFORT, default xhigh,
# the effort every turn of the GPT-6.1 Sol stage's first 17 hardened re-judges
# recorded, although their sidecars left judge_effort null).
# The caller's CLAUDE_CODE_EFFORT_LEVEL never reaches a judge: each runs at
# AUDIT_EFFORT, by flag and by environment. AUDIT_ONLY, a space-separated list
# of case directory names, limits the run to those cases. Portable to bash 3.2.
#
# Judge provenance: beside each verdict.json the runner writes
# verdict.meta.json with the judge model requested, the model the CLI reports,
# the CLI version, the effort level, the session id, the UTC timestamp, the
# sha256 of the verdict and of the prompt the judge read, the login the CLI
# reports, the declared account and the isolation the judge ran under.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AUDIT_DIR="${1:?usage: run_audit_claude.sh <audit_dir>}"
SCHEMA="$AUDIT_DIR/schema.json"
PARALLEL="${AUDIT_PARALLEL:-4}"
MODEL="${AUDIT_MODEL:-opus}"
EFFORT="${AUDIT_EFFORT:-xhigh}"
ONLY="${AUDIT_ONLY:-}"
# The tools each judge is denied by name, on top of --tools "" removing every
# built-in tool: file reading and editing, search, web and shell.
DISALLOWED="Bash,BashOutput,KillShell,Read,Write,Edit,MultiEdit,NotebookEdit,Glob,Grep,LS,WebFetch,WebSearch,Agent,Task"
# The context attachments a tool-less judge's transcript may carry.
# (No ultra_effort_enter: a judge runs at its one explicit effort level.)
ATTACHMENTS="environment,model,date,session_context,total_tokens_reminder,prompt_snapshot,structured_output,silent_turn_reminder"
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
# Absolute: the judges run from their own directories and a bare environment.
CLAUDE_BIN="$(command -v "$CLAUDE_BIN")"
case "$CLAUDE_BIN" in /*) ;; *) CLAUDE_BIN="$(pwd)/$CLAUDE_BIN" ;; esac
case "$PARALLEL" in
  '' | *[!0-9]* | 0)
    echo "AUDIT_PARALLEL must be a positive integer, not '$PARALLEL'; refusing to start" >&2
    exit 1
    ;;
esac
case "$EFFORT" in
  low | medium | high | xhigh | max) ;;
  *)
    echo "AUDIT_EFFORT must be low, medium, high, xhigh or max, not '$EFFORT'; refusing to start" >&2
    exit 1
    ;;
esac

[ -f "$SCHEMA" ] || { echo "missing $SCHEMA — run audit-prepare first" >&2; exit 1; }
# Absolute paths: each judge runs from its own empty directory.
AUDIT_DIR="$(cd "$AUDIT_DIR" && pwd)"
SCHEMA="$AUDIT_DIR/schema.json"
CASES_DIR="$AUDIT_DIR/cases"
SCHEMA_JSON=$(cat "$SCHEMA")

# The desktop login only by Max's explicit opt-in (see the header).
DESKTOP_OPT_IN=0
DESKTOP_DECLARED="desktop login (JUDGE_ALLOW_DESKTOP_LOGIN, Max 2026-09-30)"
case "${JUDGE_ALLOW_DESKTOP_LOGIN:-}" in
  '') ;;
  1) DESKTOP_OPT_IN=1 ;;
  *)
    echo "JUDGE_ALLOW_DESKTOP_LOGIN must be 1 or unset, not '$JUDGE_ALLOW_DESKTOP_LOGIN'; refusing to start" >&2
    exit 1
    ;;
esac
# Prints "desktop" when a directory is the desktop login's, under $HOME or
# under the account's own home, compared by file identity (symlinks, case
# variants and HOME overrides), and "other" when it is not. Anything else
# (a failed check) is neither, so both callers refuse on it.
desktop_dir_state() {
  "$PYTHON" - "$1" "$HOME" <<'PY'
import os, pwd, sys

config, home = sys.argv[1:3]
for base in {home, pwd.getpwuid(os.getuid()).pw_dir}:
    desktop = os.path.join(base, ".claude")
    if os.path.isdir(desktop) and os.path.samefile(config, desktop):
        print("desktop")
        sys.exit(0)
print("other")
PY
}

if [ "$DESKTOP_OPT_IN" = 1 ]; then
  [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] || {
    echo "JUDGE_ALLOW_DESKTOP_LOGIN=1 takes no lane token: unset CLAUDE_CODE_OAUTH_TOKEN; refusing to start" >&2
    exit 1
  }
  [ -z "${AUDIT_ACCOUNT:-}" ] || {
    echo "JUDGE_ALLOW_DESKTOP_LOGIN=1 declares the desktop login itself: unset AUDIT_ACCOUNT; refusing to start" >&2
    exit 1
  }
  [ -d "$HOME/.claude" ] || {
    echo "JUDGE_ALLOW_DESKTOP_LOGIN=1 but there is no desktop login directory $HOME/.claude; refusing to start" >&2
    exit 1
  }
  if [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then
    { [ -d "$CLAUDE_CONFIG_DIR" ] \
      && [ "$(desktop_dir_state "$CLAUDE_CONFIG_DIR")" = desktop ]; } || {
      echo "JUDGE_ALLOW_DESKTOP_LOGIN=1 but CLAUDE_CONFIG_DIR ($CLAUDE_CONFIG_DIR) is not the desktop login's ~/.claude; refusing to start" >&2
      exit 1
    }
  fi
  # The CLI's default config directory: the judges run with it unset.
  CONFIG_DIR="$(cd "$HOME/.claude" && pwd -P)"
else
  # The lane's own credentials, never the desktop login's.
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
  [ "$(desktop_dir_state "$CONFIG_DIR")" = other ] || {
    echo "CLAUDE_CONFIG_DIR is the desktop login's ~/.claude; refusing to start" >&2
    exit 1
  }
fi

# Every claude call gets this environment and nothing else.
allowlist() {
  for var in "$@"; do
    eval "isset=\${$var+x}"
    if [ -n "$isset" ]; then
      eval "value=\${$var}"
      printf '%s=%s\n' "$var" "$value"
    fi
  done
}
CHILD_ENV=()
while IFS= read -r line; do [ -n "$line" ] && CHILD_ENV+=("$line"); done <<EOF
$(allowlist PATH HOME USER LOGNAME TMPDIR LANG LC_ALL LC_CTYPE CLAUDE_CODE_OAUTH_TOKEN)
EOF
CHILD_ENV+=("CLAUDE_CODE_EFFORT_LEVEL=$EFFORT")
# The desktop login is found only under the CLI's default config directory,
# so under the opt-in the judges run with CLAUDE_CONFIG_DIR unset.
[ "$DESKTOP_OPT_IN" = 1 ] || CHILD_ENV+=("CLAUDE_CONFIG_DIR=$CONFIG_DIR")
CHILD_ENV+=("CLAUDE_CODE_SAFE_MODE=1" "CLAUDE_CODE_DISABLE_CLAUDE_MDS=1")
DESKTOP_ENV=()
while IFS= read -r line; do [ -n "$line" ] && DESKTOP_ENV+=("$line"); done <<EOF
$(allowlist PATH HOME USER LOGNAME TMPDIR LANG LC_ALL LC_CTYPE)
EOF
claude_child() { env -i "${CHILD_ENV[@]}" "$CLAUDE_BIN" "$@"; }

# The login, checked the way the judges will run: from an empty directory.
probe=$(mktemp -d "${TMPDIR:-/tmp}/pb-judge-auth.XXXXXX") || exit 1
AUTH_JSON=$(cd "$probe" && claude_child auth status </dev/null 2>/dev/null)
DESKTOP_JSON=$(cd "$probe" && env -i "${DESKTOP_ENV[@]}" "$CLAUDE_BIN" auth status </dev/null 2>/dev/null)
rmdir "$probe" 2>/dev/null
TOKEN_SET=0
[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] && TOKEN_SET=1
# Prints the login as the sidecar records it, or says why it is not the lane's
# (or, under the opt-in, not the desktop login in its own directory).
check_login() {
  "$PYTHON" - "$@" <<'PY'
import json, os, sys

def parse(text):
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}

status, desktop = parse(sys.argv[1]), parse(sys.argv[2])
token, declared, config = sys.argv[3] == "1", sys.argv[4], sys.argv[5]
opt_in = sys.argv[6] == "1"
method, email = status.get("authMethod"), status.get("email")
reported = status.get("configDirectory")
if status.get("loggedIn") is not True:
    problem = f"claude auth status reports no login in {config}"
elif status.get("apiProvider") != "firstParty":
    problem = f"the login is through {status.get('apiProvider')!r}, not a first-party subscription"
elif method not in ("oauth_token", "claude.ai"):
    problem = f"the login method {method!r} is not a subscription login"
elif opt_in and method != "claude.ai":
    problem = f"JUDGE_ALLOW_DESKTOP_LOGIN=1 but the CLI logs in by {method!r}, not the desktop's claude.ai login"
elif opt_in and not (email and desktop.get("loggedIn") is True and email == desktop.get("email")):
    problem = f"JUDGE_ALLOW_DESKTOP_LOGIN=1 but the login ({email}) is not the desktop login's account"
elif opt_in and not (
    isinstance(reported, str) and os.path.isdir(reported) and os.path.samefile(reported, config)
):
    problem = f"JUDGE_ALLOW_DESKTOP_LOGIN=1 but the CLI reports config directory {reported!r}, not {config}"
elif opt_in:
    print(json.dumps({"method": method, "account": email, "org": status.get("orgId")}, sort_keys=True))
    sys.exit(0)
elif token and method != "oauth_token":
    problem = f"a lane token is set but the CLI logs in by {method!r}"
elif method == "oauth_token" and not declared:
    problem = "a token login reports no account; set AUDIT_ACCOUNT to the lane's"
elif email and desktop.get("loggedIn") is True and email == desktop.get("email"):
    problem = f"the login is the desktop login's account ({email})"
else:
    print(json.dumps({"method": method, "account": email, "org": status.get("orgId")}, sort_keys=True))
    sys.exit(0)
print(problem, file=sys.stderr)
sys.exit(1)
PY
}
AUTH=$(check_login "$AUTH_JSON" "$DESKTOP_JSON" "$TOKEN_SET" "${AUDIT_ACCOUNT:-}" \
  "$CONFIG_DIR" "$DESKTOP_OPT_IN") || {
  if [ "$DESKTOP_OPT_IN" = 1 ]; then
    echo "refusing to start: JUDGE_ALLOW_DESKTOP_LOGIN=1 allows the desktop's own login only" >&2
  else
    echo "refusing to start: the judges must bill the lane's own subscription login" >&2
  fi
  exit 1
}
# The account each sidecar declares: the lane's, or the opt-in itself.
DECLARED="${AUDIT_ACCOUNT:-}"
[ "$DESKTOP_OPT_IN" = 1 ] && DECLARED="$DESKTOP_DECLARED"
CLI_VERSION=$(cd / && claude_child --version </dev/null 2>/dev/null | head -n 1)

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
# and reject a verdict whose transcript shows the judge had anything but its
# prompt. Also emit the provenance sidecar.
extract_verdict() {
  case_dir="$1"; out_tmp="$2"; meta_tmp="$3"
  "$PYTHON" - "$case_dir" "$out_tmp" "$meta_tmp" "$MODEL" "$CLI_VERSION" \
    "$CONFIG_DIR" "$AUTH" "$DECLARED" "$DISALLOWED" "$ATTACHMENTS" \
    "$EFFORT" <<'PY'
import datetime, glob, hashlib, json, shutil, sys
from pathlib import Path

(case_dir, out_path, meta_path, requested_model, cli_version, config_dir, auth,
 declared, disallowed, attachments, effort) = sys.argv[1:12]
case = Path(case_dir)
try:
    envelope = json.load(open(case / "claude.json"))
except Exception:
    sys.exit(1)
if envelope.get("is_error"):
    status = envelope.get("api_error_status")
    what = (
        "the CLI's login cannot judge now"
        if status in (401, 403, 429)
        else "the CLI reported an error"
    )
    print(
        f"{what}: status {status} {envelope.get('api_error_code')}: "
        f"{envelope.get('result')}",
        file=sys.stderr,
    )
    sys.exit(7)
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
allowed = set(attachments.split(","))
calls, unexpected, turns = [], [], []
for number, line in enumerate(open(found[0]), 1):
    try:
        event = json.loads(line)
    except ValueError:
        print(f"transcript line {number} is not JSON", file=sys.stderr)
        sys.exit(4)
    if event.get("type") == "attachment":
        attachment = event.get("attachment") or {}
        kind = attachment.get("type")
        if kind not in allowed:
            unexpected.append(kind)
        if kind == "environment" and (attachment.get("snapshot") or {}).get("isGitRepo"):
            unexpected.append("environment inside a git repository")
        if kind == "session_context" and attachment.get("context") != {}:
            carried = sorted(attachment.get("context") or {}) or [repr(attachment.get("context"))]
            unexpected.append(f"session context carrying {carried}")
    if event.get("type") == "assistant":
        if event.get("effort") != effort:
            turns.append(f"effort {event.get('effort')!r}, not {effort!r}")
        if event.get("advisorModel"):
            turns.append(f"advisor model {event.get('advisorModel')!r}")
    content = (event.get("message") or {}).get("content")
    if isinstance(content, list):
        calls += [
            part.get("name") or part.get("type")
            for part in content
            if isinstance(part, dict)
            and str(part.get("type", "")).endswith("tool_use")
            and not (part.get("type") == "tool_use" and part.get("name") == "StructuredOutput")
        ]
if calls:
    print(f"the judge called tools: {calls}", file=sys.stderr)
    sys.exit(2)
if unexpected:
    print(f"the judge's context carried unexpected attachments: {unexpected}", file=sys.stderr)
    sys.exit(5)
if turns:
    print(f"the judge did not run as requested: {sorted(set(turns))}", file=sys.stderr)
    sys.exit(6)
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
    "judge_effort": effort,
    "judge_auth": json.loads(auth),
    "judge_account_declared": declared or None,
    "judge_isolation": {
        "cwd": "a fresh empty directory outside any git repository",
        "tools": "none (--tools '')",
        "disallowed_tools": disallowed.split(","),
        "environment": "allowlisted",
        "settings": "no user settings (--setting-sources project,local)",
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
  ( cd "$work" && claude_child -p \
      --model "$MODEL" \
      --output-format json \
      --json-schema "$SCHEMA_JSON" \
      --tools "" \
      --disallowedTools "$DISALLOWED" \
      --strict-mcp-config \
      --disable-slash-commands \
      --setting-sources project,local \
      --effort "$EFFORT" \
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
    if grep -q "^the CLI's login cannot judge now" "$case_dir/claude.log" 2>/dev/null; then
      : > "$STOP_FLAG"
    fi
  fi
}

# AUDIT_ONLY names, split on whitespace and never glob-expanded.
set -f
ONLY_NAMES=$(printf '%s\n' $ONLY)
set +f
for name in $ONLY_NAMES; do
  [ -d "$CASES_DIR/$name" ] || echo "[warn] AUDIT_ONLY names no case: $name" >&2
done
selected() {
  [ -z "$ONLY_NAMES" ] && return 0
  printf '%s\n' "$ONLY_NAMES" | grep -Fxq "$1"
}

# The cases whose verdict already satisfies the schema, found in one pass
# rather than one interpreter per case.
valid_cases() {
  "$PYTHON" - "$SCRIPT_DIR" "$SCHEMA" "$CASES_DIR" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from validate_verdict import verdict_errors

schema, cases = Path(sys.argv[2]), Path(sys.argv[3])
for case in sorted(cases.iterdir()):
    verdict = case / "verdict.json"
    if verdict.is_file() and verdict.stat().st_size and not verdict_errors(schema, verdict):
        print(case.name)
PY
}

total=$(ls -d "$CASES_DIR"/*/ 2>/dev/null | wc -l | tr -d ' ')
echo "audit: $total cases | parallel=$PARALLEL model=$MODEL effort=$EFFORT runner=claude ($CLI_VERSION)"
echo "login: $AUTH in $CONFIG_DIR${DECLARED:+ (declared: $DECLARED)}"
VALID=$(valid_cases)
# Set by a judge whose login cannot judge now; no further judge starts.
RUN_STATE=$(mktemp -d "${TMPDIR:-/tmp}/pb-judge-run.XXXXXX") || exit 1
STOP_FLAG="$RUN_STATE/stop"

i=0
pids=""
for case_dir in "$CASES_DIR"/*/; do
  case_dir="${case_dir%/}"
  selected "$(basename "$case_dir")" || continue
  printf '%s\n' "$VALID" | grep -Fxq "$(basename "$case_dir")" && continue
  [ -e "$STOP_FLAG" ] && break
  classify_one "$case_dir" &
  pids="$pids $!"
  i=$((i + 1))
  if [ $((i % PARALLEL)) -eq 0 ]; then
    wait $pids 2>/dev/null
    pids=""
  fi
done
[ -n "$pids" ] && wait $pids 2>/dev/null

stopped=0
[ -e "$STOP_FLAG" ] && stopped=1
rm -f "$STOP_FLAG"
rmdir "$RUN_STATE" 2>/dev/null
done_count=$(valid_cases | wc -l | tr -d ' ')
echo "audit complete: $done_count/$total verdicts present"
if [ "$stopped" = 1 ]; then
  echo "stopped: the login cannot judge now (see the failed case's claude.log); no further judge was started" >&2
  exit 1
fi
