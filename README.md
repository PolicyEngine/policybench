# PolicyBench

How well can frontier models calculate tax and benefit outcomes without tools?

PolicyBench measures how well frontier AI models estimate US tax/benefit values for specific households using pure reasoning alone.

Benchmark scenarios are sampled from real households in the Enhanced CPS and then evaluated under 2025 policy rules with PolicyEngine-US. That gives the benchmark more realistic joint distributions of age, income, filing status, and family composition than independent synthetic sampling.

## Condition

1. **AI alone**: Models estimate tax/benefit values using only their training knowledge

## Models tested

- Claude Opus 4.6
- Claude Sonnet 4.6
- GPT-5.4
- Gemini 3.1 Pro Preview

## Programs evaluated

Federal tax, EITC, CTC, SNAP, SSI, Medicaid eligibility, state income tax, and related core household policy outputs.

## Quick start

```bash
pip install -e ".[dev]"
pytest  # Run tests (mocked, no API calls)
```

## Benchmark run

```bash
# Generate ground truth for 100 sampled CPS households
policybench ground-truth -n 100 --seed 42

# Run AI-alone evaluations on the same sampled households
policybench eval-no-tools -n 100 --seed 42

# Analyze results and export production artifacts
policybench analyze --output-dir results/analysis
```

## Repeated runs

```bash
# Optional: run the same benchmark multiple times on the same sampled households
policybench eval-no-tools-repeated -n 100 --seed 42 --repeats 3 -o results/no_tools/runs

# Analyze the canonical point estimate plus across-run stability
policybench analyze --runs-dir results/no_tools/runs --output-dir results/analysis
```
