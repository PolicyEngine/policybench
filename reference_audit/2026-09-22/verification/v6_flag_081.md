# scenario_081 / state_income_tax_before_refundable_credits

**Verdict: `reference_wrong_engine_bug`.** The stated $1,080 short-term capital loss eliminates the household's Part A dividends, but PolicyEngine 1.755.4 taxes the gross dividends. Correcting that defect alone reduces the reference from **$8,238.41 to $8,232.90**, more than the $1 tolerance. There is also an **unlisted interest-source input** (`prompt_ambiguity`): treating the $56 of interest as ordinary Part A interest gives **$8,230.10** after the same loss correction. The judge's proposed $100 Massachusetts-bank-interest exemption is wrong for 2026; it was repealed from 2024.

This root cause is not among the settled entries in `triage/root_causes.json`. No settled fix or publication convention was reapplied. Under the supplied scoring rule, the confirmed engine defect is sufficient to exclude this output for every model, irrespective of which interest-source reading is chosen.

The prompt states non-qualified dividends of $110, short-term capital gains of −$1,080, taxable interest of $56, wages of $175,002, and Massachusetts residence. It does **not** say that the interest comes from a Massachusetts bank or a qualifying deposit. Bank-account assets and residence do not establish that fact. The prompt's instruction that unlisted facts are false supports the ordinary Part A reading; the engine instead places all taxable interest in residual Part B. The frozen input contains dividends of $110.11764526367188; the prompt rounds this to $110. This rounding does not explain the material error because all dividends are absorbed under either corrected reading.

