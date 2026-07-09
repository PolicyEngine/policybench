import { describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ModelLeaderboard from "../src/components/ModelLeaderboard";
import type { BenchData } from "../src/types";

function makeBench(): BenchData {
  return {
    country: "us",
    scenarios: {},
    modelStats: [
      {
        model: "gpt-5.5",
        condition: "no_tools",
        score: 91.2,
        exact: 87.3,
        n: 100,
        nParsed: 100,
        costUsd: 9876.54,
        costPerHousehold: 98.765,
      },
    ],
    programStats: [],
    heatmap: [],
    scenarioPredictions: {},
    failureModes: { programs: [], households: [] },
  };
}

describe("ModelLeaderboard", () => {
  test("given cost data, when rendered, then keeps costs out of the public leaderboard", () => {
    // Given a benchmark row that retains its internal run-cost metadata.
    const data = makeBench();

    // When the public leaderboard is rendered.
    const markup = renderToStaticMarkup(
      createElement(ModelLeaderboard, {
        data,
        selectedView: "us",
        dashboard: { countries: { us: data } },
        programOptions: [],
        activeProgramIds: new Set<string>(),
        activeProgramSummary: "All programs",
        onResetPrograms: () => {},
        onToggleProgram: () => {},
        onSelectOnlyProgram: () => {},
      }),
    );

    // Then model results remain visible without either cost label or value.
    expect(markup).toContain("GPT-5.5");
    expect(markup).toContain("87.3%");
    expect(markup).not.toContain("Cost / household");
    expect(markup).not.toContain("per household");
    expect(markup).not.toContain("$98.765");
    expect(markup).not.toContain("$9876.54");
  });
});
