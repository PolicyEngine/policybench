import { expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ExpandPage from "../src/app/expand/page";
import rawData from "../src/data-summary.json";
import { listModels } from "../src/lib/modelPage";
import type { DashboardBundle } from "../src/types";

test("expand page renders the live model count", () => {
  const modelCount = listModels(rawData as DashboardBundle).length;
  const html = renderToStaticMarkup(createElement(ExpandPage));
  const visibleText = html
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  expect(visibleText).toContain(`tests ${modelCount} frontier models`);
  expect(visibleText).toContain(`across all ${modelCount} board models`);
});
