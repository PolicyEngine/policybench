import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ServingSensitivityChip from "../src/components/ServingSensitivityChip";
import {
  SERVING_SENSITIVITY,
  servingSensitivityFor,
} from "../src/lib/servingSensitivity";
import { wouldRank } from "../src/lib/wouldRank";
import rawData from "../src/data-summary.json";
import type { DashboardBundle } from "../src/types";

const bundle = rawData as unknown as DashboardBundle;
const rows = bundle.countries.us.modelStats.filter(
  (row) => row.condition === "no_tools",
);

describe("serving sensitivity", () => {
  test("covers exactly the four Claude rows whose request shape changed", () => {
    expect(Object.keys(SERVING_SENSITIVITY).sort()).toEqual([
      "claude-fable-5",
      "claude-fable-5.1",
      "claude-opus-5",
      "claude-sonnet-5",
    ]);
    expect(servingSensitivityFor("gpt-6-astra")).toBeUndefined();
  });

  test("chip shows the auto score, the would-rank derived from the board, and the why", () => {
    const sensitivity = servingSensitivityFor("claude-fable-5")!;
    const board = rows.find((row) => row.model === "claude-fable-5")!;
    const rank = wouldRank(sensitivity.autoExact, rows);
    const html = renderToStaticMarkup(
      createElement(ServingSensitivityChip, {
        modelLabel: "Claude Fable 5",
        boardExact: board.exact ?? board.score,
        sensitivity,
        wouldRank: rank,
      }),
    );
    expect(rank).toBe(3);
    expect(html).toContain("auto 87.5 · #3");
    expect(html).toContain("switches Claude&#x27;s extended thinking off");
    expect(html).toContain("would rank #3");
    expect(html).toContain("(+7.1)");
    expect(html).toContain("sensitivity/claude-thinking-2026-08.md");
    expect(html).toContain("issues/139");
  });

  test("Fable 5.1 links its dated note and explains the JSON transport", () => {
    const sensitivity = servingSensitivityFor("claude-fable-5.1")!;
    const html = renderToStaticMarkup(
      createElement(ServingSensitivityChip, {
        modelLabel: "Claude Fable 5.1",
        boardExact: 86.9,
        sensitivity,
        wouldRank: wouldRank(sensitivity.autoExact, rows),
      }),
    );
    expect(html).toContain("auto 88.2 · #2");
    expect(html).toContain("rejects forced tool calls");
    expect(html).toContain('href="/notes/2026-09-01-claude-fable-5-1-added"');
  });

  test("the leaderboard keeps the scores in one place and marks the rows", () => {
    const source = readFileSync(
      new URL("../src/components/ModelLeaderboard.tsx", import.meta.url),
      "utf8",
    );
    expect(source).not.toContain("SENSITIVITY_EXACT");
    expect(source).toContain("<ServingSensitivityChip");
    expect(source).toContain("re-runs are marked on the rows");
  });
});
