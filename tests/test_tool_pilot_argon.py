"""The tool pilot's validator, conversation loop, scoring and diagnosis.

Every model call is faked. The registry is a small stand-in for the engine's,
so the validator tests need no PolicyEngine system; the tests that build the
real tool system are marked slow.
"""

from __future__ import annotations

import importlib.metadata
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import tool_pilot_argon as pilot  # noqa: E402

from policybench.scenarios import Person, Scenario  # noqa: E402

V = pilot.VariableInfo
REGISTRY = {
    "age": V("person", "int", "age", "year"),
    "employment_income": V("person", "float", "employment income", "year"),
    "is_disabled": V("person", "bool", "is disabled", "year"),
    "is_medicaid_eligible": V("person", "bool", "Medicaid eligible", "year"),
    "snap": V("spm_unit", "float", "SNAP", "month"),
    "takes_up_snap_if_eligible": V("spm_unit", "bool", "takes up SNAP", "year"),
    "income_tax_before_refundable_credits": V(
        "tax_unit", "float", "income tax before refundable credits", "year"
    ),
    "free_school_meals": V("spm_unit", "float", "free school meals", "year"),
    "state_code": V("household", "Enum", "state", "year", ("CA", "CO", "TX")),
    "filing_status": V(
        "tax_unit", "Enum", "filing status", "year", ("SINGLE", "JOINT")
    ),
}


def situation(**overrides):
    base = {
        "people": {
            "head": {"age": {"2026": 40}, "employment_income": 20000},
            "kid": {"age": {"2026": 4}},
        },
        "spm_units": {"spm": {"members": ["head", "kid"]}},
        "households": {"h": {"members": ["head", "kid"], "state_code": "CO"}},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# The validator.
# ---------------------------------------------------------------------------


def test_accepts_a_household_and_yearizes_bare_values():
    request, error = pilot.normalize_request(
        {"situation": json.dumps(situation()), "variables": ["snap"]}, REGISTRY
    )
    assert error is None
    people = request["situation"]["people"]
    assert people["head"]["employment_income"] == {"2026": 20000}
    assert request["situation"]["households"]["h"]["state_code"] == {"2026": "CO"}
    assert request["variables"] == ["snap"]
    assert request["period"] == "2026"


def test_a_bare_value_takes_the_calls_period():
    request, error = pilot.normalize_request(
        {"situation": situation(), "variables": ["snap"], "period": "2026-03"},
        REGISTRY,
    )
    assert error is None
    assert request["situation"]["people"]["head"]["employment_income"] == {
        "2026-03": 20000
    }


@pytest.mark.parametrize(
    "args, fragment",
    [
        ({"situation": "{not json", "variables": ["snap"]}, "not valid JSON"),
        ({"situation": situation(), "variables": ["snapp"]}, "Close matches: snap"),
        (
            {"situation": situation(axes=[[{"name": "age"}]]), "variables": ["snap"]},
            "remove axes",
        ),
        (
            {
                "situation": situation(
                    people={"head": {"snap": {"2026": 1}}},
                    spm_units={"s": {"members": ["head"]}},
                    households={"h": {"members": ["head"]}},
                ),
                "variables": ["snap"],
            },
            "snap is a spm_unit variable; set it under spm_units",
        ),
        (
            {
                "situation": situation(spm_units={"s": {"members": ["ghost"]}}),
                "variables": ["snap"],
            },
            "member 'ghost' is not in people",
        ),
        (
            {
                "situation": situation(
                    spm_units={
                        "a": {"members": ["head"]},
                        "b": {"members": ["head", "kid"]},
                    }
                ),
                "variables": ["snap"],
            },
            "head is already in spm_units.a",
        ),
        (
            {
                "situation": situation(people={"head": {"age": {"26": 40}}}),
                "variables": ["age"],
            },
            "period '26'",
        ),
        (
            {
                "situation": situation(people={"head": {"age": {"2026": [40]}}}),
                "variables": ["age"],
            },
            "must be a number",
        ),
        (
            {
                "situation": situation(
                    people={"head": {"employment_income": {"2026": float("nan")}}}
                ),
                "variables": ["age"],
            },
            "not a finite number",
        ),
        (
            {
                "situation": situation(
                    people={"head": {"employment_income": {"2026": True}}}
                ),
                "variables": ["age"],
            },
            "takes a number",
        ),
        (
            {
                "situation": situation(
                    households={"h": {"members": ["head", "kid"], "state_code": "ZZ"}}
                ),
                "variables": ["snap"],
            },
            "takes one of: CA, CO, TX",
        ),
        ({"situation": situation(), "variables": []}, "non-empty list"),
        (
            {"situation": situation(), "variables": ["snap"], "period": "next year"},
            "must be a year",
        ),
        ({"situation": situation(), "variables": ["snap"], "code": "x"}, "unknown"),
        ({"situation": {"people": {}}, "variables": ["snap"]}, "non-empty object"),
    ],
)
def test_rejects_with_a_specific_problem(args, fragment):
    request, error = pilot.normalize_request(args, REGISTRY)
    assert request is None
    assert error["error"] == "validation"
    assert any(fragment in problem for problem in error["problems"]), error


def test_too_many_variables_are_refused():
    names = [f"v{i}" for i in range(pilot.MAX_VARIABLES + 1)]
    registry = {**REGISTRY, **{n: V("person", "float") for n in names}}
    _, error = pilot.normalize_request(
        {"situation": situation(), "variables": names}, registry
    )
    assert any("at most" in p for p in error["problems"])


json_scalars = st.none() | st.booleans() | st.integers() | st.floats() | st.text()
json_values = st.recursive(
    json_scalars,
    lambda children: (
        st.lists(children, max_size=4)
        | st.dictionaries(
            st.sampled_from([*REGISTRY, "members", "people", "2026", "x", "axes"]),
            children,
            max_size=4,
        )
    ),
    max_leaves=25,
)


@settings(max_examples=300, deadline=None)
@given(args=json_values)
def test_validator_never_raises_on_arbitrary_json(args):
    """Invariant: any JSON value gets exactly one of a request or an error."""
    request, error = pilot.normalize_request(args, REGISTRY)
    assert (request is None) != (error is None)


PERSON_NAMES = st.sampled_from(["head", "kid", "x"])
OTHER_NAMES = st.sampled_from([*REGISTRY, "nope", "members"])
# Mostly plausible values, so a good share of calls is accepted, plus
# arbitrary JSON scalars so the type checks are exercised too.
PLAUSIBLE = st.one_of(
    st.integers(min_value=0, max_value=120),
    st.floats(min_value=0, max_value=1e6, allow_nan=False),
    st.booleans(),
    st.sampled_from(["CO", "TX", "SINGLE", "JOINT"]),
)
SCALARS = st.one_of(PLAUSIBLE, PLAUSIBLE, PLAUSIBLE, json_scalars)
PERIOD_VALUES = st.one_of(
    SCALARS,
    st.dictionaries(st.sampled_from(["2026", "2026-01", "26"]), SCALARS, max_size=2),
)


def names_on(entity: str) -> list[str]:
    return [n for n, info in REGISTRY.items() if info.entity == entity]


def typed_value(name: str):
    """A value of the variable's own type, so a group input can be valid."""
    info = REGISTRY.get(name)
    if info is None:
        return SCALARS
    if info.value_type == "Enum":
        return st.sampled_from(list(info.possible_values))
    if info.value_type in {"float", "int"}:
        return st.one_of(
            st.integers(min_value=0, max_value=120),
            st.floats(min_value=0, max_value=1e6, allow_nan=False),
        )
    if info.value_type == "bool":
        return st.booleans()
    return SCALARS


def inputs_for(entity: str):
    """Mostly typed inputs on the entity's own variables, with some misplaced
    or unknown names and arbitrary values so the rejections are exercised."""
    own = names_on(entity)
    wrong = st.tuples(OTHER_NAMES, PERIOD_VALUES)
    if not own:  # families and marital units carry no inputs in REGISTRY
        return st.one_of(
            st.just({}), st.just({}), st.lists(wrong, max_size=1).map(dict)
        )
    right = st.sampled_from(own).flatmap(
        lambda name: st.one_of(
            typed_value(name),
            st.dictionaries(
                st.sampled_from(["2026", "2026-01"]),
                typed_value(name),
                min_size=1,
                max_size=2,
            ),
        ).map(lambda value: (name, value))
    )
    return st.lists(st.one_of(right, right, right, wrong), max_size=2).map(dict)


def situations():
    """People first, then each group's units, mostly over unique, non-empty
    subsets of those people; some memberships are invalid (a ghost, a person
    twice or in two units), so the membership checks can fail."""

    def with_groups(people):
        names = sorted(people)
        valid = st.lists(
            st.sampled_from(names), min_size=1, max_size=len(names), unique=True
        )
        invalid = st.lists(st.sampled_from([*names, "ghost"]), max_size=3)

        def unit(entity):
            return st.builds(
                lambda members, inputs: {"members": members, **inputs},
                st.one_of(valid, valid, valid, invalid),
                inputs_for(entity),
            )

        groups = st.fixed_dictionaries(
            {},
            optional={
                group: st.dictionaries(
                    st.sampled_from(["u1", "u1", "u2"]), unit(entity), min_size=1
                )
                for group, entity in pilot.GROUPS.items()
            },
        )
        return groups.map(lambda g: {"people": people, **g})

    return st.dictionaries(
        PERSON_NAMES, inputs_for("person"), min_size=1, max_size=3
    ).flatmap(with_groups)


SITUATIONS = situations()
CALLS = st.fixed_dictionaries(
    {
        "situation": st.one_of(SITUATIONS, SITUATIONS.map(json.dumps)),
        "variables": st.lists(OTHER_NAMES, min_size=1, max_size=4),
    },
    optional={"period": st.sampled_from(["2026", "2026-03", "bad"])},
)


def test_validator_accepts_only_known_names_on_their_entities():
    """Invariant: an accepted call names only registry variables, each on its
    own entity, with valid periods, and every unit member is a listed person
    in at most one unit of its group. The strategy reaches acceptance, with
    groups and group inputs, often enough to check it."""
    accepted = []
    with_units = []
    with_group_inputs = []

    @settings(max_examples=1000, deadline=None, derandomize=True, database=None)
    @given(args=CALLS)
    def check(args):
        request, error = pilot.normalize_request(args, REGISTRY)
        assert (request is None) != (error is None)
        if request is None:
            return
        accepted.append(1)
        situation = request["situation"]
        for name in request["variables"]:
            assert name in REGISTRY
        for person in situation["people"].values():
            for name, periods in person.items():
                assert REGISTRY[name].entity == "person"
                assert periods and all(pilot.PERIOD_RE.match(k) for k in periods)
        group_input = False
        if any(situation.get(group) for group in pilot.GROUPS):
            with_units.append(1)
        for group, entity in pilot.GROUPS.items():
            seen = set()
            for unit in situation.get(group, {}).values():
                for member in unit["members"]:
                    assert member in situation["people"] and member not in seen
                    seen.add(member)
                for name, periods in unit.items():
                    if name != "members":
                        group_input = True
                        assert REGISTRY[name].entity == entity
                        assert all(pilot.PERIOD_RE.match(k) for k in periods)
        if group_input:
            with_group_inputs.append(1)

    check()
    # Floors well under the worst of four seeds measured (322 accepted, 58
    # with units, 14 with group inputs), so a Hypothesis upgrade or an edit to
    # this function cannot quietly make the checks vacuous or flaky.
    assert len(accepted) >= 100, f"only {len(accepted)} of 1000 calls were accepted"
    assert len(with_units) >= 20, f"only {len(with_units)} accepted calls had units"
    assert len(with_group_inputs) >= 5, (
        f"only {len(with_group_inputs)} accepted calls carried a group input"
    )


def test_deeply_nested_arguments_are_refused_not_raised():
    # Deep enough to raise RecursionError (not JSONDecodeError) in json.loads,
    # yet under the size cap, so the RecursionError path is what refuses it.
    deep = "[" * 100_000 + "]" * 100_000
    with pytest.raises(RecursionError):
        json.loads(deep)
    for text in (deep, '{"situation": ' + deep + "}"):
        request, error = pilot.normalize_request(text, REGISTRY)
        assert request is None and error["error"] == "validation"
    request, error = pilot.normalize_request(
        {"situation": "[" * 100_000 + "]" * 100_000, "variables": ["snap"]}, REGISTRY
    )
    assert request is None and error["error"] == "validation"


@settings(max_examples=200, deadline=None)
@given(
    income=st.floats(min_value=0, max_value=1e7, allow_nan=False),
    age=st.integers(min_value=0, max_value=110),
    period=st.sampled_from(["2026", "2025", "2026-01", "2026-12"]),
)
def test_valid_households_round_trip(income, age, period):
    sit = situation(people={"head": {"age": age, "employment_income": income}})
    sit["spm_units"] = {"spm": {"members": ["head"]}}
    sit["households"] = {"h": {"members": ["head"], "state_code": "TX"}}
    request, error = pilot.normalize_request(
        {"situation": sit, "variables": ["snap"], "period": period}, REGISTRY
    )
    assert error is None
    assert request["situation"]["people"]["head"] == {
        "age": {period: age},
        "employment_income": {period: income},
    }


def test_execute_request_reads_entity_names_and_reports_engine_errors():
    class FakeArray(list):
        pass

    class FakeSimulation:
        def __init__(self, tax_benefit_system, situation):
            if "bad" in situation["people"]:
                raise ValueError("bad person")
            self.populations = {
                "person": SimpleNamespace(ids=list(situation["people"])),
                "spm_unit": SimpleNamespace(ids=["spm"]),
            }

        def calculate(self, name, period):
            if name == "snap":
                return FakeArray([1234.567])
            return FakeArray([True, False])

    request = {
        "situation": situation(),
        "variables": ["snap", "is_medicaid_eligible"],
        "period": "2026",
    }
    result = pilot.execute_request(None, REGISTRY, request, FakeSimulation)
    assert result["results"]["snap"]["values"] == {"spm": 1234.57}
    assert result["results"]["is_medicaid_eligible"]["values"] == {
        "head": True,
        "kid": False,
    }
    bad = {
        "situation": {"people": {"bad": {}}},
        "variables": ["snap"],
        "period": "2026",
    }
    error = pilot.execute_request(None, REGISTRY, bad, FakeSimulation)
    assert error["error"] == "engine" and "bad person" in error["message"]


# ---------------------------------------------------------------------------
# The conversation loop, with a faked model.
# ---------------------------------------------------------------------------


def make_scenario() -> Scenario:
    return Scenario(
        id="scenario_t",
        state="CO",
        filing_status="single",
        adults=[Person(name="head", age=40, employment_income=20000)],
        children=[Person(name="child1", age=4, employment_income=0)],
    )


VARIABLES = ["snap", "federal_income_tax_before_refundable_credits"]


def tool_call(name, arguments, call_id):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def response(calls, prompt=1000, completion=200, reasoning=50, content=None):
    message = SimpleNamespace(
        role="assistant", content=content, tool_calls=calls, function_call=None
    )
    usage = SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        reasoning_tokens=reasoning,
        prompt_tokens_details=SimpleNamespace(cached_tokens=0),
        completion_tokens_details=None,
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls")],
        usage=usage,
        model="gemini-4-argon",
    )


