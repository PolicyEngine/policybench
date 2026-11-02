# Optional employer pass-through in the payroll tax references, October 5, 2026

This directory audits the state part of PolicyBench's US `payroll_tax` references in release `dashboard-data-20260930`. Four scored references count an employee share of a state paid-leave or disability premium that the law lets the employer deduct but does not require. The directory proposes two alternative records for those four outputs, excluding them or regenerating them, and changes no reference. Either one changes published scores, so they wait for Max's ruling (cos decision d972).

## Recommendation

Exclude the four outputs (scenario_032 MN, scenario_043 CO, scenario_081 MA, scenario_082 NY) from scoring in the next release, with `proposed_exclusions.json`. Then state in the payroll output's definition how these shares count, so a fresh run can score such households again; until then the board has no scored test of the line between mandatory and optional employee shares.

- **Keep fails the repo's test.** A scored reference must follow from the stated facts under the law (2026-09-22 rule 1). All eight reviews of these four programs find that the premium is the employer's and that the law requires no amount of the employee: the employee pays only what the employer chooses to deduct, from $0 up to a cap. The frozen references count the cap. policyengine-us states that assumption for Minnesota and Massachusetts ("assuming the employer withholds the maximum permitted employee share"), and the prompt never states the employer's choice. The judges who annotated the 149 wrong answers on these outputs flagged no reference, but they were not asked to research the deduction law.
- **The reference turns on a definition the prompt does not settle.** "Mandatory employee state payroll taxes" has two defensible readings here. One is the amount the law requires of the employee whatever the employer does: $0, the regenerated value. The other is the employee share the statute sets, withheld unless the employer elects to pay it: the frozen value. The statutes frame the employer's choice both ways. Colorado treats an employer that deducts less as having "elected to pay" the rest; Minnesota has employees pay "the remaining portion, if any" above the employer's floor; New York says every employee "shall contribute ... to the extent and in the manner herein provided" and then only authorizes collection. The prompt's default for unlisted facts (treat them as false) cannot choose between the readings, because each statute frames a different act as the choice. A reference that turns on "an input or definition the prompt never states" is excluded (2026-09-22 rule 4; 2026-09-28 rule 4). The closest precedents were excluded under the same reason code: r24, who paid for the coverage behind listed disability benefits, an employer-arrangement fact; r25, whether the federal output includes the net investment income tax, a definition question; and r14, an unlisted 40 weekly hours, where the audit excluded rather than apply the zero default.
- **Regenerate is the alternative if Max reads "mandatory" strictly.** On that reading the frozen values are too high, and the regenerated value is the only one that no caveat in the law record moves: Acts 2026 c. 101, private plans, collective agreements and employer size each change the cap, never the $0 floor. `proposed_regenerations.json` is ready for that ruling. The Maryland output-scope adapter (2026-09-28 rule 3) is the form it would take, but not a precedent that decides the case: there the definition was explicit ("excluding local income ... taxes") and the adapter undid an engine change made after the freeze, while here the definition is the contested part and regeneration would change values that have stood since the first run.

Board and model effects are not criteria in the rules, so they do not decide this; both options' effects are reported below.

## How the reference is built

These facts hold for policyengine-us 2.15.17, as installed in the reference venv, plus `latest_final`, the system that built the published references.

- `payroll_tax` is `spm_unit_payroll_tax` (`policybench/benchmark_specs.json`), which sums `employee_payroll_tax` over the SPM unit's tax units (`variables/household/expense/tax/spm_unit_payroll_tax.py`).
- `employee_payroll_tax` adds employee Social Security tax, employee Medicare tax, Additional Medicare Tax and `employee_state_payroll_tax` (`variables/gov/irs/tax/payroll/employee_payroll_tax.py`), unless the contributed `abolish_payroll_tax` parameter is set (it is not).
- `employee_state_payroll_tax` adds one `<st>_employee_state_payroll_tax` per state for 14 states. Its documentation reads "Employee-side mandatory state payroll taxes and payroll-funded contributions" (`variables/gov/states/tax/payroll/employee_state_payroll_tax.py`).
- Each state aggregate adds its programs' employee contributions. For Minnesota, Massachusetts, Delaware, Maine and Vermont, the contribution's documentation says it assumes "the employer withholds the maximum permitted employee share". Colorado's, New York's and Washington's say no such thing, though each computes the largest permitted share. The engine has an `employer_headcount` input, which sets employer-side contributions in several states and Delaware's contribution rate, but no input for the employer's deduction choice.
- The five optional contributions are read only by their state aggregates. `employee_payroll_tax` also feeds `spm_unit_paycheck_withholdings`, `household_tax_before_refundable_credits`, Alabama's itemized deductions, `fica_marginal_tax_rate` and `taxsim_tfica`, and California SDI also feeds Santa Clara County general assistance. No PolicyBench output other than `payroll_tax` moves when the five change (the sweep below).

