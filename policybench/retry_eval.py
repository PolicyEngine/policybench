"""Retry full model-household responses that failed the response contract."""

from __future__ import annotations

import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from policybench.chunked_eval import (
    merge_model_outputs,
    model_requires_serial_execution,
    run_model_chunks,
)
from policybench.config import DEFAULT_PROGRAM_SET
from policybench.eval_no_tools import is_infrastructure_error_text


@dataclass(frozen=True)
class RetryPreparation:
    output_dir: Path
    target_units: pd.DataFrame
    original_failed_rows_path: Path
    scenario_manifest_paths: dict[str, Path]
    source_predictions_copy: Path


def _read_prediction_csv(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    return pd.read_csv(path)


def _nonempty_string_mask(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().ne("")


def _infrastructure_error_mask(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).map(is_infrastructure_error_text)


def response_retry_units(
    predictions: pd.DataFrame,
    *,
    require_explanations: bool = True,
) -> pd.DataFrame:
    """Return model-scenario groups with missing values or retryable errors."""
    required = {"model", "scenario_id", "variable", "prediction"}
    missing = required - set(predictions.columns)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"Prediction file missing columns: {missing_text}")

    row_needs_retry = predictions["prediction"].isna()
    if require_explanations:
        if "explanation" not in predictions.columns:
            row_needs_retry = pd.Series(True, index=predictions.index)
        else:
            row_needs_retry = row_needs_retry | ~_nonempty_string_mask(
                predictions["explanation"]
            )
    if "error" in predictions.columns:
        row_needs_retry = row_needs_retry | _infrastructure_error_mask(
            predictions["error"]
        )

    if not row_needs_retry.any():
        return pd.DataFrame(
            columns=[
                "model",
                "scenario_id",
                "missing_predictions",
                "missing_explanations",
                "infrastructure_error_rows",
                "source_rows",
            ]
        )

    working = predictions.copy()
    working["_missing_prediction"] = working["prediction"].isna()
    if require_explanations:
        if "explanation" not in working.columns:
            working["_missing_explanation"] = True
        else:
            working["_missing_explanation"] = ~_nonempty_string_mask(
                working["explanation"]
            )
    else:
        working["_missing_explanation"] = False
    if "error" in working.columns:
        working["_infrastructure_error"] = _infrastructure_error_mask(working["error"])
    else:
        working["_infrastructure_error"] = False

    retry_keys = working.loc[
        row_needs_retry,
        ["model", "scenario_id"],
    ].drop_duplicates()
    retry_rows = working.merge(retry_keys, on=["model", "scenario_id"], how="inner")
    units = (
        retry_rows.groupby(["model", "scenario_id"], sort=True)
        .agg(
            missing_predictions=("_missing_prediction", "sum"),
            missing_explanations=("_missing_explanation", "sum"),
            infrastructure_error_rows=("_infrastructure_error", "sum"),
            source_rows=("variable", "size"),
        )
        .reset_index()
    )
    for column in [
        "missing_predictions",
        "missing_explanations",
        "infrastructure_error_rows",
        "source_rows",
    ]:
        units[column] = units[column].astype(int)
    return units


def _filter_units(units: pd.DataFrame, models: list[str] | None) -> pd.DataFrame:
    if models is None:
        return units
    return units[units["model"].isin(models)].copy()


def _write_model_scenario_manifests(
    *,
    scenario_manifest: pd.DataFrame,
    target_units: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Path]:
    manifest_dir = output_dir / "scenario_manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    scenario_ids = set(scenario_manifest["scenario_id"].astype(str))
    paths: dict[str, Path] = {}
    for model, units in target_units.groupby("model", sort=True):
        requested_ids = set(units["scenario_id"].astype(str))
        missing = sorted(requested_ids - scenario_ids)
        if missing:
            raise ValueError(
                "Retry target contains scenario ids missing from manifest: "
                + ", ".join(missing[:5])
            )
        subset = scenario_manifest[
            scenario_manifest["scenario_id"].astype(str).isin(requested_ids)
        ].copy()
        path = manifest_dir / f"{model}.csv"
        subset.to_csv(path, index=False)
        paths[str(model)] = path
    return paths


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_retry_round(
    *,
    country: str,
    source_predictions: str | Path,
    scenario_manifest: str | Path,
    output_dir: str | Path,
    require_explanations: bool = True,
    models: list[str] | None = None,
    max_responses: int | None = None,
) -> RetryPreparation:
    """Write manifests and original rows for full-response retries."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_predictions = Path(source_predictions)
    scenario_manifest = Path(scenario_manifest)

    predictions = _read_prediction_csv(source_predictions)
    scenarios = pd.read_csv(scenario_manifest)
    target_units = response_retry_units(
        predictions,
        require_explanations=require_explanations,
    )
    target_units = _filter_units(target_units, models)
    if max_responses is not None:
        target_units = target_units.head(max_responses).copy()
    target_units.insert(0, "country", country)

    target_path = output_dir / "target_units.csv"
    target_units.to_csv(target_path, index=False)

    source_copy = output_dir / source_predictions.name
    if source_predictions.resolve() != source_copy.resolve():
        shutil.copy2(source_predictions, source_copy)

    original_failed_rows = predictions.merge(
        target_units[["model", "scenario_id"]],
        on=["model", "scenario_id"],
        how="inner",
    )
    original_failed_rows_path = output_dir / "original_failed_responses.csv.gz"
    original_failed_rows.to_csv(original_failed_rows_path, index=False)

    manifest_paths = _write_model_scenario_manifests(
        scenario_manifest=scenarios,
        target_units=target_units,
        output_dir=output_dir,
    )

    metadata = {
        "country": country,
        "require_explanations": require_explanations,
        "source_predictions": str(source_predictions),
        "source_predictions_sha256": _sha256(source_predictions),
        "scenario_manifest": str(scenario_manifest),
        "scenario_manifest_sha256": _sha256(scenario_manifest),
        "target_responses": int(len(target_units)),
        "target_models": sorted(target_units["model"].unique().tolist()),
        "max_responses": max_responses,
    }
    (output_dir / "retry_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return RetryPreparation(
        output_dir=output_dir,
        target_units=target_units,
        original_failed_rows_path=original_failed_rows_path,
        scenario_manifest_paths=manifest_paths,
        source_predictions_copy=source_copy,
    )


def _model_output_dir(output_dir: Path, model: str) -> Path:
    return output_dir / "model_runs" / model


def run_retry_models(
    *,
    preparation: RetryPreparation,
    country: str,
    program_set: str = DEFAULT_PROGRAM_SET,
    chunk_size: int = 10,
    parallel: int = 1,
    model_parallel: int = 1,
    chunk_attempts: int = 1,
    include_explanations: bool = True,
) -> Path:
    """Run retry model calls from prepared per-model manifests."""
    if preparation.target_units.empty:
        output_path = preparation.output_dir / "retry_predictions.csv"
        columns = pd.read_csv(preparation.source_predictions_copy, nrows=0).columns
        pd.DataFrame(columns=columns).to_csv(output_path, index=False)
        return output_path

    models = sorted(preparation.target_units["model"].unique().tolist())
    serial_models = [
        model for model in models if model_requires_serial_execution(model)
    ]
    parallel_models = [
        model for model in models if not model_requires_serial_execution(model)
    ]
    model_outputs: dict[str, Path] = {}

    def run_one(model: str, *, model_parallel_chunks: int) -> Path:
        return run_model_chunks(
            scenario_manifest=preparation.scenario_manifest_paths[model],
            output_dir=_model_output_dir(preparation.output_dir, model),
            country=country,
            model=model,
            program_set=program_set,
            chunk_size=chunk_size,
            parallel=model_parallel_chunks,
            chunk_attempts=chunk_attempts,
            include_explanations=include_explanations,
            single_output=False,
        )

    for model in serial_models:
        model_outputs[model] = run_one(model, model_parallel_chunks=1)

    if parallel_models:
        if model_parallel == 1:
            for model in parallel_models:
                model_outputs[model] = run_one(model, model_parallel_chunks=parallel)
        else:
            with ThreadPoolExecutor(max_workers=model_parallel) as executor:
                futures = {
                    executor.submit(
                        run_one,
                        model,
                        model_parallel_chunks=parallel,
                    ): model
                    for model in parallel_models
                }
                for future in as_completed(futures):
                    model_outputs[futures[future]] = future.result()

    return merge_model_outputs(
        model_output_paths=[model_outputs[model] for model in models],
        output_path=preparation.output_dir / "retry_predictions.csv",
    )


def _valid_retry_groups(
    *,
    source_predictions: pd.DataFrame,
    retry_predictions: pd.DataFrame,
    target_units: pd.DataFrame,
    require_explanations: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    source_variables = (
        source_predictions.merge(
            target_units[["model", "scenario_id"]],
            on=["model", "scenario_id"],
            how="inner",
        )
        .groupby(["model", "scenario_id"])["variable"]
        .apply(lambda values: set(values.astype(str)))
    )
    accepted = []
    rejected = []
    for key, expected_variables in source_variables.items():
        model, scenario_id = key
        group = retry_predictions[
            (retry_predictions["model"].astype(str) == str(model))
            & (retry_predictions["scenario_id"].astype(str) == str(scenario_id))
        ]
        reasons = []
        if group.empty:
            reasons.append("no retry rows")
        else:
            retry_variables = set(group["variable"].astype(str))
            if retry_variables != expected_variables:
                reasons.append("retry variable set does not match source response")
            if group.duplicated(["model", "scenario_id", "variable"]).any():
                reasons.append("duplicate retry rows")
            if group["prediction"].isna().any():
                reasons.append("missing retry prediction")
            if require_explanations and (
                "explanation" not in group.columns
                or not _nonempty_string_mask(group["explanation"]).all()
            ):
                reasons.append("missing retry explanation")
            if "error" in group.columns and _nonempty_string_mask(group["error"]).any():
                reasons.append("retry row has parser or provider error")
        row = {"model": model, "scenario_id": scenario_id}
        if reasons:
            rejected.append({**row, "reason": "; ".join(reasons)})
        else:
            accepted.append(row)
    return (
        pd.DataFrame(accepted, columns=["model", "scenario_id"]),
        pd.DataFrame(rejected, columns=["model", "scenario_id", "reason"]),
    )


def merge_retry_predictions(
    *,
    source_predictions: str | Path,
    retry_predictions: str | Path,
    target_units: str | Path,
    output_dir: str | Path,
    require_explanations: bool = True,
) -> dict[str, Path]:
    """Write a sensitivity prediction file with only fully parsed retries applied."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source = _read_prediction_csv(source_predictions)
    retry = _read_prediction_csv(retry_predictions)
    targets = pd.read_csv(target_units)
    if "country" in targets.columns:
        targets = targets.drop(columns=["country"])

    accepted, rejected = _valid_retry_groups(
        source_predictions=source,
        retry_predictions=retry,
        target_units=targets,
        require_explanations=require_explanations,
    )
    accepted_path = output_dir / "accepted_retry_units.csv"
    rejected_path = output_dir / "rejected_retry_units.csv"
    accepted.to_csv(accepted_path, index=False)
    rejected.to_csv(rejected_path, index=False)

    if accepted.empty:
        merged = source.copy()
        accepted_retry_rows = retry.iloc[0:0].copy()
        replaced_originals = source.iloc[0:0].copy()
    else:
        accepted_keys = accepted.assign(_accepted=True)
        source_with_flags = source.merge(
            accepted_keys,
            on=["model", "scenario_id"],
            how="left",
        )
        retry_with_flags = retry.merge(
            accepted_keys,
            on=["model", "scenario_id"],
            how="inner",
        )
        accepted_mask = source_with_flags["_accepted"].fillna(False).astype(bool)
        replaced_originals = source_with_flags[accepted_mask].drop(
            columns=["_accepted"]
        )
        kept_source = source_with_flags[~accepted_mask].drop(columns=["_accepted"])
        accepted_retry_rows = retry_with_flags.drop(columns=["_accepted"])
        merged = pd.concat([kept_source, accepted_retry_rows], ignore_index=True)

    sort_columns = [
        column
        for column in ["model", "scenario_id", "variable"]
        if column in merged.columns
    ]
    if sort_columns:
        merged = merged.sort_values(sort_columns).reset_index(drop=True)

    merged_path = output_dir / "merged_predictions.csv.gz"
    accepted_rows_path = output_dir / "accepted_retry_rows.csv.gz"
    replaced_originals_path = output_dir / "replaced_original_responses.csv.gz"
    merged.to_csv(merged_path, index=False)
    accepted_retry_rows.to_csv(accepted_rows_path, index=False)
    replaced_originals.to_csv(replaced_originals_path, index=False)
    return {
        "merged_predictions": merged_path,
        "accepted_retry_units": accepted_path,
        "rejected_retry_units": rejected_path,
        "accepted_retry_rows": accepted_rows_path,
        "replaced_original_responses": replaced_originals_path,
    }


def run_retry_round(
    *,
    country: str,
    source_predictions: str | Path,
    scenario_manifest: str | Path,
    output_dir: str | Path,
    program_set: str = DEFAULT_PROGRAM_SET,
    chunk_size: int = 10,
    parallel: int = 1,
    model_parallel: int = 1,
    chunk_attempts: int = 1,
    require_explanations: bool = True,
    models: list[str] | None = None,
    max_responses: int | None = None,
    prepare_only: bool = False,
) -> dict[str, Path]:
    """Prepare and optionally run a full-response retry round."""
    preparation = prepare_retry_round(
        country=country,
        source_predictions=source_predictions,
        scenario_manifest=scenario_manifest,
        output_dir=output_dir,
        require_explanations=require_explanations,
        models=models,
        max_responses=max_responses,
    )
    outputs = {
        "target_units": preparation.output_dir / "target_units.csv",
        "original_failed_responses": preparation.original_failed_rows_path,
        "source_predictions_copy": preparation.source_predictions_copy,
    }
    if prepare_only:
        return outputs
    retry_predictions = run_retry_models(
        preparation=preparation,
        country=country,
        program_set=program_set,
        chunk_size=chunk_size,
        parallel=parallel,
        model_parallel=model_parallel,
        chunk_attempts=chunk_attempts,
        include_explanations=require_explanations,
    )
    outputs["retry_predictions"] = retry_predictions
    outputs.update(
        merge_retry_predictions(
            source_predictions=source_predictions,
            retry_predictions=retry_predictions,
            target_units=outputs["target_units"],
            output_dir=preparation.output_dir,
            require_explanations=require_explanations,
        )
    )
    return outputs
