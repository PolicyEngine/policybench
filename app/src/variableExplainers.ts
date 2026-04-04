import type { CountryCode } from "./types";

export type VariableExplainer = {
  summary: string;
  bullets: string[];
};

const US_EXPLAINERS: Record<string, VariableExplainer> = {
  adjusted_gross_income: {
    summary:
      "Diagnostics show the largest AGI misses in mixed-income and retirement-heavy households, not ordinary wage cases.",
    bullets: [
      "On the diagnostic slice, large partnership, dividend, and capital-gain households drive the biggest errors. In Colorado scenario_042, some models miss AGI by millions.",
      "Several models also treat visible cashflow as AGI when the tax treatment is different. In scenarios_016 and _058, models effectively count disability-related income that should not flow into AGI.",
    ],
  },
  income_tax: {
    summary:
      "Net federal income tax inherits the same income-base errors and then adds credit-treatment mistakes on top.",
    bullets: [
      "Models often get close on ordinary wage households and drift when the return mixes retirement income, partnership income, or multiple credit regimes.",
      "The hardest rows are usually the same ones that break AGI and credit components, so net tax errors often come from the wrong intermediate values rather than one bad final subtraction.",
    ],
  },
  income_tax_before_refundable_credits: {
    summary:
      "Models often return gross tax before all credits or net tax after too many credits instead of the requested pre-refundable amount.",
    bullets: [
      "In scenarios_006 and _068, Grok explicitly subtracts child credits even though the target is tax before refundable credits.",
      "Mixed-income outliers also dominate the largest misses. In scenario_042, some models understate pre-credit tax by more than $1 million.",
    ],
  },
  income_tax_refundable_credits: {
    summary:
      "The recurring failure is bundling EITC and refundable CTC into one rough total or zeroing the refund out entirely.",
    bullets: [
      "In scenario_035, Grok predicts $13,126 when truth is $1,421, which is consistent with collapsing multiple credit ideas into one amount.",
      "In scenario_060, some models return $0 when truth is $10,377, so the error is not just sizing but also whether any refundable credit exists.",
    ],
  },
  eitc: {
    summary:
      "EITC errors usually jump between a schedule maximum and zero rather than landing near the correct point on the schedule.",
    bullets: [
      "In scenario_035, Grok predicts near-max EITC even though truth is $45.",
      "In scenarios_060 and _074, some models return $0 on clearly positive EITC cases.",
    ],
  },
  ctc: {
    summary:
      "The common mistakes are flat per-child guesses and dropping the refundable piece.",
    bullets: [
      "In scenario_030, several models still return $8,000 even though truth is $0.",
      "In scenario_047, Grok returns $0 on truth $6,600 and explains the case as if only the non-refundable piece mattered.",
    ],
  },
  snap: {
    summary:
      "Positive SNAP cases are the main miss; many models zero them out using raw asset or net-worth heuristics.",
    bullets: [
      "In scenarios_035 and _047, several models return $0 on households with truth above $11,000.",
      "In scenario_092, Gemini Pro cites SNAP asset limits and returns $0 even though the visible prompt inputs do not support that denial.",
    ],
  },
  ssi: {
    summary:
      "SSI misses are usually driven by treating household wealth or net worth as if it were the SSI resource test.",
    bullets: [
      "In scenarios_054 and _092, many models return $0 against truth $11,604 after citing asset-style heuristics.",
      "There are also false positives in the other direction when models shortcut from low income to SSI entitlement.",
    ],
  },
  free_school_meals: {
    summary:
      "The main error is false negatives from simple income-threshold rules.",
    bullets: [
      "In scenarios_048 and _090, models deny eligibility on positive cases by applying broad poverty-line heuristics.",
      "This binary target is otherwise easier than the dollar outputs, so a small number of false negatives carry most of the signal.",
    ],
  },
  is_medicaid_eligible: {
    summary:
      "Models often overuse Medicare enrollment or visible assets as disqualifiers and miss non-wage eligibility pathways.",
    bullets: [
      "In scenarios_054 and _076, many models return 0 when truth is 1.",
      "The errors are not just arithmetic. They reflect the wrong eligibility pathway being chosen from the household facts.",
    ],
  },
  state_agi: {
    summary:
      "Models often copy federal AGI into state AGI even when the state treatment differs or the state has no income tax base at all.",
    bullets: [
      "In Washington scenario_094, some models predict millions of state AGI when truth is $0.",
      "In Colorado scenario_042, the same federal-to-state carryover shows up on a large mixed-income household.",
    ],
  },
  state_income_tax_before_refundable_credits: {
    summary:
      "This output usually fails when models import rough federal or flat-rate logic into state-specific tax bases.",
    bullets: [
      "In small-liability cases like scenarios_055 and _060, several models overshoot by a wide margin relative to truth.",
      "In large cases like scenario_042, the main failure is still the wrong state tax base rather than the final credit step.",
    ],
  },
  state_refundable_credits: {
    summary:
      "Most rows are easy zeros; the informative misses are the few positive state credits that models leave at zero.",
    bullets: [
      "In Colorado scenario_090, several models return $0 when truth is $6,836.",
      "When models do predict a positive state credit, they often derive it from a rough federal-credit ratio instead of the state program itself.",
    ],
  },
  household_state_income_tax: {
    summary:
      "Net state tax inherits the wrong state tax base and then misses the offset from state credits.",
    bullets: [
      "In Washington scenario_094, some models invent state tax where truth is $0.",
      "In scenario_074, every model stays positive even though truth is negative after credits are applied.",
    ],
  },
};

