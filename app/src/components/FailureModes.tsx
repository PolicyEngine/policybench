import { useMemo } from "react";
import type {
  BenchData,
  FailureModesPayload,
  HeatmapEntry,
  ProgramFailure,
} from "../types";
import { getVariableLabel } from "../types";
import { getVariableExplainer } from "../variableExplainers";

function formatPct(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "n/a";
  return `${value.toFixed(1)}%`;
}

function getHeatmapScore(entry: HeatmapEntry): number {
  return entry.score ?? entry.within10pct ?? entry.accuracy ?? 0;
}

function StatLine({
  label,
  value,
}: {
  label: string;
  value?: number | null;
}) {
  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <span className="text-text-muted">{label}</span>
      <span className="text-text font-[family-name:var(--font-mono)]">
        {formatPct(value)}
      </span>
    </div>
  );
}

function ProgramCard({
  program,
  country,
}: {
  program: ProgramFailure;
  country: BenchData["country"];
}) {
  return (
    <div className="card px-5 py-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
            {program.isBinary ? "Household boolean" : "Dollar target"}
          </div>
          <div className="mt-1 text-text text-base font-medium">
            {getVariableLabel(program.variable, country)}
          </div>
        </div>
        <div className="rounded-full border border-border bg-surface px-3 py-1 text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
          Overall {formatPct(program.overallCorrectPct)}
        </div>
      </div>

      <div className="mt-4 space-y-2.5">
        <StatLine
          label={program.isBinary ? "Positive households" : "Positive-amount cases"}
          value={program.positiveCasePct}
        />
        <StatLine
          label={program.isBinary ? "Negative households" : "Zero-amount cases"}
          value={program.zeroCasePct}
        />
        <StatLine label="With children" value={program.withChildrenPct} />
        <StatLine label="Low income" value={program.lowIncomePct} />
        <StatLine label="High income" value={program.highIncomePct} />
        {!program.isBinary && (
          <StatLine
            label="Underpredict share on positives"
            value={program.underpredictSharePositivePct}
          />
        )}
      </div>
    </div>
  );
}

function ErrorReadPatterns({
  data,
  variables,
}: {
  data: BenchData;
  variables: string[];
}) {
  const averageScores = useMemo(() => {
    const valuesByVariable: Record<string, number[]> = {};
    for (const entry of data.heatmap) {
      if (entry.condition !== "no_tools" || !variables.includes(entry.variable)) {
        continue;
      }
      if (!valuesByVariable[entry.variable]) valuesByVariable[entry.variable] = [];
      valuesByVariable[entry.variable].push(getHeatmapScore(entry));
    }
    return Object.fromEntries(
      Object.entries(valuesByVariable).map(([variable, values]) => [
        variable,
        values.reduce((sum, value) => sum + value, 0) / values.length,
      ]),
    );
  }, [data.heatmap, variables]);

  return (
    <div className="mt-10">
      <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
        What the error reads show
      </div>
      <p className="mt-3 max-w-3xl text-sm leading-relaxed text-text-secondary">
        These expanders summarize recurring miss patterns from direct reads of
        model answers and explanations. They sit here with failure modes because
        they describe why the low-scoring program slices break.
      </p>

      <div className="mt-5 space-y-3">
        {variables.map((variable) => {
          const explainer = getVariableExplainer(data.country, variable);
          const avg = averageScores[variable];
          return (
            <details
              key={variable}
              className="card px-5 py-4 open:border-primary/30 group"
            >
              <summary className="flex cursor-pointer list-none items-start justify-between gap-4">
                <div className="min-w-0 flex items-start gap-2">
                  <span
                    aria-hidden
                    className="mt-0.5 inline-block text-text-muted transition-transform group-open:rotate-90"
                  >
                    ▸
                  </span>
                  <div className="min-w-0">
                    <div className="text-text text-sm font-medium">
                      {getVariableLabel(variable, data.country)}
                    </div>
                    <p className="mt-1 text-sm leading-relaxed text-text-secondary">
                      {explainer?.summary ??
                        "This target combines multiple policy rules, and errors usually come from positive cases rather than zero cases."}
                    </p>
                  </div>
                </div>
                {avg !== undefined && (
                  <div className="shrink-0 rounded-full border border-border bg-surface px-3 py-1 text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
                    Avg {avg.toFixed(0)}%
                  </div>
                )}
              </summary>

              <div className="mt-4 border-t border-border-subtle pt-4">
                <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
                  Common misses
                </div>
                <ul className="mt-3 space-y-2 text-sm leading-relaxed text-text-secondary">
                  {(explainer?.bullets ?? []).map((bullet) => (
                    <li key={bullet} className="flex gap-2">
                      <span className="mt-[0.45rem] h-1.5 w-1.5 shrink-0 rounded-full bg-primary/70" />
                      <span>{bullet}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </details>
          );
        })}
      </div>
    </div>
  );
}

export default function FailureModes({ data }: { data: BenchData }) {
  const country = data.country;
  const failureModes: FailureModesPayload = data.failureModes;
  const hardestPrograms = [...failureModes.programs].slice(0, 10);
  const errorReadVariables = hardestPrograms.map((program) => program.variable);

  return (
    <div>
      <div className="eyebrow mb-3 animate-fade-up">Failure modes</div>
      <h2
        className="font-[family-name:var(--font-display)] text-4xl md:text-5xl text-text tracking-tight animate-fade-up"
        style={{ animationDelay: "80ms" }}
      >
        Where models still break
      </h2>
      <p
        className="text-text-secondary mt-3 max-w-3xl leading-relaxed animate-fade-up"
        style={{ animationDelay: "160ms" }}
      >
        The hardest part of PolicyBench is not saying when a program is zero. It is
        getting the positive amount right for the households that actually qualify.
        The cards below split those cases apart so the benchmark is not flattered by
        easy zero-answer rows.
      </p>

      <div
        className="card px-5 py-5 mt-8 border-warning/20 bg-warning-soft/30 animate-fade-up"
        style={{ animationDelay: "240ms" }}
      >
        <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
          How to read these cards
        </div>
        <p className="mt-3 text-sm leading-relaxed text-text-secondary">
          These cards are intentionally stricter than the aggregate leaderboard but
          still use <span className="text-text">within-10% accuracy</span> for
          dollar-valued programs so positive cases stay interpretable.
          <span className="text-text"> Positive-amount cases</span> is the
          harder and more informative number for benefits and refundable
          credits. For binary coverage flags, the cards compare positive and
          negative class accuracy.
        </p>
      </div>

      <div className="mt-8 grid lg:grid-cols-2 gap-4">
        {hardestPrograms.map((program, index) => (
          <div
            key={program.variable}
            className="animate-fade-up"
            style={{ animationDelay: `${300 + index * 40}ms` }}
          >
            <ProgramCard program={program} country={country} />
          </div>
        ))}
      </div>

      <ErrorReadPatterns data={data} variables={errorReadVariables} />
    </div>
  );
}
