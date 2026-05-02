---
title: "PolicyBench: Can AI models calculate tax and benefit outcomes?"
---

# PolicyBench: Can AI models calculate tax and benefit outcomes?

**Max Ghenis** (PolicyEngine)

## Abstract

Large language models have absorbed information about tax codes, benefit programs, and policy rules, yet translating this knowledge into quantitative household outputs remains difficult. PolicyBench is a public no-tool benchmark for selected person- and household-facing tax and benefit outputs in the US and UK. We test frontier models on sampled household scenarios evaluated under US tax year 2026 and UK fiscal year 2026-27 rules and scored against PolicyEngine reference outputs.

The benchmark focuses on a single condition: AI alone, where models must rely on their parametric knowledge to estimate policy outcomes from a household description. US scenarios are sampled from Enhanced CPS households. The public UK path uses a UK-calibrated transfer dataset. PolicyEngine generates the benchmark reference outputs for each described case.

These findings are intended to measure model capability, not tool compliance. The central question is therefore straightforward: how much household-level tax-benefit calculation ability frontier models actually have when they do not have access to external computation.

```{tableofcontents}
```
