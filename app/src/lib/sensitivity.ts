import type {
  BenchData,
  CountryCode,
  DashboardBundle,
  ModelStat,
  ViewKey,
} from "../types";

const GLOBAL_REQUIRED_COUNTRIES: readonly CountryCode[] = ["us", "uk"];
import {
  metricTypeForVariable,
  outputGroupForVariable,
  scorePrediction,
  type ScoreRow,
} from "./scoring";

export type SensitivityViewId = "household" | "aggregate" | "equal";

export type SensitivityView = {
  id: SensitivityViewId;
  label: string;
  description: string;
};

export const SENSITIVITY_VIEWS: SensitivityView[] = [
  {
    id: "household",
    label: "Household",
    description:
      "Population household-impact weights — each output group's share is |ref| / max(|household_net_income|, Σ|ref|) in the full source microsimulation population, averaged with household weights and renormalized before scoring each benchmark household. US weights use the full Enhanced CPS; UK weights use the full enhanced FRS.",
  },
  {
    id: "aggregate",
    label: "Aggregate",
    description:
      "Budget-weighted — each output group's weight is its share of total absolute reference dollars in the full source microsimulation population, renormalized within each benchmark household. One dollar of impact = one dollar.",
  },
  {
    id: "equal",
    label: "Equal",
    description:
      "Equal weighting — each variable in a household contributes the same to that household's score (1/K within each household). One output = one output, regardless of dollar magnitude.",
  },
];

// Keys on each modelStat that hold the per-view score (0–100). The country
// payload exposes ``boundedScore``/``aggregateScore``/``equalScore`` directly;
// the global payload also exposes country-level breakdowns under
// ``boundedCountryScores``/``aggregateCountryScores``/``equalCountryScores``
// for the per-country country selector.
const VIEW_TO_FIELD: Record<SensitivityViewId, keyof ModelStat> = {
  household: "boundedScore",
  aggregate: "aggregateScore",
  equal: "equalScore",
};

const VIEW_TO_COUNTRY_FIELD: Record<SensitivityViewId, keyof ModelStat> = {
  household: "boundedCountryScores",
  aggregate: "aggregateCountryScores",
  equal: "equalCountryScores",
};

export type ScenarioRow = {
  country: CountryCode;
  scenarioId: string;
  outputGroup: string;
  model: string;
  score: number;
};

// Build all per-cell scoring rows. Kept for the bootstrap intervals path —
// the view selector now reads precomputed view scores from the dashboard
// payload instead of re-aggregating row-level scores on the client.
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

export type ModelScore = {
  model: string;
  score: number;
};

function readCountryScore(stat: ModelStat, view: SensitivityViewId): number | undefined {
  const value = stat[VIEW_TO_FIELD[view]];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function readGlobalCountryScores(
  stat: ModelStat,
  view: SensitivityViewId,
): Record<string, number> | undefined {
  const map = stat[VIEW_TO_COUNTRY_FIELD[view]];
  if (!map || typeof map !== "object") return undefined;
  return map as Record<string, number>;
}

/** Returns true if every model in the selected payload exposes a score for this view. */
export function viewSupportsSelected(
  dashboard: DashboardBundle,
  view: SensitivityViewId,
  selectedView: ViewKey,
): boolean {
  if (view === "household") return true;
  const stats = pickModelStats(dashboard, selectedView);
  if (!stats || stats.length === 0) return false;
  return stats.every((stat) => {
    if (selectedView === "global") {
      const countryScores = readGlobalCountryScores(stat, view);
      if (!countryScores) return false;
      return GLOBAL_REQUIRED_COUNTRIES.every(
        (c) => typeof countryScores[c] === "number",
      );
    }
    return readCountryScore(stat, view) !== undefined;
  });
}

function pickModelStats(
  dashboard: DashboardBundle,
  selectedView: ViewKey,
): ModelStat[] | undefined {
  if (selectedView === "global") {
    return dashboard.global?.modelStats?.filter((m) => m.condition === "no_tools");
  }
  return dashboard.countries[selectedView]?.modelStats?.filter(
    (m) => m.condition === "no_tools",
  );
}

export function modelScoresForView(
  dashboard: DashboardBundle,
  view: SensitivityViewId,
  selectedView: ViewKey,
): ModelScore[] {
  const stats = pickModelStats(dashboard, selectedView) ?? [];
  const out: ModelScore[] = [];
  for (const stat of stats) {
    let score: number | undefined;
    if (selectedView === "global") {
      const countryScores = readGlobalCountryScores(stat, view);
      if (countryScores) {
        const values = GLOBAL_REQUIRED_COUNTRIES.map((c) => countryScores[c]).filter(
          (v): v is number => typeof v === "number" && Number.isFinite(v),
        );
        if (values.length === GLOBAL_REQUIRED_COUNTRIES.length) {
          score = values.reduce((a, b) => a + b, 0) / values.length;
        }
      }
    } else {
      score = readCountryScore(stat, view);
    }
    if (score === undefined) continue;
    out.push({ model: stat.model, score });
  }
  return out.sort((a, b) => b.score - a.score);
}
