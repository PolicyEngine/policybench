"""The household calculator the PolicyBench tool pilot gives a model.

Written by ``scripts/sync_calculator_core.py``; do not edit it by hand.

This module is a verbatim copy of the calculator inside
``scripts/tool_pilot_argon.py``: the tool's schema and descriptions for each
feature set, the validator (names, labels, placement, overrides, the flat
household), the engine call, the explanations, the board's pinned engine and
convention reform, and the worker pool that runs each call in its own process
under a timeout. Nothing here calls a model.

Why a copy. The v2 confirmatory runner refuses to start unless
``scripts/tool_pilot_argon.py`` and the ``policybench`` package are its
treatment commit's (``scripts/confirmatory_run.py``, ``TREATMENT_PATHS``), so
the harness cannot import this module until that run is over. Until then both
hold the same code. ``tests/test_calculator_core.py`` fails if this file is
not the sync script's output for the harness as it stands, if any definition
here differs from the harness's (compared by AST), or if the two build
different tool schemas or read a call differently. To change the calculator,
change the harness and run the sync script; once the treatment pin is lifted,
the harness imports this module and its own copy goes.

Everything below the imports is the harness's text, in the harness's order.
"""

from __future__ import annotations

import contextlib
import copy
import difflib
import functools
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import multiprocessing as mp
import os
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
FIX_MODULE = ROOT / "reference_audit/2026-09-28/fixes/latest_final.py"
# The bytes the 2.41.0 references were built with: the sidecar's 2026-10-13
# engine_upgrade revision pins latest_final.py to this sha256, and
# verify_fix_pins checks it and every module it composes against that revision.
FIX_MODULE_SHA256 = "dbbdd228b99933c6f336af97970821c25c863a18606285e8d6d9ffb3bc9af78e"

YEAR = 2026
REFERENCE_ENGINE = "2.41.0"

TOOL_NAME = "calculate_household"

TOOL_TIMEOUT_SECONDS = 60
WORKER_START_TIMEOUT_SECONDS = 900

POOL_UNAVAILABLE = "pool_unavailable"

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

# The calculator's features, each on or off, so a study can change one at a
# time (Max, 2026-10-23: "measuring this as an experiment could be
# publishable"; "do all these tests with a cheap model"):
# - names: a name written with spaces, or a benchmark output key, is read as
#   its engine variable;
# - labels: a fact written under the label the prompt gives it (a prompt
#   labels some facts in words, e.g. employment_income as "gross wages and
#   salaries"; policybench.prompts.INPUT_LABEL_OVERRIDES) is read as its
#   variable, and a fact the reference also sets under another name
#   (policybench.scenarios.PE_INPUT_ALIASES: usual weekly hours) is set there
#   too;
# - placement: an input set on another entity moves to the one unit holding
#   its people;
# - overrides: a realized contribution is read as its _desired input, and an
#   input that replaces a formula is flagged;
# - explain: `explain` traces up to three variables;
# - concise: an explanation is brief unless `detail` is "full";
# - flat: the household is described as people with roles and facts
#   (`household`), and the tool builds its units as the benchmark does.
# "pe2" is tool version 2 (names, placement, overrides and explain); "pe3" is
# all seven. Any other set
# runs as an arm named "pe:" plus its features joined by "+", e.g.
# "pe:names+flat".
NAMES, LABELS, PLACEMENT, OVERRIDES, EXPLAIN, CONCISE, FLAT = (
    "names",
    "labels",
    "placement",
    "overrides",
    "explain",
    "concise",
    "flat",
)
TOOL_FEATURES = (NAMES, LABELS, PLACEMENT, OVERRIDES, EXPLAIN, CONCISE, FLAT)
V2_FEATURES = frozenset({NAMES, PLACEMENT, OVERRIDES, EXPLAIN})
FEATURES_BY_ARM = {
    "pe": frozenset(),
    "web+pe": frozenset(),
    "pe2": V2_FEATURES,
    "pe3": frozenset(TOOL_FEATURES),
    "web+pe3": frozenset(TOOL_FEATURES),
}
_FEATURE_ARM = re.compile(r"^pe:([a-z]+(?:\+[a-z]+)*)$")


def arm_features(arm: str) -> frozenset | None:
    """The calculator features an arm offers, or None for an arm without the
    calculator. Refuses an unknown feature, or concise without explain."""
    if arm in FEATURES_BY_ARM:
        return FEATURES_BY_ARM[arm]
    match = _FEATURE_ARM.match(arm or "")
    if match is None:
        return None
    features = frozenset(match.group(1).split("+"))
    unknown = sorted(features - set(TOOL_FEATURES))
    if unknown:
        raise SystemExit(
            f"unknown tool features {unknown}; the features are {TOOL_FEATURES}"
        )
    if CONCISE in features and EXPLAIN not in features:
        raise SystemExit("the concise feature needs explain")
    return features


# The engine version the notices and the tool description state: the board's
# (set by command_run), so a household set on a newer engine says so. The
# frozen board's 2.41.0 leaves every text byte for byte as before.
_STATED_ENGINE = {"version": REFERENCE_ENGINE}


def set_stated_engine(version: str) -> None:
    _STATED_ENGINE["version"] = version


@contextlib.contextmanager
def stating_engine(version: str):
    """The texts as a run on `version` sent them, for a check that rebuilds a
    notice; the stated engine is restored afterwards."""
    before = _STATED_ENGINE["version"]
    set_stated_engine(version)
    try:
        yield
    finally:
        set_stated_engine(before)


def engine_text(text: str) -> str:
    return text.replace(
        f"policyengine-us {REFERENCE_ENGINE}",
        f"policyengine-us {_STATED_ENGINE['version']}",
    )


V2_PILOT_DEFINITIONS = (
    (
        re.compile(
            r"whether (.+?) is eligible for Medicaid under PolicyEngine rules, "
            r"not whether they are currently enrolled \(1 if yes, 0 if no\)"
        ),
        "whether {who} is eligible for Medicaid in 2026 under federal and state "
        "Medicaid rules, not whether they are currently enrolled; the Medicare "
        "Savings Programs (QMB, SLMB and QI), which help only with Medicare costs, "
        "do not count (1 if yes, 0 if no)",
    ),
    (
        re.compile(
            r"whether (.+?) is eligible for CHIP under PolicyEngine rules, "
            r"not whether they are currently enrolled \(1 if yes, 0 if no\)"
        ),
        "whether {who} is eligible for CHIP (the Children's Health Insurance "
        "Program, including any CHIP coverage the state gives pregnant women) in "
        "2026 under federal and state rules, not whether they are currently "
        "enrolled; someone eligible for Medicaid is not CHIP-eligible (1 if yes, "
        "0 if no)",
    ),
    (
        re.compile(
            r"whether PolicyEngine returns positive annual free school meal support "
            r"for the household \(1 if yes, 0 if no; reduced-price meals do not "
            r"count as 1\)"
        ),
        "whether the household's children get free school meals in 2026: treat "
        "everyone aged 5 to 17 as attending a public K-12 school that takes part "
        "in the National School Lunch and School Breakfast Programs, and count "
        "meals at no charge to the family, whether through federal free-meal "
        "eligibility or a state program that makes both breakfast and lunch free "
        "for all students or pays the reduced-price charge for both breakfast and "
        "lunch (1 if yes, 0 if no; 0 if no one is aged 5 to 17; reduced-price "
        "meals do not count as 1)",
    ),
    (
        re.compile(
            r"whether PolicyEngine returns positive annual reduced-price school meal "
            r"support for the household \(1 if yes, 0 if no; free meals do not "
            r"count as 1\)"
        ),
        "whether the household's children get reduced-price school meals in 2026: "
        "treat everyone aged 5 to 17 as attending a public K-12 school that takes "
        "part in the National School Lunch and School Breakfast Programs, and "
        "count meals at the federal reduced price that no state program makes "
        "free (1 if yes, 0 if no; 0 if no one is aged 5 to 17; free meals do not "
        "count as 1)",
    ),
)
# d1029 (Max, 2026-11-01): the US income tax outputs cover the head and spouse's
# return only. The reference has no second tax unit, so a dependent's own return
# is in no reference, and household sets drop households where a dependent has
# income or a loss (policybench.scenarios._households_with_dependent_return_income).
HEAD_SPOUSE_RETURN = (
    "Cover only the return of the head and spouse, not any return a dependent files"
)
# d1971 (Max, 2026-11-01): the EITC comes from 26 USC 32's formula, as d1263 kept
# the rate schedule over the Tax Table. 32(f) prescribes the IRS table, which
# differs by a few dollars ($3,183 against $3,179.76 for one pilot household).
STATE_USES_EITC_FORMULA = (
    "Where a state amount depends on the federal EITC, use the EITC from the "
    "formula in 26 U.S.C. 32"
)

