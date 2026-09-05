"""The frozen report distinguishes raw usage costs from published totals."""

import json
from pathlib import Path

import pandas as pd
import pytest


def test_frozen_report_discloses_recorded_subtotal_and_published_total():
    run = (
        Path(__file__).resolve().parents[1]
        / "paper/snapshot/20260501/runs"
        / "us_full_run_20260612_policyengine_4_16_1_populace"
    )
    usage = pd.read_csv(run / "analysis/usage_summary.csv")
    rows = json.loads((run / "data.json").read_text())["modelStats"]
    costs = {
        row["model"]: row["costUsd"] for row in rows if row["condition"] == "no_tools"
    }
    recorded = usage.loc[usage["total_cost_usd"].notna()]
    subtotal = recorded["total_cost_usd"].sum()
    total = sum(costs.values())
    fallbacks = sorted(set(costs) - set(recorded["model"]))
    assert len(recorded) == 30
    assert len(costs) == 33
    assert subtotal == pytest.approx(349.950, abs=0.0005)
    assert total == pytest.approx(414.029, abs=0.0005)
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
