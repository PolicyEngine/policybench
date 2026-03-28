---
title: Introduction
---

# Introduction

## The promise and peril of AI for policy analysis

Artificial intelligence is increasingly invoked as a tool for public policy analysis. Large language models (LLMs) can summarize legislation, explain eligibility rules, and draft policy memos with impressive fluency. Policymakers, journalists, and researchers have begun using these models to answer questions about how tax and benefit systems affect specific households --- questions like "How much would this family receive in SNAP benefits?" or "What is the marginal tax rate for a single parent earning $40,000 in California?"

These questions have precise, deterministic answers. The US tax code and benefit programs define exact formulas, phase-out schedules, income thresholds, and interaction effects that together determine a household's tax liability, credit amounts, and benefit eligibility. A correct answer requires not just knowledge of individual program rules but the ability to execute multi-step calculations that account for interactions across programs, state-specific provisions, and household-specific circumstances.

LLMs are trained on tax law, IRS publications, benefit program documentation, and policy analyses. They can often describe the rules governing a program in considerable detail. But describing rules and computing outcomes from those rules are fundamentally different tasks. The question motivating this paper is whether frontier AI models can bridge that gap --- whether their parametric knowledge of policy rules translates into accurate quantitative outputs for specific household scenarios.

## Why precision matters

Policy analysis is a domain where approximate answers can be worse than no answer at all. Consider a family evaluating whether to accept a raise that might push them above a benefit cliff, a tax preparer estimating a client's refundable credits, or a researcher modeling the distributional effects of a proposed reform. In each case, errors of even a few hundred dollars can lead to materially wrong conclusions.

The stakes are compounded by the complexity of the US tax-and-benefit system. Federal income tax alone involves multiple filing statuses, bracket structures, deductions, exemptions, and credits --- each with its own phase-in and phase-out schedules. Layered on top are state income taxes (with their own brackets and rules), means-tested benefits like SNAP and SSI (with asset tests, income disregards, and categorical eligibility rules), and tax credits like the EITC and CTC (with earned income requirements, child age limits, and investment income thresholds). These programs interact in ways that create effective marginal tax rates that are discontinuous, non-monotonic, and difficult to compute even for domain experts.

Microsimulation models exist precisely to handle this complexity. Tools like PolicyEngine-US encode the full logic of each program and compute exact outcomes for arbitrary household configurations. The question is whether AI models, armed only with their training data, can approximate these computations well enough to be useful.

## Prior work

Benchmarking AI models on quantitative reasoning tasks is a well-established area. Mathematical reasoning benchmarks like GSM8K {cite}`cobbe2021gsm8k` and MATH {cite}`hendrycks2021math` evaluate models on multi-step arithmetic and algebraic problems. Domain-specific benchmarks exist for medical reasoning, legal analysis, and financial calculations.

However, benchmarks for tax and benefit computation are scarce. TaxBench evaluated LLMs on tax preparation questions but focused on qualitative understanding of tax rules rather than precise numerical computation for specific households. No prior benchmark, to our knowledge, has systematically evaluated frontier models on their ability to compute exact tax liabilities, credit amounts, and benefit levels for diverse household scenarios across multiple programs.

PolicyBench fills this gap. It provides a rigorous, reproducible benchmark that isolates the computational challenge: given a fully specified household and a specific policy variable, can the model produce the correct numerical answer without external computation?

## This paper's contributions

This paper makes three contributions:

1. **A new benchmark for AI-assisted policy analysis.** PolicyBench defines 100 household scenarios by sampling realistic cases from the Enhanced CPS and encoding them faithfully in PolicyEngine-US. For each scenario, we evaluate 10 tax-and-benefit variables, producing 1,000 ground-truth values. This benchmark is open-source and extensible to additional countries and programs.

2. **An empirical evaluation of frontier model capabilities.** We test Claude Opus 4.6, Claude Sonnet 4.6, GPT-5.4, and Gemini 3.1 Pro Preview in a no-tools setting. Our results quantify how much household-level policy calculation frontier models can actually do from parametric knowledge alone.

3. **Evidence about the limits of unaided policy calculation.** We show where frontier models systematically fail on thresholds, phase-outs, state variation, and program interactions, and provide a benchmark that can track whether future model generations close that gap.
