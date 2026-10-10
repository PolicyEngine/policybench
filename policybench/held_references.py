"""References an earlier check held against a model consensus.

The consensus trigger (``policybench.consensus``) reads no history. A cell
whose reference a check has already worked from the law and held is flagged
again on every later payload in which the same models still agree. This module
lets a reference-adversary pass list such a cell as checked and held, with the
consensus answer explained, and spend no case on it. It changes no score, no
reference and no exclusion; it only decides which flags get a case.

A held record names a cell, the prompt the models answered (by its sha256),
the reference value the check held, and each consensus answer the check
explained. It applies to a flag only while all of these are true:

1. the flag is for the record's cell;
2. the payload's prompt for that scenario is the one the check read, byte for
   byte. A scenario id is a position in a run, so the same id can name another
   household after a regeneration, and a reworded prompt is another question;
3. the flag's reference is the held value; and
4. each triggering cluster is one answer the record explains: every member's
   own answer matches the same explained answer.

"Is" and "matches" mean within ``HOLD_TOLERANCE``, a dollar, on an amount
output, and equal on an eligibility output. The bound belongs to the check,
not to the pass: the flags' own ``tolerance`` is never used, so a pass run at
a loose tolerance cannot stretch a record over an answer the check never
looked at. Members' own answers are compared, not the cluster's rounded key.

Otherwise the flag stays in the pass and is judged, and the report gives the
first reason that fails: ``prompt_changed``, ``reference_moved`` or
``unexplained_consensus``. A hold can therefore go stale, but it cannot cover
a prompt, a reference or a consensus answer that the check did not see.

The caller must check the flags against the payload they are applied with
(``policybench.reference_adversary.build_adversary_cases`` does): this module
takes a flag's reference and its members' answers from the flag.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
HELD_VERDICT = "reference_holds"
# Dollars. PolicyBench's exact-match tolerance: an answer within a dollar of
# another is, by the benchmark's own standard, the same answer.
HOLD_TOLERANCE = 1.0
# Why a record did not apply to its flagged cell, in the order they are tested.
NOT_APPLIED_REASONS = ("prompt_changed", "reference_moved", "unexplained_consensus")
_REQUIRED_TEXT = ("scenario_id", "variable", "checked_on", "evidence")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _finite(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def prompt_sha256(payload: dict, scenario_id: str) -> str | None:
    """The sha256 of the prompt the models answered for a scenario.

    This is ``scenarios[scenario_id].prompt.tool``: the preface, the household
    facts, every requested output's definition and the answer format. ``None``
    when the payload has no such prompt.
    """
    scenario = (payload.get("scenarios") or {}).get(scenario_id)
    prompt = ((scenario or {}).get("prompt") or {}).get("tool")
    if not isinstance(prompt, str) or not prompt:
        return None
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def validate_records(records: Any) -> list[dict]:
    """The records, or ``ValueError`` naming the first one that is malformed.

    Each record needs ``scenario_id``, ``variable``, ``prompt_sha256`` (64
    lowercase hex digits), a finite ``reference``, ``verdict``
    ``"reference_holds"``, ``checked_on``, ``evidence`` (where the check is
    written up) and a non-empty ``consensus`` list whose entries each give a
    finite ``answer`` and an ``explanation``. Other keys are kept as written.
    A cell may be listed once.
    """
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
        digest = record.get("prompt_sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ValueError(f"{where}: prompt_sha256 must be 64 lowercase hex digits")
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


def validate_held_references(document: Any) -> list[dict]:
    """The records of a held-references document, or ``ValueError``.

    The document is ``{"schema_version": 1, "records": [...]}``;
    ``validate_records`` gives the record schema.
    """
    if not isinstance(document, dict):
        raise ValueError("held references: the document is not a JSON object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"held references: schema_version must be {SCHEMA_VERSION}, "
            f"not {document.get('schema_version')!r}"
        )
    return validate_records(document.get("records"))


def load_held_references(path: Path | str) -> list[dict]:
    """Read and validate a held-references file."""
    return validate_held_references(json.loads(Path(path).read_text()))


def _is_binary(variable: str) -> bool:
    from policybench.spec import metric_type_for_output

    return metric_type_for_output(variable) == "binary"


def _same(a: float, b: float, exact: bool) -> bool:
    return a == b if exact else abs(a - b) <= HOLD_TOLERANCE


def _member_answers(cluster: dict) -> list[float] | None:
    """Each member's own answer, or ``None`` when the flag does not give one
    finite answer for every model it names."""
    models = cluster.get("models")
    predictions = cluster.get("predictions")
    if not isinstance(models, list) or not models or not isinstance(predictions, dict):
        return None
    answers = [predictions.get(model) for model in models]
    if not all(_finite(answer) for answer in answers):
        return None
    return [float(answer) for answer in answers]


def apply_held_references(
    flags: list[dict], records: list[dict], payload: dict
) -> tuple[list[dict], dict]:
    """Split consensus flags into those to judge and those already held.

    ``flags`` is the ``flags`` list of a consensus-flags report computed from
    ``payload``, a US dashboard payload, which supplies each scenario's
    prompt. Returns ``(kept, report)``. ``kept`` holds the flags that still
    need a case, in their original order. ``report`` has three lists, which
    together hold every record exactly once:

    - ``held``: a flagged cell the record covers, with each triggering
      cluster next to the explanation that covers it;
    - ``not_applied``: a flagged cell the record no longer covers, with the
      reason (``NOT_APPLIED_REASONS``); the flag stays in ``kept``;
    - ``not_flagged``: a record whose cell is not flagged here.

    No argument is modified. Raises ``ValueError`` for a malformed record, a
    cell flagged twice, or a flag with no triggering cluster.
    """
    by_cell = {(r["scenario_id"], r["variable"]): r for r in validate_records(records)}
    kept: list[dict] = []
    held: list[dict] = []
    not_applied: list[dict] = []
    flagged: set[tuple[str, str]] = set()
    for flag in flags:
        cell = (str(flag["scenario_id"]), str(flag["variable"]))
        if cell in flagged:
            raise ValueError(f"{cell[0]} {cell[1]}: flagged more than once")
        flagged.add(cell)
        if not flag.get("clusters"):
            raise ValueError(f"{cell[0]} {cell[1]}: the flag has no triggering cluster")
        record = by_cell.get(cell)
        if record is None:
            kept.append(flag)
            continue
        exact = _is_binary(cell[1])
        reference = float(flag["reference"])
        summary = {
            "scenario_id": cell[0],
            "variable": cell[1],
            "state": flag.get("state"),
            "reference": reference,
            "held_reference": float(record["reference"]),
            "trigger": list(flag.get("trigger", [])),
        }
        prompt = prompt_sha256(payload, cell[0])
        if prompt != record["prompt_sha256"]:
            kept.append(flag)
            not_applied.append(
                {
                    **summary,
                    "reason": "prompt_changed",
                    "prompt_sha256": prompt,
                    "record": record,
                }
            )
            continue
        if not _same(reference, float(record["reference"]), exact):
            kept.append(flag)
            not_applied.append(
                {**summary, "reason": "reference_moved", "record": record}
            )
            continue
        clusters = []
        unexplained = []
        for cluster in flag["clusters"]:
            answers = _member_answers(cluster)
            covering = None
            if answers is not None:
                covering = next(
                    (
                        entry
                        for entry in record["consensus"]
                        if all(
                            _same(answer, float(entry["answer"]), exact)
                            for answer in answers
                        )
                    ),
                    None,
                )
            listed = {
                "answer": float(cluster["answer"]),
                "n_models": int(cluster["n_models"]),
                "n_top": int(cluster.get("n_top", 0)),
                "models": list(cluster.get("models") or []),
                "predictions": dict(cluster.get("predictions") or {}),
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
