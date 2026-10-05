"""Sweep a frozen run's references against the engine's estimates of unlisted inputs.

A US reference is a policyengine-us calculation on the facts the prompt lists. Where
a rule needs an input the prompt never lists, the engine supplies one: a default, a
formula estimate, or an assumed county. The prompt tells models to "treat any
unlisted numeric input as 0 and any other unlisted household fact, boolean, or
status input as false" (``policybench.prompts.TASK_PREFACE``). An output whose
reference moves when such an estimate is replaced by that literal reading, or by a
documented alternative reading, rests on an input the prompt never states. That is
the test of the ``reference_depends_on_unlisted_input`` exclusion rule
(``reference_exclusions.json``).

The audits found each estimate on its own (r14's weekly hours on 2026-09-22, the
SALT withholding estimate and four others on 2026-10-05). ``ESTIMATES`` registers
them. ``run`` recomputes every output of a frozen run on the reference system that
built its references (a fix module, as ``reference_audit/2026-09-28/scripts/
sweep.py`` defines one), first as published and then under each registered reading,
and reports every output that moves by more than the $1 exact-match tolerance or
flips a flag. Each move is marked scored or already excluded.

Every simulation runs on one tax-benefit system per worker process: building the
2.15.17 system takes about 40 seconds and a household simulation about half a
second.

The swept system adds ``policybench.output_scope.reform`` to the fix module, so its
state income tax and state refundable credit outputs exclude local taxes and
credits as the benchmark defines them. The run checks that the adapter changes no
published reference: each local entry it removes must be zero for every household.

A county reading that switches on one of the engine's locality flags (in_nyc,
in_san_francisco, ...) makes an unlisted household fact true, which the prompt's
rule makes false. Its moves are reported with status ``prompt_rules_out`` and do
not fail ``--strict``.

Usage (``docs/runbook.md``, "Reference-build gates"):

  uv run policybench unlisted-input-sweep \\
    --fix reference_audit/2026-09-28/fixes/latest_final.py \\
    --fix-support reference_audit/2026-09-22/fixes/r19_irs_sales_tax_2025.json \\
    --out-dir results/local/unlisted_input_sweep

``--run-dir`` defaults to the frozen run,
``paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace``.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import multiprocessing
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any

from policybench import output_scope

if TYPE_CHECKING:
    import pandas as pd

TOLERANCE = 1.0
BASELINE_TOLERANCE = 1e-3
NOOP_TOLERANCE = 1e-9
FIXED_POINT_TOLERANCE = 0.005
MAX_FIXED_POINT_ITERATIONS = 25
LITERAL = "literal"
ALTERNATIVE = "alternative"
COMBINED_ESTIMATE = "all_literal_readings"
COMBINED_READING = "all_literal"

# Inputs the references were built under another name. The frozen manifest stores
# partnership_se_income; policyengine-us 2.15.17 calls it
# partnership_self_employment_net_earnings. The 2026-09-28 reference builder
# (reference_audit/2026-09-28/scripts/build_references_latest.py) builds households
# with sweep.py's build_situation, which renames it.
REFERENCE_INPUT_RENAMES = {
    "partnership_se_income": "partnership_self_employment_net_earnings"
}

# Local income taxes whose only route to the federal SALT deduction is the
# withholding estimate. In policyengine-us 2.15.17 the income-tax line of SALT is
# state_withheld_income_tax plus local_income_tax. md_withheld_income_tax carries an
# AGI-based estimate of Maryland county tax (the county's rate times AGI less the
# largest single standard deduction); local_income_tax adds no Maryland entry, and
# the county liability variable feeds no SALT variable. Replacing the withholding
# estimate with what the household paid therefore has to add the county liability
# back. NYC tax already reaches SALT through local_income_tax (as nyc_income_tax,
# net of NYC refundable credits), so it is not added.
SALT_VIA_WITHHOLDING_ONLY = ("md_local_income_tax_before_refundable_credits",)

DEFAULT_RUN_DIR = Path(
    "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)


# ---------------------------------------------------------------------------
# Overrides and readings
# ---------------------------------------------------------------------------

_GROUPS = {
    "tax_unit": "tax_units",
    "spm_unit": "spm_units",
    "household": "households",
}


def _canonical(value: Any) -> Any:
    if isinstance(value, bool) or isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return float(value)
    return value


def _same_value(a: Any, b: Any) -> bool:
    """Equal and of the same kind: 0.0 and False are different settings."""
    a, b = _canonical(a), _canonical(b)
    return type(a) is type(b) and a == b


@dataclass(frozen=True)
class Override:
    """Input values a reading sets on top of the household as built for the reference.

    ``people`` maps a person's name in the situation to ``{variable: value}``; the
    group fields map a variable to its value on the household's one unit. Values are
    for the scenario year.
    """

    people: dict[str, dict[str, Any]] = field(default_factory=dict)
    tax_unit: dict[str, Any] = field(default_factory=dict)
    spm_unit: dict[str, Any] = field(default_factory=dict)
    household: dict[str, Any] = field(default_factory=dict)

    def items(self) -> Iterable[tuple[str, str | None, str, Any]]:
        """(entity, person or None, variable, value) for every value set."""
        for name in sorted(self.people):
            for variable in sorted(self.people[name]):
                yield "person", name, variable, self.people[name][variable]
        for entity in _GROUPS:
            values = getattr(self, entity)
            for variable in sorted(values):
                yield entity, None, variable, values[variable]

    def is_empty(self) -> bool:
        return not any(True for _ in self.items())

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.people:
            out["people"] = {
                name: {k: _canonical(v) for k, v in sorted(values.items())}
                for name, values in sorted(self.people.items())
            }
        for entity in _GROUPS:
            values = getattr(self, entity)
            if values:
                out[entity] = {k: _canonical(v) for k, v in sorted(values.items())}
        return out

    def key(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True)

    def describe(self) -> str:
        parts = []
        for entity, person, variable, value in self.items():
            where = person if person is not None else entity
            shown = f"{value:.2f}" if isinstance(value, float) else str(value)
            parts.append(f"{where}.{variable}={shown}")
        return "; ".join(parts)

    def merged(self, other: Override) -> Override:
        """Both overrides at once; setting one variable to two values is an error."""
        people = {name: dict(values) for name, values in self.people.items()}
        for name, values in other.people.items():
            target = people.setdefault(name, {})
            for variable, value in values.items():
                if variable in target and not _same_value(target[variable], value):
                    raise ValueError(f"conflicting values for {name}.{variable}")
                target[variable] = value
        groups = {}
        for entity in _GROUPS:
            mine = dict(getattr(self, entity))
            for variable, value in getattr(other, entity).items():
                if variable in mine and not _same_value(mine[variable], value):
                    raise ValueError(f"conflicting values for {entity}.{variable}")
                mine[variable] = value
            groups[entity] = mine
        return Override(people=people, **groups)

    def apply(self, situation: dict, period: str) -> dict:
        """A copy of ``situation`` with these values set for ``period``."""
        out = copy.deepcopy(situation)
        for name, values in self.people.items():
            if name not in out["people"]:
                raise KeyError(f"no person {name!r} in the situation")
            for variable, value in values.items():
                out["people"][name][variable] = {period: value}
        for entity, plural in _GROUPS.items():
            values = getattr(self, entity)
            if not values:
                continue
            units = out[plural]
            if len(units) != 1:
                raise ValueError(f"expected one {entity}, found {len(units)}")
            unit = next(iter(units.values()))
            for variable, value in values.items():
                unit[variable] = {period: value}
        return out


@dataclass
class ReadingPlan:
    """One way to fill an unlisted input for one household."""

    override: Override
    variant: str = ""
    simulation: Any = None
    trace: list[dict[str, float]] = field(default_factory=list)
    converged: bool = True
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Reading:
    """A reading of an unlisted input.

    ``kind`` is ``literal`` for the prompt's own rule (unlisted numbers 0, unlisted
    facts false) and ``alternative`` for another reading the stated facts support,
    used where the engine already applies the literal one. ``plan`` returns the
    household's overrides (several for a reading with variants, none where the
    reading cannot apply).
    """

    id: str
    kind: str
    description: str
    plan: Callable[[HouseholdContext], list[ReadingPlan]]


@dataclass(frozen=True)
class UnlistedEstimate:
    """An input the engine fills in that no PolicyBench prompt lists."""

    id: str
    engine_inputs: tuple[str, ...]
    entity: str
    engine_behavior: str
    why_unlisted: str
    found_in: str
    readings: tuple[Reading, ...]

    def reading(self, reading_id: str) -> Reading:
        for reading in self.readings:
            if reading.id == reading_id:
                return reading
        raise KeyError(f"{self.id} has no reading {reading_id!r}")

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "engine_inputs": list(self.engine_inputs),
            "entity": self.entity,
            "engine_behavior": self.engine_behavior,
            "why_unlisted": self.why_unlisted,
            "found_in": self.found_in,
            "readings": [
                {"id": r.id, "kind": r.kind, "description": r.description}
                for r in self.readings
            ],
        }


# ---------------------------------------------------------------------------
# Household context
# ---------------------------------------------------------------------------


def discover_locality_flags() -> tuple[str, ...]:
    """Household flags that put a household in a locality with its own rules.

    policyengine-us defines them as ``in_*`` variables under ``variables/gov/local``
    (in_san_francisco, in_denver, ...) and ``variables/household/demographic/
    geographic`` (in_nyc), each a formula of county. They are read from the installed
    source tree, so no system is built. The prompt states no locality, and its rule
    makes every unlisted household fact false.
    """
    spec = importlib.util.find_spec("policyengine_us")
    if spec is None or not spec.submodule_search_locations:
        return ()
    root = Path(next(iter(spec.submodule_search_locations))) / "variables"
    names = set()
    for pattern in ("gov/local/**/in_*.py", "household/demographic/geographic/in_*.py"):
        names.update(path.stem for path in root.glob(pattern))
    return tuple(sorted(names))


class Engine:
    """The swept tax-benefit system and how to simulate a situation on it."""

    def __init__(
        self,
        system: Any,
        simulation_class: Any,
        aggregate_local_components: Sequence[str] = (),
        removed_local_components: Sequence[str] = (),
        remaining_local_components: Sequence[str] | None = None,
        county_states: frozenset[str] | None = None,
        locality_flags: Sequence[str] | None = None,
    ):
        self.system = system
        self.simulation_class = simulation_class
        # Local taxes still in the swept state income tax aggregate.
        self.aggregate_local_components = tuple(aggregate_local_components)
        # Local entries the output-scope adapter removed from the state lists.
        self.removed_local_components = tuple(removed_local_components)
        # Local entries still in any state list (taxes and credits).
        self.remaining_local_components = tuple(
            aggregate_local_components
            if remaining_local_components is None
            else remaining_local_components
        )
        self.county_states = county_states
        if locality_flags is None:
            locality_flags = [
                name for name in discover_locality_flags() if self.has_variable(name)
            ]
        self.locality_flags = tuple(locality_flags)

    @property
    def remaining_local_credits(self) -> tuple[str, ...]:
        """Local credits the swept system still counts in state refundable credits."""
        return tuple(
            name
            for name in self.remaining_local_components
            if name not in output_scope.LOCAL_INCOME_TAX_COMPONENTS
            and name not in self.aggregate_local_components
        )

    def simulate(self, situation: dict) -> Any:
        return self.simulation_class(
            tax_benefit_system=self.system, situation=situation
        )

    def has_variable(self, name: str) -> bool:
        return name in self.system.variables

    def parameter(self, path: str, instant: str) -> Any:
        node = self.system.parameters
        for part in path.split("."):
            node = getattr(node, part)
        return node(instant)

    def counties(self, state: str) -> list[str]:
        """Every county the engine knows in ``state``, in the engine's order.

        policyengine-us gives a household with no county its state's first county in
        this order (``first_county_in_state``: the alphabetically first value).
        """
        enum = self.system.variables["county"].possible_values
        members = [
            member
            for member in enum
            if member.name != "UNKNOWN" and str(member.value).endswith(f", {state}")
        ]
        return [member.name for member in sorted(members, key=lambda m: str(m.value))]


@dataclass
class HouseholdContext:
    scenario: Any
    situation: dict
    variables: list[str]
    engine: Engine
    baseline: Any = None
    _cache: dict[str, Any] = field(default_factory=dict)

    @property
    def year(self) -> int:
        return int(self.scenario.year)

    @property
    def period(self) -> str:
        return str(self.scenario.year)

    @property
    def person_names(self) -> list[str]:
        return list(self.situation["people"])

    def total(self, simulation: Any, variable: str) -> float:
        return float(simulation.calculate(variable, self.year).sum())

    def by_person(self, simulation: Any, variable: str) -> dict[str, float]:
        values = simulation.calculate(variable, self.year)
        return {
            name: float(values[index]) for index, name in enumerate(self.person_names)
        }

    def _baseline_value(self, entity: str, person: str | None, variable: str) -> Any:
        values = self.baseline.calculate(variable, self.year)
        if hasattr(values, "decode_to_str"):
            values = values.decode_to_str()
        index = self.person_names.index(person) if entity == "person" else 0
        value = values[index]
        return value if isinstance(value, str) else float(value)

    def is_noop(self, override: Override) -> bool:
        """Whether every value ``override`` sets equals the reference's own value.

        Setting an input to the value the engine computes for it leaves every
        output unchanged, so such a reading needs no simulation.
        """
        for entity, person, variable, value in override.items():
            current = self._baseline_value(entity, person, variable)
            if isinstance(current, str) or isinstance(value, str):
                if str(current) != str(value):
                    return False
            elif abs(float(current) - float(value)) > NOOP_TOLERANCE:
                return False
        return True

    def simulate(self, override: Override) -> Any:
        if override.is_empty() or self.is_noop(override):
            return self.baseline
        key = override.key()
        if key not in self._cache:
            self._cache[key] = self.engine.simulate(
                override.apply(self.situation, self.period)
            )
        return self._cache[key]

    def outputs(self, simulation: Any) -> dict[str, float]:
        from policybench.ground_truth import (
            _extract_person_value,
            _pe_variable_for_output,
        )

        values = {}
        for variable in self.variables:
            pe_variable = _pe_variable_for_output(variable, self.scenario.country)
            values[variable] = float(
                _extract_person_value(
                    simulation.calculate(pe_variable, self.year),
                    self.scenario,
                    variable,
                )
            )
        return values


# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------


def _zero_on_tax_unit(variable: str) -> Callable[[HouseholdContext], list[ReadingPlan]]:
    def plan(ctx: HouseholdContext) -> list[ReadingPlan]:
        return [
            ReadingPlan(
                Override(tax_unit={variable: 0.0}),
                detail={"engine_value": ctx.total(ctx.baseline, variable)},
            )
        ]

    return plan


def _zero_on_people(variable: str) -> Callable[[HouseholdContext], list[ReadingPlan]]:
    def plan(ctx: HouseholdContext) -> list[ReadingPlan]:
        values = ctx.by_person(ctx.baseline, variable)
        people = {name: {variable: 0.0} for name, value in values.items() if value}
        if not people:
            return []
        return [ReadingPlan(Override(people=people), detail={"engine_value": values})]

    return plan


def salt_income_tax_paid(
    ctx: HouseholdContext, simulation: Any, *, net: bool = False
) -> float:
    """The state income tax a household pays during the year if it pays its liability.

    The engine's state income tax before refundable credits, less any local tax the
    swept system's state aggregate still adds, plus the local tax whose only route
    to SALT is the withholding estimate (Maryland county tax). ``net`` also
    subtracts state refundable credits, less any local credit the swept system still
    counts in them. Floored at zero.
    """
    amount = ctx.total(simulation, output_scope.STATE_AGGREGATE)
    for name in ctx.engine.aggregate_local_components:
        amount -= ctx.total(simulation, name)
    for name in SALT_VIA_WITHHOLDING_ONLY:
        if ctx.engine.has_variable(name):
            amount += ctx.total(simulation, name)
    if net:
        amount -= ctx.total(simulation, "state_refundable_credits")
        for name in ctx.engine.remaining_local_credits:
            amount += ctx.total(simulation, name)
    return max(0.0, amount)


def _withholding_fixed_point(
    net: bool,
) -> Callable[[HouseholdContext], list[ReadingPlan]]:
    def plan(ctx: HouseholdContext) -> list[ReadingPlan]:
        estimate = ctx.total(ctx.baseline, "state_withheld_income_tax")
        withheld = salt_income_tax_paid(ctx, ctx.baseline, net=net)
        trace = []
        converged = False
        override = Override(tax_unit={"state_withheld_income_tax": withheld})
        simulation = ctx.baseline
        # A state's tax can read federal tax or the federal SALT deduction, so the
        # amount paid is iterated until it reproduces itself.
        for _ in range(MAX_FIXED_POINT_ITERATIONS):
            override = Override(tax_unit={"state_withheld_income_tax": withheld})
            simulation = ctx.simulate(override)
            implied = salt_income_tax_paid(ctx, simulation, net=net)
            trace.append({"withheld": withheld, "implied": implied})
            if abs(implied - withheld) < FIXED_POINT_TOLERANCE:
                converged = True
                break
            withheld = implied
        return [
            ReadingPlan(
                override,
                simulation=simulation,
                trace=trace,
                converged=converged,
                detail={"engine_value": estimate, "paid": withheld},
            )
        ]

    return plan


def _stated_hours_alternative(
    hours: float,
) -> Callable[[HouseholdContext], list[ReadingPlan]]:
    target = "weekly_hours_worked_before_lsr"

    def plan(ctx: HouseholdContext) -> list[ReadingPlan]:
        # Stated usual hours reach the target through PE_INPUT_ALIASES; a person
        # without them keeps the engine default.
        people = {
            name: {target: hours}
            for name, person in ctx.situation["people"].items()
            if target not in person
        }
        if not people:
            return []
        return [ReadingPlan(Override(people=people))]

    return plan


def _people_flag_alternative(
    variable: str,
    value: Any,
    when: Callable[[HouseholdContext], dict[str, bool]],
) -> Callable[[HouseholdContext], list[ReadingPlan]]:
    def plan(ctx: HouseholdContext) -> list[ReadingPlan]:
        people = {name: {variable: value} for name, hit in when(ctx).items() if hit}
        if not people:
            return []
        return [ReadingPlan(Override(people=people))]

    return plan


def _receives_ssdi(ctx: HouseholdContext) -> dict[str, bool]:
    values = ctx.by_person(ctx.baseline, "social_security_disability")
    return {name: value > 0 for name, value in values.items()}


def _is_disabled(ctx: HouseholdContext) -> dict[str, bool]:
    values = ctx.by_person(ctx.baseline, "is_disabled")
    return {name: bool(value) for name, value in values.items()}


def _pre_tcja_mortgage(ctx: HouseholdContext) -> list[ReadingPlan]:
    # deductible_mortgage_interest_tax_unit is the only variable that reads the
    # origination years; it is interest times a deductible share, min(1, capped
    # balance / balance), which raising a cap cannot lower. Where the share is
    # already 1 (deductible equals interest), every output is unchanged, so no
    # simulation is needed. Testing the share, not non-deductible interest, keeps
    # this exact for negative interest too.
    interest = ctx.total(ctx.baseline, "home_mortgage_interest_tax_unit")
    deductible = ctx.total(ctx.baseline, "deductible_mortgage_interest_tax_unit")
    capped = interest - deductible
    if abs(capped) <= NOOP_TOLERANCE:
        return []
    year = int(
        ctx.engine.parameter(
            "gov.irs.deductions.itemized.interest.mortgage.pre_tcja_origination_year",
            f"{ctx.period}-01-01",
        )
    )
    values = {}
    for prefix in ("first", "second"):
        if ctx.total(ctx.baseline, f"{prefix}_home_mortgage_balance") > 0:
            values[f"{prefix}_home_mortgage_origination_year"] = year
    if not values:
        return []
    return [
        ReadingPlan(
            Override(tax_unit=values),
            detail={"capped_interest": capped, "origination_year": year},
        )
    ]


def _each_county(ctx: HouseholdContext) -> list[ReadingPlan]:
    states = ctx.engine.county_states
    if states is not None and ctx.scenario.state not in states:
        return []
    return [
        ReadingPlan(Override(household={"county": county}), variant=county)
        for county in ctx.engine.counties(ctx.scenario.state)
    ]


ESTIMATES: tuple[UnlistedEstimate, ...] = (
    UnlistedEstimate(
        id="state_withheld_income_tax",
        engine_inputs=("state_withheld_income_tax",),
        entity="tax_unit",
        engine_behavior=(
            "The income-tax line of the federal SALT deduction is "
            "state_withheld_income_tax plus local_income_tax, and it counts when it "
            "exceeds general sales tax. state_withheld_income_tax adds per-state "
            "*_withheld_income_tax formulas on each person's federal AGI "
            "(parameters/gov/states/household/state_withheld_income_tax.yaml); "
            "Maryland's includes a county estimate. CO and MO formulas read it, and "
            "HI, VA, SC, NM, ID, UT and AZ formulas read SALT."
        ),
        why_unlisted=(
            "No prompt states state income tax withheld or paid during the year "
            "(26 U.S.C. 164(a)(3), (b)(5))."
        ),
        found_in="reference_audit 2026-10-05 (PR #191)",
        readings=(
            Reading(
                id="zero",
                kind=LITERAL,
                description=(
                    "No state income tax was withheld or paid (unlisted numeric "
                    "input = 0); SALT takes local income tax or general sales tax."
                ),
                plan=_zero_on_tax_unit("state_withheld_income_tax"),
            ),
            Reading(
                id="liability",
                kind=ALTERNATIVE,
                description=(
                    "The household pays its own state income tax before refundable "
                    "credits during the year, with its Maryland county liability in "
                    "place of the county estimate, iterated to a fixed point."
                ),
                plan=_withholding_fixed_point(net=False),
            ),
            Reading(
                id="net",
                kind=ALTERNATIVE,
                description=(
                    "As liability, net of state refundable credits and floored at 0."
                ),
                plan=_withholding_fixed_point(net=True),
            ),
        ),
    ),
    UnlistedEstimate(
        id="local_sales_tax",
        engine_inputs=("local_sales_tax",),
        entity="tax_unit",
        engine_behavior=(
            "local_sales_tax is 0.2 times state_sales_tax (the optional state sales "
            "tax table amount; for 2026 the reference system holds the 2025 IRS "
            "table) outside CT, DC, IN, KY, MA, MD, ME, MI, NJ and RI, an "
            "approximation of the locality's tax "
            "(variables/gov/local/tax/sales/local_sales_tax.py). Federal SALT and "
            "Hawaii's SALT deduction read it."
        ),
        why_unlisted="No prompt states a locality or a local sales tax rate.",
        found_in="reference_audit 2026-10-05 (variants.py no_local_sales)",
        readings=(
            Reading(
                id="zero",
                kind=LITERAL,
                description="No local general sales tax (unlisted numeric input = 0).",
                plan=_zero_on_tax_unit("local_sales_tax"),
            ),
        ),
    ),
    UnlistedEstimate(
        id="medicare_part_b_premium",
        engine_inputs=("medicare_part_b_premium", "takes_up_medicare_if_eligible"),
        entity="person",
        engine_behavior=(
            "takes_up_medicare_if_eligible defaults to true, so every "
            "Medicare-eligible person is medicare_enrolled and is charged a modeled "
            "medicare_part_b_premium, net of Medicare Savings Program coverage. "
            "medical_expense_health_insurance_premiums adds it unless a direct "
            "health_insurance_premiums input is set, which no frozen household does."
        ),
        why_unlisted=(
            "No prompt states Medicare enrollment or a Part B premium, and the "
            "prompt says not to infer unlisted expenses or health coverage."
        ),
        found_in="reference_audit 2026-10-05 (variants.py no_part_b)",
        readings=(
            Reading(
                id="zero",
                kind=LITERAL,
                description="No Part B premium is paid (unlisted expense = 0).",
                plan=_zero_on_people("medicare_part_b_premium"),
            ),
        ),
    ),
    UnlistedEstimate(
        id="county",
        engine_inputs=("county",),
        entity="household",
        engine_behavior=(
            "A household with no county takes its state's alphabetically first "
            "county (first_county_in_state): Allegany County for Maryland, whose "
            "county rate then sets the county withholding estimate and liability. "
            "County also sets locality flags (in_nyc, in_san_francisco and others) "
            "and county-level program rules."
        ),
        why_unlisted="Prompts state the state, never the county.",
        found_in=(
            "reference_audit 2026-09-28 (latest_md_local_output_scope) and 2026-10-05"
        ),
        readings=(
            Reading(
                id="each_county",
                kind=ALTERNATIVE,
                description=(
                    "Each other county of the household's state. A county that "
                    "switches on a locality flag (living in NYC or San Francisco) "
                    "makes an unlisted fact true, which the prompt's rule makes "
                    "false; its moves are marked prompt_rules_out."
                ),
                plan=_each_county,
            ),
        ),
    ),
    UnlistedEstimate(
        id="weekly_hours_worked_before_lsr",
        engine_inputs=("weekly_hours_worked_before_lsr",),
        entity="person",
        engine_behavior=(
            "SNAP's work rules and the TANF rules of HI, MA, MT, DC and OK read "
            "weekly_hours_worked_before_lsr (some through weekly_hours_worked). "
            "Stated usual hours reach it through PE_INPUT_ALIASES; otherwise the "
            "2.15.17 default is 0 (the literal reading; it was 40 before upstream "
            "#9261)."
        ),
        why_unlisted="Most prompts list no hours worked.",
        found_in="reference_audit 2026-09-22 root cause r14 (weekly hours)",
        readings=(
            Reading(
                id="forty_hours",
                kind=ALTERNATIVE,
                description=(
                    "A person with no stated hours works 40 hours a week (the "
                    "1.755.4 default and the 22c board's reading)."
                ),
                plan=_stated_hours_alternative(40.0),
            ),
        ),
    ),
    UnlistedEstimate(
        id="mortgage_origination_year",
        engine_inputs=(
            "first_home_mortgage_origination_year",
            "second_home_mortgage_origination_year",
        ),
        entity="tax_unit",
        engine_behavior=(
            "An origination year of 0 (the default) takes the post-TCJA "
            "acquisition-debt cap ($750,000; $375,000 married filing separately) "
            "for the mortgage interest deduction."
        ),
        why_unlisted=(
            "Prompts list mortgage balances and interest, never when the mortgage "
            "was taken out (26 U.S.C. 163(h)(3)(F))."
        ),
        found_in="reference_audit 2026-10-05 follow-up",
        readings=(
            Reading(
                id="pre_tcja",
                kind=ALTERNATIVE,
                description=(
                    "The mortgage originated in or before the engine's pre-TCJA "
                    "origination year (2017), so the $1,000,000 cap applies."
                ),
                plan=_pre_tcja_mortgage,
            ),
        ),
    ),
    UnlistedEstimate(
        id="months_receiving_social_security_disability",
        engine_inputs=("months_receiving_social_security_disability",),
        entity="person",
        engine_behavior=(
            "The input defaults to 0, so Medicare's under-65 route (24 months of "
            "SSDI entitlement) is closed (the literal reading)."
        ),
        why_unlisted="Prompts list SSDI income, never how long it has been received.",
        found_in=(
            "reference_exclusions.json (head_medicare_eligible records, 2026-09-05)"
        ),
        readings=(
            Reading(
                id="twenty_four_months",
                kind=ALTERNATIVE,
                description=(
                    "A person with listed SSDI income has received it for 24 months."
                ),
                plan=_people_flag_alternative(
                    "months_receiving_social_security_disability", 24, _receives_ssdi
                ),
            ),
        ),
    ),
    UnlistedEstimate(
        id="meets_ssi_disability_criteria",
        engine_inputs=("meets_ssi_disability_criteria",),
        entity="person",
        engine_behavior=(
            "The input defaults to false (the literal reading), so a person listed "
            "as disabled does not meet SSI's disability criterion."
        ),
        why_unlisted=(
            "Prompts say a person is disabled, never whether the disability meets "
            "the Social Security definition."
        ),
        found_in="reference_exclusions.json (snap and ssi records, 2026-09-05)",
        readings=(
            Reading(
                id="disabled_meets_criteria",
                kind=ALTERNATIVE,
                description="A person listed as disabled meets SSI's criterion.",
                plan=_people_flag_alternative(
                    "meets_ssi_disability_criteria", True, _is_disabled
                ),
            ),
        ),
    ),
)

ESTIMATES_BY_ID = {estimate.id: estimate for estimate in ESTIMATES}


def select_estimates(ids: Sequence[str] | None) -> tuple[UnlistedEstimate, ...]:
    if not ids:
        return ESTIMATES
    unknown = [i for i in ids if i not in ESTIMATES_BY_ID]
    if unknown:
        raise SystemExit(
            f"Unknown estimate(s): {', '.join(unknown)}. "
            f"Registered: {', '.join(ESTIMATES_BY_ID)}"
        )
    return tuple(ESTIMATES_BY_ID[i] for i in ids)


def combined_literal_plan(
    ctx: HouseholdContext, estimates: Sequence[UnlistedEstimate]
) -> list[ReadingPlan]:
    """Every literal reading at once: the household exactly as the prompt lists it.

    Some estimates only matter together; the federal SALT deduction falls back to
    the local sales tax estimate only once the withholding estimate is gone.
    """
    override = Override()
    parts = []
    for estimate in estimates:
        for reading in estimate.readings:
            if reading.kind != LITERAL:
                continue
            plans = reading.plan(ctx)
            if len(plans) > 1 or any(p.variant or p.simulation for p in plans):
                raise ValueError(
                    f"literal reading {estimate.id}/{reading.id} must be one override"
                )
            for plan in plans:
                if ctx.is_noop(plan.override):
                    continue
                override = override.merged(plan.override)
                parts.append(f"{estimate.id}/{reading.id}")
    if len(parts) < 2:
        return []
    return [ReadingPlan(override, detail={"parts": parts})]


# ---------------------------------------------------------------------------
# One household
# ---------------------------------------------------------------------------


def build_reference_situation(scenario, engine: Engine, patch=None) -> dict:
    """The situation the reference builder simulates for ``scenario``."""
    situation = scenario.to_pe_household()
    for person in situation["people"].values():
        for old, new in REFERENCE_INPUT_RENAMES.items():
            if (
                old in person
                and not engine.has_variable(old)
                and engine.has_variable(new)
            ):
                person[new] = person.pop(old)
    if patch is not None:
        situation = patch(copy.deepcopy(situation), scenario)
    return situation


@dataclass(frozen=True)
class HouseholdJob:
    scenario_json: str
    variables: tuple[str, ...]
    estimate_ids: tuple[str, ...]
    combined: bool = True


def _reading_record(
    estimate_id: str,
    reading_id: str,
    kind: str,
    plan: ReadingPlan,
    noop: bool,
    outputs: dict[str, float] | None,
    localities: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "estimate": estimate_id,
        "reading": reading_id,
        "kind": kind,
        "variant": plan.variant,
        "override": plan.override.as_dict(),
        "override_text": plan.override.describe(),
        "noop": noop,
        "converged": plan.converged,
        "iterations": len(plan.trace),
        "trace": plan.trace,
        "detail": plan.detail,
        "localities": list(localities),
        "outputs": outputs,
    }


def sweep_household(job: HouseholdJob, engine: Engine, patch=None) -> dict[str, Any]:
    """The reference and every applicable reading for one household."""
    from policybench.scenarios import scenario_from_dict

    started = time.perf_counter()
    scenario = scenario_from_dict(json.loads(job.scenario_json))
    situation = build_reference_situation(scenario, engine, patch)
    ctx = HouseholdContext(
        scenario=scenario,
        situation=situation,
        variables=list(job.variables),
        engine=engine,
    )
    ctx.baseline = engine.simulate(copy.deepcopy(situation))
    baseline_outputs = ctx.outputs(ctx.baseline)
    scope_components = dict.fromkeys(
        engine.removed_local_components + engine.remaining_local_components
    )
    local_taxes = {
        name: ctx.total(ctx.baseline, name)
        for name in scope_components
        if engine.has_variable(name)
    }

    def localities_on(simulation: Any) -> set[str]:
        return {
            flag for flag in engine.locality_flags if ctx.total(simulation, flag) > 0
        }

    baseline_localities = localities_on(ctx.baseline)
    estimates = [ESTIMATES_BY_ID[i] for i in job.estimate_ids]
    readings = []
    output_cache: dict[str, tuple[dict[str, float], list[str]]] = {}

    def evaluate(estimate_id: str, reading_id: str, kind: str, plan: ReadingPlan):
        noop = plan.override.is_empty() or ctx.is_noop(plan.override)
        outputs = None
        localities: list[str] = []
        if not noop:
            key = plan.override.key()
            if key not in output_cache:
                simulation = plan.simulation or ctx.simulate(plan.override)
                switched_on = sorted(localities_on(simulation) - baseline_localities)
                output_cache[key] = (ctx.outputs(simulation), switched_on)
            outputs, localities = output_cache[key]
        readings.append(
            _reading_record(
                estimate_id, reading_id, kind, plan, noop, outputs, localities
            )
        )

    for estimate in estimates:
        for reading in estimate.readings:
            for plan in reading.plan(ctx):
                evaluate(estimate.id, reading.id, reading.kind, plan)
    if job.combined:
        for plan in combined_literal_plan(ctx, estimates):
            evaluate(COMBINED_ESTIMATE, COMBINED_READING, LITERAL, plan)

    return {
        "scenario_id": scenario.id,
        "state": scenario.state,
        "baseline": baseline_outputs,
        "local_taxes": local_taxes,
        "baseline_localities": sorted(baseline_localities),
        "readings": readings,
        "simulations": 1 + len(ctx._cache),
        "aggregate_local_components": list(engine.aggregate_local_components),
        "removed_local_components": list(engine.removed_local_components),
        "remaining_local_components": list(engine.remaining_local_components),
        "seconds": round(time.perf_counter() - started, 3),
    }


# ---------------------------------------------------------------------------
# Worker processes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EngineConfig:
    fix_path: str | None
    output_scope_adapter: bool = True
    county_states: tuple[str, ...] | None = None


def load_fix_module(path: str | Path):
    """Import a fix module (``reform`` and/or ``patch(situation, scenario)``)."""
    path = Path(path)
    digest = hashlib.sha1(str(path).encode()).hexdigest()[:8]
    name = f"policybench_fix_{path.stem}_{digest}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def compose_reform(fix_reform, adapter: bool):
    """The fix module's reform, then the output-scope adapter.

    Returns the composed Reform subclass and a dict that receives, when the system
    is built, the local taxes the fix leaves in the state aggregate (the ones the
    adapter removes).
    """
    from policyengine_core.reforms import Reform

    seen: dict[str, list[str]] = {}

    class composed(Reform):
        def apply(self):
            if fix_reform is not None:
                fix_reform.apply(self)
            # The engine can apply a reform more than once; a later pass sees the
            # lists the adapter already scoped, so keep the first observation.
            seen.setdefault(
                "listed", output_scope.all_listed_local_components(self.parameters)
            )
            if adapter:
                self.modify_parameters(output_scope.remove_local_components)

    return composed, seen


def build_engine(config: EngineConfig) -> tuple[Engine, Any]:
    from policyengine_us import CountryTaxBenefitSystem, Simulation

    fix_reform = patch = None
    if config.fix_path:
        module = load_fix_module(config.fix_path)
        fix_reform = getattr(module, "reform", None)
        patch = getattr(module, "patch", None)
    reform, seen = compose_reform(fix_reform, config.output_scope_adapter)
    system = CountryTaxBenefitSystem(reform=reform)
    listed = list(seen.get("listed", ()))
    aggregate = output_scope.listed_local_components(system.parameters)
    remaining = output_scope.all_listed_local_components(system.parameters)
    removed = [name for name in listed if name not in remaining]
    engine = Engine(
        system=system,
        simulation_class=Simulation,
        aggregate_local_components=aggregate,
        removed_local_components=removed,
        remaining_local_components=remaining,
        county_states=(
            frozenset(config.county_states)
            if config.county_states is not None
            else None
        ),
    )
    return engine, patch


_WORKER: dict[str, Any] = {}


def _init_worker(config: EngineConfig) -> None:
    engine, patch = build_engine(config)
    _WORKER["engine"] = engine
    _WORKER["patch"] = patch


def _run_job(job: HouseholdJob) -> dict[str, Any]:
    return sweep_household(job, _WORKER["engine"], _WORKER["patch"])


def _print_progress(done: int, total: int, result: dict[str, Any]) -> None:
    print(
        f"[{done}/{total}] {result['scenario_id']} {result['state']}: "
        f"{result['simulations']} simulations in {result['seconds']:.0f} s",
        file=sys.stderr,
        flush=True,
    )


def run_jobs(
    jobs: Sequence[HouseholdJob],
    config: EngineConfig,
    workers: int,
    progress: Callable[[int, int, dict[str, Any]], None] | None = _print_progress,
) -> list[dict[str, Any]]:
    """Run every job, building the system once per worker process.

    Results come back in completion order; ``evaluate`` sorts them.
    """
    results = []

    def collect(result: dict[str, Any]) -> None:
        results.append(result)
        if progress is not None:
            progress(len(results), len(jobs), result)

    if workers <= 1:
        _init_worker(config)
        for job in jobs:
            collect(_run_job(job))
        return results
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=workers,
        mp_context=context,
        initializer=_init_worker,
        initargs=(config,),
    ) as pool:
        futures = [pool.submit(_run_job, job) for job in jobs]
        for future in as_completed(futures):
            collect(future.result())
    return results


# ---------------------------------------------------------------------------
# Comparison and report
# ---------------------------------------------------------------------------


def is_binary_output(variable: str) -> bool:
    from policybench.spec import metric_type_for_output

    return metric_type_for_output(variable) == "binary"


def output_moved(
    baseline: float, value: float, *, binary: bool, tolerance: float = TOLERANCE
) -> bool:
    """A flag moves when it flips; an amount when it moves past the tolerance."""
    if binary:
        return round(baseline) != round(value)
    return abs(value - baseline) > tolerance


def reproduces(reference: float, value: float, *, binary: bool) -> bool:
    if binary:
        return round(reference) == round(value)
    return abs(value - reference) <= BASELINE_TOLERANCE


def exclusion_names_inputs(record: dict | None, inputs: Iterable[str]) -> bool:
    if not record:
        return False
    text = str(record.get("unlisted_input") or "")
    return any(name in text for name in inputs)


def _acknowledgement_key(entry: dict) -> tuple[str, str, str, str]:
    return (
        entry["scenario_id"],
        entry["variable"],
        entry["estimate"],
        entry.get("reading", "*"),
    )


def load_acknowledgements(path: str | Path | None) -> dict[tuple, dict]:
    """Scored moves already under review (a pending decision or ruling), by key.

    The file is ``{"acknowledged": [{"scenario_id", "variable", "estimate",
    "reading" (optional; any reading if absent), "status", "note"}]}``.
    """
    if not path:
        return {}
    entries = json.loads(Path(path).read_text(encoding="utf-8"))["acknowledged"]
    out = {}
    for entry in entries:
        missing = {"scenario_id", "variable", "estimate", "status"} - set(entry)
        if missing:
            raise SystemExit(
                f"acknowledgement {entry} is missing {', '.join(sorted(missing))}"
            )
        out[_acknowledgement_key(entry)] = entry
    return out


def _acknowledgement_for(
    acknowledgements: dict[tuple, dict],
    sid: str,
    variable: str,
    estimate: str,
    reading: str,
) -> dict | None:
    return acknowledgements.get(
        (sid, variable, estimate, reading)
    ) or acknowledgements.get((sid, variable, estimate, "*"))


def _estimate_inputs(estimate_id: str, parts: Sequence[str] = ()) -> tuple[str, ...]:
    if estimate_id == COMBINED_ESTIMATE:
        names = []
        for part in parts:
            names.extend(ESTIMATES_BY_ID[part.split("/")[0]].engine_inputs)
        return tuple(names)
    return ESTIMATES_BY_ID[estimate_id].engine_inputs


@dataclass
class SweepReport:
    baseline: pd.DataFrame
    moves: pd.DataFrame
    readings: pd.DataFrame
    values: pd.DataFrame
    summary: dict[str, Any]


MOVE_COLUMNS = [
    "scenario_id",
    "state",
    "variable",
    "estimate",
    "reading",
    "kind",
    "variant",
    "reference",
    "baseline",
    "value",
    "delta",
    "status",
    "scored",
    "excluded_reason",
    "exclusion_names_input",
    "acknowledged_status",
    "localities",
    "override",
]


def evaluate(
    results: Sequence[dict[str, Any]],
    reference: pd.Series,
    exclusions: dict[tuple[str, str], dict],
    acknowledgements: dict[tuple, dict] | None = None,
    tolerance: float = TOLERANCE,
) -> SweepReport:
    """Compare every reading with the reference as recomputed, and that with the CSV.

    ``reference`` is the published values indexed by (scenario_id, variable). A move
    is measured against the recomputed reference (the swept system's own baseline),
    so it shows what the reading alone does.
    """
    import pandas as pd

    acknowledgements = acknowledgements or {}
    baseline_rows = []
    move_rows = []
    reading_rows = []
    value_rows = []
    for result in sorted(results, key=lambda r: r["scenario_id"]):
        sid = result["scenario_id"]
        for variable, value in sorted(result["baseline"].items()):
            key = (sid, variable)
            record = exclusions.get(key)
            published = float(reference[key])
            binary = is_binary_output(variable)
            baseline_rows.append(
                {
                    "scenario_id": sid,
                    "state": result["state"],
                    "variable": variable,
                    "reference": published,
                    "baseline": value,
                    "reproduces": reproduces(published, value, binary=binary),
                    "scored": record is None,
                    "excluded_reason": record["reason_code"] if record else "",
                }
            )
        for reading in result["readings"]:
            moved_here = 0
            parts = reading["detail"].get("parts", ())
            inputs = _estimate_inputs(reading["estimate"], parts)
            outputs = reading["outputs"]
            if outputs is not None:
                for variable, value in sorted(outputs.items()):
                    base = result["baseline"][variable]
                    value_rows.append(
                        {
                            "scenario_id": sid,
                            "variable": variable,
                            "estimate": reading["estimate"],
                            "reading": reading["reading"],
                            "variant": reading["variant"],
                            "baseline": base,
                            "value": value,
                        }
                    )
                    binary = is_binary_output(variable)
                    if not output_moved(
                        base, value, binary=binary, tolerance=tolerance
                    ):
                        continue
                    moved_here += 1
                    key = (sid, variable)
                    record = exclusions.get(key)
                    names_input = exclusion_names_inputs(record, inputs)
                    ack = _acknowledgement_for(
                        acknowledgements,
                        sid,
                        variable,
                        reading["estimate"],
                        reading["reading"],
                    )
                    if record is not None:
                        status = (
                            "excluded_same_input"
                            if names_input
                            else "excluded_other_reason"
                        )
                    elif reading["localities"]:
                        status = "prompt_rules_out"
                    elif ack is not None:
                        status = "acknowledged"
                    else:
                        status = "scored"
                    move_rows.append(
                        {
                            "scenario_id": sid,
                            "state": result["state"],
                            "variable": variable,
                            "estimate": reading["estimate"],
                            "reading": reading["reading"],
                            "kind": reading["kind"],
                            "variant": reading["variant"],
                            "reference": float(reference[key]),
                            "baseline": base,
                            "value": value,
                            "delta": value - base,
                            "status": status,
                            "scored": record is None,
                            "excluded_reason": record["reason_code"] if record else "",
                            "exclusion_names_input": names_input,
                            "acknowledged_status": ack["status"] if ack else "",
                            "localities": ";".join(reading["localities"]),
                            "override": reading["override_text"],
                        }
                    )
            reading_rows.append(
                {
                    "scenario_id": sid,
                    "state": result["state"],
                    "estimate": reading["estimate"],
                    "reading": reading["reading"],
                    "kind": reading["kind"],
                    "variant": reading["variant"],
                    "noop": reading["noop"],
                    "converged": reading["converged"],
                    "iterations": reading["iterations"],
                    "outputs_moved": moved_here,
                    "localities": ";".join(reading["localities"]),
                    "override": reading["override_text"],
                    "detail": json.dumps(reading["detail"], sort_keys=True),
                }
            )

    baseline = pd.DataFrame(baseline_rows)
    moves = pd.DataFrame(move_rows, columns=MOVE_COLUMNS)
    readings = pd.DataFrame(reading_rows)
    values = pd.DataFrame(value_rows)
    summary = summarize(results, baseline, moves, readings)
    return SweepReport(baseline, moves, readings, values, summary)


def summarize(
    results: Sequence[dict[str, Any]],
    baseline: pd.DataFrame,
    moves: pd.DataFrame,
    readings: pd.DataFrame,
) -> dict[str, Any]:

    mismatched = baseline[~baseline["reproduces"] & baseline["scored"]]
    scope = [
        {"scenario_id": r["scenario_id"], "local_taxes": r["local_taxes"]}
        for r in results
        if any(abs(v) > 0.005 for v in r["local_taxes"].values())
    ]
    unconverged = readings[~readings["converged"]] if not readings.empty else readings
    per_reading = []
    if not readings.empty:
        grouped = readings.groupby(["estimate", "reading", "kind"], sort=True)
        for (estimate, reading, kind), frame in grouped:
            active = frame[~frame["noop"]]
            these = moves[
                (moves["estimate"] == estimate) & (moves["reading"] == reading)
            ]
            per_reading.append(
                {
                    "estimate": estimate,
                    "reading": reading,
                    "kind": kind,
                    "households_planned": int(frame["scenario_id"].nunique()),
                    "households_changed": int(active["scenario_id"].nunique()),
                    "simulated_variants": int(len(active)),
                    "outputs_moved": int(
                        these[["scenario_id", "variable"]].drop_duplicates().shape[0]
                    ),
                    "scored_outputs_moved": int(
                        these[these["status"] == "scored"][["scenario_id", "variable"]]
                        .drop_duplicates()
                        .shape[0]
                    ),
                }
            )
    by_output = []
    if not moves.empty:
        for (sid, variable), frame in moves.groupby(
            ["scenario_id", "variable"], sort=True
        ):
            by_output.append(
                {
                    "scenario_id": sid,
                    "variable": variable,
                    "status": _strongest_status(frame["status"]),
                    "excluded_reason": frame["excluded_reason"].iloc[0],
                    "estimates": sorted(set(frame["estimate"])),
                    "localities": sorted(
                        {
                            flag
                            for text in frame["localities"].fillna("")
                            for flag in str(text).split(";")
                            if flag
                        }
                    ),
                    "readings": sorted(set(frame["estimate"] + "/" + frame["reading"])),
                    "reference": float(frame["reference"].iloc[0]),
                    "baseline": float(frame["baseline"].iloc[0]),
                    "min_value": float(frame["value"].min()),
                    "max_value": float(frame["value"].max()),
                }
            )
    return {
        "outputs": int(len(baseline)),
        "scored_outputs": int(baseline["scored"].sum()) if len(baseline) else 0,
        "households": int(len(results)),
        "simulations": int(sum(r["simulations"] for r in results)),
        "baseline_scored_mismatches": mismatched[
            ["scenario_id", "variable", "reference", "baseline"]
        ].to_dict("records"),
        "baseline_excluded_mismatches": int(
            (~baseline["reproduces"] & ~baseline["scored"]).sum()
        )
        if len(baseline)
        else 0,
        "scope_violations": scope,
        "unconverged": unconverged[["scenario_id", "estimate", "reading"]].to_dict(
            "records"
        )
        if len(unconverged)
        else [],
        "per_reading": per_reading,
        "moved_outputs": by_output,
        "counts": {
            status: sum(1 for o in by_output if o["status"] == status)
            for status in _STATUS_ORDER
        },
    }


# Strongest first: an output's status is the strongest of its moves. A move is
# scored unless the output is excluded, the reading switches on a locality fact the
# prompt's rule makes false (prompt_rules_out), or an --acknowledged entry covers it.
_STATUS_ORDER = (
    "scored",
    "acknowledged",
    "prompt_rules_out",
    "excluded_other_reason",
    "excluded_same_input",
)


def _strongest_status(statuses: Iterable[str]) -> str:
    present = set(statuses)
    for status in _STATUS_ORDER:
        if status in present:
            return status
    return ""


def render_markdown(summary: dict[str, Any], moves: pd.DataFrame) -> str:
    meta = summary["run"]
    lines = [
        "# Unlisted-input sweep",
        "",
        f"- Engine: policyengine-us {meta['policyengine_us']} "
        f"(policyengine-core {meta['policyengine_core']})",
        f"- Reference system: `{meta['fix_id']}`"
        + (" + `policybench_output_scope`" if meta["output_scope_adapter"] else ""),
        f"- Run: {meta['scenarios']} ({summary['households']} households, "
        f"{summary['outputs']} outputs, {summary['scored_outputs']} scored)",
        f"- Simulations: {summary['simulations']} in {meta['seconds']:.0f} s "
        f"on {meta['workers']} workers",
        f"- Tolerance: ${meta['tolerance']:g} for amounts; flags move when they flip",
        "",
        "## Gates",
        "",
        f"- Baseline reproduces every scored reference: "
        f"{'yes' if not summary['baseline_scored_mismatches'] else 'NO'} "
        f"({len(summary['baseline_scored_mismatches'])} mismatches)",
        f"- Local taxes and credits in the state outputs: "
        f"{'none' if not summary['scope_violations'] else 'FOUND'}"
        f" (removed by the adapter and zero in every household: "
        f"{', '.join(meta['removed_local_components']) or 'none'}; "
        f"still listed: {', '.join(meta['remaining_local_components']) or 'none'})",
        f"- Fixed points converged: {'yes' if not summary['unconverged'] else 'NO'}",
        f"- Scored outputs that move: {summary['counts']['scored']}",
        f"- Outputs that move only where a reading puts the household in a "
        f"locality (prompt_rules_out): {summary['counts']['prompt_rules_out']}",
        "",
        "## Readings",
        "",
        "| Estimate | Reading | Kind | Households changed | Simulations | "
        "Outputs moved | Scored |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in summary["per_reading"]:
        lines.append(
            f"| {row['estimate']} | {row['reading']} | {row['kind']} | "
            f"{row['households_changed']} | {row['simulated_variants']} | "
            f"{row['outputs_moved']} | {row['scored_outputs_moved']} |"
        )
    lines += ["", "## Outputs that move", ""]
    if not summary["moved_outputs"]:
        lines.append("None.")
    else:
        lines += [
            "| Output | Status | Published | Recomputed | Range under readings "
            "| Readings |",
            "|---|---|---:|---:|---|---|",
        ]
        for row in summary["moved_outputs"]:
            status = row["status"]
            if row["excluded_reason"]:
                status += f" ({row['excluded_reason']})"
            elif row["status"] == "prompt_rules_out":
                status += f" ({', '.join(row['localities'])})"
            lines.append(
                f"| {row['scenario_id']} {row['variable']} | {status} | "
                f"{row['reference']:,.2f} | {row['baseline']:,.2f} | "
                f"{row['min_value']:,.2f} to "
                f"{row['max_value']:,.2f} | {', '.join(row['readings'])} |"
            )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not installed"


def assemble_fix_dir(fix: Path, support: Sequence[Path], destination: Path) -> Path:
    """Copy the fix module's directory and support files into ``destination``.

    Fix modules load their parts and data files from their own directory
    (``Path(__file__).with_name``); the 2026-09-28 sales tax convention reads
    ``r19_irs_sales_tax_2025.json``, which lives in the 2026-09-22 directory.
    """
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(fix.parent.iterdir()):
        if path.is_file() and path.suffix in {".py", ".json"}:
            shutil.copy2(path, destination / path.name)
    for path in support:
        shutil.copy2(path, destination / path.name)
    return destination / fix.name


def _county_count(state: str) -> int:
    try:
        from policyengine_us.variables.household.demographic.geographic.county.county_enum import (  # noqa: E501
            County,
        )
    except ImportError:  # pragma: no cover - the engine moved the enum
        return 0
    return sum(1 for c in County if str(c.value).endswith(f", {state}"))


def build_jobs(
    scenarios: pd.DataFrame,
    reference: pd.Series,
    programs: Sequence[str],
    estimates: Sequence[UnlistedEstimate],
    county_states: frozenset[str] | None,
    combined: bool = True,
) -> list[HouseholdJob]:
    """One job per household, longest first so the pool's tail is short."""
    from policybench.scenarios import scenario_from_dict
    from policybench.spec import expand_programs_for_scenario

    estimate_ids = tuple(e.id for e in estimates)
    jobs = []
    for _, row in scenarios.iterrows():
        scenario = scenario_from_dict(json.loads(row["scenario_json"]))
        variables = tuple(
            v
            for v in expand_programs_for_scenario(list(programs), scenario)
            if (scenario.id, v) in reference.index
        )
        cost = 1
        if "county" in estimate_ids and (
            county_states is None or scenario.state in county_states
        ):
            cost += _county_count(scenario.state)
        jobs.append(
            (
                cost,
                scenario.id,
                HouseholdJob(row["scenario_json"], variables, estimate_ids, combined),
            )
        )
    jobs.sort(key=lambda item: (-item[0], item[1]))
    return [job for _, _, job in jobs]


def _resolve(run_dir: Path, explicit: str | None, name: str) -> Path:
    return Path(explicit) if explicit else run_dir / name


def run(args) -> int:
    """The ``unlisted-input-sweep`` command. Returns the process exit code."""
    import pandas as pd

    started = time.perf_counter()
    run_dir = Path(args.run_dir)
    scenarios_path = _resolve(run_dir, args.scenarios, "scenarios.csv")
    reference_path = _resolve(run_dir, args.reference, "reference_outputs.csv")
    meta_path = Path(f"{reference_path}.meta.json")
    exclusions_path = _resolve(run_dir, args.exclusions, "reference_exclusions.json")
    for path in (scenarios_path, reference_path, meta_path):
        if not path.exists():
            raise SystemExit(f"Missing {path}")

    programs = json.loads(meta_path.read_text(encoding="utf-8"))["programs"]
    reference = pd.read_csv(reference_path).set_index(["scenario_id", "variable"])[
        "value"
    ]
    exclusions = {}
    if exclusions_path.exists():
        for record in json.loads(exclusions_path.read_text(encoding="utf-8"))[
            "exclusions"
        ]:
            exclusions[(record["scenario_id"], record["variable"])] = record
    acknowledgements = load_acknowledgements(args.acknowledged)
    scenarios = pd.read_csv(scenarios_path)
    if args.scenario:
        scenarios = scenarios[scenarios["scenario_id"].isin(args.scenario)]
        if scenarios.empty:
            raise SystemExit("No scenarios match --scenario")
    if (scenarios["country"] != "us").any():
        raise SystemExit("The unlisted-input sweep covers US scenarios only")

    estimates = select_estimates(args.estimate)
    county_states = (
        None
        if args.county_states in (None, "all")
        else frozenset(s.strip().upper() for s in args.county_states.split(","))
    )
    jobs = build_jobs(
        scenarios,
        reference,
        programs,
        estimates,
        county_states,
        combined=not args.no_combined,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fix = Path(args.fix) if args.fix else None
    support = [Path(p) for p in args.fix_support or []]
    workers = args.workers or max(1, min(16, (os.cpu_count() or 2) - 2))
    with tempfile.TemporaryDirectory(prefix="unlisted_input_sweep_fix_") as tmp:
        fix_files = {}
        fix_path = None
        if fix is not None:
            fix_path = assemble_fix_dir(fix, support, Path(tmp))
            fix_files = {
                p.name: _sha256(p) for p in sorted(Path(tmp).iterdir()) if p.is_file()
            }
        config = EngineConfig(
            fix_path=str(fix_path) if fix_path else None,
            output_scope_adapter=not args.no_output_scope_adapter,
            county_states=tuple(sorted(county_states)) if county_states else None,
        )
        print(
            f"policyengine-us {_package_version('policyengine-us')}; "
            f"{len(jobs)} households; {len(estimates)} estimates; {workers} workers",
            flush=True,
        )
        results = run_jobs(jobs, config, workers)
    scope = scope_lists(results)

    report = evaluate(results, reference, exclusions, acknowledgements, args.tolerance)
    summary = report.summary
    summary["run"] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "policyengine_us": _package_version("policyengine-us"),
        "policyengine_core": _package_version("policyengine-core"),
        "fix": str(fix) if fix else None,
        "fix_id": fix.stem if fix else "baseline",
        "fix_files_sha256": fix_files,
        "output_scope_adapter": not args.no_output_scope_adapter,
        **scope,
        "scenarios": str(scenarios_path),
        "scenarios_sha256": _sha256(scenarios_path),
        "reference": str(reference_path),
        "reference_sha256": _sha256(reference_path),
        "exclusions": str(exclusions_path) if exclusions_path.exists() else None,
        "exclusions_sha256": _sha256(exclusions_path)
        if exclusions_path.exists()
        else None,
        "acknowledged": args.acknowledged,
        "tolerance": args.tolerance,
        "county_states": sorted(county_states) if county_states else "all",
        "combined_literal_reading": not args.no_combined,
        "workers": workers,
        "seconds": round(time.perf_counter() - started, 1),
    }
    summary["estimates"] = [e.describe() for e in estimates]

    report.moves.to_csv(out_dir / "moves.csv", index=False)
    report.readings.to_csv(out_dir / "readings.csv", index=False)
    report.baseline.to_csv(out_dir / "baseline.csv", index=False)
    report.values.to_csv(out_dir / "values.csv.gz", index=False)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    (out_dir / "households.json").write_text(
        json.dumps(
            [
                {k: v for k, v in r.items() if k != "readings"}
                | {
                    "readings": [
                        {k: v for k, v in reading.items() if k != "outputs"}
                        for reading in r["readings"]
                        if not reading["noop"]
                    ]
                }
                for r in sorted(results, key=lambda r: r["scenario_id"])
            ],
            indent=1,
            sort_keys=True,
            default=_json_default,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown = render_markdown(summary, report.moves)
    (out_dir / "report.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    return exit_code(
        summary,
        strict=args.strict,
        allow_baseline_mismatch=args.allow_baseline_mismatch,
    )


SCOPE_KEYS = (
    "aggregate_local_components",
    "removed_local_components",
    "remaining_local_components",
)


def scope_lists(results: Sequence[dict[str, Any]]) -> dict[str, list[str]]:
    """The local entries the swept system removed from, or keeps in, its state lists.

    Every worker builds the same system, so every household reports the same lists.
    """
    lists = {tuple(tuple(r[key]) for key in SCOPE_KEYS) for r in results}
    if len(lists) > 1:
        raise RuntimeError(f"workers built different systems: {sorted(lists)}")
    if not lists:
        return {key: [] for key in SCOPE_KEYS}
    return {key: list(values) for key, values in zip(SCOPE_KEYS, lists.pop())}


def exit_code(
    summary: dict[str, Any], *, strict: bool, allow_baseline_mismatch: bool
) -> int:
    """1 when the sweep itself fails a gate; 2 when --strict finds scored moves."""
    if summary["baseline_scored_mismatches"] and not allow_baseline_mismatch:
        return 1
    if summary["scope_violations"] or summary["unconverged"]:
        return 1
    if strict and summary["counts"]["scored"]:
        return 2
    return 0


def _json_default(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def add_arguments(parser) -> None:
    parser.add_argument(
        "--fix",
        default=None,
        help=(
            "Fix module defining the reference system (reform and/or "
            "patch(situation, scenario)), e.g. "
            "reference_audit/2026-09-28/fixes/latest_final.py"
        ),
    )
    parser.add_argument(
        "--fix-support",
        action="append",
        default=None,
        help="Extra file the fix module reads from its directory (repeatable)",
    )
    parser.add_argument(
        "--run-dir",
        default=str(DEFAULT_RUN_DIR),
        help="Frozen run directory with scenarios.csv, reference_outputs.csv, "
        "its .meta.json and reference_exclusions.json",
    )
    parser.add_argument("--scenarios", default=None, help="Override scenarios.csv")
    parser.add_argument(
        "--reference", default=None, help="Override reference_outputs.csv"
    )
    parser.add_argument(
        "--exclusions", default=None, help="Override reference_exclusions.json"
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--estimate",
        action="append",
        default=None,
        help=f"Registered estimate to sweep (repeatable; default all): "
        f"{', '.join(ESTIMATES_BY_ID)}",
    )
    parser.add_argument(
        "--scenario", action="append", default=None, help="Restrict to a scenario id"
    )
    parser.add_argument(
        "--county-states",
        default="all",
        help="States whose counties the county estimate sweeps: 'all' (default) "
        "or a comma-separated list such as MD",
    )
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--tolerance", type=float, default=TOLERANCE)
    parser.add_argument(
        "--acknowledged",
        default=None,
        help="JSON of scored moves already under review, so --strict passes them",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 2 when any scored output moves without an exclusion or "
        "acknowledgement",
    )
    parser.add_argument(
        "--allow-baseline-mismatch",
        action="store_true",
        help="Do not fail when the recomputed reference differs from the CSV "
        "(previewing a new engine)",
    )
    parser.add_argument(
        "--no-output-scope-adapter",
        action="store_true",
        help="Sweep the fix module's system without policybench.output_scope",
    )
    parser.add_argument(
        "--no-combined",
        action="store_true",
        help="Skip the reading that applies every literal reading at once",
    )
