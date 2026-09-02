/**
 * Board position a hypothetical exact-match score would take against the
 * given rows: one plus the number of rows scoring strictly higher. A row
 * that ties shares the higher position. Used by the leaderboard's
 * sensitivity callout so "would rank" is derived from the board data rather
 * than typed by hand.
 */
export function wouldRank(
  exact: number,
  rows: ReadonlyArray<{ exact?: number | null }>,
): number {
  return 1 + rows.filter((row) => (row.exact ?? 0) > exact).length;
}
