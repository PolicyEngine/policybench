# Source lines relied on

The README makes several statements about what the engine and the data builders do. Each rests on the lines below, read on 2026-10-10. Paths under `policyengine_us/` are in the policyengine-us 2.38.6 wheel that `uv.lock` pins; the two data builders were read on their main branches at the commits given.

## What sets "is a surviving spouse"

policyengine-us-data, main `42ed5d45c56df80d754fbe24cce21cfeb8d05cbe`, `policyengine_us_data/datasets/cps/cps.py` line 1212:

```python
    cps["is_surviving_spouse"] = person.A_MARITL == 4
```

Microcosm, main `aca40a692a16ff7d0b2d2b9a7a1571341762f082`, `packages/microcosm-build/src/microcosm/build/us_runtime/relationship_inputs.py` line 181:

```python
    result["is_surviving_spouse"] = marital_status == 4
```

`marital_status` there is the survey's `A_MARITL` (lines 157 to 161 of the same file).

## How the engine decides the filing status

`policyengine_us/variables/household/demographic/tax_unit/surviving_spouse_eligible.py`, the whole formula:

```python
        person = tax_unit.members
        is_head = person("is_tax_unit_head", period)
        is_surviving_spouse = person("is_surviving_spouse", period)
        surviving_spouse_head = tax_unit.any(is_head & is_surviving_spouse)
        has_child_dependents = tax_unit("tax_unit_child_dependents", period) > 0
        married = tax_unit("tax_unit_married", period)
        return surviving_spouse_head & has_child_dependents & ~married
```

The formula requires a child dependent. It reads nothing about when the spouse died, which is PolicyEngine/policyengine-us#10059.

`filing_status.py` in the same folder selects, in order, joint, surviving spouse, head of household and separate, with single as the default.

## What "estate income" means to the engine

`policyengine_us/variables/household/income/person/estate/estate_income.py`, the variable's documentation:

> Net income or loss from an interest in an estate or trust reported on Schedule E Part III and carried to Schedule 1 line 5 (PUF E26390 less E26400). This covers Schedule K-1 (Form 1041) boxes 5 through 8; interest, dividends, and capital gains a beneficiary receives from an estate or trust belong in those separate inputs. Positive amounts enter federal gross income under IRC § 61(a)(14); losses are deducted through loss_ald.

## What "employer sponsored insurance premiums" means to the engine

`policyengine_us/variables/input/employer_sponsored_insurance_premiums.py`, the variable's documentation:

> Annual employer-paid health insurance premiums. CBO treats this as part of household market income.

## Ohio's employer-plan test

`policyengine_us/variables/gov/states/oh/tax/income/deductions/medical_exepenses/oh_employer_subsidized_health_plan_eligible.py`, from the formula:

```python
        # Enrolled in, or offered, employer coverage.
        has_employer_coverage = person("has_esi", period) | person(
            "offered_aca_disqualifying_esi", period
        )
        ...
        employer_pays = (contribution == status.SOME) | (contribution == status.ALL)
        ...
        return tax_unit.any(head_or_spouse & (has_employer_coverage | employer_pays))
```

Having or being offered employer coverage is enough, whether or not the employer pays. The statute's test is that the employer pays some of the plan's cost.

## Ohio's fixed amount

`policyengine_us/parameters/gov/states/oh/tax/income/rates.yaml`, the first bracket's rate, line 14:

```yaml
      2026-01-01: 0.0127448
```

The second bracket starts at 26,050, so the tax on the first bracket is 0.0127448 × 26,050 = 332.00204.

## Ohio's retirement income credit

`policyengine_us/variables/gov/states/oh/tax/income/credits/retirement_income/pension_based/oh_pension_based_retirement_income_credit.py`, the comment in the formula:

```python
        # Under R.C. 5747.055(A)(1), distributions must be received on
        # account of retirement; modeled without checking retirement event condition.
```
