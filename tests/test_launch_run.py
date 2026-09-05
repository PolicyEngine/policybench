"""Tests for scripts/launch_run.sh and scripts/policybench_launchd_wrapper.sh.

Nothing here touches launchd: the launcher is exercised with --dry-run (it
prints the plist it would install) and the wrapper with a stub supervisor
that writes run_state.json. See scripts/check_run_survival.sh for the live
macOS check that a launched job outlives the process group that started it.
"""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "scripts" / "launch_run.sh"
WRAPPER = REPO / "scripts" / "policybench_launchd_wrapper.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None, reason="launcher scripts need bash"
)


def _run(args: list[str], env: dict[str, str] | None = None, cwd: Path | None = None):
    return subprocess.run(
        ["bash", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        check=False,
    )


def _clean_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path / "home"),
        "POLICYBENCH_LAUNCH_AGENTS_DIR": str(tmp_path / "agents"),
    }
    env.update(extra)
    return env


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    path = tmp_path / "scenarios.csv"
    path.write_text("scenario_id,scenario_json\nscenario_000,{}\n")
    return path


def _dry_run(tmp_path: Path, manifest: Path, *extra: str, env: dict | None = None):
    result = _run(
        [
            str(LAUNCHER),
            "start",
            "--name",
            "Unit Test/run",
            "--model",
            "glm-5.3",
            "--scenario-manifest",
            str(manifest),
            "--run-dir",
            str(tmp_path / "run"),
            "--budget-usd",
            "12.5",
            "--max-workers",
            "3",
            "--policybench",
            "/bin/echo",
            "--dry-run",
            *extra,
        ],
        env=env or _clean_env(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    return plistlib.loads(result.stdout.encode()), result.stderr


def test_dry_run_renders_a_valid_launchd_plist(tmp_path: Path, manifest: Path):
    plist, stderr = _dry_run(tmp_path, manifest)
    assert plist["Label"] == "org.policyengine.policybench.Unit-Test-run"
    args = plist["ProgramArguments"]
    assert args[0] == str(WRAPPER)
    assert args[args.index("--run-dir") + 1] == str(tmp_path / "run")
    assert args[args.index("--label") + 1] == plist["Label"]
    command = args[args.index("--") + 1 :]
    assert command[:3] == ["/bin/echo", "run", "--model"]
    assert command[3] == "glm-5.3"
    assert command[command.index("--scenario-manifest") + 1] == str(manifest)
    assert command[command.index("--budget-usd") + 1] == "12.5"
    assert command[command.index("--max-workers") + 1] == "3"
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] == {"SuccessfulExit": False}
    assert plist["ThrottleInterval"] == 60
    assert plist["WorkingDirectory"] == str(REPO)
    assert plist["EnvironmentVariables"]["PYTHONPATH"] == str(REPO)
    assert plist["EnvironmentVariables"]["PYTHONUNBUFFERED"] == "1"
    assert plist["StandardOutPath"] == str(tmp_path / "run" / "launchd.log")
    assert "launchctl bootstrap" in stderr
    assert "status Unit-Test-run" in stderr
    assert not (tmp_path / "agents").exists(), "dry run must not write a plist"


def test_dry_run_forwards_only_provider_credentials(tmp_path: Path, manifest: Path):
    env = _clean_env(
        tmp_path,
        OPENAI_API_KEY="sk-test",
        OPENROUTER_API_KEY="or-test",
        LITELLM_LOG="DEBUG",
        UNRELATED_SECRET="nope",
        AWS_SECRET_ACCESS_KEY="also-nope",
        ANTHROPIC_BASE_URL="http://127.0.0.1:1/session-proxy",
        OPENAI_API_BASE="http://127.0.0.1:2",
    )
    plist, _ = _dry_run(
        tmp_path, manifest, "--env", "EXTRA_FLAG=1", "--env", "LITELLM_LOG", env=env
    )
    forwarded = plist["EnvironmentVariables"]
    assert forwarded["OPENAI_API_KEY"] == "sk-test"
    assert forwarded["OPENROUTER_API_KEY"] == "or-test"
    assert forwarded["LITELLM_LOG"] == "DEBUG"
    assert forwarded["EXTRA_FLAG"] == "1"
    assert "UNRELATED_SECRET" not in forwarded
    assert "AWS_SECRET_ACCESS_KEY" not in forwarded
    # Endpoint overrides ride along only when asked for with --env.
    assert "ANTHROPIC_BASE_URL" not in forwarded
    assert "OPENAI_API_BASE" not in forwarded


def test_dry_run_accepts_a_command_override(tmp_path: Path, manifest: Path):
    plist, _ = _dry_run(
        tmp_path,
        manifest,
        "--throttle-seconds",
        "5",
        "--no-caffeinate",
        "--",
        "/bin/sleep",
        "30",
    )
    args = plist["ProgramArguments"]
    assert args[args.index("--") + 1 :] == ["/bin/sleep", "30"]
    assert "--no-caffeinate" in args[: args.index("--")]
    assert plist["ThrottleInterval"] == 5


def test_start_requires_a_model_or_a_command(tmp_path: Path):
    result = _run(
        [str(LAUNCHER), "start", "--name", "x", "--dry-run"], env=_clean_env(tmp_path)
    )
    assert result.returncode == 1
    assert "--model is required" in result.stderr


def test_env_file_must_be_private(tmp_path: Path, manifest: Path):
    env_file = tmp_path / "secrets.env"
    env_file.write_text("OPENAI_API_KEY=sk\n")
    env_file.chmod(0o644)
    result = _run(
        [
            str(LAUNCHER),
            "start",
            "--name",
            "x",
            "--dry-run",
            "--env-file",
            str(env_file),
            "--",
            "/bin/true",
        ],
        env=_clean_env(tmp_path),
    )
    assert result.returncode == 1
    assert "mode 600" in result.stderr


# -- wrapper -----------------------------------------------------------------


def _stub_supervisor(tmp_path: Path) -> Path:
    """A fake `policybench run` driven by environment variables.

    STUB_STATE: JSON written to <run dir>/run_state.json ("" writes nothing).
    STUB_RC:    exit code.
    """
    stub = tmp_path / "policybench"
    stub.write_text(
        "#!/bin/bash\n"
        'run_dir="$1"\n'
        'mkdir -p "$run_dir"\n'
        'echo "stub supervisor ran with: $*"\n'
        '[ -n "${STUB_STATE:-}" ] && printf "%s" "$STUB_STATE" '
        '> "$run_dir/run_state.json"\n'
        'exit "${STUB_RC:-0}"\n'
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    return stub


def _wrapper(tmp_path: Path, run_dir: Path, state: dict | None, rc: int, *extra: str):
    stub = _stub_supervisor(tmp_path)
    env = _clean_env(tmp_path, STUB_RC=str(rc))
    env["STUB_STATE"] = json.dumps(state) if state is not None else ""
    return _run(
        [
            str(WRAPPER),
            "--run-dir",
            str(run_dir),
            "--no-caffeinate",
            "--max-restarts",
            "3",
            *extra,
            "--",
            str(stub),
            str(run_dir),
        ],
        env=env,
    )


def test_wrapper_exits_zero_when_every_scenario_is_complete(tmp_path: Path):
    run_dir = tmp_path / "run"
    result = _wrapper(
        tmp_path, run_dir, {"completed": 100, "total": 100, "stopped_reason": None}, 0
    )
    assert result.returncode == 0, result.stderr
    assert (run_dir / ".launchd_done").exists()
    assert not (run_dir / ".launchd_restarts").exists()
    log = (run_dir / "supervisor.log").read_text()
    assert "stub supervisor ran with" in log
    assert "run finished" in log


def test_wrapper_treats_a_recorded_stop_as_finished_despite_exit_1(tmp_path: Path):
    run_dir = tmp_path / "run"
    state = {
        "completed": ["scenario_000"],
        "total": 100,
        "stopped_reason": "budget: spent $36.00 of $40.00 (stop at 90%)",
    }
    result = _wrapper(tmp_path, run_dir, state, 1)
    assert result.returncode == 0, result.stderr
    assert (run_dir / ".launchd_done").exists()


def test_wrapper_asks_for_a_relaunch_after_an_unfinished_death(tmp_path: Path):
    run_dir = tmp_path / "run"
    state = {"completed": ["scenario_000"], "total": 100, "stopped_reason": None}
    result = _wrapper(tmp_path, run_dir, state, 137)  # SIGKILL
    assert result.returncode == 75, result.stderr
    assert (run_dir / ".launchd_restarts").read_text().strip() == "1"
    assert not (run_dir / ".launchd_done").exists()
    assert (
        "asking launchd to relaunch (attempt 1 of 3)"
        in (run_dir / "supervisor.log").read_text()
    )


def test_wrapper_gives_up_after_max_restarts(tmp_path: Path):
    run_dir = tmp_path / "run"
    state = {"completed": [], "total": 100, "stopped_reason": None}
    codes = [_wrapper(tmp_path, run_dir, state, 1).returncode for _ in range(3)]
    assert codes == [75, 75, 0]
    assert (run_dir / ".launchd_gave_up").exists()
    assert not (run_dir / ".launchd_restarts").exists()
    assert "giving up" in (run_dir / "supervisor.log").read_text()


def test_wrapper_gives_up_at_once_when_the_command_cannot_start(tmp_path: Path):
    run_dir = tmp_path / "run"
    env = _clean_env(tmp_path)
    result = _run(
        [
            str(WRAPPER),
            "--run-dir",
            str(run_dir),
            "--no-caffeinate",
            "--",
            str(tmp_path / "missing-supervisor"),
        ],
        env=env,
    )
    assert result.returncode == 0
    assert (run_dir / ".launchd_gave_up").exists()
    assert "could not be executed (rc=127)" in (run_dir / "supervisor.log").read_text()


def test_dry_run_rejects_a_missing_command(tmp_path: Path):
    result = _run(
        [str(LAUNCHER), "start", "--name", "x", "--dry-run", "--", "/bin/no-such-tool"],
        env=_clean_env(tmp_path),
    )
    assert result.returncode == 1
    assert "not executable" in result.stderr


def test_wrapper_without_a_heartbeat_follows_the_exit_code(tmp_path: Path):
    run_dir = tmp_path / "run"
    assert _wrapper(tmp_path, run_dir, None, 0).returncode == 0
    assert (run_dir / ".launchd_done").exists()
    run_dir2 = tmp_path / "run2"
    assert _wrapper(tmp_path, run_dir2, None, 9).returncode == 75


def test_wrapper_sources_the_env_file(tmp_path: Path):
    run_dir = tmp_path / "run"
    env_file = tmp_path / "secrets.env"
    env_file.write_text("STUB_RC=0\nSTUB_STATE=\n")
    stub = _stub_supervisor(tmp_path)
    env = _clean_env(tmp_path, STUB_RC="7")  # the env file must override this
    result = _run(
        [
            str(WRAPPER),
            "--run-dir",
            str(run_dir),
            "--no-caffeinate",
            "--env-file",
            str(env_file),
            "--",
            str(stub),
            str(run_dir),
        ],
        env=env,
    )
    assert result.returncode == 0, result.stderr
