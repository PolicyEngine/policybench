import { describe, expect, test } from "bun:test";

import {
  coverageAccuracy,
  hardestCases,
  listModels,
  modelCountrySummaries,
  programRows,
} from "../src/lib/modelPage";
import type { BenchData, DashboardBundle } from "../src/types";

function makeBench(): BenchData {
  return {
    country: "us",
    scenarios: {
      scenario_001: {
        country: "us",
        state: "CA",
        numAdults: 1,
        numChildren: 0,
        totalIncome: 30000,
      },
      scenario_002: {
        country: "us",
        state: "TX",
        numAdults: 2,
        numChildren: 1,
        totalIncome: 60000,
      },
    },
    modelStats: [
      {
        model: "model-a",
        condition: "no_tools",
        score: 90,
        within1pct: 80,
        exact: 70,
        boundedScore: 92,
        n: 100,
        nParsed: 98,
      },
      {
        model: "model-b",
        condition: "no_tools",
        score: 85,
        within1pct: 60,
        exact: 50,
        boundedScore: 88,
        n: 100,
        nParsed: 100,
      },
      // A non-headline condition row must never leak into rankings.
      {
        model: "model-a",
        condition: "web_search",
        score: 99,
        within1pct: 99,
        n: 100,
        nParsed: 100,
      },
    ],
    programStats: [],
    heatmap: [
      {
        model: "model-a",
        variable: "snap",
        condition: "no_tools",
        score: 90,
        within1pct: 75,
        exact: 60,
        mae: 10,
        n: 50,
        nParsed: 50,
        coverage: 100,
      },
      {
        model: "model-a",
        variable: "ssi",
        condition: "no_tools",
        score: 95,
        within1pct: 95,
        exact: 90,
        mae: 2,
        n: 50,
        nParsed: 50,
        coverage: 100,
      },
    ],
    scenarioPredictions: {
      scenario_001: {
        snap: {
          "model-a": { prediction: 200, error: 100, groundTruth: 100 },
          "model-b": { prediction: 100, error: 0, groundTruth: 100 },
        },
        person_wic_eligible: {
          "model-a": { prediction: 1, error: 0, groundTruth: 1 },
          "model-b": { prediction: 0, error: -1, groundTruth: 1 },
        },
      },
      scenario_002: {
        snap: {
          "model-a": { prediction: null, error: null, groundTruth: 50 },
        },
        ssi: {
          "model-a": { prediction: 101, error: 1, groundTruth: 100 },
        },
      },
    },
    failureModes: { programs: [], households: [] },
  };
}

function makeBundle(): DashboardBundle {
  return { countries: { us: makeBench() } };
}

describe("listModels", () => {
  test("orders by best headline score across countries", () => {
    expect(listModels(makeBundle())).toEqual(["model-a", "model-b"]);
  });
});

describe("modelCountrySummaries", () => {
  test("ranks within the no_tools condition only", () => {
    const [summary] = modelCountrySummaries(makeBundle(), "model-b");
    expect(summary.country).toBe("us");
    expect(summary.rank).toBe(2);
    expect(summary.rankedModels).toBe(2);
    expect(summary.stat.within1pct).toBe(60);
  });

  test("returns empty for unknown models", () => {
    expect(modelCountrySummaries(makeBundle(), "missing")).toEqual([]);
  });
});

describe("programRows", () => {
  test("sorts hardest program first", () => {
    const rows = programRows(makeBench(), "model-a");
    expect(rows.map((row) => row.variable)).toEqual(["snap", "ssi"]);
    expect(rows[0].within1pct).toBe(75);
  });
});

describe("hardestCases", () => {
  test("ranks unparsed answers first, then by relative error", () => {
    const cases = hardestCases(makeBench(), "model-a");
    expect(cases[0]).toMatchObject({
      scenarioId: "scenario_002",
      variable: "snap",
      prediction: null,
    });
    expect(cases[1]).toMatchObject({
      scenarioId: "scenario_001",
      variable: "snap",
      relativeError: 1,
    });
    // 1% miss on ssi is within tolerance and excluded; binary flags excluded.
    expect(cases).toHaveLength(2);
  });
});

describe("coverageAccuracy", () => {
  test("counts binary eligibility flags", () => {
    expect(coverageAccuracy(makeBench(), "model-a")).toEqual({
      correct: 1,
      total: 1,
    });
    expect(coverageAccuracy(makeBench(), "model-b")).toEqual({
      correct: 0,
      total: 1,
    });
  });
});
