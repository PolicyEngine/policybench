# Stage 3c brief: exclude scenario_023 head_medicaid_eligible; harden the gates

Work in `/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2` (branch `adds-0928-stage2`, HEAD f7ced3b3), in place. The lead's pre-merge review of PR #182 confirmed one blocker and several minors. Evidence is in `docs/adds0928/review_pr182_2026-09-29.json`; read it first.

Also read:
- `docs/adds0928/brief_S3b_review_fixes.md`, for the regeneration chain, the Voice rules and the other Rules;
- the repo `CLAUDE.md`;
- Max's voice guide `~/.claude/projects/-Users-maxghenis/memory/voice_max.md`.

Python: `.venv/bin/python` with `OPENBLAS_NUM_THREADS=1 PYTHONPATH=$PWD`. The machine is disk-starved and heavily loaded. Run the heavy steps serially, never make copies of large files, and delete any scratch you create.

## The decision (already made; apply it)

`scenario_023 head_medicaid_eligible` joins the exclusions as `reference_depends_on_unlisted_input`, with `unlisted_input` = `meets_ssi_disability_criteria`. This is the same input and reason that already exclude this household's SNAP.

The basis is on the record:
- The excl_snap_ssi_disability investigation (`reference_audit/2026-09-28/clusters.json`) flags it out of cluster: "the lead should review it".
- Its independent review agrees (`verification/reviews/excl_snap_ssi_disability.md`).
- The investigation's own analysis supports it. The head's MAGI is 141.2% of FPL, above the 138% adult limit, so Medi-Cal is reachable only through a disability pathway. California's 250% Working Disabled Program requires the federal (SSA) definition of disability, 42 CFR 435.540(a), and that definition is the unlisted input.
- Reading A (the head does not meet the SSI/SSA disability criteria) gives 0. Reading B gives 1, which is the engine's value on 2.15.17, category WORKING_DISABLED_BUY_IN.
- Rule 4 of `reference_audit/2026-09-28/README.md` says such an output is excluded.

Before recording anything, verify both values yourself on 2.15.17 with `fixes/latest_final.py`, using the probe approach in the review evidence. Record exactly what you computed.

## 1. Record and apply the exclusion

- **`reference_exclusions.json`.** Add the entry, following the scenario_023 SNAP entry's schema:
  - `frozen_value` 1.0, `alternative_value` 0.0;
  - `engine_version` "policyengine-us 2.15.17";
  - `decided_on` "2026-09-29";
  - `alternative_reading` and `note`, each stating what you computed and the legal basis.
  - Exclusion entries decided before this wave stay unchanged.
- **Audit record (`reference_audit/2026-09-28/`).**
  - Record the disposition of the out-of-cluster flag: a `reconciliations`-style entry in `clusters.json`, plus an `audit_exclusions` list in `final_actions.json` naming this output and its basis.
  - Add `verification/reviews/pr182_review_023.md` with the review's reasoning and your computed values.
  - Update `README.md`: counts (56 exclusions, 1,928 scored, 28 unlisted-input; recompute every count), a short "Also excluded on review" paragraph, and rule text if needed.
  - The engine-upgrade revision's `changed` list stays exactly the engine changes. This exclusion is a separate, listed audit decision, not an engine change.
- **Case annotations.** The published case note for this output (`annotations/.../us_case_notes.csv`, the row that calls the 22 zero answers `llm_error` "None of them considered the employed-disabled buy-in") must not survive as a scored-error note. Let triage rebuild it the way it handles every other excluded output. Check the result.

## 2. Harden the gates (review minors; each needs a failing-then-passing test)

In `scripts/finish_adds0928.py`:
- **`reference_revision()`.** Also compare `impact_weight` (and every other column) against the 22c base. Any difference not listed is refused.
- **Exclusion set.** Require exact set equality in `resolve_base`, and after the freeze in `resolve_live_base`/`export`: the 22c exclusion keys (from BASE_COMMIT), plus the revision's newly excluded keys, plus the `audit_exclusions` keys in `final_actions.json`, and nothing else. A swapped or extra exclusion must be refused. Replace the count-only check (`52 + added`).
- **Replay gate.** Add a test where an incumbent's modelStats drift on the 22c references, and the export must refuse. The review showed that turning `replay_base_references` into a no-op leaves all 64 tests passing.
- **Drift attribution.** The drift report and every public claim that says "the only cause is the reviewed reference revision" must now name both causes: the revision and the one audit exclusion. The replay still proves incumbents reproduce on the 22c references. Word it accurately.

In `tests/`:
- **`test_reference_upgrade.py:125`.** A 0/1 flag change of exactly 1 must not be exempt as "within $1". Match `paper_results.moves_beyond_tolerance`.
- **`test_disclosures.py`.** Split the paper-claim tests at lines 605 and 636 so the HTML assertions run in CI, and only the PDF part skips without pypdf/pdftotext.
- **Sweep-timing test (`test_reference_upgrade.py`, the pin-commit check).** After the squash merge the pin commit leaves main's history. Make the skip message say exactly that. Also assert, without git, that the recorded pin time precedes the sweep start and follows 2.15.17's upload, so the check keeps running.
- **Sidecar reasons.** The 19 `excluded_outputs_rechecked` reasons are cut at 600 characters.
  - Store the reviewers' full `corrected_per_output` text instead, taken deterministically from `clusters.json`.
  - Use the documented install path (`scripts/install_adds0929_references.py` accepts record-text-only changes), and fix the truncation in `build_references_latest.py`.
  - Add a test that each recorded reason equals the full reviewer text.
  - If regenerating the sidecar needs a full 1,984-output recompute on this machine, patch the text with a small committed script instead. The install check must still prove that only record text changed.

## 3. Regenerate and update every public figure

Run the chain in `brief_S3b_review_fixes.md` ("Regenerating after data-adjacent fixes"):
- triage, export (keeping the 22c replay gate), freeze dry-run, freeze;
- `paper/render_paper.py`;
- `freeze_snapshot.py --rendered-only`.

Then update everything that states a now-stale figure, recomputing each value from the frozen artifacts:
- **The release note.** Recompute Sonnet 5.5's rank. If it is no longer 4th, rename the note file and its slug to match, e.g. `2026-09-29-claude-sonnet-5-5-debuts-fifth.json`, and update `app/src/notes/index.ts` and every reference. The title's ordinal is test-pinned to `facts['sonnetRank']`. Describe the gap to its neighbor as about level if it is under 0.1 points.
- **Other copy:** the BBCE note update (check whether anything moved), the paper, `docs/paper.md`, `docs/benchmark_card.md`, the app Methodology copy, `app/src/data.versions.json`, and the sensitivity docs.
- **Test pins:** recompute every one; never copy a failing number.

Report the new payload sha256. The release asset will be replaced by the lead, not by you.

## Rules

- Do not push, upload, open PRs, or call any model or provider API.
- Make coherent commits, each ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Done means:**
  - `pytest -q -m "not slow"` passes.
  - The app checks pass: `bun install --frozen-lockfile`, `bun run test`, `bun run lint`, `bun run build` in `app/`.
  - `ruff check .` and `ruff format --check .` pass.
  - The paper renders.
- **Final answer:**
  - every change, with its file and finding;
  - every moved pin, as old → new, with the source of the new value;
  - the computed values for the exclusion;
  - the new ranks of the three additions and of the top five;
  - the new payload sha256;
  - the test and app results, verbatim.
