---
title: Methodology
---

# Methodology

## Experimental design

PolicyBench evaluates frontier AI models on a single task: given a fully specified household and a named policy variable, produce the correct numerical value without tools.

- **AI alone.** The model receives a natural language description of the household and must estimate the requested value using only its parametric knowledge. No tools, APIs, or reference materials are provided.

The benchmark is intentionally scoped to direct no-tools capability. It is designed to measure whether models can actually carry out household-level policy calculations from the information in the prompt, not whether they can comply with a tool-calling interface.

## Models tested

We evaluate four frontier models from three providers, using the latest provider-published versions available on March 25, 2026:

| Model | Provider | Model ID |
|:------|:---------|:---------|
| Claude Opus 4.6 | Anthropic | `claude-opus-4-6` |
| Claude Sonnet 4.6 | Anthropic | `claude-sonnet-4-6` |
| GPT-5.4 | OpenAI | `gpt-5.4` |
| Gemini 3.1 Pro Preview | Google | `gemini-3.1-pro-preview` |

Models are prompted to return only a single numeric value, with explicit instructions to avoid dollar signs, commas, or explanatory text.

## Programs evaluated

We evaluate 10 PolicyEngine-US variables spanning federal taxes, tax credits, means-tested benefits, and state taxes:

| Variable | Description | Category |
|:---------|:-----------|:---------|
| `income_tax` | Federal income tax liability | Federal tax |
| `income_tax_before_refundable_credits` | Federal tax before refundable credits | Federal tax |
| `eitc` | Earned Income Tax Credit | Credits |
| `ctc` | Child Tax Credit | Credits |
| `income_tax_refundable_credits` | Total refundable credits | Credits |
| `snap` | SNAP (food stamps) annual benefit | Benefits |
| `ssi` | Supplemental Security Income | Benefits |
| `free_school_meals` | Free school meal eligibility | Benefits |
| `is_medicaid_eligible` | Medicaid eligibility | Benefits |
| `household_state_income_tax` | State income tax liability | State tax |

These variables were chosen to span the major components of the US tax-and-benefit system and to test different types of computational challenges. Federal and state income tax require bracket calculations and interactions with deductions and exemptions. Tax credits involve phase-in and phase-out schedules that depend on earned income, number of children, and filing status. Means-tested benefits (SNAP, SSI) involve income and categorical eligibility tests, benefit reduction rates, and state-specific maximum allotments.

Binary variables (Medicaid eligibility, free school meals) are evaluated using classification accuracy rather than error metrics.

## Household scenarios

We generate 100 household scenarios by sampling real households from the Enhanced CPS with a fixed random seed for reproducibility. To keep the benchmark household descriptions faithful and tractable, we restrict the sampled cases to households with a single tax unit, a single SPM unit, and a single family, then carry through their observed filing status, ages, employment patterns, and selected non-wage income sources. This preserves realistic joint distributions while avoiding synthetic combinations that never occur in the data.

Each scenario is converted to a PolicyEngine-US household JSON object specifying people, tax units, SPM units, families, and households. Filing status is encoded directly in the tax unit payload so that the benchmark label matches the described case.

## Ground truth computation

Ground truth values are computed using PolicyEngine-US, an open-source microsimulation model that encodes federal and state tax law, benefit program rules, and their interactions for all 50 US states and DC. For each of the 100 scenarios and 10 variables, we run a PolicyEngine simulation for tax year 2025 and record the computed value. This produces 1,000 ground-truth data points.

PolicyEngine-US is the authoritative source: its calculations implement the actual statutory rules and have been validated against official tax calculators, benefit program documentation, and expert review. Any discrepancy between a model's output and the PolicyEngine value is treated as a model error, not a ground truth error.

## Evaluation metrics

We use three primary metrics, applied differently depending on the variable type:

**Mean absolute error (MAE)** measures the average magnitude of errors in dollar terms. For a set of $n$ predictions $\hat{y}_i$ against ground truth values $y_i$:

$$\text{MAE} = \frac{1}{n}\sum_{i=1}^{n}|\hat{y}_i - y_i|$$

**Mean absolute percentage error (MAPE)** measures relative error, excluding cases where the ground truth is zero (where percentage error is undefined):

$$\text{MAPE} = \frac{1}{|S|}\sum_{i \in S}\left|\frac{\hat{y}_i - y_i}{y_i}\right|, \quad S = \{i : y_i \neq 0\}$$

**Within-10% accuracy** measures the fraction of predictions that fall within 10% of the ground truth value. For zero ground truth values, we instead check whether the prediction is within $1 of zero:

$$\text{Acc}_{10\%} = \frac{1}{n}\sum_{i=1}^{n}\mathbf{1}\left[\frac{|\hat{y}_i - y_i|}{|y_i|} \leq 0.10\right]$$

For binary variables (Medicaid eligibility, free school meals), we report classification accuracy.
