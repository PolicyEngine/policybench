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
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

import pytest

from policybench.paper_results import r
from policybench.snapshot_payload import read_run_payload

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
    # Exclusion covers what the audits found, not every defect or unstated
    # input: an output a fix or reading not run on the reference engine would
    # move can still be scored (the paper's limitations say so).
    r"every\s+output\s+whose\s+reference\s+rests\s+on",
    r"every\s+output\s+whose\s+reference\s+depends\s+on",
    r"re-ran\s+five",
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


def _pdf_running_text() -> str:
    """The PDF's text with the page-number lines at page breaks removed, so a
    sentence that crosses a page reads as one sentence."""
    pages = _pdf_text().split("\f")
    kept = []
    for page in pages:
        lines = page.splitlines()
        while lines and (not lines[-1].strip() or lines[-1].strip().isdigit()):
            lines.pop()
        while lines and (not lines[0].strip() or lines[0].strip().isdigit()):
            lines.pop(0)
        kept.append("\n".join(lines))
    return "\n".join(kept)


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
    dashboard = read_run_payload(run_dir)
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
    # Outputs excluded from scoring (scored=false) are annotated as description
    # only; the audit universe is the scored rows.
    excluded_outputs = {
        (scenario_id, variable)
        for (_, scenario_id, variable), row in prediction_rows
        if row.get("scored") is False
    }
    prediction_rows = [
        (row_key, row)
        for row_key, row in prediction_rows
        if (row_key[1], row_key[2]) not in excluded_outputs
    ]
    annotated = {
        row_key
        for row_key in annotated
        if (row_key[1], row_key[2]) not in excluded_outputs
    }
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
    """The chunked-row count comes from the app's copy of the frozen serving
    configuration and the model total from the board payload; the app tests
    (app/tests/boardScope.test.ts) render the sentence against both."""
    text = re.sub(r"\s+", " ", METHODOLOGY.read_text())
    assert "chunkedServingModels().length" in text
    assert "of the ${noToolsModels.length} models" in text
    assert re.search(r"\b[A-Z][a-z]+ of the \d+ models", text) is None
    assert "because the provider rejects a forced tool call" in text
    leaderboard = re.sub(r"\s+", " ", LEADERBOARD.read_text())
    assert "jsonContractClaudeModels()" in leaderboard
    assert "Claude Sonnet 5.5 reject" not in leaderboard


def test_methodology_recheck_count_is_the_sidecar_record():
    """The one engine-upgrade fact the payload does not carry: how many
    excluded outputs moved on the new engine and were re-reviewed."""
    sidecar = json.loads(
        (
            ROOT
            / "paper/snapshot/20260501/runs"
            / "us_full_run_20260612_policyengine_4_16_1_populace"
            / "reference_outputs.csv.meta.json"
        ).read_text()
    )
    upgrade = next(r for r in sidecar["revisions"] if r["kind"] == "engine_upgrade")
    source = (ROOT / "app/src/lib/referenceEngine.ts").read_text()
    engine = upgrade["engine_version"].removeprefix("policyengine-us ")
    assert f'engineVersion: "{engine}"' in source
    assert f"rechecked: {len(upgrade['excluded_outputs_rechecked'])}," in source


def test_serving_config_has_both_transports():
    rows = _serving_rows()
    contracts = {row["answer_contract"] for row in rows}
    assert contracts == {"tool", "json"}, contracts
    json_models = sorted(
        row["model"] for row in rows if row["answer_contract"] == "json"
    )
    assert "claude-fable-5.1" in json_models
    assert "claude-opus-5.5" in json_models


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
        "annotated": 7_772,
        "exact_misses": 7_768,
        "annotated_exact_misses": 7_768,
        "annotated_exact_hits": 4,
        "unannotated_below_full_bounded_score": 2_027,
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
        "household_dataset",
        "population_weight_artifact",
        "audit_annotation_artifacts",
        "reproducibility_notes",
    )
    guide = PAPER_GUIDE.read_text()

    for key in checklist_keys:
        assert f"`{key}`" in guide
        assert key in manifest


SENSITIVITY_NOTE = ROOT / "sensitivity" / "claude-thinking-2026-08.md"
FORCED_TOOL_OVERCLAIMS = (
    r"whose\s+provider\s+accepts\s+a\s+forced\s+tool",
    r"wherever\s+the\s+provider\s+accepts\s+one",
    r"every\s+model\s+whose\s+provider\s+accepts",
)


