"""The calculator package against the harness it is copied from.

``policybench_calculator.core`` must be the calculator inside
``scripts/tool_pilot_argon.py`` and nothing else: the same definitions, the
same tool schemas, the same reading of every call. The harness cannot import
the package while the confirmatory runner pins it
(``scripts/confirmatory_run.py``, ``TREATMENT_PATHS``), so these tests hold
the two copies together. None of them needs the engine.
"""

from __future__ import annotations

import ast
import builtins
import copy
import hashlib
import itertools
import json
import symtable
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

import sync_calculator_core as sync  # noqa: E402
import tool_pilot_argon as pilot  # noqa: E402

from policybench_calculator import core  # noqa: E402

# Every set of features an arm can offer: concise only beside explain.
FEATURE_SETS = [
    frozenset(chosen)
    for size in range(len(pilot.TOOL_FEATURES) + 1)
    for chosen in itertools.combinations(pilot.TOOL_FEATURES, size)
    if not (pilot.CONCISE in chosen and pilot.EXPLAIN not in chosen)
]


def _statements(path: Path) -> dict[str, ast.stmt]:
    return {
        name: node
        for node in ast.parse(path.read_text()).body
        for name in sync.statement_names(node)
    }


def test_core_is_the_sync_scripts_output_for_this_harness():
    assert sync.CORE.read_text() == sync.render(sync.HARNESS.read_text()), (
        "policybench_calculator/core.py is stale: run scripts/sync_calculator_core.py"
    )
    assert sync.main(["--check"]) == 0


def test_every_definition_is_the_harnesss():
    """Independent of how the sync script slices the source: each module-level
    name in the copy has the harness's syntax tree, in the harness's order."""
    harness, copied = _statements(sync.HARNESS), _statements(sync.CORE)
    assert set(sync.ENTRY_POINTS) <= set(copied)
    assert len(copied) > 100
    for name, node in copied.items():
        assert name in harness, f"{name} is not in the harness"
        assert ast.dump(node) == ast.dump(harness[name]), name
    assert list(copied) == [name for name in harness if name in copied]


def test_the_copy_defines_every_name_it_reads():
    source = sync.CORE.read_text()
    table = symtable.symtable(source, "core.py", "exec")
    for node in ast.parse(source).body:
        if not sync.statement_names(node):
            continue
        for name in sync.statement_reads(node, table):
            assert (
                hasattr(core, name)
                or hasattr(builtins, name)
                or name in sync.MODULE_NAMES
            ), name


def test_the_copys_values_are_the_harnesss():
    """Every constant: the limits, the descriptions, the wording tables, and
    the paths (so the package sits where the harness's files are)."""
    compared = 0
    for name in _statements(sync.CORE):
        mine, theirs = getattr(core, name), getattr(pilot, name)
        if callable(mine) or name == "_STATED_ENGINE":
            # Functions and classes are compared by syntax tree above; the
            # stated engine is run state, compared under stating_engine below.
            continue
        assert mine == theirs, name
        compared += 1
    assert compared > 40
    assert core.ROOT == pilot.ROOT == ROOT
    assert core.FIX_MODULE == pilot.FIX_MODULE and core.SNAPSHOT == pilot.SNAPSHOT


@pytest.mark.parametrize("engine", ["2.41.0", "2.60.4"])
def test_both_build_the_same_tool_for_every_feature_set(engine):
    assert len(FEATURE_SETS) == 96
    with pilot.stating_engine(engine), core.stating_engine(engine):
        for features in FEATURE_SETS:
            mine = core.calculate_tool_schema(features=features)
            theirs = pilot.calculate_tool_schema(features=features)
            # The dumps compare key order too: it is what a provider is sent.
            assert json.dumps(mine) == json.dumps(theirs), sorted(features)
            assert f"policyengine-us {engine}" in mine["function"]["description"]
        for version in (1, 2):
            assert core.calculate_tool_schema(version) == pilot.calculate_tool_schema(
                version
            )
    assert core.engine_text("policyengine-us 2.41.0") == pilot.engine_text(
        "policyengine-us 2.41.0"
    )


