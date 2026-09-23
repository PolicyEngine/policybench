"""Checks for data-driven manuscript values."""

import re
from collections import Counter
from copy import deepcopy

import pandas as pd
import pytest

from policybench.analysis import model_cost_latency
from policybench.config import PRICE_OVERRIDES_PER_1M
from policybench.paper_results import (
    MODEL_DISPLAY_NAMES,
    MODEL_RELEASE_DATES,
    ROOT,
    SNAPSHOT_DIR,
    PaperResults,
    r,
)


def test_frozen_roster_has_42_display_names_and_release_dates():
    roster = {row["model"] for row in r.model_stats}

    assert len(roster) == 42
    assert set(MODEL_DISPLAY_NAMES) == roster
    assert roster <= set(MODEL_RELEASE_DATES)
    assert MODEL_DISPLAY_NAMES["claude-fable-5.1"] == "Claude Fable 5.1"
    assert MODEL_RELEASE_DATES["claude-fable-5.1"] == "2026-09-01"
    assert MODEL_DISPLAY_NAMES["gemini-3.7-flash"] == "Gemini 3.7 Flash"
    assert MODEL_RELEASE_DATES["gemini-3.7-flash"] == "2026-08-13"
    assert MODEL_DISPLAY_NAMES["grok-4.6"] == "Grok 4.6"
    assert MODEL_DISPLAY_NAMES["ox-alpha"] == "GLM-5.3-Flash (preview)"
    assert MODEL_RELEASE_DATES["ox-alpha"] == "2026-08-20"
    assert MODEL_DISPLAY_NAMES["gpt-6-sol"] == "GPT-6 Sol"
    assert MODEL_DISPLAY_NAMES["gpt-6-luna"] == "GPT-6 Luna"
    assert MODEL_RELEASE_DATES["gpt-6-sol"] == "2026-09-22"
    assert MODEL_RELEASE_DATES["gpt-6-luna"] == "2026-09-22"
    assert MODEL_DISPLAY_NAMES["claude-opus-5.5"] == "Claude Opus 5.5"


def test_parse_contract_failure_counts_come_from_frozen_dashboard():
    assert r.parse_contract_failure_counts == Counter(
        {
            "kimi-k2.6": 394,
            "glm-5.2": 133,
            "glm-5.3": 71,
            "kimi-k3": 59,
        }
    )
    assert r.parse_contract_failure_count == 657
    assert r.parse_contract_failure_count_fmt == "657"
    assert r.parse_contract_failure_pct_fmt == "0.8"


def test_audit_universe_counts_come_from_frozen_rows_and_annotations():
    assert r.audit_annotated_row_count == 7_583
    assert r.audit_annotated_row_count_fmt == "7,583"
    assert r.audit_selection_rule == ("rows whose legacy threshold score is below 1")
    assert r.exact_match_miss_count == 7_579
    assert r.exact_match_miss_count_fmt == "7,579"
    assert r.annotated_exact_miss_count == 7_579
    assert r.annotated_exact_miss_count_fmt == "7,579"
    assert r.annotated_exact_hit_count == 4
    assert r.annotated_exact_hit_count_fmt == "4"
    assert r.unannotated_below_full_bounded_score_count == 1_843
    assert r.unannotated_below_full_bounded_score_count_fmt == "1,843"


def test_contract_violations_are_counted_both_ways():
    """657 scored rows never parsed a number (rows on excluded outputs are outside
    every count); 61 more parsed a number but carry no explanation.
    The manuscript reports both, not just the first."""
    assert dict(r.explanation_missing_counts) == {
        "grok-4.3": 56,
        "kimi-k2.6": 4,
        "claude-haiku-4.5": 1,
    }
    assert r.explanation_missing_count_fmt == "61"
    assert r.contract_violation_count_fmt == "718"
    assert r.explanation_missing_breakdown_fmt == (
        "Grok 4.3 (56), Kimi K2.6 (4), and Claude Haiku 4.5 (1)"
    )


def test_raw_response_preservation_is_stated_with_its_exceptions():
    assert dict(r.blank_raw_response_counts) == {
        "claude-fable-5": 1984,
        "glm-5.3": 78,
        "kimi-k3": 64,
    }
    assert r.blank_raw_response_note == (
        "no raw payload is retained for Claude Fable 5 (1,984 rows), "
        "GLM-5.3 (78 rows), and Kimi K3 (64 rows)"
    )


