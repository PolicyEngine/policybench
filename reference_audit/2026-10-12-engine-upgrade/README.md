# Reference upgrade, October 13, 2026

This directory records how PolicyBench's US references moved from policyengine-us 2.38.6 to
policyengine-us 2.41.0. 2.41.0 was the newest PyPI release when PolicyBench began sweeping the
references on 2026-10-13 (`verification/sweep_timing.json`): its wheel was uploaded at 01:44:55
UTC and installed at 01:49:51; the sweep's first pass began at 01:50:17 and wrote its first
output at 01:51:12. It is the first release carrying every fix
release 20261010 was waiting on. The directory is named for the day the audit began
(2026-10-12); the records date the upgrade by its UTC day, 2026-10-13.

Of the 1,984 outputs:
- 9 excluded outputs are regenerated because 2.41.0 fixes the engine defects behind them, and
  they return to scoring. Each lands on its audited target (table below).
- 12 excluded outputs whose values move were re-reviewed, and they stay excluded. One of them,
  scenario_080's SNAP, lands on its corrected value (#10033 fixes its defect) but stays excluded
  (below).
- No scored reference changes, by any amount.
- Nothing is newly excluded.

The exclusion record falls from 58 records to 49, so each model is scored on 1,935 outputs.

| Output | Fix | 2.38.6 | 2.41.0 = target | Target kind |
|---|---|---|---|---|
| scenario_007 (ID) state income tax | #10023 | 771.56 | 661.32 | fix_modules |
| scenario_042 (WI) state income tax | #10026 | 464.18 | 0.00 | record |
| scenario_053 (ID) state income tax | #10023 | 2,451.06 | 2,186.06 | fix_modules |
| scenario_091 (WI) state income tax | #10026 | 895.81 | 878.52 | record |
| scenario_099 (CA) state income tax | #10032, #10034, #10052 | 4,588.48 | 4,615.48 | fix_modules |
| scenario_100 federal refundable credits | #10030 | 2,878.10 | 822.29 | record |
| scenario_100 state refundable credits | #10030 | 473.18 | 164.46 | record |
| scenario_119 federal refundable credits | #10030 | 2,854.01 | 3,366.07 | record |
| scenario_119 state income tax | #10030 | 1,859.09 | 1,756.68 | record |

Each of the six pull requests, and #10033, is an ancestor of 2.41.0's release commit,
de3815f4cc. The published wheel's 1,984 computed outputs are identical to a first pass on that
commit.

scenario_080's SNAP lands on its record's corrected value, $3,240, so 2.41.0 (#10033) fixes the
heat-and-eat defect behind it, but it stays excluded: the 2026-09-29 recheck found it indeterminate
on the stated facts. Its prompt calls the head disabled but states none of the routes by which
7 U.S.C. 2012(j) makes a member disabled (with one, the allowance would stand, at $3,576), and it
does not say whether the household's $2,000 energy subsidy is a LIHEAP payment or a State-law
payment, which 7 U.S.C. 2014(k)(4) treats differently. `actions_from_cells.py` drafts such an
output as a recheck (`indeterminate_rechecks`).

Before publication, PolicyBench re-swept every output on 2.41.2, the newest release when it checked
PyPI at 11:34 UTC (`verification/publication_check_2_41_2.csv`): all 1,984 are identical to
2.41.0's.

For the next release (Gemini 4 Argon and Muse Spark 1.3), which keeps these references,
PolicyBench re-swept every output on 2.41.3, the newest release when it checked PyPI at 17:22 UTC
on 2026-10-13 (`verification/publication_check_2_41_3.csv`): all 1,984 are again identical to
2.41.0's. `verification/sweep_timing.json` holds the latest check.

## Files

- `final_actions.json`: the reviewed actions the build ran on. Its sha256, `cfe9f335…`, is the
  sidecar's `provenance.actions_sha256`.
- `scripts/build_references_upgrade.py`: the builder. `scripts/sweep_timing.py`: the timing
  record and the publication check (`verification/sweep_timing.json`).
- `actions_from_cells.py`: drafts the actions from a first pass. `upstreams.json`: the upstream
  fix each regeneration names.
- `evidence/pe2.38.6.json`: the ten candidate outputs on 2.38.6, without and with their fix modules, which
  give the `fix_modules` targets.
- `fixes/r33_ca_educator_expense_addback.py`: this audit's own fix module. California does not
  allow the federal educator expense deduction and adds it back (#10052's
  `ca_educator_expense_addition`). scenario_099's 2.38.6 target needs it beside the 2026-09-22
  audit's r02 and r11 modules.
- `hand_corrected_narratives.json` and `.md`: the reference narratives of the nine changed
  outputs, and why each departs from the writer's draft.
