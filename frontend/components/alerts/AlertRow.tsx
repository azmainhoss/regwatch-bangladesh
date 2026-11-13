"use client";

import { useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle2, CheckCheck, ClipboardCheck, Clock, FileText, GitCompare, Inbox, Mail, UserCheck, type LucideIcon } from "lucide-react";
import { Tag, TONE_CLASS, type Tone } from "@/components/StatusBadge";
import type { AlertRead } from "@/services/alertsApi";
import { openAlert, toggleRead } from "@/services/alertsStore";
import AlertQuote from "./AlertQuote";

const GROUP_ICON: Record<string, LucideIcon> = {
  library: FileText,
  source_change: GitCompare,
  assigned: UserCheck,
  review_waiting: ClipboardCheck,
  my_work_decided: CheckCircle2,
  due_soon: Clock,
  overdue: AlertTriangle,
  admin_queue: Inbox,
};

const SEVERITY_TONE: Record<string, Tone> = { info: "info", warn: "warn", bad: "bad" };

// One shared clock so every "5 min ago" moves together without each row running its own timer.
const clockListeners = new Set<() => void>();
let clockTimer: ReturnType<typeof setInterval> | null = null;
let clockNow = 0;
function subscribeClock(l: () => void) {
  clockListeners.add(l);
  if (!clockTimer) {
    clockTimer = setInterval(() => {
      clockNow = Date.now();
      clockListeners.forEach((fn) => fn());
    }, 30000);
  }
  return () => {
    clockListeners.delete(l);
    if (clockListeners.size === 0 && clockTimer) {
      clearInterval(clockTimer);
      clockTimer = null;
    }
  };
}
function clockSnapshot() {
  if (!clockNow) clockNow = Date.now();
  return clockNow;
}
export function useNow() {
  return useSyncExternalStore(subscribeClock, clockSnapshot, () => 0);
}

const DHAKA = "Asia/Dhaka";

export function fullWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: DHAKA });
}

/** "5 min ago" under 24 hours, else "13 Nov, 10:30". */
export function whenText(iso: string, now: number): string {
  const d = new Date(iso);
  const t = d.getTime();
  if (Number.isNaN(t)) return "";
  const diff = Math.max(0, now - t);
  const min = Math.floor(diff / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} h ago`;
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: DHAKA });
}

export default function AlertRow({ alert, compact = false, onOpened }: { alert: AlertRead; compact?: boolean; onOpened?: () => void }) {
  const router = useRouter();
  const now = useNow();
  const unread = !alert.read_at;
  const tone = SEVERITY_TONE[alert.severity] ?? "info";
  const Icon = GROUP_ICON[alert.group] ?? Mail;
  return (
    <li className={`flex items-stretch gap-0 border-b border-line last:border-b-0 ${unread ? "bg-accent-soft/30" : ""}`} data-testid="alert-row" data-unread={unread ? "true" : "false"}>
      <button
        type="button"
        onClick={() => {
          openAlert(alert, router);
          onOpened?.();
        }}
        className="flex min-h-[56px] min-w-0 flex-1 items-start gap-3 px-3 py-3 text-left transition-colors hover:bg-sunken/70"
      >
        <span className="mt-1.5 flex w-2 shrink-0 justify-center">
          {unread && <span className="h-2 w-2 rounded-full bg-accent" aria-hidden />}
        </span>
        <span className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full ring-1 ring-inset ${TONE_CLASS[tone]}`} aria-hidden>
          <Icon className="h-4 w-4" strokeWidth={1.9} />
        </span>
        <span className="min-w-0 flex-1">
          {unread && <span className="sr-only">Unread. </span>}
          <span className={`block text-[14px] leading-snug text-ink ${compact ? "line-clamp-1" : ""} ${unread ? "font-bold" : "font-medium"}`}>{alert.title}</span>
          <span className={`mt-0.5 block text-[13px] leading-snug text-ink-2 ${compact ? "line-clamp-2" : ""}`}>{alert.body}</span>
          {!compact && alert.detail && (
            <span className="mt-1 block break-words text-[13px] leading-snug text-ink-2">
              <span className="font-semibold">Comment:</span> {alert.detail}
            </span>
          )}
          {alert.quote && (
            <AlertQuote text={alert.quote.text} reference={alert.quote.document_reference} page={alert.quote.page_number} clamp={compact} />
          )}
          <span className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
            {alert.organization_name && <Tag>{alert.organization_name}</Tag>}
            <span className="meta text-xs" title={fullWhen(alert.created_at)}>
              {whenText(alert.created_at, now)}
            </span>
          </span>
        </span>
      </button>
      <button
        type="button"
        onClick={() => void toggleRead(alert.id)}
        aria-label={unread ? "Mark as read" : "Mark as unread"}
        title={unread ? "Mark as read" : "Mark as unread"}
        className="grid h-11 w-11 shrink-0 place-items-center self-start text-ink-3 transition-colors hover:text-ink sm:mt-1"
      >
        {unread ? <CheckCheck className="h-4 w-4" strokeWidth={1.9} /> : <span className="h-2.5 w-2.5 rounded-full border border-ink-3" aria-hidden />}
      </button>
    </li>
  );
}
