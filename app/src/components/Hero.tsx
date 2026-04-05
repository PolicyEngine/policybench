/* eslint-disable @next/next/no-img-element */
import { MODEL_LABELS } from "../modelMeta";
import type {
  BenchData,
  DashboardBundle,
  GlobalBenchData,
  ViewKey,
} from "../types";
import { VIEW_LABELS } from "../types";

export function ViewSelector({
  selectedView,
  onSelect,
  className = "",
  pillClassName = "",
}: {
  selectedView: ViewKey;
  onSelect: (view: ViewKey) => void;
  className?: string;
  pillClassName?: string;
}) {
  const views: ViewKey[] = ["global", "us", "uk"];
  const defaultPill =
    "rounded-full px-3 py-1.5 text-xs font-medium transition-colors sm:px-4";
  const pill = pillClassName || defaultPill;
  return (
    <div
      className={`inline-flex max-w-full items-center gap-1 rounded-full border border-border bg-bg/80 p-1 ${className}`}
    >
      {views.map((view) => (
        <button
          key={view}
          type="button"
          onClick={() => onSelect(view)}
          className={`${pill} ${
            selectedView === view
              ? "bg-primary text-void"
              : "text-text-secondary hover:text-text"
          }`}
        >
          {VIEW_LABELS[view]}
        </button>
      ))}
    </div>
  );
}

export default function Hero({
  selectedView,
  onSelectView,
  dashboard,
  data,
}: {
  selectedView: ViewKey;
  onSelectView: (view: ViewKey) => void;
  dashboard: DashboardBundle;
  data: BenchData | GlobalBenchData;
}) {
  const isGlobal = selectedView === "global";
  const benchData = isGlobal ? null : (data as BenchData);
  const rankedNoTools = [...data.modelStats]
    .filter((m) => m.condition === "no_tools")
    .sort((a, b) => b.score - a.score);
  const leadModel = rankedNoTools[0];
  const usHouseholds = Object.keys(dashboard.countries.us.scenarios).length;
  const ukHouseholds = Object.keys(dashboard.countries.uk.scenarios).length;

  const subtitle = isGlobal
    ? `${(data as GlobalBenchData).sharedModelCount} frontier models across ${(usHouseholds + ukHouseholds).toLocaleString()} households in 2 countries.`
    : selectedView === "uk"
      ? `${rankedNoTools.length} models on ${Object.keys(benchData!.scenarios).length.toLocaleString()} households across ${benchData!.programStats.length} tax and benefit outputs.`
      : `${rankedNoTools.length} models on ${Object.keys(benchData!.scenarios).length.toLocaleString()} households across ${benchData!.programStats.length} tax and benefit outputs.`;

  const stats = isGlobal
    ? [
        { value: `${leadModel?.score.toFixed(1) ?? "0.0"}%`, label: "Top score" },
        { value: "2", label: "Countries" },
        { value: `${(data as GlobalBenchData).sharedModelCount}`, label: "Models" },
        { value: `${(usHouseholds + ukHouseholds).toLocaleString()}`, label: "Households" },
      ]
    : [
        { value: `${leadModel?.score.toFixed(1) ?? "0.0"}%`, label: "Top score" },
        { value: `${rankedNoTools.length}`, label: "Models" },
        { value: `${Object.keys(benchData!.scenarios).length.toLocaleString()}`, label: "Households" },
        { value: `${benchData!.programStats.length}`, label: "Outputs" },
      ];

  return (
    <header className="relative overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-[280px] bg-[radial-gradient(circle_at_top,_color-mix(in_srgb,var(--color-primary)_13%,transparent),transparent_58%)]" />

      <div className="relative max-w-7xl mx-auto px-4 pt-8 pb-6 sm:px-6 sm:pt-10 sm:pb-8">
        <div className="flex items-start justify-between gap-6 flex-wrap animate-fade-up">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <img
                src="/assets/policyengine-mark.svg"
                alt="PolicyEngine"
                className="h-7 w-7 opacity-80 shrink-0"
              />
              <h1 className="font-[family-name:var(--font-display)] text-3xl sm:text-4xl text-text tracking-tight">
                PolicyBench
              </h1>
            </div>
            <p className="text-text-secondary text-sm sm:text-base max-w-xl mt-2 leading-relaxed">
              {subtitle}{" "}
              <span className="text-text-muted">
                100% = exact answers across the full benchmark.
              </span>
            </p>
          </div>

          <ViewSelector
            selectedView={selectedView}
            onSelect={onSelectView}
            className="mt-1"
          />
        </div>

        <div
          className="flex items-center gap-6 mt-5 animate-fade-up"
          style={{ animationDelay: "120ms" }}
        >
          <div className="flex items-center gap-5 sm:gap-6">
            {stats.map((stat, i) => (
              <div key={stat.label} className="flex items-baseline gap-1.5">
                <span className="font-[family-name:var(--font-mono)] text-lg sm:text-xl font-semibold text-primary tracking-tight">
                  {stat.value}
                </span>
                <span className="text-[10px] uppercase tracking-[0.12em] text-text-muted font-medium">
                  {stat.label}
                </span>
                {i < stats.length - 1 && (
                  <span className="text-border ml-2 select-none" aria-hidden>
                    /
                  </span>
                )}
              </div>
            ))}
          </div>

          {leadModel && (
            <div className="hidden sm:flex items-center gap-2 ml-auto text-sm text-text-muted">
              <span>Leading:</span>
              <span className="text-text font-medium">
                {MODEL_LABELS[leadModel.model] ?? leadModel.model}
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="h-px bg-gradient-to-r from-transparent via-primary/25 to-transparent" />
    </header>
  );
}
