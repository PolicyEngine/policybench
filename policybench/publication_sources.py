"""Check whether each 2026 parameter value behind a scored reference was published.

A PolicyBench reference follows from the stated facts and from law published
before the 2026-07-03 reference freeze. A reference can still rest on a number
nobody published before the freeze: an amount PolicyEngine computed itself
(uprated from an index when the tree loads, or typed into the YAML as a 2026
entry after doing the arithmetic by hand) and cited to a statute, an index
release or guidance for another year. Louisiana's 2026 standard deduction is
the case that prompted this check: policyengine-us 2.15.17 encodes $12,835 as
an explicit 2026 entry whose YAML comment shows the CPI-U arithmetic
(``12,500 * (324.054 / 315.605)``), and its four citations are a statute, a
withholding-tables notice, a CPI release and the 2025 return instructions, none
of which this module counts as a 2026 publication of the amount.

The engine-side script
(``reference_audit/2026-10-05-reference-adversary/scripts/publication_sources.py``)
records which parameter values each scored reference reads and where each 2026
value comes from. This module holds the pure part: classifying citations,
reading dates out of citation titles and links, deciding a value's origin and
its flags, and rendering the report. Nothing here imports policyengine.

Origins (``classify_origin``), decided against the plain policyengine-us system:

``explicit_2026``
    A YAML entry dated in 2026 holds the value.
``carried_forward``
    A YAML entry dated before 2026 holds the value (static law).
``uprated`` / ``interpolated`` / ``backdated`` / ``computed_at_load``
    The value was produced while the parameter tree loaded: by core's
    ``uprate_parameters``, by interpolation, by policyengine-us's
    ``backdate_parameters`` (which copies a parameter's earliest value, here one
    dated after the instant read, back to 2015), or by another
    ``Parameter.update`` that policyengine-us code runs at load (for example its
    uprating extensions).
``created_at_load``
    The parameter has no YAML source at all (a structural default).
``convention``
    The reference conventions (``latest_final``) set the value.
``unresolved``
    None of the above explains the value.

Citations (``classify_citation``) are classified by source (government,
law republisher, other) and kind (statute, regulation, register notice,
agency publication, withholding guidance, index data, other), and dated where
the title or link states a date. A statute or regulation citation dates the law,
not the 2026 amount: it can say an amount is indexed without stating what the
indexed amount is, and a date it states is usually an effective date, so it has
no freeze status. Only a government register notice or agency publication
issued for 2026 (it applies to 2026, or was issued in 2025 or 2026 and names no
other year) and not dated after the freeze counts as a 2026 publication; for an
economic series (a price index or projection) a government index release
counts too. Whether that publication actually states the amount is not
something metadata can show; this check only finds values that have no such
candidate at all.

Flags (``value_flags``):

``computed_or_indexed``
    The value was produced at load (uprated, interpolated, backdated,
    computed).
``explicit_2026_without_2026_publication``
    An explicit 2026 entry with no 2026 publication among its citations.
``computed_in_yaml_comment``
    A YAML comment beside the entry shows PolicyEngine computed the value (an
    arithmetic expression that reproduces it, projection or estimate wording,
    or an index named beside a multiplication).
``created_at_load`` / ``origin_unresolved``
    The value has no YAML entry, or its origin could not be determined.
``no_government_citation``
    No citation is a government source.
``post_freeze_citation``
    At least one citation is dated after the freeze and none before it.
``convention_set``
    ``latest_final`` supplied the value; no other flag is set.
``carried_forward``
    Informational.
"""

from __future__ import annotations

import ast
import json
import operator
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote, urlsplit

FREEZE_DATE = date(2026, 7, 3)
REFERENCE_YEAR = 2026

ORIGINS = (
    "explicit_2026",
    "carried_forward",
    "uprated",
    "interpolated",
    "backdated",
    "computed_at_load",
    "created_at_load",
    "unresolved",
    "convention",
)
COMPUTED_ORIGINS = frozenset(
    {"uprated", "interpolated", "backdated", "computed_at_load"}
)
# policyengine-us's tools/parameters.py function that copies each parameter's
# earliest value back to 2015 when the tree loads.
BACKDATE_WRITER = "backdate_parameters"

FLAGS = (
    "computed_or_indexed",
    "explicit_2026_without_2026_publication",
    "computed_in_yaml_comment",
    "created_at_load",
    "origin_unresolved",
    "no_government_citation",
    "post_freeze_citation",
    "convention_set",
    "carried_forward",
)
INFORMATIONAL_FLAGS = frozenset({"convention_set", "carried_forward"})
REVIEW_FLAGS = tuple(flag for flag in FLAGS if flag not in INFORMATIONAL_FLAGS)

SOURCE_CLASSES = ("government", "law_republisher", "other")
CITATION_KINDS = (
    "index_data",
    "withholding",
    "regulation",
    "register",
    "agency_publication",
    "statute",
    "other",
)
QUALIFYING_KINDS = frozenset({"register", "agency_publication"})
CATEGORIES = ("law", "economic_series", "model_switch")

# Hosts outside .gov, .us and .mil that the citations of the engine run point
# to and that are the official site of a US government body (named here from
# the site itself). A host left out only makes a citation count as "other".
GOVERNMENT_HOSTS = frozenset(
    {
        "ctoec.org",  # Connecticut Office of Early Childhood
        "ctpaidleave.org",  # Connecticut Paid Leave Authority
        "fldoe.org",  # Florida Department of Education
        "flrules.org",  # Florida Administrative Code (Department of State)
        "kslegislature.org",  # Kansas Legislature
        "louisianabelieves.com",  # Louisiana Department of Education
        "marylandpublicschools.org",  # Maryland State Department of Education
        "myflfamilies.com",  # Florida Department of Children and Families
        "myflorida.com",  # Florida agencies (for example ahca.myflorida.com)
        "okdhslive.org",  # Oklahoma Human Services policy library
        "oscn.net",  # Oklahoma State Courts Network (statutes)
        "sccgov.org",  # County of Santa Clara
        "sfhsa.org",  # San Francisco Human Services Agency
    }
)
# Commercial or nonprofit republishers of statutes and regulations that the
# citations point to.
LAW_REPUBLISHER_HOSTS = frozenset(
    {
        "amlegal.com",
        "casetext.com",
        "findlaw.com",
        "justia.com",
        "law.cornell.edu",
        "legiscan.com",
        "lexis.com",
        "public.law",
        "trackbill.com",
        "westlaw.com",
    }
)
INDEX_HOSTS = frozenset({"bls.gov", "cbo.gov"})
GOVERNMENT_SUFFIXES = (".gov", ".mil", ".us")

