"""Data-driven manuscript values for the PolicyBench paper.

Every quantitative claim in ``paper/index.qmd`` reads from the single module
level instance ``r`` exposed here, mirroring the ``whatnut`` paper pattern. The
accessors return already-formatted strings (``f"{x:.1f}"``, ranges, model
names, leaderboards) computed from the FROZEN manuscript snapshot under
``paper/snapshot/20260501/`` and its ``manifest.json`` -- never from the live
``results/`` run output.

Sources, in order of authority:

* ``paper/snapshot/20260501/manifest.json`` -- snapshot/response dates, the
  US source-run label, PolicyEngine versions, the populace dataset id, and the
  declared scope (households, output groups, models).
* ``paper/snapshot/20260501/runs/<us_label>/data.json.gz`` -- the frozen US
  dashboard payload: the frozen model roster, ``modelStats`` exact-match and
  within-1% scores, per-output ``programStats`` and ``failureModes``
  breakdowns, household and scored-output counts.
* ``paper/snapshot/20260501/model_serving_config.json`` -- the per-model
  serving treatments, their evidence kinds, and the registry commit.
* the frozen audit annotations dir (``manifest['audit_annotation_artifacts']``)
  -- the rows selected by the legacy threshold score, their adjudicated
  failure sources, and the developer adjudications that settle every
  reference-suspect flag.

The qmd imports ``r`` once in an ``#| echo: false`` setup cell and then every
inline number is a ```{python} r.field``` placeholder, so a future
snapshot refresh updates the prose with no edits to the manuscript text.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from functools import cached_property
from pathlib import Path

import pandas as pd

from policybench.reference_exclusions import (
    ENGINE_DEFECT,
    LATER_LAW,
    UNLISTED_INPUT,
    exclusion_basis,
    exclusion_keys,
    load_reference_exclusions,
)
from policybench.reference_exclusions import FILENAME as EXCLUSIONS_FILENAME
from policybench.snapshot_payload import read_run_payload
from policybench.spec import metric_type_for_output

# ``paper_results`` lives in ``policybench/``; the repo root is one level up.
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "paper" / "snapshot" / "20260501"

# The 2026-09-29 move from policyengine-us 1.755.4 to 2.15.17. Its audit,
# reference_audit/2026-09-28, holds the publication check, the sweep timing
# and the re-run sweeps below; they describe that upgrade, whichever upgrades
# follow it (the engine_upgrade_* accessors follow the last).
SEPTEMBER_UPGRADE_DATE = "2026-09-29"
UPGRADE_VERIFICATION = ROOT / "reference_audit" / "2026-09-28" / "verification"
# The sweep that rechecked every reference on the newest policyengine-us
# release when PolicyBench checked PyPI before publishing, with the fix module
# the references were built with.
PUBLICATION_CHECK_SWEEP = UPGRADE_VERIFICATION / "latest_final_2170.csv"
# When the reference sweep began, each release's PyPI upload time, and when
# PolicyBench read PyPI for the publication check.
SWEEP_TIMING = UPGRADE_VERIFICATION / "sweep_timing.json"
# What each exclusion sweep re-run on the reference engine moves.
RERUN_SWEEPS = UPGRADE_VERIFICATION / "rerun_sweeps.json"

# The 2026-10-09 move's audit: its builder, and the timing record and
# publication check scripts/sweep_timing.py writes there.
OCTOBER_UPGRADE_AUDIT = "reference_audit/2026-10-09-engine-upgrade"
OCTOBER_SWEEP_TIMING = (
    ROOT / OCTOBER_UPGRADE_AUDIT / "verification" / "sweep_timing.json"
)

# How the paper names each engine defect an upgrade can fix, after the audits'
# own statements of them (reference_audit/2026-09-22/root_causes.json and
# reference_audit/2026-10-05-reference-adversary/proposed_changes.json). An
# upgrade that restores an output whose root cause has no name here stops the
# render, so a new fix is named before it is published.
ROOT_CAUSE_LABELS = {
    "az_standard_deduction_indexing": "Arizona's standard deduction indexing",
    "oh_medical_deduction_premiums": (
        "Ohio's medical deduction for health insurance premiums"
    ),
    "co_sales_tax_refund_surplus": "Colorado's 2026 sales tax refund",
    "ny_cdcc_606_c2": "New York's 2026 child and dependent care credit",
    "r01_ira_compensation": (
        "the IRA deduction's compensation limit and a dependent's contributions"
    ),
    "r02_ira_219g": "the IRA deduction's active-participant phase-out",
    "r03_estate_income": "estate income in gross income",
    "r05_nj_worker_ui": "New Jersey's worker unemployment and workforce contributions",
    "r06_wi_act15_before_refundable": (
        "Wisconsin's retirement income exclusion before refundable credits"
    ),
    "r07_idaho_health_premiums": "Idaho's subtraction for health insurance premiums",
    "r08_eitc_earned_income_deferrals": (
        "elective deferrals in the earned income behind the EITC"
    ),
    "r11_ca_itemized_conformity": "California's itemized deduction conformity",
    "r22_ma_part_a_loss_offset": "Massachusetts's Part A capital loss offset",
    "r30_snap_heat_and_eat_sua": "the heat-and-eat SNAP utility allowance",
    "r32_wi_capital_gain_distributions": (
        "Wisconsin's capital gain subtraction for distributions"
    ),
}
# The same for the cause of a scored reference an upgrade changes.
CHANGE_CAUSE_LABELS = {
    "id_permanent_building_fund_tax": (
        "Idaho's $10 permanent building fund tax (Idaho Code 63-3082), which "
        "policyengine-us now counts in state income tax"
    ),
}
UPSTREAM_PR = re.compile(r"policyengine-us#(\d+)")

# The 2026-10-05 review of release dashboard-data-20260930. Each of its three
# audits recomputed every output on the reference engine under readings of an
# input the prompt never states. Each entry names the sweep's CSV, the column
# holding the reference system's own value (the sweep's baseline), and the
# columns holding the readings and checks it ran. The records the review added
# carry ``decided_on`` = REVIEW_DATE.
REVIEW_DATE = "2026-10-05"
# The day Max ruled on the reference adversary's records (d1022) and the
# Louisiana records (d994); each such record names its ruling in ``decision``.
RULING_DATE = "2026-10-06"
REVIEW_SWEEPS: dict[str, tuple[Path, str, tuple[str, ...]]] = {
    # State income tax in the federal SALT deduction
    # (reference_audit/2026-10-05/README.md).
    "salt_withholding": (
        ROOT
        / "reference_audit"
        / "2026-10-05"
        / "verification"
        / "sweep_salt_withholding.csv",
        "baseline",
        ("liability", "net", "zero"),
    ),
    # Medicare enrollment and the Part B premium in medical expenses
    # (reference_audit/2026-10-05-medicare-part-b/README.md).
    "medicare_part_b": (
        ROOT
        / "reference_audit"
        / "2026-10-05-medicare-part-b"
        / "verification"
        / "sweep_part_b.csv",
        "baseline",
        ("no_part_b", "not_enrolled", "not_enrolled_direct", "irmaa_from_2026_income"),
    ),
    # The optional employer pass-through of state paid-leave premiums
    # (reference_audit/2026-10-05-payroll/README.md).
    "payroll_optional_shares": (
        ROOT
        / "reference_audit"
        / "2026-10-05-payroll"
        / "verification"
        / "sweep_payroll_scope.csv",
        "final",
        ("scoped",),
    ),
}

NUMBER_WORDS = {
    0: "no",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}


def _series(parts: list[str]) -> str:
    """'a', 'a and b', or 'a, b and c'."""
    if len(parts) <= 2:
        return " and ".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def count_word(n: int) -> str:
    """A count as the paper writes it: a word up to ten, digits above."""
    return NUMBER_WORDS.get(n, f"{n:,}")


def moves_beyond_tolerance(variable: str, before: float, after: float) -> bool:
    """Whether a value change leaves the exact-match tolerance: more than $1
    for an amount output, any change for a 0/1 flag."""
    if metric_type_for_output(variable) == "amount":
        return abs(after - before) > 1
    return after != before


def partition_rerun_sweep_moves(
    summary: dict, excluded: frozenset[tuple[str, str]] | set[tuple[str, str]]
) -> dict[str, list[tuple[str, str, str]]]:
    """Split what the re-run sweeps move (verification/rerun_sweeps.json).

    Each listed move is (sweep, scenario_id, variable), compared with the
    sweep's own baseline (the same calculation without its fix or reading):
    scored outputs beyond the exact-match tolerance, scored outputs moved
    within it, and excluded outputs.
    """
    groups: dict[str, list[tuple[str, str, str]]] = {
        "scored_beyond_tolerance": [],
        "scored_within_tolerance": [],
        "excluded": [],
    }
    for sweep in summary["sweeps"]:
        for move in sweep["moves"]:
            if move["recomputed"] == move["baseline"]:
                continue
            key = (sweep["sweep"], move["scenario_id"], move["variable"])
            if (move["scenario_id"], move["variable"]) in excluded:
                groups["excluded"].append(key)
            elif moves_beyond_tolerance(
                move["variable"], move["baseline"], move["recomputed"]
            ):
                groups["scored_beyond_tolerance"].append(key)
            else:
                groups["scored_within_tolerance"].append(key)
    return groups


def partition_review_sweep_moves(
    moves: list[tuple[str, str, str, float, float]],
    excluded_before: frozenset[tuple[str, str]] | set[tuple[str, str]],
    excluded_now: frozenset[tuple[str, str]] | set[tuple[str, str]],
) -> dict[str, list[tuple[str, str, str]]]:
    """Split what the 2026-10-05 review's sweeps move.

    Each move is (sweep, scenario_id, variable, baseline, recomputed) for one
    reading or check whose value differs from the sweep's baseline. A move of
    an output excluded before the review is ``excluded_before``; of an output
    the review excluded, ``newly_excluded``; of an output still scored,
    ``scored_beyond_tolerance`` or ``scored_within_tolerance``. Every move
    lands in exactly one group, keyed (sweep, scenario_id, variable).
    """
    groups: dict[str, list[tuple[str, str, str]]] = {
        "excluded_before": [],
        "newly_excluded": [],
        "scored_beyond_tolerance": [],
        "scored_within_tolerance": [],
    }
    for sweep, scenario_id, variable, baseline, recomputed in moves:
        output = (scenario_id, variable)
        key = (sweep, scenario_id, variable)
        if output in excluded_before:
            groups["excluded_before"].append(key)
        elif output in excluded_now:
            groups["newly_excluded"].append(key)
        elif moves_beyond_tolerance(variable, baseline, recomputed):
            groups["scored_beyond_tolerance"].append(key)
        else:
            groups["scored_within_tolerance"].append(key)
    if sum(len(group) for group in groups.values()) != len(moves):
        raise AssertionError("review sweep partition lost or duplicated a move")
    return groups


def partition_engine_upgrade_changes(
    changes: list[dict],
    excluded: frozenset[tuple[str, str]] | set[tuple[str, str]],
    restored: frozenset[tuple[str, str]] | set[tuple[str, str]] = frozenset(),
) -> dict[str, list[dict]]:
    """Split an engine upgrade's changed outputs into four disjoint groups.

    ``excluded`` is the exclusion record once the upgrade was decided, and
    ``restored`` the excluded outputs the upgrade returned to scoring at the
    new engine's values. A change to an excluded output is a new exclusion; a
    change to a restored output is a restoration. Any other change is scored,
    and moves beyond the exact-match tolerance ($1 for an amount, any change
    for a 0/1 flag) or within it. Every change lands in exactly one group, so
    the four counts add up to the revision's changed list.
    """
    both = set(excluded) & set(restored)
    if both:
        raise ValueError(f"outputs both excluded and restored: {sorted(both)}")
    partition: dict[str, list[dict]] = {
        "scored_changes": [],
        "within_tolerance": [],
        "new_exclusions": [],
        "restored": [],
    }
    for change in changes:
        key = (change["scenario_id"], change["variable"])
        if key in excluded:
            partition["new_exclusions"].append(change)
            continue
        if key in restored:
            partition["restored"].append(change)
            continue
        moved = abs(change["regenerated"] - change["previous"])
        amount = metric_type_for_output(change["variable"]) == "amount"
        beyond = moved > 1 if amount else moved > 0
        partition["scored_changes" if beyond else "within_tolerance"].append(change)
    if sum(len(group) for group in partition.values()) != len(changes):
        raise AssertionError(
            "engine upgrade partition lost or duplicated a change: "
            f"{ {name: len(group) for name, group in partition.items()} } "
            f"of {len(changes)}"
        )
    return partition


def engine_version_number(label: str) -> str:
    """'policyengine-us 2.15.17' -> '2.15.17' (a bare version is returned as is)."""
    return label.removeprefix("policyengine-us ")


def engine_version_key(version: str) -> tuple[int, ...]:
    """Numeric sort key of a policyengine-us release, so 2.4.0 < 2.15.17."""
    return tuple(int(part) for part in engine_version_number(version).split("."))


def engine_version_count_phrase(counts: dict[str, int]) -> str:
    """'52 computed with policyengine-us 1.755.4, 12 with 2.15.17': one clause
    per engine, oldest release first, for any number of engines."""
    ordered = sorted(counts, key=engine_version_key)
    clauses = [f"{counts[version]:,} with {version}" for version in ordered]
    if clauses:
        clauses[0] = (
            f"{counts[ordered[0]]:,} computed with policyengine-us {ordered[0]}"
        )
    return ", ".join(clauses)


def _key(entry: dict) -> tuple[str, str]:
    return entry["scenario_id"], entry.get("variable", "snap")


def exclusions_in_place(
    exclusions: list[dict], revisions: list[dict], date: str, *, include_day: bool
) -> list[dict]:
    """The exclusion records in place just before ``date`` (UTC day) or, with
    ``include_day``, at its end: records decided by then and not yet removed.

    ``exclusions`` is the current record. A revision that returns excluded
    outputs to scoring lists each in ``regenerated_exclusions`` with the
    record it removes (``record``), so the record as it stood at any earlier
    date can be rebuilt: a record a later revision removed was still in place.
    """

    def by_then(day: str) -> bool:
        return day <= date if include_day else day < date

    history = [(record, None) for record in exclusions] + [
        (entry["record"], revision["date"])
        for revision in revisions
        for entry in revision.get("regenerated_exclusions", [])
    ]
    return [
        record
        for record, removed_on in history
        if by_then(record["decided_on"])
        and (removed_on is None or not by_then(removed_on))
    ]


class EngineUpgrade:
    """One ``engine_upgrade`` revision of the reference sidecar, with the
    exclusion record as it stood around it.

    ``excluded_before`` holds the outputs excluded when the upgrade began:
    records decided before its date and not removed before it. ``excluded``
    holds those excluded once it was decided: records decided by the end of
    its date and not removed by then. A record decided after the upgrade never
    counts here, and a record a later revision removed still does.
    ``restored`` holds the outputs the upgrade returned to scoring (its
    ``regenerated_exclusions``).
    """

    def __init__(
        self,
        revision: dict,
        excluded_before: frozenset[tuple[str, str]],
        excluded: frozenset[tuple[str, str]],
    ):
        self.revision = revision
        self.excluded_before = excluded_before
        self.excluded = excluded
        self.restored = frozenset(
            _key(entry) for entry in revision.get("regenerated_exclusions", [])
        )

    def __repr__(self) -> str:
        return (
            f"EngineUpgrade({self.date}: {self.previous_engine_version} -> "
            f"{self.engine_version})"
        )

    @property
    def date(self) -> str:
        return self.revision["date"]

    @property
    def engine_version(self) -> str:
        return engine_version_number(self.revision["engine_version"])

    @property
    def previous_engine_version(self) -> str:
        return engine_version_number(self.revision["previous_engine_version"])

    @property
    def changes(self) -> list[dict]:
        return self.revision["changed"]

    @cached_property
    def partition(self) -> dict[str, list[dict]]:
        """The changed outputs, split into scored changes beyond the
        exact-match tolerance, scored changes within it, new exclusions and
        restorations. Refuses a change to an output excluded both before and
        after the upgrade: an excluded output keeps the value it was decided
        on (rule 5)."""
        kept = (self.excluded_before & self.excluded) - self.restored
        touched = sorted(kept & {_key(change) for change in self.changes})
        if touched:
            raise ValueError(
                f"the {self.date} upgrade changes outputs it kept excluded: {touched}"
            )
        return partition_engine_upgrade_changes(
            self.changes, self.excluded - self.excluded_before, self.restored
        )

    @property
    def scored_change_count(self) -> int:
        return len(self.partition["scored_changes"])

    @property
    def within_tolerance_count(self) -> int:
        return len(self.partition["within_tolerance"])

    @property
    def new_exclusion_count(self) -> int:
        return len(self.partition["new_exclusions"])

    @property
    def restored_count(self) -> int:
        return len(self.restored)

    @property
    def rechecked(self) -> list[dict]:
        """Excluded outputs whose value moves on the new engine; each stays
        excluded with the value it was decided on."""
        return self.revision.get("excluded_outputs_rechecked", [])

    @property
    def rechecked_count(self) -> int:
        return len(self.rechecked)

    def rechecked_value(self, record: dict) -> float:
        """A rechecked output's value on the new engine (``value_on_<ver>``)."""
        return record["value_on_" + self.engine_version.replace(".", "_")]


