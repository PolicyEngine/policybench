"""The published request-shape disclosures must match the frozen serving config.

The site copy and the sensitivity doc describe how models were served. The
frozen ``model_serving_config.json`` is the machine-readable record of the
same facts, so the prose is checked against it rather than trusted.
"""

import csv
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
PAPER_GUIDE = ROOT / "docs" / "paper.md"
AUDIT_GUIDE = ROOT / "docs" / "audit.md"
MODEL_PAGE = ROOT / "app" / "src" / "app" / "model" / "[id]" / "page.tsx"
EXPAND_PAGE = ROOT / "app" / "src" / "app" / "expand" / "page.tsx"
PAPER_PAGE = ROOT / "app" / "src" / "app" / "paper" / "page.tsx"
SNAPSHOT_MANIFEST = ROOT / "paper" / "snapshot" / "20260501" / "manifest.json"
SCENARIO_EXPLORER = ROOT / "app" / "src" / "components" / "ScenarioExplorer.tsx"
PAPER = ROOT / "paper" / "index.qmd"
PAPER_HTML = ROOT / "app" / "public" / "paper" / "web" / "index.html"
PAPER_PDF = ROOT / "app" / "public" / "paper" / "policybench.pdf"
AUDIT_UNIVERSE = ROOT / "app" / "src" / "lib" / "auditUniverse.ts"

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
    r"every\s+wrong\s+(?:cell|model-output\s+row)",
    r"all\s+[^.]{0,100}rows\s+receiving\s+less\s+than\s+full\s+score",
    r"exhaustive\s+(?:annotation\s+coverage\s+for|over)\s+"
    r"(?:the\s+)?(?:scored[- ]?)?misses",
    r"scored-miss\s+audit\s+is\s+exhaustive",
)

AUDIT_FALSE_CLAIM_PATTERNS = (
    *PAPER_FALSE_CLAIM_PATTERNS[-4:],
    r"every\s+miss\s+(?:gets|is)\s+(?:a\s+)?diagnos",
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


def _audit_counts_from_frozen_files() -> dict[str, int]:
    manifest = json.loads(SNAPSHOT_MANIFEST.read_text())
    run_label = manifest["source_run_labels"]["us"]
    run_dir = ROOT / manifest["source_run_artifacts"][run_label]["path"]
    dashboard = json.loads((run_dir / "data.json").read_text())
    annotation_dir = ROOT / manifest["audit_annotation_artifacts"]["path"]
    with (annotation_dir / "us_audit_row_annotations.csv").open(newline="") as file:
        annotations = list(csv.DictReader(file))

    def key(model: str, scenario_id: str, variable: str) -> tuple[str, str, str]:
        return model, scenario_id, variable

    annotated = {
        key(row["model"], row["scenario_id"], row["variable"]) for row in annotations
    }
    prediction_rows = [
        (key(model, scenario_id, variable), row)
        for scenario_id, variable_map in dashboard["scenarioPredictions"].items()
        for variable, model_map in variable_map.items()
        for model, row in model_map.items()
    ]
    legacy_threshold = {
        row_key for row_key, row in prediction_rows if row["thresholdScore"] < 100
    }
    exact_misses = {row_key for row_key, row in prediction_rows if row["exact"] < 100}
    below_full_bounded_score = {
        row_key for row_key, row in prediction_rows if row["boundedScore"] < 100
    }

    assert annotated == legacy_threshold
    return {
        "annotated": len(annotated),
        "exact_misses": len(exact_misses),
        "annotated_exact_misses": len(annotated & exact_misses),
        "annotated_exact_hits": len(annotated - exact_misses),
        "unannotated_below_full_bounded_score": len(
            below_full_bounded_score - annotated
        ),
    }


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
        EXPAND_PAGE,
        PAPER,
    ):
        text = re.sub(r"\s+", " ", path.read_text())
        for claim in FALSE_CLAIMS:
            assert claim not in text, f"{path.name} still says {claim!r}"


def test_audit_disclosures_use_the_frozen_legacy_threshold_universe():
    counts = _audit_counts_from_frozen_files()
    assert counts == {
        "annotated": 7_840,
        "exact_misses": 7_838,
        "annotated_exact_misses": 7_838,
        "annotated_exact_hits": 2,
        "unannotated_below_full_bounded_score": 1_324,
    }

    for path in (
        PAPER,
        BENCHMARK_CARD,
        PAPER_GUIDE,
        AUDIT_GUIDE,
        METHODOLOGY,
        MODEL_PAGE,
        EXPAND_PAGE,
    ):
        normalized = re.sub(r"\s+", " ", path.read_text())
        for pattern in AUDIT_FALSE_CLAIM_PATTERNS:
            assert re.search(pattern, normalized, re.IGNORECASE) is None, (
                f"{path} still matches {pattern!r}"
            )

    for path in (BENCHMARK_CARD, PAPER_GUIDE):
        text = re.sub(r"\s+", " ", path.read_text())
        for count in counts.values():
            assert f"{count:,}" in text, (path, count)
        assert re.search(r"legacy threshold score is below 1", text, re.IGNORECASE)

    paper = PAPER.read_text()
    for accessor in (
        "audit_annotated_row_count_fmt",
        "audit_selection_rule",
        "exact_match_miss_count_fmt",
        "annotated_exact_miss_count_fmt",
        "annotated_exact_hit_count_fmt",
        "unannotated_below_full_bounded_score_count_fmt",
    ):
        assert f"r.{accessor}" in paper

    helper = AUDIT_UNIVERSE.read_text()
    assert "rows whose legacy threshold score is below 1" in helper
    for path in (METHODOLOGY, MODEL_PAGE):
        text = path.read_text()
        assert "summarizeAuditUniverse" in text
        assert "annotatedRowCount" in text
        assert "annotatedExactMissCount" in text
        assert "exactMissCount" in text
        assert "annotatedExactHitCount" in text
        assert "unannotatedBelowFullBoundedScoreCount" in text


