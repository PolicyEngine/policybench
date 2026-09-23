# Projected-parameter audit: Minnesota, Maryland, Michigan, Missouri, Illinois

Reference freeze: **2026-07-03**. Engine: **policyengine-us 1.755.4**. Audit date: **2026-09-22**.

Four assigned references have verified stale-parameter defects; two r18 candidates match published 2026 amounts. Maryland 068 is a **provisional** held-convention calculation, not a resolved exclusion recommendation. No additional outputs in the five families move after controlling for the reference-snapshot discrepancy described below.

| Scenario | State | Output | Frozen | Convention | Delta | Classification |
|---|---|---|---:|---:|---:|---|
| 032 | MN | Refundable credits | 2187.600098 | 2187.600098 | +0.000000 | `unchanged` |
| 045 | MI | State tax before refundable credits | 1288.837524 | 1290.962524 | +2.125000 | `engine_defect_stale` |
| 068 | MD | State tax before refundable credits | 1252.967773 | 1255.342773 | +2.375000 | `held_convention` **(provisional)** |
| 070 | IL | State tax before refundable credits | 1650.561279 | 1650.561279 | +0.000000 | `unchanged` |
| 078 | MD | Federal tax before refundable credits | 24772.693359 | 24780.613281 | +7.919922 | `engine_defect_stale` |
| 093 | MO | State tax before refundable credits | 3389.650879 | 3388.245605 | -1.405273 | `engine_defect_stale` |
| 122 | MN | State tax before refundable credits | 1028.216553 | 1025.541504 | -2.675049 | `engine_defect_stale` |

Machine-readable assigned-row results: [`work/r19_summary.json`](work/r19_summary.json). Each family section gives sources, dates, full parameter tables or inventories, the fix, and all its attributed movers. `unchanged` uses the benchmark's $1 tolerance; no binary output changes.

## Verification and reference snapshots

All five modules completed the unmodified triage harness over **1,984 outputs each**. The full no-fix control also completed 1,984 outputs. Across the assigned states, the scans cover MN 42, MD 32, MI 52, MO 40, and IL 32 outputs, including every household in those states. Full CSVs, diagnostics, source inventories, and [`work/r19_validation.json`](work/r19_validation.json) are retained.

**The initial five family sweeps and baseline control read a different SNAP reference snapshot from the final Michigan rerun.** In the initial runs, 14 SNAP frozen values differed from the stored r18 frozen column: nine by more than $1 and five by −$0.316833. The engine reproduced the original r18 amounts in every run. The final harness points to the original v1.1 bundle and its frozen inputs now agree with those amounts. All 1,984 Michigan computed values are exactly identical between runs; only the 14 SNAP frozen inputs and resulting comparison fields changed. The seven assigned rows are unaffected. Both raw runs and the exact input changes are retained in [`work/r19_mi_final_convention.csv`](work/r19_mi_final_convention.csv) and [`work/r19_final_sweep_reference_changes.json`](work/r19_final_sweep_reference_changes.json). No file under `triage/` or the publish bundle was modified by this audit; the external change was not attributed to anyone.

The following table classifies all nine otherwise-unattributed raw movers as **unchanged by these families**. The initially read SNAP convention reference is shown separately from the computed result; no SNAP correction is inferred from these state-family sweeps. The five below-tolerance differences (027, 030, 045, 073, 108) are retained in [`work/r19_reference_snapshot_difference.json`](work/r19_reference_snapshot_difference.json). These SNAP controls are outside the seven assigned rows in the main summary JSON.

| Scenario | Output | Earlier frozen / SNAP convention | Computed result / final frozen | Raw delta | Family delta | Classification / reason |
|---|---|---:|---:|---:|---:|---|
| 008 | SNAP | 15120.000000 | 15246.905273 | +126.905273 | 0 | `unchanged` by assigned families; reference snapshot differs |
| 012 | SNAP | 4884.000000 | 4952.089355 | +68.089355 | 0 | `unchanged` by assigned families; reference snapshot differs |
| 038 | SNAP | 7212.000000 | 7286.944336 | +74.944336 | 0 | `unchanged` by assigned families; reference snapshot differs |
| 043 | SNAP | 3576.000000 | 3596.039795 | +20.039795 | 0 | `unchanged` by assigned families; reference snapshot differs |
| 054 | SNAP | 6060.000000 | 6125.688965 | +65.688965 | 0 | `unchanged` by assigned families; reference snapshot differs |
| 066 | SNAP | 3576.000000 | 3596.039795 | +20.039795 | 0 | `unchanged` by assigned families; reference snapshot differs |
| 079 | SNAP | 2376.000000 | 2428.017334 | +52.017334 | 0 | `unchanged` by assigned families; reference snapshot differs |
| 080 | SNAP | 3576.000000 | 3596.039795 | +20.039795 | 0 | `unchanged` by assigned families; reference snapshot differs |
| 109 | SNAP | 7932.000000 | 8020.554199 | +88.554199 | 0 | `unchanged` by assigned families; reference snapshot differs |

Reproduction command, substituting `mn`, `md`, `mi`, `mo`, or `il` for FAMILY:

```bash
cd /Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/sweep
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/opus55 \
../.venv-pe1755/bin/python sweep.py \
  --fix /Users/maxghenis/PolicyEngine/_wk/pb-triage-verify-v5b/sweep/fixes/r19_FAMILY_convention.py \
  --out /Users/maxghenis/PolicyEngine/_wk/pb-triage-verify-v5b/sweep/verify/work/r19_FAMILY_convention.csv
```

Publication limitations remain explicit: Maryland annual-return deductions and CDCC timing; Michigan's additional held tables; Minnesota marriage-credit timing; and Missouri's 2026 public-pension-cap publication date. The four verified mover classifications do not depend on those unresolved dates. Maryland 068 is the one assigned row whose convention classification remains provisional.

The initial workspace had no tracked modifications. All new files are inside the assigned workspace. The requested commit attempt failed because the supplied environment makes `.git` read-only (`.git/index.lock: Operation not permitted`); no commits, history rewrites, remote pushes, filings, or posts were made.




