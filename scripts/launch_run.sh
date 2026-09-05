#!/bin/bash
# Launch a supervised PolicyBench run (`policybench run`) as a launchd user
# agent so it outlives the shell, terminal, or Claude Code session that started
# it, survives a reboot, and is relaunched if it is killed before finishing.
#
#   scripts/launch_run.sh start --name NAME --model MODEL [options]
#   scripts/launch_run.sh status NAME
#   scripts/launch_run.sh logs NAME [LINES]
#   scripts/launch_run.sh stop NAME
#   scripts/launch_run.sh list
#
# `start` options (defaults in brackets):
#   --scenario-manifest PATH  [paper/snapshot/20260501/us_scenarios.csv]
#   --run-dir DIR             [results/local/launchd/NAME/run]
#   --budget-usd N            passed through; omit for no cap
#   --max-workers N           [5]
#   --max-rounds N            passed through when given
#   --repo DIR                checkout whose code runs (PYTHONPATH) [this one]
#   --policybench PATH        supervisor executable [REPO/.venv/bin/policybench,
#                             else the main clone's .venv, else `policybench`]
#   --env NAME[=VALUE]        extra environment for the job (repeatable)
#   --env-file FILE           sourced by the job at start (keeps secrets out of
#                             the plist); must not be group/world readable
#   --max-restarts N          relaunch cap after unfinished exits [5]
#   --throttle-seconds N      launchd delay before a relaunch [60]
#   --no-caffeinate           do not wrap the supervisor in `caffeinate -i`
#   --dry-run                 print the plist and the commands; change nothing
#   -- COMMAND [ARGS...]      run this instead of `policybench run` (used by
#                             scripts/check_run_survival.sh)
#
# Environment variables named *_API_KEY, *_API_TOKEN, or starting with
# ANTHROPIC_, OPENAI_, OPENROUTER_, GEMINI_, GOOGLE_, XAI_, DEEPSEEK_, LITELLM_,
# or POLICYENGINE_ are copied into the job (launchd does not inherit a shell's
# environment). The plist is written mode 600 because of that.
#
# Portable to bash 3.2 (macOS). Only `start` without --dry-run, `status`,
# `logs`, `stop`, and `list` touch launchd.
set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
DEFAULT_REPO=$(cd "$SCRIPT_DIR/.." && pwd)
LABEL_PREFIX="org.policyengine.policybench"
AGENTS_DIR="${POLICYBENCH_LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
DOMAIN="gui/$(id -u)"

usage() { sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-64}"; }
die() { echo "launch_run: $*" >&2; exit 1; }

sanitize_name() {
  printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '-'
}

xml_escape() {
  printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}

resolve_policybench() {  # $1 = repo
  local repo=$1 common
  if [ -x "$repo/.venv/bin/policybench" ]; then
    printf '%s' "$repo/.venv/bin/policybench"; return
  fi
  common=$(git -C "$repo" rev-parse --git-common-dir 2>/dev/null)
  if [ -n "$common" ]; then
    common=$(cd "$repo" && cd "$common/.." 2>/dev/null && pwd)
    if [ -n "$common" ] && [ -x "$common/.venv/bin/policybench" ]; then
      printf '%s' "$common/.venv/bin/policybench"; return
    fi
  fi
  command -v policybench 2>/dev/null || true
}

env_is_forwarded() {  # $1 = variable name
  case "$1" in
    # Endpoint overrides are never forwarded implicitly: a Claude Code session
    # exports ANTHROPIC_BASE_URL for its own proxy, which must not redirect a
    # benchmark's calls. Pass them with --env when a proxy is intended.
    *_BASE_URL|*_API_BASE|*_ENDPOINT) return 1 ;;
    *_API_KEY|*_API_TOKEN) return 0 ;;
    ANTHROPIC_*|OPENAI_*|OPENROUTER_*|GEMINI_*|GOOGLE_*|XAI_*|DEEPSEEK_*|LITELLM_*|POLICYENGINE_*) return 0 ;;
  esac
  return 1
}

