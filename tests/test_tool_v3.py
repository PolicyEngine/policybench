"""The calculator's features one at a time (tool v3 and the ablation arms).

Each feature (names, placement, overrides, explain, concise, flat) must work
on its own and change nothing else, so a study can turn one on at a time. The
version 2 feature set must reproduce tool v2's notice byte for byte, and the
flat household format must build the units the benchmark's own reference
situations have.
"""

from __future__ import annotations

import itertools
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
    "pre_subsidy_rent": V("person", "float", "rent", "year"),
    "spm_unit_energy_subsidy": V("spm_unit", "float", "energy", "year"),
    "qualified_passenger_vehicle_loan_interest": V(
        "household", "float", "car loan", "year"
    ),
    "state_code": V("household", "Enum", "state", "year", ("CA", "LA")),
    "tax_unit_childcare_expenses": V("tax_unit", "float", "childcare", "year"),
    "marital_unit_flag": V("marital_unit", "bool", "flag", "year"),
    "has_esi": V("person", "bool", "ESI", "year"),
    "hours_worked_last_week": V("person", "float", "hours", "year"),
    "weekly_hours_worked_before_lsr": V("person", "float", "hours", "year"),
    "partnership_self_employment_net_earnings": V("person", "float", "p", "year"),
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
    assert len(F.TOOL_FEATURES) == 7 and F.LABELS in F.arm_features("pe3")
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
    assert "detail" not in request  # the trace, as tool version 2 explains


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


def test_labels_reads_the_facts_as_the_prompt_labels_them():
    situation = _situation()
    situation["people"]["head"].update(
        {
            "gross wages and salaries": 30000,
            "Has Employer-Sponsored Insurance": True,
            "usual weekly hours worked": 40,
            "self-employment partnership income": 5,
        }
    )
    request, error = _norm({"situation": situation, "variables": ["snap"]}, F.LABELS)
    assert error is None, error
    head = request["situation"]["people"]["head"]
    assert head["employment_income"] == {"2026": 30000}
    assert head["has_esi"] == {"2026": True}
    assert head["hours_worked_last_week"] == {"2026": 40}
    assert head["partnership_self_employment_net_earnings"] == {"2026": 5}
    # The reference also sets stated hours where the SNAP work rules read them.
    assert head["weekly_hours_worked_before_lsr"] == {"2026": 40}
    assert any("also set weekly_hours_worked_before_lsr" in n for n in request["notes"])
    # A name written with spaces is the names feature's, not this one's.
    spaced = _situation()
    spaced["people"]["head"]["employment income"] = 1
    request, error = _norm({"situation": spaced, "variables": ["snap"]}, F.LABELS)
    assert request is None and "unknown variable 'employment income'" in str(error)


def test_labels_leaves_hours_already_set_where_the_rules_read_them():
    situation = _situation()
    situation["people"]["head"].update(
        {"hours_worked_last_week": 40, "weekly_hours_worked_before_lsr": 20}
    )
    request, _ = _norm({"situation": situation, "variables": ["snap"]}, F.LABELS)
    head = request["situation"]["people"]["head"]
    assert head["weekly_hours_worked_before_lsr"] == {"2026": 20}


def test_pe2_reads_no_labels_and_sets_no_alias_as_it_ran():
    situation = _situation()
    situation["people"]["head"]["gross wages and salaries"] = 30000
    request, error = _norm(
        {"situation": situation, "variables": ["snap"]}, *F.V2_FEATURES
    )
    assert request is None and "gross wages and salaries" in str(error)
    situation = _situation()
    situation["people"]["head"]["hours_worked_last_week"] = 40
    request, _ = _norm({"situation": situation, "variables": ["snap"]}, *F.V2_FEATURES)
    assert (
        "weekly_hours_worked_before_lsr" not in request["situation"]["people"]["head"]
    )


def test_only_pe2_says_the_facts_carry_variable_names():
    claim = "labeled with its variable names"
    assert claim in F.TOOL_NOTICE_V2
    for size in range(1, len(F.TOOL_FEATURES) + 1):
        for features in itertools.combinations(F.TOOL_FEATURES, size):
            features = frozenset(features)
            if F.CONCISE in features and F.EXPLAIN not in features:
                continue
            notice = F.compose_tool_notice(features, True)
            assert (claim in notice) == (features == F.V2_FEATURES), features
            assert notice.endswith("as instructed above.")
            assert ("names it read" in notice) == bool(features & {F.NAMES, F.LABELS})


