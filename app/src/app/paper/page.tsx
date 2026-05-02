/* eslint-disable @next/next/no-img-element */
import Link from "next/link";

const manuscriptPaths = {
  pdf: "/paper/policybench.pdf",
  web: "/paper/web/index.html?v=20260501",
};
const ssrnUrl = process.env.NEXT_PUBLIC_POLICYBENCH_SSRN_URL;

export default function PaperPage() {
  return (
    <main className="min-h-screen bg-void">
      <nav className="sticky top-0 z-40 border-b border-border bg-bg/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 sm:px-6">
          <Link
            href="/"
            className="shrink-0 py-3 font-[family-name:var(--font-display)] text-lg tracking-tight text-text transition-colors hover:text-primary"
          >
            PolicyBench
          </Link>
          <div className="min-w-0 flex-1 overflow-x-auto">
            <div className="flex min-w-max gap-1">
              <a
                href="#paper-top"
                className="border-b-2 border-primary px-3 py-3 text-[11px] font-medium uppercase tracking-wider text-primary sm:px-4"
              >
                Paper
              </a>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Link
              href="/"
              className="rounded-full border border-border bg-card px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider text-text-secondary transition-colors hover:border-primary/40 hover:text-primary"
            >
              Benchmark
            </Link>
            <a
              href="https://policyengine.org"
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-wider text-text-secondary transition-colors hover:border-primary/40 hover:text-primary"
              aria-label="By PolicyEngine"
              title="By PolicyEngine"
            >
              <span>by</span>
              <img
                src="/assets/policyengine-logo.svg"
                alt="PolicyEngine"
                className="h-3 w-auto"
              />
            </a>
          </div>
        </div>
      </nav>

      <div id="paper-top" className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <div className="eyebrow mb-3">Manuscript</div>
        <h1 className="font-[family-name:var(--font-display)] text-4xl tracking-tight text-text sm:text-5xl">
          PolicyBench
        </h1>
        <p className="mt-4 max-w-2xl text-base leading-relaxed text-text-secondary sm:text-lg">
          Benchmarking no-tool tax-and-benefit estimation in frontier language
          models. This page embeds the frozen 2026-05-01 manuscript snapshot:
          a 100-household-per-country public preview scored against
          PolicyEngine reference outputs.
        </p>

        <div className="mt-5 inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-sm text-text-secondary">
          <img
            src="/assets/policyengine-logo.svg"
            alt="PolicyEngine"
            className="h-4 w-auto"
          />
          <span>Research paper by PolicyEngine</span>
        </div>

        <div className="mt-8 flex flex-wrap gap-3">
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

        <section className="mt-8 overflow-hidden rounded-3xl border border-border bg-card">
          <div className="border-b border-border px-5 py-3 text-sm text-text-secondary">
            Frozen manuscript snapshot
          </div>
          <iframe
            src={manuscriptPaths.web}
            title="PolicyBench paper"
            className="block h-[calc(100vh-16rem)] min-h-[720px] w-full border-0 bg-white"
          />
        </section>
      </div>
    </main>
  );
}
