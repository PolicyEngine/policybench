**scenario_067 / dependent1_medicaid_eligible — verdict: `prompt_ambiguity`**

The frozen value is **1**. The relationship-only alternative is **0** if Dependent 1 is the biological, adopted, or step child of the claiming filer. The prompt calls this person “Dependent 1,” age 23, and never establishes that relationship. Another adult tax dependent can properly have a separate Medicaid MAGI household. The judge's parent-child premise is therefore an assumption, not a stated fact. Under the requested scoring standard this is an **unlisted-input exclusion**, not a demonstrated engine defect on fully specified facts.

This relationship root cause is **not an entry in `triage/root_causes.json`**, which I read without reopening its settled findings. The paper already acknowledges under-specified adult tax-dependent relationships in [its limitations](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/paper/index.qmd:1243). Its statement about historically scoring encoded inputs does not resolve the ambiguity under this investigation's supplied rule.

**Facts and reproduced mechanism.** The frozen scenario puts Head (60), Spouse (58), and Dependent 1 (23) in `adults`, with an empty `children` list. Dependent 1 has both tax-head and tax-spouse flags false, `is_disabled=true`, and $10,800 of generic `disability_benefits`. There is no parent-child link or `own_children_in_household` input. “All listed people live together” and a shared household group do not specify the relationship needed for a person-specific Medicaid household. The instruction setting unlisted numeric inputs to zero explains the engine's zero parent-count input; it does not tell the reader which family relationship “Dependent 1” represents.

I ran `pe_case.py` under 1.755.4 against the pristine frozen bundle. Both `frozen_reference` and `recomputed_baseline` were **1.0**; the full situation and calculated intermediates are in [baseline.txt](sweep/work/r067_adult_dependent_relationship/baseline.txt). These findings independently reproduce the earlier investigator's leads.

The following paths are relative to `/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/.venv-pe1755/lib/python3.13/site-packages/policyengine_us/`. I read each described formula:

| Engine file | Observed mechanism |
| --- | --- |
| `variables/household/demographic/person/is_parent.py` and `own_children_in_household.py` | `is_parent` is whether the own-child count exceeds zero; the absent count leaves all three false. |
| `variables/household/demographic/person/is_qualifying_child_dependent.py` | Its age/student test is false for this 23-year-old nonstudent. This variable explicitly excludes the separate disability exception. |
| `variables/gov/hhs/medicaid/income/medicaid_claimed_by_parent_in_tax_unit.py` | Infers a parental claimant from the qualifying-child test or any head/spouse with `is_parent=true`. Neither holds here. |
| `variables/gov/hhs/medicaid/income/medicaid_tax_dependent_exception_other_than_spouse_or_child.py` and `medicaid_uses_non_filer_rules.py` | A dependent without that inferred parental claimant triggers the other-dependent exception and nonfiler household rules. |
| `variables/gov/hhs/medicaid/income/medicaid_household_income.py` and `medicaid_household_size.py` | The adult nonfiler calculation yields Dependent 1's own $0 MAGI and size 1; the tax-household branch instead includes $87,302 and size 3. |
| `variables/gov/hhs/medicaid/income/medicaid_magi_person.py` and `medicaid_income_level.py` | Individual MAGI is `[87302, 0, 0]`; household income divided by the applicable poverty guideline produces the eligibility ratio. The generic disability benefit's taxability is not changed in this investigation. |
| `variables/gov/hhs/medicaid/eligibility/categories/adult/is_adult_for_medicaid_fc.py`, `parameters/gov/hhs/medicaid/eligibility/categories/adult/income_limit.yaml`, and `variables/gov/hhs/medicaid/eligibility/categories/medicaid_category.py` | Indiana's adult threshold is 1.38 FPL. Dependent 1 selects `ADULT` at zero income; under the child-relationship reading no category succeeds. |
| `variables/gov/hhs/chip/is_chip_eligible_child.py` and `parameters/gov/hhs/chip/child/max_age.yaml` | CHIP's child pathway requires age under 19. Changing a parent relationship does not change this person's age. |

