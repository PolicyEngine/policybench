"""Which committed wording amendments are in force, and whether the committed
annotation files publish them.

``annotations/<run>/us_wording-amendments.json`` lists the wording amendments
board releases from dashboard-data-20260930 on made to published audit text:
the case, the field (one model's row annotation, a case note, or a decision's
reasoning in the adjudication record), the exact old text and its
replacement. Each release that made amendments appended them as one block.
(Release dashboard-data-20261006's whole-field rewrites are in two other
records, docs/release_20261006/annotation_rewrites.json and
reference_audit/2026-10-05-medicaid-031-annotations/rewrites.json. Its 342 on
audit text are on cases release 20261010 re-judged; its 9 on the reference
explanations stay in force, and the drivers hold that file to the base
release's bytes.)

A row annotation or case note amendment stays in force until a later release
re-judges its case: the new verdict then replaces the text it corrected, and
that release's own amendments, if any, speak for the new text. A reasoning
amendment stays in force while the adjudication record holds the decision: a
re-judge changes a decision's reasoning only through listed amendments, and
the case note's adjudication sentence restates it. While an amendment is in
force, the committed files must publish its new text and not its old.

Release dashboard-data-20261014 broke that for the 14 amendments release
dashboard-data-20261013b made (entries 856 to 869). Its driver rebuilt the text
of every case it kept from the case's verdict and replayed only its own stage's
amendments, and no gate compared a kept case's text with the record, so it and
every release since published the five cases' text without them.
``dropped_amendments`` finds the amendments in force that a set of committed
texts does not publish. ``restore_frames``, ``restore_csv_texts`` and
``restore_payload`` give the next board release the restoration of the 14.
docs/wording_amendments.md has the trace and the steps for that release's
driver.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from policybench.adjudications import _ADJUDICATION_MARKER

ROOT = Path(__file__).resolve().parents[1]
RUN_LABEL = "us_full_run_20260612_policyengine_4_16_1_populace"
ANNOTATIONS = Path("annotations") / RUN_LABEL
RECORD_PATH = ANNOTATIONS / "us_wording-amendments.json"
ROW_ANNOTATIONS_PATH = ANNOTATIONS / "us_audit_row_annotations.csv"
CASE_NOTES_PATH = ANNOTATIONS / "us_case_notes.csv"
ADJUDICATIONS_PATH = ANNOTATIONS / "us_adjudications.json"
POINTER_PATH = Path("app/src/data.artifact.json")

# The fields an amendment may name, and where each one's text is published:
# the row annotations file (one model's row), the body of the case note (its
# text before any adjudication sentence), and the adjudication record (a
# decision's reasoning, which the case note's adjudication sentence restates).
TEXT_FIELDS = ("annotation", "case_annotation", "reasoning")


@dataclass(frozen=True)
class Release:
    """One board release from the record's first on, oldest first.

    ``amendments`` is how many entries it appended to the record.
    ``judge_provenance`` is the committed record of the verdicts it judged
    again (each names its ``case_id``), or None when it re-judged no case,
    and ``judge_provenance_sha256`` pins that file's bytes, so an edit to it
    cannot retire an amendment unseen.
    """

    tag: str
    amendments: int
    judge_provenance: str | None
    judge_provenance_sha256: str | None = None


# Every board release since the record began, in publication order. A release
# that appends amendments or re-judges cases must be listed here, and the last
# entry must be the release app/src/data.artifact.json names: the tests hold
# the blocks to the record's length, the last tag to the pointer and the
# listed provenance files to every one committed, so an unlisted release fails
# them rather than hiding a dropped amendment.
RELEASES: tuple[Release, ...] = (
    Release(
        "dashboard-data-20260930",
        394,
        "docs/gpt61sol/judge_provenance.json",
        "6f7ec329b93a39a8f6fd556c3a3c2f0dbba5d2be6dd31d14ea92a64e3acbb77b",
    ),
    Release("dashboard-data-20261006", 0, None),
    Release(
        "dashboard-data-20261010",
        0,
        "docs/haiku55/judge_provenance.json",
        "f0d0b32ffb0b045a5516fcdaa6c7536a0476023f270e57d7daad4c5355315715",
    ),
    Release(
        "dashboard-data-20261013",
        462,
        "docs/musewonder/judge_provenance.json",
        "8734eadc9fe2afb17ec09408b832be35c635d362d6249a3b20765c9446a61edc",
    ),
    Release(
        "dashboard-data-20261013b",
        14,
        "docs/release_20261013b/judge_provenance.json",
        "b07a270d9b0d081deec519805324f6326d3f9e69de4caaa3860a1409aff587e8",
    ),
    Release(
        "dashboard-data-20261014",
        0,
        "docs/argon/judge_provenance.json",
        "d03ad43ca15f5982293d34dfdc298960852aeab1ff1f8abb3b3e936a68998698",
    ),
    Release(
        "dashboard-data-20261027",
        1578,
        "docs/terra/judge_provenance.json",
        "e86bdc31f8f1c692c49e4166df2019f6ee96edad2c5032e8a7cfe80c0da3aa80",
    ),
    Release(
        "dashboard-data-20261111",
        0,
        "docs/fable52/judge_provenance.json",
        "16eef650f1873511b3e50436fc44880cdc22b54906b905403c8b7c0e8f3c2dd6",
    ),
)

# The 14 amendments release dashboard-data-20261013b made (record entries 856
# to 869, its whole block), which release dashboard-data-20261014 dropped and
# no release since has published. The sha256 is of the 14 entries as
# json.dumps(entries, sort_keys=True, ensure_ascii=False) spells them, so an
# edit to the record cannot change what the restoration applies.
DROPPED_BY_20261014 = tuple(range(856, 870))
DROPPED_BY_20261014_SHA256 = (
    "035b7e85e5592afae161de3fc3ee23c6e2af75bea6922fc1c766a76af45a134a"
)
# The releases whose committed files and payload publish the 14's old text.
# Closed: the tests pin it to these three, so no later release can join it.
PUBLISHED_WITHOUT_THE_14 = (
    "dashboard-data-20261014",
    "dashboard-data-20261027",
    "dashboard-data-20261111",
)

APPLIED = "APPLIED"
REVERTED = "REVERTED"
BOTH = "BOTH"
NEITHER = "NEITHER"
MISSING = "MISSING"


class WordingAmendmentError(ValueError):
    """A record, a text or a restoration that does not hold."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WordingAmendmentError(message)


