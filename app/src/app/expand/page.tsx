import type { Metadata } from "next";
import Link from "next/link";

import rawData from "../../data-summary.json";
import ExpandModelCount from "../../components/ExpandModelCount";
import SiteHeader from "../../components/SiteHeader";
import { listModels } from "../../lib/modelPage";
import type { DashboardBundle } from "../../types";

const dashboard = rawData as DashboardBundle;
const modelCount = listModels(dashboard).length;

const DESCRIPTION =
  "Expand PolicyBench to your region, population, or program: households drawn to your area, references computed from the law, every miss diagnosed, results public.";

export const metadata: Metadata = {
  title: "Expand",
  description: DESCRIPTION,
  alternates: {
    canonical: "/expand",
  },
  openGraph: {
    type: "website",
    url: "https://policybench.org/expand",
    siteName: "PolicyBench",
    title: "Expand PolicyBench",
    description: DESCRIPTION,
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "PolicyBench — an LLM benchmark for tax and benefit calculation",
      },
    ],
  },
};

function Package({
  title,
  price,
  children,
}: {
  title: string;
  price: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card px-5 py-5 flex flex-col">
      <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
        {title}
      </div>
      <div className="mt-2 font-[family-name:var(--font-display)] text-2xl text-text">
        {price}
      </div>
      <div className="mt-3 text-sm leading-relaxed text-text-secondary">
        {children}
      </div>
    </div>
  );
}

export default function ExpandPage() {
  return (
    <div className="min-h-screen">
      <SiteHeader
        actionLink={{
          label: "Benchmark",
          href: "/",
          type: "internal",
        }}
      />
      <main className="max-w-4xl mx-auto px-4 sm:px-6 pt-12 pb-20">
        <div className="eyebrow mb-3">PolicyBench &middot; expansion</div>
        <h1 className="font-[family-name:var(--font-display)] text-4xl md:text-5xl text-text tracking-tight">
          Expand PolicyBench to your region, population, or program
        </h1>

        <p className="mt-6 text-base leading-relaxed text-text-secondary">
          Families already ask AI about the questions that decide their month:
          Do I qualify for SNAP? How much is my credit? Will this job cost me
          Medicaid? The{" "}
          <Link href="/" className="text-primary hover:underline">
            public board
          </Link>{" "}
          <ExpandModelCount modelCount={modelCount} context="frontier" /> on 100
          real households.
          The best model computes 88.7% of amounts within $1. On SNAP cases
          where the family is owed benefits, models answer exactly $0 in 42% of
          answers, and no model gets more than 1 case in 20 right.
          On Medicaid eligibility, the median model misclassifies 1 person in
          15; the weakest, nearly 1 in 3. A family
          told &ldquo;$0&rdquo; does not apply. Those are national numbers —
          nobody measures this for your region.
        </p>

        <p className="mt-4 text-base leading-relaxed text-text-secondary">
          A PolicyBench slice measures it. We draw households from
          survey microdata weighted to your population, cover your programs,
          benchmark the models behind the tools your people use, and compute every
          reference from the law with PolicyEngine. Every miss gets a
          diagnosed failure mode. You get a public slice leaderboard, a
          written analysis of where models fail your population, and a
          briefing. The answer key checks itself in public: references come
          from open-source code, cross-checked against other calculators
          where they exist, and challenged values get adjudicated against
          the statute — the{" "}
          <Link href="/paper" className="text-primary hover:underline">
            methodology and adjudication record
          </Link>{" "}
          are published.
        </p>

        <div className="grid sm:grid-cols-3 gap-4 mt-10">
          <Package title="Program deep-dive" price="from $7,500">
            One program family — SNAP, Medicaid, child care, tax credits —
            <ExpandModelCount modelCount={modelCount} context="board" />.
            Per-model accuracy, diagnosed failure modes, written analysis, and a
            briefing. Fast: the board already holds the raw material.
          </Package>
          <Package title="State or city slice" price="from $20,000">
            New households weighted to your area and program mix. A published
            slice leaderboard beside the national board, the full audit, the
            analysis, and a briefing for your team or grantees.
          </Package>
          <Package title="National or portfolio" price="let&rsquo;s talk">
            A 50-state observatory, or coverage across a whole grantee
            portfolio — including your grantees&rsquo; own tools, run through
            the same households as the board. We scope these directly.
          </Package>
        </div>

        <p className="mt-8 text-sm leading-relaxed text-text-secondary">
          We size samples to the confidence width your question needs, from
          your population — not a fixed household count. Any slice can add
          standing coverage: quarterly refresh and re-analysis, new models as
          they ship, and technical assistance to grantees building AI tools —
          priced with the slice.
        </p>

        <div className="card px-5 py-4 mt-8">
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
            What funding buys — and what it never buys
          </div>
          <p className="mt-2 text-sm leading-relaxed text-text-secondary">
            Funders buy coverage: households, programs, regions, refresh
            cadence. Funding never buys scores, rankings, or placement. No
            model vendor pays for evaluation — vendor funding for separate
            projects never touches the benchmark. Every slice stays public —
            prompts, references, predictions, and diagnoses.
          </p>
        </div>

        <div className="mt-10 flex flex-col sm:flex-row sm:items-center gap-4">
          <a
            href="mailto:contact@policybench.org?subject=Expanding%20PolicyBench"
            className="inline-flex items-center justify-center rounded-full bg-primary px-6 py-3 text-sm font-semibold hover:opacity-90 transition-opacity"
            style={{ color: "var(--background)" }}
          >
            Contact us
          </a>
          <span className="text-sm text-text-secondary">
            contact@policybench.org
          </span>
        </div>
        <p className="mt-4 text-base leading-relaxed text-text-secondary">
          PolicyBench is a project of PolicyEngine, a 501(c)(3) nonprofit —
          engagements work as grants or contracts. We also brief funder
          networks — one slice presented to a convened
          room goes further than a dozen pitches, and we are glad to present
          at yours.
        </p>
      </main>
    </div>
  );
}
