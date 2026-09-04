"""Checks for data-driven manuscript values."""

import re
from collections import Counter

import pandas as pd
import pytest

from policybench.analysis import model_cost_latency
from policybench.config import PRICE_OVERRIDES_PER_1M
from policybench.paper_results import (
    MODEL_DISPLAY_NAMES,
    MODEL_RELEASE_DATES,
    ROOT,
    SNAPSHOT_DIR,
    r,
)


def test_frozen_roster_has_33_display_names_and_release_dates():
    roster = {row["model"] for row in r.model_stats}

    assert len(roster) == 33
    assert set(MODEL_DISPLAY_NAMES) == roster
    assert roster <= set(MODEL_RELEASE_DATES)
    assert MODEL_DISPLAY_NAMES["claude-fable-5.1"] == "Claude Fable 5.1"
    assert MODEL_RELEASE_DATES["claude-fable-5.1"] == "2026-09-01"
    assert MODEL_DISPLAY_NAMES["gemini-3.7-flash"] == "Gemini 3.7 Flash"
    assert MODEL_RELEASE_DATES["gemini-3.7-flash"] == "2026-08-13"
    assert MODEL_DISPLAY_NAMES["grok-4.6"] == "Grok 4.6"
    assert MODEL_DISPLAY_NAMES["ox-alpha"] == "Ox Alpha (preview)"
    assert MODEL_RELEASE_DATES["ox-alpha"] == "2026-08-21"


def test_parse_contract_failure_counts_come_from_frozen_dashboard():
    assert r.parse_contract_failure_counts == Counter(
        {
            "kimi-k2.6": 426,
            "glm-5.2": 139,
            "kimi-k3": 64,
        }
    )
    assert r.parse_contract_failure_count == 629
    assert r.parse_contract_failure_count_fmt == "629"
    assert r.parse_contract_failure_pct_fmt == "1.0"


def test_audit_universe_counts_come_from_frozen_rows_and_annotations():
    assert r.audit_annotated_row_count == 7_840
    assert r.audit_annotated_row_count_fmt == "7,840"
    assert r.audit_selection_rule == ("rows whose legacy threshold score is below 1")
    assert r.exact_match_miss_count == 7_838
    assert r.exact_match_miss_count_fmt == "7,838"
    assert r.annotated_exact_miss_count == 7_838
    assert r.annotated_exact_miss_count_fmt == "7,838"
    assert r.annotated_exact_hit_count == 2
    assert r.annotated_exact_hit_count_fmt == "2"
    assert r.unannotated_below_full_bounded_score_count == 1_324
    assert r.unannotated_below_full_bounded_score_count_fmt == "1,324"


def test_contract_violations_are_counted_both_ways():
    """629 rows never parsed a number; 61 more parsed a number but carry no
    explanation. The manuscript reports both, not just the first."""
    assert dict(r.explanation_missing_counts) == {
        "grok-4.3": 56,
        "kimi-k2.6": 4,
        "claude-haiku-4.5": 1,
    }
    assert r.explanation_missing_count_fmt == "61"
    assert r.contract_violation_count_fmt == "690"
    assert r.explanation_missing_breakdown_fmt == (
        "Grok 4.3 (56), Kimi K2.6 (4), and Claude Haiku 4.5 (1)"
    )


def test_raw_response_preservation_is_stated_with_its_exceptions():
    assert dict(r.blank_raw_response_counts) == {
        "claude-fable-5": 1984,
        "kimi-k3": 64,
    }
    assert r.blank_raw_response_note == (
        "no raw payload is retained for Claude Fable 5 (1,984 rows) and "
        "Kimi K3 (64 rows)"
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
    assert "where the provider returns one, otherwise reconstructed" in text
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
    assert r.serving_evidence_caption == (
        "Four rows carry supervised-run fingerprints for answer contract, "
        "request shape, tool choice, and completion ceiling; reasoning setup "
        "and timeouts for every row, and all fields for the other "
        f"{summary['registry']} rows, are the harness registry as frozen in the "
        "snapshot's serving-configuration file."
    )