def test_frozen_kimi_k3_cost_preserves_recorded_provider_charges():
    predictions = pd.read_csv(
        SNAPSHOT_DIR / "runs" / r.us_run_label / "predictions.csv.gz",
        usecols=[
            "model",
            "scenario_id",
            "variable",
            "prediction",
            "total_cost_usd",
            "provider_reported_cost_usd",
            "prompt_tokens",
            "completion_tokens",
        ],
    )
    kimi = predictions.loc[predictions["model"] == "kimi-k3"]
    recorded_cost = kimi["total_cost_usd"].sum()
    published = next(row for row in r.model_stats if row["model"] == "kimi-k3")

    assert f"{recorded_cost:.3f}" == "47.043"
    assert recorded_cost == pytest.approx(kimi["provider_reported_cost_usd"].sum())
    assert published["costUsd"] == pytest.approx(recorded_cost)
    assert model_cost_latency(kimi, PRICE_OVERRIDES_PER_1M)["kimi-k3"][
        "costUsd"
    ] == pytest.approx(recorded_cost)
    repriced_cost = (
        kimi["prompt_tokens"].sum() * PRICE_OVERRIDES_PER_1M["kimi-k3"]["input"]
        + kimi["completion_tokens"].sum() * PRICE_OVERRIDES_PER_1M["kimi-k3"]["output"]
    ) / 1e6
    assert recorded_cost != pytest.approx(repriced_cost)


@pytest.mark.parametrize(
    "path",
    [
        "policybench/config.py",
        "paper/index.qmd",
        "docs/benchmark_card.md",
        "app/src/components/Methodology.tsx",
    ],
)
def test_cost_basis_discloses_recorded_costs_without_retroactive_overrides(path):
    text = re.sub(r"\s+", " ", (ROOT / path).read_text().replace("#", ""))

    assert "recorded per-call cost" in text
    # eval_no_tools records the token-count reconstruction whenever one exists
    # and falls back to the provider's charge (tests/test_eval_no_tools.py).
    assert (
        "reconstructed from token counts at the list price configured at request time"
        in text
    )
    assert "provider-reported charge where no reconstruction was available" in text
    assert "where the provider returns one, otherwise reconstructed" not in text
    assert "List-price overrides apply at request time, not retroactively" in text
    assert "override provider-reported" not in text
    assert "supersede recorded costs" not in text


def test_serving_evidence_caption_comes_from_frozen_configuration():
    summary = r.serving_config["evidence_summary"]
    labels = r.serving_config["evidence_field_labels"]
    commit = r.serving_config["registry_commit"]

    assert re.fullmatch(r"[0-9a-f]{40}", commit)
    assert labels == {
        "registry_for_run_state": ["reasoning setup", "timeouts"],
        "run_state": [
            "answer contract",
            "request shape",
            "tool choice",
            "completion ceiling",
        ],
    }
    assert r.serving_evidence_pinned_counts == {
        "answer contract": 13,
        "request shape": 13,
        "tool choice": 12,
        "completion ceiling": 13,
    }
    assert r.serving_evidence_caption == (
        "Supervised-run fingerprints pin answer contract, request shape, "
        "and completion ceiling for 13 rows; tool choice for 12 rows; reasoning "
        "setup and timeouts for three rows. Reasoning setup and timeouts for the "
        "other ten fingerprinted rows, and all fields for the other "
        f"{summary['registry']} rows, are the harness registry as frozen in the "
        "snapshot's serving-configuration file."
    )


def test_serving_evidence_counts_exclude_legacy_or_unrecorded_fields():
    results = PaperResults()
    results.serving_config = deepcopy(r.serving_config)
    fable_evidence = results.serving_config["models"]["claude-fable-5.1"]["evidence"]

    assert results.serving_evidence_pinned_counts["tool choice"] == 12
    del fable_evidence["legacy_tool_choice_label"]
    assert results.serving_evidence_pinned_counts["tool choice"] == 13
    del fable_evidence["treatment_fingerprint"]["answer_contract"]
    assert results.serving_evidence_pinned_counts["answer contract"] == 12


def test_joint_credit_accuracy_exceptions_come_from_frozen_table():
    table = r.federal_state_joint_accuracy.set_index("Model")

    assert table.loc["Claude Fable 5.1"].tolist() == [100.0, 93.8, 93.8]
    assert table.loc["Claude Opus 5.5"].tolist() == [100.0, 91.8, 91.8]
    assert table.loc["GPT-6 Astra"].tolist() == [100.0, 89.7, 89.7]
    assert table.loc["GPT-6 Sol"].tolist() == [99.0, 88.7, 88.7]
    assert table.loc["GPT-5.6 Sol"].tolist() == [99.0, 87.6, 87.6]
    assert r.joint_credit_accuracy_exceptions == [
        "Claude Fable 5.1",
        "Claude Opus 5.5",
        "GPT-6 Astra",
        "GPT-6 Sol",
        "GPT-5.6 Sol",
    ]
    assert r.joint_credit_accuracy_note == (
        "The joint hit rate can be no higher than either marginal and is "
        "strictly lower than both for every model except Claude Fable 5.1, "
        "Claude Opus 5.5, GPT-6 Astra, GPT-6 Sol, and GPT-5.6 Sol."
    )
    other_models = table.drop(index=r.joint_credit_accuracy_exceptions)
    assert (other_models["Joint within 10%"] < other_models["Federal within 10%"]).all()
    assert (other_models["Joint within 10%"] < other_models["State within 10%"]).all()

    paper = (ROOT / "paper/index.qmd").read_text()
    assert "`{python} r.joint_credit_accuracy_note`" in paper
    assert "strictly lower for all but the top model" not in paper


