import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import JudgeTextCorrections from "../src/components/JudgeTextCorrections";
import { DetailContent } from "../src/components/ScenarioExplorer";
import artifact from "../src/data.artifact.json";
import registryJson from "../src/data.versions.json";
import {
  isLivePointerRef,
  parseDataVersionRegistry,
} from "../src/lib/dataVersions";
import type { ExplanationsFile } from "../src/lib/explanations";
import {
  AUDIT_JUDGE_MODELS,
  JUDGE_TEXT_ERRATA,
  JUDGE_TEXT_ERRATA_URL,
  PARSE_FAILURE_NOTE,
  auditJudgeNames,
  caseNoteErrata,
  judgeTextErrataForCell,
  rowErrata,
  rowSpan,
  type JudgeTextErratum,
} from "../src/lib/judgeTextErrata";
import { MODEL_LABELS } from "../src/modelMeta";
import type { ScenarioPrediction } from "../src/types";

const entries = JUDGE_TEXT_ERRATA.entries;

const page = readFileSync(
  new URL("../../docs/fable52/judge_text_errata.md", import.meta.url),
  "utf8",
);

type PageEntry = {
  heading: string;
  where: string;
  text?: string;
  correction?: string;
  source?: string;
  scoring?: string;
};

function parsePage(markdown: string): PageEntry[] {
  const [, body] = markdown.split("\n## Entries\n\n");
  const parsed: PageEntry[] = [];
  let heading = "";
  for (const line of body.split("\n")) {
    const cell = line.match(/^### `(.+)`$/);
    if (cell) {
      heading = cell[1];
      continue;
    }
    const where = line.match(/^- \*\*Where:\*\* (.*)$/);
    if (where) {
      parsed.push({ heading, where: where[1] });
      continue;
    }
    const field = line.match(/^ {2}- \*\*(Text|Correction|Source|Scoring):\*\* (.*)$/);
    if (field) {
      const key = field[1].toLowerCase() as
        | "text"
        | "correction"
        | "source"
        | "scoring";
      parsed[parsed.length - 1][key] = field[2];
    }
  }
  return parsed;
}

/** The app ids a "where" names, split independently of the generator. */
function namedModels(where: string): string[] {
  const idByLabel = new Map(
    Object.entries(MODEL_LABELS).map(([id, label]) => [label, id]),
  );
  const ids: string[] = [];
  for (const part of where.split(";").map((p) => p.trim())) {
    const rows = part.match(/^rows? for (.*)$/);
    if (!rows) continue;
    const names = rows[1].split(/, | and /);
    for (const name of names) {
      const id = idByLabel.get(name);
      if (!id) throw new Error(`no board model is labelled ${name}`);
      ids.push(id);
    }
  }
  return ids;
}

/** RFC 4180 rows (quoted fields may hold commas, quotes and newlines). */
function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') {
        quoted = false;
      } else {
        field += c;
      }
    } else if (c === '"') {
      quoted = true;
    } else if (c === ",") {
      row.push(field);
      field = "";
    } else if (c === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (c !== "\r") {
      field += c;
    }
  }
  if (field || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

// The text sidecar prepare-data writes for the live board: the case notes
// and row sentences the scenario explorer shows.
const explanations = JSON.parse(
  readFileSync(
    new URL("../public/data/explanations-us.json", import.meta.url),
    "utf8",
  ),
) as ExplanationsFile;

function cellTexts(entry: { scenarioId: string; variable: string }) {
  const models =
    explanations.scenarios[entry.scenarioId]?.[entry.variable]?.models ?? {};
  return models;
}

function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#x27;");
}

/** Markup with React's text-node separators removed. */
function flat(html: string): string {
  return html.replaceAll("<!-- -->", "");
}

function countCorrections(html: string): number {
  return html.split('data-testid="judge-text-correction"').length - 1;
}

