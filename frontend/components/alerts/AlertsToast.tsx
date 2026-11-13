"use client";

import { createPortal } from "react-dom";
import { Notice } from "@/components/ui";
import { clearAlertsNotice, useAlerts } from "@/services/alertsStore";

/** A short message after an alert change fails or settings are reset. Shown on every page while signed in. */
export default function AlertsToast() {
  const s = useAlerts();
  if (!s.notice || typeof document === "undefined") return null;
  return createPortal(
    <div className="no-print pointer-events-none fixed inset-x-4 bottom-4 z-[65] flex justify-center sm:inset-x-auto sm:right-6 sm:justify-end" data-testid="alerts-toast">
      <div className="pointer-events-auto w-full max-w-md shadow-pop">
        <Notice kind={s.notice.kind} onDismiss={clearAlertsNotice}>
          {s.notice.text}
        </Notice>
      </div>
    </div>,
    document.body,
  );
}
