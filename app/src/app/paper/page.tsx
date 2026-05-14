/* eslint-disable @next/next/no-img-element */
import type { Metadata } from "next";
import Link from "next/link";

import SiteHeader from "../../components/SiteHeader";

const SNAPSHOT_DATE_LABEL = "Snapshot 2026-05-14";

export const metadata: Metadata = {
  title: "Paper",
  description:
    "PolicyBench paper — 2026-05-14 household-equal scored manuscript snapshot with May 13 model responses and refreshed PolicyEngine reference outputs.",
};

const manuscriptPaths = {
  pdf: "/paper/policybench.pdf",
  web: "/paper/web/index.html?v=20260514-oracle",
};
const ssrnUrl = process.env.NEXT_PUBLIC_POLICYBENCH_SSRN_URL;

export default function PaperPage() {
  const expanded = (
    <>
      <p className="max-w-2xl text-sm leading-relaxed text-text-secondary sm:text-base">
        Benchmarking no-tool tax-and-benefit estimation in frontier language
        models. This page embeds the 2026-05-14 scored manuscript snapshot:
        a 100-household-per-country public preview using household-equal impact
        scores against PolicyEngine reference outputs.
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.12em] text-text-secondary">
          <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-primary/70" />
          {SNAPSHOT_DATE_LABEL}
        </span>
      </div>
    </>
  );

  return (
    <main id="main" className="min-h-screen bg-void">
      <h1 className="sr-only">PolicyBench paper</h1>
      <SiteHeader
        actionLink={{
          label: "Benchmark",
          href: "/",
          type: "internal",
        }}
        expandedContent={expanded}
        alwaysExpanded
      />

      <div id="paper-top" className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <div className="eyebrow mb-3">Manuscript</div>

        <div className="mt-2 inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-sm text-text-secondary">
          <img
            src="/assets/policyengine-logo.svg"
            alt="PolicyEngine"
            className="h-4 w-auto"
          />
          <span>Research paper by PolicyEngine</span>
        </div>

        <div className="mt-6 flex flex-wrap gap-3">
          {ssrnUrl && (
            <a
              href={ssrnUrl}
              className="rounded-full border border-border bg-card px-4 py-2 text-sm text-text transition-colors hover:border-primary hover:text-primary"
            >
              SSRN copy
            </a>
          )}
          <a
            href={manuscriptPaths.web}
            className="rounded-full border border-border bg-card px-4 py-2 text-sm text-text transition-colors hover:border-primary hover:text-primary"
          >
            Open standalone HTML
          </a>
          <a
            href={manuscriptPaths.pdf}
            download="policybench.pdf"
            className="rounded-full border border-border bg-card px-4 py-2 text-sm text-text transition-colors hover:border-primary hover:text-primary"
          >
            Download PDF
          </a>
          <Link
            href="/"
            className="rounded-full border border-border bg-card px-4 py-2 text-sm text-text transition-colors hover:border-primary hover:text-primary"
          >
            Live benchmark
          </Link>
        </div>

        <section
          aria-labelledby="manuscript-section-heading"
          className="mt-8 overflow-hidden rounded-3xl border border-border bg-card"
        >
          <div
            id="manuscript-section-heading"
            className="border-b border-border px-5 py-3 text-sm text-text-secondary"
          >
            Frozen manuscript snapshot
          </div>
          <iframe
            src={manuscriptPaths.web}
            title="PolicyBench manuscript (embedded)"
            loading="lazy"
            sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
            referrerPolicy="same-origin"
            className="block h-[calc(100vh-16rem)] min-h-[720px] w-full border-0 bg-white"
          />
          <div className="border-t border-border px-5 py-3 text-sm">
            <a
              href="#paper-top"
              className="text-text-secondary hover:text-primary-strong"
            >
              ↑ Back to top
            </a>
            <span className="mx-2 text-text-muted" aria-hidden>
              ·
            </span>
            <a
              href={manuscriptPaths.web}
              className="text-text-secondary hover:text-primary-strong"
            >
              Open manuscript in a new page
            </a>
          </div>
        </section>
      </div>
    </main>
  );
}
