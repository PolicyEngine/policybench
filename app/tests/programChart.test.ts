import { describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ProgramBars from "../src/components/ProgramBars";
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
});