@pytest.mark.parametrize("path", [LEADERBOARD, SENSITIVITY_NOTE])
def test_forced_tool_claims_are_qualified_by_contract(path):
    """Forcing applies to rows on the tool contract, not to every provider that
    accepts a forced tool: the older Gemini rows take JSON from their family
    default, and some cards select JSON without recording a rejection."""
    text = re.sub(r"\s+", " ", path.read_text())
    for pattern in FORCED_TOOL_OVERCLAIMS:
        assert re.search(pattern, text, re.IGNORECASE) is None, (
            f"{path.name} still matches {pattern!r}"
        )
    assert (
        re.search(r"(selects? (the tool contract|JSON)|on the tool contract)", text)
        is not None
    ), path.name


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
    """JSON rows exist for two reasons -- a provider that rejects a forced
    tool, and a model card or its family default that selects JSON -- and the
    copy must not attribute all of them to provider capability, nor attribute
    the DeepSeek rows to a family choice: DeepSeek V4.1 Flash's card records
    the rejection (and says the same of the V4 rows), and the family default
    now reaches only the older Gemini rows."""
    for path in (METHODOLOGY, BENCHMARK_CARD, SENSITIVITY_NOTE):
        text = re.sub(r"\s+", " ", path.read_text())
        assert "rejects a forced tool" in text, path.name
        assert "selects JSON" in text, path.name
        assert re.search(r"Gemini and DeepSeek", text) is None, path.name
        assert re.search(r"DeepSeek[^.]{0,40}famil", text) is None, path.name


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


def _hyphen_insensitive(text: str) -> str:
    """LaTeX breaks lines at hyphens and text extraction can drop them."""
    return text.replace("-", "")


def _serving_evidence_sentence() -> str:
    return r.serving_evidence_caption


def test_rendered_html_reports_serving_evidence_summary():
    parser = _VisibleTextParser()
    parser.feed(PAPER_HTML.read_text())
    html_text = _straight_quotes(re.sub(r"\s+", " ", " ".join(parser.parts)))
    assert _serving_evidence_sentence() in html_text


def test_rendered_pdf_reports_serving_evidence_summary():
    pdf_text = _straight_quotes(re.sub(r"\s+", " ", _pdf_text()))
    assert _hyphen_insensitive(_serving_evidence_sentence()) in _hyphen_insensitive(
        pdf_text
    )


# The cost-and-latency sentence and table print dollar amounts. Quarto once
# printed an inline string's repr there (a literal "\\$0.002") and the raw
# DataFrame table kept the Markdown escape ("\$0.034") and its index column.
COST_SENTENCE = re.compile(
    r"Per-household cost spans \$\d+\.\d{3} \([^)]+\) to \$\d+\.\d{3} \([^)]+\)"
)


def _cost_latency_table_cells(html: str) -> list[list[str]]:
    start = html.index('id="tbl-us-cost-latency"')
    table = html[start : html.index("</table>", start)]
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)
    return [
        [
            re.sub(r"<[^>]+>", "", cell).strip()
            for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
        ]
        for row in rows
    ]


def test_rendered_html_prints_dollar_amounts_without_escapes():
    html = PAPER_HTML.read_text()
    parser = _VisibleTextParser()
    parser.feed(html)
    text = re.sub(r"\s+", " ", " ".join(parser.parts))
    assert "\\$" not in text
    assert COST_SENTENCE.search(text), "cost sentence missing or escaped"
    header, *rows = _cost_latency_table_cells(html)
    # md_table puts a zero-width space after each slash as a line break point.
    assert [cell.replace("\u200b", "") for cell in header] == [
        "Model",
        "Exact (%)",
        "Cost / household",
        "Latency (median)",
    ]
    assert len(rows) == r.n_models
    for row in rows:
        assert not row[0].isdigit(), row  # no DataFrame index column
        assert re.fullmatch(r"\$\d+\.\d{3}|—", row[2]), row


def test_rendered_pdf_prints_dollar_amounts_without_escapes():
    text = re.sub(r"\s+", " ", _pdf_text())
    assert "\\$" not in text
    assert COST_SENTENCE.search(text), "cost sentence missing or escaped"


