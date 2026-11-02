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
    // Release 20261027: the counts tests/test_disclosures.py recomputes
    // from the frozen annotations and payload (51 models; GPT-6.1 Terra's
    // rows join, and the move to policyengine-us 2.60.0 changes four scored
    // references; release 20261014: 8,765 annotated, 2,329 unannotated).
    expect(summarizeAuditUniverse(us)).toEqual({
      annotatedRowCount: 9_050,
      legacyThresholdRowCount: 9_050,
      exactMissCount: 9_046,
      annotatedExactMissCount: 9_046,
      annotatedExactHitCount: 4,
      unannotatedBelowFullBoundedScoreCount: 2_407,
    });
  });
});
