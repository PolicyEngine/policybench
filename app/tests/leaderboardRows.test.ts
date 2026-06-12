import { describe, expect, test } from "bun:test";

import {
  rankWithFallbackScore,
  rankWithRecomputedScores,
} from "../src/lib/leaderboardRows";
import type { ModelStat } from "../src/types";

function model(model: string, score: number): ModelStat {
  return {
    model,
    condition: "no_tools",
    score,
    within1pct: score,
    exact: score,
    n: 10,
    nParsed: 10,
  };
}

describe("rankWithRecomputedScores", () => {
  test("drops models absent from the recomputed score map", () => {
    expect(
      rankWithRecomputedScores(
        [model("fallback-a", 91), model("fallback-b", 82)],
        new Map(),
      ),
    ).toEqual([]);
  });

  test("uses recomputed scores instead of precomputed fallback stats", () => {
    const rows = rankWithRecomputedScores(
      [model("model-a", 10), model("model-b", 90)],
      new Map([
        ["model-a", 75],
        ["model-b", 25],
      ]),
    );

    expect(rows.map((row) => [row.model, row.score])).toEqual([
      ["model-a", 75],
      ["model-b", 25],
    ]);
  });
});

describe("rankWithFallbackScore", () => {
  test("keeps the legacy fallback path explicit", () => {
    const rows = rankWithFallbackScore(
      [model("model-a", 10), model("model-b", 90)],
      (entry) => entry.exact ?? 0,
    );

    expect(rows.map((row) => row.model)).toEqual(["model-b", "model-a"]);
  });
});