def _paper_engine_times() -> tuple[str, str]:
    """The paper's engine sentences, as the timing record dates them."""
    timing = json.loads(
        (ROOT / "reference_audit/2026-09-28/verification/sweep_timing.json").read_text()
    )
    uploaded = timing["pypi"]["wheel_uploaded_at_utc"][r.policyengine_us_version]
    read_at = timing["pypi"]["read_at_utc"]
    return (
        "the newest release when it began sweeping the references that day "
        f"(uploaded {uploaded[11:16]} UTC)",
        f"policyengine-us {timing['pypi']['newest_at_read']}, the newest release "
        f"when PolicyBench checked PyPI on {read_at[:10]} at {read_at[11:16]} UTC, "
        f"gives the same value as {r.policyengine_us_version}",
    )


# The HTML and PDF halves of each paper claim are separate tests: the HTML is
# checked everywhere, and only the PDF half skips where neither pdftotext nor
# pypdf is available (as in CI).


def _html_text() -> str:
    parser = _VisibleTextParser()
    parser.feed(PAPER_HTML.read_text())
    return _straight_quotes(re.sub(r"\s+", " ", " ".join(parser.parts)))


def _abstract_exclusion_sentence() -> str:
    counts = (r.engine_defect_exclusion_count, r.unlisted_input_exclusion_count)
    assert sum(counts) == r.excluded_output_count
    return (
        "PolicyBench excludes from scoring, for every model, the "
        f"{counts[0]} outputs whose references rest on engine defects the audits "
        f"found and upstream has not fixed, and the {counts[1]} whose references "
        "depend on an input the prompt does not state."
    )


def test_paper_abstract_scopes_the_exclusions_to_what_the_audits_found():
    assert _abstract_exclusion_sentence() in _html_text()


def test_rendered_pdf_abstract_scopes_the_exclusions_to_what_the_audits_found():
    text = _straight_quotes(re.sub(r"\s+", " ", _pdf_running_text()))
    assert _abstract_exclusion_sentence() in text


def test_pdf_running_text_joins_a_sentence_across_a_page_break(monkeypatch):
    import sys

    module = sys.modules[__name__]
    monkeypatch.setattr(
        module, "_pdf_text", lambda: "the 28 outputs whose\n\n2\n\f3\nreferences rest"
    )
    assert (
        re.sub(r"\s+", " ", _pdf_running_text())
        == "the 28 outputs whose references rest"
    )


def test_paper_takes_its_engine_times_from_the_timing_record():
    """The paper renders both clock times from sweep_timing.json through
    paper_results; its source hard-codes none."""
    source = PAPER.read_text()
    assert re.search(r"\d\d:\d\d UTC", source) is None
    assert "r.reference_engine_uploaded_utc" in source
    assert "r.publication_check_pypi_read_utc" in source
    text = _html_text()
    for sentence in _paper_engine_times():
        assert sentence in text, sentence


def test_rendered_pdf_takes_its_engine_times_from_the_timing_record():
    text = _straight_quotes(re.sub(r"\s+", " ", _pdf_text()))
    for sentence in _paper_engine_times():
        assert sentence in text, sentence


def test_live_version_description_states_the_reference_engines():
    """The dataset selector's one-line description of the live board names the
    engine behind each scored reference and the engines behind the excluded
    outputs' values, from the frozen records."""
    run_dir = (
        ROOT
        / "paper/snapshot/20260501/runs"
        / "us_full_run_20260612_policyengine_4_16_1_populace"
    )
    sidecar = json.loads((run_dir / "reference_outputs.csv.meta.json").read_text())
    upgrade = next(r for r in sidecar["revisions"] if r["kind"] == "engine_upgrade")
    engine = upgrade["engine_version"].removeprefix("policyengine-us ")
    previous = upgrade["previous_engine_version"].removeprefix("policyengine-us ")
    exclusions = json.loads((run_dir / "reference_exclusions.json").read_text())[
        "exclusions"
    ]
    by_engine = Counter(
        e["engine_version"].removeprefix("policyengine-us ") for e in exclusions
    )
    assert set(by_engine) == {previous, engine}
    versions = json.loads(VERSIONS.read_text())
    live = next(v for v in versions["versions"] if v["id"] == versions["default"])
    assert live["description"].startswith(
        f"Scored reference outputs from policyengine-us {engine} (the "
        f"{len(exclusions)} excluded outputs keep the values they were decided "
        f"on: {by_engine[previous]} from policyengine-us {previous}, "
        f"{by_engine[engine]} from {engine}, and the "
        f"{len(upgrade['excluded_outputs_rechecked'])} that move on {engine} were "
        "re-reviewed and stay excluded); "
    )