**Law applicable in 2026.** The official [2025 edition of 42 CFR 435.603](https://www.govinfo.gov/content/pkg/CFR-2025-title42-vol4/pdf/CFR-2025-title42-vol4-sec435-603.pdf), printed April 8, 2026, precedes the July 3 freeze. Paragraph (b) defines child by biological/adoptive/step relationship without an age limit. Paragraph (f)(2) uses the claiming taxpayer's household; (f)(2)(i) is the exception for dependents other than spouse/child. Paragraph (f)(3) limits this 23-year-old's nonfiler household to self and relevant resident spouse/children; younger applicants can also include parents/siblings. Paragraph (d)(1) sums household MAGI, subject to dependent-income exclusions in (d)(2). These rules distinguish the two readings; age 23 alone cannot establish the exception.

[Indiana's Medicaid manual chapter 3200](https://www.in.gov/dA/9fcd49126c/Medicaid_PM_3200.pdf?language_id=1), pages 5–9, corroborates the distinction and specifically discusses adult children claimed by parents. Its current PDF revision date was not verified, so the official CFR edition supplies the prefreeze evidence.

[42 CFR 435.119](https://www.govinfo.gov/content/pkg/CFR-2025-title42-vol4/pdf/CFR-2025-title42-vol4-sec435-119.pdf) provides the age 19–64 adult group and 133% FPL standard. The five-point disregard in §435.603(d)(4) yields the effective 138% test. [Indiana chapter 3500, §3515](https://www.in.gov/dA/0ca2b535d9/Medicaid_PM_3500.pdf?language_id=1) confirms this HIP standard and permits HIP pending a disability determination. Its current PDF revision date is also unverified. Generic disability does not automatically foreclose MAGI coverage, and failure of the MAGI test alone does not decide all disability-based pathways.

[HHS's January 15, 2026 notice](https://www.govinfo.gov/content/pkg/FR-2026-01-15/pdf/2026-00755.pdf) publishes the $27,320 three-person poverty guideline. The child's alternative household income is **$82,360 wages + $4,942 pension = $87,302**, giving **$87,302 / $27,320 = 3.195534407 FPL**, above **1.38 × $27,320 = $37,701.60**. The sandbox returns 3.1955345 because of floating-point precision. This is not a projected-parameter dispute.

[42 CFR 457.10](https://www.ecfr.gov/current/title-42/chapter-IV/subchapter-D/part-457/subpart-A/section-457.10) separately limits CHIP's child definition to under 19. An adult child for MAGI household composition remains an adult for age-based eligibility.

**Alternative and materiality.** The [2026-only Reform](sweep/fixes/r067_adult_dependent_relationship.py) changes only `medicaid_claimed_by_parent_in_tax_unit`: adult tax dependents are interpreted as children of their claiming filer. It preserves the original formula before 2026 and restores it in 2027. This is a sensitivity assumption for missing relationships, not a proposed universal rule that all adult dependents are children. It does not alter `is_parent`, ages, income definitions, or disability-status inputs.

| Scenario 067 quantity | Frozen encoding | Adult-child reading |
| --- | ---: | ---: |
| Dependent 1 Medicaid household income | $0 | $87,302 |
| Dependent 1 Medicaid household size | 1 | 3 |
| Dependent 1 income / FPL | 0 | 3.1955345 |
| `head_medicaid_eligible` | 0 | 0 |
| `spouse_medicaid_eligible` | 0 | 0 |
| `dependent1_medicaid_eligible` | 1 | 0 |
| `head_chip_eligible` | 0 | 0 |
| `spouse_chip_eligible` | 0 | 0 |
| `dependent1_chip_eligible` | 0 | 0 |

The binary flip is material. SSI and the optional senior/disabled and SSI-recipient Medicaid pathways remain as encoded; the baseline calculates no SSI and neither category succeeds. The alternative is conditional on the specified relationship reading while retaining the separate disability-status convention, not a certification of real-world eligibility through every possible pathway.

**Full sweep.** [The CSV](sweep/out/r067_adult_dependent_relationship.csv) contains all **1,984** frozen outputs across **100** households. Exactly **two** move under the adult-child interpretation; the harness reports **zero** small nonzero deltas above its 0.000001 diagnostic floor. Scenario 112's federal refundable credits and payroll tax each differ by only −5.68×10⁻¹⁴ because of decimal/float representation; they are not relationship effects or moved outputs. No output is omitted because models answered it correctly.

| Scenario | State | Output | Frozen | Recomputed | Confirmed for this root cause? |
| --- | --- | --- | ---: | ---: | --- |
| scenario_064 | WI | `dependent1_medicaid_eligible` | 1 | 0 | Yes: the same predicate changes MAGI from $0 to $124,366.484375, household size from 3 to 5, and income/FPL from 0 to 3.215266; `ADULT` becomes `NONE`. |
| scenario_067 | IN | `dependent1_medicaid_eligible` | 1 | 0 | Yes: parental-claim predicate brings $87,302 into the size-3 household and removes adult income eligibility. |

The complete manifest scan finds four adult dependents in three households:

| Scenario/person | Age | Result of adult-child interpretation |
| --- | ---: | --- |
| 064 / dependent1 | 27 | Confirmed flip above. The prompt states disability and insurance, but no parent relationship. |
| 064 / dependent2 | 18 | Already satisfies the qualifying-child age test; the child-reading module changes nothing for this person. |
| 067 / dependent1 | 23 | Confirmed flag above. |
| 093 / dependent1 | 27 | MAGI changes from $45,000 / size 1 (2.819549 FPL) to $157,408.25 / size 3 (5.761649 FPL). Medicaid remains 0; no requested output changes. |

The 97 other households contain no adult dependents and the sweep reports no movement in them. All figures above are direct outputs in [diagnostics.json](sweep/work/r067_adult_dependent_relationship/diagnostics.json). The reform changes no Head/Spouse parent flag, minor's relationship predicate, age, disability input, or source of income. Scenario 064's baseline size 3 comes from the engine including the two under-19 family members in its nonfiler calculation; I have not adjudicated that separate family-membership approximation. Its zero-income result and high-income alternative do not depend on treating that size as established fact.

For scenario 064, [Wisconsin's BadgerCare Plus handbook §16.1](https://www.emhandbooks.wisconsin.gov/bcplus/policyfiles/3/16/16.1.htm) states a 100% FPL adult limit, including disregards; the page identifies its last update as December 18, 2024, effective January 1, 2025. The engine parameter also says 1.00. The audit prompt's generated explanation calling Wisconsin a 138% ACA expansion state is therefore inaccurate; I used the source parameter and run rather than that narrative. Its alternative MAGI is far above the actual adult limit.

The 18-year-old's opposite relationship reading exposes another affected output. The prompt calls this person **Dependent 2**, separately from **Child 1**, and does not identify a parent. The [nonchild-reading module](sweep/fixes/r067_adult_dependent_nonchild.py) sets the same Medicaid relationship predicate false for adult dependents during 2026 only. It leaves the already-nonchild readings of the other three adult dependents intact. Its [separate full CSV](sweep/out/r067_adult_dependent_nonchild.csv) covers **1,984 outputs / 100 households**, with exactly **one** moved output and no other delta above 0.000001. [The log](sweep/work/r067_adult_dependent_relationship/nonchild_sweep.txt) records the summary. The candidate diagnostics confirm:

| Scenario | State | Output | Frozen | Recomputed under nonchild reading | Confirmed for this root cause? |
| --- | --- | --- | ---: | ---: | --- |
| scenario_064 | WI | `dependent2_medicaid_eligible` | 0 | 1 | Yes: the relationship exception removes $124,366.484375 of claimant-household MAGI; own/family-child MAGI is $0 and the category becomes `OLDER_CHILD`. |

The encoded household size changes from 5 to 2; this retains the engine's broad family-child approximation. Whether the 12-year-old belongs in that nonfiler household is unverified, but both younger members have zero MAGI, so size 1 versus 2 would not change the zero-income eligibility result. An 18-year-old nonchild dependent with no resident parent of their own is one consistent alternative. [Wisconsin handbook §7.1](https://www.emhandbooks.wisconsin.gov/bcplus/policyfiles/2/07/7.1.htm), last updated April 9, 2025, says children ages 6–18 at or below 156% FPL are exempt from the current-insurance restriction. Thus the stated employer coverage does not defeat this zero-income reading. The read engine files `variables/gov/hhs/medicaid/eligibility/categories/older_child/is_older_child_for_medicaid.py` and corresponding `parameters/gov/hhs/medicaid/eligibility/categories/older_child/{age_range,income_limit}.yaml` apply age 6 through 18 and Wisconsin's 1.56 threshold. All five scenario 064 CHIP outputs remain zero in this run.

These are **different conditional readings**, not three outputs from one corrected household file. They expose three distinct Medicaid references that depend on the missing adult relationship. The primary answer for scenario 067 remains 1 under the encoded nonchild reading and 0 under the child reading. No further family-tree reconstruction is claimed.

**Upstream status.** A fresh run under the supplied **2.8.0** environment still returns 1, household income $0, and size 1 for Dependent 1; see [latest_release.txt](sweep/work/r067_adult_dependent_relationship/latest_release.txt). The relationship, exception, nonfiler, and household-income formulas are byte-identical in 1.755.4, 2.8.0, and the examined local `upstream/main`, commit `2c2e42c08f9c3a163437166c7fed398024ffb892`. Main has a separate California pregnancy-size change that does not resolve this relationship ambiguity. No main execution is claimed.

Related merged [PR #8169](https://github.com/PolicyEngine/policyengine-us/pull/8169) introduced these MAGI household formulas; this is verified from git commit `b31679c5d561f9f4a0d324049afd346c5b815047` dated April 30, 2026. A local remote-tracking branch, `upstream/medicaid-magi-parent-ids`, contains September 7 commit `875a58982e67c52d1987a6db0c195473cade840c`, adding explicit parent IDs. I read that branch's formula: it retains the current inference when IDs are absent. The branch is not in examined main; execution, live status, and a PR number are unverified. GitHub CLI issue/PR searches failed with API connectivity errors, so no claim is made that no case-specific issue exists. Exact comparisons and limitations are in [upstream.txt](sweep/work/r067_adult_dependent_relationship/upstream.txt).

**Reproduction and validation.** Run from the triage sweep directory; all outputs remain in the assigned workspace:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/opus55 \
  ../.venv-pe1755/bin/python sweep.py \
  --fix /Users/maxghenis/PolicyEngine/_wk/pb-flag-v6-067/sweep/fixes/r067_adult_dependent_relationship.py \
  --out /Users/maxghenis/PolicyEngine/_wk/pb-flag-v6-067/sweep/out/r067_adult_dependent_relationship.csv
```

[verify.py](sweep/work/r067_adult_dependent_relationship/verify.py) independently scans candidates, records baseline and alternative intermediates, checks all six scenario 067 Medicaid/CHIP outputs, compares the older parent-count perturbation, and checks 2025/2027 boundaries. **All assertions passed**; [verify.txt](sweep/work/r067_adult_dependent_relationship/verify.txt) retains the output. [sweep.txt](sweep/work/r067_adult_dependent_relationship/sweep.txt) records the complete sweep summary. The published sweep CSV has 1,984 unique scenario/output rows.

[nonchild_verify.py](sweep/work/r067_adult_dependent_relationship/nonchild_verify.py) repeats the candidate calculations for the other relationship reading and checks its 2025/2027 boundaries; all assertions passed. See [nonchild_verify.txt](sweep/work/r067_adult_dependent_relationship/nonchild_verify.txt) and [nonchild_diagnostics.json](sweep/work/r067_adult_dependent_relationship/nonchild_diagnostics.json). Reproduce the second full sweep with the command above substituting `r067_adult_dependent_nonchild.py` and `r067_adult_dependent_nonchild.csv`.

All changes are confined to this workspace. No external issue, PR, or message was posted, nothing was pushed, and no upstream file was edited. A requested commit on `flag-triage` was attempted, but the session's read-only `.git` protection rejected creation of `.git/index.lock` with `Operation not permitted`; no commit was created.
