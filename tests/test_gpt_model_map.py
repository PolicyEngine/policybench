"""The local LiteLLM model-map entries of the Responses-API GPT ids.

eval_no_tools registers an entry for each GPT_RESPONSES_MODELS id that
LiteLLM's map lacks. The tests read the entry builder, not litellm.model_cost:
an id the remote map already carries keeps the remote entry, so the map shows
the local entry only for ids the remote map lacks.
"""

import pytest

from policybench.config import GPT_RESPONSES_MODELS
from policybench.eval_no_tools import (
    GPT_RESPONSES_MAX_INPUT_TOKENS,
    _gpt_responses_model_entry,
)

# OpenAI's model page for each id (developers.openai.com/api/docs/models/<id>)
# lists these three figures; GPT-5.6, GPT-6 and GPT-6.1 read 2026-11-20, GPT-6.2
# read 2026-11-17.
DOCUMENTED_CONTEXT_WINDOW = 1_050_000
DOCUMENTED_MAX_INPUT = 922_000
DOCUMENTED_MAX_OUTPUT = 128_000


def test_every_gpt_responses_id_has_an_input_limit():
    assert set(GPT_RESPONSES_MODELS.values()) <= set(GPT_RESPONSES_MAX_INPUT_TOKENS)


@pytest.mark.parametrize("model_id", sorted(GPT_RESPONSES_MODELS.values()))
def test_entry_input_limit_is_the_documented_maximum_input(model_id):
    """max_input_tokens is the input limit OpenAI documents, not the total
    context window, which also holds the output."""
    entry = _gpt_responses_model_entry(model_id)
    assert entry["max_input_tokens"] == DOCUMENTED_MAX_INPUT
    assert entry["max_output_tokens"] == DOCUMENTED_MAX_OUTPUT
    assert entry["max_input_tokens"] != DOCUMENTED_CONTEXT_WINDOW
    assert (
        entry["max_input_tokens"] + entry["max_output_tokens"]
        == DOCUMENTED_CONTEXT_WINDOW
    )


def test_registration_gives_unmapped_ids_the_documented_input_limit(monkeypatch):
    """Each id LiteLLM's map lacks is registered with the builder's entry, so
    its registered input limit is the documented one; an id the map carries
    keeps the map's entry."""
    import litellm

    from policybench import eval_no_tools

    mapped = sorted(GPT_RESPONSES_MODELS.values())[0]
    registered = {}
    monkeypatch.setattr(litellm, "model_cost", {mapped: {"max_input_tokens": 1}})
    monkeypatch.setattr(litellm, "register_model", registered.update)
    eval_no_tools._register_gpt_responses_models()
    assert set(registered) == set(GPT_RESPONSES_MODELS.values()) - {mapped}
    for entry in registered.values():
        assert entry["max_input_tokens"] == DOCUMENTED_MAX_INPUT
