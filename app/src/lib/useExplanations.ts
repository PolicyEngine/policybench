import { useCallback, useEffect, useState } from "react";

import type { CountryCode } from "../types";
import type { ExplanationsFile } from "./explanations";

export type ExplanationsStatus = "idle" | "loading" | "ready" | "error";

const cache = new Map<CountryCode, Promise<ExplanationsFile>>();

function fetchExplanations(country: CountryCode): Promise<ExplanationsFile> {
  let pending = cache.get(country);
  if (!pending) {
    pending = fetch(`/data/explanations-${country}.json`).then((response) => {
      if (!response.ok) {
        throw new Error(`Failed to load explanations: HTTP ${response.status}`);
      }
      return response.json() as Promise<ExplanationsFile>;
    });
    // Drop failed loads from the cache so a retry can issue a fresh request.
    pending.catch(() => {
      if (cache.get(country) === pending) cache.delete(country);
    });
    cache.set(country, pending);
  }
  return pending;
}

/**
 * Lazily load the per-country explanation sidecar once `enabled` flips true
 * (the scenario explorer enables it when it approaches the viewport). Status
 * is derived from the last settled fetch, so switching country or retrying
 * falls back to "loading" until the new fetch resolves.
 */
export function useExplanations(
  country: CountryCode,
  enabled: boolean,
): {
  status: ExplanationsStatus;
  explanations: ExplanationsFile | null;
  retry: () => void;
} {
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState<{
    country: CountryCode;
    explanations: ExplanationsFile;
  } | null>(null);
  const [failure, setFailure] = useState<{
    country: CountryCode;
    attempt: number;
  } | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    fetchExplanations(country).then(
      (explanations) => {
        if (!cancelled) setLoaded({ country, explanations });
      },
      () => {
        if (!cancelled) setFailure({ country, attempt });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [country, enabled, attempt]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  const isReady = loaded?.country === country;
  const isFailed =
    failure?.country === country && failure.attempt === attempt;
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
