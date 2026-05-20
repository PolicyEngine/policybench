import type { BenchData, CountryCode } from "../types";
import SiteHeader, { type HeaderNavItem } from "./SiteHeader";

const SNAPSHOT_DATE_LABEL = "Snapshot 2026-05-20";

export default function Hero({
  selectedView,
  onSelectView,
  data,
  availableViews,
  navItems,
  activeNav,
}: {
  selectedView: CountryCode;
  onSelectView: (view: CountryCode) => void;
  data: BenchData;
  availableViews: CountryCode[];
  navItems: readonly HeaderNavItem[];
  activeNav: string;
}) {
  const rankedNoTools = [...data.modelStats]
    .filter((m) => m.condition === "no_tools")
    .sort((a, b) => b.score - a.score);

  const subtitle =
    "Testing how accurately language models calculate household taxes and benefits.";

  const stats = [
    { value: `${rankedNoTools.length}`, label: "Models" },
    {
      value: `${Object.keys(data.scenarios).length.toLocaleString()}`,
      label: "Households",
    },
    { value: `${data.programStats.length}`, label: "Outputs" },
  ];

  return (
    <>
      <SiteHeader
        navItems={navItems}
        activeNav={activeNav}
        selectedView={selectedView}
        onSelectView={onSelectView}
        availableViews={availableViews}
        actionLink={{ label: "Paper", href: "/paper", type: "internal" }}
      />

      <section
        aria-labelledby="hero-title"
        className="relative isolate overflow-hidden"
      >
        <div
          aria-hidden
          className="absolute inset-x-0 top-0 h-[320px] bg-[radial-gradient(circle_at_top,_color-mix(in_srgb,var(--color-primary)_13%,transparent),transparent_58%)] pointer-events-none -z-10"
        />
        <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-10 pb-10 sm:pt-14 sm:pb-12">
          <span
            id="hero-title"
            className="font-[family-name:var(--font-display)] tracking-tight text-text leading-none text-[36px] sm:text-[44px] block"
          >
            PolicyBench
          </span>

          <p className="mt-5 text-text-secondary text-sm sm:text-base max-w-xl leading-relaxed">
            {subtitle}
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
        </div>
      </section>
    </>
  );
}