## Every payroll reference with a state component

`scripts/decompose_payroll.py` recomputes all 100 payroll references, reproduces every one, and splits each into its federal and state parts. Twelve carry a state component; eleven are scored.

| Output | State program | State part | Federal part | Reference | Employee share | Status |
|---|---|---:|---:|---:|---|---|
| scenario_005 | CA SDI | 5,590.00 | 30,454.00 | 36,044.00 | mandatory | scored |
| scenario_022 | CA SDI | 684.26 | 4,026.58 | 4,710.83 | mandatory | scored |
| scenario_023 | CA SDI | 226.75 | 1,334.36 | 1,561.12 | mandatory | scored |
| scenario_099 | CA SDI | 2,145.00 | 12,622.50 | 14,767.50 | mandatory | scored |
| scenario_028 | PA UC employee contribution | 42.00 | 4,590.00 | 4,632.00 | mandatory | scored |
| scenario_123 | PA UC employee contribution | 101.50 | 11,092.50 | 11,194.00 | mandatory | scored |
| scenario_120 | CT Paid Leave | 827.98 | 12,668.17 | 13,496.16 | mandatory | scored |
| scenario_008 | NJ TDI 50.92 + FLI 61.64 | 112.56 | 2,050.20 | 2,162.76 | mandatory | excluded (r05, NJ worker UI omitted) |
| scenario_032 | MN Paid Leave | 127.60 | 2,218.50 | 2,346.10 | **optional** | scored; proposed |
| scenario_043 | CO FAMLI | 17.99 | 312.74 | 330.73 | **optional** | scored; proposed |
| scenario_081 | MA PFML | 805.01 | 13,387.65 | 14,192.66 | **optional** | scored; proposed |
| scenario_082 | NY PFL 411.91 + DBL 31.20 | 443.11 | 7,664.92 | 8,108.03 | **optional** | scored; proposed |

Amounts are the engine's (float32): Connecticut's 0.5% of $165,597 is $827.985, which the engine stores as $827.98. Every household with wages in a state with a modeled program carries that program. No household with wages lives in Delaware, Maine, Oregon, Rhode Island, Vermont or Washington; two Washington households (scenario_002 and scenario_111) have none. The four proposed references have had these values since the first run (references generated 2026-06-12, committed 2026-06-15).

## The law, program by program

The test is who owes the contribution. A **mandatory** employee contribution is one the statute puts on the worker and requires the employer to withhold. An **optional employer pass-through** is a premium the statute puts on the employer, which may deduct up to a share from wages and may instead pay it, so the employee amount runs from $0 to a cap at the employer's choice. `program_classification.json` has each program's citation, 2026 rate and engine amounts; `verification/law_research.json` has every record, quote, URL and verdict.

