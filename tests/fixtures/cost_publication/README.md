# Synthetic cost accounting fixture

These are invented toy prices and receipts, not provider evidence. No model
response or PolicyEngine computation generated them. The provider and model
names start with `synthetic-`.

The card, captured 2026-09-07 and effective 2026-09-01, charges USD 2 per million
input tokens and USD 4 per million output tokens.

| Calls | Tokens per call | Toy receipt | Normalized estimate |
| --- | --- | --- | --- |
| `sync:1`, `sync:2`, `sync:3` | 1,000 input + 100 output | USD 0.002 each | `(1,000 * 2 + 100 * 4) / 1M = 0.0024` each |
| `sync:replay` | Replays `sync:3` | USD 0 new spend | USD 0 additional estimate; original already counted |
| `batch:toy:u1` | 2,000 input + 300 output | USD 0.0026 | `(2,000 * 2 + 300 * 4) / 1M = 0.0052` |

The sync history contains two failed responses and a successful row repair.
Cache reads/writes are included in input counts; reasoning is included in output
counts. Toy billed spend is `3 * 0.002 + 0.0026 = 0.0086`; normalized spend is
`3 * 0.0024 + 0.0052 = 0.0124`. Legacy recorded totals deliberately carry the
synchronous reconstruction to test that it cannot substitute for billing.

Evidence hashes identify strings such as `not-a-provider-pricecard` and
`toy-receipt:sync:1`, with `synthetic:` references. They are not provider pages
or invoices. A valid synthetic fixture must never pass accounting eligibility
or enable public costs.
