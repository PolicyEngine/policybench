"""The situations PolicyBench sends policyengine-us.

A situation that sets a variable the engine does not define fails with
SituationParsingError (unknown variable). policyengine-us removes and renames
inputs (#9605 deletes the tax-unit first/second home mortgage interest inputs),
so these tests parse every committed scenario manifest's situations against
the pinned engine: the next removal fails here, not at the next engine bump's
reference build.

Invariants of ``Scenario.to_pe_household`` (property tests below):
- every manifest input is either dropped for its entity (PE_DROPPED_INPUTS) or
  passed once, under its engine name (PE_INPUT_RENAMES), with its value;
- no dropped input reaches the engine;
- building the situation leaves the scenario, and so its prompt, unchanged.
"""

import copy
import importlib.util
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from policybench.ground_truth import _build_us_vectorized_situation
from policybench.prompts import describe_household
from policybench.scenarios import (
    PE_DROPPED_INPUTS,
    PE_INPUT_RENAMES,
    Person,
    Scenario,
    scenario_from_dict,
    scenario_to_dict,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = sorted(
    {
        *ROOT.glob("paper/snapshot/*/us_scenarios.csv"),
        *ROOT.glob("paper/snapshot/*/runs/*/scenarios.csv"),
    }
)
BENCHMARK_MANIFEST = ROOT / "paper/snapshot/20260501/us_scenarios.csv"
MORTGAGE_INTEREST = ("first_home_mortgage_interest", "second_home_mortgage_interest")
ENTITY_OF_GROUP = {
    "people": "person",
    "marital_units": "marital_unit",
    "tax_units": "tax_unit",
    "spm_units": "spm_unit",
    "families": "family",
    "households": "household",
}
# The audit harness the 2026-09-22 and 2026-09-29 reference builds used
# (reference_audit/2026-09-22/scripts/regen_references.py and
# 2026-09-28/scripts/build_references_latest.py import its build_situation).
AUDIT_SWEEP = ROOT / "reference_audit/2026-09-28/scripts/sweep.py"


@lru_cache(maxsize=None)
def _manifest_scenarios(path: Path) -> tuple[Scenario, ...]:
    frame = pd.read_csv(path)
    scenarios = [scenario_from_dict(json.loads(s)) for s in frame["scenario_json"]]
    return tuple(s for s in scenarios if s.country == "us")


def _pinned_variables():
    # The system policyengine_us.Simulation parses situations against.
    from policyengine_us.system import system

    return system.variables


def _carriers() -> list[Scenario]:
    return [
        scenario
        for scenario in _manifest_scenarios(BENCHMARK_MANIFEST)
        if any(key in scenario.tax_unit_inputs for key in MORTGAGE_INTEREST)
    ]


def test_the_committed_manifests_include_the_benchmark():
    # A glob that matched nothing would pass every check below vacuously.
    assert BENCHMARK_MANIFEST in MANIFESTS
    assert len(_manifest_scenarios(BENCHMARK_MANIFEST)) == 100


@pytest.mark.parametrize("manifest", MANIFESTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_situation_input_is_a_variable_of_the_pinned_engine(manifest):
    variables = _pinned_variables()
    problems = []
    for scenario in _manifest_scenarios(manifest):
        situation = scenario.to_pe_household()
        for group, entities in situation.items():
            for entity in entities.values():
                for name in entity:
                    if name == "members":
                        continue
                    variable = variables.get(name)
                    if variable is None:
                        problems.append(f"{scenario.id} {group}: {name} is unknown")
                    elif variable.entity.key != ENTITY_OF_GROUP[group]:
                        problems.append(
                            f"{scenario.id} {group}: {name} belongs to "
                            f"{variable.entity.key}"
                        )
    assert not problems, (
        "Situations set inputs the pinned policyengine-us does not define. Map a "
        "renamed input in PE_INPUT_RENAMES or drop a removed one in "
        "PE_DROPPED_INPUTS (policybench/scenarios.py):\n" + "\n".join(problems)
    )


@pytest.mark.parametrize("manifest", MANIFESTS, ids=lambda p: str(p.relative_to(ROOT)))
def test_the_pinned_engine_parses_every_situation(manifest):
    """The reference build's own path: one vectorized situation, parsed."""
    from policyengine_us import Simulation

    situation, _ = _build_us_vectorized_situation(list(_manifest_scenarios(manifest)))
    Simulation(situation=situation)


def test_structured_mortgage_interest_never_reaches_the_engine():
    carriers = _carriers()
    # The benchmark's 11 households that list them; CT 120 and OK 046 list a
    # second home too.
    assert sorted(s.id for s in carriers) == [
        "scenario_040",
        "scenario_046",
        "scenario_049",
        "scenario_056",
        "scenario_078",
        "scenario_081",
        "scenario_088",
        "scenario_092",
        "scenario_110",
        "scenario_118",
        "scenario_120",
    ]
    for manifest in MANIFESTS:
        for scenario in _manifest_scenarios(manifest):
            tax_unit = scenario.to_pe_household()["tax_units"]["tax_unit"]
            assert not set(MORTGAGE_INTEREST) & set(tax_unit), scenario.id
    for scenario in carriers:
        situation = scenario.to_pe_household()
        # The premise that makes dropping them inert: the engine's preferred
        # person-level input carries the same total.
        person_total = sum(
            person["home_mortgage_interest"]["2026"]
            for person in situation["people"].values()
            if "home_mortgage_interest" in person
        )
        listed = sum(scenario.tax_unit_inputs.get(k, 0.0) for k in MORTGAGE_INTEREST)
        assert person_total == pytest.approx(listed, abs=1e-6), scenario.id
        # The per-loan balances stay: the acquisition-debt cap reads them.
        tax_unit = situation["tax_units"]["tax_unit"]
        for key, value in scenario.tax_unit_inputs.items():
            if key.endswith("_mortgage_balance"):
                assert tax_unit[key] == {"2026": value}, (scenario.id, key)


def test_the_prompt_still_lists_the_dropped_inputs():
    """The manifests, and so the frozen prompts, keep them."""
    scenario = next(s for s in _carriers() if s.id == "scenario_120")
    before = scenario_to_dict(scenario)
    prompt = describe_household(scenario)
    scenario.to_pe_household()
    assert scenario_to_dict(scenario) == before
    assert describe_household(scenario) == prompt
    assert "- first home mortgage interest: $2,976" in prompt
    assert "- second home mortgage interest: $768" in prompt
    assert "- home mortgage interest: $3,744" in prompt


def test_a_renamed_input_reaches_the_engine_under_its_new_name():
    scenario = next(
        s for s in _manifest_scenarios(BENCHMARK_MANIFEST) if s.id == "scenario_064"
    )
    head = scenario.to_pe_household()["people"]["head"]
    assert "partnership_se_income" not in head
    assert head["partnership_self_employment_net_earnings"] == {"2026": 14_000.0}
    # The prompt keeps the manifest's name and label.
    assert "- self-employment partnership income: $14,000" in describe_household(
        scenario
    )


def test_an_input_set_directly_and_through_a_rename_is_refused():
    scenario = Scenario(
        id="collision",
        state="TX",
        filing_status="single",
        adults=[
            Person(
                name="head",
                age=40,
                employment_income=0.0,
                inputs={
                    "partnership_se_income": 1.0,
                    "partnership_self_employment_net_earnings": 2.0,
                },
            )
        ],
    )
    with pytest.raises(ValueError, match="partnership_self_employment_net_earnings"):
        scenario.to_pe_household()


def _audit_build_situation():
    spec = importlib.util.spec_from_file_location("audit_sweep", AUDIT_SWEEP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_situation


def test_the_audit_harness_builds_the_same_situations():
    """The audit harness's build_situation (to_pe_household plus its own RENAME)
    and to_pe_household agree on every committed household: PE_INPUT_RENAMES
    covers the harness's RENAME, so audit sweeps on current engines build the
    package's situations. (It does not compare with the situations the
    1.755.4-era references were built from, which passed the dropped inputs.)"""
    build_situation = _audit_build_situation()
    for manifest in MANIFESTS:
        for scenario in _manifest_scenarios(manifest):
            assert build_situation(scenario) == scenario.to_pe_household(), (
                manifest,
                scenario.id,
            )


@pytest.mark.slow
def test_dropping_the_structured_interest_moves_no_reference(monkeypatch):
    """On the pinned engine every output of the 11 households is the same with
    the tax-unit interest inputs passed and without them."""
    import policybench.scenarios as scenarios_module
    from policybench.ground_truth import calculate_ground_truth

    meta = json.loads(
        (
            ROOT / "paper/snapshot/20260501/runs/"
            "us_full_run_20260612_policyengine_4_16_1_populace/"
            "reference_outputs.csv.meta.json"
        ).read_text()
    )
    carriers = _carriers()
    dropped = calculate_ground_truth(carriers, programs=meta["programs"], year=2026)
    monkeypatch.setattr(scenarios_module, "PE_DROPPED_INPUTS", {})
    assert (
        "first_home_mortgage_interest"
        in (carriers[0].to_pe_household()["tax_units"]["tax_unit"])
    )
    passed = calculate_ground_truth(carriers, programs=meta["programs"], year=2026)
    pd.testing.assert_frame_equal(dropped, passed, check_exact=True)


# Property tests over arbitrary inputs: the dropped and renamed names mixed with
# ordinary ones, on every entity.
_DROPPED_NAMES = sorted({n for names in PE_DROPPED_INPUTS.values() for n in names})
_NAMES = st.sampled_from(
    [
        *_DROPPED_NAMES,
        *PE_INPUT_RENAMES,
        *PE_INPUT_RENAMES.values(),
        "home_mortgage_interest",
        "first_home_mortgage_balance",
        "real_estate_taxes",
        "rent",
    ]
)
_VALUES = st.one_of(
    st.floats(allow_nan=False, allow_infinity=False, width=32), st.booleans()
)
_INPUTS = st.dictionaries(_NAMES, _VALUES, max_size=6).filter(
    # A manifest never lists an input under both names; that case is refused.
    lambda inputs: (
        not any(
            old in inputs and new in inputs for old, new in PE_INPUT_RENAMES.items()
        )
    )
)


def _engine_inputs(entity: str, inputs: dict) -> dict:
    dropped = PE_DROPPED_INPUTS.get(entity, frozenset())
    return {
        PE_INPUT_RENAMES.get(k, k): {"2026": v}
        for k, v in inputs.items()
        if k not in dropped
    }


@settings(max_examples=200, deadline=None)
@given(person=_INPUTS, tax_unit=_INPUTS, spm_unit=_INPUTS, household=_INPUTS)
def test_every_input_is_dropped_or_passed_once_under_its_engine_name(
    person, tax_unit, spm_unit, household
):
    scenario = Scenario(
        id="property",
        state="TX",
        filing_status="single",
        adults=[Person(name="head", age=40, employment_income=0.0, inputs=person)],
        tax_unit_inputs=tax_unit,
        spm_unit_inputs=spm_unit,
        household_inputs=household,
        year=2026,
    )
    before = copy.deepcopy(scenario_to_dict(scenario))
    situation = scenario.to_pe_household()
    assert scenario_to_dict(scenario) == before
    assert scenario.to_pe_household() == situation

    entities = {
        "person": (situation["people"]["head"], person),
        "tax_unit": (situation["tax_units"]["tax_unit"], tax_unit),
        "spm_unit": (situation["spm_units"]["spm_unit"], spm_unit),
        "household": (situation["households"]["household"], household),
    }
    for entity, (data, inputs) in entities.items():
        expected = _engine_inputs(entity, inputs)
        for name, value in expected.items():
            assert data[name] == value, (entity, name)
        for name in PE_DROPPED_INPUTS.get(entity, ()):
            assert name not in data, (entity, name)
        for old in PE_INPUT_RENAMES:
            assert old not in data, (entity, old)
