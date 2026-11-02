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
  whose path below its root contains ``smoke`` belongs to an onboarding smoke;
  the root's own path does not count.
- smoke prediction files (CSVs whose path below a ledger root contains
  ``smoke``), which keep each smoke response's id and request times.

Each kind of evidence is tied to the frozen request it explains, the
household's first call (the one whose id its rows keep):

- ``cache``: an entry holding the response id was stored before the request
  began. Both times are this machine's clock.
- ``spend_ledger``: a ledger outside the smokes records ``cache_hit`` for that
  response id on the same model and household, at the frozen request's own
  start time. A later run that replayed a response the board fetched live
  therefore does not count.
- ``smoke_ledger`` / ``smoke_file``: an onboarding smoke served the same
  response id and finished before the request began.
- ``openrouter_id`` / ``openai_id``: the frozen predictions alone suffice.
  OpenRouter ids (``gen-<unix seconds>-...``) and OpenAI Responses ids
  (``resp_`` + 16 hex + ``00`` + 8 hex seconds) embed their creation time, on
  the provider's clock. On live households that time falls within 23 seconds
  of the row's ``request_started_at``, so a creation time more than a minute
  before the request began means the response already existed.

A household counts as replayed when any evidence holds. A full replay sums to
under a second: every call came from the cache. A partial replay sums to a
second or more, so a later call in the household (another chunk, a repair, or
a re-request with a larger completion budget) went to the provider.
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
# for it. On live households an id's creation time sits within 23 seconds of
# the request start (OpenRouter; OpenAI ids within 4).
MARGIN_SECONDS = 60.0
# Every replayed household in the frozen run sums to under 0.12 s; the fastest
# live household (Gemini 3.5 Flash-Lite) takes 1.75 s.
FULL_REPLAY_SECONDS = 1.0
# A ledger record belongs to the frozen request when it starts at the same
# moment; the board's own ledger records it to the microsecond.
SAME_REQUEST_SECONDS = 0.5

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


# Trees that hold no run artifacts, skipped so a walk over a large review
# folder stays quick.
SKIP_DIRS = frozenset(
    {".git", ".venv", "venv", "node_modules", "site-packages", "__pycache__"}
)


def walk_files(root: Path, suffix: str):
    """Files under ``root`` ending in ``suffix``, skipping SKIP_DIRS."""
    for directory, subdirs, names in os.walk(root):
        subdirs[:] = [name for name in subdirs if name not in SKIP_DIRS]
        for name in names:
            if name.endswith(suffix):
                yield Path(directory) / name


def _under_smoke(path: Path, root: Path) -> bool:
    """Whether a file sits in a smoke run, judged below its root so a root
    whose own path mentions a smoke does not make every file a smoke's."""
    return "smoke" in str(path.relative_to(root))


def ledger_records(roots: list[Path]) -> pd.DataFrame:
    records = []
    for root in roots:
        for path in walk_files(root, ".spend.jsonl"):
            for line in path.read_text().splitlines():
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                record["_smoke"] = _under_smoke(path, root)
                records.append(record)
    return pd.DataFrame(records)


def smoke_file_times(roots: list[Path]) -> dict[str, float]:
    """When each smoke response was first served: the earliest completion time
    of a smoke row carrying its id. Rows without a time cannot show order and
    are skipped."""
    finished: dict[str, float] = {}
    wanted = {"provider_response_id", "request_completed_at"}
    for root in roots:
        for path in walk_files(root, ".csv"):
            if not _under_smoke(path, root):
                continue
            try:
                frame = pd.read_csv(
                    path, usecols=lambda column: column in wanted, low_memory=False
                )
            except (ValueError, pd.errors.ParserError, UnicodeDecodeError):
                continue
            if not wanted <= set(frame.columns):
                continue
            completed = pd.to_numeric(frame["request_completed_at"], errors="coerce")
            pairs = pd.DataFrame(
                {"id": frame["provider_response_id"], "completed": completed}
            ).dropna()
            for response_id, when in zip(pairs["id"], pairs["completed"]):
                key = str(response_id)
                if key not in finished or when < finished[key]:
                    finished[key] = float(when)
    return finished


