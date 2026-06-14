import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { MODEL_DISPLAY_ORDER, MODEL_LABELS } from "../src/modelMeta";

type DashboardCountryPayload = {
  modelStats?: Array<{ model: string }>;
};

type DashboardPayload = {
  countries?: Record<string, DashboardCountryPayload>;
};

test("published dashboard data models have display metadata", () => {
  const data = JSON.parse(
    readFileSync(new URL("../src/data.json", import.meta.url), "utf8"),
  ) as DashboardPayload;
  const modelOrder = MODEL_DISPLAY_ORDER as readonly string[];

  for (const [country, payload] of Object.entries(data.countries ?? {})) {
    const models = new Set(
      (payload.modelStats ?? []).map((row) => row.model).filter(Boolean),
    );
    for (const model of models) {
      assert.ok(MODEL_LABELS[model], `${country} ${model} missing label`);
      assert.ok(modelOrder.includes(model), `${country} ${model} missing order`);
    }
  }
});
