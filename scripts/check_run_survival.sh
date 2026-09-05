#!/bin/bash
# Live regression check (macOS only): a run started by scripts/launch_run.sh
# outlives the process group that launched it, is relaunched by launchd when
# killed before finishing, and stops cleanly. This is the reproducible stand-in
# for "restart the Claude Code session and see whether the supervisor is still
# there": a session teardown, a terminal closing, and a stray `kill -9` are all
# signals aimed at a process group or a pid, and that is exactly what this
# script sends.
#
#   scripts/check_run_survival.sh            # prints PASS or FAIL, exit 0/1
#
# It launches `/bin/sleep 3600` through the launcher (no model calls, no spend),
# next to a plain `nohup sleep & disown` control launched from the same
# throwaway shell, then:
#   1. SIGTERMs and SIGKILLs that shell's whole process group. The control dies;
#      the launchd job must survive (it lives in launchd's session, not ours).
#   2. SIGKILLs the job's sleep. launchd must relaunch it (KeepAlive on an
#      unfinished exit; --throttle-seconds 5 keeps the wait short).
#   3. Stops the job through the launcher and checks that nothing is left.
set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
LAUNCHER="$SCRIPT_DIR/launch_run.sh"
NAME="survival-check-$$"
LABEL="org.policyengine.policybench.$NAME"
DOMAIN="gui/$(id -u)"
WORK=$(mktemp -d "${TMPDIR:-/tmp}/pb-survival.XXXXXX")
RUN_DIR="$WORK/run"
fail=0

command -v launchctl >/dev/null 2>&1 || { echo "SKIP: launchctl not found (macOS only)"; exit 0; }

say() { printf '%s\n' "$*"; }
check() {  # $1 = description, $2 = 0/1 (1 = ok)
  if [ "$2" -eq 1 ]; then say "  ok   $1"; else say "  FAIL $1"; fail=1; fi
}
job_pid() {
  launchctl print "$DOMAIN/$LABEL" 2>/dev/null | sed -n 's/^[[:space:]]*pid = \([0-9]*\).*/\1/p' | head -1
}
sleep_pid_under() {  # $1 = wrapper pid -> pid of the /bin/sleep it runs
  pgrep -P "$1" -x sleep 2>/dev/null | head -1
}
cleanup() {
  "$LAUNCHER" stop "$NAME" >/dev/null 2>&1
  pkill -f "^pb-survival-control-$$" 2>/dev/null
  rm -rf "$WORK"
}
trap cleanup EXIT

say "1. launching a dummy run and a nohup control from a throwaway process group"
# A python-spawned bash in its own session stands in for the shell a Claude Code
# Bash tool call (or a terminal tab) would use.
launcher_shell_pgid=$(python3 - "$LAUNCHER" "$NAME" "$RUN_DIR" "$$" <<'PY'
import subprocess, sys
launcher, name, run_dir, tag = sys.argv[1:]
script = f"""
"{launcher}" start --name "{name}" --run-dir "{run_dir}" --throttle-seconds 5 --no-caffeinate -- /bin/sleep 3600 >"{run_dir}.start.log" 2>&1
nohup bash -c 'exec -a pb-survival-control-{tag} /bin/sleep 3601' >/dev/null 2>&1 & disown
sleep 3
"""
p = subprocess.Popen(["bash", "-c", script], start_new_session=True)
print(p.pid)  # session leader: pid == pgid
p.wait()
PY
)
sleep 1
control_pid=$(pgrep -f "^pb-survival-control-$$" | head -1)
wrapper_pid=$(job_pid)
check "launchd job $LABEL is running (pid ${wrapper_pid:-none})" "$([ -n "$wrapper_pid" ] && echo 1 || echo 0)"
check "nohup control sleep is running (pid ${control_pid:-none})" "$([ -n "$control_pid" ] && echo 1 || echo 0)"
if [ -n "$wrapper_pid" ]; then
  wrapper_pgid=$(ps -o pgid= -p "$wrapper_pid" | tr -d ' ')
  wrapper_ppid=$(ps -o ppid= -p "$wrapper_pid" | tr -d ' ')
  check "job runs under launchd (ppid $wrapper_ppid) in its own process group ($wrapper_pgid, launcher shell was $launcher_shell_pgid)" \
    "$([ "$wrapper_ppid" = "1" ] && [ "$wrapper_pgid" != "$launcher_shell_pgid" ] && echo 1 || echo 0)"
fi

say "2. killing the launcher shell's whole process group (SIGTERM, then SIGKILL)"
kill -TERM -- "-$launcher_shell_pgid" 2>/dev/null
sleep 1
kill -KILL -- "-$launcher_shell_pgid" 2>/dev/null
sleep 2
check "nohup control died with its process group" "$([ -n "$control_pid" ] && ! kill -0 "$control_pid" 2>/dev/null && echo 1 || echo 0)"
check "launchd job survived the group kill" "$([ -n "$wrapper_pid" ] && kill -0 "$wrapper_pid" 2>/dev/null && echo 1 || echo 0)"

say "3. SIGKILLing the job's sleep; launchd should relaunch it within ~5s"
sleep_pid=$(sleep_pid_under "$wrapper_pid")
[ -n "$sleep_pid" ] && kill -KILL "$sleep_pid"
new_pid=""
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  sleep 1
  new_pid=$(job_pid)
  [ -n "$new_pid" ] && [ "$new_pid" != "$wrapper_pid" ] && break
done
check "launchd relaunched the job (new wrapper pid ${new_pid:-none}, old $wrapper_pid)" \
  "$([ -n "$new_pid" ] && [ "$new_pid" != "$wrapper_pid" ] && echo 1 || echo 0)"
check "wrapper recorded the unfinished exit in $RUN_DIR/.launchd_restarts" \
  "$([ "$(cat "$RUN_DIR/.launchd_restarts" 2>/dev/null)" = "1" ] && echo 1 || echo 0)"

say "4. stopping through the launcher"
"$LAUNCHER" stop "$NAME" >/dev/null 2>&1
sleep 2
check "job unloaded" "$(launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1 && echo 0 || echo 1)"
check "no sleep left from the job" "$([ -z "$(pgrep -f "^/bin/sleep 3600$")" ] && echo 1 || echo 0)"
check "plist removed" "$([ ! -f "$HOME/Library/LaunchAgents/$LABEL.plist" ] && echo 1 || echo 0)"

if [ "$fail" -eq 0 ]; then say "PASS: launchd-launched runs survive the launching process group and are relaunched when killed"; else say "FAIL: see the lines above; logs in $RUN_DIR (kept)"; trap - EXIT; "$LAUNCHER" stop "$NAME" >/dev/null 2>&1; fi
exit "$fail"
