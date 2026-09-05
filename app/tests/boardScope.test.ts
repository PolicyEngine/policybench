import { describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import Methodology from "../src/components/Methodology";
import ArchivedBoardNotice from "../src/components/ArchivedBoardNotice";
import { isCurrentBoard, modelPageHref } from "../src/lib/boardScope";
import type { BenchData } from "../src/types";

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
    expect(render("1.1")).toContain("Ten of the 39 models");
    expect(render("1.0")).not.toContain("Ten of the 39 models");
    expect(render("1.0")).toContain("archived snapshot");
  });

  test("labels the methodology scope for the selected board", () => {
    const live = render("1.1");
    expect(live).toContain("This app shows the current no-tools US benchmark");
    expect(live).toContain("Current benchmark scope");
    expect(live).toContain("Latest United States run in this app evaluates");

    const archived = render("1.0");
    expect(archived).toContain("This app is showing the archived 1.0 board");
    expect(archived).toContain("Archived board scope");
    expect(archived).toContain("The archived 1.0 run evaluates");
    expect(archived).not.toContain("Current benchmark scope");
  });
});
