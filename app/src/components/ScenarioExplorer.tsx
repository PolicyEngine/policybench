import { useState, useMemo } from "react";
import {
  getVariableLabel,
  isBinaryVariable,
  type BenchData,
  type ScenarioPredictionsByVariable,
} from "../types";
import { formatDollars } from "../format";
import {
  MODEL_COLORS,
  MODEL_LABELS,
  MODEL_ORDER,
  getPredictionTextColor,
} from "../modelMeta";

function formatBoolean(value: number): string {
  return value === 1 ? "Yes" : "No";
}

export default function ScenarioExplorer({ data }: { data: BenchData }) {
  const scenarioIds = useMemo(
    () => Object.keys(data.scenarios).sort(),
    [data]
  );
  const [selectedScenario, setSelectedScenario] = useState(scenarioIds[0]);
  const [selectedVariable, setSelectedVariable] = useState<string | null>(null);

  const scenario = data.scenarios[selectedScenario];

  const predictions = useMemo(() => {
    const rows = data.scatter.filter(
      (d) => d.scenario === selectedScenario && d.condition === "no_tools"
    );
    const byVar: ScenarioPredictionsByVariable = {};
    for (const r of rows) {
      if (!byVar[r.variable]) byVar[r.variable] = {};
      byVar[r.variable][r.model] = {
        prediction: r.prediction,
        error: r.error,
        groundTruth: r.groundTruth,
      };
    }
    return byVar;
  }, [data, selectedScenario]);

  const variables = useMemo(
    () => Object.keys(predictions).sort(),
    [predictions]
  );
  const activeVariable =
    selectedVariable && variables.includes(selectedVariable)
      ? selectedVariable
      : variables[0];
  const activePrompt =
    activeVariable != null
      ? scenario.promptByVariable?.[activeVariable]
      : undefined;

  const models = useMemo(() => {
    const unique = new Set<string>();
    for (const varData of Object.values(predictions)) {
      for (const m of Object.keys(varData)) unique.add(m);
    }
    return MODEL_ORDER.filter((m) => unique.has(m));
  }, [predictions]);

  if (!scenario) return null;

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
        className="text-text-secondary mt-3 max-w-xl leading-relaxed animate-fade-up"
        style={{ animationDelay: "160ms" }}
      >
        Select a household to see every model&apos;s prediction for each program,
        compared against PolicyEngine&apos;s ground truth.
      </p>

      {/* Controls row */}
      <div className="flex flex-wrap items-end gap-4 mt-8">
        {/* Scenario picker */}
        <div>
          <label className="block text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium mb-1.5">
            Household
          </label>
          <select
            value={selectedScenario}
            onChange={(e) => setSelectedScenario(e.target.value)}
            className="bg-surface border border-border text-text text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-primary/50 font-[family-name:var(--font-mono)]"
          >
            {scenarioIds.map((id) => {
              const s = data.scenarios[id];
              return (
                <option key={id} value={id}>
                  {id.replace("scenario_", "#")} &mdash; {s.state},{" "}
                  {s.filingStatus}, {formatDollars(Number(s.totalIncome))}
                </option>
              );
            })}
          </select>
        </div>

        <div>
          <label className="block text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium mb-1.5">
            Prompt variable
          </label>
          <select
            value={activeVariable}
            onChange={(e) => setSelectedVariable(e.target.value)}
            className="bg-surface border border-border text-text text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-primary/50"
          >
            {variables.map((variable) => (
              <option key={variable} value={variable}>
                {getVariableLabel(variable)}
              </option>
            ))}
          </select>
        </div>

      </div>

      {/* Scenario summary card */}
      <div className="card px-5 py-4 mt-6 grid grid-cols-2 md:grid-cols-5 gap-4 animate-fade-up" style={{ animationDelay: "240ms" }}>
        {[
          ["State", scenario.state],
          ["Filing status", scenario.filingStatus],
          ["Adults", String(scenario.numAdults)],
          ["Children", String(scenario.numChildren)],
          ["Income", formatDollars(scenario.totalIncome as number)],
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

      {activeVariable && activePrompt && (
        <details
          className="card px-5 py-4 mt-6 animate-fade-up"
          style={{ animationDelay: "280ms" }}
        >
          <summary className="cursor-pointer list-none flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
                Exact prompts
              </div>
              <div className="text-text text-sm mt-1">
                {getVariableLabel(activeVariable)}
              </div>
            </div>
            <div className="text-text-muted text-xs">
              GPT/Claude use function calling; Gemini uses JSON mode
            </div>
          </summary>

          <div className="grid md:grid-cols-2 gap-4 mt-4">
            <div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium mb-2">
                Function-call contract
              </div>
              <pre className="bg-surface rounded-lg border border-border-subtle p-3 text-xs text-text-secondary whitespace-pre-wrap leading-relaxed overflow-x-auto">
                {activePrompt.tool}
              </pre>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium mb-2">
                JSON contract
              </div>
              <pre className="bg-surface rounded-lg border border-border-subtle p-3 text-xs text-text-secondary whitespace-pre-wrap leading-relaxed overflow-x-auto">
                {activePrompt.json}
              </pre>
            </div>
          </div>
        </details>
      )}

      {/* Results table */}
      <div className="mt-6 overflow-x-auto animate-fade-up" style={{ animationDelay: "320ms" }}>
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="text-left text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium pb-3 pr-4 w-44">
                Program
              </th>
              <th className="text-right text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium pb-3 px-3 w-24">
                Truth
              </th>
              {models.map((m) => (
                <th
                  key={m}
                  className="text-right text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium pb-3 px-3 w-28"
                >
                  <div className="flex items-center justify-end gap-1.5">
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ backgroundColor: MODEL_COLORS[m] }}
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
              const isBinary = isBinaryVariable(v);

              return (
                <tr
                  key={v}
                  className={`border-t border-border-subtle ${
                    activeVariable === v ? "bg-primary-soft/40" : ""
                  }`}
                >
                  <td className="py-2.5 pr-4 text-sm text-text-secondary">
                    <button
                      type="button"
                      onClick={() => setSelectedVariable(v)}
                      className="text-left hover:text-text transition-colors"
                    >
                      {getVariableLabel(v)}
                    </button>
                  </td>
                  <td className="py-2.5 px-3 text-right font-[family-name:var(--font-mono)] text-sm text-text">
                    {isBinary ? formatBoolean(truth) : formatDollars(truth)}
                  </td>
                  {models.map((m) => {
                    const pred = varData[m];
                    if (!pred)
                      return (
                        <td key={m} className="py-2.5 px-3 text-right text-text-muted text-sm">
                          --
                        </td>
                      );

                    const displayPred = isBinary
                      ? formatBoolean(pred.prediction)
                      : formatDollars(pred.prediction);

                    const isCorrect = isBinary
                      ? pred.prediction === truth
                      : Math.abs(pred.error) <= Math.abs(truth) * 0.1 ||
                        (truth === 0 && pred.prediction === 0);

                    return (
                      <td
                        key={m}
                        className="py-2.5 px-3 text-right font-[family-name:var(--font-mono)] text-sm"
                        style={{
                          color: isCorrect
                            ? getPredictionTextColor(0, 1)
                            : getPredictionTextColor(pred.error, truth),
                        }}
                      >
                        {displayPred}
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
