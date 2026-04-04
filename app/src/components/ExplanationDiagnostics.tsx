import { useMemo, useState } from "react";
import { formatCurrency } from "../format";
import { MODEL_LABELS, MODEL_ORDER, getPredictionTextColor } from "../modelMeta";
import type { BenchData } from "../types";
import { getVariableLabel, isBinaryVariable } from "../types";
import ProviderMark from "./ProviderMark";
import { getProviderForModel } from "../modelMeta";

function formatBoolean(value: number): string {
  return value === 1 ? "Yes" : "No";
}

function pickRandomScenario(
  scenarioIds: string[],
  exclude?: string | null
): string | null {
  if (scenarioIds.length === 0) return null;
  if (scenarioIds.length === 1) return scenarioIds[0];

  const candidates = exclude
    ? scenarioIds.filter((scenarioId) => scenarioId !== exclude)
    : scenarioIds;

  if (candidates.length === 0) return scenarioIds[0];
  return candidates[Math.floor(Math.random() * candidates.length)];
}

function pickBestScenario(
  scenarioIds: string[],
  scenarioPredictions: BenchData["scenarioPredictions"]
): string | null {
  if (!scenarioIds.length) return null;

  const scored = scenarioIds.map((scenarioId) => {
    const variables = scenarioPredictions[scenarioId] ?? {};
    let totalExplanationCount = 0;
    let bestVariableExplanationCount = 0;

    for (const modelMap of Object.values(variables)) {
      const explanationCount = Object.values(modelMap).filter(
        (entry) => !!entry.explanation
      ).length;
      totalExplanationCount += explanationCount;
      bestVariableExplanationCount = Math.max(
        bestVariableExplanationCount,
        explanationCount
      );
    }

    return {
      scenarioId,
      totalExplanationCount,
      bestVariableExplanationCount,
    };
  });

  scored.sort((a, b) => {
    if (b.bestVariableExplanationCount !== a.bestVariableExplanationCount) {
      return b.bestVariableExplanationCount - a.bestVariableExplanationCount;
    }
    if (b.totalExplanationCount !== a.totalExplanationCount) {
      return b.totalExplanationCount - a.totalExplanationCount;
    }
    return a.scenarioId.localeCompare(b.scenarioId);
  });

  return scored[0]?.scenarioId ?? null;
}

