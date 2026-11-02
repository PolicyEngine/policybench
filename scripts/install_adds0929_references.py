"""Install a rebuild of the 2026-09-29 references into the snapshot and the stage.

The references are built by
reference_audit/2026-09-28/scripts/build_references_latest.py (its docstring
gives the rebuild command); reference_audit/2026-09-28/scripts/
rewrite_reference_records.py rewrites the installed records with the builder's
record functions when no output needs recomputing. A build may change record
text, and add the audit exclusions final_actions.json lists, only: this script
refuses a build whose reference CSV differs by a byte from the installed one,
or whose sidecar or exclusion record differs outside the text a rebuild
rewrites (see ``rewritable``): the engine_upgrade revision's date, rule, each
change's basis and each rechecked excluded output's reason, the sidecar's
regenerated_at_utc, the exclusion record's derivation, and the notes of the
exclusions the upgrade added. The exclusion record may also gain the entries
final_actions.json lists under audit_exclusions, each exactly as recorded there,
and must keep them once installed. Every older revision and exclusion must be
unchanged. It then copies the three files to the committed snapshot and to the
stage's two copies (the freeze requires them to be identical), and records each
staged file's prepared and new sha256, and every install that changed it, in the
stage receipt (stage.json ``restaged``) before updating the receipt's pin, so
the finish script's input check keeps guarding everything else. It is
idempotent.

Usage::

    python scripts/install_adds0929_references.py --built OUT --stage-dir STAGE \\
        [--built-by reference_audit/2026-09-28/scripts/rewrite_reference_records.py]
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = "us_full_run_20260612_policyengine_4_16_1_populace"
SNAPSHOT = ROOT / "paper/snapshot/20260501/runs" / RUN
BUILDER = "reference_audit/2026-09-28/scripts/build_references_latest.py"
REWRITER = "reference_audit/2026-09-28/scripts/rewrite_reference_records.py"
ACTIONS = ROOT / "reference_audit/2026-09-28/final_actions.json"
CSV = "reference_outputs.csv"
EXCLUSIONS = "reference_exclusions.json"
SIDECAR = "reference_outputs.csv.meta.json"
RECORDS = (EXCLUSIONS, SIDECAR)
CHANGES = {
    BUILDER: (
        "rebuilt by build_references_latest.py from the committed files: the engine "
        "upgrade dated 2026-09-29 and its rule anchored to the reference sweep; the "
        "reference CSV is byte-identical and no value or key changed"
    ),
    REWRITER: (
        "rewritten by rewrite_reference_records.py with the builder's record "
        "functions: each rechecked excluded output's full reviewed reason "
        "(clusters.json), and the audit exclusions final_actions.json lists; the "
        "reference CSV is byte-identical and no reference value changed"
    ),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _upgrade(sidecar: dict) -> dict | None:
    """The sidecar's last revision when it is the engine upgrade."""
    revisions = sidecar.get("revisions") or []
    if revisions and revisions[-1].get("kind") == "engine_upgrade":
        return revisions[-1]
    return None


def _added_exclusions(sidecar: dict, exclusions: dict) -> set[tuple[str, str]]:
    """Outputs the engine upgrade changed that the exclusion record lists."""
    upgrade = _upgrade(sidecar)
    if upgrade is None:
        return set()
    listed = {(e["scenario_id"], e["variable"]) for e in exclusions["exclusions"]}
    return {
        (c["scenario_id"], c["variable"]) for c in upgrade.get("changed", [])
    } & listed


def rewritable(
    sidecar: dict, exclusions: dict, added: set[tuple[str, str]]
) -> tuple[dict, dict]:
    """Both records with the text a rebuild may rewrite blanked out.

    ``added`` names the exclusions the installed upgrade added; only their
    notes are blanked, so a rebuild cannot touch an older exclusion. In the
    sidecar only the engine_upgrade revision's date, rule and change bases,
    and regenerated_at_utc, are blanked, so every older revision must match.
    """
    sidecar, exclusions = copy.deepcopy(sidecar), copy.deepcopy(exclusions)
    sidecar["regenerated_at_utc"] = None
    upgrade = _upgrade(sidecar)
    if upgrade is not None:
        upgrade["date"] = upgrade["rule"] = None
        for change in upgrade.get("changed", []):
            change["basis"] = None
        for item in upgrade.get("excluded_outputs_rechecked", []):
            item["reason"] = None
    exclusions["derivation"] = None
    for entry in exclusions["exclusions"]:
        if (entry.get("scenario_id"), entry.get("variable")) in added:
            entry["note"] = None
    return sidecar, exclusions


