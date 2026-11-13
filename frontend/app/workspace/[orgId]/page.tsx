"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Download, FileText, Plus } from "lucide-react";
import { EmptyState, SkeletonLine } from "@/components/ui";
import { ItemStatusBadge, TaskStatusBadge } from "@/components/workspace/badges";
import { ListSkeleton } from "@/components/workspace/Shell";
import { downloadReportCsv } from "@/services/workspaceApi";
import { daysLeftText, formatDate } from "@/services/workspaceRules";
import { selectDashboard } from "@/services/workspaceSelectors";
import { changeTask, meOf, orgRegisters, orgTasks, setNotice, useWorkspace } from "@/services/workspaceStore";

function Tile({ href, label, value, of, tone }: { href: string; label: string; value: number; of: number; tone?: "bad" | "warn" }) {
  return (
    <Link href={href} className="panel block min-h-[88px] px-4 py-3.5 transition-colors hover:border-line-strong hover:bg-sunken/60" data-testid={`tile-${label.toLowerCase().replace(/\s+/g, "-")}`}>
      <span className="block text-[13px] font-semibold text-ink-3">{label}</span>
      <span className={`mt-1 block text-[28px] font-bold leading-none tabular-nums ${tone === "bad" && value > 0 ? "text-bad" : tone === "warn" && value > 0 ? "text-warn" : "text-ink"}`} data-testid="tile-value">
        {value}
      </span>
      <span className="mt-1.5 block text-[12.5px] text-ink-3">
        {value} of {of} item{of === 1 ? "" : "s"}
      </span>
    </Link>
  );
}

