# GPT-6.1 Terra release mechanics

The release driver is `scripts/finish_terra.py`; `scripts/freeze_terra.py` freezes its bound stage. The release adds the `terra/run` supervised run as display and provider id `gpt-6.1-terra` to release `dashboard-data-20261014`, and installs the committed `reference_audit/2026-10-22-engine-upgrade/reference-build/`. The board has 51 models, 1,984 requested outputs, 49 exclusions and 1,935 scored outputs per model. This document describes the release machinery. The lead writes every statement about the resulting scores, judgments and checks.

## Base and inputs

`BASE_COMMIT` is `bf845cbe4e92de495150c8660c35ea357d996a8c`, PR #221's squash merge. The run directory, annotations and `reference_audit/held_references.json` at main's `e0217ede` equal that commit's bytes. The payload pin is the published wrapper containing `countries.us`; the compact snapshot stores that country payload inside `data.json.gz`.

| Input | SHA256 |
| --- | --- |
| Published base payload, 135,840,397 bytes | `22db9a9c052545371687f6afa3551896336abbd15c76f767ebb777a77f6d2268` |
| Base `reference_outputs.csv` | `2d00cf595adf183fcfa3d069756723b5ce09bd4123fbf3e673635474346b3a0c` |
| Base reference sidecar | `0dc1ba15a11a20d9a3915a4537a33127e5406b5fde4797586d39ce5dbf170915` |
| Base exclusion record | `a2ddf91634ed66124d13105a09badea39ec6b5f11863011fa51f9ca17f8f3939` |
| `scenarios.csv` | `71b16212f0c0b3e5d13d8694ce57e362c23248665806c4d6dea7b23ef472858a` |
| Scenario sidecar | `03a66e90b86e9bd0cc77f27520784bd581777762f749675dc716e24c1b8eaebb` |
| Base adjudications, 63 entries | `df4cc1eb27bce6514185d294c4da3c7e76d94b9ead2b8fe921a8fd306090049e` |
| Grounding | `b1e4a9bc74d762f410524a147efcda7d705c3afcfa3dc27f720fa60c54a7b55c` |
| `docs/terra/seed_digest.csv`, 678 cases | `e80285307cb1030ab656fd18eac50437b6f42912a1655a55a9f2f1dad7dd07ed` |

The seed is `/Users/maxghenis/reviews/policybench-gemini-4-argon/worktree-results/stage2/audit`, whose parent `README.md` identifies it as release 20261014's judged audit. `seed_digest.csv` hashes each case's prompt and verdict. The driver binds that digest and refuses another seed or grounding. The run remains read-only at `/Users/maxghenis/PolicyEngine/policybench/results/local/terra-runs/terra/run`; `pin-inputs` writes its predictions and run-state hashes to `docs/terra/input_pins.json`, which must be committed before export and freeze.

## Changes from the earlier drivers

Argon's driver supplies the folding, seed binding, adjudication record gates, `judge_ever_flagged` handling, judge transcript and provenance validation, and template v2 for every new or re-opened case. Carried verdicts keep the template version recorded in their sidecars and their exact seed bytes. `MODELS` contains only `{"terra": "gpt-6.1-terra"}`. `RELEASE_TAG` has one definition in the driver; the spec must agree with it. The lead may change that constant and the matching spec field at freeze time.

Two judge gates are stricter than Argon's. Every verdict that is not carried over from the seed must record `claude-opus-5-5` as the judge requested and the only one reported, `scripts/run_audit_claude.sh` as its runner (the runner the judge step runs) and an ISO 8601 `judged_at_utc` in UTC, whichever models its case lists: a case the installed build re-opened can list incumbents alone. The judge provenance record's note is generated from its entries (`provenance_note`). It tallies the judge model each sidecar reports, the effort and judge template each records and whether each judge ran isolated, and it states no login, schedule or retry history beyond what the entries and their group counts record. Export and the freeze refuse a record whose note differs from the generated one.

Muse Wonder's driver supplies the installed-build gates and copying, with the build read from its committed audit directory. The directory and pins share one driver table, so repointing a later audit is reviewable. The driver's install step accepts exactly that build. It checks the sidecar against the base plus one engine-upgrade revision, the reviewed actions against their own provenance hash, the builder and inherited module pins, every changed reference, every retained exclusion and the reference narratives. The audit's UTC revision day is 2026-10-23; its directory name records when the audit began.

| Installed input | SHA256 |
| --- | --- |
| `reference_outputs.csv` | `eab09a0c184c14b0c33679d9ac132d6f1de720c439ac30685a67ca38655184cb` |
| `reference_outputs.csv.meta.json` | `55c17fe298f9ac09ff56b2187d1d314ede7d239e94924da6abb6e0ad2542260c` |
| `reference_exclusions.json` | `91408c0f3d49e1984b436164a047f8cedc3e501feb2099ba0e7d2782ee8ac73d` |
| Builder | `d4b00204390c6ada97bdf91358dc3d60ae3307d101062b8982fa62923cc9c645` |
| `final_actions.json` | `93fc088f0d2617e9e6d5bf5f0b65e4e8709d46bdd64da12e5cb9d92c06c8fd21` |
| Rebuilt reference narratives | `47c33db094072c97ca18bb763526767c9fc23ecc50d153951be54b43182bc5e4` |

