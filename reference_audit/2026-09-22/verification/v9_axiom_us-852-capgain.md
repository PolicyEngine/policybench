# us-852-capgain — Axiom preparation report

Prepared 2026-09-23. This is an Axiom coverage and source-preparation package, not a finding filed against an oracle. No encoding, signed run, repository change, commit, PR, or approval was performed. Scratch evidence is in `scratch/us-852-capgain/` in the assigned workspace.

## 1. Verdict

**BLOCKED — ingest §852 before dispatch.** Neither `us/statute/26/852` nor any descendant has a normalized provision row in axiom-corpus main `942e138e7a8250c9814e774ac9b8e63008148106`. Consequently the intended §852(b)(3)(B) and (C) citations cannot currently resolve in the pinned release. The existing §61 module does not supply the missing distribution classification.

The currently planned re-pin to `us-rulespec-2026-08-23-canada-338-suspension-union` is **insufficient**: its manifest does not introduce a §852 source scope. This package cannot dispatch against today's main, or merely after that chain. It needs an official §852 ingest, publication in a signed release, and a dedicated approved rulespec-us pin to that release. A separate source decision is needed if the encoding includes Form 1040 reporting: the available instructions are for **2025**, not a verified final 2026 form.

The independent provision-level reading supports including **$3,753, $180 and $1,170** as long-term capital gains for scenarios **042, 051 and 091**, respectively. Scenario 051 is an additional moved household present in the sweep but omitted from the assignment's short summary. All four moved benchmark outputs were reproduced. This conclusion does not certify complete state returns.

Rulespec main inspected: `f43dec520dd392bc5333934f56dad7498363e704`. The required local fetch was attempted and denied at `.git/FETCH_HEAD` by workspace permissions; no escalation was attempted. Read-only GitHub ref queries independently confirmed that both local `origin/main` hashes above matched remote main. All repository reads used those immutable trees.

## 2. Source

