# Louisiana's 2026 standard deduction, October 5, 2026

This directory audits the 2026 Louisiana standard deduction behind two scored references in release `dashboard-data-20260930`. It changes no reference. Max ruled to keep both at the $12,835 deduction. Release `dashboard-data-20261006` ships the wording-only case-note rewrites below. The proposed benchmark-card and paper convention sentence remains held under d994.

**Update, d994 (ruled 2026-10-06, after this release was built).** Max kept the published-amounts convention as written, so the held sentence is not adopted and Idaho's scenario_076, SNAP's scenario_008, scenario_038 and scenario_109, and Maryland's scenario_068 keep their references. He also ruled to exclude both Louisiana references from scoring, because no Louisiana publication stated the $12,835 deduction before the freeze. Release `dashboard-data-20261006` still scores both at $12,835; the exclusions ship in the release after it. Version 2's prompt states indexed amounts.

| Output | Reference | Models exact |
|---|---:|---:|
| scenario_051 state income tax before refundable credits (single, Louisiana AGI $40,180) | $820.35 | 0 of 46 |
| scenario_077 state income tax before refundable credits (single, Louisiana AGI $23,006.18) | $305.14 | 0 of 46 |

Both references are 3% of Louisiana AGI less a $12,835 standard deduction. The five models with the highest exact-match rates answer $830.40 and $315.18, which use 2025's $12,500.

## What the law and Louisiana published

