/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import type { ViewKey } from "../types";
import { VIEW_LABELS } from "../types";

export type HeaderNavItem = { id: string; label: string };

export type HeaderActionLink = {
  label: string;
  href: string;
  type?: "internal" | "external";
};

const HEADER_BACKGROUND_REVEAL_START = 0;
const HEADER_BACKGROUND_REVEAL_DISTANCE = 160;
const COMPACT_HEADER_REVEAL_START = 280;
const COMPACT_HEADER_REVEAL_DISTANCE = 72;

function ViewSelector({
  selectedView,
  onSelect,
  views,
}: {
  selectedView: ViewKey;
  onSelect: (view: ViewKey) => void;
  views: ViewKey[];
}) {
  return (
    <div
      role="group"
      aria-label="Country view"
      className="inline-flex max-w-full items-center gap-1 rounded-full border border-border bg-bg/80 p-1"
    >
      {views.map((view) => (
        <button
          key={view}
          type="button"
          onClick={() => onSelect(view)}
          aria-pressed={selectedView === view}
          className={`rounded-full text-[11px] px-3 py-1.5 font-medium transition-colors ${
            selectedView === view
              ? "bg-primary-strong text-white"
              : "text-text-secondary hover:text-text"
          }`}
        >
          {VIEW_LABELS[view]}
        </button>
      ))}
    </div>
  );
}

function getScrollProgress(start: number, distance: number) {
  if (typeof window === "undefined") return 0;
  return Math.min(1, Math.max(0, (window.scrollY - start) / distance));
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function useScrollProgress(start: number, distance: number, enabled: boolean) {
  const [progress, setProgress] = useState(() =>
    enabled ? getScrollProgress(start, distance) : 0,
  );
  const rafRef = useRef(0);

  useEffect(() => {
    if (!enabled) return;
    if (prefersReducedMotion()) {
      const snap = () =>
        setProgress(getScrollProgress(start, distance) > 0.5 ? 1 : 0);
      snap();
      const timeout = window.setTimeout(snap, 0);
      window.addEventListener("scroll", snap, { passive: true });
      window.addEventListener("resize", snap);
      window.addEventListener("hashchange", snap);
      window.addEventListener("load", snap);
      return () => {
        window.clearTimeout(timeout);
        window.removeEventListener("scroll", snap);
        window.removeEventListener("resize", snap);
        window.removeEventListener("hashchange", snap);
        window.removeEventListener("load", snap);
      };
    }
    const onScroll = () => {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        setProgress(getScrollProgress(start, distance));
      });
    };
    onScroll();
    const settleTimeout = window.setTimeout(onScroll, 0);
    const hashScrollTimeout = window.setTimeout(onScroll, 120);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    window.addEventListener("hashchange", onScroll);
    window.addEventListener("load", onScroll);
    return () => {
      window.clearTimeout(settleTimeout);
      window.clearTimeout(hashScrollTimeout);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      window.removeEventListener("hashchange", onScroll);
      window.removeEventListener("load", onScroll);
      cancelAnimationFrame(rafRef.current);
    };
  }, [start, distance, enabled]);

  return enabled ? progress : 0;
}

export type SiteHeaderProps = {
  navItems?: readonly HeaderNavItem[];
  activeNav?: string;
  selectedView?: ViewKey;
  onSelectView?: (view: ViewKey) => void;
  availableViews?: ViewKey[];
  actionLink?: HeaderActionLink;
  /**
   * Optional expanded content shown inside the sticky header. Use only with
   * `alwaysExpanded` — when `alwaysExpanded` is false, this prop is ignored and
   * pages should render hero content as a regular in-flow section instead. The
   * old scroll-driven collapse caused the sticky's layout box to shrink during
   * scroll, which fed back into scrollY and created a "caught" dead zone.
   */
  expandedContent?: React.ReactNode;
  /**
   * When true, the header always renders in its expanded state. Used on pages
   * (e.g. /paper) where we don't have an in-page hero to drive the collapse.
   */
  alwaysExpanded?: boolean;
};