def test_expand_page_has_no_literal_model_roster_count():
    text = EXPAND_PAGE.read_text()
    assert (
        re.search(
            r"\b\d+\s+(?:frontier|board)\s+models?\b",
            text,
            re.IGNORECASE,
        )
        is None
    )


def test_expand_page_does_not_describe_the_mixed_headline_as_amount_only():
    normalized = re.sub(r"\s+", " ", EXPAND_PAGE.read_text()).lower()
    assert "of amounts within $1" not in normalized
    assert "every miss diagnosed" not in normalized
    assert "every miss gets a diagnosed failure mode" not in normalized


def test_public_scoring_copy_names_the_headline_metric():
    manifest = json.loads(SNAPSHOT_MANIFEST.read_text())
    expected_metric = "household-impact-weighted exact-match rate"
    surfaces = {
        PAPER_PAGE: PAPER_PAGE.read_text(),
        SNAPSHOT_MANIFEST: manifest["description"],
        MODEL_PAGE: MODEL_PAGE.read_text(),
        METHODOLOGY: METHODOLOGY.read_text(),
    }

    assert expected_metric in surfaces[PAPER_PAGE]
    assert expected_metric in surfaces[SNAPSHOT_MANIFEST]
    for path, text in surfaces.items():
        normalized = re.sub(r"\s+", " ", text)
        for sentence in re.split(r"(?<=[.!?])\s+", normalized):
            if "household-equal" not in sentence.lower():
                continue
            assert "legacy" in sentence.lower(), path
            assert "secondary metric" in sentence.lower(), path


def test_paper_checklist_names_existing_manifest_keys():
    manifest = json.loads(SNAPSHOT_MANIFEST.read_text())
    checklist_keys = (
        "source_run_artifacts",
        "committed_snapshot_artifacts",
        "published_dashboard_artifact",
        "live_dashboard_artifact",
        "rendered_paper_artifacts",
        "reference_output_refresh",
        "population_weight_artifact",
        "audit_annotation_artifacts",
        "reproducibility_notes",
    )
    guide = PAPER_GUIDE.read_text()

    for key in checklist_keys:
        assert f"`{key}`" in guide
        assert key in manifest


def test_benchmark_card_snapshot_scope_matches_scenario_metadata():
    manifest = json.loads(SNAPSHOT_MANIFEST.read_text())
    run_label = manifest["source_run_labels"]["us"]
    run_dir = ROOT / manifest["source_run_artifacts"][run_label]["path"]
    scenario_metadata = json.loads((run_dir / "scenarios.csv.meta.json").read_text())
    text = re.sub(r"\s+", " ", BENCHMARK_CARD.read_text())
    expected = (
        f"current {manifest['snapshot_date']} snapshot scores "
        f"{scenario_metadata['num_scenarios']} public households whose scenario "
        "manifest was generated on "
        f"{scenario_metadata['generated_at_utc'][:10]} from a "
        f"{scenario_metadata['requested_num_scenarios']}-household request split "
        f"with seed {scenario_metadata['split_seed']}."
    )

    assert scenario_metadata["split"] == "public"
    assert expected in text


def test_scenario_explorer_retires_exact_every_model_prompt_claims():
    text = SCENARIO_EXPLORER.read_text()
    retired_patterns = (
        r"sent\s+to\s+(?:every|each|all)\s+models?",
        r"exact\s+(?:request\s+)?prompt",
        r"prompt\s+(?:that|which)?\s*(?:was\s+)?sent\s+to\s+"
        r"(?:every|each|all)\s+models?",
    )
    for pattern in retired_patterns:
        assert re.search(pattern, text, re.IGNORECASE) is None, pattern


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


def _assert_rendered_audit_scope(text: str) -> None:
    counts = _audit_counts_from_frozen_files()
    normalized = _straight_quotes(re.sub(r"\s+", " ", text))
    assert (
        f"{counts['annotated']:,} rows whose legacy threshold score is below 1"
        in normalized
    )
    assert (
        f"{counts['annotated_exact_misses']:,} of the snapshot's "
        f"{counts['exact_misses']:,} exact-match misses" in normalized
    )
    assert f"{counts['annotated_exact_hits']:,} exact hits" in normalized
    assert (
        f"{counts['unannotated_below_full_bounded_score']:,} additional rows "
        "with bounded score below 100" in normalized
    )


def test_rendered_html_reports_the_audit_universe():
    parser = _VisibleTextParser()
    parser.feed(PAPER_HTML.read_text())
    _assert_rendered_audit_scope(" ".join(parser.parts))


def test_rendered_pdf_reports_the_audit_universe():
    _assert_rendered_audit_scope(_pdf_text())


def _straight_quotes(text: str) -> str:
    """Pandoc renders apostrophes as U+2019; compare against the source form."""
    return text.replace("\u2019", "'").replace("\u2018", "'")


def _serving_evidence_sentence() -> str:
    config = json.loads(SERVING_CONFIG.read_text())
    summary = config["evidence_summary"]
    fields = config["evidence_field_labels"]

    def joined(items: list[str]) -> str:
        if len(items) == 2:
            return " and ".join(items)
        return f"{', '.join(items[:-1])}, and {items[-1]}"

    return (
        f"{NUMBER_WORDS[summary['run_state']].capitalize()} rows carry "
        "supervised-run fingerprints for "
        f"{joined(fields['run_state'])}; "
        f"{joined(fields['registry_for_run_state'])} for every row, and all "
        f"fields for the other {summary['registry']} rows, are the harness "
        "registry as frozen in the "
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
