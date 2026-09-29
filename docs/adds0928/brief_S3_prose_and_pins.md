# Stage 3 brief: prose, notes, paper and pins for release dashboard-data-20260929

You are working in `/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2`, branch `adds-0928-stage2`, in place. The release data is already frozen and committed (HEAD 49175d0f). Your job is every documentation, app-copy, note, paper and test-pin change the release needs, so that the full test suite, the app checks and the paper render pass. Do not change data, references, exclusions, adjudications, the payload or the frozen snapshot, except through the documented regeneration commands below.

Read the repository's `CLAUDE.md`. Also read `docs/adds0928/stage2_design.md` ("Before rendering, write a new September 28 note...") and `reference_audit/2026-09-28/README.md`.

## What changed in this release (verified facts; cite only these or what you verify yourself)

- **Release.** `dashboard-data-20260929`: 45 models (the 42 of 20260922c plus Claude Sonnet 5.5, Grok 4.7 and DeepSeek V4.1 Flash), 100 households, 1,984 outputs, 1,929 scored, 55 excluded (was 1,932 and 52). The payload sha256 is `e7d5e056b53c0d6d406bb3afb389aeaf80ebb611932ce72c8b3c3ceaef5ddad6` (`app/src/data.artifact.json`).
- **Reference engine.** References now come from policyengine-us **2.15.17**, the newest on PyPI (uploaded 2026-09-29 00:23 UTC). Max's ruling, 2026-09-28: "we should be using the latest pe for this always!"
  - policyengine.py 6.1.2 is recorded for provenance only. Its certified US bundle is policyengine-us 2.2.1, and it will not import next to 2.15.17. PolicyBench has always computed references with `policyengine_us.Simulation`.
  - The pre-freeze publication rule still holds, with the nine conventions re-expressed for 2.15.17. Read `reference_audit/2026-09-28/README.md` for the exact changes. Do not restate mechanisms beyond what that README and its record say.
- **Reference changes against 20260922c.**
  - 4 scored references changed: 008 NJ refundable credits 5,342.40→5,842.40; 013 AZ SNAP 0→240; 028 PA reduced-price school meals 1→0; 082 NY refundable credits 650.50→667.00.
  - 3 outputs newly excluded as unlisted-input readings: 033, 078 and 117 federal income tax (taxability of a listed state and local tax refund).
  - 2 moved by under $1: 078 and 117 state income tax.
  - 19 excluded outputs were re-reviewed and stay excluded.
- **Staged results** (weighted exact-match share; from `results/local/adds0928-v3/data-board45.json` and `incumbent-drift.json`; recompute from the frozen payload rather than trusting these):
  - Claude Sonnet 5.5: 91.973%, rank 4 of 45. It is 0.015 points ahead of GPT-6 Luna (91.958%), so describe that as about level, never as a clear lead.
  - Grok 4.7: 88.228%, rank 12. DeepSeek V4.1 Flash: 87.274%, rank 15.
  - The top 3 are GPT-6 Sol 94.813, Claude Opus 5.5 93.507 and GPT-5.6 Sol 93.280.
  - Every incumbent's exact rate rose 0.36 to 0.54 points under the new references. The top eight incumbents keep their order, and 6 incumbents change rank.
  - Cost per household: Sonnet 5.5 about $0.034, Grok 4.7 about $0.26, DeepSeek V4.1 Flash about $0.024 (confirm from the payload).
- **Treatments.** Sonnet 5.5 uses the JSON answer contract with adaptive thinking; see `policybench/model_cards.py` and `model_serving_config.json`. Grok 4.7 uses a 1,800-second request timeout. DeepSeek V4.1 Flash is served through the moving `deepseek-flash` alias. The design doc's risk section says how to disclose that; follow it.
- **BBCE follow-up** (for the BBCE note update and the release note). Verify each figure from the frozen predictions before using it.
  - The four income-held BBCE households (CT 027, TX 030, MI 073, WI 108; reference $288 each) now have 45 models' answers.
    - Sonnet 5.5 answers CT $388 (citing BBCE), TX $1,208, MI $0 and WI $0. Its TX explanation says "I counted wages only and treated the assistance amounts as excluded", the same income error and amount as Claude Opus 5.5 and GPT-6 Sol.
    - Grok 4.7: CT $276 (citing BBCE), TX $0, MI $0, WI $0.
    - DeepSeek V4.1 Flash: CT $0, TX $588, MI $0, WI $0.
    - None of the three gets any of the four exactly right.
  - The references now add a fifth household held back by income: Arizona 013. Arizona raised its expanded categorical eligibility gross limit from 185% to 200% of the poverty guideline from benefit month 03/2026, and the reference is $240 ($24 a month, March to December). Every one of the 45 models answers $0 for it.
  - The asset-held households (008, 054, 066, 080): Sonnet 5.5 answers above $0 for all four, Grok 4.7 for all four, and DeepSeek V4.1 Flash for three of four. The savings-versus-income split in the note holds for the new models.