const UK_EXPLAINERS: Record<string, VariableExplainer> = {
  income_tax: {
    summary:
      "UK Income Tax misses cluster in mixed-income and relief-heavy cases rather than plain salary cases.",
    bullets: [
      "Capital gains, dividends, property income, Gift Aid, and pension contributions raise error rates in the diagnostics. In scenario_027, GPT-5.4 appears to fold gains into ordinary tax and overshoots from £15,752 to £300,553.",
      "Some weaker models also pool household income when the target is person-level tax aggregated to the household. In scenario_016, they miss a working child with earnings.",
    ],
  },
  national_insurance: {
    summary:
      "Models often treat National Insurance as a shadow of income tax even though the schedules and age rules differ.",
    bullets: [
      "In scenario_010, Grok charges NI to a 73-year-old earner when truth is £0.",
      "On multi-person wage cases like scenario_001, some models undercount the combined employee NI materially.",
    ],
  },
  child_benefit: {
    summary:
      "The main error is netting the High Income Child Benefit Charge into the Child Benefit amount itself.",
    bullets: [
      "In scenarios_001, _023, and _080, some models return £0 because they treat HICBC as eliminating the benefit output.",
      "Older-child edge cases also matter. In scenario_086, all five models return £0 when truth is still positive.",
    ],
  },
  universal_credit: {
    summary:
      "Universal Credit misses are driven by capital and tenure heuristics that are too blunt for the benchmark target.",
    bullets: [
      "In scenarios_067, _081, and _047, nearly every model returns £0 on positive cases after applying a hard capital-limit story.",
      "There are also false positives from formula-like reasoning. In scenario_009, Gemini Flash predicts a positive UC amount on truth £0 by adding standard and child elements mechanically.",
    ],
  },
  pension_credit: {
    summary:
      "The high headline score is flattered by many zero rows; the harder positive cases are still often missed.",
    bullets: [
      "In scenarios_014, _021, and _041, models return £0 on positive older-household cases after citing broad income or capital heuristics.",
      "There are also false positives in the other direction, such as scenario_050, where a model folds in a housing-style amount and predicts Pension Credit on truth £0.",
    ],
  },
  pip: {
    summary:
      "PIP is mostly an award-level problem rather than a yes-or-no eligibility problem.",
    bullets: [
      "In scenarios_039 and _035, weaker models underprice combined household awards.",
      "In scenarios_041 and _075, some models overstate the annual amount by choosing the wrong daily living or mobility rate combination.",
    ],
  },
};

const EXPLAINERS: Record<CountryCode, Record<string, VariableExplainer>> = {
  us: US_EXPLAINERS,
  uk: UK_EXPLAINERS,
};

export function getVariableExplainer(
  country: CountryCode,
  variable: string,
): VariableExplainer | null {
  return EXPLAINERS[country][variable] ?? null;
}