The install rebuilds the four changed narratives through the audit's `scripts/narratives_upgrade.py` and `hand_corrected_narratives.json`. It calls that pinned script's pure `rewrite_explanations` function, validates each supplied amount and derives trace-line counts from the committed traces. This avoids importing the narrative writer SDK and its import-time pricing fetch. Every other explanation row keeps its bytes. The three reference files are copied into the scoring source and staged run, and the new explanations into the staged annotations. A fresh stage can cache the reviewed build before preparation; preparation installs it into the full bundle and renders the audit with its references. A prepared stage can install the same build through the same gates. Later steps refuse a missing, changed or different installed build.

Four scored references move: scenario_031 SNAP and scenario_028, scenario_117 and scenario_123 `free_school_meals_eligible`. A judge prompt includes both a reference value and its explanation, so these cases are rendered again and their old verdicts set aside even when every incumbent answer stays the same. The approved moves alone may change incumbent scores. Export first puts the base references and exclusion record back in a scratch copy and requires every incumbent's serialized `modelStats` to equal the base byte for byte (`export_on_base_references`, from release 20261010). It also confines the installed CSV's changes to the four approved moves; any remaining incumbent drift stops the release.

The 49 exclusion records keep their decided values. Sixteen are rechecked, none is regenerated, and no adjudication is dropped for regeneration. PR #242's four r24 cells remain excluded at their decided $0 values, pending Max's d1878. The reference engine's employer-paid coverage default does not decide the prompt's unstated coverage payer. This release adds no ruling on that question.

Argon's open `triage_adjudications` mechanism remains available with the build installed. The initial spec has no proposals, ruled adjudications or triage decisions. If triage needs a developer decision, the lead adds the exact allowed entry and its `triage_decided_on` and `triage_adjudications_written_on` dates to the spec, installs the same reviewed build again to bind the updated spec, then runs `adjudicate-exclusions` and triage again. An entry may affirm a flagged reference with its basis or settle a developer-only row class on an unflagged case, and keeps the output scored. The record gates continue to require the judge's class and bound verdict. Wording corrections go through the stage's `wording-amendments.json`.

Main's later disclosure changes also apply. PR #231's `live_calls`, `cache_hit_calls` and `live_elapsed_seconds` columns must survive the Terra fold and pass the driver's provenance checks. Counts repeat over rows from a shared request group; live time is apportioned like `elapsed_seconds`, and replayed responses contribute zero live time. Incumbent rows written before these columns existed retain their unknown values. Pandas concatenation promotes Terra's integer call counts to floats alongside those empty incumbent cells, so preparation restores every Terra cell from its immutable source CSV after folding and validates all columns as exact text. PR #228's latency convention continues to use each household's summed recorded elapsed time, including cache lookup time, and records only the successful retry attempt. The paper's latency disclosures must explain replayed households. PR #230 prices an uncosted row only when that row recorded both prompt and completion tokens; a model with no recorded usage has no computed cost. `CARRIED_USAGE` preserves the published Fable 5 cost, tokens and latency in their original key order, since its board rows were rebuilt without those fields.

The pyproject pin and `uv.lock` must both name policyengine-us 2.60.0. The driver checks these against the installed sidecar during install, preparation and freeze. The lead updates those two files before installing the build; the supplied development venv stays on 2.41.0. The freeze retains treatment validation: Terra's run-state treatment must equal its registry card at the time of freezing. It installs the new reference revision and manifest pins, updates held-reference value pins when required, and updates the paper's reference-engine sentence. The lead owns the accompanying results prose.

## Lead command sequence

These commands are for the lead after integrating the driver into `/Users/maxghenis/PolicyEngine/policybench-wt/terra-release`. They have deliberately not been executed while implementing the driver. Keep the run, seed and grounding sources read-only. Use a new stage directory. Provision the publication-check venv at the path below separately with the newest published policyengine-us before the final check; keep the supplied `.venv` unchanged.

