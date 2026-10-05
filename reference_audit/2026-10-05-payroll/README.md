# Optional employer pass-through in the payroll tax references, October 5, 2026

This directory audits the state part of PolicyBench's US `payroll_tax` references in release `dashboard-data-20260930`. Four scored references count an employee share of a state paid-leave premium that the law lets the employer deduct but does not require. The directory proposes two alternative records for those four outputs, excluding them or regenerating them, and changes no reference. Either one changes published scores, so they wait for Max's ruling (cos decision DECISION_ID).

## Recommendation

Exclude the four outputs (scenario_032 MN, scenario_043 CO, scenario_081 MA, scenario_082 NY) from scoring in the next release, with `proposed_exclusions.json`. In the next prompt version, state how optional employee shares count, so these households can be scored again on a fresh run.

- **Keep fails.** Under each state's law the premium is the employer's, and the employee pays only what the employer chooses to deduct, from zero up to a cap (16 of 16 independent reviews agree). The frozen reference assumes the cap. policyengine-us documents that assumption for Minnesota and Massachusetts ("assuming the employer withholds the maximum permitted employee share"), and the prompt never states the employer's choice. The reference therefore rests on a fact the prompt does not give.
- **Regenerate picks a side of a real split.** The prompt asks for "mandatory employee state payroll taxes" and says to exclude employer payroll taxes. On that wording the frozen value is too high. But the same laws speak of the employee share in mandatory terms: Minnesota's statute says employees "must pay the remaining portion, if any", New York's says every employee "shall contribute", and Massachusetts tells employers they "must withhold PFML contributions". 22 of 46 models included the Massachusetts and New York contributions. That is the case the exclusion rule covers: a careful reader could take the stated facts the other way.
- **Regenerating would mostly reward answers that never engaged with the program.** Across the four outputs it would newly credit 82 answers. One gives the optional-deduction reason; 36 say the state has no employee payroll tax and 39 never mention a state program, the same pattern as on Pennsylvania's mandatory contribution, where 17 and 16 models say the state has none. It would take credit from 35 answers that include the program at exactly the engine's amount.
- **Exclusion is the symmetric remedy and moves the board least.** GPT-6 Sol stays first (95.00% to 95.09%); five adjacent pairs swap. Regeneration moves GPT-6 Sol to 94.63% and puts Claude Opus 5.5 first on the within-1% metric.

## How the reference is built

These files hold for policyengine-us 2.15.17, as installed in the reference venv, plus `latest_final`, the system that built the published references.

- `payroll_tax` is `spm_unit_payroll_tax` (`policybench/benchmark_specs.json`), which sums `employee_payroll_tax` over the SPM unit's tax units (`variables/household/expense/tax/spm_unit_payroll_tax.py`).
- `employee_payroll_tax` adds employee Social Security tax, employee Medicare tax, Additional Medicare Tax and `employee_state_payroll_tax` (`variables/gov/irs/tax/payroll/employee_payroll_tax.py`).
- `employee_state_payroll_tax` adds one `<st>_employee_state_payroll_tax` per state for 14 states. Its documentation reads "Employee-side mandatory state payroll taxes and payroll-funded contributions" (`variables/gov/states/tax/payroll/employee_state_payroll_tax.py`).
- Each state aggregate adds its programs' employee contributions. For Minnesota, Massachusetts, Delaware, Maine and Vermont, the contribution's documentation says it assumes "the employer withholds the maximum permitted employee share". Colorado's, New York's and Washington's say no such thing, though each computes the largest permitted share.
- Nothing else in the engine reads these contributions except through `employee_payroll_tax`, which also feeds `spm_unit_paycheck_withholdings` and `household_tax_before_refundable_credits`. No PolicyBench output other than `payroll_tax` moves when they change (the sweep below).

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

Every household with wages in a state with a modeled program carries that program; no benchmark household lives in Delaware, Maine, Oregon, Rhode Island, Vermont or Washington. The four proposed references have had these values since the first run (2026-06-15).

## The law, program by program

The test is who owes the contribution. A **mandatory** employee contribution is one the statute puts on the worker and requires the employer to withhold. An **optional employer pass-through** is a premium the statute puts on the employer, which may deduct up to a share from wages and may instead pay it, so the employee amount runs from zero to a cap at the employer's choice. `program_classification.json` has each program's citation, 2026 rate and engine amounts; `verification/law_research.json` has every record, quote and URL.

