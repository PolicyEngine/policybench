# Reference audit, September 22, 2026

This directory records how the September 22 references and exclusion record were built for the 42-model board (release `dashboard-data-20260922`): 27 regenerated references and 51 outputs excluded from scoring for every model, 40 of them added in this audit. The references come from policyengine-us 1.755.4 for tax year 2026, frozen on 2026-07-03.

## The rules

1. A scored reference follows from the stated facts and from law published before the 2026-07-03 freeze (Max, 2026-09-22). Where the engine projected a 2026 parameter with a price index, a publication convention regenerates the reference with the amount published before the freeze, or with the last amount published. A convention changes parameter values only.
2. An engine defect fixed in policyengine-us after the freeze is regenerated with its fix, on the same engine version (Max, 2026-09-23). Seven root causes qualify: `r04` (#8839), `r09` (#9301), `r17` (#9363), `r26` and `r27` (#9318), and `r28` and `r31` (#9162).
3. An engine defect not fixed upstream excludes every output its fix moves by more than $1.
4. A reference that turns on an input or definition the prompt never states is excluded.

## What is here

- `root_causes.json` holds each root cause and publication convention: its class, the defect or unlisted input, the law, the alternative reading, the upstream status (`upstream_fixed: true` for rule 2) and, for the SNAP defects, `measured_against`. Classes:
  - `engine_defect`: the engine misapplies the law on facts the prompt states.
  - `unlisted_input`: the reference turns on an input or definition the prompt never states.
  - `convention`: a publication convention (rule 1).
  - `superseded`: withdrawn, with the reason.
  - `regenerated`: the first SNAP rule, as recorded before the conventions generalized it; its note records how it was superseded.
- `fixes/` holds the sandbox modules. Each is a `policyengine_core` Reform or a situation patch on policyengine-us 1.755.4, evaluated for tax year 2026; each module's docstring states the periods it changes, since some conventions also set the published 2025 amounts their held 2026 values carry forward and `r06` models the Wisconsin election from 2025.
  - The `_v2` modules are the independently verified revisions.
  - `r13_hold_fy2026_v2.py` is the superseded first SNAP module, which mixed the FY2026 hold with formula corrections. `r13_hold_fy2026_v3.py` is its hold alone, and the corrections are `r26`, `r27`, `r28` and `r31`, all fixed upstream.
  - The `c13v3_*` modules combine the SNAP convention with a SNAP fix, to measure the fix on top of the convention.
  - `r29_*` are the net-income sensitivity readings.
  - `r18_hold_all_projections.py` is the projection screen: it holds every projected 2025–2026 parameter at its last encoded value.
- `sweep_moves.csv` lists every output each module changes when all 1,984 references are recomputed under it.
  - `baseline` is the value the module is measured against: the frozen reference (`measured_against = frozen`), or, for the SNAP defects, the SNAP convention's reference (`measured_against = c_snap_hold_fy2026`).
  - `moved_over_1` marks changes over the $1 exact-match tolerance, or a flipped flag.
  - The unmodified harness reproduces all 1,984 pre-audit references frozen on 2026-07-03.
- `snap_net_income_sensitivity.csv` recomputes SNAP on top of the convention with the rounding fixes, under three net-income procedures in every state: the engine's floor, the nearest dollar (as upstream #9318 does), and cents kept (7 CFR 273.10(e)(1)(ii)). No scored output differs by more than the dollar tolerance between the nearest-dollar and cents-kept readings.
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
  - `v8`: the Axiom rules engine's SNAP allotment rounding against the corrected values, and the rounding procedures in the state SNAP manuals for the states with affected households.
  - `v9`: read-only Axiom encoding-preparation lanes. Each checked whether Axiom encodes a defect's governing provision and derived the affected households' values from the statute text.

## How the records follow

1. An output moved only by upstream-fixed defects (and conventions) is regenerated. The regenerated value applies every convention and upstream fix together.
2. Any other output an engine defect moves by more than $1 is excluded. The exclusion names the defects not fixed upstream and records:
   - the frozen value;
   - the corrected value, computed with every applicable fix and convention together;
   - the law and the upstream status.

   The SNAP defects are measured against the SNAP convention's reference, the value that would otherwise be published.
3. An unlisted-input root cause excludes every output its alternative reading moves, with the alternative value. An output that moves under both an unfixed defect and an unlisted input is recorded as the engine defect, and the note names the unlisted input. An exclusion carried over from 2026-09-05 keeps its original record. The later SNAP defects also move two such outputs, 023 and 100.
4. The reference sidecar (`reference_outputs.csv.meta.json`) lists one revision per convention and per upstream fix. Each revision lists the outputs that source changes, with its module's sha256 and, for a fix, the upstream pull request. An excluded output keeps its frozen value.
5. Every reference flag the September 22 judges raised carries a developer adjudication: `affirmed`, `regenerated`, `engine_defect` or `unlisted_input`.
