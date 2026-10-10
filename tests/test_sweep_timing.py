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


@pytest.mark.parametrize("offset, ok", [(600, True), (-600, False)])
def test_the_sweep_refuses_an_engine_that_was_not_the_newest(
    tmp_path, monkeypatch, offset, ok
):
    """MOCK: a release newer than the engine uploaded before the sweep's first
    output means the engine was not the newest when the sweep began."""
    args = _sweep_args(tmp_path)
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
        return path, {"builder_sha256": timing.sha256(timing.BUILDER), "MOCK": True}

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
    # A venv installed before the newer release's wheel was uploaded does not
    # hold that release.
    monkeypatch.setattr(
        timing,
        "read_pypi",
        lambda url=None: _pypi_around_now(3600, offset_engine=-7200),
    )
    with pytest.raises(timing.Refusal, match="must follow"):
        timing.check(_check_args(build, snapshot, venv, tmp_path / "w2"))


def test_the_check_sweep_is_run_and_must_write_its_output(tmp_path, monkeypatch):
    """MOCK subprocess: check runs the builder under the venv's interpreter
    with empty actions naming the newer engine, and refuses when that sweep
    writes nothing (as the builder does when the venv lacks the engine)."""
    calls = []

    def fake_run(command, **kw):
        calls.append(command)
        if "writes" in str(command[0]):
            out = Path(command[command.index("--out-dir") + 1])
            _computed(VALUES, out / "computed.csv")
        return type("Ran", (), {"returncode": 1, "stdout": "", "stderr": "draft"})()

    monkeypatch.setattr(timing.subprocess, "run", fake_run)
    venv = tmp_path / "writes-venv"
    path, receipt = timing.run_check_sweep(venv, "2.39.0", tmp_path / "a")
    assert path.is_file() and receipt["exit_code"] == 1
    actions = json.loads((tmp_path / "a/actions.empty.json").read_text())
    assert actions["engine"] == "policyengine-us 2.39.0" and actions["draft"] is True
    assert calls[0][0] == str(venv / "bin/python") and "--allow-draft" in calls[0]
    with pytest.raises(timing.Refusal, match="wrote no computed.csv"):
        timing.run_check_sweep(tmp_path / "silent-venv", "2.39.0", tmp_path / "b")
