# Hand-corrected reference narratives

`hand_corrected_narratives.json` replaces the narrative writer (claude-haiku-4-5)
for eight outputs the engine upgrade changes, through
`scripts/narratives_upgrade.py --hand-corrected`. Judges' prompts render these
narratives. The independent review of the upgrade machinery (GPT-6.1 Sol,
2026-10-09) found two of the written ones wrong (Ohio 025, Colorado 043). Checking
the other changed outputs' narratives against their engine traces found six more
that misstate a figure or the mechanism behind the change:

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
- **scenario_082 New York.** It applied a 29% rate to $3,000, which gives $870, not
  the $880.61 it stated. The engine's applicable percentage is 29.35%.

Every figure in the corrections is the engine's, from the build's trace or
computed on policyengine-us 2.37.2 with the pinned conventions.

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
