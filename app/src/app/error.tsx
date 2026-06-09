"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-void px-6">
      <div className="max-w-md text-center">
        <div className="eyebrow mb-3">PolicyBench</div>
        <h1 className="font-[family-name:var(--font-display)] text-3xl text-text tracking-tight">
          Something went wrong
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-text-secondary">
          The dashboard hit an unexpected error while rendering.
          {error.digest ? ` (Reference: ${error.digest})` : ""}
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <button
            type="button"
            onClick={reset}
            className="rounded-full border border-primary-strong bg-primary-strong px-4 py-2 text-sm font-medium text-white transition-colors hover:opacity-90"
          >
            Try again
          </button>
          <a
            href="https://github.com/PolicyEngine/policybench/issues"
            className="rounded-full border border-border bg-card px-4 py-2 text-sm text-text-secondary transition-colors hover:border-primary-strong/40 hover:text-text"
          >
            Report an issue
          </a>
        </div>
      </div>
    </main>
  );
}
