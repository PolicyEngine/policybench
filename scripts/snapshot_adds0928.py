"""Copy completed scenario CSVs for a PARTIAL rehearsal without reading live state.

Creates synthetic incomplete run_state.json files (total=100). Pass the copied
root to finish_adds0928.py --early to demonstrate refusal. Then, ONLY in this
scratch copy, set total=completed and use --early --partial. These synthetic
states carry no evidence about the actual supervisor's serving fingerprint.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from finish_adds0928 import MODELS, ROOT, SNAPSHOT, validate_stage_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    validate_stage_path(args.out_dir, [args.runs_root, SNAPSHOT])
    if args.out_dir.exists():
        raise SystemExit("use a new out-dir; never overwrite an earlier snapshot")
    expected = {}
    with (SNAPSHOT / "reference_outputs.csv").open() as stream:
        for row in csv.DictReader(stream):
            expected.setdefault(row["scenario_id"], set()).add(row["variable"])
    for slug, model in MODELS.items():
        target = args.out_dir / slug / "run"
        (target / "scenarios").mkdir(parents=True)
        combined = []
        hashes = {}
        for source in sorted(
            (args.runs_root / slug / "run/scenarios").glob("scenario_???.csv")
        ):
            raw = source.read_bytes()
            rows = list(csv.DictReader(io.StringIO(raw.decode())))
            # The supervisor names files by queue index, not scenario_id.
            scenario_id = rows[0]["scenario_id"] if rows else ""
            if (
                not rows
                or {r["scenario_id"] for r in rows} != {scenario_id}
                or {r["model"] for r in rows} != {model}
                or {r["variable"] for r in rows} != expected.get(scenario_id)
                or len(rows) != len(expected.get(scenario_id, []))
            ):
                print(f"Skipped incomplete/invalid scenario: {source.name}")
                continue
            (target / "scenarios" / source.name).write_bytes(raw)
            hashes[source.name] = hashlib.sha256(raw).hexdigest()
            combined.extend(rows)
        if not combined:
            raise SystemExit(f"no completed scenarios: {slug}")
        with (target / "predictions.csv").open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(combined[0]))
            writer.writeheader()
            writer.writerows(combined)
        state = {
            "model": model,
            "completed": len(hashes),
            "total": 100,
            "stopped_reason": None,
            "synthetic_partial": True,
            "note": "CSV-only rehearsal; actual run_state and treatment "
            "fingerprint not read",
        }
        (target / "run_state.json").write_text(json.dumps(state, indent=2) + "\n")
        (target / "scenario-sha256.json").write_text(
            json.dumps(hashes, indent=2) + "\n"
        )
        print(
            f"PARTIAL {model}: copied {len(hashes)}/100 households "
            f"({len(combined)} rows)"
        )
    print(f"Scratch snapshot: {args.out_dir.resolve().relative_to(ROOT)}")


if __name__ == "__main__":
    main()
