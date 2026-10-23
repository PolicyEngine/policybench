"""The calculator's tool version 2 (the pe2 arm).

Version 2 reads the names the prompt uses (labels written with spaces, and the
benchmark's output keys), redirects a contribution set as the realized amount
to its ``_desired`` input, flags an input that replaces a formula, places an
input set on another entity where exactly one unit holds it, and explains a
variable on request. Version 1 must behave exactly as before.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import tool_pilot_argon as pilot  # noqa: E402

V = pilot.VariableInfo
REGISTRY = {
    "age": V("person", "int", "age", "year"),
    "employment_income": V("person", "float", "employment income", "year"),
    "rent": V("person", "float", "rent", "year"),
    "traditional_401k_contributions": V(
        "person", "float", "401(k)", "year", computed=True
    ),
    "traditional_401k_contributions_desired": V(
        "person", "float", "401(k) asked", "year"
    ),
    "is_medicaid_eligible": V("person", "bool", "Medicaid", "year", computed=True),
    "snap": V("spm_unit", "float", "SNAP", "month", computed=True),
    "free_school_meals": V("spm_unit", "float", "free meals", "year", computed=True),
    "qualified_passenger_vehicle_loan_interest": V(
        "household", "float", "car loan interest", "year"
    ),
    "state_code": V("household", "Enum", "state", "year", ("CA", "TX")),
    "filing_status": V(
        "tax_unit", "Enum", "filing status", "year", ("SINGLE", "JOINT"), True
    ),
}


def _situation(**overrides):
    base = {
        "people": {
            "head": {"age": {"2026": 40}, "employment_income": 30000},
            "kid": {"age": {"2026": 8}},
        },
        "spm_units": {"spm": {"members": ["head", "kid"]}},
        "households": {"h": {"members": ["head", "kid"], "state_code": "CA"}},
    }
    base.update(overrides)
    return base


def _call(situation, variables=("snap",), **extra):
    return {"situation": json.dumps(situation), "variables": list(variables), **extra}


def _v2(args):
    return pilot.normalize_request(args, REGISTRY, 2)


def test_version_1_still_refuses_what_version_2_reads():
    situation = _situation()
    situation["people"]["head"]["traditional 401k contributions desired"] = 1000
    situation["people"]["head"]["qualified_passenger_vehicle_loan_interest"] = 500
    request, error = pilot.normalize_request(
        _call(situation, ("free_school_meals_eligible",), explain=["snap"]), REGISTRY
    )
    assert request is None
    problems = " ".join(error["problems"])
    assert "unknown arguments: explain" in problems
    assert "unknown variable 'traditional 401k contributions desired'" in problems
    assert "is a household variable; set it under households" in problems
    assert "unknown variable 'free_school_meals_eligible'" in problems


def test_version_2_reads_a_label_written_with_spaces():
    situation = _situation()
    situation["people"]["head"]["Traditional 401k contributions desired"] = 1000
    request, error = _v2(_call(situation))
    assert error is None
    head = request["situation"]["people"]["head"]
    assert head["traditional_401k_contributions_desired"] == {"2026": 1000}
    assert any(
        "as traditional_401k_contributions_desired" in n for n in request["notes"]
    )


def test_version_2_sets_the_asked_amount_for_a_computed_contribution():
    situation = _situation()
    situation["people"]["head"]["traditional_401k_contributions"] = 18523
    request, error = _v2(_call(situation))
    assert error is None
    head = request["situation"]["people"]["head"]
    assert "traditional_401k_contributions" not in head
    assert head["traditional_401k_contributions_desired"] == {"2026": 18523}
    assert any("before limits" in n for n in request["notes"])


def test_version_2_flags_an_input_that_replaces_a_formula():
    situation = _situation()
    situation["spm_units"]["spm"]["snap"] = 100
    request, error = _v2(_call(situation))
    assert error is None
    assert request["situation"]["spm_units"]["spm"]["snap"] == {"2026": 100}
    assert any("snap is computed by the engine" in n for n in request["notes"])


def test_version_2_moves_a_household_input_to_the_persons_household():
    situation = _situation()
    situation["people"]["head"]["qualified_passenger_vehicle_loan_interest"] = 500
    request, error = _v2(_call(situation))
    assert error is None
    assert request["situation"]["households"]["h"][
        "qualified_passenger_vehicle_loan_interest"
    ] == {"2026": 500}
    assert (
        "qualified_passenger_vehicle_loan_interest"
        not in (request["situation"]["people"]["head"])
    )
    assert any(
        "moved qualified_passenger_vehicle_loan_interest" in n for n in request["notes"]
    )


def test_version_2_makes_the_one_unit_the_engine_would_when_a_group_is_left_out():
    situation = _situation()
    del situation["households"]
    situation["people"]["kid"]["state_code"] = "TX"
    request, error = _v2(_call(situation))
    assert error is None
    households = request["situation"]["households"]
    assert households == {
        "all": {"members": ["head", "kid"], "state_code": {"2026": "TX"}}
    }


def test_version_2_moves_a_person_input_off_a_one_person_unit_only():
    one = _situation(
        spm_units={"a": {"members": ["head"], "rent": 9000}, "b": {"members": ["kid"]}}
    )
    request, error = _v2(_call(one))
    assert error is None
    assert request["situation"]["people"]["head"]["rent"] == {"2026": 9000}
    both = _situation()
    both["spm_units"]["spm"]["rent"] = 9000
    request, error = _v2(_call(both))
    assert request is None
    assert any("set it on one person" in p for p in error["problems"])


def test_version_2_refuses_two_different_values_for_one_input():
    situation = _situation()
    situation["households"]["h"]["qualified_passenger_vehicle_loan_interest"] = 400
    situation["people"]["head"]["qualified_passenger_vehicle_loan_interest"] = 500
    request, error = _v2(_call(situation))
    assert request is None
    assert any("set twice with different values" in p for p in error["problems"])


def test_version_2_refuses_a_group_input_no_single_unit_holds():
    situation = _situation(
        households={"h1": {"members": ["head"]}, "h2": {"members": ["kid"]}},
        tax_units={"t": {"members": ["head", "kid"], "state_code": "CA"}},
    )
    request, error = _v2(_call(situation))
    assert request is None
    assert any("no single unit there holds" in p for p in error["problems"])


def test_version_2_reads_output_keys_as_their_engine_variables():
    request, error = _v2(
        _call(_situation(), ("free_school_meals_eligible", "head_medicaid_eligible"))
    )
    assert error is None
    assert request["variables"] == ["free_school_meals", "is_medicaid_eligible"]
    notes = " ".join(request["notes"])
    assert "1 when free_school_meals is above 0" in notes
    assert "is_medicaid_eligible for the person the key names (head)" in notes


def test_version_2_explains_at_most_three_known_variables():
    request, error = _v2(_call(_situation(), explain=["snap", "free school meals"]))
    assert error is None
    assert request["explain"] == ["snap", "free_school_meals"]
    request, error = _v2(_call(_situation(), explain=["snap", "a", "b", "c"]))
    assert request is None
    assert any("explain at most 3" in p for p in error["problems"])
    request, error = _v2(_call(_situation(), explain=["no_such_thing"]))
    assert request is None
    assert any("explain: unknown variable" in p for p in error["problems"])


@given(st.sampled_from(sorted(REGISTRY)), st.sampled_from([" ", "  ", "-", " - "]))
def test_a_label_written_with_any_separator_reads_back_to_its_name(name, separator):
    written = name.replace("_", separator).upper()
    resolved, note = pilot.resolve_name(written, REGISTRY, output_names=False)
    assert resolved == name
    assert (note is None) == (written == name)


def test_the_stated_engine_follows_the_board_and_defaults_to_the_frozen_one():
    profile = pilot.ModelProfile("m", "gpt-x", "chat", "tool", arm="pe")
    frozen_notice = profile.notice
    frozen_schema = pilot.calculate_tool_schema(1)
    assert "policyengine-us 2.41.0" in frozen_notice
    try:
        pilot.set_stated_engine("2.60.4")
        assert "policyengine-us 2.60.4" in profile.notice
        assert "2.41.0" not in profile.notice
        assert (
            "policyengine-us 2.60.4"
            in pilot.calculate_tool_schema(2)["function"]["description"]
        )
    finally:
        pilot.set_stated_engine(pilot.REFERENCE_ENGINE)
    assert profile.notice == frozen_notice
    assert pilot.calculate_tool_schema(1) == frozen_schema


def test_the_pe2_arm_offers_tool_version_2():
    profile = pilot.ModelProfile("m", "gpt-x", "chat", "tool", arm="pe2")
    assert profile.uses_calculator and not profile.uses_web
    assert profile.tool_version == 2
    assert profile.notice == pilot.TOOL_NOTICE_V2
    assert "explain" in profile.notice
    assert profile.arm2_label == "m+pe-tool-v2"
    json_profile = pilot.ModelProfile("m", "claude-x", "chat", "json", arm="pe2")
    assert json_profile.notice.endswith("single JSON object described above.")
    for arm in ("pe", "web+pe"):
        assert (
            pilot.ModelProfile("m", "gpt-x", "chat", "tool", arm=arm).tool_version == 1
        )
    v2 = pilot.calculate_tool_schema(2)["function"]
    assert "explain" in v2["parameters"]["properties"]
    assert (
        "explain"
        not in pilot.calculate_tool_schema(1)["function"]["parameters"]["properties"]
    )


def _echo_worker(conn, fix_path, reform):
    conn.send(("ready", None))
    while True:
        args = conn.recv()
        if args is None:
            return
        conn.send(("ok", {"received": args}))


def test_the_pool_tells_its_workers_the_tool_version():
    pool = pilot.ToolPool(
        size=1, timeout=5.0, worker_target=_echo_worker, tool_version=2
    )
    try:
        result, _ = pool.call({"situation": "{}"})
        assert result == {
            "received": {"__tool_version__": 2, "arguments": {"situation": "{}"}}
        }
    finally:
        pool.close()
    pool = pilot.ToolPool(size=1, timeout=5.0, worker_target=_echo_worker)
    try:
        result, _ = pool.call({"situation": "{}"})
        assert result == {"received": {"situation": "{}"}}
    finally:
        pool.close()


@pytest.mark.slow
def test_an_explanation_traces_the_engine_and_cites_its_parameters():
    system = pilot.build_tool_system(reform=True)
    registry = pilot.build_registry(system)
    # Computed: the engine derives it and no stated fact sets it.
    assert registry["snap"].computed and registry["is_medicaid_eligible"].computed
    assert not registry["employment_income"].computed  # summed, but stated
    assert not registry["age"].computed
    assert not registry["takes_up_snap_if_eligible"].computed
    situation = {
        "people": {
            "head": {
                "age": {"2026": 40},
                "employment_income": {"2026": 20000},
                "traditional_401k_contributions": {"2026": 1000},
            }
        },
        "households": {"h": {"members": ["head"], "state_code": "TX"}},
    }
    request, error = pilot.normalize_request(
        {
            "situation": json.dumps(situation),
            "variables": ["federal_income_tax_before_refundable_credits"],
            "explain": ["income_tax_before_refundable_credits"],
        },
        registry,
        2,
    )
    assert error is None, error
    assert request["variables"] == ["income_tax_before_refundable_credits"]
    result = pilot.execute_request(system, registry, request)
    if "traditional_401k_contributions_desired" in registry:
        assert any("before limits" in n for n in result["notes"])
    explanation = result["explanations"]["income_tax_before_refundable_credits"]
    assert explanation["steps"][0].startswith(
        "income_tax_before_refundable_credits (2026)"
    )
    assert len(explanation["steps"]) <= pilot.EXPLAIN_MAX_LINES
    assert explanation["parameters"], explanation
    assert not any(
        p["name"].startswith("gov.abolitions.") for p in explanation["parameters"]
    )
    assert any(p["sources"] for p in explanation["parameters"])
    value = result["results"]["income_tax_before_refundable_credits"]["values"]
    assert set(value) == {"0"} or len(value) == 1