MODEL_SWITCH_PREFIXES = ("gov.abolitions.", "gov.contrib.", "gov.simulation.")
ECONOMIC_SERIES_PREFIXES = ("gov.bls.", "gov.cbo.", "calibration.", "gov.census.")

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_MONTH = (
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_YEAR = r"((?:19|20)\d{2})"
_FULL_DATE = re.compile(
    rf"\b{_MONTH}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+{_YEAR}(?!\d)", re.IGNORECASE
)
_DAY_FIRST_DATE = re.compile(
    rf"\b(\d{{1,2}})\s+{_MONTH}\.?,?\s+{_YEAR}(?!\d)", re.IGNORECASE
)
_ISO_DATE = re.compile(rf"(?<!\d){_YEAR}([-/._])(\d{{1,2}})\2(\d{{1,2}})(?!\d)")
_MONTH_YEAR = re.compile(rf"\b{_MONTH}\.?,?\s+{_YEAR}(?!\d)", re.IGNORECASE)
_PATH_YEAR_MONTH = re.compile(rf"/{_YEAR}/(\d{{1,2}})(?=/)")
_EIGHT_DIGITS = re.compile(r"(?<!\d)(\d{8})(?!\d)")
_FR_CITATION = re.compile(r"\b(\d{1,3})\s+(?:FR|Fed\.?\s*Reg\.?)\s+\d{1,6}\b")
_IRS_ISSUANCE = re.compile(
    r"\b(?:Rev(?:enue)?\.?\s*Proc(?:edure)?s?\.?|Rev(?:enue)?\.?\s*Rul(?:ing)?s?\.?|"
    r"Notice|Announcement|IR|I\.R\.B\.|IRB|Internal\s+Revenue\s+Bulletin"
    rf"(?:\s+No\.)?)\s*[-–]?\s*{_YEAR}-\d{{1,3}}(?!\d)",
    re.IGNORECASE,
)
_IRB_PATH = re.compile(rf"/irb/{_YEAR}-\d+", re.IGNORECASE)
_IRS_DROP = re.compile(r"irs-drop/(?:rp|rr|n|a)-(\d{2})-\d{1,3}(?!\d)", re.I)
_RIB = re.compile(r"\bRIB\s*#?\s*(\d{2})-\d{2,4}(?!\d)", re.IGNORECASE)
_ANY_YEAR = re.compile(r"(?=((?:19|20)\d{2}))")
_CONGRESS = re.compile(
    r"\b(\d{2,3})(?:st|nd|rd|th)[-\s]congress\b|"
    r"\b(?:pub(?:lic)?\.?\s*l(?:aw)?\.?(?:\s*no\.)?|p\.\s?l\.)\s*(\d{2,3})-\d+|"
    r"\bPLAW-(\d{2,3})publ",
    re.IGNORECASE,
)
_FOUR_DIGIT_YEAR = re.compile(rf"(?<!\d){_YEAR}(?!\d)")

_APPLIES_LABELLED = re.compile(
    rf"\b(?:tax|taxable|fiscal|benefit|plan|program|income|calendar)\s+year\s*"
    rf"{_YEAR}(?!\d)|\b(?:TY|FY|CY|PY)\s*-?\s*{_YEAR}(?!\d)",
    re.IGNORECASE,
)
_APPLIES_NOUNS = (
    r"Forms?|Instructions?|Booklet|Schedules?|Publications?|Pub\.|Tax\s+Tables?|"
    r"Tax\s+Rates?|Rates?|Brackets|Withholding|Tables|Guides?|Returns?|Indexing|"
    r"Inflation\s+Adjust\w*|Guidelines|Income\s+Limits|Fair\s+Market\s+Rents|"
    r"COLA|Cost[-\s]of[-\s]Living|Allotments?|Standards|Amounts|Limits|"
    r"Thresholds|Deductions?|Exemptions?|Credits?"
)
_APPLIES_YEAR_FIRST = re.compile(
    rf"(?<!\d){_YEAR}(?!\d)\s+(?:[A-Za-z][\w.&'/-]*\s+){{0,5}}?(?:{_APPLIES_NOUNS})\b",
    re.IGNORECASE,
)
_APPLIES_FOR = re.compile(rf"\b(?:for|in)\s+{_YEAR}(?!\d)", re.IGNORECASE)
_APPLIES_PAREN = re.compile(rf"\({_YEAR}\)")
_APPLIES_HREF = (
    re.compile(rf"\({_YEAR}\)"),
    re.compile(
        rf"/(?:forms?|taxforms|instructions|pubs?|publications|irs-prior)/"
        rf"(?:[\w.-]+/)?{_YEAR}(?=[/_.-])",
        re.IGNORECASE,
    ),
    re.compile(rf"--{_YEAR}(?!\d)"),
)

_INDEX_TITLE = re.compile(
    r"consumer\s+price\s+index|\bc?-?cpi(?:-u|-w)?\b|chained\s+cpi|"
    r"employment\s+cost\s+index|average\s+wage\s+index|"
    r"budget\s+and\s+economic\s+outlook|economic\s+projections",
    re.IGNORECASE,
)
_WITHHOLDING = re.compile(r"withholding", re.IGNORECASE)
_REGULATION = re.compile(
    r"\bC\.?\s?F\.?\s?R\b|code\s+of\s+(?:federal\s+|state\s+)?regulations|"
    r"administrative\s+code|admin\.?\s+code|administrative\s+rules?|"
    r"admin\.?\s+rules?|\bCOMAR\b|\bNYCRR\b|\bN\.?J\.?A\.?C\b|\bregulations?\b",
    re.IGNORECASE,
)
_REGULATION_HOSTS = ("ecfr.gov", "flrules.org", "dsd.maryland.gov")
_REGISTER = re.compile(
    r"federal\s+register|\bFed\.?\s*Reg\.|\b\d{1,3}\s+FR\s+\d|"
    r"\b[A-Z][a-z]+\s+Register\b|pennsylvania\s+bulletin",
    re.IGNORECASE,
)
_REGISTER_HOSTS = ("federalregister.gov",)
_AGENCY_STRONG = re.compile(
    r"\brev(?:enue)?\.?\s*proc|\brevenue\s+procedure|\brev(?:enue)?\.?\s*rul|"
    r"\bnotice\b|\bforms?\b|\binstructions?\b|\bpublications?\b|\bpub\.?\s*\d|"
    r"\bbulletin\b|\bbooklet\b|\bguide\b|\bmanual\b|\bhandbook\b|\bfact\s+sheet|"
    r"\btax\s+news\b|\bannouncement\b|\bmemo(?:randum)?\b|\bcircular\b|"
    r"\bcost[-\s]of[-\s]living|\bCOLA\b|\bpoverty\s+guidelines\b|"
    r"\bincome\s+limits\b|\bfair\s+market\s+rents\b|\bworksheet\b|"
    r"\binflation\s+adjust",
    re.IGNORECASE,
)
_STATUTE = re.compile(
    r"\bU\.?\s?S\.?\s?C\b|\bU\.?S\.?\s+Code\b|united\s+states\s+code|statute|"
    r"\bStat\.|revised\s+code|code\s+ann|general\s+laws|laws\s+of|session\s+law|"
    r"public\s+law|\bP\.?\s?L\.?\s?\d|\bpub\.?\s*l\.|\bact\b|\b[HS]\.?\s?B\.?\s?\d|"
    r"house\s+bill|senate\s+bill|assembly\s+bill|\bchapter\b|\bcode\b|§|"
    r"\bsection\b|\bsec\.|\btitle\s+\d|\bORS\b|\bRSA\b|\bMCL\b|\bILCS\b|\bKRS\b|"
    r"\bRCW\b|\bNRS\b|\bIC\s+\d|\btax\s+law\b",
    re.IGNORECASE,
)
_STATUTE_HOST = re.compile(
    r"leg|statut|capitol|revisor|assembly|senate|gencourt|uscode|congress\.gov|"
    r"(?:^|\.)codes?\.|(?:^|\.)law\.|(?:^|\.)lis\.|council|ilga|(?:^|\.)cga\.|"
    r"(?:^|\.)lrc\.|(?:^|\.)iga\.|statehouse|oscn|nmonesource|delcode"
)
_AGENCY_WEAK = re.compile(
    r"\brates?\b|\bbrackets?\b|\bstandards?\b|\ballotments?\b|\bpolicy\b|"
    r"\bguidance\b|\boverview\b|\bfaq\b|\breport\b|\bnews\b|\bpress\b|"
    r"\brelease\b|\bchart\b|\btable\b|\bletter\b|\bdetermination\b|"
    r"\bschedule\b|\bindexing\b|\bamounts?\b|\blimits?\b|\bthresholds?\b",
    re.IGNORECASE,
)
_AGENCY_HOST_PARTS = (
    "irs.gov",
    "ssa.gov",
    "usda.gov",
    "hhs.gov",
    "cms.gov",
    "medicaid.gov",
    "huduser.gov",
    "hud.gov",
    "dol.gov",
    "treasury.gov",
    "revenue",
    "tax",
    "dor.",
    "dfa.",
    "ftb.",
    "comptroller",
    "finance",
    "dhs.",
    "dss.",
    "hhsc",
    "labor",
)

# Words that say a value is PolicyEngine's own projection or estimate.
_PROJECTION_WORDS = re.compile(
    r"\bprojected\b|\bprojection\b|extrapolat\w*|\bestimat\w*", re.IGNORECASE
)
# Words that name an index; they show a computation only beside a
# multiplication (an index can also describe how an agency set its amount).
_INDEX_WORDS = re.compile(
    r"\bc?-?cpi(?:-u|-w)?\b|uprat\w*|inflation\s+factor", re.IGNORECASE
)
_MULTIPLICATION_WORDS = re.compile(
    r"\btimes\b|\bmultipl(?:ied|y|ying)\b|[*×]", re.IGNORECASE
)
_EXPRESSION = re.compile(r"[\d(][\d\s,._()+\-*/×÷]*[\d)]")
_THOUSANDS = re.compile(r"(?<=\d)[,_](?=\d{3}(?!\d))")
_KEY_LINE = re.compile(r"""^("[^"]*"|'[^']*'|[^:#'"][^:#]*?):(?:\s|$)""")
_NAME_TOKEN = re.compile(r"\[\d+\]|[^.\[\]]+")
_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY_OPERATORS = {ast.USub: operator.neg, ast.UAdd: operator.pos}


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DateEvidence:
    """A date range a citation states, with how precisely it states it."""

    earliest: date
    latest: date
    precision: str
    basis: str

    def to_dict(self) -> dict[str, str]:
        data = asdict(self)
        data["earliest"] = self.earliest.isoformat()
        data["latest"] = self.latest.isoformat()
        return data


_PRECISION_RANK = {"day": 3, "month": 2, "year": 1}


def _month_number(name: str) -> int:
    return _MONTHS[name[:3].lower()]


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date.fromordinal(date(year, month + 1, 1).toordinal() - 1)


def _year_evidence(year: int, basis: str) -> DateEvidence:
    return DateEvidence(date(year, 1, 1), date(year, 12, 31), "year", basis)


def _fr_year(volume: int) -> int | None:
    """The calendar year of a Federal Register volume (volume 1 is 1936)."""
    year = 1935 + volume
    return year if 1936 <= year <= 2099 else None


def stated_years(text: str | None) -> set[int]:
    """Every year the text states.

    That is each four-digit 19xx or 20xx run (also inside longer digit runs,
    such as the 2026 of ``cpi_01132026``), the year of each Federal Register
    volume cited as ``<volume> FR <page>``, and the year of each two-digit
    issuance number the date reader understands (IRS ``rp-25-32`` file names
    and Louisiana ``RIB 26-019`` bulletins).
    """
    if not text:
        return set()
    years = {int(match.group(1)) for match in _ANY_YEAR.finditer(text)}
    for match in _FR_CITATION.finditer(text):
        year = _fr_year(int(match.group(1)))
        if year is not None:
            years.add(year)
    for pattern in (_IRS_DROP, _RIB):
        years |= {2000 + int(match.group(1)) for match in pattern.finditer(text)}
    return years


def _date_candidates(text: str) -> list[DateEvidence]:
    found: list[DateEvidence] = []
    for match in _FULL_DATE.finditer(text):
        day = _safe_date(
            int(match.group(3)), _month_number(match.group(1)), int(match.group(2))
        )
        if day:
            found.append(DateEvidence(day, day, "day", match.group(0)))
    for match in _DAY_FIRST_DATE.finditer(text):
        day = _safe_date(
            int(match.group(3)), _month_number(match.group(2)), int(match.group(1))
        )
        if day:
            found.append(DateEvidence(day, day, "day", match.group(0)))
    for match in _ISO_DATE.finditer(text):
        day = _safe_date(int(match.group(1)), int(match.group(3)), int(match.group(4)))
        if day:
            found.append(DateEvidence(day, day, "day", match.group(0)))
    for match in _EIGHT_DIGITS.finditer(text):
        digits = match.group(1)
        day = None
        year = int(digits[:4])
        if 1990 <= year <= 2035:
            day = _safe_date(year, int(digits[4:6]), int(digits[6:]))
        if day is None:
            year = int(digits[4:])
            if 1990 <= year <= 2035:
                day = _safe_date(year, int(digits[:2]), int(digits[2:4]))
        if day:
            found.append(DateEvidence(day, day, "day", digits))
    for match in _MONTH_YEAR.finditer(text):
        year, month = int(match.group(2)), _month_number(match.group(1))
        found.append(
            DateEvidence(
                date(year, month, 1), _month_end(year, month), "month", match.group(0)
            )
        )
    for match in _PATH_YEAR_MONTH.finditer(text):
        year, month = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12:
            found.append(
                DateEvidence(
                    date(year, month, 1),
                    _month_end(year, month),
                    "month",
                    match.group(0),
                )
            )
    for match in _FR_CITATION.finditer(text):
        year = _fr_year(int(match.group(1)))
        if year is not None:
            found.append(_year_evidence(year, match.group(0)))
    for pattern in (_IRS_ISSUANCE, _IRB_PATH):
        for match in pattern.finditer(text):
            found.append(_year_evidence(int(match.group(1)), match.group(0)))
    for pattern in (_IRS_DROP, _RIB):
        for match in pattern.finditer(text):
            found.append(_year_evidence(2000 + int(match.group(1)), match.group(0)))
    return found


def extract_publication_date(text: str | None) -> DateEvidence | None:
    """The issue date a citation's title or link states, if it states one.

    Full dates (``February 20, 2026``, ``2026-02-20``, ``/2025/10/09/``, an
    eight-digit ``20260113`` or ``01132026`` run), month and year
    (``October 2025``), Federal Register volumes and IRS issuance numbers
    (``Rev. Proc. 2025-32``, ``rp-25-32``, ``IRB 2025-45``) and Louisiana
    revenue bulletins (``RIB 26-019``) are read. The most precise evidence
    wins, and among equally precise evidence the latest. A stated effective
    date can be read as an issue date. The result never lies after the last
    year the text states (``stated_years``).
    """
    if not text:
        return None
    candidates = _date_candidates(text)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (_PRECISION_RANK[item.precision], item.latest, item.basis),
    )


