"""The matched-effort sensitivity (November 2026): data, scores and comparisons.

PolicyBench sends no reasoning setting, so Claude Fable 5.2's board row runs at
Anthropic's documented default effort for it (high) and Claude Opus 5.5's at its
documented default (medium). The sensitivity runs each model at the other's
default, one run of the board's 100 households each. Its request differs from
the board's by Anthropic's ``output_config.effort``, which
POLICYBENCH_REASONING_EFFORT_OVERRIDE sends for the named model, and by the
``anthropic-beta: effort-2025-11-24`` header litellm 1.95.0 adds to a request
carrying it:

- Claude Opus 5.5 at effort high (``claude-opus-5.5-effort-high``);
- Claude Fable 5.2 at effort medium (``claude-fable-5.2-effort-medium``).

Everything is scored with the board's own functions against the frozen
snapshot's references, weights and scored set (the 1,934 outputs left after
``reference_exclusions.json``). The four paired comparisons resample households
with :data:`policybench.analysis.SEED`: 10,000 draws of the households both
sides completed, from ``analysis.household_headline_scores`` (exact).

    PYTHONPATH=. python scripts/effort_sensitivity.py --check-board
    PYTHONPATH=. python scripts/effort_sensitivity.py --run-root RUNS \
        --board-run claude-fable-5.2=FABLE_BOARD_RUN \
        --board-run claude-opus-5.5=OPUS_BOARD_RUN

``--check-board`` reproduces the two board rows' frozen scores, cost and
latency from the snapshot's predictions. ``--run-root`` (the folder holding
``opus55-high/run`` and ``fable52-medium/run``) writes the predictions and
per-program assets and ``sensitivity/data/claude-effort-2026-11.json``. Each
``--board-run`` is the run folder a board row was frozen from (its
predictions must hash to the serving config's ``source_predictions_sha256``);
only its spend ledgers are read, for the request counts the snapshot's
predictions do not carry (failed attempts appear only in the ledger). Each
``--probe`` (optional; scoring does not need it) is one of the two probe
records written before the runs; the summary keeps its household, times, tokens
and cost (no answer of a probe is scored). The litellm version each board row
ran under is the repository lockfile's pin as last changed before that row's
first request.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import math
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from policybench.analysis import (
    SEED,
    _country_from_scenarios,
    household_headline_scores,
    model_cost_latency,
)
from policybench.config import PRICE_OVERRIDES_PER_1M
from policybench.reference_exclusions import scored_reference_for
from policybench.scorer_vectors import canonical_filtered_scores
from policybench.snapshot_payload import read_run_payload
from policybench.spec import output_group_id
from policybench.spend_ledger import count_budget_escalations, read_spend_ledger

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "sensitivity" / "data"
SUMMARY = DATA / "claude-effort-2026-11.json"
RUN_DIR = (
    ROOT
    / "paper/snapshot/20260501/runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace"
)
RELEASE = "dashboard-data-20261111"
N_BOOT = 10_000
# The plan's run rules (fixed before the first call).
PLAN_HOUSEHOLDS = 100
PLAN_CAP_USD = 45.0
PLAN_PER_ARM_USD = 22.5
# Where the board rows' effort labels come from: the board sends no effort, so
# each row runs at Anthropic's documented default, read on this day.
EFFORT_DEFAULTS = {
    "source": "https://platform.claude.com/docs/en/build-with-claude/effort",
    "read_on": "2026-11-12",
    "claude-fable-5.2": "high",
    "claude-opus-5.5": "medium",
}

# sensitivity model id -> arm definition
ARMS = {
    "claude-opus-5.5-effort-high": {
        "board_model": "claude-opus-5.5",
        "effort": "high",
        "board_effort": "medium",
        "stem": "sensitivity-claude-opus-5-5-effort-high",
        "run": "opus55-high",
        "override": "claude-opus-5-5=high",
    },
    "claude-fable-5.2-effort-medium": {
        "board_model": "claude-fable-5.2",
        "effort": "medium",
        "board_effort": "high",
        "stem": "sensitivity-claude-fable-5-2-effort-medium",
        "run": "fable52-medium",
        "override": "claude-fable-5-2=medium",
    },
}
BOARD_MODELS = ("claude-fable-5.2", "claude-opus-5.5")
# (key, first, second): each difference is first minus second, in points.
COMPARISONS = (
    (
        "fable_medium_vs_fable_board_high",
        "claude-fable-5.2-effort-medium",
        "claude-fable-5.2",
    ),
    (
        "opus_high_vs_opus_board_medium",
        "claude-opus-5.5-effort-high",
        "claude-opus-5.5",
    ),
    ("at_medium_fable_vs_opus", "claude-fable-5.2-effort-medium", "claude-opus-5.5"),
    ("at_high_fable_vs_opus", "claude-fable-5.2", "claude-opus-5.5-effort-high"),
)
SCORE_COLUMNS = ["model", "scenario_id", "variable", "prediction"]
USAGE_COLUMNS = [
    "error",
    "elapsed_seconds",
    "request_started_at",
    "request_completed_at",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "reasoning_tokens",
    "cached_prompt_tokens",
    "cache_write_prompt_tokens",
    "provider_reported_cost_usd",
    "reconstructed_cost_usd",
    "total_cost_usd",
    "cost_is_estimated",
    "estimated_cost_usd",
    "live_calls",
    "cache_hit_calls",
]
# The run's own columns, as the harness writes them; the assets keep them all.
ASSET_COLUMNS = [
    "call_id",
    "model",
    "scenario_id",
    "variable",
    "prediction",
    "explanation",
    "failure_source",
    "raw_response",
    "error",
    "elapsed_seconds",
    "request_started_at",
    "request_completed_at",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "reasoning_tokens",
    "cached_prompt_tokens",
    "cache_write_prompt_tokens",
    "provider_reported_cost_usd",
    "reconstructed_cost_usd",
    "total_cost_usd",
    "cost_is_estimated",
    "estimated_cost_usd",
    "provider_response_id",
    "provider_system_fingerprint",
    "provider_resolved_model",
    "live_calls",
    "cache_hit_calls",
    "live_elapsed_seconds",
]


@dataclass(frozen=True)
class ScoringInputs:
    reference: pd.DataFrame
    scenarios: pd.DataFrame
    weights_by_group: dict[str, float]
    market_income: dict[str, float]
    country: str | None
    payload: dict
    n_excluded: int


def scoring_inputs(run_dir: Path = RUN_DIR) -> ScoringInputs:
    """The frozen snapshot's scored reference, scenarios and board weights."""
    reference, excluded = scored_reference_for(run_dir / "reference_outputs.csv")
    scenarios = pd.read_csv(run_dir / "scenarios.csv")
    payload = read_run_payload(run_dir)
    weights_by_group: dict[str, float] = {}
    for variable, weight in payload["globalWeights"]["household"].items():
        group = output_group_id(variable)
        weights_by_group[group] = weights_by_group.get(group, 0.0) + weight
    market_income = dict(
        zip(
            scenarios["scenario_id"].astype(str),
            pd.to_numeric(scenarios["total_income"], errors="coerce").fillna(0.0),
            strict=True,
        )
    )
    return ScoringInputs(
        reference=reference,
        scenarios=scenarios,
        weights_by_group=weights_by_group,
        market_income=market_income,
        country=_country_from_scenarios(scenarios),
        payload=payload,
        n_excluded=len(excluded),
    )


