# Reference audit, September 22, 2026

This directory records how the 23 regenerated references and the 55-output exclusion record were built for the 42-model board (release `dashboard-data-20260922`). The frozen references come from policyengine-us 1.755.4 for tax year 2026, frozen on 2026-07-03.

## What is here

- `root_causes.json` holds each root cause and publication convention: its class, the defect or unlisted input, the law, the alternative reading, and the upstream status. Classes:
  - `engine_defect`: the engine misapplies the law on facts the prompt states. Every output the fix moves is excluded.
  - `unlisted_input`: the reference turns on an input or definition the prompt never states. Every output the alternative reading moves is excluded.
  - `convention`: the engine projected a parameter with a price index where a government had published an amount, or had published nothing new before the freeze. The reference is regenerated with the amount published before the freeze, or with the last amount published.
  - `superseded`: withdrawn, with the reason.
  - `regenerated`: the SNAP rule, as recorded before the conventions generalized it.
- `fixes/` holds the sandbox modules. Each is a `policyengine_core` Reform or a situation patch on policyengine-us 1.755.4, limited to 2026. The `_v2` modules are the independently verified revisions. `r18_hold_all_projections.py` is the projection screen: it holds every projected 2025–2026 parameter at its last encoded value.
- `sweep_moves.csv` lists every output each module changes when all 1,984 references are recomputed under it (`moved_over_1` marks changes over the $1 exact-match tolerance). A module moves only outputs it changes; the unmodified harness reproduces all 1,984 frozen references exactly.
- `scripts/` holds the harness (`sweep.py`), the records builder (`build_records.py`, which writes `reference_exclusions.json` and `us_adjudications.json`) and the regeneration script (`regen_references.py`, which writes `reference_outputs.csv` and its sidecar). They run against the local results tree and a policyengine-us 1.755.4 environment; their paths are the ones used on 2026-09-22.
- `verification/` holds the independent reports. GPT-6 Astra lanes re-derived each first-pass fix from primary sources and reran its sweep (`v1`–`v4`), sourced every projected parameter behind a moved output (`v5a`, `v5b`), and settled the three reference flags the September 22 judge raised on scored outputs (`v6`).

## How the records follow

1. An engine-defect root cause excludes every output its fix moves by more than $1. The exclusion records the frozen value, the corrected value computed with every applicable fix together, the law, and the upstream status.
2. An unlisted-input root cause excludes every output its alternative reading moves, with the alternative value.
3. A convention regenerates every scored output it changes. The reference sidecar (`reference_outputs.csv.meta.json`) lists each changed output under its convention, with the module's sha256. An excluded output keeps its frozen value.
4. Every reference flag the judges raised carries a developer adjudication: `affirmed`, `regenerated`, `engine_defect` or `unlisted_input`.
