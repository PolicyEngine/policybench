# ny-606e — Axiom encoding preparation

Prepared 2026-09-23. Read-only lane; no RuleSpec, module test YAML, commits, repository edits, or signed runs were produced. All new files are under `scratch/ny-606e/`.

## 1. Verdict

**BLOCKED.** The statute supports scenario_104's corrected **$0**, subject to the explicit assumption that the supplied rent needs no service-charge adjustment. A passing signed dispatch cannot yet be specified.

The whole of section 606 exists in the corpus and is selected by the current release, but the proposed narrow citation **`us-ny/statute/TAX/606/e/7/D` does not resolve**. The retained July body has literal backslash-n sequences instead of structural line breaks. The newer September body also lacks structural line breaks. The inspected encoder rejects the narrow target with `CorpusSourceSliceError`. A source repair/structured child ingestion or an approved resolver correction must make the exact source unit resolve before dispatch. Form IT-214 and its instructions also need official ingestion if their operational rules are included in the encoding.

The named serial re-pin chain is **insufficient by itself**: both the August 8 and planned August 23 release selectors select the same July NY statute scope. Source admission/resolution must be addressed, followed by fresh immutable refs and live PR/run checks. No claim of READY-AFTER merely upon #1387/#1386 merging is justified.

Snapshot limitation: the prescribed `git fetch -q origin` failed because `.git/FETCH_HEAD` is outside this lane's writable roots. GitHub CLI reads failed to connect. Thus “origin/main” below means the local remote-tracking snapshot, not independently refreshed remote state:

| Repository | Snapshot read |
|---|---|
| rulespec-us | `f43dec520dd392bc5333934f56dad7498363e704` — merge #1384 |
| axiom-corpus | `942e138e7a8250c9814e774ac9b8e63008148106` |
| axiom-encode | `5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9` |

## 2. Source

