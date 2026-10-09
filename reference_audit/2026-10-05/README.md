# State income tax withheld in the federal SALT deduction, October 5, 2026

This directory audits how PolicyBench's US references fill the state income tax part of the federal state and local tax (SALT) deduction. It proposes three exclusions and changes no reference. Adopting them changes published scores, so they wait for Max's ruling.

## The mechanism

These files hold for policyengine-us 2.15.17, the version that built the published references, as installed in the reference venv.

- `salt_deduction` takes the smaller of the SALT cap and `salt` (`variables/gov/irs/income/taxable_income/deductions/itemizing/salt_deduction.py`).
- `salt` adds `state_and_local_sales_or_income_tax` and `real_estate_taxes` (`parameters/gov/irs/deductions/itemized/salt_and_real_estate/sources.yaml`).
- `state_and_local_sales_or_income_tax` is the larger of income tax and sales tax. Income tax is `state_withheld_income_tax` plus `local_income_tax`; sales tax is `state_sales_tax` plus `local_sales_tax` (`state_and_local_sales_or_income_tax.py`).
- `state_withheld_income_tax` has no formula of its own. It adds the per-state `*_withheld_income_tax` variables (`parameters/gov/states/household/state_withheld_income_tax.yaml`). Its label reads "state income tax before refundable credits", but each component is a formula on the person's whole federal AGI, not the household's state liability. For example, `ma_withheld_income_tax` is 5% of AGI above the $4,400 single personal exemption, and `ca_withheld_income_tax` and `va_withheld_income_tax` apply the state rate schedule to AGI that includes Social Security both states exempt.

No PolicyBench prompt states state income tax withheld or paid, and the household data never set it. The prompt says to "treat any unlisted numeric input as 0". So the reference rests on an engine estimate of an input the prompt never lists. Under 26 U.S.C. 164(a)(3) and (b)(5), a household deducts the state income tax it paid during the year, or general sales tax instead. The stated facts support two readings, and each gives a reference different from the frozen one:

| Reading | State income tax in SALT |
|---|---|
| Reference | the engine's withholding estimate |
| `liability` | the household pays its 2026 state income tax during 2026: the engine's own state income tax before refundable credits |
| `net` | as `liability`, net of state refundable credits |
| `zero` | none paid ("unlisted numeric input = 0"), so SALT takes general sales tax |

Two engine details shape the `liability` reading:

