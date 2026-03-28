import { useMemo } from "react";
import type { BenchData } from "../App";
import { MODEL_COLORS, MODEL_LABELS } from "../modelMeta";

type ModelStat = BenchData["modelStats"][number] & {
  runCount?: number;
  within10pctRunMean?: number;
  within10pctRunStd?: number;
};

function Badge({ children, variant }: { children: React.ReactNode; variant: "cyan" | "coral" | "amber" | "green" }) {
  const styles = {
    cyan: "text-cyan bg-cyan-soft border-cyan/20",
    coral: "text-coral bg-coral-soft border-coral/20",
    amber: "text-amber bg-amber-soft border-amber/20",
    green: "text-green bg-green-soft border-green/20",
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-medium tracking-wide uppercase border ${styles[variant]}`}>
      {children}
    </span>
  );
}

function accColor(pct: number): "green" | "cyan" | "amber" | "coral" {
  if (pct >= 80) return "green";
  if (pct >= 65) return "cyan";
  if (pct >= 50) return "amber";
  return "coral";
}

function fmtRunStability(
  mean?: number,
  std?: number,
  runCount?: number
): string | null {
  if (runCount == null || runCount <= 1 || mean == null || Number.isNaN(mean)) {
    return null;
  }
  const meanLabel = `${mean.toFixed(1)}%`;
  if (std == null || Number.isNaN(std)) {
    return `${meanLabel} over ${runCount} runs`;
  }
  return `${meanLabel} +/- ${std.toFixed(1)} over ${runCount} runs`;
}

export default function ModelLeaderboard({ data }: { data: BenchData }) {
  const noTools = useMemo<ModelStat[]>(
    () =>
      (data.modelStats as ModelStat[])
        .filter((m) => m.condition === "no_tools")
        .sort((a, b) => b.within10pct - a.within10pct),
    [data]
  );

  return (
    <div>
      <div className="eyebrow mb-3 animate-fade-up">Leaderboard</div>
      <h2
        className="font-[family-name:var(--font-display)] text-4xl md:text-5xl text-text tracking-tight animate-fade-up"
        style={{ animationDelay: "80ms" }}
      >
        Model rankings
      </h2>
      <p
        className="text-text-secondary mt-3 max-w-xl leading-relaxed animate-fade-up"
        style={{ animationDelay: "160ms" }}
      >
        Models ranked by share of predictions within 10% of ground truth in the
        no-tools condition.
      </p>

      <div className="mt-10 space-y-3">
        {/* Header */}
        <div className="grid grid-cols-12 gap-3 px-4 text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
          <div className="col-span-1">#</div>
          <div className="col-span-5">Model</div>
          <div className="col-span-3 text-right">Within 10%</div>
          <div className="col-span-3 text-right">MAE</div>
        </div>

        {noTools.map((m, i) => {
          return (
            <div
              key={m.model}
              className="card card-hover grid grid-cols-12 gap-3 items-center px-4 py-4 animate-fade-up"
              style={{ animationDelay: `${240 + i * 80}ms` }}
            >
              {/* Rank */}
              <div className="col-span-1">
                <span className="text-text-muted font-[family-name:var(--font-mono)] text-sm">
                  {i + 1}
                </span>
              </div>

              {/* Model name */}
              <div className="col-span-5 flex items-center gap-2.5">
                <span
                  className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: MODEL_COLORS[m.model] || "#6c6c84" }}
                />
                <span className="text-text font-medium text-sm">
                  {MODEL_LABELS[m.model] || m.model}
                </span>
              </div>

              {/* No-tools accuracy */}
              <div className="col-span-3 text-right">
                <Badge variant={accColor(m.within10pct)}>
                  {m.within10pct.toFixed(1)}%
                </Badge>
                {fmtRunStability(
                  m.within10pctRunMean,
                  m.within10pctRunStd,
                  m.runCount
                ) && (
                  <div className="text-[10px] text-text-muted font-[family-name:var(--font-mono)] mt-1">
                    {fmtRunStability(
                      m.within10pctRunMean,
                      m.within10pctRunStd,
                      m.runCount
                    )}
                  </div>
                )}
              </div>

              {/* No-tools MAE */}
              <div className="col-span-3 text-right font-[family-name:var(--font-mono)] text-sm text-coral">
                ${Math.round(m.mae).toLocaleString()}
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary callout */}
      <div className="mt-8 card px-5 py-4 border-cyan/20 bg-cyan-soft/30 animate-fade-up" style={{ animationDelay: "600ms" }}>
        <p className="text-text-secondary text-sm leading-relaxed">
          <span className="text-cyan font-medium">Key finding:</span> The best
          no-tools model
          ({MODEL_LABELS[noTools[0]?.model] || noTools[0]?.model}) achieves{" "}
          <span className="text-text font-[family-name:var(--font-mono)]">
            {noTools[0]?.within10pct.toFixed(1)}%
          </span>{" "}
          {fmtRunStability(
            noTools[0]?.within10pctRunMean,
            noTools[0]?.within10pctRunStd,
            noTools[0]?.runCount
          ) && (
            <>
              and across repeated runs averages{" "}
              <span className="text-text font-[family-name:var(--font-mono)]">
                {fmtRunStability(
                  noTools[0]?.within10pctRunMean,
                  noTools[0]?.within10pctRunStd,
                  noTools[0]?.runCount
                )}
              </span>{" "}
            </>
          )}
          accuracy with an average error of{" "}
          <span className="text-text font-[family-name:var(--font-mono)]">
            ${Math.round(noTools[0]?.mae || 0).toLocaleString()}
          </span>
          .
        </p>
      </div>
    </div>
  );
}
