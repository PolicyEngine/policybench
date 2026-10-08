"""Tests for the reference adversary's deterministic halves."""

from __future__ import annotations

import ast
import copy
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from policybench.adjudications import parse_adjudications, unresolved_suspect_cases
from policybench.audit import _case_id as audit_case_id
from policybench.consensus import ConsensusParams, consensus_flags
from policybench.prompts import get_variable_description
from policybench.reference_adversary import (
    BLOCKED_DOMAINS,
    QUEUE_COLUMNS,
    REFERENCE_FREEZE,
    STAGE1_SCHEMA,
    VERDICT_SCHEMA,
    VERDICT_SUGGESTIONS,
    VERDICTS,
    AdversaryCase,
    _case_id,
    adjudication_queue,
    apply_adversary_flags,
    blocked_search_result,
    blocked_url,
    build_adversary_cases,
    canonical_json,
    check_login,
    claude_transcript_audit,
    codex_events_audit,
    collect_adversary,
    load_case,
    load_derivations,
    main,
    merge_judges,
    output_errors,
    prepare_adversary,
    render_stage1_prompt,
    render_stage2_prompt,
    sha256_text,
    write_stage2_prompt,
)

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "policybench/reference_adversary.py"
RUN = "us_full_run_20260612_policyengine_4_16_1_populace"
FROZEN_PAYLOAD = ROOT / "paper/snapshot/20260501/runs" / RUN / "data.json.gz"
FROZEN_ANNOTATIONS = ROOT / "annotations" / RUN

TAX = "state_income_tax_before_refundable_credits"
MEDICAID = "head_medicaid_eligible"
MODELS = ["top-a", "top-b", "top-c", "mid-a", "mid-b", "mid-c"]
PAYLOAD_DERIVATION = "PAYLOAD-DERIVATION: the engine taxed the parents only."


def _household_prompt(state: str, variables: list[str]) -> str:
    lines = [
        "Estimate the requested tax and benefit outputs using only the household "
        "facts below. Treat any unlisted numeric input as 0.",
        "",
        "Household:",
        f"- state: {state}",
        "- tax year: 2026",
        "",
        "Provide the following policy quantities for this household:",
    ]
    lines += [f"- {v}: {get_variable_description(v)}" for v in variables]
    return "\n".join(lines)


def _entry(prediction, reference, explanation, *, parsed=True) -> dict:
    return {
        "prediction": prediction,
        "groundTruth": reference,
        "scored": True,
        "error": None if prediction is None else abs(prediction - reference),
        "parsed": parsed,
        "score": 12.5,
        "boundedScore": 12.5,
        "thresholdScore": 0.0,
        "exact": 0.0,
        "within1pct": 0.0,
        "within5pct": 0.0,
        "within10pct": 0.0,
        "explanation": explanation,
        "annotation": "DIAGNOSIS-ANNOTATION",
        "failureSource": "llm_error",
        "failureSubtype": "household_unit_or_filing_status",
        "caseAnnotation": "DIAGNOSIS-CASE-ANNOTATION",
        "caseFailureSources": "llm_error",
        "caseFailureSubtypes": "household_unit_or_filing_status",
        "referenceExplanation": PAYLOAD_DERIVATION,
    }


def _payload() -> dict:
    tax_reference = 3070.061279296875
    tax_answers = {
        "top-a": 4451.56,
        "top-b": 4451.56,
        "top-c": 4452.0,
        "mid-a": 4451.57,
        "mid-b": 3070.06,
        "mid-c": None,
    }
    medicaid_answers = {m: 1.0 for m in MODELS[:4]} | {"mid-b": 0.0, "mid-c": 0.0}
    return {
        "country": "us",
        "scenarios": {
            "scenario_001": {
                "country": "us",
                "state": "PA",
                "prompt": {
                    "tool": _household_prompt("PA", [TAX, MEDICAID]),
                    "json": "json contract prompt",
                },
            },
            "scenario_002": {
                "country": "us",
                "state": "MN",
                "prompt": {
                    "tool": _household_prompt("MN", [MEDICAID]),
                    "json": "json contract prompt",
                },
            },
        },
        "modelStats": [{"model": m} for m in MODELS],
        "scenarioPredictions": {
            "scenario_001": {
                TAX: {
                    m: _entry(
                        a,
                        tax_reference,
                        f"{m} taxed the whole household; value = {a}",
                        parsed=a is not None,
                    )
                    for m, a in tax_answers.items()
                },
                MEDICAID: {m: _entry(0.0, 0.0, f"{m}: not eligible") for m in MODELS},
            },
            "scenario_002": {
                MEDICAID: {
                    m: _entry(a, 0.0, f"{m}: expansion adult, eligible = {a}")
                    for m, a in medicaid_answers.items()
                }
            },
        },
    }


PARAMS = ConsensusParams(min_models=3, top_k=3, min_top=2, zero_cluster_min_models=3)


@pytest.fixture
def payload() -> dict:
    return _payload()


@pytest.fixture
def flags(payload) -> list[dict]:
    return consensus_flags(payload, PARAMS)


@pytest.fixture
def cases(payload, flags) -> list[AdversaryCase]:
    return build_adversary_cases(payload, flags)


def _stage1(**overrides) -> dict:
    stage1 = {
        "independent_answer": 4451.56,
        "computation": "PA taxes each return; the dependent files their own.",
        "citations": [
            {
                "source": "72 P.S. 7302",
                "pinpoint": "(a)",
                "url": "https://www.legis.state.pa.us/72/7302",
                "published": "1971-03-04",
                "pre_freeze": True,
                "quote": "a tax is imposed on the taxable income",
            }
        ],
        "law_supports": "consensus",
        "definition_reading": "Household state income tax across all returns.",
        "ambiguity": "",
        "confidence": "high",
    }
    return stage1 | overrides


def _verdict(**overrides) -> dict:
    verdict = {
        "verdict": "definition_mismatch",
        "summary": "The engine taxes the parents' return only.",
        "independent_answer": 4451.56,
        "reference_value": 3070.06,
        "consensus_value": 4452.0,
        "engine_step_at_issue": "pa_income_tax sums only the head's tax unit",
        "stage1_error": "",
        "citations": _stage1()["citations"],
        "suggested_adjudication": "definition_exclusion",
        "confidence": "high",
    }
    return verdict | overrides


def _write(path: Path, document: dict) -> str:
    text = canonical_json(document)
    path.write_text(text)
    return sha256_text(text)


def _sidecar(case_dir: Path, output: str, meta: str, **fields) -> None:
    digest = hashlib.sha256((case_dir / output).read_bytes()).hexdigest()
    (case_dir / meta).write_text(json.dumps({"output_sha256": digest, **fields}))


def _judged(adversary_dir: Path, case_id: str, *, stage1=None, verdict=None):
    """Write a stage 1, its stage-2 prompt and a verdict, as a runner would."""
    case_dir = adversary_dir / "cases" / case_id
    _write(case_dir / "stage1.json", stage1 or _stage1())
    _sidecar(
        case_dir,
        "stage1.json",
        "stage1.meta.json",
        judge_runner="scripts/run_reference_adversary_claude.sh",
    )
    prompt = write_stage2_prompt(adversary_dir, case_id)
    _write(case_dir / "verdict.json", verdict or _verdict())
    _sidecar(
        case_dir,
        "verdict.json",
        "verdict.meta.json",
        judge_runner="scripts/run_reference_adversary_claude.sh",
        judge_model_reported=["claude-opus-5-5"],
        prompt_sha256=hashlib.sha256(prompt.read_bytes()).hexdigest(),
        stage1_sha256=hashlib.sha256(
            (case_dir / "stage1.json").read_bytes()
        ).hexdigest(),
    )
    return case_dir


