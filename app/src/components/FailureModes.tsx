import type {
  BenchData,
  FailureModesPayload,
  HouseholdFailure,
  ProgramFailure,
} from "../types";
import { getVariableLabel } from "../types";

function formatPct(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "n/a";
  return `${value.toFixed(1)}%`;
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

function HouseholdChip({ household }: { household: HouseholdFailure }) {
  return (
    <div className="rounded-2xl border border-border bg-surface px-4 py-3">
      <div className="text-text text-sm">{household.label}</div>
      <div className="mt-1 flex items-center justify-between gap-3 text-xs">
        <span className="text-text-muted">{household.n.toLocaleString()} scored rows</span>
        <span className="text-danger font-[family-name:var(--font-mono)]">
          {formatPct(household.correctPct)}
        </span>
      </div>
    </div>
  );
}

export default function FailureModes({ data }: { data: BenchData }) {
  const country = data.country;
  const failureModes: FailureModesPayload = data.failureModes;
  const hardestPrograms = [...failureModes.programs].slice(0, 10);
  const hardestHouseholds = [...failureModes.households].slice(0, 7);

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
          Read this carefully
        </div>
        <p className="mt-3 text-sm leading-relaxed text-text-secondary">
          These cards are intentionally stricter than the old headline view but
          still use <span className="text-text">within-10% accuracy</span> for
          dollar-valued programs so positive cases stay interpretable.
          <span className="text-text"> Positive-amount cases</span> is the
          harder and more informative number for benefits and refundable
          credits. For household booleans, the cards compare positive and
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

      <div
        className="mt-10 animate-fade-up"
        style={{ animationDelay: "520ms" }}
      >
        <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
          Hardest household segments
        </div>
        <div className="mt-4 grid md:grid-cols-2 xl:grid-cols-3 gap-3">
          {hardestHouseholds.map((household) => (
            <HouseholdChip key={household.label} household={household} />
          ))}
        </div>
      </div>
    </div>
  );
}