def extract_applies_to_year(title: str | None, href: str | None) -> int | None:
    """The year a document applies to (a tax, fiscal or benefit year), if stated.

    ``Tax Year 2026``, ``FY 2026``, ``2025 Form 540 Instructions``,
    ``Publication 15-T (2026)``, ``for 2026`` and form links such as
    ``/forms/2025/`` or ``WEB(2025)`` are read; a title that states exactly one
    year and no issue date is read as applying to that year. When several
    years are stated, the latest wins.
    """
    title = title or ""
    href = unquote(href or "")
    years: list[int] = []
    for pattern in (_APPLIES_LABELLED, _APPLIES_YEAR_FIRST, _APPLIES_FOR):
        for match in pattern.finditer(title):
            years += [int(group) for group in match.groups() if group]
    years += [int(match.group(1)) for match in _APPLIES_PAREN.finditer(title)]
    if not years:
        for pattern in _APPLIES_HREF:
            years += [int(match.group(1)) for match in pattern.finditer(href)]
    if not years and extract_publication_date(title) is None:
        bare = {int(match.group(1)) for match in _FOUR_DIGIT_YEAR.finditer(title)}
        if len(bare) == 1:
            years = list(bare)
    return max(years) if years else None


def pre_freeze_status(
    evidence: DateEvidence | None,
    applies_to_year: int | None,
    freeze: date = FREEZE_DATE,
) -> bool | None:
    """True if a citation was certainly issued before the freeze, False if
    certainly on or after it, None if that is unknown.

    A stated issue date decides. Without one, a document that applies to year
    Y is taken to be issued between January 1 of Y-1 and December 31 of Y+1
    (a 2026 form can appear in late 2025; instructions for 2026 appear in
    2027).
    """
    if evidence is not None:
        earliest, latest = evidence.earliest, evidence.latest
    elif applies_to_year is not None:
        earliest = date(applies_to_year - 1, 1, 1)
        latest = date(applies_to_year + 1, 12, 31)
    else:
        return None
    if latest < freeze:
        return True
    if earliest >= freeze:
        return False
    return None


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


def normalize_references(raw: Any, level: str = "parameter") -> list[dict]:
    """A parameter's ``metadata.reference`` as a list of ``{title, href, level}``.

    Accepts a list or a single item; each item may be a ``{title, href}``
    mapping or a bare string (a link if it looks like one, else a title).
    """
    if raw is None:
        return []
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    found = []
    for item in items:
        if isinstance(item, Mapping):
            title = item.get("title")
            href = item.get("href")
        elif isinstance(item, str):
            looks_like_link = item.strip().lower().startswith(("http", "www."))
            title, href = (None, item) if looks_like_link else (item, None)
        else:
            continue
        title = str(title).strip() if title not in (None, "") else None
        href = str(href).strip() if href not in (None, "") else None
        if title is None and href is None:
            continue
        found.append({"title": title, "href": href, "level": level})
    return found


def citation_host(href: str | None) -> str | None:
    """The lower-case host of a citation link (the archived link for Wayback)."""
    if not href:
        return None
    text = href.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.IGNORECASE):
        text = "http://" + text
    try:
        host = (urlsplit(text).hostname or "").lower()
    except ValueError:
        return None
    if host == "web.archive.org":
        inner = re.search(r"/web/[^/]*/(.+)$", text)
        if inner:
            return citation_host(inner.group(1))
    return host[4:] if host.startswith("www.") else host or None