def test_newest_engine_claims_are_anchored_to_a_time():
    """policyengine-us releases often, so "newest" holds only at a stated time:
    2.15.17 when PolicyBench began sweeping the references (2026-09-29), 2.17.0
    when PolicyBench checked PyPI later that day. The upgrade record states the
    standing rule the same way: the newest release when PolicyBench begins the
    reference sweep, checked before publishing against the newest release on
    PyPI, with the time recorded. No surface claims what is newest "at
    publication", which a later release could make stale."""
    anchored = (
        "newest release when PolicyBench began sweeping",
        "newest release when it began sweeping",
        "newest release when PolicyBench checked PyPI on",
        "newest policyengine-us release when PolicyBench begins the",
        "PolicyBench checks that the newest release on PyPI gives the same "
        "values, and records when it checked",
        "PolicyBench read PyPI on 2026-09-29 at 14:58 UTC, when policyengine-us "
        "2.17.0 was the newest release",
    )
    surfaces = (
        BENCHMARK_CARD,
        PAPER,
        PAPER_GUIDE,
        METHODOLOGY,
        VERSIONS,
        ROOT / "README.md",
        ROOT / "reference_audit/2026-09-28/README.md",
        ROOT / "app/src/notes/2026-09-29-claude-sonnet-5-5-debuts-fourth.json",
        ROOT / "app/src/notes/2026-09-23-five-snap-households-bbce.json",
        SENSITIVITY_NOTE,
    )
    for path in surfaces:
        text = re.sub(r"\s+", " ", path.read_text())
        assert "at publication" not in text, path.name
        for match in re.finditer(r"newest", text):
            window = text[max(0, match.start() - 100) : match.end() + 80]
            assert any(phrase in window for phrase in anchored), (path.name, window)


def test_card_states_the_engines_behind_scored_and_excluded_references():
    """The card's engine sentences, rebuilt from the sidecar, the exclusion
    record and the publication-check sweep."""
    run_dir = (
        ROOT
        / "paper/snapshot/20260501/runs"
        / "us_full_run_20260612_policyengine_4_16_1_populace"
    )
    sidecar = json.loads((run_dir / "reference_outputs.csv.meta.json").read_text())
    upgrade = next(r for r in sidecar["revisions"] if r["kind"] == "engine_upgrade")
    engine = upgrade["engine_version"].removeprefix("policyengine-us ")
    previous = upgrade["previous_engine_version"].removeprefix("policyengine-us ")
    exclusions = json.loads((run_dir / "reference_exclusions.json").read_text())[
        "exclusions"
    ]
    by_engine = Counter(
        e["engine_version"].removeprefix("policyengine-us ") for e in exclusions
    )
    with (ROOT / "reference_audit/2026-09-28/verification/latest_final_2170.csv").open(
        newline=""
    ) as source:
        rows = list(csv.DictReader(source))
    (check,) = {row["engine"] for row in rows}
    card = re.sub(r"\s+", " ", BENCHMARK_CARD.read_text())
    assert (
        "PolicyBench computes each scored US reference by running "
        f"`policyengine_us.Simulation` from policyengine-us {engine}, the newest "
        "release when PolicyBench began sweeping the references on 2026-09-29"
    ) in card
    assert (
        f"The {len(exclusions)} excluded outputs keep the values they were decided "
        f"on ({by_engine[previous]} computed with policyengine-us {previous}, "
        f"{by_engine[engine]} with {engine}), and PolicyBench re-reviewed the "
        f"{len(upgrade['excluded_outputs_rechecked'])} of them that move on {engine}"
    ) in card
    # The card's two times are the timing record's: the reference engine's
    # PyPI upload, and when PolicyBench read PyPI for the check.
    timing = json.loads(
        (ROOT / "reference_audit/2026-09-28/verification/sweep_timing.json").read_text()
    )
    uploaded = timing["pypi"]["wheel_uploaded_at_utc"][engine]
    read_at = timing["pypi"]["read_at_utc"]
    assert timing["pypi"]["newest_at_read"] == check
    assert (
        "the newest release when PolicyBench began sweeping the references on "
        f"{timing['reference_sweep']['first_output_at_utc'][:10]} (uploaded "
        f"{uploaded[11:16]} UTC)."
    ) in card
    assert (
        f"policyengine-us {check}, the newest release when PolicyBench checked "
        f"PyPI on {read_at[:10]} at {read_at[11:16]} UTC, gives the same value as "
        f"{engine} for all {len(rows):,} outputs under the same conventions and "
        "adapter."
    ) in card
    # No other clock time appears in the card.
    assert sorted(set(re.findall(r"\b\d\d:\d\d UTC", card))) == sorted(
        {f"{uploaded[11:16]} UTC", f"{read_at[11:16]} UTC"}
    )


