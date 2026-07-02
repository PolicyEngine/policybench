/* eslint-disable @next/next/no-img-element */
"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import type { CountryCode } from "../types";
import { VIEW_LABELS } from "../types";

export type HeaderNavItem = { id: string; label: string };

export type HeaderActionLink = {
  label: string;
  href: string;
  type?: "internal" | "external";
};

const HEADER_BACKGROUND_REVEAL_START = 0;
const HEADER_BACKGROUND_REVEAL_DISTANCE = 160;
// Start the compact brand/nav reveal the moment the background finishes, not
// 120px later. The old 280px start left a fully frosted bar holding nothing
// but the right-side pills while hero text slid clipped beneath its border —
// the mid-scroll "glitch" of #44. The hero title's bottom passes under the
// bar by ~160px of scroll, so revealing here cannot double the brand.
const COMPACT_HEADER_REVEAL_START = 160;
const COMPACT_HEADER_REVEAL_DISTANCE = 72;

function ViewSelector({
  selectedView,
  onSelect,
  views,
}: {
  selectedView: CountryCode;
  onSelect: (view: CountryCode) => void;
  views: CountryCode[];
}) {
  // Only show the country toggle when more than one country is published.
  // The current release is US-only, so the selector stays hidden.
  if (views.length <= 1) return null;
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

function useMobileHeader() {
  const [isMobileHeader, setIsMobileHeader] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const media = window.matchMedia("(max-width: 767px)");
    const update = () => setIsMobileHeader(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  return isMobileHeader;
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
  selectedView?: CountryCode;
  onSelectView?: (view: CountryCode) => void;
  availableViews?: CountryCode[];
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
  const isMobileHeader = useMobileHeader();
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
  const bgOpacity = alwaysExpanded || isMobileHeader ? 1 : backgroundProgress;
  const contentOpacity =
    alwaysExpanded || isMobileHeader ? 1 : compactContentProgress;
  const contentVisible = alwaysExpanded || contentOpacity > 0.05;

  const showViewSelector =
    availableViews && availableViews.length > 0 && selectedView && onSelectView;
  const headerPositionClass = alwaysExpanded ? "relative z-40" : "sticky top-0 z-40";

  return (
    <header className={headerPositionClass}>
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
        <div className="flex flex-wrap items-center gap-2 sm:gap-3 py-2 sm:py-3">
          <Link
            href="/"
            className="order-1 shrink-0 hover:opacity-80 sm:order-none"
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
            <span className="font-[family-name:var(--font-display)] tracking-tight text-text leading-none text-[16px]">
              PolicyBench
            </span>
          </Link>

          {navItems.length > 0 && (
            <div
              className="order-last flex w-full min-w-0 items-center overflow-x-auto sm:order-none sm:w-auto sm:overflow-visible"
              style={{
                opacity: contentOpacity,
                pointerEvents: contentVisible ? "auto" : "none",
              }}
              aria-hidden={!contentVisible ? true : undefined}
            >
              <div className="mx-2 hidden h-4 w-px shrink-0 bg-border sm:block" />
              <div className="flex min-w-max gap-0.5">
                {navItems.map((item) => (
                  <a
                    key={item.id}
                    href={`#${item.id}`}
                    tabIndex={contentVisible ? 0 : -1}
                    aria-current={activeNav === item.id ? "true" : undefined}
                    className={`border-b-2 px-2 py-2 text-[10px] font-medium uppercase tracking-[0.08em] sm:px-3 sm:text-[11px] sm:tracking-wider ${
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

          <div className="order-2 min-w-2 flex-1 sm:order-none" />

          {showViewSelector && (
            <div className="order-4 max-w-full sm:order-none">
              <ViewSelector
                selectedView={selectedView}
                onSelect={onSelectView}
                views={availableViews}
              />
            </div>
          )}

          {actionLink && (
            <div className="order-3 shrink-0 sm:order-none">
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
            className="order-5 hidden shrink-0 items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider text-text-secondary transition-colors hover:border-primary-strong/40 hover:text-primary-strong md:inline-flex"
          >
            <span>by</span>
            <img
              src="/assets/policyengine-logo.svg"
              alt="PolicyEngine"
              className="h-3 w-auto"
            />
          </a>
        </div>

        {alwaysExpanded && (
          <div className="pt-4 pb-8 sm:pt-6">
            <span className="block font-[family-name:var(--font-display)] tracking-tight text-text leading-none text-[36px] sm:text-[44px]">
              PolicyBench
            </span>
            {expandedContent && <div className="mt-5">{expandedContent}</div>}
          </div>
        )}
      </div>

      <div
        className="h-px bg-gradient-to-r from-transparent via-primary/25 to-transparent"
        style={{ opacity: alwaysExpanded ? 1 : bgOpacity }}
      />
    </header>
  );
}
