import Link from "next/link";
import { Fragment, type ReactNode } from "react";

import { notes, type NoteFact, type PolicyBenchNote } from "../notes";

const PLACEHOLDER = /\{([A-Za-z][A-Za-z0-9]*)\}/g;

export const NOTES_INTRO =
  "Dated records of board changes and findings. Each note names the data release its numbers come from; a test in the repository checks every number against the frozen snapshot of that release.";

export function formatNoteDate(date: string): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${date}T00:00:00Z`));
}

// Facts named *Exact or *Rate are board percentages shown to one decimal, so
// a whole-number rate (88.0) keeps its decimal like every other row.
const ONE_DECIMAL_FACT = /(Exact|Rate)$/;

function factText(key: string, fact: NoteFact): string {
  if (Array.isArray(fact)) return fact.join(", ");
  if (key === "referenceAnnual" && typeof fact === "number") {
    return String(Math.round(fact));
  }
  if (ONE_DECIMAL_FACT.test(key) && typeof fact === "number") {
    return fact.toFixed(1);
  }
  if (typeof fact === "number" && Number.isInteger(fact)) {
    return fact.toLocaleString("en-US");
  }
  return String(fact);
}

export function interpolateNoteText(
  note: PolicyBenchNote,
  paragraph: string,
): string {
  return paragraph.replace(PLACEHOLDER, (_, key: string) => {
    const fact = note.facts[key];
    if (fact === undefined) throw new Error(`Unknown note fact: ${key}`);
    return factText(key, fact);
  });
}

function NoteLink({ href, children }: { href: string; children: ReactNode }) {
  const className = "text-primary-strong underline-offset-2 hover:underline";
  if (href.startsWith("/")) {
    return (
      <Link href={href} className={className}>
        {children}
      </Link>
    );
  }
  return (
    <a href={href} className={className}>
      {children}
    </a>
  );
}

function factNode(
  note: PolicyBenchNote,
  key: string,
  fact: NoteFact,
): ReactNode {
  if (Array.isArray(fact)) {
    return fact.map((item, index) => {
      const link = note.data.find((entry) => entry.label === item);
      return (
        <Fragment key={item}>
          {index > 0 ? ", " : null}
          {link ? <NoteLink href={link.href}>{item}</NoteLink> : item}
        </Fragment>
      );
    });
  }
  if (key === "referenceAnnual" && typeof fact === "number") {
    return (
      <>
        {Math.round(fact)}
        <sup className="ml-0.5 text-[0.65em]">
          <a
            href={`#${note.slug}-reference-annual-note`}
            aria-label={`See the unrounded reference amount of $${fact.toFixed(2)}`}
            className="text-primary-strong hover:underline"
          >
            1
          </a>
        </sup>
      </>
    );
  }
  return factText(key, fact);
}

function NoteParagraph({
  note,
  paragraph,
}: {
  note: PolicyBenchNote;
  paragraph: string;
}) {
  const content: ReactNode[] = [];
  let cursor = 0;
  for (const match of paragraph.matchAll(PLACEHOLDER)) {
    const index = match.index;
    if (index > cursor) content.push(paragraph.slice(cursor, index));
    const key = match[1];
    const fact = note.facts[key];
    if (fact === undefined) throw new Error(`Unknown note fact: ${key}`);
    content.push(<Fragment key={`${key}-${index}`}>{factNode(note, key, fact)}</Fragment>);
    cursor = index + match[0].length;
  }
  if (cursor < paragraph.length) content.push(paragraph.slice(cursor));
  return <p className="text-base leading-7 text-text-secondary">{content}</p>;
}

export function NoteArticle({
  note,
  titleLevel,
  linkTitle = false,
}: {
  note: PolicyBenchNote;
  titleLevel: "h1" | "h2";
  linkTitle?: boolean;
}) {
  const Title = titleLevel;
  const title = linkTitle ? (
    <Link href={`/notes/${note.slug}`} className="hover:text-primary-strong">
      {note.title}
    </Link>
  ) : (
    note.title
  );
  const annualReference = note.facts.referenceAnnual;
  const DataTitle = titleLevel === "h1" ? "h2" : "h3";

  return (
    <article id={note.slug} className="scroll-mt-8">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 font-[family-name:var(--font-mono)] text-xs text-text-muted">
        <time dateTime={note.date} className="uppercase tracking-[0.12em]">
          {formatNoteDate(note.date)}
        </time>
        <span aria-hidden="true">·</span>
        <span>
          Numbers from{" "}
          <a
            href={`https://github.com/PolicyEngine/policybench/releases/tag/${note.release}`}
            className="text-primary-strong underline-offset-2 hover:underline"
          >
            release {note.release}
          </a>{" "}
          (board snapshot {note.boardSnapshot})
        </span>
      </div>
      <Title className="mt-2 font-[family-name:var(--font-display)] text-3xl tracking-tight text-text sm:text-4xl">
        {title}
      </Title>

      <div className="mt-6 space-y-4">
        {note.paragraphs.map((paragraph, index) => (
          <NoteParagraph key={index} note={note} paragraph={paragraph} />
        ))}
      </div>

      {typeof annualReference === "number" ? (
        <p
          id={`${note.slug}-reference-annual-note`}
          className="mt-4 text-xs leading-relaxed text-text-muted"
        >
          <sup>1</sup> Unrounded frozen reference: ${annualReference.toFixed(2)}.
        </p>
      ) : null}

      <section aria-labelledby={`${note.slug}-data`} className="mt-8">
        <DataTitle
          id={`${note.slug}-data`}
          className="text-xs font-medium uppercase tracking-[0.14em] text-text-muted"
        >
          Data
        </DataTitle>
        <ul className="mt-3 grid gap-x-6 gap-y-2 text-sm text-text-secondary sm:grid-cols-2">
          {note.data.map((entry) => (
            <li key={`${entry.label}:${entry.href}`}>
              <NoteLink href={entry.href}>{entry.label}</NoteLink>
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}

export function NotesPageContent() {
  return (
    <div className="mx-auto max-w-3xl px-4 pb-20 pt-10 sm:px-6 sm:pt-14">
      <div className="space-y-14">
        {notes.map((note, index) => (
          <Fragment key={note.slug}>
            {index > 0 ? (
              <div className="h-px bg-gradient-to-r from-transparent via-border to-transparent" />
            ) : null}
            <NoteArticle note={note} titleLevel="h2" linkTitle />
          </Fragment>
        ))}
      </div>
    </div>
  );
}
