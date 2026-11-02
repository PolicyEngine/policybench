**Verdict: APPROVE WITH NITS.** The engine mechanism is right, and so are the figures, the class counts and the model descriptions. The caveat is that I could not run the tests, the scripts or `git diff`. This session only had read-only file tools (no shell, no Write). I checked those items by reading the code and the committed records instead; the limits are listed at the end.

## Blocking findings

None.

## Should fix (not blocking)

**1. A third copy of the wrong mechanism sits in tracked code, and the README doesn't mention it.**
- README:43 says the judge's prompt "stated the wrong mechanism twice": the grounding line and the old reference explanation.
- There is a third copy. The judge instructions use it as their example of a good diagnosis, so it appears in every case's prompt (`prompt.md` line 5). It comes from `policybench/audit.py:295-297`: *"never applied the aged/disabled income test, which deducts the Medicare Part B premium from countable income"*.
- `tests/test_audit.py:665-669` repeats it as a passing example.
- I checked the annotations: no other `*_medicaid_eligible` row or case note relies on a Part B deduction. So the published damage is limited to this cell, but future audit stages will keep priming judges with the false rule.
- **Fix:** add it to "Where the old mechanism came from". Either change the example in `audit.py` and `test_audit.py` now (for instance "…which applies the state's income disregard"), or split that change into its own task with a link.

**2. The README cites a file that doesn't exist.**
- README:83 cites `verification/independent_review.md`, but the file is not at HEAD.
- **Fix:** commit this review as that file, or drop the line.

**3. claude-sonnet-4.6's subtype doesn't match a near-identical row.**
- claude-sonnet-4.6 is `taxable_income_or_deductions`, but glm-5.3 is `categorical_eligibility`.
- The new sonnet-4.6 text says *"its explanation settled on the expansion test, with gross income of $23,853 against $20,783"*. Its response agrees: *"Given that PolicyEngine typically implements the standard ACA Medi-Cal expansion at 138% FPL and the income exceeds that threshold…"*
- glm-5.3 made the same error (expansion limit, gross income, understated 138%) and is classed `categorical_eligibility`.
- Under the old mechanism, sonnet-4.6's income-counting subtype rested on the missed Part B deduction. Under the corrected mechanism, its main error is choosing the wrong pathway.
- **Fix:** reclassify it to `categorical_eligibility`, making the counts 28/4/3/8; no score changes. Or state in README:62 why it stays.
- gpt-5.5 (tested against a "spend-down standard") is a weaker version of the same question.

**4. A manifest note is now false for this cell.**
- `manifest.json:24` says developer adjudications are applied before export *"so the published payload and the frozen annotations agree."*
- For this cell they no longer agree until a data release re-exports. README:71 says so; the manifest doesn't.
- **Fix:** add a sentence to the manifest note, or list the divergence somewhere a release driver checks.

## Nits

- **"Holds only if the disregard is skipped" overstates** (rows gemini-3.7-flash, gpt-5.6-luna, gpt-5.6-sol). Against the engine's limit, income stays over with any monthly disregard below about $152.39, SSI's $20 included. Two of these models also named no threshold. Suggested wording: "holds against the engine's limit only if the $230 disregard is skipped or replaced by a smaller one, such as SSI's $20."
- **gemini-3.5-flash:** "*elsewhere it cited gross income of $23,853*". That figure isn't in this output's explanation (*"The head's monthly income exceeds the 138% Federal Poverty Level threshold…"*). It presumably comes from another output in `raw_response`, which I could not read. Name the source ("in its SNAP explanation"), or drop the clause.
- **deepseek-v4-pro:** "about $1,757.79" puts "about" before an exact figure.
- **claude-fable-5:** "applied no disregard … and said even SSI-style disregards would leave it over" reads as self-contradictory. Try: "assumed no specific disregard, saying even SSI-style disregards would leave it over."
- **Reference explanation:** "within the limit of 138% of the 2026 federal poverty guideline for one person, $22,024.80" reads as if the guideline itself is $22,024.80. Try: "within the $22,024.80 limit (138% of the 2026 guideline for one person)."
- **Case note:** "or missed that age alone gives the head a category" also covers glm-5.2 and grok-4.3. Those two ruled the head out on Medicare grounds, so "or treated Medicare eligibility or the lack of SSI or disability as disqualifying" is more accurate.
- **README:17 is incomplete.** `is_medicaid_eligible` also ANDs the federal and Arkansas work-requirement gates, and ORs in `ca_ffyp_eligible` and `il_hbi_eligible` (`is_medicaid_eligible.py:46-54`). Neither changes anything for this head: the work requirement applies only to the ADULT and 1115 categories. Add "(plus work-requirement gates that don't apply here)".
- **README:62:** "compared income with no exclusion or disregard with the limit" uses "with" twice. Try: "compared income, with no exclusion or disregard, against the limit."
- **`engine_values.py`** never records `immigration_status`, so the "default CITIZEN" claim isn't backed by the record. The code supports it: `immigration_status_str.default_value = CITIZEN`, which feeds `immigration_status`. Add it to `PERSON_VARIABLES`.
- **`payload_diff.py:126`** checks `{p[1] for p in reproduction}` without first checking `p[0] == "modelStats"`. A difference in another section whose index happened to equal claude-fable-5's would pass unnoticed. Assert `p[0] == "modelStats"` too.
- **The test doesn't pin subtypes.** `test_rewritten_rows_keep_their_classes` checks `failure_source` and `reference_suspect` but not `failure_subtype`, which the README says is unchanged. Pin the 29/4/3/7 tally, or the per-row subtype.
- **`KEYS`/`FIELDS` are duplicated** between `apply_rewrites.py` and the test. This is minor drift risk.
- **The release drivers don't re-apply the ledger.** The next release that rebuilds annotations from stage verdicts will fail the test until someone runs `apply_rewrites.py` by hand. That is acceptable as a tripwire, but a one-line note in the release driver or its docs would help.

