/**
 * The tool_choice: auto sensitivity runs of the Claude rows
 * (sensitivity/claude-thinking-2026-08.md), scored on the same outputs
 * the board scores. The board's forced answer-tool call switches Claude's
 * extended thinking off (other reasoning-by-default providers reason
 * regardless); Claude Fable 5.1 rejects forced tool calls and answers as JSON,
 * reasoning in both runs, so its comparison is one of transport. Claude Opus
 * 5.5 and Claude Sonnet 5.5 reject forced calls the same way and have no auto
 * re-run. Claude Haiku 5.5 accepts forced calls, so its board row is a
 * forced-tool row like Claude Opus 5's. Scores are
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
    autoExact: 93.173,
    boardTreatment: `${FORCED_TOOL}, one output per request`,
    autoTreatment:
      "re-run with tool_choice: auto and the whole household in one request",
    thinkingSuppressedOnBoard: true,
    noteHref: SENSITIVITY_DOC_HREF,
  },
  "claude-opus-5": {
    autoExact: 91.551,
    boardTreatment: FORCED_TOOL,
    autoTreatment: "re-run with tool_choice: auto",
    thinkingSuppressedOnBoard: true,
    noteHref: SENSITIVITY_DOC_HREF,
  },
  "claude-sonnet-5": {
    autoExact: 86.307,
    boardTreatment: `${FORCED_TOOL}, one output per request`,
    autoTreatment:
      "re-run with tool_choice: auto and the whole household in one request",
    thinkingSuppressedOnBoard: true,
    noteHref: SENSITIVITY_DOC_HREF,
  },
  "claude-fable-5.1": {
    autoExact: 93.545,
    boardTreatment:
      "rejects forced tool calls, so its row answers as a JSON object and reasons at the provider default",
    autoTreatment:
      "re-run with the answer tool declared under tool_choice: auto (it reasons in both runs, so this compares transports)",
    thinkingSuppressedOnBoard: false,
    noteHref: "/notes/2026-09-01-claude-fable-5-1-added",
  },
  "claude-haiku-5.5": {
    autoExact: 90.386,
    boardTreatment: FORCED_TOOL,
    autoTreatment: "re-run with tool_choice: auto",
    thinkingSuppressedOnBoard: true,
    noteHref: SENSITIVITY_DOC_HREF,
  },
};

export function servingSensitivityFor(
  model: string,
): ServingSensitivity | undefined {
  return SERVING_SENSITIVITY[model];
}

/** How many rows carry an auto re-run, and how many of those board rows ran
 * without extended thinking; the leaderboard's sensitivity copy states both. */
export function servingSensitivityCounts(
  entries: Record<string, ServingSensitivity> = SERVING_SENSITIVITY,
): { reruns: number; thinkingSuppressed: number } {
  const values = Object.values(entries);
  return {
    reruns: values.length,
    thinkingSuppressed: values.filter((entry) => entry.thinkingSuppressedOnBoard)
      .length,
  };
}

/** Signed one-decimal delta from unrounded inputs (display rounding only). */
export function formatDelta(autoExact: number, boardExact: number): string {
  const delta = autoExact - boardExact;
  const rounded = Math.abs(delta).toFixed(1);
  return `${delta < 0 ? "−" : "+"}${rounded}`;
}
