# ca-mpp-snap: existing Axiom artifact adjudication

## 1. Verdict

**NOT-NEEDED for a new numerical encoding of the three assigned rounding rules.** California net-income rounding is already encoded at **MPP 63-503.31**, the parent of the assignment's .311. The existing .31 rule returns **$877** for scenario_023; feeding that output into existing 7 USC 2017(a) returns **$34/month**. Existing federal statute and regulation modules both return the FY2026 small-household minimum of **$24**.

This verdict concerns the provision encodings. The broader California benefit composition does not import .31 or .311 and is **not certified here as a complete CalFresh calculator**. It also has current-engine schema blockers described below. No duplicate atomic encode is warranted; integration and legacy-provenance migration are separate work.

Read rulespec-us `origin/main` **f43dec520dd392bc5333934f56dad7498363e704**, independently confirmed as live GitHub main. The requested fetch failed with `cannot open '.git/FETCH_HEAD': Operation not permitted`; the connector supplied read-only remote verification. Standalone rulespec-us-ca local `origin/main` is **321ed395ac076b580f20af351eb476056e018779**. Its .31/.311 files are byte-identical to the tested monorepo files. No commit, push, branch, external finding, workflow dispatch, local encode, or new RuleSpec/test YAML was made. Scratch includes byte-for-byte existing-source copies and JSON execution requests.

## 2. Source

