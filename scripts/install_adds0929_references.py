"""Install a rebuild of the 2026-09-29 references into the snapshot and the stage.

The references are built by
reference_audit/2026-09-28/scripts/build_references_latest.py (its docstring
gives the rebuild command). A rebuild may change record text only:
this script refuses a build whose reference CSV differs by a byte from the
installed one, or whose sidecar or exclusion record differs outside the fields
a rebuild rewrites (see TEXT_FIELDS). It then copies the three files to the
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
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = "us_full_run_20260612_policyengine_4_16_1_populace"
SNAPSHOT = ROOT / "paper/snapshot/20260501/runs" / RUN
BUILDER = "reference_audit/2026-09-28/scripts/build_references_latest.py"
CSV = "reference_outputs.csv"
# The fields a rebuild of the same references may rewrite.
TEXT_FIELDS = {
    "reference_exclusions.json": {"derivation", "note"},
    "reference_outputs.csv.meta.json": {"date", "rule", "basis", "regenerated_at_utc"},
}
CHANGE = (
    "rebuilt by build_references_latest.py from the committed files: the engine "
    "upgrade dated 2026-09-29 and its rule anchored to the reference sweep; the "
    "reference CSV is byte-identical and no value or key changed"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def masked(value, fields: set[str]):
    """The record with the fields a rebuild may rewrite blanked out."""
    if isinstance(value, dict):
        return {k: None if k in fields else masked(v, fields) for k, v in value.items()}
    if isinstance(value, list):
        return [masked(v, fields) for v in value]
    return value


def check_build(built: Path, installed: Path) -> None:
    """Refuse a build that changes anything but record text."""
    if (built / CSV).read_bytes() != (installed / CSV).read_bytes():
        raise SystemExit(f"{built / CSV} differs from the installed references")
    for name, fields in TEXT_FIELDS.items():
        new = json.loads((built / name).read_text())
        old = json.loads((installed / name).read_text())
        if masked(new, fields) != masked(old, fields):
            raise SystemExit(
                f"{built / name}: a field outside {sorted(fields)} changed"
            )


def install(built: Path, stage: Path) -> list[tuple[Path, str, str]]:
    staged = stage / "publish" / RUN / "us"
    receipt_path = stage / "stage.json"
    receipt = json.loads(receipt_path.read_text())
    copies = {
        name: [SNAPSHOT / name, staged / name, stage / "scoring" / name]
        for name in (CSV, *TEXT_FIELDS)
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