# sha256 of each feature set's tool schema (json.dumps with sorted keys, as the
# harness's profile_treatment hashes it) in the household records of the
# October and November 2026 development runs, which ran on policyengine-us
# 2.60.4. The records themselves stay outside the repository with their
# household set; a schema's hash says nothing about a household.
RECORDED_SCHEMA_SHA256 = {
    "explain": "c06768afd93c2acbe396dea6dbae9340703bbe7c2b3702cd68825e56e2cf85c9",
    "flat": "bb46d278e7236d5c1c8b5ec4d9b50ed568b13bd24d278a44959e7ff21518aecd",
    "labels": "7950b061b162f21ac0acdfa424e0199357017c12251eecd188718a1ef5af186b",
    "names": "552d7e25b054668128b4a64c82a01f067fe29bd27fef26d82690dabf440a6f88",
    "overrides": "569c424e860ffe7d66b45b76856d6a62ca44acc32415d3c588a6ef2891fef2d0",
    "placement": "ef387526f076662ae0e1145e5c5dfaf49257455c966c0f1ba1620b7f7b92f36c",
    "explain+concise": (
        "461caed5af5392b2563bcb7017746b8c29f637af3158725bc74815f9a2a444b8"
    ),
    "names+placement+overrides+explain": (
        "4776fa0d4f6421331ebd134643366e0c6dc16f4a84905cce818272c531a1c853"
    ),
    "names+labels+placement+overrides+flat": (
        "c21b6cd91e9cfa20a97bfdd7b83db892709d3d1e813865947e5d94b1336c0925"
    ),
    "names+labels+overrides+explain+concise+flat": (
        "8fff7ef8923ab8ff63539c065323bda08f341281d4fa05c672517766876b5d52"
    ),
    "names+labels+placement+explain+concise+flat": (
        "d658f8af57651d12d9524d5bcbd692bf7908e53b5fc2c3e4a30e9cf41358a34c"
    ),
    "labels+placement+overrides+explain+concise+flat": (
        "8510fe574c6948be9fcc96d4cd3e785e447a645cae7ccb3d3fc429cfea05a059"
    ),
    "names+placement+overrides+explain+concise+flat": (
        "5ba88703cdf1d668b7300ad52eb4c71ed3db5a9996140c60120bfa9748d6c768"
    ),
    "names+labels+placement+overrides+explain+concise": (
        "12420320789d05768a091bf926bf5bd37d10c37499fa419c2228763f2911d910"
    ),
    "names+labels+placement+overrides+explain+flat": (
        "899583b1d27c0f1277630b5bd050b48b8b8678d02d12d9885b19f5faf7532952"
    ),
    # Version 3 (the pe3 and web+pe3 arms): all seven features.
    "names+labels+placement+overrides+explain+concise+flat": (
        "8fff7ef8923ab8ff63539c065323bda08f341281d4fa05c672517766876b5d52"
    ),
}


def test_the_package_builds_the_schemas_the_development_runs_recorded():
    with core.stating_engine("2.60.4"):
        for written, recorded in RECORDED_SCHEMA_SHA256.items():
            schema = core.calculate_tool_schema(features=frozenset(written.split("+")))
            digest = hashlib.sha256(
                json.dumps(schema, sort_keys=True).encode()
            ).hexdigest()
            assert digest == recorded, written
    assert (
        RECORDED_SCHEMA_SHA256["+".join(core.TOOL_FEATURES)]
        == RECORDED_SCHEMA_SHA256["names+labels+overrides+explain+concise+flat"]
    ), "placement changes no schema text beside flat"


@pytest.mark.parametrize(
    "arm",
    [
        *pilot.ARMS,
        "pe:names",
        "pe:flat+names",
        "pe:explain+concise",
        "pe:concise",
        "pe:names+telepathy",
        "pe:",
        "PE3",
        "",
        None,
    ],
)
def test_arms_name_the_same_features(arm):
    def read(module):
        try:
            return module.arm_features(arm)
        except SystemExit as refusal:
            return ("refused", str(refusal))

    assert read(core) == read(pilot)


