"""Score the frozen run under each combination of the Part B and SALT proposals.

Copies the frozen run (predictions, references, scenarios, exclusions) to scratch
directories and never writes the snapshot. Each copy is scored with ``python -m
policybench.cli analyze``, the command the freeze runs, and the dashboard payloads are
compared. The cases:

``published``
    The exclusion record unchanged. It must reproduce the published payload's scoring:
    every modelStats field except the cost and latency fields the freeze overlays, and
    programStats, heatmap, globalWeights and failureModes exactly.
``part_b``
    This audit's records if PolicyEngine/policybench#191 is not adopted: scenario_114's
    Virginia output and the standalone Part B record for its federal output.
``salt``
    #191's three records alone (022, 081 and 114 federal), as #191 scored them.
``salt_and_part_b``
    #191's three records and this audit's Virginia record.

Each case also recomputes the legacy household impact summary that the freeze writes
beside the analyze output (``impact_summary_by_model.csv``, pinned in the snapshot
manifest), with ``scripts/freeze_snapshot.household_impact_summary_by_model`` on the
scored reference; the published case must reproduce the frozen file.

``--weights-check`` also scores a copy whose eligibility impact weights are the ones
policyengine-us 2.15.17 computes (verification/sweep_part_b.csv) instead of the
published ones, which the 2026-09-29 rebuild did not recompute. It reports whether any
compared payload value changes and how the legacy impact summary moves.

#191's records are read from ``verification/inputs/pr191_proposed_exclusions.json``, a
copy of ``reference_audit/2026-10-05/proposed_exclusions.json`` at #191's head
8af912a0, checked against its sha256.

  PYTHONPATH=<checkout> <triage>/.venv-pe21517/bin/python \\
    reference_audit/2026-10-05-medicare-part-b/scripts/leaderboard_impact.py \\
      --scratch <dir> --weights-check
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
PROPOSED = HERE / "proposed_exclusions.json"
SWEEP = HERE / "verification/sweep_part_b.csv"
OUT_DIR = HERE / "verification"
SALT_COPY = HERE / "verification/inputs/pr191_proposed_exclusions.json"
SALT_SHA256 = "3c330177762c46fa5c52b02f9f943e9d5a65e15855280b64e9b462ab27413272"
FROZEN_IMPACT = RUN / "analysis/impact_summary_by_model.csv"
RUN_FILES = (
    "predictions.csv.gz",
    "reference_outputs.csv",
    "reference_outputs.csv.meta.json",
    "reference_exclusions.json",
    "scenarios.csv",
    "scenarios.csv.meta.json",
)
# The freeze overlays these from the published payload; the analyze CLI does not.
OVERLAID = {"costUsd", "costPerHousehold", "totalTokens", "latencySeconds"}
METRICS = (
    "exact",
    "within1pct",
    "within5pct",
    "within10pct",
    "score",
    "outputGroupScore",
)
EXACT_PAYLOAD_KEYS = ("programStats", "heatmap", "globalWeights", "failureModes")
RANKED = ("exact", "within1pct", "score")


def always_zero(run_dir: Path) -> dict[str, float]:
    """The always-zero baseline, as paper_results._always_zero_weighted_rates scores it."""
    import numpy as np

    from policybench.analysis import weighted_hit_rate_scores_by_model
    from policybench.reference_exclusions import scored_reference_for
    from policybench.spec import get_output_ids, output_group_id

    truth, _ = scored_reference_for(run_dir / "reference_outputs.csv")
    headline = set(get_output_ids("us", "headline"))
    truth = truth[truth["variable"].map(output_group_id).isin(headline)]
    truth = truth.reset_index(drop=True)
    truth["scenario_id"] = truth["scenario_id"].astype(str)
    scenarios = pd.read_csv(run_dir / "scenarios.csv")
    market = dict(
        zip(
            scenarios["scenario_id"].astype(str),
            pd.to_numeric(scenarios["total_income"], errors="coerce").fillna(0.0),
        )
    )
    predictions = truth[["scenario_id", "variable"]].copy()
    predictions["model"] = "Always zero"
    predictions["prediction"] = np.zeros(len(truth))
    scored = weighted_hit_rate_scores_by_model(truth, predictions, market, country="us")
    return {
        "exact": float(scored["weighted_exact"].mean()) * 100,
        "within1pct": float(scored["weighted_within_1pct"].mean()) * 100,
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def salt_records() -> list[dict]:
    if sha256(SALT_COPY) != SALT_SHA256:
        raise SystemExit(f"{SALT_COPY} does not match #191's file at 8af912a0")
    return json.loads(SALT_COPY.read_text())["exclusions"]


def legacy_impact_summary(run_dir: Path) -> pd.DataFrame:
    """The freeze's impact_summary_by_model.csv, computed on a staged copy."""
    from policybench.reference_exclusions import scored_reference_for

    path = ROOT / "scripts/freeze_snapshot.py"
    spec = importlib.util.spec_from_file_location("freeze_snapshot", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    truth, _ = scored_reference_for(run_dir / "reference_outputs.csv")
    predictions = pd.read_csv(run_dir / "predictions.csv.gz", low_memory=False)
    return module.household_impact_summary_by_model(truth, predictions)


def legacy_impact_change(base: pd.DataFrame, case: pd.DataFrame) -> dict:
    a = base.set_index("model")["mean_impact_score"]
    b = case.set_index("model")["mean_impact_score"].reindex(a.index)
    rank_a = a.rank(ascending=False, method="min")
    rank_b = b.rank(ascending=False, method="min")
    moved = rank_a != rank_b
    return {
        "mean_impact_score_delta": {
            "min": float((b - a).min()),
            "max": float((b - a).max()),
        },
        "models_changing_rank": int(moved.sum()),
        "rank_changes": {
            model: {"published": int(rank_a[model]), "case": int(rank_b[model])}
            for model in a.index[moved]
        },
    }


def stage(target: Path, extra: list[dict], weights: pd.DataFrame | None = None) -> Path:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in RUN_FILES:
        shutil.copy2(RUN / name, target / name)
    if extra:
        record = json.loads((target / "reference_exclusions.json").read_text())
        record["exclusions"].extend(extra)
        (target / "reference_exclusions.json").write_text(
            json.dumps(record, indent=2) + "\n"
        )
    if weights is not None:
        reference = pd.read_csv(target / "reference_outputs.csv")
        keyed = weights.set_index(["scenario_id", "variable"])["baseline_impact_weight"]
        keys = list(zip(reference["scenario_id"], reference["variable"]))
        has = reference["impact_weight"].notna()
        reference.loc[has, "impact_weight"] = [
            float(keyed[k]) for k, h in zip(keys, has) if h
        ]
        reference.to_csv(target / "reference_outputs.csv", index=False)
        # The analyzer checks the CSV against the digest its sidecar pins; repin the
        # scratch copy's sidecar to the rewritten CSV.
        meta_path = target / "reference_outputs.csv.meta.json"
        meta = json.loads(meta_path.read_text())
        meta["reference_csv_sha256"] = sha256(target / "reference_outputs.csv")
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    return target


def analyze(run_dir: Path) -> dict:
    out = run_dir / "analysis"
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
            str(out),
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


def check_reproduces_published(base: dict) -> None:
    published = json.loads(gzip.decompress((RUN / "data.json.gz").read_bytes()))
    diffs = payload_differences(published, base)
    if diffs:
        raise SystemExit(
            f"unchanged copy does not reproduce the published payload: {diffs[:10]}"
        )


def ranks(frame: pd.DataFrame, metric: str) -> pd.Series:
    return frame[metric].rank(ascending=False, method="min").astype(int)


def compare(base: dict, case: dict) -> pd.DataFrame:
    a = pd.DataFrame(base["modelStats"]).set_index("model")
    b = pd.DataFrame(case["modelStats"]).set_index("model")
    rows = pd.DataFrame(index=a.index)
    for metric in METRICS:
        rows[f"{metric}_published"] = a[metric]
        rows[f"{metric}_case"] = b[metric]
        rows[f"{metric}_delta"] = b[metric] - a[metric]
    for metric in RANKED:
        rows[f"{metric}_rank_published"] = ranks(a, metric)
        rows[f"{metric}_rank_case"] = ranks(b, metric)
    rows["n_published"] = a["n"]
    rows["n_case"] = b["n"]
    return rows.sort_values("exact_rank_published")


def program_rows(base: dict, case: dict) -> pd.DataFrame:
    a = pd.DataFrame(base["programStats"]).set_index("variable")
    b = pd.DataFrame(case["programStats"]).set_index("variable")
    rows = pd.DataFrame(index=a.index)
    for metric in ("exact", "score", "n"):
        rows[f"{metric}_published"] = a[metric]
        rows[f"{metric}_case"] = b[metric]
        rows[f"{metric}_delta"] = b[metric] - a[metric]
    return rows[(rows.filter(like="_delta").abs() > 1e-9).any(axis=1)]


def rank_changes(models: pd.DataFrame, metric: str) -> dict:
    return {
        model: {
            "published": int(row[f"{metric}_rank_published"]),
            "case": int(row[f"{metric}_rank_case"]),
        }
        for model, row in models.iterrows()
        if row[f"{metric}_rank_published"] != row[f"{metric}_rank_case"]
    }


def summarize(
    name: str, records: list[dict], base: dict, case: dict, zero: dict
) -> dict:
    models = compare(base, case)
    leader = models.sort_values("exact_rank_case").index[0]
    return {
        "case": name,
        "exclusions_added": [f"{r['scenario_id']}/{r['variable']}" for r in records],
        "scored_outputs": {
            "published": int(models["n_published"].iloc[0]),
            "case": int(models["n_case"].iloc[0]),
        },
        "exact_delta_pp": {
            "min": float(models["exact_delta"].min()),
            "max": float(models["exact_delta"].max()),
            "mean": float(models["exact_delta"].mean()),
        },
        "within1pct_delta_pp": {
            "min": float(models["within1pct_delta"].min()),
            "max": float(models["within1pct_delta"].max()),
        },
        "score_delta": {
            "min": float(models["score_delta"].min()),
            "max": float(models["score_delta"].max()),
        },
        **{f"{m}_rank_changes": rank_changes(models, m) for m in RANKED},
        "always_zero_baseline": zero,
        "leader": leader,
        "leader_exact": {
            "published": float(models.loc[leader, "exact_published"]),
            "case": float(models.loc[leader, "exact_case"]),
        },
        "leader_margin_over_always_zero_exact": {
            "published": float(
                models.loc[leader, "exact_published"] - zero["published"]["exact"]
            ),
            "case": float(models.loc[leader, "exact_case"] - zero["case"]["exact"]),
        },
        "programs": program_rows(base, case).round(6).reset_index().to_dict("records"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--weights-check", action="store_true")
    args = parser.parse_args()
    scratch = Path(args.scratch)

    proposal = json.loads(PROPOSED.read_text())
    va = proposal["exclusions"]
    federal = [c["record"] for c in proposal["conditional_on_salt_decision"]]
    salt = salt_records()
    cases = {
        "part_b": va + federal,
        "salt": salt,
        "salt_and_part_b": salt + va,
    }

    base_dir = stage(scratch / "published", [])
    base = analyze(base_dir)
    check_reproduces_published(base)
    zero_published = always_zero(base_dir)
    impact_base = legacy_impact_summary(base_dir)
    frozen_impact = pd.read_csv(FROZEN_IMPACT)
    pd.testing.assert_frame_equal(
        impact_base.reset_index(drop=True),
        frozen_impact,
        check_exact=False,
        rtol=0,
        atol=1e-12,
    )

    summaries, tables = [], {}
    for name, records in cases.items():
        run_dir = stage(scratch / name, records)
        case = analyze(run_dir)
        zero = {"published": zero_published, "case": always_zero(run_dir)}
        summary = summarize(name, records, base, case, zero)
        summary["legacy_impact_summary"] = legacy_impact_change(
            impact_base, legacy_impact_summary(run_dir)
        )
        summaries.append(summary)
        tables[name] = compare(base, case)

    # The marginal effect of the Virginia record on top of #191's records.
    salt_models = tables["salt"]
    both = tables["salt_and_part_b"]
    marginal = pd.DataFrame(
        {
            "exact_salt": salt_models["exact_case"],
            "exact_salt_and_part_b": both["exact_case"],
            "exact_delta": both["exact_case"] - salt_models["exact_case"],
            "rank_salt": salt_models["exact_rank_case"],
            "rank_salt_and_part_b": both["exact_rank_case"],
            "score_delta": both["score_case"] - salt_models["score_case"],
        }
    )
    marginal_summary = {
        "exact_delta_pp": {
            "min": float(marginal["exact_delta"].min()),
            "max": float(marginal["exact_delta"].max()),
        },
        "exact_rank_changes": {
            model: {
                "salt": int(r.rank_salt),
                "salt_and_part_b": int(r.rank_salt_and_part_b),
            }
            for model, r in marginal.iterrows()
            if r.rank_salt != r.rank_salt_and_part_b
        },
    }

    weights_check = None
    if args.weights_check:
        sweep = pd.read_csv(SWEEP)
        run_dir = stage(scratch / "weights_2_15_17", [], weights=sweep)
        moved = int(
            (
                sweep["reference_impact_weight"].notna()
                & (
                    (
                        sweep["reference_impact_weight"]
                        - sweep["baseline_impact_weight"]
                    ).abs()
                    > 1e-3
                )
            ).sum()
        )
        diffs = payload_differences(base, analyze(run_dir))
        weights_check = {
            "impact_weights_replaced": moved,
            "payload_differences": diffs,
            "legacy_impact_summary": legacy_impact_change(
                impact_base, legacy_impact_summary(run_dir)
            ),
        }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wide = pd.concat(
        {
            name: table[
                ["exact_case", "exact_rank_case", "score_case", "score_rank_case"]
            ]
            for name, table in tables.items()
        },
        axis=1,
    )
    wide.columns = [f"{case}_{col.removesuffix('_case')}" for case, col in wide.columns]
    first = tables["part_b"]
    wide.insert(0, "exact_published", first["exact_published"])
    wide.insert(1, "exact_rank_published", first["exact_rank_published"])
    wide.insert(2, "score_published", first["score_published"])
    wide.insert(3, "score_rank_published", first["score_rank_published"])
    wide.to_csv(OUT_DIR / "leaderboard_impact_models.csv")
    marginal.to_csv(OUT_DIR / "leaderboard_impact_marginal.csv")
    result = {
        "published_reproduced": True,
        "legacy_impact_summary_reproduced": True,
        "cases": summaries,
        "virginia_record_on_top_of_salt": marginal_summary,
        "impact_weights_check": weights_check,
    }
    (OUT_DIR / "leaderboard_impact.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    with pd.option_context("display.width", 250, "display.max_rows", 100):
        print(wide.round(4))
        print(marginal.round(4))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
