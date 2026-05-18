import type {
  BenchData,
  DashboardBundle,
  GlobalWeightsByView,
  HeatmapEntry,
  ModelStat,
  ScenarioPredictionsByVariable,
  WeightingKey,
} from "../types";
import {
  metricTypeForVariable,
  outputGroupForVariable,
  scorePrediction,
} from "./scoring";

const EXCLUDED_OUTPUTS = new Set(["premium_tax_credit"]);
const WEIGHTING_KEYS: WeightingKey[] = ["household", "aggregate", "equal"];

function isExcludedOutput(variable: string): boolean {
  return EXCLUDED_OUTPUTS.has(outputGroupForVariable(variable));
}

function scrubPrompt(text?: string): string | undefined {
  return text
    ?.replace(/; exclude the ACA Premium Tax Credit/g, "")
    .replace(
      /\n- premium_tax_credit:[\s\S]*?(?=\n- [a-z0-9_]+:|\n\nUse the `submit_outputs`|$)/g,
      "",
    );
}

function normalizeWeights(weights: Record<string, number>): Record<string, number> {
  const entries = Object.entries(weights).filter(
    ([variable]) => !isExcludedOutput(variable),
  );
  const total = entries.reduce((sum, [, weight]) => sum + weight, 0);
  if (total <= 0) return Object.fromEntries(entries);
  return Object.fromEntries(
    entries.map(([variable, weight]) => [variable, weight / total]),
  );
}

function filterWeights(weights?: GlobalWeightsByView): GlobalWeightsByView | undefined {
  if (!weights) return undefined;
  return Object.fromEntries(
    WEIGHTING_KEYS.map((key) => [key, normalizeWeights(weights[key] ?? {})]),
  ) as GlobalWeightsByView;
}

function groupWeights(weights: Record<string, number>): Record<string, number> {
  const grouped: Record<string, number> = {};
  for (const [variable, weight] of Object.entries(weights)) {
    const group = outputGroupForVariable(variable);
    grouped[group] = (grouped[group] ?? 0) + weight;
  }
  return grouped;
}

function metricHits(
  variable: string,
  truth: number,
  prediction: number | null | undefined,
  country: BenchData["country"],
) {
  const parsed =
    prediction !== null && prediction !== undefined && !Number.isNaN(prediction);
  if (!parsed) {
    return { parsed: false, exact: 0, within1pct: 0, within5pct: 0, within10pct: 0 };
  }
  if (metricTypeForVariable(variable, country) === "binary") {
    const exact = Math.round(prediction) === Math.round(truth) ? 1 : 0;
    return { parsed, exact, within1pct: exact, within5pct: exact, within10pct: exact };
  }
  const absError = Math.abs(prediction - truth);
  const exact = absError <= 1 ? 1 : 0;
  const within = (tolerance: number) =>
    truth === 0 ? exact : absError / Math.abs(truth) <= tolerance ? 1 : 0;
  return {
    parsed,
    exact,
    within1pct: within(0.01),
    within5pct: within(0.05),
    within10pct: within(0.1),
  };
}

function weightedHeatmapScore(
  heatmap: HeatmapEntry[],
  model: string,
  weights: Record<string, number>,
): number | undefined {
  const groupedWeights = groupWeights(weights);
  let numerator = 0;
  let denominator = 0;
  for (const entry of heatmap) {
    if (entry.condition !== "no_tools" || entry.model !== model) continue;
    const weight = groupedWeights[entry.variable];
    if (weight === undefined) continue;
    numerator += weight * (entry.score / 100);
    denominator += weight;
  }
  return denominator > 0 ? (numerator / denominator) * 100 : undefined;
}

