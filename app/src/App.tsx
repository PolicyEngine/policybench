"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import rawData from "./data.json";
import Hero from "./components/Hero";
import FailureModes from "./components/FailureModes";
import Methodology from "./components/Methodology";
import ModelLeaderboard from "./components/ModelLeaderboard";
import ProgramHeatmap from "./components/ProgramHeatmap";
import ScenarioExplorer from "./components/ScenarioExplorer";
import type { BenchData, CountryCode, DashboardBundle, ViewKey } from "./types";
import { VIEW_LABELS } from "./types";

const dashboard = rawData as DashboardBundle;

export type { DashboardBundle } from "./types";

const COUNTRY_NAV_ITEMS = [
  { id: "models", label: "Models" },
  { id: "scenarios", label: "Scenarios" },
  { id: "failure-modes", label: "Failure" },
  { id: "programs", label: "Programs" },
  { id: "methodology", label: "Method" },
] as const;

const GLOBAL_NAV_ITEMS = [
  { id: "models", label: "Models" },
  { id: "methodology", label: "Method" },
] as const;

const COUNTRY_ORDER: CountryCode[] = ["us", "uk"];

function getAvailableViews(dashboard: DashboardBundle): ViewKey[] {
  const countryViews = COUNTRY_ORDER.filter((country) => dashboard.countries[country]);
  if (dashboard.global?.modelStats.length && countryViews.length > 1) {
    return ["global", ...countryViews];
  }
  return countryViews;
}

export default function App() {
  const availableViews = useMemo(() => getAvailableViews(dashboard), []);
  const defaultView = availableViews.includes("uk")
    ? "uk"
    : (availableViews[0] ?? "global");
  const [selectedView, setSelectedView] = useState<ViewKey>(defaultView);
  const [activeNav, setActiveNav] = useState<string>("models");
  const observerRef = useRef<IntersectionObserver | null>(null);

  const isGlobal = selectedView === "global";
  const data = isGlobal
    ? dashboard.global!
    : dashboard.countries[selectedView as CountryCode]!;
  const navItems = isGlobal ? GLOBAL_NAV_ITEMS : COUNTRY_NAV_ITEMS;
  const handleSelectView = (view: ViewKey) => {
    setSelectedView(view);
    setActiveNav("models");
  };

  useEffect(() => {
    if (observerRef.current) observerRef.current.disconnect();

    const sectionIds = navItems.map((item) => item.id);

    observerRef.current = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveNav(entry.target.id);
          }
        }
      },
      { rootMargin: "-40% 0px -55% 0px" },
    );

    for (const id of sectionIds) {
      const el = document.getElementById(id);
      if (el) observerRef.current.observe(el);
    }

    return () => {
      observerRef.current?.disconnect();
    };
  }, [navItems]);

  const noToolsModels = useMemo(
    () => data.modelStats.filter((m) => m.condition === "no_tools"),
    [data],
  );

  const footerCopy = useMemo(() => {
    if (isGlobal) {
      const totalHouseholds = Object.values(dashboard.countries).reduce(
        (sum, country) => sum + Object.keys(country?.scenarios ?? {}).length,
        0
      );
      const countryCount = Object.keys(dashboard.countries).length;
      return `PolicyBench — global leaderboard across ${dashboard.global?.sharedModelCount ?? 0} shared frontier models, ${countryCount} country benchmarks, and ${totalHouseholds.toLocaleString()} households.`;
    }

    const countryData = data as BenchData;
    const scoredRows = noToolsModels.reduce((sum, model) => sum + model.n, 0);
    return `PolicyBench — ${VIEW_LABELS[countryData.country]} benchmark with ${scoredRows.toLocaleString()} scored outputs across ${noToolsModels.length} frontier models, ${countryData.programStats.length} programs, and ${Object.keys(countryData.scenarios).length} household scenarios.`;
  }, [data, isGlobal, noToolsModels]);

  return (
    <div className="min-h-screen bg-void">
      <div
        className="fixed inset-0 pointer-events-none z-50 opacity-[0.02]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
        }}
      />

      <Hero
        selectedView={selectedView}
        onSelectView={handleSelectView}
        dashboard={dashboard}
        data={data}
        availableViews={availableViews}
        navItems={navItems}
        activeNav={activeNav}
      />

      <main className="max-w-7xl mx-auto px-4 sm:px-6">
        <section id="models" className="pt-12 pb-16 sm:pt-16 sm:pb-20">
          <ModelLeaderboard data={data} selectedView={selectedView} />
        </section>

        {!isGlobal && (
          <>
            <div className="h-px bg-gradient-to-r from-transparent via-border/40 to-transparent" />
            <section id="scenarios" className="pt-12 pb-16 sm:pt-16 sm:pb-20">
              <ScenarioExplorer
                key={(data as BenchData).country}
                data={data as BenchData}
              />
            </section>

            <div className="h-px bg-gradient-to-r from-transparent via-border/40 to-transparent" />
            <section
              id="failure-modes"
              className="pt-12 pb-16 sm:pt-16 sm:pb-20"
            >
              <FailureModes data={data as BenchData} />
            </section>

            <div className="h-px bg-gradient-to-r from-transparent via-border/40 to-transparent" />
            <section id="programs" className="pt-12 pb-16 sm:pt-16 sm:pb-20">
              <ProgramHeatmap data={data as BenchData} />
            </section>
          </>
        )}

        <div className="h-px bg-gradient-to-r from-transparent via-border/40 to-transparent" />
        <section id="methodology" className="pt-12 pb-16 sm:pt-16 sm:pb-20">
          <Methodology data={data} selectedView={selectedView} />
        </section>
      </main>

      <footer className="border-t border-border py-10 px-6 text-center">
        <p className="text-text-muted text-xs tracking-wide">{footerCopy}</p>
        <p className="text-text-muted text-xs mt-2">
          <a
            href="/paper"
            className="text-text-secondary hover:text-primary transition-colors"
          >
            Paper
          </a>{" "}
          &middot;{" "}
          <a
            href="https://policyengine.org"
            className="text-text-secondary hover:text-primary transition-colors"
          >
            PolicyEngine
          </a>{" "}
          &middot;{" "}
          <a
            href="https://policybench.org"
            className="text-text-secondary hover:text-primary transition-colors"
          >
            PolicyBench.org
          </a>{" "}
          &middot;{" "}
          <a
            href="https://github.com/PolicyEngine/policybench"
            className="text-text-secondary hover:text-primary transition-colors"
          >
            GitHub
          </a>
        </p>
      </footer>
    </div>
  );
}
