"use client";

import { useState } from "react";
import data from "./data.json";
import Hero from "./components/Hero";
import Methodology from "./components/Methodology";
import ScatterPlot from "./components/ScatterPlot";
import ModelLeaderboard from "./components/ModelLeaderboard";
import ProgramHeatmap from "./components/ProgramHeatmap";
import ScenarioExplorer from "./components/ScenarioExplorer";

export type BenchData = typeof data;

const NAV_ITEMS = [
  { id: "methodology", label: "Method" },
  { id: "scatter", label: "Scatter" },
  { id: "models", label: "Models" },
  { id: "programs", label: "Programs" },
  { id: "scenarios", label: "Scenarios" },
] as const;

export default function App() {
  const [activeNav, setActiveNav] = useState<string>("methodology");
  const noToolsPredictions = data.scatter.filter((d) => d.condition === "no_tools");
  const noToolsModels = new Set(
    data.modelStats
      .filter((m) => m.condition === "no_tools")
      .map((m) => m.model)
  );
  const noToolsPrograms = data.programStats.length;

  return (
    <div className="min-h-screen bg-void">
      {/* Grain overlay */}
      <div
        className="fixed inset-0 pointer-events-none z-50 opacity-[0.02]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
        }}
      />

      <Hero data={data} />

      {/* Sticky nav */}
      <nav className="sticky top-0 z-40 bg-void/80 backdrop-blur-md border-b border-border">
        <div className="max-w-7xl mx-auto px-6 flex gap-1">
          {NAV_ITEMS.map((item) => (
            <a
              key={item.id}
              href={`#${item.id}`}
              onClick={() => setActiveNav(item.id)}
              className={`px-4 py-3 text-xs font-medium tracking-wider uppercase transition-colors border-b-2 ${
                activeNav === item.id
                  ? "border-amber text-amber"
                  : "border-transparent text-text-secondary hover:text-text"
              }`}
            >
              {item.label}
            </a>
          ))}
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-6">
        <section id="methodology" className="pt-16 pb-20">
          <Methodology data={data} />
        </section>

        <section id="scatter" className="pt-16 pb-20">
          <ScatterPlot data={data} />
        </section>

        <section id="models" className="pb-20">
          <ModelLeaderboard data={data} />
        </section>

        <section id="programs" className="pb-20">
          <ProgramHeatmap data={data} />
        </section>

        <section id="scenarios" className="pb-20">
          <ScenarioExplorer data={data} />
        </section>
      </main>

      <footer className="border-t border-border py-10 px-6 text-center">
        <p className="text-text-muted text-xs tracking-wide">
          PolicyBench v2 &mdash; {noToolsPredictions.length.toLocaleString()}{" "}
          no-tools predictions across {noToolsModels.size} frontier models, {noToolsPrograms}
          programs, and {Object.keys(data.scenarios).length} household scenarios.
        </p>
        <p className="text-text-muted text-xs mt-2">
          <a href="https://cosilico.ai" className="text-text-secondary hover:text-amber transition-colors">
            Cosilico
          </a>
          {" "}&middot;{" "}
          <a href="https://policyengine.org" className="text-text-secondary hover:text-amber transition-colors">
            PolicyEngine
          </a>
          {" "}&middot;{" "}
          <a href="https://github.com/CosilicoAI/policybench" className="text-text-secondary hover:text-amber transition-colors">
            GitHub
          </a>
        </p>
      </footer>
    </div>
  );
}
