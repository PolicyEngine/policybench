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
- an entry that was not re-judged gets ``judged_on_utc``, the UTC day of the
  current verdict its judge fields name;
- each ``judge_previous`` item's ``judged_on`` becomes the UTC day of the
  case's previous verdict (the September 22c audit tree) when that verdict's
  judge model and classes (failure source and subtype) are the recorded ones;
  otherwise the field is renamed ``adjudicated_on``, which is what it holds.

A recorded judge flag must be the flag of the verdict its date names, or name
the earlier judge run that raised it. The September 22 wave kept the flags
every one of its judge runs raised (flagged_sept22_wave.json), and recorded
such a flag at the top level with ``judge_reference_suspect_source``. When a
later wave re-judged the case, that source moves with the flag: a dated
``judge_previous`` item whose verdict does not flag the reference gets its own
``judge_reference_suspect_source``, and a top-level source is dropped once the
current verdict raises the flag itself. A flag no run explains stops the
script.

Where a later wave replaced the verdict a decision reviewed without keeping it
(the September 22 audit re-judged ten cases the 2026-09-05 wave had decided),
``adjudicated_verdict`` records that verdict as the decision's own release
recorded it. The record's ``date_conventions`` states how the dates relate.

It changes nothing else and is idempotent. Run it on the stage, then rerun the
documented chain (triage, export, freeze), which copies the record into
``annotations/``. It also writes the evidence it read (each bound verdict's
judge, classes, flag, time and sha256) to --evidence-out, which the tests
check the record against.

Usage::

    python scripts/date_adds0928_judge_verdicts.py --stage-dir STAGE \\
        --previous-cases PATH/TO/unified_audit/audit/cases
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = "us_full_run_20260612_policyengine_4_16_1_populace"
RECORD = Path("annotations") / RUN / "us_adjudications.json"
VERIFICATION = ROOT / "reference_audit" / "2026-09-28" / "verification"
WAVE_FLAGS = VERIFICATION / "flagged_sept22_wave.json"
EVIDENCE = VERIFICATION / "judge_verdicts.json"

# The September 22c record's wording for a flag an earlier judge run raised
# (reference_audit/2026-09-22/scripts/build_records.py, FLAG_SOURCE_EARLIER_RUN).
FLAG_SOURCE_EARLIER_RUN = (
    "an earlier judge run in the 2026-09-22 wave (flagged_sept22_wave.json); "
    "the case's current verdict.json does not flag it"
)
ITEM_FLAG_SOURCE = (
    "an earlier judge run in the 2026-09-22 wave (flagged_sept22_wave.json); "
    "the verdict dated here does not flag it"
)

# Each earlier wave's decisions as first published: the adjudication record
# merged with the wave's release.
WAVE_RELEASES = {
    "2026-09-05": {
        "commit": "7db59dab0014ba5b92b84bd6077d21e06875e1a9",
        "release": "dashboard-data-20260905c",
        "pull_request": 164,
        "committed_on": "2026-09-05",
    },
    "2026-09-22": {
        "commit": "56844e2fa795e7cedc04cd3c34cfb4e67e6f08b5",
        "release": "dashboard-data-20260922",
        "pull_request": 174,
        "committed_on": "2026-09-23",
    },
    "2026-09-29": {
        "commit": None,
        "release": "dashboard-data-20260929",
        "pull_request": None,
        "committed_on": "2026-09-29",
    },
}

DATE_CONVENTIONS = (
    "adjudicated_on names the audit wave that made the decision (2026-09-05, "
    "2026-09-22 or 2026-09-29). It carries no time of day or time zone, and a "
    "wave's decisions were written up to the day its release was committed "
    "(2026-09-05, 2026-09-23 and 2026-09-29). judged_on_utc, judge_rejudged_on "
    "and each judge_previous item's judged_on are UTC days, read from the "
    "verdict's sidecar (verdict.meta.json judged_at_utc). The top-level judge "
    "fields name the case's verdict in this release's audit tree, dated by "
    "judge_rejudged_on when a later wave judged the case again and by "
    "judged_on_utc otherwise, and judge_previous keeps the verdict that re-judge "
    "replaced. A wave's own judge runs could finish after one of its decisions "
    "was first written, so a recorded verdict can postdate adjudicated_on up to "
    "its wave's release. A flag an earlier judge run raised stays recorded and "
    "names that run in judge_reference_suspect_source, at the top level or on "
    "the judge_previous item it belongs to. Where a later wave replaced the "
    "verdict a decision reviewed without keeping it, adjudicated_verdict gives "
    "that verdict as the decision's own release recorded it."
)


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


def _classes(verdict: dict) -> tuple[str, str]:
    return verdict["case_failure_source"], verdict["case_failure_subtype"]


def _evidence(tree: str, found: tuple[dict, dict]) -> dict:
    verdict, meta = found
    return {
        "tree": tree,
        "judge_model": _judge(meta),
        "case_failure_source": verdict["case_failure_source"],
        "case_failure_subtype": verdict["case_failure_subtype"],
        "reference_suspect": bool(verdict.get("reference_suspect")),
        "judged_at_utc": meta["judged_at_utc"],
        "verdict_sha256": meta["verdict_sha256"],
    }


