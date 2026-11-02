"""Score the frozen run under three conventions for the federal regular tax.

  schedule  the published references: the section 1 rate schedule applied exactly.
  either    an answer is exact when it is within $1 of the published reference or
            within $1 of the reference recomputed with the constructed Tax Table.
  table     every scored reference takes its value under the constructed Tax
            Table (verification/sweep_tax_table.csv, the ``table`` variant),
            which moves the federal income tax and each output that follows it.

and, for comparison with PolicyBench's usual remedy for a reference a careful
reader could take two ways:

  exclude   the scored outputs the Tax Table moves by more than $1 leave scoring
            for every model. The scratch copy gets placeholder exclusion records
            so the analyze command will run; they are not proposed records.

Nothing published is written: the frozen run is read from git at the release
commit (scripts/release.py) into a scratch directory.

Two scorers, which must agree on every model under every convention:

  repo         ``python -m policybench.cli analyze`` on a staged copy for schedule,
               table and exclude (the command the freeze runs; the schedule
               copy must reproduce the published payload), and
               ``policybench.analysis.weighted_hit_rate_scores_by_model`` for all
               four. For ``either`` each model is scored against the accepted
               value nearer its answer, which is the same rule for an exact
               match.
  independent  scripts/independent_scorer.py, which reads the files itself and
               imports nothing from policybench.

  PYTHONDONTWRITEBYTECODE=1 uv run python \\
    reference_audit/2026-10-10-tax-table/scripts/leaderboard_impact.py --scratch <dir>

Writes verification/federal_cells.csv, model_answers.csv, model_counts.csv,
leaderboard_impact_models.csv and leaderboard_impact.json, and prints the model
table.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))

import independent_scorer  # noqa: E402
import release  # noqa: E402
import tax_table  # noqa: E402

OUT = HERE / "verification"
SWEEP = OUT / "sweep_tax_table.csv"
UNITS = OUT / "tax_units.csv"
DRAFT_TABLE = HERE / "law/irs_tax_table_2026_draft.csv"
FEDERAL = "federal_income_tax_before_refundable_credits"
YEAR = 2026
# The freeze overlays these from the published payload; the analyze CLI does not.
OVERLAID = {"costUsd", "costPerHousehold", "totalTokens", "latencySeconds"}
EXACT_PAYLOAD_KEYS = ("programStats", "heatmap", "globalWeights", "failureModes")
CONVENTIONS = ("schedule", "either", "table", "exclude")
AGREE_TOL = 1e-9


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(
    target: Path, values: dict | None = None, drop: list[tuple] | None = None
) -> Path:
    """A scratch copy of the frozen run, with some scored references replaced
    or (``drop``: scenario, variable, frozen value, other value) left unscored."""
    if target.exists():
        shutil.rmtree(target)
    release.materialize(target)
    if drop:
        path = target / "reference_exclusions.json"
        record = json.loads(path.read_text())
        record["exclusions"].extend(
            {
                "scenario_id": scenario_id,
                "variable": variable,
                "reason_code": "reference_depends_on_unlisted_input",
                "unlisted_input": "scratch placeholder: Tax Table or rate schedule",
                "alternative_reading": "scratch placeholder for scoring only",
                "frozen_value": frozen,
                "alternative_value": other,
                "engine_version": "policyengine-us 2.38.6",
                "decided_on": "2026-10-10",
                "decided_by": "scratch placeholder, not a decision",
            }
            for scenario_id, variable, frozen, other in drop
        )
        path.write_text(json.dumps(record, indent=2) + "\n")
    if values:
        path = target / "reference_outputs.csv"
        with path.open(newline="") as handle:
            rows = list(csv.reader(handle))
        header, body = rows[0], rows[1:]
        at = {name: header.index(name) for name in ("scenario_id", "variable", "value")}
        replaced = 0
        for row in body:
            key = (row[at["scenario_id"]], row[at["variable"]])
            if key in values:
                row[at["value"]] = repr(float(values[key]))
                replaced += 1
        if replaced != len(values):
            raise SystemExit("a replaced reference is not in the reference file")
        with path.open("w", newline="") as handle:
            csv.writer(handle, lineterminator="\n").writerows([header, *body])
        # The analyzer checks the CSV against the digest its sidecar pins; repin
        # the scratch copy's sidecar to the rewritten CSV.
        meta_path = target / "reference_outputs.csv.meta.json"
        meta = json.loads(meta_path.read_text())
        meta["reference_csv_sha256"] = sha256(path)
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    return target


def analyze(run_dir: Path) -> dict:
    dashboard = run_dir / "dashboard.json"
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "policybench.cli",
            "analyze",
            "-g",
            str(run_dir / "reference_outputs.csv"),
            "-p",
            str(run_dir / "predictions.csv.gz"),
            "-s",
            str(run_dir / "scenarios.csv"),
            "-o",
            str(run_dir / "analysis"),
            "--app-data-output",
            str(dashboard),
            "--reference-digest",
            sha256(run_dir / "reference_outputs.csv"),
        ],
        cwd=ROOT,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return json.loads(dashboard.read_text())["countries"]["us"]


def payload_differences(a: dict, b: dict) -> list[str]:
    """Compared payload values that differ (modelStats less the overlaid fields)."""
    out = [key for key in EXACT_PAYLOAD_KEYS if a[key] != b[key]]
    x = {m["model"]: m for m in a["modelStats"]}
    y = {m["model"]: m for m in b["modelStats"]}
    if set(x) != set(y):
        return out + ["modelStats: model sets differ"]
    for model, row in x.items():
        for field, value in row.items():
            if field not in OVERLAID and value != y[model].get(field):
                out.append(f"modelStats.{model}.{field}")
    return out


def repo_function_exact(run_dir: Path, alternative: dict | None = None) -> pd.Series:
    """The headline exact rate from the repo's scoring function.

    With ``alternative`` (a second accepted value for some outputs), each model is
    scored against whichever accepted value is nearer its own answer.
    """
    from policybench.analysis import weighted_hit_rate_scores_by_model
    from policybench.reference_exclusions import scored_reference_for

    truth, _ = scored_reference_for(run_dir / "reference_outputs.csv")
    scenarios = pd.read_csv(run_dir / "scenarios.csv")
    market = dict(
        zip(
            scenarios["scenario_id"].astype(str),
            pd.to_numeric(scenarios["total_income"], errors="coerce").fillna(0.0),
        )
    )
    predictions = pd.read_csv(run_dir / "predictions.csv.gz", low_memory=False)
    if not alternative:
        scored = weighted_hit_rate_scores_by_model(
            truth, predictions, market, country="us"
        )
        return scored.set_index("model")["weighted_exact"] * 100
    out = {}
    keys = list(zip(truth["scenario_id"], truth["variable"]))
    for model, rows in predictions.groupby("model"):
        answers = {
            (s, v): p
            for s, v, p in zip(rows["scenario_id"], rows["variable"], rows["prediction"])
        }
        own = truth.copy()
        values = []
        for key, value in zip(keys, truth["value"]):
            other = alternative.get(key)
            answer = answers.get(key)
            if other is not None and answer is not None and not pd.isna(answer):
                if abs(float(answer) - other) < abs(float(answer) - value):
                    value = other
            values.append(value)
        own["value"] = values
        scored = weighted_hit_rate_scores_by_model(own, rows, market, country="us")
        out[model] = float(scored["weighted_exact"].iloc[0]) * 100
    return pd.Series(out)


def ranks(series: pd.Series) -> pd.Series:
    return series.rank(ascending=False, method="min").astype(int)


FARM_INPUTS = ("farm_income", "farm_operations_income", "farm_rent_income")


def filers() -> dict[str, dict]:
    """Each household's tax unit head: age, and any farm income in the household.

    Form 8615 needs a filer under 24 and Schedule J needs income from farming or
    fishing, so these two facts bound where either could replace the look-up.
    """
    scenarios = pd.read_csv(io.BytesIO(release.read("scenarios.csv")))
    out = {}
    for scenario_id, text in zip(scenarios["scenario_id"], scenarios["scenario_json"]):
        adults = json.loads(text)["adults"]
        heads = [a for a in adults if a.get("inputs", {}).get("is_tax_unit_head")]
        if len(heads) != 1:
            raise SystemExit(f"{scenario_id}: not one tax unit head")
        out[scenario_id] = {
            "head_age": int(heads[0]["age"]),
            "farm_income": sum(
                float(a.get("inputs", {}).get(name) or 0.0)
                for a in adults
                for name in ("farm_income", "farm_rent_income")
            ),
            "has_farm_income": any(
                float(a.get("inputs", {}).get(name) or 0.0) != 0.0
                for a in adults
                for name in FARM_INPUTS
            ),
        }
    return out


def federal_cells(sweep: pd.DataFrame, units: pd.DataFrame) -> pd.DataFrame:
    """Each federal income tax reference, with its return's Tax Table look-up.

    Every benchmark household is one federal return in the engine, which this
    checks, so a reference and its return are one row.
    """
    with DRAFT_TABLE.open() as handle:
        draft = {int(r["at_least"]): r for r in csv.DictReader(handle)}
    if units.groupby(["system", "scenario_id"]).size().max() != 1:
        raise SystemExit("a household has more than one federal return")
    base = units[units["system"] == "baseline"].set_index("scenario_id")
    table = units[units["system"] == "table"].set_index("scenario_id")
    people = filers()
    rows = []
    for row in sweep[sweep["variable"] == FEDERAL].itertuples():
        unit, other = base.loc[row.scenario_id], table.loc[row.scenario_id]
        column = tax_table.COLUMN_FOR_FILING_STATUS[unit.filing_status]
        taxable = float(unit.taxable_income)
        # The amount taxed at the ordinary rates: line 15, or line 5 of the
        # Qualified Dividends and Capital Gain Tax Worksheet.
        ordinary = max(
            0.0, taxable - float(unit.capital_gains_excluded_from_taxable_income)
        )
        record = {
            "scenario_id": row.scenario_id,
            "state": row.state,
            "scored": bool(row.scored),
            "filing_status": unit.filing_status,
            "head_age": people[row.scenario_id]["head_age"],
            "has_farm_income": people[row.scenario_id]["has_farm_income"],
            "itemizes": bool(unit.itemizes),
            "capital_gain_worksheet": bool(unit.has_qdiv_or_ltcg and taxable > 0),
            "taxable_income": round(taxable, 2),
            "taxable_income_class": (
                "zero"
                if taxable <= 0
                else "under_100000"
                if taxable < tax_table.CEILING
                else "100000_or_more"
            ),
            "amount_at_ordinary_rates": round(ordinary, 2),
            "tax_table_applies": bool(0 < ordinary < tax_table.CEILING),
            "band": "",
            "schedule_tax_on_amount": round(float(unit.income_tax_main_rates), 2),
            "constructed_table_tax_on_amount": "",
            "irs_draft_2026_table_tax_on_amount": "",
            "marginal_rate": "",
            "schedule_regular_tax": round(float(unit.regular_tax_before_credits), 2),
            "table_regular_tax": round(float(other.regular_tax_before_credits), 2),
            "nonrefundable_credits_schedule": round(
                float(unit.income_tax_capped_non_refundable_credits), 2
            ),
            "nonrefundable_credits_table": round(
                float(other.income_tax_capped_non_refundable_credits), 2
            ),
            "reference": row.reference,
            "schedule_value": row.baseline,
            "constructed_table_value": row.table,
            "difference": row.table_delta,
            "differs_beyond_1": bool(row.table_moves),
            "table_whole_dollar_value": row.table_whole_dollar,
        }
        if record["tax_table_applies"]:
            lower, upper = tax_table.band(ordinary)
            constructed = tax_table.table_tax(ordinary, column, YEAR)
            if int(draft[lower][column]) != constructed:
                raise SystemExit("constructed table differs from the IRS draft")
            if abs(float(other.income_tax_main_rates) - constructed) > 1e-6:
                raise SystemExit("the sweep did not apply the constructed table")
            record.update(
                band=f"{lower}-{upper}",
                constructed_table_tax_on_amount=constructed,
                irs_draft_2026_table_tax_on_amount=int(draft[lower][column]),
                marginal_rate=tax_table.marginal_rate(ordinary, column, YEAR),
            )
        rows.append(record)
    return pd.DataFrame(rows)


def model_answers(
    predictions: pd.DataFrame, sweep: pd.DataFrame, changed: pd.DataFrame
) -> pd.DataFrame:
    """Every model's answer on each scored output the Tax Table changes."""
    keys = set(zip(changed["scenario_id"], changed["variable"]))
    rows = predictions[
        [(s, v) in keys for s, v in zip(predictions["scenario_id"], predictions["variable"])]
    ]
    values = changed.set_index(["scenario_id", "variable"])
    out = []
    for r in rows.itertuples():
        cell = values.loc[(r.scenario_id, r.variable)]
        answer = r.prediction
        parsed = answer is not None and not pd.isna(answer)
        near_schedule = parsed and abs(float(answer) - cell.baseline) <= 1.0
        near_table = parsed and abs(float(answer) - cell.table) <= 1.0
        explanation = str(r.explanation) if isinstance(r.explanation, str) else ""
        out.append(
            {
                "model": r.model,
                "scenario_id": r.scenario_id,
                "variable": r.variable,
                "prediction": answer,
                "schedule_value": cell.baseline,
                "constructed_table_value": cell.table,
                "table_moves_beyond_1": bool(cell.table_moves),
                "within_1_of_schedule": bool(near_schedule),
                "within_1_of_table": bool(near_table),
                "matches": (
                    "both"
                    if near_schedule and near_table
                    else "schedule"
                    if near_schedule
                    else "table"
                    if near_table
                    else "neither"
                ),
                "whole_dollar_answer": bool(parsed and float(answer) == round(float(answer))),
                "explanation_mentions_tax_table": "tax table" in explanation.lower(),
            }
        )
    return pd.DataFrame(out)


