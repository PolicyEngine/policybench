/** A React ref-shaped counter used to identify the newest dataset load. */
export type VersionSelectionSequence = { current: number };
export type MountedRef = { current: boolean };

export type DatasetSelectionState<T> = {
  versionId: string;
  pendingVersionId: string | null;
  dashboard: T;
};

export type DatasetSelectionAction<T> =
  | { type: "start"; versionId: string }
  | { type: "loaded"; versionId: string; dashboard: T }
  | { type: "clear-pending" };

/** Keep the active version and its dashboard in one atomic React state. */
export function datasetSelectionReducer<T>(
  state: DatasetSelectionState<T>,
  action: DatasetSelectionAction<T>,
): DatasetSelectionState<T> {
  switch (action.type) {
    case "start":
      return { ...state, pendingVersionId: action.versionId };
    case "loaded":
      return {
        versionId: action.versionId,
        pendingVersionId: null,
        dashboard: action.dashboard,
      };
    case "clear-pending":
      return { ...state, pendingVersionId: null };
  }
}

/** Return a shareable URL whose dataset query matches the active version. */
export function urlForDatasetVersion(
  href: string,
  versionId: string,
  defaultVersionId: string,
): string {
  const url = new URL(href);
  if (versionId === defaultVersionId) {
    url.searchParams.delete("dataset");
  } else {
    url.searchParams.set("dataset", versionId);
  }
  return url.toString();
}

/**
 * Start a dataset load and apply its result only while it is still the newest
 * selection. This keeps a slow earlier request from replacing the dashboard,
 * or rolling it back after a failure, once the reader has selected again.
 */
export function loadLatestVersion<T>(
  sequence: VersionSelectionSequence,
  mounted: MountedRef,
  load: () => Promise<T>,
  onLoaded: (value: T) => void,
  onFailed: (error: unknown) => void,
): void {
  const selection = ++sequence.current;
  load().then(
    (value) => {
      if (!mounted.current) return;
      if (selection === sequence.current) onLoaded(value);
    },
    (error: unknown) => {
      if (!mounted.current) return;
      if (selection === sequence.current) onFailed(error);
    },
  );
}
