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
    // Release 20261111: the counts tests/test_disclosures.py recomputes
    // from the frozen annotations and payload (52 models; Claude Fable 5.2's
    // rows join, and scenario_122's Minnesota state refundable credits leave
    // scoring; release 20261027: 9,050 annotated, 2,407 unannotated).
    expect(summarizeAuditUniverse(us)).toEqual({
      annotatedRowCount: 9_132,
      legacyThresholdRowCount: 9_132,
      exactMissCount: 9_128,
      annotatedExactMissCount: 9_128,
      annotatedExactHitCount: 4,
      unannotatedBelowFullBoundedScoreCount: 2_497,
    });
  });
});
