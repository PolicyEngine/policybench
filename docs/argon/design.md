# Gemini 4 Argon and Muse Spark 1.3: design

## What the release is

This release adds two models to release `dashboard-data-20261013b` (PR #218), taking the board from 48 models to 50:

1. Google's Gemini 4 Argon (display id `gemini-4-argon`, provider id `gemini/gemini-4-argon`, run slug `argon`). Google announced it on 2026-09-30 for Fairwind Program cyber partners only and opened it to the public on 2026-10-13.
2. Meta's Muse Spark 1.3 (display id `muse-spark-1.3`, provider id `openrouter/meta/muse-spark-1.3`, run slug `musespark`), released 2026-09-02. Max added it to this release on 2026-10-13 (decision d1441).

It moves no reference and rules no exclusion; its only decisions are two developer triage decisions on cases the new models re-opened, both keeping the output scored (below). The references stay release 20261013b's, computed on policyengine-us 2.41.0: the newest policyengine-us release when this release was staged, 2.41.3, and when it was frozen, 2.42.4, give the same value for all 1,984 outputs (below). Max ruled on two reference conventions on 2026-10-13, both to keep: d1252 keeps VA scenario_039's federal and OH scenario_025's state income tax scored (the held-reference records now say so), and d1263 keeps the section 1 rate schedule for federal income tax, which the benchmark card and the paper now state. Neither changes a score.

The driver is `scripts/finish_argon.py`, adapted from `scripts/finish_musewonder.py`. The freeze is `scripts/freeze_argon.py`, adapted from `scripts/freeze_musewonder.py`. Their mechanics are release 20261013's (`docs/musewonder/design.md`) except where this note says otherwise. The inputs are in `docs/argon/`:

- `spec.json`: the rulings and the two triage decisions (`triage_adjudications`), with no proposals and no ruled adjudications;
- `input_pins.json`: the two finished runs (written by `--step pin-inputs`);
- `seed_digest.csv`: the audit seed (below).

| | Release 20261013b | This release |
|---|---|---|
| Models | 48 | 50 |
| Requested outputs per model | 1,984 | 1,984 |
| Exclusions | 49: 42 unlisted inputs, 5 engine defects, 2 later-published law | 49, the same records |
| Scored outputs per model | 1,935 | 1,935 |
| Adjudications | 61, of which 49 exclude | 63: the same 61 and two triage decisions, neither excluding |

## The base

The base is release `dashboard-data-20261013b`: release 20261013 with five carried-over audit verdicts re-judged on judge template v2 (PR #218, the judge-isolation follow-up). Its references, exclusions, adjudications, predictions and serving configuration are release 20261013's byte for byte; its annotations change in those five cases only.

| Item | Value |
|---|---|
| Base tag, payload sha256 | `dashboard-data-20261013b`, `0a4b754a…b507` (130,982,477 bytes) |
| Models, outputs, exclusions, scored | 48, 1,984, 49 and 1,935 |
| `reference_outputs.csv` | `2d00cf59…3a0c` (policyengine-us 2.41.0) |
| `reference_outputs.csv.meta.json` | `0dc1ba15…0915` |
| `reference_exclusions.json` | `a2ddf916…3f39` |
| `scenarios.csv`, its sidecar | `71b16212…858a`, `03a66e90…aebb` |
| `BASE_COMMIT` | the commit whose tree holds release 20261013b (PR #218's merge on main) |
| `SEED_RELEASE_COMMIT` | `BASE_COMMIT` |
| Grounding | `b1e4a9bc…b55c`, the main clone's `results/local/unified_audit/grounding.csv` |
| Seed digest | `0f599257…f911d` (`docs/argon/seed_digest.csv`, a copy of `docs/release_20261013b/seed_digest.csv`; 677 judged cases) |

## The seed

The seed is release 20261013b's judged audit (`~/reviews/policybench-judge-isolation/stage-audit-20261013b`): release 20261013's 677 judged cases with the five that release 20261013b re-judged written over them. 423 of its verdicts record no template version (so v1), 98 record v1 and 156 record v2. `prepare_audit` keeps each seed verdict on the version its sidecar records and renders every new or re-opened case on v2 (`JUDGE_TEMPLATE_VERSION = 2`).

## No engine upgrade

Release 20261013 moved the references to policyengine-us 2.41.0. Before staging this release PolicyBench re-ran the publication check (`reference_audit/2026-10-12-engine-upgrade/scripts/sweep_timing.py check`): at 17:22 UTC on 2026-10-13 PyPI's newest release was 2.41.3, and a sweep of every output on it gives 2.41.0's value for all 1,984 (`verification/publication_check_2_41_3.csv`). After the freeze the check ran again: at 04:03 UTC on 2026-10-14 the newest release was 2.42.4 (2.42.0 to 2.42.3 never reached PyPI), and it too gives 2.41.0's value for all 1,984 (`verification/publication_check_2_42_4.csv`). No reference moves and no excluded output's defect is fixed, so this release installs no engine upgrade.

The driver therefore has no `--step install-references`. Every helper that took an installed upgrade keeps its parameter and is called with none, so the code stays comparable line for line with `finish_musewonder.py`, and `stage_upgrade` refuses a stage whose `stage.json` records an installed build. If a newer policyengine-us release moves a scored output before publication, the check exits non-zero and the release stops: moving the references then needs an engine-upgrade audit and a driver that installs its build.

## The runs and onboarding

**Gemini 4 Argon (#219).** It runs on the first-party Gemini API, like every Gemini row. The Gemini API accepts a forced function call on this model, and the onboarding gauntlet, run before the card existed, passed on the tool contract (3/3 and 16/16), so the row takes the board's forced answer tool, as Gemini 3.6, 3.7 and 3.8 Flash do. It is priced at $2/$10 per 1M input/output tokens and $0.10 cached input, the rate Google lists through 2026-11-30 (it doubles on 2026-12-01).

The model reasons at Google's default (`thinking_level` medium) and decides call by call whether to think. The question for this card was whether a forced tool suppresses that reasoning, as it does Claude Opus 5's. A rule was fixed before the evidence was complete (`~/reviews/policybench-gemini-4-argon/probes/DECISION-RULE.md`): publish a `tool_choice` auto sensitivity run only if forcing lowers the share of households with reasoning tokens at Fisher exact p < 0.05. Over the 100 board households a forced-tool run returned reasoning tokens on 80 and an auto run on 82 (p = 0.86), so there is no sensitivity run. The board row's own run, the second forced run below, returned reasoning tokens on 85 (`board-run/reasoning-comparison-run2.json` in the onboarding record; against the auto run, p = 0.70).

The card caps escalation at 32,768 completion tokens, the most one non-streaming `generateContent` request returns (Google's Gemini 4 Argon guide). A first board run recorded the model page's 65,536 instead, and the freeze checks a run's recorded treatment against the registry, so the board row is a second run on the corrected card: all 100 households in one request each, 1,984/1,984 answers parsed, no budget escalation, $2.79 (2026-10-13, 18:28 to 18:38 UTC). The first run and the auto run stay in the onboarding record as evidence.

**Muse Spark 1.3 (#220).** It runs through OpenRouter, whose one endpoint for the id is Meta's own, as Muse Wonder does, at Meta's standard-mode rate ($1.25/$4.25 per 1M, $0.15 cached input). Meta's API rejects a forced tool choice, so the row answers as a JSON object whole-scenario and reasons at Meta's default. The board run answered all 100 households in one request each, 1,984/1,984 parsed, no budget escalation (2026-10-13, 17:58 to 18:26 UTC). An app restart interrupted it at 95 of 100 households; the supervisor resumed it on the same treatment. Its four smoke households replay the smoke's responses from the harness's disk cache (identical requests), as the two smoke households of the Muse Wonder, Claude Haiku 5.5 and Claude Opus 5.5 rows do.

Both runs' files are pinned in `input_pins.json`.

## Judging

Preparing the stage on the seed kept 482 judged prompts unchanged and re-opened 196 cases (195 whose wrong models changed and one new), none of them the five release 20261013b re-judged. All 196 are rendered on judge template v2 and judged by Claude Opus 5.5 through `scripts/run_audit_claude.sh` on the pb-judge setup-token login (`judge_provenance.json`).

## Triage decisions

Triage stopped on two re-opened cases, and the release records a developer decision on each, dated by its own wave, 2026-10-14 (`triage_decided_on`). Each keeps the output scored with the judge's own case class, as the 2026-09-22 and 2026-09-29 waves decided the same patterns:

| Case | What triage stopped on | Decision |
|---|---|---|
| scenario_009 federal income tax | The verdict flags nothing but labels eight models' rows `reference_later_law`, a developer-only class, because they applied the pre-TCJA rules scheduled to return in 2026. | `llm_error` with no reference verdict: the reference applies P.L. 119-21 (enacted 2025-07-04), law published before the 2026-07-03 reference freeze. The 2026-09-29 wave decided scenario_007's federal income tax the same way. |
| scenario_064 Wisconsin income tax | The verdict flags the reference, on the hypothesis that Wisconsin limits a net capital loss deduction to $500, and labels claude-opus-5.5's row `reference_model_issue_fixed`. | `llm_error`, reference affirmed: the $500 limit is Wis. Stat. 71.05(10)(c)1., for taxable years beginning before 2023; subd. 2. allows $3,000 ($1,500 married filing separately) after 2022, as line 28 of the 2025 Schedule WD does and as policyengine-us applies. The seed's verdict on the case, judged on 2026-10-13, called the $500 add-back a model error. |

`finish_musewonder.py` read triage decisions only with an engine upgrade installed, dated by the upgrade's revision. Without one, this driver reads them from the spec, dated by `triage_decided_on`, and writes the wave into the record's date conventions with the day the spec says they were written (`triage_adjudications_written_on`). A decision may affirm a reference only where the case's verdict flags it, and may go without a reference verdict only where the verdict flags nothing and a class outside the final set remains. It never excludes an output. The freeze holds the record to exactly these entries, and `scripts/date_argon_judge_verdicts.py` adds the wave to the judge-verdict evidence uncommitted, as release 20261010 added its waves.

Three restated decisions gained a reference flag on re-judging: scenario_056 SNAP, scenario_067 dependent 1 Medicaid and scenario_114 federal income tax. Each is an unlisted-input exclusion whose recorded basis already names the input the new hypothesis turns on, so all three stay excluded unchanged.

## Open decisions checked before the freeze

| Decision | State when staged | Effect here |
|---|---|---|
| d1252 (keep scoring VA scenario_039 federal and OH scenario_025 state income tax) | ruled 2026-10-13: keep both scored; fix the labels in the v2 prompt (#165) | none: both stay scored as in release 20261013b; `reference_audit/held_references.json` records the ruling |
| d1263 (rate schedule against the Tax Table) | ruled 2026-10-13: keep the schedule and state the convention | none: federal references keep the section 1 rate schedule; the benchmark card and the paper state it (the v2 prompt line is #165) |
| d1441 (add Muse Spark 1.3) | yes (2026-10-13) | added in this release |
