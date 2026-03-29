import { useMemo } from "react";
import type { BenchData, ModelStat } from "../types";
import {
  MODEL_COLORS,
  MODEL_LABELS,
  UI_COLORS,
  getPerformanceSurfaceColor,
  getPerformanceTextColor,
} from "../modelMeta";

function Badge({
  children,
  variant,
}: {
  children: React.ReactNode;
  variant: "primary" | "warning" | "danger" | "success";
}) {
  const styles = {
    primary: "text-primary bg-primary-soft border-primary/15",
    warning: "text-warning bg-warning-soft border-warning/15",
    danger: "text-danger bg-danger-soft border-danger/15",
    success: "text-success bg-success-soft border-success/15",
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-medium tracking-wide uppercase border ${styles[variant]}`}>
      {children}
    </span>
  );
}

function accColor(pct: number): "success" | "primary" | "warning" | "danger" {
  if (pct >= 80) return "success";
  if (pct >= 65) return "primary";
  if (pct >= 50) return "warning";
  return "danger";
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
      data.modelStats
        .filter((m) => m.condition === "no_tools")
        .sort((a, b) => b.within10pct - a.within10pct),
    [data]
  );
  const leadModel = noTools[0];
  const leadStabilityLabel = fmtRunStability(
    leadModel?.within10pctRunMean,
    leadModel?.within10pctRunStd,
    leadModel?.runCount
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
          const stabilityLabel = fmtRunStability(
            m.within10pctRunMean,
            m.within10pctRunStd,
            m.runCount
          );
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
                  style={{ backgroundColor: MODEL_COLORS[m.model] || UI_COLORS.inactive }}
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
                {stabilityLabel && (
                  <div className="text-[10px] text-text-muted font-[family-name:var(--font-mono)] mt-1">
                    {stabilityLabel}
                  </div>
                )}
              </div>

              {/* No-tools MAE */}
              <div className="col-span-3 text-right font-[family-name:var(--font-mono)] text-sm text-info">
                ${Math.round(m.mae).toLocaleString()}
              </div>
            </div>
          );
        })}
      </div>

      {/* Summary callout */}
      <div className="mt-8 card px-5 py-4 animate-fade-up" style={{ animationDelay: "600ms", borderColor: getPerformanceTextColor(leadModel?.within10pct ?? 0), backgroundColor: getPerformanceSurfaceColor(leadModel?.within10pct ?? 0) }}>
        <p className="text-text-secondary text-sm leading-relaxed">
          <span className="text-primary font-medium">Key finding:</span> The best
          no-tools model
          ({MODEL_LABELS[leadModel?.model ?? ""] || leadModel?.model}) achieves{" "}
          <span className="text-text font-[family-name:var(--font-mono)]">
            {leadModel?.within10pct.toFixed(1)}%
          </span>{" "}
          {leadStabilityLabel && (
            <>
              and across repeated runs averages{" "}
              <span className="text-text font-[family-name:var(--font-mono)]">
                {leadStabilityLabel}
              </span>{" "}
            </>
          )}
          accuracy with an average error of{" "}
          <span className="text-text font-[family-name:var(--font-mono)]">
            ${Math.round(leadModel?.mae || 0).toLocaleString()}
          </span>
          .
        </p>
      </div>
    </div>
  );
}
