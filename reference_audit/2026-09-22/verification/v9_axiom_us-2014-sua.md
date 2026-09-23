# 1. Verdict

**READY-AFTER — align the protected validator with the encoder that will sign the run, then refresh the immutable dispatch refs.** The amended source is already in the pinned corpus. No new ingestion is needed. Prepare two separate signed encodes: `us/statute/7/2014/e/6` for the SUA/excess-shelter source unit and `us/statute/7/2014/k/4` for the companion state-law energy-assistance treatment. Both can have empty import closures.

Today's rulespec-us main is **`f43dec520dd392bc5333934f56dad7498363e704`**. Its `.axiom/workflow-toolchain.toml` pins axiom-encode `f856cfcb886d9bd050b228aa60aeb4b96939f739`, version `0.2.2006`; the protected signed workflow on main uses `5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9`, version `0.2.2015`. The pinned verifier compares manifest execution repository, commit and version and rejects a mismatch with **`.axiom_encode does not match the running pinned encoder`**. The shared CI workflow passes the expected encoder checkout to that check. This is a code-confirmed prerequisite, not an inferred concern. See [verifier excerpt](scratch/us-2014-sua/workflow/pinned-encoder-identity-check.py.txt) and [workflow evidence](scratch/us-2014-sua/workflow/notes.md).

A dedicated protected validation-toolchain alignment, including its exact-pin fixtures, must land outside this content lane. The current serial chain has #1384 merged, #1387 activation open, and #1386 workflow pin open; its stated changes and the planned Canada corpus re-pin **do not establish encoder identity alignment**. Coordinate the new prerequisite with that chain. The statutory source itself needs neither the Canadian release nor those merges. Do not spend a signed run against today's main expecting landable CI. After any merge, obtain a new exact main SHA; `open_pr=true` requires the current main tip. Max must approve each signed run.

No RuleSpec or test YAML was authored, no local encode ran, and no commit, branch, push, PR, issue or workflow dispatch was made. The later explicit read-only rule governs over the generic initial commit instruction. All new files are report/scratch artifacts inside the assigned workspace. The requested fetch was attempted and denied at `.git/FETCH_HEAD`; GitHub's read-only connector independently confirmed that local `origin/main` equals live main. [Issue #39](https://github.com/TheAxiomFoundation/.github/issues/39) was read through that connector after shell `gh` network access failed.

# 2. Source

