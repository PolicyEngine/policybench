import { useMemo } from "react";
import { getVariableLabel, type BenchData, type HeatmapEntry } from "../types";
import {
  MODEL_LABELS,
  MODEL_ORDER,
  getPerformanceSurfaceColor,
  getPerformanceTextColor,
} from "../modelMeta";
import { getVariableExplainer } from "../variableExplainers";

function getHeatmapScore(entry: HeatmapEntry): number {
  return entry.score ?? entry.within10pct ?? entry.accuracy ?? 0;
}

function cellColor(pct: number): string {
  return getPerformanceSurfaceColor(pct);
}

function textColor(pct: number): string {
  return getPerformanceTextColor(pct);
}

export default function ProgramHeatmap({ data }: { data: BenchData }) {
  const country = data.country;
  const { grid, variables } = useMemo(() => {
    // Build lookup: model+variable → bounded score
    const lookup: Record<string, number> = {};
    for (const h of data.heatmap) {
      if (h.condition !== "no_tools") continue;
      lookup[`${h.model}|${h.variable}`] = getHeatmapScore(h);
    }

    // Get unique variables sorted by average score (worst first for impact)
    const varAcc: Record<string, number[]> = {};
    for (const h of data.heatmap) {
      if (h.condition !== "no_tools") continue;
      if (!varAcc[h.variable]) varAcc[h.variable] = [];
      varAcc[h.variable].push(getHeatmapScore(h));
    }
    const variables = Object.keys(varAcc).sort((a, b) => {
      const avgA = varAcc[a].reduce((s, v) => s + v, 0) / varAcc[a].length;
      const avgB = varAcc[b].reduce((s, v) => s + v, 0) / varAcc[b].length;
      return avgB - avgA;
    });

    return { grid: lookup, variables };
  }, [data]);

  const models = MODEL_ORDER.filter((m) =>
    data.heatmap.some((h) => h.condition === "no_tools" && h.model === m),
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
        Bounded score by program and model (AI alone, without tools). Dollar
        targets average exact, within-1%, within-5%, and within-10% hit rates;
        binary coverage flags use exact accuracy.
      </p>

      <div
        className="relative mt-10 overflow-x-auto animate-fade-up"
        style={{ animationDelay: "240ms" }}
      >
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-bg text-left text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium pb-3 pr-4 w-48 border-r border-border-subtle">
                Program
              </th>
              {models.map((m) => (
                <th
                  key={m}
                  className="text-center text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium pb-3 px-2 w-28"
                >
                  {MODEL_LABELS[m]}
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
                  <td className="sticky left-0 z-10 bg-bg py-2.5 pr-4 text-sm text-text-secondary border-r border-border-subtle">
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

      {/* Legend */}
      <div className="flex items-center gap-6 mt-6 text-[10px] uppercase tracking-[0.14em] text-text-muted">
        <div className="flex items-center gap-1.5">
          <span
            className="w-3 h-3 rounded"
            style={{ backgroundColor: cellColor(40) }}
          />
          &lt;50%
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className="w-3 h-3 rounded"
            style={{ backgroundColor: cellColor(60) }}
          />
          50–70%
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className="w-3 h-3 rounded"
            style={{ backgroundColor: cellColor(75) }}
          />
          70–80%
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className="w-3 h-3 rounded"
            style={{ backgroundColor: cellColor(92) }}
          />
          90%+
        </div>
      </div>

      <div className="mt-10">
        <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
          What the diagnostics show
        </div>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-text-secondary">
          These expanders summarize recurring miss patterns from direct reads of
          the diagnostic rows, paired with the benchmark scores above. They are
          intentionally narrower than the leaderboard summaries: the goal is to
          say what the diagnostic evidence supports, not more.
        </p>

        <div className="mt-5 space-y-3">
          {variables.map((variable) => {
            const explainer = getVariableExplainer(country, variable);
            const avg = averageScores[variable];
            return (
              <details
                key={variable}
                className="card px-5 py-4 open:border-primary/30"
              >
                <summary className="flex cursor-pointer list-none items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="text-text text-sm font-medium">
                      {getVariableLabel(variable, country)}
                    </div>
                    <p className="mt-1 text-sm leading-relaxed text-text-secondary">
                      {explainer?.summary ??
                        "This target combines multiple policy rules, and errors usually come from positive cases rather than zero cases."}
                    </p>
                  </div>
                  <div className="shrink-0 rounded-full border border-border bg-surface px-3 py-1 text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
                    Avg {avg.toFixed(0)}%
                  </div>
                </summary>

                <div className="mt-4 border-t border-border-subtle pt-4">
                  <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
                    Common misses
                  </div>
                  <ul className="mt-3 space-y-2 text-sm leading-relaxed text-text-secondary">
                    {(explainer?.bullets ?? []).map((bullet) => (
                      <li key={bullet} className="flex gap-2">
                        <span className="mt-[0.45rem] h-1.5 w-1.5 shrink-0 rounded-full bg-primary/70" />
                        <span>{bullet}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </details>
            );
          })}
        </div>
      </div>
    </div>
  );
}