# --- Cases -----------------------------------------------------------------------


def test_case_id_matches_the_diagnosis_audit():
    for args in [("us", "scenario_001", TAX), ("us", "s 1/x", "a:b")]:
        assert _case_id(*args) == audit_case_id(*args)


def test_cases_carry_the_prompt_definition_reference_and_cluster_members(
    payload, flags, cases
):
    assert [(f["scenario_id"], f["variable"]) for f in flags] == [
        ("scenario_001", TAX),
        ("scenario_002", MEDICAID),
    ]
    tax, medicaid = cases
    scenario = payload["scenarios"]["scenario_001"]
    assert tax.household_prompt == scenario["prompt"]["tool"]
    assert tax.reference_value == 3070.061279296875
    assert tax.definition == get_variable_description(TAX)
    assert f"- {TAX}: {tax.definition}" in tax.household_prompt
    assert tax.models_answered == 5 and tax.models_exact == 1
    assert tax.state == "PA" and tax.metric_type == "amount" and tax.spec_id == TAX
    (cluster,) = tax.consensus
    members = {m["model"]: m for m in cluster["members"]}
    # Nearest-dollar rounding merges 4451.56, 4451.57 and 4452; the raw
    # prediction is kept per member, and the parse failure joins no cluster.
    assert set(members) == {"top-a", "top-b", "top-c", "mid-a"}
    assert members["mid-a"]["prediction"] == 4451.57
    assert "taxed the whole household" in members["top-a"]["explanation"]
    assert cluster["n_top"] == 3 and cluster["answer"] == 4452.0

    assert medicaid.spec_id == "person_medicaid_eligible"
    assert medicaid.metric_type == "binary"
    assert medicaid.definition.startswith("whether Head is eligible for Medicaid")
    assert f"- {MEDICAID}: {medicaid.definition}" in medicaid.household_prompt


def test_cases_read_no_score_or_annotation_field(payload, flags, cases):
    """Poisoning every score and diagnosis field changes no case and no prompt,
    and building cases leaves the payload untouched."""
    poisoned = copy.deepcopy(payload)
    score_fields = [
        "score",
        "boundedScore",
        "thresholdScore",
        "exact",
        "within1pct",
        "within5pct",
        "within10pct",
        "error",
        "annotation",
        "failureSource",
        "failureSubtype",
        "caseAnnotation",
        "caseFailureSources",
        "caseFailureSubtypes",
    ]
    for outputs in poisoned["scenarioPredictions"].values():
        for cell in outputs.values():
            for entry in cell.values():
                for name in score_fields:
                    entry[name] = f"POISON-{name}"
    before = copy.deepcopy(poisoned)
    rebuilt = build_adversary_cases(poisoned, flags)
    assert poisoned == before
    assert rebuilt == cases
    for case in rebuilt:
        for text in (
            render_stage1_prompt(case),
            canonical_json(case.to_manifest_row()),
        ):
            assert "POISON" not in text
            assert "DIAGNOSIS" not in text


def test_derivations_prefer_the_frozen_csv_then_the_payload(payload, flags):
    frozen = {("scenario_001", TAX): "FROZEN-CSV-DERIVATION"}
    tax, medicaid = build_adversary_cases(payload, flags, derivations=frozen)
    assert tax.derivation == "FROZEN-CSV-DERIVATION"
    assert medicaid.derivation == PAYLOAD_DERIVATION
    assert build_adversary_cases(payload, flags)[0].derivation == PAYLOAD_DERIVATION


def test_load_derivations_reads_the_frozen_explanations(tmp_path: Path):
    pd.DataFrame(
        [
            ["us", "scenario_001", TAX, "3070.06", "4", "Taxed the parents.", ""],
            ["us", "scenario_002", MEDICAID, "0.0", "1", "", "trace failed"],
            ["uk", "scenario_001", TAX, "1.0", "1", "A UK narrative.", ""],
        ],
        columns=[
            "country",
            "scenario_id",
            "variable",
            "reference_value",
            "trace_lines",
            "explanation",
            "error",
        ],
    ).to_csv(tmp_path / "us_case_reference_explanations.csv", index=False)
    assert load_derivations(tmp_path) == {("scenario_001", TAX): "Taxed the parents."}
    with pytest.raises(FileNotFoundError):
        load_derivations(tmp_path / "missing")


def test_explanations_are_cut_to_the_limit(payload, flags):
    long = "x" * 50
    payload["scenarioPredictions"]["scenario_001"][TAX]["top-a"]["explanation"] = long
    tax = build_adversary_cases(payload, flags, max_explanation_chars=10)[0]
    member = next(m for m in tax.consensus[0]["members"] if m["model"] == "top-a")
    assert member["explanation"] == "x" * 10 + " [... 40 more characters cut]"


def test_flags_that_do_not_match_the_payload_are_refused(payload, flags):
    wrong_reference = copy.deepcopy(flags)
    wrong_reference[0]["reference"] = 3070.0
    with pytest.raises(ValueError, match="another payload"):
        build_adversary_cases(payload, wrong_reference)
    wrong_prediction = copy.deepcopy(flags)
    wrong_prediction[0]["clusters"][0]["predictions"]["top-a"] = 1.0
    with pytest.raises(ValueError, match="another payload"):
        build_adversary_cases(payload, wrong_prediction)
    missing = copy.deepcopy(flags)
    missing[0]["scenario_id"] = "scenario_999"
    with pytest.raises(ValueError, match="scenario missing"):
        build_adversary_cases(payload, missing)
    with pytest.raises(ValueError, match="more than once"):
        build_adversary_cases(payload, flags + flags[:1])


# --- Prompts -----------------------------------------------------------------------


def test_stage1_prompt_states_the_task_and_carries_the_case(cases):
    tax = cases[0]
    prompt = render_stage1_prompt(tax)
    assert "stage 1 of 2" in prompt
    assert tax.household_prompt in prompt
    assert tax.definition in prompt
    assert "$3,070.06 (engine output 3,070.061279296875)" in prompt
    assert "5 gave a usable answer; 1 matched the reference" in prompt
    for member in tax.consensus[0]["members"]:
        assert member["model"] in prompt
        assert member["explanation"] in prompt
    assert "4,451.57" in prompt
    assert REFERENCE_FREEZE in prompt
    for domain in BLOCKED_DOMAINS:
        assert domain in prompt
    for rule in ("unlisted numeric input as 0", "take-up", "literally", "pre_freeze"):
        assert rule in prompt
    assert "ENGINE DERIVATION" not in prompt
    assert PAYLOAD_DERIVATION not in prompt


@settings(max_examples=150, deadline=None)
@given(derivation=st.text(min_size=8))
def test_stage1_prompt_never_contains_the_derivation(derivation):
    case = build_adversary_cases(
        _payload(), consensus_flags(_payload(), PARAMS), derivations=None
    )[0]
    blind = AdversaryCase(**{**case.__dict__, "derivation": ""})
    seeded = AdversaryCase(**{**case.__dict__, "derivation": derivation})
    # Stage 1 is a function of the case without its derivation.
    assert render_stage1_prompt(seeded) == render_stage1_prompt(blind)
    if derivation not in render_stage1_prompt(blind):
        assert derivation not in render_stage1_prompt(seeded)


