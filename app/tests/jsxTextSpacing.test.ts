import { beforeAll, expect, test } from "bun:test";
import { Glob } from "bun";
import { loadBindings, transform } from "next/dist/build/swc";
import ts from "typescript";

// Next 16.2's compiler (its own build of SWC) deletes whitespace that some JSX
// texts show at their start or end, so two words run together on the page. A
// JSX text is the run of characters between two tags or expressions. This
// test fails on any text under src/ where that happens, by this rule, which
// the cases below check against the compiler:
//
// 1. A text that starts with spaces or tabs followed directly by something
//    other than whitespace loses those spaces and tabs if it also contains an
//    entity the compiler decodes and a line break: a literal LF, CR, U+2028 or
//    U+2029, or an encoded one such as &#10;. So `{count} answer the\n
//    question&apos;s` renders as "12answer the question's". The same text on
//    one line, or with no decoded entity, keeps its space.
// 2. The compiler reads an encoded line break (&#10;, &#13;, &#8232; or
//    &#8233;, in decimal or hex) as a line break in the source. When one sits
//    in the whitespace at the start or end of a text, it vanishes together
//    with the spaces, tabs and line breaks around it, so `{x}&#10;word`
//    renders as "{x}word". TypeScript and Bun keep the character.
//
// Neither happens when that whitespace also holds a character the compiler
// keeps: an encoded space such as &#32; or &nbsp;, or a literal whitespace
// character other than a space, tab or line break. Whitespace inside a text
// survives, though the compiler turns an encoded line break there into a
// space. The compiler decodes the 253 names in JSX_ENTITY_NAMES, &# with
// decimal digits and &#x (lowercase x) with hex digits, with at most nine
// characters between & and ;. It leaves any other &name; as written.
//
// Put a space the compiler would drop in an explicit {" "} instead.
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
// The JSX names whose character is whitespace.
const WHITESPACE_ENTITY_NAMES = new Set(["emsp", "ensp", "nbsp", "thinsp"]);
// A reference the compiler decodes: &# with decimal digits or &#x (lowercase
// x) with hex digits, at most nine characters between & and ;, or a JSX name.
const REFERENCE = /&(?:#(\d{1,8})|#x([\da-fA-F]{1,7})|([A-Za-z][A-Za-z\d]*));/y;
const LINE_BREAKS = "\n\r\u2028\u2029";

// One character of a JSX text as the compiler reads it. The compiler splits a
// text at line breaks and trims the spaces and tabs ("blank") next to them; it
// never trims other ("kept") whitespace. `encoded` marks a decoded entity.
interface Unit {
  kind: "visible" | "kept" | "blank" | "break";
  encoded: boolean;
}

function unit(char: string, encoded: boolean): Unit {
  if (LINE_BREAKS.includes(char)) return { kind: "break", encoded };
  if (!encoded && (char === " " || char === "\t")) return { kind: "blank", encoded };
  return { kind: /\s/.test(char) ? "kept" : "visible", encoded };
}

// The unit for the reference at `match`, or null when the compiler leaves it
// as written.
function referenceUnit([, decimal, hex, name]: RegExpExecArray): Unit | null {
  if (name !== undefined) {
    if (!JSX_ENTITY_NAMES.has(name)) return null;
    return { kind: WHITESPACE_ENTITY_NAMES.has(name) ? "kept" : "visible", encoded: true };
  }
  const code = decimal !== undefined ? Number(decimal) : parseInt(hex, 16);
  // The compiler fails the build on a reference past U+10FFFF.
  if (code > 0x10ffff) return { kind: "visible", encoded: true };
  return unit(String.fromCodePoint(code), true);
}

function readText(raw: string): Unit[] {
  const units: Unit[] = [];
  for (let i = 0; i < raw.length; ) {
    REFERENCE.lastIndex = i;
    const match = raw[i] === "&" ? REFERENCE.exec(raw) : null;
    const decoded = match && referenceUnit(match);
    if (match && decoded) {
      units.push(decoded);
      i += match[0].length;
    } else {
      units.push(unit(raw[i], false));
      i += 1;
    }
  }
  return units;
}

// Whether the compiler deletes whitespace at the start or end of this text.
function losesWhitespace(raw: string): boolean {
  const units = readText(raw);
  const first = units.findIndex((u) => u.kind === "visible");
  const last = units.findLastIndex((u) => u.kind === "visible");
  const start = first === -1 ? units : units.slice(0, first);
  const end = first === -1 ? units : units.slice(last + 1);
  // Rule 1.
  const stripsLeadingBlanks =
    first > 0 &&
    start.every((u) => u.kind === "blank") &&
    units.some((u) => u.encoded) &&
    units.some((u) => u.kind === "break");
  // Rule 2.
  const dropsEncodedBreak = (run: Unit[]) =>
    run.some((u) => u.kind === "break" && u.encoded) &&
    !run.some((u) => u.kind === "kept");
  return stripsLeadingBlanks || dropsEncodedBreak(start) || dropsEncodedBreak(end);
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
      if (losesWhitespace(raw)) {
        const { line } = file.getLineAndCharacterOfPosition(node.pos);
        const firstLine = raw.trim().split(/[\n\r\u2028\u2029]/)[0];
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
  // Rule 1, in the two shapes the site had; then no entity, one line, and an
  // explicit {" "}, which all keep the space.
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
  // Whitespace the compiler keeps, ahead of the words, keeps them apart.
  ["<>{x} &nbsp;after\n one&apos;s</>", "{x}\u00a0after one's", false],
  ["<>{x}&#32;after\n one&apos;s</>", "{x} after one's", false],
  // Whitespace that holds a literal line break goes in every compiler, as JSX
  // intends, so the source shows no space there to lose.
  ["<>{x} \n  it&apos;s</>", "{x}it's", false],
  ["<>{x}\n  the company&apos;s {y}</>", "{x}the company's {y}", false],
  // Rule 2: an encoded line break at either end vanishes with the whitespace
  // around it, unless kept whitespace is there too. Inside a text it becomes
  // a space, which loses nothing on the page.
  ["<>{x}&#10;word\n next</>", "{x}word next", true],
  ["<>{x}&#10;word</>", "{x}word", true],
  ["<>{x}\n  word&#10;{y}</>", "{x}word{y}", true],
  ["<>{x}&#10;&#32;word</>", "{x} word", false],
  ["<>{x}\n  one&#10;two\n</>", "{x}one two", false],
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
    const units = readText(reference);
    const decoded = rendered !== `a${reference}b`;
    if (decoded !== units.some((u) => u.encoded)) disagreements.push(reference);
    // A JSX name's character is whitespace only for WHITESPACE_ENTITY_NAMES.
    if (decoded && JSX_ENTITY_NAMES.has(reference.slice(1, -1))) {
      const kind = /\s/.test(rendered.slice(1, -1)) ? "kept" : "visible";
      if (units[0].kind !== kind) disagreements.push(`${reference} is ${kind}`);
    }
  }
  expect(disagreements).toEqual([]);
});

test("no page text loses a space in the production build", async () => {
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
