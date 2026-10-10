"""Checks for data-driven manuscript values."""

import csv
import functools
import gzip
import io
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from policybench.analysis import model_cost_latency
from policybench.config import MODELS, PRICE_OVERRIDES_PER_1M
from policybench.paper_results import (
    MODEL_DISPLAY_NAMES,
    MODEL_RELEASE_DATES,
    REVIEW_DATE,
    REVIEW_SWEEPS,
    ROOT,
    SNAPSHOT_DIR,
    PaperResults,
    partition_review_sweep_moves,
    r,
)
from policybench.reference_exclusions import load_reference_exclusions
from tests.second_engine_upgrade import (
    paper_results_for,
    release_20261006,
    with_second_upgrade,
)


def test_frozen_roster_has_47_display_names_and_release_dates():
    roster = {row["model"] for row in r.model_stats}

    assert len(roster) == 47
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


def test_claude_haiku_5_5_release_date_is_recorded():
    """Claude Haiku 5.5's model overview says "Released October 7, 2026",
    and the Models API lists claude-haiku-5-5 with created_at 2026-10-07."""
    assert MODEL_RELEASE_DATES["claude-haiku-5.5"] == "2026-10-07"


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
    # Release 20260930's 652 (Kimi K2.6 390, GLM-5.2 133) less the eight on
    # the outputs the 2026-10-05 review excluded (seven Kimi K2.6, one GLM-5.2;
    # test_the_review_moves_the_paper_counts_by_its_eight_outputs_alone): 644
    # in release 20261006 (Kimi K2.6 383, GLM-5.2 132, GLM-5.3 71, Kimi K3
    # 58). Release 20261010's eight new exclusions take out four (Kimi K2.6)
    # and the 14 outputs its engine upgrade returns to scoring bring back 19
    # (Kimi K2.6 11, GLM-5.2 four, GLM-5.3 two, Kimi K3 two): 659. Claude
    # Haiku 5.5 parsed every answer.
    assert r.parse_contract_failure_counts == Counter(
        {
            "kimi-k2.6": 390,
            "glm-5.2": 136,
            "glm-5.3": 73,
            "kimi-k3": 60,
        }
    )
    assert r.parse_contract_failure_count == 659
    assert r.parse_contract_failure_count_fmt == "659"
    # 659 of the 47-model board's 90,522 scored answers (47 x 1,926).
    assert r.n_canonical_rows == 90_522
    assert r.parse_contract_failure_pct_fmt == "0.7"


def test_audit_universe_counts_come_from_frozen_rows_and_annotations():
    # Release 20260930's counts (7,860 annotated, 7,856 misses, 2,107
    # unannotated) less the 333 annotated misses and the 35 exact hits on the
    # eight outputs the 2026-10-05 review excluded: 7,527, 7,523 and 2,072 in
    # release 20261006. Release 20261010 adds Claude Haiku 5.5's rows and
    # moves the scored outputs: 8,001, 7,997 and 2,138.
    assert r.audit_annotated_row_count == 8_001
    assert r.audit_annotated_row_count_fmt == "8,001"
    assert r.audit_selection_rule == ("rows whose legacy threshold score is below 1")
    assert r.exact_match_miss_count == 7_997
    assert r.exact_match_miss_count_fmt == "7,997"
    assert r.annotated_exact_miss_count == 7_997
    assert r.annotated_exact_miss_count_fmt == "7,997"
    assert r.annotated_exact_hit_count == 4
    assert r.annotated_exact_hit_count_fmt == "4"
    assert r.unannotated_below_full_bounded_score_count == 2_138
    assert r.unannotated_below_full_bounded_score_count_fmt == "2,138"


