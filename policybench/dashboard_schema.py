"""Structural validation for dashboard payloads.

The app consumes one combined payload (``app/src/data.json``) shaped as
``{"countries": {"us": <bench>, "uk": <bench>}}``; per-country exports
(``<run>/<country>/data.json``) are the inner bench objects. The two shapes
are easy to confuse — copying a per-country file to the app path produces a
site that crashes at runtime — so every write and publish goes through the
validators here, which also reject NaN/Infinity values that Python's json
module would happily emit but ``JSON.parse`` in the browser rejects.
"""

from __future__ import annotations

import json
import math
from typing import Any

COUNTRY_CODES = ("us", "uk")

_BENCH_REQUIRED_KEYS = (
    "country",
    "scenarios",
    "modelStats",
    "programStats",
    "heatmap",
    "scenarioPredictions",
    "failureModes",
)

_SCENARIO_REQUIRED_KEYS = ("country", "state", "numAdults", "numChildren")

_MODEL_STAT_REQUIRED_KEYS = ("model", "condition", "score", "n")


class DashboardValidationError(ValueError):
    """A dashboard payload failed structural validation."""

    def __init__(self, source: str, errors: list[str]):
        self.errors = errors
        bullet_list = "\n".join(f"  - {error}" for error in errors)
        super().__init__(
            f"{source} failed dashboard validation "
            f"({len(errors)} error{'s' if len(errors) != 1 else ''}):\n"
            f"{bullet_list}"
        )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    return _is_number(value) and math.isfinite(value)


def validate_country_payload(bench: Any, *, country: str | None = None) -> list[str]:
    """Validate one country's bench payload. Returns a list of errors."""
    if not isinstance(bench, dict):
        return [f"bench payload must be an object, got {type(bench).__name__}"]

    errors: list[str] = []
    prefix = f"countries.{country}" if country else "payload"

    missing = [key for key in _BENCH_REQUIRED_KEYS if key not in bench]
    if missing:
        errors.append(f"{prefix}: missing required keys {missing}")

    declared = bench.get("country")
    if country is not None and declared != country:
        errors.append(
            f"{prefix}.country is {declared!r} but the payload is keyed "
            f"under {country!r}"
        )
    elif country is None and declared not in COUNTRY_CODES:
        errors.append(
            f"{prefix}.country must be one of {COUNTRY_CODES}, got {declared!r}"
        )

    scenarios = bench.get("scenarios")
    if not isinstance(scenarios, dict) or not scenarios:
        errors.append(f"{prefix}.scenarios must be a non-empty object")
        scenarios = {}
    else:
        for scenario_id, scenario in scenarios.items():
            if not isinstance(scenario, dict):
                errors.append(f"{prefix}.scenarios.{scenario_id} must be an object")
                continue
            scenario_missing = [
                key for key in _SCENARIO_REQUIRED_KEYS if key not in scenario
            ]
            if scenario_missing:
                errors.append(
                    f"{prefix}.scenarios.{scenario_id}: missing keys {scenario_missing}"
                )

    model_stats = bench.get("modelStats")
    if not isinstance(model_stats, list) or not model_stats:
        errors.append(f"{prefix}.modelStats must be a non-empty array")
    else:
        for index, row in enumerate(model_stats):
            if not isinstance(row, dict):
                errors.append(f"{prefix}.modelStats[{index}] must be an object")
                continue
            row_missing = [key for key in _MODEL_STAT_REQUIRED_KEYS if key not in row]
            if row_missing:
                errors.append(
                    f"{prefix}.modelStats[{index}] ({row.get('model', '?')}): "
                    f"missing keys {row_missing}"
                )
                continue
            if not _is_finite_number(row["score"]):
                errors.append(
                    f"{prefix}.modelStats[{index}] ({row['model']}): score must "
                    f"be a finite number, got {row['score']!r}"
                )
        conditions = {
            row.get("condition") for row in model_stats if isinstance(row, dict)
        }
        if conditions and "no_tools" not in conditions:
            errors.append(
                f"{prefix}.modelStats has no rows for condition 'no_tools' "
                f"(found {sorted(str(value) for value in conditions)})"
            )

    program_stats = bench.get("programStats")
    if not isinstance(program_stats, list) or not program_stats:
        errors.append(f"{prefix}.programStats must be a non-empty array")

    if not isinstance(bench.get("heatmap"), list):
        errors.append(f"{prefix}.heatmap must be an array")

    predictions = bench.get("scenarioPredictions")
    if not isinstance(predictions, dict):
        errors.append(f"{prefix}.scenarioPredictions must be an object")
    else:
        unknown = sorted(set(predictions) - set(scenarios))[:5]
        if unknown:
            errors.append(
                f"{prefix}.scenarioPredictions references scenario ids not in "
                f"scenarios: {unknown}"
            )
        for scenario_id, variable_map in predictions.items():
            if not isinstance(variable_map, dict):
                errors.append(
                    f"{prefix}.scenarioPredictions.{scenario_id} must be an object"
                )
                continue
            for variable, model_map in variable_map.items():
                if not isinstance(model_map, dict):
                    errors.append(
                        f"{prefix}.scenarioPredictions.{scenario_id}.{variable} "
                        f"must be an object"
                    )
                    continue
                for model, record in model_map.items():
                    if not isinstance(record, dict):
                        errors.append(
                            f"{prefix}.scenarioPredictions.{scenario_id}."
                            f"{variable}.{model} must be an object"
                        )
                        continue
                    if "prediction" not in record or "groundTruth" not in record:
                        errors.append(
                            f"{prefix}.scenarioPredictions.{scenario_id}."
                            f"{variable}.{model}: missing prediction or "
                            f"groundTruth"
                        )
                    elif not _is_finite_number(record["groundTruth"]):
                        errors.append(
                            f"{prefix}.scenarioPredictions.{scenario_id}."
                            f"{variable}.{model}: groundTruth must be a finite "
                            f"number, got {record['groundTruth']!r}"
                        )

    failure_modes = bench.get("failureModes")
    if not isinstance(failure_modes, dict) or not {
        "programs",
        "households",
    } <= set(failure_modes):
        errors.append(
            f"{prefix}.failureModes must be an object with 'programs' and 'households'"
        )

    return errors


