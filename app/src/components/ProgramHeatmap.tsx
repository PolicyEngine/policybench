import { useMemo } from "react";
import { getVariableLabel, type BenchData, type HeatmapEntry } from "../types";
import {
  MODEL_LABELS,
  MODEL_ORDER,
  getPerformanceSurfaceColor,
  getPerformanceTextColor,
} from "../modelMeta";

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
    data.heatmap.some((h) => h.condition === "no_tools" && h.model === m)
  );

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
        household booleans use exact accuracy.
      </p>

      <div className="mt-10 overflow-x-auto animate-fade-up" style={{ animationDelay: "240ms" }}>
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="text-left text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium pb-3 pr-4 w-48">
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
              const values = models.map((m) => grid[`${m}|${v}`] ?? 0);
              const avg = values.reduce((s, x) => s + x, 0) / values.length;
              return (
                <tr
                  key={v}
                  className="border-t border-border-subtle"
                >
                  <td className="py-2.5 pr-4 text-sm text-text-secondary">
                    {getVariableLabel(v)}
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
          <span className="w-3 h-3 rounded" style={{ backgroundColor: cellColor(40) }} />
          &lt;50%
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded" style={{ backgroundColor: cellColor(60) }} />
          50–70%
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded" style={{ backgroundColor: cellColor(75) }} />
          70–80%
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded" style={{ backgroundColor: cellColor(92) }} />
          90%+
        </div>
      </div>
    </div>
  );
}
