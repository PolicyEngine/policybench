import type { CountryCode, ScenarioPredictionsByVariable } from "../types";
import { programIsActive } from "./programFilters";
import {
  binaryFlag,
  metricTypeForVariable,
  outputGroupForVariable,
} from "./scoring";

/**
 * Pure, React-free implementation of PolicyBench's canonical leaderboard scorer.
 *
 * This is the exact algorithm that used to live inline in
 * `ModelLeaderboard.tsx`. It mirrors the Python canonical scorer in
 * `policybench/analysis.py` (`bounded_global_variable_weights` →
 * `_row_weights_for_ground_truth` → `row_hit_scores`/`bounded_row_score` →
 * household-equal mean): split output-group weights across the concrete rows in
 * each household, renormalize within the household, score each row, average
 * households equally.
 *
 * Equivalence with the Python scorer is enforced in CI through
 * `app/tests/canonicalScore.test.ts`, which replays deterministic vectors whose
 * expected per-model scores were computed by the Python implementation
 * (`policybench export-scorer-vectors`).
 */

export type ScoreField = "exact" | "within1pct" | "continuous";

export type ReferenceFilter = "all" | "positives" | "zeros";

export interface CanonicalScoreInput {
  /** Per-scenario, per-variable, per-model prediction records. */
  scenarioPredictions: Record<string, ScenarioPredictionsByVariable>;
  /**
   * Output-group weights for the active weighting view (one of
   * `globalWeights.household` / `.aggregate` / `.equal`). Keys may be either
   * grouped ids or concrete person-expanded variables; they are re-grouped via
   * {@link outputGroupForVariable} before use, so passing the already-grouped
   * map exported by Python is idempotent.
   */
  weights: Record<string, number> | undefined;
  /** Country, used only to resolve a variable's metric type (amount/binary). */
  country: CountryCode;
  /** Output groups the user has left active in the program filter. */
  activeProgramIds: Set<string>;
  /** Reference-case filter applied per row before scoring. */
  referenceFilter: ReferenceFilter;
  /** Which headline metric to score. */
  field: ScoreField;
}

/**
 * Per-row score for a single (variable, truth, prediction).
 *
 * Mirrors `metricValue` from the original component and the row-level Python
 * scorers:
 * - null / NaN predictions score 0.
 * - binary variables require an exact 0/1 flag match (`row_hit_scores` binary
 *   branch / `binary_flag`).
 * - amounts: `exact` = within 1 absolute unit; `within1pct` = within 1 absolute
 *   unit when the reference is 0, else within 1% relative; `continuous` =
 *   `max(0, 1 - |err| / |ref|)`, with exact-zero handling when the reference is
 *   0 (`continuous_row_score`).
 */
export function metricValue(
  variable: string,
  country: CountryCode,
  truth: number,
  prediction: number | null | undefined,
  field: ScoreField,
): number {
  if (
    prediction === null ||
    prediction === undefined ||
    Number.isNaN(prediction)
  ) {
    return 0;
  }
  const isBinary = metricTypeForVariable(variable, country) === "binary";
  if (isBinary) {
    const predictionFlag = binaryFlag(prediction);
    const truthFlag = binaryFlag(truth);
    return predictionFlag !== null &&
      truthFlag !== null &&
      predictionFlag === truthFlag
      ? 1
      : 0;
  }
  const absErr = Math.abs(prediction - truth);
  const exact = absErr <= 1 ? 1 : 0;
  if (field === "exact") return exact;
  if (field === "within1pct") {
    return truth === 0 ? exact : absErr / Math.abs(truth) <= 0.01 ? 1 : 0;
  }
  return truth === 0
    ? prediction === 0
      ? 1
      : 0
    : Math.max(0, 1 - absErr / Math.abs(truth));
}

/**
 * Compute the canonical per-model score (0–100) from scenario rows.
 *
 * Returns a `Map<model, score>`. A model is only present in the map if at least
 * one household contributed a strictly-positive renormalization denominator for
 * that model; households whose entire kept active set carries zero output-group
 * weight are skipped (the `denominator <= 0` guard), matching the original
 * component behavior.
 */
export function canonicalScoreByModel(input: CanonicalScoreInput): Map<string, number> {
  const { scenarioPredictions, weights, country, activeProgramIds, referenceFilter, field } =
    input;
  const out = new Map<string, number>();
  if (!weights) return out;

  const groupedWeights = new Map<string, number>();
  for (const [variable, weight] of Object.entries(weights)) {
    const group = outputGroupForVariable(variable);
    groupedWeights.set(group, (groupedWeights.get(group) ?? 0) + weight);
  }

  const sums = new Map<string, { score: number; households: number }>();
  for (const variableMap of Object.values(scenarioPredictions ?? {})) {
    const variables = Object.entries(variableMap).filter(
      ([variable, modelMap]) => {
        if (!programIsActive(activeProgramIds, variable)) return false;
        const first = Object.values(modelMap)[0];
        if (!first) return false;
        if (referenceFilter === "positives" && first.groundTruth === 0) {
          return false;
        }
        if (referenceFilter === "zeros" && first.groundTruth !== 0) return false;
        return groupedWeights.has(outputGroupForVariable(variable));
      },
    );
    if (variables.length === 0) continue;

    const groupCounts = new Map<string, number>();
    for (const [variable] of variables) {
      const group = outputGroupForVariable(variable);
      groupCounts.set(group, (groupCounts.get(group) ?? 0) + 1);
    }
    const rawRowWeights = new Map<string, number>();
    let denominator = 0;
    for (const [variable] of variables) {
      const group = outputGroupForVariable(variable);
      const rawWeight =
        (groupedWeights.get(group) ?? 0) / (groupCounts.get(group) ?? 1);
      rawRowWeights.set(variable, rawWeight);
      denominator += rawWeight;
    }
    if (denominator <= 0) continue;

    const models = new Set<string>();
    for (const [, modelMap] of variables) {
      for (const model of Object.keys(modelMap)) models.add(model);
    }
    for (const model of models) {
      let householdScore = 0;
      for (const [variable, modelMap] of variables) {
        const record = modelMap[model];
        const rowWeight = (rawRowWeights.get(variable) ?? 0) / denominator;
        householdScore +=
          rowWeight *
          metricValue(
            variable,
            country,
            record?.groundTruth ?? 0,
            record?.prediction,
            field,
          );
      }
      const acc = sums.get(model) ?? { score: 0, households: 0 };
      acc.score += householdScore;
      acc.households += 1;
      sums.set(model, acc);
    }
  }

  for (const [model, acc] of sums) {
    if (acc.households > 0) out.set(model, (acc.score / acc.households) * 100);
  }
  return out;
}
