# Progress

## State

The `/notes` feature and its delivery report are complete and verified. The
branch is ready to push and open as a draft pull request.

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
- Added the `/notes` list and static detail routes, shared fact-aware rendering,
  canonical metadata, navigation links, and sitemap entries.
- Added app coverage for note ordering, slugs, placeholders, and rendered
  content. Lint and all 95 app tests pass; a webpack production build also
  prerenders `/notes` and both detail pages successfully.
- Ran the full Python gate: Ruff passes and pytest reports 623 passed, 5
  skipped. Re-ran the exact app lint and test commands from CI successfully.
- Wrote the required delivery report to `out.md` with derived facts, pathway
  results, exact test output, and the local build limitation.

## Next

- Push `notes-route` and open a draft PR against `add-fable-5-1`.
- Add the draft PR URL to `out.md`, mark delivery complete, and push that final
  report commit.
