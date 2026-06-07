import assert from "node:assert/strict";
import test from "node:test";
import {
  getFrontierModelsForAvailable,
  isFrontierModel,
} from "../src/modelMeta";

test("frontier models use current Opus when available", () => {
  const models = getFrontierModelsForAvailable([
    "claude-opus-4.8",
    "claude-opus-4.7",
    "gpt-5.5",
  ]);

  assert.equal(models.has("claude-opus-4.8"), true);
  assert.equal(models.has("claude-opus-4.7"), false);
});

test("frontier models fall back to legacy Opus for older result files", () => {
  const models = getFrontierModelsForAvailable(["claude-opus-4.7", "gpt-5.5"]);

  assert.equal(isFrontierModel("claude-opus-4.7"), false);
  assert.equal(models.has("claude-opus-4.7"), true);
});
