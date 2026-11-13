"""Which scored cells the car-loan reading moves, who matches each reading, and
the board under three treatments. No engine run: reads compute_outputs.py's
verification/computed.csv and the frozen snapshot.

Scoring follows the board's export path, policybench.full_run_export.export_country:
the canonical-output filter (_filter_to_canonical_outputs), split_reference on
the snapshot's exclusion record, then the headline weighted_exact of
analysis.weighted_hit_rate_scores_by_model, with market income from the
scenarios' total_income and the country from _country_from_scenarios, as
analysis.analyze_no_tools does. A per-row hit is
analysis.row_hit_scores(variable, reference, prediction)["exact"]. A cell moves
when paper_results.moves_beyond_tolerance(variable, base, alternative) holds:
more than $1 for an amount, any change for a 0/1 flag.

The three scoreboards (share of answers right x 100, ranked, ties sharing the
best rank):
  a  the release as scored: every scored output against its reference;
  b  the scored cells that move removed for every model;
  c  the scored cells that move scored against the alternative value.
The script stops with an error, before it writes the scoreboards, if a scored
reference is not reproduced to the cent, if the baseline differs from the
2.60.0 build's computed values, or if (a) differs from the frozen board.

Usage, from the repository root with the root on PYTHONPATH:
  python reference_audit/2026-11-11-car-loan-interest/scripts/score.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AUDIT = HERE.parent
OUT = AUDIT / "verification"
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
BUILD_COMPUTED = (
    ROOT / "reference_audit/2026-10-22-engine-upgrade/reference-build/computed.csv"
)
APP_LABELS = ROOT / "app/src/modelMeta.ts"
COLUMNS = ["model", "scenario_id", "variable", "prediction"]
CENT = 0.005
BOARD_TOL = 1e-9
SHARE_DECIMALS = 3
TAX_OUTPUTS = (
    "federal_income_tax_before_refundable_credits",
    "federal_refundable_credits",
    "state_income_tax_before_refundable_credits",
    "state_refundable_credits",
    "local_income_tax",
)
BOARDS = {
    "a": "the release as scored",
    "b": "the scored cells that move removed for every model",
    "c": "the scored cells that move scored against the alternative value",
}


def board_labels() -> dict[str, str]:
    """The dashboard's display names (app/src/modelMeta.ts MODEL_LABELS)."""
    text = APP_LABELS.read_text()
    block = text.split("export const MODEL_LABELS", 1)[1].split("};", 1)[0]
    return dict(re.findall(r'^\s*"?([\w.\-]+)"?:\s*"([^"]+)",', block, re.M))


def ranks(series):
    """Rank 1 = highest share; ties share the best rank."""
    return series.rank(ascending=False, method="min").astype(int)


def headline(ground_truth, predictions, market_income, country):
    from policybench.analysis import weighted_hit_rate_scores_by_model

    table = weighted_hit_rate_scores_by_model(
        ground_truth, predictions, market_income, country=country
    )
    return table.set_index("model")["weighted_exact"] * 100


