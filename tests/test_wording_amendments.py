"""Tests for policybench.wording_amendments: every committed wording
amendment in force is published, and the restoration of the 14 that release
dashboard-data-20261014 dropped.

The data tests read the committed annotation files, the committed snapshot
payload and, for release dashboard-data-20261013b's text, git. Unit tests
whose text is invented say MOCK.
"""

from __future__ import annotations

import functools
import gzip
import io
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from policybench import wording_amendments as wa
from policybench.adjudications import parse_adjudications

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "paper/snapshot/20260501/runs" / wa.RUN_LABEL / "data.json.gz"
# The board commit of release dashboard-data-20261013b, which last published
# the 14 amendments (docs/runbook.md, "Releases cut before sealing").
COMMIT_20261013B = "2cb77a17"
# The payload cells the restoration rewrites: the 17 that carry one of the
# four restored case notes (11 on scenario_086, 2 on each other case) and
# the six restored rows' cells, five of them among the 17.
RESTORED_CELLS = 18
RESTORED_CELL_FIELDS = 23

FIVE_CASES = Counter(
    {
        "us__scenario_015__head_medicaid_eligible": 6,
        "us__scenario_015__federal_refundable_credits": 3,
        "us__scenario_014__federal_refundable_credits": 2,
        "us__scenario_086__federal_refundable_credits": 2,
        "us__scenario_045__snap": 1,
    }
)


@functools.cache
def record() -> tuple[dict, ...]:
    return tuple(wa.load_record())


@functools.cache
def superseded() -> tuple[str | None, ...]:
    return tuple(wa.superseding_releases(record()))


@functools.cache
def the_14() -> tuple[dict, ...]:
    return tuple(wa.dropped_by_20261014(record()))


def read_frames(rows_text: str, notes_text: str) -> tuple[pd.DataFrame, ...]:
    return tuple(
        pd.read_csv(io.StringIO(text), keep_default_na=False)
        for text in (rows_text, notes_text)
    )


@functools.cache
def committed_text() -> tuple[str, str]:
    return tuple(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (wa.ROW_ANNOTATIONS_PATH, wa.CASE_NOTES_PATH)
    )


def committed_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    return read_frames(*committed_text())


@functools.cache
def restored_text() -> tuple[str, str]:
    rows, notes, restored, skipped = wa.restore_frames(*committed_frames(), the_14())
    assert len(restored) == 14 and skipped == []
    return rows.to_csv(index=False), notes.to_csv(index=False)


def restored_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    return read_frames(*restored_text())


@functools.cache
def adjudications() -> tuple[dict, ...]:
    data = json.loads((ROOT / wa.ADJUDICATIONS_PATH).read_text(encoding="utf-8"))
    return tuple(data["adjudications"])


@functools.cache
def snapshot_text() -> str:
    return gzip.decompress(SNAPSHOT.read_bytes()).decode("utf-8")


def snapshot() -> dict:
    return json.loads(snapshot_text())


def git_text(commit: str, path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{path.as_posix()}"],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")


def dropped(source) -> list[tuple[int, str]]:
    return wa.dropped_amendments(record(), source, superseded=superseded())


def targets(entries) -> set[tuple]:
    return {wa.target(e) for e in entries}


# --- The registry ------------------------------------------------------------


def test_the_registry_lists_every_release_since_the_record_began():
    """The releases' blocks cover the record, the last release is the one
    the app's pointer names, and every committed judge provenance file is a
    listed release's. A release that appends amendments, re-judges cases or
    moves the pointer without a RELEASES entry fails here."""
    tags = wa.entry_releases(record())
    assert len(tags) == len(record()) == 2448
    pointer = json.loads((ROOT / wa.POINTER_PATH).read_text())
    assert wa.RELEASES[-1].tag == pointer["tag"]
    assert len({r.tag for r in wa.RELEASES}) == len(wa.RELEASES)
    assert [r.tag for r in wa.RELEASES] == sorted(r.tag for r in wa.RELEASES)
    named = {r.judge_provenance for r in wa.RELEASES if r.judge_provenance}
    found = {
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "docs").rglob("judge_provenance.json")
    }
    assert named == found


def test_the_record_blocks_match_the_record_note():
    """The block sizes agree with the record's own note on its last block."""
    note = json.loads((ROOT / wa.RECORD_PATH).read_text())["note"]
    assert "The last 1578 (after the first 870)" in note
    sizes = [r.amendments for r in wa.RELEASES]
    assert sum(sizes[:5]) == 870 and sizes[6] == 1578


