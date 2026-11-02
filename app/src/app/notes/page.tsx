import type { Metadata } from "next";

import {
  NOTES_INTRO,
  NotesPageContent,
  formatNoteDate,
} from "../../components/NotesContent";
import SiteHeader from "../../components/SiteHeader";
import { notes } from "../../notes";

export const metadata: Metadata = {
  title: "Notes",
  description: NOTES_INTRO,
  alternates: {
    canonical: "/notes",
  },
  openGraph: {
    type: "website",
    url: "https://policybench.org/notes",
    siteName: "PolicyBench",
    title: "PolicyBench notes",
    description: NOTES_INTRO,
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "PolicyBench — an LLM benchmark for tax and benefit calculation",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "PolicyBench notes",
    description: NOTES_INTRO,
    images: ["/og-image.png"],
  },
};

export default function NotesPage() {
  const expanded = (
    <>
      <h1 className="font-[family-name:var(--font-display)] text-3xl tracking-tight text-text sm:text-4xl">
        Notes
      </h1>
      <p className="mt-4 max-w-2xl text-sm leading-relaxed text-text-secondary sm:text-base">
        {NOTES_INTRO}
      </p>
      <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-3">
        <div className="flex items-baseline gap-1.5">
          <span className="font-[family-name:var(--font-mono)] text-lg font-semibold tracking-tight text-primary sm:text-xl">
            {notes.length}
          </span>
          <span className="text-[10px] font-medium uppercase tracking-[0.12em] text-text-muted">
            notes
          </span>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.12em] text-text-secondary">
          <span
            className="h-1.5 w-1.5 rounded-full bg-primary/70"
            aria-hidden="true"
          />
          Latest {formatNoteDate(notes[0].date)}
        </span>
      </div>
    </>
  );

  return (
    <main id="main" className="min-h-screen bg-void">
      <SiteHeader
        actionLinks={[
          { label: "Leaderboard", href: "/", type: "internal" },
          { label: "Paper", href: "/paper", type: "internal" },
        ]}
        expandedContent={expanded}
        alwaysExpanded
      />
      <NotesPageContent />
    </main>
  );
}