# d1263 (Max, 2026-10-13): keep the section 1 rate schedule for federal income
# tax, and state that convention in the v2 prompt. A web arm finds the IRS Tax
# Table: in the 2026-10-21 trial GPT-6 Sol answered scenario_000 from it, $1.45
# off the schedule reference.
V2_PILOT_CONVENTIONS = (
    (
        re.compile(
            r"(federal individual income tax after nonrefundable credits and before "
            r"refundable credits\. This subtracts nonrefundable credits actually "
            r"used, including CDCC and the nonrefundable portion of CTC or other "
            r"credits when applicable; it does not subtract EITC or refundable "
            r"portions of credits such as refundable CTC)"
        ),
        "{who}. Compute regular income tax from the section 1 tax rate schedules, "
        "to the cent, even where the Form 1040 instructions would use the Tax "
        f"Table. {HEAD_SPOUSE_RETURN}",
    ),
    (
        # The refundable CTC depends on the tax liability, so the schedule
        # choice can move this output too.
        re.compile(
            r"(total refundable federal income tax credits, including EITC and "
            r"refundable portions of credits such as refundable CTC when "
            r"applicable; exclude the ACA Premium Tax Credit)"
        ),
        "{who}. Where a credit depends on income tax liability, compute that "
        "liability from the section 1 tax rate schedules, not the Tax Table. "
        "Compute the EITC from the formula in 26 U.S.C. 32, to the cent, not from "
        f"the IRS EIC table. {HEAD_SPOUSE_RETURN}",
    ),
    (
        # policyengine-us 2.41.0's state_income_tax_before_refundable_credits
        # list adds id_pbf for Idaho ("Form 40 permanent building fund tax,
        # added before refundable credits"); no other state adds such a tax.
        # GPT-6 Sol's tool answers for scenario_007 were $10 short without it.
        re.compile(
            r"(state individual income tax after nonrefundable credits and before "
            r"refundable credits, excluding local income and payroll taxes)"
        ),
        "{who}; include Idaho's $10 permanent building fund tax where it applies. "
        f"{STATE_USES_EITC_FORMULA}. {HEAD_SPOUSE_RETURN}",
    ),
    (
        re.compile(r"(total refundable state individual income tax credits)"),
        f"{{who}}. {STATE_USES_EITC_FORMULA}. {HEAD_SPOUSE_RETURN}",
    ),
    (
        # The reference rule (reference sidecar, quoted in each
        # reference_audit/2026-09-28/fixes/latest_c_* module): "a scored
        # reference follows from the stated facts and from law published before
        # the 2026-07-03 reference freeze". Where no 2026 amount was published by
        # then, the reference holds the last one published before it: California's
        # 2025 indexed amounts, Idaho's zero-rate thresholds, the IRS 2025
        # optional sales tax tables, and some Maryland, Michigan and Minnesota
        # amounts. SNAP holds the FY2026 schedule (allotments, deductions,
        # utility allowances, asset limits) for October to December; "Not held:
        # the poverty guideline", so income limits move to the 2026 guideline in
        # October. Web arms had applied SNAP's FY2027 schedule, published in
        # August 2026 (GPT-6 Sol, scenarios 008 and 012).
        #
        # d1972(4) (Max, 2026-11-01): Louisiana is the one amount stated outright.
        # policyengine-us 2.60.4 carries RIB 26-019's $12,838 and $25,676, from
        # 2026-09-28; before the freeze LDR published only the provisional
        # $12,875 and $25,750 (reference_audit/2026-10-05-louisiana). The fallback
        # would send a careful reader to those, as d994 foresaw; the 20-household
        # pilot's models answered from $25,750 (mt_004).
        #
        # Session call (judge triage Pattern B): engine defaults make rental,
        # farm rent, partnership and S corporation income qualified business
        # income, and the `_would_be_qualified` flags are never prompted, so the
        # convention is stated. Setting the flags false instead would part the
        # references from what a calculator call returns on the same facts.
        re.compile(
            r"(Do not infer unlisted income, expenses, assets, benefit receipt, "
            r"rent, or health coverage\.)"
        ),
        "{who} Apply the law and program parameters published before July 3, "
        "2026. Where a 2026 amount had not been published by then, use the latest "
        "amount published before that date (for example, a state's 2025 "
        "inflation-adjusted amounts, or the IRS's 2025 optional sales tax "
        "tables). For SNAP, keep the fiscal year 2026 allotments, deductions, "
        "utility allowances and asset limits through December 2026; the income "
        "limits use the 2026 HHS poverty guidelines from October 2026. Louisiana's "
        "2026 standard deduction is $12,838 for single and separate filers and "
        "$25,676 for all other filers, not the provisional $12,875 and $25,750 in "
        "its withholding tables and estimated-tax worksheet; an amount an agency "
        "labels provisional or estimated is not a published return amount. Treat "
        "rental, farm rent, partnership and S corporation income as qualified "
        "business income under section 199A.",
    ),
    (
        # d1970 (Max, 2026-11-01): policyengine-us defaults immigration_status
        # and ssn_card_type to CITIZEN, and the prompt's rule makes unlisted
        # statuses false. The references keep the default and set it explicitly
        # (household_set.situation_for). 5 of the 14 disputed verdicts in the
        # 20-household pilot turned on this.
        re.compile(r"(fact, boolean, or status input as false\.)"),
        "{who} Everyone listed is a U.S. citizen with a valid Social Security "
        "number issued before the return's due date, unless stated otherwise.",
    ),
    (
        # d1972(2) (Max, 2026-11-01): a period for every amount. Read as monthly,
        # mt_017's $1,920 rent moved DC SNAP from $1,284 to $3,576.
        re.compile(
            r"Gross wage and salary amounts are annual totals, including any "
            r"overtime pay;"
        ),
        "Every dollar amount is an annual total, including rent and other "
        "expenses, except asset and vehicle values, loan balances and the basis of "
        "business property; gross wages and salaries include any overtime pay;",
    ),
    (
        # d1972(3) (Max, 2026-11-01): each income's tax character. Partnership
        # income: the ruled label read "(Schedule E; no self-employment
        # earnings)". partnership_self_employment_net_earnings "is not an
        # additional gross income source separate from partnership_income"
        # (policyengine-us 2.60.4), and two pilot people carry that line, so the
        # label yields to it and the second label says the amount is a part.
        re.compile(r"(?m)^- partnership income: "),
        "- partnership income (Schedule E; no self-employment earnings unless a "
        "separate line states them): ",
    ),
    (
        re.compile(r"(?m)^- partnership self employment net earnings: "),
        "- partnership net earnings from self-employment (part of partnership "
        "income, not added to it): ",
    ),
    (
        # educational_assistance feeds no gross-income source in policyengine-us
        # 2.60.4, so the reference treats all of it as tax-free. Read as taxable,
        # mt_019's $10,000 moved federal tax by $1,200.
        re.compile(r"(?m)^- educational assistance: "),
        "- educational assistance (tax-free scholarships and grants): ",
    ),
    (
        # "Memo component of long_term_capital_gains -- already included there"
        # (policyengine-us 2.60.4). The judge and the consensus added it twice.
        re.compile(r"(?m)^- schedule d capital gain distributions: "),
        "- capital gain distributions (already included in long-term capital gains): ",
    ),
    (
        # policyengine-us documents employer_sponsored_insurance_premiums as
        # "Annual employer-paid health insurance premiums". Three web arms read
        # the bare label as premiums the household paid (scenario_000).
        re.compile(r"employer sponsored insurance premiums: "),
        "employer-paid health insurance premiums (paid by the employer, not by "
        "the household): ",
    ),
    (
        # spm_unit_energy_subsidy, the SPM's energy subsidy (home energy
        # assistance). No scored output reads it. policyengine-us never reads the
        # amount for SNAP: it deems a utility allowance from the state's
        # always-SUA flag, and in 2026 only for elderly or disabled households
        # (heat_and_eat_requires_elderly_disabled, P.L. 119-21 section 10103).
        # The engine label hid what the amount is.
        re.compile(r"spm unit energy subsidy: "),
        "home energy assistance received: ",
    ),
)


