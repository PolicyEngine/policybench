import claudeFable51Added from "./2026-09-01-claude-fable-5-1-added.json";
import sixSnapHouseholds from "./2026-09-03-six-snap-households.json";

export type NoteFact = number | string | string[];

export type NoteDataLink = {
  label: string;
  href: string;
};

export type PolicyBenchNote = {
  slug: string;
  date: string;
  title: string;
  paragraphs: string[];
  facts: Record<string, NoteFact>;
  mentionRegexes?: Record<string, string>;
  data: NoteDataLink[];
  boardSnapshot: "2026-09-01";
  release: "dashboard-data-20260901c";
};

export const notes = [
  sixSnapHouseholds,
  claudeFable51Added,
] as PolicyBenchNote[];

export function getNote(slug: string): PolicyBenchNote | undefined {
  return notes.find((note) => note.slug === slug);
}
