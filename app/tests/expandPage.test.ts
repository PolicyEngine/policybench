import { expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import servingConfig from "../src/model-serving-config.json";
import {
  BoardCoverageCopy,
  FrontierCoverageCopy,
} from "../src/components/ExpandCoverageCopy";
import rawData from "../src/data-summary.json";
import {
  headlineExactLeader,
  medicaidEligibilityAccuracy,
  misclassificationFrequency,
} from "../src/lib/expandMetrics";
import { listModels } from "../src/lib/modelPage";
import { MODEL_LABELS } from "../src/modelMeta";
import type { DashboardBundle } from "../src/types";

test("expand page copy renders the bundled live model count", async () => {
  const configuredModels = Object.keys(servingConfig.models);
  const dashboard = {
    countries: {
      us: {
        modelStats: configuredModels.map((model, index) => ({
          model,
          condition: "no_tools",
          score: index,
        })),
      },
    },
  } as unknown as DashboardBundle;
  const modelCount = listModels(dashboard).length;
  const html = renderToStaticMarkup(
    createElement(
      "div",
      null,
      createElement(FrontierCoverageCopy, { modelCount }),
      createElement(BoardCoverageCopy, { modelCount }),
    ),
  );
  const visibleText = html
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  expect(modelCount).toBe(configuredModels.length);
  expect(visibleText).toContain(
    `The public board tests ${modelCount} frontier models on 100 real households.`,
  );
  expect(visibleText).toContain(
    `tax credits, across all ${modelCount} board models.`,
  );

  const pageSource = await Bun.file(
    new URL("../src/app/expand/page.tsx", import.meta.url),
  ).text();
  expect(pageSource).toContain("const modelCount = listModels(dashboard).length;");
  expect(pageSource).toContain(
    "<FrontierCoverageCopy modelCount={modelCount} />",
  );
  expect(pageSource).toContain("<BoardCoverageCopy modelCount={modelCount} />");
});

test("expand page derives its exact-score headline from the live summary", async () => {
  const dashboard = rawData as DashboardBundle;
  const leader = headlineExactLeader(dashboard);
  const expectedCopy = `${MODEL_LABELS[leader.model] ?? leader.model} computes ${leader.exact.toFixed(1)}% of requested outputs exactly`;
  const pageSource = await Bun.file(
    new URL("../src/app/expand/page.tsx", import.meta.url),
  ).text();

  expect(leader.model).toBe("gpt-5.6-sol");
  expect(leader.exact).toBeCloseTo(89.1611, 4);
  expect(pageSource).toContain("const leader = headlineExactLeader(dashboard);");
  expect(pageSource).toContain(
    "const leaderLabel = MODEL_LABELS[leader.model] ?? leader.model;",
  );
  expect(pageSource).toContain("The best model, {leaderLabel}, computes");
  expect(pageSource).toContain("{leader.exact.toFixed(1)}% of");
  expect(pageSource).not.toContain("89.2%");
  expect(expectedCopy).toBe(
    "GPT-5.6 Sol computes 89.2% of requested outputs exactly",
  );
});

test("expand page derives Medicaid error frequencies from the bundled rows", async () => {
  const accuracy = medicaidEligibilityAccuracy(rawData as DashboardBundle);
  expect(accuracy.median).toBeCloseTo(93.78531073446328);
  expect(misclassificationFrequency(accuracy.median)).toBe("about 1 in 16 people");
  expect(misclassificationFrequency(accuracy.weakest)).toBe("about 1 in 3 people");
  const pageSource = await Bun.file(
    new URL("../src/app/expand/page.tsx", import.meta.url),
  ).text();
  expect(pageSource).toContain("misclassificationFrequency(medicaidAccuracy.median)");
  expect(pageSource).toContain("misclassificationFrequency(medicaidAccuracy.weakest)");
  expect(pageSource).not.toContain("1 person in");
});

test("Medicaid accuracy weights each model's rows before taking an even median", () => {
  const heatmap = [
    { model: "a", variable: "head_medicaid_eligible", accuracy: 100, n: 1 },
    { model: "a", variable: "child1_medicaid_eligible", accuracy: 0, n: 3 },
    { model: "b", variable: "person_medicaid_eligible", accuracy: 75, n: 8 },
    { model: "a", variable: "person_chip_eligible", accuracy: 0, n: 100 },
  ].map((row) => ({ ...row, condition: "no_tools" }));
  heatmap.push({
    model: "c", variable: "person_medicaid_eligible", accuracy: 100, n: 100,
    condition: "tools",
  });
  const bundle = { countries: { us: { heatmap } } } as unknown as DashboardBundle;
  expect(medicaidEligibilityAccuracy(bundle)).toEqual({ median: 50, weakest: 25 });
  expect(misclassificationFrequency(100)).toBe("none of the evaluated people");
});
