**Verdict: `reference_correct` for the Idaho child-credit flag.** Idaho Code § 63-3029L's $205 nonrefundable child credit expired for taxable years beginning January 1, 2026. PolicyEngine 1.755.4 deliberately implements that sunset. Do not subtract $410 or exclude this scored output for the judge's hypothesis. The applicable benchmark value remains **$6,818.34** after the already-settled Idaho publication convention; the pristine frozen value is **$6,806.79**. The category here adjudicates the child-credit allegation, not the superseded frozen threshold projection.

This is not a new root cause in `triage/root_causes.json`. `c_id_hold_2025` already explains the frozen-to-v1.2 difference. The separate settled `r07_idaho_health_premiums` affects households 007 and 053; their tax values below are isolated baseline/convention checks, not revisions to that finding. Neither settled rule was re-investigated.

**Law available before the July 3, 2026 freeze.** The following primary documents settle the credit's expiration and the relevant 2025 legislation. Supplemental bill-history checks and access limitations are recorded in [law_notes.md](law_notes.md).

| Primary source | What it establishes |
| --- | --- |
| [Idaho Legislature, 2020 HB 574, §3, p.4, printed lines 7–17](https://legislature.idaho.gov/wp-content/uploads/sessioninfo/2020/legislation/H0574.pdf#page=4) | Reproduces §63-3029L(1): $205 for each IRC §24(c) qualifying child, nonrefundable, available to Idaho residents, and restricted to taxable years beginning in 2018 through 2025. The January 1, 2026 cutoff predates HB 40. |
| [Idaho Tax Commission decision 200-814-790-656, p.2](https://tax.idaho.gov/wp-content/uploads/decisions/200-814-790-656.pdf#page=2) | Independently reproduces the statutory amount and expiration date. |
| [July 1, 2026 Idaho Administrative Bulletin, pp.87–88, Docket 35-0101-2601](https://files.dfm.idaho.gov/dfm-admin-website/bulletin/2026/07.pdf#page=88) | The Commission's notice, dated May 29, confirms that §63-3029L ended the credit after December 31, 2025. This contemporaneous confirmation was published two days before the freeze. It proposes administrative cleanup following the existing statutory sunset; the notice itself did not cause expiration. |
| [2025 HB 40, all eight pages, legislative document read on LegiScan's mirror](https://legiscan.com/ID/text/H0040/id/3075079/Idaho-2025-H0040-Introduced.pdf) | §§1–4 amend §§63-3022, 63-3022A, 63-3024 and 63-3025, addressing metals, retirement income and tax rates. §5 applies retroactively to January 1, 2025. It does not amend, repeal or replace §63-3029L. The [official PDF URL](https://legislature.idaho.gov/wp-content/uploads/sessioninfo/2025/legislation/H0040.pdf) was inaccessible. |
| [Governor's March 6, 2025 signing announcement](https://gov.idaho.gov/pressrelease/idaho-delivers-largest-income-tax-cut-in-state-history-sending-another-253-million-back-to-idahoans/) | Confirms HB 40's enactment and the reduction from 5.695% to 5.3%. |

The checked 2026 proposals, [S1450](https://legiscan.com/ID/bill/S1450/2026) and [H0782](https://legiscan.com/ID/bill/H0782/2026), sought to extend the child credit indefinitely. Retrieved secondary legislative histories show neither passed: S1450 stopped after referral to Local Government & Taxation on April 1; H0782 stopped after printing and filing in the Chief Clerk's office on February 27. The [Governor's final April 10 bill-action sheet](https://gov.idaho.gov/wp-content/uploads/2026/04/daily-bill-action_041026_10-AM-MT.pdf) contains neither bill. Official legislative history pages were blocked, so those precise procedural histories were **not independently verified from official journals**. The pre-freeze Commission bulletin independently establishes the operative sunset after the legislative session. The checked 2025 S1057 proposal also retained the cutoff. No comprehensive claim about reading every 2025–2026 session law is made.

The separate parental-choice education credit does not automatically replace the expired $205 credit. The [Tax Commission's March 4, 2026 announcement](https://tax.idaho.gov/pressrelease/parental-choice-tax-credit-deadline-approaches/) describes a refundable program requiring an application for eligible nonpublic-school expenses. Scenario 076 lists no such expenses or school status. This also concerns a refundable program, while the flagged output is before refundable credits.

**Mechanism read in 1.755.4.** Paths below are relative to `/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/.venv-pe1755/lib/python3.13/site-packages/policyengine_us/`.

| Engine path | Observed behavior |
| --- | --- |
| `parameters/gov/states/id/tax/income/credits/non_refundable.yaml` | `2018-01-01: [id_ctc]`; `2026-01-01: []`. This explicit dated list implements expiration. |
| `parameters/gov/states/id/tax/income/credits/ctc/amount.yaml` | Retains the raw $205 amount from 2018. |
| `variables/gov/states/id/tax/income/credits/id_ctc.py` | Multiplies `ctc_qualifying_children` by that amount. Scenario 076 computes two children and raw `id_ctc = 410`. This standalone variable is not the credit actually applied to 2026 liability. |
| `variables/gov/states/id/tax/income/id_non_refundable_credits.py` and `variables/gov/states/tax/income/non_refundable_credit_cap.py` | Read the dated list and apply listed credits subject to remaining liability. An empty list produces zero. |
| `variables/gov/states/id/tax/income/id_income_tax_before_refundable_credits.py` | Subtracts applied nonrefundable credits from `id_income_tax_before_non_refundable_credits`, floored at zero. |
| `variables/gov/states/id/tax/income/id_income_tax_before_non_refundable_credits.py` and `parameters/gov/states/id/tax/income/main/head_of_household.yaml` | Apply the filing-status schedule to taxable income; the applicable marginal rate is 5.3%. The threshold parameter is uprated in the frozen engine. |
| `variables/gov/states/id/tax/income/id_taxable_income.py`, `id_agi.py`, and `deductions/id_deductions.py` | Taxable income is Idaho AGI minus deductions and the separate QBI/Schedule 1-A deduction. The run returns $163,220 − $24,150 − $800 = $138,270. |

The [saved trace and three-household calculations](sweep/work/id_child_credit/idaho_baseline_trace.txt) verify the actual path. The question explicitly states Idaho, tax year 2026, and children ages 13 and 8 living in the tax/benefit household. The engine recognizes both children. This flag does not depend on an unlisted household input or an alternative reading of child eligibility; the decisive input is the stated tax year.

**Values and reach.** [check_idaho.py](sweep/work/id_child_credit/check_idaho.py) scans the entire scenario table and asserts that the only Idaho households are 007, 053 and 076. It runs all three with the reference engine, then separately with the existing `r19_id_convention.py`; it introduces no child-credit reform. All amounts below are sandbox results rounded to cents.

| Household | Listed ages | Qualifying children / raw `id_ctc` | Applied 2026 nonrefundable credits | Frozen = recomputed baseline | Existing convention only |
| --- | --- | --- | --- | --- | --- |
| scenario_007 | 56 | 0 / $0 | $0 | $755.78 | $761.56 |
| scenario_053 | 25 | 0 / $0 | $0 | $2,435.28 | $2,441.06 |
| scenario_076 | 45, 13, 8 | 2 / $410 | $0 | $6,806.79 | $6,818.34 |

For 076 the exact frozen result is `6806.78662109375`. Applying only the settled convention yields `6818.34423828125`, consistent with ($138,270 − $9,622) × 0.053 = $6,818.344 before engine floating-point representation. Hypothetically subtracting the expired credit yields `6408.34423828125` ($6,408.34); this was computed in the diagnostic script and is **not a lawful corrected value**. It would reduce the convention result by $410, well beyond the $1 tolerance. The valid child-credit correction is $0.

**Sweep and moved outputs.** No fix module is warranted: `sweep/fixes/` has no new module. The unchanged harness was run over all 100 households and 1,984 frozen outputs. The [CSV](sweep/out/id_child_credit_baseline.csv) and [log](sweep/work/id_child_credit/baseline_sweep.log) report zero moved outputs and zero nonzero deltas above `1e-6`. Two unrelated CSV float-parsing residuals are approximately `5.68e-14`; every other delta is exactly zero. No output moves for this root cause, including federal downstream outputs.

| Moved output for this flag | Frozen value | Recomputed value | Confirmed |
| --- | --- | --- | --- |
| None (all 1,984 checked) | Each original reference | Matches within `5.69e-14` | Yes |

The three values in the convention column are reconciliation checks for an already-settled rule, not new child-credit movements. Households 007 and 053 lack children; 076's credit is expired. Other states cannot receive this Idaho credit (`defined_for = StateCode.ID`).

**Upstream.** Installed distribution metadata confirms versions 1.755.4 and 2.8.0. The relevant credit amount, dated list and tax-wiring files are byte-identical in both and in inspected `upstream/main` at `2c2e42c08f9c3a163437166c7fed398024ffb892` (September 22, 2026). There is no baseline correction to make. This latest-version conclusion is from source comparison, not a 2.8.0 simulation. See [upstream_notes.md](upstream_notes.md) for exact paths and commits.

Related [PR #7911](https://github.com/PolicyEngine/policyengine-us/pull/7911) implements proposed S1450 as an optional reform whose activation defaults to false. [PR #8856](https://github.com/PolicyEngine/policyengine-us/pull/8856) adds another optional Idaho credit revival while preserving the baseline. [Closed issue #8899](https://github.com/PolicyEngine/policyengine-us/issues/8899) concerns activation leakage from contributed reforms, not this baseline sunset. Commit history establishes the PRs; GitHub API searches failed, so the existence of any other specifically matching issue or PR remains unverified.

Reproduction commands and validation details are in [commands.md](sweep/work/id_child_credit/commands.md). Only this workspace was written. Nothing was filed, posted or pushed.

**Commit limitation:** the assigned branch is `flag-triage`, initially clean at `c53f54e`. The sandbox marks this workspace's `.git` directory read-only. `git add` failed with `Unable to create .../.git/index.lock: Operation not permitted`; no files could be staged or committed. All report and evidence files remain in the assigned workspace for review and commit when Git metadata is writable. No history was rewritten.
