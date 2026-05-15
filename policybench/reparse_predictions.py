"""Reparse saved provider responses after parser improvements."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from policybench.eval_no_tools import (
    _enforce_explanation_value_contract,
    _merge_predictions,
    _missing_explanations,
    _missing_variables,
    extract_explanations,
    extract_predictions,
)


def _json_loads(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _serialized_tool_calls(payload: dict) -> list[dict]:
    tool_calls = payload.get("tool_calls")
    if not isinstance(tool_calls, list):
        return []
    adapted = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        if "function" in tool_call:
            adapted.append(tool_call)
        else:
            adapted.append({"function": tool_call})
    return adapted


def _serialized_function_call(payload: dict):
    function_call = payload.get("function_call")
    if not isinstance(function_call, dict):
        return function_call
    if "function" in function_call:
        return function_call["function"]
    return function_call


def parse_serialized_response(
    raw_response: object,
    variables: list[str],
    *,
    include_explanations: bool = True,
) -> tuple[dict[str, float | None], dict[str, str | None]]:
    """Extract predictions and explanations from a stored raw_response field."""
    predictions = {variable: None for variable in variables}
    explanations = {variable: None for variable in variables}
    payload = _json_loads(raw_response)

    if isinstance(payload, dict) and isinstance(payload.get("chunked_responses"), list):
        for chunk in payload["chunked_responses"]:
            if not isinstance(chunk, dict):
                continue
            chunk_variables = [
                variable
                for variable in chunk.get("variables", [])
                if variable in predictions
            ]
            if not chunk_variables:
                continue
            chunk_predictions, chunk_explanations = parse_serialized_response(
                chunk.get("raw_response"),
                chunk_variables,
                include_explanations=include_explanations,
            )
            predictions = _merge_predictions(predictions, chunk_predictions)
            explanations.update(
                {
                    variable: value
                    for variable, value in chunk_explanations.items()
                    if value is not None
                }
            )
        return _enforce_explanation_value_contract(
            predictions,
            explanations,
            variables,
        )

    if isinstance(payload, dict) and isinstance(payload.get("responses"), list):
        for response in payload["responses"]:
            response_predictions, response_explanations = parse_serialized_response(
                response,
                variables,
                include_explanations=include_explanations,
            )
            predictions = _merge_predictions(predictions, response_predictions)
            explanations.update(
                {
                    variable: value
                    for variable, value in response_explanations.items()
                    if value is not None
                }
            )
        return _enforce_explanation_value_contract(
            predictions,
            explanations,
            variables,
        )

    if isinstance(payload, dict):
        content = payload.get("content")
        tool_calls = _serialized_tool_calls(payload)
        function_call = _serialized_function_call(payload)
        if content is None and not tool_calls and function_call is None:
            content = payload
    else:
        content = raw_response if isinstance(raw_response, str) else None
        tool_calls = None
        function_call = None

    predictions = extract_predictions(
        content,
        variables,
        tool_calls=tool_calls,
        function_call=function_call,
    )
    if include_explanations:
        explanations = extract_explanations(
            content,
            variables,
            tool_calls=tool_calls,
            function_call=function_call,
        )
    return _enforce_explanation_value_contract(
        predictions,
        explanations,
        variables,
    )


def _format_missing_error(
    predictions: dict[str, float | None],
    explanations: dict[str, str | None],
    variables: list[str],
    *,
    include_explanations: bool,
) -> str | None:
    errors = []
    missing = _missing_variables(predictions)
    if missing:
        errors.append("Missing predictions after repair: " + ", ".join(sorted(missing)))
    if include_explanations:
        missing_explanations = _missing_explanations(explanations, variables)
        if missing_explanations:
            errors.append(
                "Missing explanations after repair: "
                + ", ".join(sorted(missing_explanations))
            )
    return "; ".join(errors) if errors else None


def _format_row_missing_error(
    prediction: float | None,
    explanation: str | None,
    variable: str,
    *,
    include_explanations: bool,
) -> str | None:
    errors = []
    if prediction is None:
        errors.append(f"Missing prediction after repair: {variable}")
    if include_explanations and (
        not isinstance(explanation, str) or not explanation.strip()
    ):
        errors.append(f"Missing explanation after repair: {variable}")
    return "; ".join(errors) if errors else None


def reparse_predictions_frame(
    predictions: pd.DataFrame,
    *,
    include_explanations: bool = True,
) -> pd.DataFrame:
    """Return predictions with missing values repaired from raw responses.

    Existing parsed values are treated as observed provider outputs and are not
    cleared just because a later parser cannot interpret a provider-specific raw
    response representation.
    """
    reparsed = predictions.copy()
    if "explanation" not in reparsed.columns:
        reparsed["explanation"] = pd.NA
    if "error" not in reparsed.columns:
        reparsed["error"] = pd.NA
    reparsed["explanation"] = reparsed["explanation"].astype("object")
    reparsed["error"] = reparsed["error"].astype("object")

    for _, group in reparsed.groupby(["model", "scenario_id"], sort=False):
        variables = group["variable"].astype(str).tolist()
        raw_response = group["raw_response"].iloc[0]
        if not isinstance(raw_response, str) or not raw_response.strip():
            continue
        parsed_predictions, parsed_explanations = parse_serialized_response(
            raw_response,
            variables,
            include_explanations=include_explanations,
        )
        combined_predictions = {
            str(row["variable"]): (
                None if pd.isna(row.get("prediction")) else row.get("prediction")
            )
            for _, row in group.iterrows()
        }
        combined_explanations = {
            str(row["variable"]): (
                None if pd.isna(row.get("explanation")) else row.get("explanation")
            )
            for _, row in group.iterrows()
        }
        combined_predictions = _merge_predictions(
            combined_predictions,
            parsed_predictions,
        )
        combined_explanations.update(
            {
                variable: value
                for variable, value in parsed_explanations.items()
                if value is not None
            }
        )
        combined_predictions, combined_explanations = (
            _enforce_explanation_value_contract(
                combined_predictions,
                combined_explanations,
                variables,
            )
        )
        for index, row in group.iterrows():
            variable = str(row["variable"])
            if variable in combined_predictions:
                reparsed.at[index, "prediction"] = combined_predictions[variable]
            if variable in combined_explanations:
                reparsed.at[index, "explanation"] = combined_explanations[variable]
            reparsed.at[index, "error"] = _format_row_missing_error(
                combined_predictions.get(variable),
                combined_explanations.get(variable),
                variable,
                include_explanations=include_explanations,
            )
    return reparsed


def reparse_prediction_file(path: str | Path) -> int:
    """Reparse a prediction CSV in place. Return number of changed rows."""
    path = Path(path)
    original = pd.read_csv(path)
    reparsed = reparse_predictions_frame(original)
    changed = (
        original[["prediction", "explanation", "error"]]
        .fillna("<NA>")
        .ne(reparsed[["prediction", "explanation", "error"]].fillna("<NA>"))
        .any(axis=1)
    )
    reparsed.to_csv(path, index=False)
    return int(changed.sum())


def reparse_country_run(country_dir: str | Path) -> dict[str, int]:
    """Reparse predictions.csv and any by_model CSVs in a country run directory."""
    country_dir = Path(country_dir)
    changed = {}
    predictions_path = country_dir / "predictions.csv"
    if predictions_path.exists():
        changed[str(predictions_path)] = reparse_prediction_file(predictions_path)
    by_model_dir = country_dir / "by_model"
    if by_model_dir.exists():
        for path in sorted(by_model_dir.glob("*.csv")):
            changed[str(path)] = reparse_prediction_file(path)
    return changed


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Reparse saved prediction CSVs from raw provider responses."
    )
    parser.add_argument("country_dir", nargs="+")
    args = parser.parse_args()

    for country_dir in args.country_dir:
        for path, changed_rows in reparse_country_run(country_dir).items():
            print(f"{path}: {changed_rows} changed rows")


if __name__ == "__main__":
    main()
