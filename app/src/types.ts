export type PromptVariant = {
  tool?: string;
  json?: string;
};

export type CountryCode = "us" | "uk";
export type ViewKey = CountryCode | "global";

export const VIEW_LABELS: Record<ViewKey, string> = {
  global: "Global",
  us: "United States",
  uk: "United Kingdom",
};

export const VIEW_SHORT_LABELS: Record<CountryCode, string> = {
  us: "US",
  uk: "UK",
};

const US_VARIABLE_LABELS: Record<string, string> = {
  adjusted_gross_income: "Federal adjusted gross income",
  income_tax: "Federal income tax",
  employee_payroll_tax: "Employee payroll tax",
  self_employment_tax: "Self-employment tax",
  income_tax_before_refundable_credits: "Federal tax before refundable credits",
  income_tax_refundable_credits: "Federal refundable credits",
  eitc: "EITC",
  ctc: "CTC",
  snap: "SNAP",
  ssi: "SSI",
  free_school_meals: "Free school meals eligibility",
  household_free_school_meal_eligible: "Free school meals eligibility",
  is_medicaid_eligible: "Any Medicaid eligibility",
  household_medicaid_eligible: "Any Medicaid eligibility",
  state_agi: "State adjusted gross income",
  state_income_tax_before_refundable_credits:
    "State tax before refundable credits",
  state_refundable_credits: "State refundable credits",
  household_state_income_tax: "State income tax",
};

const UK_VARIABLE_LABELS: Record<string, string> = {
  income_tax: "Income Tax",
  national_insurance: "National Insurance",
  council_tax_less_benefit: "Council Tax less support",
  child_benefit: "Child Benefit",
  universal_credit: "Universal Credit",
  pension_credit: "Pension Credit",
  pip: "Personal Independence Payment",
  housing_benefit: "Housing Benefit",
  carers_allowance: "Carer's Allowance",
  attendance_allowance: "Attendance Allowance",
};

const US_VARIABLE_CATEGORIES: Record<string, string> = {
  adjusted_gross_income: "Federal tax",
  income_tax: "Federal tax",
  employee_payroll_tax: "Federal tax",
  self_employment_tax: "Federal tax",
  income_tax_before_refundable_credits: "Federal tax",
  income_tax_refundable_credits: "Credits",
  eitc: "Credits",
  ctc: "Credits",
  snap: "Benefits",
  ssi: "Benefits",
  free_school_meals: "Benefits",
  household_free_school_meal_eligible: "Benefits",
  is_medicaid_eligible: "Benefits",
  household_medicaid_eligible: "Benefits",
  state_agi: "State tax",
  state_income_tax_before_refundable_credits: "State tax",
  state_refundable_credits: "State tax",
  household_state_income_tax: "State tax",
};

const UK_VARIABLE_CATEGORIES: Record<string, string> = {
  income_tax: "Tax",
  national_insurance: "Tax",
  council_tax_less_benefit: "Tax",
  child_benefit: "Benefits",
  universal_credit: "Benefits",
  pension_credit: "Benefits",
  pip: "Benefits",
  housing_benefit: "Benefits",
  carers_allowance: "Benefits",
  attendance_allowance: "Benefits",
};

export function getVariableLabel(
  variable: string,
  country: CountryCode = "us"
): string {
  const labelMap = country === "uk" ? UK_VARIABLE_LABELS : US_VARIABLE_LABELS;
  return labelMap[variable] ?? variable.replace(/_/g, " ");
}

export function getVariableCategory(
  variable: string,
  country: CountryCode = "us"
): string {
  const categoryMap =
    country === "uk" ? UK_VARIABLE_CATEGORIES : US_VARIABLE_CATEGORIES;
  return categoryMap[variable] ?? "Other";
}

export function isBinaryVariable(
  variable: string,
  country: CountryCode = "us"
): boolean {
  if (country === "uk") {
    return false;
  }
  return (
    variable === "free_school_meals" ||
    variable === "household_free_school_meal_eligible" ||
    variable === "is_medicaid_eligible" ||
    variable === "household_medicaid_eligible"
  );
}

export type BenchScenario = {
  country: CountryCode;
  state: string;
  filingStatus?: string | null;
  numAdults: number;
  numChildren: number;
  totalIncome: number;
  prompt?: PromptVariant;
};

export type ModelStat = {
  model: string;
  condition: string;
  score: number;
  exact?: number;
  within1pct?: number;
  within5pct?: number;
  mae?: number | null;
  within10pct?: number;
  n: number;
  nParsed: number;
  coverage?: number;
  mape?: number;
  accuracy?: number;
  runCount?: number;
  scoreRunMean?: number;
  scoreRunStd?: number;
  scoreRunMin?: number;
  scoreRunMax?: number;
  within10pctRunMean?: number;
  within10pctRunStd?: number;
  within10pctRunMin?: number;
  within10pctRunMax?: number;
  maeRunMean?: number;
  maeRunStd?: number;
  countryScores?: Partial<Record<CountryCode, number>>;
};

export type ProgramStat = {
  variable: string;
  score: number;
  exact?: number;
  within1pct?: number;
  within5pct?: number;
  mae: number;
  n: number;
  nParsed: number;
  mape?: number;
  accuracy?: number;
  within10pct?: number;
  coverage?: number;
};

export type HeatmapEntry = {
  model: string;
  variable: string;
  condition: string;
  score: number;
  exact?: number;
  within1pct?: number;
  within5pct?: number;
  mae: number;
  n: number;
  nParsed: number;
  coverage: number;
  accuracy?: number;
  within10pct?: number;
};

export type ScenarioPrediction = {
  prediction: number;
  error: number;
  groundTruth: number;
  explanation?: string;
};

export type ScenarioPredictionsByVariable = Record<
  string,
  Record<string, ScenarioPrediction>
>;

export type ProgramFailure = {
  variable: string;
  isBinary: boolean;
  overallCorrectPct: number;
  withChildrenPct?: number | null;
  withoutChildrenPct?: number | null;
  lowIncomePct?: number | null;
  highIncomePct?: number | null;
  positiveCasePct?: number | null;
  zeroCasePct?: number | null;
  underpredictSharePositivePct?: number | null;
};

export type HouseholdFailure = {
  label: string;
  correctPct: number;
  n: number;
};

export type FailureModesPayload = {
  programs: ProgramFailure[];
  households: HouseholdFailure[];
};

export type BenchData = {
  country: CountryCode;
  scenarios: Record<string, BenchScenario>;
  modelStats: ModelStat[];
  programStats: ProgramStat[];
  heatmap: HeatmapEntry[];
  scenarioPredictions: Record<string, ScenarioPredictionsByVariable>;
  failureModes: FailureModesPayload;
};

export type CountrySummary = {
  key: CountryCode;
  label: string;
  households: number;
  models: number;
  programs: number;
};

export type GlobalBenchData = {
  modelStats: ModelStat[];
  countrySummaries: CountrySummary[];
  sharedModelCount: number;
};

export type DashboardBundle = {
  countries: Record<CountryCode, BenchData>;
  global: GlobalBenchData;
};