function recomputeModelStats(
  payload: BenchData,
  scenarioPredictions: Record<string, ScenarioPredictionsByVariable>,
  heatmap: HeatmapEntry[],
  weights?: GlobalWeightsByView,
): ModelStat[] {
  return payload.modelStats.map((stat) => {
    if (stat.condition !== "no_tools") return stat;

    let n = 0;
    let nParsed = 0;
    let exact = 0;
    let within1pct = 0;
    let within5pct = 0;
    let within10pct = 0;
    let amountN = 0;
    let amountScore = 0;
    let participationN = 0;
    let participationScore = 0;
    let maeN = 0;
    let mae = 0;

    for (const variableMap of Object.values(scenarioPredictions)) {
      for (const [variable, modelMap] of Object.entries(variableMap)) {
        const row = modelMap[stat.model];
        if (!row) continue;
        n += 1;
        const hits = metricHits(
          variable,
          row.groundTruth,
          row.prediction,
          payload.country,
        );
        if (hits.parsed) {
          nParsed += 1;
          mae += Math.abs((row.prediction ?? 0) - row.groundTruth);
          maeN += 1;
        }
        exact += hits.exact;
        within1pct += hits.within1pct;
        within5pct += hits.within5pct;
        within10pct += hits.within10pct;

        if (metricTypeForVariable(variable, payload.country) === "binary") {
          participationN += 1;
          participationScore += hits.exact;
        } else {
          amountN += 1;
          amountScore += scorePrediction(
            variable,
            payload.country,
            row.groundTruth,
            row.prediction,
          );
        }
      }
    }

    const modelHeatmap = heatmap.filter(
      (entry) => entry.condition === "no_tools" && entry.model === stat.model,
    );
    const outputGroupScore =
      modelHeatmap.length > 0
        ? modelHeatmap.reduce((sum, entry) => sum + entry.score, 0) /
          modelHeatmap.length
        : stat.outputGroupScore;
    const boundedScore =
      weights?.household && weightedHeatmapScore(heatmap, stat.model, weights.household);
    const aggregateScore =
      weights?.aggregate && weightedHeatmapScore(heatmap, stat.model, weights.aggregate);
    const equalScore =
      weights?.equal && weightedHeatmapScore(heatmap, stat.model, weights.equal);

    return {
      ...stat,
      score: boundedScore ?? stat.score,
      outputGroupScore,
      exact: n > 0 ? (exact / n) * 100 : stat.exact,
      within1pct: n > 0 ? (within1pct / n) * 100 : stat.within1pct,
      within5pct: n > 0 ? (within5pct / n) * 100 : stat.within5pct,
      within10pct: n > 0 ? (within10pct / n) * 100 : stat.within10pct,
      n,
      nParsed,
      coverage: n > 0 ? (nParsed / n) * 100 : stat.coverage,
      mae: maeN > 0 ? mae / maeN : stat.mae,
      amountAccuracy:
        amountN > 0 ? (amountScore / amountN) * 100 : stat.amountAccuracy,
      participationAccuracy:
        participationN > 0
          ? (participationScore / participationN) * 100
          : stat.participationAccuracy,
      boundedScore: boundedScore ?? stat.boundedScore,
      aggregateScore: aggregateScore ?? stat.aggregateScore,
      equalScore: equalScore ?? stat.equalScore,
    };
  });
}

function filterCountryPayload(payload: BenchData): BenchData {
  const hasExcludedOutput =
    payload.programStats.some((program) => isExcludedOutput(program.variable)) ||
    payload.heatmap.some((entry) => isExcludedOutput(entry.variable)) ||
    Object.values(payload.scenarioPredictions).some((variableMap) =>
      Object.keys(variableMap).some(isExcludedOutput),
    );
  if (!hasExcludedOutput) return payload;

  const scenarios = Object.fromEntries(
    Object.entries(payload.scenarios).map(([scenarioId, scenario]) => [
      scenarioId,
      {
        ...scenario,
        prompt: scenario.prompt
          ? {
              tool: scrubPrompt(scenario.prompt.tool),
              json: scrubPrompt(scenario.prompt.json),
            }
          : undefined,
      },
    ]),
  );
  const scenarioPredictions = Object.fromEntries(
    Object.entries(payload.scenarioPredictions).map(([scenarioId, variableMap]) => [
      scenarioId,
      Object.fromEntries(
        Object.entries(variableMap).filter(
          ([variable]) => !isExcludedOutput(variable),
        ),
      ),
    ]),
  );
  const heatmap = payload.heatmap.filter(
    (entry) => !isExcludedOutput(entry.variable),
  );
  const weights = filterWeights(payload.globalWeights);

  return {
    ...payload,
    scenarios,
    scenarioPredictions,
    programStats: payload.programStats.filter(
      (program) => !isExcludedOutput(program.variable),
    ),
    heatmap,
    globalWeights: weights,
    failureModes: {
      ...payload.failureModes,
      programs: payload.failureModes.programs.filter(
        (program) => !isExcludedOutput(program.variable),
      ),
    },
    modelStats: recomputeModelStats(payload, scenarioPredictions, heatmap, weights),
  };
}

export function filterExcludedOutputs(
  dashboard: DashboardBundle,
): DashboardBundle {
  return {
    ...dashboard,
    countries: Object.fromEntries(
      Object.entries(dashboard.countries).map(([country, payload]) => [
        country,
        payload ? filterCountryPayload(payload) : payload,
      ]),
    ),
  };
}
