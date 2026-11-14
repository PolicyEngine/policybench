import { beforeAll, expect, test } from "bun:test";
import { Glob } from "bun";
import { fileURLToPath } from "node:url";
import { loadBindings, transform } from "next/dist/build/swc";
import ts from "typescript";

// Next 16.2's compiler (its own build of SWC) deletes whitespace that some JSX
// texts show at their start or end, so two words run together on the page. A
// JSX text is the run of characters between two tags or expressions. This
// test compiles every text under src/ with Next's compiler and with
// TypeScript's, which applies JSX's whitespace rules to the text as written,
// and fails wherever Next's output has no whitespace at a place TypeScript's
// has some. RULE_CASES below record the shapes the compiler mishandles, so a
// compiler upgrade that changes them fails here too. Among them:
//
// - A text that starts with spaces or tabs and holds a decoded entity and a
//   line break loses those spaces: `{count} answer the\n question&apos;s`
//   renders as "12answer the question's".
// - An encoded line break (&#10;) at the start or end of a text vanishes with
//   the whitespace around it.
// - An encoded space (&#32;) after a line break at the end of a text vanishes
//   too.
//
// Put a space the compiler would drop in an explicit {" "} instead.
const SRC = fileURLToPath(new URL("../src/", import.meta.url));

// Next's own build of SWC, with the automatic JSX runtime its build uses.
const SWC_OPTIONS = {
  jsc: {
    parser: { syntax: "typescript", tsx: true },
    transform: { react: { runtime: "automatic" } },
    target: "es2020",
  },
};

// Compiling and comparing every text takes well under a second, but Bun's
// default five-second limit leaves little room on a loaded machine.
const TIMEOUT_MS = 60_000;

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

// Lines the two renders up by their other characters. `sameText` says whether
// those characters agree; `dropsSpace` whether `next` has no whitespace at a
// place where `reads` has some.
function compare(reads: string, next: string) {
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
  return {
    sameText: actual.shown === expected.shown,
    dropsSpace: expected.gapBefore.some((gap, i) => gap && !actual.gapBefore[i]),
  };
}

// Each JSX text in a source file whose characters or whitespace Next's
// compiler renders differently from TypeScript's. A text's whitespace depends
// only on the text, so each one compiles alone, between two expressions.
async function droppedSpaces(path: string, source: string): Promise<string[]> {
  const file = ts.createSourceFile(
    path,
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const texts: ts.JsxText[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isJsxText(node)) texts.push(node);
    ts.forEachChild(node, visit);
  };
  visit(file);
  const found: string[] = [];
  for (const node of texts) {
    // getText() skips leading whitespace, which is the part that matters.
    const raw = file.text.slice(node.pos, node.end);
    const jsx = `<>{x}${raw}{y}</>`;
    const { sameText, dropsSpace } = compare(
      renderWithTypeScript(jsx),
      await renderWithNext(jsx),
    );
    if (!sameText || dropsSpace) {
      const { line } = file.getLineAndCharacterOfPosition(node.pos);
      const firstLine = raw.trim().split(/[\n\r\u2028\u2029]/)[0];
      const what = sameText ? "loses a space" : "renders other characters";
      found.push(`${path}:${line + 1}: ${what}: "${firstLine.trim()}"`);
    }
  }
  return found;
}

