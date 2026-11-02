"""reference_audit/2026-10-09-engine-upgrade/scripts/sweep_timing.py: the
October 2026 engine move's timing record and publication check, on MOCK PyPI
data."""

import importlib.util
import json
import math
import time
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "sweep_timing",
    REPO / "reference_audit/2026-10-09-engine-upgrade/scripts/sweep_timing.py",
)
timing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(timing)

# Linux's stat keeps no birth time, and the record's times are birth times.
BIRTH_TIMES = hasattr(Path(__file__).stat(), "st_birthtime")
REAL_BIRTH_TIME = timing.birth_time


@pytest.fixture(autouse=True)
def _birth_times(monkeypatch):
    """MOCK, on a platform without birth times (Linux CI) only: date each file
    by its modification time. These tests create every file they date once and
    never rewrite it, so the two times agree; on macOS the real birth times
    are read."""
    if not BIRTH_TIMES:
        monkeypatch.setattr(timing, "birth_time", lambda path: path.stat().st_mtime)


def test_birth_time_refuses_a_platform_without_birth_times(tmp_path):
    """Where stat keeps no birth time, the record refuses rather than date the
    install or an output by a modification time."""
    path = tmp_path / "computed.csv"
    path.write_text("x\n")

    class NoBirth:
        def stat(self):
            return type("Stat", (), {"st_mtime": 0.0})()

        def __str__(self):
            return str(path)

    with pytest.raises(timing.Refusal, match="keeps no birth time"):
        REAL_BIRTH_TIME(NoBirth())
    if BIRTH_TIMES:
        assert REAL_BIRTH_TIME(path) == path.stat().st_birthtime


def _wheel(at, *, yanked=False, kind="bdist_wheel"):
    return {"packagetype": kind, "upload_time_iso_8601": at, "yanked": yanked}


MOCK_PYPI = {
    "releases": {
        "2.38.4": [
            _wheel("2026-10-09T20:50:00.1Z"),
            _wheel("2026-10-09T20:49:00Z", kind="sdist"),
        ],
        "2.39.0": [_wheel("2026-10-10T01:00:00.5Z")],
        "2.39.1": [_wheel("2026-10-10T05:00:00Z", yanked=True)],
        "2.40.0rc1": [_wheel("2026-10-10T06:00:00Z")],
        "2.9.0": [_wheel("2026-08-01T00:00:00Z")],
        "2.10.0": [],
    }
}


def test_wheel_uploads_keep_released_wheels_only():
    """MOCK: sdists, yanked wheels, pre-releases and empty releases drop out;
    versions order numerically, so 2.10 > 2.9."""
    uploads = timing.wheel_uploads(MOCK_PYPI)
    assert uploads == {
        "2.38.4": "2026-10-09T20:50:00.1Z",
        "2.39.0": "2026-10-10T01:00:00.5Z",
        "2.9.0": "2026-08-01T00:00:00Z",
    }
    assert timing.newest(uploads) == "2.39.0"
    assert list(timing.from_engine(uploads, "2.38.4")) == ["2.38.4", "2.39.0"]


@pytest.mark.parametrize(
    "moment, newer",
    [
        ("2026-10-10T00:59:59Z", []),
        ("2026-10-10T01:00:00Z", []),
        ("2026-10-10T01:00:01Z", ["2.39.0"]),
    ],
)
def test_a_newer_release_before_the_first_output_is_found(moment, newer):
    uploads = timing.wheel_uploads(MOCK_PYPI)
    assert timing.newer_before(uploads, "2.38.4", moment) == newer


def _computed(values: dict, path: Path) -> Path:
    lines = ["fix,scenario_id,state,variable,frozen,recomputed,delta,moved"]
    for (s, v), x in values.items():
        lines.append(f"latest_final,{s},TX,{v},0,{x!r},0,False")
    path.write_text("\n".join(lines) + "\n")
    return path


def test_compare_counts_the_outputs_that_differ(tmp_path):
    a = _computed({("s1", "v"): 1.0, ("s2", "v"): 2.0}, tmp_path / "a.csv")
    b = _computed({("s1", "v"): 1.0, ("s2", "v"): 2.5}, tmp_path / "b.csv")
    rows, summary = timing.compare(
        timing.read_computed(a), timing.read_computed(b), "2.38.4", "2.39.0"
    )
    assert summary == {
        "outputs": 2,
        "same": 1,
        "differ": ["s2|v"],
        "scored_outputs": 2,
        "scored_same": 1,
        "scored_differ": ["s2|v"],
        "excluded_differ": [],
        "max_abs_delta": 0.5,
    }
    assert [r["same"] for r in rows] == [True, False]
    # The same move on an output the release excludes touches no scored one.
    _, excluded = timing.compare(
        timing.read_computed(a),
        timing.read_computed(b),
        "2.38.4",
        "2.39.0",
        frozenset({("s2", "v")}),
    )
    assert (excluded["scored_outputs"], excluded["scored_same"]) == (1, 1)
    assert excluded["scored_differ"] == [] and excluded["excluded_differ"] == ["s2|v"]
    with pytest.raises(timing.Refusal, match="do not cover"):
        timing.compare(
            timing.read_computed(a),
            timing.read_computed(b),
            "x",
            "y",
            frozenset({("s9", "v")}),
        )


