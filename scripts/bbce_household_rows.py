"""Every model's SNAP answer for the households that qualify only through BBCE.

Writes two files, each one row per board model and household, from the
committed pathway recomputation ``notes/data/snap_pathways_20260922.csv``:

- ``notes/data/bbce_households_20260922.csv``: the four scored SNAP outputs
  whose household fails an ordinary SNAP income test, qualifies only through
  broad-based categorical eligibility and gets the minimum benefit. Each row
  has the reference, the model's answer, whether it is within the $1
  exact-match tolerance, whether its explanation mentions categorical
  eligibility, and whether it mentions a net income limit.
- ``notes/data/bbce_asset_households_20260922.csv``: the four households that
  pass SNAP's income tests all year, fail only its asset test, and qualify
  through broad-based categorical eligibility. Each row has the reference,
  whether that output is scored, the model's answer, and whether its
  explanation mentions categorical eligibility and assets.

``tests/test_notes.py`` regenerates the rows and compares, so the note's
counts stay tied to the frozen payload of release dashboard-data-20260922b.
That release excludes scenario_045's SNAP output (root cause r33, the SNAP
child support treatment), so the Michigan worker is no longer among the
scored households.

The rows come from the run's committed payload (``data.json.gz`` in the run
directory). The release asset ``dashboard-data.json`` carries the same US
payload under ``countries.us`` but is a different file, so each meta records
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
ASSET_OUTPUT = ROOT / "notes/data/bbce_asset_households_20260922.csv"
ASSET_META = ASSET_OUTPUT.with_suffix(ASSET_OUTPUT.suffix + ".meta.json")
MANIFEST = ROOT / "paper/snapshot/20260501/manifest.json"
RELEASE = "dashboard-data-20260922b"
# The note's mention patterns, matched case-insensitively.
# Categorical eligibility: the rule by name, or a household called
# categorically eligible, with a space or a hyphen ("categorical-eligibility
# ceiling"). It leaves out "categorically ineligible" and the ABAWD
# "categorically exempt" wording.
BBCE_PATTERN = r"broad-based|\bbbce\b|categorical(?:ly)?[- ]eligib"
# Assets: the September 3 note's pattern.
ASSETS_PATTERN = r"asset|resource"
# A net income limit or test: "net income limit", "net-income test", "net
# limit", or 100% of the poverty guideline. A bare "net income" (an amount)
# does not count.
NET_LIMIT_PATTERN = (
    r"\bnet[- ](?:income[- ])?(?:limit|test|screen|threshold|ceiling|rule)"
    r"|(?<![\d.])100(?:\.0+)?\s*%[^.;]{0,20}?(?:fpl|fpg|poverty)"
)
CATEGORICAL_PATHWAYS = ("categorical_income", "categorical_both")
ASSET_PATHWAY = "categorical_assets"
# The CSV columns each pattern fills, per file.
MINIMUM_BENEFIT_MENTIONS = {
    "mentions_categorical_eligibility": BBCE_PATTERN,
    "mentions_net_income_limit": NET_LIMIT_PATTERN,
}
ASSET_TEST_MENTIONS = {
    "mentions_categorical_eligibility": BBCE_PATTERN,
    "mentions_assets": ASSETS_PATTERN,
}


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


def asset_test_households(pathways: list[dict[str, str]]) -> list[str]:
    """Households that qualify through BBCE only because of the asset test.

    They pass SNAP's gross and net income tests but fail its asset test all
    year, so the pathway recomputation labels both parts of the year
    ``categorical_assets``. Scored or not: the prompt asks every model.
    """
    return sorted(
        row["scenario_id"]
        for row in pathways
        if row["pathway_jan_sep"] == row["pathway_oct_dec"] == ASSET_PATHWAY
    )


def household_rows(
    payload: dict,
    households: list[str],
    mentions: dict[str, str] = MINIMUM_BENEFIT_MENTIONS,
    *,
    scored_column: bool = False,
    exact_column: bool = True,
) -> list[dict[str, object]]:
    """One row per board model and household, models and households sorted."""
    regexes = {
        column: re.compile(pattern, re.IGNORECASE)
        for column, pattern in mentions.items()
    }
    board = sorted(
        row["model"] for row in payload["modelStats"] if row["condition"] == "no_tools"
    )
    rows = []
    for model in board:
        for scenario_id in households:
            entry = payload["scenarioPredictions"][scenario_id]["snap"][model]
            prediction = entry["prediction"]
            explanation = entry.get("explanation") or ""
            row: dict[str, object] = {
                "model": model,
                "scenario_id": scenario_id,
                "state": payload["scenarios"][scenario_id]["state"],
                "reference": entry["groundTruth"],
            }
            if scored_column:
                row["scored"] = entry.get("scored") is not False
            row["prediction"] = "" if prediction is None else prediction
            if exact_column:
                row["within_1_dollar"] = entry["exact"] == 100
            for column, regex in regexes.items():
                row[column] = bool(regex.search(explanation))
            rows.append(row)
    return rows


def asset_household_rows(payload: dict, households: list[str]) -> list[dict]:
    """The asset-test households' rows: whether each output is scored, and no
    exact-match column, since one of the four outputs is not scored."""
    return household_rows(
        payload,
        households,
        ASSET_TEST_MENTIONS,
        scored_column=True,
        exact_column=False,
    )


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


def _write(
    rows: list[dict],
    output: Path,
    meta_path: Path,
    households: list[str],
    mentions: dict[str, str],
) -> None:
    with output.open("w", encoding="utf-8", newline="") as target:
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
        "mention_patterns": mentions,
        "rows": len(rows),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/bbce_household_rows.py",
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} rows for {households} to {output.relative_to(ROOT)}")


def main() -> None:
    payload = read_run_payload(RUN_DIR)
    pathways = read_pathways()
    households = bbce_households(pathways)
    _write(
        household_rows(payload, households),
        OUTPUT,
        META,
        households,
        MINIMUM_BENEFIT_MENTIONS,
    )
    asset_households = asset_test_households(pathways)
    _write(
        asset_household_rows(payload, asset_households),
        ASSET_OUTPUT,
        ASSET_META,
        asset_households,
        ASSET_TEST_MENTIONS,
    )


if __name__ == "__main__":
    main()
