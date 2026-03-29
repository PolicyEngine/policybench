import {
  VARIABLE_CATEGORIES,
  getVariableLabel,
  type BenchData,
} from "../types";
import { MODEL_LABELS } from "../modelMeta";

function StatCard({
  value,
  label,
  accent,
}: {
  value: string;
  label: string;
  accent: "primary" | "warning" | "info";
}) {
  const styles = {
    primary: "text-primary border-primary/15 bg-primary-soft",
    warning: "text-warning border-warning/15 bg-warning-soft",
    info: "text-info border-info/15 bg-info-soft",
  };

  return (
    <div className={`rounded-xl border px-5 py-4 ${styles[accent]}`}>
      <div className="text-2xl font-semibold tracking-tight font-[family-name:var(--font-mono)]">
        {value}
      </div>
      <div className="mt-1.5 text-[10px] font-medium uppercase tracking-[0.14em] opacity-60">
        {label}
      </div>
    </div>
  );
}

function SectionCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card px-5 py-5">
      <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
        {title}
      </div>
      <div className="mt-3 text-sm leading-relaxed text-text-secondary">
        {children}
      </div>
    </div>
  );
}

export default function Methodology({ data }: { data: BenchData }) {
  const noToolsModels = data.modelStats.filter((m) => m.condition === "no_tools");
  const modelNames = noToolsModels.map((m) => MODEL_LABELS[m.model] || m.model);
  const variables = [...data.programStats]
    .map((program) => program.variable)
    .sort((a, b) => getVariableLabel(a).localeCompare(getVariableLabel(b)));
  const scenarioCount = Object.keys(data.scenarios).length;
  const scoredPoints =
    noToolsModels[0]?.n ?? scenarioCount * data.programStats.length;
  const hasRepeatedRuns = noToolsModels.some((model) => (model.runCount ?? 0) > 1);

  return (
    <div>
      <div className="eyebrow mb-3 animate-fade-up">Methodology</div>
      <h2
        className="font-[family-name:var(--font-display)] text-4xl md:text-5xl text-text tracking-tight animate-fade-up"
        style={{ animationDelay: "80ms" }}
      >
        How the benchmark works
      </h2>
      <p
        className="text-text-secondary mt-3 max-w-3xl leading-relaxed animate-fade-up"
        style={{ animationDelay: "160ms" }}
      >
        PolicyBench measures one thing: how well frontier models can estimate
        household-level tax and benefit outputs from the prompt alone. This
        app shows the current no-tools benchmark on a fixed test set, with
        ground truth computed by PolicyEngine-US for tax year 2025.
      </p>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-10 animate-fade-up" style={{ animationDelay: "240ms" }}>
        <StatCard
          value={`${scenarioCount}`}
          label="Enhanced CPS households"
          accent="primary"
        />
        <StatCard
          value={`${variables.length}`}
          label="Scored variables"
          accent="warning"
        />
        <StatCard
          value={`${scoredPoints.toLocaleString()}`}
          label="Model-output targets"
          accent="info"
        />
        <StatCard
          value={`${modelNames.length}`}
          label="Frontier models"
          accent="primary"
        />
      </div>

      <div className="grid lg:grid-cols-2 gap-4 mt-8">
        <SectionCard title="Task">
          Each model sees the same household description and one named policy
          variable, then must return a single numeric answer with no tool use.
          The exact provider-specific prompts are visible in the scenario
          explorer, so you can inspect the contract instead of inferring it.
        </SectionCard>

        <SectionCard title="Households">
          The benchmark samples real households from the Enhanced CPS with a
          fixed seed. To keep cases realistic and interpretable, the current
          set is restricted to households with a single tax unit, a single SPM
          unit, and a single family. Filing status, ages, children, and the
          observed wage and selected non-wage income sources are carried
          through into both the prompt and the PolicyEngine input.
        </SectionCard>

        <SectionCard title="Ground Truth">
          PolicyEngine-US computes the authoritative label for every
          household-variable pair in tax year 2025. The current scope covers
          federal adjusted gross income, federal pre-credit income tax,
          refundable federal tax credits, SNAP, SSI, household-level Medicaid eligibility,
          household-level free school meals eligibility, state AGI, state
          pre-credit income tax, state refundable credits, and final state
          income tax. The benchmark no longer scores PolicyEngine-specific
          aggregates like total benefits or household net income.
        </SectionCard>

        <SectionCard title="Scoring">
          Dollar-valued outputs are scored with mean absolute error, mean
          absolute percentage error, and share within 10% of ground truth.
          Household booleans like Medicaid and free school meals are scored
          with classification accuracy. Coverage tracks how often a model
          produced a parseable numeric answer. The leaderboard is a point
          estimate on this fixed test set
          {hasRepeatedRuns
            ? "; when repeated runs are loaded, the app also shows run-to-run stability."
            : "."}
        </SectionCard>
      </div>

      <div
        className="card px-5 py-5 mt-8 animate-fade-up"
        style={{ animationDelay: "320ms" }}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
              Current benchmark scope
            </div>
            <div className="mt-1 text-text-secondary text-sm leading-relaxed">
              Latest run in this app evaluates {modelNames.join(", ")} on{" "}
              {scoredPoints.toLocaleString()} scored outputs.
            </div>
          </div>
          <div className="text-text-muted text-xs">
            Fixed test set, no tools, tax year 2025
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mt-4">
          {variables.map((variable) => (
            <span
              key={variable}
              className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-xs text-text-secondary"
            >
              <span className="text-text">{getVariableLabel(variable)}</span>
              <span className="text-text-muted">
                {VARIABLE_CATEGORIES[variable] || "Other"}
              </span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
