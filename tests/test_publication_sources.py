"""The publication-source check classifies citations, dates and value origins."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from policybench.publication_sources import (
    CITATION_KINDS,
    COMPUTED_ORIGINS,
    FLAGS,
    FREEZE_DATE,
    ORIGINS,
    PUBLICATION_FLAGS,
    SOURCE_CLASSES,
    SUPPORT_TIERS,
    DateEvidence,
    ancestor_names,
    build_entry,
    build_report,
    citation_host,
    citation_kind,
    classify_citation,
    classify_origin,
    comment_computation,
    congress_years,
    dumps_report,
    entry_comments,
    evaluate_arithmetic,
    expand_report,
    explicit_support,
    extract_applies_to_year,
    extract_publication_date,
    normalize_references,
    parameter_category,
    parameter_key_path,
    pre_freeze_status,
    same_value,
    source_class,
    stated_years,
    summarize,
    supports_2026_value,
    value_flags,
)

ROOT = Path(__file__).resolve().parents[1]
REPORT = (
    ROOT
    / "reference_audit/2026-10-05-reference-adversary/verification"
    / "publication_sources.json"
)

# policyengine-us 2.15.17,
# parameters/gov/states/la/tax/income/deductions/standard/amount.yaml, verbatim.
LOUISIANA_YAML = """\
description: Louisiana provides the following standard deduction amount, based on filing status.
metadata:
  period: year
  unit: currency-USD
  label: Louisiana standard deduction amount
  uprating: gov.bls.cpi.cpi_u
  propagate_metadata_to_children: true
  breakdown:
    - filing_status
  reference:
    - title: Louisiana Revised Statutes, RS 47:294 - Standard deduction
      href: https://www.legis.la.gov/legis/Law.aspx?d=101761
    - title: Louisiana Register, February 20, 2026, Income Tax Withholding Tables notice
      href: https://bese.louisiana.gov/docs/default-source/rulemaking-docket/feb-louisiana-register.pdf#page=127
    - title: Consumer Price Index News Release - 2025 M12 Results
      href: https://www.bls.gov/news.release/archives/cpi_01132026.htm
    - title: 2025 Louisiana Resident Income Tax Return Instructions, Line 8
      href: https://dam.ldr.la.gov/taxforms/IT540i%20WEB(2025)D11.pdf#page=3

SINGLE:
  2025-01-01: 12_500
  # 2026 amount applies the December-to-December 2025 CPI-U increase:
  # 12,500 * (324.054 / 315.605), rounded to the nearest dollar.
  2026-01-01: 12_835
SURVIVING_SPOUSE:
  2025-01-01: 25_000
  2026-01-01: 25_670
SEPARATE:
  2025-01-01: 12_500
  2026-01-01: 12_835
# The legal code defines the HoH and Joint amounts as 200% of the
# Single amount.
HEAD_OF_HOUSEHOLD:
  2025-01-01: 25_000
  2026-01-01: 25_670
JOINT:
  2025-01-01: 25_000
  2026-01-01: 25_670
