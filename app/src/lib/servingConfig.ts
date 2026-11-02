/**
 * Counts and rosters the app copy states about the live board's serving
 * treatments, read from the frozen serving configuration
 * (src/model-serving-config.json, which prepare-data copies from
 * paper/snapshot/20260501/model_serving_config.json) rather than typed by hand.
 */
import frozenServingConfig from "../model-serving-config.json";

export type ServingTreatment = {
  answer_contract: string;
  request_shape: string;
  tool_choice: string | null;
};

export type ServingConfiguration = {
  models: Record<string, ServingTreatment>;
};

export const SERVING_CONFIG =
  frozenServingConfig as unknown as ServingConfiguration;

/** Rows that answer subsets of the requested outputs in each request. */
export function chunkedServingModels(
  config: ServingConfiguration = SERVING_CONFIG,
): string[] {
  return Object.entries(config.models)
    .filter(([, treatment]) => treatment.request_shape !== "whole scenario")
    .map(([model]) => model);
}

/**
 * Claude rows on the JSON answer contract. A Claude row defaults to the tool
 * contract (policybench/model_cards.py answer_contract_for); each Claude card
 * that sets JSON does so because Anthropic's API rejects a forced tool call
 * for that model.
 */
export function jsonContractClaudeModels(
  config: ServingConfiguration = SERVING_CONFIG,
): string[] {
  return Object.entries(config.models)
    .filter(
      ([model, treatment]) =>
        model.startsWith("claude-") && treatment.answer_contract === "json",
    )
    .map(([model]) => model);
}

const NUMBER_WORDS = [
  "zero",
  "one",
  "two",
  "three",
  "four",
  "five",
  "six",
  "seven",
  "eight",
  "nine",
  "ten",
  "eleven",
  "twelve",
  "thirteen",
  "fourteen",
  "fifteen",
  "sixteen",
  "seventeen",
  "eighteen",
  "nineteen",
  "twenty",
];

/** A whole number as a word up to twenty, as digits beyond. */
export function numberWord(value: number): string {
  return Number.isInteger(value) && value >= 0 && value < NUMBER_WORDS.length
    ? NUMBER_WORDS[value]
    : value.toLocaleString("en-US");
}

export function capitalizeFirst(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** "A", "A and B", "A, B and C". */
export function joinWithAnd(items: string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}
