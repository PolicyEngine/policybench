# Progress

## State

All eight findings are implemented. The required freeze, paper render, re-pin,
and final verification remain.

## Done

- Confirmed the worktree is clean at `d9a13ceb127db43c352011283be3d4d04a629bd5`.
- Read the applicable PR-review workflow; GitNexus graph tools are unavailable, so caller coverage will be audited with repository search.
- Implemented fail-closed reference provenance and audited every dashboard
  payload call site (F1-F2).
- Corrected manuscript request disclosures and added rendered HTML/PDF bans
  (F3).
- Made unsupported Responses-API sensitivity knobs fail before output and
  versioned treatment metadata (F4-F5a).
- Added supervised-run evidence to snapshot serving configuration, with four
  available fingerprints and honest registry fallback for 29 rows (F5b).
- Added race-safe version loading, archived model-link context, the current
  model-page board label, and archived methodology copy (F6-F8).
- Focused verification: 321 backend/evaluation tests and 97 app tests pass;
  Python lint/format and app lint pass.
- Pre-freeze full pytest: 627 passed, 5 skipped, 7 expected failures against
  the not-yet-regenerated serving config, HTML, and PDF.

## Next

- Complete the exact app install/lint/test/build chain.
- Freeze the snapshot, render PDF/web, and re-pin rendered hashes.
- Run the post-render full Python suite and final app verification.
- Write `out.md`, commit all intended artifacts, and report the final commit.
