"use client";

import { useEffect, useId, useRef, useState } from "react";

import { DATA_VERSIONS } from "../lib/dataVersionsRuntime";

/**
 * Compact dataset-version dropdown for the site header. Renders as a button
 * ("Dataset v1.1") that opens a small listbox of published versions, each with
 * its one-line description. Keeps the header's pill styling and closes on
 * outside click or Escape.
 */
export default function DatasetSelector({
  versionId,
  onSelect,
}: {
  versionId: string;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const listboxId = useId();

  // Nothing to switch between when only one version is published.
  const hasChoices = DATA_VERSIONS.length > 1;

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (!hasChoices) return null;

  const active =
    DATA_VERSIONS.find((version) => version.id === versionId) ??
    DATA_VERSIONS[0];

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-text-secondary backdrop-blur transition-colors hover:border-primary/40 hover:text-primary whitespace-nowrap"
      >
        <span>Dataset v{active.label}</span>
        <svg
          viewBox="0 0 12 12"
          aria-hidden
          className={`h-2.5 w-2.5 transition-transform ${
            open ? "rotate-180" : ""
          }`}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="M2.5 4.5 6 8l3.5-3.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <ul
          id={listboxId}
          role="listbox"
          aria-label="Dataset version"
          className="absolute right-0 z-50 mt-2 w-72 max-w-[80vw] overflow-hidden rounded-xl border border-border bg-card p-1 shadow-lg backdrop-blur"
        >
          {DATA_VERSIONS.map((version) => {
            const selected = version.id === active.id;
            return (
              <li key={version.id} role="none">
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onClick={() => {
                    onSelect(version.id);
                    setOpen(false);
                  }}
                  className={`flex w-full flex-col gap-0.5 rounded-lg px-3 py-2 text-left transition-colors ${
                    selected
                      ? "bg-primary-soft text-text"
                      : "text-text-secondary hover:bg-elevated hover:text-text"
                  }`}
                >
                  <span className="flex items-center gap-2 text-[12px] font-semibold tracking-tight">
                    Dataset v{version.label}
                    {selected && (
                      <span className="text-[9px] font-medium uppercase tracking-[0.12em] text-primary">
                        Selected
                      </span>
                    )}
                  </span>
                  <span className="text-[11px] leading-snug text-text-muted">
                    {version.description}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
