"""Record the verdicts release dashboard-data-20261014's adjudications name.

Adapted from scripts/date_musewonder_judge_verdicts.py and, for the wave,
scripts/date_haiku55_judge_verdicts.py. The Gemini 4 Argon and Muse Spark 1.3
release restated the judge fields of every decision on a case a new model
re-opened (scripts/restate_gpt61sol_adjudications.py). It rules nothing and
installs no engine upgrade; its one wave is its own triage decisions (the
spec's triage_adjudications, dated by its triage_decided_on), each keeping an
output scored. Run on the exported stage after the freeze, this script

- writes docs/argon/judge_verdicts_<release day>.json: for each committed
  decision on a re-opened case, the triage decisions included, the case's
  verdict in the stage, read from verdict.json and its sha256-bound
  verdict.meta.json, as release 20261013's did; and
- updates reference_audit/2026-09-28/verification/judge_verdicts.json:
  releases 20261013 and 20261013b decided no wave, so no earlier wave waits
  for the base commit to fill it; this release's triage wave joins,
  uncommitted (no commit or pull request until the next release fills them,
  and the day its decisions were written), and each of its decisions gains
  the stage verdict it names, as release 20261010's waves did. Any other
  wave beyond release 20261013b's is refused.

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
from date_adds0928_judge_verdicts import _evidence  # noqa: E402

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


def new_waves(record: dict, spec: dict | None = None) -> dict[str, str]:
    """The waves the record names beyond release 20261013b's, each with the
    UTC day its decisions were written. The release rules nothing and installs
    no engine upgrade, so the only one allowed is its triage wave (the spec's
    triage_decided_on, written on its triage_adjudications_written_on), and
    only when the spec lists triage decisions."""
    spec = driver.load_spec() if spec is None else spec
    waves = sorted(
        {e["adjudicated_on"] for e in record["adjudications"]} - set(BASE_WAVES)
    )
    allowed = {spec["triage_decided_on"]} if spec.get("triage_adjudications") else set()
    driver.require(
        set(waves) <= allowed,
        f"this release decides only its triage wave {sorted(allowed)}, but the "
        f"record names {waves}",
    )
    written = {}
    for wave in waves:
        written[wave] = spec["triage_adjudications_written_on"]
        driver.require(wave <= written[wave], f"the {wave} wave was written before it")
    return written


def base_wave_releases(waves: dict) -> dict:
    """Release 20261013b's waves alone, each naming the commit that published
    it: nothing waits to be filled. Waves after them are this release's own,
    uncommitted, from an earlier pass; they are dropped and written again."""
    driver.require(
        list(waves)[: len(BASE_WAVES)] == BASE_WAVES,
        "the evidence's waves are not release 20261013b's",
    )
    ours = [
        wave
        for wave in list(waves)[len(BASE_WAVES) :]
        if waves[wave].get("commit") is None
        and waves[wave].get("release") == driver.RELEASE_TAG
    ]
    driver.require(
        ours == list(waves)[len(BASE_WAVES) :],
        "the evidence names waves after release 20261013b's that are not this "
        "release's",
    )
    unfilled = [wave for wave in BASE_WAVES if waves[wave].get("commit") is None]
    driver.require(
        not unfilled,
        f"the evidence leaves release 20261013b's waves unfilled: {unfilled}",
    )
    return {wave: waves[wave] for wave in BASE_WAVES}


def updated_evidence(evidence: dict, stage: Path, record: dict) -> dict:
    """The evidence, checked against this release and given its wave: the
    earlier waves are release 20261013b's, all published, and are kept as
    they are; this release's triage wave joins uncommitted, and each of its
    decisions gains the stage verdict it names ('current')."""
    evidence = copy.deepcopy(evidence)
    waves = base_wave_releases(evidence["wave_releases"])
    for wave, written in new_waves(record).items():
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