def test_contract_violations_are_counted_both_ways():
    """659 scored rows never parsed a number (rows on excluded outputs are outside
    every count); 59 more parsed a number but carry no explanation.
    The manuscript reports both, not just the first."""
    assert dict(r.explanation_missing_counts) == {
        "grok-4.3": 55,
        "kimi-k2.6": 3,
        "claude-haiku-4.5": 1,
    }
    assert r.explanation_missing_count_fmt == "59"
    assert r.contract_violation_count_fmt == "718"
    assert r.explanation_missing_breakdown_fmt == (
        "Grok 4.3 (55), Kimi K2.6 (3), and Claude Haiku 4.5 (1)"
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
    # GPT-6.1 Sol's and Claude Haiku 5.5's supervised runs fingerprint all
    # four fields, and their reasoning setup and timeouts.
    assert r.serving_evidence_pinned_counts == {
        "answer contract": 18,
        "request shape": 18,
        "tool choice": 17,
        "completion ceiling": 18,
    }
    assert summary == {"registry": 29, "run_state": 18}
    assert r.serving_evidence_caption == (
        "Supervised-run fingerprints pin answer contract, request shape, "
        "and completion ceiling for 18 rows; tool choice for 17 rows; reasoning "
        "setup and timeouts for eight rows. Reasoning setup and timeouts for the "
        "other ten fingerprinted rows, and all fields for the other "
        f"{summary['registry']} rows, are the harness registry as frozen in the "
        "snapshot's serving-configuration file."
    )


def test_serving_evidence_counts_exclude_legacy_or_unrecorded_fields():
    results = PaperResults()
    results.serving_config = deepcopy(r.serving_config)
    fable_evidence = results.serving_config["models"]["claude-fable-5.1"]["evidence"]

    assert results.serving_evidence_pinned_counts["tool choice"] == 17
    del fable_evidence["legacy_tool_choice_label"]
    assert results.serving_evidence_pinned_counts["tool choice"] == 18
    del fable_evidence["treatment_fingerprint"]["answer_contract"]
    assert results.serving_evidence_pinned_counts["answer contract"] == 17


def test_joint_credit_accuracy_exceptions_come_from_frozen_table():
    table = r.federal_state_joint_accuracy.set_index("Model")

    assert table.loc["Claude Fable 5.1"].tolist() == [100.0, 93.8, 93.8]
    assert table.loc["Claude Opus 5.5"].tolist() == [100.0, 92.8, 92.8]
    assert table.loc["GPT-6 Astra"].tolist() == [100.0, 88.7, 88.7]
    assert table.loc["GPT-6 Sol"].tolist() == [99.0, 88.7, 88.7]
    assert table.loc["Grok 4.7"].tolist() == [99.0, 88.7, 88.7]
    assert table.loc["GPT-5.6 Sol"].tolist() == [99.0, 87.6, 87.6]
    assert table.loc["GPT-6.1 Sol"].tolist() == [99.0, 93.8, 93.8]
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
    # 5's, 5 GPT-5.6 Sol's), and again on 2026-10-08 and 2026-10-09 for the
    # cases Claude Haiku 5.5 re-opened (116, 260 and 298 in release 20261006).
    # A re-judged case with an adjudication keeps the replaced verdict under
    # judge_previous.
    assert prov["by_judge"]["claude-opus-5"]["cases"] == 94
    assert prov["by_judge"]["claude-opus-5"]["judged_on_utc"] == ["2026-09-05"]
    assert prov["by_judge"]["claude-opus-5-5"]["cases"] == 314
    assert "2026-09-30" in prov["by_judge"]["claude-opus-5-5"]["judged_on_utc"]
    assert "2026-10-09" in prov["by_judge"]["claude-opus-5-5"]["judged_on_utc"]
    assert prov["by_judge"]["gpt-5.6-sol"]["cases"] == 269
    assert r.audit_case_count_fmt == "677"
    assert r.audit_opus_judged_case_count_fmt == "94"
    assert r.audit_opus55_judged_case_count_fmt == "314"
    assert r.audit_sol_judged_case_count_fmt == "269"


def test_joint_credit_table_orders_ties_deterministically():
    table = r.federal_state_joint_accuracy
    joint = table["Joint within 10%"].tolist()
    assert joint == sorted(joint, reverse=True)
    # Ties break by model id: claude-fable-5.1 before gpt-6.1-sol, and
    # gpt-6-astra before gpt-6-sol before grok-4.7.
    tied = table[table["Joint within 10%"] == 93.8]["Model"].tolist()
    assert tied == ["Claude Fable 5.1", "GPT-6.1 Sol"]
    tied = table[table["Joint within 10%"] == 88.7]["Model"].tolist()
    assert tied == ["GPT-6 Astra", "GPT-6 Sol", "Grok 4.7"]


def test_excluded_outputs_are_outside_the_scored_audit_universe():
    # Release 20260930's 56 outputs in 39 households plus the 2026-10-05
    # review's eight (in scenario_022, 032, 043, 081, 082 and 114; 022, 081
    # and 082 already had one): 64 in 42 households in release 20261006.
    # Release 20261010 adds the six ruled records its engine upgrade keeps
    # and the two Indiana county records, and returns 14 of release 20261006's
    # excluded outputs to scoring: 58 in 42 households.
    assert r.excluded_output_count == 58
    assert r.excluded_output_phrase == "58 outputs"
    assert r.excluded_output_households_phrase == "42 households"
    assert r.unlisted_input_exclusion_count == 42
    assert r.engine_defect_exclusion_count == 14
    assert r.engine_defect_root_cause_count == 8
    assert r.snap_engine_defect_exclusion_count == 1
    assert r.engine_defect_unflagged_count == 3
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
    # The 2026-10-05 review's three inputs (the records' own text): the state
    # income tax in SALT alone for 022 and 081, with the Part B premium for
    # 114's federal output, the Part B premium alone for 114's Virginia
    # output, and the employer's deduction for the four payroll outputs.
    by_input = r.excluded_outputs_by_input
    salt = next(k for k in by_input if k.startswith("state income tax withheld"))
    part_b = next(k for k in by_input if k.startswith("Medicare enrollment"))
    payroll = next(k for k in by_input if k.startswith("whether the employer deducts"))
    assert by_input[salt] == 2
    assert by_input[f"{salt}; also {part_b}"] == 1
    assert by_input[part_b] == 1
    assert by_input[payroll] == 4
    assert by_input["county of residence (Indiana county income tax)"] == 2
    assert r.scored_outputs_per_model_fmt == "1,926"
    assert r.total_outputs_per_model_fmt == "1,984"
    # Release 20260930's 2,111 rows on excluded outputs plus the 333 annotated
    # rows on the review's eight outputs (2,444 in release 20261006), moved by
    # release 20261010's exclusions, regenerations and Claude Haiku 5.5's rows.
    assert r.excluded_output_annotation_row_count == 2212
    # Release 20260930's 820 plus the review's 325 relabeled llm_error rows
    # (135 SALT, 45 Part B, 145 payroll); its eight parse failures stay.
    # 1,145 in release 20261006.
    assert r.prompt_ambiguity_row_count == 1447
    assert (
        r.excluded_output_annotation_row_count - r.excluded_descriptive_row_count == 48
    )
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
        assert stats["n"] == 1926


# The reference records, as committed and with a synthetic second upgrade
# (tests/second_engine_upgrade.py, mock data): the upgrade accessors must hold
# for any number of upgrades, keyed to the last, while every fact of the
# 2026-09-29 upgrade stays pinned to that revision.
RESULTS = {
    "working_tree": lambda: r,
    "second_upgrade": lambda: _second_upgrade_results(),
}


@functools.cache
def _second_upgrade_results() -> PaperResults:
    return paper_results_for(with_second_upgrade(release_20261006()))


@pytest.fixture(params=sorted(RESULTS))
def results(request) -> PaperResults:
    return RESULTS[request.param]()


def test_engine_upgrade_counts_come_from_the_reference_sidecar(results):
    """The September 29 move to policyengine-us 2.15.17, as the reference
    sidecar's 2026-09-29 engine_upgrade revision records it (reference_audit/
    2026-09-28/README.md tabulates the same changes), whatever upgrades
    follow it."""
    upgrade = results.september_upgrade
    assert results.engine_upgrades[0] is upgrade
    assert results.engine_upgrade_on("2026-09-29") is upgrade
    assert results.engine_upgrade_to("2.15.17") is upgrade
    assert upgrade.engine_version == "2.15.17"
    assert upgrade.previous_engine_version == "1.755.4"
    assert upgrade.date == "2026-09-29"
    assert results.policyengine_version == "6.1.2"
    assert results.publication_check_policyengine_us_version == "2.17.0"
    # Every changed output lands in exactly one of the groups.
    assert (
        upgrade.scored_change_count
        + upgrade.within_tolerance_count
        + upgrade.new_exclusion_count
        + upgrade.restored_count
        == len(upgrade.changes)
        == 9
    )
    # Four scored references move beyond the exact-match tolerance: 008 NJ
    # and 082 NY refundable credits, 013 AZ SNAP and 028 PA reduced-price
    # meals (a 0/1 flag, so any change counts).
    assert upgrade.scored_change_count == 4
    # 078 and 117 state income tax move by under $1.
    assert upgrade.within_tolerance_count == 2
    # 033, 078 and 117 federal income tax leave scoring.
    assert upgrade.new_exclusion_count == 3
    assert upgrade.restored_count == 0
    assert upgrade.rechecked_count == 19
    # Excluded when the upgrade began: release 20260922c's 52, all on 1.755.4;
    # once it was decided, also the three above and the audit's (final_
    # actions.json audit_exclusions: scenario_023 head Medicaid).
    assert len(upgrade.excluded_before) == 52
    assert len(upgrade.excluded) == 56
    changes = {(c["scenario_id"], c["variable"]): c for c in upgrade.changes}
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
    rechecked = upgrade.rechecked[0]
    assert upgrade.rechecked_value(rechecked) == rechecked["value_on_2_15_17"]


def test_engine_upgrade_accessors_follow_the_last_upgrade(results):
    """The engine_upgrade_* accessors, the reference engine and the previous
    engine come from the sidecar's last upgrade and its own
    previous_engine_version, the engine the upgrade before it moved to."""
    upgrades = results.engine_upgrades
    last = upgrades[-1]
    assert results.last_engine_upgrade is last
    assert results.engine_upgrade_count == len(upgrades)
    assert results.engine_upgrade_revision is last.revision
    assert results.reference_revisions[-1] is last.revision
    assert results.policyengine_us_version == last.engine_version
    assert results.previous_policyengine_us_version == last.previous_engine_version
    for before, after in zip(upgrades, upgrades[1:]):
        assert after.previous_engine_version == before.engine_version
    # The revision and the rebuild carry the last upgrade's UTC day.
    assert (
        results.engine_upgrade_date
        == last.date
        == last.revision["date"]
        == results.reference_rebuilt_date
    )
    assert results.engine_upgrade_partition == last.partition
    assert results.engine_upgrade_scored_change_count == last.scored_change_count
    assert results.engine_upgrade_within_tolerance_count == (
        last.within_tolerance_count
    )
    assert results.engine_upgrade_new_exclusion_count == last.new_exclusion_count
    assert results.engine_upgrade_restored_count == last.restored_count
    assert results.engine_upgrade_rechecked_count == len(
        last.revision["excluded_outputs_rechecked"]
    )
    assert sum(len(group) for group in last.partition.values()) == len(
        last.revision["changed"]
    )
    # Excluded outputs keep the values they were decided on, each on an
    # engine the references were on; the counts cover every record.
    by_engine = results.excluded_outputs_by_engine_version
    chain = [upgrades[0].previous_engine_version] + [u.engine_version for u in upgrades]
    assert set(by_engine) <= set(chain)
    assert list(by_engine) == [v for v in chain if v in by_engine]
    assert sum(by_engine.values()) == results.excluded_output_count
    assert results.excluded_outputs_on_reference_engine_count == by_engine.get(
        last.engine_version, 0
    )
    assert results.excluded_outputs_on_previous_engine_count == by_engine.get(
        last.previous_engine_version, 0
    )


def test_each_upgrade_changes_no_output_it_kept_excluded(results):
    """Rule 5: an output excluded before an upgrade and after it keeps the
    value it was decided on, so no upgrade lists it as changed; an output an
    upgrade restores was excluded before it and is not after."""
    for upgrade in results.engine_upgrades:
        kept = upgrade.excluded_before & upgrade.excluded
        assert not kept & {(c["scenario_id"], c["variable"]) for c in upgrade.changes}
        assert upgrade.restored <= upgrade.excluded_before - upgrade.excluded


def test_the_release_on_2_15_17_counts_excluded_outputs_by_engine():
    """Release 20261006, the last on policyengine-us 2.15.17, read from git:
    52 excluded outputs keep 1.755.4 values, and 12 keep 2.15.17 values (the
    three the upgrade added, the audit's scenario_023 head Medicaid and the
    2026-10-05 review's eight)."""
    base = _release_20261006()
    assert base.policyengine_us_version == "2.15.17"
    assert base.last_engine_upgrade.revision == r.september_upgrade.revision
    assert base.excluded_output_count == 64
    assert base.excluded_outputs_by_engine_version == {"1.755.4": 52, "2.15.17": 12}
    assert base.excluded_outputs_on_previous_engine_count == 52
    assert base.excluded_outputs_on_reference_engine_count == 12
    assert base.excluded_outputs_by_engine_version_phrase == (
        "52 computed with policyengine-us 1.755.4, 12 with 2.15.17"
    )
    # The 2026-10-05 review's counts rebuild from the release's own records.
    assert base.review_scored_before_count == 1928
    assert base.excluded_before_review_keys == r.excluded_before_review_keys


def test_the_second_upgrade_fixture_partitions_by_its_own_records():
    """On the synthetic second upgrade (mock data), the last upgrade's groups
    are its own: a scored move, a move within the tolerance, a new exclusion on
    the new engine and a restored 1.755.4 exclusion. The 2026-09-29 upgrade's
    groups do not move, though a record decided after it now excludes one of
    its scored changes and the restored record has left the record."""
    from tests import second_engine_upgrade as mock

    results = _second_upgrade_results()
    last = results.last_engine_upgrade
    assert results.engine_upgrade_count == 2
    assert results.policyengine_us_version == mock.MOCK_ENGINE
    assert results.previous_policyengine_us_version == "2.15.17"

    def keys(group):
        return [(c["scenario_id"], c["variable"]) for c in last.partition[group]]

    assert keys("scored_changes") == [mock.MOCK_SCORED]
    assert keys("within_tolerance") == [mock.MOCK_WITHIN]
    assert keys("new_exclusions") == [mock.MOCK_NEW_EXCLUSION]
    assert keys("restored") == [mock.MOCK_RESTORED]
    assert last.restored == {mock.MOCK_RESTORED}
    assert mock.MOCK_RESTORED in last.excluded_before
    assert mock.MOCK_RESTORED not in last.excluded
    assert mock.MOCK_LATER_RECORD in last.excluded_before & last.excluded
    assert results.engine_upgrade_rechecked_count == 2
    assert {
        (rec["scenario_id"], rec["variable"]): last.rechecked_value(rec)
        for rec in last.rechecked
    } == mock.MOCK_RECHECKED_VALUES
    # Three engines behind the excluded outputs' values: the restored 1.755.4
    # record leaves, the 2026-10-06 record joins 2.15.17's, and the new
    # exclusion is on the new engine.
    assert results.excluded_outputs_by_engine_version == {
        "1.755.4": 51,
        "2.15.17": 13,
        mock.MOCK_ENGINE: 1,
    }
    assert results.excluded_outputs_by_engine_version_phrase == (
        f"51 computed with policyengine-us 1.755.4, 13 with 2.15.17, "
        f"1 with {mock.MOCK_ENGINE}"
    )
    assert results.excluded_outputs_on_previous_engine_count == 13
    assert results.excluded_outputs_on_reference_engine_count == 1
    september = results.september_upgrade
    assert september.partition == r.september_upgrade.partition
    assert september.excluded == r.september_upgrade.excluded
    assert september.excluded_before == r.september_upgrade.excluded_before
    # The 2026-10-05 review's counts read the record and the references as
    # they stood at the review.
    assert results.review_exclusion_keys == r.review_exclusion_keys
    assert results.excluded_before_review_keys == r.excluded_before_review_keys
    assert results.review_scored_before_count == r.review_scored_before_count
    assert results.review_sweep_partition == r.review_sweep_partition
    assert results.references_as_of(REVIEW_DATE) == release_20261006().references
    assert r.references_as_of(REVIEW_DATE) == release_20261006().references


def test_engine_upgrade_lookups_refuse_a_missing_or_ambiguous_upgrade():
    with pytest.raises(ValueError, match="no engine_upgrade revision dated"):
        r.engine_upgrade_on("2026-01-01")
    with pytest.raises(ValueError, match="no engine_upgrade revision to"):
        r.engine_upgrade_to("9.9.9")


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
    others = sorted(set(keys) - excluded)
    restored = draw(st.sets(st.sampled_from(others)) if others else st.just(set()))
    return changes, excluded, restored


@settings(max_examples=300, deadline=None)
@given(_upgrade_revisions())
def test_engine_upgrade_partition_is_exact_and_disjoint(revision):
    """Invariant: every change lands in exactly one group; new exclusions are
    the changes to excluded outputs, restorations the changes to outputs the
    upgrade returned to scoring; a scored change lies beyond the exact-match
    tolerance ($1, or any change of a 0/1 flag) and a within-tolerance change
    inside it."""
    from policybench.paper_results import partition_engine_upgrade_changes

    changes, excluded, restored = revision
    partition = partition_engine_upgrade_changes(changes, excluded, restored)
    assert set(partition) == {
        "scored_changes",
        "within_tolerance",
        "new_exclusions",
        "restored",
    }
    placed = [id(change) for group in partition.values() for change in group]
    assert sorted(placed) == sorted(id(change) for change in changes)
    assert len(placed) == len(set(placed)) == len(changes)
    for change in partition["new_exclusions"]:
        assert (change["scenario_id"], change["variable"]) in excluded
    for change in partition["restored"]:
        assert (change["scenario_id"], change["variable"]) in restored
    for name in ("scored_changes", "within_tolerance"):
        for change in partition[name]:
            key = (change["scenario_id"], change["variable"])
            assert key not in excluded and key not in restored
            moved = abs(change["regenerated"] - change["previous"])
            limit = 1 if change["variable"] in _AMOUNT_OUTPUTS else 0
            assert (moved > limit) == (name == "scored_changes")
    # Without restorations the partition is the three groups it always was.
    if not restored:
        assert partition["restored"] == []
        assert partition == partition_engine_upgrade_changes(changes, excluded)


def test_engine_upgrade_partition_refuses_an_output_both_excluded_and_restored():
    from policybench.paper_results import partition_engine_upgrade_changes

    change = {
        "scenario_id": "scenario_001",
        "variable": "snap",
        "previous": 0.0,
        "regenerated": 10.0,
    }
    key = ("scenario_001", "snap")
    with pytest.raises(ValueError, match="both excluded and restored"):
        partition_engine_upgrade_changes([change], {key}, {key})


_DAY = st.integers(min_value=1, max_value=28)


def _day(n: int) -> str:
    return f"2026-10-{n:02d}"


@st.composite
def _exclusion_histories(draw):
    """A random reference history: engine upgrades on distinct days, exclusion
    records decided on any day, some of them removed by a later upgrade that
    lists the removed record, and convention revisions in between. Returns the
    sidecar revisions, the exclusion record left at the end, and for each
    upgrade the outputs excluded just before it and once it was decided."""
    days = sorted(draw(st.sets(_DAY, min_size=1, max_size=4)))
    outputs = draw(
        st.lists(
            st.integers(min_value=0, max_value=60).map(
                lambda n: (f"scenario_{n:03d}", "snap")
            ),
            unique=True,
            max_size=25,
        )
    )
    records = []
    for key in outputs:
        decided = draw(_DAY)
        later = [i for i, day in enumerate(days) if day > decided]
        removed_by = draw(st.sampled_from([None, *later]))
        record = {
            "scenario_id": key[0],
            "variable": key[1],
            "decided_on": _day(decided),
        }
        records.append((record, removed_by))
    revisions = []
    for index, day in enumerate(days):
        if draw(st.booleans()):
            revisions.append({"kind": "convention", "date": _day(day), "changed": []})
        revisions.append(
            {
                "kind": "engine_upgrade",
                "date": _day(day),
                "engine_version": f"policyengine-us 2.{index + 1}.0",
                "previous_engine_version": f"policyengine-us 2.{index}.0",
                "excluded_outputs_rechecked": [],
                "regenerated_exclusions": [
                    {
                        "scenario_id": record["scenario_id"],
                        "variable": record["variable"],
                        "record": record,
                    }
                    for record, removed_by in records
                    if removed_by == index
                ],
                "changed": [],
            }
        )
    current = [record for record, removed_by in records if removed_by is None]
    truth = []
    for index, day in enumerate(days):
        date = _day(day)
        before = {
            (rec["scenario_id"], rec["variable"])
            for rec, removed_by in records
            if rec["decided_on"] < date and (removed_by is None or removed_by >= index)
        }
        after = {
            (rec["scenario_id"], rec["variable"])
            for rec, removed_by in records
            if rec["decided_on"] <= date and (removed_by is None or removed_by > index)
        }
        restored = {
            (rec["scenario_id"], rec["variable"])
            for rec, removed_by in records
            if removed_by == index
        }
        truth.append((before, after, restored))
    return revisions, current, truth


@settings(max_examples=300, deadline=None)
@given(_exclusion_histories())
def test_each_upgrade_sees_the_exclusion_record_as_it_stood(history):
    """Invariant: from the sidecar and the exclusion record left at the end,
    each upgrade recovers the outputs excluded just before it and once it was
    decided, whatever later upgrades restored and whatever later records
    added; a record decided after an upgrade never counts at that upgrade."""
    from policybench.paper_results import engine_upgrades_from

    revisions, current, truth = history
    upgrades = engine_upgrades_from(revisions, current)
    assert [u.revision for u in upgrades] == [
        rev for rev in revisions if rev["kind"] == "engine_upgrade"
    ]
    for upgrade, (before, after, restored) in zip(upgrades, truth, strict=True):
        assert upgrade.excluded_before == before
        assert upgrade.excluded == after
        assert upgrade.restored == restored
        assert upgrade.restored <= upgrade.excluded_before - upgrade.excluded


def test_an_upgrade_that_changes_an_output_it_kept_excluded_is_refused():
    """Rule 5: an excluded output keeps the value it was decided on, so an
    upgrade whose changed list moves an output excluded before and after it is
    refused rather than counted as a new exclusion."""
    from policybench.paper_results import engine_upgrades_from

    record = {
        "scenario_id": "scenario_001",
        "variable": "snap",
        "decided_on": "2026-09-22",
    }
    change = {
        "scenario_id": "scenario_001",
        "variable": "snap",
        "previous": 10.0,
        "regenerated": 20.0,
    }
    revision = {
        "kind": "engine_upgrade",
        "date": "2026-09-29",
        "engine_version": "policyengine-us 2.15.17",
        "previous_engine_version": "policyengine-us 1.755.4",
        "changed": [change],
    }
    (upgrade,) = engine_upgrades_from([revision], [record])
    with pytest.raises(ValueError, match="changes outputs it kept excluded"):
        upgrade.partition
    # Decided on the upgrade's day, the same change is a new exclusion.
    (upgrade,) = engine_upgrades_from(
        [revision], [{**record, "decided_on": "2026-09-29"}]
    )
    assert upgrade.partition["new_exclusions"] == [change]


def test_engine_upgrades_refuse_a_broken_engine_chain():
    from policybench.paper_results import engine_upgrades_from

    revisions = [
        {
            "kind": "engine_upgrade",
            "date": "2026-09-29",
            "engine_version": "policyengine-us 2.15.17",
            "previous_engine_version": "policyengine-us 1.755.4",
            "changed": [],
        },
        {
            "kind": "engine_upgrade",
            "date": "2026-10-09",
            "engine_version": "policyengine-us 2.37.2",
            "previous_engine_version": "policyengine-us 2.17.0",
            "changed": [],
        },
    ]
    with pytest.raises(ValueError, match="does not start from"):
        engine_upgrades_from(revisions, [])


@st.composite
def _reference_histories(draw):
    """Initial references and dated revisions that each change some of them,
    with the references after each date."""
    keys = [(f"scenario_{n:03d}", "snap") for n in range(8)]
    values = {key: draw(st.floats(0, 1e5, allow_nan=False)) for key in keys}
    days = sorted(draw(st.lists(_DAY, min_size=1, max_size=5)))
    snapshots = {_day(0): dict(values)}
    revisions = []
    for day in days:
        changed = []
        for key in draw(st.lists(st.sampled_from(keys), unique=True, max_size=4)):
            regenerated = draw(st.floats(0, 1e5, allow_nan=False))
            changed.append(
                {
                    "scenario_id": key[0],
                    "variable": key[1],
                    "previous": values[key],
                    "regenerated": regenerated,
                }
            )
            values[key] = regenerated
        revisions.append(
            {"kind": "engine_upgrade", "date": _day(day), "changed": changed}
        )
        snapshots[_day(day)] = dict(values)
    return revisions, values, snapshots


@settings(max_examples=200, deadline=None)
@given(_reference_histories())
def test_references_as_of_undo_every_later_revision(history):
    """Invariant: the references as of a date are the current references with
    every later revision's changes undone, newest first; as of the last
    revision's date they are the current references."""
    from policybench.paper_results import references_as_of

    revisions, current, snapshots = history
    for date, snapshot in snapshots.items():
        assert references_as_of(current, revisions, date) == snapshot


def test_references_as_of_refuse_a_revision_the_references_do_not_match():
    from policybench.paper_results import references_as_of

    key = ("scenario_000", "snap")
    revision = {
        "kind": "engine_upgrade",
        "date": "2026-10-09",
        "changed": [
            {
                "scenario_id": key[0],
                "variable": key[1],
                "previous": 1.0,
                "regenerated": 2.0,
            }
        ],
    }
    with pytest.raises(ValueError, match="does not end at"):
        references_as_of({key: 3.0}, [revision], "2026-10-05")


_VERSIONS = st.tuples(st.integers(0, 3), st.integers(0, 200), st.integers(0, 30)).map(
    lambda parts: ".".join(map(str, parts))
)


@settings(max_examples=300, deadline=None)
@given(st.dictionaries(_VERSIONS, st.integers(1, 2000), max_size=5))
def test_excluded_outputs_by_engine_phrase_names_each_engine_once(counts):
    """Invariant: the phrase has one clause per engine, oldest release first by
    version number (not string order), whose counts are the given ones; only
    the first clause names policyengine-us."""
    from policybench.paper_results import engine_version_count_phrase

    phrase = engine_version_count_phrase(counts)
    if not counts:
        assert phrase == ""
        return
    clauses = phrase.split(", ")
    parsed = [
        re.fullmatch(r"([\d,]+) computed with policyengine-us ([\d.]+)", clauses[0])
    ]
    parsed += [re.fullmatch(r"([\d,]+) with ([\d.]+)", c) for c in clauses[1:]]
    assert all(parsed), clauses
    versions = [m.group(2) for m in parsed]
    assert versions == sorted(counts, key=lambda v: tuple(map(int, v.split("."))))
    assert [int(m.group(1).replace(",", "")) for m in parsed] == [
        counts[v] for v in versions
    ]


# --- The 2026-10-05 review of release dashboard-data-20260930 -----------------

# Release dashboard-data-20260930's commit (#187), the base the review read and
# the next release builds on (docs/release_20261006/spec.json). CI checks out
# full history.
BASE_COMMIT = "8b4c0ca146bb6f66deba6ce24009d49d70d92df2"


def _git_blob(path: str, commit: str = BASE_COMMIT) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{path}"],
        capture_output=True,
    )
    assert result.returncode == 0, (
        f"cannot read {path} at {commit[:12]} (fetch full history): "
        f"{result.stderr.decode().strip()}"
    )
    return result.stdout