def v2_pilot_text(text: str) -> str:
    """The text with the four PolicyEngine-naming definitions made neutral and
    the conventions Max has ruled the v2 prompt states (V2_PILOT_CONVENTIONS)."""
    for pattern, replacement in (*V2_PILOT_DEFINITIONS, *V2_PILOT_CONVENTIONS):
        text = pattern.sub(
            lambda m, r=replacement: r.format(who=m.group(1)) if m.re.groups else r,
            text,
        )
    return text


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


CALCULATE_DESCRIPTION_V2 = CALCULATE_DESCRIPTION.replace(
    "An unknown name, a variable set on the wrong entity, or a malformed "
    "situation returns an error with suggestions instead of results.",
    "A name may also be written with spaces (as the facts are labeled) or be one "
    "of the output keys you are asked for; the result's `notes` say how each was "
    "read. An input set on the wrong entity is moved to the one unit it belongs "
    "to, and the notes say so; where there is no single such unit, or a name is "
    "unknown, or the situation is malformed, it returns an error with "
    "suggestions instead of results. Setting a variable the engine computes "
    "replaces its formula, and the notes say so; a contribution set as the "
    "amount contributed is read as the amount asked for before limits "
    "(`..._desired`). `explain` lists up to 3 variables to trace: each comes "
    "back with the steps that produced it and the parameters, with their "
    "values and sources, that it used.",
)
MAX_EXPLAIN = 3


FLAT_DESCRIPTION = (
    "Run PolicyEngine US (policyengine-us 2.41.0) on one household and return "
    "the requested variables. `household` is a JSON object: `state` (the "
    "two-letter state code), `people` (a list, each with `role` -- head, "
    'spouse or dependent --, `facts`, for example {"age": 40, '
    '"employment_income": 30000}, and optionally `name`, by default the role, '
    "numbered for dependents), and `household_facts` (facts about the "
    "household as a whole: its tax unit, family, SPM unit or home). The head "
    "and spouse are one couple and everyone else is on their own; everyone "
    "shares one tax unit, family, SPM unit and household. A fact is a value "
    'for `period`, or {period: value} with a period such as "2026" or '
    '"2026-01". Facts you do not give take the engine\'s defaults. `variables` '
    'lists the variables to compute for `period` (default "2026"). Each '
    "result gives the variable's entity, label and value for each member of "
    "that entity; a monthly variable computed for a year is summed over its "
    "months. An unknown name or a malformed household returns an error with "
    "suggestions instead of results."
)
# The version 1 description's last sentence, which placement amends.
_ENTITY_ERROR_SENTENCE = (
    "An unknown name, a variable set on the wrong entity, or a malformed "
    "situation returns an error with suggestions instead of results."
)