def test_every_label_a_prompt_shows_reads_back_to_its_engine_name():
    from policybench.prompts import _format_input_line
    from policybench.scenarios import PE_DROPPED_INPUTS, PE_INPUT_RENAMES

    labels = F.prompt_labels()
    fields = {spec.output_name: spec.value_type for spec in F._promptable_specs()}
    fields |= {"age": "int", "employment_income": "float"}
    dropped = {f for names in PE_DROPPED_INPUTS.values() for f in names}
    for field, value_type in {**fields, **dict.fromkeys(dropped, "float")}.items():
        for label in F.rendered_labels(field, value_type):
            want = (PE_INPUT_RENAMES.get(field, field), field in dropped)
            assert want in labels[F._label_key(label)], (field, label)
    # Fallback labels (the name with spaces) are the prompt's too.
    assert ("first_home_mortgage_balance", False) in labels[
        F._label_key("first home mortgage balance")
    ]
    # Special renderers: the Marketplace plan line is labeled on its own.
    line = _format_input_line("selected_marketplace_plan_benchmark_ratio", 0.8)
    assert line.startswith("- selected Marketplace plan: ")
    assert ("selected_marketplace_plan_benchmark_ratio", False) in labels[
        F._label_key("selected Marketplace plan")
    ]
    # The v2-pilot prompt's relabelings, as that prompt writes them.
    for field, label in (
        ("spm_unit_energy_subsidy", "home energy assistance received"),
        (
            "employer_sponsored_insurance_premiums",
            "employer-paid health insurance premiums (paid by the employer, "
            "not by the household)",
        ),
    ):
        assert label in F.rendered_labels(field)
        assert (field, False) in labels[F._label_key(label)]
    assert ("state_code", False) in labels[F._label_key("state")]
    assert ("first_home_mortgage_interest", True) in labels[
        F._label_key("first home mortgage interest")
    ]
    assert ("roth_401k_contributions_desired", False) in labels[
        F._label_key("Roth 401k contributions desired")
    ]
    assert ("partnership_s_corp_income", False) in labels[
        F._label_key("partnership or S-corp income")
    ]


def test_labels_reads_no_label_that_names_two_of_the_engines_inputs(monkeypatch):
    two = frozenset({("has_esi", False), ("age", False)})
    monkeypatch.setattr(F, "prompt_labels", lambda: {F._label_key("covered"): two})
    situation = _situation()
    situation["people"]["head"]["covered"] = True
    request, error = _norm({"situation": situation, "variables": ["snap"]}, F.LABELS)
    assert request is None and "unknown variable 'covered'" in str(error)
    one = frozenset({("has_esi", False), ("uk_only_input", False)})
    monkeypatch.setattr(F, "prompt_labels", lambda: {F._label_key("covered"): one})
    request, error = _norm({"situation": situation, "variables": ["snap"]}, F.LABELS)
    assert error is None and request["situation"]["people"]["head"]["has_esi"]


def test_labels_ignores_a_fact_the_reference_leaves_out():
    situation = _situation()
    situation["tax_units"] = {
        "t": {"members": ["head", "kid"], "first home mortgage interest": 900}
    }
    request, error = _norm({"situation": situation, "variables": ["snap"]}, F.LABELS)
    assert error is None, error
    assert request["situation"]["tax_units"]["t"] == {"members": ["head", "kid"]}
    assert any("leaves it out too" in n for n in request["notes"])
    request, error = _norm({"situation": situation, "variables": ["snap"]}, F.NAMES)
    assert request is None and "first home mortgage interest" in str(error)


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
            "spm_unit_energy_subsidy": 900,
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
    assert s["spm_units"]["spm_unit"]["spm_unit_energy_subsidy"] == {"2026": 900}
    assert s["tax_units"]["tax_unit"]["tax_unit_childcare_expenses"] == {"2026": 1200}
    assert s["households"]["household"][
        "qualified_passenger_vehicle_loan_interest"
    ] == {"2026": 300}
    assert s["people"]["Head"]["is_tax_unit_head"] == {"2026": True}
    assert s["people"]["Spouse"]["is_tax_unit_spouse"] == {"2026": True}
    assert s["people"]["Kid"]["is_tax_unit_head"] == {"2026": False}


