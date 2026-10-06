#!/usr/bin/env bash
# Reference adversary judge, run through the Claude Code CLI. The adversary
# attacks consensus-flagged references from primary law; see
# policybench/reference_adversary.py for the design and the output contracts.
#
#   policybench consensus-flags --payload <data.json.gz> --output <flags.json>
#   policybench adversary-prepare --payload <data.json.gz> --flags <flags.json> \
#       --adversary-dir <dir> --annotations-dir <frozen annotations>
#   scripts/run_reference_adversary_claude.sh <dir>        # this script
#   policybench adversary-collect --adversary-dir claude=<dir> --output-dir <out>
#
# Run it inside a Subfleet lane, so that every judge call bills to the lane's
# own subscription login and never to an API key or the desktop login (the
# credential rules below are scripts/run_audit_claude.sh's). Give each judge
# its own adversary directory: stage 1 and the verdict of a case must come from
# the same runner.
#
# Each case takes two calls, in order:
#   1. Stage 1, unless cases/<id>/stage1.json is already schema-valid. The
#      judge reads cases/<id>/stage1_prompt.md: the household prompt, the
#      output definition, the reference value and the consensus answers, but
#      not the engine derivation. A stage 1 judged afresh leaves no stage-2
#      prompt or verdict behind.
#   2. `python -m policybench.reference_adversary render-stage2` writes
#      cases/<id>/stage2_prompt.md from the valid stage 1 (which it embeds
#      verbatim with its sha256) and the derivation in derivations/<id>.md, and
#      drops a verdict judged on another stage-2 prompt.
#   3. Stage 2, unless cases/<id>/verdict.json is already schema-valid.
# Resumable: a second run over a finished directory makes no judge call.
#
# Blinding: every call runs from a fresh empty directory outside any git
# repository, in safe mode (CLAUDE_CODE_SAFE_MODE=1, no CLAUDE.md files), with
# no MCP servers and no user settings, and with exactly two tools, WebSearch
# and WebFetch (--tools); every file, shell and editing tool is absent, so the
# judge can read no file. WebFetch is denied on each blocked domain
# (BLOCKED_DOMAINS: policybench.org, policyengine.org, github.com,
# raw.githubusercontent.com and their www hosts) by a WebFetch(domain:...)
# rule. After each call, `finalize` audits the session transcript: an output
# is rejected ("[contaminated]") if the judge called any other tool, got
# content from a blocked URL or any URL naming PolicyEngine or PolicyBench (a
# fetch the deny rule refused returned nothing and is only recorded), searched
# for them, or saw a user message other than its prompt; and rejected
# ("[invalid]") unless it satisfies the stage's schema, cites no blocked
# source, and is the judge's one accepted StructuredOutput answer.
#
# Credentials: CLAUDE_CONFIG_DIR must name the lane's config directory, which
# may not be the desktop login's (~/.claude, compared by file identity); a
# keychain-token lane passes its token as CLAUDE_CODE_OAUTH_TOKEN and names its
# account in AUDIT_ACCOUNT. JUDGE_ALLOW_DESKTOP_LOGIN=1 (Max, 2026-09-30) runs
# the judges on the desktop login instead. Every claude call gets an
# allowlisted environment (PATH, HOME, user, locale, temp dir, the config dir
# and the token), so no API key, provider switch or base URL reaches it, and
# `claude auth status` must report a first-party subscription login before any
# judge runs. A call the API refuses with 401, 403 or 429 stops the run: no
# further judge starts, and the run resumes where it stopped.
#
# Provenance: beside stage1.json and verdict.json the runner writes
# stage1.meta.json and verdict.meta.json with the runner, the stage, the model
# requested and the models the CLI reports, the CLI version, the effort, the
# session id, the UTC time, the sha256 of the exact prompt bytes the judge
# read, the sha256 of the output it describes (a sidecar whose hash does not
# match is stale), the stage 1 sha256 (verdict only), the tool policy, the
# blinding ("tools"), the searches and fetches, and the login. The session
# transcript is kept as stage<N>.claude.transcript.jsonl.
#
# Environment: AUDIT_PARALLEL (positive integer, default 4), AUDIT_MODEL
# (default opus), AUDIT_EFFORT (low, medium, high, xhigh or max; default
# xhigh), AUDIT_PYTHON (an interpreter with policybench and jsonschema),
# AUDIT_CLAUDE_BIN (default claude), AUDIT_ONLY (space-separated case ids).
# Portable to bash 3.2.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ADV_DIR="${1:?usage: run_reference_adversary_claude.sh <adversary_dir>}"
PARALLEL="${AUDIT_PARALLEL:-4}"
MODEL="${AUDIT_MODEL:-opus}"
EFFORT="${AUDIT_EFFORT:-xhigh}"
ONLY="${AUDIT_ONLY:-}"
if [ -n "${AUDIT_PYTHON:-}" ]; then
  PYTHON="$AUDIT_PYTHON"