// [JSX, what Next's compiler renders, whether that drops a space]. The test
// compiles each case with Next's compiler and with TypeScript's.
const RULE_CASES: [string, string, boolean][] = [
  // Leading spaces, in the two shapes the site had; then no entity, one line,
  // and an explicit {" "}, which all keep the space.
  [
    "<><B /> on 100\n  households from PolicyEngine&rsquo;s data.\n</>",
    "<B />on 100 households from PolicyEngine\u2019s data.",
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
    "<B /> on PolicyEngine\u2019s data.",
    false,
  ],
  [
    '<><B />{" "}\n  on 100 households from PolicyEngine&rsquo;s data.\n</>',
    "<B /> on 100 households from PolicyEngine\u2019s data.",
    false,
  ],
  // A text that opens an element loses its space too.
  [
    "<>before<span> after\n one&apos;s</span></>",
    "before<span>after one's</span>",
    true,
  ],
  // Any line break counts: a lone CR, U+2028, or an encoded one. A vertical
  // tab is not a line break.
  ["<>{x} after\r one&apos;s</>", "{x}after one's", true],
  ["<>{x} after\u2028 one&apos;s</>", "{x}after one's", true],
  ["<>{x} one&#10;two</>", "{x}one two", true],
  ["<>{x} after\v one&apos;s</>", "{x} after\v one's", false],
  // An encoded space or &nbsp; at the start keeps the words apart.
  ["<>{x} &nbsp;after\n one&apos;s</>", "{x}\u00a0after one's", false],
  ["<>{x}&#32;after\n one&apos;s</>", "{x} after one's", false],
  // Whitespace that holds a literal line break goes in every compiler, as JSX
  // intends, so the source shows no space there to lose.
  ["<>{x} \n  it&apos;s</>", "{x}it's", false],
  ["<>{x}\n  the company&apos;s {y}</>", "{x}the company's {y}", false],
  // An encoded line break at either end vanishes with the whitespace around
  // it, unless an encoded space is there too. Inside a text it becomes a
  // space, which loses nothing on the page.
  ["<>{x}&#10;word\n next</>", "{x}word next", true],
  ["<>{x}&#10;word</>", "{x}word", true],
  ["<>{x}\n  word&#10;{y}</>", "{x}word{y}", true],
  ["<>{x}&#10;&#32;word</>", "{x} word", false],
  ["<>{x}\n  one&#10;two\n</>", "{x}one two", false],
  // An encoded space after a line break at the end of a text vanishes.
  ["<>{x}a&apos;\n&#32;{y}</>", "{x}a'{y}", true],
  ["<>{x}a&apos;\n&#x20;{y}</>", "{x}a'{y}", true],
  // Only an entity the compiler decodes counts: a name JSX lacks, or a JSX
  // name in other capitals, stays as written and the space stays too.
  [
    "<>{x} after\n one&notAnEntity;s</>",
    "{x} after one&notAnEntity;s",
    false,
  ],
  ["<>{x} after\n one&APOS;s</>", "{x} after one&APOS;s", false],
  ["<>{x} after\n AT&amp;T</>", "{x}after AT&T", true],
  ["<>{x} after\n one&#39;s</>", "{x}after one's", true],
  ["<>{x} after\n one&#x27;s</>", "{x}after one's", true],
];

test(
  "the guard flags exactly the cases whose space the compiler drops",
  async () => {
    const compiled: [string, string, boolean][] = [];
    const flagged: [string, boolean][] = [];
    for (const [jsx] of RULE_CASES) {
      const next = await renderWithNext(jsx);
      const { sameText, dropsSpace } = compare(renderWithTypeScript(jsx), next);
      expect([jsx, sameText]).toEqual([jsx, true]);
      compiled.push([jsx, next, dropsSpace]);
      const found = await droppedSpaces("case.tsx", `const a = ${jsx};`);
      flagged.push([jsx, found.length > 0]);
    }
    expect(compiled).toEqual(RULE_CASES);
    expect(flagged).toEqual(RULE_CASES.map(([jsx, , drops]) => [jsx, drops]));
  },
  TIMEOUT_MS,
);

test(
  "no page text loses a space in the production build",
  async () => {
    const found: string[] = [];
    let files = 0;
    for await (const rel of new Glob("**/*.tsx").scan(SRC)) {
      files += 1;
      found.push(...(await droppedSpaces(rel, await Bun.file(SRC + rel).text())));
    }
    expect(files).toBeGreaterThan(20);
    expect(found).toEqual([]);
  },
  TIMEOUT_MS,
);

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

test(
  "Next's compiler emits the five spaces the site lost",
  async () => {
    const spaced: [string, boolean[]][] = [];
    for (const [file, before, words] of FIXED_SPACES) {
      const { code } = await transform(await Bun.file(SRC + file).text(), SWC_OPTIONS);
      spaced.push([words, textsAfter(code, before, words).map((text) => /^\s/.test(text))]);
    }
    expect(spaced).toEqual(FIXED_SPACES.map(([, , words]) => [words, [true]]));
  },
  TIMEOUT_MS,
);
