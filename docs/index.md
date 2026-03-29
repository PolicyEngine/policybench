---
title: "PolicyBench: Can AI models calculate tax and benefit outcomes?"
---

# PolicyBench: Can AI models calculate tax and benefit outcomes?

**Max Ghenis** (PolicyEngine)

## Abstract

Large language models have absorbed vast quantities of information about tax codes, benefit programs, and policy rules, yet their ability to translate this knowledge into precise quantitative outputs remains untested. PolicyBench is a benchmark that evaluates whether frontier AI models can accurately calculate US tax and benefit outcomes for specific households without tools. We test frontier models across 13 federal and state tax-and-benefit programs for 100 benchmark scenarios sampled from real households in the Enhanced CPS and evaluated under 2025 policy rules.

The benchmark focuses on a single condition: AI alone, where models must rely on their parametric knowledge to estimate policy outcomes from a household description. Sampling scenarios from the Enhanced CPS improves realism by preserving observed combinations of ages, filing statuses, income sources, and family structures, while faithful PolicyEngine household encoding ensures that benchmark labels match the described case.

These findings are intended to measure model capability, not tool compliance. The central question is therefore straightforward: how much household-level tax-benefit calculation ability frontier models actually have when they do not have access to external computation.

```{tableofcontents}
```
