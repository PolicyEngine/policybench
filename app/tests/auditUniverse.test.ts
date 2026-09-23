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
    expect(summarizeAuditUniverse(us)).toEqual({
      annotatedRowCount: 7_051,
      legacyThresholdRowCount: 7_051,
      exactMissCount: 7_047,
      annotatedExactMissCount: 7_047,
      annotatedExactHitCount: 4,
      unannotatedBelowFullBoundedScoreCount: 1_841,
    });
  });
});
