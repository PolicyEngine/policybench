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

The benchmark is intentionally scoped to direct no-tools capability. It is
designed to measure whether models can estimate household-level PolicyEngine
reference outputs from the information in the prompt, not whether they can
comply with an external calculator interface.

## Models tested

The default benchmark model registry tracks the currently published no-tools
leaderboard. Published paper claims should identify the exact dated result
export, model set, household sample, output set, and policy period used for the
manuscript.

Models are prompted to return numeric outputs plus one short non-empty
explanation per output under a structured response contract. Scores use the
numeric outputs; explanations are retained for audit and error analysis.
The same country-level prompt template is used across models. Models receive
the same household facts and requested outputs, no tools or web access, and the
prompt states that unlisted numeric inputs are zero while unlisted boolean or
status facts are false.

## Programs evaluated

Benchmark outputs are specified in `policybench/benchmark_specs.json`. The
active benchmark defaults to `headline`, which focuses the ranking on
person- or household-facing outputs that contribute to household net income.
PolicyEngine variables may be native to lower-level entities; the benchmark
contract either expands them to the people shown in the prompt or aggregates
them to the household before scoring. Intermediate tax bases and payroll
subcomponents are excluded from the public ranking. Coverage eligibility
outputs are booleans and are weighted by PolicyEngine dollar-value proxies in
the household-equal impact score.

The US headline scope evaluates direct net-income components, health-related
support, and coverage flags:

| Variable | Description | Category |
|:---------|:-----------|:---------|
| `federal_income_tax_before_refundable_credits` | Federal income tax after nonrefundable credits and before refundable credits | Federal tax |
| `federal_refundable_credits` | Federal refundable income tax credits | Federal tax |
| `payroll_tax` | Payroll tax on wages | Payroll tax |
| `self_employment_tax` | Self-employment tax | Payroll tax |
| `state_income_tax_before_refundable_credits` | State income tax before refundable credits | State tax |
| `state_refundable_credits` | State refundable income tax credits | State tax |
| `local_income_tax` | Local income tax liability | Local tax |
| `snap` | SNAP (food stamps) annual benefit | Benefits |
| `ssi` | Supplemental Security Income | Benefits |
| `tanf` | TANF benefit amount | Benefits |
| `premium_tax_credit` | ACA Marketplace premium assistance | Health |
| `person_wic_eligible` | Expanded to one WIC eligibility flag per person in the household | Coverage |
| `person_medicaid_eligible` | Expanded to one Medicaid eligibility flag per person in the household | Coverage |
| `person_chip_eligible` | Expanded to one CHIP eligibility flag per person in the household | Coverage |
| `person_medicare_eligible` | Expanded to one Medicare eligibility flag per person in the household | Coverage |
| `person_head_start_eligible` | Expanded to one Head Start eligibility flag per person in the household | Coverage |
| `person_early_head_start_eligible` | Expanded to one Early Head Start eligibility flag per person in the household | Coverage |
| `free_school_meals_eligible` | Household qualifies for free school meals | Coverage |
| `reduced_price_school_meals_eligible` | Household qualifies for reduced-price school meals | Coverage |

The UK headline scope evaluates:

| Variable | Description | Category |
|:---------|:-----------|:---------|
| `income_tax` | Income Tax liability | Tax |
| `national_insurance` | National Insurance contributions | Tax |
| `capital_gains_tax` | Capital Gains Tax liability | Tax |
| `child_benefit` | Child Benefit amount before the High Income Child Benefit Charge | Benefits |
| `universal_credit` | Universal Credit amount | Benefits |
| `pension_credit` | Pension Credit amount | Benefits |
| `pip` | Personal Independence Payment amount | Benefits |

The US federal tax decomposition is intentionally compact: final federal income
tax excluding ACA PTC should equal tax before refundable credits minus federal
refundable credits. ACA Premium Tax Credit is kept as a separate health-related
output because it depends on Marketplace premium assistance rather than only
income-tax credit sequencing. Binary coverage outputs are scored with
classification accuracy rather than dollar error metrics.

