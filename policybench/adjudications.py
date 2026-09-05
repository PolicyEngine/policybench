"""Developer adjudications of judge verdicts.

The failure-audit judge may return a case as ``prompt_ambiguity`` or another
class outside the final set (``llm_error``, ``parse_contract_failure``). Such a
case is not publishable as-is: :mod:`policybench.annotation_validation` lists
its rows as unresolved. The developer resolves it by recording an adjudication
in ``annotations/<run>/<country>_adjudications.json`` beside the annotation
CSVs. Each entry keeps the judge's verdict verbatim next to the adjudicated
class and the reasoning, so the override stays auditable, and this module
applies the entries to the row annotations and case notes deterministically.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from policybench.annotation_taxonomy import (
    FAILURE_SOURCE_VALUES,
    FAILURE_SUBTYPE_VALUES,
)

CASE_KEY = ["country", "scenario_id", "variable"]
REQUIRED_FIELDS = (
    "country",
    "scenario_id",
    "variable",
    "judge_model",
    "judge_failure_source",
    "judge_failure_subtype",
    "adjudicated_failure_source",
    "adjudicated_failure_subtype",
    "adjudicated_on",
    "adjudicator",
    "reasoning",
)
FINAL_SOURCES = frozenset({"llm_error", "parse_contract_failure"})
# A developer may affirm a judge's (or override a judge's) verdict as prompt
# ambiguity only when the output is also removed from scoring for every model
# (see policybench.reference_exclusions); an ambiguous output is never scored.
AFFIRMABLE_WITH_EXCLUSION = frozenset({"prompt_ambiguity"})


class AdjudicationError(ValueError):
    """An adjudication file is malformed or does not match the annotations."""


def load_adjudications(path: Path) -> list[dict]:
    """Read and validate an adjudication file; an absent file means none."""
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    entries = payload.get("adjudications")
    if not isinstance(entries, list):
        raise AdjudicationError(f"{path}: 'adjudications' must be a list")
    seen: set[tuple[str, str, str]] = set()
    for entry in entries:
        missing = [field for field in REQUIRED_FIELDS if not entry.get(field)]
        if missing:
            raise AdjudicationError(f"{path}: entry missing {missing}: {entry}")
        adjudicated = entry["adjudicated_failure_source"]
        excluded = bool(entry.get("excluded_from_scoring", False))
        if adjudicated in AFFIRMABLE_WITH_EXCLUSION:
            if not excluded:
                raise AdjudicationError(
                    f"{path}: adjudicated_failure_source {adjudicated!r} requires "
                    "excluded_from_scoring: true (an ambiguous output is not scored)"
                )
        elif adjudicated not in FINAL_SOURCES:
            raise AdjudicationError(
                f"{path}: adjudicated_failure_source must be final, got {adjudicated!r}"
            )
        elif excluded:
            raise AdjudicationError(
                f"{path}: excluded_from_scoring is only valid with "
                f"prompt_ambiguity, got {adjudicated!r}"
            )
        for field in ("judge_failure_source",):
            if entry[field] not in FAILURE_SOURCE_VALUES:
                raise AdjudicationError(f"{path}: unknown {field} {entry[field]!r}")
        for field in ("judge_failure_subtype", "adjudicated_failure_subtype"):
            if entry[field] not in FAILURE_SUBTYPE_VALUES:
                raise AdjudicationError(f"{path}: unknown {field} {entry[field]!r}")
        key = tuple(entry[column] for column in CASE_KEY)
        if key in seen:
            raise AdjudicationError(f"{path}: duplicate adjudication for {key}")
        seen.add(key)
    return entries


_ADJUDICATION_MARKER = " Developer adjudication ("


def _strip_adjudication_sentence(note: str) -> str:
    """Drop a previously appended adjudication sentence so a revision replaces it."""
    index = note.find(_ADJUDICATION_MARKER)
    return note if index < 0 else note[:index]


def adjudication_sentence(entry: dict) -> str:
    """The sentence a case note carries once ``entry`` has been applied."""
    return (
        f" Developer adjudication ({entry['adjudicated_on']}): the judge "
        f"({entry['judge_model']}) returned {entry['judge_failure_source']}; "
        f"adjudicated {entry['adjudicated_failure_source']} "
        f"({entry['adjudicated_failure_subtype']}). {entry['reasoning']}"
    )


def _case_mask(frame: pd.DataFrame, entry: dict) -> pd.Series:
    mask = pd.Series(True, index=frame.index)
    for column in CASE_KEY:
        mask &= frame[column].astype(str) == str(entry[column])
    return mask


def apply_adjudications(
    rows: pd.DataFrame,
    cases: pd.DataFrame,
    adjudications: list[dict],
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """Return adjudicated copies of the row annotations and case notes.

    An adjudication is a case-level decision: every substantive row of the
    case (anything but a ``parse_contract_failure`` row, which stays a parse
    failure) takes the adjudicated source and subtype, so re-applying a
    revised record updates rows an earlier application already rewrote. The
    case note's ``case_failure_sources`` and
    ``case_failure_subtypes`` take the adjudicated class, and the case
    annotation gains a sentence recording the adjudication. The third return
    value reports what changed per adjudication.
    """
    rows = rows.copy()
    cases = cases.copy()
    report: list[dict] = []
    for entry in adjudications:
        row_mask = _case_mask(rows, entry) & (
            rows["failure_source"].astype(str) != "parse_contract_failure"
        )
        case_mask = _case_mask(cases, entry)
        if not case_mask.any():
            raise AdjudicationError(
                f"adjudication targets an unknown case: {[entry[c] for c in CASE_KEY]}"
            )
        before = rows.loc[row_mask, ["failure_source", "failure_subtype"]].copy()
        rows.loc[row_mask, "failure_source"] = entry["adjudicated_failure_source"]
        rows.loc[row_mask, "failure_subtype"] = entry["adjudicated_failure_subtype"]
        changed = int(
            (before != rows.loc[row_mask, ["failure_source", "failure_subtype"]])
            .any(axis=1)
            .sum()
        )
        cases.loc[case_mask, "case_failure_sources"] = entry[
            "adjudicated_failure_source"
        ]
        cases.loc[case_mask, "case_failure_subtypes"] = entry[
            "adjudicated_failure_subtype"
        ]
        sentence = adjudication_sentence(entry)
        notes = cases.loc[case_mask, "case_annotation"].astype(str)
        cases.loc[case_mask, "case_annotation"] = [
            _strip_adjudication_sentence(note).rstrip() + sentence for note in notes
        ]
        report.append(
            {
                "case": [entry[c] for c in CASE_KEY],
                "rows_rewritten": changed,
                "from": entry["judge_failure_source"],
                "to": entry["adjudicated_failure_source"],
            }
        )
    return rows, cases, report


def verify_adjudications_applied(
    rows: pd.DataFrame,
    cases: pd.DataFrame,
    adjudications: list[dict],
) -> None:
    """Raise unless the annotations agree with the complete adjudication record.

    For every entry: no row still carries the judge's non-final verdict; every
    substantive row of the case (anything but a parse failure) carries the
    adjudicated source and subtype; the case note carries the adjudicated
    source and subtype and the exact adjudication sentence, reasoning
    included. A revised record therefore fails verification until it is
    re-applied, and a record edited to disagree with the rows fails closed.
    """
    for entry in adjudications:
        key = [entry[c] for c in CASE_KEY]
        row_mask = _case_mask(rows, entry)
        case_mask = _case_mask(cases, entry)
        if not case_mask.any() or not row_mask.any():
            raise AdjudicationError(f"adjudicated case missing from annotations: {key}")
        case_rows = rows.loc[row_mask]
        stray = case_rows[
            case_rows["failure_source"].astype(str) == entry["judge_failure_source"]
        ]
        affirmed = entry["judge_failure_source"] == entry["adjudicated_failure_source"]
        if (
            entry["judge_failure_source"] not in FINAL_SOURCES
            and not affirmed
            and not stray.empty
        ):
            raise AdjudicationError(
                f"{len(stray)} rows of {key} still carry the judge's "
                f"{entry['judge_failure_source']} verdict"
            )
        substantive = case_rows[
            case_rows["failure_source"].astype(str) != "parse_contract_failure"
        ]
        off_source = substantive[
            substantive["failure_source"].astype(str)
            != entry["adjudicated_failure_source"]
        ]
        off_subtype = substantive[
            substantive["failure_subtype"].astype(str)
            != entry["adjudicated_failure_subtype"]
        ]
        if not off_source.empty or not off_subtype.empty:
            raise AdjudicationError(
                f"{len(off_source)} rows of {key} carry a source other than "
                f"{entry['adjudicated_failure_source']!r} and {len(off_subtype)} a "
                f"subtype other than {entry['adjudicated_failure_subtype']!r}"
            )
        sources = set(cases.loc[case_mask, "case_failure_sources"].astype(str))
        subtypes = set(cases.loc[case_mask, "case_failure_subtypes"].astype(str))
        if sources != {entry["adjudicated_failure_source"]} or subtypes != {
            entry["adjudicated_failure_subtype"]
        }:
            raise AdjudicationError(
                f"case note for {key} carries {sources}/{subtypes}, expected "
                f"{entry['adjudicated_failure_source']!r}/"
                f"{entry['adjudicated_failure_subtype']!r}"
            )
        sentence = adjudication_sentence(entry).strip()
        for note in cases.loc[case_mask, "case_annotation"].astype(str):
            if sentence not in note:
                raise AdjudicationError(
                    f"case note for {key} does not carry the recorded adjudication "
                    "sentence (revised record not re-applied?)"
                )


def excluded_case_keys(adjudications: list[dict]) -> set[tuple[str, str]]:
    """Cases the record removes from scoring (must equal the exclusion record)."""
    return {
        (str(e["scenario_id"]), str(e["variable"]))
        for e in adjudications
        if e.get("excluded_from_scoring")
    }
