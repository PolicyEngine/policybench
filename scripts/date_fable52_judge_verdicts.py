"""Record the verdicts the Claude Fable 5.2 release's adjudications name.

Adapted from scripts/date_terra_judge_verdicts.py and, for the waves this
release adds, scripts/date_argon_judge_verdicts.py. The Claude Fable 5.2
release restated the judge fields of every decision on a case Claude Fable
5.2 re-opened (scripts/restate_gpt61sol_adjudications.py), installs no engine
upgrade, and adds one wave: Max's 2026-11-01 ruling (d2180), whose one
decision excludes scenario_122's Minnesota state_refundable_credits. A triage
wave joins it only when the spec lists triage decisions. Run on the exported
stage after the freeze, this script

- writes docs/fable52/judge_verdicts_<release day>.json: for each committed
  decision on a re-opened case, the case's verdict in the stage, read from
  verdict.json and its sha256-bound verdict.meta.json, as release 20261027's
  did; and
- updates reference_audit/2026-09-28/verification/judge_verdicts.json:
  release 20261027 decided no wave, so no earlier wave waits for the base
  commit to fill it; this release's waves join uncommitted (no commit or pull
  request until the next release fills them, and the day their decisions
  were written), and each of their decisions gains the stage verdict it
  names, as release 20261014's triage wave did. Any other wave beyond release
  20261027's is refused.

tests/test_adjudications.py reads both files on machines without the stage.
A second run on the same stage writes the same bytes.

    python scripts/date_fable52_judge_verdicts.py --stage-dir STAGE
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import finish_fable52 as driver  # noqa: E402
from date_adds0928_judge_verdicts import _evidence  # noqa: E402

# Named for the release tag's date (dashboard-data-YYYYMMDD).
OUT = ROOT / f"docs/fable52/judge_verdicts_{driver.RELEASE_TAG[-8:]}.json"
EVIDENCE = ROOT / "reference_audit/2026-09-28/verification/judge_verdicts.json"
# Release 20261027's waves: release 20261014's, since release 20261027 decided
# none. Each already names the commit that published it.
BASE_WAVES = [
    "2026-09-05",
    "2026-09-22",
    "2026-09-29",
    "2026-10-05",
    "2026-10-06",
    "2026-10-10",
    "2026-10-14",
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


def new_waves(record: dict, spec: dict | None = None) -> dict[str, str]:
    """The waves the record names beyond release 20261027's, each with the UTC
    day its decisions were written.

    The record must name the ruled wave, the spec's decided_on, whose
    decisions are exactly the outputs the spec rules, written on its
    adjudications_written_on. The only other wave allowed is the triage wave
    (the spec's triage_decided_on, written on its
    triage_adjudications_written_on), only when the spec lists triage
    decisions, and its decisions are exactly theirs. Each written day must be
    a real YYYY-MM-DD day on or after its wave.

    Review r1, M14 (Z P3-5): the receipt does not bind the spec, so each day
    must also be the one the record's date conventions state for its wave
    (recorded_written_day): the frozen record took its sentence from the
    spec at the freeze, and the evidence must not name another day.
    """
    spec = driver.load_spec() if spec is None else spec
    days = {e["adjudicated_on"] for e in record["adjudications"]}
    waves = sorted(days - set(BASE_WAVES))
    expected = {}
    if driver.spec_records(spec):
        expected[spec["decided_on"]] = (
            {driver.spec_key(item) for item in spec["adjudications"]},
            spec.get("adjudications_written_on"),
        )
    if spec.get("triage_adjudications"):
        expected[spec.get("triage_decided_on")] = (
            {driver.spec_key(item) for item in driver.triage_items(spec)},
            spec.get("triage_adjudications_written_on"),
        )
    driver.require(
        waves == sorted(expected),
        f"this release decides the waves {sorted(expected)} (the spec's ruling "
        f"and triage decisions), but the record names {waves}",
    )
    written = {}
    for wave in waves:
        outputs, day = expected[wave]
        decided = {
            driver.spec_key(e)
            for e in record["adjudications"]
            if e["adjudicated_on"] == wave
        }
        driver.require(
            decided == outputs,
            f"the {wave} wave decides {sorted(decided)}, not the spec's "
            f"{sorted(outputs)}",
        )
        driver.require(
            driver.utc_day(day) is not None,
            f"the spec names no day (YYYY-MM-DD) the {wave} wave's decisions were "
            f"written: {day!r}",
        )
        driver.require(wave <= day, f"the {wave} wave was written before it")
        recorded = recorded_written_day(record, wave)
        driver.require(
            recorded == day,
            f"the record's date conventions say the {wave} wave's decisions were "
            f"written on {recorded!r} and the spec says {day!r}: the spec changed "
            "since the freeze, or the record is not the frozen one",
        )
        written[wave] = day
    return written


def recorded_written_day(record: dict, wave: str) -> str | None:
    """The day the record's date conventions say the wave's decisions were
    written, or None if they name it in no such sentence or in more than one.

    The sentence runs from "The <wave> wave's decision" (decisions for more
    than one) to the first " UTC.", as driver.release_date_conventions
    writes it, and ends "was written on <day> UTC." ("were" for more than
    one). tests/test_adjudications.py parses the same sentence. A span that
    reaches another wave's sentence names no day of this wave's.
    """
    conventions = record.get("date_conventions")
    opening = f"The {wave} wave's decision"
    if not isinstance(conventions, str) or conventions.count(opening) != 1:
        return None
    start = conventions.index(opening)
    end = conventions.find(" UTC.", start)
    if end < 0 or re.search(
        r"The \d{4}-\d{2}-\d{2} wave's", conventions[start + len(opening) : end]
    ):
        return None
    found = re.fullmatch(
        re.escape(opening) + r"s? .+ (?:was|were) written on (\d{4}-\d{2}-\d{2}) UTC\.",
        conventions[start : end + len(" UTC.")],
        re.DOTALL,
    )
    return found.group(1) if found else None


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
    note = (
        f"The verdicts release {driver.RELEASE_TAG}'s adjudication entries "
        "name on the cases Claude Fable 5.2 re-opened: for each committed "
        "decision on such a case, the case's verdict in the exported stage, "
        "read by scripts/date_fable52_judge_verdicts.py from verdict.json and "
        "its sha256-bound verdict.meta.json. The verdict each restatement "
        "replaced is release 20261027's entry (git show "
        f"{driver.BASE_COMMIT[:12]}:annotations/{driver.RUN_NAME}/"
        f"{driver.ADJUDICATIONS})."
    )
    for wave in new_waves(record):
        listed = sum(
            e["adjudicated_on"] == wave and case_id(e) in cases
            for e in record["adjudications"]
        )
        if listed == 1:
            note += f" The {wave} wave's decision is new and restates nothing."
        elif listed:
            note += (
                f" The {wave} wave's {listed} decisions are new and restate nothing."
            )
    return {
        "note": note,
        "release": driver.RELEASE_TAG,
        "base_commit": driver.BASE_COMMIT,
        "cases": dict(sorted(cases.items())),
    }


def base_evidence() -> dict:
    """Release 20261027's evidence, read from git at BASE_COMMIT. This step
    rewrites the working tree's copy; the base's has not changed since
    release 20261027 published it."""
    return json.loads(driver.base_commit_blob(EVIDENCE.relative_to(ROOT)))


def base_wave_releases(waves: dict) -> dict:
    """Release 20261027's waves alone, each naming the commit that published
    it: nothing waits to be filled. Waves after them are this release's own,
    uncommitted, from an earlier pass; they are dropped and written again.

    Review r1, M14 (Z P3-3): each of release 20261027's waves must be that
    release's record of it, commit, release, pull request and day, as its
    evidence file holds them at BASE_COMMIT."""
    driver.require(
        list(waves)[: len(BASE_WAVES)] == BASE_WAVES,
        "the evidence's waves are not release 20261027's",
    )
    ours = [
        wave
        for wave in list(waves)[len(BASE_WAVES) :]
        if waves[wave].get("commit") is None
        and waves[wave].get("release") == driver.RELEASE_TAG
    ]
    driver.require(
        ours == list(waves)[len(BASE_WAVES) :],
        "the evidence names waves after release 20261027's that are not this release's",
    )
    unfilled = [wave for wave in BASE_WAVES if waves[wave].get("commit") is None]
    driver.require(
        not unfilled,
        f"the evidence leaves release 20261027's waves unfilled: {unfilled}",
    )
    base = base_evidence()["wave_releases"]
    driver.require(
        list(base) == BASE_WAVES, "release 20261027's evidence names other waves"
    )
    changed = [wave for wave in BASE_WAVES if waves[wave] != base[wave]]
    driver.require(
        not changed,
        f"the evidence's records of release 20261027's waves {changed} are not "
        "that release's",
    )
    return {wave: waves[wave] for wave in BASE_WAVES}


def verify_base_cases(evidence: dict, ours: set[str]) -> None:
    """Review r1, M14 (Z P3-3): every case outside this release's waves is
    release 20261027's evidence for it, and so is the rest of the file
    beside the waves. A case this release's waves decide keeps release
    20261027's fields too, if it has any, besides the two this step writes:
    'current', the stage verdict, and 'published', which it drops."""
    base = base_evidence()
    driver.require(
        {k: v for k, v in evidence.items() if k not in ("wave_releases", "cases")}
        == {k: v for k, v in base.items() if k not in ("wave_releases", "cases")},
        "the evidence's note or fields are not release 20261027's",
    )
    cases, before = evidence["cases"], base["cases"]
    changed = sorted(
        case
        for case in set(cases) | set(before)
        if case not in ours and cases.get(case) != before.get(case)
    )
    written = ("current", "published")
    changed += sorted(
        case
        for case in ours & set(cases)
        if {k: v for k, v in cases[case].items() if k not in written}
        != {k: v for k, v in before.get(case, {}).items() if k not in written}
    )
    driver.require(
        not changed,
        f"the evidence's cases {changed[:8]} are not release 20261027's",
    )


def updated_evidence(evidence: dict, stage: Path, record: dict) -> dict:
    """The evidence, checked against this release and given its waves: the
    earlier waves are release 20261027's, all published, and stay as they
    are; this release's waves join uncommitted, and each of their decisions
    gains the stage verdict it names ('current')."""
    evidence = copy.deepcopy(evidence)
    waves = base_wave_releases(evidence["wave_releases"])
    new = new_waves(record)
    verify_base_cases(
        evidence,
        {case_id(e) for e in record["adjudications"] if e["adjudicated_on"] in new},
    )
    for wave, written in new.items():
        waves[wave] = {
            "commit": None,
            "release": driver.RELEASE_TAG,
            "pull_request": None,
            "adjudications_written_on": written,
        }
        for entry in record["adjudications"]:
            if entry["adjudicated_on"] != wave:
                continue
            case = case_id(entry)
            verdict, meta = bound_verdict(stage / "audit" / "cases" / case)
            wrong = judge_disagreements(entry, verdict, meta)
            driver.require(
                not wrong, f"{case}: the decision does not name its verdict: {wrong}"
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