# --- The invariant -------------------------------------------------------------


def test_the_committed_files_publish_every_amendment_in_force():
    """Every amendment no later release has re-judged is published by the
    committed row annotations, case notes and adjudication record, but for
    the entries known_dropped names for the release the pointer names: the
    14 while that is dashboard-data-20261111, none after it. A release that
    drops a committed amendment on a kept case, or that does not restore
    the 14, fails here."""
    source = wa.committed_source()
    found = dropped(source)
    expected = wa.known_dropped(wa.RELEASES[-1].tag)
    assert [index for index, _ in found] == list(expected)
    assert {state for _, state in found} <= {wa.REVERTED}


def test_the_committed_snapshot_publishes_every_amendment_in_force():
    """The same for the committed snapshot's cells, which the dashboard
    payload publishes: a row annotation is its model's cell's annotation, a
    case note every cell's caseAnnotation."""
    found = dropped(wa.payload_source(snapshot()))
    expected = wa.known_dropped(wa.RELEASES[-1].tag)
    assert [index for index, _ in found] == list(expected)


def test_the_14_are_release_20261013bs_block_on_five_cases():
    """The pinned 14 are the whole block release 20261013b appended, on the
    five cases, 4 + 2 + 2 + 2 + 1 row and note targets."""
    tags = wa.entry_releases(record())
    block = [i for i, tag in enumerate(tags) if tag == "dashboard-data-20261013b"]
    assert tuple(block) == wa.DROPPED_BY_20261014
    assert Counter(e["case_id"] for e in the_14()) == FIVE_CASES
    assert len(targets(the_14())) == 10
    assert all(s is None for s in (superseded()[i] for i in block))


def test_the_pin_refuses_an_edited_record():
    """MOCK edit: one changed character in one of the 14 entries fails the
    pin, so an edit to the record cannot change what the restoration
    applies."""
    edited = [dict(e) for e in record()]
    edited[860]["new"] = edited[860]["new"] + " MOCK"
    with pytest.raises(wa.WordingAmendmentError, match="pinned"):
        wa.dropped_by_20261014(edited)


# --- The restoration on the committed data --------------------------------------


def test_the_restoration_gives_back_release_20261013bs_text():
    """Restoring the 14 on the committed files gives each of the 10 targets
    the text release 20261013b committed, byte for byte, and changes no
    other row, note or column."""
    before = committed_frames()
    after = restored_frames()
    published = read_frames(
        *(
            git_text(COMMIT_20261013B, path)
            for path in (wa.ROW_ANNOTATIONS_PATH, wa.CASE_NOTES_PATH)
        )
    )
    want = targets(the_14())
    for frame_before, frame_after, frame_then, column, with_model in zip(
        before,
        after,
        published,
        ("annotation", "case_annotation"),
        (True, False),
        strict=True,
    ):
        assert list(frame_after.columns) == list(frame_before.columns)
        changed = frame_after[column] != frame_before[column]
        assert frame_after.drop(columns=column).equals(
            frame_before.drop(columns=column)
        )
        keys = ["country", "scenario_id", "variable"] + (
            ["model"] if with_model else []
        )
        moved = {
            ("__".join(k[:3]), column, k[3] if with_model else None)
            for k in frame_after.loc[changed, keys].itertuples(index=False)
        }
        assert moved == {t for t in want if t[1] == column}
        then = {
            tuple(k): text
            for *k, text in frame_then[[*keys, column]].itertuples(index=False)
        }
        for *k, text in frame_after.loc[changed, [*keys, column]].itertuples(
            index=False
        ):
            assert text == then[tuple(k)], k


def test_the_restored_files_publish_every_amendment_in_force():
    rows, notes = restored_frames()
    assert dropped(wa.frame_source(rows, notes, adjudications())) == []