def parse_record(record: dict, label: object = RECORD_PATH) -> list[dict]:
    """A wording amendments record's entries, in order, each checked to name
    a text field and, for a row annotation alone, a model."""
    entries = record.get("amendments") if isinstance(record, dict) else None
    _require(isinstance(entries, list), f"{label}: no amendments list")
    for index, entry in enumerate(entries):
        _require(
            isinstance(entry, dict) and entry.get("field") in TEXT_FIELDS,
            f"{label} entry {index}: not an amendment of {TEXT_FIELDS}",
        )
        _require(
            ("model" in entry) == (entry["field"] == "annotation"),
            f"{label} entry {index}: a row annotation names its model, "
            "and nothing else does",
        )
    return entries


def load_record(root: Path = ROOT) -> list[dict]:
    """The record's entries under ``root``, in order."""
    return parse_record(json.loads((root / RECORD_PATH).read_text(encoding="utf-8")))


def entry_releases(
    record: Sequence[dict], releases: Sequence[Release] = RELEASES
) -> list[str]:
    """Each entry's release tag, from the releases' block sizes in order."""
    tags = [r.tag for r in releases for _ in range(r.amendments)]
    _require(
        len(tags) == len(record),
        f"the releases' blocks cover {len(tags)} entries; the record holds "
        f"{len(record)}: list the release that appended the rest",
    )
    return tags