# A registry in each copy's own VariableInfo: entity, type, label, period,
# named values, and whether the engine computes it.
VARIABLES = {
    "age": ("person", "int", "age", "year"),
    "employment_income": ("person", "float", "employment income", "year"),
    "is_tax_unit_head": ("person", "bool", "head", "year"),
    "is_tax_unit_spouse": ("person", "bool", "spouse", "year"),
    "traditional_401k_contributions": ("person", "float", "401(k)", "year", None, True),
    "traditional_401k_contributions_desired": ("person", "float", "asked", "year"),
    "snap": ("spm_unit", "float", "SNAP", "month", None, True),
    "pre_subsidy_rent": ("person", "float", "rent", "year"),
    "spm_unit_energy_subsidy": ("spm_unit", "float", "energy", "year"),
    "qualified_passenger_vehicle_loan_interest": (
        "household",
        "float",
        "car loan",
        "year",
    ),
    "state_code": ("household", "Enum", "state", "year", ("CA", "LA")),
    "tax_unit_childcare_expenses": ("tax_unit", "float", "childcare", "year"),
    "marital_unit_flag": ("marital_unit", "bool", "flag", "year"),
    "has_esi": ("person", "bool", "ESI", "year"),
    "hours_worked_last_week": ("person", "float", "hours", "year"),
    "weekly_hours_worked_before_lsr": ("person", "float", "hours", "year"),
    "school_meal_tier": ("spm_unit", "Enum", "tier", "year", ("FREE", "PAID"), True),
    "filing_status": ("tax_unit", "Enum", "status", "year", ("SINGLE", "JOINT"), True),
    "family_note": ("family", "str", "note", "year"),
}
REGISTRIES = {
    module: {name: module.VariableInfo(*fields) for name, fields in VARIABLES.items()}
    for module in (pilot, core)
}

# Names as a model writes them: the engine's, the same with spaces, hyphens
# or capitals, labels the prompts show, benchmark output keys, and nonsense.
_WRITTEN = sorted(VARIABLES)
_WRITTEN += [name.replace("_", " ") for name in _WRITTEN[::2]]
_WRITTEN += [name.replace("_", "-").title() for name in _WRITTEN[1:12:3]]
_WRITTEN += [
    "gross wages and salaries",
    "Gross wages and salaries",
    "usual weekly hours worked",
    "has employer-sponsored insurance",
    "state",
    "free_school_meals_eligible",
    "federal_income_tax",
    "snap_benefits",
    "members",
    "telepathy",
    "",
    " age ",
]
written_names = st.sampled_from(_WRITTEN)
scalars = st.one_of(
    st.integers(-3, 10**6),
    st.floats(width=32),
    st.booleans(),
    st.sampled_from(["CA", "LA", "FREE", "JOINT", "x", "", "40"]),
    st.none(),
)
periods = st.sampled_from(["2026", "2026-01", "2026-13", "1999", "year", ""])
values = st.one_of(
    scalars,
    st.dictionaries(periods, scalars, max_size=3),
    st.lists(scalars, max_size=2),
)
facts = st.dictionaries(written_names, values, max_size=6)
person_names = st.sampled_from(["head", "kid", "third", "", "n" * 70])
flat_people = st.lists(
    st.one_of(
        st.fixed_dictionaries(
            {},
            optional={
                "name": st.one_of(person_names, st.none(), st.integers(0, 2)),
                "role": st.sampled_from(["head", "spouse", "dependent", "child", None]),
                "facts": st.one_of(facts, st.just([])),
                "age": st.integers(0, 90),
            },
        ),
        st.just("someone"),
    ),
    max_size=4,
)
households = st.one_of(
    st.fixed_dictionaries(
        {},
        optional={
            "state": st.sampled_from(["CA", "LA", "ZZ", None, 6]),
            "people": st.one_of(flat_people, st.just({})),
            "household_facts": st.one_of(facts, st.just([]), st.none()),
            "notes": st.just("extra"),
        },
    ),
    st.sampled_from(["not json", None, 3]),
)
members = st.one_of(
    st.lists(st.sampled_from(["head", "kid", "third", "ghost"]), max_size=3),
    st.sampled_from(["head", None]),
)
units = st.dictionaries(
    st.sampled_from(["first", "second", ""]),
    st.one_of(
        st.builds(lambda inputs, people: {**inputs, "members": people}, facts, members),
        facts,
        st.just("unit"),
    ),
    max_size=2,
)
situations = st.one_of(
    st.fixed_dictionaries(
        {},
        optional={
            "people": st.one_of(
                st.dictionaries(person_names, st.one_of(facts, st.just(3)), max_size=3),
                st.just([]),
            ),
            **{group: st.one_of(units, st.just({})) for group in pilot.GROUPS},
            "axes": st.just([]),
        },
    ),
    st.sampled_from(["{not json", None, []]),
)


