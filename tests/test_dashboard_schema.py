"""Tests for dashboard payload validation."""

import json

import pytest

from policybench.dashboard_schema import (
    DashboardValidationError,
    assert_valid_dashboard_payload,
    dump_country_payload,
    dump_dashboard_payload,
    validate_country_payload,
    validate_dashboard_payload,
)


def make_bench(country: str = "us") -> dict:
    return {
        "country": country,
        "scenarios": {
            "scenario_001": {
                "country": country,
                "state": "CA" if country == "us" else "London",
                "numAdults": 1,
                "numChildren": 2,
                "totalIncome": 30000,
            }
        },
        "modelStats": [
            {"model": "model-a", "condition": "no_tools", "score": 71.5, "n": 100}
        ],
        "programStats": [{"variable": "snap", "score": 60.0, "mae": 12.0, "n": 100}],
        "heatmap": [
            {
                "model": "model-a",
                "variable": "snap",
                "condition": "no_tools",
                "score": 60.0,
            }
        ],
        "scenarioPredictions": {
            "scenario_001": {
                "snap": {
                    "model-a": {"prediction": 100.0, "groundTruth": 90.0},
                }
            }
        },
        "failureModes": {"programs": [], "households": []},
    }


def make_payload() -> dict:
    return {"countries": {"us": make_bench("us"), "uk": make_bench("uk")}}


def test_valid_payload_passes():
    assert validate_dashboard_payload(make_payload()) == []


def test_valid_country_payload_passes():
    assert validate_country_payload(make_bench(), country="us") == []


def test_per_country_payload_at_top_level_gets_specific_error():
    # The exact failure mode observed in the wild: a <run>/<country>/data.json
    # copied to app/src/data.json.
    errors = validate_dashboard_payload(make_bench())
    assert len(errors) == 1
    assert "per-country export" in errors[0]


def test_missing_countries_key():
    assert validate_dashboard_payload({"foo": 1}) == [
        "payload missing top-level 'countries' object"
    ]


def test_country_key_mismatch():
    payload = {"countries": {"us": make_bench("uk")}}
    errors = validate_dashboard_payload(payload)
    assert any("keyed under 'us'" in error for error in errors)


def test_missing_bench_keys_reported():
    bench = make_bench()
    del bench["modelStats"]
    del bench["failureModes"]
    errors = validate_country_payload(bench, country="us")
    assert any("missing required keys" in error for error in errors)
    assert any("modelStats must be a non-empty array" in error for error in errors)


def test_orphan_scenario_predictions_reported():
    bench = make_bench()
    bench["scenarioPredictions"]["scenario_999"] = bench["scenarioPredictions"][
        "scenario_001"
    ]
    errors = validate_country_payload(bench, country="us")
    assert any("scenario_999" in error for error in errors)


def test_no_tools_condition_required():
    bench = make_bench()
    bench["modelStats"][0]["condition"] = "web_search"
    errors = validate_country_payload(bench, country="us")
    assert any("no_tools" in error for error in errors)


def make_wrong_leaf(**extra) -> dict:
    return {"prediction": 100.0, "groundTruth": 90.0, "thresholdScore": 0.0, **extra}


def test_wrong_answer_without_failure_annotation_fails_publish_gate():
    # The gap class shipped in 20260707b: GPT-5.5's default-effort rerun had
    # wrong answers with no judged failureSource. Publishing must fail.
    bench = make_bench()
    bench["scenarioPredictions"]["scenario_001"]["snap"]["model-a"] = make_wrong_leaf()
    errors = validate_country_payload(
        bench, country="us", require_failure_annotations=True
    )
    assert errors == [
        "countries.us.scenarioPredictions.scenario_001.snap.model-a: "
        "wrong answer has no judged failureSource annotation"
    ]


def test_wrong_answer_without_failure_annotation_allowed_in_staged_export():
    # Fold-board staging exports precede the failure audit, so the default
    # (non-publish) validation stays structural.
    bench = make_bench()
    bench["scenarioPredictions"]["scenario_001"]["snap"]["model-a"] = make_wrong_leaf()
    assert validate_country_payload(bench, country="us") == []


def test_wrong_answer_with_failure_annotation_passes_publish_gate():
    bench = make_bench()
    bench["scenarioPredictions"]["scenario_001"]["snap"]["model-a"] = make_wrong_leaf(
        failureSource="model",
        failureSubtype="calculation_error",
        annotation="The model omitted the standard deduction.",
    )
    errors = validate_country_payload(
        bench, country="us", require_failure_annotations=True
    )
    assert errors == []


def test_correct_answer_needs_no_failure_annotation():
    bench = make_bench()
    bench["scenarioPredictions"]["scenario_001"]["snap"]["model-a"] = {
        "prediction": 90.0,
        "groundTruth": 90.0,
        "thresholdScore": 100.0,
    }
    errors = validate_country_payload(
        bench, country="us", require_failure_annotations=True
    )
    assert errors == []


def test_dashboard_payload_threads_annotation_requirement():
    payload = make_payload()
    payload["countries"]["us"]["scenarioPredictions"]["scenario_001"]["snap"][
        "model-a"
    ] = make_wrong_leaf()
    assert validate_dashboard_payload(payload) == []
    errors = validate_dashboard_payload(payload, require_failure_annotations=True)
    assert errors == [
        "countries.us.scenarioPredictions.scenario_001.snap.model-a: "
        "wrong answer has no judged failureSource annotation"
    ]


def test_nan_score_reported():
    bench = make_bench()
    bench["modelStats"][0]["score"] = float("nan")
    errors = validate_country_payload(bench, country="us")
    assert any("finite number" in error for error in errors)


def test_dump_rejects_nan_anywhere():
    payload = make_payload()
    payload["countries"]["us"]["programStats"][0]["mae"] = float("nan")
    # Structural checks don't cover every numeric leaf; allow_nan=False is the
    # backstop because JSON.parse in the browser rejects NaN literals.
    with pytest.raises(ValueError):
        dump_dashboard_payload(payload)


def test_dump_round_trips():
    payload = make_payload()
    assert json.loads(dump_dashboard_payload(payload)) == payload
    bench = make_bench()
    assert json.loads(dump_country_payload(bench, country="us")) == bench


def test_assert_raises_with_readable_message():
    with pytest.raises(DashboardValidationError) as excinfo:
        assert_valid_dashboard_payload(make_bench(), source="app/src/data.json")
    message = str(excinfo.value)
    assert "app/src/data.json" in message
    assert "per-country export" in message
