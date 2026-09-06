"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";

import {
  NEXT_BOARD_HREF,
  SENSITIVITY_DOC_HREF,
  formatDelta,
  type ServingSensitivity,
} from "../lib/servingSensitivity";

const PANEL_MAX_WIDTH = 352; // 22rem
const VIEWPORT_MARGIN = 8;

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
 * Where to place the panel: under the chip, clamped so the whole panel stays
 * inside the viewport on narrow screens.
 */
export function panelPosition(
  anchor: { left: number; bottom: number },
  viewportWidth: number,
): { top: number; left: number; width: number } {
  const width = Math.min(PANEL_MAX_WIDTH, viewportWidth - 2 * VIEWPORT_MARGIN);
  const maxLeft = viewportWidth - width - VIEWPORT_MARGIN;
  const left = Math.max(VIEWPORT_MARGIN, Math.min(anchor.left, maxLeft));
  return { top: anchor.bottom + 6, left, width };
}

/**
 * A row-level marker for a model whose board score depends on request shape.
 * The chip shows the tool_choice: auto re-run's score and would-rank; opening
 * it explains why, in place, and links the full note. The summary is a native
 * <details> control (keyboard-operable, labeled); the open panel renders
 * through a portal with fixed, viewport-clamped coordinates so it escapes the
 * row's animation transform, which would otherwise trap it beneath later rows.
 * Escape, an outside click, scrolling or resizing closes it.
 */
export default function ServingSensitivityChip({
  modelLabel,
  boardExact,
  sensitivity,
  wouldRank,
}: {
  modelLabel: string;
  /** The model's exact-match score on the unfiltered board (unrounded). */
  boardExact: number;
  sensitivity: ServingSensitivity;
  wouldRank: number;
}) {
  const detailsRef = useRef<HTMLDetailsElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [placement, setPlacement] = useState<{
    top: number;
    left: number;
    width: number;
  } | null>(null);

  const close = useCallback(() => {
    const details = detailsRef.current;
    if (details?.open) details.open = false;
    setPlacement(null);
  }, []);

  const place = useCallback(() => {
    const details = detailsRef.current;
    const summary = details?.querySelector("summary");
    if (!details?.open || !summary) return;
    const rect = summary.getBoundingClientRect();
    setPlacement(
      panelPosition({ left: rect.left, bottom: rect.bottom }, window.innerWidth),
    );
  }, []);

  useEffect(() => {
    const details = detailsRef.current;
    if (!details) return;
    const onToggle = () => (details.open ? place() : setPlacement(null));
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    const onClick = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        details.open &&
        !details.contains(target) &&
        !panelRef.current?.contains(target)
      ) {
        close();
      }
    };
    details.addEventListener("toggle", onToggle);
    document.addEventListener("keydown", onKey);
    document.addEventListener("click", onClick);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      details.removeEventListener("toggle", onToggle);
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("click", onClick);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [close, place]);

  const auto = sensitivity.autoExact.toFixed(1);
  const deltaText = formatDelta(sensitivity.autoExact, boardExact);

  const panel = (
    <div
      ref={panelRef}
      role="note"
      data-testid="serving-sensitivity-panel"
      className="z-50 rounded-lg border border-border bg-card p-3 text-left text-xs leading-relaxed text-text-secondary shadow-lg"
      style={
        placement
          ? {
              position: "fixed",
              top: placement.top,
              left: placement.left,
              width: placement.width,
            }
          : undefined
      }
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
        exact ({deltaText} against its {boardExact.toFixed(1)}% on the
        unfiltered board) and would rank #{wouldRank} there. The board keeps
        the request shape its model card records; the re-run sits beside it as
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
  );

  return (
    <details ref={detailsRef} className="relative inline-block align-middle">
      <summary
        className="list-none cursor-pointer select-none rounded-full border border-border bg-surface px-2 py-0.5 font-[family-name:var(--font-mono)] text-[10px] text-text-secondary hover:border-primary-strong/50 hover:text-text [&::-webkit-details-marker]:hidden"
        aria-label={`Serving sensitivity for ${modelLabel}: ${auto}% with tool_choice auto, would rank #${wouldRank}`}
        title="Serving sensitivity"
      >
        auto {auto} · #{wouldRank}
      </summary>
      {placement && typeof document !== "undefined"
        ? createPortal(panel, document.body)
        : // Server render and the closed state keep the panel inline (hidden
          // by the closed <details>), so markup matches on hydration and the
          // text stays reachable without JavaScript.
          <div className="absolute left-0 top-full mt-1.5 w-[min(22rem,calc(100vw-2rem))]">
            {panel}
          </div>}
    </details>
  );
}