def _maybe_json(strategy):
    """A value, or the same value written as a JSON string, as a model writes
    the `situation` and `household` arguments."""
    return st.one_of(strategy, strategy.map(json.dumps))


name_lists = st.one_of(
    st.lists(written_names, max_size=4),
    written_names,
    st.sampled_from([None, [3], {}]),
)
calls = st.fixed_dictionaries(
    {},
    optional={
        "situation": _maybe_json(situations),
        "household": _maybe_json(households),
        "variables": name_lists,
        "period": st.sampled_from(["2026", "2026-02", 2026, "", None, "soon", True]),
        "explain": name_lists,
        "detail": st.sampled_from(["brief", "full", "long", None]),
        "__tool_features__": st.just(["names"]),
    },
)
messages = st.one_of(_maybe_json(calls), st.sampled_from(["{not json", [], None, 7]))


# The strategies above write mostly nonsense, which exercises every refusal.
# The ones below write a household the validator accepts and then make up to
# two slips a model makes, so both copies are also compared on requests they
# accept, with and without notes.
PERSON_INPUTS = [
    name
    for name, fields in VARIABLES.items()
    if fields[0] == "person" and not name.startswith("is_tax_unit_")
]
INPUTS_OF = {
    entity: [name for name, fields in VARIABLES.items() if fields[0] == entity]
    for entity in pilot.GROUPS.values()
}
UNIT_INPUTS = [name for names in INPUTS_OF.values() for name in names]
PROMPT_LABELS = {
    "employment_income": "gross wages and salaries",
    "hours_worked_last_week": "usual weekly hours worked",
    "has_esi": "has employer-sponsored insurance",
}
SLIPS = (
    "spaces",
    "capitals",
    "label",
    "unknown name",
    "wrong type",
    "dated",
    "bad period",
    "misplaced",
    "stray key",
    "written output",
    "unknown output",
    "no outputs",
    "other shape",
    "explain",
    "detail",
    "forged features",
    "people",
)


def _typed(name: str):
    """A value of the variable's own type."""
    value_type, named = VARIABLES[name][1], (*VARIABLES[name], None)[4]
    if value_type == "int":
        return st.integers(0, 90)
    if value_type == "float":
        return st.one_of(st.integers(0, 10**6), st.floats(0, 10**6, width=32))
    if value_type == "bool":
        return st.booleans()
    if value_type == "Enum":
        return st.sampled_from(named)
    return st.sampled_from(["note", ""])


@st.composite
def _inputs(draw, names, max_size=3):
    chosen = draw(st.lists(st.sampled_from(names), max_size=max_size, unique=True))
    return {name: draw(_typed(name)) for name in chosen}


