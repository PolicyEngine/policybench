# Upstream fixes behind two "record" regenerations

Two release 20261006 engine-defect records land on their own audited corrected
value (alternative_value) on policyengine-us 2.37.2. Nothing else in the engine
has moved them since the records were decided. To name the upstream fix each
regeneration cites, `scripts/probe_cells.py` computed each output with the
pinned conventions (`reference_audit/2026-09-28/fixes/latest_final.py`). It ran
on a checkout of the candidate pull request's merge commit and on its first
parent. Both checkouts used the policyengine-core 3.32.29 environment of the
2.37.2 evidence, run on 2026-10-09.

| Output | Record's corrected value | Parent | Merge | Fix |
|---|---:|---:|---:|---|
| scenario_064 federal_income_tax_before_refundable_credits (r01_ira_compensation) | 4,441.455078 | 4,439.289551 | 4,441.455078 | PolicyEngine/policyengine-us#9801 (merge 1f9d85aa, parent 4732913a), "Keep dependents' above-the-line deductions off the filer's AGI" |
| scenario_064 state_income_tax_before_refundable_credits (r01_ira_compensation) | 4,599.621582 | 4,598.476074 | 4,599.621582 | #9801 |
| scenario_039 state_income_tax_before_refundable_credits (r03_estate_income) | 1,975.798218 | 514.498413 | 1,975.798218 | PolicyEngine/policyengine-us#9633 (merge e77257c4, parent 7968789c), "Include estate and trust income in federal gross income and the NIIT base" |

On the merge commit, each output equals its record's corrected value to the
cent. On the parent it does not. scenario_039's federal output, the record's
other half (estate income counted as qualified business income), waits on
PolicyEngine/policyengine-us#10027.