def _host_matches(host: str, domains: Iterable[str]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def source_class(title: str | None, href: str | None) -> str:
    """``government``, ``law_republisher`` or ``other``, from the link's host.

    Without a link, a title naming federal law, the Federal Register or an IRS
    issuance counts as a government source.
    """
    host = citation_host(href)
    if host:
        if _host_matches(host, LAW_REPUBLISHER_HOSTS):
            return "law_republisher"
        if host.endswith(GOVERNMENT_SUFFIXES) or _host_matches(host, GOVERNMENT_HOSTS):
            return "government"
        return "other"
    title = title or ""
    if re.search(
        r"\bU\.?\s?S\.?\s?C\b|\bC\.?\s?F\.?\s?R\b|federal\s+register|public\s+law|"
        r"\b\d{1,3}\s+(?:FR|Fed\.?\s*Reg\.?)\s+\d|"
        r"internal\s+revenue|\bIRS\b|rev(?:enue)?\.?\s*proc",
        title,
        re.IGNORECASE,
    ):
        return "government"
    return "other"


def citation_kind(title: str | None, href: str | None) -> str:
    """What a citation is: index data, withholding guidance, regulation,
    register notice, agency publication, statute, or other.

    Checked in that order of precedence, except that strong agency-publication
    words (``Rev. Proc.``, ``Form``, ``Instructions``, ``Bulletin``...) win over
    statute words and weak ones (``rates``, ``standards``...) lose to them.
    """
    title = title or ""
    link = unquote(href or "")
    host = citation_host(href) or ""
    text = f"{title} {link}"
    if _host_matches(host, INDEX_HOSTS) or _INDEX_TITLE.search(title):
        if not _AGENCY_STRONG.search(title) or _host_matches(host, INDEX_HOSTS):
            return "index_data"
    if _WITHHOLDING.search(text):
        return "withholding"
    if _host_matches(host, _REGULATION_HOSTS) or _REGULATION.search(title):
        return "regulation"
    if _host_matches(host, _REGISTER_HOSTS) or _REGISTER.search(title):
        return "register"
    if _AGENCY_STRONG.search(title):
        return "agency_publication"
    if _STATUTE_HOST.search(host) or _STATUTE.search(title):
        return "statute"
    if _AGENCY_WEAK.search(title) or any(part in host for part in _AGENCY_HOST_PARTS):
        return "agency_publication"
    if source_class(title, href) == "government":
        return "agency_publication"
    return "other"


def classify_citation(
    title: str | None, href: str | None = None, level: str = "parameter"
) -> dict[str, Any]:
    """Classify one citation: source, kind, stated dates and freeze status.

    ``kind`` is ``citation_kind``, except that a register notice or agency
    publication on a host that is not a government source counts as
    ``other``. ``pre_freeze`` is ``pre_freeze_status`` of the stated dates,
    except for a statute or regulation, whose stated date is usually an
    effective date or a code edition: its status is None.
    ``dated_for_2026`` is true when the citation applies to 2026, or was issued
    in 2025 or 2026 and names no other year it applies to.
    ``dated_2026_publication`` is true for a government register notice or
    agency publication dated for 2026 and not dated after the freeze.
    ``recent_law`` is true for a statute or regulation that states 2025 or 2026
    (a session, a bill year) or names the 119th Congress.
    """
    title = None if title in (None, "") else str(title)
    href = None if href in (None, "") else str(href)
    text = " ".join(part for part in (title, unquote(href or "")) if part)
    evidence = extract_publication_date(text)
    applies = extract_applies_to_year(title, href)
    source = source_class(title, href)
    kind = citation_kind(title, href)
    if source != "government" and kind in QUALIFYING_KINDS:
        kind = "other"  # a news story or advocacy page is not an agency's own
    # A date a statute or regulation citation states is usually an effective
    # date or a code edition, not when the law was published.
    if kind in ("statute", "regulation"):
        pre_freeze = None
    else:
        pre_freeze = pre_freeze_status(evidence, applies)
    issued_year = (
        evidence.latest.year
        if evidence is not None and evidence.earliest.year == evidence.latest.year
        else None
    )
    if applies is not None:
        for_2026 = applies == REFERENCE_YEAR
    else:
        for_2026 = issued_year in (REFERENCE_YEAR - 1, REFERENCE_YEAR)
    recent = (REFERENCE_YEAR - 1, REFERENCE_YEAR)
    law_years = stated_years(text) | congress_years(text)
    return {
        "title": title,
        "href": href,
        "level": level,
        "host": citation_host(href),
        "source_class": source,
        "kind": kind,
        "publication_date": None if evidence is None else evidence.to_dict(),
        "applies_to_year": applies,
        "pre_freeze": pre_freeze,
        "dated_for_2026": bool(for_2026),
        "dated_2026_publication": bool(
            source == "government"
            and kind in QUALIFYING_KINDS
            and pre_freeze is not False
            and for_2026
        ),
        "recent_law": bool(
            kind in ("statute", "regulation") and law_years & set(recent)
        ),
    }


def congress_years(text: str | None) -> set[int]:
    """The two calendar years of each Congress a citation names.

    ``119th-congress`` or ``119th Congress`` (as in a congress.gov link or
    title), and public law numbers (``Pub. L. No. 119-21``, ``P.L. 119-21``,
    ``PLAW-119publ21``), name the 119th Congress, which sits in 2025 and 2026.
    """
    if not text:
        return set()
    years = set()
    for match in _CONGRESS.finditer(text):
        number = int(next(group for group in match.groups() if group))
        if 1 <= number <= 200:
            years |= {1787 + 2 * number, 1788 + 2 * number}
    return years


SUPPORT_TIERS = (
    "2026_publication",
    "undated_publication",
    "recent_law",
    "inputs_only",
    "other",
)


def supports_2026_value(citation: Mapping[str, Any], category: str = "law") -> bool:
    """Whether a classified citation is a candidate publication of a 2026 value.

    For an economic series (a price index or projection) the index release
    itself publishes the value, so a government index-data citation dated for
    2026 counts too.
    """
    if citation.get("dated_2026_publication"):
        return True
    return bool(
        category == "economic_series"
        and citation.get("kind") == "index_data"
        and citation.get("source_class") == "government"
        and citation.get("pre_freeze") is not False
        and citation.get("dated_for_2026")
    )


def explicit_support(
    citations: Sequence[Mapping[str, Any]], category: str = "law"
) -> str:
    """The strongest support an explicit 2026 entry's citations give its value.

    ``2026_publication``: a candidate 2026 publication (``supports_2026_value``).
    ``undated_publication``: a government register notice or agency
    publication that states no date or year (often a page listing every
    year's amounts). ``recent_law``: a statute or regulation from 2025 or 2026,
    which may state the amount itself. ``inputs_only``: withholding guidance or
    index data for 2025 or 2026, which are inputs to an amount, not the amount.
    ``other``: none of these.
    """
    if any(supports_2026_value(c, category) for c in citations):
        return "2026_publication"
    if any(
        c.get("source_class") == "government"
        and c.get("kind") in QUALIFYING_KINDS
        and c.get("publication_date") is None
        and c.get("applies_to_year") is None
        for c in citations
    ):
        return "undated_publication"
    if any(c.get("recent_law") for c in citations):
        return "recent_law"
    if any(
        c.get("kind") in ("withholding", "index_data") and c.get("dated_for_2026")
        for c in citations
    ):
        return "inputs_only"
    return "other"


# ---------------------------------------------------------------------------
# YAML entries and comments
# ---------------------------------------------------------------------------


def parameter_key_path(name: str, file_root: str) -> list[str] | None:
    """Where a parameter sits inside the YAML file that defines ``file_root``.

    ``gov.x.amount.SINGLE`` in ``gov.x.amount`` is ``["SINGLE"]``; a scale
    leaf ``gov.x.rates[1].threshold`` in ``gov.x.rates`` is
    ``["[1]", "threshold"]``; the file's own parameter is ``[]``. Returns
    None when the name is not inside the file.
    """
    if name == file_root:
        return []
    if not file_root:
        rest = name
    elif name.startswith(file_root + ".") or name.startswith(file_root + "["):
        rest = name[len(file_root) :]
    else:
        return None
    return _NAME_TOKEN.findall(rest)


def ancestor_names(name: str) -> list[str]:
    """Every proper ancestor of a parameter name, nearest first.

    ``gov.x.rates[1].threshold`` gives ``gov.x.rates[1]``, ``gov.x.rates``,
    ``gov.x`` and ``gov``.
    """
    names = []
    for match in re.finditer(r"\.|\[", name):
        names.append(name[: match.start()])
    return [ancestor for ancestor in reversed(names) if ancestor]


def _inline_comment(line: str) -> str | None:
    quote = None
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == "#" and (index == 0 or line[index - 1] in " \t"):
            return line[index + 1 :].strip()
    return None


def entry_comments(yaml_text: str, key_path: Sequence[str], instant: str) -> list[str]:
    """The comments written beside one dated entry of a parameter's YAML.

    The entry is the line whose key is ``instant`` under ``key_path`` (as
    ``parameter_key_path`` gives it; ``values`` and ``brackets`` wrappers are
    skipped). Its comments are the comment lines directly above it and any
    comment at the end of the line. Returns an empty list if the entry is not
    found.
    """
    target = [*key_path, instant]
    lines = yaml_text.splitlines()
    stack: list[tuple[int, str]] = []
    counters: dict[tuple[str, ...], int] = {}
    for number, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = stripped
        dash = content.startswith("- ") or content == "-"
        while stack and (
            stack[-1][0] > indent
            or (stack[-1][0] == indent and (not dash or stack[-1][1].startswith("[")))
        ):
            stack.pop()
        if dash:
            parent = tuple(token for _, token in stack)
            index = counters.get(parent, 0)
            counters[parent] = index + 1
            stack.append((indent, f"[{index}]"))
            content = content[1:].lstrip()
            indent += 2
            if not content:
                continue
        match = _KEY_LINE.match(content)
        if not match:
            continue
        key = match.group(1).strip().strip("'\"")
        stack.append((indent, key))
        path = [token for _, token in stack if token not in ("values", "brackets")]
        if path != target:
            continue
        comments = []
        above = number - 1
        while above >= 0 and lines[above].strip().startswith("#"):
            comments.append(lines[above].strip().lstrip("#").strip())
            above -= 1
        comments.reverse()
        inline = _inline_comment(content)
        if inline:
            comments.append(inline)
        return [comment for comment in comments if comment]
    return []


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        if isinstance(node.value, bool):
            raise ValueError("bool")
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        return _BINARY_OPERATORS[type(node.op)](
            _evaluate(node.left), _evaluate(node.right)
        )
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_evaluate(node.operand))
    raise ValueError(f"unsupported expression: {ast.dump(node)}")


