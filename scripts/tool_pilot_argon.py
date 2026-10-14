"""Internal pilot: Gemini 4 Argon with a PolicyEngine tool on the board's 100 US
households. Not a board condition, and nothing here is published.

The benchmark has one condition, ``no_tools`` (docs/benchmark_card.md,
"Evaluation conditions"). This script stays outside the board pipeline: it
writes only under --out-dir, never touches the run store, the snapshot, the
cache or the dashboard, and labels its rows ``gemini-4-argon+pe-tool`` so no
board export can take them for a board row.

Arms, on the same 100 households:
  1. No tools: Argon's frozen board predictions (release dashboard-data-20261014,
     PR #221), read from the snapshot and never re-run.
  2. PolicyEngine tool: the board prompt plus TOOL_NOTICE, the board's
     ``submit_outputs`` answer tool, and ``calculate_household``, which runs the
     reference engine on a situation the model writes as JSON. The reference
     engine is the installed policyengine-us (2.41.0) with the reference
     builder's convention reform, reference_audit/2026-09-28/fixes/latest_final.py
     (reference_audit/2026-10-12-engine-upgrade/scripts/build_references_upgrade.py
     computes every reference on that system). The ``oracle`` subcommand checks
     that the reference situations reproduce every scored reference through it.

The model writes JSON only. The tool parses it, checks every name against the
engine's variable registry, and passes plain data to policyengine_us.Simulation
in a separate worker process with a per-call timeout. No model-written text is
executed.

Subcommands:
  oracle    reference situations through the tool engine
  run       call the model (needs GEMINI_API_KEY); one JSON record per household
  score     both arms through the board's analyze_no_tools on the scored outputs
  diagnose  classify every arm-2 miss
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import difflib
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import multiprocessing as mp
import os
import queue
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
FIX_MODULE = ROOT / "reference_audit/2026-09-28/fixes/latest_final.py"
# The bytes the 2.41.0 references were built with: the sidecar's 2026-10-13
# engine_upgrade revision pins latest_final.py to this sha256. The modules it
# composes are checked end to end by the oracle subcommand.
FIX_MODULE_SHA256 = "dbbdd228b99933c6f336af97970821c25c863a18606285e8d6d9ffb3bc9af78e"

MODEL_NAME = "gemini-4-argon"
ARM1_LABEL = MODEL_NAME
ARM2_LABEL = "gemini-4-argon+pe-tool"
YEAR = 2026
REFERENCE_ENGINE = "2.41.0"

TOOL_NAME = "calculate_household"
TOOL_TURN_CAP = 8
MAX_CALCULATIONS_PER_TURN = 4
# Tool turns, then one forced answer turn, two repair turns and a margin for
# replies that call no function.
MAX_TOTAL_TURNS = TOOL_TURN_CAP + 5
MAX_REPAIR_ROUNDS = 2
MAX_PROVIDER_ATTEMPTS = 3
TOOL_TIMEOUT_SECONDS = 60
WORKER_START_TIMEOUT_SECONDS = 900
DEFAULT_BUDGET_USD = 50.0

MAX_PEOPLE = 16
MAX_UNITS_PER_GROUP = 16
MAX_VARIABLES = 40
MAX_SITUATION_CHARS = 200_000
MAX_PROBLEMS = 20
MAX_MESSAGE_CHARS = 2_000
PERIOD_RE = re.compile(r"^(?:20[0-4]\d)(?:-(?:0[1-9]|1[0-2]))?$")

GROUPS = {
    "tax_units": "tax_unit",
    "spm_units": "spm_unit",
    "families": "family",
    "marital_units": "marital_unit",
    "households": "household",
}
ENTITY_GROUP = {"person": "people", **{v: k for k, v in GROUPS.items()}}

TOOL_NOTICE = (
    "\n\nYou also have a `calculate_household` function. It runs PolicyEngine US "
    "(policyengine-us 2.41.0), an open-source rules engine for US federal and "
    "state taxes and benefits, on a household situation you build from the facts "
    "above. You may call it in up to 8 turns. Then call `submit_outputs` exactly "
    "once with your final answers, as instructed above."
)

CALCULATE_DESCRIPTION = (
    "Run PolicyEngine US (policyengine-us 2.41.0) on one household and return "
    "the requested variables. `situation` is a PolicyEngine household JSON "
    "object with the entity groups people, tax_units, spm_units, families, "
    "marital_units and households. Name each person and each unit; every unit "
    "lists its `members` by person name, and a group left out puts everyone in "
    "one unit. Set each input under its policyengine-us variable name as "
    '{period: value}, for example "age": {"2026": 40}; a period is a year '
    '("2026") or a month ("2026-01"), and a bare value is read as the call\'s '
    "`period`. Inputs you do not set take the engine's defaults. `variables` "
    'lists policyengine-us variables to compute for `period` (default "2026"). '
    "Each result gives the variable's entity, label and value for each member of "
    "that entity; a monthly variable computed for a year is summed over its "
    "months. An unknown name, a variable set on the wrong entity, or a malformed "
    "situation returns an error with suggestions instead of results."
)


def calculate_tool_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": CALCULATE_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "situation": {
                        "type": "string",
                        "description": (
                            "The household situation as a JSON object, written "
                            "as a JSON string."
                        ),
                    },
                    "variables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "policyengine-us variable names to compute (at most "
                            f"{MAX_VARIABLES})."
                        ),
                    },
                    "period": {
                        "type": "string",
                        "description": 'Year or month to compute, default "2026".',
                    },
                },
                "required": ["situation", "variables"],
            },
        },
    }


# ---------------------------------------------------------------------------
# The tool: validation (pure, testable without the engine) and execution.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VariableInfo:
    entity: str
    value_type: str
    label: str | None = None
    definition_period: str | None = None
    possible_values: tuple[str, ...] | None = None


def build_registry(system) -> dict[str, VariableInfo]:
    registry = {}
    for name, variable in system.variables.items():
        value_type = getattr(variable.value_type, "__name__", str(variable.value_type))
        possible = None
        if value_type == "Enum" and variable.possible_values is not None:
            possible = tuple(member.name for member in variable.possible_values)
        registry[name] = VariableInfo(
            entity=variable.entity.key,
            value_type=value_type,
            label=variable.label,
            definition_period=str(variable.definition_period),
            possible_values=possible,
        )
    return registry


def _suggest(name: str, registry: Mapping[str, VariableInfo], entity=None) -> str:
    names = [
        n for n, info in registry.items() if entity is None or info.entity == entity
    ]
    close = difflib.get_close_matches(name, names, n=5, cutoff=0.6)
    return f" Close matches: {', '.join(close)}." if close else ""


def _scalar_problem(value) -> str | None:
    if isinstance(value, bool) or isinstance(value, str):
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            return "is not a finite number"
        return None
    return "must be a number, true/false or a string"


def _type_problem(value, info: VariableInfo) -> str | None:
    if info.value_type in {"float", "int"}:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"takes a number ({info.value_type})"
    elif info.value_type == "bool":
        if not (isinstance(value, bool) or value in (0, 1)):
            return "takes true or false"
    elif info.value_type == "Enum":
        if not isinstance(value, str):
            return "takes one of its named values as a string"
        if info.possible_values and value not in info.possible_values:
            shown = ", ".join(info.possible_values[:30])
            return f"takes one of: {shown}"
    elif info.value_type == "str":
        if not isinstance(value, str):
            return "takes a string"
    return None


def _normalize_inputs(
    where: str,
    entity: str,
    data: dict,
    registry: Mapping[str, VariableInfo],
    period: str,
    problems: list[str],
    allow_members: bool,
) -> dict:
    out: dict[str, Any] = {}
    for name, value in data.items():
        if allow_members and name == "members":
            continue
        if not isinstance(name, str) or name not in registry:
            problems.append(
                f"{where}: unknown variable {name!r}."
                + (_suggest(name, registry) if isinstance(name, str) else "")
            )
            continue
        info = registry[name]
        if info.entity != entity:
            problems.append(
                f"{where}: {name} is a {info.entity} variable; set it under "
                f"{ENTITY_GROUP.get(info.entity, info.entity)}."
            )
            continue
        if isinstance(value, dict):
            periods = value
        else:
            periods = {period: value}
        normalized = {}
        for key, item in periods.items():
            if not isinstance(key, str) or not PERIOD_RE.match(key):
                problems.append(
                    f"{where}: {name} has period {key!r}; use a year such as "
                    '"2026" or a month such as "2026-01".'
                )
                continue
            scalar = _scalar_problem(item)
            if scalar is not None:
                problems.append(f"{where}: {name} for {key} {scalar}.")
                continue
            typed = _type_problem(item, info)
            if typed is not None:
                problems.append(f"{where}: {name} {typed}.")
                continue
            normalized[key] = item
        out[name] = normalized
    return out


def normalize_request(
    args, registry: Mapping[str, VariableInfo]
) -> tuple[dict | None, dict | None]:
    """Check a calculate_household call; return (request, None) or (None, error).

    Accepts only plain JSON data. Every input and output name must be a
    variable of the engine, on its own entity; nothing else in the situation
    (axes, reforms, parameters) is accepted.
    """
    problems: list[str] = []

    def fail() -> tuple[None, dict]:
        return None, {
            "error": "validation",
            "problems": problems[:MAX_PROBLEMS],
            "problem_count": len(problems),
        }

    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError as error:
            problems.append(f"arguments are not valid JSON: {error}")
            return fail()
    if not isinstance(args, dict):
        problems.append("arguments must be an object")
        return fail()
    unknown = sorted(set(args) - {"situation", "variables", "period"})
    if unknown:
        problems.append(f"unknown arguments: {', '.join(map(str, unknown))}")

    period = args.get("period", str(YEAR))
    if period in (None, ""):
        period = str(YEAR)
    if isinstance(period, int) and not isinstance(period, bool):
        period = str(period)
    if not isinstance(period, str) or not PERIOD_RE.match(period):
        problems.append(
            f'period {period!r} must be a year ("2026") or a month ("2026-01")'
        )
        period = str(YEAR)

    situation = args.get("situation")
    if isinstance(situation, str):
        if len(situation) > MAX_SITUATION_CHARS:
            problems.append("situation is too large")
            return fail()
        try:
            situation = json.loads(situation)
        except json.JSONDecodeError as error:
            problems.append(f"situation is not valid JSON: {error}")
            return fail()
    if not isinstance(situation, dict):
        problems.append("situation must be a JSON object")
        return fail()
    if len(json.dumps(situation, default=str)) > MAX_SITUATION_CHARS:
        problems.append("situation is too large")
        return fail()
    extra = sorted(set(situation) - {"people", *GROUPS})
    if extra:
        problems.append(
            "situation accepts only people, "
            + ", ".join(GROUPS)
            + f"; remove {', '.join(map(str, extra))}"
        )

    people = situation.get("people")
    normalized: dict[str, Any] = {}
    if not isinstance(people, dict) or not people:
        problems.append("situation.people must be a non-empty object of named people")
        people = {}
    elif len(people) > MAX_PEOPLE:
        problems.append(f"at most {MAX_PEOPLE} people")
    normalized_people = {}
    for name, data in people.items():
        if not isinstance(name, str) or not name or len(name) > 64:
            problems.append(f"person name {name!r} must be a short string")
            continue
        if not isinstance(data, dict):
            problems.append(f"people.{name} must be an object of inputs")
            continue
        normalized_people[name] = _normalize_inputs(
            f"people.{name}", "person", data, registry, period, problems, False
        )
    normalized["people"] = normalized_people

    for group, entity in GROUPS.items():
        if group not in situation:
            continue
        units = situation[group]
        if not isinstance(units, dict) or not units:
            problems.append(f"{group} must be a non-empty object of named units")
            continue
        if len(units) > MAX_UNITS_PER_GROUP:
            problems.append(f"at most {MAX_UNITS_PER_GROUP} {group}")
        seen: dict[str, str] = {}
        normalized_units = {}
        for unit_name, unit in units.items():
            where = f"{group}.{unit_name}"
            if not isinstance(unit, dict):
                problems.append(f"{where} must be an object with members")
                continue
            members = unit.get("members")
            if (
                not isinstance(members, list)
                or not members
                or not all(isinstance(m, str) for m in members)
            ):
                problems.append(f"{where}.members must list person names")
                members = []
            for member in members:
                if member not in people:
                    problems.append(f"{where}: member {member!r} is not in people")
                elif member in seen:
                    problems.append(
                        f"{where}: {member} is already in {group}.{seen[member]}"
                    )
                else:
                    seen[member] = unit_name
            normalized_unit = {"members": list(members)}
            normalized_unit.update(
                _normalize_inputs(where, entity, unit, registry, period, problems, True)
            )
            normalized_units[unit_name] = normalized_unit
        normalized[group] = normalized_units

    variables = args.get("variables")
    if isinstance(variables, str):
        variables = [variables]
    if (
        not isinstance(variables, list)
        or not variables
        or not all(isinstance(v, str) for v in variables)
    ):
        problems.append("variables must be a non-empty list of variable names")
        variables = []
    elif len(variables) > MAX_VARIABLES:
        problems.append(f"at most {MAX_VARIABLES} variables per call")
    requested = []
    for name in variables:
        if name not in registry:
            problems.append(
                f"variables: unknown variable {name!r}." + _suggest(name, registry)
            )
        elif name not in requested:
            requested.append(name)

    if problems:
        return fail()
    return {"situation": normalized, "variables": requested, "period": period}, None


def _jsonable(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bytes):
        value = value.decode()
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        value = float(value)
        if not math.isfinite(value):
            return None
        return round(value, 2)
    return str(value)


def execute_request(system, registry, request: dict, simulation_cls=None) -> dict:
    if simulation_cls is None:
        from policyengine_us import Simulation as simulation_cls
    try:
        simulation = simulation_cls(
            tax_benefit_system=system, situation=copy.deepcopy(request["situation"])
        )
    except Exception as error:  # the engine's own message is the useful one
        return {
            "error": "engine",
            "message": f"{type(error).__name__}: {error}"[:MAX_MESSAGE_CHARS],
        }
    results = {}
    for name in request["variables"]:
        info = registry[name]
        try:
            array = simulation.calculate(name, request["period"])
        except Exception as error:
            results[name] = {
                "error": f"{type(error).__name__}: {error}"[:MAX_MESSAGE_CHARS]
            }
            continue
        if hasattr(array, "decode_to_str"):
            array = array.decode_to_str()
        ids = [str(i) for i in simulation.populations[info.entity].ids]
        results[name] = {
            "entity": info.entity,
            "label": info.label,
            "period": request["period"],
            "values": {i: _jsonable(v) for i, v in zip(ids, list(array))},
        }
    return {"results": results}


def load_fix_reform(path: Path = FIX_MODULE):
    if path == FIX_MODULE and _sha256(path) != FIX_MODULE_SHA256:
        raise SystemExit(f"{path} does not match the pinned sha256 {FIX_MODULE_SHA256}")
    spec = importlib.util.spec_from_file_location("tool_pilot_latest_final", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.reform


def build_tool_system(reform: bool = True, path: Path = FIX_MODULE):
    from policyengine_us import CountryTaxBenefitSystem

    if not reform:
        return CountryTaxBenefitSystem()
    return CountryTaxBenefitSystem(reform=load_fix_reform(path))


def _worker_main(conn, fix_path: str, reform: bool) -> None:
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    system = build_tool_system(reform=reform, path=Path(fix_path))
    registry = build_registry(system)
    conn.send(("ready", None))
    while True:
        try:
            args = conn.recv()
        except EOFError:
            return
        if args is None:
            return
        request, error = normalize_request(args, registry)
        if error is not None:
            conn.send(("ok", error))
            continue
        conn.send(("ok", execute_request(system, registry, request)))


class ToolPool:
    """Worker processes that hold the tool system, each call under a timeout."""

    def __init__(
        self,
        size: int,
        fix_path: Path = FIX_MODULE,
        timeout: float = TOOL_TIMEOUT_SECONDS,
        reform: bool = True,
    ):
        self._ctx = mp.get_context("spawn")
        self._fix_path = str(fix_path)
        self._reform = reform
        self.timeout = timeout
        self._idle: queue.Queue = queue.Queue()
        self.timeouts = 0
        self.crashes = 0
        starting = [self._start() for _ in range(size)]
        for worker in starting:
            self._idle.put(self._await_ready(worker))

    def _start(self):
        parent, child = self._ctx.Pipe()
        process = self._ctx.Process(
            target=_worker_main,
            args=(child, self._fix_path, self._reform),
            daemon=True,
        )
        process.start()
        return process, parent

    def _await_ready(self, worker):
        process, conn = worker
        if not conn.poll(WORKER_START_TIMEOUT_SECONDS):
            process.kill()
            raise RuntimeError("tool worker did not start")
        status, _ = conn.recv()
        if status != "ready":
            raise RuntimeError(f"tool worker failed to start: {status}")
        return worker

    def call(self, args) -> tuple[dict, float]:
        worker = self._idle.get()
        process, conn = worker
        started = time.perf_counter()
        try:
            conn.send(args)
            if conn.poll(self.timeout):
                _, result = conn.recv()
                self._idle.put(worker)
                return result, time.perf_counter() - started
            self.timeouts += 1
            result = {
                "error": "timeout",
                "message": f"the calculation exceeded {self.timeout:.0f} seconds",
            }
        except (EOFError, BrokenPipeError, OSError) as error:
            self.crashes += 1
            result = {"error": "engine", "message": f"tool worker failed: {error}"}
        elapsed = time.perf_counter() - started
        process.kill()
        process.join(timeout=10)
        self._idle.put(self._await_ready(self._start()))
        return result, elapsed

    def close(self) -> None:
        while not self._idle.empty():
            process, conn = self._idle.get()
            try:
                conn.send(None)
            except (BrokenPipeError, OSError):
                pass
            process.join(timeout=5)
            if process.is_alive():
                process.kill()


# ---------------------------------------------------------------------------
# Households, prompts and the conversation loop.
# ---------------------------------------------------------------------------


def load_board(snapshot: Path = SNAPSHOT):
    from policybench.reference_exclusions import (
        load_reference_exclusions,
        split_reference,
    )
    from policybench.scenarios import scenario_from_dict
    from policybench.spec import expand_programs_for_scenario

    meta = json.loads((snapshot / "reference_outputs.csv.meta.json").read_text())
    reference = pd.read_csv(snapshot / "reference_outputs.csv")
    scored, excluded = split_reference(reference, load_reference_exclusions(snapshot))
    scenarios_frame = pd.read_csv(snapshot / "scenarios.csv")
    scenarios = {}
    variables = {}
    for _, row in scenarios_frame.iterrows():
        scenario = scenario_from_dict(json.loads(row["scenario_json"]))
        scenarios[scenario.id] = scenario
        variables[scenario.id] = expand_programs_for_scenario(
            meta["programs"], scenario
        )
    return {
        "meta": meta,
        "reference": reference,
        "scored": scored,
        "excluded": excluded,
        "scenarios_frame": scenarios_frame,
        "scenarios": scenarios,
        "variables": variables,
    }


def build_initial_request(scenario, variables: list[str]) -> tuple[list[dict], dict]:
    """The board's request for this household, plus the tool notice and tool."""
    from policybench.config import MODELS
    from policybench.eval_no_tools import (
        _build_answer_tool,
        _chat_completion_request_kwargs,
        _completion_budget_ceiling,
    )

    model_id = MODELS[MODEL_NAME]
    messages, kwargs = _chat_completion_request_kwargs(scenario, variables, model_id)
    board_prompt = messages[0]["content"]
    messages = [{"role": "user", "content": board_prompt + TOOL_NOTICE}]
    answer_tool = _build_answer_tool(variables, country=scenario.country)
    kwargs = {k: v for k, v in kwargs.items() if k not in {"messages", "caching"}}
    kwargs["tools"] = [calculate_tool_schema(), answer_tool]
    kwargs["tool_choice"] = "required"
    kwargs["_board_prompt_sha256"] = hashlib.sha256(board_prompt.encode()).hexdigest()
    kwargs["_budget_ceiling"] = _completion_budget_ceiling(model_id)
    return messages, kwargs