@st.composite
def written_cases(draw):
    """(features, message, framed): a call the validator accepts, in the shape
    its features take (`household` under flat, else `situation`), with none,
    one or two of SLIPS made in it."""
    features = draw(st.sampled_from(FEATURE_SETS))
    flat = pilot.FLAT in features
    names = ["head", "kid", "third"][: draw(st.sampled_from([1, 2, 2, 3]))]
    people = {name: draw(_inputs(PERSON_INPUTS)) for name in names}
    units = {
        entity: draw(_inputs(INPUTS_OF[entity], 2)) if INPUTS_OF[entity] else {}
        for entity in pilot.GROUPS.values()
    }
    if flat:
        household_facts = {k: v for inputs in units.values() for k, v in inputs.items()}
        state = household_facts.pop("state_code", "CA")
        payload = {
            "state": state,
            "people": [
                {"role": "dependent" if index else "head", "facts": facts}
                for index, facts in enumerate(people.values())
            ],
            "household_facts": household_facts,
        }
        containers = [person["facts"] for person in payload["people"]]
        unit_containers = [payload["household_facts"]]
    else:
        payload = {"people": people}
        for group, entity in pilot.GROUPS.items():
            if units[entity] or draw(st.booleans()):
                payload[group] = {
                    f"{entity}_1": {"members": list(names), **units[entity]}
                }
        containers = list(people.values())
        unit_containers = [
            unit for group in pilot.GROUPS for unit in payload.get(group, {}).values()
        ]
    known = st.sampled_from(sorted(VARIABLES))
    arguments = {"variables": draw(st.lists(known, min_size=1, max_size=3))}
    if draw(st.booleans()):
        arguments["period"] = draw(st.sampled_from(["2026", "2026-02", 2026]))
    if pilot.EXPLAIN in features and draw(st.booleans()):
        arguments["explain"] = draw(st.lists(known, max_size=3))
    if pilot.CONCISE in features and draw(st.booleans()):
        arguments["detail"] = draw(st.sampled_from(["brief", "full"]))

    def a_fact(pool):
        """A container that holds a fact, and one of its names; or None."""
        holding = [facts for facts in pool if set(facts) - {"members"}]
        if not holding:
            return None, None
        facts = draw(st.sampled_from(holding))
        return facts, draw(st.sampled_from(sorted(set(facts) - {"members"})))

    for slip in draw(st.sampled_from([[], [], [0], [0], [0, 1]])):
        del slip
        kind = draw(st.sampled_from(SLIPS))
        facts, name = a_fact(containers + unit_containers)
        if kind in ("spaces", "capitals", "label", "unknown name") and facts:
            written = {
                "spaces": name.replace("_", " "),
                "capitals": name.replace("_", "-").title(),
                "label": PROMPT_LABELS.get(name, name.upper()),
                "unknown name": "telepathy",
            }[kind]
            facts[written] = facts.pop(name)
        elif kind == "wrong type" and facts:
            facts[name] = draw(scalars)
        elif kind in ("dated", "bad period") and facts:
            period = "2026-01" if kind == "dated" else draw(periods)
            facts[name] = {period: facts[name]}
        elif kind == "misplaced":
            source, name = a_fact(draw(st.sampled_from([containers, unit_containers])))
            target = draw(st.sampled_from(containers + unit_containers))
            if source is not None and target is not source:
                target[name] = source.pop(name)
        elif kind == "stray key":
            draw(st.sampled_from([payload, arguments, *containers]))["axes"] = []
        elif kind == "written output":
            arguments["variables"] = draw(st.lists(written_names, max_size=3))
        elif kind == "unknown output":
            arguments["variables"] = [*arguments["variables"], "snap_benefits"]
        elif kind == "no outputs":
            arguments["variables"] = draw(st.sampled_from([[], None, "age", [3]]))
        elif kind == "explain":
            arguments["explain"] = draw(st.lists(written_names, max_size=4))
        elif kind == "detail":
            arguments["detail"] = draw(st.sampled_from(["brief", "long", None]))
        elif kind == "forged features":
            arguments["__tool_features__"] = ["names"]
        elif kind == "people" and flat:
            payload["people"].append(
                draw(
                    st.sampled_from(
                        [
                            {"role": "head", "facts": {}},
                            {"role": "spouse", "facts": {"age": 40}},
                            {"role": "child", "facts": {}},
                            {"role": "dependent", "name": "head", "facts": {}},
                            {"role": "dependent", "facts": {"is_tax_unit_head": True}},
                        ]
                    )
                )
            )
        elif kind == "people" and unit_containers:
            draw(st.sampled_from(unit_containers))["members"] = draw(
                st.sampled_from([[], ["ghost"], [names[0], names[0]], "head"])
            )
        elif kind == "other shape":
            flat = not flat
    arguments["household" if flat else "situation"] = (
        json.dumps(payload) if draw(st.booleans()) else payload
    )
    message = json.dumps(arguments) if draw(st.booleans()) else arguments
    return features, message, draw(st.sampled_from([True] * 7 + [False]))


def _reading(module, features, arguments, framed) -> str:
    """How a copy's worker reads one message, as text (so NaN compares equal
    and key order counts)."""
    message = copy.deepcopy(arguments)
    if framed:
        message = module.tool_call_frame(features, message)
    try:
        outcome = module.worker_request(message, REGISTRIES[module])
    except Exception as error:  # the two must fail alike too
        outcome = ("raised", type(error).__name__, str(error))
    return json.dumps(outcome)