def submit(values: dict, call_id="s1"):
    outputs = {
        k: {"value": v, "explanation": f"From the tool. value = {v}"}
        for k, v in values.items()
    }
    return tool_call("submit_outputs", {"outputs": outputs}, call_id)


def calculate(call_id="c1"):
    return tool_call(
        pilot.TOOL_NAME,
        {"situation": json.dumps(situation()), "variables": ["snap"]},
        call_id,
    )


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, **kwargs):
        self.requests.append(
            {
                **kwargs,
                "messages": json.loads(json.dumps(kwargs["messages"], default=str)),
            }
        )
        return self.responses.pop(0)


def fake_tool(args):
    return {
        "results": {
            "snap": {"entity": "spm_unit", "period": "2026", "values": {"spm": 2553.0}}
        }
    }, 0.25


def test_a_tool_turn_then_the_answer_tool():
    model = FakeModel(
        [response([calculate()]), response([submit({"snap": 2553, VARIABLES[1]: 0})])]
    )
    spend = pilot.Spend(50.0)
    record = pilot.run_household(make_scenario(), VARIABLES, fake_tool, model, spend)
    assert record["status"] == "complete"
    assert record["predictions"] == {"snap": 2553.0, VARIABLES[1]: 0.0}
    assert record["tool_turns"] == 1 and not record["cap_hit"]
    first, second = model.requests
    assert first["tool_choice"] == "required"
    assert [t["function"]["name"] for t in first["tools"]] == [
        pilot.TOOL_NAME,
        "submit_outputs",
    ]
    assert first["messages"][0]["content"].endswith(pilot.TOOL_NOTICE)
    tool_messages = [m for m in second["messages"] if m["role"] == "tool"]
    assert json.loads(tool_messages[0]["content"])["results"]["snap"]["values"] == {
        "spm": 2553.0
    }
    totals = record["totals"]
    assert totals["model_turns"] == 2 and totals["tool_calls"] == 1
    assert totals["tool_seconds"] == pytest.approx(0.25)
    # Invariant: the household's cost is the sum of its turns' costs, and the
    # shared spend counter saw exactly that.
    assert totals["cost_usd"] == pytest.approx(
        sum(t["total_cost_usd"] for t in record["turns"])
    )
    assert spend.spent_usd == pytest.approx(totals["cost_usd"])
    # $2 / $10 per 1M at 1,000 input and 200 output tokens a turn.
    assert totals["cost_usd"] == pytest.approx(2 * (1000 * 2 + 200 * 10) / 1e6)


def test_the_prompt_is_the_board_prompt_plus_the_notice():
    from policybench.eval_no_tools import _chat_completion_request_kwargs

    scenario = make_scenario()
    board_messages, _ = _chat_completion_request_kwargs(
        scenario, VARIABLES, "gemini/gemini-4-argon"
    )
    prompt, kwargs = pilot.build_initial_request(scenario, VARIABLES)
    assert prompt == board_messages[0]["content"] + pilot.TOOL_NOTICE
    assert "caching" not in kwargs and "messages" not in kwargs
    assert kwargs["_answer_tool"]["function"]["name"] == "submit_outputs"


def test_the_cap_forces_the_answer_tool():
    cap = 3
    model = FakeModel(
        [response([calculate(f"c{i}")]) for i in range(cap)]
        + [response([submit({"snap": 1, VARIABLES[1]: 2})])]
    )
    record = pilot.run_household(
        make_scenario(), VARIABLES, fake_tool, model, pilot.Spend(50.0), turn_cap=cap
    )
    assert record["status"] == "complete" and record["cap_hit"]
    assert [r["tool_choice"] for r in model.requests[:cap]] == ["required"] * cap
    assert model.requests[cap]["tool_choice"] == {
        "type": "function",
        "function": {"name": "submit_outputs"},
    }


def test_extra_calculations_in_one_turn_are_not_run():
    calls = [calculate(f"c{i}") for i in range(pilot.MAX_CALCULATIONS_PER_TURN + 2)]
    ran = []

    def counting_tool(args):
        ran.append(args)
        return fake_tool(args)

    model = FakeModel(
        [response(calls), response([submit({"snap": 1, VARIABLES[1]: 2})])]
    )
    record = pilot.run_household(
        make_scenario(), VARIABLES, counting_tool, model, pilot.Spend(50.0)
    )
    assert len(ran) == pilot.MAX_CALCULATIONS_PER_TURN
    results = [c["result"] for c in record["turns"][0]["calls"]]
    assert sum(r.get("error") == "not_run" for r in results) == 2


def test_a_missing_output_gets_a_repair_turn_for_it_alone():
    model = FakeModel(
        [response([submit({"snap": 10})]), response([submit({VARIABLES[1]: 5}, "s2")])]
    )
    record = pilot.run_household(
        make_scenario(), VARIABLES, fake_tool, model, pilot.Spend(50.0)
    )
    assert record["status"] == "complete" and record["repair_rounds"] == 1
    repair = model.requests[1]
    answer_tool = repair["tools"][1]["function"]["parameters"]
    assert list(answer_tool["properties"]["outputs"]["properties"]) == [VARIABLES[1]]
    assert record["predictions"] == {"snap": 10.0, VARIABLES[1]: 5.0}


def test_an_exhausted_budget_stops_before_calling():
    model = FakeModel([])
    record = pilot.run_household(
        make_scenario(), VARIABLES, fake_tool, model, pilot.Spend(1.0, spent_usd=2.0)
    )
    assert record["status"] == "budget_stop" and model.requests == []


def test_a_provider_error_ends_the_household(monkeypatch):
    monkeypatch.setattr(pilot, "MAX_PROVIDER_ATTEMPTS", 1)

    def failing(**kwargs):
        raise RuntimeError("boom")

    record = pilot.run_household(
        make_scenario(), VARIABLES, fake_tool, failing, pilot.Spend(50.0)
    )
    assert record["status"] == "provider_error" and "boom" in record["error"]


# ---------------------------------------------------------------------------
# Scoring and diagnosis.
# ---------------------------------------------------------------------------


def test_hit_is_the_boards_exact_rule():
    assert pilot.hit("snap", 100.9, 100.0)
    assert not pilot.hit("snap", 101.5, 100.0)
    assert pilot.hit("head_medicaid_eligible", 1, 1.0)
    assert not pilot.hit("head_medicaid_eligible", 0, 1.0)
    assert not pilot.hit("snap", None, 1.0)
    assert not pilot.hit("snap", float("nan"), 1.0)


def call_record(
    values: dict, period="2026", people=("head", "kid"), entity="x", age=30
):
    sit = situation()
    sit["people"] = {p: {"age": age} for p in people}
    return {
        "name": pilot.TOOL_NAME,
        "arguments": json.dumps(
            {"situation": json.dumps(sit), "variables": list(values)}
        ),
        "result": {
            "results": {
                name: {"entity": entity, "period": period, "values": vals}
                for name, vals in values.items()
            }
        },
    }


def household(calls, cap_hit=False):
    return {"turns": [{"calls": calls}], "cap_hit": cap_hit}


def test_tool_value_maps_people_by_position_and_aggregates_groups():
    scenario = make_scenario()
    call = call_record(
        {
            "is_medicaid_eligible": {"head": False, "kid": True},
            "free_school_meals": {"spm": 0.0, "spm2": 12.0},
        }
    )
    assert (
        pilot.tool_value_for_output(call, scenario, "child1_medicaid_eligible") == 1.0
    )
    assert pilot.tool_value_for_output(call, scenario, "head_medicaid_eligible") == 0.0
    assert (
        pilot.tool_value_for_output(call, scenario, "free_school_meals_eligible") == 1.0
    )
    monthly = call_record({"snap": {"spm": 200.0}}, period="2026-01")
    assert pilot.tool_value_for_output(monthly, scenario, "snap") is None


@pytest.mark.parametrize(
    "calls, submitted, category",
    [
        ([], 100.0, "tool_error_or_cap"),
        ([call_record({"snap": {"spm": 100.0}})], 100.0, "wrong_input_mapping"),
        ([call_record({"snap": {"spm": 100.0}})], 250.0, "answer_differs_from_tool"),
        (
            [call_record({"snap": {"spm": 9.0}}, period="2026-01")],
            9.0,
            "wrong_variable_or_period",
        ),
        ([call_record({"tanf": {"spm": 9.0}})], 9.0, "wrong_variable_or_period"),
        ([call_record({"snap": {"spm": 100.0}})], None, "no_answer"),
    ],
)
def test_each_miss_gets_its_category(calls, submitted, category):
    verdict = pilot.classify_miss(
        household(calls), make_scenario(), "snap", submitted, 400.0
    )
    assert verdict["category"] == category


@settings(max_examples=200, deadline=None)
@given(
    tool_values=st.lists(
        st.one_of(st.none(), st.floats(min_value=-1e5, max_value=1e5)), max_size=4
    ),
    periods=st.lists(
        st.sampled_from(["2026", "2026-01", "2025"]), min_size=4, max_size=4
    ),
    submitted=st.one_of(st.none(), st.floats(min_value=-1e5, max_value=1e5)),
)
def test_every_miss_lands_in_exactly_one_category(tool_values, periods, submitted):
    """Invariant: classify_miss returns one of MISS_CATEGORIES for any transcript."""
    calls = [
        call_record(
            {"snap": {"spm": v}} if v is not None else {"tanf": {"spm": 1.0}}, p
        )
        for v, p in zip(tool_values, periods)
    ]
    verdict = pilot.classify_miss(
        household(calls), make_scenario(), "snap", submitted, 1e9
    )
    assert verdict["category"] in pilot.MISS_CATEGORIES


def test_situation_diff_matches_people_by_position():
    scenario = make_scenario()
    reference = scenario.to_pe_household()
    model = json.loads(json.dumps(reference))
    model["people"] = {
        "me": dict(model["people"]["head"]),
        "child": dict(model["people"]["child1"]),
    }
    assert pilot.situation_diff(model, reference, scenario) == []
    model["people"]["me"]["employment_income"] = {"2026": 21000}
    diff = pilot.situation_diff(model, reference, scenario)
    assert [(d["variable"], d["model"]) for d in diff] == [
        ("employment_income", {"2026": 21000})
    ]


def test_default_only_differences_are_dropped():
    defaults = {
        "takes_up_snap_if_eligible": True,
        "would_file_taxes_voluntarily": False,
    }
    assert pilot._is_default_only(
        {
            "variable": "takes_up_snap_if_eligible",
            "reference": {"2026": True},
            "model": {},
        },
        defaults,
    )
    assert not pilot._is_default_only(
        {
            "variable": "would_file_taxes_voluntarily",
            "reference": {"2026": True},
            "model": {},
        },
        defaults,
    )


def test_arm1_rescoring_reproduces_the_published_board_row():
    """Differential: the board's analysis on the frozen predictions gives the
    published weighted_exact for Argon (summary_by_model.csv)."""
    from policybench.analysis import analyze_no_tools

    board = pilot.load_board()
    arm1 = pilot.arm1_predictions()
    analysis = analyze_no_tools(
        board["scored"], arm1, scenarios=board["scenarios_frame"]
    )
    row = analysis["model_summary"].set_index("model").loc[pilot.ARM1_LABEL]
    published = pd.read_csv(pilot.SNAPSHOT / "analysis/summary_by_model.csv").set_index(
        "model"
    )
    assert row["weighted_exact"] == pytest.approx(
        published.loc[pilot.ARM1_LABEL, "weighted_exact"], abs=1e-12
    )
    assert len(board["scored"]) == 1935


def test_the_fix_module_is_the_pinned_one():
    assert pilot._sha256(pilot.FIX_MODULE) == pilot.FIX_MODULE_SHA256
    meta = json.loads((pilot.SNAPSHOT / "reference_outputs.csv.meta.json").read_text())
    revision = [
        r
        for r in meta["revisions"]
        if r.get("engine_version") == "policyengine-us 2.41.0"
    ][0]
    pins = {m["module"]: m["sha256"] for m in revision["fix_modules"]}
    assert pins["latest_final.py"] == pilot.FIX_MODULE_SHA256


def _engine_is_reference() -> bool:
    try:
        return importlib.metadata.version("policyengine-us") == pilot.REFERENCE_ENGINE
    except importlib.metadata.PackageNotFoundError:
        return False


@pytest.mark.slow
@pytest.mark.skipif(not _engine_is_reference(), reason="needs policyengine-us 2.41.0")
def test_the_real_tool_runs_a_household_through_the_reference_engine():
    system = pilot.build_tool_system(reform=True)
    registry = pilot.build_registry(system)
    request, error = pilot.normalize_request(
        {
            "situation": json.dumps(
                {
                    "people": {
                        "you": {
                            "age": {"2026": 30},
                            "employment_income": {"2026": 20000},
                        },
                        "kid": {"age": {"2026": 3}},
                    },
                    "households": {
                        "h": {"members": ["you", "kid"], "state_code": "CO"}
                    },
                }
            ),
            "variables": ["snap", "is_medicaid_eligible", "filing_status"],
        },
        registry,
    )
    assert error is None
    result = pilot.execute_request(system, registry, request)["results"]
    assert result["snap"]["entity"] == "spm_unit"
    assert set(result["is_medicaid_eligible"]["values"]) == {"you", "kid"}
    assert isinstance(result["filing_status"]["values"]["tax_unit"], str)
    assert math.isfinite(result["snap"]["values"]["spm_unit"])


def test_payroll_reads_the_equivalent_engine_variable():
    call = call_record({"employee_payroll_tax": {"tax_unit": 1530.0}})
    assert pilot.tool_value_for_output(call, make_scenario(), "payroll_tax") == 1530.0
    assert pilot.tool_value_for_output(call, make_scenario(), "snap") is None


def test_submitted_matches_names_the_tool_values_an_answer_copied():
    calls = [
        call_record({"state_income_tax": {"tax_unit": 812.4}, "snap": {"spm": 5.0}})
    ]
    assert pilot.submitted_matches(calls, 812.0) == ["state_income_tax[tax_unit]@2026"]
    assert pilot.submitted_matches(calls, None) == []


