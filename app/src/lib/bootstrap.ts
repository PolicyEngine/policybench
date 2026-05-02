import type { CountryCode, ViewKey } from "../types";
import type { ScoreRow } from "./scoring";
import { type SensitivityViewId } from "./sensitivity";

const DEFAULT_DRAWS = 500;

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type ModelScenarioOutputBuckets = Map<
  string, // model
  Map<
    CountryCode,
    Map<
      string, // scenarioId
      Map<string, { sum: number; count: number }> // outputGroup -> sum/count
    >
  >
>;

function bucketize(rows: ScoreRow[]): ModelScenarioOutputBuckets {
  const buckets: ModelScenarioOutputBuckets = new Map();
  for (const row of rows) {
    let countryMap = buckets.get(row.model);
    if (!countryMap) {
      countryMap = new Map();
      buckets.set(row.model, countryMap);
    }
    let scenarioMap = countryMap.get(row.country);
    if (!scenarioMap) {
      scenarioMap = new Map();
      countryMap.set(row.country, scenarioMap);
    }
    let outputMap = scenarioMap.get(row.scenarioId);
    if (!outputMap) {
      outputMap = new Map();
      scenarioMap.set(row.scenarioId, outputMap);
    }
    const cur = outputMap.get(row.outputGroup) ?? { sum: 0, count: 0 };
    cur.sum += row.score * 100;
    cur.count += 1;
    outputMap.set(row.outputGroup, cur);
  }
  return buckets;
}

export type BootstrapInterval = {
  lower: number;
  upper: number;
  rankLower: number;
  rankUpper: number;
};

export function bootstrapIntervals(
  rows: ScoreRow[],
  selectedView: ViewKey,
  filterFn: (row: ScoreRow) => boolean,
  options: { draws?: number; seed?: number } = {},
): Map<string, BootstrapInterval> {
  const draws = options.draws ?? DEFAULT_DRAWS;
  const seed = options.seed ?? 42;
  const filtered = rows.filter(filterFn);
  const buckets = bucketize(filtered);

  // Per-country scenario universe.
  const perCountryScenarios = new Map<CountryCode, string[]>();
  for (const countryMap of buckets.values()) {
    for (const [country, scenarioMap] of countryMap) {
      const list = perCountryScenarios.get(country) ?? [];
      for (const scenarioId of scenarioMap.keys()) {
        if (!list.includes(scenarioId)) list.push(scenarioId);
      }
      perCountryScenarios.set(country, list);
    }
  }
  for (const list of perCountryScenarios.values()) list.sort();

  const countriesToUse: CountryCode[] =
    selectedView === "global"
      ? (["us", "uk"] as CountryCode[]).filter((c) =>
          perCountryScenarios.has(c),
        )
      : [selectedView as CountryCode];

  const models = [...buckets.keys()];
  const rng = mulberry32(seed);

  const drawScores: Record<string, number[]> = {};
  for (const model of models) drawScores[model] = [];
  const rankSamples: Record<string, number[]> = {};
  for (const model of models) rankSamples[model] = [];

  for (let draw = 0; draw < draws; draw += 1) {
    // Sample scenario ids per country with replacement.
    const sampledIds = new Map<CountryCode, string[]>();
    for (const country of countriesToUse) {
      const ids = perCountryScenarios.get(country);
      if (!ids || ids.length === 0) continue;
      const sampled: string[] = [];
      for (let i = 0; i < ids.length; i += 1) {
        sampled.push(ids[Math.floor(rng() * ids.length)]);
      }
      sampledIds.set(country, sampled);
    }

    const scoreThisDraw: Record<string, number> = {};
    for (const model of models) {
      const countryMap = buckets.get(model)!;
      const countryScores: number[] = [];
      for (const country of countriesToUse) {
        const scenarioMap = countryMap.get(country);
        if (!scenarioMap) continue;
        const sampled = sampledIds.get(country) ?? [];
        // Aggregate output-group means across the sampled scenarios.
        const outputBuckets = new Map<string, { sum: number; count: number }>();
        for (const scenarioId of sampled) {
          const outputMap = scenarioMap.get(scenarioId);
          if (!outputMap) continue;
          for (const [outputGroup, v] of outputMap) {
            const cur = outputBuckets.get(outputGroup) ?? {
              sum: 0,
              count: 0,
            };
            // Each scenario contributes its mean for that output_group.
            cur.sum += v.sum / v.count;
            cur.count += 1;
            outputBuckets.set(outputGroup, cur);
          }
        }
        if (outputBuckets.size === 0) continue;
        let totalGroupMean = 0;
        let groupCount = 0;
        for (const v of outputBuckets.values()) {
          if (v.count === 0) continue;
          totalGroupMean += v.sum / v.count;
          groupCount += 1;
        }
        if (groupCount > 0) countryScores.push(totalGroupMean / groupCount);
      }
      if (countryScores.length === countriesToUse.length) {
        scoreThisDraw[model] =
          countryScores.reduce((a, b) => a + b, 0) / countryScores.length;
      }
    }

    const ranked = Object.entries(scoreThisDraw).sort(
      (a, b) => b[1] - a[1],
    );
    for (let i = 0; i < ranked.length; i += 1) {
      const [model, score] = ranked[i];
      drawScores[model].push(score);
      rankSamples[model].push(i + 1);
    }
  }

  const out = new Map<string, BootstrapInterval>();
  for (const model of models) {
    const scores = drawScores[model].sort((a, b) => a - b);
    const ranks = rankSamples[model];
    if (scores.length === 0) continue;
    const lowerIndex = Math.floor(scores.length * 0.025);
    const upperIndex = Math.min(
      scores.length - 1,
      Math.ceil(scores.length * 0.975) - 1,
    );
    out.set(model, {
      lower: scores[lowerIndex],
      upper: scores[upperIndex],
      rankLower: Math.min(...ranks),
      rankUpper: Math.max(...ranks),
    });
  }
  return out;
}

export function viewToFilter(
  view: SensitivityViewId,
): (row: ScoreRow) => boolean {
  switch (view) {
    case "main":
      return () => true;
    case "amount_only":
      return (row) => row.metricType === "amount";
    case "binary_only":
      return (row) => row.metricType === "binary";
    case "positive_only":
      return (row) => row.truth !== 0;
    case "zero_only":
      return (row) => row.truth === 0;
    default:
      return () => true;
  }
}