def markdown(frame, columns, formats) -> str:
    lines = [
        "| " + " | ".join(columns.values()) + " |",
        "|"
        + "|".join("---" if c in ("model", "display_name") else "---:" for c in columns)
        + "|",
    ]
    for _, row in frame.iterrows():
        cells = [formats.get(c, "{}").format(row[c]) for c in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    sys.path.insert(0, str(ROOT))
    import pandas as pd

    from policybench.analysis import _country_from_scenarios, row_hit_scores
    from policybench.full_run_export import _filter_to_canonical_outputs
    from policybench.paper_results import moves_beyond_tolerance
    from policybench.reference_exclusions import (
        exclusions_path_for,
        load_reference_exclusions,
        split_reference,
    )
    from policybench.snapshot_payload import read_run_payload

    OUT.mkdir(exist_ok=True)
    log = []

    def say(line=""):
        print(line)
        log.append(line)

    reference_path = RUN / "reference_outputs.csv"
    reference = pd.read_csv(reference_path)
    scenarios = pd.read_csv(RUN / "scenarios.csv")
    country = str(scenarios["country"].dropna().iloc[0]).lower()
    exclusions = load_reference_exclusions(exclusions_path_for(reference_path))
    excluded_keys = {(e["scenario_id"], e["variable"]) for e in exclusions}
    computed = pd.read_csv(OUT / "computed.csv")
    labels = board_labels()

    # ---- Baseline reproduction ---------------------------------------------
    merged = reference.merge(
        computed, on=["scenario_id", "variable"], how="outer", indicator=True
    )
    if not (merged["_merge"] == "both").all():
        raise SystemExit(
            "computed.csv and the references differ in their cells: "
            f"{merged['_merge'].value_counts().to_dict()}"
        )
    merged["excluded"] = [
        (s, v) in excluded_keys
        for s, v in zip(merged["scenario_id"], merged["variable"])
    ]
    merged["cent"] = (merged["value"] - merged["base"]).abs() < CENT
    say("BASELINE: |engine baseline - reference| < $0.005")
    say(f"  cells: {len(merged)}; reproduced to the cent: {int(merged['cent'].sum())}")
    for flag, group in merged.groupby("excluded"):
        say(
            f"  {'excluded' if flag else 'scored'}: "
            f"{int(group['cent'].sum())} of {len(group)}"
        )
    misses = merged[~merged["cent"]]
    misses[["scenario_id", "variable", "value", "base", "excluded"]].rename(
        columns={"value": "reference", "base": "engine_baseline"}
    ).to_csv(OUT / "baseline_not_reproduced.csv", index=False)
    if (~misses["excluded"]).any():
        raise SystemExit(
            "the engine baseline does not reproduce every scored reference"
        )
    build = pd.read_csv(BUILD_COMPUTED)
    against_build = merged.merge(
        build[["scenario_id", "variable", "recomputed"]],
        on=["scenario_id", "variable"],
        how="left",
    )
    build_gap = float((against_build["base"] - against_build["recomputed"]).abs().max())
    say(
        "  baseline vs the 2.60.0 build's computed.csv: "
        f"{against_build['recomputed'].notna().sum()} cells, "
        f"max |difference| = {build_gap:.2e}"
    )
    if against_build["recomputed"].isna().any() or build_gap != 0:
        raise SystemExit(
            "the engine baseline differs from the 2.60.0 build's computed values"
        )

    # ---- Cells that move ---------------------------------------------------
    merged["moved"] = [
        moves_beyond_tolerance(v, b, a)
        for v, b, a in zip(merged["variable"], merged["base"], merged["alt"])
    ]
    merged["change"] = merged["alt"] - merged["base"]
    merged["any_change"] = merged["change"].abs() > 1e-9
    stated = {}
    for _, srow in scenarios.iterrows():
        data = json.loads(srow["scenario_json"])
        if "auto_loan_interest" in data.get("household_inputs", {}):
            stated[srow["scenario_id"]] = float(
                data["household_inputs"]["auto_loan_interest"]
            )
    filing = dict(zip(scenarios["scenario_id"], scenarios["filing_status"]))
    moved = merged[merged["moved"]].copy()
    moved["filing_status"] = moved["scenario_id"].map(filing)
    moved["stated_auto_loan_interest"] = moved["scenario_id"].map(stated)
    moved["scored"] = ~moved["excluded"]
    moved = moved.sort_values(["scenario_id", "variable"]).reset_index(drop=True)
    say("")
    say(
        "MOVED: cells that move beyond the exact-match tolerance "
        "(baseline vs alternative)"
    )
    say(
        f"  moved: {len(moved)} (scored {int(moved['scored'].sum())}, "
        f"excluded {int(moved['excluded'].sum())})"
    )
    small = merged[merged["any_change"] & ~merged["moved"]]
    small[["scenario_id", "variable", "excluded", "base", "alt", "change"]].rename(
        columns={"base": "engine_baseline", "alt": "alternative"}
    ).to_csv(OUT / "changes_within_tolerance.csv", index=False)
    say(f"  cells that change but stay within tolerance: {len(small)}")
    positive = sorted(s for s, v in stated.items() if v > 0)
    nonpositive = sorted(s for s, v in stated.items() if v <= 0)
    say(
        f"  households stating auto loan interest > 0: {len(positive)}; "
        f"<= 0: {nonpositive}"
    )

    # Households that state auto loan interest, with the engine's intermediate values.
    traces = json.loads((OUT / "traces.json").read_text())
    trace = {(t["scenario_id"], t["kind"]): t for t in traces}
    rows = []
    for sid in sorted(stated):
        cells = merged[merged["scenario_id"] == sid]
        rows.append(
            {
                "scenario_id": sid,
                "state": cells["state"].iloc[0],
                "filing_status": filing[sid],
                "stated_auto_loan_interest": stated[sid],
                "deduction_alternative": sum(
                    trace[(sid, "alt")]["auto_loan_interest_deduction"]
                ),
                "magi": sum(
                    trace[(sid, "base")]["agi_plus_section_911_931_933_exclusions"]
                ),
                "taxable_income_baseline": sum(trace[(sid, "base")]["taxable_income"]),
                "taxable_income_alternative": sum(
                    trace[(sid, "alt")]["taxable_income"]
                ),
                "outputs": len(cells),
                "moved": int(cells["moved"].sum()),
                "moved_scored": int((cells["moved"] & ~cells["excluded"]).sum()),
                "moved_outputs": ";".join(cells.loc[cells["moved"], "variable"]),
            }
        )
    households = pd.DataFrame(rows)
    households.to_csv(OUT / "households.csv", index=False)

    # ---- Predictions -------------------------------------------------------
    predictions = pd.read_csv(
        RUN / "predictions.csv.gz", usecols=COLUMNS, low_memory=False
    )
    if predictions.duplicated(["model", "scenario_id", "variable"]).any():
        raise SystemExit("the snapshot's predictions list a cell twice")
    ground_truth = _filter_to_canonical_outputs(reference, country, None)
    predictions = _filter_to_canonical_outputs(predictions, country, None)
    scored, excluded = split_reference(ground_truth, exclusions)
    models = sorted(predictions["model"].unique())
    say("")
    say(f"predictions: {len(models)} models, {len(predictions):,} rows")
    say(f"references: {len(scored):,} scored, {len(excluded):,} excluded")

    # ---- Who matches which reading -----------------------------------------
    moved_scored = moved[moved["scored"]]
    pred_index = predictions.set_index(["model", "scenario_id", "variable"])[
        "prediction"
    ]
    match_rows = []
    for _, cell in moved_scored.iterrows():
        for model in models:
            pred = pred_index.get((model, cell["scenario_id"], cell["variable"]))
            pred = None if pred is None or pd.isna(pred) else float(pred)
            match_rows.append(
                {
                    "scenario_id": cell["scenario_id"],
                    "variable": cell["variable"],
                    "model": model,
                    "matches_reference": bool(
                        row_hit_scores(cell["variable"], cell["value"], pred)["exact"]
                    ),
                    "matches_alternative": bool(
                        row_hit_scores(cell["variable"], cell["alt"], pred)["exact"]
                    ),
                }
            )
    matches = pd.DataFrame(match_rows)
    say("")
    say(
        "MATCHES: per moved scored cell, models matching the reference / "
        "the alternative"
    )
    per_cell = {}
    for (sid, var), group in matches.groupby(["scenario_id", "variable"], sort=True):
        ref_models = group.loc[group["matches_reference"], "model"].tolist()
        alt_models = group.loc[group["matches_alternative"], "model"].tolist()
        neither = int(
            (~group["matches_reference"] & ~group["matches_alternative"]).sum()
        )
        per_cell[(sid, var)] = (len(ref_models), len(alt_models))
        say(
            f"  {sid} {var}: match reference {len(ref_models)}, "
            f"match alternative {len(alt_models)}, neither {neither}"
        )
        say(f"    reference: {', '.join(ref_models) or '-'}")
        say(f"    alternative: {', '.join(alt_models) or '-'}")
    moved["models_matching_reference"] = [
        per_cell.get((s, v), (None, None))[0]
        for s, v in zip(moved["scenario_id"], moved["variable"])
    ]
    moved["models_matching_alternative"] = [
        per_cell.get((s, v), (None, None))[1]
        for s, v in zip(moved["scenario_id"], moved["variable"])
    ]
    moved_cols = {
        "scenario_id": "scenario_id",
        "state": "state",
        "filing_status": "filing_status",
        "stated_auto_loan_interest": "stated_auto_loan_interest",
        "variable": "variable",
        "value": "reference",
        "base": "engine_baseline",
        "alt": "alternative",
        "change": "change",
        "scored": "scored",
        "models_matching_reference": "models_matching_reference",
        "models_matching_alternative": "models_matching_alternative",
    }
    moved_table = moved[list(moved_cols)].rename(columns=moved_cols)
    moved_table["models_matching_reference"] = moved_table[
        "models_matching_reference"
    ].astype("Int64")
    moved_table["models_matching_alternative"] = moved_table[
        "models_matching_alternative"
    ].astype("Int64")
    moved_table.to_csv(OUT / "moved_cells.csv", index=False)
    with pd.option_context("display.width", 250, "display.max_columns", 20):
        say(moved_table.to_string(index=False))

    totals = (
        matches.assign(
            alternative_only=matches["matches_alternative"]
            & ~matches["matches_reference"],
            reference_only=matches["matches_reference"]
            & ~matches["matches_alternative"],
        )
        .groupby("model")[
            [
                "matches_reference",
                "matches_alternative",
                "reference_only",
                "alternative_only",
            ]
        ]
        .sum()
        .astype(int)
    )

    # ---- Three scoreboards -------------------------------------------------
    market_income = dict(
        zip(
            scenarios["scenario_id"].astype(str),
            pd.to_numeric(scenarios["total_income"], errors="coerce").fillna(0.0),
        )
    )
    scenario_country = _country_from_scenarios(scenarios)
    moved_keys = set(zip(moved_scored["scenario_id"], moved_scored["variable"]))
    in_moved = pd.Series(
        [
            (s, v) in moved_keys
            for s, v in zip(scored["scenario_id"], scored["variable"])
        ],
        index=scored.index,
    )
    if int(in_moved.sum()) != len(moved_keys):
        raise SystemExit("a moved scored cell is missing from the scored references")
    board_b = scored.loc[~in_moved].reset_index(drop=True)
    alt_value = {
        (s, v): a
        for s, v, a in zip(
            moved_scored["scenario_id"], moved_scored["variable"], moved_scored["alt"]
        )
    }
    board_c = scored.copy()
    board_c["value"] = [
        alt_value.get((s, v), x)
        for s, v, x in zip(scored["scenario_id"], scored["variable"], scored["value"])
    ]
    board = pd.DataFrame(
        {
            "share_a": headline(scored, predictions, market_income, scenario_country),
            "share_b": headline(board_b, predictions, market_income, scenario_country),
            "share_c": headline(board_c, predictions, market_income, scenario_country),
        }
    )
    for key in BOARDS:
        board[f"rank_{key}"] = ranks(board[f"share_{key}"])

    # (a) must be the frozen board, as the paper and the tests read it.
    payload = read_run_payload(RUN)
    frozen = pd.Series(
        {
            row["model"]: row["exact"]
            for row in payload["modelStats"]
            if row["condition"] == "no_tools"
        }
    )
    summary = (
        pd.read_csv(RUN / "analysis/summary_by_model.csv").set_index("model")[
            "weighted_exact"
        ]
        * 100
    )
    if set(frozen.index) != set(board.index) or set(summary.index) != set(board.index):
        raise SystemExit(
            "the frozen board and the recomputed board list different models"
        )
    gap_payload = float((board["share_a"] - frozen.reindex(board.index)).abs().max())
    gap_summary = float((board["share_a"] - summary.reindex(board.index)).abs().max())
    say("")
    say(
        f"SCOREBOARDS (share of answers right x 100). a = {len(scored)} scored cells; "
        f"b = {len(board_b)}; c = {len(board_c)}"
    )
    say(
        "  (a) vs the frozen board (data.json.gz modelStats exact): "
        f"max |difference| = {gap_payload:.2e} over {len(frozen)} models"
    )
    say(
        "  (a) vs analysis/summary_by_model.csv weighted_exact x 100: "
        f"max |difference| = {gap_summary:.2e}"
    )
    if gap_payload > BOARD_TOL or gap_summary > BOARD_TOL:
        raise SystemExit("scoreboard (a) is not the frozen board")

    board = board.join(totals).reset_index().rename(columns={"index": "model"})
    board["display_name"] = board["model"].map(labels).fillna(board["model"])
    board = board.sort_values(["rank_a", "model"]).reset_index(drop=True)
    board[
        [
            "model",
            "display_name",
            "share_a",
            "rank_a",
            "share_b",
            "rank_b",
            "share_c",
            "rank_c",
        ]
    ].to_csv(OUT / "scoreboards.csv", index=False)
    board[
        [
            "model",
            "display_name",
            "matches_reference",
            "matches_alternative",
            "reference_only",
            "alternative_only",
        ]
    ].to_csv(OUT / "model_matches.csv", index=False)
    fmt = {f"share_{k}": "{:.3f}" for k in BOARDS}
    with pd.option_context(
        "display.width",
        250,
        "display.max_rows",
        100,
        "display.float_format",
        "{:.3f}".format,
    ):
        say(
            board[
                ["model", "share_a", "rank_a", "share_b", "rank_b", "share_c", "rank_c"]
            ].to_string(index=False)
        )
    (OUT / "scoreboards.md").write_text(
        "# Scoreboards (a), (b) and (c), all models\n\n"
        "Share of answers right (percent, weighted as the board weights them) "
        "and rank. (a) the release as scored; "
        f"(b) the {len(moved_keys)} scored cells that move removed for every "
        "model; (c) those cells scored against the alternative value. "
        "Generated by `scripts/score.py`.\n\n"
        + markdown(
            board,
            {
                "display_name": "Model",
                "share_a": "(a) share",
                "rank_a": "(a) rank",
                "share_b": "(b) share",
                "rank_b": "(b) rank",
                "share_c": "(c) share",
                "rank_c": "(c) rank",
            },
            fmt,
        )
    )

    # ---- Headline facts ----------------------------------------------------
    facts = {
        "question": (
            "How would the board change if each household's stated auto loan interest "
            "counted as qualified passenger vehicle loan interest?"
        ),
        "engine": json.loads((OUT / "engine_run.json").read_text())["engine"],
        "scored_outputs_per_model": len(scored),
        "excluded_outputs": len(excluded),
        "households_stating_auto_loan_interest_above_zero": len(positive),
        "cells_moved": len(moved),
        "scored_cells_moved": int(moved["scored"].sum()),
        "excluded_cells_moved": int(moved["excluded"].sum()),
        "scoreboards": BOARDS,
        "share": (
            "percent of answers right, weighted as the board weights them, "
            f"rounded to {SHARE_DECIMALS} decimals"
        ),
        "models": {
            row["model"]: {
                key: {
                    "share": round(float(row[f"share_{key}"]), SHARE_DECIMALS),
                    "rank": int(row[f"rank_{key}"]),
                }
                for key in BOARDS
            }
            for _, row in board.iterrows()
        },
    }
    # One line per model keeps the file short.
    head = json.dumps({k: v for k, v in facts.items() if k != "models"}, indent=1)
    rows = [f"  {json.dumps(m)}: {json.dumps(v)}" for m, v in facts["models"].items()]
    text = head[:-2] + ',\n "models": {\n' + ",\n".join(rows) + "\n }\n}\n"
    if json.loads(text) != facts:
        raise SystemExit("headline.json does not serialize the facts")
    (OUT / "headline.json").write_text(text)
    (OUT / "summary.txt").write_text("\n".join(log) + "\n")


if __name__ == "__main__":
    main()
