# Stage 3 brief: note, paper, card and pins for release dashboard-data-20260930

Work in place in `/Users/maxghenis/PolicyEngine/policybench-wt/gpt61sol-driver`, branch `gpt61sol-driver`. The release data is already frozen and committed (`git log --oneline -3`). Your job is every documentation, app-copy, note, paper and test-pin change the release needs, so that the full test suite, the app checks and the paper render pass. Do not change data, references, exclusions, adjudications, the payload or the frozen snapshot, except through the documented regeneration commands below.

Read the repository's `CLAUDE.md`, `docs/gpt61sol/design.md` (the commands after the freeze are near its end) and, as the model for this job, `docs/adds0928/brief_S3_prose_and_pins.md` with its report `docs/adds0928/report_S3.md`. This release is smaller than that one: one model joins, and nothing else moves.

## What changed in this release (verified facts; cite only these or what you verify yourself)

- **Release.** `dashboard-data-20260930`: 46 models, the 45 of `dashboard-data-20260929` plus GPT-6.1 Sol. 100 households, 1,984 outputs, 1,928 scored, 56 excluded, all as in 20260929. The payload sha256 is in `app/src/data.artifact.json`.
- **Nothing else moved.** The references, the exclusions and every incumbent's statistics are release 20260929's, byte for byte; the driver and the freeze refuse anything else (`scripts/finish_gpt61sol.py` `incumbent_drift`, `scripts/freeze_gpt61sol.py` `verify_incumbent_stats`, `verify_references`). The release adds no adjudication.
- **Staged result** (weighted exact-match share; recompute from the frozen payload rather than trusting these):
  - GPT-6.1 Sol: 90.595%, rank 8 of 46, at about $0.023 a household. All 1,928 scored answers parsed.
  - Its neighbours: Claude Fable 5.1 90.828% (rank 7) and Kimi K3 90.435% (rank 9).
  - The top three keep their places: GPT-6 Sol 95.003%, Claude Opus 5.5 93.697%, GPT-5.6 Sol 93.572%. GPT-6 Sol costs about $0.027 a household.
  - So GPT-6.1 Sol scores about 4.4 points below GPT-6 Sol. State the gap; give no reason for it unless you can show one from committed data.
- **Treatment.** `policybench/model_cards.py` `gpt-6.1-sol`: the forced tool contract on the Responses API with provider-default reasoning, like GPT-6 Sol. `policybench/paper_results.py` and `app/src/modelMeta.ts` give its display name and its release date, 2026-09-29, the day OpenAI announced it. Prices are in `policybench/config.py`.
- **Failure-reason judges.** GPT-6.1 Sol joined 134 audit cases (cases where it missed), and an Opus 5.5 judge re-read each. `docs/gpt61sol/judge_provenance.json` records how each of those 134 verdicts was produced; read its note and use only what it says:
  - 60 ran isolated: from an empty directory outside the repository, with no tools and a token login, with an empty session context.
  - 74 ran through the earlier runner from inside the repository. Their transcripts show no file read, search or shell call, but each one's context carried the login's account e-mail, the repository's git status and a skill listing.
  - Scores do not depend on judge verdicts. The verdicts feed the published failure reasons (case notes and row annotations).
  - The note and the paper must disclose the 60 and 74 split plainly, and link the record.
  - A follow-up release (`dashboard-data-20260930b`, branch `judge-isolation-20260930b`) is planned for verdicts carried over from earlier releases. Do not describe it as done, and do not promise what it will do.
- **Wording amendments.** The release applies 394 wording-only amendments to published failure reasons in re-judged cases (`results/local/gpt61sol-v1/wording-amendments.json`, read only; the policy is in `docs/gpt61sol/design.md`). No class, exclusion or score changes through them. Mention them only if the paper or card already describes this mechanism for an earlier release; do not invent a description.

## Deliverables

