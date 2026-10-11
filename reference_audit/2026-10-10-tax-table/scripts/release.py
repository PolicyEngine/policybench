"""The frozen run of release dashboard-data-20261010, read from git.

Later releases rewrite the working tree's snapshot, so the audit's scripts and
tests read the run as commit 5a8164a0 (#208) holds it and check each file
against its sha256. Nothing here writes the snapshot.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RELEASE = "dashboard-data-20261010"
RELEASE_COMMIT = "5a8164a001efb27fa55f47fe7ea26666a0de31f8"
RUN = "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
SHA256 = {
    "scenarios.csv": "71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a",
    "scenarios.csv.meta.json": (
        "03a66e90b86e9bd0cc77f27520784bd581777762f749675dc716e24c1b8eaebb"
    ),
    "reference_outputs.csv": (
        "fdd17a57092df4a9111652c85609c767bdbd05b6e32602dd8201b0b74bbbf371"
    ),
    "reference_outputs.csv.meta.json": (
        "d534cfeacf7f8a8b7f6fca477adbb02c5bb52b226778d63cc10fd117ec70c54b"
    ),
    "reference_exclusions.json": (
        "089e01e1f699aa19f2171e1ac5b6dc2ce775f9898c94420e6a0b06ff5f773626"
    ),
    "predictions.csv.gz": (
        "0183ab75931b354d6b177b147bbf57fbb79d9d0ac5b98a0304fa32eb329007ae"
    ),
    "data.json.gz": "535a51db14f13284b7054f2980b3663c3bc4317037eb3a0cc65e392096df5a90",
}
SCORING_FILES = (
    "predictions.csv.gz",
    "reference_outputs.csv",
    "reference_outputs.csv.meta.json",
    "reference_exclusions.json",
    "scenarios.csv",
    "scenarios.csv.meta.json",
)


def read(name: str) -> bytes:
    """One file of the frozen run as the release commit holds it."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{RELEASE_COMMIT}:{RUN}/{name}"],
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit(
            f"cannot read {RUN}/{name} at {RELEASE_COMMIT[:12]}; fetch full history "
            f"(git fetch --unshallow): {result.stderr.decode().strip()}"
        )
    digest = hashlib.sha256(result.stdout).hexdigest()
    if digest != SHA256[name]:
        raise SystemExit(f"{name} at {RELEASE_COMMIT[:12]} has sha256 {digest}")
    return result.stdout


def materialize(target: Path, names: tuple[str, ...] = SCORING_FILES) -> Path:
    """Write the named files of the frozen run into a scratch directory."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    for name in names:
        (target / name).write_bytes(read(name))
    return target