export default function SiteHeader({
  navItems = [],
  activeNav,
  selectedView,
  onSelectView,
  availableViews,
  actionLink,
  expandedContent,
  alwaysExpanded = false,
}: SiteHeaderProps) {
  // Background and compact content opacity are scroll-driven, but staggered:
  // the background covers text moving under the sticky bar, while the compact
  // brand/nav wait until the hero intro has cleared. These properties don't
  // affect layout, so they can't trigger the scroll-position feedback loop.
  const backgroundProgress = useScrollProgress(
    HEADER_BACKGROUND_REVEAL_START,
    HEADER_BACKGROUND_REVEAL_DISTANCE,
    !alwaysExpanded,
  );
  const compactContentProgress = useScrollProgress(
    COMPACT_HEADER_REVEAL_START,
    COMPACT_HEADER_REVEAL_DISTANCE,
    !alwaysExpanded,
  );
  const bgOpacity = alwaysExpanded ? 1 : backgroundProgress;
  const contentOpacity = alwaysExpanded ? 1 : compactContentProgress;
  const contentVisible = alwaysExpanded || contentOpacity > 0.05;

  const showViewSelector =
    availableViews && availableViews.length > 0 && selectedView && onSelectView;

  return (
    <header className="sticky top-0 z-40">
      <div
        className="pointer-events-none absolute inset-0 border-b backdrop-blur-md"
        style={{
          opacity: bgOpacity,
          backgroundColor: `color-mix(in srgb, var(--color-bg) ${Math.round(
            bgOpacity * 90,
          )}%, transparent)`,
          borderColor: `color-mix(in srgb, var(--color-border) ${Math.round(
            bgOpacity * 100,
          )}%, transparent)`,
        }}
      />

      {alwaysExpanded && (
        <div
          className="absolute inset-x-0 top-0 h-[280px] bg-[radial-gradient(circle_at_top,_color-mix(in_srgb,var(--color-primary)_13%,transparent),transparent_58%)] pointer-events-none"
        />
      )}

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6">
        <div
          className={`flex items-center gap-3 ${
            alwaysExpanded ? "pt-10 pb-4" : "py-3"
          }`}
        >
          <Link
            href="/"
            className="shrink-0 hover:opacity-80"
            style={
              alwaysExpanded
                ? undefined
                : {
                    opacity: contentOpacity,
                    pointerEvents: contentVisible ? "auto" : "none",
                  }
            }
            tabIndex={alwaysExpanded || contentVisible ? 0 : -1}
            aria-hidden={!alwaysExpanded && !contentVisible ? true : undefined}
          >
            <span
              className={`font-[family-name:var(--font-display)] tracking-tight text-text leading-none ${
                alwaysExpanded ? "text-[36px]" : "text-[16px]"
              }`}
            >
              PolicyBench
            </span>
          </Link>

          {navItems.length > 0 && (
            <div
              className="flex items-center"
              style={{
                opacity: contentOpacity,
                pointerEvents: contentVisible ? "auto" : "none",
              }}
              aria-hidden={!contentVisible ? true : undefined}
            >
              <div className="h-4 w-px bg-border shrink-0 mx-2" />
              <div className="flex min-w-max gap-0.5">
                {navItems.map((item) => (
                  <a
                    key={item.id}
                    href={`#${item.id}`}
                    tabIndex={contentVisible ? 0 : -1}
                    aria-current={activeNav === item.id ? "true" : undefined}
                    className={`px-2.5 py-2 text-[11px] font-medium tracking-wider uppercase border-b-2 sm:px-3 ${
                      activeNav === item.id
                        ? "border-primary-strong text-primary-strong"
                        : "border-transparent text-text-secondary hover:text-text"
                    }`}
                  >
                    {item.label}
                  </a>
                ))}
              </div>
            </div>
          )}

          <div className="flex-1" />

          {showViewSelector && (
            <ViewSelector
              selectedView={selectedView}
              onSelect={onSelectView}
              views={availableViews}
            />
          )}

          {actionLink && (
            <div>
              {actionLink.type === "external" ? (
                <a
                  href={actionLink.href}
                  className="rounded-full border border-border bg-card px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-text-secondary backdrop-blur hover:border-primary/40 hover:text-primary whitespace-nowrap"
                >
                  {actionLink.label}
                </a>
              ) : (
                <Link
                  href={actionLink.href}
                  className="rounded-full border border-border bg-card px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-text-secondary backdrop-blur hover:border-primary/40 hover:text-primary whitespace-nowrap"
                >
                  {actionLink.label}
                </Link>
              )}
            </div>
          )}

          <a
            href="https://policyengine.org"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider text-text-secondary transition-colors hover:border-primary-strong/40 hover:text-primary-strong"
          >
            <span>by</span>
            <img
              src="/assets/policyengine-logo.svg"
              alt="PolicyEngine"
              className="h-3 w-auto"
            />
          </a>
        </div>

        {alwaysExpanded && expandedContent && (
          <div className="pb-8">{expandedContent}</div>
        )}
      </div>

      <div
        className="h-px bg-gradient-to-r from-transparent via-primary/25 to-transparent"
        style={{ opacity: alwaysExpanded ? 1 : bgOpacity }}
      />
    </header>
  );
}