def engine_upgrades_from(
    revisions: list[dict], exclusions: list[dict]
) -> list[EngineUpgrade]:
    """The sidecar's engine upgrades, oldest first, each with the exclusion
    record as it stood around it (``exclusions_in_place``). Refuses a chain
    in which an upgrade does not start from the engine the one before it
    moved to."""

    def in_place(date: str, include_day: bool) -> frozenset[tuple[str, str]]:
        return frozenset(
            _key(record)
            for record in exclusions_in_place(
                exclusions, revisions, date, include_day=include_day
            )
        )

    upgrades = [
        EngineUpgrade(
            revision,
            excluded_before=in_place(revision["date"], False),
            excluded=in_place(revision["date"], True),
        )
        for revision in revisions
        if revision.get("kind") == "engine_upgrade"
    ]
    for before, after in zip(upgrades, upgrades[1:]):
        if after.previous_engine_version != before.engine_version:
            raise ValueError(
                f"the {after.date} upgrade does not start from "
                f"{before.engine_version}, the engine the {before.date} upgrade "
                f"moved to: {after.previous_engine_version}"
            )
    return upgrades


def references_as_of(
    references: dict[tuple[str, str], float], revisions: list[dict], date: str
) -> dict[tuple[str, str], float]:
    """The references as they stood at the end of ``date``: ``references``
    with every later revision's changes undone, newest first. Refuses a change
    whose regenerated value is not where the later references stand."""
    values = dict(references)
    for revision in reversed(revisions):
        if revision["date"] <= date:
            continue
        for change in reversed(revision.get("changed", [])):
            key = _key(change)
            if abs(values[key] - change["regenerated"]) > 1e-6:
                raise ValueError(
                    f"{key}: the {revision['date']} revision does not end at "
                    f"the later reference ({change['regenerated']} != {values[key]})"
                )
            values[key] = change["previous"]
    return values


# Human-readable model names for the frozen roster. Aliases that do not
# appear here fall back to a humanized form of the PolicyBench id.
MODEL_DISPLAY_NAMES = {
    "gpt-6-astra": "GPT-6 Astra",
    "gpt-6-sol": "GPT-6 Sol",
    "gpt-6.1-sol": "GPT-6.1 Sol",
    "gpt-6-luna": "GPT-6 Luna",
    "gpt-5.6-sol": "GPT-5.6 Sol",
    "gpt-5.6-terra": "GPT-5.6 Terra",
    "gpt-5.6-luna": "GPT-5.6 Luna",
    "claude-fable-5.1": "Claude Fable 5.1",
    "claude-opus-5.5": "Claude Opus 5.5",
    "claude-sonnet-5.5": "Claude Sonnet 5.5",
    "claude-fable-5": "Claude Fable 5",
    "claude-sonnet-5": "Claude Sonnet 5",
    "ox-alpha": "GLM-5.3-Flash (preview)",
    "grok-4.5": "Grok 4.5",
    "grok-4.6": "Grok 4.6",
    "grok-4.7": "Grok 4.7",
    "deepseek-v4-pro": "DeepSeek V4 Pro",
    "deepseek-v4-pro-0813": "DeepSeek V4 Pro 0813",
    "deepseek-v4-flash-0731": "DeepSeek V4 Flash 0731",
    "deepseek-v4.1-flash": "DeepSeek V4.1 Flash",
    "claude-opus-5": "Claude Opus 5",
    "gemini-3.8-flash": "Gemini 3.8 Flash",
    "gemini-3.7-flash": "Gemini 3.7 Flash",
    "gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite",
    "gemini-3.6-flash": "Gemini 3.6 Flash",
    "kimi-k3": "Kimi K3",
    "kimi-k2.6": "Kimi K2.6",
    "glm-5.3": "GLM-5.3",
    "glm-5.2": "GLM-5.2",
    "minimax-m3": "MiniMax M3",
    "qwen-3.7-max": "Qwen3.7-max",
    "qwen3.8-max": "Qwen3.8-Max",
    "inkling": "Inkling",
    "grok-build-0.1": "Grok Build 0.1",
    "claude-opus-4.8": "Claude Opus 4.8",
    "claude-opus-4.7": "Claude Opus 4.7",
    "claude-sonnet-4.6": "Claude Sonnet 4.6",
    "claude-haiku-5.5": "Claude Haiku 5.5",
    "claude-haiku-4.5": "Claude Haiku 4.5",
    "grok-4.3": "Grok 4.3",
    "gpt-5.5": "GPT-5.5",
    "gpt-5.4-mini": "GPT-5.4 mini",
    "gpt-5.4-nano": "GPT-5.4 nano",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro Preview",
    "gemini-3.5-flash": "Gemini 3.5 Flash",
    "gemini-3-flash-preview": "Gemini 3 Flash Preview",
    "gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash Lite Preview",
}

# Human-readable labels for the amount outputs the prose names by hand. Person
# eligibility flags and the remaining amount outputs fall back to a humanized
# form of the variable id (see ``_humanize_variable``).
OUTPUT_DISPLAY_NAMES = {
    "federal_income_tax_before_refundable_credits": (
        "federal income tax before refundable credits"
    ),
    "state_income_tax_before_refundable_credits": (
        "state income tax before refundable credits"
    ),
    "state_refundable_credits": "state refundable credits",
    "federal_refundable_credits": "federal refundable credits",
    "local_income_tax": "local income tax",
    "payroll_tax": "payroll tax",
    "self_employment_tax": "self-employment tax",
    "snap": "SNAP",
    "ssi": "SSI",
    "tanf": "TANF",
}

# Population-construction figures for the certified populace build this run
# used (populace-us-2024-5da5a95-20260611, populace_us_2024). These describe
# the upstream dataset, not the 100-household snapshot, so they cannot be read
# from the frozen run payload. They are computed once from the dataset and are
# reproducible at build time via, from the repo root::
#
#     from policybench import scenarios
#     df, _, _ = scenarios.load_certified_us_person_frame()
#     df["is_adult"] = df["age"] >= 18
#     n_people, n_households = len(df), df["household_id"].nunique()
#     n_eligible = len(scenarios._eligible_households(df))
#
# Loading the dataset and building a full US Simulation is too heavy to run on
# every paper render, so the verified values are pinned here against the build
# id in the manifest. ``test`` is intentionally omitted -- this module stays
# importable without a test dependency, per the task spec.
POPULACE_PEOPLE = 160_858
POPULACE_HOUSEHOLDS = 75_112
POPULACE_ELIGIBLE_HOUSEHOLDS = 63_128


def _humanize_variable(variable: str) -> str:
    """Fallback readable label for an output id not in the curated map."""
    text = variable.replace("person_", "").replace("_eligible", " eligibility")
    return text.replace("_", " ")