def forced_answer_choice() -> dict:
    from policybench.eval_no_tools import ANSWER_FUNCTION_NAME, _tool_choice_for

    return _tool_choice_for(ANSWER_FUNCTION_NAME)


def _tool_calls(message) -> list:
    return list(getattr(message, "tool_calls", None) or [])


def _call_name(call) -> str | None:
    function = getattr(call, "function", None)
    if function is None and isinstance(call, dict):
        function = call.get("function")
    if function is None:
        return None
    return getattr(function, "name", None) or (
        function.get("name") if isinstance(function, dict) else None
    )


def _call_arguments(call):
    function = getattr(call, "function", None)
    if function is None and isinstance(call, dict):
        function = call.get("function")
    arguments = getattr(function, "arguments", None)
    if arguments is None and isinstance(function, dict):
        arguments = function.get("arguments")
    return arguments


def _call_id(call) -> str:
    return getattr(call, "id", None) or (
        call.get("id") if isinstance(call, dict) else ""
    )


def _message_dict(message) -> dict:
    if hasattr(message, "model_dump"):
        data = message.model_dump()
    elif isinstance(message, dict):
        data = dict(message)
    else:
        data = dict(vars(message))
    return {k: v for k, v in data.items() if v is not None}


def _has_thought_signature(message) -> bool:
    for call in _tool_calls(message):
        if "__thought__" in str(_call_id(call)):
            return True
        fields = getattr(call, "provider_specific_fields", None) or {}
        if isinstance(fields, dict) and fields.get("thought_signature"):
            return True
    fields = getattr(message, "provider_specific_fields", None) or {}
    return bool(isinstance(fields, dict) and fields.get("thought_signatures"))