cmd_start() {
  local name="" model="" manifest="" run_dir="" budget="" workers=5 rounds="" repo="$DEFAULT_REPO"
  local pb="" env_file="" max_restarts=5 throttle=60 caffeinate=1 dry_run=0
  local extra_env=""   # newline-separated NAME=VALUE
  local exec_override=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --name) name="$2"; shift 2 ;;
      --model) model="$2"; shift 2 ;;
      --scenario-manifest) manifest="$2"; shift 2 ;;
      --run-dir) run_dir="$2"; shift 2 ;;
      --budget-usd) budget="$2"; shift 2 ;;
      --max-workers) workers="$2"; shift 2 ;;
      --max-rounds) rounds="$2"; shift 2 ;;
      --repo) repo=$(cd "$2" && pwd) || die "no such repo: $2"; shift 2 ;;
      --policybench) pb="$2"; shift 2 ;;
      --env)
        if printf '%s' "$2" | grep -q '='; then
          extra_env="$extra_env$2
"
        else
          [ -n "${!2:-}" ] || die "--env $2: not set in the current environment"
          extra_env="$extra_env$2=${!2}
"
        fi
        shift 2 ;;
      --env-file) env_file="$2"; shift 2 ;;
      --max-restarts) max_restarts="$2"; shift 2 ;;
      --throttle-seconds) throttle="$2"; shift 2 ;;
      --no-caffeinate) caffeinate=0; shift ;;
      --dry-run) dry_run=1; shift ;;
      --) shift; exec_override=1; break ;;
      -h|--help) usage 0 ;;
      *) die "unknown option $1 (see --help)" ;;
    esac
  done
  [ -n "$name" ] || die "--name is required"
  name=$(sanitize_name "$name")
  local label="$LABEL_PREFIX.$name"
  local plist="$AGENTS_DIR/$label.plist"
  [ -n "$run_dir" ] || run_dir="$repo/results/local/launchd/$name/run"
  case "$run_dir" in /*) ;; *) run_dir="$(pwd)/$run_dir" ;; esac
  if [ -n "$env_file" ]; then
    [ -r "$env_file" ] || die "--env-file $env_file is not readable"
    case "$env_file" in /*) ;; *) env_file="$(pwd)/$env_file" ;; esac
    if [ "$(stat -f '%Lp' "$env_file" 2>/dev/null || stat -c '%a' "$env_file")" != "600" ]; then
      die "--env-file must be mode 600 (chmod 600 $env_file)"
    fi
  fi

  # The command launchd runs.
  local args
  if [ "$exec_override" -eq 1 ]; then
    [ $# -gt 0 ] || die "nothing after --"
    case "$1" in
      */*) [ -x "$1" ] || die "command is not executable: $1" ;;
      *) command -v "$1" >/dev/null 2>&1 || die "command not found on PATH: $1" ;;
    esac
    args=("$@")
  else
    [ -n "$model" ] || die "--model is required (or pass a command after --)"
    [ -n "$pb" ] || pb=$(resolve_policybench "$repo")
    [ -n "$pb" ] || die "cannot find a policybench executable; pass --policybench"
    [ -n "$manifest" ] || manifest="$repo/paper/snapshot/20260501/us_scenarios.csv"
    case "$manifest" in /*) ;; *) manifest="$(pwd)/$manifest" ;; esac
    [ -f "$manifest" ] || die "scenario manifest not found: $manifest"
    args=("$pb" run --model "$model" --scenario-manifest "$manifest" --run-dir "$run_dir" --max-workers "$workers")
    [ -n "$budget" ] && args+=(--budget-usd "$budget")
    [ -n "$rounds" ] && args+=(--max-rounds "$rounds")
  fi
  local wrapper="$SCRIPT_DIR/policybench_launchd_wrapper.sh"
  local program=("$wrapper" --run-dir "$run_dir" --label "$label" --max-restarts "$max_restarts")
  [ -n "$env_file" ] && program+=(--env-file "$env_file")
  [ "$caffeinate" -eq 0 ] && program+=(--no-caffeinate)
  program+=(-- "${args[@]}")

  # Environment forwarded into the job.
  local env_lines="PATH=$PATH
HOME=$HOME
PYTHONPATH=$repo
PYTHONUNBUFFERED=1
"
  local var forwarded=""
  for var in $(env | sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p' | sort -u); do
    case "$var" in PATH|HOME|PYTHONPATH|PYTHONUNBUFFERED) continue ;; esac
    if env_is_forwarded "$var"; then
      env_lines="$env_lines$var=${!var}
"
      forwarded="$forwarded $var"
    fi
  done
  env_lines="$env_lines$extra_env"

  # Render the plist.
  local xml a line k v
  xml="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
  <key>Label</key><string>$(xml_escape "$label")</string>
  <key>ProgramArguments</key>
  <array>
"
  for a in "${program[@]}"; do
    xml="$xml    <string>$(xml_escape "$a")</string>
"
  done
  xml="$xml  </array>
  <key>WorkingDirectory</key><string>$(xml_escape "$repo")</string>
  <key>EnvironmentVariables</key>
  <dict>
"
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    k=${line%%=*}; v=${line#*=}
    xml="$xml    <key>$(xml_escape "$k")</key><string>$(xml_escape "$v")</string>
"
  done <<EOF_ENV
$env_lines
EOF_ENV
  xml="$xml  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key><false/>
  </dict>
  <key>ThrottleInterval</key><integer>$throttle</integer>
  <key>ExitTimeOut</key><integer>30</integer>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$(xml_escape "$run_dir/launchd.log")</string>
  <key>StandardErrorPath</key><string>$(xml_escape "$run_dir/launchd.log")</string>
</dict>
</plist>
"

  local how="
Env:     PATH HOME PYTHONPATH PYTHONUNBUFFERED${forwarded}$(printf '%s' "$extra_env" | sed -n 's/^\([^=]*\)=.*/ \1/p' | tr -d '\n')
Check:   $0 status $name
Logs:    $0 logs $name            (supervisor.log and launchd.log live in $run_dir)
Stop:    $0 stop $name
launchd: launchctl print $DOMAIN/$label | grep -E 'state|pid'"

  if [ "$dry_run" -eq 1 ]; then
    printf '%s' "$xml"
    echo "# dry run: would write $plist and run: launchctl bootstrap $DOMAIN $plist" >&2
    printf '%s\n' "$how" | sed 's/^/# /' >&2
    return 0
  fi

  command -v launchctl >/dev/null 2>&1 || die "launchctl not found; this launcher needs macOS launchd"
  if launchctl print "$DOMAIN/$label" >/dev/null 2>&1; then
    if launchctl print "$DOMAIN/$label" 2>/dev/null | grep -qE '^[[:space:]]*pid = [0-9]+'; then
      die "$label is already running. Run '$0 status $name' or '$0 stop $name' first."
    fi
    # Loaded but idle: a finished job whose self-unload did not complete, or a
    # job that gave up. Reap it so the new run can start.
    launchctl bootout "$DOMAIN/$label" >/dev/null 2>&1 || true
    sleep 1
  fi
  mkdir -p "$AGENTS_DIR" "$run_dir" || die "cannot create $AGENTS_DIR or $run_dir"
  umask 077
  printf '%s' "$xml" > "$plist" || die "cannot write $plist"
  chmod 600 "$plist"
  if command -v plutil >/dev/null 2>&1; then
    plutil -lint -s "$plist" >/dev/null || die "generated plist does not lint: $plist"
  fi
  rm -f "$run_dir/.launchd_restarts" "$run_dir/.launchd_done" "$run_dir/.launchd_gave_up"
  launchctl bootstrap "$DOMAIN" "$plist" || die "launchctl bootstrap failed (see launchctl print $DOMAIN/$label)"
  sleep 1
  local pid
  pid=$(launchctl print "$DOMAIN/$label" 2>/dev/null | sed -n 's/^[[:space:]]*pid = \([0-9]*\).*/\1/p' | head -1)
  echo "Started $label (launchd pid ${pid:-pending}); the run is independent of this shell and session."
  echo "$how"
}

