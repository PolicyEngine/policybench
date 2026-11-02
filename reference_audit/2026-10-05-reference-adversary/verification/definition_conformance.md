# Definition conformance

18 outputs; 17 mismatches, 9 material, touching 8 scored cells; 0 material definition-silent components; 0 conservation failures.

## Component mismatches

| Output | Rule | Component | Evidence | Material | Cells (effect on reference) | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| payroll_tax | mandatory | `co_employee_famli_contribution` | law_classification | yes | scenario_043 17.99 | 'co_employee_famli_contribution' (Colorado employee FAMLI contribution) is classified as an optional employer pass-through (C.R.S. 8-13.3-507(2), (3)(b) and (5); 7 CCR 1107-1 s. 1.4(6)(A)) |
| payroll_tax | mandatory | `ma_employee_paid_leave_contribution` | engine_text+law_classification | yes | scenario_081 805.01 | 'ma_employee_paid_leave_contribution' (Massachusetts employee paid leave contribution) rests on an optional employer election: "Employee-side Massachusetts Paid Family and Medical Leave contribution, assuming the employer withholds the maximum permitted employee share."; 'ma_employee_paid_leave_contribution' (Massachusetts employee paid leave contribution) is classified as an optional employer pass-through (M.G.L. c. 175M, s. 6(a), (c) and (d); 458 CMR 2.05(5)) |
| payroll_tax | mandatory | `mn_employee_paid_leave_contribution` | engine_text+law_classification | yes | scenario_032 127.60 | 'mn_employee_paid_leave_contribution' (Minnesota employee paid leave contribution) rests on an optional employer election: "Employee-side Minnesota Paid Leave contribution, assuming the employer withholds the maximum permitted employee share."; 'mn_employee_paid_leave_contribution' (Minnesota employee paid leave contribution) is classified as an optional employer pass-through (Minn. Stat. 268B.14, subds. 1, 3 and 5a) |
| payroll_tax | mandatory | `ny_employee_disability_benefits_contribution` | law_classification | yes | scenario_082 31.20 | 'ny_employee_disability_benefits_contribution' (New York employee disability benefits contribution) is classified as an optional employer pass-through (N.Y. Workers' Compensation Law ss. 209(3)-(4) and 210(1)) |
| payroll_tax | mandatory | `ny_employee_paid_family_leave_contribution` | law_classification | yes | scenario_082 411.91 | 'ny_employee_paid_family_leave_contribution' (New York employee paid family leave contribution) is classified as an optional employer pass-through (N.Y. Workers' Compensation Law ss. 209(3)-(4) and 210(1)) |
| payroll_tax | mandatory | `de_employee_paid_leave_contribution` | engine_text | no |  | 'de_employee_paid_leave_contribution' (Delaware employee paid leave contribution) rests on an optional employer election: "Employee-side Delaware paid leave contribution, assuming the employer withholds the maximum permitted employee share." |
| payroll_tax | mandatory | `me_employee_paid_leave_contribution` | engine_text | no |  | 'me_employee_paid_leave_contribution' (Maine employee paid leave contribution) rests on an optional employer election: "Employee-side Maine paid leave contribution, assuming the employer withholds the maximum permitted employee share." |
| payroll_tax | mandatory | `vt_employee_child_care_contribution` | engine_text | no |  | 'vt_employee_child_care_contribution' (Vermont employee child care contribution) rests on an optional employer election: "Employee-side Vermont Child Care Contribution, assuming the employer withholds the maximum permitted employee share." |
| state_income_tax_before_refundable_credits | after_nonrefundable_credits | `ms_income_tax_before_credits_unit` | variable_name | no |  | 'ms_income_tax_before_credits_unit' (Mississippi income tax before credits) is a tax before credits, and nothing on its path subtracts nonrefundable credits |
| state_income_tax_before_refundable_credits | excludes_local_tax | `nyc_income_tax_before_refundable_credits` | variable_name | no |  | 'nyc_income_tax_before_refundable_credits' (NYC income tax) is a local (city or county) amount |
| state_income_tax_before_refundable_credits | state_scope | `nyc_income_tax_before_refundable_credits` | variable_name | no |  | 'nyc_income_tax_before_refundable_credits' (NYC income tax) is a local (city or county) amount |
| state_refundable_credits | state_scope | `md_montgomery_eitc` | variable_name | no |  | 'md_montgomery_eitc' (Montgomery County, Maryland EITC) is a local (city or county) amount |
| state_refundable_credits | state_scope | `nyc_refundable_credits` | variable_name | no |  | 'nyc_refundable_credits' (NYC refundable credits) is a local (city or county) amount |

## Household scope

| Scenario | Output | Person | Earned | Unearned | Reference | Own return | Must file | Counted by |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| scenario_093 | federal_income_tax_before_refundable_credits | dependent1 | 45,000.00 | 0.00 | 8,628.99 | 3,220.00 | True | dependent1_medicaid_eligible -1.00, payroll_tax 3,442.50 |
| scenario_093 | state_income_tax_before_refundable_credits | dependent1 | 45,000.00 | 0.00 | 3,388.25 | 1,139.83 | True | dependent1_medicaid_eligible -1.00, payroll_tax 3,442.50 |
| scenario_123 | federal_income_tax_before_refundable_credits | child1 | 45,000.00 | 0.00 | 5,200.24 | 3,220.00 | True | payroll_tax 3,474.00 |
| scenario_123 | state_income_tax_before_refundable_credits | child1 | 45,000.00 | 0.00 | 3,070.06 | 1,381.50 | True | payroll_tax 3,474.00 |

## Material definition-silent components (information)

| Output | Component | Label | Cells (effect on reference) |
| --- | --- | --- | --- |
| none | | | |

## Notes

- Baseline: policyengine-us 2.15.17 with latest_final reproduces all 1928 scored references within 1e-3 of reference_outputs.csv before anything is reported.
- policyengine-core 3.32.8 sums `adds` and subtracts `subtracts` only when no formula applies, reading a string attribute as a parameter list at the period start (policyengine_core/simulations/simulation.py, `Simulation._run_formula`); a variable with `defined_for` takes its default wherever that variable is not positive (`Simulation._calculate`). Formula sums are read from source, and every expanded node equals the signed sum of its parts in every scored cell: 8128 checks, 0 failures, 1 zeroed by `defined_for`.
- payroll_tax is spm_unit_payroll_tax = sum_contained_tax_units('employee_payroll_tax') (variables/household/expense/tax/spm_unit_payroll_tax.py); employee_payroll_tax adds EMPLOYEE_PAYROLL_TAX_COMPONENTS, employee_state_payroll_tax among them (variables/gov/irs/tax/payroll/employee_payroll_tax.py); `add` sums a person variable over every member of the group, dependents included (policyengine_core/commons/formulas.py, `for_each_variable`).
- Federal income tax: irs_gross_income multiplies every source by not is_tax_unit_dependent (variables/gov/irs/income/taxable_income/adjusted_gross_income/irs_gross_income/irs_gross_income.py), and is_tax_unit_dependent is every member who is neither head nor spouse (variables/household/demographic/tax_unit/is_tax_unit_dependent.py). PA taxable income starts from irs_gross_income (variables/gov/states/pa/tax/income/taxable_income/pa_total_taxable_income.py). The household-scope rows measure the same thing directly: removing the dependent's income leaves the income tax references unchanged and lowers payroll_tax.
- Own return: the dependent alone as tax-unit head with claimed_as_dependent_on_another_return set. basic_standard_deduction then gives min(standard amount, max(earned income + 450, 1,350)) (gov.irs.deductions.standard.dependent.*; the 2026 amount cites Rev. Proc. 2025-32 p. 18 in its metadata, as does the 2026 single amount of 16,100); the filing test is tax_unit_is_required_to_file, the engine's IRC 6012(a)(1) (variables/gov/irs/tax_unit_is_required_to_file.py).
- State income tax list (gov.states.household.state_income_tax_before_refundable_credits): 45 entries in the reference system. latest_md_local_output_scope removed md_local_income_tax_before_refundable_credits (present: False); nyc_income_tax_before_refundable_credits stays in it (present: True).
- Mandatory: 2.15.17's own documentation flags the MN, MA, DE, ME and VT contributions ('assuming the employer withholds the maximum permitted employee share'). The CO FAMLI and NY PFL/DBL variables and the parameters they read carry no such wording; they are flagged by the cited classification in PolicyEngine/policybench#194 @ 049f4f09:reference_audit/2026-10-05-payroll/program_classification.json.
- Mississippi: the state list carries ms_income_tax_before_credits_unit, which comes before Mississippi's nonrefundable credits (ms_income_tax subtracts ms_non_refundable_credits from it, variables/gov/states/ms/tax/income/ms_income_tax.py). Material in scored cells: False.
