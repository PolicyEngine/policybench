"""The frozen report distinguishes raw usage costs from published totals."""

from pathlib import Path

import pandas as pd
import pytest

from policybench.snapshot_payload import read_run_payload


def test_frozen_report_discloses_recorded_subtotal_and_published_total():
    run = (
        Path(__file__).resolve().parents[1]
        / "paper/snapshot/20260501/runs"
        / "us_full_run_20260612_policyengine_4_16_1_populace"
    )
    usage = pd.read_csv(run / "analysis/usage_summary.csv")
    rows = read_run_payload(run)["modelStats"]
    costs = {
        row["model"]: row["costUsd"] for row in rows if row["condition"] == "no_tools"
    }
    recorded = usage.loc[usage["total_cost_usd"].notna()]
    subtotal = recorded["total_cost_usd"].sum()
    total = sum(costs.values())
    fallbacks = sorted(set(costs) - set(recorded["model"]))
    # Release 20260929's 42 of 45, $448.339 and $512.418, plus GPT-6.1 Sol's
    # recorded $2.300, Claude Haiku 5.5's recorded $0.130, Muse Wonder's
    # recorded $7.864, Gemini 4 Argon's recorded $2.789 and Muse Spark 1.3's
    # recorded $2.059.
    assert len(recorded) == 47
    assert len(costs) == 50
    assert subtotal == pytest.approx(463.4808, abs=0.0005)
    assert total == pytest.approx(527.5602, abs=0.0005)
    assert fallbacks == ["claude-fable-5", "gemini-3.6-flash", "grok-build-0.1"]
    report = (run / "analysis/report.md").read_text()
    assert (
        f"Recorded-usage cost subtotal ({len(recorded)} of {len(costs)} models): "
        f"${subtotal:.3f}."
    ) in report
    assert (
        f"Published model costs total ${total:.3f} "
        f"(includes release-metadata costs for: {', '.join(fallbacks)})."
    ) in report
