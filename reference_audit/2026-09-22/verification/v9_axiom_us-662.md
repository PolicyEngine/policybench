# us-662 — Axiom encoding preparation

## 1. Verdict

**BLOCKED.** `us/statute/26/662/a` has no normalized provision in the inspected canonical corpus `origin/main`. Its official text is retained inside a full-title source archive, but the signed encoder resolves normalized provision records from the pinned release; it does not encode directly from that archive. An official-source extraction/ingest, signed release publication, and separately approved rulespec-us re-pin are required before dispatch.

The named serial chain ending at `us-rulespec-2026-08-23-canada-338-suspension-union` is **insufficient by itself**: that release recipe also lacks §662. Do not dispatch against the inspected main. No passing, immutable future command can be specified before the prerequisite commits exist.

Independent household adjudication supports including **$25,950** for scenario_039 and **$6,322.94140625** for scenario_110, treating the supplied amounts as already classified taxable beneficiary estate income. Zero estate QBI follows from the benchmark's explicit unlisted-status=false convention, not from a statutory rule that estate income is always nonbusiness. The households lack the distribution, DNI, and character facts needed to compute a raw §662 amount. Full federal/state liabilities therefore remain conditional, as detailed below.

Read-only boundary: only this workspace's `scratch/us-662/` was written. No encoding, authored RuleSpec/test YAML, commits, branches, dispatches, PRs, or external comments. The task-specific no-commit rule controls over the generic commit instruction.

## 2. Source

Canonical corpus snapshot inspected: **`942e138e7a8250c9814e774ac9b8e63008148106`**. Rulespec snapshot: **`f43dec520dd392bc5333934f56dad7498363e704`**. These are verified local `origin/main` objects, not confirmed live remote tips. The requested rulespec fetch failed with `cannot open '.git/FETCH_HEAD': Operation not permitted`; GitHub CLI reads failed to connect.

| Provision | Canonical citation and corpus status | Vintage and release membership |
|---|---|---|
| §662(a) | Intended citation `us/statute/26/662/a`; neither it nor parent `us/statute/26/662` exists as a normalized record | Not in the pinned release or named Aug23 successor recipe |
| §61(a)(14) | **`us/statute/26/61/a/14`** exists, as do parent `/61` and `/61/a` | Recovery scope dated **2026-07-13**, present in both release recipes |
| §199A(c)(3)(A)(ii) | **`us/statute/26/199A/c/3`** is the stored source unit containing (A)(ii); parent `/199A` and `/199A/c` also exist. Do not mistake an unverified deeper path for a stored record | Same 2026-07-13 recovery scope, present in both release recipes |

The supporting normalized file is `data/corpus/provisions/us/statute/2026-07-13-recovery-r2026-07-15-self-contained-r2026-07-17-dedup.jsonl`. Its §61/§199A records and provenance were read from canonical `origin/main`; excerpts are saved in [supporting-corpus-provisions.json](supporting-corpus-provisions.json). The retained source excerpts come from OLRC archive `xml_usc26@119-100.zip`; their provenance records supply archive/member/excerpt SHA-256 values.

