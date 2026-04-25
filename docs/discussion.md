---
title: Discussion
---

# Discussion

## Where models fail

The AI-alone results reveal systematic patterns in model errors that reflect the underlying structure of tax and benefit programs.

**Means-tested benefits are hardest.** Programs like SNAP and SSI involve multi-step eligibility determinations: gross income tests, net income tests, asset limits, categorical eligibility provisions, and benefit reduction rates that differ by household size and state. Models must not only know these rules but execute them in the correct order, applying the right thresholds for the specific household configuration. Even models that can recite SNAP eligibility rules struggle to correctly determine whether a family of four in California with $25,000 in income qualifies, and if so, for how much.

**Phase-outs and cliffs create discontinuities.** The EITC, CTC, and many state tax provisions have phase-in and phase-out schedules that create sharp nonlinearities in the relationship between income and the computed value. Models tend to produce smooth approximations where the true function is discontinuous. For example, a model might estimate a positive EITC for a household whose income is just above the phase-out threshold, producing an error of several thousand dollars at a single dollar of income difference.

**State-level variation adds complexity.** State income tax calculations require knowledge of state-specific bracket structures, deductions, credits, and their interactions with federal provisions. Models must effectively maintain 50 separate tax code implementations in their parameters. Errors are systematically larger for states with complex tax systems (California, New York) than for states with no income tax (Texas, Florida, Washington).

**Income tax estimates are closer but still unreliable.** Federal income tax is the program where models perform best in the AI-alone condition, likely because tax bracket calculations are well-represented in training data and involve relatively straightforward arithmetic. However, even here, models make errors on the order of thousands of dollars for complex returns, particularly those involving interactions between the standard deduction, credits, and the alternative minimum tax.

## What this benchmark is meant to measure

PolicyBench is now scoped to the no-tools condition because that is the capability question of interest: whether frontier models can actually compute household-level tax-benefit outcomes from a description alone. Tool use may still matter in production systems, but it answers a different question. A benchmark centered on tool access tends to measure interface compliance and delegation quality more than unaided policy-calculation ability.

That distinction matters because the failure modes in the AI-alone condition are substantive. Models are not just formatting answers badly or missing one step in a schema. They are making large quantitative mistakes on thresholds, phase-outs, nonlinear interactions, and state-specific rules. Those are the core computational limits the benchmark is intended to expose.

## Implications for AI-assisted policy analysis

These results suggest a clear architecture for AI systems that provide policy analysis:

1. **Computation should be delegated to validated tools.** LLMs should not be trusted to perform tax and benefit calculations from memory, regardless of their general capability. Microsimulation engines like PolicyEngine exist precisely to handle this complexity and have been validated against statutory rules.

2. **Models add value as interfaces, not calculators.** The appropriate role for an LLM in policy analysis is to translate natural language questions into structured API calls, interpret results for non-technical users, and synthesize findings across multiple scenarios. These are tasks where models excel.

3. **Benchmarks should distinguish capability from system design.** A no-tools benchmark is useful for measuring raw model capability. A separate system benchmark can measure how well models use tools in practice. Conflating the two makes the headline harder to interpret.

4. **Household realism matters.** Sampling benchmark cases from realistic microdata is important because many policy mistakes come from interactions between filing status, age structure, income mix, and household composition. Benchmarks built from independently sampled attributes risk testing unrealistic combinations instead of real policy difficulty.

## Limitations

Several limitations qualify these findings:

**Scope of outputs.** PolicyBench evaluates selected tax and benefit outputs, not the full tax-benefit system. The rebuilt headline scope focuses on signed household net-income components and selected coverage booleans weighted by PolicyEngine value proxies. Intermediate tax bases and credit components are retained as supplementary diagnostics. Model performance may differ on outputs not included in the benchmark.

**Household complexity.** Sampling from the Enhanced CPS improves realism substantially, but the benchmark still uses a filtered subset of households so that cases remain promptable and interpretable. More complex multi-tax-unit households, itemized-deduction-heavy filers, and unusual household structures remain underrepresented.

**Single tax year.** All evaluations use tax year 2025. Model performance may differ for historical years (where training data is more abundant) or future years (where models must extrapolate from known rules).

**Prompt sensitivity.** We use a single prompt template per condition. Model performance may be sensitive to prompt phrasing, particularly in the AI-alone condition where chain-of-thought prompting or structured reasoning might improve accuracy.

**Model versions.** AI model capabilities change rapidly. Results for specific model versions may not generalize to future releases, though the qualitative finding --- that models struggle with precise computation without tools --- is likely to persist.

## Future work

Several extensions of PolicyBench are planned or in progress:

**Additional country tracks.** PolicyEngine supports Canadian and other tax-benefit systems. Extending PolicyBench beyond the current US and UK tracks would test whether models' computational limitations are specific to these systems or are more general.

**Specialized policy models.** PolicyBench provides a natural evaluation framework for testing whether future domain-adapted policy models improve unaided performance on tax and benefit calculation, not just general-language reasoning.

**Dynamic scenarios.** Current scenarios are static household snapshots. Future versions could test models on reform scenarios (e.g., "What would this household's SNAP benefits be if the maximum allotment increased by 10%?"), which require understanding both baseline rules and the proposed change.

**Multi-turn evaluation.** Real-world policy analysis often involves iterative questioning: a user asks about one variable, then follows up about related variables or alternative scenarios. Evaluating models in multi-turn settings would better reflect actual use cases.