def test_flat_names_a_person_by_role_when_no_name_is_given():
    people = [
        {"role": "head", "facts": {"age": 40}},
        {"role": "dependent", "facts": {"age": 6}},
        {"name": "Kid", "role": "dependent", "facts": {"age": 4}},
        {"role": "dependent", "facts": {"age": 2}},
    ]
    request, error = _norm(_flat(people=people), F.FLAT)
    assert error is None, error
    assert list(request["situation"]["people"]) == [
        "head",
        "dependent_1",
        "Kid",
        "dependent_3",
    ]
    assert "people[0]: named head" in request["notes"]
    people = [
        {"role": "head", "facts": {}},
        {"name": "head", "role": "dependent", "facts": {}},
    ]
    request, error = _norm(_flat(people=people), F.FLAT)
    assert any("listed twice" in p for p in error["problems"])
    people = [{"name": "", "role": "head", "facts": {}}]
    request, error = _norm(_flat(people=people), F.FLAT)
    assert any("name must be a short string" in p for p in error["problems"])


def test_flat_placement_gives_a_household_of_ones_person_fact_to_that_person():
    one = [{"name": "Solo", "role": "head", "facts": {"age": 70}}]
    args = _flat(people=one, household_facts={"pre_subsidy_rent": 9000})
    request, error = _norm(args, F.FLAT, F.PLACEMENT)
    assert error is None, error
    solo = request["situation"]["people"]["Solo"]
    assert solo["pre_subsidy_rent"] == {"2026": 9000}
    assert "pre_subsidy_rent" not in request["situation"]["spm_units"]["spm_unit"]
    assert any("moved pre_subsidy_rent" in n for n in request["notes"])
    one[0]["facts"]["pre_subsidy_rent"] = 100
    conflict = _flat(people=one, household_facts={"pre_subsidy_rent": 9000})
    request, error = _norm(conflict, F.FLAT, F.PLACEMENT)
    assert any("different value" in p for p in error["problems"])
    # Two people: whose rent it is is not said, so it is refused.
    request, error = _norm(
        _flat(household_facts={"pre_subsidy_rent": 9000}), F.FLAT, F.PLACEMENT
    )
    assert any("whose facts list it" in p for p in error["problems"])
    # Without placement, even a household of one is refused.
    request, error = _norm(args, F.FLAT)
    assert any("whose facts list it" in p for p in error["problems"])


def test_flat_refuses_facts_given_beside_the_person():
    people = [{"role": "head", "age": 40, "employment_income": 30000}]
    request, error = _norm(_flat(people=people), F.FLAT)
    assert request is None
    assert any(
        "takes only name, role and facts; give age, employment_income under facts" in p
        for p in error["problems"]
    )


def test_flat_reads_a_fact_written_two_ways_once_whatever_the_order():
    for facts in (
        {"spm_unit_energy_subsidy": 900, "spm unit energy subsidy": 800},
        {"spm unit energy subsidy": 800, "spm_unit_energy_subsidy": 900},
    ):
        request, error = _norm(_flat(household_facts=facts), F.FLAT, F.NAMES)
        assert request is None
        assert any("set twice with different values" in p for p in error["problems"])
    same = {"spm_unit_energy_subsidy": 900, "spm unit energy subsidy": {"2026": 900}}
    request, error = _norm(_flat(household_facts=same), F.FLAT, F.NAMES)
    assert error is None, error


def test_flat_roles_set_the_relationship_inputs_and_refuse_a_contradiction():
    for written in ("is_tax_unit_head", "is tax unit head"):
        people = [{"name": "A", "role": "head", "facts": {written: False}}]
        request, error = _norm(_flat(people=people), F.FLAT, F.NAMES)
        assert request is None, written
        assert any("contradicts the role head" in p for p in error["problems"])
        people = [{"name": "A", "role": "head", "facts": {written: True}}]
        request, error = _norm(_flat(people=people), F.FLAT, F.NAMES)
        assert error is None, (written, error)
        head = request["situation"]["people"]["A"]
        assert head["is_tax_unit_head"] == {"2026": True}
        assert head["is_tax_unit_spouse"] == {"2026": False}


