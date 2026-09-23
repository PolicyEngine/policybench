# ca-17076 — read-only Axiom preparation

## 1. Verdict

**BLOCKED.** No passing signed dispatch can be specified against today's main. The California provisions exist on corpus main, but their September 14 scope is absent from both the currently pinned August 8 release and the planned August 23 successor. Amount-ready encoding also needs the federal IRC text applicable on January 1, 2025; the inspected current corpus roots contain post-OBBB law. Completing the named serial re-pin chain alone does not resolve either issue.

The statute supports the sandbox's isolated deduction changes for all three households, subject to the stated qualifying-expense/gift assumptions and unchanged benchmark tax context. Independently derived comparison taxes are **$40,522.71 (005), $1,902.59 (022), and $4,429.91 (099)**. Household 099 is entirely a charitable-deduction case; encoding §17076 alone cannot explain its movement.

Inspected rulespec-us main: `f43dec520dd392bc5333934f56dad7498363e704`; corpus main: `942e138e7a8250c9814e774ac9b8e63008148106`. Both were confirmed against live GitHub. Checks occurred on September 22, 2026 America/New_York (through September 23 UTC). The required fetch was attempted first but denied access to `.git/FETCH_HEAD`; live read-only GitHub checks confirmed the cached identity.

This lane followed the task's specific read-only prohibition: **no commits, repository edits, new RuleSpec or module-test YAML, encodes, dispatches, PRs, or external messages**. Scratch contains source copies, exact existing-module compile snapshots, arithmetic, and this report. No orchestrator `-o` destination was exposed in the lane context; the report is retained at `scratch/ca-17076/report.md` for collection.

## 2. Source

All three target rows exist at corpus main in:

`data/corpus/provisions/us-ca/statute/2026-09-14-income-tax-chapter-us-ca-sections-4e26e6efabc3f0c7.jsonl`

| Official provision | Exact canonical citation | JSONL line | Retained source vintage | In pinned release |
| --- | --- | ---: | --- | --- |
| [R&TC 17024.5](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=RTC&sectionNum=17024.5) | `us-ca/statute/rtc/17024.5` | 41 | Captured 2026-09-14; SB 711 §1, effective 2025-10-01 | No |
| [R&TC 17076](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=RTC&sectionNum=17076) | `us-ca/statute/rtc/17076` | 120 | Captured 2026-09-14; SB 711 §11, effective 2025-10-01 | No |
| [R&TC 17201](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=RTC&sectionNum=17201) | `us-ca/statute/rtc/17201` | 227 | Captured 2026-09-14; Stats. 1993 ch. 873 §12 | No |

Raw official HTML is tracked under `data/corpus/sources/us-ca/statute/2026-09-14-income-tax-chapter-us-ca-sections-4e26e6efabc3f0c7/california-leginfo-sections/RTC-<section>.html`. Exact bodies, inventory hashes, and histories are preserved in [source notes](source/notes.md) and [selected rows](source/selected-provisions.json). Collection in September 2026 does not make the relevant SB 711 rules post-freeze law: their effective date was October 1, 2025.

The current pin is `us-rulespec-2026-08-08-obbb-alien-snap`, content SHA256 `0d69a0cdbe024fc2276f3c261c00402bb0a47488ac5f482cc20bd3404980adbc`. I checked its tracked scope manifest and the manifest for `us-rulespec-2026-08-23-canada-338-suspension-union`. Neither includes the September California income-tax scope. An exact-citation scan of all tracked California statute JSONL files found no older copy of these target roots. This is release-manifest/inventory evidence; published release-object signatures were not independently reverified. `axiom-locate release` found neither object locally.

Necessary adjoining authority in the same September scope includes `us-ca/statute/rtc/17049` (line 69), `17250.1` (265), `17250.2` (266), and `17275.5` (282). In particular, [§17250.1(b)](https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=RTC&sectionNum=17250.1) expressly disapplies the increased federal cash-contribution limit. All were checked as source text, not presumed from the fix.

