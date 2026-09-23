# Projected-parameter audit of PolicyBench references

Audit date: **2026-09-22**. Reference freeze: **2026-07-03**. Engine: **policyengine-us 1.755.4**, supplied triage environment. Only files in the assigned workspace were written; existing tracked files were preserved. Nothing was filed, pushed, or posted.

Four full **1,984-output** sweeps and one full no-op control identify **14 causal moved outputs**: three `engine_defect_stale` Wisconsin rows and eleven `held_convention` rows. The JSON also includes Wisconsin 108 as `unchanged`. No additional causal output was found beyond the assigned r18/r12 row sets. All affected outputs are listed and sourced in the family sections below.

The **Idaho threshold publication finding remains provisional**, and the exact **FTB 2026 indexing publication date is unverified**. These limitations are explicit below and in the relevant JSON entries. The IRS and California calculations preserve unrelated engine formulas, including withholding/local-sales proxies.

The current reference CSV differs from the saved r18 frozen values on **14 SNAP outputs**: all now equal the earlier r13 held values. The no-op control reproduces those same differences, including nine above $1. These are not effects of the four audited families. Raw sweep CSVs are retained; the shared verification section reconciles every such row.

| Family | Full outputs | Raw moved rows | Causal moved rows | Convention |
|---|---:|---:|---:|---|
| IRS sales-tax tables | 1,984 | 11 | 2 | Published 2025 tables held |
| Wisconsin | 1,984 | 12 | 3 | Published 2026 schedules |
| Idaho | 1,984 | 12 | 3 | 2025 thresholds held, publication status provisional |
| California | 1,984 | 15 | 6 | Sourced 2025 values held; correct older CalEITC breakpoints |

Machine-readable results: [r19_summary.json](work/r19_summary.json). Automated verification: [r19_validation.json](work/r19_validation.json).

## IRS optional state sales-tax tables

The 2026 convention uses the **published 2025 table**, rather than the engine's extrapolation of its 2023 YAML table. The r18 hold removed projected 2025 and 2026 entries but left projected **2024** entries in place; it therefore did not test the last published table. There are 5,358 projected leaves in this family (47 state/DC codes, six family sizes, 19 income brackets), each with projected 2025 and 2026 entries.

### Sources, dates, and convention

