# Frozen cost basis and publication validation

Issue [118](https://github.com/PolicyEngine/policybench/issues/118) requires
complete cumulative accounting before restoring public cost comparisons. The
offline validator consumes the existing `.spend.jsonl` ledger and a separate,
versioned cost contract. It does not record calls, alter serving treatments,
fetch responses, recalculate PolicyEngine references, or change the public UI.

## The two cost measures

The v1 metric is `operational_workflow_sync_uncached_v1`: the cost of every
physical attempt in a model's validated workflow for the frozen scenario set,
estimated at one dated snapshot of standard synchronous, uncached token prices.
Initial requests, unsuccessful attempts, retries, row repairs, and explanation
repairs all contribute. Different models may use different validated recipes;
this measures workflow cost and does **not** establish identical-request model
efficiency. Compare rows only within the same complete scenario roster and
normalization date. The report includes the scenario count per model.

| Field | Meaning | Evidence |
| --- | --- | --- |
| `actual_billed_usd` | Actual new spend across retained physical calls | Provider-reported per-call amount or attributable billing export, with receipt reference and SHA256 |
| `normalized_sync_usd` | Estimated cost of the same physical calls under the frozen synchronous pricecard | Complete token usage and explicit inclusion semantics; always marked as an estimate |
| `*_known_subtotal_usd` | Sum over calls with known amounts | Diagnostic only; never fills an unknown total |

Legacy `total_cost_usd`, `reconstructed_cost_usd`, `estimated_cost_usd`, and
`cost_is_estimated` do not establish actual billing. The current ledger can mark
a configured list-price reconstruction as `cost_is_estimated=false`. The report
retains legacy fields for diagnosis and never treats that flag as a receipt.
Provider-reported billing must agree exactly with the ledger field;
billing-export attribution remains an auditable attestation. Contract amounts
use nonnegative decimal strings. Arithmetic uses decimals without rounding model
totals or applying a hidden tolerance.

All input tokens receive the standard input price, including provider cache reads
and writes. All output/reasoning tokens receive the standard output price. The
contract declares whether prompt tokens include cache partitions and whether
completion tokens include reasoning. Every component needs an explicit
nonnegative integer, including zero; missing reasoning or cache usage is unknown.
`total_tokens`, when present, must equal the ledger's raw prompt plus completion
fields. V1 supports linear per-token pricing only. Tiers, separate reasoning
rates, request fees, and other charges need a new supported contract.

Batch transport changes the actual receipt; normalization uses synchronous
rates. An application cache replay adds zero new billed and normalized cost only
when it links to a matching original physical call already counted in this run.
Model, scenario, requested outputs, usage, recipe, and pricecard must match.
Missing original attempt history blocks readiness. Provider prompt caching still
represents a physical call.

## Frozen contract v1

The [JSON schema](../policybench/cost_publication.schema.json) requires every
declared property and rejects additional contract properties. Unknown values use
`null`; omitted fields are schema errors. Schema-valid unknowns remain ineligible.
The existing ledger keeps its open record format; validation checks the types of
fields it consumes.

The contract freezes:

- Run identity, every displayed model, the complete scenario roster, each model's
  independently inventoried call keys, and independently declared model totals.
- History status (`complete`, `unknown`, `unrecoverable`), evidence reference and
  digest, and a reason for unavailable evidence. Model call lists must partition
  the ledger exactly. Accepted predictions cannot prove complete attempt history.
- Recipe identity: provider, requested model ID, response contract, maximum
  outputs per request and completion-token cap, and exact prompt/treatment hashes.
  The treatment artifact must cover sampling, retries, repairs, and budget
  escalation. Observed counts/caps cannot exceed those maxima. This records an
  existing treatment; it does not change one or certify convergence.
- Pricing identity: provider/model, USD, standard synchronous mode, effective
  date, capture date, source reference and captured-source hash, two decimal
  rates, and synthetic/retained evidence kind. All capture dates must equal the
  normalization date; each price must already be effective. A real card requires
  an authoritative provider source captured on that date.
- Per-call ledger hash, recipe/card references, usage semantics, billing receipt
  and provenance, and any application-cache origin.

Recipe and pricecard IDs hash their complete JSON objects. Call bindings hash
the complete ledger object. V1 canonicalization uses
`json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)`
with default ASCII escaping, encoded as UTF-8. Use `content_digest` to generate
SHA256 IDs. These digests freeze content; they do not authenticate sources.
Independent review must verify retained source files against the declared hashes,
inspect receipt attribution, and establish roster/call completeness.

Exact duplicate observations count once. Conflicting observations with the same
call key block validation, even if one looks newer. Use the existing ledger's
upsert/terminal-result recovery before freezing a contract. Batch keys must match
`batch:{batch_id}:{custom_id}`. Strict reads reject missing files, malformed or
truncated lines, duplicate JSON keys, and non-finite values. The live reader's
default recovery behavior remains unchanged.

Each model must use one recipe and one card. Mixed introductory/standard pricing,
snapshot dates, missing model rows, unknown usage/billing, and mismatched totals
block eligibility. Complete calls with unknown billing can still yield a complete
normalized estimate beside a billed subtotal. Incomplete history or missing call
inventory makes both full totals unknown.

## Run the offline checks

The fixture uses **invented toy prices and receipts**, dated 2026-09-07, for
`synthetic-provider`. It makes no claim about actual provider prices or bills.
Four physical calls and one replay yield toy billed spend of USD 0.0086 and a
normalized estimate of USD 0.0124. The fixture README shows the arithmetic.

```bash
uv run --offline python -m policybench.cost_publication \
  --contract tests/fixtures/cost_publication/synthetic.contract.json \
  --ledger tests/fixtures/cost_publication/synthetic.spend.jsonl \
  --json-out /tmp/policybench-cost-report.json \
  --markdown-out /tmp/policybench-cost-report.md
```

Repeat `--ledger` for multiple files. Outputs must be distinct from input
evidence. Reports are deterministic. Exit 0 means retained **accounting**
eligibility; exit 1 means ineligible (including a valid synthetic fixture); exit
2 indicates invalid CLI usage. Exit 0 never authorizes public release.

Audit the committed release without inventing missing provenance:

```bash
uv run --offline python -m policybench.frozen_cost_audit \
  --run-dir paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace \
  --output-dir /tmp/policybench-frozen-cost-audit
```

This writes hashed inventories, an incomplete contract, JSON validation, and a
Markdown report outside the input bundle, and always exits 1. Recorded aggregates
remain diagnostic. Discovered ledgers are listed for a separate contract audit;
their presence alone cannot establish completeness. The command does not
inspect benefit values or read/reprice the prediction CSV. An `unrecoverable`
designation applies to this frozen bundle, not an unsearched original run archive.

## Public eligibility boundary

| Result | Meaning |
| --- | --- |
| `schema_valid` | Structure is valid; unknowns remain allowed |
| `validation_passed` | All accounting checks pass, possibly using synthetic fixtures |
| `accounting_eligible` | All checks pass using retained-evidence attestations |
| `public_costs_available` | Always `false` in v1; remaining issue118 release gates need separate review |

Every report includes `issue118_release_review_required`. Accounting does not
certify the GPT-5.5 rerun, recipe convergence, historical Fable/Grok/Sonnet
provenance, public UI labels and regression tests, or all-model release approval.
No command changes the public payload or app. PR119 owns hiding the legacy cost
surface. PR163 launch survivability and PR159 stability paths remain outside
this work. Issue118 stays open.

## Existing ledger versus issue118

| Requirement | Existing main evidence | New validation boundary |
| --- | --- | --- |
| Cumulative calls | Sync/Batch integration retains stable keys, phases, status, model, scenario, requested variables | Check a separately frozen complete inventory; never rebuild calls from accepted rows |
| Retries and repairs | Sync ordinals and repair phases; Batch job/custom IDs and rounds | Sum every physical call once, including terminal failures |
| Actual versus normalized cost | Provider-reported and reconstructed fields coexist; Batch currently reconstructs synchronous token cost | Require receipts separately from dated normalization |
| Cache/usage provenance | Token/cache fields with nulls; local replay flags | Require token-inclusion semantics and retained replay origin |
| Frozen recipe/pricing | Some budget/provider identity, no complete immutable card/recipe contract | Content-addressed objects and call bindings with explicit unknowns |
| Model reconciliation | Public aggregation uses prediction-row usage summaries | Independently check ledger/model inventories and totals; leave export unchanged |
| Historical release | Frozen payload and usage summary retain aggregates | Hash/classify fields and mark missing attempts unrecoverable from this bundle |

The next integration step is to capture reviewed recipe/card/receipt evidence and
an independent call inventory alongside future runs, then validate an entire
release roster before enabling a public-cost adapter. Historical aggregates alone
cannot satisfy that step.
