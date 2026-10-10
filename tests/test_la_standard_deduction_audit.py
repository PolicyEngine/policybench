"""The Louisiana 2026 standard deduction audit (reference_audit/2026-10-05-louisiana).

Checks the committed sweep and scoring records against each other and against the
statute's arithmetic, without loading the engine:

- the sweep's baseline reproduces every scored reference, and the candidates move only
  the two Louisiana state income tax outputs;
- for every Louisiana household and every candidate, the engine's Louisiana tax is 3%
  of Louisiana AGI less the candidate deduction (R.S. 47:32, 47:293, 47:294), with the
  joint, head of household and surviving spouse amount at 200% of the single one;
- between any two candidates, each output moves by exactly 3% of the change in the
  deduction where taxable income stays positive, and not at all where it stays zero;
- the analyze CLI's scoring moves exact match for exactly the models a $1-tolerance
  count of their answers says it should.
"""

from __future__ import annotations

import gzip
import itertools
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "reference_audit/2026-10-05-louisiana"
VERIFICATION = AUDIT / "verification"
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
OUTPUTS = {
    ("scenario_051", "state_income_tax_before_refundable_credits"),
    ("scenario_077", "state_income_tax_before_refundable_credits"),
}
CANDIDATES = (
    "engine",
    "dec_dec_unrounded",
    "annual_average",
    "ldr_published",
    "ldr_official",
    "hold_2025",
)
RATE = 0.03
DOUBLE = {"joint", "head_of_household", "surviving_spouse"}


@pytest.fixture(scope="module")
def sweep() -> pd.DataFrame:
    return pd.read_csv(VERIFICATION / "sweep_la_standard_deduction.csv")


@pytest.fixture(scope="module")
def households() -> dict:
    return json.loads((VERIFICATION / "sweep_la_households.json").read_text())


@pytest.fixture(scope="module")
def filing_status() -> dict[str, str]:
    scenarios = pd.read_csv(RUN / "scenarios.csv")
    return {
        row["scenario_id"]: json.loads(row["scenario_json"])["filing_status"].lower()
        for _, row in scenarios.iterrows()
    }


def test_baseline_reproduces_every_scored_reference(sweep):
    assert len(sweep) == 1984
    scored = sweep[~sweep["excluded"]]
    assert len(scored) == 1928
    assert scored["baseline_matches_reference"].all()


def test_engine_candidate_is_the_reference(sweep):
    assert not sweep["engine_changed"].any()


@pytest.mark.parametrize("candidate", CANDIDATES[1:])
def test_candidates_move_only_the_two_louisiana_outputs(sweep, candidate):
    changed = sweep[sweep[f"{candidate}_changed"]]
    assert set(zip(changed["scenario_id"], changed["variable"])) == OUTPUTS
    assert not changed["excluded"].any()


def test_statute_arithmetic_for_every_louisiana_household(households, filing_status):
    candidates = households["candidates_single"]
    assert {h["scenario_id"] for h in households["households"]} == {
        "scenario_038",
        "scenario_051",
        "scenario_057",
        "scenario_074",
        "scenario_077",
    }
    for household in households["households"]:
        multiple = 2 if filing_status[household["scenario_id"]] in DOUBLE else 1
        for candidate in CANDIDATES:
            d = household[candidate]
            assert d["la_standard_deduction"] == pytest.approx(
                multiple * candidates[candidate], abs=0.01
            )
            assert d["la_itemized_deductions"] == 0
            taxable = max(d["la_agi"] - d["la_standard_deduction"], 0)
            assert d["la_taxable_income"] == pytest.approx(taxable, abs=0.01)
            assert d["state_income_tax_before_refundable_credits"] == pytest.approx(
                RATE * taxable - d["la_non_refundable_credits"], abs=0.01
            )


def test_pairwise_moves_are_three_percent_of_the_deduction_change(
    households, filing_status
):
    candidates = households["candidates_single"]
    for household in households["households"]:
        multiple = 2 if filing_status[household["scenario_id"]] in DOUBLE else 1
        for a, b in itertools.permutations(CANDIDATES, 2):
            da, db = household[a], household[b]
            move = (
                db["state_income_tax_before_refundable_credits"]
                - da["state_income_tax_before_refundable_credits"]
            )
            if da["la_taxable_income"] > 0 and db["la_taxable_income"] > 0:
                expected = -RATE * multiple * (candidates[b] - candidates[a])
                assert move == pytest.approx(expected, abs=0.01)
            if da["la_taxable_income"] == 0 and db["la_taxable_income"] == 0:
                assert move == 0


def test_scoring_moves_exact_match_for_exactly_the_models_that_match():
    summary = json.loads((VERIFICATION / "leaderboard_impact.json").read_text())
    assert summary["published_reproduced"] is True
    models = pd.read_csv(VERIFICATION / "leaderboard_impact_models.csv")
    published = json.loads(gzip.decompress((RUN / "data.json.gz").read_bytes()))
    predictions = published["scenarioPredictions"]
    for option in ("keep", "ldr_published", "ldr_official", "hold_2025"):
        values = summary["reference_values"][option]
        matched = set()
        for key, reference in values.items():
            sid, variable = key.split("/")
            within = sorted(
                model
                for model, row in predictions[sid][variable].items()
                if row.get("prediction") is not None
                and abs(float(row["prediction"]) - reference) <= 1.0
            )
            assert within == summary["options"][option]["exact_models"][key]
            matched.update(within)
        rows = models[models["option"] == option]
        moved = set(rows[rows["exact_delta"] > 1e-12]["model"])
        assert moved == matched, option
    assert summary["options"]["exclude"]["scored_outputs"] == 1926
    assert summary["options"]["keep"]["scored_outputs"] == 1928