def test_the_restored_payload_publishes_every_amendment_in_force():
    """restore_payload rewrites the 10 targets' cells and nothing else: the
    changed cells are the row targets' models and every cell carrying a
    restored case note, each with only its annotation field changed, every
    other cell serialized as before, and the input payload unchanged."""
    payload = {"countries": {"us": snapshot()}}
    out, restored, skipped = wa.restore_payload(payload, the_14())
    assert len(restored) == 14 and skipped == []
    assert json.dumps(payload["countries"]["us"]) == json.dumps(
        json.loads(snapshot_text())
    )
    assert dropped(wa.payload_source(out)) == []
    before = payload["countries"]["us"]["scenarioPredictions"]
    after = out["countries"]["us"]["scenarioPredictions"]
    want: set[tuple] = set()
    for case, field, model in targets(the_14()):
        _, scenario, variable = case.split("__")
        cells = before[scenario][variable]
        if field == "annotation":
            want.add((scenario, variable, model, "annotation"))
        else:
            want |= {
                (scenario, variable, m, "caseAnnotation")
                for m, c in cells.items()
                if "caseAnnotation" in c
            }
    moved = set()
    for scenario, variables in after.items():
        for variable, cells in variables.items():
            for model, cell in cells.items():
                old = before[scenario][variable][model]
                if json.dumps(cell) == json.dumps(old):
                    continue
                assert list(cell) == list(old)
                moved |= {
                    (scenario, variable, model, k) for k in cell if cell[k] != old[k]
                }
    assert moved == want
    assert len(moved) == RESTORED_CELL_FIELDS


def test_a_reopened_case_is_skipped():
    """A case the release judged again keeps its text: the new verdict's
    text replaces what the entry corrected."""
    snap = "us__scenario_045__snap"
    rows, notes, restored, skipped = wa.restore_frames(
        *committed_frames(), the_14(), reopened=frozenset({snap})
    )
    assert [e["case_id"] for e in skipped] == [snap] and len(restored) == 13
    before = committed_frames()[0]
    assert (rows.annotation != before.annotation).sum() == 5
    out, restored, skipped = wa.restore_payload(
        {"countries": {"us": snapshot()}}, the_14(), reopened=frozenset({snap})
    )
    assert [e["case_id"] for e in skipped] == [snap] and len(restored) == 13


# --- A dropped amendment is caught, whichever it is -----------------------------


@functools.cache
def droppable() -> tuple[int, ...]:
    """In-force row and note amendments no later entry rewrites, whose new
    text the restored files hold once and whose old text they do not: the
    ones a release could drop by publishing the old text instead."""
    rows, notes = restored_frames()
    source = wa.frame_source(rows, notes)
    later = wa.later_same_target(record())
    out = []
    for index, entry in enumerate(record()):
        if superseded()[index] is not None or later[index]:
            continue
        if entry["field"] == "reasoning":
            continue
        (text,) = source(entry)
        if text.count(entry["new"]) == 1 and entry["old"] not in text:
            reverted = text.replace(entry["new"], entry["old"])
            if reverted.count(entry["old"]) == 1:
                out.append(index)
    return tuple(out)


def test_most_amendments_in_force_are_droppable():
    """The property below draws from most of the 444 amendments in force,
    the 14 among them where no later entry rewrites them."""
    assert sum(s is None for s in superseded()) == 444
    assert len(droppable()) >= 400
    assert set(droppable()) & set(wa.DROPPED_BY_20261014)


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(st.data())
def test_dropping_any_amendment_in_force_is_caught_and_restorable(data):
    """Put back one in-force amendment's old text in the restored files, as
    release 20261014 did to the 14: dropped_amendments names it, and
    restore_frames with that entry gives back the restored files exactly."""
    index = data.draw(st.sampled_from(droppable()), label="entry")
    entry = record()[index]
    rows, notes = restored_frames()
    frame = rows if entry["field"] == "annotation" else notes
    case = entry["case_id"].split("__")
    mask = (
        (frame.country == case[0])
        & (frame.scenario_id == case[1])
        & (frame.variable == case[2])
    )
    if entry["field"] == "annotation":
        mask &= frame.model == entry["model"]
    (at,) = frame.index[mask]
    frame.loc[at, entry["field"]] = frame.loc[at, entry["field"]].replace(
        entry["new"], entry["old"]
    )
    found = dict(dropped(wa.frame_source(rows, notes, adjudications())))
    assert found.get(index) == wa.REVERTED
    back_rows, back_notes, restored, _ = wa.restore_frames(rows, notes, [entry])
    assert restored == [entry]
    assert (back_rows.to_csv(index=False), back_notes.to_csv(index=False)) == (
        restored_text()
    )


# --- Refusals, on MOCK text -------------------------------------------------------

MOCK_ENTRY = {
    "case_id": "us__scenario_mock__mock_output",
    "field": "annotation",
    "model": "mock-model",
    "old": "MOCK old wording",
    "new": "MOCK new wording",
    "reason": "MOCK",
}


