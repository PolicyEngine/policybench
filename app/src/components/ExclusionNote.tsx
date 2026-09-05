import type { ReferenceExclusion, ScenarioPrediction } from "../types";
import { formatCurrency } from "../format";
import { binaryFlag } from "../lib/scoring";
import { describeExclusionReason } from "../lib/predictionStatus";

function formatValue(
  value: number,
  isBinary: boolean,
  currencySymbol: "$" | "£",
): string {
  if (isBinary) {
    const flag = binaryFlag(value);
    return flag === null ? "Invalid" : flag === 1 ? "Yes" : "No";
  }
  return formatCurrency(value, currencySymbol);
}

/**
 * Why an output contributes to no model's score. Rendered in the prediction
 * detail dialog for rows the payload marks `scored: false`; the release's
 * exclusion record, when present, supplies the alternative reading and the
 * reference under it.
 */
export default function ExclusionNote({
  pred,
  exclusion,
  isBinary,
  currencySymbol,
}: {
  pred: ScenarioPrediction;
  exclusion?: ReferenceExclusion;
  isBinary: boolean;
  currencySymbol: "$" | "£";
}) {
  const unlistedInput = exclusion?.unlistedInput ?? pred.excludedInput;
  const reason = describeExclusionReason(
    exclusion?.reasonCode ?? pred.excludedReason,
  );
  return (
    <section
      className="mt-4 rounded-lg border border-border-subtle bg-surface px-4 py-3"
      data-testid="exclusion-note"
    >
      <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
        Excluded from scoring
      </div>
      <p className="mt-2 text-sm text-text-secondary leading-relaxed">
        This output is scored for no model: {reason}
        {unlistedInput ? (
          <>
            {" "}
            (
            <code className="font-[family-name:var(--font-mono)] text-[12px]">
              {unlistedInput}
            </code>
            )
          </>
        ) : null}
        . The prediction above is shown for inspection and counts neither for
        nor against this model.
      </p>
      {exclusion ? (
        <>
          <p className="mt-2 text-sm text-text-secondary leading-relaxed">
            {exclusion.alternativeReading} Under that reading the reference is{" "}
            <span className="font-[family-name:var(--font-mono)]">
              {formatValue(exclusion.alternativeValue, isBinary, currencySymbol)}
            </span>{" "}
            rather than the frozen{" "}
            <span className="font-[family-name:var(--font-mono)]">
              {formatValue(exclusion.frozenValue, isBinary, currencySymbol)}
            </span>
            .
          </p>
          <p className="mt-2 text-xs text-text-muted leading-relaxed">
            Both values recomputed with {exclusion.engineVersion}; excluded by
            the developers on {exclusion.decidedOn}.
            {exclusion.note ? ` ${exclusion.note}` : ""}
          </p>
        </>
      ) : null}
    </section>
  );
}