**Historical federal-source prerequisite:** canonical roots `us/statute/26/67` and `us/statute/26/170` were found only in the July 13 recovery scope, with post-OBBB text. The former now places educator expenses in (g) and permanent suspension in (h); the latter includes the 0.5% charitable floor. They cannot silently stand in for California's January 1, 2025 incorporated law.

Ingest the official [2024 USC §67 HTML](https://www.govinfo.gov/content/pkg/USCODE-2024-title26/html/USCODE-2024-title26-subtitleA-chap1-subchapB-partI-sec67.htm) and [2024 USC §170 HTML](https://www.govinfo.gov/content/pkg/USCODE-2024-title26/html/USCODE-2024-title26-subtitleA-chap1-subchapB-partVI-sec170.htm), or their official annual USC XML, with retrieval date, raw SHA256 and a distinct dated expression. Preserve current federal law. Those historical dependency encodings stop at this ingest prerequisite here; no historical corpus citation or future release/ref is invented.

## 3. Existing rulespec-us coverage

There is **no module at 17024.5, 17076, or 17201**, including dotted and slash-normalized variants. These would be new encodings, so `replace_rulespec_path` is empty. No California miscellaneous or charitable deduction computation was found in the scoped main-tree search.

The entire adjacent `us-ca/statutes/rtc/` inventory was read; none implements this disputed stage:

| Existing YAML path beneath that directory | What it encodes |
| --- | --- |
| `17014.yaml`, `17016.yaml` | Residence and residence presumptions |
| `17017.yaml` | Geographic United States definition |
| `17029.yaml`, `17034.yaml` | Repeal survival and default effective dates |
| `17038.yaml` | California CPI series |
| `17041.yaml` | Tax-rate/statutory structure; final liability and inflation outputs deferred |
| `17052.yaml` | CalEITC modifications/parameters; final credit deferred |
| `17053/6.yaml` | Prisoner joint-venture wage credit |
| `17054.yaml`, `17054/7.yaml` | Exemption and senior-head-of-household credit rules; final amounts/qualification deferred |
| `17061.yaml` | Unemployment-insurance refund credit |
| `17062/1.yaml` | AMT incorporation, explicitly deferred: `rules: []` |

The relevant annual and pilot modules are:

- `us-ca/policies/income_tax/2026_resident_liability_source_hold.yaml`, lines 81–85: “The pinned corpus lacks the FTB-published 2026 indexed standard deduction, complete itemized-deduction surface, and indexed exemption credit inputs required for the annual return.” The named hold starts at line 208 and ends in `formula: true` at line 230. Lines 49–51 say its zero sentinel “is not a claim that the taxpayer owes zero California tax.”
- `us-ca/policies/income_tax/pilot_liability_pipeline.yaml`, lines 30–32: “The caller supplies completed worksheet line 3 taxable income after all deductions”; it uses 2025 estimated-tax schedules and excludes taxable-income construction/final-return liability.
- Nearby federal `us/statutes/26/67/h.yaml` says “no miscellaneous itemized deduction is allowed for any taxable year beginning after December 31, 2017”; its allowance judgment is `formula: false`. This is federal denial, not California coverage. `us/statutes/26/67/e.yaml` computes estate/trust AGI only. There is no 67(a)/(b) individual-floor module in this tree.

Thus the California modules do not carry an implemented equivalent of the disputed federal-inheritance behavior; they lack the calculation and expose holds. Full inventory, exact quotes and manifest reads are in [coverage notes](coverage/coverage-notes.md).

**What would lift the hold:** signed California conformity/modifier modules plus applicable-vintage expense classification and the 2% computation address this part of the deduction gap. Charity needs its own §17201/§17250.1 and historical §170 companion. Removing the entire line-208 deduction/exemption hold additionally requires the remaining deduction surface, authoritative 2026 indexed standard-deduction and exemption amounts, and composition from ordinary facts/upstream outputs. The separate CA AGI, rates, credits and ordering holds remain until their own dependencies are complete. Existing annual provenance also requires authorized repair before modern compilation.

## 4. Import closure

Prospective source-local §17076 modifier candidate: **`existing_signed_imports_json=[]`**. There are no suitable existing signed-v5 CA deduction modules to name. The empty existing-import closure has no compile blocker; this does **not** make the missing amount calculation ready.

| Inspected candidate/context | Local current-engine result | Reason to exclude from proposed imports |
| --- | --- | --- |
| Annual CA source-hold module | Fails: removed plural `corpus_citation_paths` | Manual applied-rulespec/v1 manifest; incomplete stage |
| CA estimated-tax pilot | Same failure | Manual v1 manifest; caller-supplied taxable income |
| Federal 67(h) | Compiles, one derived output | Manual v1 manifest; federal denial and wrong jurisdiction |
| Federal 67(e) | Not compiled in this lane | Estate/trust AGI, not this individual's CA deduction; not proposed |
| Federal 26/32 → IRS earned-income-credit module | Imported plural field inspected; no compile run needed for this excluded closure | Unrelated to target and known incompatible provenance |

Verbatim failures are in [annual compile log](coverage/annual_hold.current.compile.log) and [pilot compile log](coverage/pilot.current.compile.log). Existing files were copied byte-for-byte with `git archive` into a minimal scratch tree, not authored or repaired.

The locator returned an old 0.1.0 binary that accepted plural fields; its successful compiles are not current readiness evidence. A canonical 0.2.0 binary rejected both modules and accepted 67(h); its SHA256 is `faf4383622f63c64b861e5772b78b00df97efef4a8315b792b25219033bee75e`. Exact binary-to-commit provenance is unverified. Current engine main `6e709eb1ca7ea686263293d932c759d9dee48a4a`, `src/rulespec.rs:810–824`, independently corroborates recursive plural-field rejection. The protected-run log discussed below also demonstrates rejection with the pinned engine SHA.

The signed workflow helper `src/axiom_encode/prepare_signed_backfill.py:1368–1500` requires same-jurisdiction tracked primary paths, excludes the target/source/dependent paths, and requires applied-rulespec/v5 manifests; the workflow then verifies their signatures. Hence federal modules cannot be casually added to the CA `existing_signed_imports_json`. Plan separate applicable-vintage dependencies and California adapters; final signed paths/symbols must be inspected after they exist. Modifier-only completeness acceptance remains unverified.

## 5. Dispatch inputs

**Do not dispatch the following candidate.** It records exact, observed inputs, but fails the active-release prerequisite and has no ready dollar-computation dependencies. There is no honest complete command that can be promised to pass today. The final JSON deliberately leaves `dispatch_command` empty.

```sh
gh workflow run targeted-signed-reencode.yml \
  -R TheAxiomFoundation/axiom-encode --ref main \
  -f country=us \
  -f rulespec_ref=f43dec520dd392bc5333934f56dad7498363e704 \
  -f pr_base_branch=main \
  -f corpus_ref=942e138e7a8250c9814e774ac9b8e63008148106 \
  -f rules_engine_ref=af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca \
  -f citation=us-ca/statute/rtc/17076 \
  -f replace_rulespec_path= \
  -f 'existing_signed_imports_json=[]' \
  -f 'source_bundle_json=[]' \
  -F 'review_finding=@scratch/ca-17076/review-finding.txt' \
  -f open_pr=true
```

Ref provenance:

| Input | Where verified |
| --- | --- |
| `rulespec_ref=f43dec…` | Local origin/main and live GitHub branch endpoint |
| `corpus_ref=942e138…` | Canonical corpus origin/main, exact tracked rows, live branch endpoint |
| `rules_engine_ref=af6e4e…` | rulespec-us `.axiom/workflow-toolchain.toml` and protected run 35789753522 log |
| Workflow `--ref main` | Required workflow branch gate; inspected encoder main `5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9` |
| Citation/replacement/imports | Exact canonical row; absent target module; inspected import validator |

Optional repair, legacy-replacement, dependent-cascade and queue fields remain their empty defaults; retained-successor paths default to `[]`. `source_bundle_json=[]` is deliberately empty because a valid fresh-source bundle with the historical dependencies has not yet been established. This candidate is for a new primary, not replacement of the annual hold.

The workflow's input block and validation steps were read in this run. Full SHA identities are checked at lines 373–401; corpus/engine must be main ancestors. With `open_pr=true`, `src/axiom_encode/prepare_signed_backfill.py:267–330` requires the exact current PR-base tip, so this recorded rulespec SHA becomes invalid once main advances. Lines 830–876 materialize the release selected by the **rulespec toolchain**, not unrestricted corpus HEAD. The resolver filters active release scopes (`corpus_resolver.py:553–667`). Supplying a newer `corpus_ref` therefore cannot bypass the pin. Encoding runs in `production-signing` and invokes the protected encoder with `--backend openai` (workflow lines 184, 1249–1270).

The immutable future rulespec SHA cannot be filled before the missing release/activation/re-pin lands. Recheck all refs and collisions, validate actual signed dependency closure, and obtain Max's approval for each eventual signed run. This lane does not request or provide that approval.

## 6. Review finding text

The exact prepared `review_finding` payload is also saved in [review-finding.txt](review-finding.txt). It is a prospective brief, not a claim of dispatch readiness.

Encoding regime (verbatim task requirement):

RuleSpec content in any `rulespec-*` repository is produced ONLY by the supervised
encoder: `axiom-encode encode <corpus citation> --backend codex --apply` (local
supervised runtime, subscription Codex auth via a lane CODEX_HOME; never
OPENAI_API_KEY). Every atomic module carries the encoder's apply manifest under
`.axiom/encoding-manifests/`. Hand-written YAML is never a module — not for a
pilot, not for a demo, not "to avoid API spend". The only hand edits allowed are
repair rounds on the encoder's output (findings file + replay) on repos whose
`run-generated-guard` is off, and composed `module.kind: composition` pipelines,
which are assembled, not encoded. Briefs to lanes must say this verbatim; a brief
that says "hand-author" is wrong. New repos set `run-generated-guard: true`.

For rulespec-us, landable content comes from the signed path only: the axiom-encode workflow `targeted-signed-reencode.yml` (workflow_dispatch; the `encode` job runs in environment `production-signing`, and its encode step runs `/opt/axiom-verification/axiom-encode encode --backend openai` with the org key). You never write RuleSpec YAML, never write test YAML for a module, and never run a local encode.

Encode the complete California R&TC 17076 source unit, with California-specific meaning and explicitly identified incorporated-source dependencies. This is a prospective brief: do not dispatch before the source-release and historical-source prerequisites in report.md are satisfied. A modifier-only encoding is not an amount-ready adjudication and must not be represented as clearing the annual liability hold.

Source coverage:
1. Cover 17076(a): apply the incorporated IRC 67 two-percent floor, subject to California modifications. For an ordinary individual with positive applicable federal AGI A and otherwise deductible miscellaneous expenses E, the amount is max(0, E - 0.02*A). Expense deductibility and membership in the miscellaneous pool must be established from ordinary facts and applicable-source rules, not assumed from an input labeled final allowed deduction. Use the January 1, 2025 IRC vintage selected by 17024.5(a)(1)(Q). The ordinary benchmark employee costs are treated as otherwise qualifying; undocumented deductibility/valuation is an explicit case assumption.
2. Cover every condition of 17076(b): a deduction otherwise allowable under California law, described in 17049, and strictly greater than $3,000 must be excluded from the miscellaneous pool. Exclusion from the floor is not denial of the deduction. Do not infer 17049 qualification merely from the amount. The earlier unrestricted-right inclusion, repayment circumstances, and inventory exception belong to 17049; its alternative tax comparison and carryover mechanics may be precisely deferred to that dependency.
3. Cover 17076(c): the referenced vintage IRC 67(g) suspension does not apply. The incorporated pre-OBBB suspension already ends before 2026. Current federal corpus text instead puts educator expenses in (g) and permanent suspension in (h); never bind the California cross-reference to those current subsection meanings.
4. The related conformity encoding must cover 17024.5(a)(1)(Q), (h)(2)(A), the registered-domestic-partner exception (h)(2)(B), (h)(5)-(6), and (i). Federal AGI, not California AGI, governs these percentage limits. Do not imply this narrow slice completes all of 17024.5: if targeting its root, account for each earlier-date branch (a)(1)(A)-(P), uncodified/technical amendment rules (a)(2)-(3), excluded federal references (b), historic debt rules (c), regulations (d), elections/consents (e)-(f), limitations period (g), and remaining terminology/construction rules (h)(1),(3)-(4),(7)-(8), with implementation or precise source-specific deferrals.
5. A separate charity companion is essential for the supplied household comparisons. 17201(a) incorporates Part VI; (b) and (c) separately incorporate Parts VII and IX and must not disappear when its root is encoded. Use pre-OBBB IRC 170 with no 0.5% floor. Include 17250.1(b)'s express exclusion of the increased cash-gift limit; ordinary qualified gifts remain subject to the applicable 50%/30%/20% categories. If encoding that root, also cover or precisely defer its agricultural-research recipient and conservation termination branches. Do not promise the simplified sandbox charity formula covers all noncash gifts, carryovers, substantiation, or donee categories.

Permissible precise deferrals:
- To applicable-vintage incorporated IRC 67 dependencies: the full (b) exclusion classification and (d) impairment definition; (c) pass-through regulation mechanics; (e) estate/trust AGI; and (f) coordination. Classification and the floor cannot remain deferred if the module claims final miscellaneous-dollar outputs.
- To 17049: claim-of-right eligibility details, inventory exception, annual tax comparison and carryovers, while preserving the local 17076(b) strict-dollar and exclusion rule.
- To separate incorporated-source/California modules: other deductions and prohibitions under 17201; qualified charitable recipients, payment, valuation, substantiation including 17275.5, carryovers and special gift classes. No final charity amount is available outside an explicitly supported domain.
- To annual composition: 17077 high-income limitation, standard-versus-itemized election, CA AMT add-back, tax brackets, exemptions, credits and ordering. Final tax amounts below are integration expectations holding other benchmark lines fixed, not outputs that a 17076 atomic module can independently certify. The existing annual hold must remain until its other source requirements and provenance repair are complete.

Required paired positive and blocking tests (request only; this lane authors no test YAML):
- Expenses above, exactly at, and below 2% of applicable federal AGI; zero qualifying expenses.
- 17076(b) qualifying claim-of-right deduction greater than $3,000 versus exactly $3,000; qualifying versus nonqualifying repayment at the same amount, including the 17049 inventory exception. Assert classification as well as dollar results where the dependency supports them.
- Each encoded IRC 67(b) exception against an ordinary cost failing that exception. At minimum pair qualifying impairment-related workplace expenses with otherwise ordinary work expenses. Keep charity outside the miscellaneous pool. Do not import the post-OBBB educator exception into the 2025 vintage.
- Federal AGI different from CA AGI (household 022 supplies a regression), and RDP as-if-spouse AGI versus the ordinary federal-return branch if that exception is encoded.
- Suspension nonapplication in 2025 and 2026 within supported effective periods. No current-federal permanent-denial alias.
- For the charity companion: gifts below the would-be federal floor remain deductible, provided eligibility is met; missing payment/qualification/substantiation blocks the appropriate output. Include cash ceiling and relevant noncash-category boundaries if claimed.
Every companion case must assign every local #input, including all false facts. Proof excerpts must be verbatim substrings of the precisely resolved source. Never alter toolchain pins, workflow pins, CODEOWNERS or waivers to make this run pass.

Worked cases: all are California TY2026. Expenses/gifts below are accepted as otherwise deductible, qualified, paid and substantiated; unlisted tax-preparation fees are zero. All relevant gift ceilings are nonbinding. Federal AGI and other unchanged tax context come from the existing independently verified benchmark traces. Independent decimal arithmetic applies the statute-derived deduction changes to that context; it does not certify unrelated IRA, indexing, filing-status or AMT rules.

Case 1, scenario_005: joint, ages 35/33, no children. Federal and CA AGI $536,764.50. Employee expenses $13,847.8232421875; cash gifts $1,069.7646484375; noncash gifts $1,503.7646484375. Floor $10,735.29; CA miscellaneous deduction $3,112.5332421875; CA charity $2,573.529296875 (frozen charity and misc both zero). Total restored deductions $5,686.0625390625. Existing $1,941.21 high-income limitation remains unchanged; marginal rate is 9.3%. Frozen state tax before refundable credits $41,051.511719; sandbox $40,522.707031. Independent result $40,522.7079028671875, or $40,522.71. Statute supports the corrected treatment and isolated corrected value, not the frozen treatment. Miscellaneous deduction alone would yield approximately $40,762.05; charity is needed for the whole change.

Case 2, scenario_022: single, age 77, no children; preserve explicit single filing status despite a separate surviving-spouse flag. Federal AGI $109,149.1640625; CA AGI $91,524.4140625. Employee expenses $8,350.5439453125; cash gifts $14,693.412109375; noncash gifts $700. Floor $2,182.98328125; CA miscellaneous deduction $6,167.5606640625. CA charity $15,393.412109375; removing the federal floor restores another $545.7458203125. Restored deductions $6,713.306484375; unchanged marginal rate 8%. Frozen $2,439.650146; sandbox $1,902.585449; independent $1,902.58562725, or $1,902.59. Statute supports corrected treatment and isolated corrected value. Applying the floor to CA AGI would be wrong. Miscellaneous alone yields approximately $1,946.25.

Case 3, scenario_099: joint, adults 42/41, children 9/4. Federal/CA AGI $159,585.046875; employee expenses $1,262.6470947265625; cash gifts $11,932.94140625; noncash gifts $688.058837890625. Floor $3,191.7009375 exceeds expenses, so both the frozen and corrected miscellaneous deduction are correctly zero. CA charity $12,621.000244140625; restored charity floor $797.925234375. At unchanged 8%, tax falls $63.83401875. Frozen $4,493.743164; sandbox $4,429.909180; independent $4,429.90914525, or $4,429.91. Statute supports the bundled corrected treatment and isolated corrected tax, but 17076 by itself changes nothing here: this is a charity conformity case.

Case 4, boundary family: ordinary individual, federal AGI $100,000, qualifying ordinary miscellaneous costs $5,000 => $3,000 after the floor; costs $2,000 => $0; costs $1,999 => $0. An otherwise allowable, 17049-qualified $4,000 repayment is excluded from this floor; an otherwise allowable ordinary $4,000 cost without a qualifying exception yields $2,000. At exactly $3,000 the specific 17076(b) exclusion predicate is false; determine any actual deduction under its remaining applicable rules, rather than inventing a denial.

These cases adjudicate the isolated provision changes. Neither set of full benchmark returns is independently certified by this atomic encoding brief. Axiom currently has no runnable CA miscellaneous/charitable deduction result for them; held zero sentinels are not statutory tax values.

## 7. Risks

| Rejection or review risk | How this package addresses it |
| --- | --- |
| Target exists only outside active corpus release | Names exact absent scope and requires a release plus separate gated re-pin; newer corpus checkout alone is insufficient |
| Wrong federal vintage/subsection | Requires retained pre-OBBB sources; distinguishes vintage 67(g) from current 67(g)/(h) |
| Incomplete source unit | Explicitly covers all three 17076 branches and names clause-specific deferrals/dependencies for larger related roots |
| Missing positive/blocking exception tests | Specifies floor, claim-of-right, impairment, AGI/RDP, suspension, and charity boundary pairs; all local inputs, including false ones, assigned |
| Import compile/signature failure | Empty existing-import candidate; excludes manual-v1 CA/federal modules and identifies plural-field failures |
| Misstated household scope | Includes all three moved cases and separates miscellaneous-only effects from charity; no full-return or held-zero parity claim |
| Annual hold prematurely cleared | Identifies remaining indexed amounts, deduction coverage and separate AGI/rate/credit holds |
| Stale PR base | Exact-base-tip rule means refs must be rebuilt after prerequisites land |
| Oversized successor release | Current workflow caps release downloads at 16 MiB. Open encoder #1675 proposes 64 MiB; whether that is required depends on the eventual release object size, not merely its name |

**Collisions and serial chain.** Live exact-citation open-PR searches across rulespec-us and axiom-encode returned no match for 17076, 17024.5 or 17201. I read 30 recent targeted-run records and all fetched runs covering September 22 EDT through the check; none targeted these citations. This is a snapshot, not a reservation. Saved evidence: [collision check](workflow/collision-check.json).

[Rulespec-us #1387](https://github.com/TheAxiomFoundation/rulespec-us/pull/1387) waiver activation and [#1386](https://github.com/TheAxiomFoundation/rulespec-us/pull/1386) workflow-pin update were open; #1384 was already merged at the inspected main. Their PR descriptions confirm the serial order and intended August 23 re-pin. Later drift staging/activation remains prospective in the supplied plan, not a verified merged SHA. That entire chain still lacks this September California scope. [Encoder #1675](https://github.com/TheAxiomFoundation/axiom-encode/pull/1675) is relevant if a larger union is selected. [Encoder #1665](https://github.com/TheAxiomFoundation/axiom-encode/pull/1665) concerns the unrelated 26/32 legacy-import repair; this proposed empty closure does not depend on it.

**Observed failure mode.** Protected [run 35789753522](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/35789753522) failed with the verbatim log message that imported `us:statutes/42/416/l` “declares removed plural `corpus_citation_paths`; every source/proof node must declare exactly one singular `corpus_citation_path`.” Its actual immutable input values and failure lines were read and saved in [run excerpts](workflow/run-35789753522-excerpts.log). The artifact listing was read; download produced a remote file reference, but local DNS prevented retrieving the ZIP. Its `issues.json` was therefore **not inspected**. Additional complete-source-unit rejection details from the task are not independently verified from that artifact here; the complete-source requirement itself is verified in workflow/helper code.

**Checks and limitations.** Three independent Decimal-arithmetic comparisons passed, each within $0.001 of the supplied sandbox sweep; [script](households/hand_arithmetic.py) and [results](households/hand_arithmetic.json) are retained. Sweep rows 75–77, scenario JSON, root-cause record, fix, earlier coverage, and independent verification report were read. An attempted new three-household PE trace stalled in system initialization and was canceled; no new PE simulation result is claimed. AGIs, existing limiter/rates and AMT-zero context are explicitly from the supplied verifier's traces, while this lane's legal deductions and decimal deltas were independently derived. The annual and pilot existing-module compile failures and federal 67(h) compile success were observed in this run. No population computation ran.

[Binding issue #39](https://github.com/TheAxiomFoundation/.github/issues/39) was read through the GitHub connector after shell `gh` networking failed. Its proof, companion-test, signed-generation and decrement-only-waiver rules are reflected in the brief; no waiver, authority-file change or manual encoding is proposed. Remaining uncertainties are final historical-source representation, future release/ref identities, actual signed dependency outputs, encoder acceptance, and complete annual-return authority.

```json
{
  "lane": "ca-17076",
  "verdict": "BLOCKED",
  "citation": "us-ca/statute/rtc/17076",
  "in_corpus": true,
  "in_pinned_release": false,
  "existing_modules": [
    "us-ca/policies/income_tax/2026_resident_liability_source_hold.yaml",
    "us-ca/policies/income_tax/pilot_liability_pipeline.yaml",
    "us/statutes/26/67/h.yaml",
    "us/statutes/26/67/e.yaml"
  ],
  "blocking_imports": [],
  "dispatch_command": "",
  "prerequisites": [
    "Ingest provenance-preserving historical IRC 67 and 170 expressions applicable on 2025-01-01; retain current federal expressions.",
    "Publish a signed corpus release including the September 14 California income-tax scope and required historical federal authority; current August 8 and planned August 23 releases omit the CA targets.",
    "Complete applicable serial waiver/workflow activation steps and a dedicated rulespec-us re-pin to the source-complete release; evaluate the release-size cap before selecting a large union.",
    "Establish signed applicable-vintage classification/calculation dependencies and California adapters; inspect actual signed paths and full closure before specifying an amount-ready dispatch.",
    "Include a separate charity conformity companion for all r11 movements, especially scenario_099.",
    "Refresh immutable refs after main advances, verify exact PR base, recheck collisions, and obtain Max's approval for every signed run.",
    "To lift the entire annual deduction/exemption hold, also complete remaining deductions and authoritative 2026 indexed amounts and repair the annual module's legacy provenance."
  ]
}
```
