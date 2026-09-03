import { expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import servingConfig from "../src/model-serving-config.json";
import ExpandModelCount from "../src/components/ExpandModelCount";

test("expand page renders the live model count", () => {
  const modelCount = Object.keys(servingConfig.models).length;
  const html = renderToStaticMarkup(
    createElement(
      "div",
      null,
      createElement(ExpandModelCount, { modelCount, context: "frontier" }),
      createElement(ExpandModelCount, { modelCount, context: "board" }),
    ),
  );
  const visibleText = html
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  expect(visibleText).toContain(`tests ${modelCount} frontier models`);
  expect(visibleText).toContain(`across all ${modelCount} board models`);
});
