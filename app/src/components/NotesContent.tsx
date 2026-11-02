import Link from "next/link";
import { Fragment, type ReactNode } from "react";

import { notes, type NoteFact, type PolicyBenchNote } from "../notes";

// A fact placeholder: `{key}`, or `{key:words}` to spell out a whole number
// under ten in running prose ("four households", not "4 households").
const PLACEHOLDER = /\{([A-Za-z][A-Za-z0-9]*)(?::(words))?\}/g;

type FactFormat = "words" | undefined;

const NUMBER_WORDS = [
  "zero",
  "one",
  "two",
  "three",
  "four",
  "five",
  "six",
  "seven",
  "eight",
  "nine",
];

export const NOTES_INTRO =
  "Dated records of board changes and findings. Each note names the data release its numbers come from, and a test in the repository checked every number against the frozen snapshot of that release.";

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

function factText(key: string, fact: NoteFact, format?: FactFormat): string {
  if (Array.isArray(fact)) return fact.join(", ");
  if (
    format === "words" &&
    typeof fact === "number" &&
    Number.isInteger(fact) &&
    fact >= 0 &&
    fact < NUMBER_WORDS.length
  ) {
    return NUMBER_WORDS[fact];
  }
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
  return paragraph.replace(
    PLACEHOLDER,
    (_, key: string, format: FactFormat) => {
      const fact = note.facts[key];
      if (fact === undefined) throw new Error(`Unknown note fact: ${key}`);
      return factText(key, fact, format);
    },
  );
}

const PROSE_LINK =
  "text-primary-strong underline decoration-primary-strong/30 decoration-1 underline-offset-[3px] transition-colors hover:decoration-primary-strong";

function NoteLink({
  href,
  className = PROSE_LINK,
  children,
}: {
  href: string;
  className?: string;
  children: ReactNode;
}) {
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
  format?: FactFormat,
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
  return factText(key, fact, format);
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
    const format = match[2] as FactFormat;
    const fact = note.facts[key];
    if (fact === undefined) throw new Error(`Unknown note fact: ${key}`);
    content.push(
      <Fragment key={`${key}-${index}`}>
        {factNode(note, key, fact, format)}
      </Fragment>,
    );
    cursor = index + match[0].length;
  }
  if (cursor < paragraph.length) content.push(paragraph.slice(cursor));
  return (
    <p className="text-base leading-7 text-text">
      {content}
    </p>
  );
}

function releaseHref(release: string): string {
  return `https://github.com/PolicyEngine/policybench/releases/tag/${release}`;
}

// The data links name where each file lives, so a reader can tell a release
// download from a script or another page of the site before following it.
function dataSource(href: string): string {
  if (href.startsWith("/")) return "PolicyBench";
  if (href.includes("/releases/download/")) return "Download";
  if (href.includes("/releases/")) return "Release";
  if (href.includes("/pull/")) return "Pull request";
  if (href.includes("/issues/")) return "Issue";
  if (href.includes("/tree/")) return "Folder";
  const path = href.split(/[?#]/)[0];
  if (/\.(csv|json|parquet|gz)$/.test(path)) return "Data";
  if (/\.(py|ts|sh)$/.test(path)) return "Script";
  if (/\.md$/.test(path)) return "Document";
  if (href.includes("github.com")) return "GitHub";
  return new URL(href).hostname.replace(/^www\./, "");
}

function ArrowIcon({ external }: { external: boolean }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      className="h-3.5 w-3.5 shrink-0 text-text-muted transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-primary-strong"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {external ? (
        <path d="M5.5 10.5l5-5M6.5 5.5h4v4" />
      ) : (
        <path d="M3.5 8h9M9 4.5L12.5 8 9 11.5" />
      )}
    </svg>
  );
}

const META_TEXT =
  "text-[11px] font-medium uppercase tracking-[0.12em] text-text-muted";

function MetaDot() {
  return (
    <span aria-hidden="true" className="text-border">
      ·
    </span>
  );
}

function NoteMeta({ note }: { note: PolicyBenchNote }) {
  return (
    <div className={`flex flex-wrap items-baseline gap-x-2.5 gap-y-1 ${META_TEXT}`}>
      <time dateTime={note.date} className="text-primary-strong">
        {formatNoteDate(note.date)}
      </time>
      <MetaDot />
      <a
        href={releaseHref(note.release)}
        title="The numbers in this note come from this data release"
        className="underline decoration-border underline-offset-[3px] transition-colors hover:text-primary-strong hover:decoration-primary-strong"
      >
        release {note.release}
      </a>
      <MetaDot />
      <span>board snapshot {note.boardSnapshot}</span>
    </div>
  );
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
      <NoteMeta note={note} />
      <Title className="mt-3 text-balance font-[family-name:var(--font-display)] text-[28px] leading-tight tracking-tight text-text sm:text-[34px]">
        {title}
      </Title>

      <div className="mt-6 space-y-4">
        {note.paragraphs.map((paragraph, index) => (
          <NoteParagraph
            key={index}
            note={note}
            paragraph={paragraph}
          />
        ))}
      </div>

      {typeof annualReference === "number" ? (
        <p
          id={`${note.slug}-reference-annual-note`}
          className="mt-6 border-t border-border-subtle pt-3 text-xs leading-relaxed text-text-muted"
        >
          <sup>1</sup> Unrounded frozen reference: ${annualReference.toFixed(2)}.
        </p>
      ) : null}

      <section
        aria-labelledby={`${note.slug}-data`}
        className="card mt-10 px-5 py-5 sm:px-6"
      >
        <DataTitle
          id={`${note.slug}-data`}
          className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted"
        >
          Data
        </DataTitle>
        <ul className="mt-3 divide-y divide-border-subtle">
          {note.data.map((entry) => {
            const external = !entry.href.startsWith("/");
            return (
              <li
                key={`${entry.label}:${entry.href}`}
                className="group relative flex items-center gap-3 py-2.5 text-sm text-text-secondary transition-colors hover:text-primary-strong"
              >
                <NoteLink
                  href={entry.href}
                  className="min-w-0 flex-1 after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:rounded-md focus-visible:after:ring-2 focus-visible:after:ring-primary-strong"
                >
                  {entry.label}
                </NoteLink>
                <span
                  className="hidden shrink-0 text-[10px] font-medium uppercase tracking-[0.12em] text-text-muted sm:inline"
                  aria-hidden="true"
                >
                  {dataSource(entry.href)}
                </span>
                <ArrowIcon external={external} />
              </li>
            );
          })}
        </ul>
      </section>
    </article>
  );
}

