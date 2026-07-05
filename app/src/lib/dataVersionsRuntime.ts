/**
 * Browser-side access to the dataset-version registry.
 *
 * Keeps the static JSON imports (registry + the default version's bundled
 * summary) isolated from the pure parser in dataVersions.ts, and exposes the
 * lazy loaders the UI uses to switch versions.
 *
 * Build layout (see scripts/prepare-data.ts):
 *   - default version  -> src/data-summary.json          (bundled, synchronous)
 *                         public/data/explanations-*.json (lazy sidecars)
 *   - other versions    -> src/data-summary.<slug>.json    (code-split, lazy)
 *                         public/data/<slug>/explanations-*.json (lazy sidecars)
 */

import registryJson from "../data.versions.json";
import defaultSummary from "../data-summary.json";
import type { CountryCode, DashboardBundle } from "../types";
import {
  parseDataVersionRegistry,
  versionSlug,
  type DataVersion,
} from "./dataVersions";

const registry = parseDataVersionRegistry(registryJson);

export const DATA_VERSIONS: readonly DataVersion[] = registry.versions;
export const DEFAULT_VERSION_ID = registry.default;

const VERSIONS_BY_ID = new Map(registry.versions.map((v) => [v.id, v]));

export function getVersionById(id: string): DataVersion | undefined {
  return VERSIONS_BY_ID.get(id);
}

export function isKnownVersionId(id: string): boolean {
  return VERSIONS_BY_ID.has(id);
}

/**
 * Resolve the active version id from the ?dataset= query, falling back to the
 * default when absent or unrecognized so stale/hand-edited links stay valid.
 */
export function resolveVersionIdFromQuery(search: string): string {
  const raw = new URLSearchParams(search).get("dataset");
  if (raw && isKnownVersionId(raw)) return raw;
  return DEFAULT_VERSION_ID;
}

/**
 * Lazy summary loaders for the non-default versions. The default version is the
 * synchronous `defaultSummary` import above; every other version's summary is a
 * separate JSON chunk fetched only when selected. Static import() specifiers let
 * the bundler code-split each version.
 */
const NON_DEFAULT_SUMMARY_LOADERS: Record<
  string,
  () => Promise<{ default: unknown }>
> = {
  // Add a line here when a new non-default version ships (the id must match
  // data.versions.json). The default version is served from data-summary.json.
  "1.0": () => import("../data-summary.1_0.json"),
};

const summaryCache = new Map<string, Promise<DashboardBundle>>();

/**
 * Load a version's bundled numeric summary. The default resolves immediately
 * from the statically imported chunk; others resolve their code-split JSON and
 * are cached so repeat selections don't refetch.
 */
export function loadVersionSummary(id: string): Promise<DashboardBundle> {
  if (id === DEFAULT_VERSION_ID) {
    return Promise.resolve(defaultSummary as DashboardBundle);
  }
  let pending = summaryCache.get(id);
  if (!pending) {
    const loader = NON_DEFAULT_SUMMARY_LOADERS[id];
    if (!loader) {
      pending = Promise.reject(
        new Error(`No bundled summary loader registered for dataset "${id}"`),
      );
    } else {
      pending = loader().then((module) => module.default as DashboardBundle);
    }
    // Drop failed loads so a later retry can re-issue the import.
    pending.catch(() => {
      if (summaryCache.get(id) === pending) summaryCache.delete(id);
    });
    summaryCache.set(id, pending);
  }
  return pending;
}

/**
 * Public path to a version's per-country explanation sidecar. The default keeps
 * the flat /data/ path; other versions are namespaced by slug.
 */
export function explanationsPath(
  versionId: string,
  country: CountryCode,
): string {
  if (versionId === DEFAULT_VERSION_ID) {
    return `/data/explanations-${country}.json`;
  }
  return `/data/${versionSlug(versionId)}/explanations-${country}.json`;
}
