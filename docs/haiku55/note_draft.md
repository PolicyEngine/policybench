# Draft: release note for Claude Haiku 5.5 and the engine upgrade

DRAFT. The values in brackets are the 2.37.2 rehearsal's (results/local/rehearsal-2372);
every one becomes a `{fact}` that tests/test_notes.py recomputes from the frozen release.
Nothing here is final until the release built on the fixed policyengine-us is frozen.

Slug: `2026-10-09-claude-haiku-5-5-joins-as-the-references-move-to-policyengine-us-{ver}`
Title: "Claude Haiku 5.5 joins the board as the references move to policyengine-us {engineVersion}"

## Paragraphs

1. Claude Haiku 5.5, which Anthropic released on October 7, joined the board on
   {releaseDate}, bringing it to {nModels} [47] models. It gets {haikuExact}% [80.9] of answers
   within $1, weighted by household impact, #{haikuRank} [37] of {nModels}, and
   {haikuGain} [4.8] points more than Claude Haiku 4.5 ({haiku45Exact}% [76.2],
   #{haiku45Rank} [43]). GPT-6 Sol still leads at {solExact}% [96.5], ahead of Claude
   Opus 5.5 ({opusExact}% [95.6]) and GPT-5.6 Sol ({sol56Exact}% [94.8]).

2. At ${haikuCost} [0.0013] a household, Claude Haiku 5.5 is the cheapest of the board's
   paid rows; Claude Haiku 4.5 costs ${haiku45Cost} [0.055] and used {haikuTokenRatio:words}
   [five] times as many tokens. Unlike Claude Opus 5.5 and Claude Sonnet 5.5, its API
   accepts a forced tool call, so its row answers through the board's forced answer tool,
   which leaves Claude's extended thinking off, as Claude Opus 5's row does. Re-run with
   tool_choice: auto, which leaves the tool to the model and thinking on, it gets
   {haikuAutoExact}% [rescore after freeze] and would rank #{haikuAutoRank}.
   [Ox Alpha shows $0 because it ran in a free preview window (sensitivity/ox-alpha-2026-08.md),
   so the sentence says "the cheapest of the board's paid rows" and the test checks it on the
   frozen board, excluding only rows with zero cost.]

3. The release also moves PolicyBench's references from policyengine-us {previousEngine}
   [2.15.17] to {engineVersion} [final]. The new version fixes {fixedDefects:words}
   engine defects behind outputs PolicyBench had stopped scoring, so {regenerated:words}
   [7 on 2.37.2; more on the final engine] of those outputs return to scoring at the new
   version's values, each landing within $1 of the value its exclusion said the law
   gives: [list by program and state, from the sidecar's regenerated_exclusions]. PolicyBench
   still builds each reference from the stated facts and law published before it froze the
   references on 2026-07-03, with the same publication conventions.

4. Two rulings of October 6 apply too. PolicyBench's reference adversary flags the scored
   outputs where many models, or several of the strongest, agree on the same answer away
   from the reference, and a judge blind to the engine's derivation works each one from
   primary law. Of its {adversaryOutputs:words} [eight] outputs, four are engine defects,
   in Arizona, Ohio, Colorado and New York, which the new version fixes, so they are scored
   again at its values. The other four are the federal and state income tax of two
   households, in Pennsylvania and Missouri, whose dependent earns $45,000 of wages and
   must file a return of their own; the output definitions do not say whether the
   household's income tax includes that return, so PolicyBench stops scoring them. The
   2026 Louisiana standard deduction behind two households' state income tax was computed
   from published price indexes, and Louisiana first published a 2026 figure on
   September 28, after the freeze, so PolicyBench stops scoring those two as well.
   [Every claim checked against reference_audit/2026-10-05-reference-adversary/README.md
   and the spec's adjudication reasoning; recheck wording against the final records.]

5. The new version also counts Indiana county income tax in local income tax, at the rate of
   the county it assigns a household whose county the prompt does not state, so PolicyBench
   stops scoring the local income tax of {indianaOutputs:words} [two] Indiana households.
   Idaho's $10 permanent building fund tax now counts in one household's state income tax,
   which rises from ${id076Before} [6,818.34] to ${id076After} [6,828.34]. Every model is now
   scored on {scoredOutputs} [1,915] of its {totalOutputs} requested outputs, and PolicyBench
   excludes {excluded} [69].

6. Together, the new references and exclusions raise every one of the {incumbents} [46]
   earlier models' exact rate, by {driftMin} [0.12] to {driftMax} [0.63] points.
   [Reorderings from effects: on 2.37.2, Grok 4.7 passes Inkling for #12; GPT-6.1 Sol
   keeps #8 over Kimi K3 by 0.004 points. Recompute on the final engine.]

## Data links

- Dashboard data release ({tag})
- Engine upgrade record: reference_audit/2026-10-09-engine-upgrade/
- Reference sidecar with every change
- Exclusion record
- Reference adversary's evidence: reference_audit/2026-10-05-reference-adversary/
- Claude Haiku 5.5 model page
- Sensitivity method: sensitivity/claude-thinking-2026-08.md

## Open checks before this ships

- Every mechanism sentence traced to code read this session or a computed value (CLAUDE.md
  "No fabricated mechanisms").
- No "X, not Y" constructions; sentence case; numbers over adjectives.
- Social copy is separate and carries no costs.
