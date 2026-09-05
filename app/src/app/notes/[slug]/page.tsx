import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { NoteArticle, interpolateNoteText } from "../../../components/NotesContent";
import SiteHeader from "../../../components/SiteHeader";
import { getNote, notes } from "../../../notes";

export const dynamicParams = false;

export function generateStaticParams() {
  return notes.map((note) => ({ slug: note.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const note = getNote(slug);
  if (!note) notFound();
  const description = interpolateNoteText(note, note.paragraphs[0]);
  const url = `https://policybench.org/notes/${note.slug}`;
  return {
    title: note.title,
    description,
    alternates: { canonical: `/notes/${note.slug}` },
    openGraph: {
      type: "article",
      url,
      siteName: "PolicyBench",
      title: note.title,
      description,
      publishedTime: note.date,
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
      title: note.title,
      description,
      images: ["/og-image.png"],
    },
  };
}

export default async function NotePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const note = getNote(slug);
  if (!note) notFound();

  return (
    <main id="main" className="min-h-screen bg-void">
      <SiteHeader
        actionLinks={[
          { label: "Leaderboard", href: "/", type: "internal" },
          { label: "Paper", href: "/paper", type: "internal" },
        ]}
        alwaysExpanded
      />
      <div className="mx-auto max-w-3xl px-4 pb-20 pt-10 sm:px-6 sm:pt-14">
        <NoteArticle note={note} titleLevel="h1" />
      </div>
    </main>
  );
}
