"""The matched-effort sensitivity's figures are pinned to committed evidence.

``sensitivity/data/claude-effort-2026-11.json`` summarizes the two runs (Claude
Opus 5.5 at effort high, Claude Fable 5.2 at effort medium). The committed
predictions must match the summary's pins; every score, run statistic and
paired comparison in the summary must recompute from those predictions and the
frozen snapshot (references, exclusions, weights and the two board rows'
predictions); and every figure in ``sensitivity/claude-effort-2026-11.md`` must
be one of those recomputed figures, rounded for display, or one the summary
records from files the repository does not hold (the spend ledgers' request
counts, the probe records) or from its lockfile history (the litellm pins),
which can be checked here only for consistency. The plan file
``sensitivity/claude-effort-2026-11-plan.md`` must hold the plan's sections and
a record whose figures are the summary's.
"""

import functools
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

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

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "sensitivity" / "data"
SUMMARY = json.loads((DATA / "claude-effort-2026-11.json").read_text())
DOC = ROOT / "sensitivity" / "claude-effort-2026-11.md"
PLAN_DOC = ROOT / "sensitivity" / "claude-effort-2026-11-plan.md"
MANIFEST = ROOT / "paper" / "snapshot" / "20260501" / "us_scenarios.csv"
SNAPSHOT_DIR = ROOT / "paper" / "snapshot" / "20260501"
RUN_DIR = SNAPSHOT_DIR / "runs" / "us_full_run_20260612_policyengine_4_16_1_populace"
SCORE_COLUMNS = ["model", "scenario_id", "variable", "prediction"]
STEMS = {
    "claude-opus-5.5-effort-high": "sensitivity-claude-opus-5-5-effort-high",
    "claude-fable-5.2-effort-medium": "sensitivity-claude-fable-5-2-effort-medium",
}
BOARD_MODELS = ("claude-fable-5.2", "claude-opus-5.5")
# Each comparison is first minus second; the plan fixed these four.
COMPARISONS = {
    "fable_medium_vs_fable_board_high": (
        "claude-fable-5.2-effort-medium",
        "claude-fable-5.2",
    ),
    "opus_high_vs_opus_board_medium": (
        "claude-opus-5.5-effort-high",
        "claude-opus-5.5",
    ),
    "at_medium_fable_vs_opus": ("claude-fable-5.2-effort-medium", "claude-opus-5.5"),
    "at_high_fable_vs_opus": ("claude-fable-5.2", "claude-opus-5.5-effort-high"),
}
DISPLAY = {
    "claude-fable-5.2": "Claude Fable 5.2",
    "claude-opus-5.5": "Claude Opus 5.5",
}


@functools.cache
def _payload() -> dict:
    return read_run_payload(RUN_DIR)


@functools.cache
def _reference() -> pd.DataFrame:
    reference, _ = scored_reference_for(RUN_DIR / "reference_outputs.csv")
    return reference


@functools.cache
def _scenarios() -> pd.DataFrame:
    return pd.read_csv(RUN_DIR / "scenarios.csv")


def _weights_by_group() -> dict[str, float]:
    weights: dict[str, float] = {}
    for variable, weight in _payload()["globalWeights"]["household"].items():
        group = output_group_id(variable)
        weights[group] = weights.get(group, 0.0) + weight
    return weights


@functools.cache
def _arm(model_id: str) -> pd.DataFrame:
    with gzip.open(DATA / f"{STEMS[model_id]}-predictions.csv.gz", "rt") as fh:
        return pd.read_csv(fh, low_memory=False)


@functools.cache
def _board() -> pd.DataFrame:
    """The two board rows' predictions, from the frozen snapshot."""
    frames = []
    with pd.read_csv(
        RUN_DIR / "predictions.csv.gz", chunksize=20_000, low_memory=False
    ) as reader:
        for chunk in reader:
            frames.append(chunk[chunk["model"].isin(BOARD_MODELS)])
    return pd.concat(frames, ignore_index=True)


def _predictions(model: str) -> pd.DataFrame:
    if model in STEMS:
        return _arm(model)
    board = _board()
    return board[board["model"] == model]


def _scores(predictions: pd.DataFrame) -> dict[str, float]:
    out = {}
    for field, key in (
        ("exact", "exact"),
        ("within1pct", "within1pct"),
        ("continuous", "score"),
    ):
        scores, _ = canonical_filtered_scores(
            _reference(),
            predictions[SCORE_COLUMNS],
            _weights_by_group(),
            set(_weights_by_group()),
            "all",
            field,
        )
        (value,) = scores.values()
        out[key] = float(value)
    return out


def _utc(seconds: float) -> str:
    return pd.Timestamp(float(seconds), unit="s").strftime("%Y-%m-%dT%H:%M:%SZ")


