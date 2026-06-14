"""Build and run local Codex audits for PolicyBench cell deviations."""

from __future__ import annotations

import json
import math
import random
import re
import shutil
import subprocess
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from policybench.analysis import (
    build_scenario_prompt_map,
    threshold_score_single_prediction,
)
from policybench.full_run_export import load_predictions

AUDIT_CLASSIFICATIONS = [
    "llm_error",
    "reference_error",
    "prompt_underspecified",
    "mixed",
    "needs_reference_review",
]

PROMPT_OPPORTUNITY_FLAGS = [
    "missing_program_mechanics",
    "hidden_defaults_and_eligibility_facts",
    "reference_explanation_omits_decisive_mechanics",
    "ambiguous_variable_semantics",
    "cross_program_dependencies",
    "inconsistent_prompt_source_values",
]


RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "id",
        "classification",
        "confidence",
        "summary",
        "evidence",
        "model_patterns",
        "arithmetic",
        "prompt_opportunity_flags",
    ],
    "properties": {
        "id": {"type": "string"},
        "classification": {"type": "string", "enum": AUDIT_CLASSIFICATIONS},
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "summary": {"type": "string"},
        "evidence": {"type": "string"},
        "model_patterns": {"type": "string"},
        "arithmetic": {"type": "string"},
        "prompt_opportunity_flags": {
            "type": "array",
            "items": {"type": "string", "enum": PROMPT_OPPORTUNITY_FLAGS},
        },
    },
}


@dataclass(frozen=True)
class AuditRunResult:
    """Summary of a local Codex audit batch."""

    attempted: int
    completed: int
    failed: int
    audit_dir: Path


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_default(value: Any) -> Any:
    if value is pd.NA:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        return _json_default(value.item())
    return value