def test_joint_credit_accuracy_prose_tracks_changed_table_exceptions():
    results = PaperResults()
    table = r.federal_state_joint_accuracy.copy()
    table.loc[table["Model"] == "Claude Fable 5.1", "Joint within 10%"] = 89.0
    results.federal_state_joint_accuracy = table

    assert results.joint_credit_accuracy_exceptions == [
        "Claude Opus 5.5",
        "GPT-6 Astra",
        "GPT-6 Sol",
        "GPT-5.6 Sol",
    ]
    assert (
        "except Claude Opus 5.5, GPT-6 Astra, GPT-6 Sol, and GPT-5.6 Sol."
        in results.joint_credit_accuracy_note
    )
    assert "Claude Fable 5.1" not in results.joint_credit_accuracy_note


def test_judge_provenance_is_frozen_in_the_manifest():
    """Every audited case names its judge model; all three judges are board rows."""
    prov = r.audit_judge_provenance
    roster = {row["model"] for row in r.model_stats}
    assert set(prov["by_judge"]) == {"claude-opus-5", "claude-opus-5-5", "gpt-5.6-sol"}
    # The Opus 5.5 judge id is the API id; its board row is claude-opus-5.5.
    assert {judge.replace("5-5", "5.5") for judge in prov["by_judge"]} <= roster
    assert (
        sum(entry["cases"] for entry in prov["by_judge"].values())
        == (prov["cases_judged"])
    )
    assert prov["by_judge"]["claude-opus-5"]["cases"] == 183
    assert prov["by_judge"]["claude-opus-5"]["judged_on_utc"] == ["2026-09-05"]
    assert prov["by_judge"]["claude-opus-5-5"]["cases"] == 171
    assert prov["by_judge"]["gpt-5.6-sol"]["cases"] == 314
    assert r.audit_case_count_fmt == "668"
    assert r.audit_opus_judged_case_count_fmt == "183"
    assert r.audit_opus55_judged_case_count_fmt == "171"
    assert r.audit_sol_judged_case_count_fmt == "314"


def test_joint_credit_table_orders_ties_deterministically():
    table = r.federal_state_joint_accuracy
    joint = table["Joint within 10%"].tolist()
    assert joint == sorted(joint, reverse=True)
    tied = table[table["Joint within 10%"] == 87.6]["Model"].tolist()
    assert tied[:2] == ["GPT-5.6 Sol", "GPT-6 Luna"]


def test_excluded_outputs_are_outside_the_scored_audit_universe():
    assert r.excluded_output_count == 52
    assert r.excluded_output_phrase == "52 outputs"
    assert r.excluded_output_households_phrase == "36 households"
    assert r.unlisted_input_exclusion_count == 24
    assert r.engine_defect_exclusion_count == 28
    assert r.engine_defect_root_cause_count == 11
    assert r.snap_engine_defect_exclusion_count == 1
    assert r.engine_defect_unflagged_count == 9
    assert r.regenerated_reference_count == 26
    assert r.regenerated_by_convention_count == 23
    assert r.regenerated_by_upstream_fix_count == 15
    assert r.upstream_fixed_root_cause_count == 7
    assert r.upstream_fix_prs_fmt == "#8839, #9162, #9301, #9318 and #9363"
    assert r.excluded_outputs_by_input["meets_ssi_disability_criteria"] == 6
    assert (
        r.excluded_outputs_by_input["months_receiving_social_security_disability"] == 5
    )
    assert r.scored_outputs_per_model_fmt == "1,932"
    assert r.total_outputs_per_model_fmt == "1,984"
    assert r.excluded_output_annotation_row_count == 1793
    assert r.prompt_ambiguity_row_count == 616
    # No scored row carries a descriptive class; every excluded-output row
    # carries its exclusion's class unless it never parsed.
    scored_sources = {
        row["failure_source"] for row in r._audit_rows if not r._is_excluded(row)
    }
    assert not scored_sources & {
        "prompt_ambiguity",
        "reference_engine_defect",
        "reference_later_law",
    }
    for row in r._excluded_output_annotation_rows:
        assert row["failure_source"] in {
            "prompt_ambiguity",
            "reference_engine_defect",
            "reference_later_law",
            "parse_contract_failure",
        }
    for stats in r.model_stats:
        assert stats["n"] == 1932