def _stats(predictions: pd.DataFrame) -> dict:
    (model,) = set(predictions["model"])
    cost = model_cost_latency(predictions, PRICE_OVERRIDES_PER_1M)[model]
    by_household = predictions.groupby("scenario_id")
    recorded = bool(predictions["live_calls"].notna().all())
    live_calls = by_household["live_calls"].first()
    parsed = predictions["prediction"].notna()
    return {
        "households": int(predictions["scenario_id"].nunique()),
        "outputs": int(len(predictions)),
        "outputs_parsed": int(parsed.sum()),
        "parse_failures": int((~parsed).sum()),
        "cost_usd": float(cost["costUsd"]),
        "cost_per_household_usd": float(cost["costPerHousehold"]),
        "median_household_seconds": float(cost["latencySeconds"]),
        "output_tokens": int(round(float(predictions["completion_tokens"].sum()))),
        "answered_calls": int(live_calls.sum()) if recorded else None,
        "households_with_a_second_answered_call": (
            int((live_calls > 1).sum()) if recorded else None
        ),
        "cache_hit_calls": (
            int(by_household["cache_hit_calls"].first().sum()) if recorded else None
        ),
        "first_request_utc": _utc(predictions["request_started_at"].min()),
        "last_response_utc": _utc(predictions["request_completed_at"].max()),
    }


def _scored_count(predictions: pd.DataFrame) -> int:
    merged = _reference().merge(
        predictions[SCORE_COLUMNS], on=["scenario_id", "variable"]
    )
    return int(merged["prediction"].notna().sum())


def test_committed_assets_match_the_summary_pins():
    assert set(SUMMARY["assets"]) == {
        f"{stem}-{kind}.csv.gz"
        for stem in STEMS.values()
        for kind in ("predictions", "by-variable")
    }
    for name, pin in SUMMARY["assets"].items():
        path = DATA / name
        assert path.stat().st_size == pin["bytes"], name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == pin["sha256"], name


@pytest.mark.parametrize("model_id", sorted(STEMS))
def test_arm_scores_recompute_from_committed_predictions(model_id):
    predictions = _arm(model_id)
    block = SUMMARY["runs"][model_id]["sensitivity"]
    assert set(predictions["model"]) == {model_id}
    scores = _scores(predictions)
    for key in ("exact", "within1pct", "score"):
        assert round(scores[key], 3) == block[key], key
    assert block["n"] == len(_reference())
    assert _scored_count(predictions) == block["n_parsed"]


@pytest.mark.parametrize("model_id", sorted(STEMS))
def test_board_blocks_match_the_frozen_snapshot(model_id):
    run = SUMMARY["runs"][model_id]
    board_row = next(m for m in _payload()["modelStats"] if m["model"] == run["model"])
    for key in ("exact", "within1pct", "score"):
        assert run["board"][key] == round(board_row[key], 3), key
    assert run["board"]["n"] == board_row["n"]
    assert run["board"]["n_parsed"] == board_row["nParsed"]
    # The board functions reproduce the frozen row from its predictions.
    board = _predictions(run["model"])
    scores = _scores(board)
    for key in ("exact", "within1pct", "score"):
        assert scores[key] == board_row[key], key
    stats = _stats(board)
    assert stats["cost_usd"] == board_row["costUsd"]
    assert stats["median_household_seconds"] == board_row["latencySeconds"]


@pytest.mark.parametrize("model_id", sorted(STEMS))
def test_run_statistics_recompute(model_id):
    run = SUMMARY["runs"][model_id]
    assert _stats(_arm(model_id)) == {
        key: run["sensitivity"][key] for key in _stats(_arm(model_id))
    }
    board_stats = _stats(_predictions(run["model"]))
    assert board_stats == {key: run["board"][key] for key in board_stats}


def _household_exact(models: list[str]) -> pd.DataFrame:
    scenarios = _scenarios()
    market_income = dict(
        zip(
            scenarios["scenario_id"].astype(str),
            pd.to_numeric(scenarios["total_income"], errors="coerce").fillna(0.0),
            strict=True,
        )
    )
    predictions = pd.concat(
        [_predictions(model)[SCORE_COLUMNS] for model in models], ignore_index=True
    )
    household = household_headline_scores(
        _reference(),
        predictions,
        market_income,
        country=_country_from_scenarios(scenarios),
        metric="exact",
    )
    return household.pivot(index="scenario_id", columns="model", values="score").fillna(
        0.0
    )


