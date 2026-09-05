---
title: Reading the paper
---

# Reading the paper

The canonical PolicyBench manuscript is the Quarto source at
[`paper/index.qmd`](https://github.com/PolicyEngine/policybench/blob/main/paper/index.qmd).
It builds against:

- `paper/snapshot/20260501/` — the dated snapshot directory with
  scenarios, reference outputs, impact summaries, frozen run-level dashboard
  exports under `runs/`, the rendered PDF/web manuscript hashes, and the
  `manifest.json` provenance index.
- `app/src/data.artifact.json` — the committed pointer to the published
  live-site payload (a GitHub release asset). The manifest pins its sha256,
  which must equal the combined source-run dashboard exports under `runs/`
  (machine-checked by tests/test_snapshot_artifacts.py).

## Rendered outputs

- PDF: [`app/public/paper/policybench.pdf`](https://policybench.org/paper/policybench.pdf)
- Web: [`app/public/paper/web/`](https://policybench.org/paper/web/)
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

- `source_run_artifacts` and `committed_snapshot_artifacts`, covering the
  source-run dashboard exports, snapshot CSV hashes, and per-run compact
  artefacts (`runs/<run_label>/`) including
  `predictions.csv.gz` with raw provider responses wherever the transport
  exposed them (blank for Claude Fable 5's batch-served rows and 64 Kimi K3
  parse failures)
- `published_dashboard_artifact` and `live_dashboard_artifact`, with the
  pinned release URL, byte count, and sha256 for each dashboard payload
- `rendered_paper_artifacts`, with the rendered PDF and web bundle hashes
- `reference_output_refresh`, with the PolicyEngine and PolicyEngine US
  versions plus the certified US populace dataset's build id, URI, and sha256
- `population_weight_artifact`, with the committed scoring-weight path and
  sha256
- `audit_annotation_artifacts`, with the row and case audit file hashes. The
  frozen annotations cover 7,840 rows whose legacy threshold score is below 1:
  7,838 of 7,838 exact-match misses and two exact hits. Another 1,324 rows have
  bounded score below 100 but were outside that selection and are not
  annotated.
- `reproducibility_notes`, covering model-alias instability and what is not
  retained locally (LiteLLM cache, since it is a generated request cache)

A third party can verify the leaderboard numbers against the committed
`reference_outputs.csv` files without rerunning the benchmark, and can rerun
the benchmark by pointing `policybench eval-no-tools-chunked` at the same
scenarios.
