"""Apply rewrites.json to the frozen audit annotations and re-pin their hashes.

Each rewrite names one annotation file, one row (scenario_id and variable, plus model for
row annotations), one text field, the field's whole old text and its whole new text. The
script refuses a rewrite whose row is missing or not unique, or whose field holds neither
the old nor the new text, and it changes nothing else: no other field, no other row, no
row order and no quoting. It then writes the new sha256 of each annotation file into
paper/snapshot/20260501/manifest.json (``audit_annotation_artifacts.files``).

``--check`` writes nothing and fails unless every rewrite is in force and the manifest
pins the files as they are.

  python reference_audit/2026-10-05-medicaid-031-annotations/scripts/apply_rewrites.py
  python reference_audit/2026-10-05-medicaid-031-annotations/scripts/apply_rewrites.py --check
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parents[1]
REWRITES = HERE / "rewrites.json"
MANIFEST = ROOT / "paper/snapshot/20260501/manifest.json"

KEYS = {
    "us_audit_row_annotations.csv": ("scenario_id", "variable", "model"),
    "us_case_notes.csv": ("scenario_id", "variable"),
    "us_case_reference_explanations.csv": ("scenario_id", "variable"),
}
FIELDS = {
    "us_audit_row_annotations.csv": "annotation",
    "us_case_notes.csv": "case_annotation",
    "us_case_reference_explanations.csv": "explanation",
}


def _read(path: Path) -> tuple[list[str], list[list[str]], bytes]:
    raw = path.read_bytes()
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8"), newline="")))
    return rows[0], rows[1:], raw


def _write(header: list[str], rows: list[list[str]]) -> bytes:
    out = io.StringIO(newline="")
    csv.writer(out, lineterminator="\n").writerows([header, *rows])
    return out.getvalue().encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = json.loads(REWRITES.read_text())
    manifest = json.loads(MANIFEST.read_text())
    block = manifest["audit_annotation_artifacts"]
    annotations = ROOT / block["path"]
    problems: list[str] = []
    changed_files: dict[str, bytes] = {}

    by_file: dict[str, list[dict]] = {}
    for item in payload["rewrites"]:
        by_file.setdefault(item["file"], []).append(item)

    for name, items in sorted(by_file.items()):
        if name not in KEYS:
            problems.append(f"{name}: not a rewritable annotation file")
            continue
        header, rows, raw = _read(annotations / name)
        # The round trip must reproduce the file, so a write changes only the
        # rewritten fields.
        if _write(header, rows) != raw:
            problems.append(f"{name}: does not round-trip byte for byte")
            continue
        columns = {column: i for i, column in enumerate(header)}
        key_columns = [columns[c] for c in KEYS[name]]
        field = columns[FIELDS[name]]
        index: dict[tuple, list[int]] = {}
        for i, row in enumerate(rows):
            index.setdefault(tuple(row[c] for c in key_columns), []).append(i)
        seen: set[tuple] = set()
        for item in items:
            if item["field"] != FIELDS[name]:
                problems.append(f"{name}: {item['field']!r} is not the text field")
                continue
            key = tuple(item[c] for c in KEYS[name])
            if key in seen:
                problems.append(f"{name}: two rewrites of {key}")
                continue
            seen.add(key)
            hits = index.get(key, [])
            if len(hits) != 1:
                problems.append(f"{name}: {key} matches {len(hits)} rows")
                continue
            current = rows[hits[0]][field]
            if current == item["new"]:
                continue
            if current != item["old"]:
                problems.append(f"{name}: {key} holds neither the old nor the new text")
                continue
            if args.check:
                problems.append(f"{name}: {key} still holds the old text")
                continue
            rows[hits[0]][field] = item["new"]
        data = _write(header, rows)
        if data != raw:
            changed_files[name] = data

    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1

    if not args.check:
        for name, data in changed_files.items():
            (annotations / name).write_bytes(data)
            print(f"rewrote {name}")

    stale = []
    for name in sorted(KEYS):
        digest = _sha256((annotations / name).read_bytes())
        if block["files"][name] != digest:
            stale.append(name)
            block["files"][name] = digest
    if stale and args.check:
        print(f"manifest pins stale hashes for {stale}", file=sys.stderr)
        return 1
    if stale:
        text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
        original = MANIFEST.read_text()
        # Keep the manifest's formatting: it must round-trip before we rewrite it.
        if json.dumps(json.loads(original), indent=2, ensure_ascii=False) + "\n" != original:
            print("manifest.json does not round-trip; refusing to rewrite it", file=sys.stderr)
            return 1
        MANIFEST.write_text(text)
        print(f"re-pinned {stale} in {MANIFEST.relative_to(ROOT)}")
    print(f"{len(payload['rewrites'])} rewrites in force")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