@functools.cache
def _release_20260930() -> PaperResults:
    """PaperResults over release 20260930's own committed artifacts, read from
    git at its commit: manifest, payload, exclusion record and annotations."""
    base = PaperResults()
    run = f"paper/snapshot/20260501/runs/{r.us_run_label}"
    base.manifest = json.loads(_git_blob("paper/snapshot/20260501/manifest.json"))
    base.dashboard = json.loads(gzip.decompress(_git_blob(f"{run}/data.json.gz")))
    with tempfile.TemporaryDirectory() as scratch:
        record = Path(scratch) / "reference_exclusions.json"
        record.write_bytes(_git_blob(f"{run}/reference_exclusions.json"))
        base.reference_exclusions = load_reference_exclusions(record)
    annotation_dir = base.manifest["audit_annotation_artifacts"]["path"]
    rows = _git_blob(f"{annotation_dir}/us_audit_row_annotations.csv").decode()
    base._audit_rows = list(csv.DictReader(io.StringIO(rows)))
    return base


# Release dashboard-data-20261006's commit (#202): the last release whose
# references are on policyengine-us 2.15.17, before the next release moves them.
RELEASE_20261006_COMMIT = "9ce4ade8382962a9134860c23f56d92509b5e57f"


@functools.cache
def _release_20261006() -> PaperResults:
    """PaperResults over release 20261006's reference records, read from git
    at its commit: manifest, sidecar revisions, exclusions and references."""
    run = f"paper/snapshot/20260501/runs/{r.us_run_label}"

    def blob(path: str) -> bytes:
        return _git_blob(path, RELEASE_20261006_COMMIT)

    base = PaperResults()
    base.manifest = json.loads(blob("paper/snapshot/20260501/manifest.json"))
    base.reference_revisions = json.loads(
        blob(f"{run}/reference_outputs.csv.meta.json")
    )["revisions"]
    with tempfile.TemporaryDirectory() as scratch:
        record = Path(scratch) / "reference_exclusions.json"
        record.write_bytes(blob(f"{run}/reference_exclusions.json"))
        base.reference_exclusions = load_reference_exclusions(record)
    # Parsed with pandas, as paper_results parses the frozen references (its
    # float parser differs from float() in the last place for three values,
    # which the review sweeps' exact baseline checks would refuse).
    rows = pd.read_csv(io.BytesIO(blob(f"{run}/reference_outputs.csv")))
    base.frozen_references = {
        (row.scenario_id, row.variable): float(row.value)
        for row in rows.itertuples(index=False)
    }
    return base


