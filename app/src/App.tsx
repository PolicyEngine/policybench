"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
// Generated from data.json by scripts/prepare-data.ts (runs in dev/build):
// the bundled summary holds every numeric field, while bulky explanation
// text is split into /data/explanations-*.json and fetched on demand.
import rawData from "./data-summary.json";
import Hero from "./components/Hero";
import FailureModes from "./components/FailureModes";
import Methodology from "./components/Methodology";
import ModelLeaderboard from "./components/ModelLeaderboard";
import ProgramHeatmap from "./components/ProgramHeatmap";
import ScenarioExplorer from "./components/ScenarioExplorer";
import {
  buildProgramOptions,
  resolveActiveProgramIds,
  selectOnlyProgram as selectOnlyProgramFilter,
  toggleProgramSelection,
} from "./lib/programFilters";
import type { CountryCode, DashboardBundle } from "./types";
import { VIEW_LABELS } from "./types";

const dashboard = rawData as DashboardBundle;

export type { DashboardBundle } from "./types";

const COUNTRY_NAV_ITEMS = [
  { id: "models", label: "Models" },
  { id: "programs", label: "Programs" },
  { id: "scenarios", label: "Scenarios" },
  { id: "failure-modes", label: "Failure" },
  { id: "methodology", label: "Method" },
] as const;

const COUNTRY_ORDER: CountryCode[] = ["us", "uk"];

function getAvailableViews(dashboard: DashboardBundle): CountryCode[] {
  return COUNTRY_ORDER.filter((country) => dashboard.countries[country]);
}

/** Default UK visitors to the UK benchmark; everyone else starts on the US benchmark. */
function detectVisitorCountry(availableViews: readonly CountryCode[]): CountryCode {
  if (typeof window === "undefined" || typeof navigator === "undefined") {
    return availableViews.includes("us") ? "us" : (availableViews[0] ?? "us");
  }
  let timezone = "";
  try {
    timezone = Intl.DateTimeFormat().resolvedOptions().timeZone ?? "";
  } catch {
    timezone = "";
  }
  const langs = (navigator.languages ?? [navigator.language ?? ""])
    .map((value) => value.toLowerCase());
  const matchesUK =
    timezone === "Europe/London" ||
    timezone === "Europe/Belfast" ||
    timezone === "Europe/Guernsey" ||
    timezone === "Europe/Isle_of_Man" ||
    timezone === "Europe/Jersey" ||
    langs.some((lang) =>
      ["en-gb", "cy-gb", "gd-gb", "en-uk"].includes(lang),
    );
  if (matchesUK && availableViews.includes("uk")) return "uk";
  return availableViews.includes("us") ? "us" : (availableViews[0] ?? "us");
}

/** Explicit country override from the URL, e.g. ?country=uk or ?view=us. */
function countryFromQuery(
  availableViews: readonly CountryCode[],
): CountryCode | null {
  if (typeof window === "undefined") return null;
  const params = new URLSearchParams(window.location.search);
  const raw = (params.get("country") ?? params.get("view") ?? "").toLowerCase();
  if ((raw === "uk" || raw === "us") && availableViews.includes(raw as CountryCode)) {
    return raw as CountryCode;
  }
  return null;
}

