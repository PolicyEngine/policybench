"""Record the verdicts release dashboard-data-20261014's adjudications name.

Adapted from scripts/date_musewonder_judge_verdicts.py. The Gemini 4 Argon
and Muse Spark 1.3 release restated the judge fields of every decision on a
case a new model re-opened (scripts/restate_gpt61sol_adjudications.py). It
rules nothing and installs no engine upgrade, so it adds no wave of
decisions. Run on the exported stage after the freeze, this script

- writes docs/argon/judge_verdicts_<release day>.json: for each committed
  decision on a re-opened case, the case's verdict in the stage, read from
  verdict.json and its sha256-bound verdict.meta.json, as release 20261013's
  did; and
- checks reference_audit/2026-09-28/verification/judge_verdicts.json against
  this release and rewrites it unchanged: releases 20261013 and 20261013b
  decided no wave, so no wave waits for the base commit to fill it, and this
  release adds none. A wave the record names beyond release 20261013b's is
  refused.

tests/test_adjudications.py reads both files on machines without the stage.
A second run on the same stage writes the same bytes.

    python scripts/date_argon_judge_verdicts.py --stage-dir STAGE
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import finish_argon as driver  # noqa: E402

# Named for the release tag's date (dashboard-data-YYYYMMDD).
OUT = ROOT / f"docs/argon/judge_verdicts_{driver.RELEASE_TAG[-8:]}.json"
EVIDENCE = ROOT / "reference_audit/2026-09-28/verification/judge_verdicts.json"
# Release 20261013b's waves: release 20261010's, since releases 20261013 and
# 20261013b decided none. Each already names the commit that published it.
BASE_WAVES = [
    "2026-09-05",
    "2026-09-22",
    "2026-09-29",
    "2026-10-05",
    "2026-10-06",
    "2026-10-10",
]


def case_id(entry: dict) -> str:
    return f"{entry['country']}__{entry['scenario_id']}__{entry['variable']}"


def bound_verdict(folder: Path) -> tuple[dict, dict]:
    raw = (folder / "verdict.json").read_bytes()
    meta = json.loads((folder / "verdict.meta.json").read_text())
    driver.require(
        meta["verdict_sha256"] == hashlib.sha256(raw).hexdigest(),
        f"{folder.name}: the sidecar does not bind this verdict",
    )
    return json.loads(raw), meta


def judge_disagreements(entry: dict, verdict: dict, meta: dict) -> list[str]:
    """Where a decision's judge fields depart from the verdict it names: the
    judge, the classes, the UTC day, and the reference flag. The flag may be
    set from an earlier run the verdict does not repeat, but only with its
    judge_reference_suspect_source saying so."""
    problems = []
    expected = {
        "judge_model": meta["judge_model_requested"],
        "judge_failure_source": verdict["case_failure_source"],
        "judge_failure_subtype": verdict["case_failure_subtype"],
    }
    for field, value in expected.items():
        if entry.get(field) != value:
            problems.append(f"{field} {entry.get(field)!r} != {value!r}")
    day = entry.get("judge_rejudged_on") or entry.get("judged_on_utc")
    if day != meta["judged_at_utc"][:10]:
        problems.append(
            f"judged on {day!r}, the verdict on {meta['judged_at_utc'][:10]}"
        )
    flagged, now = (
        bool(entry.get("judge_reference_suspect")),
        bool(verdict["reference_suspect"]),
    )
    if flagged != now and not (
        flagged and not now and entry.get("judge_reference_suspect_source")
    ):
        problems.append(f"reference flag {flagged} != the verdict's {now}")
    return problems


def committed_record() -> dict:
    return json.loads((driver.ANNOTATIONS / driver.ADJUDICATIONS).read_text())


def restatements(stage: Path, record: dict) -> dict:
    """The current verdict of each committed decision on a re-opened case."""
    reopened = {
        entry["case_id"]
        for entry in json.loads(driver.JUDGE_PROVENANCE.read_text())["verdicts"]
    }
    cases = {}
    for entry in record["adjudications"]:
        case = case_id(entry)
        if case not in reopened:
            continue
        verdict, meta = bound_verdict(stage / "audit" / "cases" / case)
        wrong = judge_disagreements(entry, verdict, meta)
        driver.require(
            not wrong, f"{case}: the decision does not name its verdict: {wrong}"
        )
        cases[case] = {
            "judge_model": meta["judge_model_requested"],
            "case_failure_source": verdict["case_failure_source"],
            "case_failure_subtype": verdict["case_failure_subtype"],
            "reference_suspect": bool(verdict["reference_suspect"]),
            "judged_at_utc": meta["judged_at_utc"],
            "verdict_sha256": meta["verdict_sha256"],
        }
    return {
        "note": (
            f"The verdicts release {driver.RELEASE_TAG}'s adjudication entries "
            "name on the cases a new model re-opened: for each committed "
            "decision on such a case, the case's verdict in the "
            "exported stage, read by scripts/date_argon_judge_verdicts.py "
            "from verdict.json and its sha256-bound verdict.meta.json. The "
            "verdict each restatement replaced is release 20261013b's entry (git show "
            f"{driver.BASE_COMMIT[:12]}:annotations/{driver.RUN_NAME}/"
            f"{driver.ADJUDICATIONS})."
        ),
        "release": driver.RELEASE_TAG,
        "base_commit": driver.BASE_COMMIT,
        "cases": dict(sorted(cases.items())),
    }


def new_waves(record: dict) -> list[str]:
    """The waves the record names beyond release 20261013b's. The release
    rules nothing and installs no engine upgrade, so there must be none."""
    waves = sorted(
        {e["adjudicated_on"] for e in record["adjudications"]} - set(BASE_WAVES)
    )
    driver.require(
        not waves,
        f"this release decides no wave, but the record names {waves}",
    )
    return waves


def base_wave_releases(waves: dict) -> dict:
    """Release 20261013b's waves alone, each naming the commit that published
    it: nothing waits to be filled."""
    driver.require(
        list(waves) == BASE_WAVES,
        "the evidence's waves are not release 20261013b's",
    )
    unfilled = [wave for wave in BASE_WAVES if waves[wave].get("commit") is None]
    driver.require(
        not unfilled,
        f"the evidence leaves release 20261013b's waves unfilled: {unfilled}",
    )
    return {wave: waves[wave] for wave in BASE_WAVES}


def updated_evidence(evidence: dict, record: dict) -> dict:
    """The evidence, checked against this release: its waves are release
    20261013b's, all published, and the record adds none. Nothing changes."""
    evidence = copy.deepcopy(evidence)
    waves = base_wave_releases(evidence["wave_releases"])
    new_waves(record)
    evidence["wave_releases"] = dict(sorted(waves.items()))
    return evidence


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    record = committed_record()
    OUT.write_text(json.dumps(restatements(args.stage_dir, record), indent=1) + "\n")
    evidence = updated_evidence(json.loads(EVIDENCE.read_text()), record)
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)} and {EVIDENCE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
