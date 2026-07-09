"""Locks every roster model's serving treatment.

The model-card registry replaced scattered per-model tuples; this table is
the single place that records what each model's treatment IS. A failure here
means a card or heuristic changed a live model's treatment — fine if
deliberate, but it must show up in the diff of this file too.
"""

import pytest

from policybench.config import MODELS
from policybench.eval_no_tools import (
    _answer_contract_for_model,
    _completion_controls,
    _request_timeout_seconds,
    _required_explanation_chunk_size,
)
from policybench.model_cards import card_for

# model_id -> (contract, chunk_size, timeout_s, budget_for_16_vars_with_expl)
EXPECTED = {
    "gpt-5.6-sol": ("tool", None, 300, 16_384),
    "gpt-5.6-terra": ("tool", None, 300, 16_384),
    "gpt-5.6-luna": ("tool", None, 300, 16_384),
    "gpt-5.5": ("tool", 3, 60, 16_384),
    "claude-fable-5": ("tool", 1, 300, 16_384),
    "claude-sonnet-5": ("tool", 1, 300, 16_384),
    "claude-opus-4-8": ("tool", 1, 120, 4_096),
    "claude-opus-4-7": ("tool", 1, 120, 4_096),
    "claude-sonnet-4-6": ("tool", 1, 120, 4_096),
    "claude-haiku-4-5-20251001": ("tool", 1, 120, 4_096),
    "gemini/gemini-3.1-pro-preview": ("json", None, 120, 16_384),
    "gemini/gemini-3-flash-preview": ("json", None, 120, 16_384),
    "gemini/gemini-3.5-flash": ("json", None, 120, 16_384),
    "gemini/gemini-3.1-flash-lite-preview": ("json", None, 120, 16_384),
    "gpt-5.4-mini": ("tool", None, 20, 4_096),
    "gpt-5.4-nano": ("tool", None, 20, 4_096),
    "xai/grok-4.3": ("tool", None, 420, 4_096),
    "xai/grok-build-0.1": ("tool", None, 420, 4_096),
    "deepseek/deepseek-v4-pro": ("json", None, 300, 16_384),
    "deepseek/deepseek-v4-flash": ("json", None, 300, 16_384),
    "openrouter/moonshotai/kimi-k2.6": ("json", 3, 600, 16_384),
    "openrouter/z-ai/glm-5.2": ("json", 3, 300, 16_384),
    "openrouter/minimax/minimax-m3": ("tool", None, 300, 16_384),
    "openrouter/qwen/qwen3.7-max": ("json", 3, 600, 16_384),
}


def _budget(model_id: str) -> int:
    controls = _completion_controls(
        model_id, include_explanations=True, variables=[f"v{i}" for i in range(16)]
    )
    return (
        controls.get("max_completion_tokens")
        or controls.get("max_tokens")
        or controls.get("max_output_tokens")
    )


def test_every_roster_model_has_an_expected_treatment():
    missing = set(MODELS.values()) - set(EXPECTED)
    assert not missing, f"add treatments for: {sorted(missing)}"


@pytest.mark.parametrize("model_id", sorted(EXPECTED))
def test_treatment_locked(model_id):
    contract, chunk, timeout, budget = EXPECTED[model_id]
    assert _answer_contract_for_model(model_id) == contract
    assert _required_explanation_chunk_size(model_id, True) == chunk
    assert _request_timeout_seconds(model_id) == timeout
    assert _budget(model_id) == budget


def test_no_chunking_when_explanations_off():
    for model_id in EXPECTED:
        assert _required_explanation_chunk_size(model_id, False) is None


@pytest.mark.parametrize(
    ("model_id", "expected_cost"),
    [
        ("gpt-5.6-sol", 0.09),
        ("gpt-5.6-terra", 0.039),
        ("gpt-5.6-luna", 0.019),
    ],
)
def test_gpt_56_cards_record_measured_full_run_cost(model_id, expected_cost):
    assert card_for(model_id).expected_cost_per_scenario_usd == expected_cost
