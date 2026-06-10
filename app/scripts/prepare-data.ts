/**
 * Build-time split of the dashboard payload.
 *
 * Source resolution order:
 *   1. src/data.json - committed or locally exported payload
 *   2. src/data.artifact.json - pointer to a published GitHub release asset
 *      (written by `policybench publish-dashboard`); downloaded to .cache/
 *      and verified against the recorded sha256
 *
 * Emits:
 *   - src/data-summary.json          bundled with the app (no free text)
 *   - public/data/explanations-*.json fetched lazily by the scenario explorer
 *
 * Runs before `next dev` and `next build` (see package.json). Outputs are
 * generated artifacts and gitignored.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  assertDashboardShape,
  parseArtifactPointer,
  sha256Hex,
} from "../src/lib/dataArtifact";
import { splitDashboardExplanations } from "../src/lib/explanations";
import type { DashboardBundle } from "../src/types";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = path.join(appRoot, "src", "data.json");
const pointerPath = path.join(appRoot, "src", "data.artifact.json");
const cacheDir = path.join(appRoot, ".cache");
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

async function fetchArtifact(): Promise<{ bytes: Buffer; origin: string }> {
  const pointer = parseArtifactPointer(
    JSON.parse(readFileSync(pointerPath, "utf8")),
  );
  const cachePath = path.join(
    cacheDir,
    `dashboard-data-${pointer.sha256.slice(0, 16)}.json`,
  );

  if (existsSync(cachePath)) {
    const cached = readFileSync(cachePath);
    if ((await sha256Hex(cached)) === pointer.sha256) {
      return { bytes: cached, origin: `${cachePath} (cached)` };
    }
    console.warn(`prepare-data: cache at ${cachePath} is stale, re-downloading`);
  }

  console.log(
    `prepare-data: downloading ${pointer.url} (${formatMb(pointer.bytes)})`,
  );
  const response = await fetch(pointer.url);
  if (!response.ok) {
    throw new Error(
      `Failed to download dashboard artifact: HTTP ${response.status} from ` +
      pointer.url,
    );
  }
  const bytes = Buffer.from(await response.arrayBuffer());
  const digest = await sha256Hex(bytes);
  if (digest !== pointer.sha256) {
    throw new Error(
      `Downloaded artifact hash mismatch for ${pointer.url}: expected ` +
      `${pointer.sha256}, got ${digest}. Refusing to use it.`,
    );
  }
  mkdirSync(cacheDir, { recursive: true });
  writeFileSync(cachePath, bytes);
  return { bytes, origin: pointer.url };
}

async function resolveSource(): Promise<{ bytes: Buffer; origin: string }> {
  if (existsSync(sourcePath)) {
    return { bytes: readFileSync(sourcePath), origin: sourcePath };
  }
  if (existsSync(pointerPath)) {
    return fetchArtifact();
  }
  throw new Error(
    `prepare-data: neither ${sourcePath} nor ${pointerPath} exists. ` +
    "Export a run (policybench export-full-run) or commit an artifact " +
    "pointer (policybench publish-dashboard).",
  );
}

const { bytes, origin } = await resolveSource();
const bundle = JSON.parse(bytes.toString("utf8")) as unknown;
assertDashboardShape(bundle, origin);
const { summary, explanations } = splitDashboardExplanations(
  bundle as DashboardBundle,
);

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
  `prepare-data: ${formatMb(bytes.length)} payload from ${origin} -> ` +
  `${formatMb(summaryJson.length)} bundled summary + ` +
  `lazy explanations (${sidecarSizes.join(", ")})`,
);