```bash
cd /Users/maxghenis/PolicyEngine/policybench-wt/terra-release
export OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD"
PB_PY=/Users/maxghenis/PolicyEngine/policybench-wt/terra-release/.venv/bin/python
PB_RUNS=/Users/maxghenis/PolicyEngine/policybench/results/local/terra-runs
PB_SEED=/Users/maxghenis/reviews/policybench-gemini-4-argon/worktree-results/stage2/audit
PB_GROUNDING=/Users/maxghenis/PolicyEngine/policybench/results/local/unified_audit/grounding.csv
PB_STAGE=/Users/maxghenis/PolicyEngine/policybench-wt/terra-release/results/local/terra/stage
PB_AUDIT=/Users/maxghenis/PolicyEngine/policybench-wt/terra-release/reference_audit/2026-10-22-engine-upgrade
PB_BUILD="$PB_AUDIT/reference-build"
PB_RUN=us_full_run_20260612_policyengine_4_16_1_populace
PB_CHECK_VENV=/Users/maxghenis/PolicyEngine/policybench-wt/terra-release/results/local/terra/publication-check-venv
PB_TAG=$("$PB_PY" -c 'import sys; sys.path.insert(0, "scripts"); import finish_terra as d; print(d.RELEASE_TAG)')

"$PB_PY" scripts/finish_terra.py --step pin-inputs --runs-root "$PB_RUNS"
```

Commit `docs/terra/input_pins.json`. Change `policyengine-us==2.41.0` to `policyengine-us==2.60.0` in `pyproject.toml`, then run `uv lock --upgrade-package policyengine-us` and commit those two files. This updates the lock without syncing the supplied venv. The install and freeze check the resulting pins.

```bash
"$PB_PY" scripts/finish_terra.py --step install-references --stage-dir "$PB_STAGE" \
  --grounding "$PB_GROUNDING"

# Optional explicit seed binding; prepare also binds and verifies the seed.
"$PB_PY" scripts/finish_terra.py --step bind-seed --stage-dir "$PB_STAGE" \
  --audit-seed "$PB_SEED" --grounding "$PB_GROUNDING"

"$PB_PY" scripts/finish_terra.py --step prepare --runs-root "$PB_RUNS" \
  --stage-dir "$PB_STAGE" --audit-seed "$PB_SEED" --grounding "$PB_GROUNDING"

# Supply the authorized isolated judge login to these commands.
export CLAUDE_CONFIG_DIR="$HOME/.policybench-judge/pb-judge-config"
"$PB_PY" scripts/finish_terra.py --step judge --stage-dir "$PB_STAGE"
"$PB_PY" scripts/restate_gpt61sol_adjudications.py --stage-dir "$PB_STAGE" \
  --audit-seed "$PB_SEED"
"$PB_PY" scripts/finish_terra.py --step triage --stage-dir "$PB_STAGE"
```

The judge command requires the authorized `CLAUDE_CODE_OAUTH_TOKEN` and `AUDIT_ACCOUNT` environment values expected by `scripts/run_audit_claude.sh`. Export neither credential into a committed file. The restatement command updates carried decisions' judge fields from the bound seed and current verdicts while preserving their decisions. If restatement or triage stops, review the bound verdicts, `reference-flags.csv` and `unresolved-rows.csv` where present, record any permitted developer decision in the spec, set its two date fields, then continue:

```bash
# Rebind after a spec edit, then apply its decisions and repeat triage.
"$PB_PY" scripts/finish_terra.py --step install-references --stage-dir "$PB_STAGE" \
  --grounding "$PB_GROUNDING"
"$PB_PY" scripts/finish_terra.py --step adjudicate-exclusions --stage-dir "$PB_STAGE"
"$PB_PY" scripts/finish_terra.py --step triage --stage-dir "$PB_STAGE"

"$PB_PY" scripts/finish_terra.py --step provenance --stage-dir "$PB_STAGE"
```

Commit the checked `docs/terra/judge_provenance.json`, its generated note unedited, and any spec changes before export. Fill the result placeholders below and update the paper's release prose before rendering.

```bash
"$PB_PY" scripts/finish_terra.py --step export --stage-dir "$PB_STAGE"
"$PB_PY" scripts/freeze_terra.py --stage-dir "$PB_STAGE" --dry-run
"$PB_PY" scripts/freeze_terra.py --stage-dir "$PB_STAGE"

"$PB_PY" "$PB_AUDIT/scripts/sweep_timing.py" check --build "$PB_BUILD" \
  --snapshot "$PWD/paper/snapshot/20260501/runs/$PB_RUN" \
  --check-venv "$PB_CHECK_VENV"

"$PB_PY" paper/render_paper.py
"$PB_PY" scripts/freeze_snapshot.py --rendered-only
```

Export writes `data-board51.json` and a hash-bound `release-ready.json`. Both freeze modes rebuild that payload from its bound inputs and validate every gate; `--dry-run` validates before the following freeze command writes the repository artifacts. The freeze uploads nothing. If the publication check finds another scored move, stop and stage a reviewed build for it before proceeding.

## Lead completion record

- [LEAD: Record Terra's score, rank, cost, latency and response window from the gated release.]
- [LEAD: Record carried, re-opened and newly judged case counts, including the four changed-reference cases.]
- [LEAD: Record every triage decision and its dates, or state that triage needed none.]
- [LEAD: Record export scope checks, freeze dry-run, freeze and treatment-validation outcomes.]
- [LEAD: Record the publication-check time, newest engine, comparison outcome and check venv.]
- [LEAD: Record paper rendering, rendered-only repinning and any manual publication preparation.]
