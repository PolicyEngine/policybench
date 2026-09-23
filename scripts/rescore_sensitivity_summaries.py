"""Rescore the Claude thinking-sensitivity summaries against the frozen snapshot.

The sensitivity runs' predictions never change; their scores do whenever the
frozen board's scored reference changes (regenerated references, new exclusions)
or its roster changes (the would-rank). This recomputes every pinned number in
``sensitivity/data/claude-fable-5-1-thinking.json`` and
``sensitivity/data/claude-thinking-2026-08.json`` the way
``tests/test_sensitivity_evidence.py`` checks them, after
``scripts/sensitivity_by_variable.py`` has regenerated the per-program assets:

    PYTHONPATH=. python scripts/sensitivity_by_variable.py
    PYTHONPATH=. python scripts/rescore_sensitivity_summaries.py \
        --release dashboard-data-YYYYMMDD

It rewrites the board and sensitivity blocks, the would-rank, the exact delta,
the release, the by-variable asset pins and the scored-universe sentence, and
prints the numbers the prose (sensitivity doc, servingSensitivity.ts, notes)
must carry.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import pandas as pd

from policybench.reference_exclusions import (
    load_reference_exclusions,
    scored_reference_for,
)
from policybench.scorer_vectors import canonical_filtered_scores
from policybench.snapshot_payload import read_run_payload
from policybench.spec import output_group_id

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "sensitivity" / "data"
RUN_DIR = (
    ROOT
    / "paper/snapshot/20260501/runs"
    / "us_full_run_20260612_policyengine_4_16_1_populace"
)
FABLE51 = DATA / "claude-fable-5-1-thinking.json"
AUGUST = DATA / "claude-thinking-2026-08.json"
NUMBER_WORDS = {11: "eleven", 55: "fifty-five", 66: "sixty-six"}


def pin(path: Path) -> dict:
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def would_rank(exact: float, rows: list[dict]) -> int:
    """Match app/src/lib/wouldRank.ts: 1 + rows with strictly higher exact."""
    return 1 + sum(
        (row["exact"] if row.get("exact") is not None else 0) > exact for row in rows
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release", required=True)
    args = parser.parse_args()

    payload = read_run_payload(RUN_DIR)
    rows = payload["modelStats"]
    board_by_model = {row["model"]: row for row in rows}
    reference, _ = scored_reference_for(RUN_DIR / "reference_outputs.csv")
    n_excluded = len(load_reference_exclusions(RUN_DIR / "reference_exclusions.json"))
    n_scored = len(reference)
    weights_by_group: dict[str, float] = {}
    for variable, weight in payload["globalWeights"]["household"].items():
        group = output_group_id(variable)
        weights_by_group[group] = weights_by_group.get(group, 0.0) + weight
    excluded_words = NUMBER_WORDS.get(n_excluded, f"{n_excluded:,}")
    universe = (
        f"the frozen {len(rows)}-model board's reference outputs and household "
        "output-group weights (paper/snapshot/20260501), with the "
        f"{excluded_words} outputs listed in the run's reference_exclusions.json "
        f"removed from scoring as they are for every board row ({n_scored:,} scored "
        "outputs)"
    )

    def rescore(block: dict, stem: str) -> None:
        with gzip.open(DATA / f"{stem}-predictions.csv.gz") as fileobj:
            predictions = pd.read_csv(
                fileobj, usecols=["model", "scenario_id", "variable", "prediction"]
            )
        model_id = block["sensitivity_model_id"]
        assert set(predictions["model"]) == {model_id}, model_id
        for field, key in (
            ("exact", "exact"),
            ("within1pct", "within1pct"),
            ("continuous", "score"),
        ):
            scores, _ = canonical_filtered_scores(
                reference,
                predictions,
                weights_by_group,
                set(weights_by_group),
                "all",
                field,
            )
            block["sensitivity"][key] = round(float(scores[model_id]), 3)
        block["sensitivity"]["would_rank"] = would_rank(
            block["sensitivity"]["exact"], rows
        )
        board = board_by_model[block["model"]]
        for key in ("exact", "within1pct", "score"):
            block["board"][key] = round(float(board[key]), 3)
        block["board"]["n"] = int(board["n"])
        block["board"]["n_parsed"] = int(board["nParsed"])
        block["delta_exact"] = round(
            block["sensitivity"]["exact"] - block["board"]["exact"], 3
        )
        by_variable = f"{stem}-by-variable.csv.gz"
        block["assets"][by_variable] = pin(DATA / by_variable)
        board_rank = would_rank(float(board["exact"]), rows)
        sensitivity = block["sensitivity"]
        print(
            f"{block['model']:18s} board {block['board']['exact']:.3f} (#{board_rank}) "
            f"auto {sensitivity['exact']:.3f} "
            f"(would rank #{sensitivity['would_rank']}) "
            f"delta {block['delta_exact']:+.3f}"
        )

    fable51 = json.loads(FABLE51.read_text())
    rescore(fable51, "sensitivity-claude-fable-5-1-thinking")
    fable51["release"] = args.release
    fable51["scored_against"] = (
        universe
        + "; exact, within-1% and the bounded score all on that universe. The fold "
        "used results/local/fable51/predictions32.csv as the incumbent base"
    )
    FABLE51.write_text(json.dumps(fable51, indent=2) + "\n")

    august = json.loads(AUGUST.read_text())
    for block in august["runs"].values():
        stem = next(
            name for name in block["assets"] if name.endswith("-predictions.csv.gz")
        ).removesuffix("-predictions.csv.gz")
        rescore(block, stem)
    august["release"] = args.release
    august["scored_against"] = (
        universe + "; per-variable rates likewise on the scored outputs"
    )
    AUGUST.write_text(json.dumps(august, indent=2) + "\n")
    print(f"scored outputs: {n_scored:,}; exclusions: {n_excluded}; rows: {len(rows)}")


if __name__ == "__main__":
    main()
