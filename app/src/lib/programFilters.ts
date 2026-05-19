import { getVariableLabel, type BenchData } from "../types";
import { outputGroupForVariable } from "./scoring";

export type ProgramOption = {
  variable: string;
  label: string;
};

export type ProgramRate = {
  variable: string;
  value: number | undefined;
};

export function buildProgramOptions(data: BenchData): ProgramOption[] {
  const variables = new Set<string>();
  for (const entry of data.heatmap) {
    if (entry.condition === "no_tools") {
      variables.add(outputGroupForVariable(entry.variable));
    }
  }
  return Array.from(variables)
    .map((variable) => ({
      variable,
      label: getVariableLabel(variable, data.country),
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

export function resolveActiveProgramIds(
  programOptionIds: readonly string[],
  selectedPrograms: Set<string>,
): Set<string> {
  const all = new Set(programOptionIds);
  if (selectedPrograms.size === 0) return all;
  const active = new Set(
    [...selectedPrograms]
      .map(outputGroupForVariable)
      .filter((variable) => all.has(variable)),
  );
  return active.size > 0 ? active : all;
}

export function toggleProgramSelection(
  programOptionIds: readonly string[],
  selectedPrograms: Set<string>,
  variable: string,
): Set<string> {
  const allowed = new Set(programOptionIds);
  const normalized = new Set(
    [...selectedPrograms]
      .map(outputGroupForVariable)
      .filter((value) => allowed.has(value)),
  );
  const next =
    selectedPrograms.size === 0 || normalized.size === 0
      ? new Set(programOptionIds)
      : normalized;
  const groupedVariable = outputGroupForVariable(variable);

  if (next.has(groupedVariable)) {
    if (next.size === 1) return next;
    next.delete(groupedVariable);
  } else {
    next.add(groupedVariable);
  }

  return next.size === programOptionIds.length ? new Set() : next;
}

export function selectOnlyProgram(variable: string): Set<string> {
  return new Set([outputGroupForVariable(variable)]);
}

export function programIsActive(
  activeProgramIds: Set<string>,
  variable: string,
): boolean {
  return activeProgramIds.has(outputGroupForVariable(variable));
}

export function groupWeights(
  weights: Record<string, number>,
): Record<string, number> {
  const grouped: Record<string, number> = {};
  for (const [variable, weight] of Object.entries(weights)) {
    const group = outputGroupForVariable(variable);
    grouped[group] = (grouped[group] ?? 0) + weight;
  }
  return grouped;
}

export function weightForProgram(
  weights: Record<string, number>,
  variable: string,
): number | undefined {
  return groupWeights(weights)[outputGroupForVariable(variable)];
}

function groupRates(rates: Iterable<ProgramRate>): ProgramRate[] {
  const grouped = new Map<string, { sum: number; n: number }>();
  for (const { variable, value } of rates) {
    if (value === undefined) continue;
    const group = outputGroupForVariable(variable);
    const acc = grouped.get(group) ?? { sum: 0, n: 0 };
    acc.sum += value;
    acc.n += 1;
    grouped.set(group, acc);
  }
  return [...grouped.entries()].map(([variable, { sum, n }]) => ({
    variable,
    value: sum / n,
  }));
}

export function weightedProgramScore(
  rates: Iterable<ProgramRate>,
  weights: Record<string, number>,
): number | undefined {
  const groupedWeights = groupWeights(weights);
  let numerator = 0;
  let denominator = 0;

  for (const { variable, value } of groupRates(rates)) {
    if (value === undefined) continue;
    const weight = groupedWeights[variable];
    if (weight === undefined) continue;
    numerator += weight * (value / 100);
    denominator += weight;
  }

  return denominator > 0 ? (numerator / denominator) * 100 : undefined;
}