- Maryland county tax reaches SALT only through `md_withheld_income_tax` (upstream #8888). The reference system's state output leaves it out, so the reading adds it back. Two households carry it, at the Allegany rate the engine assigns an unlisted county: scenario_068 ($834.27) and scenario_078 ($4,358.51).
- NYC tax is in the engine's state aggregate but reaches SALT through `local_income_tax`, so the reading removes it. No household has NYC or other local income tax.

A state's tax can depend on federal tax or on federal SALT, so the input is iterated to a fixed point. Every household converged on the first pass: changing the input never changed a state liability in this set.

## Method

1. **Sweep.** `scripts/sweep_salt_withholding.py` rebuilds every household with `Scenario.to_pe_household` and computes every output on policyengine-us 2.15.17 with `latest_final` (`../2026-09-28/fixes/`), the system that built the references. Its baseline reproduces all 1,928 scored references. It then reruns every household under each reading, feeding the reading in as the tax-unit input `state_withheld_income_tax`.
   - That input feeds SALT and the state formulas that read SALT or withholding: CO, MO, SC, NM, HI, ID, UT, VA and AZ. It also feeds a few benefit-program deductions that no output reads.
   - Montana's federal-tax deduction reads `mt_withheld_income_tax` directly. The only Montana household, scenario_100, has no withholding estimate and no Montana liability.
   - Outputs: `verification/sweep_salt_withholding.csv` (every output under every reading), `verification/sweep_salt_withholding_households.json` (each household's SALT components, itemization, cap and fixed-point trace) and `verification/sweep_salt_withholding.log`.
2. **Side readings.** `scripts/variants.py` computes every other value the records quote, on the same system and households, and writes `verification/variants.json` and `variants.log`:
   - the liability reading with the corrected state liability for households whose state output is an engine-defect exclusion;
   - mandatory employee state payroll contributions added to SALT;
   - no local sales tax;
   - no modeled Medicare Part B premium;
   - Maryland's 24 county rates;
   - scenario_120 under r02's IRA fix.
3. **Propose.** `scripts/propose_exclusions.py` writes `proposed_exclusions.json`. It holds one `reference_depends_on_unlisted_input` record, in the format of the frozen run's `reference_exclusions.json`, for every scored output the `liability` reading moves by more than the $1 exact-match tolerance. Outputs already excluded for another reason are listed with the note text a release should add to their records.
4. **Impact.** `scripts/leaderboard_impact.py` copies the frozen run twice to a scratch directory and never writes the snapshot. It appends the proposed records to one copy and scores both with `python -m policybench.cli analyze`, the command the freeze runs. The unchanged copy must reproduce the published payload's scoring: modelStats except the cost and latency fields the freeze overlays, plus programStats, heatmap, globalWeights and failureModes. It does: every compared value is equal. Outputs: `verification/leaderboard_impact_models.csv`, `leaderboard_impact_programs.csv`, `leaderboard_impact.json` and `leaderboard_impact.log`.
5. **Verify.** Five independent reviewers checked the work in a Claude Code workflow on 2026-10-05, each in its own scratch directory:
   - **Mechanism.** One traced the code path and recomputed the five withholding estimates and the nine federal values for 022, 081 and 114 by hand, all to the cent.
   - **Differential.** One re-implemented the sweep with a different mechanism: per-person state withholding inputs. Its values were bit-identical on all 1,984 outputs.
   - **Adversarial.** One tried to refute the exclusions. It could not, and it found the payroll-contribution defect.
   - **Impact.** One reproduced the impact byte for byte and recomputed the headline through `policybench.analysis` directly.
   - **Completeness.** One found the Part B premium and the county dependence below.

   Their structured reports are in `verification/independent_reviews.json`; their scratch paths are not kept. Every number they raised that the records quote is recomputed by `variants.py` above.

## What moves

Nine of the 100 households itemize. Under every reading, five outputs move by more than $1, all of them federal income tax before refundable credits. No other output moves by even a cent.

| Output | Reference | `liability` | `zero` | Withholding estimate | Engine liability | Status |
|---|---:|---:|---:|---:|---:|---|
| scenario_022 (CA) | 11,113.57 | 11,895.23 | 12,192.29 | 6,058.85 | 2,505.87 | scored; proposed |
| scenario_081 (MA) | 26,932.27 | 26,991.31 | 28,763.81 | 8,484.41 | 8,238.41 | scored; proposed |
| scenario_114 (VA) | 10,729.61 | 11,137.31 | 11,758.09 | 5,367.30 | 3,514.15 | scored; proposed |
| scenario_078 (MD) | 24,164.46 | 24,799.16 | 27,290.70 | 15,791.66 | 11,295.39 | excluded (state and local tax refund) |
| scenario_120 (CT) | 40,416.67* | 40,438.95 | 43,619.93 | 12,010.05 | 11,917.18 | excluded (r02 IRA engine defect) |

\* scenario_120's published reference is 40,021.82, the value its 2026-09-22 record kept. 40,416.67 is its 2.15.17 value.

`net` gives the same values as `liability`, because no affected household has a state refundable credit. In 078 the $40,400 cap binds under the withholding estimate and not under the liability. 078's liability value also depends on the county, which the prompt does not state: $24,705.95 to $25,068.44 across Maryland's 24 county rates.

Under the zero reading, SALT takes general sales tax. That includes the engine's local sales tax component, 20% of the state table amount, which estimates an unlisted locality. Without it, 022's zero-reading value is $12,234.66 and 114's is $11,783.48. The local component moves no reference on its own.

No model is within $1 of the frozen reference on any of the three proposed outputs (0 of 138 rows). Model answers do land on the other readings:

- In scenario_081 the engine's Massachusetts liability, $8,238.41, is itself an engine-defect exclusion (r22, corrected $8,232.90). With the corrected liability the output is $26,992.64. Four models answer within $1 of that: GPT-5.6 Sol ($26,992.59), Claude Opus 5.5 ($26,992.66), and GPT-6 Astra and GPT-6.1 Sol ($26,993.29).
- In scenario_022, Grok 4.7 and Inkling answer $12,192, the zero reading.

## Related engine issues found on the way

- **State payroll contributions are left out of SALT.** policyengine-us 2.15.17 computes mandatory employee state payroll contributions (`employee_state_payroll_tax`) for the payroll tax output, but SALT never reads them. Rev. Rul. 2025-4 (January 15, 2025) treats state paid family and medical leave contributions as deductible state income taxes, and Trujillo v. Commissioner, 68 T.C. 670 (1977), did the same for California SDI. Adding them moves the same federal outputs and no others:
  - 022 (CA SDI $684.26): $10,963.04 under the estimate, $11,744.69 under the liability;
  - 081 (MA paid leave $805.01): $26,739.07 and $26,798.11;
  - 120 (CT paid leave $827.98): $40,217.95 and $40,240.24.

  The proposed and existing records note this. It needs an upstream fix.
- **Medicare Part B premium.** The engine adds a modeled Part B premium ($2,434.80 for 2026) to medical expenses for every Medicare-eligible person, 30 households in all. It assumes enrollment, which the prompt never states, though the prompt's rules say not to infer unlisted expenses or health coverage. With the premium at 0, two outputs move, both in scenario_114:
  - federal: $10,729.61 → $11,265.27 (proposed here for the withholding reason);
  - Virginia state: $3,514.15 → $3,654.15. This one is scored and is **not** in this proposal.

  Under the literal reading (no withholding, no local sales tax, no Part B) the household takes the standard deduction: federal $11,969.80, Virginia $4,127.67. This is a separate unlisted input. Its audit is a follow-up task, so that the same release can carry its record if confirmed.

## Leaderboard impact

The three exclusions leave 1,925 scored outputs per model.

- **Headline exact rate.** Every model's household-impact-weighted exact rate rises by 0.42 to 0.61 points. Every model missed all three outputs, and each carries 0.20 to 0.21 of its household's weight on an equal-household headline. GPT-6 Sol moves from 95.00% to 95.62%.
- **Always-zero baseline.** It moves from 69.98% to 70.40%, so GPT-6 Sol's lead over it goes from 25.02 to 25.22 points.
- **Headline rank.** One rank changes: Claude Sonnet 5.5 (92.65%) passes GPT-6 Luna (92.61%) for fourth. They were 0.016 points apart.
- **Within-1% rank.** Three adjacent pairs swap: GPT-6.1 Sol and Grok 4.7 (#9/#10), GLM-5.3 and Gemini 3.5 Flash Lite (#26/#27), and MiniMax M3 and Claude Opus 4.8 (#39/#40).
- **Bounded-score rank.** Three adjacent pairs swap: GPT-5.5 and GPT-5.6 Terra (13/14), Claude Opus 5 and DeepSeek V4 Flash 0731 (23/24), and MiniMax M3 and Claude Sonnet 5 (42/43).
- **Federal income tax.** Exact match across models rises from 61.6% to 64.0%.

`verification/leaderboard_impact.json` has the full figures.

## What a release adopting the records must also do

The reviewers checked these against the code and tests. They are not done here.

1. **Adjudications.** Add three developer adjudications (`excluded_from_scoring: true`, `adjudicated_failure_source: prompt_ambiguity`) to `annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_adjudications.json`. Without them `scripts/freeze_snapshot.py`'s `reference_exclusions_block` stops the freeze.
2. **Annotation rows.** Relabel the 135 `llm_error` annotation rows on the three outputs to `prompt_ambiguity`, as for every other exclusion (`tests/test_paper_results.py` checks this). Reword the case and row annotations that call the withholding estimate the household's state income tax:
   - 081: "$8,484.41 of Massachusetts income tax";
   - 114: "$5,367.59 state income tax";
   - 022: "about $6,059 of estimated CA income tax".
3. **Superseded regeneration.** Supersede the 2026-09-22 `c_ca_hold_2025` regeneration of scenario_022 federal, which `tests/test_reference_audit.py` expects to stay scored. Extend the record-date rule there for exclusions dated after the wave.
4. **Pinned counts.** Update the counts the tests and documents pin:
   - exclusions 56 → 59, unlisted-input 28 → 31, households 39 → 40;
   - scored outputs per model 1,928 → 1,925;
   - 2.15.17-era records 4 → 7, adjudications 69 → 72;
   - audited rows 7,860 → 7,722, exact-match misses 7,856 → 7,718.
5. **Paper.** Revise the paper:
   - Line ~1041 says Maryland's withholding allowance "reaches federal tax through the state and local tax deduction". Under these records its federal effect falls only on excluded outputs.
   - Add the withholding reading to the unlisted-input list and the sweep narrative.
   - Re-render the abstract and the tables.
6. **Existing notes.** Add the `already_excluded` note text to scenario_078's record, whose note says the SALT cap "binds at every 2026 county rate", and to scenario_120's record.
