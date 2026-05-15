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

function getScrollProgress(threshold: number) {
  if (typeof window === "undefined") return 0;
  return Math.min(1, Math.max(0, window.scrollY / threshold));
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function useScrollProgress(threshold: number, enabled: boolean) {
  const [progress, setProgress] = useState(() =>
    enabled ? getScrollProgress(threshold) : 0,
  );
  const rafRef = useRef(0);

  useEffect(() => {
    if (!enabled) return;
    if (prefersReducedMotion()) {
      const snap = () => setProgress(getScrollProgress(threshold) > 0.5 ? 1 : 0);
      snap();
      window.addEventListener("scroll", snap, { passive: true });
      return () => window.removeEventListener("scroll", snap);
    }
    const onScroll = () => {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        setProgress(getScrollProgress(threshold));
      });
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(rafRef.current);
    };
  }, [threshold, enabled]);

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
  // Background and content opacity are scroll-driven so the sticky bar reveals
  // itself as the in-flow hero scrolls away. These properties don't affect
  // layout, so they can't trigger the scroll-position feedback loop.
  const progress = useScrollProgress(160, !alwaysExpanded);
  const bgOpacity = alwaysExpanded ? 1 : progress;
  const contentOpacity = alwaysExpanded ? 1 : progress;
  const contentVisible = alwaysExpanded || contentOpacity > 0.05;

  const showViewSelector =
    availableViews && availableViews.length > 0 && selectedView && onSelectView;

  return (
    <header className="sticky top-0 z-40">
      <div
        className="absolute inset-0 border-b backdrop-blur-md"
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
            className="shrink-0 transition-opacity hover:opacity-80"
            style={
              alwaysExpanded
                ? undefined
                : { opacity: contentOpacity, pointerEvents: contentVisible ? "auto" : "none" }
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
              className="flex items-center transition-opacity"
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
