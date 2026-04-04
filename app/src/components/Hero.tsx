import Link from "next/link";
import { MODEL_LABELS } from "../modelMeta";
import type {
  BenchData,
  CountrySummary,
  DashboardBundle,
  GlobalBenchData,
  ViewKey,
} from "../types";
import { VIEW_LABELS } from "../types";

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

function CountrySummaryList({
  countrySummaries,
}: {
  countrySummaries: CountrySummary[];
}) {
  return (
    <div className="space-y-3">
      {countrySummaries.map((summary) => (
        <div
          key={summary.key}
          className="flex items-center justify-between gap-4 border-b border-border pb-3 last:border-b-0 last:pb-0"
        >
          <div className="min-w-0">
            <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
              {summary.key}
            </div>
            <div className="truncate text-sm font-medium text-text">
              {summary.label}
            </div>
          </div>
          <div className="text-right">
            <div className="font-[family-name:var(--font-mono)] text-sm text-primary">
              {summary.households.toLocaleString()}
            </div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted">
              households
            </div>
          </div>
        </div>
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
  const topModels = rankedNoTools.slice(0, 3);
  const usHouseholds = Object.keys(dashboard.countries.us.scenarios).length;
  const ukHouseholds = Object.keys(dashboard.countries.uk.scenarios).length;

  const subtitle = isGlobal
    ? "Global scores average each model’s US and UK benchmark results, using only the models that ran cleanly in both countries."
    : selectedView === "uk"
      ? `Frontier models on ${Object.keys(benchData!.scenarios).length.toLocaleString()} UK-calibrated households across ${benchData!.programStats.length} tax and benefit outputs.`
      : `Frontier models on ${Object.keys(benchData!.scenarios).length.toLocaleString()} U.S. households across ${benchData!.programStats.length} tax and benefit outputs.`;

  const statCards = isGlobal
    ? [
        {
          value: `${leadModel?.score.toFixed(1) ?? "0.0"}%`,
          label: "Top global score",
          accent: "primary" as const,
        },
        {
          value: "2",
          label: "Countries",
          accent: "info" as const,
        },
        {
          value: `${(data as GlobalBenchData).sharedModelCount}`,
          label: "Shared models",
          accent: "warning" as const,
        },
        {
          value: `${(usHouseholds + ukHouseholds).toLocaleString()}`,
          label: "Total households",
          accent: "primary" as const,
        },
      ]
    : [
        {
          value: `${leadModel?.score.toFixed(1) ?? "0.0"}%`,
          label: "Top score",
          accent: "primary" as const,
        },
        {
          value: `${Object.keys(benchData!.scenarios).length.toLocaleString()}`,
          label: "Households",
          accent: "info" as const,
        },
        {
          value: `${benchData!.programStats.length}`,
          label: "Outputs",
          accent: "warning" as const,
        },
        {
          value: `${rankedNoTools.length}`,
          label: "Models",
          accent: "primary" as const,
        },
      ];

  return (
    <header className="relative overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-[360px] bg-[radial-gradient(circle_at_top,_color-mix(in_srgb,var(--color-primary)_13%,transparent),transparent_58%)]" />

      <div className="relative max-w-7xl mx-auto px-4 pt-10 pb-8 sm:px-6 sm:pt-14 sm:pb-10">
        <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_19rem] lg:items-end">
          <div>
            <div className="flex items-end justify-between gap-4 flex-wrap animate-fade-up">
              <h1 className="font-[family-name:var(--font-display)] text-5xl sm:text-6xl lg:text-7xl text-text leading-[0.94] tracking-tight">
                PolicyBench
              </h1>

              <ViewSelector
                selectedView={selectedView}
                onSelect={onSelectView}
              />
            </div>

            <p
              className="text-text-secondary text-base sm:text-lg max-w-2xl mt-6 leading-relaxed animate-fade-up"
              style={{ animationDelay: "180ms" }}
            >
              {subtitle} The leaderboard below uses a bounded score where 100%
              means exact answers across the full benchmark.
            </p>

            <div
              className="mt-5 flex flex-wrap gap-3 animate-fade-up"
              style={{ animationDelay: "220ms" }}
            >
              <a
                href="#models"
                className="inline-flex items-center rounded-full bg-primary px-4 py-2 text-sm font-medium text-void transition-opacity hover:opacity-90"
              >
                View leaderboard
              </a>
              {!isGlobal && (
                <a
                  href="#scenarios"
                  className="inline-flex items-center rounded-full border border-border px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:border-primary/40 hover:text-text"
                >
                  Explore households
                </a>
              )}
              <Link
                href="/paper"
                className="inline-flex items-center rounded-full border border-border bg-card px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:border-primary/40 hover:text-text"
              >
                Read paper
              </Link>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-7">
              {statCards.map((stat, index) => (
                <Stat
                  key={stat.label}
                  value={stat.value}
                  label={stat.label}
                  accent={stat.accent}
                  delay={260 + index * 80}
                />
              ))}
            </div>
          </div>

          <div
            className="animate-fade-up border-t border-border pt-5 lg:border-t-0 lg:border-l lg:pl-8 lg:pt-0"
            style={{ animationDelay: "220ms" }}
          >
            <div className="eyebrow mb-4">
              {isGlobal ? "Countries" : "Top models"}
            </div>
            {isGlobal ? (
              <CountrySummaryList
                countrySummaries={(data as GlobalBenchData).countrySummaries}
              />
            ) : (
              <div className="space-y-3">
                {topModels.map((model, index) => (
                  <div
                    key={model.model}
                    className="flex items-center justify-between gap-4 border-b border-border pb-3 last:border-b-0 last:pb-0"
                  >
                    <div className="min-w-0">
                      <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
                        {index + 1}
                      </div>
                      <div className="truncate text-sm font-medium text-text">
                        {MODEL_LABELS[model.model] ?? model.model}
                      </div>
                    </div>
                    <div className="font-[family-name:var(--font-mono)] text-lg text-primary">
                      {model.score.toFixed(1)}%
                    </div>
                  </div>
                ))}
              </div>
            )}
            <p className="mt-4 text-xs leading-relaxed text-text-muted">
              {isGlobal ? (
                <>
                  Shared-model aggregate across{" "}
                  <span className="text-text">
                    {VIEW_LABELS.us} and {VIEW_LABELS.uk}
                  </span>
                  .
                </>
              ) : (
                <>
                  Best current run:{" "}
                  <span className="text-text">
                    {MODEL_LABELS[leadModel?.model ?? ""] ?? leadModel?.model}
                  </span>
                  .
                </>
              )}
            </p>

            <div className="mt-6 rounded-2xl border border-border bg-card/70 p-4">
              <div className="flex items-center gap-2">
                <img
                  src="/assets/policyengine-mark.svg"
                  alt="PolicyEngine"
                  className="h-4 w-4 opacity-90"
                />
                <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
                  Preprint
                </div>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-text-secondary">
                Read the PolicyBench manuscript for methodology, related work,
                scoring, and cross-country results.
              </p>
              <div className="mt-3 flex flex-wrap gap-3 text-sm">
                <Link
                  href="/paper"
                  className="text-primary transition-colors hover:text-primary-strong"
                >
                  Open paper
                </Link>
                <a
                  href="/paper/policybench.pdf"
                  className="text-text-secondary transition-colors hover:text-text"
                >
                  Download PDF
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="h-px bg-gradient-to-r from-transparent via-primary/25 to-transparent" />
    </header>
  );
}
