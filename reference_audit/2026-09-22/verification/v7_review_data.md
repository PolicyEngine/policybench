SHIP AFTER FIXES

1. **Major — CONFIRMED: the SNAP convention regenerates outputs affected by an engine defect that the publication rule requires excluding.**

   **Location:** [r13_hold_fy2026_v2.py:77](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/reference_audit/2026-09-22/fixes/r13_hold_fy2026_v2.py:77), classified entirely as a convention in [root_causes.json:124](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/reference_audit/2026-09-22/root_causes.json:124).

   The module corrects contribution rounding as well as holding published parameters. The pinned engine computes `floor(net_income) * rate`; line 83 adds the missing upward rounding. That requirement already appears in the [2025 CFR, §273.10(e)(2)(ii)(A)](https://www.govinfo.gov/content/pkg/CFR-2025-title7-vol4/pdf/CFR-2025-title7-vol4-sec273-10.pdf).

   **Evidence:** In the pinned 1.755.4 environment, I ran a reform whose only action was `self.update_variable(m.snap_expected_contribution)`, using the committed module and original parameters. These currently scored SNAP outputs changed:

   | Scenario | Original reference | Rounding-only result | Change |
   |---|---:|---:|---:|
   | 008 | $15,246.905273 | $15,243.307617 | −$3.60 |
   | 012 | $4,952.089355 | $4,942.789551 | −$9.30 |
   | 038 | $7,286.944336 | $7,281.843750 | −$5.10 |
   | 054 | $6,125.688965 | $6,118.790039 | −$6.90 |
   | 079 | $2,428.017334 | $2,418.717041 | −$9.30 |
   | 109 | $8,020.554199 | $8,017.554199 | −$3.00 |

   All six appear in the regeneration sidecar and none in exclusions. Thus the defect independently crosses the $1 threshold; combining it with a convention does not satisfy the supplied exclusion rule.

   Excluding these six changes the four headline scores to **94.578, 93.389, 93.102, and 91.869**, respectively. All 42 ranking positions remain unchanged.

   **Smallest fix:** Separate rounding into an `engine_defect` cause, sweep it, exclude its qualifying outputs—including these six—and preserve their original frozen values. Remove their regeneration entries and regenerate the board, sensitivity summaries, publication numbers, and pins.

2. **Minor — CONFIRMED: the audit test accepts unsupported and misattributed sweep evidence.**

   **Location:** [tests/test_reference_audit.py:85](/Users/maxghenis/PolicyEngine/policybench-wt/opus55/tests/test_reference_audit.py:85).

   The test reduces sweep records to output keys and checks only subset membership. It discards causes, classes, values, and movement thresholds; it also never checks the reverse direction for missed exclusions.

   **Evidence:** I loaded the test module with `runpy.run_path` and patched `csv.DictReader` in memory to change every sweep record to:

   ```python
   recomputed = frozen
   delta = "0"
   moved_over_1 = "False"
   root_cause = "r02_ira_219g"
   class_ = "engine_defect"
   ```

   All three audit tests passed, including `test_sweep_moves_cover_every_exclusion_and_regeneration`. No files were changed.

   **Smallest fix:** Retain cause-keyed records and assert matching classifications, qualifying movements, complete exclusion coverage, and exact convention ownership.

Checks that found nothing wrong:

- **Snapshot arithmetic:** Recomputed **1,984 unique outputs, 55 exclusions, 1,929 scored outputs, 23 unique regenerated references, and 61 unique adjudications**. No regeneration overlaps an exclusion. Every regenerated value matches the CSV; every excluded value retains its recorded frozen value.
- **Recorded exclusion support:** All **44 September 22 additions**—31 defects and 13 unlisted-input exclusions—have qualifying movements of the matching class. No declared defect sweep has an unexcluded qualifying output. Finding 1 concerns a defect bundled into a convention.
- **Sweep integrity:** Compared all **136 committed movement records across 31 modules** with the full local sweep CSVs: no missing records or numerical discrepancies beyond serialization precision. The stored baseline has 1,984 rows, zero qualifying moves, and maximum difference `5.68e-14`.
- **Convention consistency:** All nine conventions’ scored movement sets exactly match their sidecar ownership. Every owned value equals its convention-only sweep result within `1e-6`; no duplicate ownership or module-hash mismatch.
- **Primary-source spot checks:** IRS Texas table values **931/1,595** match the [2025 Schedule A instructions](https://www.irs.gov/pub/irs-prior/i1040sca--2025.pdf). Michigan’s **$5,900 exemption** and **$67,610/$135,220 retirement caps** match its [2026 withholding guide](https://www.michigan.gov/taxes/-/media/Project/Websites/taxes/Forms/SUW/TY2026/446_Withholding-Guide_2026.pdf).
- **Board recomputation:** Both raw snapshot predictions and dashboard predictions reproduce all 42 scores using the repository scorer. Requested values: **94.505970046, 93.214066253, 92.938541256, 91.616327493**. All 83,328 prediction values, reference values, and scoring flags agree; no duplicate prediction keys.
- **Pins:** All 42 manifest file checks pass. Reconstructed dashboard bytes equal `data-board42.json`: **116,127,282 bytes**, SHA-256 **`a4eadbbc9d329b09a33183117596c2c34cd41df69bad56c767bf60e2a9e8edf8`**. The freezer constant and app pointer agree.
- **Sensitivity:** Independently reproduced all four summaries’ three metrics, ranks, deltas, counts, eight asset hashes, and per-variable rows. Exact scores: Fable 5.1 **91.288**, Fable 5 **91.088**, Opus 5 **89.617**, Sonnet 5 **84.434**.
- **Test changes:** Reviewed every changed Python test and all eight changed app test files against `origin/main`. No literal tautologies or unjustified assertion deletions found. The app headline tolerance changes from four to three decimals alongside its three-decimal pin.
- **Executed tests:** **102 passed** across reference audit, sensitivity evidence, paper results, notes, report costs, and model cards, using `pytest -q -s -p no:cacheprovider` with bytecode disabled. Full Python and app suites were not rerun. Final `git status --short` was clean.