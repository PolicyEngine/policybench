import { getVariableLabel, type CountryCode } from "../types";
import { formatShare, type ProgramBar } from "../lib/programChart";

function formatPct(value: number | null): string {
  return value == null || Number.isNaN(value) ? "—" : `${value.toFixed(1)}%`;
}

/**
 * A model's exact-match rate on every output group, one thin bar per program
 * in descending order, with the program's share of the headline weight beside
 * it. Plain HTML: the list is the accessible structure, each row's title
 * carries the companion numbers, and the table below the chart is the
 * tabular twin.
 */
export default function ProgramBars({
  bars,
  country,
}: {
  bars: ProgramBar[];
  country: CountryCode;
}) {
  return (
    <ol className="mt-3 space-y-1.5" aria-label="Exact-match rate by program">
      {bars.map((bar) => {
        const rate = bar.exact ?? 0;
        const share = formatShare(bar.weightShare);
        const tooltip = [
          `${getVariableLabel(bar.variable, country)}: ${formatPct(bar.exact)} exact`,
          `${formatPct(bar.within1pct)} within 1%`,
          `${bar.n.toLocaleString("en-US")} outputs`,
          share ? `${share} of the headline weight` : "",
        ]
          .filter(Boolean)
          .join(" · ");
        return (
          <li
            key={bar.variable}
            title={tooltip}
            className="grid grid-cols-[minmax(0,11rem)_1fr_3.5rem_3rem] items-center gap-x-3 text-xs sm:grid-cols-[minmax(0,14rem)_1fr_3.5rem_3rem]"
          >
            <span className="truncate text-text-secondary">
              {getVariableLabel(bar.variable, country)}
            </span>
            <span
              className="relative block h-2.5 overflow-hidden rounded-r-md bg-surface"
              aria-hidden="true"
            >
              <span
                className="absolute inset-y-0 left-0 rounded-r-md bg-primary"
                style={{ width: `${Math.max(0, Math.min(100, rate))}%` }}
              />
            </span>
            <span className="text-right font-[family-name:var(--font-mono)] text-text">
              {formatPct(bar.exact)}
            </span>
            <span
              className="text-right font-[family-name:var(--font-mono)] text-[10px] text-text-muted"
              title={share ? "Share of the headline weight" : undefined}
            >
              {share}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
