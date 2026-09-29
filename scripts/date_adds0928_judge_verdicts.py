"""Date the judge verdicts the September 29 adjudication record keeps.

The upgrade's refresh of the staged ``us_adjudications.json`` moved each
re-judged entry's replaced judge class under ``judge_previous`` and gave it a
``judged_on`` equal to the entry's ``adjudicated_on``. For some entries that
paired claude-opus-5-5 with a date before Opus 5.5 judged anything. It also
left the entry's own ``judged_on_utc`` at the replaced verdict's date and
recorded the re-judge as ``judge_rejudged_on`` 2026-09-28, the local date of a
run whose verdicts carry 2026-09-29 UTC timestamps.

This script takes every date from the verdict sidecars (``verdict.meta.json``,
bound to its ``verdict.json`` by sha256):

- a re-judged entry's ``judge_rejudged_on``, and its ``judged_on_utc`` where it
  has one, become the UTC day of the case's current verdict in the stage;
- each ``judge_previous`` item's ``judged_on`` becomes the UTC day of the
  case's previous verdict (the September 22c audit tree) when that verdict's
  judge model and classes (failure source and subtype) are the recorded ones;
  otherwise the field is renamed ``adjudicated_on``, which is what it holds.

It changes nothing else and is idempotent. Run it on the stage, then rerun the
documented chain (triage, export, freeze), which copies the record into
``annotations/``.

Usage::

    python scripts/date_adds0928_judge_verdicts.py --stage-dir STAGE \\
        --previous-cases PATH/TO/unified_audit/audit/cases
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

RUN = "us_full_run_20260612_policyengine_4_16_1_populace"


def _bound_verdict(case_dir: Path) -> tuple[dict, dict] | None:
    """(verdict, sidecar) when the sidecar is bound to the verdict by sha256."""
    verdict_path = case_dir / "verdict.json"
    meta_path = case_dir / "verdict.meta.json"
    if not verdict_path.is_file() or not meta_path.is_file():
        return None
    meta = json.loads(meta_path.read_text())
    blob = verdict_path.read_bytes()
    if meta.get("verdict_sha256") != hashlib.sha256(blob).hexdigest():
        return None
    return json.loads(blob), meta


def _judge(meta: dict) -> str:
    """The judge model a sidecar names, as the adjudication record spells it."""
    requested = meta.get("judge_model_requested", "")
    reported = meta.get("judge_model_reported") or []
    if requested in {"opus", "claude-opus-5"} and "claude-opus-5" in reported:
        return "claude-opus-5"
    return requested


def date_entries(
    entries: list[dict], current_cases: Path, previous_cases: Path
) -> list[str]:
    """Rewrite the judge dates in place; return one line per change."""
    changes: list[str] = []
    for entry in entries:
        previous = entry.get("judge_previous")
        if not previous:
            continue
        case = f"{entry['country']}__{entry['scenario_id']}__{entry['variable']}"
        current = _bound_verdict(current_cases / case)
        if current is None:
            raise SystemExit(f"{case}: no bound current verdict in the stage")
        verdict, meta = current
        if _judge(meta) != entry["judge_model"] or (
            verdict["case_failure_source"],
            verdict["case_failure_subtype"],
        ) != (entry["judge_failure_source"], entry["judge_failure_subtype"]):
            raise SystemExit(f"{case}: the stage verdict is not the recorded one")
        day = meta["judged_at_utc"][:10]
        for field in ("judge_rejudged_on", "judged_on_utc"):
            if field in entry and entry[field] != day:
                changes.append(f"{case}: {field} {entry[field]} -> {day}")
                entry[field] = day
        if "judge_rejudged_on" not in entry:
            raise SystemExit(f"{case}: a judge_previous entry names no re-judge")
        found = _bound_verdict(previous_cases / case)
        for item in previous:
            if "judged_on" not in item:
                continue
            matches = found is not None and (
                _judge(found[1]) == item["judge_model"]
                and (
                    found[0]["case_failure_source"],
                    found[0]["case_failure_subtype"],
                )
                == (item["judge_failure_source"], item["judge_failure_subtype"])
            )
            if matches:
                day = found[1]["judged_at_utc"][:10]
                if item["judged_on"] != day:
                    changes.append(
                        f"{case}: judge_previous {item['judge_model']} judged_on "
                        f"{item['judged_on']} -> {day}"
                    )
                    item["judged_on"] = day
            else:
                changes.append(
                    f"{case}: judge_previous {item['judge_model']} judged_on "
                    "renamed adjudicated_on (no matching previous verdict)"
                )
                item["adjudicated_on"] = item.pop("judged_on")
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--previous-cases", type=Path, required=True)
    args = parser.parse_args()
    path = args.stage_dir / "publish" / RUN / "annotations" / "us_adjudications.json"
    record = json.loads(path.read_text())
    changes = date_entries(
        record["adjudications"], args.stage_dir / "audit" / "cases", args.previous_cases
    )
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    for line in changes:
        print(line)
    print(f"{len(changes)} changes in {path}")


if __name__ == "__main__":
    main()
