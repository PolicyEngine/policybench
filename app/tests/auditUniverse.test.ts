import { describe, expect, it } from "bun:test";

import rawData from "../src/data-summary.json";
import type { DashboardBundle } from "../src/types";
import {
  AUDIT_SELECTION_RULE,
  summarizeAuditUniverse,
} from "../src/lib/auditUniverse";

const dashboard = rawData as DashboardBundle;

describe("audit universe", () => {
  it("recomputes the frozen US annotation coverage", () => {
    const us = dashboard.countries.us;
    expect(us).toBeDefined();
    if (!us) return;

    expect(AUDIT_SELECTION_RULE).toBe(
      "rows whose legacy threshold score is below 1",
    );
    // Release 20261006: the counts tests/test_disclosures.py recomputes
    // from the frozen annotations and payload (release 20260930's less the
    // 368 scored rows on the eight outputs it excludes).
    expect(summarizeAuditUniverse(us)).toEqual({
      annotatedRowCount: 7_527,
      legacyThresholdRowCount: 7_527,
      exactMissCount: 7_523,
      annotatedExactMissCount: 7_523,
      annotatedExactHitCount: 4,
      unannotatedBelowFullBoundedScoreCount: 2_072,
    });
  });
});