function monthLabel(date: string): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "long",
    timeZone: "UTC",
  }).format(new Date(`${date}T00:00:00Z`));
}

function groupByMonth(
  list: PolicyBenchNote[],
): { month: string; notes: PolicyBenchNote[] }[] {
  const groups: { month: string; notes: PolicyBenchNote[] }[] = [];
  for (const note of list) {
    const month = monthLabel(note.date);
    const last = groups[groups.length - 1];
    if (last && last.month === month) last.notes.push(note);
    else groups.push({ month, notes: [note] });
  }
  return groups;
}

function NoteCard({ note }: { note: PolicyBenchNote }) {
  return (
    <article className="card card-hover group relative px-5 py-5 sm:px-6 sm:py-6">
      <div className={`flex flex-wrap items-baseline gap-x-2.5 gap-y-1 ${META_TEXT}`}>
        <time dateTime={note.date} className="text-primary-strong">
          {formatNoteDate(note.date)}
        </time>
        <MetaDot />
        <span>release {note.release}</span>
      </div>
      <h3 className="mt-2.5 text-balance font-[family-name:var(--font-display)] text-xl leading-snug tracking-tight text-text transition-colors group-hover:text-primary-strong sm:text-2xl">
        <Link
          href={`/notes/${note.slug}`}
          className="after:absolute after:inset-0 after:rounded-[16px] focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-primary-strong"
        >
          {note.title}
        </Link>
      </h3>
      <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-text-secondary sm:text-[15px]">
        {interpolateNoteText(note, note.paragraphs[0])}
      </p>
      <span
        className="mt-4 inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.12em] text-primary-strong"
        aria-hidden="true"
      >
        Read note
        <ArrowIcon external={false} />
      </span>
    </article>
  );
}

function monthId(month: string): string {
  return month.toLowerCase().replace(/\s+/g, "-");
}

export function NotesPageContent() {
  const groups = groupByMonth(notes);
  return (
    <div className="mx-auto max-w-7xl px-4 pb-24 pt-10 sm:px-6 sm:pt-14">
      <div className="grid gap-10 md:grid-cols-[180px_minmax(0,960px)] md:gap-12">
        <nav aria-label="Months" className="hidden md:block">
          <ul className="sticky top-8 space-y-2 border-l border-border-subtle">
            {groups.map((group) => (
              <li key={group.month}>
                <a
                  href={`#${monthId(group.month)}`}
                  className="-ml-px block border-l border-transparent pl-4 text-[11px] font-medium uppercase tracking-[0.12em] text-text-muted transition-colors hover:border-primary-strong hover:text-primary-strong"
                >
                  {group.month}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="space-y-12">
          {groups.map((group) => (
            <section
              key={group.month}
              id={monthId(group.month)}
              aria-labelledby={`${monthId(group.month)}-label`}
              className="scroll-mt-8"
            >
              <div className="mb-4 flex items-center gap-4">
                <h2
                  id={`${monthId(group.month)}-label`}
                  className="shrink-0 text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted"
                >
                  {group.month}
                </h2>
                <div className="h-px flex-1 bg-border-subtle" />
              </div>
              <div className="space-y-4">
                {group.notes.map((note) => (
                  <NoteCard key={note.slug} note={note} />
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}

export function NoteNeighbors({ note }: { note: PolicyBenchNote }) {
  const index = notes.findIndex((entry) => entry.slug === note.slug);
  // The index is newest first, so the newer note sits one place earlier.
  const newer = index > 0 ? notes[index - 1] : undefined;
  const older = index >= 0 ? notes[index + 1] : undefined;
  if (!newer && !older) return null;
  const linkClass =
    "card card-hover group flex flex-col gap-1.5 px-5 py-4 text-left";
  return (
    <nav
      aria-label="More notes"
      className="mt-14 grid gap-3 border-t border-border-subtle pt-8 sm:grid-cols-2"
    >
      {older ? (
        <Link href={`/notes/${older.slug}`} className={linkClass}>
          <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
            ← Older · {formatNoteDate(older.date)}
          </span>
          <span className="text-sm leading-snug text-text transition-colors group-hover:text-primary-strong">
            {older.title}
          </span>
        </Link>
      ) : (
        <span className="hidden sm:block" />
      )}
      {newer ? (
        <Link
          href={`/notes/${newer.slug}`}
          className={`${linkClass} sm:items-end sm:text-right`}
        >
          <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
            Newer · {formatNoteDate(newer.date)} →
          </span>
          <span className="text-sm leading-snug text-text transition-colors group-hover:text-primary-strong">
            {newer.title}
          </span>
        </Link>
      ) : null}
    </nav>
  );
}
