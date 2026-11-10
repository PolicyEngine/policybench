"""The Claude Fable 5.2 dating step adds Max's 2026-11-01 wave (d2180) to the
judge-verdict evidence, uncommitted, and refuses any other wave.

MOCK DATA: the ruled decision, its verdict and its sidecar below are
synthetic and live in pytest's temporary directory; the written days stand
in for the lead's. Release 20261027's adjudication record and evidence are
read from git at the base commit, since the freeze and this step rewrite the
working tree's copies, and are only read.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from unittest import mock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import date_fable52_judge_verdicts as dating  # noqa: E402
import finish_fable52 as driver  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RULED = ("scenario_122", "state_refundable_credits")
WAVE = "2026-11-01"
WRITTEN_ON = "2026-11-10"
CASE = f"us__{RULED[0]}__{RULED[1]}"


def filled_spec(**changes) -> dict:
    """The spec as the lead fills it, with no triage decision."""
    spec = json.loads((REPO / driver.SPEC_PATH).read_text())
    spec.update(
        {
            "snapshot_date": WRITTEN_ON,
            "adjudications_written_on": WRITTEN_ON,
            "triage_adjudications": [],
        }
    )
    spec.update(changes)
    return spec


def ruled_entry(**changes) -> dict:
    """A MOCK decision of the ruled wave, its judge fields set as a verdict
    judged on WRITTEN_ON would set them."""
    entry = {
        "country": "us",
        "scenario_id": RULED[0],
        "variable": RULED[1],
        "adjudicated_on": WAVE,
        "judge_model": driver.JUDGE_MODEL,
        "judge_failure_source": "llm_error",
        "judge_failure_subtype": "state_local_rule",
        "judged_on_utc": WRITTEN_ON,
        "judge_reference_suspect": True,
    }
    entry.update(changes)
    return entry


EVIDENCE_PATH = dating.EVIDENCE.relative_to(REPO)


def record_with(*entries) -> dict:
    record = driver.base_adjudication_record()
    record["adjudications"].extend(entries)
    return record


def committed_evidence() -> dict:
    """Release 20261027's evidence, from git at the base commit."""
    return json.loads(driver.base_commit_blob(EVIDENCE_PATH))


def test_the_base_waves_are_the_committed_records_and_all_published():
    days = {
        e["adjudicated_on"] for e in driver.base_adjudication_record()["adjudications"]
    }
    assert sorted(days) == dating.BASE_WAVES
    waves = committed_evidence()["wave_releases"]
    assert list(waves) == dating.BASE_WAVES
    assert all(waves[wave].get("commit") for wave in dating.BASE_WAVES)


def test_the_output_is_named_for_the_release_day():
    assert dating.OUT.name == f"judge_verdicts_{driver.RELEASE_TAG[-8:]}.json"
    assert dating.OUT.parent == REPO / "docs/fable52"


def test_the_ruled_wave_is_written_on_the_specs_day():
    record = record_with(ruled_entry())
    assert dating.new_waves(record, filled_spec()) == {WAVE: WRITTEN_ON}


def test_the_record_before_the_freeze_is_refused():
    with pytest.raises(SystemExit, match=r"decides the waves \['2026-11-01'\]"):
        dating.new_waves(driver.base_adjudication_record(), filled_spec())


@pytest.mark.parametrize(
    "entries, spec, message",
    [
        (
            [ruled_entry(variable="snap")],
            {},
            "the 2026-11-01 wave decides",
        ),
        (
            [ruled_entry(), ruled_entry(scenario_id="scenario_000")],
            {},
            "the 2026-11-01 wave decides",
        ),
        (
            [ruled_entry(), ruled_entry(adjudicated_on="2026-11-02")],
            {},
            r"but the record names \['2026-11-01', '2026-11-02'\]",
        ),
        (
            [ruled_entry()],
            {"adjudications_written_on": "[LEAD: the UTC day]"},
            "names no day",
        ),
        ([ruled_entry()], {"adjudications_written_on": None}, "names no day"),
        (
            [ruled_entry()],
            {"adjudications_written_on": "2026-10-31"},
            "was written before it",
        ),
    ],
)
def test_a_wave_other_than_the_spec_says_is_refused(entries, spec, message):
    with pytest.raises(SystemExit, match=message):
        dating.new_waves(record_with(*entries), filled_spec(**spec))


@settings(max_examples=80, deadline=None)
@given(day=st.one_of(st.dates().map(str), st.text(max_size=12)))
def test_any_real_day_on_or_after_the_wave_is_accepted_and_no_other(day):
    record = record_with(ruled_entry())
    spec = filled_spec(adjudications_written_on=day)
    if driver.utc_day(day) is not None and day >= WAVE:
        assert dating.new_waves(record, spec) == {WAVE: day}
    else:
        with pytest.raises(SystemExit):
            dating.new_waves(record, spec)


