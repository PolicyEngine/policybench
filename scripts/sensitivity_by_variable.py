"""Per-program rates for a sensitivity run, scored like the board.

Each thinking sensitivity run ships a ``*-by-variable.csv.gz`` beside its
predictions: one row per output group with the run's unweighted hit rates,
the same rows the dashboard exporter writes into ``heatmap``. This script
recomputes them against the scored reference (the frozen CSV minus
``reference_exclusions.json``) so the tables in
``sensitivity/claude-thinking-2026-08.md`` describe the same 1,973 outputs
the board scores, and prints those tables.

    uv run python scripts/sensitivity_by_variable.py            # regenerate all
    uv run python scripts/sensitivity_by_variable.py --tables   # print doc tables
"""

from __future__ import annotations

import argparse
import gzip
from pathlib import Path

import pandas as pd

from policybench.analysis import analyze_no_tools
from policybench.reference_exclusions import scored_reference_for
from policybench.snapshot_payload import read_run_payload

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "sensitivity" / "data"
RUN_DIR = (
    ROOT
    / "paper/snapshot/20260501/runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace"
)

# sensitivity model id -> (asset stem, board model id)
RUNS = {
    "claude-fable-5-thinking": (
        "sensitivity-claude-fable-5-thinking",
        "claude-fable-5",
    ),
    "claude-opus-5-thinking": ("sensitivity-claude-opus-5-thinking", "claude-opus-5"),
    "claude-sonnet-5-thinking": (
        "sensitivity-claude-sonnet-5-thinking",
        "claude-sonnet-5",
    ),
    "claude-fable-5.1-thinking": (
        "sensitivity-claude-fable-5-1-thinking",
        "claude-fable-5.1",
    ),
}

ASSET_COLUMNS = [
    "model",
    "variable",
    "n",
    "nParsed",
    "exact",
    "within1pct",
    "within5pct",
    "within10pct",
    "score",
    "thresholdScore",
    "mae",
    "coverage",
]


def load_predictions(path: Path) -> pd.DataFrame:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as source:
        return pd.read_csv(
            source, usecols=["model", "scenario_id", "variable", "prediction"]
        )


def by_variable_rates(
    predictions: pd.DataFrame,
    reference: pd.DataFrame,
    scenarios: pd.DataFrame,
) -> pd.DataFrame:
    """One row per output group with the run's rates, as the exporter's heatmap
    reports them (percentages; ``n`` counts the scored rows in the group)."""
    metrics = analyze_no_tools(reference, predictions, scenarios=scenarios)["metrics"]
    rows = []
    for _, row in metrics.sort_values(["variable", "model"]).iterrows():
        rows.append(
            {
                "model": row["model"],
                "variable": row["variable"],
                "n": int(row["n"]),
                "nParsed": int(row["n_parsed"]),
                "exact": float(row["exact"] * 100),
                "within1pct": float(row["within_1pct"] * 100),
                "within5pct": float(row["within_5pct"] * 100),
                "within10pct": float(row["within_10pct"] * 100),
                "score": float(row["score"] * 100),
                "thresholdScore": float(row["threshold_score"] * 100),
                "mae": float(row["mae"]),
                "coverage": float(row["coverage"] * 100),
            }
        )
    return pd.DataFrame(rows, columns=ASSET_COLUMNS)


def scored_inputs(run_dir: Path = RUN_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    reference, _ = scored_reference_for(run_dir / "reference_outputs.csv")
    scenarios = pd.read_csv(run_dir / "scenarios.csv")
    return reference, scenarios


def write_asset(frame: pd.DataFrame, path: Path) -> None:
    with gzip.GzipFile(path, "wb", mtime=0) as sink:
        sink.write(frame.to_csv(index=False).encode("utf-8"))


def doc_table(
    asset: pd.DataFrame,
    board_model: str,
    payload: dict,
    board_label: str,
    auto_label: str,
) -> str:
    """Markdown rows: board rate (frozen heatmap), sensitivity rate, delta;
    sorted by delta descending, then by variable."""
    board = {
        row["variable"]: row["exact"]
        for row in payload["heatmap"]
        if row["model"] == board_model
    }
    lines = [f"| program | {board_label} | {auto_label} | delta |", "|---|---|---|---|"]
    rows = []
    for _, row in asset.iterrows():
        b = round(board[row["variable"]], 1)
        a = round(float(row["exact"]), 1)
        rows.append((row["variable"], b, a, round(a - b, 1)))
    for variable, b, a, delta in sorted(rows, key=lambda r: (-r[3], r[0])):
        lines.append(f"| {variable} | {b:.1f} | {a:.1f} | {delta:+.1f} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tables", action="store_true", help="print doc tables only")
    args = parser.parse_args()
    reference, scenarios = scored_inputs()
    payload = read_run_payload(RUN_DIR)
    for model, (stem, board_model) in RUNS.items():
        predictions = load_predictions(DATA / f"{stem}-predictions.csv.gz")
        assert set(predictions["model"]) == {model}, model
        frame = by_variable_rates(predictions, reference, scenarios)
        if not args.tables:
            write_asset(frame, DATA / f"{stem}-by-variable.csv.gz")
            print(f"wrote {stem}-by-variable.csv.gz ({len(frame)} groups)")
        if board_model in ("claude-fable-5", "claude-fable-5.1"):
            labels = (
                ("board", "auto")
                if board_model == "claude-fable-5"
                else ("board (JSON)", "auto (tool declared)")
            )
            print(f"\n## {board_model}\n")
            print(doc_table(frame, board_model, payload, *labels))


if __name__ == "__main__":
    main()
