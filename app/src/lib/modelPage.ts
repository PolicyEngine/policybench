/**
 * Server-side selectors for the per-model deep-dive pages (/model/[id]).
 *
 * These run at build time over the bundled summary (no explanation text), so
 * the pages are statically generated and ship no extra client JS.
 */

import type {
  BenchData,
  CountryCode,
  DashboardBundle,
  HeatmapEntry,
  ModelStat,
} from "../types";
import { isBinaryVariable } from "../types";
import { binaryFlag } from "./scoring";

export type ModelCountrySummary = {
  country: CountryCode;
  stat: ModelStat;
  /** Leaderboard position by the headline exact-match metric (1-based). */
  rank: number;
  rankedModels: number;
};

export type ProgramRow = {
  variable: string;
  within1pct: number | null;
  exact: number | null;
  n: number;
};

export type HardCase = {
  scenarioId: string;
  variable: string;
  groundTruth: number;
  prediction: number | null;
  /** Relative error for positive references; null for unparsed predictions. */
  relativeError: number | null;
};

function noToolsStats(bench: BenchData): ModelStat[] {
  return bench.modelStats.filter((row) => row.condition === "no_tools");
}

/** Every model present in any country, in leaderboard order of best score. */
export function listModels(bundle: DashboardBundle): string[] {
  const best = new Map<string, number>();
  for (const bench of Object.values(bundle.countries)) {
    if (!bench) continue;
    for (const row of noToolsStats(bench)) {
      const headline = row.exact ?? row.score;
      best.set(row.model, Math.max(best.get(row.model) ?? -Infinity, headline));
    }
  }
  return [...best.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([model]) => model);
}

export function modelCountrySummaries(
  bundle: DashboardBundle,
  model: string,
): ModelCountrySummary[] {
  const summaries: ModelCountrySummary[] = [];
  for (const [country, bench] of Object.entries(bundle.countries) as [
    CountryCode,
    BenchData | undefined,
  ][]) {
    if (!bench) continue;
    const rows = noToolsStats(bench).sort(
      (a, b) => (b.exact ?? b.score) - (a.exact ?? a.score),
    );
    const index = rows.findIndex((row) => row.model === model);
    if (index === -1) continue;
    summaries.push({
      country,
      stat: rows[index],
      rank: index + 1,
      rankedModels: rows.length,
    });
  }
  return summaries;
}

/** Per-program scores for one model in one country, hardest first. */
export function programRows(bench: BenchData, model: string): ProgramRow[] {
  return bench.heatmap
    .filter(
      (entry: HeatmapEntry) =>
        entry.model === model && entry.condition === "no_tools",
    )
    .map((entry) => ({
      variable: entry.variable,
      within1pct: entry.within1pct ?? null,
      exact: entry.exact ?? null,
      n: entry.n,
    }))
    .sort((a, b) => (a.exact ?? 0) - (b.exact ?? 0));
}

/**
 * The model's worst misses on positive-dollar references, plus unparsed
 * responses. Binary eligibility flags are excluded — a flipped flag has no
 * meaningful error magnitude to rank by.
 */
export function hardestCases(
  bench: BenchData,
  model: string,
  limit = 6,
): HardCase[] {
  const cases: HardCase[] = [];
  for (const [scenarioId, variableMap] of Object.entries(
    bench.scenarioPredictions,
  )) {
    for (const [variable, modelMap] of Object.entries(variableMap)) {
      const record = modelMap[model];
      if (!record) continue;
      if (isBinaryVariable(variable, bench.country)) continue;
      const truth = record.groundTruth;
      if (record.prediction === null || Number.isNaN(record.prediction)) {
        cases.push({
          scenarioId,
          variable,
          groundTruth: truth,
          prediction: null,
          relativeError: null,
        });
        continue;
      }
      if (truth === 0) continue;
      const relativeError = Math.abs(record.prediction - truth) / Math.abs(truth);
      if (relativeError <= 0.01) continue;
      cases.push({
        scenarioId,
        variable,
        groundTruth: truth,
        prediction: record.prediction,
        relativeError,
      });
    }
  }
  return cases
    .sort((a, b) => {
      // Unparsed responses are the worst failure; then by relative error.
      if ((a.relativeError === null) !== (b.relativeError === null)) {
        return a.relativeError === null ? -1 : 1;
      }
      return (b.relativeError ?? 0) - (a.relativeError ?? 0);
    })
    .slice(0, limit);
}

/** Share of binary eligibility flags this model got right, or null if none. */
export function coverageAccuracy(
  bench: BenchData,
  model: string,
): { correct: number; total: number } | null {
  let correct = 0;
  let total = 0;
  for (const variableMap of Object.values(bench.scenarioPredictions)) {
    for (const [variable, modelMap] of Object.entries(variableMap)) {
      if (!isBinaryVariable(variable, bench.country)) continue;
      const record = modelMap[model];
      if (!record) continue;
      total += 1;
      const predictionFlag =
        record.prediction === null ? null : binaryFlag(record.prediction);
      const truthFlag = binaryFlag(record.groundTruth);
      if (
        predictionFlag !== null &&
        truthFlag !== null &&
        predictionFlag === truthFlag
      ) {
        correct += 1;
      }
    }
  }
  return total === 0 ? null : { correct, total };
}
