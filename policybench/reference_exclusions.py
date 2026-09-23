"""Reference outputs excluded from scoring because the reference is not sound.

A benchmark output is scored only when its reference follows from the facts the
prompt states under the law for the benchmark year. Two cases fail that test,
and each output that fails is excluded from scoring for every model, so no
model gains or loses from it:

``reference_depends_on_unlisted_input``
    The reference depends on an engine input the household facts never
    carried, so the prompt could not list it and a careful reader could take
    the stated facts the other way. The entry names the unlisted input and the
    alternative reading, and records the reference under both readings.

``reference_engine_defect``
    The engine that produced the reference misapplies the law on facts the
    prompt does state. The entry names the root cause, the defect and the law,
    and records the frozen reference beside the corrected value, computed with
    the same engine version and a sandbox fix that implements the rule. It
    also points to the upstream issue or fix. A later reference version that
    uses a fixed engine brings the output back.

``reference_law_published_after_freeze``
    The reference depends on a law or official parameter published after the
    references were frozen, so the frozen value is the engine's projection
    and no model could have known the governing figure when it answered. The
    entry names what was published and when, and records the frozen
    projection beside the value under the published figure.

The record lives beside the reference CSV as ``reference_exclusions.json`` and
travels with the run into the frozen snapshot, where the manifest pins it.
Every entry carries ``alternative_reading`` and ``alternative_value``: for an
unlisted input they are the other reading and the reference under it; for an
engine defect they are the rule as the law states it and the corrected value;
for later-published law they are the published figure and the value under it.
Exclusion is symmetric: rows whose answer happened to match the frozen
reference leave the score along with rows that did not.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

FILENAME = "reference_exclusions.json"
UNLISTED_INPUT = "reference_depends_on_unlisted_input"
ENGINE_DEFECT = "reference_engine_defect"
LATER_LAW = "reference_law_published_after_freeze"
REASON_CODES = frozenset({UNLISTED_INPUT, ENGINE_DEFECT, LATER_LAW})
COMMON_FIELDS = (
    "scenario_id",
    "variable",
    "reason_code",
    "alternative_reading",
    "frozen_value",
    "alternative_value",
    "engine_version",
    "decided_on",
    "decided_by",
)
REQUIRED_FIELDS_BY_REASON = {
    UNLISTED_INPUT: COMMON_FIELDS + ("unlisted_input",),
    ENGINE_DEFECT: COMMON_FIELDS + ("root_cause", "defect", "law", "upstream"),
    LATER_LAW: COMMON_FIELDS + ("root_cause", "published", "law"),
}
# Kept for readers that predate the engine-defect reason code.
REQUIRED_FIELDS = REQUIRED_FIELDS_BY_REASON[UNLISTED_INPUT]


class ReferenceExclusionError(ValueError):
    """The exclusion record is malformed or disagrees with the references."""


def exclusions_path_for(reference_path: Path) -> Path:
    """The exclusion record that accompanies a reference CSV."""
    return Path(reference_path).with_name(FILENAME)


def load_reference_exclusions(path: Path) -> list[dict]:
    """Read and validate an exclusion record; an absent file means no exclusions."""
    path = Path(path)
    if path.is_dir():
        path = path / FILENAME
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    entries = payload.get("exclusions")
    if not isinstance(entries, list):
        raise ReferenceExclusionError(f"{path}: 'exclusions' must be a list")
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        if entry.get("reason_code") not in REASON_CODES:
            raise ReferenceExclusionError(
                f"{path}: unknown reason_code {entry.get('reason_code')!r}"
            )
        missing = [
            field
            for field in REQUIRED_FIELDS_BY_REASON[entry["reason_code"]]
            if field not in entry or entry[field] in (None, "")
        ]
        if missing:
            raise ReferenceExclusionError(f"{path}: entry missing {missing}: {entry}")
        try:
            frozen = float(entry["frozen_value"])
            alternative = float(entry["alternative_value"])
        except (TypeError, ValueError) as exc:
            raise ReferenceExclusionError(
                f"{path}: non-numeric values: {entry}"
            ) from exc
        if abs(frozen - alternative) <= 1e-6:
            raise ReferenceExclusionError(
                f"{path}: {entry['scenario_id']}/{entry['variable']} has the same "
                "reference under both readings; it is not excludable"
            )
        key = (str(entry["scenario_id"]), str(entry["variable"]))
        if key in seen:
            raise ReferenceExclusionError(f"{path}: duplicate exclusion for {key}")
        seen.add(key)
    return entries


def exclusion_basis(entry: dict) -> str:
    """What an exclusion turns on: the unlisted input or the engine root cause."""
    if entry["reason_code"] in (ENGINE_DEFECT, LATER_LAW):
        return str(entry["root_cause"])
    return str(entry["unlisted_input"])


def exclusion_keys(exclusions: list[dict]) -> set[tuple[str, str]]:
    return {(str(e["scenario_id"]), str(e["variable"])) for e in exclusions}


def exclusion_lookup(exclusions: list[dict]) -> dict[tuple[str, str], dict]:
    return {(str(e["scenario_id"]), str(e["variable"])): e for e in exclusions}


def verify_exclusions_against_reference(
    reference: pd.DataFrame, exclusions: list[dict]
) -> None:
    """Every excluded output must exist and carry the recorded frozen value."""
    if not exclusions:
        return
    indexed = reference.set_index(["scenario_id", "variable"])["value"]
    for entry in exclusions:
        key = (str(entry["scenario_id"]), str(entry["variable"]))
        if key not in indexed.index:
            raise ReferenceExclusionError(f"excluded output {key} is not a reference")
        if abs(float(indexed[key]) - float(entry["frozen_value"])) > 1e-3:
            raise ReferenceExclusionError(
                f"excluded output {key}: reference {float(indexed[key])} does not "
                f"match the recorded frozen_value {entry['frozen_value']}"
            )


def split_reference(
    reference: pd.DataFrame, exclusions: list[dict]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (scored reference, excluded reference rows)."""
    if not exclusions or reference.empty:
        return reference.reset_index(drop=True), reference.iloc[0:0].copy()
    verify_exclusions_against_reference(reference, exclusions)
    keys = exclusion_keys(exclusions)
    mask = pd.Series(
        [
            (str(s), str(v)) in keys
            for s, v in zip(reference["scenario_id"], reference["variable"])
        ],
        index=reference.index,
    )
    return (
        reference.loc[~mask].reset_index(drop=True),
        reference.loc[mask].reset_index(drop=True),
    )


def scored_reference_for(reference_path: Path) -> tuple[pd.DataFrame, list[dict]]:
    """Read a reference CSV and drop its excluded outputs."""
    reference = pd.read_csv(reference_path)
    exclusions = load_reference_exclusions(exclusions_path_for(reference_path))
    scored, _ = split_reference(reference, exclusions)
    return scored, exclusions