def test_compare_refuses_other_outputs_or_non_finite_values(tmp_path):
    a = timing.read_computed(_computed({("s1", "v"): 1.0}, tmp_path / "a.csv"))
    b = timing.read_computed(_computed({("s2", "v"): 1.0}, tmp_path / "b.csv"))
    with pytest.raises(timing.Refusal, match="different outputs"):
        timing.compare(a, b, "x", "y")
    nan = timing.read_computed(_computed({("s1", "v"): math.nan}, tmp_path / "n.csv"))
    with pytest.raises(timing.Refusal, match="non-finite"):
        timing.compare(a, nan, "x", "y")


@given(
    st.dictionaries(
        st.text("abc", min_size=1, max_size=3), st.floats(-1e9, 1e9), min_size=1
    )
)
def test_a_sweep_compared_with_itself_is_all_the_same(values):
    """Property: every output of a sweep is the same as itself."""
    computed = {(k, "v"): ("TX", x) for k, x in values.items()}
    rows, summary = timing.compare(computed, computed, "a", "a")
    assert summary["same"] == summary["outputs"] == len(values)
    assert summary["differ"] == [] and summary["max_abs_delta"] == 0.0


def _venv(root: Path, engine: str) -> Path:
    (root / f"lib/python3.12/site-packages/policyengine_us-{engine}.dist-info").mkdir(
        parents=True
    )
    return root


def _pypi_around_now(offset_newer: float, offset_engine: float = -3600) -> dict:
    """MOCK PyPI: the engine offset_engine seconds from now (an hour ago by
    default), a newer release offset_newer seconds from now."""

    def at(seconds):
        return timing.utc(time.time() + seconds)

    return {
        "releases": {
            "2.38.4": [_wheel(at(offset_engine))],
            "2.39.0": [_wheel(at(offset_newer))],
        }
    }


def _sweep_args(tmp_path: Path):
    """MOCK sweep inputs, in a sweep's order: the engine is installed, then
    the sweep writes its first output."""
    venv = _venv(tmp_path / "venv", "2.38.4")
    first = tmp_path / "computed.csv"
    first.write_text("x\n")
    return type(
        "Args",
        (),
        {"engine": "2.38.4", "venv": str(venv), "first_output": str(first)},
    )


MOCK_INSTALL = {"version": "MOCK", "files_verified": 1, "editable": False}


@pytest.mark.parametrize("offset, ok", [(600, True), (-600, False)])
def test_the_sweep_refuses_an_engine_that_was_not_the_newest(
    tmp_path, monkeypatch, offset, ok
):
    """MOCK: a release newer than the engine uploaded before the sweep's first
    output means the engine was not the newest when the sweep began."""
    args = _sweep_args(tmp_path)
    monkeypatch.setattr(timing, "engine_install", lambda venv, engine: MOCK_INSTALL)
    monkeypatch.setattr(timing, "read_pypi", lambda url=None: _pypi_around_now(offset))
    if ok:
        record = timing.sweep(args)
        assert record["reference_sweep"]["engine"] == "2.38.4"
        assert record["pypi"]["newest_at_read"] == "2.39.0"
        assert (
            record["reference_sweep"]["first_output_at_utc"]
            <= record["pypi"]["read_at_utc"]
        )
        assert record["reference_sweep"]["first_output_sha256"] == (
            timing.sha256(Path(args.first_output))
        )
    else:
        with pytest.raises(timing.Refusal, match="was not the newest"):
            timing.sweep(args)


def test_the_sweep_refuses_an_engine_uploaded_after_its_output(tmp_path, monkeypatch):
    """MOCK: an output older than its engine's wheel (an earlier rehearsal's
    file, say) cannot date the sweep."""
    args = _sweep_args(tmp_path)
    monkeypatch.setattr(timing, "engine_install", lambda venv, engine: MOCK_INSTALL)
    monkeypatch.setattr(
        timing, "read_pypi", lambda url=None: _pypi_around_now(7200, offset_engine=3600)
    )
    with pytest.raises(timing.Refusal, match="must follow"):
        timing.sweep(args)


