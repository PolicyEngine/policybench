# PolicyBench development

## Quick start
```bash
pip install -e ".[dev]"
pytest                    # Run tests (all external calls mocked)
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
- All tests mock external calls (LiteLLM, PE-US API)
- `pytest -m "not slow"` to skip slow tests
- Full benchmark runs are manual and expensive

## Formatting
- Use `ruff format .` before committing
- Use `ruff check . --fix` for auto-fixable lint issues
