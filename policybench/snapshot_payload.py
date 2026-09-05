"""Read and write a frozen run's dashboard payload.

The manuscript snapshot keeps each source run's per-country dashboard export
under ``paper/snapshot/<id>/runs/<run>/``. The export grew past GitHub's
100 MB file limit with the 39-model board, so the frozen copy is stored as a
deterministic gzip (``data.json.gz``: fixed mtime, fixed stored name) whose
bytes are pinned in the manifest. Readers go through :func:`read_run_payload`,
which also accepts an older plain ``data.json`` so pre-gzip snapshots and
throwaway exports keep working.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

PAYLOAD_NAME = "data.json.gz"
LEGACY_PAYLOAD_NAME = "data.json"


def run_payload_path(run_dir: Path) -> Path:
    """The payload file a run directory carries (gzip preferred)."""
    gz = Path(run_dir) / PAYLOAD_NAME
    if gz.exists():
        return gz
    plain = Path(run_dir) / LEGACY_PAYLOAD_NAME
    if plain.exists():
        return plain
    raise FileNotFoundError(f"no {PAYLOAD_NAME} or {LEGACY_PAYLOAD_NAME} in {run_dir}")


def read_run_payload_text(run_dir: Path) -> str:
    """The payload's JSON text exactly as serialized at freeze time."""
    path = run_payload_path(run_dir)
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as handle:
            return handle.read().decode("utf-8")
    return path.read_text(encoding="utf-8")


def read_run_payload(run_dir: Path) -> dict:
    """Parse a frozen run's per-country dashboard payload."""
    return json.loads(read_run_payload_text(run_dir))


def write_run_payload(run_dir: Path, payload_text: str) -> Path:
    """Write ``payload_text`` as a byte-deterministic ``data.json.gz``.

    A fixed mtime and stored name make the archive a pure function of its
    content, so the manifest can pin the gzip's own sha256.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    target = run_dir / PAYLOAD_NAME
    with target.open("wb") as raw:
        with gzip.GzipFile(
            filename=LEGACY_PAYLOAD_NAME, mode="wb", fileobj=raw, mtime=0
        ) as handle:
            handle.write(payload_text.encode("utf-8"))
    return target
