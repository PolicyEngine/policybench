import type { HeatmapEntry } from "../types";

/**
 * Which per-program rate the homepage heatmap shows. The board's headline is
 * exact match, so that is the default; the bounded score awards partial
 * credit for close dollar answers and reads higher on the hard tax lines,
 * which is why a 69% exact program can show 93% bounded.
 */
export type HeatmapMetricId = "exact" | "within1pct" | "score";

export type HeatmapMetric = {
  id: HeatmapMetricId;
  label: string;
  description: string;
};

export const HEATMAP_METRICS: HeatmapMetric[] = [
  {
    id: "exact",
    label: "Exact match",
    description:
      "the headline metric: a dollar answer within $1 of the reference, or an eligibility flag that matches",
  },
  {
    id: "within1pct",
    label: "Within 1%",
    description:
      "the near-miss companion: a dollar answer within 1% of the reference, or a matching flag",
  },
  {
    id: "score",
    label: "Bounded score",
    description:
      "partial credit: dollar answers score by relative error, eligibility flags by exact match",
  },
];

export const DEFAULT_HEATMAP_METRIC: HeatmapMetricId = "exact";

/** The entry's rate under the metric, in percent; falls back to the next
 * broader field only for legacy entries that lack it. */
export function heatmapValue(
  entry: HeatmapEntry,
  metric: HeatmapMetricId,
): number {
  if (metric === "exact") return entry.exact ?? entry.score ?? 0;
  if (metric === "within1pct") {
    return entry.within1pct ?? entry.exact ?? entry.score ?? 0;
  }
  return entry.score ?? entry.within10pct ?? entry.accuracy ?? 0;
}
