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
    // Release 20261013: the counts tests/test_disclosures.py recomputes
    // from the frozen annotations and payload (48 models; Muse Wonder's rows
    // join, and the ten outputs the 2.41.0 upgrade regenerates return to
    // scoring).
    expect(summarizeAuditUniverse(us)).toEqual({
      annotatedRowCount: 8_550,
      legacyThresholdRowCount: 8_550,
      exactMissCount: 8_546,
      annotatedExactMissCount: 8_546,
      annotatedExactHitCount: 4,
      unannotatedBelowFullBoundedScoreCount: 2_218,
    });
  });
});