def test_apply_reference_input_sets_removes_and_replaces_units():
    scenario = make_scenario()
    reference = scenario.to_pe_household()
    model = {
        "people": {"me": {"age": {"2026": 40}}, "kid": {"age": {"2026": 4}}},
        "households": {"h": {"members": ["me", "kid"], "state_name": {"2026": "CO"}}},
    }
    set_income = pilot.apply_reference_input(
        model,
        reference,
        {
            "entity": "person",
            "reference_unit": "head",
            "variable": "employment_income",
            "reference": {"2026": 20000},
            "model": {},
        },
    )
    assert set_income["people"]["me"]["employment_income"] == {"2026": 20000}
    assert "employment_income" not in model["people"]["me"]  # the input is not mutated
    dropped = pilot.apply_reference_input(
        model,
        reference,
        {
            "entity": "households",
            "variable": "state_name",
            "reference": {},
            "model": {},
        },
    )
    assert "state_name" not in dropped["households"]["h"]
    units = pilot.apply_reference_input(
        model,
        reference,
        {"entity": "marital_units", "variable": "<units>", "reference": 2, "model": 0},
    )
    members = [u["members"] for u in units["marital_units"].values()]
    assert sorted(members) == sorted(
        [
            [{"head": "me", "child1": "kid"}[m] for m in u["members"]]
            for u in reference["marital_units"].values()
        ]
    )
    assert (
        pilot.apply_reference_input(
            {"people": {"me": {}}},
            reference,
            {
                "entity": "person",
                "reference_unit": "head",
                "variable": "age",
                "reference": {},
            },
        )
        is None
    )


@settings(max_examples=200, deadline=None)
@given(
    first=st.lists(st.floats(min_value=0, max_value=1), min_size=2, max_size=40),
    shift=st.floats(min_value=-0.5, max_value=0.5),
)
@example(first=[0.0, 0.125], shift=1e-12)  # once landed in no category
def test_paired_bootstrap_intervals_bracket_the_means(first, shift):
    """Invariant: each interval contains its point estimate, and identical arms
    give a zero difference interval."""
    a = pd.Series(first)
    b = (a + shift).clip(0, 1)
    out = pilot.paired_bootstrap(a, b, draws=500)
    low, high = out["difference_interval"]
    assert low - 1e-9 <= out["difference"] <= high + 1e-9
    assert out["households_better"] + out["households_worse"] + out[
        "households_same"
    ] == len(a)
    same = pilot.paired_bootstrap(a, a, draws=200)
    assert same["difference_interval"] == [0.0, 0.0]


def test_household_scores_average_to_the_boards_weighted_exact():
    """Differential: the household table reproduces the board's headline."""
    board = pilot.load_board()
    arm1 = pilot.arm1_predictions()
    table = pilot.household_weighted_exact(
        board["scored"], arm1, board["scenarios_frame"]
    )
    published = pd.read_csv(pilot.SNAPSHOT / "analysis/summary_by_model.csv").set_index(
        "model"
    )
    assert table["weighted_exact"].mean() == pytest.approx(
        published.loc[pilot.ARM1_LABEL, "weighted_exact"], abs=1e-12
    )
    assert table["scenario_id"].nunique() == 100


def test_tool_use_summary_counts_failed_first_calls_and_unknown_names():
    bad = {
        "name": pilot.TOOL_NAME,
        "arguments": "{}",
        "result": {
            "error": "validation",
            "problems": [
                "variables: unknown variable 'chip_eligible'. "
                "Close matches: is_chip_eligible.",
                "spm_units.s: auto_loan_balance is a household variable; "
                "set it under households.",
            ],
        },
    }
    good = call_record({"snap": {"spm": 1.0}})
    records = {
        "a": {"turns": [{"calls": [bad]}, {"calls": [good]}]},
        "b": {"turns": [{"calls": [good]}]},
        "c": {"turns": [{"calls": []}]},
    }
    summary = pilot.tool_use_summary(records)
    assert summary["households_using_tool"] == 2
    assert summary["first_call_succeeded"] == 1
    assert summary["households_with_no_successful_call"] == 0
    assert summary["most_common_unknown_names"] == {"chip_eligible": 1}
    assert summary["most_common_misplaced_variables"] == {"auto_loan_balance": 1}
    assert summary["most_requested_variables"] == {"snap": 2}


def test_main_call_is_the_one_that_computed_the_most_outputs():
    full = call_record(
        {"snap": {"spm": 1.0}, "income_tax_before_refundable_credits": {"tu": 2.0}}
    )
    probe = call_record({"snap": {"spm": 3.0}}, people=("head",))
    record = household([full, probe])
    outputs = ["snap", "federal_income_tax_before_refundable_credits"]
    assert pilot.main_call(record, make_scenario(), outputs) is full
    assert pilot.main_call(household([]), make_scenario(), outputs) is None


def test_a_repair_never_overwrites_a_valid_first_value():
    """The board's merge: the first valid value stands even when its
    explanation needed a repair and the repair answers differently."""
    first = tool_call(
        "submit_outputs",
        {
            "outputs": {
                "snap": {"value": 2553, "explanation": "No trailer here."},
                VARIABLES[1]: {"value": 7, "explanation": "Tax. value = 7"},
            }
        },
        "s1",
    )
    repair = tool_call(
        "submit_outputs",
        {"outputs": {"snap": {"value": 0, "explanation": "Recomputed. value = 0"}}},
        "s2",
    )
    model = FakeModel([response([first]), response([repair])])
    record = pilot.run_household(
        make_scenario(), VARIABLES, fake_tool, model, pilot.Spend(50.0)
    )
    assert record["repair_rounds"] == 1 and record["status"] == "complete"
    assert record["predictions"]["snap"] == 2553.0
    assert record["explanations"]["snap"] == "Recomputed. value = 0"
    assert record["repair_disagreements"][0]["variable"] == "snap"


def test_a_truncated_turn_is_retried_at_the_ceiling_and_paid_for():
    truncated = response([calculate()], prompt=1000, completion=16384)
    truncated.choices[0].finish_reason = "length"
    model = FakeModel(
        [
            truncated,
            response([calculate()]),
            response([submit({"snap": 1, VARIABLES[1]: 2})]),
        ]
    )
    spend = pilot.Spend(50.0)
    record = pilot.run_household(make_scenario(), VARIABLES, fake_tool, model, spend)
    budgets = [r.get("max_completion_tokens") for r in model.requests]
    assert budgets[0] < budgets[1] == 32_768
    totals = record["totals"]
    assert totals["truncation_retries"] == 1 and totals["model_turns"] == 2
    assert spend.spent_usd == pytest.approx(totals["cost_usd"])
    assert totals["cost_usd"] == pytest.approx(
        (3000 * 2 + (16384 + 200 + 200) * 10) / 1e6
    )


def test_submit_in_the_same_turn_as_a_calculation_ends_it_without_running_it():
    ran = []

    def counting_tool(args):
        ran.append(args)
        return fake_tool(args)

    model = FakeModel([response([calculate(), submit({"snap": 1, VARIABLES[1]: 2})])])
    record = pilot.run_household(
        make_scenario(), VARIABLES, counting_tool, model, pilot.Spend(50.0)
    )
    assert record["status"] == "complete" and ran == []
    tool_messages = [m for m in record["messages"] if m.get("role") == "tool"]
    assert len(tool_messages) == 2
    assert "not run" in tool_messages[0]["content"]


def test_replies_without_a_function_call_end_at_the_turn_limit():
    model = FakeModel([response([], content="thinking aloud")] * pilot.MAX_TOTAL_TURNS)
    record = pilot.run_household(
        make_scenario(), VARIABLES, fake_tool, model, pilot.Spend(50.0)
    )
    assert record["status"] == "turn_limit"
    assert len(model.requests) == pilot.MAX_TOTAL_TURNS
    assert all(v is None for v in record["predictions"].values())


def test_a_litellm_message_keeps_its_thought_signature_round_trip():
    """Gemini refuses a function-call history without thought signatures; the
    assistant message goes back as litellm returned it."""
    from litellm.types.utils import ChatCompletionMessageToolCall, Function, Message

    call = ChatCompletionMessageToolCall(
        id="call_1__thought__c2lnbmF0dXJl",
        type="function",
        function=Function(name=pilot.TOOL_NAME, arguments='{"variables": ["snap"]}'),
    )
    message = Message(role="assistant", content=None, tool_calls=[call])
    assert pilot._has_thought_signature(message)
    data = pilot._message_dict(message)
    assert data["tool_calls"][0]["id"] == "call_1__thought__c2lnbmF0dXJl"
    assert json.loads(json.dumps(data))["role"] == "assistant"


def _scripted_worker(conn, fix_path, reform):
    conn.send(("ready", None))
    while True:
        args = conn.recv()
        if args is None:
            return
        if args == "sleep":
            import time as _time

            _time.sleep(30)
        if args == "die":
            import os as _os

            _os._exit(1)
        conn.send(("ok", {"results": {"echo": args}}))


def test_the_pool_times_out_and_restarts_a_worker_and_survives_a_crash():
    pool = pilot.ToolPool(size=1, timeout=1.0, worker_target=_scripted_worker)
    try:
        assert pool.call("hi")[0] == {"results": {"echo": "hi"}}
        result, elapsed = pool.call("sleep")
        assert result["error"] == "timeout" and elapsed < 10
        assert pool.call("after-timeout")[0] == {"results": {"echo": "after-timeout"}}
        result, _ = pool.call("die")
        assert result["error"] == "engine"
        assert pool.call("after-crash")[0] == {"results": {"echo": "after-crash"}}
        assert (pool.timeouts, pool.crashes, pool.lost) == (1, 1, 0)
    finally:
        pool.close()


def _record(sid, variables, predictions, status="complete", cost=0.01):
    record = {
        "scenario_id": sid,
        "variables": variables,
        "predictions": predictions,
        "explanations": {v: "x" for v in variables},
        "status": status,
        "turns": [{"total_cost_usd": cost, "calls": []}],
        "cap_hit": False,
        "wall_seconds": 1.0,
    }
    record["totals"] = pilot.household_totals(record)
    return record


def test_score_counts_every_household_and_unparsed_outputs_as_misses(tmp_path):
    """No selection on outcome: an incomplete household stays in both arms,
    its unparsed outputs scored as misses, as the board scores them."""
    import argparse

    board = pilot.load_board()
    reference = board["reference"].set_index(["scenario_id", "variable"])["value"]
    households = tmp_path / "households"
    households.mkdir()
    for sid, status in (("scenario_000", "complete"), ("scenario_001", "incomplete")):
        variables = board["variables"][sid]
        predictions = {v: float(reference[(sid, v)]) for v in variables}
        if status == "incomplete":
            predictions[variables[0]] = None
        record = _record(sid, variables, predictions, status)
        (households / f"{sid}.json").write_text(json.dumps(record))
    pilot.command_score(argparse.Namespace(out_dir=str(tmp_path), complete_only=False))
    score = json.loads((tmp_path / "score.json").read_text())
    assert score["households"] == 2
    scored = board["scored"][
        board["scored"].scenario_id.isin(["scenario_000", "scenario_001"])
    ]
    missed = int(
        (
            (scored.scenario_id == "scenario_001")
            & (scored.variable == board["variables"]["scenario_001"][0])
        ).sum()
    )
    assert score["unweighted_hits"]["arm2"] == len(scored) - missed
    pilot.command_score(argparse.Namespace(out_dir=str(tmp_path), complete_only=True))
    assert json.loads((tmp_path / "score.json").read_text())["households"] == 1


def test_a_resume_reruns_only_infrastructure_failures_and_keeps_their_cost(tmp_path):
    statuses = {
        "a": "complete",
        "b": "incomplete",
        "c": "turn_limit",
        "d": "provider_error",
        "e": "budget_stop",
        "f": "harness_error",
    }
    for sid, status in statuses.items():
        record = _record(sid, ["snap"], {"snap": None}, status, cost=1.0)
        if sid == "d":
            record["prior_attempts"] = [
                {"status": "provider_error", "totals": {"cost_usd": 0.5}}
            ]
        (tmp_path / f"{sid}.json").write_text(json.dumps(record))
    spent, done, previous = pilot.resume_state(tmp_path)
    assert done == {"a", "b", "c"}
    assert set(previous) == set(statuses)
    assert spent == pytest.approx(6.5)


def _dies_on_restart_worker(conn, marker, reform):
    """Starts once; a replacement (the marker exists) exits before ready."""
    from pathlib import Path as _Path

    if _Path(marker).exists():
        import os as _os

        _os._exit(3)
    _Path(marker).touch()
    conn.send(("ready", None))
    while True:
        args = conn.recv()
        if args is None:
            return
        if args == "die":
            import os as _os

            _os._exit(1)
        conn.send(("ok", {"results": {"echo": args}}))


def test_a_replacement_that_fails_to_start_is_counted_lost_not_raised(tmp_path):
    pool = pilot.ToolPool(
        size=1,
        fix_path=tmp_path / "started",
        timeout=1.0,
        worker_target=_dies_on_restart_worker,
        acquire_timeout=0.5,
    )
    try:
        result, _ = pool.call("die")
        assert result["error"] == "engine"
        assert pool.counters() == {"timeouts": 0, "crashes": 1, "lost": 1}
        result, _ = pool.call("anything")
        assert result["error"] == pilot.POOL_UNAVAILABLE
    finally:
        pool.close()


def test_an_unavailable_pool_stops_the_household_as_rerunnable():
    def no_pool(args):
        return {"error": pilot.POOL_UNAVAILABLE, "message": "none"}, 0.5

    model = FakeModel([response([calculate()])])
    record = pilot.run_household(
        make_scenario(), VARIABLES, no_pool, model, pilot.Spend(50.0)
    )
    assert record["status"] == "harness_error"
    assert record["status"] in pilot.RERUNNABLE_STATUSES
    assert len(model.requests) == 1


def test_a_harness_exception_keeps_the_turns_and_their_spend():
    def broken_tool(args):
        raise RuntimeError("tool bug")

    model = FakeModel([response([calculate()])])
    spend = pilot.Spend(50.0)
    record = pilot.run_household(make_scenario(), VARIABLES, broken_tool, model, spend)
    assert record["status"] == "harness_error" and "tool bug" in record["error"]
    assert len(record["turns"]) == 1
    assert record["totals"]["cost_usd"] > 0
    assert record["totals"]["cost_usd"] == pytest.approx(spend.spent_usd)


