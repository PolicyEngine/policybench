#!/usr/bin/env bash
# Reference adversary judge, run through the Codex CLI. The adversary attacks
# consensus-flagged references from primary law; see
# policybench/reference_adversary.py for the design and the output contracts.
#
#   policybench consensus-flags --payload <data.json.gz> --output <flags.json>
#   policybench adversary-prepare --payload <data.json.gz> --flags <flags.json> \
#       --adversary-dir <dir> --annotations-dir <frozen annotations>
#   scripts/run_reference_adversary_codex.sh <dir>         # this script
#   policybench adversary-collect --adversary-dir codex=<dir> --output-dir <out>
#
# Run it inside a Subfleet lane, so that every judge call bills to the lane's
# ChatGPT subscription. Never with an API key: every codex call gets an
# allowlisted environment (PATH, HOME, user, locale, temp dir and CODEX_HOME),
# so no API key, base URL or provider switch reaches it, and the runner
# refuses to start unless `codex login status` reports a ChatGPT login. It
# also refuses a Codex home that holds an AGENTS.md, whose instructions could
# reach the judge outside the audited tool events.
# Give each judge its own adversary directory: stage 1 and the verdict of a
# case must come from the same runner.
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
# Each call is
#   codex --search exec --json --sandbox read-only --skip-git-repo-check \
#     --ephemeral --color never -C <empty temp dir> [-m AUDIT_MODEL] \
#     -c model_reasoning_effort=<effort> --output-schema <schema> -o <out> -
# run from that empty directory with the prompt on stdin. --search (a
# top-level flag; codex-cli 0.159.0 rejects it after exec) gives the judge
# live web search.
#
# Blinding: Codex's read-only sandbox still lets the judge read files by
# absolute path, so the runner audits what it did. --json makes Codex print
# its events as JSON lines (kept as stage<N>.codex.events.jsonl), and
# `finalize` inspects every tool event, never the judge's own messages or
# reasoning; it also scans Codex's stderr, which in --json mode does not echo
# the prompt (the --json runs examined held status lines only). An output is
# rejected ("[contaminated]") if a shell command or its output names a
# derivation-bearing path or name (derivations/,
# us_case_reference_explanations, data.json, referenceExplanation,
# stage2_prompt, another judge's stage1.json or verdict.json, the frozen case
# notes or adjudications, policybench, policyengine), if the judge opened a
# URL on a blocked domain (BLOCKED_DOMAINS) or searched for PolicyEngine or
# PolicyBench, or if it used any other tool (an MCP call, a sub-agent, a file
# change). Both stages are audited. An output is rejected ("[invalid]") unless
# it satisfies the stage's schema and cites no blocked source.
#
# Limits, unlike the Claude runner: Codex's event log records a web search's
# query but not its results, so a search result that lists a PolicyEngine or
# GitHub page cannot be detected (the prompt asks the judge to exclude those
# domains); and a call the provider refuses fails only its own case, so a
# refused lane fails every remaining call before the run ends.
#
# Provenance: beside stage1.json and verdict.json the runner writes
# stage1.meta.json and verdict.meta.json with the runner, the stage, the model
# requested (Codex's JSON events do not report the model), the CLI version,
# the effort, the thread id, the UTC time, the sha256 of the exact prompt bytes
# the judge read, the sha256 of the output it describes (a sidecar whose hash
# does not match is stale), the stage 1 sha256 (verdict only), the tool
# policy, the blinding ("cwd+log-audit"), and the searches, opened URLs and
# commands.
#
# Environment: AUDIT_PARALLEL (positive integer, default 4), AUDIT_MODEL
# (default: the lane's), AUDIT_REASONING_EFFORT or AUDIT_EFFORT (default high),
# AUDIT_PYTHON (an interpreter with policybench and jsonschema),
# AUDIT_CODEX_BIN (default codex), AUDIT_ONLY (space-separated case ids).
# Portable to bash 3.2.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ADV_DIR="${1:?usage: run_reference_adversary_codex.sh <adversary_dir>}"
PARALLEL="${AUDIT_PARALLEL:-4}"
EFFORT="${AUDIT_REASONING_EFFORT:-${AUDIT_EFFORT:-high}}"
MODEL="${AUDIT_MODEL:-}"
ONLY="${AUDIT_ONLY:-}"
if [ -n "${AUDIT_PYTHON:-}" ]; then
  PYTHON="$AUDIT_PYTHON"
elif [ -x "$REPO_DIR/.venv/bin/python" ]; then
  PYTHON="$REPO_DIR/.venv/bin/python"
else
  PYTHON="python3"
