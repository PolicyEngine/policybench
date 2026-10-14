"""scripts/date_argon_judge_verdicts.py: the wave evidence of release
dashboard-data-20261014 (Gemini 4 Argon and Muse Spark 1.3).

The release's one wave is its own triage decisions (docs/argon/spec.json's
triage_adjudications). It joins the evidence uncommitted, each of its
decisions gains the stage verdict it names, and a second pass writes the same
evidence. Every earlier wave stays release 20261013b's.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import date_argon_judge_verdicts as dating  # noqa: E402
import finish_argon as driver  # noqa: E402

DAY = "2026-10-14"
# The committed spec, read once: the tests patch driver.load_spec.
REAL_SPEC = driver.load_spec()


def _evidence() -> dict:
    return json.loads(dating.EVIDENCE.read_text())


def _spec(**changes) -> dict:
    spec = {
        **copy.deepcopy(REAL_SPEC),
        "triage_decided_on": DAY,
        "triage_adjudications_written_on": DAY,
    }
    spec.setdefault("triage_adjudications", [{"scenario_id": "MOCK"}])
    return {**spec, **changes}


def _entry(scenario: str, *, suspect: bool, day: str = DAY) -> dict:
    return {
        "country": "us",
        "scenario_id": scenario,
        "variable": "snap",
        "judge_model": driver.JUDGE_MODEL,
        "judge_failure_source": "llm_error",
        "judge_failure_subtype": "thresholds_rates",
        "adjudicated_failure_source": "llm_error",
        "adjudicated_failure_subtype": "thresholds_rates",
        "adjudicated_on": day,
        "adjudicator": "developer",
        "judge_reference_suspect": suspect,
        "reasoning": "MOCK",
        "judged_on_utc": "2026-10-13",
    }


def _bind(stage: Path, entry: dict, *, suspect: bool | None = None) -> None:
    folder = stage / "audit" / "cases" / dating.case_id(entry)
    folder.mkdir(parents=True, exist_ok=True)
    verdict = {
        "case_failure_source": entry["judge_failure_source"],
        "case_failure_subtype": entry["judge_failure_subtype"],
        "models": [],
        "reference_suspect": entry["judge_reference_suspect"]
        if suspect is None
        else suspect,
    }
    raw = json.dumps(verdict).encode()
    (folder / "verdict.json").write_bytes(raw)
    (folder / "verdict.meta.json").write_text(
        json.dumps(
            {
                "verdict_sha256": hashlib.sha256(raw).hexdigest(),
                "judge_model_requested": driver.JUDGE_MODEL,
                "judged_at_utc": "2026-10-13T19:00:00+00:00",
            }
        )
    )


def _record(*extra) -> dict:
    base = driver.base_adjudication_record()
    return {**base, "adjudications": base["adjudications"] + list(extra)}


def test_the_committed_evidence_holds_release_20261013bs_waves_or_this_releases():
    """Before the freeze the evidence is release 20261013b's; after the dating
    script it adds this release's triage wave, uncommitted. Either way the
    base waves come back, each published."""
    evidence = _evidence()
    waves = dating.base_wave_releases(evidence["wave_releases"])
    assert list(waves) == dating.BASE_WAVES
    assert all(release["commit"] for release in waves.values())
    extra = list(evidence["wave_releases"])[len(dating.BASE_WAVES) :]
    assert extra in ([], [REAL_SPEC["triage_decided_on"]])


def test_new_waves_allows_only_the_spec_triage_wave():
    spec = _spec()
    assert dating.new_waves(_record(), spec) == {}
    triaged = _record(_entry("scenario_009", suspect=False))
    assert dating.new_waves(triaged, spec) == {DAY: DAY}
    with pytest.raises(SystemExit, match="decides only its triage wave"):
        dating.new_waves(_record(_entry("scenario_009", suspect=False, day="2026-10-15")), spec)
    with pytest.raises(SystemExit, match="decides only its triage wave"):
        dating.new_waves(triaged, _spec(triage_adjudications=[]))
    with pytest.raises(SystemExit, match="written before it"):
        dating.new_waves(triaged, _spec(triage_adjudications_written_on="2026-10-13"))


def test_base_wave_releases_refuses_a_wave_that_is_not_this_releases():
    waves = _evidence()["wave_releases"]
    base = {wave: waves[wave] for wave in dating.BASE_WAVES}
    ours = {
        **base,
        DAY: {"commit": None, "release": driver.RELEASE_TAG, "pull_request": None},
    }
    assert dating.base_wave_releases(ours) == base
    for foreign in (
        {"commit": None, "release": "MOCK", "pull_request": None},
        {"commit": "f" * 40, "release": driver.RELEASE_TAG, "pull_request": 1},
    ):
        with pytest.raises(SystemExit, match="not this release's"):
            dating.base_wave_releases({**base, DAY: foreign})
    unfilled = copy.deepcopy(base)
    unfilled[dating.BASE_WAVES[-1]]["commit"] = None
    with pytest.raises(SystemExit, match="unfilled"):
        dating.base_wave_releases(unfilled)
    reordered = dict(reversed(list(base.items())))
    with pytest.raises(SystemExit, match="not release 20261013b's"):
        dating.base_wave_releases(reordered)


def test_the_triage_wave_joins_uncommitted_with_its_stage_verdicts(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(driver, "load_spec", lambda: _spec())
    entries = [
        _entry("scenario_009", suspect=False),
        _entry("scenario_064", suspect=True),
    ]
    for entry in entries:
        _bind(tmp_path, entry)
    record = _record(*entries)
    evidence = _evidence()
    out = dating.updated_evidence(evidence, tmp_path, record)
    assert list(out["wave_releases"]) == [*dating.BASE_WAVES, DAY]
    assert out["wave_releases"][DAY] == {
        "commit": None,
        "release": driver.RELEASE_TAG,
        "pull_request": None,
        "adjudications_written_on": DAY,
    }
    for entry in entries:
        found = out["cases"][dating.case_id(entry)]
        assert found["current"]["tree"] == "stage"
        assert found["current"]["reference_suspect"] is entry["judge_reference_suspect"]
        assert "published" not in found
    # The earlier waves and every other case are untouched.
    base = {k: v for k, v in out["cases"].items() if k not in map(dating.case_id, entries)}
    assert base == {
        k: v for k, v in evidence["cases"].items() if k not in map(dating.case_id, entries)
    }
    # A second pass on its own output writes the same evidence.
    assert dating.updated_evidence(out, tmp_path, record) == out


def test_the_evidence_refuses_a_triage_decision_that_does_not_name_its_verdict(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(driver, "load_spec", lambda: _spec())
    entry = _entry("scenario_064", suspect=True)
    _bind(tmp_path, entry, suspect=False)
    with pytest.raises(SystemExit, match="does not name its verdict"):
        dating.updated_evidence(_evidence(), tmp_path, _record(entry))


@settings(max_examples=40, deadline=None)
@given(flags=st.lists(st.booleans(), min_size=1, max_size=5))
def test_the_wave_evidence_is_idempotent_for_any_triage_decisions(flags):
    """For any number of triage decisions, flagged or not, the evidence
    names the wave once and a second pass changes nothing."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        entries = [
            _entry(f"scenario_9{i:02d}", suspect=flag) for i, flag in enumerate(flags)
        ]
        for entry in entries:
            _bind(stage, entry)
        record = _record(*entries)
        saved = driver.load_spec
        driver.load_spec = lambda: _spec()
        try:
            once = dating.updated_evidence(_evidence(), stage, record)
            twice = dating.updated_evidence(once, stage, record)
        finally:
            driver.load_spec = saved
    assert once == twice
    assert list(once["wave_releases"]).count(DAY) == 1
    assert all(dating.case_id(e) in once["cases"] for e in entries)
