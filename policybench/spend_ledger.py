"""Durable, de-duplicated accounting for physical provider calls."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

SPEND_LEDGER_SUFFIX = ".spend.jsonl"


def spend_ledger_path(output_path: str | Path) -> Path:
    """Return the provider-call ledger sidecar for an evaluation output."""
    return Path(f"{output_path}{SPEND_LEDGER_SUFFIX}")


def read_spend_ledger(path: str | Path) -> list[dict]:
    """Read valid JSON-object records, ignoring an interrupted final line."""
    path = Path(path)
    if not path.exists():
        return []
    records = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            logger.warning(
                "Ignoring invalid spend-ledger line %s in %s", line_number, path
            )
            continue
        if not isinstance(record, dict):
            logger.warning(
                "Ignoring non-object spend-ledger line %s in %s", line_number, path
            )
            continue
        records.append(record)
    return records


def count_budget_escalations(records: Iterable[dict]) -> int:
    """Count requests that moved to a larger completion budget."""
    return sum(
        record.get("escalated_from_budget_tokens") is not None for record in records
    )


def _deduplicate_records(records: Iterable[dict]) -> list[dict]:
    indexed: dict[str, dict] = {}
    for record in records:
        call_key = record.get("call_key")
        if not isinstance(call_key, str) or not call_key:
            raise ValueError("Spend-ledger records require a nonempty call_key.")
        existing = indexed.get(call_key)
        if existing is not None and (
            (
                existing.get("total_cost_usd") is not None
                and record.get("total_cost_usd") is None
            )
            or (
                existing.get("status") not in {"pending", "missing"}
                and record.get("status") in {"pending", "missing"}
            )
        ):
            # A transiently incomplete/error re-poll must not erase a prior
            # priced or terminal result for the same physical provider call.
            continue
        indexed[call_key] = record
    return list(indexed.values())


def replace_spend_ledger(path: str | Path, records: Iterable[dict]) -> Path:
    """Atomically replace a ledger with the exact de-duplicated record set."""
    path = Path(path)
    deduplicated = _deduplicate_records(records)

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
        for record in deduplicated
    )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(payload)
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return path


def upsert_spend_ledger(path: str | Path, records: Iterable[dict]) -> Path:
    """Atomically add call records, replacing duplicate stable call keys."""
    path = Path(path)
    return replace_spend_ledger(path, [*read_spend_ledger(path), *records])
