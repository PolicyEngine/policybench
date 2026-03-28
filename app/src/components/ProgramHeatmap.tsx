import { useMemo } from "react";
import type { BenchData } from "../App";
import { MODEL_LABELS, MODEL_ORDER } from "../modelMeta";

const VARIABLE_LABELS: Record<string, string> = {
  income_tax: "Income tax",
  income_tax_before_refundable_credits: "Tax (pre-refundable)",
  income_tax_refundable_credits: "Refundable credits",
  eitc: "EITC",
  ctc: "CTC",
  snap: "SNAP",
  ssi: "SSI",
  free_school_meals: "Free school meals",
  is_medicaid_eligible: "Medicaid eligible",
  household_state_income_tax: "State income tax",
};

function cellColor(pct: number): string {
  // Dark-theme heat: low → deep red, mid → amber, high → green
  if (pct >= 90) return "rgba(0, 255, 136, 0.25)";
  if (pct >= 80) return "rgba(0, 255, 136, 0.15)";
  if (pct >= 70) return "rgba(0, 212, 255, 0.15)";
  if (pct >= 60) return "rgba(255, 170, 0, 0.15)";
  if (pct >= 50) return "rgba(255, 170, 0, 0.10)";
  return "rgba(255, 68, 102, 0.15)";
}

function textColor(pct: number): string {
  if (pct >= 90) return "#00ff88";
  if (pct >= 80) return "#40e8ff";
  if (pct >= 70) return "#00d4ff";
  if (pct >= 60) return "#ffaa00";
  if (pct >= 50) return "#ffaa00";
  return "#ff4466";
}

export default function ProgramHeatmap({ data }: { data: BenchData }) {
  const { grid, variables } = useMemo(() => {
    // Build lookup: model+variable → accuracy (some entries use "accuracy", others "within10pct")
    const lookup: Record<string, number> = {};
    for (const h of data.heatmap) {
      if (h.condition !== "no_tools") continue;
      const acc = (h as Record<string, unknown>).within10pct ?? (h as Record<string, unknown>).accuracy ?? 0;
      lookup[`${h.model}|${h.variable}`] = acc as number;
    }

    // Get unique variables sorted by average accuracy (worst first for impact)
    const varAcc: Record<string, number[]> = {};
    for (const h of data.heatmap) {
      if (h.condition !== "no_tools") continue;
      const acc = (h as Record<string, unknown>).within10pct ?? (h as Record<string, unknown>).accuracy ?? 0;
      if (!varAcc[h.variable]) varAcc[h.variable] = [];
      varAcc[h.variable].push(acc as number);
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
        Accuracy by program and model (AI alone, without tools). Each cell shows the
        percentage of predictions within 10% of the true value.
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
                    {VARIABLE_LABELS[v] || v.replace(/_/g, " ")}
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
          <span className="w-3 h-3 rounded" style={{ backgroundColor: "rgba(255, 68, 102, 0.15)" }} />
          &lt;50%
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded" style={{ backgroundColor: "rgba(255, 170, 0, 0.15)" }} />
          50–70%
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded" style={{ backgroundColor: "rgba(0, 212, 255, 0.15)" }} />
          70–80%
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded" style={{ backgroundColor: "rgba(0, 255, 136, 0.25)" }} />
          90%+
        </div>
      </div>
    </div>
  );
}
