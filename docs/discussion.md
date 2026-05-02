---
title: Discussion
---

# Discussion

## Where models fail

The AI-alone results reveal systematic patterns in model errors that reflect the underlying structure of tax and benefit programs.

**Multi-step tax quantities are consistently difficult.** In the current
snapshot, US federal income tax before refundable credits, state income tax
before refundable credits, payroll tax, and UK Income Tax and National
Insurance are among the lowest-scoring outputs. These quantities require the
model to identify the right income concept, deduction or credit sequence,
threshold, rate schedule, and jurisdiction-specific rule before doing the final
arithmetic.

**Positive benefit cases remain hard even when zero cases are easy.** Sparse
programs can look high-performing because many households have a true value of
zero. Positive SNAP, Universal Credit, Pension Credit, PIP, and similar cases
are more informative: models often know that a program exists, but miss the
income test, asset treatment, award level, or taper when the reference value is
positive.

**Phase-outs and cliffs create discontinuities.** The EITC, CTC, ACA Premium
Tax Credit, Universal Credit, and many state tax provisions have thresholds,
phase-ins, phase-outs, and eligibility cliffs. Models tend to produce smooth
approximations where the true function is piecewise and sometimes
discontinuous.

**Jurisdiction-specific rules add complexity.** State and local income tax in
the US and UK fiscal-year rules require jurisdiction-specific thresholds,
rates, and credit interactions. The benchmark therefore tests more than generic
tax bracket recall; it tests whether models can apply the right rules to a
concrete household.

## What this benchmark is meant to measure

PolicyBench is now scoped to the no-tools condition because that is the capability question of interest: whether frontier models can actually compute household-level tax-benefit outcomes from a description alone. Tool use may still matter in production systems, but it answers a different question. A benchmark centered on tool access tends to measure interface compliance and delegation quality more than unaided policy-calculation ability.

That distinction matters because the failure modes in the AI-alone condition are substantive. Models are not just formatting answers badly or missing one step in a schema. They are making large quantitative mistakes on thresholds, phase-outs, nonlinear interactions, and state-specific rules. Those are the core computational limits the benchmark is intended to expose.

## Implications for AI-assisted policy analysis

These results suggest a clear architecture for AI systems that provide policy analysis:

1. **Computation should be delegated to maintained tools.** LLMs should not be trusted to perform tax and benefit calculations from memory, regardless of their general capability. Microsimulation engines like PolicyEngine exist to handle this complexity and encode statutory rules in auditable software.

2. **Models add value as interfaces, not calculators.** The appropriate role for an LLM in policy analysis is to translate natural language questions into structured API calls, interpret results for non-technical users, and synthesize findings across multiple scenarios. These are tasks where models excel.

3. **Benchmarks should distinguish capability from system design.** A no-tools benchmark is useful for measuring raw model capability. A separate system benchmark can measure how well models use tools in practice. Conflating the two makes the headline harder to interpret.

4. **Household realism matters.** Sampling benchmark cases from realistic microdata is important because many policy mistakes come from interactions between filing status, age structure, income mix, and household composition. Benchmarks built from independently sampled attributes risk testing unrealistic combinations instead of real policy difficulty.

## Limitations

Several limitations qualify these findings:

**Scope of outputs.** PolicyBench evaluates selected tax and benefit outputs, not the full tax-benefit system. The headline scope focuses on person- or household-facing net-income components and selected coverage flags. Coverage flags are binary in the main ranking; PolicyEngine value proxies are used only in the secondary household-equal impact score. PolicyEngine variables may be native to lower-level entities, but headline outputs are either expanded to the people shown in the prompt or aggregated to the household before scoring. The US federal income-tax output is represented by tax before refundable credits and refundable credits; net federal income tax excluding ACA PTC can be derived from those two outputs. Intermediate tax bases are excluded. Model performance may differ on outputs not included in the benchmark.

**Household complexity.** Sampling from the Enhanced CPS preserves observed household structure, but the benchmark still uses a filtered subset of households so that cases remain promptable and interpretable. More complex multi-tax-unit households, itemized-deduction-heavy filers, and unusual household structures remain underrepresented.

**Single policy period.** Evaluations use US tax year 2026 and UK fiscal year
2026-27. Model performance may differ for historical years, where training data
is more abundant, or future years, where models must extrapolate from known
rules.

**Open public set.** The site exposes the current household prompts, model
outputs, explanations, and PolicyEngine reference outputs for transparency.
That makes the public leaderboard an open-set benchmark, not a protected
held-out test set.

**Prompt sensitivity.** We use a single prompt template per condition. Model performance may be sensitive to prompt phrasing, particularly in the AI-alone condition where chain-of-thought prompting or structured reasoning might improve accuracy.

**Model versions.** AI model capabilities change rapidly. Results for specific model versions may not generalize to future releases, though the qualitative finding --- that models struggle with precise computation without tools --- is likely to persist.

## Future work

Several extensions of PolicyBench are planned or in progress:

**Additional country tracks.** PolicyEngine supports Canadian and other tax-benefit systems. Extending PolicyBench beyond the current US and UK tracks would test whether models' computational limitations are specific to these systems or are more general.

**Specialized policy models.** PolicyBench provides a natural evaluation framework for testing whether future domain-adapted policy models improve unaided performance on tax and benefit calculation, not just general-language reasoning.

**Dynamic scenarios.** Current scenarios are static household snapshots. Future versions could test models on reform scenarios (e.g., "What would this household's SNAP benefits be if the maximum allotment increased by 10%?"), which require understanding both baseline rules and the proposed change.

**Multi-turn evaluation.** Real-world policy analysis often involves iterative questioning: a user asks about one variable, then follows up about related variables or alternative scenarios. Evaluating models in multi-turn settings would better reflect actual use cases.
