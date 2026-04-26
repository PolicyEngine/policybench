---
title: Methodology
---

# Methodology

## Experimental design

PolicyBench evaluates frontier AI models on a no-tools task: given a fully
specified household and a named set of policy variables, produce the requested
outputs without tools.

- **AI alone.** The model receives a natural language description of the
  household and must estimate the requested outputs using only its parametric
  knowledge. No tools, APIs, or reference materials are provided.

The benchmark is intentionally scoped to direct no-tools capability. It is designed to measure whether models can actually carry out household-level policy calculations from the information in the prompt, not whether they can comply with a tool-calling interface.

## Models tested

The default benchmark model registry tracks the currently published no-tools
leaderboard. Frozen paper claims should be read from
`results/paper_exports/benchmark_snapshot.json`, which records the exact run
directories and shared model set used for manuscript claims.

Models are prompted to return only numeric outputs under a structured response
contract.

## Programs evaluated

Benchmark outputs are specified in `policybench/benchmark_specs.json`. The
published `v1` snapshot is retained for reproducibility. New runs default to
`v2_headline`, which focuses the ranking on person- or household-facing outputs
that contribute to household net income. PolicyEngine variables may be native
to lower-level entities; the benchmark contract either expands them to the
people shown in the prompt or aggregates them to the household before scoring.
Intermediate tax bases move to supplementary diagnostics. Coverage eligibility
outputs are booleans and are weighted by PolicyEngine dollar-value proxies in
the household-equal impact score.

The rebuilt US headline scope evaluates direct net-income components and
coverage flags:

| Variable | Description | Category |
|:---------|:-----------|:---------|
| `income_tax` | Federal income tax after refundable credits | Federal tax |
| `payroll_tax` | Payroll tax on wages | Payroll tax |
| `self_employment_tax` | Self-employment tax | Payroll tax |
| `household_state_income_tax` | State income tax liability | State tax |
| `local_income_tax` | Local income tax liability | Local tax |
| `snap` | SNAP (food stamps) annual benefit | Benefits |
| `ssi` | Supplemental Security Income | Benefits |
| `tanf` | TANF benefit amount | Benefits |
| `wic` | WIC benefit amount | Benefits |
| `person_medicaid_eligible` | Expanded to one Medicaid eligibility flag per person in the household | Coverage |
| `person_chip_eligible` | Expanded to one CHIP eligibility flag per person in the household | Coverage |
| `person_medicare_eligible` | Expanded to one Medicare eligibility flag per person in the household | Coverage |
| `person_head_start_eligible` | Expanded to one Head Start eligibility flag per person in the household | Coverage |
| `person_early_head_start_eligible` | Expanded to one Early Head Start eligibility flag per person in the household | Coverage |
| `free_school_meals_eligible` | Household qualifies for free school meals | Coverage |
| `reduced_price_school_meals_eligible` | Household qualifies for reduced-price school meals | Coverage |

The rebuilt UK headline scope evaluates:

| Variable | Description | Category |
|:---------|:-----------|:---------|
| `income_tax` | Income Tax liability | Tax |
| `national_insurance` | National Insurance contributions | Tax |
| `child_benefit` | Child Benefit amount | Benefits |
| `universal_credit` | Universal Credit amount | Benefits |
| `pension_credit` | Pension Credit amount | Benefits |
| `pip` | Personal Independence Payment amount | Benefits |

Intermediate tax bases, credit components, and payroll-tax decompositions are
kept in supplementary diagnostic sets. For example, the US supplementary set
includes AGI, pre-credit tax, EITC, CTC, refundable credits, person-level
employee Social Security and Medicare tax, and household Additional Medicare
Tax. Binary coverage outputs are scored with classification accuracy rather
than dollar error metrics.

## Household scenarios

US scenarios are sampled from Enhanced CPS households with a fixed random seed
for reproducibility. To keep household descriptions faithful and tractable, we
restrict sampled cases to households with a single tax unit, a single SPM unit,
and a single family, then carry through observed filing status, ages, employment
patterns, and selected non-wage income sources. The public UK path samples from
the UK-calibrated transfer dataset.

Each scenario is converted to a PolicyEngine-US household JSON object specifying people, tax units, SPM units, families, and households. Filing status is encoded directly in the tax unit payload so that the benchmark label matches the described case.

## Reference-output computation

Reference output values are computed using PolicyEngine-US and PolicyEngine-UK.
For each sampled scenario and selected output, we run a PolicyEngine simulation
for tax year 2025 and record the computed value.

PolicyEngine is the benchmark reference source. Its calculations implement
policy rules and are maintained as open-source microsimulation models. Any
discrepancy between a model's output and the PolicyEngine value is treated as a
model error relative to the benchmark reference output, not as a claim about
administrative ground truth.

## Evaluation metrics

We use three primary metrics, applied differently depending on the variable type:

**Mean absolute error (MAE)** measures the average magnitude of errors in dollar terms. For a set of $n$ predictions $\hat{y}_i$ against reference values $y_i$:

$$\text{MAE} = \frac{1}{n}\sum_{i=1}^{n}|\hat{y}_i - y_i|$$

**Mean absolute percentage error (MAPE)** measures relative error, excluding cases where the reference value is zero (where percentage error is undefined):

$$\text{MAPE} = \frac{1}{|S|}\sum_{i \in S}\left|\frac{\hat{y}_i - y_i}{y_i}\right|, \quad S = \{i : y_i \neq 0\}$$

**Within-10% accuracy** measures the fraction of predictions that fall within 10% of the reference value. For zero reference values, we instead check whether the prediction is within $1 of zero:

$$\text{Acc}_{10\%} = \frac{1}{n}\sum_{i=1}^{n}\mathbf{1}\left[\frac{|\hat{y}_i - y_i|}{|y_i|} \leq 0.10\right]$$

For household-boolean diagnostic variables, we report classification accuracy.
