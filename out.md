# `/notes` delivery report

## State

Implemented and verified on the local `notes-route` branch. Remote delivery is
blocked by this workspace's GitHub connectivity and connector authorization;
details and exact handoff commands are below.

## Notes and routes

- Added `/notes`, newest first, and statically generated detail routes:
  - `/notes/2026-09-03-six-snap-households`
  - `/notes/2026-09-01-claude-fable-5-1-added`
- Added the two JSON note records and their typed index under
  `app/src/notes/`.
- Rendered every prose placeholder from its tested `facts` entry. Scenario IDs
  in the SNAP note link directly to the existing scenario explorer query
  convention. The annual `$287.68` fact renders as `$288` with an exact-value
  footnote.
- Added full metadata, canonical URLs, site navigation, and sitemap entries.
- Added every requested release, snapshot, sensitivity, model, paper, pathway,
  scenario, and policy-parameter data link.

## Checked note facts

### Claude Fable 5.1 added

- Board exact rate: 86.3%; rank: 2 of 33; parsed: 1,984 of 1,984.
- Auto-tool sensitivity: 87.5%; would-rank: 2.
- Claude Fable 5 auto rate: 86.9%; board rate: 79.9%; board-row gap:
  6.4 points.

### Six SNAP households the top three models deny

- Positive frozen SNAP references: 20 of 100.
- Common zero predictions from GPT-5.6 Sol, Claude Fable 5.1, and Kimi K3:
  `scenario_027`, `scenario_030`, `scenario_045`, `scenario_073`,
  `scenario_108`, and `scenario_112`.
- Each common-denial reference is `$287.68` annually; the frozen explanation
  records `$23.84` monthly.
- Explanation-row regex counts, case-insensitive:
  - Sol `categorical`: 1.
  - Sol `asset|resource`: 36.
  - Fable 5.1 `broad-based|bbce`: 28.
  - Kimi K3 `categorical`: 17.
- Reference engine: policyengine-us 1.755.4. Pathway recompute engine:
  policyengine-us 1.723.0.

## Pathway recompute

`scripts/snap_pathways.py` reuses the vectorized situation builder and value
extractor from `policybench/ground_truth.py`. It generated 100 committed rows
plus a provenance sidecar.

- `ordinary`: 10
- `categorical_income`: 5
- `categorical_assets`: 4
- `categorical_both`: 1
- `ineligible`: 80
- Positive-allotment `snap_eligible`: 20
- Categorical-only total: 10; income-related categorical total (including
  `categorical_both`): 6.
- Asset-only cases and states:
  - `scenario_008` — New Jersey
  - `scenario_054` — North Carolina
  - `scenario_066` — Virginia
  - `scenario_080` — Pennsylvania
- On those four asset cases, Sol is within 1% on three and within 10% on one;
  Fable 5.1 is within 1% on all four.
- Recompute/reference disagreements: none. Maximum absolute difference: `$0`.
- The underlying `is_snap_eligible` gate is true despite a zero computed
  allotment for `scenario_028` and `scenario_032`; the exported eligibility
  column deliberately follows the note's positive-allotment definition.

One-time script output:

```text
PolicyEngine's is_snap_eligible gate is true but the computed allotment is $0 for: scenario_028, scenario_032
Wrote 100 rows to notes/data/snap_pathways_20260901.csv
  ordinary: 10
  categorical_income: 5
  categorical_assets: 4
  categorical_both: 1
  ineligible: 80
```

## Files changed

- Progress and report: `PROGRESS.md`, `out.md`.
- Evidence generation: `scripts/snap_pathways.py`,
  `notes/data/snap_pathways_20260901.csv`, and its `.meta.json` sidecar.
- Note records and rendering: `app/src/notes/`,
  `app/src/components/NotesContent.tsx`, and the two `/notes` page files.
- Discovery and navigation: `app/src/App.tsx`, `app/src/components/Hero.tsx`,
  `app/src/components/SiteHeader.tsx`, the paper and model pages, and the
  sitemap.
- Tests: `tests/test_notes.py` and `app/tests/notes.test.ts`.
- Ignore rule: `.gitignore` admits the committed pathway evidence.

No file under `paper/snapshot/**` or `app/public/paper/**` was edited.

## Verification

### Python

Command:

```text
PY=/Users/maxghenis/PolicyEngine/policybench/.venv/bin/python
PYTHONPATH=/Users/maxghenis/PolicyEngine/policybench-wt/notes
$PY -c '<assert policybench.ground_truth.__file__ is in the notes worktree>'
$PY -m ruff format .
$PY -m ruff check .
$PY -m pytest -q
```

Output:

```text
policybench.ground_truth: /Users/maxghenis/PolicyEngine/policybench-wt/notes/policybench/ground_truth.py
75 files left unchanged
All checks passed!
........................................................................ [ 11%]
........................................................................ [ 22%]
........................................................................ [ 34%]
........................................................................ [ 45%]
........................................................................ [ 57%]
........................................................................ [ 68%]
........................................................................ [ 80%]
...sss...ss............................................................. [ 91%]
....................................................                     [100%]
=============================== warnings summary ===============================
tests/test_ground_truth.py::TestGroundTruth::test_eitc_zero_for_50k_single
tests/test_ground_truth.py::TestGroundTruth::test_eitc_positive_for_low_income_family
tests/test_ground_truth.py::TestGroundTruth::test_income_tax_reconciles_from_compact_tax_components
tests/test_ground_truth.py::TestGroundTruth::test_household_structure_drives_filing_status_ground_truth
tests/test_ground_truth.py::TestGroundTruth::test_household_net_income_reasonable
tests/test_ground_truth.py::TestGroundTruth::test_calculate_ground_truth_dataframe
tests/test_ground_truth.py::TestGroundTruth::test_us_vectorized_ground_truth_matches_scalar_reference
tests/test_ground_truth.py::TestGroundTruth::test_us_vectorized_ground_truth_matches_scalar_reference
  /Users/maxghenis/PolicyEngine/policybench/.venv/lib/python3.14/site-packages/policyengine_us/variables/gov/irs/income/taxable_income/adjusted_gross_income/irs_gross_income/unemployment_insurance/taxable_unemployment_insurance.py:22: RuntimeWarning: invalid value encountered in divide
    share = where(tax_unit_uc > 0, person_uc / tax_unit_uc, 0)

tests/test_snapshot_artifacts.py::test_snapshot_deviation_audit_annotations_are_complete_and_final
tests/test_snapshot_artifacts.py::test_snapshot_audit_annotations_have_no_orphan_rows
  /Users/maxghenis/PolicyEngine/policybench-wt/notes/policybench/annotation_validation.py:226: DtypeWarning: Columns (0: cost_is_estimated) have mixed types. Specify dtype option on import or set low_memory=False.
    predictions = pd.read_csv(country_dir / "predictions.csv.gz")

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
623 passed, 5 skipped, 10 warnings in 50.54s
```

### App lint and tests

Command, matching the app CI job:

```text
bun run lint
bun test tests
```

Output:

```text
$ eslint . --max-warnings=0
bun test v1.3.12 (700fc117)

 95 pass
 0 fail
 322 expect() calls
Ran 95 tests across 12 files. [1316.00ms]
```

### Production build

`IS_WEBPACK_TEST=1 bun run build` completed successfully with Next.js 16.2.6
using webpack. It compiled, type-checked, generated all 43 static pages, and
reported:

```text
Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /expand
├ ● /model/[id]
│ ├ /model/gpt-5.6-sol
│ ├ /model/claude-fable-5.1
│ ├ /model/kimi-k3
│ └ [+30 more paths]
├ ○ /notes
├ ● /notes/[slug]
│ ├ /notes/2026-09-03-six-snap-households
│ └ /notes/2026-09-01-claude-fable-5-1-added
├ ○ /paper
├ ○ /robots.txt
└ ○ /sitemap.xml

○  (Static)  prerendered as static content
●  (SSG)     prerendered as static HTML (uses generateStaticParams)
```

## Delivery

- Branch: `notes-route`
- Base: `add-fable-5-1`
- Local implementation commit before this report update: `725c1ac`
- Draft PR URL: unavailable because the remote branch could not be created.

The remaining commands, once GitHub access is restored, are:

```text
git push -u origin notes-route
gh pr create --draft --base add-fable-5-1 --head notes-route --title "Add /notes with two data-linked notes" --body "Adds dated, fact-tested notes for Claude Fable 5.1 and six shared SNAP denials, with committed pathway evidence."
```

## Could not do locally

The default Turbopack path behind unprefixed `bun run build` fails in this
managed sandbox with `TurbopackInternalError: Failed to write app endpoint
/page`. Its cause chain ends in PostCSS loader evaluation trying to create a
process, bind a port, and receiving `Operation not permitted (os error 1)`.
`NEXT_TURBOPACK_USE_WORKER=0` reaches the same sandbox restriction. The webpack
build path completed successfully as recorded above. CI runs outside this
sandbox and can execute the default command.

The requested push failed before authentication because the managed shell
cannot resolve GitHub:

```text
fatal: unable to access 'https://github.com/PolicyEngine/policybench.git/': Could not resolve host: github.com
```

The installed GitHub connector was then tried as the network-independent
fallback. Both low-level tree creation and direct `notes-route` branch creation
returned `user cancelled MCP tool call`; a follow-up branch search confirmed
that `notes-route` does not exist remotely. Therefore no truthful PR URL can be
recorded and no draft PR can be opened from this environment.
