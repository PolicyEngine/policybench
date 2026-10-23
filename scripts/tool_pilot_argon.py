"""Pilot: a board model with a PolicyEngine tool on the board's 100 US households.
Not a board condition. Its results for Gemini 4 Argon, GPT-6 Sol and Claude Opus 5.5
are in the 2026-10-20 note (scripts/tool_pilot_note.py, notes/data/tool_pilot_*).

The model defaults to Gemini 4 Argon, the first one piloted; ``run --model``
takes any board model whose provider has an entry in PROVIDER_KEYS.

The benchmark has one condition, ``no_tools`` (docs/benchmark_card.md,
"Evaluation conditions"). This script stays outside the board pipeline: it
writes only under --out-dir, never touches the run store, the snapshot, the
cache or the dashboard, and labels its rows ``<model>+pe-tool`` (for example
``gemini-4-argon+pe-tool``) so no board export can take them for a board row.

Arms, on the same 100 households (``run --arm`` picks arm 2's tools):
  1. No tools: the model's frozen board predictions (release
     dashboard-data-20261014), read from the snapshot and never re-run.
  2. PolicyEngine tool: the board's prompt and request settings for the model,
     plus a tool notice, the board's answer (``submit_outputs`` for a
     tool-contract model, the JSON reply for a JSON-contract one), and
     ``calculate_household``, which runs the
     reference engine on a situation the model writes as JSON. The reference
     engine is the installed policyengine-us (2.41.0) with the reference
     builder's convention reform, reference_audit/2026-09-28/fixes/latest_final.py
     (reference_audit/2026-10-12-engine-upgrade/scripts/build_references_upgrade.py
     computes every reference on that system). The ``oracle`` subcommand checks
     that the reference situations reproduce every scored reference through it.
     ``--arm web`` offers the provider's own web search in place of the tool,
     and ``--arm web+pe`` offers both; rows are labeled ``<model>+web`` and
     ``<model>+web+pe-tool``. Searches are logged per turn and priced at list
     (SEARCH_USD_PER_1K) on top of their tokens; policybench.org and GitHub are
     blocked where the provider allows it (BLOCKED_DOMAINS), and ``score``
     writes searches.csv with an audit of any that touch the benchmark.

The model writes JSON only. The tool parses it, checks every name against the
engine's variable registry, and passes plain data to policyengine_us.Simulation
in a separate worker process with a per-call timeout. No model-written text is
executed.

Subcommands:
  oracle    reference situations through the tool engine
  run       call the model (needs its provider's key, PROVIDER_KEYS); one JSON
            record per household
  score     both arms through the board's analyze_no_tools on the scored outputs
  diagnose  classify every arm-2 miss
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import decimal
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
import subprocess
import sys
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
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
# engine_upgrade revision pins latest_final.py to this sha256, and
# verify_fix_pins checks it and every module it composes against that revision.
FIX_MODULE_SHA256 = "dbbdd228b99933c6f336af97970821c25c863a18606285e8d6d9ffb3bc9af78e"

MODEL_NAME = "gemini-4-argon"
ARM1_LABEL = MODEL_NAME
ARM2_LABEL = "gemini-4-argon+pe-tool"
# The API key each provider's models need, by litellm model-id prefix.
PROVIDER_KEYS = {
    "gemini/": "GEMINI_API_KEY",
    "gpt-": "OPENAI_API_KEY",
    "claude-": "ANTHROPIC_API_KEY",
}
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
# Infrastructure failures a resume reruns. Every other status is the model's
# own outcome and stands, so no household is redrawn until it succeeds.
RERUNNABLE_STATUSES = frozenset({"provider_error", "budget_stop", "harness_error"})
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

TOOL_NOTICE = (
    "\n\nYou also have a `calculate_household` function. It runs PolicyEngine US "
    "(policyengine-us 2.41.0), an open-source rules engine for US federal and "
    "state taxes and benefits, on a household situation you build from the facts "
    "above. You may call it in up to 8 turns. Then call `submit_outputs` exactly "
    "once with your final answers, as instructed above."
)

# The notice for a JSON-contract model, whose API refuses a forced tool: the
# same tool, and the board's JSON reply in place of submit_outputs.
JSON_TOOL_NOTICE = (
    "\n\nYou also have a `calculate_household` function. It runs PolicyEngine US "
    "(policyengine-us 2.41.0), an open-source rules engine for US federal and "
    "state taxes and benefits, on a household situation you build from the facts "
    "above. You may call it in up to 8 turns. Then give your final answers as the "
    "single JSON object described above."
)

# The arms ``run --arm`` takes. "pe" is arm 2 as run on 2026-10-14 and
# 2026-10-15. "web" swaps the PolicyEngine tool for the provider's own web
# search, and "web+pe" offers both. "none" offers neither: its first request is
# the board's own no-tools request (the forced answer function, or the JSON reply
# with no tools), so a prompt version other than the board's has its own
# no-tools baseline. Repairs, retries and truncation then follow this pilot's
# loop, not the board's; they matter only when a first answer does not parse.
ARMS = ("none", "pe", "web", "web+pe", "pe2", "pe3")
ARM_SUFFIX = {
    "none": "+no-tools",
    "pe": "+pe-tool",
    "web": "+web",
    "web+pe": "+web+pe-tool",
    "pe2": "+pe-tool-v2",
    "pe3": "+pe-tool-v3",
}
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


def arm_suffix(arm: str) -> str:
    if arm in ARM_SUFFIX:
        return ARM_SUFFIX[arm]
    features = arm_features(arm)
    return f"+pe-tool[{'+'.join(f for f in TOOL_FEATURES if f in features)}]"


TOOL_NOTICE_V2 = (
    "\n\nYou also have a `calculate_household` function. It runs PolicyEngine US "
    "(policyengine-us 2.41.0), an open-source rules engine for US federal and "
    "state taxes and benefits, on a household situation you build from the facts "
    "above. The facts above are labeled with its variable names, written with "
    "spaces; it accepts them as written, and it accepts the output keys you are "
    "asked for. Set every listed fact. Its result says which names it read, which "
    "inputs it moved to the entity they belong to, and which inputs replace a "
    "formula; ask it to `explain` up to three variables to see how it computed "
    "them, with the parameters and laws it used. You may call it in up to 8 "
    "turns. Then call `submit_outputs` exactly once with your final answers, as "
    "instructed above."
)
JSON_TOOL_NOTICE_V2 = TOOL_NOTICE_V2.replace(
    "Then call `submit_outputs` exactly once with your final answers, as "
    "instructed above.",
    "Then give your final answers as the single JSON object described above.",
)


def _listing(items: list[str]) -> str:
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + ", and " + items[-1]


def compose_tool_notice(features: frozenset, tool_contract: bool) -> str:
    """The calculator notice for a set of features: the opening, a sentence
    per feature, then the turn limit and the answer instruction. No feature
    gives TOOL_NOTICE and the version 2 features TOOL_NOTICE_V2, as those arms
    ran. TOOL_NOTICE_V2 says the facts are labeled with the engine's variable
    names, which holds for most facts but not those the prompt labels in words
    ("gross wages and salaries"); every other set says only what it reads."""
    if not features:
        return TOOL_NOTICE if tool_contract else JSON_TOOL_NOTICE
    if features == V2_FEATURES:
        return TOOL_NOTICE_V2 if tool_contract else JSON_TOOL_NOTICE_V2
    what = (
        "household you describe"
        if FLAT in features
        else "household situation you build"
    )
    text = (
        "\n\nYou also have a `calculate_household` function. It runs PolicyEngine US "
        "(policyengine-us 2.41.0), an open-source rules engine for US federal and "
        f"state taxes and benefits, on a {what} from the facts above."
    )
    if FLAT in features:
        text += (
            " Describe it as `household`: each person with their role (head, spouse "
            "or dependent) and facts, and the facts about the household as a "
            "whole; it builds the household's units as the facts imply."
        )
    if LABELS in features and NAMES in features:
        text += (
            " It accepts the facts above under the labels they have there, its "
            "variable names written with spaces, and the output keys you are asked "
            "for. Set every listed fact."
        )
    elif LABELS in features:
        text += (
            " It accepts the facts above under the labels they have there. Set "
            "every listed fact."
        )
    elif NAMES in features:
        text += (
            " It accepts its variable names written with spaces, and the output "
            "keys you are asked for. Set every listed fact."
        )
    notes = []
    if NAMES in features or LABELS in features:
        notes.append("which names it read")
    if PLACEMENT in features:
        notes.append("which inputs it moved to the entity they belong to")
    if OVERRIDES in features:
        notes.append("which inputs replace a formula")
    explain = ""
    if EXPLAIN in features:
        explain = (
            "ask it to `explain` up to three variables to see in brief how it "
            "computed them, with the parameters and laws it used, or every step "
            'with `detail` set to "full"'
            if CONCISE in features
            else "ask it to `explain` up to three variables to see how it computed "
            "them, with the parameters and laws it used"
        )
    if notes and explain:
        text += f" Its result says {_listing(notes)}; {explain}."
    elif notes:
        text += f" Its result says {_listing(notes)}."
    elif explain:
        text += f" You may {explain}."
    text += " You may call it in up to 8 turns. "
    text += (
        "Then call `submit_outputs` exactly once with your final answers, as "
        "instructed above."
        if tool_contract
        else "Then give your final answers as the single JSON object described above."
    )
    return text


# The engine version the notices and the tool description state: the board's
# (set by command_run), so a household set on a newer engine says so. The
# frozen board's 2.41.0 leaves every text byte for byte as before.
_STATED_ENGINE = {"version": REFERENCE_ENGINE}


def set_stated_engine(version: str) -> None:
    _STATED_ENGINE["version"] = version


def engine_text(text: str) -> str:
    return text.replace(
        f"policyengine-us {REFERENCE_ENGINE}",
        f"policyengine-us {_STATED_ENGINE['version']}",
    )


# A web arm's request timeout. A search-heavy turn can outlast the board's
# (300 s for Gemini 4 Argon, the harness default for its card; its web-only arm
# never finished scenario_005 within it in six attempts on 2026-10-21), so the
# web arms allow this much. A timed-out web request is not retried: three
# 900 s attempts would hold a worker for 45 minutes, so the household ends as
# provider_error and a resume pass reruns it.
WEB_REQUEST_TIMEOUT_SECONDS = 900

_CALCULATE_OPENING = "You also have a `calculate_household` function."
WEB_SENTENCE = "You also have web search, which searches the public web."
WEB_NOTICE = (
    "\n\n" + WEB_SENTENCE + " Then call `submit_outputs` exactly once with your "
    "final answers, as instructed above."
)
JSON_WEB_NOTICE = (
    "\n\n" + WEB_SENTENCE + " Then give your final answers as the single JSON "
    "object described above."
)
# The PE notice with web search named in its opening sentence; the rest of it,
# the tool's description and the turn cap, is unchanged.
WEB_TOOL_NOTICE, JSON_WEB_TOOL_NOTICE = (
    notice.replace(
        _CALCULATE_OPENING,
        "You also have web search, which searches the public web, and a "
        "`calculate_household` function.",
    )
    for notice in (TOOL_NOTICE, JSON_TOOL_NOTICE)
)

# Prompt versions ``run --prompt`` takes. "v1" is the board's prompt. "v2-pilot"
# is the board's prompt with the four output definitions that name PolicyEngine
# (Medicaid, CHIP, free and reduced-price school meals; d1705) rewritten in
# neutral terms. It is a pilot stand-in for the v2 prompts, not the v2 board
# wording. Each rewrite states the convention the reference follows where the
# law alone would not settle it, read from policyengine-us 2.41.0, which the
# convention reform leaves untouched for these outputs:
# - is_in_k12_school treats everyone aged 5 to 17 as a K-12 student, and
#   school_meal_net_subsidy is zero without one.
# - school_meal_tier is free at or under 130% of poverty, with categorical
#   eligibility, in a universal-free-meals state (CA, CO, MA, ME, MI, MN, NM,
#   NY and VT in 2026), or where the state pays the reduced-price copay (NC);
#   reduced price up to 185%. Both parameters describe breakfast and lunch
#   together (state_universal_free_meals: "free breakfast and lunch to all
#   students"), so the wording says so: a breakfast-only program is not free
#   meals here.
# - is_chip_eligible_child excludes anyone Medicaid-eligible, and chip_category
#   includes CHIP coverage of pregnant women.
# - is_medicaid_eligible counts medicaid_category's groups (children, adults,
#   parents, pregnancy, SSI, senior or disabled, medically needy, buy-in and
#   two waivers), not the Medicare Savings Programs, which are separate
#   (gov/hhs/medicare/savings_programs). A first wording, "in any eligibility
#   group", led GPT-6 Sol to count QI as Medicaid in the 2026-10-21 trial.
PROMPT_VERSIONS = ("v1", "v2-pilot")
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
        "Table",
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
        "liability from the section 1 tax rate schedules, not the Tax Table",
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
        "{who}; include Idaho's $10 permanent building fund tax where it applies",
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
        "limits use the 2026 HHS poverty guidelines from October 2026.",
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

# What a JSON-contract web arm hears once its search-only and calculation turns
# reach the cap. Its API takes no forced answer, so this is the only stop short
# of MAX_TOTAL_TURNS.
JSON_SEARCH_CAP_TEXT = (
    "You have used all {cap} tool turns. Reply now with your final answers as "
    "the JSON object described above."
)

# Max (2026-10-21): tell the web arms not to look for the answer keys.
BENCHMARK_SEARCH_RULE = (
    " Do not search for PolicyBench, the benchmark these questions come from, or "
    "for its published answers, and do not use any PolicyBench page, code or "
    "data you come across."
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


def v2_pilot_strings(value):
    """Every string in a tool schema, rewritten as v2_pilot_text does."""
    if isinstance(value, str):
        return v2_pilot_text(value)
    if isinstance(value, dict):
        return {k: v2_pilot_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [v2_pilot_strings(v) for v in value]
    return value


def prompt_wording_sha256(profile: "ModelProfile") -> str | None:
    """A hash of the v2-pilot rewrites a profile sends, so a resume cannot
    add households under different wording; None for the board's own v1."""
    if profile.prompt_version == "v1":
        return None
    wording = [
        [pattern.pattern, text]
        for pattern, text in (*V2_PILOT_DEFINITIONS, *V2_PILOT_CONVENTIONS)
    ]
    return hashlib.sha256(json.dumps(wording).encode()).hexdigest()