def test_stage2_prompt_embeds_stage1_verbatim_with_its_sha_and_the_derivation(cases):
    tax = AdversaryCase(**{**cases[0].__dict__, "derivation": "ENGINE-STEPS"})
    stage1 = _stage1()
    digest = sha256_text(canonical_json(stage1))
    prompt = render_stage2_prompt(tax, stage1, digest)
    assert "stage 2 of 2" in prompt
    assert canonical_json(stage1) in prompt
    assert f"sha256 {digest}" in prompt
    assert "ENGINE-STEPS" in prompt
    assert "stage1_error" in prompt and "frozen" in prompt
    assert tax.household_prompt in prompt
    # The derivation follows stage 1, never precedes it.
    assert prompt.index(canonical_json(stage1)) < prompt.index("ENGINE-STEPS")
    no_derivation = AdversaryCase(**{**tax.__dict__, "derivation": ""})
    assert "no derivation was recorded" in render_stage2_prompt(
        no_derivation, stage1, digest
    )


# --- Schemas -----------------------------------------------------------------------


def _strict(schema: dict, where: str = "<root>") -> list[str]:
    problems = []
    if schema.get("type") == "object":
        if schema.get("additionalProperties") is not False:
            problems.append(f"{where}: additionalProperties is not false")
        if sorted(schema.get("required", [])) != sorted(schema["properties"]):
            problems.append(f"{where}: not every property is required")
        for name, sub in schema["properties"].items():
            problems += _strict(sub, f"{where}/{name}")
    if schema.get("type") == "array":
        problems += _strict(schema["items"], f"{where}[]")
    return problems


def test_schemas_are_strict_for_structured_output():
    """Every object closes its properties and requires all of them, which
    OpenAI strict structured outputs (codex --output-schema) require."""
    assert _strict(STAGE1_SCHEMA) == []
    assert _strict(VERDICT_SCHEMA) == []
    assert VERDICT_SCHEMA["properties"]["verdict"]["enum"] == list(VERDICTS)


def test_valid_outputs_pass_and_nulls_are_allowed():
    assert output_errors(STAGE1_SCHEMA, _stage1()) == []
    assert output_errors(VERDICT_SCHEMA, _verdict()) == []
    nulls = _stage1(independent_answer=None)
    nulls["citations"][0]["pre_freeze"] = None
    assert output_errors(STAGE1_SCHEMA, nulls) == []
    assert (
        output_errors(
            VERDICT_SCHEMA, _verdict(independent_answer=None, consensus_value=None)
        )
        == []
    )


@pytest.mark.parametrize(
    "schema, document, fragment",
    [
        (
            STAGE1_SCHEMA,
            {k: v for k, v in _stage1().items() if k != "citations"},
            "'citations' is a required property",
        ),
        (STAGE1_SCHEMA, _stage1(citations=[]), "should be non-empty"),
        (STAGE1_SCHEMA, _stage1(law_supports="engine"), "law_supports"),
        (STAGE1_SCHEMA, _stage1(confidence="certain"), "confidence"),
        (STAGE1_SCHEMA, _stage1(extra="x"), "Additional properties"),
        (
            STAGE1_SCHEMA,
            _stage1(citations=[{**_stage1()["citations"][0], "note": "x"}]),
            "citations/0",
        ),
        (
            STAGE1_SCHEMA,
            _stage1(citations=[{**_stage1()["citations"][0], "pre_freeze": "yes"}]),
            "pre_freeze",
        ),
        (VERDICT_SCHEMA, _verdict(verdict="reference_suspect"), "verdict"),
        (VERDICT_SCHEMA, _verdict(suggested_adjudication="exclude"), "suggested"),
        (VERDICT_SCHEMA, _verdict(reference_value=None), "reference_value"),
        (VERDICT_SCHEMA, _verdict(extra=1), "Additional properties"),
        (
            VERDICT_SCHEMA,
            {k: v for k, v in _verdict().items() if k != "stage1_error"},
            "'stage1_error' is a required property",
        ),
    ],
)
def test_invalid_outputs_are_rejected(schema, document, fragment):
    errors = output_errors(schema, document)
    assert errors and any(fragment in error for error in errors), errors


@pytest.mark.parametrize(
    "url, blocked",
    [
        ("https://policyengine.org/us/research", True),
        ("https://www.policyengine.org", True),
        ("https://docs.policyengine.org/x", True),
        ("https://github.com/PolicyEngine/policyengine-us/issues/8411", True),
        ("https://raw.githubusercontent.com/x/y/main/z.yaml", True),
        ("https://policybench.org/paper", True),
        ("https://pypi.org/project/policyengine-us/", True),
        ("revenue.louisiana.gov/tax-forms", False),
        ("https://www.irs.gov/pub/irs-drop/rp-25-32.pdf", False),
        ("https://notgithub.com/x", False),
        ("", False),
    ],
)
def test_blocked_url(url, blocked):
    assert blocked_url(url) is blocked


def test_citing_a_blocked_source_invalidates_an_output():
    for citation in (
        {"url": "https://github.com/PolicyEngine/policyengine-us"},
        {"source": "PolicyEngine US parameters", "url": "https://example.gov"},
    ):
        stage1 = _stage1(citations=[{**_stage1()["citations"][0], **citation}])
        assert any("blocked source" in e for e in output_errors(STAGE1_SCHEMA, stage1))


# --- Preparation and resumability ------------------------------------------------


def test_prepare_keeps_the_derivation_out_of_stage1_files(tmp_path: Path, cases):
    tax = AdversaryCase(**{**cases[0].__dict__, "derivation": "SECRET-DERIVATION"})
    adversary = tmp_path / "adv"
    prepare_adversary(adversary, [tax, cases[1]])
    assert json.loads((adversary / "schema_stage1.json").read_text()) == STAGE1_SCHEMA
    assert json.loads((adversary / "schema_verdict.json").read_text()) == VERDICT_SCHEMA
    derivation = adversary / "derivations" / f"{tax.case_id}.md"
    assert derivation.read_text() == "SECRET-DERIVATION"
    case_dir = adversary / "cases" / tax.case_id
    assert (case_dir / "stage1_prompt.md").read_text() == render_stage1_prompt(tax)
    for path in [adversary / "cases.jsonl", *(adversary / "cases").rglob("*")]:
        if path.is_file():
            assert "SECRET-DERIVATION" not in path.read_text(), path
    row = json.loads((adversary / "cases.jsonl").read_text().splitlines()[0])
    assert "derivation" not in row
    assert row["derivation_sha256"] == sha256_text("SECRET-DERIVATION")
    assert load_case(adversary, tax.case_id) == tax


def _outputs(case_dir: Path) -> set[str]:
    names = {
        "stage1.json",
        "stage1.meta.json",
        "stage2_prompt.md",
        "verdict.json",
        "verdict.meta.json",
    }
    return {name for name in names if (case_dir / name).exists()}


ALL_OUTPUTS = {
    "stage1.json",
    "stage1.meta.json",
    "stage2_prompt.md",
    "verdict.json",
    "verdict.meta.json",
}


def test_reprepare_unchanged_keeps_every_output(tmp_path: Path, cases):
    adversary = tmp_path / "adv"
    prepare_adversary(adversary, cases)
    case_dir = _judged(adversary, cases[0].case_id)
    assert _outputs(case_dir) == ALL_OUTPUTS
    prepare_adversary(adversary, cases)
    assert _outputs(case_dir) == ALL_OUTPUTS


def test_a_changed_stage1_prompt_drops_stage1_and_everything_after(
    tmp_path: Path, cases
):
    adversary = tmp_path / "adv"
    prepare_adversary(adversary, cases)
    case_dir = _judged(adversary, cases[0].case_id)
    changed = AdversaryCase(
        **{**cases[0].__dict__, "household_prompt": cases[0].household_prompt + "!"}
    )
    prepare_adversary(adversary, [changed, cases[1]])
    assert _outputs(case_dir) == set()


