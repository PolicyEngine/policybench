"""r04: count capital gain distributions reported without Schedule D (Form 1040 line 7a).

Backport of upstream policyengine-us PR #8839 (merge commit 491642087f, merged
2026-07-05, fixes issue #8828) to policyengine-us 1.755.4. The three files the PR
changes are byte-identical in 1.755.4 and in the PR's parent commit
(491642087f^), so the backport is the PR's own diff, applied as a reform.

Defect in 1.755.4
-----------------
`non_sch_d_capital_gains` ("Capital gains not reported on Schedule D", PUF E01100)
is read only by has_qdiv_or_ltcg, dwks09 and dwks10. Those Schedule D worksheet
lines feed regular_tax_before_credits, which only alternative_minimum_tax reads.
The input is absent from gov.irs.gross_income.sources, so it never reaches
irs_gross_income, AGI, or Section 86 provisional income (taxable_ss_magi). It is
absent from net_capital_gain, so it never reaches the preferential-rate base
(capital_gains_excluded_from_taxable_income / capital_gains_tax). It is absent
from gov.irs.investment.income.sources, so it never reaches net investment income.

Law
---
* IRC 61(a)(3): gross income includes gains derived from dealings in property.
* IRC 852(b)(3)(B): a capital gain dividend "shall be treated by the shareholders
  as a gain from the sale or exchange of a capital asset held for more than 1
  year", i.e. long-term capital gain, which is net capital gain for the IRC 1(h)
  rates.
* 2025 Form 1040 instructions (i1040gi), line 7, Exception 1: when the only
  capital gains are 1099-DIV box 2a distributions, enter them on line 7a and
  check "Schedule D not required" on line 7b, so they are part of total income
  and AGI. The Social Security Benefits Worksheet line 3 includes line 7a
  (IRC 86(b)(2) provisional income). The Qualified Dividends and Capital Gain Tax
  Worksheet line 3 ("No" branch) enters line 7a in the preferential-rate base.
* Form 8960 instructions, line 5a: net gain from disposition of property combines
  Form 1040 line 7a and Schedule 1 line 4, so the distributions are net
  investment income under IRC 1411(c)(1)(A)(iii).

Changes (exactly PR #8839's three code changes, nothing else)
--------------------------------------------------------------
1. gov.irs.gross_income.sources: insert non_sch_d_capital_gains after
   capital_gains (upstream position). Every reader of this list moves with it:
   irs_gross_income, taxable_ss_magi, taxable_uc_agi, dependent_gross_income,
   medicaid_irs_gross_income, student_loan_interest_ald_magi,
   capped_qualified_tuition_expenses_ald.
2. gov.irs.investment.income.sources: append non_sch_d_capital_gains (upstream
   position). Readers: net_investment_income (NIIT, MN NIIT, and the EITC /
   NJ EITC investment-income tests).
3. net_capital_gain: add non_sch_d_capital_gains to the returned total, as the
   upstream formula does (no Schedule D netting on the no-Schedule-D path).

The PR's changelog entry and YAML tests are not code and are not backported.
dwks09 / dwks10 / has_qdiv_or_ltcg already read the input in 1.755.4 and upstream
did not change them.
"""

from __future__ import annotations

from policyengine_core.periods import instant
from policyengine_core.reforms import Reform
from policyengine_us.model_api import *  # noqa: F401,F403

FIX_ID = "r04_capital_gain_distributions"
DESCRIPTION = (
    "Backport policyengine-us PR #8839 (issue #8828): non_sch_d_capital_gains "
    "(Form 1040 line 7a capital gain distributions, IRC 852(b)(3)(B) long-term "
    "gain) enters gov.irs.gross_income.sources (AGI, Section 86 provisional "
    "income), gov.irs.investment.income.sources (NIIT, EITC investment-income "
    "test), and net_capital_gain (IRC 1(h) preferential-rate base)."
)

INPUT = "non_sch_d_capital_gains"


class net_capital_gain(Variable):
    """Upstream main formula after PR #8839 (net_capital_gain.py lines 20-38)."""

    value_type = float
    entity = TaxUnit
    label = "Net capital gain"
    unit = USD
    documentation = (
        "The excess of net long-term capital gain over net short-term capital"
        'loss, plus qualified dividends (the definition of "net capital gain"'
        "which applies to 26 U.S.C. § 1(h) from § 1(h)(11))."
    )
    definition_period = YEAR
    reference = dict(
        title="26 U.S. Code § 1222(11)",
        href="https://www.law.cornell.edu/uscode/text/26/1222#11",
    )

    def formula(tax_unit, period, parameters):
        lt_capital_gain = max_(0, add(tax_unit, period, ["long_term_capital_gains"]))
        st_capital_loss = max_(0, -add(tax_unit, period, ["short_term_capital_gains"]))
        investment_income_election = add(
            tax_unit,
            period,
            ["investment_income_elected_form_4952"],
        )
        net_cap_gain = max_(
            0,
            lt_capital_gain - st_capital_loss - investment_income_election,
        )
        qual_div_income = add(tax_unit, period, ["qualified_dividend_income"])
        # Capital gain distributions reported without Schedule D (Form 1040
        # line 7 with the box checked) are long-term gains under IRC
        # 852(b)(3)(B) and enter the preferential-rate base directly, with no
        # Schedule D netting available on that filing path.
        non_sch_d_capital_gains = add(tax_unit, period, [INPUT])
        return net_cap_gain + qual_div_income + non_sch_d_capital_gains


def _add_source(node, after: str | None) -> None:
    """Add INPUT to every dated value of a list parameter, keeping each date range."""
    entries = sorted(node.values_list, key=lambda e: e.instant_str)
    starts = [e.instant_str for e in entries]
    for i, entry in enumerate(entries):
        values = list(entry.value)
        if INPUT in values:
            continue
        if after is not None and after in values:
            values.insert(values.index(after) + 1, INPUT)
        else:
            values.append(INPUT)
        stop = (
            instant(starts[i + 1]).offset(-1, "day") if i + 1 < len(entries) else None
        )
        node.update(start=instant(entry.instant_str), stop=stop, value=values)


def modify_parameters(parameters):
    _add_source(parameters.gov.irs.gross_income.sources, after="capital_gains")
    _add_source(parameters.gov.irs.investment.income.sources, after=None)
    return parameters


class reform(Reform):
    def apply(self):
        self.update_variable(net_capital_gain)
        self.modify_parameters(modify_parameters)