@functools.cache
def _release_20261006_full() -> PaperResults:
    """PaperResults over every release 20261006 artifact these tests read,
    from git at its commit: the reference records (_release_20261006) and its
    manifest, payload, serving configuration, row annotations and
    adjudication record. Its own differential tests run on it, since the
    working tree holds a later release."""
    base = _release_20261006()
    run = f"paper/snapshot/20260501/runs/{r.us_run_label}"

    def blob(path: str) -> bytes:
        return _git_blob(path, RELEASE_20261006_COMMIT)

    base.dashboard = json.loads(gzip.decompress(blob(f"{run}/data.json.gz")))
    base.serving_config = json.loads(
        blob("paper/snapshot/20260501/model_serving_config.json")
    )
    annotation_dir = base.manifest["audit_annotation_artifacts"]["path"]
    rows = blob(f"{annotation_dir}/us_audit_row_annotations.csv").decode()
    base._audit_rows = list(csv.DictReader(io.StringIO(rows)))
    record = json.loads(blob(f"{annotation_dir}/us_adjudications.json"))
    base.review_adjudications = [
        entry
        for entry in record["adjudications"]
        if entry.get("adjudicated_on") == REVIEW_DATE
    ]
    return base


def test_release_20260930s_own_counts_rebuild_from_git():
    """The counts these tests pinned for release 20260930, recomputed from its
    committed artifacts rather than from the working tree."""
    base = _release_20260930()
    assert base.manifest["published_dashboard_artifact"]["tag"] == (
        "dashboard-data-20260930"
    )
    assert base.excluded_output_count == 56
    assert base.excluded_output_households_phrase == "39 households"
    assert base.unlisted_input_exclusion_count == 28
    assert base.engine_defect_exclusion_count == 28
    assert base.excluded_outputs_by_engine_version == {"1.755.4": 52, "2.15.17": 4}
    assert {row["n"] for row in base.model_stats} == {1928}
    assert base.audit_annotated_row_count == 7_860
    assert base.exact_match_miss_count == 7_856
    assert base.annotated_exact_miss_count == 7_856
    assert base.annotated_exact_hit_count == 4
    assert base.unannotated_below_full_bounded_score_count == 2_107
    assert base.parse_contract_failure_counts == Counter(
        {"kimi-k2.6": 390, "glm-5.2": 133, "glm-5.3": 71, "kimi-k3": 58}
    )
    assert base.excluded_output_annotation_row_count == 2_111
    assert base.prompt_ambiguity_row_count == 820
    assert base.audit_developer_adjudications["cases"] == 69
    assert base.model_response_date == "2026-06-12 to 2026-09-30"