1. **A new release note** in `app/src/notes/`, dated 2026-09-30, registered in `app/src/notes/index.ts`, following the structure of `2026-09-29-claude-sonnet-5-5-debuts-fifth.json` and `2026-09-22-gpt-6-sol-debuts-first.json`, and the fact-pinning of `tests/test_notes.py` (see `test_release_20260929_note` and its `_facts` helper).
   - Cover: GPT-6.1 Sol's score, rank and cost against GPT-6 Sol and its neighbours; its treatment; that nothing else in the release moved; and the judge disclosure above.
   - Every number in the note must be a fact a test recomputes from committed data. Add the tests. `CURRENT_RELEASE_SNAPSHOT` and the earlier release's "current release" tests need the same handover the 20260929 note got from 20260922c (`test_previous_release_scores_rebuild_from_this_snapshot` and its neighbours).
   - Title in sentence case. The slug follows the earlier ones: `2026-09-30-gpt-6-1-sol-debuts-<ordinal>`.
2. **The paper and its render.**
   - First run `scripts/sensitivity_by_variable.py` and `scripts/rescore_sensitivity_summaries.py --release dashboard-data-20260930`, as the design note lists.
   - Update `paper/index.qmd` and `docs/paper.md` for 46 models and the response window, and add the GPT-6.1 Sol row wherever the roster or serving table is prose.
   - Render with `paper/render_paper.py`, then re-pin with `scripts/freeze_snapshot.py --rendered-only`.
   - Keep statements about earlier releases true to those releases.
3. **The benchmark card, methodology copy and other docs.** Update `docs/benchmark_card.md`, the app components that state counts, `app/src/data.versions.json`'s description, and the app copy of the serving config (`app/src/model-serving-config.json`, refreshed from `paper/snapshot/20260501/model_serving_config.json` as prepare-data does). Update the sensitivity docs and the cost report the tests compare.
4. **Test pins.** Update tests that pin facts of the live release (45 models and whatever follows from it) to this release's values. Recompute each new value from the frozen artifacts; never copy a failing assertion's number. Leave pins that belong to earlier releases alone. `tests/test_paper_results.py::test_frozen_roster_has_45_display_names_and_release_dates` becomes 46.

## Voice (public copy: note, paper, card, methodology copy)

Before writing any prose, read Max's voice guide `~/.claude/projects/-Users-maxghenis/memory/voice_max.md` (its "Current rules") and the working model `~/.claude/projects/-Users-maxghenis/memory/user_max_working_model.md`, and apply them to every string you write or change. In particular:
- active voice, with the actor in the subject;
- one thought per sentence, with varied rhythm;
- no self-referential clauses and no empty "X, not Y" antithesis;
- no superlatives or intensifiers, and numbers over adjectives;
- sentence-case headings;
- the paper and card state what the benchmark does now, with no draft or review lineage;
- a release note takes the change as its subject and keeps the numbers;
- no policy positions, and no speculation about why a model scores as it does.

Keep the notes' register (third person, "PolicyBench …").

## Rules

- **No fabricated claims.** State only what you read in committed code or data, or computed yourself. Messaging docs and briefs, this one included, are claims: verify each figure above before you use it.
- **Save progress as you go.** Commit each deliverable as soon as its own tests pass, in the order above. Don't hold everything for one commit at the end: a job that stops on a usage limit must leave its finished parts committed. Start by checking `git log` and `git status` for work an earlier attempt left, and continue it.
- **Workflow.**
  - Python: `/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/.venv/bin/python`, run with `OPENBLAS_NUM_THREADS=1 PYTHONPATH=$PWD`.
  - Run `ruff format` and `ruff check .`.
  - Run the full `pytest -q`, serially (the machine is shared; a parallel run has been killed for memory), and the app's `bun install --frozen-lockfile`, `bun run test`, `bun run lint` and `bun run build` in `app/`.
- **Commits.** Each message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push, open PRs, upload release assets, or post anything. Do not edit the frozen snapshot data files, the references or the adjudications by hand.
- **Never delete anything you did not create.** Never `rm -rf` a shared directory or a glob.
- **Report.** End with a report listing every file changed, every test pin changed with old → new and where the new value came from, and the final results of pytest and the app checks. Write it to `docs/gpt61sol/report_S3.md` and commit it.
