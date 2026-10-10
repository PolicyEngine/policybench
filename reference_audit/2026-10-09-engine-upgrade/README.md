# Reference upgrade, October 10, 2026

This directory records how PolicyBench's US references moved from policyengine-us 2.15.17 to
policyengine-us 2.38.6. That was the first PyPI release carrying policyengine-us #10027, #10031,
#10032 and #10034, and the newest release when PolicyBench began sweeping the references on
2026-10-10 (`verification/sweep_timing.json`). The directory is named for the day the audit began
(2026-10-09); the records date the upgrade by its UTC day, 2026-10-10.

Of the 1,984 outputs:
- 18 outputs are regenerated because 2.38.6 fixes the engine defects behind them. Release
  20261006 excluded 14 of them, which return to scoring. The other four were ruled on 2026-10-06
  while still scored, and they stay scored.
- 1 scored reference changes beyond the $1 tolerance: Idaho's scenario_076 state income tax, by
  the $10 permanent building fund tax.
- 2 outputs are newly excluded: the local income tax of Indiana's scenario_015 and scenario_067.
  2.38.6 computes it for a county no prompt states.
- 2 scored references change by less than the $1 tolerance (scenario_082 state income tax,
  scenario_085 federal income tax).
- 17 excluded outputs whose values move were re-reviewed, and they stay excluded.

## Files

- `final_actions.json`: the reviewed actions the build ran on. Its sha256, `ef23b50e…`, is the
  sidecar's `provenance.actions_sha256`.
- `scripts/build_references_upgrade.py`: the builder. `scripts/sweep_timing.py`: the timing
  record and the publication check (`verification/sweep_timing.json`).
- `upstreams.json`: the upstream fix each regeneration names.
- `evidence/`: the fix-module values on policyengine-us 2.37.2 and the upstream bisect.
- `hand_corrected_narratives.json` and `.md`: the reference narratives of the changed outputs.

## Erratum

`final_actions.json`'s `note` was written before CA scenario_099's state income tax moved from the
regenerations to the rechecks (commit a4e76adf). The note still says 19 regenerations and 16
rechecks, but the file's arrays hold 18 regenerations and 17 rechecks. Those are the counts the
sidecar, the paper and the benchmark card give. The note stays as written because the sidecar
pins the file's bytes (`tests/test_reference_upgrade.py`).