@functools.cache
def _recomputed_comparisons() -> dict[str, dict]:
    """The four paired comparisons, recomputed: household exact scores,
    SEED, 10,000 draws of the households, 95% percentile interval."""
    models = sorted({model for pair in COMPARISONS.values() for model in pair})
    wide = _household_exact(models)
    out = {}
    for key, (first, second) in COMPARISONS.items():
        both = sorted(
            set(_predictions(first)["scenario_id"].astype(str))
            & set(_predictions(second)["scenario_id"].astype(str))
        )
        diff = (wide.loc[both, first] - wide.loc[both, second]).to_numpy()
        rng = np.random.default_rng(SEED)
        draws = rng.integers(0, len(diff), size=(10_000, len(diff)))
        means = diff[draws].mean(axis=1)
        lo, hi = np.quantile(means, [0.025, 0.975])
        out[key] = {
            "households": len(diff),
            "difference_points": float(100 * diff.mean()),
            "ci95_low_points": float(100 * lo),
            "ci95_high_points": float(100 * hi),
            "share_of_draws_above_zero": float((means > 0).mean()),
            "households_first_higher": int((diff > 1e-12).sum()),
            "households_second_higher": int((diff < -1e-12).sum()),
        }
    return out


def test_the_bootstrap_block_is_the_test_s_own_method():
    """The summary's bootstrap settings are the ones this file recomputes with."""
    assert SUMMARY["bootstrap"] == {
        "seed": SEED,
        "draws": 10_000,
        "interval": "95% percentile",
    }


def test_each_run_stayed_under_its_cap_and_the_total_under_the_plan_s():
    plan = SUMMARY["plan"]
    costs = {model_id: _stats(_arm(model_id))["cost_usd"] for model_id in STEMS}
    for model_id, cost in costs.items():
        assert cost < plan["per_arm_start_usd"], model_id
        record = SUMMARY["run_records"][model_id]
        assert record["spent_usd"] < record["budget_usd"] == plan["per_arm_start_usd"]
        assert record["stopped_reason"] is None
    probes = sum(p["cost_usd"] for p in SUMMARY["probes"])
    assert sum(costs.values()) + probes < plan["cap_usd"]


def test_the_probes_came_before_the_runs_and_entered_no_score():
    """Two recorded probes, one per model at its arm's effort, on the frozen
    manifest's first household and one output, ended before either run's first
    request (from the committed predictions); no probe row is in the arms'
    predictions, which hold only the runs' households."""
    probes = SUMMARY["probes"]
    arms = {run["model"]: run["effort"] for run in SUMMARY["runs"].values()}
    assert {(p["model"], p["effort"]) for p in probes} == set(arms.items())
    first_household = pd.read_csv(MANIFEST, nrows=1)["scenario_id"].iloc[0]
    assert {p["household"] for p in probes} == {first_household}
    assert {len(p["outputs"]) for p in probes} == {1}
    assert not any(p["scored"] for p in probes)
    first_request = min(_stats(_arm(m))["first_request_utc"] for m in STEMS)
    assert max(p["ended_utc"] for p in probes) < first_request
    assert all(p["started_utc"] < p["ended_utc"] for p in probes)
    litellm = SUMMARY["client_library"]
    assert {p["litellm"] for p in probes} == {litellm["effort_runs"]["litellm"]}
    assert f"litellm {litellm['effort_runs']['litellm']} adds" in SUMMARY["condition"]
    assert "anthropic-beta: effort-2025-11-24" in SUMMARY["condition"]


def test_the_board_rows_effort_labels_are_the_documented_defaults():
    defaults = SUMMARY["effort_defaults"]
    for run in SUMMARY["runs"].values():
        assert defaults[run["model"]] == run["board_effort"]
        assert run["board_effort"] != run["effort"]
    assert {run["board_effort"] for run in SUMMARY["runs"].values()} == {
        run["effort"] for run in SUMMARY["runs"].values()
    }


def test_paired_comparisons_recompute():
    assert set(SUMMARY["comparisons"]) == set(COMPARISONS)
    for key, expected in _recomputed_comparisons().items():
        block = SUMMARY["comparisons"][key]
        assert (block["first"], block["second"]) == COMPARISONS[key], key
        for field, value in expected.items():
            assert block[field] == pytest.approx(value, abs=1e-9), (key, field)
        assert block["households_tied"] == (
            expected["households"]
            - expected["households_first_higher"]
            - expected["households_second_higher"]
        )


def test_household_mean_exact_is_the_headline():
    """The bootstrap's input averages to each row's headline exact score."""
    wide = _household_exact([*BOARD_MODELS, *STEMS])
    rows = {row["model"]: row["exact"] for row in _payload()["modelStats"]}
    for model in BOARD_MODELS:
        assert 100 * wide[model].mean() == pytest.approx(rows[model], abs=1e-9)
    for model_id in STEMS:
        assert 100 * wide[model_id].mean() == pytest.approx(
            _scores(_arm(model_id))["exact"], abs=1e-9
        )


