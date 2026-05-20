import assert from "node:assert/strict";
import test from "node:test";
import { binaryFlag, scorePrediction } from "../src/lib/scoring";

function assertClose(actual: number, expected: number): void {
  assert.ok(Math.abs(actual - expected) < 1e-9);
}

test("scorePrediction uses bounded continuous amount score", () => {
  assertClose(scorePrediction("income_tax", "us", 100, 100), 1);
  assertClose(scorePrediction("income_tax", "us", 100, 104), 0.96);
  assertClose(scorePrediction("income_tax", "us", 100, 112), 0.88);
  assertClose(scorePrediction("income_tax", "us", 100, 250), 0);
});

test("scorePrediction gives exact zero credit only for zero references", () => {
  assertClose(scorePrediction("snap", "us", 0, 0), 1);
  assertClose(scorePrediction("snap", "us", 0, 0.5), 0);
});

test("scorePrediction requires exact 0/1 flags for binary outputs", () => {
  assertClose(scorePrediction("head_medicaid_eligible", "us", 1, 1), 1);
  assertClose(scorePrediction("head_medicaid_eligible", "us", 1, 0), 0);
  assertClose(scorePrediction("head_medicaid_eligible", "us", 1, 0.6), 0);
  assertClose(scorePrediction("head_medicaid_eligible", "us", 1, 0.5), 0);
  assertClose(scorePrediction("head_medicaid_eligible", "us", 0, 0.5), 0);
});

test("binaryFlag only accepts exact 0/1 flags", () => {
  assert.equal(binaryFlag(0), 0);
  assert.equal(binaryFlag(1), 1);
  assert.equal(binaryFlag(0.49), null);
  assert.equal(binaryFlag(0.5), null);
});