Official authorities: [7 USC 2014](https://uscode.house.gov/view.xhtml?req=%28title%3A7+section%3A2014+edition%3Aprelim%29), [7 USC 2012](https://uscode.house.gov/view.xhtml?req=%28title%3A7+section%3A2012+edition%3Aprelim%29), and [P.L. 119-21, §10103](https://www.govinfo.gov/content/pkg/PLAW-119publ21/html/PLAW-119publ21.htm), approved July 4, 2025.

Corpus `origin/main`, independently checked: **`942e138e7a8250c9814e774ac9b8e63008148106`**. The tracked file `data/corpus/provisions/us/statute/2026-07-22-rulespec-title-7-consolidated.jsonl` contains:

| Canonical citation | JSONL line | Resolved source |
|---|---:|---|
| `us/statute/7/2014/e/6` | 135 | Entire excess-shelter paragraph, including amended C(iv)(I) |
| `us/statute/7/2014/k/4` | 162 | Both amended state-law energy-payment clauses |
| `us/statute/7/2012/j` | 50 | All seven elderly/disabled routes |

**`us/statute/7/2014/e/6/C/iv/I` does not exist as a separate corpus record.** Dispatch the real paragraph citation, with complete-source-unit coverage; do not invent a narrower leaf.

Vintage is OLRC **Online@119-100**, expression/source-as-of **2026-06-26**, USLM XML from [the official releasepoint ZIP](https://uscode.house.gov/download/releasepoints/us/pl/119/100/xml_usc07@119-100.zip). Tracked source: `data/corpus/sources/us/statute/2026-07-22-rulespec-title-7-consolidated/2026-07-21-snap-chapter-51-title-7-title-7/uslm/usc7.xml`; retained source SHA-256 `1e85a2d4a9e3068671d2f444ad7faeccc9ed0e5f232ca6f1504dbdfc0a25a3d3`. Exact resolved bodies are in [statutory-text.txt](scratch/us-2014-sua/corpus/statutory-text.txt).

The rulespec pin is **`us-rulespec-2026-08-08-obbb-alien-snap`**, content SHA-256 **`0d69a0cdbe024fc2276f3c261c00402bb0a47488ac5f482cc20bd3404980adbc`**. Its manifest includes the consolidated Title 7 scope. Both amendments are present; the planned August 23 union also contains them. No ingest prerequisite applies.

The resolved C(iv)(I) says the standard shall be available to **“households with an elderly or disabled member”**, with a qualifying payment greater than $20 in the current month or immediately preceding 12 months. In k(4), (A) applies the direct-payment treatment to households **without** such a member; (B) deems qualifying third-party-paid expenses household-paid for households **with** one. The gates run in opposite directions.

For [7 CFR 273.9](https://www.ecfr.gov/current/title-7/subtitle-B/chapter-II/subchapter-C/part-273/section-273.9), canonical corpus citation is `us/regulation/7/273/9`. The pinned `2026-05-10-snap-7-cfr-273-r2026-07-15-self-contained.jsonl` has source date April 29, 2026; main also holds `2026-07-15-title-7-part-273.jsonl`, source date July 9. Both retain the unrestricted LIHEAA shortcut at **(d)(6)(iii)(D)(3)** after regulatory restructuring. Neither contains the conforming elderly/disabled gate. Live eCFR access failed, so conformance after July 9 is **unverified**. Encode the amended statute rather than repeating the unrestricted regulatory branch.

USDA's [August 29, 2025 implementation memo](https://www.usda.gov/sites/default/files/guidance-documents/fns.SNAP-admin-energy-assistance-payments.pdf) preserves the actual-heating/cooling-expense route and addresses ongoing-case recertification. Its [May 8, 2026 Q&A](https://www.usda.gov/sites/default/files/guidance-documents/fns.snap-obbb-restrictionsInternetExpEnergyAssistPayments-QAs1.pdf) distinguishes federally authorized LIHEAP/HUD payments from k(4)'s state-law payments. These guidance documents exist in corpus main's September 13 SNAP-guidance scope, **outside both the pinned and planned August releases**. They inform this reading; the proposed modules do not import them or use their text as pinned-source proofs.

# 3. Existing rulespec-us coverage

Read only the verified `origin/main` snapshot. There is no root `us/statutes/7/2014.yaml`. These are all seven modules beneath `us/statutes/7/2014/`; each has an existing companion test:

| Module suffix | What it encodes; relevant source lines |
|---|---|
| `a.yaml` | Participation basis; lines 13–18 defer `household_eligible_for_snap_participation` subject to the remaining eligibility rules. |
| `c.yaml` | Gross/net income standards; lines 107–109 apply `not household_includes_elderly_or_disabled_member` to the gross-income test. Imports e/6/A. |
| `d.yaml` | Selected income exclusions; lines 10–11 defer aggregate excluded income: `this file encodes selected source-backed leaves only`. |
| `e/2.yaml` | Earned-income deduction; line 24: `max(0, snap_countable_earned_income - work_supplementation_earned_income)`; line 42 multiplies by the deduction rate. |
| `e/2/B.yaml` | Earned-income deduction rate; lines 28–30 set `0.20`. |
| `e/6/A.yaml` | Income after externally supplied shelter deduction; line 43: `max(0, snap_net_income_pre_shelter - snap_excess_shelter_deduction)`. No SUA eligibility rule. |
| `g.yaml` | Resource limits and selected rules; lines 10–11 defer complete `countable_household_financial_resources`. |

None encodes either §10103 amendment. New `e/6.yaml` and `k/4.yaml`, their `.test.yaml` companions, and their ownership manifests are absent. Existing e/6/A is a separate legacy interface; this package does not overwrite it.

`us/regulations/7-cfr/273/9.yaml` contains income tests and utility hooks. Lines 77–128 set each standard/limited/individual utility option to `formula: '0'` and sum the hooks. It does not implement the amendment.

The more specific **`us/regulations/7-cfr/273/9/d/6/iii.yaml` does encode the old unrestricted receipt route**. Lines 89–102 include:

```text
or (
  liheaa_or_similar_energy_assistance_payment_received_or_made_on_household_behalf_in_current_month_or_immediately_preceding_twelve_months
  and liheaa_or_similar_energy_assistance_annual_payment_amount > liheaa_or_similar_energy_assistance_annual_payment_threshold
)
```

Its threshold is 20; the only version starts October 1, 2008. No elderly/disabled input exists. The existing test `liheaa_payment_above_threshold_makes_heating_cooling_standard_available` expects `holds` at $21 without separately incurred costs. Thus this module carries the same **missing elderly/disabled restriction**, although it is not the state-flag implementation used in the supplied sandbox comparison.

Executed that unchanged existing module for a scenario_080-style January 2026 case, assigning all seven local inputs. Assuming the generic $2,000 subsidy is qualifying timely LIHEAP, with no actual utility costs, the result was **`holds`**. That assumption tests the most favorable receipt-route case; its program/timing are not independently stated in the benchmark. [Request](scratch/us-2014-sua/coverage/scenario080-old-gate-request.json) and [explain response](scratch/us-2014-sua/coverage/scenario080-old-gate-response.json) show the unrestricted branch. This is an existing gate execution, not an amended signed encoding or annual SNAP calculation.

`us/statutes/7/2012/j.yaml` also does not adjudicate disability: lines 14–23 merely aggregate an external classification with `count_where(member_of_household, snap_member_is_elderly_or_disabled) > 0`.

# 4. Import closure

**Candidate `existing_signed_imports_json='[]'` for both new modules.** Define an explicit input for the independently resolved §2012(j) status and precise external boundaries for State amounts, State choices and other statutory classifications. Do not silently import the legacy disability aggregator or utility gate. A future module that derives §2012(j) from individual facts needs its own signed encoding.

All relevant manifests found are `axiom-encode/applied-rulespec/v1` with `hmac-sha256`; some modules have no manifest. None qualifies as an existing signed-v5 import. The workflow expects canonical module **file paths**, not corpus citation strings, in a nonempty import list.

The existing root SNAP regulation has this closure:

```text
us:regulations/7-cfr/273/9
  -> us:statutes/7/2012/j
  -> us:regulations/7-cfr/273/10
       -> us:policies/usda/snap/fy-2026-cola/deductions -> 2012/j
       -> us:policies/usda/snap/fy-2026-cola/maximum-allotments
       -> us:statutes/7/2012/j
  -> us:policies/usda/snap/fy-2026-cola/income-eligibility-standards
```

| Existing module | Observed local compile result |
|---|---|
| 273/9/d/6/iii; 2012/j | Load |
| All seven 2014 modules, including c → e/6/A → e/2 → e/2/B | Load |
| FY2026 income-eligibility-standards | Fails: removed plural `corpus_citation_paths` |
| FY2026 deductions; maximum-allotments | Fail: unknown `module.source_verification` field `values` |
| 273/10 | Fails through deductions |
| 273/9 | Fails through 273/10; also contains the independently failing income standards |

No module in this closure reaches 26/32. The proposed empty closure has no blocking imports. The three COLA modules above would block reuse of the broader SNAP composition.

Compile limitation: `axiom-locate engine` returned an older permissive binary. Checks were repeated with the canonical checkout's stricter executable, version `0.2.0`, SHA-256 `faf4383622f63c64b861e5772b78b00df97efef4a8315b792b25219033bee75e`. Its build commit is **unverified**, so these are observed local checks, not proof of compilation at the dispatch engine SHA. Current engine source independently contains the plural-field rejection. Exact commands, copied existing sources, manifest inventory and logs are in [coverage notes](scratch/us-2014-sua/coverage/coverage-notes.md).

# 5. Dispatch inputs

**Reference commands only — do not dispatch before the prerequisite in section 1.** Every current input is populated below; empty strings and empty arrays are intentional. No future SHA has been invented. After protected alignment lands, regenerate both commands against then-current main and its compatible toolchain. If one resulting PR merges before the other run, refresh the second command's `rulespec_ref` too.

Verified ref provenance:

- `rulespec_ref=f43dec…`: local `origin/main`, confirmed by live GitHub `branches/main`.
- `corpus_ref=942e138…`: canonical corpus main, confirmed by GitHub. Actual source content comes from the signed release pinned by rulespec-us, not arbitrarily from this newer checkout.
- `rules_engine_ref=af6e4ea…`: rulespec-us `.axiom/workflow-toolchain.toml`; GitHub compare confirms ancestry of current engine main `6e709eb1ca7ea686263293d932c759d9dee48a4a`.
- Workflow `--ref main`: inspected at encoder `5d80d753…`. The protected encode job requires main, so substituting an old encoder SHA is not a bypass.
- Citations and absent destination/module/test/manifest paths: verified against corpus and rulespec snapshots above. Both replacement fields are empty because these are new source units.

Read the full [workflow](scratch/us-2014-sua/workflow/targeted-signed-reencode.yml.txt), its [validation helper](scratch/us-2014-sua/workflow/prepare_signed_backfill.py.txt), and a real [failed signed-run log excerpt](scratch/us-2014-sua/workflow/run35789753522-excerpts.log). Validation requires full immutable SHAs, exact main for PR creation, existing pinned source, and complete source-unit coverage. `gh workflow run --help` confirms `-F name=@file` sends the file contents. Shell syntax was checked; neither command was executed.

```sh
# CURRENT-BASE REFERENCE ONLY. BLOCKED FROM LANDABLE CI BY ENCODER IDENTITY MISMATCH.
# Do not execute until Max approves and protected validation pins align; refresh exact main refs.
gh workflow run targeted-signed-reencode.yml -R TheAxiomFoundation/axiom-encode --ref main \
  -f 'citation=us/statute/7/2014/e/6' \
  -f 'country=us' \
  -f 'rulespec_ref=f43dec520dd392bc5333934f56dad7498363e704' \
  -f 'pr_base_branch=main' \
  -f 'corpus_ref=942e138e7a8250c9814e774ac9b8e63008148106' \
  -f 'rules_engine_ref=af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca' \
  -F 'review_finding=@scratch/us-2014-sua/review_finding.txt' \
  -f 'repair_run_id=' \
  -f 'source_bundle_json=[]' \
  -f 'existing_signed_imports_json=[]' \
  -f 'replace_rulespec_path=' \
  -f 'replace_legacy_rulespec_path=' \
  -f 'legacy_exact_dependent_rulespec_path=' \
  -f 'second_legacy_exact_dependent_rulespec_path=' \
  -f 'legacy_retained_successor_rulespec_paths_json=[]' \
  -f 'dependent_citation=' \
  -f 'dependent_review_finding=' \
  -f 'second_dependent_citation=' \
  -f 'second_dependent_review_finding=' \
  -f 'open_pr=true' \
  -f 'queue_id=' \
  -f 'queue_item_id=' \
  -f 'queue_manifest_sha256=' \
  -f 'queue_item_generation_sha256=' \
  -f 'queue_dispatcher_run_id='

# CURRENT-BASE REFERENCE ONLY. BLOCKED FROM LANDABLE CI BY ENCODER IDENTITY MISMATCH.
# Do not execute until Max approves and protected validation pins align; refresh exact main refs.
gh workflow run targeted-signed-reencode.yml -R TheAxiomFoundation/axiom-encode --ref main \
  -f 'citation=us/statute/7/2014/k/4' \
  -f 'country=us' \
  -f 'rulespec_ref=f43dec520dd392bc5333934f56dad7498363e704' \
  -f 'pr_base_branch=main' \
  -f 'corpus_ref=942e138e7a8250c9814e774ac9b8e63008148106' \
  -f 'rules_engine_ref=af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca' \
  -F 'review_finding=@scratch/us-2014-sua/review_finding_k4.txt' \
  -f 'repair_run_id=' \
  -f 'source_bundle_json=[]' \
  -f 'existing_signed_imports_json=[]' \
  -f 'replace_rulespec_path=' \
  -f 'replace_legacy_rulespec_path=' \
  -f 'legacy_exact_dependent_rulespec_path=' \
  -f 'second_legacy_exact_dependent_rulespec_path=' \
  -f 'legacy_retained_successor_rulespec_paths_json=[]' \
  -f 'dependent_citation=' \
  -f 'dependent_review_finding=' \
  -f 'second_dependent_citation=' \
  -f 'second_dependent_review_finding=' \
  -f 'open_pr=true' \
  -f 'queue_id=' \
  -f 'queue_item_id=' \
  -f 'queue_manifest_sha256=' \
  -f 'queue_item_generation_sha256=' \
  -f 'queue_dispatcher_run_id='
```

# 6. Review finding text

The exact multiline inputs are [review_finding.txt](scratch/us-2014-sua/review_finding.txt) for e/6, SHA-256 `76e476f8218d206f3efd9990910346ad1766933810e8993fd1e2b6286d1b0ebe`, and [review_finding_k4.txt](scratch/us-2014-sua/review_finding_k4.txt) for k/4, SHA-256 `6af43df28b7a84917add398e63abc3dca3a613fa0c2ffc0059a809513885ffc2`. They carry the required encoding regime verbatim. They request signed generation only and contain no RuleSpec or test YAML.

The e/6 finding requires coverage of **A–E**, not just the desired gate: the 50% excess-shelter calculation and third-party restriction; indexed caps and elderly/disabled exception; optional and mandatory State standards, qualifying costs, central-meter and shared-cost restrictions with their precise exceptions; amended receipt eligibility, separate-standard option, no compelled reduction and season proration; homeless alternative and its exclusions; and internet-fee exclusion. Historical schedules must be encoded or named precisely as deferred historical outputs. CPI series, published State amounts, State elections and separately resolved legal classifications may be explicit boundaries; missing values must not become invented constants or zero legal entitlements.

The k/4 finding separately covers both opposing gates, distinguishes payment amounts from expenses paid, preserves the k(2)(G) exception, and precisely defers other income exclusions and total-benefit calculation. It does not infer that an unspecified energy subsidy is State-law income. The federal LIHEAP and one-time weatherization exclusions remain relevant.

Both findings specify July 4, 2025 amendment applicability, an effective-date boundary test, and a separate deferral of administrative recertification transitions. Both findings require verbatim path-anchored proof excerpts and every local input assigned in every test, including false facts. Paired positive/blocking tests cover $20 versus $21; qualifying member versus generic disability only; payment/timing/State election; actual-cost eligibility without an elderly/disabled member; mandatory-standard exceptions; no-cost households; homeless conditions and anti-stacking; cap exceptions; internet costs; and both k/4 age/disability directions. Broad blanket deferrals are prohibited.

**Disability determination.** The head in scenario_080 is 41, and scenario_100's head is 46. Generic `is_disabled=true` establishes none of §2012(j)'s enumerated routes. The record states no SSI/SSDI or other qualifying assistance, governmental disability retirement, qualifying VA/survivor status, or Railroad Retirement facts. Therefore **neither head is established as a SNAP disabled member on the stated facts**; using the benchmark's absent-input defaults, the resolved predicate is false. This does not mean benefit receipt is always necessary: some statutory VA-status routes independently qualify. Nor does generic Medicaid eligibility or model-generated Medicaid spending establish receipt of disability-related assistance meeting the specified standards. [Official definition](https://uscode.house.gov/view.xhtml?req=%28title%3A7+section%3A2012+edition%3Aprelim%29).

The supplied general audit files stop before r30; the actual affected-row evidence is `triage/sweep/out/r30_on_c13v3.csv`, retained locally as [affected_outputs.csv](scratch/us-2014-sua/affected_outputs.csv). Exactly two rows move. The specified and frozen-bundle household JSONs were checked equal. Household-level reruns of the supplied c13+r30 reform reproduced both corrected annual values exactly; [results](scratch/us-2014-sua/household_results.json) and [arithmetic checks](scratch/us-2014-sua/arithmetic_checks.json) preserve the distinction between reproduced values and independently derived law.

| Worked benchmark | PE 1.755.4 frozen | PE with FY2026 convention | Supplied utility correction | Independent source result |
|---|---:|---:|---:|---|
| scenario_080, PA | $3,596.039794921875 | $3,576.00 | $3,244.799560546875 | SUA receipt route false; utility and excess-shelter deductions $0. With other benchmark assumptions held, whole-dollar allotment is $270/month, **$3,240/year**. |
| scenario_100, MT | $8,625.8896484375 | $8,566.7998046875 | $6,936.00 | SUA false; utility and excess-shelter deductions $0. $6,936 follows the benchmark net-income floor; retaining net-income cents gives **$6,924/year**. MT's election remains unverified. |

**Case 1 — scenario_080.** One adult, age 41; no stated utilities, rent or mortgage payments. A $93,000 mortgage balance is not a shelter payment. Financial assistance is $3,600/year, dividends $16, long-term capital gains $924, energy subsidy $2,000, bank assets about $19,828. Even assuming all $2,000 is qualifying timely LIHEAP, C(iv)(I)'s elderly/disabled condition is unmet. C(ii)(I) also supplies no actual-cost route. The independent provision result is **zero SUA and zero excess-shelter deduction**, supporting the corrected treatment.

Holding the benchmark's income classification, eligibility and published FY2026 schedule fixed: `(3600 + 16)/12 − 209 = 92⅓` monthly net income. The supplied comparator floors this to $92, yielding `298 − .30 × 92 = 270.40`. The separate federal whole-dollar benefit rule yields $270, or $3,240 over twelve identical months; Pennsylvania's own rounding rule produces the same result here. Thus **the statute supports removal of the allowance, but neither $3,576 nor $3,244.80 is the fully rounded annual amount under these held assumptions**. This is not a finding filed against any oracle. [Federal rounding](https://www.govinfo.gov/content/pkg/CFR-2025-title7-vol4/pdf/CFR-2025-title7-vol4-part273.pdf), [Pennsylvania rule](https://www.pacodeandbulletin.gov/secure/pacode/data/055/chapter501/s501.9.html), [FY2026 amounts](https://fns-prod.azureedge.us/sites/default/files/resource-files/snap-fy26maximumAllotments-deductions.pdf).

**Case 2 — scenario_100.** Head age 46 and children ages 6 and 5; earnings $5,914.720703125/year; no energy subsidy, utility bills or housing costs. Generic head disability supplies no §2012(j) route. No payment means the receipt route fails even before considering the new age/disability limitation: this case demonstrates why a State mandatory-standard flag cannot create eligibility without qualifying costs. The independently derived deductions are again **zero**, supporting the corrected treatment.

The rerun supplies annual TANF of $6,064.958984375 as an upstream computed boundary, not a household-stated payment. Holding it and other benchmark rules fixed gives monthly net income `5914.720703125/12 × .8 + 6064.958984375/12 − 209 = 690.727962…`. Flooring net income gives $578/month and the supplied $6,936/year. Preserving cents and rounding the 30% contribution upward gives `785 − ceil(207.218388…) = 577`, or $6,924/year. The scoped corpus/manual and [official Montana budgeting policy](https://dphhs.mt.gov/assets/hcsd/snapmanual/SNAP601-1.pdf) did not establish Montana's cents election. **The statute supports the corrected no-SUA result; it does not independently establish the exact $6,936 total. Neither annual figure can be certified unconditionally from this provision alone.**

**Case 3 — qualifying-member contrast.** State elects a heating/cooling standard; a member is 60, or independently satisfies a qualifying §2012(j) disability route; timely qualifying payment is $21; actual utility costs are zero. C(iv)(I) requires the allowance to be available. Flip only qualifying-member status to false: no receipt entitlement. Set payment to exactly $20 or outside the prior-12-month window: no receipt entitlement. No State dollar amount is invented.

**Case 4 — actual-cost and k/4 contrasts.** An under-60 household with no qualifying disabled member, no energy payment, and $100 of qualifying actual heating expense retains the cost route when the State lawfully uses the standard; removing the expense removes that route. Separately, for a State-law energy payment of $100 and covered expense of $80, no other exceptions, k(4)(A) deems $100 directly payable when qualifying-member status is false, while k(4)(B) deems $0 household-paid. Flip that status to true: the amounts are $0 under (A) and $80 under (B). These are provision-specific deeming amounts, not a complete income-inclusion or allotment calculation.

All annual illustrations use PolicyBench's twelve-month FY2026 freeze. They do not establish actual October–December FY2027 amounts, every other eligibility rule, the subsidy program/timing, ongoing-case recertification history, or upstream TANF entitlement. The new source units should return the legal gates/deductions, not pretend to compute a complete annual SNAP award.

# 7. Risks

| Rejection or interpretation risk | Preparation that addresses it |
|---|---|
| Signing/validator identity mismatch | Named protected pin-alignment prerequisite; current commands withheld. Recheck main and compatible refs after it lands. |
| Citation does not resolve | Use actual e/6 and k/4 corpus records, already in signed release; do not dispatch invented C/iv/I. |
| Incomplete source unit | Finding maps all e/6 A–E branches and both k/4 branches, with specific external dependencies for allowed deferrals. |
| Encoder imports broken legacy modules despite `[]` | Finding explicitly requires no existing-module imports and an empty sequence, not null. Review generated closure before acceptance. |
| Old regulatory rule overrides amended statute | The existing gate run documents missing restriction; encode controlling amended statute. |
| Generic disability substituted for §2012(j) | Explicit legal-status boundary and contrast tests; no invented benefit receipt or VA status. |
| Proof/test rejection | Exact corpus excerpts and every local input explicitly set, including false; paired exception tests. No new waiver exit. |
| Overclaiming full household adjudication | Separate statutory deduction result from comparator arithmetic, benefit rounding, MT uncertainty and the freeze convention. |

Actual failure evidence was read for [run 35789753522](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/35789753522): a null-import attempt failed, and later attempts imported `us:statutes/42/416/l`, whose plural citation field prevented compilation. An empty requested import list alone is insufficient protection. This supports the explicit standalone constraint in the finding.

Open PR searches in rulespec-us and axiom-encode for 2014/273/9 found no exact e/6, k/4 or utility-leaf signed encoding collision. Nearby open work includes rulespec-us #1138, #850, #853/#854 and #891. #1307 and #1363 concern shared metadata; checked file lists do not touch these target paths, but #1363 touches 273/10, 2017/a, COLA, 26/32 and shared compositions. The 30 most recent dispatch runs contained no target collision; today's three were Canada runs 35855033586, 35807158166 and 35807156409. These are point-in-time checks and must be repeated before dispatch. [Saved PR/run evidence](scratch/us-2014-sua/workflow/evidence-summary.json).

Remaining uncertainty is explicit: exact build provenance of the local strict binary, live eCFR conformance after the retained vintage, MT income rounding, unstated statutory disability/program facts, and future main/toolchain SHAs. A signed run and its generated artifacts do not yet exist. Source readiness is established; guaranteed future encoder success is not claimed.

Validation completed: affected-row inventory and household-fact equality checks; corrected household reruns matching both sweep values; independent decimal arithmetic; existing-module compile checks and one all-input Axiom gate execution; read-only workflow/ref/collision checks; reference-command shell syntax. No population simulation or external mutation occurred.

```json
{
  "lane": "us-2014-sua",
  "verdict": "READY-AFTER",
  "citation": "us/statute/7/2014/e/6",
  "in_corpus": true,
  "in_pinned_release": true,
  "existing_modules": [
    "us/regulations/7-cfr/273/9.yaml",
    "us/regulations/7-cfr/273/9/d/6/iii.yaml",
    "us/statutes/7/2012/j.yaml",
    "us/statutes/7/2014/a.yaml",
    "us/statutes/7/2014/c.yaml",
    "us/statutes/7/2014/d.yaml",
    "us/statutes/7/2014/e/2.yaml",
    "us/statutes/7/2014/e/2/B.yaml",
    "us/statutes/7/2014/e/6/A.yaml",
    "us/statutes/7/2014/g.yaml",
    "us/regulations/7-cfr/273/10.yaml",
    "us/policies/usda/snap/fy-2026-cola/income-eligibility-standards.yaml",
    "us/policies/usda/snap/fy-2026-cola/deductions.yaml",
    "us/policies/usda/snap/fy-2026-cola/maximum-allotments.yaml"
  ],
  "blocking_imports": [],
  "dispatch_command": "gh workflow run targeted-signed-reencode.yml -R TheAxiomFoundation/axiom-encode --ref main \\\n  -f 'citation=us/statute/7/2014/e/6' \\\n  -f 'country=us' \\\n  -f 'rulespec_ref=f43dec520dd392bc5333934f56dad7498363e704' \\\n  -f 'pr_base_branch=main' \\\n  -f 'corpus_ref=942e138e7a8250c9814e774ac9b8e63008148106' \\\n  -f 'rules_engine_ref=af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca' \\\n  -F 'review_finding=@scratch/us-2014-sua/review_finding.txt' \\\n  -f 'repair_run_id=' \\\n  -f 'source_bundle_json=[]' \\\n  -f 'existing_signed_imports_json=[]' \\\n  -f 'replace_rulespec_path=' \\\n  -f 'replace_legacy_rulespec_path=' \\\n  -f 'legacy_exact_dependent_rulespec_path=' \\\n  -f 'second_legacy_exact_dependent_rulespec_path=' \\\n  -f 'legacy_retained_successor_rulespec_paths_json=[]' \\\n  -f 'dependent_citation=' \\\n  -f 'dependent_review_finding=' \\\n  -f 'second_dependent_citation=' \\\n  -f 'second_dependent_review_finding=' \\\n  -f 'open_pr=true' \\\n  -f 'queue_id=' \\\n  -f 'queue_item_id=' \\\n  -f 'queue_manifest_sha256=' \\\n  -f 'queue_item_generation_sha256=' \\\n  -f 'queue_dispatcher_run_id='",
  "prerequisites": [
    "Land a dedicated protected validation-toolchain and exact-fixture alignment to the encoder identity that will sign the run; current f856cfcb/0.2.2006 validator does not match 5d80d753/0.2.2015 signing workflow.",
    "After prerequisite and serial-chain merges, refresh exact rulespec main and compatible corpus/engine refs, verify source and absent destinations, and repeat collision checks; displayed command is current-base reference only.",
    "Obtain Max approval for each signed e/6 and k/4 run; no dispatch was made."
  ]
}
```