def test_by_variable_assets_recompute_on_the_scored_reference():
    sys.path.insert(0, str(ROOT / "scripts"))
    from sensitivity_by_variable import by_variable_rates

    for model_id, stem in STEMS.items():
        expected = by_variable_rates(
            _arm(model_id)[SCORE_COLUMNS], _reference(), _scenarios()
        )
        committed = pd.read_csv(DATA / f"{stem}-by-variable.csv.gz")
        pd.testing.assert_frame_equal(
            committed, expected, check_exact=False, atol=1e-9, check_dtype=False
        )


def test_arms_keep_the_board_serving_card_but_the_effort():
    """Each run's recorded treatment equals its board row's frozen serving card
    in every field but ``thinking``, which carries the effort and nothing else."""
    serving = json.loads((SNAPSHOT_DIR / "model_serving_config.json").read_text())
    efforts = {
        "claude-opus-5.5-effort-high": "high",
        "claude-fable-5.2-effort-medium": "medium",
    }
    for model_id, record in SUMMARY["run_records"].items():
        board = serving["models"][SUMMARY["runs"][model_id]["model"]]["evidence"][
            "treatment_fingerprint"
        ]
        arm = record["treatment_fingerprint"]
        assert set(arm) == set(board), model_id
        assert {k for k in arm if arm[k] != board[k]} == {"thinking"}, model_id
        assert board["thinking"] == {"mode": "provider_default"}
        assert arm["thinking"] == {"reasoning_effort": efforts[model_id]}
        assert SUMMARY["runs"][model_id]["effort"] == efforts[model_id]
        assert record["stopped_reason"] is None, model_id
        assert record["budget_usd"] == SUMMARY["plan"]["per_arm_start_usd"]
        assert record["completed"] == record["total"]
        assert record["total"] == SUMMARY["plan"]["households_per_arm"]


# Note figures. Rounding and signs follow the doc: one decimal for scores,
# differences and seconds; cents for run costs, a tenth of a cent per household.
# Thousands separators inside a number only, so "1, 3" reads as 1 and 3.
NUMBER = re.compile(r"\d(?:[\d,]*\d)?(?:\.\d+)?")


def _one(x: float) -> str:
    text = f"{x:.1f}"
    return "0.0" if text == "-0.0" else text


def _signed(x: float) -> str:
    text = _one(x)
    return text if text.startswith("-") or text == "0.0" else f"+{text}"


def _rows() -> list[tuple[str, str, str]]:
    """(label, effort, model) for the doc's four score and cost rows."""
    return [
        ("Claude Fable 5.2 (board row)", "high", "claude-fable-5.2"),
        ("Claude Fable 5.2", "medium", "claude-fable-5.2-effort-medium"),
        ("Claude Opus 5.5 (board row)", "medium", "claude-opus-5.5"),
        ("Claude Opus 5.5", "high", "claude-opus-5.5-effort-high"),
    ]


COMPARISON_LABELS = {
    "fable_medium_vs_fable_board_high": (
        "1. Claude Fable 5.2, medium minus high (board row)"
    ),
    "opus_high_vs_opus_board_medium": (
        "2. Claude Opus 5.5, high minus medium (board row)"
    ),
    "at_medium_fable_vs_opus": (
        "3. At medium: Claude Fable 5.2 minus Claude Opus 5.5 (board row)"
    ),
    "at_high_fable_vs_opus": (
        "4. At high: Claude Fable 5.2 (board row) minus Claude Opus 5.5"
    ),
}


@functools.cache
def _expected_lines() -> tuple[str, ...]:
    """Every figure-bearing line of the doc's three tables, recomputed."""
    lines = []
    for label, effort, model in _rows():
        predictions = _predictions(model)
        scores = _scores(predictions)
        lines.append(
            f"| {label} | {effort} | {_one(scores['exact'])} "
            f"| {_one(scores['within1pct'])} | {_one(scores['score'])} "
            f"| {_scored_count(predictions):,}/{len(_reference()):,} |"
        )
    for key, label in COMPARISON_LABELS.items():
        c = _recomputed_comparisons()[key]
        tied = (
            c["households"]
            - c["households_first_higher"]
            - c["households_second_higher"]
        )
        lines.append(
            f"| {label} | {c['households']} | {_signed(c['difference_points'])} "
            f"| {_signed(c['ci95_low_points'])} to {_signed(c['ci95_high_points'])} "
            f"| {c['households_first_higher']}, {c['households_second_higher']}, "
            f"{tied} |"
        )
    for label, effort, model in _rows():
        s = _stats(_predictions(model))
        ledger = _ledger(model)
        lines.append(
            f"| {label} | {effort} | ${s['cost_usd']:,.2f} "
            f"| ${s['cost_per_household_usd']:,.3f} | {s['output_tokens']:,} "
            f"| {_one(s['median_household_seconds'])} | {ledger['requests']:,} "
            f"| {ledger['households_with_a_second_request']} | {s['parse_failures']} |"
        )
    return tuple(lines)


