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
const PANEL_GAP = 6;

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

export type PanelPlacement = {
  top: number;
  left: number;
  width: number;
  /** Height cap when neither side of the chip has room for the panel. */
  maxHeight: number;
  side: "below" | "above";
};

/**
 * Where to place the panel: under the chip when the viewport has room for
 * its height there, above the chip otherwise, and clamped horizontally so
 * the whole panel stays inside the viewport on narrow screens. When neither
 * side fits, the larger side is used and the panel scrolls inside its
 * height cap rather than running off the screen.
 */
export function panelPosition(
  anchor: { left: number; top: number; bottom: number },
  viewport: { width: number; height: number },
  panelHeight: number,
): PanelPlacement {
  const width = Math.min(PANEL_MAX_WIDTH, viewport.width - 2 * VIEWPORT_MARGIN);
  const maxLeft = viewport.width - width - VIEWPORT_MARGIN;
  const left = Math.max(VIEWPORT_MARGIN, Math.min(anchor.left, maxLeft));
  const roomBelow = viewport.height - VIEWPORT_MARGIN - (anchor.bottom + PANEL_GAP);
  const roomAbove = anchor.top - PANEL_GAP - VIEWPORT_MARGIN;
  const below = panelHeight <= roomBelow || roomBelow >= roomAbove;
  if (below) {
    return {
      top: anchor.bottom + PANEL_GAP,
      left,
      width,
      maxHeight: Math.max(0, roomBelow),
      side: "below",
    };
  }
  const height = Math.min(panelHeight, Math.max(0, roomAbove));
  return {
    top: anchor.top - PANEL_GAP - height,
    left,
    width,
    maxHeight: Math.max(0, roomAbove),
    side: "above",
  };
}

/**
 * A row-level marker for a model whose board score depends on request shape.
 * The chip shows the tool_choice: auto re-run's score and would-rank; opening
 * it explains why, in place, and links the full note. The summary is a native
 * <details> control (keyboard-operable, labeled); the open panel renders
 * through a portal with fixed, viewport-clamped coordinates so it escapes the
 * row's animation transform, which would otherwise trap it beneath later rows;
 * it sits below the chip when there is room, above it otherwise, and scrolls
 * inside its height cap when neither fits. Opening moves focus into the panel,
 * Tab wraps back to the chip, Escape closes and returns focus, an outside
 * click closes, and scrolling or resizing re-places rather than closes.
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
  const [placement, setPlacement] = useState<PanelPlacement | null>(null);
  // Focus moves into the panel once the portaled copy has been committed,
  // not on the toggle itself (the portal does not exist yet at that point).
  const [pendingFocus, setPendingFocus] = useState(false);

  const close = useCallback((restoreFocus: boolean) => {
    const details = detailsRef.current;
    if (details?.open) details.open = false;
    setPlacement(null);
    if (restoreFocus) details?.querySelector("summary")?.focus();
  }, []);

  // Place from the chip's current position and the panel's rendered height.
  // The first pass after opening measures the inline (hidden) copy of the
  // panel; later passes measure the portaled one.
  const place = useCallback(() => {
    const details = detailsRef.current;
    const summary = details?.querySelector("summary");
    if (!details?.open || !summary) return;
    const rect = summary.getBoundingClientRect();
    const measured = panelRef.current?.getBoundingClientRect().height ?? 0;
    setPlacement(
      panelPosition(
        { left: rect.left, top: rect.top, bottom: rect.bottom },
        { width: window.innerWidth, height: window.innerHeight },
        measured || 240,
      ),
    );
  }, []);

  useEffect(() => {
    const details = detailsRef.current;
    if (!details) return;
    let frame = 0;
    const reposition = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(place);
    };
    const onToggle = () => {
      if (details.open) {
        place();
        // Keyboard users land inside the explanation; Escape returns them.
        setPendingFocus(true);
      } else {
        setPlacement(null);
        setPendingFocus(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && details.open) {
        event.preventDefault();
        close(true);
      }
    };
    const onClick = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        details.open &&
        !details.contains(target) &&
        !panelRef.current?.contains(target)
      ) {
        close(false);
      }
    };
    // Tab past the panel's last link, or Shift+Tab before its first, returns
    // to the chip so the reading order stays with the row.
    const onPanelKey = (event: KeyboardEvent) => {
      if (event.key !== "Tab" || !panelRef.current) return;
      const links = panelRef.current.querySelectorAll<HTMLElement>("a");
      const first = links[0];
      const last = links[links.length - 1];
      const summary = details.querySelector("summary") as HTMLElement | null;
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        summary?.focus();
      } else if (
        event.shiftKey &&
        (document.activeElement === first ||
          document.activeElement === panelRef.current)
      ) {
        event.preventDefault();
        summary?.focus();
      }
    };
    details.addEventListener("toggle", onToggle);
    document.addEventListener("keydown", onKey);
    document.addEventListener("keydown", onPanelKey);
    document.addEventListener("click", onClick);
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    return () => {
      cancelAnimationFrame(frame);
      details.removeEventListener("toggle", onToggle);
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("keydown", onPanelKey);
      document.removeEventListener("click", onClick);
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
    };
  }, [close, place]);

  useEffect(() => {
    if (!placement || !pendingFocus) return;
    panelRef.current?.focus();
    setPendingFocus(false);
  }, [placement, pendingFocus]);

  // Re-place once the portaled panel has a real height (it may differ from
  // the hidden inline copy's estimate).
  useEffect(() => {
    if (!placement) return;
    const measured = panelRef.current?.getBoundingClientRect().height ?? 0;
    if (measured && Math.abs(measured - (placement.maxHeight || measured)) > 0) {
      const details = detailsRef.current;
      const summary = details?.querySelector("summary");
      if (!details?.open || !summary) return;
      const rect = summary.getBoundingClientRect();
      const next = panelPosition(
        { left: rect.left, top: rect.top, bottom: rect.bottom },
        { width: window.innerWidth, height: window.innerHeight },
        measured,
      );
      if (next.top !== placement.top || next.side !== placement.side) {
        setPlacement(next);
      }
    }
    // Only the measured height can change the answer; placement itself is
    // the trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [placement?.top, placement?.side]);

  const auto = sensitivity.autoExact.toFixed(1);
  const deltaText = formatDelta(sensitivity.autoExact, boardExact);

  const panel = (
    <div
      ref={panelRef}
      role="note"
      tabIndex={-1}
      aria-label={`Serving sensitivity for ${modelLabel}`}
      data-testid="serving-sensitivity-panel"
      data-side={placement?.side}
      className="z-50 overflow-y-auto rounded-lg border border-border bg-card p-3 text-left text-xs leading-relaxed text-text-secondary shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-strong/40"
      style={
        placement
          ? {
              position: "fixed",
              top: placement.top,
              left: placement.left,
              width: placement.width,
              maxHeight: placement.maxHeight,
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