def model_counts(answers: pd.DataFrame, models: list[str]) -> pd.DataFrame:
    """Per model: answers on the federal cells the table moves by more than $1."""
    federal = answers[(answers["variable"] == FEDERAL) & answers["table_moves_beyond_1"]]
    rows = []
    for model in models:
        own = federal[federal["model"] == model]
        counts = own["matches"].value_counts()
        rows.append(
            {
                "model": model,
                "cells": int(len(own)),
                "matches_schedule": int(counts.get("schedule", 0)),
                "matches_table": int(counts.get("table", 0)),
                "matches_both": int(counts.get("both", 0)),
                "matches_neither": int(counts.get("neither", 0)),
                "whole_dollar_answers": int(own["whole_dollar_answer"].sum()),
                "explanations_mentioning_tax_table": int(
                    own["explanation_mentions_tax_table"].sum()
                ),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", required=True)
    args = parser.parse_args()
    scratch = Path(args.scratch)

    sweep = pd.read_csv(SWEEP)
    units = pd.read_csv(UNITS)
    scored = sweep[sweep["scored"]]
    changed = scored[(scored["table"] - scored["baseline"]).abs() > 1e-6]
    table_values = {
        (r.scenario_id, r.variable): float(r.table) for r in changed.itertuples()
    }

    cells = federal_cells(sweep, units)
    cells.to_csv(OUT / "federal_cells.csv", index=False)

    # Repo scorer, through the CLI.
    base_dir = stage(scratch / "schedule")
    base = analyze(base_dir)
    published = json.loads(gzip.decompress(release.read("data.json.gz")))
    published = published["countries"]["us"] if "countries" in published else published
    differences = payload_differences(published, base)
    if differences:
        raise SystemExit(f"the unchanged copy differs from the payload: {differences[:10]}")
    table_dir = stage(scratch / "table", table_values)
    table = analyze(table_dir)
    moved_scored = scored[scored["table_moves"]]
    exclude_dir = stage(
        scratch / "exclude",
        drop=[
            (r.scenario_id, r.variable, float(r.reference), float(r.table))
            for r in moved_scored.itertuples()
        ],
    )
    exclude = analyze(exclude_dir)

    cli = {
        "schedule": pd.DataFrame(base["modelStats"]).set_index("model"),
        "table": pd.DataFrame(table["modelStats"]).set_index("model"),
        "exclude": pd.DataFrame(exclude["modelStats"]).set_index("model"),
    }
    models = list(cli["schedule"].index)

    # Repo scorer, through its function; and the independent scorer.
    repo = {
        "schedule": repo_function_exact(base_dir),
        "either": repo_function_exact(base_dir, table_values),
        "table": repo_function_exact(table_dir),
        "exclude": repo_function_exact(exclude_dir),
    }
    independent = {
        "schedule": independent_scorer.exact_rates(base_dir),
        "either": independent_scorer.exact_rates(base_dir, also_accept=table_values),
        "table": independent_scorer.exact_rates(table_dir),
        "exclude": independent_scorer.exact_rates(exclude_dir),
    }
    agreement = {}
    for convention in CONVENTIONS:
        a = repo[convention].reindex(models)
        b = pd.Series(independent[convention]).reindex(models)
        gap = float((a - b).abs().max())
        agreement[convention] = {"max_abs_gap_repo_vs_independent": gap}
        if gap > AGREE_TOL:
            raise SystemExit(f"{convention}: scorers disagree by {gap}")
        if convention in cli:
            cli_gap = float((a - cli[convention]["exact"].reindex(models)).abs().max())
            agreement[convention]["max_abs_gap_function_vs_cli"] = cli_gap
            if cli_gap > AGREE_TOL:
                raise SystemExit(f"{convention}: function and CLI disagree by {cli_gap}")

    predictions = pd.read_csv(base_dir / "predictions.csv.gz", low_memory=False)
    answers = model_answers(predictions, sweep, changed)
    answers.to_csv(OUT / "model_answers.csv", index=False)
    counts = model_counts(answers, models)
    counts.to_csv(OUT / "model_counts.csv", index=False)

    frame = pd.DataFrame(index=pd.Index(models, name="model"))
    for convention in CONVENTIONS:
        frame[f"exact_{convention}"] = repo[convention].reindex(models)
        frame[f"exact_{convention}_independent"] = pd.Series(
            independent[convention]
        ).reindex(models)
        frame[f"rank_{convention}"] = ranks(frame[f"exact_{convention}"])
    for convention in CONVENTIONS[1:]:
        frame[f"exact_{convention}_delta"] = (
            frame[f"exact_{convention}"] - frame["exact_schedule"]
        )
    for metric in ("within1pct", "score"):
        for convention in cli:
            frame[f"{metric}_{convention}"] = cli[convention][metric].reindex(models)
    frame = frame.join(counts.set_index("model"))
    frame = frame.sort_values("rank_schedule")
    frame.to_csv(OUT / "leaderboard_impact_models.csv")

    def rank_changes(convention: str) -> dict:
        return {
            model: {
                "schedule": int(row["rank_schedule"]),
                convention: int(row[f"rank_{convention}"]),
            }
            for model, row in frame.iterrows()
            if row["rank_schedule"] != row[f"rank_{convention}"]
        }

    federal_scored = cells[cells["scored"]]
    moved = federal_scored[federal_scored["differs_beyond_1"]]
    delta = federal_scored["difference"]
    nonzero = delta[delta.abs() > 1e-6]
    federal_answers = answers[
        (answers["variable"] == FEDERAL) & answers["table_moves_beyond_1"]
    ]
    result = {
        "published_payload_reproduced": True,
        "release": {"tag": release.RELEASE, "commit": release.RELEASE_COMMIT},
        "inputs": dict(release.SHA256),
        "sweep_sha256": sha256(SWEEP),
        "models": len(models),
        "scored_outputs_per_model": {
            convention: int(stats["n"].iloc[0]) for convention, stats in cli.items()
        },
        "federal_references": {
            "all": int(len(cells)),
            "scored": int(len(federal_scored)),
            "scored_nonzero": int((federal_scored["schedule_value"].abs() > 1e-6).sum()),
            "scored_by_taxable_income": {
                str(name): int(count)
                for name, count in federal_scored["taxable_income_class"]
                .value_counts()
                .items()
            },
            "all_by_taxable_income": {
                str(name): int(count)
                for name, count in cells["taxable_income_class"].value_counts().items()
            },
            "scored_where_table_applies": int(
                federal_scored["tax_table_applies"].sum()
            ),
            "scored_itemizers_where_table_applies": int(
                (federal_scored["tax_table_applies"] & federal_scored["itemizes"]).sum()
            ),
            "scored_through_a_capital_gain_worksheet_where_table_applies": int(
                (
                    federal_scored["tax_table_applies"]
                    & federal_scored["capital_gain_worksheet"]
                ).sum()
            ),
            # Rounding only the looked-up amount to a whole dollar (the sweep's
            # table_whole_dollar variant), against the table variant.
            "look_up_rounding_sensitivity": {
                "scored_changed_by_any_amount": int(
                    (
                        (
                            federal_scored["constructed_table_value"]
                            - federal_scored["table_whole_dollar_value"]
                        ).abs()
                        > 1e-6
                    ).sum()
                ),
                "scored_moved_by_more_than_1": [
                    {
                        "scenario_id": r.scenario_id,
                        "table": float(r.constructed_table_value),
                        "table_whole_dollar": float(r.table_whole_dollar_value),
                    }
                    for r in federal_scored.itertuples()
                    if abs(r.constructed_table_value - r.table_whole_dollar_value) > 1
                ],
                "scored_max_abs_change_at_100000_or_more": float(
                    (
                        federal_scored["constructed_table_value"]
                        - federal_scored["table_whole_dollar_value"]
                    )
                    .abs()[federal_scored["taxable_income_class"] == "100000_or_more"]
                    .max()
                ),
            },
            # Where another method could replace the look-up: Form 8615 needs a
            # filer under 24, Schedule J income from farming or fishing.
            "returns_where_table_applies": {
                "all": int(cells["tax_table_applies"].sum()),
                "head_24_or_older": int(
                    (cells["tax_table_applies"] & (cells["head_age"] >= 24)).sum()
                ),
                "head_under_24": [
                    {"scenario_id": r.scenario_id, "head_age": int(r.head_age)}
                    for r in cells[
                        cells["tax_table_applies"] & (cells["head_age"] < 24)
                    ].itertuples()
                ],
                "with_farm_income": list(
                    cells[cells["tax_table_applies"] & cells["has_farm_income"]][
                        "scenario_id"
                    ]
                ),
            },
            "scored_changed_by_any_amount": int(len(nonzero)),
            "scored_differing_by_more_than_1": int(len(moved)),
            "scored_differing_by_1_or_less": int(len(nonzero) - len(moved)),
            "scored_unchanged": int(len(federal_scored) - len(nonzero)),
            "difference_distribution_among_changed": {
                "min": float(nonzero.min()),
                "p25": float(nonzero.quantile(0.25)),
                "median": float(nonzero.median()),
                "p75": float(nonzero.quantile(0.75)),
                "max": float(nonzero.max()),
                "mean": float(nonzero.mean()),
                "mean_abs": float(nonzero.abs().mean()),
                "table_higher": int((nonzero > 0).sum()),
                "table_lower": int((nonzero < 0).sum()),
            },
            "abs_difference_histogram": {
                label: int(((nonzero.abs() > low) & (nonzero.abs() <= high)).sum())
                for label, low, high in (
                    ("0-1", 0, 1),
                    ("1-2", 1, 2),
                    ("2-3", 2, 3),
                    ("3-4", 3, 4),
                    ("4-5", 4, 5),
                    ("5-6", 5, 6),
                    ("over 6", 6, np.inf),
                )
            },
        },
        "scored_outputs_the_table_changes": {
            variable: {
                "changed": int(len(group)),
                "beyond_1": int(group["table_moves"].sum()),
                "max_abs_delta": float(group["table_delta"].abs().max()),
            }
            for variable, group in changed.groupby("variable")
        },
        "excluded_outputs_the_table_changes": {
            variable: int(len(group))
            for variable, group in sweep[
                ~sweep["scored"] & ((sweep["table"] - sweep["baseline"]).abs() > 1e-6)
            ].groupby("variable")
        },
        "answers_on_federal_cells_moved_beyond_1": {
            "rows": int(len(federal_answers)),
            **{
                kind: int((federal_answers["matches"] == kind).sum())
                for kind in ("schedule", "table", "both", "neither")
            },
            "whole_dollar_answers": int(federal_answers["whole_dollar_answer"].sum()),
            "explanations_mentioning_tax_table": int(
                federal_answers["explanation_mentions_tax_table"].sum()
            ),
            "models_with_a_table_only_match": int((counts["matches_table"] > 0).sum()),
        },
        "answers_on_scored_outputs_changed_by_1_or_less": {
            "outputs": int((~changed["table_moves"]).sum()),
            "rows": int((~answers["table_moves_beyond_1"]).sum()),
            "exact_differs_between_the_two_values": int(
                (
                    ~answers["table_moves_beyond_1"]
                    & (answers["within_1_of_schedule"] != answers["within_1_of_table"])
                ).sum()
            ),
        },
        "all_federal_answers": {
            "rows": int((predictions["variable"] == FEDERAL).sum()),
            "explanations_mentioning_tax_table": int(
                predictions.loc[predictions["variable"] == FEDERAL, "explanation"]
                .fillna("")
                .str.contains("tax table", case=False)
                .sum()
            ),
        },
        "scorer_agreement": agreement,
        "conventions": {
            convention: {
                "exact_delta_pp": {
                    "min": float(frame[f"exact_{convention}_delta"].min()),
                    "max": float(frame[f"exact_{convention}_delta"].max()),
                    "mean": float(frame[f"exact_{convention}_delta"].mean()),
                },
                "models_gaining": int((frame[f"exact_{convention}_delta"] > 1e-12).sum()),
                "models_losing": int((frame[f"exact_{convention}_delta"] < -1e-12).sum()),
                "exact_rank_changes": rank_changes(convention),
                "leader": str(frame[f"exact_{convention}"].idxmax()),
                "leader_exact": float(frame[f"exact_{convention}"].max()),
            }
            for convention in CONVENTIONS[1:]
        },
        "leader_schedule": {
            "model": str(frame["exact_schedule"].idxmax()),
            "exact": float(frame["exact_schedule"].max()),
        },
    }
    (OUT / "leaderboard_impact.json").write_text(json.dumps(result, indent=2) + "\n")
    with pd.option_context("display.width", 250, "display.max_rows", 100):
        print(
            frame[
                [
                    "exact_schedule",
                    "exact_either",
                    "exact_table",
                    "exact_exclude",
                    "rank_schedule",
                    "rank_either",
                    "rank_table",
                    "rank_exclude",
                    "cells",
                    "matches_schedule",
                    "matches_table",
                    "matches_both",
                    "matches_neither",
                ]
            ].round(4)
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
