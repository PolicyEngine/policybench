import type { CountryCode } from "./types";

export type VariableExplainer = {
  summary: string;
  bullets: string[];
};

const US_EXPLAINERS: Record<string, VariableExplainer> = {
  federal_income_tax_before_refundable_credits: {
    summary:
      "This target isolates federal income tax after nonrefundable credits but before refundable credits.",
    bullets: [
      "It subtracts nonrefundable credits actually used, such as CDCC and the nonrefundable part of CTC when applicable.",
      "It leaves EITC and refundable credit portions, such as refundable CTC, for the refundable-credits output.",
    ],
  },
  federal_refundable_credits: {
    summary:
      "This target captures the refundable federal credit side of the income-tax calculation.",
    bullets: [
      "It includes EITC and refundable portions of credits such as refundable CTC when applicable.",
      "It excludes the ACA Premium Tax Credit, which is outside the benchmark federal income-tax target.",
    ],
  },
  premium_tax_credit: {
    summary:
      "This target captures ACA Marketplace premium assistance as a health-related resource, separate from federal income-tax credits.",
    bullets: [
      "It depends on Marketplace eligibility, disqualifying health coverage such as affordable employer coverage, ACA MAGI, and the local second-lowest-cost silver plan premium.",
      "Marketplace plan facts are phrased as selected-plan information a household might know, while the local benchmark premium usually still has to be estimated.",
    ],
  },
  snap: {
    summary:
      "Positive SNAP cases are the main miss; many models zero them out using raw asset or net-worth heuristics.",
    bullets: [
      "In scenarios_035 and _047, several models return $0 on households with reference values above $11,000.",
      "In scenario_092, Gemini Pro cites SNAP asset limits and returns $0 even though the visible prompt inputs do not support that denial.",
    ],
  },
  ssi: {
    summary:
      "SSI misses are usually driven by treating household wealth or net worth as if it were the SSI resource test.",
    bullets: [
      "In scenarios_054 and _092, many models return $0 against a $11,604 reference value after citing asset-style heuristics.",
      "There are also false positives in the other direction when models shortcut from low income to SSI entitlement.",
    ],
  },
  free_school_meals_eligible: {
    summary:
      "The main error is false negatives from simple income-threshold rules.",
    bullets: [
      "In scenarios_048 and _090, models deny eligibility on positive cases by applying broad poverty-line heuristics.",
      "This binary target is otherwise easier than the dollar outputs, so a small number of false negatives carry most of the signal.",
    ],
  },
  person_medicaid_eligible: {
    summary:
      "Models often overuse Medicare enrollment or visible assets as disqualifiers and miss non-wage eligibility pathways.",
    bullets: [
      "In scenarios_054 and _076, many models return 0 when the reference flag is 1.",
      "The errors are not just arithmetic. They reflect the wrong eligibility pathway being chosen from the household facts.",
    ],
  },
  state_income_tax_before_refundable_credits: {
    summary:
      "This output usually fails when models import rough federal or flat-rate logic into state-specific tax bases.",
    bullets: [
      "In small-liability cases like scenarios_055 and _060, several models overshoot by a wide margin relative to the reference value.",
      "In large cases like scenario_042, the main failure is still the wrong state tax base rather than the final credit step.",
    ],
  },
  state_refundable_credits: {
    summary:
      "Most rows are easy zeros; the informative misses are the few positive state credits that models leave at zero.",
    bullets: [
      "In Colorado scenario_090, several models return $0 against a $6,836 reference value.",
      "When models do predict a positive state credit, they often derive it from a rough federal-credit ratio instead of the state program itself.",
    ],
  },
};

const UK_EXPLAINERS: Record<string, VariableExplainer> = {
  income_tax: {
    summary:
      "UK Income Tax misses cluster in mixed-income and relief-heavy cases rather than plain salary cases.",
    bullets: [
      "Capital gains, dividends, property income, Gift Aid, and pension contributions raise error rates. In scenario_027, GPT-5.4 appears to fold gains into ordinary tax and overshoots from £15,752 to £300,553.",
      "Some weaker models also pool household income when the target is person-level tax aggregated to the household. In scenario_016, they miss a working child with earnings.",
    ],
  },
  national_insurance: {
    summary:
      "Models often treat National Insurance as a shadow of income tax even though the schedules and age rules differ.",
    bullets: [
      "In scenario_010, Grok charges NI to a 73-year-old earner against a £0 reference.",
      "On multi-person wage cases like scenario_001, some models undercount the combined employee NI materially.",
    ],
  },
  child_benefit: {
    summary:
      "Child Benefit is scored before the High Income Child Benefit Charge; HICBC belongs in Income Tax.",
    bullets: [
      "A common error is returning a net amount or £0 for high-income households after applying HICBC to the benefit output itself.",
      "Older-child and qualifying-young-person cases remain separate edge cases because the child can qualify after age 16 when the prompt states that status.",
    ],
  },
  universal_credit: {
    summary:
      "Universal Credit misses are driven by capital and tenure heuristics that are too blunt for the benchmark target.",
    bullets: [
      "In scenarios_067, _081, and _047, nearly every model returns £0 on positive cases after applying a hard capital-limit story.",
      "There are also false positives from formula-like reasoning. In scenario_009, Gemini Flash predicts a positive UC amount against a £0 reference by adding standard and child elements mechanically.",
    ],
  },
  pension_credit: {
    summary:
      "The high headline score is flattered by many zero rows; the harder positive cases are still often missed.",
    bullets: [
      "In scenarios_014, _021, and _041, models return £0 on positive older-household cases after citing broad income or capital heuristics.",
      "There are also false positives in the other direction, such as scenario_050, where a model folds in a housing-style amount and predicts Pension Credit against a £0 reference.",
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
  us: {
    ...US_EXPLAINERS,
    reduced_price_school_meals_eligible:
      US_EXPLAINERS.free_school_meals_eligible,
    person_chip_eligible: US_EXPLAINERS.person_medicaid_eligible,
    person_medicare_eligible: US_EXPLAINERS.person_medicaid_eligible,
  },
  uk: UK_EXPLAINERS,
};

export function getVariableExplainer(
  country: CountryCode,
  variable: string,
): VariableExplainer | null {
  return EXPLAINERS[country][variable] ?? null;
}