The benchmark excludes intermediate tax bases, payroll subcomponents, and
outputs that mainly require unavailable household history, restricted local
market data, or program take-up assignment rather than rule calculation. ACA
Premium Tax Credit is retained as a deliberate health-support output; when
local benchmark premiums are not listed, the model must estimate them from the
household facts. WIC is requested as person-level eligibility, not as a dollar
amount; WIC dollar values are used only as impact-weight proxies for coverage
flags.

## Household scenarios

US scenarios are sampled from Enhanced CPS households with a fixed random seed
for reproducibility. To keep household descriptions faithful and tractable, we
restrict sampled cases to households with a single federal tax unit, a single
family, and a single benefit-calculation unit. Adult dependents remain in scope
when they satisfy those restrictions. We carry through ages, household roles,
employment patterns, and selected non-wage income sources, but do not provide
filing status in the prompt.

The public UK path samples from the UK-calibrated transfer dataset. The current
UK benchmark keeps households with one benefit unit and one or two adults. The
prompt states that all listed people are in the same UK benefit unit; if two
adults are listed, they are the couple in that benefit unit. This keeps
Universal Credit, Pension Credit, Child Benefit, Income Tax, and National
Insurance prompts aligned with the household structure used by PolicyEngine-UK.

US scenarios are converted to PolicyEngine-US household JSON objects specifying
people, tax units, SPM units, families, and households. Tax-unit role flags are
included in the PolicyEngine input so the reference calculation can infer filing
status from the same household structure described to the model. UK scenarios
are converted to PolicyEngine-UK inputs using the public transfer dataset's
person and benefit-unit structure, with prompts limited to one household group
for tax and benefit calculations.

## Reference-output computation

Reference output values are computed using PolicyEngine-US and PolicyEngine-UK.
For each sampled scenario and selected output, we run a PolicyEngine simulation
for US tax year 2026 or UK fiscal year 2026-27 and record the computed value.

PolicyEngine is the benchmark reference source. Its calculations implement
policy rules and are maintained as open-source microsimulation models. Any
discrepancy between a model's output and the PolicyEngine value is treated as a
model error relative to the benchmark reference output, not as a claim about
administrative records.

## Evaluation metrics

The public leaderboard uses a bounded `0-100` score. For amount outputs, each
prediction receives credit for exact match and for falling within 1%, 5%, and
10% of the PolicyEngine reference value; the output score averages those hit
rates. For binary outputs, the score is classification accuracy after numeric
predictions are rounded to `0` or `1`. Person-level coverage rows are averaged
within their program group before country-level aggregation. Missing or
unparseable answers count as misses through the coverage multiplier. The
country score gives each output group equal weight, and the global score gives
the US and UK equal weight for models run in both countries.

We also report diagnostic error metrics. **Mean absolute error (MAE)** measures
the average magnitude of errors in currency terms. For a set of $n$ predictions
$\hat{y}_i$ against reference values $y_i$:

$$\text{MAE} = \frac{1}{n}\sum_{i=1}^{n}|\hat{y}_i - y_i|$$

**Mean absolute percentage error (MAPE)** measures relative error, excluding
cases where the reference value is zero:

$$\text{MAPE} = \frac{1}{|S|}\sum_{i \in S}\left|\frac{\hat{y}_i - y_i}{y_i}\right|, \quad S = \{i : y_i \neq 0\}$$

**Within-10% accuracy** measures the fraction of predictions that fall within
10% of the reference value. For zero reference values, we instead check whether
the prediction is within `$1` of zero:

$$\text{Acc}_{10\%} = \frac{1}{n}\sum_{i=1}^{n}\mathbf{1}\left[(y_i = 0 \land |\hat{y}_i| \leq 1) \lor (y_i \neq 0 \land \frac{|\hat{y}_i - y_i|}{|y_i|} \leq 0.10)\right]$$

For binary variables, we report classification accuracy.

Sensitivity checks should be reported alongside paper claims, including
amount-only, binary-only, positive-reference-case, zero-reference-case,
country-only, and household-equal impact-score rankings when the relevant
artifacts are available.
