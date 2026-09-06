import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ServingSensitivityChip, {
  panelPosition,
} from "../src/components/ServingSensitivityChip";
import {
  SERVING_SENSITIVITY,
  formatDelta,
  servingSensitivityFor,
} from "../src/lib/servingSensitivity";
import fable51Summary from "../../sensitivity/data/claude-fable-5-1-thinking.json";
import augustSummary from "../../sensitivity/data/claude-thinking-2026-08.json";
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
    expect(html).toContain("(+7.1 against its 80.4% on the unfiltered board)");
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
    expect(html).toContain("compares transports");
    expect(html).toContain('href="/notes/2026-09-01-claude-fable-5-1-added"');
  });

  test("the leaderboard keeps the scores in one place and marks the rows", () => {
    const source = readFileSync(
      new URL("../src/components/ModelLeaderboard.tsx", import.meta.url),
      "utf8",
    );
    expect(source).not.toContain("SENSITIVITY_EXACT");
    expect(source).toContain("<ServingSensitivityChip");
    expect(source).toContain("re-runs are marked on the four rows");
    expect(source).toContain("Three Claude rows ran without extended thinking");
    // The comparison baseline is the unfiltered exact score in both layouts,
    // never the score under the reader's current metric or filters.
    expect(source.match(/boardExact=\{unfilteredExact\(m\.model\)\}/g)?.length).toBe(2);
    expect(source).not.toContain("boardExact={m.score}");
  });

  test("scores are the pinned measurements, and deltas come from unrounded inputs", () => {
    expect(SERVING_SENSITIVITY["claude-fable-5.1"].autoExact).toBe(
      fable51Summary.sensitivity.exact,
    );
    for (const run of Object.values(augustSummary.runs)) {
      expect(SERVING_SENSITIVITY[run.model].autoExact).toBe(run.sensitivity.exact);
    }
    // 88.183 − 86.945 = 1.238 → +1.2; rounding first would have said +1.3.
    expect(formatDelta(88.183, fable51Summary.board.exact)).toBe("+1.2");
    expect(formatDelta(88.2, 86.945)).toBe("+1.3");
    expect(formatDelta(80.775, 80.8)).toBe("−0.0");
    const fable5 = Object.values(augustSummary.runs).find(
      (run) => run.model === "claude-fable-5",
    )!;
    expect(formatDelta(fable5.sensitivity.exact, fable5.board.exact)).toBe("+7.1");
  });

  test("the open panel stays inside narrow viewports", () => {
    // Desktop: under the chip at its own left edge.
    expect(panelPosition({ left: 320, bottom: 400 }, 1280)).toEqual({
      top: 406,
      left: 320,
      width: 352,
    });
    // 375px phone with the chip 120px in: the 352px panel shifts left so its
    // right edge stays 8px inside the viewport.
    const phone = panelPosition({ left: 120, bottom: 400 }, 375);
    expect(phone.width).toBe(352);
    expect(phone.left).toBe(375 - 352 - 8);
    expect(phone.left + phone.width).toBeLessThanOrEqual(375 - 8);
    // A 320px viewport is narrower than the panel's maximum: it shrinks.
    const narrow = panelPosition({ left: 200, bottom: 400 }, 320);
    expect(narrow.width).toBe(320 - 16);
    expect(narrow.left).toBe(8);
    // Chip near the right edge on a tablet: clamped, not overflowing.
    const tablet = panelPosition({ left: 700, bottom: 300 }, 768);
    expect(tablet.left + tablet.width).toBe(768 - 8);
  });
});
