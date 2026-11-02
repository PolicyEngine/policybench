import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fc from "fast-check";

import ModelLeaderboard from "../src/components/ModelLeaderboard";
import rawData from "../src/data-summary.json";
import servingConfig from "../src/model-serving-config.json";
import augustSummary from "../../sensitivity/data/claude-thinking-2026-08.json";
import haiku55Summary from "../../sensitivity/data/claude-haiku-5-5-thinking.json";
import fable51Summary from "../../sensitivity/data/claude-fable-5-1-thinking.json";
import { MODEL_LABELS } from "../src/modelMeta";
import { buildProgramOptions } from "../src/lib/programFilters";
import {
  capitalizeFirst,
  chunkedServingModels,
  joinWithAnd,
  jsonContractClaudeModels,
  numberWord,
  type ServingConfiguration,
} from "../src/lib/servingConfig";
import {
  SERVING_SENSITIVITY,
  servingSensitivityCounts,
} from "../src/lib/servingSensitivity";
import type { BenchData, DashboardBundle } from "../src/types";

const bundle = rawData as unknown as DashboardBundle;
const board = bundle.countries.us as BenchData;

const treatment = fc.record({
  answer_contract: fc.constantFrom("tool", "json"),
  request_shape: fc.constantFrom(
    "whole scenario",
    "one output per request",
    "three outputs per request",
  ),
  tool_choice: fc.constantFrom("forced", null),
});
const config = fc
  .dictionary(
    fc.oneof(
      fc.string({ minLength: 1, maxLength: 8 }),
      fc.string({ minLength: 1, maxLength: 8 }).map((s) => `claude-${s}`),
    ),
    treatment,
    { maxKeys: 20 },
  )
  .map((models) => ({ models }) as ServingConfiguration);

function isSubsequence(items: string[], of: string[]): boolean {
  let at = 0;
  for (const item of of) if (item === items[at]) at += 1;
  return at === items.length;
}

