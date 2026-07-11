import { describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ProviderMark from "../src/components/ProviderMark";
import {
  FRONTIER_MODELS,
  MODEL_LABELS,
  PROVIDER_LABELS,
  frontierModelsFor,
  getProviderForModel,
  orderModels,
  type ProviderKey,
} from "../src/modelMeta";

describe("model metadata", () => {
  test.each([
    ["gpt-5.6-sol", "GPT-5.6 Sol", "openai"],
    ["gpt-5.6-terra", "GPT-5.6 Terra", "openai"],
    ["gpt-5.6-luna", "GPT-5.6 Luna", "openai"],
    ["kimi-k2.6", "Kimi K2.6", "moonshot"],
    ["glm-5.2", "GLM-5.2", "zai"],
    ["minimax-m3", "MiniMax M3", "minimax"],
    ["qwen-3.7-max", "Qwen 3.7 Max", "alibaba"],
  ] as const)("maps %s to its label and provider", (model, label, provider) => {
    expect(MODEL_LABELS[model]).toBe(label);
    expect(getProviderForModel(model)).toBe(provider);
  });

  test("labels the added providers", () => {
    expect(PROVIDER_LABELS).toMatchObject({
      alibaba: "Alibaba",
      minimax: "MiniMax",
      moonshot: "Moonshot AI",
      zai: "Z.ai",
    });
  });

  test("renders a visible icon for every provider", () => {
    for (const provider of Object.keys(PROVIDER_LABELS) as ProviderKey[]) {
      const markup = renderToStaticMarkup(
        createElement(ProviderMark, { provider }),
      );
      expect(markup).toContain("<svg");
      expect(markup).toContain(`aria-label="${PROVIDER_LABELS[provider]}"`);
    }
  });

  test("uses Sol as the current OpenAI frontier model", () => {
    expect(FRONTIER_MODELS).toContain("gpt-5.6-sol");
    expect(FRONTIER_MODELS).not.toContain("gpt-5.5");
    expect(FRONTIER_MODELS).not.toContain("gpt-5.6-terra");
    expect(FRONTIER_MODELS).not.toContain("gpt-5.6-luna");
  });

  test("falls back to GPT-5.5 for a frozen bundle without Sol", () => {
    expect(frontierModelsFor(["gpt-5.5", "gpt-5.4-mini"])).toEqual([
      "gpt-5.5",
    ]);
    expect(frontierModelsFor(["gpt-5.6-sol", "gpt-5.5"])).toEqual([
      "gpt-5.6-sol",
    ]);
  });

  test("falls back to another represented provider model", () => {
    expect(frontierModelsFor(["gpt-5.6-terra"])).toEqual(["gpt-5.6-terra"]);
  });

  test("falls back to Opus 4.8 for a frozen bundle without Fable", () => {
    expect(frontierModelsFor(["claude-opus-4.8", "claude-opus-4.7"])).toEqual([
      "claude-opus-4.8",
    ]);
  });

  test("gives every represented provider a frontier model", () => {
    const models = [
      "claude-fable-5",
      "gpt-5.6-sol",
      "grok-4.3",
      "grok-4.5",
      "gemini-3.1-pro-preview",
      "deepseek-v4-pro",
      "kimi-k2.6",
      "glm-5.2",
      "minimax-m3",
      "qwen-3.7-max",
    ];
    expect(new Set(frontierModelsFor(models))).toEqual(new Set(models));
  });
});

describe("orderModels", () => {
  test("orders known models first and appends unknown models deterministically", () => {
    expect(
      orderModels([
        "future-model-z",
        "gpt-5.5",
        "future-model-a",
        "claude-fable-5",
        "future-model-z",
      ]),
    ).toEqual([
      "claude-fable-5",
      "gpt-5.5",
      "future-model-a",
      "future-model-z",
    ]);
  });
});
