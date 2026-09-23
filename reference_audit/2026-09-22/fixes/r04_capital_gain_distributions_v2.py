"""2026 distribution-income correction, including the WI exclusion and §1(h)(2).

Federal inclusion follows policyengine-us PR #8839, with distributions included
before the investment-income election reduction. IRC 1(h)(2) applies even if
Schedule D is not required (2025 Schedule D Tax Worksheet, lines 7-9).
Wisconsin Schedule SB instructions, line 5, require the 30% exclusion for mutual
fund/REIT capital gain distributions; adding federal AGI without it overstates WI
income. Existing engine amounts/rates and unrelated behavior are preserved.

Sources:
https://www.law.cornell.edu/uscode/text/26/852#b_3_B
https://www.law.cornell.edu/uscode/text/26/1#h_2
https://www.irs.gov/instructions/i1040sd
https://www.revenue.wi.gov/TaxForms2025/2025-ScheduleSB-Inst.pdf#page=2
"""
from policyengine_core.periods import instant
from policyengine_core.reforms import Reform
from policyengine_us.model_api import *

FIX_ID = "r04_capital_gain_distributions_v2"
DESCRIPTION = "2026 non-Schedule-D distributions: federal inclusion, election reduction, Wisconsin capital-gain exclusion."
SOURCE = "non_sch_d_capital_gains"


class net_capital_gain(Variable):
    value_type = float
    entity = TaxUnit
    label = "Net capital gain"
    unit = USD
    definition_period = YEAR
    reference = "https://www.law.cornell.edu/uscode/text/26/1#h_2"

    def formula(tax_unit, period, parameters):
        lt = max_(0, add(tax_unit, period, ["long_term_capital_gains"]))
        st_loss = max_(0, -add(tax_unit, period, ["short_term_capital_gains"]))
        election = add(tax_unit, period, ["investment_income_elected_form_4952"])
        distributions = add(tax_unit, period, [SOURCE]) if period.start.year == 2026 else 0
        qualified_dividends = add(tax_unit, period, ["qualified_dividend_income"])
        return max_(0, lt - st_loss + distributions - election) + qualified_dividends


class wi_capital_gain_loss_subtraction(Variable):
    value_type = float
    entity = TaxUnit
    label = "Wisconsin capital gain/loss subtraction from federal AGI"
    unit = USD
    definition_period = YEAR
    defined_for = StateCode.WI
    reference = "https://www.revenue.wi.gov/TaxForms2025/2025-ScheduleSB-Inst.pdf#page=2"

    def formula(tax_unit, period, parameters):
        st = add(tax_unit, period, ["short_term_capital_gains"])
        sources = ["long_term_capital_gains"]
        if period.start.year == 2026:
            sources.append(SOURCE)
        lt = add(tax_unit, period, sources)
        total = max_(0, st + lt)
        fraction = parameters(period).gov.states.wi.tax.income.subtractions.capital_gain.fraction
        reduction = min_(total, max_(0, lt)) * fraction
        # Preserve original arithmetic when SOURCE is absent.
        wi_gain = total - reduction
        return max_(0, total - wi_gain)


def modify_parameters(parameters):
    for node, after in [
        (parameters.gov.irs.gross_income.sources, "capital_gains"),
        (parameters.gov.irs.investment.income.sources, None),
    ]:
        values = list(node(instant("2026-01-01")))
        if SOURCE in values:
            continue
        if after in values:
            values.insert(values.index(after) + 1, SOURCE)
        else:
            values.append(SOURCE)
        node.update(start=instant("2026-01-01"), stop=instant("2026-12-31"), value=values)
    return parameters


class reform(Reform):
    def apply(self):
        self.update_variable(net_capital_gain)
        self.update_variable(wi_capital_gain_loss_subtraction)
        self.modify_parameters(modify_parameters)
