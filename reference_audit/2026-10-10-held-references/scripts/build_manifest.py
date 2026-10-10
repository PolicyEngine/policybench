"""Write manifest.json: the sha256 of every evidence file in this directory.

The manifest pins the release's inputs (read from git at the release commit,
because later releases rewrite the working tree's copies), the two engines the
traces ran on, and every file here except README.md, the manifest itself and
the two test logs. tests/test_held_references.py rebuilds it and compares.

  uv run python reference_audit/2026-10-10-held-references/scripts/build_manifest.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
RELEASE = "dashboard-data-20261010"
RELEASE_COMMIT = "5a8164a001efb27fa55f47fe7ea26666a0de31f8"
RUN = "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
RELEASE_INPUTS = (
    "scenarios.csv",
    "data.json.gz",
    "predictions.csv.gz",
    "reference_outputs.csv",
)
ENGINES = [
    {
        "role": "the engine report/REPORT.md used: upstream main on 2026-10-10",
        "package": "policyengine-us",
        "version": "2.38.8",
        "commit": "75cdd8019e07b54c78f0c8d077935c5dc9b14670",
        "policyengine_core": "3.33.0",
        "traces": "traces/policyengine-us-2.38.8-75cdd8019e",
    },
    {
        "role": "the release's own engine, as uv.lock pins it",
        "package": "policyengine-us",
        "version": "2.38.6",
        "policyengine_core": "3.32.29",
        "traces": "traces/policyengine-us-2.38.6",
    },
]
# The README, the manifest itself, and the logs of the test runs that check it.
UNPINNED = {
    "README.md",
    "manifest.json",
    "verification/pytest_held_references.txt",
    "verification/mutants_held_references.txt",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def release_input(name: str) -> bytes:
    """A release input as RELEASE_COMMIT holds it."""
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{RELEASE_COMMIT}:{RUN}/{name}"],
        capture_output=True,
        check=True,
    ).stdout


def manifest() -> dict:
    files = {}
    for path in sorted(HERE.rglob("*")):
        inside = path.relative_to(HERE)
        relative = inside.as_posix()
        # Bytecode caches and a file manager's dot files are not evidence.
        hidden = any(p.startswith(".") or p == "__pycache__" for p in inside.parts)
        if not path.is_file() or relative in UNPINNED or hidden:
            continue
        data = path.read_bytes()
        files[relative] = {"sha256": _sha256(data), "bytes": len(data)}
    return {
        "release": {
            "tag": RELEASE,
            "commit": RELEASE_COMMIT,
            "inputs": {
                f"{RUN}/{name}": _sha256(release_input(name)) for name in RELEASE_INPUTS
            },
        },
        "engines": ENGINES,
        "files": files,
    }


def main() -> None:
    out = HERE / "manifest.json"
    out.write_text(json.dumps(manifest(), indent=2) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
