import type { BenchData } from "../types";
import { programRows, type ProgramRow } from "./modelPage";
import { outputGroupForVariable } from "./scoring";

export type ProgramBar = ProgramRow & {
  /** The program's share of the headline weighting (0–1), or null when the
   * payload carries no household weights. */
  weightShare: number | null;
};

/**
 * One bar per output group for a model, descending by exact-match rate, with
 * each program's share of the headline weight so a reader can see why the
 * unweighted rates do not average to the headline: the dollar-heavy tax lines
 * carry most of the weight and are where models miss most.
 */
export function programBars(bench: BenchData, model: string): ProgramBar[] {
  const weights = bench.globalWeights?.household;
  const byGroup: Record<string, number> = {};
  let total = 0;
  if (weights) {
    for (const [variable, weight] of Object.entries(weights)) {
      const group = outputGroupForVariable(variable);
      byGroup[group] = (byGroup[group] ?? 0) + weight;
      total += weight;
    }
  }
  return programRows(bench, model)
    .map((row) => ({
      ...row,
      weightShare:
        weights && total > 0 ? (byGroup[row.variable] ?? 0) / total : null,
    }))
    .sort((a, b) => (b.exact ?? 0) - (a.exact ?? 0));
}

export function formatShare(share: number | null): string {
  if (share == null) return "";
  const pct = share * 100;
  return pct >= 10 ? `${pct.toFixed(0)}%` : `${pct.toFixed(1)}%`;
}