def validate_dashboard_payload(payload: Any) -> list[str]:
    """Validate the combined app payload. Returns a list of errors."""
    if not isinstance(payload, dict):
        return [f"payload must be an object, got {type(payload).__name__}"]

    if "countries" not in payload:
        if {"country", "modelStats"} <= set(payload):
            return [
                "payload looks like a per-country export "
                "(<run>/<country>/data.json); the app payload must be the "
                'combined {"countries": {...}} shape written by '
                "export_full_run"
            ]
        return ["payload missing top-level 'countries' object"]

    countries = payload["countries"]
    if not isinstance(countries, dict) or not countries:
        return ["payload.countries must be a non-empty object"]

    errors: list[str] = []
    unknown = sorted(set(countries) - set(COUNTRY_CODES))
    if unknown:
        errors.append(
            f"payload.countries has unknown country keys {unknown}; expected "
            f"a subset of {list(COUNTRY_CODES)}"
        )

    for country, bench in countries.items():
        if country in COUNTRY_CODES:
            errors.extend(validate_country_payload(bench, country=country))

    return errors


def assert_valid_dashboard_payload(payload: Any, *, source: str = "payload") -> None:
    errors = validate_dashboard_payload(payload)
    if errors:
        raise DashboardValidationError(source, errors)


def assert_valid_country_payload(
    bench: Any, *, country: str | None = None, source: str = "payload"
) -> None:
    errors = validate_country_payload(bench, country=country)
    if errors:
        raise DashboardValidationError(source, errors)


def dump_dashboard_payload(payload: Any, *, source: str = "payload") -> str:
    """Validate and serialize the combined payload.

    ``allow_nan=False`` matters: Python happily writes NaN/Infinity literals
    that are invalid JSON, and ``JSON.parse`` in the browser throws on them.
    """
    assert_valid_dashboard_payload(payload, source=source)
    return json.dumps(payload, allow_nan=False)


def dump_country_payload(
    bench: Any, *, country: str | None = None, source: str = "payload"
) -> str:
    """Validate and serialize one country's bench payload."""
    assert_valid_country_payload(bench, country=country, source=source)
    return json.dumps(bench, allow_nan=False)
