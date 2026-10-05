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
      expect(resolved.join(" ")).not.toMatch(
        /\{[A-Za-z][A-Za-z0-9]*(?::words)?\}/,
      );
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
      "Most models answer $0 for households that qualify for SNAP under their states&#x27; higher income limits",
    );
    expect(markup).toContain("release dashboard-data-20260922");
    // The BBCE note is on the frozen release.
    expect(markup).toContain("release dashboard-data-20260930");
    // Cents stay as written; whole-dollar facts get thousands separators.
    expect(markup).toContain("GPT-6 Sol answers $1,208.40");
    expect(markup).toContain(
      "six households, four of them among the five here, at $287.68 each",
    );
    expect(markup).toContain("$12,000 of financial assistance");
    expect(markup).toContain("hold $48,000 and $58,700 in savings");
    // Whole-number shares are not board rates, so they keep no decimal.
    expect(markup).toContain("77% come in above $0, against 17%");
    // The September 22 notes close with the later release's figures; board
    // rates keep one decimal there too.
    expect(markup).toContain(
      "A later release, dashboard-data-20260922c, corrects the reference for one output",
    );
    expect(markup).toContain("Claude Opus 5.5 93.0%");
    expect(markup).toContain("Claude Fable 5.1 added");
    expect(markup).not.toMatch(/\{[A-Za-z][A-Za-z0-9]*(?::words)?\}/);
  });

  test("a words placeholder spells out whole numbers under ten", () => {
    const note = {
      ...notes[0],
      facts: { small: 4, large: 12, zero: 0, cents: "4.50" },
      paragraphs: [
        "{small:words} and {large:words} and {zero:words} and {cents:words} and {small}.",
      ],
    };
    expect(interpolateNoteText(note, note.paragraphs[0])).toBe(
      "four and 12 and zero and 4.50 and 4.",
    );
    const markup = renderToStaticMarkup(
      createElement(NoteArticle, { note, titleLevel: "h1" }),
    );
    expect(markup).toContain("four and 12 and zero and 4.50 and 4.");
  });

  test("the BBCE note links each household by description", () => {
    const note = notes.find(
      (entry) => entry.slug === "2026-10-05-five-snap-households-bbce",
    );
    expect(note).toBeDefined();
    expect(note!.date).toBe("2026-10-05");
    expect(note!.release).toBe("dashboard-data-20260930");
    const markup = renderToStaticMarkup(
      createElement(NoteArticle, { note: note!, titleLevel: "h1" }),
    );
    expect(markup).toContain(">Connecticut couple</a>");
    expect(markup).toContain(">Arizona resident</a>");
    expect(markup).toContain(
      "For each of five households that qualify for SNAP food benefits, most of the 46 models on PolicyBench answer $0.",
    );
    expect(markup).toContain(
      "$288 for 2026 for four households, and $240 for an Arizona resident who qualifies from March",
    );
    expect(markup).toContain(
      "$24 a month through September 2026 and $25 from October",
    );
    expect(markup).toContain("GPT-6 Astra gets three of the five households right");
    expect(markup).toContain(
      "GPT-6.1 Sol gets two right, the Michigan and Wisconsin households",
    );
    expect(markup).toContain(
      "An earlier version of this note, first published September 23, counted the worker among its households.",
    );
    expect(markup).not.toContain("revised this note");
    expect(markup).not.toContain("updated this note");
    expect(markup).toContain(">policyengine-us #9586 (SNAP child support treatment)</a>");
    expect(markup).not.toContain("scenario_045");
    expect(markup).not.toMatch(/>scenario_\d+<\/a>/);
  });

  test("the September 3 note links the later correction", () => {
    const note = notes.find(
      (entry) => entry.slug === "2026-09-03-six-snap-households",
    );
    const markup = renderToStaticMarkup(
      createElement(NoteArticle, { note: note!, titleLevel: "h1" }),
    );
    expect(markup).toContain(
      "A later note, published October 5, corrects this one. From release dashboard-data-20260922c on, PolicyBench scores the SNAP amounts of four of these six households at $288 each, and scores a Michigan worker who pays child support at $0",
    );
    expect(markup).toContain(
      'href="https://github.com/PolicyEngine/policybench/releases/tag/dashboard-data-20260922c"',
    );
    expect(markup).not.toContain("scenario_045 and scenario_112");
    expect(markup).toContain(
      'href="/notes/2026-10-05-five-snap-households-bbce"',
    );
    expect(markup).not.toContain("2026-09-23-five-snap-households-bbce");
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