def test_a_changed_derivation_drops_only_stage2(tmp_path: Path, cases):
    adversary = tmp_path / "adv"
    prepare_adversary(adversary, cases)
    case_dir = _judged(adversary, cases[0].case_id)
    changed = AdversaryCase(**{**cases[0].__dict__, "derivation": "a new trace"})
    prepare_adversary(adversary, [changed, cases[1]])
    assert _outputs(case_dir) == {"stage1.json", "stage1.meta.json"}


def test_prepare_prunes_cases_no_longer_flagged(tmp_path: Path, cases):
    adversary = tmp_path / "adv"
    prepare_adversary(adversary, cases)
    prepare_adversary(adversary, cases[:1])
    assert sorted(p.name for p in (adversary / "cases").iterdir()) == [cases[0].case_id]
    assert sorted(p.stem for p in (adversary / "derivations").iterdir()) == [
        cases[0].case_id
    ]
    with pytest.raises(ValueError, match="duplicate"):
        prepare_adversary(adversary, [cases[0], cases[0]])


def test_stage2_prompt_needs_a_valid_canonical_stage1(tmp_path: Path, cases):
    adversary = tmp_path / "adv"
    prepare_adversary(adversary, cases)
    case_id = cases[0].case_id
    case_dir = adversary / "cases" / case_id
    with pytest.raises(ValueError, match="no valid stage 1"):
        write_stage2_prompt(adversary, case_id)
    _write(case_dir / "stage1.json", _stage1(citations=[]))
    with pytest.raises(ValueError, match="no valid stage 1"):
        write_stage2_prompt(adversary, case_id)
    (case_dir / "stage1.json").write_text(json.dumps(_stage1()))
    with pytest.raises(ValueError, match="canonical"):
        write_stage2_prompt(adversary, case_id)
    digest = _write(case_dir / "stage1.json", _stage1())
    prompt = write_stage2_prompt(adversary, case_id).read_text()
    assert digest in prompt and canonical_json(_stage1()) in prompt


def test_a_new_stage2_prompt_invalidates_the_verdict(tmp_path: Path, cases):
    adversary = tmp_path / "adv"
    prepare_adversary(adversary, cases)
    case_id = cases[0].case_id
    case_dir = _judged(adversary, case_id)
    write_stage2_prompt(adversary, case_id)  # unchanged: the verdict stays
    assert _outputs(case_dir) == ALL_OUTPUTS
    # The stage-2 prompt went missing but the bound sidecar records the
    # prompt the verdict answered: still the same prompt, so it stays.
    (case_dir / "stage2_prompt.md").unlink()
    write_stage2_prompt(adversary, case_id)
    assert (case_dir / "verdict.json").exists()
    # A re-judged stage 1 changes the stage-2 prompt: the verdict goes.
    _write(case_dir / "stage1.json", _stage1(independent_answer=4400.0))
    write_stage2_prompt(adversary, case_id)
    assert _outputs(case_dir) == {"stage1.json", "stage1.meta.json", "stage2_prompt.md"}


# --- Collection ------------------------------------------------------------------


def test_collect_reports_verdicts_with_provenance(tmp_path: Path, cases):
    adversary = tmp_path / "adv"
    prepare_adversary(adversary, cases)
    _judged(adversary, cases[0].case_id)
    out = collect_adversary(adversary)
    (row,) = out["verdicts"].to_dict("records")
    assert row["case_id"] == cases[0].case_id
    assert row["verdict"] == "definition_mismatch"
    assert row["reference_value"] == cases[0].reference_value
    assert row["stage1_law_supports"] == "consensus"
    assert row["judge_model"] == "claude-opus-5-5"
    assert json.loads(row["citations"]) == _verdict()["citations"]
    assert list(out["verdicts"].columns) == [
        "case_id",
        "country",
        "scenario_id",
        "variable",
        "verdict",
        "suggested_adjudication",
        "confidence",
        "reference_value",
        "consensus_value",
        "independent_answer",
        "stage1_law_supports",
        "engine_step_at_issue",
        "stage1_error",
        "summary",
        "citations",
        "judge_model",
    ]
    assert out["missing"]["case_id"].tolist() == [cases[1].case_id]
    assert out["missing"]["reason"].tolist() == ["no verdict"]
    assert out["inconsistent"].empty


@pytest.mark.parametrize(
    "damage, reason",
    [
        # A sidecar for another output binds nothing.
        (lambda meta: {**meta, "output_sha256": "0" * 64}, "no sidecar bound"),
        # A bound sidecar that names no stage 1 does not show the binding.
        (
            lambda meta: {k: v for k, v in meta.items() if k != "stage1_sha256"},
            "another stage 1",
        ),
        (lambda meta: None, "no sidecar bound"),
    ],
)
def test_collect_needs_a_sidecar_binding_the_verdict_to_its_stage1(
    tmp_path: Path, cases, damage, reason
):
    """A verdict is never taken as bound to the current stage 1 by default."""
    adversary = tmp_path / "adv"
    prepare_adversary(adversary, cases)
    case_dir = _judged(adversary, cases[0].case_id)
    meta = damage(json.loads((case_dir / "verdict.meta.json").read_text()))
    if meta is None:
        (case_dir / "verdict.meta.json").unlink()
    else:
        (case_dir / "verdict.meta.json").write_text(json.dumps(meta))
    out = collect_adversary(adversary)
    assert out["verdicts"].empty
    missing = out["missing"].set_index("case_id")["reason"]
    assert reason in missing[cases[0].case_id]


@pytest.mark.parametrize(
    "damage, reason",
    [
        (lambda d: (d / "verdict.json").write_text("{"), "invalid verdict"),
        (
            lambda d: _write(d / "verdict.json", _verdict(verdict="maybe")),
            "invalid verdict",
        ),
        (lambda d: (d / "stage1.json").unlink(), "no valid stage 1"),
        (
            # Stage 1 re-judged after the verdict: the stage-2 prompt and the
            # verdict's sidecar name the old stage 1.
            lambda d: _write(d / "stage1.json", _stage1(confidence="low")),
            "another stage 1",
        ),
    ],
)
def test_collect_lists_cases_without_a_usable_verdict(
    tmp_path: Path, cases, damage, reason
):
    adversary = tmp_path / "adv"
    prepare_adversary(adversary, cases)
    damage(_judged(adversary, cases[0].case_id))
    out = collect_adversary(adversary)
    assert out["verdicts"].empty
    missing = out["missing"].set_index("case_id")["reason"]
    assert reason in missing[cases[0].case_id]


@pytest.mark.parametrize(
    "stage1, verdict, problem",
    [
        (
            _stage1(),
            _verdict(
                verdict="reference_holds",
                suggested_adjudication="engine_defect",
                engine_step_at_issue="",
                stage1_error="stage 1 missed the dependent rule",
            ),
            "reference_holds with suggested_adjudication engine_defect",
        ),
        (
            _stage1(),
            _verdict(suggested_adjudication="affirmed"),
            "definition_mismatch with suggested_adjudication affirmed",
        ),
        (
            _stage1(),
            _verdict(
                verdict="reference_holds",
                suggested_adjudication="affirmed",
                engine_step_at_issue="",
                independent_answer=4451.56,
            ),
            "verdict holds the reference without naming a stage-1 error",
        ),
        (
            _stage1(law_supports="reference", independent_answer=3070.06),
            _verdict(
                verdict="reference_wrong",
                suggested_adjudication="engine_defect",
                independent_answer=3070.06,
            ),
            "calls it wrong without naming a stage-1 error",
        ),
        (
            _stage1(),
            _verdict(independent_answer=3070.06),
            "departs from stage 1's",
        ),
        (
            _stage1(),
            _verdict(engine_step_at_issue=""),
            "definition_mismatch names no engine step at issue",
        ),
        (
            _stage1(),
            _verdict(
                verdict="reference_holds",
                suggested_adjudication="affirmed",
                stage1_error="stage 1 counted the child's return",
            ),
            "reference_holds names an engine step at issue",
        ),
        (_stage1(), _verdict(reference_value=12835.0), "is not the case's reference"),
        (_stage1(), _verdict(consensus_value=999.0), "matches no consensus cluster"),
    ],
)
def test_collect_flags_inconsistent_verdicts(
    tmp_path: Path, cases, stage1, verdict, problem
):
    adversary = tmp_path / "adv"
    prepare_adversary(adversary, cases)
    _judged(adversary, cases[0].case_id, stage1=stage1, verdict=verdict)
    out = collect_adversary(adversary)
    assert len(out["verdicts"]) == 1  # judged, but flagged
    problems = out["inconsistent"]["problem"].tolist()
    assert any(problem in p for p in problems), problems


