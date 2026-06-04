"""LiteLLM disk cache setup for PolicyBench."""

import os

import litellm
from litellm.caching.caching import Cache

# Resolved relative to the process CWD unless POLICYBENCH_CACHE_DIR is set.
# Chunked/resumed runs shell out to subprocesses that inherit the parent CWD, so
# set the env var (to an absolute path) when launching commands from different
# directories — otherwise a run started elsewhere silently gets a fresh cache.
CACHE_DIR = os.environ.get("POLICYBENCH_CACHE_DIR", ".policybench_cache")


def enable_cache(cache_dir: str | None = None):
    """Enable LiteLLM disk caching for reproducible, cost-efficient runs.

    The cache directory defaults to ``cache_dir`` if given, else
    ``$POLICYBENCH_CACHE_DIR``, else ``.policybench_cache`` in the current
    working directory.
    """
    litellm.cache = Cache(type="disk", disk_cache_dir=cache_dir or CACHE_DIR)
