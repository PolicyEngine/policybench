"""scripts/install_adds0929_references.py installs a rebuild of the references
only when it changes record text, and keeps the stage receipt's pins true."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import install_adds0929_references as install  # noqa: E402

RUN = install.RUN


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


OLDER = {"scenario_id": "s", "variable": "a"}
ADDED = {"scenario_id": "s", "variable": "b"}


def _record_dicts(note: str, date: str) -> tuple[dict, dict]:
    """An exclusion record and sidecar shaped like the real ones: an older
    revision and exclusion the rebuild must keep, and the engine upgrade,
    which added one exclusion and changed one scored reference."""
    exclusions = {
        "derivation": f"moved on {date}",
        "exclusions": [
            {**OLDER, "note": "older", "decided_on": "2026-09-22"},
            {**ADDED, "note": note, "decided_on": "2026-09-29"},
        ],
    }
    meta = {
        "regenerated_at_utc": f"{date}T11:57:49Z",
        "revisions": [
            {
                "date": "2026-09-22",
                "kind": "convention",
                "rule": "older rule",
                "changed": [{**OLDER, "basis": "older basis"}],
            },
            {
                "date": date,
                "kind": "engine_upgrade",
                "rule": "r",
                "changed": [
                    {**ADDED, "basis": date, "regenerated": 2.0},
                    {"scenario_id": "s", "variable": "v", "basis": date},
                ],
            },
        ],
    }
    return exclusions, meta


def _encode(csv: bytes, exclusions: dict, meta: dict) -> dict[str, bytes]:
    meta = {**meta, "reference_csv_sha256": hashlib.sha256(csv).hexdigest()}
    return {
        "reference_outputs.csv": csv,
        "reference_exclusions.json": json.dumps(exclusions).encode(),
        "reference_outputs.csv.meta.json": json.dumps(meta).encode(),
    }


def _records(csv: bytes, note: str, date: str) -> dict[str, bytes]:
    return _encode(csv, *_record_dicts(note, date))


@pytest.fixture
def layout(tmp_path, monkeypatch):
    snapshot = tmp_path / "snapshot"
    stage = tmp_path / "stage"
    staged = stage / "publish" / RUN / "us"
    scoring = stage / "scoring"
    old = _records(b"scenario_id,variable,value\ns,v,1.0\n", "old", "2026-09-28")
    for directory in (snapshot, staged, scoring):
        directory.mkdir(parents=True)
        for name, raw in old.items():
            (directory / name).write_bytes(raw)
    receipt = {
        "files": {f"publish/{RUN}/us/{name}": _sha(staged / name) for name in old},
        "partial": False,
        "early": False,
    }
    (stage / "stage.json").write_text(json.dumps(receipt))
    monkeypatch.setattr(install, "SNAPSHOT", snapshot)
    return tmp_path, snapshot, stage, old


def _built(root: Path, records: dict[str, bytes]) -> Path:
    built = root / "built"
    built.mkdir(exist_ok=True)
    for name, raw in records.items():
        (built / name).write_bytes(raw)
    return built


def test_a_text_only_rebuild_is_installed_everywhere_and_pinned(layout):
    root, snapshot, stage, old = layout
    prepared = json.loads((stage / "stage.json").read_text())["files"]
    new = _records(old["reference_outputs.csv"], "new", "2026-09-29")
    built = _built(root, new)
    install.install(built, stage)
    for directory in (snapshot, stage / "publish" / RUN / "us", stage / "scoring"):
        for name, raw in new.items():
            assert (directory / name).read_bytes() == raw
    receipt = json.loads((stage / "stage.json").read_text())
    for name, pin in receipt["files"].items():
        assert _sha(stage / name) == pin
    changed = {item["file"]: item for item in receipt["restaged"]}
    assert set(changed) == {
        f"publish/{RUN}/us/reference_exclusions.json",
        f"publish/{RUN}/us/reference_outputs.csv.meta.json",
    }
    for name, item in changed.items():
        assert item["sha256_prepared"] == prepared[name]
        assert item["sha256_after"] == receipt["files"][name]
    # Idempotent: a second install changes nothing, and keeps the prepared pin.
    install.install(built, stage)
    assert json.loads((stage / "stage.json").read_text()) == receipt


def test_a_rebuild_that_changes_a_value_is_refused(layout):
    root, snapshot, stage, old = layout
    before = {name: (snapshot / name).read_bytes() for name in old}
    built = _built(
        root, _records(b"scenario_id,variable,value\ns,v,2.0\n", "new", "2026-09-29")
    )
    with pytest.raises(SystemExit, match="differs from the installed references"):
        install.install(built, stage)
    assert {name: (snapshot / name).read_bytes() for name in old} == before


def test_a_rebuild_that_changes_a_non_text_field_is_refused(layout):
    root, _snapshot, stage, old = layout
    new = _records(old["reference_outputs.csv"], "new", "2026-09-29")
    meta = json.loads(new["reference_outputs.csv.meta.json"])
    meta["revisions"][-1]["changed"][0]["regenerated"] = 3.0
    new["reference_outputs.csv.meta.json"] = json.dumps(meta).encode()
    with pytest.raises(SystemExit, match="a field outside"):
        install.install(_built(root, new), stage)


def _older_edits():
    """Edits to text the rebuild must not touch: the same field names the
    upgrade may rewrite, on an older revision or exclusion."""

    def revision_date(exclusions, meta):
        meta["revisions"][0]["date"] = "2026-09-29"

    def revision_rule(exclusions, meta):
        meta["revisions"][0]["rule"] = "a new older rule"

    def revision_basis(exclusions, meta):
        meta["revisions"][0]["changed"][0]["basis"] = "a new older basis"

    def older_note(exclusions, meta):
        exclusions["exclusions"][0]["note"] = "a new older note"

    def added_decided_on(exclusions, meta):
        exclusions["exclusions"][1]["decided_on"] = "2026-09-28"

    return [revision_date, revision_rule, revision_basis, older_note, added_decided_on]


@pytest.mark.parametrize("edit", _older_edits(), ids=lambda f: f.__name__)
def test_a_rebuild_that_changes_older_record_text_is_refused(layout, edit):
    """The mask covers the engine_upgrade revision and the exclusions it added
    only: a rebuild that redates an older revision, or rewrites its rule, a
    basis or an older exclusion's note, is refused."""
    root, snapshot, stage, old = layout
    before = {name: (snapshot / name).read_bytes() for name in old}
    exclusions, meta = _record_dicts("new", "2026-09-29")
    edit(exclusions, meta)
    new = _encode(old["reference_outputs.csv"], exclusions, meta)
    with pytest.raises(SystemExit, match="a field outside"):
        install.install(_built(root, new), stage)
    assert {name: (snapshot / name).read_bytes() for name in old} == before


def test_the_committed_records_pass_their_own_guard():
    """The installed snapshot records compare equal to themselves under the
    guard, and the guard blanks exactly the upgrade's three new exclusions'
    notes."""
    sidecar = json.loads((install.SNAPSHOT / install.SIDECAR).read_text())
    exclusions = json.loads((install.SNAPSHOT / install.EXCLUSIONS).read_text())
    added = install._added_exclusions(sidecar, exclusions)
    decided = {
        (e["scenario_id"], e["variable"]): e["decided_on"]
        for e in exclusions["exclusions"]
    }
    upgrade = install._upgrade(sidecar)
    assert upgrade is not None and len(added) == 3
    assert {decided[key] for key in added} == {upgrade["date"]}
    install.check_build(install.SNAPSHOT, install.SNAPSHOT)
