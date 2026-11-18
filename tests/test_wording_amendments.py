"""Tests for policybench.wording_amendments: every committed wording
amendment in force is published, and the restoration of the 14 that release
dashboard-data-20261014 dropped.

Two kinds of data test. The invariant and registry tests read the working
tree, so they hold every later release's committed files. The restoration
tests read release dashboard-data-20261111's files from git at its board
commit, the base the next release restores the 14 on, so they still hold
once that release commits the restored text. Unit tests whose text is
invented say MOCK.
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
SNAPSHOT_PATH = Path("paper/snapshot/20260501/runs") / wa.RUN_LABEL / "data.json.gz"
# Board commits (docs/runbook.md, "Releases cut before sealing", and #260):
# release dashboard-data-20261013b, which last published the 14, and release
# dashboard-data-20261111, the base the next release restores them on.
COMMIT_20261013B = "2cb77a17"
COMMIT_20261111 = "e61eea4c"
TAG_20261111 = "dashboard-data-20261111"
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


def git_bytes(commit: str, path: Path) -> bytes:
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{path.as_posix()}"],
        capture_output=True,
        check=True,
    ).stdout


def read_frames(rows_text: str, notes_text: str) -> tuple[pd.DataFrame, ...]:
    return tuple(
        pd.read_csv(io.StringIO(text), keep_default_na=False)
        for text in (rows_text, notes_text)
    )


def targets(entries) -> set[tuple]:
    return {wa.target(e) for e in entries}


# --- The working tree: what the pointer's release committed ----------------------


@functools.cache
def record() -> tuple[dict, ...]:
    return tuple(wa.load_record())


@functools.cache
def superseded() -> tuple[str | None, ...]:
    return tuple(wa.superseding_releases(record()))


@functools.cache
def snapshot_text() -> str:
    return gzip.decompress((ROOT / SNAPSHOT_PATH).read_bytes()).decode("utf-8")


# --- Release 20261111 at its board commit: the base of the restoration ------------

RELEASES_TO_20261111 = wa.RELEASES[
    : [r.tag for r in wa.RELEASES].index(TAG_20261111) + 1
]


@functools.cache
def base_record() -> tuple[dict, ...]:
    return tuple(
        wa.parse_record(json.loads(git_bytes(COMMIT_20261111, wa.RECORD_PATH)))
    )


@functools.cache
def base_superseded() -> tuple[str | None, ...]:
    return tuple(wa.superseding_releases(base_record(), ROOT, RELEASES_TO_20261111))


@functools.cache
def base_text() -> tuple[str, str]:
    return tuple(
        git_bytes(COMMIT_20261111, path).decode("utf-8")
        for path in (wa.ROW_ANNOTATIONS_PATH, wa.CASE_NOTES_PATH)
    )


def base_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    return read_frames(*base_text())


@functools.cache
def base_adjudications() -> tuple[dict, ...]:
    data = json.loads(git_bytes(COMMIT_20261111, wa.ADJUDICATIONS_PATH))
    return tuple(data["adjudications"])


@functools.cache
def base_snapshot_text() -> str:
    return gzip.decompress(git_bytes(COMMIT_20261111, SNAPSHOT_PATH)).decode("utf-8")


def base_snapshot() -> dict:
    return json.loads(base_snapshot_text())


@functools.cache
def the_14() -> tuple[dict, ...]:
    return tuple(wa.dropped_by_20261014(base_record()))


@functools.cache
def restored_text() -> tuple[str, str]:
    rows, notes, restored, skipped = wa.restore_csv_texts(*base_text(), the_14())
    assert len(restored) == 14 and skipped == []
    return rows, notes


def restored_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    return read_frames(*restored_text())


def base_dropped(source) -> list[tuple[int, str]]:
    return wa.dropped_amendments(base_record(), source, superseded=base_superseded())


# --- The registry ------------------------------------------------------------------


def test_the_registry_lists_every_release_since_the_record_began():
    """The releases' blocks cover the record, the last release is the one
    the app's pointer names, every committed judge provenance file is a
    listed release's and matches its pin, and the record only grows. A
    release that appends amendments, re-judges cases, moves the pointer or
    edits a provenance file without a RELEASES entry fails here."""
    assert len(wa.entry_releases(record())) == len(record())
    pointer = json.loads((ROOT / wa.POINTER_PATH).read_text())
    assert wa.RELEASES[-1].tag == pointer["tag"]
    tags = [r.tag for r in wa.RELEASES]
    assert len(set(tags)) == len(tags) and tags == sorted(tags)
    named = {r.judge_provenance for r in wa.RELEASES if r.judge_provenance}
    found = {
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "docs").rglob("judge_provenance.json")
    }
    assert named == found
    assert set(wa.rejudged_cases()) == set(tags)
    assert record()[: len(base_record())] == base_record()


def test_the_registry_matches_the_record_at_release_20261111():
    """Release 20261111's record: 2448 entries, its note naming the last
    block's 1578, and the blocks the registry gives."""
    assert len(base_record()) == 2448
    note = json.loads(git_bytes(COMMIT_20261111, wa.RECORD_PATH))["note"]
    assert "The last 1578 (after the first 870)" in note
    assert [r.amendments for r in RELEASES_TO_20261111] == [
        394, 0, 0, 462, 14, 0, 1578, 0,
    ]  # fmt: skip


