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
        if entry["adjudicated_failure_source"] not in FINAL_SOURCES:
            raise AdjudicationError(
                f"{path}: adjudicated_failure_source must be final, got "
                f"{entry['adjudicated_failure_source']!r}"
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

    Only rows whose ``failure_source`` equals the judge's recorded verdict are
    rewritten (a ``parse_contract_failure`` row in an adjudicated case stays a
    parse failure). The case note's ``case_failure_sources`` and
    ``case_failure_subtypes`` take the adjudicated class, and the case
    annotation gains a sentence recording the adjudication. The third return
    value reports what changed per adjudication.
    """
    rows = rows.copy()
    cases = cases.copy()
    report: list[dict] = []
    for entry in adjudications:
        row_mask = _case_mask(rows, entry) & (
            rows["failure_source"].astype(str) == entry["judge_failure_source"]
        )
        case_mask = _case_mask(cases, entry)
        if not case_mask.any():
            raise AdjudicationError(
                f"adjudication targets an unknown case: {[entry[c] for c in CASE_KEY]}"
            )
        rows.loc[row_mask, "failure_source"] = entry["adjudicated_failure_source"]
        rows.loc[row_mask, "failure_subtype"] = entry["adjudicated_failure_subtype"]
        cases.loc[case_mask, "case_failure_sources"] = entry[
            "adjudicated_failure_source"
        ]
        cases.loc[case_mask, "case_failure_subtypes"] = entry[
            "adjudicated_failure_subtype"
        ]
        sentence = (
            f" Developer adjudication ({entry['adjudicated_on']}): the judge "
            f"({entry['judge_model']}) returned {entry['judge_failure_source']}; "
            f"adjudicated {entry['adjudicated_failure_source']} "
            f"({entry['adjudicated_failure_subtype']}). {entry['reasoning']}"
        )
        marker = f"Developer adjudication ({entry['adjudicated_on']})"
        notes = cases.loc[case_mask, "case_annotation"].astype(str)
        cases.loc[case_mask, "case_annotation"] = [
            note if marker in note else note.rstrip() + sentence for note in notes
        ]
        report.append(
            {
                "case": [entry[c] for c in CASE_KEY],
                "rows_rewritten": int(row_mask.sum()),
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
    """Raise unless every adjudicated case carries its adjudicated class."""
    for entry in adjudications:
        row_mask = _case_mask(rows, entry)
        case_mask = _case_mask(cases, entry)
        if not case_mask.any() or not row_mask.any():
            raise AdjudicationError(
                f"adjudicated case missing from annotations: "
                f"{[entry[c] for c in CASE_KEY]}"
            )
        stray = rows.loc[
            row_mask
            & (rows["failure_source"].astype(str) == entry["judge_failure_source"])
        ]
        if entry["judge_failure_source"] not in FINAL_SOURCES and not stray.empty:
            raise AdjudicationError(
                f"{len(stray)} rows of {[entry[c] for c in CASE_KEY]} still carry "
                f"the judge's {entry['judge_failure_source']} verdict"
            )
        sources = set(cases.loc[case_mask, "case_failure_sources"].astype(str))
        if sources != {entry["adjudicated_failure_source"]}:
            raise AdjudicationError(
                f"case note for {[entry[c] for c in CASE_KEY]} carries {sources}, "
                f"expected {entry['adjudicated_failure_source']!r}"
            )
