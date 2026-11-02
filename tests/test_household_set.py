"""The household-set builder and the tool pilot's --board path.

The build test runs the real engine on three of the frozen board's own
households, with sampling and the dataset download faked, so the references it
writes must equal the frozen ones on the frozen engine (policyengine-us
2.41.0). It is marked slow.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.metadata
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import household_set as hs  # noqa: E402
import tool_pilot_argon as pilot  # noqa: E402

ON_FROZEN_ENGINE = importlib.metadata.version("policyengine-us") == "2.41.0"
SOL = "gpt-6-sol"


def test_rename_gives_fresh_ids_in_draw_order():
    scenarios = hs.load_scenarios(hs.FROZEN_BOARD)[:3]
    renamed = hs.rename_scenarios(list(reversed(scenarios)), "mc")
    assert [s.id for s in renamed] == ["mc_000", "mc_001", "mc_002"]
    assert renamed[0].state == scenarios[2].state
    assert renamed[0].metadata == scenarios[2].metadata
    assert [s.id for s in scenarios] == ["scenario_000", "scenario_001", "scenario_002"]


@given(st.lists(st.text(min_size=1), unique=True, max_size=60), st.integers(1, 15))
def test_batches_partition_the_draw_in_order(ids, size):
    batches = hs.split_batches(ids, size)
    assert [sid for batch in batches for sid in batch] == ids
    assert all(len(batch) == size for batch in batches[:-1])
    assert all(1 <= len(batch) <= size for batch in batches)


def test_batches_refuse_a_size_below_one():
    with pytest.raises(ValueError):
        hs.split_batches(["a"], 0)


def test_differences_report_missing_and_moved_outputs():
    expected = pd.DataFrame(
        {
            "scenario_id": ["a", "a", "b"],
            "variable": ["x", "y", "x"],
            "value": [1.0, 2.0, 3.0],
        }
    )
    computed = pd.DataFrame(
        {"scenario_id": ["a", "a"], "variable": ["x", "y"], "value": [1.0, 2.5]}
    )
    diff = hs.differences(expected, computed, tolerance=1e-6)
    assert sorted(zip(diff.scenario_id, diff.variable)) == [("a", "y"), ("b", "x")]
    assert hs.differences(expected, computed, tolerance=1.0).scenario_id.tolist() == [
        "b"
    ]


def test_fix_module_pins_are_the_frozen_revision():
    pins = hs.fix_module_pins()
    assert pins == [
        {"module": p["module"], "path": p["path"], "sha256": p["sha256"]}
        for p in hs.frozen_fix_pins()
    ]


def test_the_frozen_board_reads_as_before():
    assert pilot.board_engine() == pilot.REFERENCE_ENGINE
    assert not pilot.is_household_set(pilot.SNAPSHOT)
    assert pilot.board_fix_module_sha256() == pilot.FIX_MODULE_SHA256
    assert pilot.board_path(argparse.Namespace()) == pilot.SNAPSHOT


@pytest.mark.slow
def test_build_writes_the_frozen_references_for_frozen_households(household_board):
    out, sampled = household_board
    frozen = pd.read_csv(hs.FROZEN_BOARD / "reference_outputs.csv")
    built = pd.read_csv(out / "reference_outputs.csv")
    names = {f"mc_{i:03d}": s.id for i, s in enumerate(sampled)}
    built["frozen_id"] = built.scenario_id.map(names)
    merged = built.merge(
        frozen,
        left_on=["frozen_id", "variable"],
        right_on=["scenario_id", "variable"],
        suffixes=("", "_frozen"),
    )
    assert (
        len(merged)
        == len(built)
        == len(frozen[frozen.scenario_id.isin(names.values())])
    )
    from policybench.reference_exclusions import load_reference_exclusions

    excluded = {
        (e["scenario_id"], e["variable"])
        for e in load_reference_exclusions(hs.FROZEN_BOARD)
    }
    scored = merged[
        [(s, v) not in excluded for s, v in zip(merged.frozen_id, merged.variable)]
    ]
    assert (scored.value - scored.value_frozen).abs().max() < 1e-6


@pytest.mark.slow
def test_build_writes_a_board_the_pilot_reads(household_board):
    out, _ = household_board
    meta = json.loads((out / "reference_outputs.csv.meta.json").read_text())
    assert meta["board_kind"] == "household_set"
    assert meta["seed"] == 7 and meta["num_scenarios"] == 3
    assert meta["reference_csv_sha256"] == hs.sha256_file(out / "reference_outputs.csv")
    assert json.loads((out / "batches.json").read_text())["batches"] == [
        ["mc_000", "mc_001"],
        ["mc_002"],
    ]
    board = pilot.load_board(out)
    assert sorted(board["scenarios"]) == ["mc_000", "mc_001", "mc_002"]
    assert board["excluded"].empty
    assert pilot.is_household_set(out)
    assert pilot.board_engine(out) == "2.41.0"
    pilot.verify_fix_pins(snapshot=out)
    pilot._require_engine(out)


@pytest.mark.slow
def test_build_refuses_a_written_directory_and_a_dataset_off_the_bundle(
    household_board, tmp_path, monkeypatch
):
    out, _ = household_board
    with pytest.raises(SystemExit, match="not empty"):
        hs.main(["build", "--n", "3", "--seed", "7", "--out", str(out)])
    import policybench.policyengine_runtime as runtime

    dataset = tmp_path / "x.h5"
    dataset.write_bytes(b"other bytes")
    monkeypatch.setattr(
        runtime, "materialize_certified_us_dataset", lambda: str(dataset)
    )
    monkeypatch.setattr(
        runtime,
        "policyengine_bundles_for_countries",
        lambda countries: {"us": {"certified_data_artifact_sha256": "0" * 64}},
    )
    with pytest.raises(SystemExit, match="not the bundle's"):
        hs.main(["build", "--n", "1", "--seed", "1", "--out", str(tmp_path / "new")])


def _record(sid, variables, predictions, model, arm, prompt="v2-pilot"):
    record = {
        "scenario_id": sid,
        "model": model,
        "arm": arm,
        "prompt_version": prompt,
        "benchmark_search_rule": arm in ("web", "web+pe"),
        "variables": variables,
        "predictions": predictions,
        "explanations": {v: "x" for v in variables},
        "status": "complete",
        "turns": [{"total_cost_usd": 0.02, "calls": []}],
        "cap_hit": False,
        "wall_seconds": 1.0,
    }
    record["totals"] = pilot.household_totals(record)
    return record


def _write_run(directory, board, model, arm, miss=None, prompt="v2-pilot"):
    reference = board["reference"].set_index(["scenario_id", "variable"])["value"]
    (directory / "households").mkdir(parents=True)
    for sid in sorted(board["scenarios"]):
        variables = board["variables"][sid]
        predictions = {v: float(reference[(sid, v)]) for v in variables}
        if miss is not None and sid == miss[0]:
            predictions[miss[1]] = float(reference[(sid, miss[1])]) + 100
        record = _record(sid, variables, predictions, model, arm, prompt)
        (directory / "households" / f"{sid}.json").write_text(json.dumps(record))


@pytest.mark.slow
def test_a_household_set_scores_each_arm_against_its_no_tools_run(
    household_board, tmp_path
):
    out, _ = household_board
    board = pilot.load_board(out)
    amount = next(
        v
        for v in board["variables"]["mc_000"]
        if not v.endswith("_eligible") and v in set(board["scored"].variable)
    )
    none_dir, web_dir = tmp_path / "none", tmp_path / "web"
    _write_run(none_dir, board, SOL, "none", miss=("mc_000", amount))
    _write_run(web_dir, board, SOL, "web")
    pilot.command_score(
        argparse.Namespace(
            out_dir=str(web_dir),
            complete_only=False,
            board=str(out),
            baseline_dir=str(none_dir),
        )
    )
    score = json.loads((web_dir / "score.json").read_text())
    assert score["unweighted_hits"]["arm2"] == score["scored_outputs"]
    assert score["unweighted_hits"]["arm1"] == score["scored_outputs"] - 1
    usage = pd.read_csv(web_dir / "usage_by_household.csv")
    assert usage.arm1_cost_usd.round(6).tolist() == [0.02, 0.02, 0.02]

    with pytest.raises(SystemExit, match="--baseline-dir"):
        pilot.command_score(
            argparse.Namespace(
                out_dir=str(web_dir), complete_only=False, board=str(out)
            )
        )
    with pytest.raises(SystemExit, match="not gpt-6-sol none"):
        pilot.command_score(
            argparse.Namespace(
                out_dir=str(web_dir),
                complete_only=False,
                board=str(out),
                baseline_dir=str(web_dir),
            )
        )
    v1_dir = tmp_path / "none-v1"
    _write_run(v1_dir, board, SOL, "none", prompt="v1")
    with pytest.raises(SystemExit, match="another prompt version"):
        pilot.command_score(
            argparse.Namespace(
                out_dir=str(web_dir),
                complete_only=False,
                board=str(out),
                baseline_dir=str(v1_dir),
            )
        )


def _scenario(sid, filing_status, tax_unit):
    from policybench.scenarios import Person, Scenario

    return Scenario(
        id=sid,
        state="CA",
        filing_status=filing_status,
        adults=[Person(name="head", age=40, employment_income=0.0)],
        metadata={"household_id": 1, "tax_unit_id": tax_unit},
    )


def test_stated_filing_status_is_read_from_the_tax_unit_table(tmp_path):
    import h5py
    import numpy as np

    path = tmp_path / "set.h5"
    rows = np.array(
        [(0, 11, b"JOINT"), (1, 12, b"SEPARATE"), (2, 13, b"SURVIVING_SPOUSE")],
        dtype=[
            ("index", "<i8"),
            ("tax_unit_id", "<i8"),
            ("filing_status_input", "S20"),
        ],
    )
    with h5py.File(path, "w") as handle:
        handle.create_group("tax_unit").create_dataset("table", data=rows)
    stated = hs.stated_filing_status(path)
    assert stated == {11: "JOINT", 12: "SEPARATE", 13: "SURVIVING_SPOUSE"}
    scenarios = [
        _scenario("mc_000", "joint", 11),
        _scenario("mc_001", "joint", 12),
        _scenario("mc_002", "surviving_spouse", 13),
        _scenario("mc_003", "single", 99),
    ]
    assert hs.filing_status_mismatches(scenarios, stated) == [
        {
            "scenario_id": "mc_001",
            "tax_unit_id": 12,
            "stated": "SEPARATE",
            "engine": "joint",
        }
    ]
    assert hs.filing_status_mismatches(scenarios, None) == []
    not_h5 = tmp_path / "x.h5"
    not_h5.write_bytes(b"placeholder")
    assert hs.stated_filing_status(not_h5) is None


def test_a_reference_situation_states_citizenship_and_ssn():
    scenario = hs.load_scenarios(hs.FROZEN_BOARD)[0]
    people = hs.situation_for(scenario)["people"]
    assert people
    for person in people.values():
        assert person["immigration_status"] == {"2026": "CITIZEN"}
        assert person["ssn_card_type"] == {"2026": "CITIZEN"}


def test_a_stated_status_outranks_the_default():
    scenario = hs.load_scenarios(hs.FROZEN_BOARD)[0]
    head = scenario.adults[0]
    stated = dataclasses.replace(
        scenario,
        adults=[
            dataclasses.replace(head, inputs={**head.inputs, "ssn_card_type": "NONE"}),
            *scenario.adults[1:],
        ],
    )
    assert hs.situation_for(stated)["people"][head.name]["ssn_card_type"] == {
        "2026": "NONE"
    }


def test_the_stated_statuses_are_the_engine_defaults():
    """d1970 keeps every reference, so stating them must change none."""
    from policyengine_us.variables.household.demographic.person import (
        immigration_status,
        ssn_card_type,
    )

    assert hs.STATED_STATUSES == {
        "immigration_status": immigration_status.immigration_status.default_value.name,
        "ssn_card_type": ssn_card_type.ssn_card_type.default_value.name,
    }


@pytest.fixture(scope="module")
def engine_system():
    return hs.reference_system()


def _dependent_scenario(state: str, child_income: float = 0.0, **child_inputs):
    from policybench.scenarios import Person, Scenario

    return Scenario(
        id=f"{state.lower()}_{int(child_income)}",
        state=state,
        filing_status=None,
        adults=[Person("adult1", 40, 50_000.0)],
        children=[Person("child1", 16, child_income, dict(child_inputs))],
    )


def test_the_build_check_names_each_dependent_the_engine_gives_return_income(
    engine_system,
):
    """d1029's last check reads the reference engine's own measures for every
    person but the head and spouse, so it holds whichever inputs produce the
    income (Sol review r2). Partnership self-employment earnings are not gross
    income, but they require a return from $400; the head's own earnings never
    count (review r3)."""
    from policybench.scenarios import Person, Scenario

    head_earns = Scenario(
        id="tx_head_earns",
        state="TX",
        filing_status=None,
        adults=[
            Person("adult1", 40, 0.0, {"self_employment_income": 30_000.0}),
            Person(
                "adult2",
                38,
                0.0,
                {"is_tax_unit_spouse": True, "self_employment_income": 20_000.0},
            ),
        ],
        children=[Person("child1", 16, 0.0)],
    )
    found = hs.dependents_with_return_income(
        [
            _dependent_scenario("TX", 5_117.0),
            _dependent_scenario("PA", 0.0, taxable_interest_income=40.0),
            _dependent_scenario("TX"),
            _dependent_scenario("TX", 0.0, child_support_received=3_000.0),
            _dependent_scenario(
                "FL", 0.0, partnership_self_employment_net_earnings=10_000.0
            ),
            head_earns,
        ],
        engine_system,
    )
    assert found == [
        "tx_5117 child1 gross income $5,117.00",
        "pa_0 child1 gross income $40.00",
        # 92.35% of $10,000 (26 U.S.C. 1402(a)(12)).
        "fl_0 child1 self-employment earnings $9,235.00",
    ]


def test_the_build_check_reads_the_engine_it_is_given(monkeypatch):
    """The check runs on the engine the references use, fixes included
    (review r3, reviewer mutant R4)."""
    from types import SimpleNamespace

    import numpy as np
    import policyengine_us

    engines = []

    class Simulation:
        def __init__(self, tax_benefit_system=None, situation=None):
            engines.append(tax_benefit_system)
            self.populations = {"person": SimpleNamespace(ids=["adult1", "child1"])}

        def calculate(self, variable, period):
            return np.zeros(2)

    monkeypatch.setattr(policyengine_us, "Simulation", Simulation)
    found = hs.dependents_with_return_income(
        [_dependent_scenario("TX")], "the reference engine"
    )
    assert found == []
    assert engines == ["the reference engine"]


def test_alaska_alone_gives_income_with_no_input(engine_system):
    """The draw's state list checked against the reference engine: an adult and
    a child with no inputs get gross income in Alaska, from the Permanent Fund
    Dividend, and nowhere else."""
    from policybench.scenarios import STATES_WITH_UNSTATED_INCOME, US_STATE_CODES

    assert STATES_WITH_UNSTATED_INCOME == {"AK"}
    assert (
        hs.states_with_unstated_income(sorted(US_STATE_CODES), engine_system)
        == STATES_WITH_UNSTATED_INCOME
    )


@pytest.mark.parametrize(
    ("variable", "person"),
    [("irs_gross_income", 0), ("dependent_gross_income", 1)],
    ids=["head", "dependent"],
)
def test_the_state_check_reads_the_head_and_the_dependent(
    monkeypatch, variable, person
):
    """A state counts when the engine gives income to either person on either
    measure, and the check reads the engine it receives."""
    import numpy as np
    import policyengine_us

    engines = []

    class Simulation:
        def __init__(self, tax_benefit_system=None, situation=None):
            engines.append(tax_benefit_system)
            self.state = situation["households"]["household"]["state_code"][
                str(hs.YEAR)
            ]

        def calculate(self, name, period):
            amounts = np.zeros(2)
            if name == variable and self.state == "NM":
                amounts[person] = 1.0
            return amounts

    monkeypatch.setattr(policyengine_us, "Simulation", Simulation)
    found = hs.states_with_unstated_income(["NM", "TX"], "the reference engine")
    assert found == {"NM"}
    assert engines == ["the reference engine"] * 2


def test_every_input_the_engine_counts_for_a_dependent_is_listed(engine_system):
    """d1029's list checked against the reference engine (review r3): a
    dependent who has one promptable person input alone, at $10,000 or
    $200,000, gets gross income or self-employment earnings only from a listed
    input, or from Social Security, which follows its own rule. One simulation
    holds a Texas household for each input and amount."""
    from policyengine_us import Simulation

    from policybench.scenarios import (
        DEPENDENT_RETURN_INCOME_FIELDS,
        SOCIAL_SECURITY_FIELDS,
        get_promptable_input_specs,
    )

    specs = [
        spec
        for spec in get_promptable_input_specs()
        if spec.entity == "person" and spec.value_type == "float"
    ]
    units = ("tax_units", "families", "spm_units", "households", "marital_units")
    people, groups, cases = {}, {unit: {} for unit in units}, []
    for amount in (10_000.0, 200_000.0):
        for spec in specs:
            i = len(cases)
            head, child = f"h{i}", f"c{i}"
            # Wages under the input's own name: an input set on any person
            # stops that variable's formula for every person.
            people[head] = {
                "age": {hs.YEAR: 40},
                "employment_income_before_lsr": {hs.YEAR: 50_000.0},
            }
            people[child] = {"age": {hs.YEAR: 16}, spec.source_name: {hs.YEAR: amount}}
            for unit in ("tax_units", "families", "spm_units"):
                groups[unit][f"{unit}{i}"] = {"members": [head, child]}
            groups["households"][f"household{i}"] = {
                "members": [head, child],
                "state_code": {hs.YEAR: "TX"},
            }
            groups["marital_units"][f"head{i}"] = {"members": [head]}
            groups["marital_units"][f"child{i}"] = {"members": [child]}
            cases.append(spec.output_name)
    simulation = Simulation(
        tax_benefit_system=engine_system, situation={"people": people, **groups}
    )
    people_ids = list(simulation.populations["person"].ids)
    counted = set()
    for variable in ("dependent_gross_income", "taxable_self_employment_income"):
        amounts = dict(zip(people_ids, simulation.calculate(variable, hs.YEAR)))
        counted |= {name for i, name in enumerate(cases) if amounts[f"c{i}"] != 0}
    # The probe reaches both measures.
    assert {"employment_income", "partnership_self_employment_net_earnings"} <= counted
    assert counted - set(SOCIAL_SECURITY_FIELDS) <= DEPENDENT_RETURN_INCOME_FIELDS


def _certified_build(tmp_path, monkeypatch):
    """A build with a certified bundle and dataset, both faked."""
    import policybench.policyengine_runtime as runtime

    version = importlib.metadata.version("policyengine-us")
    dataset = tmp_path / "d.h5"
    dataset.write_bytes(b"placeholder")
    monkeypatch.setattr(
        runtime, "materialize_certified_us_dataset", lambda: str(dataset)
    )
    monkeypatch.setattr(
        runtime,
        "policyengine_bundles_for_countries",
        lambda countries: {
            "us": {
                "certified_data_artifact_sha256": hs.sha256_file(dataset),
                "bundled_model_version": version,
                "model_version": version,
            }
        },
    )
    monkeypatch.setattr(hs, "fix_module_pins", lambda fix_module: [])


def test_the_build_refuses_a_draw_that_kept_a_dependent_with_return_income(
    tmp_path, monkeypatch
):
    import policybench.scenarios as scenarios_module

    _certified_build(tmp_path, monkeypatch)
    sampled = hs.load_scenarios(hs.FROZEN_BOARD)[:1]
    monkeypatch.setattr(hs, "reference_system", lambda fix_module: "system")
    monkeypatch.setattr(
        scenarios_module, "generate_scenarios", lambda **kwargs: sampled
    )
    checked = []

    def with_income(scenarios, system):
        checked.append((scenarios, system))
        return ["mc_000 child1 gross income $6,944.00"]

    def references(scenarios, programs, system):
        raise AssertionError("the build computed references before the check")

    monkeypatch.setattr(hs, "dependents_with_return_income", with_income)
    monkeypatch.setattr(hs, "compute_references", references)
    monkeypatch.setattr(hs, "stated_filing_status", lambda path: {})
    out = tmp_path / "set"
    refusal = r"kept dependents with income.*mc_000 child1 gross income \$6,944"
    with pytest.raises(SystemExit, match=refusal):
        hs.main(["build", "--n", "1", "--seed", "7", "--out", str(out)])
    assert not out.exists()
    ((scenarios, system),) = checked
    assert system == "system"
    assert [s.id for s in scenarios] == ["mc_000"]


def test_the_build_refuses_a_draw_in_a_state_with_unstated_income(
    tmp_path, monkeypatch
):
    import policybench.scenarios as scenarios_module

    _certified_build(tmp_path, monkeypatch)
    sampled = hs.load_scenarios(hs.FROZEN_BOARD)[:2]
    monkeypatch.setattr(hs, "reference_system", lambda fix_module: "system")
    monkeypatch.setattr(
        scenarios_module, "generate_scenarios", lambda **kwargs: sampled
    )
    checked = []

    def unstated(states, system):
        checked.append((states, system))
        return {"NM"}

    def references(scenarios, programs, system):
        raise AssertionError("the build computed references before the check")

    monkeypatch.setattr(hs, "dependents_with_return_income", lambda *args: [])
    monkeypatch.setattr(hs, "states_with_unstated_income", unstated)
    monkeypatch.setattr(hs, "compute_references", references)
    monkeypatch.setattr(hs, "stated_filing_status", lambda path: {})
    out = tmp_path / "set"
    with pytest.raises(SystemExit, match="income with no input.*states: NM"):
        hs.main(["build", "--n", "2", "--seed", "7", "--out", str(out)])
    assert not out.exists()
    # Each drawn state, once.
    assert checked == [(sorted({s.state for s in sampled}), "system")]


def test_the_build_filters_the_draw_and_rounds_before_the_references(
    tmp_path, monkeypatch
):
    import policybench.scenarios as scenarios_module
    from policybench.scenarios import STATES_WITH_UNSTATED_INCOME

    _certified_build(tmp_path, monkeypatch)
    drawn = {}
    sampled = hs.load_scenarios(hs.FROZEN_BOARD)[:1]

    def draw(**kwargs):
        drawn.update(kwargs)
        return sampled

    seen = []

    def references(scenarios, programs, system):
        seen.extend(scenarios)
        return pd.DataFrame(
            columns=["scenario_id", "variable", "value", "impact_weight"]
        )

    checked = []
    monkeypatch.setattr(scenarios_module, "generate_scenarios", draw)
    monkeypatch.setattr(hs, "compute_references", references)
    monkeypatch.setattr(hs, "reference_system", lambda fix_module: None)
    monkeypatch.setattr(
        hs,
        "dependents_with_return_income",
        lambda scenarios, system: checked.extend(scenarios) or [],
    )
    monkeypatch.setattr(hs, "states_with_unstated_income", lambda states, system: set())
    monkeypatch.setattr(hs, "stated_filing_status", lambda path: {})
    monkeypatch.setattr(hs, "filing_status_mismatches", lambda scenarios, stated: [])
    out = tmp_path / "set"
    hs.main(["build", "--n", "1", "--seed", "7", "--out", str(out)])
    assert drawn["head_spouse_returns_only"] is True
    assert drawn["excluded_states"] == STATES_WITH_UNSTATED_INCOME

    def amounts(scenario):
        return [
            value
            for person in (*scenario.adults, *scenario.children)
            for value in (person.employment_income, *person.inputs.values())
            if not isinstance(value, bool | str)
        ]

    (scenario,) = seen
    assert amounts(scenario)
    assert all(float(amount).is_integer() for amount in amounts(scenario))
    # The draw had cents to round, and the check read the rounded households
    # the references read (review r3, reviewer mutant R5).
    assert not all(float(amount).is_integer() for amount in amounts(sampled[0]))
    assert checked == [scenario]
    meta = json.loads((out / "scenarios.csv.meta.json").read_text())
    assert meta["household_filter"] == hs.HOUSEHOLD_FILTER


def test_a_dataset_is_named_by_repo_file_and_tag_together(tmp_path):
    with pytest.raises(SystemExit, match="--dataset-repo, --dataset-file and"):
        hs.main(
            [
                "build",
                "--n",
                "1",
                "--seed",
                "1",
                "--out",
                str(tmp_path / "x"),
                "--dataset-repo",
                "policyengine/populace-us",
                "--purpose",
                "test",
            ]
        )


@pytest.mark.slow
def test_v2_needs_a_bundle_that_certifies_the_installed_engine(tmp_path, monkeypatch):
    import policybench.policyengine_runtime as runtime

    dataset = tmp_path / "d.h5"
    dataset.write_bytes(b"placeholder")
    monkeypatch.setattr(
        runtime, "materialize_certified_us_dataset", lambda: str(dataset)
    )
    monkeypatch.setattr(
        runtime,
        "policyengine_bundles_for_countries",
        lambda countries: {
            "us": {
                "certified_data_artifact_sha256": hs.sha256_file(dataset),
                "bundled_model_version": "2.2.1",
                "model_version": "2.60.4",
            }
        },
    )
    with pytest.raises(SystemExit, match="not a certified pair"):
        hs.main(["build", "--n", "1", "--seed", "1", "--out", str(tmp_path / "v2")])
