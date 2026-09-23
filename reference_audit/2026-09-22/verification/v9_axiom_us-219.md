# us-219 — Axiom signed-encoding preparation

## 1. Verdict

**READY — dispatch the source-bundle command below against the verified current main.** Max's approval is required before the orchestrator executes it. This lane did not dispatch, encode, author RuleSpec/test YAML, change external repositories, or commit.

The package adds a new whole-section `us:statutes/26/219` module and first signs the annual parameters in Notice 2025-67 page 4. It supplies the section 219 arithmetic needed for the ten benchmark households, with precisely identified external calculation/classification boundaries. It does **not** claim to independently derive every possible filing status, plan qualification, or upstream income component. In particular, legal surviving-spouse classification remains an explicit upstream dependency, rather than a fabricated local input.

**The statute supports the sandbox-corrected IRA deduction in all ten households.** Nine corrected return deductions are zero; scenario_064 retains the head's $108.19200134277344 and removes the dependent's $18.031999588012695. This adjudication concerns the IRA deduction; section 219 alone does not independently establish an entire federal or state tax liability.

No source-membership prerequisite requires waiting for the serial re-pin chain. Both needed source scopes are already in today's pinned release selector and in the proposed successor. The command is valid only while rulespec-us main remains `f43dec520dd392bc5333934f56dad7498363e704`, rechecked through the GitHub connector at **2026-09-23 02:33 UTC / September 22 ET**. The workflow requires an exact current main tip for `open_pr=true`. If orchestration waits for #1387, #1386, and the subsequent drift-stage/activation/re-pin, refresh the immutable refs and repeat the collision check; do not dispatch the stale command. Waiting is an operational sequencing choice, not a demonstrated dependency of this provision.

The required `git fetch` was attempted and denied at the external checkout's `.git/FETCH_HEAD`. The local `origin/main` SHA matched the independently read remote main. All repository inspection used immutable `git show`/`git ls-tree` snapshots or read-only GitHub GETs. The subfleet manifest names an external `-o` destination, `/Users/maxghenis/PolicyEngine/_wk/axenc-pb/report-us-219.md`; direct writes there are outside this lane's allowed workspace. The report and its dispatch attachments are supplied in this workspace for orchestration to collect.

## 2. Source

