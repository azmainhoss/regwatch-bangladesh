"use client";

import Link from "next/link";
import { Settings, X } from "lucide-react";
import { SkeletonLine } from "@/components/ui";
import { markAllRead, selectPanelAlerts, selectView, useAlerts } from "@/services/alertsStore";
import AlertRow from "./AlertRow";

export const PANEL_TITLE_ID = "alert-panel-title";

/** The bell's dropdown on wide screens, and the bottom sheet on phones. Reads everything from the shared store. */
export default function AlertPanel({ onClose, showClose = false }: { onClose: () => void; showClose?: boolean }) {
  const s = useAlerts();
  const alerts = selectPanelAlerts(s);
  const view = selectView(s, "all", null);
  const loading = alerts.length === 0 && (view.status === "idle" || view.status === "loading");
  const failed = alerts.length === 0 && typeof view.status === "object";
  return (
    <div className="flex max-h-[85dvh] flex-col sm:max-h-[70vh]" data-testid="alert-panel">
      <div className="flex items-center gap-1 border-b border-line px-3 py-2">
        <h2 id={PANEL_TITLE_ID} className="mr-auto pl-1 text-[15px] font-semibold text-ink">
          Alerts
        </h2>
        <button
          type="button"
          onClick={() => void markAllRead()}
          disabled={s.unread === 0}
          className="btn-ghost min-h-[44px] px-2 sm:min-h-0"
        >
          Mark all read
        </button>
        <Link href="/alerts/settings" onClick={onClose} aria-label="Alert settings" title="Alert settings" className="btn-ghost h-11 w-11 p-0 sm:h-8 sm:w-8">
          <Settings className="h-4 w-4" strokeWidth={1.8} />
        </Link>
        {showClose && (
          <button type="button" onClick={onClose} aria-label="Close" className="btn-ghost h-11 w-11 p-0">
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        {loading ? (
          <div className="space-y-3 p-4" aria-busy="true" aria-label="Loading">
            {[0, 1, 2].map((i) => (
              <div key={i}>
                <SkeletonLine className="h-4 w-2/3" />
                <SkeletonLine className="mt-2 h-3 w-full" />
              </div>
            ))}
          </div>
        ) : failed ? (
          <p className="px-4 py-8 text-center text-[13.5px] text-ink-3">Could not load your alerts. They will load again in a moment.</p>
        ) : alerts.length === 0 ? (
          <p className="px-4 py-8 text-center text-[13.5px] text-ink-3">Nothing new. You will see new circulars and work for you here.</p>
        ) : (
          <ul>
            {alerts.map((a) => (
              <AlertRow key={a.id} alert={a} compact onOpened={onClose} />
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-line px-3 py-1.5 text-center">
        <Link href="/alerts" onClick={onClose} className="btn-ghost min-h-[44px] w-full text-accent sm:min-h-0">
          See all alerts
        </Link>
      </div>
    </div>
  );
}