Official sources read: [N.Y. Tax Law §606](https://www.nysenate.gov/legislation/laws/TAX/606), displayed revision September 4, 2026; [2025 IT-214](https://www.tax.ny.gov/pdf/current_forms/it/it214_fill_in.pdf); [2025 IT-214-I](https://www.tax.ny.gov/pdf/current_forms/it/it214i.pdf); and [S3009C, Part RR, printed pages 134–141](https://legislation.nysenate.gov/pdf/bills/2025/S3009C). The [enacted bill page](https://www.nysenate.gov/legislation/bills/2025/S3009/amendment/C) records Chapter 59, signed May 9, 2025. A 2026 IT-214 was not verified. Part RR changes surrounding eligibility, definitions, and amounts from 2025; its §7 amends (e)(7)(A), **not the $450 text of (e)(7)(D)**.

The exact **stored** canonical citation is **`us-ny/statute/TAX/606`**. The proposed child citation is `us-ny/statute/TAX/606/e/7/D`; no exact child row exists. Distinguish retained legal text from an admissible resolved source unit:

| Source unit | In inspected corpus main | Selected by pinned release |
|---|---|---|
| Whole §606, July vintage | Yes | Yes, by tracked release selector |
| Exact §606(e)(7)(D) child | No stored row; parent slicing fails | No usable resolved child established |
| IT-214 / IT-214-I | No retained source unit found | No |

Pinned provision file: `data/corpus/provisions/us-ny/statute/2026-07-06-ny-tax-article22-core-us-ny-sections-tax-601-tax-606-tax-614-tax-615-tax-616.jsonl`. Its `source_as_of` and `expression_date` are `2026-07-06`, with `metadata.active_date=2026-06-05`. Format: `new-york-openleg-json`; official acquisition URL: `https://legislation.nysenate.gov/api/3/laws/TAX/606?full=true`. Raw retained file: `data/corpus/sources/us-ny/statute/2026-07-06-ny-tax-article22-core-us-ny-sections-tax-601-tax-606-tax-614-tax-615-tax-616/new-york-openleg-json/TAX/606.json`.

The raw-source SHA256 is `fda308972641a125f95dc0b233c2f79e1f26507b524bf23f7153dd060f5cfafd`; provisions-file SHA256 is `c9513c936e31200b318b40fa5f3f73dfef6e805284668fd42b3848263e916247`. Both independently match the recorded ingest manifest. This lane did not cryptographically verify that manifest's signature.

Newer file: `data/corpus/provisions/us-ny/statute/2026-09-14-income-tax-chapter.jsonl`, dated September 14, 2026. It contains an empty-body §606 parent and a body-bearing `us-ny/statute/TAX/606/block-1`. The entire subsection (e) matches July after whitespace normalization. Those normalized scratch excerpts are reading aids, **not admitted source replacements**.

rulespec-us `.axiom/toolchain.toml` pins `us-rulespec-2026-08-08-obbb-alien-snap`, content SHA256 `0d69a0cdbe024fc2276f3c261c00402bb0a47488ac5f482cc20bd3404980adbc`. Corpus `manifests/releases/us-rulespec-2026-08-08-obbb-alien-snap.json:1062` selects the July NY statute scope. `manifests/releases/us-rulespec-2026-08-23-canada-338-suspension-union.json` selects the same scope. The downloaded signed release was unavailable through `axiom-locate release`, so release membership here is verified from the tracked selector; the published object/content hash was not independently reverified.

**Required source work:** retain an official JSON/HTML source with URL, acquisition date and SHA provenance and expose a correctly structured (e)/(7)/(D) unit, including the controlling paragraph (7) context. If repairing the July source is the chosen route, publish a new immutable release and obtain the dedicated consumer re-pin; do not edit the current immutable release. Admit the official IT-214 and IT-214-I PDFs above, explicitly recording their 2025 vintage, before relying on their form-specific rules. No form dispatch is proposed while those source units are absent.

Evidence: [corpus inventory and hashes](corpus-coverage-note.md), [exact July row](corpus-606-july-full.json), [resolver failures](workflow-resolver-test.txt).

## 3. Existing rulespec-us coverage

The inspected origin/main contains no §606(e), IT-214, RPTC, or real-property-tax-credit module. The bounded inventory covered tracked NY modules and their §606/IT-214 references, and target-path searches across rulespec-us. The relevant nearby modules are:

| Module | Existing behavior and source evidence |
|---|---|
| `us-ny/policies/income_tax/pilot_liability_pipeline.yaml` | §601 resident main-tax schedule only. Lines 56–57: “Section 606 credits and final New York income tax are outside the / narrow non-circular `ny_main_income_tax` comparison target.” |
| `us-ny/statutes/TAX/601.yaml` | Broad income-tax source deferred: line 3 `status: deferred`; line 11 `ny_income_tax_before_credits`; line 13 `rules: []`. Its deferred reason identifies unresolved status, residency, source-fraction, tax-base and §606-credit boundaries. |
| `us-ny/statutes/NYC/11-1706.yaml` | Encodes city pass-through entity tax credit. Lines 20–21 defer `household_and_dependent_care_credit`, referring to “credits allowed under Tax Law § 606(c) and (c-2)”. This is a different credit. |

`programs/us-ny/income-tax/fy-2026.yaml:7` exposes only `ny_pit_pilot_taxable_income` and `ny_pit_pilot_main_income_tax`; it marks the latter incomplete. The adjacent §614 module is a standard-deduction module, not a credit computation.

These files demonstrate **missing Axiom coverage**, not an encoded instance of the numerical behavior in the supplied comparison. There is no existing target to replace. The existing pilot must not be passed as `replace_rulespec_path`.

## 4. Import closure

Candidate **`existing_signed_imports_json=[]`**. No existing signed-v5 module was identified that supplies the target rent-cap computation. The three nearby modules above are unnecessary for a narrow cap rule. This candidate closure contains no modules, so it has **no blocking import and no per-module compile claim**. No RuleSpec compile was run; there is no target module to compile.

Adjusted-rent derivation, averaging, and any included-service/subsidy treatment must be sourced. If separate companion encodings are chosen, they must be produced by the signed path and their completed import closure rechecked before generating the final command. An empty existing-import list is not permission to substitute unsupported legal conclusions for facts. Avoid importing federal earned-income-credit or general NY liability machinery merely to encode this restriction; the proposed empty closure cannot reach 26/32.

Source-resolution check, distinct from an engine compile: the exact encoder snapshot was extracted to scratch and its existing resolver executed without encoding. These were direct private and public slicing checks on retained body strings, not a signed-release-backed `resolve_local_corpus_source` invocation. The record-loading/encode call chain was inspected separately and passes the July body unchanged. All six body/citation combinations failed through both APIs for `/e`, `/e/7`, and `/e/7/D`. The July row contains **0 actual line breaks and 6,363 literal `\\n` sequences**; September's block contains neither actual line breaks nor literal `\\n`. Code evidence is `src/axiom_encode/corpus_resolver.py`: record-body handling, selected body to slicing at lines 621–654, parent fallback at 1405–1430, and generic state-source slicing at 1519–1529. The exact-target path maps to `us-ny/statutes/TAX/606/e/7/D.yaml`, but correct path routing does not establish successful source resolution. [Call-chain evidence and reproduction](workflow-findings.md).

## 5. Dispatch inputs

**No passing dispatch command is supplied.** `dispatch_command` is empty in the final JSON. The verified current source fails before encoding, while future corrected source/release/base SHAs do not exist in this lane's evidence. Presenting the current refs as a READY command, or inventing future refs, would misstate readiness.

The following are verified preparation values, **not a run authorization**:

| Input | Verified value or disposition |
|---|---|
| workflow/repository/ref | `targeted-signed-reencode.yml`, `TheAxiomFoundation/axiom-encode`, `main`; inspected workflow snapshot `5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9` |
| `country` | `us`, which routes `us-ny` to rulespec-us |
| `citation` | Proposed `us-ny/statute/TAX/606/e/7/D`; rejected by present source resolution |
| `rulespec_ref` | Inspected `f43dec520dd392bc5333934f56dad7498363e704`; must refresh against actual dispatch-time main |
| `corpus_ref` | Inspected corpus `942e138e7a8250c9814e774ac9b8e63008148106`; insufficient for the proposed narrow target |
| `rules_engine_ref` | Protected rulespec workflow pin `af6e4ea2920b0c0a97bf6a6f45b0c6643e93c0ca`, read from `.axiom/workflow-toolchain.toml`; ancestry/build and continued approval were not reverified |
| `replace_rulespec_path` | Empty: new target, no existing module |
| `existing_signed_imports_json` | `[]`, subject to the companion-source decision |
| `source_bundle_json` | No admitted transaction specified yet; default `[]` does not solve missing adjusted-rent/form sources |
| `review_finding` | [Prepared text](review_finding.txt), provisional until the final resolved source boundary is known |
| `pr_base_branch`, `open_pr` | `main`, `true` for a future approved dispatch |
| Other repair/dependent/legacy/queue inputs | Empty/default; this lane is not a repair replay or queue dispatch |

The workflow's input block was read in full. Its checkout gate at lines 372–403 requires lowercase 40-character SHAs, exact checkout identity, an admissible rulespec base, and corpus/engine ancestry on main. The signed job is gated on `refs/heads/main`, uses `production-signing`, and runs the installed protected encoder. Import parsing requires tracked same-jurisdiction signed-v5 modules; target/replacement validation is not bypassed by supplying a path. These checks and the live-base requirement are why a static pre-chain SHA must not be silently reused after the chain advances.

The workflow loads the signed corpus release selected by rulespec's `.axiom/toolchain.toml` (lines 827–876); a newer `corpus_ref` alone does not admit newer source scopes. After source admission, one possible bounded transaction would encode the complete adjusted-rent definition `/e/1/G` as a fresh companion before the D target. The source-bundle code supports this and makes the companion a required import. Those companion lanes receive empty review findings and complete-source validation, so a broad `/e/7` companion cannot be described as merely a chapeau. The D unit must retain its operative parent context, or the primary must become the whole bounded paragraph (7), with all its branches reviewed. Neither alternative is yet a verified dispatch package. [Workflow/source-bundle evidence](workflow-findings.md).

The full issue [TheAxiomFoundation/.github#39](https://github.com/TheAxiomFoundation/.github/issues/39) was read through the public web after CLI access failed. This package follows its source-provenance, protected-pin, generated-content, exact-proof, exhaustive-local-input and no-new-waiver rules. Max's approval remains required for any future signed run; none was requested or consumed here.

## 6. Review finding text and independent adjudication

The complete provisional `review_finding` is [review_finding.txt](review_finding.txt). It requires a strict tenant-specific `$450` monthly **adjusted-rent** prohibition, accurate source context, adjustments and rental-month treatment, paired positive/blocking cases, and precise deferrals. It does not claim that escaping this one restriction establishes positive-credit eligibility.

The retained subsection (e)(7) provides the no-credit context for (D). Its threshold is adjusted rent; subsection (e)(1)(F)(ii)'s 25% tax equivalent is a separate calculation. Subsection (e)(1)(G) supplies the included-service exclusions. For 2025 onward, the qualified-taxpayer test uses federal AGI and positive tax-equivalent excess; the senior flat-credit table gives $375 at AGI up to $3,000. The 2025 form independently performs the monthly rent test at line 13 before the 25% operation at line 14. These conclusions were derived from official/retained source text, not the sandbox docstring. [Statutory reading and source locations](statute-adjudication.md).

**Every moved benchmark output:** the sweep has exactly one r09 row, scenario_104, NY, `state_refundable_credits`, frozen **$375**, corrected **$0**. The supplied household JSON is TY2026, one single adult age 72, wages $0, Social Security retirement $14,096, veterans benefits $20,520, annual pre-subsidy rent **$6,483.529296875**. The new household-only baseline run reproduced total refundable credits $375 and RPTC $375, with federal AGI $0, housing assistance $0, actual rent equal to the supplied rent, and real-estate tax $0. [Input](household-source.json), [sweep row](sweep-moved-rows.json), [successful rerun](household-pe1755-success.log).

With no included-service adjustment and 12 rental months, $6,483.529296875 / 12 = **$540.2941080729**, above $450. Therefore the statute independently gives **$0 RPTC**. Holding the other benchmark components fixed gives **$0 state refundable credits**. **The statute supports the corrected value under that explicit input interpretation.** The annual tax equivalent, $1,620.88232421875, cannot be substituted in the cap comparison.

This conclusion is conditional on sparse inputs: the JSON does not state whether heat, utilities, furnishings, or board are included. Heat included without a separately stated charge would leave $459.24999 monthly and still fail; an unitemized heat/gas/electricity bundle would reduce monthly adjusted rent to $432.23529 and escape the cap. Accordingly neither full real-world entitlement nor universal correctness of the entire sandbox reform is established by this one household. No external-oracle finding is filed or proposed.

Four worked cases follow. Positive amounts additionally assume TY2026, full-year NY residence, age 72, AGI $0, the same residence throughout, not another person's dependent, property not wholly tax-exempt, no subsidy, and all other restrictions satisfied. All included-service facts are false except as stated.

| Case | Rent facts | Monthly adjusted rent | Cap prohibits? | Wider statutory credit; benchmark comparison |
|---|---|---:|---|---|
| **scenario_104** | $6,483.529296875; 12 months; no adjustment supplied | $540.2941080729 | Yes | **$0**; frozen **$375**, corrected **$0** |
| Equality | $5,400; 12 months; no services | $450 | No | $375; tax equivalent $1,350 exceeds zero |
| Paired blocking case | $5,412; 12 months; no services | $451 | Yes | $0 despite positive tax equivalent |
| Included heat | $6,000; 12 months; unitemized heat, 15% exclusion | $425 | No | $375; adjusted annual rent $5,100, tax equivalent $1,275 |

The finding additionally calls for 6-versus-12-month and tenant-versus-nontenant test pairs, all local inputs including false facts, and every operative service adjustment if that companion is encoded. The isolated cap should return only its restriction; the contextual positive dollar amounts above do not expand its output claim to a complete credit.

## 7. Risks and checks

- **Source-resolution rejection — demonstrated.** Fix the admitted source structure or approved resolver behavior, verify the exact resolved text/hash, and rerun resolution before proposing a command. Do not use the 400,000-character whole §606 as an opportunistic substitute target.
- **Missing form authority.** IT-214 references elsewhere in the corpus are not a retained form. Ingest the official PDFs with vintage and provenance before a form-based encoding; a pure statutory cap must explicitly limit its claims.
- **Completeness and input-boundary rejection.** The finding identifies the controlling chapeau, adjusted-rent definition, service exceptions, paired tests, and specific neighboring computations that a narrow module defers. A broader resolved unit needs a fresh completeness review. A final-credit claim requires all remaining eligibility and amount rules.
- **Proof mismatch.** Human-normalized excerpts are not the resolved provision. Generate proofs against exact admitted text; do not repair proofs by paraphrase or add a waiver.
- **Import risk.** Current candidate closure is empty. Any later companion/import changes require signed-v5 validation and an actual compile of that closure at the chosen engine. No existing-module load success is claimed.
- **Serial chain and collisions — live status unverified.** The cached main contains #1384. The supplied brief names #1387, #1386 and later drift/activation/re-pin steps; their current state could not be verified. Searches for open rulespec-us and axiom-encode PRs and the latest 30 targeted workflow runs were attempted through `gh`; all failed network access. Public-web PR/action fallbacks also failed. Consequently absence of a competing §606 run/PR is **not established**. The example failed run 35789753522 was not downloaded in this lane and is not presented as a newly inspected log. [Read-attempt logs](workflow-recent-runs.error), [rulespec PR query](workflow-open-rulespec-prs.error), [encoder PR query](workflow-open-encode-prs.error).
- **Upstream status.** The supplied root-causes record attributes a later change to policyengine-us#9301. `gh pr view 9301` failed, so current PR metadata is unverified and does not support this legal conclusion.

Completed checks: tracked corpus/module inventory; July/September subsection comparison; source/provision SHA comparisons with recorded ingest manifest; exact-origin encoder source-resolution checks; extraction of the sole moved row; one successful PE1.755.4 household baseline reproduction; four Decimal arithmetic checks. Results are in [adjudication-checks.json](adjudication-checks.json). An initial baseline command used an unavailable `social_security_taxable` variable; it failed after printing the relevant values, and the corrected command completed with exit 0. The sandbox correction was checked against the supplied sweep and prior verifier, **not rerun**. No population simulation, RuleSpec compilation, local encoding, workflow dispatch, or repository mutation was performed.

The JSON flags below refer to the **exact proposed child source unit**. Its whole-section parent is present and selected, as separately recorded.

```json
{
  "lane": "ny-606e",
  "verdict": "BLOCKED",
  "citation": "us-ny/statute/TAX/606/e/7/D",
  "in_corpus": false,
  "in_pinned_release": false,
  "source_parent_citation": "us-ny/statute/TAX/606",
  "parent_in_corpus": true,
  "parent_in_pinned_release": true,
  "existing_modules": [
    "us-ny/policies/income_tax/pilot_liability_pipeline.yaml",
    "us-ny/statutes/TAX/601.yaml",
    "us-ny/statutes/NYC/11-1706.yaml"
  ],
  "blocking_imports": [],
  "dispatch_command": "",
  "prerequisites": [
    "Make the exact section 606(e)(7)(D) source unit and its controlling context resolve through approved source ingestion/repair or an approved resolver correction.",
    "If the source changes, publish an immutable signed corpus release and complete a dedicated rulespec-us re-pin; the named August 23 re-pin alone retains the unusable July source.",
    "Ingest official IT-214 and IT-214-I with URL/date/SHA provenance before encoding their form-specific rules; verify any adjusted-rent companion source units.",
    "Refresh rulespec-us main, corpus and engine identities, verify the signed release object, resolve the target and compile any final signed import closure.",
    "Check live serial-chain status, open PRs and same-citation runs, finalize the exact command and review finding, and obtain Max's approval for the signed run."
  ]
}
```