def refuse_policyengine(label: str, value) -> None:
    """A v2-pilot guard: no board text the model sees may name PolicyEngine."""
    text = value if isinstance(value, str) else json.dumps(value)
    if "policyengine" in text.lower():
        found = re.search(r".{0,60}policyengine.{0,60}", text, re.IGNORECASE)
        raise ValueError(
            f"the v2-pilot {label} still names PolicyEngine: {found.group(0)!r}"
        )


# Every provider that can block domains blocks these. policybench.org and
# GitHub host the benchmark's prompts and references, and GitHub also the
# reference engine's source. OpenAI's filter takes whole domains only (it
# refuses "github.com/PolicyEngine/policybench"), so all of GitHub is blocked,
# for both providers that filter. The Gemini API's search tool takes no domain
# list (it refuses excludeDomains), so its queries are audited instead.
BLOCKED_DOMAINS = ("policybench.org", "github.com", "githubusercontent.com")
# Text that marks a search or result as reaching the reference engine itself.
REFERENCE_ENGINE_MARKERS = ("policyengine",)
# Dynamic filtering: Claude filters results in code before they reach its
# context (platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool).
ANTHROPIC_WEB_SEARCH_TOOL = "web_search_20260209"
# List prices per 1,000 searches, from each provider's pricing page on
# 2026-10-20. OpenAI bills each web_search_call ("$10.00 / 1k calls");
# Anthropic each search ("$10 per 1,000 searches"); Google each query a Gemini
# 3 or later model runs ("$14 per 1,000 requests", after 5,000 free a month
# shared across those models, which this price ignores).
SEARCH_USD_PER_1K = {"openai": 10.0, "anthropic": 10.0, "gemini": 14.0}
# Asks the Responses API for each search's result URLs.
OPENAI_SEARCH_SOURCES = "web_search_call.action.sources"
# Times a JSON-contract reply that searched but gave no answer is sent back
# as it is, Anthropic's continuation for a paused server-tool turn.
MAX_PAUSE_CONTINUATIONS = 3
# The litellm whose Gemini search-tool handling allow_gemini_search_with_functions
# was written against.
GEMINI_SEARCH_PATCH_LITELLM = "1.88.1"

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
    'spouse or dependent --, `facts`, for example {"age": 40, "employment '
    'income": 30000}, and optionally `name`, by default the role, numbered for '
    "dependents), and `household_facts` (facts about the "
    "household as a whole: its tax unit, family, SPM unit or home). The head "
    "and spouse are one couple and everyone else is on their own; everyone "
    "shares one tax unit, family, SPM unit and household. A fact is a value "
    'for `period`, or {period: value} with a period such as "2026" or '
    '"2026-01". Facts you do not give take the engine\'s defaults. `variables` '
    'lists the variables to compute for `period` (default "2026"). Each '
    "result gives the variable's entity, label and value for each member of "
    "that entity; a monthly variable computed for a year is summed over its "
    "months."
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
                    "An input set on the wrong entity is moved to the one unit it "
                    "belongs to."
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
                    "(every step)."
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
    from policybench.scenarios import (
        PE_INPUT_ALIASES,
        PE_INPUT_RENAMES,
        get_promptable_input_specs,
    )

    names = {spec.source_name for spec in get_promptable_input_specs()}
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
            args.get("household"), registry, problems, v2
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

    detail = "full"
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
        request["detail"] = detail
    return request, None


FLAT_ROLES = ("head", "spouse", "dependent")


def flat_situation(household, registry, problems: list[str], v2: dict | None):
    """The flat feature's household -- state, people with role and facts, and
    household facts -- as a situation, with the units the benchmark's own
    reference situations have (policybench.scenarios.Scenario.to_pe_household):
    the head and spouse one marital unit and everyone else alone, and one tax
    unit, SPM unit, family and household holding everyone. A household fact
    goes to the unit of its variable's entity. A person given no name is named
    by role (head, spouse, dependent_1, ...). Returns None after recording
    problems."""
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
    dependents = 0
    for index, person in enumerate(people):
        if not isinstance(person, dict):
            problems.append(
                f"people[{index}] must be an object with name, role and facts"
            )
            continue
        name, role, facts = (
            person.get("name"),
            person.get("role"),
            person.get("facts", {}),
        )
        if role not in FLAT_ROLES:
            problems.append(
                f"people[{index}].role must be one of {', '.join(FLAT_ROLES)}"
            )
            continue
        if role == "dependent":
            dependents += 1
        if name is None:
            name = role if role != "dependent" else f"dependent_{dependents}"
            if v2 is not None:
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
        facts.setdefault("is_tax_unit_head", role == "head")
        facts.setdefault("is_tax_unit_spouse", role == "spouse")
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
        resolved = name
        if isinstance(name, str) and name not in registry and v2 is not None:
            resolved, note = read_fact_name(name, registry, v2["features"])
            if resolved is not None:
                v2["notes"].append(f"household_facts: {note}")
        if not isinstance(resolved, str) or resolved not in registry:
            problems.append(
                f"household_facts: unknown variable {name!r}."
                + (_suggest(name, registry) if isinstance(name, str) else "")
            )
            continue
        entity = registry[resolved].entity
        if entity == "person":
            # As placement moves a person variable off a one-person unit: only
            # a household of one says whose fact it is.
            if v2 is not None and PLACEMENT in v2["features"] and len(everyone) == 1:
                facts_of = situation["people"][everyone[0]]
                if resolved in facts_of and facts_of[resolved] != value:
                    problems.append(
                        f"household_facts: {resolved} is also set for "
                        f"{everyone[0]} with a different value"
                    )
                    continue
                facts_of[resolved] = value
                v2["notes"].append(
                    f"household_facts: moved {resolved}, a person's fact, to "
                    f"{everyone[0]}"
                )
                continue
            problems.append(
                f"household_facts: {resolved} is a person's fact; give it under "
                "the person whose facts list it"
            )
            continue
        unit_of[entity][resolved] = value
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


@functools.lru_cache(maxsize=1)
def prompt_labels() -> dict[str, str]:
    """The labels the prompts give facts in words, keyed by _label_key, as the
    engine names the facts (policybench.scenarios.PE_INPUT_RENAMES applied):
    the board's labels and the v2-pilot prompt's relabelings. A label two facts
    share is left out."""
    from policybench.prompts import INPUT_LABEL_OVERRIDES
    from policybench.scenarios import PE_INPUT_RENAMES

    labels: dict[str, str] = {}
    shared = set()
    for source, label in {**INPUT_LABEL_OVERRIDES, **v2_pilot_labels()}.items():
        key = _label_key(label)
        name = PE_INPUT_RENAMES.get(source, source)
        if key in labels and labels[key] != name:
            shared.add(key)
        labels[key] = name
    for source, name in PE_INPUT_RENAMES.items():
        labels.setdefault(_label_key(source), name)
    return {key: name for key, name in labels.items() if key not in shared}


def v2_pilot_labels() -> dict[str, str]:
    """The facts the v2-pilot prompt relabels (a V2_PILOT_CONVENTIONS rewrite
    of "<name with spaces>: " to "<new label>: "), by input name."""
    relabeled = {}
    for pattern, replacement in V2_PILOT_CONVENTIONS:
        old = pattern.pattern
        if pattern.groups or not old.endswith(": ") or not replacement.endswith(": "):
            continue
        relabeled[old[:-2].replace(" ", "_")] = replacement[:-2]
    return relabeled


def read_fact_name(
    name: str, registry: Mapping[str, VariableInfo], features: frozenset
) -> tuple[str | None, str | None]:
    """A fact's engine variable under the labels feature (the label the prompt
    gives it) and then the names feature (spaces for underscores). Returns
    (engine name, note) or (None, None)."""
    if LABELS in features:
        labeled = prompt_labels().get(_label_key(name))
        if labeled is not None and labeled in registry:
            return labeled, f"read {name!r} as {labeled}"
    if NAMES in features:
        return resolve_name(name, registry, output_names=False)
    return None, None


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
    from directly (one level down, zero-valued ones left out), and the first
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
        "more": 'set detail to "full" for every step',
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
        features = frozenset()
        if isinstance(args, dict) and "__tool_features__" in args:
            features = frozenset(args.get("__tool_features__") or ())
            args = args.get("arguments")
        elif isinstance(args, dict) and args.get("__tool_version__") == 2:
            features, args = V2_FEATURES, args.get("arguments")
        request, error = normalize_request(args, registry, features=features)
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
        if self._tool_features == V2_FEATURES:
            args = {"__tool_version__": 2, "arguments": args}
        elif self._tool_features:
            args = {
                "__tool_features__": sorted(self._tool_features),
                "arguments": args,
            }
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


@dataclass(frozen=True)
class ModelProfile:
    """How the board sends one model, and how its tool arm answers.

    ``api`` follows the board: the Responses API for GPT-5 and GPT-6 models
    (``_uses_responses_api``), chat completions otherwise. ``contract`` is the
    model card's answer contract: "tool" answers through the forced
    ``submit_outputs`` function; "json" answers in the board's JSON reply,
    for models whose API refuses a forced tool (the card says so for Claude
    Opus 5.5), and offers ``calculate_household`` under tool_choice auto.
    """

    name: str
    model_id: str
    api: str
    contract: str
    arm: str = "pe"
    prompt_version: str = "v1"
    benchmark_search_rule: bool = False

    @property
    def notice(self) -> str:
        tool = self.contract == "tool"
        if self.arm == "none":
            return ""
        if self.arm == "web":
            notice = WEB_NOTICE if tool else JSON_WEB_NOTICE
        elif self.arm == "web+pe":
            notice = WEB_TOOL_NOTICE if tool else JSON_WEB_TOOL_NOTICE
        elif self.arm == "pe2":
            return engine_text(TOOL_NOTICE_V2 if tool else JSON_TOOL_NOTICE_V2)
        elif self.arm != "pe" and arm_features(self.arm) is not None:
            return engine_text(compose_tool_notice(arm_features(self.arm), tool))
        else:
            return engine_text(TOOL_NOTICE if tool else JSON_TOOL_NOTICE)
        return engine_text(notice) + (
            BENCHMARK_SEARCH_RULE if self.benchmark_search_rule else ""
        )

    @property
    def uses_calculator(self) -> bool:
        return arm_features(self.arm) is not None

    @property
    def tool_features(self) -> frozenset:
        return arm_features(self.arm) or frozenset()

    @property
    def tool_version(self) -> int:
        return 2 if self.tool_features == V2_FEATURES else 1

    @property
    def uses_web(self) -> bool:
        return self.arm in ("web", "web+pe")

    @property
    def provider(self) -> str:
        return provider_family(self.model_id)

    @property
    def arm1_label(self) -> str:
        return self.name

    @property
    def arm2_label(self) -> str:
        version = "" if self.prompt_version == "v1" else f"@{self.prompt_version}"
        rule = "+no-benchmark-search" if self.benchmark_search_rule else ""
        return f"{self.name}{arm_suffix(self.arm)}{version}{rule}"


def provider_family(model_id: str) -> str:
    for prefix, family in (
        ("gemini/", "gemini"),
        ("claude-", "anthropic"),
        ("gpt-", "openai"),
    ):
        if model_id.startswith(prefix):
            return family
    raise SystemExit(f"no provider is known for {model_id}")


def model_profile(
    name: str = MODEL_NAME,
    arm: str = "pe",
    prompt_version: str = "v1",
    benchmark_search_rule: bool = False,
) -> ModelProfile:
    from policybench.config import MODELS
    from policybench.eval_no_tools import (
        _answer_contract_for_model,
        _uses_responses_api,
    )

    if arm not in ARMS and arm_features(arm) is None:
        raise SystemExit(
            f"unknown arm {arm!r}; the arms are {', '.join(ARMS)}, or pe: plus "
            f"calculator features joined by + ({', '.join(TOOL_FEATURES)})"
        )
    if prompt_version not in PROMPT_VERSIONS:
        raise SystemExit(
            f"unknown prompt {prompt_version!r}; the prompts are "
            f"{', '.join(PROMPT_VERSIONS)}"
        )
    if benchmark_search_rule and arm not in ("web", "web+pe"):
        raise SystemExit("the benchmark-search rule needs a web arm")
    model_id = MODELS[name]
    return ModelProfile(
        name=name,
        model_id=model_id,
        api="responses" if _uses_responses_api(model_id) else "chat",
        contract=_answer_contract_for_model(model_id),
        arm=arm,
        prompt_version=prompt_version,
        benchmark_search_rule=benchmark_search_rule,
    )


def web_search_tool(profile: ModelProfile) -> dict:
    """The provider's own web search, in the shape its API takes."""
    if profile.provider == "openai" and profile.api == "responses":
        return {
            "type": "web_search",
            "filters": {"blocked_domains": list(BLOCKED_DOMAINS)},
        }
    if profile.provider == "anthropic":
        return {
            "type": ANTHROPIC_WEB_SEARCH_TOOL,
            "name": "web_search",
            "blocked_domains": list(BLOCKED_DOMAINS),
        }
    if profile.provider == "gemini":
        return {"googleSearch": {}}
    raise SystemExit(f"no web search tool is wired for {profile.model_id}")


