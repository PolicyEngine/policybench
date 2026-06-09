import { describe, expect, test } from "bun:test";

import {
  mergeScenarioExplanations,
  splitDashboardExplanations,
} from "../src/lib/explanations";
import type { DashboardBundle, ScenarioPrediction } from "../src/types";

function makeRecord(
  overrides: Partial<ScenarioPrediction> = {},
): ScenarioPrediction {
  return {
    prediction: 100,
    error: 10,
    groundTruth: 90,
    score: 88.9,
    within10pct: 100,
    ...overrides,
  };
}

const REFERENCE = "PolicyEngine derives SNAP from net income after deductions.";

function makeBundle(): DashboardBundle {
  return {
    countries: {
      us: {
        country: "us",
        scenarios: {
          scenario_001: {
            country: "us",
            state: "CA",
            numAdults: 1,
            numChildren: 2,
            totalIncome: 30000,
          },
        },
        modelStats: [],
        programStats: [],
        heatmap: [],
        failureModes: { programs: [], households: [] },
        scenarioPredictions: {
          scenario_001: {
            snap: {
              "model-a": makeRecord({
                referenceExplanation: REFERENCE,
                explanation: "Model A reasoning.",
                annotation: "Audit note for A.",
                caseAnnotation: "Case-level note.",
              }),
              "model-b": makeRecord({
                prediction: null,
                error: null,
                referenceExplanation: REFERENCE,
                failureSource: "llm_error",
              }),
            },
            eitc: {
              "model-a": makeRecord(),
            },
          },
        },
      },
    },
  };
}

describe("splitDashboardExplanations", () => {
  test("strips every text field from the summary", () => {
    const { summary } = splitDashboardExplanations(makeBundle());
    const records = Object.values(
      summary.countries.us!.scenarioPredictions.scenario_001,
    ).flatMap((modelMap) => Object.values(modelMap));
    expect(records).toHaveLength(3);
    for (const record of records) {
      expect(record.referenceExplanation).toBeUndefined();
      expect(record.explanation).toBeUndefined();
      expect(record.annotation).toBeUndefined();
      expect(record.caseAnnotation).toBeUndefined();
    }
  });

  test("keeps numeric and small audit fields in the summary", () => {
    const { summary } = splitDashboardExplanations(makeBundle());
    const modelMap =
      summary.countries.us!.scenarioPredictions.scenario_001.snap;
    expect(modelMap["model-a"].prediction).toBe(100);
    expect(modelMap["model-a"].score).toBe(88.9);
    expect(modelMap["model-b"].failureSource).toBe("llm_error");
  });

  test("dedupes the reference explanation to one string per case", () => {
    const { explanations } = splitDashboardExplanations(makeBundle());
    const file = explanations.us!;
    expect(file.country).toBe("us");
    const snapCase = file.scenarios.scenario_001.snap;
    expect(snapCase.reference).toBe(REFERENCE);
    expect(snapCase.models?.["model-a"]).toEqual({
      explanation: "Model A reasoning.",
      annotation: "Audit note for A.",
      caseAnnotation: "Case-level note.",
    });
    // model-b had only the shared reference text, so it gets no entry.
    expect(snapCase.models?.["model-b"]).toBeUndefined();
    // Cases without any text are omitted entirely.
    expect(file.scenarios.scenario_001.eitc).toBeUndefined();
  });

  test("does not mutate the input bundle", () => {
    const bundle = makeBundle();
    splitDashboardExplanations(bundle);
    expect(
      bundle.countries.us!.scenarioPredictions.scenario_001.snap["model-a"]
        .referenceExplanation,
    ).toBe(REFERENCE);
  });
});

describe("mergeScenarioExplanations", () => {
  test("round-trips the original records", () => {
    const bundle = makeBundle();
    const original = bundle.countries.us!.scenarioPredictions.scenario_001;
    const { summary, explanations } = splitDashboardExplanations(bundle);
    const merged = mergeScenarioExplanations(
      summary.countries.us!.scenarioPredictions.scenario_001,
      explanations.us!.scenarios.scenario_001,
    );
    expect(merged).toEqual(original);
  });

  test("returns the same reference when there is nothing to merge", () => {
    const { summary } = splitDashboardExplanations(makeBundle());
    const predictions =
      summary.countries.us!.scenarioPredictions.scenario_001;
    expect(mergeScenarioExplanations(predictions, undefined)).toBe(
      predictions,
    );
  });
});
