#!/usr/bin/env bash
# Bulk failure-audit classifier, run through the Codex CLI so the work bills to
# a ChatGPT plan rather than a metered API key.
#
#   policybench audit-prepare --country-dir <dir> --audit-dir <audit>
#   scripts/run_audit_codex.sh <audit>          # this script
#   policybench audit-collect  --country-dir <dir> --audit-dir <audit>
#
# Resumable: a case is skipped once it has a verdict.json carrying the required
# keys. Re-run freely after interruptions or to fill in failures. Concurrency,
# model, and reasoning effort are tunable via env. Portable to bash 3.2 (macOS).
set -u

AUDIT_DIR="${1:?usage: run_audit_codex.sh <audit_dir>}"
SCHEMA="$AUDIT_DIR/schema.json"
CASES_DIR="$AUDIT_DIR/cases"
PARALLEL="${AUDIT_PARALLEL:-4}"
EFFORT="${AUDIT_REASONING_EFFORT:-low}"
MODEL_FLAG=""
[ -n "${AUDIT_MODEL:-}" ] && MODEL_FLAG="-m ${AUDIT_MODEL}"

[ -f "$SCHEMA" ] || { echo "missing $SCHEMA — run audit-prepare first" >&2; exit 1; }

# A verdict is "done" if it carries the required keys. Full JSON validation
# happens later in `policybench audit-collect`; this is just the skip gate.
verdict_ok() {
  [ -s "$1" ] && grep -q '"case_failure_source"' "$1" && grep -q '"models"' "$1"
}

classify_one() {
  case_dir="$1"
  prompt="$case_dir/prompt.md"
  out="$case_dir/verdict.json"
  [ -f "$prompt" ] || return 0
  verdict_ok "$out" && return 0
  # Self-contained prompt; read-only sandbox; enforce the JSON shape; write the
  # final message to verdict.json. Default reasoning effort (xhigh) is wasteful
  # for classification, so it is lowered.
  codex exec \
    --sandbox read-only \
    --skip-git-repo-check \
    --ephemeral \
    --color never \
    $MODEL_FLAG \
    -c model_reasoning_effort="$EFFORT" \
    --output-schema "$SCHEMA" \
    -o "$out" \
    - < "$prompt" > "$case_dir/codex.log" 2>&1
  if verdict_ok "$out"; then
    echo "[ok] $(basename "$case_dir")"
  else
    echo "[FAIL] $(basename "$case_dir") (see codex.log)"
  fi
}

total=$(find "$CASES_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
echo "audit: $total cases | parallel=$PARALLEL effort=$EFFORT model=${AUDIT_MODEL:-default}"

# Bounded concurrency: launch in batches of $PARALLEL and wait for each batch.
# Portable to bash 3.2 (no `wait -n` / `mapfile`).
i=0
pids=""
while IFS= read -r case_dir; do
  classify_one "$case_dir" &
  pids="$pids $!"
  i=$((i + 1))
  if [ $((i % PARALLEL)) -eq 0 ]; then
    wait $pids 2>/dev/null
    pids=""
  fi
done < <(find "$CASES_DIR" -mindepth 1 -maxdepth 1 -type d | sort)
[ -n "$pids" ] && wait $pids 2>/dev/null

done_count=0
while IFS= read -r case_dir; do
  verdict_ok "$case_dir/verdict.json" && done_count=$((done_count + 1))
done < <(find "$CASES_DIR" -mindepth 1 -maxdepth 1 -type d)
echo "audit complete: $done_count/$total verdicts present"