def audit_exclusions(actions_path: Path | None = None) -> dict[tuple[str, str], dict]:
    """The exclusion records final_actions.json lists under audit_exclusions:
    outputs the audit excluded on review, apart from any engine change."""
    actions_path = ACTIONS if actions_path is None else actions_path
    actions = json.loads(actions_path.read_text())
    records = {}
    for item in actions.get("audit_exclusions", []):
        key = (item["scenario_id"], item["variable"])
        record = item["exclusion"]
        if (record["scenario_id"], record["variable"]) != key or key in records:
            raise SystemExit(f"malformed audit exclusion in {actions_path}: {key}")
        records[key] = record
    return records


def _without(exclusions: dict, keys) -> dict:
    """The exclusion record without the given outputs' entries."""
    return {
        **exclusions,
        "exclusions": [
            e
            for e in exclusions["exclusions"]
            if (e.get("scenario_id"), e.get("variable")) not in keys
        ],
    }


def check_build(
    built: Path, installed: Path, audit: dict[tuple[str, str], dict] | None = None
) -> None:
    """Refuse a build that changes anything but record text, apart from adding
    the listed audit exclusions (``audit``, by default final_actions.json's)."""
    if (built / CSV).read_bytes() != (installed / CSV).read_bytes():
        raise SystemExit(f"{built / CSV} differs from the installed references")
    old = {name: json.loads((installed / name).read_text()) for name in RECORDS}
    new = {name: json.loads((built / name).read_text()) for name in RECORDS}
    audit = audit_exclusions() if audit is None else audit
    for label, record in (("installed", old[EXCLUSIONS]), ("built", new[EXCLUSIONS])):
        entries = {
            (e.get("scenario_id"), e.get("variable")): e for e in record["exclusions"]
        }
        for key in set(entries) & set(audit):
            if entries[key] != audit[key]:
                raise SystemExit(
                    f"{label} exclusion {key} differs from its audit_exclusions record"
                )
        if label == "built" and not set(audit) <= set(entries):
            raise SystemExit(
                f"{built / EXCLUSIONS} lacks audit exclusions: "
                f"{sorted(set(audit) - set(entries))}"
            )
    added = _added_exclusions(old[SIDECAR], old[EXCLUSIONS])
    old_masked = rewritable(old[SIDECAR], _without(old[EXCLUSIONS], audit), added)
    new_masked = rewritable(new[SIDECAR], _without(new[EXCLUSIONS], audit), added)
    for name, before, after in zip(
        (SIDECAR, EXCLUSIONS), old_masked, new_masked, strict=True
    ):
        if before != after:
            raise SystemExit(
                f"{built / name}: a field outside the rewritable record text changed"
            )


def install(built: Path, stage: Path, by: str = BUILDER) -> list[tuple[Path, str, str]]:
    if by not in CHANGES:
        raise SystemExit(f"unknown builder {by}")
    staged = stage / "publish" / RUN / "us"
    receipt_path = stage / "stage.json"
    receipt = json.loads(receipt_path.read_text())
    copies = {
        name: [SNAPSHOT / name, staged / name, stage / "scoring" / name]
        for name in (CSV, *RECORDS)
    }
    for name, group in copies.items():
        if len({digest(p) for p in group}) != 1:
            raise SystemExit(f"copies of {name} differ before the install: {group}")
    check_build(built, SNAPSHOT)

    changes = []
    for name, group in copies.items():
        for path in group:
            before = digest(path)
            path.write_bytes((built / name).read_bytes())
            changes.append((path, before, digest(path)))

    earlier = {item["file"]: item for item in receipt.get("restaged", [])}
    restaged = []
    for path, before, after in changes:
        if not path.is_relative_to(stage):
            continue
        name = str(path.relative_to(stage))
        if name not in receipt["files"]:
            continue
        item = earlier.get(name, {})
        # The pin prepare wrote, before any earlier restage of this file.
        prepared = item.get(
            "sha256_prepared", item.get("sha256_before", receipt["files"][name])
        )
        # Every install that changed the file since prepare, oldest first.
        installs = list(item.get("installs", []))
        if "by" in item:
            installs.append({"by": item["by"], "change": item["change"]})
        if before != after:
            installs.append({"by": by, "change": CHANGES[by]})
        if prepared != after:
            restaged.append(
                {
                    "file": name,
                    "sha256_prepared": prepared,
                    "sha256_after": after,
                    "installed_by": "scripts/install_adds0929_references.py",
                    "installs": installs,
                }
            )
        receipt["files"][name] = after
    receipt["restaged"] = restaged
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--built", type=Path, required=True)
    parser.add_argument("--stage-dir", type=Path, required=True)
    parser.add_argument("--built-by", choices=sorted(CHANGES), default=BUILDER)
    args = parser.parse_args()
    for path, before, after in install(
        args.built.resolve(), args.stage_dir.resolve(), by=args.built_by
    ):
        state = "unchanged" if before == after else f"{before[:12]} -> {after[:12]}"
        print(f"{path}: {state}")


if __name__ == "__main__":
    main()
