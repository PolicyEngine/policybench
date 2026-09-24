import type { ReferenceExclusion, ScenarioPrediction } from "../types";
import { binaryFlag } from "./scoring";

/**
 * What a model-output cell is evidence of.
 *
 * - "excluded": the output is scored for no model because its reference
 *   depends on an input the household data never carried. The prediction
 *   stays inspectable but is neither right nor wrong for scoring purposes.
 * - "unparsed": the model returned nothing the parser could read.
 * - "correct" / "off": the scored comparison against the frozen reference.
 */
export type PredictionStatus = "excluded" | "unparsed" | "correct" | "off";

export function isExcludedOutput(
  pred: ScenarioPrediction | undefined | null,
): boolean {
  return pred?.scored === false;
}

export function isPredictionCorrect(
  pred: ScenarioPrediction,
  truth: number,
  isBinary: boolean,
): boolean {
  if (pred.prediction === null) return false;
  if (pred.exact !== undefined) return pred.exact >= 100;
  if (pred.thresholdScore !== undefined) return pred.thresholdScore >= 100;
  if (isBinary) {
    const predictionFlag = binaryFlag(pred.prediction);
    const truthFlag = binaryFlag(truth);
    return (
      predictionFlag !== null &&
      truthFlag !== null &&
      predictionFlag === truthFlag
    );
  }
  return (
    Math.abs(pred.prediction - truth) <= Math.abs(truth) * 0.1 ||
    (truth === 0 && Math.abs(pred.prediction) <= 1)
  );
}

export function predictionStatus(
  pred: ScenarioPrediction,
  truth: number,
  isBinary: boolean,
): PredictionStatus {
  if (isExcludedOutput(pred)) return "excluded";
  if (pred.prediction === null) return "unparsed";
  return isPredictionCorrect(pred, truth, isBinary) ? "correct" : "off";
}

/** The exclusion record for one output, if the release carries one. */
export function findReferenceExclusion(
  exclusions: ReferenceExclusion[] | undefined,
  scenarioId: string | null | undefined,
  variable: string,
): ReferenceExclusion | undefined {
  if (!exclusions || !scenarioId) return undefined;
  return exclusions.find(
    (entry) => entry.scenarioId === scenarioId && entry.variable === variable,
  );
}

const EXCLUSION_REASON_LABELS: Record<string, string> = {
  reference_depends_on_unlisted_input:
    "the reference depends on an input the household facts never listed",
  reference_engine_defect:
    "the engine that produced the reference misapplies the law on the stated facts",
  reference_law_published_after_freeze:
    "the reference depends on a figure published after the references were frozen",
};

export function describeExclusionReason(reasonCode?: string): string {
  if (!reasonCode) return EXCLUSION_REASON_LABELS.reference_depends_on_unlisted_input;
  return EXCLUSION_REASON_LABELS[reasonCode] ?? reasonCode.replaceAll("_", " ");
}

// What the frozen reference of an excluded output rests on, as the exclusion
// note above the audit notes describes it.
const EXCLUDED_REFERENCE_BASIS: Record<string, string> = {
  reference_depends_on_unlisted_input:
    "which assumes one reading of the unlisted input described above",
  reference_engine_defect: "which carries the engine defect described above",
  reference_law_published_after_freeze:
    "which uses the engine's projection described above",
};

/**
 * The line shown before the audit note of an excluded output. The audit note
 * compares the answer with the frozen reference, which the exclusion sets
 * aside, so an answer the note calls wrong can be right under the rule the
 * exclusion states.
 */
export function describeExcludedAuditNote(reasonCode?: string): string {
  const basis =
    EXCLUDED_REFERENCE_BASIS[
      reasonCode ?? "reference_depends_on_unlisted_input"
    ] ?? "which the exclusion above sets aside";
  return `This audit note compares the answer with the frozen reference, ${basis}.`;
}
