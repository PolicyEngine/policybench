"""Repair individual prediction rows that still fail the output contract."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from policybench.chunked_eval import model_requires_serial_execution
from policybench.config import MODELS
from policybench.eval_no_tools import is_infrastructure_error_text, run_single_no_tools
from policybench.reparse_predictions import reparse_predictions_frame
from policybench.scenarios import load_scenarios_from_manifest

KEY_COLUMNS = ["model", "scenario_id", "variable"]


@dataclass(frozen=True)
class RowRepairPreparation:
    output_dir: Path
    target_rows: pd.DataFrame
    target_rows_path: Path
    source_predictions_copy: Path
    reparsed_source_predictions: Path
    scenario_manifest: Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_prediction_csv(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _source_predictions_copy_path(output_dir: Path, source_predictions: Path) -> Path:
    if source_predictions.name.endswith(".csv.gz"):
        return output_dir / "source_predictions.csv.gz"
    suffix = source_predictions.suffix or ".csv"
    return output_dir / f"source_predictions{suffix}"


def _nonempty(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _valid_repair_mask(frame: pd.DataFrame, *, require_explanations: bool) -> pd.Series:
    valid = frame["prediction"].notna()
    if require_explanations:
        if "explanation" not in frame.columns:
            return pd.Series(False, index=frame.index)
        valid = valid & frame["explanation"].fillna("").astype(str).str.strip().ne("")
    if "error" in frame.columns:
        valid = valid & ~frame["error"].fillna("").astype(str).map(
            is_infrastructure_error_text
        )
    return valid


def row_repair_targets(
    predictions: pd.DataFrame,
    *,
    require_explanations: bool = True,
) -> pd.DataFrame:
    """Return individual rows still missing a parsed value or explanation."""
    required = set(KEY_COLUMNS) | {"prediction"}
    missing = required - set(predictions.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Prediction file missing columns: {missing_text}")

    needs_repair = predictions["prediction"].isna()
    if require_explanations:
        if "explanation" not in predictions.columns:
            needs_repair = pd.Series(True, index=predictions.index)
        else:
            needs_repair = needs_repair | predictions["explanation"].fillna("").astype(
                str
            ).str.strip().eq("")
    if "error" in predictions.columns:
        needs_repair = needs_repair | predictions["error"].fillna("").astype(str).map(
            is_infrastructure_error_text
        )

    return (
        predictions.loc[needs_repair, KEY_COLUMNS]
        .drop_duplicates()
        .sort_values(KEY_COLUMNS)
        .reset_index(drop=True)
    )


def prepare_row_repair_round(
    *,
    source_predictions: str | Path,
    scenario_manifest: str | Path,
    output_dir: str | Path,
    country: str,
    require_explanations: bool = True,
    models: list[str] | None = None,
    max_rows: int | None = None,
) -> RowRepairPreparation:
    """Reparse source predictions and write row-level repair targets."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_predictions = Path(source_predictions)
    scenario_manifest = Path(scenario_manifest)

    source = _read_prediction_csv(source_predictions)
    reparsed = reparse_predictions_frame(
        source,
        include_explanations=require_explanations,
    )
    targets = row_repair_targets(
        reparsed,
        require_explanations=require_explanations,
    )
    if models is not None:
        targets = targets[targets["model"].isin(models)].copy()
    if max_rows is not None:
        targets = targets.head(max_rows).copy()

    source_copy = _source_predictions_copy_path(output_dir, source_predictions)
    if source_predictions.resolve() != source_copy.resolve():
        source_copy.write_bytes(source_predictions.read_bytes())

    reparsed_source_path = output_dir / "reparsed_source_predictions.csv.gz"
    reparsed.to_csv(reparsed_source_path, index=False)
    target_rows_path = output_dir / "target_rows.csv"
    targets.to_csv(target_rows_path, index=False)

    metadata = {
        "country": country,
        "require_explanations": require_explanations,
        "source_predictions": str(source_predictions),
        "source_predictions_sha256": _sha256(source_predictions),
        "source_predictions_copy": str(source_copy),
        "source_predictions_copy_sha256": _sha256(source_copy),
        "reparsed_source_predictions": str(reparsed_source_path),
        "reparsed_source_predictions_sha256": _sha256(reparsed_source_path),
        "scenario_manifest": str(scenario_manifest),
        "scenario_manifest_sha256": _sha256(scenario_manifest),
        "target_rows": int(len(targets)),
        "target_models": sorted(targets["model"].unique().tolist())
        if not targets.empty
        else [],
        "max_rows": max_rows,
    }
    (output_dir / "row_repair_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return RowRepairPreparation(
        output_dir=output_dir,
        target_rows=targets,
        target_rows_path=target_rows_path,
        source_predictions_copy=source_copy,
        reparsed_source_predictions=reparsed_source_path,
        scenario_manifest=scenario_manifest,
    )


