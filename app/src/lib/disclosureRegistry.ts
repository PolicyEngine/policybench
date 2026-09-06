/**
 * One open disclosure at a time. Chips register when they open; opening
 * another closes the previous one, and document-level keys (Escape) are
 * routed to the active disclosure only, so focus is restored to the chip
 * that was actually open rather than to whichever handler ran last.
 */
export type DisclosureHandle = {
  /** Close this disclosure; `restoreFocus` returns focus to its trigger. */
  close: (restoreFocus: boolean) => void;
};

export function createDisclosureRegistry() {
  let active: DisclosureHandle | null = null;
  return {
    /** Make `handle` the open disclosure, closing any other. */
    activate(handle: DisclosureHandle): void {
      if (active && active !== handle) active.close(false);
      active = handle;
    },
    /** Forget `handle` if it is the active one (call on close). */
    release(handle: DisclosureHandle): void {
      if (active === handle) active = null;
    },
    isActive(handle: DisclosureHandle): boolean {
      return active === handle;
    },
    /** Escape closes the active disclosure and restores its focus; returns
     * whether anything was open. */
    escape(): boolean {
      if (!active) return false;
      const handle = active;
      active = null;
      handle.close(true);
      return true;
    },
  };
}

export const servingSensitivityDisclosures = createDisclosureRegistry();
