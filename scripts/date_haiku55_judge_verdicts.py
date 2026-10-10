"""Record the verdicts release dashboard-data-20261009's adjudications name.

The Claude Haiku 5.5 release restated the judge fields of every decision on a
case Claude Haiku 5.5 re-opened (scripts/restate_gpt61sol_adjudications.py),
dropped the decisions on records its engine upgrade regenerated, and added
two waves of decisions: the 2026-10-06 rulings' (d1022, d994) and the engine
upgrade's, on the outputs it newly excludes. Run on the exported stage after
the freeze, this script

- writes docs/haiku55/judge_verdicts_20261009.json: for each committed
  decision on a re-opened case, the case's verdict in the stage, read from
  verdict.json and its sha256-bound verdict.meta.json, as
  scripts/date_gpt61sol_judge_verdicts.py did for release 20260930; and
- brings reference_audit/2026-09-28/verification/judge_verdicts.json up to
  this release, as release 20261006's driver did
  (scripts/release_20261006.py build_evidence): the 2026-10-05 wave's release
  is now committed (the driver's BASE_COMMIT), so its decisions gain the
  verdicts that release published; this release's waves join, uncommitted,
  with the UTC day their decisions were written; and each decision of theirs,
  new or restated in place from an earlier wave, gains the stage verdict it
  reviewed in place of the earlier evidence.

tests/test_adjudications.py reads both files on machines without the stage.
A second run on the same stage writes the same bytes.

    python scripts/date_haiku55_judge_verdicts.py --stage-dir STAGE
"""

from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import finish_haiku55 as driver  # noqa: E402
from date_adds0928_judge_verdicts import _evidence  # noqa: E402

# Named for the release tag's date (dashboard-data-YYYYMMDD).
OUT = ROOT / f"docs/haiku55/judge_verdicts_{driver.RELEASE_TAG[-8:]}.json"
EVIDENCE = ROOT / "reference_audit/2026-09-28/verification/judge_verdicts.json"
# The wave release 20261006 decided, which this release's base commit froze.
FILL_WAVE = "2026-10-05"
# Release 20261006's waves, before this release's.
BASE_WAVES = ["2026-09-05", "2026-09-22", "2026-09-29", FILL_WAVE]


def case_id(entry: dict) -> str:
    return f"{entry['country']}__{entry['scenario_id']}__{entry['variable']}"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout


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
            "The verdicts release dashboard-data-20261009's adjudication entries "
            "name on the cases Claude Haiku 5.5 re-opened: for each committed "
            "decision on such a case, the case's verdict in the exported stage, "
            "read by scripts/date_haiku55_judge_verdicts.py from verdict.json and "
            "its sha256-bound verdict.meta.json. The verdict each restatement "
            "replaced is release 20261006's entry (git show "
            f"{driver.BASE_COMMIT[:12]}:annotations/{driver.RUN_NAME}/"
            f"{driver.ADJUDICATIONS})."
        ),
        "release": driver.RELEASE_TAG,
        "base_commit": driver.BASE_COMMIT,
        "cases": dict(sorted(cases.items())),
    }


def fill_release() -> dict:
    """The 2026-10-05 wave's release as committed: the base commit, its pull
    request (the squash subject's "(#N)") and its UTC commit day."""
    subject = git("show", "-s", "--format=%s", driver.BASE_COMMIT).strip()
    number = re.search(r"\(#(\d+)\)$", subject)
    driver.require(number is not None, f"{subject!r} names no pull request")
    when = datetime.datetime.fromisoformat(
        git("show", "-s", "--format=%cI", driver.BASE_COMMIT).strip()
    )
    return {
        "commit": driver.BASE_COMMIT,
        "release": "dashboard-data-20261006",
        "pull_request": int(number.group(1)),
        "committed_on": when.astimezone(datetime.timezone.utc).date().isoformat(),
    }


def upgrade_day() -> str | None:
    """The day of the committed sidecar's engine upgrade, if this release has one
    (the last revision, after release 20261006's 2026-09-29 move)."""
    meta = json.loads((driver.SNAPSHOT / "reference_outputs.csv.meta.json").read_text())
    last = meta["revisions"][-1]
    if last.get("kind") == "engine_upgrade" and last["date"] > BASE_WAVES[-1]:
        return last["date"]
    return None


