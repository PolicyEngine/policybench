import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import fc from "fast-check";

import rawData from "../src/data-summary.json";
import {
  ENGINE_UPGRADE_RECHECK,
  excludedOutputEngineSentence,
  excludedOutputsByEngine,
} from "../src/lib/referenceEngine";
import type { DashboardBundle, ReferenceExclusion } from "../src/types";

const board = (rawData as unknown as DashboardBundle).countries.us;
const exclusions = board.referenceExclusions ?? [];

function compare(a: string, b: string): number {
  const left = a.split(".").map(Number);
  const right = b.split(".").map(Number);
  for (let i = 0; i < Math.max(left.length, right.length); i += 1) {
    const diff = (left[i] ?? 0) - (right[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

const version = fc
  .tuple(fc.nat(3), fc.nat(800), fc.nat(20))
  .map((parts) => parts.join("."));
const exclusionList = fc.array(
  version.map(
    (v) => ({ engineVersion: `policyengine-us ${v}` }) as ReferenceExclusion,
  ),
  { maxLength: 60 },
);

describe("excludedOutputsByEngine properties", () => {
  test("the counts partition the exclusions by version, oldest first", () => {
    fc.assert(
      fc.property(exclusionList, (list) => {
        const groups = excludedOutputsByEngine(list);
        // Every exclusion is counted once, under its own version.
        expect(groups.reduce((sum, [, count]) => sum + count, 0)).toBe(
          list.length,
        );
        for (const [v, count] of groups) {
          expect(count).toBeGreaterThan(0);
          expect(
            list.filter((e) => e.engineVersion === `policyengine-us ${v}`)
              .length,
          ).toBe(count);
        }
        // Versions are distinct and in numeric (not string) order.
        const versions = groups.map(([v]) => v);
        expect(new Set(versions).size).toBe(versions.length);
        for (let i = 1; i < versions.length; i += 1) {
          expect(compare(versions[i - 1], versions[i])).toBeLessThan(0);
        }
        // Order of the input does not matter.
        expect(excludedOutputsByEngine([...list].reverse())).toEqual(groups);
      }),
    );
  });

  test("the sentence states every count once and the total", () => {
    fc.assert(
      fc.property(exclusionList, (list) => {
        const sentence = excludedOutputEngineSentence(list, null);
        if (list.length === 0) {
          expect(sentence).toBeNull();
          return;
        }
        expect(sentence).toStartWith(
          `The ${list.length.toLocaleString("en-US")} excluded outputs keep`,
        );
        for (const [v, count] of excludedOutputsByEngine(list)) {
          expect(sentence).toContain(`${count.toLocaleString("en-US")} `);
          expect(sentence).toContain(v);
        }
        expect(sentence).not.toContain("re-reviewed");
      }),
    );
  });

  test("numeric version order beats string order", () => {
    expect(
      excludedOutputsByEngine([
        { engineVersion: "policyengine-us 2.15.17" },
        { engineVersion: "policyengine-us 1.755.4" },
        { engineVersion: "policyengine-us 2.9.0" },
      ] as ReferenceExclusion[]).map(([v]) => v),
    ).toEqual(["1.755.4", "2.9.0", "2.15.17"]);
  });
});

describe("excluded-output engines against the Python record", () => {
  test("the payload's counts are the ones the paper renders from the exclusion record", () => {
    // paper_results.excluded_outputs_by_engine_version counts the frozen
    // reference_exclusions.json; the rendered paper states its counts.
    const html = readFileSync(
      new URL("../public/paper/web/index.html", import.meta.url),
      "utf8",
    ).replace(/<[^>]+>/g, "");
    const match = html.match(
      /keep the values they were decided on \((\d+) computed with policyengine-us ([\d.]+), (\d+) with ([\d.]+)\)/,
    );
    expect(match).not.toBeNull();
    const [, olderCount, older, newerCount, newer] = match!;
    expect(excludedOutputsByEngine(exclusions)).toEqual([
      [older, Number(olderCount)],
      [newer, Number(newerCount)],
    ]);
  });

  test("the live sentence names the reference engine's recheck", () => {
    const sentence = excludedOutputEngineSentence(
      exclusions,
      ENGINE_UPGRADE_RECHECK.engineVersion,
    );
    expect(sentence).toContain(
      `re-reviewed the ${ENGINE_UPGRADE_RECHECK.rechecked} of them that move on ${ENGINE_UPGRADE_RECHECK.engineVersion}`,
    );
  });
});
