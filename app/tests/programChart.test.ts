import { describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ProgramBars, {
  PROGRAM_BAR_ROW_CLASS,
  PROGRAM_BAR_TRACK_CLASS,
} from "../src/components/ProgramBars";
import { formatShare, programBars } from "../src/lib/programChart";
import rawData from "../src/data-summary.json";
import type { DashboardBundle } from "../src/types";

const bench = (rawData as unknown as DashboardBundle).countries.us;

describe("program bars", () => {
  test("one bar per output group, descending by exact rate, with weight shares", () => {
    const bars = programBars(bench, "claude-fable-5.1");
    expect(bars.length).toBe(18);
    const rates = bars.map((b) => b.exact ?? 0);
    expect(rates).toEqual([...rates].sort((a, b) => b - a));
    const federal = bars.find(
      (b) => b.variable === "federal_income_tax_before_refundable_credits",
    )!;
    expect(federal.exact).toBeCloseTo(69.0, 1);
    expect(federal.weightShare).toBeCloseTo(0.191, 2);
    const total = bars.reduce((sum, b) => sum + (b.weightShare ?? 0), 0);
    expect(total).toBeCloseTo(1, 3);
    expect(formatShare(federal.weightShare)).toBe("19%");
    expect(formatShare(0.041)).toBe("4.1%");
    expect(formatShare(null)).toBe("");
  });

  test("renders every program with its rate and share", () => {
    const bars = programBars(bench, "claude-fable-5.1");
    const html = renderToStaticMarkup(
      createElement(ProgramBars, { bars, country: "us" }),
    );
    expect(html.match(/<li /g)?.length).toBe(18);
    expect(html).toContain("Federal tax before refundable credits");
    expect(html).toContain(">69.0%<");
    expect(html).toContain(">19%<");
    expect(html).toContain("69.0% exact");
    expect(html).toContain("width:69%");
  });

  test("narrow rows stack the bar under the label; wide rows reserve a bar track", () => {
    // Below `sm` the row has three columns (label, rate, share) and the bar
    // spans the full width on its own line, ordered after the numbers, so a
    // 320px viewport never squeezes the bar track to zero. From `sm` up the
    // label column is capped and the bar track keeps a 6rem minimum.
    const row = PROGRAM_BAR_ROW_CLASS.split(" ");
    expect(row).toContain("grid-cols-[minmax(0,1fr)_3.5rem_3rem]");
    expect(row).toContain(
      "sm:grid-cols-[minmax(0,14rem)_minmax(6rem,1fr)_3.5rem_3rem]",
    );
    const track = PROGRAM_BAR_TRACK_CLASS.split(" ");
    expect(track).toContain("col-span-full");
    expect(track).toContain("order-last");
    expect(track).toContain("sm:col-span-1");
    expect(track).toContain("sm:order-none");
    const bars = programBars(bench, "claude-fable-5.1");
    const html = renderToStaticMarkup(
      createElement(ProgramBars, { bars, country: "us" }),
    );
    expect(html.match(/order-last col-span-full/g)?.length).toBe(18);
  });
});
