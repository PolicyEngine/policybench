# Progress

## State

The frozen SNAP pathways have been recomputed and are ready for note/test use.

## Done

- Installed the app dependencies with `bun install --frozen-lockfile`.
- Confirmed the worktree is on `notes-route` at the requested starting commit.
- Added `scripts/snap_pathways.py`, reusing the reference calculation's
  vectorized situation builder and the installed PolicyEngine variables.
- Generated 100 pathway rows with policyengine-us 1.723.0. All recomputed SNAP
  values match the frozen references exactly; 20 households receive SNAP and
  10 depend on categorical eligibility.

## Next

- Add data-backed note definitions and Python tests.
- Add the `/notes` routes, navigation, scenario deep links, sitemap entries, and app tests.
- Run the requested Python and app verification suites.
- Write `out.md`, push `notes-route`, and open a draft PR against `add-fable-5-1`.
