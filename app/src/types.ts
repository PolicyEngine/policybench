export type PromptVariant = {
  tool?: string;
  json?: string;
};

export const VARIABLE_LABELS: Record<string, string> = {
  adjusted_gross_income: "Federal adjusted gross income",
  income_tax_before_refundable_credits: "Federal tax before refundable credits",
  income_tax_refundable_credits: "Federal refundable credits",
  eitc: "EITC",
  ctc: "CTC",
  snap: "SNAP",
  ssi: "SSI",
  free_school_meals: "Free school meals eligibility",
  is_medicaid_eligible: "Any Medicaid eligibility",
  state_agi: "State adjusted gross income",
  state_income_tax_before_refundable_credits:
    "State tax before refundable credits",
  state_refundable_credits: "State refundable credits",
  household_state_income_tax: "State income tax",
};

export const VARIABLE_CATEGORIES: Record<string, string> = {
  adjusted_gross_income: "Federal tax",
  income_tax_before_refundable_credits: "Federal tax",
  income_tax_refundable_credits: "Credits",
  eitc: "Credits",
  ctc: "Credits",
  snap: "Benefits",
  ssi: "Benefits",
  free_school_meals: "Benefits",
  is_medicaid_eligible: "Benefits",
  state_agi: "State tax",
  state_income_tax_before_refundable_credits: "State tax",
  state_refundable_credits: "State tax",
  household_state_income_tax: "State tax",
};

export function getVariableLabel(variable: string): string {
  return VARIABLE_LABELS[variable] ?? variable.replace(/_/g, " ");
}

export function isBinaryVariable(variable: string): boolean {
  return variable === "free_school_meals" || variable === "is_medicaid_eligible";
}

export type BenchScenario = {
  state: string;
  filingStatus: string;
  numAdults: number;
  numChildren: number;
  totalIncome: number;
  promptByVariable?: Record<string, PromptVariant>;
};

export type ModelStat = {
  model: string;
  condition: string;
  mae: number;
  within10pct: number;
  n: number;
  nParsed: number;
  coverage: number;
  mape?: number;
  accuracy?: number;
  runCount?: number;
  within10pctRunMean?: number;
  within10pctRunStd?: number;
  within10pctRunMin?: number;
  within10pctRunMax?: number;
  maeRunMean?: number;
  maeRunStd?: number;
};

export type ProgramStat = {
  variable: string;
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
  mae: number;
  n: number;
  nParsed: number;
  coverage: number;
  accuracy?: number;
  within10pct?: number;
};

export type ScatterEntry = {
  model: string;
  condition: string;
  scenario: string;
  variable: string;
  prediction: number;
  groundTruth: number;
  error: number;
};

export type ScenarioPrediction = {
  prediction: number;
  error: number;
  groundTruth: number;
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
  scenarios: Record<string, BenchScenario>;
  modelStats: ModelStat[];
  programStats: ProgramStat[];
  heatmap: HeatmapEntry[];
  scatter: ScatterEntry[];
  failureModes: FailureModesPayload;
};
