"""Tests for versioned LiteLLM cache setup."""

from unittest.mock import patch

import litellm

from policybench.cache import enable_cache
from policybench.model_cards import PROMPT_CONTRACT_VERSION


def test_enable_cache_namespaces_entries_by_bumped_contract_version(monkeypatch):
    monkeypatch.setattr(litellm, "cache", None)
    fake_cache = object()

    with patch("policybench.cache.Cache", return_value=fake_cache) as cache_class:
        enable_cache("/tmp/policybench-cache")

    assert PROMPT_CONTRACT_VERSION == "2026-08-09-v2-scoring-contract"
    cache_class.assert_called_once_with(
        type="disk",
        disk_cache_dir="/tmp/policybench-cache",
        namespace=f"policybench:{PROMPT_CONTRACT_VERSION}",
    )
    assert litellm.cache is fake_cache
