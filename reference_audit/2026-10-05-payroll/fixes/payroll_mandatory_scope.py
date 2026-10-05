"""Candidate output-definition adapter: keep optional employer pass-through out of payroll_tax.

PolicyBench defines payroll_tax as "annual household employee-side payroll tax: employee
Social Security tax, employee Medicare tax, Additional Medicare Tax, and mandatory
employee state payroll taxes. Exclude employer payroll taxes, ..."
(policybench/benchmark_specs.json, output prompt).

policyengine-us 2.15.17 builds the output from ``employee_state_payroll_tax``
(variables/gov/states/tax/payroll/employee_state_payroll_tax.py), whose documentation
reads "Employee-side mandatory state payroll taxes and payroll-funded contributions".
It adds one ``<st>_employee_state_payroll_tax`` aggregate per state, and those add each
program's employee contribution. For programs whose premium the law places on the
employer, with the employer allowed but not required to deduct a share from wages, the
engine counts the largest share the employer may deduct. Its Minnesota variable says so:
"assuming the employer withholds the maximum permitted employee share"
(variables/gov/states/mn/tax/payroll/paid_leave/mn_employee_paid_leave_contribution.py).

This module removes those programs (``OPTIONAL``, classified from primary law in
``../program_classification.json``) from the list behind ``employee_state_payroll_tax``,
so the scored output again matches its definition. Only the list changes; no formula,
rate or amount changes, and every mandatory employee contribution stays in. It mirrors
the 2026-09-28 Maryland output-scope adapter
(reference_audit/2026-09-28/fixes/latest_md_local_output_scope.py).
"""

from policyengine_core.reforms import Reform
from policyengine_core.variables import Variable

FIX_ID = "payroll_mandatory_scope"
DESCRIPTION = (
    "Exclude employee shares the employer may but need not deduct from the payroll "
    "tax output (output definition)"
)
AGGREGATE = "employee_state_payroll_tax"
# Employee shares the employer may, but need not, deduct from wages
# (program_classification.json, classification optional_employer_pass_through).
OPTIONAL = (
    "co_employee_famli_contribution",
    "ma_employee_paid_leave_contribution",
    "mn_employee_paid_leave_contribution",
    "ny_employee_disability_benefits_contribution",
    "ny_employee_paid_family_leave_contribution",
)


def leaves(system) -> list[str]:
    """Every program contribution under the engine's state aggregates, in order.

    CountryTaxBenefitSystem applies a reform twice to the same system, so on the second
    pass the aggregate already lists programs; those are kept as they are.
    """
    out = []
    for name in system.variables[AGGREGATE].adds:
        if name.endswith("_" + AGGREGATE):
            out.extend(system.variables[name].adds)
        else:
            out.append(name)
    return out


class reform(Reform):
    def apply(self):
        listed = self.variables[AGGREGATE].adds
        if not any(name.endswith("_" + AGGREGATE) for name in listed):
            # Second pass: the list already holds the kept programs.
            assert not set(OPTIONAL) & set(listed)
            return
        current = leaves(self)
        unknown = sorted(set(OPTIONAL) - set(current))
        if unknown:
            raise ValueError(f"not under {AGGREGATE}: {unknown}")
        kept = [name for name in current if name not in OPTIONAL]

        class employee_state_payroll_tax(Variable):
            adds = kept

        self.update_variable(employee_state_payroll_tax)
        assert list(self.variables[AGGREGATE].adds) == kept