def test_an_explanation_only_repair_names_the_kept_value():
    first = tool_call(
        "submit_outputs",
        {
            "outputs": {
                "snap": {"value": 2553, "explanation": "No trailer."},
                VARIABLES[1]: {"value": 7, "explanation": "Tax. value = 7"},
            }
        },
        "s1",
    )
    repair = tool_call(
        "submit_outputs",
        {"outputs": {"snap": {"value": 2553, "explanation": "SNAP. value = 2553"}}},
        "s2",
    )
    model = FakeModel([response([first]), response([repair])])
    pilot.run_household(make_scenario(), VARIABLES, fake_tool, model, pilot.Spend(50.0))
    prompt = model.requests[1]["messages"][-1]["content"]
    assert "keep your value 2553" in prompt and "value = 2553" in prompt


@pytest.mark.parametrize(
    "value, text",
    [
        (2553.0, "2553"),
        (12345.67, "12345.67"),
        (1234567.0, "1234567"),
        (1e-05, "0.00001"),
        (-12.5, "-12.5"),
        (0.0, "0"),
    ],
)
def test_plain_number_round_trips_through_the_boards_trailer_pattern(value, text):
    from policybench.eval_no_tools import _extract_terminal_explanation_value

    assert pilot.plain_number(value) == text
    assert _extract_terminal_explanation_value(f"Reason. value = {text}") == value


# ---------------------------------------------------------------------------
# Other models: the Responses API (GPT-6 Sol) and the JSON contract (Opus 5.5).
# ---------------------------------------------------------------------------

SOL = "gpt-6-sol"
OPUS = "claude-opus-5.5"


def test_profiles_follow_the_boards_api_and_answer_contract():
    argon, sol, opus = (pilot.model_profile(n) for n in (pilot.MODEL_NAME, SOL, OPUS))
    assert (argon.api, argon.contract) == ("chat", "tool")
    assert (sol.api, sol.contract) == ("responses", "tool")
    assert (opus.api, opus.contract) == ("chat", "json")
    assert argon.notice == pilot.TOOL_NOTICE and sol.notice == pilot.TOOL_NOTICE
    assert opus.notice == pilot.JSON_TOOL_NOTICE
    assert (argon.arm1_label, argon.arm2_label) == (pilot.ARM1_LABEL, pilot.ARM2_LABEL)
    assert sol.arm2_label == "gpt-6-sol+pe-tool"
    # Both notices describe the same tool; only the way to answer differs.
    shared = "You may call it in up to 8 turns. Then "
    assert pilot.TOOL_NOTICE.split(shared)[0] == pilot.JSON_TOOL_NOTICE.split(shared)[0]


def test_a_responses_prompt_is_the_boards_input_plus_the_notice():
    from policybench.eval_no_tools import _responses_request_kwargs

    scenario = make_scenario()
    profile = pilot.model_profile(SOL)
    _, board = _responses_request_kwargs(scenario, VARIABLES, profile.model_id)
    prompt, kwargs = pilot.build_initial_request(scenario, VARIABLES, profile)
    assert prompt == board["input"] + pilot.TOOL_NOTICE
    assert kwargs["max_output_tokens"] == board["max_output_tokens"]
    assert "input" not in kwargs and "tools" not in kwargs


def test_a_json_contract_prompt_is_the_boards_plus_the_json_notice():
    from policybench.eval_no_tools import _chat_completion_request_kwargs

    scenario = make_scenario()
    profile = pilot.model_profile(OPUS)
    messages, board = _chat_completion_request_kwargs(
        scenario, VARIABLES, profile.model_id
    )
    prompt, kwargs = pilot.build_initial_request(scenario, VARIABLES, profile)
    assert prompt == messages[0]["content"] + pilot.JSON_TOOL_NOTICE
    assert kwargs["_answer_tool"] is None
    assert kwargs["response_format"] == board["response_format"]


def function_call(name, arguments, call_id):
    return SimpleNamespace(
        type="function_call",
        id=f"fc_{call_id}",
        call_id=call_id,
        name=name,
        arguments=json.dumps(arguments),
        status="completed",
    )


def responses_response(items, response_id, prompt=1000, completion=200, cached=0):
    usage = SimpleNamespace(
        input_tokens=prompt,
        output_tokens=completion,
        total_tokens=prompt + completion,
        input_tokens_details=SimpleNamespace(cached_tokens=cached),
        output_tokens_details=SimpleNamespace(reasoning_tokens=50),
    )
    return SimpleNamespace(
        id=response_id,
        output=[SimpleNamespace(type="reasoning", id=f"rs_{response_id}"), *items],
        output_text=None,
        status="completed",
        incomplete_details=None,
        usage=usage,
        model=SOL,
    )


class FakeResponses:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs, default=str)))
        return self.responses.pop(0)


def sol_calculate(call_id):
    return function_call(
        pilot.TOOL_NAME,
        {"situation": json.dumps(situation()), "variables": ["snap"]},
        call_id,
    )


def sol_submit(values, call_id="s1"):
    outputs = {
        k: {"value": v, "explanation": f"From the tool. value = {v}"}
        for k, v in values.items()
    }
    return function_call("submit_outputs", {"outputs": outputs}, call_id)


def test_a_responses_conversation_chains_and_returns_each_call_output():
    model = FakeResponses(
        [
            responses_response([sol_calculate("call_a")], "resp_1"),
            responses_response(
                [sol_submit({"snap": 2553, VARIABLES[1]: 0})], "resp_2", cached=800
            ),
        ]
    )
    spend = pilot.Spend(50.0)
    record = pilot.run_household(
        make_scenario(),
        VARIABLES,
        fake_tool,
        model,
        spend,
        profile=pilot.model_profile(SOL),
    )
    assert record["status"] == "complete" and record["model"] == SOL
    assert record["predictions"] == {"snap": 2553.0, VARIABLES[1]: 0.0}
    first, second = model.requests
    assert first["model"] == SOL and first["tool_choice"] == "required"
    assert first["input"].endswith(pilot.TOOL_NOTICE)
    assert "previous_response_id" not in first
    # The Responses API's flat tool shape.
    assert [t["name"] for t in first["tools"]] == [pilot.TOOL_NAME, "submit_outputs"]
    assert all(t["type"] == "function" for t in first["tools"])
    assert "max_output_tokens" in first and "max_completion_tokens" not in first
    assert second["previous_response_id"] == "resp_1"
    (output,) = second["input"]
    assert output["type"] == "function_call_output" and output["call_id"] == "call_a"
    assert json.loads(output["output"])["results"]["snap"]["values"] == {"spm": 2553.0}
    # $2 / $10 per 1M; GPT cached input bills at a tenth of the input rate.
    totals = record["totals"]
    assert totals["cached_prompt_tokens"] == 800
    assert totals["cost_usd"] == pytest.approx(
        (1000 * 2 + 200 * 10 + (200 * 2 + 800 * 0.2 + 200 * 10)) / 1e6
    )
    assert spend.spent_usd == pytest.approx(totals["cost_usd"])


def test_a_responses_cap_forces_the_answer_function():
    cap = 2
    model = FakeResponses(
        [responses_response([sol_calculate(f"c{i}")], f"r{i}") for i in range(cap)]
        + [responses_response([sol_submit({"snap": 1, VARIABLES[1]: 2})], "rz")]
    )
    record = pilot.run_household(
        make_scenario(),
        VARIABLES,
        fake_tool,
        model,
        pilot.Spend(50.0),
        turn_cap=cap,
        profile=pilot.model_profile(SOL),
    )
    assert record["status"] == "complete" and record["cap_hit"]
    assert model.requests[cap]["tool_choice"] == {
        "type": "function",
        "name": "submit_outputs",
    }
    # The cap notice goes with the last call output, in the same request.
    last = model.requests[cap]["input"]
    assert [i.get("type") for i in last] == ["function_call_output", None]
    assert "used all 2 calculation turns" in last[1]["content"]


def test_a_truncated_responses_turn_is_retried_at_the_ceiling():
    truncated = responses_response([], "r_cut", completion=16384)
    truncated.status = "incomplete"
    truncated.incomplete_details = SimpleNamespace(reason="max_output_tokens")
    model = FakeResponses(
        [truncated, responses_response([sol_submit({"snap": 1, VARIABLES[1]: 2})], "r")]
    )
    record = pilot.run_household(
        make_scenario(),
        VARIABLES,
        fake_tool,
        model,
        pilot.Spend(50.0),
        profile=pilot.model_profile(SOL),
    )
    assert record["status"] == "complete"
    budgets = [r["max_output_tokens"] for r in model.requests]
    assert budgets[0] < budgets[1] == 128_000
    # The retry resends the same turn: no response to chain from yet.
    assert all("previous_response_id" not in r for r in model.requests)
    assert record["totals"]["truncation_retries"] == 1


def json_answer(values, fence=False):
    text = json.dumps(
        {
            k: {"value": v, "explanation": f"From the tool. value = {v}"}
            for k, v in values.items()
        }
    )
    return f"```json\n{text}\n```" if fence else text


def run_opus(model, **kwargs):
    return pilot.run_household(
        make_scenario(),
        VARIABLES,
        kwargs.pop("tool", fake_tool),
        model,
        kwargs.pop("spend", pilot.Spend(50.0)),
        profile=pilot.model_profile(OPUS),
        **kwargs,
    )


def test_a_json_contract_model_calculates_then_answers_in_json():
    model = FakeModel(
        [
            response([calculate()]),
            response([], content=json_answer({"snap": 2553, VARIABLES[1]: 0})),
        ]
    )
    spend = pilot.Spend(50.0)
    record = run_opus(model, spend=spend)
    assert record["status"] == "complete" and record["model"] == OPUS
    assert record["predictions"] == {"snap": 2553.0, VARIABLES[1]: 0.0}
    first, second = model.requests
    # The API refuses a forced tool on this model: auto, and no answer tool.
    assert [r["tool_choice"] for r in model.requests] == ["auto", "auto"]
    assert [t["function"]["name"] for t in first["tools"]] == [pilot.TOOL_NAME]
    assert first["model"] == "claude-opus-5-5"
    prompt = first["messages"][0]["content"]
    assert prompt[0]["text"].endswith(pilot.JSON_TOOL_NOTICE)
    # One prompt-cache breakpoint per request, on its last message; the stored
    # conversation stays unmarked.
    assert prompt[0]["cache_control"] == {"type": "ephemeral"}
    assert isinstance(second["messages"][0]["content"], str)
    assert second["messages"][-1]["role"] == "tool"
    assert second["messages"][-1]["cache_control"] == {"type": "ephemeral"}
    assert not any("cache_control" in m for m in record["messages"])
    # $4 / $20 per 1M at 1,000 input and 200 output tokens a turn.
    assert record["totals"]["cost_usd"] == pytest.approx(2 * (4000 + 4000) / 1e6)


def test_a_json_contract_cap_is_a_message_and_later_calls_do_not_run():
    ran = []

    def counting_tool(args):
        ran.append(args)
        return fake_tool(args)

    cap = 2
    model = FakeModel(
        [response([calculate(f"c{i}")]) for i in range(cap + 1)]
        + [response([], content=json_answer({"snap": 1, VARIABLES[1]: 2}))]
    )
    record = run_opus(model, tool=counting_tool, turn_cap=cap)
    assert record["status"] == "complete"
    assert len(ran) == cap and record["tool_turns"] == cap and record["cap_hit"]
    cap_request = model.requests[cap]
    assert (
        "used all 2 calculation turns"
        in cap_request["messages"][-1]["content"][0]["text"]
    )
    refused = model.requests[cap + 1]["messages"][-1]
    assert refused["role"] == "tool" and "not_run" in refused["content"]
    assert record["totals"]["tool_error_kinds"] == ["not_run"]


def test_a_json_contract_repair_asks_for_the_missing_output_in_json():
    model = FakeModel(
        [
            response([], content=json_answer({"snap": 1}, fence=True)),
            response([], content=json_answer({VARIABLES[1]: 2})),
        ]
    )
    record = run_opus(model)
    assert record["status"] == "complete" and record["repair_rounds"] == 1
    assert record["predictions"] == {"snap": 1.0, VARIABLES[1]: 2.0}
    repair = model.requests[1]["messages"][-1]["content"][0]["text"]
    assert VARIABLES[1] in repair and "Reply with a JSON object" in repair
    assert "submit_outputs" not in repair


def test_a_json_contract_reply_with_no_answer_is_nudged_not_repaired():
    model = FakeModel(
        [
            response([], content="Let me work through this."),
            response([], content=json_answer({"snap": 1, VARIABLES[1]: 2})),
        ]
    )
    record = run_opus(model)
    assert record["status"] == "complete" and record["repair_rounds"] == 0
    nudge = model.requests[1]["messages"][-1]["content"][0]["text"]
    assert "JSON object" in nudge and "calculate_household" in nudge


def test_records_name_one_model_and_old_records_are_argons():
    assert pilot.records_model({"a": {}, "b": {"model": pilot.MODEL_NAME}}) == (
        pilot.MODEL_NAME
    )
    assert pilot.records_model({"a": {"model": SOL}}) == SOL
    with pytest.raises(SystemExit):
        pilot.records_model({"a": {"model": SOL}, "b": {"model": OPUS}})


def test_arm_labels_follow_the_model():
    records = {"s": _record("s", ["snap"], {"snap": 1.0})}
    assert set(pilot.arm2_predictions(records, "gpt-6-sol+pe-tool").model) == {
        "gpt-6-sol+pe-tool"
    }
    frozen = pilot.arm1_predictions(label=SOL)
    assert set(frozen.model) == {SOL} and frozen.scenario_id.nunique() == 100
    with pytest.raises(SystemExit):
        pilot.arm1_predictions(label="no-such-model")


def test_every_pilot_model_has_a_provider_key():
    for name in (pilot.MODEL_NAME, SOL, OPUS):
        assert pilot.provider_key(pilot.model_profile(name).model_id).endswith(
            "_API_KEY"
        )


STEPS = st.lists(
    st.one_of(
        st.tuples(st.sampled_from(["calculate", "calculate_text"]), st.integers(1, 6)),
        st.tuples(
            st.sampled_from(["full", "partial", "prose", "empty", "truncated"]),
            st.just(0),
        ),
    ),
    max_size=16,
)


