"""Every model's SNAP answer for the BBCE households on release 20260929.

The September 29 update to the note on SNAP households that qualify only
through broad-based categorical eligibility reads these files:

- ``notes/data/bbce_households_20260929.csv``: the households held back by
  income. The note's four (Connecticut, Texas, Michigan, Wisconsin) and the
  Arizona household the policyengine-us 2.15.17 references add, which qualifies
  from March 2026, when Arizona raised its BBCE gross limit to 200% of the
  poverty guideline.
- ``notes/data/bbce_asset_households_20260929.csv``: the note's four
  households held back by savings.

Each row has one board model's answer and the mention flags the note's
patterns give its explanation, as ``scripts/bbce_household_rows.py`` writes
them for release dashboard-data-20260922b. The households are listed here
rather than rederived: the pathway recomputation behind the September 22
lists needs policyengine-us 1.755.4. ``tests/test_notes.py`` regenerates the
rows from the frozen payload and compares them with the committed files.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from bbce_household_rows import (
    ASSET_TEST_MENTIONS,
    MINIMUM_BENEFIT_MENTIONS,
    asset_household_rows,
    household_rows,
)

from policybench.snapshot_payload import read_run_payload, run_payload_path

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = (
    ROOT
    / "paper/snapshot/20260501/runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace"
)
MANIFEST = ROOT / "paper/snapshot/20260501/manifest.json"
RELEASE = "dashboard-data-20260929"
INCOME_HOUSEHOLDS = [
    "scenario_013",
    "scenario_027",
    "scenario_030",
    "scenario_073",
    "scenario_108",
]
ASSET_HOUSEHOLDS = ["scenario_008", "scenario_054", "scenario_066", "scenario_080"]
OUTPUT = ROOT / "notes/data/bbce_households_20260929.csv"
ASSET_OUTPUT = ROOT / "notes/data/bbce_asset_households_20260929.csv"


def meta_path(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".meta.json")


def release_payload_sha256() -> str:
    artifact = json.loads(MANIFEST.read_text(encoding="utf-8"))[
        "published_dashboard_artifact"
    ]
    if artifact["tag"] != RELEASE:
        raise ValueError(f"The manifest pins {artifact['tag']}, not {RELEASE}.")
    return artifact["sha256"]


def build(payload: dict) -> dict[Path, tuple[list[dict], list[str], dict[str, str]]]:
    """The rows, households and mention patterns of each file."""
    return {
        OUTPUT: (
            household_rows(payload, INCOME_HOUSEHOLDS, MINIMUM_BENEFIT_MENTIONS),
            INCOME_HOUSEHOLDS,
            MINIMUM_BENEFIT_MENTIONS,
        ),
        ASSET_OUTPUT: (
            asset_household_rows(payload, ASSET_HOUSEHOLDS),
            ASSET_HOUSEHOLDS,
            ASSET_TEST_MENTIONS,
        ),
    }


def main() -> None:
    payload = read_run_payload(RUN_DIR)
    run_sha256 = hashlib.sha256(run_payload_path(RUN_DIR).read_bytes()).hexdigest()
    for output, (rows, households, mentions) in build(payload).items():
        with output.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        meta = {
            "release": RELEASE,
            "source_run": RUN_DIR.name,
            "run_payload_sha256": run_sha256,
            "release_payload_sha256": release_payload_sha256(),
            "households": households,
            "mention_patterns": mentions,
            "rows": len(rows),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "script": "scripts/bbce_households_20260929.py",
        }
        meta_path(output).write_text(json.dumps(meta, indent=2) + "\n")
        print(f"Wrote {len(rows)} rows for {households} to {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