def new_waves(record: dict, upgrade: str | None = None) -> dict[str, str]:
    """This release's waves and the UTC day each one's decisions were written
    (the spec's adjudications_written_on for the 2026-10-06 rulings, its
    upgrade_adjudications_written_on for the engine upgrade's wave). The waves
    must be the 2026-10-06 rulings' and, with an engine upgrade, its day."""
    spec = driver.load_spec()
    waves = sorted(
        {e["adjudicated_on"] for e in record["adjudications"]} - set(BASE_WAVES)
    )
    allowed = {"2026-10-06"} | ({upgrade} if upgrade else set())
    driver.require(
        "2026-10-06" in waves and set(waves) <= allowed,
        f"this release's waves are {waves}, not the 2026-10-06 rulings' and the "
        f"engine upgrade's ({sorted(allowed)})",
    )
    written = {}
    for wave in waves:
        if wave == "2026-10-06":
            written[wave] = spec["adjudications_written_on"]
        else:
            written[wave] = spec["upgrade_adjudications_written_on"]
        driver.require(wave <= written[wave], f"the {wave} wave was written before it")
    return written


def updated_evidence(evidence: dict, stage: Path, record: dict) -> dict:
    evidence = copy.deepcopy(evidence)
    waves = evidence["wave_releases"]
    driver.require(
        list(waves)[: len(BASE_WAVES)] == BASE_WAVES,
        "the evidence's waves are not release 20261006's",
    )
    fill = fill_release()
    if waves[FILL_WAVE].get("commit") is None:
        driver.require(
            waves[FILL_WAVE]["release"] == fill["release"],
            f"the {FILL_WAVE} wave is not release 20261006's",
        )
        waves[FILL_WAVE] = fill
    driver.require(
        waves[FILL_WAVE] == fill, f"the {FILL_WAVE} wave was filled otherwise"
    )
    published = json.loads(
        git(
            "show",
            f"{driver.BASE_COMMIT}:annotations/{driver.RUN_NAME}/{driver.ADJUDICATIONS}",
        )
    )["adjudications"]
    filled = 0
    for entry in published:
        if entry["adjudicated_on"] != FILL_WAVE:
            continue
        evidence["cases"][case_id(entry)]["published"] = {
            "release": fill["release"],
            "commit": fill["commit"],
            "judge_model": entry["judge_model"],
            "case_failure_source": entry["judge_failure_source"],
            "case_failure_subtype": entry["judge_failure_subtype"],
            "judged_on_utc": entry.get("judged_on_utc"),
        }
        filled += 1
    driver.require(filled > 0, f"release 20261006 published no {FILL_WAVE} decisions")
    for wave, written in new_waves(record, upgrade_day()).items():
        waves[wave] = {
            "commit": None,
            "release": driver.RELEASE_TAG,
            "pull_request": None,
            "adjudications_written_on": written,
        }
        for entry in record["adjudications"]:
            if entry["adjudicated_on"] == wave:
                case = case_id(entry)
                folder = stage / "audit" / "cases" / case
                # A decision this wave restated in place (the spec's
                # restated_adjudications) was an earlier wave's: its case's
                # evidence now describes this wave's decision, which no release
                # has published yet. The earlier release's evidence stays in
                # git at that release's commit, where its tests read it.
                verdict, meta = bound_verdict(folder)
                wrong = judge_disagreements(entry, verdict, meta)
                driver.require(
                    not wrong,
                    f"{case}: the decision does not name its verdict: {wrong}",
                )
                found = evidence["cases"].setdefault(case, {})
                found["current"] = _evidence("stage", (verdict, meta))
                found.pop("published", None)
    evidence["wave_releases"] = dict(sorted(waves.items()))
    return evidence


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    record = committed_record()
    OUT.write_text(json.dumps(restatements(args.stage_dir, record), indent=1) + "\n")
    evidence = updated_evidence(
        json.loads(EVIDENCE.read_text()), args.stage_dir, record
    )
    EVIDENCE.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)} and {EVIDENCE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
