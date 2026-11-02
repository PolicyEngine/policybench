"""Every model's SNAP answer for the BBCE note's households on release 20260930.

The October 5 note on SNAP households that qualify only through broad-based
categorical eligibility (BBCE) reads these files:

- ``notes/data/bbce_households_20260930.csv``: the households held back by
  income. Each scored SNAP output whose household qualifies in some month of
  2026, qualifies in every such month only through BBCE after failing an
  ordinary SNAP income test, and gets the minimum benefit in each of those
  months. Each row has the reference, the model's answer, whether it is within
  the $1 exact-match tolerance, and whether its explanation mentions
  categorical eligibility and a net income limit.
- ``notes/data/bbce_asset_households_20260930.csv``: the households held back
  by savings, which pass SNAP's income tests all year, fail only its asset
  test, and qualify through BBCE. Each row has the reference, whether that
  output is scored, the model's answer, and whether its explanation mentions
  categorical eligibility and assets.

The households come from the pathway recomputation on the release's
references, ``notes/data/snap_pathways_20260930.csv``
(``scripts/snap_pathways_20260930.py``), month by month: one household, in
Arizona, qualifies only from March 2026, when Arizona raised its BBCE gross
income limit. ``tests/test_notes.py`` regenerates the rows from the frozen
payload and compares them with the committed files.

The rows come from the run's committed payload (``data.json.gz`` in the run
directory). The release asset ``dashboard-data.json`` carries the same US
payload but is a different file, so each meta records both hashes:
``run_payload_sha256`` for the committed payload and
``release_payload_sha256`` for the asset, as the snapshot manifest pins it.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bbce_household_rows import (  # noqa: E402
    ASSETS_PATTERN,
    NET_LIMIT_PATTERN,
    household_rows,
)

from policybench.snapshot_payload import (  # noqa: E402
    read_run_payload,
    run_payload_path,
)

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = (
    ROOT
    / "paper/snapshot/20260501/runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace"
)
MANIFEST = ROOT / "paper/snapshot/20260501/manifest.json"
RELEASE = "dashboard-data-20260930"
PATHWAYS = ROOT / "notes/data/snap_pathways_20260930.csv"
OUTPUT = ROOT / "notes/data/bbce_households_20260930.csv"
ASSET_OUTPUT = ROOT / "notes/data/bbce_asset_households_20260930.csv"
SCRIPT_PATH = "scripts/bbce_households_20260930.py"
# Categorical eligibility, matched case-insensitively: the rule by name, a
# household called categorically eligible with a space or a hyphen between
# the words, or a state's "expanded categorical" limit, another name for BBCE
# (GPT-6.1 Sol: "Michigan's expanded categorical gross-income limit"). It
# leaves out "categorically ineligible" and the ABAWD "categorically exempt"
# wording.
BBCE_PATTERN = r"broad-based|\bbbce\b|categorical(?:ly)?[- ]eligib|expanded categorical"
INCOME_MENTIONS = {
    "mentions_categorical_eligibility": BBCE_PATTERN,
    "mentions_net_income_limit": NET_LIMIT_PATTERN,
}
ASSET_MENTIONS = {
    "mentions_categorical_eligibility": BBCE_PATTERN,
    "mentions_assets": ASSETS_PATTERN,
}
CATEGORICAL_INCOME_PATHWAYS = {"categorical_income", "categorical_both"}
ASSET_PATHWAY = "categorical_assets"


def meta_path(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".meta.json")


def read_pathways() -> list[dict[str, str]]:
    with PATHWAYS.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def bbce_households(pathways: list[dict[str, str]]) -> list[str]:
    """Scored SNAP outputs held back by income that BBCE brings to the minimum.

    In every month of 2026 the household qualifies, it does so only through
    BBCE after failing SNAP's gross or net income test, and it gets that
    month's minimum allotment; it qualifies in at least one month.
    """
    households = []
    for row in pathways:
        pathways_by_month = row["pathway_by_month"].split()
        eligible = [p for p in pathways_by_month if p != "ineligible"]
        if row["snap_scored"] != "True" or not eligible:
            continue
        if not set(eligible) <= CATEGORICAL_INCOME_PATHWAYS:
            continue
        snap = [float(v) for v in row["monthly_snap"].split()]
        minimum = [float(v) for v in row["monthly_min_allotment"].split()]
        if all(
            (s == m > 0) if p != "ineligible" else s == 0
            for s, m, p in zip(snap, minimum, pathways_by_month, strict=True)
        ):
            households.append(row["scenario_id"])
    return sorted(households)


def asset_households(pathways: list[dict[str, str]]) -> list[str]:
    """Households that qualify through BBCE only because of the asset test,
    in every month. Scored or not: the prompt asks every model."""
    return sorted(
        row["scenario_id"]
        for row in pathways
        if set(row["pathway_by_month"].split()) == {ASSET_PATHWAY}
    )


def build(
    payload: dict, pathways: list[dict[str, str]]
) -> dict[Path, tuple[list[dict], list[str], dict[str, str]]]:
    """The rows, households and mention patterns of each file."""
    income = bbce_households(pathways)
    savings = asset_households(pathways)
    return {
        OUTPUT: (
            household_rows(payload, income, INCOME_MENTIONS),
            income,
            INCOME_MENTIONS,
        ),
        ASSET_OUTPUT: (
            household_rows(
                payload,
                savings,
                ASSET_MENTIONS,
                scored_column=True,
                exact_column=False,
            ),
            savings,
            ASSET_MENTIONS,
        ),
    }


def release_payload_sha256() -> str:
    artifact = json.loads(MANIFEST.read_text(encoding="utf-8"))[
        "published_dashboard_artifact"
    ]
    if artifact["tag"] != RELEASE:
        raise ValueError(f"The manifest pins {artifact['tag']}, not {RELEASE}.")
    return artifact["sha256"]


def main() -> None:
    payload = read_run_payload(RUN_DIR)
    run_sha256 = hashlib.sha256(run_payload_path(RUN_DIR).read_bytes()).hexdigest()
    for output, (rows, households, mentions) in build(payload, read_pathways()).items():
        with output.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        meta = {
            "release": RELEASE,
            "source_run": RUN_DIR.name,
            "run_payload_sha256": run_sha256,
            "release_payload_sha256": release_payload_sha256(),
            "pathways": PATHWAYS.relative_to(ROOT).as_posix(),
            "pathways_sha256": hashlib.sha256(PATHWAYS.read_bytes()).hexdigest(),
            "households": households,
            "mention_patterns": mentions,
            "rows": len(rows),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "script": SCRIPT_PATH,
        }
        meta_path(output).write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Wrote {len(rows)} rows for {households} to {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