Official §662 text was independently read at [GovInfo §662](https://www.govinfo.gov/content/pkg/USCODE-2024-title26/html/USCODE-2024-title26-subtitleA-chap1-subchapJ-partI-subpartC-sec662.htm), and in the newer retained OLRC release **Online@119-103**. Related official locations are [§61](https://www.govinfo.gov/link/uscode/26/61), [current §199A](https://uscode.house.gov/view.xhtml?req=%28title%3A26+section%3A199a+edition%3Aprelim%29), and [26 CFR 1.199A-6(d)](https://www.govinfo.gov/content/pkg/CFR-2025-title26-vol4/pdf/CFR-2025-title26-vol4-sec1-199A-6.pdf).

**Required ingest:** extract §662, including (a)(1)–(2), (b), and (c), from the official OLRC **USLM XML** archive [Title 26, release 119-103](https://uscode.house.gov/download/releasepoints/us/pl/119/103/xml_usc26@119-103.zip), retain source URL/date/hash provenance, and create resolvable provision records through the authorized corpus ingestion process. The source archive already exists on canonical main at:

`data/corpus/sources/us/statute/2026-09-13-tax-statute-closure-31-title-26/olrc/xml_usc26@119-103.zip`

Its recorded source-as-of is **2026-09-02**; the ingest manifest is dated **2026-09-13**. This lane verified archive SHA-256 **`285b9862808f26055c3eed16c2aca1d8de1fae96b581f44a55cfedb907a46eff`** and extracted member `usc26.xml` SHA-256 **`ab999da948658a2265f762abfedd72413a3f7828d34659ff27ed8240fcd956e4`**. The actual §662 text is retained in [official-usc26-662.xml](official-usc26-662.xml). Presence of the raw source does **not** mean the citation is currently resolvable.

Exact `citation_path` searches, allowing JSON whitespace and checking all tracked federal statute provision files plus the legacy provision directory, returned no §662 record. A broad substring search instead found a §6621 cross-reference; that was excluded. The corpus-tree inventory and empty exact-match output are retained here.

The rulespec pin read from `.axiom/toolchain.toml` is `us-rulespec-2026-08-08-obbb-alien-snap`, content SHA-256 **`0d69a0cdbe024fc2276f3c261c00402bb0a47488ac5f482cc20bd3404980adbc`**. [Pinned](pinned-release.json) and [successor](chain-release.json) release recipes were read from canonical corpus main. `axiom-locate release` did not locate a materialized signed object, so this lane does not claim fresh signature verification of the published release object.

Per the missing-source instruction, executable dispatch preparation stops here for §662. The remaining sections preserve requested coverage evidence and independent review material for the orchestrator; they do not authorize or represent a runnable encode.

## 3. Existing rulespec-us coverage

At rulespec SHA `f43dec520dd392bc5333934f56dad7498363e704`, no primary module exists at §662, §661, §663, or §643. The directly relevant existing modules are:

| Module | What the inspected code encodes | Relation to this task |
|---|---|---|
| `us/statutes/26/61.yaml` | General gross-income definition and enumerated positive income sum | Includes the estate/trust category; does not compute beneficiary distributions/DNI |
| `us/statutes/26/62.yaml` | AGI arithmetic consuming a supplied gross-income input and deduction inputs; no imports | Does not construct estate/trust beneficiary income |
| `us/statutes/26/199A.yaml` | QBI deduction arithmetic using resolved QBI as an input | Explicitly defers QBI composition and trade/business classification |
| `us/statutes/26/67/e.yaml` | The estate or trust entity's own AGI, subtracting resolved deduction inputs from its gross income | Does not calculate a beneficiary's income; read, not compiled |

The §61 enumerated formula contains the literal line:

```text
+ max(0, income_from_an_interest_in_an_estate_or_trust)
```

Its separate `gross_income` formula is:

```text
max(
    0,
    all_income_from_whatever_source_derived
    - amounts_otherwise_provided_excluded_from_gross_income_under_this_subtitle
)
```

Thus the category is present, but the module does not connect the enumerated sum to the aggregate input. Two existing-module engine queries demonstrate the distinction: estate income 7,800 with aggregate input zero gives enumerated income **7,800** and gross income **0**; supplying aggregate income 7,800 gives **7,800** for both. This is a composition boundary, not evidence of a categorical omission in §61. It also does not make §662 **NOT-NEEDED**.

The §199A deferral says:

```text
Subsection (c) defines qualified business income, qualified items, and
exclusions. This module consumes resolved qualified business income as
an input while encoding the deduction arithmetic; QBI composition is
deferred.
```

The following deferral similarly covers subsection (d)'s trade/business classification. Neither this module nor §61 establishes a universal true or false estate-QBI classification. Exact copied modules, manifests, compile logs, and query evidence are in this scratch directory; [coverage-analysis.md](coverage-analysis.md) supplies line references and command details.

## 4. Import closure

Candidate future **`existing_signed_imports_json=[]`**. A standalone §662(a) unit can consume explicit, resolved DNI/applicability/character facts; no existing module import is necessary to calculate its two distribution tiers. This choice must be reviewed after the missing corpus unit is ingested. It must not be used to hide unresolved legal boundary facts.

The nearby existing closures were actually compiled:

| Existing closure | Local engine result | Direct signed-workflow eligibility |
|---|---|---|
| §61 | Compiles; two outputs, including the estate traces above | Manifest is `applied-rulespec/v1`, not v5 |
| §62 (no imports; gross income is a local input) | Compiles | Manifest v1 |
| §199A → §1(h) → IRS Rev. Proc. 2025-32 capital-gains module | Compiles; §199A closure has 34 outputs | All inspected manifests v1 |

The workflow's direct-import validator requires tracked same-jurisdiction primary **file paths** with signed-v5 manifests. It rejects these v1 modules as supplied direct imports even though the local engine compiles them. Therefore they are not candidates for `existing_signed_imports_json`.

**Compile-blocking imports in the proposed empty closure: none.** The inspected nearby closures do not reach §32 or its earned-income-credit import, and do not contain the removed plural citation field. The brief's §32 failure is not a blocker for this standalone target. This lane did not independently compile §32.

The local engine was located with `axiom-locate engine`; binary SHA-256 is **`674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7`**. These are local load checks of existing bytes, not a claim that the binary exactly matches the prospective signed-run engine commit.

## 5. Dispatch inputs

**No dispatch command is supplied: there is no valid verified command for an absent corpus unit.** Freezing today's rulespec SHA would also fail after the required re-pin: the workflow requires `open_pr=true` to use the exact then-current main tip. A command with placeholder refs or a known-invalid current pin would not meet the requested dispatch standard.

Verified local immutable objects, to preserve the inspection provenance:

| Input/component | SHA | Source |
|---|---|---|
| `rulespec_ref` inspected | `f43dec520dd392bc5333934f56dad7498363e704` | rulespec-us local `origin/main`, merge #1384 |
| `corpus_ref` inspected | `942e138e7a8250c9814e774ac9b8e63008148106` | canonical axiom-corpus local `origin/main` |
| `rules_engine_ref` candidate only | `6e709eb1ca7ea686263293d932c759d9dee48a4a` | canonical engine local `origin/main`; not the identified local binary build |
| Workflow inspected | `5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9` | axiom-encode local `origin/main` |

After the prerequisites, refresh and verify immutable refs and exact canonical citation. The eventual workflow is `targeted-signed-reencode.yml`, repository `TheAxiomFoundation/axiom-encode`, workflow ref `main`; candidate values are `country=us`, `pr_base_branch=main`, `citation=us/statute/26/662/a` **only if ingested at that path**, empty `replace_rulespec_path` for a still-new module, `existing_signed_imports_json=[]`, `source_bundle_json=[]`, `open_pr=true`, and the reviewed finding below. Max's approval remains required for every signed run. No new approval is requested by this read-only lane.

Verified mechanisms: [workflow lines 827–875](workflow-evidence/targeted-signed-reencode.yml) materialize the toolchain-pinned signed release; [resolver lines 551–580 and 937–976](workflow-evidence/corpus_resolver.py) restrict source lookup to that release's provision artifacts. [Base validation lines 267–332](workflow-evidence/prepare_signed_backfill_impl.py) enforce exact main for PR creation; direct imports at lines 1368–1502 require v5. [workflow-analysis.md](workflow-analysis.md) records the remaining input validations and protected signing path.

## 6. Review finding text

**Prepared finding for review after ingest, not currently dispatchable:**

Encode the entire resolved §662(a) source unit. Cover the §661 applicability gate, currently required distributions whether or not paid, the first-tier proportional DNI limitation computed without the §642(c) deduction, the rule for income-or-corpus obligations to the extent satisfied from current income, other proper distributions, and their residual-DNI proportional limitation. Guard zero denominators and exhausted residual DNI. Do not replace this source unit with a single unconditional addition of an estate-income input.

Precisely defer external determinations to explicit local inputs: §643 DNI construction, §642(c) charitable deductions and allocation, §661 entity classification, §663 exclusions/timing/separate shares, and §662(b) character classification. Supply separate DNI inputs where the statutory computations differ. §662(a)'s reference to (b) means a gross cash distribution cannot silently become taxable ordinary income. A deferred or unresolved classification must remain identifiable; it must not masquerade as a legally determined zero. If the resolved citation is the whole §662 rather than (a), cover or precisely defer (b)'s character proportions, governing-instrument exception and deduction allocations, and (c)'s taxable-year alignment.

Treat the §199A issue as a separate classification boundary. Taxable-income inclusion under §199A(c)(3)(A)(ii) is necessary but not sufficient: clause (i), the qualified-business definition, and (B)'s exclusions still apply. Preserve carried-out character for a separate signed QBI-composition unit. Do not encode an automatic estate-QBI=true or estate-QBI=false rule, and do not label a positive-only current amount as a complete treatment of qualified-business losses.

Require paired positive/blocking cases for: entity/applicability eligibility; mandatory income despite no cash payment; binding versus nonbinding first-tier cap; positive versus exhausted residual DNI; zero other distributions; income-or-corpus obligation satisfied from income versus solely corpus; resolved §663 exclusion versus eligible distribution; taxable versus tax-exempt character; and qualified taxable business items versus nonbusiness or excluded items at any QBI interface. For any implemented (b)/(c) branches, also pair governing-instrument special allocation and mismatched taxable years with their controls. Every companion case must explicitly assign every local input, including false facts. Proof excerpts must come verbatim from the eventual resolved provision, not from this prose or the sandbox docstring.

**Case 1 — scenario_039 (VA).** Single, age 61, no spouse/children; 2026 estate income **25,950**, self-employment loss **6,260.029296875**, Social Security **36,105**, taxable IRA distributions **26,800**, taxable pension **2,030**, wages zero. Estate-QBI status is unlisted. Disability and surviving-spouse flags are listed; filing status is expressly single.

| Measure | PolicyEngine 1.755.4 | Assigned sandbox correction | Independent reading |
|---|---:|---:|---|
| Estate contribution to gross income | 0 | 25,950 | **25,950** under the classified taxable-beneficiary-income input contract |
| Estate contribution to QBI before other-item netting | 25,950 | 0 | **0 under the benchmark convention**; actual business character unknown |
| Federal tax before refundable credits | 1,345.510498 | 8,596.028320 | Corrected provision-level treatment supported; full amount not independently established by the assigned provisions |
| VA tax before refundable credits | 514.498413 | 1,975.798218 | Same inclusion conclusion; complete VA liability not independently derived here |

The positive taxable-beneficiary amount belongs in gross income under §61(a)(14), with §662(a) supplying its upstream distribution calculation and (b) preserving character. Therefore the statute supports the **corrected inclusion**, not zero inclusion of established taxable beneficiary income. Under the benchmark's expressly supplied unlisted-status=false convention, estate QBI is zero. Neither exact final liability is certified as an unconditional statutory result: missing DNI/character facts and additional federal/state provisions prevent that conclusion.

Fresh two-household reproduction observes taxable Social Security increasing from **10,129.0986328125** to **30,689.25**, AGI from **32,699.068359375** to **79,209.21875**, and QBI deduction from **3,319.813720703125** to zero. These explain why the federal movement exceeds a simple marginal-rate multiplication of 25,950; they are simulator observations, not a separate signed Axiom adjudication.

**Case 2 — scenario_110 (OH).** Single, age 51, no spouse/children; estate income **6,322.94140625**, wages **100,000**, long-term gains **30,851.765625**, short-term gains **18**, qualified dividends **10,032**, other dividends **5,662.11767578125**, taxable interest **21,301**, tax-exempt interest **954**. Listed desired traditional contributions are 401(k) **4,244.89990234375** and IRA **198.3520050048828**. Estate-QBI status is unlisted. Full facts are preserved in [households.json](households.json).

| Measure | PolicyEngine 1.755.4 | Assigned sandbox correction | Independent reading |
|---|---:|---:|---|
| Estate contribution to gross income | 0 | 6,322.94140625 | **6,322.94140625** under the same taxable-income input contract |
| Estate contribution to QBI | 6,322.94140625 | 0 | **0 under the benchmark convention**; actual business character unknown |
| Federal tax before refundable credits | 23,897.443359 | 25,700.166016 | Corrected provision-level treatment supported; full amount not independently established |
| OH tax before refundable credits | 4,057.472168 | 4,231.353027 | Inclusion supported; state result additionally depends on Ohio business-income classification |

Again the statute supports the **corrected inclusion**. A false federal QBI qualification input alone does not establish Ohio nonbusiness classification. The supplied verification report conditions Ohio's corrected amount on that additional interpretation, and the audit records a separate IRA-related change for this household. Neither frozen nor single-reform final tax is certified here as the complete legally correct return. Observed AGI is **163,421.640625 → 169,744.578125** and QBI deduction **1,264.5882568359375 → 0**.

**Why these are conditional findings:** neither household provides estate DNI, aggregate/current distribution requirements, all-beneficiary amounts, governing-instrument allocations, or income classes. A raw §662 calculation is therefore underdetermined. The independently derived dollar inclusions use the supplied `estate_income` as an already classified beneficiary-income amount. QBI status from economic facts alone is **unknown** in both cases. `policybench/prompts.py:19–21`, read in this run, expressly supplies the additional convention that unlisted status inputs are false. That benchmark convention produces the zero-QBI test fact; it is not a universal rule of law.

**Case 3 — current-distribution cap.** Domestic nongrantor complex trust, same tax year, ordinary taxable nonbusiness income, no charity deduction, §663 exclusion, or separate shares. A's current entitlement is 30,000; all beneficiaries' current entitlements total 60,000; first-tier DNI is 40,000; other distributions zero; cash paid to A zero. First-tier inclusion = **40,000 × 30,000 / 60,000 = 20,000**. Mandatory entitlement is included despite unpaid cash. Paired nonbinding-cap control with DNI 80,000 gives **30,000**. These amounts follow directly from the first-tier ratio in the retained official §662 text.

**Case 4 — other distributions and residual DNI.** Same classifications. A's current entitlement is 10,000, total current entitlements 40,000; A's other distribution is 30,000, total other distributions 120,000; DNI is 100,000 with no charity deduction. First tier **10,000**; residual DNI **60,000**; second tier **60,000 × 30,000 / 120,000 = 15,000**; total **25,000**. Nonbinding-cap control with DNI 200,000 gives **40,000**. Exhausted-residual control with DNI 40,000 gives **10,000**. All are ordinary taxable nonbusiness amounts by explicit facts, not by inference from estate origin.

The legal reading above uses the independently read [official §662 text](official-usc26-662.txt), [§61 text](official-usc26-61.txt), and [§199A text](official-usc26-199A.txt), extracted from the retained current OLRC archive. [household-analysis.md](household-analysis.md) provides the complete household evidence and qualifications.

## 7. Risks

| Risk | Preparation response |
|---|---|
| Missing active source | Block dispatch; ingest normalized §662 records, publish an authenticated successor release, and land a dedicated pin update |
| Treating the announced chain as sufficient | Both inspected release recipes omit §662; recheck the actual eventual release scope |
| Stale base or unverifiable immutable refs | The workflow requires exact main for `open_pr=true`; refresh after prerequisites, not before |
| Import signature rejection | Candidate import list is empty; nearby compiling modules have v1 manifests and cannot be admitted as direct v5 imports |
| Incomplete source-unit coverage | Finding covers both tiers and cap branches; names external calculations and their input contracts precisely |
| Missing exception tests or invented proof text | Finding requires paired positive/blocking cases and all local inputs; proof text must be extracted from resolved corpus text after ingest |
| Overclaiming household adjudication | Separate taxable-income input interpretation, benchmark QBI convention, actual unknown economic classification, and observed full-tax outputs |
| Confusing local compile with signed-run success | Existing bytes were compiled locally; no new encoding, v5 attestation verification, or complete target CI run occurred |

Binding [Axiom issue #39](https://github.com/TheAxiomFoundation/.github/issues/39) was read successfully through the web fallback after the requested `gh issue view` failed. Its restrictions on provenance, protected pins, proof excerpts, complete input assignments, and oracle reporting were followed. The page was cached; its historical tool pins are not asserted to be today's pins. This package makes no upstream oracle finding.

Collision searches were **attempted but could not be completed**: GitHub CLI reads of open rulespec-us/axiom-encode PRs matching 662/61/199A and the latest 30 targeted runs failed to connect. Web fallback for #1387 and #1386 returned cache misses. No absence-of-collisions claim is made. Current statuses of #1387/#1386, subsequent drift/activation PRs, today's runs, and the example failure artifact remain unverified. Local refs confirm inspection of the #1384 merge and cached chain branches only. Before any approval request, the orchestrator must repeat the live citation/run/PR checks and inspect actual failure history.

**Checks completed:** all eight baseline/corrected assertions for the four moved outputs passed within one cent using the exact assigned sandbox variant under policyengine-us **1.755.4**, for these two households only. Five nearby existing-module compile checks passed; two §61 queries demonstrated the composition boundary. No population run was performed. An optional nonexistent `traditional_ira_deduction` lookup is recorded in the reproduction artifact; it did not affect the assertions. No signed encoding was possible, so there is no Axiom §662 monetary test result.

```json
{
  "lane": "us-662",
  "verdict": "BLOCKED",
  "citation": "us/statute/26/662/a",
  "in_corpus": false,
  "in_pinned_release": false,
  "existing_modules": [
    "us/statutes/26/61.yaml",
    "us/statutes/26/62.yaml",
    "us/statutes/26/199A.yaml",
    "us/statutes/26/67/e.yaml"
  ],
  "blocking_imports": [],
  "dispatch_command": "",
  "prerequisites": [
    "Ingest normalized, resolvable section 662 source units from the retained official OLRC XML with URL/date/SHA provenance; confirm the final canonical subsection citation.",
    "Publish an authenticated corpus release containing section 662 and land its dedicated approved rulespec-us pin update; the named Aug23 chain alone is insufficient.",
    "Recheck current remote refs, open PRs and targeted signed runs; obtain the exact rulespec main SHA plus compatible immutable corpus and engine refs after prerequisites land.",
    "Review the explicit DNI, income-character and benchmark-QBI input contracts, then obtain Max's approval for the concrete signed-run command."
  ]
}
```