describe("judge-text errata data", () => {
  test("the JSON holds the errata page's entries, in the page's order", () => {
    const pageEntries = parsePage(page);
    expect(pageEntries).toHaveLength(105);
    expect(entries).toHaveLength(105);
    expect(new Set(entries.map((entry) => entry.cell)).size).toBe(31);
    expect(new Set(pageEntries.map((entry) => entry.heading)).size).toBe(31);
    entries.forEach((entry, index) => {
      const onPage = pageEntries[index];
      expect(entry.cell).toBe(`us__${entry.scenarioId}__${entry.variable}`);
      expect(onPage).toEqual({
        heading: `${entry.scenarioId} ${entry.variable}`,
        where: entry.where,
        text: entry.text,
        correction: entry.correction,
        source: entry.source,
        scoring: entry.scoring,
      });
      expect(page).toContain(`  - **Text:** ${entry.text}\n`);
    });
  });

  test("is for the release the live board shows", () => {
    expect(page.split("\n")[0]).toBe(
      `# Errata for the judge's texts in release ${JUDGE_TEXT_ERRATA.release}`,
    );
    expect(artifact.tag).toBe(JUDGE_TEXT_ERRATA.release);
    const registry = parseDataVersionRegistry(registryJson);
    const live = registry.versions.find((v) => v.id === registry.default);
    expect(live && isLivePointerRef(live.artifact)).toBe(true);
  });

  test("each entry's models are the rows its where names", () => {
    for (const entry of entries) {
      expect(entry.unresolvedRows).toEqual([]);
      expect(entry.models).toEqual(namedModels(entry.where));
      expect(entry.caseNote).toBe(/(^|; )case note($|;)/.test(entry.where));
      expect(entry.referenceHypothesis).toBe(
        entry.where === "case note (reference hypothesis)",
      );
      expect(
        entry.caseNote || entry.referenceHypothesis || entry.models.length > 0,
      ).toBe(true);
      expect(entry.text.startsWith(`"${entry.span}"`)).toBe(true);
      for (const [model, span] of Object.entries(entry.rowSpans)) {
        expect(entry.models).toContain(model);
        expect(entry.text).toContain(`"${span}"`);
      }
    }
  });

  test("every quoted span occurs in the frozen text the app shows for its cell and place", () => {
    const hypotheses = new Map<string, string>();
    const [header, ...rows] = parseCsv(
      readFileSync(
        new URL(
          "../../annotations/us_full_run_20260612_policyengine_4_16_1_populace/us_case_notes.csv",
          import.meta.url,
        ),
        "utf8",
      ),
    );
    const at = (name: string) => header.indexOf(name);
    for (const row of rows) {
      if (row.length < header.length) continue;
      hypotheses.set(
        `${row[at("scenario_id")]}|${row[at("variable")]}`,
        row[at("reference_bug_hypothesis")],
      );
    }

    let checks = 0;
    for (const entry of entries) {
      const texts = cellTexts(entry);
      for (const model of entry.models) {
        expect(texts[model]?.annotation ?? "").toContain(rowSpan(entry, model));
        checks++;
      }
      if (entry.caseNote) {
        const notes = new Set(
          Object.values(texts)
            .map((t) => t.caseAnnotation)
            .filter((note): note is string => !!note),
        );
        expect(notes.size).toBe(1);
        expect([...notes][0]).toContain(entry.span);
        checks++;
      }
      if (entry.referenceHypothesis) {
        // The app does not show this field; the frozen case-note file holds it.
        expect(
          hypotheses.get(`${entry.scenarioId}|${entry.variable}`) ?? "",
        ).toContain(entry.span);
        checks++;
      }
    }
    expect(checks).toBe(481 + 22 + 2);
  });

  test("the row lookup finds exactly the rows each entry names, across every row of those cells", () => {
    const expected = new Set<string>();
    for (const entry of entries) {
      for (const model of entry.models) {
        expected.add(`${entry.cell}|${model}|${entries.indexOf(entry)}`);
      }
    }
    const found = new Set<string>();
    for (const cell of new Set(entries.map((entry) => entry.cell))) {
      const sample = entries.find((entry) => entry.cell === cell)!;
      const cellEntries = judgeTextErrataForCell(
        sample.scenarioId,
        sample.variable,
        "1.1",
        "1.1",
      );
      for (const [model, texts] of Object.entries(cellTexts(sample))) {
        for (const entry of rowErrata(cellEntries, model, texts.annotation)) {
          found.add(`${cell}|${model}|${entries.indexOf(entry)}`);
        }
      }
    }
    expect(found.size).toBe(481);
    expect([...found].sort()).toEqual([...expected].sort());
  });

  test("names the judge models the frozen manifest records", () => {
    const manifest = JSON.parse(
      readFileSync(
        new URL("../../paper/snapshot/20260501/manifest.json", import.meta.url),
        "utf8",
      ),
    ) as {
      audit_annotation_artifacts: {
        judge_provenance: { by_judge: Record<string, unknown> };
      };
    };
    const judges = Object.keys(
      manifest.audit_annotation_artifacts.judge_provenance.by_judge,
    ).map((id) => id.replace(/-(\d)-(\d)$/, "-$1.$2"));
    expect([...AUDIT_JUDGE_MODELS].sort()).toEqual(judges.sort());
    expect(auditJudgeNames()).toBe("GPT-5.6 Sol, Claude Opus 5 or Claude Opus 5.5");
  });
});

