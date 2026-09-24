# Reference audit, September 22, 2026

This directory records how the September 22 references and exclusion record were built for the 42-model board: release `dashboard-data-20260922`, and its revisions of 2026-09-24 for one more engine defect (below). Release `dashboard-data-20260922b` excluded the one output that defect moves while its fix was open upstream; release `dashboard-data-20260922c` regenerates that output with the fix, which merged the same day. The current record has 26 regenerated references and 52 outputs excluded from scoring for every model, 41 of them added in this audit on 2026-09-22. The references come from policyengine-us 1.755.4 for tax year 2026, frozen on 2026-07-03.

## The rules

1. A scored reference follows from the stated facts and from law published before the 2026-07-03 freeze (Max, 2026-09-22). Where the engine projected a 2026 parameter with a price index, a publication convention regenerates the reference with the amount published before the freeze, or with the last amount published. A convention changes parameter values only.
2. An engine defect fixed in policyengine-us after the freeze is regenerated with its fix, on the same engine version (Max, 2026-09-23). Eight root causes qualify: `r04` (#8839), `r09` (#9301 and #9313), `r17` (#9363), `r26` and `r27` (#9318), `r28` and `r31` (#9162), and, from release `dashboard-data-20260922c`, `r33` (#9586).
3. An engine defect not fixed upstream excludes every output its fix moves by more than $1.
4. A reference that turns on an input or definition the prompt never states is excluded.

## What is here

- `root_causes.json` holds each root cause and publication convention: its class, the defect or unlisted input, the law, the alternative reading, the upstream status (`upstream_fixed: true` for rule 2) and, for a defect measured on top of other sources, `measured_against`. Classes:
  - `engine_defect`: the engine misapplies the law on facts the prompt states.
  - `unlisted_input`: the reference turns on an input or definition the prompt never states.
  - `convention`: a publication convention (rule 1).
  - `superseded`: withdrawn, with the reason.
  - `regenerated`: the first SNAP rule, as recorded before the conventions generalized it; its note records how it was superseded.
- `fixes/` holds the sandbox modules. Each is a `policyengine_core` Reform or a situation patch on policyengine-us 1.755.4, evaluated for tax year 2026. The IRS sales tax, California, Idaho, Maryland, Minnesota, Michigan and Missouri conventions also set the 2025 amounts their held 2026 values carry forward. `r06` has no year guard, so it applies from 2025, when Wisconsin's retirement subtraction begins, and `r04_capital_gain_distributions.py`, a faithful backport of #8839, applies in every year, as upstream does.
  - The `_v2` modules are the independently verified revisions.
  - `r04_capital_gain_distributions.py` is the faithful backport of upstream #8839 and regenerates the r04 references. The verified `r04_capital_gain_distributions_v2.py` also extended Wisconsin's capital gain exclusion to the distributions, which #8839 does not; that part is `r32_wi_capital_gain_distributions.py`, a defect not fixed upstream.
  - `r13_hold_fy2026_v2.py` is the superseded first SNAP module, which mixed the FY2026 hold with formula corrections. `r13_hold_fy2026_v3.py` is its hold alone, and the corrections are `r26`, `r27`, `r28` and `r31`, all fixed upstream.
  - The `c13v3_*` modules combine the SNAP convention with a SNAP fix, to measure the fix on top of the convention. `c13v3_upstream_plus_r30.py` measures r30 against the published SNAP value instead (the convention with every upstream SNAP fix, `c13v3_plus_upstream_snap.py`); it moves the same two outputs. `c13v3_plus_upstream_snap.py` holds the SNAP fixes merged before #9586; with r33 added, `c13v3_upstream_plus_r33.py` is the SNAP configuration the references now apply.
  - `cwi_plus_r04.py` combines the Wisconsin convention with #8839, the baseline r32 is measured against, and `cwi_plus_r04_r32.py` adds r32.
  - `r29_*` are the net-income sensitivity readings. From release `dashboard-data-20260922c` the sensitivity combines them with r33 (`c13v3_r26_r28_r33`, `c13v3_r28_r29n_r33`, `c13v3_r28_r29c_r33`), as the references do; r33 moves only scenario_045 SNAP, to $0 under every procedure.
  - `r18_hold_all_projections.py` is the projection screen: it holds every projected 2025–2026 parameter at its last encoded value.
- `sweep_moves.csv` lists every output each module changes when all 1,984 references are recomputed under it.
  - `baseline` is the value the module is measured against, named by `measured_against`: the frozen reference (`frozen`); for the SNAP defects, the SNAP convention's reference (`c_snap_hold_fy2026`); for r32, which only matters once the distributions reach federal AGI, the Wisconsin convention plus #8839 (`c_wi_published_2026+r04_capital_gain_distributions`). That combination's own rows are listed with class `baseline`, so each r32 baseline can be checked.
  - `moved_over_1` marks changes over the $1 exact-match tolerance, or a flipped flag.
  - The unmodified harness reproduces all 1,984 pre-audit references frozen on 2026-07-03.
- `snap_net_income_sensitivity.csv` recomputes SNAP on top of the convention with the rounding fixes and r33, under three net-income procedures in every state: the engine's floor, the nearest dollar (as upstream #9318 does), and cents kept (7 CFR 273.10(e)(1)(ii)). No scored output differs by more than the dollar tolerance between the nearest-dollar and cents-kept readings.
- `scripts/` holds the tools that build the records:
  - the harness, `sweep.py` and `run_one.sh`;
  - the records builder, `build_records.py`, which writes `reference_exclusions.json` and `us_adjudications.json`;
  - the regeneration script, `regen_references.py`, which writes `reference_outputs.csv` and its sidecar;
  - the on-convention measurement, `make_on_convention.py`;
  - this package's builder, `package_audit.py`.

  They run against the local results tree and a policyengine-us 1.755.4 environment; their paths are the ones used on 2026-09-22 and 2026-09-23.
- `verification/` holds the independent reports:
  - `v1`–`v4`: GPT-6 Astra lanes re-derived each first-pass fix from primary sources and reran its sweep.
  - `v5a`, `v5b`: sourced every projected parameter behind a moved output.
  - `v6`: settled the three reference flags the September 22 judge raised on scored outputs.
  - `v7`: the adversarial reviews of the first refreeze. They found that the first SNAP convention module also corrected the engine's SNAP arithmetic.
  - `v8`: the Axiom rules engine's encoding of the SNAP allotment and minimum-benefit rounding (7 U.S.C. 2017(a)), given the engine's household size, eligibility and floored net income, against the rounding-only sandbox for the 19 households the first SNAP module changed, January to September; it does not test net income rounding. Also the rounding procedures in the state SNAP manuals for the states with affected households.
  - `v9`: read-only Axiom encoding-preparation lanes. Each checked whether Axiom encodes a defect's governing provision and derived the affected households' values from the statute text.

## How the records follow

1. An output moved only by upstream-fixed defects (and conventions) is regenerated. The regenerated value applies every convention and upstream fix together.
2. Any other output an engine defect moves by more than $1 is excluded. The exclusion names the defects not fixed upstream and records:
   - the frozen value;
   - the corrected value: the output's unfixed defects' fixes applied together on top of every publication convention and upstream fix, as the published references are;
   - the law and the upstream status.

   The SNAP defects are measured against the SNAP convention's reference, and r32 against the Wisconsin convention plus #8839: the value that would otherwise be published.
3. An unlisted-input root cause excludes every output its alternative reading moves, with the alternative value, computed the same way. An output that moves under both an unfixed defect and an unlisted input is recorded as the engine defect, and the note names the unlisted input. An exclusion carried over from 2026-09-05 keeps its classification; its alternative value is recomputed with every convention and upstream fix (the unlisted readings are the `u_*` situation patches), and its note names a defect not fixed upstream that also moves it. The later SNAP defects also move two such outputs, 023 and 100.
4. The reference sidecar (`reference_outputs.csv.meta.json`) lists one revision per convention and per upstream fix. Each revision lists the outputs that source changes, with its module's sha256 and, for a fix, the upstream pull request. An excluded output keeps its frozen value.
5. Every reference flag the September 22 judges raised carries a developer adjudication: `affirmed`, `regenerated`, `engine_defect` or `unlisted_input`.

## Revision of 2026-09-24: SNAP child support treatment (`r33`, release `dashboard-data-20260922b`)

`r33_snap_child_support_treatment` was recorded on 2026-09-24 as an engine defect not fixed upstream, so rule 3 applied and release `dashboard-data-20260922b` excluded the one output it moves for every model. Its fix merged the same day; the next section records release `dashboard-data-20260922c`, which regenerates the output under rule 2. This section describes the record as it stood for release `dashboard-data-20260922b`.

- **Defect.** policyengine-us reads `gov.usda.snap.income.deductions.child_support` as the state option in 7 CFR 273.9(c)(17): when it is true, `snap_child_support_gross_income_deduction` and `snap_gross_test_income` take legally obligated child support paid to nonhousehold members out of gross income. When it is false, `snap_child_support_deduction` deducts the payments from net income, as 7 CFR 273.9(d)(5) requires of a state that does not take the option. The parameter's values carry the opposite meaning. For 2026, 1.755.4 excludes the payments from gross income in 37 jurisdictions that USDA's 17th SNAP State Options Report lists as deducting them, and deducts them in 9 of the 14 it lists as excluding them. Michigan is a deduction state in the 16th edition ("Treatment of Child Support Payments", p. 15) and the 17th (p. 21), as in the 14th. The 15th, which reports FY 2023 choices, lists it as an exclusion state; policyengine-us#9586 found no Michigan policy that adopted an exclusion for FY 2023 and keeps Michigan a deduction state in every year. Michigan's Bridges Eligibility Manual 556 (11-1-2025) enters child support at line 20, after gross income at line 10. The engine excludes it from gross income.
- **Upstream.** For release `dashboard-data-20260922b` the fix was open: PolicyEngine/policyengine-us#9586, head `3f156660320436e02258a94b40bc6e7ba1d7208e`. It changes the parameter's values and no formula.
- **Fix modules.** For release `dashboard-data-20260922b`, `fixes/r33_snap_child_support_treatment.py` embedded that head's `child_support.yaml` verbatim (it now embeds the merged file; see the next section): all 53 jurisdictions and every dated value. It replaces each jurisdiction's history from 2010-01-01. The reformed system's parameter matches the YAML value for value in every jurisdiction, and it changes the 2026 value in 46 jurisdictions. `fixes/c13v3_plus_r33.py` adds r33 to the SNAP convention, and `fixes/c13v3_upstream_plus_r33.py` adds it to the convention plus every upstream SNAP fix (the SNAP value actually published).
- **Sweep.** All 1,984 references were recomputed under each module. The four households that list child support paid are 014 (WV), 015 (IN), 045 (MI) and 074 (LA). On the frozen engine, r33 alone changes one output, `scenario_045` SNAP, from 287.68 to 0. On the SNAP convention it changes the same output, from 286.08 to 0. On the published SNAP configuration it again changes only that output, from 288.00 to 0. Every other output is unchanged to the cent under all three. `sweep_moves.csv` records the move against the SNAP convention (`measured_against` `c_snap_hold_fy2026`, as for r30), and `make_on_convention.py` writes both measurements.
- **The household.** The Michigan household is one person with $5,200 a year of child support paid and no elderly or disabled member. With the payments excluded, SNAP gross income is $2,589.63 a month, 198.6 percent of the poverty guideline in January. That is within the 200 percent gross limit of Michigan's broad-based categorical eligibility, so the household is eligible and receives the $24 monthly minimum. With the payments counted, gross income is $3,022.97, 231.8 percent of the guideline. The household is then not categorically eligible, fails the 130 percent gross income test, and receives $0. Net income is $1,102 a month either way.
- **Record.**
  - `scenario_045` SNAP is excluded as `reference_engine_defect`, root cause r33, decided 2026-09-24. The exclusion names r28, fixed upstream, as also moving the output.
  - An excluded output keeps its frozen value, so its reference returns from the regenerated 288.00 to the frozen 287.68.
  - The frozen bundle's derivation narrative for that value called the annual $287.68 a monthly benefit and an average, credited the October minimum to changes in the standard and shelter deductions, and left out the child support the engine subtracts from gross income. `scripts/regen_references.py` rewrites it from the frozen engine's trace, as for 080 and 091: `FROZEN_NARRATIVES` holds the engine facts, `FROZEN_REQUIRED` the figures it must state ($433.33 and $287.68), and `HAND_CORRECTED` the published text, which replaces a writer draft that credited the October change to the poverty guideline. The narrative attributes the exclusion to PolicyEngine's child support parameter and sums the twelve monthly minimums, $23.84 for nine months and $24.3744 (8% of the projected $304.68 maximum) for three, to $287.68. `tests/test_reference_audit.py` checks it against the committed tables.
  - The sidecar's `c_snap_hold_fy2026` and `r28_snap_min_allotment_rounding` revisions no longer list the output. No other reference and no other narrative changed.
  - The new narrative re-rendered the case's judge prompt, which dropped its verdict. Claude Opus 5.5 re-judged the case on 2026-09-24 through `scripts/run_audit_claude.sh`, with four engine facts added to the case's grounding in the unified audit (`grounding.csv`): the child support parameter is true for Michigan and the engine reads true as excluding child support paid from gross income; the trace cites no Michigan statute, manual or state-option election, so a diagnosis describes the exclusion as what PolicyEngine or the reference does; and the gross income, net income and allotment figures. It returned `llm_error` and `taxable_income_or_deductions` and raised no reference flag, and each diagnosis compares the answer with the reference. A run the same day without those facts stated the engine's exclusion as Michigan's rule in most diagnoses and was not used. The developer adjudication keeps the verdict beside the `engine_defect` decision.
- **Counts.**
  - Exclusions go from 52 to 53. Engine-defect exclusions go from 28 to 29, across 12 root causes in 21 households, 9 of them never flagged.
  - Regenerated references go from 26 to 25: 12 SNAP, 22 by conventions and 14 by upstream fixes, in 24 households.
  - Adjudications go from 63 to 64. Every model is scored on 1,931 outputs.
  - When #9586 merges, rule 2 applies: the reference is regenerated with the fix, and the output returns to scoring at $0.

## Revision of 2026-09-24: the r33 fix merged (release `dashboard-data-20260922c`)

PolicyEngine/policyengine-us#9586 was squash-merged on 2026-09-24 as `d9e801df417352b8246a4c292a19ec082a518790`, so rule 2 applies to r33: its output is regenerated with the fix, not excluded.

- **Root cause.** `root_causes.json` marks r33 `upstream_fixed`, with `upstream` naming the merged pull request and a dated note on both releases. r33 is the eighth root cause fixed upstream.
- **Fix modules.** `fixes/r33_snap_child_support_treatment.py` now embeds the merged `child_support.yaml`. Between the head the previous revision used and the merge, the pull request changed North Carolina, Missouri and Louisiana to exclusion states from 2010, Vermont's fiscal year 2024 to a deduction, and several states' values before 2017; Michigan is a deduction state throughout, as before. The 2026 value still changes in 46 jurisdictions.
- **Sweep.** All 1,984 references were recomputed with the merged values: r33 still moves only `scenario_045` SNAP, to $0, on the frozen engine, on the SNAP convention and on the published SNAP configuration. No household in the benchmark is in Vermont.
- **Record.**
  - `scenario_045` SNAP is regenerated at $0 with r28 and r33 (`regenerated_by_fix`), and its exclusion and the adjudication added for it on 2026-09-24 are removed. `scripts/regen_references.py` holds the regenerated value's derivation, read from an engine run with the fix.
  - The SNAP net-income sensitivity adds r33 to its three procedures (`c13v3_r26_r28_r33`, `c13v3_r28_r29n_r33`, `c13v3_r28_r29c_r33`); r33 moves only `scenario_045` SNAP, to $0 under every procedure.
- **Counts.** Exclusions go from 53 to 52, engine-defect exclusions from 29 to 28 (11 root causes, 20 households, 8 never flagged), and adjudications from 64 to 63. Regenerated references go from 25 to 26: 13 SNAP and 15 by upstream fixes. Every model is scored on 1,932 outputs, as on release `dashboard-data-20260922`; the one difference from that release is `scenario_045` SNAP's reference, $0 instead of $288.