def test_a_consistent_stage1_correction_is_not_flagged(tmp_path: Path, cases):
    adversary = tmp_path / "adv"
    prepare_adversary(adversary, cases)
    verdict = _verdict(
        verdict="reference_holds",
        suggested_adjudication="affirmed",
        engine_step_at_issue="",
        independent_answer=3070.06,
        stage1_error="Stage 1 taxed the dependent's own return, which the "
        "definition's single return excludes.",
    )
    _judged(adversary, cases[0].case_id, verdict=verdict)
    assert collect_adversary(adversary)["inconsistent"].empty


def test_verdict_suggestion_pairings_cover_every_verdict():
    assert set(VERDICT_SUGGESTIONS) == set(VERDICTS)
    for suggestions in VERDICT_SUGGESTIONS.values():
        assert "none" in suggestions


# --- Merging and the adjudication queue -----------------------------------------


def _frame(rows: list[dict]) -> pd.DataFrame:
    base = {
        "country": "us",
        "reference_value": 3070.06,
        "suggested_adjudication": "definition_exclusion",
        "confidence": "high",
        "consensus_value": 4452.0,
        "independent_answer": 4451.56,
        "stage1_law_supports": "consensus",
        "engine_step_at_issue": "only the head's tax unit",
        "stage1_error": "",
        "summary": "The engine taxes one return.",
        "citations": "[]",
        "judge_model": "claude-opus-5-5",
    }
    return pd.DataFrame(
        [
            base | {"case_id": f"us__{r['scenario_id']}__{r['variable']}"} | r
            for r in rows
        ]
    )


def test_merge_judges_marks_agreement():
    claude = _frame(
        [
            {"scenario_id": "s1", "variable": TAX, "verdict": "definition_mismatch"},
            {"scenario_id": "s2", "variable": TAX, "verdict": "reference_holds"},
            {"scenario_id": "s3", "variable": TAX, "verdict": "reference_wrong"},
        ]
    )
    codex = _frame(
        [
            {"scenario_id": "s1", "variable": TAX, "verdict": "definition_mismatch"},
            {"scenario_id": "s2", "variable": TAX, "verdict": "reference_wrong"},
        ]
    )
    merged = merge_judges({"claude": claude, "codex": codex}).set_index("scenario_id")
    assert merged.loc["s1", "agree"] and merged.loc["s1", "judges"] == 2
    assert not merged.loc["s2", "agree"]
    assert not merged.loc["s3", "agree"] and merged.loc["s3", "judges"] == 1
    assert pd.isna(merged.loc["s3", "codex_verdict"])
    assert json.loads(merged.loc["s2", "verdicts"]) == {
        "claude": "reference_holds",
        "codex": "reference_wrong",
    }
    queue = adjudication_queue(merged.reset_index())
    # Any judge's non-holding verdict queues the case.
    assert sorted(queue["scenario_id"]) == ["s1", "s2", "s3"]
    s2 = queue.set_index("scenario_id").loc["s2"]
    assert "claude: reference_holds" not in s2["reference_bug_hypothesis"]
    assert (
        "Reference adversary (codex): reference_wrong"
        in (s2["reference_bug_hypothesis"])
    )
    assert (
        "Reference adversary (claude): reference_holds"
        in (s2["reference_bug_hypothesis"])
    )


def test_queue_holds_every_non_holding_verdict_in_the_case_notes_schema():
    verdicts = _frame(
        [
            {"scenario_id": "s1", "variable": TAX, "verdict": "definition_mismatch"},
            {
                "scenario_id": "s2",
                "variable": TAX,
                "verdict": "reference_holds",
                "suggested_adjudication": "affirmed",
            },
            {
                "scenario_id": "s3",
                "variable": TAX,
                "verdict": "prompt_ambiguous",
                "suggested_adjudication": "unlisted_input",
                "engine_step_at_issue": "",
            },
        ]
    )
    queue = adjudication_queue(verdicts)
    assert list(queue.columns) == QUEUE_COLUMNS
    assert queue["scenario_id"].tolist() == ["s1", "s3"]
    assert queue["reference_suspect"].tolist() == [True, True]
    assert set(queue["reference_suspect_source"]) == {"reference_adversary"}
    s1 = queue.iloc[0]
    assert s1["reference_bug_hypothesis"] == (
        "Reference adversary (claude-opus-5-5): definition_mismatch. The engine "
        "taxes one return. Engine step at issue: only the head's tax unit"
    )
    assert json.loads(s1["adversary_verdicts"]) == {
        "claude-opus-5-5": "definition_mismatch"
    }
    assert queue["suggested_adjudication"].tolist() == [
        "definition_exclusion",
        "unlisted_input",
    ]
    assert adjudication_queue(verdicts.iloc[[1]]).empty


def test_queue_holds_an_inconsistent_hold_too():
    """A reference_holds verdict that collect flags as inconsistent (here,
    holding the reference without naming the error in stage 1's finding for
    the consensus) is queued with its problem, for one judge or merged."""
    holds = {
        "scenario_id": "s2",
        "variable": TAX,
        "verdict": "reference_holds",
        "suggested_adjudication": "affirmed",
        "engine_step_at_issue": "",
    }
    verdicts = _frame([holds])
    problem = "verdict holds the reference without naming a stage-1 error"
    inconsistent = pd.DataFrame(
        [
            {
                "case_id": f"us__s2__{TAX}",
                "scenario_id": "s2",
                "variable": TAX,
                "problem": problem,
            }
        ]
    )
    assert adjudication_queue(verdicts, inconsistent.iloc[0:0]).empty
    (row,) = adjudication_queue(verdicts, inconsistent).to_dict("records")
    assert row["scenario_id"] == "s2" and row["reference_suspect"] is True
    assert row["reference_bug_hypothesis"].endswith(
        f"Inconsistent verdict: {problem}"
    )
    merged = merge_judges({"claude": verdicts})
    (row,) = adjudication_queue(
        merged, inconsistent.assign(judge="claude")
    ).to_dict("records")
    assert row["reference_bug_hypothesis"].endswith(
        f"Inconsistent verdict: claude: {problem}"
    )


def _case_notes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["us", "s1", TAX, 30, "llm_error", "x", False, None, "note one"],
            ["us", "s2", TAX, 4, "llm_error", "x", True, "judge says y", "note two"],
            ["us", "s3", TAX, 12, "llm_error", "x", False, None, "note three"],
        ],
        columns=[
            "country",
            "scenario_id",
            "variable",
            "wrong_model_count",
            "case_failure_sources",
            "case_failure_subtypes",
            "reference_suspect",
            "reference_bug_hypothesis",
            "case_annotation",
        ],
    )