_T = st.integers(0, 10).map(lambda n: f"2026-10-10T0{n // 10}:{n % 10}0:00Z")


@given(_T, _T, _T)
def test_a_sweep_follows_its_engines_upload_and_install(uploaded, installed, output):
    """Property: the order check passes exactly when upload <= install <= output."""
    if uploaded <= installed <= output:
        timing.sweep_order_problems(uploaded, installed, output, "2.38.4")
    else:
        with pytest.raises(timing.Refusal, match="must follow"):
            timing.sweep_order_problems(uploaded, installed, output, "2.38.4")


def _write_build(root: Path, values: dict, excluded: set, engine: str = "2.38.4"):
    """MOCK reference build and the committed snapshot it froze into: the
    references are the computed values, every output scored but ``excluded``,
    and the sidecar names the committed builder."""
    build, snapshot = root / "build", root / "snapshot"
    build.mkdir(parents=True)
    snapshot.mkdir(parents=True)
    _computed(values, build / "computed.csv")
    lines = ["scenario_id,variable,value,impact_weight"]
    lines += [f"{s},{v},{x!r}," for (s, v), x in values.items()]
    (build / "reference_outputs.csv").write_text("\n".join(lines) + "\n")
    record = {
        "exclusions": [{"scenario_id": s, "variable": v} for s, v in sorted(excluded)]
    }
    (build / "reference_exclusions.json").write_text(json.dumps(record))
    meta = {
        "reference_csv_sha256": timing.sha256(build / "reference_outputs.csv"),
        "revisions": [
            {
                "kind": "engine_upgrade",
                "engine_version": f"policyengine-us {engine}",
                "provenance": {"builder_sha256": timing.sha256(timing.BUILDER)},
            }
        ],
    }
    (build / "reference_outputs.csv.meta.json").write_text(json.dumps(meta))
    for name in (
        "reference_outputs.csv",
        "reference_outputs.csv.meta.json",
        "reference_exclusions.json",
    ):
        (snapshot / name).write_bytes((build / name).read_bytes())
    return build, snapshot


VALUES = {("s1", "v"): 1.0, ("s2", "v"): 2.0, ("s3", "v"): 3.0}


def _check_setup(tmp_path, monkeypatch, pypi, excluded=frozenset({("s3", "v")})):
    path = tmp_path / "sweep_timing.json"
    path.write_text(json.dumps({"reference_sweep": {"engine": "2.38.4"}, "pypi": {}}))
    monkeypatch.setattr(timing, "TIMING", path)
    monkeypatch.setattr(timing, "VERIFICATION", tmp_path / "verification")
    monkeypatch.setattr(timing, "read_pypi", lambda url=None: pypi)
    build, snapshot = _write_build(tmp_path, VALUES, set(excluded))
    return build, snapshot


def _check_args(build, snapshot, check_venv=None, work_dir=None):
    return type(
        "Args",
        (),
        {
            "build": str(build),
            "snapshot": str(snapshot),
            "check_venv": check_venv and str(check_venv),
            "work_dir": work_dir and str(work_dir),
        },
    )


def _MOCK_sweep(values: dict):
    """MOCK check sweep: writes ``values`` as the computed.csv a first pass on
    the venv's engine would, in place of running the builder."""

    def run(venv, engine, out_dir):
        out_dir.mkdir(parents=True)
        path = _computed(values, out_dir / "computed.csv")
        return path, {
            "builder_sha256": timing.sha256(timing.BUILDER),
            "MOCK": True,
            "engine_install": MOCK_INSTALL,
        }

    return run


ONLY_ENGINE = {"releases": {"2.38.4": [_wheel("2026-10-09T20:50:00Z")]}}


def test_the_check_records_a_still_newest_engine(tmp_path, monkeypatch):
    """MOCK: with the reference engine still the newest, the record says so and
    pins the build; a newer release needs a venv holding it."""
    build, snapshot = _check_setup(tmp_path, monkeypatch, ONLY_ENGINE)
    out = timing.check(_check_args(build, snapshot))
    check = out["publication_check"]
    assert check["engine"] == "2.38.4" and "was still the newest" in check["result"]
    assert check["scored_outputs"] == 2
    assert set(check["build_sha256"]) == {*timing.BUILD_FILES, "builder"}
    monkeypatch.setattr(timing, "read_pypi", lambda url=None: MOCK_PYPI)
    with pytest.raises(timing.Refusal, match="newer than the reference engine"):
        timing.check(_check_args(build, snapshot))