class ScriptedModel:
    """Plays a script of turns in the model's own shape, then answers in full.

    ``calculate_text`` sends text beside its calls; ``truncated`` is a reply
    cut off at the output budget, which the harness retries at the ceiling.
    """

    def __init__(self, profile, steps):
        self.profile = profile
        self.steps = list(steps)
        self.requests = []
        self.responses = []

    def __call__(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs, default=str)))
        kind, count = self.steps.pop(0) if self.steps else ("full", 0)
        n = len(self.requests)
        values = {"snap": 1, VARIABLES[1]: 2}
        if kind == "partial":
            values = {"snap": 1}
        responses_api = self.profile.api == "responses"
        if kind in {"calculate", "calculate_text", "truncated"}:
            make = sol_calculate if responses_api else calculate
            calls = [make(f"t{n}c{i}") for i in range(max(count, 1))]
            content = "Checking with the tool." if kind == "calculate_text" else None
        elif kind in {"full", "partial"} and self.profile.contract == "tool":
            make = sol_submit if responses_api else submit
            calls, content = [make(values, f"t{n}s")], None
        elif kind in {"full", "partial"}:
            calls, content = [], json_answer(values)
        else:
            calls, content = [], ("Thinking." if kind == "prose" else None)
        if responses_api:
            items = list(calls)
            if content:
                items.append(
                    SimpleNamespace(
                        type="message",
                        content=[SimpleNamespace(type="output_text", text=content)],
                    )
                )
            result = responses_response(items, f"resp_{n}")
            if kind == "truncated":
                result.status = "incomplete"
                result.incomplete_details = SimpleNamespace(reason="max_output_tokens")
        else:
            result = response(calls, content=content)
            if kind == "truncated":
                result.choices[0].finish_reason = "length"
        result.truncated = kind == "truncated"
        self.responses.append(result)
        return result


def _response_call_ids(profile, result) -> list[str]:
    if profile.api == "responses":
        return [i.call_id for i in result.output if i.type == "function_call"]
    return [c.id for c in result.choices[0].message.tool_calls or []]


def _new_items(profile, request) -> list[tuple[str, str | None]]:
    """What a request adds after the model's last turn, in order:
    ("result", call id) for a function result, ("user", None) for user text."""
    if profile.api == "responses":
        items = request["input"]
        return [
            ("result", i["call_id"])
            if i.get("type") == "function_call_output"
            else ("user", None)
            for i in items
        ]
    messages = request["messages"]
    last_assistant = max(
        i for i, m in enumerate(messages) if m.get("role") == "assistant"
    )
    return [
        ("result", m["tool_call_id"]) if m.get("role") == "tool" else ("user", None)
        for m in messages[last_assistant + 1 :]
    ]


@settings(max_examples=300, deadline=None, derandomize=True)
@given(st.sampled_from([pilot.MODEL_NAME, SOL, OPUS]), STEPS, st.integers(1, 4))
def test_any_conversation_keeps_the_protocol_the_cap_and_the_spend(name, steps, cap):
    profile = pilot.model_profile(name)
    model = ScriptedModel(profile, steps)
    ran = []

    def counting_tool(args):
        ran.append(args)
        return fake_tool(args)

    spend = pilot.Spend(50.0)
    record = pilot.run_household(
        make_scenario(),
        VARIABLES,
        counting_tool,
        model,
        spend,
        turn_cap=cap,
        profile=profile,
    )
    assert record["status"] in {"complete", "incomplete", "turn_limit"}
    assert set(record["predictions"]) == set(VARIABLES)
    # At most MAX_TOTAL_TURNS turns reach the conversation; a turn cut off
    # below the ceiling costs one more request (intended), never more.
    totals = record["totals"]
    assert totals["model_turns"] <= pilot.MAX_TOTAL_TURNS
    assert len(model.requests) == totals["model_turns"] + totals["truncation_retries"]
    assert totals["truncation_retries"] <= totals["model_turns"]
    # The cap: at most `cap` turns run calculations, each at most 4 of them.
    assert record["tool_turns"] <= cap
    assert len(ran) <= cap * pilot.MAX_CALCULATIONS_PER_TURN
    # Spend: the shared counter saw exactly the household's turns.
    assert spend.spent_usd == pytest.approx(record["totals"]["cost_usd"])
    # The protocol both APIs enforce: each function call of a response that
    # reached the conversation gets exactly one result in the next request,
    # before any user text, and a Responses request chains to that response.
    # A response cut off below the budget ceiling never reaches it: the same
    # request goes again at the ceiling.
    from policybench.eval_no_tools import _completion_budget_ceiling

    ceiling = _completion_budget_ceiling(profile.model_id)
    budget_key = (
        "max_output_tokens" if profile.api == "responses" else "max_completion_tokens"
    )
    for i, (result, request) in enumerate(zip(model.responses, model.requests[1:])):
        sent = model.requests[i]
        if result.truncated and sent[budget_key] < ceiling:
            assert request[budget_key] == ceiling
            assert {k: v for k, v in request.items() if k != budget_key} == {
                k: v for k, v in sent.items() if k != budget_key
            }
            continue
        items = _new_items(profile, request)
        results = [call_id for kind, call_id in items if kind == "result"]
        assert sorted(results) == sorted(_response_call_ids(profile, result))
        kinds = [kind for kind, _ in items]
        assert kinds == sorted(kinds), "user text came before a function result"
        if profile.api == "responses":
            assert request["previous_response_id"] == result.id
    for request in model.requests:
        names = [t.get("name") or t["function"]["name"] for t in request["tools"]]
        if profile.contract == "json":
            assert names == [pilot.TOOL_NAME] and request["tool_choice"] == "auto"
        else:
            assert names[0] == pilot.TOOL_NAME and names[1] == "submit_outputs"
    if record["status"] == "complete":
        assert all(v is not None for v in record["predictions"].values())


# ---------------------------------------------------------------------------
# Settling unread outputs, and leave-one-out attribution.
# ---------------------------------------------------------------------------

STATE_OUTPUT = "state_income_tax_before_refundable_credits"


def unread(calls, variables=(STATE_OUTPUT,)):
    record = household(calls)
    record["variables"] = list(variables)
    return record


def test_a_state_variable_equal_to_the_boards_output_is_the_situations_miss():
    """Sol read ca_income_tax_before_refundable_credits; on its situation the
    board's own output is the same number, so the inputs decide the miss."""
    call = call_record(
        {
            "ca_income_tax_before_refundable_credits": {"tu": 40483.32},
            "snap": {"spm": 0.0},
        },
        entity="tax_unit",
    )
    record = unread([call], variables=(STATE_OUTPUT, "snap"))
    verdict = pilot.classify_miss(record, make_scenario(), STATE_OUTPUT, 40483.32, 1)
    assert verdict["category"] == "wrong_variable_or_period"
    asked = []

    def board_value_for(arguments):
        asked.append(arguments)
        return 40483.3

    settled = pilot.resolve_unread_output(
        verdict,
        record,
        make_scenario(),
        STATE_OUTPUT,
        40483.32,
        board_value_for,
        output_entities={"tax_unit"},
    )
    assert settled["category"] == "wrong_input_mapping"
    assert settled["call_arguments"] == call["arguments"] == asked[0]
    assert settled["tool_value"] == 40483.3
    assert "ca_income_tax_before_refundable_credits" in settled["detail"]
    assert settled["answering_call"] == "holds the submitted value"


def test_a_variable_that_differs_from_the_boards_output_stays_a_wrong_variable():
    """Sol read state_income_tax (after refundable credits); its situation gives
    the board's output exactly, so the situation was right and the read was not."""
    call = call_record({"state_income_tax": {"tu": 6363.34}}, entity="tax_unit")
    record = unread([call])
    verdict = pilot.classify_miss(record, make_scenario(), STATE_OUTPUT, 6363.34, 1)
    settled = pilot.resolve_unread_output(
        verdict,
        record,
        make_scenario(),
        STATE_OUTPUT,
        6363.34,
        lambda a: 6828.34,
        output_entities={"tax_unit"},
    )
    assert settled["category"] == "wrong_variable_or_period"
    assert settled["board_output_on_situation"] == 6828.34


def test_an_answer_no_call_returned_falls_back_to_the_main_call():
    """Opus summed two components itself; no single result holds its answer,
    so the main call's situation is checked and the verdict stands."""
    parts = call_record(
        {
            "employee_social_security_tax": {"head": 3720.0},
            "employee_medicare_tax": {"head": 870.0},
            "snap": {"spm": 0.0},
        }
    )
    record = unread([parts], variables=("payroll_tax", "snap"))
    verdict = pilot.classify_miss(record, make_scenario(), "payroll_tax", 4590.0, 1)
    settled = pilot.resolve_unread_output(
        verdict,
        record,
        make_scenario(),
        "payroll_tax",
        4590.0,
        lambda a: 4632.0,
        output_entities={"tax_unit", "spm_unit"},
    )
    assert settled["category"] == "wrong_variable_or_period"
    assert settled["answering_call"] == "main call"
    assert settled["board_output_on_situation"] == 4632.0


def test_other_verdicts_pass_through_unsettled():
    record = unread([call_record({STATE_OUTPUT: {"tu": 5.0}})])
    verdict = pilot.classify_miss(record, make_scenario(), STATE_OUTPUT, 5.0, 9.0)
    assert verdict["category"] == "wrong_input_mapping"

    def never(arguments):
        raise AssertionError("no engine call for a settled verdict")

    assert (
        pilot.resolve_unread_output(
            verdict, record, make_scenario(), STATE_OUTPUT, 5.0, never
        )
        is verdict
    )


def _diff(variable, model, reference, entity="person", unit="head"):
    return {
        "entity": entity,
        "reference_unit": unit,
        "model_unit": unit,
        "variable": variable,
        "model": model,
        "reference": reference,
    }


def test_leave_one_out_names_the_inputs_a_joint_fix_needs(monkeypatch):
    """A toy output that needs two inputs together (as the 401(k) limit needs
    the requested amounts and no post-limit override): no single input fixes
    it, the full set does, and leave-one-out names the two that matter."""

    def toy_value(system, situation, scenario, output):
        head = situation["people"]["head"]
        a = head.get("a", {}).get("2026", 0)
        b = head.get("b", {}).get("2026", 0)
        return 100.0 if (a, b) == (1, 1) else 0.0

    monkeypatch.setattr(pilot, "output_value", toy_value)
    model = {"people": {"head": {"c": {"2026": 5}}, "kid": {}}}
    reference = {"people": {"head": {"a": {"2026": 1}, "b": {"2026": 1}}, "kid": {}}}
    diffs = [
        _diff("a", {}, {"2026": 1}),
        _diff("b", {}, {"2026": 1}),
        _diff("c", {"2026": 5}, {}),
    ]
    result = pilot.attribute_miss(None, model, reference, None, "snap", 100.0, diffs)
    assert result["single_causes"] == [] and result["all_differences_fix_it"]
    assert result["necessary_inputs"] == ["person.a", "person.b"]
    assert result["mapping_kind"] == "left_out"


def test_a_reviewed_re_entry_is_entered_differently_and_a_coincidence_is_not(
    monkeypatch,
):
    """Sol's scenario_018 on situation_diff's own diffs: the prompt's taxable
    interest went into interest_income (a reviewed pair), and 50 weekly hours
    happen to equal it. The pair makes it entered_differently; the hours are
    only a candidate. Without the pair, the same miss is left_out."""

    def toy_value(system, situation, scenario, output):
        head = situation["people"]["head"]
        return 0.0 if "taxable_interest_income" in head else 6.01 + 100

    monkeypatch.setattr(pilot, "output_value", toy_value)
    groups = {group: {} for group in pilot.GROUPS}
    reference = {
        "people": {"head": {"taxable_interest_income": {"2026": 50.0}}, "kid": {}},
        **groups,
    }
    model = {
        "people": {
            "head": {
                "interest_income": {"2026": 50},
                "weekly_hours_worked": {"2026": 50},
            },
            "kid": {},
        },
        **groups,
    }
    diffs = pilot.situation_diff(model, reference, make_scenario())
    assert {d["variable"]: d["model"] for d in diffs}["taxable_interest_income"] == {}
    result = pilot.attribute_miss(None, model, reference, None, "snap", 0.0, diffs)
    assert result["single_causes"] == ["person.taxable_interest_income"]
    assert result["mapping_kind"] == "entered_differently"
    assert result["entered_as"] == ["person.interest_income"]
    assert result["entered_as_candidates"] == ["person.weekly_hours_worked"]

    hours_only = {
        "people": {"head": {"weekly_hours_worked": {"2026": 50}}, "kid": {}},
        **groups,
    }
    coincidence = pilot.attribute_miss(
        None,
        hours_only,
        reference,
        None,
        "snap",
        0.0,
        pilot.situation_diff(hours_only, reference, make_scenario()),
    )
    assert coincidence["mapping_kind"] == "left_out"
    assert coincidence["entered_as"] == []
    assert coincidence["entered_as_candidates"] == ["person.weekly_hours_worked"]


def test_an_amount_entered_under_another_input_is_entered_differently(monkeypatch):
    """Sol's scenario_088: the reference's home_mortgage_interest is unset in
    the model's situation, but the same $10,777 sits under mortgage_interest."""

    def toy_value(system, situation, scenario, output):
        # Outside the board's $1 tolerance either way.
        return 0.0 if "home_mortgage_interest" in situation["people"]["head"] else 416.2

    monkeypatch.setattr(pilot, "output_value", toy_value)
    model = {"people": {"head": {"mortgage_interest": {"2026": 10777}}}}
    reference = {"people": {"head": {"home_mortgage_interest": {"2026": 10777.0}}}}
    diffs = [
        _diff("home_mortgage_interest", {}, {"2026": 10777.0}),
        _diff("mortgage_interest", {"2026": 10777}, {}),
    ]
    result = pilot.attribute_miss(None, model, reference, None, "snap", 0.0, diffs)
    assert result["single_causes"] == ["person.home_mortgage_interest"]
    assert result["mapping_kind"] == "entered_differently"
    assert result["entered_as"] == ["person.mortgage_interest"]
    # The same cause with nothing like its amount elsewhere was left out, and a
    # true flag elsewhere does not count as the amount.
    unrelated = [
        _diff("home_mortgage_interest", {}, {"2026": 10777.0}),
        _diff("is_disabled", {"2026": True}, {}),
        _diff("rent", {"2026": 900}, {}),
    ]
    assert not pilot._entered_elsewhere(unrelated[0], unrelated)
    assert pilot._entered_elsewhere(diffs[0], diffs)
    other_person = [
        diffs[0],
        {**diffs[1], "model_unit": "kid", "reference_unit": "kid"},
    ]
    assert not pilot._entered_elsewhere(other_person[0], other_person)


def test_a_coincidental_probe_on_another_entity_is_not_evidence():
    """r2's case: the answer copies after-credit tax of $200 from the model's
    situation, whose board output is $300; a later probe returns an
    employment_income of $200 on a person. The probe does not count, so the
    verdict stays a wrong variable on the real call."""
    real = call_record(
        {"state_income_tax": {"tu": 200.0}, "snap": {"spm": 0.0}}, entity="tax_unit"
    )
    probe = call_record({"employment_income": {"head": 200.0}}, entity="person", age=41)
    record = unread([real, probe], variables=(STATE_OUTPUT, "snap"))
    verdict = pilot.classify_miss(record, make_scenario(), STATE_OUTPUT, 200.0, 300)
    board = {real["arguments"]: 300.0, probe["arguments"]: 200.0}
    settled = pilot.resolve_unread_output(
        verdict,
        record,
        make_scenario(),
        STATE_OUTPUT,
        200.0,
        board.get,
        output_entities={"tax_unit"},
    )
    assert settled["category"] == "wrong_variable_or_period"
    assert settled["call_arguments"] == real["arguments"]
    assert settled["board_output_on_situation"] == 300.0


