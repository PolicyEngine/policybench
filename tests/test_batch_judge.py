"""The batch judge's payload and derivations, and the adversary hooks it uses.

The payload tests run on the three-household set from tests/conftest.py, so
they need the frozen engine; the adversary hook tests need no engine.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import batch_judge as bj  # noqa: E402
import tool_pilot_argon as pilot  # noqa: E402

from policybench import reference_adversary as ra  # noqa: E402
from policybench.consensus import ConsensusParams, consensus_flags  # noqa: E402

THREE = ConsensusParams(min_models=2, top_k=3, min_top=2, zero_cluster_min_models=2)


def _case(**overrides):
    case = dict(
        case_id="us__s__snap",
        country="us",
        scenario_id="s",
        variable="snap",
        definition="annual SNAP benefit",
        household_prompt="A household.",
        reference_value=100.0,
        consensus=(
            {
                "answer": 0.0,
                "n_models": 2,
                "n_top": 2,
                "top_models": ["a", "b"],
                "members": [
                    {"model": "a", "prediction": 0.0, "explanation": "x"},
                    {"model": "b", "prediction": 0.0, "explanation": "y"},
                ],
            },
        ),
        models_answered=3,
        models_exact=1,
        derivation="snap = 100",
    )
    case.update(overrides)
    return ra.AdversaryCase(**case)


def test_the_default_condition_leaves_both_headers_unchanged():
    case = _case()
    assert ra._STAGE1_HEADER in ra.render_stage1_prompt(case)
    stage2 = ra.render_stage2_prompt(case, {"answer": 1}, "0" * 64)
    assert stage2.startswith(ra._STAGE2_HEADER)
    assert "answer_condition" not in case.to_manifest_row()


def test_a_web_condition_restates_both_headers_and_survives_the_manifest():
    case = _case(answer_condition="answering with web search")
    stage1 = ra.render_stage1_prompt(case)
    stage2 = ra.render_stage2_prompt(case, {"answer": 1}, "0" * 64)
    for text in (stage1, stage2):
        assert "AI models answering with web search, agreed" in text
        assert ra.DEFAULT_ANSWER_CONDITION not in text
    row = case.to_manifest_row()
    assert row["answer_condition"] == "answering with web search"
    again = ra.AdversaryCase.from_manifest_row(row, case.derivation)
    assert again == case
    default = _case()
    assert (
        ra.AdversaryCase.from_manifest_row(
            default.to_manifest_row(), default.derivation
        )
        == default
    )


@pytest.mark.parametrize("condition", ["with web search", 3, ""])
def test_a_malformed_condition_is_refused(condition):
    with pytest.raises(ValueError, match="answerCondition"):
        ra.answer_condition_of({"answerCondition": condition})


def _payload(predictions, reference=100.0, definitions=None, condition=None):
    payload = {
        "country": "us",
        "modelStats": [{"model": m} for m in ("a", "b", "c")],
        "scenarios": {"s": {"prompt": {"tool": "A household."}, "state": "CA"}},
        "scenarioPredictions": {
            "s": {
                "snap": {
                    model: {
                        "prediction": value,
                        "explanation": f"{model} says {value}",
                        "groundTruth": reference,
                        "scored": True,
                    }
                    for model, value in predictions.items()
                }
            }
        },
    }
    if definitions is not None:
        payload["outputDefinitions"] = definitions
    if condition is not None:
        payload["answerCondition"] = condition
    return payload


def test_two_of_three_agreeing_off_the_reference_flag_a_cell_and_one_does_not():
    flagged = consensus_flags(_payload({"a": 0.0, "b": 0.0, "c": 100.0}), THREE)
    assert [(f["scenario_id"], f["variable"]) for f in flagged] == [("s", "snap")]
    assert flagged[0]["clusters"][0]["models"] == ["a", "b"]
    alone = consensus_flags(_payload({"a": 0.0, "b": 50.0, "c": 100.0}), THREE)
    assert alone == []
    exact = consensus_flags(_payload({"a": 100.4, "b": 99.6, "c": 100.0}), THREE)
    assert exact == []


def test_cases_take_the_payload_definition_and_condition():
    payload = _payload(
        {"a": 0.0, "b": 0.0, "c": 100.0},
        definitions={"snap": "v2 SNAP definition"},
        condition="answering with web search",
    )
    flags = consensus_flags(payload, THREE)
    (case,) = ra.build_adversary_cases(payload, flags)
    assert case.definition == "v2 SNAP definition"
    assert case.answer_condition == "answering with web search"
    payload.pop("outputDefinitions")
    payload.pop("answerCondition")
    (case,) = ra.build_adversary_cases(payload, flags)
    assert case.answer_condition == ra.DEFAULT_ANSWER_CONDITION
    assert case.definition != "v2 SNAP definition"


# --- On a household set ----------------------------------------------------


def _write_arm(runs, board, model, arm, stage, wrong=None):
    """Records for one model and arm whose sent prompt is the v2-pilot one."""
    reference = board["reference"].set_index(["scenario_id", "variable"])["value"]
    folder = runs / model / bj.arm_folder(arm) / stage / "households"
    folder.mkdir(parents=True)
    for sid in sorted(board["scenarios"]):
        scenario, variables = board["scenarios"][sid], board["variables"][sid]
        prompt = bj.household_prompt(scenario, variables, "v2-pilot", model)
        predictions = {v: float(reference[(sid, v)]) for v in variables}
        if wrong and sid == wrong[0]:
            predictions[wrong[1]] = wrong[2]
        record = {
            "scenario_id": sid,
            "model": model,
            "arm": arm,
            "prompt_version": "v2-pilot",
            "benchmark_search_rule": arm == "web",
            "variables": variables,
            "predictions": predictions,
            "explanations": {v: f"{model} on {v}" for v in variables},
            "status": "complete",
            "sent_board_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        }
        (folder / f"{sid}.json").write_text(json.dumps(record))


@pytest.mark.slow
def test_a_batch_payload_flags_what_two_models_get_wrong_and_judges_it_blind(
    household_board, tmp_path
):
    out, _ = household_board
    board = pilot.load_board(out)
    variable = next(
        v
        for v in board["variables"]["mc_000"]
        if v == "federal_income_tax_before_refundable_credits"
    )
    runs = tmp_path / "runs"
    for model in bj.MODELS:
        wrong = ("mc_000", variable, 123456.0) if model != "gemini-4-argon" else None
        _write_arm(runs, board, model, "web", "b0", wrong=wrong)
    payload = bj.build_payload(out, runs, "b0", "web", batch=0)
    assert sorted(payload["scenarios"]) == ["mc_000", "mc_001"]
    assert payload["answerCondition"] == "answering with web search"
    assert [m["model"] for m in payload["modelStats"]] == [
        f"{m}+web" for m in bj.MODELS
    ]
    medicaid = payload["outputDefinitions"].get("head_medicaid_eligible")
    if medicaid is not None:
        assert "PolicyEngine" not in medicaid
    flags = consensus_flags(payload, THREE)
    assert [(f["scenario_id"], f["variable"]) for f in flags] == [("mc_000", variable)]
    (case,) = ra.build_adversary_cases(payload, flags)
    assert case.household_prompt == payload["scenarios"]["mc_000"]["prompt"]["tool"]
    assert "with web search" in ra.render_stage1_prompt(case)

    flags_path = tmp_path / "flags.json"
    flags_path.write_text(json.dumps({"flags": flags}))
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload))
    bj.main(
        [
            "derivations",
            "--board",
            str(out),
            "--payload",
            str(payload_path),
            "--flags",
            str(flags_path),
            "--out-dir",
            str(tmp_path / "annotations"),
        ]
    )
    derivations = ra.load_derivations(tmp_path / "annotations")
    text = derivations[("mc_000", variable)]
    reference = board["reference"].set_index(["scenario_id", "variable"])["value"]
    assert text.startswith(
        f"Output {variable} = {float(reference[('mc_000', variable)]):g}"
    )
    assert "income_tax_before_refundable_credits" in text


@pytest.mark.slow
def test_a_payload_refuses_an_unfinished_batch_a_calculator_arm_and_another_prompt(
    household_board, tmp_path
):
    out, _ = household_board
    board = pilot.load_board(out)
    runs = tmp_path / "runs"
    with pytest.raises(SystemExit, match="only"):
        bj.build_payload(out, runs, "b0", "pe", batch=0)
    for model in bj.MODELS[:2]:
        _write_arm(runs, board, model, "none", "b0")
    with pytest.raises(SystemExit, match="has not finished"):
        bj.build_payload(out, runs, "b0", "none", batch=0)
    _write_arm(runs, board, bj.MODELS[2], "none", "b0")
    record_path = runs / bj.PROMPT_MODEL / "none" / "b0" / "households" / "mc_000.json"
    record = json.loads(record_path.read_text())
    record["sent_board_prompt_sha256"] = "0" * 64
    record_path.write_text(json.dumps(record))
    with pytest.raises(SystemExit, match="rebuilt prompt"):
        bj.build_payload(out, runs, "b0", "none", batch=0)
    with pytest.raises(SystemExit, match="batches 0 to 1"):
        bj.build_payload(out, runs, "b0", "none", batch=2)
    with pytest.raises(SystemExit, match="not both"):
        bj.build_payload(out, runs, "b0", "none", batch=0, scenarios=["mc_000"])


CHEAP = ("claude-haiku-5.5", "gpt-6-luna", "gemini-3.1-flash-lite-preview")


def test_the_prompt_model_is_the_first_on_the_tool_contract():
    assert bj.prompt_model_for(bj.MODELS) == "gpt-6-sol"
    assert bj.prompt_model_for(CHEAP) == "claude-haiku-5.5"
    assert bj.prompt_model_for(("gemini-3.1-flash-lite-preview", "gpt-6-luna")) == (
        "gpt-6-luna"
    )


@pytest.mark.slow
def test_a_payload_judges_any_model_set(household_board, tmp_path):
    out, _ = household_board
    board = pilot.load_board(out)
    runs = tmp_path / "runs"
    variable = "federal_income_tax_before_refundable_credits"
    for model in CHEAP:
        wrong = ("mc_000", variable, 999.0) if model != "gpt-6-luna" else None
        _write_arm(runs, board, model, "none", "b0", wrong=wrong)
    payload = bj.build_payload(out, runs, "b0", "none", batch=0, models=CHEAP)
    assert payload["models"] == list(CHEAP)
    assert [m["model"] for m in payload["modelStats"]] == [f"{m}+none" for m in CHEAP]
    flags = consensus_flags(payload, THREE)
    assert [(f["scenario_id"], f["variable"]) for f in flags] == [("mc_000", variable)]
    assert flags[0]["clusters"][0]["models"] == [
        "claude-haiku-5.5+none",
        "gemini-3.1-flash-lite-preview+none",
    ]
    with pytest.raises(SystemExit, match="at least two models"):
        bj.build_payload(out, runs, "b0", "none", batch=0, models=CHEAP[:1])