def load_board_predictions(run_dir: Path = RUN_DIR) -> pd.DataFrame:
    """The two board rows' predictions from the frozen snapshot."""
    wanted = set(SCORE_COLUMNS + USAGE_COLUMNS)
    frames = []
    with pd.read_csv(
        run_dir / "predictions.csv.gz",
        usecols=lambda column: column in wanted,
        chunksize=20_000,
        low_memory=False,
    ) as reader:
        for chunk in reader:
            frames.append(chunk[chunk["model"].isin(BOARD_MODELS)])
    return pd.concat(frames, ignore_index=True)


def load_asset(stem: str, data: Path = DATA) -> pd.DataFrame:
    with gzip.open(data / f"{stem}-predictions.csv.gz", "rt", encoding="utf-8") as fh:
        return pd.read_csv(fh, low_memory=False)


def headline(predictions: pd.DataFrame, inputs: ScoringInputs) -> dict[str, dict]:
    """The board's exact, within-1% and bounded scores on the scored outputs."""
    out: dict[str, dict] = {}
    for field, key in (
        ("exact", "exact"),
        ("within1pct", "within1pct"),
        ("continuous", "score"),
    ):
        scores, _ = canonical_filtered_scores(
            inputs.reference,
            predictions[SCORE_COLUMNS],
            inputs.weights_by_group,
            set(inputs.weights_by_group),
            "all",
            field,
        )
        for model, value in scores.items():
            out.setdefault(model, {})[key] = float(value)
    return out


