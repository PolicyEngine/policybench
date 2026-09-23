# Wisconsin retirement subtraction: signed encoding preparation

Lane `wi-71-05-54m`; inspected September 23, 2026. This is an Axiom coverage and dispatch-readiness package, not a finding against an external oracle. No encoding, repository commit, external write, or workflow dispatch was performed. Evidence is under [scratch/wi-71-05-54m](scratch/wi-71-05-54m/).

The subfleet manifest specifies `/Users/maxghenis/PolicyEngine/_wk/axenc-pb/report-wi-71-05-54m.md`. That path is outside this lane's writable workspace. This file is its same-relative-path worktree counterpart; the orchestrator can collect it. Existing workspace files were preserved.

## 1. Verdict

**BLOCKED.** The statute's substantive text exists in the corpus and is selected by the pinned release manifest, but the requested narrow source unit is not resolvable. The encoder snapshot's own slicing function rejects `us-wi/statute/71.05/6/b/54m`. Separately, the 2025 Schedule SB instructions have discovery entries but no ingested provision or retained PDF in the inspected corpus tree. A source-unit ingest/normalization or resolver fix, the Schedule SB ingest, and an approved containing release/pin are prerequisites. This lane stops dispatch preparation at those source blockers; it supplies no executable dispatch command or invented canonical leaf.

**Household adjudication: the statute supports the corrected $0 for scenario_042 when the retirement subtraction is elected.** The frozen $284.74 is the reproduced unelected-path value. Election is optional in the statute; selecting the lower-tax permitted path is the benchmark/model convention, not a statutory mandate. Section 6 provides the independent arithmetic and its assumptions.

This cannot be certified for dispatch against today's main. The requested `git fetch -q origin` failed with `cannot open '.git/FETCH_HEAD': Operation not permitted`; GitHub CLI reads failed connecting to `api.github.com`. The verified local rulespec-us `origin/main` is **`f43dec520dd392bc5333934f56dad7498363e704`**, the merge of waiver-renewal #1384. The #1387 activation, #1386 workflow-pin, drift stage, and Canada activation/re-pin chain were not verified live. Their named endpoint retains the same Wisconsin scopes and does not remedy either source blocker. After the source prerequisites and approved pin changes, re-check the chain and choose a stable exact main: the workflow checks that base both before encoding and before publishing a PR.

## 2. Source