def _clean_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clean_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean_value(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return _json_default(value)


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return slug or "cell"


def _reference_path(country_dir: Path) -> Path:
    reference_path = country_dir / "reference_outputs.csv"
    if reference_path.exists():
        return reference_path
    legacy_path = country_dir / "ground_truth.csv"
    if legacy_path.exists():
        return legacy_path
    raise FileNotFoundError(f"Missing reference outputs in {country_dir}.")


def _read_reference_explanations(
    run_dir: Path, country: str
) -> dict[tuple[str, str], str]:
    path = run_dir / "annotations" / f"{country}_case_reference_explanations.csv"
    if not path.exists():
        return {}
    explanations = pd.read_csv(path)
    required = {"scenario_id", "variable", "explanation"}
    if not required.issubset(explanations.columns):
        return {}
    return {
        (str(row["scenario_id"]), str(row["variable"])): str(row["explanation"])
        for _, row in explanations.dropna(subset=["explanation"]).iterrows()
    }


def _expected_prediction_rows(
    reference: pd.DataFrame,
    predictions: pd.DataFrame,
) -> pd.DataFrame:
    models = pd.DataFrame({"model": sorted(predictions["model"].dropna().unique())})
    expected = reference.assign(_join_key=1).merge(
        models.assign(_join_key=1),
        on="_join_key",
    )
    expected = expected.drop(columns="_join_key")
    prediction_columns = [
        column
        for column in [
            "call_id",
            "model",
            "scenario_id",
            "variable",
            "prediction",
            "explanation",
            "raw_response",
            "error",
            "elapsed_seconds",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "provider_response_id",
            "provider_system_fingerprint",
            "provider_resolved_model",
        ]
        if column in predictions.columns
    ]
    merged = expected.merge(
        predictions[prediction_columns],
        on=["model", "scenario_id", "variable"],
        how="left",
    )
    if "prediction" not in merged.columns:
        merged["prediction"] = pd.NA
    if "explanation" not in merged.columns:
        merged["explanation"] = pd.NA
    return merged


def _score_rows(rows: pd.DataFrame) -> pd.DataFrame:
    scored = rows.copy()
    scored["score"] = [
        threshold_score_single_prediction(variable, truth, prediction)
        for variable, truth, prediction in zip(
            scored["variable"],
            scored["value"],
            scored["prediction"],
            strict=True,
        )
    ]
    return scored


def _modal_prediction(values: pd.Series) -> tuple[Any, int]:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return None, 0
    rounded = [f"{value:.6g}" for value in numeric]
    value, count = Counter(rounded).most_common(1)[0]
    return value, int(count)


def _max_abs_error(group: pd.DataFrame) -> float | None:
    prediction = pd.to_numeric(group["prediction"], errors="coerce")
    truth = pd.to_numeric(group["value"], errors="coerce")
    errors = (prediction - truth).abs().dropna()
    if errors.empty:
        return None
    return float(errors.max())


def _source_artifacts(run_dir: Path, country: str) -> dict[str, str]:
    country_dir = run_dir / country
    return {
        "run_dir": str(run_dir.resolve()),
        "country_dir": str(country_dir.resolve()),
        "scenarios": str((country_dir / "scenarios.csv").resolve()),
        "reference_outputs": str(_reference_path(country_dir).resolve()),
        "predictions": str((country_dir / "predictions.csv").resolve()),
        "by_model_dir": str((country_dir / "by_model").resolve()),
    }


def _scenario_summaries(
    scenarios: pd.DataFrame,
    variables: list[str],
) -> dict[str, dict[str, Any]]:
    prompt_map = build_scenario_prompt_map(scenarios, variables)
    summaries: dict[str, dict[str, Any]] = {}
    for _, row in scenarios.iterrows():
        scenario_id = str(row["scenario_id"])
        scenario_prompts = prompt_map.get(scenario_id, {})
        first_prompt = next(iter(scenario_prompts.values()), {})
        summaries[scenario_id] = {
            key: _clean_value(row[key])
            for key in [
                "country",
                "state",
                "filing_status",
                "num_adults",
                "num_children",
                "total_income",
                "source_dataset",
            ]
            if key in row.index
        }
        summaries[scenario_id]["prompt"] = {
            "tool": first_prompt.get("tool"),
            "json": first_prompt.get("json"),
        }
    return summaries


def _model_response_records(group: pd.DataFrame) -> list[dict[str, Any]]:
    columns = [
        "model",
        "prediction",
        "value",
        "error",
        "score",
        "explanation",
        "raw_response",
        "elapsed_seconds",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "provider_response_id",
        "provider_system_fingerprint",
        "provider_resolved_model",
    ]
    rows = []
    for _, row in group.sort_values("model").iterrows():
        record = {
            column: _clean_value(row[column])
            for column in columns
            if column in row.index
        }
        record["reference_value"] = record.pop("value", None)
        rows.append(record)
    return rows


def write_result_schema(audit_dir: Path) -> Path:
    path = audit_dir / "cell_deviation_audit_result.schema.json"
    path.write_text(json.dumps(RESULT_SCHEMA, indent=2) + "\n", encoding="utf-8")
    return path


def build_cell_deviation_audit_run(
    *,
    run_dir: str | Path,
    output_dir: str | Path,
    countries: Sequence[str] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Build a deterministic local-Codex audit queue and packet set."""
    run_path = Path(run_dir)
    audit_dir = Path(output_dir)
    if audit_dir.exists() and any(audit_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"{audit_dir} already exists and is not empty; pass overwrite=True."
        )
    if audit_dir.exists() and overwrite:
        shutil.rmtree(audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    packets_dir = audit_dir / "packets"
    packets_dir.mkdir(exist_ok=True)
    (audit_dir / "raw_subagent_outputs").mkdir(exist_ok=True)
    (audit_dir / "codex_events").mkdir(exist_ok=True)

    selected_countries = list(countries or ["us", "uk"])
    queue: list[dict[str, Any]] = []
    country_counts: dict[str, int] = {}
    created_at = _now_iso()

    for country in selected_countries:
        country_dir = run_path / country
        reference = pd.read_csv(_reference_path(country_dir))
        predictions = load_predictions(country_dir)
        scenarios = pd.read_csv(country_dir / "scenarios.csv")
        variables = reference["variable"].drop_duplicates().astype(str).tolist()
        summaries = _scenario_summaries(scenarios, variables)
        reference_explanations = _read_reference_explanations(run_path, country)
        scored = _score_rows(_expected_prediction_rows(reference, predictions))
        wrong = scored[scored["score"] < 1].copy()
        source_artifacts = _source_artifacts(run_path, country)
        country_count = 0

        for (scenario_id, variable), wrong_group in wrong.groupby(
            ["scenario_id", "variable"],
            sort=True,
        ):
            group = scored[
                (scored["scenario_id"] == scenario_id)
                & (scored["variable"] == variable)
            ].copy()
            reference_value = group["value"].iloc[0]
            modal_prediction, modal_prediction_count = _modal_prediction(
                group["prediction"]
            )
            cell_id = f"{country}:{scenario_id}:{variable}"
            index = len(queue) + 1
            packet_name = (
                f"{index:04d}_{_safe_slug(country)}_{_safe_slug(str(scenario_id))}_"
                f"{_safe_slug(str(variable))}.json"
            )
            packet_path = packets_dir / packet_name
            reference_explanation = reference_explanations.get(
                (str(scenario_id), str(variable)),
                "",
            )
            queue_record = {
                "id": cell_id,
                "country": country,
                "scenario_id": str(scenario_id),
                "variable": str(variable),
                "reference_value": _clean_value(reference_value),
                "wrong_count": int(len(wrong_group)),
                "parsed_count": int(
                    pd.to_numeric(group["prediction"], errors="coerce").notna().sum()
                ),
                "exact_count": int((group["score"] >= 1).sum()),
                "modal_prediction": modal_prediction,
                "modal_prediction_count": modal_prediction_count,
                "max_abs_error": _max_abs_error(group),
                "reference_explanation": reference_explanation,
                "artifact_paths": source_artifacts,
                "status": "queued",
                "queue_index": index,
                "packet_path": str(packet_path.resolve()),
            }
            packet = {
                "id": cell_id,
                "country": country,
                "scenario_id": str(scenario_id),
                "variable": str(variable),
                "reference_value": _clean_value(reference_value),
                "reference_explanation": reference_explanation,
                "scenario_summary": summaries.get(str(scenario_id), {}),
                "model_responses": _model_response_records(group),
                "queue_record": queue_record,
                "source_artifacts": source_artifacts,
                "requested_classifications": AUDIT_CLASSIFICATIONS,
                "prompt_opportunity_flags": PROMPT_OPPORTUNITY_FLAGS,
            }
            packet_path.write_text(
                json.dumps(packet, indent=2, default=_json_default) + "\n",
                encoding="utf-8",
            )
            queue.append(queue_record)
            country_count += 1
        country_counts[country] = country_count

    manifest = {
        "run_id": audit_dir.name,
        "created_at": created_at,
        "source_run_dir": str(run_path.resolve()),
        "total_queued_cells": len(queue),
        "countries": country_counts,
        "output_files": {
            "queue_json": str((audit_dir / "queue.json").resolve()),
            "queue_jsonl": str((audit_dir / "queue.jsonl").resolve()),
            "audit_results_jsonl": str((audit_dir / "audit_results.jsonl").resolve()),
            "summary_md": str((audit_dir / "summary.md").resolve()),
            "raw_subagent_outputs_dir": str(
                (audit_dir / "raw_subagent_outputs").resolve()
            ),
            "codex_events_dir": str((audit_dir / "codex_events").resolve()),
        },
    }
    _write_json(audit_dir / "manifest.json", manifest)
    _write_json(audit_dir / "queue.json", queue)
    _write_jsonl(audit_dir / "queue.jsonl", queue)
    _write_json(audit_dir / "running_agents.json", [])
    (audit_dir / "audit_results.jsonl").write_text("", encoding="utf-8")
    write_result_schema(audit_dir)
    _write_summary(audit_dir, queue, [])
    return manifest


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, default=_json_default) + "\n")


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    text = "".join(json.dumps(row, default=_json_default) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return default
    return json.loads(raw)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_summary(
    audit_dir: Path,
    queue: Sequence[dict[str, Any]],
    results: Sequence[dict[str, Any]],
) -> None:
    status_counts = Counter(row.get("status", "queued") for row in queue)
    classification_counts = Counter(row.get("classification") for row in results)
    country_status: dict[str, Counter[str]] = {}
    for row in queue:
        country_status.setdefault(str(row.get("country")), Counter())[
            str(row.get("status", "queued"))
        ] += 1

    lines = [
        "# PolicyBench Cell Deviation Audits",
        "",
        f"Updated: {_now_iso()}",
        "",
        "## Status",
        "",
        f"- Complete: {status_counts.get('complete', 0)}",
        f"- Failed: {status_counts.get('failed', 0)}",
        f"- Running: {status_counts.get('running', 0)}",
        f"- Queued: {status_counts.get('queued', 0)}",
        "",
        "## Classifications",
        "",
    ]
    for classification in AUDIT_CLASSIFICATIONS:
        count = classification_counts.get(classification, 0)
        if count:
            lines.append(f"- {classification}: {count}")
    if not any(classification_counts.values()):
        lines.append("- None yet")
    lines.extend(["", "## By Country", ""])
    for country, counts in sorted(country_status.items()):
        parts = ", ".join(f"{key}: {value}" for key, value in sorted(counts.items()))
        lines.append(f"- {country}: {parts}")
    (audit_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _audit_prompt(packet_path: Path, repo_dir: Path) -> str:
    classifications = ", ".join(AUDIT_CLASSIFICATIONS)
    flags = ", ".join(PROMPT_OPPORTUNITY_FLAGS)
    return "\n".join(
        [
            "Audit one PolicyBench cell deviation.",
            "",
            f"Cell packet: {packet_path}",
            f"Repo: {repo_dir}",
            "",
            (
                "Read the packet JSON and any referenced local artifacts or code "
                "needed. Do not edit files, do not file GitHub issues, and do not "
                "run network calls."
            ),
            "",
            (
                "Decide whether the reference value is correct and why models "
                f"deviated. Use exactly one classification: {classifications}."
            ),
            "",
            (
                "Treat prompt/reference caveats separately from actual "
                "PolicyEngine/reference bugs. If prompt/reference caveats exist, "
                "include prompt_opportunity_flags using short labels from this "
                f"taxonomy when possible: {flags}."
            ),
            "",
            (
                "Return only schema-valid JSON with these fields: id, "
                "classification, confidence, summary, evidence, model_patterns, "
                "arithmetic, and prompt_opportunity_flags. Use an empty array "
                "for prompt_opportunity_flags when no taxonomy flags apply."
            ),
            "",
        ]
    )


def extract_json_result(text: str) -> dict[str, Any]:
    """Extract a JSON object from a Codex final message."""
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty Codex final message.")
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.S)
    if fence:
        return json.loads(fence.group(1))
    if stripped.startswith("{"):
        return json.loads(stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return json.loads(stripped[start : end + 1])
    raise ValueError("No JSON object found in Codex final message.")


def _codex_command(
    *,
    codex_bin: str,
    repo_dir: Path,
    schema_path: Path,
    output_path: Path,
    model: str | None,
    emit_json_events: bool,
) -> list[str]:
    cmd = [
        codex_bin,
        "exec",
        "-C",
        str(repo_dir),
        "--sandbox",
        "read-only",
        "-c",
        'approval_policy="never"',
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
        "-",
    ]
    if emit_json_events:
        cmd.insert(8, "--json")
    if model:
        cmd[2:2] = ["--model", model]
    return cmd


def _preflight_codex(
    *,
    codex_bin: str,
    repo_dir: Path,
    audit_dir: Path,
    model: str | None,
) -> None:
    """Validate local Codex auth/config once before claiming queue rows."""
    login = subprocess.run(
        [codex_bin, "login", "status"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if login.returncode != 0:
        error = login.stderr.strip() or login.stdout.strip()
        raise RuntimeError(f"Codex preflight failed: {error}")
    output_path = audit_dir / ".codex_preflight_output.txt"
    cmd = [
        codex_bin,
        "exec",
        "-C",
        str(repo_dir),
        "--sandbox",
        "read-only",
        "-c",
        'approval_policy="never"',
        "--output-last-message",
        str(output_path),
        "-",
    ]
    if model:
        cmd[2:2] = ["--model", model]
    smoke = subprocess.run(
        cmd,
        input="Reply with OK only.",
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )
    output_path.unlink(missing_ok=True)
    if smoke.returncode != 0:
        error = smoke.stderr.strip() or smoke.stdout.strip()
        raise RuntimeError(f"Codex preflight failed: {error}")


def _is_codex_environment_error(error: str) -> bool:
    fragments = (
        "Error loading config.toml",
        "unknown variant",
        "401 Unauthorized",
        "invalid_grant",
        "Missing bearer or basic authentication",
    )
    return any(fragment in error for fragment in fragments)


def _result_for_failure(
    *,
    row: dict[str, Any],
    started_at: str,
    completed_at: str,
    elapsed_seconds: float,
    output_path: Path,
    events_path: Path | None,
    stderr_path: Path | None,
    exit_code: int | None,
    error: str,
) -> dict[str, Any]:
    result = {
        "id": row["id"],
        "classification": "needs_reference_review",
        "confidence": 0,
        "summary": (
            f"Codex audit runner failed before producing a usable result: {error}"
        ),
        "evidence": error,
        "model_patterns": "",
        "arithmetic": "",
        "prompt_opportunity_flags": [],
        "started_at": started_at,
        "completed_at": completed_at,
        "elapsed_seconds": elapsed_seconds,
        "packet_path": row["packet_path"],
        "raw_output_path": str(output_path),
        "codex_events_path": str(events_path) if events_path is not None else None,
        "stderr_path": str(stderr_path) if stderr_path is not None else None,
        "exit_code": exit_code,
    }
    if _is_codex_environment_error(error):
        result["runner_environment_error"] = True
    return result


def _run_one_audit(
    *,
    row: dict[str, Any],
    audit_dir: Path,
    repo_dir: Path,
    codex_bin: str,
    model: str | None,
    timeout_seconds: int | None,
    keep_codex_events: bool,
) -> dict[str, Any]:
    packet_path = Path(row["packet_path"])
    cell_slug = _safe_slug(row["id"].replace(":", "_"))
    output_path = audit_dir / "raw_subagent_outputs" / f"{cell_slug}.json"
    events_path = audit_dir / "codex_events" / f"{cell_slug}.jsonl"
    stderr_path = audit_dir / "codex_events" / f"{cell_slug}.stderr.log"
    schema_path = audit_dir / "cell_deviation_audit_result.schema.json"
    started_at = _now_iso()
    started = time.perf_counter()
    cmd = _codex_command(
        codex_bin=codex_bin,
        repo_dir=repo_dir,
        schema_path=schema_path,
        output_path=output_path,
        model=model,
        emit_json_events=keep_codex_events,
    )
    try:
        completed = subprocess.run(
            cmd,
            input=_audit_prompt(packet_path, repo_dir),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        if keep_codex_events or completed.returncode != 0:
            events_path.write_text(completed.stdout, encoding="utf-8")
        if keep_codex_events or completed.returncode != 0:
            stderr_path.write_text(completed.stderr, encoding="utf-8")
        else:
            stderr_path.unlink(missing_ok=True)
        completed_at = _now_iso()
        elapsed_seconds = time.perf_counter() - started
        if completed.returncode != 0:
            return _result_for_failure(
                row=row,
                started_at=started_at,
                completed_at=completed_at,
                elapsed_seconds=elapsed_seconds,
                output_path=output_path,
                events_path=events_path if events_path.exists() else None,
                stderr_path=stderr_path if stderr_path.exists() else None,
                exit_code=completed.returncode,
                error=completed.stderr.strip() or completed.stdout.strip(),
            )
        parsed = extract_json_result(output_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - runner must persist failed cells.
        completed_at = _now_iso()
        elapsed_seconds = time.perf_counter() - started
        stderr_path.write_text(str(exc), encoding="utf-8")
        parsed = _result_for_failure(
            row=row,
            started_at=started_at,
            completed_at=completed_at,
            elapsed_seconds=elapsed_seconds,
            output_path=output_path,
            events_path=events_path if events_path.exists() else None,
            stderr_path=stderr_path,
            exit_code=None,
            error=str(exc),
        )
    parsed.update(
        {
            "id": row["id"],
            "started_at": parsed.get("started_at", started_at),
            "completed_at": parsed.get("completed_at", _now_iso()),
            "elapsed_seconds": parsed.get("elapsed_seconds", elapsed_seconds),
            "packet_path": str(packet_path),
            "raw_output_path": str(output_path),
            "codex_events_path": str(events_path) if events_path.exists() else None,
            "stderr_path": str(stderr_path) if stderr_path.exists() else None,
            "exit_code": parsed.get("exit_code", 0),
        }
    )
    return parsed


def run_cell_deviation_audits(
    *,
    audit_dir: str | Path,
    repo_dir: str | Path,
    limit: int | None = None,
    parallel: int = 1,
    codex_bin: str = "codex",
    model: str | None = None,
    timeout_seconds: int | None = None,
    keep_codex_events: bool = False,
    randomize: bool = False,
    random_seed: int | None = None,
) -> AuditRunResult:
    """Run local Codex audits for queued packets and persist result JSONL."""
    audit_path = Path(audit_dir)
    repo_path = Path(repo_dir)
    if parallel <= 0:
        raise ValueError("parallel must be positive.")
    queue_path = audit_path / "queue.json"
    results_path = audit_path / "audit_results.jsonl"
    queue = _read_json(queue_path, [])
    results = _read_jsonl(results_path)
    completed_ids = {row["id"] for row in results if row.get("exit_code", 0) == 0}
    selected = [
        row
        for row in queue
        if row.get("status", "queued") == "queued" and row["id"] not in completed_ids
    ]
    if randomize:
        if random_seed is None:
            random.SystemRandom().shuffle(selected)
        else:
            random.Random(random_seed).shuffle(selected)
    if limit is not None:
        selected = selected[:limit]
    if not selected:
        _write_summary(audit_path, queue, results)
        return AuditRunResult(0, 0, 0, audit_path)

    _preflight_codex(
        codex_bin=codex_bin,
        repo_dir=repo_path,
        audit_dir=audit_path,
        model=model,
    )

    for row in queue:
        if any(row["id"] == selected_row["id"] for selected_row in selected):
            row["status"] = "running"
    _write_json(queue_path, queue)
    _write_jsonl(audit_path / "queue.jsonl", queue)

    result_by_id = {row["id"]: row for row in results}
    selected_ids = {row["id"] for row in selected}
    completed = 0
    failed = 0

    def persist_progress() -> None:
        current_results = list(result_by_id.values())
        _write_json(queue_path, queue)
        _write_jsonl(audit_path / "queue.jsonl", queue)
        _write_jsonl(results_path, current_results)
        _write_json(audit_path / "running_agents.json", [])
        _write_summary(audit_path, queue, current_results)

    def requeue_unfinished_selected() -> None:
        for row in queue:
            if row["id"] in selected_ids and row.get("status") == "running":
                row["status"] = "queued"
                row.pop("completed_at", None)
                row.pop("elapsed_seconds", None)

    selected_iter = iter(selected)

    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = {}

        def submit_next() -> None:
            try:
                row = next(selected_iter)
            except StopIteration:
                return
            future = executor.submit(
                _run_one_audit,
                row=row,
                audit_dir=audit_path,
                repo_dir=repo_path,
                codex_bin=codex_bin,
                model=model,
                timeout_seconds=timeout_seconds,
                keep_codex_events=keep_codex_events,
            )
            futures[future] = row

        for _ in range(min(parallel, len(selected))):
            submit_next()

        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                futures.pop(future)
                result = future.result()
                if result.get("runner_environment_error"):
                    for pending in futures:
                        pending.cancel()
                    requeue_unfinished_selected()
                    persist_progress()
                    error = result.get("evidence") or result.get("summary")
                    raise RuntimeError(f"Codex environment failure: {error}")
                result_by_id[result["id"]] = result
                status = "complete" if result.get("exit_code", 0) == 0 else "failed"
                if status == "complete":
                    completed += 1
                else:
                    failed += 1
                for row in queue:
                    if row["id"] == result["id"]:
                        row["status"] = status
                        row["completed_at"] = result.get("completed_at")
                        row["elapsed_seconds"] = result.get("elapsed_seconds")
                    elif row["id"] in selected_ids and row.get("status") != "complete":
                        row["status"] = row.get("status", "running")
                persist_progress()
                submit_next()

    return AuditRunResult(len(selected), completed, failed, audit_path)
