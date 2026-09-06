/**
 * The tool_choice: auto sensitivity runs of the Claude rows
 * (sensitivity/claude-thinking-2026-08.md), scored on the same 1,973 outputs
 * the board scores. The board's forced answer-tool call switches Claude's
 * extended thinking off (other reasoning-by-default providers reason
 * regardless); Claude Fable 5.1 rejects forced tool calls and answers as JSON,
 * reasoning in both runs, so its comparison is one of transport. Scores are
 * the pinned three-decimal measurements from sensitivity/data/*.json; round
 * only for display. Each entry's "would rank" is derived from the live board
 * rows at render time, never typed by hand.
 */

export type ServingSensitivity = {
  /** Exact-match score of the tool_choice: auto re-run (pinned, unrounded). */
  autoExact: number;
  /** How the board row was served, in one clause. */
  boardTreatment: string;
  /** What changed in the re-run, in one clause. */
  autoTreatment: string;
  /** Whether the board row itself ran without extended thinking. */
  thinkingSuppressedOnBoard: boolean;
  /** Page carrying the full explanation for this row. */
  noteHref: string;
};

export const SENSITIVITY_DOC_HREF =
  "https://github.com/PolicyEngine/policybench/blob/main/sensitivity/claude-thinking-2026-08.md";
export const NEXT_BOARD_HREF =
  "https://github.com/PolicyEngine/policybench/issues/139";

const FORCED_TOOL =
  "ran under the board's forced answer-tool call, which switches Claude's extended thinking off";

export const SERVING_SENSITIVITY: Record<string, ServingSensitivity> = {
  "claude-fable-5": {
    autoExact: 87.542,
    boardTreatment: `${FORCED_TOOL}, one output per request`,
    autoTreatment:
      "re-run with tool_choice: auto and the whole household in one request",
    thinkingSuppressedOnBoard: true,
    noteHref: SENSITIVITY_DOC_HREF,
  },
  "claude-opus-5": {
    autoExact: 86.201,
    boardTreatment: FORCED_TOOL,
    autoTreatment: "re-run with tool_choice: auto",
    thinkingSuppressedOnBoard: true,
    noteHref: SENSITIVITY_DOC_HREF,
  },
  "claude-sonnet-5": {
    autoExact: 80.775,
    boardTreatment: `${FORCED_TOOL}, one output per request`,
    autoTreatment:
      "re-run with tool_choice: auto and the whole household in one request",
    thinkingSuppressedOnBoard: true,
    noteHref: SENSITIVITY_DOC_HREF,
  },
  "claude-fable-5.1": {
    autoExact: 88.183,
    boardTreatment:
      "rejects forced tool calls, so its row answers as a JSON object and reasons at the provider default",
    autoTreatment:
      "re-run with the answer tool declared under tool_choice: auto (it reasons in both runs, so this compares transports)",
    thinkingSuppressedOnBoard: false,
    noteHref: "/notes/2026-09-01-claude-fable-5-1-added",
  },
};

export function servingSensitivityFor(
  model: string,
): ServingSensitivity | undefined {
  return SERVING_SENSITIVITY[model];
}

/** Signed one-decimal delta from unrounded inputs (display rounding only). */
export function formatDelta(autoExact: number, boardExact: number): string {
  const delta = autoExact - boardExact;
  const rounded = Math.abs(delta).toFixed(1);
  return `${delta < 0 ? "−" : "+"}${rounded}`;
}