def _ledger(model: str) -> dict:
    """A row's request counts, as the summary records them from its run's
    spend ledger (the board rows' from the run each was frozen from)."""
    if model in STEMS:
        return SUMMARY["run_records"][model]["ledger"]
    return SUMMARY["board_run_records"][model]


def test_ledger_counts_agree_with_the_answered_calls_in_the_predictions():
    """Where the predictions record answered calls, each household's count is
    its ledger requests less those that ended in a provider error, and a
    household with one request has one answered call. Each ledger covers the
    100 households, and a board row's ledger is the frozen row's own run."""
    serving = json.loads((SNAPSHOT_DIR / "model_serving_config.json").read_text())
    for _label, _effort, model in _rows():
        ledger = _ledger(model)
        assert ledger["households"] == SUMMARY["plan"]["households_per_arm"]
        extra = sum(len(r) - 1 for r in ledger["second_requests"].values())
        assert ledger["requests"] == ledger["households"] + extra
        assert sum(ledger["by_status"].values()) == ledger["requests"]
        assert ledger["by_status"].get("ok") == ledger["households"]
        assert ledger["households_with_a_second_request"] == len(
            ledger["second_requests"]
        )
        assert ledger["budget_escalations"] == sum(
            r["escalated_from_budget_tokens"] is not None
            for requests in ledger["second_requests"].values()
            for r in requests
        )
        if model not in STEMS:
            run = serving["models"][model]["evidence"]["run"]
            assert ledger["run"] == run
        predictions = _predictions(model)
        if predictions["live_calls"].isna().all():
            assert model == "claude-opus-5.5"  # rows predate the column
            continue
        answered = predictions.groupby("scenario_id")["live_calls"].first()
        for scenario_id, count in answered.items():
            requests = ledger["second_requests"].get(scenario_id)
            expected = (
                1
                if requests is None
                else sum(r["status"] != "provider_error" for r in requests)
            )
            assert count == expected, (model, scenario_id)


def _doc_without_code() -> str:
    text = DOC.read_text()
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"\]\([^)]*\)", "] ", text)  # link targets
    return re.sub(r"\s+", " ", text)


def test_doc_tables_are_the_recomputed_figures():
    lines = DOC.read_text().splitlines()
    for line in _expected_lines():
        assert line in lines, line
    # The doc has no other figure-bearing table rows.
    table_rows = [
        line
        for line in lines
        if line.startswith("| ")
        and not line.startswith("| |")
        and "---" not in line
        and not line.startswith("| comparison")
    ]
    assert sorted(table_rows) == sorted(_expected_lines())


