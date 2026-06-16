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
* ``paper/snapshot/20260501/runs/<us_label>/data.json`` -- the frozen US
  dashboard payload: the 13-model roster, ``modelStats`` exact-match and
  within-1% scores, per-output ``programStats`` and ``failureModes``
  breakdowns, household and scored-output counts.
* the frozen audit annotations dir (``manifest['audit_annotation_artifacts']``)
  -- the count of wrong rows, the fact that every wrong row is an ``llm_error``,
  and that zero rows are reference-suspect (no PolicyEngine bugs found).

The qmd imports ``r`` once in an ``#| echo: false`` setup cell and then every
inline number is a ```{python} r.field``` placeholder, so a future
snapshot refresh updates the prose with no edits to the manuscript text.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from functools import cached_property
from pathlib import Path

# ``paper_results`` lives in ``policybench/``; the repo root is one level up.
ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "paper" / "snapshot" / "20260501"

# Human-readable model names for the 13-model June roster. Aliases that do not
# appear here fall back to a humanized form of the PolicyBench id.
MODEL_DISPLAY_NAMES = {
    "claude-opus-4.8": "Claude Opus 4.8",
    "claude-opus-4.7": "Claude Opus 4.7",
    "claude-sonnet-4.6": "Claude Sonnet 4.6",
    "claude-haiku-4.5": "Claude Haiku 4.5",
    "grok-4.3": "Grok 4.3",
    "grok-build-0.1": "Grok Build 0.1",
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
#     df, _ = scenarios.load_enhanced_cps_person_frame()
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
        run_dir = SNAPSHOT_DIR / "runs" / self.us_run_label
        return json.loads((run_dir / "data.json").read_text())

    @cached_property
    def reference_meta(self) -> dict:
        run_dir = SNAPSHOT_DIR / "runs" / self.us_run_label
        meta = json.loads((run_dir / "reference_outputs.csv.meta.json").read_text())
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
        """policyengine.py version that generated the reference outputs."""
        return self.manifest["reference_output_refresh"]["policyengine_version"]

    @property
    def policyengine_us_version(self) -> str:
        return self.manifest["reference_output_refresh"]["policyengine_us_version"]

    @property
    def dataset_id(self) -> str:
        """Populace dataset name, e.g. ``populace_us_2024``."""
        return self.manifest["reference_output_refresh"]["policyengine_us_dataset"]

    @property
    def dataset_build_id(self) -> str:
        """Certified populace build id, e.g. ``populace-us-2024-5da5a95-20260611``."""
        return self.manifest["reference_output_refresh"][
            "policyengine_us_data_build_id"
        ]

    @property
    def dataset_uri(self) -> str:
        return self.manifest["reference_output_refresh"]["policyengine_us_dataset_uri"]

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
    def n_households(self) -> int:
        return self.manifest["scope"]["households"]["us"]

    @property
    def n_households_fmt(self) -> str:
        return f"{self.n_households:,}"

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
        run_dir = SNAPSHOT_DIR / "runs" / self.us_run_label
        with (run_dir / "reference_outputs.csv").open(newline="") as handle:
            return [float(row["value"]) for row in csv.DictReader(handle)]

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
        from policybench.spec import get_output_ids, output_group_id

        run_dir = SNAPSHOT_DIR / "runs" / self.us_run_label
        ground_truth = pd.read_csv(run_dir / "reference_outputs.csv")
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
    def wrong_row_count(self) -> int:
        return len(self._audit_rows)

    @property
    def wrong_row_count_fmt(self) -> str:
        return f"{self.wrong_row_count:,}"

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
        """True iff every audited wrong row is sourced to ``llm_error``."""
        counts = self._audit_source_counts
        return set(counts) == {"llm_error"}

    @property
    def audit_llm_error_count_fmt(self) -> str:
        return f"{self._audit_source_counts.get('llm_error', 0):,}"

    @property
    def audit_reference_bug_count(self) -> int:
        """Number of audited wrong rows flagged as reference-suspect (true)."""
        return self._audit_reference_suspect_counts.get("true", 0)

    @property
    def audit_zero_reference_bugs(self) -> bool:
        """True iff no audited wrong row is flagged reference-suspect."""
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
