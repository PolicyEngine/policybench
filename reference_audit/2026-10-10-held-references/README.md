# Two references checked against a model consensus and held, October 10, 2026

On 2026-10-10 a session checked two scored references of release dashboard-data-20261010 that several strong models agree against. In each cell the consensus applies a rule the law does not give, and the reference is what the statute's rate schedule gives for the stated facts as the engine reads them. Whether the prompt's wording fixes that reading is the open question below, and the Virginia review's point about the Tax Table is unresolved. This directory holds the check, the evidence it rests on, two independent reviews, and a second check of the whole of it made for this record.

| Cell | Reference | Models' consensus | Verdict | The rule the consensus gets wrong |
|---|---:|---:|---|---|
| scenario_039 (VA), `federal_income_tax_before_refundable_credits` | $8,596.03 | $5,145.11 (6 models) | Reference holds | Filing status. The six models file the lone widowed head as a qualifying surviving spouse. 26 U.S.C. 2(a)(1)(B) requires a dependent child living in the home. |
| scenario_025 (OH), `state_income_tax_before_refundable_credits` | $1,916.61 | $1,589.56 (8 models) | Reference holds | The 2026 rate schedule. R.C. 5747.02(A)(3)(c) is "$332.00 plus 2.75% of the amount in excess of $26,050". The eight models leave out the $332.00, and take no medical deduction. |

**This is evidence only.** It changes no reference, exclusion record, score, payload or frozen snapshot. It adds two records to `reference_audit/held_references.json` and one option to `policybench adversary-prepare`, which decides only which flagged cells get an adversary case.