def _expected_prose() -> list[str]:
    arm_stats = {model: _stats(_arm(model)) for model in STEMS}
    days = {
        stamp[:10]
        for s in arm_stats.values()
        for stamp in (s["first_request_utc"], s["last_response_utc"])
    }
    (arm_day,) = days
    opus, fable = (
        arm_stats["claude-opus-5.5-effort-high"],
        arm_stats["claude-fable-5.2-effort-medium"],
    )
    fingerprint = SUMMARY["run_records"]["claude-opus-5.5-effort-high"][
        "treatment_fingerprint"
    ]
    plan = SUMMARY["plan"]
    households = plan["households_per_arm"]
    assert {s["households"] for s in arm_stats.values()} == {households}
    c = _recomputed_comparisons()

    def above_below(x: float) -> str:
        return "above" if x > 0 else "below" if x < 0 else "level with"

    c1, c2 = c["fable_medium_vs_fable_board_high"], c["opus_high_vs_opus_board_medium"]
    c3, c4 = c["at_medium_fable_vs_opus"], c["at_high_fable_vs_opus"]
    board_days = {
        model: _stats(_predictions(model))["first_request_utc"][:10]
        for model in BOARD_MODELS
    }
    budget = fingerprint["initial_completion_budget_tokens"]
    defaults = SUMMARY["effort_defaults"]
    probe_opus, probe_fable = SUMMARY["probes"]
    probe_cost = probe_opus["cost_usd"] + probe_fable["cost_usd"]
    both = opus["cost_usd"] + fable["cost_usd"]
    litellm = SUMMARY["client_library"]
    arm_litellm = litellm["effort_runs"]["litellm"]
    board_litellm = {m: v["litellm"] for m, v in litellm["board_rows"].items()}
    return [
        f"which PolicyBench read on {defaults['read_on']}, gives that default as"
        f" {defaults['claude-fable-5.2']} for Claude Fable 5.2 and"
        f" {defaults['claude-opus-5.5']} for Claude Opus 5.5; the board rows'"
        ' "high" and "medium" below are those documented defaults.',
        "The request differs from the board's by Anthropic's `output_config.effort`"
        " field, which the harness sends for one named model when"
        " `POLICYBENCH_REASONING_EFFORT_OVERRIDE` is set, and by the"
        " `anthropic-beta: effort-2025-11-24` header, which the client library,"
        f" litellm {arm_litellm}, adds to each request carrying that field with its"
        " bundled model map, which the runs used.",
        "A matched effort label does not mean matched tokens or cost;",
        f"Claude Opus 5.5 at high ran from {probe_opus['started_utc'][11:19]} to"
        f" {probe_opus['ended_utc'][11:19]} UTC on {probe_opus['started_utc'][:10]}"
        f" and cost ${probe_opus['cost_usd']:,.2f}; Claude Fable 5.2 at medium ran"
        f" from {probe_fable['started_utc'][11:19]} to"
        f" {probe_fable['ended_utc'][11:19]} UTC and cost"
        f" ${probe_fable['cost_usd']:,.2f}; ${probe_cost:,.2f} together.",
        "The probes' answers entered no score.",
        "they hold no response field that reports the effort Anthropic applied, and"
        " Anthropic's effort documentation names none.",
        f"The session that operated release {SUMMARY['release']}, which runs on"
        " Claude Fable 5.2, wrote the plan and started both runs. A Claude Opus 5.5"
        " agent wrote the option that sends the effort and the scripts, sent the two"
        " probes and ran the scoring. GPT-6.1 Sol, an OpenAI model, read the plan,"
        " the code change and a draft of this note before publication, as a bundle"
        " of those files rather than the repository, and asked for changes.",
        "[`claude-effort-2026-11-plan.md`](claude-effort-2026-11-plan.md) gives its"
        " rules word for word and, after them, a record of the runs that lists every"
        " departure from the plan.",
        f"a spend cap of ${plan['cap_usd']:,.0f} of API credit across both arms,"
        f" each arm starting with ${plan['per_arm_start_usd']:,.2f};",
        "PolicyBench counts a dollar amount as right when it falls within $1 of the"
        " reference PolicyEngine computes, and an eligibility answer as right when it"
        " matches, and weights each answer by household impact.",
        "so a difference can differ by 0.1 from the difference of the rounded scores"
        " above. The four comparisons are on this headline measure; the bounded"
        " score above is one figure per row, with no interval.",
        "takes the 2.5th and 97.5th percentiles of the resampled mean difference as"
        " the 95% interval;",
        "The intervals resample households, not runs; see Limits.",
        f"Two runs on {arm_day}, each over the board's {households} households",
        f"a {fingerprint['request_timeout_seconds']}-second timeout",
        f"a starting output budget of {budget:,}"
        f" tokens that doubles, up to {fingerprint['completion_budget_ceiling']:,},",
        f"one run per arm over all {households} households;",
        f"PolicyBench resamples the households {10_000:,} times with seed {SEED}",
        f"Scores are on the {len(_reference()):,} outputs the board scores;",
        f"Both runs completed all {households} households.",
        f"At medium, Claude Fable 5.2 scores {_one(abs(c3['difference_points']))}"
        f" points {above_below(c3['difference_points'])} Claude Opus 5.5.",
        f"At high, Claude Fable 5.2 scores {_one(abs(c4['difference_points']))} points"
        f" {above_below(c4['difference_points'])} Claude Opus 5.5.",
        f"Claude Fable 5.2 at medium scores {_one(abs(c1['difference_points']))}"
        f" points {above_below(c1['difference_points'])} its board row at high;",
        f"Claude Opus 5.5 at high scores {_one(abs(c2['difference_points']))}"
        f" points {above_below(c2['difference_points'])} its board row at medium.",
        f"The two runs cost ${opus['cost_usd']:,.2f} (Claude Opus 5.5 at high) and"
        f" ${fable['cost_usd']:,.2f} (Claude Fable 5.2 at medium),"
        f" ${both:,.2f} together, and the probes ${probe_cost:,.2f}:"
        f" ${both + probe_cost:,.2f} against the ${plan['cap_usd']:,.0f} cap.",
        f"Neither run reached its ${plan['per_arm_start_usd']:,.2f} cap.",
        f"The comparisons rest on {households} households.",
        f"the Claude Opus 5.5 board row on {board_days['claude-opus-5.5']},"
        f" the Claude Fable 5.2 board row on {board_days['claude-fable-5.2']},"
        f" and both effort runs on {arm_day}.",
        f"release {SUMMARY['release']}'s references and scored set.",
        "The board rows' effort labels are Anthropic's documented defaults, read on"
        f" {defaults['read_on']}: the board rows sent no effort, and no record shows"
        " the default in force when Claude Opus 5.5's board row ran.",
        "Claude Opus 5.5's board row ran when the repository's lockfile pinned"
        f" litellm {board_litellm['claude-opus-5.5']}, and Claude Fable 5.2's when it"
        f" pinned {board_litellm['claude-fable-5.2']}; both effort runs used litellm"
        f" {arm_litellm}.",
        f"PolicyBench checked offline, for all {households} households of both runs,",
    ]