elif [ -x "$REPO_DIR/.venv/bin/python" ]; then
  PYTHON="$REPO_DIR/.venv/bin/python"
else
  PYTHON="python3"
fi
CLAUDE_BIN="${AUDIT_CLAUDE_BIN:-claude}"
export PYTHONPATH="$REPO_DIR${PYTHONPATH:+:$PYTHONPATH}"
adversary() { "$PYTHON" -m policybench.reference_adversary "$@"; }

{ command -v "$PYTHON" >/dev/null 2>&1 || [ -x "$PYTHON" ]; } || {
  echo "no python interpreter; set AUDIT_PYTHON" >&2
  exit 1
}
"$PYTHON" -c "import jsonschema, policybench.reference_adversary" >/dev/null 2>&1 || {
  echo "$PYTHON cannot import jsonschema and policybench.reference_adversary;" >&2
  echo "run inside the project environment (uv sync --extra dev) or set AUDIT_PYTHON." >&2
  echo "Refusing to start: outputs could not be validated." >&2
  exit 1
}
command -v "$CLAUDE_BIN" >/dev/null 2>&1 || {
  echo "claude CLI not found; set AUDIT_CLAUDE_BIN" >&2
  exit 1
}
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

for file in schema_stage1.json schema_verdict.json cases.jsonl; do
  [ -f "$ADV_DIR/$file" ] || {
    echo "missing $ADV_DIR/$file — run policybench adversary-prepare first" >&2
    exit 1
  }
done
ADV_DIR="$(cd "$ADV_DIR" && pwd)"
CASES_DIR="$ADV_DIR/cases"
SCHEMA1="$ADV_DIR/schema_stage1.json"
SCHEMAV="$ADV_DIR/schema_verdict.json"
SCHEMA1_JSON=$(cat "$SCHEMA1")
SCHEMAV_JSON=$(cat "$SCHEMAV")
# One WebFetch(domain:...) deny rule per blocked domain, from the module.
BLOCKED=$("$PYTHON" -c 'from policybench.reference_adversary import BLOCKED_DOMAINS
print(",".join(f"WebFetch(domain:{d})" for d in BLOCKED_DOMAINS))') || exit 1
TOOLS="WebSearch,WebFetch"

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
# Prints "desktop" when a directory is the desktop login's ~/.claude (by file
# identity, under $HOME or the account's own home), "other" when it is not.
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
    echo "JUDGE_ALLOW_DESKTOP_LOGIN=1 but there is no $HOME/.claude; refusing to start" >&2
    exit 1
  }
  if [ -n "${CLAUDE_CONFIG_DIR:-}" ]; then
    { [ -d "$CLAUDE_CONFIG_DIR" ] \
      && [ "$(desktop_dir_state "$CLAUDE_CONFIG_DIR")" = desktop ]; } || {
      echo "JUDGE_ALLOW_DESKTOP_LOGIN=1 but CLAUDE_CONFIG_DIR is not the desktop's ~/.claude; refusing to start" >&2
      exit 1
    }
  fi
  CONFIG_DIR="$(cd "$HOME/.claude" && pwd -P)"
