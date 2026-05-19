import { useCallback, useMemo, useState } from "react";
import type {
  BenchData,
  DashboardBundle,
  ModelStat,
  CountryCode,
} from "../types";
import { getVariableLabel } from "../types";
import { MODEL_LABELS, MODEL_ORDER, getProviderForModel } from "../modelMeta";
import ProviderMark from "./ProviderMark";
import { ProgramFilterPanel } from "./ProgramFilterDropdown";
import {
  programIsActive,
  type ProgramOption,
} from "../lib/programFilters";
import { metricTypeForVariable, outputGroupForVariable } from "../lib/scoring";
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

type PendingModel = {
  model: string;
  note: string;
};

const PENDING_MODELS: Record<CountryCode, PendingModel[]> = {
  us: [
    { model: "grok-4.20", note: "US full run pending" },
  ],
  uk: [],
};

export default function ModelLeaderboard({
  data,
  selectedView,
  dashboard,
  programOptions,
  activeProgramIds,
  activeProgramSummary,
  onResetPrograms,
  onToggleProgram,
  onSelectOnlyProgram,
}: {
  data: BenchData;
  selectedView: CountryCode;
  dashboard: DashboardBundle;
  programOptions: ProgramOption[];
  activeProgramIds: Set<string>;
  activeProgramSummary: string;
  onResetPrograms: () => void;
  onToggleProgram: (variable: string) => void;
  onSelectOnlyProgram: (variable: string) => void;
}) {
  const [sensitivityView, setSensitivityView] =
    useState<SensitivityViewId>("household");
  // Headline scoring: defaults to "within1pct". On UK, ~71% of references
  // are £0 and Exact mode mostly measures "did you say £0?" — the
  // within-1% bar restores meaningful separation. Exact remains a click
  // away as the production-deployability bar; Continuous tracks
  // conceptual progress year over year.
  const [scoringMode, setScoringMode] = useState<
    "exact" | "within1pct" | "continuous"
  >("within1pct");
  // Reference cases: All by default, but Positives is the right view when
  // (e.g.) UK references are 71% £0 and Exact mode mostly measures
  // "did you say £0?". Zeros surfaces the inverse — eligibility hedging.
  const [referenceFilter, setReferenceFilter] = useState<
    "all" | "positives" | "zeros"
  >("all");
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

  const isProgramActive = useCallback(
    (variable: string) => programIsActive(activeProgramIds, variable),
    [activeProgramIds],
  );

  function metricValue(
    variable: string,
    truth: number,
    prediction: number | null | undefined,
    field: "exact" | "within1pct" | "continuous",
  ): number {
    if (prediction === null || prediction === undefined || Number.isNaN(prediction)) {
      return 0;
    }
    const isBinary = metricTypeForVariable(variable, data.country) === "binary";
    if (isBinary) {
      return Math.round(prediction) === Math.round(truth) ? 1 : 0;
    }
    const absErr = Math.abs(prediction - truth);
    const exact = absErr <= 1 ? 1 : 0;
    if (field === "exact") return exact;
    if (field === "within1pct") {
      return truth === 0 ? exact : absErr / Math.abs(truth) <= 0.01 ? 1 : 0;
    }
    return truth === 0
      ? prediction === 0
        ? 1
        : 0
      : Math.max(0, 1 - absErr / Math.abs(truth));
  }

  // Compute the selected metric from scenario rows, not heatmap averages. This
  // mirrors Python's canonical scorer: split output-group weights across
  // concrete rows in each household, renormalize within the household, then
  // average households equally.
  const hitRateByModel = (field: "exact" | "within1pct" | "continuous") => {
    const out = new Map<string, number>();
    const weights = data.globalWeights?.[effectiveView];
    if (!weights) return out;

    const groupedWeights = new Map<string, number>();
    for (const [variable, weight] of Object.entries(weights)) {
      const group = outputGroupForVariable(variable);
      groupedWeights.set(group, (groupedWeights.get(group) ?? 0) + weight);
    }

    const sums = new Map<string, { score: number; households: number }>();
    for (const variableMap of Object.values(data.scenarioPredictions ?? {})) {
      const variables = Object.entries(variableMap).filter(([variable, modelMap]) => {
        if (!isProgramActive(variable)) return false;
        const first = Object.values(modelMap)[0];
        if (!first) return false;
        if (referenceFilter === "positives" && first.groundTruth === 0) return false;
        if (referenceFilter === "zeros" && first.groundTruth !== 0) return false;
        return groupedWeights.has(outputGroupForVariable(variable));
      });
      if (variables.length === 0) continue;

      const groupCounts = new Map<string, number>();
      for (const [variable] of variables) {
        const group = outputGroupForVariable(variable);
        groupCounts.set(group, (groupCounts.get(group) ?? 0) + 1);
      }
      const rawRowWeights = new Map<string, number>();
      let denominator = 0;
      for (const [variable] of variables) {
        const group = outputGroupForVariable(variable);
        const rawWeight =
          (groupedWeights.get(group) ?? 0) / (groupCounts.get(group) ?? 1);
        rawRowWeights.set(variable, rawWeight);
        denominator += rawWeight;
      }
      if (denominator <= 0) continue;

      const models = new Set<string>();
      for (const [, modelMap] of variables) {
        for (const model of Object.keys(modelMap)) models.add(model);
      }
      for (const model of models) {
        let householdScore = 0;
        for (const [variable, modelMap] of variables) {
          const record = modelMap[model];
          const rowWeight = (rawRowWeights.get(variable) ?? 0) / denominator;
          householdScore +=
            rowWeight *
            metricValue(
              variable,
              record?.groundTruth ?? 0,
              record?.prediction,
              field,
            );
        }
        const acc = sums.get(model) ?? { score: 0, households: 0 };
        acc.score += householdScore;
        acc.households += 1;
        sums.set(model, acc);
      }
    }

    for (const [model, acc] of sums) {
      if (acc.households > 0) out.set(model, (acc.score / acc.households) * 100);
    }
    return out;
  };

  const exactScoreByModel = useMemo(
    () => hitRateByModel("exact"),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      data,
      effectiveView,
      referenceFilter,
      activeProgramIds,
    ],
  );
  const within1pctScoreByModel = useMemo(
    () => hitRateByModel("within1pct"),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      data,
      effectiveView,
      referenceFilter,
      activeProgramIds,
    ],
  );
  const filteredContinuousByModel = useMemo(
    () => hitRateByModel("continuous"),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      data,
      effectiveView,
      referenceFilter,
      activeProgramIds,
    ],
  );

  const noTools = useMemo<ModelStat[]>(() => {
    const base = data.modelStats.filter((m) => m.condition === "no_tools");

    if (scoringMode === "exact" || scoringMode === "within1pct") {
      // Exact: percent of predictions that match the reference to the dollar
      // (or to the boolean for eligibility flags). Within-1%: the analyst
      // bar — rounding and tiny rate drift are OK, but not material misses.
      // Weighted by the active variable weighting and recomputed from
      // scenario rows so program filters renormalize the active set.
      const weighted =
        scoringMode === "exact" ? exactScoreByModel : within1pctScoreByModel;
      return [...base]
        .map((m) => {
          const w = weighted.get(m.model);
          const fallback =
            scoringMode === "exact" ? (m.exact ?? 0) : (m.within1pct ?? 0);
          return {
            ...m,
            score: w !== undefined ? w : fallback,
          };
        })
        .sort((a, b) => b.score - a.score);
    }

    // Continuous mode. Use the recomputed weighted score for country views so
    // program filters renormalize the active program weights.
    if (filteredContinuousByModel.size > 0) {
      return [...base]
        .map((m) => ({
          ...m,
          score: filteredContinuousByModel.get(m.model) ?? 0,
        }))
        .sort((a, b) => b.score - a.score);
    }
    if (effectiveView === "household") {
      return [...base].sort((a, b) => b.score - a.score);
    }
    // Replace the score with the selected view's precomputed value, drop
    // models without one.
    return base
      .filter((m) => sensitivityScoreByModel.has(m.model))
      .map((m) => ({ ...m, score: sensitivityScoreByModel.get(m.model)! }))
      .sort((a, b) => b.score - a.score);
  }, [
    data,
    effectiveView,
    sensitivityScoreByModel,
    filteredContinuousByModel,
    exactScoreByModel,
    within1pctScoreByModel,
    scoringMode,
  ]);

  const pendingModels = useMemo<PendingModel[]>(() => {
    const present = new Set(noTools.map((model) => model.model));
    const configured = PENDING_MODELS[selectedView].filter(
      (model) => !present.has(model.model),
    );
    return [...configured].sort((a, b) => {
      const aIndex = MODEL_ORDER.indexOf(a.model as (typeof MODEL_ORDER)[number]);
      const bIndex = MODEL_ORDER.indexOf(b.model as (typeof MODEL_ORDER)[number]);
      return aIndex - bIndex;
    });
  }, [noTools, selectedView]);

  const activeView = SENSITIVITY_VIEWS.find((v) => v.id === sensitivityView)!;

  // "Exact" means "within one currency unit," and that unit is country-
  // specific. Surface the right word in tooltips, captions, and the Options
  // summary so the UK leaderboard doesn't read "to the dollar".
  const isUK = selectedView === "uk";
  const currencyUnit = isUK ? "pound" : "dollar";
  const currencySymbol = isUK ? "£" : "$";
  const scoringLabel =
    scoringMode === "exact"
      ? "exact"
      : scoringMode === "within1pct"
        ? "within 1%"
        : "continuous";
  const referenceLabel =
    referenceFilter === "all"
      ? "all cases"
      : referenceFilter === "positives"
        ? "positives only"
        : "zeros only";
  const optionsSummary = `scoring: ${scoringLabel} · cases: ${referenceLabel} · weighting: ${activeView.label.toLowerCase()} · ${activeProgramSummary.toLowerCase()}`;

  const weights = data.globalWeights;
  const weightsCountry = data.country;

  const weightedVariables = useMemo(() => {
    if (!weights) return [] as string[];
    const all = new Set<string>();
    for (const view of ["household", "aggregate", "equal"] as const) {
      const map = weights[view];
      if (map) {
        Object.keys(map)
          .filter(isProgramActive)
          .forEach((v) => all.add(v));
      }
    }
    const ranked = Array.from(all).map((v) => ({
      v,
      key: weights[effectiveView]?.[v] ?? 0,
    }));
    ranked.sort((a, b) => b.key - a.key);
    return ranked.map((r) => r.v);
  }, [weights, effectiveView, isProgramActive]);

  return (
    <div>
      <div className="eyebrow mb-3 animate-fade-up">Leaderboard</div>
      <h2
        id="leaderboard-heading"
        className="font-[family-name:var(--font-display)] text-4xl md:text-5xl text-text tracking-tight animate-fade-up"
        style={{ animationDelay: "80ms" }}
      >
        Model rankings
      </h2>
      {pendingModels.length > 0 && (
        <p
          className="text-text-secondary mt-3 max-w-xl leading-relaxed animate-fade-up"
          style={{ animationDelay: "160ms" }}
        >
          Pending rows below mark models that are actively being added.
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
          {`${noTools.length} models, ranked by ${
            scoringMode === "exact"
              ? "exact-match"
              : scoringMode === "within1pct"
                ? "within-1% hit rate"
                : `${activeView.label.toLowerCase()}-weighted bounded`
          } score (${
            selectedView === "us" ? "United States" : "United Kingdom"
          })`}
        </p>
        <div
          role="row"
          className="hidden gap-3 px-4 text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium md:grid md:grid-cols-12"
        >
          <div role="columnheader" className="col-span-1">#</div>
          <div role="columnheader" className="col-span-8">
            Model
          </div>
          <div role="columnheader" className="col-span-3 text-right">
            {scoringMode === "exact"
              ? "Exact match %"
              : scoringMode === "within1pct"
                ? "Within 1%"
                : "Score"}
          </div>
        </div>

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
                    {stabilityLabel && (
                      <div className="mt-1 pl-6 text-[10px] font-[family-name:var(--font-mono)] text-text-muted">
                        {stabilityLabel}
                      </div>
                    )}
                  </div>

                  <Badge variant={accColor(m.score)}>{m.score.toFixed(1)}%</Badge>
                </div>

              </div>

              <div className="hidden items-center gap-3 md:grid md:grid-cols-12">
                <div className="col-span-1">
                  <span className="text-text-muted font-[family-name:var(--font-mono)] text-sm">
                    {i + 1}
                  </span>
                </div>

                <div className="col-span-8 flex items-center gap-2.5">
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
                  {stabilityLabel && (
                    <div className="text-[10px] text-text-muted font-[family-name:var(--font-mono)] mt-1">
                      {stabilityLabel}
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

              <div className="col-span-8 flex flex-col gap-0.5">
                <div className="flex items-center gap-2.5">
                  <ProviderMark
                    provider={getProviderForModel(m.model)}
                    size={14}
                    className="flex-shrink-0"
                  />
                  <span className="text-text font-medium text-sm">
                    {MODEL_LABELS[m.model] || m.model}
                  </span>
                </div>
                {m.note && (
                  <div className="pl-6 text-[10px] uppercase tracking-[0.14em] text-text-muted">
                    {m.note}
                  </div>
                )}
              </div>

              <div className="col-span-3 text-right">
                <Badge variant="warning">Pending</Badge>
              </div>

            </div>
          </div>
        ))}
      </div>

      <details
        className="mt-8 group rounded-2xl border border-border bg-card/40 animate-fade-up"
        style={{ animationDelay: "320ms" }}
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
              Options
            </span>
            <span className="truncate text-text-muted">
              {optionsSummary}
            </span>
          </span>
        </summary>

        <div className="space-y-4 border-t border-border-subtle px-4 py-4">
          {programOptions.length > 0 && (
            <div>
              <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
                Programs
              </div>
              <div className="mt-2">
                <ProgramFilterPanel
                  options={programOptions}
                  activeProgramIds={activeProgramIds}
                  description="Filter restricts model scoring, the program breakdown table, and the scenario explorer to the selected outputs. Weights rescale to 100% over the active set."
                  onReset={onResetPrograms}
                  onToggle={onToggleProgram}
                  onSelectOnly={onSelectOnlyProgram}
                />
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <span
              id="leaderboard-scoring-label"
              className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted"
            >
              Scoring
            </span>
            <div
              role="group"
              aria-labelledby="leaderboard-scoring-label"
              className="inline-flex flex-wrap items-center gap-1 rounded-full border border-border bg-card p-1"
            >
              {(
                [
                  [
                    "exact",
                    "Exact",
                    `Percent of predictions that match the PolicyEngine reference within one ${currencyUnit} (eligibility flags match the boolean). Real-world policy decisions need this — close-but-not-right isn't deployable.`,
                  ],
                  [
                    "within1pct",
                    "Within 1%",
                    "Percent of predictions within 1% of the reference. The analyst bar — rounding and small rate/parameter drift are tolerated, but material misses are not.",
                  ],
                  [
                    "continuous",
                    "Continuous",
                    "Bounded continuous score: max(0, 1 - |prediction - reference| / |reference|), clipped to [0, 1], reducing to exact-match accuracy for boolean variables. Awards partial credit for close answers; useful for tracking conceptual progress while exact rates remain low.",
                  ],
                ] as const
              ).map(([id, label, description]) => {
                const isActive = scoringMode === id;
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setScoringMode(id)}
                    aria-pressed={isActive}
                    title={description}
                    className={`rounded-full px-3 py-1.5 text-[11px] font-medium transition-colors ${
                      isActive
                        ? "bg-primary-strong text-white"
                        : "text-text-secondary hover:text-text"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
            <span className="text-[11px] text-text-muted">
              {scoringMode === "exact"
                ? `Percent matching within ${currencySymbol}1.`
                : scoringMode === "within1pct"
                  ? "Percent within 1% of reference."
                  : "Bounded score: 1 - |err| / |ref|, clipped to [0, 1]."}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-3">
              <span
                id="leaderboard-refcases-label"
                className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted"
              >
                Reference cases
              </span>
              <div
                role="group"
                aria-labelledby="leaderboard-refcases-label"
                className="inline-flex flex-wrap items-center gap-1 rounded-full border border-border bg-card p-1"
              >
                {(
                  [
                    [
                      "all",
                      "All",
                      "Every (model, scenario, variable) cell in the benchmark slice.",
                    ],
                    [
                      "positives",
                      "Positives only",
                      "Restrict to cases where the PolicyEngine reference is non-zero (e.g., the household actually receives the benefit or owes the tax). Reveals competence on cases that matter, especially on zero-heavy slices like UK.",
                    ],
                    [
                      "zeros",
                      "Zeros only",
                      "Restrict to cases where the PolicyEngine reference is zero (no benefit, no tax). Measures eligibility hedging — does the model correctly say zero when it should?",
                    ],
                  ] as const
                ).map(([id, label, description]) => {
                  const isActive = referenceFilter === id;
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() => setReferenceFilter(id)}
                      aria-pressed={isActive}
                      title={description}
                      className={`rounded-full px-3 py-1.5 text-[11px] font-medium transition-colors ${
                        isActive
                          ? "bg-primary-strong text-white"
                          : "text-text-secondary hover:text-text"
                      }`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
              <span className="text-[11px] text-text-muted">
                {referenceFilter === "all"
                  ? "All reference cells."
                  : referenceFilter === "positives"
                    ? "Only cases where the reference is nonzero."
                    : "Only cases where the reference is zero."}
              </span>
          </div>

          <div className="flex flex-wrap items-center gap-3">
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
            <p className="text-[11px] text-text-muted">
              The &ldquo;{
                SENSITIVITY_VIEWS.find((v) => v.id === sensitivityView)?.label ??
                  sensitivityView
              }&rdquo; view is not available on this slice; the leaderboard
              falls back to the Household view.
            </p>
          )}
        </div>
      </details>

      {weights && weightedVariables.length > 0 && weightsCountry && (
        <details
          className="mt-4 group rounded-2xl border border-border bg-card/40 animate-fade-up"
          style={{ animationDelay: "340ms" }}
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
