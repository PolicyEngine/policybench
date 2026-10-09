"""reference_audit/2026-10-09-engine-upgrade/scripts/sweep_timing.py: the
2026-10-09 move's timing record and publication check, on MOCK PyPI data."""

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


def _pypi_around_now(offset_newer: float) -> dict:
    """MOCK PyPI: the engine an hour ago, a newer release offset seconds from now."""

    def at(seconds):
        return timing.utc(time.time() + seconds)

    return {
        "releases": {
            "2.38.4": [_wheel(at(-3600))],
            "2.39.0": [_wheel(at(offset_newer))],
        }
    }


@pytest.mark.parametrize("offset, ok", [(600, True), (-600, False)])
def test_the_sweep_refuses_an_engine_that_was_not_the_newest(
    tmp_path, monkeypatch, offset, ok
):
    """MOCK: a release newer than the engine uploaded before the sweep's first
    output means the engine was not the newest when the sweep began."""
    first = tmp_path / "computed.csv"
    first.write_text("x\n")
    monkeypatch.setattr(timing, "read_pypi", lambda url=None: _pypi_around_now(offset))
    args = type(
        "Args",
        (),
        {
            "engine": "2.38.4",
            "venv": str(_venv(tmp_path / "venv", "2.38.4")),
            "first_output": str(first),
        },
    )
    if ok:
        record = timing.sweep(args)
        assert record["reference_sweep"]["engine"] == "2.38.4"
        assert record["pypi"]["newest_at_read"] == "2.39.0"
        assert (
            record["reference_sweep"]["first_output_at_utc"]
            <= record["pypi"]["read_at_utc"]
        )
    else:
        with pytest.raises(timing.Refusal, match="was not the newest"):
            timing.sweep(args)


def test_the_check_records_a_still_newest_engine(tmp_path, monkeypatch):
    record = {"reference_sweep": {"engine": "2.38.4"}, "pypi": {}}
    path = tmp_path / "sweep_timing.json"
    path.write_text(json.dumps(record))
    monkeypatch.setattr(timing, "TIMING", path)
    monkeypatch.setattr(
        timing,
        "read_pypi",
        lambda url=None: {"releases": {"2.38.4": [_wheel("2026-10-09T20:50:00Z")]}},
    )
    args = type(
        "Args", (), {"computed": "x", "check_computed": None, "check_venv": None}
    )
    out = timing.check(args)
    assert out["publication_check"]["engine"] == "2.38.4"
    assert "was still the newest" in out["publication_check"]["result"]
    monkeypatch.setattr(timing, "read_pypi", lambda url=None: MOCK_PYPI)
    with pytest.raises(timing.Refusal, match="newer than the reference engine"):
        timing.check(args)