else
  [ -n "${CLAUDE_CONFIG_DIR:-}" ] || {
    echo "CLAUDE_CONFIG_DIR is not set: the judges would bill the desktop login." >&2
    echo "Run inside a Subfleet lane (see the header). Refusing to start." >&2
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
[ "$DESKTOP_OPT_IN" = 1 ] || CHILD_ENV+=("CLAUDE_CONFIG_DIR=$CONFIG_DIR")
CHILD_ENV+=("CLAUDE_CODE_SAFE_MODE=1" "CLAUDE_CODE_DISABLE_CLAUDE_MDS=1")
DESKTOP_ENV=()
while IFS= read -r line; do [ -n "$line" ] && DESKTOP_ENV+=("$line"); done <<EOF
$(allowlist PATH HOME USER LOGNAME TMPDIR LANG LC_ALL LC_CTYPE)
EOF
claude_child() { env -i "${CHILD_ENV[@]}" "$CLAUDE_BIN" "$@"; }

probe=$(mktemp -d "${TMPDIR:-/tmp}/pb-adversary-auth.XXXXXX") || exit 1
AUTH_JSON=$(cd "$probe" && claude_child auth status </dev/null 2>/dev/null)
DESKTOP_JSON=$(cd "$probe" && env -i "${DESKTOP_ENV[@]}" "$CLAUDE_BIN" auth status </dev/null 2>/dev/null)
rmdir "$probe" 2>/dev/null
TOKEN_SET=0
[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] && TOKEN_SET=1
AUTH=$(adversary check-login --status "$AUTH_JSON" --desktop-status "$DESKTOP_JSON" \
  --token-set "$TOKEN_SET" --declared "${AUDIT_ACCOUNT:-}" --config-dir "$CONFIG_DIR" \
  --desktop-opt-in "$DESKTOP_OPT_IN") || {
  echo "refusing to start: the judges must bill the lane's own subscription login" >&2
  exit 1
}
DECLARED="${AUDIT_ACCOUNT:-}"
[ "$DESKTOP_OPT_IN" = 1 ] && DECLARED="$DESKTOP_DECLARED"
CLI_VERSION=$(cd / && claude_child --version </dev/null 2>/dev/null | head -n 1)

valid() { [ -s "$2" ] && adversary validate --schema "$1" --file "$2" >/dev/null 2>&1; }
sha256() {
  "$PYTHON" -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$1"
}

# One judge call: stage 1 or 2 of one case. Publishes the output and its
# sidecar atomically, only once finalize accepts them.
judge_stage() {
  case_dir="$1"; stage="$2"; name=$(basename "$case_dir")
  if [ "$stage" = 1 ]; then
    prompt="$case_dir/stage1_prompt.md"; out="$case_dir/stage1.json"
    meta="$case_dir/stage1.meta.json"; schema="$SCHEMA1"; schema_json="$SCHEMA1_JSON"
  else
    prompt="$case_dir/stage2_prompt.md"; out="$case_dir/verdict.json"
    meta="$case_dir/verdict.meta.json"; schema="$SCHEMAV"; schema_json="$SCHEMAV_JSON"
  fi
  tag="stage$stage"
  envelope="$case_dir/$tag.claude.json"
  log="$case_dir/$tag.claude.log"
  transcript="$case_dir/$tag.claude.transcript.jsonl"
  rm -f "$out.tmp" "$meta.tmp" "$meta" "$envelope" "$transcript"
  work=$(mktemp -d "${TMPDIR:-/tmp}/pb-adversary.XXXXXX") || {
    echo "[FAIL] $name stage $stage (no scratch directory)"
    return 1
  }
  if git -C "$work" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    rmdir "$work"
    echo "[FAIL] $name stage $stage (scratch directory is inside a git repository)"
    return 1
  fi
  # The judged bytes: a private copy of the prompt, hashed before the call.
  judged=$(mktemp "${TMPDIR:-/tmp}/pb-adversary-prompt.XXXXXX") || {
    rmdir "$work"
    echo "[FAIL] $name stage $stage (no scratch file for the prompt)"
    return 1
  }
  if ! cp "$prompt" "$judged" || ! judged_sha=$(sha256 "$judged"); then
    rm -f "$judged"; rmdir "$work"
    echo "[FAIL] $name stage $stage (could not copy and hash the prompt)"
    return 1
  fi
  ( cd "$work" && claude_child -p \
      --model "$MODEL" \
      --output-format json \
      --json-schema "$schema_json" \
      --tools "$TOOLS" \
      --allowedTools "$TOOLS" \
      --disallowedTools "$BLOCKED" \
      --strict-mcp-config \
      --disable-slash-commands \
      --setting-sources project,local \
      --effort "$EFFORT" \
      < "$judged" > "$envelope" 2> "$log" )
  rmdir "$work" 2>/dev/null || echo "[warn] $name stage $stage: the judge left files in $work"
  adversary finalize --runner claude --stage "$stage" --raw "$envelope" \
    --schema "$schema" --out "$out.tmp" --meta "$meta.tmp" \
    --prompt-file "$judged" --prompt-sha256 "$judged_sha" --case-prompt "$prompt" \
    --stage1 "$case_dir/stage1.json" --model-requested "$MODEL" \
    --cli-version "$CLI_VERSION" --effort "$EFFORT" --config-dir "$CONFIG_DIR" \
    --transcript-out "$transcript" --auth "$AUTH" --account "$DECLARED" \
    2>> "$log"
  status=$?
  rm -f "$judged"
  if [ "$status" = 0 ]; then
    mv -f "$out.tmp" "$out"
    mv -f "$meta.tmp" "$meta"
    echo "[ok] $name stage $stage"
    return 0
  fi
  rm -f "$out.tmp" "$meta.tmp"
  case "$status" in
    2) echo "[contaminated] $name stage $stage (see $tag.claude.log)" ;;
    7)
      : > "$STOP_FLAG"
      echo "[FAIL] $name stage $stage (the login cannot judge now; see $tag.claude.log)"
      ;;
    *) echo "[invalid] $name stage $stage (see $tag.claude.log)" ;;
  esac
  return 1
}