def _set(entry: dict, field: str, value, case: str, changes: list[str]) -> None:
    if entry.get(field) != value:
        changes.append(f"{case}: {field} {entry.get(field)} -> {value}")
        entry[field] = value


def date_entries(
    entries: list[dict],
    current_cases: Path,
    previous_cases: Path,
    wave_flags: frozenset[str] | set[str] = frozenset(),
    evidence: dict | None = None,
) -> list[str]:
    """Rewrite the judge dates and flag sources in place; return one line per
    changed field. ``wave_flags`` holds "scenario_id:variable" keys the
    September 22 wave's judge runs flagged. ``evidence``, when given, collects
    each bound verdict the record's dates name, keyed by case."""
    changes: list[str] = []
    for entry in entries:
        case = f"{entry['country']}__{entry['scenario_id']}__{entry['variable']}"
        key = f"{entry['scenario_id']}:{entry['variable']}"
        current = _bound_verdict(current_cases / case)
        if current is None:
            raise SystemExit(f"{case}: no bound current verdict in the stage")
        verdict, meta = current
        if _judge(meta) != entry["judge_model"] or _classes(verdict) != (
            entry["judge_failure_source"],
            entry["judge_failure_subtype"],
        ):
            raise SystemExit(f"{case}: the stage verdict is not the recorded one")
        if evidence is not None:
            evidence.setdefault(case, {})["current"] = _evidence("stage", current)
        day = meta["judged_at_utc"][:10]
        previous = entry.get("judge_previous")
        if previous:
            if "judge_rejudged_on" not in entry:
                raise SystemExit(f"{case}: a judge_previous entry names no re-judge")
            for field in ("judge_rejudged_on", "judged_on_utc"):
                if field in entry:
                    _set(entry, field, day, case, changes)
        else:
            _set(entry, "judged_on_utc", day, case, changes)
        flagged = bool(entry.get("judge_reference_suspect"))
        if flagged != bool(verdict.get("reference_suspect")):
            # A flag the current verdict does not raise stays only with the
            # source naming the earlier run of the wave that raised it.
            if not (
                flagged
                and entry.get("judge_reference_suspect_source")
                and key in wave_flags
            ):
                raise SystemExit(f"{case}: the recorded flag is not the verdict's")
        elif "judge_reference_suspect_source" in entry:
            # The current verdict raises the flag itself, or no flag is kept.
            changes.append(f"{case}: judge_reference_suspect_source dropped")
            del entry["judge_reference_suspect_source"]

        found = _bound_verdict(previous_cases / case) if previous else None
        for item in previous or []:
            if "judged_on" not in item:
                continue
            matches = found is not None and (
                _judge(found[1]) == item["judge_model"]
                and _classes(found[0])
                == (item["judge_failure_source"], item["judge_failure_subtype"])
            )
            if not matches:
                changes.append(
                    f"{case}: judge_previous {item['judge_model']} judged_on "
                    "renamed adjudicated_on (no matching previous verdict)"
                )
                item["adjudicated_on"] = item.pop("judged_on")
                continue
            item_flag = bool(item.get("judge_reference_suspect"))
            verdict_flag = bool(found[0].get("reference_suspect"))
            if item_flag != verdict_flag:
                if not (item_flag and key in wave_flags):
                    raise SystemExit(
                        f"{case}: judge_previous records flag {item_flag}, its "
                        f"verdict says {verdict_flag}, and no earlier run raised it"
                    )
                if item.get("judge_reference_suspect_source") != ITEM_FLAG_SOURCE:
                    changes.append(
                        f"{case}: judge_previous judge_reference_suspect_source added"
                    )
                    item["judge_reference_suspect_source"] = ITEM_FLAG_SOURCE
            elif "judge_reference_suspect_source" in item:
                changes.append(
                    f"{case}: judge_previous judge_reference_suspect_source dropped"
                )
                del item["judge_reference_suspect_source"]
            day = found[1]["judged_at_utc"][:10]
            if item["judged_on"] != day:
                changes.append(
                    f"{case}: judge_previous {item['judge_model']} judged_on "
                    f"{item['judged_on']} -> {day}"
                )
                item["judged_on"] = day
            if evidence is not None:
                evidence.setdefault(case, {})["previous"] = _evidence(
                    "20260922c", found
                )
    return changes


def _recorded_verdicts(entry: dict) -> list[tuple[str, str, str]]:
    """(judge, failure source, subtype) of each verdict the entry records."""
    verdicts = [
        (
            entry["judge_model"],
            entry["judge_failure_source"],
            entry["judge_failure_subtype"],
        )
    ]
    for item in entry.get("judge_previous", []):
        verdicts.append(
            (
                item["judge_model"],
                item["judge_failure_source"],
                item["judge_failure_subtype"],
            )
        )
    return verdicts


