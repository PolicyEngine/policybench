import errataJson from "../judgeTextErrata.json";
import { MODEL_LABELS } from "../modelMeta";

/**
 * PolicyBench's errata for the judge's texts: statements in the case notes and
 * row sentences of the live release that a check found wrong, each with a
 * correction. judgeTextErrata.json is generated with the public errata page
 * from the same records; the judge's texts themselves stay as published.
 */
export const JUDGE_TEXT_ERRATA_URL =
  "https://github.com/PolicyEngine/policybench/blob/main/docs/fable52/judge_text_errata.md";

/**
 * The fixed note the audit writes, with no judge, for a case whose wrong rows
 * all returned no parseable answer (policybench/audit.py collect_audit).
 */
export const PARSE_FAILURE_NOTE =
  "All wrong responses were missing or unparseable predictions.";

/**
 * The judge models that wrote the live board's audit notes, as the frozen
 * manifest's audit_annotation_artifacts.judge_provenance records them.
 */
export const AUDIT_JUDGE_MODELS = [
  "gpt-5.6-sol",
  "claude-opus-5",
  "claude-opus-5.5",
] as const;

export type JudgeTextErratum = {
  cell: string;
  scenarioId: string;
  variable: string;
  /** Where the text sits, as the errata page states it. */
  where: string;
  /** The text sits in the case note. */
  caseNote: boolean;
  /** The text sits in the case note's reference hypothesis field. */
  referenceHypothesis: boolean;
  /** App ids of the model rows that `where` names. */
  models: string[];
  /** Row names `where` gives that match no board display name. */
  unresolvedRows: string[];
  /** The text as the errata page publishes it. */
  text: string;
  /** The quoted span the shown text contains. */
  span: string;
  /** A row's own span, where it differs from `span`. */
  rowSpans: Record<string, string>;
  correction: string;
  source: string;
  scoring: string;
};

export type JudgeTextErrataFile = {
  release: string;
  page: string;
  note: string;
  entries: JudgeTextErratum[];
};

// The generated file's literal types (an empty rowSpans, say) do not narrow
// to this shape; tests/judgeTextErrata.test.ts checks every entry instead.
export const JUDGE_TEXT_ERRATA = errataJson as unknown as JudgeTextErrataFile;

/**
 * The errata for one output on the board being shown. They were checked
 * against the live release's texts, so an archived board gets none.
 */
export function judgeTextErrataForCell(
  scenarioId: string,
  variable: string,
  versionId: string,
  liveVersionId: string,
  file: JudgeTextErrataFile = JUDGE_TEXT_ERRATA,
): JudgeTextErratum[] {
  if (versionId !== liveVersionId) return [];
  return file.entries.filter(
    (entry) => entry.scenarioId === scenarioId && entry.variable === variable,
  );
}

/** The span an erratum quotes from one model's row sentence. */
export function rowSpan(entry: JudgeTextErratum, model: string): string {
  return entry.rowSpans[model] ?? entry.span;
}

/**
 * The errata on one model's row sentence: entries that name the row and whose
 * quoted span the shown sentence contains, so a correction never attaches to
 * a text that is not there.
 */
export function rowErrata(
  entries: JudgeTextErratum[],
  model: string,
  rowText: string | undefined,
): JudgeTextErratum[] {
  if (!rowText) return [];
  return entries.filter(
    (entry) =>
      entry.models.includes(model) && rowText.includes(rowSpan(entry, model)),
  );
}

/**
 * The errata on a case note: entries placed on the note whose quoted span the
 * shown note contains.
 */
export function caseNoteErrata(
  entries: JudgeTextErratum[],
  caseNote: string | undefined,
): JudgeTextErratum[] {
  if (!caseNote) return [];
  return entries.filter(
    (entry) => entry.caseNote && caseNote.includes(entry.span),
  );
}

/** "GPT-5.6 Sol, Claude Opus 5 or Claude Opus 5.5". */
export function auditJudgeNames(): string {
  const names = AUDIT_JUDGE_MODELS.map((model) => MODEL_LABELS[model] ?? model);
  return `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}`;
}

/**
 * Whether a row's audit note on the shown board began as a judge model's text:
 * the live board's notes did, except the fixed note for unparseable answers.
 * Some of them show wording PolicyBench amended later
 * (annotations/.../us_wording-amendments.json), and the payload does not mark
 * which, so the line under every such note says so.
 */
export function isJudgeWrittenNote(
  annotation: string | undefined,
  versionId: string,
  liveVersionId: string,
): boolean {
  return (
    !!annotation &&
    versionId === liveVersionId &&
    annotation.trim() !== PARSE_FAILURE_NOTE
  );
}
