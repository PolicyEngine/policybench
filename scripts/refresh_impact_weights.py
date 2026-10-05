"""Check or refresh a reference CSV's impact weights against the reference engine.

The invariant (policybench/impact_weights.py): every published impact weight
equals the weight the reference system computes for that household on its own.
``scripts/freeze_snapshot.py`` refuses a reference that breaks it, so a release
that carries a reference rebuilt on a new engine, or one whose rebuild rewrote
values only, runs this first.

``check`` recomputes every output of RUN_DIR's households on the reference
system and lists the weights that differ (exit status 1 if any).

``write`` writes the refreshed reference_outputs.csv and its sidecar to OUT_DIR:
only the weight field of each differing row changes; the sidecar gains an
``impact_weight_refresh`` revision listing every change, and its
reference_csv_sha256 and regenerated_at_utc follow the new CSV. It refuses
unless every scored value reproduces exactly. OUT_DIR may not be inside the
committed snapshot: a release installs the files into its stage and snapshot
and re-pins the manifest (docs/runbook.md, "Impact weights").

Usage::

    python scripts/refresh_impact_weights.py check RUN_DIR
    python scripts/refresh_impact_weights.py write RUN_DIR --out-dir OUT_DIR \\
        --date YYYY-MM-DD --basis TEXT [--causes CAUSES_CSV]

CAUSES_CSV has columns scenario_id, variable, cause; with it every changed row
must have a cause, which the revision records.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from policybench.impact_weights import (  # noqa: E402
    REFERENCE_CSV,
    SIDECAR,
    engine_reference_outputs,
    impact_weight_mismatches,
    read_reference,
    refresh_impact_weights,
)

SNAPSHOT = ROOT / "paper" / "snapshot"


def check(run_dir: Path) -> int:
    reference = read_reference(run_dir / REFERENCE_CSV)
    mismatches = impact_weight_mismatches(reference, engine_reference_outputs(run_dir))
    for row in mismatches.itertuples(index=False):
        print(
            f"{row.scenario_id} {row.variable:40s} "
            f"{row.published!s:>20} -> {row.engine_weight!s}"
        )
    print(f"{len(mismatches)} impact weights differ from the reference engine")
    return 1 if len(mismatches) else 0


def write(args: argparse.Namespace) -> int:
    out = Path(args.out_dir).resolve()
    if out == args.run_dir.resolve() or out.is_relative_to(SNAPSHOT.resolve()):
        raise SystemExit(f"refusing to write into {out}: install through a release")
    datetime.date.fromisoformat(args.date)
    causes = None
    if args.causes:
        frame = pd.read_csv(args.causes)
        causes = {
            (row.scenario_id, row.variable): row.cause
            for row in frame.itertuples(index=False)
        }
    refresh = refresh_impact_weights(
        args.run_dir,
        engine_reference_outputs(args.run_dir),
        date=args.date,
        regenerated_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        basis=args.basis,
        causes=causes,
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / REFERENCE_CSV).write_text(refresh.csv_text)
    (out / SIDECAR).write_text(json.dumps(refresh.sidecar, indent=2) + "\n")
    print(f"{len(refresh.changes)} impact weights refreshed into {out}")
    print(f"sha256 {refresh.sidecar['reference_csv_sha256']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    check_parser = sub.add_parser("check")
    check_parser.add_argument("run_dir", type=Path)
    write_parser = sub.add_parser("write")
    write_parser.add_argument("run_dir", type=Path)
    write_parser.add_argument("--out-dir", required=True)
    write_parser.add_argument("--date", required=True)
    write_parser.add_argument("--basis", required=True)
    write_parser.add_argument("--causes")
    args = parser.parse_args(argv)
    if args.command == "check":
        return check(args.run_dir)
    return write(args)


if __name__ == "__main__":
    raise SystemExit(main())
