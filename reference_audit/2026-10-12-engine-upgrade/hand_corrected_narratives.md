# Hand-corrected reference narratives

`hand_corrected_narratives.json` replaces the narrative writer (claude-haiku-4-5)
for every output the 2026-10-12 engine upgrade changes: the nine engine-defect
records policyengine-us 2.41.0 regenerates. It is applied through
`scripts/narratives_upgrade.py --hand-corrected`. Judges' prompts render these
narratives. Each text states the value and figures of the 2.41.0 build's trace
(`reference_traces.json`), and where a text names a rule, the rule is the one in
policyengine-us 2.41.0's code or parameters. Every sum a text states was
recomputed from its figures. Where the cent-rounded figures miss the trace's
total by a cent (scenario_042's taxable income), the text gives the trace's
total and says so.

The writer's drafts misstated the change behind six of the nine, and a figure or
term in the others:

- **scenario_100 federal and state, scenario_119 federal and state (EITC
  deferrals, policyengine-us #10030).** Each draft said the traditional 401(k)
  deferrals count as earned income for the credit. The fix is the opposite:
  elective deferrals are excluded from gross income, so they are not earned
  income for the earned income tax credit or the refundable child tax credit.
  Earned income is wages less the deferrals ($2,055.72 for scenario_100,
  $51,912.80 for scenario_119). The Montana draft also called the $822.29
  federal credit a Montana phase-in; Montana's credit is 20% of the federal
  credit (`gov.states.mt.tax.income.credits.eitc.match`, 0.2 from 2026). The
  scenario_119 federal draft called the child tax credit "constrained by the
  tax liability limitation"; the refundable part is the $4,400.00 credit less
  the $2,310.23 of liability it offsets. The Virginia draft left the $1,560.00
  child and dependent care expense deduction out of its taxable income sum.
- **scenario_007 and scenario_053 Idaho (#10023).** Both called `id_pbf` a
  property tax benefit or credit. It is Idaho's $10.00 permanent building fund
  tax, which adds to the tax. The scenario_007 draft also ran its subtractions
  and AGI in the wrong order.
- **scenario_042 Wisconsin (#10026).** The draft said the property tax credit
  and the retirement income exclusion together brought the tax to zero. The
  output is the tax on the path the filer elects. The exclusion path subtracts
  $24,000.00 of retirement income, the cap for a filer 67 or older, and its tax
  is $0.00. The standard path's tax is $408.70 ($708.70 less the $300.00
  property tax credit). The filer elects the lower one
  (`wi_retirement_income_exclusion_elected`). The draft also put taxable income
  at $18,497.46; it is $19,197.46.
- **scenario_091 Wisconsin (#10026).** The draft's AGI items did not sum to its
  AGI: it left out the $43.28 traditional IRA deduction. It called the 30%
  capital gain subtraction a loss deduction.
- **scenario_099 California (#10032, #10034, #10052).** The draft subtracted
  deductions from federal AGI, not California AGI, so its arithmetic missed the
  $337.50 educator expense addback by that amount. It called the addback a
  conformity adjustment; California does not conform to the federal deduction.
  It also called the $1,256.00 of exemption credits the two dependents'; they
  are the joint filers' and the two dependents'.
