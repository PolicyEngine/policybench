SHIP AFTER FIXES

1. **Blocker — CONFIRMED: SNAP arithmetic defects remain scored under a publication convention.**  
   [paper/index.qmd:1069](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/paper/index.qmd:1069) treats statutory rounding corrections as grounds to regenerate references. But [r13_hold_fy2026_v2.py:77](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/reference_audit/2026-09-22/fixes/r13_hold_fy2026_v2.py:77) fixes an existing arithmetic defect, independently of projected parameters.

   **Evidence:** In policyengine-us 1.755.4, ran a `Reform` updating only `snap_expected_contribution` and `snap_net_income`, leaving parameters unchanged:

   | SNAP scenario | Original reference | Rounding-only result | Change | Currently excluded |
   |---|---:|---:|---:|---|
   | 008 | $15,246.9053 | $15,243.3076 | −$3.5977 | No |
   | 012 | $4,952.0894 | $4,942.7896 | −$9.2998 | No |
   | 054 | $6,125.6890 | $6,118.7900 | −$6.8989 | No |
   | 109 | $8,020.5542 | $8,017.5542 | −$3.0000 | No |

   **Smallest fix:** Separate rounding defects from the parameter convention; sweep the isolated defect across all references; exclude every >$1 mover, restore its original frozen value, and rescore/refreeze the publications.