export default function App() {
  const availableViews = useMemo(() => getAvailableViews(dashboard), []);
  // Default to the US benchmark, then switch UK visitors after mount when
  // timezone or browser language gives us a clear signal.
  const initialView: CountryCode = availableViews.includes("us")
    ? "us"
    : (availableViews[0] ?? "us");
  const [selectedView, setSelectedView] = useState<CountryCode>(initialView);
  const [hasUserPickedView, setHasUserPickedView] = useState(false);
  const [selectedPrograms, setSelectedPrograms] = useState<Set<string>>(
    () => new Set(),
  );

  useEffect(() => {
    if (hasUserPickedView) return;
    // An explicit ?country= override wins and locks the view; otherwise fall
    // back to timezone/language auto-detection.
    const fromUrl = countryFromQuery(availableViews);
    const next = fromUrl ?? detectVisitorCountry(availableViews);
    if (next !== selectedView) {
      setSelectedView(next);
    }
    if (fromUrl) {
      setHasUserPickedView(true);
    }
    // We only want this auto-pick to run once per session; further changes
    // come from the user clicking the country selector.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [activeNav, setActiveNav] = useState<string>("models");
  const observerRef = useRef<IntersectionObserver | null>(null);

  const data = dashboard.countries[selectedView]!;
  const navItems = COUNTRY_NAV_ITEMS;

  const programOptions = useMemo(() => buildProgramOptions(data), [data]);

  const programOptionIds = useMemo(
    () => programOptions.map((option) => option.variable),
    [programOptions],
  );

  const activeProgramIds = useMemo(() => {
    return resolveActiveProgramIds(programOptionIds, selectedPrograms);
  }, [programOptionIds, selectedPrograms]);

  const activeProgramSummary =
    activeProgramIds.size < programOptions.length
      ? `${activeProgramIds.size} of ${programOptions.length} selected`
      : `All ${programOptions.length} programs`;

  const resetPrograms = useCallback(() => {
    setSelectedPrograms(new Set());
  }, []);

  const toggleProgram = useCallback(
    (variable: string) => {
      setSelectedPrograms((previous) => {
        return toggleProgramSelection(programOptionIds, previous, variable);
      });
    },
    [programOptionIds],
  );

  const selectOnlyProgram = useCallback((variable: string) => {
    setSelectedPrograms(selectOnlyProgramFilter(variable));
  }, []);

  const handleSelectView = (view: CountryCode) => {
    setSelectedView(view);
    setHasUserPickedView(true);
    setActiveNav("models");
    // Keep the URL in sync so the current view is shareable/embeddable.
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("country", view);
      window.history.replaceState(null, "", url);
    }
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
    const countryData = data;
    const scoredRows = noToolsModels.reduce((sum, model) => sum + model.n, 0);
    return `PolicyBench — ${VIEW_LABELS[countryData.country]} benchmark with ${scoredRows.toLocaleString()} scored outputs across ${noToolsModels.length} frontier models, ${countryData.programStats.length} programs, and ${Object.keys(countryData.scenarios).length} household scenarios.`;
  }, [data, noToolsModels]);

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
        data={data}
        availableViews={availableViews}
        navItems={navItems}
        activeNav={activeNav}
      />

      <main id="main" className="max-w-7xl mx-auto px-4 sm:px-6">
        <h1 className="sr-only">PolicyBench leaderboard</h1>
        <section
          id="models"
          aria-labelledby="leaderboard-heading"
          className="scroll-mt-20 pt-12 pb-16 sm:pt-16 sm:pb-20"
        >
          <ModelLeaderboard
            data={data}
            selectedView={selectedView}
            dashboard={dashboard}
            programOptions={programOptions}
            activeProgramIds={activeProgramIds}
            activeProgramSummary={activeProgramSummary}
            onResetPrograms={resetPrograms}
            onToggleProgram={toggleProgram}
            onSelectOnlyProgram={selectOnlyProgram}
          />
        </section>

        <div className="h-px bg-gradient-to-r from-transparent via-border/40 to-transparent" />
        <section id="programs" className="scroll-mt-20 pt-12 pb-16 sm:pt-16 sm:pb-20">
          <ProgramHeatmap
            data={data}
            programOptions={programOptions}
            activeProgramIds={activeProgramIds}
            activeProgramSummary={activeProgramSummary}
            onResetPrograms={resetPrograms}
            onToggleProgram={toggleProgram}
            onSelectOnlyProgram={selectOnlyProgram}
          />
        </section>

        <div className="h-px bg-gradient-to-r from-transparent via-border/40 to-transparent" />
        <section id="scenarios" className="scroll-mt-20 pt-12 pb-16 sm:pt-16 sm:pb-20">
          <ScenarioExplorer key={data.country} data={data} />
        </section>

        <div className="h-px bg-gradient-to-r from-transparent via-border/40 to-transparent" />
        <section
          id="failure-modes"
          className="scroll-mt-20 pt-12 pb-16 sm:pt-16 sm:pb-20"
        >
          <FailureModes data={data} />
        </section>

        <div className="h-px bg-gradient-to-r from-transparent via-border/40 to-transparent" />
        <section id="methodology" className="scroll-mt-20 pt-12 pb-16 sm:pt-16 sm:pb-20">
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
