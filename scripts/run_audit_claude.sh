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
#     any tool call but the structured answer, an event of a type or a
#     context attachment of a kind not listed below, a session context that
#     is not empty (an account e-mail or git status), account data anywhere
#     outside the prompt's own user message and the judge's own turns (an
#     e-mail address, or a key naming an e-mail, account, credential,
#     organization or git status), a working directory inside a git
#     repository, an assistant turn at any effort but the requested one, or
#     an advisor model; and unless the judge's one accepted StructuredOutput
#     call (any other is one the schema refused) answered exactly the verdict;
#   - it reads a private copy of prompt.md, hashed before it runs; the sidecar
#     records that hash. A verdict is rejected if prompt.md no longer has it
#     at extraction, or if the transcript's user events are not exactly one
#     text message equal to the judged prompt (plus Claude Code's own
#     StructuredOutput nudge, PROMPT_NUDGE) and the results of the judge's
#     StructuredOutput calls.
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
# A judge the API refuses is logged with the CLI's error. When the login
# cannot judge now, the runner starts no further judge, lets the running ones
# finish and exits 1; the run resumes where it stopped once the login can
# judge. That is so when the API refuses the login (HTTP 401, 403 or 429: a
# revoked login, an organization that bars Claude Code, a usage limit), and
# when a judge's transcript shows the login putting account context in the
# judge's context (a session context, such as the account e-mail Claude Code
# 2.1.284 adds for a claude.ai login, a credential_org record, or account data
# anywhere else in the transcript), which it would do for every judge.
#
# Concurrency, model and effort are tunable via env (AUDIT_PARALLEL, a
# positive integer; AUDIT_MODEL, default opus; AUDIT_EFFORT, default xhigh,
# the effort every turn of the GPT-6.1 Sol stage's first 17 hardened re-judges
# recorded, although their sidecars left judge_effort null).
# The caller's CLAUDE_CODE_EFFORT_LEVEL never reaches a judge: each runs at
# AUDIT_EFFORT, by flag and by environment. AUDIT_ONLY, a space-separated list
# of case directory names, limits the run to those cases. Portable to bash 3.2.
#
# A verdict counts only if it satisfies the audit schema and names exactly the
# models its case lists in audit-prepare's cases.jsonl, each once and no other
# (the finish driver's coverage rule, scripts/validate_verdict.py). A judge
# whose verdict does not is logged "[invalid]"; nothing is published for the
# case, which stays pending for the next run, and the run goes on.
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
# The event types a judge's transcript may carry: those of the GPT-6.1 Sol
# stage's 60 isolated transcripts. JUDGE_EVENT_TYPES in
# scripts/finish_gpt61sol.py, which a test keeps equal to this list.
EVENT_TYPES="queue-operation,user,attachment,atis-latch,last-prompt,assistant,cost-state"
# The one user text message besides the prompt a judge's transcript may carry:
# Claude Code's own nudge, recorded as an isMeta user message, when a judge
# answers in text without calling StructuredOutput (as the GPT-6.1 Sol stage's
# us__scenario_014__state_income_tax_before_refundable_credits transcript
# shows). JUDGE_PROMPT_NUDGE in scripts/finish_gpt61sol.py, which a test keeps
# equal to this text.
PROMPT_NUDGE="[structured-output-enforce] You MUST call the StructuredOutput tool to complete this request. Call this tool now."
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
# The models each case lists, which its verdict must name exactly.
MANIFEST="$AUDIT_DIR/cases.jsonl"
[ -f "$MANIFEST" ] || { echo "missing $MANIFEST — run audit-prepare first" >&2; exit 1; }
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
# A verdict counts for its case only if it also names exactly the models the
# case lists (see the header). Says why not on stderr.
case_ok() {
  [ -s "$1" ] || { echo "no verdict" >&2; return 1; }
  "$PYTHON" "$SCRIPT_DIR/validate_verdict.py" "$SCHEMA" "$1" "$MANIFEST" "$2" >/dev/null
}