class Spend:
    def __init__(self, budget_usd: float, spent_usd: float = 0.0):
        self.budget_usd = budget_usd
        self.spent_usd = spent_usd
        self._lock = threading.Lock()

    def add(self, usd: float | None) -> None:
        with self._lock:
            self.spent_usd += float(usd or 0.0)

    def exhausted(self, reserve_usd: float = 0.0) -> bool:
        with self._lock:
            return self.spent_usd + reserve_usd > self.budget_usd


class BudgetStop(RuntimeError):
    pass


def _request_with_retries(
    completion_fn, kwargs: dict
) -> tuple[Any, float, float, float]:
    from policybench.eval_no_tools import _run_request_with_wall_timeout, _should_retry

    for attempt in range(MAX_PROVIDER_ATTEMPTS):
        started_at = time.time()
        started = time.perf_counter()
        try:
            response = _run_request_with_wall_timeout(completion_fn, kwargs)
            return response, started_at, time.time(), time.perf_counter() - started
        except Exception as error:
            if attempt == MAX_PROVIDER_ATTEMPTS - 1 or not _should_retry(error):
                raise
            time.sleep(2 * (2**attempt))
    raise RuntimeError("unreachable")


def run_household(
    scenario,
    variables: list[str],
    tool_call: Callable[[Any], tuple[dict, float]],
    completion_fn: Callable[..., Any],
    spend: Spend,
    turn_cap: int = TOOL_TURN_CAP,
) -> dict:
    """One household's conversation: tool turns, then the board's answer tool."""
    from policybench.config import MODELS
    from policybench.eval_no_tools import (
        _apply_thinking_configuration,
        _build_answer_tool,
        _enforce_explanation_value_contract,
        _extract_usage_metadata,
        _missing_explanations,
        _response_finish_reason,
        _serialize_response_payload,
        extract_explanations,
        extract_predictions,
    )

    model_id = MODELS[MODEL_NAME]
    messages, base = build_initial_request(scenario, variables)
    board_prompt_sha256 = base.pop("_board_prompt_sha256")
    ceiling = base.pop("_budget_ceiling")
    calculate_tool = base["tools"][0]
    record: dict[str, Any] = {
        "scenario_id": scenario.id,
        "variables": variables,
        "board_prompt_sha256": board_prompt_sha256,
        "tool_notice_sha256": hashlib.sha256(TOOL_NOTICE.encode()).hexdigest(),
        "turns": [],
        "status": "running",
    }
    predictions: dict[str, float | None] = {v: None for v in variables}
    explanations: dict[str, str | None] = {v: None for v in variables}
    pending = list(variables)
    tool_turns = 0
    repair_rounds = 0
    forced = False
    answer_variables = list(variables)
    household_started = time.perf_counter()

    for turn_index in range(MAX_TOTAL_TURNS):
        if spend.exhausted():
            record["status"] = "budget_stop"
            break
        if repair_rounds:
            kind = "repair"
            tool_choice = forced_answer_choice()
            tools = [
                calculate_tool,
                _build_answer_tool(answer_variables, country=scenario.country),
            ]
        elif forced or tool_turns >= turn_cap:
            kind = "forced_answer"
            forced = True
            tool_choice = forced_answer_choice()
            tools = base["tools"]
        else:
            kind = "open"
            tool_choice = "required"
            tools = base["tools"]
        kwargs = {k: v for k, v in base.items() if k not in {"tools", "tool_choice"}}
        kwargs.update(
            {
                "model": model_id,
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
        _apply_thinking_configuration(kwargs, model_id)
        budget_key = (
            "max_completion_tokens"
            if "max_completion_tokens" in kwargs
            else "max_tokens"
        )
        escalated_from = None
        try:
            response, started_at, completed_at, latency = _request_with_retries(
                completion_fn, kwargs
            )
            finish_reason = _response_finish_reason(response, responses_api=False)
            if finish_reason == "length" and kwargs.get(budget_key, 0) < ceiling:
                usage = _extract_usage_metadata(response, model_id, messages, "")
                spend.add(usage.get("total_cost_usd"))
                record["turns"].append(
                    {
                        "index": turn_index,
                        "kind": kind,
                        "truncated_and_retried": True,
                        "completion_budget": kwargs.get(budget_key),
                        "latency_seconds": latency,
                        **usage,
                    }
                )
                escalated_from = kwargs.get(budget_key)
                kwargs[budget_key] = ceiling
                response, started_at, completed_at, latency = _request_with_retries(
                    completion_fn, kwargs
                )
                finish_reason = _response_finish_reason(response, responses_api=False)
        except Exception as error:
            record["status"] = "provider_error"
            record["error"] = f"{type(error).__name__}: {error}"[:MAX_MESSAGE_CHARS]
            break

        message = response.choices[0].message
        content = getattr(message, "content", None)
        calls = _tool_calls(message)
        raw = _serialize_response_payload(
            content=content, tool_calls=calls, function_call=None
        )
        usage = _extract_usage_metadata(
            response, model_id, messages, raw or content or ""
        )
        spend.add(usage.get("total_cost_usd"))
        turn = {
            "index": turn_index,
            "kind": kind,
            "tool_choice": tool_choice,
            "completion_budget": kwargs.get(budget_key),
            "escalated_from": escalated_from,
            "request_started_at": started_at,
            "request_completed_at": completed_at,
            "latency_seconds": latency,
            "finish_reason": finish_reason,
            "content": content,
            "reasoning_content": getattr(message, "reasoning_content", None),
            "has_thought_signature": _has_thought_signature(message),
            "calls": [],
            **usage,
        }
        record["turns"].append(turn)
        messages.append(_message_dict(message))

        answer_calls = [c for c in calls if _call_name(c) == "submit_outputs"]
        calculate_calls = [c for c in calls if _call_name(c) == TOOL_NAME]
        other_calls = [
            c for c in calls if c not in answer_calls and c not in calculate_calls
        ]

        if answer_calls:
            got = extract_predictions(
                content, answer_variables, tool_calls=answer_calls
            )
            got_explanations = extract_explanations(
                content, answer_variables, tool_calls=answer_calls
            )
            got, got_explanations = _enforce_explanation_value_contract(
                got, got_explanations, answer_variables
            )
            for variable in answer_variables:
                if got.get(variable) is not None:
                    predictions[variable] = got[variable]
                if got_explanations.get(variable):
                    explanations[variable] = got_explanations[variable]
            turn["calls"].append(
                {
                    "name": "submit_outputs",
                    "arguments": _call_arguments(answer_calls[0]),
                    "ignored_calls": len(calculate_calls)
                    + len(other_calls)
                    + len(answer_calls)
                    - 1,
                }
            )
            pending = [v for v in variables if predictions[v] is None]
            missing_explanation = _missing_explanations(explanations, variables)
            still = [
                v for v in variables if v in set(pending) | set(missing_explanation)
            ]
            for call in calls:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": _call_id(call),
                        "name": _call_name(call),
                        "content": json.dumps(
                            {"accepted": not still, "missing": still}
                            if call is answer_calls[0]
                            else {"error": "not run: submit_outputs ended the turn"}
                        ),
                    }
                )
            if not still:
                record["status"] = "complete"
                break
            if repair_rounds >= MAX_REPAIR_ROUNDS:
                record["status"] = "incomplete"
                break
            repair_rounds += 1
            answer_variables = still
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your submit_outputs call omitted or left unusable these "
                        f"outputs: {', '.join(still)}. Call submit_outputs again "
                        "with only these outputs, each with a numeric value and an "
                        "explanation ending with `value = X`."
                    ),
                }
            )
            continue

        if calculate_calls:
            tool_turns += 1
            for position, call in enumerate(calculate_calls):
                if position >= MAX_CALCULATIONS_PER_TURN:
                    result, tool_latency = (
                        {
                            "error": "not_run",
                            "message": (
                                f"at most {MAX_CALCULATIONS_PER_TURN} "
                                "calculations per turn"
                            ),
                        },
                        0.0,
                    )
                else:
                    result, tool_latency = tool_call(_call_arguments(call))
                turn["calls"].append(
                    {
                        "name": TOOL_NAME,
                        "arguments": _call_arguments(call),
                        "result": result,
                        "tool_latency_seconds": tool_latency,
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": _call_id(call),
                        "name": TOOL_NAME,
                        "content": json.dumps(result),
                    }
                )
            for call in other_calls:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": _call_id(call),
                        "name": _call_name(call) or "unknown",
                        "content": json.dumps({"error": "unknown function"}),
                    }
                )
            if tool_turns >= turn_cap:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"You have used all {turn_cap} calculation turns. Call "
                            "submit_outputs now with your final answers."
                        ),
                    }
                )
            continue

        for call in other_calls:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": _call_id(call),
                    "name": _call_name(call) or "unknown",
                    "content": json.dumps({"error": "unknown function"}),
                }
            )
        messages.append(
            {
                "role": "user",
                "content": "Call calculate_household or submit_outputs.",
            }
        )
    else:
        record["status"] = "turn_limit"

    if record["status"] == "running":
        record["status"] = "incomplete"
    record["predictions"] = predictions
    record["explanations"] = explanations
    record["tool_turns"] = tool_turns
    record["cap_hit"] = tool_turns >= turn_cap
    record["repair_rounds"] = repair_rounds
    record["wall_seconds"] = time.perf_counter() - household_started
    record["messages"] = messages
    record["totals"] = household_totals(record)
    return record


