import claudeFable51Added from "./2026-09-01-claude-fable-5-1-added.json";
import sixSnapHouseholds from "./2026-09-03-six-snap-households.json";
import gpt6AstraDebutsSecond from "./2026-09-05-gpt-6-astra-debuts-second.json";

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
  // The board snapshot and data release the facts were checked against; a
  // note keeps its own release when later releases move the board.
  boardSnapshot: string;
  release: string;
};

export const notes = [
  gpt6AstraDebutsSecond,
  sixSnapHouseholds,
  claudeFable51Added,
] as PolicyBenchNote[];

export function getNote(slug: string): PolicyBenchNote | undefined {
  return notes.find((note) => note.slug === slug);
}
