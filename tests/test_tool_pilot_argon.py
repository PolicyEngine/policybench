"""The Argon tool pilot's validator, conversation loop, scoring and diagnosis.

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
from hypothesis import given, settings
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
def test_validator_never_raises_and_accepts_only_known_names(args):
    """Invariant: any input gets exactly one of a request or an error, and an
    accepted request names only registry variables on their own entities."""
    request, error = pilot.normalize_request(args, REGISTRY)
    assert (request is None) != (error is None)
    if request is None:
        return
    for name in request["variables"]:
        assert name in REGISTRY
    for person in request["situation"]["people"].values():
        for name, periods in person.items():
            assert REGISTRY[name].entity == "person"
            assert all(pilot.PERIOD_RE.match(k) for k in periods)
    for group, entity in pilot.GROUPS.items():
        for unit in request["situation"].get(group, {}).values():
            for name in unit:
                assert name == "members" or REGISTRY[name].entity == entity


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
    messages, kwargs = pilot.build_initial_request(scenario, VARIABLES)
    assert messages[0]["content"] == board_messages[0]["content"] + pilot.TOOL_NOTICE
    assert "caching" not in kwargs


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


def call_record(values: dict, period="2026", people=("head", "kid")):
    sit = situation()
    sit["people"] = {p: {"age": 30} for p in people}
    return {
        "name": pilot.TOOL_NAME,
        "arguments": json.dumps(
            {"situation": json.dumps(sit), "variables": list(values)}
        ),
        "result": {
            "results": {
                name: {"entity": "x", "period": period, "values": vals}
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
