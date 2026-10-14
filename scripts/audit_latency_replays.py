"""Find the frozen board's households whose recorded latency is a cache replay.

Writes ``docs/latency_replay_audit/households.csv``: one row for every
household of the frozen US run whose first recorded response was served again
from the harness's disk response cache (``policybench/cache.py``), and for
every household whose rows sum to under a second without such evidence.
``docs/latency_replay_audit.md`` explains the result.

The evidence comes from artifacts that live outside the repository, so this
script runs only on the machine that holds them:

- the litellm disk caches (``--cache-dir``, repeatable). Each entry's sqlite
  ``store_time`` says when a response was first stored. Values are pickles; the
  script searches their bytes for response ids and never unpickles them.
- the supervised runner's spend ledgers (``*.spend.jsonl`` under
  ``--ledger-root``, repeatable), which record ``cache_hit`` per call. A ledger
  under a path containing ``smoke`` belongs to an onboarding smoke.
- smoke prediction files (CSV under a path containing ``smoke``) below the
  ledger roots, which keep each smoke response's id.

Two kinds of evidence need only the frozen predictions. OpenRouter ids
(``gen-<unix seconds>-...``) and OpenAI Responses ids (``resp_`` + 16 hex +
``00`` + 8 hex seconds) embed their creation time. On live households that
time falls within a few seconds of the row's ``request_started_at``. A
creation time more than a minute before the request began means the response
already existed when the request was sent.

A household counts as replayed when any evidence holds for its first recorded
response id. A full replay sums to under a second: every call came from the
cache. A partial replay sums to a second or more, so a later call in the
household (a repair, a retry round or another chunk) went to the provider.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from policybench.analysis import household_latency_seconds  # noqa: E402

FROZEN_PREDICTIONS = (
    ROOT
    / "paper"
    / "snapshot"
    / "20260501"
    / "runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace"
    / "predictions.csv.gz"
)
OUTPUT = ROOT / "docs" / "latency_replay_audit" / "households.csv"
# A response that existed this long before the request began was not generated
# for it. Live households sit within 4 seconds of their request start.
MARGIN_SECONDS = 60.0
# Every replayed household in the frozen run sums to under 0.12 s; the fastest
# live household (Gemini 3.5 Flash-Lite) takes 1.75 s.
FULL_REPLAY_SECONDS = 1.0

RESPONSE_ID = re.compile(
    rb"(gen-\d{10}-[A-Za-z0-9]{10,40}"
    rb"|chatcmpl-[A-Za-z0-9-]{8,80}"
    rb"|msg_[A-Za-z0-9]{10,60}"
    rb"|resp_[A-Za-z0-9]{20,80}"
    rb"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)
OPENROUTER_ID = re.compile(r"^gen-(\d{10})-")
OPENAI_ID = re.compile(r"^resp_[0-9a-f]{16}00([0-9a-f]{8})[0-9a-f]{24}$")

FIELDS = [
    "model",
    "scenario_id",
    "household_latency_seconds",
    "replay",
    "evidence",
    "source",
    "first_response_id",
    "request_started_at",
    "response_existed_at",
]


def provider_response_id(recorded: object) -> object:
    """The provider's own id; litellm wraps OpenAI Responses ids in base64."""
    if not isinstance(recorded, str) or not recorded.startswith("resp_"):
        return recorded
    try:
        decoded = base64.b64decode(recorded[5:] + "==").decode()
    except (ValueError, UnicodeDecodeError):
        return recorded
    match = re.search(r"response_id:(resp_[0-9a-f]+)", decoded)
    return match.group(1) if match else recorded


def id_created_at(response_id: object) -> float | None:
    """Creation time embedded in an OpenRouter or OpenAI Responses id."""
    if not isinstance(response_id, str):
        return None
    for pattern, base in ((OPENROUTER_ID, 10), (OPENAI_ID, 16)):
        match = pattern.match(response_id)
        if match:
            return float(int(match.group(1), base))
    return None


def cache_store_times(cache_dirs: list[Path]) -> dict[str, float]:
    """Earliest store time of a cache entry holding each response id."""
    stored: dict[str, float] = {}
    for cache_dir in cache_dirs:
        con = sqlite3.connect(f"file:{cache_dir / 'cache.db'}?mode=ro", uri=True)
        try:
            rows = con.execute("select store_time, filename, value from Cache")
            for store_time, filename, value in rows:
                if filename:
                    blob = (cache_dir / filename).read_bytes()
                else:
                    blob = bytes(value or b"")
                for match in set(RESPONSE_ID.findall(blob)):
                    key = match.decode()
                    if key not in stored or store_time < stored[key]:
                        stored[key] = float(store_time)
        finally:
            con.close()
    return stored


