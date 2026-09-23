# Idaho health-insurance deduction: signed encoding preparation

Lane `id-63-3022p`; September 22, 2026. Read-only preparation for Max Ghenis. This is an Axiom coverage package, not a finding against an oracle. No repository content was edited, committed, pushed, or dispatched. Only scratch evidence/report files were written, including an unchanged existing module snapshot for a compile check.

## 1. Verdict

**BLOCKED.** The statute is in corpus main, but neither rulespec-us's current signed-release selection nor the specified Canada re-pin endpoint contains it. A checked-in September 14 release manifest selects the needed source; its published signed archive, release-content SHA256, and activation could not be verified. The external prerequisite is to verify/activate an immutable containing release and land its approved rulespec-us pin, then freeze the resulting exact main SHA. The named #1387/#1386/drift/Canada chain alone is insufficient.

The independent reading supports **the corrected value for both households**, conditional on the supplied personal premiums being after-tax taxpayer payments and other return components remaining fixed: scenario_007 **$645.54**, scenario_053 **$2,170.28**. The independently established deductions are $2,080 and $5,000; this is not certification of every component of either return.

Inspected rulespec-us local `origin/main`: **`f43dec520dd392bc5333934f56dad7498363e704`**. The requested fetch failed because `.git/FETCH_HEAD` was not writable. GitHub CLI reads also failed to connect. Therefore this report identifies verified local snapshots, not a refreshed claim about today's live main or active runs. See [access checks](access-checks.md). No passable immutable future dispatch command can truthfully be supplied yet; section 5 preserves the complete current input set as explicitly ineligible.

## 2. Source

