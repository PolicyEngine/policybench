"""Checks for data-driven manuscript values."""

from collections import Counter

from policybench.paper_results import (
    MODEL_DISPLAY_NAMES,
    MODEL_RELEASE_DATES,
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
