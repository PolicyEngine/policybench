import type { Metadata } from "next";

import {
  NOTES_INTRO,
  NotesPageContent,
} from "../../components/NotesContent";
import SiteHeader from "../../components/SiteHeader";

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