@settings(max_examples=1000, deadline=None, derandomize=True, database=None)
@given(st.sampled_from(FEATURE_SETS), messages, st.booleans())
def test_both_refuse_any_malformed_call_alike(features, arguments, framed):
    assert _reading(core, features, arguments, framed) == _reading(
        pilot, features, arguments, framed
    )


@settings(max_examples=2000, deadline=None, derandomize=True, database=None)
@given(written_cases())
def test_both_read_any_written_call_alike(case):
    assert _reading(core, *case) == _reading(pilot, *case)


def test_the_written_calls_are_accepted_and_refused_and_noted():
    """The differential above is worth its name only if its calls reach the
    validator's every outcome: accepted, accepted with notes (a name read, an
    input moved, a formula replaced) and refused."""
    tally = {"accepted": 0, "noted": 0, "refused": 0, "unframed": 0}

    @settings(max_examples=600, deadline=None, derandomize=True, database=None)
    @given(written_cases())
    def count(case):
        features, arguments, framed = case
        message = copy.deepcopy(arguments)
        if framed:
            message = core.tool_call_frame(features, message)
        request, error = core.worker_request(message, REGISTRIES[core])
        tally["unframed"] += not framed
        tally["accepted" if request is not None else "refused"] += 1
        tally["noted"] += bool(request and request.get("notes"))
        assert (request is None) != (error is None)

    count()
    assert tally["accepted"] >= 150 and tally["noted"] >= 100, tally
    assert tally["refused"] >= 100 and tally["unframed"] >= 15, tally


def test_both_read_a_forged_frame_alike():
    arguments = {"situation": {"people": {"head": {"age": 40}}}, "variables": ["age"]}
    for frame in (
        ("calculate", ("telepathy",), arguments),
        ("calculate", ("concise",), arguments),
        ("calculate", ["names"], arguments),
        ("calculate", ({},), arguments),
        ("calculate", ("names",)),
        ("compute", ("names",), arguments),
    ):
        assert core.worker_request(frame, REGISTRIES[core]) == pilot.worker_request(
            frame, REGISTRIES[pilot]
        )


class _FakeArray(list):
    pass


class _FakeSimulation:
    def __init__(self, tax_benefit_system, situation):
        if "bad" in situation["people"]:
            raise ValueError("bad person")
        self.populations = {
            "person": SimpleNamespace(ids=list(situation["people"])),
            "spm_unit": SimpleNamespace(ids=["spm"]),
        }

    def calculate(self, name, period):
        if name == "snap":
            return _FakeArray([1234.567])
        if name == "pre_subsidy_rent":
            raise KeyError("no rent")
        return _FakeArray([True, float("inf")][: len(self.populations["person"].ids)])


@pytest.mark.parametrize("people", [{"head": {}, "kid": {}}, {"bad": {}}])
def test_both_execute_a_request_alike(people):
    request = {
        "situation": {"people": people},
        "variables": ["snap", "age", "pre_subsidy_rent"],
        "period": "2026",
        "notes": ["read 'Age' as age"],
    }
    mine = core.execute_request(None, REGISTRIES[core], request, _FakeSimulation)
    theirs = pilot.execute_request(None, REGISTRIES[pilot], request, _FakeSimulation)
    assert json.dumps(mine) == json.dumps(theirs)
    assert ("error" in mine) == ("bad" in people)


def _echo_worker(conn, fix_path, reform):
    conn.send(("ready", None))
    while True:
        args = conn.recv()
        if args is None:
            return
        conn.send(("ok", {"received": args}))


@pytest.mark.parametrize("features", [frozenset(), frozenset({"flat", "names"})])
def test_both_pools_send_their_workers_the_same_message(features):
    received = []
    for module in (core, pilot):
        pool = module.ToolPool(
            size=1, timeout=5.0, worker_target=_echo_worker, tool_features=features
        )
        try:
            result, _ = pool.call({"x": 1})
            received.append(result)
            assert pool.counters() == {"timeouts": 0, "crashes": 0, "lost": 0}
        finally:
            pool.close()
    assert received[0] == received[1]
    assert (received[0]["received"] == {"x": 1}) == (not features)
