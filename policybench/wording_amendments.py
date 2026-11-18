"""Which committed wording amendments are in force, and whether the committed
annotation files publish them.

``annotations/<run>/us_wording-amendments.json`` lists every wording-only
amendment a board release made to published annotation text: the case, the
field (a case note, one model's row annotation, or a decision's reasoning in
the adjudication record), the exact old text and its replacement. Each release
that made amendments appended them to the record as one block.

An amendment stays in force until a later release re-judges its case. The new
verdict then replaces the text the amendment corrected, and that release's own
amendments, if any, speak for the new text. While an amendment is in force,
the committed files must publish its new text and not its old.

Release dashboard-data-20261014 broke that for the 14 amendments release
dashboard-data-20261013b made (entries 856 to 869). Its driver rebuilt the text
of every case it kept from the case's verdict and replayed only its own stage's
amendments, and no gate compared a kept case's text with the record, so it and
every release since published the five cases' text without them.
``dropped_amendments`` finds the amendments in force that a set of committed
texts does not publish. ``restore_frames`` and ``restore_payload`` give the
next board release the restoration of the 14. docs/wording_amendments.md has
the trace and the steps for that release's driver.
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

ROOT = Path(__file__).resolve().parents[1]
RUN_LABEL = "us_full_run_20260612_policyengine_4_16_1_populace"
ANNOTATIONS = Path("annotations") / RUN_LABEL
RECORD_PATH = ANNOTATIONS / "us_wording-amendments.json"
ROW_ANNOTATIONS_PATH = ANNOTATIONS / "us_audit_row_annotations.csv"
CASE_NOTES_PATH = ANNOTATIONS / "us_case_notes.csv"
ADJUDICATIONS_PATH = ANNOTATIONS / "us_adjudications.json"
POINTER_PATH = Path("app/src/data.artifact.json")

# The fields an amendment may name, and where each one's text is published:
# the row annotations file (one model's row), the case notes file, and the
# adjudication record (a decision's reasoning).
TEXT_FIELDS = ("annotation", "case_annotation", "reasoning")


@dataclass(frozen=True)
class Release:
    """One board release from the record's first on, oldest first.

    ``amendments`` is how many entries it appended to the record.
    ``judge_provenance`` is the committed record of the verdicts it judged
    again (each names its ``case_id``), or None when it re-judged no case.
    """

    tag: str
    amendments: int
    judge_provenance: str | None


# Every board release since the record began, in publication order. A release
# that appends amendments or re-judges cases must be listed here, and the last
# entry must be the release app/src/data.artifact.json names: the tests hold
# the blocks to the record's length and the last tag to the pointer, so an
# unlisted release fails them rather than hiding a dropped amendment.
RELEASES: tuple[Release, ...] = (
    Release("dashboard-data-20260930", 394, "docs/gpt61sol/judge_provenance.json"),
    Release("dashboard-data-20261006", 0, None),
    Release("dashboard-data-20261010", 0, "docs/haiku55/judge_provenance.json"),
    Release("dashboard-data-20261013", 462, "docs/musewonder/judge_provenance.json"),
    Release(
        "dashboard-data-20261013b",
        14,
        "docs/release_20261013b/judge_provenance.json",
    ),
    Release("dashboard-data-20261014", 0, "docs/argon/judge_provenance.json"),
    Release("dashboard-data-20261027", 1578, "docs/terra/judge_provenance.json"),
    Release("dashboard-data-20261111", 0, "docs/fable52/judge_provenance.json"),
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


def load_record(root: Path = ROOT) -> list[dict]:
    """The record's entries, in order."""
    record = json.loads((root / RECORD_PATH).read_text(encoding="utf-8"))
    entries = record.get("amendments") if isinstance(record, dict) else None
    _require(isinstance(entries, list), f"{RECORD_PATH}: no amendments list")
    for index, entry in enumerate(entries):
        _require(
            isinstance(entry, dict) and entry.get("field") in TEXT_FIELDS,
            f"{RECORD_PATH} entry {index}: not an amendment of {TEXT_FIELDS}",
        )
        _require(
            ("model" in entry) == (entry["field"] == "annotation"),
            f"{RECORD_PATH} entry {index}: a row annotation names its model, "
            "and nothing else does",
        )
    return entries


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
    """Each release's re-judged cases, as case ids, from its judge provenance."""
    out: dict[str, frozenset[str]] = {}
    for release in releases:
        if release.judge_provenance is None:
            out[release.tag] = frozenset()
            continue
        data = json.loads((root / release.judge_provenance).read_text())
        out[release.tag] = frozenset(v["case_id"] for v in data["verdicts"])
    return out


def superseding_releases(
    record: Sequence[dict],
    root: Path = ROOT,
    releases: Sequence[Release] = RELEASES,
) -> list[str | None]:
    """For each entry, the first release after its own that re-judged its
    case, or None while the entry is in force."""
    tags = [r.tag for r in releases]
    rejudged = rejudged_cases(root, releases)
    out: list[str | None] = []
    for entry, tag in zip(record, entry_releases(record, releases), strict=True):
        later = tags[tags.index(tag) + 1 :]
        out.append(next((t for t in later if entry["case_id"] in rejudged[t]), None))
    return out


