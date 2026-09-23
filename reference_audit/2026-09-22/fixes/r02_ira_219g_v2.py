"""Verified r02, with deduction-list substitutions confined to tax year 2026.

The original phase-out arithmetic and MAGI calculations are reused unchanged.
Its `_swap_from` also replaces every future ALD list and carries unindexed 2026
thresholds forward. This sandbox verifies 2026 only, so restore baseline lists
outside that year. No household input or contribution amount is changed.

`mask_dependents` is enabled only by the r01+r02 composition, retaining r01's
return-level restriction while keeping the original contribution variable.
Standalone r02 still changes only active-participant deductibility.

Sources: IRC 219(g); IRS Notice 2025-67 p.4; IRS Pub.590-A Worksheets 1-1,
1-2 and Appendix B; MA General Laws ch.62 sec.2(d)(1)(F); MS 2025 Form 80-100
line 50. See the verification report for links and the scope limitations of
inferring coverage from the benchmark's elective-deferral inputs.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from policyengine_core.parameters import ParameterNode
from policyengine_core.periods import period as make_period
from policyengine_core.reforms import Reform
from policyengine_us.model_api import *

_spec = spec_from_file_location('r02_verified_original', Path(__file__).with_name('r02_ira_219g.py'))
_original = module_from_spec(_spec)
_spec.loader.exec_module(_original)
FIX_ID = 'r02_ira_219g_v2'
DESCRIPTION = 'IRC 219(g) phase-out, confined to 2026; same 2026 arithmetic as original r02.'
YEAR_2026 = make_period('year:2026-01-01:1')
OLD, NEW = _original.OLD, _original.NEW


def modify_parameters(parameters):
    if 'ira_219g' not in parameters.gov.irs.ald.children:
        parameters.gov.irs.ald.add_child('ira_219g', ParameterNode('gov.irs.ald.ira_219g', data=_original.PARAMETER_DATA))
    for node in (
        parameters.gov.irs.ald.deductions,
        parameters.gov.states.ma.tax.income.ald.disallowed,
        parameters.gov.states.ms.tax.income.adjustments.adjustments,
    ):
        values = [NEW if value == OLD else value for value in node('2026-01-01')]
        node.update(period=YEAR_2026, value=values)
    return parameters


def build_reform(mask_dependents=False):
    class traditional_ira_deduction(Variable):
        value_type = float
        entity = Person
        label = 'Traditional IRA deduction (verified 2026 phase-out)'
        unit = USD
        definition_period = YEAR
        reference = 'https://www.law.cornell.edu/uscode/text/26/219'

        def formula(person, period, parameters):
            contributions = person(OLD, period)
            if period.start.year != 2026:
                return contributions
            result = min_(contributions, person('ira_219g_deductible_limit', period))
            if mask_dependents:
                claimant = person('is_tax_unit_head', period) | (
                    person('is_tax_unit_spouse', period)
                    & person.tax_unit('tax_unit_is_joint', period)
                )
                result = result * claimant
            return result

    class r02_verified_reform(Reform):
        def apply(self):
            for variable in _original.REFORM_VARIABLES[:-1]:
                self.update_variable(variable)
            self.update_variable(traditional_ira_deduction)
            self.modify_parameters(modify_parameters)
    return r02_verified_reform


reform = build_reform()