def calculate_tool_schema(version: int = 1, features: frozenset | None = None) -> dict:
    if features is None:
        features = V2_FEATURES if version == 2 else frozenset()
    if features:
        schema = calculate_tool_schema(1)
        function = schema["function"]
        properties = function["parameters"]["properties"]
        if features == V2_FEATURES:
            function["description"] = engine_text(CALCULATE_DESCRIPTION_V2)
        else:
            description = (
                FLAT_DESCRIPTION if FLAT in features else CALCULATE_DESCRIPTION
            )
            if PLACEMENT in features and FLAT not in features:
                description = description.replace(
                    _ENTITY_ERROR_SENTENCE,
                    "An unknown name or a malformed situation returns an error "
                    "with suggestions instead of results.",
                )
            notes = []
            if LABELS in features:
                notes.append(
                    "A fact may be written under the label it has in the facts "
                    "you were given."
                )
            if NAMES in features:
                notes.append(
                    "A name may also be written with spaces or be one of the "
                    "output keys you are asked for."
                )
            if PLACEMENT in features and FLAT not in features:
                notes.append(
                    "An input set on the wrong entity is moved to the one unit "
                    "holding its people; where no single unit holds them, it "
                    "returns an error."
                )
            if OVERRIDES in features:
                notes.append(
                    "Setting a variable the engine computes replaces its formula; a "
                    "contribution set as the amount contributed is read as the "
                    "amount asked for before limits (`..._desired`)."
                )
            if notes:
                notes.append("The result's `notes` say what it did.")
            function["description"] = engine_text(" ".join([description, *notes]))
        if FLAT in features:
            del properties["situation"]
            properties["household"] = {
                "type": "string",
                "description": (
                    "The household as a JSON object (state, people with role and "
                    "facts, household_facts), written as a JSON string."
                ),
            }
            function["parameters"]["required"] = ["household", "variables"]
        if EXPLAIN in features:
            properties["explain"] = {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    f"Up to {MAX_EXPLAIN} variables to explain: how the engine "
                    "computed them."
                ),
            }
        if CONCISE in features:
            properties["detail"] = {
                "type": "string",
                "enum": ["brief", "full"],
                "description": (
                    'How much an explanation shows: "brief" (the default: the '
                    'value, what it came from, and the main parameters) or "full" '
                    f"(the trace, up to {EXPLAIN_MAX_LINES} steps and "
                    f"{EXPLAIN_MAX_PARAMETERS} parameters)."
                ),
            }
        return schema
    return {
        "type": "function",
        "function": {
            "name": TOOL_NAME,
            "description": engine_text(CALCULATE_DESCRIPTION),
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


@dataclass(frozen=True)
class VariableInfo:
    entity: str
    value_type: str
    label: str | None = None
    definition_period: str | None = None
    possible_values: tuple[str, ...] | None = None
    # Whether the engine computes the variable (a formula or a sum of other
    # variables) and no household fact the benchmark states sets it: setting
    # it replaces what the engine would compute.
    computed: bool = False


# Inputs the benchmark's reference situations set besides its promptable
# facts (policybench.scenarios.Scenario.to_pe_household), and the convention
# switches (take-up, filing) any household may set.
BASE_STATED_INPUTS = frozenset(
    {
        "age",
        "employment_income",
        "self_employment_income",
        "long_term_capital_gains",
        "partnership_s_corp_income",
        "is_tax_unit_head",
        "is_tax_unit_spouse",
        "state_code",
        "weekly_hours_worked_before_lsr",
    }
)
CONVENTION_PREFIXES = ("takes_up_", "would_")


def stated_inputs() -> frozenset[str]:
    """Every variable a household fact the benchmark states can set."""
    from policybench.scenarios import PE_INPUT_ALIASES, PE_INPUT_RENAMES

    names = {spec.source_name for spec in _promptable_specs()}
    names |= BASE_STATED_INPUTS
    names |= set(PE_INPUT_ALIASES.values()) | set(PE_INPUT_RENAMES.values())
    return frozenset(names)


def build_registry(
    system, stated: frozenset[str] | None = None
) -> dict[str, VariableInfo]:
    """The engine's variables. ``stated`` (default :func:`stated_inputs`) marks
    which ones a stated fact sets; the rest that the engine computes are
    ``computed``."""
    if stated is None:
        stated = stated_inputs()
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
            computed=bool(
                getattr(variable, "formulas", None)
                or getattr(variable, "adds", None)
                or getattr(variable, "subtracts", None)
            )
            and name not in stated
            and not name.startswith(CONVENTION_PREFIXES),
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


def _normalize_value(
    where: str,
    name: str,
    value,
    info: VariableInfo,
    period: str,
    problems: list[str],
) -> dict | None:
    """One input's {period: value}, or None after recording why not."""
    if isinstance(value, dict):
        if not value:
            problems.append(
                f"{where}: {name} has no values; set it as {{period: value}}."
            )
            return None
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
    return normalized


def _normalize_inputs(
    where: str,
    entity: str,
    data: dict,
    registry: Mapping[str, VariableInfo],
    period: str,
    problems: list[str],
    allow_members: bool,
    v2: dict | None = None,
) -> dict:
    """Each input under its engine name. ``v2`` (tool version 2) collects the
    names it read, the inputs it redirected or flagged, and the inputs set on
    another entity, which normalize_request then places."""
    out: dict[str, Any] = {}
    for name, value in data.items():
        if allow_members and name == "members":
            continue
        if v2 is not None and isinstance(name, str) and name not in registry:
            resolved, note = read_fact_name(name, registry, v2["features"])
            if resolved is not None:
                v2["notes"].append(f"{where}: {note}")
                name = resolved
            elif (field := dropped_fact(name, registry, v2["features"])) is not None:
                v2["notes"].append(_dropped_note(where, name, field))
                continue
        if not isinstance(name, str) or name not in registry:
            problems.append(
                f"{where}: unknown variable {name!r}."
                + (_suggest(name, registry) if isinstance(name, str) else "")
            )
            continue
        info = registry[name]
        if v2 is not None and OVERRIDES in v2["features"]:
            desired = f"{name}{DESIRED_SUFFIX}"
            if (
                info.computed
                and desired in registry
                and registry[desired].entity == info.entity
            ):
                v2["notes"].append(
                    f"{where}: set {desired} (the amount asked for, before "
                    f"limits) for {name}, which the engine computes from it"
                )
                name, info = desired, registry[desired]
            elif info.computed:
                v2["notes"].append(
                    f"{where}: {name} is computed by the engine; the value set "
                    "replaces its formula"
                )
        if info.entity != entity:
            if v2 is not None and PLACEMENT in v2["features"]:
                v2["misplaced"].append((where, entity, name, value))
                continue
            problems.append(
                f"{where}: {name} is a {info.entity} variable; set it under "
                f"{ENTITY_GROUP.get(info.entity, info.entity)}."
            )
            continue
        normalized = _normalize_value(where, name, value, info, period, problems)
        if normalized is None:
            continue
        if v2 is not None and name in out and out[name] != normalized:
            problems.append(f"{where}: {name} is set twice with different values")
            continue
        out[name] = normalized
    return out


def normalize_request(
    args,
    registry: Mapping[str, VariableInfo],
    version: int = 1,
    features: frozenset | None = None,
) -> tuple[dict | None, dict | None]:
    """Check a calculate_household call; return (request, None) or (None, error).

    Accepts only plain JSON data. Every input and output name must be a
    variable of the engine, on its own entity; nothing else in the situation
    (axes, reforms, parameters) is accepted. Tool version 2 also reads a name
    written with spaces or a benchmark output key, redirects a contribution to
    its ``_desired`` input, flags an input that replaces a formula, places an
    input set on another entity where exactly one unit holds it, and takes
    ``explain``; the request's ``notes`` say what it did.
    """
    problems: list[str] = []
    if features is None:
        features = V2_FEATURES if version == 2 else frozenset()
    v2 = {"notes": [], "misplaced": [], "features": features} if features else None

    def fail() -> tuple[None, dict]:
        return None, {
            "error": "validation",
            "problems": problems[:MAX_PROBLEMS],
            "problem_count": len(problems),
        }

    if isinstance(args, str):
        if len(args) > 2 * MAX_SITUATION_CHARS:
            problems.append("arguments are too large")
            return fail()
        try:
            args = json.loads(args)
        except (ValueError, RecursionError) as error:
            problems.append(
                f"arguments are not valid JSON: {error}"[:MAX_MESSAGE_CHARS]
            )
            return fail()
    if not isinstance(args, dict):
        problems.append("arguments must be an object")
        return fail()
    allowed = {"variables", "period"}
    allowed |= {"household"} if FLAT in features else {"situation"}
    allowed |= {"explain"} if EXPLAIN in features else set()
    allowed |= {"detail"} if CONCISE in features else set()
    unknown = sorted(set(args) - allowed)
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

    if FLAT in features:
        args = dict(args)
        args["situation"] = flat_situation(
            args.get("household"), registry, problems, v2, period
        )
        if args["situation"] is None:
            return fail()
    situation = args.get("situation")
    if isinstance(situation, str):
        if len(situation) > MAX_SITUATION_CHARS:
            problems.append("situation is too large")
            return fail()
        try:
            situation = json.loads(situation)
        except (ValueError, RecursionError) as error:
            problems.append(f"situation is not valid JSON: {error}"[:MAX_MESSAGE_CHARS])
            return fail()
    if not isinstance(situation, dict):
        problems.append("situation must be a JSON object")
        return fail()
    try:
        too_large = len(json.dumps(situation, default=str)) > MAX_SITUATION_CHARS
    except (ValueError, RecursionError):
        too_large = True
    if too_large:
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
            f"people.{name}", "person", data, registry, period, problems, False, v2
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
            if not isinstance(unit_name, str) or not unit_name or len(unit_name) > 64:
                problems.append(
                    f"{group} unit name {unit_name!r} must be a short string"
                )
                continue
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
                _normalize_inputs(
                    where, entity, unit, registry, period, problems, True, v2
                )
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
    if v2 is not None and PLACEMENT in features:
        _place_misplaced(v2, normalized, situation, registry, period, problems)
    if v2 is not None and LABELS in features:
        _set_aliases(v2, normalized["people"], registry)
    requested = []
    for name in variables:
        if (
            v2 is not None
            and NAMES in features
            and isinstance(name, str)
            and name not in registry
        ):
            resolved, note = resolve_name(name, registry, output_names=True)
            if resolved is not None:
                v2["notes"].append(f"variables: {note}")
                name = resolved
        if name not in registry:
            problems.append(
                f"variables: unknown variable {name!r}." + _suggest(name, registry)
            )
        elif name not in requested:
            requested.append(name)
    explain = []
    if EXPLAIN in features and args.get("explain") is not None:
        names = args["explain"]
        if isinstance(names, str):
            names = [names]
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            problems.append("explain must be a list of variable names")
            names = []
        elif len(names) > MAX_EXPLAIN:
            problems.append(f"explain at most {MAX_EXPLAIN} variables per call")
        for name in names:
            if NAMES in features and name not in registry:
                resolved, note = resolve_name(name, registry, output_names=True)
                if resolved is not None:
                    v2["notes"].append(f"explain: {note}")
                    name = resolved
            if name not in registry:
                problems.append(
                    f"explain: unknown variable {name!r}." + _suggest(name, registry)
                )
            elif name not in explain:
                explain.append(name)

    detail = None
    if CONCISE in features:
        detail = args.get("detail") or "brief"
        if detail not in ("brief", "full"):
            problems.append('detail must be "brief" or "full"')

    if problems:
        return fail()
    request = {"situation": normalized, "variables": requested, "period": period}
    if v2 is not None:
        request["explain"] = explain
        request["notes"] = v2["notes"]
    if detail is not None:
        request["detail"] = detail
    return request, None


FLAT_ROLES = ("head", "spouse", "dependent")
FLAT_PERSON_KEYS = ("name", "role", "facts")
# The relationship inputs a role sets (as Scenario.to_pe_household's people
# carry them).
FLAT_RELATIONS = {"is_tax_unit_head": "head", "is_tax_unit_spouse": "spouse"}


def flat_names(people) -> list:
    """The name each listed person goes by: the one given, or, for a person
    given none, the role (head, spouse, dependent_1, ...: dependents are
    numbered by their place among the dependents listed)."""
    names, dependents = [], 0
    for person in people if isinstance(people, list) else []:
        if not isinstance(person, dict):
            names.append(None)
            continue
        role = person.get("role")
        if role == "dependent":
            dependents += 1
        name = person.get("name")
        if name is None and role in FLAT_ROLES:
            name = role if role != "dependent" else f"dependent_{dependents}"
        names.append(name)
    return names


def _same_value(
    registry,
    name: str,
    a,
    b,
    period: str,
    problems: list[str] | None = None,
    where: str = "",
) -> bool | None:
    """Whether two values of an input are the same once normalized, or None
    when either is malformed. ``a`` stays in the situation, so normalization
    reports it later; a caller that drops ``b`` passes ``problems`` so a
    malformed ``b`` is reported, not lost."""
    info = registry[name]
    first_problems: list[str] = []
    second_problems: list[str] = []
    first = _normalize_value(where, name, a, info, period, first_problems)
    second = _normalize_value(where, name, b, info, period, second_problems)
    if problems is not None:
        problems.extend(second_problems)
    if first_problems or second_problems:
        return None
    return first == second


def flat_situation(
    household,
    registry,
    problems: list[str],
    v2: dict | None,
    period: str = str(YEAR),
):
    """The flat feature's household -- state, people with role and facts, and
    household facts -- as a situation, with the units the benchmark's own
    reference situations have (policybench.scenarios.Scenario.to_pe_household):
    the head and spouse one marital unit and everyone else alone, and one tax
    unit, SPM unit, family and household holding everyone. Roles set the
    relationship inputs; a stated one that contradicts its role is refused.
    A household fact goes to the unit of its variable's entity, under the
    name it was written with, so normalization reads and compares it as any
    other input. A person given no name is named by role (flat_names).
    Returns None after recording problems."""
    features = v2["features"] if v2 is not None else frozenset()

    def engine_name(name):
        if isinstance(name, str) and name in registry:
            return name
        if isinstance(name, str):
            return read_fact_name(name, registry, features)[0]
        return None

    if isinstance(household, str):
        if len(household) > MAX_SITUATION_CHARS:
            problems.append("household is too large")
            return None
        try:
            household = json.loads(household)
        except (ValueError, RecursionError) as error:
            problems.append(f"household is not valid JSON: {error}"[:MAX_MESSAGE_CHARS])
            return None
    if not isinstance(household, dict):
        problems.append(
            "household must be a JSON object with state, people and household_facts"
        )
        return None
    extra = sorted(set(household) - {"state", "people", "household_facts"})
    if extra:
        problems.append(
            "household accepts state, people and household_facts; remove "
            + ", ".join(map(str, extra))
        )
    people = household.get("people")
    if not isinstance(people, list) or not people:
        problems.append("household.people must be a non-empty list of people")
        return None
    if len(people) > MAX_PEOPLE:
        problems.append(f"at most {MAX_PEOPLE} people")
        return None
    situation: dict[str, Any] = {"people": {}}
    roles: dict[str, str] = {}
    for index, (person, name) in enumerate(zip(people, flat_names(people))):
        if not isinstance(person, dict):
            problems.append(
                f"people[{index}] must be an object with name, role and facts"
            )
            continue
        stray = sorted(map(str, set(person) - set(FLAT_PERSON_KEYS)))
        if stray:
            problems.append(
                f"people[{index}] takes only name, role and facts; give "
                f"{', '.join(stray)} under facts"
            )
            continue
        role, facts = person.get("role"), person.get("facts", {})
        if role not in FLAT_ROLES:
            problems.append(
                f"people[{index}].role must be one of {', '.join(FLAT_ROLES)}"
            )
            continue
        if person.get("name") is None and v2 is not None:
            v2["notes"].append(f"people[{index}]: named {name}")
        if not isinstance(name, str) or not name or len(name) > 64:
            problems.append(f"people[{index}].name must be a short string")
            continue
        if name in roles:
            problems.append(f"people[{index}]: {name!r} is listed twice")
            continue
        if not isinstance(facts, dict):
            problems.append(f"people[{index}].facts must be an object")
            continue
        roles[name] = role
        situation["people"][name] = dict(facts)
    heads = [n for n, r in roles.items() if r == "head"]
    spouses = [n for n, r in roles.items() if r == "spouse"]
    if len(heads) != 1:
        problems.append("the household needs exactly one head")
    if len(spouses) > 1:
        problems.append("the household has at most one spouse")
    if problems:
        return None
    for name, role in roles.items():
        facts = situation["people"][name]
        for relation, relation_role in FLAT_RELATIONS.items():
            if relation not in registry:
                continue
            implied = role == relation_role
            stated = [k for k in facts if engine_name(k) == relation]
            if not stated:
                facts[relation] = implied
            elif any(
                _same_value(registry, relation, facts[k], implied, period) is False
                for k in stated
            ):
                problems.append(
                    f"people.{name}: {relation} contradicts the role {role}; the "
                    "role sets it"
                )
    everyone = list(situation["people"])
    couple = heads + spouses
    groups = [couple] + [[n] for n in everyone if n not in couple]
    situation["marital_units"] = {
        f"marital_unit_{i}": {"members": members}
        for i, members in enumerate(groups, start=1)
    }
    situation["tax_units"] = {"tax_unit": {"members": list(everyone)}}
    situation["spm_units"] = {"spm_unit": {"members": list(everyone)}}
    situation["families"] = {"family": {"members": list(everyone)}}
    situation["households"] = {"household": {"members": list(everyone)}}
    state = household.get("state")
    if state is not None:
        situation["households"]["household"]["state_code"] = state
    unit_of = {
        "tax_unit": situation["tax_units"]["tax_unit"],
        "spm_unit": situation["spm_units"]["spm_unit"],
        "family": situation["families"]["family"],
        "household": situation["households"]["household"],
        "marital_unit": situation["marital_units"]["marital_unit_1"],
    }
    facts = household.get("household_facts") or {}
    if not isinstance(facts, dict):
        problems.append("household_facts must be an object")
        return None
    for name, value in facts.items():
        resolved = engine_name(name)
        if resolved is None:
            field = (
                dropped_fact(name, registry, features)
                if isinstance(name, str)
                else None
            )
            if field is not None:
                v2["notes"].append(_dropped_note("household_facts", name, field))
                continue
            problems.append(
                f"household_facts: unknown variable {name!r}."
                + (_suggest(name, registry) if isinstance(name, str) else "")
            )
            continue
        entity = registry[resolved].entity
        if entity == "person":
            # As placement moves a person variable off a one-person unit: only
            # a household of one says whose fact it is.
            if v2 is None or PLACEMENT not in features or len(everyone) != 1:
                problems.append(
                    f"household_facts: {resolved} is a person's fact; give it "
                    "under the person whose facts list it"
                )
                continue
            target = situation["people"][everyone[0]]
            v2["notes"].append(
                f"household_facts: moved {resolved}, a person's fact, to {everyone[0]}"
            )
        else:
            target = unit_of[entity]
        if name in target:
            # The repeat is dropped, so only one validated as equal is kept quiet.
            same = _same_value(
                registry,
                resolved,
                target[name],
                value,
                period,
                problems,
                "household_facts",
            )
            if same is False:
                problems.append(
                    f"household_facts: {resolved} is set twice with different values"
                )
            continue
        target[name] = value
    return None if problems else situation


DESIRED_SUFFIX = "_desired"
_LABEL_SEPARATORS = re.compile(r"[\s\-]+")


def output_reading(name: str) -> tuple[str, str] | None:
    """A benchmark output key's engine variable and how the output reads it,
    or None when the name is not an output key."""
    from policybench.ground_truth import (
        _aggregation_for_output,
        _pe_variable_for_output,
    )
    from policybench.spec import find_output_spec, parse_person_output

    person = parse_person_output(name)
    if person is None and find_output_spec(name, country="us") is None:
        return None
    engine = _pe_variable_for_output(name, "us")
    if engine == name:
        return None
    aggregation = _aggregation_for_output(name, "us")
    if person is not None:
        how = f"{engine} for the person the key names ({person[0]})"
    elif aggregation == "any_positive":
        how = f"1 when {engine} is above 0, else 0"
    else:
        how = f"{engine}, summed over the household's units"
    return engine, how


def _label_key(text: str) -> str:
    """A label as compared: lower case, letters and digits only, so "Roth
    401(k) contributions" and "roth 401k contributions" read alike."""
    return re.sub(r"[^0-9a-z]", "", text.casefold())


# The prompt's household block gives the state as "state: CT".
PROMPT_EXTRA_LABELS = {"state": "state_code"}


@functools.lru_cache(maxsize=1)
def _promptable_specs():
    from policybench.scenarios import get_promptable_input_specs

    return get_promptable_input_specs()


def _sample_value(value_type: str):
    if value_type == "bool":
        return True
    if value_type in ("str", "Enum"):
        return "x"
    return 1.0


def rendered_labels(field: str, value_type: str = "float") -> tuple[str, ...]:
    """The labels a fact is shown under: in the board's prompt
    (policybench.prompts._format_input_line, special renderers included) and
    in the v2-pilot prompt (v2_pilot_text applied to that line)."""
    from policybench.prompts import _format_input_line, _humanize_input_label

    line = _format_input_line(field, _sample_value(value_type))
    label = _humanize_input_label(field)
    if not (line == f"- {label}" or line.startswith(f"- {label}: ")):
        label = line[2:].split(": ", 1)[0]
    labels = [label]
    suffix = line[2 + len(label) :]
    rewritten = v2_pilot_text(line)
    if rewritten != line and rewritten.startswith("- ") and rewritten.endswith(suffix):
        labels.append(rewritten[2 : len(rewritten) - len(suffix)])
    return tuple(labels)


@functools.lru_cache(maxsize=1)
def prompt_labels() -> dict[str, frozenset[tuple[str, bool]]]:
    """Every label the prompts show a fact under, keyed by _label_key, each
    with the facts it may name as (engine name, dropped): the promptable
    inputs, every labeled input (policybench.prompts.INPUT_LABEL_OVERRIDES),
    the inputs the reference sets besides them (BASE_STATED_INPUTS), inputs
    the engine has renamed and inputs the reference leaves out
    (policybench.scenarios.PE_INPUT_RENAMES, PE_DROPPED_INPUTS), each in the
    board's and the v2-pilot prompt's wording. Dropped facts are shown but are
    not engine inputs. A label may name facts of another country; a lookup
    reads only the one its engine has."""
    from policybench.prompts import INPUT_LABEL_OVERRIDES
    from policybench.scenarios import PE_DROPPED_INPUTS, PE_INPUT_RENAMES

    fields = {spec.output_name: spec.value_type for spec in _promptable_specs()}
    dropped = {f for names in PE_DROPPED_INPUTS.values() for f in names}
    for source in (
        "age",
        *BASE_STATED_INPUTS,
        *INPUT_LABEL_OVERRIDES,
        *PE_INPUT_RENAMES,
        *dropped,
    ):
        fields.setdefault(source, "int" if source == "age" else "float")
    labels: dict[str, set[tuple[str, bool]]] = {}
    for source, value_type in fields.items():
        target = (PE_INPUT_RENAMES.get(source, source), source in dropped)
        keys = {_label_key(label) for label in rendered_labels(source, value_type)}
        if source in PE_INPUT_RENAMES or source in dropped:
            keys.add(_label_key(source))
        for key in keys:
            labels.setdefault(key, set()).add(target)
    for label, name in PROMPT_EXTRA_LABELS.items():
        labels.setdefault(_label_key(label), set()).add((name, False))
    return {key: frozenset(targets) for key, targets in labels.items()}


def read_fact_name(
    name: str, registry: Mapping[str, VariableInfo], features: frozenset
) -> tuple[str | None, str | None]:
    """A fact's engine variable under the labels feature (any label the
    prompt shows it under, when exactly one fact it may name is the engine's)
    and then the names feature (spaces for underscores). Returns (engine
    name, note) or (None, None)."""
    if LABELS in features:
        found = [
            engine
            for engine, dropped in prompt_labels().get(_label_key(name), ())
            if not dropped and engine in registry
        ]
        if len(found) == 1:
            return found[0], f"read {name!r} as {found[0]}"
    if NAMES in features:
        return resolve_name(name, registry, output_names=False)
    return None, None


def dropped_fact(
    name: str, registry: Mapping[str, VariableInfo], features: frozenset
) -> str | None:
    """Under the labels feature, the input a fact names when the prompt shows
    it but the reference leaves it out (policybench.scenarios.PE_DROPPED_INPUTS:
    no longer an engine input); otherwise None."""
    if LABELS not in features:
        return None
    found = [
        engine
        for engine, dropped in prompt_labels().get(_label_key(name), ())
        if dropped
    ]
    return found[0] if len(found) == 1 else None


def _dropped_note(where: str, name: str, field: str) -> str:
    return (
        f"{where}: {name!r} ({field}) is not an input of this engine; the "
        "benchmark's reference leaves it out too, so it was ignored"
    )


def _set_aliases(v2: dict, people: dict, registry: Mapping[str, VariableInfo]):
    """Set each fact the reference also sets under another name there too
    (policybench.scenarios.PE_INPUT_ALIASES: the SNAP work rules read stated
    usual weekly hours as weekly_hours_worked_before_lsr), unless it is set."""
    from policybench.scenarios import PE_INPUT_ALIASES

    for person, inputs in people.items():
        for source, target in PE_INPUT_ALIASES.items():
            if source in inputs and target in registry and target not in inputs:
                inputs[target] = dict(inputs[source])
                v2["notes"].append(
                    f"people.{person}: also set {target} from {source}, as the "
                    "benchmark's reference does"
                )


def resolve_name(
    name: str, registry: Mapping[str, VariableInfo], output_names: bool
) -> tuple[str | None, str | None]:
    """Tool version 2's reading of a name the engine does not know: the name
    with spaces or hyphens as underscores, or (for outputs) a benchmark output
    key. Returns (engine name, note) or (None, None)."""
    if name in registry:
        return name, None
    written = _LABEL_SEPARATORS.sub("_", name.strip().lower())
    if written in registry:
        return written, f"read {name!r} as {written}"
    if output_names:
        reading = output_reading(name)
        if reading is not None and reading[0] in registry:
            return reading[0], f"{name} is {reading[1]}; computed {reading[0]}"
    return None, None


def _place_misplaced(
    v2: dict,
    normalized: dict,
    situation: dict,
    registry: Mapping[str, VariableInfo],
    period: str,
    problems: list[str],
) -> None:
    """Move each input set on another entity to the one unit that holds the
    people it was set for: a group variable set on a person goes to that
    person's unit (a group left out of the situation becomes one unit of
    everyone, as the engine reads it), a person variable set on a one-person
    unit goes to that person, and a group variable set on another group goes
    to the unit holding all of its members. Anything else stays an error."""
    for where, source_entity, name, value in v2["misplaced"]:
        info = registry[name]
        if source_entity == "person":
            persons = [where.split(".", 1)[1]]
        else:
            group, unit = where.split(".", 1)
            persons = list(normalized.get(group, {}).get(unit, {}).get("members", []))
        target_group = ENTITY_GROUP.get(info.entity, info.entity)
        if info.entity == "person":
            if len(persons) != 1:
                problems.append(
                    f"{where}: {name} is a person variable; set it on one person "
                    "under people."
                )
                continue
            destination = normalized["people"].get(persons[0])
            to = f"people.{persons[0]}"
        else:
            if target_group not in situation and target_group not in normalized:
                normalized[target_group] = {
                    "all": {"members": list(normalized["people"])}
                }
            units = normalized.get(target_group, {})
            holding = [
                unit
                for unit, data in units.items()
                if set(persons) <= set(data.get("members", []))
            ]
            if len(holding) != 1:
                problems.append(
                    f"{where}: {name} is a {info.entity} variable; set it under "
                    f"{target_group} (no single unit there holds "
                    f"{', '.join(persons) or 'its members'})."
                )
                continue
            destination = units[holding[0]]
            to = f"{target_group}.{holding[0]}"
        if destination is None:
            problems.append(f"{where}: {name} has no place to go")
            continue
        normalized_value = _normalize_value(to, name, value, info, period, problems)
        if normalized_value is None:
            continue
        if name in destination and destination[name] != normalized_value:
            problems.append(f"{to}: {name} is set twice with different values")
            continue
        destination[name] = normalized_value
        v2["notes"].append(f"moved {name} from {where} to {to}")


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
    out = {"results": results}
    if "notes" in request:
        out["notes"] = list(request["notes"])
    if request.get("explain"):
        out["explanations"] = {
            name: (
                brief_explanation(
                    explain_variable(system, request, name, simulation_cls)
                )
                if request.get("detail") == "brief"
                else explain_variable(system, request, name, simulation_cls)
            )
            for name in request["explain"]
        }
    return out


BRIEF_INPUTS = 8
BRIEF_PARAMETERS = 5


def brief_explanation(full: dict) -> dict:
    """The concise feature's explanation: the value, the variables it came
    from directly (one level down, the first BRIEF_INPUTS), and the first
    parameters it read with their sources."""
    if "error" in full:
        return full
    steps = full["steps"]
    direct = [
        s.strip() for s in steps[1:] if s.startswith("  ") and not s.startswith("    ")
    ]
    return {
        "value": steps[0].strip() if steps else "",
        "from": direct[:BRIEF_INPUTS],
        "parameters": full["parameters"][:BRIEF_PARAMETERS],
        "more": 'set detail to "full" for the trace',
    }


EXPLAIN_MAX_LINES = 60
EXPLAIN_MAX_DEPTH = 6
EXPLAIN_MAX_PARAMETERS = 15
# Switches every variable has; never part of a reason.
_QUIET_PARAMETERS = ("gov.abolitions.",)


def _trace_value(value) -> Any:
    if hasattr(value, "decode_to_str"):
        value = value.decode_to_str()
    try:
        items = list(value)
    except TypeError:
        return _jsonable(value)
    items = [_jsonable(v) for v in items]
    return items[0] if len(items) == 1 else items


def _all_zero(value) -> bool:
    try:
        return all((not v) if not isinstance(v, str) else False for v in list(value))
    except TypeError:
        return not value


def parameter_sources(system, name: str, limit: int = 2) -> list[dict]:
    """A parameter's cited sources: its own ``reference`` metadata, or the
    nearest ancestor's."""
    node = system.parameters
    chain = [node]
    for part in name.split("."):
        children = getattr(node, "children", None)
        if not isinstance(children, dict) or part not in children:
            break
        node = children[part]
        chain.append(node)
    for node in reversed(chain):
        refs = (getattr(node, "metadata", None) or {}).get("reference")
        if refs:
            refs = refs if isinstance(refs, list) else [refs]
            out = []
            for ref in refs[:limit]:
                if isinstance(ref, dict):
                    out.append({k: ref[k] for k in ("title", "href") if ref.get(k)})
                else:
                    out.append({"href": str(ref)})
            return out
    return []


def explain_variable(system, request: dict, name: str, simulation_cls=None) -> dict:
    """How the engine computed ``name`` for the request's household: the
    computation steps (each variable, its period and value, with its inputs
    indented beneath it; zero-valued branches below the first level left out),
    then the parameters it read, each with its value and cited sources."""
    if simulation_cls is None:
        from policyengine_us import Simulation as simulation_cls
    try:
        simulation = simulation_cls(
            tax_benefit_system=system, situation=copy.deepcopy(request["situation"])
        )
        simulation.trace = True
        simulation.calculate(name, request["period"])
    except Exception as error:
        return {"error": f"{type(error).__name__}: {error}"[:MAX_MESSAGE_CHARS]}

    def find(nodes):
        for node in nodes:
            if node.name == name:
                return node
            hit = find(node.children)
            if hit is not None:
                return hit
        return None

    root = find(simulation.tracer.trees)
    if root is None:
        return {"error": f"no trace for {name}"}
    steps: list[str] = []
    parameters: dict[str, Any] = {}

    def walk(node, depth):
        if len(steps) >= EXPLAIN_MAX_LINES or depth > EXPLAIN_MAX_DEPTH:
            return
        if depth > 1 and _all_zero(node.value):
            return
        steps.append(
            "  " * depth + f"{node.name} ({node.period}) = {_trace_value(node.value)}"
        )
        for parameter in node.parameters:
            if parameter.name.startswith(_QUIET_PARAMETERS):
                continue
            parameters.setdefault(parameter.name, _trace_value(parameter.value))
        for child in node.children:
            walk(child, depth + 1)

    walk(root, 0)
    return {
        "steps": steps,
        "parameters": [
            {"name": key, "value": value, "sources": parameter_sources(system, key)}
            for key, value in list(parameters.items())[:EXPLAIN_MAX_PARAMETERS]
        ],
    }


def _board_upgrade(snapshot: Path) -> dict:
    """A board's last engine_upgrade revision: the engine its references are
    on and the fix modules it pins. The frozen board's is 2.41.0's; a household
    set (scripts/household_set.py) records one."""
    meta = json.loads((snapshot / "reference_outputs.csv.meta.json").read_text())
    revisions = [r for r in meta["revisions"] if r.get("kind") == "engine_upgrade"]
    if not revisions:
        raise SystemExit(f"{snapshot} records no engine_upgrade revision")
    return revisions[-1]


def board_engine(snapshot: Path = SNAPSHOT) -> str:
    """The policyengine-us version a board's references were computed on."""
    return _board_upgrade(snapshot)["engine_version"].removeprefix("policyengine-us ")


def is_household_set(snapshot: Path) -> bool:
    meta = json.loads((snapshot / "reference_outputs.csv.meta.json").read_text())
    return meta.get("board_kind") == "household_set"


def pinned_fix_modules(snapshot: Path = SNAPSHOT) -> list[dict]:
    """The fix modules a board's references were built with, as its sidecar's
    engine_upgrade revision pins them (path and sha256)."""
    return _board_upgrade(snapshot)["fix_modules"]


def board_fix_module_sha256(snapshot: Path = SNAPSHOT) -> str:
    """The pinned latest_final.py: the constant for the frozen board, the
    sidecar's record for a household set."""
    if not is_household_set(snapshot):
        return FIX_MODULE_SHA256
    return _board_upgrade(snapshot)["fix_module"]["sha256"]


def verify_fix_pins(
    fixes_dir: Path = FIX_MODULE.parent, snapshot: Path = SNAPSHOT
) -> None:
    """Every module latest_final.py composes must be the pinned bytes.

    Each pin is checked at its recorded path; a module the reform reads from
    its own directory (the sales tax tables) is also checked there.
    """
    problems = []
    for pin in pinned_fix_modules(snapshot):
        candidates = {ROOT / pin["path"], fixes_dir / pin["module"]}
        for path in sorted(candidates):
            if path.exists() and _sha256(path) != pin["sha256"]:
                problems.append(f"{path} does not match the pinned {pin['sha256']}")
        if not any(path.exists() for path in candidates):
            problems.append(f"{pin['module']} is missing")
    pinned = board_fix_module_sha256(snapshot)
    if _sha256(FIX_MODULE) != pinned:
        problems.append(f"{FIX_MODULE} does not match {pinned}")
    if problems:
        raise SystemExit("; ".join(problems))


def load_fix_reform(path: Path = FIX_MODULE, snapshot: Path = SNAPSHOT):
    if path == FIX_MODULE:
        verify_fix_pins(snapshot=snapshot)
    spec = importlib.util.spec_from_file_location("tool_pilot_latest_final", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.reform


def build_tool_system(
    reform: bool = True, path: Path = FIX_MODULE, snapshot: Path = SNAPSHOT
):
    from policyengine_us import CountryTaxBenefitSystem

    if not reform:
        return CountryTaxBenefitSystem()
    return CountryTaxBenefitSystem(reform=load_fix_reform(path, snapshot))


# How a pool tells its worker the calculator's features: a tuple, which a
# model's JSON arguments can never be, so a model cannot turn on a feature its
# arm does not offer. A pool without features sends the arguments as they are.
CALL_FRAME = "calculate"


def tool_call_frame(features: frozenset, arguments) -> tuple:
    return (CALL_FRAME, tuple(sorted(features)), arguments)


def frame_features(names) -> frozenset:
    """A frame's features, refused (ValueError) unless they are a tuple of
    known feature names with concise only beside explain."""
    if not isinstance(names, tuple) or not all(isinstance(n, str) for n in names):
        raise ValueError("the features must be a tuple of names")
    features = frozenset(names)
    if features - set(TOOL_FEATURES):
        raise ValueError(
            f"unknown tool features {sorted(features - set(TOOL_FEATURES))}"
        )
    if CONCISE in features and EXPLAIN not in features:
        raise ValueError("the concise feature needs explain")
    return features


def worker_request(message, registry) -> tuple[dict | None, dict | None]:
    """A worker's reading of one pool message: a call frame's arguments under
    its features, or anything else as a model's arguments with no features
    (keys such as "__tool_features__" or "__tool_version__" in them are the
    model's, and refused as unknown arguments)."""
    features = frozenset()
    if isinstance(message, tuple) and len(message) == 3 and message[0] == CALL_FRAME:
        try:
            features = frame_features(message[1])
        except ValueError as error:
            return None, {"error": "configuration", "message": str(error)}
        message = message[2]
    return normalize_request(message, registry, features=features)


def _worker_main(conn, fix_path: str, reform: bool, board: str | None = None) -> None:
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    snapshot = Path(board) if board else SNAPSHOT
    system = build_tool_system(reform=reform, path=Path(fix_path), snapshot=snapshot)
    registry = build_registry(system)
    conn.send(("ready", None))
    while True:
        try:
            args = conn.recv()
        except EOFError:
            return
        if args is None:
            return
        request, error = worker_request(args, registry)
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
        worker_target: Callable | None = None,
        acquire_timeout: float | None = None,
        board: Path | None = None,
        tool_version: int = 1,
        tool_features: frozenset | None = None,
    ):
        self._ctx = mp.get_context("spawn")
        self._tool_version = tool_version
        self._tool_features = (
            tool_features
            if tool_features is not None
            else (V2_FEATURES if tool_version == 2 else frozenset())
        )
        self._fix_path = str(fix_path)
        # A worker gets the board only when it is not the frozen one, so a
        # three-argument worker target still starts on the default.
        self._board = None if board is None or board == SNAPSHOT else str(board)
        self._reform = reform
        self._target = worker_target or _worker_main
        self.timeout = timeout
        self.acquire_timeout = (
            WORKER_START_TIMEOUT_SECONDS + timeout
            if acquire_timeout is None
            else acquire_timeout
        )
        self._idle: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self.timeouts = 0
        self.crashes = 0
        self.lost = 0
        starting = [self._start() for _ in range(size)]
        for worker in starting:
            self._idle.put(self._await_ready(worker))

    def _start(self):
        parent, child = self._ctx.Pipe()
        args = (child, self._fix_path, self._reform)
        if self._board is not None:
            args += (self._board,)
        process = self._ctx.Process(target=self._target, args=args, daemon=True)
        process.start()
        return process, parent

    def _await_ready(self, worker):
        """The worker once it reports ready; RuntimeError (worker killed) if it
        does not start, however it fails."""
        process, conn = worker
        try:
            if not conn.poll(WORKER_START_TIMEOUT_SECONDS):
                raise RuntimeError("tool worker did not start")
            status, _ = conn.recv()
            if status != "ready":
                raise RuntimeError(f"tool worker failed to start: {status}")
        except (RuntimeError, EOFError, OSError, ValueError) as error:
            process.kill()
            process.join(timeout=10)
            raise RuntimeError(f"tool worker failed to start: {error}") from error
        return worker

    def counters(self) -> dict:
        with self._lock:
            return {
                "timeouts": self.timeouts,
                "crashes": self.crashes,
                "lost": self.lost,
            }

    def call(self, args) -> tuple[dict, float]:
        started = time.perf_counter()
        try:
            worker = self._idle.get(timeout=self.acquire_timeout)
        except queue.Empty:
            # Infrastructure, not the model: run_household stops the household
            # with a rerunnable status rather than show the model this result.
            return (
                {"error": POOL_UNAVAILABLE, "message": "no tool worker is available"},
                time.perf_counter() - started,
            )
        process, conn = worker
        if self._tool_features:
            args = tool_call_frame(self._tool_features, args)
        try:
            conn.send(args)
            if conn.poll(self.timeout):
                _, result = conn.recv()
                self._idle.put(worker)
                return result, time.perf_counter() - started
            with self._lock:
                self.timeouts += 1
            result = {
                "error": "timeout",
                "message": f"the calculation exceeded {self.timeout:.0f} seconds",
            }
        except (EOFError, BrokenPipeError, OSError, ValueError) as error:
            with self._lock:
                self.crashes += 1
            result = {"error": "engine", "message": f"tool worker failed: {error}"}
        elapsed = time.perf_counter() - started
        process.kill()
        process.join(timeout=10)
        try:
            self._idle.put(self._await_ready(self._start()))
        except RuntimeError:
            with self._lock:
                self.lost += 1
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


def _require_engine(board: Path = SNAPSHOT) -> None:
    version = _versions()["policyengine-us"]
    pinned = board_engine(board)
    if version != pinned:
        where = (
            f"the reference engine of household set {board}"
            if is_household_set(board)
            else "the reference engine of release dashboard-data-20261014"
        )
        raise SystemExit(
            f"policyengine-us {version} is installed; the pilot pins {pinned}, {where}."
        )
