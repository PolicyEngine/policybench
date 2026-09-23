# us-32c2 — Axiom encoding preparation

## 1. Verdict

**BLOCKED. Do not dispatch a signed run from this package today.** The independent statutory adjudication is complete for the provision effects: the Montana and Virginia corrections are supported within the benchmark's continuous-dollar convention. California's corrected earned-income base is supported, but **neither reported California credit amount is established by the law; holding AGI and the schedule fixed, the isolated lawful credit change is $0 because AGI remains binding**.

The following external prerequisites prevent a passing, narrow signed replacement:

1. **Source-identity admission:** `us/statutes/26/32/c/2.yaml` currently declares `us/statute/26/32`. The inspected encoder accepts exact identity or one direct-child refinement, so a request for `us/statute/26/32/c/2` fails before generation. A supported signed identity migration or reviewed encoder change is required. The same problem affects requesting `us/statute/26/24/d/1` against existing `24/d.yaml`, which declares `us/statute/26/24`.
2. **Dependency strategy needs verification:** the current §112 and earned-income/credit dependencies have legacy v1 manifests, so they cannot be explicitly reused through `existing_signed_imports_json`. An empty array neither attests nor forbids inherited §112 in repo-augmented generation. Its current compile/proof closure remains unverified. Signed refresh is a proposed dependency strategy, not a demonstrated universal requirement for inherited imports.
3. **Downstream compile failure:** §32 imports `us:policies/irs/rev-proc-2025-32/earned-income-credit`, which declares removed plural `corpus_citation_paths`; §24(d) reaches it through §32. A signed successor/import migration must land before this credit closure can pass the pinned engine. Encoder [PR #1665](https://github.com/TheAxiomFoundation/axiom-encode/pull/1665) proposes the relevant migration, but remains open.
4. **Direct deferral classification:** §402(e)(3) is in corpus main but outside both the current release and the planned August 23 release. A bounded §32 definition can consume already-classified includible compensation; independently calculating that classification from gross wages requires a release including §402 and appropriate signed dependencies. The named serial re-pin chain alone does not satisfy this requirement.
5. **Coordinate overlapping work and regenerate exact refs:** rulespec-us #1160 directly touches `32/c/2`, `112`, and `24/d`; #1158, #1159 and #1363 overlap the consumer closure. Complete or coordinate the pending serial pin changes, then obtain a fresh exact-main SHA. No future commit SHA is invented here.

This is not **NOT-NEEDED**: existing Axiom arithmetic can consume correct taxable wages, but does not derive the exclusion from raw pay, has a pension input-contract hazard, and lacks a runnable current signed credit closure. It is not **READY-AFTER** on the named re-pin chain alone: source admission and dependency migrations also need resolution.

Read-only scope was preserved. Only scratch evidence, calculation/check scripts, this report and a proposed finding were written. No RuleSpec or module test YAML, encodes, commits, branches, pushes, PRs, comments, dispatches or approvals were created. The assignment's specific no-commit rule controls over the generic opening commit instruction. No `-o` destination was exposed in the supplied context, so the report is saved at `scratch/us-32c2/report.md` for the orchestrator.

## 2. Source

Inspected rulespec-us `origin/main`: **`f43dec520dd392bc5333934f56dad7498363e704`**. The required `git fetch -q origin` was attempted and denied because `.git/FETCH_HEAD` is outside writable scope. A read-only live GitHub ref query independently matched that local SHA. Canonical corpus main was likewise verified as **`942e138e7a8250c9814e774ac9b8e63008148106`**. Reads use immutable Git objects, not the older checkout HEAD.

| Provision | Official text | Exact available canonical corpus unit | Corpus main | Current pinned release |
|---|---|---|---|---|
| 26 USC 32(c)(2)(A)(i) | [OLRC §32](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section32&num=0&edition=prelim) | `us/statute/26/32/c/2` | Yes | Yes |
| 26 USC 24(d)(1)(B)(i) | [OLRC §24](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section24&num=0&edition=prelim) | `us/statute/26/24/d/1` | Yes | Yes |
| 26 USC 24(h)(6), 2026 threshold substitution | [OLRC §24](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section24&num=0&edition=prelim) | `us/statute/26/24/h/6` | Yes | Yes |
| 26 USC 402(e)(3), relevant upstream exclusion | [OLRC §402](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section402&num=0&edition=prelim) | `us/statute/26/402/e/3` | Yes | **No** |
| Cal. R&TC 17052(c)(4)(A) | [California Legislature §17052](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=RTC&sectionNum=17052) | `us-ca/statute/rtc/17052` | Yes | Yes |

The corpus has no separate `/32/c/2/A/i`, `/24/d/1/B/i` or `/17052/c/4/A` node. Do not invent these as dispatch citations.

Exact tracked provision files and vintages:

- §§24 and 32: `data/corpus/provisions/us/statute/2026-07-13-recovery-r2026-07-15-self-contained-r2026-07-17-dedup.jsonl`. `source_as_of` and `expression_date` are **2026-07-13**; metadata records OLRC `Online@119-100`, created **2026-04-17**. Source XML files are `data/corpus/sources/us/statute/2026-07-13-recovery-r2026-07-15-self-contained-r2026-07-17-dedup/official-documents/usc26-section-32.xml` and `usc26-section-24.xml`; the official source archive is [OLRC title 26, PL 119-100](https://uscode.house.gov/download/releasepoints/us/pl/119/100/xml_usc26@119-100.zip).
- §402: `data/corpus/provisions/us/statute/2026-09-13-tax-statute-closure-31-title-26.jsonl`. `source_as_of`/expression date **2026-09-02**, metadata created **2026-09-09**, `Online@119-103`; captured [OLRC title 26, PL 119-103 XML archive](https://uscode.house.gov/download/releasepoints/us/pl/119/103/xml_usc26@119-103.zip), member `usc26.xml`.
- California: `data/corpus/provisions/us-ca/statute/2026-07-06-ca-rtc-pit-core-us-ca-sections-rtc-17041-rtc-17043-rtc-17045-rtc-17052-rtc-17054-rtc-17073.5.jsonl`, source/expression date **2026-07-06**, effective **2023-01-01**, AB 1766, Stats. 2022 ch. 482 §5. Captured official HTML provenance digest: `b0109e3cbb14a528423c83e6a41ad5145e711f702baff33ae24c84204601427d`.

`.axiom/toolchain.toml` pins **`us-rulespec-2026-08-08-obbb-alien-snap`**, content digest **`0d69a0cdbe024fc2276f3c261c00402bb0a47488ac5f482cc20bd3404980adbc`**. Membership was checked against canonical tracked release manifests. `axiom-locate release` found no local materialization, so this is manifest membership verification, not signature verification of a downloaded release. The planned `us-rulespec-2026-08-23-canada-338-suspension-union` also excludes the September §402 scope; `us-rulespec-2026-09-13-federal-and-plans-union` includes it. No new ingest is needed for the listed provisions; a release change is needed for §402 classification.

California **does follow the federal includible-gross-income condition**. Section 17052(c)(4)(A) changes the end of federal clause (A)(i) to add the California withholding condition, preserving the includibility words; (c)(4)(B) retains self-employment earnings. Do not confuse that conclusion with automatic federal/California conformity for every other payroll exclusion. The live official California page was read; live OLRC requests encountered 403/timeouts, so the exact official corpus captures govern proof excerpts. Full source records and release evidence are in [source-audit.md](corpus/source-audit.md).

For an expanded **Roth-classification encoding**, the bounded corpus citation search did not locate §402A itself. Before preparing that separate provision, ingest [official OLRC §402A](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section402A&num=0&edition=prelim) from title-26 USLM XML with source URL, retrieval/expression date and SHA provenance, then include it in the signed release. No §402A dispatch is prepared here. The household Roth distinction is corroborated by official IRS guidance; it is not represented as an existing corpus encoding.

## 3. Existing rulespec-us coverage

The following inventory is at the immutable rulespec SHA above. Quoted line numbers refer to those Git objects; numbered copies are retained under `coverage/`.

| Existing module | Coverage and relevance |
|---|---|
| `us/statutes/26/32/c/2.yaml` | Earned-income definition, exclusions and §112 election. Uses **already includible** compensation; does not itself classify elective deferrals. Thus no demonstrated gross-wage inclusion error under its stated input contract, but no independent raw-wage exclusion either. Literal pension input can subtract a pension twice. Legacy v1 provenance. |
| `us/statutes/26/32.yaml` | EITC eligibility, rates, imported annual amounts, AGI/earnings phaseout and restrictions. Imports the definition and the legacy IRS module. Not runnable with the pinned modern citation contract. |
| `us/statutes/26/24/d.yaml` | Refundable CTC arithmetic, §32 pre-election earnings plus §112 pay, social-security alternative and §911 gate. It follows the definition, rather than independently classifying wages. Its 2026 formula still uses $3,000; this is a separate Axiom composition gap. Imports §32 and inherits its loader blocker. |
| `us/statutes/26/24/h.yaml` | Special post-2017 amounts, thresholds, dependents and SSNs. Records $2,500 but explicitly defers composing it into §24(d). |
| `us/statutes/26/24.yaml` | Parent CTC eligibility/nonrefundable and advance-payment surface; imports §24(h), explicitly defers refundable computation to §24(d). Not an independent earned-income classifier. |
| `us/statutes/26/112.yaml` | Combat-pay exclusion amount, used by both earned-income consumers. Legacy v1 manifest, not a reusable signed-v5 dependency. |
| `us/policies/irs/rev-proc-2025-32/earned-income-credit.yaml` | Legacy annual EITC table imported by §32; removed plural source field. |
| `us/policies/irs/rev-proc-2025-32/page-15.yaml` | Existing signed-v5 annual EITC successor, plus other page content. Not yet the import used by §32. |
| `us-ca/statutes/rtc/17052.yaml` | California base tables/parameters; explicitly defers final CalEITC and indexed amounts. Does not compute the wage definition or the disputed 2026 refund. |
| `us/statutes/26/86.yaml` | Nearby cross-reference: line 576 treats Social Security benefits as pension/annuity for §32(c)(2), among other provisions. Does not compute wage deferral exclusion; not in this import closure. |

No tracked `us/statutes/26/402.yaml` or `us/statutes/26/402/...` module exists on the inspected main. The bounded inventory and citation searches are reproducible from `git ls-tree`/`git grep`; no new RuleSpec was made.

Relevant excerpts:

```text
32/c/2.yaml:3    - us:statutes/26/112#amount_excluded_from_gross_income_by_reason_of_section_112
32/c/2.yaml:8      corpus_citation_path: us/statute/26/32
32/c/2.yaml:57       employee_compensation_includible_in_gross_income
32/c/2.yaml:58       + net_earnings_from_self_employment_after_self_employment_tax_deduction
32/c/2.yaml:59       - pension_or_annuity_amount
32.yaml:7       - us:policies/irs/rev-proc-2025-32/earned-income-credit
32.yaml:444          max(adjusted_gross_income, earned_income)
24/d.yaml:47         3000
24/d.yaml:114        earned_income_before_section_112_election
24/d.yaml:115        + amount_excluded_from_gross_income_by_reason_of_section_112
24/h.yaml:137        2500
```

The §24(h) deferral explains that its substituted source value is recorded but composition into the subsection (d) formula remains deferred. The California module, lines 13–19, defers `california_earned_income_tax_credit` because federal/state dependencies are not copied, and `inflation_adjusted_earned_income_credit_amounts` because §17041(h) is not supplied.

Four fresh executions using the discovered older Rust artifact verified the existing definition's limited contract: with already-classified wages and pension input zero, earned income was **14,664.166015625**, **2,055.720703125**, and **51,912.80078125** for scenarios 023/100/119. Giving scenario 023 its separate $8,000 pension in `pension_or_annuity_amount` returned **6,664.166015625**. This demonstrates the double-subtraction risk under the literal mapping; it does not establish that every caller maps the field that way. Requests/responses: [earned-income-checks.json](coverage/earned-income-checks.json).

## 4. Import closure

The actual graph is:

```text
32/c/2 -> 112
32 -> 32/c/2, 152/c, 7703, IRS/earned-income-credit
7703 -> 151 -> 911/a, 931, 933
24/d -> 32/c/2, 112, 32
24 -> 24/h
CA/17052 -> no imports (final credit deferred)
IRS/page-15 -> no imports
```

**The narrow definition does not itself import §32.** Its broader consumers do, so it would be incorrect to say every module in this assignment fails for the plural field.

| Module ID (prefix `us:` except California) | Legacy discovered Rust compile | Pinned-engine assessment today | Signed-v5 reuse |
|---|---|---|---|
| `statutes/26/32/c/2` | Pass | Standalone current compile unverified; no plural field in its two-node closure | No, v1 |
| `statutes/26/112` | Pass | Current compile unverified; no plural field | No, v1 |
| `statutes/26/32` | Pass | **Cannot load: reaches legacy IRS plural field** | No, v1 |
| `statutes/26/152/c` | Pass | Current compile unverified; no plural field | No, v1 |
| `statutes/26/7703` | Pass | Current compile unverified; no plural field in closure | No, v1 |
| `statutes/26/151` | Pass | Current compile unverified; no plural field in closure | No, v1 |
| `statutes/26/911/a` | Pass | Current compile unverified; no plural field | No, v1 |
| `statutes/26/931` | Pass | Current compile unverified; no plural field | No, v1 |
| `statutes/26/933` | Pass | Current compile unverified; no plural field | No, v1 |
| `policies/irs/rev-proc-2025-32/earned-income-credit` | Pass | **Cannot load: directly declares plural field** | No, v1 |
| `statutes/26/24/d` | Pass | **Cannot load: transitive through §32** | No, v1 |
| `statutes/26/24` | Pass | Current compile unverified; no plural field in closure | No, v1 |
| `statutes/26/24/h` | Pass | Current compile unverified; no plural field | No, v1 |
| `us-ca:statutes/rtc/17052` | Pass | Current compile unverified; no plural field | No, v1 |
| `policies/irs/rev-proc-2025-32/page-15` | Not present in older checkout | No imports/plural field; exact current compile not executed | **v5 manifest present, primary digest matches** |

Engine evidence matters here. `axiom-locate engine` selects the artifact under `_tariff-parity`, checkout `ffd8213271947b0189a9dd61a055c1e0e78908a0`; it compiled 14 existing modules whose bytes matched the inspected immutable source. It is permissive about the removed field and **cannot certify current signed validation**. A second newer local binary (`sha256 faf4383622f63c64b861e5772b78b00df97efef4a8315b792b25219033bee75e`) stopped at an outdated repository-root check rejecting `programs/`; its build commit is unverified. Neither failure nor success from that binary is attributed to the modules' current legal semantics. No rebuild or RuleSpec-copy workaround was attempted.

The pinned engine **`af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca`** was inspected directly: `src/rulespec.rs` lines 802–833 recursively reject any key equal to `corpus_citation_paths`; `src/compile.rs` also rejects it. The pinned root validator explicitly permits declarative `programs/`, unlike the second local binary. The actual protected run [35789753522](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/35789753522) built that pin and failed on another imported module with the exact same removed-field error. Therefore the §32/§24(d) conclusion is a deterministic inference from inspected source plus the actual imported bytes, corroborated by a real pinned-engine log, **not a claimed fresh pinned compile of this closure**. All local commands/statuses are retained in [inventory.json](coverage/inventory.json), [modern-inventory.json](coverage/modern-inventory.json), and [pinned-engine-contract.txt](coverage/pinned-engine-contract.txt).

Candidate import inputs:

- **Current narrow run:** no verified complete signed-v5 import set exists. `[]` is syntactically admissible but does not certify §112's current compile/proof closure; it is not a readiness claim.
- **After signed §112 refresh:** intended direct-import path is `["us/statutes/26/112.yaml"]`, conditional on its new full-path manifest, hash, signature and closure checks. This array is **not valid as a signed-v5 claim today**.
- **Future downstream §32 annual-table repair:** `["us/policies/irs/rev-proc-2025-32/page-15.yaml"]` is the existing candidate. Its full-path manifest declares v5/Ed25519 and its primary SHA-256 matches `b032822be996093985f5d04fb64477d613fefd239c133e4c3c45192cc281f58e`. Protected signature/inventory verification still must run. It does not automatically replace legacy output names or repair the remaining v1 closure.

`existing_signed_imports_json` takes tracked **file paths**, not module IDs. The helper requires `.axiom/encoding-manifests/<full-path>.json` with v5 schema; the old manifests are often at legacy shortened paths as well as being v1. They cannot be reused by relabeling the JSON. Evidence: [import helper](https://github.com/TheAxiomFoundation/axiom-encode/blob/5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9/src/axiom_encode/prepare_signed_backfill.py#L1364).

## 5. Dispatch inputs

**There is no verified passing dispatch command today.** The following complete command records observed immutable values and the intended narrow target. It is a **known-blocked diagnostic snapshot**, not a recommendation to run: its citation/replacement pairing fails current source admission, and `[]` does not supply protected signed-import verification of the inherited closure. Do not spend a signed run demonstrating the already-read preflight error.

```sh
gh workflow run targeted-signed-reencode.yml \
  -R TheAxiomFoundation/axiom-encode --ref main \
  -f country=us \
  -f rulespec_ref=f43dec520dd392bc5333934f56dad7498363e704 \
  -f pr_base_branch=main \
  -f corpus_ref=8f7d60aaced28ee4252b9237f9d6e02360dc34bc \
  -f rules_engine_ref=af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca \
  -f citation=us/statute/26/32/c/2 \
  -f replace_rulespec_path=us/statutes/26/32/c/2.yaml \
  -f existing_signed_imports_json='[]' \
  -f source_bundle_json='[]' \
  -F review_finding=@scratch/us-32c2/review-finding.txt \
  -f open_pr=true
```

The three SHA inputs come from live rulespec main and the inspected `origin/main:.axiom/workflow-toolchain.toml`; corpus/engine pins also appear in the actual protected-run checkout logs. Current corpus main `942e138e…` and current engine main `6e709eb1ca7ea686263293d932c759d9dee48a4a` were read, but selecting newer checkout refs alone does not change rulespec-us's signed corpus release.

The workflow was read at encoder main **`5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9`**. Its required `--ref main` condition means the workflow itself is mutable between preparation and dispatch; re-read it at authorization time. All three checkout refs require full lowercase 40-character SHAs. Corpus/engine SHAs must be ancestors of their main branches. With `open_pr=true`, rulespec must equal main **both initially and immediately before push**. The encoded run operates in `production-signing` and uses `--backend openai --apply --mode repo-augmented --require-complete-source-unit`. This preparation lane does not execute that command. [Workflow and validation source](https://github.com/TheAxiomFoundation/axiom-encode/blob/5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9/.github/workflows/targeted-signed-reencode.yml).

Using `citation=us/statute/26/32` would satisfy the existing target's source identity, but requests the **whole section**. It is not an equivalent narrow run: every other branch must be encoded or genuinely and precisely deferred, the existing `32.yaml` surface must not be duplicated, and dependent compatibility must hold. That route has not been demonstrated to pass. Changing only the citation to hide the admission error is not the recommended package.

No separate ACTC command is ready: its identity refinement, threshold composition and §32 import closure must be resolved first. After prerequisites land, the orchestrator must produce new exact-main commands with refreshed verified import arrays and obtain Max's approval. The JSON at the end therefore leaves `dispatch_command` empty rather than presenting a known-failing command as runnable.

## 6. Review finding text

The full proposed `review_finding` input is [review-finding.txt](review-finding.txt). It includes the assignment's encoding regime verbatim, the narrow-source admission condition, whole-source coverage, precise deferrals, paired tests, and all four worked cases below. It is preparation text for a future corrected narrow transaction; it does not cure present workflow admission or provenance blockers.

The source requires wages, salaries, tips and employee compensation **“but only if such amounts are includible in gross income for the taxable year”**. Section 402(e)(3), read with the inclusion rules and §402(g), supports excluding qualified traditional deferrals while retaining excess amounts required includible. The retained designated-Roth treatment is separately corroborated by the [official IRS Roth comparison](https://www.irs.gov/retirement-plans/roth-comparison-chart); no §402A corpus proof is claimed. Section 32(c)(2) also covers adjusted net self-employment income and all six B rules: disregard community-property allocation; exclude pensions/annuities, §871(a) amounts, inmate-service compensation, and only the subsidized portion of specified state work activities; permit the §112 election. The source does not direct subtracting separate pension receipts from otherwise qualifying wages.

Precise deferral boundaries are upstream classification under §§401(k), 402, 402A and 403(b), limits/excess/catch-up rules, §1402/164(f) net earnings, and §112 excluded amounts; downstream §32 credit eligibility/rates/AGI/tables and state credit formulas are separate. A classified-compensation input is acceptable for a bounded definition, but must not be advertised as independent raw-pay classification. No vague deferral of a local §32(c)(2) branch or opaque earned-income answer input is acceptable. Existing public pre-election/final earned-income outputs must be preserved or their consumers migrated through signed transactions.

For a separate §24(d) consumer, apply the section-32 definition and **§24(h)(6)'s $2,500 substitution for 2026**. Distinguish its mandatory inclusion of §112 pay from the optional EITC election. A replacement of the full §24(d)(1) source also needs the three-or-more-child alternative and lesser/greater-of limitations, not merely clause (B)(i); replacing all (d) also needs its §911 gate. [Official §24](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section24&num=0&edition=prelim).

Every operative exception/election needs paired positive and blocking witnesses in the same period, differing in exactly one controlling input and asserting the main amount. Cover each controlling conjunct separately, partial subsidies, pension classification without double subtraction, combat election true/false, and community-property invariance. Assign every local `#input`, including false Booleans. Include zero/positive boundaries and traditional/Roth/excess classification integration tests. Exact proof excerpts must be substrings of the resolved source, not stitched or paraphrased assertions. These requirements come from [binding issue #39](https://github.com/TheAxiomFoundation/.github/issues/39), read via the GitHub connector after `gh issue view` could not reach the network, and the inspected completeness validator/workflow.

**Worked cases and adjudication.** These use actual scenario facts and independently calculated legal formulas, not the fix docstring. Qualification, residency, valid IDs and absence of other exceptions are held at benchmark facts/defaults; the supplied situations do not prove every eligibility condition. All three cases have no self-employment or supplied combat/inmate/§871/state-work income. Employer-paid health insurance is not subtracted again as an employee payroll deduction. Calculations follow the continuous-dollar benchmark convention; §32(f)'s Treasury bracket-table filing amounts are not certified here. Float32 differences below one cent do not change the conclusions. [Detailed facts, method and evidence](households/adjudication.md).

| Household / moved benchmark output | PE 1.755.4 frozen | Sandbox corrected | Independently derived provision result | Adjudication |
|---|---:|---:|---:|---|
| 023 CA — state refundable credits | 148.310867 | 174.968216 | **Legal isolated change $0**; exact 2026 table amount unresolved; same-schedule control **99.460066** | **Neither credit amount established**; corrected wage base supported |
| 100 MT — federal refundable credits | 2,878.096680 | 822.288269 | **822.288281** | Corrected supported |
| 100 MT — state refundable credits | 473.177704 | 164.457657 | **164.457656** | Corrected supported |
| 119 VA — federal refundable credits | 2,854.008789 | 3,366.073730 | **3,366.073525**, including unchanged ACTC balance | Corrected provision effect supported |
| 119 VA — state income tax before refundable credits | 1,859.094360 | 1,756.681396 | **1,756.681436**, holding unrelated components fixed | Corrected provision effect supported |

**Case 1 — scenario_023 (California).** Single adult, age 28, no children. Gross wages $17,442.646484375; traditional 401(k) $2,778.47998046875; Roth 401(k) $490.32000732421875; taxable 403(b) distribution $8,000; IRA deduction $129.8303985595703. Statutory earned income is **$14,664.16650390625**, compared with frozen **$17,442.646484375** and sandbox **$14,664.166015625**. The Roth amount stays in taxable wages. The separate pension is excluded from earned income, not subtracted from these pension-free wages.

AGI under the unchanged IRA assumption is **$22,534.33610534668**, above both wage measures. California's incorporated AGI comparison therefore remains binding. The legal credit is `min(C2026(14664.16650390625), C2026(22534.33610534668))`, with the latter binding under the schedule, **unchanged by this wage correction**. The available official [FTB 3514 instructions](https://www.ftb.ca.gov/forms/2025/2025-3514-booklet.html) corroborate the second AGI lookup and smaller-credit rule; they are 2025 guidance, not a verified 2026 table.

No final 2026 table amount is certified. Holding the saved schedule fixed and independently applying it to AGI yields **$99.46006599474843**, matching the separately supplied r17 diagnostic. That is a conditional numerical control, not a statutory 2026 result. Thus the statute supports the corrected **wages**, supports **neither** the frozen $148.31 nor corrected $174.97 as an adjudicated credit, and does not support the claimed +$26.657349 change. The audit's `not_confirmed` entry and verification report corroborate this distinction; the statutory interpretation was derived separately.

**Case 2 — scenario_100 (Montana).** Head of household, adult 46, children 6 and 5. Wages $5,914.720703125; traditional 401(k) $3,859; Roth 401(k) $681; IRA $180.32000732421875. Statutory earned income is **$2,055.720703125** (frozen $5,914.720703125; sandbox $2,055.720703125). The IRA deduction lowers AGI, not earned wages; AGI is $1,875.4006958007812, so there is no phaseout.

EITC is `0.40 × 2055.720703125 = $822.28828125`. ACTC is `0.15 × max(2055.720703125 − 2500, 0) = $0`; two children do not qualify for the three-child alternative. Federal refundable credits are therefore **$822.28828125**. Montana's 2026 refundable match is **20%**, yielding **$164.45765625**. Both corrected outputs are supported. The two-child rate comes from §32(b)(1); Montana's change is enacted in [2025 chapter 227/HB 337 §3, effective under §§5–6](https://archive.legmt.gov/content/Sessions/69th/Contractor_index/CH0227.pdf).

**Case 3 — scenario_119 (Virginia).** Head of household, adult 45, children 14 and 11. Wages $55,000; traditional 401(k) $3,087.199951171875; Roth $544.7999877929688; taxable interest $800; IRA $144.25599670410156. Earned income is **$51,912.800048828125** (frozen $55,000; sandbox $51,912.80078125). AGI is **$52,568.54405212402** and controls the phaseout. Using the 2026 two-child maximum $7,316 and unmarried threshold $23,890 from [IRS Rev. Proc. 2025-32 §4.06](https://www.irs.gov/pub/irs-drop/rp-25-32.pdf):

`7316 − 0.2106 × (52568.54405212402 − 23890) = $1,276.2986226226807` EITC.

Corrected ACTC phase-in capacity remains $7,411.920007324219, above the unchanged refundable balance **$2,089.77490234375**. That balance is derived by the supplied benchmark from $4,400 child credit less $2,310.22509765625 limiting tax; this lane does not independently audit that unrelated tax liability. Adding it gives **$3,366.073524966431** federal refundable credits. The independently derived EITC increase is **$512.0646226226807**.

Virginia's selected nonrefundable 20% branch reduces pre-refund tax by **$102.4129245245361**, giving **$1,756.681435827026** while holding unrelated components fixed. [Virginia Code §58.1-339.8 B(2)–(3)](https://law.lis.virginia.gov/vacode/title58.1/chapter3/section58.1-339.8/) supports the 20% match; its 2025–2026 refundable alternative is also 20%. Household output confirms the benchmark selects the nonrefundable branch; the read selection code favors that branch on ties, but this lane did not calculate both hypothetical liabilities to prove a tie here. The law permits that choice; it does not require that accounting branch. Corrected provision effects are supported, without claiming a complete independent federal/Virginia return calculation.

**Case 4 — classification boundary.** $10,000 pay with $2,000 qualifying excluded traditional deferral gives $8,000 includible wages. Changing only its classification to taxable designated Roth gives $10,000. A separate $3,000 pension must leave those earned-income amounts unchanged. Set unrelated local facts explicitly zero/false; include a separate excess-deferral case retaining amounts required includible by §402(g). If the narrow module receives classified wages, these are upstream integration witnesses, not proof that the module itself encodes the missing classification. [Official §402](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section402&num=0&edition=prelim), [IRS Roth treatment](https://www.irs.gov/retirement-plans/roth-comparison-chart).

## 7. Risks

**Likeliest rejection reasons and mitigation:** source-identity mismatch and non-v5 manifests for paths explicitly listed in `existing_signed_imports_json` are pre-generation blockers; prose cannot cure them. Complete-source validation rejects unaccounted branches and generic deferrals; the proposed finding enumerates the whole narrow source and named boundaries. Paired-exception tests must flip one controlling input and assert the affected output. Literal pension subtraction can corrupt already-net wages; the finding supplies a concrete counterexample. A consumer run must resolve the annual IRS import and the $2,500 ACTC substitution. Do not admit the California +$26.66 move as an expected result. Use exact proof substrings and all local facts, and preserve the reviewed source/manifest chain; no new waiver or manual metadata patch is proposed.

**Serial chain:** live #1384 is merged at the inspected main; [#1387](https://github.com/TheAxiomFoundation/rulespec-us/pull/1387) activation and [#1386](https://github.com/TheAxiomFoundation/rulespec-us/pull/1386) workflow pin remain open. The later drift-stage/activation/re-pin PRs were not found in the inspected complete open-PR collection. The chain's existence is not itself a legal requirement for encoding §32(c)(2), which is already in the pinned release. Operationally a long `open_pr=true` run should wait for coordinated main stability because exact-base validation can fail after any intervening merge. The chain neither fixes deep source refinement nor adds §402(e)(3). The brief's “up to 3.5 hours” per strict CI was not independently measured in this lane and remains unverified.

**Verified open collisions:**

| PR | Observed overlapping files/status |
|---|---|
| [rulespec-us #1160](https://github.com/TheAxiomFoundation/rulespec-us/pull/1160) | Open draft; `32/c/2.yaml` + tests, `112.yaml` + tests, `24/d.yaml` + tests |
| [rulespec-us #1158](https://github.com/TheAxiomFoundation/rulespec-us/pull/1158) | Open draft; `32.yaml` + tests and `24/d.yaml` + tests |
| [rulespec-us #1159](https://github.com/TheAxiomFoundation/rulespec-us/pull/1159) | Open draft; `32.yaml` + tests |
| [rulespec-us #1363](https://github.com/TheAxiomFoundation/rulespec-us/pull/1363) | Open draft; legacy IRS annual module, `32.yaml`, `24/d.yaml`; body reports provenance blocks. Not an approved signed repair. |
| [axiom-encode #1665](https://github.com/TheAxiomFoundation/axiom-encode/pull/1665) | Open proposed legacy-to-signed IRS successor repoint. Proposal read; implementation/landing success unverified. |

REST collections were read because connector search omitted open PRs; exact changed-file APIs verified overlaps. The latest **30 targeted runs** across the inspected 200 repository runs contained no §32 or §24 citation/descendant. This is a bounded check, not a promise that no one will dispatch later. Full refs, PR heads, workflow contracts and run evidence: [workflow/report.md](workflow/report.md).

**Validation performed:** all five baseline and r08 moved outputs reproduced their CSV values within **$0.000001** using only the three assigned households. Independent decimal arithmetic agreed with all four supported MT/VA outputs within **$0.01**; CA's same-schedule AGI diagnostic and zero isolated effect were checked separately. Four existing Axiom earned-income executions passed their intended input-contract probes, including the pension counterexample; 14 legacy-binary compile checks passed with immutable-byte comparisons. Current pinned-engine compile acceptance remains unverified beyond the definite plural-field blocker established from source. No population simulation, local encode or new RuleSpec test was run. Evidence: [arithmetic-checks.log](households/arithmetic-checks.log), [household-checks.json](households/household-checks.json), [independent-arithmetic.json](households/independent-arithmetic.json), [coverage inventory](coverage/inventory.json).

```json
{
  "lane": "us-32c2",
  "verdict": "BLOCKED",
  "citation": "us/statute/26/32/c/2",
  "in_corpus": true,
  "in_pinned_release": true,
  "existing_modules": [
    "us:statutes/26/32/c/2",
    "us:statutes/26/32",
    "us:statutes/26/24/d",
    "us:statutes/26/24/h",
    "us:statutes/26/24",
    "us:statutes/26/112",
    "us:policies/irs/rev-proc-2025-32/earned-income-credit",
    "us:policies/irs/rev-proc-2025-32/page-15",
    "us-ca:statutes/rtc/17052",
    "us:statutes/26/86"
  ],
  "blocking_imports": [
    "us:policies/irs/rev-proc-2025-32/earned-income-credit",
    "us:statutes/26/32"
  ],
  "dispatch_command": "",
  "prerequisites": [
    "Supported signed source-identity refinement for existing 32/c/2 and ACTC target; current two-level refinement fails admission",
    "Verify the dependency strategy: signed-v5 explicit imports, or a separately validated inherited closure and precise bounded source contracts; section 112 cannot currently be listed as signed-v5",
    "Signed legacy IRS successor/import migration and successful current-engine recheck of 32 and 24/d closure; coordinate encoder PR 1665",
    "For independent raw-pay deferral classification, release-bind section 402 sources beyond both 08-08 and planned 08-23 release, then encode/import appropriate signed classification",
    "Compose section 24(h)(6) 2500-dollar threshold and preserve mandatory combat-pay inclusion in ACTC consumer",
    "Coordinate overlapping rulespec PRs 1160, 1158, 1159, 1363 and the serial 1387/1386/later repin chain; refresh exact-main refs and obtain Max approval"
  ]
}
```