function entryFor(cell: string, where: string): JudgeTextErratum {
  const entry = entries.find((e) => e.cell === cell && e.where === where);
  if (!entry) throw new Error(`no erratum for ${cell} at ${where}`);
  return entry;
}

function row(
  scenarioId: string,
  variable: string,
  model: string,
): ScenarioPrediction {
  const texts = explanations.scenarios[scenarioId][variable].models![model];
  return {
    prediction: 1000,
    error: 500,
    groundTruth: 500,
    exact: 0,
    failureSource: "llm_error",
    annotation: texts.annotation,
    caseAnnotation: texts.caseAnnotation,
  };
}

function renderRow(
  scenarioId: string,
  variable: string,
  model: string,
  {
    versionId = "1.1",
    pred = row(scenarioId, variable, model),
  }: { versionId?: string; pred?: ScenarioPrediction } = {},
): string {
  return flat(renderToStaticMarkup(
    createElement(DetailContent, {
      selectedCell: { variable, model },
      errata: judgeTextErrataForCell(scenarioId, variable, versionId, "1.1"),
      predictions: { [variable]: { [model]: pred } },
      country: "us",
      currencySymbol: "$",
      explanationsStatus: "ready",
      versionId,
      liveVersionId: "1.1",
      onClose: () => {},
    }),
  ));
}