def allow_gemini_search_with_functions() -> None:
    """Keep Gemini's search tool beside function tools in litellm.

    litellm 1.88.1 drops googleSearch from any request that also declares
    functions unless ``include_server_side_tool_invocations`` is set. It reads
    that flag only among the mapped OpenAI parameters, and a ``completion``
    keyword reaches it later, as a provider extra, after the search tool is
    gone. Gemini 3 and 4 models take both together with the flag
    (ai.google.dev/gemini-api/docs/tool-combination), and the web arms always
    send it, so both of litellm's drops are skipped. Refuses any other litellm,
    whose code this was not checked against.
    """
    version = importlib.metadata.version("litellm")
    if version != GEMINI_SEARCH_PATCH_LITELLM:
        raise SystemExit(
            f"litellm {version} is installed; the Gemini search patch was "
            f"checked against {GEMINI_SEARCH_PATCH_LITELLM} only"
        )
    from litellm.llms.vertex_ai.gemini.vertex_and_google_ai_studio_gemini import (
        VertexGeminiConfig,
    )

    def keep_search_tools(
        gtool_func_declarations,
        googleSearch,
        googleSearchRetrieval,
        enterpriseWebSearch,
        urlContext,
        optional_params,
    ):
        return googleSearch, googleSearchRetrieval, enterpriseWebSearch, urlContext

    VertexGeminiConfig._resolve_search_tool_conflict = staticmethod(keep_search_tools)
    VertexGeminiConfig._drop_search_tools_mixed_with_functions = classmethod(
        lambda cls, optional_params: None
    )


def build_initial_request(
    scenario, variables: list[str], profile: ModelProfile | None = None
) -> tuple[str, dict]:
    """The board's prompt and request settings for this household, with the
    tool notice appended and the calculate tool added."""
    from policybench.eval_no_tools import (
        _chat_completion_request_kwargs,
        _completion_budget_ceiling,
        _responses_request_kwargs,
    )

    profile = profile or model_profile()
    if profile.api == "responses":
        messages, kwargs = _responses_request_kwargs(
            scenario, variables, profile.model_id
        )
        kwargs = {k: v for k, v in kwargs.items() if k not in {"input"}}
    else:
        messages, kwargs = _chat_completion_request_kwargs(
            scenario, variables, profile.model_id
        )
        kwargs = {k: v for k, v in kwargs.items() if k not in {"messages", "caching"}}
    board_prompt = messages[0]["content"]
    kwargs.pop("tools", None)
    kwargs.pop("tool_choice", None)
    kwargs["_board_prompt_sha256"] = hashlib.sha256(board_prompt.encode()).hexdigest()
    kwargs["_budget_ceiling"] = _completion_budget_ceiling(profile.model_id)
    kwargs["_answer_tool"] = (
        answer_tool_for(profile, variables, scenario.country)
        if profile.contract == "tool"
        else None
    )
    if profile.prompt_version == "v2-pilot":
        board_prompt = v2_pilot_text(board_prompt)
        refuse_policyengine("prompt", board_prompt)
        refuse_policyengine("request", {k: v for k, v in kwargs.items() if k[0] != "_"})
    kwargs["_sent_board_prompt_sha256"] = hashlib.sha256(
        board_prompt.encode()
    ).hexdigest()
    return board_prompt + profile.notice, kwargs


def answer_tool_for(profile: ModelProfile, variables: list[str], country: str) -> dict:
    """The board's submit_outputs tool, in the profile's prompt version."""
    from policybench.eval_no_tools import _build_answer_tool

    tool = _build_answer_tool(variables, country=country)
    if profile.prompt_version == "v2-pilot":
        tool = v2_pilot_strings(tool)
        refuse_policyengine("answer tool", tool)
    return tool


def forced_answer_choice(profile: ModelProfile | None = None) -> dict:
    from policybench.eval_no_tools import ANSWER_FUNCTION_NAME, _tool_choice_for

    if profile is not None and profile.api == "responses":
        return {"type": "function", "name": ANSWER_FUNCTION_NAME}
    return _tool_choice_for(ANSWER_FUNCTION_NAME)


def _responses_tool(chat_tool: dict) -> dict:
    """A chat-completions function tool in the Responses API's flat shape."""
    function = chat_tool["function"]
    return {
        "type": "function",
        "name": function["name"],
        "description": function["description"],
        "parameters": function["parameters"],
    }


@dataclass
class Call:
    id: str
    name: str | None
    arguments: Any


@dataclass
class Turn:
    response: Any
    content: str | None
    calls: list[Call]
    finish_reason: str | None
    reasoning_content: str | None = None
    has_thought_signature: bool = False
    # Calls the provider ran itself (Anthropic's server tools: web search and
    # the code execution its dynamic filtering runs in). They need no result.
    server_calls: list[dict] = field(default_factory=list)
    # Server calls with no result in the same response: deferred beside a
    # client call, or left by a paused turn. Only tool results may follow them.
    unfinished_server_calls: list[str] = field(default_factory=list)


CACHE_BREAKPOINT = {"type": "ephemeral"}


def _with_cache_breakpoint(message: dict) -> dict:
    """The message with an Anthropic prompt-cache breakpoint at its end.

    Anthropic caches a prefix only at a marked block, and litellm carries the
    mark from a text block or from a tool message. Gemini and OpenAI cache
    repeated prefixes on their own.
    """
    message = dict(message)
    if message.get("role") == "tool":
        message["cache_control"] = CACHE_BREAKPOINT
    elif isinstance(message.get("content"), str):
        message["content"] = [
            {
                "type": "text",
                "text": message["content"],
                "cache_control": CACHE_BREAKPOINT,
            }
        ]
    return message


# Where litellm keeps Anthropic server tool results on a message: web search
# and web fetch results, and code execution results.
SERVER_RESULT_KEYS = ("web_search_results", "tool_results")


def is_server_call(call_id) -> bool:
    """An Anthropic server tool's call, which litellm lists among the tool
    calls; the API runs it and returns its result in the same response."""
    return str(call_id or "").startswith("srvtoolu_")


class ChatConversation:
    """A chat-completions conversation: one growing message list.

    With ``cache_breakpoint`` each request marks its last message, so a turn
    reads the conversation so far from Anthropic's prompt cache. The stored
    messages stay unmarked, which keeps one breakpoint per request.
    """

    budget_key = "max_completion_tokens"

    def __init__(self, prompt: str, cache_breakpoint: bool = False):
        self.messages: list[dict] = [{"role": "user", "content": prompt}]
        self.cache_breakpoint = cache_breakpoint

    def request_kwargs(self, base: dict, tools: list[dict], tool_choice) -> dict:
        kwargs = dict(base)
        messages = self.messages
        # A continuation ends on the assistant's own message, which goes back
        # without a mark: marking turns its content into a list, and litellm
        # then rebuilds the message in another block order.
        if self.cache_breakpoint and messages[-1].get("role") != "assistant":
            messages = [*messages[:-1], _with_cache_breakpoint(messages[-1])]
        kwargs["messages"] = messages
        # A request with no tools sends no tools key at all, as the board's
        # JSON-contract request does.
        if tools:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if self.budget_key not in kwargs and "max_tokens" in kwargs:
            self.budget_key = "max_tokens"
        return kwargs

    def read(self, response, budget) -> Turn:
        from policybench.eval_no_tools import _response_finish_reason

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ProviderEmpty("response has no choices")
        message = choices[0].message
        calls, server_calls = [], []
        for c in _tool_calls(message):
            call = Call(_call_id(c), _call_name(c), _call_arguments(c))
            if is_server_call(call.id):
                server_calls.append(asdict(call))
            else:
                calls.append(call)
        fields = getattr(message, "provider_specific_fields", None)
        finished = {
            _field(block, "tool_use_id")
            for key in SERVER_RESULT_KEYS
            for block in (
                (fields or {}).get(key) or [] if isinstance(fields, dict) else []
            )
        }
        return Turn(
            response=response,
            content=getattr(message, "content", None),
            calls=calls,
            finish_reason=_response_finish_reason(response, responses_api=False),
            reasoning_content=getattr(message, "reasoning_content", None),
            has_thought_signature=_has_thought_signature(message),
            server_calls=server_calls,
            unfinished_server_calls=[
                c["id"] for c in server_calls if c["id"] not in finished
            ],
        )

    def add_assistant(self, turn: Turn) -> None:
        message = _message_dict(turn.response.choices[0].message)
        self._attach_deferred_results(message)
        self.messages.append(message)

    def _attach_deferred_results(self, message: dict) -> None:
        """Move a deferred server call's result onto the message that made it.

        When Claude calls a server tool beside a client tool, the API runs the
        server tool on the next request, and that response begins with its
        result, without the call. litellm 1.88.1 re-sends a server result only
        beside its call in the same message, so left in place the result drops
        out of later requests, and the API refuses the call that lacks it (a
        live probe got that 400 on the third request). The result joins its
        call, the only place litellm sends it from.
        """
        fields = message.get("provider_specific_fields")
        if not isinstance(fields, dict):
            return
        own = {_call_id(c) for c in message.get("tool_calls") or []}
        for key in SERVER_RESULT_KEYS:
            kept = []
            for block in fields.get(key) or []:
                call_id = _field(block, "tool_use_id")
                earlier = (
                    None if not call_id or call_id in own else self._caller(call_id)
                )
                if earlier is None:
                    kept.append(block)
                    continue
                earlier_fields = earlier.setdefault("provider_specific_fields", {})
                earlier_fields[key] = [*(earlier_fields.get(key) or []), block]
            if key in fields:
                fields[key] = kept

    def _caller(self, call_id: str) -> dict | None:
        for message in reversed(self.messages):
            if message.get("role") == "assistant" and any(
                _call_id(c) == call_id for c in message.get("tool_calls") or []
            ):
                return message
        return None

    def add_tool_result(self, call: Call, result: dict) -> None:
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.name or "unknown",
                "content": json.dumps(result),
            }
        )

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def transcript(self) -> list:
        return self.messages


class ResponsesConversation:
    """A Responses API conversation, chained by previous_response_id.

    The provider keeps each response, its reasoning included, so a turn sends
    only what is new: the function call outputs and any user text.
    """

    budget_key = "max_output_tokens"

    def __init__(self, prompt: str):
        self.prompt = prompt
        self.previous_response_id: str | None = None
        self.pending: list[dict] = []
        self.log: list[dict] = []

    def request_kwargs(self, base: dict, tools: list[dict], tool_choice) -> dict:
        kwargs = dict(base)
        kwargs["tools"] = [
            _responses_tool(t) if t.get("type") == "function" else t for t in tools
        ]
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if self.previous_response_id is None:
            kwargs["input"] = self.prompt
        else:
            kwargs["input"] = list(self.pending)
            kwargs["previous_response_id"] = self.previous_response_id
        return kwargs

    def read(self, response, budget) -> Turn:
        from policybench.eval_no_tools import (
            _get_response_item_attr,
            _response_finish_reason,
            _responses_content_and_tool_calls,
        )

        content, _ = _responses_content_and_tool_calls(response)
        calls = []
        for item in getattr(response, "output", None) or []:
            if _get_response_item_attr(item, "type") == "function_call":
                calls.append(
                    Call(
                        _get_response_item_attr(item, "call_id")
                        or _get_response_item_attr(item, "id")
                        or "",
                        _get_response_item_attr(item, "name"),
                        _get_response_item_attr(item, "arguments"),
                    )
                )
        return Turn(
            response=response,
            content=content,
            calls=calls,
            finish_reason=_response_finish_reason(
                response, responses_api=True, completion_budget_tokens=budget
            ),
        )

    def add_assistant(self, turn: Turn) -> None:
        self.log.append(
            {
                "input": self.prompt
                if self.previous_response_id is None
                else self.pending,
                "response_id": getattr(turn.response, "id", None),
                "content": turn.content,
                "calls": [asdict(c) for c in turn.calls],
            }
        )
        self.previous_response_id = getattr(turn.response, "id", None)
        self.pending = []

    def add_tool_result(self, call: Call, result: dict) -> None:
        self.pending.append(
            {
                "type": "function_call_output",
                "call_id": call.id,
                "output": json.dumps(result),
            }
        )

    def add_user(self, text: str) -> None:
        self.pending.append({"role": "user", "content": text})

    def transcript(self) -> list:
        return self.log + ([{"pending": self.pending}] if self.pending else [])


