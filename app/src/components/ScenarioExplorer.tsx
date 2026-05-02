import { useMemo, useState } from "react";
import { getVariableLabel, isBinaryVariable, type BenchData } from "../types";
import { formatCurrency } from "../format";
import {
  MODEL_LABELS,
  MODEL_ORDER,
  getProviderForModel,
  getPredictionTextColor,
} from "../modelMeta";
import ExplanationTooltip from "./ExplanationTooltip";
import ProviderMark from "./ProviderMark";

function formatBoolean(value: number): string {
  return value === 1 ? "Yes" : "No";
}

function pickRandomScenario(
  scenarioIds: string[],
  exclude?: string | null,
): string | null {
  if (scenarioIds.length === 0) return null;
  if (scenarioIds.length === 1) return scenarioIds[0];

  const candidates = exclude
    ? scenarioIds.filter((scenarioId) => scenarioId !== exclude)
    : scenarioIds;

  if (candidates.length === 0) return scenarioIds[0];

  return candidates[Math.floor(Math.random() * candidates.length)];
}

export default function ScenarioExplorer({
  data,
}: {
  data: BenchData;
}) {
  const country = data.country;
  const [promptFormat, setPromptFormat] = useState<"tool" | "json">("tool");

  const scenarioIds = useMemo(
    () => Object.keys(data.scenarios).sort(),
    [data],
  );

  const [selectedScenario, setSelectedScenario] = useState<string | null>(() =>
    pickRandomScenario(scenarioIds),
  );

  const resolvedScenarioId =
    selectedScenario && data.scenarios[selectedScenario]
      ? selectedScenario
      : scenarioIds[0] ?? null;
  const scenario = resolvedScenarioId ? data.scenarios[resolvedScenarioId] : null;

  const predictions = useMemo(
    () =>
      resolvedScenarioId
        ? (data.scenarioPredictions[resolvedScenarioId] ?? {})
        : {},
    [data, resolvedScenarioId],
  );

  const variables = useMemo(() => Object.keys(predictions).sort(), [predictions]);

  const models = useMemo(() => {
    const unique = new Set<string>();
    for (const varData of Object.values(predictions)) {
      for (const m of Object.keys(varData)) unique.add(m);
    }
    return MODEL_ORDER.filter((m) => unique.has(m));
  }, [predictions]);

  if (!scenario || !resolvedScenarioId) return null;

  const activePrompt = scenario.prompt;
  const geographyLabel = country === "uk" ? "Region" : "State";
  const hasFilingStatus = !!scenario.filingStatus;
  const currencySymbol = country === "uk" ? "£" : "$";
  const explanationRows = Object.values(predictions).reduce(
    (sum, modelMap) =>
      sum +
      Object.values(modelMap).filter((entry) => !!entry.explanation).length,
    0,
  );
  const totalPredictionRows = Object.values(predictions).reduce(
    (sum, modelMap) => sum + Object.keys(modelMap).length,
    0,
  );

  const handleShuffle = () => {
    const nextScenario = pickRandomScenario(scenarioIds, resolvedScenarioId);
    if (nextScenario) setSelectedScenario(nextScenario);
  };

  return (
    <div>
      <div className="eyebrow mb-3 animate-fade-up">Deep dive</div>
      <h2
        className="font-[family-name:var(--font-display)] text-4xl md:text-5xl text-text tracking-tight animate-fade-up"
        style={{ animationDelay: "80ms" }}
      >
        Scenario explorer
      </h2>
      <p
        className="text-text-secondary mt-3 max-w-2xl leading-relaxed animate-fade-up"
        style={{ animationDelay: "160ms" }}
      >
        Inspect benchmark households, the exact prompt, model outputs, and the
        model-provided explanation notes returned with each response.
      </p>

      <div className="mt-8 flex flex-wrap items-end gap-4">
        <div className="min-w-0 flex-1">
          <label className="block text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium mb-1.5">
            Household
          </label>
          <div className="flex items-center gap-2">
            <select
              value={resolvedScenarioId}
              onChange={(e) => setSelectedScenario(e.target.value)}
              className="min-w-0 flex-1 bg-surface border border-border text-text text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-primary/50 font-[family-name:var(--font-mono)]"
            >
              {scenarioIds.map((id) => {
                const s = data.scenarios[id];
                return (
                  <option key={id} value={id}>
                    {id.replace("scenario_", "#")} &mdash; {s.state}
                    {s.filingStatus ? `, ${s.filingStatus}` : ""},{" "}
                    {formatCurrency(Number(s.totalIncome), currencySymbol)}
                  </option>
                );
              })}
            </select>
            <button
              type="button"
              onClick={handleShuffle}
              disabled={scenarioIds.length < 2}
              aria-label="Shuffle household"
              title="Shuffle household"
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
              <span className="sr-only">Shuffle household</span>
            </button>
          </div>
        </div>
      </div>

      <div
        className={`card px-5 py-4 mt-6 grid grid-cols-2 gap-4 animate-fade-up ${
          hasFilingStatus ? "md:grid-cols-5" : "md:grid-cols-4"
        }`}
        style={{ animationDelay: "240ms" }}
      >
        {[
          [geographyLabel, scenario.state],
          ...(hasFilingStatus
            ? [["Filing status", scenario.filingStatus as string]]
            : []),
          ["Adults", String(scenario.numAdults)],
          ["Children", String(scenario.numChildren)],
          [
            "Income",
            formatCurrency(scenario.totalIncome as number, currencySymbol),
          ],
        ].map(([label, value]) => (
          <div key={label}>
            <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
              {label}
            </div>
            <div className="text-text font-[family-name:var(--font-mono)] text-sm mt-0.5">
              {value}
            </div>
          </div>
        ))}
      </div>

      {totalPredictionRows > 0 && (
        <div
          className="card px-5 py-4 mt-4 animate-fade-up"
          style={{ animationDelay: "260ms" }}
        >
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
            Explanation coverage
          </div>
          <p className="mt-2 text-sm text-text-secondary leading-relaxed">
            {explanationRows} of {totalPredictionRows} model-output rows for
            this household include explanation text. These notes are returned
            by the model and are not separately scored; hover the note markers
            next to predictions to read them.
          </p>
        </div>
      )}

      {activePrompt && (
        <details
          className="card px-5 py-4 mt-6 animate-fade-up"
          style={{ animationDelay: "280ms" }}
        >
          <summary className="cursor-pointer list-none flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
                Exact prompt
              </div>
              <div className="text-text text-sm mt-1">
                Full household batch contract for all benchmark outputs
              </div>
            </div>
            <div className="text-text-muted text-xs">
              Provider-specific structured-output transport, no external tool
            </div>
          </summary>

          <div className="mt-4">
            <div className="flex flex-wrap gap-2 mb-3">
              <button
                type="button"
                onClick={() => setPromptFormat("tool")}
                className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${
                  promptFormat === "tool"
                    ? "border-primary bg-primary-soft text-primary"
                    : "border-border text-text-secondary hover:text-text"
                }`}
              >
                Structured schema
              </button>
              <button
                type="button"
                onClick={() => setPromptFormat("json")}
                className={`rounded-full border px-3 py-1.5 text-xs transition-colors ${
                  promptFormat === "json"
                    ? "border-primary bg-primary-soft text-primary"
                    : "border-border text-text-secondary hover:text-text"
                }`}
              >
                JSON schema
              </button>
            </div>
            <pre className="bg-surface rounded-lg border border-border-subtle p-3 text-xs text-text-secondary whitespace-pre-wrap leading-relaxed overflow-x-auto">
              {promptFormat === "tool" ? activePrompt.tool : activePrompt.json}
            </pre>
          </div>
        </details>
      )}

      <div
        className="relative mt-6 overflow-x-auto animate-fade-up"
        style={{ animationDelay: "320ms" }}
      >
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-bg text-left text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium pb-3 pr-4 w-44 border-r border-border-subtle">
                Program
              </th>
              <th className="text-right text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium pb-3 px-3 w-24">
                Reference
              </th>
              {models.map((m) => (
                <th
                  key={m}
                  className="text-right text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium pb-3 px-3 w-28"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <ProviderMark
                      provider={getProviderForModel(m)}
                      size={12}
                      className="flex-shrink-0"
                    />
                    {MODEL_LABELS[m]?.split(" ").slice(-2).join(" ")}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {variables.map((v) => {
              const varData = predictions[v] || {};
              const truth = Object.values(varData)[0]?.groundTruth ?? 0;
              const isBinary = isBinaryVariable(v, country);

              return (
                <tr key={v} className="border-t border-border-subtle">
                  <td className="sticky left-0 z-10 bg-bg py-2.5 pr-4 text-sm text-text-secondary border-r border-border-subtle">
                    {getVariableLabel(v, country)}
                  </td>
                  <td className="py-2.5 px-3 text-right font-[family-name:var(--font-mono)] text-sm text-text">
                    {isBinary
                      ? formatBoolean(truth)
                      : formatCurrency(truth, currencySymbol)}
                  </td>
                  {models.map((m) => {
                    const pred = varData[m];
                    if (!pred) {
                      return (
                        <td
                          key={m}
                          className="py-2.5 px-3 text-right text-text-muted text-sm"
                        >
                          --
                        </td>
                      );
                    }

                    const displayPred = isBinary
                      ? formatBoolean(Math.round(pred.prediction))
                      : formatCurrency(pred.prediction, currencySymbol);

                    const isCorrect = isBinary
                      ? Math.round(pred.prediction) === Math.round(truth)
                      : Math.abs(pred.error) <= Math.abs(truth) * 0.1 ||
                        (truth === 0 && Math.abs(pred.prediction) <= 1);

                    return (
                      <td
                        key={m}
                        className="py-2.5 px-3 text-right text-sm align-top"
                        style={{
                          color: isCorrect
                            ? getPredictionTextColor(0, 1)
                            : getPredictionTextColor(pred.error, truth),
                        }}
                      >
                        <div className="flex items-start justify-end gap-2">
                          <div className="font-[family-name:var(--font-mono)]">
                            {displayPred}
                          </div>
                          {pred.explanation && (
                            <ExplanationTooltip explanation={pred.explanation}>
                              note
                            </ExplanationTooltip>
                          )}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
