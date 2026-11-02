"""Check which states prescribe an income tax table, and count the references there.

A scoped follow-up to the federal audit, not an audit of the states: it records
which states' resident instructions prescribe a tax table below an income
ceiling, and how many scored state income tax references sit in those states. It
does not construct any state's table or recompute any reference.

law/state_tax_table_claims.json holds one row per state (the 21 states with a
nonzero scored state income tax reference in the release), as a research lane
read each state's instructions. This script fetches each address, extracts the
text (``pdftotext -raw`` for a PDF, tags stripped otherwise) and checks each
quotation against it, ignoring white space, case and typographic quote marks,
because several states' PDFs carry text with the spaces missing. It then counts
the release's scored state income tax references by state.

  python3 -I reference_audit/2026-10-10-tax-table/scripts/state_tax_tables.py \\
    --dir ~/reviews/policybench-tax-table-2026-10-10/state_documents

Writes verification/state_tax_tables.json. Standard library, curl and poppler.
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
CLAIMS = HERE / "law/state_tax_table_claims.json"
OUT = HERE / "verification/state_tax_tables.json"
STATE_TAX = "state_income_tax_before_refundable_credits"
AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)


def release():
    path = Path(__file__).with_name("release.py")
    spec = importlib.util.spec_from_file_location("state_tables_release", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetch(url: str, directory: Path) -> Path:
    target = directory / hashlib.sha256(url.encode()).hexdigest()[:16]
    if not target.exists():
        subprocess.run(
            ["curl", "-sS", "-L", "--compressed", "--max-time", "180", "-A", AGENT]
            + ["-o", str(target), url],
            check=True,
        )
    return target


def text_of(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:5] == b"%PDF-":
        return subprocess.run(
            ["pdftotext", "-raw", str(path), "-"], capture_output=True, check=True
        ).stdout.decode("utf-8", errors="replace")
    page = raw.decode("utf-8", errors="replace")
    page = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", page))


def squeeze(text: str) -> str:
    """Lower case, typographic marks made plain, words broken at a line end
    joined, and every space removed."""
    for mark, plain in (
        ("’", "'"),
        ("‘", "'"),
        ("“", '"'),
        ("”", '"'),
        ("–", "-"),
        ("—", "-"),
        ("­", ""),
        (" ", " "),
    ):
        text = text.replace(mark, plain)
    text = re.sub(r"-\s*\n\s*", "", text)  # a word broken at a line end
    return re.sub(r"\s+", "", text).lower()


def reference_counts() -> dict[str, dict[str, int]]:
    source = release()
    scenarios = csv.DictReader(io.StringIO(source.read("scenarios.csv").decode()))
    state = {row["scenario_id"]: row["state"] for row in scenarios}
    excluded = {
        (e["scenario_id"], e["variable"])
        for e in json.loads(source.read("reference_exclusions.json"))["exclusions"]
    }
    counts: dict[str, dict[str, int]] = {}
    rows = csv.DictReader(io.StringIO(source.read("reference_outputs.csv").decode()))
    for row in rows:
        key = (row["scenario_id"], row["variable"])
        if row["variable"] != STATE_TAX or key in excluded:
            continue
        value = float(row["value"])
        entry = counts.setdefault(
            state[row["scenario_id"]], {"scored": 0, "nonzero": 0, "with_cents": 0}
        )
        entry["scored"] += 1
        entry["nonzero"] += abs(value) > 1e-6
        entry["with_cents"] += abs(value - round(value)) > 0.005
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, help="where fetched documents are kept")
    args = parser.parse_args()
    directory = Path(args.dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)

    claims = json.loads(CLAIMS.read_text(encoding="utf-8"))
    counts = reference_counts()
    states = []
    for claim in claims["states"]:
        checks = []
        for quote_key, url_key in (("quote", "url"), ("second_quote", "second_url")):
            if not claim.get(quote_key):
                continue
            saved = fetch(claim[url_key], directory)
            checks.append(
                {
                    "quote": claim[quote_key],
                    "url": claim[url_key],
                    "document_sha256": hashlib.sha256(saved.read_bytes()).hexdigest(),
                    "document_bytes": saved.stat().st_size,
                    "found": squeeze(claim[quote_key]) in squeeze(text_of(saved)),
                }
            )
        states.append(
            {
                "state": claim["state"],
                "instructions_tax_year": claim["tax_year"],
                "table_prescribed": claim["table_prescribed"].startswith("yes"),
                "ceiling": claim["ceiling"],
                "mandatory": claim["mandatory"],
                "band_width_as_reported": claim["band_width"],
                "note": claim.get("note", ""),
                "quotations": checks,
                "every_quotation_found": all(check["found"] for check in checks),
                "scored_state_references": counts.get(claim["state"], {}).get(
                    "scored", 0
                ),
                "scored_nonzero_state_references": counts.get(claim["state"], {}).get(
                    "nonzero", 0
                ),
                "scored_nonzero_references_with_cents": counts.get(
                    claim["state"], {}
                ).get("with_cents", 0),
            }
        )

    table_states = [s for s in states if s["table_prescribed"]]
    must = [
        s
        for s in table_states
        if s["mandatory"].startswith("mandatory")
    ]
    covered = {s["state"] for s in states}
    nonzero_elsewhere = {
        state: entry["nonzero"]
        for state, entry in sorted(counts.items())
        if entry["nonzero"] and state not in covered
    }
    result = {
        "read_on": claims["read_on"],
        "scope": (
            "Which states prescribe a tax table and how many scored references "
            "sit there. No state's table is constructed and no reference is "
            "recomputed."
        ),
        "how": claims["how"],
        "states_checked": len(states),
        "every_quotation_found": all(s["every_quotation_found"] for s in states),
        "states_with_a_table": [s["state"] for s in table_states],
        "states_without_a_table": [
            s["state"] for s in states if not s["table_prescribed"]
        ],
        "states_where_the_table_is_mandatory": [s["state"] for s in must],
        "scored_nonzero_state_references": {
            "all_states": sum(entry["nonzero"] for entry in counts.values()),
            "in_states_checked": sum(
                s["scored_nonzero_state_references"] for s in states
            ),
            "in_states_with_a_table": sum(
                s["scored_nonzero_state_references"] for s in table_states
            ),
            "in_states_where_the_table_is_mandatory": sum(
                s["scored_nonzero_state_references"] for s in must
            ),
            "with_cents_in_states_with_a_table": sum(
                s["scored_nonzero_references_with_cents"] for s in table_states
            ),
            "in_states_not_checked": nonzero_elsewhere,
        },
        "states": states,
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    for s in states:
        print(
            f"{s['state']}  table={'yes' if s['table_prescribed'] else 'no ':3s} "
            f"found={s['every_quotation_found']!s:5s} "
            f"nonzero={s['scored_nonzero_state_references']}  {s['ceiling'][:60]}"
        )
    summary = {k: v for k, v in result.items() if k not in ("states", "how", "scope")}
    print(json.dumps(summary, indent=2))
    if not result["every_quotation_found"]:
        raise SystemExit("a quotation was not found in its document")


if __name__ == "__main__":
    main()