fi
CODEX_BIN="${AUDIT_CODEX_BIN:-codex}"
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
command -v "$CODEX_BIN" >/dev/null 2>&1 || {
  echo "codex CLI not found; set AUDIT_CODEX_BIN" >&2
  exit 1
}
CODEX_BIN="$(command -v "$CODEX_BIN")"
case "$CODEX_BIN" in /*) ;; *) CODEX_BIN="$(pwd)/$CODEX_BIN" ;; esac
case "$PARALLEL" in
  '' | *[!0-9]* | 0)
    echo "AUDIT_PARALLEL must be a positive integer, not '$PARALLEL'; refusing to start" >&2
    exit 1
    ;;
esac
case "$EFFORT" in
  '' | *[!a-z]*)
    echo "the reasoning effort must be a word such as low, medium, high or xhigh, not '$EFFORT'; refusing to start" >&2
    exit 1
    ;;
esac
MODEL_FLAG=""
if [ -n "$MODEL" ]; then
  case "$MODEL" in
    *[!A-Za-z0-9._-]*)
      echo "AUDIT_MODEL must be a model id, not '$MODEL'; refusing to start" >&2
      exit 1
      ;;
  esac
  MODEL_FLAG="-m $MODEL"
fi

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

# Never an API key (see the header): only these variables reach codex.
CODEX_ENV=()
for var in PATH HOME USER LOGNAME LANG LC_ALL TMPDIR CODEX_HOME; do
  eval "value=\${$var-}"
  [ -n "$value" ] && CODEX_ENV+=("$var=$value")
done
codex_child() { env -i "${CODEX_ENV[@]}" "$CODEX_BIN" "$@"; }
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
[ -e "$CODEX_HOME_DIR/AGENTS.md" ] && {
  echo "$CODEX_HOME_DIR/AGENTS.md exists: its instructions could reach the judge; use a lane home without one" >&2
  exit 1
}
LOGIN=$(cd / && codex_child login status </dev/null 2>&1 | head -n 1)
case "$LOGIN" in
  "Logged in using ChatGPT"*) ;;
  *)
    echo "codex login status reports '$LOGIN', not a ChatGPT login; refusing to start" >&2
    echo "(run inside a Subfleet lane: the judges must bill a ChatGPT subscription)" >&2
    exit 1
    ;;
esac
CLI_VERSION=$(cd / && codex_child --version </dev/null 2>/dev/null | head -n 1)

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
    meta="$case_dir/stage1.meta.json"; schema="$SCHEMA1"
  else
    prompt="$case_dir/stage2_prompt.md"; out="$case_dir/verdict.json"
    meta="$case_dir/verdict.meta.json"; schema="$SCHEMAV"
  fi
  tag="stage$stage"
  events="$case_dir/$tag.codex.events.jsonl"
  log="$case_dir/$tag.codex.log"
  raw="$case_dir/$tag.codex.out"
  rm -f "$out.tmp" "$meta.tmp" "$meta" "$events" "$raw"
  work=$(mktemp -d "${TMPDIR:-/tmp}/pb-adversary.XXXXXX") || {
    echo "[FAIL] $name stage $stage (no scratch directory)"
    return 1
  }
  if git -C "$work" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    rmdir "$work"
    echo "[FAIL] $name stage $stage (scratch directory is inside a git repository)"
    return 1
  fi
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
  ( cd "$work" && codex_child --search exec \
      --json \
      --sandbox read-only \
      --skip-git-repo-check \
      --ephemeral \
      --color never \
      -C "$work" \
      $MODEL_FLAG \
      -c model_reasoning_effort="$EFFORT" \
      --output-schema "$schema" \
      -o "$raw" \
      - < "$judged" > "$events" 2> "$log" )
  rmdir "$work" 2>/dev/null || echo "[warn] $name stage $stage: the judge left files in $work"
  adversary finalize --runner codex --stage "$stage" --raw "$raw" --events "$events" \
    --log "$log" \
    --schema "$schema" --out "$out.tmp" --meta "$meta.tmp" \
    --prompt-file "$judged" --prompt-sha256 "$judged_sha" --case-prompt "$prompt" \
    --stage1 "$case_dir/stage1.json" --model-requested "${MODEL:-default}" \
    --cli-version "$CLI_VERSION" --effort "$EFFORT" \
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
    2) echo "[contaminated] $name stage $stage (see $tag.codex.log)" ;;
    *) echo "[invalid] $name stage $stage (see $tag.codex.log)" ;;
  esac
  return 1
}

judge_case() {
  case_dir="$1"; name=$(basename "$case_dir")
  [ -f "$case_dir/stage1_prompt.md" ] || return 0
  if ! valid "$SCHEMA1" "$case_dir/stage1.json"; then
    # Stage 2 rests on stage 1: judging stage 1 afresh leaves none behind. A
    # stage-2 prompt left on disk would also hand the judge the derivation.
    rm -f "$case_dir/stage1.json" "$case_dir/stage2_prompt.md" \
      "$case_dir/verdict.json" "$case_dir/verdict.meta.json"
    judge_stage "$case_dir" 1 || return 0
  fi
  if ! adversary render-stage2 --adversary-dir "$ADV_DIR" --case-id "$name" \
      >/dev/null 2> "$case_dir/stage2.render.log"; then
    echo "[FAIL] $name (no stage-2 prompt; see stage2.render.log)"
    return 0
  fi
  valid "$SCHEMAV" "$case_dir/verdict.json" && return 0
  rm -f "$case_dir/verdict.json" "$case_dir/verdict.meta.json"
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
echo "reference adversary: $total cases | parallel=$PARALLEL effort=$EFFORT model=${MODEL:-default} runner=codex ($CLI_VERSION)"

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
  judge_case "$case_dir" &
done
wait

done_count=0
for case_dir in "$CASES_DIR"/*/; do
  [ -d "$case_dir" ] || continue
  valid "$SCHEMAV" "${case_dir%/}/verdict.json" && done_count=$((done_count + 1))
done
echo "reference adversary complete: $done_count/$total verdicts present"
