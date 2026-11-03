# PolicyBench development

## Quick start
```bash
pip install -e ".[dev]"
pytest                    # Run tests (see "Testing" for network use)
ruff check .              # Lint
ruff format .             # Format
```

## Architecture
- **One condition**: AI alone (no tools)
- **Ground truth**: policyengine-us Simulation
- **TDD**: Write tests first, then implement

## Key files
- `policybench/config.py` — Models, programs, constants
- `policybench/scenarios.py` — Household scenario generation
- `policybench/ground_truth.py` — PE-US calculations
- `policybench/prompts.py` — Natural language prompt templates
- `policybench/eval_no_tools.py` — LiteLLM-based AI-alone benchmark
- `policybench/model_cards.py` — Per-model serving treatments (contracts, chunking, timeouts)
- `policybench/supervisor.py` — Supervised runs: scenario work queue, budget governor (`policybench run`)
- `policybench/onboard.py` — New-model probe gauntlet (`policybench onboard`)
- `policybench/fold_board.py` — Fold new models into a staged board (`policybench fold-board`)
- `policybench/analysis.py` — Metrics and reporting

## Testing
- Tests mock LiteLLM's model calls, the provider batch adapters and `gh`, and the tests that need policyengine-us run it in-process.
- LiteLLM fetches its model cost map from GitHub when a pytest process imports it, and falls back to its bundled copy if the fetch fails. Set `LITELLM_LOCAL_MODEL_COST_MAP=True` to skip the fetch.
- The `tests/test_scenarios.py` tests download the certified US dataset from Hugging Face.
- `pytest -m "not slow"` to skip slow tests
- `pytest -m "not slow" -n 4 --dist loadfile` to run the same tests on four workers (CI starts one per logical CPU)
- Some tests read git history, so run the suite from a full clone (`git fetch --unshallow`)
- Full benchmark runs are manual and expensive

## Formatting
- Use `ruff format .` before committing
- Use `ruff check . --fix` for auto-fixable lint issues
