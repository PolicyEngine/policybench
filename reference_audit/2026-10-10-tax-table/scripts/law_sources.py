"""Record the law documents read and check the committed excerpts against them.

The documents themselves are not committed (law/sources.json gives each one's
address and sha256). Given the directory they were saved in, this script

1. extracts text (``pdftotext -raw`` for the PDFs; tags stripped from the HTML
   and XML), so every check runs on text made the same way;
2. writes law/sources.json: each document's address, what it is used for, the
   dates its PDF carries, and the sha256 and size of the saved file and of its
   extraction;
3. checks every block quote of law/excerpts.md against the extraction its
   ``<!-- source: ... -->`` comment names, after removing line-break hyphens and
   collapsing white space, and writes law/excerpts_check.json;
4. reads the 2025 and 2026 rate tables out of the two revenue procedures and
   compares thresholds, rates and base amounts with scripts/tax_table.py;
5. re-parses both Publications 1040 and compares with the committed CSVs;
6. confirms that no IRS document read uses the word "midpoint" or "middle"
   (other than "middle initial" on Form 1040-ES's vouchers). A description in
   other words would not be caught;
7. reads archived copies of IRS.gov's draft-forms listing (Internet Archive
   captures from before and after the 2026-07-03 freeze) and writes
   law/draft_listing_history.json: which posting dates the captures cover, and
   whether any listed draft is a Publication 1040, the Instructions for Form
   1040 or a tax table.

  python3 -I reference_audit/2026-10-10-tax-table/scripts/law_sources.py \\
    --law-dir ~/reviews/policybench-tax-table-2026-10-10/law

Standard library only (and poppler's pdftotext and pdfinfo on PATH). It loads
its two sibling modules by path, so it runs under ``python3 -I``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import importlib.util
import io
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
LAW = HERE / "law"
READ_ON = "2026-10-10"

SOURCES = [
    {
        "document": "26 U.S.C. 3 (United States Code, 2024 Edition)",
        "used_for": "the Tax Table tax is imposed in lieu of the section 1 tax",
        "saved_from": "https://www.govinfo.gov/content/pkg/USCODE-2024-title26/html/USCODE-2024-title26-subtitleA-chap1-subchapA-partI-sec3.htm",
        "file": "govinfo_usc26_3.htm",
    },
    {
        "document": "26 U.S.C. 4 (United States Code, 2024 Edition)",
        "used_for": "the rules for the elective table are repealed",
        "saved_from": "https://www.govinfo.gov/content/pkg/USCODE-2024-title26/html/USCODE-2024-title26-subtitleA-chap1-subchapA-partI-sec4.htm",
        "file": "govinfo_usc26_4.htm",
    },
    {
        "document": "26 U.S.C. 1 (United States Code, 2024 Edition)",
        "used_for": "the rate schedules; section 1(h)'s reference to them",
        "saved_from": "https://www.govinfo.gov/content/pkg/USCODE-2024-title26/html/USCODE-2024-title26-subtitleA-chap1-subchapA-partI-sec1.htm",
        "file": "govinfo_usc26_1.htm",
        "note": (
            "govinfo's most recent edition on the day read "
            "(govinfo.gov/link/uscode/26/1?type=usc&year=mostrecent returned the same "
            "bytes). uscode.house.gov, which carries later amendments, was under "
            "maintenance."
        ),
    },
    {
        "document": "26 U.S.C. 6102 (United States Code, 2024 Edition)",
        "used_for": "whole-dollar amounts are the filer's option",
        "saved_from": "https://www.govinfo.gov/content/pkg/USCODE-2024-title26/html/USCODE-2024-title26-subtitleF-chap61-subchapB-sec6102.htm",
        "file": "govinfo_usc26_6102.htm",
    },
    {
        "document": "Pub. L. 119-21, section 70101",
        "used_for": "the section 1(j) rate tables continue after 2025",
        "saved_from": "https://www.govinfo.gov/content/pkg/PLAW-119publ21/html/PLAW-119publ21.htm",
        "file": "plaw119-21.htm",
    },
    {
        "document": "26 CFR 1.3-1 (eCFR, as of 2026-07-01)",
        "used_for": "the regulation predates the present table",
        "saved_from": "https://www.ecfr.gov/api/versioner/v1/full/2026-07-01/title-26.xml?part=1&section=1.3-1",
        "file": "ecfr_1.3-1.xml",
    },
    {
        "document": "Rev. Proc. 2025-32",
        "used_for": "the 2026 rate tables (section 4.01)",
        "saved_from": "https://www.irs.gov/pub/irs-drop/rp-25-32.pdf",
        "file": "rp-25-32.pdf",
    },
    {
        "document": "Rev. Proc. 2024-40",
        "used_for": "the 2025 rate tables (section 3.01), for the check on the 2025 table",
        "saved_from": "https://www.irs.gov/pub/irs-drop/rp-24-40.pdf",
        "file": "rp-24-40.pdf",
    },
    {
        "document": "2026 Form 1040-ES",
        "used_for": "the IRS's 2026 Tax Rate Schedules, published before the freeze",
        "saved_from": "https://www.irs.gov/pub/irs-pdf/f1040es.pdf",
        "file": "f1040es.pdf",
    },
    {
        "document": "2025 Instructions for Form 1040 (and 1040-SR)",
        "used_for": "line 16; the capital gain worksheet; rounding; the Tax Table",
        "saved_from": "https://www.irs.gov/pub/irs-pdf/i1040gi.pdf",
        "file": "i1040gi.pdf",
    },
    {
        "document": "2025 Instructions for Schedule D (Form 1040)",
        "used_for": "the Schedule D Tax Worksheet, lines 44 and 46",
        "saved_from": "https://www.irs.gov/pub/irs-pdf/i1040sd.pdf",
        "file": "i1040sd.pdf",
    },
    {
        "document": "Publication 1040 (2025), Tax and Earned Income Credit Tables",
        "used_for": "the published 2025 Tax Table (law/irs_tax_table_2025.csv)",
        "saved_from": "https://www.irs.gov/pub/irs-prior/p1040--2025.pdf",
        "file": "p1040_2025.pdf",
    },
    {
        "document": "Publication 1040 (2026), early release draft",
        "used_for": "the draft 2026 Tax Table (law/irs_tax_table_2026_draft.csv)",
        "saved_from": "https://www.irs.gov/pub/irs-dft/p1040--dft.pdf",
        "file": "p1040_dft.pdf",
    },
    {
        "document": "IRS.gov draft tax forms listing, search '1040'",
        "used_for": "the date the draft Publication 1040 (2026) was posted",
        "saved_from": "https://www.irs.gov/draft-tax-forms?find=1040&items_per_page=200",
        "file": "irs_drafts_1040.html",
    },
    {
        "document": "IRS.gov forms, instructions and publications listing, search 'Publication 1040'",
        "used_for": "the current final Publication 1040 is the 2025 revision",
        "saved_from": "https://www.irs.gov/forms-instructions-and-publications?find=Publication+1040&items_per_page=200",
        "file": "irs_forms_p1040.html",
    },
    {
        "document": "IRS.gov forms, instructions and publications listing, search '1040-ES'",
        "used_for": "the date the 2026 Form 1040-ES was posted",
        "saved_from": "https://www.irs.gov/forms-instructions-and-publications?find=1040-ES&items_per_page=200",
        "file": "irs_forms_1040es.html",
    },
    {
        "document": "IRS news release IR-2025-103",
        "used_for": "the date the IRS announced Rev. Proc. 2025-32",
        "saved_from": "https://www.irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-tax-year-2026-including-amendments-from-the-one-big-beautiful-bill",
        "file": "irs_news_2026_adjustments.html",
    },
]
FREEZE = "2026-07-03"
LISTING = "https://www.irs.gov/draft-tax-forms"
# Internet Archive captures of the listing (capture time in UTC, page, saved as).
# Each page holds 25 drafts, newest posting first; page 0 is the first.
ARCHIVED_LISTINGS = [
    ("20260520014706", 0, "wayback/drafts_20260520_p0.html"),
    ("20260527224622", 0, "wayback/drafts_20260527_p0.html"),
    ("20260605135701", 0, "wayback/drafts_20260605_p0.html"),
    ("20260606195555", 0, "wayback/drafts_20260606_p0.html"),
    ("20260614191000", 1, "wayback/drafts_20260614_p1.html"),
    ("20260614191329", 2, "wayback/drafts_20260614_p2.html"),
    ("20260614191635", 3, "wayback/drafts_20260614_p3.html"),
    ("20260614191701", 4, "wayback/drafts_20260614_p4.html"),
    ("20260614192542", 6, "wayback/drafts_20260614_p6.html"),
    ("20260614192754", 7, "wayback/drafts_20260614_p7.html"),
    ("20260614193027", 8, "wayback/drafts_20260614_p8.html"),
    ("20260617214824", 0, "wayback/drafts_20260617_p0.html"),
    ("20260623160616", 0, "wayback/drafts_20260623_p0.html"),
    ("20260703080914", 0, "wayback/drafts_20260703_p0.html"),
    ("20260724143117", 0, "wayback/drafts_20260724_p0.html"),
    ("20260808055206", 0, "wayback/drafts_20260808_p0.html"),
    ("20260908012431", 0, "wayback/drafts_20260908_p0.html"),
    ("20260910205726", 0, "wayback/drafts_20260910_p0.html"),
]
IRS_TEXTS = (
    "i1040gi.raw.txt",
    "i1040sd.raw.txt",
    "p1040_2025.raw.txt",
    "p1040_dft.raw.txt",
    "f1040es.raw.txt",
    "rp-25-32.raw.txt",
    "rp-24-40.raw.txt",
)
REV_PROCS = {2025: "rp-24-40.pdf", 2026: "rp-25-32.pdf"}
TABLE_STATUS = {1: "joint", 2: "head_of_household", 3: "single", 4: "separate"}
TABLES = {2025: "irs_tax_table_2025.csv", 2026: "irs_tax_table_2026_draft.csv"}
PUBLICATIONS = {2025: "p1040_2025.raw.txt", 2026: "p1040_dft.raw.txt"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(name: str):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"law_sources_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def markup_text(raw: str) -> str:
    """The text of an HTML or XML document, one block per line."""
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
    text = re.sub(r"<br\s*/?>|</p>|</P>|</div>|</h\d>|</tr>|</HEAD>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text)


def extraction_name(file: str) -> str:
    stem, suffix = file.rsplit(".", 1)
    return f"{stem}.raw.txt" if suffix == "pdf" else f"{stem}.txt"


def extract(law_dir: Path, file: str) -> Path:
    source = law_dir / file
    target = law_dir / extraction_name(file)
    if file.endswith(".pdf"):
        subprocess.run(["pdftotext", "-raw", str(source), str(target)], check=True)
    else:
        raw = source.read_text(encoding="utf-8", errors="replace")
        target.write_text(markup_text(raw), encoding="utf-8")
    return target


def pdf_dates(path: Path) -> dict:
    out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True).stdout
    found = dict(
        line.split(":", 1) for line in out.splitlines() if ":" in line
    )
    return {
        key: found[name].strip()
        for key, name in (
            ("title", "Title"),
            ("created", "CreationDate"),
            ("modified", "ModDate"),
            ("pages", "Pages"),
        )
        if name in found
    }


def normalize(text: str) -> str:
    """Join words broken at a line end, then collapse white space."""
    text = text.replace("­", "")
    text = re.sub(r"-\s+", "", text)
    text = re.sub(r"(?:\.\s?){3,}", " ", text)  # worksheet dot leaders
    return re.sub(r"\s+", " ", text).strip()


def excerpts() -> list[tuple[str, str]]:
    """(source file, quoted text) for each block quote of law/excerpts.md."""
    out, source, quote = [], None, []
    lines = (LAW / "excerpts.md").read_text(encoding="utf-8").splitlines()
    for line in [*lines, ""]:
        marker = re.match(r"<!-- source: (\S+) -->", line)
        if line.startswith("> "):
            quote.append(line[2:])
            continue
        if quote:
            if source is None:
                raise SystemExit(f"a block quote names no source: {quote[0][:60]}")
            out.append((source, "\n".join(quote)))
            source, quote = None, []
        if marker:
            source = marker.group(1)
    return out


def rate_tables(layout: str, year: int) -> dict:
    """Thresholds, rates and base amounts of Tables 1 to 4 for a tax year.

    Read from the ``pdftotext -layout`` extraction, which keeps each table under
    its heading. A table has two columns ("If Taxable Income Is:" and "The Tax
    Is:") whose cells wrap over lines, so each line's right-hand text is taken by
    position and a table's right-hand column is read as one run of text.
    """
    lines = layout.splitlines()
    start = next(
        i
        for i, line in enumerate(lines)
        if f"Tax Rate Tables. For taxable years beginning in {year}" in line
    )
    right: dict[int, list[str]] = {}
    left: dict[int, list[str]] = {}
    table = None
    for line in lines[start + 1 :]:
        heading = re.match(r"\s*TABLE (\d) - Section 1\(j\)\(2\)", line)
        if heading:
            table = int(heading.group(1))
            if table == 5:
                break
            continue
        if table is None:
            continue
        for cell in re.finditer(r"\S(?:.*?\S)?(?=\s{3,}|$)", line):
            side = right if cell.start() >= 35 else left
            side.setdefault(table, []).append(cell.group(0))
    out = {}
    for number, status in TABLE_STATUS.items():
        tax = re.sub(r"\s+", " ", " ".join(right[number]))
        income = re.sub(r"\s+", " ", " ".join(left[number]))
        first = re.search(r"Not over \$([\d,]+)", income)
        rate = re.search(r"(\d+)% of the taxable income", tax)
        rows = re.findall(
            r"\$\s?([\d,]+(?:\.\d\d)?) plus (\d+)% of the excess over \$([\d,]+)",
            tax,
        )
        dollars = [int(row[2].replace(",", "")) for row in rows]
        if len(dollars) != 6 or int(first.group(1).replace(",", "")) != dollars[0]:
            raise SystemExit(f"{year} table {number}: not seven closed brackets")
        out[status] = {
            "thresholds": tuple(dollars),
            "rates": (int(rate.group(1)), *(int(row[1]) for row in rows)),
            "base_amounts_cents": tuple(
                round(float(row[0].replace(",", "")) * 100) for row in rows
            ),
        }
    return out


def listing_rows(page: str) -> list[dict]:
    """The rows of a draft-forms listing page: product, title, revision, posted."""
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, flags=re.S):
        cells = [
            re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cell))).strip()
            for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S)
        ]
        if len(cells) >= 4 and cells[0] != "Product Number":
            month, day, year = cells[3].split("/")
            rows.append(
                {
                    "product": cells[0],
                    "title": cells[1],
                    "revision": cells[2],
                    "posted": f"{year}-{month}-{day}",
                }
            )
    return rows


def is_tax_table_product(row: dict) -> bool:
    return (
        row["product"] in ("Publication 1040", "Instruction 1040")
        or row["product"].startswith("Instruction 1040 (Tax")
        or "tax table" in row["title"].lower()
        or "Tax and Earned Income Credit Tables" in row["title"]
    )


def merge(ranges: list[tuple[str, str]]) -> list[list[str]]:
    """Posting-date ranges, joined where one starts by the next day after another
    ends (ISO dates sort as text; adjacency is checked on the calendar)."""
    from datetime import date, timedelta

    merged: list[list[str]] = []
    for first, last in sorted(ranges):
        if merged:
            end = date.fromisoformat(merged[-1][1])
            if date.fromisoformat(first) <= end + timedelta(days=1):
                merged[-1][1] = max(merged[-1][1], last)
                continue
        merged.append([first, last])
    return merged


def draft_listing_history(law_dir: Path) -> dict:
    captures, seen = [], {}
    for timestamp, page, name in ARCHIVED_LISTINGS:
        saved = law_dir / name
        rows = listing_rows(saved.read_text(encoding="utf-8", errors="replace"))
        if len(rows) != 25:
            raise SystemExit(f"{name}: expected 25 listing rows, read {len(rows)}")
        size = re.search(
            r"Showing\s+[\d,]+\s*-\s*[\d,]+\s+of\s+([\d,]+)",
            re.sub(r"<[^>]+>", " ", saved.read_text(encoding="utf-8", errors="replace")),
        )
        captured = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
        query = f"?page={page}" if page else ""
        captures.append(
            {
                "captured_utc": f"{captured}T{timestamp[8:10]}:{timestamp[10:12]}Z",
                "page": page,
                "address": f"https://web.archive.org/web/{timestamp}id_/{LISTING}{query}",
                "sha256": sha256(saved.read_bytes()),
                "rows": len(rows),
                "drafts_in_the_whole_listing": int(size.group(1).replace(",", "")),
                "first_posted": min(row["posted"] for row in rows),
                "last_posted": max(row["posted"] for row in rows),
                "tax_table_products": [row for row in rows if is_tax_table_product(row)],
                "before_freeze": captured <= FREEZE,
            }
        )
        if captured <= FREEZE:
            for row in rows:
                seen[tuple(row.values())] = row
    before = [c for c in captures if c["before_freeze"]]
    current = listing_rows(
        (law_dir / "irs_drafts_1040.html").read_text(encoding="utf-8", errors="replace")
    )
    return {
        "freeze": FREEZE,
        "listing": LISTING,
        "note": (
            "Each capture is one 25-row page of the whole listing (its size at "
            "each capture is recorded below), newest posting first. A draft is listed once, at its latest posting. "
            "The captures do not show every draft posted in the period: pages "
            "for some days were not archived, and none shows a posting before "
            "the earliest date below. A range below is the earliest and latest "
            "posting date on the captured pages, not a claim that every draft "
            "posted between them is on one."
        ),
        "captures_on_or_before_freeze": len(before),
        "drafts_in_the_whole_listing_on_or_before_freeze": [
            min(c["drafts_in_the_whole_listing"] for c in before),
            max(c["drafts_in_the_whole_listing"] for c in before),
        ],
        "distinct_rows_seen_on_or_before_freeze": len(seen),
        "posting_dates_covered_on_or_before_freeze": merge(
            [(c["first_posted"], c["last_posted"]) for c in before]
        ),
        "rows_seen_on_or_before_freeze": sorted(
            seen.values(), key=lambda row: (row["posted"], row["product"], row["title"])
        ),
        "tax_table_products_listed_on_or_before_freeze": [
            row for c in before for row in c["tax_table_products"]
        ],
        "tax_table_products_listed_in_later_captures": [
            row for c in captures if not c["before_freeze"] for row in c["tax_table_products"]
        ],
        "tax_table_products_listed_on_read_date": [
            row for row in current if is_tax_table_product(row)
        ],
        "captures": captures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--law-dir", required=True)
    args = parser.parse_args()
    law_dir = Path(args.law_dir).expanduser()
    tax_table = load("tax_table")
    table_parser = load("parse_irs_tax_table")

    records = []
    for source in SOURCES:
        saved = law_dir / source["file"]
        text = extract(law_dir, source["file"])
        record = {
            key: value for key, value in source.items() if key != "file"
        } | {
            "read_on": READ_ON,
            "saved_file": {
                "name": source["file"],
                "sha256": sha256(saved.read_bytes()),
                "bytes": saved.stat().st_size,
            },
            "extraction": {
                "name": text.name,
                "made_with": (
                    "pdftotext -raw" if source["file"].endswith(".pdf") else "tags stripped"
                ),
                "sha256": sha256(text.read_bytes()),
                "bytes": text.stat().st_size,
            },
        }
        if source["file"].endswith(".pdf"):
            record["pdf"] = pdf_dates(saved)
        records.append(record)

    texts = {
        record["extraction"]["name"]: normalize(
            (law_dir / record["extraction"]["name"]).read_text(encoding="utf-8")
        )
        for record in records
    }
    checked = []
    for source, quote in excerpts():
        if source not in texts:
            raise SystemExit(f"excerpts.md names an unknown source: {source}")
        found = normalize(quote) in texts[source]
        checked.append({"source": source, "found": found, "excerpt": quote[:90]})
    missing = [c for c in checked if not c["found"]]

    schedules = {}
    for year, name in REV_PROCS.items():
        layout = subprocess.run(
            ["pdftotext", "-layout", str(law_dir / name), "-"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        read = rate_tables(layout, year)
        for status, table in read.items():
            same = (
                table["thresholds"] == tax_table.SCHEDULES[year][status]
                and table["rates"] == tax_table.RATES
                and table["base_amounts_cents"] == tax_table.BASE_AMOUNTS[year][status]
            )
            schedules[f"{year} {status}"] = same

    tables = {}
    for year, name in PUBLICATIONS.items():
        rows = table_parser.parse((law_dir / name).read_text(encoding="utf-8"))
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(table_parser.COLUMNS)
        writer.writerows(rows)
        committed = (LAW / TABLES[year]).read_text()
        built = tax_table.constructed_table(year)
        tables[str(year)] = {
            "publication": name,
            "csv": TABLES[year],
            "csv_sha256": sha256(committed.encode()),
            "parse_equals_committed_csv": buffer.getvalue() == committed,
            "amounts": 4 * len(rows),
            "amounts_equal_to_constructed_table": sum(
                row[2 + i] == built_row[status]
                for row, built_row in zip(rows, built)
                for i, status in enumerate(table_parser.COLUMNS[2:])
            ),
        }

    # "middle initial" is the name line of Form 1040-ES's payment vouchers.
    midpoint = {
        name: len(
            re.findall(
                r"midpoint|mid-point|middle(?! initial)",
                (law_dir / name).read_text(encoding="utf-8"),
                flags=re.I,
            )
        )
        for name in IRS_TEXTS
    }
    history = draft_listing_history(law_dir)
    (LAW / "draft_listing_history.json").write_text(
        json.dumps(history, indent=2) + "\n"
    )
    act = texts["plaw119-21.txt"]
    check = {
        "read_on": READ_ON,
        "excerpts": len(checked),
        "excerpts_found": len(checked) - len(missing),
        "excerpts_not_found": missing,
        "by_source": {
            source: sum(c["source"] == source for c in checked)
            for source in sorted({c["source"] for c in checked})
        },
        "rate_tables_equal_to_tax_table_py": schedules,
        "tax_tables": tables,
        "occurrences_of_midpoint_or_middle": midpoint,
        "pub_l_119_21_amends_section_3": bool(
            re.search(r"Section 3\(a\) is amended|tax tables for individuals", act, re.I)
        ),
        "tax_table_drafts_listed_on_or_before_freeze": len(
            history["tax_table_products_listed_on_or_before_freeze"]
        ),
    }
    ok = (
        not missing
        and all(schedules.values())
        and all(t["parse_equals_committed_csv"] for t in tables.values())
        and all(t["amounts_equal_to_constructed_table"] == t["amounts"] for t in tables.values())
        and not any(midpoint.values())
        and not check["pub_l_119_21_amends_section_3"]
        and not check["tax_table_drafts_listed_on_or_before_freeze"]
    )
    check["all_checks_pass"] = ok
    (LAW / "sources.json").write_text(
        json.dumps(
            {
                "read_on": READ_ON,
                "committed": (
                    "law/excerpts.md and the two Tax Table CSVs. No whole document "
                    "is committed; each is public at the address given."
                ),
                "copyright": (
                    "Works of the United States Government; no copyright "
                    "(17 U.S.C. 105)."
                ),
                "sources": records,
            },
            indent=2,
        )
        + "\n"
    )
    (LAW / "excerpts_check.json").write_text(json.dumps(check, indent=2) + "\n")
    print(json.dumps(check, indent=2))
    if not ok:
        raise SystemExit("a law check failed")


if __name__ == "__main__":
    main()
