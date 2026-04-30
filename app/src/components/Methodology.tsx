import { MODEL_LABELS } from "../modelMeta";
import {
  getVariableCategory,
  getVariableLabel,
  VIEW_LABELS,
  type BenchData,
  type GlobalBenchData,
  type ViewKey,
} from "../types";

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

export default function Methodology({
  data,
  selectedView,
}: {
  data: BenchData | GlobalBenchData;
  selectedView: ViewKey;
}) {
  const isGlobal = selectedView === "global";

  if (isGlobal) {
    const globalData = data as GlobalBenchData;
    const totalHouseholds = globalData.countrySummaries.reduce(
      (sum, country) => sum + country.households,
      0
    );
    const countryCount = globalData.countrySummaries.length;

    return (
      <div>
        <div className="eyebrow mb-3 animate-fade-up">Methodology</div>
        <h2
          className="font-[family-name:var(--font-display)] text-4xl md:text-5xl text-text tracking-tight animate-fade-up"
          style={{ animationDelay: "80ms" }}
        >
          How global scores work
        </h2>
        <p
          className="text-text-secondary mt-3 max-w-3xl leading-relaxed animate-fade-up"
          style={{ animationDelay: "160ms" }}
        >
          The global leaderboard is a shared-model aggregate, not a separate
          benchmark. Each model’s global score is the equal-weight average of
          its country-level PolicyBench scores across the included countries.
        </p>

        <div
          className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-10 animate-fade-up"
          style={{ animationDelay: "240ms" }}
        >
          <StatCard
            value={`${countryCount}`}
            label="Country benchmarks"
            accent="primary"
          />
          <StatCard
            value={`${globalData.sharedModelCount}`}
            label="Shared models"
            accent="warning"
          />
          <StatCard
            value={totalHouseholds.toLocaleString()}
            label="Total households"
            accent="info"
          />
          <StatCard value="2026" label="Tax year" accent="primary" />
        </div>

        <div className="grid lg:grid-cols-2 gap-4 mt-8">
          <SectionCard title="Aggregation">
            Only models with both country runs appear in the global table.
            Their global score is the average of the bounded country scores,
            rather than a currency-weighted or output-weighted blend.
          </SectionCard>

          <SectionCard title="Interpretation">
            This view answers a narrow question: which models travel best across
            policy systems? It does not replace the country-specific leaderboards,
            and it intentionally omits mean absolute error because dollars and
            pounds are not directly comparable.
          </SectionCard>
        </div>

        <div
          className="card px-5 py-5 mt-8 animate-fade-up"
          style={{ animationDelay: "320ms" }}
        >
          <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
            Included country benchmarks
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {globalData.countrySummaries.map((summary) => (
              <div
                key={summary.key}
                className="rounded-2xl border border-border bg-surface px-4 py-4"
              >
                <div className="text-text text-sm font-medium">
                  {summary.label}
                </div>
                <div className="mt-2 text-xs leading-relaxed text-text-secondary">
                  {summary.households.toLocaleString()} households,{" "}
                  {summary.programs} outputs, {summary.models} evaluated models.
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const benchData = data as BenchData;
  const country = benchData.country;
  const noToolsModels = benchData.modelStats.filter(
    (m) => m.condition === "no_tools"
  );
  const modelNames = noToolsModels.map((m) => MODEL_LABELS[m.model] || m.model);
  const variables = [...benchData.programStats]
    .map((program) => program.variable)
    .sort((a, b) =>
      getVariableLabel(a, country).localeCompare(getVariableLabel(b, country))
    );
  const scenarioCount = Object.keys(benchData.scenarios).length;
  const scoredPoints =
    noToolsModels[0]?.n ?? scenarioCount * benchData.programStats.length;
  const hasRepeatedRuns = noToolsModels.some(
    (model) => (model.runCount ?? 0) > 1
  );

  const householdsLabel =
    country === "uk" ? "UK transfer households" : "Enhanced CPS households";
  const referenceOutputSource =
    country === "uk" ? "PolicyEngine-UK" : "PolicyEngine-US";
  const benchmarkDescription =
    country === "uk"
      ? "This app shows the current no-tools UK benchmark on a fixed test set, with PolicyEngine reference outputs computed by PolicyEngine-UK for tax year 2026."
      : "This app shows the current no-tools US benchmark on a fixed test set, with PolicyEngine reference outputs computed by PolicyEngine-US for tax year 2026.";

  return (
    <div>
      <div className="eyebrow mb-3 animate-fade-up">Methodology</div>
      <h2
        className="font-[family-name:var(--font-display)] text-4xl md:text-5xl text-text tracking-tight animate-fade-up"
        style={{ animationDelay: "80ms" }}
      >
        How the {VIEW_LABELS[country]} benchmark works
      </h2>
      <p
        className="text-text-secondary mt-3 max-w-3xl leading-relaxed animate-fade-up"
        style={{ animationDelay: "160ms" }}
      >
        PolicyBench measures a no-tools task: how well frontier models can
        estimate person- and household-level tax and benefit outputs from the
        prompt alone while following a structured response contract.{" "}
        {benchmarkDescription}
      </p>

      <div
        className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-10 animate-fade-up"
        style={{ animationDelay: "240ms" }}
      >
        <StatCard
          value={`${scenarioCount.toLocaleString()}`}
          label={householdsLabel}
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
          Each model sees the same household description and must return all
          scored outputs plus a short explanation for each output in one
          response, with no tool use. The exact provider-specific prompts are
          visible in the scenario explorer, so you can inspect the contract
          instead of inferring it.
        </SectionCard>

        <SectionCard title="Households">
          {country === "uk"
            ? "The UK benchmark samples one-benefit-unit households from the public UK calibrated transfer dataset with a fixed seed. That dataset maps benchmark-compatible US Enhanced CPS records into UK-facing inputs and recalibrates weights to selected UK targets. The prompt states the shared UK benefit-unit structure; nonzero promptable inputs are carried through into both the prompt and the PolicyEngine-UK input."
            : `The US benchmark samples households from the Enhanced CPS with a fixed seed. The current set is restricted to households with a single federal tax unit, a single family, and a single benefit-calculation unit. Adult dependents remain in scope when they satisfy those restrictions. Ages, roles, income sources, and other nonzero promptable inputs are carried through into both the prompt and the ${referenceOutputSource} input; filing status is inferred from household structure.`}
        </SectionCard>

        <SectionCard title="Reference outputs">
          {country === "uk"
            ? "PolicyEngine-UK computes the PolicyEngine reference output for every household-variable pair in tax year 2026. The displayed variables define the benchmark scope for this snapshot."
            : "PolicyEngine-US computes the PolicyEngine reference output for every household-variable pair in tax year 2026. The displayed variables define the benchmark scope for this snapshot."}
        </SectionCard>

        <SectionCard title="Scoring">
          The headline leaderboard uses a bounded score from 0 to 100. For
          dollar-valued outputs, that score averages exact-dollar hit rate,
          within-1%, within-5%, and within-10% hit rates.
          {country === "us"
            ? " Binary coverage flags like person-level Medicaid eligibility and school meal eligibility use exact accuracy."
            : ""}
          {" "}Coverage still tracks how often a model produced a parseable numeric
          answer, and mean absolute error remains a secondary error metric. The
          leaderboard is a point estimate on this fixed test set
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
              Latest {VIEW_LABELS[country]} run in this app evaluates{" "}
              {modelNames.join(", ")} on {scoredPoints.toLocaleString()} scored
              outputs.
            </div>
          </div>
          <div className="text-text-muted text-xs">
            Fixed test set, no tools, tax year 2026
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mt-4">
          {variables.map((variable) => (
            <span
              key={variable}
              className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-xs text-text-secondary"
            >
              <span className="text-text">
                {getVariableLabel(variable, country)}
              </span>
              <span className="text-text-muted">
                {getVariableCategory(variable, country)}
              </span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
