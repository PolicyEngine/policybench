import { describe, expect, test } from "bun:test";

import registryJson from "../src/data.versions.json";
import {
  isLivePointerRef,
  parseDataVersionRegistry,
  versionSlug,
} from "../src/lib/dataVersions";

const INLINE_ARTIFACT = {
  version: 1,
  repo: "PolicyEngine/policybench",
  tag: "dashboard-data-20260625",
  asset: "dashboard-data.json",
  url: "https://github.com/PolicyEngine/policybench/releases/download/dashboard-data-20260625/dashboard-data.json",
  sha256: "a".repeat(64),
  bytes: 36_259_601,
};

const VALID_REGISTRY = {
  version: 1,
  default: "1.1",
  versions: [
    {
      id: "1.1",
      label: "1.1",
      description: "Live data",
      snapshotLabel: null,
      artifact: { pointer: "live" },
    },
    {
      id: "1.0",
      label: "1.0",
      description: "June snapshot",
      snapshotLabel: "Snapshot 2026-06-25",
      artifact: INLINE_ARTIFACT,
    },
  ],
};

describe("parseDataVersionRegistry", () => {
  test("accepts a registry with live and inline artifacts", () => {
    const registry = parseDataVersionRegistry(VALID_REGISTRY);
    expect(registry.default).toBe("1.1");
    expect(registry.versions).toHaveLength(2);
    expect(isLivePointerRef(registry.versions[0].artifact)).toBe(true);
    expect(isLivePointerRef(registry.versions[1].artifact)).toBe(false);
  });

  test("defaults snapshotLabel to null when omitted", () => {
    const raw = structuredClone(VALID_REGISTRY);
    delete (raw.versions[0] as { snapshotLabel?: unknown }).snapshotLabel;
    const registry = parseDataVersionRegistry(raw);
    expect(registry.versions[0].snapshotLabel).toBeNull();
  });

  test.each([
    [{ ...VALID_REGISTRY, version: 2 }, /version/],
    [{ ...VALID_REGISTRY, versions: [] }, /non-empty array/],
    [{ ...VALID_REGISTRY, default: "9.9" }, /default/],
    [null, /object/],
  ])("rejects %j", (registry, message) => {
    expect(() => parseDataVersionRegistry(registry)).toThrow(message);
  });

  test("rejects duplicate version ids", () => {
    const raw = structuredClone(VALID_REGISTRY);
    raw.versions[1].id = "1.1";
    expect(() => parseDataVersionRegistry(raw)).toThrow(/duplicate/);
  });

  test("rejects an unknown artifact pointer alias", () => {
    const raw = structuredClone(VALID_REGISTRY);
    (raw.versions[0] as { artifact: unknown }).artifact = { pointer: "latest" };
    expect(() => parseDataVersionRegistry(raw)).toThrow(/live/);
  });

  test("rejects an inline artifact with a malformed sha256", () => {
    const raw = structuredClone(VALID_REGISTRY);
    (raw.versions[1].artifact as { sha256: string }).sha256 = "nope";
    expect(() => parseDataVersionRegistry(raw)).toThrow(/sha256/);
  });

  test("the shipped data.versions.json is valid and defaults to a listed id", () => {
    const registry = parseDataVersionRegistry(registryJson);
    const ids = registry.versions.map((version) => version.id);
    expect(ids).toContain(registry.default);
    // Exactly one version defers to the live pointer; archived ones are pinned.
    const live = registry.versions.filter((version) =>
      isLivePointerRef(version.artifact),
    );
    expect(live).toHaveLength(1);
  });
});

describe("versionSlug", () => {
  test("replaces dots so ids map to filesystem paths", () => {
    expect(versionSlug("1.0")).toBe("1_0");
    expect(versionSlug("1.10.2")).toBe("1_10_2");
    expect(versionSlug("2")).toBe("2");
  });
});
