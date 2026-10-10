# Hand-corrected reference narratives

`hand_corrected_narratives.json` replaces the narrative writer (claude-haiku-4-5)
for every output the engine upgrade changes (23 on policyengine-us 2.38.6),
through `scripts/narratives_upgrade.py --hand-corrected`. Judges' prompts render
these narratives. Each text states the value and figures of the final engine's
trace; the notes below give why each departs from the writer's draft.

The first corrections were made on the policyengine-us 2.37.2 rehearsal, where the
upgrade changed eight outputs. The independent review of the upgrade machinery
(GPT-6.1 Sol, 2026-10-09) found two of the written ones wrong (Ohio 025, Colorado
043). Checking the other changed outputs' narratives against their engine traces
found six more that misstate a figure or the mechanism behind the change:

- **scenario_064 federal and state.** They counted the household's $126.22 of
  traditional IRA contributions, but the engine deducts only the head's $108.19.
  A dependent's $18.03 stays off the filers' return: that is policyengine-us #9801,
  the fix that regenerates both outputs. The federal one also gave the $3,200
  child tax credit to one child. It is $2,200 for the child and $500 for each of
  two other dependents.
- **scenario_039 Virginia.** It left out the $25,950 of estate and trust income,
  which federal gross income now includes (#9633). That inclusion regenerates the
  output.
- **scenario_018 Arizona.** It called the $16,100 deduction a mix of the standard
  and itemized deductions, and its AGI arithmetic was off by $50. The $16,100 is
  the standard deduction, which exceeds the itemized $10,637.30.
- **scenario_076 Idaho.** It gave federal AGI as $163,220, not $164,220, so its
  arithmetic did not reach the taxable income it stated.
- **scenario_082 New York.** (On 2.37.2; its final text is in the section below.) It
  applied a 29% rate to $3,000, which gives $870, not the $880.61 it stated. The engine's applicable percentage is about 29.354%, read at
  New York AGI ($117,585.15). The child credit's phase-out reads federal AGI
  ($117,652.65; `ny_ctc_post_2024_phase_out` uses `adjusted_gross_income`).

Every figure in those corrections was the engine's on policyengine-us 2.37.2, from
the build's trace or computed with the pinned conventions.

- **scenario_025 Ohio state income tax.** The written narrative said the engine
  "correctly applied Ohio's rule limiting health insurance premium deductions to
  Medicare-eligible filers without employer coverage". That restriction is the
  defect the exclusion recorded and policyengine-us #10020 removed. The
  correction follows the engine: `oh_insured_unreimbursed_medical_care_expense_amount`
  (line 3 premiums when the filer can get Medicare or an employer-paid plan, plus
  line 4 other medical expenses) and `oh_insured_unreimbursed_medical_care_expenses`
  (the excess over `gov.states.oh.tax.income.deductions.unreimbursed_medical_care_expenses.rate`,
  0.075, of federal AGI). Computed on policyengine-us 2.37.2 with the pinned
  conventions: premiums $6,500, other medical $800, federal AGI $94,925.30,
  deduction $180.60, Ohio AGI $94,744.70, tax $2,116.61 before a $200 credit.
- **scenario_043 Colorado state refundable credits.** The written narrative put
  the $0 down to the household's income. The household meets the refund's
  eligibility rules (`co_sales_tax_refund_eligible` is true), and the refund is $0
  because `gov.states.co.tax.income.credits.sales_tax_refund.in_effect` is false
  for 2026 (C.R.S. 39-22-2003(2): no excess revenues for fiscal year 2025-26), as
  the exclusion record's corrected value said.

Each text states the reference value to the cent, as the narratives script
requires, and names no engine version, so a rebuild on a newer engine can reuse
it while the output's value and trace are unchanged.

## Corrections on the final engine

On the code the final engine carries (checked before its release, then on
policyengine-us 2.38.6 itself, with identical values), 24 outputs change, and Claude
Haiku 4.5 wrote a narrative for each from its trace. An independent reviewer (GPT-6.1
Sol, read-only) then checked every narrative against its trace: each number, each sum,
and each statement of how the value was derived. It found errors in all 17 that had no
hand correction; its report is kept with the release's review records, outside the
repository. The texts in `hand_corrected_narratives.json` for those outputs are its
trace-only rewrites, reworded for readers. A script then checked that every dollar figure
in each is a value in the output's trace or a sum or difference of two of them. One of
the 24, scenario_099 California income tax, then stayed excluded (below), so the release
installs 23. What each drafted narrative got wrong:

- **scenario_003 federal income tax.** It put the $1,582 capital loss inside gross
  income; the loss is an above-the-line deduction that takes $184,872.25 to adjusted
  gross income of $183,290.25.
- **scenario_005 California income tax.** It subtracted the deductions from federal
  adjusted gross income, which does not give the taxable income it stated; they come
  off California AGI ($538,928.31). It also attributed the limitation to conformity
  rules the trace does not show.
- **scenario_008 payroll tax.** It said the fix leaves New Jersey's worker unemployment
  and workforce contributions out of payroll tax. The trace includes both ($102.51 and
  $11.39). It also named a version label and miscounted the household.
- **scenario_015 and scenario_067 local income tax.** scenario_015's subtracted the full
  $4,510 capital loss in gross income, where the calculation deducts $3,000. Both said
  PolicyEngine assigns the county "per its default convention", which the trace cannot
  show; it shows only the county used.
- **scenario_022 California income tax.** It said the charitable deduction applies
  federal limitations. The deduction equals the donations.
- **scenario_039 federal income tax.** Only its description of the filer went beyond the
  trace.
- **scenario_049, scenario_099 and scenario_110 federal income tax.** Each applied the
  main rates to all taxable income; the calculation first takes out the qualified
  dividends and capital gains taxed at preferential rates. scenario_099's also
  multiplied the 32% care credit rate by $12,740 of expenses, where the credit uses the
  $6,000 limit, and subtracted the full capital loss.
- **scenario_082 federal income tax and New York income tax.** Both subtracted the full
  $30,710.82 capital loss in gross income, where a $3,000 loss deduction applies. The
  federal one omitted the $700 charitable deduction its taxable income needs, and the
  New York one stated a household income figure that matches no value in the trace.
- **scenario_082 New York refundable credits.** The IRA fix changes this household's
  adjusted gross income, so the credit is $1,187.55 on the final engine, where it was
  $1,187.61 on policyengine-us 2.37.2. The text states the child credit's phase-out at
  federal AGI ($117,661.12) and the care credit's percentage at New York AGI
  ($117,593.62), about 29.352%.
- **scenario_085 federal income tax.** It gave a threshold as the reason for a $0 net
  investment income tax, which the trace does not show.
- **scenario_099 California income tax.** (Not installed: the output stays excluded.) Its
  draft attributed the $1,256 exemption credit to two children; the trace shows two
  dependents and no split. The release's judge then found that the reference rests on a
  further defect: California does not conform to the federal educator expense deduction
  (FTB Instructions for Schedule CA (540), Section C, line 11), which policyengine-us
  2.38.6 still allows, so the output keeps its record (`excluded_outputs_rechecked`).
- **scenario_110 Ohio income tax.** It said adjusted gross income reflects traditional
  IRA contributions; none appears, and gross income equals AGI.
- **scenario_120 Connecticut income tax.** Only its description of the filer went
  beyond the trace.
