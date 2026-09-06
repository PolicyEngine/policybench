import { describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ProgramHeatmap from "../src/components/ProgramHeatmap";
import {
  DEFAULT_HEATMAP_METRIC,
  HEATMAP_METRICS,
  heatmapValue,
} from "../src/lib/heatmapMetric";
import { scorePrediction } from "../src/lib/scoring";
import { buildProgramOptions } from "../src/lib/programFilters";
import rawData from "../src/data-summary.json";
import type { DashboardBundle, HeatmapEntry } from "../src/types";

const bench = (rawData as unknown as DashboardBundle).countries.us;

function fable51(variable: string): HeatmapEntry {
  return bench.heatmap.find(
    (entry) =>
      entry.model === "claude-fable-5.1" &&
      entry.variable === variable &&
      entry.condition === "no_tools",
  )!;
}

describe("program heatmap metric", () => {
  test("defaults to the headline metric, exact match", () => {
    expect(DEFAULT_HEATMAP_METRIC).toBe("exact");
    expect(HEATMAP_METRICS.map((m) => m.id)).toEqual([
      "exact",
      "within1pct",
      "score",
    ]);
  });

  test("exact and bounded rates differ where partial credit is large", () => {
    const federal = fable51("federal_income_tax_before_refundable_credits");
    expect(Math.round(heatmapValue(federal, "exact"))).toBe(69);
    expect(Math.round(heatmapValue(federal, "score"))).toBe(93);
    const stateTax = fable51("state_income_tax_before_refundable_credits");
    expect(Math.round(heatmapValue(stateTax, "exact"))).toBe(63);
    expect(Math.round(heatmapValue(stateTax, "score"))).toBe(92);
  });

  test("the rendered heatmap shows exact-match cells and says so", () => {
    const options = buildProgramOptions(bench);
    const html = renderToStaticMarkup(
      createElement(ProgramHeatmap, {
        data: bench,
        programOptions: options,
        activeProgramIds: new Set(options.map((option) => option.variable)),
        activeProgramSummary: "All programs",
        onResetPrograms: () => {},
        onToggleProgram: () => {},
        onSelectOnlyProgram: () => {},
      }),
    );
    expect(html).toContain("Exact match by program and model");
    expect(html).toContain("cells do not average to its headline score");
    // The federal income tax row's cells are every model's exact rate for
    // that program, never the bounded scores.
    // Anchor on the table cell: the same label also appears in the program
    // filter's option list above the table.
    const cell = html.match(/<td[^>]*>Federal tax before refundable credits<\/td>/);
    expect(cell).not.toBeNull();
    const rowStart = cell!.index!;
    const row = html.slice(rowStart, html.indexOf("</tr>", rowStart));
    const cells = [...row.matchAll(/>(\d+)%<\/div>/g)]
      .map((m) => Number(m[1]))
      .sort((a, b) => a - b);
    const entries = bench.heatmap.filter(
      (e) =>
        e.condition === "no_tools" &&
        e.variable === "federal_income_tax_before_refundable_credits",
    );
    const exactRates = entries.map((e) => Math.round(e.exact ?? 0)).sort((a, b) => a - b);
    const boundedRates = entries.map((e) => Math.round(e.score)).sort((a, b) => a - b);
    expect(cells).toEqual(exactRates);
    expect(cells).not.toEqual(boundedRates);
    expect(cells).toContain(69);
    expect(html).toContain('aria-pressed="true"');
  });

  test("the definitions state the zero-reference rule the scorers apply", () => {
    // A $0.14 answer to a $0 reference is within $1, so it earns exact and
    // within-1% credit, but the bounded score demands an exact zero.
    const row =
      bench.scenarioPredictions["scenario_102"]["self_employment_tax"][
        "claude-haiku-4.5"
      ];
    expect(row.groundTruth).toBe(0);
    expect(row.prediction).toBeCloseTo(0.14, 2);
    expect(row.within1pct).toBe(100);
    expect(row.exact).toBe(100);
    expect(row.score).toBe(0);
    expect(scorePrediction("self_employment_tax", "us", 0, 0.14)).toBe(0);
    expect(scorePrediction("self_employment_tax", "us", 0, 0)).toBe(1);
    const byId = Object.fromEntries(HEATMAP_METRICS.map((m) => [m.id, m.description]));
    expect(byId.within1pct).toContain("within $1 when the reference is $0");
    expect(byId.score).toContain("nonzero answer to a $0 reference scores zero");
    expect(byId.exact).toContain("within $1 of the reference");
  });
});