def _repair_result_is_valid(row: dict, *, require_explanations: bool) -> bool:
    if row.get("prediction") is None:
        return False
    if require_explanations and not _nonempty(row.get("explanation")):
        return False
    return not is_infrastructure_error_text(row.get("error"))


def _empty_repair_row(
    *,
    country: str,
    attempt: int,
    model: str,
    scenario_id: str,
    variable: str,
    error: str,
) -> dict:
    return {
        "country": country,
        "attempt": attempt,
        "model": model,
        "scenario_id": scenario_id,
        "variable": variable,
        "prediction": None,
        "explanation": None,
        "raw_response": None,
        "error": error,
        "elapsed_seconds": None,
        "request_started_at": None,
        "request_completed_at": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "reasoning_tokens": None,
        "cached_prompt_tokens": None,
        "provider_reported_cost_usd": None,
        "reconstructed_cost_usd": None,
        "total_cost_usd": None,
        "cost_is_estimated": None,
        "estimated_cost_usd": None,
        "provider_response_id": None,
        "provider_system_fingerprint": None,
        "provider_resolved_model": None,
    }


def repair_prediction_row(
    *,
    country: str,
    scenario,
    model: str,
    variable: str,
    attempts_per_row: int,
    require_explanations: bool = True,
) -> tuple[dict, list[dict]]:
    """Retry one model-scenario-variable row and return best row plus attempts."""
    if model not in MODELS:
        valid = ", ".join(sorted(MODELS))
        raise ValueError(f"Unknown model '{model}'. Valid models: {valid}.")
    if attempts_per_row <= 0:
        raise ValueError("attempts_per_row must be positive.")

    attempts = []
    model_id = MODELS[model]
    for attempt in range(1, attempts_per_row + 1):
        try:
            result = run_single_no_tools(
                scenario,
                variable,
                model_id,
                include_explanations=require_explanations,
            )
            row = {
                "country": country,
                "attempt": attempt,
                "model": model,
                "scenario_id": scenario.id,
                "variable": variable,
                "prediction": result.get("predictions", {}).get(variable),
                "explanation": result.get("explanations", {}).get(variable),
                "raw_response": result.get("raw_response"),
                "error": result.get("error"),
                "elapsed_seconds": result.get("elapsed_seconds"),
                "request_started_at": result.get("request_started_at"),
                "request_completed_at": result.get("request_completed_at"),
                "prompt_tokens": result.get("prompt_tokens"),
                "completion_tokens": result.get("completion_tokens"),
                "total_tokens": result.get("total_tokens"),
                "reasoning_tokens": result.get("reasoning_tokens"),
                "cached_prompt_tokens": result.get("cached_prompt_tokens"),
                "provider_reported_cost_usd": result.get("provider_reported_cost_usd"),
                "reconstructed_cost_usd": result.get("reconstructed_cost_usd"),
                "total_cost_usd": result.get("total_cost_usd"),
                "cost_is_estimated": result.get("cost_is_estimated"),
                "estimated_cost_usd": result.get("estimated_cost_usd"),
                "provider_response_id": result.get("provider_response_id"),
                "provider_system_fingerprint": result.get(
                    "provider_system_fingerprint"
                ),
                "provider_resolved_model": result.get("provider_resolved_model"),
            }
        except Exception as exc:
            row = _empty_repair_row(
                country=country,
                attempt=attempt,
                model=model,
                scenario_id=scenario.id,
                variable=variable,
                error=f"{type(exc).__name__}: {str(exc)[:500]}",
            )
        attempts.append(row)
        if _repair_result_is_valid(row, require_explanations=require_explanations):
            break

    for row in attempts:
        if _repair_result_is_valid(row, require_explanations=require_explanations):
            return row, attempts
    return attempts[-1], attempts


