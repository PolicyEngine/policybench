# Peer review round 5 report

## F1: Reused fold output provenance

Files changed: `policybench/fold_board.py`, `tests/test_fold_board.py`.

Fix: The fold now removes all four destination reference and sidecar files before copying the source set. A missing source sidecar therefore leaves no stale destination sidecar, while a replacement source sidecar is copied byte for byte.

Tests added: `test_reused_output_removes_stale_reference_sidecar_before_export`, `test_reused_output_replaces_reference_sidecar_from_source`.

## F2: Fail-closed reference provenance in every export

Files changed: `policybench/full_run_export.py`, `policybench/analysis.py`, `policybench/cli.py`, `policybench/fold_board.py`, `tests/test_analysis.py`, `tests/test_export_full_run.py`, `tests/test_fold_board.py`.

Fix: `ReferenceProvenanceError` now rejects a missing sidecar or missing country bundle, and dashboard builders require callers to supply `policyengine_bundles` with no installed-runtime fallback. All repository call sites and CLI export paths thread bundles from the reference sidecar, and CLI preflight happens before any payload is written.

Tests added: `TestSummaries.test_build_dashboard_payload_requires_reference_bundles`, `test_export_full_run_cli_fails_closed_without_reference_sidecar`; `test_reference_policyengine_bundles_come_from_the_sidecar` was extended for both fail-closed cases.

## F3: Accurate request and transport disclosure

Files changed: `paper/index.qmd`, `tests/test_disclosures.py`, `app/public/paper/web/index.html`, `app/public/paper/policybench.pdf`, `paper/snapshot/20260501/manifest.json`.

Fix: The manuscript now distinguishes the canonical whole-scenario design from the 10-of-33 chunked accommodation, names request shape and answer transport as the two non-identical dimensions, and describes Ox Alpha's actual canonical forced-tool treatment. Source, visible HTML, and extracted PDF text are checked case-insensitively for every prohibited claim.

Tests added: `test_paper_source_and_rendered_html_make_no_false_request_claims`, `test_rendered_pdf_makes_no_false_request_claims`.

## F4: Fast failure for unsupported Responses API sensitivity knobs

Files changed: `policybench/eval_no_tools.py`, `tests/test_eval_no_tools.py`, `tests/test_supervisor.py`.

Fix: Unsupported sensitivity settings now raise `SensitivityKnobError`, are preflighted once per model before output or checkpoint creation, and bypass every generic row-recovery handler. Both public evaluation loops and the `eval-no-tools` and `run` CLI paths exit nonzero without sending a request or creating prediction state.

Tests added: `test_eval_entrypoints_reject_responses_sensitivity_before_writing` for both evaluators, `test_eval_no_tools_cli_rejects_responses_sensitivity_without_predictions`, `test_run_cli_maps_sensitivity_knob_error_to_system_exit`.

## F5: Honest, frozen serving-treatment evidence

Files changed: `policybench/eval_no_tools.py`, `policybench/supervisor.py`, `scripts/freeze_snapshot.py`, `policybench/paper_results.py`, `paper/index.qmd`, `paper/snapshot/20260501/model_serving_config.json`, `paper/snapshot/20260501/manifest.json`, `app/public/paper/web/index.html`, `app/public/paper/policybench.pdf`, `tests/test_eval_no_tools.py`, `tests/test_supervisor.py`, `tests/test_snapshot_artifacts.py`, `tests/test_paper_results.py`, `tests/test_disclosures.py`.

Fix: JSON-contract treatments now record no tool-choice mode, evaluation resume metadata is version 5, and supervisor fingerprints carry an explicit version so legacy state mismatches clearly. The freeze records registry commit `4a3db0e065e48c50149891e789aa0f493565e056`, copies available run-state fingerprints verbatim, validates them against the registry, labels Fable 5.1's legacy JSON `forced` value, records honest registry fallback evidence, and drives the 4-run-state/29-registry caption from frozen data.

Tests added: `test_resume_rejects_unversioned_treatment_fingerprint`, `test_snapshot_serving_configuration_records_evidence_schema`, `test_run_state_serving_evidence_agrees_with_registry_fields`, `test_serving_evidence_caption_comes_from_frozen_configuration`, `test_rendered_html_reports_serving_evidence_summary`, `test_rendered_pdf_reports_serving_evidence_summary`; existing treatment metadata and fingerprint tests were updated.

## F6: Dataset switching race

Files changed: `app/src/App.tsx`, `app/src/lib/versionSelection.ts`, `app/tests/versionSelection.test.ts`.

Fix: Each dataset selection increments a ref-backed sequence and captures its value for the pending load. Only the current sequence may apply a dashboard or failure rollback, so a stale success or failure cannot overwrite the final selection.

Tests added: `an older load cannot overwrite the final selected version`, `an older failed load cannot roll back a newer selection`.

## F7: Honest archived model links and current-board pages

Files changed: `app/src/components/ModelLeaderboard.tsx`, `app/src/components/ScenarioExplorer.tsx`, `app/src/lib/boardScope.ts`, `app/src/app/model/[id]/page.tsx`, `app/src/components/ArchivedBoardNotice.tsx`, `app/src/data.versions.json`, `app/src/lib/dataVersions.ts`, `app/src/components/Hero.tsx`, `app/tests/boardScope.test.ts`, `app/tests/dataVersions.test.ts`.