def test_flat_placement_compares_values_once_normalized():
    one = [
        {"name": "Solo", "role": "head", "facts": {"pre_subsidy_rent": {"2026": 9000}}}
    ]
    args = _flat(people=one, household_facts={"pre_subsidy_rent": 9000})
    request, error = _norm(args, F.FLAT, F.PLACEMENT)
    assert error is None, error
    assert request["situation"]["people"]["Solo"]["pre_subsidy_rent"] == {"2026": 9000}


def test_the_descriptions_promise_only_what_the_features_do():
    flat = F.calculate_tool_schema(features=frozenset({F.FLAT}))["function"]
    assert '"employment_income": 30000' in flat["description"]
    example = [
        {"role": "head", "facts": {"age": 40, "employment_income": 30000}},
    ]
    request, error = _norm(_flat(people=example), F.FLAT)
    assert error is None, error
    entity_error = "a variable set on the wrong entity"
    placed = F.calculate_tool_schema(features=frozenset({F.PLACEMENT}))["function"]
    assert entity_error not in placed["description"]
    assert "moved to the one unit holding its people" in placed["description"]
    named = F.calculate_tool_schema(features=frozenset({F.NAMES}))["function"]
    assert entity_error in named["description"]
    concise = F.calculate_tool_schema(features=frozenset({F.EXPLAIN, F.CONCISE}))
    detail = concise["function"]["parameters"]["properties"]["detail"]["description"]
    assert f"up to {F.EXPLAIN_MAX_LINES} steps" in detail
    for features in (frozenset({F.EXPLAIN, F.CONCISE}), frozenset(F.TOOL_FEATURES)):
        assert "every step" not in F.compose_tool_notice(features, True)


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
        _flat(household_facts={"spm unit energy subsidy": 900}), F.FLAT, F.NAMES
    )
    assert error is None
    spm_unit = request["situation"]["spm_units"]["spm_unit"]
    assert spm_unit["spm_unit_energy_subsidy"] == {"2026": 900}
    assert any("as spm_unit_energy_subsidy" in n for n in request["notes"])


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


def test_the_pool_tells_its_workers_the_features_in_a_frame():
    pool = F.ToolPool(
        size=1,
        timeout=5.0,
        worker_target=_echo_worker,
        tool_features=frozenset({F.FLAT, F.NAMES}),
    )
    try:
        result, _ = pool.call({"x": 1})
        assert result == {"received": ("calculate", ("flat", "names"), {"x": 1})}
    finally:
        pool.close()


def test_a_model_cannot_turn_on_a_feature_its_arm_does_not_offer():
    forged = {
        "__tool_features__": ["names"],
        "arguments": {
            "situation": {"people": {"head": {"Employment income": 12345}}},
            "variables": ["age"],
        },
    }
    for message in (forged, {"__tool_version__": 2, "arguments": forged["arguments"]}):
        request, error = F.worker_request(message, REGISTRY)
        assert request is None
        assert "unknown arguments: " in error["problems"][0]
    request, error = F.worker_request(
        F.tool_call_frame(frozenset({F.NAMES}), forged["arguments"]), REGISTRY
    )
    assert error is None
    assert request["situation"]["people"]["head"]["employment_income"] == {
        "2026": 12345
    }
    for names in (("telepathy",), ("concise",), ({},), ["names"]):
        request, error = F.worker_request(("calculate", names, {}), REGISTRY)
        assert request is None and error["error"] == "configuration", names


def _profile(arm):
    return F.ModelProfile("m", "gpt-x", "chat", "tool", arm=arm)


def _record(profile, **changes):
    record = {
        "scenario_id": "mt_000",
        "tool_notice_sha256": __import__("hashlib")
        .sha256(profile.notice.encode())
        .hexdigest(),
        **F.profile_treatment(profile),
    }
    record.update(changes)
    return record


