import { useMemo } from "react";
import type {
  BenchData,
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

function Badge({
  children,
  variant,
}: {
  children: React.ReactNode;
  variant: "primary" | "warning" | "danger" | "success";
}) {
  const styles = {
    primary: "text-primary bg-primary-soft border-primary/15",
    warning: "text-warning bg-warning-soft border-warning/15",
    danger: "text-danger bg-danger-soft border-danger/15",
    success: "text-success bg-success-soft border-success/15",
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
    { model: "deepseek-v4-pro", note: "US and UK runs pending" },
    { model: "deepseek-v4-flash", note: "US and UK runs pending" },
  ],
  us: [
    { model: "grok-4.20", note: "US full run pending" },
    { model: "deepseek-v4-pro", note: "Run pending" },
    { model: "deepseek-v4-flash", note: "Run pending" },
  ],
  uk: [
    { model: "deepseek-v4-pro", note: "Run pending" },
    { model: "deepseek-v4-flash", note: "Run pending" },
  ],
};

export default function ModelLeaderboard({
  data,
  selectedView,
}: {
  data: BenchData | GlobalBenchData;
  selectedView: ViewKey;
}) {
  const isGlobal = selectedView === "global";
  const noTools = useMemo<ModelStat[]>(
    () =>
      data.modelStats
        .filter((m) => m.condition === "no_tools")
        .sort((a, b) => b.score - a.score),
    [data]
  );
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

  return (
    <div>
      <div className="eyebrow mb-3 animate-fade-up">Leaderboard</div>
      <h2
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
          ? "Global scores are equal-weight averages of each model’s US and UK benchmark scores. Only models with both country runs are included."
          : "The headline score averages exact, within-1%, within-5%, and within-10% hits for dollar outputs, plus exact accuracy on binary coverage flags."}
        {pendingModels.length > 0 && (
          <>
            {" "}
            Pending rows below mark models that are actively being added.
          </>
        )}
      </p>

      <div className="mt-8 space-y-3">
        <div
          className={`hidden gap-3 px-4 text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium md:grid ${
            isGlobal ? "md:grid-cols-12" : "md:grid-cols-12"
          }`}
        >
          <div className="col-span-1">#</div>
          <div className={isGlobal ? "col-span-5" : "col-span-5"}>Model</div>
          <div className="col-span-3 text-right">
            {isGlobal ? "Global score" : "Score"}
          </div>
          <div className="col-span-3 text-right">
            {isGlobal ? "Country scores" : "MAE"}
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
    </div>
  );
}