def _pinned_text() -> list[str]:
    """Statements with no figure of their own: who ran what, the guards'
    timing, what the test covers, and the fresh caches."""
    return [
        "After the runs, PolicyBench tightened the option's guards, in the commits"
        " after `921a7886`; the plan's record lists the changes. The data under"
        " `sensitivity/data/` are from the runs made before that change, and nothing"
        " was rerun.",
        "`tests/test_effort_sensitivity_evidence.py` recomputes this page's scores,"
        " intervals, costs, output tokens, latencies and run dates from those files"
        " and the frozen snapshot. The request counts, the probes' figures and the"
        " litellm versions come from the summary's `run_records`,"
        " `board_run_records`, `probes` and `client_library` blocks,",
        "LITELLM_LOCAL_MODEL_COST_MAP=True \\"
        " POLICYBENCH_CACHE_DIR=results/local/claude-effort/opus55-high/cache \\",
        "LITELLM_LOCAL_MODEL_COST_MAP=True \\"
        " POLICYBENCH_CACHE_DIR=results/local/claude-effort/fable52-medium/cache \\",
        "Each run starts with an empty cache directory of its own, as the effort"
        " runs did. `LITELLM_LOCAL_MODEL_COST_MAP=True` keeps litellm on its bundled"
        " model map, as in the effort runs; with the remote map litellm loads"
        " otherwise, the request can go without the beta header.",
    ]


def _interval_sentence() -> str:
    def words(c: dict) -> str:
        if c["ci95_low_points"] > 0:
            return "lies above zero"
        if c["ci95_high_points"] < 0:
            return "lies below zero"
        return "includes zero"

    groups: dict[str, list[str]] = {}
    for number, key in enumerate(COMPARISON_LABELS, start=1):
        groups.setdefault(words(_recomputed_comparisons()[key]), []).append(str(number))
    parts = []
    for phrase, numbers in groups.items():
        named = (
            f"comparison {numbers[0]}"
            if len(numbers) == 1
            else "comparisons " + ", ".join(numbers[:-1]) + " and " + numbers[-1]
        )
        parts.append(f"{phrase} for {named}")
    body = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + ", and " + parts[-1]
    return f"The 95% interval {body}."


def _second_request_sentences() -> list[str]:
    """What the ledgers record of each row's second requests: a retry after a
    provider error at the same budget, or, after an answer that used the
    whole output budget, a request at double the budget."""
    sentences, single = [], []
    for label, effort, model in _rows():
        ledger = _ledger(model)
        name = (
            label.replace(" (board row)", "'s board row")
            if model not in STEMS
            else f"{label} at {effort}"
        )
        if not ledger["second_requests"]:
            single.append(name)
            continue
        retried, doubled, budgets = 0, 0, set()
        for first, second in ledger["second_requests"].values():
            assert second["status"] == "ok"
            if first["status"] == "provider_error":
                assert (
                    second["completion_budget_tokens"]
                    == first["completion_budget_tokens"]
                )
                retried += 1
            else:
                assert first["status"] == "parse_error"
                assert first["completion_tokens"] == first["completion_budget_tokens"]
                assert second["completion_budget_tokens"] == (
                    2 * first["completion_budget_tokens"]
                )
                doubled += 1
                budgets.add(first["completion_budget_tokens"])
        kinds = []
        if retried:
            kinds.append((retried, "after a provider error"))
        if doubled:
            (budget,) = budgets
            kinds.append(
                (
                    doubled,
                    f"after an answer stopped at the {budget:,}-token budget, "
                    "with the budget doubled",
                )
            )
        n = len(ledger["second_requests"])
        noun = "household" if n == 1 else "households"
        if len(kinds) == 1:
            body = f", each {kinds[0][1]}"
        else:
            body = ": " + ", and ".join(f"{k} {words}" for k, words in kinds)
        sentences.append(f"{name} made a second request for {n} {noun}{body}.")
    if single:
        sentences.append(
            " and ".join(single) + " needed one request for every household."
        )
    return sentences


def test_doc_prose_figures_are_the_recomputed_figures():
    text = re.sub(r"\s+", " ", DOC.read_text())
    for sentence in [
        *_expected_prose(),
        _interval_sentence(),
        *_second_request_sentences(),
        *_pinned_text(),
    ]:
        assert sentence in text, sentence
    # Whole words only: "against" holds "gains".
    assert not re.search(r"\b(gains?|gained|loses?|lost)\b", text)