| Authority | Official source and canonical citation | Corpus main and pinned release |
|---|---|---|
| §852(b)(3)(B), shareholder treatment | [OLRC §852](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section852&num=0&edition=prelim); text successfully read from the [GovInfo 2024 edition](https://www.govinfo.gov/content/pkg/USCODE-2024-title26/pdf/USCODE-2024-title26-subtitleA-chap1-subchapM-partI-sec852.pdf), PDF pp. 1–2. Intended citation: `us/statute/26/852/b/3/B`. | **Absent.** This is the intended canonical spelling, not an existing resolvable citation. No tracked normalized provision file or corpus source vintage can be supplied for it. |
| §852(b)(3)(C), definition and excess allocations | Same official section. Intended citation: `us/statute/26/852/b/3/C`, with descendants preserving uppercase subparagraph and subclause letters. | **Absent**, including descendants; absent from the current and planned Canada-union release scope inventories. |
| §61(a)(3), inclusion of property gains | [OLRC §61](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61&num=0&edition=prelim); [GovInfo 2024 edition](https://www.govinfo.gov/content/pkg/USCODE-2024-title26/html/USCODE-2024-title26-subtitleA-chap1-subchapB-partI-sec61.htm). Exact citation `us/statute/26/61/a/3`; section citation `us/statute/26/61`. | **Present and in the pinned scope.** `data/corpus/provisions/us/statute/2026-07-13-recovery-r2026-07-15-self-contained-r2026-07-17-dedup.jsonl`. Source-as-of and expression date `2026-07-13`; publication `Online@119-100`, source created `2026-04-17`. Retained source is `data/corpus/sources/us/statute/2026-07-13-recovery-r2026-07-15-self-contained-r2026-07-17-dedup/official-documents/usc26-section-61.xml`. |
| Form 1040 capital gains without Schedule D | [IRS Form 1040 instructions](https://www.irs.gov/instructions/i1040gi). Exact corpus citation `us/form/irs/ty2025/i1040gi/block-83`, “Capital Gain or (Loss).” | **Present in main, outside both releases examined.** `data/corpus/provisions/us/form/2026-09-10-tax-irs-forms-ty2025.jsonl`; HTML source-as-of `2026-09-10`, expression date `2025-01-01`, tax year **2025**. Source snapshot `data/corpus/sources/us/form/2026-09-10-tax-irs-forms-ty2025/official-documents/irs-i1040gi-ty2025.html`. It uses line **7a** and the line **7b** checkbox. Do not label it final 2026 instructions. |

The pinned release is `us-rulespec-2026-08-08-obbb-alien-snap`, content SHA-256 `0d69a0cdbe024fc2276f3c261c00402bb0a47488ac5f482cc20bd3404980adbc`, read from `.axiom/toolchain.toml`. Its manifest is `manifests/releases/us-rulespec-2026-08-08-obbb-alien-snap.json`. Release-scope membership was checked against tracked manifests and normalized rows; the published release object was not downloaded or cryptographically re-verified in this lane. `axiom-locate release <name>` found no local materialization.

**Required ingest:** retain an official, dated §852 source, preferably OLRC USLM XML, or the official GovInfo section PDF with a reproducible extraction. Record the exact download URL, retrieval date, source SHA-256, legislative release point and effective-date provenance. Normalize §852(b)(3)(B), all of (C)(i)–(vi), and the context/cross-reference material needed to establish applicability and exceptions; preserve hierarchy and verbatim text. The 2024-edition PDF was read; the current OLRC search result also reproduced the relevant B/C text, but direct retrieval of its complete page failed. Confirm the release point and law applicable to 2026 during ingest rather than treating retrieval date or the older edition as a 2026 consolidation. If form-routing behavior is included, use a separately dated IRS source and an explicit tax-year contract.

Evidence: [saved §61 rows](../scratch/us-852-capgain/61-corpus.jsonl), [IRS matches](../scratch/us-852-capgain/form1040-corpus-matches.jsonl), [pinned manifest](../scratch/us-852-capgain/pinned-release-manifest.json), [Canada-union US scopes](../scratch/us-852-capgain/canada-union-us-scope.json), and the empty exact-citation searches `852-citation-search.txt` / `852-all-federal-provision-search.txt`. The latter checked all 289 tracked federal normalized-provision files across document classes. This establishes absence of an encodable row, not absence of every possible mention in retained raw source files.

Under the assignment's “If the corpus lacks it … stop there” instruction, **dispatch preparation stops at this ingest prerequisite**. The remaining sections preserve the requested coverage, independent household reading, and future review requirements; they are not a dispatch-ready encoding brief.

## 3. Existing rulespec-us coverage

The tracked tree and federal module text at the stated rulespec SHA contain no §852 module or module implementing capital-gain-distribution/Schedule D routing. Relevant nearby coverage is:

| Module | What the inspected code does; relationship to the missing provision |
|---|---|
| `us/statutes/26/61.yaml` | Lines 27–41 sum enumerated income categories, including `+ max(0, gains_derived_from_dealings_in_property)`. Lines 66–70 define `gross_income` independently as `max(0, all_income_from_whatever_source_derived - amounts_otherwise_provided_excluded_from_gross_income_under_this_subtitle)`. It includes a gain supplied by the caller, but neither classifies a RIC dividend nor connects that classified amount automatically to the aggregate. No Schedule D gate was found here. |
| `us/statutes/26/62.yaml` | Line 56: `formula: max(0, gross_income - deductions_described_in_subsection_a)`. It consumes externally supplied gross income and deduction amounts, without identifying §852 dividends or form-routing amounts. |
| `us/statutes/26/1222.yaml` | Defines capital-gain and loss categories and netting. Its long-term-gain rule consumes `gains_from_sales_or_exchanges_of_capital_assets_held_more_than_one_year_taken_into_account_in_gross_income`. The missing §852 deemed long-term treatment is not derived from a distribution input. |
| `us/statutes/26/1/h.yaml` | Lines 118–125 compute the preferential base from `max(0, long_term_capital_gains)`, net short-term losses, the investment-income election and `+ qualified_dividend_income`. This consumes an already classified gain. |
| `us/policies/irs/rev-proc-2025-32/capital-gains.yaml` | Supplies 2026 zero-rate and 15-percent thresholds; e.g. `capital_gains_zero_rate_threshold_single: 49450`. It does not classify distributions. |
| `us/statutes/26/1411.yaml` | Lines 180–188 include `taxable_net_gain_from_dispositions_after_active_partnership_s_corporation_exception` alongside other investment-income inputs. It does not supply the missing §852 classification or general gross-income connection. |

These are **coverage and composition boundaries**, not a demonstrated repetition of the benchmark omission within those formulas. An isolated §61 inclusion test with a caller-supplied amount does not make §852 already encoded, and does not warrant NOT-NEEDED.

The §61 and §62 manifests exist under the legacy nested `us/.axiom/encoding-manifests/` directory and declare `axiom-encode/applied-rulespec/v1`, HMAC signatures. The other nearby manifests inspected are also v1. None is an eligible signed-v5 existing import under the present workflow parser. Immutable copies and the full inventory are retained in [coverage evidence](../scratch/us-852-capgain/coverage/module-inventory.json).

## 4. Import closure

**Candidate `existing_signed_imports_json`: `[]`.** No existing signed-v5 module was established as a suitable required direct import for the narrow classification task. This is a future candidate only; no new module exists whose actual closure could be tested. A §61 legal citation is not automatically a computational import of the old §61 module.

After ingest, an atomic §852(C) definition and §852(B) shareholder-treatment dependency, or a supported fresh-source bundle covering both, should be reviewed before choosing the final target. Do not select the whole §852(b)(3) source unit and silently omit (A), (D) or (E). Do not import §32 merely to create a household-wide tax pipeline.

The neighboring existing closures were inspected and compiled **without modifying their bytes**:

| Existing root and complete additional closure | Local discovered engine | Current engine / dispatch conclusion |
|---|---|---|
| §61; §62 (each has no imports) | Both compile. | Current binary not executed; legacy v1 manifests prevent signed-v5 selection. |
| §1222 → §1211, §1212(a)(1) → §172(c) | All compile. | No plural-key barrier found in this closure; current binary not executed, all inspected manifests v1. |
| §1(h) → IRS capital-gains thresholds | Both compile. | **Current schema load barrier:** the imported threshold module contains `source_verification.values`; current `SourceVerification` rejects unknown fields and has no `values` field. This is a source-code inference, not a current-binary test. |
| §1411 → §67(e), §911(a)(1), §911(d)(6) | All compile. | No plural-key barrier found; current binary not executed, all inspected manifests v1. |
| §32 → §32(c)(2) → §112; §152(c); §7703 → §151 → §911(a), §931, §933; IRS earned-income-credit thresholds | All compile in the old binary. | **Current load failure:** `us:policies/irs/rev-proc-2025-32/earned-income-credit` declares removed `corpus_citation_paths`. Any closure reaching it fails the current recursive loader. Exclude this entire unrelated dependency path. |

`axiom-locate engine` resolved `/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine`. Its checkout HEAD is `ffd8213271947b0189a9dd61a055c1e0e78908a0`, and it accepted the retired plural field. That is why its 22 successful module compile checks **do not establish compatibility with today's signed runtime**. The binary's build commit was not independently attested.

Current engine main `6e709eb1ca7ea686263293d932c759d9dee48a4a`, [`src/rulespec.rs`](https://github.com/TheAxiomFoundation/axiom-rules-engine/blob/6e709eb1ca7ea686263293d932c759d9dee48a4a/src/rulespec.rs), rejects plural keys at lines 819–823; lines 1086–1095 validate every loaded module and recurse into imports. The typed source-verification schema also rejects unknown fields. [Compile commands/results](../scratch/us-852-capgain/coverage/compile-results.json) and [current source](../scratch/us-852-capgain/workflow/engine-rulespec.txt) retain the distinction.

There are **no blocking imports in the proposed empty selection**. There are unresolved source and dependency-design prerequisites, and the generated closure must be checked again: an empty dispatch import array does not prevent the encoder from introducing other imports. Protected [run 35789753522](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/35789753522) did exactly that and failed on §416(l)'s plural field.

## 5. Dispatch inputs

**No executable `gh workflow run` command is supplied.** A command claiming an existing §852 citation or a release containing it would be false. The assignment's source-missing stop rule controls this exception to the requested command format. No placeholder or knowingly failing command should be dispatched.

The following immutable references were verified by GitHub GET queries during this run; they are evidence of current state, **not future approved dispatch inputs**:

| Input / implementation | Verified value | Origin |
|---|---|---|
| `rulespec_ref` | `f43dec520dd392bc5333934f56dad7498363e704` | rulespec-us remote `refs/heads/main`, matching local `origin/main` |
| `corpus_ref` | `942e138e7a8250c9814e774ac9b8e63008148106` | axiom-corpus remote `refs/heads/main`, matching local `origin/main` |
| `rules_engine_ref` | `6e709eb1ca7ea686263293d932c759d9dee48a4a` | axiom-rules-engine remote `refs/heads/main` |
| workflow code read | `5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9` | axiom-encode remote main; workflow blob `b3ef651c6167342e366ddcc749193ff7e2efa45b` |
| `citation` | Intended `us/statute/26/852/b/3/B`, paired with (C); **unresolvable today** | Intended OLRC hierarchy; ingest must establish actual normalized rows |
| `country`, `pr_base_branch`, `open_pr` | Intended `us`, `main`, `true` | Present workflow input schema; no action taken |
| `replace_rulespec_path` | Omit for a genuinely new target | No existing target found |
| `existing_signed_imports_json` | Candidate `[]` | No eligible existing signed-v5 dependency established |

The [workflow](https://github.com/TheAxiomFoundation/axiom-encode/blob/5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9/.github/workflows/targeted-signed-reencode.yml) and [helper implementation](https://github.com/TheAxiomFoundation/axiom-encode/blob/5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9/src/axiom_encode/prepare_signed_backfill.py) were read in full. Relevant constraints:

- Inputs require lowercase 40-character immutable repository SHAs. For ordinary `open_pr=true` dispatch, `rulespec_ref` must equal the exact remote main tip when validated; today's SHA will become unsuitable after prerequisite merges.
- Workflow lines 826–875 materialize the release from rulespec-us's pin. Moving only `corpus_ref` cannot widen that release.
- Existing-import entries are tracked same-jurisdiction **file paths**, not module IDs. Helper lines 1368–1510 require their canonical manifests to be signed-v5.
- The protected encode job uses environment `production-signing` and `/opt/axiom-verification/axiom-encode encode --backend openai ... --apply`; complete-source-unit is enabled by default. No local encode is permitted for this task.

After ingest and dedicated re-pin, the orchestrator must refresh these identities, verify the resolved B/C source units and actual closure, finalize the fresh-source strategy, assemble the complete command, and obtain Max's approval for that specific signed run.

## 6. Review finding text

**Independent review memo retained for the post-ingest brief; not a ready `review_finding` submission.**

Encode the shareholder treatment in §852(b)(3)(B) and the entire capital-gain-dividend definition in (C). The statute treats a qualifying capital gain dividend as gain on a capital asset held more than one year. Together with §61(a)(3), this requires inclusion of the gain; filing Schedule D is not a condition of that treatment. IRS instructions expressly provide a direct Form 1040 reporting route. A zero preferential tax rate does not remove the income from gross income or AGI. Keep the amount distinct from ordinary and qualified dividends to avoid double counting. [Official §852](https://www.govinfo.gov/link/uscode/26/852), [§61](https://www.govinfo.gov/content/pkg/USCODE-2024-title26/html/USCODE-2024-title26-subtitleA-chap1-subchapB-partI-sec61.htm), [IRS instructions](https://www.irs.gov/instructions/i1040gi).

Coverage checklist for the eventual resolved source units:

- (C)(i): written shareholder reporting; (ii)–(iv): excess reporting, proportional reduction, fiscal-year post-December exception, and all defined amounts including §855 distributions. The exception must protect pre-January dividends only when its stated conditions hold.
- (C)(v): increased reported amounts after a qualifying §860(e) determination remain subject to the subparagraph's limits. (C)(vi): account explicitly for the reference to (b)(8)'s late-year losses; do not treat pre-adjustment company gain as final when an election affects it.
- Establish the input contract for qualifying RIC/part-I applicability. External company net capital gain, adjusted reporting and election determinations may be separately computed inputs only with precise legal definitions and explicit responsibility for their upstream derivation.
- Defer company-level tax under (3)(A), undistributed-gain treatment and credits under (D), and unrelated loss-netting, preferential-rate and full-return calculations only by naming their source clauses and outputs. A narrow B/C encoding must still address the overriding classification in (E) when applicable; an explicit supported-profile exclusion must block a claim of complete shareholder treatment for that case.
- The 2025 IRS block can ground a separately scoped reporting rule, not a fabricated 2026 form. For the direct route, the source requires no capital losses, only box-2a distributions, no boxes 2b/2c/2d, and no QOF deferral. Nominee amounts belong to the actual owner. Failure of a reporting exception routes the amount elsewhere; it does not make the distribution exempt.

Companion cases must assign **every** declared local input, including false booleans. Pair ordinary qualifying reporting with absent/incorrect reporting; no excess with positive excess; fiscal-year post-December relief with its blocking conditions; qualifying determination with no qualifying determination; applicability with its exclusion. Demonstrate that short ownership of the fund does not negate (B)'s deemed long-term character. Pair direct-reporting eligibility with each applicable blocking fact if that reporting rule is in scope. Use verbatim proof excerpts from the **resolved ingested row**, not this memo or an oracle docstring.

The benchmark's `non_sch_d_capital_gains` input is treated as the already reportable shareholder amount. The households do not contain fund-level aggregate reporting, net gain, fiscal-year allocation or determination facts. Do not fabricate zero values for those corporate inputs to claim that these households test all of (C). Synthetic cases must test that definition independently.

**Worked case 1 — scenario_042, Wisconsin, single, age 79, year 2026.** Relevant facts: distribution **$3,753**; Social Security $29,580; taxable IRA $19,200; pension $4,886; interest $175; ordinary dividends $5,920; qualified dividends $928; farm loss $1,127.2940673828125. Baseline and sandbox both show zero separately entered long- and short-term sale gains and no investment-income election.

The independent §852/§61 contribution is **$3,753**, agreeing with the corrected inclusion; the omitted contribution of $0 is not supported. The additional AGI increase is larger because §86 changes taxable Social Security. Including the farm loss, other income before this distribution is $29,981.7059326171875. Provisional income becomes $48,524.7059326171875. Applying the single §86 upper-tier formula gives `min(0.85 × 29,580, 0.85 × (48,524.7059326171875 − 34,000) + 4,500) = 16,846.000042724609375`. AGI is therefore **$50,580.705975341796875**, or **$50,580.71**. The frozen AGI is $43,637.65234375; corrected AGI is $50,580.70703125. The small difference from exact arithmetic is floating-point precision. [Official §86](https://www.govinfo.gov/link/uscode/26/86).

The $3,753 plus $928 qualified dividends produces a $4,681 preferential base. Holding the benchmark's single-filer deduction treatment fixed, use the $16,100 standard deduction, $2,050 age addition, $6,000 senior deduction and 2026 ordinary brackets. Taxable income is $26,430.705975341796875, ordinary taxable income $21,749.705975341796875, and federal tax is `$1,240 + 12% × ($21,749.705975341796875 − $12,400)` = **$2,361.964717041015625**, matching corrected **$2,361.96** to cents. Rate/deduction amounts were checked against [Rev. Proc. 2025-32](https://www.irs.gov/pub/irs-drop/rp-25-32.pdf) §§4.01, 4.03 and 4.14; the senior deduction against [IRS 2026 guidance](https://www.irs.gov/newsroom/2026-filing-season-updates-and-resources-for-seniors). This is conditional independent arithmetic, not an Axiom execution. The assigned provisions do not themselves fix Wisconsin deductions, rates or the separate retirement election, so the Wisconsin total below remains a conditional downstream comparison.

**Worked case 2 — scenario_051, Louisiana, single, age 25, year 2026.** Wages $40,000; distribution **$180**; no separately entered sale gain/loss. The law-derived distribution inclusion is **$180**, so AGI is **$40,180**, matching corrected $40,180 rather than frozen $40,000. Federal tax remains $2,620 in both runs because the extra gain is in the zero-rate band; unchanged federal tax does not justify excluding the gain. The Louisiana state output increases by $5.40. The assigned federal provisions establish the $180 income correction; they do not alone establish Louisiana's full liability.

**Worked case 3 — scenario_091, Wisconsin, single, age 22, year 2026.** Wages $27,000; traditional 401(k) contribution $926.1599731445312; interest $4,806; ordinary dividends $208; qualified dividends $3,968; traditional IRA contribution $43.276798248291016; distribution **$1,170**. No separately entered sale gain/loss or investment-income election. Given the stated deductible retirement treatment, AGI from the facts is `27,000 − 926.1599731445312 + 4,806 + 208 + 3,968 + 1,170 − 43.276798248291016 = 36,182.563228607177784`, or **$36,182.56**. Frozen AGI is $35,012.5625; corrected AGI $36,182.5625. **The statute supports the corrected $1,170 inclusion**, not the omitted $0 contribution. The preferential base rises from $3,968 to $5,138; the federal output is unchanged. Wisconsin's final total again requires separate state law.

**Worked case 4 — synthetic (C) allocation and blocking pair.** A calendar-year RIC reports aggregate capital gain dividends $10,000 but has $8,000 net capital gain; the shareholder's reported amount is $1,000. Excess is $2,000, allocated share `$2,000 × $1,000 / $10,000 = $200`; qualifying capital gain dividend is **$800**. With net capital gain $10,000, the same shareholder amount qualifies in full: **$1,000**. For a noncalendar year with post-December reporting $4,000 and the same $2,000 excess, a $1,000 post-December dividend bears $500 excess and qualifies for **$500**, while an otherwise identical pre-January dividend bears zero excess and qualifies for **$1,000**. Reducing post-December reporting below $2,000 blocks that special allocation and restores the general proportional allocation. These are direct arithmetic applications of (C)(ii)–(iv), not household facts.

**Every moved benchmark output** from `sweep_moves.csv`, `fix=r04_capital_gain_distributions`:

| Household | Benchmark output | PE 1.755.4 frozen | Sandbox corrected | Independent adjudication |
|---|---|---:|---:|---|
| scenario_042 | Federal tax before refundable credits | 1,979.158325 | 2,361.964844 | Corrected direct inclusion $3,753 supported; federal calculation above gives **2,361.96**. |
| scenario_042 | State tax before refundable credits | 284.740906 | 414.204346 | Corrected inclusion supported; **neither full state total is established by §§852/61 alone**. Other Wisconsin provisions remain material. |
| scenario_051 | State tax before refundable credits | 814.950012 | 820.349976 | Corrected inclusion $180 supported; full state total needs Louisiana law. |
| scenario_091 | State tax before refundable credits | 843.661499 | 884.021851 | Corrected inclusion $1,170 supported; full state total needs Wisconsin law. |

Conditional checks explain the state propagation without upgrading it to independent full-return certification: Wisconsin's retained 30% capital-gain subtraction leaves $2,627.10 / $819 additional state income in 042 / 091; the retained 12% deduction taper and 4.4% marginal rate give increases **$129.463488 / $40.360320**, matching the sweep to cents. Louisiana's retained 3% rate gives **$5.40**. These state parameters are engine-context checks, not conclusions derived from the assigned federal provisions. Scenario 042 also has a separately audited Wisconsin retirement-election interaction, so the r04-only corrected state value must not be advertised as the uniquely lawful final return.

Household evidence: [fresh calculations and complete facts](../scratch/us-852-capgain/households/household_check.jsonl), [reproduction script](../scratch/us-852-capgain/households/household_check.py), [independent exact arithmetic](../scratch/us-852-capgain/households/independent_arithmetic.json), [four successful sweep comparisons](../scratch/us-852-capgain/households/reproduction_checks.json), and [source/command notes](../scratch/us-852-capgain/households/notes.md). The baseline/corrected script ran household-level calculations only, sequentially, with bytecode writes disabled; all four sweep rows matched to the CSV's six-decimal precision. No population simulation was run. The supplied fix, root-cause record, verification material and earlier coverage report were read as context, not substituted for the statutory reading.

## 7. Risks

- **Source resolution is the present blocker.** Issue [TheAxiomFoundation/.github#39](https://github.com/TheAxiomFoundation/.github/issues/39), read in this run, requires existing corpus provisions or official snapshots with URL/date/hash provenance. Do not encode from this report, broaden a release through `corpus_ref`, or edit the pin in a feature PR.
- **Source-unit completeness.** B alone requires a defined qualifying amount; C has excess-reporting, fiscal-year and determination branches. The proposed checklist retains those branches and names external computations and exclusions. A broad parent citation cannot silently drop corporate tax or undistributed gains. The workflow's complete-source-unit requirement is verified; the example failure artifact's additional `issues.json` findings were not downloaded, so their detailed contents remain briefing-only.
- **Input/proof discipline.** Household facts do not prove the fund-level prerequisites. Separate household inclusion checks from synthetic definition tests; assign every local input and ground every excerpt in the ingested row. The memo contains no RuleSpec or test YAML.
- **Closure/schema incompatibility.** The current loader rejects plural corpus paths, and the nearby capital-gains threshold file has an unsupported source-verification field. Avoid unneeded legacy imports, require eligible signatures for selected imports, and test the actual generated closure in the signed engine. Old local compile success is insufficient.
- **AGI composition.** §61's external aggregate is not wired to its enumerated-income output. A correct classification module alone does not establish end-to-end AGI or tax parity. Ensure future composition consumes the distribution exactly once and permits §86 feedback.
- **Timing and collisions.** As of the live checks, [#1384](https://github.com/TheAxiomFoundation/rulespec-us/pull/1384) is merged; [#1387](https://github.com/TheAxiomFoundation/rulespec-us/pull/1387) is open with successful strict run [35791296078](https://github.com/TheAxiomFoundation/rulespec-us/actions/runs/35791296078); [#1386](https://github.com/TheAxiomFoundation/rulespec-us/pull/1386) remains open and its inspected run was cancelled. [#1385](https://github.com/TheAxiomFoundation/rulespec-us/pull/1385) closed unmerged. No drift-stage or final activation/re-pin PR appeared among the open PRs examined. Coordinate the additional source-release pin with that serial chain rather than assuming its eventual result includes §852.
- **No target collision found, within the inspected scope.** The full open collections contained 21 rulespec-us and 15 axiom-encode PRs. Titles/bodies and specific searches found no §852/capital-gain-distribution work. The latest 30 targeted runs spanned September 21–23; today's three concerned Canada and none targeted this provision. Refresh immediately before dispatch. Encoder [#1675](https://github.com/TheAxiomFoundation/axiom-encode/pull/1675) concerns release-object size limits; current workflow enforces 16 MiB, but no size/publication blocker is asserted for the not-yet-created §852 release.
- **Limits of verification.** The current engine was inspected, not built or executed. Published release bytes/signatures and final 2026 Form 1040 instructions were not verified. No signed Axiom numerical result exists for this target. No oracle issue or other external write was made.

Read-only checks completed: fresh remote ref/PR/run queries; canonical normalized-source and release-scope inventories; immutable module/manifest/closure inspection; 22 existing-module compiles using the discovered older binary; current-engine schema inspection; three household baseline/corrected runs reproducing all four moved outputs; independent statutory and exact-arithmetic checks. Supporting workflow, helper, source and protected failure log are in [workflow notes](../scratch/us-852-capgain/workflow/notes.md).

Encoding regime retained verbatim for any subsequent lane brief:

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

```json
{
  "lane": "us-852-capgain",
  "verdict": "BLOCKED",
  "citation": "us/statute/26/852/b/3/B",
  "in_corpus": false,
  "in_pinned_release": false,
  "existing_modules": [
    "us/statutes/26/61.yaml",
    "us/statutes/26/62.yaml",
    "us/statutes/26/1222.yaml",
    "us/statutes/26/1/h.yaml",
    "us/policies/irs/rev-proc-2025-32/capital-gains.yaml",
    "us/statutes/26/1411.yaml"
  ],
  "blocking_imports": [],
  "dispatch_command": "",
  "prerequisites": [
    "Ingest official 26 USC 852(b)(3)(B), (C) and necessary context with retained URL/date/SHA provenance and canonical normalized citations.",
    "Publish a signed corpus release containing those rows; the planned Canada-union release is insufficient.",
    "Land a dedicated approved rulespec-us corpus pin coordinated with the serial re-pin chain.",
    "If Form 1040 routing is encoded, resolve its tax-year source contract and include the appropriate IRS source in the signed release.",
    "Finalize the B/C source-unit and fresh dependency strategy, check the actual closure in the current signed engine, refresh immutable refs at exact main, and obtain Max's approval for the resulting command."
  ]
}
```
