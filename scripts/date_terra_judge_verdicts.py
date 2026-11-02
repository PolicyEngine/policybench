"""Record the verdicts release dashboard-data-20261027's adjudications name.

Adapted from scripts/date_argon_judge_verdicts.py and, for the wave the base
release left uncommitted, scripts/date_musewonder_judge_verdicts.py. The
GPT-6.1 Terra release restated the judge fields of every decision on a case
GPT-6.1 Terra or its move to policyengine-us 2.60.0 re-opened
(scripts/restate_gpt61sol_adjudications.py). It rules nothing, its triage
decided nothing (the spec's triage_adjudications is empty), and its engine
upgrade newly excludes no output, so it decides no wave. Run on the exported
stage after the freeze, this script

- writes docs/terra/judge_verdicts_<release day>.json: for each committed
  decision on a re-opened case, the case's verdict in the stage, read from
  verdict.json and its sha256-bound verdict.meta.json, as release 20261014's
  did; and
- brings reference_audit/2026-09-28/verification/judge_verdicts.json up to
  this release: release 20261014, whose 2026-10-14 triage wave joined the
  evidence uncommitted, is now committed (the driver's BASE_COMMIT), so that
  wave names the commit, its pull request and its UTC commit day, and each of
  its decisions gains the verdict that release published. Any wave beyond
  release 20261014's is refused.

tests/test_adjudications.py reads both files on machines without the stage.
A second run on the same stage writes the same bytes.

    python scripts/date_terra_judge_verdicts.py --stage-dir STAGE
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

import finish_terra as driver  # noqa: E402

# Named for the release tag's date (dashboard-data-YYYYMMDD).
OUT = ROOT / f"docs/terra/judge_verdicts_{driver.RELEASE_TAG[-8:]}.json"
EVIDENCE = ROOT / "reference_audit/2026-09-28/verification/judge_verdicts.json"
# The wave release 20261014 decided, which this release's base commit froze.
FILL_WAVES = ["2026-10-14"]
FILL_RELEASE = "dashboard-data-20261014"
# Release 20261014's waves: release 20261010's, then its own triage wave
# (releases 20261013 and 20261013b decided none).
BASE_WAVES = [
    "2026-09-05",
    "2026-09-22",
    "2026-09-29",
    "2026-10-05",
    "2026-10-06",
    "2026-10-10",
    *FILL_WAVES,
]


def case_id(entry: dict) -> str:
    return f"{entry['country']}__{entry['scenario_id']}__{entry['variable']}"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
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
    driver.require(cases, "no committed decision is on a re-opened case")
    return {
        "note": (
            f"The verdicts release {driver.RELEASE_TAG}'s adjudication entries "
            "name on the cases GPT-6.1 Terra or the move to policyengine-us "
            "2.60.0 re-opened: for each committed decision on such a case, the "
            "case's verdict in the exported stage, read by "
            "scripts/date_terra_judge_verdicts.py from verdict.json and its "
            "sha256-bound verdict.meta.json. The verdict each restatement "
            "replaced is release 20261014's entry (git show "
            f"{driver.BASE_COMMIT[:12]}:annotations/{driver.RUN_NAME}/"
            f"{driver.ADJUDICATIONS}). The release decides no wave."
        ),
        "release": driver.RELEASE_TAG,
        "base_commit": driver.BASE_COMMIT,
        "cases": dict(sorted(cases.items())),
    }


def fill_release() -> dict:
    """The 2026-10-14 wave's release as committed: the base commit, its pull
    request (the squash subject's "(#N)") and its UTC commit day."""
    subject = git("show", "-s", "--format=%s", driver.BASE_COMMIT).strip()
    number = re.search(r"\(#(\d+)\)$", subject)
    driver.require(number is not None, f"{subject!r} names no pull request")
    driver.require(FILL_RELEASE in subject, f"{subject!r} does not name {FILL_RELEASE}")
    when = datetime.datetime.fromisoformat(
        git("show", "-s", "--format=%cI", driver.BASE_COMMIT).strip()
    )
    return {
        "commit": driver.BASE_COMMIT,
        "release": FILL_RELEASE,
        "pull_request": int(number.group(1)),
        "committed_on": when.astimezone(datetime.timezone.utc).date().isoformat(),
    }


def require_no_new_waves(record: dict) -> None:
    """The release decides no wave: every decision is release 20261014's
    waves'."""
    waves = sorted(
        {e["adjudicated_on"] for e in record["adjudications"]} - set(BASE_WAVES)
    )
    driver.require(
        not waves, f"this release decides no wave, but the record names {waves}"
    )


def base_wave_releases(waves: dict) -> dict:
    """Release 20261014's waves, in order and nothing after them. Every one
    before the fill waves names the commit that published it."""
    driver.require(
        list(waves) == BASE_WAVES,
        "the evidence's waves are not release 20261014's",
    )
    unfilled = [
        wave
        for wave in BASE_WAVES
        if wave not in FILL_WAVES and waves[wave].get("commit") is None
    ]
    driver.require(
        not unfilled,
        f"the evidence leaves waves before release 20261014's unfilled: {unfilled}",
    )
    return copy.deepcopy(waves)


def updated_evidence(evidence: dict, record: dict) -> dict:
    """The evidence brought up to this release: the 2026-10-14 wave names the
    commit that published it, and each of its decisions gains the verdict that
    commit's record published. Every other wave and case is kept as it is."""
    require_no_new_waves(record)
    evidence = copy.deepcopy(evidence)
    waves = base_wave_releases(evidence["wave_releases"])
    fill = fill_release()
    for wave in FILL_WAVES:
        if waves[wave].get("commit") is None:
            driver.require(
                waves[wave]["release"] == fill["release"],
                f"the {wave} wave is not release 20261014's",
            )
            driver.require(
                waves[wave]["adjudications_written_on"] <= fill["committed_on"],
                f"the {wave} wave was written after its release was committed",
            )
            waves[wave] = fill
        driver.require(waves[wave] == fill, f"the {wave} wave was filled otherwise")
    published = json.loads(
        git(
            "show",
            f"{driver.BASE_COMMIT}:annotations/{driver.RUN_NAME}/{driver.ADJUDICATIONS}",
        )
    )["adjudications"]
    filled = 0
    for entry in published:
        if entry["adjudicated_on"] not in FILL_WAVES:
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
    driver.require(filled > 0, f"release 20261014 published no {FILL_WAVES} decisions")
    evidence["wave_releases"] = waves
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