def _num(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def household_totals(record: dict) -> dict:
    turns = record.get("turns", [])
    calls = [c for t in turns for c in t.get("calls", []) if c.get("name") == TOOL_NAME]
    errors = [
        c for c in calls if isinstance(c.get("result"), dict) and "error" in c["result"]
    ]
    return {
        "model_turns": len(turns),
        "tool_calls": len(calls),
        "tool_errors": len(errors),
        "tool_error_kinds": sorted({c["result"]["error"] for c in errors}),
        "prompt_tokens": sum(_num(t.get("prompt_tokens")) for t in turns),
        "completion_tokens": sum(_num(t.get("completion_tokens")) for t in turns),
        "reasoning_tokens": sum(_num(t.get("reasoning_tokens")) for t in turns),
        "cached_prompt_tokens": sum(_num(t.get("cached_prompt_tokens")) for t in turns),
        "cost_usd": sum(_num(t.get("total_cost_usd")) for t in turns),
        "model_seconds": sum(_num(t.get("latency_seconds")) for t in turns),
        "tool_seconds": sum(_num(c.get("tool_latency_seconds")) for c in calls),
    }


# ---------------------------------------------------------------------------
# Subcommands.
# ---------------------------------------------------------------------------


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _versions() -> dict:
    out = {}
    for name in ("policyengine-us", "policyengine-core", "litellm"):
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = None
    return out


def _require_engine() -> None:
    version = _versions()["policyengine-us"]
    if version != REFERENCE_ENGINE:
        raise SystemExit(
            f"policyengine-us {version} is installed; the pilot pins "
            f"{REFERENCE_ENGINE}, the reference engine of release "
            "dashboard-data-20261014."
        )


def command_oracle(args) -> None:
    """Reference situations through the tool engine: every scored reference must
    come back within the board's tolerance."""
    _require_engine()
    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output

    board = load_board()
    scored_keys = set(zip(board["scored"].scenario_id, board["scored"].variable))
    values = board["reference"].set_index(["scenario_id", "variable"])["value"]
    rows = []
    for label, reform in (("reference_engine", True), ("plain_engine", False)):
        system = build_tool_system(reform=reform)
        registry = build_registry(system)
        for sid, scenario in board["scenarios"].items():
            situation = scenario.to_pe_household()
            request, error = normalize_request(
                {"situation": situation, "variables": ["age"]}, registry
            )
            if error is not None:
                raise SystemExit(
                    f"{sid}: the validator rejects the reference situation: {error}"
                )
            from policyengine_us import Simulation

            simulation = Simulation(
                tax_benefit_system=system, situation=request["situation"]
            )
            # The same household through the tool's execute path and the
            # diagnosis's output mapping, as a model's call would go.
            outputs = [v for v in board["variables"][sid] if (sid, v) in values.index]
            call_args = {
                "situation": json.dumps(situation),
                "variables": sorted(
                    {_pe_variable_for_output(v, "us") for v in outputs}
                ),
            }
            tool_request, tool_error = normalize_request(call_args, registry)
            if tool_error is not None:
                raise SystemExit(f"{sid}: {tool_error}")
            call = {
                "arguments": call_args,
                "result": execute_request(system, registry, tool_request),
            }
            for variable in outputs:
                value = float(
                    _extract_person_value(
                        simulation.calculate(
                            _pe_variable_for_output(variable, "us"), YEAR
                        ),
                        scenario,
                        variable,
                    )
                )
                rows.append(
                    {
                        "engine": label,
                        "scenario_id": sid,
                        "variable": variable,
                        "scored": (sid, variable) in scored_keys,
                        "reference": float(values[(sid, variable)]),
                        "tool": value,
                        "tool_path": tool_value_for_output(call, scenario, variable),
                    }
                )
    frame = pd.DataFrame(rows)
    frame["hit"] = [
        hit(variable, tool, reference)
        for variable, tool, reference in zip(
            frame.variable, frame.tool, frame.reference
        )
    ]
    frame["tool_path_hit"] = [
        hit(variable, tool, reference)
        for variable, tool, reference in zip(
            frame.variable, frame.tool_path, frame.reference
        )
    ]
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out / "oracle.csv", index=False)
    summary = (
        frame[frame.scored]
        .groupby("engine")
        .agg(
            scored_outputs=("hit", "size"),
            reproduced=("hit", "sum"),
            reproduced_through_tool_path=("tool_path_hit", "sum"),
        )
    )
    print(summary.to_string())
    (out / "oracle_summary.json").write_text(
        json.dumps(
            {
                "versions": _versions(),
                "fix_module_sha256": _sha256(FIX_MODULE),
                "summary": summary.reset_index().to_dict(orient="records"),
            },
            indent=2,
        )
    )