def _adjudication(scenario_id: str) -> dict:
    return {
        "country": "us",
        "scenario_id": scenario_id,
        "variable": TAX,
        "judge_model": "claude-opus-5-5",
        "judge_failure_source": "llm_error",
        "judge_failure_subtype": "household_unit_or_filing_status",
        "adjudicated_failure_source": "llm_error",
        "adjudicated_failure_subtype": "household_unit_or_filing_status",
        "adjudicated_on": "2026-10-05",
        "adjudicator": "developer",
        "reasoning": "The definition covers the parents' return only.",
        "reference_verdict": "affirmed",
        "reference_basis": "72 P.S. 7302 and the output definition",
    }


def test_queued_cases_block_the_freeze_until_adjudicated():
    verdicts = _frame(
        [
            {"scenario_id": "s1", "variable": TAX, "verdict": "definition_mismatch"},
            {
                "scenario_id": "s3",
                "variable": TAX,
                "verdict": "reference_holds",
                "suggested_adjudication": "affirmed",
            },
        ]
    )
    notes = apply_adversary_flags(_case_notes(), adjudication_queue(verdicts))
    flagged = notes.set_index("scenario_id")
    assert flagged.loc["s1", "reference_suspect"]
    assert flagged.loc["s1", "reference_suspect_source"] == "reference_adversary"
    assert flagged.loc["s1", "reference_bug_hypothesis"].startswith(
        "Reference adversary (claude-opus-5-5): definition_mismatch."
    )
    assert not flagged.loc["s3", "reference_suspect"]
    assert flagged.loc["s3", "reference_suspect_source"] == ""
    assert unresolved_suspect_cases(notes, []) == [
        ("us", "s1", TAX),
        ("us", "s2", TAX),
    ]
    adjudications = parse_adjudications(
        {"adjudications": [_adjudication("s1")]}, "test"
    )
    assert unresolved_suspect_cases(notes, adjudications) == [("us", "s2", TAX)]


def test_a_queue_case_missing_from_the_case_notes_is_refused():
    queue = adjudication_queue(
        _frame([{"scenario_id": "s9", "variable": TAX, "verdict": "reference_wrong"}])
    )
    with pytest.raises(ValueError, match="case notes lack"):
        apply_adversary_flags(_case_notes(), queue)


_KEYS = st.tuples(
    st.sampled_from(["s1", "s2", "s3", "s4"]), st.sampled_from([TAX, "snap"])
)


@st.composite
def _notes_and_queue(draw):
    keys = draw(st.lists(_KEYS, min_size=1, max_size=8))
    hypotheses = st.one_of(st.none(), st.just(""), st.text(max_size=12))
    notes = pd.DataFrame(
        {
            "country": ["us"] * len(keys),
            "scenario_id": [k[0] for k in keys],
            "variable": [k[1] for k in keys],
            "wrong_model_count": draw(
                st.lists(st.integers(0, 46), min_size=len(keys), max_size=len(keys))
            ),
            "case_failure_sources": draw(
                st.lists(st.text(max_size=6), min_size=len(keys), max_size=len(keys))
            ),
            "reference_suspect": draw(
                st.lists(st.booleans(), min_size=len(keys), max_size=len(keys))
            ),
            "reference_bug_hypothesis": draw(
                st.lists(hypotheses, min_size=len(keys), max_size=len(keys))
            ),
            "case_annotation": draw(
                st.lists(st.text(max_size=10), min_size=len(keys), max_size=len(keys))
            ),
        },
        index=draw(st.lists(st.integers(0, 3), min_size=len(keys), max_size=len(keys))),
    )
    queued = draw(st.lists(st.sampled_from(sorted(set(keys))), unique=True))
    queue = pd.DataFrame(
        [
            {
                "country": "us",
                "scenario_id": s,
                "variable": v,
                "reference_suspect": True,
                "reference_bug_hypothesis": draw(st.text(min_size=1, max_size=12)),
                "reference_suspect_source": "reference_adversary",
                "adversary_verdicts": "{}",
                "suggested_adjudication": "none",
            }
            for s, v in queued
        ],
        columns=QUEUE_COLUMNS,
    )
    return notes, queue


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(_notes_and_queue())
def test_apply_adversary_flags_changes_nothing_else(data):
    notes, queue = data
    before = notes.copy()
    after = apply_adversary_flags(notes, queue)
    pd.testing.assert_frame_equal(notes, before)  # the input is not mutated
    assert list(after.index) == list(before.index)
    targets = {"reference_suspect", "reference_bug_hypothesis"}
    for column in before.columns:
        if column not in targets:
            pd.testing.assert_series_equal(after[column], before[column])
    queued = set(zip(queue["scenario_id"], queue["variable"]))
    hit = [key in queued for key in zip(before["scenario_id"], before["variable"])]
    for position, is_hit in enumerate(hit):
        was = bool(before["reference_suspect"].iloc[position])
        now = bool(after["reference_suspect"].iloc[position])
        assert now >= was  # never clears a flag
        old = before["reference_bug_hypothesis"].iloc[position]
        new = after["reference_bug_hypothesis"].iloc[position]
        source = after["reference_suspect_source"].iloc[position]
        if is_hit:
            assert now and source == "reference_adversary"
            if isinstance(old, str) and old.strip():
                assert new.startswith(old.strip())
        else:
            assert now == was and source == ""
            assert (pd.isna(old) and pd.isna(new)) or old == new
    expected = sorted(
        {("us", s, v) for s, v in queued}
        | {
            ("us", s, v)
            for s, v, flag in zip(
                before["scenario_id"], before["variable"], before["reference_suspect"]
            )
            if flag
        }
    )
    assert sorted(set(unresolved_suspect_cases(after, []))) == expected
    # Idempotent.
    pd.testing.assert_frame_equal(apply_adversary_flags(after, queue), after)


# --- Judge activity audits and the login check -----------------------------------


def _events(*items: dict) -> str:
    lines = [{"type": "thread.started", "thread_id": "thread-1"}]
    for item in items:
        lines.append({"type": "item.started", "item": item})
        lines.append({"type": "item.completed", "item": item})
    return "\n".join(json.dumps(line) for line in lines)


def test_codex_audit_passes_law_research_and_ignores_the_judges_words():
    events = _events(
        {
            "id": "1",
            "type": "agent_message",
            "text": "The definition says under PolicyEngine rules; data.json",
        },
        {"id": "2", "type": "reasoning", "text": "not consulting policyengine.org"},
        {
            # The codex-cli 0.159.0 shape: the item's query summarizes the
            # action's queries.
            "id": "3",
            "type": "web_search",
            "query": "Pennsylvania 3.07% dependent return ...",
            "action": {
                "type": "search",
                "queries": ["Pennsylvania 3.07% dependent return", "72 P.S. 7302"],
            },
        },
        {
            "id": "3b",
            "type": "web_search",
            "query": "'3.07'",
            "action": {"type": "find_in_page", "pattern": "3.07"},
        },
        {
            "id": "4",
            "type": "web_search",
            "query": "",
            "action": {"type": "open_page", "url": "https://www.revenue.pa.gov/x"},
        },
        {
            "id": "5",
            "type": "command_execution",
            "command": "ls",
            "aggregated_output": "",
        },
    )
    problems, activity = codex_events_audit(events)
    assert problems == []
    assert activity == {
        "searches": [
            "Pennsylvania 3.07% dependent return",
            "72 P.S. 7302",
            "'3.07'",
        ],
        "fetches": ["https://www.revenue.pa.gov/x"],
        "commands": ["ls"],
        "thread_id": "thread-1",
    }