| Program | Who owes it | Employee share | Class | Primary source |
|---|---|---|---|---|
| MN Paid Leave | Premiums "accrue and become payable by each employer"; the employer pays at least 50% (small employers: at least 0.22% of a 0.66% premium) | Employees pay "the remaining portion, if any, of the premium not paid by the employer": $0 to 0.44% | optional | [Minn. Stat. 268B.14](https://www.revisor.mn.gov/statutes/cite/268B.14) subds. 1, 3, 5a |
| CO FAMLI | The employer "shall remit" premiums | The employer "may deduct up to 50 percent" (0.44%); one that deducts less "is considered to have elected to pay" it | optional | [C.R.S. 8-13.3-507](https://olls.info/crs/crs2025-title-08.pdf)(2), (5); 7 CCR 1107-1 s. 1.4(6)(A) |
| MA PFML | The employer "shall remit" contributions | The employer may deduct up to 100% of family and 40% of medical (0.46%) and may deduct less | optional | [M.G.L. c. 175M, s. 6](https://malegislature.gov/Laws/GeneralLaws/PartI/TitleXXII/Chapter175M/Section6)(a), (c); 458 CMR 2.05(5)(c) |
| NY PFL and DBL | The covered employer provides the coverage; it pays the DBL cost beyond what it collects, and no employer is required to fund PFL | The employer "is authorized to collect" up to the caps (PFL 0.432%, at most $411.91; DBL $0.60 a week) | optional | [N.Y. WCL s. 209](https://www.nysenate.gov/legislation/laws/WKC/209)(3)-(4), s. 210(1) |
| CT Paid Leave | Each employee "shall contribute" | The employer "shall deduct and withhold" 0.5%; there is no employer share | mandatory | [Conn. Gen. Stat. 31-49g](https://www.cga.ct.gov/2026/sup/chap_557.htm)(b)(1), (3) |
| CA SDI | Each worker "shall pay worker contributions" | The employer must withhold 1.3% in trust; one that pays it instead still owes the worker's contribution, and the payment counts as wages | mandatory | [Cal. UIC s. 984](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=UIC&sectionNum=984.)(a)(1), s. 986(a) |
| PA UC | Each employee "shall pay contributions" | The employer "shall withhold, in trust" 0.07% of all wages | mandatory | [UC Law s. 301.4](https://www.palegis.us/statutes/unconsolidated/law-information/view-statute?iFrame=true&txtType=HTM&yr=1936&sessInd=2&smthLwInd=2&act=001&chpt=3)(a)-(b) |
| NJ TDI and FLI | Each worker "shall contribute" | The employer "shall ... withhold in trust" (TDI 0.19%, FLI 0.23%) | mandatory | [N.J.S.A. 43:21-7](https://www.nj.gov/labor/myunemployment/assets/pdfs/UI_statute.pdf)(d)(1)(E), (G) |

One researcher per program read the statute, rules, agency pages and engine source; then two reviewers per program, one on the statute and one on the rules and agency guidance, tried to refute each classification, re-fetching the sources and re-running the engine amounts. None of the 16 reviews refuted a classification; eight of them cover the four optional programs. All ran as separate agents in one Claude Code workflow on 2026-10-05, with no reviewer outside it.

For the record of an upstream fix, the same test classifies the modeled programs that reach no wage-earning household; these were researched once and not reviewed. Delaware Paid Leave, Maine PFML and the Vermont Child Care Contribution are optional pass-throughs; Washington Cares, Paid Leave Oregon, the Oregon statewide transit tax and Rhode Island TDI are mandatory; Washington PFML is mixed (the employer "may deduct" the employee share and "may elect to pay" it).

Every 2026 rate, share and cap above was published before the 2026-07-03 reference freeze. Each engine amount equals the law's largest employee share within a cent, with two qualifications: New York's DBL cap is $0.60 a week, which the engine annualizes over 52 weeks ($31.20; a weekly payroll with 53 paydays in 2026 could reach $31.80), and the Massachusetts cap is subject to Acts 2026 c. 101 (below).

What points the other way, all recorded in `verification/law_research.json`:

- **Minnesota.** Subd. 3 says employees "must pay the remaining portion, if any", and subd. 5a(b)(2) that the employer "must make wage deductions as necessary". The Paid Leave office says that if an employer pays more than its required minimum, "this is additional compensation to the employee and is included in the employee's federal gross income as wages". The same office tells employers they "can deduct up to 0.44%" and "may choose to pay more than their required portion".
- **Colorado.** The FAMLI Division's employer page says "Most Colorado businesses should be deducting FAMLI premiums from all employees on their payroll", and its FAQ tells employers to "collect and remit the 0.44% of the employee's share". The same page says some employers "may choose not to deduct any premiums", and the statute says "may deduct".
- **Massachusetts.** The Department of Family and Medical Leave says employers "must withhold PFML contributions from employees' paychecks" and "Most Massachusetts employers must make payroll withholdings"; c. 175M s. 1 counts payments by an employee as contributions, and s. 4(a)(ii) requires notice of the employee's contribution amount. The same page says employers "may choose to cover a larger share", and 458 CMR 2.05(5)(c) covers an employer that "opts to deduct a lower percentage".
- **New York.** WCL s. 209(1) says every employee "shall contribute to the cost of providing disability and ... family leave benefits", the Department of Financial Services' 2026 rate decision says "Employers shall collect employee contributions consistent with this Decision", and the Workers' Compensation Board calls Paid Family Leave "fully paid for by employees". The same Board says an employer "is allowed, but not required" to collect, and s. 209(4) only authorizes collection.
- **California, for contrast.** An employer may pay a worker's SDI instead of deducting it (s. 986(a)(2)), but the worker still owes the contribution and the payment is grossed up as wages. In Minnesota an employer that pays more than its floor leaves the employee nothing owed: the employee pays "the remaining portion, if any".
- **Massachusetts, Acts 2026 c. 101** (approved 2026-06-12, before the freeze). Its s. 25 strikes "40" in lines 22, 33 and 39 of c. 175M s. 6 and inserts "100"; s. 26 strikes "100" in lines 25, 33 and 43 and inserts "40". Section 6 contains each figure exactly three times, in subsections (c), (d) and (e), so the swap reaches the deduction caps: up to 40% of family and 100% of medical. (Applied in sequence, line 33, subsection (d), would end with both figures at 40, which reads as a drafting slip.) Its s. 45 applies ss. 25-26 "for taxable years beginning on or after January 1, 2026", while its s. 43(a) asks for guidance on "the impact for employers and employees in calendar year 2027". The department's rates page, captured 2026-06-17 after the act's approval, still showed the 0.46% maximum, and the department later dated the change 2027-01-01. Under the literal s. 45 reading, the most a large employer could deduct for scenario_081 in 2026 would be $1,351.02 (0.772%) rather than $805.01. The share stays optional either way, so this bears only on keeping the reference.

## What the models answered

`scripts/model_answers.py` scores every answer on the twelve outputs with `policybench.analysis.row_hit_scores`, the scorer the board uses (exact within $1), against the frozen reference and against the reference without the optional shares. Its frozen-reference scores equal the payload's own `exact` field on every row.

| Output | Frozen | Without optional share | Exact now | Exact if regenerated | Most common answers |
|---|---:|---:|---:|---:|---|
| scenario_032 MN | 2,346.10 | 2,218.50 | 6 | 33 | 2,218.50 (29), 2,346.10 (6), 2,219 (4) |
| scenario_043 CO | 330.73 | 312.74 | 16 | 26 | 312.73 (18), 331.13 (9), 330.72 (7) |
| scenario_081 MA | 14,192.66 | 13,387.65 | 9 | 9 | 13,387.65 (7), 14,192.66 (6), 14,193 (3) |
| scenario_082 NY | 8,108.03 | 7,664.92 | 4 | 14 | 7,664.92 (8), 7,665 (6), 8,108.03 (3) |

Every model's explanation on each output, classified by one reviewer per group of outputs (`verification/explanations.json`; 46 models per output):

| Output | Include the state program | Leave it out as optional or employer-paid | Say the state has no employee payroll tax | Never mention it | Other or unparsed |
|---|---:|---:|---:|---:|---:|
| scenario_032 MN | 7 | 1 | 19 | 16 | 3 |
| scenario_043 CO | 18 | 0 | 14 | 11 | 3 |
| scenario_081 MA | 22 | 1 | 7 | 9 | 7 |
| scenario_082 NY | 22 | 0 | 6 | 12 | 6 |
| scenario_005 CA SDI | 31 | 0 | 2 | 8 | 5 |
| scenario_022 CA SDI | 29 | 2 | 4 | 9 | 2 |
| scenario_023 CA SDI | 30 | 0 | 5 | 7 | 4 |
| scenario_099 CA SDI | 29 | 0 | 2 | 10 | 5 |
| scenario_028 PA UC | 12 | 0 | 17 | 15 | 2 |
| scenario_123 PA UC | 15 | 0 | 16 | 11 | 4 |
| scenario_120 CT Paid Leave | 20 | 0 | 11 | 9 | 6 |

The explanations do not separate the optional programs from the mandatory ones. Pennsylvania's and Connecticut's mandatory contributions draw the same mix of "no employee payroll tax" and silence as Minnesota's and Colorado's optional ones; California SDI is included far more often.

If the four references were regenerated, 82 answers would newly be exact. Of these:

- 1 gives the optional-deduction reason (Grok 4.7 on scenario_032: "paid-leave withholding is optional");
- 36 say the state has no employee payroll tax, 25 of them "no mandatory" tax, which is true on the strict reading;
- 39 never mention a state program;
- 6 are other: four name the program and leave it out, among them Claude Opus 5.5 on scenario_081 ("excluded on the assumption the model does not include it").

66 of the 82 come from models that include a mandatory state program elsewhere. Regeneration would also take credit from 35 answers within $1 of the frozen references; 15 equal them to the cent, and 9 are Colorado answers of 331.13 at the 2025 rate of 0.45%. Exclusion removes all 184 rows, so it stops scoring both groups.

Model by model, Claude models almost never answer the frozen value on the four outputs (1 of 40 answers), and the newer GPT models mostly do: GPT-6.1 Sol on all four, and GPT-6 Sol, GPT-6 Astra and GPT-5.6 Sol on three. GPT-6 Sol answers federal tax alone on Minnesota and the frozen value on Colorado, Massachusetts and New York, and matches all seven mandatory references. Claude Opus 5.5 answers federal tax alone on all four; it matches all four California SDI references but leaves out Connecticut's mandatory contribution "on the assumption that PolicyEngine does not model it" and misses both Pennsylvania outputs. Claude Fable 5.1 answers federal tax alone on all eleven scored outputs, mandatory ones included. Ox Alpha and Gemini 3.8 Flash answer federal tax alone on the four; Ox Alpha includes California SDI at the 2025 rate on scenario_022 and scenario_023.

## Board impact

`scripts/leaderboard_impact.py` copies the frozen run to scratch directories and scores it with `python -m policybench.cli analyze`, the command the freeze runs. The unchanged copy reproduces the published payload's modelStats (except the cost and latency fields the freeze overlays), programStats, heatmap, globalWeights and failureModes exactly. Household-impact-weighted exact-match rate, the headline:

| Published rank | Model | Published | Exclude (rank) | Regenerate (rank) | Payroll exact: published, exclude, regenerate |
|---:|---|---:|---:|---:|---|
| 1 | GPT-6 Sol | 95.00 | 95.09 (1) | 94.63 (1) | 98, 95, 96 |
| 2 | Claude Opus 5.5 | 93.70 | 94.32 (2) | 94.39 (2) | 92, 92, 96 |
| 3 | GPT-5.6 Sol | 93.57 | 93.70 (3) | 93.27 (3) | 94, 91, 92 |
| 4 | GPT-6 Luna | 92.10 | 92.34 (5) | 92.07 (5) | 91, 89, 91 |
| 5 | Claude Sonnet 5.5 | 92.08 | 92.52 (4) | 92.44 (4) | 92, 91, 94 |
| 6 | GPT-6 Astra | 91.67 | 91.80 (6) | 91.18 (7) | 86, 83, 83 |
| 7 | Claude Fable 5.1 | 90.83 | 91.38 (7) | 91.52 (6) | 88, 88, 92 |
| 8 | GPT-6.1 Sol | 90.60 | 90.53 (9) | 89.91 (9) | 86, 82, 82 |
| 9 | Kimi K3 | 90.43 | 90.54 (8) | 89.92 (8) | 92, 89, 89 |
| 10 | GPT-5.6 Luna | 89.31 | 89.55 (10) | 89.13 (11) | 89, 87, 88 |
| 11 | Ox Alpha | 88.49 | 89.09 (11) | 89.18 (10) | 87, 87, 91 |
| 12 | Grok 4.7 | 88.34 | 88.61 (13) | 88.35 (13) | 92, 90, 92 |
| 13 | Inkling | 88.22 | 88.65 (12) | 88.37 (12) | 81, 80, 82 |

Payroll exact counts are out of 99 scored payroll outputs (95 under exclusion).

| | Keep | Exclude | Regenerate |
|---|---|---|---|
| Scored outputs per model | 1,928 | 1,924 | 1,928 |
| Headline change per model | none | -0.07 to +0.62 points (mean absolute 0.44) | -0.69 to +0.69 points (mean absolute 0.33) |
| GPT-6 Sol | 95.00%, first | 95.09%, first | 94.63%, first |
| GPT-6 Sol's lead over Claude Opus 5.5 | 1.31 points | 0.78 | 0.24 |
| Within-1% leader (lead over second) | GPT-6 Sol (0.97) | GPT-6 Sol (0.46) | Claude Opus 5.5 (0.09) |
| Models whose headline falls | none | GPT-6.1 Sol (-0.07, 8th to 9th) | 15, GPT-6.1 Sol most (-0.69) |
| Adjacent headline swaps | none | 5 | 10 |
| Bounded-score rank changes | none | 4 | 2 |
| Always-zero baseline | 69.98% | 70.53% | 69.98% |
| GPT-6 Sol's lead over always-zero | 25.02 points | 24.57 | 24.65 |
| Payroll exact across models | 78.5% | 81.0% | 79.5% |

The exclusion swaps are Claude Sonnet 5.5 and GPT-6 Luna (#4/#5), Kimi K3 and GPT-6.1 Sol (#8/#9), Inkling and Grok 4.7 (#12/#13), Gemini 3 Flash Preview and Claude Opus 4.7 (#29/#30), and Gemini 3.1 Flash Lite Preview and DeepSeek V4 Pro (#35/#36). Payroll exact rises under exclusion because most of the 184 removed rows were misses.

**With the state income tax withholding proposal.** PolicyEngine/policybench#191 (cos d963) proposes three federal exclusions and may land in the same release. Its records alone reproduce its own figures here: GPT-6 Sol 95.61% (95.6146; #191's README rounds it to 95.62%), and Claude Sonnet 5.5 passes GPT-6 Luna. On top of them, exclusion takes GPT-6 Sol to 95.75% and Claude Opus 5.5 to 94.97%, with three adjacent swaps; regeneration takes them to 95.19% and 95.00%. `verification/leaderboard_impact.json` has every figure.

## Method

Run from this checkout. `<triage>` is `results/local/adds202609/triage` in the main checkout, which holds the policyengine-us 2.15.17 venv; `<policybench venv>` is the repo's `.venv`.

1. **Decompose.** `scripts/decompose_payroll.py` recomputes every payroll reference on policyengine-us 2.15.17 with `latest_final` (`../2026-09-28/fixes/`) and splits it into federal and per-program state parts (`verification/payroll_decomposition.csv`, `.json` and `.log`). All 100 reproduce the published reference, and the parts add to the total.
2. **Classify.** As above; `program_classification.json` is the result, and `verification/law_research.json` holds the records and verdicts.
3. **Sweep.** `scripts/sweep_payroll_scope.py` recomputes all 1,984 outputs with and without `fixes/payroll_mandatory_scope.py`, an output-scope adapter that drops the five reviewed optional contributions from the list behind `employee_state_payroll_tax` and changes no formula or rate. The baseline reproduces all 1,928 scored references; the 19 excluded outputs that differ keep the values they were decided on, each listed in the sidecar's `excluded_outputs_rechecked`. The adapter moves four outputs, the four payroll references above, and no other output by even a cent (`verification/sweep_payroll_scope.csv` and `.log`). `CountryTaxBenefitSystem` applies a reform twice to the same system (`policyengine_us/system.py`), so the adapter is written to be idempotent: its second pass leaves the already-flattened list unchanged.
4. **Propose.** `scripts/propose_changes.py` writes both alternatives in the format a release installs: `proposed_exclusions.json` (four `reference_depends_on_unlisted_input` records sharing one unlisted input) and `proposed_regenerations.json` (four regenerated values with the adapter's sha256). It refuses a sweep that moves any output the proposal does not cover, and an adapter whose program list differs from the reviewed optional programs.
5. **Answers.** `scripts/model_answers.py` writes `verification/model_answers.csv` and `model_answers_summary.json`, from the payload as git holds it at the pass's commit ([Pinned inputs](#pinned-inputs)).
6. **Impact.** `scripts/leaderboard_impact.py --with-salt` writes `verification/leaderboard_impact*.csv` and `leaderboard_impact.json`. It reads the run, this audit's proposals and #191's records from git at the pass's commits, not from the working tree ([Pinned inputs](#pinned-inputs)).

```
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=$PWD <triage>/.venv-pe21517/bin/python reference_audit/2026-10-05-payroll/scripts/decompose_payroll.py --out-dir reference_audit/2026-10-05-payroll/verification
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=$PWD <triage>/.venv-pe21517/bin/python reference_audit/2026-10-05-payroll/scripts/sweep_payroll_scope.py --out-dir reference_audit/2026-10-05-payroll/verification
PYTHONPATH=$PWD <policybench venv>/bin/python reference_audit/2026-10-05-payroll/scripts/propose_changes.py
PYTHONPATH=$PWD <policybench venv>/bin/python reference_audit/2026-10-05-payroll/scripts/model_answers.py
PYTHONPATH=$PWD <policybench venv>/bin/python reference_audit/2026-10-05-payroll/scripts/leaderboard_impact.py --scratch <dir> --with-salt
```

## Independent review

Eight reviewers checked the work in a second Claude Code workflow on 2026-10-05, each in its own scratch directory and without changing the checkout. Their structured reports are in `verification/independent_reviews.json`.

- **Differential impact.** One re-implemented both options without the CLI, once through `policybench.analysis`'s functions and once in its own numpy code. All 2,438 compared values match (largest rate difference 2.8e-14), as do 966 more for the #191 combinations. It found that #191's 95.62% is a rounding of 95.6146.
- **Differential sweep.** One recomputed all 1,984 outputs by a different mechanism: the five contributions set to 0 as household inputs, with no adapter. Every value is bit-identical to the audit's, and exactly the four payroll outputs move.
- **Mechanism.** One traced the engine path, found the double reform application at `system.py` lines 136 and 153, and hand-computed all 36 federal, state and total values and the four regenerated values from the household facts (largest gap $0.00066, float32 storage). It corrected three statements, fixed above: the engine readers of these variables, the Washington households, and the `employer_headcount` input.
- **Recommendation.** Two advocates built the strongest cases for keep and for regenerate, and a judge weighed them against the rules. The judge found exclusion best supported and the recommendation sound, but rejected several of the first draft's arguments. Board effects and which answers gain credit are not rule criteria; inclusion counts cannot tell ambiguous outputs from clear ones; and exclusion moves the board more than regeneration on most measures. This README now rests the recommendation on the rules and precedents above.
- **Release checklist.** One listed what a release adopting either option must change, by installing each option's records on scratch clones and running the tests (below).
- **Claims.** One checked 131 claims in the first draft and found five errors and thirteen imprecisions, all corrected here.

## What a release adopting either option must also do

The release-checklist reviewer found both options installable, and neither a records-only change. Either needs a release driver (`freeze_gpt61sol.py` refuses any change to the exclusions), a payload refreeze, and changes to tests that pin release 20260929 or 20260930 bytes.

**Exclude:**

1. Record the ruling and set `decided_on` on the four records to its date.
2. Insert the four records into `reference_exclusions.json` before the trailing scenario_023 record (`tests/test_reference_upgrade.py:221-232` requires the tail to equal `final_actions.json`'s audit exclusions), and put any new `derivation` text before the 2026-09-29 marker.
3. Add four developer adjudications (`adjudicated_failure_source: prompt_ambiguity`, `excluded_from_scoring: true`, `reference_verdict: unlisted_input`). Take `judged_on_utc` from the published audit tree (`results/local/gpt61sol-stage/gpt61sol-v1/audit/cases`: 2026-09-29 for 032, 081 and 082; 2026-09-22 for 043), not the older `unified_audit` verdicts. Add the 2026-10-05 wave to `date_conventions` and the judge evidence, and fill the 2026-09-29 wave's null commit (`tests/test_adjudications.py:639, 694-784`).
4. Apply the adjudications with `scripts/apply_adjudications.py`: 145 `llm_error` rows become `prompt_ambiguity` (38 on 032, 30 on 043, 36 on 081, 41 on 082); the four `parse_contract_failure` rows stay.
5. Reword the four case notes and the row annotations that call these shares mandatory (at least 47 of the 149). scenario_032's note is wrong under any option: it says "The one model that did include the paid-leave premium used 0.35%", but seven included it and six match the reference. scenario_043's gives FICA as $312.75 and then $312.73 (the engine's is $312.74).
6. Let `tests/test_reference_audit.py:288-300` and `tests/test_reference_upgrade.py:94-108` accept records decided after their waves; re-scope `tests/test_finish_gpt61sol.py:400-418`, which pins release 20260929's exclusion record.
7. Update the pinned counts:

| Count | Now | Exclude | Exclude with #191 |
|---|---:|---:|---:|
| Excluded outputs | 56 | 60 | 63 |
| Unlisted-input exclusions | 28 | 32 | 35 |
| Households with an exclusion | 39 | 41 | 42 |
| Scored outputs per model | 1,928 | 1,924 | 1,921 |
| Exclusions decided on 2.15.17 | 4 | 8 | 11 |
| Developer adjudications | 69 | 73 | 76 |
| Audited rows | 7,860 | 7,711 | 7,573 |
| Exact-match misses | 7,856 | 7,707 | 7,569 |
| `prompt_ambiguity` rows | 820 | 965 | 1,100 |
| Annotated rows on excluded outputs | 2,111 | 2,260 | 2,398 |
| Parse-contract failures (scored) | 652 | 648 | 645 |
| Leader's weighted exact (`app/tests/expandPage.test.ts`) | 95.003 | 95.093 | 95.749 |

8. Refreeze the payload, analysis CSVs and manifest; update `app/src/data.artifact.json`, `data.versions.json` (60 exclusions: 52 on 1.755.4, 8 on 2.15.17) and `paperSnapshot.json`; keep the snapshot label. Uploading the release asset is Max's step.
9. Rescore the sensitivity evidence (`scripts/sensitivity_by_variable.py`, then `scripts/rescore_sensitivity_summaries.py`; Claude Fable 5.1 auto goes from 91.728 to 92.349).
10. Revise `paper/index.qmd` (the unlisted-input list near line 1087, the sweep sentence, and a review-table row beside "US payroll and overtime" at line 888), `docs/benchmark_card.md` and `docs/paper.md`; re-render and run `freeze_snapshot.py --rendered-only`.
11. If #191 lands in the same release, reword its scenario_081 record, which counts the $805.01 Massachusetts share as paid.

**Regenerate**, beyond the refreeze, pointers, sensitivity and paper steps above:

1. Write the four values into both reference CSVs (the run copy and `paper/snapshot/20260501/us_reference_outputs.csv`) and update `reference_csv_sha256`.
2. Decide how the sidecar records the adapter. `scripts/freeze_snapshot.py` requires a single `engine_upgrade` revision as the last one, and the Maryland adapter is a `fix_modules` entry inside it. Add `payroll_mandatory_scope.py` to `OUTPUT_SCOPE_ADAPTERS` and rewrite the reproducibility note that names only the Maryland adapter (`tests/test_snapshot_artifacts.py:897-935`).
3. Re-run the publication check on the newest policyengine-us with the adapter, as the engine rule requires; `latest_final_2170.csv` has no adapter.
4. Rewrite the four reference narratives, remove the 82 annotations that become exact, annotate the 35 new misses, and re-judge the four cases with Claude Opus 5.5 through `scripts/run_audit_claude.sh`.
5. The pinned exclusion and adjudication counts do not change; audited rows go to 7,813 and misses to 7,809; the leader pin becomes 94.629.

## Related findings

- **Engine.** policyengine-us has no input for the employer's deduction choice. An upstream change could add one, defaulting to the largest share, so users can model either reading; it would also need to settle Delaware, Maine, Vermont and Washington. The Connecticut rate parameter cites 31-49e, where 31-49g(b)(1) holds the rate. California's SDI rate parameter carries 1.3% back to 0000-01-01, which is wrong for earlier years (1.2% in 2025). The Massachusetts parameters do not encode Acts 2026 c. 101. None of these moves a benchmark number.
- **#191.** Its README rounds GPT-6 Sol's 95.6146% to 95.62%. Its scenario_081 record treats the $805.01 Massachusetts share as a contribution the household paid, which this audit classifies as optional.
- **SALT.** policyengine-us 2.15.17 leaves state payroll contributions out of the federal SALT deduction, the defect #191 records.

## Pinned inputs

This audit's passes read release dashboard-data-20260930's run, as #187 committed it at `8b4c0ca1`, and this directory's inputs as #202 merged them at `9ce4ade8`. Every committed file the scripts below write regenerates byte for byte from those inputs. Release dashboard-data-20261006 (#202) then installed the four proposed exclusions and #191's three records, and rewrote the run's payload and exclusion record. On that working tree the unpinned impact script stopped at the `salt` copy with `--with-salt`: its appended records duplicated #202's, and the analyze CLI refuses a duplicate exclusion. The unpinned `model_answers.py` exited 0 after rewriting `verification/model_answers.csv`: its `scored` column turned false on the four outputs' 184 rows.

Each script below now takes every file it reads from git with `git show <commit>:<path>`. It stops before scoring or writing anything unless each file's sha256 matches its pin, and it never reads the working tree. `<run>` is `paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace`.

### `scripts/leaderboard_impact.py`

| Input | Commit | sha256 |
|---|---|---|
| `<run>/data.json.gz` | `8b4c0ca1` | `1e029aaa87d1dfbd2ceee88419599a919dd7c9d4aba78a308ec48d008d54ae18` |
| `<run>/predictions.csv.gz` | `8b4c0ca1` | `ca2c4c48c7fd3e680c9c61a7380ecfcb60ce95f913c5c363762e023949d8ad12` |
| `<run>/reference_outputs.csv` | `8b4c0ca1` | `e8bbba8fd3e90f78e7c0e83df06227bc1c94563e92f7405fe12be853a30b2466` |
| `<run>/reference_outputs.csv.meta.json` | `8b4c0ca1` | `816fef53c452d8520a321bc12bc29b28da1e7956a06818e5ec13d7fc7b371a4b` |
| `<run>/reference_exclusions.json` | `8b4c0ca1` | `bf4e6a249aeee01d0b71f5834ef7a35c4bab2266d2c59d0e81b12a0da44281c2` |
| `<run>/scenarios.csv` | `8b4c0ca1` | `71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a` |
| `<run>/scenarios.csv.meta.json` | `8b4c0ca1` | `03a66e90b86e9bd0cc77f27520784bd581777762f749675dc716e24c1b8eaebb` |
| `proposed_exclusions.json` | `9ce4ade8` | `f23088c2d76ce2a0f1c535529952e579798920450c0ca47a9e975f3fe3c44157` |
| `proposed_regenerations.json` | `9ce4ade8` | `58386f369f6164cc9d63cc4dcc4423495e214e45948fb2e2479910fc8165efef` |
| `reference_audit/2026-10-05/proposed_exclusions.json` | `9ce4ade8` | `3c330177762c46fa5c52b02f9f943e9d5a65e15855280b64e9b462ab27413272` |

It stages each file under `<scratch>/pass_inputs/<path>` and reads only that copy. `reference_audit/2026-10-05/proposed_exclusions.json` holds #191's records and is read only with `--with-salt`. The pass read it at #191's head `8af912a0`, which `leaderboard_impact.json` records as `salt_commit`. #202 merged the same bytes, so the script reads them from `9ce4ade8` and does not need #191's closed branch.

### `scripts/model_answers.py`

| Input | Commit | sha256 |
|---|---|---|
| `<run>/data.json.gz` | `8b4c0ca1` | `1e029aaa87d1dfbd2ceee88419599a919dd7c9d4aba78a308ec48d008d54ae18` |
| `verification/payroll_decomposition.csv` | `9ce4ade8` | `fa34d6d98b7ea5fa00023ed93946948e48ea728e45702cea222355e008be9cab` |
| `program_classification.json` | `9ce4ade8` | `282cbf25ce9110a3c5c51873b7ca0e89f1f5ed38592b0c5b51d393f08000089a` |

### Reproduce

The scoring code is the checkout's. The impact script's check on its unchanged copy stops it if that code no longer scores the pinned run as the pinned payload records. The scripts run from any checkout that has both commits in its history; a shallow clone needs `git fetch --unshallow` first:

```bash
PYTHONPATH=$PWD uv run python reference_audit/2026-10-05-payroll/scripts/leaderboard_impact.py --scratch <dir outside the repository> --with-salt
PYTHONPATH=$PWD uv run python reference_audit/2026-10-05-payroll/scripts/model_answers.py
```

`--out-dir <dir>` writes the files elsewhere. `tests/test_reference_audit_pins.py` checks the pins, that a changed byte in any input is refused, and that no script reads the working tree. It reruns `model_answers.py` from a checkout whose working tree is junk and requires the committed `verification/model_answers.csv` and `model_answers_summary.json` byte for byte. Its slow test regenerates `leaderboard_impact.json` and the ten `leaderboard_impact_*.csv` files (with `--with-salt`) from this checkout, whose run #202 rewrote, and requires the committed files byte for byte. The slow test takes one to two minutes per audit, so CI deselects it:

```bash
OPENBLAS_NUM_THREADS=1 uv run pytest -m slow tests/test_reference_audit_pins.py
```