def hit(variable: str, prediction, reference) -> bool:
    """The board's exact-match test (policybench.analysis.row_hit_scores)."""
    from policybench.analysis import row_hit_scores

    if prediction is None or reference is None:
        return False
    try:
        if pd.isna(prediction) or pd.isna(reference):
            return False
    except (TypeError, ValueError):
        return False
    return row_hit_scores(variable, float(reference), float(prediction))["exact"] == 1.0


def command_run(args) -> None:
    _require_engine()
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is not set")
    from litellm import completion

    board = load_board()
    out = Path(args.out_dir)
    households_dir = out / "households"
    households_dir.mkdir(parents=True, exist_ok=True)
    ids = sorted(board["scenarios"])
    if args.scenarios:
        ids = [sid for sid in ids if sid in set(args.scenarios)]
    if args.limit:
        ids = ids[: args.limit]

    spent_before = 0.0
    done = set()
    for path in households_dir.glob("*.json"):
        record = json.loads(path.read_text())
        spent_before += _num(record.get("totals", {}).get("cost_usd"))
        if record.get("status") == "complete":
            done.add(record["scenario_id"])
    spend = Spend(args.budget_usd, spent_before)
    todo = [sid for sid in ids if sid not in done]
    manifest = {
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_head": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "script_sha256": _sha256(Path(__file__)),
        "versions": _versions(),
        "fix_module": str(FIX_MODULE.relative_to(ROOT)),
        "fix_module_sha256": _sha256(FIX_MODULE),
        "model": MODEL_NAME,
        "tool_notice": TOOL_NOTICE,
        "calculate_tool": calculate_tool_schema(),
        "turn_cap": TOOL_TURN_CAP,
        "max_calculations_per_turn": MAX_CALCULATIONS_PER_TURN,
        "tool_timeout_seconds": TOOL_TIMEOUT_SECONDS,
        "budget_usd": args.budget_usd,
        "spent_before_usd": spent_before,
        "households": todo,
        "workers": args.workers,
    }
    (out / f"manifest-{manifest['started_at_utc'].replace(':', '')}.json").write_text(
        json.dumps(manifest, indent=2)
    )
    print(f"{len(todo)} households to run; ${spent_before:.4f} already spent")
    if not todo:
        return
    pool = ToolPool(size=args.workers)
    try:

        def one(sid: str) -> dict:
            if spend.exhausted(args.reserve_usd):
                return {"scenario_id": sid, "status": "budget_stop"}
            record = run_household(
                board["scenarios"][sid],
                board["variables"][sid],
                pool.call,
                completion,
                spend,
            )
            (households_dir / f"{sid}.json").write_text(
                json.dumps(record, indent=1, default=str)
            )
            totals = record["totals"]
            print(
                f"{sid} {record['status']} turns={totals['model_turns']} "
                f"calls={totals['tool_calls']} errors={totals['tool_errors']} "
                f"cost=${totals['cost_usd']:.4f} spent=${spend.spent_usd:.4f}",
                flush=True,
            )
            return record

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=args.workers
        ) as executor:
            results = list(executor.map(one, todo))
    finally:
        pool.close()
    stopped = [r["scenario_id"] for r in results if r.get("status") == "budget_stop"]
    print(
        f"spent ${spend.spent_usd:.4f} of ${args.budget_usd:.2f}; "
        f"budget stops: {stopped}"
    )