def target(entry: dict) -> tuple[str, str, str | None]:
    """Where an entry's text lives: its case, its field and, for a row
    annotation, its model."""
    return entry["case_id"], entry["field"], entry.get("model")


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
    NEITHER, or MISSING when there is no text.
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
# target (one row, one case note, or every payload cell carrying the note).
TextSource = Callable[[dict], list[str | None]]


def _case_key(case_id: str) -> tuple[str, str, str]:
    country, scenario, variable = case_id.split("__", 2)
    return country, scenario, variable


def frame_source(rows, notes, adjudications: Sequence[dict] = ()) -> TextSource:
    """Texts from the row annotations and case notes (frames or the parsed
    CSVs, with country, scenario_id, variable, model and annotation, and
    case_annotation) and the adjudication record's entries."""
    published_rows: dict[tuple, list[str]] = {}
    for r in _records(rows):
        key = (str(r["country"]), str(r["scenario_id"]), str(r["variable"]))
        published_rows.setdefault((*key, str(r["model"])), []).append(
            str(r["annotation"])
        )
    published_notes: dict[tuple, list[str]] = {}
    for r in _records(notes):
        key = (str(r["country"]), str(r["scenario_id"]), str(r["variable"]))
        published_notes.setdefault(key, []).append(str(r["case_annotation"]))
    reasoning: dict[tuple, list[str]] = {}
    for e in adjudications:
        key = (e.get("country", "us"), e["scenario_id"], e["variable"])
        reasoning.setdefault(key, []).append(str(e.get("reasoning", "")))

    def texts(entry: dict) -> list[str | None]:
        key = _case_key(entry["case_id"])
        if entry["field"] == "annotation":
            found = published_rows.get((*key, entry["model"]), [])
        elif entry["field"] == "case_annotation":
            found = published_notes.get(key, [])
        else:
            joined = reasoning.get(key)
            found = ["\n".join(joined)] if joined else []
        _require(len(found) <= 1, f"{entry['case_id']}: more than one text")
        return list(found) or [None]

    return texts


def payload_source(payload: dict) -> TextSource:
    """Texts from a dashboard payload's cells: a row annotation is its
    model's cell's ``annotation``, a case note is the ``caseAnnotation`` of
    every cell that carries it. The payload is the published wrapper (with
    ``countries``) or the country payload the snapshot stores. A reasoning
    entry has no cell text."""
    country = payload["countries"]["us"] if "countries" in payload else payload
    predictions = country["scenarioPredictions"]

    def texts(entry: dict) -> list[str | None]:
        _, scenario, variable = _case_key(entry["case_id"])
        cells = predictions.get(scenario, {}).get(variable, {})
        if entry["field"] == "annotation":
            cell = cells.get(entry["model"])
            return [None if cell is None else cell.get("annotation")]
        if entry["field"] == "case_annotation":
            found = [
                c["caseAnnotation"] for c in cells.values() if "caseAnnotation" in c
            ]
            return list(found) or [None]
        return []

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

    An entry is in force while no later release has re-judged its case
    (superseding_releases, or ``superseded`` when the caller computed it).
    Its later entries of the same target, which are then in force too, are
    undone first (entry_state). Every text the source gives for the target
    must publish it. A source that gives no text for a target (a payload,
    for a reasoning entry) does not count it.
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


def _records(frame) -> list[dict]:
    return frame.to_dict("records") if hasattr(frame, "to_dict") else list(frame)


def restore_frames(rows, notes, entries: Sequence[dict], *, reopened=frozenset()):
    """Copies of ``rows`` and ``notes`` with ``entries`` restored, and the
    entries restored and skipped.

    ``rows`` and ``notes`` are pandas frames shaped as the committed files
    are (or as a release driver's triage builds them): country, scenario_id,
    variable and model with annotation, and country, scenario_id and variable
    with case_annotation. Each entry must find exactly one row or note. An
    entry on a case in ``reopened`` is skipped and its text left as it is:
    the release judged that case again, so the new verdict's text replaces
    the text the entry corrected. Entries are applied in the order given.
    """
    rows, notes = rows.copy(), notes.copy()
    restored: list[dict] = []
    skipped: list[dict] = []
    for entry in entries:
        _require(
            entry["field"] in ("annotation", "case_annotation"),
            f"{entry['case_id']}: only a row annotation or a case note is restored",
        )
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
        frame.loc[index, entry["field"]] = restore_text(
            str(frame.loc[index, entry["field"]]),
            [entry],
            f"{entry['case_id']} {entry['field']} {entry.get('model') or ''}",
        )
        restored.append(entry)
    return rows, notes, restored, skipped


def restore_payload(payload: dict, entries: Sequence[dict], *, reopened=frozenset()):
    """``payload`` with ``entries`` restored in its cells, and the entries
    restored and skipped.

    A row annotation entry rewrites its model's cell's ``annotation``; a case
    note entry rewrites the ``caseAnnotation`` of every cell that carries it,
    and at least one must. The payload is the published wrapper (with
    ``countries``) or a country payload, and the result has the same shape.
    Only the dicts on the path to a changed cell are copied; the rest is
    shared with ``payload``. A case in ``reopened`` is skipped, as in
    restore_frames.
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
        _require(
            entry["field"] in ("annotation", "case_annotation"),
            f"{entry['case_id']}: only a row annotation or a case note is restored",
        )
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
            cells[model][field] = restore_text(
                cells[model][field], [entry], f"{entry['case_id']} {model} {field}"
            )
        restored.append(entry)
    return out, restored, skipped
