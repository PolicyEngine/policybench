---
title: Reading the paper
---

# Reading the paper

The canonical PolicyBench manuscript is the Quarto source at
[`paper/index.qmd`](https://github.com/PolicyEngine/policybench/blob/main/paper/index.qmd).
It builds against:

- `app/src/data.json` — the frozen dashboard export with model summaries,
  program summaries, scenario predictions, prompts, and PolicyEngine runtime
  bundle metadata.
- `paper/snapshot/20260501/` — the dated snapshot directory with
  scenarios, reference outputs, impact summaries, run-level artefacts under
  `runs/`, the rendered PDF/web manuscript hashes, and the
  `manifest.json` provenance index.

## Rendered outputs

- PDF: [`app/public/paper/policybench.pdf`](https://policybench.org/paper/policybench.pdf)
- Web: [`app/public/paper/web/`](https://policybench.org/paper/)
- Both rendered artefacts are sha256-pinned in
  `paper/snapshot/20260501/manifest.json` under `rendered_paper_artifacts`.

## What to cite

For methodology, scope, response contract, scoring rule, and limitations, cite
[`paper/index.qmd`](https://github.com/PolicyEngine/policybench/blob/main/paper/index.qmd)
at the snapshot date. The `docs/` site does not duplicate the manuscript
prose; it only carries the operational runbook ([`results.md`](results.md))
and the normative benchmark card
([`benchmark_card.md`](benchmark_card.md)).

## Reproducibility checklist

The manifest at `paper/snapshot/20260501/manifest.json` lists:

- the dashboard export and snapshot CSV hashes
- the per-run compact artefacts (`runs/<run_label>/`) including
  `predictions.csv.gz` with raw provider responses
- the rendered PDF and web bundle hashes
- the UK calibrated transfer dataset's pinned commit, public URL, and sha256
- reproducibility notes covering model-alias instability and what is not
  retained locally (LiteLLM cache, since it is a generated request cache)

A third party can verify the leaderboard numbers against the committed
`ground_truth.csv` files without rerunning the benchmark, and can rerun the
benchmark by pointing `policybench eval-no-tools-chunked` at the same
scenarios.
