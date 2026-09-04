import { expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import servingConfig from "../src/model-serving-config.json";
import {
  BoardCoverageCopy,
  FrontierCoverageCopy,
} from "../src/components/ExpandCoverageCopy";
import rawData from "../src/data-summary.json";
import { headlineExactLeader } from "../src/lib/expandMetrics";
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
  expect(leader.exact).toBeCloseTo(88.6505, 4);
  expect(pageSource).toContain("const leader = headlineExactLeader(dashboard);");
  expect(pageSource).toContain(
    "const leaderLabel = MODEL_LABELS[leader.model] ?? leader.model;",
  );
  expect(pageSource).toContain("The best model, {leaderLabel}, computes");
  expect(pageSource).toContain("{leader.exact.toFixed(1)}% of");
  expect(pageSource).not.toContain("88.7%");
  expect(expectedCopy).toBe(
    "GPT-5.6 Sol computes 88.7% of requested outputs exactly",
  );
});
