/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { useEffect, useState } from "react";
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
  compact,
}: {
  selectedView: ViewKey;
  onSelect: (view: ViewKey) => void;
  compact?: boolean;
}) {
  const views: ViewKey[] = ["global", "us", "uk"];
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

export default function Hero({
  selectedView,
  onSelectView,
  dashboard,
  data,
  navItems,
  activeNav,
}: {
  selectedView: ViewKey;
  onSelectView: (view: ViewKey) => void;
  dashboard: DashboardBundle;
  data: BenchData | GlobalBenchData;
  navItems: readonly NavItem[];
  activeNav: string;
}) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 60);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

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
    <header
      className={`sticky top-0 z-40 transition-[background-color,border-color] duration-300 ${
        scrolled
          ? "bg-bg/90 backdrop-blur-md border-b border-border"
          : "bg-transparent border-b border-transparent"
      }`}
    >
      {/* Gradient glow — fades out when scrolled */}
      <div
        className={`absolute inset-x-0 top-0 h-[280px] bg-[radial-gradient(circle_at_top,_color-mix(in_srgb,var(--color-primary)_13%,transparent),transparent_58%)] pointer-events-none transition-opacity duration-300 ${
          scrolled ? "opacity-0" : "opacity-100"
        }`}
      />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6">
        {/* Top row: brand + view selector — always visible */}
        <div
          className={`flex items-center gap-3 transition-[padding] duration-300 ${
            scrolled ? "py-2" : "pt-8 pb-4 sm:pt-10 sm:pb-4"
          }`}
        >
          <Link
            href="/"
            className="shrink-0 flex items-center gap-2.5 transition-colors hover:opacity-80"
          >
            <span
              className={`font-[family-name:var(--font-display)] tracking-tight text-text transition-[font-size] duration-300 ${
                scrolled ? "text-base" : "text-3xl sm:text-4xl"
              }`}
            >
              PolicyBench
            </span>
            {/* "a PolicyEngine project" tagline — visible when expanded */}
            <span
              className={`flex items-center gap-1.5 transition-all duration-300 overflow-hidden ${
                scrolled
                  ? "opacity-0 max-w-0"
                  : "opacity-60 max-w-[200px]"
              }`}
            >
              <span className="text-text-muted text-sm whitespace-nowrap">a</span>
              <img
                src="/assets/policyengine-logo.svg"
                alt="PolicyEngine"
                className="h-3.5 w-auto shrink-0"
              />
              <span className="text-text-muted text-sm whitespace-nowrap">project</span>
            </span>
          </Link>

          {/* Nav tabs — slide in when scrolled */}
          <div
            className={`flex items-center gap-0 transition-all duration-300 overflow-hidden ${
              scrolled
                ? "opacity-100 max-w-[600px] ml-1"
                : "opacity-0 max-w-0 ml-0"
            }`}
          >
            <div className="h-4 w-px bg-border shrink-0 mx-2" />
            <div className="flex min-w-max gap-0.5">
              {navItems.map((item) => (
                <a
                  key={item.id}
                  href={`#${item.id}`}
                  className={`px-2.5 py-2 text-[11px] font-medium tracking-wider uppercase transition-colors border-b-2 sm:px-3 ${
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
            compact={scrolled}
          />

          {/* Paper link — only when scrolled */}
          <div
            className={`transition-all duration-300 overflow-hidden ${
              scrolled ? "opacity-100 max-w-[80px]" : "opacity-0 max-w-0"
            }`}
          >
            <Link
              href="/paper"
              className="rounded-full border border-border bg-card px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-text-secondary transition-colors hover:border-primary/40 hover:text-primary whitespace-nowrap"
            >
              Paper
            </Link>
          </div>
        </div>

        {/* Expanded content: subtitle + stats — collapses on scroll */}
        <div
          className={`overflow-hidden transition-all duration-300 ease-out ${
            scrolled ? "max-h-0 opacity-0 pb-0" : "max-h-40 opacity-100 pb-6 sm:pb-8"
          }`}
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

      {/* Bottom border gradient — only when not scrolled */}
      {!scrolled && (
        <div className="h-px bg-gradient-to-r from-transparent via-primary/25 to-transparent" />
      )}
    </header>
  );
}
