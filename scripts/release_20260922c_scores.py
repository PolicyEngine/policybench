"""The no-tools exact scores release dashboard-data-20260922c published.

The September 29 release note compares every earlier model's exact score under
the policyengine-us 2.15.17 references with the score release 20260922c
published. This script copies those 42 scores out of the 22c release asset,
``dashboard-data.json`` (sha256 01e7e72b..., the asset the app's
``src/data.artifact.json`` pointed to at commit 3220a7a6), into
``notes/data/release_20260922c_exact.csv``, so ``tests/test_notes.py`` checks
the note's drift facts against a small committed file, without the 116 MB
payload or git history.

Usage::

    python scripts/release_20260922c_scores.py PATH/TO/dashboard-data.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "notes/data/release_20260922c_exact.csv"
RELEASE = "dashboard-data-20260922c"
POINTER_COMMIT = "3220a7a62b6be83032e9313c9df539c619ad8932"
ASSET_SHA256 = "01e7e72b3a6bdd2d3178ba32625ff769d5b81dc07541af6ea8da2c852774ddcc"
ASSET_BYTES = 116_100_222


def meta_path(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".meta.json")


def exact_scores(payload: dict) -> list[tuple[str, float]]:
    """(model, exact) for every no-tools row of the US board, best first."""
    rows = [
        row
        for row in payload["countries"]["us"]["modelStats"]
        if row["condition"] == "no_tools"
    ]
    return sorted(
        ((row["model"], float(row["exact"])) for row in rows),
        key=lambda item: (-item[1], item[0]),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("payload", type=Path, help="the 22c dashboard-data.json")
    args = parser.parse_args()
    blob = args.payload.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != ASSET_SHA256 or len(blob) != ASSET_BYTES:
        raise SystemExit(
            f"{args.payload} is not the {RELEASE} asset: sha256 {digest}, "
            f"{len(blob):,} bytes"
        )
    scores = exact_scores(json.loads(blob))
    with OUTPUT.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(["model", "exact"])
        for model, exact in scores:
            writer.writerow([model, repr(exact)])
    meta = {
        "release": RELEASE,
        "asset": "dashboard-data.json",
        "url": (
            "https://github.com/PolicyEngine/policybench/releases/download/"
            f"{RELEASE}/dashboard-data.json"
        ),
        "asset_sha256": ASSET_SHA256,
        "asset_bytes": ASSET_BYTES,
        "pointer": f"app/src/data.artifact.json at {POINTER_COMMIT}",
        "field": "countries.us.modelStats[condition == no_tools].exact",
        "rows": len(scores),
        "output_sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/release_20260922c_scores.py",
    }
    meta_path(OUTPUT).write_text(json.dumps(meta, indent=2) + "\n")
    print(f"Wrote {len(scores)} scores to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