- **Statute.** La. R.S. 47:294(A) sets $12,500 for single and separate filers for 2025, and 200% of that for the other statuses. 294(B): from January 1, 2026, the prior year's amount is multiplied by "the percentage increase in the [CPI-U] ... for the previous calendar year". It sets no rounding rule and gives the Department of Revenue no duty to publish the amount. Act 11 of the 2024 Third Extraordinary Session enacted it; no later act amended it. The Constitution (Art. III, §2(A)(3)(b)) barred deduction bills in the 2026 regular session.
- **CPI-U** (BLS series CUUR0000SA0). December 2024 315.605, December 2025 324.054: +2.677%, released 2026-01-13. The 2025 annual average over 2024's is +2.631%. September 2024 to September 2025 is +3.013%.
- **Withholding (before the freeze).** The Department of Revenue published $12,875 single and separate, $25,750 for the other statuses, as the amounts it used in its 2026 withholding tables. That is $12,500 × 1.03, from the CPI-U data available on December 1, 2025. It appears in:
  - the R-1306 and R-1210 employer formulas (effective January 2026);
  - LAC 61:I.1501's Emergency Rule (signed and posted 2025-12-23, effective 2026-01-01; Louisiana Register 2026-01-20, p. 13, 2601#014);
  - Revenue Information Bulletin 26-005 (2026-01-12);
  - the Notice of Intent (2026-02-20, pp. 308-317, 2602#031; repromulgated 2026-03-20, p. 422);
  - the Rule (2026-05-20, LR 52:749, 2605#012).

  The rule documents and RIB 26-005 each say the amounts allowed on 2026 returns may differ once calendar-2025 CPI-U is released in January 2026. The R-1306 and R-1210 formulas carry the figure without that caveat.
- **Estimated tax (before the freeze).** The worksheet in the 2026 Form IT-540ESi instructions (created 2025-12-03; a Wayback capture of 2026-04-12 is byte-identical) gives the same $12,875 as the "Louisiana estimated standard deduction". Maryland's 2026 estimated-tax worksheet, by contrast, carried its 2025 amount.
- **Legislative Fiscal Office (before the freeze).** In the Notice of Intent's fiscal statement (Louisiana Register, 2026-02-20, p. 317), the LFO reads the statute as December to December, about 2.68%. It says the withholding deduction exceeds the deduction taxpayers will receive on 2026 returns. $12,500 × 1.0268 = $12,835.00.
- **The Department's indexing method (before the freeze).** In the Louisiana Register of 2026-06-20 (p. 1050, 2606#052; Wayback capture 2026-06-23, byte-identical), the Department's Notice of Intent on LAC 61:I.1311 puts the 2026 retirement income exemption at $12,324: $12,000 × 1.027. R.S. 47:44.1 indexes that exemption in the same words as 294(B). The same 2.7% on $12,500 gives $12,837.50.
- **The 2026 return amount (after the freeze).** Revenue Information Bulletin 26-019, dated 2026-09-28 (served Last-Modified 2026-09-29), sets $12,838 single and separate and $25,676 for the other statuses: $12,500 × the 2.7% CPI-U multiplier, with the joint amount twice the rounded single one. BLS's January 13 release gives the December-to-December change as 2.7%. The bulletin names no comparison months, and a RIB is not binding. The 2026 IT-540 instructions are not yet posted. https://dam.ldr.la.gov/lawspolicies/RIB%2026-019.pdf

policyengine-us carries $12,835 and $25,670 as explicit 2026 entries in every version from the one that built the frozen references (1.755.4) through the reference engine (2.15.17). PolicyEngine/policyengine-us#8411 added them on 2026-05-24: $12,500 × 324.054 / 315.605, rounded to the dollar. No Louisiana publication states $12,835.

## Does the convention cover $12,835?

The benchmark card's convention reads: "Where policyengine-us projects a 2026 amount with a price index, or carries one published after the freeze, the reference takes the amount published before the freeze or, where none was, the last one published."

$12,835 is neither. It was computed from CPI-U values BLS had published, under the statute's formula, and entered as an explicit 2026 value; nothing forecast it. The September 22 projection screen (`../2026-09-22/fixes/r18_hold_all_projections.py`) finds projected values by diffing the uprated parameter tree against the tree with uprating disabled. An explicit entry is in both trees, so the screen could not flag it, and no convention module touches Louisiana.

So the governing rule is the card's first sentence: "A scored reference follows from the stated facts and from law published before PolicyBench froze the references on 2026-07-03." $12,835 follows from R.S. 47:294(B) and the January 13 CPI release. The LFO's published 2.68% gives it exactly. The Department of Revenue's own amount, $12,838, published after the freeze by the same method, moves each output by $0.09.

The record's precedents on withholding publications run both ways:

- Michigan's 2026 personal exemption came from Treasury's Form 446 withholding guide, and Missouri's 2026 brackets from its withholding formula. Wisconsin's amounts came from its 1-ES estimated-tax instructions.
- Maryland's withholding guide limited its $3,400 to the percentage withholding method. That amount fed only the engine's withholding estimate, and the return deduction was held at 2025's $3,350.

Louisiana's withholding and estimated-tax amount sits with Maryland's: every notice that states it says the return amount will differ, and RIB 26-019 shows it does. Apart from SNAP's FY2027 figures, which USDA published after the freeze, every 2026 value the nine convention modules change on 2.15.17 replaces an uprated projection. No convention overrides an explicit engine entry that encodes a computation from pre-freeze data.

One gap remains. Once policyengine-us encodes RIB 26-019's $12,838, the engine "carries one published after the freeze". The convention's letter would then send the reference to the amount published before the freeze, $12,875, or the last one published, $12,500. Both are further from Louisiana's 2026 law than either $12,835 or $12,838. The wording below closes that gap.

## Options

Values are policyengine-us 2.15.17 with `latest_final` (the system that built the references) and the Louisiana amounts replaced (`verification/sweep_la_standard_deduction.log`). Under every candidate, the sweep moves these two outputs and no other of the 1,984. Exact-match counts use the $1 tolerance on the release's 46 models (`verification/leaderboard_impact.json`).

| Option | Deduction (single) | scenario_051 | scenario_077 | Models exact (051 / 077) | Headline effect |
|---|---:|---:|---:|---:|---|
| **Keep (recommended)** | $12,835 | $820.35 | $305.14 | 0 / 0 | none |
| Louisiana's 2026 return amount (RIB 26-019, after the freeze), for comparison | $12,838 | $820.26 | $305.05 | 0 / 0 | exact match unchanged; bounded scores move by under 0.0001 points |
| Regenerate with the amount published before the freeze | $12,875 | $819.15 | $303.94 | 0 / 1 (GPT-6 Astra) | GPT-6 Astra +0.06 points; no rank changes |
| Regenerate with the last return amount published (2025) | $12,500 | $830.40 | $315.19 | 21 / 19 | up to +0.13 points; Gemini 3.6 Flash and 3.7 Flash swap exact ranks 24 and 25 |
| Exclude both outputs | n/a | not scored | not scored | n/a | 1,926 scored outputs; the same exact-rank swap, two bounded-score swaps (ranks 16/17 and 35/36) |

Every calendar-year reading of 294(B) lands within the $1 tolerance of both references at any rounding up to $50: December to December, the annual-average change, and the 2.7% LDR applied. The two lines in the table below the recommendation:

- **$12,875** was a withholding and estimated-tax amount. The Department said its return amount would differ, and RIB 26-019 shows it does. Regenerating with it would score models against a figure Louisiana never adopted for 2026 returns.
- **$12,500** is the 2025 amount. Every 2026 source supersedes it: the statute, every 2026 publication by the Department, and the LFO.

Neither exclusion basis applies. The reference turns on no input the prompt omits, and the engine applies the law correctly on the stated facts. The readings the law allows agree within tolerance.

## Recommendation

Keep both references. The original proposal below separated two documentation changes. Release `dashboard-data-20261006` ships only the case-note rewrites in item 2; item 1 remains held under d994.

1. **Benchmark card and paper — HELD (d994).** The proposed replacement for the convention's second sentence was:

   > Where a 2026 amount rests on a price-index projection, or on an index value or announcement published after the freeze, the reference takes the amount published before the freeze or, where none was, the last one published. Where a statute fixes a 2026 amount from index values published before the freeze, the reference applies the statute, whenever the government announces the result. Louisiana's 2026 standard deduction is $12,500 increased by the calendar-2025 CPI-U change (R.S. 47:294(B)); the December 2025 index, released 2026-01-13, gives $12,835, and the $12,838 the Department of Revenue announced on 2026-09-28 moves neither reference by more than $0.09. A withholding or estimated-tax amount the government labels provisional sets no return amount.

   Without the second sentence, the convention's letter misfires once policyengine-us encodes RIB 26-019: the engine would then carry an amount published after the freeze, and the reference would fall back to $12,875 or $12,500.

   The same sentence bears on the record's other holds. Maryland's 2026 return deduction is indexed under Tax-General §10-217(c) through IRC §1(f)(3), whose index month for 2026 is August 2025 (BLS release 2025-09-11; `../2026-09-22/verification/v5b_projection_mn_md_mi_mo_il.md`). It was held at 2025's $3,350 because no 2026 return amount was published before the freeze; that hold moves scenario_068's state income tax by $2.375. Under the sentence above, Maryland's amount would come from its statute too. Whether any Idaho or Michigan hold is in the same position is unchecked. Adopting the sentence therefore means re-examining those holds in the release that carries it. Keeping the convention's current letter instead leaves Louisiana unchanged today (its $12,835 is no projection) and defers the question until policyengine-us encodes $12,838.

   The subsequent re-examination found that adopting this wording would change five scored references: scenario_076's Idaho income tax, SNAP for scenario_008, scenario_038 and scenario_109, and scenario_068's Maryland income tax under the IRS reading. Those changes are held under d994. The existing benchmark-card and paper convention remains in force for this release.
2. **Case notes for the two outputs.** Replace "inflation-indexed ... $12,835" with the sourced chain:

   > R.S. 47:294(B) multiplies 2025's $12,500 by the CPI-U increase for calendar 2025. The December 2025 index, released January 13, 2026, puts that at 2.68% (the Legislative Fiscal Office's figure in the Louisiana Register of February 20, 2026), which gives $12,835. Before the freeze the Department of Revenue applied 2.7% to the retirement exemption, which the same words index (Louisiana Register, June 20, 2026); on September 28, 2026 it set the standard deduction at $12,838 the same way (RIB 26-019). That gives $820.26 (scenario_051) and $305.05 (scenario_077), within the tolerance. The $12,875 in the Department's 2026 withholding tables and estimated-tax worksheet was a provisional amount from CPI-U data available on December 1, 2025.

   For scenario_077, record that GPT-6 Astra's $303.93 used that withholding amount.

If Max rules instead that the convention takes the amount published before the freeze, `fixes/latest_c_la_published_2026.py` applies it. `fixes/latest_final_la.py` composes it with `latest_final`, and `verification/verify_convention_module.json` shows the composition reproduces the sweep's `ldr_published` column on all 1,984 outputs.

## Method

1. **Sweep.** `scripts/sweep_la_standard_deduction.py` rebuilds every household with `Scenario.to_pe_household` and computes every output on policyengine-us 2.15.17 with `latest_final`. Its baseline reproduces all 1,928 scored references. It then reruns every household with the Louisiana 2026 amounts set to each candidate, joint at 200%. Outputs: `verification/sweep_la_standard_deduction.csv`, `verification/sweep_la_households.json` (each Louisiana household's AGI, deduction, taxable income and tax under each candidate) and the log.
2. **Score.** `scripts/leaderboard_impact.py` copies the frozen run to scratch directories and never writes the snapshot. For each option it rewrites the two reference values (and the copy's reference digest) or appends the two outputs to the exclusion record. It scores each copy with `python -m policybench.cli analyze`, the command the freeze runs. The unchanged copy reproduces the published payload's scoring field for field. Outputs: `verification/leaderboard_impact.json`, `leaderboard_impact_models.csv` and the log.
3. **Module check.** `scripts/verify_convention_module.py` recomputes all 1,984 outputs with `fixes/latest_final_la.py` and compares each with the sweep's `ldr_published` column; they agree on every output. policyengine-us applies a reform set twice (before uprating and again with its structural reforms), so the module's guard accepts the engine's value or its own.
4. **Tests.** `tests/test_la_standard_deduction_audit.py` checks these records without loading the engine:
   - the baseline matches every scored reference, and the candidates move only the two outputs;
   - every Louisiana household's engine tax equals 3% of Louisiana AGI less the candidate deduction;
   - between any two candidates, each output moves by exactly 3% of the deduction change;
   - the analyze CLI moves exact match for exactly the models a $1-tolerance count says it should.

5. **Retirement exemption.** policyengine-us 2.15.17 holds the R.S. 47:44.1 exemption for filers 65 and older at $12,000 for 2026. The Department published $12,324 before the freeze (Louisiana Register, 2026-06-20). `scripts/check_retirement_exemption.py` recomputes all 1,984 outputs with `latest_final` and the 2026 cap at $12,324: no output changes (`verification/check_retirement_exemption.json`).

Louisiana's withholding proxy (`la_withheld_income_tax`) subtracts the federal standard deduction, so the Louisiana amount does not reach the federal SALT deduction. The three other Louisiana households (038, 057, 074) have Louisiana AGI below the deduction under every candidate.

Engine: `results/local/adds202609/triage/.venv-pe21517` (policyengine-us 2.15.17).