judge_case() {
  case_dir="$1"; name=$(basename "$case_dir")
  [ -f "$case_dir/stage1_prompt.md" ] || return 0
  if ! valid "$SCHEMA1" "$case_dir/stage1.json"; then
    # Stage 2 rests on stage 1: judging stage 1 afresh leaves none behind.
    rm -f "$case_dir/stage1.json" "$case_dir/stage2_prompt.md" \
      "$case_dir/verdict.json" "$case_dir/verdict.meta.json"
    [ -e "$STOP_FLAG" ] && return 0
    judge_stage "$case_dir" 1 || return 0
  fi
  if ! adversary render-stage2 --adversary-dir "$ADV_DIR" --case-id "$name" \
      >/dev/null 2> "$case_dir/stage2.render.log"; then
    echo "[FAIL] $name (no stage-2 prompt; see stage2.render.log)"
    return 0
  fi
  valid "$SCHEMAV" "$case_dir/verdict.json" && return 0
  rm -f "$case_dir/verdict.json" "$case_dir/verdict.meta.json"
  [ -e "$STOP_FLAG" ] && return 0
  judge_stage "$case_dir" 2
  return 0
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

total=$(find "$CASES_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
echo "reference adversary: $total cases | parallel=$PARALLEL model=$MODEL effort=$EFFORT runner=claude ($CLI_VERSION)"
echo "login: $AUTH in $CONFIG_DIR${DECLARED:+ (declared: $DECLARED)}"
RUN_STATE=$(mktemp -d "${TMPDIR:-/tmp}/pb-adversary-run.XXXXXX") || exit 1
STOP_FLAG="$RUN_STATE/stop"

# A rolling pool: at most PARALLEL cases run at once, and the next case
# starts as soon as any running one finishes, so one slow case holds one slot
# rather than a whole batch. bash 3.2 has no `wait -n`; `jobs -pr` lists the
# running cases (a finished case it has not yet noticed only delays a start).
running_cases() { jobs -pr | wc -l | tr -d ' '; }
for case_dir in "$CASES_DIR"/*/; do
  [ -d "$case_dir" ] || continue
  case_dir="${case_dir%/}"
  selected "$(basename "$case_dir")" || continue
  while [ "$(running_cases)" -ge "$PARALLEL" ]; do sleep 1; done
  [ -e "$STOP_FLAG" ] && break
  judge_case "$case_dir" &
done
wait

stopped=0
[ -e "$STOP_FLAG" ] && stopped=1
rm -f "$STOP_FLAG"
rmdir "$RUN_STATE" 2>/dev/null
done_count=0
for case_dir in "$CASES_DIR"/*/; do
  [ -d "$case_dir" ] || continue
  valid "$SCHEMAV" "${case_dir%/}/verdict.json" && done_count=$((done_count + 1))
done
echo "reference adversary complete: $done_count/$total verdicts present"
if [ "$stopped" = 1 ]; then
  echo "stopped: the login cannot judge now (see the failed case's log); no further judge was started" >&2
  exit 1
fi
