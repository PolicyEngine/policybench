# Stage 3b brief: fix the review findings for release dashboard-data-20260929

Work in `/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2` (branch `adds-0928-stage2`, in place). Stage 3 (commits after 464649b6) wrote the release's prose, notes, paper and pins. Two adversarial reviews requested changes, and the lead has consolidated them below.

Keep following `docs/adds0928/brief_S3_prose_and_pins.md`, including its Voice and Rules sections, and Max's voice guide `~/.claude/projects/-Users-maxghenis/memory/voice_max.md`. Use the worktree `.venv` with `OPENBLAS_NUM_THREADS=1 PYTHONPATH=$PWD`, and run the heavy steps serially.

## Decisions already made (apply them; do not reopen)

1. **Engine wording.** Keep policyengine-us 2.15.17 as the recorded engine. State it as a dated fact: "policyengine-us 2.15.17, the newest release when PolicyBench began sweeping the references on 2026-09-29 (uploaded 00:23 UTC)". Add the verification: policyengine-us 2.17.0, the newest release at publication (uploaded 2026-09-29 12:21 UTC), gives the same value for all 1,984 outputs under the same conventions and adapter.
   - Evidence: `/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/sweep/out/latest_final_2170.csv` and `.log`, from `sweep_latest.py --fix fixes/latest_final.py` run in a policyengine 6.1.2 + policyengine-us 2.17.0 venv.
   - Copy both files into `reference_audit/2026-09-28/verification/`, add a README line, and add a test that the CSV's `recomputed` column equals the committed reference for every scored output.
   - Remove every unanchored "newest", in the card, paper, release note, README and app copy.
2. **Upgrade date.** Use 2026-09-29 for the upgrade everywhere. The references were rebuilt at 2026-09-29 11:57 UTC and the release is 20260929. Call the three models "the September 29 additions" (release 20260929) consistently, in place of "September 28 additions".
3. **What 2.15.17 computes.** It computes each *scored* reference. Everywhere the copy says 2.15.17 computes every reference or every household-variable pair, say "each scored reference". Add one sentence in the card, the paper and the app Methodology copy: the 55 excluded outputs keep the values they were decided on (52 computed with policyengine-us 1.755.4, 3 with 2.15.17), and the 19 of them that move on 2.15.17 were re-reviewed and stay excluded. Apply the same to `app/src/data.versions.json`'s description.

## Findings to fix

**Release note (`app/src/notes/2026-09-29-...json`):**
- Paragraph 7 calls the Arizona household "a fifth household to do so". That is wrong: other scored households also qualify only through BBCE. Arizona is the fifth household *held back by income* in the BBCE note's sense, where the other four are CT 027, TX 030, MI 073 and WI 108. Rewrite it as the reviewer suggested, and fix "the other four".
- The DeepSeek V4.1 Flash cost is priced at the provider's standard (peak) list rate, per `policybench/config.py`. Say so ("at DeepSeek's standard list price"). Make no claim about off-peak billing unless you verify DeepSeek's current off-peak policy and the run's timestamps from a primary source this session.
- Tie the remaining prose facts to data in the tests: the title's ordinal equals the ordinal of `facts['sonnetRank']`, and the engine version equals the sidecar's.

**Drift claims.** The note's drift range, its three neighbor swaps, "GPT-6 Sol still leads" and "every one of the 42 earlier models" need a real check.
- Commit a small fixture holding the 42 no_tools exact scores of release `dashboard-data-20260922c`, taken from the live 22c payload. Its sha256 is `01e7e72b3a6bdd2d3178ba32625ff769d5b81dc07541af6ea8da2c852774ddcc`, and it is available as the stage base or in git at 3220a7a: `paper/snapshot/.../data.json.gz` wraps the country payload.
- Record the source sha in a meta file.
- Test the note's drift facts against that fixture and the frozen payload with no git access. Replace the vacuous assertion.