def load_records(out_dir: Path) -> dict[str, dict]:
    records = {}
    for path in sorted((out_dir / "households").glob("*.json")):
        record = json.loads(path.read_text())
        records[record["scenario_id"]] = record
    return records


def arm2_predictions(records: Mapping[str, dict]) -> pd.DataFrame:
    rows = []
    for sid, record in records.items():
        for variable in record["variables"]:
            value = record["predictions"].get(variable)
            rows.append(
                {
                    "model": ARM2_LABEL,
                    "scenario_id": sid,
                    "variable": variable,
                    "prediction": value,
                    "explanation": record["explanations"].get(variable),
                    "error": None if value is not None else record["status"],
                }
            )
    return pd.DataFrame(rows)


def arm1_predictions(snapshot: Path = SNAPSHOT) -> pd.DataFrame:
    frame = pd.read_csv(snapshot / "predictions.csv.gz", low_memory=False)
    return frame[frame["model"] == ARM1_LABEL].copy()


def command_score(args) -> None:
    from policybench.analysis import analyze_no_tools
    from policybench.spec import output_group_id

    board = load_board()
    out = Path(args.out_dir)
    records = load_records(out)
    complete = sorted(
        sid for sid, r in records.items() if r.get("status") == "complete"
    )
    households = sorted(records) if args.all_records else complete
    if not households:
        raise SystemExit("no household records to score")
    scored = board["scored"][board["scored"].scenario_id.isin(households)]
    arm1 = arm1_predictions()
    arm1 = arm1[arm1.scenario_id.isin(households)]
    arm2 = arm2_predictions({sid: records[sid] for sid in households})
    scenarios = board["scenarios_frame"][
        board["scenarios_frame"].scenario_id.isin(households)
    ]
    analysis = analyze_no_tools(
        scored, pd.concat([arm1, arm2], ignore_index=True), scenarios=scenarios
    )
    summary = analysis["model_summary"]
    columns = [
        c
        for c in (
            "model",
            "weighted_exact",
            "mean_exact",
            "total_n",
            "parsed_n",
            "weighted_within_1pct",
            "bounded_score",
        )
        if c in summary.columns
    ]
    print(summary[columns].to_string(index=False))

    rows = scored[["scenario_id", "variable", "value"]].rename(
        columns={"value": "reference"}
    )
    a1 = arm1.set_index(["scenario_id", "variable"])["prediction"]
    a2 = arm2.set_index(["scenario_id", "variable"])["prediction"]
    rows["arm1"] = [a1.get((s, v)) for s, v in zip(rows.scenario_id, rows.variable)]
    rows["arm2"] = [a2.get((s, v)) for s, v in zip(rows.scenario_id, rows.variable)]
    rows["arm1_hit"] = [
        hit(v, p, r) for v, p, r in zip(rows.variable, rows.arm1, rows.reference)
    ]
    rows["arm2_hit"] = [
        hit(v, p, r) for v, p, r in zip(rows.variable, rows.arm2, rows.reference)
    ]
    rows["program"] = rows.variable.map(output_group_id)
    rows.to_csv(out / "scored_rows.csv", index=False)
    per_program = (
        rows.groupby("program")
        .agg(
            scored_outputs=("variable", "size"),
            arm1_hits=("arm1_hit", "sum"),
            arm2_hits=("arm2_hit", "sum"),
        )
        .reset_index()
    )
    per_program["arm1_rate"] = per_program.arm1_hits / per_program.scored_outputs
    per_program["arm2_rate"] = per_program.arm2_hits / per_program.scored_outputs
    per_program["change_pp"] = 100 * (per_program.arm2_rate - per_program.arm1_rate)
    per_program.to_csv(out / "per_program.csv", index=False)
    print(per_program.to_string(index=False))

    usage = usage_by_household(records, arm1, households)
    usage.to_csv(out / "usage_by_household.csv", index=False)
    usage_summary = summarize_usage(usage)
    print(json.dumps(usage_summary, indent=2))
    (out / "score.json").write_text(
        json.dumps(
            {
                "households": len(households),
                "incomplete_households": sorted(set(records) - set(complete)),
                "scored_outputs": int(len(scored)),
                "summary": summary[columns].to_dict(orient="records"),
                "unweighted_hits": {
                    "arm1": int(rows.arm1_hit.sum()),
                    "arm2": int(rows.arm2_hit.sum()),
                },
                "usage": usage_summary,
            },
            indent=2,
            default=float,
        )
    )


