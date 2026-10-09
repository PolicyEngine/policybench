# Draft: paper changes for the Claude Haiku 5.5 release

DRAFT, written against the 2.37.2 rehearsal. Each `{r.x}` below is a new
`policybench.paper_results` accessor, computed from the frozen snapshot and pinned by
a test (tests/test_paper_results.py). Bracketed values are the rehearsal's.

## 1. New paragraph after the October 5 review (paper/index.qmd, after line 1087)

On `{r.ruling_date}` [2026-10-06] PolicyBench excluded `{r.ruled_exclusion_count_word}`
[ten] more outputs. `{r.adversary_output_count_word}` [Eight] came from a reference
adversary (`reference_audit/2026-10-05-reference-adversary`). It flags the scored outputs
where many models, or several of the strongest, agree on an answer the reference does not
give. A judge that cannot see the engine's derivation then works each flagged output from
primary law, and only afterwards reconciles its answer with the derivation. It flagged 61
outputs and ran 52, the rest belonging to other audits, and held 45 references. Of the
seven it did not hold, an independent check confirmed four engine defects: Arizona's 2026 standard deduction left unindexed (A.R.S. 43-1041(H)), Ohio's
medical deduction counting premiums only for Medicare-eligible filers without an
employer-paid plan (R.C. 5747.01(A)(10)), Colorado's 2026 sales tax refund paid without the
excess revenues C.R.S. 39-22-2003(2) requires, and New York's 2026 child and dependent care
credit under Tax Law 606(c-2). It found one question of definition, in two households whose
dependent earns $45,000 of wages and must file their own return: the output definitions name
no return, so the household's federal and state income tax can be read with or without that
return. It refuted the seventh, in North Carolina, whose references stand. The other two
outputs are two Louisiana households' 2026 state
income tax, which rests on a standard deduction policyengine-us computed from published price
indexes and Louisiana first published on 2026-09-28, after the freeze. All ten records are
computed on policyengine-us `{r.september_upgrade.engine_version}` [2.15.17].

## 2. The October engine move (patch B, results/local/upgrade-scratch/paper-upgrade-support)

Table row "(October 2026 upgrade)" in @tbl-reference-review, and after the September
upgrade paragraph:

On `{r.last_engine_upgrade.date}` PolicyBench moved the references again, from
policyengine-us `{r.last_engine_upgrade.previous_engine_version}` to
`{r.last_engine_upgrade.engine_version}`, a release that fixes engine defects behind
excluded outputs. With the same publication conventions it recomputed every output. The
move returns `{r.engine_upgrade_restored_count_word}` [seven] excluded outputs to scoring:
each lands within $1 of the value its exclusion said the law gives, and each names the
upstream fix (`regenerated_exclusions` in the reference sidecar). It changes
`{r.engine_upgrade_scored_change_count_word}` [one] scored reference beyond the dollar
tolerance (Idaho's $10 permanent building fund tax) and excludes
`{r.engine_upgrade_new_exclusion_count_word}` [two] outputs it moves onto an unstated input,
the Indiana county whose income tax the engine assigns when the prompt names none.
PolicyBench re-reviewed the `{r.engine_upgrade_rechecked_count}` [22] excluded outputs whose
values moved; all stay excluded at the values they were decided on.

[Replace patch B's `[RELEASE AUTHOR]` placeholders with the upstream PR numbers from the
sidecar: #9928 AZ, #10020 OH, #9946 CO, #9948 NY, #9801 WI 064, #9633 VA 039 state, and the
eight 2026-10-09 fixes as they land.]

## 3. Line 1091 (review finding 9 and the judges)

- "each is an output that a sweep of every reference ... moved on policyengine-us
  {previous} or ... on {september}" becomes scoped to the earlier waves, plus: "The
  2026-10-06 records come from the reference adversary and the Louisiana audit, and the
  Indiana county records from the `{r.last_engine_upgrade.date}` move, computed on
  `{r.last_engine_upgrade.engine_version}`."
- The judges sentence adds the October additions: "and Claude Opus 5.5 judged the cases the
  September 22, September 29, September 30 and October 9 additions joined or a reference
  revision changed".

## 4. Accessors to add (policybench/paper_results.py)

- `ruling_date`, `ruled_exclusion_count(_word)`, `adversary_output_count(_word)`: from the
  frozen exclusion record's records with `decided_on == 2026-10-06`, split by `decision`
  (d1022, d994), including the ones the upgrade regenerated, which are no longer in the
  record but are in the sidecar's `regenerated_exclusions`.
- `engine_upgrade_*_count_word`: wording forms of the existing EngineUpgrade counts.
- Each pinned in tests/test_paper_results.py against the frozen files, with the
  2.15.17-era facts staying pinned to the 2026-09-29 revision as now.