def evaluate_arithmetic(text: str) -> list[tuple[str, float]]:
    """Arithmetic expressions written in a comment, with their values.

    Only numbers (with ``,`` or ``_`` thousands separators), ``+ - * / × ÷``
    and parentheses are read; an expression needs a multiplication or a
    division. Anything else is ignored, never executed.
    """
    found = []
    for match in _EXPRESSION.finditer(text):
        raw = match.group(0).strip()
        if not re.search(r"[*/×÷]", raw) or len(re.findall(r"\d+", raw)) < 2:
            continue
        expression = _THOUSANDS.sub("", raw).replace("×", "*").replace("÷", "/")
        while expression.count("(") > expression.count(")") and "(" in expression:
            expression = expression[expression.index("(") + 1 :]
        while expression.count(")") > expression.count("(") and ")" in expression:
            expression = expression[: expression.rindex(")")]
        try:
            value = _evaluate(ast.parse(expression.strip(), mode="eval"))
        except (SyntaxError, ValueError, ZeroDivisionError, RecursionError):
            continue
        found.append((raw, value))
    return found


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def comment_computation(comments: Sequence[str], value: Any) -> dict | None:
    """Whether an entry's comments show PolicyEngine computed its value.

    ``computation`` is true when an arithmetic expression in a comment rounds
    to the value (within 0.51; only for values of at least 1, since a
    statutory fraction such as ``2/37`` is not a computed amount), when a
    comment calls the value a projection or an estimate, or when it names an
    index (CPI, uprating) beside a multiplication (``times``, ``*``). An index
    named alone can describe how an agency set its published amount, so it
    does not count. Returns None when there are no comments.
    """
    if not comments:
        return None
    text = " ".join(comments)
    projection = sorted(
        {match.group(0).lower() for match in _PROJECTION_WORDS.finditer(text)}
    )
    index = sorted({match.group(0).lower() for match in _INDEX_WORDS.finditer(text)})
    number = _numeric(value)
    expressions = []
    for raw, result in evaluate_arithmetic(text):
        matches = (
            number is not None and abs(number) >= 1 and abs(result - number) <= 0.51
        )
        expressions.append({"text": raw, "result": result, "matches_value": matches})
    multiplied = bool(_MULTIPLICATION_WORDS.search(text))
    return {
        "comments": list(comments),
        "keywords": sorted(set(projection) | set(index)),
        "expressions": expressions,
        "computation": bool(projection)
        or (bool(index) and multiplied)
        or any(e["matches_value"] for e in expressions),
    }


# ---------------------------------------------------------------------------
# Origins and flags
# ---------------------------------------------------------------------------


def same_value(a: Any, b: Any) -> bool:
    """Parameter values compared as the engine stores them (floats to 1e-9)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b or abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same_value(x, y) for x, y in zip(a, b))
    return a == b


def classify_origin(
    *,
    entry_instant: str | None,
    value: Any,
    yaml_entries: Mapping[str, Mapping[str, Any]] | None,
    uprated_instants: Iterable[str],
    interpolated: bool,
    load_updates: Sequence[Mapping[str, Any]],
    reference_value: Any,
    convention_modules: Sequence[str],
    year: int = REFERENCE_YEAR,
) -> tuple[str, str, dict]:
    """A value's origin, its origin in the plain system, and the evidence.

    ``entry_instant`` and ``value`` describe the plain system's entry in effect;
    ``yaml_entries`` maps each date the parameter's own YAML lists to
    ``{"value": ...}`` (None when the parameter has no YAML source);
    ``uprated_instants`` are the dates core's uprating added;
    ``load_updates`` are ``Parameter.update`` calls run while the plain tree
    loaded that cover the instant. The value is convention-set when a
    ``latest_final`` part's update covers the instant or the reference value
    differs from the plain one.
    """
    detail: dict[str, Any] = {}
    uprated = set(uprated_instants)
    if entry_instant is None:
        baseline = "unresolved"
        detail["reason"] = "no entry is in effect"
    elif (
        yaml_entries is not None
        and entry_instant in yaml_entries
        and same_value(yaml_entries[entry_instant].get("value"), value)
    ):
        detail["yaml_entry"] = entry_instant
        if entry_instant.startswith(str(year)):
            baseline = "explicit_2026"
        elif entry_instant < f"{year}-01-01":
            baseline = "carried_forward"
        else:
            baseline = "unresolved"
            detail["reason"] = "the entry in effect is dated after the year"
    elif entry_instant in uprated:
        baseline = "uprated"
        detail["uprated_entry"] = entry_instant
    elif interpolated:
        baseline = "interpolated"
    elif load_updates:
        writers = sorted({str(item.get("caller")) for item in load_updates})
        detail["writers"] = writers
        if any(BACKDATE_WRITER in writer for writer in writers):
            baseline = "backdated"
            if yaml_entries:
                detail["backdated_from"] = min(yaml_entries)
        else:
            baseline = "computed_at_load"
    elif yaml_entries is None:
        baseline = "created_at_load"
    else:
        baseline = "unresolved"
        detail["reason"] = f"the YAML lists no entry at {entry_instant} with this value"
    convention = bool(convention_modules) or not same_value(reference_value, value)
    if convention:
        detail["convention_modules"] = list(convention_modules)
    return ("convention" if convention else baseline), baseline, detail


def value_flags(
    origin: str,
    citations: Sequence[Mapping[str, Any]],
    *,
    convention_modules: Sequence[str] = (),
    comment_evidence: Mapping[str, Any] | None = None,
    category: str = "law",
) -> list[str]:
    """The flags of one (parameter, 2026 value), in ``FLAGS`` order.

    A convention-set value gets ``convention_set`` and nothing else: the
    convention, not the parameter's YAML, is then what the reference rests on.
    ``category`` matters only for an explicit 2026 entry: an economic series
    accepts an index release as its 2026 publication (``supports_2026_value``).
    """
    if origin not in ORIGINS:
        raise ValueError(f"unknown origin: {origin!r}")
    if origin == "convention" or convention_modules:
        return ["convention_set"]
    flags = set()
    if origin in COMPUTED_ORIGINS:
        flags.add("computed_or_indexed")
    if origin == "explicit_2026" and not any(
        supports_2026_value(citation, category) for citation in citations
    ):
        flags.add("explicit_2026_without_2026_publication")
    if comment_evidence and comment_evidence.get("computation"):
        flags.add("computed_in_yaml_comment")
    if origin == "created_at_load":
        flags.add("created_at_load")
    if origin == "unresolved":
        flags.add("origin_unresolved")
    if not any(citation.get("source_class") == "government" for citation in citations):
        flags.add("no_government_citation")
    statuses = [citation.get("pre_freeze") for citation in citations]
    if any(status is False for status in statuses) and not any(
        status is True for status in statuses
    ):
        flags.add("post_freeze_citation")
    if origin == "carried_forward":
        flags.add("carried_forward")
    return [flag for flag in FLAGS if flag in flags]


def parameter_category(name: str) -> str:
    """``model_switch`` (abolitions, contributed reforms, simulation switches),
    ``economic_series`` (price indexes, projections, calibration and uprating
    series) or ``law``.
    """
    if name.startswith(MODEL_SWITCH_PREFIXES):
        return "model_switch"
    if name.startswith(ECONOMIC_SERIES_PREFIXES) or ".uprating" in name:
        return "economic_series"
    return "law"


def value_kind(value: Any) -> str:
    """``switch`` (a bool), ``list`` (a list of names) or ``number``."""
    if isinstance(value, bool):
        return "switch"
    if isinstance(value, list):
        return "list"
    return "number"


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

LOUISIANA_STANDARD_DEDUCTION = "gov.states.la.tax.income.deductions.standard.amount"
# The flags that say the 2026 amount itself may not have been published.
PUBLICATION_FLAGS = (
    "computed_or_indexed",
    "explicit_2026_without_2026_publication",
    "computed_in_yaml_comment",
    "created_at_load",
    "origin_unresolved",
    "post_freeze_citation",
)


YAML_ROOT = "policyengine_us/parameters/"
# Fields an engine fact carries into its report entry.
FACT_FIELDS = (
    "parameter",
    "value",
    "entry_instant",
    "instants",
    "origin",
    "baseline_origin",
    "baseline_value",
    "baseline_entry_instant",
    "origin_detail",
    "convention_modules",
    "label",
    "unit",
    "uprating",
    "yaml_file",
    "yaml_comments",
    "scored_cells",
    "unscored_cells",
)


def build_entry(fact: Mapping[str, Any]) -> dict[str, Any]:
    """One report entry from one engine fact: citations classified, flags set.

    The entry keeps ``FACT_FIELDS`` (the plain-system value and date default to
    the reference ones; ``yaml_file`` is relative to ``YAML_ROOT``) and adds
    the category, value kind, classified citations, comment evidence, explicit
    2026 support, flags and cell counts.
    """
    category = parameter_category(fact["parameter"])
    citations = [
        classify_citation(item.get("title"), item.get("href"), item.get("level", ""))
        for item in fact.get("references") or []
    ]
    comments = list(fact.get("yaml_comments") or [])
    evidence = comment_computation(comments, fact.get("value"))
    flags = value_flags(
        fact["origin"],
        citations,
        convention_modules=fact.get("convention_modules") or (),
        comment_evidence=evidence,
        category=category,
    )
    entry = {field: fact.get(field) for field in FACT_FIELDS}
    entry["baseline_origin"] = entry["baseline_origin"] or fact["origin"]
    if "baseline_value" not in fact:
        entry["baseline_value"] = fact.get("value")
    if not entry["baseline_entry_instant"]:
        entry["baseline_entry_instant"] = fact.get("entry_instant")
    detail = dict(entry["origin_detail"] or {})
    detail.pop("yaml_entry", None)  # the baseline entry date says the same
    entry["origin_detail"] = detail
    entry["convention_modules"] = list(entry["convention_modules"] or [])
    entry["instants"] = list(entry["instants"] or [])
    entry["yaml_comments"] = comments
    yaml_file = entry["yaml_file"]
    if yaml_file and yaml_file.startswith(YAML_ROOT):
        entry["yaml_file"] = yaml_file[len(YAML_ROOT) :]
    entry["scored_cells"] = sorted(fact.get("scored_cells") or [])
    entry["unscored_cells"] = sorted(fact.get("unscored_cells") or [])
    entry["category"] = category
    entry["value_kind"] = value_kind(fact.get("value"))
    entry["citations"] = citations
    entry["comment_evidence"] = evidence
    entry["explicit_2026_support"] = (
        explicit_support(citations, category)
        if fact["origin"] == "explicit_2026"
        else None
    )
    entry["flags"] = flags
    entry["review"] = any(flag in REVIEW_FLAGS for flag in flags)
    entry["publication_review"] = any(flag in PUBLICATION_FLAGS for flag in flags)
    entry["scored_cell_count"] = len(entry["scored_cells"])
    entry["unscored_cell_count"] = len(entry["unscored_cells"])
    return entry


def _flag_counts(entries: Sequence[Mapping[str, Any]], flag: str) -> dict[str, int]:
    hits = [entry for entry in entries if flag in entry["flags"]]
    return {
        "values": len(hits),
        "law_values": sum(entry["category"] == "law" for entry in hits),
        "parameters": len({entry["parameter"] for entry in hits}),
        "scored_cells": len({cell for entry in hits for cell in entry["scored_cells"]}),
    }


def summarize(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Counts over the entries read by at least one scored cell."""
    scored = [entry for entry in entries if entry["scored_cell_count"]]
    review = [entry for entry in scored if entry["review"]]
    publication = [entry for entry in scored if entry["publication_review"]]
    unpublished_explicit = [
        entry
        for entry in scored
        if "explicit_2026_without_2026_publication" in entry["flags"]
    ]
    return {
        "values": len(entries),
        "values_read_by_scored_cells": len(scored),
        "values_read_only_by_unscored_cells": len(entries) - len(scored),
        "parameters_read_by_scored_cells": len({e["parameter"] for e in scored}),
        "scored_cells_reading_any_value": len(
            {cell for entry in scored for cell in entry["scored_cells"]}
        ),
        "by_flag": {flag: _flag_counts(scored, flag) for flag in FLAGS},
        "by_origin": dict(sorted(Counter(e["origin"] for e in scored).items())),
        "by_category": dict(sorted(Counter(e["category"] for e in scored).items())),
        "review_values": len(review),
        "review_values_by_category": dict(
            sorted(Counter(e["category"] for e in review).items())
        ),
        "scored_cells_reading_a_review_value": len(
            {cell for entry in review for cell in entry["scored_cells"]}
        ),
        "publication_review_values": len(publication),
        "publication_review_law_values": sum(
            entry["category"] == "law" for entry in publication
        ),
        "scored_cells_reading_a_publication_review_value": len(
            {cell for entry in publication for cell in entry["scored_cells"]}
        ),
        "explicit_2026_without_2026_publication_by_support": {
            tier: sum(e["explicit_2026_support"] == tier for e in unpublished_explicit)
            for tier in SUPPORT_TIERS
        },
        "explicit_2026_without_2026_publication_by_kind": dict(
            sorted(Counter(e["value_kind"] for e in unpublished_explicit).items())
        ),
    }


