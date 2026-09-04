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

/** Row-weighted Medicaid accuracy for each model, then the median across models. */
export function medicaidEligibilityAccuracy(bundle: DashboardBundle): {
  median: number;
  weakest: number;
} {
  const byModel = new Map<string, { correct: number; rows: number }>();
  for (const row of bundle.countries.us?.heatmap ?? []) {
    const accuracy = row.accuracy ?? row.exact;
    if (
      row.condition !== "no_tools" ||
      !row.variable.endsWith("_medicaid_eligible") ||
      accuracy === undefined ||
      !Number.isFinite(accuracy) ||
      row.n <= 0
    ) {
      continue;
    }
    const model = byModel.get(row.model) ?? { correct: 0, rows: 0 };
    model.correct += accuracy * row.n;
    model.rows += row.n;
    byModel.set(row.model, model);
  }
  const accuracies = [...byModel.values()]
    .map(({ correct, rows }) => correct / rows)
    .sort((a, b) => a - b);
  if (accuracies.length === 0) {
    throw new Error("The bundled live board has no Medicaid eligibility accuracy");
  }
  const middle = Math.floor(accuracies.length / 2);
  const median = accuracies.length % 2 === 1
    ? accuracies[middle]
    : (accuracies[middle - 1] + accuracies[middle]) / 2;
  return { median, weakest: accuracies[0] };
}

export function misclassificationFrequency(accuracy: number): string {
  return accuracy >= 100
    ? "none of the evaluated people"
    : `about 1 in ${Math.round(100 / (100 - accuracy))} people`;
}