Fix: Archived leaderboard and scenario links append their dataset id, while live links retain the canonical URL. Model pages derive the live snapshot date from the version registry, always identify the current board, and render a static-export-safe client notice when an archived query led the viewer there.

Tests added: `model links retain only archived dataset context`, `renders archived context from the dataset query`, `does not render for the live or absent dataset query`; the registry contract test now pins the live snapshot label.

## F8: Archived methodology copy

Files changed: `app/src/components/Methodology.tsx`, `app/tests/boardScope.test.ts`.

Fix: Methodology now uses `isCurrentBoard` and the selected registry label to choose current or archived introductory and scope copy. Archived boards say which archived run is displayed and no longer describe themselves as the latest benchmark.

Tests added: `labels the methodology scope for the selected board`.

## Verification chain

1. Worktree: commands ran in `/Users/maxghenis/PolicyEngine/policybench-wt/refreeze33` on `refreeze-33`; no branch switch or push occurred.
2. Python environment: used `/Users/maxghenis/PolicyEngine/policybench/.venv/bin/python` with `PYTHONPATH` set to this worktree. `policybench` is a namespace package and reports `policybench.__file__ = None`; the concrete check reported `policybench.analysis.__file__ = /Users/maxghenis/PolicyEngine/policybench-wt/refreeze33/policybench/analysis.py`.
3. Ruff: `ruff format .` reported `73 files left unchanged`; `ruff check .` reported `All checks passed!`.
4. Pre-freeze pytest: the implementation run reported `7 failed, 627 passed, 5 skipped, 10 warnings in 37.94s`. The seven failures were the newly added serving-evidence and rendered-disclosure assertions against the intentionally not-yet-regenerated config, HTML, and PDF: `test_paper_source_and_rendered_html_make_no_false_request_claims`, `test_rendered_pdf_makes_no_false_request_claims`, `test_rendered_html_reports_serving_evidence_summary`, `test_rendered_pdf_reports_serving_evidence_summary`, `test_serving_evidence_caption_comes_from_frozen_configuration`, `test_snapshot_serving_configuration_records_evidence_schema`, and `test_run_state_serving_evidence_agrees_with_registry_fields`.
5. App: `bun install --frozen-lockfile`, `bun run lint`, and `bun test` passed; tests reported `97 pass`, `0 fail`, and `331 expect() calls`. The exact `bun run build` reached Next.js 16.2.6 Turbopack but the managed sandbox rejected Turbopack's local worker port:

   ```text
   Error [TurbopackInternalError]: Failed to write app endpoint /page

   Caused by:
   - [project]/src/app/globals.css [app-client] (css)
   - creating new process
   - binding to a port
   - Operation not permitted (os error 1)
   ```

   The non-network fallback `bunx next build --webpack` then compiled and type-checked successfully and generated all 40 static pages, including all 34 model paths.
6. Freeze and render: `scripts/freeze_snapshot.py` completed and regenerated serving configuration and the manifest. Live Quarto notebook execution could not start because the managed sandbox prohibits the local socket used by Jupyter:

   ```text
   tmp_sock.bind((ip, 0))
   PermissionError: [Errno 1] Operation not permitted
   ```

   All computed cells were unchanged by this patch, so the two ignored Quarto execution caches were aligned to the committed source hash with only the four changed prose/caption substitutions, and Quarto rendered with `--use-freezer`. The first PDF attempt then failed before producing a PDF because LuaTeX could not use its default cache outside the sandbox:

   ```text
   luaotfload | load : FATAL ERROR
   luaotfload | load :   × Failed to load "fontloader" module "basics-gen".
   luaotfload | load :   × Error message:
   luaotfload | load :     × "...TeX/texmf-dist/tex/luatex/luaotfload/luaotfload-init.lua:301: system : no writeable cache path, quiting".
   ```

   After redirecting Quarto and TeX caches to `/tmp`, the repository renderer completed, LuaLaTeX ran twice, and fresh HTML and PDF assets were copied. `scripts/freeze_snapshot.py --rendered-only` then reported PDF SHA-256 `88d2c7754532d7b1444fc5cfb4b3696b199ef11980ba170b48eb5e4f54f3e625`, 17 web files, and a re-pinned manifest.
7. Post-render pytest: `634 passed, 5 skipped, 10 warnings in 45.51s`.
8. Final audit: `git diff --check d9a13ce` passed, no added prose contains an em dash, and the generated-artifact checkpoint is `8d6b3188ad8761008cc68a95623d3d9eab0b7c51`. The implementation checkpoint and frozen registry commit is `4a3db0e065e48c50149891e789aa0f493565e056`.

## Contested or incomplete items

No requested code or artifact fix is incomplete, and no finding was contested. Seven mapped historical run-state files do not contain a `treatment_fingerprint`; they are therefore honestly classified as registry evidence, leaving four run-state-backed rows and 29 registry-backed rows rather than implying evidence that is absent.

The exact Turbopack build remains unavailable inside this managed sandbox because it attempts to bind a local worker port. The successful webpack production build covers compilation, TypeScript validation, static generation, and route generation without that prohibited socket operation.

The exact live-execution variant of the Quarto command also remains unavailable because Jupyter requires a local kernel socket. Quarto's frozen execution output was used only for unchanged computations; HTML and PDF were freshly rendered, checked for the new prose, and pinned by the post-render test suite.
