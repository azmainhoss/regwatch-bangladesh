"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { EmptyState } from "@/components/ui";
import { PriorityTag, TaskStatusBadge } from "@/components/workspace/badges";
import { ListSkeleton } from "@/components/workspace/Shell";
import { daysLeftText, formatDate } from "@/services/workspaceRules";
import { changeTask, meOf, orgTasks, useWorkspace } from "@/services/workspaceStore";

type Tab = "mine" | "department" | "all";

export default function TasksPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const ws = useWorkspace();
  const me = meOf(ws, orgId);
  const defaultTab: Tab = me && (me.role === "ANALYST" || me.role === "DEPARTMENT_LEAD") ? "mine" : "all";
  const [tab, setTab] = useState<Tab | null>(null);
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const current = tab ?? defaultTab;
  const loaded = ws.loaded[`tasks:${orgId}`] === "ok" && ws.loaded[`items:${orgId}`] === "ok";
  const all = orgTasks(ws, orgId);

  const rows = useMemo(() => {
    if (!me) return [];
    return all.filter((t) => {
      const item = ws.items[t.compliance_item_id];
      if (current === "mine" && t.assigned_to_user_id !== me.userId) return false;
      if (current === "department" && (!me.departmentId || item?.department_id !== me.departmentId)) return false;
      if (status && t.status !== status) return false;
      if (priority && t.priority !== priority) return false;
      if (overdueOnly && !t.is_overdue) return false;
      return true;
    });
  }, [all, ws.items, me, current, status, priority, overdueOnly]);

  if (!me) return null;
  const tabs: [Tab, string][] = [["mine", "Mine"], ...(me.role === "DEPARTMENT_LEAD" ? ([["department", "My department"]] as [Tab, string][]) : []), ["all", "All"]];

  return (
    <div className="space-y-4" data-testid="tasks-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1.5" role="tablist" aria-label="Task view">
          {tabs.map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={current === key}
              onClick={() => setTab(key)}
              className={`min-h-[44px] rounded-full px-4 text-[13.5px] font-semibold ring-1 ring-inset sm:min-h-0 sm:py-1.5 ${current === key ? "bg-accent text-accent-ink ring-accent" : "bg-surface text-ink-2 ring-line-strong hover:bg-sunken"}`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select className="field h-11 w-auto max-w-full py-1 sm:h-9" aria-label="Status filter" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            <option value="PENDING">To do</option>
            <option value="IN_PROGRESS">In progress</option>
            <option value="SUBMITTED">Evidence submitted</option>
            <option value="APPROVED">Approved</option>
            <option value="REJECTED">Rejected</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
          <select className="field h-11 w-auto max-w-full py-1 sm:h-9" aria-label="Priority filter" value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="">All priorities</option>
            <option value="CRITICAL">Critical</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>
          <label className="flex min-h-[44px] items-center gap-2 text-[13.5px] font-semibold text-ink-2 sm:min-h-0">
            <input type="checkbox" className="h-4 w-4 accent-[rgb(var(--accent))]" checked={overdueOnly} onChange={(e) => setOverdueOnly(e.target.checked)} />
            Overdue only
          </label>
        </div>
      </div>
      {!loaded ? (
        <ListSkeleton rows={4} />
      ) : rows.length === 0 ? (
        <EmptyState title="No tasks here.">{current === "mine" && !status && !priority && !overdueOnly ? "Nothing assigned to you. Enjoy the quiet." : undefined}</EmptyState>
      ) : (
        <ul className="panel divide-y divide-line overflow-hidden" data-testid="task-rows">
          {rows.map((t) => {
            const item = ws.items[t.compliance_item_id];
            const mine = t.assigned_to_user_id === me.userId && (t.status === "PENDING" || t.status === "IN_PROGRESS");
            return (
              <li key={t.id} className="grid gap-2 px-4 py-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1.3fr)_auto_auto] md:items-center md:gap-4">
                <div className="min-w-0">
                  <Link href={`/workspace/${orgId}/items/${t.compliance_item_id}#task-${t.id}`} className="text-[14.5px] font-semibold text-ink hover:text-accent">
                    {t.title}
                  </Link>
                  <span className="block truncate text-[12.5px] text-ink-3">{item?.obligation_title ?? "Item"}</span>
                </div>
                <div className="text-[13px]">
                  <span className={`block font-semibold tabular-nums ${t.is_overdue ? "text-bad" : "text-ink"}`}>{formatDate(t.due_date)}</span>
                  <span className={t.is_overdue ? "text-bad" : "text-ink-3"}>
                    {t.status === "APPROVED" || t.status === "CANCELLED" ? "" : daysLeftText(t.days_left)}
                    {t.assigned_to ? `${t.status === "APPROVED" || t.status === "CANCELLED" ? "" : ", "}${t.assigned_to.full_name}` : ""}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <PriorityTag priority={t.priority} />
                  <TaskStatusBadge status={t.status} />
                </div>
                {mine ? (
                  <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" onClick={() => void changeTask(orgId, t.id, { status: t.status === "PENDING" ? "IN_PROGRESS" : "PENDING" })}>
                    {t.status === "PENDING" ? "Start" : "Pause"}
                  </button>
                ) : (
                  <span />
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
