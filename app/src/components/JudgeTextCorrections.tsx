import {
  JUDGE_TEXT_ERRATA_URL,
  rowSpan,
  type JudgeTextErratum,
} from "../lib/judgeTextErrata";

/**
 * PolicyBench's corrections to statements in a judge's text, rendered
 * beneath the text they correct. Pass `model` for a row sentence, so a row
 * with its own quoted span shows that span. The judge's text itself is left
 * as published.
 */
export default function JudgeTextCorrections({
  errata,
  model,
}: {
  errata: JudgeTextErratum[];
  model?: string;
}) {
  if (errata.length === 0) return null;
  return (
    <div className="mt-2 space-y-2">
      {errata.map((entry) => {
        const span = model ? rowSpan(entry, model) : entry.span;
        return (
          <section
            key={`${entry.where}|${entry.span}`}
            className="rounded-lg border border-border-subtle bg-surface px-4 py-3"
            data-testid="judge-text-correction"
          >
            <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
              Correction from PolicyBench
            </div>
            <p className="mt-2 text-sm text-text-secondary leading-relaxed">
              <span className="text-text-muted">On &ldquo;{span}&rdquo;:</span>{" "}
              {entry.correction}{" "}
              <a
                href={JUDGE_TEXT_ERRATA_URL}
                className="underline underline-offset-2 hover:text-text"
              >
                Errata
              </a>
            </p>
          </section>
        );
      })}
    </div>
  );
}
