"""MOCK DATA: a synthetic second engine upgrade, for the paper and upgrade tests.

The release after dashboard-data-20261006 moves the references from
policyengine-us 2.15.17 to a newer release (Max, 2026-10-09: "yes i want to
wait for hte fixed engine"), appending a second ``engine_upgrade`` revision to
the reference sidecar. The tests that must hold for any number of upgrades also run
against release 20261006's records, read from git, with one more upgrade
appended here, so they keep a two-upgrade case before and after that release
lands.

Every value this module adds is invented for the tests. It is shaped like the
hub's preview sweep (reviews/policybench-pe-upgrade-2026-10-09/
cells_pe2.37.1.md), but the engine version, the moves, the restored and the
new exclusion records are not published references and must never be read as
PolicyBench results.
"""

from __future__ import annotations

import copy
import functools
import io
import json
import subprocess
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUN_PATH = (
    "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
RUN_DIR = ROOT / RUN_PATH
# Release dashboard-data-20261006 (#202): the last release on 2.15.17.
RELEASE_20261006_COMMIT = "9ce4ade8382962a9134860c23f56d92509b5e57f"

MOCK_ENGINE = "2.37.2"
MOCK_PREVIOUS_ENGINE = "2.15.17"
MOCK_DATE = "2026-10-09"
MOCK_REBUILT_AT = "2026-10-09T18:00:00.000000+00:00"
MOCK_VALUE_KEY = "value_on_" + MOCK_ENGINE.replace(".", "_")

FEDERAL = "federal_income_tax_before_refundable_credits"
# A scored reference the mock upgrade moves beyond the tolerance.
MOCK_SCORED = ("scenario_015", "local_income_tax")
# A scored reference it moves by under $1.
MOCK_WITHIN = ("scenario_000", FEDERAL)
# A scored output it moves and excludes, on the new engine.
MOCK_NEW_EXCLUSION = ("scenario_067", "local_income_tax")
# An output excluded on 1.755.4 (r02_ira_219g) whose defect the mock engine
# fixes: its record is removed and the output returns to scoring.
MOCK_RESTORED = ("scenario_120", FEDERAL)
# A record decided between the upgrades (2026-10-06, on 2.15.17) on an output
# the 2026-09-29 upgrade changed as a scored reference. It stays excluded and
# moves on the mock engine, so the upgrade rechecks it.
MOCK_LATER_RECORD = ("scenario_082", "state_refundable_credits")
MOCK_LATER_RECORD_DATE = "2026-10-06"
# An output excluded on 1.755.4 that moves on the mock engine and stays excluded.
MOCK_RECHECKED = ("scenario_005", FEDERAL)

MOCK_MOVES = {
    MOCK_SCORED: 670.55,
    MOCK_WITHIN: 0.25,
    MOCK_NEW_EXCLUSION: 1348.83,
    MOCK_RESTORED: 401.36,
}
MOCK_RECHECKED_VALUES = {MOCK_RECHECKED: 107833.15625, MOCK_LATER_RECORD: 1187.61}


@dataclass(frozen=True)
class Tree:
    """The reference records a release commits, as plain data."""

    sidecar: dict
    exclusions: list[dict]
    references: dict[tuple[str, str], float]
    manifest: dict
    pins: list[str]


def _tree(read: Callable[[str], str]) -> Tree:
    """The reference records ``read`` returns for each repository path. The
    references are parsed as paper_results parses them (pandas, whose float
    parser can differ from float() in the last place), so the review sweeps'
    exact checks hold."""
    frame = pd.read_csv(io.StringIO(read(f"{RUN_PATH}/reference_outputs.csv")))
    references = {
        (row.scenario_id, row.variable): float(row.value)
        for row in frame.itertuples(index=False)
    }
    return Tree(
        sidecar=json.loads(read(f"{RUN_PATH}/reference_outputs.csv.meta.json")),
        exclusions=json.loads(read(f"{RUN_PATH}/reference_exclusions.json"))[
            "exclusions"
        ],
        references=references,
        manifest=json.loads(read("paper/snapshot/20260501/manifest.json")),
        pins=tomllib.loads(read("pyproject.toml"))["project"]["dependencies"],
    )


def working_tree() -> Tree:
    """The working tree's reference records."""
    return _tree(lambda path: (ROOT / path).read_text())


@functools.cache
def release_20261006() -> Tree:
    """Release 20261006's reference records, read from git at its commit: the
    base the mock upgrade is appended to. Read from git rather than the
    working tree, which the release that moves the references rewrites (and
    whose 2026-10-06 records exclude the mock's later-record output), so the
    fixture builds before and after that release lands. CI checks out full
    history."""

    def read(path: str) -> str:
        shown = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{RELEASE_20261006_COMMIT}:{path}"],
            capture_output=True,
        )
        if shown.returncode != 0:
            raise RuntimeError(
                f"cannot read {path} at {RELEASE_20261006_COMMIT[:12]} (fetch "
                f"full history): {shown.stderr.decode().strip()}"
            )
        return shown.stdout.decode()

    return _tree(read)


def _record_like(template: dict, key: tuple[str, str], **fields) -> dict:
    record = copy.deepcopy(template)
    record.update(scenario_id=key[0], variable=key[1], **fields)
    return record