def mock_frames(row_text: str):
    rows = pd.DataFrame(
        {
            "country": ["us", "us"],
            "scenario_id": ["scenario_mock", "scenario_mock"],
            "variable": ["mock_output", "mock_output"],
            "model": ["mock-model", "other-model"],
            "annotation": [row_text, "MOCK old wording elsewhere"],
        }
    )
    notes = pd.DataFrame(
        {
            "country": ["us"],
            "scenario_id": ["scenario_mock"],
            "variable": ["mock_output"],
            "case_annotation": ["MOCK note"],
        }
    )
    return rows, notes


def test_restore_frames_changes_only_its_row():
    rows, notes = mock_frames("A MOCK old wording here.")
    out_rows, out_notes, restored, _ = wa.restore_frames(rows, notes, [MOCK_ENTRY])
    assert out_rows.annotation.tolist() == [
        "A MOCK new wording here.",
        "MOCK old wording elsewhere",
    ]
    assert rows.annotation[0] == "A MOCK old wording here."
    assert out_notes.equals(notes) and restored == [MOCK_ENTRY]


@pytest.mark.parametrize(
    "text, message",
    [
        ("No such wording.", "occurs 0 times"),
        ("MOCK old wording, MOCK old wording.", "occurs 2 times"),
        ("MOCK old wording, then MOCK new wording.", "already holds"),
    ],
)
def test_restore_frames_refuses_text_it_cannot_amend_exactly_once(text, message):
    rows, notes = mock_frames(text)
    with pytest.raises(wa.WordingAmendmentError, match=message):
        wa.restore_frames(rows, notes, [MOCK_ENTRY])


def test_restore_frames_refuses_a_missing_or_doubled_row_and_a_reasoning_entry():
    rows, notes = mock_frames("MOCK old wording")
    with pytest.raises(wa.WordingAmendmentError, match="0 rows"):
        wa.restore_frames(rows, notes, [{**MOCK_ENTRY, "model": "absent-model"}])
    doubled = pd.concat([rows.iloc[[0]], rows], ignore_index=True)
    with pytest.raises(wa.WordingAmendmentError, match="2 rows"):
        wa.restore_frames(doubled, notes, [MOCK_ENTRY])
    reasoning = {k: v for k, v in MOCK_ENTRY.items() if k != "model"}
    with pytest.raises(wa.WordingAmendmentError, match="only a row annotation"):
        wa.restore_frames(rows, notes, [{**reasoning, "field": "reasoning"}])


def test_restore_payload_refuses_a_case_without_cells():
    payload = {"scenarioPredictions": {"scenario_mock": {}}}
    with pytest.raises(wa.WordingAmendmentError, match="no cells"):
        wa.restore_payload(payload, [MOCK_ENTRY])
    payload = {
        "scenarioPredictions": {
            "scenario_mock": {"mock_output": {"mock-model": {"score": 0}}}
        }
    }
    with pytest.raises(wa.WordingAmendmentError, match="no cell carries"):
        wa.restore_payload(payload, [MOCK_ENTRY])


@pytest.mark.parametrize(
    "text, state",
    [
        ("MOCK new wording.", wa.APPLIED),
        ("MOCK old wording.", wa.REVERTED),
        ("MOCK old wording; MOCK new wording.", wa.BOTH),
        ("Something else.", wa.NEITHER),
        (None, wa.MISSING),
    ],
)
def test_entry_state(text, state):
    assert wa.entry_state(text, MOCK_ENTRY) == state


def test_entry_state_and_restore_text_when_the_new_text_cuts_words():
    """MOCK cut, as entry 1275 cuts "exactly 12% × $9,629 = " from its old
    text: the old text holds the new, so a reverted text holds the new text
    only inside the old, and is REVERTED, not APPLIED; restore_text amends
    it, and refuses a text holding the new text outside the old."""
    cut = {**MOCK_ENTRY, "old": "exactly MOCK $1.00", "new": "MOCK $1.00"}
    assert wa.entry_state("Paid MOCK $1.00.", cut) == wa.APPLIED
    assert wa.entry_state("Paid exactly MOCK $1.00.", cut) == wa.REVERTED
    assert wa.entry_state("Paid exactly MOCK $1.00, MOCK $1.00.", cut) == wa.BOTH
    assert wa.restore_text("Paid exactly MOCK $1.00.", [cut], "MOCK") == (
        "Paid MOCK $1.00."
    )
    with pytest.raises(wa.WordingAmendmentError, match="already holds"):
        wa.restore_text("Paid exactly MOCK $1.00, MOCK $1.00.", [cut], "MOCK")


