import { beforeAll, expect, test } from "bun:test";
import { Glob } from "bun";
import { loadBindings, transform } from "next/dist/build/swc";
import ts from "typescript";

// Next 16.2's compiler drops the leading space of a JSX text that spans more
// than one line and contains an entity the compiler decodes (&apos;, &rsquo;,
// &#39;, ...). So `{count} answer the\n  question&apos;s` renders as
// "12answer the question's". The same text on one line, a multi-line text
// without an entity, or one whose only &name; is not a JSX entity, keeps its
// space. Put that space in an explicit {" "} after the element or expression.
const SRC = new URL("../src/", import.meta.url).pathname;

// The 253 names in TypeScript's JSX entity table. Of 2,425 candidate names
// (these, the HTML5 names and case variants of these), Next 16.2.6's compiler
// decodes exactly these, case-sensitively, and leaves any other &name; as
// written.
const JSX_ENTITY_NAMES = new Set(
  (
    "AElig Aacute Acirc Agrave Alpha Aring Atilde Auml Beta Ccedil Chi " +
    "Dagger Delta ETH Eacute Ecirc Egrave Epsilon Eta Euml Gamma Iacute " +
    "Icirc Igrave Iota Iuml Kappa Lambda Mu Ntilde Nu OElig Oacute Ocirc " +
    "Ograve Omega Omicron Oslash Otilde Ouml Phi Pi Prime Psi Rho Scaron " +
    "Sigma THORN Tau Theta Uacute Ucirc Ugrave Upsilon Uuml Xi Yacute Yuml " +
    "Zeta aacute acirc acute aelig agrave alefsym alpha amp and ang apos " +
    "aring asymp atilde auml bdquo beta brvbar bull cap ccedil cedil cent " +
    "chi circ clubs cong copy crarr cup curren dArr dagger darr deg delta " +
    "diams divide eacute ecirc egrave empty emsp ensp epsilon equiv eta " +
    "eth euml euro exist fnof forall frac12 frac14 frac34 frasl gamma ge " +
    "gt hArr harr hearts hellip iacute icirc iexcl igrave image infin int " +
    "iota iquest isin iuml kappa lArr lambda lang laquo larr lceil ldquo " +
    "le lfloor lowast loz lrm lsaquo lsquo lt macr mdash micro middot " +
    "minus mu nabla nbsp ndash ne ni not notin nsub ntilde nu oacute ocirc " +
    "oelig ograve oline omega omicron oplus or ordf ordm oslash otilde " +
    "otimes ouml para part permil perp phi pi piv plusmn pound prime prod " +
    "prop psi quot rArr radic rang raquo rarr rceil rdquo real reg rfloor " +
    "rho rlm rsaquo rsquo sbquo scaron sdot sect shy sigma sigmaf sim " +
    "spades sub sube sum sup sup1 sup2 sup3 supe szlig tau there4 theta " +
    "thetasym thinsp thorn tilde times trade uArr uacute uarr ucirc ugrave " +
    "uml upsih upsilon uuml weierp xi yacute yen yuml zeta zwj zwnj"
  ).split(" "),
);
// A reference the compiler decodes: &# with decimal digits or &#x (lowercase
// x) with hex digits, at most nine characters between & and ;, or a JSX name.
const REFERENCE = /&(?:#\d{1,8}|#x[\da-fA-F]{1,7}|([A-Za-z][A-Za-z\d]*));/g;

function decodesEntity(raw: string): boolean {
  for (const [, name] of raw.matchAll(REFERENCE)) {
    if (name === undefined || JSX_ENTITY_NAMES.has(name)) return true;
  }
  return false;
}

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
        decodesEntity(raw) &&
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

test("the rule reads as entities exactly the references the compiler decodes", async () => {
  const references = [
    ...Array.from(JSX_ENTITY_NAMES, (name) => `&${name};`),
    // Names JSX lacks (HTML5 has some), JSX names in other capitals, a name
    // without its semicolon, and numeric references around the length limit.
    "&notAnEntity;",
    "&APOS;",
    "&Amp;",
    "&AMP;",
    "&NewLine;",
    "&Tab;",
    "&nbsp",
    "&#0;",
    "&#39;",
    "&#00000039;",
    "&#000000039;",
    "&#x27;",
    "&#x2A;",
    "&#x0000027;",
    "&#x00000027;",
    "&#X27;",
  ];
  const disagreements: string[] = [];
  for (const reference of references) {
    const rendered = await renderWithNext(`<>a${reference}b</>`);
    const compilerDecodes = rendered !== `a${reference}b`;
    if (compilerDecodes !== decodesEntity(reference)) disagreements.push(reference);
  }
  expect(disagreements).toEqual([]);
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