def test_a_resume_refuses_households_run_under_another_treatment():
    pe3 = _profile("pe3")
    assert F.record_treatment_problem(_record(pe3), pe3) is None
    six = sorted(set(F.TOOL_FEATURES) - {F.LABELS})
    assert "tool features" in F.record_treatment_problem(
        _record(pe3, tool_features=six), pe3
    )
    assert "another tool notice" in F.record_treatment_problem(
        _record(pe3, tool_notice_sha256="0" * 64), pe3
    )
    assert "calculator schema" in F.record_treatment_problem(
        _record(pe3, calculate_tool_sha256="0" * 64), pe3
    )
    old = _record(pe3)
    del old["tool_features"]
    assert "no recorded tool features" in F.record_treatment_problem(old, pe3)
    # Arms whose treatment never changed accept records from before the fields.
    for arm in ("pe", "pe2", "web+pe", "none", "web"):
        profile = _profile(arm)
        legacy = _record(profile)
        for key in ("tool_features", "calculate_tool_sha256", "tool_notice_sha256"):
            legacy.pop(key)
        assert F.record_treatment_problem(legacy, profile) is None, arm
    pe2 = _profile("pe2")
    assert "tool features" in F.record_treatment_problem(_record(_profile("pe")), pe2)


def test_diagnostics_read_flat_people_by_their_default_names():
    household = {
        "people": [
            {"role": "head", "facts": {}},
            {"role": "spouse", "facts": {}},
            {"name": "Kid", "role": "dependent", "facts": {}},
            {"role": "dependent", "facts": {}},
        ]
    }
    names = F._person_names({"household": json.dumps(household)})
    assert names == ["head", "spouse", "Kid", "dependent_2"]


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


@pytest.mark.slow
def test_a_household_described_from_its_prompt_computes_the_same():
    """Differential, with the labels feature alone: each of 30 frozen-board
    households described flat from the facts its v2-pilot prompt shows, each
    under the label the prompt shows it under (dropped facts included), with
    the state and roles the prompt gives, computes every board output as the
    benchmark's own situation does. The take-up conventions, which the prompt
    states in words, are set under their engine names."""
    import household_set as hs
    import pandas as pd
    from policyengine_us import Simulation

    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output
    from policybench.scenarios import (
        DEFAULT_TAKEUP_INPUTS,
        is_excluded_prompt_input_name,
    )

    system = F.build_tool_system(reform=True)
    registry = F.build_registry(system)
    reference = pd.read_csv(hs.FROZEN_BOARD / "reference_outputs.csv")
    variables = reference.groupby("scenario_id").variable.agg(list)
    shown = set()

    def label(field, value):
        value_type = (
            "bool"
            if isinstance(value, bool)
            else ("str" if isinstance(value, str) else "float")
        )
        written = F.rendered_labels(field, value_type)[-1]
        shown.add((field, written))
        return written

    def prompt_facts(inputs):
        return {
            label(k, v): v
            for k, v in inputs.items()
            if not is_excluded_prompt_input_name(k)
        }

    checked = 0
    for scenario in hs.load_scenarios(hs.FROZEN_BOARD)[:30]:
        couple = scenario.marital_couple() or ()
        head = couple[0] if couple else scenario.adults[0].name
        people = []
        for person in scenario.all_people:
            facts = {"age": person.age}
            if person.name.startswith("adult") or abs(person.employment_income) > 1e-6:
                facts[label("employment_income", 1.0)] = person.employment_income
            facts |= prompt_facts(person.inputs)
            facts |= DEFAULT_TAKEUP_INPUTS["person"]
            role = (
                "head"
                if person.name == head
                else ("spouse" if person.name in couple else "dependent")
            )
            people.append({"name": person.name, "role": role, "facts": facts})
        household_facts = {}
        for inputs in (
            scenario.tax_unit_inputs,
            scenario.spm_unit_inputs,
            scenario.household_inputs,
        ):
            household_facts |= prompt_facts(inputs)
        for entity in ("tax_unit", "spm_unit", "household"):
            household_facts |= DEFAULT_TAKEUP_INPUTS[entity]
        household = {
            "state": scenario.state,
            "people": people,
            "household_facts": household_facts,
        }
        request, error = F.normalize_request(
            {"household": json.dumps(household), "variables": ["snap"]},
            registry,
            features=frozenset({F.FLAT, F.LABELS}),
        )
        assert error is None, (scenario.id, error)
        own = Simulation(
            tax_benefit_system=system, situation=hs.situation_for(scenario)
        )
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
    worded = {w for f, w in shown if w != f.replace("_", " ")}
    assert checked > 300 and len(worded) > 10, (checked, sorted(worded))
    # No label a US prompt can show names two of this engine's inputs.
    ambiguous = {
        key: targets
        for key, targets in F.prompt_labels().items()
        if len({e for e, dropped in targets if not dropped and e in registry}) > 1
    }
    assert not ambiguous, ambiguous
