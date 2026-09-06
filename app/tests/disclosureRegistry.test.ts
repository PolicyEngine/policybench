import { describe, expect, test } from "bun:test";

import { createDisclosureRegistry } from "../src/lib/disclosureRegistry";

function handle(log: string[], name: string) {
  return {
    close: (restoreFocus: boolean) => {
      log.push(`${name}:${restoreFocus ? "focus" : "quiet"}`);
    },
  };
}

describe("disclosure registry", () => {
  test("opening a second chip closes the first without stealing focus", () => {
    const log: string[] = [];
    const registry = createDisclosureRegistry();
    const later = handle(log, "later");
    const earlier = handle(log, "earlier");
    registry.activate(later);
    // The reviewed sequence: a later row's chip is open; the reader tabs back
    // and opens an earlier chip. Only the earlier one stays open.
    registry.activate(earlier);
    expect(log).toEqual(["later:quiet"]);
    expect(registry.isActive(earlier)).toBe(true);
    expect(registry.isActive(later)).toBe(false);
    // Escape closes the open one and restores focus to *its* chip only.
    expect(registry.escape()).toBe(true);
    expect(log).toEqual(["later:quiet", "earlier:focus"]);
    expect(registry.escape()).toBe(false);
  });

  test("release forgets only the active handle", () => {
    const log: string[] = [];
    const registry = createDisclosureRegistry();
    const a = handle(log, "a");
    const b = handle(log, "b");
    registry.activate(a);
    registry.release(b);
    expect(registry.isActive(a)).toBe(true);
    registry.release(a);
    expect(registry.isActive(a)).toBe(false);
    expect(registry.escape()).toBe(false);
    expect(log).toEqual([]);
  });
});
