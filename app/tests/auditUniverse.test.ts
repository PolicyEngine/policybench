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
    // Release 20261009: the counts tests/test_disclosures.py recomputes
    // from the frozen annotations and payload (47 models; the ten outputs
    // ruled on 2026-10-06 and the two Indiana county outputs leave scoring,
    // the outputs the engine upgrade regenerates return to it).
    expect(summarizeAuditUniverse(us)).toEqual({
      annotatedRowCount: 7_507,
      legacyThresholdRowCount: 7_507,
      exactMissCount: 7_503,
      annotatedExactMissCount: 7_503,
      annotatedExactHitCount: 4,
      unannotatedBelowFullBoundedScoreCount: 2_115,
    });
  });
});