def _append_rows(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    frame = pd.DataFrame(rows)
    frame.to_csv(path, mode="a", index=False, header=not path.exists())


def _completed_repair_keys(
    path: Path,
    *,
    require_explanations: bool,
) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()
    try:
        existing = pd.read_csv(path)
    except (
        OSError,
        UnicodeDecodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ):
        return set()
    if not set(KEY_COLUMNS).issubset(existing.columns) or "prediction" not in existing:
        return set()
    valid = existing[
        _valid_repair_mask(existing, require_explanations=require_explanations)
    ]
    return set(map(tuple, valid[KEY_COLUMNS].astype(str).to_numpy()))


def run_row_repair_models(
    *,
    preparation: RowRepairPreparation,
    country: str,
    attempts_per_row: int = 3,
    parallel: int = 4,
    require_explanations: bool = True,
) -> Path:
    """Run row-level repairs, with resumable attempt and final-row artifacts."""
    if parallel <= 0:
        raise ValueError("parallel must be positive.")

    output_path = preparation.output_dir / "row_repair_predictions.csv"
    attempts_path = preparation.output_dir / "row_repair_attempts.csv"
    if preparation.target_rows.empty:
        columns = list(
            pd.read_csv(preparation.reparsed_source_predictions, nrows=0).columns
        )
        pd.DataFrame(columns=columns).to_csv(output_path, index=False)
        pd.DataFrame().to_csv(attempts_path, index=False)
        return output_path

    completed = _completed_repair_keys(
        output_path,
        require_explanations=require_explanations,
    )
    pending = [
        row._asdict()
        for row in preparation.target_rows.itertuples(index=False)
        if tuple(map(str, row)) not in completed
    ]
    if not pending:
        return output_path

    scenarios = load_scenarios_from_manifest(preparation.scenario_manifest)
    scenario_by_id = {scenario.id: scenario for scenario in scenarios}

    def run_task(task: dict) -> tuple[dict, list[dict]]:
        scenario_id = str(task["scenario_id"])
        if scenario_id not in scenario_by_id:
            raise ValueError(f"Missing scenario '{scenario_id}' in manifest.")
        return repair_prediction_row(
            country=country,
            scenario=scenario_by_id[scenario_id],
            model=str(task["model"]),
            variable=str(task["variable"]),
            attempts_per_row=attempts_per_row,
            require_explanations=require_explanations,
        )

    parallel_tasks = [
        task
        for task in pending
        if not model_requires_serial_execution(str(task["model"]))
    ]
    serial_tasks = [
        task for task in pending if model_requires_serial_execution(str(task["model"]))
    ]
    print(
        f"Row repair: {len(pending):,} pending rows "
        f"({len(parallel_tasks):,} parallel, {len(serial_tasks):,} serial)"
    )

    if parallel_tasks:
        done = 0
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = [executor.submit(run_task, task) for task in parallel_tasks]
            for future in as_completed(futures):
                final, attempts = future.result()
                _append_rows(output_path, [final])
                _append_rows(attempts_path, attempts)
                done += 1
                if done % 50 == 0:
                    print(f"Row repair: completed {done:,}/{len(parallel_tasks):,}")

    for done, task in enumerate(serial_tasks, start=1):
        final, attempts = run_task(task)
        _append_rows(output_path, [final])
        _append_rows(attempts_path, attempts)
        if done % 10 == 0:
            print(f"Row repair: completed serial {done:,}/{len(serial_tasks):,}")

    return output_path


def merge_row_repair_predictions(
    *,
    source_predictions: str | Path,
    repair_predictions: str | Path,
    output_dir: str | Path,
    require_explanations: bool = True,
) -> dict[str, Path]:
    """Replace only rows with valid row-level repairs."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source = reparse_predictions_frame(
        _read_prediction_csv(source_predictions),
        include_explanations=require_explanations,
    )
    repair_path = Path(repair_predictions)
    if repair_path.exists():
        try:
            repair = pd.read_csv(repair_path)
        except pd.errors.EmptyDataError:
            repair = pd.DataFrame(columns=KEY_COLUMNS)
    else:
        repair = pd.DataFrame(columns=KEY_COLUMNS)

    if not repair.empty:
        valid = repair[
            _valid_repair_mask(repair, require_explanations=require_explanations)
        ]
        valid = valid.drop_duplicates(KEY_COLUMNS, keep="first")
    else:
        valid = pd.DataFrame(columns=repair.columns)

    merged = source.copy()
    if not valid.empty:
        valid_by_key = valid.set_index(KEY_COLUMNS, drop=False)
        for index, row in merged.iterrows():
            key = tuple(str(row[column]) for column in KEY_COLUMNS)
            if key not in valid_by_key.index:
                continue
            replacement = valid_by_key.loc[key]
            if isinstance(replacement, pd.DataFrame):
                replacement = replacement.iloc[0]
            for column in valid.columns:
                if column in {"country", "attempt"}:
                    continue
                if column not in merged.columns:
                    merged[column] = pd.NA
                if isinstance(replacement[column], str):
                    merged[column] = merged[column].astype("object")
                merged.at[index, column] = replacement[column]

    accepted_keys = valid[KEY_COLUMNS].drop_duplicates() if not valid.empty else valid
    target_rows = row_repair_targets(
        source,
        require_explanations=require_explanations,
    )
    rejected = target_rows.merge(
        accepted_keys.assign(_accepted=True)
        if not accepted_keys.empty
        else accepted_keys,
        on=KEY_COLUMNS,
        how="left",
    )
    if "_accepted" in rejected.columns:
        rejected = rejected[rejected["_accepted"].isna()].drop(columns=["_accepted"])
    if not rejected.empty:
        rejected = rejected.assign(reason="no valid row-level repair")
    else:
        rejected = pd.DataFrame(columns=KEY_COLUMNS + ["reason"])

    repaired_original_rows = source.merge(accepted_keys, on=KEY_COLUMNS, how="inner")
    accepted_rows = valid.copy()

    sort_columns = [column for column in KEY_COLUMNS if column in merged.columns]
    if sort_columns:
        merged = merged.sort_values(sort_columns).reset_index(drop=True)

    merged_path = output_dir / "merged_predictions.csv.gz"
    accepted_rows_path = output_dir / "accepted_row_repair_rows.csv.gz"
    replaced_originals_path = output_dir / "replaced_original_rows.csv.gz"
    rejected_rows_path = output_dir / "rejected_row_repair_rows.csv"
    merged.to_csv(merged_path, index=False)
    accepted_rows.to_csv(accepted_rows_path, index=False)
    repaired_original_rows.to_csv(replaced_originals_path, index=False)
    rejected.to_csv(rejected_rows_path, index=False)
    return {
        "merged_predictions": merged_path,
        "accepted_row_repair_rows": accepted_rows_path,
        "replaced_original_rows": replaced_originals_path,
        "rejected_row_repair_rows": rejected_rows_path,
    }


def run_row_repair_round(
    *,
    country: str,
    source_predictions: str | Path,
    scenario_manifest: str | Path,
    output_dir: str | Path,
    attempts_per_row: int = 3,
    parallel: int = 4,
    require_explanations: bool = True,
    models: list[str] | None = None,
    max_rows: int | None = None,
    prepare_only: bool = False,
) -> dict[str, Path]:
    """Run the complete row-level repair workflow."""
    preparation = prepare_row_repair_round(
        source_predictions=source_predictions,
        scenario_manifest=scenario_manifest,
        output_dir=output_dir,
        country=country,
        require_explanations=require_explanations,
        models=models,
        max_rows=max_rows,
    )
    outputs = {
        "target_rows": preparation.target_rows_path,
        "source_predictions_copy": preparation.source_predictions_copy,
        "reparsed_source_predictions": preparation.reparsed_source_predictions,
    }
    if prepare_only:
        return outputs
    repair_predictions = run_row_repair_models(
        preparation=preparation,
        country=country,
        attempts_per_row=attempts_per_row,
        parallel=parallel,
        require_explanations=require_explanations,
    )
    outputs["row_repair_predictions"] = repair_predictions
    outputs.update(
        merge_row_repair_predictions(
            source_predictions=preparation.reparsed_source_predictions,
            repair_predictions=repair_predictions,
            output_dir=preparation.output_dir,
            require_explanations=require_explanations,
        )
    )
    return outputs
