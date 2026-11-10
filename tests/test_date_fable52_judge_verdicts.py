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
import datetime as dt
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


def release_conventions(written: str = WRITTEN_ON) -> str:
    """Release 20261027's date conventions with the ruled wave named, written
    on ``written``, as the driver's adjudicate step writes them."""
    base = driver.base_adjudication_record()["date_conventions"]
    spec = filled_spec(adjudications_written_on=written)
    with mock.patch.object(driver, "load_spec", lambda: spec):
        return driver.release_date_conventions(base, None)


def record_with(*entries, written: str = WRITTEN_ON) -> dict:
    """Release 20261027's record with ``entries`` added; with a ruled-wave
    entry among them, its date conventions name the wave as the frozen
    record does, written on ``written``."""
    record = driver.base_adjudication_record()
    record["adjudications"].extend(entries)
    if any(entry["adjudicated_on"] == WAVE for entry in entries):
        record["date_conventions"] = release_conventions(written)
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
    spec = filled_spec(adjudications_written_on=day)
    if driver.utc_day(day) is not None and day >= WAVE:
        # The frozen record states the same day the spec does.
        record = record_with(ruled_entry(), written=day)
        assert dating.new_waves(record, spec) == {WAVE: day}
    else:
        with pytest.raises(SystemExit):
            dating.new_waves(record_with(ruled_entry()), spec)


# --- Review r1, M14 (Z P3-5): the day the frozen record states ---------------


@settings(max_examples=60, deadline=None)
@given(
    recorded=st.dates(min_value=dt.date(2026, 11, 1), max_value=dt.date(2027, 12, 31)),
    spec_day=st.dates(min_value=dt.date(2026, 11, 1), max_value=dt.date(2027, 12, 31)),
)
def test_the_spec_and_the_frozen_record_must_state_the_same_day(recorded, spec_day):
    """The review's case among them: frozen on 2026-11-10, the spec moved to
    2026-11-11 before dating."""
    record = record_with(ruled_entry(), written=str(recorded))
    spec = filled_spec(adjudications_written_on=str(spec_day))
    if recorded == spec_day:
        assert dating.new_waves(record, spec) == {WAVE: str(spec_day)}
    else:
        with pytest.raises(SystemExit, match="the spec changed since the freeze"):
            dating.new_waves(record, spec)


def test_the_reviews_case_a_spec_moved_after_the_freeze_is_refused():
    record = record_with(ruled_entry(), written="2026-11-10")
    spec = filled_spec(adjudications_written_on="2026-11-11")
    with pytest.raises(
        SystemExit, match=r"written on '2026-11-10' and the spec says '2026-11-11'"
    ):
        dating.new_waves(record, spec)


def test_the_dating_parser_reads_the_day_the_driver_writes():
    """A differential check: driver.release_date_conventions writes the
    singular sentence for this release's one record, and the dating step
    reads its day back."""
    conventions = release_conventions("2026-11-12")
    assert (
        "The 2026-11-01 wave's decision follows Max's ruling of 2026-11-01 "
        "(21:06 UTC) and was written on 2026-11-12 UTC."
    ) in conventions
    record = {"date_conventions": conventions}
    assert dating.recorded_written_day(record, WAVE) == "2026-11-12"


@pytest.mark.parametrize(
    "conventions, day",
    [
        (
            "A. The 2026-11-01 wave's decision follows X and was written on "
            "2026-11-12 UTC. B.",
            "2026-11-12",
        ),
        (
            "The 2026-11-01 wave's decisions keep Y, and were written on "
            "2026-11-13 UTC.",
            "2026-11-13",
        ),
        ("The 2026-11-01 wave's decision follows X.", None),
        (
            "The 2026-11-01 wave's decision follows X and was written on "
            "2026-11-12. The 2026-11-02 wave's decisions were written on "
            "2026-11-13 UTC.",
            None,
        ),
        (
            "The 2026-11-01 wave's decision was written on 2026-11-12 UTC. "
            "The 2026-11-01 wave's decision was written on 2026-11-12 UTC.",
            None,
        ),
        ("Nothing names the wave.", None),
    ],
    ids=["singular", "plural", "no day", "no UTC", "twice", "absent"],
)
def test_the_recorded_day_comes_from_the_waves_own_sentence(conventions, day):
    assert dating.recorded_written_day({"date_conventions": conventions}, WAVE) == day


@pytest.mark.parametrize("conventions", ["base", "missing"])
def test_a_record_that_does_not_name_the_waves_day_is_refused(conventions):
    record = record_with(ruled_entry())
    if conventions == "base":
        record["date_conventions"] = driver.base_adjudication_record()[
            "date_conventions"
        ]
    else:
        del record["date_conventions"]
    with pytest.raises(SystemExit, match=r"written on None and the spec says"):
        dating.new_waves(record, filled_spec())


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