Official text: [Idaho Code §63-3022P, Health insurance costs](https://legislature.idaho.gov/statutesrules/idstat/Title63/T63CH30/SECT63-3022P/).

- Exact canonical corpus citation: **`us-id/statute/63-3022P`**, including capital `P`.
- Canonical corpus local `origin/main`: **`942e138e7a8250c9814e774ac9b8e63008148106`**.
- Tracked provision: `data/corpus/provisions/us-id/statute/2026-09-14-income-tax-chapter-us-id-title-63-chapter-30.jsonl`.
- Retained official artifact: `data/corpus/sources/us-id/statute/2026-09-14-income-tax-chapter-us-id-title-63-chapter-30/idaho-statutes-section-html/title-63/chapter-30/63-3022P.html`; substantive text at line 529, history at line 532.
- Format: `idaho-statutes-section-html`; `source_as_of` and `expression_date`: **2026-09-14**. Retained amendment history ends with 2003 chapter 10, section 2. The snapshot date is not a new effective date.
- Source artifact SHA256: **`c413e98e9cb2e5a63dcb20a351046310327c1d5d4a0ee8c54203e9373ca0d0f6`**, independently recomputed and matching the inventory/ingest manifest. See [provision](provision.json), [official HTML snapshot](source-63-3022P.html), and [provenance](corpus-63-3022P-provenance.json).

No statute ingest is needed. `axiom-locate corpus-file 63-3022P` missed it; `git ls-tree`/`git show` in the canonical checkout established its presence. The live Legislature fetch failed, so the retained official artifact supplies the exact text read here.

Release evidence, read from `manifests/releases/` in corpus main:

| Release | Idaho statute scope selected | Contains §63-3022P? |
|---|---|---|
| `us-rulespec-2026-08-08-obbb-alien-snap` — current consumer pin | `2026-07-31-id-title-63-chapter-30-successor` | No |
| `us-rulespec-2026-08-23-canada-338-suspension-union` — specified chain endpoint | Same July 31 scope | No |
| `us-rulespec-2026-09-14-wave4-r2-union` — checked-in later manifest | `2026-09-14-income-tax-chapter-us-id-title-63-chapter-30` (lines 1861–1864) | Its selected source includes P; published signed release unverified |

The July scope has only the five substantive sections 63-3022D, 63-3022E, 63-3024, 63-3024A, and 63-3025D. Current `.axiom/toolchain.toml` pins release-content SHA256 `0d69a0cdbe024fc2276f3c261c00402bb0a47488ac5f482cc20bd3404980adbc`. The September manifest was introduced at corpus commit `8d77a9d2aa7edbab056365273a20bd884a90adb2`; its file hash is not a release-content hash. Both `axiom-locate release` queries for the September wave4 variants returned no local artifact.

Administrative corroboration actually read: [March 2, 2026 Form 40/39R instructions](https://tax.idaho.gov/wp-content/uploads/forms/EIN00046/EIN00046_03-02-2026.pdf), Form 39R line 18 and worksheet, and [current IDAPA 35.01.01](https://proddfmmainsa.blob.core.windows.net/dfm-admin-website/rules/current/35/350101.pdf), Rule 193. These explain excluded prior-accounting amounts and the Idaho standard-deduction treatment. The instructions are for tax year 2025; they supply no independently verified 2026 indexed constants. Their corpus/release inclusion was not established, so they must not be invented as proof sources for the atomic statute encoding.

## 3. Existing rulespec-us coverage

At the inspected rulespec-us SHA, the target primary `us-id/statutes/63-3022P.yaml`, companion, and manifest are absent. The Idaho statute tree has only the following five statute modules and their tests. The two nearby income-tax policies are also listed. None computes this premium deduction; no existing monetary implementation of P was found to compare with the audit's deduction omission/election issue.

| Module | Actual coverage and relevant source excerpt |
|---|---|
| `us-id/statutes/63-3022D.yaml` | Child/dependent care. Summary lines 7–8: “employment-related expenses paid during the taxable year, not to exceed $12,000.” |
| `us-id/statutes/63-3022E.yaml` | Elderly/developmental-disability household deduction. Summary: “$1,000 for each qualifying individual age 65 or older or with developmental disabilities”. |
| `us-id/statutes/63-3024.yaml` | Ordinary tax from supplied taxable income, filing facts, and inflation factor. Lines 7–10: “The tax is 5.3% of taxable income over $2,500, or over $5,000 for joint returns”. No premium calculation. |
| `us-id/statutes/63-3024A.yaml` | Grocery credit and election. Lines 7–13: “refundable grocery tax credits for the taxpayer, spouse, and dependents.” No premium calculation. |
| `us-id/statutes/63-3025D.yaml` | Elderly/developmental-disability household payment and self-filer credit. Lines 7–11: “$100 for each such member, capped at three payments per calendar year.” |
| `us-id/policies/income_tax/pilot_liability_pipeline.yaml` | Caller-supplied income, subtraction, rate, threshold and credit. Lines 32–39 describe an “unverified caller-supplied subtraction”; line 56: `max(0, id_pit_pilot_adjusted_gross_income - id_pit_pilot_supplied_personal_exemption)`. It does not derive the premium deduction. |
| `us-id/policies/income_tax/2026_full_year_resident_source_hold.yaml` | Explicit unavailable computations. Lines 42–44 describe zero sentinels, not legal zero claims. Lines 151–167 declare the income/modification hold below. |

Relevant source-hold lines, unchanged on main:

```text
151  - name: id_pit_2026_income_and_modification_source_hold_applies
156    source: Missing substantive official 2026 Idaho income-base, addition, and subtraction authority in the pinned corpus
165      - effective_from: '2026-01-01'
166        effective_to: '2026-12-31'
167        formula: true
```

**What would lift it:** a signed P module would fill the health-premium component. It would not justify setting this broad hold false. The income-stage hold also requires the federal starting point and complete operative additions/subtractions (lines 64–66), then a source-backed composition wiring them. Full liability additionally requires the deduction/exemption, indexed schedule, surtax, and credit stages (lines 101–103). Resolve those through their own governed encodings/composition work; do not replace this policy using P as its citation. The older [coverage report](/Users/maxghenis/PolicyEngine/_wk/axiom-pb-parity/state/coverage.md) agrees that the target calculation was unavailable.

## 4. Import closure

**Candidate `existing_signed_imports_json`: `[]`.** There are zero proposed signed-v5 imports and thus no imported module whose compilation needs to be assumed. The atomic source can consume payment/coverage/timing/person facts and actual prior-accounting amounts, then derive the deduction. Federal qualification and deduction calculations remain precise external boundaries, not supplied final Idaho answers. No path to 26/32 or its EITC imports is needed.

The inspected workflow helper accepts canonical checkout-relative primary YAML paths, not module IDs, and requires same-jurisdiction tracked signed-v5 manifests (`prepare_signed_backfill.py:1368–1501`). A direct federal `us/statutes/26/*` import is not valid for this `us-id` target. Adjacent 63-3022D's old manifest is v1, not a verified v5 candidate; none of the neighboring modules is needed here.

Two nearby modules are explicitly unsuitable imports:

| Noncandidate module | Compatibility evidence |
|---|---|
| `us-id:policies/income_tax/2026_full_year_resident_source_hold` | Removed plural `corpus_citation_paths` at line 6. Direct compile of a byte-identical main snapshot fails with that exact schema error. [Compile log](compile-checks/source-hold-current.log). |
| `us-id:policies/income_tax/pilot_liability_pipeline` | Same plural declaration at line 6. Pinned engine code rejects that key, independently of its formulas. |

Engine `af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca`, `src/rulespec.rs:819–822`, returns `PluralCorpusCitationPaths` whenever it encounters that key. The direct compile used the available canonical binary; its exact build commit was not established, so the pinned source code is the immutable compatibility evidence. An older binary returned by `axiom-locate engine` did compile the hold, but that legacy result is **not** current compatibility evidence. Compiling against the complete canonical checkout also encountered an unrelated forbidden root-level `programs/` layout; the isolated unchanged snapshot avoided that confounder. No new module was compiled or executed. Details: [coverage and corpus notes](coverage-corpus-notes.md).

## 5. Dispatch inputs

**No eligible command is authorized or available.** The complete command below records verified current inputs and is **WITHHELD / DO NOT RUN**: the current consumer release cannot resolve P. Choosing a newer `corpus_ref` does not fix this. The workflow reads the target RuleSpec checkout's release pin and materializes that release (`targeted-signed-reencode.yml:827–875`); the encoder resolves only its verified release inventory (`corpus_resolver.py:552–578, 991–1003`).

Ref provenance:

| Input | Verified value and origin |
|---|---|
| `rulespec_ref` | `f43dec520dd392bc5333934f56dad7498363e704`, local rulespec-us origin/main; ineligible until additional pin lands |
| `corpus_ref` | `942e138e7a8250c9814e774ac9b8e63008148106`, local canonical corpus origin/main containing P |
| `rules_engine_ref` | `af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca`, rulespec-us `.axiom/workflow-toolchain.toml:7`, and commit/source read in canonical engine |
| Workflow inspected | axiom-encode local origin/main `5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9`; mandated command uses `--ref main`, whose live value could not be refreshed |
| Citation | Exact canonical row `us-id/statute/63-3022P` |
| Replacement / imports / source bundle | Empty replacement (new absent statute target); `[]` imports; `[]` bundle |

All 25 workflow inputs are explicit below. `-F review_finding=@...` reads the exact accompanying text file; `-F open_pr=true` sets the workflow's Boolean-typed input to true. This command was not executed.

```sh
gh workflow run targeted-signed-reencode.yml \
  -R TheAxiomFoundation/axiom-encode --ref main \
  -f citation=us-id/statute/63-3022P \
  -f country=us \
  -f rulespec_ref=f43dec520dd392bc5333934f56dad7498363e704 \
  -f pr_base_branch=main \
  -f corpus_ref=942e138e7a8250c9814e774ac9b8e63008148106 \
  -f rules_engine_ref=af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca \
  -F review_finding=@scratch/id-63-3022p/review-finding.txt \
  -f repair_run_id= \
  -f source_bundle_json='[]' \
  -f existing_signed_imports_json='[]' \
  -f replace_rulespec_path= \
  -f replace_legacy_rulespec_path= \
  -f legacy_exact_dependent_rulespec_path= \
  -f second_legacy_exact_dependent_rulespec_path= \
  -f legacy_retained_successor_rulespec_paths_json='[]' \
  -f dependent_citation= \
  -f dependent_review_finding= \
  -f second_dependent_citation= \
  -f second_dependent_review_finding= \
  -F open_pr=true \
  -f queue_id= \
  -f queue_item_id= \
  -f queue_manifest_sha256= \
  -f queue_item_generation_sha256= \
  -f queue_dispatcher_run_id=
```

After release activation and the approved pin change, re-read all refs, inspect current workflow changes, validate release provenance against `corpus_ref`, and replace the recorded RuleSpec SHA with the then-current exact main tip. The workflow checks exact base equality at entry and again before PR publication (`prepare_signed_backfill.py:267–331`; workflow lines 3589–3593). Serialize main merges during the run; the ongoing chain can invalidate an otherwise valid base. Recheck collision/attempt budget and obtain Max's approval. No waiver, workflow-pin, CODEOWNERS, or toolchain edits belong in this feature encoding.

The protected `production-signing` job and `/opt/axiom-verification/axiom-encode encode --backend openai ... --apply --require-complete-source-unit` invocation were read in workflow lines 169–185 and 1268–1284. Local encoding is not a substitute. All workflow constraints and defaults: [dispatch contract](dispatch-contract.md).

## 6. Review finding text

The exact proposed `review_finding` is [review-finding.txt](review-finding.txt), reproduced below; SHA256 `9299baef4a8e5a64e0d8f7ac43129696dd114ae06ccd4e8e135249362a3bdf1d`. It covers four worked cases and the required paired tests; it is prose for the supervised encoder, not RuleSpec or test YAML.

The two moved sweep rows and independent arithmetic, in dollars:

| Household | Frozen 1.755.4 | Sandbox corrected | Statutory premium deduction | Independent conditional tax | Reading |
|---|---:|---:|---:|---:|---|
| scenario_007 | 755.77832 | 645.53833 | 2,080 | 645.5383203125 → **645.54** | Supports corrected value |
| scenario_053 | 2,435.27832 | 2,170.27832 | 5,000 | 2,170.2783203125 → **2,170.28** | Supports corrected value |

This conclusion comes from the retained official statute's taxpayer-payment and anti-duplication rule, not the fix docstring. Both households use Idaho standard deductions; none of the personal premium is already deducted/accounted for under the explicit case assumptions. The separately read §63-3024 rate is 5.3%, giving exact marginal changes $110.24/$265.00. Baseline household reruns reproduced the frozen references exactly. The 2026 indexed threshold and unrelated credits were held fixed, not independently certified. See [full adjudication and source/fact evidence](adjudication.md), and [rate provision](rate-provision.json).

```text
Encode the complete source unit us-id/statute/63-3022P, Idaho Code section 63-3022P, from the verified signed corpus release selected by rulespec-us. This is an Axiom coverage request and independent statutory expectation, not an oracle finding. Do not run until the containing Idaho scope is in the consumer's verified release. Use the signed workflow only. No local encoding or hand-authored RuleSpec or companion YAML is authorized by this preparation package.

Cover the individual taxpayer's amount actually paid during the taxable year for medical-care insurance covering the taxpayer, spouse, or dependents. Compute the additional Idaho deduction only for dollars not otherwise deducted or accounted for for Idaho income tax. Do not accept a supplied final Idaho premium subtraction as an input. Use underlying payment amounts, timing, payer, insured relationship, coverage facts, and the nonoverlapping portion of those same payments already deducted/accounted for. Reject invalid negative payment/accounting inputs or make the valid nonnegative input domain explicit; never deduct a dollar twice.

Cover the entire statutory insurance definition: hospital or medical policy/certificate, subscriber contract, specific-disease insurance, hospital-confinement indemnity, accident-only, dental, vision, single-employer self-funded retained-risk coverage, student health benefits, and medical-care/treatment coverage supplementing liability insurance. The word includes is not authority to exclude all other medical-care insurance. Do not transform employer-paid retained risk into an amount paid by the taxpayer. An employee's after-tax contribution to qualifying employer coverage can qualify.

Account explicitly for the third sentence's employer duty to disclose whether employee health contributions were excluded from taxable income. Prefer an obligation output. If administrative compliance is outside the individual's monetary interface, precisely defer only that named statement-compliance output, grounded to that sentence and with the missing employer/employee compliance interface stated. Do not silently omit the sentence; receipt of a statement is not an express statutory condition for the deduction.

Precise external boundaries: this section consumes facts about spouse/dependent status and amounts already deducted/accounted for; federal AGI, federal dependency, business/SEHI and Schedule A calculations require separate governing units and are not recreated here. An itemized amount counts only if actually retained for Idaho. Standard deduction selection does not itself account for the premium. Honor the actual Idaho election; optimizing the whole state return is a separate composition. Idaho MSA and long-term-care computations (63-3022K/Q), nonresident allocation, tax rates/thresholds, credits, and complete liability are also separate. State clearly that the atomic deduction does not clear the entire 2026 income/modification source hold.

Administrative corroboration was read in official tax-year-2025 instructions EIN00046_03-02-2026.pdf, Form 39R line 18/worksheet and Form 40 deduction election, and current IDAPA 35.01.01 Rule 193. They explain pretax, MSA, business, and actual Idaho itemization accounting. Do not cite them as corpus proof unless separately resolved inside the consumer's verified release. Do not import their 2025 dollar constants into 2026. This statutory encoding can use actual prior-accounting facts without encoding the external worksheet formula or election optimizer. No imports are requested: existing_signed_imports_json=[].

Worked case 1 -- scenario_007, tax year 2026: single Idaho resident, age 56, no spouse/dependents; personal qualified insurance paid during the year 2080; wholly taxpayer-paid after tax; employer-paid premiums 6309.27587890625 are separate and excluded; pretax personal premiums 0; SEHI/business deduction of the same premiums 0; no MSA funding or other prior accounting; Idaho standard deduction selected. Expected section 63-3022P deduction: 2080. The two input aliases health_insurance_premiums_without_medicare_part_b and other_health_insurance_premiums both describe these same 2080 dollars; do not sum them. Benchmark baseline Idaho AGI 35280, standard deduction 16100, taxable income 19180; premium deduction makes these 33200 and 17100. Frozen PolicyEngine 1.755.4 tax before refundable credits: 755.77832; sandbox corrected: 645.53833. Statutory premium delta at the separately read section 63-3024 rate of 5.3% is 110.24; holding unrelated return components fixed gives 645.5383203125, or 645.54. The statute supports the corrected value under the explicit after-tax facts, not the frozen omission.

Worked case 2 -- scenario_053, tax year 2026: single Idaho resident, age 25, no spouse/dependents; employment income 66968.6796875; qualified personal medical insurance paid in year 5000; after-tax taxpayer payment; separate employer-paid premiums 3389.27587890625 excluded; pretax amount 0; SEHI/business deduction 0; no MSA or other prior accounting; Idaho standard deduction selected, 16100. The potential medical/Idaho itemized deduction is 377.34863, but is not used on this Idaho standard-deduction return. Expected premium deduction: 5000, not 4622.65137. Frozen tax: 2435.27832; sandbox corrected: 2170.27832. Statutory tax reduction: 265; conditional resulting tax: 2170.2783203125, or 2170.28. The statute supports the corrected value. As in case 1, the two premium aliases are one payment. The premium input's after-tax character must be explicit in generated tests; has_esi=true alone establishes neither pretax treatment nor disqualification.

Worked case 3 -- partial prior accounting: individual pays 8000 of otherwise qualifying own/spouse/dependent medical insurance during the year; 2000 of those same dollars is already deducted in AGI and retained for Idaho; another nonoverlapping 1000 is actually used in Idaho itemized medical deductions; no other exclusions. Expected additional deduction: 5000. A paired blocking test with all 8000 already accounted for must produce zero. Account for overlap before aggregating exclusions; never subtract the same payment twice.

Worked case 4 -- election integration boundary: given otherwise valid AGI 60000, eligible premiums 10000, supplied medical deduction 5500, Idaho itemized deductions 20200, allowed standard deduction 16100, and no mandatory-itemization restriction. Under actual Idaho itemization, premium deduction is 4500 and combined reductions are 24700. Under actual Idaho standard selection, premium deduction is 10000 and combined reductions are 26100. The standard route gives taxable income 33900 rather than 35300. These are supplied integration amounts, not constants to encode under this section. The atomic module must honor the election/accounting facts; the external optimizer and worksheet allocation require their own authority.

The benchmark full-tax expectations certify only this subtraction's effect with other components held fixed. They are not outputs to invent in the atomic premium module. The primary numerical companion assertions are the statutory deductions. Cent-level tax comparisons are integration evidence; floating-point tails in the sweep are not legal rounding rules.

Paired positive and blocking tests: taxpayer/spouse/dependent versus unrelated nondependent insured; paid this year versus another year; taxpayer-paid versus wholly employer-paid; medical versus nonmedical insurance; after-tax employee contribution versus pretax amount; ordinary funds versus already-accounted-for Idaho MSA funds; zero versus positive overlapping business/SEHI deduction; Idaho standard election versus actual Idaho itemized use; no, partial, and full prior accounting; and employer statement addressing both excluded and nonexcluded contributions without inventing a receipt gate. Exercise each enumerated insurance category, and both zero and positive monetary amounts. Every generated companion case must explicitly assign every local input, including all false Booleans. Ground proof atoms to exact substrings of the resolved statutory unit; source dates are snapshot dates, not statutory effective-date amendments. Use the singular corpus_citation_path schema. Do not import the held annual Idaho policy, its pilot, or the federal EITC closure.
```

## 7. Risks

| Risk / likely rejection | How this package addresses it |
|---|---|
| Citation outside the pinned release | Blocks dispatch. Requires a verified signed release containing the September Idaho scope and an approved consumer pin; later corpus checkout alone cannot help. |
| Moving main, serial re-pin chain | Records immutable local refs and explains both base checks. Future refs cannot be invented; orchestrator must refresh after prerequisites and serialize merges. |
| Incomplete source unit | Finding explicitly covers all insurance categories, taxpayer/insured/timing conditions, anti-duplication, and the employer-statement duty; only named external computations or administrative output may be precisely deferred. |
| Unassigned false facts / untested exception | Finding requires every local input in every companion and paired positive/blocking cases. It distinguishes actual Idaho itemization from an unused federal medical amount. |
| Invalid proofs / invented administrative authority | Exact resolved statutory substrings only. Form and Rule 193 are corroboration unless separately verified in the consumer release. No 2025-to-2026 dollar extrapolation. |
| Broken imports | Empty requested closure avoids both Idaho plural-path policies and the federal EITC closure. No unverified signed-v5 dependency is offered. |
| Duplicate premiums / unspecified after-tax status | Cases separate employer-paid amounts, identify duplicate premium input aliases, and explicitly state taxpayer payment, after-tax treatment, and zero prior accounting. |
| Overclaiming full annual output | Primary assertions are premium deductions; full-tax values are conditional comparisons. P alone does not lift every annual return hold. |

**Collisions and live run state remain unverified.** Required `gh pr list` calls for both repositories and the last-30 targeted runs call all failed. Public fallback did not provide today's target-specific PRs or runs. Cached local branch names include old Idaho annual-return and oracle-workflow work but establish neither open status nor a current P encoding. The orchestrator must repeat searches for `us-id/statute/63-3022P`, `63-3022P`, and the canonical target path on both repositories and today's workflow runs before approval. No assertion of “no collisions” is made. Run 35789753522 and its artifact were inaccessible; its supplied failure account remains user-provided and unverified here. The workflow's attempt-budget code was read; citation-specific remaining attempts were not observable.

The binding [agent-PR rules, issue #39](https://github.com/TheAxiomFoundation/.github/issues/39) were read through the public browser fallback after the requested CLI read failed. They require signed generation, exact proof grounding, complete companion inputs, source provenance, and separate governed pin changes; this lane made no external oracle filing or repository change. The issue page was cached, so newer edits remain unverified.

Checks completed: corpus row/path and official artifact hash; current/next/later release scope comparison; seven adjacent coverage artifacts; workflow inputs/validators/resolver/pins; pinned engine rejection code and unchanged-source-hold compile; both household baseline reproductions; independent decimal premium/tax arithmetic and final report structure. The arithmetic/provenance/structure checks [passed](checks.json); reproduce with `PYTHONDONTWRITEBYTECODE=1 python3 scratch/id-63-3022p/verify_package.py` from the assigned workspace. No new RuleSpec/test YAML, signed run, population simulation, or passing whole-return Axiom result was produced. The generic commit instruction is superseded by this assignment's explicit read-only/no-commit rule.

The empty `dispatch_command` below means **withheld because no verified passing immutable input set exists**; section 5 preserves the complete ineligible command without representing it as dispatchable.

```json
{
  "lane": "id-63-3022p",
  "verdict": "BLOCKED",
  "citation": "us-id/statute/63-3022P",
  "in_corpus": true,
  "in_pinned_release": false,
  "existing_modules": [
    "us-id/statutes/63-3022D.yaml",
    "us-id/statutes/63-3022E.yaml",
    "us-id/statutes/63-3024.yaml",
    "us-id/statutes/63-3024A.yaml",
    "us-id/statutes/63-3025D.yaml",
    "us-id/policies/income_tax/pilot_liability_pipeline.yaml",
    "us-id/policies/income_tax/2026_full_year_resident_source_hold.yaml"
  ],
  "blocking_imports": [],
  "dispatch_command": "",
  "prerequisites": [
    "Verify and activate an immutable signed corpus release containing 2026-09-14-income-tax-chapter-us-id-title-63-chapter-30, with archive provenance and release-content SHA256; the wave4-r2-union manifest alone is insufficient evidence.",
    "Land the separately approved rulespec-us pin to that containing release after coordinating the current serial chain; the Canada 2026-08-23 endpoint lacks this provision.",
    "Refresh and freeze exact rulespec main, corpus, engine and workflow evidence; verify base stability, live PR/run collisions and remaining attempt budget.",
    "Obtain Max Ghenis's approval for the concrete signed workflow run."
  ]
}
```