"""  # noqa: E501, W291

LOUISIANA_REFERENCES = [
    {
        "title": "Louisiana Revised Statutes, RS 47:294 - Standard deduction",
        "href": "https://www.legis.la.gov/legis/Law.aspx?d=101761",
    },
    {
        "title": "Louisiana Register, February 20, 2026, Income Tax Withholding "
        "Tables notice",
        "href": "https://bese.louisiana.gov/docs/default-source/rulemaking-docket/"
        "feb-louisiana-register.pdf#page=127",
    },
    {
        "title": "Consumer Price Index News Release - 2025 M12 Results",
        "href": "https://www.bls.gov/news.release/archives/cpi_01132026.htm",
    },
    {
        "title": "2025 Louisiana Resident Income Tax Return Instructions, Line 8",
        "href": "https://dam.ldr.la.gov/taxforms/IT540i%20WEB(2025)D11.pdf#page=3",
    },
]
REV_PROC_2025_32 = (
    "2026 IRS data release",
    "https://www.irs.gov/pub/irs-drop/rp-25-32.pdf#page=18",
)
LAW_PREFIX = "gov.states.la.tax.income.deductions.standard.amount"


def _louisiana_fact(status: str = "SINGLE", value: float = 12_835) -> dict:
    return {
        "parameter": f"{LAW_PREFIX}.{status}",
        "value": value,
        "entry_instant": "2026-01-01",
        "baseline_value": value,
        "baseline_entry_instant": "2026-01-01",
        "origin": "explicit_2026",
        "baseline_origin": "explicit_2026",
        "origin_detail": {"yaml_entry": "2026-01-01"},
        "convention_modules": [],
        "indexed_parameter": True,
        "uprating": "gov.bls.cpi.cpi_u",
        "unit": "currency-USD",
        "yaml_file": "policyengine_us/parameters/gov/states/la/tax/income/"
        "deductions/standard/amount.yaml",
        "yaml_key_path": [status],
        "yaml_comments": entry_comments(LOUISIANA_YAML, [status], "2026-01-01"),
        "references": normalize_references(LOUISIANA_REFERENCES),
        "instants": ["2026-01-01"],
        "scored_cells": ["scenario_038/state_income_tax_before_refundable_credits"],
        "unscored_cells": [],
    }


def _fact(parameter: str, origin: str, references=(), **extra) -> dict:
    fact = {
        "parameter": parameter,
        "value": 100.0,
        "entry_instant": "2026-01-01",
        "origin": origin,
        "convention_modules": [],
        "references": normalize_references(list(references)),
        "yaml_comments": [],
        "instants": ["2026-01-01"],
        "scored_cells": ["scenario_001/snap"],
        "unscored_cells": [],
    }
    fact.update(extra)
    return fact


# ---------------------------------------------------------------------------
# Louisiana, the motivating case
# ---------------------------------------------------------------------------


def test_louisiana_comment_is_found_beside_the_single_2026_entry():
    assert entry_comments(LOUISIANA_YAML, ["SINGLE"], "2026-01-01") == [
        "2026 amount applies the December-to-December 2025 CPI-U increase:",
        "12,500 * (324.054 / 315.605), rounded to the nearest dollar.",
    ]
    assert entry_comments(LOUISIANA_YAML, ["SINGLE"], "2025-01-01") == []
    # The HoH comment sits above the key, not above a dated entry.
    assert entry_comments(LOUISIANA_YAML, ["HEAD_OF_HOUSEHOLD"], "2026-01-01") == []
    assert entry_comments(LOUISIANA_YAML, ["JOINT"], "2026-01-01") == []
    assert entry_comments(LOUISIANA_YAML, ["MISSING"], "2026-01-01") == []


def test_louisiana_comment_arithmetic_reproduces_the_value():
    comments = entry_comments(LOUISIANA_YAML, ["SINGLE"], "2026-01-01")
    evidence = comment_computation(comments, 12_835)
    assert evidence["computation"] is True
    assert evidence["keywords"] == ["cpi-u"]
    [expression] = evidence["expressions"]
    assert expression["text"] == "12,500 * (324.054 / 315.605)"
    assert expression["result"] == pytest.approx(12_500 * 324.054 / 315.605)
    assert expression["matches_value"] is True
    # The same arithmetic does not reproduce the department's published amounts.
    assert (
        comment_computation(comments, 12_838)["expressions"][0]["matches_value"]
        is False
    )


def test_louisiana_citations_classify_as_none_publishing_the_2026_amount():
    statute, register, cpi, instructions = [
        classify_citation(item["title"], item["href"]) for item in LOUISIANA_REFERENCES
    ]
    assert (statute["source_class"], statute["kind"]) == ("government", "statute")
    assert statute["publication_date"] is None and statute["pre_freeze"] is None

    assert (register["source_class"], register["kind"]) == (
        "government",
        "withholding",
    )
    assert register["publication_date"]["latest"] == "2026-02-20"
    assert register["pre_freeze"] is True
    assert register["dated_for_2026"] is True

    assert cpi["host"] == "bls.gov" and cpi["kind"] == "index_data"
    assert cpi["publication_date"]["latest"] == "2026-01-13"

    assert instructions["kind"] == "agency_publication"
    assert instructions["applies_to_year"] == 2025
    assert not any(
        c["dated_2026_publication"] for c in (statute, register, cpi, instructions)
    )


def test_louisiana_entries_are_flagged():
    single = build_entry(_louisiana_fact("SINGLE"))
    assert single["flags"] == [
        "explicit_2026_without_2026_publication",
        "computed_in_yaml_comment",
    ]
    assert single["explicit_2026_support"] == "inputs_only"
    assert single["publication_review"] is True
    joint = build_entry(_louisiana_fact("JOINT", 25_670))
    assert joint["flags"] == ["explicit_2026_without_2026_publication"]
    # A Rev. Proc.-style 2026 publication among its citations clears the flag.
    published = _louisiana_fact("JOINT", 25_670)
    published["references"] += normalize_references(
        [{"title": REV_PROC_2025_32[0], "href": REV_PROC_2025_32[1]}]
    )
    assert build_entry(published)["flags"] == []


def test_louisiana_section_of_the_markdown():
    facts = [_louisiana_fact("SINGLE"), _louisiana_fact("JOINT", 25_670)]
    report, markdown = build_report(facts, [], {"policyengine_us": "2.15.17"})
    assert "## Louisiana standard deduction" in markdown
    assert f"`{LAW_PREFIX}.SINGLE` = 12,835" in markdown
    assert "reproduces the value: True" in markdown
    assert "0 of the 4 citations is a candidate 2026 publication" in markdown
    assert (
        report["summary"]["by_flag"]["explicit_2026_without_2026_publication"]["values"]
        == 2
    )
    json.dumps(report)


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "earliest", "latest", "precision"),
    [
        ("Louisiana Register, February 20, 2026, notice", "2026-02-20", None, "day"),
        ("Feb. 3 2025 release", "2025-02-03", None, "day"),
        ("published 20 February 2026", "2026-02-20", None, "day"),
        ("https://x.gov/archives/cpi_01132026.htm", "2026-01-13", None, "day"),
        ("https://x.gov/data/20251009-table.pdf", "2025-10-09", None, "day"),
        (
            "https://www.federalregister.gov/documents/2025/10/09/x",
            "2025-10-09",
            None,
            "day",
        ),  # noqa: E501
        ("Tax News, October 2025", "2025-10-01", "2025-10-31", "month"),
        (
            "https://a.gov/system/files/2026/02/x.xlsx",
            "2026-02-01",
            "2026-02-28",
            "month",
        ),  # noqa: E501
        ("Rev. Proc. 2025-32", "2025-01-01", "2025-12-31", "year"),
        ("Revenue Procedure 2024-40, section 3", "2024-01-01", "2024-12-31", "year"),
        (
            "https://www.irs.gov/pub/irs-drop/rp-25-32.pdf",
            "2025-01-01",
            "2025-12-31",
            "year",
        ),  # noqa: E501
        ("Notice 2025-67", "2025-01-01", "2025-12-31", "year"),
        ("https://www.irs.gov/irb/2025-45_IRB", "2025-01-01", "2025-12-31", "year"),
        ("91 FR 1797", "2026-01-01", "2026-12-31", "year"),
        ("90 Fed. Reg. 5000", "2025-01-01", "2025-12-31", "year"),
        ("RIB 26-019", "2026-01-01", "2026-12-31", "year"),
    ],
)
def test_publication_dates(text, earliest, latest, precision):
    evidence = extract_publication_date(text)
    assert evidence is not None
    assert evidence.earliest.isoformat() == earliest
    assert evidence.latest.isoformat() == (latest or earliest)
    assert evidence.precision == precision


@pytest.mark.parametrize(
    "text",
    [None, "", "26 U.S. Code § 63(c)", "Standard deduction", "2025 M12", "13 FR"],
)
def test_no_publication_date(text):
    assert extract_publication_date(text) is None


def test_most_precise_then_latest_date_wins():
    evidence = extract_publication_date("Rev. Proc. 2025-32, released October 9, 2025")
    assert evidence.precision == "day" and evidence.latest == date(2025, 10, 9)
    evidence = extract_publication_date("January 2025 and March 2026 tables")
    assert evidence.latest == date(2026, 3, 31)


@pytest.mark.parametrize(
    ("title", "href", "year"),
    [
        ("2025 Louisiana Resident Income Tax Return Instructions, Line 8", None, 2025),
        ("Publication 15-T (2026)", None, 2026),
        ("Tax Year 2026 rates", None, 2026),
        ("SNAP FY 2026 Cost-of-Living Adjustments", None, 2026),
        ("HUD CY2026 Inflation-Adjusted Values (Table 1)", None, 2026),
        ("Medicare Part B premium for 2026", None, 2026),
        ("2026 Poverty Guidelines", None, 2026),
        (None, "https://dam.ldr.la.gov/taxforms/IT540i%20WEB(2025)D11.pdf", 2025),
        (None, "https://www.ftb.ca.gov/forms/2025/2025-540-booklet.html", 2025),
        (None, "https://www.irs.gov/pub/irs-prior/p526--2020.pdf", 2020),
        ("Rev. Proc. 2025-32", None, None),
        ("Louisiana Register, February 20, 2026, notice", None, None),
        ("Standard deduction", "https://example.gov/x", None),
    ],
)
def test_applies_to_year(title, href, year):
    assert extract_applies_to_year(title, href) == year


@pytest.mark.parametrize(
    ("evidence", "applies", "expected"),
    [
        (DateEvidence(date(2026, 7, 2), date(2026, 7, 2), "day", ""), None, True),
        (DateEvidence(date(2026, 7, 3), date(2026, 7, 3), "day", ""), None, False),
        (DateEvidence(date(2026, 1, 1), date(2026, 12, 31), "year", ""), None, None),
        (DateEvidence(date(2025, 1, 1), date(2025, 12, 31), "year", ""), 2030, True),
        (None, 2024, True),
        (None, 2025, None),
        (None, 2027, None),
        (None, 2028, False),
        (None, None, None),
    ],
)
def test_pre_freeze_status(evidence, applies, expected):
    assert FREEZE_DATE == date(2026, 7, 3)
    assert pre_freeze_status(evidence, applies) is expected


def test_stated_years_reads_long_digit_runs_and_short_forms():
    assert stated_years("cpi_01132026.htm") == {2026}
    assert stated_years("91 FR 1797") == {2026}
    assert stated_years("irs-drop/rp-25-32.pdf and RIB 26-019") == {2025, 2026}
    assert stated_years("no years here") == set()
    assert stated_years(None) == set()


def test_congress_years():
    assert congress_years(
        "https://www.congress.gov/bill/119th-congress/house-bill/1/text"
    ) == {2025, 2026}
    assert congress_years("One Big Beautiful Bill Act, Pub. L. No. 119-21") == {
        2025,
        2026,
    }
    assert congress_years("PLAW-115publ97") == {2017, 2018}
    assert congress_years("26 U.S. Code § 63") == set()


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("href", "host", "source"),
    [
        ("https://www.irs.gov/pub/irs-drop/rp-25-32.pdf", "irs.gov", "government"),
        ("www.legis.la.gov/legis/Law.aspx?d=1", "legis.la.gov", "government"),
        ("https://www.nj.state.us/x", "nj.state.us", "government"),
        (
            "https://www.oscn.net/applications/oscn/DeliverDocument.asp?CiteID=1",
            "oscn.net",
            "government",
        ),  # noqa: E501
        (
            "https://www.law.cornell.edu/uscode/text/26/63",
            "law.cornell.edu",
            "law_republisher",
        ),  # noqa: E501
        ("https://law.justia.com/codes/x", "law.justia.com", "law_republisher"),
        ("https://casetext.com/regulation/x", "casetext.com", "law_republisher"),
        ("https://www.kff.org/medicaid/x", "kff.org", "other"),
        ("https://docs.google.com/spreadsheets/d/x", "docs.google.com", "other"),
        (
            "https://web.archive.org/web/20240101000000/https://www.ssa.gov/oact/cola/",
            "ssa.gov",
            "government",
        ),
    ],
)
def test_hosts_and_source_classes(href, host, source):
    assert citation_host(href) == host
    assert source_class(None, href) == source


def test_title_only_citations():
    assert source_class("26 U.S.C. 63(c)", None) == "government"
    assert source_class("Rev. Proc. 2025-32", None) == "government"
    assert source_class("PolicyEngine estimate", None) == "other"
    assert citation_host(None) is None


@pytest.mark.parametrize(
    ("title", "href", "kind"),
    [
        (
            "CPI-U, U.S. city average",
            "https://data.bls.gov/timeseries/CUSR0000SA0",
            "index_data",
        ),  # noqa: E501
        ("Budget and Economic Outlook", None, "index_data"),
        (
            "Publication 15-T (2026), Federal Income Tax Withholding Methods",
            None,
            "withholding",
        ),  # noqa: E501
        (
            "7 CFR 273.9(d)(1)",
            "https://www.ecfr.gov/current/title-7/section-273.9",
            "regulation",
        ),  # noqa: E501
        ("Annual Update of the HHS Poverty Guidelines, 91 FR 1797", None, "register"),
        (
            "Federal Register notice",
            "https://www.federalregister.gov/d/2026-01",
            "register",
        ),  # noqa: E501
        ("Rev. Proc. 2025-32", None, "agency_publication"),
        ("2025 Form 540 Instructions", None, "agency_publication"),
        ("Louisiana Revised Statutes, RS 47:294", None, "statute"),
        (
            "26 U.S. Code § 63(c)",
            "https://www.law.cornell.edu/uscode/text/26/63",
            "statute",
        ),  # noqa: E501
        (
            "RS 47:32 - Rates of tax",
            "https://www.legis.la.gov/legis/Law.aspx?d=1",
            "statute",
        ),  # noqa: E501
        (
            "H.R.1 - One Big Beautiful Bill Act",
            "https://www.congress.gov/bill/119th-congress/house-bill/1/text",
            "statute",
        ),  # noqa: E501
        (
            "SSI Federal Payment Amounts",
            "https://www.ssa.gov/oact/cola/SSIamts.html",
            "agency_publication",
        ),  # noqa: E501
        (
            "Medicare Savings Programs",
            "https://www.medicare.gov/basics/costs",
            "agency_publication",
        ),  # noqa: E501
        ("Some blog post", "https://example.com/post", "other"),
    ],
)
def test_citation_kinds(title, href, kind):
    assert citation_kind(title, href) == kind


def test_dated_2026_publication_rules():
    rev_proc = classify_citation(*REV_PROC_2025_32)
    assert rev_proc["dated_2026_publication"] is True
    assert rev_proc["pre_freeze"] is True
    # Issued for 2025: not a 2026 publication even though it is pre-freeze.
    old = classify_citation(
        "2025 IRS data release", "https://www.irs.gov/pub/irs-drop/rp-24-40.pdf"
    )
    assert old["pre_freeze"] is True and old["dated_2026_publication"] is False
    # A register notice dated 2026 counts; a 2026 statute does not.
    fpg = classify_citation("Annual Update of the HHS Poverty Guidelines, 91 FR 1797")
    assert fpg["kind"] == "register" and fpg["dated_2026_publication"] is True
    obbba = classify_citation(
        "One Big Beautiful Bill Act, Pub. L. No. 119-21, § 70404 (2025)",
        "https://www.govinfo.gov/content/pkg/PLAW-119publ21/html/PLAW-119publ21.htm",
    )
    assert obbba["kind"] == "statute" and obbba["recent_law"] is True
    assert obbba["dated_2026_publication"] is False
    # A statute's stated date is an effective date, not a publication date.
    effective = classify_citation(
        "ESSB 6346, Sec. 1205 (takes effect January 1, 2029)",
        "https://lawfilesext.leg.wa.gov/biennium/2025-26/Pdf/Bills/6346-S.PL.pdf",
    )
    assert effective["kind"] == "statute" and effective["pre_freeze"] is None
    assert effective["recent_law"] is True
    # Dated after the freeze: never a 2026 publication.
    late = classify_citation(
        "Revenue Information Bulletin RIB 26-019, September 28, 2026",
        "https://revenue.louisiana.gov/x.pdf",
    )
    assert late["pre_freeze"] is False and late["dated_2026_publication"] is False
    # Not a government source: never a 2026 publication.
    blog = classify_citation("2026 Tax Brackets", "https://taxfoundation.org/x")
    assert blog["source_class"] == "other" and blog["dated_2026_publication"] is False


def test_index_release_supports_only_an_economic_series():
    cbo = classify_citation(
        "CBO | Economic Projections | February 2026",
        "https://www.cbo.gov/system/files/2026-02/51135-2026-02-Economic-Projections.xlsx",
    )
    assert cbo["kind"] == "index_data" and cbo["dated_for_2026"] is True
    assert supports_2026_value(cbo, "economic_series") is True
    assert supports_2026_value(cbo, "law") is False
    assert explicit_support([cbo], "law") == "inputs_only"
    assert explicit_support([cbo], "economic_series") == "2026_publication"


def test_explicit_support_tiers():
    undated = classify_citation(
        "SSI Federal Payment Amounts", "https://www.ssa.gov/oact/cola/SSIamts.html"
    )
    obbba = classify_citation(
        "H.R.1 - One Big Beautiful Bill Act",
        "https://www.congress.gov/bill/119th-congress/house-bill/1/text",
    )
    lii = classify_citation(
        "26 U.S. Code § 63", "https://www.law.cornell.edu/uscode/text/26/63"
    )
    assert explicit_support([undated, obbba, lii]) == "undated_publication"
    assert explicit_support([obbba, lii]) == "recent_law"
    assert explicit_support([lii]) == "other"
    assert explicit_support([]) == "other"
    assert set(SUPPORT_TIERS) >= {"2026_publication", "inputs_only"}


def test_normalize_references_shapes():
    assert normalize_references(None) == []
    assert normalize_references({"title": "A", "href": "https://a.gov"}) == [
        {"title": "A", "href": "https://a.gov", "level": "parameter"}
    ]
    assert normalize_references(["https://a.gov/x", "Some title", 7, {}], "value") == [
        {"title": None, "href": "https://a.gov/x", "level": "value"},
        {"title": "Some title", "href": None, "level": "value"},
    ]


# ---------------------------------------------------------------------------
# YAML paths, comments and arithmetic
# ---------------------------------------------------------------------------


def test_parameter_key_paths_and_ancestors():
    assert parameter_key_path("gov.x.amount.SINGLE", "gov.x.amount") == ["SINGLE"]
    assert parameter_key_path("gov.x.amount", "gov.x.amount") == []
    assert parameter_key_path("gov.x.rates[1].threshold", "gov.x.rates") == [
        "[1]",
        "threshold",
    ]
    assert parameter_key_path("gov.x.amounts.SINGLE", "gov.x.amount") is None
    assert parameter_key_path("gov.x.size.3", "gov.x") == ["size", "3"]
    assert ancestor_names("gov.x.rates[1].threshold") == [
        "gov.x.rates[1]",
        "gov.x.rates",
        "gov.x",
        "gov",
    ]
    assert ancestor_names("gov") == []


SCALE_YAML = """\
description: A scale.
brackets:
  - threshold:
      2025-01-01: 0
    rate:
      2025-01-01: 0.1
  - threshold:
      values:
        # Indexed: 11,000 * 1.03
        2026-01-01: 11_330  # rounded
    rate:
      2025-01-01: 0.2
