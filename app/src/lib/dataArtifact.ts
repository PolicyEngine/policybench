/**
 * Helpers for resolving the dashboard payload from a published artifact.
 *
 * `policybench publish-dashboard` uploads data.json as a GitHub release
 * asset and writes a pointer file (src/data.artifact.json) recording the
 * URL and sha256. When src/data.json is absent from the working tree,
 * scripts/prepare-data.ts downloads the asset via the pointer and verifies
 * the hash before using it.
 */

export type ArtifactPointer = {
  version: number;
  repo: string;
  tag: string;
  asset: string;
  url: string;
  sha256: string;
  bytes: number;
};

const POINTER_STRING_FIELDS = ["repo", "tag", "asset", "url", "sha256"] as const;

export function parseArtifactPointer(raw: unknown): ArtifactPointer {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    throw new Error("artifact pointer must be a JSON object");
  }
  const pointer = raw as Record<string, unknown>;
  if (pointer.version !== 1) {
    throw new Error(
      `unsupported artifact pointer version ${JSON.stringify(pointer.version)}; ` +
        "expected 1",
    );
  }
  for (const field of POINTER_STRING_FIELDS) {
    if (typeof pointer[field] !== "string" || pointer[field] === "") {
      throw new Error(`artifact pointer is missing string field "${field}"`);
    }
  }
  if (typeof pointer.bytes !== "number" || !Number.isFinite(pointer.bytes)) {
    throw new Error('artifact pointer is missing numeric field "bytes"');
  }
  if (!/^[0-9a-f]{64}$/.test(pointer.sha256 as string)) {
    throw new Error("artifact pointer sha256 must be 64 lowercase hex chars");
  }
  if (!(pointer.url as string).startsWith("https://")) {
    throw new Error("artifact pointer url must be https");
  }
  return pointer as ArtifactPointer;
}

export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer,
  );
  return Array.from(new Uint8Array(digest))
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Guard against the most common malformed export: a per-country payload
 * (<run>/<country>/data.json) copied to the app path instead of the combined
 * {"countries": {...}} shape.
 */
export function assertDashboardShape(payload: unknown, source: string): void {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    throw new Error(`${source}: dashboard payload must be a JSON object`);
  }
  const record = payload as Record<string, unknown>;
  if (!("countries" in record)) {
    if ("country" in record && "modelStats" in record) {
      throw new Error(
        `${source}: this is a per-country export (<run>/<country>/data.json); ` +
          'the app needs the combined {"countries": {...}} payload written ' +
          "by export_full_run / publish-dashboard",
      );
    }
    throw new Error(`${source}: dashboard payload missing top-level "countries"`);
  }
  const countries = record.countries;
  if (
    typeof countries !== "object" ||
    countries === null ||
    Object.keys(countries as object).length === 0
  ) {
    throw new Error(`${source}: "countries" must be a non-empty object`);
  }
}