def test_the_review_moves_the_paper_counts_by_its_eight_outputs_alone():
    """Differential: each count the paper renders is release 20260930's,
    computed from its own committed files, moved by exactly the rows on the
    outputs the review excluded. Release 20261006's own files, from git: the
    working tree holds a later release."""
    r = _release_20261006_full()
    base = _release_20260930()
    review = r.review_exclusion_keys
    assert len(review) == 8
    assert r._excluded_output_keys == base._excluded_output_keys | review
    assert not base._excluded_output_keys & review

    def on_review(rows):
        return [row for row in rows if (row["scenario_id"], row["variable"]) in review]

    # The base scored those rows; the payload keeps them, unscored.
    base_rows = on_review(base._scored_prediction_rows)
    assert len(base_rows) == 8 * r.n_models
    assert all(row["scored"] is False for row in on_review(r._scenario_prediction_rows))
    misses = {r._prediction_row_key(row) for row in base_rows if row["exact"] < 100}
    hits_below_full = {
        r._prediction_row_key(row)
        for row in base_rows
        if row["exact"] == 100 and row["boundedScore"] < 100
    }
    annotated = {r._prediction_row_key(row) for row in on_review(base._audit_rows)}
    assert annotated == misses

    assert r.audit_annotated_row_count == base.audit_annotated_row_count - len(
        annotated
    )
    assert r.exact_match_miss_count == base.exact_match_miss_count - len(misses)
    assert r.annotated_exact_hit_count == base.annotated_exact_hit_count
    assert r.unannotated_below_full_bounded_score_count == (
        base.unannotated_below_full_bounded_score_count - len(hits_below_full)
    )
    parse_failures = Counter(
        row["model"]
        for row in base_rows
        if row.get("failureSource") == "parse_contract_failure"
    )
    assert r.parse_contract_failure_counts == (
        base.parse_contract_failure_counts - parse_failures
    )
    assert sum(parse_failures.values()) == 8
    assert r.excluded_output_annotation_row_count == (
        base.excluded_output_annotation_row_count + len(annotated)
    )
    # Every annotated miss on the eight is relabeled to the exclusion's class
    # except the answers that never parsed.
    assert r.prompt_ambiguity_row_count == (
        base.prompt_ambiguity_row_count + len(annotated) - 8
    )
    assert r.excluded_output_count == base.excluded_output_count + 8
    assert r.unlisted_input_exclusion_count == base.unlisted_input_exclusion_count + 8
    assert r.engine_defect_exclusion_count == base.engine_defect_exclusion_count
    assert r.audit_developer_adjudications["cases"] == (
        base.audit_developer_adjudications["cases"] + len(r.review_adjudications)
    )
    assert r.n_scored_outputs == base.n_scored_outputs - 8


def test_the_review_sweeps_move_exactly_the_records_the_review_added():
    """The review's records are what its sweeps moved: every output a sweep
    moves beyond the tolerance is one of its eight records or was already
    excluded, and no still-scored output moves by any amount."""
    assert r.review_date == REVIEW_DATE == "2026-10-05"
    assert r.review_sweep_count == len(REVIEW_SWEEPS) == 3
    assert r.review_sweep_count_word == "three"
    assert r.review_new_exclusion_count == len(r.review_adjudications) == 8
    assert r.review_new_exclusion_count_word == "eight"
    # The review ran on the engine the 2026-09-29 upgrade moved to, the
    # reference engine then, whatever engine later releases move to.
    assert r.review_exclusion_engine_version == r.september_upgrade.engine_version
    assert set(r.review_newly_excluded_moved_outputs) == r.review_exclusion_keys
    assert r.review_sweep_partition["scored_beyond_tolerance"] == []
    assert r.review_sweep_partition["scored_within_tolerance"] == []
    assert r.review_still_scored_moves_phrase == "no output that is still scored"
    federal = "federal_income_tax_before_refundable_credits"
    assert r.review_already_excluded_moved_outputs == [
        ("scenario_078", federal),
        ("scenario_120", federal),
    ]
    assert r.review_already_excluded_moved_count_word == "two"
    assert r.review_sweep_moved_outputs("salt_withholding") == [
        ("scenario_022", federal),
        ("scenario_078", federal),
        ("scenario_081", federal),
        ("scenario_114", federal),
        ("scenario_120", federal),
    ]
    assert r.review_sweep_moved_count_word("salt_withholding") == "five"
    assert r.review_sweep_newly_excluded_count_word("salt_withholding") == "three"
    assert r.review_sweep_already_excluded_count_word("salt_withholding") == "two"
    assert r.review_sweep_moved_outputs("medicare_part_b") == [
        ("scenario_114", federal),
        ("scenario_114", "state_income_tax_before_refundable_credits"),
    ]
    assert r.review_sweep_moved_household_count_word("medicare_part_b") == "one"
    assert r.review_sweep_moved_outputs("payroll_optional_shares") == [
        (f"scenario_{n}", "payroll_tax") for n in ("032", "043", "081", "082")
    ]
    assert r.review_sweep_moved_count_word("payroll_optional_shares") == "four"
    assert r.review_sweep_newly_excluded_count_word("payroll_optional_shares") == (
        "four"
    )


def test_the_review_swept_release_20260930s_references_and_exclusions():
    """Each sweep covers every output, carries release 20260930's exclusions
    and references, and its baseline reproduces every reference that release
    scored (the paper's count)."""
    base = _release_20260930()
    assert r.excluded_before_review_keys == base._excluded_output_keys
    assert r.review_scored_before_count == 1_984 - 56 == 1_928
    assert r.review_scored_before_count_fmt == "1,928"
    for name, frame in r.review_sweep_rows.items():
        assert len(frame) == 1_984, name
        recorded = {
            (row.scenario_id, row.variable)
            for row in frame.itertuples(index=False)
            if row.excluded
        }
        assert recorded == base._excluded_output_keys, name


def test_the_review_records_quote_their_sweeps_values():
    """Each record's frozen value is the sweep's reference, and its
    alternative is a value one of its sweeps computed for that output."""
    values: dict[tuple[str, str], list[float]] = {}
    references: dict[tuple[str, str], float] = {}
    for name, (_, baseline, readings) in REVIEW_SWEEPS.items():
        for row in r.review_sweep_rows[name].itertuples(index=False):
            key = (row.scenario_id, row.variable)
            references[key] = float(row.reference)
            values.setdefault(key, []).extend(
                float(getattr(row, reading)) for reading in readings
            )
    for record in r.review_exclusions:
        key = (record["scenario_id"], record["variable"])
        assert record["frozen_value"] == pytest.approx(references[key], abs=0.005)
        assert any(
            record["alternative_value"] == pytest.approx(value, abs=0.005)
            for value in values[key]
        ), key
        assert record["reason_code"] == "reference_depends_on_unlisted_input"


def test_no_judge_had_flagged_the_reviews_outputs():
    """The paper says no judge flagged the eight: each adjudication keeps a
    judge verdict of a model error with no reference-suspect flag, in release
    20261006, which recorded them (a later re-judge may reclassify a case)."""
    r = _release_20261006_full()
    assert r.review_judge_flagged_count == 0
    assert {(e["scenario_id"], e["variable"]) for e in r.review_adjudications} == (
        r.review_exclusion_keys
    )
    for entry in r.review_adjudications:
        assert entry["judge_failure_source"] == "llm_error"
        assert entry["judge_reference_suspect"] is False
        assert entry["excluded_from_scoring"] is True
    # The manifest's tally of judge-flagged cases does not move.
    base = _release_20260930()
    assert r.audit_flagged_by_verdict == base.audit_flagged_by_verdict


def test_marylands_withholding_estimate_moves_only_an_excluded_federal_output():
    """The paper: policyengine-us reads Maryland's withholding allowance only
    in its withholding estimate, and the one Maryland federal output that
    estimate moves is excluded (reference_audit/2026-10-05)."""
    frame = r.review_sweep_rows["salt_withholding"]
    _, baseline, readings = REVIEW_SWEEPS["salt_withholding"]
    maryland = frame[frame["state"] == "MD"]
    moved = {
        (row.scenario_id, row.variable)
        for row in maryland.itertuples(index=False)
        if any(getattr(row, reading) != getattr(row, baseline) for reading in readings)
    }
    assert moved == {("scenario_078", "federal_income_tax_before_refundable_credits")}
    assert moved <= r.excluded_before_review_keys
    paper = re.sub(r"\s+", " ", (ROOT / "paper/index.qmd").read_text())
    assert "the one Maryland federal output that estimate moves is excluded" in paper
    assert (
        "which reaches federal tax through the state and local tax deduction."
        not in (paper)
    )