Official statute: [Wis. Stat. 71.05(6)(b)54m](https://docs.legis.wisconsin.gov/statutes/statutes/71/i/05/6/b/54m). The live Legislature endpoint was unavailable, so the retained official HTML and its normalized corpus record were read.

| Item | Verified evidence |
|---|---|
| Canonical corpus checkout `origin/main` | `942e138e7a8250c9814e774ac9b8e63008148106` |
| Actual canonical provision citation | **`us-wi/statute/71.05`**; one whole-section record, including 54m.a–e |
| Tracked provision file | `data/corpus/provisions/us-wi/statute/2026-07-16-pit-west-chapter-71.jsonl` |
| Retained source | `data/corpus/sources/us-wi/statute/2026-07-16-pit-west-chapter-71/wisconsin-statutes-html/statutes/statutes/71.html` |
| Source URL recorded by corpus | `https://docs.legis.wisconsin.gov/statutes/statutes/71?view=section` |
| Vintage | `source_as_of` and `expression_date`: `2026-04-03`; source version: `2026-07-16-pit-west-chapter-71`; ingest manifest generated July 21 |
| Source HTML SHA256 | `662f8ba8b5410f11f34b4c8a3d0b6767ce778845287e9fa84ddfd3b6f6e50e98`, recomputed from the tracked blob and matching the ingest manifest |
| Consumer release | `us-rulespec-2026-08-08-obbb-alien-snap`, content pin `0d69a0cdbe024fc2276f3c261c00402bb0a47488ac5f482cc20bd3404980adbc` |

The [pinned release manifest](scratch/wi-71-05-54m/pinned-release.json) selects jurisdiction `us-wi`, document class `statute`, version `2026-07-16-pit-west-chapter-71`, and the 2026 Form 1-ES source. Thus the whole-section statute is **in corpus main and within the pinned release's declared selection**. `axiom-locate release` found no local published archive; the archive's bytes/signature were not independently verified. The [Canada endpoint manifest](scratch/wi-71-05-54m/chain-endpoint-release.json) selects those same Wisconsin sources.

The intended child path `us-wi/statute/71.05/6/b/54m` is **not an exact corpus record and fails parent slicing**. The [resolver probe](scratch/wi-71-05-54m/workflow/resolver-probe.log), using unmodified resolver code from encoder commit `5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9`, reports:

```text
Could not isolate 'us-wi/statute/71.05/6/b/54m' from active parent 'us-wi/statute/71.05'; missing structural marker path '6/b/54m'
```

The source labels this subdivision `54m.`; the generic slicer looks for parenthesized markers. `/6/b` is also unsafe: it starts at a cross-reference inside paragraph (a), rather than the subtraction paragraph. `/6` returns over 55,000 characters. Substituting the 100,371-character whole section would expand the source-coverage obligation well beyond this assignment. No such substitution is proposed.

**Required statutory source work:** either normalize/ingest a canonical 54m source unit retaining the subtraction chapeau, all a–e branches, cross-references, official URL, retrieval date, source hash, and effective-date provenance; or land a tested resolver change that isolates that same complete unit from the already retained HTML. An ingestion that creates a new corpus record also needs an approved release and consumer pin selecting it. A resolver-only repair may reuse the already selected statute, subject to signed-runtime validation.

**Schedule SB:** [2025 Schedule SB instructions](https://www.revenue.wi.gov/TaxForms2025/2025-ScheduleSB-Inst.pdf), revision October 2025, page 7 line 16 and page 8 line 17, were read from the official PDF. In corpus main, `manifests/us-wi-tax-forms.yaml` has two case-variant discovery entries, source IDs `taxforms2025-2025-schedulesb-inst-1e6e63914c` and `taxforms2025-2025-schedulesb-inst-7163d493ed`, dated May 23, 2026. These are **not** ingested source records. Neither the Wisconsin provision inventory nor retained-source inventory contains that PDF; neither named release selects a Schedule SB source scope. There is no verified canonical ingested citation for its line 16.

**Required Schedule SB ingest:** the official PDF URL above, format PDF, retaining the original artifact and URL/date/SHA provenance; normalize line 16 with its credit caution and line 17's no-double-counting worksheet as addressable source units. Resolve the case-variant discovery duplicates against the actual artifact. Publish/select an approved signed release. Per the task's stop rule, no Schedule SB dispatch citation or command is supplied before that ingest.

Temporal caution: [DOR Tax Bulletin 233, page 4](https://www.revenue.wi.gov/WisconsinTaxBulletin/233-04-30-WTB.pdf) describes Act 174 amendments effective April 4, 2026. The retained statute includes those amendments despite its April 3 expression label. Source snapshot date and legal effective date must be distinguished. The 2025 instructions also describe a broader Form 1 credit restriction than the retained statute's literal §71.07 cross-reference; resolve that scope/vintage question before encoding a universal credit ban. It does not change this household's zero result.

## 3. Existing rulespec-us coverage

The full tracked tree and targeted text search on the rulespec-us SHA above found **two income-tax modules**, no `us-wi/statutes/71.05...` module, and no 54m subtraction/election implementation. The other Wisconsin primaries are CMS eligibility modules, unrelated to this citation. A historical `pilot_liability_pipeline` manifest remains, but no corresponding primary module exists in this tree; it is not runnable coverage.

| Module | What it encodes and the relevant boundary |
|---|---|
| `us-wi/policies/income_tax/2026_full_year_resident_core.yaml` | Bounded full-year AGI, deductions, exemptions and selected credits. Explicitly excludes other retirement subtractions. Public complete tax outputs are held zero sentinels, not a legal-value computation. |
| `us-wi/policies/income_tax/2026_form1es_estimated_schedule.yaml` | Estimated tax from supplied taxable income and filing selectors. Does not calculate retirement income, an election, or annual liability. |

Relevant verbatim source from the [core snapshot](scratch/wi-71-05-54m/existing-wi-core.txt):

```text
509: and not wi_pit_2026_has_retirement_subtraction_other_than_encoded_military
1630: - name: wi_pit_2026_has_retirement_subtraction_other_than_encoded_military
1634: description: Whether another retirement-system or age-based retirement subtraction applies.
```

Its direct-subtraction formula, lines 647–652, comprises U.S. obligation interest, federally taxable Social Security, military/uniformed-services retirement, and specified insurance subtractions. It has no ordinary age-67 retirement subtraction. Lines 1320–1335 name `wi_pit_2026_complete_tax_after_nonrefundable_credits`, describe it as held pending the annual Tax Table, and set `formula: 0`.

The [estimated-schedule snapshot](scratch/wi-71-05-54m/existing-wi-estimated.txt), lines 23–29, states:

```text
It does not
construct deductions, exemptions, or annual-return taxable income;
apply credits or return rounding; prorate nonresident or part-year-
resident brackets; map surviving-spouse status; compute estimated
payments or final annual liability; or claim exact PolicyEngine
parity.
```

**Axiom conclusion:** missing coverage, not the same demonstrated numerical defect. Neither module implements the two election paths needed to adjudicate the benchmark output. A held zero cannot be counted as an Axiom match to the independently derived zero. A new atomic subtraction module would fill one component; a later governed composition would still need to wire its elected income and credit consequences consistently into the return outputs.

## 4. Import closure

**Candidate `existing_signed_imports_json`: `[]`.** A narrow atomic subtraction module should use retirement receipts, federal taxability/qualification, age, filing/election, already-exempt amounts, and residency/allocation facts. It need not import federal EITC or a whole state return. Its proposed import closure is empty, so no import reaches 26/32 or the known EITC dependency.

The workflow helper accepts tracked primary YAML **paths**, not module IDs, and requires signed-v5 manifests in the target's exact `us-wi` jurisdiction. Both adjacent tax modules have `axiom-encode/applied-rulespec/v1`, `backend: manual` manifests, so neither is an eligible signed-v5 import.

| Nearby module, excluded from proposed closure | Compile evidence |
|---|---|
| `us-wi:policies/income_tax/2026_full_year_resident_core` | **Fails** with the canonical local v0.2.0 binary: removed plural `corpus_citation_paths` at module line 6. [Actual diagnostic](scratch/wi-71-05-54m/wi-core-current-compile.log). |
| `us-wi:policies/income_tax/2026_form1es_estimated_schedule` | **Loads**, compiling five derived outputs. Still not a signed-v5 import and not needed. [Compile log](scratch/wi-71-05-54m/wi-estimated-current-compile.log). |

The compile inputs were byte-identical `git show` snapshots under an isolated scratch `rulespec-us` root; no RuleSpec was authored or repaired. Binary: `/Users/maxghenis/TheAxiomFoundation/axiom-rules-engine/target/release/axiom-rules-engine`, SHA256 `faf4383622f63c64b861e5772b78b00df97efef4a8315b792b25219033bee75e`. Its exact build commit is unverified. Independently, engine source at `6e709eb1ca7ea686263293d932c759d9dee48a4a`, `src/rulespec.rs:813–823`, explicitly rejects the plural key.

`axiom-locate engine` initially returned an older v0.1.0 binary that compiled both modules. That legacy result is retained in the scratch logs but is not used to assert current signed-runtime compatibility.

## 5. Dispatch inputs

**No eligible `gh workflow run` command exists for this package yet.** Supplying the unresolved child, a discovery-only Schedule SB citation, or an unapproved broader whole-section target would not meet the requested pass-ready standard. This is the task's source-ingestion stop condition, not a request for additional permission. `dispatch_command` is therefore empty below.

Verified values for the orchestrator's eventual reconstruction, **not a dispatch authorization**:

| Input / workflow selector | Verified value or disposition |
|---|---|
| Repository / workflow / ref | `TheAxiomFoundation/axiom-encode`, `targeted-signed-reencode.yml`, `main` |
| Inspected workflow commit | `5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9`, local encoder `origin/main` |
| `country`, `pr_base_branch` | `us`, `main` |
| `rulespec_ref` | Observed `f43dec520dd392bc5333934f56dad7498363e704`; must be refreshed to the exact stable main after prerequisites |
| `corpus_ref` | Observed `942e138e7a8250c9814e774ac9b8e63008148106`; a source ingest will require a newly verified containing commit |
| `rules_engine_ref` | Inspected source `6e709eb1ca7ea686263293d932c759d9dee48a4a`; verify approved runtime/ancestry before use |
| `citation` | **Unset:** actual record is `us-wi/statute/71.05`; desired child `/6/b/54m` fails resolution |
| `replace_rulespec_path` | Empty for a new atomic module; do not replace the broad annual core |
| `existing_signed_imports_json` | `[]` |
| `source_bundle_json` | `[]`; no guessed Schedule SB source citation |
| `review_finding` | Section 6, revised after source-unit and vintage resolution |
| `open_pr` | `true` for the eventual Max-approved run |
| Repair/dependent/legacy/queue inputs | Empty/default; no repair run or dependent transaction proposed |

Mechanisms read in the [workflow](scratch/wi-71-05-54m/workflow/targeted-signed-reencode.yml) and [helper](scratch/wi-71-05-54m/workflow/prepare_signed_backfill_impl.py): input block lines 4–115; immutable lowercase 40-character checkout checks and corpus/engine ancestry at workflow lines 365–401; exact main requirement in helper lines 267–332; main re-check before publication at workflow lines 3590–3593. The workflow uses `production-signing`, `/opt/axiom-verification/axiom-encode encode --backend openai --apply`, and complete-source-unit validation. Release materialization at workflow lines 827–877 follows the RuleSpec checkout's pin; changing `corpus_ref` alone does not make an unselected new source usable.

The named serial chain is therefore a scheduling prerequisite to re-check, **not a sufficient source fix**. Once that chain and required source/release work settle, re-read live main, workflow, imports, and same-citation run history, fill the new immutable values, and let Max approve the concrete signed dispatch.

## 6. Review finding text

The following is a prospective finding brief. It must be finalized against the resolved source unit after the blockers in section 2 are removed.

**Required coverage.** Encode the complete 54m.a–e unit, including the applicable taxable-year start, qualified-plan/IRC 408 receipt restriction, previously exempt government/military/uniformed-services/railroad payments, age at year-end, individual $24,000 cap, joint $48,000 pooling when both spouses qualify, §71.07 credit/carryover prohibition upon claiming, part-year allocation and nonresident exclusion. The provision has no general AGI phaseout; do not borrow subdivision 54's income thresholds. Derive the permitted subtraction and the consequences of a supplied election fact. Do not import a minimum-tax/tie-breaking policy into statutory eligibility. Use one singular canonical source path per source/proof node and verbatim excerpts from the actual resolved text.

**Precisely deferred boundaries.** Defer computing federal plan qualification and federal taxability to externally established facts, while applying those conditions explicitly. Defer separate exemption computations under 71.05(1)(a)/(am)/(an) and railroad law, while removing their already-exempt amounts from the base. Defer the sibling 54/line-17 entitlement, full AGI construction, indexed deduction, annual tax-table computation and individual credit formulas to separate source units/composition. Expose the subtraction and credit restriction so that composition can recompute income/deduction/tax and report one consistent elected return. Do not claim complete annual tax from this atom. If part-year mixed-spouse or zero-denominator cases cannot be supported from the resolved authority, identify those cases precisely and fail closed with a coverage hold; do not return a normal-looking final amount or silently omit paragraph e.

**Instruction boundary.** Once ingested, account for line 16's federally taxable and previously subtracted income limits and credit caution. Preserve the line-17 worksheet's prevention of double subtraction. Its federal-AGI eligibility is determined before the Wisconsin subtraction; a reduced Wisconsin AGI cannot create federal-AGI eligibility. Resolve the 2025 instructions versus amended statutory credit scope before making all Form 1 credits zero. Do not disable tax withholding or estimated payments as though they were prohibited credits.

**Required paired tests.** Age 67 versus 66; taxable-year beginning after 2024 versus in 2024; election true versus false; qualifying taxable IRA/plan receipts versus unqualified/already-exempt receipts; both joint spouses age 67 versus one younger, including all distributions paid to one spouse; full-year/part-year eligibility versus nonresident; ordinary permitted credit and prior-year carryover without an election versus their §71.07 prohibition when the subtraction is claimed. Assign every local `#input`, including all false flags, in every companion case. Include allocation caps and no-double-subtraction boundaries after the relevant sources are resolved. New failures have no waiver route.

**Worked case 1 — the entire moved benchmark set: scenario_042.** The [exact root-cause filter](scratch/wi-71-05-54m/benchmark-moves.json) returns one moved output, `state_income_tax_before_refundable_credits`:

| Household facts / result | Value |
|---|---:|
| Tax year / state / modeled filing status | 2026 / WI / single |
| Adult age; spouse/dependents | 79; none |
| Taxable IRA / private pension | $19,200 / $4,886 |
| Already tax-exempt IRA, not included in subtraction base | $4,700 |
| Frozen 1.755.4 output, freshly reproduced | $284.74090576171875 |
| Supplied sandbox-corrected output | $0 |
| Independently derived elected-path output | **$0** |

The [scenario record](scratch/wi-71-05-54m/scenario_042.json) also supplies interest $175, ordinary dividends $5,920, qualified dividends $928, farm loss $1,127.2940673828125, Social Security dependent benefits $29,580, capital-gain distributions $3,753 and qualified BDC income $70.93914031982422. `is_surviving_spouse=true` is present, but the household calculation returns `SINGLE`; no $48,000 cap is assumed. Full-year resident treatment and an elected subtraction are explicit case assumptions.

On the r06-isolated income base, ordinary Wisconsin income excluding Social Security is independently summed as:

```text
5,920 + 928 + 175 + 19,200 + 4,886 - 1,127.2940673828125
  = 29,981.7059326171875
Eligible retirement receipts = 19,200 + 4,886 = 24,086
Elected subtraction = min(24,086, 24,000) = 24,000
Post-subtraction income = 5,981.7059326171875
Taxable income = max(0, 5,981.7059326171875 - 13,960 - 950) = 0
```

The $24,000 amount assumes the private pension is from a qualifying plan; the **zero-tax conclusion does not require that assumption**. Using only the explicit taxable IRA gives $10,781.7059326171875 remaining income. Even adding the full $3,753 capital distribution and $70.93914031982422 BDC amount conservatively gives $14,605.64507293701172, still below $13,960 + $950 = $14,910. This upper bound is not an assertion about the exact tax treatment of those additional items.

The $13,960 deduction is the official 2026 single schedule for income through $20,119; the $950 exemption combines the $700 personal amount and $250 age-65 amount. [2026 Form 1-ES instructions, page 2](https://www.revenue.wi.gov/TaxForms2026/2026-Form1-ES-inst.pdf). The statute supplies the Social Security subtraction and personal exemptions in 71.05. Zero taxable income yields zero pre-credit tax; a barred credit cannot create positive tax. The only observed standard-path credit was the $300 school-property credit; observed refundable credits were zero. Federal AGI was $43,637.652, so the single-filer line-17 $15,000 ceiling was not met.

**Adjudication: supports the corrected $0 on the elected return.** The frozen $284.74 is the reproduced model's unelected-path calculation. The statute permits leaving the subtraction unclaimed; this review does not certify that model amount as the lawful unelected liability. It does not represent the elected lower-tax path being benchmarked. No signed Axiom numeric result exists yet.

**Worked case 2 — individual threshold.** Full-year resident, nonjoint, 2026, age 67, $30,000 taxable IRC 408 IRA, no previously exempt amount, election true: subtraction **$24,000**, and §71.07 credits/carryovers barred. Change only age to 66: subtraction **$0**. Change only election to false: subtraction **$0**, and this provision's credit bar does not apply. A year beginning in 2024 also gives **$0** under this provision.

**Worked case 3 — joint pooling.** Full-year joint filers aged 67/67, qualifying taxable IRA receipts $48,000/$0, election true: **$48,000** subtraction. Ages 67/66 with the same receipts: **$24,000**. Ages 66/67 with the same receipts: **$0**, because only the younger spouse received the income. The first result tests pooling independent of receipt allocation; it must not be capped at $24,000 merely because only one spouse received the distribution.

**Worked case 4 — exclusions and residency.** Age 70, single, full-year resident, election true, receipts consisting of $20,000 independently exempt military retirement plus $10,000 taxable IRC 408 IRA: subtraction **$10,000**. A separate part-year variant with $30,000 qualifying IRA and statutory allocation numerator $20,000 / denominator $40,000 has limit **$12,000**. A nonresident otherwise eligible has subtraction **$0**. These test subtraction outputs, not invented complete tax liabilities.

The binding preparation regime supplied for encoder handoff is reproduced verbatim:

> RuleSpec content in any `rulespec-*` repository is produced ONLY by the supervised
> encoder: `axiom-encode encode <corpus citation> --backend codex --apply` (local
> supervised runtime, subscription Codex auth via a lane CODEX_HOME; never
> OPENAI_API_KEY). Every atomic module carries the encoder's apply manifest under
> `.axiom/encoding-manifests/`. Hand-written YAML is never a module — not for a
> pilot, not for a demo, not "to avoid API spend". The only hand edits allowed are
> repair rounds on the encoder's output (findings file + replay) on repos whose
> `run-generated-guard` is off, and composed `module.kind: composition` pipelines,
> which are assembled, not encoded. Briefs to lanes must say this verbatim; a brief
> that says "hand-author" is wrong. New repos set `run-generated-guard: true`.

For rulespec-us, landable content comes from the signed path only: the axiom-encode workflow `targeted-signed-reencode.yml` (workflow_dispatch; the `encode` job runs in environment `production-signing`, and its encode step runs `/opt/axiom-verification/axiom-encode encode --backend openai` with the org key). You never write RuleSpec YAML, never write test YAML for a module, and never run a local encode.

## 7. Risks

- **Source resolution and release selection:** verified leaf-slicing failure and missing Schedule SB ingest are hard blockers. Whole-section substitution would create a much larger complete-source-unit obligation. Require the exact source unit and validate its bytes before a paid/signed run.
- **Incomplete source coverage:** an age/cap-only formula would omit exclusions, optional election, pooling, credit carryovers and residence. The finding covers a–e and identifies external computation boundaries; any unresolved part-year subcase must be precisely deferred and held.
- **Unsuitable imports:** the annual core fails current-engine compilation and both neighboring tax manifests are v1/manual. The proposed empty closure avoids these and the federal EITC path. It does not repair the annual core.
- **Proof/test rejection:** use substrings of the resolved provision, singular source paths, and complete local input assignments with positive/blocking pairs. Do not alter toolchain, workflow pins, CODEOWNERS or waivers in this feature. [Binding issue #39](https://github.com/TheAxiomFoundation/.github/issues/39) was successfully read through the web tool after the requested CLI read failed.
- **Temporal/credit scope:** April 2026 amendments and October 2025 instructions need explicit version treatment. Do not infer that every refundable credit outside §71.07 is barred solely from the current 54m.d cross-reference. The benchmark case's result is insensitive to that unresolved general scope.
- **Annual liability claim:** the existing core's missing annual tax table is a separate coverage hold. An atomic subtraction encoding does not establish complete Wisconsin liability coverage; the zero household derivation is independently supported by zero taxable income.
- **Live collisions and moving main — unverified:** attempted the required recent signed-run list and open-PR searches for `71.05` in rulespec-us and axiom-encode; CLI requests failed. Web attempts for current filtered PRs, #1387/#1386, the workflow runs page and run 35789753522 were unavailable; a cached August PR page cannot clear September 23 collisions. No claim of “no collisions” or inspection of that failure artifact is made. Re-check open PRs and today's runs for `71.05`, `54m`, and Schedule SB before dispatch; exact-main validation can invalidate a run during the serial chain. [Workflow-readiness evidence](scratch/wi-71-05-54m/workflow/notes.md).

Validation completed: exact affected-row extraction (one household); one pinned 1.755.4 household reproduction; independent decimal arithmetic, including the IRA-only upper bound; exact corpus/release/module inventory checks; resolver-owned child-slicing probe; and compilation of the two unchanged existing modules with the current local binary (one expected schema failure, one success). The reproduction command and recorded intermediates are in the [household research notes](scratch/wi-71-05-54m/statute-household-notes.md). No population run, new RuleSpec, module test YAML, local encode, signed run, or external repository mutation was performed.

In the JSON below, `citation` and the two presence booleans refer to the **existing whole-section record** and the release manifest's source selection. They do not assert that the requested 54m child or Schedule SB is resolver-ready. `blocking_imports` describes the proposed empty closure; the incompatible neighboring core is documented above.

```json
{
  "lane": "wi-71-05-54m",
  "verdict": "BLOCKED",
  "citation": "us-wi/statute/71.05",
  "in_corpus": true,
  "in_pinned_release": true,
  "requested_leaf": "us-wi/statute/71.05/6/b/54m",
  "requested_leaf_resolvable": false,
  "schedule_sb_in_corpus": false,
  "release_archive_verified": false,
  "existing_modules": [
    "us-wi/policies/income_tax/2026_full_year_resident_core.yaml",
    "us-wi/policies/income_tax/2026_form1es_estimated_schedule.yaml"
  ],
  "blocking_imports": [],
  "dispatch_command": "",
  "prerequisites": [
    "Make the complete 71.05(6)(b)54m source unit canonically resolvable through governed ingestion/normalization or a tested resolver repair.",
    "Ingest the official 2025 Schedule SB PDF with URL/date/SHA provenance and addressable line 16 and line 17 context; reconcile effective dates and credit scope.",
    "Publish and activate an approved containing release and consumer pin for any newly ingested source; the named Canada chain alone does not add Schedule SB.",
    "Re-verify the serial re-pin chain, live exact rulespec-us main, approved corpus/engine/workflow refs, signed-release bytes, and same-citation open PRs/runs.",
    "Finalize the immutable dispatch command for the verified narrow citation and obtain Max's signed-run approval."
  ]
}
```