def test_the_check_holds_its_build_to_the_release(tmp_path, monkeypatch):
    """MOCK: a build that is not the frozen release's is refused before PyPI
    is read: another engine, a sidecar that does not pin its CSV, a missing or
    other builder, a sidecar, CSV or record that is not the committed
    snapshot's, a computed.csv that is not the scored references, and a
    non-finite value anywhere."""
    build, snapshot = _check_setup(tmp_path, monkeypatch, ONLY_ENGINE)
    meta_path = build / "reference_outputs.csv.meta.json"
    meta = json.loads(meta_path.read_text())
    revision = meta["revisions"][0]

    def refused(match):
        with pytest.raises(timing.Refusal, match=match):
            timing.check(_check_args(build, snapshot))

    def sidecar(**changes):
        meta_path.write_text(json.dumps({**meta, **changes}))

    sidecar(revisions=[{**revision, "engine_version": "x"}])
    refused("not an engine upgrade to 2.38.4")
    sidecar(reference_csv_sha256="0" * 64)
    refused("does not pin its reference_outputs.csv")
    for provenance in ({"builder_sha256": "f" * 64}, {}):
        sidecar(revisions=[{**revision, "provenance": provenance}])
        refused("not the committed one")
    sidecar(MOCK_extra=1)
    refused("reference_outputs.csv.meta.json is not the committed snapshot's")
    sidecar()
    record = snapshot / "reference_exclusions.json"
    original = record.read_bytes()
    record.write_text(json.dumps({"exclusions": []}))
    refused("reference_exclusions.json is not the committed snapshot's")
    record.write_bytes(original)
    _computed({**VALUES, ("s1", "v"): 1.5}, build / "computed.csv")
    refused("not its scored references")
    # Non-finite values are refused, scored or excluded, before any
    # comparison: the still-newest branch never reaches compare.
    for key in (("s1", "v"), ("s3", "v")):
        _computed({**VALUES, key: math.nan}, build / "computed.csv")
        refused("non-finite")
    # A moved excluded output is the engine's value, not the reference's: fine.
    _computed({**VALUES, ("s3", "v"): 9.0}, build / "computed.csv")
    assert timing.check(_check_args(build, snapshot))["publication_check"]


@pytest.mark.parametrize(
    "moved, publishes",
    [({}, True), ({("s3", "v"): 3.5}, True), ({("s2", "v"): 2.5}, False)],
)
def test_the_check_stops_the_publish_when_a_scored_output_moves(
    tmp_path, monkeypatch, moved, publishes
):
    """MOCK: check runs the sweep on the newer release itself (here a MOCK
    sweep); one that moves only excluded outputs passes, one that moves a
    scored output writes the record and exits non-zero."""
    build, snapshot = _check_setup(
        tmp_path, monkeypatch, _pypi_around_now(-1800, offset_engine=-7200)
    )
    venv = _venv(tmp_path / "check-venv", "2.39.0")
    monkeypatch.setattr(timing, "engine_install", lambda venv, engine: MOCK_INSTALL)
    monkeypatch.setattr(timing, "run_check_sweep", _MOCK_sweep({**VALUES, **moved}))
    monkeypatch.setattr(timing.tempfile, "mkdtemp", lambda **kw: str(tmp_path / "w"))
    monkeypatch.setattr(timing, "SNAPSHOT", snapshot)
    argv = ["check", "--build", str(build), "--check-venv", str(venv)]
    if publishes:
        timing.main(argv)
    else:
        with pytest.raises(timing.Refusal, match="do not publish"):
            timing.main(argv)
    check = json.loads(timing.TIMING.read_text())["publication_check"]
    assert check["engine"] == "2.39.0" and check["scored_outputs"] == 2
    assert bool(check["scored_differ"]) is not publishes
    assert check["check_sweep"]["MOCK"] is True
    assert check["check_sweep"]["engine_install"] == MOCK_INSTALL
    # A venv installed before the newer release's wheel was uploaded does not
    # hold that release.
    monkeypatch.setattr(
        timing,
        "read_pypi",
        lambda url=None: _pypi_around_now(3600, offset_engine=-7200),
    )
    with pytest.raises(timing.Refusal, match="must follow"):
        timing.check(_check_args(build, snapshot, venv, tmp_path / "w2"))


