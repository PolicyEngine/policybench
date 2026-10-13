# Meta Muse Wonder and the third engine upgrade: design

## What the release is

This release does two things on top of release `dashboard-data-20261010` (PR #208):

1. It adds Meta Muse Wonder (display id `muse-wonder`, provider id `openrouter/meta/muse-wonder`, run slug `musewonder`) as the board's 48th model. It is the board's first Meta model.
2. It moves the references from policyengine-us 2.38.6 to the newest policyengine-us release, a third `engine_upgrade` revision (Max, 2026-09-28: "we should be using the latest pe for this always!"). Release 20261010 left ten outputs excluded for engine defects whose upstream fixes had not shipped. Max's instruction of 2026-10-12 for those: "If any have shipped, regenerate their cells instead of excluding them." Each one the new engine fixes is regenerated and scored again.

It rules no exclusion. Two decisions on reference conventions were open when it was staged: d1252 (VA scenario_039 federal and OH scenario_025 state income tax) and d1263 (the Tax Table against the rate schedule). The spec records both as open, so nothing scored changes on their points.

Meta also released Muse Wonder Full on 2026-10-12. Only Muse Wonder has an API; Muse Wonder Full is limited to Muse Code subscribers. The board runs every model through its provider's API under one protocol, so Muse Wonder Full cannot join it, and the release note says so.

The driver is `scripts/finish_musewonder.py`, adapted from `scripts/finish_haiku55.py`. The freeze is `scripts/freeze_musewonder.py`, adapted from `scripts/freeze_haiku55.py`. Their mechanics are release 20261010's (`docs/haiku55/design.md`) except where this note says otherwise. The inputs are in `docs/musewonder/`:

- `spec.json`: the rulings, no proposals, no adjudications, and the decisions on any outputs the engine upgrade newly excludes (`upgrade_adjudications`, empty unless the build needs one);
- `input_pins.json`: the finished run (written by `--step pin-inputs`);
- `seed_digest.csv`, `seed_recovery.md` and `seed_recovery.json`: the audit seed, rebuilt (below).

The engine upgrade's builder, actions, evidence and narratives are in `reference_audit/2026-10-12-engine-upgrade/`, adapted from `reference_audit/2026-10-09-engine-upgrade/`.

| | Release 20261010 | This release before a build is installed |
|---|---|---|
| Models | 47 | 48 |
| Requested outputs per model | 1,984 | 1,984 |
| Exclusions | 58: 42 unlisted inputs, 14 engine defects, 2 later-published law | 58, the same records |
| Scored outputs per model | 1,926 | 1,926 |
| Adjudications | 70, of which 58 exclude | 70, the same decisions |

An installed build changes these counts as in release 20261010: it removes the records it regenerates and drops their decisions, and adds any records it newly excludes.

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

**Pending.** The card PR (#216) waits on access: every OpenRouter call to `meta/muse-wonder` returns HTTP 403 until the account confirms the age attestation OpenRouter requires for this model (d1445). Then, in order:

1. the reasoning probes (plain, forced tool, `tool_choice` auto, required), as `sensitivity/claude-thinking-2026-08.md` did for Claude, recorded on the card;
2. the card's `answer_contract`: a forced answer tool unless the provider rejects it;
3. the onboarding gauntlet and the board run on the frozen 100-household manifest with a budget cap set from the probes' token counts;
4. the `tool_choice` auto sensitivity run, if forcing the tool suppresses reasoning.

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

**First pass on a pre-release.** On policyengine-us 2.41.0 built from git (`de3815f4cc`, before its PyPI publish), 23 outputs differ from 2.38.6, all of them excluded. All ten candidates land on their targets, and no scored output moves. The release build waits on the published wheel, which `sweep_timing.py` requires.

**DecisionWave.** Release 20261010's driver dated every triage decision by its ruled 2026-10-06 wave. This release rules nothing, so a triage decision (a developer affirming a reference the upgrade changed, which a re-judged verdict flagged) is dated by the engine upgrade's revision day. The upgrade's day is named as a wave in the date conventions whenever the upgrade decides anything, a new exclusion or a triage affirmation (`decision_wave`, `release_date_conventions`), with the day its decisions were written (`upgrade_adjudications_written_on`). With no decision, the conventions stay release 20261010's.

**Builder notes.** A sidecar keeps every upgrade's revision. `scripts/freeze_snapshot.py` accepts both later builders' notes (`UPGRADE_BUILDERS`): the 2026-10-10 upgrade's and this one's. Both pin the same inherited setup (the 2026-09-29 conventions, composer and adapter, `latest_final.py` and the sales-tax table).

## Open decisions checked before the freeze

| Decision | State when staged | Effect here |
|---|---|---|
| d1252 (keep scoring VA scenario_039 federal and OH scenario_025 state income tax) | open | none: both stay scored as in release 20261010 |
| d1263 (rate schedule against the Tax Table) | open | none: federal references keep the section 1 rate schedule |
| d1441 (add Muse Spark 1.3 in this release) | open | not added without Max's yes |

Check `cos decisions --all` again before freezing and apply any ruling.
