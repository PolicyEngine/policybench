"""The frozen run payload is a deterministic gzip with a plain-file fallback."""

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from policybench.snapshot_payload import (
    PAYLOAD_NAME,
    read_run_payload,
    read_run_payload_text,
    run_payload_path,
    write_run_payload,
)

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "paper" / "snapshot" / "20260501"


def test_write_is_byte_deterministic_and_round_trips(tmp_path: Path):
    text = json.dumps({"modelStats": [{"model": "m", "exact": 1.0}]})
    first = write_run_payload(tmp_path / "a", text)
    second = write_run_payload(tmp_path / "b", text)
    assert first.name == PAYLOAD_NAME
    assert first.read_bytes() == second.read_bytes()
    assert read_run_payload_text(tmp_path / "a") == text
    assert read_run_payload(tmp_path / "a") == json.loads(text)
    with gzip.open(first, "rb") as handle:
        assert handle.read().decode() == text


def test_reader_prefers_the_gzip_and_falls_back_to_plain(tmp_path: Path):
    (tmp_path / "data.json").write_text('{"legacy": true}')
    assert run_payload_path(tmp_path).name == "data.json"
    assert read_run_payload(tmp_path) == {"legacy": True}
    write_run_payload(tmp_path, '{"gz": true}')
    assert run_payload_path(tmp_path).name == PAYLOAD_NAME
    assert read_run_payload(tmp_path) == {"gz": True}
    with pytest.raises(FileNotFoundError):
        run_payload_path(tmp_path / "missing")


def test_frozen_snapshot_pins_the_gzip_not_a_plain_export():
    manifest = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())
    entries = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
    run_label = manifest["source_run_labels"]["us"]
    path = f"runs/{run_label}/{PAYLOAD_NAME}"
    assert path in entries
    frozen = SNAPSHOT_DIR / path
    assert hashlib.sha256(frozen.read_bytes()).hexdigest() == entries[path]
    assert not (frozen.parent / "data.json").exists()
    # Well under GitHub's 100 MB single-file limit.
    assert frozen.stat().st_size < 60 * 1024 * 1024
