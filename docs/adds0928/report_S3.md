# Stage 3 report: prose, notes, paper and pins for release dashboard-data-20260929

Written by the stage-3 implementer (Claude Code workflow wf_c63fb075-f87, Opus 5.5), then a voice pass. The harness kept the implementer from writing this file, so the lead recorded its returned report here.

## Commits

- b3ef6247 Pin release 20260929's counts in the tests, sensitivity doc and app
- e615e5e8 State the 45-model board and the policyengine-us 2.15.17 references in the card and app copy
- 0833778f Update the paper for the 45-model board on policyengine-us 2.15.17, render and re-pin it
- 10edbe9c Add the September 29 release note and update the BBCE note for release 20260929
- 7e192f6d Put the actor first in the paper's engine paragraph and the card's engine sentence; re-render and re-pin
- 756ce4f2 Voice pass on the release-20260929 prose; re-render and re-pin the paper

## Files changed

- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/app/src/notes/2026-09-29-claude-sonnet-5-5-debuts-fourth.json (new release note)
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/app/src/notes/index.ts
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/app/src/notes/2026-09-23-five-snap-households-bbce.json (dated update: 2 paragraphs, 10 update* facts, 4 links; 20260922b figures unchanged)
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/notes/data/bbce_households_20260929.csv (+ .meta.json; 45 models x 5 income-held households incl. AZ 013)
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/notes/data/bbce_asset_households_20260929.csv (+ .meta.json; 45 x 4 savings-held households)
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/scripts/bbce_households_20260929.py (new; writes both CSVs)
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/paper/index.qmd
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/policybench/paper_results.py (engine_upgrade_* properties, previous_policyengine_us_version, reference_rebuilt_date; regenerated_reference_* restricted to convention/upstream_fix; dataset_* read from the scenario draw)
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/app/public/paper/policybench.pdf, app/public/paper/web/index.html, app/public/paper/web/figures/positive_zero_scatter.png (render)
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/paper/snapshot/20260501/manifest.json (rendered_paper_artifacts only, via --rendered-only)
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/app/src/paperSnapshot.json (re-pin)
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/docs/benchmark_card.md (new Reference outputs section; audit/exclusion/adjudication counts; snapshot date; Sonnet 5.5 and DeepSeek V4.1 Flash in the rejects-forced-tool list)
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/docs/paper.md
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/docs/artifacts.md
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/sensitivity/claude-thinking-2026-08.md
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/app/src/components/Methodology.tsx (Ten of the 45; engine version read from the board payload)
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/app/src/components/ModelLeaderboard.tsx
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/app/src/data.versions.json (description: Reference outputs from policyengine-us 2.15.17)
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/app/src/lib/servingSensitivity.ts
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/app/src/model-serving-config.json (refreshed from frozen file by prepare-data)
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/tests/test_adjudications.py
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/tests/test_disclosures.py
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/tests/test_paper_results.py
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/tests/test_report_costs.py
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/tests/test_sensitivity_evidence.py
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/tests/test_snapshot_artifacts.py
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/tests/test_notes.py (release-note test pinning every sentence; drift-baseline rebuild test vs git cb312fd7; BBCE update test)
- /Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/app/tests/auditUniverse.test.ts, boardScope.test.ts, dataVersions.test.ts, expandPage.test.ts, heatmapMetric.test.ts, programChart.test.ts, servingSensitivity.test.ts

## Test pins changed (old → new; source)