**One call is open.** Each independent reviewer agrees that the consensus is wrong, and would still exclude its cell, on a wording ground the consensus does not raise ([The reviewers' dissents](#the-reviewers-dissents)). Whether to keep scoring the two outputs is Max's call. It was queued as cos decision d1252 on 2026-10-10 and had not been ruled when this record was written. Nothing here acts on it.

## What the consensus trigger does with these cells

The trigger (`policybench consensus-flags`) flags a cell when a wrong cluster has at least 15 models, or at least 3 of the top 5. On the release's payload (`data.json.gz`, sha256 `535a51db…`, 47 models) at the default parameters it flags 55 of 1,926 scored cells (`verification/consensus_flags_20261010.json`).

- **scenario_025 is flagged.** Its cluster at $1,590 has 8 models, 4 of them in the top 5 (gpt-6-sol, claude-opus-5.5, claude-sonnet-5.5, gpt-6-luna).
- **scenario_039's federal income tax is not flagged today.** Its cluster at $5,145 has 6 models, and only 2 are in the top 5 (claude-opus-5.5 and claude-sonnet-5.5). The other four rank 6th, 7th, 9th and 12th (gpt-6-astra, claude-fable-5.1, gpt-6.1-sol, gpt-5.5). The cell would be flagged once three of the cluster's models are in the top 5: one of those four moving up past a model outside the cluster, or one more top-5 model giving the same answer. With `--min-top 2` it is flagged now (`verification/consensus_flags_20261010_min_top_2.json`).

This output returned to scoring in release dashboard-data-20261010, when policyengine-us #10027 fixed the engine defect that had excluded it (`reference_audit/2026-10-09-engine-upgrade/final_actions.json`). The reference adversary has never judged it. scenario_025 was judged on 2026-10-06 at its old reference ([Ohio's earlier record](#ohios-earlier-record)).

## How a later pass lists them

`reference_audit/held_references.json` is a standing list of references a check has held. Each record names the cell, the held reference, each consensus answer the check explained, and where the check is written up.

`policybench adversary-prepare --held-references reference_audit/held_references.json` reads it (`policybench/held_references.py`). A flagged cell with a record gets no adversary case, and `<adversary-dir>/held_references.json` lists it as checked and held next to the explanation of each triggering cluster. The record applies only while all of these are true:

1. **The prompt is the one the check read.** The record carries the sha256 of the prompt the models answered: the preface, the household, every output's definition. A scenario id is a position in a run, so the same id can name another household later, and a reworded prompt is another question.
2. **The reference is the held value**, within a dollar.
3. **Each triggering cluster is an answer the record explains:** every member's own answer is within a dollar of the same explained answer.

The dollar is PolicyBench's exact-match tolerance and belongs to the record. The pass's own `--tolerance` is not used, so a pass run at a loose tolerance cannot stretch a record over another answer.

Otherwise the cell is judged as usual, and the listing gives the first reason that fails: `prompt_changed`, `reference_moved` or `unexplained_consensus`. A record whose cell is not flagged is listed as `not_flagged`.

Three guards keep the option from hiding or losing anything:

- The flags must come from the payload they are applied with. A held flag gets no case, so the command checks it against the payload as it checks a flag that does get one, and refuses flags whose recorded payload hash is another's.
- Preparing a directory removes the case of a cell no longer listed. If a cell that would now be listed as held already has judge output there, the command refuses and deletes nothing.
- A record that no longer applies to a cell another audit covers (`--skip-cells`) is reported as covered elsewhere, not as judged.

Run on the release's payload:

| Flags | Cases prepared | Listed as checked and held | Not flagged |
|---|---:|---|---|
| Default parameters, 55 flags | 54 | scenario_025 | scenario_039 |
| `--min-top 2`, 71 flags | 69 | scenario_025, scenario_039 | none |

The listings are `verification/held_on_20261010.json` and `verification/held_on_20261010_min_top_2.json`.

Each record explains only the consensus answer that was checked: $5,145.11 and $1,589.56. Neither lists the answer its reviewer's other reading gives ($6,259.99; $1,319.65 or $1,145.86). If models came to agree on one of those, the cell would be judged.

## How the verdicts were checked

`report/REPORT.md` is the session's write-up, as it wrote it. It ran both households on policyengine-us upstream main at commit `75cdd8019e` (version 2.38.8, policyengine-core 3.33.0), worked each cell by hand from the law, reconstructed the models' answers from their own explanations, and had each cell reviewed by GPT-6.1 Sol.

For this record every claim in that report was treated as a claim and checked again on 2026-10-10:

| Claim | How it was checked | Result |
|---|---|---|
| Both references reproduce on main `75cdd8019e` (2.38.8) | policyengine-us installed from that commit in a clean environment, with policyengine-core 3.33.0; `scripts/trace_cells.py` run on the release's `scenarios.csv` | $8,596.03 and $1,916.61. All four trace files and both situations are byte-identical to the session's; `key_variables.txt` differs only in the install path on its first line. The re-run's listed values, its install record and its files' hashes are in `traces/policyengine-us-2.38.8-75cdd8019e/rerun/`. |
| Both references reproduce on the release's own engine | The same script on policyengine-us 2.38.6 with policyengine-core 3.32.29, the environment `uv.lock` pins | $8,596.03 and $1,916.61 (`traces/policyengine-us-2.38.6/`). Both situations, all 77 listed values and both short traces equal the 2.38.8 run's. A short trace (`*_trace.txt`) prints the tree under the output and prunes every zero-valued branch, with whatever lies under it. The full traces print those branches too, and differ in 36 lines for scenario_039 and 29 for scenario_025: repeated references to capital-gains variables that are zero, an `adjusted_earnings` node that 2.38.6 nests under `filer_adjusted_earnings`, and one reference that reads `employment_income` on 2.38.6 and `irs_employment_income` on 2.38.8. |
| The hand derivations | `scripts/hand_derivations.py`, exact decimal arithmetic from the facts and the law's figures, with no engine | Virginia's reference reproduces to the cent. Ohio's statute figure is $1,916.60; with the fixed amount as the engine carries it, $332.00204, the same arithmetic gives the reference, $1,916.61. Both consensus answers, each other model answer the report reconstructs, and each value the reviewers' other readings give also reproduce to the cent (`verification/hand_derivations.json`). |
| The situations the engine was run on | PolicyBench's own `Scenario.to_pe_household`, on the release's `scenarios.csv` | Equal to both committed situations. |
| The models' answers | `model_answers.json` compared with the release's payload | All 94 answers and explanations match. The cluster sizes, ranks and quoted explanations are as reported. |
| The law | Every statute excerpt compared with the Government Publishing Office's text or with codes.ohio.gov; each PDF downloaded again | No difference (`law/sources.json`). |
| The data flag behind "is a surviving spouse" | policyengine-us-data `cps.py` and Microcosm `relationship_inputs.py` read on their main branches | Both set it from marital status code 4 ([Prompt labels](#prompt-labels)). |

Four statements in the report need correcting or qualifying; see [Corrections to the report](#corrections-to-the-report).

## Virginia scenario_039: federal income tax before refundable credits

### What the models saw

One person: age 61, "is disabled", "is a surviving spouse", estate income $25,950, self-employment income -$6,260, Social Security retirement income $36,105, taxable IRA distributions $26,800, taxable private pension income $2,030, and premiums and assets that do not move the answer (`prompt_households.json`). No other household member. No prompt states a filing status.

### By hand

1. **Filing status: single.** 26 U.S.C. 2(a)(1) defines "surviving spouse" as a taxpayer (A) whose spouse died in one of the two preceding tax years and (B) whose home is the principal place of abode of a dependent son, stepson, daughter or stepdaughter. The household has no child, so (B) fails whenever the spouse died. The 2025 Form 1040 instructions say the same of a filer widowed before the year: single, "But if you have a child, you may be able to use the qualifying surviving spouse filing status".
2. **Income other than Social Security.** Estate income is gross income (26 U.S.C. 61(a)(14)). $25,950.00 - $6,260.03 + $26,800.00 + $2,030.00 = $48,519.97.
3. **Social Security (26 U.S.C. 86).** Other income plus half of benefits is $66,572.47, above the $34,000 adjusted base amount. The taxable part is the lesser of 85% of benefits ($30,689.25) and 0.85 × ($66,572.47 - $34,000) + $4,500 = $32,186.60: **$30,689.25**.
4. **Adjusted gross income:** $79,209.22.
5. **Standard deduction:** $16,100 (Rev. Proc. 2025-32, section 4.14). The head is 61, so there is no additional amount.
6. **Qualified business income deduction:** 0. The only business item is a loss, which carries forward (26 U.S.C. 199A(c)(2)).
7. **Taxable income:** $63,109.22.
8. **Tax** (Rev. Proc. 2025-32, section 4.01, Table 3): $5,800 + 22% × ($63,109.22 - $50,400) = **$8,596.03**.
9. **Credits and other taxes:** none. The credit for the elderly or the disabled starts from at most $5,000 and falls by half of adjusted gross income above $7,500 (26 U.S.C. 22(c) and (d)). The net investment income tax starts at $200,000 (26 U.S.C. 1411(b)).

The engine takes the same steps (`traces/*/key_variables.txt`): `filing_status` SINGLE, `surviving_spouse_eligible` False with `tax_unit_child_dependents` 0, `tax_unit_taxable_social_security` 30,689.25, `adjusted_gross_income` 79,209.22, `taxable_income` 63,109.22, `income_tax_before_refundable_credits` 8,596.03.

### The consensus, $5,145.11

Six models (claude-opus-5.5, claude-sonnet-5.5, gpt-6-astra, claude-fable-5.1, gpt-6.1-sol, gpt-5.5) compute income as the reference does and change only the filing status. Working from the prompt's whole-dollar loss, their adjusted gross income is $79,209.25. They take the $32,200 standard deduction and the joint table: $2,480 + 12% × ($47,009.25 - $24,800) = **$5,145.11**. To the cent of the underlying facts it is the same figure.

All six say so. Claude Opus 5.5: "Filed as surviving spouse, which uses the joint brackets and joint standard deduction". None of the six mentions a child or a dependent. Four models match the reference (gpt-6-sol, gpt-6-luna, kimi-k3, ox-alpha), and two of them state the test. Kimi K3: "surviving spouse with no dependent child cannot use qualifying-surviving-spouse status".

Two more models (gpt-5.6-sol and gpt-5.6-luna, about $4,485) make the same status error and also use the joint return's Social Security thresholds, which gives $4,484.79.

## Ohio scenario_025: state income tax before refundable credits

### What the models saw

A married couple with no dependents. Head, 61: no wages, "has employer-sponsored insurance", "employer sponsored insurance premiums: $21,208", "health insurance premiums excluding Medicare Part B: $6,500", "other health insurance premiums: $6,500", "other medical expenses: $800", "over-the-counter health expenses: $50". Spouse, 57: wages $62,725, taxable private pension income $32,200, "has employer-sponsored insurance".

### By hand

1. **Federal adjusted gross income:** $62,725.29 + $32,200.00 = $94,925.29.
2. **Medical deduction (R.C. 5747.01(A)(10)).**
   - Division (a) deducts insurance premiums in full, but not for a taxpayer "eligible to participate in any subsidized health plan maintained by any employer of the taxpayer or of the taxpayer's spouse". Both spouses have employer coverage, and the $21,208 is read as the employer's share of the head's plan, so nothing is deducted in full.
   - Division (b) deducts medical care the taxpayer paid, above 7.5% of federal adjusted gross income. Division (c) takes the meaning of medical care from 26 U.S.C. 213, which includes insurance. The 2025 worksheet puts these premiums on line 3 and other care on line 4.
   - Line 3 is $6,500 and line 4 is $800. The $50 of over-the-counter expenses is left out: 26 U.S.C. 213(b) counts a medicine or drug only if it is prescribed or is insulin. Line 5 is $7,300, line 7 is 7.5% × $94,925.29 = $7,119.40, and line 8 is **$180.60**.
   - The $21,208 is not counted: as the employer's payment, the taxpayer did not pay it. The engine documents the input as "Annual employer-paid health insurance premiums". The prompt gives the head's premiums, excluding Medicare Part B, as $6,500 in total.
3. **Ohio adjusted gross income:** $94,744.69.
4. **Exemptions (R.C. 5747.025):** two at $1,900, the amount for modified adjusted gross income above $80,000. H.B. 96 section 757.120(A) bars any adjustment of the exemption amounts or the $26,050 threshold "in 2025 or 2026".
5. **Taxable nonbusiness income:** $90,944.69.
6. **Tax (R.C. 5747.02(A)(3)(c)):** $332.00 + 2.75% × ($90,944.69 - $26,050) = $2,116.60.
7. **Credits.** Retirement income credit: $200 for retirement income over $8,000 when modified adjusted gross income less exemptions is under $100,000 (R.C. 5747.055(B)). Joint filing credit: none, because each spouse needs at least $500 of qualifying income and the head has none (R.C. 5747.05(E)(1)).
8. **Result:** $2,116.60 - $200 = **$1,916.60**.

The engine gives $1,916.61. Its rate table carries the fixed amount as 1.27448% × $26,050 = $332.002, the rate R.C. 5747.02(A)(2) sets for 2026, and that fraction of a cent rounds the result up.

### The consensus, $1,589.56

Eight models (gpt-6-sol, claude-opus-5.5, claude-sonnet-5.5, gpt-6-luna, claude-fable-5.1, kimi-k3, grok-4.7, gemini-3.6-flash) take no medical deduction and no fixed amount: 2.75% × ($94,925 - $3,800 - $26,050) - $200 = **$1,589.56**. Claude Opus 5.5 writes the assumption down: "assuming no base amount is added to the 2026 schedule".

The answer is about $327 below the reference: the $332.00, less the $4.97 that the medical deduction they do not take is worth.

Other answers reconstruct the same way (`verification/hand_derivations.json`):

| Answer | Reading | Model |
|---:|---|---|
| $1,921.57 | The $332.00, no medical deduction: the reference before policyengine-us #10020 | none |
| $1,742.81 | The $332.00; the $6,500 deducted in full | gpt-6.1-sol |
| $1,319.63 | The $332.00; the $21,208 counted as paid by the head, so the exemptions fall to $2,150 each | gpt-6-astra |
| $1,950.25 | The 2024 fixed amount, $360.69 | gpt-5.6-sol |

### Ohio's earlier record

The reference adversary judged this cell on 2026-10-06, when the reference was $1,921.57. Its verdict, confirmed independently, was an engine defect: the engine gave the head's premiums no weight (`reference_audit/2026-10-05-reference-adversary/verification/independent/oh_025.md`). That file put the law's value at $1,916.60 and found the consensus "wrong under every reading". Under decision d1022 the output was excluded and then regenerated once the engine was fixed. policyengine-us #10020 fixed it, and release dashboard-data-20261010 regenerated the reference at $1,916.61 and returned it to scoring.

So the reference now equals the value the earlier record derived, and the same eight-model cluster stands against it.

## The independent reviews

Two GPT-6.1 Sol reviews, one per cell: `reviews/review_va039.md` and `reviews/review_oh025.md`, with their briefs beside them. Both are committed as written, including their links to files on the maintainer's machine.

**How independent they were.** Each brief told the reviewer to work the cell from the law first, and did not state the session's verdict. Each brief did name the candidate answers and say which one is the reference. Both reviews report a read-only sandbox, and they worked from the sources in the session's `law/` folder; the Virginia review says it used no network. The Ohio review also read the session's report as it then stood: its last section cites `REPORT.md` and says it "overstates scenario_025's conclusion". The report was last saved five minutes after the reviews.

**Where they agree with the verdicts.**

- The references and the consensus answers: $8,596.03 and $5,145.11 for Virginia; $1,916.60 and $1,589.56 for Ohio.
- The reconstructions each review takes up. Virginia's: the joint-return answer, $4,484.79. Ohio's: $1,921.57, $1,742.81 and $1,319.63. The Ohio review does not take up gpt-5.6-sol's $1,950.25, which only the report reconstructs.
- Virginia: the filing status is single. The reviewer puts its confidence "above 99% in the arithmetic and Single status for an ordinary widow with no qualifying child".
- Ohio: "The rate schedule is settled in PolicyEngine's favor: $332, 2.75%, the frozen threshold and frozen exemptions are correct. B's consensus does not follow the statute."

### The reviewers' dissents

Each reviewer's verdict is "Scenario ambiguous", not "PolicyEngine correct". Each would exclude its output from scoring. Neither ground is the consensus's.

**Virginia: "estate income" states no character.** The reviewer: "The principal exclusion ground is therefore estate-income character and category scope. The surviving-spouse label is an additional wording defect, but weaker grounds for treating B as an established lawful household liability."

- The engine defines the input as Schedule E Part III income carried to Schedule 1 line 5, with an estate's interest, dividends and capital gains in other inputs. The prompt says only "estate income".
- Read as qualified dividends or long-term gain, the same $25,950 is taxed at preferential rates and the tax is **$6,259.99**, with the same filing status, adjusted gross income and taxable income.
- The reviewer's confidence: "75% in exclusion".
- The reviewer names what would change its mind: documentation the models could see, or the certified record, establishing "residual ordinary Schedule E income".

**Ohio: "employer sponsored insurance premiums" does not say who paid.** The reviewer: "The medical input is underspecified. 'Employer sponsored insurance premiums' identifies a plan relationship and an amount, but not the payer."

- The engine's definition, "Annual employer-paid health insurance premiums", was not in the prompt.
- Read as paid by the head after tax, with the plan subsidized, the tax is **$1,319.65**. With no employer contribution stated, the plan is unsubsidized under the prompt's defaults, both premium amounts are deducted in full, and the tax is **$1,145.86**.
- The reviewer's confidence: "very high on the rate and freeze, and high on medical ambiguity". It adds: "Exclusion does not make B's missing $332 correct."
- The reviewer also notes that the repeated $6,500 is not marked as one payment listed twice ($1,737.85 if it is two), that the $50 could be a qualifying supply ($1,915.23), and that the pension is not said to be received on account of retirement, which the $200 credit requires.

This is the reading the 2026-10-06 verification called R4 and rejected as "inconsistent with the prompt's own premium total": the prompt gives the head's premiums, excluding Medicare Part B, as $6,500.

**Why the session's report did not adopt them.** On Virginia: the preface sets every unlisted numeric input to 0, qualified dividends and capital gains are separate inputs, and no model answers within $1 of $6,259.99. On Ohio: the prompt's own $6,500 total leaves the $21,208 out; one model, gpt-6-astra, does take the reviewer's subsidized-plan reading ($1,319.63), and none the unsubsidized one. The report reads both as wording gaps that earlier audits had weighed, and neither as support for the consensus.

**What is undecided.** PolicyBench's rule excludes an output "when its reference depends on an input or definition that the certified household data never carried and the prompt therefore never stated, and a careful reader could take the stated facts the other way". Whether either dissent meets it is a scoring call, not a question about the engine or the law. It is Max's, as decision d1252, and it is pending. If it goes the reviewers' way, a later release excludes the output; this record would then be listed as `not_flagged`, because the trigger reads scored cells only.

### One more point from the Virginia review

The 2025 Form 1040 instructions say a filer with taxable income under $100,000 "must use the Tax Table". On the 2025 table a single filer's band from $63,100 to $63,150 reads $8,802, which is the 2025 rate schedule at the band's midpoint ($8,801.50) rounded to the dollar. The same method on the 2026 rates would give $8,600, $3.97 above a reference that applies the rate schedule exactly. No 2026 Tax Table exists yet. The point reaches every federal income tax reference with taxable income under $100,000, not this cell alone, and this record does not settle it.

## Prompt labels

Two labels did the misleading, and both are noted on the v2 prompt issue, PolicyEngine/policybench#165.

- **"is a surviving spouse."** That is the Code's name for the filing status that gets the joint table. The data flag is only the survey's marital status. The label is in 12 of the 100 prompts, and none of those households lists a child. policyengine-us-data sets `is_surviving_spouse` from `A_MARITL == 4` (`policyengine_us_data/datasets/cps/cps.py` line 1212 at main `42ed5d45`), and Microcosm does the same (`packages/microcosm-build/src/microcosm/build/us_runtime/relationship_inputs.py` line 181 at main `aca40a69`). The engine adds the child test itself (`surviving_spouse_eligible`). `engine_sources.md` quotes all three.
- **"estate income."** The label states no character, and the engine's meaning (ordinary Schedule E income) is not in the prompt. It is in two prompts: this one and scenario_110 (OH).

"employer sponsored insurance premiums" is already on #165, which asks to label it employer-paid.

## Corrections to the report

1. **The independent reviews were not blind to the candidates.** The report says the reviewers "worked each cell from the law before seeing any answer". The briefs named the candidate answers and the reference, and the Ohio reviewer read the report as it then stood. The briefs did withhold the verdicts, as the report says.
2. **The trigger does not flag scenario_039's federal income tax today.** The request behind this record expected the next pass to flag it. At the default parameters it does not ([above](#what-the-consensus-trigger-does-with-these-cells)).
3. **The reviews do not confirm every reconstruction.** The report says they agree with "each reconstruction above". The Ohio review reconstructs three other answers and not $1,950.25.
4. **The Department of Taxation's FAQ is not among the saved sources.** The report cites its questions 8 and 9. The session's `law/` folder holds no copy; the quotation is in the 2026-10-06 verification file, which fetched it then. Nothing in the verdict depends on it: the statute and the worksheet say the same.

The report's three engine observations are outside both cells. Each matches the engine's source in policyengine-us 2.38.6 (`engine_sources.md` quotes the lines), which is as far as this record checked them: `surviving_spouse_eligible` has no test of when the spouse died (PolicyEngine/policyengine-us#10059, open); `oh_employer_subsidized_health_plan_eligible` counts having or being offered employer coverage, whether or not the employer pays; and `oh_pension_based_retirement_income_credit` says in a comment that it does not check that the pension was received on account of retirement.

## Files

`manifest.json` gives the sha256 of every file here except this README and the two test logs, the sha256 of the release's four inputs at commit `5a8164a0`, and the two engines. `tests/test_held_references.py` rebuilds it, so an evidence file that changes fails the tests.

| Path | What it is |
|---|---|
| `../held_references.json` | The standing list, with these two records |
| `report/REPORT.md` | The session's write-up, as written |
| `reviews/` | The two briefs and the two GPT-6.1 Sol reviews, as written |
| `prompt_households.json` | The two household blocks the models saw |
| `model_answers.md`, `model_answers.json` | All 47 models' answers and explanations for both cells |
| `law/excerpts.md`, `law/sources.json` | The passages relied on; each saved document's address, sha256 and recheck |
| `traces/policyengine-us-2.38.8-75cdd8019e/` | The session's engine run: listed values, situations, short traces and full traces. `rerun/` is this record's re-run on the same commit |
| `traces/policyengine-us-2.38.6/` | The same run on the release's engine |
| `scripts/trace_cells.py` | The script every run used |
| `engine_sources.md` | The engine and data-builder lines the statements about them rest on |
| `scripts/hand_derivations.py`, `verification/hand_derivations.json` | The hand derivations, executable |
| `verification/consensus_flags_20261010*.json` | The trigger on the release's payload, at the default parameters and with `--min-top 2` |
| `verification/held_on_20261010*.json` | What `adversary-prepare --held-references` lists for each |
| `scripts/build_manifest.py`, `manifest.json` | The hashes |
| `verification/pytest_held_references.txt`, `scripts/mutants_held_references.py`, `verification/mutants_held_references.txt` | The test run; and deliberate breaks of the rule and of the command, each caught by the tests |

**No whole law document is committed.** The statutes, the revenue procedure and the IRS forms are free of copyright; the Ohio booklet and the Legislative Service Commission's analysis are state publications and may not be. `law/excerpts.md` quotes the passages relied on, and `law/sources.json` gives each document's public address and the sha256 of the copy the session saved.

## Reproduce

```bash
# the engine runs (the release's engine is the locked environment)
uv run python reference_audit/2026-10-10-held-references/scripts/trace_cells.py \
  <run>/scenarios.csv <out-dir> > <out-dir>/key_variables.txt
# the hand derivations and the hashes
uv run python reference_audit/2026-10-10-held-references/scripts/hand_derivations.py
uv run python reference_audit/2026-10-10-held-references/scripts/build_manifest.py
# what a pass lists
uv run policybench consensus-flags --payload <run>/data.json.gz --output <flags>
uv run policybench adversary-prepare --payload <run>/data.json.gz --flags <flags> \
  --held-references reference_audit/held_references.json --adversary-dir <adv>
```

`<run>` is `paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace` as commit `5a8164a0` holds it. For the 2.38.8 run, install policyengine-us from commit `75cdd8019e07b54c78f0c8d077935c5dc9b14670` with policyengine-core 3.33.0.