@pytest.mark.parametrize(
    "item, problem",
    [
        (
            {
                "id": "1",
                "type": "command_execution",
                "command": "cat /tmp/adv/derivations/us__s1__snap.md",
                "aggregated_output": "",
            },
            "derivations/",
        ),
        (
            {
                "id": "1",
                "type": "command_execution",
                "command": "grep -r deduction /Users",
                "aggregated_output": "annotations/x/us_case_reference_explanations",
            },
            "us_case_reference_explanations",
        ),
        (
            {
                "id": "1",
                "type": "web_search",
                "query": "",
                "action": {"type": "open_page", "url": "https://policyengine.org/us"},
            },
            "blocked URL",
        ),
        (
            {
                "id": "1",
                "type": "web_search",
                "query": "",
                "action": {
                    "type": "open_page",
                    "url": "https://github.com/PolicyEngine/x/issues/8411",
                },
            },
            "blocked URL",
        ),
        (
            {"id": "1", "type": "web_search", "query": "policyengine louisiana 2026"},
            "policyengine",
        ),
        ({"id": "1", "type": "mcp_tool_call", "tool": "read"}, "'mcp_tool_call'"),
        ({"id": "1", "type": "file_change", "changes": []}, "'file_change'"),
        ({"id": "1", "type": "collab_tool_call"}, "'collab_tool_call'"),
        (
            {
                "id": "1",
                "type": "web_search",
                "query": "Louisiana standard deduction 2026 ...",
                "action": {
                    "type": "search",
                    "queries": ["Louisiana standard deduction 2026", "PolicyEngine LA"],
                },
            },
            "a web search names 'policyengine'",
        ),
        (
            {
                "id": "1",
                "type": "web_search",
                "query": "'12,835' in https://github.com/PolicyEngine/x",
                "action": {
                    "type": "find_in_page",
                    "url": "https://raw.githubusercontent.com/x/y.yaml",
                    "pattern": "12,835",
                },
            },
            "blocked URL",
        ),
    ],
)
def test_codex_audit_catches_contamination(item, problem):
    problems, _ = codex_events_audit(_events(item))
    assert problems and any(problem in p for p in problems), problems


def test_codex_audit_greps_lines_that_are_not_events():
    problems, _ = codex_events_audit("warning: read /x/data.json\n")
    assert problems == ["line 1: non-event output names 'data.json'"]


def _transcript(
    prompt: str,
    *parts: dict,
    refused: tuple[str, ...] = (),
    results: dict | None = None,
) -> str:
    results = results or {}
    events = [{"type": "user", "message": {"role": "user", "content": prompt}}]
    for part in parts:
        events.append(
            {"type": "assistant", "message": {"role": "assistant", "content": [part]}}
        )
        events.append(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": part["id"],
                            "content": results.get(part["id"], "ok"),
                            "is_error": part["id"] in refused,
                        }
                    ],
                },
            }
        )
    return "\n".join(json.dumps(event) for event in events)


def _use(id_: str, name: str, **payload) -> dict:
    return {"type": "tool_use", "id": id_, "name": name, "input": payload}


def test_claude_audit_passes_web_research_and_returns_the_accepted_answer():
    transcript = _transcript(
        "the prompt\n",
        _use("1", "WebSearch", query="PA dependent return 3.07%"),
        _use("2", "WebFetch", url="https://www.revenue.pa.gov/x", prompt="rate"),
        _use("3", "StructuredOutput", bad=True),
        _use("4", "StructuredOutput", **_stage1()),
        refused=("3",),
    )
    problems, activity, accepted = claude_transcript_audit(transcript, "the prompt")
    assert problems == []
    assert activity == {
        "searches": ["PA dependent return 3.07%"],
        "fetches": ["https://www.revenue.pa.gov/x"],
        "denied_fetches": [],
    }
    assert accepted == [_stage1()]


def test_claude_audit_records_a_fetch_the_deny_rule_refused():
    """A blocked fetch whose result is an error returned nothing: recorded,
    not contamination. One that returned content is contamination."""
    fetch = _use("1", "WebFetch", url="https://policyengine.org/us", prompt="x")
    refused = _transcript("p", fetch, refused=("1",))
    problems, activity, _ = claude_transcript_audit(refused, "p")
    assert problems == []
    assert activity["denied_fetches"] == ["https://policyengine.org/us"]
    assert activity["fetches"] == []
    problems, _, _ = claude_transcript_audit(_transcript("p", fetch), "p")
    assert problems == ["the judge fetched a blocked URL: https://policyengine.org/us"]


@pytest.mark.parametrize(
    "part, prompt, problem",
    [
        (_use("1", "Read", file_path="/x"), "p", "not given: Read"),
        (_use("1", "Bash", command="cat /x"), "p", "not given: Bash"),
        (_use("1", "WebFetch", url="https://policybench.org"), "p", "blocked URL"),
        (_use("1", "WebSearch", query="PolicyEngine LA"), "p", "searched for"),
        (_use("1", "WebSearch", query="ok"), "another prompt", "user text messages"),
    ],
)
def test_claude_audit_catches_contamination(part, prompt, problem):
    problems, _, _ = claude_transcript_audit(_transcript("p", part), prompt)
    assert any(problem in p for p in problems), problems


SEARCH = "Colorado sales tax refund 2026"


@pytest.mark.parametrize(
    "content, exposed",
    [
        # Claude Code's WebSearch result: a JSON list of links, then a summary.
        (
            'Links: [{"title":"C.R.S. 39-22-2003","url":"https://colorado.public.'
            'law/statutes/crs_39-22-2003"},{"title":"Calculator","url":"https://'
            'www.policyengine.org/us/co-refund"}]\n\nThe refund needs a surplus.',
            "https://www.policyengine.org/us/co-refund",
        ),
        # A blocked domain whatever the repository.
        (
            [{"type": "text", "text": "See https://github.com/someone/rules/issues/1."}],
            "https://github.com/someone/rules/issues/1",
        ),
        # A URL naming the engine on another host.
        (
            "https://example.org/policyengine-estimates and more",
            "https://example.org/policyengine-estimates",
        ),
        # The summary names the engine with no URL.
        ("PolicyEngine puts the 2026 refund at $19.", "text names policyengine"),
    ],
)
def test_claude_audit_rejects_a_search_whose_result_reaches_a_blocked_source(
    content, exposed
):
    search = _use("1", "WebSearch", query=SEARCH)
    transcript = _transcript("p", search, results={"1": content})
    problems, activity, _ = claude_transcript_audit(transcript, "p")
    assert problems == [f"a search returned a blocked source: {SEARCH} -> {exposed}"]
    assert activity["searches"] == [SEARCH]


def test_claude_audit_passes_a_clean_search_result():
    content = (
        'Links: [{"title":"C.R.S. 39-22-2003","url":"https://colorado.public.law/'
        'statutes/crs_39-22-2003"}]\n\nThe refund needs excess state revenues.'
    )
    search = _use("1", "WebSearch", query=SEARCH, blocked_domains=["github.com"])
    transcript = _transcript("p", search, results={"1": content})
    assert claude_transcript_audit(transcript, "p")[0] == []


def test_blocked_search_result_lists_each_source_once_in_order():
    text = (
        "https://github.com/a/b, https://www.policyengine.org/x. "
        "https://github.com/a/b and PolicyBench too; https://irs.gov/p17"
    )
    assert blocked_search_result(text) == [
        "https://github.com/a/b",
        "https://www.policyengine.org/x",
        "text names policybench",
    ]
    assert blocked_search_result("") == []


