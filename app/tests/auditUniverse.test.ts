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
      annotatedRowCount: 9_076,
      legacyThresholdRowCount: 9_076,
      exactMissCount: 9_073,
      annotatedExactMissCount: 9_073,
      annotatedExactHitCount: 3,
      unannotatedBelowFullBoundedScoreCount: 1_605,
    });
  });
});
