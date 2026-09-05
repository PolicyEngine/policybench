"use client";

import { useSyncExternalStore } from "react";

type VersionLabel = { id: string; label: string };

type ArchivedBoardNoticeProps = {
  liveVersionId: string;
  liveSnapshotDate: string;
  versions: readonly VersionLabel[];
  /** Optional deterministic search string for server rendering and tests. */
  search?: string;
};

function subscribeToLocation(onChange: () => void): () => void {
  window.addEventListener("popstate", onChange);
  return () => window.removeEventListener("popstate", onChange);
}

function browserSearch(): string {
  return window.location.search;
}

function staticExportSearch(): string {
  return "";
}

export default function ArchivedBoardNotice({
  liveVersionId,
  liveSnapshotDate,
  versions,
  search,
}: ArchivedBoardNoticeProps) {
  const locationSearch = useSyncExternalStore(
    subscribeToLocation,
    browserSearch,
    staticExportSearch,
  );
  const resolvedSearch = search ?? locationSearch;

  const dataset = new URLSearchParams(resolvedSearch).get("dataset");
  const archivedVersion = versions.find(
    (version) => version.id === dataset && version.id !== liveVersionId,
  );
  if (!archivedVersion) return null;

  return (
    <p
      role="note"
      className="mt-6 max-w-3xl rounded-lg border border-warning/40 bg-warning-soft px-3 py-2 text-sm leading-relaxed text-warning-text"
    >
      You came from the archived {archivedVersion.label} board. Per-model pages
      show the current board (snapshot {liveSnapshotDate}); archived per-model
      views are not available.
    </p>
  );
}
