import { describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ModelLeaderboard from "../src/components/ModelLeaderboard";
import rawData from "../src/data-summary.json";
import servingConfig from "../src/model-serving-config.json";
import { MODEL_LABELS } from "../src/modelMeta";
import { buildProgramOptions } from "../src/lib/programFilters";
import {
  chunkedServingModels,
  joinWithAnd,
  jsonContractClaudeModels,
  numberWord,
} from "../src/lib/servingConfig";
import type { BenchData, DashboardBundle } from "../src/types";

const bundle = rawData as unknown as DashboardBundle;
const board = bundle.countries.us as BenchData;
const treatments = Object.entries(servingConfig.models);

describe("serving configuration helpers", () => {
  test("chunked rows are the rows that do not send the whole scenario", () => {
    expect(chunkedServingModels()).toEqual(
      treatments
        .filter(([, treatment]) => treatment.request_shape !== "whole scenario")
        .map(([model]) => model),
    );
    expect(chunkedServingModels().length).toBeGreaterThan(0);
  });

  test("the JSON-contract Claude rows are the Claude rows without a forced tool", () => {
    const expected = treatments
      .filter(
        ([model, treatment]) =>
          model.startsWith("claude-") && treatment.answer_contract === "json",
      )
      .map(([model]) => model);
    expect(jsonContractClaudeModels()).toEqual(expected);
    for (const model of expected) {
      expect(
        (servingConfig.models as Record<string, { tool_choice: string | null }>)[
          model
        ].tool_choice,
      ).toBeNull();
    }
  });

  test("number words and lists", () => {
    expect(numberWord(10)).toBe("ten");
    expect(numberWord(45)).toBe("45");
    expect(joinWithAnd(["A"])).toBe("A");
    expect(joinWithAnd(["A", "B"])).toBe("A and B");
    expect(joinWithAnd(["A", "B", "C"])).toBe("A, B and C");
  });
});

describe("leaderboard serving copy", () => {
  function render(versionId: string): string {
    const programOptions = buildProgramOptions(board);
    return renderToStaticMarkup(
      createElement(ModelLeaderboard, {
        data: board,
        selectedView: "us",
        dashboard: bundle,
        versionId,
        liveVersionId: "1.1",
        programOptions,
        activeProgramIds: new Set(programOptions.map((option) => option.variable)),
        activeProgramSummary: "All programs",
        onResetPrograms: () => {},
        onToggleProgram: () => {},
        onSelectOnlyProgram: () => {},
      }),
    ).replace(/\s+/g, " ");
  }

  test("names the Claude rows that reject forced calls from the configuration", () => {
    const labels = joinWithAnd(
      treatments
        .filter(
          ([model, treatment]) =>
            model.startsWith("claude-") && treatment.answer_contract === "json",
        )
        .map(([model]) => MODEL_LABELS[model] ?? model),
    );
    const html = render("1.1");
    expect(html).toContain(`${labels} reject forced calls, so their rows select JSON`);
    expect(render("1.0")).not.toContain("reject forced calls");
  });
});
