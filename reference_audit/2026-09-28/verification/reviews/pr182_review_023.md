# Pre-merge review of release dashboard-data-20260929: scenario_023 head_medicaid_eligible

Reviewed 2026-09-29 (PolicyBench PR #182). Decision recorded 2026-09-29 by the developer: exclude the output as `reference_depends_on_unlisted_input`, with `unlisted_input` = `meets_ssi_disability_criteria`, the input and reason that already exclude this household's SNAP. `clusters.json` (`reconciliations`) records the disposition, and `final_actions.json` lists the exclusion under `audit_exclusions`.

## The flag

- The investigation of cluster `excl_snap_ssi_disability` ended its summary with an out-of-cluster flag: the scored scenario_023 head_medicaid_eligible (1) follows reading B, because `ca_wdp_disability_eligible` reads the broad `is_disabled` flag, and under reading A the law gives 0 (42 CFR 435.540(a)), "so the lead should review it".
- The cluster's independent review agreed (`excl_snap_ssi_disability.md`, fifth problem). Under the stated facts, 2.15.17 plus the conventions puts the head in `WORKING_DISABLED_BUY_IN`, so 408 is the reading-A SNAP value only if "is disabled" confers no disability Medi-Cal, "which contradicts the scored head_medicaid_eligible = 1".
- Nothing in the wave's records disposed of the flag: `final_actions.json` had no entry for the output, `clusters.json` reconciled only scenario_078's federal income tax, and the README was silent. The output stayed scored at 1.0 with impact weight 6,612.94.

## The review's reasoning

- The prompt states only `is_disabled: true`, rendered as "is disabled".
- The head's MAGI is 141.2% of the federal poverty guideline, above the 138% limit for the adult expansion group, so only a disability pathway leads to Medi-Cal. SSI is $0 under either reading.
- California's 250% Working Disabled Program requires the federal definition of disability. The review quoted the Los Angeles County DPSS 250% WDP policy, which policyengine-us cites, as requiring the person to "Meet the federal definition of disability for Social Security disability programs". 42 CFR 435.540(a) reads: "The agency must use the same definition of disability as used under SSI" (eCFR text read 2026-09-29). policyengine-us describes `meets_ssi_disability_criteria` as the SSI disability criteria before the substantial gainful activity screen.
- policyengine-us 2.15.17's `ca_wdp_disability_eligible` returns `is_disabled | is_blind | social_security_disability > 0` and never reads `meets_ssi_disability_criteria`, so flipping that input alone leaves the engine's value at 1 (the table below). The investigator reports the same code in 1.755.4, which is why the 2026-09-05 sweep over that input did not move the output.
- The published SSI case note for the same household says the head's unlisted SSI disability status is false under the prompt instructions, which contradicts a reference of 1 through a disability pathway.
- In the frozen predictions, 22 of 45 models answer 0, 21 answer 1 and 2 give no answer. The case note published the 22 zeros and the 2 missing answers as `llm_error`.
- Rule 4 of `../../README.md` excludes an output whose reference turns on a fact the prompt does not state.

## Computed values

`scripts/probe_023_medicaid.py` on policyengine-us 2.15.17 with `fixes/latest_final.py` (sha256 `dbbdd228…`), the household built by the references' builder (`scripts/sweep.py`). Output: `../probe_023_medicaid.json`.

| System | Reading | head_medicaid_eligible | medicaid_category |
|---|---|---:|---|
| Reference system (`latest_final`) | Stated facts | 1 | WORKING_DISABLED_BUY_IN |
| Reference system | Reading A: does not meet the criteria | 1 | WORKING_DISABLED_BUY_IN |
| Reference system | Reading B: meets the criteria | 1 | SENIOR_OR_DISABLED |
| WDP disability test reading `meets_ssi_disability_criteria` | Stated facts | 0 | NONE |
| WDP disability test reading `meets_ssi_disability_criteria` | Reading A | 0 | NONE |
| WDP disability test reading `meets_ssi_disability_criteria` | Reading B | 1 | SENIOR_OR_DISABLED |

- The reference system reproduces the committed reference, 1.0.
- `medicaid_income_level` is 1.4119 in every run, and SSI is 0.
- Reading A gives 0 and reading B gives 1. The exclusion records `frozen_value` 1.0, the engine's value, and `alternative_value` 0.0.
- Under reading B the engine's category hierarchy places the head in SENIOR_OR_DISABLED ahead of the buy-in; `ca_wdp_eligible` is true there too.

## Effect

- The output leaves scoring for every model. It stays in the payload, marked `scored=false`.
- The exclusion record has 56 entries: 28 engine-defect and 28 unlisted-input. 1,928 of the 1,984 outputs are scored.
- The reference value does not change, so the engine_upgrade revision's `changed` list keeps exactly the engine's changes.
- The staged adjudication record gains the matching entry (`prompt_ambiguity`, `reference_verdict` `unlisted_input`). Triage then rebuilds the case note as it does for every other excluded output.
