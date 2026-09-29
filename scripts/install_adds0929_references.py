"""Install a rebuild of the 2026-09-29 references into the snapshot and the stage.

The references are built by
reference_audit/2026-09-28/scripts/build_references_latest.py (its docstring
gives the rebuild command). A rebuild may change record text only:
this script refuses a build whose reference CSV differs by a byte from the
installed one, or whose sidecar or exclusion record differs outside the text a
rebuild rewrites (see ``rewritable``): the engine_upgrade revision's date, rule
and each change's basis, the sidecar's regenerated_at_utc, the exclusion
record's derivation, and the notes of the exclusions the upgrade added. Every
older revision and exclusion must be unchanged. It then copies the three files to the
committed snapshot and to the stage's two copies (the freeze requires them to
be identical), and records each staged file's prepared and new sha256 in the
stage receipt (stage.json ``restaged``) before updating the receipt's pin, so
the finish script's input check keeps guarding everything else. It is
idempotent.

Usage::

    python scripts/install_adds0929_references.py --built OUT --stage-dir STAGE
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
CSV = "reference_outputs.csv"
EXCLUSIONS = "reference_exclusions.json"
SIDECAR = "reference_outputs.csv.meta.json"
RECORDS = (EXCLUSIONS, SIDECAR)
CHANGE = (
    "rebuilt by build_references_latest.py from the committed files: the engine "
    "upgrade dated 2026-09-29 and its rule anchored to the reference sweep; the "
    "reference CSV is byte-identical and no value or key changed"
)


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
    exclusions["derivation"] = None
    for entry in exclusions["exclusions"]:
        if (entry.get("scenario_id"), entry.get("variable")) in added:
            entry["note"] = None
    return sidecar, exclusions


def check_build(built: Path, installed: Path) -> None:
    """Refuse a build that changes anything but record text."""
    if (built / CSV).read_bytes() != (installed / CSV).read_bytes():
        raise SystemExit(f"{built / CSV} differs from the installed references")
    old = {name: json.loads((installed / name).read_text()) for name in RECORDS}
    new = {name: json.loads((built / name).read_text()) for name in RECORDS}
    added = _added_exclusions(old[SIDECAR], old[EXCLUSIONS])
    old_masked = rewritable(old[SIDECAR], old[EXCLUSIONS], added)
    new_masked = rewritable(new[SIDECAR], new[EXCLUSIONS], added)
    for name, before, after in zip(
        (SIDECAR, EXCLUSIONS), old_masked, new_masked, strict=True
    ):
        if before != after:
            raise SystemExit(
                f"{built / name}: a field outside the rewritable record text changed"
            )


def install(built: Path, stage: Path) -> list[tuple[Path, str, str]]:
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

    restaged = [
        item for item in receipt.get("restaged", []) if item.get("by") != BUILDER
    ]
    for path, _before, after in changes:
        if not path.is_relative_to(stage):
            continue
        name = str(path.relative_to(stage))
        if name not in receipt["files"]:
            continue
        # The pin prepare wrote, before any earlier restage of this file.
        prepared = next(
            (
                item.get("sha256_prepared", item.get("sha256_before"))
                for item in receipt.get("restaged", [])
                if item["file"] == name
            ),
            receipt["files"][name],
        )
        restaged = [item for item in restaged if item["file"] != name]
        if prepared != after:
            restaged.append(
                {
                    "file": name,
                    "sha256_prepared": prepared,
                    "sha256_after": after,
                    "by": BUILDER,
                    "installed_by": "scripts/install_adds0929_references.py",
                    "change": CHANGE,
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
    args = parser.parse_args()
    for path, before, after in install(args.built.resolve(), args.stage_dir.resolve()):
        state = "unchanged" if before == after else f"{before[:12]} -> {after[:12]}"
        print(f"{path}: {state}")


if __name__ == "__main__":
    main()