def _plain(value) -> Any:
    """A provider object as plain data, for the record."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return {k: _plain(v) for k, v in vars(value).items()}
    return value


def _field(value, key: str):
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def turn_searches(
    response, turn: Turn, profile: ModelProfile, seen: set[str]
) -> tuple[list[dict], int]:
    """The web searches one response ran, and how many its provider bills.

    - OpenAI: every ``web_search_call`` output item is billed as a call,
      whatever its action. The pricing page says "$10.00 / 1k calls" without
      naming the actions billed, so open_page and find_in_page are counted too,
      an upper bound; ``search_actions`` counts the searches alone. Each
      search's result URLs (OPENAI_SEARCH_SOURCES) are logged as sources.
    - Anthropic: ``usage.server_tool_use.web_search_requests`` counts every
      search, including those run from code under dynamic filtering. The log
      holds each server call (a direct search's query, or the code that ran
      searches) and each result's URL and title.
    - Gemini: each non-empty query of a GOOGLE_SEARCH_WEB invocation, once per
      invocation id in the household (``seen``). Its responses carry no result
      URLs: an invocation's response holds only search-suggestion HTML, and
      litellm's grounding metadata is empty on function-calling turns (live
      probe, 2026-10-20), so what Gemini read cannot be audited.
    """
    log: list[dict] = []
    billed = 0
    if profile.provider == "openai":
        for item in getattr(response, "output", None) or []:
            if _field(item, "type") != "web_search_call":
                continue
            billed += 1
            action = _plain(_field(item, "action")) or {}
            log.append(
                {
                    "kind": action.get("type"),
                    "id": _field(item, "id"),
                    "queries": action.get("queries")
                    or ([action["query"]] if action.get("query") else []),
                    "url": action.get("url"),
                    "status": _field(item, "status"),
                }
            )
            for source in action.get("sources") or []:
                log.append(
                    {
                        "kind": "source",
                        "id": _field(item, "id"),
                        "url": _field(source, "url"),
                        "source": _plain(source),
                    }
                )
        return log, billed
    message = (getattr(response, "choices", None) or [None])[0]
    message = getattr(message, "message", None)
    fields = _plain(getattr(message, "provider_specific_fields", None)) or {}
    if profile.provider == "anthropic":
        usage = getattr(response, "usage", None)
        server_use = _field(usage, "server_tool_use")
        billed = int(_num(_field(server_use, "web_search_requests")))
        for call in turn.server_calls:
            arguments = call.get("arguments")
            try:
                arguments = json.loads(arguments)
            except (TypeError, ValueError):
                pass
            entry = {"kind": call.get("name"), "id": call.get("id")}
            if isinstance(arguments, dict) and "query" in arguments:
                entry["queries"] = [arguments["query"]]
            elif isinstance(arguments, dict) and "code" in arguments:
                entry["code"] = str(arguments["code"])[:MAX_MESSAGE_CHARS]
            log.append(entry)
        for block in fields.get("web_search_results") or []:
            content = _field(block, "content")
            for result in content if isinstance(content, list) else []:
                log.append(
                    {
                        "kind": "result",
                        "url": _field(result, "url"),
                        "title": _field(result, "title"),
                    }
                )
        return log, billed
    if profile.provider == "gemini":
        for invocation in fields.get("server_side_tool_invocations") or []:
            if _field(invocation, "tool_type") != "GOOGLE_SEARCH_WEB":
                continue
            invocation_id = str(_field(invocation, "id"))
            queries = [
                q for q in (_field(_field(invocation, "args"), "queries") or []) if q
            ]
            repeat = invocation_id in seen
            seen.add(invocation_id)
            if not repeat:
                billed += len(queries)
            log.append(
                {
                    "kind": "search",
                    "id": invocation_id,
                    "queries": queries,
                    "repeat": repeat,
                }
            )
        return log, billed
    return log, billed


def search_cost_usd(profile: ModelProfile, searches: int) -> float:
    return searches * SEARCH_USD_PER_1K[profile.provider] / 1000


class ProviderEmpty(RuntimeError):
    pass


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


def is_timeout(error: Exception) -> bool:
    """A provider or wall-clock timeout (litellm.Timeout and its kin)."""
    return any("Timeout" in cls.__name__ for cls in type(error).__mro__)


def _request_with_retries(
    completion_fn, kwargs: dict, retry_timeouts: bool = True
) -> tuple[Any, float, float, float]:
    from policybench.eval_no_tools import _run_request_with_wall_timeout, _should_retry

    for attempt in range(MAX_PROVIDER_ATTEMPTS):
        started_at = time.time()
        started = time.perf_counter()
        try:
            response = _run_request_with_wall_timeout(completion_fn, kwargs)
            return response, started_at, time.time(), time.perf_counter() - started
        except Exception as error:
            if (
                attempt == MAX_PROVIDER_ATTEMPTS - 1
                or not _should_retry(error)
                or (not retry_timeouts and is_timeout(error))
            ):
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
    profile: ModelProfile | None = None,
) -> dict:
    """One household's conversation: tool turns, then the board's answer.

    A tool-contract model answers through ``submit_outputs`` (forced once the
    cap is reached, as the board forces it). A JSON-contract model answers in
    the board's JSON reply; its API refuses a forced tool, so the calculate
    tool is offered under tool_choice auto and the cap is a user message.

    The profile's arm sets the tools: the calculate tool ("pe"), the
    provider's web search ("web"), or both ("web+pe"). The provider runs a
    search inside the response that asked for it, so searches use no
    calculation turn; each response's searches are logged and their list
    price added to its cost.
    """
    from policybench.eval_no_tools import (
        _apply_thinking_configuration,
        _enforce_explanation_value_contract,
        _extract_usage_metadata,
        _merge_repair_cells,
        _missing_explanations,
        _serialize_response_payload,
        extract_explanations,
        extract_predictions,
    )

    profile = profile or model_profile()
    prompt, base = build_initial_request(scenario, variables, profile)
    board_prompt_sha256 = base.pop("_board_prompt_sha256")
    sent_board_prompt_sha256 = base.pop("_sent_board_prompt_sha256")
    ceiling = base.pop("_budget_ceiling")
    answer_tool = base.pop("_answer_tool")
    calculate_tool = calculate_tool_schema(features=profile.tool_features)
    offered = ([web_search_tool(profile)] if profile.uses_web else []) + (
        [calculate_tool] if profile.uses_calculator else []
    )
    if profile.uses_web:
        base["timeout"] = max(
            float(base.get("timeout") or 0), WEB_REQUEST_TIMEOUT_SECONDS
        )
    if profile.uses_web and profile.provider == "gemini":
        base["include_server_side_tool_invocations"] = True
    if profile.uses_web and profile.provider == "openai":
        # The URLs behind each search's results, for the audit.
        base["include"] = [*base.get("include", []), OPENAI_SEARCH_SOURCES]
    seen_searches: set[str] = set()
    pause_continuations = 0
    conversation = (
        ResponsesConversation(prompt)
        if profile.api == "responses"
        else ChatConversation(
            # The board's own request marks no prompt-cache breakpoint, so the
            # no-tools arm, its stand-in, marks none either.
            prompt,
            cache_breakpoint=profile.model_id.startswith("claude-")
            and profile.arm != "none",
        )
    )
    json_contract = profile.contract == "json"
    calculate_offered = profile.uses_calculator
    record: dict[str, Any] = {
        "scenario_id": scenario.id,
        "model": profile.name,
        "arm": profile.arm,
        "api": profile.api,
        "contract": profile.contract,
        "variables": variables,
        "board_prompt_sha256": board_prompt_sha256,
        "prompt_version": profile.prompt_version,
        "prompt_wording_sha256": prompt_wording_sha256(profile),
        "benchmark_search_rule": profile.benchmark_search_rule,
        "sent_board_prompt_sha256": sent_board_prompt_sha256,
        "tool_notice_sha256": hashlib.sha256(profile.notice.encode()).hexdigest(),
        "turns": [],
        "status": "running",
    }
    predictions: dict[str, float | None] = {v: None for v in variables}
    explanations: dict[str, str | None] = {v: None for v in variables}
    tool_turns = 0
    # Turns that only searched: in the web arms they count toward the cap, so
    # a model cannot search without end while the cap waits on calculations.
    search_only_turns = 0
    repair_rounds = 0
    answer_variables = list(variables)
    household_started = time.perf_counter()

    def tools_and_choice(kind: str):
        if json_contract:
            # The board's JSON contract sends no tools, so the no-tools arm
            # sends none and no tool_choice either.
            return list(offered), ("auto" if offered else None)
        if kind == "repair":
            return (
                [
                    *offered,
                    answer_tool_for(profile, answer_variables, scenario.country),
                ],
                forced_answer_choice(profile),
            )
        if kind == "forced_answer" or not offered:
            # With no tools offered, the board forces its answer function from
            # the first turn; so does the no-tools arm.
            return [*offered, answer_tool], forced_answer_choice(profile)
        return [*offered, answer_tool], "required"

    def cap_reached() -> bool:
        return tool_turns + search_only_turns >= turn_cap

    def count_search_only(turn_record: dict, turn) -> bool:
        """Count a web arm's turn that searched and neither answered nor
        calculated toward the cap, so a model cannot search without end."""
        nonlocal search_only_turns
        if profile.uses_web and (turn.server_calls or turn_record.get("web_searches")):
            search_only_turns += 1
            turn_record["search_only_turn"] = True
            return True
        return False

    def bill_searches(response, turn) -> dict:
        """Log the response's searches and add their price to the spend."""
        if not profile.uses_web:
            return {}
        log, billed = turn_searches(response, turn, profile, seen_searches)
        cost = search_cost_usd(profile, billed)
        spend.add(cost)
        return {
            "server_calls": turn.server_calls,
            "unfinished_server_calls": turn.unfinished_server_calls,
            "searches": log,
            "web_searches": billed,
            "search_actions": billed
            if profile.provider != "openai"
            else sum(1 for e in log if e.get("kind") == "search"),
            "search_cost_usd": cost,
        }

    def accept_answer(content, calls) -> list[str]:
        """Merge an answer into the predictions; return the outputs still needed."""
        nonlocal predictions, explanations
        got = extract_predictions(content, answer_variables, tool_calls=calls)
        got_explanations = extract_explanations(
            content, answer_variables, tool_calls=calls
        )
        got, got_explanations = _enforce_explanation_value_contract(
            got, got_explanations, answer_variables
        )
        # The board's merge: a repair fills only cells still missing, and a
        # valid earlier value or explanation always stands.
        disagreements = record.setdefault("repair_disagreements", [])
        predictions = _merge_repair_cells(
            predictions,
            {v: got.get(v) for v in answer_variables},
            field="prediction",
            disagreements=disagreements,
        )
        explanations = _merge_repair_cells(
            explanations,
            {v: got_explanations.get(v) for v in answer_variables},
            field="explanation",
            disagreements=disagreements,
        )
        pending = {v for v in variables if predictions[v] is None}
        missing_explanation = set(_missing_explanations(explanations, variables))
        return [v for v in variables if v in pending | missing_explanation]

    def repair_text(still: list[str]) -> str:
        kept = [
            f"{v} (keep your value {number}; its explanation must end with "
            f"`value = {number}`)"
            for v in still
            if predictions[v] is not None
            for number in [plain_number(predictions[v])]
        ]
        how = (
            "Reply with a JSON object holding only these outputs"
            if json_contract
            else "Call submit_outputs again with only these outputs"
        )
        return (
            f"Your {'answer' if json_contract else 'submit_outputs call'} omitted "
            f"or left unusable these outputs: {', '.join(still)}. {how}, each with "
            "a numeric value and an explanation ending with `value = X`."
            + (
                " Explanations only are missing for: " + "; ".join(kept) + "."
                if kept
                else ""
            )
        )

    def run_calculations(turn_record: dict, calls: list[Call]) -> bool:
        """Run the turn's calculations; False if the pool had no worker."""
        for position, call in enumerate(calls):
            if position >= MAX_CALCULATIONS_PER_TURN:
                result, tool_latency = (
                    {
                        "error": "not_run",
                        "message": (
                            f"at most {MAX_CALCULATIONS_PER_TURN} calculations per turn"
                        ),
                    },
                    0.0,
                )
            else:
                result, tool_latency = tool_call(call.arguments)
            turn_record["calls"].append(
                {
                    "name": TOOL_NAME,
                    "arguments": call.arguments,
                    "result": result,
                    "tool_latency_seconds": tool_latency,
                }
            )
            if isinstance(result, dict) and result.get("error") == POOL_UNAVAILABLE:
                return False
            conversation.add_tool_result(call, result)
        return True

    try:
        forced = False
        for turn_index in range(MAX_TOTAL_TURNS):
            if spend.exhausted():
                record["status"] = "budget_stop"
                break
            if repair_rounds:
                kind = "repair"
            elif not json_contract and (
                forced or tool_turns + search_only_turns >= turn_cap or not offered
            ):
                kind, forced = "forced_answer", True
            else:
                kind = "open"
            tools, tool_choice = tools_and_choice(kind)
            kwargs = conversation.request_kwargs(
                {k: v for k, v in base.items() if k not in {"tools", "tool_choice"}}
                | {"model": profile.model_id},
                tools,
                tool_choice,
            )
            _apply_thinking_configuration(kwargs, profile.model_id)
            budget_key = conversation.budget_key
            escalated_from = None
            try:
                response, started_at, completed_at, latency = _request_with_retries(
                    completion_fn, kwargs, retry_timeouts=not profile.uses_web
                )
                turn = conversation.read(response, kwargs.get(budget_key))
                if (
                    turn.finish_reason == "length"
                    and kwargs.get(budget_key, 0) < ceiling
                ):
                    usage = _extract_usage_metadata(response, profile.model_id, [], "")
                    spend.add(usage.get("total_cost_usd"))
                    record["turns"].append(
                        {
                            "index": turn_index,
                            "kind": kind,
                            "truncated_and_retried": True,
                            "completion_budget": kwargs.get(budget_key),
                            "latency_seconds": latency,
                            **usage,
                            **bill_searches(response, turn),
                        }
                    )
                    escalated_from = kwargs.get(budget_key)
                    kwargs[budget_key] = ceiling
                    response, started_at, completed_at, latency = _request_with_retries(
                        completion_fn, kwargs, retry_timeouts=not profile.uses_web
                    )
                    turn = conversation.read(response, kwargs.get(budget_key))
            except Exception as error:
                record["status"] = "provider_error"
                record["error"] = f"{type(error).__name__}: {error}"[:MAX_MESSAGE_CHARS]
                break

            raw = _serialize_response_payload(
                content=turn.content,
                tool_calls=[
                    {"id": c.id, "function": {"name": c.name, "arguments": c.arguments}}
                    for c in turn.calls
                ],
                function_call=None,
            )
            usage = _extract_usage_metadata(
                response, profile.model_id, [], raw or turn.content or ""
            )
            spend.add(usage.get("total_cost_usd"))
            turn_record = {
                "index": turn_index,
                "kind": kind,
                "tool_choice": tool_choice,
                "completion_budget": kwargs.get(budget_key),
                "escalated_from": escalated_from,
                "request_started_at": started_at,
                "request_completed_at": completed_at,
                "latency_seconds": latency,
                "finish_reason": turn.finish_reason,
                "content": turn.content,
                "reasoning_content": turn.reasoning_content,
                "has_thought_signature": turn.has_thought_signature,
                "response_id": getattr(response, "id", None),
                "calls": [],
                **usage,
                **bill_searches(response, turn),
            }
            record["turns"].append(turn_record)
            conversation.add_assistant(turn)

            answer_calls = [c for c in turn.calls if c.name == "submit_outputs"]
            calculate_calls = [c for c in turn.calls if c.name == TOOL_NAME]
            other_calls = [
                c
                for c in turn.calls
                if c not in answer_calls and c not in calculate_calls
            ]

            # A tool-contract answer: the submit_outputs call ends the turn.
            if answer_calls:
                still = accept_answer(
                    turn.content,
                    [
                        {"function": {"name": c.name, "arguments": c.arguments}}
                        for c in answer_calls
                    ],
                )
                turn_record["calls"].append(
                    {
                        "name": "submit_outputs",
                        "arguments": answer_calls[0].arguments,
                        "ignored_calls": len(turn.calls) - 1,
                    }
                )
                for call in turn.calls:
                    conversation.add_tool_result(
                        call,
                        {"accepted": not still, "missing": still}
                        if call is answer_calls[0]
                        else {"error": "not run: submit_outputs ended the turn"},
                    )
            elif calculate_calls and (
                tool_turns + search_only_turns >= turn_cap
                or (not json_contract and kind != "open")
            ):
                # Past the cap, or in a turn that forced the answer, nothing
                # runs. tool_choice auto cannot withhold the tool from a
                # JSON-contract model; a forced turn should never carry a
                # calculation, but a provider that sends one gets no result.
                refusal = {
                    "error": "not_run",
                    "message": "no calculation turns are left; "
                    + (
                        "reply with your final answers as the JSON object "
                        "described above"
                        if json_contract
                        else "call submit_outputs with your final answers"
                    ),
                }
                for call in turn.calls:
                    turn_record["calls"].append(
                        {
                            "name": call.name,
                            "arguments": call.arguments,
                            "result": refusal,
                            "tool_latency_seconds": 0.0,
                        }
                    )
                    conversation.add_tool_result(call, refusal)
                continue
            elif calculate_calls:
                tool_turns += 1
                if not run_calculations(turn_record, calculate_calls):
                    # Infrastructure, not the model: a rerunnable status, so the
                    # household is not scored on an answer the pool prevented.
                    record["status"] = "harness_error"
                    record["error"] = "the tool pool had no worker"
                    break
                for call in other_calls:
                    conversation.add_tool_result(call, {"error": "unknown function"})
                if tool_turns + search_only_turns >= turn_cap and (
                    turn.unfinished_server_calls
                ):
                    # Only tool results may follow a deferred server call;
                    # the refusal of any later calculation says the same.
                    turn_record["cap_notice_withheld"] = True
                elif tool_turns + search_only_turns >= turn_cap:
                    conversation.add_user(
                        f"You have used all {turn_cap} calculation turns. "
                        + (
                            "Reply now with your final answers as the JSON object "
                            "described above."
                            if json_contract
                            else "Call submit_outputs now with your final answers."
                        )
                    )
                continue
            elif json_contract and not turn.calls and turn.unfinished_server_calls:
                # A paused server-tool turn: a server call with no result and
                # nothing waiting on us. It continues when sent back as it is.
                if pause_continuations < MAX_PAUSE_CONTINUATIONS:
                    pause_continuations += 1
                    turn_record["continued_after_pause"] = True
                    continue
                record["status"] = "incomplete"
                record["error"] = (
                    "a paused server-tool turn was still unfinished after "
                    f"{MAX_PAUSE_CONTINUATIONS} continuations"
                )
                break
            elif json_contract and turn.content:
                # A JSON-contract answer: the reply itself.
                still = accept_answer(turn.content, None)
                answered = any(v is not None for v in predictions.values()) or any(
                    explanations.values()
                )
                for call in other_calls:
                    conversation.add_tool_result(call, {"error": "unknown function"})
                if not answered:
                    if turn.unfinished_server_calls:
                        continue  # only tool results may follow
                    if count_search_only(turn_record, turn) and cap_reached():
                        conversation.add_user(JSON_SEARCH_CAP_TEXT.format(cap=turn_cap))
                        continue
                    conversation.add_user(
                        "Reply with your final answers as the JSON object described "
                        "above"
                        + (
                            ", or call calculate_household."
                            if calculate_offered
                            else "."
                        )
                    )
                    continue
            else:
                for call in other_calls:
                    conversation.add_tool_result(call, {"error": "unknown function"})
                searched_only = count_search_only(turn_record, turn)
                if turn.unfinished_server_calls:
                    continue  # only tool results may follow
                if json_contract and searched_only and cap_reached():
                    conversation.add_user(JSON_SEARCH_CAP_TEXT.format(cap=turn_cap))
                    continue
                if calculate_offered:
                    nudge = (
                        "Call calculate_household or give your final answers as "
                        "the JSON object described above."
                        if json_contract
                        else "Call calculate_household or submit_outputs."
                    )
                else:
                    nudge = (
                        "Give your final answers as the JSON object described above."
                        if json_contract
                        else "Call submit_outputs with your final answers."
                    )
                conversation.add_user(nudge)
                continue

            if not still:
                record["status"] = "complete"
                break
            if repair_rounds >= MAX_REPAIR_ROUNDS:
                record["status"] = "incomplete"
                break
            answer_variables = still
            if turn.unfinished_server_calls:
                # Only tool results may follow an unfinished server call. The
                # next reply is merged for the outputs listed here; no repair
                # round is used, since no repair text was sent.
                turn_record["repair_deferred"] = True
                continue
            repair_rounds += 1
            conversation.add_user(repair_text(still))
        else:
            record["status"] = "turn_limit"
    except Exception as error:  # keep the turns, and their spend, so far
        record["status"] = "harness_error"
        record["error"] = f"{type(error).__name__}: {error}"[:MAX_MESSAGE_CHARS]

    if record["status"] == "running":
        record["status"] = "incomplete"
    record["predictions"] = predictions
    record["explanations"] = explanations
    record["tool_turns"] = tool_turns
    record["search_only_turns"] = search_only_turns
    record["cap_hit"] = tool_turns + search_only_turns >= turn_cap
    record["repair_rounds"] = repair_rounds
    record["pause_continuations"] = pause_continuations
    record["wall_seconds"] = time.perf_counter() - household_started
    record["messages"] = conversation.transcript()
    record["totals"] = household_totals(record)
    return record


