import { beforeAll, expect, test } from "bun:test";
import { Glob } from "bun";
import { loadBindings, transform } from "next/dist/build/swc";
import ts from "typescript";

// Next 16.2's compiler drops the leading space of a JSX text that spans more
// than one line and contains an HTML entity (&apos;, &rsquo;, ...). So
// `{count} answer the\n  question&apos;s` renders as "12answer the question's".
// The same text on one line, or a multi-line text without an entity, keeps its
// space. Put that space in an explicit {" "} after the element or expression.
const ENTITY = /&(#\d+|#x[0-9a-f]+|[a-z][a-z0-9]*);/i;
const SRC = new URL("../src/", import.meta.url).pathname;

function droppedSpaces(path: string, source: string): string[] {
  const file = ts.createSourceFile(
    path,
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const found: string[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isJsxText(node)) {
      // getText() skips leading whitespace, which is the part that matters.
      const raw = file.text.slice(node.pos, node.end);
      const firstLine = raw.split(/\r?\n/)[0];
      const siblings = Array.from(
        (node.parent as ts.JsxElement | ts.JsxFragment).children,
      );
      const previous = siblings[siblings.indexOf(node) - 1];
      if (
        previous &&
        raw.includes("\n") &&
        ENTITY.test(raw) &&
        /^[ \t]+\S/.test(firstLine)
      ) {
        const { line } = file.getLineAndCharacterOfPosition(node.pos);
        found.push(`${path}:${line + 1}: "${firstLine.trim()}"`);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return found;
}

// Next's own build of SWC, with the automatic JSX runtime its build uses.
const SWC_OPTIONS = {
  jsc: {
    parser: { syntax: "typescript", tsx: true },
    transform: { react: { runtime: "automatic" } },
    target: "es2020",
  },
};

beforeAll(async () => {
  // Otherwise loadBindings looks for an npm package-lock.json to patch.
  process.env.NEXT_IGNORE_INCORRECT_LOCKFILE = "1";
  await loadBindings();
});

type Child = string | number | boolean | null | undefined | Element | Child[];
interface Element {
  type: unknown;
  props: { children?: Child };
}
const FRAGMENT = Symbol("Fragment");
const createElement = (type: unknown, props: Element["props"]): Element => ({
  type,
  props,
});
const RUNTIME = { Fragment: FRAGMENT, jsx: createElement, jsxs: createElement };
function B() {
  return null;
}

// Runs the CommonJS a compiler made from `export const a = <case>;`, with the
// expressions x and y standing for the strings "{x}" and "{y}", and returns a.
function evaluate(code: string): Child {
  const exports: { a?: Child } = {};
  new Function("require", "exports", "x", "y", "B", code)(
    () => RUNTIME,
    exports,
    "{x}",
    "{y}",
    B,
  );
  return exports.a;
}

// What a case shows on the page: its strings, with HTML tags around elements
// and <B /> for the component.
function render(node: Child): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (Array.isArray(node)) return node.map(render).join("");
  if (typeof node !== "object") return String(node);
  const inner = render(node.props.children);
  if (node.type === FRAGMENT) return inner;
  if (typeof node.type === "string") return `<${node.type}>${inner}</${node.type}>`;
  return "<B />";
}

async function renderWithNext(jsx: string): Promise<string> {
  const { code } = await transform(`export const a = ${jsx};`, {
    ...SWC_OPTIONS,
    module: { type: "commonjs" },
  });
  return render(evaluate(code));
}

// TypeScript's JSX emit applies JSX's whitespace rules to the source as
// written and decodes each entity afterwards, so it reads a text the way its
// author wrote it. It is the reference the compiler is held to.
function renderWithTypeScript(jsx: string): string {
  const { outputText } = ts.transpileModule(`export const a = ${jsx};`, {
    fileName: "case.tsx",
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  });
  return render(evaluate(outputText));
}

// Whether `next` has no whitespace at a place where `reads` has some, lining
// the two up by their other characters.
function dropsSpace(reads: string, next: string): boolean {
  const gaps = (text: string) => {
    const shown: string[] = [];
    const gapBefore: boolean[] = [];
    let gap = false;
    for (const char of text) {
      if (/\s/.test(char)) {
        gap = true;
      } else {
        shown.push(char);
        gapBefore.push(gap);
        gap = false;
      }
    }
    gapBefore.push(gap);
    return { shown: shown.join(""), gapBefore };
  };
  const expected = gaps(reads);
  const actual = gaps(next);
  expect(actual.shown).toBe(expected.shown);
  return expected.gapBefore.some((gap, i) => gap && !actual.gapBefore[i]);
}

// [JSX, what Next's compiler renders, whether that drops a space]. The test
// compiles each case with Next's compiler and with TypeScript's.
const RULE_CASES: [string, string, boolean][] = [
  [
    "<><B /> on 100\n  households from PolicyEngine&rsquo;s data.\n</>",
    "<B />on 100 households from PolicyEngine’s data.",
    true,
  ],
  [
    "<>{x} reject forced calls, so\n  Fable 5.1&apos;s marker.\n</>",
    "{x}reject forced calls, so Fable 5.1's marker.",
    true,
  ],
  ["<><B /> on 100\n  real households.\n</>", "<B /> on 100 real households.", false],
  [
    "<><B /> on PolicyEngine&rsquo;s data.</>",
    "<B /> on PolicyEngine’s data.",
    false,
  ],
  [
    '<><B />{" "}\n  on 100 households from PolicyEngine&rsquo;s data.\n</>',
    "<B /> on 100 households from PolicyEngine’s data.",
    false,
  ],
];

test("the rule flags exactly the cases whose space the compiler drops", async () => {
  const compiled: [string, string, boolean][] = [];
  const flagged: [string, boolean][] = [];
  for (const [jsx] of RULE_CASES) {
    const next = await renderWithNext(jsx);
    compiled.push([jsx, next, dropsSpace(renderWithTypeScript(jsx), next)]);
    flagged.push([jsx, droppedSpaces("case.tsx", `const a = ${jsx};`).length > 0]);
  }
  expect(compiled).toEqual(RULE_CASES);
  expect(flagged).toEqual(RULE_CASES.map(([jsx, , drops]) => [jsx, drops]));
});

test("no page text loses its leading space in the production build", async () => {
  const found: string[] = [];
  let files = 0;
  for await (const rel of new Glob("**/*.tsx").scan(SRC)) {
    files += 1;
    found.push(...droppedSpaces(rel, await Bun.file(SRC + rel).text()));
  }
  expect(files).toBeGreaterThan(20);
  expect(found).toEqual([]);
});

// The texts that follow, in the compiled code, the array child containing
// `before` and that start with `words` once leading whitespace is set aside.
// Each text joins the string children up to the next child of another kind.
function textsAfter(code: string, before: string, words: string): string[] {
  const file = ts.createSourceFile(
    "compiled.js",
    code,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.JS,
  );
  const found: string[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isArrayLiteralExpression(node)) {
      const items = node.elements;
      items.forEach((item, index) => {
        if (!item.getText(file).includes(before)) return;
        let text = "";
        for (let next = index + 1; next < items.length; next += 1) {
          const child = items[next];
          if (!ts.isStringLiteral(child)) break;
          text += child.text;
        }
        if (text.trimStart().startsWith(words)) found.push(text);
      });
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return found;
}

// The five places policybench.org ran two words together until each space
// moved into an explicit {" "}: the file, a piece of the compiled child before
// the space, and the words after it.
const FIXED_SPACES: [string, string, string][] = [
  ["components/ExpandCoverageCopy.tsx", 'context: "frontier"', "on 100 households"],
  ["components/ModelLeaderboard.tsx", "forcedToolRejectingClaudeLabels", "reject forced calls"],
  ["components/Methodology.tsx", "chunkedRowsPhrase", "answer the same facts"],
  ["components/Methodology.tsx", "max(0, 1", "when the reference is nonzero"],
  ["components/Methodology.tsx", "annotatedExactMissCount", "of the snapshot"],
];

test("Next's compiler emits the five spaces the site lost", async () => {
  const spaced: [string, boolean[]][] = [];
  for (const [file, before, words] of FIXED_SPACES) {
    const { code } = await transform(await Bun.file(SRC + file).text(), SWC_OPTIONS);
    spaced.push([words, textsAfter(code, before, words).map((text) => /^\s/.test(text))]);
  }
  expect(spaced).toEqual(FIXED_SPACES.map(([, , words]) => [words, [true]]));
});