export default function ExplanationDiagnostics({
  data,
}: {
  data: BenchData;
}) {
  const country = data.country;
  const currencySymbol = country === "uk" ? "£" : "$";

  const scenarioIds = useMemo(() => {
    return Object.entries(data.scenarioPredictions)
      .filter(([, variables]) =>
        Object.values(variables).some((models) =>
          Object.values(models).some((prediction) => prediction.explanation)
        )
      )
      .map(([scenarioId]) => scenarioId)
      .sort();
  }, [data.scenarioPredictions]);

  const preferredScenario = useMemo(
    () => pickBestScenario(scenarioIds, data.scenarioPredictions),
    [data.scenarioPredictions, scenarioIds]
  );

  const [selectedScenario, setSelectedScenario] = useState<string | null>(() =>
    preferredScenario
  );

  const resolvedScenarioId =
    selectedScenario && data.scenarioPredictions[selectedScenario]
      ? selectedScenario
      : preferredScenario ?? scenarioIds[0] ?? null;

  const scenario = resolvedScenarioId ? data.scenarios[resolvedScenarioId] : null;
  const scenarioPredictions = useMemo(
    () =>
      resolvedScenarioId ? data.scenarioPredictions[resolvedScenarioId] ?? {} : {},
    [data.scenarioPredictions, resolvedScenarioId]
  );

  const variableOptions = useMemo(() => {
    return Object.entries(scenarioPredictions)
      .map(([variable, modelMap]) => ({
        variable,
        explanationCount: Object.values(modelMap).filter(
          (entry) => !!entry.explanation
        ).length,
      }))
      .filter((entry) => entry.explanationCount > 0)
      .sort((a, b) => a.variable.localeCompare(b.variable));
  }, [scenarioPredictions]);

  const [selectedVariable, setSelectedVariable] = useState<string | null>(null);

  const resolvedVariable =
    selectedVariable &&
    variableOptions.some((entry) => entry.variable === selectedVariable)
      ? selectedVariable
      : variableOptions[0]?.variable ?? null;

  const explanationEntries = useMemo(() => {
    if (!resolvedVariable) return [];
    const modelMap = scenarioPredictions[resolvedVariable] ?? {};
    return MODEL_ORDER.filter((model) => modelMap[model]?.explanation).map(
      (model) => ({
        model,
        prediction: modelMap[model].prediction,
        groundTruth: modelMap[model].groundTruth,
        error: modelMap[model].error,
        explanation: modelMap[model].explanation,
      })
    );
  }, [resolvedVariable, scenarioPredictions]);

  const omittedModels = useMemo(() => {
    if (!resolvedVariable) return [];
    const modelMap = scenarioPredictions[resolvedVariable] ?? {};
    return MODEL_ORDER.filter(
      (model) => modelMap[model] && !modelMap[model].explanation
    );
  }, [resolvedVariable, scenarioPredictions]);

  const totalModelsForVariable = resolvedVariable
    ? Object.keys(scenarioPredictions[resolvedVariable] ?? {}).length
    : 0;

  if (!scenario || !resolvedScenarioId || !scenarioIds.length) return null;

  const truth =
    resolvedVariable && explanationEntries[0]
      ? explanationEntries[0].groundTruth
      : resolvedVariable
        ? Object.values(scenarioPredictions[resolvedVariable] ?? {})[0]?.groundTruth
        : null;
  const variableIsBinary = resolvedVariable
    ? isBinaryVariable(resolvedVariable, country)
    : false;
  const truthLabel =
    truth == null
      ? "n/a"
      : variableIsBinary
        ? formatBoolean(truth)
        : formatCurrency(truth, currencySymbol);

  const handleShuffle = () => {
    const nextScenario = pickRandomScenario(scenarioIds, resolvedScenarioId);
    if (nextScenario) {
      setSelectedScenario(nextScenario);
    }
  };

  return (
    <div>
      <div className="eyebrow mb-3 animate-fade-up">Diagnostics</div>
      <h2
        className="font-[family-name:var(--font-display)] text-4xl md:text-5xl text-text tracking-tight animate-fade-up"
        style={{ animationDelay: "80ms" }}
      >
        How models explain the same case
      </h2>
      <p
        className="mt-3 max-w-3xl text-text-secondary leading-relaxed animate-fade-up"
        style={{ animationDelay: "160ms" }}
      >
        This section uses a separate 100-household diagnostic run with optional
        one-sentence explanations. It is not part of the benchmark score. It is
        for comparing how models justify the same output on the same household.
        The first household shown is picked for explanation coverage rather than
        at random.
      </p>

      <div
        className="mt-8 flex flex-wrap items-end gap-4 animate-fade-up"
        style={{ animationDelay: "220ms" }}
      >
        <div className="min-w-0 flex-1">
          <label className="mb-1.5 block text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
            Diagnostic household
          </label>
          <div className="flex items-center gap-2">
            <select
              value={resolvedScenarioId}
              onChange={(e) => setSelectedScenario(e.target.value)}
              className="min-w-0 flex-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text focus:border-primary/50 focus:outline-none font-[family-name:var(--font-mono)]"
            >
              {scenarioIds.map((scenarioId) => {
                const item = data.scenarios[scenarioId];
                return (
                  <option key={scenarioId} value={scenarioId}>
                    {scenarioId.replace("scenario_", "#")} - {item.state}
                    {item.filingStatus ? `, ${item.filingStatus}` : ""},{" "}
                    {formatCurrency(Number(item.totalIncome), currencySymbol)}
                  </option>
                );
              })}
            </select>
            <button
              type="button"
              onClick={handleShuffle}
              disabled={scenarioIds.length < 2}
              aria-label="Shuffle diagnostic household"
              title="Shuffle diagnostic household"
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border bg-surface text-text-secondary transition-colors hover:border-primary/50 hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
            >
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                className="h-4 w-4"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M16 3h5v5" />
                <path d="M4 20 21 3" />
                <path d="M21 16v5h-5" />
                <path d="M15 15 21 21" />
                <path d="M4 4 9 9" />
              </svg>
            </button>
          </div>
        </div>

        <div className="min-w-[16rem]">
          <label className="mb-1.5 block text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
            Output
          </label>
          <select
            value={resolvedVariable ?? ""}
            onChange={(e) => setSelectedVariable(e.target.value)}
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text focus:border-primary/50 focus:outline-none"
          >
            {variableOptions.map((entry) => (
              <option key={entry.variable} value={entry.variable}>
                {getVariableLabel(entry.variable, country)} ({entry.explanationCount})
              </option>
            ))}
          </select>
        </div>
      </div>

      <div
        className="card mt-6 px-5 py-4 animate-fade-up"
        style={{ animationDelay: "280ms" }}
      >
        <div className="grid gap-4 md:grid-cols-4">
          <div>
            <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
              Region
            </div>
            <div className="mt-1 text-sm text-text">{scenario.state}</div>
          </div>
          <div>
            <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
              Household
            </div>
            <div className="mt-1 text-sm text-text">
              {scenario.numAdults} adults, {scenario.numChildren} children
            </div>
          </div>
          <div>
            <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
              Output
            </div>
            <div className="mt-1 text-sm text-text">
              {resolvedVariable ? getVariableLabel(resolvedVariable, country) : "n/a"}
            </div>
          </div>
          <div>
            <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
              Ground truth
            </div>
            <div className="mt-1 font-[family-name:var(--font-mono)] text-sm text-text">
              {truthLabel}
            </div>
          </div>
        </div>
        <div className="mt-4 border-t border-border-subtle pt-4 text-sm text-text-secondary">
          {resolvedVariable ? (
            <>
              {explanationEntries.length} of {totalModelsForVariable} models
              returned explanation text for this output in the diagnostic run.
            </>
          ) : (
            <>No diagnostic explanation text is available for this output.</>
          )}
        </div>
      </div>

      {explanationEntries.length > 0 ? (
        <div className="mt-6 grid gap-4 lg:grid-cols-2">
        {explanationEntries.map((entry, index) => {
          const valueLabel = variableIsBinary
            ? formatBoolean(entry.prediction)
            : formatCurrency(entry.prediction, currencySymbol);
          const matches = variableIsBinary
            ? entry.prediction === entry.groundTruth
            : Math.abs(entry.error) <= Math.abs(entry.groundTruth) * 0.1 ||
              (entry.groundTruth === 0 && entry.prediction === 0);

          return (
            <div
              key={`${resolvedScenarioId}-${resolvedVariable}-${entry.model}`}
              className="card animate-fade-up px-5 py-5"
              style={{ animationDelay: `${320 + index * 40}ms` }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2.5">
                    <ProviderMark
                      provider={getProviderForModel(entry.model)}
                      size={16}
                      className="flex-shrink-0"
                    />
                    <div className="truncate text-base font-medium text-text">
                      {MODEL_LABELS[entry.model] || entry.model}
                    </div>
                  </div>
                </div>
                <div
                  className="rounded-full border border-border px-3 py-1 text-[10px] font-medium uppercase tracking-[0.14em]"
                  style={{
                    color: matches
                      ? getPredictionTextColor(0, 1)
                      : getPredictionTextColor(entry.error, entry.groundTruth),
                  }}
                >
                  {valueLabel}
                </div>
              </div>

              <p className="mt-4 text-sm leading-relaxed text-text-secondary">
                {entry.explanation}
              </p>
            </div>
          );
        })}
        </div>
      ) : (
        <div
          className="card mt-6 px-5 py-5 text-sm text-text-secondary animate-fade-up"
          style={{ animationDelay: "320ms" }}
        >
          No explanation text was returned for this scenario and output in the
          diagnostic run.
        </div>
      )}

      {omittedModels.length > 0 && (
        <div
          className="mt-6 animate-fade-up text-sm text-text-secondary"
          style={{ animationDelay: "520ms" }}
        >
          No explanation text was returned for{" "}
          {omittedModels.map((model) => MODEL_LABELS[model] || model).join(", ")}.
        </div>
      )}
    </div>
  );
}