def test_the_base_waves_pass_and_an_earlier_pass_is_dropped():
    waves = committed_evidence()["wave_releases"]
    assert dating.base_wave_releases(waves) == waves
    ours = {"commit": None, "release": driver.RELEASE_TAG}
    assert dating.base_wave_releases({**waves, WAVE: ours}) == waves


@pytest.mark.parametrize(
    "edit, message",
    [
        (
            lambda w: w.update({WAVE: {"commit": None, "release": "dashboard-data-x"}}),
            "not this release's",
        ),
        (
            lambda w: w.update(
                {WAVE: {"commit": "abc", "release": driver.RELEASE_TAG}}
            ),
            "not this release's",
        ),
        (lambda w: w["2026-10-14"].update(commit=None), "unfilled"),
        (lambda w: w.pop("2026-09-05"), "not release 20261027's"),
    ],
)
def test_evidence_that_is_not_the_bases_is_refused(edit, message):
    waves = copy.deepcopy(committed_evidence()["wave_releases"])
    edit(waves)
    with pytest.raises(SystemExit, match=message):
        dating.base_wave_releases(waves)


def write_verdict(stage: Path, **verdict_changes) -> dict:
    """A MOCK verdict for the ruled case and its sha256-binding sidecar."""
    folder = stage / "audit" / "cases" / CASE
    folder.mkdir(parents=True)
    verdict = {
        "case_failure_source": "llm_error",
        "case_failure_subtype": "state_local_rule",
        "reference_suspect": True,
        **verdict_changes,
    }
    raw = json.dumps(verdict).encode()
    (folder / "verdict.json").write_bytes(raw)
    meta = {
        "verdict_sha256": hashlib.sha256(raw).hexdigest(),
        "judge_model_requested": driver.JUDGE_MODEL,
        "judged_at_utc": f"{WRITTEN_ON}T03:04:05Z",
    }
    (folder / "verdict.meta.json").write_text(json.dumps(meta))
    return meta


def test_the_ruled_wave_joins_uncommitted_with_its_verdict(tmp_path):
    meta = write_verdict(tmp_path)
    record = record_with(ruled_entry())
    with mock.patch.object(driver, "load_spec", filled_spec):
        evidence = dating.updated_evidence(committed_evidence(), tmp_path, record)
        again = dating.updated_evidence(evidence, tmp_path, record)
    waves = evidence["wave_releases"]
    assert list(waves) == [*dating.BASE_WAVES, WAVE]
    assert waves[WAVE] == {
        "commit": None,
        "release": driver.RELEASE_TAG,
        "pull_request": None,
        "adjudications_written_on": WRITTEN_ON,
    }
    assert evidence["cases"][CASE]["current"] == {
        "tree": "stage",
        "judge_model": driver.JUDGE_MODEL,
        "case_failure_source": "llm_error",
        "case_failure_subtype": "state_local_rule",
        "reference_suspect": True,
        "judged_at_utc": meta["judged_at_utc"],
        "verdict_sha256": meta["verdict_sha256"],
    }
    assert "published" not in evidence["cases"][CASE]
    # Every earlier wave and case keeps its evidence, and a second pass on the
    # same stage changes nothing.
    before = committed_evidence()
    assert {w: waves[w] for w in dating.BASE_WAVES} == before["wave_releases"]
    assert {c: v for c, v in evidence["cases"].items() if c != CASE} == {
        c: v for c, v in before["cases"].items() if c != CASE
    }
    assert again == evidence


@pytest.mark.parametrize(
    "verdict, message",
    [
        ({"case_failure_subtype": "thresholds_rates"}, "does not name its verdict"),
        ({"reference_suspect": False}, "does not name its verdict"),
    ],
)
def test_a_decision_that_does_not_name_its_verdict_is_refused(
    tmp_path, verdict, message
):
    write_verdict(tmp_path, **verdict)
    with (
        mock.patch.object(driver, "load_spec", filled_spec),
        pytest.raises(SystemExit, match=message),
    ):
        dating.updated_evidence(
            committed_evidence(), tmp_path, record_with(ruled_entry())
        )


def test_a_verdict_its_sidecar_does_not_bind_is_refused(tmp_path):
    write_verdict(tmp_path)
    (tmp_path / "audit/cases" / CASE / "verdict.json").write_text("{}")
    with (
        mock.patch.object(driver, "load_spec", filled_spec),
        pytest.raises(SystemExit, match="the sidecar does not bind this verdict"),
    ):
        dating.updated_evidence(
            committed_evidence(), tmp_path, record_with(ruled_entry())
        )
