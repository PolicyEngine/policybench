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
PYTHON="${AUDIT_PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=".venv/bin/python"
# Fail fast rather than burn classifier calls making zero progress: verdict
# validation needs a working interpreter.
command -v "$PYTHON" >/dev/null 2>&1 || [ -x "$PYTHON" ] || {
  echo "no python interpreter for verdict validation; set AUDIT_PYTHON" >&2
  exit 1
}
MODEL_FLAG=""
[ -n "${AUDIT_MODEL:-}" ] && MODEL_FLAG="-m ${AUDIT_MODEL}"

[ -f "$SCHEMA" ] || { echo "missing $SCHEMA — run audit-prepare first" >&2; exit 1; }

# A verdict is "done" only if it is parseable JSON carrying the required keys.
# A substring check alone would accept a verdict.json truncated mid-write
# (interrupted codex run), which the runner would then skip forever while the
# collector reports it permanently missing.
verdict_ok() {
  [ -s "$1" ] || return 1
  "$PYTHON" - "$1" <<'PY' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
sys.exit(0 if isinstance(d, dict) and {"case_failure_source", "models"} <= d.keys() else 1)
PY
}

classify_one() {
  case_dir="$1"
  prompt="$case_dir/prompt.md"
  out="$case_dir/verdict.json"
  tmp="$case_dir/verdict.json.tmp"
  [ -f "$prompt" ] || return 0
  verdict_ok "$out" && return 0
  # Self-contained prompt; read-only sandbox; enforce the JSON shape. Write to a
  # temp file and publish atomically only once it validates, so an interrupted
  # run never leaves a half-written verdict that looks done. Default reasoning
  # effort (xhigh) is wasteful for classification, so it is lowered.
  rm -f "$tmp"
  codex exec \
    --sandbox read-only \
    --skip-git-repo-check \
    --ephemeral \
    --color never \
    $MODEL_FLAG \
    -c model_reasoning_effort="$EFFORT" \
    --output-schema "$SCHEMA" \
    -o "$tmp" \
    - < "$prompt" > "$case_dir/codex.log" 2>&1
  if verdict_ok "$tmp"; then
    mv -f "$tmp" "$out"
    echo "[ok] $(basename "$case_dir")"
  else
    rm -f "$tmp"
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
