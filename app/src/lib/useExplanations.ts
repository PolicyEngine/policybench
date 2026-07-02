import { useCallback, useEffect, useState } from "react";

import type { CountryCode } from "../types";
import { explanationsPath } from "./dataVersionsRuntime";
import type { ExplanationsFile } from "./explanations";

export type ExplanationsStatus = "idle" | "loading" | "ready" | "error";

// Keyed by "<versionId>:<country>" so switching dataset version or country
// fetches the right sidecar instead of serving a cached one.
const cache = new Map<string, Promise<ExplanationsFile>>();

function cacheKey(versionId: string, country: CountryCode): string {
  return `${versionId}:${country}`;
}

function fetchExplanations(
  versionId: string,
  country: CountryCode,
): Promise<ExplanationsFile> {
  const key = cacheKey(versionId, country);
  let pending = cache.get(key);
  if (!pending) {
    pending = fetch(explanationsPath(versionId, country)).then((response) => {
      if (!response.ok) {
        throw new Error(`Failed to load explanations: HTTP ${response.status}`);
      }
      return response.json() as Promise<ExplanationsFile>;
    });
    // Drop failed loads from the cache so a retry can issue a fresh request.
    pending.catch(() => {
      if (cache.get(key) === pending) cache.delete(key);
    });
    cache.set(key, pending);
  }
  return pending;
}

/**
 * Lazily load the per-country explanation sidecar for the active dataset
 * version once `enabled` flips true (the scenario explorer enables it when it
 * approaches the viewport). Status is derived from the last settled fetch, so
 * switching country/version or retrying falls back to "loading" until the new
 * fetch resolves.
 */
export function useExplanations(
  country: CountryCode,
  enabled: boolean,
  versionId: string,
): {
  status: ExplanationsStatus;
  explanations: ExplanationsFile | null;
  retry: () => void;
} {
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState<{
    key: string;
    explanations: ExplanationsFile;
  } | null>(null);
  const [failure, setFailure] = useState<{
    key: string;
    attempt: number;
  } | null>(null);

  const key = cacheKey(versionId, country);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    fetchExplanations(versionId, country).then(
      (explanations) => {
        if (!cancelled) setLoaded({ key, explanations });
      },
      () => {
        if (!cancelled) setFailure({ key, attempt });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [key, versionId, country, enabled, attempt]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  const isReady = loaded?.key === key;
  const isFailed = failure?.key === key && failure.attempt === attempt;
  return {
    status: !enabled
      ? "idle"
      : isReady
        ? "ready"
        : isFailed
          ? "error"
          : "loading",
    explanations: isReady ? loaded.explanations : null,
    retry,
  };
}