Official statutory locations: [OLRC current section 219](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section219&num=0&edition=prelim), [OLRC retained release-point XML archive](https://uscode.house.gov/download/releasepoints/us/pl/119/100/xml_usc26@119-100.zip), and the independently readable [GovInfo section 219 text](https://www.govinfo.gov/content/pkg/USCODE-2024-title26/html/USCODE-2024-title26-subtitleA-chap1-subchapB-partVII-sec219.htm). OLRC live HTML timed out/returned 403; the retained corpus XML and GovInfo text were read. The latter includes the 2022 catch-up-indexing amendment.

Official annual authority: [IRS Notice 2025-67, page 4](https://www.irs.gov/pub/irs-drop/n-25-67.pdf). Its 2026 IRA ceiling is $7,500, with $1,100 catch-up at age 50; own-active phase-outs are $81,000–$91,000 for single/HOH and $129,000–$149,000 for joint returns, spouse-only coverage is $242,000–$252,000, and married-separate coverage remains $0–$10,000 absent the living-apart exception.

Canonical corpus `origin/main`: **`942e138e7a8250c9814e774ac9b8e63008148106`**, verified locally and remotely.

| Source | Exact canonical citation | Tracked provision file and vintage |
|---|---|---|
| Whole statute, selected primary | `us/statute/26/219` | `data/corpus/provisions/us/statute/2026-07-13-recovery-r2026-07-15-self-contained-r2026-07-17-dedup.jsonl`; `source_as_of` and expression date `2026-07-13`; publication `Online@119-100`, source metadata created `2026-04-17` |
| Required statutory descendants | `us/statute/26/219/b/1`, `/b/5`, `/c`, `/f/1`, `/g` | All present in that same file, together with the rest of (a)–(g) and their paragraph records |
| Annual parameter source | `us/guidance/irs/notice-2025-67/page-4` | `data/corpus/provisions/us/guidance/2026-07-23-irs-notice-2025-67.jsonl`; `source_as_of=2025-11-13`, expression date `2026-01-01`, version `2026-07-23-irs-notice-2025-67` |

The statute's retained artifact is `data/corpus/sources/us/statute/2026-07-13-recovery-r2026-07-15-self-contained-r2026-07-17-dedup/official-documents/usc26-section-219.xml`, with adjacent `provenance/usc26-section-219.xml.json`. Its measured SHA-256 is `b11cd5cea06f2621c32c65274aac5ebb799c89ef0e1405be391e2c6f06f120df`, exactly matching provenance. Notice's retained artifact is `data/corpus/sources/us/guidance/2026-07-23-irs-notice-2025-67/official-documents/irs-notice-2025-67.pdf`.

**In corpus: yes. In pinned release: yes, verified through its tracked scope selector.** The rulespec-us toolchain pins `us-rulespec-2026-08-08-obbb-alien-snap`, content SHA-256 `0d69a0cdbe024fc2276f3c261c00402bb0a47488ac5f482cc20bd3404980adbc`. `manifests/releases/us-rulespec-2026-08-08-obbb-alien-snap.json` contains both exact source versions above. The successor `manifests/releases/us-rulespec-2026-08-23-canada-338-suspension-union.json` also contains both; the lane asserted these memberships. No ingest is needed.

Limitation: `axiom-locate release` found no materialized local release, and the public R2 release object was inaccessible through shell DNS and web. Membership is established from the canonical tracked selector, not a fresh verification of the public object's signature/content hash. The signed workflow itself retrieves and verifies/materializes that object before encoding (workflow lines 827–876).

## 3. Existing rulespec-us coverage

All claims below concern **`f43dec520dd392bc5333934f56dad7498363e704`**. The relevant primary modules are exactly:

| Module | Current coverage |
|---|---|
| `us/statutes/26/219/b.yaml` | Compensation minimum, age catch-up, statutory base figures, SEP/SIMPLE exclusions, and the separate 501(c)(18) limitation. Does not derive compensation/spousal capacity or apply annual indexing. |
| `us/statutes/26/219/g.yaml` | Participation categories, exception/applicability predicates, and a forwarded MAGI input. Monetary threshold selection and phase-out outputs are explicitly deferred. |
| `us/policies/irs/notice-2025-67/savers-credit.yaml` | Nine section 25B Saver's Credit parameters; no section 219 annual ceiling/phase-out parameters. |

There is no parent `219.yaml`, no (c)/(f) module, and no Notice `page-4.yaml`. Fresh parent/source destinations, companions, and canonical manifest destinations were checked absent.

The earlier compensation assessment needs correction: Axiom **already has** the minimum at the immediate input boundary. At [219/b line 200](https://github.com/TheAxiomFoundation/rulespec-us/blob/f43dec520dd392bc5333934f56dad7498363e704/us/statutes/26/219/b.yaml#L200):

```text
formula: min(deductible_amount_before_compensation_limit, max(0, compensation_includible_in_gross_income))
```

But lines 27–29 and 58–60 assign `formula: '5000'` and `formula: '1000'`, each effective from `'1990-01-01'`; lines 177–180 add the latter at age 50. Existing-module execution for 2026 returned maximum general deduction limits of **0, 3,000, 5,000, and 6,000** for `(age, compensation)` `(40,0)`, `(40,3000)`, `(40,10000)`, `(50,10000)`. Thus the stale-ceiling observation is confirmed. These are existing maximum-limit outputs, not complete IRA deduction computations.

At [219/g lines 15–39](https://github.com/TheAxiomFoundation/rulespec-us/blob/f43dec520dd392bc5333934f56dad7498363e704/us/statutes/26/219/g.yaml#L15), deferred outputs include:

```text
us:statutes/26/219/g#applicable_dollar_amount
us:statutes/26/219/g#dollar_limitation_after_subsection_reduction
us:statutes/26/219/g#limitation_reduction
us:statutes/26/219/g#limitation_reduction_before_rounding
us:statutes/26/219/g#phaseout_denominator
```

The recorded reason is:

> Generated rule treated a filing-status or marital-status legal classification as a local fact. This output is deferred until the upstream status source can be encoded or imported without inventing local tax-status component inputs.

Tests with phase-out names assert participation/applicability rather than dollar results. The new finding requires actual monetary assertions. The existing active-participant expression also globally excludes participation when a reserve/firefighter exception holds; new tests must preserve independently qualifying participation in another plan, as required by the statutory “solely because” limitation.

Evidence: `scratch/us-219/coverage/coverage-notes.md`, exact extracted existing module bytes, and saved compiled requests/results. No extracted RuleSpec bytes were authored or repaired.

## 4. Import closure

**Candidate `existing_signed_imports_json`: `[]`.** No relevant signed-v5 dependency is presently available. The two 219 modules have legacy `applied-rulespec/v1` HMAC manifests; the Saver's Credit module has v1/manual provenance. A repository-wide manifest search found exactly two v5 manifests, for unrelated Rev. Proc. 2025-32 page 15 and section 7/2015/f.

The intended new closure is:

```text
us:statutes/26/219
  -> us:policies/irs/notice-2025-67/page-4  [fresh signed source in this run]
```

The workflow signs the fresh source first and requires its direct import into the target. No existing module is in that proposed closure. Both new modules await generation and compilation; this lane cannot claim an execution result for nonexistent artifacts.

| Existing nearby module | Imports | Actual local load check | Current signed-runtime significance |
|---|---|---|---|
| 219/b | None | Compiled; 4 derived outputs; four 2026 execution cases passed | Not a v5 import candidate; current pinned-engine load not independently run |
| 219/g | None | Compiled; 7 derived outputs | Not a v5 import candidate; current pinned-engine load not independently run |
| Notice savers-credit | None | Compiled with located older binary | Declares removed plural `corpus_citation_paths`; unsafe for current signed runtime and irrelevant to IRA values |

`axiom-locate engine` selected `/Users/maxghenis/TheAxiomFoundation/_tariff-parity/axiom-rules-engine/target/release/axiom-rules-engine`, binary SHA-256 `674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7`; its checkout is at `ffd8213271947b0189a9dd61a055c1e0e78908a0`. It accepts the removed plural field, so its successful checks are explicitly **not** proof of compatibility with the current signed runtime.

The current-runtime rejection is evidenced by the actual log of [run 35789753522](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/35789753522): an automatically selected `us:statutes/42/416/l` import caused `declares removed plural corpus_citation_paths`. That run also specified `existing_signed_imports_json=[]`: an empty explicit list does not disable automatic repo-augmented imports. Therefore the finding explicitly excludes broken/legacy closures. Neither current 219 module reaches 26/32. The proposed closure has **no known blocking import**; the known 26/32 → legacy EIC closure must not be added automatically.

## 5. Dispatch inputs

Inspected workflow/helper revision: **`5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9`**, [targeted signed workflow](https://github.com/TheAxiomFoundation/axiom-encode/blob/5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9/.github/workflows/targeted-signed-reencode.yml). The required `--ref main` is the workflow's protected dispatch branch; it is not an immutable workflow selector. Recheck that workflow revision if main changes.

| Input identity | Verified origin |
|---|---|
| `rulespec_ref=f43dec520dd392bc5333934f56dad7498363e704` | Local `origin/main` and remote branch GET; includes merged #1384 |
| `corpus_ref=942e138e7a8250c9814e774ac9b8e63008148106` | Canonical corpus `origin/main` and remote main GET |
| `rules_engine_ref=af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca` | Today's rulespec-us `.axiom/workflow-toolchain.toml`; the same ref successfully checked out/built in run 35789753522 |
| `citation=us/statute/26/219` | Exact resolved corpus parent record |
| `replace_rulespec_path=` | Empty intentionally: new parent, not replacement of (b) or (g) |
| `source_bundle_json=["us/guidance/irs/notice-2025-67/page-4"]` | Existing canonical source, absent canonical module destination |
| `existing_signed_imports_json=[]` | Fresh source supplied atomically; no suitable existing v5 module |
| `review_finding` | Complete file `scratch/us-219/review-finding.txt`, SHA-256 `aefa0a37f8033656147c4a058448f2d6e5c51959acb4fffed76d56a45624d7ac` |

Run from this assigned workspace so the findings attachment resolves. **This is a prepared command, not an executed command.** All 25 workflow inputs are explicitly supplied, including empty optional values. `gh workflow run --help` confirmed `-F key=@file` reads the file's contents.

```sh
gh workflow run targeted-signed-reencode.yml \
  -R TheAxiomFoundation/axiom-encode --ref main \
  -f citation=us/statute/26/219 \
  -f country=us \
  -f rulespec_ref=f43dec520dd392bc5333934f56dad7498363e704 \
  -f pr_base_branch=main \
  -f corpus_ref=942e138e7a8250c9814e774ac9b8e63008148106 \
  -f rules_engine_ref=af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca \
  -F review_finding=@scratch/us-219/review-finding.txt \
  -f repair_run_id= \
  -f 'source_bundle_json=["us/guidance/irs/notice-2025-67/page-4"]' \
  -f 'existing_signed_imports_json=[]' \
  -f replace_rulespec_path= \
  -f replace_legacy_rulespec_path= \
  -f legacy_exact_dependent_rulespec_path= \
  -f second_legacy_exact_dependent_rulespec_path= \
  -f 'legacy_retained_successor_rulespec_paths_json=[]' \
  -f dependent_citation= \
  -f dependent_review_finding= \
  -f second_dependent_citation= \
  -f second_dependent_review_finding= \
  -f open_pr=true \
  -f queue_id= \
  -f queue_item_id= \
  -f queue_manifest_sha256= \
  -f queue_item_generation_sha256= \
  -f queue_dispatcher_run_id=
```

Verified constraints: full lowercase 40-character refs; corpus/engine main ancestry; exact current rulespec main when opening a PR; canonical same-jurisdiction source citations; fresh source/target destinations absent; existing imports expressed as file paths and verified v5 if used. The source bundle executes before the parent (workflow 1927–1937, 1970–1976) and enforces direct imports (1357–1360, 1664–1677, 1737–1739). Source lanes receive an empty review finding; this matters for the Notice-page risk below.

The encoding regime for any downstream lane remains verbatim:

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

For rulespec-us specifically, use only the protected signed workflow: its job is in `production-signing`, and the encode step invokes `/opt/axiom-verification/axiom-encode encode --backend openai`. No local encode is authorized. [Binding agent rules, issue #39](https://github.com/TheAxiomFoundation/.github/issues/39) were read and retained in scratch.

## 6. Review finding text

**The exact `review_finding` input is the attached [review-finding.txt](/Users/maxghenis/.subfleet/worktrees/20260922-222028-axpb-us-219/scratch/us-219/review-finding.txt).** It contains the complete prose specification, four case families, all ten household adjudications, conservative MAGI bounds, and all 16 affected output rows. The following is the reviewable substance.

Cover the complete parent source (a)–(g), not only the two benchmark triggers: qualifying contributions; compensation and indexed dollar minima; lower-earning spousal capacity; all compensation inclusions/exclusions, including the special section 1402(c)(6) service rule in (f)(1); per-person treatment; complete active-participant phase-out with its $10 rounding, positive $200 floor and zero endpoint; all plan categories and exceptions; SEP/SIMPLE/501(c)(18); rollover/inherited/endowment restrictions; timely prior-year payments; excess carryforwards and closed-year reductions; election cross-reference; and repealed paragraphs. Import the new annual Notice outputs. Do not hardcode ungrounded Notice amounts under a statutory proof or carry forward unindexed base amounts.

Precisely defer only external determinations: section 401(c)(2) earned income, section 3401(h)(2) qualification, referenced plan/account qualification, section 415(c)(3) compensation, section 4973 excess history, general income computations under sections 86/469 and the specified disregards, actual-return legal eligibility, account/election administration, and surviving-spouse classification through the complete section 2(a) dependency chain. Keep section 219 arithmetic and its explicit blocking effects runnable on established underlying amounts/facts. Do not defer the monetary phase-out, compensation minimum, or 2026 ceiling.

Current encoder source prohibits local numeric/string `filing_status` and legal-status aliases: `cli.py:55930` invokes that hard apply check. Its `US_TAX_PACK` prompt expressly permits source-backed facts about whether a joint/separate return was actually made. The finding uses that factual boundary, distinguishes it from filing eligibility, and prohibits renaming a classification to evade the guard. It specifically requires a precise unresolved survivor-selection contract rather than silently applying the single threshold. This is conditional statutory arithmetic, not universal upstream tax-status adjudication.

Require paired positive/blocking tests for each exception, including reserve 90/91 days, firefighter $1,800/more, and an excepted plan plus a separately qualifying plan; 457(b)-only/other-plan; own/spouse-only/no participation; all-year apart/any cohabitation; valid contribution/rollover/inherited/life-insurance; qualifying compensation/pension/deferred; spouse/nonspouse; timely/late payment; and carryforward/no carryforward. Every local `#input` must be assigned, including false ones. Proof excerpts must be verbatim, singular-path anchored. No new failure has a waiver exit.

The deduction derivation is independent of the sandbox docstrings: section (a) supplies qualified contributions; (b)(1) supplies the lesser of dollar amount and compensation; (c) only extends capacity to a lower-earning joint spouse; (f)(1) excludes retirement receipts; and (g) reduces the dollar ceiling to zero at the relevant upper endpoint. For r02, actual modeled positive 401(k) allocations establish the represented qualifying-plan activity; they are not a universal proxy for participation. [IRS coverage guidance](https://www.irs.gov/retirement-plans/are-you-covered-by-an-employers-retirement-plan) confirms the allocation interpretation. Desired deferrals alone are not independent real-world evidence of completed allocations; this is the explicit benchmark-fixture interpretation.

| Household | Relevant facts | Baseline IRA deduction | Corrected IRA deduction | Independent §219 deduction and adjudication |
|---|---|---:|---:|---|
| scenario_003 (TX, joint) | Head age 64, spouse 61; both wages and every represented SE source zero. Head requests traditional $1,117.9840087890625 and Roth $1,734.0159912109375; receipts are investment/retirement income. | $1,117.9840087890625 | $0 | $0. Both compensation amounts are zero, so §219(c) supplies no spousal capacity. Supports corrected deduction. Desired 401(k) inputs do not change the compensation result. |
| scenario_064 (WI, joint) | Head age 48 has wages $97,295, pretax 401(k) $2,315.39990234375, taxable wages $94,979.6015625, net represented farm/partnership SE sources −$2,800; head traditional IRA $108.19200134277344. Disabled dependent age 27 has no wages/SE earnings and traditional IRA request $18.031999588012695. | $126.22400093078613 (head $108.19200134277344 + dependent $18.031999588012695) | $108.19200134277344 | Head $108.19200134277344; dependent $0 on parents' return. Dependent has no compensation and is not a joint spouse; the head's compensation easily covers their own contribution. Joint income is below the active-contributor starting threshold. Supports corrected deduction. |
| scenario_085 (PA, single) | Age 67; no wages/SE earnings; Social Security, pensions, distributions and interest only. Traditional request $0.3967039883136749; Roth $0.6152960062026978. | $0.3967039883136749 | $0 | $0. None of the represented retirement/investment receipts supplies compensation. Supports corrected deduction. The sub-dollar contribution is still subject to the compensation limit. |
| scenario_005 (CA, joint) | Ages 35/33, wages $180,000/$250,000; actual modeled traditional 401(k) $20,825 each (requests $23,154 each), Roth deferrals positive; traditional IRA $1,081.9200439453125 each. Joint §219 MAGI $538,928.375. | $2,163.840087890625 | $0 | $0 for each spouse. Each contributor is active and joint MAGI exceeds $149,000. Supports corrected deduction. |
| scenario_049 (NH, joint) | Ages 53/52; head wages $0/no IRA request; spouse wages $253,000, traditional 401(k) $15,436 and Roth 401(k) $2,724; spouse traditional IRA $721.280029296875. Joint §219 MAGI $247,385. | $721.280029296875 | $0 | $0. The contributor is the active spouse, so the $149,000 upper endpoint applies. The higher spouse-only-coverage threshold does not apply to that contributor. Supports corrected deduction. |
| scenario_052 (TX, joint) | Ages 59/55; head wages $500,000, traditional/Roth 401(k) $926.1599731445312/$163.44000244140625, traditional IRA $43.276798248291016; spouse wages $0/no IRA request. Joint §219 MAGI $504,821.84375. | $43.276798248291016 | $0 | $0. Active contributing head exceeds joint $149,000 endpoint. Supports corrected deduction. |
| scenario_082 (NY, HOH) | Age 23, wages $100,195; traditional/Roth 401(k) $181.3730010986328/$32.00699996948242; traditional IRA $8.475040435791016. §219 MAGI $117,593.625. | $8.475040435791016 | $0 | $0. Active HOH exceeds $91,000 endpoint. Supports corrected deduction. |
| scenario_099 (CA, joint) | Ages 42/41, wages $85,000/$80,000; each traditional/Roth 401(k) $1,543.5999755859375/$272.3999938964844; each traditional IRA $72.12799835205078. | $144.25599670410156 | $0 | $0 each. Taxable wages alone are about $161,912.80; even subtracting $3,000 capital loss and $337.50 requested educator expense leaves $158,575.30, above $149,000. Both contributors active. Supports corrected deduction. |
| scenario_110 (OH, single) | Age 51, wages $100,000; traditional/Roth 401(k) $4,244.89990234375/$749.0999755859375; traditional IRA $198.3520050048828; substantial additional investment income. | $198.3520050048828 | $0 | $0. Taxable wages alone are $95,755.10, above $91,000; no other represented above-line deduction reduces that below the endpoint. Active contributor. Supports corrected deduction. |
| scenario_120 (CT, single) | Age 76, wages $165,597; traditional/Roth 401(k) $617.4400024414062/$108.95999908447266; traditional IRA $28.851200103759766; additional pension/SS income. | $28.851200103759766 | $0 | $0. Taxable wages approximately $164,979.56 remain far above $91,000 even allowing the full represented $2,446.588134765625 farm-rent loss; active contributor. The source has no age-70½ bar: §219(d)(1) is repealed. Supports corrected deduction. |

The conservative MAGI arguments deliberately do not depend on adjudicating unrelated positive-income treatments. The lower bounds use modeled taxable wages minus every represented non-IRA/non-disregarded above-line deduction, leaving out all other positive income. All seven bounds independently exceed their phase-out endpoints:

| Scenario | Conservative MAGI lower bound | Sandbox §219 MAGI | Complete-phase-out endpoint |
|---|---:|---:|---:|
| 005 | $385,350 | $538,928.375 | $149,000 |
| 049 | $237,564 | $247,385 | $149,000 |
| 052 | $496,073.84375 | $504,821.84375 | $149,000 |
| 082 | $97,013.625 | $117,593.625 | $91,000 |
| 099 | $158,575.296875 | $159,729.296875 | $149,000 |
| 110 | $95,755.1015625 | $163,620 | $91,000 |
| 120 | $162,532.97436523438 | $232,663.96875 | $91,000 |

All gross/ALD components are retained in `intermediates.json`. None of the IRA requests approaches the old or new statutory dollar ceiling, and all seven r02 cases are entirely phased out, so changing the base/catch-up figures cannot change these results.

**Observed downstream outputs from the complete sweep**

F = `federal_income_tax_before_refundable_credits`; S = `state_income_tax_before_refundable_credits`. The statute supports the corrected IRA treatment in each row. These are phase-only/compensation-only sweep totals, not claims that all other policy components are independently correct.

| Scenario | Output | Frozen | Sandbox corrected | Delta |
|---|---|---:|---:|---:|
| 003 | F | 22,154.699219 | 22,400.654297 | 245.955078 |
| 064 | F | 4,439.289551 | 4,441.455078 | 2.165527 |
| 064 | S | 4,605.997070 | 4,607.142090 | 1.145020 |
| 085 | F | 2,322.760010 | 2,322.848633 | 0.088623 |
| 005 | F | 106,505.898438 | 107,198.335938 | 692.437500 |
| 005 | S | 41,051.511719 | 41,276.824219 | 225.312500 |
| 049 | F | 30,543.908203 | 30,702.589844 | 158.681641 |
| 052 | F | 104,211.406250 | 104,225.257812 | 13.851562 |
| 082 | F | 9,563.052734 | 9,564.916992 | 1.864258 |
| 082 | S | 5,598.552246 | 5,599.143555 | 0.591309 |
| 099 | F | 10,679.750000 | 10,711.484375 | 31.734375 |
| 099 | S | 4,493.743164 | 4,505.339844 | 11.596680 |
| 110 | F | 23,897.443359 | 23,941.082031 | 43.638672 |
| 110 | S | 4,057.472168 | 4,062.927002 | 5.454834 |
| 120 | F | 40,021.816406 | 40,028.320312 | 6.503906 |
| 120 | S | 11,917.183594 | 11,919.057617 | 1.874023 |

Scenario_085 F and scenario_082 S are below the sweep's $1 cutoff but are included because the assignment requires every moved household/output.

Four worked-case families beyond the affected households:

1. **2026 dollar and compensation limits:** qualifying traditional contributions $9,000, compensation $20,000, no active plan for taxpayer/spouse: age 49 allows $7,500; age 50 allows $8,600. With compensation $600, the deduction is $600 at either age. A dependent's personal deduction never enters the parent's return.
2. **Spousal compensation:** joint lower earner compensation $0; higher earner compensation $8,000 and valid deductible+nondeductible+Roth contributions totaling $2,000; neither active: lower-earner qualifying contribution $7,500 allows $6,000. Change to separate filing and the deduction is $0; a dependent relationship also cannot activate §219(c).
3. **Rounding, floor and endpoint:** single active contributor, under 50, compensation/qualifying contribution at least $7,500. MAGI $86,001 yields raw reduction $3,750.75, rounded down to $3,750, deduction $3,750; MAGI $90,999 yields $200 due to the positive-limit floor; MAGI $91,000 yields $0. If contribution is only $80 at MAGI $90,999, deduction remains $80, not $200. Compensation $1,000 at MAGI $86,001 allows $1,000, proving the phase-out reduces the dollar ceiling, not the compensation ceiling.
4. **Spouse-only coverage and living apart:** under-50 nonactive joint contributor with active spouse, qualifying contribution/compensation $7,500, MAGI $247,000 → $3,750; if neither spouse active → $7,500. Separately filing active contributor with MAGI $85,000: lived apart all year → $4,500 using the single range; lived together any time → $0 using the MFS range.

The federal/state totals in the table are **sweep observations**, not independently derived total-tax amounts. The independent statutory answer is the IRA deduction column. Accordingly, every household supports the corrected IRA treatment; neither set of whole-tax totals is fully adjudicated from section 219 alone. The distinction prevents overstating the evidence while providing every moved benchmark output.

## 7. Risks

- **Actual-return facts versus legal classifiers.** The new encoder must honor the current input rules. A local enum is rejected even though an older local encoder had a repair path. A source-backed actual filing event is allowed; a renamed legal status is not. Survivor status remains a named external dependency. Full raw-household, universal filing-status coverage needs subsequent signed upstream work.
- **Automatic legacy imports.** An empty explicit imports list does not prevent auto-selection, as the observed failed run demonstrates. The finding excludes legacy 219 modules, the irrelevant plural-metadata Saver's Credit module, and broken closures including 26/32. The signed run must compile its actual generated closure; this preparation cannot certify future imports.
- **Complete-source-unit coverage.** Parent 219 includes more than the two benchmark triggers. The finding enumerates all branches and exact external deferrals, plus paired tests. For fresh Notice page 4, the source lane receives no parent review finding. That page begins in the middle of section 25B's HOH paragraph and ends in the middle of a section 408A paragraph. The source encoder must encode fully supported amounts and precisely defer incomplete boundary clauses. This residual source-lane rejection risk cannot be eliminated by the parent finding; no rejection-free run is promised without running it.
- **Annual grounding and numerical boundaries.** Keep Notice proofs on the Notice path. Test age 49/50, exact thresholds, $10 reduction rounding, $200 positive floor, and actual contributions below $200. Do not apply phase-out fractions to compensation or contributions. Do not equate represented IRA contributions with automatically deductible amounts.
- **Source snapshot/engine limitations.** Public release-object verification could not be repeated here; tracked membership and retained source hashes were checked. The located binary is older than the selected signed-runtime engine. Its compilation evidence is narrowly labeled. The failure artifact's `issues.json` was not downloaded because shell networking was unavailable; only the actual GitHub job log rejection is asserted as independently read.
- **Serial-chain collisions.** #1384 is merged; [#1387 activation](https://github.com/TheAxiomFoundation/rulespec-us/pull/1387) and [#1386 workflow pin](https://github.com/TheAxiomFoundation/rulespec-us/pull/1386) remain open at `500d9df58be4e17f8572e51f665a28241b039823` and `a9dd1fb7985ccfdaf9f98548edde94ad48cd227c`. #1386 specifies ordering after activation. The measurement-only #1385 drift probe was closed; the later drift/activation/re-pin remains separate orchestration work. Neither pin file, workflow pin, CODEOWNERS nor waiver ledger is part of this feature package.
- **Same-provision collision search.** Exact open-PR searches for `26/219` and `2025-67` in both repositories found none; all 102 open rulespec-us PR metadata records were read. The latest 30 targeted signed runs and 100 recent workflow-dispatch runs, including September 22 UTC and the September 23 UTC portion of September 22 ET, contained no matching target. This is a point-in-time observation; repeat immediately before dispatch.

**Changes/tests:** only this Markdown report and lane scratch evidence were written. Existing changes were preserved. No commit was made because this lane's specific read-only rule prohibits commits. Three existing modules compiled with the qualified older binary; four existing section 219(b) evaluations passed. Sequential household-only baseline/reform calculations verified all ten corrected IRA deductions and all seven conservative MAGI bounds; six state tax pairs reproduced the sweep within $0.000001. Ten federal tax rows were extracted from the sweep rather than recalculated under their benchmark label. Both release-selector membership checks and the retained statutory XML provenance hash passed. No population/microsimulation run, local encode, or new RuleSpec/test module was produced.

Machine-readable evidence and complete logs are under `scratch/us-219/households/`, `scratch/us-219/coverage/`, and `scratch/us-219/workflow/`. The review finding is a prose instruction file, not RuleSpec.

```json
{
  "lane": "us-219",
  "verdict": "READY",
  "citation": "us/statute/26/219",
  "in_corpus": true,
  "in_pinned_release": true,
  "existing_modules": [
    "us/statutes/26/219/b.yaml",
    "us/statutes/26/219/g.yaml",
    "us/policies/irs/notice-2025-67/savers-credit.yaml"
  ],
  "blocking_imports": [],
  "dispatch_command": "gh workflow run targeted-signed-reencode.yml \\\n  -R TheAxiomFoundation/axiom-encode --ref main \\\n  -f citation=us/statute/26/219 \\\n  -f country=us \\\n  -f rulespec_ref=f43dec520dd392bc5333934f56dad7498363e704 \\\n  -f pr_base_branch=main \\\n  -f corpus_ref=942e138e7a8250c9814e774ac9b8e63008148106 \\\n  -f rules_engine_ref=af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca \\\n  -F review_finding=@scratch/us-219/review-finding.txt \\\n  -f repair_run_id= \\\n  -f 'source_bundle_json=[\"us/guidance/irs/notice-2025-67/page-4\"]' \\\n  -f 'existing_signed_imports_json=[]' \\\n  -f replace_rulespec_path= \\\n  -f replace_legacy_rulespec_path= \\\n  -f legacy_exact_dependent_rulespec_path= \\\n  -f second_legacy_exact_dependent_rulespec_path= \\\n  -f 'legacy_retained_successor_rulespec_paths_json=[]' \\\n  -f dependent_citation= \\\n  -f dependent_review_finding= \\\n  -f second_dependent_citation= \\\n  -f second_dependent_review_finding= \\\n  -f open_pr=true \\\n  -f queue_id= \\\n  -f queue_item_id= \\\n  -f queue_manifest_sha256= \\\n  -f queue_item_generation_sha256= \\\n  -f queue_dispatcher_run_id=",
  "prerequisites": [
    "Max approval before any signed run; orchestrator alone dispatches.",
    "At dispatch, rulespec_ref must equal current main; reverify and refresh immutable refs after any serial-chain merge."
  ],
  "scope": "Section 219 economic rules with signed 2026 Notice parameters; explicit external income, plan-qualification, return-validity, and survivor-classification boundaries.",
  "source_bundle_json": [
    "us/guidance/irs/notice-2025-67/page-4"
  ],
  "review_finding_sha256": "aefa0a37f8033656147c4a058448f2d6e5c51959acb4fffed76d56a45624d7ac"
}
```
