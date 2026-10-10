import { describe, expect, test } from "bun:test";

import nextConfig, { noteRedirects } from "../next.config";
import { getNote, notes } from "../src/notes";

describe("note redirects", () => {
  test("the September 23 BBCE URL redirects permanently to the October 5 note", async () => {
    const redirects = await nextConfig.redirects!();
    expect(redirects).toEqual(noteRedirects);
    expect(redirects).toContainEqual({
      source: "/notes/2026-09-23-five-snap-households-bbce",
      destination: "/notes/2026-10-05-five-snap-households-bbce",
      permanent: true,
    });
  });

  test("every redirect leaves a URL no note owns for a note that exists", async () => {
    const redirects = await nextConfig.redirects!();
    const slugs = new Set(notes.map((note) => note.slug));
    for (const redirect of redirects) {
      const source = redirect.source.replace(/^\/notes\//, "");
      const destination = redirect.destination.replace(/^\/notes\//, "");
      expect(redirect.source.startsWith("/notes/")).toBe(true);
      expect(redirect.destination.startsWith("/notes/")).toBe(true);
      expect(slugs.has(source)).toBe(false);
      expect(getNote(destination)).toBeDefined();
      expect(redirect.permanent).toBe(true);
    }
  });

  test("no note links a redirected URL", async () => {
    const redirects = await nextConfig.redirects!();
    const sources = new Set(redirects.map((redirect) => redirect.source));
    for (const note of notes) {
      for (const entry of note.data) {
        expect(sources.has(entry.href)).toBe(false);
      }
    }
  });
});
