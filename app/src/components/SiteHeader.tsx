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
  compact,
}: {
  selectedView: ViewKey;
  onSelect: (view: ViewKey) => void;
  views: ViewKey[];
  compact?: boolean;
}) {
  const pill = compact
    ? "rounded-full text-[10px] px-2.5 py-1 font-medium transition-colors"
    : "rounded-full px-3 py-1.5 text-xs font-medium transition-colors sm:px-4";
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
          className={`${pill} ${
            selectedView === view
              ? "bg-primary text-void"
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

function useScrollProgress(threshold = 80, enabled = true) {
  const [progress, setProgress] = useState(() =>
    enabled ? getScrollProgress(threshold) : 0,
  );
  const rafRef = useRef(0);

  useEffect(() => {
    if (!enabled) return;
    const onScroll = () => {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        setProgress(getScrollProgress(threshold));
      });
    };
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
  const measuredProgress = useScrollProgress(80, !alwaysExpanded);
  const progress = alwaysExpanded ? 0 : measuredProgress;
  const scrolled = progress > 0.5;
  const navVisible = !alwaysExpanded; // navItems are only meaningful while
  // the in-page hero is driving the collapse; on alwaysExpanded pages we
  // hide them outright by leaving navItems empty.
  const actionVisible = alwaysExpanded || progress > 0.3;

  const lerp = (a: number, b: number) => a + (b - a) * progress;
  const expandedPadTop = lerp(40, 8);
  const expandedPadBot = lerp(16, 8);
  const titleSize = lerp(36, 16);
  const expandOpacity = 1 - Math.min(1, progress * 2);
  const expandHeight = `${(1 - progress) * 320}px`;
  const navOpacity = Math.max(0, (progress - 0.3) / 0.7);
  const bgOpacity = progress;

  const showViewSelector =
    availableViews && availableViews.length > 0 && selectedView && onSelectView;

  return (
    <header className="sticky top-0 z-40">
      <div
        className="absolute inset-0 border-b backdrop-blur-md"
        style={{
          opacity: alwaysExpanded ? 1 : bgOpacity,
          backgroundColor: alwaysExpanded
            ? "color-mix(in srgb, var(--color-bg) 90%, transparent)"
            : `color-mix(in srgb, var(--color-bg) ${Math.round(bgOpacity * 90)}%, transparent)`,
          borderColor: alwaysExpanded
            ? "var(--color-border)"
            : `color-mix(in srgb, var(--color-border) ${Math.round(bgOpacity * 100)}%, transparent)`,
        }}
      />

      <div
        className="absolute inset-x-0 top-0 h-[280px] bg-[radial-gradient(circle_at_top,_color-mix(in_srgb,var(--color-primary)_13%,transparent),transparent_58%)] pointer-events-none"
        style={{ opacity: alwaysExpanded ? 1 : 1 - progress }}
      />

      <div className="relative max-w-7xl mx-auto px-4 sm:px-6">
        <div
          className="flex items-center gap-3"
          style={{
            paddingTop: `${expandedPadTop}px`,
            paddingBottom: `${expandedPadBot}px`,
          }}
        >
          <Link href="/" className="shrink-0 hover:opacity-80">
            <span
              className="font-[family-name:var(--font-display)] tracking-tight text-text leading-none"
              style={{ fontSize: `${titleSize}px` }}
            >
              PolicyBench
            </span>
          </Link>

          {navItems.length > 0 && (
            <div
              className="flex items-center overflow-hidden"
              style={{
                opacity: navOpacity,
                maxWidth: navOpacity > 0.05 ? "600px" : "0px",
                marginLeft: navOpacity > 0.05 ? "4px" : "0px",
              }}
              aria-hidden={navVisible ? undefined : true}
            >
              <div className="h-4 w-px bg-border shrink-0 mx-2" />
              <div className="flex min-w-max gap-0.5">
                {navItems.map((item) => (
                  <a
                    key={item.id}
                    href={`#${item.id}`}
                    tabIndex={navVisible ? 0 : -1}
                    className={`px-2.5 py-2 text-[11px] font-medium tracking-wider uppercase border-b-2 sm:px-3 ${
                      activeNav === item.id
                        ? "border-primary text-primary"
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
              compact={scrolled}
            />
          )}

          {actionLink && (
            <div
              className="overflow-hidden"
              style={{
                opacity: alwaysExpanded ? 1 : navOpacity,
                maxWidth:
                  alwaysExpanded || navOpacity > 0.05 ? "120px" : "0px",
              }}
              aria-hidden={actionVisible ? undefined : true}
            >
              {actionLink.type === "external" ? (
                <a
                  href={actionLink.href}
                  tabIndex={actionVisible ? 0 : -1}
                  className="rounded-full border border-border bg-card px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-text-secondary hover:border-primary/40 hover:text-primary whitespace-nowrap"
                >
                  {actionLink.label}
                </a>
              ) : (
                <Link
                  href={actionLink.href}
                  tabIndex={actionVisible ? 0 : -1}
                  className="rounded-full border border-border bg-card px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-text-secondary hover:border-primary/40 hover:text-primary whitespace-nowrap"
                >
                  {actionLink.label}
                </Link>
              )}
            </div>
          )}

          <a
            href="https://policyengine.org"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider text-text-secondary transition-colors hover:border-primary/40 hover:text-primary"
            aria-label="By PolicyEngine"
            title="By PolicyEngine"
          >
            <span>by</span>
            <img
              src="/assets/policyengine-logo.svg"
              alt="PolicyEngine"
              className="h-3 w-auto"
            />
          </a>
        </div>

        {expandedContent && (
          <div
            className="overflow-hidden"
            style={{
              maxHeight: alwaysExpanded ? "none" : expandHeight,
              opacity: alwaysExpanded ? 1 : expandOpacity,
              paddingBottom:
                alwaysExpanded || expandOpacity > 0.05
                  ? `${alwaysExpanded ? 32 : lerp(32, 0)}px`
                  : "0px",
            }}
          >
            {expandedContent}
          </div>
        )}
      </div>

      <div
        className="h-px bg-gradient-to-r from-transparent via-primary/25 to-transparent"
        style={{ opacity: alwaysExpanded ? 1 : 1 - progress }}
      />
    </header>
  );
}