- tests/test_adjudications.py::test_committed_record_is_applied_to_the_frozen_annotations (entries): 63 → 68 (annotations/.../us_adjudications.json)
- test_adjudications (adjudicated classes prompt_ambiguity/llm_error/engine_defect): 24/11/28 → 27/13/28 (us_adjudications.json; new check: llm_error by reference_verdict = affirmed 5, regenerated 6, none 2 (007 federal, 008 NJ later-law resolutions))
- test_adjudications (excluded_from_scoring entries; manifest reference_exclusions.outputs): 52; 52 → 55; 55 (us_adjudications.json; manifest)
- test_adjudications (manifest developer_adjudications.cases / by_judge_verdict): 63 / llm_error 44, prompt_ambiguity 2, reference_engine_defect 11, reference_model_issue_fixed 6 → 68 / llm_error 49, prompt_ambiguity 2, reference_data_issue_fixed 1, reference_model_issue_fixed 16 (paper/snapshot/20260501/manifest.json (equals entries' judge classes))
- tests/test_paper_results.py::test_frozen_roster_has_45_display_names_and_release_dates (renamed from _42_): 42 → 45 (+ Sonnet 5.5 2026-09-28, Grok 4.7 2026-09-21, DeepSeek V4.1 Flash 2026-09-10) (payload modelStats; policybench/paper_results.py registry)
- test_paper_results::test_parse_contract_failure_counts_come_from_frozen_dashboard: kimi-k2.6 394; total 657 → kimi-k2.6 391; total 654 (payload rows on scored outputs (3 newly excluded outputs leave the count))
- test_paper_results::test_audit_universe_counts_come_from_frozen_rows_and_annotations: 7,545 / 7,541 / 7,541 / 4 / 1,843 → 7,796 / 7,792 / 7,792 / 4 / 2,027 (payload + us_audit_row_annotations.csv)
- test_paper_results::test_contract_violations_are_counted_both_ways: grok-4.3 56; 61; 718 → grok-4.3 55; 60; 714 (payload)
- test_paper_results::test_serving_evidence_caption_comes_from_frozen_configuration: 13/13/12/13; three rows → 16/16/15/16; six rows; summary registry 29, run_state 16 (paper/snapshot/20260501/model_serving_config.json)
- test_paper_results::test_serving_evidence_counts_exclude_legacy_or_unrecorded_fields: 12 -> 13; 12 → 15 -> 16; 15 (model_serving_config.json)
- test_paper_results::test_joint_credit_accuracy_exceptions_come_from_frozen_table: Astra [100,89.7,89.7], GPT-6 Sol [99,88.7,88.7], GPT-5.6 Sol [99,87.6,87.6]; 5 exceptions → Astra [100,88.7,88.7], GPT-6 Sol [99,87.6,87.6], Grok 4.7 [99,87.6,87.6], GPT-5.6 Sol [99,86.6,86.6]; 6 exceptions (Grok 4.7 added) (payload federal/state refundable credit predictions)
- test_paper_results::test_joint_credit_accuracy_prose_tracks_changed_table_exceptions: 4 exceptions → 5 exceptions incl. Grok 4.7 (same table)
- test_paper_results::test_judge_provenance_is_frozen_in_the_manifest: opus-5 183, opus-5-5 171, sol 314, total 668 → opus-5 132, opus-5-5 239 (judged_on includes 2026-09-29), sol 303, total 674 (manifest audit_annotation_artifacts.judge_provenance)
- test_paper_results::test_joint_credit_table_orders_ties_deterministically: 87.6 tie: GPT-5.6 Sol, GPT-6 Luna → 88.7 tie: GPT-6 Astra, GPT-6 Luna; 87.6 tie: GPT-6 Sol, Grok 4.7 (joint table, ties broken by model id)
- test_paper_results::test_excluded_outputs_are_outside_the_scored_audit_universe: 52 / '52 outputs' / '36 households' / unlisted 24 / 1,932 / 1793 / 616 / n 1932 → 55 / '55 outputs' / '39 households' / unlisted 27 / 1,929 / 2041 / 780 / n 1929; SALT-refund unlisted input 3; regenerated 26 kept (household 24, SNAP 13 added) (reference_exclusions.json, annotations, payload, sidecar convention+upstream_fix revisions)
- test_paper_results::test_engine_upgrade_counts_come_from_the_reference_sidecar (new): - → 2.15.17 from 1.755.4; date 2026-09-28; scored changes 4; within tolerance 2; new exclusions 3; rechecked 19; NJ 5342.40->5842.40, AZ 0->240, PA 1->0, NY 650.5->667 (reference_outputs.csv.meta.json engine_upgrade revision)
- test_paper_results::test_dataset_build_is_the_one_the_households_came_from (new): - → populace-us-2024-5da5a95-20260611 (scenarios.csv.meta.json and population_weights.json)
- tests/test_snapshot_artifacts.py::test_snapshot_deviation_audit_annotations_are_complete_and_final: 7,545/7,541/7,541/4/9,388/1,843; llm_error 6,888, parse 657 → 7,796/7,792/7,792/4/9,823/2,027; llm_error 7,142, parse 654 (payload + annotations)
- tests/test_disclosures.py::test_audit_disclosures_use_the_frozen_legacy_threshold_universe: 7,545/7,541/7,541/4/1,843 → 7,796/7,792/7,792/4/2,027 (payload + annotations)
- tests/test_report_costs.py::test_frozen_report_discloses_recorded_subtotal_and_published_total: 39 / 42 / 416.523 / 480.602 → 42 / 45 / 448.339 / 512.418 (analysis/usage_summary.csv, payload modelStats; lines already in frozen analysis/report.md)
- tests/test_sensitivity_evidence.py::test_doc_table_ranks_match_the_frozen_45_model_board (renamed): '42-model board (2026-09-22)', 42 rows → '45-model board (2026-09-29)', 45 rows (payload; doc table values from rescored sensitivity/data/*.json)
- tests/test_notes.py CURRENT_RELEASE_SNAPSHOT / SUPERSEDED_RELEASES: 2026-09-22 / (no 22c) → 2026-09-29 / + dashboard-data-20260922c (manifest snapshot_date)
- app/tests/auditUniverse.test.ts: 7,545/7,545/7,541/7,541/4/1,843 → 7,796/7,796/7,792/7,792/4/2,027 (app data summary from frozen payload)
- app/tests/boardScope.test.ts: Ten of the 42 models → Ten of the 45 models; + engine sentence 'PolicyEngine-US (policyengine-us 2.15.17) computes' (serving config (10 chunked of 45); payload policyengineBundles)
- app/tests/dataVersions.test.ts: Snapshot 2026-09-22 → Snapshot 2026-09-29 (app/src/data.versions.json (written by freezer))
- app/tests/expandPage.test.ts: leader 94.278; '94.3%' → 94.813; '94.8%' (data summary)
- app/tests/heatmapMetric.test.ts: Fable 5.1 federal exact 76 → 79 (data summary heatmap (82 scored federal outputs))
- app/tests/programChart.test.ts: 76.5; width 76.47058823529412% → 79.3; width 79.26829268292683% (data summary)
- app/tests/servingSensitivity.test.ts: rank 6; 'auto 90.9 · #6'; '+7.4 against its 83.5%'; Fable 5.1 'auto 91.1 · #6'; delta +7.4 → rank 7; 'auto 91.4 · #7'; '+7.5 against its 83.9%'; 'auto 91.6 · #7'; delta +7.5 (rescored sensitivity summaries (servingSensitivity.ts autoExact 91.414/89.905/84.695/91.646))

## Results

- pytest (implementer): 955 passed, 6 skipped, 11 warnings in 67.26s (0:01:07)
- app checks: bun install --frozen-lockfile: ok (no changes); bun run test: 149 pass, 0 fail; bun run lint: exit 0 (eslint --max-warnings=0); bun run build: exit 0, compiled; the new note page /notes/2026-09-29-claude-sonnet-5-5-debuts-fourth prerenders. Also ruff format --check (103 files formatted), ruff check (all passed), git diff --check clean. Final paper PDF sha256 69a9679a32a217669cb06aec46309fd067b8ba21288055d37216237d25499935 (web index.html key 4bb46077... replaced by the final render; manifest and paperSnapshot.json re-pinned).
- paper rendered: True
- pytest (after voice pass): 955 passed, 6 skipped, 11 warnings in 108.28s (after re-render and re-pin; OPENBLAS_NUM_THREADS=1, PYTHONPATH=$PWD, worktree .venv). App: bun test tests shows 149 passed, 0 failed. ruff format and check are clean on tests/test_notes.py. Left unchanged, and outside a wording-only pass: docs/paper.md still says reference_output_refresh carries "the certified US populace dataset's build id". However, the implementer's own comment in policybench/paper_results.py says that block records the reference runtime's default dataset (populace-us-2024-spm-20260915), which can differ from the certified build the households were sampled from. That fact needs checking. Commit 756ce4f2 on adds-0928-stage2 is not pushed.

## Voice pass edits

- 2026-09-29-claude-sonnet-5-5-debuts-fourth.json: superlative / adjective without a number
- 2026-09-29-claude-sonnet-5-5-debuts-fourth.json: sentence a reader would read twice
- 2026-09-29-claude-sonnet-5-5-debuts-fourth.json: passive voice / inanimate actor where PolicyBench acts
- 2026-09-29-claude-sonnet-5-5-debuts-fourth.json: passive participle where an actor exists
- 2026-09-29-claude-sonnet-5-5-debuts-fourth.json: sentence a reader would read twice (double 'from', dangling 'which')
- 2026-09-29-claude-sonnet-5-5-debuts-fourth.json: name the actor and action (actorless abstraction)
- 2026-09-29-claude-sonnet-5-5-debuts-fourth.json: split a 50-word sentence; passive voice where an actor exists
- 2026-09-29-claude-sonnet-5-5-debuts-fourth.json: sentence a reader would read twice (the colon list was attached to the wrong clause)
- 2026-09-29-claude-sonnet-5-5-debuts-fourth.json: be-verb identity replaced by a real verb; name the actor
- 2026-09-23-five-snap-households-bbce.json: sentence a reader would read twice
- 2026-09-23-five-snap-households-bbce.json: split a sentence a reader would read twice; be-verb replaced with a verb
- index.qmd: passive voice where an actor exists; sentence a reader would read twice
- index.qmd: superlative in a label; passive chain; sentence starting with a numeral
- index.qmd: inanimate actor replaced by the real actor
- index.qmd: sentences a reader would read twice (garden path 'read from 40 hours', stacked relative clauses); passive voice
- index.qmd: passive voice where an actor exists; inanimate actor
- index.qmd: passive voice where an actor exists; sentence a reader would read twice
- benchmark_card.md: passive voice; be-verb identity; ambiguous 'it'
- benchmark_card.md: sentence a reader would read twice (a list of causes followed a colon after 'references')
- benchmark_card.md: sentence a reader would read twice (an internal class label used as prose)
- benchmark_card.md: inanimate actor; passive voice where an actor exists
- paper.md: passive participle where an actor exists
- test_notes.py: pinned phrase updated to carry the same fact

## Open problems the implementer reported

- docs/adds0928/report_S3.md is NOT committed. The harness refused the write ('Subagents should return findings as text, not write report files'), so this output carries the report: all files, every pin old->new with its source, and the results. The orchestrator should write and commit it if the release needs that file.
- Where the brief differs from the frozen artifacts (the artifacts win). (1) Incumbent drift is +0.3621 (Kimi K2.6) to +0.5349 (GPT-6 Sol). That rounds to 0.36 to 0.53, not the brief's 0.54, and the note says 0.53. (2) Among the 42 incumbents, only three neighbor pairs swap, at positions 16/17, 25/26 and 31/32: Opus 5 over Fable 5, Gemini 3 Flash Preview over Opus 4.7, and DeepSeek V4 Pro over Gemini 3.1 Flash Lite Preview. So six models change rank, which matches the brief, and the top 15 keep their order, not only the top eight. The note names the three swaps. (3) With the engine-upgrade revision in the sidecar, paper_results.regenerated_reference_count would have become 34. I restricted it to the September 22 convention and upstream-fix revisions (26) and added engine_upgrade_* properties. Every other staged figure checked out: Sonnet 91.973 (#4, 0.0155 above Luna 91.958), Grok 88.228 (#12), Flash 87.274 (#15), the top three, the costs ($0.0343, $0.2597, $0.0242) and all the BBCE figures.
- Frozen manifest mechanism error, left unfixed. The reproducibility note says 'Reference outputs were generated with policyengine.py 6.1.2 and policyengine-us 2.15.17 against the certified PolicyEngine US populace dataset (populace-us-2024-spm-20260915...)'. In fact the references come from policyengine_us.Simulation on each household's own inputs, and policyengine.py is recorded only for provenance. The sentence comes from the build_manifest template in scripts/freeze_snapshot.py, and correcting it needs that template fixed plus a full refreeze. I did not edit the frozen manifest.
- Dataset build mismatch. The manifest's reference_output_refresh records populace-us-2024-spm-20260915, which is the policyengine.py 6.x bundle's default dataset. The households and the population weights come from populace-us-2024-5da5a95-20260611. paper_results.dataset_* now read the scenario draw's build, and a new test pins this. The manifest field itself is unchanged.
- Pre-existing paper render bug, not fixed. The cost-and-latency sentence renders a literal '\\\\$0.002' and the cost table renders '\$0.034', in both the HTML and the PDF. The previous render has the same problem.
- DeepSeek alias provenance review is still open. The stage-2 design asks for a substantive review before release. Every one of the row's 1,984 answers reports only 'deepseek-flash' and one system fingerprint (aeb56401ca74e127821c4f9126dcb669). The release note discloses this and labels the row from DeepSeek's September 10 release note.
- The release note and the BBCE update link the tag dashboard-data-20260929, which won't resolve until the release assets are uploaded. Upload stays outside this stage.
- Judgment calls a reviewer should confirm. (a) 'Across development and five audit waves': I raised it from four because the September 28 additions had their own judge wave, the same way PR #174 went from three to four. (b) The benchmark card now leaves out the September 22 regenerated-reference counts and the 22b/22c release history, following the fresh-introduction voice rule; the paper keeps that history.
- Environment change: I installed the project's locked dev and docs extras into the worktree .venv (uv sync --frozen --extra dev --extra docs --inexact) so Quarto could run Jupyter. policyengine-us stayed at 2.15.17 and policyengine at 6.1.2. prepare-data also downloaded the June 1.0 payload into app/.cache, which is untracked.
- On 'using my voice?': before writing any prose I read voice_max.md (current rules and standing bans) and user_max_working_model.md. I applied them to every string I added or changed: actor-first active voice, numbers over adjectives, no empty antithesis (Sonnet vs Luna is stated as '#4... GPT-6 Luna, #5, also rounds to 92.0%, less than 0.02 points behind'), no self-reference, sentence-case title, change-as-subject for the release and BBCE notes, and present-state wording in the paper and card. I also did one full-document pass. No independent Opus or Astra voice or fact review has run yet, and the CLAUDE.md rule calls for one before merge.

Two adversarial reviews (facts; tests) followed; their findings are consolidated in brief_S3b_review_fixes.md.