def _fake_run_writing(receipt_problems=(), computed=True):
    """MOCK subprocess.run for run_on_engine: writes the engine check's
    receipt (and the sweep's computed.csv) where the real runner would."""
    calls = []

    def run(command, env=None, **kw):
        calls.append((command, env))
        Path(env["PB_ENGINE_RECEIPT"]).write_text(
            json.dumps(
                {
                    "version": env["PB_EXPECTED_ENGINE"],
                    "files_verified": 2,
                    "problems": list(receipt_problems),
                }
            )
        )
        if computed and "--out-dir" in command:
            out = Path(command[command.index("--out-dir") + 1])
            out.mkdir(parents=True, exist_ok=True)  # as the builder does
            _computed(VALUES, out / "computed.csv")
        return type("Ran", (), {"returncode": 1, "stdout": "", "stderr": "draft"})()

    return run, calls


def test_the_check_sweep_runs_the_builder_in_the_checked_process(tmp_path, monkeypatch):
    """MOCK subprocess: one process, under the venv's interpreter with -P and a
    fresh bytecode-cache prefix, checks the engine and then runs the builder
    with empty actions naming the newer engine; a sweep that writes nothing,
    or a failed check, is refused."""
    run, calls = _fake_run_writing()
    monkeypatch.setattr(timing.subprocess, "run", run)
    venv = tmp_path / "venv"
    path, receipt = timing.run_check_sweep(venv, "2.39.0", tmp_path / "a")
    assert path.is_file() and receipt["exit_code"] == 1
    assert receipt["engine_install"]["fresh_bytecode_cache"] is True
    command, env = calls[0]
    assert command[:4] == [str(venv / "bin/python"), "-P", "-c", timing.ENGINE_RUNNER]
    assert command[4] == str(timing.BUILDER) and "--allow-draft" in command
    assert env["PB_EXPECTED_ENGINE"] == "2.39.0" and env["PYTHONPYCACHEPREFIX"]
    actions = json.loads((tmp_path / "a/actions.empty.json").read_text())
    assert actions["engine"] == "policyengine-us 2.39.0" and actions["draft"] is True
    run, _ = _fake_run_writing(computed=False)
    monkeypatch.setattr(timing.subprocess, "run", run)
    with pytest.raises(timing.Refusal, match="wrote no computed.csv"):
        timing.run_check_sweep(venv, "2.39.0", tmp_path / "b")
    run, _ = _fake_run_writing(receipt_problems=["an editable install"])
    monkeypatch.setattr(timing.subprocess, "run", run)
    with pytest.raises(timing.Refusal, match="an editable install"):
        timing.run_check_sweep(venv, "2.39.0", tmp_path / "c")
    monkeypatch.setattr(
        timing.subprocess,
        "run",
        lambda *a, **k: type(
            "Ran", (), {"returncode": 2, "stdout": "", "stderr": "x"}
        )(),
    )
    with pytest.raises(timing.Refusal, match="did not run"):
        timing.engine_install(venv, "2.39.0")


def test_a_relative_check_venv_is_the_one_found_and_run(tmp_path, monkeypatch):
    """MOCK: --check-venv given relative to a caller outside the repository is
    resolved once, so discovery, the install check and the sweep all use it."""
    build, snapshot = _check_setup(
        tmp_path, monkeypatch, _pypi_around_now(-1800, offset_engine=-7200)
    )
    venv = _venv(tmp_path / "check-venv", "2.39.0").resolve()
    seen = []

    def install(found, engine):
        seen.append(found)
        return MOCK_INSTALL

    def sweep(found, engine, out_dir):
        seen.append(found)
        return _MOCK_sweep(VALUES)(found, engine, out_dir)

    monkeypatch.setattr(timing, "engine_install", install)
    monkeypatch.setattr(timing, "run_check_sweep", sweep)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    timing.check(_check_args(build, snapshot, "../check-venv", tmp_path / "w"))
    assert seen == [venv, venv]


def test_a_missing_scratch_parent_is_created(tmp_path, monkeypatch):
    """MOCK: in a checkout without results/local, check creates it before
    making the sweep's scratch directory."""
    build, snapshot = _check_setup(
        tmp_path, monkeypatch, _pypi_around_now(-1800, offset_engine=-7200)
    )
    root = tmp_path / "clean-checkout"
    root.mkdir()
    monkeypatch.setattr(timing, "ROOT", root)
    monkeypatch.setattr(timing, "engine_install", lambda venv, engine: MOCK_INSTALL)
    monkeypatch.setattr(timing, "run_check_sweep", _MOCK_sweep(VALUES))
    venv = _venv(tmp_path / "check-venv", "2.39.0")
    timing.check(_check_args(build, snapshot, venv))
    assert (root / "results/local").is_dir()
    assert any((root / "results/local").glob("check-sweep-2.39.0-*"))


