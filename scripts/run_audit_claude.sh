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
# Run it inside a Subfleet Claude lane (`subfleet run --task build --tier
# standard ...`) so the child `claude -p` calls inherit that lane's login
# instead of the interactive app login. Concurrency and model are tunable via
# env (AUDIT_PARALLEL, AUDIT_MODEL; default model opus). Portable to bash 3.2.
#
# Judge provenance: beside each verdict.json the runner writes
# verdict.meta.json with the judge model requested, the model the CLI reports,
# the CLI version, the session id, and the UTC timestamp, so annotations can
# carry which judge produced them.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AUDIT_DIR="${1:?usage: run_audit_claude.sh <audit_dir>}"
SCHEMA="$AUDIT_DIR/schema.json"
CASES_DIR="$AUDIT_DIR/cases"
PARALLEL="${AUDIT_PARALLEL:-4}"
MODEL="${AUDIT_MODEL:-opus}"
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
SCHEMA_JSON=$(cat "$SCHEMA")
CLI_VERSION=$("$CLAUDE_BIN" --version 2>/dev/null | head -n 1)

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
# the `result` text as JSON. Also emit the provenance sidecar.
extract_verdict() {
  envelope="$1"; out_tmp="$2"; meta_tmp="$3"; requested_model="$4"; cli_version="$5"
  "$PYTHON" - "$envelope" "$out_tmp" "$meta_tmp" "$requested_model" "$cli_version" <<'PY'
import datetime, hashlib, json, sys
envelope_path, out_path, meta_path, requested_model, cli_version = sys.argv[1:6]
try:
    envelope = json.load(open(envelope_path))
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
verdict_bytes = json.dumps(verdict, indent=2, sort_keys=True).encode("utf-8")
open(out_path, "wb").write(verdict_bytes)
meta = {
    "judge_runner": "scripts/run_audit_claude.sh",
    # Binds the sidecar to this verdict: a sidecar whose hash does not match
    # the case's verdict.json is stale and carries no provenance.
    "verdict_sha256": hashlib.sha256(verdict_bytes).hexdigest(),
    "judge_model_requested": requested_model,
    "judge_model_reported": sorted((envelope.get("modelUsage") or {}).keys()),
    "judge_cli_version": cli_version,
    "session_id": envelope.get("session_id"),
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
  rm -f "$tmp" "$meta_tmp" "$envelope" "$case_dir/verdict.meta.json"
  # Self-contained prompt, no tools, no project instructions; the schema
  # enforces the JSON shape. Publish atomically only once it validates.
  CLAUDE_CODE_SAFE_MODE=1 CLAUDE_CODE_DISABLE_CLAUDE_MDS=1 \
    "$CLAUDE_BIN" -p \
      --model "$MODEL" \
      --output-format json \
      --json-schema "$SCHEMA_JSON" \
      --disallowedTools "Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch,Agent" \
      --strict-mcp-config \
      < "$prompt" > "$envelope" 2> "$case_dir/claude.log"
  if extract_verdict "$envelope" "$tmp" "$meta_tmp" "$MODEL" "$CLI_VERSION" \
    && verdict_ok "$tmp"; then
    mv -f "$tmp" "$out"
    mv -f "$meta_tmp" "$case_dir/verdict.meta.json"
    echo "[ok] $(basename "$case_dir")"
  else
    rm -f "$tmp" "$meta_tmp"
    echo "[FAIL] $(basename "$case_dir") (see claude.log / claude.json)"
  fi
}

total=$(ls -d "$CASES_DIR"/*/ 2>/dev/null | wc -l | tr -d ' ')
echo "audit: $total cases | parallel=$PARALLEL model=$MODEL runner=claude ($CLI_VERSION)"

i=0
pids=""
for case_dir in "$CASES_DIR"/*/; do
  case_dir="${case_dir%/}"
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
