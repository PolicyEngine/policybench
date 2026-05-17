import { useMemo, useState } from "react";
import type {
  BenchData,
  DashboardBundle,
  GlobalBenchData,
  ModelStat,
  ViewKey,
} from "../types";
import { VIEW_SHORT_LABELS, getVariableLabel } from "../types";
import {
  MODEL_LABELS,
  MODEL_ORDER,
  PROVIDER_LABELS,
  getProviderForModel,
  isFrontierModel,
  type ProviderKey,
} from "../modelMeta";
import ProviderMark from "./ProviderMark";
import {
  SENSITIVITY_VIEWS,
  modelScoresForView,
  viewSupportsSelected,
  type SensitivityViewId,
} from "../lib/sensitivity";

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
    useState<SensitivityViewId>("household");
  // Default: frontier-only, no provider filter. The benchmark currently has
  // 12 models; "frontier" narrows to one flagship per provider for a
  // scannable top-line read.
  const [frontierOnly, setFrontierOnly] = useState(true);
  const [providerFilter, setProviderFilter] = useState<Set<ProviderKey>>(
    () => new Set(),
  );

  // Defensive: if a model's payload doesn't include the requested view (stale
  // data.json), fall back to the canonical Household view so the leaderboard
  // still has a defensible ranking.
  const sensitivityUnsupportedForView = useMemo(
    () =>
      sensitivityView !== "household" &&
      !viewSupportsSelected(dashboard, sensitivityView, selectedView),
    [dashboard, selectedView, sensitivityView],
  );
  const effectiveView: SensitivityViewId = sensitivityUnsupportedForView
    ? "household"
    : sensitivityView;

  const sensitivityScores = useMemo(
    () => modelScoresForView(dashboard, effectiveView, selectedView),
    [dashboard, effectiveView, selectedView],
  );

  const sensitivityScoreByModel = useMemo(() => {
    const out = new Map<string, number>();
    for (const entry of sensitivityScores) out.set(entry.model, entry.score);
    return out;
  }, [sensitivityScores]);

  const filterModel = (model: string): boolean => {
    if (frontierOnly && !isFrontierModel(model)) return false;
    if (providerFilter.size > 0) {
      const provider = getProviderForModel(model);
      if (!provider || !providerFilter.has(provider)) return false;
    }
    return true;
  };

  const noTools = useMemo<ModelStat[]>(() => {
    const base = data.modelStats
      .filter((m) => m.condition === "no_tools")
      .filter((m) => filterModel(m.model));
    if (effectiveView === "household") {
      return [...base].sort((a, b) => b.score - a.score);
    }
    // Replace the score with the selected view's precomputed value, drop
    // models without one.
    return base
      .filter((m) => sensitivityScoreByModel.has(m.model))
      .map((m) => ({ ...m, score: sensitivityScoreByModel.get(m.model)! }))
      .sort((a, b) => b.score - a.score);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, effectiveView, sensitivityScoreByModel, frontierOnly, providerFilter]);

  const pendingModels = useMemo<PendingModel[]>(() => {
    const present = new Set(noTools.map((model) => model.model));
    const configured = PENDING_MODELS[selectedView]
      .filter((model) => !present.has(model.model))
      .filter((model) => filterModel(model.model));
    return [...configured].sort((a, b) => {
      const aIndex = MODEL_ORDER.indexOf(a.model as (typeof MODEL_ORDER)[number]);
      const bIndex = MODEL_ORDER.indexOf(b.model as (typeof MODEL_ORDER)[number]);
      return aIndex - bIndex;
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [noTools, selectedView, frontierOnly, providerFilter]);

  const activeView = SENSITIVITY_VIEWS.find((v) => v.id === sensitivityView)!;

  // Per-variable weights table. Available on country payloads only; global
  // (US + UK) is intentionally skipped because weights differ between
  // countries and combining them would be misleading.
  const weights = !isGlobal && "globalWeights" in data ? data.globalWeights : undefined;
  const weightsCountry =
    !isGlobal && "country" in data ? data.country : undefined;

  const weightedVariables = useMemo(() => {
    if (!weights) return [] as string[];
    const all = new Set<string>();
    for (const view of ["household", "aggregate", "equal"] as const) {
      const map = weights[view];
      if (map) Object.keys(map).forEach((v) => all.add(v));
    }
    const ranked = Array.from(all).map((v) => ({
      v,
      key: weights[effectiveView]?.[v] ?? 0,
    }));
    ranked.sort((a, b) => b.key - a.key);
    return ranked.map((r) => r.v);
  }, [weights, effectiveView]);

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
          ? "Global scores are equal-weight averages of each model’s US and UK bounded scores. They are not weighted by country population or household count."
          : "Country scores give each household equal weight. Each variable's weight is the mean across households of |ref| / max(|household_net_income|, Σ |ref|), renormalized so the global weights sum to one."}
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
        className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-3 animate-fade-up"
        style={{ animationDelay: "190ms" }}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span
            id="leaderboard-filter-label"
            className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted"
          >
            Show
          </span>
          <button
            type="button"
            onClick={() => setFrontierOnly((v) => !v)}
            aria-pressed={frontierOnly}
            className={`rounded-full border px-3 py-1 text-[11px] font-medium transition-colors ${
              frontierOnly
                ? "border-primary-strong bg-primary-strong text-white"
                : "border-border bg-card text-text-secondary hover:text-text"
            }`}
            title="Show only one frontier flagship per provider (Opus 4.7, GPT-5.5, Grok 4.3, Gemini 3.1 Pro Preview)"
          >
            Frontier only
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span
            id="leaderboard-provider-label"
            className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted"
          >
            Provider
          </span>
          <div
            role="group"
            aria-labelledby="leaderboard-provider-label"
            className="inline-flex flex-wrap items-center gap-1"
          >
            {(Object.keys(PROVIDER_LABELS) as ProviderKey[]).map((provider) => {
              const isActive = providerFilter.has(provider);
              return (
                <button
                  key={provider}
                  type="button"
                  onClick={() => {
                    setProviderFilter((prev) => {
                      const next = new Set(prev);
                      if (next.has(provider)) next.delete(provider);
                      else next.add(provider);
                      return next;
                    });
                  }}
                  aria-pressed={isActive}
                  className={`rounded-full border px-3 py-1 text-[11px] font-medium transition-colors ${
                    isActive
                      ? "border-primary-strong bg-primary-soft text-primary-strong"
                      : "border-border bg-card text-text-secondary hover:text-text"
                  }`}
                >
                  {PROVIDER_LABELS[provider]}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div
        className="mt-3 flex flex-wrap items-center gap-3 animate-fade-up"
        style={{ animationDelay: "200ms" }}
      >
        <span
          id="leaderboard-view-label"
          className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted"
        >
          Weighting
        </span>
        <div
          role="group"
          aria-labelledby="leaderboard-view-label"
          className="inline-flex flex-wrap items-center gap-1 rounded-full border border-border bg-card p-1"
        >
          {SENSITIVITY_VIEWS.map((view) => {
            const isActive = sensitivityView === view.id;
            const supported =
              view.id === "household" ||
              viewSupportsSelected(dashboard, view.id, selectedView);
            const disabled = !supported;
            const disabledTitleSuffix = " (not available on this slice)";
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
      </div>
      {sensitivityUnsupportedForView && (
        <p
          className="mt-3 text-[11px] text-text-muted animate-fade-up"
          style={{ animationDelay: "220ms" }}
        >
          The &ldquo;{
            SENSITIVITY_VIEWS.find((v) => v.id === sensitivityView)?.label ??
              sensitivityView
          }&rdquo; view is not available on this slice; the leaderboard falls
          back to the Household view.
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

        {noTools.length === 0 && pendingModels.length === 0 && (
          <div
            role="status"
            className="card px-4 py-6 text-center text-sm text-text-secondary animate-fade-up"
          >
            No models match these filters.{" "}
            <button
              type="button"
              onClick={() => {
                setFrontierOnly(false);
                setProviderFilter(new Set());
              }}
              className="text-primary-strong underline-offset-2 hover:underline"
            >
              Clear filters
            </button>
          </div>
        )}

        {noTools.map((m, i) => {
          const stabilityLabel = fmtRunStability(
            m.scoreRunMean,
            m.scoreRunStd,
            m.runCount
          );
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

      {weights && weightedVariables.length > 0 && weightsCountry && (
        <details
          className="mt-8 group rounded-2xl border border-border bg-card/40 animate-fade-up"
          style={{ animationDelay: "320ms" }}
        >
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-xs text-text-secondary hover:text-text">
            <span className="flex items-center gap-2">
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
                className="transition-transform group-open:rotate-90"
              >
                <polyline points="4 2 8 6 4 10" />
              </svg>
              <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
                Per-variable weights
              </span>
              <span className="text-text-muted">
                {weightedVariables.length} variables, sorted by {activeView.label}
              </span>
            </span>
          </summary>
          <div className="overflow-x-auto border-t border-border-subtle">
            <table className="min-w-full text-sm">
              <thead className="bg-bg/40">
                <tr>
                  <th
                    scope="col"
                    className="px-4 py-2 text-left text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted"
                  >
                    Variable
                  </th>
                  {(["household", "aggregate", "equal"] as const).map((key) => (
                    <th
                      key={key}
                      scope="col"
                      className={`px-4 py-2 text-right text-[10px] font-medium uppercase tracking-[0.14em] ${
                        effectiveView === key
                          ? "text-primary-strong"
                          : "text-text-muted"
                      }`}
                    >
                      {key === "household"
                        ? "Household"
                        : key === "aggregate"
                          ? "Aggregate"
                          : "Equal"}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {weightedVariables.map((variable) => (
                  <tr
                    key={variable}
                    className="border-t border-border-subtle"
                  >
                    <td className="px-4 py-2 text-text-secondary">
                      {getVariableLabel(variable, weightsCountry)}
                    </td>
                    {(["household", "aggregate", "equal"] as const).map(
                      (key) => {
                        const w = weights[key]?.[variable] ?? 0;
                        return (
                          <td
                            key={key}
                            className={`px-4 py-2 text-right font-[family-name:var(--font-mono)] ${
                              effectiveView === key
                                ? "text-text"
                                : "text-text-secondary"
                            }`}
                          >
                            {(w * 100).toFixed(2)}%
                          </td>
                        );
                      },
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}