def _sort_key(entry: Mapping[str, Any]) -> tuple:
    return (
        -entry["scored_cell_count"],
        entry["parameter"],
        entry["entry_instant"] or "",
    )


def _format_value(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, (int, float)):
        if float(value).is_integer() and abs(value) >= 1:
            return f"{value:,.0f}"
        return f"{value:.6g}"
    text = str(value)
    return text if len(text) <= 40 else text[:37] + "..."


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


_DISPLAY_KIND_ORDER = (
    "register",
    "agency_publication",
    "regulation",
    "statute",
    "withholding",
    "index_data",
    "other",
)


def _citation_rank(citation: Mapping[str, Any]) -> tuple:
    return (
        not citation["dated_2026_publication"],
        citation["source_class"] != "government",
        _DISPLAY_KIND_ORDER.index(citation["kind"]),
        citation["pre_freeze"] is not True,
    )


def _citation_label(citation: Mapping[str, Any], width: int = 60) -> str:
    label = citation["title"] or citation["host"] or citation["href"] or ""
    if len(label) > width:
        label = label[: width - 3] + "..."
    if citation["publication_date"]:
        label += f", {citation['publication_date']['latest']}"
    elif citation["applies_to_year"]:
        label += f", for {citation['applies_to_year']}"
    return f"{citation['kind']}: {label}"


def _best_citation(entry: Mapping[str, Any]) -> str:
    citations = entry["citations"]
    if not citations:
        return "none"
    best = sorted(citations, key=_citation_rank)[0]
    return f"{_citation_label(best)} ({len(citations)} cited)"


def _flag_list(flags: Iterable[str], keep: Iterable[str]) -> str:
    keep = set(keep)
    return ", ".join(flag for flag in flags if flag in keep)


def _louisiana_lines(entries: Sequence[Mapping[str, Any]]) -> list[str]:
    louisiana = sorted(
        (
            entry
            for entry in entries
            if entry["parameter"].startswith(LOUISIANA_STANDARD_DEDUCTION + ".")
        ),
        key=lambda entry: entry["parameter"],
    )
    lines = ["## Louisiana standard deduction", ""]
    if not louisiana:
        return lines + ["No cell reads this parameter.", ""]
    first = louisiana[0]
    lines += [
        f"policyengine-us {first.get('policyengine_us', '2.15.17')} holds "
        f"`{LOUISIANA_STANDARD_DEDUCTION}` in `{first.get('yaml_file')}`."
        + (
            " The parameter carries `uprating` metadata "
            f"(`{first.get('uprating')}`), so years after its last entry are "
            "uprated at load."
            if first.get("indexed_parameter")
            else ""
        ),
        "",
    ]
    for entry in louisiana:
        cells = entry["scored_cells"]
        lines.append(
            f"- `{entry['parameter']}` = {_format_value(entry['value'])} from the "
            f"entry dated {entry['entry_instant']} (origin `{entry['origin']}`, "
            f"support `{entry['explicit_2026_support']}`); flags: "
            f"{', '.join(f'`{flag}`' for flag in entry['flags']) or 'none'}; read by "
            f"{len(cells)} scored cells"
            + (
                f" ({', '.join(cells[:8])}{'...' if len(cells) > 8 else ''})"
                if cells
                else ""
            )
            + "."
        )
        evidence = entry.get("comment_evidence") or {}
        for comment in evidence.get("comments") or []:
            lines.append(f"  - YAML comment: {comment}")
        for expression in evidence.get("expressions") or []:
            lines.append(
                f"  - `{expression['text']}` = {expression['result']:,.2f}; "
                f"reproduces the value: {expression['matches_value']}."
            )
    lines += ["", "Its citations, as classified:", ""]
    for citation in louisiana[0]["citations"]:
        date_text = (citation["publication_date"] or {}).get("latest", "none stated")
        lines.append(
            f"- {citation['title'] or citation['href']} ({citation['host']}): "
            f"{citation['source_class']}, {citation['kind']}; issue date {date_text}; "
            f"applies to {citation['applies_to_year'] or 'no stated year'}; "
            f"pre-freeze {citation['pre_freeze']}; 2026 publication "
            f"{citation['dated_2026_publication']}."
        )
    candidates = sum(
        supports_2026_value(c, first["category"]) for c in first["citations"]
    )
    lines += [
        "",
        f"{candidates} of the {len(first['citations'])} citations is a candidate "
        "2026 publication under this check's rules. The audit brief records that "
        "the Louisiana Department of Revenue published $12,875 (provisional "
        "withholding) before the freeze and $12,838 (RIB 26-019) on 2026-09-28; "
        "this check reads only metadata and has not read those documents.",
        "",
    ]
    return lines