def with_second_upgrade(tree: Tree) -> Tree:
    """``tree`` with the mock upgrade appended, as a release would commit it.

    Refuses a tree that already carries an upgrade past 2.15.17, or whose
    outputs no longer have the roles the mock gives them.
    """
    revisions = tree.sidecar["revisions"]
    upgrades = [rev for rev in revisions if rev.get("kind") == "engine_upgrade"]
    base = upgrades[-1]
    if base["engine_version"] != f"policyengine-us {MOCK_PREVIOUS_ENGINE}":
        raise ValueError("the tree already moved past policyengine-us 2.15.17")
    records = {(e["scenario_id"], e["variable"]): e for e in tree.exclusions}
    for key in (MOCK_SCORED, MOCK_WITHIN, MOCK_NEW_EXCLUSION, MOCK_LATER_RECORD):
        if key in records:
            raise ValueError(f"mock role needs a scored output: {key}")
    for key in (MOCK_RESTORED, MOCK_RECHECKED):
        if key not in records:
            raise ValueError(f"mock role needs an excluded output: {key}")

    references = dict(tree.references)
    changed = []
    for key, delta in MOCK_MOVES.items():
        previous = references[key]
        references[key] = previous + delta
        cause = {
            MOCK_NEW_EXCLUSION: "excluded_reference_depends_on_unlisted_input",
            MOCK_RESTORED: "regenerated_upstream_fix",
        }.get(key, "mock_engine_change")
        changed.append(
            {
                "scenario_id": key[0],
                "variable": key[1],
                "frozen": previous,
                "previous": previous,
                "regenerated": references[key],
                "cause": cause,
                "basis": "MOCK: invented for tests/second_engine_upgrade.py.",
            }
        )

    restored_record = records[MOCK_RESTORED]
    unlisted = next(
        e
        for e in tree.exclusions
        if e["reason_code"] == "reference_depends_on_unlisted_input"
    )
    new_record = _record_like(
        unlisted,
        MOCK_NEW_EXCLUSION,
        frozen_value=references[MOCK_NEW_EXCLUSION],
        alternative_value=0.0,
        engine_version=f"policyengine-us {MOCK_ENGINE}",
        decided_on=MOCK_DATE,
        note="MOCK: invented for tests/second_engine_upgrade.py.",
    )
    later_record = _record_like(
        restored_record,
        MOCK_LATER_RECORD,
        frozen_value=references[MOCK_LATER_RECORD],
        alternative_value=MOCK_RECHECKED_VALUES[MOCK_LATER_RECORD],
        engine_version=f"policyengine-us {MOCK_PREVIOUS_ENGINE}",
        decided_on=MOCK_LATER_RECORD_DATE,
        note="MOCK: invented for tests/second_engine_upgrade.py.",
    )
    exclusions = [
        e for e in tree.exclusions if (e["scenario_id"], e["variable"]) != MOCK_RESTORED
    ] + [later_record, new_record]

    revision = {
        "date": MOCK_DATE,
        "kind": "engine_upgrade",
        "root_cause": "engine_upgrade_policyengine_us_" + MOCK_ENGINE.replace(".", "_"),
        "outputs": "every scored output",
        "rule": base["rule"],
        "engine_version": f"policyengine-us {MOCK_ENGINE}",
        "previous_engine_version": f"policyengine-us {MOCK_PREVIOUS_ENGINE}",
        "policyengine_py": base["policyengine_py"],
        "fix_modules": copy.deepcopy(base["fix_modules"]),
        "builder": base["builder"],
        "excluded_outputs_untouched": True,
        "excluded_outputs_rechecked": [
            {
                "scenario_id": key[0],
                "variable": key[1],
                "kept_value": references[key],
                MOCK_VALUE_KEY: value,
                "reason": "MOCK: invented for tests/second_engine_upgrade.py.",
            }
            for key, value in MOCK_RECHECKED_VALUES.items()
        ],
        "regenerated_exclusions": [
            {
                # The shape reference_audit/2026-10-09-engine-upgrade's builder
                # writes: the removed record travels with the regeneration.
                "scenario_id": MOCK_RESTORED[0],
                "variable": MOCK_RESTORED[1],
                "root_cause": restored_record["root_cause"],
                "decided_on": restored_record["decided_on"],
                "kept_value": tree.references[MOCK_RESTORED],
                MOCK_VALUE_KEY: references[MOCK_RESTORED],
                "regenerated": references[MOCK_RESTORED],
                "basis": "MOCK: invented for tests/second_engine_upgrade.py.",
                "record": copy.deepcopy(restored_record),
            }
        ],
        "changed": changed,
    }
    sidecar = copy.deepcopy(tree.sidecar)
    sidecar["revisions"].append(revision)
    sidecar["policyengine_bundles"]["us"]["model_version"] = MOCK_ENGINE
    sidecar["regenerated_at_utc"] = MOCK_REBUILT_AT
    manifest = copy.deepcopy(tree.manifest)
    refresh = manifest["reference_output_refresh"]
    refresh.update(
        policyengine_us_version=MOCK_ENGINE,
        regenerated_at_utc=MOCK_REBUILT_AT,
        date=MOCK_DATE,
    )
    pins = [
        f"policyengine-us=={MOCK_ENGINE}"
        if pin == f"policyengine-us=={MOCK_PREVIOUS_ENGINE}"
        else pin
        for pin in tree.pins
    ]
    return Tree(
        sidecar=sidecar,
        exclusions=exclusions,
        references=references,
        manifest=manifest,
        pins=pins,
    )


def paper_results_for(tree: Tree):
    """A fresh PaperResults over ``tree``'s reference records; every other
    artifact is the working tree's."""
    from policybench.paper_results import PaperResults

    results = PaperResults()
    results.manifest = tree.manifest
    results.reference_revisions = tree.sidecar["revisions"]
    results.reference_exclusions = tree.exclusions
    results.frozen_references = tree.references
    return results
