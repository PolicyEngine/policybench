import type { ModelStat } from "../types";

export function rankWithRecomputedScores(
  models: ModelStat[],
  scoresByModel: Map<string, number>,
): ModelStat[] {
  return models
    .filter((model) => scoresByModel.has(model.model))
    .map((model) => ({
      ...model,
      score: scoresByModel.get(model.model)!,
    }))
    .sort((a, b) => b.score - a.score);
}

export function rankWithFallbackScore(
  models: ModelStat[],
  scoreForModel: (model: ModelStat) => number,
): ModelStat[] {
  return models
    .map((model) => ({ ...model, score: scoreForModel(model) }))
    .sort((a, b) => b.score - a.score);
}
