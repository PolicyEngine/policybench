"""Read the Tax Table out of an IRS Publication 1040 and write it as CSV.

Publication 1040 ("Tax and Earned Income Credit Tables") reprints the Tax Table
of the Instructions for Form 1040. ``pdftotext -raw`` (poppler) gives each table
row as six integers on one line: at least, but less than, single, married filing
jointly, married filing separately, head of household. The Tax Table ends where
the Tax Computation Worksheet page begins; the Earned Income Credit table that
follows has rows of other lengths and is not read.

The parser refuses a table that is not exactly the 2,062 bands from $0 to
$100,000 in order, so a changed layout cannot pass as a table.

  pdftotext -raw p1040.pdf p1040.raw.txt
  python3 -I parse_irs_tax_table.py p1040.raw.txt irs_tax_table_2025.csv

Standard library only, and no import from its own directory, so it can run with
``python3 -I`` on a downloaded document.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

COLUMNS = (
    "at_least",
    "less_than",
    "single",
    "joint",
    "separate",
    "head_of_household",
)
END = "Tax Computation Worksheet—Line 16"
ROW = re.compile(r"^\d[\d,]*( \d[\d,]*){5}$")
CEILING = 100_000


def expected_bands() -> list[tuple[int, int]]:
    out = [(0, 5), (5, 15), (15, 25)]
    out += [(lower, lower + 25) for lower in range(25, 3_000, 25)]
    out += [(lower, lower + 50) for lower in range(3_000, CEILING, 50)]
    return out


def parse(text: str) -> list[tuple[int, ...]]:
    end = text.find(END)
    if end < 0:
        raise SystemExit(f"no {END!r} heading: not a Publication 1040 extraction")
    rows = []
    for line in text[:end].splitlines():
        line = line.strip()
        if ROW.match(line):
            rows.append(tuple(int(token.replace(",", "")) for token in line.split()))
    bands = [row[:2] for row in rows]
    if bands != expected_bands():
        raise SystemExit(
            f"read {len(rows)} six-number rows; they are not the "
            f"{len(expected_bands())} Tax Table bands in order"
        )
    return rows


def main() -> None:
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    rows = parse(source.read_text(encoding="utf-8"))
    with target.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    print(f"wrote {target}: {len(rows)} bands, {4 * len(rows)} amounts")


if __name__ == "__main__":
    main()