def usage_by_household(records, arm1: pd.DataFrame, households) -> pd.DataFrame:
    a1 = arm1.copy()
    for column in (
        "prompt_tokens",
        "completion_tokens",
        "reasoning_tokens",
        "total_cost_usd",
        "elapsed_seconds",
        "cached_prompt_tokens",
    ):
        a1[column] = pd.to_numeric(a1[column], errors="coerce").fillna(0.0)
    grouped = a1.groupby("scenario_id").agg(
        arm1_prompt_tokens=("prompt_tokens", "sum"),
        arm1_completion_tokens=("completion_tokens", "sum"),
        arm1_reasoning_tokens=("reasoning_tokens", "sum"),
        arm1_cost_usd=("total_cost_usd", "sum"),
        arm1_seconds=("elapsed_seconds", "sum"),
        arm1_calls=("call_id", "nunique"),
    )
    rows = []
    for sid in households:
        totals = records[sid]["totals"]
        rows.append(
            {
                "scenario_id": sid,
                "status": records[sid]["status"],
                "arm2_model_turns": totals["model_turns"],
                "arm2_tool_calls": totals["tool_calls"],
                "arm2_tool_errors": totals["tool_errors"],
                "arm2_cap_hit": records[sid].get("cap_hit"),
                "arm2_prompt_tokens": totals["prompt_tokens"],
                "arm2_cached_prompt_tokens": totals["cached_prompt_tokens"],
                "arm2_completion_tokens": totals["completion_tokens"],
                "arm2_reasoning_tokens": totals["reasoning_tokens"],
                "arm2_cost_usd": totals["cost_usd"],
                "arm2_model_seconds": totals["model_seconds"],
                "arm2_tool_seconds": totals["tool_seconds"],
                "arm2_wall_seconds": records[sid].get("wall_seconds"),
            }
        )
    frame = pd.DataFrame(rows).merge(
        grouped.reset_index(), on="scenario_id", how="left"
    )
    return frame


def summarize_usage(usage: pd.DataFrame) -> dict:
    def stats(column):
        series = pd.to_numeric(usage[column], errors="coerce")
        return {
            "total": float(series.sum()),
            "mean": float(series.mean()),
            "median": float(series.median()),
            "max": float(series.max()),
        }

    keys = [
        c
        for c in usage.columns
        if c.startswith(("arm1_", "arm2_")) and c != "arm2_cap_hit"
    ]
    out = {key: stats(key) for key in keys}
    out["arm2_cap_hit_households"] = int(
        usage["arm2_cap_hit"].fillna(False).astype(bool).sum()
    )
    return out


# ---------------------------------------------------------------------------
# Miss diagnosis.
# ---------------------------------------------------------------------------

MISS_CATEGORIES = (
    "wrong_input_mapping",
    "wrong_variable_or_period",
    "tool_error_or_cap",
    "answer_differs_from_tool",
    "no_answer",
)


def _successful_calls(record: dict) -> list[dict]:
    calls = []
    for turn in record.get("turns", []):
        for call in turn.get("calls", []):
            result = call.get("result")
            if (
                call.get("name") == TOOL_NAME
                and isinstance(result, dict)
                and "results" in result
            ):
                calls.append(call)
    return calls


def _person_names(arguments) -> list[str]:
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        situation = args["situation"]
        situation = json.loads(situation) if isinstance(situation, str) else situation
        return list(situation["people"])
    except (KeyError, TypeError, ValueError):
        return []


def tool_value_for_output(call: dict, scenario, output: str):
    """The value one successful call returned for a benchmark output, or None.

    The output's engine variable must be in the call's results at the 2026
    annual period. Person outputs read the model's person in the scenario's
    position (the prompt lists people in scenario order); group outputs take
    the board's aggregation over the returned units.
    """
    from policybench.ground_truth import (
        _aggregation_for_output,
        _pe_variable_for_output,
    )

    pe_variable = _pe_variable_for_output(output, "us")
    entry = call["result"]["results"].get(pe_variable)
    if not isinstance(entry, dict) or "values" not in entry:
        return None
    if str(entry.get("period")) != str(YEAR):
        return None
    values = entry["values"]
    aggregation = _aggregation_for_output(output, "us")
    if aggregation == "person":
        from policybench.ground_truth import _person_index_for_output

        index = _person_index_for_output(scenario, output)
        names = _person_names(call.get("arguments"))
        if index is None or index >= len(names) or names[index] not in values:
            return None
        value = values[names[index]]
    else:
        numbers = [
            float(v) if not isinstance(v, str) else math.nan for v in values.values()
        ]
        value = sum(numbers)
        if aggregation == "any_positive":
            value = float(value > 0)
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_miss(record: dict, scenario, output: str, submitted, reference) -> dict:
    """One of MISS_CATEGORIES, with the evidence behind it.

    Assumes the output missed. The last successful call that computed the
    output's engine variable for 2026 decides: if the submitted value differs
    from what the tool returned there, the answer departs from the tool; if it
    matches, the tool computed a different value from the model's situation
    than the reference situation gives, so the inputs were mapped differently
    (a reference issue is a reading of that mapping, decided on review).
    """
    from policybench.ground_truth import _pe_variable_for_output

    pe_variable = _pe_variable_for_output(output, "us")
    calls = _successful_calls(record)
    evidence = {"pe_variable": pe_variable, "successful_calls": len(calls)}
    if submitted is None or (isinstance(submitted, float) and math.isnan(submitted)):
        return {"category": "no_answer", **evidence}
    computed = [
        c for c in calls if tool_value_for_output(c, scenario, output) is not None
    ]
    if not computed:
        any_period = [
            c
            for c in calls
            if pe_variable in c["result"]["results"]
            and isinstance(c["result"]["results"][pe_variable], dict)
            and "values" in c["result"]["results"][pe_variable]
        ]
        if not calls:
            return {
                "category": "tool_error_or_cap",
                **evidence,
                "cap_hit": record.get("cap_hit"),
            }
        if any_period:
            return {
                "category": "wrong_variable_or_period",
                "detail": "variable computed only for another period",
                **evidence,
            }
        return {
            "category": "wrong_variable_or_period",
            "detail": "output's engine variable never computed",
            **evidence,
        }
    last = computed[-1]
    tool_value = tool_value_for_output(last, scenario, output)
    evidence["tool_value"] = tool_value
    evidence["call_arguments"] = last.get("arguments")
    if not hit(output, submitted, tool_value):
        return {"category": "answer_differs_from_tool", **evidence}
    return {"category": "wrong_input_mapping", **evidence}


