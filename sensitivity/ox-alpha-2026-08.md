# Ox Alpha preview run (August 2026)

`stealth/ox-alpha` is a cloaked model OpenRouter listed on 2026-08-21 with
no maker named, a 1M-token context, and a free window of about a week.
Community fingerprinting points to a Zhipu GLM lineage. Nothing is
confirmed. We ran it through the full benchmark because free previews of
unreleased frontier models are worth measuring while they exist.

This is a preview run beside the board, not a board row. A board row needs
a release date, a named provider, and a model that stays callable for
re-runs. A stealth preview has none of those, and the real model may ship
under its own name later. When it does, it gets onboarded normally, with
this run as its early read.

## Result

Canonical v1 condition: identical whole-scenario prompt, forced answer
tool call, no reasoning parameters, 100 households, 18 outputs.

| | exact | would rank | within 1% | parsed |
|---|---|---|---|---|
| ox-alpha | **84.2** | #4 of 31 | 86.4 | 1,984 / 1,984 |

Only GPT-5.6 Sol (88.7), Kimi K3 (86.2), and GPT-5.6 Luna (84.5) score
higher on the live board. Inference cost was $0 in the free window; the
tool contract passed the gauntlet 3/3 and 16/16 after a thinking-class
completion budget (the 384-token probe budget starved it, the known
reasoning-model trap).

## Per program

Within-$1 rates per output. GLM-5.2, the latest released model in the
suspected lineage, appears for reference only.

| program | Ox Alpha | GLM-5.2 |
|---|---|---|
| local_income_tax | 100.0 | 94.0 |
| person_early_head_start_eligible | 100.0 | 89.5 |
| person_head_start_eligible | 100.0 | 89.5 |
| person_wic_eligible | 100.0 | 92.7 |
| person_medicare_eligible | 99.4 | 89.3 |
| reduced_price_school_meals_eligible | 99.0 | 94.0 |
| self_employment_tax | 99.0 | 91.0 |
| tanf | 99.0 | 94.0 |
| free_school_meals_eligible | 98.0 | 93.0 |
| ssi | 98.0 | 90.0 |
| person_medicaid_eligible | 93.8 | 85.9 |
| person_chip_eligible | 92.7 | 93.2 |
| payroll_tax | 87.0 | 73.0 |
| federal_refundable_credits | 84.0 | 79.0 |
| snap | 79.0 | 76.0 |
| state_refundable_credits | 79.0 | 72.0 |
| federal_income_tax_before_refundable_credits | 63.0 | 43.0 |
| state_income_tax_before_refundable_credits | 55.0 | 45.0 |

On the 20 SNAP cases where the household is owed benefits, Ox Alpha
answers exactly $0 seven times and gets none exact — the same failure
shape as the rest of the board.

## Reproducing

```
python -m policybench.cli run \
  --model ox-alpha \
  --scenario-manifest paper/snapshot/20260501/us_scenarios.csv \
  --run-dir results/local/oxalpha/run \
  --budget-usd 5 --max-workers 4
```

The model card (`openrouter/stealth/ox-alpha`) pins the tool contract, a
600s timeout, and the thinking-class budget. Predictions are attached to
the `dashboard-data-20260817` release as
`preview-ox-alpha-predictions.csv.gz`.