def rejudged_cases(
    root: Path = ROOT, releases: Sequence[Release] = RELEASES
) -> dict[str, frozenset[str]]:
    """Each release's re-judged cases, as case ids, from its judge provenance,
    each file checked against its pin."""
    out: dict[str, frozenset[str]] = {}
    for release in releases:
        if release.judge_provenance is None:
            out[release.tag] = frozenset()
            continue
        raw = (root / release.judge_provenance).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        _require(
            digest == release.judge_provenance_sha256,
            f"{release.judge_provenance} hashes to {digest}, not the "
            f"{release.judge_provenance_sha256} {release.tag} pins",
        )
        data = json.loads(raw)
        out[release.tag] = frozenset(v["case_id"] for v in data["verdicts"])
    return out


def superseding_releases(
    record: Sequence[dict],
    root: Path = ROOT,
    releases: Sequence[Release] = RELEASES,
) -> list[str | None]:
    """For each entry, the first release after its own that re-judged its
    case, or None while the entry is in force. A reasoning entry is never
    superseded by a re-judge (the module docstring says why): it stays in
    force, and a decision that leaves the record leaves it MISSING."""
    tags = [r.tag for r in releases]
    rejudged = rejudged_cases(root, releases)
    out: list[str | None] = []
    for entry, tag in zip(record, entry_releases(record, releases), strict=True):
        if entry["field"] == "reasoning":
            out.append(None)
            continue
        later = tags[tags.index(tag) + 1 :]
        out.append(next((t for t in later if entry["case_id"] in rejudged[t]), None))
    return out


def target(entry: dict) -> tuple[str, str, str | None]:
    """Where an entry's text lives: its case, its field and, for a row
    annotation, its model."""
    return entry["case_id"], entry["field"], entry.get("model")


def split_note(note: str) -> tuple[str, str]:
    """A case note's body (the text collect_audit writes) and its
    adjudication sentence (apply_adjudications' text, or "" when the case has
    no decision). Case note amendments name the body; a decision's reasoning
    is restated in the sentence."""
    index = note.find(_ADJUDICATION_MARKER)
    return (note, "") if index < 0 else (note[:index], note[index:])


def holds(text: str, entry: dict) -> tuple[bool, bool]:
    """Whether ``text`` holds ``entry``'s old text and its new text, each
    counted outside the other where one contains the other: an amendment
    that cuts words ("exactly 12% × $9,629 = $1,155.43" to "$1,155.43") has
    its new text inside its old, and one that adds words has its old inside
    its new."""
    old, new = entry["old"], entry["new"]
    if new in old:
        return old in text, new in text.replace(old, "\x00")
    return old in text.replace(new, "\x00"), new in text


def entry_state(text: str | None, entry: dict, later: Iterable[dict] = ()) -> str:
    """Whether ``text`` publishes ``entry``.

    ``later`` are the record's later entries of the same target, in record
    order. Each may rewrite part of this entry's new text with its context,
    so they are undone first, last first, each new text back to its old once
    where it occurs. Then (holds) APPLIED: the new text is there and the old
    is not; REVERTED: the old text is there and the new is not; BOTH,
    NEITHER, or MISSING when there is no text (the target's row, note or
    decision is gone).

    The test is presence in the target's text, not position: it cannot tell
    a dropped amendment whose new text the same field also holds elsewhere,
    and an old text that a later, unrelated edit puts back elsewhere in the
    field reads BOTH.
    """
    if text is None:
        return MISSING
    for item in reversed(list(later)):
        if item["new"] in text:
            text = text.replace(item["new"], item["old"], 1)
    has_old, has_new = holds(text, entry)
    if has_new and not has_old:
        return APPLIED
    if has_old and not has_new:
        return REVERTED
    return BOTH if has_old else NEITHER


# A source of published text: for an entry, every text that publishes its
# target (one row, one case note's body, a decision's reasoning and the
# sentence restating it, or every payload cell carrying one of those).
TextSource = Callable[[dict], list[str | None]]


def _case_key(case_id: str) -> tuple[str, str, str]:
    country, scenario, variable = case_id.split("__", 2)
    return country, scenario, variable