PLAN_HEADINGS = [
    "## Why",
    "## Arms",
    "## Run rules",
    "## Scoring",
    "## Comparisons reported (all of them, whatever they show)",
    "## Publication",
    "## Review",
]


def test_the_plan_file_holds_the_plan_and_a_record_of_the_summary_s_figures():
    """The published plan: its seven sections in order, then the dated record.
    Its rules are the summary's plan terms, and the record's probe and spend
    figures are the summary's."""
    lines = PLAN_DOC.read_text().splitlines()
    headings = [line for line in lines if line.startswith("## ")]
    record = "## Record after the runs (2026-11-13)"
    assert headings == [*PLAN_HEADINGS, record]
    text = re.sub(r"\s+", " ", PLAN_DOC.read_text())
    plan_part, record_part = text.split(record)
    plan = SUMMARY["plan"]
    for rule in (
        f"One run per arm, {plan['households_per_arm']} households each.",
        f"Spend cap: ${plan['cap_usd']:,.0f} of API credit across both arms. Each arm"
        f" starts with ${plan['per_arm_start_usd']:,.2f}.",
        "The effort value is the only difference from the board condition.",
        "Paired by household, with the bootstrap method and seed of",
    ):
        assert rule in plan_part, rule
    # The header's note on that method states the summary's bootstrap.
    boot = SUMMARY["bootstrap"]
    assert (
        f"a bootstrap paired by household, with seed {boot['seed']},"
        f" {boot['draws']:,} draws and a {boot['interval']} interval."
    ) in plan_part
    probe_opus, probe_fable = SUMMARY["probes"]
    probes = probe_opus["cost_usd"] + probe_fable["cost_usd"]
    spent = {m: r["spent_usd"] for m, r in SUMMARY["run_records"].items()}
    opus, fable = (
        spent["claude-opus-5.5-effort-high"],
        spent["claude-fable-5.2-effort-medium"],
    )
    for sentence in (
        f"they cost ${probe_opus['cost_usd']:,.2f} (Claude Opus 5.5) and"
        f" ${probe_fable['cost_usd']:,.2f} (Claude Fable 5.2), ${probes:,.2f}"
        " together. Their answers entered no score.",
        f"The runs spent ${opus:,.2f} (Claude Opus 5.5 at high) and ${fable:,.2f}"
        f" (Claude Fable 5.2 at medium), ${opus + fable + probes:,.2f} with the"
        " probes.",
        f"PolicyBench sent the two probes from {probe_opus['started_utc'][11:19]} to"
        f" {probe_opus['ended_utc'][11:19]} (Claude Opus 5.5 at high) and from"
        f" {probe_fable['started_utc'][11:19]} to {probe_fable['ended_utc'][11:19]}"
        " (Claude Fable 5.2 at medium).",
        "the option, the scripts, the data and the note were first committed in"
        " `921a7886`",
    ):
        assert sentence in record_part, sentence
    assert re.search(r"sha256 `[0-9a-f]{64}`", record_part)
    assert "\u2014" not in text and "\u2013" not in text


def test_doc_style():
    text = DOC.read_text()
    assert "\u2014" not in text  # no em dashes
    assert "\u2013" not in text
    # Board display names only: no model ids outside code.
    prose = _doc_without_code()
    assert not re.search(r"claude-(fable|opus)", prose)


def test_every_number_in_the_doc_is_a_recomputed_figure():
    """No figure in the doc outside code comes from anywhere but the checks
    above: strip model names, the release tag and the title's month, then every
    remaining number must appear in a recomputed table line or sentence, or be
    one of the definitions' constants (the $1 and 1% tolerances, the 0.1
    rounding note, the 95% interval's percentiles, the comparison numbers)."""
    text = _doc_without_code()
    text = text.replace(f"release {SUMMARY['release']}", "release")
    for name in ("Claude Fable 5.2", "Claude Opus 5.5", "GPT-6.1 Sol"):
        text = text.replace(name, "")
    text = text.replace("(November 2026)", "")
    allowed = (
        set(
            NUMBER.findall(
                " ".join(
                    [
                        *_expected_lines(),
                        *_expected_prose(),
                        *_second_request_sentences(),
                    ]
                )
            )
        )
        | {"1", "0.1", "2.5", "97.5", "95"}
        | {str(n) for n in range(1, len(COMPARISON_LABELS) + 1)}
    )
    found = set(NUMBER.findall(text))
    assert found <= allowed, sorted(found - allowed)
    # Each recomputed figure-bearing line or sentence is present (above), so
    # every figure the checks produce is in the doc as well.