def _fake_install(
    root: Path, version: str, files: dict[str, str], algorithm: str = "sha256"
) -> Path:
    """MOCK site-packages: a policyengine-us wheel's dist-info whose RECORD
    pins ``files`` as written, with the given hash algorithm."""
    import base64
    import hashlib

    site = root / "site"
    record = []
    for name, text in files.items():
        path = site / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        digest = base64.urlsafe_b64encode(
            hashlib.new(algorithm, text.encode()).digest()
        )
        record.append(f"{name},{algorithm}={digest.rstrip(b'=').decode()},{len(text)}")
    info = site / f"policyengine_us-{version}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: policyengine-us\nVersion: {version}\n"
    )
    (info / "RECORD").write_text("\n".join(record) + "\n")
    return site


def _runner(
    tmp_path: Path, *paths: Path, builder=None, fresh_cache=True, expected="9.9.9"
):
    """Run ENGINE_RUNNER as run_on_engine does (-P, a fresh cache prefix), with
    ``paths`` first on the import path, as a shadowing tree or a .pth redirect
    would put them. Returns the receipt and the process."""
    import os
    import subprocess
    import sys
    import tempfile

    receipt = Path(tempfile.mkdtemp(dir=tmp_path)) / "receipt.json"
    env = {
        **{k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG")},
        "PYTHONPATH": os.pathsep.join(str(p) for p in paths),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PB_EXPECTED_ENGINE": expected,
        "PB_ENGINE_RECEIPT": str(receipt),
    }
    if fresh_cache:
        env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp(dir=tmp_path)
    command = [sys.executable, "-P", "-c", timing.ENGINE_RUNNER]
    if builder is not None:
        command.append(str(builder))
    ran = subprocess.run(command, env=env, capture_output=True, text=True, cwd=tmp_path)
    return json.loads(receipt.read_text()), ran


PACKAGE = {"policyengine_us/__init__.py": "X = 1\n", "policyengine_us/m.py": "Y = 2\n"}


def _printer(directory: Path) -> Path:
    """A MOCK builder that prints the engine module's X."""
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "builder.py"
    script.write_text("import policyengine_us\nprint('X', policyengine_us.X)\n")
    return script


@pytest.mark.parametrize("algorithm", ["sha256", "sha384", "sha512"])
def test_a_clean_wheel_passes_the_runner_and_runs_its_builder(tmp_path, algorithm):
    """MOCK install, real runner: a clean wheel, with any hash RECORD permits,
    passes and the builder runs in the same process on its code."""
    site = _fake_install(tmp_path / "clean", "9.9.9", PACKAGE, algorithm)
    found, ran = _runner(tmp_path, site, builder=_printer(tmp_path / "b"))
    assert found["problems"] == [] and found["files_verified"] == 2
    assert ran.returncode == 0 and "X 1" in ran.stdout


def test_the_runner_refuses_what_is_imported_not_the_label(tmp_path):
    """MOCK installs, real runner: a source tree shadowing the wheel under the
    same version label, an editable install, a file changed after install, an
    unrecorded module, an unrecorded native extension, a wrong version and a
    run without a fresh bytecode cache each stop it before any builder runs."""
    import importlib.machinery

    site = _fake_install(tmp_path / "clean", "9.9.9", PACKAGE)
    shadow = tmp_path / "shadow"
    (shadow / "policyengine_us").mkdir(parents=True)
    (shadow / "policyengine_us" / "__init__.py").write_text("X = 0\n")

    def problems(*paths, **kw):
        found, ran = _runner(tmp_path, *paths, builder=_printer(tmp_path / "p"), **kw)
        assert ran.returncode == 3 and "X " not in ran.stdout, ran.stdout
        return " ".join(found["problems"])

    assert "imports policyengine_us from" in problems(shadow, site)
    editable = _fake_install(tmp_path / "editable", "9.9.9", PACKAGE)
    (editable / "policyengine_us-9.9.9.dist-info" / "direct_url.json").write_text(
        json.dumps({"url": "file:///src", "dir_info": {"editable": True}})
    )
    assert "an editable install" in problems(editable)
    changed = _fake_install(tmp_path / "changed", "9.9.9", PACKAGE)
    (changed / "policyengine_us" / "m.py").write_text("Y = 3\n")
    assert "policyengine_us/m.py" in problems(changed)
    extra = _fake_install(tmp_path / "extra", "9.9.9", PACKAGE)
    (extra / "policyengine_us" / "extra.py").write_text("Z = 4\n")
    assert "importable files the wheel lacks" in problems(extra)
    native = _fake_install(tmp_path / "native", "9.9.9", PACKAGE)
    suffix = importlib.machinery.EXTENSION_SUFFIXES[0]
    (native / "policyengine_us" / f"m{suffix}").write_bytes(b"\0")
    assert f"policyengine_us/m{suffix}" in problems(native)
    assert "version 9.9.9, not 9.9.8" in problems(site, expected="9.9.8")
    assert "no fresh bytecode-cache prefix" in problems(site, fresh_cache=False)


def test_stale_bytecode_cannot_run_in_place_of_the_verified_source(tmp_path):
    """MOCK install, real runner: an unchecked-hash .pyc compiled from older
    code sits in __pycache__ beside a source that matches RECORD. A plain
    interpreter runs the stale bytecode; the runner's fresh cache prefix makes
    the builder run the verified source."""
    import importlib.util
    import os
    import py_compile
    import subprocess
    import sys

    site = _fake_install(tmp_path / "stale", "9.9.9", PACKAGE)
    source = site / "policyengine_us" / "__init__.py"
    old = tmp_path / "old" / "__init__.py"
    old.parent.mkdir()
    old.write_text("X = 0\n")
    py_compile.compile(
        str(old),
        cfile=importlib.util.cache_from_source(str(source)),
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )
    plain = subprocess.run(
        [sys.executable, "-c", "import policyengine_us; print('X', policyengine_us.X)"],
        env={**os.environ, "PYTHONPATH": str(site), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert "X 0" in plain.stdout  # the stale bytecode is what a plain import runs
    found, ran = _runner(tmp_path, site, builder=_printer(tmp_path / "b"))
    assert found["problems"] == [] and "X 1" in ran.stdout


def test_a_package_beside_the_builder_cannot_shadow_the_engine(tmp_path):
    """MOCK install, real runner: a policyengine_us package in the builder's
    own directory is not on the import path (-P, and runpy adds no script
    directory), so the builder runs the wheel's code."""
    site = _fake_install(tmp_path / "clean", "9.9.9", PACKAGE)
    beside = tmp_path / "scripts"
    (beside / "policyengine_us").mkdir(parents=True)
    (beside / "policyengine_us" / "__init__.py").write_text("X = -1\n")
    found, ran = _runner(tmp_path, site, builder=_printer(beside))
    assert found["problems"] == [] and "X 1" in ran.stdout


def test_a_symlink_in_the_package_is_refused(tmp_path):
    """MOCK installs, real runner: a symlinked directory (a package that would
    shadow a recorded module, its files hidden from the scan) and a symlinked
    file each stop the runner before the builder runs; installs must be
    copies, not links (so uv's symlink link mode is not supported)."""
    outside = tmp_path / "outside" / "spm"
    outside.mkdir(parents=True)
    (outside / "__init__.py").write_text("X = 99\n")
    linked_dir = _fake_install(
        tmp_path / "dir", "9.9.9", {**PACKAGE, "policyengine_us/spm.py": "S = 1\n"}
    )
    (linked_dir / "policyengine_us" / "spm").symlink_to(
        outside, target_is_directory=True
    )
    found, ran = _runner(tmp_path, linked_dir, builder=_printer(tmp_path / "b1"))
    assert ran.returncode == 3 and "policyengine_us/spm" in " ".join(found["problems"])
    linked_file = _fake_install(tmp_path / "file", "9.9.9", PACKAGE)
    target = tmp_path / "outside" / "m.py"
    target.write_text("Y = 2\n")
    (linked_file / "policyengine_us" / "m.py").unlink()
    (linked_file / "policyengine_us" / "m.py").symlink_to(target)
    found, ran = _runner(tmp_path, linked_file, builder=_printer(tmp_path / "b2"))
    assert ran.returncode == 3 and "symlinks in the package" in " ".join(
        found["problems"]
    )


def test_run_takes_only_fresh_receipts_and_outputs(tmp_path, monkeypatch):
    """MOCK subprocess: an existing receipt, or an out-dir already holding a
    computed.csv, is refused before anything runs; a run whose builder writes
    nothing new is refused after it; and a relative receipt given outside the
    repository is the file the child writes and the parent reads."""
    run, calls = _fake_run_writing()
    monkeypatch.setattr(timing.subprocess, "run", run)
    venv = _venv(tmp_path / "venv", "9.9.9")
    out = tmp_path / "pass1"
    out.mkdir()
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}")
    with pytest.raises(timing.Refusal, match="each run writes a fresh receipt"):
        timing.run_on_engine(venv, "9.9.9", receipt, ["--out-dir", str(out)])
    receipt.unlink()
    _computed(VALUES, out / "computed.csv")
    argv = ["run", "--venv", str(venv), "--engine", "9.9.9", "--receipt", str(receipt)]
    with pytest.raises(timing.Refusal, match="fresh out-dir"):
        timing.main([*argv, "--", "--out-dir", str(out)])
    (out / "computed.csv").unlink()
    silent, _ = _fake_run_writing(computed=False)
    monkeypatch.setattr(timing.subprocess, "run", silent)
    with pytest.raises(timing.Refusal, match="wrote no new"):
        timing.main([*argv, "--", "--out-dir", str(out)])
    # Outside the repository, a relative receipt and out-dir are resolved once.
    monkeypatch.setattr(timing.subprocess, "run", run)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    with pytest.raises(SystemExit) as stopped:
        timing.main(
            [
                "run",
                "--venv",
                str(venv),
                "--engine",
                "9.9.9",
                "--receipt",
                "r.json",
                "--",
                "--out-dir",
                "fresh",
            ]
        )
    assert stopped.value.code == 1  # the MOCK builder's draft refusal
    assert calls[-1][1]["PB_ENGINE_RECEIPT"] == str(elsewhere / "r.json")
    assert (elsewhere / "r.json").is_file() and (
        elsewhere / "fresh/computed.csv"
    ).is_file()


def test_builder_arguments_are_read_as_the_builder_reads_them(tmp_path, monkeypatch):
    """The equals form, an abbreviation and a repeated flag (last wins) name
    the same out-dir the builder would use; --computed-csv names the file the
    run must write; paths are resolved here; an unknown argument is refused."""
    monkeypatch.chdir(tmp_path)
    out = str(tmp_path / "b")
    for argv in (
        ["--out-dir", "b"],
        ["--out-dir=b"],
        ["--out-d", "b"],
        ["--out-dir", "a", "--out-dir=b"],
    ):
        canonical, computed = timing.builder_arguments([*argv, "--allow-draft"])
        assert canonical == ["--out-dir", out, "--allow-draft"], argv
        assert computed == tmp_path / "b" / "computed.csv"
    canonical, computed = timing.builder_arguments(
        ["--actions=x.json", "--out-dir", "b", "--computed-csv", "c.csv"]
    )
    assert canonical == [
        "--actions",
        str(tmp_path / "x.json"),
        "--out-dir",
        out,
        "--computed-csv",
        str(tmp_path / "c.csv"),
    ]
    assert computed == tmp_path / "c.csv"
    assert timing.builder_arguments(["--evidence-request", "r.json"])[1] is None
    with pytest.raises(timing.Refusal, match="cannot take these arguments"):
        timing.builder_arguments(["--out-dir", "b", "--unknown"])


def test_the_replica_takes_exactly_the_builders_flags():
    """builder_arguments' parser has the builder's own flags, so argparse
    resolves equals forms and abbreviations the same way in both."""
    import ast

    tree = ast.parse(timing.BUILDER.read_text())
    (main,) = [
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"
    ]
    flags = {
        call.args[0].value: any(
            k.arg == "action" and getattr(k.value, "value", None) == "store_true"
            for k in call.keywords
        )
        for call in ast.walk(main)
        if isinstance(call, ast.Call)
        and getattr(call.func, "attr", None) == "add_argument"
    }
    assert {f for f, switch in flags.items() if switch} == set(timing.BUILDER_SWITCHES)
    assert {f for f, switch in flags.items() if not switch} == set(
        timing.BUILDER_VALUE_FLAGS
    )


def test_run_checks_the_file_the_builder_actually_writes(tmp_path, monkeypatch):
    """MOCK subprocess: with the equals form an old computed.csv is still
    refused, and with --computed-csv the run checks that file, not the
    out-dir's."""

    def run(command, env=None, **kw):
        Path(env["PB_ENGINE_RECEIPT"]).write_text(
            json.dumps({"version": "9.9.9", "files_verified": 2, "problems": []})
        )
        target = Path(command[command.index("--computed-csv") + 1])
        _computed(VALUES, target)
        return type("Ran", (), {"returncode": 1, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(timing.subprocess, "run", run)
    venv = _venv(tmp_path / "venv", "9.9.9")
    old = tmp_path / "old"
    old.mkdir()
    _computed(VALUES, old / "computed.csv")
    base = ["run", "--venv", str(venv), "--engine", "9.9.9"]
    with pytest.raises(timing.Refusal, match="fresh out-dir"):
        timing.main(
            [*base, "--receipt", str(tmp_path / "r1.json"), "--", f"--out-dir={old}"]
        )
    with pytest.raises(SystemExit) as stopped:
        timing.main(
            [
                *base,
                "--receipt",
                str(tmp_path / "r2.json"),
                "--",
                "--out-dir",
                str(tmp_path / "new"),
                "--computed-csv",
                str(tmp_path / "c.csv"),
            ]
        )
    assert stopped.value.code == 1 and (tmp_path / "c.csv").is_file()