def test_holding_calls_that_disagree_leave_the_verdict_marked_ambiguous():
    """Two tax-unit results both hold the answer, but only one situation's
    board output equals it: no reclassification on evidence that splits."""
    first = call_record(
        {"state_income_tax": {"tu": 200.0}, "snap": {"spm": 0.0}}, entity="tax_unit"
    )
    second = call_record({"xx_credit": {"tu": 200.0}}, entity="tax_unit", age=41)
    record = unread([first, second], variables=(STATE_OUTPUT, "snap"))
    verdict = pilot.classify_miss(record, make_scenario(), STATE_OUTPUT, 200.0, 300)
    board = {first["arguments"]: 300.0, second["arguments"]: 200.0}
    settled = pilot.resolve_unread_output(
        verdict,
        record,
        make_scenario(),
        STATE_OUTPUT,
        200.0,
        board.get,
        output_entities={"tax_unit"},
    )
    assert settled["category"] == "wrong_variable_or_period"
    assert settled["detail"].startswith("ambiguous")
    assert settled["holding_calls"] == 2
    # The evidence reported is the main situation's, not the probe's (r3).
    assert settled["call_arguments"] == first["arguments"]
    assert settled["board_output_on_situation"] == 300.0
    assert settled["holding_board_values"] == [300.0, 200.0]


def test_agreeing_holding_calls_attribute_the_fullest_one():
    """Every holding call agrees; the situation attributed is the one that
    computed the most of the household's outputs, not a later narrow probe."""
    full = call_record(
        {"ca_income_tax": {"tu": 500.0}, "snap": {"spm": 0.0}},
        entity="tax_unit",
    )
    probe = call_record({"ca_income_tax": {"tu": 500.0}}, entity="tax_unit", age=41)
    record = unread([full, probe], variables=(STATE_OUTPUT, "snap"))
    verdict = pilot.classify_miss(record, make_scenario(), STATE_OUTPUT, 500.0, 900)
    settled = pilot.resolve_unread_output(
        verdict,
        record,
        make_scenario(),
        STATE_OUTPUT,
        500.0,
        lambda a: 500.0,
        output_entities={"tax_unit"},
    )
    assert settled["category"] == "wrong_input_mapping"
    assert settled["call_arguments"] == full["arguments"]
    assert settled["holding_calls"] == 2


def test_a_binary_output_is_never_reclassified():
    # The call computes SNAP, so it is the main one; r5's construction.
    call = call_record(
        {"is_wic_eligible": {"head": True, "kid": False}, "snap": {"spm": 0.0}},
        entity="person",
    )
    record = unread([call], variables=("head_medicaid_eligible", "snap"))
    verdict = pilot.classify_miss(
        record, make_scenario(), "head_medicaid_eligible", 0.0, 1.0
    )
    assert verdict["category"] == "wrong_variable_or_period"
    settled = pilot.resolve_unread_output(
        verdict,
        record,
        make_scenario(),
        "head_medicaid_eligible",
        0.0,
        lambda a: 0.0,
        output_entities={"person"},
        binary=True,
    )
    assert settled["category"] == "wrong_variable_or_period"
    assert settled["answering_call"] == "main call"
    # Binary outputs skip the holding check, so no note may claim that no
    # call holds the answer (r5): a 0 sits in many results.
    assert "no call's results hold it" not in settled.get("detail", "")


def test_a_lone_probe_cannot_outvote_the_main_situation_for_a_summed_answer():
    """r3's case: Opus summed $3,720 and $870 into $4,590 on its main
    situation, whose board payroll is $4,632. A later tax-unit probe, which
    computes fewer outputs, returns $4,590 on a situation whose board payroll
    is also $4,590. The probe is the only holding call, but the main
    situation disagrees, so the verdict stands on the main call."""
    parts = call_record(
        {
            "employee_social_security_tax": {"tu": 3720.0},
            "employee_medicare_tax": {"tu": 870.0},
            "snap": {"spm": 0.0},
            "ssi": {"head": 0.0},
        },
        entity="tax_unit",
    )
    probe = call_record({"xx_tax": {"tu": 4590.0}}, entity="tax_unit", age=41)
    record = unread([parts, probe], variables=("payroll_tax", "snap", "ssi"))
    verdict = pilot.classify_miss(record, make_scenario(), "payroll_tax", 4590.0, 4632)
    assert verdict["category"] == "wrong_variable_or_period"
    board = {parts["arguments"]: 4632.0, probe["arguments"]: 4590.0}
    settled = pilot.resolve_unread_output(
        verdict,
        record,
        make_scenario(),
        "payroll_tax",
        4590.0,
        board.get,
        output_entities={"tax_unit", "spm_unit"},
    )
    assert settled["category"] == "wrong_variable_or_period"
    assert settled["call_arguments"] == parts["arguments"]
    assert settled["board_output_on_situation"] == 4632.0
    assert settled["holding_board_values"] == [4590.0]
    assert settled["detail"].startswith("ambiguous")


def test_no_main_situation_when_every_call_ties_at_zero():
    """r4's case: with payroll the only output and no call computing it, every
    call ties at zero and the tie rule would make the last probe the main call,
    vouching for itself. No situation is the main one, so nothing flips."""
    parts = call_record(
        {
            "employee_social_security_tax": {"tu": 3720.0},
            "employee_medicare_tax": {"tu": 870.0},
        },
        entity="tax_unit",
    )
    probe = call_record({"xx_tax": {"tu": 4590.0}}, entity="tax_unit", age=41)
    record = unread([parts, probe], variables=("payroll_tax",))
    verdict = pilot.classify_miss(record, make_scenario(), "payroll_tax", 4590.0, 4632)
    assert verdict["category"] == "wrong_variable_or_period"
    board = {parts["arguments"]: 4632.0, probe["arguments"]: 4590.0}
    settled = pilot.resolve_unread_output(
        verdict,
        record,
        make_scenario(),
        "payroll_tax",
        4590.0,
        board.get,
        output_entities={"tax_unit", "spm_unit"},
    )
    assert settled["category"] == "wrong_variable_or_period"
    assert settled["detail"].startswith("no call computed any")
    assert pilot.main_call_and_count(record, make_scenario(), ["payroll_tax"])[1] == 0


def test_a_main_situation_equal_to_an_answer_no_call_holds_is_noted():
    """An answer the model built itself, on a main situation whose board output
    equals it: strong evidence of a mapping miss, noted but not reclassified."""
    parts = call_record(
        {
            "employee_social_security_tax": {"tu": 3720.0},
            "employee_medicare_tax": {"tu": 870.0},
            "snap": {"spm": 0.0},
        },
        entity="tax_unit",
    )
    record = unread([parts], variables=("payroll_tax", "snap"))
    verdict = pilot.classify_miss(record, make_scenario(), "payroll_tax", 4590.0, 4632)
    settled = pilot.resolve_unread_output(
        verdict,
        record,
        make_scenario(),
        "payroll_tax",
        4590.0,
        lambda a: 4590.0,
        output_entities={"tax_unit", "spm_unit"},
    )
    assert settled["category"] == "wrong_variable_or_period"
    assert "no call's results hold it" in settled["detail"]


def test_an_uncomputable_main_situation_is_noted_not_called_a_disagreement():
    main = call_record(
        {"ca_income_tax": {"tu": 500.0}, "snap": {"spm": 0.0}}, entity="tax_unit"
    )
    record = unread([main], variables=(STATE_OUTPUT, "snap"))
    verdict = pilot.classify_miss(record, make_scenario(), STATE_OUTPUT, 500.0, 900)
    settled = pilot.resolve_unread_output(
        verdict,
        record,
        make_scenario(),
        STATE_OUTPUT,
        500.0,
        lambda a: None,
        output_entities={"tax_unit"},
    )
    assert settled["category"] == "wrong_variable_or_period"
    assert settled["detail"].startswith("the main situation could not be computed")


# ---------------------------------------------------------------------------
# Web arms: the provider's own web search in place of, or beside, the tool.
# ---------------------------------------------------------------------------

# The notices the published pilot runs recorded (tool_notice_sha256 in every
# household record of results/run, gpt-6-sol/run and claude-opus-5.5/run).
PE_NOTICE_SHA256 = {
    "tool": "27c97c6dfddfefc856aca123f93e22d7aa81ce73ab7250cec3f977d6cf76d78d",
    "json": "82a32a6f59d64c895241e01bd319d049635030c54ef8240704930898c1e1a9a5",
}


def _sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()


def test_the_pe_arm_keeps_the_notices_the_published_runs_used():
    assert _sha(pilot.TOOL_NOTICE) == PE_NOTICE_SHA256["tool"]
    assert _sha(pilot.JSON_TOOL_NOTICE) == PE_NOTICE_SHA256["json"]
    for name, contract in ((pilot.MODEL_NAME, "tool"), (SOL, "tool"), (OPUS, "json")):
        assert _sha(pilot.model_profile(name).notice) == PE_NOTICE_SHA256[contract]


def test_web_notices_name_search_and_keep_the_answer_instruction():
    argon, opus = (
        pilot.model_profile(pilot.MODEL_NAME, "web"),
        pilot.model_profile(OPUS, "web"),
    )
    assert argon.notice == pilot.WEB_NOTICE and opus.notice == pilot.JSON_WEB_NOTICE
    assert "calculate_household" not in pilot.WEB_NOTICE + pilot.JSON_WEB_NOTICE
    assert pilot.WEB_NOTICE.endswith(pilot.TOOL_NOTICE.split("8 turns. ")[1])
    assert pilot.JSON_WEB_NOTICE.endswith(pilot.JSON_TOOL_NOTICE.split("8 turns. ")[1])
    # Web+PE: the PE notice with web search named in its opening sentence.
    for both, pe in (
        (pilot.WEB_TOOL_NOTICE, pilot.TOOL_NOTICE),
        (pilot.JSON_WEB_TOOL_NOTICE, pilot.JSON_TOOL_NOTICE),
    ):
        assert both != pe and "web search" in both
        assert both.split("function. ", 1)[1] == pe.split("function. ", 1)[1]
    labels = {arm: pilot.model_profile(SOL, arm).arm2_label for arm in pilot.ARMS}
    assert labels == {
        "pe": "gpt-6-sol+pe-tool",
        "web": "gpt-6-sol+web",
        "web+pe": "gpt-6-sol+web+pe-tool",
    }
    with pytest.raises(SystemExit):
        pilot.model_profile(SOL, "search")


def gemini_searches(*invocations):
    return {
        "server_side_tool_invocations": [
            {"tool_type": "GOOGLE_SEARCH_WEB", "id": i, "args": {"queries": q}}
            for i, q in invocations
        ]
    }


def with_fields(resp, fields=None, server_tool_use=None):
    if fields is not None:
        resp.choices[0].message.provider_specific_fields = fields
    if server_tool_use is not None:
        resp.usage.server_tool_use = SimpleNamespace(
            web_search_requests=server_tool_use
        )
    return resp


def test_a_gemini_web_arm_offers_search_and_the_answer_and_bills_each_query():
    profile = pilot.model_profile(pilot.MODEL_NAME, "web")
    model = FakeModel(
        [
            with_fields(
                response([submit({"snap": 2553, VARIABLES[1]: 0})]),
                gemini_searches(("g1", ["co snap 2026", "", "co standard deduction"])),
            )
        ]
    )
    spend = pilot.Spend(50.0)
    record = pilot.run_household(
        make_scenario(), VARIABLES, fake_tool, model, spend, profile=profile
    )
    assert record["status"] == "complete" and record["arm"] == "web"
    (request,) = model.requests
    assert request["tools"][0] == {"googleSearch": {}}
    assert [t["function"]["name"] for t in request["tools"][1:]] == ["submit_outputs"]
    assert request["tool_choice"] == "required"
    assert request["include_server_side_tool_invocations"] is True
    assert request["messages"][0]["content"].endswith(pilot.WEB_NOTICE)
    totals = record["totals"]
    # Two non-empty queries at $14 per 1,000, on top of the tokens' $0.004.
    assert totals["web_searches"] == 2
    assert totals["search_cost_usd"] == pytest.approx(0.028)
    assert totals["token_cost_usd"] == pytest.approx((1000 * 2 + 200 * 10) / 1e6)
    assert totals["cost_usd"] == pytest.approx(0.032)
    assert spend.spent_usd == pytest.approx(totals["cost_usd"])
    assert totals["tool_calls"] == 0
    (search,) = record["turns"][0]["searches"]
    assert search["queries"] == ["co snap 2026", "co standard deduction"]


def test_a_gemini_invocation_is_billed_once_however_often_it_comes_back():
    profile = pilot.model_profile(pilot.MODEL_NAME, "web")
    model = FakeModel(
        [
            with_fields(
                response([submit({"snap": 10})]), gemini_searches(("g1", ["a"]))
            ),
            with_fields(
                response([submit({VARIABLES[1]: 5}, "s2")]),
                gemini_searches(("g1", ["a"]), ("g2", ["b", "c"])),
            ),
        ]
    )
    record = pilot.run_household(
        make_scenario(), VARIABLES, fake_tool, model, pilot.Spend(50.0), profile=profile
    )
    assert record["status"] == "complete" and record["repair_rounds"] == 1
    assert record["totals"]["web_searches"] == 3
    repeats = [s["repeat"] for t in record["turns"] for s in t["searches"]]
    assert repeats == [False, True, False]


def web_search_call(call_id, action):
    return SimpleNamespace(
        type="web_search_call", id=call_id, status="completed", action=action
    )


def test_a_responses_web_and_tool_arm_sends_native_search_beside_the_functions():
    profile = pilot.model_profile(SOL, "web+pe")
    model = FakeResponses(
        [
            responses_response(
                [
                    web_search_call(
                        "ws_1", SimpleNamespace(type="search", query="co snap")
                    ),
                    sol_calculate("call_a"),
                ],
                "resp_1",
            ),
            responses_response(
                [
                    web_search_call(
                        "ws_2", SimpleNamespace(type="open_page", url="https://x.gov")
                    ),
                    sol_submit({"snap": 2553, VARIABLES[1]: 0}),
                ],
                "resp_2",
            ),
        ]
    )
    spend = pilot.Spend(50.0)
    record = pilot.run_household(
        make_scenario(), VARIABLES, fake_tool, model, spend, profile=profile
    )
    assert record["status"] == "complete" and record["arm"] == "web+pe"
    first, second = model.requests
    assert first["tools"][0] == {
        "type": "web_search",
        "filters": {"blocked_domains": list(pilot.BLOCKED_DOMAINS)},
    }
    assert [t.get("name") for t in first["tools"][1:]] == [
        pilot.TOOL_NAME,
        "submit_outputs",
    ]
    assert first["input"].endswith(pilot.WEB_TOOL_NOTICE)
    # Only the calculation gets an output; the provider ran the search.
    (output,) = second["input"]
    assert output["type"] == "function_call_output" and output["call_id"] == "call_a"
    totals = record["totals"]
    assert totals["web_searches"] == 2 and totals["tool_calls"] == 1
    assert totals["search_cost_usd"] == pytest.approx(0.02)
    assert spend.spent_usd == pytest.approx(totals["cost_usd"])
    kinds = [s["kind"] for t in record["turns"] for s in t["searches"]]
    assert kinds == ["search", "open_page"]


