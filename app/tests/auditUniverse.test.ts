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
    // Release 20261014: the counts tests/test_disclosures.py recomputes
    // from the frozen annotations and payload (50 models; Gemini 4 Argon's
    // and Muse Spark 1.3's rows join on release 20261013's references and
    // exclusions).
    expect(summarizeAuditUniverse(us)).toEqual({
      annotatedRowCount: 8_765,
      legacyThresholdRowCount: 8_765,
      exactMissCount: 8_761,
      annotatedExactMissCount: 8_761,
      annotatedExactHitCount: 4,
      unannotatedBelowFullBoundedScoreCount: 2_329,
    });
  });
});