def situation_diff(
    model_situation: dict, reference_situation: dict, scenario
) -> list[dict]:
    """Inputs set differently in the model's situation and the reference's.

    People are matched by position (the prompt lists them in scenario order);
    each group's single unit is matched to the reference's. An input absent on
    one side compares as the other side's value against the engine default,
    which the caller supplies through ``defaults``.
    """
    diffs = []
    model_people = list(model_situation.get("people", {}).items())
    reference_people = list(reference_situation["people"].items())
    for index, (ref_name, ref_inputs) in enumerate(reference_people):
        model_inputs = model_people[index][1] if index < len(model_people) else {}
        model_name = model_people[index][0] if index < len(model_people) else None
        for name in sorted(set(ref_inputs) | set(model_inputs)):
            ref = ref_inputs.get(name, {})
            mod = model_inputs.get(name, {})
            if _period_value(ref) != _period_value(mod):
                diffs.append(
                    {
                        "entity": "person",
                        "reference_unit": ref_name,
                        "model_unit": model_name,
                        "variable": name,
                        "reference": ref,
                        "model": mod,
                    }
                )
    if len(model_people) != len(reference_people):
        diffs.append(
            {
                "entity": "person",
                "variable": "<people>",
                "reference": len(reference_people),
                "model": len(model_people),
            }
        )
    for group in GROUPS:
        ref_units = list(reference_situation.get(group, {}).values())
        model_units = list(model_situation.get(group, {}).values())
        ref_unit = ref_units[0] if ref_units else {}
        model_unit = model_units[0] if model_units else {}
        # A group the model leaves out is one unit holding everyone.
        if (len(model_units) or 1) != len(ref_units):
            diffs.append(
                {
                    "entity": group,
                    "variable": "<units>",
                    "reference": len(ref_units),
                    "model": len(model_units),
                }
            )
        for name in sorted((set(ref_unit) | set(model_unit)) - {"members"}):
            ref = ref_unit.get(name, {})
            mod = model_unit.get(name, {})
            if _period_value(ref) != _period_value(mod):
                diffs.append(
                    {"entity": group, "variable": name, "reference": ref, "model": mod}
                )
    return diffs


def _period_value(value) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((str(k), _canon(v)) for k, v in value.items()))
    return ((str(YEAR), _canon(value)),) if value != {} else ()


def _canon(value):
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return round(float(value), 6)
    return value


def command_diagnose(args) -> None:
    board = load_board()
    out = Path(args.out_dir)
    records = load_records(out)
    rows_path = out / "scored_rows.csv"
    if not rows_path.exists():
        raise SystemExit("run score first")
    rows = pd.read_csv(rows_path)
    misses = rows[~rows.arm2_hit.astype(bool)]
    registry = None
    defaults = {}
    if not args.no_engine_defaults:
        system = build_tool_system(reform=True)
        registry = build_registry(system)
        defaults = {
            name: system.variables[name].default_value for name in system.variables
        }
    out_rows = []
    for row in misses.itertuples():
        record = records[row.scenario_id]
        scenario = board["scenarios"][row.scenario_id]
        submitted = None if pd.isna(row.arm2) else float(row.arm2)
        verdict = classify_miss(
            record, scenario, row.variable, submitted, row.reference
        )
        diff = []
        arguments = verdict.get("call_arguments")
        if arguments is not None and registry is not None:
            request, _ = normalize_request(arguments, registry)
            if request is not None:
                diff = situation_diff(
                    request["situation"], scenario.to_pe_household(), scenario
                )
                diff = [d for d in diff if not _is_default_only(d, defaults)]
        out_rows.append(
            {
                "scenario_id": row.scenario_id,
                "state": scenario.state,
                "variable": row.variable,
                "program": row.program,
                "reference": row.reference,
                "arm1": row.arm1,
                "arm1_hit": row.arm1_hit,
                "arm2": submitted,
                "category": verdict["category"],
                "detail": verdict.get("detail"),
                "tool_value": verdict.get("tool_value"),
                "status": record.get("status"),
                "cap_hit": record.get("cap_hit"),
                "input_diff": json.dumps(diff, default=str),
            }
        )
    frame = pd.DataFrame(out_rows)
    frame.to_csv(out / "misses.csv", index=False)
    print(frame.groupby("category").size().to_string())
    print(frame.groupby(["program", "category"]).size().to_string())


def _is_default_only(diff: dict, defaults: Mapping[str, Any]) -> bool:
    """A difference that is only an input left at the engine default on one side."""
    name = diff.get("variable")
    if name not in defaults:
        return False
    default = defaults[name]
    if hasattr(default, "name"):
        default = default.name
    sides = []
    for side in (diff.get("reference"), diff.get("model")):
        if side in ({}, None):
            sides.append(None)
        elif isinstance(side, dict):
            sides.append(tuple(sorted(_canon(v) for v in side.values())))
        else:
            sides.append((_canon(side),))
    canon_default = (_canon(default),)
    if sides[0] is None:
        return sides[1] == canon_default
    if sides[1] is None:
        return sides[0] == canon_default
    return False


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("oracle", "run", "score", "diagnose"):
        p = sub.add_parser(name)
        p.add_argument("--out-dir", required=True)
        if name == "run":
            p.add_argument("--scenarios", nargs="*")
            p.add_argument("--limit", type=int)
            p.add_argument("--workers", type=int, default=4)
            p.add_argument("--budget-usd", type=float, default=DEFAULT_BUDGET_USD)
            p.add_argument(
                "--reserve-usd",
                type=float,
                default=1.0,
                help="stop starting households when this much budget remains",
            )
        if name == "score":
            p.add_argument("--all-records", action="store_true")
        if name == "diagnose":
            p.add_argument("--no-engine-defaults", action="store_true")
    args = parser.parse_args(argv)
    {
        "oracle": command_oracle,
        "run": command_run,
        "score": command_score,
        "diagnose": command_diagnose,
    }[args.command](args)


if __name__ == "__main__":
    main()
