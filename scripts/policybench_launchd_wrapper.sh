#!/bin/bash
# launchd entry point for a supervised PolicyBench run (see scripts/launch_run.sh).
#
# Runs the supervisor in the foreground (under `caffeinate -i` when available),
# appends its output to the run directory, and translates the outcome into the
# exit code launchd's KeepAlive policy keys on:
#
#   exit 0   the run is finished: every scenario complete, or the supervisor
#            recorded a stopped_reason (budget stop, rounds exhausted). launchd
#            leaves the job alone; the job unloads itself.
#   exit 75  the supervisor died without finishing (SIGKILL, reboot, crash,
#            a stray `pkill`). launchd relaunches after ThrottleInterval and the
#            supervisor resumes from run_state.json and the scenario CSVs.
#
# After --max-restarts consecutive unfinished exits the wrapper gives up (exit 0
# and a .launchd_gave_up marker) so a persistent crash cannot loop forever.
#
# Portable to bash 3.2 (macOS). Usage:
#   policybench_launchd_wrapper.sh --run-dir DIR --label LABEL
#       [--max-restarts N] [--env-file FILE] [--no-caffeinate] -- COMMAND [ARGS...]
set -u

RUN_DIR=""
LABEL=""
MAX_RESTARTS=5
ENV_FILE=""
USE_CAFFEINATE=1
while [ $# -gt 0 ]; do
  case "$1" in
    --run-dir) RUN_DIR="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    --max-restarts) MAX_RESTARTS="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --no-caffeinate) USE_CAFFEINATE=0; shift ;;
    --) shift; break ;;
    *) echo "policybench_launchd_wrapper: unknown option $1" >&2; exit 64 ;;
  esac
done
[ -n "$RUN_DIR" ] || { echo "policybench_launchd_wrapper: --run-dir is required" >&2; exit 64; }
[ $# -gt 0 ] || { echo "policybench_launchd_wrapper: no command after --" >&2; exit 64; }

mkdir -p "$RUN_DIR" || exit 73
LOG="$RUN_DIR/supervisor.log"
STATE="$RUN_DIR/run_state.json"
RESTARTS_FILE="$RUN_DIR/.launchd_restarts"
DONE_MARKER="$RUN_DIR/.launchd_done"
GAVE_UP_MARKER="$RUN_DIR/.launchd_gave_up"

if [ -n "$ENV_FILE" ]; then
  if [ -r "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
  else
    echo "policybench_launchd_wrapper: cannot read --env-file $ENV_FILE" >&2
    exit 66
  fi
fi

stamp() { date "+%Y-%m-%d %H:%M:%S"; }
attempt=$(( $(cat "$RESTARTS_FILE" 2>/dev/null || echo 0) + 1 ))
{
  echo "=== $(stamp) launchd attempt $attempt pid $$ label ${LABEL:-?}"
  echo "=== command: $*"
} >> "$LOG"

if [ "$USE_CAFFEINATE" -eq 1 ] && command -v caffeinate >/dev/null 2>&1; then
  caffeinate -i "$@" >> "$LOG" 2>&1
else
  "$@" >> "$LOG" 2>&1
fi
rc=$?
echo "=== $(stamp) exited rc=$rc" >> "$LOG"

# Outcome from the supervisor's heartbeat file: "done" when every scenario is
# complete or a stopped_reason was recorded, "unfinished" otherwise, "nostate"
# when the file is missing or unreadable (a non-supervisor command, or a crash
# before the first heartbeat).
outcome=$(python3 - "$STATE" <<'PY' 2>/dev/null
import json, sys
try:
    state = json.load(open(sys.argv[1]))
except Exception:
    print("nostate"); sys.exit()
completed = state.get("completed")
total = state.get("total")
if isinstance(completed, list):
    completed = len(completed)
if state.get("stopped_reason") or (
    isinstance(completed, int) and isinstance(total, int) and total > 0 and completed >= total
):
    print("done")
else:
    print("unfinished")
PY
)
[ -n "$outcome" ] || outcome=nostate

finish() {  # $1 = marker file, $2 = message
  echo "=== $(stamp) $2" >> "$LOG"
  rm -f "$RESTARTS_FILE"
  date "+%Y-%m-%dT%H:%M:%S" > "$1"
  if [ -n "$LABEL" ] && command -v launchctl >/dev/null 2>&1; then
    # Unload the finished job so RunAtLoad does not replay it at the next login.
    rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
    (sleep 1; launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1) &
  fi
  exit 0
}

case "$outcome" in
  done) finish "$DONE_MARKER" "run finished (heartbeat says complete or stopped); unloading job" ;;
  nostate) [ "$rc" -eq 0 ] && finish "$DONE_MARKER" "command exited 0 with no heartbeat file; unloading job" ;;
esac
if [ "$outcome" = "unfinished" ] && [ "$rc" -eq 0 ]; then
  finish "$DONE_MARKER" "supervisor exited 0; unloading job"
fi

echo "$attempt" > "$RESTARTS_FILE"
if [ "$attempt" -ge "$MAX_RESTARTS" ]; then
  finish "$GAVE_UP_MARKER" "unfinished after $attempt attempts (rc=$rc); giving up. Inspect $LOG, then relaunch."
fi
echo "=== $(stamp) unfinished (rc=$rc); asking launchd to relaunch (attempt $attempt of $MAX_RESTARTS)" >> "$LOG"
exit 75
