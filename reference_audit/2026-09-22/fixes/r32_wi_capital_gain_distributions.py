"""r32: Wisconsin's 30% capital-gain exclusion omits capital gain distributions reported without Schedule D.

Split out of r04_capital_gain_distributions_v2 on 2026-09-23. policyengine-us PR
#8839 (r04) puts non_sch_d_capital_gains (Form 1040 line 7a distributions) into
federal AGI, which Wisconsin starts from, but leaves Wisconsin's capital gain
subtraction reading long_term_capital_gains only. Upstream main still does, so this
defect is not fixed upstream and is measured on top of the Wisconsin publication
convention plus the #8839 backport (cwi_plus_r04), the value that would otherwise
be published.

Law: Wis. Stat. 71.05(6)(b)9 subtracts 30% of the net capital gain on assets held
more than one year. A capital gain distribution is long-term capital gain (IRC
852(b)(3)(B)), and the 2025 Schedule SB instructions, line 5, apply the 30%
exclusion to capital gain distributions reported directly on the federal return.

Change: in tax year 2026, the Schedule WD long-term gain the formula reads adds
non_sch_d_capital_gains. The engine's formula is otherwise unchanged; without
distributions it computes exactly the 1.755.4 value. Periods: 2026 only.

Sources:
https://docs.legis.wisconsin.gov/statutes/statutes/71/i/05/6/b/9
https://www.law.cornell.edu/uscode/text/26/852#b_3_B
https://www.revenue.wi.gov/TaxForms2025/2025-ScheduleSB-Inst.pdf#page=2
"""

from policyengine_core.reforms import Reform
from policyengine_us.model_api import *  # noqa: F401,F403

FIX_ID = "r32_wi_capital_gain_distributions"
DESCRIPTION = "2026 Wisconsin capital gain subtraction includes capital gain distributions reported without Schedule D."
SOURCE = "non_sch_d_capital_gains"


class wi_capital_gain_loss_subtraction(Variable):
    value_type = float
    entity = TaxUnit
    label = "Wisconsin capital gain/loss subtraction from federal AGI"
    unit = USD
    definition_period = YEAR
    defined_for = StateCode.WI
    reference = "https://www.revenue.wi.gov/TaxForms2025/2025-ScheduleSB-Inst.pdf#page=2"

    def formula(tax_unit, period, parameters):
        stcg_net = add(tax_unit, period, ["short_term_capital_gains"])
        sources = ["long_term_capital_gains"]
        if period.start.year == 2026:
            sources.append(SOURCE)
        ltcg_net = add(tax_unit, period, sources)
        totcg = max_(0, stcg_net + ltcg_net)
        fraction = parameters(period).gov.states.wi.tax.income.subtractions.capital_gain.fraction
        cg_reduction = min_(totcg, max_(0, ltcg_net)) * fraction
        wi_cg = totcg - cg_reduction
        return max_(0, totcg - wi_cg)


class reform(Reform):
    def apply(self):
        self.update_variable(wi_capital_gain_loss_subtraction)