export default function Dashboard() {
  const { orgId } = useParams<{ orgId: string }>();
  const router = useRouter();
  const ws = useWorkspace();
  const [exporting, setExporting] = useState(false);
  const me = meOf(ws, orgId);
  const perms = ws.me[orgId]?.permissions;
  const itemsLoaded = ws.loaded[`items:${orgId}`] === "ok" && ws.loaded[`registers:${orgId}`] === "ok";
  const d = selectDashboard(ws, orgId);
  const registers = orgRegisters(ws, orgId, true);
  const myTasks = orgTasks(ws, orgId).filter((t) => t.assigned_to_user_id === me?.userId && ["PENDING", "IN_PROGRESS", "REJECTED", "SUBMITTED"].includes(t.status));
  const deptName = (id: string | null) => (id ? ws.departments[orgId]?.find((x) => x.id === id)?.name ?? "" : "No department");
  const base = `/workspace/${orgId}`;

  if (!itemsLoaded) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <SkeletonLine key={i} className="h-[88px]" />
          ))}
        </div>
        <ListSkeleton rows={3} />
      </div>
    );
  }

  if (registers.length === 0) {
    return (
      <EmptyState title="No registers yet. Start one from a circular." icon={<FileText className="h-6 w-6" />}>
        <span className="mt-2 flex flex-wrap justify-center gap-2">
          <Link href="/" className="btn-primary min-h-[44px] sm:min-h-0">
            Browse circulars
          </Link>
          {perms?.manage_registers && (
            <Link href={`${base}/registers?new=1`} className="btn-secondary min-h-[44px] sm:min-h-0">
              <Plus className="h-4 w-4" /> New register
            </Link>
          )}
        </span>
      </EmptyState>
    );
  }

  const list = (rows: typeof d.upcoming, overdue: boolean, empty: string) =>
    rows.length === 0 ? (
      <p className="px-4 py-5 text-[14px] text-ink-3">{empty}</p>
    ) : (
      <ul className="divide-y divide-line">
        {rows.slice(0, 12).map((r) => (
          <li key={`${r.kind}-${r.id}`}>
            <Link href={`${base}/items/${r.itemId}${r.kind === "task" ? `#task-${r.id}` : ""}`} className="flex min-h-[56px] items-start gap-3 px-4 py-2.5 hover:bg-sunken/60">
              <span className="w-[5.5rem] shrink-0 text-[13px]">
                <span className={`block font-semibold tabular-nums ${overdue ? "text-bad" : "text-ink"}`}>{formatDate(r.date)}</span>
                <span className={`block ${overdue ? "text-bad" : "text-ink-3"}`}>{daysLeftText(r.days)}</span>
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[14.5px] font-semibold text-ink">{r.title}</span>
                <span className="block text-[12.5px] text-ink-3">
                  {r.kind === "task" ? "Task" : "Item"}, {deptName(r.departmentId)}
                </span>
              </span>
              {r.kind === "item" ? <ItemStatusBadge status={r.status} /> : <TaskStatusBadge status={r.status} />}
            </Link>
          </li>
        ))}
      </ul>
    );

  return (
    <div className="space-y-6" data-testid="dashboard">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Link href={`${base}/report`} className="btn-secondary min-h-[44px] sm:min-h-0">
          <FileText className="h-4 w-4" /> Board report
        </Link>
        <button
          type="button"
          className="btn-secondary min-h-[44px] sm:min-h-0"
          disabled={exporting}
          onClick={async () => {
            setExporting(true);
            try {
              await downloadReportCsv(orgId);
            } catch (e: any) {
              setNotice({ kind: "error", text: `Could not download the report: ${e?.message || "unknown error"}` });
            } finally {
              setExporting(false);
            }
          }}
        >
          <Download className="h-4 w-4" /> Download CSV
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile href={`${base}/registers/all?status=OPEN`} label="Open obligations" value={d.open} of={d.total} />
        <Tile href={`${base}/registers/all?status=OVERDUE`} label="Overdue" value={d.overdue} of={d.total} tone="bad" />
        <Tile href={`${base}/registers/all?status=EVIDENCE_SUBMITTED`} label="Waiting for sign-off" value={d.waiting} of={d.total} tone="warn" />
        <Tile href={`${base}/registers/all?changed=1`} label="Circular changed" value={d.flagged} of={d.total} tone="warn" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="panel overflow-hidden" aria-label="Upcoming deadlines">
          <h2 className="section-title border-b border-line px-4 py-3">Upcoming deadlines (next 30 days)</h2>
          {list(d.upcoming, false, "Nothing is due in the next 30 days.")}
        </section>
        <section className="panel overflow-hidden" aria-label="Overdue">
          <h2 className="section-title border-b border-line px-4 py-3">Overdue</h2>
          {list(d.overdueList, true, "Nothing is overdue.")}
        </section>
      </div>

      <section className="panel overflow-hidden" aria-label="By department">
        <h2 className="section-title border-b border-line px-4 py-3">By department</h2>
        <div className="hidden grid-cols-[minmax(0,2fr)_repeat(6,minmax(0,1fr))] gap-3 border-b border-line px-4 py-2 text-[12.5px] font-semibold text-ink-3 md:grid">
          <span>Department</span>
          <span>Open</span>
          <span>Overdue</span>
          <span>Waiting sign-off</span>
          <span>Compliant</span>
          <span>Exempted</span>
          <span>Total</span>
        </div>
        <ul className="divide-y divide-line" data-testid="by-department">
          {d.byDepartment.map((r) => (
            <li key={r.departmentId ?? "none"}>
              <button
                type="button"
                onClick={() => router.push(`${base}/registers/all?department=${r.departmentId ?? "NONE"}`)}
                className="grid min-h-[56px] w-full grid-cols-3 gap-x-3 gap-y-1 px-4 py-2.5 text-left text-[14px] hover:bg-sunken/60 md:grid-cols-[minmax(0,2fr)_repeat(6,minmax(0,1fr))] md:items-center"
              >
                <span className="col-span-3 font-semibold text-ink md:col-span-1">{r.name}</span>
                <Cell label="Open" value={r.open} />
                <Cell label="Overdue" value={r.overdue} bad />
                <Cell label="Waiting sign-off" value={r.waiting} />
                <Cell label="Compliant" value={r.compliant} />
                <Cell label="Exempted" value={r.exempted} />
                <Cell label="Total" value={r.total} />
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel overflow-hidden" aria-label="My tasks">
        <h2 className="section-title border-b border-line px-4 py-3">My tasks</h2>
        {myTasks.length === 0 ? (
          <p className="px-4 py-5 text-[14px] text-ink-3">Nothing is assigned to you.</p>
        ) : (
          <ul className="divide-y divide-line">
            {myTasks.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2.5">
                <Link href={`${base}/items/${t.compliance_item_id}#task-${t.id}`} className="min-w-0 flex-1">
                  <span className="block text-[14.5px] font-semibold text-ink">{t.title}</span>
                  <span className={`block text-[12.5px] ${t.is_overdue ? "font-semibold text-bad" : "text-ink-3"}`}>
                    Due {formatDate(t.due_date)}, {daysLeftText(t.days_left).toLowerCase()}
                  </span>
                </Link>
                <TaskStatusBadge status={t.status} />
                {(t.status === "PENDING" || t.status === "IN_PROGRESS") && (
                  <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" onClick={() => void changeTask(orgId, t.id, { status: t.status === "PENDING" ? "IN_PROGRESS" : "PENDING" })}>
                    {t.status === "PENDING" ? "Start" : "Pause"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Cell({ label, value, bad }: { label: string; value: number; bad?: boolean }) {
  return (
    <span className="tabular-nums">
      <span className="block text-[11.5px] text-ink-3 md:hidden">{label}</span>
      <span className={bad && value > 0 ? "font-semibold text-bad" : "text-ink"}>{value}</span>
    </span>
  );
}
