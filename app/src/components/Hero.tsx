/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { MODEL_LABELS } from "../modelMeta";
import type {
  BenchData,
  DashboardBundle,
  GlobalBenchData,
  ViewKey,
} from "../types";
import { VIEW_LABELS } from "../types";

function ViewSelector({
  selectedView,
  onSelect,
  views,
  compact,
}: {
  selectedView: ViewKey;
  onSelect: (view: ViewKey) => void;
  views: ViewKey[];
  compact?: boolean;
}) {
  const pill = compact
    ? "rounded-full text-[10px] px-2.5 py-1 font-medium transition-colors"
    : "rounded-full px-3 py-1.5 text-xs font-medium transition-colors sm:px-4";
  return (
    <div className="inline-flex max-w-full items-center gap-1 rounded-full border border-border bg-bg/80 p-1">
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

type NavItem = { id: string; label: string };

/** Returns 0 at top, 1 when fully collapsed. Smooth continuous value. */
function getScrollProgress(threshold: number) {
  if (typeof window === "undefined") return 0;
  return Math.min(1, Math.max(0, window.scrollY / threshold));
}

function useScrollProgress(threshold = 80) {
  const [progress, setProgress] = useState(() => getScrollProgress(threshold));
  const rafRef = useRef(0);

  useEffect(() => {
    const onScroll = () => {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        setProgress(getScrollProgress(threshold));
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(rafRef.current);
    };
  }, [threshold]);

  return progress;
}

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
  navItems: readonly NavItem[];
  activeNav: string;
}) {
  const progress = useScrollProgress(80);
  const scrolled = progress > 0.5;

  const isGlobal = selectedView === "global";
  const benchData = isGlobal ? null : (data as BenchData);
  const rankedNoTools = [...data.modelStats]
    .filter((m) => m.condition === "no_tools")
    .sort((a, b) => b.score - a.score);
  const leadModel = rankedNoTools[0];
  const countryHouseholds = Object.values(dashboard.countries).map(
    (country) => Object.keys(country?.scenarios ?? {}).length
  );
  const totalHouseholds = countryHouseholds.reduce((sum, count) => sum + count, 0);
  const countryCount = countryHouseholds.length;

  const subtitle = isGlobal
    ? `${(data as GlobalBenchData).sharedModelCount} frontier models across ${totalHouseholds.toLocaleString()} households in ${countryCount} countries.`
    : `${rankedNoTools.length} models on ${Object.keys(benchData!.scenarios).length.toLocaleString()} households across ${benchData!.programStats.length} tax and benefit outputs.`;

  const stats = isGlobal
    ? [
        { value: `${leadModel?.score.toFixed(1) ?? "0.0"}%`, label: "Top score" },
        { value: `${countryCount}`, label: "Countries" },
        { value: `${(data as GlobalBenchData).sharedModelCount}`, label: "Models" },
        { value: `${totalHouseholds.toLocaleString()}`, label: "Households" },
      ]
    : [
        { value: `${leadModel?.score.toFixed(1) ?? "0.0"}%`, label: "Top score" },
        { value: `${rankedNoTools.length}`, label: "Models" },
        { value: `${Object.keys(benchData!.scenarios).length.toLocaleString()}`, label: "Households" },
        { value: `${benchData!.programStats.length}`, label: "Outputs" },
      ];

  // Continuous interpolation helpers
  const lerp = (a: number, b: number) => a + (b - a) * progress;
  const expandedPadTop = lerp(40, 8); // pt-10 → py-2
  const expandedPadBot = lerp(16, 8);
  const titleSize = lerp(36, 16); // text-4xl → text-base
  const taglineOpacity = 1 - progress;
  const expandOpacity = 1 - Math.min(1, progress * 2); // fade out faster
  const expandHeight = `${(1 - progress) * 140}px`;
  const navOpacity = Math.max(0, (progress - 0.3) / 0.7); // fade in after 30%
  const bgOpacity = progress;

  return (
    <header className="sticky top-0 z-40">
      {/* Background — fades in */}
      <div
        className="absolute inset-0 border-b backdrop-blur-md"
        style={{
          opacity: bgOpacity,
          backgroundColor: `color-mix(in srgb, var(--color-bg) ${Math.round(bgOpacity * 90)}%, transparent)`,
          borderColor: `color-mix(in srgb, var(--color-border) ${Math.round(bgOpacity * 100)}%, transparent)`,
        }}
      />

      {/* Gradient glow — fades out */}
      <div
        className="absolute inset-x-0 top-0 h-[280px] bg-[radial-gradient(circle_at_top,_color-mix(in_srgb,var(--color-primary)_13%,transparent),transparent_58%)] pointer-events-none"
        style={{ opacity: 1 - progress }}
      />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6">
        {/* Top row: brand + nav + view selector */}
        <div
          className="flex items-center gap-3"
          style={{
            paddingTop: `${expandedPadTop}px`,
            paddingBottom: `${expandedPadBot}px`,
          }}
        >
          <Link
            href="/"
            className="shrink-0 flex items-center gap-2 hover:opacity-80"
          >
            <span
              className="font-[family-name:var(--font-display)] tracking-tight text-text leading-none"
              style={{ fontSize: `${titleSize}px` }}
            >
              PolicyBench
            </span>
            {/* "by [PE logo]" tagline */}
            <span
              className="flex items-center gap-1.5 overflow-hidden"
              style={{ opacity: taglineOpacity * 0.6, maxWidth: taglineOpacity > 0.05 ? "160px" : "0px" }}
            >
              <span className="text-text-muted text-sm whitespace-nowrap">by</span>
              <img
                src="/assets/policyengine-logo.svg"
                alt="PolicyEngine"
                className="h-3.5 w-auto shrink-0"
              />
            </span>
          </Link>

          {/* Nav tabs — fade in as you scroll */}
          <div
            className="flex items-center overflow-hidden"
            style={{
              opacity: navOpacity,
              maxWidth: navOpacity > 0.05 ? "600px" : "0px",
              marginLeft: navOpacity > 0.05 ? "4px" : "0px",
            }}
          >
            <div className="h-4 w-px bg-border shrink-0 mx-2" />
            <div className="flex min-w-max gap-0.5">
              {navItems.map((item) => (
                <a
                  key={item.id}
                  href={`#${item.id}`}
                  className={`px-2.5 py-2 text-[11px] font-medium tracking-wider uppercase border-b-2 sm:px-3 ${
                    activeNav === item.id
                      ? "border-primary text-primary"
                      : "border-transparent text-text-secondary hover:text-text"
                  }`}
                >
                  {item.label}
                </a>
              ))}
            </div>
          </div>

          <div className="flex-1" />

          <ViewSelector
            selectedView={selectedView}
            onSelect={onSelectView}
            views={availableViews}
            compact={scrolled}
          />

          {/* Paper link — fades in with nav */}
          <div
            className="overflow-hidden"
            style={{
              opacity: navOpacity,
              maxWidth: navOpacity > 0.05 ? "80px" : "0px",
            }}
          >
            <Link
              href="/paper"
              className="rounded-full border border-border bg-card px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-text-secondary hover:border-primary/40 hover:text-primary whitespace-nowrap"
            >
              Paper
            </Link>
          </div>
        </div>

        {/* Expanded content: subtitle + stats */}
        <div
          className="overflow-hidden"
          style={{
            maxHeight: expandHeight,
            opacity: expandOpacity,
            paddingBottom: expandOpacity > 0.05 ? `${lerp(32, 0)}px` : "0px",
          }}
        >
          <p className="text-text-secondary text-sm sm:text-base max-w-xl leading-relaxed">
            {subtitle}{" "}
            <span className="text-text-muted">
              100% = exact answers across the full benchmark.
            </span>
          </p>

          <div className="flex items-center gap-6 mt-4">
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
      </div>

      {/* Bottom border gradient — fades out */}
      <div
        className="h-px bg-gradient-to-r from-transparent via-primary/25 to-transparent"
        style={{ opacity: 1 - progress }}
      />
    </header>
  );
}
