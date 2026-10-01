"""Checks for data-driven manuscript values."""

import re
from collections import Counter
from copy import deepcopy

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from policybench.analysis import model_cost_latency
from policybench.config import MODELS, PRICE_OVERRIDES_PER_1M
from policybench.paper_results import (
    MODEL_DISPLAY_NAMES,
    MODEL_RELEASE_DATES,
    ROOT,
    SNAPSHOT_DIR,
    PaperResults,
    r,
)


def test_frozen_roster_has_46_display_names_and_release_dates():
    roster = {row["model"] for row in r.model_stats}

    assert len(roster) == 46
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
    assert MODEL_DISPLAY_NAMES["claude-sonnet-5.5"] == "Claude Sonnet 5.5"
    assert MODEL_RELEASE_DATES["claude-sonnet-5.5"] == "2026-09-28"
    assert MODEL_DISPLAY_NAMES["grok-4.7"] == "Grok 4.7"
    assert MODEL_RELEASE_DATES["grok-4.7"] == "2026-09-21"
    assert MODEL_DISPLAY_NAMES["deepseek-v4.1-flash"] == "DeepSeek V4.1 Flash"
    assert MODEL_RELEASE_DATES["deepseek-v4.1-flash"] == "2026-09-10"
    assert MODEL_DISPLAY_NAMES["gpt-6.1-sol"] == "GPT-6.1 Sol"
    assert MODEL_RELEASE_DATES["gpt-6.1-sol"] == "2026-09-29"


def test_app_release_dates_mirror_the_paper_registry():
    """app/src/modelMeta.ts copies MODEL_RELEASE_DATES (its comment says to
    update both together); every runnable model has a date, and the two
    copies agree key for key."""
    source = (ROOT / "app" / "src" / "modelMeta.ts").read_text()
    block = source[source.index("export const MODEL_RELEASE_DATES") :]
    block = block[: block.index("};")]
    app_dates = dict(
        re.findall(r'^\s*"?([\w.\-]+)"?:\s*"(\d{4}-\d{2}-\d{2})"', block, re.M)
    )

    assert set(MODELS) <= set(MODEL_RELEASE_DATES)
    assert app_dates == MODEL_RELEASE_DATES
    assert MODEL_RELEASE_DATES["grok-4.7"] == "2026-09-21"
    assert MODEL_RELEASE_DATES["deepseek-v4.1-flash"] == "2026-09-10"


def test_parse_contract_failure_counts_come_from_frozen_dashboard():
    assert r.parse_contract_failure_counts == Counter(
        {
            "kimi-k2.6": 390,
            "glm-5.2": 133,
            "glm-5.3": 71,
            "kimi-k3": 58,
        }
    )
    assert r.parse_contract_failure_count == 652
    assert r.parse_contract_failure_count_fmt == "652"
    # 652 of the 46-model board's 88,688 scored answers (0.8% of 20260929's
    # 86,760): GPT-6.1 Sol parsed all 1,928.
    assert r.parse_contract_failure_pct_fmt == "0.7"


def test_audit_universe_counts_come_from_frozen_rows_and_annotations():
    # Release 20260929's counts plus GPT-6.1 Sol's 88 exact misses.
    assert r.audit_annotated_row_count == 7_860
    assert r.audit_annotated_row_count_fmt == "7,860"
    assert r.audit_selection_rule == ("rows whose legacy threshold score is below 1")
    assert r.exact_match_miss_count == 7_856
    assert r.exact_match_miss_count_fmt == "7,856"
    assert r.annotated_exact_miss_count == 7_856
    assert r.annotated_exact_miss_count_fmt == "7,856"
    assert r.annotated_exact_hit_count == 4
    assert r.annotated_exact_hit_count_fmt == "4"
    assert r.unannotated_below_full_bounded_score_count == 2_107
    assert r.unannotated_below_full_bounded_score_count_fmt == "2,107"


