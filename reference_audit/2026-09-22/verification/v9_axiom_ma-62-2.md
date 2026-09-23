# ma-62-2 — Axiom preparation report

Observed September 22, 2026 EDT (September 23 UTC). Read-only lane; no RuleSpec, module tests, encoding, dispatch, repository changes, or commits. Evidence is retained beside this report. The subfleet manifest names `/Users/maxghenis/PolicyEngine/_wk/axenc-pb/report-ma-62-2.md` as the output destination; this workspace copy and the final response are supplied for the orchestrator to collect because that destination is outside this lane's writable workspace.

## 1. Verdict

**BLOCKED — official-source ingestion and a signed release containing M.G.L. c. 62 §2 are required.** The provision is absent from canonical corpus main and rulespec-us's pinned release. Following the instruction to stop encoding preparation when the source is missing, no dispatch command or encoder finding is proposed.

The ongoing re-pin chain is insufficient: both the currently pinned August 8 release manifest and the planned August 23 Canada suspension-union manifest select the same Massachusetts statute snapshot, which lacks §2. This lane cannot dispatch against today's main or merely wait for that chain and then dispatch. A subsequent source-bearing release and dedicated activation/pin must land, followed by a fresh preparation check and Max's signed-run approval.

Independent household conclusion: **the statute supports the r22 corrected $8,232.90 when the benchmark's Part B treatment of the $56 interest is retained as an explicit qualifying-bank-interest assumption. Ordinary Part A interest instead gives $8,230.10.** The stated household does not resolve that distinction; the dividend-loss offset is supported in either case.

## 2. Source

