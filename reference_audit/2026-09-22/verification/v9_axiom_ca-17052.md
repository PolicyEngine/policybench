# ca-17052 — Axiom encoding preparation

Prepared 2026-09-22. Read-only investigation; only this workspace's scratch artifacts were written. No RuleSpec or module tests were authored, no local encode ran, and no commit, PR, corpus change, or signed run was made. The specific read-only assignment overrides the initial generic commit instruction.

## 1. Verdict

**BLOCKED.** The statute is present, but a source-complete, admissible signed encoding of the requested 2026 CalEITC calculation cannot yet be specified from the verified dependencies. The missing items are corpus-backed FTB 3514 instructions/table and applicable annual factor, authorization and indexed parameters; a supported way to supply the incorporated federal mechanics; and a fresh current-main/collision check. The planned repin chain alone does not supply the missing California sources.

The independent adjudication is narrower and clear: **the statute supports the sandbox's AGI-comparison mechanism.** Holding the frozen projected schedule fixed, the independently recomputed value is **$99.4600676051**, matching r17's **$99.460068**, versus frozen **$148.310867**. This is conditional on that schedule. Neither number equals the **$96** obtained using the published **2025** FTB worksheet/table. No definitive 2026 annual amount was established from the sources retrieved here. Do not describe $96 as final 2026 law or $99.46 as an independently verified 2026 legal amount.

**Attribution:** PR **#9363** introduced the comparison. PR **#9542** changed the 2024 exclusive income boundary and references. Exact local commit/diff evidence appears in section 6. This package records Axiom coverage and acceptance criteria, not an external-oracle finding.

The required fetch was attempted and failed with `cannot open '.git/FETCH_HEAD': Operation not permitted`. All requested `gh` reads failed with `error connecting to api.github.com`. Local immutable objects were used; freshness of remote main, PR status and today's runs remains unverified. Binding [Axiom issue #39](https://github.com/TheAxiomFoundation/.github/issues/39) was read through the browser; the displayed copy was crawled three weeks earlier.

## 2. Source

