import { notFound } from "next/navigation";
import type { Metadata } from "next";
import Link from "next/link";

import SiteHeader from "../../../components/SiteHeader";
import ProviderMark from "../../../components/ProviderMark";
import {
  MODEL_LABELS,
  PROVIDER_LABELS,
  getProviderForModel,
} from "../../../modelMeta";
import { buildAllRows } from "../../../lib/sensitivity";
import { metricTypeForVariable } from "../../../lib/scoring";
import {
  getVariableLabel,
  VIEW_SHORT_LABELS,
  type CountryCode,
  type DashboardBundle,
} from "../../../types";

import rawDashboard from "../../../data.json";

const dashboard = rawDashboard as unknown as DashboardBundle;

function getAllModelIds(): string[] {
  const models = new Set<string>();
  if (dashboard.global) {
    for (const s of dashboard.global.modelStats) models.add(s.model);
  }
  for (const c of ["us", "uk"] as CountryCode[]) {
    const d = dashboard.countries[c];
    if (d) for (const s of d.modelStats) models.add(s.model);
  }
  return [...models];
}

export function generateStaticParams() {
  return getAllModelIds().map((id) => ({ id }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const label = MODEL_LABELS[id] ?? id;
  return {
    title: label,
    description: `PolicyBench per-model analysis for ${label}: variable scores, hardest outputs, and sample wrong predictions.`,
  };
}

function Badge({ score }: { score: number }) {
  let cls = "";
  if (score >= 80) cls = "text-success-text bg-success-soft border-success/30";
  else if (score >= 65)
    cls = "text-primary-strong bg-primary-soft border-primary/30";
  else if (score >= 50)
    cls = "text-warning-text bg-warning-soft border-warning/40";
  else cls = "text-danger-text bg-danger-soft border-danger/40";
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-[10px] font-medium tracking-wide uppercase border ${cls}`}
    >
      {score.toFixed(1)}%
    </span>
  );
}

export default async function ModelPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: modelId } = await params;

  if (!getAllModelIds().includes(modelId)) notFound();

  const modelLabel = MODEL_LABELS[modelId] ?? modelId;
  const provider = getProviderForModel(modelId);

  // Global and country-level stats (no_tools condition)
  const globalStat = dashboard.global?.modelStats.find(
    (s) => s.model === modelId && s.condition === "no_tools",
  );
  const usStat = dashboard.countries.us?.modelStats.find(
    (s) => s.model === modelId && s.condition === "no_tools",
  );
  const ukStat = dashboard.countries.uk?.modelStats.find(
    (s) => s.model === modelId && s.condition === "no_tools",
  );

  // Global score and country scores — prefer countryScores on globalStat,
  // fall back to per-country modelStat.
  const globalScore = globalStat?.score;
  const usScore =
    (globalStat?.countryScores?.us ?? usStat?.score);
  const ukScore =
    (globalStat?.countryScores?.uk ?? ukStat?.score);

  // Parse coverage from global stat (nParsed / n), fall back to sum of countries.
  let parseCov: number | null = null;
  if (globalStat && globalStat.n > 0) {
    parseCov = (globalStat.nParsed / globalStat.n) * 100;
  } else {
    const totalN = (usStat?.n ?? 0) + (ukStat?.n ?? 0);
    const totalParsed = (usStat?.nParsed ?? 0) + (ukStat?.nParsed ?? 0);
    if (totalN > 0) parseCov = (totalParsed / totalN) * 100;
  }

  // --- Hardest output groups: (country, outputGroup) → mean score (0–100) ---
  const allRows = buildAllRows(dashboard).filter((r) => r.model === modelId);

  const ogMap = new Map<string, { sum: number; count: number }>();
  for (const row of allRows) {
    const key = `${row.country}|${row.outputGroup}`;
    const c = ogMap.get(key) ?? { sum: 0, count: 0 };
    c.sum += row.score * 100;
    c.count += 1;
    ogMap.set(key, c);
  }
  const hardestVars = [...ogMap.entries()]
    .map(([key, { sum, count }]) => {
      const [country, outputGroup] = key.split("|") as [CountryCode, string];
      return { country, outputGroup, score: count > 0 ? sum / count : 0 };
    })
    .sort((a, b) => a.score - b.score)
    .slice(0, 5);

  // --- Sample wrong predictions: relErr > 10%, score < 0.75 ---
  type WrongPred = {
    country: CountryCode;
    scenarioId: string;
    variable: string;
    truth: number;
    prediction: number;
    score: number;
    explanation?: string;
  };
  const wrong: WrongPred[] = [];
  const seen = new Set<string>();

  for (const country of ["us", "uk"] as CountryCode[]) {
    const payload = dashboard.countries[country];
    if (!payload) continue;
    for (const [scenarioId, varMap] of Object.entries(
      payload.scenarioPredictions,
    )) {
      for (const [variable, modelMap] of Object.entries(varMap)) {
        const rec = (modelMap as Record<string, typeof modelMap[string]>)[modelId];
        if (!rec || rec.prediction == null) continue;
        const truth = rec.groundTruth;
        const pred = rec.prediction as number;
        const relErr =
          truth !== 0
            ? Math.abs((pred - truth) / truth)
            : Math.abs(pred) > 1
              ? 1
              : 0;
        if (relErr <= 0.1) continue;
        const rowScore = (rec.score ?? 0) as number;
        if (rowScore >= 0.75) continue;
        const key = `${country}|${scenarioId}|${variable}`;
        if (seen.has(key)) continue;
        seen.add(key);
        wrong.push({
          country,
          scenarioId,
          variable,
          truth,
          prediction: pred,
          score: rowScore,
          explanation: rec.explanation as string | undefined,
        });
      }
    }
  }
  wrong.sort((a, b) => {
    const ea =
      a.truth !== 0 ? Math.abs((a.prediction - a.truth) / a.truth) : 1;
    const eb =
      b.truth !== 0 ? Math.abs((b.prediction - b.truth) / b.truth) : 1;
    return eb - ea;
  });
  const samples = wrong.slice(0, 10);

  // ---- Header expanded content ----
  const expanded = (
    <div className="mt-2">
      <div className="flex flex-wrap items-center gap-3">
        <ProviderMark provider={provider} size={28} />
        <span className="font-[family-name:var(--font-display)] text-3xl text-text tracking-tight">
          {modelLabel}
        </span>
        {provider && (
          <span className="text-text-secondary text-sm">
            {PROVIDER_LABELS[provider]}
          </span>
        )}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        {globalScore !== undefined && (
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-sm">
            <span className="text-text-secondary text-[10px] uppercase tracking-wider">
              Global
            </span>
            <span className="font-[family-name:var(--font-mono)] text-text font-medium">
              {globalScore.toFixed(1)}%
            </span>
          </div>
        )}
        {usScore !== undefined && (
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-sm">
            <span className="text-text-secondary text-[10px] uppercase tracking-wider">
              US
            </span>
            <span className="font-[family-name:var(--font-mono)] text-text font-medium">
              {usScore.toFixed(1)}%
            </span>
          </div>
        )}
        {ukScore !== undefined && (
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-sm">
            <span className="text-text-secondary text-[10px] uppercase tracking-wider">
              UK
            </span>
            <span className="font-[family-name:var(--font-mono)] text-text font-medium">
              {ukScore.toFixed(1)}%
            </span>
          </div>
        )}
        {parseCov !== null && (
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-sm">
            <span className="text-text-secondary text-[10px] uppercase tracking-wider">
              Parse rate
            </span>
            <span className="font-[family-name:var(--font-mono)] text-text font-medium">
              {parseCov.toFixed(1)}%
            </span>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <main id="main" className="min-h-screen bg-void">
      <h1 className="sr-only">{modelLabel} — PolicyBench model deep-dive</h1>
      <SiteHeader
        actionLink={{ label: "Leaderboard", href: "/", type: "internal" }}
        expandedContent={expanded}
        alwaysExpanded
      />

      <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 space-y-12">
        {/* Hardest output groups */}
        <section aria-labelledby="hardest-heading">
          <div className="eyebrow mb-3">Hardest outputs</div>
          <h2
            id="hardest-heading"
            className="font-[family-name:var(--font-display)] text-3xl text-text tracking-tight mb-6"
          >
            Top 5 lowest-scoring outputs
          </h2>
          {hardestVars.length === 0 ? (
            <p className="text-text-secondary text-sm">
              No scored rows found for this model.
            </p>
          ) : (
            <div className="space-y-3">
              {hardestVars.map(({ country, outputGroup, score }, i) => (
                <div
                  key={`${country}-${outputGroup}`}
                  className="card px-4 py-4"
                >
                  <div className="flex items-center justify-between gap-4">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="font-[family-name:var(--font-mono)] text-sm text-text-muted shrink-0">
                        {i + 1}
                      </span>
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-text">
                          {getVariableLabel(outputGroup, country)}
                        </div>
                        <div className="text-[10px] uppercase tracking-wider text-text-muted mt-0.5">
                          {VIEW_SHORT_LABELS[country]}
                        </div>
                      </div>
                    </div>
                    <Badge score={score} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Sample wrong predictions */}
        {samples.length > 0 && (
          <section aria-labelledby="samples-heading">
            <div className="eyebrow mb-3">Wrong predictions</div>
            <h2
              id="samples-heading"
              className="font-[family-name:var(--font-display)] text-3xl text-text tracking-tight mb-2"
            >
              Sample errors (&gt;10% off)
            </h2>
            <p className="text-text-secondary text-sm mb-6 max-w-xl leading-relaxed">
              Cases where this model&apos;s prediction differed from the
              PolicyEngine reference by more than 10%, sorted by largest
              relative error.
            </p>
            <div className="space-y-4">
              {samples.map(
                ({
                  country,
                  scenarioId,
                  variable,
                  truth,
                  prediction,
                  score,
                  explanation,
                }) => {
                  const relErrPct =
                    truth !== 0
                      ? Math.abs((prediction - truth) / truth) * 100
                      : null;
                  const metricType = metricTypeForVariable(variable, country);
                  const fmt = (v: number) =>
                    metricType === "amount"
                      ? `$${Math.round(v).toLocaleString()}`
                      : String(Math.round(v));
                  return (
                    <div
                      key={`${country}-${scenarioId}-${variable}`}
                      className="card px-5 py-5"
                    >
                      <div className="flex flex-wrap items-start gap-3 mb-3">
                        <span className="inline-block rounded-full border border-border bg-surface px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-text-secondary">
                          {VIEW_SHORT_LABELS[country]}
                        </span>
                        <span className="text-sm font-medium text-text">
                          {getVariableLabel(variable, country)}
                        </span>
                        <span className="ml-auto">
                          <Badge score={score * 100} />
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 text-sm mb-4">
                        <div>
                          <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1">
                            Prediction
                          </div>
                          <div className="font-[family-name:var(--font-mono)] text-danger-text">
                            {fmt(prediction)}
                          </div>
                        </div>
                        <div>
                          <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1">
                            Ground truth
                          </div>
                          <div className="font-[family-name:var(--font-mono)] text-success-text">
                            {fmt(truth)}
                          </div>
                        </div>
                        {relErrPct !== null && (
                          <div>
                            <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1">
                              Error
                            </div>
                            <div className="font-[family-name:var(--font-mono)] text-text">
                              {relErrPct.toFixed(1)}%
                            </div>
                          </div>
                        )}
                      </div>
                      {explanation && (
                        <details className="text-xs">
                          <summary className="cursor-pointer select-none text-[10px] uppercase tracking-wider text-text-muted hover:text-text">
                            Model explanation
                          </summary>
                          <p className="mt-2 leading-relaxed text-text-secondary line-clamp-6">
                            {explanation}
                          </p>
                        </details>
                      )}
                      <div className="mt-3 pt-3 border-t border-border text-[10px] text-text-muted flex items-center gap-3">
                        <Link
                          href="/#scenarios"
                          className="hover:text-primary transition-colors"
                        >
                          View in scenario explorer →
                        </Link>
                        <span aria-hidden>·</span>
                        <span className="font-[family-name:var(--font-mono)]">
                          {scenarioId}
                        </span>
                      </div>
                    </div>
                  );
                },
              )}
            </div>
          </section>
        )}

        <div className="border-t border-border pt-8">
          <Link
            href="/"
            className="text-sm text-text-secondary hover:text-primary transition-colors"
          >
            ← Back to leaderboard
          </Link>
        </div>
      </div>
    </main>
  );
}
