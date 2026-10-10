"""Write manifest.json: the sha256 of every evidence file in this directory.

The manifest pins the release's inputs (as scripts/release.py reads them from
git), the engine the sweep ran on, and every file here except README.md, the
manifest itself and the logs of the test runs that check it.
tests/test_tax_table_audit.py rebuilds it and compares.

  uv run python reference_audit/2026-10-10-tax-table/scripts/build_manifest.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ENGINE = {
    "package": "policyengine-us",
    "version": "2.38.6",
    "policyengine_core": "3.32.29",
    "role": "the release's own engine, as uv.lock pins it",
}
# The README, the manifest itself, and the logs of the test runs that check it.
UNPINNED = {
    "README.md",
    "manifest.json",
    "verification/pytest_tax_table_audit.txt",
    "verification/mutants_tax_table.txt",
}


def _release():
    path = Path(__file__).with_name("release.py")
    spec = importlib.util.spec_from_file_location("tax_table_manifest_release", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest() -> dict:
    release = _release()
    files = {}
    for path in sorted(HERE.rglob("*")):
        inside = path.relative_to(HERE)
        relative = inside.as_posix()
        # Bytecode caches and a file manager's dot files are not evidence.
        hidden = any(p.startswith(".") or p == "__pycache__" for p in inside.parts)
        if not path.is_file() or relative in UNPINNED or hidden:
            continue
        data = path.read_bytes()
        files[relative] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
    return {
        "release": {
            "tag": release.RELEASE,
            "commit": release.RELEASE_COMMIT,
            "inputs": {
                f"{release.RUN}/{name}": digest
                for name, digest in release.SHA256.items()
            },
        },
        "engine": ENGINE,
        "files": files,
    }


def main() -> None:
    out = HERE / "manifest.json"
    out.write_text(json.dumps(manifest(), indent=2) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