Official controlling text: [California RTC §17052](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=RTC&sectionNum=17052), incorporating [IRC §32(a)](https://www.govinfo.gov/content/pkg/USCODE-2024-title26/html/USCODE-2024-title26-subtitleA-chap1-subchapA-partIV-subpartC-sec32.htm). The operational worksheet is [FTB 3514, 2025 booklet](https://www.ftb.ca.gov/forms/2025/2025-3514-booklet.pdf), worksheet on printed page 8 and relevant table on pages 26–27. The 2025 material establishes the comparison and dated controls; it is not a 2026 annual table.

Canonical citation: **`us-ca/statute/rtc/17052`**, the entire section. Neither inspected California source scope contains a separate `us-ca/statute/rtc/17052/a` record. Use the whole section as the encoder's source unit.

Canonical corpus local origin/main read: **`942e138e7a8250c9814e774ac9b8e63008148106`**. Two tracked versions contain the section:

| Version | Tracked provision file | Source vintage |
|---|---|---|
| July source used by the pinned release | `data/corpus/provisions/us-ca/statute/2026-07-06-ca-rtc-pit-core-us-ca-sections-rtc-17041-rtc-17043-rtc-17045-rtc-17052-rtc-17054-rtc-17073.5.jsonl` | expression/source-as-of 2026-07-06 |
| Later corpus-main snapshot | `data/corpus/provisions/us-ca/statute/2026-09-14-income-tax-chapter-us-ca-sections-4e26e6efabc3f0c7.jsonl` | expression/source-as-of 2026-09-14 |

Both identify the same AB 1766 amendment, Stats. 2022 ch. 482 §5, effective January 1, 2023. Their normalized bodies are byte-identical after extraction (`diff -u` produced no differences). The retained July HTML is `data/corpus/sources/us-ca/statute/2026-07-06-ca-rtc-pit-core-us-ca-sections-rtc-17041-rtc-17043-rtc-17045-rtc-17052-rtc-17054-rtc-17073.5/california-leginfo-sections/RTC-17052.html`, SHA-256 **`b0109e3cbb14a528423c83e6a41ad5145e711f702baff33ae24c84204601427d`**. Its ingest manifest records that path/digest and generation at 2026-07-15T19:51:39.937073+00:00. The September HTML digest is `1d75484931ec99eef7dd05dbedbb1e5c21a5d09727200042f101d2c89eb51768`.

**In pinned release: yes, for §17052.** On inspected rulespec-us main, `.axiom/toolchain.toml` pins `us-rulespec-2026-08-08-obbb-alien-snap`, content digest **`0d69a0cdbe024fc2276f3c261c00402bb0a47488ac5f482cc20bd3404980adbc`**. The tracked release manifest explicitly includes the July California statute scope. The same source record exists at the pinned corpus checkout commit `8f7d60aaced28ee4252b9237f9d6e02360dc34bc`. This verifies scope membership from Git; `axiom-locate release` found no installed release bundle, so signed bundle bytes/signature were not independently downloaded or checked.

IRC 32 also exists in corpus at `data/corpus/provisions/us/statute/2026-07-13-recovery-r2026-07-15-self-contained-r2026-07-17-dedup.jsonl`, citation `us/statute/26/32`, expression date 2026-07-13, retained official XML `sources/us/statute/2026-07-13-recovery-r2026-07-15-self-contained-r2026-07-17-dedup/official-documents/usc26-section-32.xml`. Its allowance and limitation text was read, independently of the PolicyEngine fix docstring.

**Supporting source gap:** the tracked California form/guidance inventories and provisions inspected contain no FTB 3514 worksheet or credit table. The purported 2025 tax-materials scope contains only Form 540 tax-table/rate-schedule records. Ingest the official [2025 booklet PDF](https://www.ftb.ca.gov/forms/2025/2025-3514-booklet.pdf), preserving worksheet guards, rows and columns, URL, retrieval/source date and SHA provenance, for dated controls. For a final 2026 monetary encoding, obtain and ingest the actual applicable 2026 annual FTB/indexing authority and enacted Budget Act factor/resource provision first. Direct attempted 2026 booklet/instruction URLs did not resolve; this is not proof that all 2026 authority is unpublished. No new citation for an uningested worksheet is invented here. The planned August23 union release retains the same California scopes and does not itself fill these gaps.

Source extracts: [§17052](statute-17052.txt), [IRC 32](irc32-source.json), [release manifest](pinned-release-manifest.json).

## 3. Existing rulespec-us coverage

Inspected local **origin/main `f43dec520dd392bc5333934f56dad7498363e704`**. The repository tree and targeted content search found the following relevant coverage; no separate subsection(a) or FTB 3514 computation module was found.

| Module | Actual coverage and relevant quoted lines | AGI-comparison status |
|---|---|---|
| `us-ca/statutes/rtc/17052.yaml` | Lines 13–16: `output: us-ca:statutes/rtc/17052/a#california_earned_income_tax_credit`; `reason: The final credit depends on IRC section 32, RTC section 17039 net tax,` followed by annual Budget Act and other dependencies. Lines 36–410 provide base/alternative statutory parameters; lines 413–450 provide two ITIN duties. | Final credit expressly deferred; no earned-income-only monetary computation to compare. This is missing coverage, not the same computed defect. |
| Its companion `17052.test.yaml` | Three cases test the requested-document and SSN-notice duties, with all three local Boolean inputs assigned. | No monetary or AGI-comparison cases. |
| `us-ca/policies/income_tax/2026_resident_liability_source_hold.yaml` | Lines 36–43 state missing annual materials and Budget Act factor. Lines 261–287 name `ca_pit_2026_credit_surface_source_hold_applies` and set `formula: true`. Lines403–421 define refundable credits with `source: Fail-closed annual refundable-credit sentinel while source held` and `formula: '0'`. | Explicit unavailable-source sentinel, not an adjudicated zero or an implementation of the disputed mechanism. Lines5–15 also contain the rejected plural source key. |
| `us-ca/policies/income_tax/pilot_liability_pipeline.yaml` | Summary describes the estimated-tax rate-schedule branch above $100,000 and explicitly excludes `all other worksheet taxes and credits` and `final-return liability`. | No CalEITC computation; plural source key at lines 5–10. |
| `us-ca/statutes/rtc/17041.yaml` | Lines 59–72 explicitly defer `#inflation_adjustment_factor` and `#recomputed_income_tax_bracket`. Base brackets and the non-surtax characterization output do not supply the required annual CalEITC indexing. | Not a credit implementation or a usable annual-parameter dependency. |
| `us-ca/statutes/rtc/17054.yaml` | Lines 9–10 defer `#personal_exemption_credit`; statutory base credits, blindness and another-taxpayer dependency logic are encoded. | Nearby personal-exemption provision, outside CalEITC. |
| Federal `us/statutes/26/32.yaml` | Imports lines 2–7; `eitc_phase_out_income` uses `max(adjusted_gross_income, earned_income)` and `eitc_before_eligibility` uses `max(0, min(eitc_phased_in, eitc_maximum - eitc_reduction))`. | Correct comparison structure for the federal module; federal schedules/eligibility cannot become California parameters unchanged. Closure is inadmissible here and rejected by the pinned engine as detailed below. |

The CA 17052/17041 manifests inspected are legacy `axiom-encode/applied-rulespec/v1`, not signed-v5 imports. The target may still be the existing replacement path; do not mistake that for import eligibility. The old target's ITIN proof excerpts contain literal ellipses; a new run must ground fresh exact spans rather than copy these excerpts.

## 4. Import closure

Candidate **`existing_signed_imports_json=[]`**. This is the only supported candidate established here, and is **not** a complete dependency plan. No usable signed-v5 California module supplying the incorporated comparison plus annual schedule was identified. The inspected workflow helper rejects supplied imports from a different exact jurisdiction; `us/...` cannot be supplied for `us-ca/...`. This is a workflow input restriction, not a general claim about RuleSpec import syntax.

For completeness, the natural federal candidate's entire ten-module closure was read:

| Module | Direct imports | Located legacy binary | Pinned engine `af6e4ea…` |
|---|---|---|---|
| `us:statutes/26/32` | 32/c/2,152/c,7703,IRS EIC | Compiles | Rejected through IRS EIC, established by code |
| `us:statutes/26/32/c/2` | 112 | Compiles | Runtime unverified |
| `us:statutes/26/112` | None | Compiles | Runtime unverified |
| `us:statutes/26/152/c` | None | Compiles | Runtime unverified |
| `us:statutes/26/7703` | 151 | Compiles | Runtime unverified |
| `us:statutes/26/151` | 911/a,931,933 | Compiles | Runtime unverified |
| `us:statutes/26/911/a` | None | Compiles | Runtime unverified |
| `us:statutes/26/931` | None | Compiles | Runtime unverified |
| `us:statutes/26/933` | None | Compiles | Runtime unverified |
| `us:policies/irs/rev-proc-2025-32/earned-income-credit` | None | Compiles | Rejected: plural `corpus_citation_paths`, lines 8–11 |

Pinned engine `src/rulespec.rs:819–822` rejects `corpus_citation_paths`; lines 1086 and 1093–1095 enforce that recursively on imports. This is direct code evidence, not a claim to have reproduced a failure with a current executable. The same parser rule excludes the two California policy modules above. CA 17052 and 17041 have no imports, use the singular key, and compile with the located binary; current-engine runtime/proof validation was not completed.

`axiom-locate engine` returned `/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine`, SHA-256 `674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7`. It reports version 0.1.0 and accepts the removed plural key, so its 12 successful existing-module compiles cannot clear signed-run compatibility. No engine build was attempted. Exact per-module commands, results, manifests and pinned-source excerpts are in [closure notes](closure/notes.md), [compile results](closure/compile-results.json) and [parser evidence](closure/pinned-engine-plural-contract.txt).

A prerequisite is an approved source-complete California dependency route, or supported cross-jurisdiction context with its dependency failures resolved. Merely removing the IRS import, copying federal annual amounts, or accepting precomputed credit inputs would not establish a lawful complete California encoding.

## 5. Dispatch inputs

**No pass-ready dispatch command can be certified. Do not execute the command below.** It is fully populated against the inspected snapshot for review; its corpus lacks required supporting sources and its rulespec SHA is not verified as today's remote tip. After prerequisites land, refs and finding must be refreshed and Max must approve the signed run. This lane grants no dispatch approval.

Workflow inspected: axiom-encode local origin/main **`5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9`**. The [saved workflow](workflow/targeted-signed-reencode.yml) declares the inputs at lines 4–115. The [helper](workflow/prepare_signed_backfill_impl.py) requires exact current remote main for `open_pr=true` at lines 267–331, canonical citation paths at 334–353, and same-jurisdiction tracked signed-v5 import paths at 1368–1502. Workflow 362–401 verifies full 40-character checkout identities and corpus/engine main ancestry. Replacement validation was also read, saved in [replacement extract](workflow/replacement-target-validation.txt).

| Input | Verified snapshot value and provenance |
|---|---|
| rulespec_ref | `f43dec520dd392bc5333934f56dad7498363e704`, canonical checkout's local origin/main |
| corpus_ref | `8f7d60aaced28ee4252b9237f9d6e02360dc34bc`, that rulespec commit's `.axiom/workflow-toolchain.toml`; commit object and local-main ancestry verified |
| rules_engine_ref | `af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca`, same workflow-toolchain pin; commit object and local-main ancestry verified |
| citation / replacement | `us-ca/statute/rtc/17052` / `us-ca/statutes/rtc/17052.yaml`, verified corpus record and existing module |
| imports / source bundle | `[]` / `[]`, admissible empty shapes only; unresolved legal dependencies remain |
| review_finding | Exact accompanying [review_finding.md](review_finding.md) |
| country / PR base / open_pr | `us` / `main` / `true`, per workflow schema; the future action would create a draft PR |

```sh
gh workflow run targeted-signed-reencode.yml \
  -R TheAxiomFoundation/axiom-encode \
  --ref main \
  -f citation=us-ca/statute/rtc/17052 \
  -f country=us \
  -f rulespec_ref=f43dec520dd392bc5333934f56dad7498363e704 \
  -f pr_base_branch=main \
  -f corpus_ref=8f7d60aaced28ee4252b9237f9d6e02360dc34bc \
  -f rules_engine_ref=af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca \
  -F review_finding=@scratch/ca-17052/review_finding.md \
  -f source_bundle_json='[]' \
  -f existing_signed_imports_json='[]' \
  -f replace_rulespec_path=us-ca/statutes/rtc/17052.yaml \
  -f open_pr=true
```

All remaining optional repair/dependent/legacy/queue inputs are intentionally absent and retain declared empty/default values; no such run IDs or dependent paths were established. The mandatory `--ref main` is a moving workflow branch: the actual workflow SHA must be recorded again at dispatch. Neither the current nor a future signed run was executed.

**Repin chain:** inspected main is the merge of waiver renewal #1384. Local #1387 activation head `500d9df58be4e17f8572e51f665a28241b039823` and workflow-pin branch `a9dd1fb7985ccfdaf9f98548edde94ad48cd227c` are not ancestors of it. The latter's mapping to #1386 is task-supplied, not verified live. Waiver activation #1387, workflow pin #1386, drift staging, then activation/release repin remain the named coordination chain; later PR numbers and current statuses are unverified. Reconcile that chain before the orchestrator freezes its eventual exact-main ref. §17052 already belongs to today's pinned release, so that chain is not needed to add this statute; it also cannot cure the missing worksheet/annual authority. Waiting only for the chain is insufficient for READY-AFTER.

## 6. Review finding text and independent worked cases

The complete proposed `review_finding` payload is [review_finding.md](review_finding.md), including the assignment's encoding regime verbatim. It is held pending the prerequisites, not offered as a workaround for missing sources. Its required source coverage is:

- Preserve IRC 32(a)(1)'s earned-income cap and (a)(2)(B)'s greater-of-AGI-or-earnings phase-out cap; apply the applicable California schedule and annual adjustment.
- Cover §17052(a) authorization/default-factor gates, (b) California substitutions/no joint increment, (c) California eligibility and earned-income modifications, (d)-(e) investment income/indexing, (f) refundable excess, (o) alternative schedule and inflation rules, and (p)-(q) ITIN treatment/duties.
- Precisely defer administrative (g), (i), (j) and declaratory (r) outputs; represent (k) as naming metadata or precisely defer its noncomputational naming output; identify (h)'s cross-program benefit-disregard execution and (l)'s effective dates. Identify expired years for historical (m), (n), (c)(3) branches if limiting the module to 2026. Historical (e)(2)-(3) CPI floors may be deferred only when sourced annual values already incorporate their cumulative effects; recomputation from base amounts must preserve them. Do not use a broad deferral to omit the requested comparison or final credit while calling the assignment complete.
- Pair positive and blocking tests for authorization, schedule boundaries, child groups, ages, abode/withholding, self-employment dates, investment-income limit, separated-spouse conditions, identification and ITIN duties. Explicitly set every local input, including false Booleans. Test AGI above/below/equal earnings and phase-out start, the earned-income phase-in cap, and zero/negative AGI.

The ordinary incorporated branch, for nonnegative earned income E and applicable parameters, is:

`k × max(0, min(c × min(E,M), c × M − p × max(0,max(A,E)−P)))`.

Here A is federal AGI; c/p are the applicable credit/phase-out rates; M/P are the earned-income/phase-out amounts; k is the authorized adjustment factor. This expresses the ordinary statutory limitation, **not** a complete substitute for California(o)'s alternative schedule. IRC 32(a)(2)(B) says **“adjusted gross income (or, if greater, the earned income)”**. The source text—not the fix docstring—therefore decides the ordering.

**All moved benchmark households:** `sweep_moves.csv` contains exactly one r17 row, scenario_023, state_refundable_credits. Facts from the supplied scenario: tax year 2026, California, single adult age 28, no children; wages **17,442.646484375**, traditional 401(k) contribution **2,778.47998046875**, taxable 403(b) distribution **8,000**, traditional IRA contribution **129.8303985595703**. Residency/identification conditions not explicit in the record are held eligible, as in the isolated comparison. Observed `ca_eitc_eligible=true`, `filer_adjusted_earnings=17,442.646484375`, federal AGI=CA AGI=**22,534.3359375**. Exact arithmetic on the supplied inputs gives AGI 22,534.33610534668; the tiny difference is float precision. California and federal AGI happen to agree here; the worksheet calls for federal AGI.

The independent calculation read projected parameters from baseline without importing the fix: credit/phase-out rate 0.0765, factor 0.85, first threshold 4,766.6318362973125, final-segment starting credit K=263 and endpoint U=32,901. Derived transition L=5,488.6654411451825. The final segment `C(x)=max(0,263×(32901−x)/(32901−L))` gives:

| Case | Inputs | Expected amount and adjudication |
|---|---|---|
| **1. scenario_023, 2026; comparison with inherited schedule held** | E=17,442.646484375; A=22,534.3359375; child count 0 | Frozen **148.310867**; r17 **99.460068**. Independent C(E)=148.310862246357; C(A)=**99.460067605107**. **Supports the corrected comparison/value conditional on the inherited schedule**, not an independent endorsement of its 2026 annual parameters. |
| Same household, published 2025 table sensitivity | Earned lookup 143; AGI lookup 96 | **96**, so **neither** audit amount is the result under the explicitly held 2025 table convention. Removing the 401(k) deferral from taxable earnings changes the first lookup to 168; the minimum remains96. This is not a 2026-law conclusion. |
| **2. 2025 equality control** | Otherwise eligible/no children; E=A=17,442.65 | **143**. Equality must not alter the earned-income lookup. |
| **3. 2025 lower-AGI control** | Otherwise eligible/no children; E=17,442.65; A=0 | **143**. Do not replace the phase-out base with low AGI or perform a spurious zero-credit AGI phase-in lookup. |
| **4. Statutory factor-default control** | No overriding annual Budget Act factor; otherwise eligible with positive pre-factor credit | **0**, because(a)(2)(B) sets the default factor to zero. Pair with a sourced positive-factor/resource-authorization case after ingest. |

The `$96` sensitivity is part of case 1, not another benchmark household. It arises from the dated worksheet, not by rounding `$99.46`. The projected arithmetic reproductions passed absolute tolerance `$0.0001`; worksheet minimum checks passed exactly. [Successful calculation](household/household-calculation.json), [raw household](household/scenario_023.json), [calculation script](household/check_household.py), and [detailed adjudication](household/adjudication.md) preserve the evidence. This is one household, not a population simulation.

**Upstream attribution resolved from code:** required `gh pr view --json title,mergedAt,files` and `gh pr diff` requests for both PRs were attempted but failed to connect. Local PE Git merge/commit objects provide the fallback; do not describe the timestamps below as retrieved GitHub mergedAt fields.

- [#9363](https://github.com/PolicyEngine/policyengine-us/pull/9363), merge **`7d19aa355671b69fcfb96d18ede3549ea2897d5f`**, commit time **2026-09-01T18:37:55-04:00**, title **“Take smaller of earned-income and AGI credits for CalEITC”**. At that merge, `policyengine_us/variables/gov/states/ca/tax/income/credits/earned_income/ca_eitc.py:64` adds `agi = tax_unit("adjusted_gross_income", period)`; lines 73–74 add `higher_income = max_(earned_income, agi)` and `return min_(credit_for(earned_income), credit_for(higher_income))`. [Saved full diff](household/pr9363-local.diff), lines 252–262, shows these additions.
- [#9542](https://github.com/PolicyEngine/policyengine-us/pull/9542), commit **`7a7ddd7cb5523a1e6e58e1bba46bc37b22a62b79`**, commit time **2026-09-20T14:26:01-04:00**, title **“Fix 2024 CalEITC income boundary and California credit references”**. `parameters/gov/states/ca/tax/income/credits/earned_income/phase_out/final/end.yaml:5` changes **31,950→31,951 for 2024**. Its eligibility module already had a federal-AGI upper-bound check; the PR updates comments/references. It does not change `ca_eitc.py` or add the two-credit comparison. [Saved full diff](household/pr9542-local.diff).

Thus root_causes.json's attribution of the comparison to #9542 should not be carried into the encoder brief; **9363** is the implementing PR.

## 7. Risks

| Risk | Evidence and preparation response |
|---|---|
| Incomplete source unit | Workflow defaults `require_complete_source_unit=True`; its encode step supplies the flag. Finding accounts for the whole section, precise historical/administrative deferrals, and paired exceptions. It forbids deferring the central comparison while calling the task done. |
| Missing annual authority / unsupported test answers | Corpus inventory plus existing source-hold identify the gap. Keep projected 2026, held 2025 and final-law amounts distinct; ingest authoritative annual material before dollar certification. |
| Invalid import input | Helper requires exact jurisdiction and signed-v5 manifests. Empty array is only an admissible placeholder for a still-unresolved dependency strategy. |
| Recursive compile rejection | Pinned-engine code rejects the IRS EIC plural key and the California policy plural keys. No waiver or protected-pin edit is proposed. |
| False assurance from local compiler | Located binary accepts removed syntax. Report both its successful checks and the limits of those checks; rerun with the approved current engine before dispatch. |
| Proof/table grounding rejection | Existing ITIN excerpts contain ellipses. Finding requires exact resolved substrings. July normalized(b) tables collapse repeated cells; compare retained HTML/table identity before asserting missing columns. |
| Wrong baseline or moving ref | `open_pr=true` requires the exact current main tip. Refresh after prerequisite merges; the fixed snapshot command is inspection-only. |
| Collisions / attempt budget | Required open-PR searches in rulespec-us and axiom-encode and the latest 30 targeted runs were attempted but inaccessible. Browser fallback listings were stale. **No collision clearance is claimed.** Repeat same-citation searches and inspect today's runs and failed-attempt budget immediately before dispatch. |

The task's example failed run 35789753522/artifact could not be downloaded; its rejection details are **task-supplied and unverified here**, not cited as an inspected log. The claim of up to 3.5-hour strict CI is likewise task-supplied; no duration guarantee is made. Actual current PR statuses, fresh main tips, workflow budget and production-engine runtime compatibility remain unverified.

Checks completed: corpus membership and version comparison; existing module/import/manifest inventory; pinned-workflow and pinned-engine code inspection; twelve existing-module compiles with the legacy binary; one-household baseline diagnostics and independent Decimal arithmetic; published 2025 worksheet row checks; local diffs for both attribution PRs. Initial household helper invocation used a nonexistent diagnostic after valid outputs and failed; it was not counted as a passing check. The independent valid-diagnostic script and a clean rerun of the requested household helper both passed (exit 0); the latter log is [pe-case-valid.log](household/pe-case-valid.log). No new RuleSpec/tests, full microsimulation, commit or external mutation was performed.

```json
{"lane":"ca-17052","verdict":"BLOCKED","citation":"us-ca/statute/rtc/17052","in_corpus":true,"in_pinned_release":true,"existing_modules":["us-ca/statutes/rtc/17052.yaml","us-ca/policies/income_tax/2026_resident_liability_source_hold.yaml","us-ca/policies/income_tax/pilot_liability_pipeline.yaml","us-ca/statutes/rtc/17041.yaml","us-ca/statutes/rtc/17054.yaml","us/statutes/26/32.yaml"],"blocking_imports":["us:policies/irs/rev-proc-2025-32/earned-income-credit"],"dispatch_command":"gh workflow run targeted-signed-reencode.yml -R TheAxiomFoundation/axiom-encode --ref main -f citation=us-ca/statute/rtc/17052 -f country=us -f rulespec_ref=f43dec520dd392bc5333934f56dad7498363e704 -f pr_base_branch=main -f corpus_ref=8f7d60aaced28ee4252b9237f9d6e02360dc34bc -f rules_engine_ref=af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca -F review_finding=@scratch/ca-17052/review_finding.md -f source_bundle_json='[]' -f existing_signed_imports_json='[]' -f replace_rulespec_path=us-ca/statutes/rtc/17052.yaml -f open_pr=true","prerequisites":["DO NOT EXECUTE the snapshot command: it is inspection-only, not a certified or approved dispatch.","Ingest official FTB 3514 worksheet/table and applicable 2026 factor, resource authorization and indexed parameters with URL/date/SHA provenance; publish and consume an approved release containing them.","Establish a complete admissible California dependency/source route; direct federal imports are rejected by the inspected workflow and the federal 32 closure contains removed plural syntax.","Reconcile waiver activation #1387, workflow pin #1386, drift stage, and activation/release repin chain; that chain alone does not fill the California source gap.","Refresh exact remote main and all immutable refs after prerequisites; inspect current workflow, same-citation PRs/runs and attempt budget; obtain Max's approval for the signed run."]}
```
