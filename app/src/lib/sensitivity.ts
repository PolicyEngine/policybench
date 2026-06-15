import type {
  CountryCode,
  DashboardBundle,
  ModelStat,
} from "../types";

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
      "Population household-impact weights — each output group's share is |ref| / max(|household_net_income|, Σ|ref|) in the full weighting population, averaged with household weights and renormalized before scoring each benchmark household. US weights use the full populace dataset; UK weights use the full enhanced FRS. The UK benchmark scenarios themselves still come from the public calibrated transfer dataset.",
  },
  {
    id: "aggregate",
    label: "Aggregate",
    description:
      "Budget-weighted — each output group's weight is its share of total absolute reference dollars in the full weighting population, renormalized within each benchmark household. One dollar of impact = one dollar.",
  },
  {
    id: "equal",
    label: "Equal",
    description:
      "Equal weighting — each variable in a household contributes the same to that household's score (1/K within each household). One output = one output, regardless of dollar magnitude.",
  },
];

// Keys on each modelStat that hold the per-view score (0–100).
const VIEW_TO_FIELD: Record<SensitivityViewId, keyof ModelStat> = {
  household: "boundedScore",
  aggregate: "aggregateScore",
  equal: "equalScore",
};

export type ModelScore = {
  model: string;
  score: number;
};

function readCountryScore(stat: ModelStat, view: SensitivityViewId): number | undefined {
  const value = stat[VIEW_TO_FIELD[view]];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

/** Returns true if every model in the selected payload exposes a score for this view. */
export function viewSupportsSelected(
  dashboard: DashboardBundle,
  view: SensitivityViewId,
  selectedView: CountryCode,
): boolean {
  if (view === "household") return true;
  const stats = pickModelStats(dashboard, selectedView);
  if (!stats || stats.length === 0) return false;
  return stats.every((stat) => readCountryScore(stat, view) !== undefined);
}

function pickModelStats(
  dashboard: DashboardBundle,
  selectedView: CountryCode,
): ModelStat[] | undefined {
  return dashboard.countries[selectedView]?.modelStats?.filter(
    (m) => m.condition === "no_tools",
  );
}

export function modelScoresForView(
  dashboard: DashboardBundle,
  view: SensitivityViewId,
  selectedView: CountryCode,
): ModelScore[] {
  const stats = pickModelStats(dashboard, selectedView) ?? [];
  const out: ModelScore[] = [];
  for (const stat of stats) {
    const score = readCountryScore(stat, view);
    if (score === undefined) continue;
    out.push({ model: stat.model, score });
  }
  return out.sort((a, b) => b.score - a.score);
}