label_for() { printf '%s.%s' "$LABEL_PREFIX" "$(sanitize_name "$1")"; }

run_dir_for() {  # $1 = label; read the run dir back from the plist
  local plist="$AGENTS_DIR/$1.plist"
  [ -f "$plist" ] || return 1
  python3 - "$plist" <<'PY'
import plistlib, sys
args = plistlib.load(open(sys.argv[1], "rb"))["ProgramArguments"]
print(args[args.index("--run-dir") + 1])
PY
}

cmd_status() {
  [ $# -ge 1 ] || die "usage: $0 status NAME"
  local label run_dir
  label=$(label_for "$1")
  if launchctl print "$DOMAIN/$label" >/dev/null 2>&1; then
    echo "$label: loaded"
    launchctl print "$DOMAIN/$label" | grep -E '^[[:space:]]*(state|pid|last exit code|runs) ' | sed 's/^[[:space:]]*/  /'
  else
    echo "$label: not loaded (finished, stopped, or never started)"
  fi
  run_dir=$(run_dir_for "$label") || { echo "  no plist at $AGENTS_DIR/$label.plist"; return 0; }
  echo "  run dir: $run_dir"
  for marker in .launchd_done .launchd_gave_up .launchd_restarts; do
    [ -f "$run_dir/$marker" ] && echo "  $marker: $(cat "$run_dir/$marker")"
  done
  if [ -f "$run_dir/run_state.json" ]; then
    python3 - "$run_dir/run_state.json" <<'PY'
import datetime as dt, json, sys
s = json.load(open(sys.argv[1]))
completed = s.get("completed")
completed = len(completed) if isinstance(completed, list) else completed
upd = dt.datetime.fromtimestamp(s.get("updated_at", 0)).strftime("%Y-%m-%d %H:%M:%S")
print(f"  {s.get('model')}: {completed}/{s.get('total')} complete, ${s.get('spent_usd', 0):.2f} spent, "
      f"workers={s.get('workers')}, stopped_reason={s.get('stopped_reason')!r}, heartbeat {upd}")
PY
  fi
  [ -f "$run_dir/supervisor.log" ] && { echo "  last supervisor.log lines:"; tail -n 3 "$run_dir/supervisor.log" | sed 's/^/    /'; }
}

cmd_logs() {
  [ $# -ge 1 ] || die "usage: $0 logs NAME [LINES]"
  local label run_dir n=${2:-40}
  label=$(label_for "$1")
  run_dir=$(run_dir_for "$label") || die "no plist for $label"
  for f in supervisor.log launchd.log; do
    [ -f "$run_dir/$f" ] || continue
    echo "==> $run_dir/$f <=="
    tail -n "$n" "$run_dir/$f"
  done
}

cmd_stop() {
  [ $# -ge 1 ] || die "usage: $0 stop NAME"
  local label
  label=$(label_for "$1")
  if launchctl print "$DOMAIN/$label" >/dev/null 2>&1; then
    launchctl bootout "$DOMAIN/$label" && echo "stopped $label (launchd sent SIGTERM, then SIGKILL to the job's process group)"
  else
    echo "$label was not loaded"
  fi
  rm -f "$AGENTS_DIR/$label.plist"
}

cmd_list() {
  local p label
  for p in "$AGENTS_DIR"/$LABEL_PREFIX.*.plist; do
    [ -f "$p" ] || { echo "no PolicyBench launchd jobs in $AGENTS_DIR"; return 0; }
    label=$(basename "$p" .plist)
    if launchctl print "$DOMAIN/$label" >/dev/null 2>&1; then
      echo "$label  loaded  pid=$(launchctl print "$DOMAIN/$label" | sed -n 's/^[[:space:]]*pid = \([0-9]*\).*/\1/p' | head -1)"
    else
      echo "$label  not loaded"
    fi
  done
}

[ $# -ge 1 ] || usage 64
cmd=$1; shift
case "$cmd" in
  start) cmd_start "$@" ;;
  status) cmd_status "$@" ;;
  logs) cmd_logs "$@" ;;
  stop) cmd_stop "$@" ;;
  list) cmd_list "$@" ;;
  -h|--help|help) usage 0 ;;
  *) die "unknown command $cmd (start|status|logs|stop|list)" ;;
esac
