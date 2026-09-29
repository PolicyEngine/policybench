"""The launcher retains private diagnostics across every terminal transition.

Invariants: a successful start binds its name to its absolute run directory;
completion, retry exhaustion, and stop preserve that binding and its artifacts;
reuse replaces only the binding, while a refused start changes nothing. The
retained record contains no environment or command information. All launchctl
calls go to a local fake, so these tests never load a real launchd job.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

REPO = Path(__file__).resolve().parents[1]
LAUNCHER = REPO / "scripts" / "launch_run.sh"
LABEL_PREFIX = "org.policyengine.policybench"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None, reason="launcher scripts need bash"
)


def _label(name: str) -> str:
    return f"{LABEL_PREFIX}.{re.sub(r'[^A-Za-z0-9._-]', '-', name)}"


def _environment(root: Path) -> dict[str, str]:
    """Install a fake launchctl that can run wrappers or emulate live jobs."""
    root.mkdir(parents=True, exist_ok=True)
    binaries = root / "bin"
    binaries.mkdir()
    fake = binaries / "launchctl"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, plistlib, subprocess, sys\n"
        "root = pathlib.Path(os.environ['TEST_LAUNCHCTL_STATE'])\n"
        "root.mkdir(parents=True, exist_ok=True)\n"
        "action = sys.argv[1]\n"
        "if action == 'bootstrap':\n"
        "    with open(sys.argv[3], 'rb') as f:\n"
        "        job = plistlib.load(f)\n"
        "    state = root / job['Label']\n"
        "    mode = os.environ.get('TEST_BOOTSTRAP_MODE', 'idle')\n"
        "    if mode == 'fail':\n"
        "        sys.exit(5)\n"
        "    state.write_text(mode)\n"
        "    if mode == 'run':\n"
        "        env = os.environ.copy()\n"
        "        env.update(job['EnvironmentVariables'])\n"
        "        pathlib.Path(job['StandardOutPath']).write_text('launchd output\\n')\n"
        "        for _ in range(int(os.environ.get('TEST_BOOTSTRAP_ATTEMPTS', '1'))):\n"
        "            result = subprocess.run(job['ProgramArguments'], env=env,\n"
        "                                    cwd=job['WorkingDirectory'])\n"
        "            if result.returncode != 75:\n"
        "                break\n"
        "    sys.exit(0)\n"
        "state = root / sys.argv[2].rsplit('/', 1)[-1]\n"
        "if action == 'print':\n"
        "    if not state.exists():\n"
        "        sys.exit(1)\n"
        "    print('    state = running')\n"
        "    if state.read_text() == 'active':\n"
        "        print('    pid = 12345')\n"
        "elif action == 'bootout':\n"
        "    state.unlink(missing_ok=True)\n"
        "else:\n"
        "    sys.exit(64)\n"
    )
    fake.chmod(0o755)
    # The launcher waits only for launchd state changes, which this fake applies
    # synchronously. Removing those delays keeps generated lifecycle cases fast.
    (binaries / "sleep").write_text("#!/bin/bash\nexit 0\n")
    (binaries / "sleep").chmod(0o755)
    return {
        "PATH": f"{binaries}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(root / "home"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "POLICYBENCH_LAUNCH_AGENTS_DIR": str(root / "custom agents"),
        "POLICYBENCH_LAUNCH_STATE_DIR": str(root / "retained state"),
        "TEST_LAUNCHCTL_STATE": str(root / "fake launchd"),
    }


def _run(env: dict[str, str], *args: str, cwd: Path | None = None):
    return subprocess.run(
        ["bash", str(LAUNCHER), *args],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _start(
    env: dict[str, str],
    name: str,
    run_dir: Path,
    *,
    outcome: str = "complete",
    cwd: Path | None = None,
    dry_run: bool = False,
):
    state = {
        "model": "test-model",
        "completed": 1 if outcome == "complete" else 0,
        "total": 1,
        "updated_at": 1_700_000_000,
        "stopped_reason": None,
    }
    command = (
        "import pathlib,sys; "
        "p=pathlib.Path(sys.argv[1]); "
        "(p/'run_state.json').write_text(sys.argv[2]); "
        "print('supervisor output for ' + str(p)); "
        "sys.exit(int(sys.argv[3]))"
    )
    return _run(
        env,
        "start",
        "--name",
        name,
        "--run-dir",
        str(run_dir),
        "--no-caffeinate",
        "--max-restarts",
        "3",
        *(["--dry-run"] if dry_run else []),
        "--",
        sys.executable,
        "-c",
        command,
        str(run_dir),
        json.dumps(state),
        "0" if outcome == "complete" else "1",
        cwd=cwd,
    )


def _record(env: dict[str, str], name: str) -> Path:
    return Path(env["POLICYBENCH_LAUNCH_STATE_DIR"]) / f"{_label(name)}.run-dir"


def _assert_diagnostics(env: dict[str, str], name: str, run_dir: Path):
    assert _record(env, name).read_text() == f"{run_dir}\n"
    status = _run(env, "status", name)
    assert status.returncode == 0, status.stderr
    assert f"run dir: {run_dir}" in status.stdout
    logs = _run(env, "logs", name)
    assert logs.returncode == 0, logs.stderr
    assert f"supervisor output for {run_dir}" in logs.stdout
    return status, logs


@pytest.mark.parametrize(
    ("outcome", "attempts", "marker"),
    [("complete", 1, ".launchd_done"), ("unfinished", 3, ".launchd_gave_up")],
)
def test_diagnostics_survive_terminal_cleanup(
    tmp_path: Path, outcome: str, attempts: int, marker: str
):
    env = _environment(tmp_path)
    env.update(TEST_BOOTSTRAP_MODE="run", TEST_BOOTSTRAP_ATTEMPTS=str(attempts))
    run_dir = tmp_path / "run with spaces & symbols"
    name = "terminal run"
    result = _start(env, name, run_dir, outcome=outcome)
    assert result.returncode == 0, result.stderr
    assert not (
        Path(env["POLICYBENCH_LAUNCH_AGENTS_DIR"]) / f"{_label(name)}.plist"
    ).exists()
    assert not (Path(env["TEST_LAUNCHCTL_STATE"]) / _label(name)).exists()
    assert (run_dir / marker).exists()
    status, logs = _assert_diagnostics(env, name, run_dir)
    assert marker in status.stdout
    assert "heartbeat" in status.stdout
    assert "launchd output" in logs.stdout


def test_stop_retains_diagnostics_and_only_removes_configured_plist(tmp_path: Path):
    env = _environment(tmp_path)
    env["TEST_BOOTSTRAP_MODE"] = "run"
    name = "stop-test"
    run_dir = tmp_path / "run"
    result = _start(env, name, run_dir, outcome="unfinished")
    assert result.returncode == 0, result.stderr
    home_plist = (
        Path(env["HOME"]) / "Library" / "LaunchAgents" / f"{_label(name)}.plist"
    )
    home_plist.parent.mkdir(parents=True)
    home_plist.write_text("unrelated default-directory artifact")
    stopped = _run(env, "stop", name)
    assert stopped.returncode == 0, stopped.stderr
    assert not (
        Path(env["POLICYBENCH_LAUNCH_AGENTS_DIR"]) / f"{_label(name)}.plist"
    ).exists()
    assert home_plist.read_text() == "unrelated default-directory artifact"
    _assert_diagnostics(env, name, run_dir)


def test_relative_agent_directory_is_resolved_before_wrapper_changes_cwd(
    tmp_path: Path,
):
    env = _environment(tmp_path)
    env.update(
        POLICYBENCH_LAUNCH_AGENTS_DIR="relative agents", TEST_BOOTSTRAP_MODE="run"
    )
    run_dir = tmp_path / "run"
    result = _start(env, "relative", run_dir, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "relative agents" / f"{_label('relative')}.plist").exists()
    _assert_diagnostics(env, "relative", run_dir)


def test_retained_record_is_private_and_contains_only_run_directory(tmp_path: Path):
    env = _environment(tmp_path)
    env.update(OPENAI_API_KEY="sk-do-not-retain", TEST_BOOTSTRAP_MODE="run")
    run_dir = tmp_path / "run"
    result = _start(env, "private", run_dir)
    assert result.returncode == 0, result.stderr
    record = _record(env, "private")
    assert record.read_text() == f"{run_dir}\n"
    assert stat.S_IMODE(record.stat().st_mode) == 0o600
    assert stat.S_IMODE(record.parent.stat().st_mode) == 0o700
    assert list(record.parent.iterdir()) == [record]


def test_default_state_directory_is_outside_launch_agents(tmp_path: Path):
    env = _environment(tmp_path)
    env.pop("POLICYBENCH_LAUNCH_STATE_DIR")
    env["TEST_BOOTSTRAP_MODE"] = "run"
    run_dir = tmp_path / "run"
    result = _start(env, "default-state", run_dir)
    assert result.returncode == 0, result.stderr
    record = (
        Path(env["HOME"])
        / "Library"
        / "Application Support"
        / "PolicyBench"
        / "launchd"
        / f"{_label('default-state')}.run-dir"
    )
    assert record.read_text() == f"{run_dir}\n"
    assert stat.S_IMODE(record.parent.stat().st_mode) == 0o700
    assert _run(env, "logs", "default-state").returncode == 0


@pytest.mark.parametrize("first_outcome", ["complete", "unfinished", "stop"])
def test_name_reuse_points_to_new_run_and_preserves_old_artifacts(
    tmp_path: Path, first_outcome: str
):
    env = _environment(tmp_path)
    env.update(
        TEST_BOOTSTRAP_MODE="run",
        TEST_BOOTSTRAP_ATTEMPTS="1" if first_outcome == "stop" else "3",
    )
    old_dir = tmp_path / "old run"
    result = _start(env, "reused", old_dir, outcome=first_outcome)
    assert result.returncode == 0, result.stderr
    if first_outcome == "stop":
        assert _run(env, "stop", "reused").returncode == 0
    old_artifacts = {p.name: p.read_bytes() for p in old_dir.iterdir()}
    new_dir = tmp_path / "new run"
    result = _start(env, "reused", new_dir)
    assert result.returncode == 0, result.stderr
    _assert_diagnostics(env, "reused", new_dir)
    assert {p.name: p.read_bytes() for p in old_dir.iterdir()} == old_artifacts


def test_active_name_refusal_preserves_record_and_does_not_create_new_run(
    tmp_path: Path,
):
    env = _environment(tmp_path)
    env["TEST_BOOTSTRAP_MODE"] = "active"
    old_dir = tmp_path / "active run"
    first = _start(env, "active", old_dir)
    assert first.returncode == 0, first.stderr
    record = _record(env, "active")
    previous_record = record.read_bytes()
    previous_plist = (
        Path(env["POLICYBENCH_LAUNCH_AGENTS_DIR"]) / f"{_label('active')}.plist"
    ).read_bytes()
    new_dir = tmp_path / "rejected run"
    refused = _start(env, "active", new_dir)
    assert refused.returncode != 0
    assert "already running" in refused.stderr
    assert record.read_bytes() == previous_record
    assert (
        Path(env["POLICYBENCH_LAUNCH_AGENTS_DIR"]) / f"{_label('active')}.plist"
    ).read_bytes() == previous_plist
    assert not new_dir.exists()
    assert _run(env, "status", "active").returncode == 0


def test_dry_run_does_not_write_retained_record(tmp_path: Path):
    env = _environment(tmp_path)
    result = _start(env, "dry", tmp_path / "run", dry_run=True)
    assert result.returncode == 0, result.stderr
    plist = plistlib.loads(result.stdout.encode())
    args = plist["ProgramArguments"]
    assert args[args.index("--agents-dir") + 1] == env["POLICYBENCH_LAUNCH_AGENTS_DIR"]
    assert not Path(env["POLICYBENCH_LAUNCH_STATE_DIR"]).exists()
    assert not Path(env["POLICYBENCH_LAUNCH_AGENTS_DIR"]).exists()
    assert not (tmp_path / "run").exists()


def test_existing_plist_remains_a_diagnostics_fallback(tmp_path: Path):
    env = _environment(tmp_path)
    env["TEST_BOOTSTRAP_MODE"] = "run"
    run_dir = tmp_path / "legacy run"
    result = _start(env, "legacy", run_dir, outcome="unfinished")
    assert result.returncode == 0, result.stderr
    _record(env, "legacy").unlink()
    status = _run(env, "status", "legacy")
    logs = _run(env, "logs", "legacy")
    assert status.returncode == 0, status.stderr
    assert str(run_dir) in status.stdout
    assert logs.returncode == 0, logs.stderr
    assert f"supervisor output for {run_dir}" in logs.stdout
    stopped = _run(env, "stop", "legacy")
    assert stopped.returncode == 0, stopped.stderr
    assert not (
        Path(env["POLICYBENCH_LAUNCH_AGENTS_DIR"]) / f"{_label('legacy')}.plist"
    ).exists()
    _assert_diagnostics(env, "legacy", run_dir)


def test_failed_bootstrap_does_not_leave_record_or_autoload_plist(tmp_path: Path):
    env = _environment(tmp_path)
    env["TEST_BOOTSTRAP_MODE"] = "fail"
    result = _start(env, "failed", tmp_path / "failed run")
    assert result.returncode != 0
    assert "bootstrap failed" in result.stderr
    assert not _record(env, "failed").exists()
    assert not (
        Path(env["POLICYBENCH_LAUNCH_AGENTS_DIR"]) / f"{_label('failed')}.plist"
    ).exists()


@pytest.mark.parametrize("legacy", [False, True])
def test_failed_bootstrap_with_reused_name_restores_previous_diagnostics(
    tmp_path: Path, legacy: bool
):
    env = _environment(tmp_path)
    env["TEST_BOOTSTRAP_MODE"] = "run"
    previous_dir = tmp_path / "previous run"
    result = _start(
        env,
        "reused-failure",
        previous_dir,
        outcome="unfinished" if legacy else "complete",
    )
    assert result.returncode == 0, result.stderr
    previous_record = _record(env, "reused-failure").read_bytes()
    if legacy:
        _record(env, "reused-failure").unlink()
    env["TEST_BOOTSTRAP_MODE"] = "fail"
    result = _start(env, "reused-failure", tmp_path / "failed run")
    assert result.returncode != 0
    assert "bootstrap failed" in result.stderr
    assert _record(env, "reused-failure").read_bytes() == previous_record
    _assert_diagnostics(env, "reused-failure", previous_dir)


def test_metadata_write_failure_removes_new_autoload_plist(tmp_path: Path):
    env = _environment(tmp_path)
    state_path = Path(env["POLICYBENCH_LAUNCH_STATE_DIR"])
    state_path.write_text("existing file must be preserved")
    result = _start(env, "metadata-failure", tmp_path / "run")
    assert result.returncode != 0
    assert "cannot save run directory" in result.stderr
    assert state_path.read_text() == "existing file must be preserved"
    assert not (
        Path(env["POLICYBENCH_LAUNCH_AGENTS_DIR"])
        / f"{_label('metadata-failure')}.plist"
    ).exists()
    assert not (Path(env["TEST_LAUNCHCTL_STATE"]) / _label("metadata-failure")).exists()


@pytest.mark.parametrize("outcome", ["complete", "unfinished"])
def test_failed_bootstrap_in_same_directory_preserves_terminal_diagnostics(
    tmp_path: Path, outcome: str
):
    env = _environment(tmp_path)
    env.update(TEST_BOOTSTRAP_MODE="run", TEST_BOOTSTRAP_ATTEMPTS="3")
    run_dir = tmp_path / "reused run"
    assert _start(env, "same-directory", run_dir, outcome=outcome).returncode == 0
    artifacts = {p.name: p.read_bytes() for p in run_dir.iterdir()}
    env["TEST_BOOTSTRAP_MODE"] = "fail"
    failed = _start(env, "same-directory", run_dir)
    assert failed.returncode != 0
    assert "bootstrap failed" in failed.stderr
    assert {p.name: p.read_bytes() for p in run_dir.iterdir()} == artifacts
    status, _ = _assert_diagnostics(env, "same-directory", run_dir)
    marker = ".launchd_done" if outcome == "complete" else ".launchd_gave_up"
    assert marker in status.stdout


def test_retained_record_takes_precedence_over_plist(tmp_path: Path):
    env = _environment(tmp_path)
    env["TEST_BOOTSTRAP_MODE"] = "run"
    run_dir = tmp_path / "current run"
    result = _start(env, "precedence", run_dir, outcome="unfinished")
    assert result.returncode == 0, result.stderr
    plist_path = (
        Path(env["POLICYBENCH_LAUNCH_AGENTS_DIR"]) / f"{_label('precedence')}.plist"
    )
    plist = plistlib.loads(plist_path.read_bytes())
    args = plist["ProgramArguments"]
    args[args.index("--run-dir") + 1] = str(tmp_path / "stale run")
    plist_path.write_bytes(plistlib.dumps(plist))
    _assert_diagnostics(env, "precedence", run_dir)


_names = st.text(alphabet="abcXYZ019 ._-&/", min_size=1, max_size=15)
_path_parts = st.text(alphabet="abcXYZ019 ._-&<é", min_size=1, max_size=15)


@settings(max_examples=12, deadline=None, database=None)
@given(
    name=_names,
    runs=st.lists(
        st.tuples(_path_parts, st.sampled_from(["complete", "unfinished", "stop"])),
        min_size=2,
        max_size=4,
    ),
)
def test_generated_lifecycles_keep_latest_binding_and_all_historical_artifacts(
    name: str, runs: list[tuple[str, str]]
):
    with TemporaryDirectory(prefix="policybench-lifecycle-") as temporary:
        root = Path(temporary)
        env = _environment(root)
        env["TEST_BOOTSTRAP_MODE"] = "run"
        history: dict[Path, dict[str, bytes]] = {}
        for index, (path_part, outcome) in enumerate(runs):
            run_dir = root / f"run-{index}-{path_part}"
            env["TEST_BOOTSTRAP_ATTEMPTS"] = "1" if outcome == "stop" else "3"
            result = _start(env, name, run_dir, outcome=outcome)
            assert result.returncode == 0, result.stderr
            if outcome == "stop":
                stopped = _run(env, "stop", name)
                assert stopped.returncode == 0, stopped.stderr
            status, _ = _assert_diagnostics(env, name, run_dir)
            record = _record(env, name)
            assert stat.S_IMODE(record.stat().st_mode) == 0o600
            assert stat.S_IMODE(record.parent.stat().st_mode) == 0o700
            assert not (
                Path(env["POLICYBENCH_LAUNCH_AGENTS_DIR"]) / f"{_label(name)}.plist"
            ).exists()
            marker = {
                "complete": ".launchd_done",
                "unfinished": ".launchd_gave_up",
                "stop": ".launchd_restarts",
            }[outcome]
            assert marker in status.stdout
            artifacts = {p.name: p.read_bytes() for p in run_dir.iterdir()}
            env["TEST_BOOTSTRAP_MODE"] = "fail"
            failed = _start(env, name, run_dir)
            assert failed.returncode != 0
            assert "bootstrap failed" in failed.stderr
            assert {p.name: p.read_bytes() for p in run_dir.iterdir()} == artifacts
            _assert_diagnostics(env, name, run_dir)
            env["TEST_BOOTSTRAP_MODE"] = "run"
            for old_dir, artifacts in history.items():
                assert {p.name: p.read_bytes() for p in old_dir.iterdir()} == artifacts
            history[run_dir] = {p.name: p.read_bytes() for p in run_dir.iterdir()}
