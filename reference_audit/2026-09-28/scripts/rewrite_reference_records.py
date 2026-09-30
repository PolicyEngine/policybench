"""Rewrite the 2026-09-29 reference records without recomputing any output.

build_references_latest.py recomputes all 1,984 outputs on policyengine-us 2.15.17
before it writes the records. For record changes that need no engine run, this
script applies the builder's own record functions to the installed files instead:

- each rechecked excluded output's reason in the sidecar's engine_upgrade revision
  becomes the full text of its cluster review's corrected_per_output entry
  (clusters.json; reviewed_reason);
- the exclusion record gains the audit exclusions listed in final_actions.json
  (audit_exclusions), after the upgrade's own, with the derivation the builder writes
  (exclusion_derivation).

It copies the reference CSV byte for byte, refuses an audit exclusion whose
frozen_value is not the committed reference or that the engine upgrade changed, and
writes the records with the builder's serialization (dump_record).
scripts/install_adds0929_references.py then installs the output only if the reference
CSV is byte-identical and nothing changed but record text and the listed audit
exclusions. Run from the checkout (git must hold the 20260922c base commit):

  .venv/bin/python reference_audit/2026-09-28/scripts/rewrite_reference_records.py \\
    --out-dir OUT
  .venv/bin/python scripts/install_adds0929_references.py --built OUT \\
    --stage-dir results/local/adds0928-v3 \\
    --built-by reference_audit/2026-09-28/scripts/rewrite_reference_records.py
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent
ROOT = AUDIT.parents[1]
RUN = "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
CSV = "reference_outputs.csv"
SIDECAR = "reference_outputs.csv.meta.json"
EXCLUSIONS = "reference_exclusions.json"


def builder():
    """build_references_latest.py, for its record functions (no engine import)."""
    spec = importlib.util.spec_from_file_location(
        "build_references_latest", HERE / "build_references_latest.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def rewrite(installed: Path, actions: dict, clusters: dict, base_derivation: str):
    """The installed sidecar and exclusion record, rewritten as the builder writes
    them. Returns (sidecar, exclusions)."""
    build = builder()
    records = {}
    for name in (SIDECAR, EXCLUSIONS):
        raw = (installed / name).read_text()
        records[name] = json.loads(raw)
        if build.dump_record(records[name]) != raw:
            raise SystemExit(f"{name} is not in the builder's serialization")
    sidecar, exclusions = records[SIDECAR], records[EXCLUSIONS]
    upgrade = sidecar["revisions"][-1]
    if upgrade.get("kind") != "engine_upgrade":
        raise SystemExit("the sidecar's last revision is not the engine upgrade")

    rechecked = {(a["scenario_id"], a["variable"]): a for a in actions["excluded_rechecked"]}
    for item in upgrade["excluded_outputs_rechecked"]:
        entry = rechecked[(item["scenario_id"], item["variable"])]
        item["reason"] = build.reviewed_reason(clusters, entry)

    audit = build.audit_exclusions(actions)
    with (installed / CSV).open(newline="") as source:
        values = {(r["scenario_id"], r["variable"]): float(r["value"]) for r in csv.DictReader(source)}
    changed = {(c["scenario_id"], c["variable"]) for c in upgrade["changed"]}
    for key, record in audit.items():
        if key in changed or record["frozen_value"] != values[key]:
            raise SystemExit(f"audit exclusion {key} is not an unchanged reference")
    kept = [e for e in exclusions["exclusions"] if (e["scenario_id"], e["variable"]) not in audit]
    exclusions["exclusions"] = kept + list(audit.values())
    exclusions["derivation"] = build.exclusion_derivation(
        base_derivation, len(actions["new_exclusions"]) + len(audit), len(audit)
    )
    return sidecar, exclusions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--installed", type=Path, default=ROOT / RUN)
    args = parser.parse_args()
    build = builder()
    actions = json.loads((AUDIT / "final_actions.json").read_text())
    clusters = {c["id"]: c for c in json.loads((AUDIT / "clusters.json").read_text())["clusters"]}
    base = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{build.BASE_COMMIT}:{RUN}/{EXCLUSIONS}"],
        check=True,
        capture_output=True,
    ).stdout
    sidecar, exclusions = rewrite(args.installed, actions, clusters, json.loads(base)["derivation"])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.installed / CSV, args.out_dir / CSV)
    (args.out_dir / SIDECAR).write_text(build.dump_record(sidecar))
    (args.out_dir / EXCLUSIONS).write_text(build.dump_record(exclusions))
    print(
        f"{len(sidecar['revisions'][-1]['excluded_outputs_rechecked'])} rechecked reasons, "
        f"{len(exclusions['exclusions'])} exclusions -> {args.out_dir}"
    )


if __name__ == "__main__":
    main()