def frame_source(rows, notes, adjudications: Sequence[dict] = ()) -> TextSource:
    """Texts from the row annotations and case notes (frames or the parsed
    CSVs, with country, scenario_id, variable, model and annotation, and
    case_annotation) and the adjudication record's entries.

    A row annotation entry reads its row; a case note entry, the note's body;
    a reasoning entry, the record's reasoning for the case and the note's
    adjudication sentence (None when the note has none)."""
    published_rows: dict[tuple, list[str]] = {}
    for r in _records(rows):
        key = (str(r["country"]), str(r["scenario_id"]), str(r["variable"]))
        published_rows.setdefault((*key, str(r["model"])), []).append(
            str(r["annotation"])
        )
    published_notes: dict[tuple, list[tuple[str, str]]] = {}
    for r in _records(notes):
        key = (str(r["country"]), str(r["scenario_id"]), str(r["variable"]))
        published_notes.setdefault(key, []).append(
            split_note(str(r["case_annotation"]))
        )
    reasoning: dict[tuple, list[str]] = {}
    for e in adjudications:
        key = (e.get("country", "us"), e["scenario_id"], e["variable"])
        reasoning.setdefault(key, []).append(str(e.get("reasoning", "")))

    def texts(entry: dict) -> list[str | None]:
        key = _case_key(entry["case_id"])
        if entry["field"] == "annotation":
            found = published_rows.get((*key, entry["model"]), [])
            _require(len(found) <= 1, f"{entry['case_id']}: more than one row")
            return list(found) or [None]
        note = published_notes.get(key, [])
        _require(len(note) <= 1, f"{entry['case_id']}: more than one case note")
        if entry["field"] == "case_annotation":
            return [note[0][0] if note else None]
        decided = reasoning.get(key)
        return [
            "\n".join(decided) if decided else None,
            (note[0][1] or None) if note else None,
        ]

    return texts


def payload_source(payload: dict) -> TextSource:
    """Texts from a dashboard payload's cells: a row annotation is its
    model's cell's ``annotation``; a case note is the body of the
    ``caseAnnotation`` of every cell that carries one, and a decision's
    reasoning its adjudication sentence. The payload is the published wrapper
    (with ``countries``) or the country payload the snapshot stores."""
    country = payload["countries"]["us"] if "countries" in payload else payload
    predictions = country["scenarioPredictions"]

    def texts(entry: dict) -> list[str | None]:
        _, scenario, variable = _case_key(entry["case_id"])
        cells = predictions.get(scenario, {}).get(variable, {})
        if entry["field"] == "annotation":
            cell = cells.get(entry["model"])
            return [None if cell is None else cell.get("annotation")]
        notes = [
            split_note(c["caseAnnotation"])
            for c in cells.values()
            if "caseAnnotation" in c
        ]
        if entry["field"] == "case_annotation":
            return [body for body, _ in notes] or [None]
        return [sentence or None for _, sentence in notes] or [None]

    return texts


def committed_source(root: Path = ROOT) -> TextSource:
    """Texts from the committed row annotations, case notes and adjudication
    record under ``root``."""
    rows, notes = (
        list(csv.DictReader(io.StringIO((root / p).read_text(encoding="utf-8"))))
        for p in (ROW_ANNOTATIONS_PATH, CASE_NOTES_PATH)
    )
    record = json.loads((root / ADJUDICATIONS_PATH).read_text(encoding="utf-8"))
    return frame_source(rows, notes, record["adjudications"])


def later_same_target(record: Sequence[dict]) -> list[list[dict]]:
    """For each entry, the record's later entries of its target, in record
    order."""
    out: list[list[dict]] = [[] for _ in record]
    seen: dict[tuple, list[dict]] = {}
    for index in range(len(record) - 1, -1, -1):
        found = seen.setdefault(target(record[index]), [])
        out[index] = found[::-1]
        found.append(record[index])
    return out


