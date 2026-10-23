# Reference upgrade, October 23, 2026

This directory records how PolicyBench's US references move from policyengine-us 2.41.0 to
policyengine-us 2.60.0 for the next board release. 2.60.0 was the newest PyPI release when
PolicyBench began sweeping the references (`verification/sweep_timing.json`): its wheel was
uploaded at 22:47:49 UTC on 2026-10-22 and installed at 01:44:20 UTC on 2026-10-23, and the
sweep wrote its first output at 01:45:50. The directory is named for the day the audit began
(2026-10-22); the records date the upgrade by its UTC day, 2026-10-23.

The build is staged, not installed. `reference-build/` holds the reference CSV, sidecar and exclusion
record that the next board release installs into
`paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/`. Until then
the published board, release 20261014, stays on 2.41.0.

Of the 1,984 outputs:
- 4 scored outputs change, and each is approved (table below).
- 16 excluded outputs differ from the values they were decided on. Each was rechecked, and
  each stays excluded at its decided value. Five of them changed since 2.41.0: scenario_118's
  SNAP and the four r24 outputs below. The other eleven keep 2.41.0's values, which already
  differed from their decided values.
- No exclusion is regenerated, and nothing is newly excluded.

The exclusion record keeps its 49 records, so each model is still scored on the same 1,935
outputs; four of their references change.

| Output | Fix | 2.41.0 | 2.60.0 | Law |
|---|---|---|---|---|
| scenario_031 (CA) SNAP | #10036 | $0 | $288 | California MCE has no net income test; a one-person household gets the $24 minimum |
| scenario_028 (PA) free school meals | #10238 | 0 | 1 | Pennsylvania Act 33 of 2023, universal free breakfast |
| scenario_117 (AR) free school meals | #10238 | 0 | 1 | Arkansas Act 123 of 2025, universal free breakfast |
| scenario_123 (PA) free school meals | #10238 | 0 | 1 | Pennsylvania Act 33 of 2023, universal free breakfast |

All four come from law in force before the 2026-07-03 reference freeze. California's MCE waiver
dates from CDSS's 2011-2015 letters. Pennsylvania codified its breakfast program on 2023-12-13,
and Arkansas's applies from the 2025-26 school year. Both are standing statutes.

The school-meal output asks "whether PolicyEngine returns positive annual free school meal
support". Each of these households is in the paid tier for lunch, but its K-12 children now
get a free breakfast. `final_actions.json` gives each change's basis, with the figures from
`reference-build/reference_traces.json`.