def household_exact(predictions: pd.DataFrame, inputs: ScoringInputs) -> pd.DataFrame:
    """Per-household headline (exact) scores, one column per model."""
    household = household_headline_scores(
        inputs.reference,
        predictions[SCORE_COLUMNS],
        inputs.market_income,
        country=inputs.country,
        metric="exact",
    )
    return household.pivot(index="scenario_id", columns="model", values="score").fillna(
        0.0
    )


def completed_households(predictions: pd.DataFrame) -> dict[str, set[str]]:
    return {
        model: set(frame["scenario_id"].astype(str))
        for model, frame in predictions.groupby("model")
    }


def paired_difference(
    wide: pd.DataFrame, first: str, second: str, households: list[str]
) -> dict:
    """First minus second, in points, with a paired household bootstrap
    (SEED, 10,000 draws, 95% percentile interval)."""
    frame = wide.loc[sorted(households)]
    diff = (frame[first] - frame[second]).to_numpy()
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, len(diff), size=(N_BOOT, len(diff)))
    means = diff[draws].mean(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    better = int((diff > 1e-12).sum())
    worse = int((diff < -1e-12).sum())
    return {
        "first": first,
        "second": second,
        "households": len(diff),
        "difference_points": float(100 * diff.mean()),
        "ci95_low_points": float(100 * lo),
        "ci95_high_points": float(100 * hi),
        "share_of_draws_above_zero": float((means > 0).mean()),
        "households_first_higher": better,
        "households_second_higher": worse,
        "households_tied": len(diff) - better - worse,
    }


def _utc(seconds: float) -> str:
    return pd.Timestamp(float(seconds), unit="s").strftime("%Y-%m-%dT%H:%M:%SZ")


def run_stats(predictions: pd.DataFrame, model: str) -> dict:
    """Cost, output tokens, median latency, calls and parse failures of one row."""
    rows = predictions[predictions["model"] == model]
    cost = model_cost_latency(rows, PRICE_OVERRIDES_PER_1M)[model]
    by_household = rows.groupby("scenario_id")
    # live_calls counts the answered provider calls behind a household's rows
    # (repeated on each row); rows written before the column existed leave it
    # empty, and then the count is not recorded rather than zero.
    recorded = bool(rows["live_calls"].notna().all())
    live_calls = by_household["live_calls"].first()
    parsed = rows["prediction"].notna()
    return {
        "households": int(rows["scenario_id"].nunique()),
        "outputs": int(len(rows)),
        "outputs_parsed": int(parsed.sum()),
        "parse_failures": int((~parsed).sum()),
        "cost_usd": float(cost["costUsd"]),
        "cost_per_household_usd": float(cost["costPerHousehold"]),
        "median_household_seconds": float(cost["latencySeconds"]),
        "output_tokens": int(round(float(rows["completion_tokens"].sum()))),
        "answered_calls": int(live_calls.sum()) if recorded else None,
        "households_with_a_second_answered_call": (
            int((live_calls > 1).sum()) if recorded else None
        ),
        "cache_hit_calls": (
            int(by_household["cache_hit_calls"].first().sum()) if recorded else None
        ),
        "first_request_utc": _utc(rows["request_started_at"].min()),
        "last_response_utc": _utc(rows["request_completed_at"].max()),
    }


def check_board(inputs: ScoringInputs, board: pd.DataFrame) -> dict:
    """Reproduce the board rows' frozen scores, cost and latency exactly."""
    stats = {row["model"]: row for row in inputs.payload["modelStats"]}
    scores = headline(board, inputs)
    wide = household_exact(board, inputs)
    report = {}
    for model in BOARD_MODELS:
        row = stats[model]
        mine = run_stats(board, model)
        report[model] = {
            "exact": (scores[model]["exact"], row["exact"]),
            "within1pct": (scores[model]["within1pct"], row["within1pct"]),
            "score": (scores[model]["score"], row["score"]),
            "household_mean_exact": (100 * float(wide[model].mean()), row["exact"]),
            "cost_usd": (mine["cost_usd"], row["costUsd"]),
            "median_household_seconds": (
                mine["median_household_seconds"],
                row["latencySeconds"],
            ),
            "n_parsed": (
                int(
                    inputs.reference.merge(
                        board[board["model"] == model][SCORE_COLUMNS],
                        on=["scenario_id", "variable"],
                    )["prediction"]
                    .notna()
                    .sum()
                ),
                row["nParsed"],
            ),
        }
    return report


def summarize(
    arm_predictions: pd.DataFrame, board: pd.DataFrame, inputs: ScoringInputs
) -> dict:
    combined = pd.concat([board, arm_predictions], ignore_index=True)
    scores = headline(combined, inputs)
    wide = household_exact(combined, inputs)
    done = completed_households(combined)
    stats = {row["model"]: row for row in inputs.payload["modelStats"]}
    scored_counts = {
        model: int(
            inputs.reference.merge(
                frame[SCORE_COLUMNS], on=["scenario_id", "variable"]
            )["prediction"]
            .notna()
            .sum()
        )
        for model, frame in combined.groupby("model")
    }
    runs = {}
    for model_id, arm in ARMS.items():
        runs[model_id] = {
            "model": arm["board_model"],
            "effort": arm["effort"],
            "board_effort": arm["board_effort"],
            "override": arm["override"],
            "board": {
                "exact": round(stats[arm["board_model"]]["exact"], 3),
                "within1pct": round(stats[arm["board_model"]]["within1pct"], 3),
                "score": round(stats[arm["board_model"]]["score"], 3),
                "n": int(stats[arm["board_model"]]["n"]),
                "n_parsed": int(stats[arm["board_model"]]["nParsed"]),
                **run_stats(board, arm["board_model"]),
            },
            "sensitivity": {
                "exact": round(scores[model_id]["exact"], 3),
                "within1pct": round(scores[model_id]["within1pct"], 3),
                "score": round(scores[model_id]["score"], 3),
                "n": len(inputs.reference),
                "n_parsed": scored_counts[model_id],
                **run_stats(arm_predictions, model_id),
            },
        }
    comparisons = {}
    for key, first, second in COMPARISONS:
        households = sorted(done[first] & done[second])
        comparisons[key] = paired_difference(wide, first, second, households)
    return {"runs": runs, "comparisons": comparisons}


def ledger_summary(run_dir: Path) -> dict:
    """Every provider request a run made, from its per-household spend ledgers
    (failed attempts appear only there): counts by status, the budget
    escalations, and each household that needed more than one request."""
    records = []
    for path in sorted((run_dir / "scenarios").glob("*.spend.jsonl")):
        records.extend(read_spend_ledger(path))
    by_household: dict[str, list[dict]] = {}
    for record in sorted(
        records,
        key=lambda r: (str(r["scenario_id"]), float(r.get("request_started_at") or 0)),
    ):
        by_household.setdefault(str(record["scenario_id"]), []).append(record)
    second = {
        scenario_id: [
            {
                "phase": r.get("phase"),
                "attempt": r.get("attempt"),
                "status": r.get("status"),
                "completion_budget_tokens": r.get("completion_budget_tokens"),
                "escalated_from_budget_tokens": r.get("escalated_from_budget_tokens"),
                "outputs_requested": len(r.get("variables") or []),
                "completion_tokens": r.get("completion_tokens"),
            }
            for r in requests
        ]
        for scenario_id, requests in by_household.items()
        if len(requests) > 1
    }
    return {
        "requests": len(records),
        "households": len(by_household),
        "by_status": dict(sorted(Counter(r.get("status") for r in records).items())),
        "budget_escalations": count_budget_escalations(records),
        "households_with_a_second_request": len(second),
        "second_requests": second,
    }


def board_run_record(model: str, run_dir: Path) -> dict:
    """The board row's own run folder: confirmed as the one the frozen row was
    taken from by the serving config's predictions hash, then its ledger."""
    serving = json.loads((RUN_DIR.parents[1] / "model_serving_config.json").read_text())
    evidence = serving["models"][model]["evidence"]
    digest = hashlib.sha256((run_dir / "predictions.csv").read_bytes()).hexdigest()
    assert digest == evidence["source_predictions_sha256"], (model, digest)
    return {"run": evidence["run"], **ledger_summary(run_dir)}


def write_gzip_csv(frame: pd.DataFrame, path: Path) -> None:
    with gzip.GzipFile(path, "wb", mtime=0) as sink:
        sink.write(frame.to_csv(index=False).encode("utf-8"))


def asset_pin(path: Path) -> dict:
    return {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def arm_predictions_from_runs(run_root: Path) -> pd.DataFrame:
    frames = []
    for model_id, arm in ARMS.items():
        frame = pd.read_csv(
            run_root / arm["run"] / "run" / "predictions.csv", low_memory=False
        )
        assert set(frame["model"]) == {arm["board_model"]}, (
            model_id,
            set(frame["model"]),
        )
        frame["model"] = model_id
        frames.append(frame[ASSET_COLUMNS])
    return pd.concat(frames, ignore_index=True)


def run_records(run_root: Path) -> dict:
    """What each arm's run state recorded: the treatment and the spend."""
    out = {}
    for model_id, arm in ARMS.items():
        state = json.loads(
            (run_root / arm["run"] / "run" / "run_state.json").read_text()
        )
        out[model_id] = {
            "treatment_fingerprint": state["treatment_fingerprint"],
            "workload": state["workload"],
            "completed": len(state["completed"])
            if isinstance(state["completed"], list)
            else state["completed"],
            "total": state["total"],
            "spent_usd": state["spent_usd"],
            "budget_usd": state["budget_usd"],
            "stopped_reason": state["stopped_reason"],
            "budget_escalation_count": state["budget_escalation_count"],
            "ledger": ledger_summary(run_root / arm["run"] / "run"),
            "started_at_utc": pd.Timestamp(state["started_at"], unit="s").strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "updated_at_utc": pd.Timestamp(state["updated_at"], unit="s").strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        }
    return out


def probe_record(path: Path) -> dict:
    """What the summary keeps of a probe: no ids, no answer."""
    record = json.loads(path.read_text())
    model = next(
        arm["board_model"]
        for arm in ARMS.values()
        if arm["override"] == f"{record['model_id']}={record['effort_requested']}"
    )
    assert record["litellm_outcome"] == "ok", path
    assert record["harness_thinking_record"] == {
        "reasoning_effort": record["effort_requested"]
    }, path
    return {
        "model": model,
        "effort": record["effort_requested"],
        "household": record["scenario_id"],
        "outputs": record["variables"],
        "started_utc": record["started_at_utc"],
        "ended_utc": record["ended_at_utc"],
        "prompt_tokens": record["litellm_usage"]["prompt_tokens"],
        "completion_tokens": record["litellm_usage"]["completion_tokens"],
        "cost_usd": record["cost_usd_at_list_price"],
        "litellm": record["litellm_version"],
        "scored": False,
    }


def lockfile_litellm(before_utc: str) -> dict:
    """The repository lockfile's litellm pin as last changed before a time."""
    commit = subprocess.run(
        ["git", "log", "-1", "--format=%H", f"--before={before_utc}", "--", "uv.lock"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    lock = subprocess.run(
        ["git", "show", f"{commit}:uv.lock"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    pin = r'\[\[package\]\]\nname = "litellm"\nversion = "([^"]+)"'
    (version,) = re.findall(pin, lock)
    return {"lockfile_commit": commit, "litellm": version}


def main() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from sensitivity_by_variable import by_variable_rates, write_asset

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-board", action="store_true")
    parser.add_argument("--run-root", type=Path)
    parser.add_argument(
        "--board-run",
        action="append",
        default=[],
        metavar="MODEL=RUN_DIR",
        help="a board row's own run folder (both board models are required)",
    )
    parser.add_argument(
        "--probe",
        action="append",
        default=[],
        type=Path,
        metavar="PROBE_JSON",
        help="a probe record written before the runs (one per arm)",
    )
    args = parser.parse_args()
    inputs = scoring_inputs()
    board = load_board_predictions()
    if args.check_board:
        report = check_board(inputs, board)
        exact_match = all(
            mine == frozen
            for checks in report.values()
            for name, (mine, frozen) in checks.items()
            if name in ("exact", "within1pct", "score", "n_parsed")
        )
        close_match = all(
            math.isclose(mine, frozen, rel_tol=0, abs_tol=1e-9)
            for checks in report.values()
            for mine, frozen in checks.values()
        )
        print(json.dumps(report, indent=1))
        print(f"scores equal the frozen floats exactly: {exact_match}")
        print(f"every figure within 1e-9 of the frozen value: {close_match}")
        sys.exit(0 if exact_match and close_match else 1)
    if args.run_root is None:
        parser.error("--run-root or --check-board")
    board_runs = dict(item.split("=", 1) for item in args.board_run)
    if set(board_runs) != set(BOARD_MODELS):
        parser.error(f"--board-run needed for each of {BOARD_MODELS}")
    probes = sorted(
        (probe_record(path) for path in args.probe), key=lambda p: p["started_utc"]
    )
    # The runs used this interpreter's litellm, as the probes did.
    effort_litellm = importlib.metadata.version("litellm")
    assert {p["litellm"] for p in probes} <= {effort_litellm}, probes
    arms = arm_predictions_from_runs(args.run_root)
    assets = {}
    for model_id, arm in ARMS.items():
        frame = arms[arms["model"] == model_id]
        path = DATA / f"{arm['stem']}-predictions.csv.gz"
        write_gzip_csv(frame, path)
        assets[path.name] = asset_pin(path)
        rates = by_variable_rates(
            load_asset(arm["stem"])[SCORE_COLUMNS], inputs.reference, inputs.scenarios
        )
        rates_path = DATA / f"{arm['stem']}-by-variable.csv.gz"
        write_asset(rates, rates_path)
        assets[rates_path.name] = asset_pin(rates_path)
    committed = pd.concat(
        [load_asset(arm["stem"]) for arm in ARMS.values()], ignore_index=True
    )
    summary = {
        "release": RELEASE,
        "plan": {
            "summary": (
                "fixed before the first call: each model at the other's provider "
                "default effort, one run of the board's 100 households per arm, a "
                "spend cap of $45 of API credit across both arms (each starting "
                "with $22.50), the board's retry rule, and the four comparisons "
                "below, each a paired household bootstrap; "
                "sensitivity/claude-effort-2026-11-plan.md gives the plan's text "
                "and records each departure from it"
            ),
            "households_per_arm": PLAN_HOUSEHOLDS,
            "cap_usd": PLAN_CAP_USD,
            "per_arm_start_usd": PLAN_PER_ARM_USD,
        },
        "condition": (
            "the board row's serving card and prompts; the request differs from "
            "the board's by Anthropic's output_config.effort, which "
            "POLICYBENCH_REASONING_EFFORT_OVERRIDE sends for the named model, and "
            f"by the anthropic-beta: effort-2025-11-24 header litellm {effort_litellm} "
            "adds to a request carrying it"
        ),
        "effort_defaults": EFFORT_DEFAULTS,
        "scored_against": (
            f"the frozen {len(inputs.payload['modelStats'])}-model board's reference "
            "outputs and household output-group weights (paper/snapshot/20260501), "
            f"with the {inputs.n_excluded} outputs listed in the run's "
            "reference_exclusions.json removed from scoring as they are for every "
            f"board row ({len(inputs.reference):,} scored outputs)"
        ),
        "bootstrap": {"seed": int(SEED), "draws": N_BOOT, "interval": "95% percentile"},
        "assets": assets,
        "run_records": run_records(args.run_root),
        "board_run_records": {
            model: board_run_record(model, Path(board_runs[model]))
            for model in BOARD_MODELS
        },
        **summarize(committed, board, inputs),
    }
    summary["probes"] = probes
    summary["client_library"] = {
        "effort_runs": {"litellm": effort_litellm},
        "board_rows": {
            arm["board_model"]: lockfile_litellm(
                summary["runs"][arm_id]["board"]["first_request_utc"]
            )
            for arm_id, arm in ARMS.items()
        },
    }
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: summary[k] for k in ("runs", "comparisons")}, indent=1))


if __name__ == "__main__":
    main()
