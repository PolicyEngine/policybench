import type { BenchData } from "../types";

export const AUDIT_SELECTION_RULE =
  "rows whose legacy threshold score is below 1";

export type AuditUniverseSummary = {
  annotatedRowCount: number;
  legacyThresholdRowCount: number;
  exactMissCount: number;
  annotatedExactMissCount: number;
  annotatedExactHitCount: number;
  unannotatedBelowFullBoundedScoreCount: number;
};

/** Recompute the audit universe from the metrics and annotations in a bundle. */
export function summarizeAuditUniverse(data: BenchData): AuditUniverseSummary {
  let annotatedRowCount = 0;
  let legacyThresholdRowCount = 0;
  let exactMissCount = 0;
  let annotatedExactMissCount = 0;
  let annotatedExactHitCount = 0;
  let unannotatedBelowFullBoundedScoreCount = 0;
  let annotationSelectionMismatches = 0;

  for (const variableMap of Object.values(data.scenarioPredictions)) {
    for (const modelMap of Object.values(variableMap)) {
      for (const row of Object.values(modelMap)) {
        const annotated = row.failureSource !== undefined;
        const legacyThresholdSelected =
          row.thresholdScore !== undefined && row.thresholdScore < 100;
        const exactMiss = row.exact !== undefined && row.exact < 100;
        const belowFullBoundedScore =
          row.boundedScore !== undefined && row.boundedScore < 100;

        annotatedRowCount += Number(annotated);
        legacyThresholdRowCount += Number(legacyThresholdSelected);
        exactMissCount += Number(exactMiss);
        annotatedExactMissCount += Number(annotated && exactMiss);
        annotatedExactHitCount += Number(annotated && !exactMiss);
        unannotatedBelowFullBoundedScoreCount += Number(
          !annotated && belowFullBoundedScore,
        );
        annotationSelectionMismatches += Number(
          annotated !== legacyThresholdSelected,
        );
      }
    }
  }

  if (annotationSelectionMismatches !== 0) {
    throw new Error(
      `Audit annotations differ from the legacy-threshold selection on ${annotationSelectionMismatches.toLocaleString()} rows`,
    );
  }

  return {
    annotatedRowCount,
    legacyThresholdRowCount,
    exactMissCount,
    annotatedExactMissCount,
    annotatedExactHitCount,
    unannotatedBelowFullBoundedScoreCount,
  };
}
