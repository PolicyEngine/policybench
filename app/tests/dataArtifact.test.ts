import { describe, expect, test } from "bun:test";

import {
  assertDashboardShape,
  parseArtifactPointer,
  sha256Hex,
} from "../src/lib/dataArtifact";

const VALID_POINTER = {
  version: 1,
  repo: "PolicyEngine/policybench",
  tag: "dashboard-data-20260610",
  asset: "dashboard-data.json",
  url: "https://github.com/PolicyEngine/policybench/releases/download/dashboard-data-20260610/dashboard-data.json",
  sha256: "a".repeat(64),
  bytes: 57_000_000,
};

describe("parseArtifactPointer", () => {
  test("accepts a valid pointer", () => {
    expect(parseArtifactPointer(VALID_POINTER)).toEqual(VALID_POINTER);
  });

  test.each([
    [{ ...VALID_POINTER, version: 2 }, /version/],
    [{ ...VALID_POINTER, sha256: "xyz" }, /sha256/],
    [{ ...VALID_POINTER, url: "http://insecure.example/x" }, /https/],
    [{ ...VALID_POINTER, bytes: "big" }, /bytes/],
    [{ ...VALID_POINTER, tag: "" }, /tag/],
    [null, /object/],
  ])("rejects %j", (pointer, message) => {
    expect(() => parseArtifactPointer(pointer)).toThrow(message);
  });
});

describe("sha256Hex", () => {
  test("matches a known vector", async () => {
    // sha256("abc")
    expect(await sha256Hex(new TextEncoder().encode("abc"))).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
  });
});

describe("assertDashboardShape", () => {
  test("accepts the combined payload", () => {
    expect(() =>
      assertDashboardShape({ countries: { us: {} } }, "data.json"),
    ).not.toThrow();
  });

  test("names the per-country mistake specifically", () => {
    expect(() =>
      assertDashboardShape(
        { country: "us", modelStats: [], scenarios: {} },
        "data.json",
      ),
    ).toThrow(/per-country export/);
  });

  test("rejects payloads without countries", () => {
    expect(() => assertDashboardShape({ foo: 1 }, "data.json")).toThrow(
      /missing top-level "countries"/,
    );
    expect(() => assertDashboardShape({ countries: {} }, "data.json")).toThrow(
      /non-empty/,
    );
  });
});