def dropped_amendments(
    record: Sequence[dict],
    source: TextSource,
    root: Path = ROOT,
    releases: Sequence[Release] = RELEASES,
    *,
    superseded: Sequence[str | None] | None = None,
) -> list[tuple[int, str]]:
    """Each amendment in force that ``source`` does not publish, with its
    state (REVERTED, BOTH, NEITHER or MISSING), in record order.

    In force is superseding_releases' (or ``superseded``, when the caller
    computed it). An entry's later entries of the same target, in force
    whenever it is, are undone first (entry_state). Every text the source
    gives for the target must publish it.
    """
    if superseded is None:
        superseded = superseding_releases(record, root, releases)
    _require(len(superseded) == len(record), "one superseding release per entry")
    chains = later_same_target(record)
    out: list[tuple[int, str]] = []
    for index, entry in enumerate(record):
        if superseded[index] is not None:
            continue
        states = [entry_state(t, entry, chains[index]) for t in source(entry)]
        bad = next((s for s in states if s != APPLIED), None)
        if bad is not None:
            out.append((index, bad))
    return out


def known_dropped(tag: str) -> tuple[int, ...]:
    """The record entries release ``tag``'s committed files are known not to
    publish: the 14 for the three releases that published without them, and
    none for any other. A release after dashboard-data-20261111 must publish
    every amendment in force."""
    return DROPPED_BY_20261014 if tag in PUBLISHED_WITHOUT_THE_14 else ()


