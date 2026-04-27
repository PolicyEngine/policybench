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
  payroll_tax: "Payroll tax",
  self_employment_tax: "Self-employment tax",
  local_income_tax: "Local income tax",
  income_tax_before_refundable_credits: "Federal tax before refundable credits",
  income_tax_refundable_credits: "Federal refundable credits",
  eitc: "EITC",
  ctc: "CTC",
  snap: "SNAP",
  ssi: "SSI",
  tanf: "TANF",
  wic: "WIC",
  free_school_meals_eligible: "Free school meals eligibility",
  household_free_school_meal_eligible: "Free school meals eligibility",
  reduced_price_school_meals_eligible:
    "Reduced-price school meals eligibility",
  household_reduced_price_school_meal_eligible:
    "Reduced-price school meals eligibility",
  person_medicaid_eligible: "Person-level Medicaid eligibility",
  person_chip_eligible: "Person-level CHIP eligibility",
  person_medicare_eligible: "Person-level Medicare eligibility",
  person_head_start_eligible: "Person-level Head Start eligibility",
  person_early_head_start_eligible: "Person-level Early Head Start eligibility",
  person_employee_social_security_tax: "Person-level employee Social Security tax",
  person_employee_medicare_tax: "Person-level employee Medicare tax",
  household_additional_medicare_tax: "Household Additional Medicare Tax",
  state_agi: "State adjusted gross income",
  state_income_tax_before_refundable_credits:
    "State tax before refundable credits",
  state_refundable_credits: "State refundable credits",
  household_state_income_tax: "State income tax",
};

const UK_VARIABLE_LABELS: Record<string, string> = {
  income_tax: "Income Tax",
  national_insurance: "National Insurance",
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
  payroll_tax: "Federal tax",
  self_employment_tax: "Federal tax",
  local_income_tax: "Local tax",
  income_tax_before_refundable_credits: "Federal tax",
  income_tax_refundable_credits: "Credits",
  eitc: "Credits",
  ctc: "Credits",
  snap: "Benefits",
  ssi: "Benefits",
  tanf: "Benefits",
  wic: "Benefits",
  free_school_meals_eligible: "Coverage",
  household_free_school_meal_eligible: "Benefits",
  reduced_price_school_meals_eligible: "Coverage",
  household_reduced_price_school_meal_eligible: "Benefits",
  person_medicaid_eligible: "Coverage",
  person_chip_eligible: "Coverage",
  person_medicare_eligible: "Coverage",
  person_head_start_eligible: "Coverage",
  person_early_head_start_eligible: "Coverage",
  person_employee_social_security_tax: "Federal tax",
  person_employee_medicare_tax: "Federal tax",
  household_additional_medicare_tax: "Federal tax",
  state_agi: "State tax",
  state_income_tax_before_refundable_credits: "State tax",
  state_refundable_credits: "State tax",
  household_state_income_tax: "State tax",
};

const UK_VARIABLE_CATEGORIES: Record<string, string> = {
  income_tax: "Tax",
  national_insurance: "Tax",
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
  const personEligibility = parsePersonEligibilityVariable(variable);
  if (personEligibility) {
    return `${personEligibility.personLabel} ${personEligibility.program} eligibility`;
  }
  const personPayroll = parsePersonPayrollVariable(variable);
  if (personPayroll) {
    return `${personPayroll.personLabel} ${personPayroll.component}`;
  }
  const labelMap = country === "uk" ? UK_VARIABLE_LABELS : US_VARIABLE_LABELS;
  return labelMap[variable] ?? variable.replace(/_/g, " ");
}

export function getVariableCategory(
  variable: string,
  country: CountryCode = "us"
): string {
  if (parsePersonEligibilityVariable(variable)) {
    return "Coverage";
  }
  if (parsePersonPayrollVariable(variable)) {
    return "Federal tax";
  }
  const categoryMap =
    country === "uk" ? UK_VARIABLE_CATEGORIES : US_VARIABLE_CATEGORIES;
  return categoryMap[variable] ?? "Other";
}

function parsePersonEligibilityVariable(variable: string):
  | { personLabel: string; program: string }
  | null {
  const match = variable.match(
    /^(adult\d+|child\d+)_(medicaid|chip|medicare|head_start|early_head_start)_eligible$/
  );
  if (!match) {
    return null;
  }
  const [, person, program] = match;
  const personLabel = person
    .replace("adult", "Adult ")
    .replace("child", "Child ");
  const programLabel =
    program === "chip"
      ? "CHIP"
      : program
          .split("_")
          .map((word) => word[0].toUpperCase() + word.slice(1))
          .join(" ");
  return { personLabel, program: programLabel };
}

function parsePersonPayrollVariable(variable: string):
  | { personLabel: string; component: string }
  | null {
  const match = variable.match(
    /^(adult\d+|child\d+)_(employee_social_security_tax|employee_medicare_tax)$/
  );
  if (!match) {
    return null;
  }
  const [, person, component] = match;
  const personLabel = person
    .replace("adult", "Adult ")
    .replace("child", "Child ");
  const componentLabel =
    component === "employee_social_security_tax"
      ? "employee Social Security tax"
      : "employee Medicare tax";
  return { personLabel, component: componentLabel };
}

export function isBinaryVariable(
  variable: string,
  country: CountryCode = "us"
): boolean {
  if (country === "uk") {
    return false;
  }
  return (
    variable === "free_school_meals_eligible" ||
    variable === "household_free_school_meal_eligible" ||
    variable === "reduced_price_school_meals_eligible" ||
    variable === "household_reduced_price_school_meal_eligible" ||
    variable === "person_medicaid_eligible" ||
    variable === "person_chip_eligible" ||
    variable === "person_medicare_eligible" ||
    variable === "person_head_start_eligible" ||
    variable === "person_early_head_start_eligible" ||
    parsePersonEligibilityVariable(variable) !== null
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

export type PolicyEngineBundle = {
  bundle_id?: string | null;
  country_id?: string | null;
  policyengine_version?: string | null;
  model_package?: string | null;
  model_version?: string | null;
  data_package?: string | null;
  data_version?: string | null;
  default_dataset?: string | null;
  default_dataset_uri?: string | null;
  certified_data_build_id?: string | null;
  certified_data_artifact_sha256?: string | null;
  data_build_model_version?: string | null;
  data_build_model_git_sha?: string | null;
  data_build_fingerprint?: string | null;
  compatibility_basis?: string | null;
  certified_by?: string | null;
};

export type BenchData = {
  country: CountryCode;
  policyengineBundles?: Partial<Record<CountryCode, PolicyEngineBundle>>;
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
  policyengineBundles?: Partial<Record<CountryCode, PolicyEngineBundle>>;
};

export type DashboardBundle = {
  countries: Record<CountryCode, BenchData>;
  global: GlobalBenchData;
};
