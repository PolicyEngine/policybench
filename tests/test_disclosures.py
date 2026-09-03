"""The published request-shape disclosures must match the frozen serving config.

The site copy and the sensitivity doc describe how models were served. The
frozen ``model_serving_config.json`` is the machine-readable record of the
same facts, so the prose is checked against it rather than trusted.
"""

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVING_CONFIG = ROOT / "paper" / "snapshot" / "20260501" / "model_serving_config.json"
METHODOLOGY = ROOT / "app" / "src" / "components" / "Methodology.tsx"
VERSIONS = ROOT / "app" / "src" / "data.versions.json"
LEADERBOARD = ROOT / "app" / "src" / "components" / "ModelLeaderboard.tsx"
SENSITIVITY_DOC = ROOT / "sensitivity" / "claude-thinking-2026-08.md"
BENCHMARK_CARD = ROOT / "docs" / "benchmark_card.md"
MODEL_PAGE = ROOT / "app" / "src" / "app" / "model" / "[id]" / "page.tsx"
PAPER = ROOT / "paper" / "index.qmd"
PAPER_HTML = ROOT / "app" / "public" / "paper" / "web" / "index.html"
PAPER_PDF = ROOT / "app" / "public" / "paper" / "policybench.pdf"

NUMBER_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
}

FALSE_CLAIMS = (
    "identical forced-tool request",
    "identical prompt for every model",
    "one structured response per household",
    "identical request this board holds every",
    "holds every model to the identical request",
    "still-identical request shape",
    "Every model uses its provider's structured-output transport",
)

PAPER_FALSE_CLAIM_PATTERNS = (
    r"single\s+structured\s+response",
    r"one\s+response\s+per\s+household",
    r"one\s+structured\s+response",
    r"identical\s+request",
    r"identical\s+forced-tool\s+request",
    r"(?<!not\s)identical\s+across\s+models",
)


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _assert_no_false_paper_claims(path: Path, text: str) -> None:
    normalized = re.sub(r"\s+", " ", text)
    for pattern in PAPER_FALSE_CLAIM_PATTERNS:
        assert re.search(pattern, normalized, re.IGNORECASE) is None, (
            f"{path} still matches {pattern!r}"
        )


def _pdf_text() -> str:
    pdftotext = shutil.which("pdftotext")
    if pdftotext is not None:
        result = subprocess.run(
            [pdftotext, str(PAPER_PDF), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(PAPER_PDF)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _serving_rows() -> list[dict]:
    payload = json.loads(SERVING_CONFIG.read_text())
    rows = payload if isinstance(payload, list) else payload.get("models", payload)
    if isinstance(rows, dict):
        rows = [dict(model=key, **value) for key, value in rows.items()]
    return rows


def test_methodology_states_the_chunked_count_from_the_serving_config():
    rows = _serving_rows()
    chunked = [row for row in rows if row["request_shape"] != "whole scenario"]
    text = METHODOLOGY.read_text()
    phrase = f"{NUMBER_WORDS[len(chunked)].capitalize()} of the {len(rows)}"
    assert phrase in re.sub(r"\s+", " ", text), phrase
    assert "JSON object where the provider rejects a forced tool" in re.sub(
        r"\s+", " ", text
    )


def test_serving_config_has_both_transports():
    rows = _serving_rows()
    contracts = {row["answer_contract"] for row in rows}
    assert contracts == {"tool", "json"}, contracts
    json_models = sorted(
        row["model"] for row in rows if row["answer_contract"] == "json"
    )
    assert "claude-fable-5.1" in json_models


def test_current_board_copy_makes_no_identical_request_claim():
    for path in (
        METHODOLOGY,
        VERSIONS,
        LEADERBOARD,
        SENSITIVITY_DOC,
        BENCHMARK_CARD,
        MODEL_PAGE,
        PAPER,
    ):
        text = re.sub(r"\s+", " ", path.read_text())
        for claim in FALSE_CLAIMS:
            assert claim not in text, f"{path.name} still says {claim!r}"


def test_sensitivity_doc_names_the_subset_count_from_the_serving_config():
    rows = _serving_rows()
    chunked = [row for row in rows if row["request_shape"] != "whole scenario"]
    text = re.sub(r"\s+", " ", SENSITIVITY_DOC.read_text())
    phrase = (
        f"{NUMBER_WORDS[len(chunked)].capitalize()} models answer in one- or "
        "three-output subsets"
    )
    assert phrase in text, phrase


def test_paper_serving_table_publishes_the_transport_per_model():
    """The paper's serving table is what the copy points to as the per-model
    transport record, so it must carry the answer contract, not only request
    shape and reasoning setup."""
    text = PAPER.read_text()
    assert '"Transport": (' in text
    assert 'serving["answer_contract"]' in text
    rows = _serving_rows()
    assert {row["tool_choice"] for row in rows} == {"forced", None}
    for row in rows:
        assert (row["answer_contract"] == "tool") == (row["tool_choice"] == "forced")


def test_json_transport_copy_names_both_reasons():
    """JSON rows exist for two reasons — a provider that rejects a forced tool,
    and a model card that selects JSON for a family — and the copy must not
    attribute all of them to provider capability."""
    for path in (METHODOLOGY, BENCHMARK_CARD):
        text = re.sub(r"\s+", " ", path.read_text())
        assert "rejects a forced tool" in text, path.name
        assert "selects JSON" in text, path.name


def test_paper_source_and_rendered_html_make_no_false_request_claims():
    _assert_no_false_paper_claims(PAPER, PAPER.read_text())
    parser = _VisibleTextParser()
    parser.feed(PAPER_HTML.read_text())
    _assert_no_false_paper_claims(PAPER_HTML, " ".join(parser.parts))


def test_rendered_pdf_makes_no_false_request_claims():
    _assert_no_false_paper_claims(PAPER_PDF, _pdf_text())


def _straight_quotes(text: str) -> str:
    """Pandoc renders apostrophes as U+2019; compare against the source form."""
    return text.replace("\u2019", "'").replace("\u2018", "'")


def _serving_evidence_sentence() -> str:
    config = json.loads(SERVING_CONFIG.read_text())
    summary = config["evidence_summary"]
    return (
        f"Serving treatments for {summary['run_state']} rows are pinned from "
        "supervised-run fingerprints; the remaining "
        f"{summary['registry']} are the harness registry as frozen in the "
        "snapshot's serving-configuration file."
    )


def test_rendered_html_reports_serving_evidence_summary():
    parser = _VisibleTextParser()
    parser.feed(PAPER_HTML.read_text())
    html_text = _straight_quotes(re.sub(r"\s+", " ", " ".join(parser.parts)))
    assert _serving_evidence_sentence() in html_text


def test_rendered_pdf_reports_serving_evidence_summary():
    pdf_text = _straight_quotes(re.sub(r"\s+", " ", _pdf_text()))
    assert _serving_evidence_sentence() in pdf_text
