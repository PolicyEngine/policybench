import { describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import Methodology from "../src/components/Methodology";
import ArchivedBoardNotice from "../src/components/ArchivedBoardNotice";
import rawData from "../src/data-summary.json";
import servingConfig from "../src/model-serving-config.json";
import { isCurrentBoard, modelPageHref } from "../src/lib/boardScope";
import type { BenchData, DashboardBundle } from "../src/types";

describe("isCurrentBoard", () => {
  test("only the live version is the current board", () => {
    expect(isCurrentBoard("1.1", "1.1")).toBe(true);
    expect(isCurrentBoard("1.0", "1.1")).toBe(false);
  });

  test("model links retain only archived dataset context", () => {
    expect(modelPageHref("gpt-5.6", "1.1", "1.1")).toBe(
      "/model/gpt-5.6",
    );
    expect(modelPageHref("gpt-5.6", "1.0", "1.1")).toBe(
      "/model/gpt-5.6?dataset=1.0",
    );
  });
});

describe("ArchivedBoardNotice", () => {
  const props = {
    liveVersionId: "1.1",
    liveSnapshotDate: "2026-09-01",
    versions: [
      { id: "1.1", label: "1.1" },
      { id: "1.0", label: "1.0" },
    ],
  };

  test("renders archived context from the dataset query", () => {
    const html = renderToStaticMarkup(
      createElement(ArchivedBoardNotice, {
        ...props,
        search: "?dataset=1.0",
      }),
    );
    expect(html).toContain("You came from the archived 1.0 board.");
    expect(html).toContain("current board (snapshot 2026-09-01)");
  });

  test("does not render for the live or absent dataset query", () => {
    expect(
      renderToStaticMarkup(
        createElement(ArchivedBoardNotice, {
          ...props,
          search: "?dataset=1.1",
        }),
      ),
    ).toBe("");
    expect(
      renderToStaticMarkup(
        createElement(ArchivedBoardNotice, { ...props, search: "" }),
      ),
    ).toBe("");
  });
});

describe("dataset switching", () => {
  // The live board's payload summary (prepare-data writes it from the frozen
  // release) and the frozen serving configuration: the copy's counts must
  // come from these, never from hand-typed numbers.
  const data = (rawData as unknown as DashboardBundle).countries.us as BenchData;
  const boardModels = data.modelStats.filter(
    (row) => row.condition === "no_tools",
  ).length;
  const chunked = Object.values(servingConfig.models).filter(
    (treatment) => treatment.request_shape !== "whole scenario",
  ).length;
  const words = ["zero", "one", "two", "three", "four", "five", "six", "seven",
    "eight", "nine", "ten", "eleven", "twelve"];
  const rosterPhrase = `${words[chunked][0].toUpperCase()}${words[chunked].slice(1)} of the ${boardModels} models`;

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

  test("the configuration and payload agree on the board's roster", () => {
    expect(Object.keys(servingConfig.models).sort()).toEqual(
      data.modelStats
        .filter((row) => row.condition === "no_tools")
        .map((row) => row.model)
        .sort(),
    );
  });

  test("the current-board roster sentence appears only for the live version", () => {
    expect(render("1.1")).toContain(rosterPhrase);
    expect(render("1.0")).not.toContain(rosterPhrase);
    expect(render("1.0")).toContain("archived snapshot");
  });

  test("labels the methodology scope for the selected board", () => {
    const live = render("1.1");
    expect(live).toContain("This app shows the current no-tools US benchmark");
    expect(live).toContain("Current benchmark scope");
    expect(live).toContain("Latest United States run in this app evaluates");
    // The reference engine comes from the board's own payload.
    const engine = data.policyengineBundles?.us?.model_version;
    expect(engine).toBeTruthy();
    expect(live).toContain(
      `PolicyEngine-US (policyengine-us ${engine}) computes each scored PolicyEngine reference output`,
    );

    const archived = render("1.0");
    expect(archived).toContain("This app is showing the archived 1.0 board");
    expect(archived).toContain("Archived board scope");
    expect(archived).toContain("The archived 1.0 run evaluates");
    expect(archived).not.toContain("Current benchmark scope");
  });

  test("states the engine behind the excluded outputs from the payload", () => {
    const exclusions = data.referenceExclusions ?? [];
    const byEngine = new Map<string, number>();
    for (const exclusion of exclusions) {
      const version = exclusion.engineVersion.replace("policyengine-us ", "");
      byEngine.set(version, (byEngine.get(version) ?? 0) + 1);
    }
    const engine = data.policyengineBundles?.us?.model_version as string;
    const [older] = [...byEngine.keys()].filter((version) => version !== engine);
    const html = render("1.1").replaceAll("&#x27;", "'");
    expect(html).toContain(
      `The ${exclusions.length} excluded outputs keep the values they were decided on (${byEngine.get(older)} computed with policyengine-us ${older}, ${byEngine.get(engine)} with ${engine})`,
    );
    expect(html).toContain(`that move on ${engine}; all`);
    expect(render("1.0")).not.toContain("excluded outputs keep the values");
  });
});
