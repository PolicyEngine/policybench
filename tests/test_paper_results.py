"""Checks for data-driven manuscript values."""

from collections import Counter

from policybench.paper_results import (
    MODEL_DISPLAY_NAMES,
    MODEL_RELEASE_DATES,
    r,
)


def test_frozen_roster_has_30_display_names_and_release_dates():
    roster = {row["model"] for row in r.model_stats}

    assert len(roster) == 30
    assert set(MODEL_DISPLAY_NAMES) == roster
    assert roster <= set(MODEL_RELEASE_DATES)
    assert MODEL_DISPLAY_NAMES["gemini-3.7-flash"] == "Gemini 3.7 Flash"
    assert MODEL_RELEASE_DATES["gemini-3.7-flash"] == "2026-08-13"


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
    assert r.parse_contract_failure_pct_fmt == "1.1"
