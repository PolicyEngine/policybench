import type { BenchData } from "../types";

function Stat({
  value,
  label,
  accent,
  delay,
}: {
  value: string;
  label: string;
  accent: "primary" | "info" | "warning";
  delay: number;
}) {
  const styles = {
    primary: "text-primary border-primary/15 bg-primary-soft",
    info: "text-info border-info/15 bg-info-soft",
    warning: "text-warning border-warning/15 bg-warning-soft",
  };
  return (
    <div
      className={`border rounded-xl px-5 py-4 ${styles[accent]} animate-fade-up`}
      style={{ animationDelay: `${delay}ms` }}
    >
      <div className="text-2xl font-semibold tracking-tight font-[family-name:var(--font-mono)]">
        {value}
      </div>
      <div className="text-[10px] uppercase tracking-[0.14em] mt-1.5 opacity-60 font-medium">
        {label}
      </div>
    </div>
  );
}

export default function Hero({ data }: { data: BenchData }) {
  const noTools = data.modelStats.filter((m) => m.condition === "no_tools");
  const noToolsPredictions = data.scatter.filter(
    (d) => d.condition === "no_tools"
  );
  const noToolsPrograms = data.programStats.length;
  const bestNoToolsAcc = Math.max(...noTools.map((m) => m.within10pct));

  const avgNoToolsAcc =
    noTools.reduce((s, m) => s + m.within10pct, 0) / noTools.length;
  const avgNoToolsMAE =
    noTools.reduce((s, m) => s + m.mae, 0) / noTools.length;

  return (
    <header className="relative overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-[360px] bg-[radial-gradient(circle_at_top,_color-mix(in_srgb,var(--color-primary)_13%,transparent),transparent_58%)]" />

      <div className="relative max-w-7xl mx-auto px-6 pt-24 pb-16">
        <div className="eyebrow mb-5 animate-fade-up">Benchmark</div>

        <h1
          className="font-[family-name:var(--font-display)] text-6xl md:text-7xl lg:text-8xl text-text leading-[0.92] tracking-tight animate-fade-up"
          style={{ animationDelay: "80ms" }}
        >
          PolicyBench
        </h1>

        <div
          className="mt-5 inline-flex items-center gap-2 rounded-full border border-border bg-bg px-3 py-1.5 text-sm text-text-secondary animate-fade-up"
          style={{ animationDelay: "120ms" }}
        >
          <span>by</span>
          <a href="https://policyengine.org" className="font-semibold text-primary hover:text-primary-strong transition-colors">
            PolicyEngine
          </a>
        </div>

        <p
          className="text-text-secondary text-lg max-w-2xl mt-7 leading-relaxed animate-fade-up"
          style={{ animationDelay: "180ms" }}
        >
          How much household-level policy calculation can frontier models do
          from parametric knowledge alone? This benchmark evaluates{" "}
          {noTools.length} no-tools models on{" "}
          {noToolsPredictions.length.toLocaleString()} predictions across {noToolsPrograms}
          programs and {Object.keys(data.scenarios).length} household scenarios.
        </p>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-12">
          <Stat
            value={`${avgNoToolsAcc.toFixed(1)}%`}
            label="Avg within 10%"
            accent="primary"
            delay={250}
          />
          <Stat
            value={`${bestNoToolsAcc.toFixed(1)}%`}
            label="Best model"
            accent="info"
            delay={350}
          />
          <Stat
            value={`$${Math.round(avgNoToolsMAE).toLocaleString()}`}
            label="Avg error"
            accent="warning"
            delay={450}
          />
          <Stat
            value={String(noTools.length)}
            label="Models benchmarked"
            accent="primary"
            delay={550}
          />
        </div>
      </div>

      <div className="h-px bg-gradient-to-r from-transparent via-primary/25 to-transparent" />
    </header>
  );
}
