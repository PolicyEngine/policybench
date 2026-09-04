import type { CountryCode, DashboardBundle } from "../types";

export type ExactLeader = {
  model: string;
  exact: number;
};

/** Highest household-impact-weighted exact score for one live board country. */
export function headlineExactLeader(
  bundle: DashboardBundle,
  country: CountryCode = "us",
): ExactLeader {
  let leader: ExactLeader | null = null;
  const bench = bundle.countries[country];
  if (!bench) {
    throw new Error(`The bundled live board has no ${country} data`);
  }
  for (const row of bench.modelStats) {
    if (
      row.condition !== "no_tools" ||
      row.exact === undefined ||
      !Number.isFinite(row.exact)
    ) {
      continue;
    }
    if (leader === null || row.exact > leader.exact) {
      leader = { model: row.model, exact: row.exact };
    }
  }
  if (leader === null) {
    throw new Error("The bundled live board has no exact-score leader");
  }
  return leader;
}