**Paper (`paper/index.qmd`, `docs/paper.md`):**
- Drop the unnamed "five audit waves" count ("Across development and each later audit ...").
- "the reviewers excluded" becomes "the investigation found, and PolicyBench excluded, ...".
- `docs/paper.md`: the manifest's `reference_output_refresh` block records the reference runtime's default dataset (build populace-us-2024-spm-20260915, from the policyengine.py 6.1.2 bundle), which reference computation does not read. The households' source build is populace-us-2024-5da5a95-20260611 (`scenarios.csv.meta.json`). Say that accurately.
- Fix the pre-existing render bug: the cost-and-latency sentence renders a literal `\\$0.002` and the cost table renders `\$0.034`, in both HTML and PDF. Find the escaping in `paper/index.qmd` or `policybench/paper_results.py`, fix it, and add a test on the rendered HTML.

**Manifest reproducibility note (`scripts/freeze_snapshot.py`, the `build_manifest` template).**
- It says the references "were generated with policyengine.py X and policyengine-us Y against the certified PolicyEngine US populace dataset (build ...)". That is a mechanism error. PolicyBench computes each reference with `policyengine_us.Simulation` from the household's own listed inputs, and records policyengine.py only for provenance.
- Rewrite the template sentence accurately: name policyengine-us Y and policyengine.py X (provenance), and say the households were drawn from the populace build in `scenarios.csv.meta.json`. Read that build from the scenarios meta, not the runtime bundle.
- Keep the manifest's existing keys. If you add a field for the households' build, test it.
- Regenerate the manifest through the documented freeze (the next section), not by hand.

**App copy.**
- `Methodology.tsx`: compute the chunked-row count from `model-serving-config.json` (rows whose request shape is not "whole scenario") and the model total from the payload's modelStats.
- `ModelLeaderboard.tsx`: build the list of Claude rows that reject forced tool calls (JSON contract) from the serving config.
- Update `app/tests` to compare against the config and payload, not hand-typed numbers.

**Paper-results invariants (`policybench/paper_results.py`, the engine_upgrade_* properties).**
- Assert that scored changes + within-tolerance + new exclusions == `len(engine_upgrade_revision['changed'])`.
- Add a Hypothesis property test over synthetic revisions and exclusion sets checking that the partition is exact and disjoint. hypothesis is a dev dependency.

**Adjudication `judge_previous` dates (data fix).**
- The upgrade's refresh wrote each replaced judge class under `judge_previous` with a `judged_on` equal to the entry's `adjudicated_on`. For some entries that pairs claude-opus-5-5 with a date before Opus 5.5 judged anything, which is impossible.
- Fix it. Take each previous verdict's actual `judged_at_utc` from `/Users/maxghenis/PolicyEngine/policybench/results/local/unified_audit/audit/cases/<case>/verdict.meta.json` when that verdict's classes match the recorded previous classes. Otherwise rename the field to `adjudicated_on`, which is what it holds.
- Add a test: every `judge_previous` date is on or after its judge model's release date (`MODEL_RELEASE_DATES` or the equivalent registry), and every current judge date is on or after the previous one.
- Also comment the judge-provenance test (older judges' counts fall because Opus 5.5 re-judged their cases after the reference revisions).
- Edit the staged record `results/local/adds0928-v3/publish/us_full_run_20260612_policyengine_4_16_1_populace/annotations/us_adjudications.json`. The committed `annotations/.../us_adjudications.json` is produced by the freeze.

## Regenerating after data-adjacent fixes

The adjudication fix and the manifest template fix change frozen artifacts, so rerun the documented chain after them, in this order:

```bash
V=$PWD/results/local/adds0928-v3
.venv/bin/python scripts/finish_adds0928.py --stage-dir $V --step triage
.venv/bin/python scripts/finish_adds0928.py --stage-dir $V --step export      # keeps the 22c replay gate
.venv/bin/python scripts/freeze_adds0928.py --stage-dir $V --dry-run
.venv/bin/python scripts/freeze_adds0928.py --stage-dir $V
.venv/bin/python paper/render_paper.py && .venv/bin/python scripts/freeze_snapshot.py --rendered-only
```

If the payload hash changes (annotations feed the payload), report the new sha256. `app/src/data.artifact.json` must then match it, and the freeze updates it.

## Done means

- Every finding above is fixed, or explicitly answered in your report with evidence.
- `pytest -q` passes, the app checks pass (`bun run test`, `lint`, `build`), `ruff check .` and `ruff format --check .` pass, and the paper renders.
- Coherent commits, each ending with the `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` line. No push.
- Return, as your final answer: every change with file and finding, every pin moved (old → new → source), the final payload sha256, and the test and app results.