Official source: [CDSS Food Stamp Manual, chapter 63-503, fsman06.docx](https://www.cdss.ca.gov/Portals/9/Regs/Man/Fsman/fsman06.docx?ver=wrx9nKY4BHRH9SGFqVVMkg%3D%3D), linked by the [current official manual index](https://www.cdss.ca.gov/inforesources/letters-regulations/legislation-and-regulations/calworks-calfresh-regulations/calfresh-regulations). The DOCX retained in corpus was read directly, extracted into `official-fsman06.txt`, and its SHA-256 verified:

`eb0eb8a58a8371c8f56e80a3bf49d561e01eb0ffcbae2567a2475d7abb8f4e75`.

The controlling rounding provision is **`us-ca/regulation/mpp/63-503.31`**. The ordinary net-income arithmetic is **`us-ca/regulation/mpp/63-503.311`**. These are state regulations, not statutes. Both exist in canonical axiom-corpus `origin/main` **942e138e7a8250c9814e774ac9b8e63008148106**:

- Provision file: `data/corpus/provisions/us-ca/regulation/2026-07-13-recovery.jsonl`, records 527–528.
- Retained source: `data/corpus/sources/us-ca/regulation/2026-07-13-recovery/official-documents/us-ca-mpp-63-503`.
- Provenance: sibling `provenance/us-ca-mpp-63-503.json`, fetched `2026-07-13T23:53:00Z`; provision `source_as_of=2026-07-13`.
- Printed vintage: .31 appears on page 283, Manual Letter FS-04-07 effective July 1, 2004; .311 appears on page 284, FS-06-04 effective November 1, 2006. These dates differ from the 2026 snapshot date.

MPP .31 retains cents through the calculation, then rounds the final net income down below fifty cents and up at fifty cents. CDSS independently reiterates that reading in [ACIN I-25-11, April 29, 2011](https://cdss.ca.gov/lettersnotices/entres/getinfo/acin/2011/I-25_11.pdf). This derivation uses the official regulation itself, not the sandbox docstring or a ParaRegs summary.

**In pinned release: yes, by verified release selection.** rulespec-us pins `us-rulespec-2026-08-08-obbb-alien-snap`, content SHA-256 `0d69a0cdbe024fc2276f3c261c00402bb0a47488ac5f482cc20bd3404980adbc`. Its tracked selector includes `us-ca/regulation` version `2026-07-13-recovery`; the two records also exist at the selector's historical corpus commit **1f87488a9fa7def07988cafc6de254811a5b1d28**. No ingest or release expansion is needed. The release artifact was not locally materialized, so this is selector-and-historical-content verification, not fresh cryptographic verification of its distributed bytes. See `dispatch/report.md`.

## 3. Existing rulespec-us coverage

`git ls-files` found .31 and .311 in standalone rulespec-us-ca; `git ls-tree origin/main` confirmed both under rulespec-us/us-ca. Relevant immutable source copies are under `rulespec-us/` and `federal/rulespec-us/` in this scratch directory.

| Module | What was read and tested |
|---|---|
| `us-ca/regulations/mpp/63-503/31.yaml` | Correct nearest-dollar net-income rule, line 125: `floor(net_monthly_income_calculated_with_exact_dollars_and_cents_including_shelter_and_medical_costs + net_monthly_income_round_up_cent_floor)`. Parameter is `0.50` at line 77. No imports. Four rounding cases pass. |
| `us-ca/regulations/mpp/63-503/311.yaml` | Ordinary income/deduction arithmetic. Line 294: `if net_monthly_income_determination_steps_apply: max(0, monthly_income_after_homeless_shelter_deduction - excess_shelter_deduction) else: 0`. It deliberately has no final rounding; .31 supplies that separate rule. Household arithmetic and elderly/disabled blocking case pass. |
| `us-ca/regulations/mpp/63-503/312.yaml` | Neighboring elderly/disabled route, including medical and uncapped excess-shelter deductions. Final formula is `if household_elderly_or_disabled_net_monthly_income_calculation_applies: max(0, monthly_income_after_standard_dependent_care_medical_and_homeless_deductions - excess_shelter_cost_for_elderly_or_disabled_household) else: 0`. Read, not executed; scenario_023 is outside this USDA classification. |
| `us-ca/regulations/mpp/63-503/321.yaml` | Gross/net eligibility comparisons, including monthly and quarterly reporting. Does not implement net-income rounding. Read, not executed. |
| `us-ca/regulations/mpp/63-503/324.yaml` | Table-allotment interface: `max(0, coupon_allotment_table_monthly_allotment_for_household_size_and_net_income)`. It accepts an allotment boundary value; it does not compute .31. |
| `us-ca/policies/cdss/snap/fy-2026-benefit-calculation.yaml` | Composition for eligibility, deductions and federal allotments; imports .324 but neither .31 nor .311. Its 18-module closure contains no .31 rounding rule. Successful local compilation does not establish a complete household result or current-runtime compatibility. |
| `us/statutes/7/2017/a.yaml` | Line 128: `floor(max(0, snap_maximum_allotment - snap_household_food_contribution))`. Lines 153–156 apply `floor((snap_one_person_thrifty_food_plan_cost * snap_minimum_allotment_rate) + 0.5)` to household sizes ≤2, otherwise zero. |
| `us/regulations/7-cfr/273/10.yaml` | Line 425 uses the same nearest-dollar minimum. Line 445 uses either `ceil(snap_net_monthly_income * snap_allotment_net_income_reduction_rate)` before subtraction or `floor(snap_maximum_allotment - (snap_net_monthly_income * snap_allotment_net_income_reduction_rate))`. Line 465 separates initial-month issuance/minimum rules. |

Both federal modules return `floor(298 × .08 + .5) = 24`, consistent with the [official USC §2017(a)](https://www.govinfo.gov/content/pkg/USCODE-2024-title7/pdf/USCODE-2024-title7-chap51-sec2017.pdf), [CFR §273.10(e)(2)(ii)](https://www.govinfo.gov/content/pkg/CFR-2025-title7-vol4/pdf/CFR-2025-title7-vol4-sec273-10.pdf), and [USDA FY2026 minimum table](https://fns-prod.azureedge.us/sites/default/files/resource-files/snap-fy26MinimumAllotments.pdf). The 2024 USC and 2025 CFR publication vintages were actually read; live preliminary USC/eCFR retrieval failed. No later statutory change is inferred from that failure.

These atomic formulas do not contain the three questioned numerical behaviors. This is an Axiom coverage assessment and requested comparator adjudication, not an external-oracle finding.

## 4. Import closure

No new target is proposed; candidate `existing_signed_imports_json` is **`[]`**. MPP .31 and .311 have no imports and both compile and execute locally. Neither depends on 26/32 or its EIC policy import.

The federal closure union comprises `us:statutes/7/2017/a`, `us:statutes/7/2014/e/6/A`, `us:statutes/7/2014/e/2`, `us:statutes/7/2014/e/2/B`, `us:policies/usda/snap/fy-2026-cola/maximum-allotments`, `us:regulations/7-cfr/273/10`, `us:policies/usda/snap/fy-2026-cola/deductions`, and `us:statutes/7/2012/j`. Every module loads in the two successful local compiles, and none declares plural citation paths. Full sources, hashes and closure are retained in `federal/summary.json`.

The separate California composition closure is enumerated in `composition_closure.json` (18 modules). All load together in the **located local binary**, yielding 114 outputs. However, five modules declare removed `corpus_citation_paths`:

- `us-ca:policies/cdss/snap/fy-2026-benefit-calculation`
- `us-ca:policies/cdss/snap/modified-categorical-eligibility`
- `us:policies/usda/snap/fy-2026-cola/income-eligibility-standards`
- `us:regulations/7-cfr/273/7`
- `us:regulations/7-cfr/273/24`

At verified current engine main **6e709eb1ca7ea686263293d932c759d9dee48a4a**, `src/rulespec.rs:819–823` rejects that key recursively, and line 1086 applies the validator to loaded imports. Thus these are **code-derived current-engine blockers**, not a reproduced failure of the older local executable. We did not build a new engine. Local binary SHA-256 is `674ca6e70afdccb59c3d6847933bc24b4590105e49db54790f2dcd0bdbbe32d7`; its exact build commit is unverified.

Existing apply provenance is not signed-v5 eligibility: .31's manifest is `axiom-encode/applied-rulespec/v1`, generated May 14, 2026, and its source hash matches `1af19100ca58a0983e81cb624f7361e535400324670318d10ce757d1d8e9785e`. The two federal manifests are also v1. The inspected workflow import validator requires v5 manifests, tracked atomic YAML, and the target's primary jurisdiction; a California target cannot simply list federal `us/` leaves in `existing_signed_imports_json`. Local numerical validity does not establish signed-import admissibility.

## 5. Dispatch inputs

**Not applicable: no encode command or workflow dispatch is proposed.** Providing a runnable duplicate-encode command would contradict the tested NOT-NEEDED verdict. `dispatch_command` is empty below.

For traceability, the workflow and validation code were read at encoder main **5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9**; source snapshot is corpus **942e138e7a8250c9814e774ac9b8e63008148106**; rulespec main and current engine identities are recorded above. These are observed immutable identities, not an approved dependency set or a future dispatch recipe. The workflow requires full SHA inputs, origin/main ancestry for corpus/engine, and current main for `open_pr=true`; saved refs must be refreshed before any future approved run.

The serial re-pin chain is **not needed to make these provisions available**: they are already in the pinned release. #1387 activation and #1386 workflow pin remain open. A separate integration/signing repair must coordinate with that chain, resolve the named schema/provenance blockers and recheck main. This lane neither changes pins nor requests approval for a signed run.

## 6. Review finding text and worked adjudication

No `review_finding` is submitted because no new atom is needed. The following review text is suitable for the orchestrator's disposition and any later, separately scoped integration work:

> Preserve and use the existing MPP 63-503.31 final-net-income rounding rule. Resolve the official .31 source unit, not .311 alone: .311 computes the ordinary net amount, while .31 carries cents through the calculation and rounds the final net amount half up. Route the resulting net income into federal allotment computation before rounding the contribution up or the allotment down. Preserve the nearest-dollar 8% federal minimum. Defer eligibility, quarterly averaging, individual income exclusions, deduction amounts, proration and FY2027 parameter determination to their separately identified provisions; these boundary checks do not adjudicate those inputs. Include paired .49/.50 and whole-dollar tests, ordinary versus elderly/disabled .311 applicability, homeless deduction versus excess-shelter treatment if that arithmetic is changed, and regular versus initial-month minimum cases if the benefit composition is changed. Assign all local input facts, including false. A .311 re-encode must not claim complete-source-unit coverage while silently dropping its QR/PB or exception branches. Use verbatim proof excerpts from each resolved unit and existing supervised artifacts; do not hand-author a new atomic module.

**Complete California reference inventory.** Reading every SNAP row in `reference_outputs.csv` and matching `scenarios.csv` gives:

| California household | Frozen annual SNAP |
|---|---:|
| scenario_005 | $0 |
| scenario_022 | $0 |
| **scenario_023** | **$461.3397216796875** |
| scenario_031 | $0 |
| scenario_099 | $0 |

Thus **scenario_023 is the only California household with nonzero reference SNAP and the only r27 moved household**. Selection and facts are retained in `households/selection.json`; audit sweep comparison and fresh household execution are in `households/`.

**Worked case 1 — scenario_023.** One person, age 28; annual employment $17,442.646484375 and taxable 403(b) distributions $8,000; rent $2,000/month; utility allowance $663/month. For the tested boundary, USDA elderly/disabled classification is false (the separate generic disability fact is true), so .311 applies. Earned-income deduction is 20%; standard deduction $209; shelter deduction capped at $744; dependent-care, child-support, medical and homeless deductions zero. Eligibility is held at the benchmark's true value; this is not an independent eligibility determination.

Using exact annual facts, `17442.646484375/12 × .8 + 8000/12 − 209 − 744 = 876.509765625`, or $876.51 to cents. MPP .31 yields **$877**, not $876. Then `ceil(.30 × 877)=264`; `298−264=34`. Equivalently `floor(298−263.10)=34`. The $24 minimum does not bind. The existing Axiom .31 result fed into the existing federal module returns **$34**, recorded in `joined-ca-federal.response.json`.

| Quantity, January–September FY2026 | PolicyEngine 1.755.4 | Isolated r27 sandbox | Independent legal calculation / Axiom |
|---|---:|---:|---:|
| Raw net-income calculation | $876.5096435546875 | Same before new rounding | About $876.51 |
| Net used for 30% contribution | $876 after floor | $877 | **$877** |
| Monthly benefit | $35.199981689453125 | $34.899993896484375 | **$34.00** after federal whole-dollar rule |
| Federal one/two-person minimum | $23.84000015258789 | Unchanged by r27 | **$24.00** |

**Adjudication:** MPP supports the corrected r27 **net income**, not the original floored net. For the final benefit, the governing rules support **neither $35.20 nor isolated-r27 $34.90**: the complete calculation is $34. The combined r26+r27 calculation therefore matches the law at this FY2026 boundary; r28's minimum correction does not bind for this household.

The frozen annual $461.3397216796875 is reproduced exactly and combines nine $35.199981689453125 months with three $48.179962158203125 months under original FY2027 extrapolated parameters. Do not divide it by 12 to infer a FY2026 month. The audit's FY2026-held annual baseline is $422.3997802734375 and isolated-r27 comparator $418.7999267578125; the complete corrected FY2026-held calculation is **$408**. That $408 is the benchmark parameter-holding convention, **not a claim about actual October–December 2026 entitlement**. January–September under the tested law totals $306; actual fourth-quarter amounts require FY2027 parameters.

Existing .311 with extracted decimal intermediates returns $876.5097351074219 rather than PE's $876.5096435546875 because the latter uses floating-point calculation/summation. Both round to $877. All 13 local .311 inputs were supplied, including false exception flags; the zero care-cap placeholder cannot affect zero care expenses.

**Worked case 2 — half-dollar boundary.** Exact calculated net $123.49 → .31 output **$123**; $123.50 → **$124**; exactly $123 → **$123**. All three JSON cases executed successfully. Changing the .311 elderly/disabled fact to true makes that ordinary-route output zero; that is an applicability sentinel, not a finding that an elderly household has no income.

**Worked case 3 — minimum binds.** Eligible one-person regular-month household, FY2026 one-person maximum $298 and net $971: ordinary benefit `floor(298−.30×971)=6`; minimum `floor(.08×298+.5)=24`; issued regular-month benefit **$24**. Both federal modules execute to $24; both permitted contribution/allotment rounding elections agree. The statute supports the rounded comparator, not $23.84. Initial-month rules are a separate branch.

**Executed checks:** 784 federal derived assertions pass (9 existing companion cases, 15 additional JSON boundary requests, and 171 saved household-month replays for all 19 households from the earlier parity check). Four California rounding assertions, two .311 arithmetic/applicability assertions and the joined $34 benefit assertion pass. The 171 replays use the earlier saved PE boundary facts; scenario_023's fresh facts are independently reproduced here. These are provision-boundary checks, not population runs or full eligibility validation. Reproduction commands:

```sh
ruby scratch/ca-mpp-snap/check_ca.rb
PYTHONDONTWRITEBYTECODE=1 /Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/.venv-pe1755/bin/python scratch/ca-mpp-snap/federal/check.py
```

The household reproduction command and exact original/held/fixed values are retained in `households/evidence.md`. No PolicyBench source file was modified.

## 7. Risks

- **Wrong source unit:** dispatching .311 to add rounding misses controlling .31 and duplicates existing coverage. The source correction and tested module prevent that mistake.
- **Composition coverage:** existing atomic correctness does not imply the broad CalFresh composition applies .31. Its missing import/connection and five removed-field modules require separate integration/provenance work.
- **Runtime mismatch:** older local engine accepts plural metadata; current source rejects it. Current-engine behavior here is code-derived, not executed. No general current signed-CI pass is claimed.
- **Legacy manifests:** correct existing output is not proof of signed-v5 import admissibility. Do not use the v1 CA/federal artifacts as if the workflow import validator accepted them.
- **Complete-source-unit and grounding:** future edits must cover or precisely defer all source branches and retain paired exception tests and verbatim path-anchored proof text. No waiver, pin, workflow or CODEOWNERS change is proposed. Binding [issue #39](https://github.com/TheAxiomFoundation/.github/issues/39) was read and saved as `issue39.md`.
- **Collisions:** searched all 102 open rulespec-us and 24 open encoder PR titles/bodies, plus 82 encoder runs created September 22 UTC (16 targeted signed runs). No direct MPP .31/.311 collision found. Related [rulespec-us #1363](https://github.com/TheAxiomFoundation/rulespec-us/pull/1363) changes the federal SNAP modules, parameter leaves and California categorical-eligibility dependency; it does not change .31/.311. Its proposed repairs are not on main. This was not a changed-file audit of every open PR.
- **Annual interpretation:** the isolated r27 sandbox alone still produces cents; the federal rule must also apply. The FY2026-held annual comparator cannot validate actual FY2027 benefits. Generic disability and USDA disability were kept distinct; eligibility remains an input boundary.

```json
{"lane":"ca-mpp-snap","verdict":"NOT-NEEDED","citation":"us-ca/regulation/mpp/63-503.31","in_corpus":true,"in_pinned_release":true,"existing_modules":["us-ca/regulations/mpp/63-503/31.yaml","us-ca/regulations/mpp/63-503/311.yaml","us/statutes/7/2017/a.yaml","us/regulations/7-cfr/273/10.yaml"],"blocking_imports":["us-ca:policies/cdss/snap/fy-2026-benefit-calculation","us-ca:policies/cdss/snap/modified-categorical-eligibility","us:policies/usda/snap/fy-2026-cola/income-eligibility-standards","us:regulations/7-cfr/273/7","us:regulations/7-cfr/273/24"],"dispatch_command":"","prerequisites":["No new encode is needed for the tested rounding atoms.","For separate CalFresh integration: connect existing MPP .31, repair current-engine plural-field blockers, establish admissible signed provenance, coordinate with the serial re-pin chain, and reverify live main before any Max-approved signed dispatch."]}
```
