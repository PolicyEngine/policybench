"""Every model's SNAP answer for the five minimum-benefit BBCE households.

Writes ``notes/data/bbce_households_20260922.csv``: one row per board model and
household, with the reference, the model's answer, whether it is within the
$1 exact-match tolerance, and whether its explanation mentions categorical
eligibility. The households are the scored SNAP outputs whose household
qualifies only through broad-based categorical eligibility and gets the
minimum benefit, read from ``notes/data/snap_pathways_20260922.csv``.
``tests/test_notes.py`` regenerates the rows and compares, so the note's
counts stay tied to the frozen payload of release dashboard-data-20260922.

The rows come from the run's committed payload (``data.json.gz`` in the run
directory). The release asset ``dashboard-data.json`` carries the same US
payload under ``countries.us`` but is a different file, so the meta records
both hashes: ``run_payload_sha256`` for the committed payload and
``release_payload_sha256`` for the asset, as the snapshot manifest pins it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from policybench.snapshot_payload import read_run_payload, run_payload_path

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = (
    ROOT
    / "paper/snapshot/20260501/runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace"
)
PATHWAYS = ROOT / "notes/data/snap_pathways_20260922.csv"
OUTPUT = ROOT / "notes/data/bbce_households_20260922.csv"
META = OUTPUT.with_suffix(OUTPUT.suffix + ".meta.json")
MANIFEST = ROOT / "paper/snapshot/20260501/manifest.json"
RELEASE = "dashboard-data-20260922"
# The note's mention pattern: the rule by name, or a household called
# categorically eligible. It leaves out "categorically ineligible" and the
# ABAWD "categorically exempt" wording.
BBCE_PATTERN = r"broad-based|\bbbce\b|categorical(?:ly)? eligib"
CATEGORICAL_PATHWAYS = ("categorical_income", "categorical_both")


def bbce_households(pathways: list[dict[str, str]]) -> list[str]:
    """Scored SNAP outputs that pass only through BBCE and get the minimum.

    The household fails the ordinary gross or net income test, is eligible for
    the TANF-funded non-cash benefit, and its twelve monthly allotments are
    the minimum allotment.
    """
    households = []
    for row in pathways:
        year_pathways = {row["pathway_jan_sep"], row["pathway_oct_dec"]}
        if row["snap_scored"] != "True" or not year_pathways <= set(
            CATEGORICAL_PATHWAYS
        ):
            continue
        monthly = [float(value) for value in row["monthly_snap"].split()]
        minimum = float(row["min_allotment_jan"])
        if minimum > 0 and all(value == minimum for value in monthly):
            households.append(row["scenario_id"])
    return sorted(households)


def household_rows(
    payload: dict, households: list[str], pattern: str = BBCE_PATTERN
) -> list[dict[str, object]]:
    regex = re.compile(pattern, re.IGNORECASE)
    board = sorted(
        row["model"] for row in payload["modelStats"] if row["condition"] == "no_tools"
    )
    rows = []
    for model in board:
        for scenario_id in households:
            entry = payload["scenarioPredictions"][scenario_id]["snap"][model]
            prediction = entry["prediction"]
            rows.append(
                {
                    "model": model,
                    "scenario_id": scenario_id,
                    "state": payload["scenarios"][scenario_id]["state"],
                    "reference": entry["groundTruth"],
                    "prediction": "" if prediction is None else prediction,
                    "within_1_dollar": entry["exact"] == 100,
                    "mentions_categorical_eligibility": bool(
                        regex.search(entry.get("explanation") or "")
                    ),
                }
            )
    return rows


def read_pathways() -> list[dict[str, str]]:
    with PATHWAYS.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def release_artifact() -> dict:
    """The release asset the snapshot manifest pins for this board."""
    artifact = json.loads(MANIFEST.read_text(encoding="utf-8"))[
        "published_dashboard_artifact"
    ]
    if artifact["tag"] != RELEASE:
        raise ValueError(f"The manifest pins {artifact['tag']}, not {RELEASE}.")
    return artifact


def main() -> None:
    payload = read_run_payload(RUN_DIR)
    households = bbce_households(read_pathways())
    rows = household_rows(payload, households)
    with OUTPUT.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    meta = {
        "release": RELEASE,
        "source_run": RUN_DIR.name,
        "run_payload_sha256": hashlib.sha256(
            run_payload_path(RUN_DIR).read_bytes()
        ).hexdigest(),
        "release_payload_sha256": release_artifact()["sha256"],
        "households": households,
        "mention_pattern": BBCE_PATTERN,
        "rows": len(rows),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/bbce_household_rows.py",
    }
    META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} rows for {households} to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
