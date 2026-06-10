import type {
  CountryCode,
  DashboardBundle,
  ScenarioPrediction,
  ScenarioPredictionsByVariable,
} from "../types";

/**
 * Free-text fields account for ~85% of data.json (the agent-written
 * referenceExplanation alone is repeated verbatim for every model on the same
 * scenario-output case). The build splits them into per-country sidecar files
 * served from /data/, which the scenario explorer fetches on demand; every
 * numeric field stays in the bundled summary so rankings, the heatmap, and
 * sensitivity recomputation keep working synchronously.
 */
export const MODEL_TEXT_FIELDS = [
  "explanation",
  "annotation",
  "caseAnnotation",
] as const;

export type ModelTextField = (typeof MODEL_TEXT_FIELDS)[number];

export type ModelExplanation = Partial<Record<ModelTextField, string>>;

export type CaseExplanations = {
  /** Deduplicated referenceExplanation — identical across models per case. */
  reference?: string;
  models?: Record<string, ModelExplanation>;
};

export type ScenarioExplanations = Record<string, CaseExplanations>;

export type ExplanationsFile = {
  country: CountryCode;
  scenarios: Record<string, ScenarioExplanations>;
};

export type SplitDashboard = {
  summary: DashboardBundle;
  explanations: Partial<Record<CountryCode, ExplanationsFile>>;
};

/**
 * Split a full dashboard bundle into a text-free summary (bundled with the
 * app) and per-country explanation sidecars (fetched lazily). Does not mutate
 * the input. Inverse of mergeScenarioExplanations applied per scenario.
 */
export function splitDashboardExplanations(
  bundle: DashboardBundle,
): SplitDashboard {
  const explanations: Partial<Record<CountryCode, ExplanationsFile>> = {};
  const summaryCountries: DashboardBundle["countries"] = {};

  for (const [countryKey, bench] of Object.entries(bundle.countries)) {
    const country = countryKey as CountryCode;
    if (!bench) continue;

    const scenarioTexts: Record<string, ScenarioExplanations> = {};
    const summaryPredictions: Record<string, ScenarioPredictionsByVariable> =
      {};

    for (const [scenarioId, variableMap] of Object.entries(
      bench.scenarioPredictions ?? {},
    )) {
      const caseTexts: ScenarioExplanations = {};
      const summaryVariableMap: ScenarioPredictionsByVariable = {};

      for (const [variable, modelMap] of Object.entries(variableMap)) {
        let reference: string | undefined;
        const models: Record<string, ModelExplanation> = {};
        const summaryModelMap: Record<string, ScenarioPrediction> = {};

        for (const [model, record] of Object.entries(modelMap)) {
          const {
            referenceExplanation,
            explanation,
            annotation,
            caseAnnotation,
            ...numericRecord
          } = record;
          summaryModelMap[model] = numericRecord;

          reference ??= referenceExplanation || undefined;
          const texts: ModelExplanation = {};
          if (explanation) texts.explanation = explanation;
          if (annotation) texts.annotation = annotation;
          if (caseAnnotation) texts.caseAnnotation = caseAnnotation;
          if (Object.keys(texts).length > 0) models[model] = texts;
        }

        summaryVariableMap[variable] = summaryModelMap;
        const caseEntry: CaseExplanations = {};
        if (reference) caseEntry.reference = reference;
        if (Object.keys(models).length > 0) caseEntry.models = models;
        if (Object.keys(caseEntry).length > 0) caseTexts[variable] = caseEntry;
      }

      summaryPredictions[scenarioId] = summaryVariableMap;
      if (Object.keys(caseTexts).length > 0) {
        scenarioTexts[scenarioId] = caseTexts;
      }
    }

    summaryCountries[country] = {
      ...bench,
      scenarioPredictions: summaryPredictions,
    };
    explanations[country] = { country, scenarios: scenarioTexts };
  }

  return { summary: { countries: summaryCountries }, explanations };
}

/**
 * Re-attach lazily fetched explanation text to one scenario's prediction
 * records. Returns the input unchanged (same reference) when there is no
 * text for the scenario, so memoized consumers don't re-render.
 */
export function mergeScenarioExplanations(
  predictions: ScenarioPredictionsByVariable,
  scenarioExplanations: ScenarioExplanations | undefined,
): ScenarioPredictionsByVariable {
  if (!scenarioExplanations) return predictions;

  const merged: ScenarioPredictionsByVariable = {};
  for (const [variable, modelMap] of Object.entries(predictions)) {
    const caseEntry = scenarioExplanations[variable];
    if (!caseEntry) {
      merged[variable] = modelMap;
      continue;
    }
    const mergedModels: Record<string, ScenarioPrediction> = {};
    for (const [model, record] of Object.entries(modelMap)) {
      mergedModels[model] = {
        ...record,
        ...(caseEntry.reference
          ? { referenceExplanation: caseEntry.reference }
          : {}),
        ...caseEntry.models?.[model],
      };
    }
    merged[variable] = mergedModels;
  }
  return merged;
}
