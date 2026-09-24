import { describe, expect, test } from "bun:test";
import { readdirSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  NoteArticle,
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
    expect(markup).toContain(
      "Most models miss SNAP&#x27;s minimum benefit when broad-based categorical eligibility lifts the income limits",
    );
    expect(markup).toContain("release dashboard-data-20260922");
    // The BBCE note moved to the release that excludes the Michigan worker.
    expect(markup).toContain("release dashboard-data-20260922b");
    // Cents stay as written; whole-dollar facts get thousands separators.
    expect(markup).toContain("GPT-6 Sol answers $1,208.40");
    // The unrounded October minimum keeps all four decimals, so nine months
    // of $23.84 and three of it add up to the $287.68 beside them.
    expect(markup).toContain(
      "$23.84 a month through September and a projected $24.3744 from October",
    );
    expect(markup).toContain("$12,000 of financial assistance");
    expect(markup).toContain("holds $48,000 in savings");
    // Whole-number shares are not board rates, so they keep no decimal.
    expect(markup).toContain("74% of answers come in above $0");
    expect(markup).toContain("Claude Fable 5.1 added");
    expect(markup).not.toMatch(/\{[A-Za-z][A-Za-z0-9]*\}/);
  });

  test("the BBCE note links each household by description", () => {
    const note = notes.find(
      (entry) => entry.slug === "2026-09-23-five-snap-households-bbce",
    );
    expect(note).toBeDefined();
    const markup = renderToStaticMarkup(
      createElement(NoteArticle, { note: note!, titleLevel: "h1" }),
    );
    expect(markup).toContain(">Connecticut couple</a>");
    expect(markup).toContain(
      "For each of 4 households that qualify for SNAP food benefits, most of the 42 models on PolicyBench answer $0.",
    );
    expect(markup).toContain(
      "An earlier version of this note, published September 23, counted a fifth household: a Michigan worker who pays child support.",
    );
    expect(markup).toContain(">policyengine-us #9586 (SNAP child support treatment)</a>");
    expect(markup).not.toContain("scenario_045");
    expect(markup).not.toMatch(/>scenario_\d+<\/a>/);
  });

  test("only the September 3 note carries the unrounded-reference footnote", () => {
    const footnoted = notes.filter((note) => {
      const markup = renderToStaticMarkup(
        createElement(NoteArticle, { note, titleLevel: "h1" }),
      );
      return markup.includes(`id="${note.slug}-reference-annual-note"`);
    });
    // The five-household note's $288 is a rounded reference, so it has none.
    expect(footnoted.map((note) => note.slug)).toEqual([
      "2026-09-03-six-snap-households",
    ]);
  });
});
