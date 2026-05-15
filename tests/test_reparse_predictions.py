import json

import pandas as pd

from policybench.reparse_predictions import (
    parse_serialized_response,
    reparse_predictions_frame,
)


def _tool_response(arguments: dict) -> str:
    return json.dumps(
        {
            "tool_calls": [
                {
                    "name": "submit_outputs",
                    "arguments": json.dumps(arguments),
                }
            ]
        }
    )


def test_parse_serialized_response_accepts_nested_outputs_string() -> None:
    raw_response = json.dumps(
        {
            "responses": [
                _tool_response(
                    {
                        "outputs": json.dumps(
                            {
                                "spouse_chip_eligible": {
                                    "value": 0,
                                    "explanation": (
                                        "Spouse is an adult, not CHIP eligible. "
                                        "value = 0"
                                    ),
                                }
                            }
                        )
                    }
                )
            ]
        }
    )

    predictions, explanations = parse_serialized_response(
        raw_response,
        ["spouse_chip_eligible"],
    )

    assert predictions == {"spouse_chip_eligible": 0.0}
    assert explanations == {
        "spouse_chip_eligible": "Spouse is an adult, not CHIP eligible. value = 0"
    }


def test_reparse_predictions_frame_updates_missing_values_from_raw_response() -> None:
    raw_response = json.dumps(
        {
            "chunked_responses": [
                {
                    "variables": ["spouse_chip_eligible"],
                    "raw_response": json.dumps(
                        {
                            "responses": [
                                _tool_response(
                                    {
                                        "outputs": json.dumps(
                                            {
                                                "spouse_chip_eligible": {
                                                    "value": 0,
                                                    "explanation": (
                                                        "Spouse is age 61, so not "
                                                        "CHIP eligible. value = 0"
                                                    ),
                                                }
                                            }
                                        )
                                    }
                                )
                            ]
                        }
                    ),
                }
            ]
        }
    )
    predictions = pd.DataFrame(
        [
            {
                "model": "claude-sonnet-4.6",
                "scenario_id": "scenario_000",
                "variable": "spouse_chip_eligible",
                "prediction": None,
                "explanation": None,
                "raw_response": raw_response,
                "error": (
                    "Missing predictions after repair: spouse_chip_eligible; "
                    "Missing explanations after repair: spouse_chip_eligible"
                ),
            }
        ]
    )

    reparsed = reparse_predictions_frame(predictions)

    assert reparsed["prediction"].iloc[0] == 0
    assert "age 61" in reparsed["explanation"].iloc[0]
    assert pd.isna(reparsed["error"].iloc[0])


def test_reparse_predictions_frame_keeps_existing_values_when_raw_is_unparsed() -> None:
    predictions = pd.DataFrame(
        [
            {
                "model": "gemini",
                "scenario_id": "scenario_000",
                "variable": "income_tax",
                "prediction": 123.0,
                "explanation": "Already parsed. value = 123",
                "raw_response": "provider-specific raw text",
                "error": None,
            }
        ]
    )

    reparsed = reparse_predictions_frame(predictions)

    assert reparsed["prediction"].iloc[0] == 123.0
    assert reparsed["explanation"].iloc[0] == "Already parsed. value = 123"
    assert pd.isna(reparsed["error"].iloc[0])
