/**
 * Build-time split of the dashboard payload, for every published dataset
 * version listed in src/data.versions.json.
 *
 * Per-version source resolution order:
 *   1. src/data.json - committed or locally exported payload. Applies to the
 *      default version only, so a local export can stand in for the live data
 *      without re-downloading the archived versions.
 *   2. the version's artifact:
 *        - {"pointer": "live"}    -> src/data.artifact.json (the current pointer)
 *        - an inline release pointer (tag/url/sha256/bytes) for archived versions
 *      The asset is downloaded to .cache/ and verified against its sha256.
 *
 * Emits, per version:
 *   - default version -> src/data-summary.json               (bundled with app)
 *                        public/data/explanations-*.json      (lazy sidecars)
 *   - other versions  -> src/data-summary.<slug>.json         (code-split chunk)
 *                        public/data/<slug>/explanations-*.json (lazy sidecars)
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
  type ArtifactPointer,
} from "../src/lib/dataArtifact";
import {
  isLivePointerRef,
  parseDataVersionRegistry,
  versionSlug,
  type DataVersion,
} from "../src/lib/dataVersions";
import { splitDashboardExplanations } from "../src/lib/explanations";
import type { DashboardBundle } from "../src/types";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = path.join(appRoot, "src", "data.json");
const pointerPath = path.join(appRoot, "src", "data.artifact.json");
const registryPath = path.join(appRoot, "src", "data.versions.json");
const cacheDir = path.join(appRoot, ".cache");
const srcDir = path.join(appRoot, "src");
const sidecarRoot = path.join(appRoot, "public", "data");

function formatMb(bytes: number): string {
  return `${(bytes / 1_000_000).toFixed(1)}MB`;
}

/**
 * Escape non-ASCII characters like Python's json.dump does. Turbopack's dev
 * JSON-module loader mis-parses multi-byte UTF-8 in imported JSON (the module
 * resolves to undefined), so the bundled summary must stay ASCII-only.
 */
function toAsciiJson(value: unknown): string {
  // Escape every non-ASCII code unit (>= 0x80) like Python's json.dump does.
  return JSON.stringify(value).replace(/[^\x00-\x7f]/g, (char) =>
    `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`,
  );
}

async function fetchFromPointer(
  pointer: ArtifactPointer,
): Promise<{ bytes: Buffer; origin: string }> {
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

/** Resolve the live pointer (src/data.artifact.json) to a verified payload. */
function resolveLivePointer(): ArtifactPointer {
  if (!existsSync(pointerPath)) {
    throw new Error(
      `prepare-data: version uses {"pointer": "live"} but ${pointerPath} ` +
        "is missing.",
    );
  }
  return parseArtifactPointer(JSON.parse(readFileSync(pointerPath, "utf8")));
}

async function resolveVersionSource(
  version: DataVersion,
  isDefault: boolean,
): Promise<{ bytes: Buffer; origin: string }> {
  // A local export stands in for the live/default data only. Archived versions
  // always resolve through their pinned artifact so their hashes stay honest.
  if (isDefault && existsSync(sourcePath)) {
    return { bytes: readFileSync(sourcePath), origin: sourcePath };
  }
  const pointer = isLivePointerRef(version.artifact)
    ? resolveLivePointer()
    : version.artifact;
  return fetchFromPointer(pointer);
}

async function buildVersion(
  version: DataVersion,
  isDefault: boolean,
): Promise<string> {
  const { bytes, origin } = await resolveVersionSource(version, isDefault);
  const bundle = JSON.parse(bytes.toString("utf8")) as unknown;
  assertDashboardShape(bundle, `${origin} (version ${version.id})`);
  const { summary, explanations } = splitDashboardExplanations(
    bundle as DashboardBundle,
  );

  // Default -> canonical paths (App.tsx imports src/data-summary.json and the
  // flat /data/ sidecars); other versions -> slug-namespaced paths.
  const slug = versionSlug(version.id);
  const summaryPath = isDefault
    ? path.join(srcDir, "data-summary.json")
    : path.join(srcDir, `data-summary.${slug}.json`);
  const sidecarDir = isDefault ? sidecarRoot : path.join(sidecarRoot, slug);

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

  return (
    `prepare-data: [${version.id}] ${formatMb(bytes.length)} payload from ` +
    `${origin} -> ${formatMb(summaryJson.length)} bundled summary + ` +
    `lazy explanations (${sidecarSizes.join(", ")})`
  );
}

const registry = parseDataVersionRegistry(
  JSON.parse(readFileSync(registryPath, "utf8")),
);

// Build the default first so a local src/data.json export surfaces problems
// before the network fetches for archived versions.
const ordered = [...registry.versions].sort((a, b) =>
  a.id === registry.default ? -1 : b.id === registry.default ? 1 : 0,
);

for (const version of ordered) {
  const line = await buildVersion(version, version.id === registry.default);
  console.log(line);
}