def _ordinal_join(items: list[str]) -> str:
    """Join a list as 'a, b, and c' (Oxford comma)."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _sentence_count(value: int) -> str:
    """Format a small count as a word when it opens a sentence."""
    words = (
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
    )
    rendered = words[value] if 0 <= value < len(words) else f"{value:,}"
    return rendered.capitalize()


class PaperResults:
    """Lazy accessors over the frozen snapshot, manifest, and audit.

    Each underlying artifact is loaded once on first access via
    ``cached_property``. Accessors return formatted strings ready to drop into
    the manuscript prose.
    """

    # ----- raw artifact loaders ------------------------------------------
    @cached_property
    def manifest(self) -> dict:
        return json.loads((SNAPSHOT_DIR / "manifest.json").read_text())

    @cached_property
    def us_run_label(self) -> str:
        return self.manifest["source_run_labels"]["us"]

    @cached_property
    def dashboard(self) -> dict:
        return read_run_payload(SNAPSHOT_DIR / "runs" / self.us_run_label)

    @cached_property
    def serving_config(self) -> dict:
        return json.loads((SNAPSHOT_DIR / "model_serving_config.json").read_text())

    @cached_property
    def reference_meta(self) -> dict:
        run_dir = SNAPSHOT_DIR / "runs" / self.us_run_label
        meta = json.loads((run_dir / "reference_outputs.csv.meta.json").read_text())
        return meta["policyengine_bundles"]["us"]

    @cached_property
    def sample_bundle(self) -> dict:
        """Runtime metadata of the scenario draw: the certified dataset build
        the benchmark households were sampled from."""
        run_dir = SNAPSHOT_DIR / "runs" / self.us_run_label
        meta = json.loads((run_dir / "scenarios.csv.meta.json").read_text())
        return meta["policyengine_bundles"]["us"]

    @cached_property
    def model_stats(self) -> list[dict]:
        """No-tools model rows, ranked by the exact-match headline metric.

        Exact match is the headline deployability bar. Because the public
        leaderboard is household-impact-weighted, the weighting down-weights the
        zero-reference outputs a hedge-to-zero model gets for free, so the
        weighted exact rate is not compressed near the unweighted zero share and
        discriminates between models about as well as within-1%. The
        ``within1pct`` field remains on every row as the near-miss companion.
        """
        rows = [
            row
            for row in self.dashboard["modelStats"]
            if row.get("condition") == "no_tools"
        ]
        return sorted(rows, key=lambda row: row["exact"], reverse=True)

    @cached_property
    def program_stats(self) -> list[dict]:
        """Per-output rows, ranked easiest-to-hardest by exact match."""
        return sorted(
            self.dashboard["programStats"],
            key=lambda row: row["exact"],
            reverse=True,
        )

    @cached_property
    def _audit_rows(self) -> list[dict]:
        annotation_dir = ROOT / self.manifest["audit_annotation_artifacts"]["path"]
        path = annotation_dir / "us_audit_row_annotations.csv"
        with path.open(newline="") as handle:
            return list(csv.DictReader(handle))

    @cached_property
    def _scenario_prediction_rows(self) -> list[dict]:
        """Flatten the frozen dashboard's model-scenario-output rows."""
        rows = []
        for scenario_id, variable_map in self.dashboard["scenarioPredictions"].items():
            for variable, model_map in variable_map.items():
                for model, result in model_map.items():
                    rows.append(
                        {
                            "model": model,
                            "scenario_id": scenario_id,
                            "variable": variable,
                            **result,
                        }
                    )
        return rows

    @staticmethod
    def _prediction_row_key(row: dict) -> tuple[str, str, str]:
        return row["model"], row["scenario_id"], row["variable"]

    @cached_property
    def reference_exclusions(self) -> list[dict]:
        """Outputs removed from scoring for every model (frozen record)."""
        return load_reference_exclusions(
            SNAPSHOT_DIR / "runs" / self.us_run_label / EXCLUSIONS_FILENAME
        )

    @cached_property
    def _excluded_output_keys(self) -> frozenset[tuple[str, str]]:
        return frozenset(exclusion_keys(self.reference_exclusions))

    def _is_excluded(self, row: dict) -> bool:
        return (row["scenario_id"], row["variable"]) in self._excluded_output_keys

    @cached_property
    def _scored_prediction_rows(self) -> list[dict]:
        """Frozen rows that carry a score (excluded outputs left out)."""
        return [
            row
            for row in self._scenario_prediction_rows
            if row.get("scored", True) and not self._is_excluded(row)
        ]

    @cached_property
    def _audit_row_keys(self) -> frozenset[tuple[str, str, str]]:
        """Annotated rows on scored outputs (the legacy-threshold audit universe)."""
        rows = [row for row in self._audit_rows if not self._is_excluded(row)]
        keys = frozenset(self._prediction_row_key(row) for row in rows)
        if len(keys) != len(rows):
            raise ValueError("Frozen audit annotations contain duplicate row keys")
        return keys

    @cached_property
    def _excluded_output_annotation_rows(self) -> list[dict]:
        """Annotated rows on excluded outputs, kept as description, not scored."""
        return [row for row in self._audit_rows if self._is_excluded(row)]

    @cached_property
    def _legacy_threshold_row_keys(self) -> frozenset[tuple[str, str, str]]:
        return frozenset(
            self._prediction_row_key(row)
            for row in self._scored_prediction_rows
            if row["thresholdScore"] < 100
        )

    @cached_property
    def _exact_match_miss_row_keys(self) -> frozenset[tuple[str, str, str]]:
        return frozenset(
            self._prediction_row_key(row)
            for row in self._scored_prediction_rows
            if row["exact"] < 100
        )

    @cached_property
    def _below_full_bounded_score_row_keys(
        self,
    ) -> frozenset[tuple[str, str, str]]:
        return frozenset(
            self._prediction_row_key(row)
            for row in self._scored_prediction_rows
            if row["boundedScore"] < 100
        )

    @cached_property
    def _stats_by_model(self) -> dict[str, dict]:
        return {row["model"]: row for row in self.model_stats}

    # ----- provenance / scope --------------------------------------------
    @property
    def snapshot_date(self) -> str:
        return self.manifest["snapshot_date"]

    @property
    def model_response_date(self) -> str:
        return self.manifest["model_response_date"]

    @property
    def policyengine_version(self) -> str:
        """policyengine.py version the reference sidecar records for provenance;
        the references themselves come from policyengine_us.Simulation."""
        return self.manifest["reference_output_refresh"]["policyengine_version"]

    @property
    def policyengine_us_version(self) -> str:
        return self.manifest["reference_output_refresh"]["policyengine_us_version"]

    @property
    def reference_rebuilt_date(self) -> str:
        """UTC date the frozen references were last regenerated."""
        refresh = self.manifest["reference_output_refresh"]
        return (refresh.get("regenerated_at_utc") or refresh["generated_at_utc"])[:10]

    # The dataset accessors describe the households' source: the certified
    # build the scenario draw sampled (and the population weights use). The
    # manifest's reference_output_refresh records the reference runtime's
    # default dataset instead, which computing a household's references never
    # reads and which can be a later build.
    @property
    def dataset_id(self) -> str:
        """Populace dataset name, e.g. ``populace_us_2024``."""
        return self.sample_bundle["default_dataset"]

    @property
    def dataset_build_id(self) -> str:
        """Certified populace build id, e.g. ``populace-us-2024-5da5a95-20260611``."""
        return self.sample_bundle["certified_data_build_id"]

    @property
    def dataset_uri(self) -> str:
        return self.sample_bundle["default_dataset_uri"]

    @property
    def dataset_label(self) -> str:
        """Short human label for the data source used in prose ('populace')."""
        return "populace"

    @property
    def n_models(self) -> int:
        return len(self.model_stats)

    @property
    def n_models_fmt(self) -> str:
        return str(self.n_models)

    @property
    def serving_evidence_pinned_counts(self) -> dict[str, int]:
        """Count usable fingerprint evidence separately for each serving field."""
        fingerprint_keys = {
            "answer contract": "answer_contract",
            "request shape": "chunk_size",
            "tool choice": "tool_choice_mode",
            "completion ceiling": "completion_budget_ceiling",
        }
        counts = dict.fromkeys(
            self.serving_config["evidence_field_labels"]["run_state"], 0
        )
        for row in self.serving_config["models"].values():
            evidence = row["evidence"]
            if evidence["kind"] != "run_state":
                continue
            fingerprint = evidence["treatment_fingerprint"]
            for label in counts:
                key = fingerprint_keys[label]
                if key not in evidence["fields"] or key not in fingerprint:
                    continue
                if label == "tool choice" and "legacy_tool_choice_label" in evidence:
                    continue
                counts[label] += 1
        return counts

    @property
    def serving_evidence_caption(self) -> str:
        field_labels = self.serving_config["evidence_field_labels"]
        fields_by_count: dict[int, list[str]] = {}
        for label, count in self.serving_evidence_pinned_counts.items():
            fields_by_count.setdefault(count, []).append(label)
        fingerprint_counts = "; ".join(
            f"{_ordinal_join(labels)} for {_sentence_count(count).lower()} rows"
            for count, labels in fields_by_count.items()
        )
        registry_fields = _ordinal_join(field_labels["registry_for_run_state"])
        registry_count = sum(
            row["evidence"]["kind"] == "registry"
            for row in self.serving_config["models"].values()
        )
        # Newer fingerprints also pin the reasoning setup and timeout, so the
        # registry supplies them only for the rows whose fingerprint omits them.
        registry_keys = {
            "reasoning setup": "reasoning_setup",
            "timeouts": "request_timeout_seconds",
        }
        run_state_rows = [
            row
            for row in self.serving_config["models"].values()
            if row["evidence"]["kind"] == "run_state"
        ]
        fully_pinned = sum(
            all(
                registry_keys[label] not in row["registry_derived"]
                for label in field_labels["registry_for_run_state"]
            )
            for row in run_state_rows
        )
        if not fully_pinned:
            return (
                f"Supervised-run fingerprints pin {fingerprint_counts}. "
                f"{registry_fields.capitalize()} for every row, and all fields for "
                f"the other {registry_count} rows, are the harness registry as "
                "frozen in the snapshot's serving-configuration file."
            )
        other_fingerprinted = len(run_state_rows) - fully_pinned
        return (
            f"Supervised-run fingerprints pin {fingerprint_counts}; "
            f"{registry_fields} for {_sentence_count(fully_pinned).lower()} rows. "
            f"{registry_fields.capitalize()} for the other "
            f"{_sentence_count(other_fingerprinted).lower()} fingerprinted rows, "
            f"and all fields for the other {registry_count} rows, are the harness "
            "registry as frozen in the snapshot's serving-configuration file."
        )

    @cached_property
    def federal_state_joint_accuracy(self) -> pd.DataFrame:
        """Frozen federal/state credit marginals and their household-level joint."""

        def hit_within_10(truth: float, pred: float | None) -> bool:
            if pred is None or pd.isna(pred):
                return False
            if truth == 0:
                return abs(pred) <= 1.0
            return abs(pred - truth) / abs(truth) <= 0.10

        rows = []
        excluded = self._excluded_output_keys
        for scenario_id, variables in self.dashboard["scenarioPredictions"].items():
            # Neither credit output is excluded in this snapshot; the check keeps
            # the table on the scored universe if a future record removes one.
            if (scenario_id, "federal_refundable_credits") in excluded or (
                scenario_id,
                "state_refundable_credits",
            ) in excluded:
                continue
            federal = variables.get("federal_refundable_credits", {})
            state = variables.get("state_refundable_credits", {})
            for model in federal:
                if model not in state:
                    continue
                fed_hit = hit_within_10(
                    federal[model]["groundTruth"], federal[model].get("prediction")
                )
                state_hit = hit_within_10(
                    state[model]["groundTruth"], state[model].get("prediction")
                )
                rows.append(
                    {
                        "model": model,
                        "fed_hit": fed_hit,
                        "state_hit": state_hit,
                        "both_hit": fed_hit and state_hit,
                    }
                )
        summary = (
            pd.DataFrame(rows)
            .groupby("model")[["fed_hit", "state_hit", "both_hit"]]
            .mean()
            .reset_index()
            # Ties on the joint rate are broken by model id so the table, the
            # exception list, and the prose order identically on every platform.
            .sort_values(
                ["both_hit", "model"], ascending=[False, True], kind="mergesort"
            )
        )
        for column in ("fed_hit", "state_hit", "both_hit"):
            summary[column] = (summary[column] * 100).round(1)
        summary["model"] = summary["model"].map(self.model_name)
        summary.columns = [
            "Model",
            "Federal within 10%",
            "State within 10%",
            "Joint within 10%",
        ]
        return summary

    @property
    def joint_credit_accuracy_exceptions(self) -> list[str]:
        """Models whose joint credit hit rate equals at least one marginal."""
        table = self.federal_state_joint_accuracy
        exceptions = (table["Joint within 10%"] == table["Federal within 10%"]) | (
            table["Joint within 10%"] == table["State within 10%"]
        )
        return table.loc[exceptions, "Model"].tolist()

    @property
    def joint_credit_accuracy_note(self) -> str:
        note = (
            "The joint hit rate can be no higher than either marginal and is "
            "strictly lower than both for every model"
        )
        if self.joint_credit_accuracy_exceptions:
            note += " except " + _ordinal_join(self.joint_credit_accuracy_exceptions)
        return note + "."

    @property
    def n_households(self) -> int:
        return self.manifest["scope"]["households"]["us"]

    @property
    def n_households_fmt(self) -> str:
        return f"{self.n_households:,}"

    def _benchmark_people(self) -> list[dict]:
        """Every person in the frozen US scenarios, with their prompt inputs."""
        run_dir = SNAPSHOT_DIR / "runs" / self.us_run_label
        scenarios = pd.read_csv(run_dir / "scenarios.csv")
        people = []
        for text in scenarios["scenario_json"]:
            scenario = json.loads(text)
            people += scenario.get("adults", []) + scenario.get("children", [])
        return people

    @property
    def benchmark_person_count(self) -> int:
        return len(self._benchmark_people())

    @property
    def disabled_person_count(self) -> int:
        """People the prompt lists with the general ``is disabled`` fact."""
        return sum(
            bool(person.get("inputs", {}).get("is_disabled"))
            for person in self._benchmark_people()
        )

    @property
    def program_disability_input_count(self) -> int:
        """People carrying any program-specific disability input (the paper
        says none do)."""
        inputs = (
            "meets_ssi_disability_criteria",
            "months_receiving_social_security_disability",
            "is_permanently_and_totally_disabled",
            "retired_on_total_disability",
            "is_incapable_of_self_care",
            "is_permanently_disabled_veteran",
            "is_surviving_spouse_of_disabled_veteran",
            "is_surviving_child_of_disabled_veteran",
        )
        return sum(
            any(person.get("inputs", {}).get(name) for name in inputs)
            for person in self._benchmark_people()
        )

    @property
    def n_output_groups(self) -> int:
        return self.manifest["scope"]["output_groups"]["us"]

    @property
    def n_output_groups_fmt(self) -> str:
        return str(self.n_output_groups)

    @property
    def n_scored_outputs(self) -> int:
        """Scored output rows per model in the frozen snapshot (e.g. 1,984).

        Person-level eligibility outputs expand per person, so this exceeds
        ``n_households * n_output_groups``.
        """
        return int(self.model_stats[0]["n"])

    @property
    def n_scored_outputs_fmt(self) -> str:
        return f"{self.n_scored_outputs:,}"

    @property
    def n_canonical_rows(self) -> int:
        """Total scored model-output rows across every model (n x models)."""
        return sum(int(row["n"]) for row in self.model_stats)

    @property
    def n_canonical_rows_fmt(self) -> str:
        return f"{self.n_canonical_rows:,}"

    @cached_property
    def parse_contract_failure_counts(self) -> Counter:
        """Missing or unparseable frozen dashboard rows, counted by model."""
        counts: Counter = Counter()
        for row in self._scored_prediction_rows:
            if row.get("failureSource") == "parse_contract_failure":
                counts[row["model"]] += 1
        return counts

    @property
    def parse_contract_failure_count(self) -> int:
        return sum(self.parse_contract_failure_counts.values())

    @property
    def parse_contract_failure_count_fmt(self) -> str:
        return f"{self.parse_contract_failure_count:,}"

    @property
    def parse_contract_failure_pct_fmt(self) -> str:
        pct = 100 * self.parse_contract_failure_count / self.n_canonical_rows
        return f"{pct:.1f}"

    @property
    def parse_contract_failure_breakdown_fmt(self) -> str:
        """Model-level parse failures, descending, with readable names."""
        items = [
            f"{self.model_name(model)} ({count:,})"
            for model, count in self.parse_contract_failure_counts.most_common()
        ]
        return _ordinal_join(items)

    @cached_property
    def explanation_missing_counts(self) -> Counter:
        """Frozen rows with a parsed numeric value but no explanation, by model."""
        counts: Counter = Counter()
        for row in self._scored_prediction_rows:
            if row.get("prediction") is None:
                continue
            if not str(row.get("explanation") or "").strip():
                counts[row["model"]] += 1
        return counts

    @property
    def explanation_missing_count(self) -> int:
        return sum(self.explanation_missing_counts.values())

    @property
    def explanation_missing_count_fmt(self) -> str:
        return f"{self.explanation_missing_count:,}"

    @property
    def explanation_missing_breakdown_fmt(self) -> str:
        items = [
            f"{self.model_name(model)} ({count:,})"
            for model, count in self.explanation_missing_counts.most_common()
        ]
        return _ordinal_join(items)

    @property
    def contract_violation_count_fmt(self) -> str:
        """Rows short of the numeric-plus-explanation contract, either way."""
        return f"{self.parse_contract_failure_count + self.explanation_missing_count:,}"

    @cached_property
    def blank_raw_response_counts(self) -> Counter:
        """Frozen prediction rows whose raw_response is empty, by model.

        Rows served through the Anthropic batch adapter carry no raw payload,
        and some parse failures never captured one; the manuscript states the
        preservation rule with these exceptions rather than as absolute.
        """
        run_dir = SNAPSHOT_DIR / "runs" / self.us_run_label
        frame = pd.read_csv(
            run_dir / "predictions.csv.gz", usecols=["model", "raw_response"]
        )
        blank = frame["raw_response"].isna() | (
            frame["raw_response"].astype(str).str.strip() == ""
        )
        return Counter(frame.loc[blank, "model"].value_counts().to_dict())

    @property
    def blank_raw_response_note(self) -> str:
        """Prose clause naming the rows without a retained raw response."""
        items = [
            f"{self.model_name(model)} ({count:,} rows)"
            for model, count in self.blank_raw_response_counts.most_common()
        ]
        if not items:
            return "every row carries its raw provider response"
        return "no raw payload is retained for " + _ordinal_join(items)

    # ----- populace dataset construction ---------------------------------
    @property
    def populace_people_fmt(self) -> str:
        return f"{POPULACE_PEOPLE:,}"

    @property
    def populace_households_fmt(self) -> str:
        return f"{POPULACE_HOUSEHOLDS:,}"

    @property
    def populace_eligible_households_fmt(self) -> str:
        return f"{POPULACE_ELIGIBLE_HOUSEHOLDS:,}"

    @property
    def populace_eligible_pct_fmt(self) -> str:
        return f"{100 * POPULACE_ELIGIBLE_HOUSEHOLDS / POPULACE_HOUSEHOLDS:.1f}"

    @property
    def populace_excluded_pct_fmt(self) -> str:
        excluded = POPULACE_HOUSEHOLDS - POPULACE_ELIGIBLE_HOUSEHOLDS
        return f"{100 * excluded / POPULACE_HOUSEHOLDS:.1f}"

    # ----- zero inflation ------------------------------------------------
    @cached_property
    def _reference_values(self) -> list[float]:
        """Reference values of the scored outputs (excluded outputs left out,
        as they are from every published score)."""
        from policybench.reference_exclusions import scored_reference_for

        run_dir = SNAPSHOT_DIR / "runs" / self.us_run_label
        scored, _ = scored_reference_for(run_dir / "reference_outputs.csv")
        return [float(value) for value in scored["value"]]

    @property
    def zero_share(self) -> float:
        values = self._reference_values
        return sum(1 for value in values if value == 0) / len(values)

    @property
    def zero_share_pct_fmt(self) -> str:
        return f"{100 * self.zero_share:.0f}"

    # ----- always-zero baseline (household-impact-weighted) --------------
    @cached_property
    def _always_zero_weighted_rates(self) -> dict[str, float]:
        """Weighted exact and within-1% rates of an always-zero predictor.

        Computed from the frozen snapshot through the canonical
        household-impact-weighting path (``weighted_hit_rate_scores_by_model``
        over the headline-filtered reference outputs) -- the same aggregation
        that produces every model's ``exact``/``within1pct`` field in the
        leaderboard. Because the weighting down-weights zero-reference outputs,
        this baseline sits well below the unweighted zero share, which is why
        the weighted exact rate is not compressed and still discriminates
        between models.
        """
        import numpy as np
        import pandas as pd

        from policybench.analysis import weighted_hit_rate_scores_by_model
        from policybench.reference_exclusions import scored_reference_for
        from policybench.spec import get_output_ids, output_group_id

        run_dir = SNAPSHOT_DIR / "runs" / self.us_run_label
        # The scored reference: excluded outputs are out of the baseline as
        # they are out of every model's score.
        ground_truth, _ = scored_reference_for(run_dir / "reference_outputs.csv")
        headline = set(get_output_ids("us", "headline"))
        ground_truth = ground_truth[
            ground_truth["variable"].map(output_group_id).isin(headline)
        ].reset_index(drop=True)
        ground_truth["scenario_id"] = ground_truth["scenario_id"].astype(str)

        scenarios = pd.read_csv(run_dir / "scenarios.csv")
        market = dict(
            zip(
                scenarios["scenario_id"].astype(str),
                pd.to_numeric(scenarios["total_income"], errors="coerce").fillna(0.0),
            )
        )

        predictions = ground_truth[["scenario_id", "variable"]].copy()
        predictions["model"] = "Always zero"
        predictions["prediction"] = np.zeros(len(ground_truth))
        scored = weighted_hit_rate_scores_by_model(
            ground_truth, predictions, market, country="us"
        )
        return {
            "exact": float(scored["weighted_exact"].mean()) * 100,
            "within1pct": float(scored["weighted_within_1pct"].mean()) * 100,
        }

    @property
    def always_zero_exact_fmt(self) -> str:
        """Household-impact-weighted exact rate of the always-zero baseline."""
        return f"{self._always_zero_weighted_rates['exact']:.1f}"

    @property
    def always_zero_within1_fmt(self) -> str:
        """Household-impact-weighted within-1% rate of the always-zero baseline."""
        return f"{self._always_zero_weighted_rates['within1pct']:.1f}"

    @property
    def top_exact_margin_fmt(self) -> str:
        """Points by which the top model's exact rate beats always-zero."""
        margin = (
            self._stats_by_model[self.top_model_id]["exact"]
            - self._always_zero_weighted_rates["exact"]
        )
        return f"{margin:.1f}"

    # ----- model helpers -------------------------------------------------
    def model_name(self, model_id: str) -> str:
        return MODEL_DISPLAY_NAMES.get(model_id, model_id)

    def _score_fmt(self, model_id: str) -> str:
        """Headline exact-match rate for a model, formatted to one decimal."""
        return f"{self._stats_by_model[model_id]['exact']:.1f}"

    def _within1_fmt(self, model_id: str) -> str:
        """Companion within-1% rate for a model, formatted to one decimal."""
        return f"{self._stats_by_model[model_id]['within1pct']:.1f}"

    @property
    def top_model_id(self) -> str:
        return self.model_stats[0]["model"]

    @property
    def top_model(self) -> str:
        return self.model_name(self.top_model_id)

    @property
    def top_score_fmt(self) -> str:
        return self._score_fmt(self.top_model_id)

    @property
    def bottom_model_id(self) -> str:
        return self.model_stats[-1]["model"]

    @property
    def bottom_model(self) -> str:
        return self.model_name(self.bottom_model_id)

    @property
    def bottom_score_fmt(self) -> str:
        return self._score_fmt(self.bottom_model_id)

    @property
    def opus48_score_fmt(self) -> str:
        return self._score_fmt("claude-opus-4.8")

    @property
    def opus47_score_fmt(self) -> str:
        return self._score_fmt("claude-opus-4.7")

    @property
    def opus_gap_fmt(self) -> str:
        """Exact-match points by which Opus 4.7 leads Opus 4.8 (headline)."""
        gap = (
            self._stats_by_model["claude-opus-4.7"]["exact"]
            - self._stats_by_model["claude-opus-4.8"]["exact"]
        )
        return f"{gap:.1f}"

    def model_score_fmt(self, model_id: str) -> str:
        """Headline exact-match rate for any roster model, one decimal."""
        return self._score_fmt(model_id)

    def model_within1_fmt(self, model_id: str) -> str:
        """Companion within-1% rate for any roster model, one decimal."""
        return self._within1_fmt(model_id)

    @property
    def top3_summary(self) -> str:
        """'Model A (x.x), Model B (y.y), and Model C (z.z)' on exact match."""
        parts = [
            f"{self.model_name(row['model'])} ({row['exact']:.1f}% exact; "
            f"{row['within1pct']:.1f}% within-1%)"
            for row in self.model_stats[:3]
        ]
        return _ordinal_join(parts)

    @cached_property
    def exact_leaderboard(self) -> list[tuple[int, str, str, str]]:
        """Ranked (rank, model name, exact %, within-1% %) tuples.

        Ordered by the headline exact-match rate, with the within-1% companion
        column preserved alongside.
        """
        rows = []
        for index, row in enumerate(self.model_stats, start=1):
            rows.append(
                (
                    index,
                    self.model_name(row["model"]),
                    f"{row['exact']:.1f}",
                    f"{row['within1pct']:.1f}",
                )
            )
        return rows

    # ----- hardest outputs -----------------------------------------------
    def _output_name(self, variable: str) -> str:
        return OUTPUT_DISPLAY_NAMES.get(variable, _humanize_variable(variable))

    @cached_property
    def hardest_programs_rows(self) -> list[dict]:
        """Output rows ranked hardest-first by within-1% hit rate."""
        return sorted(
            self.dashboard["programStats"],
            key=lambda row: row["within1pct"],
        )

    def hardest_programs(self, n: int = 5) -> str:
        """'a, b, c, d, and e' -- the n hardest outputs by within-1%."""
        names = [
            self._output_name(row["variable"]) for row in self.hardest_programs_rows[:n]
        ]
        return _ordinal_join(names)

    @cached_property
    def hardest_programs_by_score_rows(self) -> list[dict]:
        """Output rows ranked hardest-first by the bounded continuous score.

        This is the ordering shown in the ``us_hardest`` manuscript table, which
        sorts ``programStats`` by ``score``. The prose that describes the hardest
        outputs "by bounded score" must read from this ranking, not from the
        within-1% ranking in ``hardest_programs_rows``, because the two orderings
        differ (payroll tax, for instance, is bottom-three on within-1% but not
        on bounded score).
        """
        return sorted(self.dashboard["programStats"], key=lambda row: row["score"])

    def hardest_programs_by_score(self, n: int = 5) -> str:
        """'a, b, c, d, and e' -- the n hardest outputs by bounded score."""
        names = [
            self._output_name(row["variable"])
            for row in self.hardest_programs_by_score_rows[:n]
        ]
        return _ordinal_join(names)

    @property
    def hardest_program(self) -> str:
        return self._output_name(self.hardest_programs_rows[0]["variable"])

    @property
    def hardest_program_within1_fmt(self) -> str:
        return f"{self.hardest_programs_rows[0]['within1pct']:.1f}"

    @property
    def hardest_three_programs(self) -> str:
        return self.hardest_programs(3)

    @property
    def hardest_five_by_score(self) -> str:
        """The five hardest outputs by bounded score (matches ``us_hardest``)."""
        return self.hardest_programs_by_score(5)

    # ----- audit ---------------------------------------------------------
    @property
    def audit_annotated_row_count(self) -> int:
        return len(self._audit_row_keys)

    @property
    def audit_annotated_row_count_fmt(self) -> str:
        return f"{self.audit_annotated_row_count:,}"

    # ----- outputs excluded from scoring -----------------------------------
    @property
    def excluded_output_count(self) -> int:
        return len(self.reference_exclusions)

    @property
    def excluded_output_count_fmt(self) -> str:
        return f"{self.excluded_output_count:,}"

    @property
    def excluded_output_phrase(self) -> str:
        words = {
            0: "no",
            1: "one",
            2: "two",
            3: "three",
            4: "four",
            5: "five",
            6: "six",
            7: "seven",
            8: "eight",
            9: "nine",
            10: "ten",
            11: "eleven",
            12: "twelve",
        }
        count = self.excluded_output_count
        return f"{words.get(count, str(count))} output{'s' if count != 1 else ''}"

    @property
    def excluded_outputs_by_input(self) -> dict[str, int]:
        """Unlisted-input exclusions, counted by the input they turn on."""
        counts: dict[str, int] = {}
        for entry in self.reference_exclusions:
            if entry["reason_code"] != UNLISTED_INPUT:
                continue
            counts[entry["unlisted_input"]] = counts.get(entry["unlisted_input"], 0) + 1
        return counts

    @property
    def excluded_outputs_by_root_cause(self) -> dict[str, int]:
        """Engine-defect exclusions, counted by root cause."""
        counts: dict[str, int] = {}
        for entry in self.reference_exclusions:
            if entry["reason_code"] != ENGINE_DEFECT:
                continue
            key = exclusion_basis(entry)
            counts[key] = counts.get(key, 0) + 1
        return counts

    @property
    def unlisted_input_exclusion_count(self) -> int:
        return sum(self.excluded_outputs_by_input.values())

    @property
    def engine_defect_exclusion_count(self) -> int:
        return sum(self.excluded_outputs_by_root_cause.values())

    @property
    def later_law_exclusion_count_word(self) -> str:
        return count_word(self.later_law_exclusion_count)

    @property
    def excluded_output_households_fmt(self) -> str:
        return f"{len({e['scenario_id'] for e in self.reference_exclusions}):,}"

    @property
    def excluded_output_households_phrase(self) -> str:
        words = {
            0: "no",
            1: "one",
            2: "two",
            3: "three",
            4: "four",
            5: "five",
            6: "six",
            7: "seven",
            8: "eight",
            9: "nine",
            10: "ten",
            11: "eleven",
            12: "twelve",
        }
        count = len({e["scenario_id"] for e in self.reference_exclusions})
        return f"{words.get(count, str(count))} household{'s' if count != 1 else ''}"

    @property
    def scored_outputs_per_model(self) -> int:
        return len(self._reference_values)

    @property
    def scored_outputs_per_model_fmt(self) -> str:
        return f"{self.scored_outputs_per_model:,}"

    @property
    def total_outputs_per_model_fmt(self) -> str:
        return f"{len(self._reference_values) + self.excluded_output_count:,}"

    @property
    def excluded_output_annotation_row_count(self) -> int:
        return len(self._excluded_output_annotation_rows)

    @property
    def excluded_output_annotation_row_count_fmt(self) -> str:
        return f"{self.excluded_output_annotation_row_count:,}"

    @property
    def prompt_ambiguity_row_count(self) -> int:
        return sum(
            1
            for row in self._excluded_output_annotation_rows
            if row["failure_source"] == "prompt_ambiguity"
        )

    @property
    def prompt_ambiguity_row_count_fmt(self) -> str:
        return f"{self.prompt_ambiguity_row_count:,}"

    @cached_property
    def audit_judge_provenance(self) -> dict:
        """Manifest tally of which judge model produced each audit verdict."""
        return self.manifest["audit_annotation_artifacts"]["judge_provenance"]

    @property
    def audit_case_count_fmt(self) -> str:
        return f"{self.audit_judge_provenance['cases_judged']:,}"

    @property
    def audit_opus_judged_case_count_fmt(self) -> str:
        entry = self.audit_judge_provenance["by_judge"]["claude-opus-5"]
        return f"{entry['cases']:,}"

    @property
    def audit_opus55_judged_case_count_fmt(self) -> str:
        entry = self.audit_judge_provenance["by_judge"]["claude-opus-5-5"]
        return f"{entry['cases']:,}"

    @property
    def audit_sol_judged_case_count_fmt(self) -> str:
        entry = self.audit_judge_provenance["by_judge"]["gpt-5.6-sol"]
        return f"{entry['cases']:,}"

    @cached_property
    def audit_developer_adjudications(self) -> dict:
        """Manifest summary of recorded developer adjudications."""
        return self.manifest["audit_annotation_artifacts"]["developer_adjudications"]

    @property
    def audit_flagged_by_verdict(self) -> dict[str, int]:
        """Judge-flagged cases by the developer's reference verdict."""
        return self.audit_developer_adjudications.get(
            "judge_flagged_by_reference_verdict", {}
        )

    @property
    def audit_flagged_case_count(self) -> int:
        return sum(self.audit_flagged_by_verdict.values())

    def audit_flagged_count(self, verdict: str) -> int:
        return self.audit_flagged_by_verdict.get(verdict, 0)

    @property
    def engine_defect_unflagged_count(self) -> int:
        """Engine-defect exclusions no judge flagged: the fix sweeps found them."""
        return self.engine_defect_exclusion_count - self.audit_flagged_count(
            "engine_defect"
        )

    @property
    def snap_engine_defect_exclusion_count(self) -> int:
        """SNAP outputs excluded for an engine defect (the SNAP rounding defects)."""
        return sum(
            1
            for e in self.reference_exclusions
            if e["reason_code"] == ENGINE_DEFECT and e["variable"] == "snap"
        )

    @cached_property
    def fable51_auto_uplift_fmt(self) -> str:
        """Claude Fable 5.1's tool_choice auto sensitivity minus its board row."""
        summary = json.loads(
            (
                ROOT / "sensitivity" / "data" / "claude-fable-5-1-thinking.json"
            ).read_text()
        )
        return f"{summary['delta_exact']:.1f}"

    @property
    def excluded_output_households_by_reason(self) -> dict[str, int]:
        households: dict[str, set[str]] = {}
        for entry in self.reference_exclusions:
            households.setdefault(entry["reason_code"], set()).add(entry["scenario_id"])
        return {reason: len(ids) for reason, ids in households.items()}

    @cached_property
    def reference_revisions(self) -> list[dict]:
        """Revisions recorded in the frozen reference sidecar (oldest first)."""
        run_dir = SNAPSHOT_DIR / "runs" / self.us_run_label
        meta = json.loads((run_dir / "reference_outputs.csv.meta.json").read_text())
        return meta.get("revisions", [])

    @property
    def regenerated_reference_keys(self) -> set[tuple[str, str]]:
        """Scored outputs a convention or an upstream fix regenerated.

        These are the September 22 regenerations, made on the engine version
        before the first upgrade; each engine upgrade's own changes are counted
        by ``engine_upgrades`` (the last one's by the ``engine_upgrade_*``
        properties).
        """
        return {
            (change["scenario_id"], change.get("variable", "snap"))
            for revision in self.reference_revisions
            if revision.get("kind", "convention") in {"convention", "upstream_fix"}
            for change in revision["changed"]
        }

    @cached_property
    def frozen_references(self) -> dict[tuple[str, str], float]:
        """The frozen reference for every output, scored or excluded."""
        run_dir = SNAPSHOT_DIR / "runs" / self.us_run_label
        frozen = pd.read_csv(run_dir / "reference_outputs.csv")
        return {
            (row.scenario_id, row.variable): float(row.value)
            for row in frozen.itertuples(index=False)
        }

    def references_as_of(self, date: str) -> dict[tuple[str, str], float]:
        """The references as they stood at the end of ``date`` (UTC day)."""
        return references_as_of(self.frozen_references, self.reference_revisions, date)

    def _exclusions_in_place(self, date: str, *, include_day: bool) -> list[dict]:
        """Exclusion records in place just before ``date`` or, with
        ``include_day``, at its end, whatever later releases added or removed."""
        return exclusions_in_place(
            self.reference_exclusions,
            self.reference_revisions,
            date,
            include_day=include_day,
        )

    @cached_property
    def engine_upgrades(self) -> list[EngineUpgrade]:
        """Every engine upgrade the sidecar records, oldest first."""
        return engine_upgrades_from(self.reference_revisions, self.reference_exclusions)

    @property
    def engine_upgrade_count(self) -> int:
        return len(self.engine_upgrades)

    @property
    def last_engine_upgrade(self) -> EngineUpgrade | None:
        """The upgrade behind the current references."""
        return self.engine_upgrades[-1] if self.engine_upgrades else None

    def engine_upgrade_on(self, date: str) -> EngineUpgrade:
        """The engine upgrade dated ``date`` (UTC day)."""
        matches = [u for u in self.engine_upgrades if u.date == date]
        if len(matches) != 1:
            raise ValueError(
                f"no engine_upgrade revision dated {date}, or more than one: "
                f"{[u.date for u in self.engine_upgrades]}"
            )
        return matches[0]

    def engine_upgrade_to(self, version: str) -> EngineUpgrade:
        """The engine upgrade that moved the references to ``version``."""
        version = engine_version_number(version)
        matches = [u for u in self.engine_upgrades if u.engine_version == version]
        if len(matches) != 1:
            raise ValueError(
                f"no engine_upgrade revision to {version}, or more than one: "
                f"{[u.engine_version for u in self.engine_upgrades]}"
            )
        return matches[0]

    @property
    def september_upgrade(self) -> EngineUpgrade:
        """The 2026-09-29 move from policyengine-us 1.755.4 to 2.15.17, which
        reference_audit/2026-09-28 records, however many upgrades follow."""
        return self.engine_upgrade_on(SEPTEMBER_UPGRADE_DATE)

    @property
    def engine_upgrade_revision(self) -> dict | None:
        """The sidecar revision that moved the references to the current
        engine: the last engine upgrade."""
        last = self.last_engine_upgrade
        return None if last is None else last.revision

    @property
    def previous_policyengine_us_version(self) -> str:
        """policyengine-us version behind the references before the last
        upgrade: that revision's own previous_engine_version."""
        last = self.last_engine_upgrade
        return (
            self.policyengine_us_version
            if last is None
            else (last.previous_engine_version)
        )

    @property
    def engine_upgrade_date(self) -> str:
        """UTC date PolicyBench rebuilt the references on the current engine:
        the sidecar's ``regenerated_at_utc`` day, which is also the last
        upgrade's own ``date`` (tests/test_paper_results.py checks they agree)."""
        if self.last_engine_upgrade is None:
            return ""
        return self.reference_rebuilt_date

    @property
    def engine_upgrade_partition(self) -> dict[str, list[dict]]:
        """The last upgrade's changed outputs, split into scored changes beyond
        the exact-match tolerance, scored changes within it, new exclusions and
        restorations."""
        last = self.last_engine_upgrade
        if last is None:
            return partition_engine_upgrade_changes([], frozenset())
        return last.partition

    @property
    def engine_upgrade_scored_change_count(self) -> int:
        """Scored references the last upgrade moved beyond the exact-match
        tolerance."""
        return len(self.engine_upgrade_partition["scored_changes"])

    @property
    def engine_upgrade_within_tolerance_count(self) -> int:
        """Scored references the last upgrade moved within the $1 tolerance."""
        return len(self.engine_upgrade_partition["within_tolerance"])

    @property
    def engine_upgrade_new_exclusion_count(self) -> int:
        """Outputs scored before the last upgrade that it removed from scoring."""
        return len(self.engine_upgrade_partition["new_exclusions"])

    @property
    def engine_upgrade_restored_count(self) -> int:
        """Excluded outputs the last upgrade returned to scoring."""
        last = self.last_engine_upgrade
        return 0 if last is None else last.restored_count

    @property
    def engine_upgrade_restored_count_word(self) -> str:
        return count_word(self.engine_upgrade_restored_count)

    @cached_property
    def engine_upgrade_timing(self) -> dict | None:
        """The last upgrade's sweep timing record, when that upgrade is the
        2026-10-09 audit's build and the record is written (None before)."""
        last = self.last_engine_upgrade
        if last is None or not str(last.revision.get("builder", "")).startswith(
            OCTOBER_UPGRADE_AUDIT
        ):
            return None
        if not OCTOBER_SWEEP_TIMING.is_file():
            return None
        timing = json.loads(OCTOBER_SWEEP_TIMING.read_text())
        if timing["reference_sweep"]["engine"] != last.engine_version:
            raise ValueError(
                f"{OCTOBER_SWEEP_TIMING} times policyengine-us "
                f"{timing['reference_sweep']['engine']}, not {last.engine_version}"
            )
        return timing

    @property
    def engine_upgrade_timing_sentence(self) -> str:
        """When the last upgrade's sweep began and what the publication check
        found, from its timing record; empty until the record is written."""
        timing = self.engine_upgrade_timing
        if timing is None:
            return ""
        engine = timing["reference_sweep"]["engine"]
        began = timing["reference_sweep"]["first_output_at_utc"][:10]
        uploaded = timing["pypi"]["wheel_uploaded_at_utc"][engine][11:16]
        read_at = timing["pypi"]["read_at_utc"]
        check = timing.get("publication_check")
        if check is None or check["engine"] != timing["pypi"]["newest_at_read"]:
            raise ValueError(f"{OCTOBER_SWEEP_TIMING} records no publication check")
        when = f"PolicyBench checked PyPI on {read_at[:10]} at {read_at[11:16]} UTC"
        if check["engine"] == engine:
            checked = f"It was still the newest release when {when}."
        elif check["same"] == check["outputs"]:
            checked = (
                f"policyengine-us {check['engine']}, the newest release when {when}, "
                f"gives the same value as {engine} for all {check['outputs']:,} "
                "outputs under the same conventions and adapter."
            )
        else:
            raise ValueError(
                f"policyengine-us {check['engine']} moves {check['differ']}; state "
                "what the publication check found before publishing"
            )
        return (
            f"policyengine-us {engine} was the newest release when PolicyBench began "
            f"sweeping the references on {began} (uploaded {uploaded} UTC). {checked}"
        )

    @property
    def engine_upgrade_restored_fixes(self) -> list[tuple[str, int, list[str]]]:
        """The defects behind the outputs the last upgrade returned to scoring:
        each one's name, how many outputs it restores and the upstream pull
        requests its regenerated_exclusions entries name (not the related
        ones), in the sidecar's order. A record with several root causes names
        each."""
        last = self.last_engine_upgrade
        fixes: dict[str, tuple[int, list[str]]] = {}
        for entry in [] if last is None else last.revision["regenerated_exclusions"]:
            causes = entry["record"]["root_cause"].split("+")
            unnamed = [c for c in causes if c not in ROOT_CAUSE_LABELS]
            if unnamed:
                raise ValueError(f"no paper name for the root causes {unnamed}")
            label = " and ".join(ROOT_CAUSE_LABELS[c] for c in causes)
            prs = UPSTREAM_PR.findall(entry["upstream"].split("; related")[0])
            if not prs:
                raise ValueError(f"{_key(entry)} names no upstream pull request")
            count, known = fixes.get(label, (0, []))
            fixes[label] = (count + 1, known + [p for p in prs if p not in known])
        return [(label, count, prs) for label, (count, prs) in fixes.items()]

    @property
    def engine_upgrade_restored_sentence(self) -> str:
        """One sentence naming the fixes behind the restored outputs."""
        parts = []
        for label, count, prs in self.engine_upgrade_restored_fixes:
            numbers = ", ".join(f"#{pr}" for pr in prs)
            outputs = "" if count == 1 else f"; {count_word(count)} outputs"
            parts.append(f"{label} (policyengine-us {numbers}{outputs})")
        if not parts:
            return ""
        return f"The restored outputs take the upstream fixes for {_series(parts)}."

    @property
    def engine_upgrade_scored_change_sentence(self) -> str:
        """One sentence naming what the last upgrade changed in the scored
        references beyond the tolerance."""
        last = self.last_engine_upgrade
        changes = [] if last is None else last.partition["scored_changes"]
        parts = []
        for change in changes:
            cause = change["cause"]
            if cause not in CHANGE_CAUSE_LABELS:
                raise ValueError(f"no paper name for the change cause {cause!r}")
            prs = UPSTREAM_PR.findall(change["basis"])
            numbers = f" (policyengine-us #{prs[-1]})" if prs else ""
            part = f"{CHANGE_CAUSE_LABELS[cause]}{numbers}"
            if part not in parts:
                parts.append(part)
        if not parts:
            return ""
        noun = "reference follows" if len(changes) == 1 else "references follow"
        return f"The changed scored {noun} {_series(parts)}."

    @property
    def engine_upgrade_new_exclusion_sentence(self) -> str:
        """One sentence naming the inputs behind the outputs the last upgrade
        removed from scoring."""
        last = self.last_engine_upgrade
        if last is None or not last.partition["new_exclusions"]:
            return ""
        added = {_key(change) for change in last.partition["new_exclusions"]}
        inputs = []
        for record in self.reference_exclusions:
            if _key(record) in added:
                text = record.get("unlisted_input")
                if not text:
                    raise ValueError(f"{_key(record)} names no unlisted input")
                if text not in inputs:
                    inputs.append(text)
        count = len(added)
        noun = "output that leaves" if count == 1 else "outputs that leave"
        verb = "depends" if count == 1 else "depend"
        return (
            f"The {count_word(count)} {noun} scoring {verb} on an input no prompt "
            f"states: {_series(inputs)}."
        )

    @property
    def engine_upgrade_scored_change_count_word(self) -> str:
        return count_word(self.engine_upgrade_scored_change_count)

    @property
    def engine_upgrade_new_exclusion_count_word(self) -> str:
        return count_word(self.engine_upgrade_new_exclusion_count)

    @property
    def excluded_outputs_by_engine_version(self) -> dict[str, int]:
        """Excluded outputs by the policyengine-us version behind the value
        each keeps (the version its exclusion was decided on), oldest first."""
        counts = Counter(
            engine_version_number(entry["engine_version"])
            for entry in self.reference_exclusions
        )
        return {
            version: counts[version]
            for version in sorted(counts, key=engine_version_key)
        }

    @property
    def excluded_outputs_by_engine_version_phrase(self) -> str:
        """'52 computed with policyengine-us 1.755.4, 12 with 2.15.17', for
        however many engines the excluded outputs' values come from."""
        return engine_version_count_phrase(self.excluded_outputs_by_engine_version)

    @property
    def excluded_outputs_on_previous_engine_count(self) -> int:
        return self.excluded_outputs_by_engine_version.get(
            self.previous_policyengine_us_version, 0
        )

    @property
    def excluded_outputs_on_reference_engine_count(self) -> int:
        return self.excluded_outputs_by_engine_version.get(
            self.policyengine_us_version, 0
        )

    @cached_property
    def publication_check_policyengine_us_version(self) -> str:
        """policyengine-us release of the sweep that rechecked every reference
        before publication (reference_audit/2026-09-28/verification)."""
        with PUBLICATION_CHECK_SWEEP.open(newline="") as source:
            engines = {row["engine"] for row in csv.DictReader(source)}
        if len(engines) != 1:
            raise ValueError(f"{PUBLICATION_CHECK_SWEEP} mixes engines: {engines}")
        return engines.pop()

    @cached_property
    def sweep_timing(self) -> dict:
        """reference_audit/2026-09-28/verification/sweep_timing.json."""
        return json.loads(SWEEP_TIMING.read_text())

    @property
    def reference_engine_uploaded_utc(self) -> str:
        """PyPI upload time (UTC, HH:MM) of the wheel the 2026-09-29 reference
        sweep began on (sweep_timing.json's reference_sweep engine, 2.15.17),
        however many upgrades follow it."""
        engine = self.sweep_timing["reference_sweep"]["engine"]
        self.engine_upgrade_to(engine)  # refuses a timing record of no upgrade
        return self.sweep_timing["pypi"]["wheel_uploaded_at_utc"][engine][11:16]

    @property
    def publication_check_pypi_read_date(self) -> str:
        """UTC day PolicyBench read PyPI for the publication check."""
        pypi = self.sweep_timing["pypi"]
        if pypi["newest_at_read"] != self.publication_check_policyengine_us_version:
            raise ValueError(
                f"{SWEEP_TIMING} names {pypi['newest_at_read']} as newest, but the "
                f"check ran {self.publication_check_policyengine_us_version}"
            )
        return pypi["read_at_utc"][:10]

    @property
    def publication_check_pypi_read_utc(self) -> str:
        """Time (UTC, HH:MM) PolicyBench read PyPI for the publication check."""
        return self.sweep_timing["pypi"]["read_at_utc"][11:16]

    @cached_property
    def rerun_sweeps(self) -> dict:
        """reference_audit/2026-09-28/verification/rerun_sweeps.json."""
        return json.loads(RERUN_SWEEPS.read_text())

    @cached_property
    def _rerun_sweep_upgrade(self) -> EngineUpgrade:
        """The upgrade to the engine the re-run sweeps ran on (2.15.17)."""
        return self.engine_upgrade_to(self.rerun_sweeps["engine"])

    @cached_property
    def _excluded_while_rerun_engine_was_reference(self) -> frozenset:
        """Outputs excluded while the re-run sweeps' engine was the reference
        engine, at the latest: the current record, or, once a later upgrade
        moved the references on, the record just before that upgrade."""
        upgrades = self.engine_upgrades
        index = upgrades.index(self._rerun_sweep_upgrade)
        if index + 1 == len(upgrades):
            return self._excluded_output_keys
        return upgrades[index + 1].excluded_before

    @cached_property
    def rerun_sweep_partition(self) -> dict[str, list[tuple[str, str, str]]]:
        return partition_rerun_sweep_moves(
            self.rerun_sweeps, self._excluded_while_rerun_engine_was_reference
        )

    @property
    def rerun_sweep_september_22_count(self) -> int:
        """Sweeps of the September 22 audit re-run on the reference engine."""
        return sum(
            1
            for sweep in self.rerun_sweeps["sweeps"]
            if sweep["september_22_root_cause"] is not None
        )

    @property
    def rerun_sweep_september_22_count_word(self) -> str:
        return NUMBER_WORDS[self.rerun_sweep_september_22_count]

    @property
    def rerun_sweep_new_count(self) -> int:
        """Sweeps first run on the reference engine."""
        return sum(
            1
            for sweep in self.rerun_sweeps["sweeps"]
            if sweep["september_22_root_cause"] is None
        )

    @property
    def rerun_sweep_scored_beyond_tolerance_count(self) -> int:
        return len(self.rerun_sweep_partition["scored_beyond_tolerance"])

    @property
    def rerun_sweep_scored_within_tolerance_count(self) -> int:
        return len(self.rerun_sweep_partition["scored_within_tolerance"])

    @property
    def rerun_sweep_scored_within_tolerance_count_word(self) -> str:
        return NUMBER_WORDS[self.rerun_sweep_scored_within_tolerance_count]

    @cached_property
    def rerun_sweep_new_excluded_outputs(self) -> list[tuple[str, str]]:
        """Outputs that a sweep first run on the reference engine moves
        beyond the exact-match tolerance, against its own baseline, and that
        the exclusion record did not hold before that engine's upgrade."""
        held_before = self._rerun_sweep_upgrade.excluded_before
        return sorted(
            {
                (move["scenario_id"], move["variable"])
                for sweep in self.rerun_sweeps["sweeps"]
                if sweep["september_22_root_cause"] is None
                for move in sweep["moves"]
                if (move["scenario_id"], move["variable"]) not in held_before
                and moves_beyond_tolerance(
                    move["variable"], move["baseline"], move["recomputed"]
                )
            }
        )

    @property
    def rerun_sweep_new_excluded_count_word(self) -> str:
        return NUMBER_WORDS[len(self.rerun_sweep_new_excluded_outputs)]

    # ----- the 2026-10-05 review of release dashboard-data-20260930 ----------
    @property
    def review_date(self) -> str:
        return REVIEW_DATE

    @cached_property
    def _excluded_at_review(self) -> list[dict]:
        """Exclusion records in place once the review decided, whatever
        records later releases added or removed."""
        return self._exclusions_in_place(REVIEW_DATE, include_day=True)

    @cached_property
    def review_exclusions(self) -> list[dict]:
        """Exclusion records the 2026-10-05 review added."""
        return [
            entry
            for entry in self._excluded_at_review
            if entry.get("decided_on") == REVIEW_DATE
        ]

    @property
    def review_exclusion_keys(self) -> frozenset[tuple[str, str]]:
        return frozenset(exclusion_keys(self.review_exclusions))

    @property
    def excluded_before_review_keys(self) -> frozenset[tuple[str, str]]:
        """Outputs excluded before the review: every record in place once it
        decided that it did not add."""
        return frozenset(exclusion_keys(self._excluded_at_review)) - (
            self.review_exclusion_keys
        )

    @property
    def review_new_exclusion_count(self) -> int:
        return len(self.review_exclusions)

    @property
    def review_new_exclusion_count_word(self) -> str:
        return NUMBER_WORDS[self.review_new_exclusion_count]

    @cached_property
    def ruled_records(self) -> list[dict]:
        """The records the 2026-10-06 rulings decided, in (scenario, variable)
        order: those in the exclusion record, and those a later engine upgrade
        regenerated, whose removed record its regenerated_exclusions keep."""
        current = [
            record
            for record in self.reference_exclusions
            if record.get("decided_on") == RULING_DATE
        ]
        removed = [
            entry["record"]
            for upgrade in self.engine_upgrades
            for entry in upgrade.revision.get("regenerated_exclusions", [])
            if entry.get("record", {}).get("decided_on") == RULING_DATE
        ]
        records = sorted(current + removed, key=_key)
        unnamed = [_key(record) for record in records if not record.get("decision")]
        if unnamed:
            raise ValueError(f"2026-10-06 records name no ruling: {unnamed}")
        return records

    @property
    def ruling_date(self) -> str:
        return RULING_DATE

    @property
    def ruled_exclusion_count(self) -> int:
        return len(self.ruled_records)

    @property
    def ruled_exclusion_count_word(self) -> str:
        return count_word(self.ruled_exclusion_count)

    def ruled_decision_count(self, decision: str) -> int:
        """Records one ruling (d1022 or d994) decided."""
        return sum(record["decision"] == decision for record in self.ruled_records)

    def ruled_decision_count_word(self, decision: str) -> str:
        return count_word(self.ruled_decision_count(decision))

    @property
    def ruled_regenerated_count(self) -> int:
        """Ruled records a later engine upgrade regenerated."""
        current = {_key(record) for record in self.reference_exclusions}
        return sum(_key(record) not in current for record in self.ruled_records)

    @property
    def ruled_regenerated_count_word(self) -> str:
        return count_word(self.ruled_regenerated_count)

    @property
    def ruled_kept_count(self) -> int:
        return self.ruled_exclusion_count - self.ruled_regenerated_count

    @property
    def ruled_kept_count_word(self) -> str:
        return count_word(self.ruled_kept_count)

    @property
    def ruled_exclusion_engine_version(self) -> str:
        """policyengine-us version the ruled records were computed on."""
        versions = {record["engine_version"] for record in self.ruled_records}
        if len(versions) != 1:
            raise ValueError(f"the 2026-10-06 records name several engines: {versions}")
        return engine_version_number(versions.pop())

    @property
    def review_exclusion_engine_version(self) -> str:
        """policyengine-us version the review's records were computed on."""
        versions = {entry["engine_version"] for entry in self.review_exclusions}
        if len(versions) != 1:
            raise ValueError(f"review records mix engine versions: {versions}")
        return versions.pop().removeprefix("policyengine-us ")

    @property
    def review_sweep_count(self) -> int:
        return len(REVIEW_SWEEPS)

    @property
    def review_sweep_count_word(self) -> str:
        return NUMBER_WORDS[self.review_sweep_count]

    @cached_property
    def review_sweep_rows(self) -> dict[str, pd.DataFrame]:
        """Each review sweep's CSV: every output, its frozen reference, the
        sweep's baseline and its value under each reading."""
        return {name: pd.read_csv(path) for name, (path, _, _) in REVIEW_SWEEPS.items()}

    def _review_sweep_moves(
        self, sweep: str | None = None
    ) -> list[tuple[str, str, str, float, float]]:
        """(sweep, scenario_id, variable, baseline, recomputed) for every
        reading or check that changes an output's value from the baseline."""
        moves = []
        for name, (_, baseline_column, readings) in REVIEW_SWEEPS.items():
            if sweep is not None and name != sweep:
                continue
            frame = self.review_sweep_rows[name]
            for row in frame.itertuples(index=False):
                baseline = float(getattr(row, baseline_column))
                for reading in readings:
                    recomputed = float(getattr(row, reading))
                    if recomputed != baseline:
                        moves.append(
                            (name, row.scenario_id, row.variable, baseline, recomputed)
                        )
        return moves

    @cached_property
    def review_sweep_partition(self) -> dict[str, list[tuple[str, str, str]]]:
        return partition_review_sweep_moves(
            self._review_sweep_moves(),
            self.excluded_before_review_keys,
            frozenset(exclusion_keys(self._excluded_at_review)),
        )

    def review_sweep_moved_outputs(self, sweep: str) -> list[tuple[str, str]]:
        """Outputs a review sweep moves beyond the exact-match tolerance under
        any of its readings, against its own baseline."""
        return sorted(
            {
                (scenario_id, variable)
                for _, scenario_id, variable, baseline, recomputed in (
                    self._review_sweep_moves(sweep)
                )
                if moves_beyond_tolerance(variable, baseline, recomputed)
            }
        )

    def review_sweep_moved_count(self, sweep: str) -> int:
        return len(self.review_sweep_moved_outputs(sweep))

    def review_sweep_moved_count_word(self, sweep: str) -> str:
        return NUMBER_WORDS[self.review_sweep_moved_count(sweep)]

    def review_sweep_moved_household_count_word(self, sweep: str) -> str:
        """Households whose outputs a review sweep moves beyond tolerance."""
        households = {s for s, _ in self.review_sweep_moved_outputs(sweep)}
        return NUMBER_WORDS[len(households)]

    def review_sweep_newly_excluded_count(self, sweep: str) -> int:
        """Outputs the sweep moves that were scored before the review."""
        return sum(
            output not in self.excluded_before_review_keys
            for output in self.review_sweep_moved_outputs(sweep)
        )

    def review_sweep_newly_excluded_count_word(self, sweep: str) -> str:
        return NUMBER_WORDS[self.review_sweep_newly_excluded_count(sweep)]

    def review_sweep_already_excluded_count_word(self, sweep: str) -> str:
        """Outputs the sweep moves that were already excluded."""
        return NUMBER_WORDS[
            self.review_sweep_moved_count(sweep)
            - self.review_sweep_newly_excluded_count(sweep)
        ]

    @property
    def review_newly_excluded_moved_outputs(self) -> list[tuple[str, str]]:
        return sorted(
            {(s, v) for _, s, v in self.review_sweep_partition["newly_excluded"]}
        )

    @property
    def review_already_excluded_moved_outputs(self) -> list[tuple[str, str]]:
        """Outputs excluded before the review that its sweeps also move."""
        return sorted(
            {(s, v) for _, s, v in self.review_sweep_partition["excluded_before"]}
        )

    @property
    def review_already_excluded_moved_count_word(self) -> str:
        return NUMBER_WORDS[len(self.review_already_excluded_moved_outputs)]

    @property
    def review_still_scored_moves_phrase(self) -> str:
        """'no output that is still scored', or how many still-scored outputs
        the review's sweeps move by any amount."""
        moved = {
            (s, v)
            for group in ("scored_beyond_tolerance", "scored_within_tolerance")
            for _, s, v in self.review_sweep_partition[group]
        }
        count = len(moved)
        if count in (0, 1):
            return f"{NUMBER_WORDS[count]} output that is still scored"
        return f"{NUMBER_WORDS.get(count, str(count))} outputs that are still scored"

    @property
    def review_scored_before_count(self) -> int:
        """References scored before the review, which every review sweep's
        baseline reproduces (refuses a sweep whose baseline misses one, or
        whose reference column is not the frozen reference as it stood at the
        review)."""
        reference = self.references_as_of(REVIEW_DATE)
        scored_before = set(reference) - self.excluded_before_review_keys
        for name, (_, baseline_column, _) in REVIEW_SWEEPS.items():
            frame = self.review_sweep_rows[name]
            rows = {
                (row.scenario_id, row.variable): (
                    float(row.reference),
                    float(getattr(row, baseline_column)),
                )
                for row in frame.itertuples(index=False)
            }
            if set(rows) != set(reference):
                raise ValueError(f"review sweep {name} does not cover every output")
            for key in scored_before:
                swept_reference, baseline = rows[key]
                if swept_reference != reference[key] or baseline != reference[key]:
                    raise ValueError(
                        f"review sweep {name}'s baseline does not reproduce {key}"
                    )
        return len(scored_before)

    @property
    def review_scored_before_count_fmt(self) -> str:
        return f"{self.review_scored_before_count:,}"

    @cached_property
    def review_adjudications(self) -> list[dict]:
        """The developer adjudications the review recorded."""
        annotation_dir = ROOT / self.manifest["audit_annotation_artifacts"]["path"]
        record = json.loads((annotation_dir / "us_adjudications.json").read_text())
        return [
            entry
            for entry in record["adjudications"]
            if entry.get("adjudicated_on") == REVIEW_DATE
        ]

    @property
    def review_judge_flagged_count(self) -> int:
        """Review outputs a judge had flagged reference-suspect (the paper
        says none had)."""
        return sum(
            bool(entry.get("judge_reference_suspect"))
            for entry in self.review_adjudications
        )

    @property
    def engine_upgrade_rechecked_count(self) -> int:
        """Excluded outputs whose value moved on the last upgrade's engine and
        were re-reviewed; they stay excluded."""
        last = self.last_engine_upgrade
        return 0 if last is None else last.rechecked_count

    def _regenerated_keys_of_kind(self, kind: str) -> set[tuple[str, str]]:
        return {
            (change["scenario_id"], change.get("variable", "snap"))
            for revision in self.reference_revisions
            if revision.get("kind", "convention") == kind
            for change in revision["changed"]
        }

    @property
    def regenerated_reference_count(self) -> int:
        return len(self.regenerated_reference_keys)

    @property
    def regenerated_snap_reference_count(self) -> int:
        return sum(1 for _, v in self.regenerated_reference_keys if v == "snap")

    @property
    def regenerated_reference_household_count(self) -> int:
        return len({scenario_id for scenario_id, _ in self.regenerated_reference_keys})

    @property
    def regenerated_non_snap_reference_count(self) -> int:
        return sum(
            1 for _, variable in self.regenerated_reference_keys if variable != "snap"
        )

    @property
    def regenerated_by_upstream_fix_count(self) -> int:
        """References regenerated with a fix merged upstream after the freeze."""
        return len(self._regenerated_keys_of_kind("upstream_fix"))

    @property
    def regenerated_by_convention_count(self) -> int:
        return len(self._regenerated_keys_of_kind("convention"))

    @property
    def upstream_fixed_root_causes(self) -> list[str]:
        return sorted(
            r["root_cause"]
            for r in self.reference_revisions
            if r.get("kind") == "upstream_fix"
        )

    @property
    def upstream_fixed_root_cause_count(self) -> int:
        return len(self.upstream_fixed_root_causes)

    @property
    def upstream_fix_prs_fmt(self) -> str:
        """The policyengine-us pull requests behind the upstream fixes, in order."""
        prs = sorted(
            {
                int(match)
                for r in self.reference_revisions
                if r.get("kind") == "upstream_fix"
                for match in re.findall(r"policyengine-us#(\d+)", r["upstream"])
            }
        )
        labels = [f"#{n}" for n in prs]
        return (
            ", ".join(labels[:-1]) + f" and {labels[-1]}"
            if len(labels) > 1
            else "".join(labels)
        )

    @property
    def regenerated_references_by_source(self) -> dict[str, int]:
        """Regenerated references per convention or upstream fix (may be none)."""
        return {
            revision.get("convention") or revision.get("root_cause"): len(
                revision["changed"]
            )
            for revision in self.reference_revisions
        }

    @property
    def publication_convention_count(self) -> int:
        """Conventions in the reference sidecar, including any that moved no output."""
        return sum(
            1
            for r in self.reference_revisions
            if r.get("kind", "convention") == "convention"
        )

    @property
    def later_law_exclusion_count(self) -> int:
        return sum(
            1 for e in self.reference_exclusions if e["reason_code"] == LATER_LAW
        )

    @property
    def engine_defect_root_cause_count(self) -> int:
        """Distinct root causes behind the engine-defect exclusions."""
        causes: set[str] = set()
        for entry in self.reference_exclusions:
            if entry["reason_code"] == ENGINE_DEFECT:
                causes.update(exclusion_basis(entry).split("+"))
        return len(causes)

    @property
    def excluded_descriptive_row_count(self) -> int:
        """Annotated rows on excluded outputs that carry a descriptive class."""
        return sum(
            1
            for row in self._excluded_output_annotation_rows
            if row["failure_source"]
            in {"prompt_ambiguity", "reference_engine_defect", "reference_later_law"}
        )

    @property
    def audit_adjudicated_case_count_fmt(self) -> str:
        return f"{self.audit_developer_adjudications['cases']:,}"

    @property
    def audit_adjudicated_case_phrase(self) -> str:
        """'one case' / 'two cases', for prose."""
        count = self.audit_developer_adjudications["cases"]
        words = {0: "no", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
        noun = "case" if count == 1 else "cases"
        return f"{words.get(count, str(count))} {noun}"

    @property
    def audit_selection_rule(self) -> str:
        """Describe the rule after verifying it against the frozen row sets."""
        if self._audit_row_keys != self._legacy_threshold_row_keys:
            raise ValueError(
                "Frozen annotations do not equal the legacy-threshold audit universe"
            )
        return "rows whose legacy threshold score is below 1"

    @property
    def exact_match_miss_count(self) -> int:
        return len(self._exact_match_miss_row_keys)

    @property
    def exact_match_miss_count_fmt(self) -> str:
        return f"{self.exact_match_miss_count:,}"

    @property
    def annotated_exact_miss_count(self) -> int:
        return len(self._audit_row_keys & self._exact_match_miss_row_keys)

    @property
    def annotated_exact_miss_count_fmt(self) -> str:
        return f"{self.annotated_exact_miss_count:,}"

    @property
    def annotated_exact_hit_count(self) -> int:
        return len(self._audit_row_keys - self._exact_match_miss_row_keys)

    @property
    def annotated_exact_hit_count_fmt(self) -> str:
        return f"{self.annotated_exact_hit_count:,}"

    @property
    def unannotated_below_full_bounded_score_count(self) -> int:
        return len(self._below_full_bounded_score_row_keys - self._audit_row_keys)

    @property
    def unannotated_below_full_bounded_score_count_fmt(self) -> str:
        return f"{self.unannotated_below_full_bounded_score_count:,}"

    @property
    def wrong_row_count(self) -> int:
        """Backward-compatible alias for the legacy-threshold annotation count."""
        return self.audit_annotated_row_count

    @property
    def wrong_row_count_fmt(self) -> str:
        """Backward-compatible formatted legacy-threshold annotation count."""
        return self.audit_annotated_row_count_fmt

    @cached_property
    def _audit_source_counts(self) -> Counter:
        return Counter(row["failure_source"] for row in self._audit_rows)

    @cached_property
    def _audit_reference_suspect_counts(self) -> Counter:
        return Counter(
            row["reference_suspect"].strip().lower() for row in self._audit_rows
        )

    @property
    def audit_llm_error_only(self) -> bool:
        """True iff each annotated row is sourced to ``llm_error``."""
        counts = self._audit_source_counts
        return set(counts) == {"llm_error"}

    @property
    def audit_llm_error_count_fmt(self) -> str:
        return f"{self._audit_source_counts.get('llm_error', 0):,}"

    @property
    def audit_reference_bug_count(self) -> int:
        """Number of annotated rows flagged as reference-suspect (true)."""
        return self._audit_reference_suspect_counts.get("true", 0)

    @property
    def audit_zero_reference_bugs(self) -> bool:
        """True iff no annotated row is flagged reference-suspect."""
        return self.audit_reference_bug_count == 0

    @property
    def audit_reference_bug_count_fmt(self) -> str:
        return f"{self.audit_reference_bug_count:,}"

    @cached_property
    def _failure_subtype_counts(self) -> Counter:
        return Counter(row["failure_subtype"] for row in self._audit_rows)

    def top_failure_subtypes(self, n: int = 3) -> str:
        """Most common audited failure subtypes, humanized and joined."""
        humanized = {
            "taxable_income_or_deductions": "taxable income or deductions",
            "thresholds_rates": "thresholds and rates",
            "categorical_eligibility": "categorical eligibility",
            "credit_phaseout": "credit phase-outs",
            "payroll_tax_base": "the payroll-tax base",
            "state_local_rule": "state and local rules",
            "health_coverage": "health-coverage eligibility",
        }
        top = [name for name, _ in self._failure_subtype_counts.most_common(n)]
        return _ordinal_join(
            [humanized.get(name, name.replace("_", " ")) for name in top]
        )


# Module-level singleton, imported by the paper as ``from
# policybench.paper_results import r``.
r = PaperResults()


# Public release date per model: the first day any member of the public could
# use it (paid tiers count; trusted-tester previews do not). Compiled
# 2026-09-01 from vendor announcements and contemporaneous press; per-model
# sources follow each entry.
MODEL_RELEASE_DATES: dict[str, str] = {
    # platform.claude.com/docs/en/models/fable-5-1/overview ("Released
    # September 1, 2026")
    "claude-fable-5.1": "2026-09-01",
    # Models API created_at 2026-09-21 (api.anthropic.com/v1/models, read
    # 2026-09-22)
    "claude-opus-5.5": "2026-09-21",
    # platform.claude.com/docs/en/models/sonnet-5-5/overview ("Released
    # September 28, 2026"); Models API created_at 2026-09-28
    # (api.anthropic.com/v1/models, read 2026-09-28)
    "claude-sonnet-5.5": "2026-09-28",
    # platform.claude.com/docs/en/models/haiku-5-5/overview ("Released
    # October 7, 2026"); Models API created_at 2026-10-07
    # (api.anthropic.com/v1/models, read 2026-10-08)
    "claude-haiku-5.5": "2026-10-07",
    # anthropic.com/news/claude-fable-5-mythos-5 (2026-06-09)
    "claude-fable-5": "2026-06-09",
    # announced and available 2026-07-24 (fortune.com, bloomberg.com,
    # 9to5google.com all dated 2026-07-24)
    "claude-opus-5": "2026-07-24",
    # anthropic.com/news/claude-sonnet-5 (2026-06-30)
    "claude-sonnet-5": "2026-06-30",
    # anthropic.com/news/claude-opus-4-8; macrumors.com 2026-05-28
    "claude-opus-4.8": "2026-05-28",
    # github.blog/changelog/2026-04-16-claude-opus-4-7-is-generally-available
    "claude-opus-4.7": "2026-04-16",
    # anthropic.com/news/claude-haiku-4-5 (2025-10-15)
    "claude-haiku-4.5": "2025-10-15",
    # anthropic.com/news/claude-sonnet-4-6 (2026-02-17)
    "claude-sonnet-4.6": "2026-02-17",
    # techcrunch.com 2025-12-17 gemini-3-flash launch
    "gemini-3-flash-preview": "2025-12-17",
    # blog.google gemini-3-1-pro; 9to5google.com 2026-02-19
    "gemini-3.1-pro-preview": "2026-02-19",
    # blog.google gemini-3-5 (2026-05-19, Google I/O)
    "gemini-3.5-flash": "2026-05-19",
    # 9to5google.com 2026-07-21 gemini-3-6-flash launch
    "gemini-3.6-flash": "2026-07-21",
    # blog.google/innovation-and-ai/models-and-research/gemini-models/
    # gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber (2026-07-21, launched
    # beside 3.6 Flash; 9to5google.com 2026-07-21)
    "gemini-3.5-flash-lite": "2026-07-21",
    # blog.google/innovation-and-ai/models-and-research/gemini-models/
    # 3-8-flash-and-3-8-flash-cyber (2026-09-02); 9to5google.com and
    # theregister.com 2026-09-02
    "gemini-3.8-flash": "2026-09-02",
    # blog.google/products/gemini/gemini-3-7-flash (2026-08-13)
    "gemini-3.7-flash": "2026-08-13",
    # blog.google gemini-3-1-flash-lite; siliconangle.com 2026-03-03
    "gemini-3.1-flash-lite-preview": "2026-03-03",
    # openai.com/index/introducing-gpt-5-4-mini-and-nano; 9to5mac 2026-03-17
    "gpt-5.4-mini": "2026-03-17",
    "gpt-5.4-nano": "2026-03-17",
    # en.wikipedia.org/wiki/GPT-5.5 (2026-04-23; API 04-24)
    "gpt-5.5": "2026-04-23",
    # techcrunch.com 2026-07-09 gpt-5-6 family GA (trusted-partner preview
    # 2026-06-26 excluded under the public-availability rule)
    "gpt-5.6-sol": "2026-07-09",
    "gpt-5.6-terra": "2026-07-09",
    "gpt-5.6-luna": "2026-07-09",
    # unveiled and released as a limited preview for trusted partners
    # 2026-09-03 (cnbc.com 2026-09-03), released to paid users the following
    # day (en.wikipedia.org/wiki/GPT-6_Astra citing Japan Today 2026-09-04);
    # the trusted-partner day is excluded under the public-availability rule
    "gpt-6-astra": "2026-09-04",
    # openai.com/index/introducing-gpt-6-sol-and-luna (2026-09-22; API and
    # ChatGPT availability the same day per techcrunch.com 2026-09-22)
    "gpt-6-sol": "2026-09-22",
    # OpenAI announced GPT-6.1 Sol at DevDay on 2026-09-29 (API id gpt-6.1-sol).
    "gpt-6.1-sol": "2026-09-29",
    "gpt-6-luna": "2026-09-22",
    # piunikaweb.com 2026-04-17 SuperGrok beta (paid public tier)
    "grok-4.3": "2026-04-17",
    # x.ai/news/grok-4-5; techcrunch.com 2026-07-08
    "grok-4.5": "2026-07-08",
    # x.ai/news/grok-4-6 (2026-08-12)
    "grok-4.6": "2026-08-12",
    # x.ai/news/grok-4-7 (2026-09-21; the post puts the model in Cursor, Grok
    # Build and the Grok API that day). The API's language-models record
    # carries created 2026-09-02; like grok-4.6's (created 2026-08-06), that
    # predates the public launch and is not a release date.
    "grok-4.7": "2026-09-21",
    # API public beta per secondary trackers (bighatgroup.com xai-weekly
    # 2026-06-03); no vendor-dated announcement exists
    "grok-build-0.1": "2026-05-29",
    # api-docs.deepseek.com/news/news260424 (MIT weights same day)
    "deepseek-v4-pro": "2026-04-24",
    "deepseek-v4-flash": "2026-04-24",
    # dated checkpoints huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731 and
    # DeepSeek-V4-Pro-0813 (MIT weights; the 0813 card calls itself the
    # official V4 Pro release superseding the preview); checkpoint dates per
    # unsloth.ai/docs/models/deepseek-v4 (2026-07-31, 2026-08-13)
    "deepseek-v4-flash-0731": "2026-07-31",
    "deepseek-v4-pro-0813": "2026-08-13",
    # api-docs.deepseek.com/news/news260910 ("DeepSeek-V4.1-Flash Release
    # 2026/09/10", live on the API as deepseek-flash; MIT weights at
    # huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash, created 2026-09-10)
    "deepseek-v4.1-flash": "2026-09-10",
    # verdent.ai kimi-k2.6 guide; huggingface.co/moonshotai/Kimi-K2.6
    "kimi-k2.6": "2026-04-20",
    # simonwillison.net/2026/Jul/16/kimi-k3 (API launch; weights announced
    # for 2026-07-27, not yet published at the snapshot date)
    "kimi-k3": "2026-07-16",
    # felloai.com glm-5-2 (API 2026-06-13; MIT weights 2026-06-16/17)
    "glm-5.2": "2026-06-13",
    # Z.ai API and coding tiers 2026-08-14 (cellcog.ai glm-5-3-for-ai-agents;
    # elsolitario.org 2026-08-14); OpenRouter listing 2026-08-18; weights on
    # Hugging Face 2026-08-28 under the GLM-5.3 License after a safety review
    "glm-5.3": "2026-08-14",
    # techtimes.com 2026-06-01; weights on Hugging Face by 2026-06-07
    "minimax-m3": "2026-06-01",
    # yottalabs.ai qwen-3-7-max (2026-05-19); CLOSED — API-only, no weights
    "qwen-3.7-max": "2026-05-19",
    # marktechpost.com 2026-08-03 (GA on QwenCloud + OpenRouter); the
    # 2026-07-19 WAIC preview was Qoder-platform-only, excluded under the
    # first-paid-public-availability rule. Weights promised but not yet
    # published as of 2026-08-03 — closed until they appear.
    "qwen3.8-max": "2026-08-03",
    # techcrunch.com 2026-07-15; weights on Hugging Face the same day
    # under Apache 2.0 (Thinking Machines Lab's first from-scratch model)
    "inkling": "2026-07-15",
    # openrouter.ai/stealth/ox-alpha ("released on August 20, 2026" as a
    # stealth preview; the 2026-09-01 table carried 08-21 from the listing's
    # first observed day). After the row's run Z.ai identified the preview as
    # GLM-5.3-Flash (same page, 2026-08-26). The row keeps its preview label.
    "ox-alpha": "2026-08-20",
}

# Models whose weights are publicly downloadable. GLM-5.3's weights shipped
# 2026-08-28 under the GLM-5.3 License (MIT-style with a security-review
# condition for the largest Model-as-a-Service providers), two weeks after
# its API launch; the dated DeepSeek V4 checkpoints and DeepSeek V4.1 Flash
# (huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash, 2026-09-10) are MIT.
# Ox Alpha is not marked: the preview checkpoint itself was never
# published, and Z.ai's later identification of it as GLM-5.3-Flash is
# not a weights release of that row.
# Qwen 3.7 Max and 3.8 Max
# are API-only as of 2026-08-03 (3.8's weights are promised but unpublished);
# Kimi K3's weights shipped on Hugging Face 2026-07-26/27 under a custom
# license; Inkling's shipped day one (2026-07-15) under Apache 2.0.
OPEN_WEIGHT_MODELS: frozenset[str] = frozenset(
    {
        "deepseek-v4-pro",
        "deepseek-v4-flash",
        "deepseek-v4-flash-0731",
        "deepseek-v4-pro-0813",
        "deepseek-v4.1-flash",
        "kimi-k2.6",
        "kimi-k3",
        "glm-5.2",
        "glm-5.3",
        "minimax-m3",
        "inkling",
    }
)