def _app_model_labels() -> dict[str, str]:
    source = (ROOT / "app" / "src" / "modelMeta.ts").read_text()
    block = source[source.index("export const MODEL_LABELS") :]
    block = block[: block.index("};")]
    return dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', block))


def test_json_transport_rows_are_attributed_as_their_cards_record():
    """The card names each JSON-contract row with the reason its model card
    records: the provider rejects a forced tool call, or the card (or, for the
    older Gemini rows, the family default) selects JSON. The app copy's
    assumption holds too: every Claude row on the JSON contract is one whose
    API rejects forced tool use, and such rows are most JSON rows."""
    from policybench.model_cards import card_for

    serving = json.loads(SERVING_CONFIG.read_text())["models"]
    labels = _app_model_labels()
    rejecting, card_choice, family_default = [], [], []
    for model, treatment in serving.items():
        if treatment["answer_contract"] != "json":
            continue
        card = card_for(treatment["provider_id"])
        notes = card.notes if card is not None else ""
        if re.search(r"reject|returns 400", notes, re.IGNORECASE):
            rejecting.append(model)
        elif card is not None and card.answer_contract == "json":
            card_choice.append(model)
        else:
            assert treatment["provider_id"].startswith("gemini/"), model
            family_default.append(model)
        if model.startswith("claude-"):
            assert model in rejecting, model
            assert "The API rejects forced tool use" in notes, model
    assert len(rejecting) > len(card_choice) + len(family_default)
    assert "as for the V4 rows" in card_for("deepseek/deepseek-flash").notes

    card = re.sub(r"\s+", " ", BENCHMARK_CARD.read_text())
    start = card.index("For most JSON rows the card records that the provider")
    rejection_sentence = card[start : card.index(". The cards of", start)]
    choice_sentence = card[card.index("The cards of", start) :]
    choice_sentence = choice_sentence[: choice_sentence.index("family default.")]

    def names(model: str, sentence: str) -> bool:
        label = labels.get(model)
        return bool(label) and re.search(re.escape(label) + r"(?![\w.])", sentence)

    for model in rejecting:
        assert names(model, rejection_sentence), model
    for model in card_choice:
        assert names(model, choice_sentence), model
    assert family_default and "older Gemini rows" in choice_sentence
    # Exactly these rows: the sentences name no other board row.
    assert sorted(m for m in serving if names(m, rejection_sentence)) == sorted(
        rejecting
    )
    assert sorted(m for m in serving if names(m, choice_sentence)) == sorted(
        card_choice
    )
    methodology = re.sub(r"\s+", " ", METHODOLOGY.read_text())
    assert (
        "a JSON object where the model card or its family default selects JSON, "
        "for most such rows because the provider rejects a forced tool call."
    ) in methodology

    # The sensitivity note attributes the same rows the same way.
    note = re.sub(r"\s+", " ", SENSITIVITY_NOTE.read_text())
    start = note.index("For most of them the card records that the provider")
    note_choice = note[note.index("the cards of", start) :]
    note_choice = note_choice[: note_choice.index("family default.")]
    for model in card_choice:
        assert names(model, note_choice), model
    assert "older Gemini rows" in note_choice
    assert sorted(m for m in serving if names(m, note_choice)) == sorted(card_choice)