def plain_number(value) -> str:
    """A number as plain decimal digits, never scientific notation, so the
    board's `value = X` trailer pattern can read it back."""
    text = format(decimal.Decimal(repr(float(value))), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _num(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def record_cost_with_prior_attempts(record: dict) -> float:
    """A record's spend, including attempts a resume replaced."""
    prior = sum(
        _num(a.get("totals", {}).get("cost_usd"))
        for a in record.get("prior_attempts", [])
    )
    return _num(record.get("totals", {}).get("cost_usd")) + prior


def household_totals(record: dict) -> dict:
    """Tokens, cost and time over every request, truncated ones included;
    ``model_turns`` counts the turns that reached the conversation. A web
    arm's ``cost_usd`` adds its searches' list price to its tokens'."""
    turns = record.get("turns", [])
    calls = [c for t in turns for c in t.get("calls", []) if c.get("name") == TOOL_NAME]
    errors = [
        c for c in calls if isinstance(c.get("result"), dict) and "error" in c["result"]
    ]
    return {
        "model_turns": sum(1 for t in turns if not t.get("truncated_and_retried")),
        "truncation_retries": sum(1 for t in turns if t.get("truncated_and_retried")),
        "tool_calls": len(calls),
        "tool_errors": len(errors),
        "tool_error_kinds": sorted({c["result"]["error"] for c in errors}),
        "prompt_tokens": sum(_num(t.get("prompt_tokens")) for t in turns),
        "completion_tokens": sum(_num(t.get("completion_tokens")) for t in turns),
        "reasoning_tokens": sum(_num(t.get("reasoning_tokens")) for t in turns),
        "cached_prompt_tokens": sum(_num(t.get("cached_prompt_tokens")) for t in turns),
        "cache_write_prompt_tokens": sum(
            _num(t.get("cache_write_prompt_tokens")) for t in turns
        ),
        # Tokens at list price, plus each search at its list price.
        "token_cost_usd": sum(_num(t.get("total_cost_usd")) for t in turns),
        "web_searches": sum(_num(t.get("web_searches")) for t in turns),
        "web_search_actions": sum(
            _num(t.get("search_actions", t.get("web_searches"))) for t in turns
        ),
        "search_cost_usd": sum(_num(t.get("search_cost_usd")) for t in turns),
        "cost_usd": sum(
            _num(t.get("total_cost_usd")) + _num(t.get("search_cost_usd"))
            for t in turns
        ),
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


def board_path(args) -> Path:
    """The board a command reads: --board, or the frozen snapshot."""
    return Path(getattr(args, "board", None) or SNAPSHOT)


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


def command_oracle(args) -> None:
    """Reference situations through the tool engine: every scored reference must
    come back within the board's tolerance."""
    snapshot = board_path(args)
    _require_engine(snapshot)
    from policybench.ground_truth import _extract_person_value, _pe_variable_for_output

    board = load_board(snapshot)
    scored_keys = set(zip(board["scored"].scenario_id, board["scored"].variable))
    values = board["reference"].set_index(["scenario_id", "variable"])["value"]
    rows = []
    for label, reform in (("reference_engine", True), ("plain_engine", False)):
        system = build_tool_system(reform=reform, snapshot=snapshot)
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


def resume_state(households_dir: Path) -> tuple[float, set[str], dict[str, dict]]:
    """Spend so far, the households that keep their record, and every record.

    A model outcome (complete, incomplete, turn_limit) stands; only an
    infrastructure failure (RERUNNABLE_STATUSES) is rerun, so a resume cannot
    redraw a household until it succeeds. Spend includes replaced attempts.
    """
    spent = 0.0
    done: set[str] = set()
    previous: dict[str, dict] = {}
    for path in sorted(households_dir.glob("*.json")):
        record = json.loads(path.read_text())
        spent += record_cost_with_prior_attempts(record)
        previous[record["scenario_id"]] = record
        if record.get("status") not in RERUNNABLE_STATUSES:
            done.add(record["scenario_id"])
    return spent, done, previous


def provider_key(model_id: str) -> str:
    for prefix, key in PROVIDER_KEYS.items():
        if model_id.startswith(prefix):
            return key
    raise SystemExit(f"no provider key is known for {model_id}")


def records_model(records: Mapping[str, dict]) -> str:
    """The one model a run directory's records belong to; records written
    before the pilot took --model are Argon's."""
    models = {r.get("model", MODEL_NAME) for r in records.values()}
    if len(models) > 1:
        raise SystemExit(f"records from more than one model: {sorted(models)}")
    return models.pop() if models else MODEL_NAME


def records_prompt(records: Mapping[str, dict]) -> tuple[str, bool]:
    """The one prompt version and search rule a run directory's records
    share; records written before either existed are v1 without the rule."""
    setups = {
        (r.get("prompt_version", "v1"), bool(r.get("benchmark_search_rule")))
        for r in records.values()
    }
    if len(setups) > 1:
        raise SystemExit(f"records from more than one prompt setup: {sorted(setups)}")
    return setups.pop() if setups else ("v1", False)


def records_wording(records: Mapping[str, dict]) -> str | None:
    """The one v2-pilot wording hash a run directory's records share. v2-pilot
    records written before the hash existed read as "unrecorded", so a resume
    into them is refused rather than mixed."""
    hashes = {
        r.get(
            "prompt_wording_sha256",
            "unrecorded" if r.get("prompt_version", "v1") != "v1" else None,
        )
        for r in records.values()
    }
    if len(hashes) > 1:
        raise SystemExit(f"records under more than one prompt wording: {hashes}")
    return hashes.pop() if hashes else None


def records_arm(records: Mapping[str, dict]) -> str:
    """The one arm a run directory's records belong to; records written
    before the web arms are the PE tool's."""
    arms = {r.get("arm", "pe") for r in records.values()}
    if len(arms) > 1:
        raise SystemExit(f"records from more than one arm: {sorted(arms)}")
    return arms.pop() if arms else "pe"


def command_run(args) -> None:
    snapshot = board_path(args)
    _require_engine(snapshot)
    # The notices and the tool description state the board's engine.
    set_stated_engine(board_engine(snapshot))
    profile = model_profile(
        args.model, args.arm, args.prompt, args.forbid_benchmark_search
    )
    key = provider_key(profile.model_id)
    if not os.environ.get(key):
        raise SystemExit(f"{key} is not set")
    if profile.uses_web:
        web_search_tool(profile)  # refuses a provider with no search wired
    if profile.uses_web and profile.provider == "gemini":
        allow_gemini_search_with_functions()
    from litellm import completion, responses

    completion_fn = responses if profile.api == "responses" else completion
    board = load_board(snapshot)
    out = Path(args.out_dir)
    households_dir = out / "households"
    households_dir.mkdir(parents=True, exist_ok=True)
    ids = sorted(board["scenarios"])
    if args.scenarios:
        ids = [sid for sid in ids if sid in set(args.scenarios)]
    if args.limit:
        ids = ids[: args.limit]

    spent_before, done, previous = resume_state(households_dir)
    if previous and records_model(previous) != profile.name:
        raise SystemExit(
            f"{households_dir} holds {records_model(previous)} records, "
            f"not {profile.name}"
        )
    if previous and records_arm(previous) != profile.arm:
        raise SystemExit(
            f"{households_dir} holds {records_arm(previous)} records, not {profile.arm}"
        )
    setup = (profile.prompt_version, profile.benchmark_search_rule)
    if previous and records_prompt(previous) != setup:
        raise SystemExit(
            f"{households_dir} holds records with prompt setup "
            f"{records_prompt(previous)}, not {setup}"
        )
    if previous and records_wording(previous) != prompt_wording_sha256(profile):
        raise SystemExit(
            f"{households_dir} holds records sent under other v2-pilot wording "
            f"({records_wording(previous)}); use a fresh --out-dir"
        )
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
        "board": str(snapshot),
        "board_engine": f"policyengine-us {board_engine(snapshot)}",
        "board_reference_sha256": board["meta"].get("reference_csv_sha256"),
        "model": profile.name,
        "model_id": profile.model_id,
        "arm": profile.arm,
        "prompt_version": profile.prompt_version,
        "prompt_wording_sha256": prompt_wording_sha256(profile),
        "benchmark_search_rule": profile.benchmark_search_rule,
        "v2_pilot_definitions": [
            {"v1": pattern.pattern, "v2_pilot": text}
            for pattern, text in (*V2_PILOT_DEFINITIONS, *V2_PILOT_CONVENTIONS)
        ]
        if profile.prompt_version == "v2-pilot"
        else None,
        "api": profile.api,
        "answer_contract": profile.contract,
        "tool_notice": profile.notice,
        "calculate_tool": calculate_tool_schema(features=profile.tool_features)
        if profile.uses_calculator
        else None,
        "tool_features": sorted(profile.tool_features)
        if profile.uses_calculator
        else None,
        "tool_version": profile.tool_version if profile.uses_calculator else None,
        "web_search_tool": web_search_tool(profile) if profile.uses_web else None,
        # The timeout actually sent: the board's for the model, or the web arms'.
        "request_timeout_seconds": build_initial_request(
            board["scenarios"][ids[0]], board["variables"][ids[0]], profile
        )[1].get("timeout")
        if ids and not profile.uses_web
        else (WEB_REQUEST_TIMEOUT_SECONDS if profile.uses_web else None),
        "web_timeouts_retried": not profile.uses_web,
        "search_usd_per_1k": (
            SEARCH_USD_PER_1K[profile.provider] if profile.uses_web else None
        ),
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
    # Arms without the calculator start no engine workers.
    pool = (
        ToolPool(
            size=args.workers,
            board=snapshot,
            tool_version=profile.tool_version,
            tool_features=profile.tool_features,
        )
        if profile.uses_calculator
        else None
    )

    def no_calculator(arguments) -> tuple[dict, float]:
        return {"error": "not_run", "message": "no calculator in this arm"}, 0.0

    try:

        def one(sid: str) -> dict:
            if spend.exhausted(args.reserve_usd):
                return {"scenario_id": sid, "status": "budget_stop"}
            if pool is not None and pool.counters()["lost"] >= args.workers:
                # Every worker is gone: start nothing more. The household keeps
                # no record, so a resume runs it.
                return {
                    "scenario_id": sid,
                    "status": "harness_error",
                    "error": "every tool worker was lost",
                }
            try:
                record = run_household(
                    board["scenarios"][sid],
                    board["variables"][sid],
                    pool.call if pool is not None else no_calculator,
                    completion_fn,
                    spend,
                    profile=profile,
                )
            except Exception as error:  # one household must not end the run
                record = {
                    "scenario_id": sid,
                    "model": profile.name,
                    # The setup keys a resume and score check, so a folder with
                    # this record still resumes and scores.
                    "arm": profile.arm,
                    "prompt_version": profile.prompt_version,
                    "prompt_wording_sha256": prompt_wording_sha256(profile),
                    "benchmark_search_rule": profile.benchmark_search_rule,
                    "variables": board["variables"][sid],
                    "status": "harness_error",
                    "error": f"{type(error).__name__}: {error}"[:MAX_MESSAGE_CHARS],
                    "turns": [],
                    "predictions": {v: None for v in board["variables"][sid]},
                    "explanations": {v: None for v in board["variables"][sid]},
                }
                record["totals"] = household_totals(record)
            if sid in previous:
                prior = previous[sid]
                record["prior_attempts"] = prior.get("prior_attempts", []) + [
                    {"status": prior.get("status"), "totals": prior.get("totals", {})}
                ]
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
        counters = pool.counters() if pool is not None else {}
        if pool is not None:
            pool.close()
    stopped = [r["scenario_id"] for r in results if r.get("status") == "budget_stop"]
    rerunnable = sorted(
        r["scenario_id"] for r in results if r.get("status") in RERUNNABLE_STATUSES
    )
    summary = {
        "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "spent_usd": spend.spent_usd,
        "budget_usd": args.budget_usd,
        "statuses": dict(sorted(Counter(r.get("status") for r in results).items())),
        "rerunnable_households": rerunnable,
        "errors": {
            r["scenario_id"]: r.get("error")
            for r in results
            if r.get("status") in RERUNNABLE_STATUSES and r.get("error")
        },
        "tool_pool": counters,
    }
    (
        out / f"run-summary-{summary['finished_at_utc'].replace(':', '')}.json"
    ).write_text(json.dumps(summary, indent=2))
    print(f"tool pool: {counters}; rerunnable households: {rerunnable}")
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


def arm2_predictions(
    records: Mapping[str, dict], label: str = ARM2_LABEL
) -> pd.DataFrame:
    rows = []
    for sid, record in records.items():
        for variable in record["variables"]:
            value = record["predictions"].get(variable)
            rows.append(
                {
                    "model": label,
                    "scenario_id": sid,
                    "variable": variable,
                    "prediction": value,
                    "explanation": record["explanations"].get(variable),
                    "error": None if value is not None else record["status"],
                }
            )
    return pd.DataFrame(rows)


def arm1_predictions(
    snapshot: Path = SNAPSHOT, label: str = ARM1_LABEL
) -> pd.DataFrame:
    frame = pd.read_csv(snapshot / "predictions.csv.gz", low_memory=False)
    rows = frame[frame["model"] == label].copy()
    if rows.empty:
        raise SystemExit(f"the snapshot has no frozen predictions for {label}")
    return rows


def baseline_predictions(
    records: Mapping[str, dict], label: str = ARM1_LABEL
) -> pd.DataFrame:
    """A no-tools run's records as the board's prediction frame, with each
    household's usage on its first row so per-household sums are its totals."""
    frame = arm2_predictions(records, label)
    usage = {
        "prompt_tokens": "prompt_tokens",
        "completion_tokens": "completion_tokens",
        "reasoning_tokens": "reasoning_tokens",
        "total_cost_usd": "cost_usd",
        "elapsed_seconds": "model_seconds",
        "cached_prompt_tokens": "cached_prompt_tokens",
    }
    first = ~frame.duplicated("scenario_id")
    for column, total in usage.items():
        frame[column] = [
            float(records[sid]["totals"].get(total) or 0.0) if is_first else 0.0
            for sid, is_first in zip(frame.scenario_id, first)
        ]
    frame["call_id"] = frame.scenario_id
    return frame


def command_score(args) -> None:
    from policybench.analysis import analyze_no_tools
    from policybench.spec import output_group_id

    snapshot = board_path(args)
    board = load_board(snapshot)
    out = Path(args.out_dir)
    records = load_records(out)
    profile = model_profile(
        records_model(records), records_arm(records), *records_prompt(records)
    )
    arm1_label, arm2_label = profile.arm1_label, profile.arm2_label
    complete = sorted(
        sid for sid, r in records.items() if r.get("status") == "complete"
    )
    # The board's rule: every household counts, and an unparsed output is a
    # miss. Scoring only completed households would select on the outcome.
    households = complete if args.complete_only else sorted(records)
    if not households:
        raise SystemExit("no household records to score")
    leftover = sorted(
        sid for sid in households if records[sid].get("status") in RERUNNABLE_STATUSES
    )
    if leftover:
        print(
            f"WARNING: {len(leftover)} households ended on an infrastructure "
            f"failure and score as misses until a resume reruns them: {leftover}"
        )
    scored = board["scored"][board["scored"].scenario_id.isin(households)]
    if is_household_set(snapshot):
        # No board run exists for a fresh household set: the baseline is the
        # same model's no-tools arm on it, run with the same prompt setup.
        baseline_dir = getattr(args, "baseline_dir", None)
        if not baseline_dir:
            raise SystemExit("a household set is scored against --baseline-dir")
        baseline = load_records(Path(baseline_dir))
        if records_model(baseline) != profile.name or records_arm(baseline) != "none":
            raise SystemExit(
                f"--baseline-dir holds {records_model(baseline)} "
                f"{records_arm(baseline)} records, not {profile.name} none"
            )
        if records_prompt(baseline)[0] != profile.prompt_version:
            raise SystemExit("--baseline-dir was run on another prompt version")
        missing = sorted(set(households) - set(baseline))
        if missing:
            raise SystemExit(f"--baseline-dir lacks households {missing}")
        arm1 = baseline_predictions(
            {sid: baseline[sid] for sid in households}, arm1_label
        )
    else:
        arm1 = arm1_predictions(label=arm1_label)
    arm1 = arm1[arm1.scenario_id.isin(households)]
    arm2 = arm2_predictions({sid: records[sid] for sid in households}, arm2_label)
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

    # Household scores, checked against the board's headline before use.
    both = pd.concat([arm1, arm2], ignore_index=True)
    by_household = household_weighted_exact(scored, both, scenarios)
    means = by_household.groupby("model")["weighted_exact"].mean()
    published = summary.set_index("model")["weighted_exact"]
    for model in (arm1_label, arm2_label):
        if abs(means[model] - published[model]) > 1e-9:
            raise SystemExit(
                f"household scores for {model} average {means[model]}, not the "
                f"board's {published[model]}"
            )
    wide = by_household.pivot(
        index="scenario_id", columns="model", values="weighted_exact"
    )
    wide.to_csv(out / "household_scores.csv")
    bootstrap = paired_bootstrap(wide[arm1_label], wide[arm2_label])
    print(json.dumps(bootstrap, indent=2))

    flips = (
        rows.assign(
            transition=[
                ("hit" if a else "miss") + "->" + ("hit" if b else "miss")
                for a, b in zip(rows.arm1_hit, rows.arm2_hit)
            ]
        )
        .groupby(["program", "transition"])
        .size()
        .unstack(fill_value=0)
    )
    flips.to_csv(out / "flips_by_program.csv")
    print(flips.to_string())

    usage = usage_by_household(records, arm1, households)
    usage.to_csv(out / "usage_by_household.csv", index=False)
    usage_summary = summarize_usage(usage)
    print(json.dumps(usage_summary, indent=2))
    tool_use = tool_use_summary({sid: records[sid] for sid in households})
    print(json.dumps(tool_use, indent=2))
    searches = search_log({sid: records[sid] for sid in households})
    audit = None
    if profile.uses_web:
        searches.to_csv(out / "searches.csv", index=False)
        audit = search_audit(searches, results_visible=profile.provider != "gemini")
        if not audit["results_visible"]:
            audit["caveat"] = (
                "This provider returns no result URLs, so flags and the unflagged "
                "score rest on queries alone; what the model read cannot be audited."
            )
        clean = [sid for sid in wide.index if sid not in audit["flagged_households"]]
        audit["weighted_exact_unflagged"] = {
            "households": len(clean),
            "arm1": float(wide.loc[clean, arm1_label].mean()) if clean else None,
            "arm2": float(wide.loc[clean, arm2_label].mean()) if clean else None,
        }
        print(
            f"searches logged: {audit['logged_entries']}; policybench mentions: "
            f"{len(audit['policybench_mentions'])}; blocked-domain URLs: "
            f"{len(audit['blocked_domain_urls'])}; flagged households: "
            f"{audit['flagged_households']}; results visible: "
            f"{audit['results_visible']}; entries naming the reference engine: "
            f"{audit['reference_engine_entries']}"
        )
        if not audit["results_visible"]:
            print(f"CAVEAT: {audit['caveat']}")
    (out / "score.json").write_text(
        json.dumps(
            {
                "model": profile.name,
                "arm1_label": arm1_label,
                "arm2_label": arm2_label,
                "households": len(households),
                "incomplete_households": sorted(set(records) - set(complete)),
                "rerunnable_households": leftover,
                "scored_outputs": int(len(scored)),
                "summary": summary[columns].to_dict(orient="records"),
                "unweighted_hits": {
                    "arm1": int(rows.arm1_hit.sum()),
                    "arm2": int(rows.arm2_hit.sum()),
                },
                "transitions": {
                    k: int(v) for k, v in flips.sum(axis=0).to_dict().items()
                },
                "household_bootstrap": bootstrap,
                "arm": profile.arm,
                "prompt_version": profile.prompt_version,
                "benchmark_search_rule": profile.benchmark_search_rule,
                "tool_use": tool_use,
                "search_audit": audit,
                "usage": usage_summary,
            },
            indent=2,
            default=float,
        )
    )


def household_weighted_exact(
    scored: pd.DataFrame, predictions: pd.DataFrame, scenarios_frame: pd.DataFrame
) -> pd.DataFrame:
    """Each household's weighted exact score.

    The steps of policybench.analysis.weighted_hit_rate_scores_by_model up to
    its household table, which it then averages with equal household weight;
    command_score checks that the mean of these equals its weighted_exact.
    """
    from policybench.analysis import (
        _country_from_scenarios,
        _drop_zero_weight_households,
        _row_weights_for_ground_truth,
        bounded_global_variable_weights,
        row_hit_scores,
    )

    market_income = dict(
        zip(
            scenarios_frame["scenario_id"].astype(str),
            pd.to_numeric(scenarios_frame["total_income"], errors="coerce").fillna(0.0),
        )
    )
    weights = bounded_global_variable_weights(
        scored, market_income, country=_country_from_scenarios(scenarios_frame)
    )
    row_weights = _row_weights_for_ground_truth(scored, weights)
    models = sorted(predictions["model"].dropna().unique())
    grid = (
        scored.assign(_k=1)
        .merge(pd.DataFrame({"model": models, "_k": 1}), on="_k")
        .drop(columns="_k")
    )
    merged = grid.merge(
        predictions[["model", "scenario_id", "variable", "prediction"]],
        on=["model", "scenario_id", "variable"],
        how="left",
    )
    merged["exact"] = [
        row_hit_scores(v, t, p)["exact"]
        for v, t, p in zip(merged["variable"], merged["value"], merged["prediction"])
    ]
    merged = merged.merge(row_weights, on=["scenario_id", "variable"], how="left")
    merged["weight"] = merged["weight"].fillna(0.0)
    merged = _drop_zero_weight_households(merged, row_weights)
    merged["weighted_exact"] = merged["exact"] * merged["weight"]
    return (
        merged.groupby(["model", "scenario_id"])["weighted_exact"].sum().reset_index()
    )


def paired_bootstrap(
    first: pd.Series, second: pd.Series, draws: int = 10_000, seed: int = 20261014
) -> dict:
    """Household-resampled 95% intervals for two arms' means and their difference."""
    import numpy as np

    a = first.to_numpy(dtype=float)
    b = second.to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    index = rng.integers(0, len(a), size=(draws, len(a)))
    diff = b - a
    mean_a = a[index].mean(axis=1)
    mean_b = b[index].mean(axis=1)

    def interval(values):
        low, high = np.percentile(values, [2.5, 97.5])
        return [float(low), float(high)]

    return {
        "households": int(len(a)),
        "draws": draws,
        "seed": seed,
        "arm1_mean": float(a.mean()),
        "arm2_mean": float(b.mean()),
        "difference": float(b.mean() - a.mean()),
        "arm1_interval": interval(mean_a),
        "arm2_interval": interval(mean_b),
        "difference_interval": interval(mean_b - mean_a),
        # One difference for all three, so every household lands in exactly
        # one: comparing b with a + 1e-12 rounds differently from b - a at the
        # boundary (a found case: a = 0.125, b = a + 1e-12 landed in none).
        "households_better": int((diff > 1e-12).sum()),
        "households_worse": int((diff < -1e-12).sum()),
        "households_same": int((abs(diff) <= 1e-12).sum()),
    }


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
                "arm2_token_cost_usd": totals.get("token_cost_usd", totals["cost_usd"]),
                "arm2_web_searches": totals.get("web_searches", 0),
                "arm2_search_cost_usd": totals.get("search_cost_usd", 0.0),
                "arm2_model_seconds": totals["model_seconds"],
                "arm2_tool_seconds": totals["tool_seconds"],
                "arm2_wall_seconds": records[sid].get("wall_seconds"),
            }
        )
    frame = pd.DataFrame(rows).merge(
        grouped.reset_index(), on="scenario_id", how="left"
    )
    return frame


def search_log(records: Mapping[str, dict]) -> pd.DataFrame:
    """Every logged search, query and result URL, one row each."""
    rows = []
    for sid, record in sorted(records.items()):
        for turn in record.get("turns", []):
            for entry in turn.get("searches", []):
                queries = entry.get("queries") or [None]
                for query in queries:
                    rows.append(
                        {
                            "scenario_id": sid,
                            "turn": turn.get("index"),
                            "kind": entry.get("kind"),
                            "query": query,
                            "url": entry.get("url"),
                            "title": entry.get("title"),
                            "code": entry.get("code"),
                            "repeat": bool(entry.get("repeat")),
                        }
                    )
    return pd.DataFrame(
        rows,
        columns=[
            "scenario_id",
            "turn",
            "kind",
            "query",
            "url",
            "title",
            "code",
            "repeat",
        ],
    )


def search_audit(log: pd.DataFrame, results_visible: bool = True) -> dict:
    """Searches or results that touch the benchmark itself, or a blocked domain.

    ``flagged_households`` are those with either; their arm-2 scores are not
    evidence of web access without the benchmark. ``results_visible`` is false
    when the provider returns no result URLs (Gemini), so the audit sees only
    queries and cannot show what the model read.
    """

    def touches(text, needles) -> bool:
        text = str(text or "").lower()
        return any(n in text for n in needles)

    text = [
        " ".join(v for v in row if isinstance(v, str))
        for row in log[["query", "url", "title", "code"]].itertuples(index=False)
    ]
    # Boolean masks as arrays: an empty list would select no columns, not rows.
    mentions = log.loc[
        pd.array([touches(t, ("policybench",)) for t in text], dtype="boolean")
    ]
    blocked = log.loc[
        pd.array(
            [isinstance(u, str) and touches(u, BLOCKED_DOMAINS) for u in log["url"]],
            dtype="boolean",
        )
    ]

    def records(frame: pd.DataFrame) -> list[dict]:
        # JSON has no NaN: missing cells become null.
        return frame.astype(object).where(frame.notna(), None).to_dict(orient="records")

    # The reference engine's own sites: not blocked and not a flag, since a
    # web+PE model may read the tool's docs, but counted for the reader.
    engine = log.loc[
        pd.array(
            [touches(t, REFERENCE_ENGINE_MARKERS) for t in text],
            dtype="boolean",
        )
    ]
    return {
        "results_visible": results_visible,
        "reference_engine_entries": int(len(engine)),
        "logged_entries": int(len(log)),
        "queries": int(log["query"].notna().sum()),
        "result_urls": int(log["url"].notna().sum()),
        "policybench_mentions": records(mentions),
        "blocked_domain_urls": records(blocked),
        "flagged_households": sorted(
            set(mentions["scenario_id"]) | set(blocked["scenario_id"])
        ),
    }


def tool_use_summary(records: Mapping[str, dict]) -> dict:
    """How the model used the tool: calls, error kinds, and what it got wrong."""
    from collections import Counter

    problem_kinds: Counter = Counter()
    unknown_names: Counter = Counter()
    misplaced: Counter = Counter()
    requested: Counter = Counter()
    error_kinds: Counter = Counter()
    first_call_ok = 0
    households = 0
    calls_before_first_success = []
    for record in records.values():
        calls = [
            c
            for t in record.get("turns", [])
            for c in t.get("calls", [])
            if c.get("name") == TOOL_NAME
        ]
        if not calls:
            continue
        households += 1
        ok_index = next(
            (i for i, c in enumerate(calls) if "results" in (c.get("result") or {})),
            None,
        )
        first_call_ok += ok_index == 0
        calls_before_first_success.append(ok_index)
        for call in calls:
            result = call.get("result") or {}
            if "results" in result:
                try:
                    args = json.loads(call["arguments"])
                    requested.update(args.get("variables") or [])
                except (TypeError, ValueError):
                    pass
                continue
            error_kinds[result.get("error")] += 1
            for problem in result.get("problems", []):
                if "unknown variable" in problem:
                    problem_kinds["unknown variable"] += 1
                    found = re.search(r"unknown variable '([^']+)'", problem)
                    if found:
                        unknown_names[found.group(1)] += 1
                elif " variable; set it under " in problem:
                    problem_kinds["variable on the wrong entity"] += 1
                    misplaced[problem.split(": ", 1)[1].split(" is a ")[0]] += 1
                elif "period" in problem:
                    problem_kinds["bad period"] += 1
                elif "member" in problem:
                    problem_kinds["unit membership"] += 1
                elif "takes" in problem:
                    problem_kinds["wrong value type"] += 1
                else:
                    problem_kinds["other"] += 1
    never = sum(1 for i in calls_before_first_success if i is None)
    return {
        "households_using_tool": households,
        "first_call_succeeded": int(first_call_ok),
        "households_with_no_successful_call": int(never),
        "failed_calls_by_kind": dict(error_kinds),
        "validation_problems_by_kind": dict(problem_kinds.most_common()),
        "most_common_unknown_names": dict(unknown_names.most_common(15)),
        "most_common_misplaced_variables": dict(misplaced.most_common(10)),
        "most_requested_variables": dict(requested.most_common(30)),
    }


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

# Engine variables equal to an output's own variable on these households. In
# policyengine-us 2.41.0 spm_unit_payroll_tax is sum_contained_tax_units of
# employee_payroll_tax, and an SPM unit's total is the same whichever of the
# two the model asks for.
EQUIVALENT_ENGINE_VARIABLES = {"payroll_tax": ("employee_payroll_tax",)}

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
        if "household" in args:  # the flat feature's people list
            household = args["household"]
            household = (
                json.loads(household) if isinstance(household, str) else household
            )
            return [person["name"] for person in household["people"]]
        situation = args["situation"]
        situation = json.loads(situation) if isinstance(situation, str) else situation
        return list(situation["people"])
    except (KeyError, TypeError, ValueError):
        return []


def engine_variables_for_output(output: str) -> tuple[str, ...]:
    from policybench.ground_truth import _pe_variable_for_output

    return (
        _pe_variable_for_output(output, "us"),
        *EQUIVALENT_ENGINE_VARIABLES.get(output, ()),
    )


def tool_value_for_output(call: dict, scenario, output: str):
    """The value one successful call returned for a benchmark output, or None.

    The output's engine variable must be in the call's results at the 2026
    annual period. Person outputs read the model's person in the scenario's
    position (the prompt lists people in scenario order); group outputs take
    the board's aggregation over the returned units.
    """
    from policybench.ground_truth import _aggregation_for_output

    results = call["result"]["results"]
    entry = None
    for candidate in engine_variables_for_output(output):
        found = results.get(candidate)
        if (
            isinstance(found, dict)
            and "values" in found
            and str(found.get("period")) == str(YEAR)
        ):
            entry = found
            break
    if entry is None:
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
        numbers = []
        for item in values.values():
            if item is None or isinstance(item, str):
                return None  # a non-finite or non-numeric result has no value
            numbers.append(float(item))
        value = sum(numbers)
        if aggregation == "any_positive":
            value = float(value > 0)
    if isinstance(value, bool):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def submitted_matches(calls: list[dict], submitted, limit: int = 5) -> list[str]:
    """Tool results within $1 of a submitted amount, as variable[member]@period."""
    if submitted is None:
        return []
    matches = []
    for call in calls:
        for name, entry in call["result"]["results"].items():
            if not isinstance(entry, dict):
                continue
            for member, value in (entry.get("values") or {}).items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                if abs(float(value) - float(submitted)) <= 1.0:
                    label = f"{name}[{member}]@{entry.get('period')}"
                    if label not in matches:
                        matches.append(label)
    return matches[:limit]


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
        names = engine_variables_for_output(output)
        any_period = [
            c
            for c in calls
            if any(
                isinstance(c["result"]["results"].get(name), dict)
                and "values" in c["result"]["results"][name]
                for name in names
            )
        ]
        evidence["submitted_matches"] = submitted_matches(calls, submitted)
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
    each group's first unit is matched to the reference's. An input absent on
    one side shows as an empty dict; callers drop differences that are only an
    input left at the engine default (``_is_default_only``).
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


def output_values(system, situation: dict, scenario, outputs) -> dict:
    """Benchmark outputs from one simulation of a situation, people by position."""
    from policyengine_us import Simulation

    from policybench.ground_truth import (
        _aggregation_for_output,
        _pe_variable_for_output,
        _person_index_for_output,
    )

    try:
        simulation = Simulation(
            tax_benefit_system=system, situation=copy.deepcopy(situation)
        )
    except Exception:
        return {output: None for output in outputs}
    values = {}
    for output in outputs:
        try:
            array = simulation.calculate(_pe_variable_for_output(output, "us"), YEAR)
        except Exception:
            values[output] = None
            continue
        aggregation = _aggregation_for_output(output, "us")
        if aggregation == "person":
            index = _person_index_for_output(scenario, output)
            values[output] = (
                None if index is None or index >= len(array) else float(array[index])
            )
        else:
            total = float(array.sum())
            values[output] = (
                float(total > 0) if aggregation == "any_positive" else total
            )
    return values


def output_value(system, situation: dict, scenario, output: str) -> float | None:
    return output_values(system, situation, scenario, [output])[output]


def apply_reference_input(model: dict, reference: dict, diff: dict) -> dict | None:
    """The model's situation with one differing input set as the reference sets it.

    People are matched by position. A group input goes on the model's first
    unit of that group (a new unit holding everyone if the model left the group
    out); a unit-count difference replaces the model's group with the
    reference's, members renamed to the model's people. Returns None for a
    difference that cannot be applied (a different number of people).
    """
    situation = copy.deepcopy(model)
    model_names = list(situation.get("people", {}))
    reference_names = list(reference["people"])
    if len(model_names) != len(reference_names):
        return None
    rename = dict(zip(reference_names, model_names))
    variable = diff["variable"]
    if diff["entity"] == "person":
        person = situation["people"][rename[diff["reference_unit"]]]
        if diff["reference"] in ({}, None):
            person.pop(variable, None)
        else:
            person[variable] = copy.deepcopy(diff["reference"])
        return situation
    group = diff["entity"]
    if variable == "<units>":
        situation[group] = {
            name: {
                **copy.deepcopy(unit),
                "members": [rename[m] for m in unit["members"]],
            }
            for name, unit in reference[group].items()
        }
        return situation
    units = situation.setdefault(group, {})
    if not units:
        units[f"{group}_1"] = {"members": list(model_names)}
    unit = next(iter(units.values()))
    if diff["reference"] in ({}, None):
        unit.pop(variable, None)
    else:
        unit[variable] = copy.deepcopy(diff["reference"])
    return situation


def _amounts(side) -> list[float]:
    if not isinstance(side, dict):
        return []
    return [
        float(v)
        for v in side.values()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    ]


# Reviewed re-entries: (the reference's input, another engine input a model
# put the same stated amount in). Each pair was read in a transcript; an
# equal amount anywhere else is only a candidate, since a number can match
# by chance (scenario_018's $50 of interest beside 50 weekly hours).
REENTRY_PAIRS = frozenset(
    {
        # Sol, scenario_018: "taxable interest income" entered as the
        # engine's interest_income, the sum of taxable and tax-exempt interest.
        ("taxable_interest_income", "interest_income"),
        # Sol, scenario_088: "home mortgage interest" entered as
        # mortgage_interest, the sum of deductible and non-deductible interest.
        ("home_mortgage_interest", "mortgage_interest"),
    }
)


def _entered_as(cause: dict, diffs: list[dict]) -> tuple[list[str], list[str]]:
    """The model's other inputs, on the cause's unit and period, that hold
    its amount: (reviewed re-entries, other numeric candidates)."""
    wanted = {
        period: float(value)
        for period, value in (cause["reference"] or {}).items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    confirmed, candidates = [], []
    for other in diffs:
        if other is cause or other["entity"] != cause["entity"]:
            continue
        if other.get("model_unit") != cause.get("model_unit"):
            continue
        model_side = other["model"] if isinstance(other["model"], dict) else {}
        if not any(
            period in wanted
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and abs(float(value) - wanted[period]) <= 1.0
            for period, value in model_side.items()
        ):
            continue
        label = f"{other['entity']}.{other['variable']}"
        if (cause["variable"], other["variable"]) in REENTRY_PAIRS:
            confirmed.append(label)
        else:
            candidates.append(label)
    return confirmed, candidates


def _entered_elsewhere(cause: dict, diffs: list[dict]) -> bool:
    """Whether the model set this cause, or entered its amount elsewhere.

    A cause the model set itself (a non-empty model side) was entered
    differently. One the model left unset was still entered if a reviewed
    counterpart (``REENTRY_PAIRS``) holds the same amount, within $1, for the
    same person or unit and period: Sol's $10,777 under ``mortgage_interest``
    for a reference ``home_mortgage_interest``. Any other equal number is a
    candidate only.
    """
    if cause["model"] not in ({}, None):
        return True
    return bool(_entered_as(cause, diffs)[0])


def attribute_miss(
    system, model: dict, reference: dict, scenario, output: str, target, diffs
) -> dict:
    """Which differing inputs, set as the reference sets them, fix the output.

    Each difference is applied alone; the ones that bring the output within
    the board's tolerance of the reference are its single causes. When no
    single input does, every applicable difference is applied together, and
    if that fixes it, the necessary inputs are the ones whose omission from
    the full set leaves the output wrong (leave-one-out).

    ``mapping_kind`` reads the causes (single, else necessary):
    "entered_differently" when the model set one of them, or put a cause's
    amount under a reviewed counterpart (``_entered_elsewhere``); "left_out"
    otherwise. ``entered_as`` lists those counterparts, and
    ``entered_as_candidates`` any other input holding the same amount.
    """
    causes, cause_diffs = [], []
    for diff in diffs:
        situation = apply_reference_input(model, reference, diff)
        if situation is None:
            continue
        if hit(output, output_value(system, situation, scenario, output), target):
            causes.append(f"{diff['entity']}.{diff['variable']}")
            cause_diffs.append(diff)
    joint = None
    necessary, necessary_diffs = [], []
    if not causes and diffs:

        def apply_all(skip=None) -> dict:
            situation = model
            for diff in diffs:
                if diff is skip:
                    continue
                applied = apply_reference_input(situation, reference, diff)
                situation = applied if applied is not None else situation
            return situation

        joint = hit(output, output_value(system, apply_all(), scenario, output), target)
        if joint:
            for diff in diffs:
                value = output_value(system, apply_all(skip=diff), scenario, output)
                if not hit(output, value, target):
                    necessary.append(f"{diff['entity']}.{diff['variable']}")
                    necessary_diffs.append(diff)
    basis = cause_diffs or necessary_diffs
    kind = None
    if basis:
        kind = (
            "entered_differently"
            if any(_entered_elsewhere(d, diffs) for d in basis)
            else "left_out"
        )
    # The inputs that hold an unset cause's amount: evidence for
    # entered_differently, listed so a reader can tell a real re-entry
    # (interest_income for taxable_interest_income) from a coincidence.
    unset = [d for d in basis if d["model"] in ({}, None)]
    found = [_entered_as(d, diffs) for d in unset]
    return {
        "single_causes": causes,
        "all_differences_fix_it": joint,
        "necessary_inputs": necessary,
        "mapping_kind": kind,
        "entered_as": sorted({n for confirmed, _ in found for n in confirmed}),
        "entered_as_candidates": sorted({n for _, cand in found for n in cand}),
    }


def _entity_matches(call: dict, submitted, entities) -> list[str]:
    """Results of one call within $1 of the submitted value, on the output's
    entities only, as variable[member]@period."""
    if submitted is None:
        return []
    matches = []
    for name, entry in call["result"]["results"].items():
        if not isinstance(entry, dict):
            continue
        if entities is not None and entry.get("entity") not in entities:
            continue
        for member, value in (entry.get("values") or {}).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if abs(float(value) - float(submitted)) <= 1.0:
                label = f"{name}[{member}]@{entry.get('period')}"
                if label not in matches:
                    matches.append(label)
    return matches


def resolve_unread_output(
    verdict: dict,
    record: dict,
    scenario,
    output: str,
    submitted,
    board_value_for: Callable[[Any], float | None],
    output_entities=None,
    binary: bool = False,
) -> dict:
    """Settle a wrong_variable_or_period verdict with the board's own output.

    A model can read a variable other than the board's, such as a state's own
    ``ca_income_tax_before_refundable_credits``, so the output's engine
    variable is never computed. Numbers alone do not show which call an
    answer came from, so a verdict changes only on agreeing evidence:

    - The holding calls are the successful ones with a result within $1 of
      the submitted value on one of ``output_entities``, the entities of the
      output's engine variables (an equal ``employment_income`` on a person
      is not evidence for a tax-unit tax).
    - ``board_value_for`` computes the board's output on the situation of
      each holding call and of the main call, the one that computed the most
      of the household's outputs. Only if every one of them equals the
      submitted value does the miss become wrong_input_mapping, attributed
      on the holding call that computed the most outputs. A lone probe that
      happens to hold a summed answer cannot outvote the main situation.
    - Otherwise the verdict stands, with the main call's situation and board
      value as its evidence, every holding call's value listed, and a note
      when some agree and some do not.
    - A binary output is never reclassified: a 0 or 1 matches too much by
      chance.
    - Nor is a miss in a household where no call computed any of its
      outputs: every call ties at zero, so no situation is the main one
      (the tie rule would otherwise let the last probe vouch for itself).
    """
    if verdict.get("category") != "wrong_variable_or_period":
        return verdict
    variables = list(record["variables"])

    def key(call):
        return json.dumps(call.get("arguments"), sort_keys=True, default=str)

    calls = _successful_calls(record)
    main, main_count = main_call_and_count(record, scenario, variables)
    no_main = main is not None and main_count == 0
    holding = (
        []
        if binary
        else [c for c in calls if _entity_matches(c, submitted, output_entities)]
    )
    values: dict[str, float | None] = {}
    for call in holding + ([main] if main is not None else []):
        if key(call) not in values:
            values[key(call)] = board_value_for(call.get("arguments"))

    def agrees(call) -> bool:
        value = values[key(call)]
        return value is not None and hit(output, submitted, value)

    if (
        holding
        and not no_main
        and main is not None
        and all(agrees(c) for c in holding)
        and agrees(main)
    ):
        call = main_call({"turns": [{"calls": holding}]}, scenario, variables)
        read = ", ".join(_entity_matches(call, submitted, output_entities))
        return {
            **verdict,
            "category": "wrong_input_mapping",
            "detail": f"read {read}, equal to the board's output on that situation",
            "answering_call": "holds the submitted value",
            "holding_calls": len(holding),
            "holding_board_values": [values[key(c)] for c in holding],
            "board_output_on_situation": values[key(call)],
            "tool_value": values[key(call)],
            "call_arguments": call.get("arguments"),
        }
    if main is None:
        return verdict
    settled = {
        **verdict,
        "answering_call": "main call",
        "holding_calls": len(holding),
        "holding_board_values": [values[key(c)] for c in holding],
        "board_output_on_situation": values[key(main)],
        "call_arguments": main.get("arguments"),
    }
    if no_main:
        settled["detail"] = (
            "no call computed any of the household's outputs, so no situation "
            "is the main one; not reclassified"
        )
    elif values[key(main)] is None:
        settled["detail"] = (
            "the main situation could not be computed (it no longer validates); "
            "not reclassified"
        )
    elif not holding and not binary and agrees(main):
        settled["detail"] = (
            "the main situation's board output equals the answer, but no call's "
            "results hold it (an answer the model built itself); not reclassified"
        )
    elif holding and any(agrees(c) for c in holding + [main]):
        settled["detail"] = (
            "ambiguous: the situations holding the submitted value, or the "
            "main one, disagree on the board's output"
        )
    return settled


def main_call_and_count(
    record: dict, scenario, outputs: list[str]
) -> tuple[dict | None, int]:
    """The successful call that computed the most of the household's outputs,
    and how many it computed (-1 with no successful call)."""
    best, best_count = None, -1
    for call in _successful_calls(record):
        count = sum(
            tool_value_for_output(call, scenario, output) is not None
            for output in outputs
        )
        if count >= best_count:
            best, best_count = call, count
    return best, best_count


def main_call(record: dict, scenario, outputs: list[str]) -> dict | None:
    """The successful call that computed the most of the household's outputs.

    A model often ends with a narrow probe on a skeleton situation (one
    person, no state); the situation its answers rest on is the one that
    computed the outputs. Ties go to the later call.
    """
    return main_call_and_count(record, scenario, outputs)[0]


def situation_fidelity(
    records, board, system, registry, defaults, out: Path, features=frozenset()
) -> None:
    """How each household's main situation differs from the reference's.

    The main situation is ``main_call``'s: the successful call that computed
    the most of the household's outputs. (``classify_miss`` reads the last call
    that computed the missed output, which is what the answer rests on.)

    Inputs left at the engine default on one side are dropped. A remaining
    difference is reported with whether setting it as the reference does would
    move any scored output beyond the board's tolerance, so a harmless
    difference (another name for the same fact, a formula input set
    explicitly) is told apart from one that matters.
    """
    scored = board["scored"]
    rows = []
    for sid, record in sorted(records.items()):
        outputs = list(scored[scored.scenario_id == sid].variable)
        call = main_call(record, board["scenarios"][sid], outputs)
        if call is None:
            rows.append({"scenario_id": sid, "differences": None})
            continue
        request, _ = normalize_request(call["arguments"], registry, features=features)
        if request is None:
            rows.append({"scenario_id": sid, "differences": None})
            continue
        scenario = board["scenarios"][sid]
        reference = scenario.to_pe_household()
        diffs = [
            d
            for d in situation_diff(request["situation"], reference, scenario)
            if not _is_default_only(d, defaults)
        ]
        base = output_values(system, request["situation"], scenario, outputs)
        detail = []
        for diff in diffs:
            applied = apply_reference_input(request["situation"], reference, diff)
            moved = None
            if applied is not None:
                after = output_values(system, applied, scenario, outputs)
                moved = [v for v in outputs if not hit(v, after[v], base[v])]
            detail.append(
                {
                    "input": f"{diff['entity']}.{diff['variable']}",
                    "reference": diff.get("reference"),
                    "model": diff.get("model"),
                    "outputs_it_moves": moved,
                }
            )
        rows.append(
            {
                "scenario_id": sid,
                "differences": len(diffs),
                "differences_that_move_an_output": sum(
                    1 for d in detail if d["outputs_it_moves"]
                ),
                "detail": json.dumps(detail, default=str),
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(out / "situation_fidelity.csv", index=False)
    print(
        f"situations matching the reference on every non-default input: "
        f"{int((frame.differences == 0).sum())} of {len(frame)}"
    )


def command_diagnose(args) -> None:
    from policybench.spec import metric_type_for_output

    snapshot = board_path(args)
    board = load_board(snapshot)
    out = Path(args.out_dir)
    records = load_records(out)
    # A run's calls are read as its own tool version read them.
    features = arm_features(records_arm(records)) or frozenset()
    rows_path = out / "scored_rows.csv"
    if not rows_path.exists():
        raise SystemExit("run score first")
    rows = pd.read_csv(rows_path)
    misses = rows[~rows.arm2_hit.astype(bool)]
    registry = None
    defaults = {}
    if not args.no_engine_defaults:
        _require_engine(snapshot)
        system = build_tool_system(reform=True, snapshot=snapshot)
        registry = build_registry(system)
        defaults = {
            name: system.variables[name].default_value for name in system.variables
        }
    if registry is not None:
        situation_fidelity(records, board, system, registry, defaults, out, features)
    out_rows = []
    if misses.empty:
        print("no arm-2 misses")
        pd.DataFrame(columns=["scenario_id", "variable", "category"]).to_csv(
            out / "misses.csv", index=False
        )
        return
    for row in misses.itertuples():
        record = records[row.scenario_id]
        scenario = board["scenarios"][row.scenario_id]
        submitted = None if pd.isna(row.arm2) else float(row.arm2)
        verdict = classify_miss(
            record, scenario, row.variable, submitted, row.reference
        )
        if registry is not None:

            def board_value_for(arguments, scenario=scenario, output=row.variable):
                request, _ = normalize_request(arguments, registry, features=features)
                if request is None:
                    return None
                return output_value(system, request["situation"], scenario, output)

            entities = {
                registry[name].entity
                for name in engine_variables_for_output(row.variable)
                if name in registry
            }
            verdict = resolve_unread_output(
                verdict,
                record,
                scenario,
                row.variable,
                submitted,
                board_value_for,
                output_entities=entities or None,
                binary=metric_type_for_output(row.variable) != "amount",
            )
        diff = []
        attribution = {}
        arguments = verdict.get("call_arguments")
        if arguments is not None and registry is not None:
            request, _ = normalize_request(arguments, registry, features=features)
            if request is not None:
                reference_situation = scenario.to_pe_household()
                diff = situation_diff(
                    request["situation"], reference_situation, scenario
                )
                diff = [d for d in diff if not _is_default_only(d, defaults)]
                if verdict["category"] == "wrong_input_mapping":
                    attribution = attribute_miss(
                        system,
                        request["situation"],
                        reference_situation,
                        scenario,
                        row.variable,
                        row.reference,
                        diff,
                    )
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
                "submitted_matches": json.dumps(verdict.get("submitted_matches")),
                "single_causes": json.dumps(attribution.get("single_causes")),
                "all_differences_fix_it": attribution.get("all_differences_fix_it"),
                "necessary_inputs": json.dumps(attribution.get("necessary_inputs")),
                "mapping_kind": attribution.get("mapping_kind"),
                "entered_as": json.dumps(attribution.get("entered_as")),
                "entered_as_candidates": json.dumps(
                    attribution.get("entered_as_candidates")
                ),
                "holding_board_values": json.dumps(verdict.get("holding_board_values")),
                "answering_call": verdict.get("answering_call"),
                "board_output_on_situation": verdict.get("board_output_on_situation"),
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
        p.add_argument(
            "--board",
            default=str(SNAPSHOT),
            help="the frozen board (default) or a household set from "
            "scripts/household_set.py",
        )
        if name == "run":
            p.add_argument(
                "--model",
                default=MODEL_NAME,
                help="a board model name (policybench.config.MODELS)",
            )
            p.add_argument(
                "--arm",
                default="pe",
                help="the tools: none, PolicyEngine (pe, pe2, pe3, or pe: plus "
                "calculator features joined by +), web search (web), or both "
                "(web+pe)",
            )
            p.add_argument(
                "--prompt",
                choices=PROMPT_VERSIONS,
                default="v1",
                help="the board's prompt (v1), or v1 with its four "
                "PolicyEngine-naming definitions made neutral (v2-pilot)",
            )
            p.add_argument(
                "--forbid-benchmark-search",
                action="store_true",
                help="tell a web arm not to search for PolicyBench or its answers",
            )
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
            p.add_argument(
                "--complete-only",
                action="store_true",
                help="score only households whose conversation completed",
            )
            p.add_argument(
                "--baseline-dir",
                help="on a household set, the same model's no-tools run: the "
                "baseline each arm is compared with",
            )
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
