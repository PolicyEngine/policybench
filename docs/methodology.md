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

We evaluate 13 PolicyEngine-US variables spanning federal taxes, tax credits, means-tested benefits, and state taxes:

| Variable | Description | Category |
|:---------|:-----------|:---------|
| `adjusted_gross_income` | Federal adjusted gross income (AGI) | Federal tax |
| `income_tax_before_refundable_credits` | Federal income tax before refundable credits | Federal tax |
| `eitc` | Earned Income Tax Credit | Credits |
| `ctc` | Child Tax Credit | Credits |
| `income_tax_refundable_credits` | Total refundable federal tax credits | Credits |
| `snap` | SNAP (food stamps) annual benefit | Benefits |
| `ssi` | Supplemental Security Income | Benefits |
| `free_school_meals` | Derived household free school meal eligibility label | Benefits |
| `is_medicaid_eligible` | Whether anyone in the household is Medicaid-eligible | Benefits |
| `state_agi` | State adjusted gross income | State tax |
| `state_income_tax_before_refundable_credits` | State income tax before refundable credits | State tax |
| `state_refundable_credits` | State refundable credits | State tax |
| `household_state_income_tax` | State income tax liability | State tax |

These variables were chosen to span the major components of the US tax-and-benefit system and to test different types of computational challenges. AGI and pre-credit tax require models to combine wage and non-wage income sources and track how filing status and deductions shape tax bases. Tax credits involve phase-in and phase-out schedules that depend on earned income, number of children, and filing status. Means-tested benefits (SNAP, SSI) involve income and categorical eligibility tests, benefit reduction rates, and state-specific maximum allotments.

Binary variables are evaluated as household booleans. `free_school_meals` is a
derived household eligibility label: it is 1 if the benchmark household
qualifies for free school meals (not reduced-price meals), and 0 otherwise.
`is_medicaid_eligible` is 1 if anyone in the household is eligible for
Medicaid. These are scored with classification accuracy rather than dollar
error metrics.

## Household scenarios

We generate 100 household scenarios by sampling real households from the Enhanced CPS with a fixed random seed for reproducibility. To keep the benchmark household descriptions faithful and tractable, we restrict the sampled cases to households with a single tax unit, a single SPM unit, and a single family, then carry through their observed filing status, ages, employment patterns, and selected non-wage income sources. This preserves realistic joint distributions while avoiding synthetic combinations that never occur in the data.

Each scenario is converted to a PolicyEngine-US household JSON object specifying people, tax units, SPM units, families, and households. Filing status is encoded directly in the tax unit payload so that the benchmark label matches the described case.

## Reference-output computation

Reference output values are computed using PolicyEngine-US, an open-source
microsimulation model that encodes federal and state tax law, benefit program
rules, and their interactions for all 50 US states and DC. For each of the 100
scenarios and 13 variables, we run a PolicyEngine simulation for tax year 2025
and record the computed value. This produces 1,300 reference-output data
points.

PolicyEngine-US is the benchmark reference source. Its calculations implement
the statutory rules and have been validated against official tax calculators,
benefit program documentation, and expert review. Any discrepancy between a
model's output and the PolicyEngine value is treated as a model error relative
to the benchmark reference output.

## Evaluation metrics

We use three primary metrics, applied differently depending on the variable type:

**Mean absolute error (MAE)** measures the average magnitude of errors in dollar terms. For a set of $n$ predictions $\hat{y}_i$ against reference values $y_i$:

$$\text{MAE} = \frac{1}{n}\sum_{i=1}^{n}|\hat{y}_i - y_i|$$

**Mean absolute percentage error (MAPE)** measures relative error, excluding cases where the reference value is zero (where percentage error is undefined):

$$\text{MAPE} = \frac{1}{|S|}\sum_{i \in S}\left|\frac{\hat{y}_i - y_i}{y_i}\right|, \quad S = \{i : y_i \neq 0\}$$

**Within-10% accuracy** measures the fraction of predictions that fall within 10% of the reference value. For zero reference values, we instead check whether the prediction is within $1 of zero:

$$\text{Acc}_{10\%} = \frac{1}{n}\sum_{i=1}^{n}\mathbf{1}\left[\frac{|\hat{y}_i - y_i|}{|y_i|} \leq 0.10\right]$$

For household-boolean variables (`is_medicaid_eligible`, `free_school_meals`), we report classification accuracy.