def test_an_anthropic_web_arm_answers_in_json_and_skips_server_calls():
    profile = pilot.model_profile(OPUS, "web")
    model = FakeModel(
        [
            with_fields(
                response(
                    [tool_call("web_search", {"query": "co snap"}, "srvtoolu_1")],
                    content=json_answer({"snap": 2553, VARIABLES[1]: 0}),
                ),
                {
                    "web_search_results": [
                        {
                            "type": "web_search_tool_result",
                            "tool_use_id": "srvtoolu_1",
                            "content": [
                                {"url": "https://cdhs.colorado.gov", "title": "SNAP"}
                            ],
                        }
                    ]
                },
                server_tool_use=3,
            )
        ]
    )
    spend = pilot.Spend(50.0)
    record = pilot.run_household(
        make_scenario(), VARIABLES, fake_tool, model, spend, profile=profile
    )
    assert record["status"] == "complete"
    assert record["predictions"] == {"snap": 2553.0, VARIABLES[1]: 0.0}
    (request,) = model.requests
    assert request["tools"] == [
        {
            "type": pilot.ANTHROPIC_WEB_SEARCH_TOOL,
            "name": "web_search",
            "blocked_domains": list(pilot.BLOCKED_DOMAINS),
        }
    ]
    assert request["tool_choice"] == "auto"
    assert request["messages"][0]["content"][0]["text"].endswith(pilot.JSON_WEB_NOTICE)
    turn = record["turns"][0]
    assert turn["calls"] == [] and turn["server_calls"][0]["id"] == "srvtoolu_1"
    assert {(s["kind"], s.get("url")) for s in turn["searches"]} == {
        ("web_search", None),
        ("result", "https://cdhs.colorado.gov"),
    }
    # The usage's count bills, $10 per 1,000: three searches.
    assert record["totals"]["web_searches"] == 3
    assert record["totals"]["search_cost_usd"] == pytest.approx(0.03)
    assert spend.spent_usd == pytest.approx(record["totals"]["cost_usd"])


def server_only(call_id="srvtoolu_p", searches=1):
    return with_fields(
        response(
            [tool_call("code_execution", {"code": "await web_search()"}, call_id)]
        ),
        server_tool_use=searches,
    )


def test_a_paused_search_turn_is_sent_back_unchanged():
    model = FakeModel(
        [server_only(), response([], content=json_answer({"snap": 1, VARIABLES[1]: 2}))]
    )
    record = pilot.run_household(
        make_scenario(),
        VARIABLES,
        fake_tool,
        model,
        pilot.Spend(50.0),
        profile=pilot.model_profile(OPUS, "web"),
    )
    assert record["status"] == "complete" and record["pause_continuations"] == 1
    assert record["turns"][0]["continued_after_pause"] is True
    resent = model.requests[1]["messages"]
    assert resent[-1]["role"] == "assistant"
    assert not any(m["role"] == "tool" for m in resent)
    assert record["totals"]["web_searches"] == 1


def test_a_pause_still_unfinished_past_the_limit_ends_the_household():
    """No text may follow an unfinished server call, so a pause that never
    finishes ends the household rather than earning a nudge (a 400)."""
    pauses = pilot.MAX_PAUSE_CONTINUATIONS
    model = FakeModel([server_only(f"srvtoolu_{i}") for i in range(pauses + 1)])
    record = pilot.run_household(
        make_scenario(),
        VARIABLES,
        fake_tool,
        model,
        pilot.Spend(50.0),
        profile=pilot.model_profile(OPUS, "web"),
    )
    assert record["status"] == "incomplete" and record["pause_continuations"] == pauses
    assert "still unfinished" in record["error"]
    assert len(model.requests) == pauses + 1
    for request in model.requests[1:]:
        assert request["messages"][-1]["role"] == "assistant"


