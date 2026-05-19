import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  getVariableLabel,
  isBinaryVariable,
  type BenchData,
  type CountryCode,
  type ScenarioPrediction,
} from "../types";
import { formatCurrency } from "../format";
import {
  MODEL_LABELS,
  MODEL_ORDER,
  PROVIDER_LABELS,
  getProviderForModel,
  getPredictionTextColor,
  isFrontierModel,
  type ProviderKey,
} from "../modelMeta";
import ProviderMark from "./ProviderMark";

function formatBoolean(value: number): string {
  return value === 1 ? "Yes" : "No";
}

const FAILURE_SOURCE_LABELS: Record<string, string> = {
  llm_error: "LLM",
};

function formatFailureLabel(value?: string): string | null {
  if (!value) return null;
  return FAILURE_SOURCE_LABELS[value] ?? value.replaceAll("_", " ");
}

function isPredictionCorrect(
  pred: ScenarioPrediction,
  truth: number,
  isBinary: boolean,
): boolean {
  if (pred.prediction === null) return false;
  if (pred.score !== undefined) return pred.score >= 100;
  if (isBinary) return Math.round(pred.prediction) === Math.round(truth);
  return (
    Math.abs(pred.prediction - truth) <= Math.abs(truth) * 0.1 ||
    (truth === 0 && Math.abs(pred.prediction) <= 1)
  );
}