def test_a_provenance_file_that_moved_is_refused(tmp_path):
    """MOCK edit: one changed byte in a listed provenance file fails its pin,
    so editing a release's re-judged cases cannot retire an amendment."""
    release = wa.RELEASES[4]
    path = tmp_path / release.judge_provenance
    path.parent.mkdir(parents=True)
    path.write_bytes((ROOT / release.judge_provenance).read_bytes() + b"\n")
    with pytest.raises(wa.WordingAmendmentError, match="pins"):
        wa.rejudged_cases(tmp_path, [release])


def test_only_the_three_releases_publish_without_the_14():
    """Closed list: a later release cannot join it to pass the invariant
    with the 14 still dropped."""
    assert wa.PUBLISHED_WITHOUT_THE_14 == (
        "dashboard-data-20261014",
        "dashboard-data-20261027",
        TAG_20261111,
    )
    assert wa.known_dropped("dashboard-data-20261209") == ()
    assert wa.known_dropped(TAG_20261111) == wa.DROPPED_BY_20261014


# --- The invariant ---------------------------------------------------------------


def test_the_committed_files_publish_every_amendment_in_force():
    """Every amendment in force is published by the committed row
    annotations, case note bodies, adjudication record and adjudication
    sentences, but for the entries known_dropped names for the release the
    pointer names: the 14 while that is dashboard-data-20261111, none after
    it. A release that drops a committed amendment on a kept case or a
    decision's reasoning, or does not restore the 14, fails here."""
    found = wa.dropped_amendments(
        record(), wa.committed_source(), superseded=superseded()
    )
    assert [index for index, _ in found] == list(wa.known_dropped(wa.RELEASES[-1].tag))
    assert {state for _, state in found} <= {wa.REVERTED}


def test_the_committed_snapshot_publishes_every_amendment_in_force():
    """The same for the committed snapshot's cells, which the dashboard
    payload publishes: a row annotation is its model's cell's annotation, a
    case note every cell's caseAnnotation body, a decision's reasoning every
    cell's adjudication sentence."""
    found = wa.dropped_amendments(
        record(),
        wa.payload_source(json.loads(snapshot_text())),
        superseded=superseded(),
    )
    assert [index for index, _ in found] == list(wa.known_dropped(wa.RELEASES[-1].tag))


def test_release_20261111_published_everything_in_force_but_the_14():
    """At its board commit: 456 amendments in force (439 row and note, all
    17 reasoning), every one published but the 14, in the files and in the
    snapshot."""
    in_force = [i for i, s in enumerate(base_superseded()) if s is None]
    assert len(in_force) == 456
    reasoning = [i for i, e in enumerate(base_record()) if e["field"] == "reasoning"]
    assert len(reasoning) == 17 and set(reasoning) <= set(in_force)
    files = wa.frame_source(*base_frames(), base_adjudications())
    cells = wa.payload_source(base_snapshot())
    for source in (files, cells):
        assert base_dropped(source) == [
            (i, wa.REVERTED) for i in wa.DROPPED_BY_20261014
        ]


def test_the_14_are_release_20261013bs_block_on_five_cases():
    """The pinned 14 are the whole block release 20261013b appended, on the
    five cases, four case notes and six rows, none of them re-judged by
    release 20261111."""
    tags = wa.entry_releases(base_record(), RELEASES_TO_20261111)
    block = [i for i, tag in enumerate(tags) if tag == "dashboard-data-20261013b"]
    assert tuple(block) == wa.DROPPED_BY_20261014
    assert Counter(e["case_id"] for e in the_14()) == FIVE_CASES
    assert Counter(t[1] for t in targets(the_14())) == {
        "case_annotation": 4,
        "annotation": 6,
    }
    assert all(base_superseded()[i] is None for i in block)