def test_prompts_ask_for_blocked_domains_on_every_search(tmp_path: Path, cases):
    adversary = tmp_path / "adv"
    prepare_adversary(adversary, cases)
    case_dir = _judged(adversary, cases[0].case_id)
    for prompt in (
        render_stage1_prompt(cases[0]),
        (case_dir / "stage2_prompt.md").read_text(),
    ):
        assert "(blocked_domains), pass all of these domains on every search" in (
            " ".join(prompt.split())
        )
        for domain in BLOCKED_DOMAINS:
            assert domain in prompt


def test_check_login_mirrors_the_audit_runner_rule(tmp_path: Path):
    lane = json.dumps(
        {"loggedIn": True, "authMethod": "oauth_token", "apiProvider": "firstParty"}
    )
    common = {"config_dir": str(tmp_path), "desktop_opt_in": False}
    assert check_login(lane, "", token=True, declared="lane@x", **common) == {
        "method": "oauth_token",
        "account": None,
        "org": None,
    }
    with pytest.raises(ValueError, match="AUDIT_ACCOUNT"):
        check_login(lane, "", token=True, declared="", **common)
    api = json.dumps(
        {"loggedIn": True, "authMethod": "api_key", "apiProvider": "firstParty"}
    )
    with pytest.raises(ValueError, match="not a subscription"):
        check_login(api, "", token=False, declared="x", **common)
    desktop = json.dumps(
        {
            "loggedIn": True,
            "authMethod": "claude.ai",
            "apiProvider": "firstParty",
            "email": "max@example.org",
        }
    )
    with pytest.raises(ValueError, match="desktop login's account"):
        check_login(desktop, desktop, token=False, declared="", **common)
    # A token login reports no email, so the declared account is what can be
    # compared: a lane token for the desktop's own account is refused.
    with pytest.raises(ValueError, match="is the desktop login's account"):
        check_login(lane, desktop, token=True, declared=" Max@Example.org", **common)
    assert check_login(lane, desktop, token=True, declared="lane@x", **common)


# --- Command line ----------------------------------------------------------------


def test_main_validate_and_render_stage2(tmp_path: Path, cases, capsys):
    adversary = tmp_path / "adv"
    prepare_adversary(adversary, cases)
    case_id = cases[0].case_id
    case_dir = adversary / "cases" / case_id
    schema = str(adversary / "schema_stage1.json")
    assert main(["validate", "--schema", schema, "--file", str(case_dir / "x")]) == 1
    assert (
        main(["render-stage2", "--adversary-dir", str(adversary), "--case-id", case_id])
        == 1
    )
    _write(case_dir / "stage1.json", _stage1(citations=[]))
    assert (
        main(["validate", "--schema", schema, "--file", str(case_dir / "stage1.json")])
        == 1
    )
    _write(case_dir / "stage1.json", _stage1())
    assert (
        main(["validate", "--schema", schema, "--file", str(case_dir / "stage1.json")])
        == 0
    )
    assert (
        main(["render-stage2", "--adversary-dir", str(adversary), "--case-id", case_id])
        == 0
    )
    assert (case_dir / "stage2_prompt.md").is_file()


def _collect_cli(*argv: str) -> None:
    import sys
    from unittest import mock

    from policybench import cli

    with mock.patch.object(sys, "argv", ["policybench", "adversary-collect", *argv]):
        cli.main()


def test_collect_cli_refuses_a_repeated_judge_label(tmp_path: Path, cases):
    for judge in ("claude", "codex"):
        prepare_adversary(tmp_path / judge / "adv", cases)
    out = tmp_path / "out"
    with pytest.raises(SystemExit, match="adv given more than once"):
        _collect_cli(
            "--adversary-dir",
            str(tmp_path / "claude" / "adv"),
            "--adversary-dir",
            str(tmp_path / "codex" / "adv"),
            "--output-dir",
            str(out),
        )
    assert not out.exists()


def test_collect_cli_fails_on_missing_verdicts_unless_allowed(
    tmp_path: Path, cases
):
    adversary = tmp_path / "adv"
    prepare_adversary(adversary, cases)
    _judged(
        adversary,
        cases[0].case_id,
        verdict=_verdict(
            verdict="reference_holds",
            suggested_adjudication="affirmed",
            engine_step_at_issue="",
        ),
    )
    out = tmp_path / "out"
    args = ("--adversary-dir", f"claude={adversary}", "--output-dir", str(out))
    with pytest.raises(SystemExit, match="1 case\\(s\\) have no usable verdict"):
        _collect_cli(*args)
    # The tables are written either way, and the inconsistent hold is queued.
    queue = pd.read_csv(out / "adversary_adjudication_queue.csv")
    assert queue["scenario_id"].tolist() == [cases[0].scenario_id]
    assert queue["variable"].tolist() == [cases[0].variable]
    assert "Inconsistent verdict: claude: " in queue["reference_bug_hypothesis"][0]
    _collect_cli(*args, "--allow-missing")
    missing = pd.read_csv(out / "adversary_claude_missing.csv")
    assert missing["case_id"].tolist() == [cases[1].case_id]


# --- What the module never touches -----------------------------------------------


def test_module_names_no_score_field():
    """The module reads a cell's prediction, explanation, reference and
    referenceExplanation only: it names no score or diagnosis field."""
    constants = {
        node.value
        for node in ast.walk(ast.parse(MODULE.read_text()))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    forbidden = {
        "score",
        "boundedScore",
        "thresholdScore",
        "exact",
        "within1pct",
        "within5pct",
        "within10pct",
        "annotation",
        "caseAnnotation",
        "failureSource",
        "failureSubtype",
        "modelStats",
        "heatmap",
        "programStats",
        "globalWeights",
    }
    assert constants & forbidden == set()


def test_the_pipeline_writes_only_inside_the_adversary_dir(
    tmp_path: Path, payload, flags
):
    adversary = tmp_path / "work" / "adv"
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(payload))
    snapshot = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    cases = build_adversary_cases(json.loads(outside.read_text()), flags)
    prepare_adversary(adversary, cases)
    _judged(adversary, cases[0].case_id)
    collect_adversary(adversary)
    for path, data in snapshot.items():
        assert path.read_bytes() == data
    written = {p for p in tmp_path.rglob("*") if p.is_file()} - set(snapshot)
    assert all(adversary in p.parents for p in written)


# --- The frozen run ---------------------------------------------------------------


@pytest.mark.skipif(not FROZEN_PAYLOAD.exists(), reason="frozen payload absent")
def test_frozen_run_cases_are_blind_in_stage1():
    from policybench.consensus import consensus_report, load_us_payload

    payload = load_us_payload(FROZEN_PAYLOAD)
    report = consensus_report(payload)
    derivations = load_derivations(FROZEN_ANNOTATIONS)
    cases = build_adversary_cases(payload, report["flags"], derivations=derivations)
    assert len(cases) == report["flagged_cells"] == 61
    for case in cases:
        assert f"- {case.variable}: {case.definition}" in case.household_prompt
        assert case.derivation, case.case_id
        assert case.derivation not in render_stage1_prompt(case)
    tax = next(c for c in cases if (c.scenario_id, c.variable) == ("scenario_123", TAX))
    assert tax.derivation == derivations[("scenario_123", TAX)]
    assert round(tax.reference_value, 2) == 3070.06
    (cluster,) = tax.consensus
    assert cluster["answer"] == 4452.0 and cluster["n_models"] == 32
    # The frozen payload wraps the same derivation text for the fallback.
    with gzip.open(FROZEN_PAYLOAD) as handle:
        raw = json.load(handle)
    cell = raw["scenarioPredictions"]["scenario_123"][TAX]
    assert next(iter(cell.values()))["referenceExplanation"]