def test_entry_state_undoes_later_rewrites_of_the_new_text_first():
    """MOCK chain: a later entry rewrote part of this entry's new text, so
    the published text holds neither entry's new text whole; undoing the
    later one shows this one applied."""
    later = {**MOCK_ENTRY, "old": "new wording", "new": "newer wording"}
    assert wa.entry_state("MOCK newer wording.", MOCK_ENTRY) == wa.NEITHER
    assert wa.entry_state("MOCK newer wording.", MOCK_ENTRY, [later]) == wa.APPLIED
    assert wa.entry_state("MOCK old wording.", MOCK_ENTRY, [later]) == wa.REVERTED


def test_entry_releases_refuses_an_unlisted_block():
    with pytest.raises(wa.WordingAmendmentError, match="list the release"):
        wa.entry_releases([*record(), MOCK_ENTRY])


# --- The Fable 5.2 driver's carry and gates, with the restoration --------------------


@pytest.fixture(scope="module")
def driver():
    """The Fable 5.2 driver, imported as its own tests import it (it imports
    release_20261006 from scripts/ when a gate runs)."""
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))
    import finish_fable52

    return finish_fable52


@pytest.fixture
def decisions():
    data = json.loads((ROOT / wa.ADJUDICATIONS_PATH).read_text(encoding="utf-8"))
    return parse_adjudications(data, wa.ADJUDICATIONS_PATH)


def serve_base(monkeypatch, driver, frames):
    """The driver's base_annotation_frames, serving ``frames``: the next
    release's base, release 20261111's committed files, with or without the
    restoration."""
    monkeypatch.setattr(
        driver, "base_annotation_frames", lambda: tuple(f.copy() for f in frames)
    )


def build(driver, decisions):
    """The frames triage builds when every case is kept: collect_audit's
    output stands in as the committed files themselves, since the carry
    replaces each kept row's and note's text with the base's."""
    rows, notes = committed_frames()
    collected = {
        "row": rows,
        "case": notes.rename(
            columns={
                "case_failure_sources": "case_failure_source",
                "case_failure_subtypes": "case_failure_subtype",
            }
        ),
    }
    return driver.annotation_frames(collected, frozenset(), decisions, [])


def test_the_carry_publishes_the_restoration_and_the_kept_gate_holds_it(
    monkeypatch, driver, decisions
):
    """With the restoration in the base the next release's driver carries
    (base_annotation_frames), triage's frames are the restored files, and
    the kept-case gate passes them. A release that carries the base without
    the restoration publishes the old text, and the gate, holding the
    restored base, names each of the 10 targets."""
    serve_base(monkeypatch, driver, restored_frames())
    built = build(driver, decisions)
    assert driver.kept_annotation_problems(*built, frozenset(), decisions) == []
    assert tuple(driver.annotation_csv_text(f) for f in built) == restored_text()

    serve_base(monkeypatch, driver, committed_frames())
    unrestored = build(driver, decisions)
    assert tuple(driver.annotation_csv_text(f) for f in unrestored) == (
        committed_text()
    )
    serve_base(monkeypatch, driver, restored_frames())
    problems = driver.kept_annotation_problems(
        *unrestored, frozenset(), decisions, limit=100
    )
    want = {
        f"{case} {model} annotation"
        if field == "annotation"
        else f"{case} case note case_annotation"
        for case, field, model in targets(the_14())
    }
    assert sorted(problems) == sorted(want)


def test_check_a_holds_the_export_to_the_restored_base_payload(driver):
    """The driver's check (a) compares the scope export's cells with the
    base payload's. Against restore_payload's base, an export carrying the
    restoration passes; against the unrestored base, exactly the 18 restored
    cells differ, so the next release passes restore_payload(live) as the
    base it compares."""
    us = snapshot()
    incumbents = {row["model"] for row in us["modelStats"]}
    five = {(c.split("__")[1], c.split("__")[2]) for c in FIVE_CASES}
    trimmed = {
        "countries": {
            "us": {
                "scenarioPredictions": {
                    scenario: {
                        variable: cells
                        for variable, cells in variables.items()
                        if (scenario, variable) in five
                    }
                    for scenario, variables in us["scenarioPredictions"].items()
                    if any(s == scenario for s, _ in five)
                }
            }
        }
    }
    restored, _, _ = wa.restore_payload(trimmed, the_14())
    assert driver.base_restoration_problems(restored, restored, incumbents) == []
    problems = driver.base_restoration_problems(
        restored, trimmed, incumbents, limit=100
    )
    assert len(problems) == RESTORED_CELLS
    assert all(p.startswith("scenarioPredictions ") for p in problems)
