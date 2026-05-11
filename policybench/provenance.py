"""Runtime provenance helpers for benchmark artifacts."""

from __future__ import annotations

import platform
import sys
from hashlib import sha256
from importlib import metadata
from pathlib import Path

PROVENANCE_PACKAGES = (
    "litellm",
    "numpy",
    "pandas",
    "policyengine",
    "policyengine-us",
    "policyengine-uk",
)


def installed_package_versions(
    packages: tuple[str, ...] = PROVENANCE_PACKAGES,
) -> dict[str, str]:
    """Return installed package versions for packages relevant to a run."""
    versions = {}
    for package in packages:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            continue
    return versions


def runtime_provenance() -> dict:
    """Return serializable Python and dependency provenance."""
    return {
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "packages": installed_package_versions(),
        "lockfiles": dependency_lockfile_hashes(),
    }


def dependency_lockfile_hashes(root: Path | None = None) -> dict[str, str]:
    """Return hashes for dependency lockfiles committed with the repo."""
    root = Path(__file__).resolve().parents[1] if root is None else Path(root)
    lockfiles = {}
    for filename in ("uv.lock",):
        path = root / filename
        if path.exists():
            lockfiles[filename] = sha256(path.read_bytes()).hexdigest()
    return lockfiles