def test_contract_violations_are_counted_both_ways():
    """652 scored rows never parsed a number (rows on excluded outputs are outside
    every count); 60 more parsed a number but carry no explanation.
    The manuscript reports both, not just the first."""
    assert dict(r.explanation_missing_counts) == {
        "grok-4.3": 55,
        "kimi-k2.6": 4,
        "claude-haiku-4.5": 1,
    }
    assert r.explanation_missing_count_fmt == "60"
    assert r.contract_violation_count_fmt == "712"
    assert r.explanation_missing_breakdown_fmt == (
        "Grok 4.3 (55), Kimi K2.6 (4), and Claude Haiku 4.5 (1)"
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
    # GPT-6.1 Sol's supervised run fingerprints all four fields, and its
    # reasoning setup and timeouts.
    assert r.serving_evidence_pinned_counts == {
        "answer contract": 17,
        "request shape": 17,
        "tool choice": 16,
        "completion ceiling": 17,
    }
    assert summary == {"registry": 29, "run_state": 17}
    assert r.serving_evidence_caption == (
        "Supervised-run fingerprints pin answer contract, request shape, "
        "and completion ceiling for 17 rows; tool choice for 16 rows; reasoning "
        "setup and timeouts for seven rows. Reasoning setup and timeouts for the "
        "other ten fingerprinted rows, and all fields for the other "
        f"{summary['registry']} rows, are the harness registry as frozen in the "
        "snapshot's serving-configuration file."
    )


def test_serving_evidence_counts_exclude_legacy_or_unrecorded_fields():
    results = PaperResults()
    results.serving_config = deepcopy(r.serving_config)
    fable_evidence = results.serving_config["models"]["claude-fable-5.1"]["evidence"]

    assert results.serving_evidence_pinned_counts["tool choice"] == 16
    del fable_evidence["legacy_tool_choice_label"]
    assert results.serving_evidence_pinned_counts["tool choice"] == 17
    del fable_evidence["treatment_fingerprint"]["answer_contract"]
    assert results.serving_evidence_pinned_counts["answer contract"] == 16


def test_joint_credit_accuracy_exceptions_come_from_frozen_table():
    table = r.federal_state_joint_accuracy.set_index("Model")

    assert table.loc["Claude Fable 5.1"].tolist() == [100.0, 93.8, 93.8]
    assert table.loc["Claude Opus 5.5"].tolist() == [100.0, 91.8, 91.8]
    assert table.loc["GPT-6 Astra"].tolist() == [100.0, 88.7, 88.7]
    assert table.loc["GPT-6 Sol"].tolist() == [99.0, 87.6, 87.6]
    assert table.loc["Grok 4.7"].tolist() == [99.0, 87.6, 87.6]
    assert table.loc["GPT-5.6 Sol"].tolist() == [99.0, 86.6, 86.6]
    assert table.loc["GPT-6.1 Sol"].tolist() == [99.0, 92.8, 92.8]
    assert r.joint_credit_accuracy_exceptions == [
        "Claude Fable 5.1",
        "GPT-6.1 Sol",
        "Claude Opus 5.5",
        "GPT-6 Astra",
        "GPT-6 Sol",
        "Grok 4.7",
        "GPT-5.6 Sol",
    ]
    assert r.joint_credit_accuracy_note == (
        "The joint hit rate can be no higher than either marginal and is "
        "strictly lower than both for every model except Claude Fable 5.1, "
        "GPT-6.1 Sol, Claude Opus 5.5, GPT-6 Astra, GPT-6 Sol, Grok 4.7, and "
        "GPT-5.6 Sol."
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
        "GPT-6.1 Sol",
        "Claude Opus 5.5",
        "GPT-6 Astra",
        "GPT-6 Sol",
        "Grok 4.7",
        "GPT-5.6 Sol",
    ]
    assert (
        "except GPT-6.1 Sol, Claude Opus 5.5, GPT-6 Astra, GPT-6 Sol, Grok 4.7, "
        "and GPT-5.6 Sol." in results.joint_credit_accuracy_note
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
    # The older judges' counts fall release to release (Opus 5 had 183 cases
    # and GPT-5.6 Sol 314 on 20260922c, 132 and 303 on 20260929) because
    # Claude Opus 5.5 re-judged their cases: after the reference revisions,
    # and on 2026-09-30 for the 134 cases GPT-6.1 Sol joined (16 of them Opus
    # 5's, 5 GPT-5.6 Sol's). A re-judged case with an adjudication keeps the
    # replaced verdict under judge_previous.
    assert prov["by_judge"]["claude-opus-5"]["cases"] == 116
    assert prov["by_judge"]["claude-opus-5"]["judged_on_utc"] == ["2026-09-05"]
    assert prov["by_judge"]["claude-opus-5-5"]["cases"] == 260
    assert "2026-09-30" in prov["by_judge"]["claude-opus-5-5"]["judged_on_utc"]
    assert prov["by_judge"]["gpt-5.6-sol"]["cases"] == 298
    assert r.audit_case_count_fmt == "674"
    assert r.audit_opus_judged_case_count_fmt == "116"
    assert r.audit_opus55_judged_case_count_fmt == "260"
    assert r.audit_sol_judged_case_count_fmt == "298"


def test_joint_credit_table_orders_ties_deterministically():
    table = r.federal_state_joint_accuracy
    joint = table["Joint within 10%"].tolist()
    assert joint == sorted(joint, reverse=True)
    # Ties break by model id: gpt-6-astra before gpt-6-luna, gpt-6-sol before
    # grok-4.7.
    tied = table[table["Joint within 10%"] == 88.7]["Model"].tolist()
    assert tied == ["GPT-6 Astra", "GPT-6 Luna"]
    tied = table[table["Joint within 10%"] == 87.6]["Model"].tolist()
    assert tied == ["GPT-6 Sol", "Grok 4.7"]


def test_excluded_outputs_are_outside_the_scored_audit_universe():
    assert r.excluded_output_count == 56
    assert r.excluded_output_phrase == "56 outputs"
    assert r.excluded_output_households_phrase == "39 households"
    assert r.unlisted_input_exclusion_count == 28
    assert r.engine_defect_exclusion_count == 28
    assert r.engine_defect_root_cause_count == 11
    assert r.snap_engine_defect_exclusion_count == 1
    assert r.engine_defect_unflagged_count == 8
    # The September 22 regenerations, made on policyengine-us 1.755.4; the
    # engine upgrade's own changes are counted separately below.
    assert r.regenerated_reference_count == 26
    assert r.regenerated_reference_household_count == 24
    assert r.regenerated_snap_reference_count == 13
    assert r.regenerated_by_convention_count == 23
    assert r.regenerated_by_upstream_fix_count == 15
    assert r.upstream_fixed_root_cause_count == 8
    assert (
        r.upstream_fix_prs_fmt == "#8839, #9162, #9301, #9313, #9318, #9363 and #9586"
    )
    assert r.excluded_outputs_by_input["meets_ssi_disability_criteria"] == 7
    assert (
        r.excluded_outputs_by_input["months_receiving_social_security_disability"] == 5
    )
    assert (
        r.excluded_outputs_by_input[
            "whether the prior-year deduction of the refunded state and local tax "
            "reduced federal tax (prior-year itemization, the income-versus-sales-tax "
            "election, SALT-cap headroom)"
        ]
        == 3
    )
    assert r.scored_outputs_per_model_fmt == "1,928"
    assert r.total_outputs_per_model_fmt == "1,984"
    # Release 20260929's 2,065 plus GPT-6.1 Sol's 46 rows on excluded outputs.
    assert r.excluded_output_annotation_row_count == 2111
    # Release 20260929's 802 plus GPT-6.1 Sol's 18.
    assert r.prompt_ambiguity_row_count == 820
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
        assert stats["n"] == 1928


def test_engine_upgrade_counts_come_from_the_reference_sidecar():
    """The September 29 move to policyengine-us 2.15.17, as the reference
    sidecar's engine_upgrade revision records it (reference_audit/2026-09-28/
    README.md tabulates the same changes)."""
    assert r.policyengine_us_version == "2.15.17"
    assert r.previous_policyengine_us_version == "1.755.4"
    assert r.policyengine_version == "6.1.2"
    # The revision and the rebuild carry the upgrade's UTC day.
    assert (
        r.engine_upgrade_revision["date"]
        == r.engine_upgrade_date
        == r.reference_rebuilt_date
        == "2026-09-29"
    )
    assert r.publication_check_policyengine_us_version == "2.17.0"
    # Every changed output lands in exactly one of the three groups.
    assert (
        r.engine_upgrade_scored_change_count
        + r.engine_upgrade_within_tolerance_count
        + r.engine_upgrade_new_exclusion_count
        == len(r.engine_upgrade_revision["changed"])
        == 9
    )
    # Excluded outputs keep the values they were decided on: 52 on 1.755.4,
    # and on 2.15.17 the three this upgrade added plus the audit's
    # (final_actions.json audit_exclusions: scenario_023 head Medicaid).
    assert r.excluded_outputs_by_engine_version == {"1.755.4": 52, "2.15.17": 4}
    assert r.excluded_outputs_on_previous_engine_count == 52
    assert r.excluded_outputs_on_reference_engine_count == 4
    assert r.excluded_output_count == 56
    # Four scored references move beyond the exact-match tolerance: 008 NJ
    # and 082 NY refundable credits, 013 AZ SNAP and 028 PA reduced-price
    # meals (a 0/1 flag, so any change counts).
    assert r.engine_upgrade_scored_change_count == 4
    # 078 and 117 state income tax move by under $1.
    assert r.engine_upgrade_within_tolerance_count == 2
    # 033, 078 and 117 federal income tax leave scoring.
    assert r.engine_upgrade_new_exclusion_count == 3
    assert r.engine_upgrade_rechecked_count == 19
    changes = {
        (change["scenario_id"], change["variable"]): change
        for change in r.engine_upgrade_revision["changed"]
    }
    assert {
        key: (change["previous"], change["regenerated"])
        for key, change in changes.items()
        if key
        in {
            ("scenario_008", "state_refundable_credits"),
            ("scenario_013", "snap"),
            ("scenario_028", "reduced_price_school_meals_eligible"),
            ("scenario_082", "state_refundable_credits"),
        }
    } == {
        ("scenario_008", "state_refundable_credits"): (
            pytest.approx(5342.40, abs=0.005),
            pytest.approx(5842.40, abs=0.005),
        ),
        ("scenario_013", "snap"): (0.0, 240.0),
        ("scenario_028", "reduced_price_school_meals_eligible"): (1.0, 0.0),
        ("scenario_082", "state_refundable_credits"): (650.5, 667.0),
    }


def test_disability_section_counts_come_from_the_frozen_scenarios():
    assert r.benchmark_person_count == 177
    assert r.disabled_person_count == 33
    # The paper says no benchmark person carries a program-specific
    # disability determination; only the general flag reaches the prompt.
    assert r.program_disability_input_count == 0


def test_dataset_build_is_the_one_the_households_came_from():
    """The paper names the certified build the scenario draw sampled and the
    population weights use; the reference runtime's default dataset, which the
    manifest records under reference_output_refresh, is a later build that no
    household reference reads."""
    import json

    weights = json.loads((ROOT / "policybench/population_weights.json").read_text())
    source = weights["countries"]["us"]["metadata"]["source_dataset_uri"]
    assert r.dataset_id == "populace_us_2024"
    assert r.dataset_build_id == "populace-us-2024-5da5a95-20260611"
    assert r.dataset_uri == source
    assert (
        r.manifest["reference_output_refresh"]["policyengine_us_data_build_id"]
        != r.dataset_build_id
    )


_AMOUNT_OUTPUTS = (
    "snap",
    "state_refundable_credits",
    "federal_income_tax_before_refundable_credits",
)
_FLAG_OUTPUTS = (
    "reduced_price_school_meals_eligible",
    "free_school_meals_eligible",
)


@st.composite
def _upgrade_revisions(draw):
    """A synthetic engine-upgrade revision and exclusion record: changes to
    amount and 0/1 outputs, some of them to outputs the record excludes."""
    keys = draw(
        st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=40).map(
                    lambda n: f"scenario_{n:03d}"
                ),
                st.sampled_from(_AMOUNT_OUTPUTS + _FLAG_OUTPUTS),
            ),
            max_size=30,
        )
    )
    changes = []
    for scenario_id, variable in keys:
        if variable in _FLAG_OUTPUTS:
            previous = draw(st.sampled_from((0.0, 1.0)))
            regenerated = draw(st.sampled_from((0.0, 1.0)))
        else:
            previous = draw(st.floats(0, 1e5, allow_nan=False))
            regenerated = previous + draw(
                st.one_of(st.floats(-2, 2, allow_nan=False), st.floats(-1e4, 1e4))
            )
        changes.append(
            {
                "scenario_id": scenario_id,
                "variable": variable,
                "previous": previous,
                "regenerated": regenerated,
            }
        )
    excluded = draw(st.sets(st.sampled_from(keys)) if keys else st.just(set())) | draw(
        st.sets(
            st.tuples(st.just("scenario_999"), st.sampled_from(_AMOUNT_OUTPUTS)),
            max_size=3,
        )
    )
    return changes, excluded


@settings(max_examples=300, deadline=None)
@given(_upgrade_revisions())
def test_engine_upgrade_partition_is_exact_and_disjoint(revision):
    """Invariant: every change lands in exactly one group; new exclusions are
    the changes to excluded outputs; a scored change lies beyond the
    exact-match tolerance ($1, or any change of a 0/1 flag) and a within-
    tolerance change inside it."""
    from policybench.paper_results import partition_engine_upgrade_changes

    changes, excluded = revision
    partition = partition_engine_upgrade_changes(changes, excluded)
    assert set(partition) == {"scored_changes", "within_tolerance", "new_exclusions"}
    placed = [id(change) for group in partition.values() for change in group]
    assert sorted(placed) == sorted(id(change) for change in changes)
    assert len(placed) == len(set(placed)) == len(changes)
    for change in partition["new_exclusions"]:
        assert (change["scenario_id"], change["variable"]) in excluded
    for name in ("scored_changes", "within_tolerance"):
        for change in partition[name]:
            assert (change["scenario_id"], change["variable"]) not in excluded
            moved = abs(change["regenerated"] - change["previous"])
            limit = 1 if change["variable"] in _AMOUNT_OUTPUTS else 0
            assert (moved > limit) == (name == "scored_changes")
