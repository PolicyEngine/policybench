import { useMemo, useState } from "react";
import { getVariableLabel, type BenchData } from "../types";
import {
  DEFAULT_HEATMAP_METRIC,
  HEATMAP_METRICS,
  heatmapValue,
  type HeatmapMetricId,
} from "../lib/heatmapMetric";
import {
  MODEL_LABELS,
  getPerformanceSurfaceColor,
  getPerformanceTextColor,
  orderModels,
} from "../modelMeta";
import { programIsActive, type ProgramOption } from "../lib/programFilters";
import ProgramFilterDropdown from "./ProgramFilterDropdown";

function cellColor(pct: number): string {
  return getPerformanceSurfaceColor(pct);
}

function textColor(pct: number): string {
  return getPerformanceTextColor(pct);
}

const SCORE_LEGEND = [
  { label: "<50%", score: 45 },
  { label: "50-59%", score: 55 },
  { label: "60-69%", score: 65 },
  { label: "70-79%", score: 75 },
  { label: "80-89%", score: 85 },
  { label: "90%+", score: 95 },
] as const;

export default function ProgramHeatmap({
  data,
  programOptions,
  activeProgramIds,
  activeProgramSummary,
  onResetPrograms,
  onToggleProgram,
  onSelectOnlyProgram,
}: {
  data: BenchData;
  programOptions: ProgramOption[];
  activeProgramIds: Set<string>;
  activeProgramSummary: string;
  onResetPrograms: () => void;
  onToggleProgram: (variable: string) => void;
  onSelectOnlyProgram: (variable: string) => void;
}) {
  const country = data.country;
  const [metric, setMetric] = useState<HeatmapMetricId>(DEFAULT_HEATMAP_METRIC);
  const activeMetric = HEATMAP_METRICS.find((m) => m.id === metric)!;
  const { grid, variables } = useMemo(() => {
    // Build lookup: model+variable → rate under the selected metric
    const lookup: Record<string, number> = {};
    for (const h of data.heatmap) {
      if (h.condition !== "no_tools") continue;
      lookup[`${h.model}|${h.variable}`] = heatmapValue(h, metric);
    }

    // Get unique variables sorted by average score (worst first for impact)
    const varAcc: Record<string, number[]> = {};
    for (const h of data.heatmap) {
      if (h.condition !== "no_tools") continue;
      if (!programIsActive(activeProgramIds, h.variable)) continue;
      if (!varAcc[h.variable]) varAcc[h.variable] = [];
      varAcc[h.variable].push(heatmapValue(h, metric));
    }
    const variables = Object.keys(varAcc).sort((a, b) => {
      const avgA = varAcc[a].reduce((s, v) => s + v, 0) / varAcc[a].length;
      const avgB = varAcc[b].reduce((s, v) => s + v, 0) / varAcc[b].length;
      return avgB - avgA;
    });

    return { grid: lookup, variables };
  }, [activeProgramIds, data, metric]);

  const models = orderModels(
    data.heatmap
      .filter((entry) => entry.condition === "no_tools")
      .map((entry) => entry.model),
  );

  const averageScores = useMemo(() => {
    const averages: Record<string, number> = {};
    for (const variable of variables) {
      const values = models.map((m) => grid[`${m}|${variable}`] ?? 0);
      averages[variable] =
        values.reduce((sum, value) => sum + value, 0) / values.length;
    }
    return averages;
  }, [grid, models, variables]);

  return (
    <div>
      <div className="eyebrow mb-3 animate-fade-up">By program</div>
      <h2
        className="font-[family-name:var(--font-display)] text-4xl md:text-5xl text-text tracking-tight animate-fade-up"
        style={{ animationDelay: "80ms" }}
      >
        Program breakdown
      </h2>
      <p
        className="text-text-secondary mt-3 max-w-xl leading-relaxed animate-fade-up"
        style={{ animationDelay: "160ms" }}
      >
        {activeMetric.label} by program and model (AI alone):{" "}
        {activeMetric.description}. Each cell is that model&apos;s unweighted
        rate on the program&apos;s outputs; the leaderboard weights programs
        by their share of household dollars, so a model&apos;s cells do not
        average to its headline score.
      </p>

      <div
        role="group"
        aria-label="Heatmap metric"
        className="mt-5 inline-flex flex-wrap gap-1 rounded-full border border-border bg-surface p-1 animate-fade-up"
        style={{ animationDelay: "200ms" }}
      >
        {HEATMAP_METRICS.map((option) => (
          <button
            key={option.id}
            type="button"
            aria-pressed={metric === option.id}
            onClick={() => setMetric(option.id)}
            className={`rounded-full px-3 py-1 text-[11px] font-medium uppercase tracking-[0.12em] transition-colors ${
              metric === option.id
                ? "bg-primary-soft text-primary-strong"
                : "text-text-muted hover:text-text"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      <ProgramFilterDropdown
        options={programOptions}
        activeProgramIds={activeProgramIds}
        summary={activeProgramSummary}
        description="Shared with model scoring. The scenario explorer remains unfiltered so each household's full prompt stays visible. The table shows only selected outputs; model scores rescale selected weights to 100%."
        onReset={onResetPrograms}
        onToggle={onToggleProgram}
        onSelectOnly={onSelectOnlyProgram}
        className="mt-6"
        animationDelay="220ms"
      />

      <div
        className="relative mt-8 overflow-x-auto animate-fade-up"
        style={{ animationDelay: "240ms" }}
      >
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-bg text-left text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium pb-3 pl-3 pr-4 w-48 border-r border-border-subtle">
                Program
              </th>
              {models.map((m) => (
                <th
                  key={m}
                  className="text-center text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium pb-3 px-2 w-28"
                >
                  {MODEL_LABELS[m] ?? m}
                </th>
              ))}
              <th className="text-center text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium pb-3 px-2 w-20">
                Avg
              </th>
            </tr>
          </thead>
          <tbody>
            {variables.map((v, vi) => {
              const avg = averageScores[v];
              return (
                <tr key={v} className="border-t border-border-subtle">
                  <td className="sticky left-0 z-10 bg-bg py-2.5 pl-3 pr-4 text-sm text-text-secondary border-r border-border-subtle">
                    {getVariableLabel(v, country)}
                  </td>
                  {models.map((m, mi) => {
                    const pct = grid[`${m}|${v}`] ?? 0;
                    return (
                      <td key={m} className="py-2.5 px-2 text-center">
                        <div
                          className="inline-block px-3 py-1 rounded-md font-[family-name:var(--font-mono)] text-xs font-medium transition-all"
                          style={{
                            backgroundColor: cellColor(pct),
                            color: textColor(pct),
                            animationDelay: `${240 + vi * 40 + mi * 20}ms`,
                          }}
                        >
                          {pct.toFixed(0)}%
                        </div>
                      </td>
                    );
                  })}
                  <td className="py-2.5 px-2 text-center">
                    <span
                      className="font-[family-name:var(--font-mono)] text-xs"
                      style={{ color: textColor(avg) }}
                    >
                      {avg.toFixed(0)}%
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div
        role="list"
        aria-label="Color scale: cells color-code each row's percent rate; the printed percentage in the cell is the source of truth"
        className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 text-[10px] uppercase tracking-[0.14em] text-text-muted"
      >
        <span className="sr-only">
          Cells use color as a redundant cue; the percentage shown in each
          cell is the model&apos;s rate under the selected metric.
        </span>
        {SCORE_LEGEND.map(({ label, score }) => (
          <div key={label} role="listitem" className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="h-3 w-3 rounded"
              style={{ backgroundColor: cellColor(score) }}
            />
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}
