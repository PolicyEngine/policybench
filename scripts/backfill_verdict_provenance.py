"""Bind existing judge-provenance sidecars to the verdicts they describe.

Runners now write ``verdict.meta.json`` with the verdict's sha256 so the
freezer can tell a current sidecar from one left behind by a re-judged case.
Sidecars written before that field existed are bound here, and Codex-judged
cases that predate Codex sidecars get one from the ``codex.log`` header. A
sidecar is only bound when its recorded judging time sits within
``--tolerance`` seconds of the verdict file's modification time, so a sidecar
that cannot be shown to belong to the current verdict is left alone (the
freezer then falls back to ``codex.log`` or counts the case as unknown).

    uv run python scripts/backfill_verdict_provenance.py [--dry-run] [cases_dir]
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from freeze_snapshot import AUDIT_CASES_DIR  # noqa: E402


def _utc(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()


def backfill(cases_dir: Path, *, tolerance: float, dry_run: bool) -> dict[str, int]:
    counts = {"bound": 0, "codex_sidecar_written": 0, "left_alone": 0, "already": 0}
    for case_dir in sorted(cases_dir.iterdir()):
        verdict_path = case_dir / "verdict.json"
        if not verdict_path.is_file():
            continue
        digest = hashlib.sha256(verdict_path.read_bytes()).hexdigest()
        verdict_mtime = verdict_path.stat().st_mtime
        meta_path = case_dir / "verdict.meta.json"
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text())
            if meta.get("verdict_sha256"):
                counts["already"] += 1
                continue
            judged_at = datetime.datetime.fromisoformat(
                meta["judged_at_utc"]
            ).timestamp()
            if abs(judged_at - verdict_mtime) > tolerance:
                counts["left_alone"] += 1
                continue
            meta["verdict_sha256"] = digest
            meta.setdefault("judge_runner", "scripts/run_audit_claude.sh")
            if not dry_run:
                meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True))
            counts["bound"] += 1
            continue
        codex_log = case_dir / "codex.log"
        if codex_log.is_file():
            match = re.search(
                r"^model: (\S+)$",
                codex_log.read_text(encoding="utf-8", errors="replace"),
                re.M,
            )
            if not match:
                counts["left_alone"] += 1
                continue
            meta = {
                "judge_runner": "scripts/run_audit_codex.sh",
                "verdict_sha256": digest,
                "judge_model_requested": "default",
                "judge_model_reported": [match.group(1)],
                "judged_at_utc": _utc(verdict_mtime),
                "backfilled_from": "codex.log",
            }
            if not dry_run:
                meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True))
            counts["codex_sidecar_written"] += 1
            continue
        counts["left_alone"] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases_dir", nargs="?", default=str(AUDIT_CASES_DIR))
    parser.add_argument("--tolerance", type=float, default=600.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    counts = backfill(
        Path(args.cases_dir), tolerance=args.tolerance, dry_run=args.dry_run
    )
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
