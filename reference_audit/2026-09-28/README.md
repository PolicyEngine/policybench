# Reference upgrade, September 29, 2026

This directory records how PolicyBench's US references moved from policyengine-us 1.755.4 to policyengine-us 2.15.17, the newest release when PolicyBench began sweeping the references on 2026-09-29 (uploaded 00:23 UTC). PolicyBench built the references at 11:57 UTC that day, and rebuilt them at 15:04 UTC to correct the records' dates and wording; no reference value changed. policyengine-us 2.17.0, the newest release when PolicyBench checked PyPI on 2026-09-29 at 14:58 UTC, gives the same value as 2.15.17 for all 1,984 outputs under the same conventions and adapter. The reference sidecar's `engine_upgrade` revision lists every change.

Of the 1,984 outputs:
- 4 scored references change value;
- 3 outputs are newly excluded from scoring;
- 2 references change by less than the $1 exact-match tolerance;
- 19 already-excluded outputs were recomputed, re-reviewed and stay excluded.

The record now has 1,929 scored outputs and 55 exclusions.

The records date the upgrade by its UTC day. The directory's name, 2026-09-28, is the US Eastern date on which the wave began; the sweep began at 01:42 UTC on 2026-09-29 (`verification/sweep_timing.json`), so the upgrade is dated 2026-09-29. The one decision dated 2026-09-28 is Max's ruling, labeled as his, and `clusters.json` labels each review with its local date.

## The rules

1. References come from the newest policyengine-us release when PolicyBench begins the reference sweep. Before publishing, PolicyBench checks that the newest release on PyPI gives the same values, and records when it checked (step 6 of the method). The rule follows Max's ruling of 2026-09-28: "we should be using the latest pe for this always!" policyengine.py 6.1.2 is recorded for provenance. Its certified US bundle is policyengine-us 2.2.1, which still carries SNAP rounding defects fixed since, and `import policyengine` 6.1.2 refuses to load next to 2.15.17. PolicyBench computes references with `policyengine_us.Simulation` directly, as it always has, so the sidecar records `model_matches_policyengine_bundle: false`.
2. A scored reference follows from the stated facts and from law published before the 2026-07-03 reference freeze (Max, 2026-09-22). The nine publication conventions of the September 22 audit are re-expressed for 2.15.17 in `fixes/latest_c_*.py`. The SNAP convention needed a rewrite: 2.15.17 applies reforms after uprating and carries USDA's FY2027 figures as published values, so holding the uprating index alone changes nothing, and each FY2026 figure is held directly for October to December 2026. The eight upstream fixes the September 22 audit regenerated (r04, r09, r17, r26, r27, r28, r31, r33) are all in 2.15.17 and need no module.
3. The benchmark's output definitions hold. policyengine-us #8888 folded Maryland county income tax into its state income tax aggregate, but PolicyBench's state income tax output excludes local tax. `fixes/latest_md_local_output_scope.py` restores that scope; the county tax stays in the federal SALT deduction.
4. An output whose reference turns on a fact the prompt does not state is excluded, as before.
5. Excluded outputs recorded before this wave keep the values they were decided on. They are not scored.

## What changed and why

