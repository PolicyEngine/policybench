import { describe, expect, test } from "bun:test";
import { readdirSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  NotesPageContent,
  interpolateNoteText,
} from "../src/components/NotesContent";
import { notes } from "../src/notes";

describe("notes", () => {
  test("the index is newest first", () => {
    expect(notes.map((note) => note.date)).toEqual(
      [...notes].map((note) => note.date).sort().reverse(),
    );
  });

  test("slugs are unique and match JSON filenames", () => {
    const slugs = notes.map((note) => note.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
    const filenames = readdirSync(new URL("../src/notes", import.meta.url))
      .filter((name) => name.endsWith(".json"))
      .map((name) => name.replace(/\.json$/, ""))
      .sort();
    expect([...slugs].sort()).toEqual(filenames);
  });

  test("every paragraph placeholder resolves", () => {
    for (const note of notes) {
      const resolved = note.paragraphs.map((paragraph) =>
        interpolateNoteText(note, paragraph),
      );
      expect(resolved.join(" ")).not.toMatch(/\{[A-Za-z][A-Za-z0-9]*\}/);
    }
  });

  test("the notes page renders every title without unresolved placeholders", () => {
    const markup = renderToStaticMarkup(createElement(NotesPageContent));
    expect(markup).toContain("GPT-6 Astra debuts second: the two rules it invented");
    expect(markup).toContain("release dashboard-data-20260905c");
    // Whole-number board rates keep one decimal.
    expect(markup).toContain("at 88.0% of answers within $1");
    expect(markup).not.toContain("at 88% of answers");
    expect(markup).toContain("release dashboard-data-20260901c");
    expect(markup).toContain("Six SNAP households the top three models deny");
    expect(markup).toContain("Claude Fable 5.1 added");
    expect(markup).not.toMatch(/\{[A-Za-z][A-Za-z0-9]*\}/);
  });
});
