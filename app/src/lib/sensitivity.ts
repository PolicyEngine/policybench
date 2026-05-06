import type {
  BenchData,
  CountryCode,
  DashboardBundle,
  ViewKey,
} from "../types";

const GLOBAL_REQUIRED_COUNTRIES: readonly CountryCode[] = ["us", "uk"];
import {
  metricTypeForVariable,
  outputGroupForVariable,
  scorePrediction,
  type ScoreRow,
} from "./scoring";

export type SensitivityViewId =
  | "main"
  | "amount_only"
  | "binary_only"
  | "positive_only"
  | "zero_only";

export type SensitivityView = {
  id: SensitivityViewId;
  label: string;
  description: string;
};

export const SENSITIVITY_VIEWS: SensitivityView[] = [
  {
    id: "main",
    label: "Main",
    description: "Equal-weight average across output groups; baseline ranking.",
  },
  {
    id: "amount_only",
    label: "Amount only",
    description: "Drops binary coverage flags; ranks on amount outputs only.",
  },
  {
    id: "binary_only",
    label: "Binary only",
    description: "Restricts to binary coverage outputs.",
  },
  {
    id: "positive_only",
    label: "Positive cases",
    description: "Restricts to rows where the reference value is non-zero.",
  },
  {
    id: "zero_only",
    label: "Zero cases",
    description: "Restricts to rows where the reference value is zero.",
  },
];

export type ScenarioRow = {
  country: CountryCode;
  scenarioId: string;
  outputGroup: string;
  model: string;
  score: number;
};

function buildRows(country: CountryCode, payload: BenchData): ScoreRow[] {
  const rows: ScoreRow[] = [];
  for (const [scenarioId, variableMap] of Object.entries(
    payload.scenarioPredictions,
  )) {
    for (const [variable, modelMap] of Object.entries(variableMap)) {
      const outputGroup = outputGroupForVariable(variable);
      const metricType = metricTypeForVariable(variable, country);
      for (const [model, record] of Object.entries(modelMap)) {
        rows.push({
          country,
          scenarioId,
          variable,
          outputGroup,
          model,
          truth: record.groundTruth,
          prediction: record.prediction,
          metricType,
          score: scorePrediction(
            variable,
            country,
            record.groundTruth,
            record.prediction,
          ),
        });
      }
    }
  }
  return rows;
}

export function buildAllRows(dashboard: DashboardBundle): ScoreRow[] {
  const rows: ScoreRow[] = [];
  for (const country of ["us", "uk"] as CountryCode[]) {
    const payload = dashboard.countries[country];
    if (!payload) continue;
    rows.push(...buildRows(country, payload));
  }
  return rows;
}

function filterRows(rows: ScoreRow[], view: SensitivityViewId): ScoreRow[] {
  switch (view) {
    case "main":
      return rows;
    case "amount_only":
      return rows.filter((row) => row.metricType === "amount");
    case "binary_only":
      return rows.filter((row) => row.metricType === "binary");
    case "positive_only":
      return rows.filter((row) => row.truth !== 0);
    case "zero_only":
      return rows.filter((row) => row.truth === 0);
    default:
      return rows;
  }
}

function aggregateGroupMean<T>(
  rows: T[],
  key: (row: T) => string,
  value: (row: T) => number,
): Record<string, number> {
  const sums = new Map<string, { sum: number; count: number }>();
  for (const row of rows) {
    const k = key(row);
    const v = value(row);
    if (!Number.isFinite(v)) continue;
    const cur = sums.get(k) ?? { sum: 0, count: 0 };
    cur.sum += v;
    cur.count += 1;
    sums.set(k, cur);
  }
  const out: Record<string, number> = {};
  for (const [k, { sum, count }] of sums) {
    if (count > 0) out[k] = sum / count;
  }
  return out;
}

export type ModelScore = {
  model: string;
  score: number;
};

function scoresPerCountryModel(rows: ScoreRow[]): Map<
  string,
  Map<string, number>
> {
  // First reduce to (country, model, output_group) means.
  const groupKey = (row: ScoreRow) =>
    `${row.country}|${row.model}|${row.outputGroup}`;
  const outputMeans = aggregateGroupMean(rows, groupKey, (row) => row.score * 100);
  // Then average the output groups by (country, model).
  const buckets = new Map<string, { sum: number; count: number }>();
  for (const [k, mean] of Object.entries(outputMeans)) {
    const [country, model] = k.split("|");
    const bk = `${country}|${model}`;
    const cur = buckets.get(bk) ?? { sum: 0, count: 0 };
    cur.sum += mean;
    cur.count += 1;
    buckets.set(bk, cur);
  }
  // Reshape into Map<country, Map<model, score>>.
  const out = new Map<string, Map<string, number>>();
  for (const [bk, { sum, count }] of buckets) {
    if (count === 0) continue;
    const [country, model] = bk.split("|");
    if (!out.has(country)) out.set(country, new Map());
    out.get(country)!.set(model, sum / count);
  }
  return out;
}

/** Returns true if the active sensitivity slice has rows for every required country. */
export function viewSupportsGlobal(
  rows: ScoreRow[],
  view: SensitivityViewId,
): boolean {
  const filtered = filterRows(rows, view);
  const present = new Set<CountryCode>();
  for (const row of filtered) present.add(row.country);
  return GLOBAL_REQUIRED_COUNTRIES.every((c) => present.has(c));
}

export function modelScoresForView(
  rows: ScoreRow[],
  view: SensitivityViewId,
  selectedView: ViewKey,
): ModelScore[] {
  const filtered = filterRows(rows, view);
  const perCountry = scoresPerCountryModel(filtered);
  if (selectedView === "global") {
    // Global score requires every required country to have rows under the
    // active sensitivity slice. If any required country is missing (e.g.
    // "Binary only" with no UK binary outputs), surface no rows so the
    // leaderboard component can suppress or relabel the global view.
    const haveAllRequired = GLOBAL_REQUIRED_COUNTRIES.every((c) =>
      perCountry.has(c),
    );
    if (!haveAllRequired) return [];

    const allModels = new Set<string>();
    for (const c of GLOBAL_REQUIRED_COUNTRIES) {
      for (const m of perCountry.get(c)?.keys() ?? []) allModels.add(m);
    }
    const out: ModelScore[] = [];
    for (const model of allModels) {
      const present: number[] = [];
      for (const c of GLOBAL_REQUIRED_COUNTRIES) {
        const s = perCountry.get(c)?.get(model);
        if (s !== undefined && Number.isFinite(s)) present.push(s);
      }
      if (present.length === GLOBAL_REQUIRED_COUNTRIES.length) {
        out.push({
          model,
          score: present.reduce((a, b) => a + b, 0) / present.length,
        });
      }
    }
    return out.sort((a, b) => b.score - a.score);
  }
  const map = perCountry.get(selectedView);
  if (!map) return [];
  return [...map.entries()]
    .map(([model, score]) => ({ model, score }))
    .sort((a, b) => b.score - a.score);
}
