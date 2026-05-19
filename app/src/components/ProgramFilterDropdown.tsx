import type { ProgramOption } from "../lib/programFilters";

type SharedProps = {
  options: ProgramOption[];
  activeProgramIds: Set<string>;
  description: string;
  onReset: () => void;
  onToggle: (variable: string) => void;
  onSelectOnly: (variable: string) => void;
};

type ProgramFilterDropdownProps = SharedProps & {
  summary: string;
  className?: string;
  animationDelay?: string;
};

/** Inner program-filter UI without a disclosure wrapper.
 *
 * Used directly inside the leaderboard's unified "Options" disclosure, and
 * wrapped in a standalone `<details>` by ``ProgramFilterDropdown`` for the
 * heatmap and scenario sections.
 */
export function ProgramFilterPanel({
  options,
  activeProgramIds,
  description,
  onReset,
  onToggle,
  onSelectOnly,
}: SharedProps) {
  if (options.length === 0) return null;
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-xs leading-relaxed text-text-secondary">
          {description}
        </p>
        <button
          type="button"
          onClick={onReset}
          className="rounded-full border border-border bg-surface px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.12em] text-text-secondary transition-colors hover:border-primary-strong/40 hover:text-text"
        >
          All programs
        </button>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {options.map((option) => {
          const checked = activeProgramIds.has(option.variable);
          return (
            <div
              key={option.variable}
              className={`flex min-w-0 items-center gap-2 rounded-lg border px-3 py-2 transition-colors ${
                checked
                  ? "border-primary-strong/30 bg-primary-soft/50"
                  : "border-border-subtle bg-surface/60"
              }`}
            >
              <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => onToggle(option.variable)}
                  className="h-3.5 w-3.5 rounded border-border text-primary-strong"
                />
                <span className="truncate text-xs text-text-secondary">
                  {option.label}
                </span>
              </label>
              <button
                type="button"
                onClick={() => onSelectOnly(option.variable)}
                className="shrink-0 rounded-full border border-border bg-card px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-text-muted transition-colors hover:border-primary-strong/40 hover:text-text"
              >
                Only
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Standalone disclosure around ``ProgramFilterPanel``.
 *
 * Used in the program heatmap and scenario explorer, where the program filter
 * is the only adjustable control. The leaderboard collapses this into its
 * unified "Options" disclosure instead.
 */
export default function ProgramFilterDropdown({
  options,
  activeProgramIds,
  summary,
  description,
  onReset,
  onToggle,
  onSelectOnly,
  className = "",
  animationDelay,
}: ProgramFilterDropdownProps) {
  if (options.length === 0) return null;

  return (
    <details
      className={`group rounded-2xl border border-border bg-card/40 animate-fade-up ${className}`}
      style={animationDelay ? { animationDelay } : undefined}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs text-text-secondary hover:text-text">
        <span className="flex min-w-0 items-center gap-2">
          <svg
            aria-hidden
            viewBox="0 0 12 12"
            width="10"
            height="10"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="shrink-0 transition-transform group-open:rotate-90"
          >
            <polyline points="4 2 8 6 4 10" />
          </svg>
          <span className="shrink-0 text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
            Program filter
          </span>
          <span className="truncate text-text-muted">{summary}</span>
        </span>
      </summary>

      <div className="border-t border-border-subtle px-4 py-4">
        <ProgramFilterPanel
          options={options}
          activeProgramIds={activeProgramIds}
          description={description}
          onReset={onReset}
          onToggle={onToggle}
          onSelectOnly={onSelectOnly}
        />
      </div>
    </details>
  );
}
