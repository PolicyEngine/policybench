/** A React ref-shaped counter used to identify the newest dataset load. */
export type VersionSelectionSequence = { current: number };

/**
 * Start a dataset load and apply its result only while it is still the newest
 * selection. This keeps a slow earlier request from replacing the dashboard,
 * or rolling it back after a failure, once the reader has selected again.
 */
export function loadLatestVersion<T>(
  sequence: VersionSelectionSequence,
  load: () => Promise<T>,
  onLoaded: (value: T) => void,
  onFailed: (error: unknown) => void,
): void {
  const selection = ++sequence.current;
  load().then(
    (value) => {
      if (selection === sequence.current) onLoaded(value);
    },
    (error: unknown) => {
      if (selection === sequence.current) onFailed(error);
    },
  );
}
