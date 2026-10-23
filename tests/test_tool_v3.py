"""The calculator's features one at a time (tool v3 and the ablation arms).

Each feature (names, placement, overrides, explain, concise, flat) must work
on its own and change nothing else, so a study can turn one on at a time. The
version 2 feature set must reproduce tool v2's notice byte for byte, and the
flat household format must build the units the benchmark's own reference
situations have.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import tool_pilot_argon as pilot  # noqa: E402

V = pilot.VariableInfo
REGISTRY = {
    "age": V("person", "int", "age", "year"),
    "employment_income": V("person", "float", "employment income", "year"),
    "is_tax_unit_head": V("person", "bool", "head", "year"),
    "is_tax_unit_spouse": V("person", "bool", "spouse", "year"),
    "traditional_401k_contributions": V(
        "person", "float", "401(k)", "year", computed=True
    ),
    "traditional_401k_contributions_desired": V("person", "float", "asked", "year"),
    "snap": V("spm_unit", "float", "SNAP", "month", computed=True),
    "pre_subsidy_rent": V("spm_unit", "float", "rent", "year"),
    "qualified_passenger_vehicle_loan_interest": V(
        "household", "float", "car loan", "year"
    ),
    "state_code": V("household", "Enum", "state", "year", ("CA", "LA")),
    "tax_unit_childcare_expenses": V("tax_unit", "float", "childcare", "year"),
    "marital_unit_flag": V("marital_unit", "bool", "flag", "year"),
}
F = pilot


def _situation():
    return {
        "people": {"head": {"age": 40}, "kid": {"age": 8}},
        "spm_units": {"spm": {"members": ["head", "kid"]}},
        "households": {"h": {"members": ["head", "kid"], "state_code": "CA"}},
    }


def _norm(args, *features):
    return pilot.normalize_request(args, REGISTRY, features=frozenset(features))


def test_the_version_2_set_reproduces_tool_v2s_notice():
    assert F.compose_tool_notice(F.V2_FEATURES, True) == F.TOOL_NOTICE_V2
    assert F.compose_tool_notice(F.V2_FEATURES, False) == F.JSON_TOOL_NOTICE_V2
    assert F.compose_tool_notice(frozenset(), True) == F.TOOL_NOTICE
    assert F.compose_tool_notice(frozenset(), False) == F.JSON_TOOL_NOTICE


def test_each_feature_adds_its_own_sentence_only():
    base = F.compose_tool_notice(frozenset({F.EXPLAIN}), True)
    assert "`explain`" in base and "names it read" not in base
    assert "written with spaces" not in base
    names = F.compose_tool_notice(frozenset({F.NAMES}), True)
    assert "written with spaces" in names and "`explain`" not in names
    flat = F.compose_tool_notice(frozenset({F.FLAT}), True)
    assert "household you describe" in flat and "`household`" in flat
    concise = F.compose_tool_notice(frozenset({F.EXPLAIN, F.CONCISE}), True)
    assert '`detail` set to "full"' in concise


def test_arms_name_their_features():
    assert F.arm_features("pe") == frozenset()
    assert F.arm_features("pe2") == F.V2_FEATURES
    assert F.arm_features("pe3") == frozenset(F.TOOL_FEATURES)
    assert F.arm_features("pe:flat+names") == frozenset({"flat", "names"})
    assert F.arm_features("none") is None and F.arm_features("web") is None
    assert F.arm_suffix("pe:flat+names") == "+pe-tool[names+flat]"
    with pytest.raises(SystemExit, match="unknown tool features"):
        F.arm_features("pe:names+telepathy")
    with pytest.raises(SystemExit, match="concise feature needs explain"):
        F.arm_features("pe:concise")
    profile = F.ModelProfile("m", "gpt-x", "chat", "tool", arm="pe:names")
    assert profile.uses_calculator and profile.tool_features == frozenset({"names"})
    assert profile.tool_version == 1
    assert "written with spaces" in profile.notice
    assert profile.arm2_label == "m+pe-tool[names]"


def test_names_alone_reads_labels_but_places_and_redirects_nothing():
    situation = _situation()
    situation["people"]["head"]["Employment income"] = 30000
    request, error = _norm({"situation": situation, "variables": ["snap"]}, F.NAMES)
    assert error is None
    assert request["situation"]["people"]["head"]["employment_income"] == {
        "2026": 30000
    }
    misplaced = _situation()
    misplaced["people"]["head"]["qualified_passenger_vehicle_loan_interest"] = 5
    request, error = _norm({"situation": misplaced, "variables": ["snap"]}, F.NAMES)
    assert request is None and any(
        "set it under households" in p for p in error["problems"]
    )
    realized = _situation()
    realized["people"]["head"]["traditional_401k_contributions"] = 100
    request, error = _norm({"situation": realized, "variables": ["snap"]}, F.NAMES)
    assert "traditional_401k_contributions" in request["situation"]["people"]["head"]
    request, error = _norm(
        {"situation": _situation(), "variables": ["snap"], "explain": ["snap"]}, F.NAMES
    )
    assert request is None and any(
        "unknown arguments: explain" in p for p in error["problems"]
    )


def test_placement_alone_moves_inputs_but_reads_no_labels():
    situation = _situation()
    situation["people"]["head"]["qualified_passenger_vehicle_loan_interest"] = 5
    request, error = _norm({"situation": situation, "variables": ["snap"]}, F.PLACEMENT)
    assert error is None
    assert request["situation"]["households"]["h"][
        "qualified_passenger_vehicle_loan_interest"
    ] == {"2026": 5}
    labeled = _situation()
    labeled["people"]["head"]["employment income"] = 1
    request, error = _norm({"situation": labeled, "variables": ["snap"]}, F.PLACEMENT)
    assert request is None


def test_overrides_alone_redirects_and_flags():
    situation = _situation()
    situation["people"]["head"]["traditional_401k_contributions"] = 100
    situation["spm_units"]["spm"]["snap"] = 5
    request, error = _norm({"situation": situation, "variables": ["snap"]}, F.OVERRIDES)
    assert error is None
    head = request["situation"]["people"]["head"]
    assert head == {
        "age": {"2026": 40},
        "traditional_401k_contributions_desired": {"2026": 100},
    }
    assert any("snap is computed" in n for n in request["notes"])


def test_concise_takes_a_detail_and_defaults_to_brief():
    request, error = _norm(
        {"situation": _situation(), "variables": ["snap"], "explain": ["snap"]},
        F.EXPLAIN,
        F.CONCISE,
    )
    assert error is None and request["detail"] == "brief"
    request, _ = _norm(
        {
            "situation": _situation(),
            "variables": ["snap"],
            "explain": ["snap"],
            "detail": "full",
        },
        F.EXPLAIN,
        F.CONCISE,
    )
    assert request["detail"] == "full"
    request, error = _norm(
        {"situation": _situation(), "variables": ["snap"], "detail": "short"},
        F.EXPLAIN,
        F.CONCISE,
    )
    assert request is None
    request, _ = _norm(
        {"situation": _situation(), "variables": ["snap"], "explain": ["snap"]},
        F.EXPLAIN,
    )
    assert request["detail"] == "full"


def test_a_brief_explanation_keeps_the_value_its_direct_inputs_and_main_parameters():
    full = {
        "steps": [
            "snap (2026) = 288",
            "  snap_normal_allotment (2026) = 288",
            "    snap_net_income (2026) = 1700",
            "  is_snap_eligible (2026) = True",
        ],
        "parameters": [{"name": f"p{i}", "value": i, "sources": []} for i in range(9)],
    }
    brief = F.brief_explanation(full)
    assert brief["value"] == "snap (2026) = 288"
    assert brief["from"] == [
        "snap_normal_allotment (2026) = 288",
        "is_snap_eligible (2026) = True",
    ]
    assert [p["name"] for p in brief["parameters"]] == ["p0", "p1", "p2", "p3", "p4"]
    assert F.brief_explanation({"error": "x"}) == {"error": "x"}


def _flat(**overrides):
    household = {
        "state": "LA",
        "people": [
            {
                "name": "Head",
                "role": "head",
                "facts": {"age": 40, "employment_income": 30000},
            },
            {"name": "Spouse", "role": "spouse", "facts": {"age": 38}},
            {"name": "Kid", "role": "dependent", "facts": {"age": 6}},
        ],
        "household_facts": {
            "pre_subsidy_rent": 9000,
            "tax_unit_childcare_expenses": 1200,
            "qualified_passenger_vehicle_loan_interest": 300,
        },
    }
    household.update(overrides)
    return {"household": json.dumps(household), "variables": ["snap"]}


def test_flat_builds_the_benchmarks_units():
    request, error = _norm(_flat(), F.FLAT)
    assert error is None, error
    s = request["situation"]
    assert s["marital_units"] == {
        "marital_unit_1": {"members": ["Head", "Spouse"]},
        "marital_unit_2": {"members": ["Kid"]},
    }
    for group, unit in (
        ("tax_units", "tax_unit"),
        ("spm_units", "spm_unit"),
        ("families", "family"),
    ):
        assert s[group][unit]["members"] == ["Head", "Spouse", "Kid"]
    assert s["households"]["household"]["state_code"] == {"2026": "LA"}
    assert s["spm_units"]["spm_unit"]["pre_subsidy_rent"] == {"2026": 9000}
    assert s["tax_units"]["tax_unit"]["tax_unit_childcare_expenses"] == {"2026": 1200}
    assert s["households"]["household"][
        "qualified_passenger_vehicle_loan_interest"
    ] == {"2026": 300}
    assert s["people"]["Head"]["is_tax_unit_head"] == {"2026": True}
    assert s["people"]["Spouse"]["is_tax_unit_spouse"] == {"2026": True}
    assert s["people"]["Kid"]["is_tax_unit_head"] == {"2026": False}


def test_flat_refuses_what_it_cannot_place():
    people = [
        {"name": "A", "role": "head", "facts": {}},
        {"name": "B", "role": "head", "facts": {}},
    ]
    request, error = _norm(_flat(people=people), F.FLAT)
    assert any("exactly one head" in p for p in error["problems"])
    request, error = _norm(_flat(household_facts={"age": 3}), F.FLAT)
    assert any("person's fact" in p for p in error["problems"])
    people = [{"name": "A", "role": "boss", "facts": {}}]
    request, error = _norm(_flat(people=people), F.FLAT)
    assert any("role must be one of" in p for p in error["problems"])
    request, error = _norm({"situation": _situation(), "variables": ["snap"]}, F.FLAT)
    assert any("unknown arguments: situation" in p for p in error["problems"])
    request, error = _norm(_flat(), F.NAMES)
    assert any("unknown arguments: household" in p for p in error["problems"])


def test_flat_with_names_reads_labeled_household_facts():
    request, error = _norm(
        _flat(household_facts={"pre subsidy rent": 9000}), F.FLAT, F.NAMES
    )
    assert error is None
    assert request["situation"]["spm_units"]["spm_unit"]["pre_subsidy_rent"] == {
        "2026": 9000
    }
    assert any("as pre_subsidy_rent" in n for n in request["notes"])


def test_the_schema_offers_each_features_arguments():
    flat = F.calculate_tool_schema(features=frozenset({F.FLAT}))["function"]
    props = flat["parameters"]["properties"]
    assert "household" in props and "situation" not in props
    assert flat["parameters"]["required"] == ["household", "variables"]
    concise = F.calculate_tool_schema(features=frozenset({F.EXPLAIN, F.CONCISE}))
    props = concise["function"]["parameters"]["properties"]
    assert "explain" in props and props["detail"]["enum"] == ["brief", "full"]
    assert F.calculate_tool_schema(features=F.V2_FEATURES) == F.calculate_tool_schema(2)
    assert F.calculate_tool_schema(features=frozenset()) == F.calculate_tool_schema(1)


def _echo_worker(conn, fix_path, reform):
    conn.send(("ready", None))
    while True:
        args = conn.recv()
        if args is None:
            return
        conn.send(("ok", {"received": args}))


def test_the_pool_tells_its_workers_the_features():
    pool = F.ToolPool(
        size=1,
        timeout=5.0,
        worker_target=_echo_worker,
        tool_features=frozenset({F.FLAT, F.NAMES}),
    )
    try:
        result, _ = pool.call({"x": 1})
        assert result == {
            "received": {"__tool_features__": ["flat", "names"], "arguments": {"x": 1}}
        }
    finally:
        pool.close()


@pytest.mark.slow
def test_a_household_described_flat_computes_what_the_benchmarks_own_does():
    """Differential: on the installed engine, each frozen-board household
    described in the flat format computes every board output exactly as the
    benchmark's own situation (Scenario.to_pe_household) does."""
    import household_set as hs
    import pandas as pd
    from policyengine_us import Simulation

    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output

    system = F.build_tool_system(reform=True)
    registry = F.build_registry(system)
    reference = pd.read_csv(hs.FROZEN_BOARD / "reference_outputs.csv")
    variables = reference.groupby("scenario_id").variable.agg(list)
    relations = {"is_tax_unit_head", "is_tax_unit_spouse"}
    checked = 0
    for scenario in hs.load_scenarios(hs.FROZEN_BOARD)[:8]:
        situation = hs.situation_for(scenario)
        couple = scenario.marital_couple() or ()
        head = couple[0] if couple else scenario.adults[0].name
        people = [
            {
                "name": name,
                "role": "head"
                if name == head
                else ("spouse" if name in couple else "dependent"),
                "facts": {k: v for k, v in facts.items() if k not in relations},
            }
            for name, facts in situation["people"].items()
        ]
        household_facts = {}
        for group in ("tax_units", "spm_units", "families", "households"):
            for unit in situation[group].values():
                household_facts.update(
                    {
                        k: v
                        for k, v in unit.items()
                        if k not in ("members", "state_code")
                    }
                )
        household = {
            "state": scenario.state,
            "people": people,
            "household_facts": household_facts,
        }
        request, error = F.normalize_request(
            {"household": json.dumps(household), "variables": ["snap"]},
            registry,
            features=frozenset({F.FLAT}),
        )
        assert error is None, (scenario.id, error)
        own = Simulation(tax_benefit_system=system, situation=situation)
        flat = Simulation(tax_benefit_system=system, situation=request["situation"])
        for variable in variables[scenario.id]:
            name = _pe_variable_for_output(variable, "us")
            values = [
                float(
                    _extract_person_value(
                        simulation.calculate(name, 2026), scenario, variable
                    )
                )
                for simulation in (own, flat)
            ]
            assert values[0] == values[1], (scenario.id, variable, values)
            checked += 1
    assert checked > 80
