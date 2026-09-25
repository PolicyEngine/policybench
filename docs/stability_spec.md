# Stability measurement spec

Version: `2026-08-18-v1`. Status: **spec adopted after adversarial review**
(see the review section at the end); implementation follows this document,
and every paid run is gated on explicit approval.

## Why

"The Stability Trap: Evaluating the Reliability of LLM-Based Instruction
Adherence Auditing" (Shergadwala, FAccT '26, arXiv:2601.11783) shows LLM
judges can reach >99% verdict agreement while the reasoning behind those
verdicts is unstable — as low as ≈19% reasoning stability on the paper's
worst quantitative rubric check (a judge-side word-count task; its
quantitative checks cluster roughly 19–30%), with >90% stability observed
only on verbatim closed-list extraction tasks. The paper's instability is
measured on the *judge* side — judges doing arithmetic — which is why this
spec's own judge is never allowed to compute or compare anything; the trap
it names, high verdict agreement masking fragile reasoning, is the risk
this spec measures in PolicyBench's *benchmarked models*.

PolicyBench is exposed in three places:

1. **Answer stability is asserted, not measured.** The manuscript's
   Uncertainty section states that the benchmark sample, not run-to-run
   model variation, dominates uncertainty (`paper/index.qmd`, "These
   intervals are a manuscript artifact…"), with no committed repeated-run
   artifacts behind it. The machinery exists (`eval-no-tools-repeated`,
   `analyze --runs-dir`, `run_stability_by_model`) and has never been run
   for the record.
2. **Explanations are collected but unexamined for stability.** Every
   scored response carries a required per-output explanation. The paper
   correctly disclaims them as faithful reasoning traces — but if a model
   gives the same right answer twice citing two different mechanisms, that
   is measurable evidence about its reliability as a policy explainer,
   independent of trace faithfulness.
3. **Counterfactual behavior is untested.** Stewart ("Beyond Explanation",
   arXiv:2603.22716) proposes counterfactual interrogation rights:
   affected parties should be able to probe a deciding system with
   modified inputs and observe whether outcomes change — benefit
   determinations are a central example, and the interrogation must hit
   the pinned system version that made the decision. PolicyEngine answers
   such probes exactly; models' implied counterfactual responses have
   never been compared to it. Here the models are interrogated as if they
   were the deciding system, with PolicyEngine computing the true
   counterfactual and per-arm provider fingerprints standing in for the
   pinned-version requirement.

Everything ships under the frozen-board discipline of
`sensitivity/claude-thinking-2026-08.md` and
[policybench#139](https://github.com/PolicyEngine/policybench/issues/139):
frozen board scores are never edited (32 models as of the 2026-08-22
refreeze that added Grok 4.6 and Ox Alpha); stability results publish as labeled
sensitivity artifacts (a `sensitivity/*.md` doc plus release-attached
CSVs), or fold into the v2 board protocol as a versioned re-run.

## Shared definitions

- **Row**: one `(model, scenario_id, variable)` cell; `variable` is an
  expanded output id (person-level coverage flags expand per person). The
  frozen US manifest yields 1,984 rows per model: 1,000 amount rows and
  984 binary rows.
- **Run**: one complete pass over a fixed scenario manifest for one model
  under one serving treatment, tagged `run_id` (`run_000`, …), produced by
  `eval-no-tools-repeated`, which routes through `run_single_no_tools`, so
  per-model cards (answer contract, chunk size, timeouts, completion
  budgets, in-request repair rounds) apply per request exactly as in board
  runs. Board *pipelines* additionally ran chunk-completeness gating,
  post-run response retries, and row repairs; repeats deliberately run the
  single-shot sync path, so repeat coverage is a lower bound on board
  coverage and layer-1 claims are scoped to within-repeat-set comparisons.
- **Repeat set**: exactly K runs (K pinned per repeat set; default 3,
  ladder to 5 — never mixed within one table) of the same manifest, model
  set, programs, prompt contract, and condition. The serving condition
  (effective `tool_choice`, chunk override) is recorded in each run's
  resume-metadata sidecar **(new in this change** — today's sidecar
  records neither `POLICYBENCH_TOOL_CHOICE` nor
  `POLICYBENCH_CHUNK_OVERRIDE`**)**, and `stability-report` refuses to
  pool runs whose fingerprints mismatch.
- **Cache discipline (hard requirement)**: as shipped, the CLI enables the
  LiteLLM disk cache for `eval-no-tools-repeated` and every request sets
  `caching: True` with no run-specific key material
  (`policybench/cli.py` enable-cache set, `eval_no_tools.py`
  request kwargs, `cache.py` namespace =
  `policybench:{PROMPT_CONTRACT_VERSION}`), so runs 2..K would replay run
  1's cached completions and every stability metric would measure the
  cache. Implementation therefore (a) stops enabling the disk cache for
  `eval-no-tools-repeated`, and (b) makes `stability-report` **hard-fail**
  when any run's spend ledger contains a `cache_hit: true` record, and
  report the count of `provider_response_id` values shared across runs as
  a residual replay diagnostic. The same guard applies to both
  counterfactual arms.
- **Parse, per row type**: an amount row is parsed iff its prediction is a
  non-null numeric; a binary row is parsed iff `binary_flag(prediction)`
  is not `None`. Binary rows with numeric but non-0/1 predictions are
  counted in their own `invalid_binary_rate` bucket — never as flips,
  never as exact.
- **Mutual exact** (prediction vs prediction): headline tolerance applied
  between two predictions — amounts `|p_a − p_b| ≤ $1`; binary rows equal
  parsed flags. Unparsed values are never mutually exact.
- **Exact-correct** (prediction vs reference): existing headline semantics
  (`row_hit_scores(...)["exact"]`).
- **Reference discipline**: the frozen snapshot's references were
  generated with policyengine-us 1.755.4; the current environment installs
  1.723.0 through the `policyengine[us]==4.16.1` bundle. Regenerated
  base-arm references agree with the frozen CSV on 1,983/1,984 rows within
  $1 (max drift $67.74, one state-tax row, measured 2026-08-18). Rules:
  layer-1 scoring uses one fixed reference file for all runs (the frozen
  CSV, for board comparability); layer 3 regenerates **both** arms with
  the installed engine and never mixes frozen with regenerated references
  inside a delta; every export records the installed policyengine-us
  version and the base-vs-frozen drift count.
- **Scenario manifest**: `paper/snapshot/20260501/us_scenarios.csv`
  (US-only in this iteration).

## Layer 1 — answer stability

**Question**: how much does a model's score and row-level output move when
the identical request is repeated, and is that movement small relative to
household-sampling uncertainty (the manuscript's unmeasured claim)?

### Existing machinery (unchanged)

`eval-no-tools-repeated` → `run_000.csv…`; `analyze --runs-dir` →
`summarize_runs_by_model` → `run_stability_by_model`. These stay as-is.

### New row-level metrics (`row_stability_by_model`)

Computed per model. Pair metrics pool the C(K,2) unordered run pairs per
row; row metrics are K-way. All rows of a scenario come from 1–3
completions per run, so pooled pair counts overstate precision ~20×:
every pooled rate ships with a **scenario-level cluster bootstrap CI**
(households resampled with replacement, all their rows carried along), and
`n_scenarios` publishes beside `n_rows` / `n_run_pairs`; `n_run_pairs` is
never quoted as precision.

- `unanimous_parse_rate@K`, `coverage_flip_rate`: rows parsed in all K
  runs / parsed in ≥1 and unparsed in ≥1 (per-type parse definition).
- `invalid_binary_rate`: binary rows with ≥1 numeric non-0/1 prediction.
- `answer_flip_rate`: share of run pairs, both sides parsed, that are not
  mutually exact. Pair-level, so K-invariant.
- `unanimous_exact_answer_rate@K`: rows with all K runs parsed and
  pairwise mutually exact (labeled with K; increases mechanically with K,
  so never compared across different K).
- `verdict_flip_rate_parsed` / `verdict_flip_rate_all`: share of run
  pairs whose exact-correct verdicts differ — the parsed variant requires
  both sides parsed (the stability-trap headline analogue); the all-rows
  variant scores unparsed as wrong (headline-consistent) and therefore
  absorbs coverage flips; both denominators are stated in the export.
- `consistently_wrong_divergent_rate`: **amount rows only** (a parsed
  wrong binary flag can only equal the one wrong value, so binary
  divergence is impossible by construction), among rows with all K runs
  parsed and all K wrong: the share where wrong answers are not mutually
  exact — "consistently wrong, differently wrong." The signature pairing
  is a low `verdict_flip_rate_parsed` with a high
  `consistently_wrong_divergent_rate`: stable grades, unstable outputs.

### Variance decomposition (`stability_variance_decomposition`)

Per model:

- `run_score_std`: sample std (ddof=1) of the K run-level headline scores
  (household-impact-weighted exact rate, per `run_id`, via
  `household_headline_scores(metric="exact")`).
- `run_score_std_ci_low/high`: chi-square CI on that std (df = K−1;
  multipliers at K=3: [0.578, 4.415]; K=5: [0.649, 2.372]). Normality of
  run scores is a reasonable CLT approximation (each is a mean over ~100
  households); the df, not normality, is the binding limitation.
- `sampling_se`: per run, `std(household scores, ddof=1) / sqrt(n)` with
  `n` = the positive-weight household count after the weighting drop,
  averaged across runs.
- `run_to_sampling_ratio` with an explicit decision rule: the manuscript
  claim "sampling dominates run-to-run variation" is **confirmed** iff
  `run_score_std_ci_high` (one-sided 95% upper bound) < `sampling_se`. At
  K=3 that requires a point ratio below ≈0.23 (the detectable-effect
  floor, printed in the artifact); otherwise the result is reported as
  inconclusive-at-K, never as a confirmation.
- Pooled roster estimate: run-score deviations pooled across the M models
  of the repeat set (M·(K−1) df) give a roster-level
  `pooled_run_to_sampling_ratio` with usable power, published with a
  per-model homogeneity table (each model's contribution to the pooled
  sum of squares).

### Runbook (paid; gated)

```bash
RUN_DIR=results/local/stability_20260818
K=3
MANIFEST=paper/snapshot/20260501/us_scenarios.csv
FROZEN_REFS=paper/snapshot/20260501/us_reference_outputs.csv

# One runs-subdirectory per provider group (separate invocations sharing
# one output dir would collide on run_NNN.csv resume metadata). Execution
# within an invocation is serial; schedule groups in parallel terminals.
# A provider 429 beyond in-layer retries exits the command; rerunning the
# identical command resumes from the checkpoint.
uv run policybench eval-no-tools-repeated \
  --country us \
  --scenario-manifest "$MANIFEST" \
  --output-dir "$RUN_DIR/us/runs/openai" \
  --repeats "$K" \
  --model gpt-5.4-mini

uv run policybench eval-no-tools-repeated \
  --country us \
  --scenario-manifest "$MANIFEST" \
  --output-dir "$RUN_DIR/us/runs/gemini" \
  --repeats "$K" \
  --model gemini-3.7-flash

# Repeated-run invocations run cache-free by design (see Cache discipline).

uv run policybench analyze \
  -g "$FROZEN_REFS" \
  -p "$RUN_DIR/us/runs/openai/run_000.csv" \
  -s "$MANIFEST" \
  -o "$RUN_DIR/us/analysis" \
  --app-data-output "$RUN_DIR/us/analysis/data.json" \
  --runs-dir "$RUN_DIR/us/runs/openai"

# --app-data-output must ALWAYS be re-pointed inside the run directory:
# its default is app/src/data.json, and the local app prefers that file
# over the pinned frozen artifact — writing it would violate the
# frozen-board discipline this spec operates under.

uv run policybench stability-report \
  --runs-dir "$RUN_DIR/us/runs/openai" \
  --runs-dir "$RUN_DIR/us/runs/gemini" \
  --reference-outputs "$FROZEN_REFS" \
  --scenario-manifest "$MANIFEST" \
  --output-dir "$RUN_DIR/us/stability"
```

`stability-report` accepts repeated `--runs-dir` flags (model sets must be
disjoint across dirs), validates run-fingerprint consistency, enforces the
cache guard, and emits `stability_metadata.json` including each run's
effective serving config diffed against
`paper/snapshot/20260501/model_serving_config.json`.

Layers 2 and 3 continue from the same repeats:

```bash
# Layer 2 (judge spend only; --deterministic-only for the free channels).
uv run policybench reasoning-stability \
  --runs-dir "$RUN_DIR/us/runs/openai" \
  --runs-dir "$RUN_DIR/us/runs/gemini" \
  -g "$FROZEN_REFS" \
  -o "$RUN_DIR/us/reasoning"

# Layer 3 truth arm (free, local PolicyEngine; ~3 minutes).
uv run policybench counterfactual-manifest -o "$RUN_DIR/us/cf"

# Layer 3 model arm (paid): run the perturbed manifest once per model with
# the ordinary runner, then report against the repeats as the base arm.
uv run policybench eval-no-tools-chunked \
  --country us \
  --scenario-manifest "$RUN_DIR/us/cf/cf_scenarios.csv" \
  --output-dir "$RUN_DIR/us/cf_arm" \
  --model gpt-5.4-mini --model gemini-3.7-flash \
  --chunk-size 5 --parallel 1 --model-parallel 1 --chunk-attempts 1

uv run policybench counterfactual-report \
  --perturbed-predictions "$RUN_DIR/us/cf_arm/predictions.csv" \
  --truth-deltas "$RUN_DIR/us/cf/truth_deltas.csv" \
  --base-runs-dir "$RUN_DIR/us/runs/openai" \
  --base-runs-dir "$RUN_DIR/us/runs/gemini" \
  -o "$RUN_DIR/us/cf_report"

# Price any rung from logged usage before spending.
uv run policybench stability-cost-plan \
  -p paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace/predictions.csv.gz \
  --repeats 3 --cf-arms 1
```

The rung-0 dry run of these commands (2026-08-23, free): the truth arm
reproduces the measured distribution exactly (247 nonzero amount rows, 0
binary flips, zero-delta share 0.8755), and the cost plan prices the
32-model roster at $1,337 for 4 arms + ≈$149 judge — Claude Fable 5
and Ox Alpha report `unpriced` (run-level and stealth-preview usage
respectively) rather than guessed; Fable prices separately at ≈$216/4
arms, consistent with the ladder's ≈$1,550+.

## Layer 2 — reasoning stability

**Question**: when a model gives the same answer twice, does it cite the
same mechanism twice? Headline: the **"right answer, unstable reasoning"
rate** — among repeat pairs where the answer is stable and correct, the
share whose explanations invoke different mechanisms.

### The judge's epistemic status (corrected after review)

Mapping an explanation onto 12 mechanism labels is **semantic
classification — the Stability Trap paper's Tier-2 regime, which it
brackets at roughly 35–83% reasoning stability — not the verbatim
closed-list extraction where it observed >90%**. The design keeps the
judge as close to the stable regime as the task allows (single text in,
discrete labels out, no pairs, no comparison, no arithmetic; the paper's
judge-side instability was specifically judges doing arithmetic), but
reliability is **established empirically by the validation battery below,
never asserted by construction**. The paper itself measured reasoning
similarity with a deterministic pipeline (regex fingerprinting +
sentence-embedding clustering); this spec prefers taxonomy labels because
they are interpretable policy mechanisms aligned with PolicyBench's audit
annotation system and comparable across models — accepting, in exchange,
a judge that must itself be validated. The deterministic numeric-claim
channel below is the in-design hedge; the pre-registered fallbacks if the
gate fails are (1) reformulate as 12 independent per-label yes/no rubric
questions (the binary-verdict form the paper found most stable), then
(2) collapse to 5 super-domains
(`income_and_deductions` = {taxable_income_or_deductions, asset_resource,
period_annualization}; `rates_and_phaseouts` = {thresholds_rates,
credit_phaseout}; `eligibility` = {categorical_eligibility,
age_disability, household_unit_or_filing_status}; `program_specific` =
{health_coverage, payroll_tax_base, state_local_rule}; `other`).

### Pair selection (deterministic)

For each row and each of the C(K,2) run pairs:

- **Answer-stable pair**: both runs parsed, mutually exact.
- **Stable-and-exact pair**: answer-stable AND both runs exact-correct.

Mechanism grading applies to answer-stable pairs; both strata are
reported with their denominators and the share of all pairs they cover.

### Mechanism labels

`MECHANISM_LABELS` = `FAILURE_SUBTYPE_VALUES` minus `missing_output` (a
parse status, not a mechanism): 12 labels, multi-label extraction (a
payroll-tax derivation citing the 6.2% Social Security rate up to the
wage base maps to `{payroll_tax_base, thresholds_rates}`).

### Judge (LLM, discrete extraction only)

- Input: one explanation text plus `(variable, country, year)` context;
  output strict JSON `{"labels": [...]}` validated against
  `MECHANISM_LABELS`; invalid → one retry → error row (excluded from
  metrics, counted in `judge_error_rate`).
- Prompt: fixed instructions, label glossary, and 3–5 static few-shot
  examples drawn from the committed reference-explanation CSV, committed
  verbatim in code. One prompt version grades model and reference
  explanations alike; the version string rides in every output row.
- Anchoring: the reference explanation for each `(scenario_id, variable)`
  (coverage: 1,984/1,984 cells) is extracted once through the same judge;
  the same-row reference is never shown while grading a model explanation.
- Judge calls never enable the LiteLLM disk cache. The module's own
  dedup cache is keyed by
  `sha256(prompt_version ‖ variable ‖ normalized_text ‖ grade_pass)`, so
  validation re-grades are genuinely independent calls while identical
  texts within one pass share one call. Verbatim-identical explanation
  pairs short-circuit to "same labels" with no call; the share of stable
  pairs resolved by this short-circuit is published per model (see the
  asymmetry note under Metrics).
- Judge models: primary `--judge-model` (default gemini-3.7-flash),
  secondary `--cross-judge-model` (default gpt-5.4-mini), temperature 0,
  ids + resolved versions recorded.

### Validation battery (the load-bearing control)

1. **Gold-set validity gate.** A committed, stratified gold set of 90
   explanations — 5 per output group from the reference-explanation CSV,
   sampled with seed 20260818 — labeled against the taxonomy and versioned
   at `annotations/stability_reasoning_gold_set.csv` (labeled 2026-08-23 by
   the maintainer agent as developer adjudication, pending maintainer
   review; label prevalence ranges from thresholds_rates 59/90 to
   period_annualization 2/90, with `other` at zero as expected for
   reference explanations). The gate: judge
   exact-set accuracy vs gold ≥ 0.80, flagged CI-aware (fail when the 95%
   lower bound sits below 0.70). Per-label agreement and prevalence
   tables publish alongside. Thresholds are provisional until the rung-1
   pilot and are recorded in the export either way.
2. **Cross-judge reliability.** The ~10% validation sample (deterministic
   hash of the dedup key) is extracted by both judge models;
   `cross_judge_set_agreement` ≥ 0.90 flagged CI-aware. This is the
   reliability statistic — same-model temp-0 re-grading measures serving
   determinism, not extraction validity, so it is reported only as a
   `determinism_floor` and gates nothing.
3. **Agreement statistics that survive skewed prevalence**: per-label
   Gwet's AC1 and raw agreement with a prevalence column (the motivating
   paper's own choice for this regime), Krippendorff's alpha over label
   sets with Jaccard distance; Cohen's κ only as a supplementary column
   for labels with ≥20 validation occurrences (κ is prevalence-paradox
   degenerate below that).
4. **Paper-comparable statistic**: per-row dominant-label-set share
   across the K runs (the R_stab analogue). Pairwise agreement rates are
   never numerically compared with the paper's percentages (pairwise 0.90
   corresponds to a dominant-share ≈0.95).
5. **Judge noise floor / attenuation.** From double-graded texts:
   `pair_noise_floor` = P(two independent extractions of the same text
   disagree). The headline publishes raw and attenuation-adjusted
   (`max(0, (observed − floor) / (1 − floor))`), plus the
   verbatim-short-circuit share — a model that repeats canned text incurs
   zero judge noise while a paraphrasing model incurs it twice, so the
   headline restricted to non-identical-text pairs is the like-for-like
   companion.

If the gate fails, layer-2 outputs still export, flagged
`judge_below_reliability_bar`, and the headline is not reported; the
pre-registered fallbacks above are the next step, not ad hoc re-prompting.

### Metrics (deterministic, from extractions)

Per model:

- `mechanism_agreement_rate_stable[_exact]`: identical label sets among
  answer-stable [stable-and-exact] pairs.
- **`right_answer_unstable_reasoning_rate`** = 1 −
  `mechanism_agreement_rate_stable_exact`. Conditioning on
  stable-and-exact is a composition-sensitive denominator, so it ships
  with three companions: (a) the **joint rate** over ALL pairs (stable ∧
  exact ∧ mechanism-divergent — fixed denominator, cross-model comparable
  by construction); (b) a **direct-standardized** rate reweighted to the
  pooled stable-pair output-group composition of the report's models; (c)
  a suppression rule — no headline below 200 stable-and-exact pairs — and
  a per-model stratum-composition table.
- `mechanism_jaccard_mean_stable[_exact]`: graded softening.
- `numeric_claim_jaccard_mean`, `numeric_claim_disjoint_rate`
  (deterministic channel): currency amounts (rounded to $1) and
  percentages (rounded to 0.1pp) regex-extracted from each explanation,
  excluding values within $1 of the row's own prediction (the restated
  answer would inflate overlap); disjoint = both non-empty, empty
  intersection.
- `reasoning_unstable_strict_rate`: labels differ OR claims disjoint
  (sensitivity companion, not the headline).
- `reference_alignment_rate`: among exact-correct run-explanations
  (row-level), share whose label set equals the reference explanation's.
- All pooled pair rates carry scenario-level cluster bootstrap CIs, as in
  layer 1.

## Layer 3 — counterfactual consistency

**Question**: when one input changes, does the model's answer change the
way the law says it should?

### Perturbation

One twin per scenario: `adults[0]` (the head in all 100 manifest
scenarios) `employment_income` += **$1,000**. Twins are built at the
`Scenario` level — `scenario_from_dict` → perturb → `id = f"{base}__cf1k"`
→ `scenario_manifest()` — never by editing the frozen CSV, so the embedded
id, recomputed `total_income`, and `scenario_json` stay mutually
consistent (`load_scenarios_from_manifest` hard-fails on id mismatch).
The perturbed manifest adds `base_scenario_id`, `perturbed_field`,
`perturbation_amount` columns (ignored by the loader) and mirrors them in
`scenario_json.metadata.counterfactual`.

An absolute increase is the only perturbation well-defined for every
household: 44/100 heads have zero wages, where percentage or decrease
perturbations are degenerate. For those 44 twins the rendered prompt gains
a wages line that the base prompt omits entirely (the template renders
head wages only when nonzero, and the prompt preamble instructs "treat any
unlisted numeric input as 0", which keeps the base well-posed); these
`first_dollar` pairs are flagged and reported as a sub-split beside the
wage-shift pairs. An optional −$1,000 arm on the 55 households with wages
≥ $1,000 is a costed rung extension (~0.55 of an arm; measured
expectation: 135/550 nonzero amount deltas, 1 eligibility flip) that
would separate schedule knowledge from a "wages up ⇒ taxes up" direction
prior; percentage shocks and demographic perturbations are future
conditions.

### Measured truth-delta reality (installed policyengine-us 1.723.0, 2026-08-18)

The entire design below is disciplined by the measured distribution of
true deltas on this manifest (regenerate via
`counterfactual-manifest --write-truth-deltas`):

- 1,984 matched rows: 1,000 amount, 984 binary. **Zero** binary
  eligibility flips. 247 amount rows with `|Δ| > $1`; zero-delta share
  87.55%.
- Nonzero rows by group: payroll_tax 100 (median +$76.50), federal income
  tax 46, state income tax 44, federal refundable credits 21, state
  refundable credits 19, snap 13 (median −$237.60), ssi 3, tanf 1;
  local_income_tax and self_employment_tax 0.
- Sign split 216 positive / 31 negative.
- `|Δ| ≥ $500` selects 4 rows (two +$550 refundable-credit phase-ins, one
  SSI −$500.003 that clears the cut by three tenths of a cent, one TANF
  −$750) — no SNAP or Medicaid boundary anywhere near it.

### Arms

Truth: both arms' references computed together with the installed engine
(`true_delta = ref_perturbed − ref_base` per row; deltas rounded to cents
before any threshold comparison). Model: one run per arm under identical
serving treatment; the base arm reuses the layer-1 repeats when run in the
same session — and once repeats exist, `pred_delta` is computed against
**every** base repeat, giving a delta distribution rather than one
arbitrary pairing. Per-arm `provider_resolved_model` /
`provider_system_fingerprint` summaries are recorded, and matched pairs
whose arms resolved to different provider fingerprints are counted and
flagged (the Stewart pinned-version concern, at the level an API consumer
can observe). Nothing in any prompt names the twin relationship; this
measures *implied* counterfactual response, not in-context delta
reasoning.

### Metrics

Primary reporting universe: the **247 nonzero-true-delta amount rows**,
with the six groups at n ≥ 10 (payroll, federal tax, state tax, federal
refundable, state refundable, snap) pre-registered as reportable;
ssi/tanf/local/self-employment publish row counts only. Amount and binary
rows are never pooled into one rate. Pooled-1,984-row rates appear only as
a secondary column beside the zero-delta baseline (`pred_delta ≡ 0`),
which scores 87.55% on pooled delta-exact by construction.

Per model, on matched rows with both arms parsed (`delta_coverage`
reported):

- `delta_exact_rate`: `|pred_delta − true_delta| ≤ $1`.
- `delta_within_10pct_rate`: band = `max($1, 0.10 · |true_delta|)` — the
  floor makes within-10% a strict superset of delta-exact (65/247 nonzero
  true deltas sit below $76.50, where a bare relative band would invert
  the two metrics; this deliberately diverges from the level metrics'
  zero-floor semantics).
- `delta_sign_agreement` on nonzero-true rows, with `sign(x) = 0` for
  `|x| ≤ $1`, reported **per direction** (positive-recall and
  negative-recall separately — 216/31 asymmetry means a "wages up ⇒ taxes
  up" prior scores ≈0.9 pooled, and the negative column is where
  schedule knowledge shows).
- `delta_mae` (nonzero rows; pooled as secondary).
- **Large-response detection** (renamed from "cliff" — the $1,000 shock
  crosses no observed program boundary): true cut `|Δ| ≥ $200` (n=40,
  spanning 6 groups, with a margin from the nearest mass point), predicted
  cut ≥ $100 in the true direction; exact binomial CI; suppressed below
  n=20 qualifying rows; the qualifying-row list is committed in the
  artifact so membership is auditable.
- Binary rows: the reference produces **zero flips**, so flip
  recall/precision are undefined and are **not published as rates**; the
  export carries raw counts instead — `n_reference_flips = 0` and each
  model's `n_model_flips` (false-positive flips, informative on its own).
  A flip-capable perturbation (magnitude verified to cross boundaries the
  way this spec's truth-delta audit was computed, target ≥ ~20 reference
  flips) is a pre-registered future rung, not a promise of this one.
- **Noise floor** (requires layer-1 repeats): every delta statistic is
  paired with the same statistic computed between two base repeats
  (true delta ≡ 0), on the **same row subset** (nonzero-true rows,
  large-response rows, binary rows — the base-base false-flip count is
  the binary floor). "Distinguishable from repeat noise" is a named test:
  scenario-level paired cluster bootstrap of (signal statistic − floor
  statistic); indistinguishable iff the 95% interval covers 0.

## Artifacts and discipline

- New CLI: `stability-report`, `reasoning-stability` (with
  `--deterministic-only` to skip the judge), `counterfactual-manifest`
  (twin manifest + both-arm references + optional truth-delta export),
  `counterfactual-report`, `stability-cost-plan`.
- Every export carries `stability_metadata.json`: spec version, prompt
  contract, condition fields, cache mode + guard result, judge
  models/prompt versions, installed PE versions + base-vs-frozen drift
  count, manifest hash, run fingerprints, serving-config diff vs the
  snapshot registry.
- Results publish as `sensitivity/stability-<date>.md` + release-attached
  CSVs. Never an edit to frozen board scores or `app/` data; every
  `analyze` invocation in the runbook re-points `--app-data-output` into
  the run directory (its default writes `app/src/data.json`, which the
  local app prefers over the pinned artifact).
- The v2 board plan (#139) is the natural carrier for a full-roster
  repeat protocol; rungs 1–2 de-risk the metrics on the v1 manifest.

## Cost ladder (measured basis; no spend authorized here)

One full-roster board-condition run ≈ $316 recorded + Claude Fable 5
≈$54.10 (run-level usage; $0.541/hh) + two unpriced models at override
prices (grok-build-0.1 ≈$4.50, gemini-3.6-flash ≈$5.50) ≈ **$380/run**
for the original 30 models; the 2026-08-22 refreeze adds grok-4.6
($8.70/run logged) and ox-alpha (stealth preview, no logged or listed
price — reported unpriced, never guessed), bringing the priced roster
total to ≈$389/run + Fable ≈$54.
Repeats run cache-free, so arms price at full run cost. Judge basis:
≈800 input + 30 output tokens/call at gemini-3.7-flash overrides
($0.75/$3.75 per 1M) = $0.0007125/call; 5,952 calls per model per K=3
repeat set = **$4.24/model pre-dedup** (verbatim dedup lowers it; the
pilot reports the realized rate); one-time reference-anchor extraction
(1,984 calls) ≈ $1.41.

| Rung | Scope | Model spend | Judge spend | Purpose |
|---|---|---|---|---|
| 0 (this PR) | mocks + fixtures; free local truth-deltas | $0 | $0 | metrics, tests, dry run |
| 1 pilot | gpt-5.4-mini ($0.58/run) + gemini-3.7-flash ($1.44/run) × (3 repeats + 1 cf arm) | ≈ $8 | ≈ $17 double-graded (2 models × 3 runs × 1,984 × 2 passes), plus $1.41 anchors | end-to-end validation; gold-set + cross-judge gates |
| 2 subset | top-8 as ranked on the 32-model board (sol, kimi-k3, luna, ox-alpha†, inkling, gpt-5.5, terra, grok-4.6) = $105.8/run priced × 4 arms | ≈ $423 + ox-alpha† (≈$235 without kimi-k3) | ≈ $39 (incl. 10% validation) | reportable sensitivity doc |
| 3 full | 32-model v1 roster × 4 arms ≈ $1,553 + ox-alpha† + Fable ≈$216, or fold into the 20-model v2 protocol | — | ≈ $149 (incl. validation + anchors) | board-grade artifact |

† ox-alpha is an unpriced stealth preview: its usage logged $0 and no
list price exists, so `stability-cost-plan` reports it `unpriced`; its
spend must be observed at rung time, not estimated here.

Optional −$1,000 arm (55 households): ≈0.55 × one arm per model. Every
paid rung is gated on explicit approval; boring before billed.

## Adversarial review record (2026-08-18)

Per process, the metric definitions were adversarially reviewed before
implementation: five lens-diverse reviewers (statistical validity,
literature fidelity — both papers fetched and read, PolicyBench
integration, counterfactual design, ops/cost) produced 36 findings; the
independent verification stage was interrupted by an account rate limit,
so the maintainer-agent re-verified the load-bearing findings directly
against code and data before adopting them. Highlights that reshaped v1:

- **Cache replay (4 reviewers independently)**: the drafted runbook would
  have had repeats 2..K replay the LiteLLM disk cache, making "perfect
  stability" a cache artifact — the exact stability-trap failure the spec
  exists to catch. Fixed via cache-free repeats + a hard ledger guard.
- **Truth-delta audit (verified by independent recomputation)**: +$1,000
  produces zero binary flips, 247/1,000 nonzero amount rows, a 216/31
  sign split, and no $500-scale program boundary — layer 3 was rebuilt
  around the measured distribution (nonzero-stratum primary reporting,
  flip counts instead of flip rates, "large response" instead of "cliff",
  per-direction sign recall).
- **Judge regime honesty**: 12-label extraction is the paper's Tier-2
  classification regime (35–83% observed stability), not its >90%
  verbatim-extraction regime; the validation battery, not construction,
  carries the reliability claim, with gold-set + cross-judge gates
  replacing circular temp-0 self-agreement, AC1/Krippendorff replacing
  prevalence-fragile κ, and pre-registered fallbacks.
- **Statistical decision rules**: chi-square-CI-based confirmation rule
  (K=3 detectable floor ≈0.23) plus a pooled roster estimator for the
  sampling-dominance claim; scenario-level cluster bootstrap CIs on all
  pooled rates; K-invariant pair-level flip metrics; composition-adjusted
  companions for the conditioned headline.
- **Ops corrections**: real `analyze` flags; `--app-data-output`
  re-pointed away from `app/src/data.json`; per-provider-group run dirs;
  serving-condition fields added to resume metadata; engine-version
  discipline (1.755.4 snapshot vs 1.723.0 installed, 1,983/1,984 rows
  within $1); corrected arithmetic throughout the cost ladder.
