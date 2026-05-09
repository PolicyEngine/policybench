"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

type TooltipPosition = {
  top: number;
  left: number;
};

export default function ExplanationTooltip({
  explanation,
  children = "why",
}: {
  explanation: string;
  children?: ReactNode;
}) {
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<TooltipPosition | null>(null);
  const tooltipId = useId();

  useEffect(() => {
    if (!open) return;

    const updatePosition = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;

      const rect = trigger.getBoundingClientRect();
      setPosition({
        top: rect.bottom + 10,
        left: rect.left + rect.width / 2,
      });
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };

    updatePosition();
    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);
    document.addEventListener("keydown", onKeyDown);

    return () => {
      window.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-describedby={open ? tooltipId : undefined}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="inline-flex rounded-full border border-border px-1.5 py-0.5 text-[10px] leading-none text-text-muted transition-colors hover:border-primary-strong/40 hover:text-text focus:border-primary-strong/60 focus:text-text cursor-help"
      >
        {children}
        <span className="sr-only">{`: ${explanation}`}</span>
      </button>
      {open &&
        position &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            id={tooltipId}
            ref={tooltipRef}
            role="tooltip"
            // Dropping pointer-events-none lets a mouse user move into the
            // tooltip to read long explanations without it dismissing.
            // We also keep the tooltip open while the user hovers it.
            onMouseEnter={() => setOpen(true)}
            onMouseLeave={() => setOpen(false)}
            className="fixed z-[100] max-w-xs -translate-x-1/2 rounded-xl border border-border bg-surface px-3 py-2 text-left text-xs leading-relaxed text-text shadow-[0_12px_48px_rgba(0,0,0,0.35)]"
            style={{
              top: position.top,
              left: position.left,
            }}
          >
            {explanation}
          </div>,
          document.body,
        )}
    </>
  );
}
