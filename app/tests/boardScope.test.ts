import { describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import Methodology from "../src/components/Methodology";
import { isCurrentBoard } from "../src/lib/boardScope";
import type { BenchData } from "../src/types";

describe("isCurrentBoard", () => {
  test("only the live version is the current board", () => {
    expect(isCurrentBoard("1.1", "1.1")).toBe(true);
    expect(isCurrentBoard("1.0", "1.1")).toBe(false);
  });
});

describe("dataset switching", () => {
  const data = {
    country: "us",
    modelStats: [],
    programStats: [],
    scenarios: [],
    scenarioPredictions: {},
    heatmap: [],
    failureModes: [],
  } as unknown as BenchData;

  function render(versionId: string): string {
    return renderToStaticMarkup(
      createElement(Methodology, {
        data,
        selectedView: "us",
        versionId,
        liveVersionId: "1.1",
      }),
    );
  }

  test("the current-board roster sentence appears only for the live version", () => {
    expect(render("1.1")).toContain("Ten of the 33 models");
    expect(render("1.0")).not.toContain("Ten of the 33 models");
    expect(render("1.0")).toContain("archived snapshot");
  });
});