**Law applicable to 2026 and published before the freeze.** [M.G.L. c. 62 § 2(b)(1)–(2)](https://malegislature.gov/Laws/GeneralLaws/PartI/TitleIX/Chapter62/Section2) places ordinary interest and dividends in Part A, except enumerated sources including qualifying Massachusetts-bank deposits, which fall in Part B. Sections 2(c)(2)(a) and 2(c)(4) apply excess short-term capital losses against Part A interest/dividends, with a combined short-/long-term loss limit of $2,000; remaining short-term losses can reach Part C. Section 2(f) bases taxable Part A income on adjusted Part A income. [DOR TIR 02-21](https://www.mass.gov/technical-information-release/tir-02-21-capital-gains-and-losses-massachusetts-tax-law-changes), dated January 2, 2003, describes this ordering and cap, establishing the rule before July 3, 2026. The statute was read directly; the TIR's relevant text and date were read in official search-indexed text because direct retrieval was blocked.

[Acts of 2024, chapter 140, §§ 101 and 251](https://malegislature.gov/Laws/SessionLaws/Acts/2024/Chapter140), approved July 29, 2024, removes the former c. 62 § 3.B(a)(6) bank-interest deduction for taxable years beginning January 1, 2024. Thus even qualifying Massachusetts-bank interest remains taxable in Part B in 2026. No bank exemption is included in either calculation here. The $8,230.10 alternative results from the **capital-loss offset against Part A interest**, not from the repealed exemption.

[M.G.L. c. 62 § 3.B](https://malegislature.gov/Laws/GeneralLaws/PartI/TitleIX/Chapter62/Section3) supplies the $2,000 FICA deduction cap, 50%-of-rent deduction capped at $4,000, and $4,400 statutory maximum single personal exemption. The engine applies $4,400 here. As additional 2026 support, [DOR's 2026 Form 1-ES](https://www.mass.gov/doc/2026-form-1-es-estimated-tax-payment-vouchers-instructions-and-worksheets/download), official search-indexed text, identifies wages and interest/dividends as 5% income; [§ 4](https://malegislature.gov/Laws/GeneralLaws/PartI/TitleIX/Chapter62/Section4) links the Part A interest/dividend rate to the Part B rate. The exact Form 1-ES publication date was not independently verified; the loss-offset rule and repeal have the separately dated pre-freeze evidence above. No projected parameter is changed. Additional source-access details are in [law_notes.md](law_notes.md).

**Read engine mechanism.** Paths below are relative to `/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/.venv-pe1755/lib/python3.13/site-packages/policyengine_us/`:

| File | Read behavior and observed implication |
| --- | --- |
| `variables/gov/states/ma/tax/income/gross_income/ma_part_a_gross_income.py` | Adds dividends and nonnegative short-term gains; omits interest. This case returns $110.117645. |
| `variables/gov/states/ma/tax/income/adjusted_gross_income/ma_part_a_agi.py` | Calculates capital-loss offsets against interest/dividends using a $2,000 cap, then floors Part A AGI at zero. This case already returns zero. |
| `variables/gov/states/ma/tax/income/taxable_income/ma_part_a_taxable_dividend_income.py` | Uses gross `dividend_income` less unused Part B exemption, bypassing Part A AGI. This case still taxes $110.117645 of dividends. |
| `variables/gov/states/ma/tax/income/gross_income/ma_part_b_gross_income.py` | Subtracts Parts A and C from MA gross income. Omitted Part A interest remains in Part B; this case has $175,058. |
| `variables/gov/states/ma/tax/income/taxable_income/ma_part_b_taxable_income_deductions.py` | Applies the FICA/rent deductions. Its bank-interest branch is disabled because `parameters/gov/states/ma/tax/income/exemptions/interest/in_effect.yaml` is false from 2024. |
| `variables/gov/states/ma/tax/income/ma_income_tax_before_credits.py` | Taxes the dividend base at 5%, alongside Part B and other bases. `ma_income_tax_before_refundable_credits.py` then subtracts nonrefundable credits. |

The baseline `pe_case.py` run matched the frozen value exactly: **8238.40625**. Its optional diagnostic list subsequently requested a nonexistent `ma_personal_exemption` variable and exited with an error; this did not invalidate the already printed baseline. The dedicated check script uses valid variables and records complete results separately.

**Correction and alternative calculation.** Keeping interest in Part B isolates the certain error:

`Part A dividends after loss = max(0, 110.117645 − min(1,080, 2,000, 110.117645)) = 0`.

`Part B tax = (175,002 + 56 − 2,000 − 4,000 − 4,400) × 5% = $8,232.90`.

Under the ordinary Part A interest reading, the loss covers $166.117645 of dividends plus interest. Part A tax is again zero, while Part B becomes:

`(175,002 − 2,000 − 4,000 − 4,400) × 5% = $8,230.10`.

The extra reduction from interest classification is $2.80. Thus $8,232.90 is the correction holding the engine's source assumption constant, and $8,230.10 is the correction under the prompt's no-unlisted-exception reading. Neither value deducts remaining capital loss against wages. Both exceed the $1 materiality threshold relative to the frozen reference.

**Sandbox artifacts.** [sweep/fixes/ma_part_a_loss_offset.py](sweep/fixes/ma_part_a_loss_offset.py) connects the existing loss-adjusted Part A AGI to the dividend tax base and updates the accompanying dividend/gain exemption allocation. It retains interest in Part B. [sweep/fixes/ma_part_a_ordinary_interest.py](sweep/fixes/ma_part_a_ordinary_interest.py) adds the ordinary Part A interest interpretation. Both use `Reform`, inherit Massachusetts applicability, and return the original formulas outside 2026. These are independent narrow modules, not adoption of the earlier investigator's unverified broader reform.

The modules preserve existing AGI/netting logic. They are verified for the reached household and simple loss/rate controls, not a complete Massachusetts implementation: mixed positive long-term gains and short-term losses, collectibles, carryovers, and mixed exempt/bank-interest sources require broader handling. None is present in the only Massachusetts household. The ordinary-interest variant explicitly assumes all its taxable interest is ordinary Part A interest.

**Full sweep and every moved output.** [sweep/out/baseline.csv](sweep/out/baseline.csv) reproduces all **1,984 original frozen CSV values exactly** when both are read with Python's `float`. The two reform sweeps each move **one output**; the other **1,983 recomputed values equal the no-fix run exactly**. Both moved rows are shown below; they are the same output under two treatments, not two different exclusions.

| Reform / interpretation | Scenario | Output | Frozen | Recomputed | Delta | Confirmed? |
| --- | --- | --- | ---: | ---: | ---: | --- |
| Dividend defect only; retain Part B interest | scenario_081 | state_income_tax_before_refundable_credits | 8238.40625 | 8232.900390625 | −5.505859375 | Yes: Part A dividend base falls from 110.117645 to 0; Part B taxable income remains 164658. |
| Same defect + ordinary Part A interest reading | scenario_081 | state_income_tax_before_refundable_credits | 8238.40625 | 8230.1005859375 | −8.3056640625 | Yes, conditional on that source reading: Part A interest/dividends are absorbed; Part B taxable income falls to 164602. |

Complete results: [dividend-only CSV](sweep/out/ma_part_a_loss_offset.csv), [ordinary-interest CSV](sweep/out/ma_part_a_ordinary_interest.csv), and [sweep summary](sweep/out/sweep_summary.json). The sub-cent differences from the arithmetic amounts are the engine's floating-point representation. The harness's pandas parsing introduces −5.684341886080802e−14 deltas for `scenario_112` federal refundable credits and payroll tax in **all three** CSVs, including baseline. These are unchanged parsing artifacts, not moved outputs or reform effects; comparison directly with the original frozen CSV confirms this.

The scan of all 100 scenario records found **only scenario_081 in Massachusetts**. It has no long-term gains/losses, U.S.-government interest, or collectible gains. Every other state's outputs and every other output for scenario_081 remain unchanged, including federal tax and refundable credits. The reform therefore has no unconfirmed spillover in this bundle and no additional Massachusetts household left unexamined. This is a scan of this frozen population, not a claim of general coverage for all Massachusetts households.

[sweep/check_ma_part_a.py](sweep/check_ma_part_a.py) passed baseline reproduction, both corrected values, five controls (the $2,000 cap, partial short-term loss, no loss, positive short-term gain, and a long-term loss remaining after short-term gains), and unchanged nonzero 2025/2027 results. [sweep/out/checks.json](sweep/out/checks.json) contains the intermediate variables and assertions' results; [checks.log](sweep/out/checks.log) records successful completion. Run it from this workspace with:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/opus55 /Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/.venv-pe1755/bin/python sweep/check_ma_part_a.py
```

Reproduction commands, run from the triage sweep directory, with all outputs in this workspace:

```sh
cd /Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/sweep
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/opus55 ../.venv-pe1755/bin/python sweep.py --out /Users/maxghenis/PolicyEngine/_wk/pb-flag-v6-081/sweep/out/baseline.csv
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/opus55 ../.venv-pe1755/bin/python sweep.py --fix /Users/maxghenis/PolicyEngine/_wk/pb-flag-v6-081/sweep/fixes/ma_part_a_loss_offset.py --out /Users/maxghenis/PolicyEngine/_wk/pb-flag-v6-081/sweep/out/ma_part_a_loss_offset.csv
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/opus55 ../.venv-pe1755/bin/python sweep.py --fix /Users/maxghenis/PolicyEngine/_wk/pb-flag-v6-081/sweep/fixes/ma_part_a_ordinary_interest.py --out /Users/maxghenis/PolicyEngine/_wk/pb-flag-v6-081/sweep/out/ma_part_a_ordinary_interest.csv
```

All runs use the pristine `results/local/newmodels/publish/us_full_run_20260612_policyengine_4_16_1_populace/us` bundle. The reference CSV SHA-256 is `b9136a15e285f9c02ba78bee854b8a3af180e280485512642c829e8ffd7d2368`.

**Upstream status.** Release **2.8.0 still returns 8238.40625**, confirmed by a successful run in [latest_081_run.txt](latest_081_run.txt). The four central formulas are byte-identical in 1.755.4, 2.8.0, and read-only `upstream/main` at `2c2e42c08f9c3a163437166c7fed398024ffb892`. Neither inspected release nor main fixes this defect. [upstream_notes.md](upstream_notes.md) records paths, hashes, and commands.

Related local history identifies [PR #5564](https://github.com/PolicyEngine/policyengine-us/pull/5564) / [issue #5562](https://github.com/PolicyEngine/policyengine-us/issues/5562) for the 2024 Massachusetts parameter update, including repeal of the bank exemption, and [issue #6968](https://github.com/PolicyEngine/policyengine-us/issues/6968) for a separate short-term-loss-to-long-term-gain correction. These references were read in local commit history, not current GitHub discussions. **A current issue/PR for this exact defect is unverified**: the GitHub API search failed and web retrieval did not supply matching coverage. No claim that no issue exists is made.

Only files in the assigned workspace were written; no issue, PR, comment, or push was made. **Commits are blocked by the environment:** `.git` is read-only and `git add`/`git commit` failed creating `.git/index.lock` with `Operation not permitted`. The assigned branch remains `flag-triage`; history was not rewritten. All deliverables remain available as workspace files.
