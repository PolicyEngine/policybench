import assert from "node:assert/strict";
import test from "node:test";
import {
  resolveActiveProgramIds,
  selectOnlyProgram,
  toggleProgramSelection,
  weightForProgram,
  weightedProgramScore,
} from "../src/lib/programFilters";

function assertClose(actual: number | undefined, expected: number): void {
  assert.ok(actual !== undefined);
  assert.ok(Math.abs(actual - expected) < 1e-9);
}

test("weightedProgramScore rescales weights over selected programs", () => {
  const weights = {
    federal_income_tax_before_refundable_credits: 0.9,
    snap: 0.1,
  };

  assertClose(
    weightedProgramScore(
      [
        { variable: "federal_income_tax_before_refundable_credits", value: 80 },
        { variable: "snap", value: 20 },
      ],
      weights,
    ),
    74,
  );
  assertClose(
    weightedProgramScore(
      [{ variable: "federal_income_tax_before_refundable_credits", value: 80 }],
      weights,
    ),
    80,
  );
});

test("weightedProgramScore groups person-level eligibility outputs", () => {
  const weights = {
    person_wic_eligible: 0.4,
    snap: 0.6,
  };

  assert.equal(weightForProgram(weights, "head_wic_eligible"), 0.4);
  assertClose(
    weightedProgramScore(
      [
        { variable: "head_wic_eligible", value: 0 },
        { variable: "spouse_wic_eligible", value: 100 },
        { variable: "snap", value: 50 },
      ],
      weights,
    ),
    50,
  );
});

test("program selection normalizes groups and keeps at least one active", () => {
  const options = ["person_wic_eligible", "snap"];

  assert.deepEqual(
    [...resolveActiveProgramIds(options, new Set(["head_wic_eligible"]))],
    ["person_wic_eligible"],
  );
  assert.deepEqual([...selectOnlyProgram("spouse_wic_eligible")], [
    "person_wic_eligible",
  ]);
  assert.deepEqual(
    [
      ...toggleProgramSelection(
        options,
        new Set(["person_wic_eligible"]),
        "head_wic_eligible",
      ),
    ],
    ["person_wic_eligible"],
  );
});
