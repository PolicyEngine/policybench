import { describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import frozenServingConfig from "../../paper/snapshot/20260501/model_serving_config.json";
import RequestShapeNotice from "../src/components/RequestShapeNotice";

type ServingConfiguration = {
  models: Record<string, { request_shape: string }>;
};

const servingModels = (frozenServingConfig as ServingConfiguration).models;

function renderNotice(model: string, versionId = "1.1"): string {
  return renderToStaticMarkup(
    createElement(RequestShapeNotice, {
      model,
      requestShape: servingModels[model]?.request_shape,
      versionId,
      liveVersionId: "1.1",
    }),
  );
}

describe("RequestShapeNotice", () => {
  test("renders the frozen output-subset count for a chunked live-board model", () => {
    const html = renderNotice("gpt-5.5");

    expect(html).toContain(
      "GPT-5.5 answered this household over 3-output subsets of this prompt",
    );
    expect(html).toContain("serving-configuration table");
  });

  test("does not render for a whole-scenario model", () => {
    expect(renderNotice("gpt-5.6-sol")).toBe("");
  });

  test("does not apply the live serving configuration to an archived board", () => {
    expect(renderNotice("gpt-5.5", "1.0")).toBe("");
  });
});
