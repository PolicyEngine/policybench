/**
 * Whether a dataset version is the current (live) board. Copy that describes
 * the current roster's serving treatments, and sensitivity comparisons made
 * against the current board's scores, are shown only for that version: an
 * archived snapshot has its own roster and reference set, so those blocks
 * would be false or meaningless under it.
 */
export function isCurrentBoard(
  versionId: string,
  liveVersionId: string,
): boolean {
  return versionId === liveVersionId;
}