Official source: [Massachusetts General Court, chapter 62 section 2](https://malegislature.gov/Laws/GeneralLaws/PartI/TitleIX/Chapter62/Section2), HTML, particularly (b), (c)(2)(a), (c)(4), and (f). Corroboration: [DOR TIR 02-21](https://www.mass.gov/technical-information-release/tir-02-21-capital-gains-and-losses-massachusetts-tax-law-changes), dated January 2, 2003, section II.C. The TIR's historical rates are not used for 2026.

The intended canonical citation is **`us-ma/statute/62/2`**, consistent with the neighboring section citations. **It is not an existing resolved corpus citation.** No subsection or block citation for this missing source has been invented.

Verified revisions:

| Repository / evidence | Immutable value |
|---|---|
| rulespec-us local `origin/main`, equal to remotely read main | `f43dec520dd392bc5333934f56dad7498363e704` |
| canonical axiom-corpus `origin/main`, equal to remotely read main | `942e138e7a8250c9814e774ac9b8e63008148106` |
| rulespec-us pinned corpus release | `us-rulespec-2026-08-08-obbb-alien-snap` |
| pinned content SHA-256 | `0d69a0cdbe024fc2276f3c261c00402bb0a47488ac5f482cc20bd3404980adbc` |

The requested `git fetch -q origin` was attempted and failed because the sandbox denied writing `.git/FETCH_HEAD`. Read-only GitHub ref queries independently confirmed both local remote-tracking SHAs; no checkout was changed.

The sole tracked Massachusetts statute provision file is [`data/corpus/provisions/us-ma/statute/2026-07-13-recovery.jsonl`](https://github.com/TheAxiomFoundation/axiom-corpus/blob/942e138e7a8250c9814e774ac9b8e63008148106/data/corpus/provisions/us-ma/statute/2026-07-13-recovery.jsonl). Its 36 records cover 12 sections: 3, 4, 6, 6l, 10a, 11a, 14, 16, 42, 54, 62, and 64, each with a document row and two blocks. **None covers §2.** The snapshot's `source_as_of` and `expression_date` are July 13, 2026; retained metadata records fetching July 14. A tracked provision search for `us-ma/statute/62/2` returned no match. The coverage file's `complete: true` describes that recovered inventory; it does not establish that every chapter section exists.

Both release manifests select `us-ma / statute / 2026-07-13-recovery`; thus §2 is absent from both selected statute scopes. The July 6 chapter-level ingest manifest is a source plan, not evidence of retained §2 text. Evidence: [citation inventory](evidence/corpus-ma-citations.txt), [current release scope](evidence/pinned-ma-scopes.json), [planned release scope](evidence/planned-ma-statute-scope.json), [planned release manifest](https://github.com/TheAxiomFoundation/axiom-corpus/blob/942e138e7a8250c9814e774ac9b8e63008148106/manifests/releases/us-rulespec-2026-08-23-canada-338-suspension-union.json), and [remote refs](evidence/corpus-remote-ref.json). Release inclusion was checked against these tracked manifests and their selected provision snapshot; the signed release object itself was not downloaded.

**Required ingest:** retain the complete official §2 HTML from the URL above, with retrieval date, effective/source vintage, SHA-256 of the retained bytes, extraction, and signed provenance. Preserve the dated amendment alternatives and subsection boundaries. If TIR 02-21 will supply proof evidence, ingest its official HTML separately with the same provenance; its exact citation must be assigned and verified through that ingest. This lane's web extracts are research evidence, not signed corpus artifacts. Publish a new immutable signed release containing the provision, then activate/pin it through the dedicated gated process. No ingest or corpus change was attempted.

## 3. Existing rulespec-us coverage

There is no `us-ma/statutes/62/2.yaml` on the verified main. The relevant neighboring modules are:

| Existing path | Observed scope and relevant verbatim excerpt |
|---|---|
| `us-ma/statutes/62/3.yaml` | Part B exemption scalars; summary: “Part B(b) allows exemptions against Part B income”. It defers the final personal-exemption computation. |
| `us-ma/statutes/62/4.yaml` | Rate and surtax parameters; includes `part_a_short_term_capital_gains_tax_rate` and `part_a_interest_and_dividends_stated_tax_rate`. It does not compute the §2 loss-adjusted base. |
| `us-ma/statutes/62/6.yaml` | Lead-paint and earned-income credit provisions; summary: “the credit equals 40 per cent of the federal credit”. |
| `us-ma/policies/income_tax/pilot_liability_pipeline.yaml` | Estimated-tax slice using completed 5% taxable income; explicitly excludes “cross-Part deductions upstream of completed taxable income”. |
| `us-ma/policies/income_tax/2026_full_year_resident_source_hold.yaml` | Explicit coverage hold: “every public Massachusetts Money stage is a fail-closed zero sentinel”; these are “not legal claims that Massachusetts income, credits, or tax are zero.” |

The remaining chapter-62 modules are `10a.yaml` (qualified funeral trust), `11a.yaml` (trust withholding), `14.yaml` (corporate fiduciaries), `16.yaml` (fiduciary settlement), `42.yaml` (fiduciary liability), `54.yaml` (severability), `62.yaml` (accounting methods), `64.yaml` (tax tables/rounding), and `6l.yaml` (credit refund election). Their summaries were read and retained in [nearby-summaries.txt](evidence/nearby-summaries.txt); the full tracked Massachusetts inventory is [rulespec-ma-paths.txt](evidence/rulespec-ma-paths.txt).

These modules supply adjacent parameters or explicit holds, not the assigned computation. No existing §2 calculation was found that could carry the same loss-offset behavior or adjudicate the household. Held monetary zeros are not an Axiom tax answer.

## 4. Import closure

**Stopped at the missing-source gate.** No signed-v5 import set or closure was selected, and no existing module was compiled in this lane. The empty `blocking_imports` list below means no proposed closure, not a clean compilation result. No claim is made that this target reaches federal §32.

Both nearby income-tax policy modules visibly declare plural `corpus_citation_paths`. A [signed-run log](https://github.com/TheAxiomFoundation/axiom-encode/actions/runs/35789753522) read in this lane rejects that field in imported `us:statutes/42/416/l`. By that observed rule, importing either nearby MA policy module would risk the same rejection; they are not proposed imports. Future preparation must check the actual complete closure, signatures, and engine loads after ingestion.

## 5. Dispatch inputs

**No runnable command.** A command with `citation=us-ma/statute/62/2` cannot satisfy source resolution against the inspected release. Supplying a newer `corpus_ref` alone does not fix this: the [workflow at verified encoder SHA `5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9`](https://github.com/TheAxiomFoundation/axiom-encode/blob/5d80d753f1ad54bc4b6a0686522ae9aa69e47bb9/.github/workflows/targeted-signed-reencode.yml), lines 831–879, materializes the release selected by the rulespec toolchain.

The required input block and validation were read. The same commit's helper requires `open_pr=true` runs to use the exact remote PR-base tip; today's rulespec SHA cannot be carried unchanged through future merges. Remotely verified engine main was `6e709eb1ca7ea686263293d932c759d9dee48a4a`, but it is not presented as a tested dispatch ref. No replacement path, imports JSON, review finding, or future ref was fabricated. See [workflow notes](workflow/notes.md).

## 6. Review finding text

**No `review_finding` dispatch input is supplied while the source is absent.** The following is the independently requested household adjudication, not an encoder brief or a filed finding against an oracle.

Section 2(b) classifies ordinary interest/dividends in Part A, subject to specified bank-interest and other exceptions. Section 2(c)(2)(a) applies excess short-term losses to Part A interest/dividends before Part C gains and carryforward. Section 2(c)(4) provides one combined $2,000 limit for short- and long-term losses against that interest/dividend income. Section 2(f) starts taxable Part A income from adjusted Part A income. [Official §2](https://malegislature.gov/Laws/GeneralLaws/PartI/TitleIX/Chapter62/Section2) and [TIR 02-21, II.C](https://www.mass.gov/technical-information-release/tir-02-21-capital-gains-and-losses-massachusetts-tax-law-changes) support this ordering.

**Every moved r22 household: scenario_081 only.** Facts directly extracted from `scenario_json`: MA, 2026, single, age 30, no children; wages $175,002; dividends $110.11764526367188; interest $56; short-term capital gains −$1,080; annual rent $44,400. No long-term or collectible gain/loss or carryforward is supplied. Bank assets of $129,000 do not establish the deposit type or institution qualifying for the bank exception.

| Interpretation of the same household | PolicyEngine 1.755.4 | Supplied corrected sweep | Independent amount |
|---|---:|---:|---:|
| r22: retain qualifying Part B bank interest | $8,238.40625 | $8,232.900391 | **$8,232.90** |
| r23 context only: ordinary Part A interest | $8,238.40625 | $8,230.100586 | **$8,230.10** |

For the r22 comparison, the allowable loss is `min(1080, 2000, 110.11764526367188) = 110.11764526367188`. Part A adjusted income and taxable dividends are zero. With no Part C gains, unused short-term loss is $969.88235473632812. The unchanged Part B calculation is:

```text
175,002 wages + 56 bank interest − 2,000 FICA deduction
− 4,000 rent deduction − 4,400 single exemption = 164,658
164,658 × 5% = 8,232.90
```

The [§3 deductions and exemption](https://malegislature.gov/Laws/GeneralLaws/PartI/TitleIX/Chapter62/Section3) and [DOR 2026 rates](https://www.mass.gov/info-details/massachusetts-tax-rates) were checked. Rent gives `min(44,400 × 50%, 4,000) = 4,000`; wages exhaust the $2,000 FICA deduction cap. The observed household has no nonrefundable credit and is below the surtax threshold. The dividend tax removed is $5.505882263183594 before numeric representation differences.

For ordinary Part A interest, Part A interest/dividends are $166.11764526367188, all absorbed by the loss. Part B taxable income becomes $164,602 and tax is $8,230.10; unused short-term loss is $913.88235473632812. Neither branch deducts the remaining loss from wages or restores the repealed bank-interest exemption.

**Adjudication:** the statute supports the corrected r22 amount under its retained interest-classification assumption. It supports the r23 contextual amount under ordinary-interest facts. The frozen $8,238.41 is supported by neither branch of this supplied household comparison. A unique full-household answer remains undetermined by the prompt's interest facts; the zero taxable-dividend result does not.

Verification: the authorized household-level `pe_case.py` run reproduced frozen `8238.40625` exactly. It recorded Part A AGI zero, taxable dividends `110.117645`, Part B taxable income `164658`, and nonrefundable credits zero. Checks passed for household identity across the supplied and helper bundles, exactly one moved r22 output, only one MA scenario, and both decimal calculations. Fixed simulations were not rerun; their values above come from the supplied sweep. [Facts/checks](adjudication/facts_and_math.json), [calculation log](adjudication/pe_case_081.txt), and [full legal reading](adjudication/adjudication.md) preserve the evidence.

## 7. Risks

- **Missing retained source is the immediate rejection risk.** Ingest and release activation/pinning are prerequisites; no waiver or finding wording can substitute for them. Binding [agent rules #39](https://github.com/TheAxiomFoundation/.github/issues/39) were read.
- **Serial-chain timing:** [#1384](https://github.com/TheAxiomFoundation/rulespec-us/pull/1384) is merged; [#1387](https://github.com/TheAxiomFoundation/rulespec-us/pull/1387) and [#1386](https://github.com/TheAxiomFoundation/rulespec-us/pull/1386) remained open when checked. Later drift/activation stages were not verified as landed. Even their planned August 23 release lacks this statute section.
- **Future encoding scope:** the resolved source unit will determine the required branch coverage. Complete-source-unit enforcement, verbatim corpus proof excerpts, every local input assigned in every test, and positive/blocking exception cases must be addressed after ingest. A finding cannot yet be grounded in a nonexistent corpus extraction. The bank exception and shared loss cap must not be inferred from the household's residence or handled as separate $2,000 allowances.
- **Import validity:** singular-source compatibility, signed-v5 admission, and actual closure compilation are separate checks. They remain unperformed for a future §2 module.
- **Collisions:** open PR searches for `"62/2"` and `"chapter 62"` in both repositories returned none. `"us-ma"` matches were unrelated SNAP/provenance/waiver work. All 16 September 22 UTC dispatches and the latest 30 targeted runs, including September 22 EDT's later UTC runs, contained no MA target. Searches are a dated observation, not a guarantee against later work.
- **Evidence limits:** direct TIR retrieval returned 403; official search-indexed text supplied its content and date. Current official text was read, but no signed source vintage or complete legal change-history validation is claimed. No Axiom-generated household result exists for this provision.

Only scratch evidence and this report were written. No commits were made because the lane's explicit read-only/no-commit rule governs this preparation task.

```json
{
  "lane": "ma-62-2",
  "verdict": "BLOCKED",
  "citation": "us-ma/statute/62/2",
  "in_corpus": false,
  "in_pinned_release": false,
  "existing_modules": [
    "us-ma/statutes/62/3.yaml",
    "us-ma/statutes/62/4.yaml",
    "us-ma/statutes/62/6.yaml",
    "us-ma/statutes/62/6l.yaml",
    "us-ma/statutes/62/10a.yaml",
    "us-ma/statutes/62/11a.yaml",
    "us-ma/statutes/62/14.yaml",
    "us-ma/statutes/62/16.yaml",
    "us-ma/statutes/62/42.yaml",
    "us-ma/statutes/62/54.yaml",
    "us-ma/statutes/62/62.yaml",
    "us-ma/statutes/62/64.yaml",
    "us-ma/policies/income_tax/pilot_liability_pipeline.yaml",
    "us-ma/policies/income_tax/2026_full_year_resident_source_hold.yaml"
  ],
  "blocking_imports": [],
  "dispatch_command": "",
  "prerequisites": [
    "Ingest official M.G.L. c.62 section 2 HTML with retained bytes, URL, date, SHA-256 and signed provenance; verify its resolved canonical citation and source unit.",
    "Ingest official TIR 02-21 with provenance if it will supply proof evidence.",
    "Publish and activate/pin a new immutable signed corpus release containing section 2; the current and planned Canada-338 releases lack it.",
    "Repeat source-scope, signed-v5 import-closure, engine-load and collision checks after the source-bearing pin lands; select the then-current exact rulespec main SHA for open_pr=true.",
    "Obtain Max's approval before any signed run; the orchestrator controls dispatch."
  ]
}
```
