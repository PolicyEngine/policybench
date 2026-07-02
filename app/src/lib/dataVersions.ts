/**
 * Registry of published dashboard dataset versions.
 *
 * The dashboard payload is resolved and split at build time by
 * scripts/prepare-data.ts (not fetched in the browser): each version yields a
 * bundled numeric summary (src/data-summary.<slug>.json) plus per-country
 * explanation sidecars (public/data/<slug>/explanations-*.json). The default
 * version loads synchronously; the others are code-split and imported lazily
 * when the reader picks them from the header selector.
 *
 * src/data.versions.json lists each version and how to resolve its artifact:
 *   - an inline pointer (tag/url/sha256/bytes) freezes an archived release, or
 *   - {"pointer": "live"} defers to src/data.artifact.json, so the next data
 *     publish only has to update that pointer as usual.
 */

import type { ArtifactPointer } from "./dataArtifact";
import { parseArtifactPointer } from "./dataArtifact";

/** Resolves to the current src/data.artifact.json pointer at build time. */
export type LivePointerRef = { pointer: "live" };

export type VersionArtifact = ArtifactPointer | LivePointerRef;

export type DataVersion = {
  /** Stable identifier used in the URL query and output paths, e.g. "1.0". */
  id: string;
  /** Short label shown in the selector, e.g. "1.1". */
  label: string;
  /** One-line human description of what changed in this version. */
  description: string;
  /**
   * Snapshot chip label shown in the hero for archived versions (e.g.
   * "Snapshot 2026-06-25"). When null the hero keeps its own live constant.
   */
  snapshotLabel: string | null;
  artifact: VersionArtifact;
};

export type DataVersionRegistry = {
  version: number;
  default: string;
  versions: DataVersion[];
};

export function isLivePointerRef(
  artifact: VersionArtifact,
): artifact is LivePointerRef {
  return (
    typeof artifact === "object" &&
    artifact !== null &&
    "pointer" in artifact &&
    (artifact as LivePointerRef).pointer === "live"
  );
}

/**
 * Filesystem- and URL-safe slug for a version id. Dots become underscores so
 * "1.0" maps to data-summary.1_0.json and public/data/1_0/.
 */
export function versionSlug(id: string): string {
  return id.replace(/\./g, "_");
}

function parseArtifact(raw: unknown, id: string): VersionArtifact {
  if (
    typeof raw === "object" &&
    raw !== null &&
    "pointer" in (raw as Record<string, unknown>)
  ) {
    if ((raw as Record<string, unknown>).pointer !== "live") {
      throw new Error(
        `data version "${id}": the only supported artifact pointer alias is ` +
          '"live"',
      );
    }
    return { pointer: "live" };
  }
  // Any non-alias artifact must be a full, hash-pinned release pointer.
  return parseArtifactPointer(raw);
}

/**
 * Validate the raw src/data.versions.json contents into a typed registry.
 * Throws with a specific message on the first malformed field so a bad edit
 * fails the build loudly rather than shipping a mislabeled dataset.
 */
export function parseDataVersionRegistry(raw: unknown): DataVersionRegistry {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    throw new Error("data.versions.json must be a JSON object");
  }
  const record = raw as Record<string, unknown>;
  if (record.version !== 1) {
    throw new Error(
      `unsupported data.versions.json version ${JSON.stringify(
        record.version,
      )}; expected 1`,
    );
  }
  if (!Array.isArray(record.versions) || record.versions.length === 0) {
    throw new Error('data.versions.json "versions" must be a non-empty array');
  }

  const seen = new Set<string>();
  const versions: DataVersion[] = record.versions.map((entry, index) => {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
      throw new Error(`data.versions.json versions[${index}] must be an object`);
    }
    const version = entry as Record<string, unknown>;
    for (const field of ["id", "label", "description"] as const) {
      if (typeof version[field] !== "string" || version[field] === "") {
        throw new Error(
          `data.versions.json versions[${index}] is missing string field ` +
            `"${field}"`,
        );
      }
    }
    const id = version.id as string;
    if (seen.has(id)) {
      throw new Error(`data.versions.json has duplicate version id "${id}"`);
    }
    seen.add(id);
    const snapshotLabelRaw = version.snapshotLabel ?? null;
    if (snapshotLabelRaw !== null && typeof snapshotLabelRaw !== "string") {
      throw new Error(
        `data.versions.json version "${id}" snapshotLabel must be a string ` +
          "or null",
      );
    }
    return {
      id,
      label: version.label as string,
      description: version.description as string,
      snapshotLabel: snapshotLabelRaw as string | null,
      artifact: parseArtifact(version.artifact, id),
    };
  });

  if (typeof record.default !== "string" || !seen.has(record.default)) {
    throw new Error(
      `data.versions.json "default" must name one of the listed versions ` +
        `(${[...seen].join(", ")})`,
    );
  }

  return {
    version: 1,
    default: record.default,
    versions,
  };
}
