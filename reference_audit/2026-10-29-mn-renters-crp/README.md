# Minnesota renter's credit: the Certificate of Rent Paid input

The GPT-6.1 Terra release's second review (2026-10-29) found that scenario_122's scored Minnesota `state_refundable_credits` reference of $0 rests on an input no prompt states. This audit traces that output and checks every other Minnesota output for the same dependence.

## What the engine does

- `mn_renters_credit_eligible` requires `mn_renters_credit_qualifying_crp`, a boolean tax-unit input with `default_value = False` in policyengine-us 2.41.0 and 2.60.0. The variable cites Minn. Stat. 290.0693, the Department of Revenue's CRP instructions and Form M1RENT.
- The certified household data never carried the input, and the 2026-09-28 conventions (`reference_audit/2026-09-28/fixes/latest_final.py`) leave it unset. Every reference build since has computed the renter's credit with no CRP.
- Minn. Stat. 290.0693 subd. 4 requires the owner or managing agent of a rented homestead to furnish a CRP to a renter on December 31.

## Scenario_122

`scripts/trace_122.py` traces the renter's credit on the installed engine (`verification/trace_122_2_60_0.json` on 2.60.0, `trace_122_2_41_0.json` on 2.41.0). Both engines agree:

- renter's credit household income: $65,346.18, under 2026's $79,330 first zero threshold;
- rent constituting property taxes: $4,800;
- as built: not eligible, so the credit and `mn_refundable_credits` are $0;
- with a qualifying CRP: eligible, with a credit of $1,921.

The prompt lists "pre-subsidy rent: $28,235" and no CRP. It tells models to treat an unlisted boolean as false and not to infer unlisted facts.

## Every Minnesota output

`scripts/sweep_crp.py` recomputes each output of the two Minnesota households as built and with the CRP set on every tax unit. Against the 2026-10-22 build on 2.60.0 (`verification/crp_sweep.json`) and against release 20261014 on 2.41.0 (`verification/crp_sweep_2_41_0.json`), the as-built pass reproduces every scored reference, and the CRP moves scenario_122's `state_refundable_credits` alone.

## The ruling

The output stays scored in this release (`docs/terra/spec.json`, ruling `crp`). The exclusion rule would remove an output whose reference rests on an unstated input, while the prompt's instruction for unlisted booleans gives the reference's reading. Max's d2180 decides it for the next release.

## Rerunning

From the repository root, with `PYTHONPATH` at the root:

```bash
.venv/bin/python reference_audit/2026-10-29-mn-renters-crp/scripts/sweep_crp.py reference_audit/2026-10-29-mn-renters-crp/verification/crp_sweep.json
```

With policyengine-us 2.41.0 installed, `--against base` checks release 20261014's references instead. `trace_122.py OUT_JSON` writes the trace.