Each named pull request (#10036, #10158, #10185 and #10238) is an ancestor of 2.60.0's release
commit, 2bc4ccc970. #10238 is not in 2.59.0's, 05813807e1. Built from source, that commit's
1,984 outputs are identical to the published wheel's (`verification/release_commit_check.json`).

## The r24 outputs stay excluded

Four outputs land exactly on their exclusion records' alternative values:

| Output | 2.60.0 = alternative value |
|---|---|
| scenario_002 federal income tax | $1,890.30 |
| scenario_107 federal income tax | $211.23 |
| scenario_121 federal income tax | $875.34 |
| scenario_121 state income tax | $212.23 |

#10185 (released in 2.50.0) counts employment disability benefits in gross income less a new
input, `tax_exempt_disability_benefits`, the part from coverage the recipient paid for. That
input defaults to zero, so the engine treats the benefits as coming from an employer-paid plan.

The four records are not engine defects; they are `reference_depends_on_unlisted_input`. The
prompt lists "disability benefits" without saying who paid for the coverage, and that decides
whether they are taxable (26 U.S.C. 105(a); 104(a)(3)).
`reference_audit/2026-09-22/root_causes.json` classes r24 `unlisted_input`, and its fix module
"encodes the employer-paid reading".

The engine now takes that reading by default, but the stated facts still do not decide it. The
builder regenerates only engine-defect records. The 2026-10-12 upgrade kept scenario_080, 052
and 081 excluded on the same ground: their defects were fixed, but a second reason stood. So
these four stay excluded at their decided $0.

Scoring them at the engine's values would mean ruling that the employer-paid default is the
reference reading. That ruling would move the four entries from `excluded_rechecked` to
`regenerated_exclusions`, and the builder's engine-defect guard would have to admit an
unlisted-input record.

## scenario_118 SNAP

It moves from 2.41.0's $2,868 to $2,400 a year. #10158 models New York's state supplement to
SSI, $87 a month for a person living alone (`ny_ssp`), and SNAP counts it as unearned income.
Gross income rises from $1,014 to $1,101 a month, and the allotment falls from $239 to $200.

The record's unlisted input still decides the output: whether the listed mortgage interest is on
the home the household lives in. So it stays excluded at $2,903.94.

## The first sweep, on 2.59.0

PolicyBench first swept on 2.59.0, the newest release at 19:49 UTC on 2026-10-22. A host restart
cut the session off before the build. When it resumed, 2.60.0 was out and moved three scored
outputs that 2.59.0 does not, the school-meal flags (#10238), so the sweep began again on
2.60.0.

`verification/superseded_2_59_0.json` keeps the 2.59.0 record and that difference. Every other
output is identical on the two releases.

## Publication check

At 02:11 UTC on 2026-10-23, PolicyBench read PyPI again, and 2.60.0 was still the newest release
(`verification/sweep_timing.json`, `publication_check`). The next board release checks again
before it publishes. After installing the build, it runs:

```
scripts/sweep_timing.py check --build reference-build --snapshot <the run directory>
```

with `--check-venv` if a newer release is out.

## Installing the build (the next board release)

1. Copy `reference-build/reference_outputs.csv`, `reference_outputs.csv.meta.json` and
   `reference_exclusions.json` into the run directory, and move pyproject's policyengine-us pin
   (and `uv.lock`) to 2.60.0.
2. Rebuild the reference narratives of the four changed outputs. No writer call is needed:

   ```
   scripts/narratives_upgrade.py --references reference-build \
     --explanations annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_case_reference_explanations.csv \
     --hand-corrected hand_corrected_narratives.json --out <csv>
   ```

   On release 20261014's explanations this gives sha256 `a1691832…`.
3. Re-score and re-freeze the board, then rerun the publication check. Judges' prompts render a
   case's reference value and narrative, so the cases on the four changed outputs are judged
   again.

`tests/test_build_references_upgrade_1022.py` holds the snapshot to either the base's three
files or this build's.

## Files

- `final_actions.json`: the reviewed actions the build ran on. Its sha256, `a6a4e07b…`, is the
  sidecar's `provenance.actions_sha256`. It is `actions_from_cells.py`'s draft with figures and
  upstream pull requests added to four bases and five reasons; no placement changed.
- `actions_from_cells.py`: drafts the actions from a first pass. Its rules recognize the two
  kinds of scored move this upgrade makes.
- `scripts/build_references_upgrade.py`: the builder (sha256 `d4b00204…`, which the sidecar
  pins). It is the 2026-10-12 builder on release 20261014's references, without a release spec.
- `scripts/sweep_timing.py`: the timing record and the publication check. The check takes
  `--snapshot`, the committed copy the build must equal.
- `scripts/narratives_upgrade.py`: the reference narratives. A run whose narratives are all
  hand-corrected needs no API key.
- `reference-build/`: the build. `computed.csv` is every output on 2.60.0, byte-identical to the sweep's
  first output.
- `hand_corrected_narratives.json` and `.md`: the four changed outputs' reference narratives.
- `verification/sweep_timing.json`, `verification/superseded_2_59_0.json` and
  `verification/release_commit_check.json`.

There is no `evidence/` or `fixes/` directory, because no regeneration here needs a
`fix_modules` target. If a later one does, the 2026-10-12 audit's `check_against_evidence.py`
applies.

The builder leaves the reference CSV's `impact_weight` column as it was, as every earlier
upgrade did.