2. **Major — CONFIRMED: the CalEITC fix cites the wrong upstream PR.**  
   [paper/index.qmd:1067](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/paper/index.qmd:1067) and [root_causes.json:148](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/reference_audit/2026-09-22/root_causes.json:148) attribute the missing AGI comparison to #9542.

   **Evidence:** Retrieved and read the upstream PR diffs through `github_fetch_pr`. [#9542](https://github.com/PolicyEngine/policyengine-us/pull/9542) changes the **2024 eligibility boundary from $31,950 to $31,951**, plus references and tests. [#9363](https://github.com/PolicyEngine/policyengine-us/pull/9363), merged **September 1**, implements the earned-income/AGI credit comparison.

   The same paper sentence says the remaining defects “are reported,” while committed exclusion entries say “to be filed,” for example [reference_exclusions.json:185](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/reference_exclusions.json:185). That claim lacks recorded issue links.

   **Smallest fix:** Replace #9542 and its date with #9363/September 1 throughout the records; describe remaining reports as pending unless actual links are supplied.

3. **Minor — CONFIRMED: “most … never flagged” reverses the recorded proportions.**  
   [paper/index.qmd:1067](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/paper/index.qmd:1067) and [the audit note:7](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/app/src/notes/2026-09-22-reference-audit.json:7) make this claim.

   **Evidence:** Joined engine-defect exclusions to adjudications on `(scenario_id, variable)`, filtering `judge_reference_suspect`:

   ```text
   engine-defect outputs: 31
   flagged: 22
   never flagged: 9
   roots touching flagged outputs: 11 of 12
   ```

   **Smallest fix:** Say “the sweep identified nine additional outputs that had never been flagged.”

4. **Minor — CONFIRMED: sensitivity prose retains stale values and a wrong scored-failure count.**  
   Recomputed with `canonical_filtered_scores` using committed predictions and frozen references:

   - [paper/index.qmd:1020](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/paper/index.qmd:1020): Fable 5.1’s uplift is `91.2878185 − 90.4271661 = 0.8606524`, hence **0.9 points**, not 1.2.
   - [sensitivity document:51](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/sensitivity/claude-thinking-2026-08.md:51): Sonnet’s all-output score is **80.254155**, rounding to **80.3**, not 80.2.
   - [sensitivity document:60](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/sensitivity/claude-thinking-2026-08.md:60): only **55 of 56** parse failures contribute scored misses. `scenario_008/payroll_tax` is excluded.
   - [sensitivity document:141](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/sensitivity/claude-thinking-2026-08.md:141): Fable 5.1’s board advantage over Fable 5 is **6.759856**, rounding to **6.8**, not 6.7.

   **Smallest fix:** Correct these values and the failure-count wording; derive the paper’s uplift from the sensitivity data, then rerender.

5. **Minor — CONFIRMED, pre-existing: cost provenance describes the opposite priority from the code.**  
   [Methodology.tsx:247](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/app/src/components/Methodology.tsx:247) says provider-reported costs take priority. [eval_no_tools.py:550](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/policybench/eval_no_tools.py:550) selects reconstructed costs whenever available.

   **Evidence:** Summed the frozen prediction cost columns for DeepSeek V4 Pro 0813:

   ```text
   provider_reported_cost_usd: $12.378115
   reconstructed_cost_usd:     $19.865589
   total_cost_usd:             $19.865589
   ```

   **Smallest fix:** Describe the actual priority consistently in Methodology and the paper’s cost caption. This paragraph predates the branch but lies within the assigned review scope.

6. **Minor — CONFIRMED: two README reproducibility assertions need narrower wording.**  
   [README.md:13](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/reference_audit/2026-09-22/README.md:13) says every module is limited to 2026. However, [the IRS convention:42](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/reference_audit/2026-09-22/fixes/r19_irs_sales_tax_convention.py:42) explicitly updates 2025, as does the California convention.

   [README.md:14](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/reference_audit/2026-09-22/README.md:14) says the unmodified harness reproduces every frozen reference. Comparing the saved baseline sweep with HEAD instead returned:

   ```text
   baseline/current outputs: 1984 / 1984
   changed: 23
   changes over $1: 18
   ```

   **Smallest fix:** Say the modules were evaluated on the 2026 bundle, and that the baseline reproduces the **pre-audit July 3 references**.

7. **Minor — CONFIRMED: the manifest retains an obsolete response-window endpoint.**  
   [manifest.json:180](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/paper/snapshot/20260501/manifest.json:180) says collection ended September 1; its `model_response_date` correctly ends September 22. Local Sol/Luna run-state timestamps confirm September 22 collection.

   **Smallest fix:** Replace the hard-coded endpoint in [freeze_snapshot.py:1383](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/scripts/freeze_snapshot.py:1383) with the recorded response window and regenerate the manifest.

8. **Nit — CONFIRMED: changed audit prose uses avoidable passive voice.**  
   [The audit note:6](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/app/src/notes/2026-09-22-reference-audit.json:6) says “Each flag was settled.”

   **Smallest fix:** “Developers settled each flag.”

Checks that found no discrepancies:

- Recomputed the published top-model scores and unrounded ranks; both new notes’ numeric fact dictionaries match the frozen data.
- Verified the recorded counts: **42 models; 55 exclusions = 31 engine defects + 24 unlisted inputs; 12 defect roots; 1,929 scored outputs; 23 regenerated references = 14 SNAP + nine tax; nine conventions, eight nonempty; 61 adjudications**.
- Verified annotation counts: **7,493 scored annotations, 7,489 exact misses, four exact hits, and 1,842 additional unannotated bounded-score misses**.
- Recomputed all **14 paper tables** in memory; their rendered cells match. All **18 rendered-artifact hashes** match, and regenerating the scatter figure in memory produced the identical PNG hash.
- Verified sensitivity headline scores, ranks, per-program tables, costs and latency; the discrepancies above are in prose.
- Read the adjudication flag-clearing/freezer mechanisms and upstream #8839/#9301 diffs; their described behavior is supported.
- **141 Bun tests passed.** Targeted Python runs produced **88 passes**; nine temporary-file-dependent tests were blocked by the read-only sandbox. The full 841-test suite was not reproduced.
- Snapshot date, reference-freeze date and dataset version **1.1** agree. Historical Models API creation dates and live release availability remain independently unverified.
- Working tree remained clean; no files were edited.