| Output | 20260922c | Now | Why |
|---|---:|---:|---|
| scenario_008 state refundable credits (NJ) | 5,342.40 | 5,842.40 | New Jersey child tax credit schedule for 2026-2028, P.L.2026, c.26, approved June 30, 2026 (upstream #8971) |
| scenario_013 SNAP (AZ) | 0 | 240 | Arizona raised its expanded categorical eligibility gross limit from 185% to 200% of poverty from benefit month 03/2026 |
| scenario_028 reduced-price school meals (PA) | 1 | 0 | Child support received counts as income for school meals (7 CFR 245.6(a)(5)(ii)); 1.755.4 left it out |
| scenario_082 state refundable credits (NY) | 650.50 | 667.00 | Empire State child credit phase-out rounding (upstream #9425) |
| scenario_033, 078 and 117 federal income tax | scored | excluded | Whether a listed state and local tax refund is income depends on whether the refunded tax reduced federal tax in the prior year, which the prompt does not say (26 U.S.C. 111(a)). 2.15.17 counts the whole refund (upstream #9422, fixing issue #9122) |

Also:
- **Stated weekly hours.** Upstream #9261 changed the default of `weekly_hours_worked_before_lsr`, the input SNAP's work rules read, from 40 to 0. The prompt's "usual weekly hours worked" is `hours_worked_last_week`, so `policybench.scenarios.PE_INPUT_ALIASES` now passes the stated value under both names. Without it, scenario_066 (40 stated hours) would fail SNAP's ABAWD test. Its reference stays at 3,576.
- **Changes under $1.** scenario_078 and scenario_117 state income tax each move by under $1 through the refund.
- **The 19 excluded outputs that move on 2.15.17.** Each was re-reviewed and stays excluded. Their defects (r01, r02, r07, r11, r30, r32) are still in 2.15.17, or they depend on an unlisted input that no engine version resolves. The sidecar's `excluded_outputs_rechecked` gives each one's 2.15.17 value and reason.

## Method

1. **Sweep.** `scripts/sweep_latest.py` recomputed all 1,984 outputs on 2.15.17, reusing the household builder of the September 22 harness (`scripts/sweep.py`). It compares each output with the 20260922c reference and with raw 1.755.4. `verification/sweep_timing.json` records when the sweep began and each release's PyPI upload time. On 2.15.17, PolicyBench re-ran four of the September 22 sweeps over every output: the IRA deduction limit fix (r02), the net investment income tax definition (r25), and the readings for mortgage residence and 40 unlisted weekly hours. It also ran a new sweep for the state and local tax refund reading (`fixes/latest_alt_*.py`; the r25 sweep composes `fixes/alt_conventions_r25.py`). Each sweep adds its fix or reading to the conventions sweep (`latest_conventions`), except the 40-hour sweep, which adds its reading to the conventions with the stated-hours alias (`latest_map_stated_hours`). Against those baselines, no sweep moves a scored output by more than the $1 exact-match tolerance. Three scored state income tax outputs move by less: scenario_082's under the IRA fix, and scenario_078's and scenario_117's under the refund reading. Against the conventions sweep alone, the 40-hour sweep also moves scenario_066's SNAP, whose prompt states 40 hours; the stated-hours alias, which the references apply, gives it the same value. `verification/rerun_sweeps.json`, written by `scripts/summarize_rerun_sweeps.py`, lists every output each sweep moves. The other defect fixes and readings of the September 22 audit ran on 1.755.4 only.
2. **Port.** Two agents ported the conventions (reports in `verification/port_*`). `fixes/latest_conventions.py` composes them, and `fixes/latest_final.py` adds the Maryland output-scope adapter.
3. **Explain.** Every output that still moved was grouped into 16 root-cause clusters (`verification/compose_result.json`). An investigator settled each cluster from the upstream commits, the engine code in both versions, and primary legal sources with their publication dates. An independent adversarial reviewer then tried to refute each settlement. `clusters.json` holds each cluster's investigation and review. Six reviews ran in a Claude Code workflow begun on the evening of 2026-09-28, US Eastern time (early on 2026-09-29 UTC), and ten on subfleet review lanes later on 2026-09-29 (`verification/reviews/`). Where two reviews conflicted (scenario_078 federal), `clusters.json` records the reconciliation.
4. **Build.** `scripts/build_references_latest.py` recomputes every output with `latest_final` and writes the references and sidecar. It refuses any scored output that moves without a reviewed action in `final_actions.json`, any listed action the engine does not reproduce, and any excluded output that moves without a recheck. It records each rechecked output's reason as its reviewer's full text in `clusters.json`. Its docstring gives the rebuild command. `scripts/rewrite_reference_records.py` applies the builder's record functions to the installed records when no output needs recomputing. `scripts/install_adds0929_references.py` installs either script's output only if the reference CSV is byte-identical and nothing changed but record text and the audit exclusions `final_actions.json` lists.
5. **Record.** `sweep_moves.csv` lists every output with these values:
   - raw 1.755.4 (`v11_1755`);
   - the 20260922c reference (`board_20260922c`);
   - raw 2.15.17 (`raw_2_15_17`);
   - 2.15.17 with the conventions (`conventions`);
   - 2.15.17 with the conventions and the adapter (`final`);
   - the published reference (`reference`).

   Each moved output also carries its cluster and action.
6. **Verify.** Before publishing, PolicyBench read PyPI on 2026-09-29 at 14:58 UTC, when policyengine-us 2.17.0 was the newest release (`verification/sweep_timing.json`). `verification/latest_final_2170.csv` and `verification/latest_final_2170.log` hold `scripts/sweep_latest.py --fix fixes/latest_final.py` run on policyengine-us 2.17.0 with policyengine.py 6.1.2. It reproduces every scored reference, and it gives each of the 19 rechecked excluded outputs the 2.15.17 value the sidecar records. A second check before publishing, at 18:28 UTC, found policyengine-us 2.17.1 (uploaded 17:24 UTC); it also gives the same value for all 1,984 outputs (`verification/latest_final_2171.csv`).
7. **Date the judge verdicts.** `scripts/date_adds0928_judge_verdicts.py` dates each judge verdict the adjudication record keeps from its sha256-bound sidecar, and writes what it read to `verification/judge_verdicts.json`. `verification/flagged_sept22_wave.json` lists the cases the September 22 wave's judge runs flagged; a kept flag that the dated verdict does not raise names that wave in `judge_reference_suspect_source`.

`tests/test_reference_upgrade.py` checks that every module the revision names is committed unchanged, that the table is the committed reference, and that every change is listed and backed by its cluster's review. The scripts use the paths of the machine that ran them, as the September 22 scripts do.
