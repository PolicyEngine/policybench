import { useState, useMemo } from "react";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import type { BenchData } from "../App";
import { formatDollars } from "../lib/format";
import { MODEL_COLORS, MODEL_LABELS, MODEL_ORDER } from "../modelMeta";

function CustomTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: Record<string, unknown> }> }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-elevated border border-border rounded-lg px-3 py-2 text-xs shadow-lg">
      <div className="text-text font-medium">{MODEL_LABELS[d.model as string] || d.model as string}</div>
      <div className="text-text-muted mt-1">{(d.variable as string).replace(/_/g, " ")}</div>
      <div className="mt-1.5 space-y-0.5">
        <div>
          <span className="text-text-secondary">Predicted:</span>{" "}
          <span className="text-text font-[family-name:var(--font-mono)]">{formatDollars(d.prediction as number)}</span>
        </div>
        <div>
          <span className="text-text-secondary">Actual:</span>{" "}
          <span className="text-text font-[family-name:var(--font-mono)]">{formatDollars(d.groundTruth as number)}</span>
        </div>
        <div>
          <span className="text-text-secondary">Error:</span>{" "}
          <span className="text-coral font-[family-name:var(--font-mono)]">{formatDollars(Math.abs(d.error as number))}</span>
        </div>
      </div>
    </div>
  );
}

export default function ScatterPlot({ data }: { data: BenchData }) {
  const [selectedModels, setSelectedModels] = useState<Set<string>>(
    new Set(MODEL_ORDER)
  );

  const models = useMemo(() => {
    const unique = new Set(
      data.scatter
        .filter((d) => d.condition === "no_tools")
        .map((d) => d.model)
    );
    return MODEL_ORDER.filter((m) => unique.has(m));
  }, [data]);

  const filtered = useMemo(() => {
    const byModel: Record<string, Array<{ prediction: number; groundTruth: number; model: string; variable: string; error: number }>> = {};
    for (const d of data.scatter) {
      if (d.condition !== "no_tools") continue;
      if (!selectedModels.has(d.model)) continue;
      // Skip binary programs that clutter the dollar scatter
      if (d.variable === "is_medicaid_eligible" || d.variable === "free_school_meals") continue;
      if (!byModel[d.model]) byModel[d.model] = [];
      byModel[d.model].push({
        prediction: d.prediction,
        groundTruth: d.groundTruth,
        model: d.model,
        variable: d.variable,
        error: d.error,
      });
    }
    return byModel;
  }, [data, selectedModels]);

  const domain = useMemo(() => {
    let max = 0;
    for (const pts of Object.values(filtered)) {
      for (const p of pts) {
        max = Math.max(max, Math.abs(p.groundTruth), Math.abs(p.prediction));
      }
    }
    return [-max * 0.05, max * 1.05];
  }, [filtered]);

  const toggleModel = (m: string) => {
    setSelectedModels((prev) => {
      const next = new Set(prev);
      if (next.has(m)) next.delete(m);
      else next.add(m);
      return next;
    });
  };

  return (
    <div>
      <div className="eyebrow mb-3 animate-fade-up">Prediction accuracy</div>
      <h2
        className="font-[family-name:var(--font-display)] text-4xl md:text-5xl text-text tracking-tight animate-fade-up"
        style={{ animationDelay: "80ms" }}
      >
        Predicted vs. actual
      </h2>
      <p
        className="text-text-secondary mt-3 max-w-xl leading-relaxed animate-fade-up"
        style={{ animationDelay: "160ms" }}
      >
        Each point is one model&apos;s prediction for a specific household-program
        pair. Points on the diagonal are perfect predictions.
      </p>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-4 mt-8 mb-6">
        <div className="flex gap-2">
          {models.map((m) => (
            <button
              key={m}
              onClick={() => toggleModel(m)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium tracking-wide transition-all border ${
                selectedModels.has(m)
                  ? "border-border bg-card text-text"
                  : "border-transparent bg-transparent text-text-muted"
              }`}
            >
              <span
                className="w-2 h-2 rounded-full"
                style={{
                  backgroundColor: selectedModels.has(m)
                    ? MODEL_COLORS[m]
                    : "#6c6c84",
                }}
              />
              {MODEL_LABELS[m] || m}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div className="card p-4 animate-fade-up" style={{ animationDelay: "240ms" }}>
        <ResponsiveContainer width="100%" height={520}>
          <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
            <XAxis
              type="number"
              dataKey="groundTruth"
              name="Actual"
              domain={domain}
              tickFormatter={formatDollars}
              label={{
                value: "Ground truth",
                position: "bottom",
                offset: 0,
                style: { fill: "#6c6c84", fontSize: 11, fontFamily: "var(--font-mono)" },
              }}
            />
            <YAxis
              type="number"
              dataKey="prediction"
              name="Predicted"
              domain={domain}
              tickFormatter={formatDollars}
              label={{
                value: "Model prediction",
                angle: -90,
                position: "left",
                offset: 0,
                style: { fill: "#6c6c84", fontSize: 11, fontFamily: "var(--font-mono)" },
              }}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine
              segment={[
                { x: domain[0], y: domain[0] },
                { x: domain[1], y: domain[1] },
              ]}
              stroke="#242432"
              strokeDasharray="4 4"
              ifOverflow="extendDomain"
            />
            {models.filter((m) => selectedModels.has(m)).map((m) => (
              <Scatter
                key={m}
                data={filtered[m] || []}
                fill={MODEL_COLORS[m]}
                fillOpacity={0.45}
                r={3}
              />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