def record_adjudicated_verdicts(
    entries: list[dict],
    published: dict[str, list[dict]],
    evidence: dict | None = None,
) -> list[str]:
    """Keep the verdict each decision reviewed where a later wave dropped it.

    ``published`` maps a wave date to the adjudication entries its release
    published. An entry of that wave whose published judge verdict (model,
    classes) is none of the verdicts the record now keeps gets
    ``adjudicated_verdict``: that verdict, its recorded day and the release.
    ``evidence``, when given, collects each published verdict, keyed by case.
    """
    changes: list[str] = []
    for entry in entries:
        wave = entry["adjudicated_on"]
        first = {
            (e["scenario_id"], e["variable"]): e for e in published.get(wave, [])
        }.get((entry["scenario_id"], entry["variable"]))
        if first is None:
            continue
        reviewed = (
            first["judge_model"],
            first["judge_failure_source"],
            first["judge_failure_subtype"],
        )
        if evidence is not None:
            case = f"{entry['country']}__{entry['scenario_id']}__{entry['variable']}"
            evidence.setdefault(case, {})["published"] = {
                "release": WAVE_RELEASES[wave]["release"],
                "commit": WAVE_RELEASES[wave]["commit"],
                "judge_model": reviewed[0],
                "case_failure_source": reviewed[1],
                "case_failure_subtype": reviewed[2],
                "judged_on_utc": first.get("judged_on_utc"),
            }
        if reviewed in _recorded_verdicts(entry):
            if "adjudicated_verdict" in entry:
                changes.append(
                    f"{entry['scenario_id']}:{entry['variable']}: "
                    "adjudicated_verdict dropped"
                )
                del entry["adjudicated_verdict"]
            continue
        release = WAVE_RELEASES[wave]
        value = {
            "judge_model": reviewed[0],
            "judge_failure_source": reviewed[1],
            "judge_failure_subtype": reviewed[2],
            "judged_on": first["judged_on_utc"],
            "recorded_in": (
                f"{release['release']} (the adjudication record merged with "
                f"PR #{release['pull_request']}, commit {release['commit'][:10]})"
            ),
        }
        if entry.get("adjudicated_verdict") != value:
            changes.append(
                f"{entry['scenario_id']}:{entry['variable']}: adjudicated_verdict "
                f"{reviewed[0]} {first['judged_on_utc']}"
            )
            entry["adjudicated_verdict"] = value
    return changes


def published_records(root: Path = ROOT) -> dict[str, list[dict]]:
    """The adjudication entries each earlier wave's release published."""
    out = {}
    for wave, release in WAVE_RELEASES.items():
        if release["commit"] is None:
            continue
        raw = subprocess.run(
            ["git", "-C", str(root), "show", f"{release['commit']}:{RECORD}"],
            check=True,
            capture_output=True,
        ).stdout
        out[wave] = [
            e for e in json.loads(raw)["adjudications"] if e["adjudicated_on"] == wave
        ]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--previous-cases", type=Path, required=True)
    parser.add_argument("--wave-flags", type=Path, default=WAVE_FLAGS)
    parser.add_argument("--evidence-out", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    path = args.stage_dir / "publish" / RUN / "annotations" / "us_adjudications.json"
    record = json.loads(path.read_text())
    evidence: dict[str, dict] = {}
    changes = date_entries(
        record["adjudications"],
        args.stage_dir / "audit" / "cases",
        args.previous_cases,
        frozenset(json.loads(args.wave_flags.read_text())),
        evidence,
    )
    changes += record_adjudicated_verdicts(
        record["adjudications"], published_records(), evidence
    )
    if record.get("date_conventions") != DATE_CONVENTIONS:
        changes.append("date_conventions set")
    # Keep the record's key order: the conventions follow the note.
    record = {
        key: value
        for key, value in {
            "schema_version": record["schema_version"],
            "note": record["note"],
            "date_conventions": DATE_CONVENTIONS,
            **record,
        }.items()
    }
    record["date_conventions"] = DATE_CONVENTIONS
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    args.evidence_out.write_text(
        json.dumps(
            {
                "note": (
                    "The verdicts the adjudication record's judge dates and flags "
                    "name, read by scripts/date_adds0928_judge_verdicts.py from "
                    "each case's verdict.json and its sha256-bound "
                    "verdict.meta.json. 'current' is the case's verdict in the "
                    "release's audit tree (the stage); 'previous' is the verdict a "
                    "judge_previous item dates, from the September 22c audit tree; "
                    "'published' is the judge verdict the decision's own wave "
                    "release recorded (git show <commit>:" + str(RECORD) + ")."
                ),
                "wave_releases": WAVE_RELEASES,
                "cases": dict(sorted(evidence.items())),
            },
            indent=2,
            sort_keys=False,
        )
        + "\n"
    )
    for line in changes:
        print(line)
    print(f"{len(changes)} changes in {path}")


if __name__ == "__main__":
    main()
