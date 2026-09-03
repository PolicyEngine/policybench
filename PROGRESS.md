# Progress

## State

Both notes and their frozen-evidence fact tests are implemented.

## Done

- Installed the app dependencies with `bun install --frozen-lockfile`.
- Confirmed the worktree is on `notes-route` at the requested starting commit.
- Added `scripts/snap_pathways.py`, reusing the reference calculation's
  vectorized situation builder and the installed PolicyEngine variables.
- Generated 100 pathway rows with policyengine-us 1.723.0. All recomputed SNAP
  values match the frozen references exactly; 20 households receive SNAP and
  10 depend on categorical eligibility.
- Added the two dated note JSON files and a newest-first TypeScript index.
- Added Python coverage that derives every placeholder fact, the explanation
  mention counts, categorical pathway counts, asset-case error bands, and
  engine versions from committed evidence. The focused suite passes (5 tests).

## Next

- Add the `/notes` routes, navigation, scenario deep links, sitemap entries, and app tests.
- Run the requested Python and app verification suites.
- Write `out.md`, push `notes-route`, and open a draft PR against `add-fable-5-1`.
