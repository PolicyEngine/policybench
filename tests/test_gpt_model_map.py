"""The local LiteLLM model-map entries of the Responses-API GPT ids.

eval_no_tools registers an entry for each GPT_RESPONSES_MODELS id that
LiteLLM's map lacks when it is imported. An id the remote map already carries
keeps the remote entry, so in the test process the map shows the local entry
only for ids the remote map lacks. The tests therefore read the entry builder,
the registrar over a stubbed map, and a fresh interpreter that removes every id
from LiteLLM's bundled map before it imports eval_no_tools.
"""

import json
import os
import subprocess
import sys

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


def test_import_registers_each_missing_id_with_the_documented_input_limit():
    """Importing eval_no_tools registers every id LiteLLM's map lacks. A fresh
    interpreter loads LiteLLM's bundled map, removes all the ids from it and
    then imports eval_no_tools; each id then carries the documented input
    limit."""
    ids = sorted(GPT_RESPONSES_MODELS.values())
    script = (
        "import json, sys\n"
        "import litellm\n"
        "ids = json.loads(sys.argv[1])\n"
        "for model_id in ids:\n"
        "    litellm.model_cost.pop(model_id, None)\n"
        "import policybench.eval_no_tools\n"
        "limits = {m: litellm.model_cost[m]['max_input_tokens'] for m in ids}\n"
        "print(json.dumps(limits))\n"
    )
    shown = subprocess.run(
        [sys.executable, "-c", script, json.dumps(ids)],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "LITELLM_LOCAL_MODEL_COST_MAP": "True"},
    )
    limits = json.loads(shown.stdout.strip().splitlines()[-1])
    assert limits == dict.fromkeys(ids, DOCUMENTED_MAX_INPUT)
