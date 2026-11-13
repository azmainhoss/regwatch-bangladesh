"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { usePathname } from "next/navigation";
import { Bell } from "lucide-react";
import { Modal } from "@/components/ui";
import { useAlerts } from "@/services/alertsStore";
import AlertPanel, { PANEL_TITLE_ID } from "./AlertPanel";
import AlertsToast from "./AlertsToast";

const QUERY = "(min-width: 640px)";

function subscribeWide(cb: () => void) {
  const m = window.matchMedia(QUERY);
  m.addEventListener("change", cb);
  return () => m.removeEventListener("change", cb);
}
function useWide() {
  return useSyncExternalStore(subscribeWide, () => window.matchMedia(QUERY).matches, () => true);
}

/** The bell in the header. Wide screens get a dropdown, phones get a bottom sheet. */
export default function BellButton() {
  const s = useAlerts();
  const wide = useWide();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const n = s.unread;

  // Going to another page closes it.
  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open || !wide) return;
    const onDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    const t = window.setTimeout(() => popRef.current?.querySelector<HTMLElement>("button, a")?.focus(), 30);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.clearTimeout(t);
    };
  }, [open, wide]);

  const close = () => setOpen(false);
  return (
    <div ref={wrapRef} className="relative">
      <AlertsToast />
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={`Alerts, ${n} unread`}
        aria-haspopup="dialog"
        aria-expanded={open}
        data-testid="bell"
        className="relative grid h-11 w-11 shrink-0 place-items-center rounded-control border border-line text-ink-2 transition-colors hover:border-line-strong hover:bg-sunken hover:text-ink sm:h-9 sm:w-9"
      >
        <Bell className="h-[18px] w-[18px]" strokeWidth={1.8} />
        {n > 0 && (
          <span
            data-testid="bell-badge"
            aria-hidden
            className="absolute -right-1.5 -top-1.5 grid min-w-[18px] place-items-center rounded-full bg-bad px-1 text-[11px] font-bold leading-[18px] text-white ring-2 ring-canvas"
          >
            {n > 99 ? "99+" : n}
          </span>
        )}
      </button>

      {wide && open && (
        <div
          ref={popRef}
          role="dialog"
          aria-labelledby={PANEL_TITLE_ID}
          className="absolute right-0 top-full z-50 mt-2 w-[380px] overflow-hidden rounded-panel border border-line bg-surface shadow-pop"
        >
          <AlertPanel onClose={close} />
        </div>
      )}
      {/* The sheet is placed on the page itself: the header's blur would otherwise trap a fixed layer inside it. */}
      {!wide &&
        createPortal(
          <Modal open={open} onClose={close} labelledBy={PANEL_TITLE_ID}>
            <AlertPanel onClose={close} showClose />
          </Modal>,
          document.body,
        )}
    </div>
  );
}