describe("serving configuration helpers", () => {
  test("worked example", () => {
    const example = {
      models: {
        "claude-a": {
          answer_contract: "json",
          request_shape: "whole scenario",
          tool_choice: null,
        },
        "claude-b": {
          answer_contract: "tool",
          request_shape: "one output per request",
          tool_choice: "forced",
        },
        "gemini-c": {
          answer_contract: "json",
          request_shape: "three outputs per request",
          tool_choice: null,
        },
      },
    } as ServingConfiguration;
    expect(chunkedServingModels(example)).toEqual(["claude-b", "gemini-c"]);
    expect(jsonContractClaudeModels(example)).toEqual(["claude-a"]);
  });

  test("chunked rows: exactly the rows not sent whole, in roster order", () => {
    fc.assert(
      fc.property(config, (cfg) => {
        const chunked = chunkedServingModels(cfg);
        const models = Object.keys(cfg.models);
        expect(isSubsequence(chunked, models)).toBe(true);
        for (const model of models) {
          expect(chunked.includes(model)).toBe(
            cfg.models[model].request_shape !== "whole scenario",
          );
        }
      }),
    );
  });

  test("JSON Claude rows: exactly the Claude rows on the JSON contract", () => {
    fc.assert(
      fc.property(config, (cfg) => {
        const rows = jsonContractClaudeModels(cfg);
        const models = Object.keys(cfg.models);
        expect(isSubsequence(rows, models)).toBe(true);
        for (const model of models) {
          expect(rows.includes(model)).toBe(
            model.startsWith("claude-") &&
              cfg.models[model].answer_contract === "json",
          );
        }
      }),
    );
  });

  test("the live helpers agree with the paper's serving-configuration table", () => {
    // Python renders the table from the same frozen configuration
    // (paper/index.qmd); the rows are matched by provider id.
    const html = readFileSync(
      new URL("../public/paper/web/index.html", import.meta.url),
      "utf8",
    );
    const rows = new Map<string, { contract: string; shape: string }>();
    for (const row of html.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/g)) {
      const cells = [...row[1].matchAll(/<td>([\s\S]*?)<\/td>/g)].map((c) =>
        // The table breaks long ids with zero-width spaces.
        c[1].replace(/<[^>]+>/g, "").replace(/\u200b/g, "").trim(),
      );
      if (cells.length === 7 && (cells[4] === "JSON" || cells[4] === "forced tool")) {
        rows.set(cells[1], { contract: cells[4], shape: cells[5] });
      }
    }
    const models = servingConfig.models as Record<
      string,
      { provider_id: string }
    >;
    expect(rows.size).toBe(Object.keys(models).length);
    const byTable = (predicate: (row: { contract: string; shape: string }) => boolean) =>
      Object.entries(models)
        .filter(([, t]) => predicate(rows.get(t.provider_id)!))
        .map(([model]) => model);
    expect(chunkedServingModels()).toEqual(
      byTable((row) => row.shape !== "whole scenario"),
    );
    expect(jsonContractClaudeModels()).toEqual(
      byTable((row) => row.contract === "JSON").filter((m) =>
        m.startsWith("claude-"),
      ),
    );
    // tests/test_disclosures.py checks each of these rows' model card
    // records that the API rejects forced tool use.
    expect(jsonContractClaudeModels()).toEqual([
      "claude-fable-5.1",
      "claude-opus-5.5",
      "claude-sonnet-5.5",
    ]);
  });

  test("number words and lists", () => {
    expect(numberWord(10)).toBe("ten");
    expect(numberWord(45)).toBe("45");
    expect(capitalizeFirst("three")).toBe("Three");
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
      jsonContractClaudeModels().map((model) => MODEL_LABELS[model] ?? model),
    );
    expect(labels).toBe("Claude Fable 5.1, Claude Opus 5.5 and Claude Sonnet 5.5");
    const html = render("1.1");
    expect(html).toContain(`${labels} reject forced calls, so their rows select JSON`);
    expect(render("1.0")).not.toContain("reject forced calls");
  });

  test("states the re-run counts the sensitivity data records", () => {
    // The August runs and Haiku 5.5's are forced-tool rows, whose thinking
    // was off; the Fable 5.1 run compares transports on a row that reasons.
    const counts = servingSensitivityCounts();
    const forced = [
      ...Object.values(augustSummary.runs).map((run) => run.model),
      haiku55Summary.model,
    ];
    expect(Object.keys(SERVING_SENSITIVITY).sort()).toEqual(
      [...forced, fable51Summary.model].sort(),
    );
    expect(
      Object.entries(SERVING_SENSITIVITY)
        .filter(([, entry]) => entry.thinkingSuppressedOnBoard)
        .map(([model]) => model)
        .sort(),
    ).toEqual([...forced].sort());
    expect(counts).toEqual({
      reruns: forced.length + 1,
      thinkingSuppressed: forced.length,
    });
    const html = render("1.1");
    expect(html).toContain(
      `${capitalizeFirst(numberWord(counts.thinkingSuppressed))} Claude rows ran without extended thinking`,
    );
    expect(html).toContain(
      `re-runs are marked on the ${numberWord(counts.reruns)} rows`,
    );
    expect(html).toContain(`has all ${numberWord(counts.reruns)} runs`);
  });

  test("the counts follow the entries", () => {
    fc.assert(
      fc.property(fc.array(fc.boolean(), { maxLength: 12 }), (flags) => {
        const entries = Object.fromEntries(
          flags.map((flag, i) => [
            `m${i}`,
            { ...SERVING_SENSITIVITY["claude-opus-5"], thinkingSuppressedOnBoard: flag },
          ]),
        );
        expect(servingSensitivityCounts(entries)).toEqual({
          reruns: flags.length,
          thinkingSuppressed: flags.filter(Boolean).length,
        });
      }),
    );
  });
});