def test_a_finished_search_with_no_answer_is_nudged_not_continued():
    searched = with_fields(
        response([tool_call("web_search", {"query": "q"}, "srvtoolu_1")]),
        {
            "web_search_results": [
                {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1"}
            ]
        },
        server_tool_use=1,
    )
    model = FakeModel(
        [searched, response([], content=json_answer({"snap": 1, VARIABLES[1]: 2}))]
    )
    record = pilot.run_household(
        make_scenario(),
        VARIABLES,
        fake_tool,
        model,
        pilot.Spend(50.0),
        profile=pilot.model_profile(OPUS, "web"),
    )
    assert record["status"] == "complete" and record["pause_continuations"] == 0
    assert record["turns"][0]["unfinished_server_calls"] == []
    assert record["turns"][0]["search_only_turn"] is True
    nudge = model.requests[1]["messages"][-1]["content"][0]["text"]
    assert "JSON object" in nudge and "calculate_household" not in nudge


def test_an_anthropic_web_and_tool_turn_runs_only_the_client_call():
    model = FakeModel(
        [
            response(
                [tool_call("web_search", {"query": "q"}, "srvtoolu_1"), calculate()]
            ),
            response([], content=json_answer({"snap": 2553, VARIABLES[1]: 0})),
        ]
    )
    ran = []

    def counting_tool(args):
        ran.append(args)
        return fake_tool(args)

    record = pilot.run_household(
        make_scenario(),
        VARIABLES,
        counting_tool,
        model,
        pilot.Spend(50.0),
        profile=pilot.model_profile(OPUS, "web+pe"),
    )
    assert record["status"] == "complete" and len(ran) == 1
    tool_messages = [m for m in model.requests[1]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_messages] == ["c1"]
    assert [
        t.get("name") or t["function"]["name"] for t in model.requests[0]["tools"]
    ] == [
        "web_search",
        pilot.TOOL_NAME,
    ]


def test_a_web_arm_reply_with_no_function_is_nudged_to_answer():
    model = FakeModel(
        [
            response([], content="Let me look this up."),
            response([submit({"snap": 1, VARIABLES[1]: 2})]),
        ]
    )
    record = pilot.run_household(
        make_scenario(),
        VARIABLES,
        fake_tool,
        model,
        pilot.Spend(50.0),
        profile=pilot.model_profile(pilot.MODEL_NAME, "web"),
    )
    assert record["status"] == "complete"
    nudge = model.requests[1]["messages"][-1]["content"]
    assert nudge == "Call submit_outputs with your final answers."


@settings(max_examples=200, deadline=None)
@given(
    st.lists(
        st.lists(
            st.tuples(
                st.sampled_from(["g1", "g2", "g3", "g4"]),
                st.lists(st.sampled_from(["", "q1", "q2"]), max_size=4),
            ),
            max_size=3,
        ),
        max_size=6,
    )
)
def test_gemini_bills_each_invocation_once_with_its_nonempty_queries(batches):
    """Invariant: over any sequence of responses, the billed count is the
    non-empty queries of each invocation id's first appearance."""
    profile = pilot.model_profile(pilot.MODEL_NAME, "web")
    seen: set[str] = set()
    billed = 0
    first_queries: dict[str, list[str]] = {}
    for batch in batches:
        resp = with_fields(response([]), gemini_searches(*batch))
        turn = pilot.ChatConversation("p").read(resp, None)
        log, count = pilot.turn_searches(resp, turn, profile, seen)
        billed += count
        assert len(log) == len(batch)
        for invocation_id, queries in batch:
            first_queries.setdefault(invocation_id, [q for q in queries if q])
    assert billed == sum(len(q) for q in first_queries.values())
    assert seen == set(first_queries)


@settings(max_examples=100, deadline=None)
@given(
    st.sampled_from(
        [(pilot.MODEL_NAME, "gemini"), (SOL, "openai"), (OPUS, "anthropic")]
    ),
    st.sampled_from(["web", "web+pe"]),
    st.integers(0, 40),
)
def test_a_households_cost_is_its_tokens_plus_its_searches_at_list(model_arm, arm, n):
    """Invariant: cost_usd = token_cost_usd + searches x list price / 1,000, and
    the shared spend counter saw exactly cost_usd."""
    name, provider = model_arm
    profile = pilot.model_profile(name, arm)
    values = {"snap": 1, VARIABLES[1]: 2}
    if provider == "openai":
        items = [
            web_search_call(f"ws_{i}", SimpleNamespace(type="search", query="q"))
            for i in range(n)
        ]
        model = FakeResponses([responses_response([*items, sol_submit(values)], "r")])
    elif provider == "gemini":
        model = FakeModel(
            [
                with_fields(
                    response([submit(values)]),
                    gemini_searches(*[(f"g{i}", ["q"]) for i in range(n)]),
                )
            ]
        )
    else:
        model = FakeModel(
            [with_fields(response([], content=json_answer(values)), server_tool_use=n)]
        )
    spend = pilot.Spend(50.0)
    record = pilot.run_household(
        make_scenario(), VARIABLES, fake_tool, model, spend, profile=profile
    )
    totals = record["totals"]
    assert record["status"] == "complete" and totals["web_searches"] == n
    assert totals["search_cost_usd"] == pytest.approx(
        n * pilot.SEARCH_USD_PER_1K[provider] / 1000
    )
    assert totals["cost_usd"] == pytest.approx(
        totals["token_cost_usd"] + totals["search_cost_usd"]
    )
    assert spend.spent_usd == pytest.approx(totals["cost_usd"])


def test_the_pe_arm_bills_no_searches_and_its_cost_is_its_tokens():
    model = FakeModel([response([submit({"snap": 1, VARIABLES[1]: 2})])])
    record = pilot.run_household(
        make_scenario(), VARIABLES, fake_tool, model, pilot.Spend(50.0)
    )
    totals = record["totals"]
    assert "searches" not in record["turns"][0]
    assert totals["web_searches"] == 0 and totals["search_cost_usd"] == 0
    assert totals["cost_usd"] == totals["token_cost_usd"]


def test_the_search_audit_flags_the_benchmark_and_blocked_domains():
    record = _record("s", ["snap"], {"snap": 1.0})
    record["turns"][0]["index"] = 0
    record["turns"][0]["searches"] = [
        {"kind": "search", "queries": ["policybench scenario_t snap"]},
        {"kind": "result", "url": "https://github.com/PolicyEngine/x", "title": "x"},
        {"kind": "result", "url": "https://www.irs.gov/a", "title": "IRS"},
    ]
    log = pilot.search_log({"s": record})
    assert list(log["kind"]) == ["search", "result", "result"]
    audit = pilot.search_audit(log)
    assert audit["queries"] == 1 and audit["result_urls"] == 2
    assert [m["query"] for m in audit["policybench_mentions"]] == [
        "policybench scenario_t snap"
    ]
    assert [b["url"] for b in audit["blocked_domain_urls"]] == [
        "https://github.com/PolicyEngine/x"
    ]


def test_records_name_one_arm_and_old_records_are_the_pe_tools():
    assert pilot.records_arm({"a": {}, "b": {"arm": "pe"}}) == "pe"
    assert pilot.records_arm({"a": {"arm": "web"}}) == "web"
    with pytest.raises(SystemExit):
        pilot.records_arm({"a": {"arm": "web"}, "b": {}})


def test_every_pilot_model_has_a_web_search_tool():
    for name in (pilot.MODEL_NAME, SOL, OPUS):
        assert pilot.web_search_tool(pilot.model_profile(name, "web"))


def _keep_litellm_gemini_config(monkeypatch):
    from litellm.llms.vertex_ai.gemini.vertex_and_google_ai_studio_gemini import (
        VertexGeminiConfig,
    )

    for name in (
        "_resolve_search_tool_conflict",
        "_drop_search_tools_mixed_with_functions",
    ):
        monkeypatch.setattr(VertexGeminiConfig, name, VertexGeminiConfig.__dict__[name])


def test_the_gemini_patch_keeps_search_beside_functions(monkeypatch):
    from litellm.utils import get_optional_params

    _keep_litellm_gemini_config(monkeypatch)
    function = calculate_tool = pilot.calculate_tool_schema()

    def tool_keys():
        params = get_optional_params(
            model="gemini-4-argon",
            custom_llm_provider="gemini",
            tools=[{"googleSearch": {}}, function],
            tool_choice="required",
            include_server_side_tool_invocations=True,
        )
        return sorted(k for t in params.get("tools", []) for k in t)

    if importlib.metadata.version("litellm") != pilot.GEMINI_SEARCH_PATCH_LITELLM:
        pytest.skip("the patch refuses other litellm versions")
    assert tool_keys() == ["function_declarations"]  # litellm drops search
    pilot.allow_gemini_search_with_functions()
    assert tool_keys() == ["function_declarations", "googleSearch"]
    assert calculate_tool["function"]["name"] == pilot.TOOL_NAME


def test_the_gemini_patch_refuses_another_litellm(monkeypatch):
    _keep_litellm_gemini_config(monkeypatch)
    monkeypatch.setattr(pilot.importlib.metadata, "version", lambda name: "9.9.9")
    with pytest.raises(SystemExit):
        pilot.allow_gemini_search_with_functions()


def as_data(value):
    if isinstance(value, SimpleNamespace):
        return {k: as_data(v) for k, v in vars(value).items()}
    if isinstance(value, dict):
        return {k: as_data(v) for k, v in value.items()}
    if isinstance(value, list):
        return [as_data(v) for v in value]
    return value


def test_a_deferred_server_result_moves_to_the_message_that_called_it():
    """Live 2026-10-20: left where it arrives, litellm drops the deferred
    result from later requests and the API refuses the third with a 400."""
    from litellm.litellm_core_utils.prompt_templates.factory import (
        anthropic_messages_pt,
    )

    deferred = response(
        [tool_call("code_execution", {"code": "x"}, "srvtoolu_d"), calculate("c1")]
    )
    result = {
        "type": "code_execution_tool_result",
        "tool_use_id": "srvtoolu_d",
        "content": {"type": "code_execution_result", "stdout": "ok"},
    }
    resumed = with_fields(response([calculate("c2")]), {"tool_results": [result]})
    model = FakeModel(
        [
            deferred,
            resumed,
            response([], content=json_answer({"snap": 1, VARIABLES[1]: 2})),
        ]
    )
    record = pilot.run_household(
        make_scenario(),
        VARIABLES,
        fake_tool,
        model,
        pilot.Spend(50.0),
        profile=pilot.model_profile(OPUS, "web+pe"),
    )
    assert record["status"] == "complete"
    assert record["turns"][0]["unfinished_server_calls"] == ["srvtoolu_d"]
    # The second request carries only the client result after the deferral.
    assert model.requests[1]["messages"][-1]["role"] == "tool"
    # litellm's own conversion of the conversation, as plain data (litellm
    # messages are dicts; the fakes here are namespaces).
    converted = anthropic_messages_pt(
        as_data(record["messages"]), model="claude-opus-5-5", llm_provider="anthropic"
    )
    first_reply = [m for m in converted if m["role"] == "assistant"][0]["content"]
    kinds = [(b["type"], b.get("id") or b.get("tool_use_id")) for b in first_reply]
    assert kinds[:2] == [
        ("server_tool_use", "srvtoolu_d"),
        ("code_execution_tool_result", "srvtoolu_d"),
    ]
    assert ("tool_use", "c1") in kinds


def test_no_text_follows_a_deferred_server_call_at_the_cap():
    cap = 1
    model = FakeModel(
        [
            response(
                [tool_call("web_search", {"query": "q"}, "srvtoolu_1"), calculate()]
            ),
            response([], content=json_answer({"snap": 1, VARIABLES[1]: 2})),
        ]
    )
    record = pilot.run_household(
        make_scenario(),
        VARIABLES,
        fake_tool,
        model,
        pilot.Spend(50.0),
        turn_cap=cap,
        profile=pilot.model_profile(OPUS, "web+pe"),
    )
    assert record["status"] == "complete"
    assert record["turns"][0]["cap_notice_withheld"] is True
    assert model.requests[1]["messages"][-1]["role"] == "tool"


def test_a_continuation_goes_back_without_a_cache_mark():
    paused = server_only()
    # A paused turn can carry text before its search; marking it would turn
    # that text into a block list, which litellm rebuilds in another order.
    paused.choices[0].message.content = "Let me look up the 2026 figures."
    model = FakeModel(
        [paused, response([], content=json_answer({"snap": 1, VARIABLES[1]: 2}))]
    )
    pilot.run_household(
        make_scenario(),
        VARIABLES,
        fake_tool,
        model,
        pilot.Spend(50.0),
        profile=pilot.model_profile(OPUS, "web"),
    )
    last = model.requests[1]["messages"][-1]
    assert last["role"] == "assistant" and "cache_control" not in json.dumps(last)
    assert last["content"] == "Let me look up the 2026 figures."


def test_search_only_turns_count_toward_the_cap_and_then_force_the_answer():
    cap = 2
    searching = [
        responses_response(
            [web_search_call(f"ws_{i}", SimpleNamespace(type="search", query="q"))],
            f"r{i}",
        )
        for i in range(cap)
    ]
    model = FakeResponses(
        searching
        + [responses_response([sol_submit({"snap": 1, VARIABLES[1]: 2})], "z")]
    )
    record = pilot.run_household(
        make_scenario(),
        VARIABLES,
        fake_tool,
        model,
        pilot.Spend(50.0),
        turn_cap=cap,
        profile=pilot.model_profile(SOL, "web"),
    )
    assert record["status"] == "complete" and record["search_only_turns"] == cap
    assert record["cap_hit"] and record["tool_turns"] == 0
    assert model.requests[cap]["tool_choice"] == {
        "type": "function",
        "name": "submit_outputs",
    }


def test_openai_asks_for_and_logs_each_searchs_sources():
    action = SimpleNamespace(
        type="search",
        query="q",
        sources=[SimpleNamespace(type="url", url="https://www.irs.gov/a")],
    )
    model = FakeResponses(
        [
            responses_response(
                [
                    web_search_call("ws_1", action),
                    web_search_call(
                        "ws_2", SimpleNamespace(type="open_page", url="https://x.org")
                    ),
                    sol_submit({"snap": 1, VARIABLES[1]: 2}),
                ],
                "r",
            )
        ]
    )
    record = pilot.run_household(
        make_scenario(),
        VARIABLES,
        fake_tool,
        model,
        pilot.Spend(50.0),
        profile=pilot.model_profile(SOL, "web"),
    )
    assert model.requests[0]["include"] == [pilot.OPENAI_SEARCH_SOURCES]
    log = record["turns"][0]["searches"]
    assert {e["url"] for e in log if e["kind"] == "source"} == {"https://www.irs.gov/a"}
    totals = record["totals"]
    assert totals["web_searches"] == 2 and totals["web_search_actions"] == 1


def test_a_json_reply_beside_an_unknown_call_gets_its_result_then_a_nudge():
    model = FakeModel(
        [
            response(
                [tool_call("lookup", {"q": 1}, "u1")], content="Let me think about it."
            ),
            response([], content=json_answer({"snap": 1, VARIABLES[1]: 2})),
        ]
    )
    record = run_opus(model)
    assert record["status"] == "complete"
    messages = model.requests[1]["messages"]
    assert messages[-2]["role"] == "tool" and messages[-2]["tool_call_id"] == "u1"
    assert "unknown function" in messages[-2]["content"]
    assert messages[-1]["role"] == "user"


def test_score_writes_a_strict_json_audit_and_flags_benchmark_searches(tmp_path):
    import argparse

    board = pilot.load_board()
    reference = board["reference"].set_index(["scenario_id", "variable"])["value"]
    households = tmp_path / "households"
    households.mkdir()
    for sid, query in (
        ("scenario_000", "policybench scenario_000"),
        ("scenario_001", "irs 2026 standard deduction"),
    ):
        variables = board["variables"][sid]
        record = _record(
            sid, variables, {v: float(reference[(sid, v)]) for v in variables}
        )
        record["model"], record["arm"] = SOL, "web"
        record["turns"][0].update(
            index=0,
            searches=[
                {"kind": "search", "queries": [query]},
                {"kind": "open_page", "url": "https://github.com/x"}
                if sid == "scenario_001"
                else {"kind": "source", "url": "https://www.irs.gov"},
            ],
        )
        (households / f"{sid}.json").write_text(json.dumps(record))
    pilot.command_score(argparse.Namespace(out_dir=str(tmp_path), complete_only=False))
    text = (tmp_path / "score.json").read_text()
    score = json.loads(text, parse_constant=lambda c: pytest.fail(f"bare {c}"))
    audit = score["search_audit"]
    assert audit["flagged_households"] == ["scenario_000", "scenario_001"]
    assert audit["weighted_exact_unflagged"]["households"] == 0
    assert audit["results_visible"] is True
    assert (tmp_path / "searches.csv").exists()


@settings(max_examples=60, deadline=None)
@given(
    st.lists(st.integers(0, 6), min_size=1, max_size=3),
    st.booleans(),
)
def test_a_multi_turn_households_cost_is_its_tokens_plus_its_searches(
    per_turn, truncate_first
):
    """Invariant across repair turns and a truncated-and-retried turn: cost is
    tokens plus every billed search, and the spend counter saw exactly that."""
    profile = pilot.model_profile(pilot.MODEL_NAME, "web")
    responses_, n = [], 0
    for index, searches in enumerate(per_turn):
        # Every turn but the last answers nothing, so each earns a repair
        # and the household completes on the last.
        values = {} if index < len(per_turn) - 1 else {"snap": 1, VARIABLES[1]: 2}
        invocations = [(f"g{index}_{k}", ["q"]) for k in range(searches)]
        if index == 0 and truncate_first:
            cut = with_fields(response([]), gemini_searches(("cut", ["q", "r"])))
            cut.choices[0].finish_reason = "length"
            responses_.append(cut)
            n += 2
        responses_.append(
            with_fields(
                response([submit(values, f"s{index}")]), gemini_searches(*invocations)
            )
        )
        n += searches
    spend = pilot.Spend(50.0)
    record = pilot.run_household(
        make_scenario(),
        VARIABLES,
        fake_tool,
        FakeModel(responses_),
        spend,
        profile=profile,
    )
    totals = record["totals"]
    assert totals["web_searches"] == n
    assert totals["search_cost_usd"] == pytest.approx(n * 14 / 1000)
    assert totals["cost_usd"] == pytest.approx(
        totals["token_cost_usd"] + totals["search_cost_usd"]
    )
    assert spend.spent_usd == pytest.approx(totals["cost_usd"])


def test_the_audit_of_an_arm_that_never_searched_is_empty_not_an_error():
    record = _record("s", ["snap"], {"snap": 1.0})
    log = pilot.search_log({"s": record})
    assert log.empty and "scenario_id" in log.columns
    audit = pilot.search_audit(log)
    assert audit["flagged_households"] == [] and audit["logged_entries"] == 0
    json.dumps(audit, allow_nan=False)


# ---------------------------------------------------------------------------
# The v2-pilot prompt and the benchmark-search rule.
# ---------------------------------------------------------------------------


def _board_part(prompt: str, profile) -> str:
    assert prompt.endswith(profile.notice)
    return prompt[: len(prompt) - len(profile.notice)]


def test_the_v2_pilot_prompt_names_policyengine_nowhere_in_any_household():
    board = pilot.load_board()
    for sid in sorted(board["scenarios"]):
        for name in (SOL, OPUS):
            v1 = pilot.model_profile(name, "web")
            v2 = pilot.model_profile(name, "web", "v2-pilot", True)
            old, _ = pilot.build_initial_request(
                board["scenarios"][sid], board["variables"][sid], v1
            )
            new, kwargs = pilot.build_initial_request(
                board["scenarios"][sid], board["variables"][sid], v2
            )
            old, new = _board_part(old, v1), _board_part(new, v2)
            assert "policyengine" not in new.lower()
            assert "policyengine" not in json.dumps(kwargs["_answer_tool"]).lower()
            # Only the four definition lines differ.
            old_lines, new_lines = old.splitlines(), new.splitlines()
            assert len(old_lines) == len(new_lines)
            changed = [(a, b) for a, b in zip(old_lines, new_lines) if a != b]
            assert all("PolicyEngine" in a for a, _ in changed)
            assert len(changed) == old.count("PolicyEngine")


def test_v2_pilot_keeps_each_persons_label_in_their_definition():
    text = (
        "- spouse_medicaid_eligible: whether Spouse is eligible for Medicaid "
        "under PolicyEngine rules, not whether they are currently enrolled "
        "(1 if yes, 0 if no)"
    )
    rewritten = pilot.v2_pilot_text(text)
    assert rewritten.startswith(
        "- spouse_medicaid_eligible: whether Spouse is eligible"
    )
    assert "PolicyEngine" not in rewritten and "in any eligibility group" in rewritten


def test_the_guard_refuses_a_definition_left_unrewritten(monkeypatch):
    monkeypatch.setattr(pilot, "V2_PILOT_DEFINITIONS", ())
    board = pilot.load_board()
    with pytest.raises(ValueError, match="names PolicyEngine"):
        pilot.build_initial_request(
            board["scenarios"]["scenario_000"],
            board["variables"]["scenario_000"],
            pilot.model_profile(SOL, "web", "v2-pilot"),
        )


def test_the_school_meal_wording_matches_every_reference():
    """The v2-pilot meal definitions say a household with no one aged 5 to 17
    gets 0, and a universal-free-meals state's households get free meals."""
    board = pilot.load_board()
    reference = board["reference"].set_index(["scenario_id", "variable"])["value"]
    universal = {"CA", "CO", "MA", "ME", "MI", "MN", "NM", "NY", "VT"}
    for sid, scenario in board["scenarios"].items():
        people = [*scenario.adults, *scenario.children]
        school_age = any(5 <= person.age <= 17 for person in people)
        free = reference.get((sid, "free_school_meals_eligible"))
        reduced = reference.get((sid, "reduced_price_school_meals_eligible"))
        if not school_age:
            assert free in (0, None) and reduced in (0, None), sid
        elif scenario.state in universal:
            assert free == 1 and reduced in (0, None), sid


def test_the_benchmark_search_rule_rides_only_on_web_notices():
    for arm in ("web", "web+pe"):
        for name in (SOL, OPUS):
            with_rule = pilot.model_profile(name, arm, "v2-pilot", True)
            without = pilot.model_profile(name, arm, "v2-pilot")
            assert with_rule.notice == without.notice + pilot.BENCHMARK_SEARCH_RULE
    with pytest.raises(SystemExit):
        pilot.model_profile(SOL, "pe", "v2-pilot", True)
    with pytest.raises(SystemExit):
        pilot.model_profile(SOL, "web", "v3")
    assert pilot.model_profile(SOL, "pe", "v2-pilot").notice == pilot.TOOL_NOTICE
    labels = {
        pilot.model_profile(SOL, "web").arm2_label,
        pilot.model_profile(SOL, "web", "v2-pilot").arm2_label,
        pilot.model_profile(SOL, "web", "v2-pilot", True).arm2_label,
    }
    assert labels == {
        "gpt-6-sol+web",
        "gpt-6-sol+web@v2-pilot",
        "gpt-6-sol+web@v2-pilot+no-benchmark-search",
    }


def test_a_v2_pilot_repair_tool_names_policyengine_nowhere():
    board = pilot.load_board()
    sid = "scenario_001"
    variables = board["variables"][sid]
    meals = "free_school_meals_eligible"
    first = {v: 0 for v in variables if v != meals}
    model = FakeModel([response([submit(first)]), response([submit({meals: 0}, "s2")])])
    record = pilot.run_household(
        board["scenarios"][sid],
        variables,
        fake_tool,
        model,
        pilot.Spend(50.0),
        profile=pilot.model_profile(pilot.MODEL_NAME, "pe", "v2-pilot"),
    )
    assert record["status"] == "complete" and record["repair_rounds"] == 1
    assert record["prompt_version"] == "v2-pilot"
    assert record["sent_board_prompt_sha256"] != record["board_prompt_sha256"]
    for request in model.requests:
        answer = [
            t for t in request["tools"] if t["function"]["name"] == "submit_outputs"
        ]
        assert "policyengine" not in json.dumps(answer).lower()


def test_records_name_one_prompt_setup_and_old_records_are_v1():
    assert pilot.records_prompt({"a": {}, "b": {"prompt_version": "v1"}}) == (
        "v1",
        False,
    )
    assert pilot.records_prompt(
        {"a": {"prompt_version": "v2-pilot", "benchmark_search_rule": True}}
    ) == ("v2-pilot", True)
    with pytest.raises(SystemExit):
        pilot.records_prompt({"a": {"prompt_version": "v2-pilot"}, "b": {}})