def render_markdown(report: Mapping[str, Any], table_limit: int = 200) -> str:
    """The Markdown summary of a report built by ``build_report``."""
    meta = report["meta"]
    summary = report["summary"]
    entries = report["entries"]
    value_check = meta.get("recorded_value_check") or {}
    lines = [
        "# Publication sources of 2026 reference parameters",
        "",
        "For every 2026 parameter value a scored PolicyBench reference reads, this "
        "report says where the value comes from (a YAML entry dated in 2026, an "
        "older entry carried forward, a value computed while the parameter tree "
        "loads, or a reference convention) and whether its citations include a "
        "government publication for 2026 not dated after the "
        f"{FREEZE_DATE.isoformat()} freeze. Generated by "
        "`reference_audit/2026-10-05-reference-adversary/scripts/publication_sources.py`"
        " with `policybench.publication_sources`; every entry, citation and cell is in "
        "`publication_sources.json`.",
        "",
        f"- Reference system: {meta.get('reference_system')}; policyengine-us "
        f"{meta.get('policyengine_us')}, policyengine-core "
        f"{meta.get('policyengine_core')}.",
        f"- Payload `{meta.get('payload')}`, sha256 `{meta.get('payload_sha256')}`.",
        f"- Reproduction: {meta.get('outputs_recomputed')} outputs recomputed "
        f"({meta.get('scored_cells_recomputed')} scored); "
        f"{meta.get('scored_reference_mismatches')} scored references differ beyond "
        "1e-3.",
        f"- Recorded leaf values checked against the reference tree: "
        f"{value_check.get('checked')}; differing: "
        f"{len(value_check.get('mismatches') or [])}.",
        f"- Households recomputed in reverse output order: "
        f"{meta.get('reverse_order_households')}; outputs whose reads changed: "
        f"{len(meta.get('reverse_order_mismatches') or [])}.",
        "",
        "## Counts",
        "",
        f"{summary['values_read_by_scored_cells']:,} (parameter, 2026 value) pairs "
        f"across {summary['parameters_read_by_scored_cells']:,} parameters are read "
        f"by {summary['scored_cells_reading_any_value']:,} scored cells; "
        f"{summary['values_read_only_by_unscored_cells']:,} more are read only by "
        "unscored cells (listed in the JSON, not counted below). "
        f"{summary['publication_review_values']:,} values "
        f"({summary['publication_review_law_values']:,} of them law parameters) carry "
        "a flag saying the 2026 amount may not have been published before the "
        f"freeze; {summary['scored_cells_reading_a_publication_review_value']:,} "
        "scored cells read at least one.",
        "",
        "| Flag | Values | Law values | Parameters | Scored cells |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for flag, counts in summary["by_flag"].items():
        lines.append(
            f"| `{flag}` | {counts['values']:,} | {counts['law_values']:,} | "
            f"{counts['parameters']:,} | {counts['scored_cells']:,} |"
        )
    lines += ["", "| Origin | Values |", "| --- | ---: |"]
    for origin, count in summary["by_origin"].items():
        lines.append(f"| `{origin}` | {count:,} |")
    tiers = summary["explicit_2026_without_2026_publication_by_support"]
    lines += [
        "",
        "Explicit 2026 entries without a 2026 publication, by the strongest support "
        "their citations do give: "
        + ", ".join(
            f"{tier} {count:,}"
            for tier, count in tiers.items()
            if tier != "2026_publication"
        )
        + "; by value kind: "
        + ", ".join(
            f"{kind} {count:,}"
            for kind, count in summary[
                "explicit_2026_without_2026_publication_by_kind"
            ].items()
        )
        + ". `undated_publication` means an agency page that names no date or year "
        "(often one listing every year's amounts); `recent_law` a 2025 or 2026 "
        "statute or regulation, which may itself state the amount; `inputs_only` "
        "withholding guidance or index data, which feed an amount without stating "
        "it; `other` none of these.",
        "",
    ]
    lines += _louisiana_lines(entries)

    flagged = sorted(
        (
            entry
            for entry in entries
            if entry["publication_review"]
            and entry["scored_cell_count"]
            and entry["category"] == "law"
        ),
        key=_sort_key,
    )
    shown = flagged[:table_limit]
    lines += [
        "## Law values whose 2026 amount may not have been published",
        "",
        f"{len(flagged):,} law values read by scored cells carry one of "
        + ", ".join(f"`{flag}`" for flag in PUBLICATION_FLAGS)
        + f". Ordered by the scored cells reading them; the first {len(shown)} are "
        "shown.",
        "",
        "| # | Parameter | 2026 value | Unit | Entry | Origin | Flags | Support | "
        "Scored cells | Best citation |",
        "| ---: | --- | ---: | --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for rank, entry in enumerate(shown, 1):
        lines.append(
            f"| {rank} | `{_cell(entry['parameter'])}` | "
            f"{_cell(_format_value(entry['value']))} | "
            f"{_cell(entry.get('unit') or '')} | "
            f"{entry['entry_instant']} | {entry['origin']} | "
            f"{_flag_list(entry['flags'], PUBLICATION_FLAGS)} | "
            f"{entry['explicit_2026_support'] or ''} | {entry['scored_cell_count']} | "
            f"{_cell(_best_citation(entry))} |"
        )

    uncited = sorted(
        (
            entry
            for entry in entries
            if entry["scored_cell_count"]
            and entry["category"] == "law"
            and not entry["publication_review"]
            and "no_government_citation" in entry["flags"]
        ),
        key=_sort_key,
    )
    hosts = Counter(
        citation["host"] or "(no link)"
        for entry in uncited
        for citation in entry["citations"]
    )
    lines += [
        "",
        "## Law values cited to no government source",
        "",
        f"{len(uncited):,} further law values read by scored cells have no "
        "publication flag but cite no government source (most cite a law "
        "republisher such as Cornell LII, or nothing). Most cited hosts: "
        + (
            ", ".join(f"{host} {count:,}" for host, count in hosts.most_common(8))
            or "none"
        )
        + f". The {min(40, len(uncited))} read by the most scored cells:",
        "",
        "| # | Parameter | 2026 value | Entry | Origin | Scored cells "
        "| Best citation |",
        "| ---: | --- | ---: | --- | --- | ---: | --- |",
    ]
    for rank, entry in enumerate(uncited[:40], 1):
        lines.append(
            f"| {rank} | `{_cell(entry['parameter'])}` | "
            f"{_cell(_format_value(entry['value']))} | {entry['entry_instant']} | "
            f"{entry['origin']} | {entry['scored_cell_count']} | "
            f"{_cell(_best_citation(entry))} |"
        )

    conventions = sorted(
        (
            e
            for e in entries
            if "convention_set" in e["flags"] and e["scored_cell_count"]
        ),
        key=_sort_key,
    )
    modules = Counter(
        module
        for entry in conventions
        for module in entry["convention_modules"] or ["(value differs)"]
    )
    other = report.get("other_instants") or []
    lines += [
        "",
        "## Convention-set values",
        "",
        f"{len(conventions):,} values read by scored cells come from `latest_final`, "
        "so their own YAML is not what the reference rests on: "
        + (
            ", ".join(
                f"`{module}` {count:,}" for module, count in sorted(modules.items())
            )
            or "none"
        )
        + ".",
        "",
        "## Economic series and model switches",
        "",
        "Of the values read by scored cells, "
        f"{summary['by_category'].get('economic_series', 0):,} are economic series "
        "(price indexes, projections, calibration and uprating series) and "
        f"{summary['by_category'].get('model_switch', 0):,} are model "
        "switches; they are flagged like any other value in the JSON but left out "
        "of the tables above.",
        "",
        "## Reads at instants outside 2026",
        "",
        f"{len(other):,} (parameter, instant) reads fall outside 2026 (prior-year "
        "lookbacks and similar), "
        f"{sum(1 for item in other if item['scored_cells']):,} of them by scored "
        "cells. They are listed under `other_instants` in the JSON and not flagged.",
        "",
        "## What this check can and cannot show",
        "",
        "- It reads citation metadata, not the cited documents. A 2026 publication "
        "among a value's citations is a candidate only: this check does not show "
        "that the publication states the value. A flagged value is one with no "
        "such candidate.",
        "- A statute or regulation citation dates the law, not the 2026 amount, so "
        "it never counts as a 2026 publication. Withholding guidance and index "
        "releases (CPI) do not count either, except that an index release counts "
        "for an economic series.",
        "- Dates are what a title or link states. A document that names only the "
        "year it applies to is taken to be issued between the year before and the "
        "year after, so its freeze status is usually unknown. A date a statute or "
        "regulation citation states is usually an effective date, so statute and "
        "regulation citations have no freeze status.",
        "- `backdated` values come from policyengine-us's `backdate_parameters`, "
        "which copies each parameter's earliest value back to 2015; when that "
        "earliest entry is dated after a 2026 instant the reference reads, the "
        "value read is one the YAML itself dates only from that later entry "
        "(`origin_detail.backdated_from`).",
        "- Citations are the value's own entry, the parameter's metadata and the "
        "nodes defined in the same YAML file; folder `index.yaml` citations are "
        "not read.",
        "- Reads are recorded inside formula calculation. Parameters read while a "
        "simulation is constructed (structural-reform switches) and the "
        "`gov.abolitions.*` switches core reads before every variable are not "
        "recorded.",
        "",
    ]
    return "\n".join(lines)


# Entry fields the JSON leaves out when they hold their default, and how
# ``expand_report`` restores them.
_SPARSE_DEFAULTS = {
    "baseline_value": lambda entry: entry["value"],
    "baseline_entry_instant": lambda entry: entry["entry_instant"],
    "baseline_origin": lambda entry: entry["origin"],
    "origin_detail": lambda entry: {},
    "convention_modules": lambda entry: [],
    "uprating": lambda entry: None,
    "yaml_comments": lambda entry: [],
    "comment_evidence": lambda entry: None,
    "explicit_2026_support": lambda entry: None,
    "label": lambda entry: None,
    "unit": lambda entry: None,
    "instants": lambda entry: [f"{REFERENCE_YEAR}-01-01"],
}
# Entry fields the JSON leaves out because ``expand_report`` recomputes them.
_DERIVED = {
    "category": lambda entry: parameter_category(entry["parameter"]),
    "value_kind": lambda entry: value_kind(entry["value"]),
    "review": lambda entry: any(flag in REVIEW_FLAGS for flag in entry["flags"]),
    "publication_review": lambda entry: any(
        flag in PUBLICATION_FLAGS for flag in entry["flags"]
    ),
    "scored_cell_count": lambda entry: len(entry["scored_cells"]),
    "unscored_cell_count": lambda entry: len(entry["unscored_cells"]),
}
ENCODING = (
    "Cells are 'scenario_id/output' strings listed once in 'cells'. "
    "'cell_sets' lists sorted index lists into 'cells'; an entry's "
    "'scored_cells' and 'unscored_cells' are indexes into 'cell_sets'. "
    "'citations' lists each distinct classified citation once and "
    "'citation_lists' each distinct list of [index into 'citations', level] "
    "pairs; an entry's 'citations' is an index into 'citation_lists'. Entry "
    "fields equal to their default are omitted: baseline_value, "
    "baseline_entry_instant and baseline_origin default to value, "
    "entry_instant and origin; origin_detail to {}; convention_modules and "
    "yaml_comments to []; instants to ['2026-01-01']; uprating, "
    "comment_evidence, explicit_2026_support, label and unit to null. "
    "category, value_kind, review, publication_review and the cell counts are "
    "not stored: they follow from parameter, value, flags and cells. "
    "yaml_file is relative to meta.yaml_root. "
    "policybench.publication_sources.expand_report decodes all of this."
)


def _same_json(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def compact_report(
    meta: Mapping[str, Any],
    summary: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    other_instants: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """The JSON form of a report: cells, cell sets and citations listed once."""
    every_cell = sorted(
        {
            cell
            for item in [*entries, *other_instants]
            for key in ("scored_cells", "unscored_cells")
            for cell in item[key]
        }
    )
    cell_index = {cell: index for index, cell in enumerate(every_cell)}
    cell_sets: list[list[int]] = []
    set_index: dict[tuple[int, ...], int] = {}

    def cell_set(cells: Iterable[str]) -> int:
        key = tuple(sorted(cell_index[cell] for cell in cells))
        if key not in set_index:
            set_index[key] = len(cell_sets)
            cell_sets.append(list(key))
        return set_index[key]

    citations: list[dict] = []
    citation_index: dict[str, int] = {}
    citation_lists: list[list] = []
    list_index: dict[str, int] = {}

    def citation_ref(citation: Mapping[str, Any]) -> list:
        body = {key: value for key, value in citation.items() if key != "level"}
        key = json.dumps(body, sort_keys=True)
        if key not in citation_index:
            citation_index[key] = len(citations)
            citations.append(body)
        return [citation_index[key], citation["level"]]

    def citation_list(items: Sequence[Mapping[str, Any]]) -> int:
        refs = [citation_ref(citation) for citation in items]
        key = json.dumps(refs)
        if key not in list_index:
            list_index[key] = len(citation_lists)
            citation_lists.append(refs)
        return list_index[key]

    compact_entries = []
    for entry in entries:
        item = dict(entry)
        for field, default in _SPARSE_DEFAULTS.items():
            if field in item and _same_json(item[field], default(entry)):
                del item[field]
        for field in _DERIVED:
            item.pop(field, None)
        item["citations"] = citation_list(entry["citations"])
        item["scored_cells"] = cell_set(entry["scored_cells"])
        item["unscored_cells"] = cell_set(entry["unscored_cells"])
        compact_entries.append(item)
    compact_other = [
        {
            **item,
            "scored_cells": cell_set(item["scored_cells"]),
            "unscored_cells": cell_set(item["unscored_cells"]),
        }
        for item in other_instants
    ]
    return {
        "meta": {**dict(meta), "encoding": ENCODING, "yaml_root": YAML_ROOT},
        "summary": dict(summary),
        "cells": every_cell,
        "cell_sets": cell_sets,
        "citations": citations,
        "citation_lists": citation_lists,
        "entries": compact_entries,
        "other_instants": compact_other,
    }


def expand_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Decode a ``compact_report`` back to entries with cell and citation lists."""
    cells = report["cells"]
    sets = [[cells[index] for index in cell_set] for cell_set in report["cell_sets"]]
    citations = report["citations"]
    lists = report["citation_lists"]
    entries = []
    for item in report["entries"]:
        entry = dict(item)
        entry["citations"] = [
            {**citations[index], "level": level}
            for index, level in lists[item["citations"]]
        ]
        entry["scored_cells"] = list(sets[item["scored_cells"]])
        entry["unscored_cells"] = list(sets[item["unscored_cells"]])
        for field, default in _SPARSE_DEFAULTS.items():
            if field not in entry:
                entry[field] = default(entry)
        for field, derive in _DERIVED.items():
            entry[field] = derive(entry)
        entries.append(entry)
    other = [
        {
            **item,
            "scored_cells": list(sets[item["scored_cells"]]),
            "unscored_cells": list(sets[item["unscored_cells"]]),
        }
        for item in report.get("other_instants") or []
    ]
    return {
        "meta": dict(report["meta"]),
        "summary": dict(report["summary"]),
        "entries": entries,
        "other_instants": other,
    }


def dumps_report(report: Mapping[str, Any]) -> str:
    """The report as JSON text with one list item per line.

    Valid JSON (``json.loads`` reads it back unchanged), compact within an
    item, and line-oriented so a regenerated report diffs entry by entry.
    """
    parts = []
    for key in sorted(report):
        value = report[key]
        if isinstance(value, list):
            items = ",\n".join(
                json.dumps(item, sort_keys=True, separators=(",", ":"))
                for item in value
            )
            body = f"[\n{items}\n]" if value else "[]"
        else:
            body = json.dumps(value, sort_keys=True, indent=1)
        parts.append(f"{json.dumps(key)}: {body}")
    return "{\n" + ",\n".join(parts) + "\n}\n"


def build_report(
    facts: Sequence[Mapping[str, Any]],
    other_instants: Sequence[Mapping[str, Any]],
    meta: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    """The JSON report (``compact_report`` form) and its Markdown summary."""
    entries = sorted(
        (build_entry(fact) for fact in facts),
        key=lambda e: (e["parameter"], e["entry_instant"] or ""),
    )
    other = sorted(
        (
            {
                "parameter": item["parameter"],
                "instant": item["instant"],
                "value": item.get("value"),
                "scored_cells": sorted(item.get("scored_cells") or []),
                "unscored_cells": sorted(item.get("unscored_cells") or []),
            }
            for item in other_instants
        ),
        key=lambda item: (item["parameter"], item["instant"]),
    )
    full_meta = {
        **dict(meta),
        "freeze_date": FREEZE_DATE.isoformat(),
        "reference_year": REFERENCE_YEAR,
        "flags": list(FLAGS),
        "review_flags": list(REVIEW_FLAGS),
        "publication_flags": list(PUBLICATION_FLAGS),
        "origins": list(ORIGINS),
        "support_tiers": list(SUPPORT_TIERS),
    }
    summary = summarize(entries)
    expanded = {
        "meta": full_meta,
        "summary": summary,
        "entries": entries,
        "other_instants": other,
    }
    return compact_report(full_meta, summary, entries, other), render_markdown(expanded)