def _ledger_hits(ledgers: pd.DataFrame) -> dict[str, list[tuple[str, str, float]]]:
    """Cache hits outside the smokes: response id -> (model, household, start)."""
    hits: dict[str, list[tuple[str, str, float]]] = {}
    if ledgers.empty or "cache_hit" not in ledgers:
        return hits
    board = ledgers[~ledgers["_smoke"] & (ledgers["cache_hit"] == True)]  # noqa: E712
    board = board.dropna(subset=["provider_response_id", "request_started_at"])
    columns = ["provider_response_id", "model", "scenario_id", "request_started_at"]
    for response_id, model, scenario, started in board[columns].itertuples(index=False):
        hits.setdefault(response_id, []).append((model, scenario, float(started)))
    return hits


def _smoke_ledger_times(ledgers: pd.DataFrame) -> dict[str, float]:
    """When a smoke first served each response id live."""
    if ledgers.empty or "cache_hit" not in ledgers:
        return {}
    smoke = ledgers[ledgers["_smoke"] & (ledgers["cache_hit"] != True)]  # noqa: E712
    return (
        smoke.dropna(subset=["provider_response_id", "request_completed_at"])
        .groupby("provider_response_id")["request_completed_at"]
        .min()
        .to_dict()
    )


def build(
    predictions: pd.DataFrame,
    stored: dict[str, float],
    ledgers: pd.DataFrame,
    smoke_times: dict[str, float],
) -> list[dict]:
    latency = household_latency_seconds(predictions)
    grouped = predictions.groupby(["model", "scenario_id"], sort=True)
    first_id = grouped["provider_response_id"].first()
    started = grouped["request_started_at"].min()
    board_start = predictions.groupby("model")["request_started_at"].min()
    ledger_hits = _ledger_hits(ledgers)
    smoke_ledger = _smoke_ledger_times(ledgers)

    rows = []
    for (model, scenario), seconds in latency.items():
        if pd.isna(seconds):
            continue
        recorded = first_id.get((model, scenario))
        inner = provider_response_id(recorded)
        start = started.get((model, scenario))
        timed = pd.notna(start)
        # When the response is known to have existed, by source and clock.
        local: dict[str, float] = {}
        if isinstance(inner, str) and inner in stored:
            local["cache"] = stored[inner]
        if recorded in smoke_ledger:
            local["smoke_ledger"] = float(smoke_ledger[recorded])
        if recorded in smoke_times:
            local["smoke_file"] = smoke_times[recorded]
        existed = {name: when for name, when in local.items() if timed and when < start}
        created = id_created_at(inner)
        if created is not None and timed and created < start - MARGIN_SECONDS:
            name = "openrouter_id" if inner.startswith("gen-") else "openai_id"
            existed[name] = created
        evidence = set(existed)
        if timed and any(
            hit_model == model
            and hit_scenario == scenario
            and abs(hit_start - start) <= SAME_REQUEST_SECONDS
            for hit_model, hit_scenario, hit_start in ledger_hits.get(recorded, ())
        ):
            evidence.add("spend_ledger")
        if not evidence and seconds >= FULL_REPLAY_SECONDS:
            continue
        if not evidence:
            replay, source = "untraced", "untraced"
        else:
            replay = "full" if seconds < FULL_REPLAY_SECONDS else "partial"
            earliest = min(existed.values()) if existed else None
            if {"smoke_ledger", "smoke_file"} & evidence:
                source = "onboarding smoke"
            elif earliest is None:
                source = "unknown"
            elif earliest >= board_start[model]:
                source = "same run"
            else:
                source = "before the board rows"
        rows.append(
            {
                "model": model,
                "scenario_id": scenario,
                "household_latency_seconds": f"{seconds:.6f}",
                "replay": replay,
                "evidence": "+".join(sorted(evidence)),
                "source": source,
                "first_response_id": recorded,
                "request_started_at": f"{start:.3f}" if timed else "",
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
        smoke_file_times(args.ledger_root),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} households to {os.path.relpath(args.output, ROOT)}")


if __name__ == "__main__":
    main()
