/**
 * Build-time split of src/data.json.
 *
 * Emits:
 *   - src/data-summary.json          bundled with the app (no free text)
 *   - public/data/explanations-*.json fetched lazily by the scenario explorer
 *
 * Runs before `next dev` and `next build` (see package.json). Outputs are
 * generated artifacts and gitignored; src/data.json stays the only source of
 * truth that benchmark exports need to update.
 */
import { mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { splitDashboardExplanations } from "../src/lib/explanations";
import type { DashboardBundle } from "../src/types";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = path.join(appRoot, "src", "data.json");
const summaryPath = path.join(appRoot, "src", "data-summary.json");
const sidecarDir = path.join(appRoot, "public", "data");

function formatMb(bytes: number): string {
  return `${(bytes / 1_000_000).toFixed(1)}MB`;
}

/**
 * Escape non-ASCII characters like Python's json.dump does. Turbopack's dev
 * JSON-module loader mis-parses multi-byte UTF-8 in imported JSON (the module
 * resolves to undefined), so the bundled summary must stay ASCII-only.
 */
function toAsciiJson(value: unknown): string {
  return JSON.stringify(value).replace(
    /[\u0080-\uffff]/g,
    (char) => `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`,
  );
}

const sourceBytes = statSync(sourcePath).size;
const bundle = JSON.parse(readFileSync(sourcePath, "utf8")) as DashboardBundle;
const { summary, explanations } = splitDashboardExplanations(bundle);

const summaryJson = toAsciiJson(summary);
writeFileSync(summaryPath, summaryJson);
mkdirSync(sidecarDir, { recursive: true });

const sidecarSizes: string[] = [];
for (const file of Object.values(explanations)) {
  const sidecarJson = JSON.stringify(file);
  writeFileSync(
    path.join(sidecarDir, `explanations-${file.country}.json`),
    sidecarJson,
  );
  sidecarSizes.push(`${file.country} ${formatMb(sidecarJson.length)}`);
}

console.log(
  `prepare-data: ${formatMb(sourceBytes)} data.json -> ` +
    `${formatMb(summaryJson.length)} bundled summary + ` +
    `lazy explanations (${sidecarSizes.join(", ")})`,
);
