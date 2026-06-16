import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import rawData from "../../../data-summary.json";
import SiteHeader from "../../../components/SiteHeader";
import ProviderMark from "../../../components/ProviderMark";
import { formatCurrency } from "../../../format";
import {
  coverageAccuracy,
  hardestCases,
  listModels,
  modelCountrySummaries,
  programRows,
} from "../../../lib/modelPage";
import { MODEL_LABELS, getProviderForModel, PROVIDER_LABELS } from "../../../modelMeta";
import {
  getVariableLabel,
  VIEW_LABELS,
  type DashboardBundle,
} from "../../../types";

const dashboard = rawData as DashboardBundle;

export const dynamicParams = false;

export function generateStaticParams() {
  return listModels(dashboard).map((id) => ({ id }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const label = MODEL_LABELS[id] ?? id;
  const summaries = modelCountrySummaries(dashboard, id);
  const scoreText = summaries
    .map(
      (summary) =>
        `${summary.country.toUpperCase()} ${(summary.stat.exact ?? summary.stat.score).toFixed(1)}%`,
    )
    .join(", ");
  const description =
    `How accurately ${label} estimates household tax and benefit amounts ` +
    `without tools, scored against PolicyEngine (exact-match rate: ` +
    `${scoreText}).`;
  return {
    title: label,
    description,
    alternates: { canonical: `/model/${id}` },
    openGraph: {
      title: `${label} on PolicyBench`,
      description,
      images: [{ url: "/og-image.png", width: 1200, height: 630 }],
    },
    twitter: {
      card: "summary_large_image",
      title: `${label} on PolicyBench`,
      description,
    },
  };
}

function formatPct(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value.toFixed(1)}%`;
}

function ScorePill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-card px-4 py-3">
      <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
        {label}
      </div>
      <div className="mt-1 font-[family-name:var(--font-mono)] text-xl text-text">
        {value}
      </div>
    </div>
  );
}

export default async function ModelPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const summaries = modelCountrySummaries(dashboard, id);
  if (summaries.length === 0) notFound();

  const label = MODEL_LABELS[id] ?? id;
  const provider = getProviderForModel(id);
  const providerLabel = provider ? PROVIDER_LABELS[provider] : null;

  const expanded = (
    <div>
      <div className="flex items-center gap-3">
        <ProviderMark provider={provider} size={28} />
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-3xl sm:text-4xl text-text tracking-tight">
            {label}
          </h1>
          {providerLabel && (
            <div className="mt-1 text-sm text-text-secondary">
              {providerLabel} · AI alone, no tools
            </div>
          )}
        </div>
      </div>
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4 max-w-3xl">
        {summaries.map((summary) => (
          <ScorePill
            key={`rank-${summary.country}`}
            label={`${VIEW_LABELS[summary.country]} rank`}
            value={`#${summary.rank} of ${summary.rankedModels}`}
          />
        ))}
        {summaries.map((summary) => (
          <ScorePill
            key={`score-${summary.country}`}
            label={`${summary.country.toUpperCase()} exact`}
            value={formatPct(summary.stat.exact ?? summary.stat.score)}
          />
        ))}
      </div>
    </div>
  );

  return (
    <main id="main" className="min-h-screen bg-void">
      <SiteHeader
        actionLink={{ label: "Leaderboard", href: "/", type: "internal" }}
        expandedContent={expanded}
        alwaysExpanded
      />

      <div className="mx-auto max-w-7xl px-4 sm:px-6 pb-20">
        {summaries.map((summary) => {
          const bench = dashboard.countries[summary.country];
          if (!bench) return null;
          const rows = programRows(bench, id);
          const cases = hardestCases(bench, id);
          const coverage = coverageAccuracy(bench, id);
          const currencySymbol = summary.country === "uk" ? "£" : "$";
          return (
            <section
              key={summary.country}
              aria-labelledby={`country-${summary.country}`}
              className="mt-12"
            >
              <div className="eyebrow mb-3">
                {VIEW_LABELS[summary.country]}
              </div>
              <h2
                id={`country-${summary.country}`}
                className="font-[family-name:var(--font-display)] text-2xl sm:text-3xl text-text tracking-tight"
              >
                {VIEW_LABELS[summary.country]} benchmark
              </h2>

              <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4 max-w-3xl">
                <ScorePill
                  label="Exact match"
                  value={formatPct(summary.stat.exact)}
                />
                <ScorePill
                  label="Bounded score"
                  value={formatPct(summary.stat.boundedScore ?? summary.stat.score)}
                />
                <ScorePill
                  label="Parse rate"
                  value={
                    summary.stat.n > 0
                      ? `${((summary.stat.nParsed / summary.stat.n) * 100).toFixed(1)}%`
                      : "—"
                  }
                />
                <ScorePill
                  label="Eligibility flags"
                  value={
                    coverage
                      ? `${coverage.correct}/${coverage.total}`
                      : "—"
                  }
                />
              </div>

              <div className="mt-8 grid gap-8 lg:grid-cols-2">
                <div>
                  <h3 className="text-sm font-medium text-text">
                    Score by program
                    <span className="ml-2 text-text-muted font-normal">
                      hardest first
                    </span>
                  </h3>
                  <div className="mt-3 overflow-x-auto rounded-2xl border border-border bg-card">
                    <table className="w-full border-collapse text-sm">
                      <thead>
                        <tr className="border-b border-border-subtle">
                          <th className="px-4 py-2.5 text-left text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
                            Program
                          </th>
                          <th className="px-4 py-2.5 text-right text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
                            Exact
                          </th>
                          <th className="px-4 py-2.5 text-right text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
                            Within 1%
                          </th>
                          <th className="px-4 py-2.5 text-right text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
                            n
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row) => (
                          <tr
                            key={row.variable}
                            className="border-t border-border-subtle first:border-t-0"
                          >
                            <td className="px-4 py-2 text-text-secondary">
                              {getVariableLabel(row.variable, summary.country)}
                            </td>
                            <td className="px-4 py-2 text-right font-[family-name:var(--font-mono)] text-text">
                              {formatPct(row.exact)}
                            </td>
                            <td className="px-4 py-2 text-right font-[family-name:var(--font-mono)] text-text-secondary">
                              {formatPct(row.within1pct)}
                            </td>
                            <td className="px-4 py-2 text-right font-[family-name:var(--font-mono)] text-text-muted">
                              {row.n}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-medium text-text">
                    Hardest cases
                    <span className="ml-2 text-text-muted font-normal">
                      worst misses on positive references
                    </span>
                  </h3>
                  <ul className="mt-3 space-y-3">
                    {cases.length === 0 && (
                      <li className="rounded-2xl border border-border bg-card px-4 py-3 text-sm text-text-muted">
                        No misses beyond 1% on positive references.
                      </li>
                    )}
                    {cases.map((entry) => (
                      <li
                        key={`${entry.scenarioId}-${entry.variable}`}
                        className="rounded-2xl border border-border bg-card px-4 py-3"
                      >
                        <div className="flex items-baseline justify-between gap-3">
                          <span className="text-sm text-text">
                            {getVariableLabel(entry.variable, summary.country)}
                          </span>
                          <span className="font-[family-name:var(--font-mono)] text-xs text-danger-text">
                            {entry.relativeError === null
                              ? "no parseable answer"
                              : `${Math.round(entry.relativeError * 100)}% off`}
                          </span>
                        </div>
                        <div className="mt-1 text-xs text-text-secondary">
                          Reference{" "}
                          <span className="font-[family-name:var(--font-mono)]">
                            {formatCurrency(entry.groundTruth, currencySymbol)}
                          </span>
                          {entry.prediction !== null && (
                            <>
                              {" "}
                              · predicted{" "}
                              <span className="font-[family-name:var(--font-mono)]">
                                {formatCurrency(entry.prediction, currencySymbol)}
                              </span>
                            </>
                          )}
                        </div>
                        <Link
                          href={`/?country=${summary.country}&scenario=${entry.scenarioId}&cell=${encodeURIComponent(`${entry.variable}~${id}`)}#scenarios`}
                          className="mt-2 inline-block text-xs text-primary-strong hover:text-primary underline underline-offset-2"
                        >
                          Inspect household{" "}
                          {entry.scenarioId.replace("scenario_", "#")}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </section>
          );
        })}

        <p className="mt-12 text-xs text-text-muted max-w-2xl leading-relaxed">
          Scores are from the frozen manuscript snapshot under the AI-alone
          condition: one structured response per household, no tools, graded
          against PolicyEngine reference outputs. See the{" "}
          <Link href="/" className="underline underline-offset-2 hover:text-text">
            leaderboard
          </Link>{" "}
          and{" "}
          <Link
            href="/paper"
            className="underline underline-offset-2 hover:text-text"
          >
            paper
          </Link>{" "}
          for methodology.
        </p>
      </div>
    </main>
  );
}
