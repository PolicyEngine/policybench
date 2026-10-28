"""scripts/date_terra_judge_verdicts.py: the judge evidence of release
dashboard-data-20261027 (GPT-6.1 Terra, the references on policyengine-us
2.60.0).

The release decides no wave. It commits release 20261014's triage wave, which
joined the evidence uncommitted: the wave names the commit that published it,
and each of its decisions gains the verdict that commit's record published. A
second pass writes the same evidence, and a wave beyond release 20261014's is
refused. Each decision on a case the release re-opened names its stage verdict.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import date_terra_judge_verdicts as dating  # noqa: E402
import finish_terra as driver  # noqa: E402

STAGE = ROOT / "results/local/terra/stage"
DAY = "2026-10-27"


@cache
def _shown(path: str) -> str:
    shown = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{driver.BASE_COMMIT}:{path}"],
        capture_output=True,
        text=True,
    )
    assert shown.returncode == 0, (
        f"{path} at {driver.BASE_COMMIT[:12]} needs git history; fetch full "
        "history. " + shown.stderr
    )
    return shown.stdout


def _base_evidence() -> dict:
    """The evidence as release 20261014 committed it: its triage wave
    uncommitted."""
    return json.loads(_shown(str(dating.EVIDENCE.relative_to(ROOT))))


def _evidence() -> dict:
    return json.loads(dating.EVIDENCE.read_text())


def _record(*extra) -> dict:
    record = dating.committed_record()
    return {**record, "adjudications": record["adjudications"] + list(extra)}


def _entry(scenario: str, *, suspect: bool, day: str = "2026-10-14") -> dict:
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
        "judge_rejudged_on": DAY,
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
                "judged_at_utc": f"{DAY}T09:00:00+00:00",
            }
        )
    )


def test_the_fill_is_release_20261014s_squash_merge():
    assert dating.fill_release() == {
        "commit": driver.BASE_COMMIT,
        "release": "dashboard-data-20261014",
        "pull_request": 221,
        "committed_on": "2026-10-14",
    }


def test_the_committed_evidence_is_release_20261014s_waves_all_filled():
    waves = _evidence()["wave_releases"]
    assert list(waves) == dating.BASE_WAVES
    assert all(release["commit"] for release in waves.values())
    assert waves["2026-10-14"] == dating.fill_release()


def test_the_committed_evidence_is_the_scripts_output_on_release_20261014s():
    """Differential: the script applied to the evidence release 20261014
    committed gives the committed evidence, and a second pass changes
    nothing."""
    record = dating.committed_record()
    once = dating.updated_evidence(_base_evidence(), record)
    assert once == _evidence()
    assert dating.updated_evidence(once, record) == once
    # Only the triage wave and its two decisions' published verdicts change.
    base = _base_evidence()
    changed = sorted(c for c in once["cases"] if once["cases"][c] != base["cases"][c])
    assert changed == sorted(
        dating.case_id(e)
        for e in record["adjudications"]
        if e["adjudicated_on"] in dating.FILL_WAVES
    )
    for case in changed:
        assert {k: v for k, v in once["cases"][case].items() if k != "published"} == (
            base["cases"][case]
        )
        assert once["cases"][case]["published"]["commit"] == driver.BASE_COMMIT


def test_a_wave_beyond_release_20261014s_is_refused():
    with pytest.raises(SystemExit, match="decides no wave"):
        dating.updated_evidence(
            _base_evidence(), _record(_entry("scenario_900", suspect=False, day=DAY))
        )
    waves = _evidence()["wave_releases"]
    extra = {**waves, DAY: {"commit": None, "release": driver.RELEASE_TAG}}
    with pytest.raises(SystemExit, match="not release 20261014's"):
        dating.base_wave_releases(extra)
    reordered = dict(reversed(list(waves.items())))
    with pytest.raises(SystemExit, match="not release 20261014's"):
        dating.base_wave_releases(reordered)


def test_a_wave_filled_otherwise_or_left_unfilled_is_refused():
    record = dating.committed_record()
    other = _base_evidence()
    other["wave_releases"]["2026-10-14"] = {
        **dating.fill_release(),
        "commit": "f" * 40,
    }
    with pytest.raises(SystemExit, match="filled otherwise"):
        dating.updated_evidence(other, record)
    foreign = _base_evidence()
    foreign["wave_releases"]["2026-10-14"]["release"] = "MOCK"
    with pytest.raises(SystemExit, match="not release 20261014's"):
        dating.updated_evidence(foreign, record)
    late = _base_evidence()
    late["wave_releases"]["2026-10-14"]["adjudications_written_on"] = "2026-10-15"
    with pytest.raises(SystemExit, match="written after"):
        dating.updated_evidence(late, record)
    unfilled = _base_evidence()
    unfilled["wave_releases"]["2026-10-10"]["commit"] = None
    with pytest.raises(SystemExit, match="unfilled"):
        dating.updated_evidence(unfilled, record)


def test_restatements_name_each_reopened_decisions_stage_verdict(tmp_path, monkeypatch):
    entries = [
        _entry("scenario_900", suspect=False),
        _entry("scenario_901", suspect=True),
    ]
    for entry in entries:
        _bind(tmp_path, entry)
    provenance = tmp_path / "judge_provenance.json"
    provenance.write_text(
        json.dumps({"verdicts": [{"case_id": dating.case_id(entries[0])}]})
    )
    monkeypatch.setattr(driver, "JUDGE_PROVENANCE", provenance)
    out = dating.restatements(tmp_path, {"adjudications": entries})
    assert list(out["cases"]) == [dating.case_id(entries[0])]
    found = out["cases"][dating.case_id(entries[0])]
    assert found["judged_at_utc"][:10] == DAY
    assert found["reference_suspect"] is False
    assert out["base_commit"] == driver.BASE_COMMIT
    _bind(tmp_path, entries[0], suspect=True)
    with pytest.raises(SystemExit, match="does not name its verdict"):
        dating.restatements(tmp_path, {"adjudications": entries})
    folder = tmp_path / "audit" / "cases" / dating.case_id(entries[0])
    (folder / "verdict.json").write_text("{}")
    with pytest.raises(SystemExit, match="does not bind"):
        dating.restatements(tmp_path, {"adjudications": entries})


FIELDS = ["judge_model", "judge_failure_source", "judge_failure_subtype", "day"]


@settings(max_examples=200, deadline=None)
@given(
    changed=st.sets(st.sampled_from(FIELDS)),
    flagged=st.booleans(),
    raised=st.booleans(),
    sourced=st.booleans(),
)
def test_judge_disagreements_finds_exactly_the_departures(
    changed, flagged, raised, sourced
):
    """A decision departs from its verdict in exactly the fields that differ,
    and in the flag unless it agrees or is set from an earlier run that
    judge_reference_suspect_source names."""
    verdict = {
        "case_failure_source": "llm_error",
        "case_failure_subtype": "thresholds_rates",
        "reference_suspect": raised,
    }
    meta = {
        "judge_model_requested": "claude-opus-5-5",
        "judged_at_utc": f"{DAY}T01:00:00Z",
    }
    entry = {
        "judge_model": "MOCK" if "judge_model" in changed else "claude-opus-5-5",
        "judge_failure_source": "MOCK"
        if "judge_failure_source" in changed
        else "llm_error",
        "judge_failure_subtype": "MOCK"
        if "judge_failure_subtype" in changed
        else "thresholds_rates",
        "judge_rejudged_on": "2026-10-28" if "day" in changed else DAY,
        "judge_reference_suspect": flagged,
    }
    if sourced:
        entry["judge_reference_suspect_source"] = "MOCK earlier run"
    flag_wrong = flagged != raised and not (flagged and not raised and sourced)
    problems = dating.judge_disagreements(entry, verdict, meta)
    assert len(problems) == len(changed) + flag_wrong


@pytest.mark.skipif(not STAGE.is_dir(), reason="the exported stage is local")
def test_the_committed_verdicts_are_the_stages():
    """Local: the committed docs/terra/judge_verdicts_20261027.json is the
    script's output on the exported stage."""
    committed = json.loads(dating.OUT.read_text())
    assert dating.restatements(STAGE, dating.committed_record()) == committed
    assert len(committed["cases"]) == 42


def test_the_restated_record_is_unchanged_in_every_wave():
    """The record decides every case release 20261014 decided, in the same
    waves (copied so the tests cannot change it)."""
    record = copy.deepcopy(dating.committed_record())
    dating.require_no_new_waves(record)
    assert {e["adjudicated_on"] for e in record["adjudications"]} == set(
        dating.BASE_WAVES
    )