def test_the_paper_dates_the_response_window_from_the_last_answer():
    """Differential: the window the paper's snapshot table prints (the
    manifest's) is the one scripts/freeze_snapshot.py computes from the frozen
    predictions, ending on the last answer's UTC date, not the release's."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import freeze_snapshot

    start, end = r.model_response_date.split(" to ")
    predictions = SNAPSHOT_DIR / "runs" / r.us_run_label / "predictions.csv.gz"
    assert freeze_snapshot.model_response_window(predictions, start) == (
        r.model_response_date
    )
    # The last answer predates the freeze; release 20260930, before the
    # window was derived, ended it on its snapshot date (2026-09-30), and
    # release 20261006 on its last answer (2026-09-29).
    assert end <= r.snapshot_date
    assert _release_20260930().model_response_date.endswith("2026-09-30")
    assert _release_20261006_full().model_response_date.endswith("2026-09-29")


def _review_moves():
    outputs = st.tuples(
        st.integers(min_value=0, max_value=12).map(lambda n: f"scenario_{n:03d}"),
        st.sampled_from(_AMOUNT_OUTPUTS + _FLAG_OUTPUTS),
    )

    @st.composite
    def build(draw):
        moves = []
        for scenario_id, variable in draw(st.lists(outputs, max_size=30)):
            if variable in _FLAG_OUTPUTS:
                baseline = draw(st.sampled_from((0.0, 1.0)))
                recomputed = 1.0 - baseline
            else:
                baseline = draw(st.floats(0, 1e5, allow_nan=False))
                recomputed = baseline + draw(
                    st.one_of(
                        st.floats(-2, 2, allow_nan=False), st.floats(-1e4, 1e4)
                    ).filter(lambda d: d != 0)
                )
            sweep = draw(st.sampled_from(sorted(REVIEW_SWEEPS)))
            moves.append((sweep, scenario_id, variable, baseline, recomputed))
        before = draw(st.sets(outputs, max_size=6))
        added = draw(st.sets(outputs, max_size=6))
        return moves, before, before | added

    return build()


@settings(max_examples=300, deadline=None)
@given(_review_moves())
def test_review_sweep_partition_is_exact_and_disjoint(case):
    """Invariant: every move lands in exactly one group; a move of an output
    excluded before is excluded_before, of an output the review excluded
    newly_excluded, and of a still-scored output scored beyond or within the
    exact-match tolerance by the size of the move."""
    from policybench.paper_results import moves_beyond_tolerance

    moves, before, now = case
    partition = partition_review_sweep_moves(moves, before, now)
    assert set(partition) == {
        "excluded_before",
        "newly_excluded",
        "scored_beyond_tolerance",
        "scored_within_tolerance",
    }
    placed = Counter(key for group in partition.values() for key in group)
    assert placed == Counter((m[0], m[1], m[2]) for m in moves)
    # The same output can move within the tolerance under one reading and
    # beyond it under another, so each move is placed on its own.
    expected = {name: Counter() for name in partition}
    for sweep, scenario_id, variable, baseline, recomputed in moves:
        output = (scenario_id, variable)
        if output in before:
            name = "excluded_before"
        elif output in now:
            name = "newly_excluded"
        elif moves_beyond_tolerance(variable, baseline, recomputed):
            name = "scored_beyond_tolerance"
        else:
            name = "scored_within_tolerance"
        expected[name][(sweep, scenario_id, variable)] += 1
    assert {name: Counter(keys) for name, keys in partition.items()} == expected


# --- The 2026-10-06 rulings and the second upgrade, on real builds -------------

REHEARSAL_BUILD = ROOT / "results/local/rehearsal-2372/build"


def _rehearsal_tree():
    """The 2.37.2 rehearsal build's reference records (local only): a real
    second upgrade, as build_references_upgrade.py writes it."""
    import tomllib

    import pandas as pd

    from tests.second_engine_upgrade import Tree

    if not (REHEARSAL_BUILD / "reference_outputs.csv.meta.json").is_file():
        pytest.skip("needs the local 2.37.2 rehearsal build")
    frame = pd.read_csv(REHEARSAL_BUILD / "reference_outputs.csv")
    return Tree(
        sidecar=json.loads(
            (REHEARSAL_BUILD / "reference_outputs.csv.meta.json").read_text()
        ),
        exclusions=json.loads(
            (REHEARSAL_BUILD / "reference_exclusions.json").read_text()
        )["exclusions"],
        references={
            (row.scenario_id, row.variable): float(row.value)
            for row in frame.itertuples(index=False)
        },
        manifest=json.loads(
            (ROOT / "paper/snapshot/20260501/manifest.json").read_text()
        ),
        pins=tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
            "dependencies"
        ],
    )


def test_the_rulings_and_the_second_upgrade_count_on_the_rehearsal_build():
    """On the real 2.37.2 build: the 2026-10-06 rulings decided ten records
    (eight under d1022, two under d994) on 2.15.17; the upgrade regenerated
    four of them (the adversary's engine defects) and keeps six; it restores
    seven excluded outputs in all, changes one scored reference beyond the
    tolerance, newly excludes two and rechecks 22."""
    from tests.second_engine_upgrade import paper_results_for

    results = paper_results_for(_rehearsal_tree())
    assert results.ruling_date == "2026-10-06"
    assert results.ruled_exclusion_count == 10
    assert results.ruled_exclusion_count_word == "ten"
    assert results.ruled_decision_count("d1022") == 8
    assert results.ruled_decision_count_word("d994") == "two"
    assert results.ruled_regenerated_count == 4
    assert results.ruled_kept_count == 6
    assert results.ruled_exclusion_engine_version == "2.15.17"
    regenerated = {
        record["root_cause"]
        for record in results.ruled_records
        if (record["scenario_id"], record["variable"])
        not in {(e["scenario_id"], e["variable"]) for e in results.reference_exclusions}
    }
    assert regenerated == {
        "az_standard_deduction_indexing",
        "oh_medical_deduction_premiums",
        "co_sales_tax_refund_surplus",
        "ny_cdcc_606_c2",
    }
    last = results.last_engine_upgrade
    assert (last.previous_engine_version, last.engine_version) == ("2.15.17", "2.37.2")
    assert results.engine_upgrade_restored_count_word == "seven"
    assert results.engine_upgrade_scored_change_count_word == "one"
    assert results.engine_upgrade_new_exclusion_count_word == "two"
    assert results.engine_upgrade_rechecked_count == 22


def test_a_ruled_record_must_name_its_ruling():
    from tests.second_engine_upgrade import paper_results_for, release_20261006

    tree = release_20261006()
    unnamed = {
        **tree.exclusions[0],
        "scenario_id": "scenario_999",
        "decided_on": "2026-10-06",
    }
    unnamed.pop("decision", None)
    results = paper_results_for(
        type(tree)(
            sidecar=tree.sidecar,
            exclusions=[*tree.exclusions, unnamed],
            references=tree.references,
            manifest=tree.manifest,
            pins=tree.pins,
        )
    )
    with pytest.raises(ValueError, match="name no ruling"):
        results.ruled_records


@pytest.mark.parametrize(
    "n, word", [(0, "no"), (7, "seven"), (10, "ten"), (11, "11"), (1234, "1,234")]
)
def test_a_count_reads_as_a_word_up_to_ten(n, word):
    from policybench.paper_results import count_word

    assert count_word(n) == word


def test_the_upgrade_sentences_name_what_the_sidecar_records():
    """The paper names the last upgrade's fixes, change and new exclusions
    from the sidecar: every restored output is counted once under its root
    cause's name with the upstream pull request its entry names, every scored
    change beyond the tolerance under its cause's, and every new exclusion
    under its record's unlisted input."""
    from policybench.paper_results import CHANGE_CAUSE_LABELS, ROOT_CAUSE_LABELS

    last = r.last_engine_upgrade
    fixes = r.engine_upgrade_restored_fixes
    entries = last.revision["regenerated_exclusions"]
    assert sum(count for _, count, _ in fixes) == len(entries)
    assert len(entries) == r.engine_upgrade_restored_count
    sentence = r.engine_upgrade_restored_sentence
    for entry in entries:
        for cause in entry["record"]["root_cause"].split("+"):
            assert ROOT_CAUSE_LABELS[cause] in sentence
        primary = entry["upstream"].split("; related")[0]
        numbers = re.findall(r"policyengine-us#(\d+)", primary)
        assert numbers and all(f"#{n}" in sentence for n in numbers)
    for label, count, prs in fixes:
        assert f"{label} (policyengine-us #{prs[0]}" in sentence
    changes = last.partition["scored_changes"]
    assert len(changes) == r.engine_upgrade_scored_change_count
    for change in changes:
        assert CHANGE_CAUSE_LABELS[change["cause"]] in (
            r.engine_upgrade_scored_change_sentence
        )
    added = {
        (c["scenario_id"], c["variable"]) for c in last.partition["new_exclusions"]
    }
    records = [
        e for e in r.reference_exclusions if (e["scenario_id"], e["variable"]) in added
    ]
    assert len(records) == r.engine_upgrade_new_exclusion_count == len(added)
    for record in records:
        assert record["unlisted_input"] in r.engine_upgrade_new_exclusion_sentence
    paper = (ROOT / "paper/index.qmd").read_text()
    for accessor in (
        "engine_upgrade_restored_sentence",
        "engine_upgrade_scored_change_sentence",
        "engine_upgrade_new_exclusion_sentence",
    ):
        assert f"`{{python}} r.{accessor}`" in paper
        assert f"{{r.{accessor}}}" in paper
    assert "`{python} r.engine_upgrade_restored_target_sentence`" in paper
    assert "RELEASE AUTHOR" not in paper


def _MOCK_fix_modules_target(entry: dict, engine: str = "policyengine-us 9.9.9"):
    """MOCK: turn a restored output's target into the fix-module kind, with a
    record value and a defective engine value both beyond the tolerance."""
    value = entry["regenerated"]
    entry["record"]["alternative_value"] = value + 50.0
    entry["target"] = {
        "kind": "fix_modules",
        "value": value,
        "engine": engine,
        "engine_value": value + 200.0,
    }


def _native_fix_modules() -> tuple[set[int], str]:
    """The frozen sidecar's restored entries already held to fix modules, and
    the engine a MOCK target must name to sit beside them (the sentence names
    one engine)."""
    entries = r.last_engine_upgrade.revision["regenerated_exclusions"]
    native = {
        index
        for index, entry in enumerate(entries)
        if entry["target"]["kind"] == "fix_modules"
    }
    engines = {entries[index]["target"]["engine"] for index in native}
    assert len(engines) <= 1, engines
    return native, next(iter(engines), "policyengine-us 9.9.9")


def _with_restored(edit) -> PaperResults:
    """MOCK edit of the frozen sidecar's restored entries."""
    results = PaperResults()
    results.reference_revisions = deepcopy(r.reference_revisions)
    edit(results.reference_revisions[-1]["regenerated_exclusions"])
    return results


def test_the_restored_target_sentence_follows_the_frozen_sidecar():
    """Every restored output is counted under how its corrected value is
    known, and lands within its tolerance of that value."""
    from policybench.paper_results import moves_beyond_tolerance

    targets = r.engine_upgrade_restored_targets
    entries = r.last_engine_upgrade.revision["regenerated_exclusions"]
    assert len(targets["record"]) + len(targets["fix_modules"]) == len(entries)
    for entry in entries:
        assert abs(entry["regenerated"] - entry["target"]["value"]) <= 1.0
    for entry in targets["record"]:
        assert entry["target"]["value"] == entry["record"]["alternative_value"]
    for entry in targets["fix_modules"]:
        target = entry["target"]
        assert moves_beyond_tolerance(
            entry["variable"], target["engine_value"], target["value"]
        )
    sentence = r.engine_upgrade_restored_target_sentence
    assert sentence.count("within $1") == (2 if targets["fix_modules"] else 1)
    for entry in targets["fix_modules"]:
        assert entry["target"]["engine"] in sentence


@given(st.data())
@settings(max_examples=40, deadline=None)
def test_the_restored_target_sentence_counts_each_kind(data):
    """MOCK edits: whichever restored outputs are held to fix modules, the
    sentence counts both kinds, names the fix modules' engine and never
    starts with a numeral."""
    from policybench.paper_results import count_word

    total = r.engine_upgrade_restored_count
    assume(total > 0)
    chosen = data.draw(st.sets(st.integers(0, total - 1)))
    native, engine = _native_fix_modules()
    held = chosen | native

    def edit(entries):
        for index in chosen:
            _MOCK_fix_modules_target(entries[index], engine)

    results = _with_restored(edit)
    targets = results.engine_upgrade_restored_targets
    assert len(targets["fix_modules"]) == len(held)
    assert len(targets["record"]) == total - len(held)
    sentence = results.engine_upgrade_restored_target_sentence
    assert not sentence[0].isdigit()
    assert (engine in sentence) == bool(held)
    if held and len(held) < total:
        assert sentence.startswith(f"Of the {count_word(total)}, ")
        other = "one" if len(held) == 1 else count_word(len(held))
        assert f"The other {other} " in sentence
        kept = total - len(held)
        assert f", {count_word(kept)} land" in sentence
    elif held:
        assert sentence.startswith(("They are held to", "It is held to"))
    else:
        assert sentence == r.engine_upgrade_restored_target_sentence


def test_a_flag_held_to_fix_modules_that_move_it_is_described():
    """MOCK edit: on a 0/1 flag, fix modules that move it from 0 to 1 show the
    defect, as the builder's beyond() rule says, though the move is not more
    than $1."""

    native, engine = _native_fix_modules()

    def flag(entries):
        entry = entries[0]
        entry["variable"] = "head_medicaid_eligible"
        entry["regenerated"] = 1.0
        entry["record"]["alternative_value"] = 0.0
        entry["target"] = {
            "kind": "fix_modules",
            "value": 1.0,
            "engine": engine,
            "engine_value": 0.0,
        }

    results = _with_restored(flag)
    held = results.engine_upgrade_restored_targets["fix_modules"]
    assert len(held) == len(native | {0})
    assert any(entry["variable"] == "head_medicaid_eligible" for entry in held)
    assert engine in results.engine_upgrade_restored_target_sentence


def test_a_restored_output_off_its_target_stops_the_sentence():
    """MOCK edits: each way a restored entry can contradict the sentence is
    refused instead of described."""

    def off_target(entries):
        entries[0]["regenerated"] = entries[0]["target"]["value"] + 1.5

    def loose(entries):
        entries[0]["tolerance"] = 2.0

    def not_the_records(entries):
        entries[0]["record"]["alternative_value"] += 0.25

    def no_defect(entries):
        _MOCK_fix_modules_target(entries[0])
        entries[0]["target"]["engine_value"] = entries[0]["target"]["value"]

    def flag_off_its_target(entries):
        entries[0]["variable"] = "head_medicaid_eligible"
        entries[0]["target"]["value"] = 1.0
        entries[0]["record"]["alternative_value"] = 1.0
        entries[0]["regenerated"] = 0.0

    def unknown_kind(entries):
        entries[0]["target"]["kind"] = "MOCK_kind"

    for edit, message in (
        (off_target, "is restored off its target"),
        (loose, "is restored on a tolerance of 2.0"),
        (not_the_records, "target is not its record's value"),
        (no_defect, "fix modules move nothing there"),
        (flag_off_its_target, "is restored off its target"),
        (unknown_kind, "unknown target kind 'MOCK_kind'"),
    ):
        with pytest.raises(ValueError, match=message):
            _with_restored(edit).engine_upgrade_restored_target_sentence
    if r.engine_upgrade_restored_count > 1:

        def two_engines(entries):
            _MOCK_fix_modules_target(entries[0])
            _MOCK_fix_modules_target(entries[1], "policyengine-us 8.8.8")

        with pytest.raises(ValueError, match="name several engines"):
            _with_restored(two_engines).engine_upgrade_restored_target_sentence


def test_every_engine_defect_still_excluded_has_a_paper_name():
    """An upgrade that restores any engine-defect record can be described:
    each root cause behind one has a name (an unnamed one stops the render)."""
    from policybench.paper_results import ROOT_CAUSE_LABELS

    for record in r.reference_exclusions:
        if record["reason_code"] == "reference_engine_defect":
            for cause in record["root_cause"].split("+"):
                assert cause in ROOT_CAUSE_LABELS, cause


def test_an_unnamed_root_cause_or_change_stops_the_sentence():
    """MOCK edits of the frozen sidecar: a restored record whose root cause,
    or a scored change whose cause, the paper has no name for is refused."""
    results = PaperResults()
    results.reference_revisions = deepcopy(r.reference_revisions)
    last = results.reference_revisions[-1]
    last["regenerated_exclusions"][0]["record"]["root_cause"] = "MOCK_unnamed_cause"
    with pytest.raises(ValueError, match="no paper name for the root causes"):
        results.engine_upgrade_restored_sentence
    results = PaperResults()
    results.reference_revisions = deepcopy(r.reference_revisions)
    last = results.reference_revisions[-1]
    last["regenerated_exclusions"][0]["upstream"] = "to be filed"
    with pytest.raises(ValueError, match="names no upstream pull request"):
        results.engine_upgrade_restored_sentence


@given(st.lists(st.text("abc", min_size=1, max_size=4), max_size=6))
def test_a_series_keeps_every_part_in_order(parts):
    from policybench.paper_results import _series

    text = _series(parts)
    if not parts:
        assert text == ""
    position = 0
    for part in parts:
        position = text.index(part, position) + len(part)
    assert text.count(" and ") == (1 if len(parts) >= 2 else 0)
    assert text.count(", ") == max(0, len(parts) - 2)


def _MOCK_october_timing(check: dict) -> dict:
    """MOCK timing record for the frozen engine, never a real sweep's."""
    engine = r.policyengine_us_version
    return {
        "pypi": {
            "read_at_utc": "2026-10-10T08:15:00Z",
            "newest_at_read": check["engine"],
            "wheel_uploaded_at_utc": {engine: "2026-10-10T02:20:11.5Z"},
        },
        "reference_sweep": {
            "engine": engine,
            "first_output_at_utc": "2026-10-10T02:41:00Z",
        },
        "publication_check": check,
    }


def _with_timing(tmp_path, monkeypatch, record: dict | None) -> PaperResults:
    from policybench import paper_results

    path = tmp_path / "sweep_timing.json"
    if record is not None:
        path.write_text(json.dumps(record))
    monkeypatch.setattr(paper_results, "OCTOBER_SWEEP_TIMING", path)
    return PaperResults()


def test_a_landed_defect_record_with_no_stated_reason_is_refused():
    """MOCK edit: a rechecked engine-defect record that lands on its corrected
    value must say why it stays excluded (an unstated input in its note, or a
    further engine defect in its recheck); otherwise the counts refuse."""
    results = PaperResults()
    results.reference_revisions = deepcopy(r.reference_revisions)
    last = results.reference_revisions[-1]
    field = "value_on_" + r.last_engine_upgrade.engine_version.replace(".", "_")
    records = {(e["scenario_id"], e["variable"]): e for e in r.reference_exclusions}
    for item in last["excluded_outputs_rechecked"]:
        key = (item["scenario_id"], item["variable"])
        if key in r.engine_defect_further_defect_keys:
            item["reason"] = "MOCK reason that states nothing"
            break
    else:
        for item in last["excluded_outputs_rechecked"]:
            key = (item["scenario_id"], item["variable"])
            record = records.get(key)
            if record and record["reason_code"] == "reference_engine_defect":
                item[field] = float(record["alternative_value"])
                record_note = record.get("note", "")
                if "(unlisted input)" not in record_note:
                    item["reason"] = "MOCK reason that states nothing"
                    break
        else:
            pytest.skip("no engine-defect record to edit")
    with pytest.raises(ValueError, match="names neither"):
        results.engine_defect_landed_keys


def test_an_upload_on_another_day_names_its_date(tmp_path, monkeypatch):
    """MOCK record: a wheel uploaded the day before the sweep began is dated,
    so the sentence does not imply the sweep's day."""
    engine = r.policyengine_us_version
    record = _MOCK_october_timing({"engine": engine})
    record["pypi"]["wheel_uploaded_at_utc"][engine] = "2026-10-09T23:50:02Z"
    sentence = _with_timing(
        tmp_path, monkeypatch, record
    ).engine_upgrade_timing_sentence
    assert "on 2026-10-10 (uploaded 2026-10-09 at 23:50 UTC)." in sentence


@given(st.datetimes(), st.dates())
def test_an_upload_phrase_dates_only_another_days_upload(moment, day):
    from policybench.paper_results import uploaded_phrase

    stamp = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    phrase = uploaded_phrase(stamp, day.isoformat())
    assert phrase.endswith(f"{stamp[11:16]} UTC")
    assert (stamp[:10] in phrase) is (stamp[:10] != day.isoformat())


def test_the_upgrade_timing_sentence_states_the_timing_record(tmp_path, monkeypatch):
    """MOCK records: the sentence gives the sweep's day, the engine's upload
    time and what the publication check found; without a record it is empty,
    and a check that moved outputs, or none, stops the render."""
    engine = r.policyengine_us_version
    assert (
        _with_timing(tmp_path, monkeypatch, None).engine_upgrade_timing_sentence == ""
    )
    still = _with_timing(
        tmp_path, monkeypatch, _MOCK_october_timing({"engine": engine})
    )
    assert still.engine_upgrade_timing_sentence == (
        f"policyengine-us {engine} was the newest release when PolicyBench began "
        "sweeping the references on 2026-10-10 (uploaded 02:20 UTC). It was still "
        "the newest release when PolicyBench checked PyPI on 2026-10-10 at 08:15 UTC."
    )
    same = {"engine": "9.9.9", "outputs": 1984, "same": 1984, "differ": []}
    newer = _with_timing(tmp_path, monkeypatch, _MOCK_october_timing(same))
    assert newer.engine_upgrade_timing_sentence.endswith(
        "policyengine-us 9.9.9, the newest release when PolicyBench checked PyPI on "
        f"2026-10-10 at 08:15 UTC, gives the same value as {engine} for all 1,984 "
        "outputs under the same conventions and adapter."
    )
    fixes = {
        "engine": "9.9.9",
        "outputs": 1984,
        "same": 1982,
        "differ": ["a|v", "b|v"],
        "scored_outputs": 1915,
        "scored_same": 1915,
        "scored_differ": [],
        "excluded_differ": ["a|v", "b|v"],
    }
    later = _with_timing(tmp_path, monkeypatch, _MOCK_october_timing(fixes))
    assert later.engine_upgrade_timing_sentence.endswith(
        f"gives the same value as {engine} for all 1,915 scored outputs under the "
        "same conventions and adapter, and moves two of the excluded outputs, "
        "which keep the values they were decided on."
    )
    moved = {
        **fixes,
        "scored_same": 1914,
        "scored_differ": ["s|v"],
        "excluded_differ": ["a|v"],
    }
    with pytest.raises(ValueError, match="state what the publication check found"):
        _with_timing(
            tmp_path, monkeypatch, _MOCK_october_timing(moved)
        ).engine_upgrade_timing_sentence
    unchecked = _MOCK_october_timing({"engine": engine})
    del unchecked["publication_check"]
    with pytest.raises(ValueError, match="records no publication check"):
        _with_timing(tmp_path, monkeypatch, unchecked).engine_upgrade_timing_sentence
    other = _MOCK_october_timing({"engine": engine})
    other["reference_sweep"]["engine"] = "0.0.1"
    with pytest.raises(ValueError, match="times policyengine-us 0.0.1"):
        _with_timing(tmp_path, monkeypatch, other).engine_upgrade_timing_sentence
    assert (
        "`{python} r.engine_upgrade_timing_sentence`"
        in (ROOT / "paper/index.qmd").read_text()
    )


def test_fixed_but_kept_engine_defect_records_are_counted_apart():
    """An engine-defect record the last upgrade rechecked whose new-engine
    value is its corrected value has a fixed defect: the paper counts it with
    the unstated inputs that keep it excluded, never as a defect "upstream
    has not fixed". Each such record names its second reason."""
    from policybench.paper_results import moves_beyond_tolerance

    last = r.last_engine_upgrade
    field = "value_on_" + last.engine_version.replace(".", "_")
    records = {(e["scenario_id"], e["variable"]): e for e in r.reference_exclusions}
    # The audit's fix-module evidence: corrected values on an engine that still
    # has the defect (where later engine changes moved the output).
    evidence: dict = {}
    for path in (ROOT / "reference_audit/2026-10-09-engine-upgrade/evidence").glob(
        "*.json"
    ):
        doc = json.loads(path.read_text())
        if doc.get("kind") != "regeneration_evidence":
            continue  # the request that produced it, say
        for row in doc["items"]:
            if moves_beyond_tolerance(
                row["variable"], row["engine_value"], row["corrected_value"]
            ):
                key = (row["scenario_id"], row["variable"])
                evidence.setdefault(key, []).append(row["corrected_value"])
    expected, further = set(), set()
    for item in last.rechecked:
        key = (item["scenario_id"], item["variable"])
        record = records[key]
        if record["reason_code"] != "reference_engine_defect":
            continue
        targets = [float(record["alternative_value"]), *evidence.get(key, [])]
        if any(
            not moves_beyond_tolerance(key[1], target, float(item[field]))
            for target in targets
        ):
            # Each landed record stays excluded for one stated reason: the
            # unstated input its note names, or a further engine defect.
            if "(unlisted input)" in record["note"]:
                expected.add(key)
                assert "second reason" in item["reason"], key
            else:
                further.add(key)
                assert "rests on a further engine defect" in item["reason"], key
    assert r.engine_defect_fixed_kept_keys == expected
    assert r.engine_defect_further_defect_keys == further
    assert expected, "the release keeps scenario_081's Massachusetts output"
    assert (
        r.engine_defect_unfixed_count
        + r.engine_defect_fixed_kept_count
        + r.engine_defect_further_defect_count
        == r.engine_defect_exclusion_count
    )
    assert r.engine_defect_present_count == (
        r.engine_defect_unfixed_count + r.engine_defect_further_defect_count
    )
    assert (
        r.engine_defect_present_count
        + r.unstated_input_exclusion_total
        + r.later_law_exclusion_count
        == r.excluded_output_count
    )
    assert (
        0
        < r.engine_defect_unfixed_root_cause_count
        <= (r.engine_defect_root_cause_count)
    )
    sentence = r.engine_defect_fixed_kept_sentence
    assert f"policyengine-us {r.policyengine_us_version} computes" in sentence
    paper = (ROOT / "paper/index.qmd").read_text()
    assert "`{python} r.engine_defect_fixed_kept_sentence`" in paper
    assert "`{python} r.engine_defect_further_defect_sentence`" in paper
    if r.engine_defect_further_defect_count:
        assert f"found on {r.policyengine_us_version}" in (
            r.engine_defect_further_defect_sentence
        )
    assert "`{python} r.engine_defect_present_count` outputs whose references" in paper
    # The September audit paragraph separates the defects the reference engine
    # still has from the records it fixes but keeps (pre-T review finding 4).
    assert (
        "still has the defect behind `{python} r.engine_defect_unfixed_count`" in paper
    )
    assert "They stay excluded until references built on a fixed engine" not in paper