describe("corrections beside the judge's texts", () => {
  const federal = "federal_income_tax_before_refundable_credits";

  test("a row erratum shows under that model's sentence, which stays as published", () => {
    const entry = entryFor(
      `us__scenario_000__${federal}`,
      "row for Gemini 3.5 Flash",
    );
    const pred = row("scenario_000", federal, "gemini-3.5-flash");
    const html = renderRow("scenario_000", federal, "gemini-3.5-flash");

    expect(countCorrections(html)).toBe(1);
    expect(html).toContain("Correction from PolicyBench");
    expect(html).toContain(escapeHtml(entry.correction));
    expect(html).toContain(`On “${escapeHtml(entry.span)}”:`);
    expect(html).toContain(`href="${JUDGE_TEXT_ERRATA_URL}"`);
    expect(html).toContain(">Errata<");
    // The judge's sentence is shown whole, ahead of the correction.
    const sentence = html.indexOf(escapeHtml(pred.annotation!));
    expect(sentence).toBeGreaterThan(-1);
    expect(sentence).toBeLessThan(html.indexOf("Correction from PolicyBench"));
  });

  test("a row the cell's errata do not name gets no correction", () => {
    const html = renderRow("scenario_000", federal, "claude-fable-5");
    expect(row("scenario_000", federal, "claude-fable-5").annotation).toBeTruthy();
    expect(countCorrections(html)).toBe(0);
    expect(html).not.toContain("Correction from PolicyBench");
  });

  test("a row with several errata shows each, with the span it corrects", () => {
    const cell = "us__scenario_032__state_refundable_credits";
    const named = entries.filter(
      (e) => e.cell === cell && e.models.includes("claude-fable-5.2"),
    );
    expect(named.length).toBeGreaterThan(1);
    const html = renderRow(
      "scenario_032",
      "state_refundable_credits",
      "claude-fable-5.2",
    );
    expect(countCorrections(html)).toBe(named.length);
    for (const entry of named) {
      expect(html).toContain(escapeHtml(entry.correction));
    }
  });

  test("a case-note erratum renders under the case note it corrects", () => {
    const cell = "us__scenario_032__state_refundable_credits";
    const cellEntries = judgeTextErrataForCell(
      "scenario_032",
      "state_refundable_credits",
      "1.1",
      "1.1",
    );
    const note = row(
      "scenario_032",
      "state_refundable_credits",
      "claude-fable-5.2",
    ).caseAnnotation;
    const onNote = caseNoteErrata(cellEntries, note);
    expect(onNote).toEqual(
      entries.filter((e) => e.cell === cell && e.caseNote),
    );
    expect(onNote).toHaveLength(2);
    const html = flat(
      renderToStaticMarkup(
        createElement(JudgeTextCorrections, { errata: onNote }),
      ),
    );
    expect(countCorrections(html)).toBe(2);
    for (const entry of onNote) {
      expect(html).toContain(`On “${escapeHtml(entry.span)}”:`);
      expect(html).toContain(escapeHtml(entry.correction));
    }
    // A note without the quoted text, and a row sentence, take none.
    expect(caseNoteErrata(cellEntries, "Some other note.")).toEqual([]);
    expect(
      caseNoteErrata(
        cellEntries.filter((e) => !e.caseNote),
        note,
      ),
    ).toEqual([]);
  });

  test("the prediction dialog shows no case-note correction, because it shows no case note", () => {
    // scenario_022's case note has an erratum; Claude Opus 5's row has none.
    const cell = `us__scenario_022__${federal}`;
    expect(entries.some((e) => e.cell === cell && e.caseNote)).toBe(true);
    expect(
      entries.some((e) => e.cell === cell && e.models.includes("claude-opus-5")),
    ).toBe(false);
    const html = renderRow("scenario_022", federal, "claude-opus-5");
    expect(countCorrections(html)).toBe(0);
  });

  test("no correction attaches to a row sentence that lacks the quoted text", () => {
    const pred = {
      ...row("scenario_000", federal, "gemini-3.5-flash"),
      annotation: "A different sentence.",
    };
    expect(
      countCorrections(
        renderRow("scenario_000", federal, "gemini-3.5-flash", { pred }),
      ),
    ).toBe(0);
  });

  test("an archived board gets no corrections and no judge line", () => {
    expect(
      judgeTextErrataForCell("scenario_000", federal, "1.0", "1.1"),
    ).toEqual([]);
    const html = renderRow("scenario_000", federal, "gemini-3.5-flash", {
      versionId: "1.0",
    });
    expect(countCorrections(html)).toBe(0);
    expect(html).not.toContain('data-testid="judge-note-disclosure"');
  });

  test("a judge's note carries the line that a judge model wrote it", () => {
    const html = renderRow("scenario_000", federal, "claude-fable-5");
    expect(html).toContain('data-testid="judge-note-disclosure"');
    expect(html).toContain(
      "A judge model (GPT-5.6 Sol, Claude Opus 5 or Claude Opus 5.5) wrote this note after scoring, and PolicyBench has checked only some of these notes; the ",
    );
    expect(html).toContain(
      `<a href="${JUDGE_TEXT_ERRATA_URL}" class="underline underline-offset-2 hover:text-text">errata</a> list the statements it found wrong.`,
    );
  });

  test("the fixed note for unparseable answers carries no judge line", () => {
    const pred = {
      ...row("scenario_000", federal, "claude-fable-5"),
      annotation: PARSE_FAILURE_NOTE,
    };
    const html = renderRow("scenario_000", federal, "claude-fable-5", { pred });
    expect(html).toContain(PARSE_FAILURE_NOTE);
    expect(html).not.toContain('data-testid="judge-note-disclosure"');
  });
});
