import { useMemo, useState } from "react";
import type {
  BenchData,
  DashboardBundle,
  GlobalBenchData,
  ModelStat,
  ViewKey,
} from "../types";
import { VIEW_SHORT_LABELS } from "../types";
import {
  MODEL_LABELS,
  MODEL_ORDER,
  getProviderForModel,
} from "../modelMeta";
import ProviderMark from "./ProviderMark";
import {
  SENSITIVITY_VIEWS,
  buildAllRows,
  modelScoresForView,
  viewSupportsSelected,
  type SensitivityViewId,
} from "../lib/sensitivity";
import {
  DEFAULT_DRAWS,
  bootstrapIntervals,
  viewToFilter,
} from "../lib/bootstrap";

function Badge({
  children,
  variant,
}: {
  children: React.ReactNode;
  variant: "primary" | "warning" | "danger" | "success";
}) {
  // Use accessible text tokens (text-warning-text / text-danger-text /
  // text-success-text / text-primary-strong) on -soft fills so badges
  // clear 4.5:1 contrast at the 10px size we render them at.
  const styles = {
    primary: "text-primary-strong bg-primary-soft border-primary/30",
    warning: "text-warning-text bg-warning-soft border-warning/40",
    danger: "text-danger-text bg-danger-soft border-danger/40",
    success: "text-success-text bg-success-soft border-success/30",
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-[10px] font-medium tracking-wide uppercase border ${styles[variant]}`}
    >
      {children}
    </span>
  );
}

function accColor(pct: number): "success" | "primary" | "warning" | "danger" {
  if (pct >= 80) return "success";
  if (pct >= 65) return "primary";
  if (pct >= 50) return "warning";
  return "danger";
}

function fmtRunStability(
  mean?: number,
  std?: number,
  runCount?: number
): string | null {
  if (runCount == null || runCount <= 1 || mean == null || Number.isNaN(mean)) {
    return null;
  }
  const meanLabel = `${mean.toFixed(1)}%`;
  if (std == null || Number.isNaN(std)) {
    return `${meanLabel} over ${runCount} runs`;
  }
  return `${meanLabel} +/- ${std.toFixed(1)} over ${runCount} runs`;
}

function GlobalCountryScores({ model }: { model: ModelStat }) {
  if (!model.countryScores) return null;
  const entries = Object.entries(model.countryScores);
  if (entries.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {entries.map(([country, score]) => (
        <span
          key={country}
          className="inline-flex items-center gap-1 rounded-full border border-border bg-surface px-2 py-1 text-[10px] font-medium tracking-wide uppercase text-text-secondary"
        >
          <span>{VIEW_SHORT_LABELS[country as keyof typeof VIEW_SHORT_LABELS]}</span>
          <span className="font-[family-name:var(--font-mono)] text-text">
            {score.toFixed(1)}%
          </span>
        </span>
      ))}
    </div>
  );
}

type PendingModel = {
  model: string;
  note: string;
};

const PENDING_MODELS: Record<ViewKey, PendingModel[]> = {
  global: [
    { model: "grok-4.20", note: "UK run in progress; US full run pending" },
  ],
  us: [
    { model: "grok-4.20", note: "US full run pending" },
  ],
  uk: [],
};

export default function ModelLeaderboard({
  data,
  selectedView,
  dashboard,
}: {
  data: BenchData | GlobalBenchData;
  selectedView: ViewKey;
  dashboard: DashboardBundle;
}) {
  const isGlobal = selectedView === "global";
  const [sensitivityView, setSensitivityView] =
    useState<SensitivityViewId>("main");
  const [showIntervals, setShowIntervals] = useState(false);

  const allRows = useMemo(() => buildAllRows(dashboard), [dashboard]);

  // Some sensitivity slices have no rows in the selected country (e.g.
  // "Binary only" has zero UK rows; "Binary only" on Global has zero UK
  // rows so the global view cannot be a true cross-country score). In that
  // case we fall back to the canonical Main view so the leaderboard still
  // has a defensible ranking and surface a notice explaining why.
  const sensitivityUnsupportedForView = useMemo(
    () =>
      sensitivityView !== "main" &&
      !viewSupportsSelected(allRows, sensitivityView, selectedView),
    [allRows, selectedView, sensitivityView],
  );
  const effectiveView: SensitivityViewId = sensitivityUnsupportedForView
    ? "main"
    : sensitivityView;

  const sensitivityScores = useMemo(() => {
    return modelScoresForView(allRows, effectiveView, selectedView);
  }, [allRows, effectiveView, selectedView]);

  const sensitivityScoreByModel = useMemo(() => {
    const out = new Map<string, number>();
    for (const entry of sensitivityScores) out.set(entry.model, entry.score);
    return out;
  }, [sensitivityScores]);

  const noTools = useMemo<ModelStat[]>(() => {
    const base = data.modelStats.filter((m) => m.condition === "no_tools");
    if (effectiveView === "main") {
      return [...base].sort((a, b) => b.score - a.score);
    }
    // Reorder + replace score with the sensitivity-view score, dropping models
    // that don't have a score under this slice.
    return base
      .filter((m) => sensitivityScoreByModel.has(m.model))
      .map((m) => ({ ...m, score: sensitivityScoreByModel.get(m.model)! }))
      .sort((a, b) => b.score - a.score);
  }, [data, effectiveView, sensitivityScoreByModel]);

  // Bootstrap intervals are off by default — they roughly triple the
  // first-paint cost and are noise to most readers. Compute on-demand when
  // the user opens the toggle. The Main view uses precomputed household-equal
  // impact scores, which do not have a browser-side bootstrap path yet.
  const intervals = useMemo(() => {
    if (!showIntervals) return new Map();
    if (effectiveView === "main") return new Map();
    return bootstrapIntervals(
      allRows,
      selectedView,
      viewToFilter(effectiveView),
      { draws: DEFAULT_DRAWS, seed: 42 },
    );
  }, [allRows, selectedView, effectiveView, showIntervals]);

  const pendingModels = useMemo<PendingModel[]>(() => {
    const present = new Set(noTools.map((model) => model.model));
    const configured = PENDING_MODELS[selectedView].filter(
      (model) => !present.has(model.model)
    );
    return [...configured].sort((a, b) => {
      const aIndex = MODEL_ORDER.indexOf(a.model as (typeof MODEL_ORDER)[number]);
      const bIndex = MODEL_ORDER.indexOf(b.model as (typeof MODEL_ORDER)[number]);
      return aIndex - bIndex;
    });
  }, [noTools, selectedView]);

  const activeView = SENSITIVITY_VIEWS.find((v) => v.id === sensitivityView)!;

  return (
    <div>
      <div className="eyebrow mb-3 animate-fade-up">Leaderboard</div>
      <h2
        id="leaderboard-heading"
        className="font-[family-name:var(--font-display)] text-4xl md:text-5xl text-text tracking-tight animate-fade-up"
        style={{ animationDelay: "80ms" }}
      >
        {isGlobal ? "Global rankings" : "Model rankings"}
      </h2>
      <p
        className="text-text-secondary mt-3 max-w-xl leading-relaxed animate-fade-up"
        style={{ animationDelay: "160ms" }}
      >
        {isGlobal
          ? "Global scores are equal-weight averages of each model’s US and UK household-equal impact scores. They are not weighted by country population or household count."
          : "Country scores give each household equal weight. Within a household, outputs receive a 30% equal-weight floor plus a 70% weight based on absolute reference impact."}
        {pendingModels.length > 0 && (
          <>
            {" "}
            Pending rows below mark models that are actively being added.
          </>
        )}
      </p>

      <aside
        aria-labelledby="open-set-heading"
        className="mt-5 flex items-start gap-3 rounded-xl border border-warning/30 bg-warning-soft px-4 py-3 text-xs text-text-secondary animate-fade-up"
        style={{ animationDelay: "180ms" }}
      >
        <span
          aria-hidden
          className="mt-0.5 inline-flex h-2 w-2 shrink-0 rounded-full bg-warning"
        />
        <p>
          <strong id="open-set-heading" className="text-text">
            Open-set leaderboard.
          </strong>{" "}
          The public scenario explorer exposes prompts and PolicyEngine
          reference outputs, so future model releases or fine-tunes could
          learn from the released cases. Treat this as a public preview;
          protected held-out claims would require a separate rotating
          evaluation set.
        </p>
      </aside>

      <div
        className="mt-5 flex flex-wrap items-center gap-3 animate-fade-up"
        style={{ animationDelay: "200ms" }}
      >
        <span
          id="leaderboard-view-label"
          className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted"
        >
          View
        </span>
        <div
          role="group"
          aria-labelledby="leaderboard-view-label"
          className="inline-flex flex-wrap items-center gap-1 rounded-full border border-border bg-card p-1"
        >
          {SENSITIVITY_VIEWS.map((view) => {
            const isActive = sensitivityView === view.id;
            const supported =
              view.id === "main" ||
              viewSupportsSelected(allRows, view.id, selectedView);
            const disabled = !supported;
            const disabledTitleSuffix = isGlobal
              ? " (not available for the Global view; switch to US or UK)"
              : selectedView === "uk"
                ? " (no UK rows under this slice; switch to US or Global)"
                : selectedView === "us"
                  ? " (no US rows under this slice; switch to UK or Global)"
                  : "";
            return (
              <button
                key={view.id}
                type="button"
                aria-disabled={disabled || undefined}
                onClick={(event) => {
                  if (disabled) {
                    event.preventDefault();
                    return;
                  }
                  setSensitivityView(view.id);
                }}
                aria-pressed={disabled ? undefined : isActive}
                className={`rounded-full px-3 py-1.5 text-[11px] font-medium transition-colors ${
                  isActive && !disabled
                    ? "bg-primary-strong text-white"
                    : disabled
                      ? "cursor-not-allowed text-text-muted line-through"
                      : "text-text-secondary hover:text-text"
                }`}
                title={
                  disabled
                    ? `${view.description}${disabledTitleSuffix}`
                    : view.description
                }
              >
                {view.label}
              </button>
            );
          })}
        </div>
        <span className="text-[11px] text-text-muted">
          {activeView.description}
        </span>
        <label className="ml-auto inline-flex items-center gap-1.5 text-[11px] text-text-secondary">
          <input
            type="checkbox"
            checked={showIntervals}
            onChange={(event) => setShowIntervals(event.target.checked)}
            disabled={effectiveView === "main"}
            className="h-3.5 w-3.5 rounded border-border accent-primary-strong"
          />
          <span>
            {effectiveView === "main"
              ? "Intervals available on sensitivity views"
              : "Show 95% intervals"}
          </span>
        </label>
      </div>
      {sensitivityUnsupportedForView && (
        <p
          className="mt-3 text-[11px] text-text-muted animate-fade-up"
          style={{ animationDelay: "220ms" }}
        >
          The &ldquo;{
            SENSITIVITY_VIEWS.find((v) => v.id === sensitivityView)?.label ??
              sensitivityView
          }&rdquo; slice has no rows in {
            isGlobal
              ? "at least one country"
              : selectedView === "uk"
                ? "the UK"
                : "the US"
          }, so the leaderboard falls back to the Main view. {
            isGlobal
              ? "Switch to United States or United Kingdom to see this slice on a single country."
              : "Switch to the other country to see this slice."
          }
        </p>
      )}

      <div
        role="region"
        aria-labelledby="leaderboard-heading"
        aria-live="polite"
        aria-atomic="false"
        className="mt-8 space-y-3"
      >
        <p className="sr-only" role="status">
          {`${noTools.length} models, ranked by ${activeView.label} score (${
            isGlobal ? "global" : selectedView === "us" ? "United States" : "United Kingdom"
          })`}
        </p>
        <div
          role="row"
          className={`hidden gap-3 px-4 text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium md:grid ${
            isGlobal ? "md:grid-cols-12" : "md:grid-cols-12"
          }`}
        >
          <div role="columnheader" className="col-span-1">#</div>
          <div role="columnheader" className={isGlobal ? "col-span-5" : "col-span-5"}>Model</div>
          <div role="columnheader" className="col-span-3 text-right">
            {isGlobal ? "Global score" : "Score"}
          </div>
          <div role="columnheader" className="col-span-3 text-right">
            {isGlobal ? "Country scores" : "MAE"}
          </div>
        </div>

        {noTools.map((m, i) => {
          const stabilityLabel = fmtRunStability(
            m.scoreRunMean,
            m.scoreRunStd,
            m.runCount
          );
          const interval = intervals.get(m.model);
          const rankRange =
            interval && interval.rankLower !== interval.rankUpper
              ? `Rank ${interval.rankLower}-${interval.rankUpper}`
              : interval
                ? `Rank ${interval.rankLower}`
                : null;
          const scoreRange = interval
            ? `${interval.lower.toFixed(1)}-${interval.upper.toFixed(1)}`
            : null;
          const intervalAriaLabel = interval
            ? `${rankRange} across bootstrap draws; 95% score interval ${interval.lower.toFixed(1)}% to ${interval.upper.toFixed(1)}%`
            : undefined;
          return (
            <div
              key={m.model}
              role="row"
              aria-label={`Rank ${i + 1}, ${MODEL_LABELS[m.model] || m.model}, score ${m.score.toFixed(1)}%`}
              className="card card-hover px-4 py-4 animate-fade-up"
              style={{ animationDelay: `${240 + i * 80}ms` }}
            >
              <div className="md:hidden">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2.5">
                      <span className="text-text-muted font-[family-name:var(--font-mono)] text-sm">
                        {i + 1}
                      </span>
                      <ProviderMark
                        provider={getProviderForModel(m.model)}
                        size={14}
                        className="flex-shrink-0"
                      />
                      <span className="truncate text-sm font-medium text-text">
                        {MODEL_LABELS[m.model] || m.model}
                      </span>
                    </div>
                    {!isGlobal && stabilityLabel && (
                      <div className="mt-1 pl-6 text-[10px] font-[family-name:var(--font-mono)] text-text-muted">
                        {stabilityLabel}
                      </div>
                    )}
                    {rankRange && (
                      <div
                        className="mt-1 pl-6 text-[10px] font-[family-name:var(--font-mono)] text-text-muted"
                        aria-label={intervalAriaLabel}
                      >
                        {rankRange} · 95% {scoreRange}
                      </div>
                    )}
                  </div>

                  <Badge variant={accColor(m.score)}>{m.score.toFixed(1)}%</Badge>
                </div>

                <div className="mt-3 flex items-center justify-between border-t border-border pt-3">
                  <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
                    {isGlobal ? "Country scores" : "Avg abs error"}
                  </div>
                  {isGlobal ? (
                    <GlobalCountryScores model={m} />
                  ) : (
                    <div className="font-[family-name:var(--font-mono)] text-sm text-info">
                      ${Math.round(m.mae ?? 0).toLocaleString()}
                    </div>
                  )}
                </div>
              </div>

              <div className="hidden items-center gap-3 md:grid md:grid-cols-12">
                <div className="col-span-1">
                  <span className="text-text-muted font-[family-name:var(--font-mono)] text-sm">
                    {i + 1}
                  </span>
                </div>

                <div className="col-span-5 flex items-center gap-2.5">
                  <ProviderMark
                    provider={getProviderForModel(m.model)}
                    size={14}
                    className="flex-shrink-0"
                  />
                  <span className="text-text font-medium text-sm">
                    {MODEL_LABELS[m.model] || m.model}
                  </span>
                </div>

                <div className="col-span-3 text-right">
                  <Badge variant={accColor(m.score)}>
                    {m.score.toFixed(1)}%
                  </Badge>
                  {rankRange && (
                    <div
                      className="text-[10px] text-text-muted font-[family-name:var(--font-mono)] mt-1"
                      title="Household-resampling 95% interval (400 draws, seed 42)"
                      aria-label={intervalAriaLabel}
                    >
                      {rankRange} · 95% {scoreRange}
                    </div>
                  )}
                  {!isGlobal && stabilityLabel && (
                    <div className="text-[10px] text-text-muted font-[family-name:var(--font-mono)] mt-1">
                      {stabilityLabel}
                    </div>
                  )}
                </div>

                <div className="col-span-3 text-right">
                  {isGlobal ? (
                    <GlobalCountryScores model={m} />
                  ) : (
                    <div className="font-[family-name:var(--font-mono)] text-sm text-info">
                      ${Math.round(m.mae ?? 0).toLocaleString()}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {pendingModels.map((m, i) => (
          <div
            key={`pending-${m.model}`}
            className="rounded-2xl border border-dashed border-border bg-card/50 px-4 py-4 animate-fade-up opacity-80"
            style={{ animationDelay: `${240 + (noTools.length + i) * 80}ms` }}
          >
            <div className="md:hidden">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2.5">
                    <span className="text-text-muted font-[family-name:var(--font-mono)] text-sm">
                      -
                    </span>
                    <ProviderMark
                      provider={getProviderForModel(m.model)}
                      size={14}
                      className="flex-shrink-0"
                    />
                    <span className="truncate text-sm font-medium text-text">
                      {MODEL_LABELS[m.model] || m.model}
                    </span>
                  </div>
                  <div className="mt-1 pl-6 text-[10px] font-[family-name:var(--font-mono)] text-text-muted">
                    {m.note}
                  </div>
                </div>

                <Badge variant="warning">Pending</Badge>
              </div>
            </div>

            <div className="hidden items-center gap-3 md:grid md:grid-cols-12">
              <div className="col-span-1">
                <span className="text-text-muted font-[family-name:var(--font-mono)] text-sm">
                  -
                </span>
              </div>

              <div className="col-span-5 flex items-center gap-2.5">
                <ProviderMark
                  provider={getProviderForModel(m.model)}
                  size={14}
                  className="flex-shrink-0"
                />
                <span className="text-text font-medium text-sm">
                  {MODEL_LABELS[m.model] || m.model}
                </span>
              </div>

              <div className="col-span-3 text-right">
                <Badge variant="warning">Pending</Badge>
              </div>

              <div className="col-span-3 text-right">
                <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted">
                  {m.note}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
