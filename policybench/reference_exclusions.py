"""Reference outputs excluded from scoring because the reference is not determinate.

A benchmark output is scored only when its reference follows from the facts the
prompt states. When a reference instead depends on an engine input the
household facts never carried (so the prompt could not list it and the model
could not know it), the output is excluded from scoring for every model: no
model gains or loses from it. The record lives beside the reference CSV as
``reference_exclusions.json`` and travels with the run into the frozen
snapshot, where the manifest pins it.

Each entry names the output, the unlisted input, the alternative reading a
careful reader could take of the stated facts, and the reference under both
readings as recomputed with the engine version that produced the references.
Exclusion is symmetric: rows whose answer happened to match the frozen
reference leave the score along with rows that did not.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

FILENAME = "reference_exclusions.json"
REASON_CODES = frozenset({"reference_depends_on_unlisted_input"})
REQUIRED_FIELDS = (
    "scenario_id",
    "variable",
    "reason_code",
    "unlisted_input",
    "alternative_reading",
    "frozen_value",
    "alternative_value",
    "engine_version",
    "decided_on",
    "decided_by",
)


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
        missing = [
            field
            for field in REQUIRED_FIELDS
            if field not in entry or entry[field] in (None, "")
        ]
        if missing:
            raise ReferenceExclusionError(f"{path}: entry missing {missing}: {entry}")
        if entry["reason_code"] not in REASON_CODES:
            raise ReferenceExclusionError(
                f"{path}: unknown reason_code {entry['reason_code']!r}"
            )
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