## What I checked and found correct

**Engine (policyengine-us 2.15.17 source):**
- **The $230 replaces the $20; it is not added.** `_apply_ssi_exclusions.py:26`: `general_exclusion = p.general if general_exclusion is None else general_exclusion`. `_apply_medicaid_optional_senior_or_disabled_exclusions.py:73-79` passes `general_exclusion=income_disregard` for every state except CT and MO.
- **Disregard:** CA = 230 per month (`disregard/individual.yaml:26-27`).
- **Income limit and test:** CA = 1.38 from 2021 (`limit/individual.yaml:29-31`), applied as `limit_pct * unit_fpg`. The test is `income <= income_limit`, so "at or under" is right.
- **Asset test:** CA = 130,000 from 2026-01-01, tested as `assets < asset_limit`, so "below" is right.
- **Countable income formula:** it adds `ssi_marital_unearned_income`, income deemed from an ineligible parent, and ISM. Spousal deeming is added after the disregard. All of this matches README:19-24.
- **Category:** `is_optional_senior_or_disabled_for_medicaid` is aged/blind/disabled AND income AND assets. `is_ssi_aged` is `age >= aged_threshold`, which is 65.
- **Medicare bar:** `is_adult_for_medicaid_nfc` is `age_eligible & ~medicare_eligible & ~ssi_excluded`. `medicaid_work_requirement_eligible` uses Medicare as an exemption. I spot-checked the parent, young-adult, pregnant, medically-needy, SSI-recipient and immigration formulas plus the buy-in and 1115 categories: none reads `is_medicare_eligible`. I could not grep the whole directory (the venv's `.gitignore` hides it from ripgrep).
- **Immigration default:** CITIZEN, via `immigration_status_str`.

**Arithmetic:**
- $23,853.47 − $2,760 = $21,093.47.
- 1.38 × $15,960 = $22,024.80, or $1,835.40 a month.
- Margin under the limit: $931.33. Gross over the limit: $1,828.67. Gross less only the $20 exclusion: $23,613.47.
- Gross is about 149% of the 2026 guideline.
- 1.38 × $15,650 = $21,597 (the 2025 figure).
- 1.38 × $15,060 = $20,783 (sonnet-4.6's figure).

All of these agree with the committed `engine_values.json`.

**Model descriptions:** I checked all 43, not just a sample, against each model's explanation as embedded in the stage judge prompt (`results/local/gpt61sol-stage/.../us__scenario_031__head_medicaid_eligible/prompt.md:76-203`). Every quote and figure matches, apart from the gemini-3.5-flash clause above. Examples:
- claude-fable-5: ~$1,890 a month, ~$1,800 limit.
- glm-5.3: "~199% FPL", ~$1,600.
- qwen-3.7-max: "typical aged/blind/disabled Medicaid limits".
- claude-opus-4.8: "well below the threshold. Wait—…100% FPL".

**Classes:**
- All 43 rows are `llm_error` with `reference_suspect=False`.
- The subtype counts are 29/4/3/7, matching the README.
- The README's 17/2/2/8 split of the 29 checks out row by row.
- `rewrites.json` carries only text fields, and the test enforces that.

**Tooling:**
- `apply_rewrites.py` refuses a missing or non-unique key, refuses a text that is neither old nor new, and requires a byte-for-byte CSV and manifest round-trip.
- `--check` writes nothing and fails on stale hashes.
- The manifest pins the three files under `audit_annotation_artifacts.files`.
- `payload_diff.json` shows only the scenario_031 cell's three text fields changing (43 + 43 + 46 paths). The base rebuild matches the frozen `data.json.gz` except four carried claude-fable-5 usage fields. That is good evidence that no score changes, and `paper_results.py` reads only classes from these files.

## Not verified: rerun before merge

I could not execute anything, so these are still open:
- the pytest command and `apply_rewrites.py --check`;
- the `engine_values.py` rerun and the `git diff` of its output;
- `git diff origin/main` (that only the 45 fields and 3 hashes changed, and the frozen run dir is untouched);
- `raw_response` in `predictions.csv.gz`, which is gzipped. I read model behaviour from the explanation text in the judge prompt instead.
- the README:62 corpus tally ("97 rows… one `state_local_rule`").