| Program | Who owes it | Employee share | Class | Primary source |
|---|---|---|---|---|
| MN Paid Leave | Premiums "accrue and become payable by each employer"; employer pays at least 50% | Employees pay "the remaining portion, if any, of the premium not paid by the employer": 0 to 0.44% | optional | [Minn. Stat. 268B.14](https://www.revisor.mn.gov/statutes/cite/268B.14) subds. 1, 3, 5a |
| CO FAMLI | Employer "shall remit" premiums | Employer "may deduct up to 50 percent" (0.44%); one that deducts less "is considered to have elected to pay" it | optional | [C.R.S. 8-13.3-507](https://olls.info/crs/crs2025-title-08.pdf)(2), (5); 7 CCR 1107-1 s. 1.4(6)(A) |
| MA PFML | Employer "shall remit" contributions | Employer may deduct up to 100% of family and 40% of medical (0.46%) and may deduct less | optional | [M.G.L. c. 175M, s. 6](https://malegislature.gov/Laws/GeneralLaws/PartI/TitleXXII/Chapter175M/Section6)(a), (c); 458 CMR 2.05(5)(c) |
| NY PFL and DBL | Covered employer provides the coverage and pays its cost beyond what it collects | Employer "is authorized to collect" up to the caps (PFL 0.432%, at most $411.91; DBL $0.60 a week) | optional | [N.Y. WCL s. 209](https://www.nysenate.gov/legislation/laws/WKC/209)(3)-(4), s. 210(1) |
| CT Paid Leave | Each employee "shall contribute" | Employer "shall deduct and withhold" 0.5%; no employer share | mandatory | [Conn. Gen. Stat. 31-49g](https://www.cga.ct.gov/2026/sup/chap_557.htm)(b)(1), (3) |
| CA SDI | Each worker "shall pay worker contributions" | Employer must withhold 1.3% in trust; one that pays it instead still owes the worker's contribution, and the payment counts as wages | mandatory | [Cal. UIC s. 984](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=UIC&sectionNum=984.)(a)(1), s. 986(a) |
| PA UC | Each employee "shall pay contributions" | Employer "shall withhold, in trust" 0.07% of all wages | mandatory | [UC Law s. 301.4](https://www.palegis.us/statutes/unconsolidated/law-information/view-statute?iFrame=true&txtType=HTM&yr=1936&sessInd=2&smthLwInd=2&act=001&chpt=3)(a)-(b) |
| NJ TDI and FLI | Each worker "shall contribute" | Employer "shall ... withhold in trust" (TDI 0.19%, FLI 0.23%) | mandatory | [N.J.S.A. 43:21-7](https://www.nj.gov/labor/myunemployment/assets/pdfs/UI_statute.pdf)(d)(1)(E), (G) |

For the record of an upstream fix, the same test classifies the modeled programs no benchmark household reaches; these were researched once and not adversarially reviewed. Delaware Paid Leave, Maine PFML and the Vermont Child Care Contribution are optional pass-throughs; Washington Cares, Paid Leave Oregon, the Oregon statewide transit tax and Rhode Island TDI are mandatory; Washington PFML is mixed (the employer "may deduct" the employee share and "may elect to pay" it).

Every 2026 rate, share and cap above was published before the 2026-07-03 reference freeze, and each engine amount equals the law's largest employee share to the cent. Points that cut the other way, all recorded in `verification/law_research.json`:

- **Minnesota.** Subd. 3 says employees "must pay the remaining portion, if any", and subd. 5a(b)(2) that the employer "must make wage deductions as necessary". The remainder is whatever the employer leaves above its 50% floor, and the Department of Employment and Economic Development tells employers they "can deduct up to 0.44%" and "may choose to pay more than their required portion".
- **New York.** WCL s. 209(1) says every employee "shall contribute ... to the extent and in the manner herein provided"; s. 209(4) then only authorizes collection, and the Workers' Compensation Board says an employer "is allowed, but not required" to collect.
- **Massachusetts.** The Department of Family and Medical Leave's overview says employers "must withhold PFML contributions from employees' paychecks"; the same page says they "may choose to cover a larger share", and 458 CMR 2.05(5)(c) covers an employer that "opts to deduct a lower percentage". Acts 2026 c. 101 (approved 2026-06-12, before the freeze) amends the deduction caps in s. 6. The two reviewers read its scope differently, and its s. 45 applies it to taxable years beginning on or after 2026-01-01, while the department, after the freeze, dates the change to 2027. If it reached 2026, the most a large employer could deduct for scenario_081 would be $1,351.02 (0.772%) rather than $805.01. The share stays optional either way, so this matters only if the reference is kept.
- **California.** An employer may pay a worker's SDI instead of deducting it (s. 986(a)(2)), but the contribution remains the worker's and the payment counts as wages, the same structure as an employer paying the employee's FICA.

## What the models answered

`scripts/model_answers.py` scores every answer on the twelve outputs with `policybench.analysis.row_hit_scores`, the scorer the board uses (exact within $1), against the frozen reference and against the reference without the optional shares. Its frozen-reference scores equal the payload's own `exact` field on every row.

| Output | Frozen | Without optional share | Exact now | Exact if regenerated | Most common answers |
|---|---:|---:|---:|---:|---|
| scenario_032 MN | 2,346.10 | 2,218.50 | 6 | 33 | 2,218.50 (29), 2,346.10 (6), 2,219 (4) |
| scenario_043 CO | 330.73 | 312.74 | 16 | 26 | 312.73 (18), 331.13 (9), 330.72 (7) |
| scenario_081 MA | 14,192.66 | 13,387.65 | 9 | 9 | 13,387.65 (7), 14,192.66 (6), 14,193 (3) |
| scenario_082 NY | 8,108.03 | 7,664.92 | 4 | 14 | 7,664.92 (8), 7,665 (6), 8,108.03 (3) |

Of 46 models, the explanations on each output (`verification/explanations.json`, one reviewer per group of outputs, every model classified):

| Output | Include the state program | Leave it out as optional or employer-paid | Say the state has no employee payroll tax | Never mention it | Other or unparsed |
|---|---:|---:|---:|---:|---:|
| scenario_032 MN | 7 | 1 | 19 | 16 | 3 |
| scenario_043 CO | 18 | 0 | 14 | 11 | 3 |
| scenario_081 MA | 22 | 1 | 7 | 9 | 7 |
| scenario_082 NY | 22 | 0 | 6 | 12 | 6 |

Where the law requires the employee contribution, the explanations look the same (mandatory programs, all scored):

| Output | Include the state program | Leave it out as optional or employer-paid | Say the state has no employee payroll tax | Never mention it | Other or unparsed |
|---|---:|---:|---:|---:|---:|
| scenario_005 CA SDI | 31 | 0 | 2 | 8 | 5 |
| scenario_022 CA SDI | 29 | 2 | 4 | 9 | 2 |
| scenario_023 CA SDI | 30 | 0 | 5 | 7 | 4 |
| scenario_099 CA SDI | 29 | 0 | 2 | 10 | 5 |
| scenario_028 PA UC | 12 | 0 | 17 | 15 | 2 |
| scenario_123 PA UC | 15 | 0 | 16 | 11 | 4 |
| scenario_120 CT Paid Leave | 20 | 0 | 11 | 9 | 6 |

So a federal-only answer usually means the model did not know or did not apply the program: on Pennsylvania's mandatory contribution, 17 and 16 models say the state has no employee payroll tax. Across the four optional outputs, a regenerated reference would newly credit 82 answers. One of them gives the optional-deduction reason (Grok 4.7 on scenario_032: "paid-leave withholding is optional"); 36 say the state has no employee payroll tax, 39 never mention a state program and 6 are other or unparsed. It would take credit from 35 answers that include the program at exactly the engine's amount.

Model by model, the readings split by family. Claude Opus 5.5, Claude Fable 5.1, Ox Alpha and Gemini 3.8 Flash answer federal tax alone on all four. GPT-6.1 Sol answers the frozen reference on all four. GPT-6 Sol answers federal tax alone on Minnesota and the frozen reference on Colorado, Massachusetts and New York; it also matches all seven mandatory references. Claude Fable 5.1 and Ox Alpha leave out every state program, mandatory ones included.

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

**Exclude** (1,928 to 1,924 scored outputs per model):

- Every model's headline exact rate moves by -0.07 to +0.62 points. GPT-6 Sol: 95.00% to 95.09%, still first.
- Five adjacent pairs swap: Claude Sonnet 5.5 and GPT-6 Luna (#4/#5), Kimi K3 and GPT-6.1 Sol (#8/#9), Inkling and Grok 4.7 (#12/#13), Gemini 3 Flash Preview and Claude Opus 4.7 (#29/#30), and Gemini 3.1 Flash Lite Preview and DeepSeek V4 Pro (#35/#36).
- The always-zero baseline moves from 69.98% to 70.53%, so GPT-6 Sol's lead over it goes from 25.02 to 24.57 points.
- Payroll exact match across models rises from 78.5% to 81.0%.

**Regenerate** (1,928 scored outputs per model):

- Headline exact rates move by -0.69 to +0.69 points. GPT-6 Sol: 95.00% to 94.63%, still first; Claude Opus 5.5: 93.70% to 94.39%, so the gap closes from 1.31 to 0.24 points.
- Ten adjacent pairs swap on the headline, among them Claude Sonnet 5.5 and GPT-6 Luna (#4/#5) and Claude Fable 5.1 and GPT-6 Astra (#6/#7). On the within-1% metric Claude Opus 5.5 passes GPT-6 Sol for first.
- The always-zero baseline is unchanged at 69.98%; GPT-6 Sol's lead over it goes from 25.02 to 24.65 points.

**With the state income tax withholding proposal.** PolicyEngine/policybench#191 (cos d963) proposes three federal exclusions and may land in the same release. Its records alone reproduce #191's figures here (GPT-6 Sol 95.62%; Claude Sonnet 5.5 passes GPT-6 Luna). On top of them, exclusion takes GPT-6 Sol to 95.75% and Claude Opus 5.5 to 94.97% with three adjacent swaps; regeneration takes them to 95.19% and 95.00%. `verification/leaderboard_impact.json` has every figure.

## Method

Run from this checkout. `<triage>` is `results/local/adds202609/triage` in the main checkout, which holds the policyengine-us 2.15.17 venv; `<policybench venv>` is the repo's `.venv`.

1. **Decompose.** `scripts/decompose_payroll.py` recomputes every payroll reference on policyengine-us 2.15.17 with `latest_final` (`../2026-09-28/fixes/`) and splits it into federal and per-program state parts (`verification/payroll_decomposition.csv` and `.json`). All 100 reproduce the published reference, and the parts add to the total.
2. **Classify.** One researcher per program read the statute, rules, agency pages and engine source; two reviewers per program, one on the statute and one on the rules and agency guidance, then tried to refute each classification, re-fetching the sources and re-running the engine amounts. None refuted. `program_classification.json` is the result; `verification/law_research.json` holds every record and verdict.
3. **Sweep.** `scripts/sweep_payroll_scope.py` recomputes all 1,984 outputs with and without `fixes/payroll_mandatory_scope.py`, an output-scope adapter in the form of the Maryland one (`../2026-09-28/fixes/latest_md_local_output_scope.py`). It drops the five optional contributions from the list behind `employee_state_payroll_tax` and changes no formula or rate. The baseline reproduces all 1,928 scored references; the 19 excluded outputs that differ keep the values they were decided on, each listed in the sidecar's `excluded_outputs_rechecked`. The adapter moves four outputs, the four payroll references above, and no other output by even a cent (`verification/sweep_payroll_scope.csv` and `.log`). `CountryTaxBenefitSystem` applies a reform twice to the same system, so the adapter is idempotent.
4. **Propose.** `scripts/propose_changes.py` writes both alternatives in the format a release installs: `proposed_exclusions.json` (four `reference_depends_on_unlisted_input` records) and `proposed_regenerations.json` (four regenerated values with the adapter's sha256). It refuses a sweep that moves any output the proposal does not cover.
5. **Answers.** `scripts/model_answers.py` writes `verification/model_answers.csv` and `model_answers_summary.json`.
6. **Impact.** `scripts/leaderboard_impact.py --with-salt` writes `verification/leaderboard_impact*.csv`, `leaderboard_impact.json` and `.log`. It reads #191's records from its commit `8af912a0`.

```
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=$PWD <triage>/.venv-pe21517/bin/python reference_audit/2026-10-05-payroll/scripts/decompose_payroll.py --out-dir reference_audit/2026-10-05-payroll/verification
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=$PWD <triage>/.venv-pe21517/bin/python reference_audit/2026-10-05-payroll/scripts/sweep_payroll_scope.py --out-dir reference_audit/2026-10-05-payroll/verification
PYTHONPATH=$PWD <policybench venv>/bin/python reference_audit/2026-10-05-payroll/scripts/propose_changes.py
PYTHONPATH=$PWD <policybench venv>/bin/python reference_audit/2026-10-05-payroll/scripts/model_answers.py
PYTHONPATH=$PWD <policybench venv>/bin/python reference_audit/2026-10-05-payroll/scripts/leaderboard_impact.py --scratch <dir> --with-salt
```

INDEPENDENT_REVIEW

## What a release adopting either option must also do

RELEASE_CHECKLIST

## Related findings

- **Published annotations.** The case notes for these outputs treat the frozen reference as settled. scenario_081's calls the Massachusetts contribution "the mandatory Massachusetts Paid Family and Medical Leave (PFML) employee contribution", and scenario_032's and scenario_043's count the optional-deduction reasoning as a model error. Both options need them reworded.
- **Engine.** policyengine-us has no input for the employer's deduction choice, employer size (except Massachusetts' employer side) or a private plan. An upstream change could add one and default it to the largest share, so users can model either reading. The Connecticut rate parameter cites 31-49e, where 31-49g(b)(1) holds the rate; California's SDI rate parameter carries 1.3% back to 0000-01-01, wrong for years before 2026 (1.2% in 2025). Neither moves a benchmark number.
- **SALT.** policyengine-us 2.15.17 leaves state payroll contributions out of the federal SALT deduction, the defect PolicyEngine/policybench#191 records.
