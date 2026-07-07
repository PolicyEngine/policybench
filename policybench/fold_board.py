"""Fold new model prediction sets into an existing board for staging.

Generalizes the one-off fold scripts used for the v1.x releases: takes the
current board's combined predictions plus one predictions CSV per new model,
enforces the row-count/duplicate gates that kept partial runs off the board,
writes a scoring directory, and runs the standard country export so the
staged ``summary_by_model.csv`` is ready to review.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


class FoldError(ValueError):
    pass


def _rows_per_model(base: pd.DataFrame) -> int:
    counts = base.groupby("model").size()
    if counts.nunique() != 1:
        raise FoldError(
            f"base board has unequal per-model row counts: {counts.to_dict()}"
        )
    return int(counts.iloc[0])


def fold_board(
    base_predictions: Path,
    additions: list[Path],
    scoring_source: Path,
    out_dir: Path,
    export: bool = True,
) -> dict:
    base = pd.read_csv(base_predictions)
    expected_rows = _rows_per_model(base)

    out_dir = Path(out_dir)
    by_model_dir = out_dir / "by_model"
    by_model_dir.mkdir(parents=True, exist_ok=True)

    frames = [base]
    folded: list[str] = []
    excluded: dict[str, str] = {}
    for path in additions:
        frame = pd.read_csv(path)
        models = frame["model"].unique()
        if len(models) != 1:
            excluded[str(path)] = f"expected one model, found {list(models)}"
            continue
        name = models[0]
        dupes = int(frame.duplicated(["scenario_id", "variable"]).sum())
        problems = []
        if len(frame) != expected_rows:
            problems.append(f"{len(frame)} rows (need {expected_rows})")
        if dupes:
            problems.append(f"{dupes} duplicate scenario/variable rows")
        if name in set(base["model"]):
            problems.append("model already on the base board")
        if problems:
            excluded[name] = "; ".join(problems)
            continue
        frame.to_csv(by_model_dir / f"{name}.csv", index=False)
        frames.append(frame[base.columns])
        folded.append(name)

    combined = pd.concat(frames, ignore_index=True)
    us_dir = out_dir / "us"
    us_dir.mkdir(parents=True, exist_ok=True)
    combined.to_csv(us_dir / "predictions.csv", index=False)
    for name in ("reference_outputs.csv", "scenarios.csv", "scenarios.csv.meta.json"):
        source = Path(scoring_source) / name
        if source.exists():
            (us_dir / name).write_bytes(source.read_bytes())

    summary = None
    if export:
        from policybench.full_run_export import export_country

        export_country(us_dir)
        summary_path = us_dir / "analysis" / "summary_by_model.csv"
        if summary_path.exists():
            summary = pd.read_csv(summary_path)

    return {
        "folded": folded,
        "excluded": excluded,
        "models": int(combined["model"].nunique()),
        "rows": len(combined),
        "out_dir": str(out_dir),
        "summary": summary,
    }
