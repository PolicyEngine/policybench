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
import artifact from "../src/data.artifact.json";
import paperSnapshot from "../src/paperSnapshot.json";

describe("notes", () => {
  // The score definition and the weighting close each release note's opening.
  const closing =
    "PolicyBench counts a dollar amount as right when it falls within $1 of the reference PolicyEngine computes, and an eligibility answer as right when it matches. It weights each answer by household impact.";

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

  test("the notes index lists every note and links its page", () => {
    const markup = renderToStaticMarkup(createElement(NotesPageContent));
    for (const note of notes) {
      expect(markup).toContain(`href="/notes/${note.slug}"`);
      expect(markup).toContain(`release ${note.release}`);
    }
    // Each card's excerpt is the note's first paragraph, as plain text.
    expect(markup).toContain(
      "Most models answer $0 for households that qualify for SNAP under their states&#x27; higher income limits",
    );
    expect(markup).not.toMatch(/\{[A-Za-z][A-Za-z0-9]*(?::words)?\}/);
  });

  test("the notes render every title without unresolved placeholders", () => {
    const markup = notes
      .map((note) =>
        renderToStaticMarkup(
          createElement(NoteArticle, { note, titleLevel: "h1" }),
        ),
      )
      .join("");
    expect(markup).toContain("GPT-6 Astra debuts second: the two rules it invented");
    expect(markup).toContain("release dashboard-data-20260905c");
    // Whole-number board rates keep one decimal.
    expect(markup).toContain("It gets 88.0% of answers right");
    expect(markup).not.toContain("gets 88% of answers");
    expect(markup).toContain("release dashboard-data-20260901c");
    expect(markup).toContain("Six SNAP households the top three models deny");
    expect(markup).toContain(
      "Most models answer $0 for households that qualify for SNAP under their states&#x27; higher income limits",
    );
    expect(markup).toContain("release dashboard-data-20260922");
    // The BBCE note keeps release dashboard-data-20260930, and the October 6
    // release note its own release.
    expect(markup).toContain("release dashboard-data-20260930");
    expect(markup).toContain(
      "PolicyBench stops scoring eight tax outputs whose references turn on facts the prompts never state",
    );
    expect(markup).toContain("release dashboard-data-20261006");
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

  test("the newest note is the frozen release's, ahead of the October 31 one", () => {
    // The live pointer names the frozen release (src/data.artifact.json).
    expect(notes[0].slug).toBe("2026-11-12-claude-fable-5-2-joins-the-board");
    expect(notes[0].release).toBe(artifact.tag);
    expect(notes[0].boardSnapshot).toBe(paperSnapshot.snapshotDate);
    expect(notes[0].slug.startsWith(notes[0].date)).toBe(true);
    // The October 31 release note keeps release 20261027 and its board
    // snapshot.
    expect(notes[1].slug).toBe("2026-10-31-gpt-6-1-terra-joins-the-board");
    expect(notes[1].release).toBe("dashboard-data-20261027");
    expect(notes[1].boardSnapshot).toBe("2026-10-27");
    expect(notes[1].slug.startsWith(notes[1].date)).toBe(true);
    // The October 20 tool-pilot note, the October 19 America.gov note and the
    // October 14 release note keep release 20261014 and its board snapshot.
    expect(notes[2].slug).toBe(
      "2026-10-20-given-a-policyengine-tool-three-models-score-above-99",
    );
    expect(notes[3].slug).toBe("2026-10-19-america-gov-scores-level-with-gpt-5-5");
    expect(notes[4].slug).toBe("2026-10-14-gemini-4-argon-joins-the-board");
    for (const note of notes.slice(2, 5)) {
      expect(note.release).toBe("dashboard-data-20261014");
      expect(note.boardSnapshot).toBe("2026-10-14");
      expect(note.slug.startsWith(note.date)).toBe(true);
    }
    // The October 13 and October 10 notes keep their own releases and board
    // snapshots.
    expect(notes[5].slug).toBe("2026-10-13-muse-wonder-joins-the-board");
    expect(notes[5].release).toBe("dashboard-data-20261013");
    expect(notes[5].boardSnapshot).toBe("2026-10-13");
    expect(notes[6].slug).toBe("2026-10-10-claude-haiku-5-5-joins-the-board");
    expect(notes[6].release).toBe("dashboard-data-20261010");
    expect(notes[6].boardSnapshot).toBe("2026-10-10");
    expect(notes[7].slug).toBe(
      "2026-10-06-policybench-stops-scoring-eight-tax-outputs",
    );
  });

  test("the Claude Fable 5.2 note renders its figures", () => {
    const note = notes.find(
      (n) => n.slug === "2026-11-12-claude-fable-5-2-joins-the-board",
    )!;
    const markup = renderToStaticMarkup(
      createElement(NoteArticle, { note, titleLevel: "h1" }),
    );
    expect(markup).toContain(
      "PolicyBench added Claude Fable 5.2 to its 2026-11-11 snapshot, two days after Anthropic released it, bringing the board to 52 models.",
    );
    // Board rates keep one decimal, a whole one too.
    expect(markup).toContain(
      "Claude Fable 5.2 gets 92.0% of answers right and ranks #5 of 52, behind GPT-5.6 Sol (93.1%) and ahead of GPT-6 Astra (91.7%, #6).",
    );
    expect(markup).toContain(
      "GPT-6 Sol still leads at 95.2%, ahead of Claude Opus 5.5 (94.1%) and GPT-6.1 Terra (93.1%).",
    );
    expect(markup).toContain(
      "Claude Fable 5.2 ranks #3, behind only GPT-6 Sol and Claude Opus 5.5.",
    );
    expect(markup).toContain(closing);
    // Thousands get separators; whole numbers under ten are spelled out.
    expect(markup).toContain(
      "drew a thinking block that took 1,789 of its 2,881 output tokens.",
    );
    expect(markup).toContain(
      "On six households the answer ran past the row&#x27;s first budget of 16,384 output tokens",
    );
    // Costs keep their cents.
    expect(markup).toContain(
      "the 100 households cost $31.69, against $6.75 for Claude Opus 5.5 and $3.43 for Claude Sonnet 5.5.",
    );
    expect(markup).toContain(
      "Claude Fable 5.1, the Fable model before it, gets 90.8% (#9) and cost $25.70.",
    );
    expect(markup).toContain(
      "with a certificate, the credit and the output are $1,921.",
    );
    expect(markup).toContain(
      "Of the 52 models, 43 answer $0, eight give a positive amount, none of them $1,921, and one gives no answer.",
    );
    expect(markup).toContain(
      "Every model is now scored on 1,934 of its 1,984 requested outputs, down from 1,935, and PolicyBench excludes 50.",
    );
    // A bound on a move is not a board rate, so it keeps its two decimals.
    expect(markup).toContain(
      "the exclusion moves each of the 51 earlier models&#x27; shares of answers right by less than 0.01 points: the 42 that answered $0 fall, and the nine that did not rise.",
    );
    expect(markup).toContain(
      "gives the same value as 2.60.0 for all 1,934 scored outputs; it moves three excluded outputs",
    );
    expect(markup).toContain(
      "Claude Opus 5.5 judged the misses in the 122 audit cases Claude Fable 5.2 joined, on 2026-11-11, and it flagged seven references as suspect. Of the seven, six already had decisions, which this release keeps: four are outputs PolicyBench excludes, and two are references it affirmed in earlier releases.",
    );
    expect(markup).toContain(
      "the judge gave eight models&#x27; answers each a class",
    );
    expect(markup).toContain("All three outputs stay scored.");
    expect(markup).toContain('href="/model/claude-fable-5.2"');
    expect(markup).toContain(
      'href="https://github.com/PolicyEngine/policybench/releases/tag/dashboard-data-20261111"',
    );
    expect(markup).not.toMatch(/\{[A-Za-z][A-Za-z0-9]*(?::words)?\}/);
  });

  test("the GPT-6.1 Terra note renders its figures", () => {
    const note = notes.find(
      (n) => n.slug === "2026-10-31-gpt-6-1-terra-joins-the-board",
    )!;
    const markup = renderToStaticMarkup(
      createElement(NoteArticle, { note, titleLevel: "h1" }),
    );
    expect(markup).toContain(
      "PolicyBench added OpenAI&#x27;s GPT-6.1 Terra to its 2026-10-27 snapshot, the day after OpenAI released it, bringing the board to 51 models.",
    );
    // Board rates keep one decimal.
    expect(markup).toContain(
      "GPT-6.1 Terra gets 93.1% of answers right and ranks #3 of 51.",
    );
    expect(markup).toContain("GPT-6.1 Terra ranks #5.");
    expect(markup).toContain(
      "GPT-6.1 Sol, which OpenAI released on September 29, gets 90.2% of answers right (#10).",
    );
    expect(markup).toContain(closing);
    // Costs keep their cents.
    expect(markup).toContain(
      "the 100 households cost $1.25, against $2.30 for GPT-6.1 Sol and $2.71 for GPT-6 Sol.",
    );
    expect(markup).toContain("The move changes four scored references");
    expect(markup).toContain("now gets the $24 monthly minimum, $288 a year");
    expect(markup).toContain(
      "every model is still scored on 1,935 of its 1,984 requested outputs.",
    );
    expect(markup).toContain(
      "gives the same value as 2.60.0 for all 1,935; it moves one excluded output",
    );
    expect(markup).toContain(
      "Against the previous release, 47 of the 50 earlier models fall, by 0.03 to 0.07 points, and three rise by 0.02.",
    );
    expect(markup).toContain("only three give the Californian&#x27;s new SNAP");
    expect(markup).toContain('href="/model/gpt-6.1-terra"');
    expect(markup).toContain(
      'href="https://github.com/PolicyEngine/policybench/releases/tag/dashboard-data-20261027"',
    );
    expect(markup).not.toMatch(/\{[A-Za-z][A-Za-z0-9]*(?::words)?\}/);
  });

  test("the tool-pilot note renders its figures", () => {
    const note = notes.find(
      (n) =>
        n.slug === "2026-10-20-given-a-policyengine-tool-three-models-score-above-99",
    )!;
    const markup = renderToStaticMarkup(
      createElement(NoteArticle, { note, titleLevel: "h1" }),
    );
    expect(markup).toContain(
      "GPT-6 Sol, which leads the board at 95.2% of answers right, gets 99.2% with the tool.",
    );
    expect(markup).toContain(
      "Claude Opus 5.5 goes from 94.1% to 99.8%, and Gemini 4 Argon from 88.7% to 99.9%.",
    );
    expect(markup).toContain(
      "PolicyBench weights each answer by household impact in these six scores.",
    );
    expect(markup).toContain(
      "Of the 187 nonzero amounts, GPT-6 Sol gets 67.4% within $1 on its own and 96.8% with the tool",
    );
    // The nonzero-amount rates count each amount once.
    expect(markup).toContain(
      "and Gemini 4 Argon, 46.5% and 99.5%. PolicyBench gives each amount the same weight in these six rates.",
    );
    // Whole numbers under ten are spelled out; costs keep their cents.
    expect(markup).toContain(
      "With the tool, 12 answers are wrong across the three runs: nine of GPT-6 Sol&#x27;s, two of Claude Opus 5.5&#x27;s and one of Gemini 4 Argon&#x27;s.",
    );
    expect(markup).toContain("GPT-6 Sol costs $5.63 with it and $2.71 without");
    expect(markup).toContain(
      "In five of GPT-6 Sol&#x27;s, it had used all eight calculation turns the pilot allows.",
    );
    expect(markup).toContain(
      "not board rows, since the board scores models answering alone, and the result is circular",
    );
    expect(markup).toContain(
      "1,065 of the 1,632 facts the prompts state, not counting ages and wages",
    );
    expect(markup).toContain(
      'href="https://github.com/PolicyEngine/policybench/blob/main/notes/data/tool_pilot_20261015.csv"',
    );
    expect(markup).not.toMatch(/\{[A-Za-z][A-Za-z0-9]*(?::words)?\}/);
  });

  test("the America.gov note renders its figures", () => {
    const note = notes.find(
      (n) => n.slug === "2026-10-19-america-gov-scores-level-with-gpt-5-5",
    )!;
    const markup = renderToStaticMarkup(
      createElement(NoteArticle, { note, titleLevel: "h1" }),
    );
    expect(markup).toContain(
      "America.gov, which says it answers questions with AI and information from government websites, scores 87.9% on PolicyBench.",
    );
    expect(markup).toContain(
      "PolicyBench counts a dollar amount as right when it falls within $1 of the reference PolicyEngine computes, and an eligibility answer as right when it matches. It weights each answer by household impact.",
    );
    expect(markup).toContain(
      "GPT-5.5, which OpenAI released in April, matches that score with AI alone and no web access, while GPT-6 Sol leads at 95.2%, also with AI alone.",
    );
    expect(markup).toContain(
      "America.gov would rank #14 of 51, but PolicyBench keeps its board to AI alone.",
    );
    // Rates keep one decimal, so GPT-6 Sol's state income tax rate reads 72.0%.
    expect(markup).toContain(
      "On income taxes, America.gov falls between GPT-5.5 and GPT-6 Sol: it gets 72.6% of federal amounts within $1, against their 70.2% and 90.5%, and 66.7% of state amounts, against 65.6% and 72.0%.",
    );
    expect(markup).toContain(
      "It trails both on SNAP amounts and Medicaid eligibility. On SNAP it gets 81.7%, against 84.9% and 89.2%,",
    );
    expect(markup).toContain(
      "On Medicaid eligibility, which PolicyBench weights most heavily, it gets 92.5%, against 96.5% and 97.7%. It called both adults in a New York couple eligible, where PolicyEngine and 49 models find neither eligible.",
    );
    expect(interpolateNoteText(note, note.paragraphs[0]).length).toBeLessThan(600);
    // Whole numbers under ten are spelled out; thousands get separators.
    expect(markup).toContain(
      "America.gov refused prompts for five households on the first attempt.",
    );
    expect(markup).toContain(
      "Six prompts run past the 8,000 characters America.gov asks a message to stay within, so PolicyBench split each across two chats asking for half the outputs apiece.",
    );
    expect(markup).toContain(
      "When PolicyBench asked again, America.gov answered two of those prompts in full and repeated its refusal word for word on the other three, which leaves 3.7% of its scored answers blank. Of the 50 models on the board, 46 answer every one.",
    );
    expect(markup).toContain(
      "and it put a Michigan couple&#x27;s SNAP at $6,432 a year, where PolicyEngine and 49 of the 50 models give $0.",
    );
    expect(markup).toContain(
      "The board&#x27;s prompts name PolicyEngine, the open-source tax and benefit model behind the references, in four output definitions.",
    );
    // React writes the note's straight double quotes as &quot;.
    expect(markup).toContain(
      "They ask about Medicaid and CHIP eligibility &quot;under PolicyEngine rules,&quot; and ask &quot;whether PolicyEngine returns&quot; support for free and for reduced-price school meals.",
    );
    expect(markup).toContain(
      "PolicyBench is revising that wording. At least two of America.gov&#x27;s five refusals cited PolicyEngine, and no model on the board declined a household on that ground.",
    );
    expect(markup).toContain("it replied to the prompt for a Virginia single parent of two.");
    expect(markup).toContain(
      "The General Services Administration has run America.gov since September 29.",
    );
    expect(markup).toContain(
      "Between October 14 and 18, PolicyBench sent each of its 100 households to America.gov in a new chat, with the board&#x27;s own prompt in the JSON answer format. It scored every reply as it scores the board.",
    );
    expect(markup).toContain(
      "Before publishing a run, PolicyBench asks again whenever a board model leaves answers out. America.gov got the same kind of retry: PolicyBench sent each refused prompt again, word for word, in a fresh chat, up to twice. On first attempts alone, America.gov gets 86.6% (#19).",
    );
    expect(markup).toContain(
      "On the answers each gave, America.gov leads GPT-5.5 on two of those four outputs and trails it by at most 1.3 points on the others.",
    );
    expect(markup).toContain(
      "If PolicyBench left all four out for every model, America.gov would rank #13 of 51.",
    );
    expect(markup).toContain(
      "America.gov&#x27;s terms say the answers it generates with AI &quot;can be incomplete or wrong.&quot;",
    );
    expect(markup).toContain(
      "PolicyBench tested America.gov once and skipped the last retry it gives board models, in which it asks again, one at a time, for each answer still missing.",
    );
    expect(markup).toContain(
      "If PolicyBench ran that retry, it would need at least 73 more chats, and America.gov could rise to 89.8% at most.",
    );
    expect(markup).toContain(
      'href="https://github.com/PolicyEngine/policybench/blob/main/notes/data/america_gov_20261019.csv"',
    );
    expect(markup).not.toMatch(/\{[A-Za-z][A-Za-z0-9]*(?::words)?\}/);
  });

  test("the Gemini 4 Argon note renders its figures", () => {
    const note = notes.find(
      (n) => n.slug === "2026-10-14-gemini-4-argon-joins-the-board",
    )!;
    const markup = renderToStaticMarkup(
      createElement(NoteArticle, { note, titleLevel: "h1" }),
    );
    expect(markup).toContain(
      "Google&#x27;s Gemini 4 Argon joined the board on 2026-10-14, the day after Google opened it to the public Gemini API, and Meta&#x27;s Muse Spark 1.3 joined with it, bringing the board to 50 models.",
    );
    // Board rates keep one decimal.
    expect(markup).toContain(
      "Gemini 4 Argon gets 88.7% of answers right and ranks #12 of 50, the highest of any Gemini model. Gemini 3.8 Flash, the previous best, gets 85.6% (#21).",
    );
    expect(markup).toContain(
      "Muse Spark 1.3 gets 87.2% (#18), behind Meta&#x27;s Muse Wonder (90.1%, #10)",
    );
    expect(markup).toContain("it ranks #6.");
    // After the bounded rank, the leader's rate names its metric.
    expect(markup).toContain(
      "GPT-6 Sol still leads at 95.2% of answers right, ahead of Claude Opus 5.5 (94.1%) and GPT-5.6 Sol (93.1%).",
    );
    expect(markup).toContain(closing);
    expect(markup).toContain(
      "With the forced tool Gemini 4 Argon returned reasoning tokens on 80 of them, and on 85 in the board&#x27;s own run; with an automatic tool choice, on 82.",
    );
    // A cost keeps its cents.
    expect(markup).toContain("the 100 households cost $2.79.");
    expect(markup).toContain(
      "every model is still scored on 1,935 of its 1,984 requested outputs. Each of the 48 earlier models keeps its score.",
    );
    expect(markup).toContain('href="/model/gemini-4-argon"');
    expect(markup).toContain('href="/model/muse-spark-1.3"');
    expect(markup).toContain(
      'href="https://github.com/PolicyEngine/policybench/releases/tag/dashboard-data-20261014"',
    );
    expect(markup).not.toMatch(/\{[A-Za-z][A-Za-z0-9]*(?::words)?\}/);
  });

  test("the Muse Wonder note renders its figures", () => {
    const note = notes.find(
      (n) => n.slug === "2026-10-13-muse-wonder-joins-the-board",
    )!;
    const markup = renderToStaticMarkup(
      createElement(NoteArticle, { note, titleLevel: "h1" }),
    );
    expect(markup).toContain(
      "PolicyBench added Muse Wonder, its first Meta model, to the board on 2026-10-13, the day after Meta released it, bringing the board to 48 models.",
    );
    // Board rates keep one decimal.
    expect(markup).toContain("Muse Wonder gets 90.1% of answers right and ranks #10 of 48.");
    expect(markup).toContain(
      "On the bounded score, which gives partial credit for amounts close to the reference, it ranks #3, behind only GPT-6 Sol and Claude Opus 5.5.",
    );
    // After the bounded rank, the leader's rate names its metric.
    expect(markup).toContain(
      "GPT-6 Sol still leads at 95.2% of answers right, ahead of Claude Opus 5.5 (94.1%) and GPT-5.6 Sol (93.1%).",
    );
    expect(markup).toContain(closing);
    expect(markup).toContain("so Muse Wonder Full is not on the board");
    expect(markup).toContain(
      "Of the outputs the previous release excluded, nine return to scoring",
    );
    expect(markup).toContain(
      "that output stays excluded because the stated facts do not decide it",
    );
    expect(markup).toContain("from policyengine-us 2.38.6 to 2.41.0");
    expect(markup).toContain(
      "Every model is now scored on 1,935 of its 1,984 requested outputs; PolicyBench excludes the other 49.",
    );
    // Falls are not board rates, so they keep their two decimals; counts
    // under ten are words.
    expect(markup).toContain("falls, by 0.18 to 0.42 points");
    expect(markup).toContain(
      "half of them are answered within $1 by at most one of the 48 models, and four by none. Muse Wonder answers one of them within $1.",
    );
    expect(markup).toContain(
      "Without them, every earlier model would keep its share of answers right from the previous release.",
    );
    expect(markup).toContain('href="/model/muse-wonder"');
    expect(markup).toContain(
      'href="https://github.com/PolicyEngine/policybench/releases/tag/dashboard-data-20261013"',
    );
    expect(markup).not.toMatch(/\{[A-Za-z][A-Za-z0-9]*(?::words)?\}/);
  });

  test("the rewritten score sentences render", () => {
    const expected: Record<string, string[]> = {
      "2026-09-01-claude-fable-5-1-added": [
        "Anthropic released Claude Fable 5.1 on 2026-09-01, and PolicyBench added it to the board the same day and parsed 1,984 of the model&#x27;s 1,984 answers.",
        "Claude Fable 5.1 gets 86.3% of answers right and ranks #2 of 33.",
        closing,
      ],
      "2026-09-05-gpt-6-astra-debuts-second": [
        "GPT-6 Astra reached the API on 2026-09-04 and joined the board on 2026-09-05.",
        "It gets 88.0% of answers right and ranks #2 of 39, behind GPT-5.6 Sol (89.2%) and ahead of Claude Fable 5.1 (86.9%, #3).",
        "PolicyBench scores every model on 1,973 of its 1,984 requested outputs and excludes the other 11, since their references depend on an engine input the household facts never list.",
        closing,
      ],
      "2026-09-22-gpt-6-sol-debuts-first": [
        "GPT-6 Sol gets 94.2% of answers right, 1.3 points above Claude Opus 5.5 (92.9%, #2), and ranks #1 of 42. GPT-5.6 Sol, the previous leader, ranks #3 at 92.7%.",
        closing,
      ],
      "2026-09-29-claude-sonnet-5-5-debuts-fifth": [
        "Claude Sonnet 5.5 gets 92.1% of answers right and ranks #5 of 45.",
        "GPT-6 Luna, #4, also rounds to 92.1% and sits about level with Claude Sonnet 5.5, less than 0.02 points ahead.",
        closing,
        "Together, the new references and the Medicaid exclusion lift every one of the 42 earlier models, by 0.14 to 0.83 points.",
      ],
      "2026-10-06-policybench-stops-scoring-eight-tax-outputs": [
        "Every model&#x27;s share of answers right rises by 0.67 to 1.35 points.",
        `${closing} GPT-6 Sol still leads at 95.8%`,
      ],
      "2026-10-10-claude-haiku-5-5-joins-the-board": [
        "Claude Haiku 5.5 joined the board on 2026-10-10, bringing the board to 47 models. It gets 79.6% of answers right, 4.8 points above Claude Haiku 4.5 (74.8%, #43), and ranks #37 of 47.",
        closing,
        "Against the previous release, every one of the 46 earlier models falls, by 0.24 to 1.37 points.",
        "Without those outputs, every earlier model&#x27;s share of answers right would have risen, by 0.39 to 0.71 points.",
      ],
      "2026-10-13-muse-wonder-joins-the-board": [
        "Against the previous release, every one of the 47 earlier models falls, by 0.18 to 0.42 points.",
      ],
      "2026-10-20-given-a-policyengine-tool-three-models-score-above-99": [
        "With or without the tool, PolicyBench counts a dollar amount as right when it falls within $1 of the reference PolicyEngine computes, and an eligibility answer as right when it matches.",
      ],
      "2026-10-31-gpt-6-1-terra-joins-the-board": [
        "Only GPT-6 Sol (95.2%) and Claude Opus 5.5 (94.1%) score higher, and GPT-5.6 Sol, which also rounds to 93.1%, trails by less than a tenth of a point.",
      ],
    };
    for (const [slug, sentences] of Object.entries(expected)) {
      const note = notes.find((n) => n.slug === slug)!;
      const markup = renderToStaticMarkup(
        createElement(NoteArticle, { note, titleLevel: "h1" }),
      );
      for (const sentence of sentences) expect(markup).toContain(sentence);
    }
  });

  test("a words placeholder spells out whole numbers under ten", () => {
    // Any note serves as the template; its facts and paragraphs are replaced.
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
    const description = interpolateNoteText(note!, note!.paragraphs[0]);
    expect(description.length).toBeLessThan(600);
    expect(description).toEndWith(
      "Of the 230 answers PolicyBench requests for these households, 190 come to $0 and seven match the reference.",
    );
    expect(note!.paragraphs[1]).toStartWith(
      "PolicyBench grades answers against references from PolicyEngine",
    );
    expect(note!.paragraphs[1]).toContain(
      "USDA published the ${minimumFromOctober} minimum",
    );
    expect(note!.paragraphs[2]).toStartWith(
      "Each household qualifies only through broad-based categorical eligibility (BBCE).",
    );
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
      "The version of this note published September 23 counted the worker among its households.",
    );
    expect(markup).not.toContain("revised this note");
    expect(markup).not.toContain("updated this note");
    expect(markup).toContain(">policyengine-us #9586 (SNAP child support treatment)</a>");
    expect(markup).not.toContain("scenario_045");
    expect(markup).not.toMatch(/>scenario_\d+<\/a>/);
  });

  test("the BBCE note closes with the later release", () => {
    const note = notes.find(
      (entry) => entry.slug === "2026-10-05-five-snap-households-bbce",
    );
    const markup = renderToStaticMarkup(
      createElement(NoteArticle, { note: note!, titleLevel: "h1" }),
    );
    // Its numbers stay release dashboard-data-20260930's.
    expect(markup).toContain("GPT-5.6 Sol and GPT-6 Luna, #3 and #4 on PolicyBench");
    expect(markup).toContain(
      "A later release, dashboard-data-20261006, stops scoring eight tax outputs and changes no SNAP reference or answer. On it, GPT-6 Luna is #5 on PolicyBench, below Claude Sonnet 5.5, and every other figure in this note stays the same.",
    );
    expect(markup).toContain(
      'href="/notes/2026-10-06-policybench-stops-scoring-eight-tax-outputs"',
    );
    expect(markup).toContain(
      'href="https://github.com/PolicyEngine/policybench/releases/tag/dashboard-data-20261006"',
    );
  });

  test("the October 6 release note renders its figures", () => {
    const note = notes.find(
      (entry) =>
        entry.slug === "2026-10-06-policybench-stops-scoring-eight-tax-outputs",
    );
    expect(note).toBeDefined();
    expect(note!.date).toBe("2026-10-06");
    const description = interpolateNoteText(note!, note!.paragraphs[0]);
    expect(description.length).toBeLessThan(600);
    expect(description).toStartWith(
      "PolicyBench stops scoring eight tax outputs, in six households, whose references turn on facts the prompts never state.",
    );
    expect(description).toEndWith(
      "Every model is now scored on 1,920 of its 1,984 requested outputs, down from 1,928, and PolicyBench excludes 64.",
    );
    const markup = renderToStaticMarkup(
      createElement(NoteArticle, { note: note!, titleLevel: "h1" }),
    );
    // Cents stay as written.
    expect(markup).toContain(
      "the outputs are $11,895.23 in California, $26,991.31 in Massachusetts, and $11,137.31 in Virginia, against references of $11,113.57, $26,932.27, and $10,729.61.",
    );
    expect(markup).toContain("the standard Part B premium, $2,434.80 for 2026");
    expect(markup).toContain(
      "35 answers match the reference within $1: six for Minnesota, 16 for Colorado, nine for Massachusetts, and four for New York. Another 82 match",
    );
    // Rises are not board rates, so they keep their two decimals; board
    // rates keep one decimal, a whole one too.
    expect(markup).toContain("rises by 0.67 to 1.35 points");
    expect(markup).toContain("GPT-6 Sol still leads at 95.8%, ahead of Claude Opus 5.5 (95.1%)");
    expect(markup).toContain(
      "Claude Sonnet 5.5 (93.3%) passes GPT-6 Luna (93.0%) for fourth.",
    );
    expect(markup).toContain(
      "Inkling moves above Grok 4.7, Gemini 3 Flash Preview above Claude Opus 4.7, and Gemini 3.1 Flash Lite Preview above DeepSeek V4 Pro.",
    );
    expect(markup).toContain(
      "from June 12 to September 29, 2026, ending on the UTC date of the last answer",
    );
    expect(markup).toContain("California&#x27;s $230 monthly income disregard");
    expect(markup).toContain(
      'href="https://github.com/PolicyEngine/policybench/pull/173"',
    );
    expect(markup).toContain(
      'href="https://github.com/PolicyEngine/policybench/releases/tag/dashboard-data-20260930"',
    );
    expect(markup).toContain(">Virginia household</a>");
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
      "A later note, published October 5, corrects this one. From release dashboard-data-20260922c on, PolicyBench scores the SNAP amounts of four of these six households at $288 each, and scores a Michigan worker who pays child support at $0: PolicyEngine counts that child support in gross income, as Michigan does (policyengine-us #9586), and the worker does not qualify.",
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
