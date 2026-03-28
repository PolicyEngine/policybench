import type { BenchData } from "../App";

function Stat({
  value,
  label,
  accent,
  delay,
}: {
  value: string;
  label: string;
  accent: "cyan" | "coral" | "amber";
  delay: number;
}) {
  const styles = {
    cyan: "text-cyan border-cyan/20 bg-cyan-soft",
    coral: "text-coral border-coral/20 bg-coral-soft",
    amber: "text-amber border-amber/20 bg-amber-soft",
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
      {/* Ambient glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[900px] h-[450px] bg-cyan/[0.03] rounded-full blur-[150px]" />

      <div className="relative max-w-7xl mx-auto px-6 pt-24 pb-16">
        <div className="eyebrow mb-5 animate-fade-up">Benchmark</div>

        <h1
          className="font-[family-name:var(--font-display)] text-6xl md:text-7xl lg:text-8xl text-text leading-[0.92] tracking-tight animate-fade-up"
          style={{ animationDelay: "80ms" }}
        >
          Policy<span className="text-cyan">Bench</span>
        </h1>

        <p
          className="text-text-secondary text-lg max-w-2xl mt-7 leading-relaxed animate-fade-up"
          style={{ animationDelay: "160ms" }}
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
            accent="coral"
            delay={250}
          />
          <Stat
            value={`${bestNoToolsAcc.toFixed(1)}%`}
            label="Best model"
            accent="cyan"
            delay={350}
          />
          <Stat
            value={`$${Math.round(avgNoToolsMAE).toLocaleString()}`}
            label="Avg error"
            accent="coral"
            delay={450}
          />
          <Stat
            value={String(noTools.length)}
            label="Models benchmarked"
            accent="amber"
            delay={550}
          />
        </div>
      </div>

      {/* Divider line with glow */}
      <div className="h-px bg-gradient-to-r from-transparent via-cyan/30 to-transparent" />
    </header>
  );
}
