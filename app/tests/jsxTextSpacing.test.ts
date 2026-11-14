import { expect, test } from "bun:test";
import { Glob } from "bun";
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

test("the rule flags the texts the compiler strips and no others", () => {
  // Each case's compiled output was checked against Next 16.2.6's own SWC.
  const stripped = [
    "<><B /> on 100\n  households from PolicyEngine&rsquo;s data.\n</>",
    "<>{x} reject forced calls, so\n  Fable 5.1&apos;s marker.\n</>",
  ];
  const kept = [
    "<><B /> on 100\n  real households.\n</>",
    "<><B /> on PolicyEngine&rsquo;s data.</>",
    '<><B />{" "}\n  on 100 households from PolicyEngine&rsquo;s data.\n</>',
  ];
  for (const jsx of stripped) {
    expect(droppedSpaces("case.tsx", `const a = ${jsx};`)).toHaveLength(1);
  }
  for (const jsx of kept) {
    expect(droppedSpaces("case.tsx", `const a = ${jsx};`)).toEqual([]);
  }
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