## Deliverables

1. **A new release note** in `app/src/notes/`, dated 2026-09-29, registered in `app/src/notes/index.ts`, following the existing notes' JSON structure (read `2026-09-22-gpt-6-sol-debuts-first.json` and `2026-09-22-reference-audit.json`) and the voice and fact-pinning of `tests/test_notes.py`.
   - Cover the three additions and the move to the newest PolicyEngine, including what changed and why, the new exclusions, and the incumbent drift.
   - Every number in the note must be a fact the tests recompute from committed data. Add the tests.
   - Title in sentence case.
2. **A dated update to the BBCE note** (`2026-09-23-five-snap-households-bbce.json`). Add an update paragraph with the new models' results and the Arizona household, and link the new release. Keep its historical figures, which are tied to release 20260922b/c, as they are, and keep its tests passing. If the update needs data files, add them under `notes/data/` with tests.
3. **The paper and its render.**
   - Update `paper/index.qmd` and `docs/paper.md` for 45 models, 1,929 scored, 55 excluded, the reference engine, the 2026-09-28 upgrade and the response window.
   - Render with `uv run python paper/render_paper.py` (or `.venv/bin/python`, see below), then re-pin with `scripts/freeze_snapshot.py --rendered-only`.
   - Keep historical statements about earlier releases true to those releases.
4. **The benchmark card, methodology copy and other docs.**
   - Update `docs/benchmark_card.md`, the app components that state counts or the engine version (for example `app/src/components/Methodology.tsx`, `ExclusionNote.tsx`) and `app/src/data.versions.json`'s description, which still says policyengine-us 1.755.4.
   - Update the sensitivity docs whose tables `tests/test_sensitivity_evidence.py` compares against the rescored summaries (already committed), and the cost report the costs test checks.
   - Refresh the app copy of the serving config (`app/src/model-serving-config.json`) from `paper/snapshot/20260501/model_serving_config.json`, as prepare-data does.
5. **Test pins.**
   - Update tests that pin facts of the live release (counts such as 42 models, 63 adjudications, 7,545 rows, 39 usage rows, 1,932/52) to this release's values. Recompute each new value from the frozen artifacts; never copy a failing assertion's number blindly.
   - Leave pins that belong to earlier releases' notes or records alone.
   - `tests/test_paper_results.py::test_frozen_roster_has_42_display_names_and_release_dates` becomes 45. The new models' display names and release dates are already in `policybench/paper_results.py` and `app/src/modelMeta.ts`: Grok 4.7 released 2026-09-21, DeepSeek V4.1 Flash 2026-09-10, and Sonnet 5.5 as recorded there.

## Voice (public copy: notes, paper, card, methodology copy)

Before writing any prose, read Max's voice guide `~/.claude/projects/-Users-maxghenis/memory/voice_max.md` (its "Current rules") and the working model `~/.claude/projects/-Users-maxghenis/memory/user_max_working_model.md`, and apply them to every string you write or change. In particular:
- active voice, with the actor in the subject;
- one thought per sentence, with varied rhythm;
- no self-referential clauses and no empty "X, not Y" antithesis;
- no superlatives or intensifiers, and numbers over adjectives;
- sentence-case headings;
- finished work introduces itself fresh: the paper and card state what the benchmark does now, with no draft or review lineage;
- release notes and corrections take the change as their subject and keep the numbers;
- no policy positions, not even hints.

When a reviewer would flag one sentence, reread the whole document for the pattern. Keep each note's existing structure and register (third person, "PolicyBench …").

## Rules

- **No fabricated claims.** State only what you read in committed code or data, or computed yourself. When a number comes from the payload, compute it.
- **Voice.** Match the existing notes and paper: plain, specific, third person ("PolicyBench …"). Use sentence-case headings. Don't guess at unrecorded figures.
- **Workflow.**
  - Run `ruff format` and `ruff check .` (reference_audit/ is excluded).
  - Run the full `pytest -q`, and the app's `bun install --frozen-lockfile`, `bun run test`, `bun run lint` and `bun run build` in `app/`.
  - Use the worktree's `.venv` (Python 3.12, policyengine-us 2.15.17) with `OPENBLAS_NUM_THREADS=1` and `PYTHONPATH=$PWD`.
  - The machine is shared and heavily loaded, so run the big steps serially.
- **Commits.**
  - Make coherent commits on `adds-0928-stage2`, each message ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - Do not push, open PRs, upload release assets, or post anything.
  - Do not edit `reference_audit/`, the frozen snapshot data files, the references or the adjudications.
- **Report.** End with a report listing every file changed, every test pin changed with old→new and where the new value came from, and the final results of pytest and the app checks. Write it to `docs/adds0928/report_S3.md` and commit it.
