import type {
  BenchData,
  DashboardBundle,
  GlobalBenchData,
  ViewKey,
} from "../types";
import SiteHeader, { type HeaderNavItem } from "./SiteHeader";

const SNAPSHOT_DATE_LABEL = "Snapshot 2026-05-01";

export default function Hero({
  selectedView,
  onSelectView,
  dashboard,
  data,
  availableViews,
  navItems,
  activeNav,
}: {
  selectedView: ViewKey;
  onSelectView: (view: ViewKey) => void;
  dashboard: DashboardBundle;
  data: BenchData | GlobalBenchData;
  availableViews: ViewKey[];
  navItems: readonly HeaderNavItem[];
  activeNav: string;
}) {
  const isGlobal = selectedView === "global";
  const benchData = isGlobal ? null : (data as BenchData);
  const rankedNoTools = [...data.modelStats]
    .filter((m) => m.condition === "no_tools")
    .sort((a, b) => b.score - a.score);
  const countryHouseholds = Object.values(dashboard.countries).map(
    (country) => Object.keys(country?.scenarios ?? {}).length,
  );
  const totalHouseholds = countryHouseholds.reduce(
    (sum, count) => sum + count,
    0,
  );
  const countryCount = countryHouseholds.length;

  const subtitle = isGlobal
    ? `${(data as GlobalBenchData).sharedModelCount} frontier models across ${totalHouseholds.toLocaleString()} households in ${countryCount} countries.`
    : `${rankedNoTools.length} models on ${Object.keys(benchData!.scenarios).length.toLocaleString()} households across ${benchData!.programStats.length} tax and benefit outputs.`;

  const stats = isGlobal
    ? [
        { value: `${countryCount}`, label: "Countries" },
        {
          value: `${(data as GlobalBenchData).sharedModelCount}`,
          label: "Models",
        },
        {
          value: `${totalHouseholds.toLocaleString()}`,
          label: "Households",
        },
      ]
    : [
        { value: `${rankedNoTools.length}`, label: "Models" },
        {
          value: `${Object.keys(benchData!.scenarios).length.toLocaleString()}`,
          label: "Households",
        },
        { value: `${benchData!.programStats.length}`, label: "Outputs" },
      ];

  const expanded = (
    <>
      <p className="text-text-secondary text-sm sm:text-base max-w-xl leading-relaxed">
        {subtitle}{" "}
        <span className="text-text-muted">
          100% = exact answers across the full benchmark.
        </span>
      </p>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 mt-4">
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

        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.12em] text-text-secondary">
          <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-primary/70" />
          {SNAPSHOT_DATE_LABEL}
        </span>
      </div>
    </>
  );

  return (
    <SiteHeader
      navItems={navItems}
      activeNav={activeNav}
      selectedView={selectedView}
      onSelectView={onSelectView}
      availableViews={availableViews}
      actionLink={{ label: "Paper", href: "/paper", type: "internal" }}
      expandedContent={expanded}
    />
  );
}