def dropped_by_20261014(record: Sequence[dict]) -> list[dict]:
    """The 14 entries to restore, checked against their pin."""
    entries = [record[i] for i in DROPPED_BY_20261014]
    digest = hashlib.sha256(
        json.dumps(entries, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    _require(
        digest == DROPPED_BY_20261014_SHA256,
        f"record entries {DROPPED_BY_20261014[0]} to {DROPPED_BY_20261014[-1]} "
        f"hash to {digest}, not the pinned {DROPPED_BY_20261014_SHA256}",
    )
    _require(
        all(e["field"] in ("annotation", "case_annotation") for e in entries),
        "a restoration names a row annotation or a case note only",
    )
    return entries


def restore_text(text: str, entries: Iterable[dict], label: str) -> str:
    """``text`` with each entry's old text, found exactly once and with its
    new text absent, replaced by the new text."""
    for entry in entries:
        _require(
            not holds(text, entry)[1],
            f"{label}: already holds the new text of {entry['case_id']} "
            f"{entry['field']}: {entry['new'][:80]!r}",
        )
        count = text.count(entry["old"])
        _require(
            count == 1,
            f"{label}: the old text occurs {count} times, not once: "
            f"{entry['old'][:80]!r}",
        )
        text = text.replace(entry["old"], entry["new"])
    return text


def _restore_field(text: str, entry: dict, label: str) -> str:
    """A row annotation, or a case note with the entry restored in its body
    and its adjudication sentence kept as it is."""
    if entry["field"] == "annotation":
        return restore_text(text, [entry], label)
    body, sentence = split_note(text)
    return restore_text(body, [entry], label) + sentence


def _records(frame) -> list[dict]:
    return frame.to_dict("records") if hasattr(frame, "to_dict") else list(frame)


def _restorable(entry: dict) -> None:
    _require(
        entry["field"] in ("annotation", "case_annotation"),
        f"{entry['case_id']}: only a row annotation or a case note is restored",
    )


def restore_frames(rows, notes, entries: Sequence[dict], *, reopened=frozenset()):
    """Copies of ``rows`` and ``notes`` with ``entries`` restored, and the
    entries restored and skipped.

    ``rows`` and ``notes`` are pandas frames shaped as the committed files
    are (or as a release driver's triage builds them): country, scenario_id,
    variable and model with annotation, and country, scenario_id and variable
    with case_annotation. Each entry must find exactly one row or note, and
    its old text exactly once in that row or in that note's body. An entry on
    a case in ``reopened`` is skipped and its text left as it is: the release
    judged that case again, so the new verdict's text replaces the text the
    entry corrected. Entries are applied in the order given.
    """
    rows, notes = rows.copy(), notes.copy()
    restored: list[dict] = []
    skipped: list[dict] = []
    for entry in entries:
        _restorable(entry)
        if entry["case_id"] in reopened:
            skipped.append(entry)
            continue
        country, scenario, variable = _case_key(entry["case_id"])
        frame = rows if entry["field"] == "annotation" else notes
        mask = (
            (frame["country"].astype(str) == country)
            & (frame["scenario_id"].astype(str) == scenario)
            & (frame["variable"].astype(str) == variable)
        )
        if entry["field"] == "annotation":
            mask &= frame["model"].astype(str) == entry["model"]
        _require(
            int(mask.sum()) == 1,
            f"{entry['case_id']} {entry['field']} "
            f"{entry.get('model') or ''}: {int(mask.sum())} rows, not one",
        )
        index = frame.index[mask][0]
        frame.loc[index, entry["field"]] = _restore_field(
            str(frame.loc[index, entry["field"]]),
            entry,
            f"{entry['case_id']} {entry['field']} {entry.get('model') or ''}",
        )
        restored.append(entry)
    return rows, notes, restored, skipped


def restore_csv_texts(
    rows_text: str, notes_text: str, entries: Sequence[dict], *, reopened=frozenset()
):
    """The row annotations and case notes files' text with ``entries``
    restored (restore_frames), each read with every cell as its text and
    written as triage writes it (``to_csv(index=False)``, which gives the
    committed files back byte for byte), and the entries restored and
    skipped."""
    import pandas as pd

    rows, notes = (
        pd.read_csv(io.StringIO(text), keep_default_na=False)
        for text in (rows_text, notes_text)
    )
    rows, notes, restored, skipped = restore_frames(
        rows, notes, entries, reopened=reopened
    )
    return rows.to_csv(index=False), notes.to_csv(index=False), restored, skipped


def restore_payload(payload: dict, entries: Sequence[dict], *, reopened=frozenset()):
    """``payload`` with ``entries`` restored in its cells, and the entries
    restored and skipped.

    A row annotation entry rewrites its model's cell's ``annotation``; a case
    note entry rewrites the body of the ``caseAnnotation`` of every cell that
    carries one, and at least one must. The payload is the published wrapper
    (with ``countries``) or a country payload, and the result has the same
    shape and key order. Only the dicts on the path to a changed cell are
    copied; the rest is shared with ``payload``. A case in ``reopened`` is
    skipped, as in restore_frames.
    """
    wrapped = "countries" in payload
    out = dict(payload)
    if wrapped:
        out["countries"] = dict(payload["countries"])
        country = out["countries"]["us"] = dict(payload["countries"]["us"])
    else:
        country = out
    country["scenarioPredictions"] = dict(country["scenarioPredictions"])
    predictions = country["scenarioPredictions"]
    restored: list[dict] = []
    skipped: list[dict] = []
    for entry in entries:
        _restorable(entry)
        if entry["case_id"] in reopened:
            skipped.append(entry)
            continue
        _, scenario, variable = _case_key(entry["case_id"])
        _require(
            variable in predictions.get(scenario, {}),
            f"{entry['case_id']}: no cells in the payload",
        )
        predictions[scenario] = dict(predictions[scenario])
        cells = predictions[scenario][variable] = dict(predictions[scenario][variable])
        if entry["field"] == "annotation":
            names = [entry["model"]] if entry["model"] in cells else []
            field = "annotation"
        else:
            names = [m for m, c in cells.items() if "caseAnnotation" in c]
            field = "caseAnnotation"
        _require(
            bool(names) and all(field in cells[m] for m in names),
            f"{entry['case_id']} {entry['field']} {entry.get('model') or ''}: "
            f"no cell carries {field}",
        )
        for model in names:
            cells[model] = copy.copy(cells[model])
            cells[model][field] = _restore_field(
                cells[model][field], entry, f"{entry['case_id']} {model} {field}"
            )
        restored.append(entry)
    return out, restored, skipped