metadata:
  type: marginal_rate
"""

COMPACT_YAML = """\
brackets:
- threshold:
    '2026-01-01': 5
  amount:
    # first amount
    2026-01-01: 1
- amount:
    # second amount
    2026-01-01: 2
1:
  # household of one
  2026-01-01: 7
"""


def test_entry_comments_in_scales_and_compact_lists():
    assert entry_comments(SCALE_YAML, ["[1]", "threshold"], "2026-01-01") == [
        "Indexed: 11,000 * 1.03",
        "rounded",
    ]
    assert entry_comments(SCALE_YAML, ["[0]", "rate"], "2025-01-01") == []
    assert entry_comments(COMPACT_YAML, ["[0]", "amount"], "2026-01-01") == [
        "first amount"
    ]
    assert entry_comments(COMPACT_YAML, ["[1]", "amount"], "2026-01-01") == [
        "second amount"
    ]
    assert entry_comments(COMPACT_YAML, ["[0]", "threshold"], "2026-01-01") == []
    assert entry_comments(COMPACT_YAML, ["1"], "2026-01-01") == ["household of one"]


def test_evaluate_arithmetic_reads_only_numbers_and_operators():
    assert evaluate_arithmetic("12,500 * (324.054 / 315.605)")[0][1] == pytest.approx(
        12_500 * 324.054 / 315.605
    )
    assert evaluate_arithmetic("1_000 × 2 ÷ 4") == [("1_000 × 2 ÷ 4", 500.0)]
    assert evaluate_arithmetic("2025-01-01 to 2026-01-01") == []
    assert evaluate_arithmetic("__import__('os').system('true') * 2") == []
    assert evaluate_arithmetic("divide 5 / 0") == []
    assert evaluate_arithmetic("") == []


def test_comment_computation_keywords_and_absent_comments():
    assert comment_computation([], 1.0) is None
    evidence = comment_computation(["Projected from CBO"], 1.0)
    assert evidence["computation"] is True and evidence["keywords"] == ["projected"]
    plain = comment_computation(["Amount from Rev. Proc. 2025-32"], 32_200)
    assert plain["computation"] is False


@pytest.mark.parametrize(
    ("comments", "value", "computed"),
    [
        # Comments from policyengine-us 2.15.17 YAML (see the engine report).
        (
            [
                "FY2025 value times the FNS simplified-process CPI factor (1.027);",
                "see the note on Louisiana in limited/active.yaml.",
            ],
            258,
            True,
        ),
        (
            [
                "2026 is a statutory projection (cutoff = year - 66 under the age-67",
                "rule of MCL 206.30(9)(e)); the TY2026 MI-1040 booklet is not yet "
                "published.",
            ],
            1960,
            True,
        ),
        (
            [
                "Indexed annually for inflation (national CPI-U) from 2027-01-01;",
                "update when DOR publishes adjusted amounts.",
            ],
            41_000,
            False,
        ),
        (
            [
                "HUD CY2026 inflationary adjustment (CPI-W, rounded down to a $25 "
                "multiple)."
            ],
            550,
            False,
        ),
        (["2/37"], 0.05405405, False),
        (["In 2022 the taxable social security is calculated separately."], 1, False),
    ],
)
def test_comment_computation_on_real_comments(comments, value, computed):
    assert comment_computation(comments, value)["computation"] is computed


# ---------------------------------------------------------------------------
# Origins and flags
# ---------------------------------------------------------------------------


def _origin(**overrides):
    arguments = {
        "entry_instant": "2026-01-01",
        "value": 10.0,
        "yaml_entries": {"2026-01-01": {"value": 10}},
        "uprated_instants": set(),
        "interpolated": False,
        "load_updates": [],
        "reference_value": 10.0,
        "convention_modules": [],
    }
    arguments.update(overrides)
    return classify_origin(**arguments)


def test_classify_origin_branches():
    assert _origin()[:2] == ("explicit_2026", "explicit_2026")
    assert _origin(
        entry_instant="2025-01-01", yaml_entries={"2025-01-01": {"value": 10}}
    )[:2] == ("carried_forward", "carried_forward")
    assert _origin(yaml_entries={}, uprated_instants={"2026-01-01"})[:2] == (
        "uprated",
        "uprated",
    )
    assert _origin(yaml_entries={}, interpolated=True)[1] == "interpolated"
    origin, baseline, detail = _origin(
        yaml_entries={}, load_updates=[{"caller": "uprating_extensions.py:f"}]
    )
    assert baseline == "computed_at_load"
    assert detail["writers"] == ["uprating_extensions.py:f"]
    origin, baseline, detail = _origin(
        entry_instant="2015-01-01",
        yaml_entries={"2026-08-01": {"value": 10}},
        load_updates=[
            {"caller": "policyengine_us/tools/parameters.py:backdate_parameters"}
        ],
    )
    assert baseline == "backdated" and detail["backdated_from"] == "2026-08-01"
    assert _origin(yaml_entries=None)[1] == "created_at_load"
    assert _origin(yaml_entries={"2026-01-01": {"value": 11}})[1] == "unresolved"
    assert _origin(entry_instant=None)[1] == "unresolved"
    # YAML wins over an uprating entry at the same date with the same value.
    assert _origin(uprated_instants={"2026-01-01"})[1] == "explicit_2026"
    origin, baseline, detail = _origin(convention_modules=["latest_c_ca_hold_2025"])
    assert (origin, baseline) == ("convention", "explicit_2026")
    assert detail["convention_modules"] == ["latest_c_ca_hold_2025"]
    assert _origin(reference_value=9.0)[:2] == ("convention", "explicit_2026")


def test_value_flags_each_flag():
    gov = classify_citation(*REV_PROC_2025_32)
    lii = classify_citation("26 U.S.C. 63", "https://www.law.cornell.edu/uscode/26/63")
    late = classify_citation("Bulletin, September 28, 2026", "https://tax.la.gov/x")
    assert value_flags("explicit_2026", [gov]) == []
    assert value_flags("explicit_2026", [lii]) == [
        "explicit_2026_without_2026_publication",
        "no_government_citation",
    ]
    assert value_flags("uprated", [gov]) == ["computed_or_indexed"]
    assert value_flags("carried_forward", []) == [
        "no_government_citation",
        "carried_forward",
    ]
    assert value_flags("created_at_load", [gov]) == ["created_at_load"]
    assert value_flags("unresolved", [gov]) == ["origin_unresolved"]
    assert value_flags("carried_forward", [late]) == [
        "post_freeze_citation",
        "carried_forward",
    ]
    assert value_flags("carried_forward", [late, gov]) == ["carried_forward"]
    assert value_flags(
        "carried_forward", [gov], comment_evidence={"computation": True}
    ) == ["computed_in_yaml_comment", "carried_forward"]
    assert value_flags("convention", [lii]) == ["convention_set"]
    assert value_flags("uprated", [], convention_modules=["m"]) == ["convention_set"]
    with pytest.raises(ValueError):
        value_flags("typed_in", [])


def test_parameter_categories():
    assert parameter_category("gov.abolitions.snap") == "model_switch"
    assert parameter_category("gov.contrib.x.in_effect") == "model_switch"
    assert parameter_category("gov.bls.cpi.cpi_u") == "economic_series"
    assert parameter_category("calibration.gov.cbo.x") == "economic_series"
    assert parameter_category("gov.irs.uprating") == "economic_series"
    assert parameter_category("gov.irs.deductions.standard.amount.SINGLE") == "law"


def test_same_value():
    assert same_value(1, 1.0) and same_value(0.1 + 0.2, 0.3)
    assert not same_value(True, 1) or True is not 1  # noqa: F632
    assert not same_value(True, False)
    assert same_value(["a", 1], ["a", 1.0]) and not same_value(["a"], ["b"])
    assert same_value(None, None) and not same_value(None, 0)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _report_facts():
    gov = {"title": REV_PROC_2025_32[0], "href": REV_PROC_2025_32[1]}
    lii = {"title": "26 U.S.C. 1", "href": "https://www.law.cornell.edu/uscode/26/1"}
    return [
        _louisiana_fact("SINGLE"),
        _fact("gov.irs.a", "explicit_2026", [gov], scored_cells=["s1/x", "s2/x"]),
        _fact("gov.irs.b", "uprated", [gov], scored_cells=["s1/x", "s3/y"]),
        _fact("gov.irs.c", "carried_forward", [lii], scored_cells=["s1/x"]),
        _fact("gov.irs.d", "convention", [lii], convention_modules=["latest_c_x"]),
        _fact("gov.bls.cpi.cpi_u", "explicit_2026", [], scored_cells=["s1/x"]),
        _fact("gov.irs.e", "uprated", [gov], scored_cells=[], unscored_cells=["s9/z"]),
    ]


def test_build_report_counts_and_tables():
    other = [
        {
            "parameter": "gov.irs.c",
            "instant": "2025-01-01",
            "value": 1,
            "scored_cells": ["s1/x"],
            "unscored_cells": [],
        }
    ]
    report, markdown = build_report(_report_facts(), other, {"seconds": 1})
    summary = report["summary"]
    assert summary["values"] == 7
    assert summary["values_read_by_scored_cells"] == 6
    assert summary["values_read_only_by_unscored_cells"] == 1
    assert summary["by_flag"]["computed_or_indexed"] == {
        "values": 1,
        "law_values": 1,
        "parameters": 1,
        "scored_cells": 2,
    }
    assert summary["by_flag"]["convention_set"]["values"] == 1
    assert summary["by_origin"]["explicit_2026"] == 3
    assert (
        summary["explicit_2026_without_2026_publication_by_support"]["inputs_only"] == 1
    )
    # Publication-flagged law values are ordered by scored cells.
    table = markdown.split("## Law values whose 2026 amount")[1].split("##")[0]
    assert table.index("`gov.irs.b`") < table.index(f"`{LAW_PREFIX}.SINGLE`")
    assert "`gov.bls.cpi.cpi_u`" not in table
    assert "`gov.irs.c`" in markdown.split("## Law values cited to no government")[1]
    assert "`latest_c_x` 1" in markdown
    assert "1 (parameter, instant) reads fall outside 2026" in markdown
    assert report["meta"]["publication_flags"] == list(PUBLICATION_FLAGS)
    json.loads(json.dumps(report))
    # Deterministic: the same facts in another order give the same report.
    again, markdown_again = build_report(
        list(reversed(_report_facts())), other, {"seconds": 1}
    )
    assert again == report and markdown_again == markdown


def test_compact_report_round_trips():
    """The JSON lists each cell, cell set and citation once; expand_report
    restores every entry exactly, and dumps_report is valid JSON."""
    other = [
        {
            "parameter": "gov.irs.c",
            "instant": "2025-01-01",
            "value": 1,
            "scored_cells": ["s1/x"],
            "unscored_cells": [],
        }
    ]
    facts = _report_facts()
    report, _ = build_report(facts, other, {"seconds": 1})
    entries = sorted(
        (build_entry(fact) for fact in facts),
        key=lambda e: (e["parameter"], e["entry_instant"] or ""),
    )
    expanded = expand_report(report)
    assert expanded["entries"] == entries
    assert expanded["other_instants"] == other
    assert expanded["summary"] == summarize(entries)
    assert len(report["cells"]) == len(set(report["cells"]))
    assert len(report["citations"]) == len(
        {json.dumps(c, sort_keys=True) for c in report["citations"]}
    )
    stored = report["entries"][0]
    assert isinstance(stored["scored_cells"], int)
    assert isinstance(stored["citations"], int)
    assert "category" not in stored and "scored_cell_count" not in stored
    text = dumps_report(report)
    assert json.loads(text) == report
    assert text.count("\n") > len(report["entries"])


def test_summarize_ignores_unscored_entries():
    entries = [build_entry(fact) for fact in _report_facts()]
    summary = summarize(entries)
    flagged_unscored = [e for e in entries if not e["scored_cell_count"]]
    assert flagged_unscored and all(
        "computed_or_indexed" in e["flags"] for e in flagged_unscored
    )
    assert summary["by_flag"]["computed_or_indexed"]["values"] == 1


def test_module_does_not_import_policyengine():
    code = (
        "import sys, policybench.publication_sources; "
        "print(any(m.startswith('policyengine') for m in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "False"


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

_MONTH_NAMES = ["January", "Feb.", "March", "Sept", "October", "Dec"]
_years = st.integers(min_value=1990, max_value=2035)


@st.composite
def _date_fragment(draw):
    year = draw(_years)
    month = draw(st.integers(1, 12))
    day = draw(st.integers(1, 28))
    short = year % 100
    return draw(
        st.sampled_from(
            [
                str(year),
                f"{draw(st.sampled_from(_MONTH_NAMES))} {day}, {year}",
                f"{day} {draw(st.sampled_from(_MONTH_NAMES))} {year}",
                f"{draw(st.sampled_from(_MONTH_NAMES))} {year}",
                f"{year}-{month:02d}-{day:02d}",
                f"/{year}/{month:02d}/",
                f"cpi_{month:02d}{day:02d}{year}.htm",
                f"{year}{month:02d}{day:02d}",
                f"Rev. Proc. {year}-{day}",
                f"Notice {year}-{day}",
                f"{draw(st.integers(1, 120))} FR {draw(st.integers(1, 99999))}",
                f"irs-drop/rp-{short:02d}-{day}.pdf",
                f"RIB {short:02d}-{day:03d}",
            ]
        )
    )


_four_digit_fragments = st.one_of(
    _years.map(str),
    st.builds(
        lambda m, d, y: f"{m} {d}, {y}",
        st.sampled_from(_MONTH_NAMES),
        st.integers(1, 28),
        _years,
    ),
    st.builds(lambda y, m: f"/{y}/{m:02d}/", _years, st.integers(1, 12)),
    st.builds(
        lambda y, m, d: f"{m:02d}{d:02d}{y}",
        _years,
        st.integers(1, 12),
        st.integers(1, 28),
    ),
    st.builds(lambda y, n: f"Rev. Proc. {y}-{n}", _years, st.integers(1, 99)),
)
_noise = st.text(
    alphabet=st.characters(codec="ascii", exclude_categories=("Cc",)), max_size=20
)
_words = st.sampled_from(
    ["Standard deduction", "Form", "Instructions", "(", ")", "/", "-", " ", "§ 63"]
)


@settings(max_examples=300, deadline=None)
@given(st.lists(st.one_of(_date_fragment(), _noise, _words), max_size=8))
def test_dates_never_after_the_last_stated_year(parts):
    text = " ".join(parts)
    evidence = extract_publication_date(text)
    if evidence is None:
        return
    assert evidence.earliest <= evidence.latest
    assert evidence.latest.year <= max(stated_years(text))


@settings(max_examples=300, deadline=None)
@given(st.lists(st.one_of(_four_digit_fragments, _words), max_size=6))
def test_dates_never_after_any_four_digit_year_in_the_text(parts):
    """An oracle independent of ``stated_years``: every 19xx or 20xx run."""
    text = " ".join(parts)
    evidence = extract_publication_date(text)
    years = [
        int(text[index : index + 4])
        for index in range(len(text) - 3)
        if text[index : index + 4].isdigit() and text[index : index + 2] in ("19", "20")
    ]
    if evidence is not None:
        assert years and evidence.latest.year <= max(years)


@settings(max_examples=200, deadline=None)
@given(st.text(alphabet=st.characters(exclude_categories=("Nd",)), max_size=60))
def test_no_digits_no_date(text):
    assert extract_publication_date(text) is None
    assert stated_years(text) == set()


_hosts = st.sampled_from(
    [
        "www.irs.gov",
        "legis.la.gov",
        "www.law.cornell.edu",
        "www.kff.org",
        "www.bls.gov",
        "www.federalregister.gov",
        "docs.google.com",
        "",
    ]
)
_hrefs = st.one_of(
    st.none(),
    st.text(max_size=40),
    st.builds(
        lambda host, path: f"https://{host}/{path}" if host else path,
        _hosts,
        st.text(max_size=30),
    ),
)
_titles = st.one_of(
    st.none(),
    st.text(max_size=60),
    st.builds(
        lambda a, b: f"{a} {b}",
        st.sampled_from(
            [
                "Rev. Proc. 2025-32",
                "26 U.S.C. 63",
                "2026 Form 1040 Instructions",
                "Withholding tables",
                "Consumer Price Index",
                "91 FR 1797",
                "September 28, 2026",
            ]
        ),
        st.text(max_size=20),
    ),
)


@settings(max_examples=400, deadline=None)
@given(_titles, _hrefs, st.text(max_size=10))
def test_classify_citation_is_total_and_deterministic(title, href, level):
    first = classify_citation(title, href, level)
    assert first == classify_citation(title, href, level)
    assert first["source_class"] in SOURCE_CLASSES
    assert first["kind"] in CITATION_KINDS
    assert first["pre_freeze"] in (True, False, None)
    assert isinstance(first["dated_2026_publication"], bool)
    if first["dated_2026_publication"]:
        assert first["source_class"] == "government"
        assert first["pre_freeze"] is not False
    json.dumps(first)


_citations = st.lists(st.builds(classify_citation, _titles, _hrefs), max_size=4)
_pre_freeze_government = st.builds(
    classify_citation,
    st.sampled_from(
        [
            "Rev. Proc. 2024-40",
            "2025 Form 540 Instructions, October 9, 2025",
            "Tax News, October 2025",
            "26 U.S.C. 63, as of 2020",
            "Annual Update, 90 FR 5000",
        ]
    ),
    st.sampled_from(
        [
            "https://www.irs.gov/pub/irs-drop/rp-24-40.pdf",
            "https://www.ftb.ca.gov/forms/x.html",
            "https://uscode.house.gov/view.xhtml",
            None,
        ]
    ),
)


@settings(max_examples=300, deadline=None)
@given(
    st.sampled_from(ORIGINS),
    _citations,
    _pre_freeze_government,
    st.lists(st.just("latest_c_x"), max_size=1),
    st.sampled_from([None, {"computation": True}, {"computation": False}]),
    st.sampled_from(["law", "economic_series", "model_switch"]),
)
def test_adding_a_pre_freeze_government_citation_never_adds_a_flag(
    origin, citations, extra, conventions, evidence, category
):
    assume(extra["source_class"] == "government" and extra["pre_freeze"] is True)
    kwargs = {
        "convention_modules": conventions,
        "comment_evidence": evidence,
        "category": category,
    }
    before = set(value_flags(origin, citations, **kwargs))
    after = set(value_flags(origin, [*citations, extra], **kwargs))
    assert "no_government_citation" not in after
    assert after <= before


@settings(max_examples=300, deadline=None)
@given(
    st.sampled_from(ORIGINS),
    _citations,
    st.lists(st.sampled_from(["latest_c_a", "latest_c_b"]), max_size=2),
    st.sampled_from([None, {"computation": True}]),
)
def test_computed_values_are_always_flagged_unless_convention_set(
    origin, citations, conventions, evidence
):
    flags = value_flags(
        origin, citations, convention_modules=conventions, comment_evidence=evidence
    )
    assert flags == [flag for flag in FLAGS if flag in flags]
    assert len(flags) == len(set(flags))
    if origin == "convention" or conventions:
        assert flags == ["convention_set"]
    elif origin in COMPUTED_ORIGINS:
        assert "computed_or_indexed" in flags
    else:
        assert "computed_or_indexed" not in flags
    if "explicit_2026_without_2026_publication" in flags:
        assert origin == "explicit_2026"


@settings(max_examples=200, deadline=None)
@given(
    st.sampled_from(ORIGINS),
    st.one_of(st.none(), st.just("2026-01-01"), st.just("2025-01-01")),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.booleans(),
    st.booleans(),
    st.lists(st.just("m"), max_size=1),
)
def test_classify_origin_is_total(_, instant, value, in_yaml, uprated, conventions):
    yaml_entries = {instant: {"value": value}} if (instant and in_yaml) else {}
    origin, baseline, detail = classify_origin(
        entry_instant=instant,
        value=value,
        yaml_entries=yaml_entries,
        uprated_instants={instant} if (instant and uprated) else set(),
        interpolated=False,
        load_updates=[],
        reference_value=value,
        convention_modules=conventions,
    )
    assert origin in ORIGINS and baseline in ORIGINS and baseline != "convention"
    assert (origin == "convention") == bool(conventions)
    if instant and in_yaml:
        assert baseline == (
            "explicit_2026" if instant.startswith("2026") else "carried_forward"
        )


@settings(max_examples=200, deadline=None)
@given(
    st.integers(min_value=1, max_value=10**7),
    st.floats(min_value=1, max_value=1000, allow_nan=False),
    st.floats(min_value=1, max_value=1000, allow_nan=False),
)
def test_comment_arithmetic_round_trips(base, numerator, denominator):
    text = f"{base:,} * ({numerator!r} / {denominator!r}), rounded"
    [(raw, result)] = evaluate_arithmetic(text)
    assert result == pytest.approx(base * numerator / denominator, rel=1e-9)
    exact = comment_computation([text], result)["expressions"][0]["matches_value"]
    assert exact is (result >= 1)
    if result >= 1:
        rounded = comment_computation([text], round(result))
        assert rounded["expressions"][0]["matches_value"] is True
        assert rounded["computation"] is True


@settings(max_examples=100, deadline=None)
@given(
    st.lists(
        st.text(
            alphabet=st.characters(codec="ascii", exclude_categories=("Cc",)),
            min_size=1,
            max_size=30,
        ).filter(lambda s: s.strip() and not s.strip().startswith("#")),
        max_size=3,
    ),
    st.sampled_from(["SINGLE", "JOINT", "1"]),
)
def test_entry_comments_return_the_comment_block(comments, key):
    block = "".join(f"  # {comment}\n" for comment in comments)
    text = f"OTHER:\n  2026-01-01: 1\n{key}:\n  2025-01-01: 5\n{block}  2026-01-01: 9\n"
    assert entry_comments(text, [key], "2026-01-01") == [c.strip() for c in comments]
    assert entry_comments(text, ["OTHER"], "2026-01-01") == []


# ---------------------------------------------------------------------------
# The committed report
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def committed_report():
    if not REPORT.exists():
        pytest.skip("the engine report has not been generated")
    return expand_report(json.loads(REPORT.read_text()))


def test_committed_report_flags_louisiana(committed_report):
    entries = {
        entry["parameter"]: entry
        for entry in committed_report["entries"]
        if entry["parameter"].startswith(LAW_PREFIX + ".")
    }
    assert entries, "no Louisiana standard deduction entry in the report"
    for name, entry in entries.items():
        assert entry["origin"] == "explicit_2026", name
        assert "explicit_2026_without_2026_publication" in entry["flags"], name
    if f"{LAW_PREFIX}.SINGLE" in entries:
        single = entries[f"{LAW_PREFIX}.SINGLE"]
        assert single["value"] == 12_835
        assert "computed_in_yaml_comment" in single["flags"]


def test_committed_report_matches_the_code(committed_report):
    """Differential: the stored citations, flags and summary are what the code
    computes from the stored inputs today."""
    meta = committed_report["meta"]
    assert meta["scored_reference_mismatches"] == 0
    assert meta["scored_cells_recomputed"] == 1928
    assert not meta["recorded_value_check"]["mismatches"]
    assert not meta["reverse_order_mismatches"]
    classified = {}
    for entry in committed_report["entries"]:
        for citation in entry["citations"]:
            key = (citation["title"], citation["href"], citation["level"])
            if key not in classified:
                classified[key] = classify_citation(*key)
            assert classified[key] == citation
        evidence = comment_computation(entry["yaml_comments"], entry["value"])
        assert evidence == entry["comment_evidence"]
        assert entry["flags"] == value_flags(
            entry["origin"],
            entry["citations"],
            convention_modules=entry["convention_modules"],
            comment_evidence=evidence,
            category=entry["category"],
        )
        if entry["origin"] == "explicit_2026":
            assert entry["explicit_2026_support"] == explicit_support(
                entry["citations"], entry["category"]
            )
        if entry["origin"] in COMPUTED_ORIGINS:
            assert "computed_or_indexed" in entry["flags"]
    assert summarize(committed_report["entries"]) == committed_report["summary"]
