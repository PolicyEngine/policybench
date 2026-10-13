# Meta Muse Wonder and the third engine upgrade: design

## What the release is

This release does two things on top of release `dashboard-data-20261010` (PR #208):

1. It adds Meta Muse Wonder (display id `muse-wonder`, provider id `openrouter/meta/muse-wonder`, run slug `musewonder`) as the board's 48th model. It is the board's first Meta model.
2. It moves the references from policyengine-us 2.38.6 to 2.41.0, the newest policyengine-us release when the sweep began, a third `engine_upgrade` revision (Max, 2026-09-28: "we should be using the latest pe for this always!"). Release 20261010 left ten outputs excluded for engine defects whose upstream fixes had not shipped. Max's instruction of 2026-10-12 for those: "If any have shipped, regenerate their cells instead of excluding them." Each one the new engine fixes is regenerated and scored again.

It rules no exclusion. Two decisions on reference conventions were open when it was staged: d1252 (VA scenario_039 federal and OH scenario_025 state income tax) and d1263 (the Tax Table against the rate schedule). The spec records both as open, so nothing scored changes on their points.

Meta also released Muse Wonder Full on 2026-10-12. Only Muse Wonder has an API; Muse Wonder Full is limited to Muse Code subscribers. The board runs every model through its provider's API under one protocol, so Muse Wonder Full cannot join it, and the release note says so.

The driver is `scripts/finish_musewonder.py`, adapted from `scripts/finish_haiku55.py`. The freeze is `scripts/freeze_musewonder.py`, adapted from `scripts/freeze_haiku55.py`. Their mechanics are release 20261010's (`docs/haiku55/design.md`) except where this note says otherwise. The inputs are in `docs/musewonder/`:

- `spec.json`: the rulings, no proposals, no adjudications, and the decisions on any outputs the engine upgrade newly excludes (`upgrade_adjudications`, empty unless the build needs one);
- `input_pins.json`: the finished run (written by `--step pin-inputs`);
- `seed_digest.csv`, `seed_recovery.md` and `seed_recovery.json`: the audit seed, rebuilt (below).

The engine upgrade's builder, actions, evidence and narratives are in `reference_audit/2026-10-12-engine-upgrade/`, adapted from `reference_audit/2026-10-09-engine-upgrade/`.

| | Release 20261010 | Before a build is installed | With the 2.41.0 build |
|---|---|---|---|
| Models | 47 | 48 | 48 |
| Requested outputs per model | 1,984 | 1,984 | 1,984 |
| Exclusions | 58: 42 unlisted inputs, 14 engine defects, 2 later-published law | 58, the same records | 48: 42 unlisted inputs, 4 engine defects, 2 later-published law |
| Scored outputs per model | 1,926 | 1,926 | 1,936 |
| Adjudications | 70, of which 58 exclude | 70, the same decisions | 60, of which 48 exclude |

The build removes the ten records it regenerates and drops their decisions, as release 20261010's did; it adds none. Each of the ten regenerated records has exactly one decision in release 20261010's record, which `adjudicate-exclusions` drops; triage may add a decision only on a re-opened case.

## The base

The base is pinned in `scripts/finish_musewonder.py`. Each value is the one git holds at `BASE_COMMIT`.

| Item | Value |
|---|---|
| Base tag, payload sha256 | `dashboard-data-20261010`, `f834478e…a6410` (128,756,688 bytes) |
| Models, outputs, exclusions, scored | 47, 1,984, 58 and 1,926 |
| `reference_outputs.csv` | `fdd17a57…f371` (policyengine-us 2.38.6) |
| `reference_outputs.csv.meta.json` | `d534cfea…c54b` |
| `reference_exclusions.json` | `089e01e1…3626` |
| `scenarios.csv`, its sidecar | `71b16212…858a`, `03a66e90…aebb` |
| `us_case_reference_explanations.csv` | `7ef73f3f…8f5f` |
| `BASE_COMMIT` | `5a8164a0…`, the squash merge of PR #208 on main (2026-10-10) |
| `SEED_RELEASE_COMMIT` | `BASE_COMMIT`: release 20261010's annotations rendered the seed's re-judged prompts |
| Grounding | `b1e4a9bc…b55c`, the main clone's `results/local/unified_audit/grounding.csv` |
| Seed digest | `bc7c057e…b883` (`docs/musewonder/seed_digest.csv`, 677 judged cases) |

The 58 records were decided on three engines: 38 on policyengine-us 1.755.4, 18 on 2.15.17 and 2 on 2.38.6.

## The seed

The seed is release 20261010's judged audit: release 20261006's 674 judged cases with the 232 that release 20261010 re-judged written over them, 677 in all. That release's stage was deleted with its worktree after it shipped, and the repository kept only the hashes of its verdicts and prompts (`docs/haiku55/judge_provenance.json`). `scripts/recover_20261010_audit.py` rebuilt the 232 from each judge's Claude Code session transcript and accepted a transcript only when its prompt and verdict hash to the provenance entry. `docs/musewonder/seed_recovery.md` gives the method and its checks. No verdict text is new.

The seed tree is `results/local/musewonder/seed-20261010/audit`, with a read-only copy in `~/reviews/policybench-muse-wonder/seed-recovery/seed-20261010`.

## Judge template v2

PR #210 made the judge template versioned. `prepare_audit` keeps a verdict on the template version its sidecar records (none means v1) and renders every new or re-opened case on v2. The seed's 677 verdicts are all v1. This release's tree is therefore mixed:

- a kept case's prompt is its v1 render, and its verdict is the seed's, byte for byte;
- a re-opened or new case renders on v2 (`JUDGE_TEMPLATE_VERSION = 2`), and `validate_verdicts` requires its sidecar to record version 2.

`install_references` renders each judged case on the version its sidecar records (`recorded_versions`, `render_audit_with`) to tell an unchanged prompt from a changed one, so a kept v1 case is not re-opened by the template alone.

## The run and onboarding

**Provider.** Meta's own Model API serves the model as `muse-wonder-1.0`, but PolicyBench holds no Meta key. OpenRouter lists `meta/muse-wonder` with a single endpoint, whose provider is Meta, serving `meta/muse-wonder-20261012`. So the board calls Meta's model through OpenRouter, as it calls Kimi, GLM, Qwen, MiniMax and Inkling. The card and the config record the route. The price is OpenRouter's list price, $4 per million input tokens and $20 per million output (cache read $0.20).

**The card (#216, merged).** Access opened once Max confirmed OpenRouter's age attestation for the model (d1445, 2026-10-13). Meta's API accepts `tool_choice` "auto" only: a forced (named-function) or "required" tool choice returns a 400, so the card selects the JSON contract, as Claude Opus 5.5's and Claude Sonnet 5.5's do. A request with no reasoning parameter reasons at the provider default, with or without tools, so the row reasons on the JSON contract and needs no `tool_choice` auto sensitivity run. The gauntlet passed 3/3 and 16/16 on the JSON contract once the card gave the reasoning budget (16,384 tokens shared across up to 16 variables); without it the 3-variable probe stopped at the token limit.

**The board run.** All 100 households and 1,984 answers, every one parsed, from 02:50 to 03:01 UTC on 2026-10-13, for $7.86 at OpenRouter's prices (the frozen `analysis/usage_summary.csv`; the run's files are pinned in `input_pins.json`). OpenRouter reports the resolved model as `meta/muse-wonder`, so `prepare` compares the route's full id (`resolved_model_id`).

**Judging.** The run re-opened 151 cases, all rendered on judge template v2 and judged by Claude Opus 5.5: 113 on Subfleet lane claude-10 (Fleet ops' loan of 2026-10-13: serial calls, five-hour usage read after each, stopped at 85%) and 38 on the pb-judge login (`judge_provenance.json`).

## The engine upgrade

The mechanics are release 20261010's ("The engine upgrade" in `docs/haiku55/design.md`): the builder reads the base's references from git, recomputes every output on the new engine, and must explain every move by a reviewed action. `sweep_timing.py` requires the reference engine to be the newest release when the sweep begins, and re-sweeps any newer release before publication.

**The ten candidates.** Release 20261010 kept ten engine-defect records excluded because their fixes had not shipped. Their audited targets on 2.38.6 are in `reference_audit/2026-10-12-engine-upgrade/evidence/pe2.38.6.json` (engine value, then corrected value):

| Output | Root cause | Fix | 2.38.6 | Target | Target kind |
|---|---|---|---|---|---|
| scenario_007 (ID) state income tax | r07 Idaho health premiums | #10023 | 771.56 | 661.32 | fix_modules |
| scenario_042 (WI) state income tax | r06, r32 | #10026 | 464.18 | 0.00 | record |
| scenario_053 (ID) state income tax | r07 | #10023 | 2,451.06 | 2,186.06 | fix_modules |
| scenario_080 SNAP | r30 heat-and-eat SUA | #10033 | 3,576.00 | 3,240.00 | record |
| scenario_091 (WI) state income tax | r32 | #10026 | 895.81 | 878.52 | record |
| scenario_099 (CA) state income tax | r02, r11, r33 | #10032, #10034, #10052 | 4,588.48 | 4,615.48 | fix_modules |
| scenario_100 federal refundable credits | r08 EITC deferrals | #10030 | 2,878.10 | 822.29 | record |
| scenario_100 state refundable credits | r08 | #10030 | 473.18 | 164.46 | record |
| scenario_119 federal refundable credits | r08 | #10030 | 2,854.01 | 3,366.07 | record |
| scenario_119 state income tax | r08 | #10030 | 1,859.09 | 1,756.68 | record |

A `record` target is the exclusion record's alternative value. A `fix_modules` target is what the audited fix modules give on 2.38.6, where the defect is still present, because something else in the engine moved the output since the record was decided.

**This audit's own fix module.** CA scenario_099's record names two root causes, r02 and r11. Release 20261010's recheck on 2.38.6 found a third difference: California does not conform to the federal educator-expense deduction, so it adds the deduction back (`r33_ca_educator_expense_addback.py` in `reference_audit/2026-10-12-engine-upgrade/fixes/`, mirroring PolicyEngine/policyengine-us#10052's `ca_educator_expense_addition`). Earlier upgrades read every module from `reference_audit/2026-09-22/fixes` at `BASE_COMMIT`. This one may also pin a module from its own `fixes/`, read at HEAD (`fix_location` in the builder, `fix_module_blob` in the driver), and the pin then carries its `path`. A name found under both folders resolves to the 2026-09-22 module, so a local module cannot shadow an audited one. `freeze_snapshot.verify_regeneration_target_pins` requires each pinned path to be a `reference_audit/<audit>/fixes/<module>` file at its committed bytes.

**The build.** policyengine-us 2.41.0 was published at 01:44:55 UTC on 2026-10-13 and was the newest release when the sweep began (`reference_audit/2026-10-12-engine-upgrade/verification/sweep_timing.json`: installed 01:49:51, first output 01:51:12). It is the first release carrying all seven fixes: 2.40.1 lacks #10052. Its 1,984 computed outputs are identical to a first pass on its release commit `de3815f4cc`. The reviewed actions (`final_actions.json`) regenerate the ten candidates, each on its target, and recheck eleven excluded outputs that move and stay excluded. No scored reference changes by any amount, and nothing is newly excluded. The build is `results/local/musewonder/engine/final` (copy in `~/reviews/policybench-muse-wonder/engine-2.41.0`), and `driver.load_build` accepts it (`test_a_real_builders_build_passes_the_drivers_gates`).

**Rechecks of scenario_005 and scenario_120.** The action drafter first called these two federal income tax outputs "not fixed": it compared them with their records' 1.755.4-era alternative values. Release 20261010's recheck had found both on the corrected value its 2.38.6 evidence gave, and kept them excluded for a second, unlisted-input reason (r25, the net investment income tax). 2.41.0 gives the same values, so the drafter now keeps that finding.

**Narratives.** The writer (claude-haiku-4-5) misstated the change behind six of the ten narratives; four said 401(k) deferrals count as earned income for the EITC, the reverse of #10030. All ten are hand-corrected against the build's trace (`hand_corrected_narratives.json`, with each basis in the `.md`).

**DecisionWave.** Release 20261010's driver dated every triage decision by its ruled 2026-10-06 wave. This release rules nothing, so a triage decision (a developer affirming a reference the upgrade changed, which a re-judged verdict flagged) is dated by the engine upgrade's revision day. The upgrade's day is named as a wave in the date conventions whenever the upgrade decides anything, a new exclusion or a triage affirmation (`decision_wave`, `release_date_conventions`), with the day its decisions were written (`upgrade_adjudications_written_on`). With no decision, the conventions stay release 20261010's.

**scenario_080 (SNAP).** Its 2026-09-22 record noted that the heat-and-eat allowance would stand ($3,576) were the household's disabled head a member 7 U.S.C. 2012(j) counts as disabled, and excluded the output on either reading. The prompt states none of the routes 2012(j) lists and tells the reader to treat unlisted statuses as false and not to infer benefit receipt, and 2.41.0 places the head's Medicaid in the adult group. So the reference takes the non-disabled path, as the card's disability convention has every disabled person's references do, and the output is scored at the record's corrected value, $3,240. The upgrade audit's README, the card and the paper say so.

**The publication check.** At 09:39 UTC on 2026-10-13 PyPI's newest release was 2.41.1; `sweep_timing.py check` re-swept every output on it (`verification/publication_check_2_41_1.csv`), and all 1,984 equal 2.41.0's. policyengine-us main at `2f3053c845` (pyproject 2.41.2, with the AMT child exemption and Vermont renter credit fixes queued to publish) also gives 2.41.0's value for every output (`~/reviews/policybench-muse-wonder/engine-check`). If a newer release publishes before the merge, run the check again and re-render.

**Two October moves in the paper.** The paper's engine-upgrade accessors describe the last upgrade. `PaperResults.upgrade_view("2.38.6")` gives the same accessors for the 2026-10-10 move, so the paper keeps a paragraph and a discrepancy-table row for each move (`october_upgrade_row`). The restored-fix phrase now names a cause a fix-modules target's modules correct beyond the record's (scenario_099's educator expense addback), and joins two outputs whose causes nest under the same pull requests (the two Wisconsin outputs of #10026); release 20261010's phrase is unchanged. With no exclusion resting on a defect 2.41.0 still has, the abstract, the September audit paragraph and the limitations say so instead of printing a zero (`abstract_exclusion_sentence`, `engine_defect_unfixed_sentence`, `engine_defect_limitation_lead`).

**Builder notes.** A sidecar keeps every upgrade's revision. `scripts/freeze_snapshot.py` accepts both later builders' notes (`UPGRADE_BUILDERS`): the 2026-10-10 upgrade's and this one's. Both pin the same inherited setup (the 2026-09-29 conventions, composer and adapter, `latest_final.py` and the sales-tax table).

## Open decisions checked before the freeze

| Decision | State when staged | Effect here |
|---|---|---|
| d1252 (keep scoring VA scenario_039 federal and OH scenario_025 state income tax) | open | none: both stay scored as in release 20261010 |
| d1263 (rate schedule against the Tax Table) | open | none: federal references keep the section 1 rate schedule |
| d1441 (add Muse Spark 1.3 in this release) | open | not added without Max's yes |

Checked again on 2026-10-13 at 10:10 UTC, before the final freeze: all three still open, so nothing changes.
