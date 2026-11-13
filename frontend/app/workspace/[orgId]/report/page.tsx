"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Download, Printer } from "lucide-react";
import { ItemStatusBadge } from "@/components/workspace/badges";
import { LoadError, ListSkeleton } from "@/components/workspace/Shell";
import { fetchReport, downloadReportCsv, type ItemRead, type UserMini } from "@/services/workspaceApi";
import { countItems, daysLeftText, formatDate, formatDateTime, summarize } from "@/services/workspaceRules";
import { orgItems, orgRegisters, orgTasks, seedItems, setNotice, useWorkspace, departmentsOf } from "@/services/workspaceStore";

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="print-break-avoid rounded-control border border-line px-3 py-2">
      <span className="block text-[12.5px] text-ink-3">{label}</span>
      <span className="block text-[22px] font-bold tabular-nums text-ink">{value}</span>
    </div>
  );
}

function ItemLines({ items, empty }: { items: ItemRead[]; empty: string }) {
  if (items.length === 0) return <p className="text-[13.5px] text-ink-3">{empty}</p>;
  return (
    <ul className="divide-y divide-line rounded-control border border-line">
      {items.map((i) => (
        <li key={i.id} className="print-break-avoid flex flex-wrap items-start gap-x-4 gap-y-1 px-3 py-2 text-[13.5px]">
          <span className="min-w-0 flex-1">
            <span className="font-semibold text-ink">{i.obligation_title}</span>
            <span className="block text-[12.5px] text-ink-3">
              {i.source.reference_number}
              {i.source.page_number ? `, p. ${i.source.page_number}` : ""}
            </span>
          </span>
          <span className={`tabular-nums ${i.display_status === "OVERDUE" ? "font-semibold text-bad" : "text-ink"}`}>
            {formatDate(i.effective_deadline)} <span className="text-ink-3">{daysLeftText(i.days_left)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function ReportPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const ws = useWorkspace();
  const [registerId, setRegisterId] = useState("");
  const [meta, setMeta] = useState<{ by: UserMini; at: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchReport(orgId, registerId || null)
      .then((r) => {
        seedItems(r.items);
        setMeta({ by: r.generated_by, at: r.generated_at });
      })
      .catch((e) => setError(e?.message || "Could not load the report."))
      .finally(() => setLoading(false));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [orgId, registerId]);

  const registers = orgRegisters(ws, orgId, true);
  const all = orgItems(ws, orgId);
  const items = useMemo(() => all.filter((i) => !i.id.startsWith("tmp:") && (!registerId || i.register_id === registerId)), [all, registerId]);
  const tasks = orgTasks(ws, orgId);
  const departments = departmentsOf(ws, orgId);
  const d = useMemo(() => summarize(items, tasks, departments, ws.today), [items, tasks, departments, ws.today]);
  const c = useMemo(() => countItems(items, ws.today), [items, ws.today]);
  const orgName = ws.orgs?.find((o) => o.id === orgId)?.name ?? "";
  const registerTitle = registerId ? ws.registers[registerId]?.title : null;
  const overdue = items.filter((i) => i.display_status === "OVERDUE");
  const upcoming = d.upcoming.filter((u) => u.kind === "item").map((u) => items.find((i) => i.id === u.id)!).filter(Boolean);
  const flagged = items.filter((i) => i.source_change);
  const deptName = (id: string | null) => (id ? departments.find((x) => x.id === id)?.name ?? "" : "");

  if (error && items.length === 0) return <LoadError message={error} onRetry={load} />;
  if (loading && items.length === 0 && ws.loaded[`items:${orgId}`] !== "ok") return <ListSkeleton rows={3} />;

  return (
    <div className="space-y-6" data-testid="report-page">
      <div className="no-print flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 max-w-full">
          <label className="sr-only" htmlFor="report-register">
            Register
          </label>
          <select id="report-register" className="field h-11 w-auto max-w-full py-1 sm:h-9" value={registerId} onChange={(e) => setRegisterId(e.target.value)}>
            <option value="">All registers</option>
            {registers.map((r) => (
              <option key={r.id} value={r.id}>
                {r.title}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-primary min-h-[44px] sm:min-h-0" onClick={() => window.print()}>
            <Printer className="h-4 w-4" /> Print or save as PDF
          </button>
          <button
            type="button"
            className="btn-secondary min-h-[44px] sm:min-h-0"
            disabled={exporting}
            onClick={async () => {
              setExporting(true);
              try {
                await downloadReportCsv(orgId, registerId || null);
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
      </div>

      <header className="space-y-1 border-b border-line pb-4">
        <p className="text-[13px] font-semibold uppercase tracking-wide text-ink-3">{orgName}</p>
        <h2 className="text-[22px] font-bold tracking-tight text-ink">Compliance status as of {formatDate(ws.today)}</h2>
        {registerTitle && <p className="text-[14px] text-ink-2">Register: {registerTitle}</p>}
        <p className="text-[13px] text-ink-3">{meta ? `Generated by ${meta.by.full_name}, ${formatDateTime(meta.at)}` : "Generating…"}</p>
      </header>

      <section aria-label="Totals" className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8" data-testid="report-totals">
        <Stat label="Items" value={c.total} />
        <Stat label="Open" value={d.open} />
        <Stat label="Overdue" value={c.overdue} />
        <Stat label="Waiting sign-off" value={c.evidence_submitted} />
        <Stat label="Compliant" value={c.compliant} />
        <Stat label="Exempted" value={c.exempted} />
        <Stat label="Not started" value={c.not_started} />
        <Stat label="Circular changed" value={c.flagged} />
      </section>

      <section aria-label="By department" className="print-break-avoid">
        <h3 className="section-title mb-2">By department</h3>
        <div className="hidden grid-cols-[minmax(0,2fr)_repeat(6,minmax(0,1fr))] gap-3 border-b border-line px-3 py-1.5 text-[12.5px] font-semibold text-ink-3 md:grid">
          <span>Department</span>
          <span>Open</span>
          <span>Overdue</span>
          <span>Waiting sign-off</span>
          <span>Compliant</span>
          <span>Exempted</span>
          <span>Total</span>
        </div>
        <ul className="divide-y divide-line rounded-control border border-line">
          {d.byDepartment.map((r) => (
            <li key={r.departmentId ?? "none"} className="grid grid-cols-3 gap-x-3 gap-y-1 px-3 py-2 text-[13.5px] tabular-nums md:grid-cols-[minmax(0,2fr)_repeat(6,minmax(0,1fr))]">
              <span className="col-span-3 font-semibold text-ink md:col-span-1">{r.name}</span>
              <span>
                <span className="text-[11.5px] text-ink-3 md:hidden">Open </span>
                {r.open}
              </span>
              <span className={r.overdue ? "font-semibold text-bad" : ""}>
                <span className="text-[11.5px] font-normal text-ink-3 md:hidden">Overdue </span>
                {r.overdue}
              </span>
              <span>
                <span className="text-[11.5px] text-ink-3 md:hidden">Waiting </span>
                {r.waiting}
              </span>
              <span>
                <span className="text-[11.5px] text-ink-3 md:hidden">Compliant </span>
                {r.compliant}
              </span>
              <span>
                <span className="text-[11.5px] text-ink-3 md:hidden">Exempted </span>
                {r.exempted}
              </span>
              <span>
                <span className="text-[11.5px] text-ink-3 md:hidden">Total </span>
                {r.total}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Overdue" className="space-y-2">
        <h3 className="section-title">Overdue</h3>
        <ItemLines items={overdue} empty="Nothing is overdue." />
      </section>
      <section aria-label="Upcoming" className="space-y-2">
        <h3 className="section-title">Due in the next 30 days</h3>
        <ItemLines items={upcoming} empty="Nothing is due in the next 30 days." />
      </section>
      <section aria-label="Circular changed" className="space-y-2">
        <h3 className="section-title">Circular changed</h3>
        <ItemLines items={flagged} empty="No source circular has changed." />
      </section>

      <section aria-label="All items" className="space-y-2">
        <h3 className="section-title">All items</h3>
        <ul className="divide-y divide-line rounded-control border border-line" data-testid="report-items">
          {items.map((i) => (
            <li key={i.id} className="print-break-avoid space-y-1 px-3 py-2.5 text-[13.5px]">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <span className="min-w-0 flex-1 font-semibold text-ink">{i.obligation_title}</span>
                <ItemStatusBadge status={i.display_status} />
              </div>
              <p className="text-[12.5px] text-ink-3">
                {i.source.reference_number}
                {i.source.page_number ? `, p. ${i.source.page_number}` : ""}
                {deptName(i.department_id) ? `, ${deptName(i.department_id)}` : ""}
                {i.assigned_lead ? `, lead ${i.assigned_lead.full_name}` : ""}
                {`, deadline ${formatDate(i.effective_deadline)}`}
                {i.signed_off_by ? `, signed off by ${i.signed_off_by.full_name}` : ""}
              </p>
              {i.source.quote && <p className="text-[12.5px] leading-relaxed text-ink-2">&ldquo;{i.source.quote}&rdquo;</p>}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
