# Frozen release cost provenance audit

Audit date: 2026-09-07. Source base: `c7aaffe9bc6f1cf2e0f09fc3114560576c97cf71`.

The retained release contains 39 no-tools model rows and 100 scenarios. It has no
`.spend.jsonl` files. No model passes the new accounting gate: actual billed spend
and normalized synchronous estimates remain unknown. This audit reads existing
payload and usage-summary fields only; it does not generate model responses,
recalculate benefit references, or invent historical attempts.

## Provenance of retained model rows

| Classification | Models | Interpretation |
| --- | ---: | --- |
| Reconstructed prediction rows | 25 | Usage summary has a reconstructed cost field, without a provider-reported subtotal |
| Provider-reported prediction rows | 8 | Usage summary has a provider-reported cost field, without a reconstructed subtotal |
| Mixed prediction-row cost fields | 3 | Both provider-reported and reconstructed subtotals appear |
| Aggregate only | 3 | Payload carries a cost, while the usage summary has no recorded cost total |

These are classifications of retained aggregate fields, not counts of physical
calls or independently verified provider bills. In particular, a provider-reported
subtotal over accepted prediction rows cannot establish complete retry spend.

The aggregate-only rows are `claude-fable-5`, `gemini-3.6-flash`, and
`grok-build-0.1`. The `claude-sonnet-5` row has reconstructed prediction-row cost
and estimated-cost flags, but no frozen standard/introductory pricecard provenance.
This audit does not select a retrospective price or replace any recorded total.

## Missing evidence and eligibility

All 39 rows lack an attached v1 publication contract. The audit records unknown
provider model identity, recipe and pricecard bindings, physical request counts,
actual billed amounts, and normalized synchronous totals. Attempt history is
unrecoverable **from this frozen bundle**; contemporaneous ledgers in other run
directories have not been assessed. Repricing accepted rows cannot fill this gap.

The generated contract is schema-valid and explicitly incomplete. Validation and
accounting eligibility both fail, and `public_costs_available` remains `false`.
No public payload, serving recipe, historical aggregate, or launch/stability code
changes as a result of this report. Existing issue118 release requirements and
PR119 visibility work remain separate.

## Exact source artifacts

| Path within the frozen run | SHA256 |
| --- | --- |
| `data.json.gz` | `2cce2598dbf9f33511f31d944221a7fc27f69b487a56c59e2c17e77d4ba5ad1f` |
| `analysis/usage_summary.csv` | `458eae34cb84cf3c11c52437612f12d659baa960857dc93a379e602422448641` |

Run directory:
`paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace`.

Reproduce the inventory, incomplete contract, JSON validation, and detailed report
with the [offline audit command](cost_publication.md#run-the-offline-checks).
The tests assert the 39-model roster, 100-scenario scope, source hashes, and
unavailable-cost boundary. The synthetic validator fixture separately covers
successful and failed attempts, retries, repairs, application/provider caches,
Batch, duplicates, unknown usage, and mixed pricing without any provider calls.

The next step is independent review of the frozen contract, then capture of
complete contemporaneous accounting evidence for a future release. This report
does not close issue118 or authorize a benchmark refresh.
