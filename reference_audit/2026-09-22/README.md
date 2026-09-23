# Reference audit, September 22, 2026

This directory records how the September 22 references and exclusion record were built for the 42-model board (release `dashboard-data-20260922`): 12 regenerated references and 66 outputs excluded from scoring for every model, 55 of them added in this audit. The references come from policyengine-us 1.755.4 for tax year 2026, frozen on 2026-07-03.

## What is here

- `root_causes.json` holds each root cause and publication convention: its class, the defect or unlisted input, the law, the alternative reading, and the upstream status. Classes:
  - `engine_defect`: the engine misapplies the law on facts the prompt states. Every output the fix moves by more than $1 is excluded.
  - `unlisted_input`: the reference turns on an input or definition the prompt never states. Every output the alternative reading moves is excluded.
  - `convention`: the engine projected a parameter with a price index where a government had published an amount, or had published nothing new before the freeze. The reference is regenerated with the amount published before the freeze, or with the last amount published. A convention changes parameter values only.
  - `superseded`: withdrawn, with the reason.
  - `regenerated`: the SNAP rule, as recorded before the conventions generalized it.
- `fixes/` holds the sandbox modules, each a `policyengine_core` Reform or a situation patch on policyengine-us 1.755.4, evaluated for tax year 2026. The defect fixes change 2026 only; the IRS sales tax and California conventions also set the published 2025 amounts that their held 2026 values carry forward. The `_v2` modules are the independently verified revisions. `r18_hold_all_projections.py` is the projection screen: it holds every projected 2025–2026 parameter at its last encoded value. `r13_hold_fy2026_v2.py` is the superseded first SNAP module, which mixed the FY2026 hold with formula corrections; `r13_hold_fy2026_v3.py` is its hold alone, and the corrections are `r26`–`r28`. The `c13v3_*` modules combine the SNAP convention with a SNAP defect fix, to measure the defect on top of the convention; `r29_*` are the net-income sensitivity readings.
- `sweep_moves.csv` lists every output each module changes when all 1,984 references are recomputed under it. `baseline` is the value the module is measured against: the frozen reference (`measured_against = frozen`), or, for the SNAP rounding defects, the SNAP convention's reference (`measured_against = c_snap_hold_fy2026`). `moved_over_1` marks changes over the $1 exact-match tolerance, or a flipped flag. The unmodified harness reproduces all 1,984 pre-audit references frozen on 2026-07-03.
- `snap_net_income_sensitivity.csv` recomputes SNAP on top of the convention, with the contribution and minimum rounding corrected, under three net-income procedures in every state: the engine's floor, the nearest dollar, and cents kept (7 CFR 273.10(e)(1)(ii)). Every output that differs across them is excluded.
- `scripts/` holds the harness (`sweep.py`, `run_one.sh`), the records builder (`build_records.py`, which writes `reference_exclusions.json` and `us_adjudications.json`), the regeneration script (`regen_references.py`, which writes `reference_outputs.csv` and its sidecar), the on-convention measurement (`make_on_convention.py`) and this package's builder (`package_audit.py`). They run against the local results tree and a policyengine-us 1.755.4 environment; their paths are the ones used on 2026-09-22.
- `verification/` holds the independent reports:
  - `v1`–`v4`: GPT-6 Astra lanes re-derived each first-pass fix from primary sources and reran its sweep.
  - `v5a`, `v5b`: sourced every projected parameter behind a moved output.
  - `v6`: settled the three reference flags the September 22 judge raised on scored outputs.
  - `v7`: the adversarial reviews of the first refreeze. They found that the first SNAP convention module also corrected the engine's SNAP arithmetic, which is now split into the convention and three engine-defect root causes.
  - `v8`: the Axiom rules engine's SNAP allotment rounding against the corrected values, and the state SNAP manuals' rounding procedures.

## How the records follow

1. An engine-defect root cause excludes every output its fix moves by more than $1. The SNAP rounding defects (`r26`–`r28`) are measured against the SNAP convention's reference, the value that would otherwise be published. The exclusion records the frozen value, the corrected value computed with every applicable fix and convention together, the law, and the upstream status.
2. An unlisted-input root cause excludes every output its alternative reading moves, with the alternative value. When an output moves under both classes, the engine defect is recorded and the note names the unlisted input.
3. A convention regenerates every scored output it changes. The reference sidecar (`reference_outputs.csv.meta.json`) lists each changed output under its convention, with the module's sha256. An excluded output keeps its frozen value.
4. Every reference flag the judges raised carries a developer adjudication: `affirmed`, `regenerated`, `engine_defect` or `unlisted_input`.
