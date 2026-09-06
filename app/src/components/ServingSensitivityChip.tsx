"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";

import {
  NEXT_BOARD_HREF,
  SENSITIVITY_DOC_HREF,
  type ServingSensitivity,
} from "../lib/servingSensitivity";

function NoteLink({ href, children }: { href: string; children: string }) {
  const className = "text-primary-strong underline-offset-2 hover:underline";
  return href.startsWith("/") ? (
    <Link href={href} className={className}>
      {children}
    </Link>
  ) : (
    <a href={href} className={className}>
      {children}
    </a>
  );
}

/**
 * A row-level marker for a model whose board score depends on request shape.
 * The chip shows the tool_choice: auto re-run's score and would-rank; opening
 * it explains why, in place, and links the full note. A native <details>
 * keeps it keyboard-operable and readable without JavaScript; the effect only
 * closes it on Escape or an outside click.
 */
export default function ServingSensitivityChip({
  modelLabel,
  boardExact,
  sensitivity,
  wouldRank,
}: {
  modelLabel: string;
  boardExact: number;
  sensitivity: ServingSensitivity;
  wouldRank: number;
}) {
  const ref = useRef<HTMLDetailsElement | null>(null);

  useEffect(() => {
    const details = ref.current;
    if (!details) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && details.open) details.open = false;
    };
    const onClick = (event: MouseEvent) => {
      if (details.open && !details.contains(event.target as Node)) {
        details.open = false;
      }
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("click", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("click", onClick);
    };
  }, []);

  const auto = sensitivity.autoExact.toFixed(1);
  const delta = sensitivity.autoExact - boardExact;
  const deltaText = `${delta >= 0 ? "+" : "−"}${Math.abs(delta).toFixed(1)}`;

  return (
    <details ref={ref} className="relative inline-block align-middle">
      <summary
        className="list-none cursor-pointer select-none rounded-full border border-border bg-surface px-2 py-0.5 font-[family-name:var(--font-mono)] text-[10px] text-text-secondary hover:border-primary-strong/50 hover:text-text [&::-webkit-details-marker]:hidden"
        aria-label={`Serving sensitivity for ${modelLabel}: ${auto}% with tool_choice auto, would rank #${wouldRank}`}
        title="Serving sensitivity"
      >
        auto {auto} · #{wouldRank}
      </summary>
      <div
        role="note"
        className="absolute left-0 top-full z-20 mt-1.5 w-[min(22rem,calc(100vw-2rem))] rounded-lg border border-border bg-card p-3 text-left text-xs leading-relaxed text-text-secondary shadow-lg"
      >
        <div className="text-[10px] uppercase tracking-[0.14em] text-text-muted font-medium">
          Serving sensitivity
        </div>
        <p className="mt-1.5">
          This row {sensitivity.boardTreatment}. The same model,{" "}
          {sensitivity.autoTreatment}, scores{" "}
          <span className="font-[family-name:var(--font-mono)] text-text">
            {auto}%
          </span>{" "}
          ({deltaText}) and would rank #{wouldRank}. The board keeps the
          request shape its model card records; the re-run sits beside it as
          a labeled sensitivity.
        </p>
        <p className="mt-1.5">
          <NoteLink href={sensitivity.noteHref}>
            {sensitivity.noteHref.startsWith("/")
              ? "Read the note"
              : "Read the sensitivity note"}
          </NoteLink>
          {" · "}
          <NoteLink href={SENSITIVITY_DOC_HREF}>All four runs</NoteLink>
          {" · "}
          <NoteLink href={NEXT_BOARD_HREF}>
            Next board moves every model to auto
          </NoteLink>
        </p>
      </div>
    </details>
  );
}