The final expanded Michigan module was rerun through the original full harness: all 1,984 computed values exactly match its earlier sweep. Its reference inputs differ on 14 SNAP rows, as documented above; only scenario 045 state tax moves against the final run's frozen inputs. Direct Michigan/Illinois traces also verify the final values. A supplementary combined clone-based run was interrupted for runtime overhead; no results from it are used.



## Minnesota

Minnesota published the 2026 renter schedule before the freeze. The two assigned r18 moves have different dispositions: the child/working-family credit projection matches the published 2026 figures used by scenario 032; the standard deduction used by scenario 122 is $50 too low. The full sweep confirms one Minnesota output changes, by −$2.67505.

### Sources, publication dates, and convention

| Source | Document/release date | What was checked | Convention |
| --- | --- | --- | --- |
| [2026 inflation-adjusted amounts](https://www.revenue.state.mn.us/sites/default/files/2025-12/inflation-adjusted-amounts-2026.pdf), pp. 1–3 and 5 | PDF dated 2025-12-01; linked by the [2025-12-16 agency release](https://www.revenue.state.mn.us/press-release/2025-12-16/minnesota-income-tax-brackets-standard-deduction-and-dependent-exemption) | Deductions, exemptions, tax brackets, AMT, child/working-family/dependent-care credits, Social Security/public-pension subtractions, and renter schedule | Published 2026 values |
| [2025 inflation-adjusted amounts](https://www.revenue.state.mn.us/sites/default/files/2024-12/inflation-adjusted-amounts-2025.pdf), pp. 1–3 and 5 | PDF dated 2024-12-11; the [2024-12-16 agency release](https://www.revenue.state.mn.us/press-release/2024-12-16/minnesota-income-tax-brackets-standard-deduction-and-dependent-exemption) announces the 2025 amounts | Corresponding 2025 values, including all 51 projected renter entries | Establishes actual 2025 values, rather than treating the engine's projected 2025 entries as published |
| [2025 M1MA grid final draft](https://www.revenue.state.mn.us/sites/default/files/2025-10/m1ma-25-grid-0.pdf), line 19 | Printed 2025-10-15 | Marriage-credit cap $1,851; engine's explicit 2025 value is $1,853 | Hold $1,851 |
| [2026 M1MA grid near-final draft](https://www.revenue.state.mn.us/sites/default/files/2026-08/m1ma-26-grid.pdf), line 19 | Printed 2026-08-03 | Marriage-credit cap $1,894; projected engine value $1,894.994377 | After freeze; earliest located 2026 publication, with earlier publication unverified |

The PDF dates establish dated agency documents; exact first-upload dates were not independently verified. The 2026 December release expressly links the complete inflation-adjustment publication, establishing pre-freeze availability. The marriage cap's first publication remains unverified: no pre-freeze 2026 cap publication was located. Its hold is provisional and has no effect on either Minnesota household, because neither qualifies for the marriage credit. The [statute](https://www.revisor.mn.gov/statutes/cite/290.0675), subdivision 3, defines the credit by a joint-versus-single tax comparison and calls for an agency table.

### Parameters and fix

Fix: [r19_mn_convention.py](../fixes/r19_mn_convention.py). It sets all **141 projected Minnesota 2026 parameters** and all **51 projected 2025 renter parameters** to the sourced values, covering all filing statuses and all brackets represented in the existing scales. Complete, unrounded parameter-by-parameter 2025, engine-2026, published-2026, convention, source, and date records are in [r19_mn_parameters.json](work/r19_mn_parameters.json).

All parameter paths below have the prefix `gov.states.mn.tax.income.`. Joint amounts also apply to surviving spouses.

| Parameter family | Published 2025 | Convention 2026 |
| --- | --- | --- |
| `deductions.standard.base` single/separate; joint; head | 14,950; 29,900; 22,500 | 15,300; 30,600; 23,000 |
| `deductions.standard.extra` unmarried; married | 2,000; 1,550 | 2,000; 1,600 |
| `deductions.{standard,itemized}.reduction.agi_threshold.low` nonseparate; separate | 238,950; 119,475 | 244,400; 122,200 |
| Same, `.high` | 330,300; 165,150 | 337,800; 168,900 |
| `exemptions.amount` | 5,200 | 5,300 |
| `exemptions.agi_threshold` single; joint; head; separate | 239,050; 358,550; 298,800; 179,275 | 244,500; 366,700; 305,600; 183,350 |
| `rates.single` three positive thresholds | 32,570; 106,990; 198,630 | 33,310; 109,430; 203,150 |
| `rates.joint`/`surviving_spouse` | 47,620; 189,180; 330,410 | 48,700; 193,480; 337,930 |
| `rates.separate` | 23,810; 94,590; 165,205 | 24,350; 96,740; 168,965 |
| `rates.head_of_household` | 40,100; 161,130; 264,050 | 41,010; 164,800; 270,060 |
| `amt.fractional_income_threshold` single/head; joint; separate | 71,470; 95,300; 47,660 | 73,100; 97,470; 48,740 |
| `credits.cdcc.phaseout_threshold` | 64,150 | 65,610 |
| `credits.cwfc.ctc.amount` | 1,750 | 1,800 |
| `credits.cwfc.phase_out.threshold` joint; other | 37,910; 31,950 | 38,770; 32,680 |
| `credits.cwfc.wfc.phase_in[1].threshold` | 9,480 | 9,690 |
| `credits.cwfc.wfc.additional.amount` 1; 2; 3+ older children | 1,000; 2,270; 2,710 | 1,020; 2,330; 2,770 |
| `subtractions.pension_income.cap` joint; other | 27,080; 13,540 | 27,690; 13,850 |
| `subtractions.{pension_income,social_security}.reduction.start` single/head; joint; separate | 84,490; 108,320; 54,160 | 86,410; 110,780; 55,390 |
| `subtractions.social_security.alternative_amount` single/head; joint; separate | 4,560; 5,840; 2,920 | Same: source explicitly says not indexed |
| `subtractions.social_security.income_amount` single/head; joint; separate | 69,250; 88,630; 44,315 | Same: source explicitly says not indexed |
| `credits.marriage.maximum_amount` | 1,851 | 1,851, provisional hold described above |

The 2025 AMT amounts in the publication differ from the engine's explicit YAML values (71,540; 95,390; 47,700). The fix corrects 2026 only for AMT; this audit's 2025 substitutions are confined to the projected renter entries.

The complete renter table below gives each bracket's lower income bound; the upper bound is one less than the next row. Percentages and credit maxima have the same row alignment in the two years. This table supplies the three existing `credits.renters.{percent_of_income,claimant_share,max_credit}` scales; adjacent repeated amounts are compressed in the module.

| Income lower bound 2025 | Income lower bound 2026 | Income percentage | Claimant share | Maximum 2025 | Maximum 2026 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 1.0% | 5% | 2,720 | 2,780 |
| 6,670 | 6,820 | 1.0% | 10% | 2,720 | 2,780 |
| 8,860 | 9,060 | 1.1% | 10% | 2,640 | 2,700 |
| 11,070 | 11,320 | 1.2% | 10% | 2,580 | 2,640 |
| 15,530 | 15,880 | 1.3% | 15% | 2,500 | 2,560 |
| 19,960 | 20,410 | 1.4% | 15% | 2,440 | 2,490 |
| 22,160 | 22,670 | 1.4% | 20% | 2,380 | 2,430 |
| 24,360 | 24,920 | 1.5% | 20% | 2,300 | 2,360 |
| 28,820 | 29,470 | 1.6% | 20% | 2,240 | 2,290 |
| 31,030 | 31,740 | 1.7% | 25% | 2,240 | 2,290 |
| 33,240 | 34,000 | 1.8% | 25% | 2,240 | 2,290 |
| 37,690 | 38,540 | 1.9% | 30% | 2,240 | 2,290 |
| 39,890 | 40,800 | 2.0% | 30% | 2,240 | 2,290 |
| 46,540 | 47,590 | 2.0% | 35% | 2,240 | 2,290 |
| 53,180 | 54,390 | 2.0% | 40% | 2,240 | 2,290 |
| 62,060 | 63,470 | 2.0% | 45% | 2,040 | 2,080 |
| 64,260 | 65,720 | 2.0% | 45% | 1,830 | 1,870 |
| 66,480 | 68,000 | 2.0% | 45% | 1,550 | 1,590 |
| 68,720 | 70,280 | 2.0% | 50% | 1,360 | 1,390 |
| 70,920 | 72,530 | 2.0% | 50% | 1,220 | 1,250 |
| 73,140 | 74,810 | 2.0% | 50% | 680 | 690 |
| 75,350 | 77,070 | 2.0% | 50% | 270 | 270 |
| 77,570 | 79,330 | Ineligible | Ineligible | 0 | 0 |

Four of the 51 projected 2025 renter entries disagree with the publication: `claimant_share[6].threshold` is 46,530 rather than 46,540; `claimant_share[10].threshold`, `max_credit[15].threshold`, and `percent_of_income[11].threshold` are 77,560 rather than 77,570. The other 47 match.

### Attribution

Scenario 032: `state_refundable_credits → mn_refundable_credits → mn_child_and_working_families_credits`. The formula uses `credits.cwfc.ctc.amount` and the 4% working-family phase-in capped at `credits.cwfc.wfc.phase_in[1].threshold`. Holding these explains the r18 delta exactly at arithmetic precision: `(1750−1800) + .04×(9480−9690) = −58.40`. The published 2026 amount is `1800 + .04×9690 = 2187.60`, matching the frozen credit. The formula also reads joint phase-out 38,770, additional older-child amounts, and the other filing-status phase-out, but they do not alter this household's result. The lone child is age 6, earnings are $29,000, and there is no phase-out or older-child add-on.

Scenario 122: `state_income_tax_before_refundable_credits → mn_income_tax_before_refundable_credits → mn_income_tax_before_credits → mn_basic_tax → mn_taxable_income → mn_deductions → mn_standard_deduction`. The single base deduction is projected at 15,250; its last explicit 2025 value is 14,950. Holding it increases first-bracket tax by `.0535×300 = 16.05`, exactly explaining the r18 move. The published 2026 base is 15,300, implying a convention reduction of `.0535×50 = 2.675`. Two aged/blind additions are $2,000 each in both years. Other projected deductions, exemptions, brackets, Social Security, AMT, and marriage parameters are read in these formulas but do not explain the assigned move.

Renter schedules are relevant to the parameter audit but do not produce either assigned r18 move. `mn_renters_credit_eligible` requires `mn_renters_credit_qualifying_crp`, whose default is false; neither scenario supplies that input. The fix preserves those household inputs and eligibility formulas.

### Full sweep and classified rows

The full sweep completed successfully: **1,984 outputs, 42 Minnesota outputs across scenarios 032 and 122, one Minnesota move, no additional Minnesota movers beyond the r18 candidates**. The other 41 Minnesota outputs match exactly. Result: [r19_mn_convention.csv](work/r19_mn_convention.csv). Machine-readable classified rows: [r19_mn_summary.json](work/r19_mn_summary.json).

| Scenario | Variable | Frozen | Convention | Delta | Classification | Reason |
| --- | --- | ---: | ---: | ---: | --- | --- |
| 032 MN | `state_refundable_credits` | 2,187.60010 | 2,187.60010 | 0.00000 | `unchanged` | Published child-credit and working-family phase-in amounts equal the projections used by this household. |
| 122 MN | `state_income_tax_before_refundable_credits` | 1,028.21655 | 1,025.54150 | −2.67505 | `engine_defect_stale` | The published single standard deduction is $15,300, $50 above the projection. |

The raw CSV also contains nine out-of-state SNAP moves. These are a **reference-snapshot discrepancy**, not a Minnesota-parameter effect: the initial sweep read different reference values from the values recorded as frozen in the r18 output, and the Illinois no-op sweep reproduces the old r18 values. The exact 14 changed reference rows (nine above tolerance and five below) are recorded in [r19_reference_snapshot_difference.json](work/r19_reference_snapshot_difference.json). Every SNAP result below equals the no-op control and its old r18 frozen value. The Minnesota fix's effect on each is therefore `unchanged`; the initial-reference deltas are preserved separately and do not enter the Minnesota convention summary. The final Michigan rerun subsequently read the original frozen bundle; the aggregate report documents that input change.

| Scenario | State | Variable | Frozen | Raw recomputed | Raw delta |
| --- | --- | --- | ---: | ---: | ---: |
| 008 | NJ | `snap` | 15,120.00000 | 15,246.90527 | 126.90527 |
| 012 | MS | `snap` | 4,884.00000 | 4,952.08936 | 68.08936 |
| 038 | LA | `snap` | 7,212.00000 | 7,286.94434 | 74.94434 |
| 043 | CO | `snap` | 3,576.00000 | 3,596.03979 | 20.03979 |
| 054 | NC | `snap` | 6,060.00000 | 6,125.68896 | 65.68896 |
| 066 | VA | `snap` | 3,576.00000 | 3,596.03979 | 20.03979 |
| 079 | AZ | `snap` | 2,376.00000 | 2,428.01733 | 52.01733 |
| 080 | PA | `snap` | 3,576.00000 | 3,596.03979 | 20.03979 |
| 109 | FL | `snap` | 7,932.00000 | 8,020.55420 | 88.55420 |

Five further SNAP differences of −$0.31683 in scenarios 027, 030, 045, 073, and 108 are below tolerance and also shared across family sweeps. Two scenario-112 float serialization differences are below $10^-12.

Validation also passed for module syntax, complete 141/141 projected-2026 coverage, and 51/51 projected-2025 coverage. Applying the actual modifier to a core `ParameterNode` populated from the frozen parameter inventory verifies every resulting 2026 amount and all 51 projected 2025 entries against the source inventory. Three subset attribution runs were interrupted during slow initial parameter loading; attribution above uses the formulas and existing r18 family sweep. An initial full attempt used an unsupported start/stop argument type; it was corrected to annual `period` updates and the full sweep was rerun successfully.

Reproduce from the triage sweep directory, with all output and fix paths inside the assigned workspace:

```sh
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/opus55 \
../.venv-pe1755/bin/python sweep.py \
  --fix /Users/maxghenis/PolicyEngine/_wk/pb-triage-verify-v5b/sweep/fixes/r19_mn_convention.py \
  --out /Users/maxghenis/PolicyEngine/_wk/pb-triage-verify-v5b/sweep/verify/work/r19_mn_convention.csv
```


## Maryland

The federal mover is a stale withholding-deduction parameter. The state mover is a return-deduction projection whose publication status remains **unverified at the freeze**. The supplied module computes a provisional hold for that return deduction and exposes `MD_VERIFIED_ONLY=1` to retain only the verified withholding correction.

### Parameters and attribution

All paths below start with `gov.states.md.tax.income.`. The family contains 25 projected parameters: five return flat amounts, five old maxima, five old minima, and ten CDCC eligibility caps. Ten have projected 2025 entries (the maxima and minima). The complete inventory, engine values, and treatment are in [`work/r19_md_parameters.json`](work/r19_md_parameters.json).

| Parameter / status | Engine 2025 | Engine 2026 | Convention used for 2026 |
|---|---:|---:|---:|
| `deductions.standard.flat_deduction.amount.SINGLE`, `SEPARATE` | 3,350 | 3,400 | 3,350, **provisional hold** |
| Same, `JOINT`, `HEAD_OF_HOUSEHOLD`, `SURVIVING_SPOUSE` | 6,700 | 6,850 | 6,700, **provisional hold** |
| `deductions.standard.max.SINGLE`, `SEPARATE` | 2,750 projected | 2,800 | 3,400 as withholding allowance |
| Same, other three statuses | 5,600 projected | 5,700 | 3,400 as withholding allowance; not read by current formulas |
| `deductions.standard.min.SINGLE`, `SEPARATE` | 1,850 projected | 1,850 | No operative minimum after 2024; unchanged, unused |
| Same, other three statuses | 3,750 projected | 3,800 | No operative minimum after 2024; unchanged, unused |
| `credits.cdcc.eligibility.agi_cap.JOINT` | 174,300 | 178,250 | 174,300, **provisional hold** |
| Same, all other statuses | 112,100 | 114,600 | 112,100, **provisional hold** |
| `credits.cdcc.eligibility.refundable_agi_cap.JOINT` | 91,400 | 93,450 | 91,400, **provisional hold** |
| Same, all other statuses | 60,900 | 62,250 | 60,900, **provisional hold** |

`md_standard_deduction.py` first checks `flat_deduction.applies`, which is true from 2025; it returns the flat amount and does not read the old minimum/maximum calculation. Scenario 068 is single and uses the flat amount. Reducing that amount from $3,400 to $3,350 increases taxable income by $50 and state tax by $50 × 4.75% = $2.375. Scenario 078 itemizes and the state deduction is larger than either flat amount.

The otherwise-obsolete maximum remains live in `md_withheld_income_tax.py`, which reads **only `max.SINGLE` for every person**, irrespective of filing status. The path is:

`max.SINGLE` → `md_withheld_income_tax` → `state_withheld_income_tax` → `state_and_local_sales_or_income_tax` → `salt` → `salt_deduction` → federal itemized deductions → federal taxable income → federal income tax before refundable credits.

The state withholding proxy excludes the taxpayer's Maryland liability calculation. This explains why scenario 078's federal output moves while its Maryland output does not. The r18 hold drops both 2025 and 2026 projected maxima and reaches **$2,700 (2024)**, rather than $2,750 (projected 2025) or $3,350 (published 2025). Its federal delta therefore cannot serve as the correction. The published $3,400 withholding allowance reduces the proxy tax by $600 × 5.5% = $33 and, with uncapped marginal SALT and a 24% federal marginal rate, should increase federal tax by approximately $7.92. That arithmetic is an attribution check; exact floating-point output belongs to the sweep below.

### Sources, dates, and limits

1. **Published 2026 withholding allowance: $3,400, all payroll statuses.** The [Maryland 2026 Employer Withholding Guide](https://www.marylandcomptroller.gov/content/dam/mdcomp/tax/instructions/withholding/2026/withholding-guide.pdf), cover marked **revised December 2025**, explicitly limits this amount to the percentage withholding method (PDF page 2; complete payroll-period table on page 11). A [US Department of the Interior payroll announcement dated April 9, 2026](https://ibc.doi.gov/HRD/Payroll/Announcements/04-09-26) independently records the increase from $3,350 to $3,400 effective January 1, 2026. Thus the amount was public before July 3, even though the guide's exact first upload date is unverified. The guide's $3,400 is a withholding allowance, not a published joint return deduction.

2. **Published 2025 return amounts: $3,350 single/separate/dependent; $6,700 joint/HOH/surviving spouse.** [Chapter 604 / HB352](https://mgaleg.maryland.gov/2025RS/Chapters_noln/CH_604_hb0352e.pdf) replaced the income-dependent minimum/maximum with flat amounts and inflation adjustment after 2025; the [legislative history](https://mgaleg.maryland.gov/mgawebsite/Legislation/Details/HB0352?ys=2025RS) gives approval on **May 20, 2025**. The Comptroller's [Tax Alert, revised December 22, 2025](https://www.marylandcomptroller.gov/content/dam/mdcomp/tax/legal-publications/alerts/tax-alert-changes-to-standard-and-itemized-deductions-and-to-state-and-local-income-tax-rates-from-the-2025-legislative-session.pdf), section IV.A, confirms the amounts and removal of the income phase-in. This proves the engine's projected 2025 $2,750 maximum is stale as a withholding/standard-deduction proxy. There is no operative post-2024 minimum table to replace the five obsolete projected minima with.

3. **2026 return publication status is not established conclusively.** The official [HB411 fiscal note](https://mgaleg.maryland.gov/2026RS/fnotes/bil_0001/hb0411.pdf), dated **February 11, 2026** on its last page, says the 2026 standard deduction had not yet been announced. The currently accessible [2025 Resident Booklet](https://www.marylandcomptroller.gov/content/dam/mdcomp/tax/instructions/2025/resident-booklet.pdf), PDF page 53, gives $3,350/$6,700 in its instructions specifically for estimating **2026** tax. Its first publication and revision dates were not established. The separate [official 2026 estimated-tax worksheet](https://www.marylandcomptroller.gov/content/dam/mdcomp/tax/forms/worksheets/2026-pv-worksheet.pdf), page 1, line 4 instructions, also gives $3,350/$6,700, but has no visible publication date. These sources do not prove that no later return-deduction announcement appeared between February 11 and July 3. The source search located no final 2026 return-deduction schedule. The default fix therefore computes the requested last-published hold **provisionally**; scenario 068's `held_convention` label must remain provisional. If a qualifying pre-freeze source publishes the single return deduction at $3,400, that row becomes `unchanged`.

The statutory measurement window does **not** establish a late-publication hold. [Maryland §10-217(c)](https://mgaleg.maryland.gov/mgawebsite/laws/StatuteText?article=gtg&section=10-217) uses IRC §1(f)(3), substituting base year 2024. [IRC §1(f)(3) and (6)](https://uscode.house.gov/view.xhtml?req=title%3A26+section%3A1+edition%3Aprelim) use the preceding calendar year and the 12 months ending August 31, with the index vintage fixed when that August index is initially published. For tax year 2026 this points to August 2025, whose [BLS release was September 11, 2025](https://www.bls.gov/news.release/archives/cpi_09112025.htm). Thus the measurement timing permits publication before July 3, 2026; it does not prove whether Maryland announced a return amount by then. A further search of official March–July materials located withholding notices and the [standalone 2026 estimated-tax worksheet](https://www.marylandcomptroller.gov/content/dam/mdcomp/tax/forms/worksheets/2025-PV-Worksheet.pdf) carrying $3,350/$6,700, but no conclusive dated return-deduction announcement. The provisional classification is preserved.

4. **CDCC caps.** [2025 Form 502CR](https://www.marylandcomptroller.gov/content/dam/mdcomp/tax/forms/2025/502cr.pdf), printed **10/25**, PDF page 6, gives AGI caps of $174,300 joint and $112,100 all other statuses; refundable caps are $91,400 joint and $60,900 individual. Exact first-publication day is unverified. No 2026 publication/date was located. The module holds all ten caps provisionally at those published values. Both Maryland households have no children or care expenses, so this unresolved timing cannot affect their scored credit outputs.

### Fix, coverage, and results

Fix: [`../fixes/r19_md_convention.py`](../fixes/r19_md_convention.py). It changes parameters only. It covers all five statuses and all ten CDCC caps. It repurposes the obsolete maximum table as the live withholding proxy: $3,350 for 2025 and $3,400 for 2026, without a filing-status split, matching the withholding guide. The old minima remain untouched because they are legally superseded and no longer read. This does not fix the withholding proxy's other simplifications, such as its treatment of withholding exemptions, county taxes, or actual W-2 withholding; those are outside this parameter audit.

The full unmodified triage sweep completed: **1,984 outputs**, **11 moved** by more than $1, of which **2 are Maryland outputs**, with 5 nonzero differences within tolerance. The scan covered all 32 Maryland outputs in scenario_068, scenario_078. There were 0 additional movers beyond the r18 Maryland-family sweep and 9 movers outside Maryland. All nine out-of-state movers and five small differences are SNAP reference-snapshot differences: the initial sweeps' harness reference file differed from the r18 frozen column on exactly those 14 rows, while the Illinois no-op recomputation reproduces the old r18 frozen values on all 14. They are retained in the raw CSV and excluded from Maryland classifications. See [`r19_reference_snapshot_difference.json`](work/r19_reference_snapshot_difference.json). The Maryland frozen values agree across the snapshots.

| Scenario | Variable | Frozen | Convention | Delta | Classification | Reason |
|---|---|---:|---:|---:|---|---|
| scenario_068 | `state_income_tax_before_refundable_credits` | 1252.96777344 | 1255.34277344 | +2.37500000 | `held_convention` (provisional) | Provisional hold of return deduction from $3,400 to published 2025 $3,350; absence of a later pre-freeze return announcement is unverified. |
| scenario_078 | `federal_income_tax_before_refundable_credits` | 24772.69335938 | 24780.61328125 | +7.91992188 | `engine_defect_stale` | Published 2026 withholding allowance is $3,400, not projected legacy $2,800; lower withholding reduces federal SALT and raises federal tax. |

Exact results: [`work/r19_md_convention.csv`](work/r19_md_convention.csv); summary: [`work/r19_md_summary.json`](work/r19_md_summary.json). The verified-only setting omits the provisional return/CDCC holds; it was not separately swept. The 2026 withholding correction and default hold have separate parameter readers, as traced above.

Validation: Python syntax parse passed. The first full attempt exposed the installed core's requirement for `Instant` objects when passing `stop`; the module was corrected to use `update(period=str(year), value=...)`, and the complete sweep above is the successful rerun. Two redundant r18 subset runs were stopped during initial parameter loading to reduce contention; their incomplete results are not used. Attribution is from the installed formulas and existing r18 Maryland-family sweep.


## Michigan

The personal exemption causing scenario 045's r18 move is a verified stale projection: the engine uses $5,950; the published 2026 amount is **$5,900**, not the $5,800 r18 hold.

### Parameters and amounts

All paths below start with `gov.states.mi.tax.income.`. The inventory [`work/r19_mi_parameters.json`](work/r19_mi_parameters.json) covers all **28 projected parameters**, including all **17 projected 2025 entries**. Status tables cover SINGLE, SEPARATE, HEAD_OF_HOUSEHOLD, SURVIVING_SPOUSE, and JOINT; as in the installed table, JOINT receives the joint limit and other engine statuses receive the nonjoint limit.

| Parameter / table | Published 2025 | Convention 2026 | Publication assessment |
|---|---|---|---|
| `exemptions.personal` | 5,800 | 5,900 | Published before freeze |
| `deductions.retirement_benefits.tier_one.amount.*` | 65,897 nonjoint; 131,794 joint | 67,610 nonjoint; 135,220 joint | Published before freeze |
| `exemptions.disabled.amount.base` | 3,400 | 3,400 | Provisional hold; 2026 publication/date unverified |
| `deductions.interest_dividends_capital_gains.amount.*` | 14,688 nonjoint; 29,376 joint | Same published 2025 amounts | Provisional hold; 2026 publication/date unverified |
| `credits.homestead_property_tax.cap` | 1,900 | 1,900 | Provisional hold |
| `.household_resources_limit` | 71,500 | 71,500 | Provisional hold |
| `.property_value_limit` | 165,400 | 165,400 | Provisional hold |
| `.reduction.start` | 62,500 | 62,500 | Provisional hold |
| `credits.home_heating.standard.base[0..5].amount` (0/1, 2, 3, 4, 5, 6 exemptions) | 604; 815; 1,027; 1,239; 1,451; 1,662 | Same published 2025 table | Hold; agency plan schedules 2026 forms for January 2027 |
| `.additional_exemption.amount` | 212 above six exemptions | 212 | Same |
| `.alternate.household_resources.cap[0..3].amount` (0/1, 2, 3, 4+ exemptions) | 18,592; 25,018; 31,449; 34,227 | Same published 2025 table | Same |
| `.alternate.heating_costs.cap` | 3,765 | 3,765 | Same |

The engine's 2025 senior investment limits are already projected ($14,685.5292/$29,371.0583), rather than the published $14,688/$29,376. Its 2025 heating allowances, additional allowance, fuel cap, and four alternate-income caps are also projections; the inventory gives each engine value. The fix uses actual published 2025 values for both 2025 and held 2026 entries, rather than treating the forecast as a published base.

### Primary sources and date evidence

1. [2026 Treasury Form 446](https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Forms/SUW/TY2026/446_Withholding-Guide_2026.pdf), **revision February 2026**, pages 1–2, supplies the personal exemption and retirement limits. [2025 Form 446](https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Forms/SUW/TY2025/446_Withholding-Guide_2025.pdf), **revision January 2025**, supplies their 2025 counterparts. A [DOI payroll announcement dated February 12, 2026](https://ibc.doi.gov/HRD/Payroll/Announcements/02-12-26) independently confirms the exemption's change from $5,800 to $5,900. Exact first upload days of the guides are unverified; both revision months precede the freeze.
2. [2025 MI-1040 instructions](https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Forms/IIT/TY2025/MI-1040-Book.pdf), pages 2–3, 14 and 26–33, give disability, senior investment, and homestead amounts. A precise first publication date was not found; this is a 2025 filing-season booklet for returns due April 15, 2026. Its pre-freeze availability is inferred from that context, not independently established by a dated upload. No 2026 table or release date for these amounts was located; the corresponding 2026 holds are provisional.
3. [2025 MI-1040CR-7](https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Forms/IIT/TY2025/MI-1040CR-7.pdf), **revision January 2026**, line 40, gives the $3,765 fuel cap. Its [instruction book](https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Forms/IIT/TY2025/MI-1040CR-7-Book.pdf), Table A/B (PDF page 12), gives the full allowance and alternate-income tables. The [2025 Taxpayer Assistance Manual](https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Tax-Professional/2025-Taxpayer-Assistance-Manual.pdf), printed pages 83 and 85, independently agrees with these tables. The linked instruction book's exact publication day was not established. The current summary HTML has conflicting entries ($1,207 instead of $1,027, and $18,595 instead of $18,592); the fix follows the matching instruction PDF and manual.
4. The [FY2027 proposed LIHEAP state plan](https://www.michigan.gov/mdhhs/-/media/Project/Websites/mdhhs/Inside-MDHHS/Reports-and-Statistics---Health-Services/Proposed-LIHEAP-State-Plan-27.pdf), page 10, says tax-year 2026 heating forms will be available in January and final benefits are estimates pending funding. This is evidence for January 2027 availability, not an actual publication date. Its own illustrative old fuel cap is not used in place of the filed 2025 form's amount.

### Attribution, fix, and coverage

`exemptions.personal` → `mi_personal_exemptions` → `mi_exemptions` → `mi_taxable_income` → Michigan tax before refundable credits. Scenario 045 is a 44-year-old single filer without dependents, so one $50 reduction from the projected allowance increases tax by $50 × 4.25% = **$2.125**. The r18 increase of $6.375 instead used a $150 reduction. These are arithmetic attribution checks; the table below uses the actual sweep output.

Fix: [`../fixes/r19_mi_convention.py`](../fixes/r19_mi_convention.py). It updates all sourced statuses/brackets and all projected 2025 entries. `MI_VERIFIED_ONLY=1` isolates the six published 2026 leaves and omits held tables. Provisional amounts are never described as conclusively established at the freeze. The full sweep includes Michigan scenarios **045, 072 and 073**, plus every other reference; the full sweep results are below.

### Computed results

| Scenario | Output | Frozen | Convention | Delta | Classification | Reason |
|---|---|---:|---:|---:|---|---|
| 045 | State tax before refundable credits | 1288.837524 | 1290.962524 | +2.125000 | `engine_defect_stale` | The published 2026 exemption of $5,900 replaces the projected $5,950; one exemption raises taxable income by $50 at 4.25%. |

The required full sweep completed **1,984 outputs**, including **52 MI outputs**. No additional state/family movers were found. Raw CSV: [`work/r19_mi_convention.csv`](work/r19_mi_convention.csv). The nine other-state SNAP raw movers and five small SNAP discrepancies are common reference-snapshot differences: their initially read reference amounts differ from r18, and this sweep recomputes the old r18 amounts. They are not effects of this family; see the aggregate report and [`work/r19_reference_snapshot_difference.json`](work/r19_reference_snapshot_difference.json).

A direct formula trace of the final module confirms scenario 045 taxable income rises from $30,325.59 to $30,375.59 while its refundable credits remain $760.78876. Scenarios 072 and 073 retain zero taxable income; all three retain zero home-heating credit. The tracer recorded variable results but no parameter-access nodes, so parameter attribution rests on the installed formulas and controlled reforms, not on interpreting empty trace lists. Trace: [`work/r19_mi_il_trace.json`](work/r19_mi_il_trace.json).

Final expanded-module rerun: [`work/r19_mi_final_convention.csv`](work/r19_mi_final_convention.csv) contains **1,984 outputs and exactly one mover**, scenario 045 (+$2.125). Every computed value exactly matches the earlier full run; only 14 SNAP reference inputs changed when the harness selected the original frozen bundle. The earlier CSV is retained unchanged.


## Missouri (`gov.states.mo.*`)

The assigned `scenario_093` change is attributable to the income-tax bracket thresholds. The convention uses the published **2026** thresholds, not a hold of the 2025 schedule. Publication before the freeze is verified: the Missouri Department of Revenue forms index dates its 2026 withholding formula **November 21, 2025**, and a second official publication reproduces the same annual brackets on **May 14, 2026**. The index date is a revision date, not an independently verified first-upload timestamp. [DOR forms index](https://dor.mo.gov/forms/), [2026 formula, annual table on page 2](https://dor.mo.gov/forms/Withholding%20Formula_2026.pdf), [USDA National Finance Center bulletin](https://help.nfc.usda.gov/bulletins/2026/1773783048.htm)

The complete common schedule for all filing statuses is below. The final infinite threshold is the engine's inactive ninth bracket; the official schedules have no ninth finite boundary. The two thresholds with projected 2025 entries (`rates[0]` and `rates[8]`) remain zero and infinity and therefore match the published schedule. The official 2025 chart is listed with a **December 23, 2025** revision date. [2025 tax chart](https://dor.mo.gov/forms/2025%20Tax%20Chart_2025.pdf), [DOR forms index](https://dor.mo.gov/forms/)

| Parameter suffix | 2025 published | Engine 2026 projection | 2026 convention | Marginal rate above boundary |
|---|---:|---:|---:|---:|
| `rates[0].threshold` | 0 | 0 | 0 | 0% |
| `rates[1].threshold` | 1,313 | 1,342.756404 | 1,348 | 2% |
| `rates[2].threshold` | 2,626 | 2,685.512809 | 2,696 | 2.5% |
| `rates[3].threshold` | 3,939 | 4,028.269213 | 4,044 | 3% |
| `rates[4].threshold` | 5,252 | 5,371.025618 | 5,392 | 3.5% |
| `rates[5].threshold` | 6,565 | 6,713.782022 | 6,740 | 4% |
| `rates[6].threshold` | 7,878 | 8,056.538427 | 8,088 | 4.5% |
| `rates[7].threshold` | 9,191 | 9,399.294831 | 9,436 | 4.7% |
| `rates[8].threshold` | infinity | infinity | infinity | inactive |

Every threshold path begins `gov.states.mo.tax.income.`. The fix is [`sweep/fixes/r19_mo_convention.py`](../fixes/r19_mo_convention.py). It supplies every 2025 and 2026 boundary, including both stable projected 2025 boundaries, and leaves the already correct marginal rates unchanged.

Attribution from installed policyengine-us 1.755.4 formulas: `mo_income_tax_before_credits` reads `gov.states.mo.tax.income.rates` and calls `rates.calc(mo_taxable_income)` per person; state tax aggregates the resulting liability after nonrefundable credits. `scenario_093` has two adult earners and an adult dependent. The supplied r18 Missouri-family attribution CSV changes only its state income-tax output, by +$7.974609375 when the 2025 boundaries are held.

A separate projected parameter, `gov.states.mo.tax.income.deductions.social_security_and_public_pension.mo_max_social_security_benefit`, has a material source gap that does **not** affect these households. The engine's explicit 2025 value is $48,216; the official 2025 Form MO-A instead specifies **$47,633** (Part 3, Section A, line 2; index revision **December 23, 2025**). The fix repairs only 2025 and explicitly preserves the frozen 2026 projection of $49,308.71500083913. This preservation matters because the harness constructs a system that applies reforms before and after uprating. [2025 MO-A](https://dor.mo.gov/forms/MO-A_2025.pdf), [DOR forms index](https://dor.mo.gov/forms/)

The current DOR pension FAQ publishes **$48,967 for 2026**, but its publication date is **unverified**; no dated primary record establishing which side of July 3, 2026 it falls on was found. If pre-freeze, $48,967 applies; if first published after the freeze, the held convention is $47,633. The module does not label either value definitive for 2026. RSMo 143.124(5) defines the state cap by a CPI adjustment to a statutory amount; one should not substitute SSA's national maximum benefit merely because the parameter has a similar name. The displayed statutory version is effective August 28, 2023. [DOR pension FAQ](https://dor.mo.gov/faq/taxation/individual/pension.html), [RSMo 143.124](https://revisor.mo.gov/main/OneSection.aspx?section=143.124)

Neither Missouri household supplies public pension income. Scenario 021 has Social Security and **private** pension income; scenario 093 has earned and interest income. The installed `mo_pension_and_ss_or_ssd_deduction_section_a` applies the projected cap to `taxable_public_pension_income`, which is zero for those facts.

The required full sweep completed **1,984 outputs**. Its Missouri result is:

| Scenario | Variable | Frozen | Convention | Delta | Classification | Reason |
|---|---|---:|---:|---:|---|---|
| 093 | `state_income_tax_before_refundable_credits` | 3,389.650879 | 3,388.245605 | −1.405273 | `engine_defect_stale` | The pre-freeze 2026 bracket boundaries are larger than the engine projections. |

All **40 Missouri outputs** (16 for scenario 021 and 24 for scenario 093) were scanned; no additional Missouri outputs move, including none missed by the r18 hold. The full sweep's raw CSV also contains nine out-of-state SNAP moves and five smaller SNAP deltas. A control calculation with the current global baseline and a no-op clone reproduces all fourteen values exactly: these are **reference-snapshot differences, not Missouri reform effects**, and are not assigned a Missouri convention classification. For these same fourteen rows, the initial harness's frozen values differed from the frozen values recorded in the supplied r18 CSV, and the no-op calculation matches the original r18 values. This identifies a changed reference snapshot without assuming an engine change. See [`work/r19_reference_snapshot_difference.json`](work/r19_reference_snapshot_difference.json). Both the raw result and the control are retained rather than silently removing rows.

Artifacts: [`work/r19_mo_convention.csv`](work/r19_mo_convention.csv), [`work/r19_mo_snap_control.json`](work/r19_mo_snap_control.json), [`work/r19_mo_summary.json`](work/r19_mo_summary.json), and [`work/r19_mo_sources.json`](work/r19_mo_sources.json). The full **1,984-output** [`baseline control`](work/r19_baseline_control.csv) completed and confirms that the Missouri reform has exactly one nonzero effect across the entire bundle; [`attributed effects`](work/r19_mo_attributed_effects.json) records it. Pension-cap invariance is established algebraically in [`work/r19_mo_formula_checks.json`](work/r19_mo_formula_checks.json): all four people have zero public pension income, and `min(public_income, cap)` is zero with either $47,633 or $48,967. This is formula-based evidence, not a completed full-engine sensitivity sweep. An exploratory direct-clone sensitivity method failed in `loss_ald` with a NumPy structured-record type error, so no results from that method are claimed. The full harness sweeps completed successfully. The separate r18 rate-subset run was interrupted during YAML parsing; formula attribution and the supplied family-attribution CSV establish the parameter path instead.

Validation: full reform sweep 1,984 rows; full baseline control 1,984 rows; one attributed reform effect; all 40 Missouri rows checked; static Python syntax and whitespace checks passed. All writes are confined to the assigned workspace.


## Illinois

The r18 mover is **unchanged under the convention**: the engine projected the published $2,925 exemption correctly.

### Parameters, sources, and dates

Both `gov.states.il.tax.income.exemption.personal` and `.dependent` are $2,850 in 2025 and $2,925 in 2026. Neither has a projected 2025 entry. The [IDOR FY 2026-15 bulletin](https://tax.illinois.gov/research/publications/bulletins/fy-2026-15.html), dated **December 2025** (exact day unverified), publishes both annual amounts; its 2025 Schedule IL-E/EITC discussion also identifies the dependent allowance. The [2026 IL-700-T withholding booklet](https://tax.illinois.gov/content/dam/soi/en/web/tax/forms/withholding/documents/currentyear/il-700-t.pdf), **R-12/25**, uses $2,925 for each regular exemption. The convention therefore uses the published 2026 value, not the 2025 hold. The module sets both leaves for all filers and dependents; eligibility and additional aged/blind allowances are unchanged.

### Attribution and fix

Scenario 070 is a single filer without dependents. `exemption.personal` → `il_personal_exemption` → `il_total_exemptions` → `il_taxable_income` → Illinois tax. The r18 hold reduces this person's allowance by $75 and raises tax by $75 × 4.95% = $3.7125; `.dependent` multiplies a zero dependent count and contributes nothing. The formula also reads the personal allowance in its eligibility check, but this taxpayer's eligibility does not change.

Fix: [`../fixes/r19_il_convention.py`](../fixes/r19_il_convention.py). Inventory: [`work/r19_il_parameters.json`](work/r19_il_parameters.json). The other Illinois household is scenario 098; the full sweep includes both, together with every other state. The full sweep results are below.

### Computed results

| Scenario | Output | Frozen | Convention | Delta | Classification | Reason |
|---|---|---:|---:|---:|---|---|
| 070 | State tax before refundable credits | 1650.561279 | 1650.561279 | +0.000000 | `unchanged` | The projected 2026 exemption of $2,925 already equals the amount published in December 2025; the r18 hold at $2,850 would be incorrect. |

The required full sweep completed **1,984 outputs**, including **32 IL outputs**. No additional state/family movers were found. Raw CSV: [`work/r19_il_convention.csv`](work/r19_il_convention.csv). The nine other-state SNAP raw movers and five small SNAP discrepancies are common reference-snapshot differences: their initially read reference amounts differ from r18, and this sweep recomputes the old r18 amounts. They are not effects of this family; see the aggregate report and [`work/r19_reference_snapshot_difference.json`](work/r19_reference_snapshot_difference.json).