function describeError(
  pred: ScenarioPrediction,
  truth: number,
  isBinary: boolean,
  currencySymbol: "$" | "£",
): string {
  if (pred.prediction === null) return "no parseable prediction";
  if (isBinary) {
    return Math.round(pred.prediction) === Math.round(truth)
      ? "matched"
      : `predicted "${formatBoolean(Math.round(pred.prediction))}" instead of "${formatBoolean(Math.round(truth))}"`;
  }
  const error = pred.prediction - truth;
  const sign = error > 0 ? "over" : "under";
  const abs = Math.abs(error);
  if (truth === 0) {
    return `${formatCurrency(abs, currencySymbol)} ${sign} a reference of $0`;
  }
  const pct = Math.round((Math.abs(error) / Math.abs(truth)) * 100);
  return `${formatCurrency(abs, currencySymbol)} ${sign} (${pct}% off)`;
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

  const [selectedScenario, setSelectedScenario] = useState<string | null>(null);

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

  // Scenarios always show every benchmark output for the active household.
  // The leaderboard's Options panel filters the *rankings* by program, but
  // the scenario explorer is the place to inspect any cell — so the filter
  // doesn't propagate here.
  const variables = useMemo(
    () => Object.keys(predictions).sort(),
    [predictions],
  );
  const filteredPredictions = predictions;

  // Frontier-only narrows to one flagship per provider; provider chips
  // multi-select. The scenario explorer table is wide (one column per model),
  // so these filters live here rather than on the leaderboard.
  const [frontierOnly, setFrontierOnly] = useState(true);
  const [providerFilter, setProviderFilter] = useState<Set<ProviderKey>>(
    () => new Set(),
  );

  const allModels = useMemo(() => {
    const unique = new Set<string>();
    for (const varData of Object.values(filteredPredictions)) {
      for (const m of Object.keys(varData)) unique.add(m);
    }
    return MODEL_ORDER.filter((m) => unique.has(m));
  }, [filteredPredictions]);

  const models = useMemo(() => {
    return allModels.filter((m) => {
      if (frontierOnly && !isFrontierModel(m)) return false;
      if (providerFilter.size > 0) {
        const provider = getProviderForModel(m);
        if (!provider || !providerFilter.has(provider)) return false;
      }
      return true;
    });
  }, [allModels, frontierOnly, providerFilter]);

  // The detail modal opens on click. Selection is scoped to the current
  // scenario so switching households doesn't carry the old cell over.
  const [manualSelection, setManualSelection] = useState<{
    scenarioId: string;
    cell: { variable: string; model: string };
  } | null>(null);

  const selectedCell =
    manualSelection &&
    manualSelection.scenarioId === resolvedScenarioId &&
    variables.includes(manualSelection.cell.variable)
      ? manualSelection.cell
      : null;

  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const householdDialogRef = useRef<HTMLDialogElement | null>(null);
  const [householdModalOpen, setHouseholdModalOpen] = useState(false);

  // Drive the native <dialog> imperatively. showModal() gives us focus
  // trapping, an inert background, ESC-to-close, and the ::backdrop
  // pseudo-element for free; we just need to mirror our React state.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (selectedCell) {
      if (!dialog.open) dialog.showModal();
    } else if (dialog.open) {
      dialog.close();
    }
  }, [selectedCell]);

  useEffect(() => {
    const dialog = householdDialogRef.current;
    if (!dialog) return;
    if (householdModalOpen) {
      if (!dialog.open) dialog.showModal();
    } else if (dialog.open) {
      dialog.close();
    }
  }, [householdModalOpen]);

  // The household-facts modal is reactive to the active scenario via its
  // factsText prop, so picking a different household from the dropdown
  // updates the modal in place rather than needing an explicit reset.

  const closeModal = () => setManualSelection(null);
  const closeHouseholdModal = () => setHouseholdModalOpen(false);

  const setSelectedCell = (cell: { variable: string; model: string }) => {
    if (!resolvedScenarioId) return;
    setManualSelection({ scenarioId: resolvedScenarioId, cell });
  };

  if (!scenario || !resolvedScenarioId) return null;

  const activePrompt = scenario.prompt;
  const geographyLabel = country === "uk" ? "Region" : "State";
  const hasFilingStatus = !!scenario.filingStatus;
  const currencySymbol = country === "uk" ? "£" : "$";

  // The prompt always opens with "Household:" and ends the facts section
  // before "Provide the following". Pull that block so the household-facts
  // modal can show ages, individual incomes, assets, etc. without surfacing
  // the prompt scaffolding.
  const householdFactsText = (() => {
    const promptText = activePrompt?.tool ?? activePrompt?.json ?? "";
    const match = promptText.match(
      /Household:[\s\S]*?(?=\n\nProvide the following|\nProvide the following|$)/,
    );
    return match ? match[0].trim() : promptText.trim();
  })();
  const hasHouseholdFacts = householdFactsText.length > 0;
  const explanationRows = Object.values(filteredPredictions).reduce(
    (sum, modelMap) =>
      sum +
      Object.values(modelMap).filter((entry) => !!entry.explanation).length,
    0,
  );
  const annotationRows = Object.values(filteredPredictions).reduce(
    (sum, modelMap) =>
      sum +
      Object.values(modelMap).filter((entry) => !!entry.annotation).length,
    0,
  );
  const failureSources = Object.values(filteredPredictions).reduce<
    Record<string, number>
  >(
    (counts, modelMap) => {
      for (const entry of Object.values(modelMap)) {
        if (!entry.failureSource) continue;
        counts[entry.failureSource] = (counts[entry.failureSource] ?? 0) + 1;
      }
      return counts;
    },
    {},
  );
  const caseAnnotationRows = Object.values(filteredPredictions).reduce(
    (sum, modelMap) =>
      sum +
      Object.values(modelMap).filter((entry) => !!entry.caseAnnotation).length,
    0,
  );
  const totalPredictionRows = Object.values(filteredPredictions).reduce(
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
        Inspect benchmark households, reference outputs, model answers, and the
        exact prompt sent to every model.
      </p>

      <div className="mt-8 flex flex-wrap items-end gap-4">
        <div className="min-w-0 flex-1">
          <label
            htmlFor="scenario-select"
            className="block text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium mb-1.5"
          >
            Household
          </label>
          <div className="flex items-center gap-2">
            <select
              id="scenario-select"
              value={resolvedScenarioId}
              onChange={(e) => setSelectedScenario(e.target.value)}
              className="min-w-0 flex-1 bg-surface border border-border text-text text-sm rounded-lg px-3 py-2 focus:border-primary-strong/60 font-[family-name:var(--font-mono)]"
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
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border bg-surface text-text-secondary transition-colors hover:border-primary-strong/50 hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
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
      </div>

      <button
        type="button"
        onClick={() => hasHouseholdFacts && setHouseholdModalOpen(true)}
        disabled={!hasHouseholdFacts}
        className="card px-5 py-4 mt-6 w-full text-left animate-fade-up transition-colors hover:border-primary-strong/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-strong/40 disabled:cursor-default disabled:hover:border-border"
        style={{ animationDelay: "240ms" }}
        aria-label={
          hasHouseholdFacts
            ? "View full household facts"
            : "Household summary"
        }
      >
        <div
          className={`grid grid-cols-2 gap-4 ${
            hasFilingStatus ? "md:grid-cols-5" : "md:grid-cols-4"
          }`}
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
        {hasHouseholdFacts && (
          <div className="mt-3 flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
            <svg
              aria-hidden
              viewBox="0 0 12 12"
              width="10"
              height="10"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="4 2 8 6 4 10" />
            </svg>
            <span>View full household facts</span>
          </div>
        )}
      </button>

      <div
        className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-3 animate-fade-up"
        style={{ animationDelay: "300ms" }}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span
            id="scenarios-filter-label"
            className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted"
          >
            Show
          </span>
          <button
            type="button"
            onClick={() => setFrontierOnly((v) => !v)}
            aria-pressed={frontierOnly}
            className={`rounded-full border px-3 py-1 text-[11px] font-medium transition-colors ${
              frontierOnly
                ? "border-primary-strong bg-primary-strong text-white"
                : "border-border bg-card text-text-secondary hover:text-text"
            }`}
            title="Show only one frontier flagship per provider (Opus 4.7, GPT-5.5, Grok 4.3, Gemini 3.1 Pro Preview)"
          >
            Frontier only
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span
            id="scenarios-provider-label"
            className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted"
          >
            Provider
          </span>
          <div
            role="group"
            aria-labelledby="scenarios-provider-label"
            className="inline-flex flex-wrap items-center gap-1"
          >
            {(Object.keys(PROVIDER_LABELS) as ProviderKey[]).map((provider) => {
              const isActive = providerFilter.has(provider);
              return (
                <button
                  key={provider}
                  type="button"
                  onClick={() => {
                    setProviderFilter((prev) => {
                      const next = new Set(prev);
                      if (next.has(provider)) next.delete(provider);
                      else next.add(provider);
                      return next;
                    });
                  }}
                  aria-pressed={isActive}
                  className={`rounded-full border px-3 py-1 text-[11px] font-medium transition-colors ${
                    isActive
                      ? "border-primary-strong bg-primary-soft text-primary-strong"
                      : "border-border bg-card text-text-secondary hover:text-text"
                  }`}
                >
                  {PROVIDER_LABELS[provider]}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div
        className="relative mt-3 overflow-x-auto animate-fade-up"
        style={{ animationDelay: "320ms" }}
      >
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-bg text-left text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium pb-3 pl-3 pr-4 w-44 border-r border-border-subtle">
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
                  <td className="sticky left-0 z-10 bg-bg py-2.5 pl-3 pr-4 text-sm text-text-secondary border-r border-border-subtle">
                    {getVariableLabel(v, country)}
                  </td>
                  <td className="py-2.5 px-3 text-right font-[family-name:var(--font-mono)] text-sm text-text align-top">
                    {/* Mirror the button padding (px-1.5 py-0.5) used in
                        model cells so the Reference numerals share the same
                        offset from the cell edge. */}
                    <span className="inline-block px-1.5 py-0.5">
                      {isBinary
                        ? formatBoolean(truth)
                        : formatCurrency(truth, currencySymbol)}
                    </span>
                  </td>
                  {models.map((m) => {
                    const pred = varData[m];
                    const isSelected =
                      selectedCell?.variable === v &&
                      selectedCell?.model === m;
                    if (!pred || pred.prediction === null) {
                      return (
                        <td
                          key={m}
                          className={`py-2.5 px-3 text-right text-text-muted text-sm align-top`}
                        >
                          <button
                            type="button"
                            onClick={() =>
                              setSelectedCell({ variable: v, model: m })
                            }
                            aria-pressed={isSelected}
                            className={`w-full rounded-md border px-2 py-1 text-right font-[family-name:var(--font-mono)] shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-strong/40 ${
                              isSelected
                                ? "border-primary-strong/50 bg-primary-soft text-primary-strong"
                                : "border-border-subtle bg-card/60 hover:border-primary-strong/40 hover:bg-surface-soft hover:text-text"
                            }`}
                          >
                            --
                          </button>
                        </td>
                      );
                    }

                    const displayPred = isBinary
                      ? formatBoolean(Math.round(pred.prediction))
                      : formatCurrency(pred.prediction, currencySymbol);
                    const predictionError = pred.error ?? pred.prediction - truth;
                    const correct = isPredictionCorrect(pred, truth, isBinary);

                    return (
                      <td
                        key={m}
                        className="py-2.5 px-3 text-right text-sm align-top"
                      >
                        <button
                          type="button"
                          onClick={() =>
                            setSelectedCell({ variable: v, model: m })
                          }
                          aria-pressed={isSelected}
                          className={`w-full rounded-md border px-2 py-1 text-right font-[family-name:var(--font-mono)] shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-strong/40 ${
                            isSelected
                              ? "border-primary-strong/50 bg-primary-soft ring-1 ring-primary-strong/40"
                              : "border-border-subtle bg-card/60 hover:border-primary-strong/40 hover:bg-surface-soft"
                          }`}
                          style={{
                            color: correct
                              ? getPredictionTextColor(0, 1)
                              : getPredictionTextColor(predictionError, truth),
                          }}
                        >
                          {displayPred}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {totalPredictionRows > 0 && (
        <div
          className="card px-5 py-4 mt-6 animate-fade-up"
          style={{ animationDelay: "340ms" }}
        >
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
            Explanation and audit coverage
          </div>
          <p className="mt-2 text-sm text-text-secondary leading-relaxed">
            {explanationRows} of {totalPredictionRows} model-output rows for
            this household include explanation text returned by the model.{" "}
            {annotationRows} rows include developer audit notes for incorrect
            predictions, and {caseAnnotationRows} incorrect rows include
            case-level notes comparing wrong models on the same
            household-output target.
          </p>
          {Object.keys(failureSources).length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(failureSources)
                .sort((a, b) => b[1] - a[1])
                .map(([source, count]) => (
                  <span
                    key={source}
                    className="rounded-full border border-border-subtle bg-surface px-2.5 py-1 text-[11px] text-text-secondary"
                  >
                    {formatFailureLabel(source)}: {count}
                  </span>
                ))}
            </div>
          )}
        </div>
      )}

      {activePrompt && (
        <details
          className="card px-5 py-4 mt-4 animate-fade-up group"
          style={{ animationDelay: "360ms" }}
        >
          <summary className="cursor-pointer list-none flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-start gap-2">
              <span
                aria-hidden
                className="mt-0.5 inline-block text-text-muted transition-transform group-open:rotate-90"
              >
                ▸
              </span>
              <div>
                <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
                  Exact prompt
                </div>
                <div className="text-text text-sm mt-1">
                  Full household batch contract for all benchmark outputs
                </div>
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

      <DetailDialog
        ref={dialogRef}
        selectedCell={selectedCell}
        predictions={filteredPredictions}
        country={country}
        currencySymbol={currencySymbol}
        onClose={closeModal}
      />

      <HouseholdDialog
        ref={householdDialogRef}
        scenarioLabel={resolvedScenarioId.replace("scenario_", "#")}
        factsText={householdFactsText}
        onClose={closeHouseholdModal}
      />
    </div>
  );
}

type HouseholdDialogProps = {
  scenarioLabel: string;
  factsText: string;
  onClose: () => void;
};

const HouseholdDialog = React.forwardRef<HTMLDialogElement, HouseholdDialogProps>(
  function HouseholdDialog({ scenarioLabel, factsText, onClose }, ref) {
    const handleBackdropClick = (
      event: React.MouseEvent<HTMLDialogElement>,
    ) => {
      if (event.target === event.currentTarget) onClose();
    };

    return (
      <dialog
        ref={ref}
        onClose={onClose}
        onClick={handleBackdropClick}
        aria-label="Full household facts"
        className="mx-auto my-auto w-[min(960px,calc(100vw-2rem))] max-h-[calc(100vh-3rem)] overflow-y-auto rounded-2xl border border-border bg-card p-0 text-text shadow-xl backdrop:bg-text/40 backdrop:backdrop-blur-sm"
      >
        <div className="relative px-5 py-5">
          <DialogCloseButton onClose={onClose} />
          <div className="pr-10">
            <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
              Household {scenarioLabel}
            </div>
            <div className="text-text text-base font-semibold mt-0.5">
              Full household facts
            </div>
            <p className="mt-2 text-xs text-text-muted leading-relaxed">
              Exactly the household section the models see at the top of the
              prompt — verbatim, no summarization.
            </p>
          </div>
          {factsText ? (
            <pre className="mt-4 whitespace-pre-wrap rounded-lg border border-border-subtle bg-surface px-4 py-3 text-xs leading-relaxed text-text-secondary font-[family-name:var(--font-mono)]">
              {factsText}
            </pre>
          ) : (
            <p className="mt-4 text-sm text-text-muted italic">
              No prompt facts available for this household.
            </p>
          )}
        </div>
      </dialog>
    );
  },
);

type DetailDialogProps = {
  selectedCell: { variable: string; model: string } | null;
  predictions: Record<string, Record<string, ScenarioPrediction>>;
  country: CountryCode;
  currencySymbol: "$" | "£";
  onClose: () => void;
};

const DetailDialog = React.forwardRef<HTMLDialogElement, DetailDialogProps>(
  function DetailDialog(
    { selectedCell, predictions, country, currencySymbol, onClose },
    ref,
  ) {
    // Backdrop click: native <dialog> reports the click target as the dialog
    // element itself when the user clicks the backdrop pseudo-element, so we
    // can dismiss without an explicit overlay element.
    const handleBackdropClick = (
      event: React.MouseEvent<HTMLDialogElement>,
    ) => {
      if (event.target === event.currentTarget) onClose();
    };

    return (
      <dialog
        ref={ref}
        onClose={onClose}
        onClick={handleBackdropClick}
        aria-label="Selected prediction detail"
        className="mx-auto my-auto w-[min(960px,calc(100vw-2rem))] max-h-[calc(100vh-3rem)] overflow-y-auto rounded-2xl border border-border bg-card p-0 text-text shadow-xl backdrop:bg-text/40 backdrop:backdrop-blur-sm"
      >
        {selectedCell ? (
          <DetailContent
            selectedCell={selectedCell}
            predictions={predictions}
            country={country}
            currencySymbol={currencySymbol}
            onClose={onClose}
          />
        ) : null}
      </dialog>
    );
  },
);

type DetailContentProps = {
  selectedCell: { variable: string; model: string };
  predictions: Record<string, Record<string, ScenarioPrediction>>;
  country: CountryCode;
  currencySymbol: "$" | "£";
  onClose: () => void;
};

function DetailContent({
  selectedCell,
  predictions,
  country,
  currencySymbol,
  onClose,
}: DetailContentProps) {
  const { variable, model } = selectedCell;
  const pred = predictions[variable]?.[model];
  if (!pred) {
    return (
      <div className="relative px-5 py-6">
        <DialogCloseButton onClose={onClose} />
        <p className="text-sm text-text-secondary">
          No data for {MODEL_LABELS[model] ?? model} on{" "}
          {getVariableLabel(variable, country)}.
        </p>
      </div>
    );
  }

  const isBinary = isBinaryVariable(variable, country);
  const truth = pred.groundTruth;
  const correct = isPredictionCorrect(pred, truth, isBinary);
  const displayTruth = isBinary
    ? formatBoolean(Math.round(truth))
    : formatCurrency(truth, currencySymbol);
  const displayPred =
    pred.prediction === null
      ? "—"
      : isBinary
        ? formatBoolean(Math.round(pred.prediction))
        : formatCurrency(pred.prediction, currencySymbol);
  const errorDescription = describeError(
    pred,
    truth,
    isBinary,
    currencySymbol,
  );
  const auditTags = [
    formatFailureLabel(pred.failureSource),
    pred.failureSubtype ? pred.failureSubtype.replaceAll("_", " ") : null,
  ].filter(Boolean) as string[];

  return (
    <div className="relative px-5 py-5">
      <DialogCloseButton onClose={onClose} />
      <div className="flex flex-wrap items-baseline justify-between gap-3 pr-10">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
            {getVariableLabel(variable, country)}
          </div>
          <div className="text-text text-base font-semibold mt-0.5 flex items-center gap-2">
            <ProviderMark
              provider={getProviderForModel(model)}
              size={14}
              className="flex-shrink-0"
            />
            {MODEL_LABELS[model] ?? model}
          </div>
        </div>
        <span
          className={`rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider ${
            correct
              ? "border-success/30 bg-success-soft text-success-text"
              : "border-danger/30 bg-danger-soft text-danger-text"
          }`}
        >
          {correct ? "Correct" : "Off"}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
            Reference
          </div>
          <div className="font-[family-name:var(--font-mono)] text-lg mt-1 text-text">
            {displayTruth}
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
            Prediction
          </div>
          <div className="font-[family-name:var(--font-mono)] text-lg mt-1 text-text">
            {displayPred}
          </div>
        </div>
        {!correct && (
          <div className="col-span-2 sm:col-span-1">
            <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
              Error
            </div>
            <div className="text-sm mt-1 text-text-secondary">
              {errorDescription}
            </div>
          </div>
        )}
      </div>

      <div className="mt-5 grid gap-5 md:grid-cols-2">
        <section>
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
            PolicyEngine derivation
          </div>
          {pred.referenceExplanation ? (
            <p className="mt-2 text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">
              {pred.referenceExplanation}
            </p>
          ) : (
            <p className="mt-2 text-sm text-text-muted italic">
              Reference computation narrative not yet generated for this case.
            </p>
          )}
        </section>

        <section>
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
            Model reasoning
          </div>
          {pred.explanation ? (
            <p className="mt-2 text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">
              {pred.explanation}
            </p>
          ) : (
            <p className="mt-2 text-sm text-text-muted italic">
              The model didn&apos;t return an explanation for this row.
            </p>
          )}
        </section>
      </div>

      {(pred.annotation || auditTags.length > 0 || !correct) && (
        <section className="mt-5 border-t border-border-subtle pt-4">
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
            Audit tags
          </div>
          {pred.annotation ? (
            <p className="mt-2 text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">
              {pred.annotation}
            </p>
          ) : correct ? null : (
            <p className="mt-2 text-sm text-text-muted italic">
              Not yet reviewed.
            </p>
          )}
          {auditTags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {auditTags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-full border border-border-subtle bg-surface px-2 py-0.5 text-[10px] uppercase tracking-wider text-text-muted"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </section>
      )}

    </div>
  );
}

function DialogCloseButton({ onClose }: { onClose: () => void }) {
  return (
    <button
      type="button"
      onClick={onClose}
      aria-label="Close detail"
      className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-full border border-border bg-surface text-text-secondary transition-colors hover:border-primary-strong/50 hover:text-text"
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 16 16"
        width="12"
        height="12"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M4 4l8 8M12 4l-8 8" />
      </svg>
    </button>
  );
}