| Edition | Verified IRS directory file date | Printed document date | Finding |
|---|---|---|---|
| [2024 Schedule A instructions](https://www.irs.gov/pub/irs-prior/i1040sca--2024.pdf) | **2024-12-20**, 22:10:36 in the [IRS prior-files directory](https://www.irs.gov/downloads/irs-prior?order=uri&page=188&sort=desc) | 2024-12-16, page 1 | Texas table on page 15. |
| [2025 Schedule A instructions](https://www.irs.gov/pub/irs-pdf/i1040sca.pdf) ([archived edition](https://www.irs.gov/pub/irs-prior/i1040sca--2025.pdf)) | **2025-12-18**, 14:10:50 in the [IRS current-files directory](https://www.irs.gov/downloads/irs-pdf?order=uri&page=24&sort=asc); archived file timestamp is three seconds later | 2025-12-08, page 1 | Full state tables on pages 13–17; Texas on page 16. Published before the freeze; these are the held 2026 convention amounts. |
| 2026 | **No publication found as of 2026-09-22** | Not available | The [IRS current-revision page](https://www.irs.gov/forms-pubs/about-schedule-a-form-1040) still links the 2025 instructions, and the IRS directories identify the current edition as 2025. No 2026 table amount or publication date is verified. |

The directory timestamps are verified file dates in the IRS column labeled “Date”; exact first-publication dates were not separately established. Together with the printed editions they provide pre-freeze publication evidence. The date evidence and exact URLs are saved in [sources.json](work/irs_sales_tax/sources.json) and [posting_dates.txt](work/irs_sales_tax/posting_dates.txt). The absence of a located 2026 edition is explicitly a publication-status finding, not an invented future date.

The IRS explains on page 17 that its 2025 tables use the 2024 tables adjusted for sales-tax revenue growth per person, plus Louisiana's changed rate. Thus generic IRS chained-CPI uprating is not the published table methodology. The 2025 engine entries themselves must be replaced, not carried forward unchecked.

### Parameters and complete table coverage

Every changed leaf is `gov.irs.deductions.itemized.salt_and_real_estate.state_sales_tax_table.tax.<STATE>.<FAMILY_SIZE>.<INCOME_BRACKET>`. Family sizes are 1–5 and over 5 (encoded as 6); the table does not have separate filing-status schedules. The 19 bracket lower bounds are $0, $20,000, $30,000, $40,000, $50,000, $60,000, $70,000, $80,000, $90,000, $100,000, $120,000, $140,000, $160,000, $180,000, $200,000, $225,000, $250,000, $275,000, and $300,000. These bounds match the engine; they are not projected.

The fix sets **all 5,814 cells** across 50 states and DC, all six family sizes, and all 19 income brackets for 2025 and 2026. It uses the 46 printed state/DC tables and zero for the five absent-state tables under the worksheet's line-1 instructions. Four zero-table states are absent from raw YAML and are filled by engine homogenization; the reform's second application covers them. This is broader than the two Texas cells, so a national sweep checks households the hold screen could miss. It does not encode the published 2024 edition or change income definitions. Because reforms also run before uprating, inserting 2025/2026 values can prevent creation of earlier 2024 projections; only 2025/2026 table values and 2026 household outputs are in this audit’s verified scope.

The full numeric source table is [published_2025_values.csv](work/irs_sales_tax/published_2025_values.csv); the reform's data file is [r19_irs_sales_tax_2025.json](../fixes/r19_irs_sales_tax_2025.json). [extract_tables.py](work/irs_sales_tax/extract_tables.py) reconstructs it from the saved official-PDF extracts and asserts 51 jurisdictions, six columns, 19 ordered brackets, and the two focal Texas values.

### Texas attribution and local component

`state_sales_tax.py` selects the state, tax-unit size (capped at six), and `state_sales_tax_income_bracket`. The bracket formula sums federal AGI and the income sources listed in `income_sources.yaml`, including exempt interest, veterans' benefits, and exempt Social Security. Both focal households have family size one. Scenario 000 selects bracket 10 ($100,000–$119,999.99); scenario 020 selects bracket 19 ($300,000 and over).

| Scenario | Parameter suffix | Engine YAML 2023 | Published 2024 | Published 2025 / held 2026 |
|---|---|---:|---:|---:|
| 000 TX | `tax.TX.1.10` | 1,402 | 917 | **931** |
| 020 TX | `tax.TX.1.19` | 2,440 | 1,571 | **1,595** |

`variables/gov/local/tax/sales/local_sales_tax.py` computes **0.2 × state_sales_tax**. The coefficient is hardcoded, not a projected parameter; the dollar amount inherits the state-table projection. Holding the published table therefore produces local proxy amounts **$186.20** and **$319.00** and combined state/local sales deductions **$1,117.20** and **$1,914.00** for 000 and 020.

The [computed parameter and household snapshots](work/irs_sales_tax/diagnostics.json) confirm the projected 2025 values differ sharply from the published edition:

| Cell | Engine projected 2024 (r18 carries this forward) | Engine projected 2025 | Engine projected 2026 | Published 2025 / convention 2026 |
|---|---:|---:|---:|---:|
| TX, size 1, bracket 10 | 1,482.153451 | 1,524.884946 | 1,559.443280 | 931 |
| TX, size 1, bracket 19 | 2,579.496733 | 2,653.865383 | 2,714.009703 | 1,595 |

The simulated table-income totals are $111,568.823730 for 000 and $300,150.187500 for 020, confirming the selected brackets. **Both households switch from itemizing to the standard deduction.** For 000, itemized deductions fall from $18,341.332031 to $17,587.199219, below its unchanged $18,150 standard deduction; taxable income rises from $26,095.781250 to $26,287.113281. For 020, itemized deductions fall from $17,090.341797 to $15,747.529297, below its unchanged $16,100 standard deduction; the engine's complete downstream calculation raises taxable income from $283,059.843750 to $283,854.187500. This branch change is why a simple marginal-rate multiplication of the sales-table difference would not reproduce the tax deltas. The diagnostic federal outputs equal the full-sweep values exactly.

The IRS worksheet instead requires the actual local rate. Texas uses the ratio method: local table deduction = state-table amount × local rate / 6.25%. The engine's 20% proxy corresponds to an assumed 1.25% local rate. Neither household states a locality or local rate, so that rate is **unverified from the stated facts**. This parameter audit preserves the proxy and does not claim that the resulting federal amounts repair that separate input/formula limitation.

The downstream path is `state_sales_tax` → `local_sales_tax` → `state_and_local_sales_or_income_tax` (greater of income withholding or combined sales taxes) → `salt` (including real-estate taxes) → `salt_deduction` → itemized deductions → taxable income → federal income tax. The traced formulas are in the installed 1.755.4 package under `variables/gov/states/tax/sales/`, `variables/gov/local/tax/sales/`, and `variables/gov/irs/income/taxable_income/deductions/itemizing/`.

Fix: [r19_irs_sales_tax_convention.py](../fixes/r19_irs_sales_tax_convention.py). Full sweep: [r19_irs_sales_tax_convention.csv](work/r19_irs_sales_tax_convention.csv). The row classification is `held_convention`, because a 2026 edition was not located and the convention carries the published 2025 table; the stale projected 2025 entries are an additional defect in the engine's starting point.

### Computed output verification

The full sweep computed **1,984 outputs**. Exactly **two causal outputs move**, both already detected by r18, but with different convention amounts. All **168 outputs across ten Texas households** were scanned: 000, 003, 020, 030, 052, 060, 083, 088, 101, and 112. All other non-SNAP outputs nationwide are unchanged. The raw CSV also has nine unrelated SNAP moves and five SNAP differences within $1: current frozen SNAP references match r13, while the engine still reproduces the original r18 frozen SNAP values. These shared reference differences are accounted for in the audit-wide control section and are not attributed to the IRS table reform.

| Scenario | Variable | Frozen | Convention | Delta | Classification | Reason |
|---|---|---:|---:|---:|---|---|
| scenario_000 TX | `federal_income_tax_before_refundable_credits` | $2,883.493652 | $2,906.453613 | $+22.959961 | `held_convention` | Published 2025 table replaces extrapolated 2023 cells; local proxy inherits the change. |
| scenario_020 TX | `federal_income_tax_before_refundable_credits` | $68,056.710938 | $68,334.734375 | $+278.023438 | `held_convention` | Published 2025 table replaces extrapolated 2023 cells; local proxy inherits the change. |



## Wisconsin — published 2026 standard deductions and tax brackets

The published 2026 single maximum deduction is **$13,960**, its phase-out starts at **$20,120**, and the first tax bracket ends at **$15,110**. The engine projects $13,870, $19,993.059944, and $15,012.691559, respectively. These are pre-freeze published amounts, so the convention uses the 2026 schedules, not a 2025 hold.

### Primary sources and chronology

| Source | Date evidence read | What it establishes |
|---|---|---|
| [2026 Form 1-ES instructions](https://www.revenue.wi.gov/TaxForms2026/2026-Form1-ES-inst.pdf), pp. 2–3 | Printed revision **R. 1-26**; legal currency date **2026-01-16** on p. 3. [DOR's 2026 forms index](https://www.revenue.wi.gov/Pages/Form/2026Individual.aspx) search extraction shows the final 1-ES item dated **2026-02-06 08:08 AM**. | All published 2026 amounts below; the final indexed edition precedes 2026-07-03. The item's timestamp is not claimed to be its first public release date. |
| [2026 WT-4A worksheet](https://www.revenue.wi.gov/TaxForms2017through2019/w-234f.pdf), p. 2 | Printed revision **R. 11-25**; legal currency date **2025-11-03**. | Independent DOR form prints the same complete 2026 schedules. This corroborates the pre-freeze chronology; its exact first posting day was not verified. |
| [2025 Form 1-ES instructions](https://www.revenue.wi.gov/TaxForms2025/2025-Form1-ES-inst.pdf), printed pp. 2–3 (PDF pp. 3–4) | Printed revision **R. 1-25**, later instruction-update cover for **2025 Wisconsin Act 15**, legal currency date **2025-07-08**. | All published 2025 values below. Exact posting day of the updated PDF was not verified. |
| [2025 Form 1 instructions](https://www.revenue.wi.gov/TaxForms2025/2025-Form1-inst.pdf), p. 13 | 2025 annual instructions; exact posting date not independently established. | Wisconsin has no separate qualifying-surviving-spouse schedule: a federal qualifying surviving spouse may file as Wisconsin head of household. The engine's surviving-spouse-to-joint mapping is a separate limitation, described below. |

The source evidence is the text returned by the web tool: [forms index and combined extracts](work/wi/source_tool_evidence.json), [2025 1-ES](work/wi/source_2025_1es.txt), [2026 1-ES](work/wi/source_2026_1es.txt), and [2026 WT-4A](work/wi/source_2026_wt4a.txt). PDF downloads through the sandbox shell were unavailable. Revision dates and dates through which a document reflects law are distinguished above from publication timestamps.

### Parameters and convention values

All paths below are relative to `gov.states.wi.tax.income`. The r18 inventory contains **22 Wisconsin projected entries, all dated 2026-01-01; none is a projected 2025 entry**. The 2025 columns were checked against DOR's 2025 1-ES schedules. The reform replaces all 22 engine entries for 2026, including all four published filing-status schedules and the engine's existing surviving-spouse alias.

| Parameter suffix | Published 2025 | Engine 2025 | Engine projected 2026 | Published/convention 2026 |
|---|---:|---:|---:|---:|
| `deductions.standard.max.SINGLE` | 13,560 | 13,560 | 13,870 | 13,960 |
| `deductions.standard.max.JOINT` | 25,110 | 25,110 | 25,680 | 25,840 |
| `deductions.standard.max.SEPARATE` | 11,930 | 11,930 | 12,200 | 12,280 |
| `deductions.standard.max.HEAD_OF_HOUSEHOLD` | 17,520 | 17,520 | 17,920 | 18,030 |
| `deductions.standard.max.SURVIVING_SPOUSE` (engine joint alias) | 25,110† | 25,110 | 25,680 | 25,840† |
| `deductions.standard.phase_out.single[1].threshold` | 19,550 | 19,550 | 19,993.059944 | 20,120 |
| `deductions.standard.phase_out.joint[1].threshold` | 28,210 | 28,210 | 28,849.320768 | 29,040 |
| `deductions.standard.phase_out.separate[1].threshold` | 13,390 | 13,390 | 13,693.456402 | 13,780 |
| `deductions.standard.phase_out.head_of_household[1].threshold` | 19,550 | 19,550 | 19,993.059944 | 20,120 |
| `deductions.standard.phase_out.head_of_household[2].threshold` | 57,210 | 57,210 | 58,506.545238 | 58,827 |
| `rates.single[1].threshold`; `rates.head_of_household[1].threshold` | 14,680 | 14,680 | 15,012.691559 | 15,110 |
| `rates.single[2].threshold`; `rates.head_of_household[2].threshold` | **50,480** | **51,130** | 52,288.754729 | 51,950 |
| `rates.single[3].threshold`; `rates.head_of_household[3].threshold` | 323,290 | 323,290 | 330,616.693061 | 332,720 |
| `rates.joint[1].threshold` | 19,580 | 19,580 | 20,023.739832 | 20,150 |
| `rates.joint[2].threshold` | **67,300** | **68,170** | 69,714.930762 | 69,260 |
| `rates.joint[3].threshold` | 431,060 | 431,060 | 440,829.075167 | 443,630 |
| `rates.separate[1].threshold` | 9,790 | 9,790 | 10,011.869916 | 10,080 |
| `rates.separate[2].threshold` | **33,650** | **34,090** | 34,862.578695 | 34,630 |
| `rates.separate[3].threshold` | 215,530 | 215,530 | 220,414.537584 | 221,820 |

† These amounts are the published **joint** schedule retained for the engine alias, not an independently published Wisconsin surviving-spouse schedule. The reform preserves existing filing-status selection formulas. The 2025 explicit second-bracket errors are visible above; even though they are not projected 2025 entries, their 2026 projections are replaced by the correct published 2026 values. The 2025 simulation itself is not changed.

The published marginal rates (3.5%, 4.4%, 5.3%, 7.65%) and deduction phase-out rates (single 12%; joint/separate 19.778%; HOH 22.515% then 12%) agree with the engine and are not projected entries. Their formulas remain unchanged. The HOH switch point is encoded in the existing continuous marginal-scale implementation; this audit does not repair independent whole-dollar table/rounding or filing-status defects.

### Formula attribution and scope

The installed 1.755.4 code at `variables/gov/states/wi/tax/income/wi_standard_deduction.py` reads the selected maximum and phase-out schedule. `wi_taxable_income.py` subtracts that deduction and exemptions from `wi_agi`; `wi_income_before_credits.py` applies the selected tax-rate scale; `wi_income_tax_before_refundable_credits.py` subtracts nonrefundable credits and floors at zero. Thus these parameters directly reach the benchmarked state-tax output. The deduction also reaches `credits/itemized_deduction/wi_itemized_deduction_credit_potential.py`, which feeds the capped itemized-deduction credit. `wi_withheld_income_tax.py` separately reads the single maximum and single tax-rate scale for the engine's withholding proxy, so a full national output sweep also checks downstream federal effects.

Fix: [r19_wi_convention.py](../fixes/r19_wi_convention.py). It accepts optional `WI_PREFIXES` for parameter-subset attribution. Full output CSV: [r19_wi_convention.csv](work/r19_wi_convention.csv). Intermediate diagnostic script: [diagnostics.py](work/wi/diagnostics.py).

### Output verification

The prescribed full sweep completed **1,984 outputs**. It changed **three Wisconsin state-tax outputs**; no additional Wisconsin household or federal/refundable-credit output moved because of the Wisconsin parameters. All four Wisconsin households (042, 064, 091, 108), comprising **82 outputs**, were scanned. The previously unflagged household 108 still has zero state income tax. The three affected state references were already excluded for other defects, as specified in the assignment; these are isolated parameter-correction values, not combined repairs of those other defects.

| Scenario | Variable | Frozen | Convention value | Delta | Classification | Reason |
|---|---|---:|---:|---:|---|---|
| 042 | `state_income_tax_before_refundable_credits` | 284.740906 | 279.234802 | -5.506104 | `engine_defect_stale` | Published single deduction maximum, phase-out start, and first tax threshold replace the projections. |
| 064 | `state_income_tax_before_refundable_credits` | 4,605.997070 | 4,598.476074 | -7.520996 | `engine_defect_stale` | Published joint deduction and first/second thresholds replace the projections; deduction and first-bracket savings exceed the effect of the lower second bracket. |
| 091 | `state_income_tax_before_refundable_credits` | 843.661499 | 838.155457 | -5.506042 | `engine_defect_stale` | Same single-parameter path as 042. |
| 108 | `state_income_tax_before_refundable_credits` | 0.000000 | 0.000000 | 0.000000 | `unchanged` | Additional Wisconsin household: state tax remains zero after replacing the parameters. |

For 042 and 091, the causally active parameters are `max.SINGLE`, `phase_out.single[1].threshold`, and `rates.single[1].threshold`. The deduction rises by $105.232807; the 4.4% marginal rate saves $4.630243, and the larger first bracket saves another $0.875776. For 064, active parameters are `max.JOINT`, `phase_out.joint[1].threshold`, and `rates.joint[1,2].threshold`: the deduction increase saves $10.478765, the first bracket saves $1.136342, and the smaller second bracket adds $4.094377. These independently computed deltas agree with the simulation within $0.0003 (float32 rounding). The formulas and [analytic attribution](work/wi/analytic_attribution.json) establish why each row moves without relying on the blanket hold screen. The data files retain full floating-point results.

The raw CSV also contains **nine unrelated SNAP differences above $1 and five below $1**. A direct file comparison verified for all 14 that its current `frozen` SNAP amount equals the earlier `r13_hold_fy2026_v2.csv` held result, while its recomputed amount equals the original `frozen` amount in `r18_hold_all_projections.csv`. Thus the reference bundle already incorporates the SNAP convention while this isolated Wisconsin reform leaves the engine's SNAP projections in place. These are not Wisconsin effects. The nine above-tolerance SNAP rows are 008, 012, 038, 043, 054, 066, 079, 080, and 109; the five below-tolerance rows are 027, 030, 045, 073, and 108. [Comparison evidence](work/wi/snap_reference_comparison.json) preserves every numeric match. The separate [full empty-reform control](work/r19_noop_control.csv) reproduced all 14 SNAP differences exactly. Comparing all 1,984 Wisconsin-reform results with that control leaves precisely the three Wisconsin state-tax changes above, and every other result is identical; see [control comparison](work/wi/noop_comparison.json). The raw Wisconsin CSV has not been filtered or altered.

Validation completed: Python syntax; exact static coverage of all 22 r18 Wisconsin parameter names; full prescribed sweep; all 82 Wisconsin outputs checked; direct formula-delta reconciliation; exact reconciliation of the 14 unrelated SNAP differences to the earlier source CSVs; and a second full 1,984-output empty-reform control isolating the three Wisconsin changes. The optional intermediate diagnostic script was interrupted during repeated system construction and did not produce an intermediate-value artifact; its contents remain for reproducibility. Three initial subset sweeps were also interrupted during import and are not counted as completed verification. JSON rows are in [r19_wi_summary.json](work/r19_wi_summary.json).


## Idaho

The Idaho projection screen concerns five income-tax thresholds and five retirement-deduction caps. The tax-threshold convention used here is **held at the last verified Idaho-published amounts, with the publication limitation below**. The retirement caps use amounts derived from the statutory formula and SSA's pre-freeze publication. The retirement choice cannot affect these households because none meets the engine's minimum retirement-deduction age.

### Parameters, sources, and dates

In the following table, threshold names abbreviate `gov.states.id.tax.income.main.<status>[1].threshold`; cap names abbreviate `gov.states.id.tax.income.deductions.retirement_benefits.cap.<STATUS>`.

| Parameter / filing statuses | Verified 2025 amount | Engine projected 2026 | Convention 2026 | Basis |
|---|---:|---:|---:|---|
| Threshold: `single`, `separate` | $4,811 | $4,920.031273 | $4,811 | Last verified Commission-published amount; held, subject to limitation below |
| Threshold: `joint`, `head_of_household`, `surviving_spouse` | $9,622 | $9,840.062546 | $9,622 | Same |
| Cap: `SINGLE`, `HEAD_OF_HOUSEHOLD`, `SURVIVING_SPOUSE` | $48,216 | $49,308.715001 | $49,824 | $4,152/month × 12, derived from statute and SSA publication |
| Cap: `JOINT` | $72,324 | $73,963.072501 | $74,736 | $4,152/month × 12 × 1.5, derived from statute and spouse benefit |
| Cap: `SEPARATE` | $0 | $0 | $0 | Separate filers cannot claim this deduction |

1. **Idaho 2025 amounts:** [2025 Individual Income Tax Forms and Instructions, EIN00046](https://tax.idaho.gov/wp-content/uploads/forms/EIN00046/EIN00046_03-02-2026.pdf), printed revision **March 2, 2026**, before the freeze. Printed page 9 (PDF page 11), Form 40 line 20, gives both thresholds and all five filing statuses. Printed page 31 (PDF page 45), Form 39R line 8, gives the single/joint caps and excludes married separate filers. The printed revision date is verified; the first date this edition was posted is not separately verified.
2. **2026 threshold publication unresolved:** the [Commission's tax-rate schedule](https://tax.idaho.gov/taxes/income-tax/individual-income/individual-income-tax-rate-schedule/) and [instruction-edition index](https://tax.idaho.gov/taxes/income-tax/individual-income/forms/individual-income-tax-instructions/) showed **2025 as the latest year** when read on September 22, 2026. No official 2026 indexed threshold or its publication date was located. This supports using the last verified publication for the sweep, but **does not prove that no pre-freeze publication exists**. Consequently the three `held_convention` row classifications below are provisional on that publication question. The official 2026 amount itself remains unverified. [Idaho Code 63-3024(3)](https://legislature.idaho.gov/statutesrules/idstat/title63/t63ch30/sect63-3024/) instructs the Commission to prescribe the annual factor and adopt the CPI measure. The official HTML already saved in the prior 053 investigation was read locally; its relevant text is preserved in `work/id/id_63-3024_excerpt.txt`. This audit did not verify the Commission’s 2026 factor or substitute a newly calculated factor for its publication.
3. **Do not confuse withholding with the tax threshold:** the Commission's [July 31, 2026 release](https://tax.idaho.gov/pressrelease/withholding-tables-updated-for-2026/) links [withholding tables printed July 23, 2026](https://tax.idaho.gov/document-mngr/pubs_EPB00744). Their annual wage cutoffs are $16,100/$32,200. Those tables do not publish the indexed taxable-income thresholds audited here, and their post-freeze date is not evidence of the tax thresholds' publication date.
4. **Retirement-cap statutory formula:** [Idaho Code 63-3022A](https://legislature.idaho.gov/statutesrules/idstat/title63/t63ch30/sect63-3022a/) defines the cap through maximum Social Security benefits at full retirement age, including the spouse's benefit for a joint return and the single-equivalent widow(er) benefit; it directs the Commission to publish amounts annually. The retrieved official text's history ends in 2015; the cap-formula text predates the freeze. [SSA's 2026 fact sheet](https://www.ssa.gov/cola/factsheets/2026.html) gives $4,018/month for 2025 and $4,152/month for 2026. The [October 24, 2025 SSA release](https://www.ssa.gov/news/en/press/releases/2025-10-24.html) links that fact sheet, establishing pre-freeze availability. [SSA’s spouse-benefit explanation, July 11, 2024](https://www.ssa.gov/blog/en/posts/2024-07-11.html), confirms the maximum spouse benefit is 50% of the worker’s full-retirement-age benefit. The annual caps above are **our arithmetic from those sources, not a located Idaho 2026 cap publication**. The 2025 arithmetic reproduces the Commission's caps exactly. An Idaho-specific 2026 publication/date remains unverified.

The engine's only projected **2025** Idaho entry is `cap.SEPARATE`, and it remains zero, consistent with the verified instructions. All other Idaho parameters listed have explicit 2025 values. This was checked against `r18_projected.json` and the installed 1.755.4 YAML, rather than relying on the misleading `last_explicit: 2100-01-01` labels in the supplied post-uprating value dump.

### Attribution

Only scenarios 007, 053, and 076 are in Idaho in the 100-household bundle (60 reference outputs total). The assigned output is `state_income_tax_before_refundable_credits` in each case.

The installed `variables/gov/states/id/tax/income/id_income_tax_before_non_refundable_credits.py` reads `id_taxable_income`, calculates all five status schedules, and selects the household's filing-status result. `id_income_tax_before_refundable_credits.py` subtracts nonrefundable credits and floors at zero. Thus 007 and 053's effective parameter is `main.single[1].threshold`; 076's is `main.head_of_household[1].threshold`.

The retirement path is `id_retirement_benefits_deduction` → `id_subtractions` → `id_agi` → `id_taxable_income`. The cap is read by `id_retirement_benefits_deduction.py`, but its result is the smaller of the cap less head/spouse Social Security retirement benefits and eligible retirement income. The eligibility formula requires age 65, or age 62 if disabled. Household adults are **56, 25, and 45**, respectively; the two children in 076 are 13 and 8. Therefore eligible retirement income and the deduction are zero for all three households regardless of the cap.

At the engine's unchanged 5.3% rate, moving the single threshold from 4,920.031273 to 4,811 adds $5.778657; moving the head-of-household threshold from 9,840.062546 to 9,622 adds $11.557315, before engine float32 rounding. This explains the supplied Idaho-only r18 CSV deltas. The projection audit does not apply the separate missing-health-insurance-subtraction repair: 007 and 053 remain excluded for that other defect, as the user specified.

### Fix and verification

Fix: `sweep/fixes/r19_id_convention.py`. It updates all ten projected Idaho leaves for 2026 and explicitly preserves the sourced zero for the one projected 2025 leaf. Set `ID_RETIREMENT_CAP_MODE=held` to inspect the alternative of awaiting an Idaho cap publication; the source-based age reasoning above establishes that this alternative cannot change the benchmark values. A separate sensitivity run was not completed.

Full sweep: **1,984 outputs; 3 Idaho moves; 9 unrelated SNAP moves against the current reference file** (`sweep/verify/work/r19_id_convention.csv`). All 60 Idaho outputs equal the supplied Idaho-only r18 sweep: the same three move, the other 57 are exactly unchanged, and there are no additional Idaho moves missed by r18. Every non-Idaho recomputed value matches, within 1e-9, the original frozen value recorded in the supplied r18 full sweep. The current reference file has since adopted the SNAP hold: for example, 008 SNAP is now frozen at $15,120.00, whereas r18 recorded $15,246.905273, exactly the present engine recomputation. All 14 unrelated deltas above $0.000001 (9 over $1, 5 within tolerance) are SNAP and are recorded in `work/id/raw_sweep_drift.json`. This establishes a reference-file difference, not a consequence of the Idaho parameters. The raw CSV is preserved without rewriting its deltas. Two attempted r18 subset sweeps and an optional trace process were stopped during engine import to reduce shared filesystem contention; their absence must not be counted as successful validation. Parameter attribution above uses the read formulas and the supplied completed `out/r18_attr/gov.states.id.csv`.

| Scenario | Variable | Frozen | Convention | Delta | Classification | Reason |
|---|---|---:|---:|---:|---|---|
| scenario_007 | `state_income_tax_before_refundable_credits` | $755.778320 | $761.557007 | $+5.778687 | `held_convention` (provisional) | Hold the single taxable-income threshold at the last verified 2025 publication; a 2026 publication/date remains unverified. |
| scenario_053 | `state_income_tax_before_refundable_credits` | $2,435.278320 | $2,441.057129 | $+5.778809 | `held_convention` (provisional) | Hold the single taxable-income threshold at the last verified 2025 publication; a 2026 publication/date remains unverified. |
| scenario_076 | `state_income_tax_before_refundable_credits` | $6,806.786621 | $6,818.344238 | $+11.557617 | `held_convention` (provisional) | Hold the head_of_household taxable-income threshold at the last verified 2025 publication; a 2026 publication/date remains unverified. |


## California confirmation

The freeze convention uses published 2025 amounts. The existing `r12_hold_ca_2025.py` reproduces the five nonrefundable/federal changes, but its refundable-credit result for 023 does **not** hold the correct 2025 CalEITC breakpoint. The 2025 engine values also are not uniformly correct: 56 of the 61 projected fiscal parameters checked agree with the sourced 2025 values; two CalEITC breakpoints and three renter-credit caps differ.

### Sources, publication dates, and convention

| Primary source | Date established by this audit | What was read / convention |
|---|---|---|
| [FTB Tax News, October 2025](https://www.ftb.ca.gov/about-ftb/newsroom/tax-news/2025/10.html) | October 2025 edition; exact first-post day unverified | 2025 brackets, standard deductions, exemption credits, renter caps; June 2024–June 2025 CCPI factor 3.0%. These pre-freeze amounts carry into 2026. |
| [FTB 2025 rate schedules](https://www.ftb.ca.gov/forms/2025/2025-540-tax-rate-schedules.pdf) and [2025 Form 540 booklet](https://www.ftb.ca.gov/forms/2025/2025-540-booklet.html) | Tax-year 2025 publications; exact first-post dates unverified. Brackets and listed credits independently appear in October 2025 Tax News. | All filing-status brackets, exemption credits, and renter caps below. |
| [FTB 2025 Form 3514 booklet](https://www.ftb.ca.gov/forms/2025/2025-3514-booklet.html), [PDF](https://www.ftb.ca.gov/forms/2025/2025-3514-booklet.pdf) | Cached official PDF created 2026-01-06, modified 2026-02-19; these are document metadata, **not independently verified publication dates**. | Earned-income / phaseout starts $4,661, $6,998, $9,823; investment-income ceiling $4,814; young-child/foster-youth amounts $1,189 and phaseout start $27,425; YCTC loss ceiling $35,640. |
| [AB 91, section 2, R&TC 17052(o)](https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=201920200AB91), [R&TC 17052](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=RTC&sectionNum=17052.) | AB 91 approved and filed 2019-07-01; annual index factors below were published by October 2025. | $200/$505 credit breakpoints in 2019, indexed with annual rounding. Derived 2025 values are $252/$636, rather than engine $257/$649. They are statutory computations; the booklet does not print these parameters by name. |
| [FTB October 2021 indexing](https://www.ftb.ca.gov/about-ftb/newsroom/tax-news/october-2021/indexing.html), [October 2023](https://www.ftb.ca.gov/about-ftb/newsroom/tax-news/2023/10.html), [October 2024](https://www.ftb.ca.gov/about-ftb/newsroom/tax-news/2024/10.html), October 2025 above | Respective October editions; exact first-post days unverified | Published 2020–25 factors: 1.4%, 4.4%, 8.3%, 3.1%, 3.3%, 3.0%. |
| [2026 Form 540-ES instructions](https://www.ftb.ca.gov/forms/2026/2026-540-es-instructions.html) | Tax-year 2026 estimated-tax instructions; exact first-post date unverified | Worksheet explicitly uses 2025 tax tables and exemption credits; standard deductions $5,706 / $11,412. |
| [BLS June 2026 CPI release](https://www.bls.gov/news.release/archives/cpi_07142026.htm) | Embargo/release 2026-07-14 | June observations were unavailable at the July 3 freeze. |
| [DIR California CPI percentage-change table](https://www.dir.ca.gov/OPRL/CPI/PresentCCPIchange.PDF) | PDF says last updated **2026-08-12** | June 2025–June 2026 California all-urban CPI change **3.4%**, after the freeze. This is a DIR date, not an FTB publication date. |

**Unverified FTB 2026 publication date:** searches located a purported FTB indexing memorandum dated **2026-09-03**, hosted at [CalTax](https://www.caltax.org/regulatory-issues/ftb/2026-PIT-Indexing-Memo.pdf). The PDF could not be retrieved by the web tool; shell networking could not resolve the host. The date and its printed 2026 amounts have **not** been independently confirmed from that primary document. This report does not substitute DIR's August 12 date for FTB's publication date or claim that FTB has not published the memo. The verified July/August release chronology supports the held convention irrespective of this unresolved exact FTB date.

### Parameter values

All names below have prefix `gov.states.ca.tax.income.`. The complete 61-name comparison, including engine 2025 and projected 2026 values, is [parameter_comparison.json](work/ca/parameter_comparison.json). The fix sets each to its sourced 2025 amount for 2026; it also repairs both projected 2025 CalEITC breakpoints.

| Parameter group | Published 2025 / held convention values | Engine 2025 comparison |
|---|---|---|
| `rates.single`, `rates.separate`, thresholds 1–8 | 11,079; 26,264; 41,452; 57,542; 72,724; 371,479; 445,771; 742,953 | All equal |
| `rates.joint`, `rates.surviving_spouse`, thresholds 1–8 | 22,158; 52,528; 82,904; 115,084; 145,448; 742,958; 891,542; 1,485,906 | All equal; use printed schedules, including upper-bracket rounding |
| `rates.head_of_household`, thresholds 1–8 | 22,173; 52,530; 67,716; 83,805; 98,990; 505,208; 606,251; 1,010,417 | All equal |
| `exemptions.amount`, `exemptions.dependent_amount` | 153 per personal/aged/blind exemption; 475 per dependent | Equal |
| `credits.earned_income.earned_income_amount` and `phase_out.start`, 0 / 1 / 2+ children | 4,661 / 6,998 / 9,823 | Equal |
| `credits.earned_income.eligibility.max_investment_income` | 4,814 | Equal |
| `credits.earned_income.phase_out.final.start`, 0 / 1+ children | **252 / 636**, derived from annual statutory rounding | **257 / 649**, both projected in 2025 |
| `credits.foster_youth.amount[1].amount`, `phase_out.start` | 1,189 / 27,425 | Equal |
| `credits.young_child.amount`, `phase_out.start`, `loss_threshold` | 1,189 / 27,425 / 35,640 | Equal |
| `credits.renter.income_cap`, single / separate | 53,994 | Equal |
| Same, joint / surviving spouse / head of household | **107,988** | **107,987**, $1 below published amount |

The statutory CalEITC sequence (no children / one or more) is 200/505 in 2019, 203/512 in 2020, 212/535 in 2021, 230/579 in 2022, 237/597 in 2023, 245/617 in 2024, and **252/636 in 2025**. `check_caleitc.py` reproduces this using decimal round-half-up each year. FTB's 2025 table is consistent at the transition: no-child credit at earnings $5,451–5,500 is $252, and the one-child credit at $11,801–11,850 is $634 after its final phaseout begins. This checks the breakpoint, not the accuracy of every part of the engine's CalEITC formula.

The raw CPI series itself is an index, not an independently scored statutory amount. The fix overrides its 61 fiscal descendants explicitly, avoiding changes to unrelated parameters. The six filing-status parameter groups already held at explicit 2025 values do not require a projection override.

### Fix, attribution, and r12 correction

Fix: [r19_ca_convention.py](../fixes/r19_ca_convention.py). Full harness output: [r19_ca_convention.csv](work/r19_ca_convention.csv). Attribution script: [diagnose.py](work/ca/diagnose.py). It isolates brackets, exemptions, CalEITC income starts, final-phase breakpoints, and other credits against the same baseline system.

`ca_income_tax_before_credits` applies the filing-status rate schedule to `ca_taxable_income`; `ca_exemptions` computes personal, aged/blind and dependent credits; `ca_income_tax_before_refundable_credits` subtracts nonrefundable credits. This attributes 005 and 099 to joint brackets plus exemption amounts, and 022/023 to single brackets plus exemption amounts. No changed renter eligibility is asserted merely because the cap parameter changes.

For **022 federal**, the code path is:

`ca_withheld_income_tax` (each person's AGI minus the SINGLE standard deduction, passed through `rates.single`) → `state_withheld_income_tax` (CA component in the state's sum) → `state_and_local_sales_or_income_tax` (maximum of income/withholding and sales taxes) → `salt` (adds real-estate taxes) → `salt_deduction` → itemized deductions → federal taxable income and tax. The held single brackets increase this withholding proxy and the SALT deduction, lowering federal tax. This confirms an **engine proxy path**, not a claim about the household's actual withholding or its actual EDD withholding schedule.

The computed 022 withholding proxy rises from **$5,978.141602 to $6,058.852051**, and SALT from **$14,807.141602 to $14,887.851563**. The bracket-only reform reproduces the entire federal change. Full convention diagnostic outputs exactly match the full harness for all CA scored outputs checked. Parameter and calculation snapshots are saved in [parameter_snapshots.json](work/ca/parameter_snapshots.json) and [attribution.json](work/ca/attribution.json).

| Scenario/output | Brackets-only delta | Exemptions-only delta | CalEITC income-start-only delta | CalEITC final-breakpoint-only delta |
|---|---:|---:|---:|---:|
| 005 state | +161.421875 | +6.933594 | 0 | 0 |
| 022 federal | −17.756836 | 0 | 0 | 0 |
| 022 state | +59.285156 | +6.934814 | 0 | 0 |
| 023 state | +2.510818 | +3.467422 | 0 | 0 |
| 023 refundable | 0 | 0 | −1.134277 | −5.320709 |
| 099 state | +118.569336 | +28.464355 | 0 | 0 |

Other-credit overrides have no scored CA effect. The two CalEITC components interact, so their isolated deltas are not expected to sum exactly to the combined change; state-tax differences at the final decimal reflect float32 rounding.

**The r12 refundable result is not a correct held-2025 value.** `CountryTaxBenefitSystem.__init__` applies reforms before uprating (lines 86–94) and again after it (112–113). In r12's first application, `cpi("2025")` reads raw YAML's last value, 2023's **332.035**, rather than forecast 2025's 361.1377838. The final CalEITC breakpoint YAML has only 2019's 200/505; consequently the r12 raw index produces **236/597**. For 023, the engine's existing continuous formula with breakpoint 236 computes **134.0826733**, matching r12 CSV's **134.0826721** within $0.000002. Holding engine 2025's 257 would instead give **144.3009628**. The sourced 2025 breakpoint 252 gives **141.8898417** before float32 rounding. See [caleitc_checks.json](work/ca/caleitc_checks.json). Thus r12's five other output changes have the intended held-amount reason; its CalEITC change includes this construction error.

### Sweep results

The full harness completed with **1,984 outputs**, **six California moves**, nine unrelated SNAP moves, and five unrelated nonzero SNAP deltas below $1. All 14 nonzero SNAP deviations exactly match the common [no-op control](work/r19_noop_control.csv): the current bundle's frozen SNAP entries differ from the original sweep's frozen entries. They are not assigned to this CA reform. The raw CSV is preserved; see [reference drift details](work/r19_reference_drift.json).

| Scenario | Output | Frozen | Convention | Delta | Classification | Reason |
|---|---|---:|---:|---:|---|---|
| 005 | State tax before refundable credits | 41,051.51 | 41,219.87 | +168.36 | held_convention | Hold joint bracket thresholds 1–5 and personal exemptions at 2025 amounts. |
| 022 | Federal tax before refundable credits | 11,131.33 | 11,113.57 | −17.76 | held_convention | Single bracket thresholds 1–5 increase the withholding proxy and SALT deduction. |
| 022 | State tax before refundable credits | 2,439.65 | 2,505.87 | +66.22 | held_convention | Hold single bracket thresholds 1–4 and personal/aged exemption amounts. |
| 023 | State tax before refundable credits | 6.80 | 12.78 | +5.98 | held_convention | Hold first single bracket threshold and personal exemption; renter credit remains $60. |
| 023 | State refundable credits | 148.31 | **141.89** | **−6.42** | held_convention | Hold CalEITC income start at $4,661 and use statutory 2025 final-phase breakpoint $252. |
| 099 | State tax before refundable credits | 4,493.74 | 4,640.78 | +147.03 | held_convention | Hold joint bracket thresholds 1–4 plus personal/dependent exemptions. |

The 023 refundable row additionally contains an `engine_defect_stale` component: the engine's **2025** projected breakpoint was already inconsistent with the pre-freeze statutory amount. Its single row label remains `held_convention` because the 2026 indexing is held. JSON records the additional defect explicitly.

All **100 outputs across five CA households** (005, 022, 023, 031, 099) were scanned. The six causal row identities are exactly the six r12 rows and the six CA tax rows in r18; **no additional CA row was missed**. Household 031 remains unchanged. The only r19-versus-r12 numerical difference is 023 refundable credits, +$7.807175 over r12's incorrect $134.082672. Against the original r18 hold, that row is +$0.968246 (within the $1 output tolerance), because r18 preserves an older projected 2024 breakpoint while dropping its 2025–26 projections.

Other formula defects remain separate: in particular, 023's CalEITC still uses the engine's earned-income-only calculation, and this parameter audit does not repair its missing AGI comparison or other separately audited inputs.

## Shared verification and reference-file differences

All four modules were run from the triage sweep directory using the supplied `sweep.py`, `../.venv-pe1755/bin/python`, and `PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/opus55`. `PYTHONDONTWRITEBYTECODE=1` prevented cache writes outside the workspace. Every output was computed; no scenario filter was used for the final family sweeps. Reproduction pattern:

```bash
cd /Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/sweep
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/opus55 \
../.venv-pe1755/bin/python sweep.py \
  --fix /Users/maxghenis/PolicyEngine/_wk/pb-triage-verify-v5a/sweep/fixes/r19_<family>_convention.py \
  --out /Users/maxghenis/PolicyEngine/_wk/pb-triage-verify-v5a/sweep/verify/work/r19_<family>_convention.csv
```

Family names are `irs_sales_tax`, `wi`, `id`, and `ca`. The full [no-op control](work/r19_noop_control.csv) uses [an empty reform](work/wi/noop_reform.py). Every output outside each family's reported causal set is **bit-identical to the control**. In particular, none of the family fixes causes any SNAP movement.

The table below accounts for all unrelated raw deltas above $0.000001. Two further decimal-serialization differences, each −$0.0000000000000568434, occur at 112 federal refundable credits and payroll tax; both are far below tolerance and identical in every sweep. In every row, the current frozen reference equals the supplied r13 recomputation; the no-op and each family recomputation equal the saved original r18 frozen value. The current reference already contains the held SNAP convention, so these raw differences must not be treated as new exclusions or fixes arising from this audit. They are outside the four-family classification list. [Reference reconciliation](work/r19_reference_drift.json) records all three source CSV paths and exact amounts.

| Scenario | State | Output | Current frozen / existing held convention | Control / original r18 frozen | Raw delta | Above $1? |
|---|---|---|---:|---:|---:|---|
| scenario_008 | NJ | snap | 15,120.000000 | 15,246.905273 | +126.905273 | Yes |
| scenario_012 | MS | snap | 4,884.000000 | 4,952.089355 | +68.089355 | Yes |
| scenario_027 | CT | snap | 288.000000 | 287.683167 | -0.316833 | No |
| scenario_030 | TX | snap | 288.000000 | 287.683167 | -0.316833 | No |
| scenario_038 | LA | snap | 7,212.000000 | 7,286.944336 | +74.944336 | Yes |
| scenario_043 | CO | snap | 3,576.000000 | 3,596.039795 | +20.039795 | Yes |
| scenario_045 | MI | snap | 288.000000 | 287.683167 | -0.316833 | No |
| scenario_054 | NC | snap | 6,060.000000 | 6,125.688965 | +65.688965 | Yes |
| scenario_066 | VA | snap | 3,576.000000 | 3,596.039795 | +20.039795 | Yes |
| scenario_073 | MI | snap | 288.000000 | 287.683167 | -0.316833 | No |
| scenario_079 | AZ | snap | 2,376.000000 | 2,428.017334 | +52.017334 | Yes |
| scenario_080 | PA | snap | 3,576.000000 | 3,596.039795 | +20.039795 | Yes |
| scenario_108 | WI | snap | 288.000000 | 287.683167 | -0.316833 | No |
| scenario_109 | FL | snap | 7,932.000000 | 8,020.554199 | +88.554199 | Yes |

Validation also checks all 1,984 keys, frozen amounts, deltas, and tolerance flags for each sweep; summary completeness; and all four modules' Python syntax. The IRS extraction asserts complete table dimensions, the Wisconsin inventory covers all 22 projected leaves, Idaho covers all ten, and California compares all 61 fiscal projected leaves. The initial IRS run failed because this installed `Parameter.update` requires period objects/strings rather than string `start`/`stop`; it was corrected to annual `period` updates and the complete sweep rerun successfully. Canceled exploratory processes are not counted as successful tests. Optional diagnostic scripts and saved source extracts are included as supporting artifacts; the reports distinguish read formulas, computed checks, and unresolved publication dates.

**Commit limitation:** the assigned branch is `projection-audit`. An authorized commit attempt failed because the sandbox prohibits creating `.git/index.lock` (`Operation not permitted`), and this session has no permission-escalation mechanism. All audit files remain uncommitted in this workspace. History was not rewritten, and nothing was pushed.