def ledger_records(roots: list[Path]) -> pd.DataFrame:
    records = []
    for root in roots:
        for path in root.rglob("*.spend.jsonl"):
            for line in path.read_text().splitlines():
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                record["_smoke"] = "smoke" in str(path)
                records.append(record)
    return pd.DataFrame(records)


def smoke_file_ids(roots: list[Path]) -> set[str]:
    ids: set[str] = set()
    for root in roots:
        for path in root.rglob("*.csv"):
            if "smoke" not in str(path):
                continue
            try:
                frame = pd.read_csv(
                    path,
                    usecols=lambda column: column == "provider_response_id",
                    low_memory=False,
                )
            except (ValueError, pd.errors.ParserError, UnicodeDecodeError):
                continue
            if "provider_response_id" in frame:
                ids.update(frame["provider_response_id"].dropna().astype(str))
    return ids


def build(
    predictions: pd.DataFrame,
    stored: dict[str, float],
    ledgers: pd.DataFrame,
    smoke_ids: set[str],
) -> list[dict]:
    latency = household_latency_seconds(predictions)
    grouped = predictions.groupby(["model", "scenario_id"], sort=True)
    first_id = grouped["provider_response_id"].first()
    started = grouped["request_started_at"].min()
    board_start = predictions.groupby("model")["request_started_at"].min()

    ledger_hit: set[str] = set()
    smoke_live: dict[str, float] = {}
    if not ledgers.empty:
        board = ledgers[~ledgers["_smoke"] & (ledgers["cache_hit"] == True)]  # noqa: E712
        ledger_hit = set(board["provider_response_id"].dropna())
        smoke = ledgers[ledgers["_smoke"] & (ledgers["cache_hit"] != True)]  # noqa: E712
        smoke_live = (
            smoke.dropna(subset=["provider_response_id"])
            .groupby("provider_response_id")["request_completed_at"]
            .min()
            .to_dict()
        )

    rows = []
    for (model, scenario), seconds in latency.items():
        if pd.isna(seconds):
            continue
        recorded = first_id.get((model, scenario))
        inner = provider_response_id(recorded)
        start = started.get((model, scenario))
        existed: dict[str, float] = {}
        if isinstance(inner, str) and inner in stored:
            existed["cache"] = stored[inner]
        created = id_created_at(inner)
        if created is not None:
            name = "openrouter_id" if inner.startswith("gen-") else "openai_id"
            existed[name] = created
        if recorded in smoke_live:
            existed["smoke_ledger"] = float(smoke_live[recorded])
        evidence = sorted(
            name
            for name, when in existed.items()
            if pd.notna(start) and when < start - MARGIN_SECONDS
        )
        if recorded in ledger_hit:
            evidence.append("spend_ledger")
        if recorded in smoke_ids:
            evidence.append("smoke_file")
        evidence = sorted(set(evidence))
        if not evidence and seconds >= FULL_REPLAY_SECONDS:
            continue
        if not evidence:
            replay, source = "untraced", "untraced"
        else:
            replay = "full" if seconds < FULL_REPLAY_SECONDS else "partial"
            earliest = min(existed.values()) if existed else None
            if "smoke_ledger" in evidence or "smoke_file" in evidence:
                source = "onboarding smoke"
            elif earliest is not None and earliest >= board_start[model]:
                source = "same run"
            else:
                source = "before the board rows"
        rows.append(
            {
                "model": model,
                "scenario_id": scenario,
                "household_latency_seconds": f"{seconds:.6f}",
                "replay": replay,
                "evidence": "+".join(evidence),
                "source": source,
                "first_response_id": recorded,
                "request_started_at": "" if pd.isna(start) else f"{start:.3f}",
                "response_existed_at": (
                    f"{min(existed.values()):.3f}" if existed else ""
                ),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--predictions", type=Path, default=FROZEN_PREDICTIONS)
    parser.add_argument("--cache-dir", type=Path, action="append", default=[])
    parser.add_argument("--ledger-root", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    predictions = pd.read_csv(args.predictions, low_memory=False)
    rows = build(
        predictions,
        cache_store_times(args.cache_dir),
        ledger_records(args.ledger_root),
        smoke_file_ids(args.ledger_root),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} households to {os.path.relpath(args.output, ROOT)}")


if __name__ == "__main__":
    main()
