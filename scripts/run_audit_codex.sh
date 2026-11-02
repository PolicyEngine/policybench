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
#
# Judge provenance: beside each verdict.json the runner writes verdict.meta.json
# (the same sidecar scripts/run_audit_claude.sh writes) with the model Codex
# reports in its log header, the model requested, the UTC timestamp, the
# verdict's sha256, so a re-judged case can never keep the other runner's
# provenance, and the bytes Codex judged: a private copy of prompt.md, taken
# before it runs, whose sha256 the sidecar records as prompt_sha256 and whose
# judge template version it records as judge_template_version
# (policybench.judge_template; null for a prompt audit-prepare did not render).
# A verdict is not published if prompt.md no longer holds those bytes.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AUDIT_DIR="${1:?usage: run_audit_codex.sh <audit_dir>}"
SCHEMA="$AUDIT_DIR/schema.json"
CASES_DIR="$AUDIT_DIR/cases"
PARALLEL="${AUDIT_PARALLEL:-4}"
EFFORT="${AUDIT_REASONING_EFFORT:-low}"
# Verdict validation needs jsonschema: prefer the project virtual environment's
# interpreter (uv sync installs it), then an explicit AUDIT_PYTHON, then python3.
if [ -n "${AUDIT_PYTHON:-}" ]; then
  PYTHON="$AUDIT_PYTHON"
elif [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python3"
fi
# Fail fast rather than burn classifier calls making zero progress: verdict
# validation needs a working interpreter.
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
MODEL_FLAG=""
[ -n "${AUDIT_MODEL:-}" ] && MODEL_FLAG="-m ${AUDIT_MODEL}"

[ -f "$SCHEMA" ] || { echo "missing $SCHEMA — run audit-prepare first" >&2; exit 1; }

# A verdict is "done" only if it is parseable JSON carrying the required keys.
# A substring check alone would accept a verdict.json truncated mid-write
# (interrupted codex run), which the runner would then skip forever while the
# collector reports it permanently missing.
verdict_ok() {
  # A verdict counts only if it satisfies the audit schema in full (every
  # required key, enum values, no extra properties); a partial object from a
  # fallback parse must not be published or mark the case complete.
  [ -s "$1" ] || return 1
  "$PYTHON" "$SCRIPT_DIR/validate_verdict.py" "$SCHEMA" "$1" >/dev/null 2>&1
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
  # effort (xhigh) is wasteful for classification, so it is lowered. A sidecar
  # left from a previous verdict describes a verdict that no longer exists,
  # and an invalid verdict.json goes too, so no verdict sits beside this
  # run's sidecar until this run's verdict is published: audit-prepare
  # removes a sidecar only together with the verdict it describes.
  rm -f "$tmp" "$out" "$case_dir/verdict.meta.json"
  # Codex reads a private copy, so the sidecar describes the bytes it judged
  # even if audit-prepare rewrites prompt.md meanwhile.
  judged=$(mktemp "${TMPDIR:-/tmp}/pb-codex-prompt.XXXXXX") || {
    echo "[FAIL] $(basename "$case_dir") (cannot copy prompt.md)"; return 0; }
  # Each case runs in its own background subshell: a worker terminated
  # mid-case still removes its copy.
  trap 'rm -f "$judged"' EXIT
  trap 'rm -f "$judged"; exit 143' TERM
  trap 'rm -f "$judged"; exit 130' INT
  cp "$prompt" "$judged" || {
    rm -f "$judged"; echo "[FAIL] $(basename "$case_dir") (cannot copy prompt.md)"
    return 0; }
  codex exec \
    --sandbox read-only \
    --skip-git-repo-check \
    --ephemeral \
    --color never \
    $MODEL_FLAG \
    -c model_reasoning_effort="$EFFORT" \
    --output-schema "$SCHEMA" \
    -o "$tmp" \
    - < "$judged" > "$case_dir/codex.log" 2>&1
  if verdict_ok "$tmp" && write_provenance "$tmp" "$case_dir/codex.log" \
      "$case_dir/verdict.meta.json.tmp" "$judged" "$prompt"; then
    # The sidecar first: an interrupted publish leaves at most a sidecar
    # without a verdict, which the next run removes, and never a verdict
    # without its sidecar, which audit-prepare would read as a legacy v1
    # verdict with no record of the bytes its judge read.
    mv -f "$case_dir/verdict.meta.json.tmp" "$case_dir/verdict.meta.json"
    mv -f "$tmp" "$out"
    echo "[ok] $(basename "$case_dir")"
  else
    rm -f "$tmp" "$case_dir/verdict.meta.json.tmp"
    echo "[FAIL] $(basename "$case_dir") (see codex.log)"
  fi
  rm -f "$judged"
}

# Provenance sidecar for a validated verdict: the model Codex reports in its
# log header (`model: ...`), the model requested (or "default"), the UTC time,
# the verdict's sha256 so the sidecar cannot outlive the verdict it describes,
# and the sha256 and judge template version of the copy Codex judged. Fails,
# so the verdict is not published, when prompt.md no longer holds that copy's
# bytes.
write_provenance() {
  verdict_path="$1"; log_path="$2"; meta_out="$3"; judged_path="$4"
  prompt_path="$5"
  "$PYTHON" - "$verdict_path" "$log_path" "$meta_out" "${AUDIT_MODEL:-default}" \
    "$judged_path" "$prompt_path" "$SCRIPT_DIR" <<'PY'
import datetime, hashlib, json, re, sys
from pathlib import Path
(verdict_path, log_path, meta_out, requested, judged_path, prompt_path,
 script_dir) = sys.argv[1:8]
sys.path.insert(0, str(Path(script_dir).resolve().parent))
from policybench.judge_template import template_version_of
judged = open(judged_path, "rb").read()
try:
    live = open(prompt_path, "rb").read()
except OSError:
    live = None
if live != judged:
    print("prompt.md changed while Codex judged it", file=sys.stderr)
    sys.exit(1)
verdict = open(verdict_path, "rb").read()
reported = []
try:
    match = re.search(r"^model: (\S+)$", open(log_path, encoding="utf-8", errors="replace").read(), re.M)
    if match:
        reported = [match.group(1)]
except OSError:
    pass
meta = {
    "judge_runner": "scripts/run_audit_codex.sh",
    "verdict_sha256": hashlib.sha256(verdict).hexdigest(),
    "judge_model_requested": requested,
    "judge_model_reported": reported,
    "judged_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    # The exact bytes Codex read on stdin, copied before it ran.
    "prompt_sha256": hashlib.sha256(judged).hexdigest(),
    "judge_template_version": template_version_of(judged),
}
json.dump(meta, open(meta_out, "w"), indent=2, sort_keys=True)
PY
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
