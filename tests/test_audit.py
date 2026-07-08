"""Tests for the model-assisted failure audit (deterministic halves)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from policybench.annotation_taxonomy import (
    FAILURE_SOURCE_VALUES,
    FAILURE_SUBTYPE_VALUES,
)
from policybench.audit import (
    AUDIT_OUTPUT_SCHEMA,
    build_audit_cases,
    collect_audit,
    is_hedged,
    parse_verdict,
    prepare_audit,
    render_case_prompt,
)


@pytest.fixture
def country_dir(tmp_path: Path) -> Path:
    """A minimal US run with two wrong cases over three models."""
    d = tmp_path / "us"
    d.mkdir()
    pd.DataFrame(
        [
            {"scenario_id": "s0", "variable": "snap", "value": 0.0},
            {"scenario_id": "s1", "variable": "snap", "value": 300.0},
        ]
    ).to_csv(d / "reference_outputs.csv", index=False)
    # s0/snap: two models wrong; s1/snap: one model wrong, one right.
    pd.DataFrame(
        [
            {
                "model": "m1",
                "scenario_id": "s0",
                "variable": "snap",
                "prediction": 250.0,
                "explanation": "Estimated benefit from income.",
                "error": None,
            },
            {
                "model": "m2",
                "scenario_id": "s0",
                "variable": "snap",
                "prediction": 400.0,
                "explanation": "Used gross income test.",
                "error": None,
            },
            {
                "model": "m1",
                "scenario_id": "s1",
                "variable": "snap",
                "prediction": 300.0,
                "explanation": "Matched the allotment.",
                "error": None,
            },
            {
                "model": "m2",
                "scenario_id": "s1",
                "variable": "snap",
                "prediction": 0.0,
                "explanation": "Assumed ineligible.",
                "error": None,
            },
        ]
    ).to_csv(d / "predictions.csv", index=False)
    return d


def test_build_audit_cases_groups_wrong_by_case(country_dir: Path):
    cases = build_audit_cases(country_dir)
    by_key = {(c.scenario_id, c.variable): c for c in cases}
    # s0/snap has both models wrong; s1/snap only m2.
    assert set(by_key) == {("s0", "snap"), ("s1", "snap")}
    assert {m.model for m in by_key[("s0", "snap")].wrong_models} == {"m1", "m2"}
    assert {m.model for m in by_key[("s1", "snap")].wrong_models} == {"m2"}
    assert by_key[("s0", "snap")].reference_value == "$0.00"


def test_render_case_prompt_includes_reference_and_models(country_dir: Path):
    case = next(c for c in build_audit_cases(country_dir) if c.scenario_id == "s0")
    prompt = render_case_prompt(case)
    assert "POLICYENGINE REFERENCE VALUE: $0.00" in prompt
    assert "m1: answered $250.00" in prompt
    assert "Used gross income test." in prompt
    assert "reference_suspect" in prompt  # instructs the PE-bug judgment


def test_schema_enums_stay_in_sync_with_taxonomy():
    props = AUDIT_OUTPUT_SCHEMA["properties"]
    assert props["case_failure_source"]["enum"] == list(FAILURE_SOURCE_VALUES)
    assert props["case_failure_subtype"]["enum"] == list(FAILURE_SUBTYPE_VALUES)
    model_props = props["models"]["items"]["properties"]
    assert model_props["failure_source"]["enum"] == list(FAILURE_SOURCE_VALUES)


def test_parse_verdict_tolerates_prose_around_json(tmp_path: Path):
    f = tmp_path / "verdict.json"
    f.write_text(
        'Here is my verdict:\n{"case_failure_source": "llm_error", "models": []}\nDone.'
    )
    parsed = parse_verdict(f)
    assert parsed["case_failure_source"] == "llm_error"
    assert parse_verdict(tmp_path / "absent.json") is None


def test_prepare_audit_writes_layout(country_dir: Path, tmp_path: Path):
    audit_dir = tmp_path / "audit"
    cases = prepare_audit(country_dir, audit_dir)
    assert (audit_dir / "schema.json").exists()
    assert (audit_dir / "cases.jsonl").exists()
    for case in cases:
        assert (audit_dir / "cases" / case.case_id / "prompt.md").exists()
    manifest = (audit_dir / "cases.jsonl").read_text().splitlines()
    assert len(manifest) == len(cases)


def test_collect_audit_folds_verdicts_and_tracks_missing(
    country_dir: Path, tmp_path: Path
):
    audit_dir = tmp_path / "audit"
    cases = prepare_audit(country_dir, audit_dir)
    # Write a verdict for the s0 case only; leave s1 missing.
    s0 = next(c for c in cases if c.scenario_id == "s0")
    verdict = {
        "reference_suspect": False,
        "reference_bug_hypothesis": "",
        "case_failure_source": "llm_error",
        "case_failure_subtype": "categorical_eligibility",
        "rationale": "Both models misjudged the income test.",
        "models": [
            {
                "model": "m1",
                "failure_source": "llm_error",
                "failure_subtype": "thresholds_rates",
            },
            {
                "model": "m2",
                "failure_source": "llm_error",
                "failure_subtype": "categorical_eligibility",
            },
        ],
    }
    (audit_dir / "cases" / s0.case_id / "verdict.json").write_text(json.dumps(verdict))

    out = collect_audit(country_dir, audit_dir)
    assert set(out["missing"]["case_id"]) == {
        c.case_id for c in cases if c.scenario_id == "s1"
    }
    rows = out["row"]
    assert len(rows) == 2  # m1, m2 on the s0 case
    m1 = rows[rows["model"] == "m1"].iloc[0]
    assert m1["failure_subtype"] == "thresholds_rates"
    assert m1["annotation"] == "Both models misjudged the income test."
    assert bool(m1["reference_suspect"]) is False
    case_rows = out["case"]
    assert case_rows.iloc[0]["case_failure_source"] == "llm_error"


def test_collect_audit_rejects_invalid_failure_source(
    country_dir: Path, tmp_path: Path
):
    audit_dir = tmp_path / "audit"
    cases = prepare_audit(country_dir, audit_dir)
    s0 = next(c for c in cases if c.scenario_id == "s0")
    (audit_dir / "cases" / s0.case_id / "verdict.json").write_text(
        json.dumps(
            {
                "case_failure_source": "not_a_real_source",
                "case_failure_subtype": "other",
                "rationale": "x",
                "models": [],
            }
        )
    )
    with pytest.raises(ValueError):
        collect_audit(country_dir, audit_dir)


def test_reference_derivation_reaches_the_prompt(tmp_path: Path):
    """The PE-derivation narrative must appear in the prompt when present.

    Regression for the column-name bug: load_case_reference_explanations
    renames ``explanation`` -> ``reference_explanation``; reading the wrong
    column silently dropped this core classifier input.
    """
    d = tmp_path / "us"
    d.mkdir()
    pd.DataFrame([{"scenario_id": "s0", "variable": "snap", "value": 0.0}]).to_csv(
        d / "reference_outputs.csv", index=False
    )
    pd.DataFrame(
        [
            {
                "model": "m1",
                "scenario_id": "s0",
                "variable": "snap",
                "prediction": 250.0,
                "explanation": "x",
                "error": None,
            }
        ]
    ).to_csv(d / "predictions.csv", index=False)
    annotations = tmp_path / "annotations"
    annotations.mkdir()
    pd.DataFrame(
        [
            {
                "scenario_id": "s0",
                "variable": "snap",
                "explanation": "PolicyEngine found the household over the income test.",
            }
        ]
    ).to_csv(annotations / "us_case_reference_explanations.csv", index=False)

    case = build_audit_cases(d)[0]
    assert "over the income test" in case.reference_derivation
    assert "HOW POLICYENGINE DERIVED THE REFERENCE" in render_case_prompt(case)


def test_binary_variable_renders_yes_no(tmp_path: Path):
    d = tmp_path / "us"
    d.mkdir()
    pd.DataFrame(
        [{"scenario_id": "s0", "variable": "person_medicaid_eligible", "value": 1.0}]
    ).to_csv(d / "reference_outputs.csv", index=False)
    pd.DataFrame(
        [
            {
                "model": "m1",
                "scenario_id": "s0",
                "variable": "person_medicaid_eligible",
                "prediction": 0.0,
                "explanation": "Assumed over the limit.",
                "error": None,
            }
        ]
    ).to_csv(d / "predictions.csv", index=False)
    case = build_audit_cases(d)[0]
    assert case.reference_value == "Yes"
    assert case.wrong_models[0].prediction == "No"


def test_missing_prediction_renders_as_missing(tmp_path: Path):
    """A model with no prediction for a cell (cross-join NaN) reads 'missing'."""
    d = tmp_path / "us"
    d.mkdir()
    pd.DataFrame([{"scenario_id": "s0", "variable": "snap", "value": 0.0}]).to_csv(
        d / "reference_outputs.csv", index=False
    )
    pd.DataFrame(
        [
            {
                "model": "answered",
                "scenario_id": "s0",
                "variable": "snap",
                "prediction": 250.0,
                "explanation": "e",
                "error": None,
            },
            # 'silent' answers a different cell, so it is missing on s0/snap.
            {
                "model": "silent",
                "scenario_id": "s9",
                "variable": "snap",
                "prediction": 5.0,
                "explanation": "e",
                "error": None,
            },
        ]
    ).to_csv(d / "predictions.csv", index=False)
    pd.DataFrame(
        [
            {"scenario_id": "s0", "variable": "snap", "value": 0.0},
            {"scenario_id": "s9", "variable": "snap", "value": 5.0},
        ]
    ).to_csv(d / "reference_outputs.csv", index=False)
    case = next(c for c in build_audit_cases(d) if c.scenario_id == "s0")
    silent = next(m for m in case.wrong_models if m.model == "silent")
    assert silent.prediction == "missing"
    assert "answered missing" in render_case_prompt(case)


def test_collect_defaults_missing_model_to_case_source(
    country_dir: Path, tmp_path: Path
):
    """When the verdict omits a wrong model, its row inherits the case source."""
    audit_dir = tmp_path / "audit"
    cases = prepare_audit(country_dir, audit_dir)
    s0 = next(c for c in cases if c.scenario_id == "s0")
    (audit_dir / "cases" / s0.case_id / "verdict.json").write_text(
        json.dumps(
            {
                "reference_suspect": False,
                "reference_bug_hypothesis": "",
                "case_failure_source": "prompt_ambiguity",
                "case_failure_subtype": "other",
                "rationale": "ambiguous",
                # Only m1 is classified; m2 is omitted by the model.
                "models": [
                    {
                        "model": "m1",
                        "failure_source": "llm_error",
                        "failure_subtype": "thresholds_rates",
                    }
                ],
            }
        )
    )
    rows = collect_audit(country_dir, audit_dir)["row"]
    m2 = rows[rows["model"] == "m2"].iloc[0]
    assert m2["failure_source"] == "prompt_ambiguity"  # inherited from case
    assert m2["failure_subtype"] == "other"


def test_duplicate_model_rows_are_deduped(tmp_path: Path):
    """Repeated runs can yield two prediction rows for one cell; keep one."""
    d = tmp_path / "us"
    d.mkdir()
    pd.DataFrame([{"scenario_id": "s0", "variable": "snap", "value": 0.0}]).to_csv(
        d / "reference_outputs.csv", index=False
    )
    pd.DataFrame(
        [
            {
                "model": "m1",
                "scenario_id": "s0",
                "variable": "snap",
                "prediction": 250.0,
                "explanation": "run a",
                "error": None,
            },
            {
                "model": "m1",
                "scenario_id": "s0",
                "variable": "snap",
                "prediction": 260.0,
                "explanation": "run b",
                "error": None,
            },
        ]
    ).to_csv(d / "predictions.csv", index=False)
    case = build_audit_cases(d)[0]
    assert [m.model for m in case.wrong_models] == ["m1"]


def test_collect_empty_wrong_set_keeps_header(tmp_path: Path):
    """No wrong cases still yields headered (empty) annotation frames."""
    d = tmp_path / "us"
    d.mkdir()
    pd.DataFrame([{"scenario_id": "s0", "variable": "snap", "value": 100.0}]).to_csv(
        d / "reference_outputs.csv", index=False
    )
    pd.DataFrame(
        [
            {
                "model": "m1",
                "scenario_id": "s0",
                "variable": "snap",
                "prediction": 100.0,
                "explanation": "correct",
                "error": None,
            }
        ]
    ).to_csv(d / "predictions.csv", index=False)
    audit_dir = tmp_path / "audit"
    prepare_audit(d, audit_dir)
    out = collect_audit(d, audit_dir)
    assert list(out["row"].columns) and "failure_source" in out["row"].columns
    assert list(out["case"].columns) and "case_failure_source" in out["case"].columns


def test_parse_failure_only_case_skips_codex_and_is_deterministic(tmp_path: Path):
    """A case whose only wrong model returned no value needs no classifier."""
    d = tmp_path / "us"
    d.mkdir()
    pd.DataFrame(
        [
            {"scenario_id": "s0", "variable": "snap", "value": 0.0},
            {"scenario_id": "s9", "variable": "snap", "value": 0.0},
        ]
    ).to_csv(d / "reference_outputs.csv", index=False)
    pd.DataFrame(
        [
            # m1 is correct on s0; m2 only answers s9, so it is missing on s0/snap.
            {
                "model": "m1",
                "scenario_id": "s0",
                "variable": "snap",
                "prediction": 0.0,
                "explanation": "ineligible",
                "error": None,
            },
            {
                "model": "m2",
                "scenario_id": "s9",
                "variable": "snap",
                "prediction": 0.0,
                "explanation": "ineligible",
                "error": None,
            },
        ]
    ).to_csv(d / "predictions.csv", index=False)
    audit_dir = tmp_path / "audit"
    cases = prepare_audit(d, audit_dir)
    s0 = next(c for c in cases if c.scenario_id == "s0")
    # No prompt is written for a parse-failure-only case (no Codex call).
    assert not (audit_dir / "cases" / s0.case_id / "prompt.md").exists()

    out = collect_audit(d, audit_dir)
    assert out["missing"].empty  # not "missing" — classified deterministically
    s0_rows = out["row"][out["row"]["scenario_id"] == "s0"]
    assert list(s0_rows["model"]) == ["m2"]
    assert s0_rows.iloc[0]["failure_source"] == "parse_contract_failure"
    assert s0_rows.iloc[0]["failure_subtype"] == "missing_output"


def test_reprepare_drops_stale_verdict_when_case_changed(tmp_path: Path):
    """A verdict is invalidated when the case content (prompt) changes."""
    d = tmp_path / "us"
    d.mkdir()
    pd.DataFrame([{"scenario_id": "s0", "variable": "snap", "value": 0.0}]).to_csv(
        d / "reference_outputs.csv", index=False
    )
    pd.DataFrame(
        [
            {
                "model": "m1",
                "scenario_id": "s0",
                "variable": "snap",
                "prediction": 250.0,
                "explanation": "first answer",
                "error": None,
            }
        ]
    ).to_csv(d / "predictions.csv", index=False)
    audit_dir = tmp_path / "audit"
    cases = prepare_audit(d, audit_dir)
    s0 = cases[0]
    verdict_path = audit_dir / "cases" / s0.case_id / "verdict.json"
    verdict_path.write_text('{"case_failure_source": "llm_error", "models": []}')

    # Re-run m1 with a different wrong answer -> the case prompt changes.
    pd.DataFrame(
        [
            {
                "model": "m1",
                "scenario_id": "s0",
                "variable": "snap",
                "prediction": 999.0,
                "explanation": "different answer",
                "error": None,
            }
        ]
    ).to_csv(d / "predictions.csv", index=False)
    prepare_audit(d, audit_dir)
    assert not verdict_path.exists()  # stale verdict dropped

    # An unchanged case keeps its verdict.
    verdict_path.write_text('{"case_failure_source": "llm_error", "models": []}')
    prepare_audit(d, audit_dir)
    assert verdict_path.exists()


def test_collect_audit_coerces_parse_source_for_parsed_predictions(tmp_path: Path):
    """Classifier parse labels should not survive on parsed, substantive misses."""
    d = tmp_path / "us"
    d.mkdir()
    pd.DataFrame([{"scenario_id": "s0", "variable": "snap", "value": 0.0}]).to_csv(
        d / "reference_outputs.csv", index=False
    )
    pd.DataFrame(
        [
            {
                "model": "m1",
                "scenario_id": "s0",
                "variable": "snap",
                "prediction": 250.0,
                "explanation": "Too high. value = 250",
                "error": None,
            }
        ]
    ).to_csv(d / "predictions.csv", index=False)

    audit_dir = tmp_path / "audit"
    cases = prepare_audit(d, audit_dir)
    case = cases[0]
    verdict_path = audit_dir / "cases" / case.case_id / "verdict.json"
    verdict_path.write_text(
        json.dumps(
            {
                "reference_suspect": False,
                "reference_bug_hypothesis": "",
                "case_failure_source": "llm_error",
                "case_failure_subtype": "other",
                "rationale": "The parsed value is wrong.",
                "models": [
                    {
                        "model": "m1",
                        "failure_source": "parse_contract_failure",
                        "failure_subtype": "other",
                    }
                ],
            }
        )
    )

    out = collect_audit(d, audit_dir)

    assert out["row"].iloc[0]["failure_source"] == "llm_error"


def test_parse_verdict_survives_brace_in_leading_prose(tmp_path: Path):
    f = tmp_path / "verdict.json"
    f.write_text(
        "I considered the set {A, B} of options.\n"
        '{"case_failure_source": "llm_error", "models": []}'
    )
    parsed = parse_verdict(f)
    assert parsed is not None
    assert parsed["case_failure_source"] == "llm_error"


def make_verdict(m1_diagnosis: str, m2_diagnosis: str, rationale: str) -> dict:
    return {
        "reference_suspect": False,
        "reference_bug_hypothesis": "",
        "case_failure_source": "llm_error",
        "case_failure_subtype": "categorical_eligibility",
        "rationale": rationale,
        "models": [
            {
                "model": "m1",
                "failure_source": "llm_error",
                "failure_subtype": "thresholds_rates",
                "diagnosis": m1_diagnosis,
            },
            {
                "model": "m2",
                "failure_source": "llm_error",
                "failure_subtype": "categorical_eligibility",
                "diagnosis": m2_diagnosis,
            },
        ],
    }


def test_collect_uses_per_model_diagnosis_for_row_annotation(
    country_dir: Path, tmp_path: Path
):
    audit_dir = tmp_path / "audit"
    cases = prepare_audit(country_dir, audit_dir)
    s0 = next(c for c in cases if c.scenario_id == "s0")
    verdict = make_verdict(
        "Applied the net-income allotment formula without the earned income "
        "deduction, overstating the benefit by $250.",
        "Applied the 130% FPL gross income test to a household that is "
        "categorically eligible under BBCE, concluding ineligibility.",
        "Both models skipped the categorical-eligibility screen that "
        "controls this household's SNAP outcome.",
    )
    (audit_dir / "cases" / s0.case_id / "verdict.json").write_text(json.dumps(verdict))

    out = collect_audit(country_dir, audit_dir)
    rows = out["row"]
    m1 = rows[rows["model"] == "m1"].iloc[0]
    m2 = rows[rows["model"] == "m2"].iloc[0]
    assert m1["annotation"].startswith("Applied the net-income allotment")
    assert m2["annotation"].startswith("Applied the 130% FPL gross income test")
    assert out["case"].iloc[0]["case_annotation"].startswith("Both models skipped")
    assert out["hedged"].empty


def test_collect_flags_hedged_verdicts_for_rejudging(country_dir: Path, tmp_path: Path):
    # The shipped 20260707c failure class: the judge answers "is the
    # reference wrong?" instead of diagnosing the model.
    audit_dir = tmp_path / "audit"
    cases = prepare_audit(country_dir, audit_dir)
    s0 = next(c for c in cases if c.scenario_id == "s0")
    verdict = make_verdict(
        "The reference is plausible under the stated PolicyEngine "
        "derivation; there is not enough concrete evidence here to call "
        "the PolicyEngine reference wrong.",
        "The model may have used a stale threshold.",
        "Hard to verify without more information.",
    )
    (audit_dir / "cases" / s0.case_id / "verdict.json").write_text(json.dumps(verdict))

    out = collect_audit(country_dir, audit_dir)
    assert list(out["hedged"]["case_id"]) == [s0.case_id]


def test_is_hedged_separates_verdict_voice_from_legal_optionality():
    # Reference-adjudication and self-doubt: rejected.
    assert is_hedged(
        "The reference is plausible under the stated PolicyEngine derivation"
    )
    assert is_hedged("There is not enough concrete evidence to call it wrong")
    assert is_hedged("The model may have applied 2023 thresholds")
    assert is_hedged("It is unclear which pathway the model used")
    assert is_hedged("We cannot determine the exact computation")
    # Definitive diagnosis, including legal-optionality phrasing: allowed.
    assert not is_hedged(
        "Treated the 138% FPL MAGI limit as the only Medicaid pathway and "
        "never applied the aged/disabled income test, which deducts the "
        "Medicare Part B premium from countable income."
    )
    assert not is_hedged("Excess shelter costs are deductible; the model omitted them.")
    assert not is_hedged("")
    assert not is_hedged(None)


def test_prompt_treats_reference_as_verified_and_demands_diagnosis(
    country_dir: Path,
):
    case = next(c for c in build_audit_cases(country_dir) if c.scenario_id == "s0")
    prompt = render_case_prompt(case)
    assert "Treat the reference and its derivation as correct" in prompt
    assert "diagnosis" in prompt
    assert "mechanically rejected" in prompt
    assert "concrete contradiction" in prompt


def test_grounding_lookup_renders_engine_facts_block(country_dir: Path):
    lookup = {("s0", "snap"): "- medicaid_category: SENIOR_OR_DISABLED\n- age: 67"}
    cases = build_audit_cases(country_dir, grounding_lookup=lookup)
    grounded = next(c for c in cases if c.scenario_id == "s0")
    bare = next(c for c in cases if c.scenario_id == "s1")
    assert "AUTHORITATIVE ENGINE FACTS" in render_case_prompt(grounded)
    assert "SENIOR_OR_DISABLED" in render_case_prompt(grounded)
    assert "AUTHORITATIVE ENGINE FACTS" not in render_case_prompt(bare)


def test_schema_requires_per_model_diagnosis():
    items = AUDIT_OUTPUT_SCHEMA["properties"]["models"]["items"]
    assert "diagnosis" in items["properties"]
    assert "diagnosis" in items["required"]
