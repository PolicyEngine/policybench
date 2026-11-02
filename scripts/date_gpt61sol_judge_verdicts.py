"""Record the verdicts the 2026-09-30 restatements name, for the tests.

Release dashboard-data-20260930 restated the judge fields of every decision
on a case GPT-6.1 Sol re-opened (scripts/restate_gpt61sol_adjudications.py).
Each restated entry's judge fields now name that case's new verdict in the
exported stage. This script reads each such verdict from the stage's
verdict.json and its sha256-bound verdict.meta.json and writes
docs/gpt61sol/judge_verdicts_20260930.json, which tests/test_adjudications.py
reads on machines without the stage, as it reads
reference_audit/2026-09-28/verification/judge_verdicts.json for the
2026-09-29 wave.

    python scripts/date_gpt61sol_judge_verdicts.py --stage-dir results/local/gpt61sol-v1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import finish_gpt61sol as driver  # noqa: E402

OUT = ROOT / "docs/gpt61sol/judge_verdicts_20260930.json"


def case_id(entry: dict) -> str:
    return f"{entry['country']}__{entry['scenario_id']}__{entry['variable']}"


def evidence(stage: Path) -> dict:
    """The current verdict of each committed decision on a re-opened case."""
    reopened = {
        entry["case_id"]
        for entry in json.loads(driver.JUDGE_PROVENANCE.read_text())["verdicts"]
    }
    record = json.loads((driver.ANNOTATIONS / driver.ADJUDICATIONS).read_text())
    cases = {}
    for entry in record["adjudications"]:
        case = case_id(entry)
        if case not in reopened:
            continue
        folder = stage / "audit" / "cases" / case
        raw = (folder / "verdict.json").read_bytes()
        meta = json.loads((folder / "verdict.meta.json").read_text())
        driver.require(
            meta["verdict_sha256"] == hashlib.sha256(raw).hexdigest(),
            f"{case}: the sidecar does not bind this verdict",
        )
        verdict = json.loads(raw)
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
            "The verdicts release dashboard-data-20260930's restated "
            "adjudication entries name: for each decision on a case GPT-6.1 "
            "Sol re-opened, the case's verdict in the exported stage "
            "(results/local/gpt61sol-v1), read by "
            "scripts/date_gpt61sol_judge_verdicts.py from verdict.json and its "
            "sha256-bound verdict.meta.json. The verdict each restatement "
            "replaced is release 20260929's entry (git show "
            f"{driver.BASE_COMMIT[:12]}:annotations/{driver.RUN_NAME}/"
            f"{driver.ADJUDICATIONS})."
        ),
        "release": driver.RELEASE_TAG,
        "base_commit": driver.BASE_COMMIT,
        "cases": dict(sorted(cases.items())),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stage-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    OUT.write_text(json.dumps(evidence(args.stage_dir), indent=1) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