# Pull the structured verdict out of the CLI's JSON envelope. Claude Code
# returns `structured_output` when --json-schema is set; fall back to parsing
# the `result` text as JSON. Copy the session transcript beside the verdict
# and reject a verdict whose transcript shows the judge had anything but its
# prompt, the judged copy of prompt.md, hashed before the judge ran. Also
# emit the provenance sidecar.
extract_verdict() {
  case_dir="$1"; out_tmp="$2"; meta_tmp="$3"; judged="$4"; judged_sha="$5"
  "$PYTHON" - "$case_dir" "$out_tmp" "$meta_tmp" "$MODEL" "$CLI_VERSION" \
    "$CONFIG_DIR" "$AUTH" "$DECLARED" "$DISALLOWED" "$ATTACHMENTS" \
    "$EFFORT" "$judged" "$judged_sha" "$PROMPT_NUDGE" "$EVENT_TYPES" <<'PY'
import datetime, glob, hashlib, json, re, shutil, sys
from pathlib import Path

(case_dir, out_path, meta_path, requested_model, cli_version, config_dir, auth,
 declared, disallowed, attachments, effort, judged_path, judged_sha,
 nudge, event_types) = sys.argv[1:16]
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
# The judged copy of prompt.md, hashed before the judge ran.
judged = Path(judged_path).read_bytes()
try:
    judged_text = judged.decode("utf-8")
except UnicodeDecodeError:
    judged_text = None
# Account data: ACCOUNT_KEY and EMAIL_ADDRESS in scripts/finish_gpt61sol.py,
# whose account_data and outside_the_judge these mirror.
account_key = re.compile(r"email|account|credential|organi[sz]ation|gitstatus", re.I)
email_address = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def account_data(value, at):
    """Where value carries an e-mail address or a key naming an account."""
    hits = []
    if isinstance(value, dict):
        for key, item in value.items():
            where = f"{at}.{key}"
            if account_key.search(str(key)):
                hits.append(f"key {where}")
            if email_address.search(str(key)):
                hits.append(f"an e-mail address in key {where}")
            hits += account_data(item, where)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits += account_data(item, f"{at}[{index}]")
    elif isinstance(value, str) and email_address.search(value):
        hits.append(f"an e-mail address at {at}")
    return hits


def outside_the_judge(event):
    """The event without the judged prompt's own text or the judge's words."""
    message = event.get("message")
    if isinstance(message, dict) and (
        event.get("type") == "assistant"
        or (
            event.get("type") == "user"
            and judged_text is not None
            and message.get("content") == judged_text
        )
    ):
        return {**event, "message": {k: v for k, v in message.items() if k != "content"}}
    return event


allowed = set(attachments.split(","))
listed = set(event_types.split(","))
calls, unexpected, turns, account, foreign = [], [], [], [], []
# The user events: text messages (the prompt) and everything else (which may
# only answer the judge's own StructuredOutput calls, by id).
texts, others, answers = [], [], set()
# Every StructuredOutput call, and the calls the schema refused (by id).
structured, refused = [], set()
for number, line in enumerate(open(found[0]), 1):
    try:
        event = json.loads(line)
    except ValueError:
        print(f"transcript line {number} is not JSON", file=sys.stderr)
        sys.exit(4)
    if not isinstance(event, dict):
        print(f"transcript line {number} is not an event", file=sys.stderr)
        sys.exit(4)
    if event.get("type") not in listed:
        foreign.append(f"an event of type {event.get('type')!r}")
    carried = account_data(outside_the_judge(event), f"line {number}")
    foreign += carried
    account += carried
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
            account.append(f"session context carrying {carried}")
        if kind == "credential_org":
            account.append("credential_org")
    if event.get("type") == "assistant":
        if event.get("effort") != effort:
            turns.append(f"effort {event.get('effort')!r}, not {effort!r}")
        if event.get("advisorModel"):
            turns.append(f"advisor model {event.get('advisorModel')!r}")
    content = (event.get("message") or {}).get("content")
    if event.get("type") == "user":
        if not isinstance(content, str):
            others.append(content)
        elif not (event.get("isMeta") is True and content == nudge):
            texts.append(content)
    if isinstance(content, list):
        if event.get("type") == "assistant":
            answers |= {
                part.get("id")
                for part in content
                if isinstance(part, dict)
                and part.get("type") == "tool_use"
                and part.get("name") == "StructuredOutput"
            }
        structured += [
            part
            for part in content
            if isinstance(part, dict)
            and part.get("type") == "tool_use"
            and part.get("name") == "StructuredOutput"
        ]
        refused |= {
            part.get("tool_use_id")
            for part in content
            if isinstance(part, dict)
            and part.get("type") == "tool_result"
            and part.get("is_error")
        }
        calls += [
            part.get("name") or part.get("type")
            for part in content
            if isinstance(part, dict)
            and str(part.get("type", "")).endswith("tool_use")
            and not (part.get("type") == "tool_use" and part.get("name") == "StructuredOutput")
        ]
if account:
    print(
        "the CLI's login cannot judge now: it puts account context in every "
        f"judge's context: {account}",
        file=sys.stderr,
    )
if calls:
    print(f"the judge called tools: {calls}", file=sys.stderr)
    sys.exit(2)
if unexpected:
    print(f"the judge's context carried unexpected attachments: {unexpected}", file=sys.stderr)
    sys.exit(5)
if foreign:
    print(f"the judge's transcript carried what an isolated judge's cannot: {foreign}", file=sys.stderr)
    sys.exit(5)
if turns:
    print(f"the judge did not run as requested: {sorted(set(turns))}", file=sys.stderr)
    sys.exit(6)
# The prompt binding: the judge read the judged copy, hashed before it ran,
# and prompt.md still has that hash.
unbound = []
if hashlib.sha256(judged).hexdigest() != judged_sha:
    unbound.append("the judged copy of prompt.md changed")
try:
    current = hashlib.sha256((case / "prompt.md").read_bytes()).hexdigest()
except OSError:
    current = None
if current != judged_sha:
    unbound.append("prompt.md changed while the judge ran")
if len(texts) != 1:
    unbound.append(f"{len(texts)} user text messages, not the prompt alone")
elif judged_text is None or texts[0] != judged_text:
    unbound.append("its user message is not the judged prompt")
for content in others:
    if not (
        isinstance(content, list)
        and content
        and all(
            isinstance(part, dict)
            and part.get("type") == "tool_result"
            and part.get("tool_use_id") in answers
            for part in content
        )
    ):
        unbound.append("a user event that is not a StructuredOutput call's result")
if unbound:
    print(f"the verdict is not bound to the judged prompt: {unbound}", file=sys.stderr)
    sys.exit(8)
# The answer: the judge's one accepted StructuredOutput call (any other is one
# the schema refused) answered exactly the verdict about to be written.
accepted = [part for part in structured if part.get("id") not in refused]
if len(accepted) != 1:
    print(
        f"the verdict is not the judge's answer: {len(accepted)} accepted "
        "StructuredOutput calls, not 1",
        file=sys.stderr,
    )
    sys.exit(9)
if json.dumps(accepted[0].get("input"), sort_keys=True) != json.dumps(
    verdict, sort_keys=True
):
    print(
        "the verdict is not the judge's answer: its accepted StructuredOutput "
        "call answered otherwise",
        file=sys.stderr,
    )
    sys.exit(9)
verdict_bytes = json.dumps(verdict, indent=2, sort_keys=True).encode("utf-8")
open(out_path, "wb").write(verdict_bytes)
meta = {
    "judge_runner": "scripts/run_audit_claude.sh",
    # Binds the sidecar to this verdict: a sidecar whose hash does not match
    # the case's verdict.json is stale and carries no provenance.
    "verdict_sha256": hashlib.sha256(verdict_bytes).hexdigest(),
    # The exact bytes the judge read on stdin, hashed before it ran.
    "prompt_sha256": judged_sha,
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
  name=$(basename "$case_dir")
  prompt="$case_dir/prompt.md"
  out="$case_dir/verdict.json"
  tmp="$case_dir/verdict.json.tmp"
  meta_tmp="$case_dir/verdict.meta.json.tmp"
  envelope="$case_dir/claude.json"
  [ -f "$prompt" ] || return 0
  case_ok "$out" "$name" 2>/dev/null && return 0
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
  # The judged bytes: a private copy of prompt.md beside the judge's empty
  # directory, hashed before the judge runs and fed to it on stdin, so the
  # sidecar's prompt_sha256 is what the judge read, whatever happens to
  # prompt.md meanwhile.
  judged=$(mktemp "${TMPDIR:-/tmp}/pb-judge-prompt.XXXXXX") || {
    rmdir "$work"
    echo "[FAIL] $name (no scratch file for the prompt)"
    return 0
  }
  if ! cp "$prompt" "$judged" || ! judged_sha=$("$PYTHON" -c \
    'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' \
    "$judged"); then
    rm -f "$judged"
    rmdir "$work"
    echo "[FAIL] $name (could not copy and hash the prompt)"
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
      < "$judged" > "$envelope" 2> "$case_dir/claude.log" )
  rmdir "$work" 2>/dev/null || echo "[warn] $(basename "$case_dir"): the judge left files in $work"
  extract_verdict "$case_dir" "$tmp" "$meta_tmp" "$judged" "$judged_sha" \
    2>> "$case_dir/claude.log"
  extracted=$?
  rm -f "$judged"
  if [ "$extracted" = 0 ] && verdict_ok "$tmp"; then
    if problem=$(case_ok "$tmp" "$name" 2>&1); then
      mv -f "$tmp" "$out"
      mv -f "$meta_tmp" "$case_dir/verdict.meta.json"
      echo "[ok] $name"
    else
      # Answered, but not for this case's models: pending, and the run goes on.
      rm -f "$tmp" "$meta_tmp"
      problem=$(printf '%s' "$problem" | tr '\n' ' ')
      echo "invalid verdict: $problem" >> "$case_dir/claude.log"
      echo "[invalid] $name ($problem)"
    fi
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

# The cases whose verdict already counts (schema and model coverage), found in
# one pass rather than one interpreter per case.
valid_cases() {
  "$PYTHON" - "$SCRIPT_DIR" "$SCHEMA" "$CASES_DIR" "$MANIFEST" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from validate_verdict import case_verdict_errors, manifest_wrong_models

schema, cases = Path(sys.argv[2]), Path(sys.argv[3])
listed = manifest_wrong_models(Path(sys.argv[4]))
for case in sorted(cases.iterdir()):
    verdict = case / "verdict.json"
    if (
        verdict.is_file()
        and verdict.stat().st_size
        and not case_verdict_errors(schema, verdict, listed.get(case.name))
    ):
        print(case.name)
PY
}

total=$(ls -d "$CASES_DIR"/*/ 2>/dev/null | wc -l | tr -d ' ')
echo "audit: $total cases | parallel=$PARALLEL model=$MODEL effort=$EFFORT runner=claude ($CLI_VERSION)"
echo "login: $AUTH in $CONFIG_DIR${DECLARED:+ (declared: $DECLARED)}"
VALID=$(valid_cases) || {
  echo "cannot read the verdicts against $MANIFEST; refusing to start" >&2
  exit 1
}
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
