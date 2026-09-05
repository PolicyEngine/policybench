"""Apply developer adjudications to a publish bundle's audit annotations.

    PYTHONPATH=. python scripts/apply_adjudications.py \
        --annotations-dir results/local/<add>/publish/<run>/annotations \
        [--adjudications annotations/<run>/us_adjudications.json] [--country us]

Rewrites ``<country>_audit_row_annotations.csv`` and ``<country>_case_notes.csv``
in place (pandas ``to_csv(index=False)``, the same writer the finish drivers
use) so the exported dashboard payload, the frozen annotation copies, and the
committed adjudication record all agree. Idempotent: a second run changes
nothing. Prints what changed and exits non-zero if an adjudication targets a
case the annotations do not contain.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from policybench.adjudications import (  # noqa: E402
    apply_adjudications,
    load_adjudications,
    verify_adjudications_applied,
)

RUN_LABEL = "us_full_run_20260612_policyengine_4_16_1_populace"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--annotations-dir", type=Path, required=True)
    parser.add_argument(
        "--adjudications",
        type=Path,
        default=ROOT / "annotations" / RUN_LABEL / "us_adjudications.json",
    )
    parser.add_argument("--country", default="us")
    args = parser.parse_args(argv)

    adjudications = load_adjudications(args.adjudications)
    if not adjudications:
        print(f"no adjudications in {args.adjudications}; nothing to apply")
        return
    rows_path = args.annotations_dir / f"{args.country}_audit_row_annotations.csv"
    cases_path = args.annotations_dir / f"{args.country}_case_notes.csv"
    rows = pd.read_csv(rows_path)
    cases = pd.read_csv(cases_path)
    rows, cases, report = apply_adjudications(rows, cases, adjudications)
    verify_adjudications_applied(rows, cases, adjudications)
    rows.to_csv(rows_path, index=False)
    cases.to_csv(cases_path, index=False)
    for item in report:
        print(
            f"{item['case']}: {item['rows_rewritten']} rows {item['from']} -> "
            f"{item['to']}"
        )
    print(f"applied {len(adjudications)} adjudication(s) to {args.annotations_dir}")


if __name__ == "__main__":
    main()
