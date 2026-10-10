"""References an earlier check held against a model consensus.

The consensus trigger (``policybench.consensus``) reads no history. A cell
whose reference a check has already worked from the law and held is flagged
again on every later payload in which the same models still agree. This module
lets a reference-adversary pass list such a cell as checked and held, with the
consensus answer explained, and spend no case on it. It changes no score, no
reference and no exclusion; it only decides which flags get a case.

A held record names a cell, the reference value the check held, and each
consensus answer the check explained. It applies to a flag only while all of
these are true:

1. the flag is for the record's cell;
2. the flag's reference is the held value: within the flags' ``tolerance`` on
   an amount output, and equal on an eligibility output when
   ``binary_outputs`` is ``"mismatch"`` (the trigger's own two tests); and
3. every triggering cluster's answer is within the tolerance of an answer the
   record explains.

Otherwise the flag stays in the pass and is judged, and the report says why
the record did not apply: ``reference_moved`` (an engine or data change gave
the cell another reference, so the check no longer covers it) or
``unexplained_consensus`` (models now agree on an answer the check never
looked at). A hold can therefore go stale, but it cannot hide a new question.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
HELD_VERDICT = "reference_holds"
# Why a record did not apply to its flagged cell.
NOT_APPLIED_REASONS = ("reference_moved", "unexplained_consensus")
_REQUIRED_TEXT = ("scenario_id", "variable", "checked_on", "evidence")


def _finite(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_held_references(document: Any) -> list[dict]:
    """The records of a held-references document, or ``ValueError``.

    The document is ``{"schema_version": 1, "records": [...]}``. Each record
    needs ``scenario_id``, ``variable``, a finite ``reference``, ``verdict``
    ``"reference_holds"``, ``checked_on``, ``evidence`` (where the check is
    written up) and a non-empty ``consensus`` list whose entries each give a
    finite ``answer`` and an ``explanation``. Other keys are kept as written.
    A cell may be listed once.
    """
    if not isinstance(document, dict):
        raise ValueError("held references: the document is not a JSON object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"held references: schema_version must be {SCHEMA_VERSION}, "
            f"not {document.get('schema_version')!r}"
        )
    records = document.get("records")
    if not isinstance(records, list):
        raise ValueError("held references: records must be a list")
    seen: set[tuple[str, str]] = set()
    for index, record in enumerate(records):
        where = f"held references: record {index}"
        if not isinstance(record, dict):
            raise ValueError(f"{where} is not an object")
        for key in _REQUIRED_TEXT:
            if not _text(record.get(key)):
                raise ValueError(f"{where}: {key} must be a non-empty string")
        where = f"held references: {record['scenario_id']} {record['variable']}"
        if not _finite(record.get("reference")):
            raise ValueError(f"{where}: reference must be a finite number")
        if record.get("verdict") != HELD_VERDICT:
            raise ValueError(
                f"{where}: verdict must be {HELD_VERDICT!r}, "
                f"not {record.get('verdict')!r}"
            )
        consensus = record.get("consensus")
        if not isinstance(consensus, list) or not consensus:
            raise ValueError(f"{where}: consensus must be a non-empty list")
        for entry in consensus:
            if (
                not isinstance(entry, dict)
                or not _finite(entry.get("answer"))
                or not _text(entry.get("explanation"))
            ):
                raise ValueError(
                    f"{where}: each consensus entry needs a finite answer and "
                    "an explanation"
                )
        cell = (record["scenario_id"], record["variable"])
        if cell in seen:
            raise ValueError(f"{where}: listed more than once")
        seen.add(cell)
    return records


def load_held_references(path: Path | str) -> list[dict]:
    """Read and validate a held-references file."""
    return validate_held_references(json.loads(Path(path).read_text()))


def _is_binary(variable: str) -> bool:
    from policybench.spec import metric_type_for_output

    return metric_type_for_output(variable) == "binary"


def _same(a: float, b: float, exact: bool, tolerance: float) -> bool:
    return a == b if exact else abs(a - b) <= tolerance


def apply_held_references(
    flags: list[dict],
    records: list[dict],
    *,
    tolerance: float = 1.0,
    binary_outputs: str = "mismatch",
) -> tuple[list[dict], dict]:
    """Split consensus flags into those to judge and those already held.

    ``flags`` is the ``flags`` list of a consensus-flags report and
    ``tolerance`` and ``binary_outputs`` are that report's parameters.
    Returns ``(kept, report)``. ``kept`` holds the flags that still need a
    case, in their original order. ``report`` has three lists, which together
    hold every record exactly once:

    - ``held``: a flagged cell the record covers, with each triggering
      cluster next to the explanation that covers it;
    - ``not_applied``: a flagged cell the record no longer covers, with the
      reason (``NOT_APPLIED_REASONS``); the flag stays in ``kept``;
    - ``not_flagged``: a record whose cell is not flagged here.

    Neither argument is modified.
    """
    if not _finite(tolerance) or tolerance < 0:
        raise ValueError(
            f"tolerance must be a finite number of at least 0: {tolerance}"
        )
    by_cell = {(r["scenario_id"], r["variable"]): r for r in records}
    kept: list[dict] = []
    held: list[dict] = []
    not_applied: list[dict] = []
    flagged: set[tuple[str, str]] = set()
    for flag in flags:
        cell = (str(flag["scenario_id"]), str(flag["variable"]))
        if cell in flagged:
            raise ValueError(f"{cell[0]} {cell[1]}: flagged more than once")
        flagged.add(cell)
        record = by_cell.get(cell)
        if record is None:
            kept.append(flag)
            continue
        exact = binary_outputs == "mismatch" and _is_binary(cell[1])
        reference = float(flag["reference"])
        summary = {
            "scenario_id": cell[0],
            "variable": cell[1],
            "state": flag.get("state"),
            "reference": reference,
            "held_reference": float(record["reference"]),
            "trigger": list(flag.get("trigger", [])),
        }
        if not _same(reference, float(record["reference"]), exact, tolerance):
            kept.append(flag)
            not_applied.append(
                {**summary, "reason": "reference_moved", "record": record}
            )
            continue
        clusters = []
        unexplained = []
        for cluster in flag["clusters"]:
            answer = float(cluster["answer"])
            covering = next(
                (
                    entry
                    for entry in record["consensus"]
                    if _same(answer, float(entry["answer"]), exact, tolerance)
                ),
                None,
            )
            listed = {
                "answer": answer,
                "n_models": int(cluster["n_models"]),
                "n_top": int(cluster.get("n_top", 0)),
                "models": list(cluster.get("models", [])),
            }
            if covering is None:
                unexplained.append(listed)
            else:
                clusters.append(
                    {
                        **listed,
                        "explained_answer": float(covering["answer"]),
                        "explanation": covering["explanation"],
                    }
                )
        if unexplained:
            kept.append(flag)
            not_applied.append(
                {
                    **summary,
                    "reason": "unexplained_consensus",
                    "unexplained_clusters": unexplained,
                    "record": record,
                }
            )
            continue
        held.append({**summary, "clusters": clusters, "record": record})
    not_flagged = [
        {"scenario_id": cell[0], "variable": cell[1], "record": record}
        for cell, record in by_cell.items()
        if cell not in flagged
    ]
    return kept, {
        "held": held,
        "not_applied": not_applied,
        "not_flagged": not_flagged,
    }
