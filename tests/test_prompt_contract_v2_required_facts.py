"""Replay real October audit perturbations; legacy gaps are reported, not gated."""

import csv
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from policybench.prompt_contract_v2 import FactProvenance, render_household_contract
from policybench.prompt_contract_v2_required_facts import (
    replay_recorded_sweep,
    report_required_facts,
)
from policybench.scenarios import scenario_from_dict

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/prompt_contract_v2/unlisted_input_sweep_20261005.json"
RUN = ROOT / (
    "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)


@pytest.fixture(scope="module")
def audit_evidence():
    fixture = json.loads(FIXTURE.read_text())
    scenarios = {
        row["scenario_id"]: scenario_from_dict(json.loads(row["scenario_json"]))
        for row in csv.DictReader((RUN / "scenarios.csv").open())
    }
    references = {
        (row["scenario_id"], row["variable"]): float(row["value"])
        for row in csv.DictReader((RUN / "reference_outputs.csv").open())
    }
    exclusions = {
        (record["scenario_id"], record["variable"]): record
        for record in json.loads((RUN / "reference_exclusions.json").read_text())[
            "exclusions"
        ]
    }
    rendered = {
        sid: render_household_contract(scenario, policyengine_us_version="2.15.17")
        for sid, scenario in scenarios.items()
    }
    return fixture, scenarios, references, exclusions, rendered


def test_recorded_sweep_provenance_matches_all_frozen_inputs(audit_evidence):
    fixture, scenarios, references, _, _ = audit_evidence
    source = fixture["sources"]["unlisted_input_sweep"]
    for filename, provenance_key in (
        ("scenarios.csv", "scenarios_sha256"),
        ("reference_outputs.csv", "reference_sha256"),
        ("reference_exclusions.json", "exclusions_sha256"),
    ):
        assert (
            hashlib.sha256((RUN / filename).read_bytes()).hexdigest()
            == source[provenance_key]
        )
    assert source["policyengine_us"] == "2.15.17"
    assert source["simulations"] == 9165
    assert "not_enrolled" in source["note"]
    assert len(scenarios) == 100
    assert len(references) == source["outputs"] == 1984


@pytest.mark.parametrize("module", ["unlisted_input_sweep", "output_scope"])
def test_reused_comparison_modules_are_exact_upstream_sources(audit_evidence, module):
    fixture = audit_evidence[0]
    source = fixture["sources"]["comparison_logic"]
    assert source["commit"] == "4485065643fd7ace5a46cfeff740c1b9f3170ad2"
    assert (
        hashlib.sha256((ROOT / f"policybench/{module}.py").read_bytes()).hexdigest()
        == (source[f"{module}_py_sha256"])
    )


def test_replay_uses_upstream_sweep_comparisons_on_100_fixtures(audit_evidence):
    fixture, scenarios, references, exclusions, _ = audit_evidence
    sweep = replay_recorded_sweep(fixture, scenarios, references, exclusions)
    assert sweep.summary["households"] == 100
    assert sweep.summary["outputs"] == 1984
    assert sweep.summary["baseline_scored_mismatches"] == []
    assert len(sweep.moves) == len(fixture["moves"])
    assert set(sweep.moves["status"]) == {
        "scored",
        "prompt_rules_out",
        "excluded_same_input",
        "excluded_other_reason",
    }
    # These excluded outputs' recomputed baselines differ from the frozen CSV.
    hours = sweep.moves[sweep.moves["estimate"] == "weekly_hours_worked_before_lsr"]
    assert set(hours["baseline"]) == {0.0, 95.0}


def test_legacy_required_fact_report_lists_gaps_without_gating(audit_evidence):
    from policybench.prompt_contract_v2 import STATED_CONVENTION_INPUTS

    fixture, scenarios, references, exclusions, rendered = audit_evidence
    sweep = replay_recorded_sweep(fixture, scenarios, references, exclusions)
    report = report_required_facts(
        sweep, fixture, scenarios, rendered, STATED_CONVENTION_INPUTS
    )
    # This assertion establishes evidence coverage, never a zero-gap release gate.
    assert report["households"] == 100
    assert report["outputs"] == 1984
    print(json.dumps(report, indent=2, sort_keys=True))


def test_global_conventions_cover_only_named_estimates(audit_evidence):
    fixture, scenarios, references, exclusions, rendered = audit_evidence
    sweep = replay_recorded_sweep(fixture, scenarios, references, exclusions)
    stated = {
        "state_withheld_income_tax",
        "takes_up_medicare_if_eligible",
        "medicare_part_b_premium",
        "state_paid_leave_employee_share",
    }
    report = report_required_facts(sweep, fixture, scenarios, rendered, stated)
    remaining = {entry["estimate"] for entry in report["remaining"]}
    assert not remaining & {
        "state_withheld_income_tax",
        "medicare_part_b_premium",
        "state_paid_leave_employee_share",
    }
    assert "county" in remaining
    assert "meets_ssi_disability_criteria" in remaining
    assert "months_receiving_social_security_disability" in remaining


@pytest.mark.parametrize(
    "sid,entity,name,estimate",
    [
        (
            "scenario_022",
            "tax_unit",
            "state_withheld_income_tax",
            "state_withheld_income_tax",
        ),
        (
            "scenario_114",
            "person",
            "takes_up_medicare_if_eligible",
            "medicare_part_b_premium",
        ),
        (
            "scenario_114",
            "person",
            "medicare_part_b_premium",
            "medicare_part_b_premium",
        ),
        (
            "scenario_032",
            "person",
            "state_paid_leave_employee_share_withheld",
            "state_paid_leave_employee_share",
        ),
    ],
)
def test_explicit_null_overrides_a_named_convention(
    audit_evidence, sid, entity, name, estimate
):
    from policybench.prompt_contract_v2 import STATED_CONVENTION_INPUTS

    fixture, scenarios, references, exclusions, rendered = audit_evidence
    scenarios = deepcopy(scenarios)
    scenario = scenarios[sid]
    values = (
        scenario.adults[0].inputs
        if entity == "person"
        else getattr(scenario, f"{entity}_inputs")
    )
    values[name] = None
    rendered = dict(rendered)
    rendered[sid] = render_household_contract(
        scenario, policyengine_us_version="2.15.17"
    )
    sweep = replay_recorded_sweep(fixture, scenarios, references, exclusions)
    report = report_required_facts(
        sweep, fixture, scenarios, rendered, STATED_CONVENTION_INPUTS
    )
    residual = next(
        (entry for entry in report["remaining"] if entry["estimate"] == estimate),
        None,
    )
    assert residual is not None
    assert sid in {output[0] for output in residual["outputs"]}


def test_unknown_disability_values_do_not_count_as_stated(audit_evidence):
    fixture, scenarios, references, exclusions, rendered = audit_evidence
    scenarios = deepcopy(scenarios)
    scenarios["scenario_057"].adults[0].inputs["meets_ssi_disability_criteria"] = True
    rendered = dict(rendered)
    rendered["scenario_057"] = render_household_contract(
        scenarios["scenario_057"], policyengine_us_version="2.15.17"
    )
    sweep = replay_recorded_sweep(fixture, scenarios, references, exclusions)
    report = report_required_facts(sweep, fixture, scenarios, rendered, set())
    unresolved = next(
        entry
        for entry in report["remaining"]
        if entry["estimate"] == "meets_ssi_disability_criteria"
    )
    assert "scenario_057" in {output[0] for output in unresolved["outputs"]}


def test_raw_unsupported_county_does_not_count_as_stated(audit_evidence):
    fixture, scenarios, references, exclusions, rendered = audit_evidence
    scenarios = deepcopy(scenarios)
    scenarios["scenario_118"].household_inputs["county"] = "ALBANY_COUNTY_NY"
    rendered = dict(rendered)
    rendered["scenario_118"] = render_household_contract(
        scenarios["scenario_118"], policyengine_us_version="2.15.17"
    )
    sweep = replay_recorded_sweep(fixture, scenarios, references, exclusions)
    report = report_required_facts(sweep, fixture, scenarios, rendered, set())
    unresolved = next(
        entry for entry in report["remaining"] if entry["estimate"] == "county"
    )
    assert ["scenario_118", "snap"] in unresolved["outputs"]


def test_observed_criteria_resolve_only_the_affected_household(audit_evidence):
    fixture, scenarios, references, exclusions, rendered = audit_evidence
    scenarios = deepcopy(scenarios)
    scenario = scenarios["scenario_057"]
    people = scenario.adults + scenario.children
    provenance = {}
    for person in people:
        if person.inputs.get("is_disabled"):
            person.inputs["meets_ssi_disability_criteria"] = True
            provenance[person.name] = {
                "meets_ssi_disability_criteria": FactProvenance(
                    "observed", "synthetic criterion finding for coverage test"
                )
            }
    rendered = dict(rendered)
    rendered[scenario.id] = render_household_contract(
        scenario, policyengine_us_version="2.15.17", provenance=provenance
    )
    sweep = replay_recorded_sweep(fixture, scenarios, references, exclusions)
    report = report_required_facts(sweep, fixture, scenarios, rendered, set())
    residual = next(
        entry
        for entry in report["remaining"]
        if entry["estimate"] == "meets_ssi_disability_criteria"
    )
    assert "scenario_057" not in {output[0] for output in residual["outputs"]}
    assert "scenario_064" in {output[0] for output in residual["outputs"]}


def test_replay_rejects_unknown_households(audit_evidence):
    fixture, scenarios, references, exclusions, _ = audit_evidence
    fixture = deepcopy(fixture)
    fixture["moves"][0]["scenario_id"] = "scenario_999"
    with pytest.raises(ValueError, match="unknown scenario"):
        replay_recorded_sweep(fixture, scenarios, references, exclusions)


def test_replay_rejects_recorded_nonmoves(audit_evidence):
    fixture, scenarios, references, exclusions, _ = audit_evidence
    fixture = deepcopy(fixture)
    fixture["moves"][0]["value"] = fixture["moves"][0]["baseline"]
    with pytest.raises(ValueError, match="does not move"):
        replay_recorded_sweep(fixture, scenarios, references, exclusions)


def test_replay_rejects_reference_evidence_changes(audit_evidence):
    fixture, scenarios, references, exclusions, _ = audit_evidence
    references = dict(references)
    first = fixture["moves"][0]
    references[(first["scenario_id"], first["variable"])] += 100
    with pytest.raises(ValueError, match="published reference"):
        replay_recorded_sweep(fixture, scenarios, references, exclusions)