def test_the_pin_refuses_an_edited_record():
    """MOCK edit: one changed character in one of the 14 entries fails the
    pin, so an edit to the record cannot change what the restoration
    applies."""
    edited = [dict(e) for e in base_record()]
    edited[860]["new"] = edited[860]["new"] + " MOCK"
    with pytest.raises(wa.WordingAmendmentError, match="pinned"):
        wa.dropped_by_20261014(edited)


# --- The restoration, on release 20261111's committed data ---------------------------


def test_the_restoration_gives_back_release_20261013bs_text():
    """Restoring the 14 on release 20261111's files gives each of the 10
    targets the text release 20261013b committed, byte for byte, and changes
    no other row, note or column."""
    before = base_frames()
    after = restored_frames()
    published = read_frames(
        *(
            git_bytes(COMMIT_20261013B, path).decode("utf-8")
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


def test_restore_csv_texts_writes_the_files_as_committed():
    """Read and written back with nothing restored, both files are their
    committed bytes, so the restored text differs from them only where the
    14 restore."""
    rows, notes, restored, _ = wa.restore_csv_texts(*base_text(), [])
    assert (rows, notes) == base_text() and restored == []


def test_the_restored_files_publish_every_amendment_in_force():
    files = wa.frame_source(*restored_frames(), base_adjudications())
    assert base_dropped(files) == []


def test_the_restored_payload_publishes_every_amendment_in_force():
    """restore_payload rewrites the 10 targets' cells and nothing else: the
    changed cells are the row targets' models and every cell carrying a
    restored case note, each with only its annotation field changed and its
    keys in order, every other cell serialized as before, the input payload
    unchanged, and each restored field release 20261013b's."""
    payload = {"countries": {"us": base_snapshot()}}
    out, restored, skipped = wa.restore_payload(payload, the_14())
    assert len(restored) == 14 and skipped == []
    assert json.dumps(payload["countries"]["us"]) == json.dumps(
        json.loads(base_snapshot_text())
    )
    assert base_dropped(wa.payload_source(out)) == []
    before = payload["countries"]["us"]["scenarioPredictions"]
    after = out["countries"]["us"]["scenarioPredictions"]
    then = json.loads(gzip.decompress(git_bytes(COMMIT_20261013B, SNAPSHOT_PATH)))[
        "scenarioPredictions"
    ]
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
    assert moved == want and len(moved) == RESTORED_CELL_FIELDS
    assert len({m[:3] for m in moved}) == RESTORED_CELLS
    for scenario, variable, model, field in moved:
        assert (
            after[scenario][variable][model][field]
            == (then[scenario][variable][model][field])
        )


def test_a_reopened_case_is_skipped():
    """A case the release judged again keeps its text: the new verdict's
    text replaces what the entry corrected."""
    snap = "us__scenario_045__snap"
    rows, notes, restored, skipped = wa.restore_frames(
        *base_frames(), the_14(), reopened=frozenset({snap})
    )
    assert [e["case_id"] for e in skipped] == [snap] and len(restored) == 13
    assert (rows.annotation != base_frames()[0].annotation).sum() == 5
    out, restored, skipped = wa.restore_payload(
        {"countries": {"us": base_snapshot()}}, the_14(), reopened=frozenset({snap})
    )
    assert [e["case_id"] for e in skipped] == [snap] and len(restored) == 13


# --- A dropped amendment is caught, whichever it is ----------------------------------


def undo(text: str, entries) -> str:
    """``text`` with ``entries`` undone, last first, each new text back to
    its old once: the text a rebuild from before them would publish."""
    for entry in reversed(list(entries)):
        assert entry["new"] in text, entry
        text = text.replace(entry["new"], entry["old"], 1)
    return text


@functools.cache
def droppable() -> tuple[int, ...]:
    """In-force row and note amendments no later entry rewrites, whose new
    text the restored files hold once and whose old text they do not, so
    putting the old text back gives it exactly once."""
    source = wa.frame_source(*restored_frames())
    later = wa.later_same_target(base_record())
    out = []
    for index, entry in enumerate(base_record()):
        if (
            base_superseded()[index] is not None
            or later[index]
            or entry["field"] == "reasoning"
        ):
            continue
        (text,) = source(entry)
        if text.count(entry["new"]) == 1 and entry["old"] not in text:
            if text.replace(entry["new"], entry["old"]).count(entry["old"]) == 1:
                out.append(index)
    return tuple(out)


def test_most_amendments_in_force_are_droppable():
    """The property below draws from most of the 439 row and note
    amendments in force, ten of the 14 among them."""
    assert len(droppable()) >= 400
    assert len(set(droppable()) & set(wa.DROPPED_BY_20261014)) == 10


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(st.data())
def test_dropping_any_amendment_in_force_is_caught_and_restorable(data):
    """Put back one in-force amendment's old text in the restored files, as
    release 20261014 did to the 14 (in a case note, in its body: the
    adjudication sentence is the decision's text, which may also hold the new
    wording, as entry 2398's case's does): dropped_amendments names it, and
    restore_frames with that entry gives back the restored files exactly."""
    index = data.draw(st.sampled_from(droppable()), label="entry")
    entry = base_record()[index]
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
    body, sentence = wa.split_note(frame.loc[at, entry["field"]])
    if entry["field"] == "annotation":
        body, sentence = frame.loc[at, entry["field"]], ""
    frame.loc[at, entry["field"]] = body.replace(entry["new"], entry["old"]) + sentence
    found = dict(base_dropped(wa.frame_source(rows, notes, base_adjudications())))
    assert found.get(index) == wa.REVERTED
    back_rows, back_notes, restored, _ = wa.restore_frames(rows, notes, [entry])
    assert restored == [entry]
    assert (back_rows.to_csv(index=False), back_notes.to_csv(index=False)) == (
        restored_text()
    )


def test_rebuilding_any_target_from_before_its_amendments_is_caught():
    """Every in-force row and note target, its whole chain of amendments
    undone (what a rebuild from the pre-amendment verdict publishes), flags
    at least one of its entries, chained targets and entry 2398 (whose new
    text the case's adjudication sentence also holds) included."""
    rows, notes = restored_frames()
    source = wa.frame_source(rows, notes, base_adjudications())
    record = base_record()
    later = wa.later_same_target(record)
    chains: dict[tuple, list[int]] = {}
    for index, entry in enumerate(record):
        if base_superseded()[index] is None and entry["field"] != "reasoning":
            chains.setdefault(wa.target(entry), []).append(index)
    assert len(chains) == 414
    for key, chain in chains.items():
        (text,) = source(record[chain[0]])
        reverted = undo(text, [record[i] for i in chain])
        states = [wa.entry_state(reverted, record[i], later[i]) for i in chain]
        assert any(s != wa.APPLIED for s in states), (key, states)
    assert 2398 in chains[wa.target(record[2398])]


@pytest.mark.parametrize("where", ["record", "sentence"])
def test_reverting_any_decisions_reasoning_is_caught(where):
    """Each of the 17 reasoning amendments, its chain undone in the
    adjudication record (or only in the case note's adjudication sentence
    that restates it), is flagged: a re-judge does not retire a decision's
    reasoning."""
    rows, notes = base_frames()
    record = base_record()
    later = wa.later_same_target(record)
    chains: dict[tuple, list[int]] = {}
    for index, entry in enumerate(record):
        if entry["field"] == "reasoning":
            chains.setdefault(wa.target(entry), []).append(index)
    assert sum(map(len, chains.values())) == 17
    for (case, _, _), chain in chains.items():
        _, scenario, variable = case.split("__")
        decisions = [dict(e) for e in base_adjudications()]
        edited = notes.copy()
        if where == "record":
            (decision,) = [
                d
                for d in decisions
                if (d["scenario_id"], d["variable"]) == (scenario, variable)
            ]
            decision["reasoning"] = undo(
                decision["reasoning"], [record[i] for i in chain]
            )
        else:
            mask = (edited.scenario_id == scenario) & (edited.variable == variable)
            (at,) = edited.index[mask]
            body, sentence = wa.split_note(edited.loc[at, "case_annotation"])
            edited.loc[at, "case_annotation"] = body + undo(
                sentence, [record[i] for i in chain]
            )
        found = dict(base_dropped(wa.frame_source(rows, edited, decisions)))
        assert any(i in found for i in chain), (case, where)
        assert later[chain[0]] == [record[i] for i in chain[1:]]


# --- Refusals and states, on MOCK text ------------------------------------------------

MOCK_ENTRY = {
    "case_id": "us__scenario_mock__mock_output",
    "field": "annotation",
    "model": "mock-model",
    "old": "MOCK old wording",
    "new": "MOCK new wording",
    "reason": "MOCK",
}
MOCK_SENTENCE = (
    " Developer adjudication (2026-01-01): the judge (mock-judge) returned "
    "llm_error; adjudicated reference_engine_defect (mock). MOCK old wording."
)


def mock_frames(row_text: str, note_text: str = "MOCK note"):
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
            "case_annotation": [note_text],
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


def test_a_case_note_is_restored_in_its_body_and_keeps_its_sentence():
    """MOCK note whose adjudication sentence also holds the old text: the
    body is restored, the sentence (the decision's text) is not touched."""
    note = {k: v for k, v in MOCK_ENTRY.items() if k != "model"}
    note["field"] = "case_annotation"
    rows, notes = mock_frames("x", "Body: MOCK old wording." + MOCK_SENTENCE)
    _, out_notes, _, _ = wa.restore_frames(rows, notes, [note])
    assert out_notes.case_annotation[0] == "Body: MOCK new wording." + MOCK_SENTENCE
    source = wa.frame_source(*mock_frames("x", out_notes.case_annotation[0]))
    assert wa.entry_state(source(note)[0], note) == wa.APPLIED


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


def test_a_reasoning_entry_reads_the_record_and_the_sentence():
    """MOCK decision: a reasoning entry is published only when both the
    adjudication record and the case note's sentence hold its new text; a
    note without a sentence leaves it MISSING."""
    entry = {k: v for k, v in MOCK_ENTRY.items() if k != "model"}
    entry["field"] = "reasoning"
    decision = [{"scenario_id": "scenario_mock", "variable": "mock_output"}]
    new_sentence = MOCK_SENTENCE.replace("old", "new")
    for reasoning, note, states in [
        ("MOCK new wording.", "Body." + new_sentence, [wa.APPLIED, wa.APPLIED]),
        ("MOCK new wording.", "Body." + MOCK_SENTENCE, [wa.APPLIED, wa.REVERTED]),
        ("MOCK old wording.", "Body." + new_sentence, [wa.REVERTED, wa.APPLIED]),
        ("MOCK new wording.", "Body.", [wa.APPLIED, wa.MISSING]),
    ]:
        source = wa.frame_source(
            *mock_frames("x", note), [{**decision[0], "reasoning": reasoning}]
        )
        assert [wa.entry_state(t, entry) for t in source(entry)] == states


def test_entry_releases_refuses_an_unlisted_block():
    with pytest.raises(wa.WordingAmendmentError, match="list the release"):
        wa.entry_releases([*base_record(), MOCK_ENTRY], RELEASES_TO_20261111)


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
    data = json.loads(git_bytes(COMMIT_20261111, wa.ADJUDICATIONS_PATH))
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
    output stands in as release 20261111's files themselves, since the carry
    replaces each kept row's and note's text with the base's."""
    rows, notes = base_frames()
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

    serve_base(monkeypatch, driver, base_frames())
    unrestored = build(driver, decisions)
    assert tuple(driver.annotation_csv_text(f) for f in unrestored) == base_text()
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
    base payload's. Against restore_payload's base, an export built apart
    that carries the restoration passes, one missing a single restored row
    fails on that row's cell only, and one carrying none of it fails on all
    18 cells; so the next release passes restore_payload(live) as the base
    it compares."""
    us = base_snapshot()
    incumbents = {row["model"] for row in us["modelStats"]}
    five = {(c.split("__")[1], c.split("__")[2]) for c in FIVE_CASES}

    def trimmed() -> dict:
        predictions = json.loads(base_snapshot_text())["scenarioPredictions"]
        return {
            "countries": {
                "us": {
                    "scenarioPredictions": {
                        scenario: {
                            variable: cells
                            for variable, cells in variables.items()
                            if (scenario, variable) in five
                        }
                        for scenario, variables in predictions.items()
                        if any(s == scenario for s, _ in five)
                    }
                }
            }
        }

    base, _, _ = wa.restore_payload(trimmed(), the_14())
    export, _, _ = wa.restore_payload(trimmed(), the_14())
    assert driver.base_restoration_problems(export, base, incumbents) == []
    snap_row = next(e for e in the_14() if e["case_id"] == "us__scenario_045__snap")
    short, _, _ = wa.restore_payload(
        trimmed(), [e for e in the_14() if e is not snap_row]
    )
    assert driver.base_restoration_problems(short, base, incumbents, limit=100) == [
        f"scenarioPredictions scenario_045 snap {snap_row['model']} changed"
    ]
    problems = driver.base_restoration_problems(trimmed(), base, incumbents, limit=100)
    assert len(problems) == RESTORED_CELLS
    assert all(p.startswith("scenarioPredictions ") for p in problems)
