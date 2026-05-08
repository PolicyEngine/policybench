---
title: PolicyBench.org improvements scope
---

# PolicyBench.org improvements scope

A scoping document for improvements to the PolicyBench dashboard at
[policybench.org](https://policybench.org). The current site is a Next.js App
Router application under `app/` rendering a single dashboard
(`app/src/App.tsx`) with five sections — model leaderboard, scenario
explorer, failure modes, program heatmap, methodology — plus a `/paper`
landing page that embeds the rendered manuscript. This document does not
change any code; it lists what would meaningfully improve the experience
for the audiences that visit the site, ranked by impact.

## Audiences

1. **Researchers** comparing model performance over time and across views.
2. **Practitioners** deciding whether to trust an LLM with a household
   tax/benefit question.
3. **Provider teams and benchmarking groups** auditing results for their
   own model.
4. **Press and policy commentators** referencing the headline number.

The site already serves audience 1 well at the leaderboard level.
Audiences 2–4 are underserved: there is no per-model deep dive, no
sensitivity-view selector, no per-scenario explanation browsing, and no
honest open-set warning beyond the paper.

## Tier 1 — high impact, ship soon

### 1.1 Open-set leakage banner and snapshot freshness indicator
**Why.** The paper now states clearly that the public leaderboard is
open-set. The site does not. A casual visitor reads the leaderboard as a
held-out evaluation. A small banner near the leaderboard header (`Sources
released publicly. Open-set leaderboard — see methodology.`) plus a
snapshot date pill (`Snapshot 2026-05-01`) close that gap.

**Where.** `app/src/components/Hero.tsx` — add an `<OpenSetBadge />` next
to the title or under the subtitle. `app/src/components/ModelLeaderboard.tsx`
— add a one-line caveat above the table.

**Effort.** Half a day.

### 1.2 Sensitivity-view selector on the leaderboard
**Why.** The paper reports eight sensitivity views (amount-only,
binary-only, positive-only, zero-only, country-only, impact-weighted, US
binary coverage). The dashboard only shows the main equal-output view.
Surfacing the same selector on the site lets visitors verify rank
stability themselves rather than taking the headline as final.

**Where.** New control in `ModelLeaderboard.tsx` (segmented control above
the table); the underlying score variants either get pre-computed and
stored in `data.json` or computed client-side from the `scenarioPredictions`
already present.

**Effort.** Two days. Pre-computation in `analysis.build_dashboard_payload`
is the cleaner path because it keeps the client small and the math
canonical.

### 1.3 Bootstrap-rank intervals next to model scores
**Why.** The paper computes household-resampling 95% intervals and
rank-ranges. The site shows a single point estimate. Rendering the rank
range (`Rank 2 (CI: 1–4)`) tempers overinterpretation of small gaps.

**Where.** `ModelLeaderboard.tsx`. Pre-compute in
`analysis.build_dashboard_payload` so the client just renders.

**Effort.** One to two days.

### 1.4 Per-model deep-dive page
**Why.** A provider team wanting to audit `gpt-5.4-mini` has no entry
point. A per-model page (`/model/[id]`) showing the model's score, top
errors, hardest variables, parse coverage, raw response examples, and a
comparison to the next-best model on each output addresses the audit use
case directly.

**Where.** New App Router route `app/src/app/model/[model]/page.tsx`
consuming the existing `scenarioPredictions` and `failureModes` data.

**Effort.** Three to four days.

## Tier 2 — meaningful impact, ship next

### 2.1 Per-output deep-dive page
**Why.** Symmetric to per-model: a researcher interested in SNAP wants
"who gets it right, who gets it wrong, on which households". Currently the
program heatmap collapses this to one cell per (variable, model).

**Where.** `app/src/app/output/[variable]/page.tsx` consuming
`programStats`, `scenarioPredictions`, and `failureModes`.

**Effort.** Two days.

### 2.2 Cross-country compare view
**Why.** When the global view is selected, models that exist in both
countries should be compared side-by-side per output where the output
exists in both (e.g., income tax). Currently the user has to switch tabs
and remember numbers.

**Where.** New section in the global view of `App.tsx`, or extend
`ModelLeaderboard` with a "show country split" toggle.

**Effort.** One to two days.

### 2.3 Cost and token usage on the leaderboard
**Why.** `predictions.csv.gz` carries `prompt_tokens`, `completion_tokens`,
`reasoning_tokens`, and `provider_reported_cost_usd`. The dashboard does
not surface any of this. Practitioners deciding whether to use a model
care about cost-per-correct-answer as much as raw accuracy.

**Where.** Aggregate per-model usage in
`analysis.build_dashboard_payload` and add a `usageStats` block to
`modelStats`. Render as a cost column in `ModelLeaderboard.tsx` with a
`$/100 outputs` framing and an opt-in toggle to switch the score axis to
score-per-dollar.

**Effort.** Two days.

### 2.4 Scenario filtering and search
**Why.** Today's scenario explorer picks a random scenario or accepts a
URL hash. There is no way to filter by state, age, income range, or
filing status. Audiences 2 and 3 want to find "households like mine" or
"the failures that matter to my product".

**Where.** Add a search/filter bar above the scenario explorer; index
scenarios on a small set of facets.

**Effort.** Two days.

### 2.5 Federal+state joint accuracy view (US)
**Why.** The paper now reports federal/state refundable credit joint
within-10% accuracy as a failure mode. The site should mirror it as a
small explainer next to the failure-mode panel: it is the cleanest
demonstration of the "marginal accuracy hides joint errors" pattern.

**Where.** `FailureModes.tsx` — add a third sub-section.

**Effort.** Half a day.

## Tier 3 — useful, ship when bandwidth allows

### 3.1 Explanation browsing
The dashboard already shows one model's explanation in a tooltip per
(scenario, variable). A "show all explanations" mode that lays out
alongside the numeric answers turns the site into a qualitative analysis
tool.

### 3.2 Citation snippet widget
A small `Cite` button in the hero that copies a BibTeX entry for the
current snapshot.

### 3.3 Programmatic data download buttons
`Download CSV / JSON` next to the leaderboard, scenario explorer, and
heatmap. The data is in `data.json` already; the buttons just expose it.

### 3.4 Snapshot history and changelog
A `/changes` page listing prior snapshots, ranking diffs, and any
methodology changes between them. Even a minimal version (table of dates
+ commit links) would help track movement over time.

### 3.5 RSS/Atom feed of leaderboard updates
For audience 1: a feed item per snapshot freeze.

### 3.6 Reasoning vs non-reasoning slice
Two of the listed Grok and Gemini variants are "reasoning" or "fast/non-
reasoning". A toggle that groups by reasoning configuration would make
the on-vs-off effect visible.

### 3.7 Mobile leaderboard polish
The leaderboard uses a wide table. On phones the eight columns get
horizontal scroll. A condensed mobile rendering (model name, score,
within-10%) plus expand-on-tap would help.

## Tier 4 — speculative or larger investments

### 4.1 Held-out protected leaderboard
The biggest credibility limitation is open-set status. A held-out
evaluation set (rotating monthly, prompts not in training corpora) would
allow a separate "Protected" rank tab. Requires policy decisions on
release cadence and a separate ingestion flow; not just a frontend
change.

### 4.2 Live evaluation against new models
A "Run my model" submission flow with a sandboxed evaluation pipeline.
Operationally complex (sandboxed inference, cost accounting, abuse
controls) but the most common ask from audience 3.

### 4.3 Country expansion previews
PolicyEngine supports Canada and Israel. A "preview" tab listing the
intended next country tracks signals roadmap to audience 1.

### 4.4 Embedded reform-scenario explorer
Today the benchmark scores baseline households. A reform-aware variant
("What does each model think a 10% SNAP boost does to this household?")
tests the marginal-effect ability the discussion section flags as future
work.

## Out-of-scope or reject

- **Branded scoreboards per provider.** The site is policy-neutral; per-
  provider marketing pages drift from that.
- **Anything that changes the canonical numbers post-snapshot.** Live
  re-runs against the same models would invalidate the manuscript
  reference. Live evaluation must target a separate held-out set.
- **Login or accounts.** The site's value is open access; auth is a
  cost without a clear win.

## Suggested first PR

Combine **1.1 (open-set banner)**, **1.2 (sensitivity selector)**, and
**1.3 (bootstrap rank intervals)** into a single PR. They share a small
amount of new pre-computed payload in `analysis.build_dashboard_payload`,
they do not require new routes, and together they shift the leaderboard
from "headline" to "honest defended ranking" — which is the change with
the largest credibility win for the smallest engineering cost.