# --- Review r1, M14 (Z P3-3): the base's waves and cases, by value ------------

WAVE_FIELDS = ("commit", "release", "pull_request", "committed_on")


def _other(value):
    if isinstance(value, int):
        return value + 1
    return f"{value}0"


@pytest.mark.parametrize("field", WAVE_FIELDS)
@pytest.mark.parametrize("wave", dating.BASE_WAVES)
def test_a_base_waves_record_edited_is_refused(wave, field):
    """The review's case among them: 2026-10-14's commit, bf845cbe..., moved
    to another non-null string."""
    waves = copy.deepcopy(committed_evidence()["wave_releases"])
    assert set(waves[wave]) == set(WAVE_FIELDS)
    waves[wave][field] = _other(waves[wave][field])
    with pytest.raises(SystemExit, match=rf"waves \['{wave}'\] are not that"):
        dating.base_wave_releases(waves)


def _first_case(evidence: dict) -> str:
    return next(case for case in evidence["cases"] if case != CASE)


CASE_EDITS = {
    "a carried case's published verdict": lambda e: e["cases"][_first_case(e)][
        "published"
    ].update(case_failure_subtype="MOCK"),
    "a carried case's current verdict": lambda e: e["cases"][_first_case(e)][
        "current"
    ].update(verdict_sha256="0" * 64),
    "a carried case dropped": lambda e: e["cases"].pop(_first_case(e)),
    "a case added": lambda e: e["cases"].update(
        {"us__scenario_000__snap": {"current": {"tree": "stage"}}}
    ),
    "the ruled case with a carried field": lambda e: e["cases"].update(
        {CASE: {"previous": {"judge_model": "MOCK"}}}
    ),
    "the note": lambda e: e.update(note=e["note"] + " MOCK"),
    "a field added": lambda e: e.update(mock=True),
}


@pytest.mark.parametrize("edit", list(CASE_EDITS))
def test_evidence_cases_outside_the_releases_wave_must_be_the_bases(tmp_path, edit):
    write_verdict(tmp_path)
    evidence = committed_evidence()
    CASE_EDITS[edit](evidence)
    message = (
        "note or fields are not"
        if edit in ("the note", "a field added")
        else "cases .* are not release 20261027's"
    )
    with (
        mock.patch.object(driver, "load_spec", filled_spec),
        pytest.raises(SystemExit, match=message),
    ):
        dating.updated_evidence(evidence, tmp_path, record_with(ruled_entry()))


def test_the_base_evidence_names_no_case_of_the_ruled_wave():
    assert CASE not in committed_evidence()["cases"]


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


# --- Review r1, M14 (Z P3-4): restatements -----------------------------------


@pytest.fixture
def reopened(tmp_path, monkeypatch):
    """A MOCK judge provenance naming the cases this release re-opened."""

    def name(*cases):
        path = tmp_path / "judge_provenance.json"
        path.write_text(json.dumps({"verdicts": [{"case_id": c} for c in cases]}))
        monkeypatch.setattr(driver, "JUDGE_PROVENANCE", path)

    monkeypatch.setattr(driver, "load_spec", filled_spec)
    return name


def test_a_decision_on_a_reopened_case_is_restated_with_its_verdict(tmp_path, reopened):
    meta = write_verdict(tmp_path)
    reopened(CASE)
    restated = dating.restatements(tmp_path, record_with(ruled_entry()))
    assert restated["release"] == driver.RELEASE_TAG
    assert restated["base_commit"] == driver.BASE_COMMIT
    assert restated["cases"] == {
        CASE: {
            "judge_model": driver.JUDGE_MODEL,
            "case_failure_source": "llm_error",
            "case_failure_subtype": "state_local_rule",
            "reference_suspect": True,
            "judged_at_utc": meta["judged_at_utc"],
            "verdict_sha256": meta["verdict_sha256"],
        }
    }
    assert restated["note"].endswith(
        f" The {WAVE} wave's decision is new and restates nothing."
    )


@pytest.mark.parametrize(
    "verdict",
    [{"case_failure_subtype": "thresholds_rates"}, {"reference_suspect": False}],
)
def test_a_restatement_that_disagrees_with_its_verdict_is_refused(
    tmp_path, reopened, verdict
):
    write_verdict(tmp_path, **verdict)
    reopened(CASE)
    with pytest.raises(SystemExit, match="does not name its verdict"):
        dating.restatements(tmp_path, record_with(ruled_entry()))


def test_no_committed_decision_on_a_reopened_case_stops_the_step(tmp_path, reopened):
    """As the script stands: review r1's Z P3-4 asks to let an empty set
    through with a note; that relaxation waits on a ruling (report-r2.md)."""
    reopened("us__scenario_000__snap")
    with pytest.raises(SystemExit, match="no committed decision is on a re-opened"):
        dating.restatements(tmp_path, record_with(ruled_entry()))


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
