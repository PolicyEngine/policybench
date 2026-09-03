import { expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import servingConfig from "../src/model-serving-config.json";
import {
  BoardCoverageCopy,
  FrontierCoverageCopy,
} from "../src/components/ExpandCoverageCopy";
import { listModels } from "../src/lib/modelPage";
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
