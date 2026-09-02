import { describe, expect, test } from "bun:test";

import { wouldRank } from "../src/lib/wouldRank";

describe("wouldRank", () => {
  const rows = [
    { exact: 88.7 },
    { exact: 86.3 },
    { exact: 86.2 },
    { exact: 84.5 },
  ];

  test("places a score above every lower row", () => {
    expect(wouldRank(86.9, rows)).toBe(2);
    expect(wouldRank(85.6, rows)).toBe(4);
    expect(wouldRank(90, rows)).toBe(1);
    expect(wouldRank(10, rows)).toBe(5);
  });

  test("a tie shares the higher position", () => {
    expect(wouldRank(86.3, rows)).toBe(2);
  });

  test("treats a missing exact as zero", () => {
    expect(
      wouldRank(1, [{ exact: null }, { exact: undefined }, { exact: 2 }]),
    ).toBe(2);
  });
});
