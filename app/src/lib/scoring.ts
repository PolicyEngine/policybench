import { isBinaryVariable, type CountryCode } from "../types";

export type ScoreRow = {
  country: CountryCode;
  scenarioId: string;
  variable: string;
  outputGroup: string;
  model: string;
  truth: number;
  prediction: number | null | undefined;
  metricType: "amount" | "binary";
  score: number;
};

const PERSON_OUTPUT_PREFIXES = [
  "head",
  "spouse",
  "adult1",
  "adult2",
  "adult3",
  "adult4",
  "adult5",
  "child1",
  "child2",
  "child3",
  "child4",
  "child5",
  "dependent1",
  "dependent2",
  "dependent3",
] as const;

const PERSON_OUTPUT_SUFFIXES = [
  "wic",
  "medicaid",
  "chip",
  "medicare",
  "head_start",
  "early_head_start",
] as const;

export function outputGroupForVariable(variable: string): string {
  const match = variable.match(
    /^(head|spouse|adult\d+|child\d+|dependent\d+)_(wic|medicaid|chip|medicare|head_start|early_head_start)_eligible$/,
  );
  if (match) {
    return `person_${match[2]}_eligible`;
  }
  // Already grouped or not a person-expanded variable.
  return variable;
}

export function metricTypeForVariable(
  variable: string,
  country: CountryCode,
): "amount" | "binary" {
  if (isBinaryVariable(variable, country)) return "binary";
  const match = variable.match(
    /^(head|spouse|adult\d+|child\d+|dependent\d+)_(wic|medicaid|chip|medicare|head_start|early_head_start)_eligible$/,
  );
  if (match) return "binary";
  return "amount";
}

function within(truth: number, prediction: number, tolerance: number): number {
  if (truth === 0) {
    return Math.abs(prediction) <= 1.0 ? 1 : 0;
  }
  return Math.abs(prediction - truth) / Math.abs(truth) <= tolerance ? 1 : 0;
}

function exactAmount(truth: number, prediction: number): number {
  return Math.abs(prediction - truth) <= 1.0 ? 1 : 0;
}

export function scorePrediction(
  variable: string,
  country: CountryCode,
  truth: number,
  prediction: number | null | undefined,
): number {
  if (prediction === null || prediction === undefined || Number.isNaN(prediction)) {
    return 0;
  }
  const metricType = metricTypeForVariable(variable, country);
  if (metricType === "binary") {
    return Math.round(prediction) === Math.round(truth) ? 1 : 0;
  }
  const exact = exactAmount(truth, prediction);
  const w1 = within(truth, prediction, 0.01);
  const w5 = within(truth, prediction, 0.05);
  const w10 = within(truth, prediction, 0.1);
  return (exact + w1 + w5 + w10) / 4;
}

// Touch the prefix/suffix tables so a future test can verify coverage.
export const PERSON_OUTPUT_PREFIX_LIST: readonly string[] =
  PERSON_OUTPUT_PREFIXES;
export const PERSON_OUTPUT_SUFFIX_LIST: readonly string[] =
  PERSON_OUTPUT_SUFFIXES;
